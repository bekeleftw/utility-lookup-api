#!/usr/bin/env python3
"""
CSV-based water provider lookup.
Uses utility_providers_IDs.csv as a data source for water providers.
"""

import csv
import os
import re
from typing import Optional, Dict, List

# Cache
_water_providers_cache = None

CSV_FILE = os.path.join(os.path.dirname(__file__), 'utility_providers_IDs.csv')

def normalize_city(city: str) -> str:
    """Normalize city name for matching."""
    if not city:
        return ''
    city = city.lower().strip()
    # Remove common prefixes/suffixes
    city = re.sub(r'^city of\s+', '', city)
    city = re.sub(r'^town of\s+', '', city)
    city = re.sub(r'^village of\s+', '', city)
    city = re.sub(r'\s+township$', '', city)
    city = re.sub(r'\s+city$', '', city)
    # Remove state suffixes like "- NJ" or "(NJ)"
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
        # Extract city from the first part (e.g., "East Hanover Township Water Department")
        first_part = match.group(1)
        state = match.group(2)
        # Try to extract city name - look for common patterns
        city_match = re.match(r'^((?:City of |Town of |Village of )?[\w\s]+?)(?:\s+(?:Township|County|Municipal|Water|Utility|Utilities|Department|District|MUD|PWS|WCID))', first_part, re.IGNORECASE)
        if city_match:
            return normalize_city(city_match.group(1)), state
        # Fallback: use first 2-3 words as city
        words = first_part.split()
        if len(words) >= 2:
            # Check if first word is "City", "Town", etc.
            if words[0].lower() in ['city', 'town', 'village']:
                city = ' '.join(words[1:3]) if len(words) > 2 else words[1]
            else:
                city = ' '.join(words[:2])
            return normalize_city(city), state
        return normalize_city(first_part), state
    
    match = re.search(r'^(.+?)\s*\(([A-Z]{2})\)$', title)
    if match:
        return normalize_city(match.group(1)), match.group(2)
    
    # Pattern: "City Name, ST"
    match = re.search(r'^(.+?),\s*([A-Z]{2})$', title)
    if match:
        return normalize_city(match.group(1)), match.group(2)
    
    # Pattern: "City ST" at end
    match = re.search(r'^(.+?)\s+([A-Z]{2})$', title)
    if match:
        city_part = match.group(1)
        if len(city_part) > 3:
            return normalize_city(city_part), match.group(2)
    
    return normalize_city(title), None


def load_water_providers() -> Dict[str, List[Dict]]:
    """Load water providers from CSV, indexed by state|city."""
    global _water_providers_cache
    
    if _water_providers_cache is not None:
        return _water_providers_cache
    
    if not os.path.exists(CSV_FILE):
        print(f"[CSVWater] CSV not found: {CSV_FILE}")
        _water_providers_cache = {}
        return _water_providers_cache
    
    providers = {}
    
    with open(CSV_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                utility_type_id = row.get('UtilityTypeId', '').strip()
                if utility_type_id != '3':  # 3 = water
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
                
                # Index by state|city
                if state and city:
                    key = f"{state}|{city}".upper()
                    if key not in providers:
                        providers[key] = []
                    providers[key].append(provider)
                
                # Also index by just city (for fallback)
                if city:
                    city_key = f"ANY|{city}".upper()
                    if city_key not in providers:
                        providers[city_key] = []
                    providers[city_key].append(provider)
                    
            except Exception as e:
                continue
    
    print(f"[CSVWater] Loaded {len(providers)} city/state combinations")
    _water_providers_cache = providers
    return providers


def lookup_water_from_csv(city: str, state: str) -> Optional[Dict]:
    """
    Look up water provider from CSV by city and state.
    
    Returns the best match or None.
    """
    if not city:
        return None
    
    providers = load_water_providers()
    city_norm = normalize_city(city).upper()
    
    # Try exact state|city match first
    if state:
        key = f"{state}|{city_norm}"
        if key in providers:
            matches = providers[key]
            if len(matches) == 1:
                return matches[0]
            # Multiple matches - prefer ones with "water" or "township" in name
            for m in matches:
                name_lower = m['name'].lower()
                if 'water' in name_lower or 'township' in name_lower:
                    return m
            return matches[0]
    
    # Try any state with this city
    any_key = f"ANY|{city_norm}"
    if any_key in providers:
        matches = providers[any_key]
        # Filter by state if provided
        if state:
            state_matches = [m for m in matches if m.get('state') == state]
            if state_matches:
                return state_matches[0]
        return matches[0] if matches else None
    
    return None


def get_csv_water_candidates(city: str, state: str) -> List[Dict]:
    """Get all water provider candidates from CSV for a city/state."""
    if not city:
        return []
    
    providers = load_water_providers()
    city_norm = normalize_city(city).upper()
    
    candidates = []
    
    # Exact state|city match
    if state:
        key = f"{state}|{city_norm}"
        if key in providers:
            candidates.extend(providers[key])
    
    # Any state with this city (for comparison)
    any_key = f"ANY|{city_norm}"
    if any_key in providers:
        for p in providers[any_key]:
            if p not in candidates:
                candidates.append(p)
    
    return candidates


# Pre-load on import
load_water_providers()


if __name__ == '__main__':
    # Test
    test_cases = [
        ('East Hanover', 'NJ'),
        ('Austin', 'TX'),
        ('Columbus', 'OH'),
        ('Short Hills', 'NJ'),
    ]
    
    for city, state in test_cases:
        result = lookup_water_from_csv(city, state)
        if result:
            print(f"{city}, {state} -> {result['name']} (ID: {result['id']})")
        else:
            print(f"{city}, {state} -> No match")
