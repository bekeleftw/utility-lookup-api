#!/usr/bin/env python3
"""
CSV-based utility provider lookup for electric and gas.
Uses utility_providers_IDs.csv as a data source.

UtilityTypeId mapping:
- 1 = Electric
- 2 = Gas
- 3 = Water (handled by csv_water_lookup.py)
"""

import csv
import os
import re
from typing import Optional, Dict, List

# Cache
_providers_cache = {}

CSV_FILE = os.path.join(os.path.dirname(__file__), 'utility_providers_IDs.csv')

UTILITY_TYPE_IDS = {
    'electric': '2',  # 1,669 entries
    'water': '3',     # 8,368 entries
    'gas': '4',       # 833 entries
    'trash': '5',     # 1,768 entries
    'sewer': '6'      # 1,706 entries
}


def normalize_city(city: str) -> str:
    """Normalize city name for matching."""
    if not city:
        return ''
    city = city.lower().strip()
    city = re.sub(r'^city of\s+', '', city)
    city = re.sub(r'^town of\s+', '', city)
    city = re.sub(r'^village of\s+', '', city)
    city = re.sub(r'\s+township$', '', city)
    city = re.sub(r'\s+city$', '', city)
    city = re.sub(r'\s*-\s*[a-z]{2}$', '', city)
    city = re.sub(r'\s*\([a-z]{2}\)$', '', city)
    return city.strip()


def extract_city_state_from_title(title: str) -> tuple:
    """Extract city and state from provider title."""
    if not title:
        return None, None
    
    # Pattern: "Something Something - ST" (state at end after dash)
    match = re.search(r'^(.+?)\s*[-–]\s*([A-Z]{2})$', title)
    if match:
        first_part = match.group(1)
        state = match.group(2)
        # Try to extract city name
        city_match = re.match(
            r'^((?:City of |Town of |Village of )?[\w\s]+?)(?:\s+(?:Township|County|Municipal|Water|Electric|Gas|Utility|Utilities|Department|District|MUD|PWS|WCID|Energy|Power|Light))',
            first_part, re.IGNORECASE
        )
        if city_match:
            return normalize_city(city_match.group(1)), state
        words = first_part.split()
        if len(words) >= 2:
            if words[0].lower() in ['city', 'town', 'village']:
                city = ' '.join(words[1:3]) if len(words) > 2 else words[1]
            else:
                city = ' '.join(words[:2])
            return normalize_city(city), state
        return normalize_city(first_part), state
    
    # Pattern: "City Name (ST)"
    match = re.search(r'^(.+?)\s*\(([A-Z]{2})\)$', title)
    if match:
        return normalize_city(match.group(1)), match.group(2)
    
    # Pattern: "City Name, ST"
    match = re.search(r'^(.+?),\s*([A-Z]{2})$', title)
    if match:
        return normalize_city(match.group(1)), match.group(2)
    
    return normalize_city(title), None


def load_providers(utility_type: str) -> Dict[str, List[Dict]]:
    """Load providers from CSV, indexed by state|city."""
    global _providers_cache
    
    cache_key = utility_type
    if cache_key in _providers_cache:
        return _providers_cache[cache_key]
    
    if not os.path.exists(CSV_FILE):
        print(f"[CSVUtility] CSV not found: {CSV_FILE}")
        _providers_cache[cache_key] = {}
        return _providers_cache[cache_key]
    
    type_id = UTILITY_TYPE_IDS.get(utility_type)
    if not type_id:
        return {}
    
    providers = {}
    
    with open(CSV_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                if row.get('UtilityTypeId', '').strip() != type_id:
                    continue
                
                provider_id = row.get('ID', '').strip()
                title = row.get('Title', '').strip()
                
                if not provider_id or not title:
                    continue
                
                city, state = extract_city_state_from_title(title)
                
                provider = {
                    'id': provider_id,
                    'name': title,
                    'phone': row.get('Phone', ''),
                    'website': row.get('URL', ''),
                    'city': city,
                    'state': state,
                    '_source': 'csv_providers'
                }
                
                if state and city:
                    key = f"{state}|{city}".upper()
                    if key not in providers:
                        providers[key] = []
                    providers[key].append(provider)
                
                if city:
                    city_key = f"ANY|{city}".upper()
                    if city_key not in providers:
                        providers[city_key] = []
                    providers[city_key].append(provider)
                    
            except Exception:
                continue
    
    print(f"[CSVUtility] Loaded {len(providers)} city/state combinations for {utility_type}")
    _providers_cache[cache_key] = providers
    return providers


def lookup_utility_from_csv(city: str, state: str, utility_type: str) -> Optional[Dict]:
    """
    Look up utility provider from CSV by city and state.
    
    Args:
        city: City name
        state: State abbreviation
        utility_type: 'electric' or 'gas'
    
    Returns:
        Best match or None
    """
    if not city or utility_type not in ['electric', 'gas', 'trash', 'sewer']:
        return None
    
    providers = load_providers(utility_type)
    city_norm = normalize_city(city).upper()
    
    # Try exact state|city match first (most reliable)
    if state:
        key = f"{state}|{city_norm}"
        if key in providers:
            matches = providers[key]
            # Filter to only providers that match the state
            state_matches = [m for m in matches if m.get('state') == state]
            if state_matches:
                if len(state_matches) == 1:
                    return state_matches[0]
                # Multiple matches - prefer ones with city name or "municipal" in name
                for m in state_matches:
                    name_lower = m['name'].lower()
                    if city.lower() in name_lower or 'municipal' in name_lower:
                        return m
                return state_matches[0]
    
    # Don't use ANY| fallback - it causes cross-state mismatches
    return None


def get_csv_utility_candidates(city: str, state: str, utility_type: str) -> List[Dict]:
    """Get all utility provider candidates from CSV for a city/state."""
    if not city or utility_type not in ['electric', 'gas', 'trash', 'sewer']:
        return []
    
    providers = load_providers(utility_type)
    city_norm = normalize_city(city).upper()
    
    candidates = []
    
    if state:
        key = f"{state}|{city_norm}"
        if key in providers:
            candidates.extend(providers[key])
    
    any_key = f"ANY|{city_norm}"
    if any_key in providers:
        for p in providers[any_key]:
            if p not in candidates:
                candidates.append(p)
    
    return candidates


if __name__ == '__main__':
    # Test
    test_cases = [
        ('Austin', 'TX', 'electric'),
        ('Austin', 'TX', 'gas'),
        ('Dallas', 'TX', 'electric'),
        ('Columbus', 'OH', 'gas'),
    ]
    
    for city, state, utype in test_cases:
        result = lookup_utility_from_csv(city, state, utype)
        if result:
            print(f"{city}, {state} ({utype}) -> {result['name']} (ID: {result['id']})")
        else:
            print(f"{city}, {state} ({utype}) -> No match")
