#!/usr/bin/env python3
"""
Provider ID Matcher - matches provider names to IDs from utility_providers_IDs.csv
Uses OpenAI-generated mappings for fuzzy matching and deduplication.
"""

import csv
import json
import os
import re
from typing import Optional, Dict, Tuple

# Cache for loaded data
_providers_cache = None
_mappings_cache = None
_simple_lookup_cache = None

MAPPINGS_FILE = os.path.join(os.path.dirname(__file__), 'data', 'provider_name_mappings.json')
SIMPLE_LOOKUP_FILE = os.path.join(os.path.dirname(__file__), 'data', 'provider_simple_lookup.json')

# UtilityTypeId mapping
UTILITY_TYPE_MAP = {
    2: 'electric',
    3: 'water',
    4: 'gas',
    5: 'trash',
    6: 'sewer'
}

# Reverse mapping
UTILITY_TYPE_REVERSE = {v: k for k, v in UTILITY_TYPE_MAP.items()}


def normalize_name(name: str) -> str:
    """Normalize provider name for matching."""
    if not name:
        return ''
    # Lowercase
    name = name.lower()
    # Remove common suffixes
    name = re.sub(r'\s*-\s*[a-z]{2}$', '', name)  # State suffix like "- TX"
    name = re.sub(r'\s*\([a-z]{2}\)$', '', name)  # State in parens like "(TX)"
    name = re.sub(r'\s+(inc|llc|corp|co|company|corporation|l\.?l\.?c\.?)\.?$', '', name, flags=re.IGNORECASE)
    # Remove special characters except spaces
    name = re.sub(r'[^a-z0-9\s]', '', name)
    # Normalize whitespace
    name = ' '.join(name.split())
    return name


def load_mappings() -> Dict[str, Dict]:
    """Load OpenAI-generated name mappings."""
    global _mappings_cache
    
    if _mappings_cache is not None:
        return _mappings_cache
    
    if os.path.exists(MAPPINGS_FILE):
        with open(MAPPINGS_FILE, 'r') as f:
            _mappings_cache = json.load(f)
        print(f"[ProviderMatcher] Loaded {len(_mappings_cache)} OpenAI mappings")
    else:
        _mappings_cache = {}
    
    return _mappings_cache


def load_simple_lookup() -> Dict[str, Dict]:
    """Load simple normalized name -> ID lookup."""
    global _simple_lookup_cache
    
    if _simple_lookup_cache is not None:
        return _simple_lookup_cache
    
    if os.path.exists(SIMPLE_LOOKUP_FILE):
        with open(SIMPLE_LOOKUP_FILE, 'r') as f:
            _simple_lookup_cache = json.load(f)
        print(f"[ProviderMatcher] Loaded {len(_simple_lookup_cache)} simple lookups")
    else:
        _simple_lookup_cache = {}
    
    return _simple_lookup_cache


def load_providers() -> Dict[str, Dict]:
    """Load providers from CSV file."""
    global _providers_cache
    
    if _providers_cache is not None:
        return _providers_cache
    
    csv_path = os.path.join(os.path.dirname(__file__), 'utility_providers_IDs.csv')
    
    if not os.path.exists(csv_path):
        print(f"[ProviderMatcher] CSV not found: {csv_path}")
        _providers_cache = {}
        return _providers_cache
    
    providers = {}
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                provider_id = row.get('ID', '').strip()
                utility_type_id = int(row.get('UtilityTypeId', 0))
                title = row.get('Title', '').strip()
                
                if not provider_id or not title:
                    continue
                
                utility_type = UTILITY_TYPE_MAP.get(utility_type_id, 'unknown')
                normalized = normalize_name(title)
                
                # Key by normalized name + utility type for exact matching
                key = f"{normalized}|{utility_type}"
                
                providers[key] = {
                    'id': provider_id,
                    'title': title,
                    'utility_type': utility_type,
                    'utility_type_id': utility_type_id,
                    'url': row.get('URL', ''),
                    'phone': row.get('Phone', ''),
                    'normalized': normalized
                }
            except Exception as e:
                continue
    
    print(f"[ProviderMatcher] Loaded {len(providers)} providers")
    _providers_cache = providers
    return providers


def match_provider(name: str, utility_type: str) -> Optional[Dict]:
    """
    Match a provider name to an ID using multiple strategies:
    1. OpenAI-generated mappings (best for fuzzy matching like "Oncor" -> "Oncor Electric-TX")
    2. Simple normalized lookup
    3. CSV-based exact match
    4. Partial string matching
    
    Args:
        name: Provider name from lookup
        utility_type: Type of utility (electric, gas, water, internet)
        
    Returns:
        Dict with provider info including 'id', or None if no match
    """
    if not name:
        return None
    
    normalized = normalize_name(name)
    
    # Strategy 1: Check OpenAI mappings first (best for deduped names)
    mappings = load_mappings()
    if normalized in mappings:
        mapping = mappings[normalized]
        return {
            'id': mapping['id'],
            'title': mapping.get('canonical', mapping.get('original', name)),
            'matched_via': 'openai_mapping'
        }
    
    # Strategy 2: Simple lookup (normalized name -> ID)
    simple = load_simple_lookup()
    if normalized in simple:
        entry = simple[normalized]
        return {
            'id': entry['id'] if isinstance(entry, dict) else entry,
            'title': entry.get('title', name) if isinstance(entry, dict) else name,
            'matched_via': 'simple_lookup'
        }
    
    # Strategy 3: CSV-based exact match with utility type
    providers = load_providers()
    key = f"{normalized}|{utility_type}"
    if key in providers:
        providers[key]['matched_via'] = 'csv_exact'
        return providers[key]
    
    # Try without utility type constraint
    for pkey, pdata in providers.items():
        if pdata['normalized'] == normalized:
            pdata['matched_via'] = 'csv_any_type'
            return pdata
    
    # Strategy 4: Partial matching - provider name contains or is contained
    best_match = None
    best_score = 0
    
    for pkey, pdata in providers.items():
        pnorm = pdata['normalized']
        
        # Skip if utility types don't match
        if pdata['utility_type'] != utility_type:
            continue
        
        # Check if one contains the other
        if normalized in pnorm or pnorm in normalized:
            score = min(len(normalized), len(pnorm)) / max(len(normalized), len(pnorm))
            if score > best_score:
                best_score = score
                best_match = pdata
    
    if best_match and best_score > 0.5:  # Lowered threshold for partial matches
        best_match['matched_via'] = 'partial'
        return best_match
    
    return None


def get_provider_id(name: str, utility_type: str) -> Optional[str]:
    """
    Get just the provider ID for a name.
    
    Args:
        name: Provider name from lookup
        utility_type: Type of utility
        
    Returns:
        Provider ID string or None
    """
    match = match_provider(name, utility_type)
    return match['id'] if match else None


# Pre-load on import
load_providers()


if __name__ == '__main__':
    # Test matching
    test_cases = [
        ('Austin Energy', 'electric'),
        ('Texas Gas Service', 'gas'),
        ('City of Austin Water', 'water'),
        ('AT&T', 'internet'),
        ('Oncor Electric', 'electric'),
    ]
    
    for name, utype in test_cases:
        result = match_provider(name, utype)
        if result:
            print(f"{name} ({utype}) -> ID: {result['id']}, Title: {result['title']}")
        else:
            print(f"{name} ({utype}) -> No match")
