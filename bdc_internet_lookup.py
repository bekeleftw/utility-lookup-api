"""
Fast internet provider lookup using local SQLite BDC database.
"""

import sqlite3
import os
from typing import Optional, Dict, List

DB_PATH = os.path.join(os.path.dirname(__file__), 'bdc_internet_new.db')

# Technology code mapping from FCC BDC
TECHNOLOGY_CODES = {
    '10': 'DSL',
    '40': 'Cable',
    '50': 'Fiber',
    '60': 'Fixed Wireless (Licensed)',
    '61': 'Fixed Wireless (Unlicensed)',
    '70': 'Satellite',
    '71': 'GSO Satellite',
    '72': 'NGSO Satellite',
    '0': 'Other',
}


def get_available_states() -> List[str]:
    """Check if the BDC database is available."""
    if os.path.exists(DB_PATH):
        return ['ALL']  # Full nationwide coverage
    return []


def lookup_internet_by_block(block_geoid: str) -> Optional[Dict]:
    """
    Look up internet providers by census block GEOID.
    
    Args:
        block_geoid: 15-digit census block GEOID
        
    Returns:
        Dict with providers list or None if not found
    """
    if not os.path.exists(DB_PATH):
        return None
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Try exact block match first
        cursor.execute('''
            SELECT provider_name, technology, max_down, max_up, low_latency
            FROM providers
            WHERE block_geoid = ?
        ''', (block_geoid,))
        
        rows = cursor.fetchall()
        
        # If no exact match, try tract-level match (first 11 digits)
        # This handles cases where geocoder returns a slightly different block suffix
        if not rows and len(block_geoid) >= 11:
            tract_prefix = block_geoid[:11]
            cursor.execute('''
                SELECT provider_name, technology, max_down, max_up, low_latency
                FROM providers
                WHERE block_geoid LIKE ?
                LIMIT 1000
            ''', (tract_prefix + '%',))
            rows = cursor.fetchall()
            if rows:
                print(f"  BDC: No exact block match, using tract-level data ({len(rows)} records)")
        
        conn.close()
        
        if not rows:
            return {'providers': [], 'provider_count': 0, 'block_geoid': block_geoid}
        
        providers = []
        seen = set()
        
        for row in rows:
            provider_name, tech_code, max_down, max_up, low_latency = row
            
            # Skip duplicates (same provider, same technology)
            key = (provider_name, tech_code)
            if key in seen:
                continue
            seen.add(key)
            
            technology = TECHNOLOGY_CODES.get(str(tech_code), f'Unknown ({tech_code})')
            
            providers.append({
                'name': provider_name,
                'technology': technology,
                'max_download_mbps': max_down or 0,
                'max_upload_mbps': max_up or 0,
                'low_latency': bool(low_latency),
            })
        
        # Sort by download speed descending
        providers.sort(key=lambda x: x['max_download_mbps'], reverse=True)
        
        return {
            'providers': providers,
            'provider_count': len(providers),
            'block_geoid': block_geoid,
            'source': 'fcc_bdc_local'
        }
        
    except Exception as e:
        print(f"BDC lookup error: {e}")
        return None


def lookup_internet_fast(address: str) -> Optional[Dict]:
    """
    Fast internet lookup - requires block_geoid to be passed separately.
    This is a wrapper that expects geocoding to be done externally.
    
    For direct block lookups, use lookup_internet_by_block() instead.
    """
    # This function exists for API compatibility but requires the caller
    # to provide block_geoid. The main lookup flow in utility_lookup_v1.py
    # should call lookup_internet_by_block() directly with the geocoded block.
    return None


if __name__ == '__main__':
    # Test lookup
    test_block = '040210101001000'  # Arizona block
    result = lookup_internet_by_block(test_block)
    if result:
        print(f"Found {result['provider_count']} providers for block {test_block}")
        for p in result['providers'][:5]:
            print(f"  {p['name']}: {p['max_download_mbps']} Mbps ({p['technology']})")
    else:
        print("No results")
