#!/usr/bin/env python3
"""
Utility Provider Reconciler - Uses AI to pick the best utility provider
when multiple sources (CSV, HIFLD, EPA, municipal) return different results.
Works for electric, gas, and water utilities.
"""

import os
import json
from typing import Optional, Dict, List

# Lazy-load OpenAI client to avoid import errors when API key not set
_client = None

def get_openai_client():
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    return _client

def reconcile_utility_providers(
    address: str,
    city: str,
    state: str,
    zip_code: str,
    utility_type: str,
    candidates: List[Dict]
) -> Optional[Dict]:
    """
    Use AI to pick the best utility provider from multiple candidates.
    
    Args:
        address: Full street address
        city: City name
        state: State abbreviation
        zip_code: ZIP code
        utility_type: 'electric', 'gas', or 'water'
        candidates: List of provider dicts from different sources
        
    Returns:
        Best matching provider dict with confidence explanation
    """
    if not candidates:
        return None
    
    if len(candidates) == 1:
        candidates[0]['_reconciliation'] = 'single_source'
        return candidates[0]
    
    # Check if all candidates are the same provider (just different sources)
    names = set()
    for c in candidates:
        name = (c.get('name') or '').lower()
        # Normalize name for comparison - remove common suffixes
        for suffix in ['water department', 'water utility', 'electric', 'gas', 
                       'utilities', 'utility', 'company', 'corp', 'inc', 'llc']:
            name = name.replace(suffix, '')
        names.add(name.strip()[:20])  # First 20 chars for fuzzy match
    
    if len(names) == 1:
        # All sources agree - return the one with most info
        best = max(candidates, key=lambda c: sum(1 for v in c.values() if v))
        best['_reconciliation'] = 'sources_agree'
        return best
    
    # Build utility-specific context for AI
    utility_context = {
        'electric': """
1. IOUs (Investor-Owned Utilities) like Duke Energy, Xcel serve large territories
2. Electric cooperatives (co-ops) serve rural areas, often with "Electric Cooperative" in name
3. Municipal electric utilities serve specific cities
4. In deregulated states (TX, PA, etc.), there's a delivery company (TDU) vs retail providers
5. HIFLD polygon data is authoritative for service territories""",
        'gas': """
1. Large gas utilities (Atmos, CenterPoint, etc.) serve multi-state regions
2. Municipal gas utilities serve specific cities
3. Some areas have no natural gas service (propane only)
4. State LDC (Local Distribution Company) data is authoritative""",
        'water': """
1. Municipal/township water departments typically serve addresses within that municipality
2. Regional providers (like "NJ American Water") serve broader areas but may not serve addresses in cities with their own municipal water
3. MUDs (Municipal Utility Districts) serve specific developments, usually identified by number
4. EPA SDWIS data covers larger service areas; local municipal data is more specific"""
    }
    
    # Sources disagree - use AI to pick
    prompt = f"""You are a utility service territory expert. Given an address and multiple {utility_type} provider candidates from different data sources, determine which provider most likely serves this specific address.

Address: {address}
City: {city}
State: {state}
ZIP: {zip_code}
Utility Type: {utility_type}

Candidates:
{json.dumps(candidates, indent=2, default=str)}

Consider:
{utility_context.get(utility_type, utility_context['electric'])}
- Provider names containing the city name are more likely correct for that city
- CSV provider data is curated; federal data (HIFLD, EPA) covers larger areas

Return JSON with:
{{
    "best_match_index": <0-based index of best candidate>,
    "confidence": "high" | "medium" | "low",
    "reasoning": "<brief explanation>"
}}

Return ONLY valid JSON, no other text."""

    try:
        response = get_openai_client().chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=300
        )
        
        content = response.choices[0].message.content.strip()
        # Extract JSON
        if content.startswith('```'):
            content = content.split('```')[1]
            if content.startswith('json'):
                content = content[4:]
        
        result = json.loads(content)
        best_idx = result.get('best_match_index', 0)
        
        if 0 <= best_idx < len(candidates):
            best = candidates[best_idx]
            best['_reconciliation'] = 'ai_selected'
            best['_reconciliation_confidence'] = result.get('confidence', 'medium')
            best['_reconciliation_reasoning'] = result.get('reasoning', '')
            return best
        
    except Exception as e:
        print(f"[Reconciler] AI error for {utility_type}: {e}")
    
    # Fallback: prefer municipal/local providers over regional
    for c in candidates:
        name_lower = (c.get('name') or '').lower()
        if 'township' in name_lower or 'municipal' in name_lower or city.lower() in name_lower:
            c['_reconciliation'] = 'heuristic_local'
            return c
    
    # Last resort: return first candidate
    candidates[0]['_reconciliation'] = 'fallback'
    return candidates[0]


# Backwards compatibility alias
def reconcile_water_providers(address, city, state, zip_code, candidates):
    return reconcile_utility_providers(address, city, state, zip_code, 'water', candidates)


def get_all_utility_candidates(
    city: str,
    state: str,
    utility_type: str,
    zip_code: str = None,
    county: str = None,
    lat: float = None,
    lon: float = None
) -> List[Dict]:
    """
    Gather utility provider candidates from all sources.
    
    Args:
        city: City name
        state: State abbreviation
        utility_type: 'electric', 'gas', or 'water'
        zip_code: ZIP code (optional)
        county: County name (optional)
        lat: Latitude (optional)
        lon: Longitude (optional)
    """
    candidates = []
    
    if utility_type == 'electric':
        return _get_electric_candidates(city, state, zip_code, county, lat, lon)
    elif utility_type == 'gas':
        return _get_gas_candidates(city, state, zip_code, county)
    elif utility_type == 'water':
        return _get_water_candidates(city, state, zip_code, county)
    
    return candidates


