#!/usr/bin/env python3
"""
Combined internet provider lookup using multiple sources.

Sources (in priority order):
1. FCC BDC database (local SQLite) - most authoritative, address-level
2. BroadbandNow.com - good coverage, ZIP-level
3. AllConnect.com - additional providers, city/ZIP-level

Deduplicates and merges results from all sources.
"""

import os
from typing import Optional, Dict, List
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

# Canonical provider names for deduplication across sources
CANONICAL_NAMES = {
    'at&t': 'AT&T', 'att': 'AT&T', 'at&t internet': 'AT&T',
    'xfinity': 'Xfinity', 'comcast': 'Xfinity', 'xfinity internet': 'Xfinity',
    'spectrum': 'Spectrum', 'charter': 'Spectrum', 'spectrum internet': 'Spectrum',
    'verizon': 'Verizon', 'verizon fios': 'Verizon Fios', 'fios': 'Verizon Fios',
    'google fiber': 'Google Fiber',
    'frontier': 'Frontier', 'frontier communications': 'Frontier',
    'centurylink': 'CenturyLink', 'lumen': 'CenturyLink', 'century link': 'CenturyLink',
    'cox': 'Cox', 'cox communications': 'Cox',
    'optimum': 'Optimum', 'altice': 'Optimum', 'cablevision': 'Optimum',
    'mediacom': 'Mediacom',
    'windstream': 'Windstream',
    'hughesnet': 'HughesNet', 'hughes': 'HughesNet',
    'viasat': 'Viasat', 'exede': 'Viasat',
    't-mobile': 'T-Mobile', 't-mobile 5g': 'T-Mobile', 'tmobile': 'T-Mobile',
    'starlink': 'Starlink',
    'earthlink': 'EarthLink',
    'astound': 'Astound', 'rcn': 'Astound', 'wave': 'Astound',
    'grande': 'Grande', 'grande communications': 'Grande',
    'ziply': 'Ziply Fiber', 'ziply fiber': 'Ziply Fiber',
    'consolidated': 'Consolidated Communications',
    'tds': 'TDS Telecom', 'tds telecom': 'TDS Telecom',
    'breezeline': 'Breezeline', 'atlantic broadband': 'Breezeline',
    'wow': 'WOW!', 'wide open west': 'WOW!',
    'metronet': 'Metronet',
    'ting': 'Ting', 'ting internet': 'Ting',
    'fidium': 'Fidium', 'fidium fiber': 'Fidium',
    'sonic': 'Sonic',
    'rise broadband': 'Rise Broadband',
    'sparklight': 'Sparklight', 'cable one': 'Sparklight',
    'midco': 'Midco',
    'suddenlink': 'Suddenlink', 'altice usa': 'Suddenlink',
}

# Technology priority for merging (higher = better)
TECH_PRIORITY = {
    'Fiber': 100,
    '5G': 90,
    'Cable': 80,
    'Fixed Wireless': 70,
    'DSL': 60,
    'Satellite': 50,
    'Unknown': 0,
}


def normalize_provider_name(name: str) -> str:
    """Normalize provider name for deduplication."""
    if not name:
        return ""
    normalized = name.lower().strip()
    return CANONICAL_NAMES.get(normalized, name)


def merge_provider_data(providers: List[Dict]) -> List[Dict]:
    """
    Merge provider data from multiple sources, deduplicating by name.
    Keeps the best data (highest speed, best technology) for each provider.
    """
    merged = defaultdict(lambda: {
        'name': None,
        'technology': 'Unknown',
        'max_download_mbps': 0,
        'max_upload_mbps': 0,
        'sources': [],
    })
    
    for p in providers:
        name = normalize_provider_name(p.get('name', ''))
        if not name:
            continue
        
        key = name.lower()
        entry = merged[key]
        
        # Set canonical name
        if not entry['name']:
            entry['name'] = name
        
        # Keep best technology
        new_tech = p.get('technology', 'Unknown')
        if TECH_PRIORITY.get(new_tech, 0) > TECH_PRIORITY.get(entry['technology'], 0):
            entry['technology'] = new_tech
        
        # Keep highest speeds
        new_down = p.get('max_download_mbps') or 0
        new_up = p.get('max_upload_mbps') or 0
        if new_down > entry['max_download_mbps']:
            entry['max_download_mbps'] = new_down
        if new_up > entry['max_upload_mbps']:
            entry['max_upload_mbps'] = new_up
        
        # Track sources
        source = p.get('source', 'unknown')
        if source not in entry['sources']:
            entry['sources'].append(source)
    
    # Convert to list and sort by download speed
    result = list(merged.values())
    result.sort(key=lambda x: (
        TECH_PRIORITY.get(x['technology'], 0),
        x['max_download_mbps']
    ), reverse=True)
    
    return result