def _get_electric_candidates(city, state, zip_code, county, lat, lon) -> List[Dict]:
    """Gather electric provider candidates from all sources."""
    candidates = []
    
    # Source 1: CSV providers (UtilityTypeId = 1 for electric)
    try:
        from csv_utility_lookup import lookup_utility_from_csv
        csv_result = lookup_utility_from_csv(city, state, 'electric')
        if csv_result:
            csv_result['_source'] = 'csv_providers'
            candidates.append(csv_result)
    except Exception as e:
        pass
    
    # Source 2: HIFLD polygon data (most authoritative for electric)
    # This is already the primary source in the main lookup
    
    # Source 3: Municipal utilities
    try:
        from municipal_utilities import lookup_municipal_electric
        muni_result = lookup_municipal_electric(city, state)
        if muni_result:
            muni_result['_source'] = 'municipal_utility'
            candidates.append(muni_result)
    except Exception as e:
        pass
    
    # Source 4: FindEnergy data
    try:
        from findenergy_lookup import lookup_findenergy
        fe_result = lookup_findenergy(zip_code, 'electric') if zip_code else None
        if fe_result:
            fe_result['_source'] = 'findenergy'
            candidates.append(fe_result)
    except Exception as e:
        pass
    
    return candidates


def _get_gas_candidates(city, state, zip_code, county) -> List[Dict]:
    """Gather gas provider candidates from all sources."""
    candidates = []
    
    # Source 1: CSV providers (UtilityTypeId = 2 for gas)
    try:
        from csv_utility_lookup import lookup_utility_from_csv
        csv_result = lookup_utility_from_csv(city, state, 'gas')
        if csv_result:
            csv_result['_source'] = 'csv_providers'
            candidates.append(csv_result)
    except Exception as e:
        pass
    
    # Source 2: Municipal utilities
    try:
        from municipal_utilities import lookup_municipal_gas
        muni_result = lookup_municipal_gas(city, state)
        if muni_result:
            muni_result['_source'] = 'municipal_utility'
            candidates.append(muni_result)
    except Exception as e:
        pass
    
    # Source 3: State LDC mapping
    try:
        from pathlib import Path
        import json as json_mod
        gas_file = Path(__file__).parent / "gas_utilities_lookup.json"
        if gas_file.exists():
            with open(gas_file, 'r') as f:
                gas_data = json_mod.load(f)
            city_key = f"{state}|{city.upper()}"
            if city_key in gas_data.get('by_city', {}):
                gas_result = gas_data['by_city'][city_key].copy()
                gas_result['_source'] = 'state_ldc'
                candidates.append(gas_result)
    except Exception as e:
        pass
    
    return candidates


def _get_water_candidates(city, state, zip_code, county) -> List[Dict]:
    """Gather water provider candidates from all sources."""
    candidates = []
    
    # Source 1: CSV providers
    try:
        from csv_water_lookup import lookup_water_from_csv
        csv_result = lookup_water_from_csv(city, state)
        if csv_result:
            csv_result['_source'] = 'csv_providers'
            candidates.append(csv_result)
    except Exception as e:
        print(f"[Reconciler] CSV lookup error: {e}")
    
    # Source 2: EPA SDWIS
    try:
        from pathlib import Path
        import json as json_mod
        water_file = Path(__file__).parent / "water_utilities_lookup.json"
        if water_file.exists():
            with open(water_file, 'r') as f:
                epa_data = json_mod.load(f)
            city_key = f"{state}|{city.upper()}"
            if city_key in epa_data.get('by_city', {}):
                epa_result = epa_data['by_city'][city_key].copy()
                epa_result['_source'] = 'epa_sdwis'
                candidates.append(epa_result)
    except Exception as e:
        print(f"[Reconciler] EPA lookup error: {e}")
    
    # Source 3: Municipal utilities
    try:
        from municipal_utilities import lookup_municipal_water
        muni_result = lookup_municipal_water(city, state)
        if muni_result:
            muni_result['_source'] = 'municipal_utility'
            candidates.append(muni_result)
    except Exception as e:
        print(f"[Reconciler] Municipal lookup error: {e}")
    
    return candidates


# Backwards compatibility alias
def get_all_water_candidates(city, state, zip_code=None, county=None):
    return get_all_utility_candidates(city, state, 'water', zip_code, county)


if __name__ == '__main__':
    # Test
    test_cases = [
        ("3211 Ventura Dr", "East Hanover", "NJ", "07936"),
        ("100 Congress Ave", "Austin", "TX", "78701"),
        ("123 Main St", "Short Hills", "NJ", "07078"),
    ]
    
    for addr, city, state, zip_code in test_cases:
        print(f"\n=== {addr}, {city}, {state} {zip_code} ===")
        candidates = get_all_water_candidates(city, state, zip_code)
        print(f"Found {len(candidates)} candidates:")
        for i, c in enumerate(candidates):
            print(f"  {i}: {c.get('name')} ({c.get('_source')})")
        
        if candidates:
            best = reconcile_water_providers(addr, city, state, zip_code, candidates)
            print(f"Best: {best.get('name')} (via {best.get('_reconciliation')})")