def lookup_internet_combined(
    zip_code: str,
    city: str = None,
    state: str = None,
    block_geoid: str = None,
    include_satellite: bool = True
) -> Optional[Dict]:
    """
    Look up internet providers using all available sources.
    
    Args:
        zip_code: 5-digit ZIP code
        city: City name (optional, improves accuracy)
        state: State abbreviation (optional)
        block_geoid: Census block GEOID for BDC lookup (optional)
        include_satellite: Whether to include satellite providers
        
    Returns:
        Dict with merged providers list
    """
    all_providers = []
    sources_used = []
    
    # Source 1: FCC BDC database (most authoritative)
    if block_geoid:
        try:
            from bdc_internet_lookup import lookup_internet_by_block
            bdc_result = lookup_internet_by_block(block_geoid)
            if bdc_result and bdc_result.get('providers'):
                for p in bdc_result['providers']:
                    p['source'] = 'fcc_bdc'
                all_providers.extend(bdc_result['providers'])
                sources_used.append('fcc_bdc')
                print(f"  [Internet] BDC: {len(bdc_result['providers'])} providers")
        except ImportError:
            pass
        except Exception as e:
            print(f"  [Internet] BDC error: {e}")
    
    # Source 2 & 3: BroadbandNow and AllConnect (run concurrently)
    def fetch_broadbandnow():
        try:
            from broadbandnow_lookup import lookup_broadbandnow
            return ('broadbandnow', lookup_broadbandnow(zip_code, city, state))
        except Exception as e:
            print(f"  [Internet] BroadbandNow error: {e}")
            return ('broadbandnow', None)
    
    def fetch_allconnect():
        try:
            from allconnect_lookup import lookup_allconnect
            return ('allconnect', lookup_allconnect(zip_code, city, state))
        except Exception as e:
            print(f"  [Internet] AllConnect error: {e}")
            return ('allconnect', None)
    
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(fetch_broadbandnow), executor.submit(fetch_allconnect)]
        for future in as_completed(futures):
            source_name, result = future.result()
            if result and result.get('providers'):
                for p in result['providers']:
                    p['source'] = source_name
                all_providers.extend(result['providers'])
                sources_used.append(source_name)
                print(f"  [Internet] {source_name}: {len(result['providers'])} providers")
    
    if not all_providers:
        return None
    
    # Merge and deduplicate
    merged = merge_provider_data(all_providers)
    
    # Filter satellite if requested
    if not include_satellite:
        merged = [p for p in merged if p['technology'] != 'Satellite']
    
    return {
        'providers': merged,
        'provider_count': len(merged),
        'sources': sources_used,
        'zip_code': zip_code,
    }


if __name__ == '__main__':
    # Test combined lookup
    test_cases = [
        ('78701', 'Austin', 'TX'),
        ('07102', 'Newark', 'NJ'),
        ('90210', 'Beverly Hills', 'CA'),
    ]
    
    for zip_code, city, state in test_cases:
        print(f"\n{'='*60}")
        print(f"Combined lookup: {city}, {state} ({zip_code})")
        print('='*60)
        
        result = lookup_internet_combined(zip_code, city, state)
        
        if result:
            print(f"\nFound {result['provider_count']} unique providers from {result['sources']}:")
            for p in result['providers'][:15]:
                speed = f" - {p['max_download_mbps']} Mbps" if p['max_download_mbps'] else ""
                sources = f" [{', '.join(p['sources'])}]"
                print(f"  {p['name']} ({p['technology']}){speed}{sources}")
        else:
            print("No results")
