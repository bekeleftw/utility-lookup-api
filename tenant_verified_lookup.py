#!/usr/bin/env python3
"""
Tenant-verified utility lookup module.

Uses data from addresses_with_tenant_verification.csv to provide:
1. Street-level overrides for ambiguous ZIPs
2. Additional utilities not in EIA data

This is a high-confidence data source since tenants uploaded actual utility bills.
"""

import json
import re
import os
from typing import Optional, Dict, List

# Load the tenant-verified lookup data
_LOOKUP_DATA = None
_DATA_FILE = os.path.join(os.path.dirname(__file__), 'tenant_verified_lookup.json')

def _load_data():
    global _LOOKUP_DATA
    if _LOOKUP_DATA is None:
        try:
            with open(_DATA_FILE, 'r') as f:
                _LOOKUP_DATA = json.load(f)
        except FileNotFoundError:
            print(f"Warning: {_DATA_FILE} not found")
            _LOOKUP_DATA = {'street_overrides': {}, 'zip_utilities': {}}
        except Exception as e:
            print(f"Warning: Failed to load tenant verified data: {e}")
            _LOOKUP_DATA = {'street_overrides': {}, 'zip_utilities': {}}
    return _LOOKUP_DATA

def normalize_street(address: str) -> Optional[str]:
    """Extract and normalize street name from address for matching."""
    m = re.match(r'[\d\-]+\s+(.+?),', address)
    if not m:
        return None
    street = m.group(1).lower().strip()
    # Remove unit/apt numbers
    street = re.sub(r'\s+(apt|unit|ste|suite|#|bldg|building)\s*\S*$', '', street, flags=re.I)
    # Normalize common abbreviations
    replacements = [
        (r'\bst\b', 'street'), (r'\bave\b', 'avenue'), (r'\bblvd\b', 'boulevard'),
        (r'\bdr\b', 'drive'), (r'\bln\b', 'lane'), (r'\brd\b', 'road'),
        (r'\bct\b', 'court'), (r'\bpl\b', 'place'), (r'\bcir\b', 'circle'),
        (r'\bpkwy\b', 'parkway'), (r'\bhwy\b', 'highway'), (r'\bter\b', 'terrace'),
    ]
    for pattern, replacement in replacements:
        street = re.sub(pattern, replacement, street)
    return street

def check_tenant_verified(
    address: str,
    zip_code: str,
    utility_type: str = 'electric'
) -> Optional[Dict]:
    """
    Check if we have tenant-verified utility data for this address.
    
    Args:
        address: Full address string
        zip_code: ZIP code (5 digits)
        utility_type: Type of utility ('electric', 'gas', 'water')
    
    Returns:
        Dict with utility info if found, None otherwise.
        {
            'name': 'Utility Name',
            'source': 'tenant_verified',
            'confidence': 'high',
            'match_type': 'street' or 'zip'
        }
    """
    # Currently only have electric data
    if utility_type != 'electric':
        return None
    
    data = _load_data()
    
    if not zip_code:
        return None
    
    # Priority 1: Street-level override (highest confidence)
    if zip_code in data.get('street_overrides', {}):
        street = normalize_street(address)
        if street and street in data['street_overrides'][zip_code]:
            utility_name = data['street_overrides'][zip_code][street]
            return {
                'NAME': utility_name,
                'name': utility_name,
                '_source': 'tenant_verified_street',
                '_confidence': 'high',
                '_match_type': 'street',
                '_tenant_verified': True
            }
    
    # Priority 2: ZIP-level additions (utilities we know serve this ZIP but aren't in EIA)
    # This doesn't override, but can be used to supplement
    # Return None here - let the caller decide whether to use zip_utilities
    
    return None

def get_additional_utilities_for_zip(zip_code: str) -> List[str]:
    """
    Get list of additional utilities that serve this ZIP according to tenant data.
    These are utilities not in our EIA data but verified by tenant uploads.
    
    Args:
        zip_code: 5-digit ZIP code
    
    Returns:
        List of utility names
    """
    data = _load_data()
    return data.get('zip_utilities', {}).get(zip_code, [])

def get_area_context(zip_code: str, address: str = None) -> Dict:
    """
    Get contextual information about utilities seen in this area.
    This is meant to inform AI decision-making, NOT to override results.
    
    Args:
        zip_code: 5-digit ZIP code
        address: Optional full address for street-level context
    
    Returns:
        Dict with area context:
        {
            'has_multiple_utilities': bool,
            'utilities_seen': ['Utility A', 'Utility B'],
            'street_pattern': 'Utility X' or None,
            'context_note': 'Human-readable note for AI'
        }
    """
    data = _load_data()
    result = {
        'has_multiple_utilities': False,
        'utilities_seen': [],
        'street_pattern': None,
        'context_note': None
    }
    
    if not zip_code:
        return result
    
    # Check ZIP-level alternatives (all utilities seen in tenant data)
    zip_alts = data.get('zip_alternatives', {}).get(zip_code, [])
    if zip_alts:
        result['has_multiple_utilities'] = len(zip_alts) > 1
        result['utilities_seen'] = zip_alts
    
    # Also check zip_utilities (missing from EIA)
    zip_utils = data.get('zip_utilities', {}).get(zip_code, [])
    if zip_utils:
        # Merge with alternatives, avoiding duplicates
        for u in zip_utils:
            if u not in result['utilities_seen']:
                result['utilities_seen'].append(u)
        if len(result['utilities_seen']) > 1:
            result['has_multiple_utilities'] = True
    
    # Check street-level pattern
    if address and zip_code in data.get('street_overrides', {}):
        street = normalize_street(address)
        if street and street in data['street_overrides'][zip_code]:
            result['street_pattern'] = data['street_overrides'][zip_code][street]
    
    # Build context note for AI
    if result['has_multiple_utilities'] or result['street_pattern']:
        notes = []
        if result['utilities_seen']:
            notes.append(f"Tenant data shows these utilities have been seen in ZIP {zip_code}: {', '.join(result['utilities_seen'][:5])}")
        if result['street_pattern']:
            notes.append(f"On this specific street, tenants have previously reported: {result['street_pattern']}")
        notes.append("Note: Tenant data is not always accurate (tenants sometimes upload wrong utility proof).")
        result['context_note'] = ' '.join(notes)
    
    return result

def has_street_override(zip_code: str) -> bool:
    """Check if we have any street-level overrides for this ZIP."""
    data = _load_data()
    return zip_code in data.get('street_overrides', {})

# Utility name normalization for matching
UTILITY_ALIASES = {
    'sce': ['southern california edison', 'socal edison'],
    'sdge': ['san diego gas & electric', 'san diego gas and electric', 'sdg&e'],
    'pge': ['pacific gas & electric', 'pacific gas and electric', 'pg&e'],
    'pse': ['puget sound energy'],
    'aps': ['arizona public service', 'arizona public service (aps)'],
    'srp': ['salt river project', 'salt river project (srp)'],
    'ouc': ['orlando utilities commission', 'orlando utilites commission'],
    'jea': ['jea - fl'],
    'teco': ['teco energy', 'tampa electric', 'tampa electric co'],
    'fpl': ['florida power and light', 'florida power & light'],
    'duke': ['duke energy', 'duke energy carolinas', 'duke energy progress', 'duke energy florida'],
    'georgia power': ['georgia power company', 'georgia power co'],
    'dominion': ['dominion energy', 'dominion virginia power'],
    'xcel': ['xcel energy'],
    'comed': ['commonwealth edison', 'commonwealth edison (comed)'],
    'ameren': ['ameren il', 'ameren mo'],
}

def normalize_utility_name(name: str) -> str:
    """Normalize utility name for comparison."""
    if not name:
        return ""
    name = name.lower().strip()
    # Remove state suffixes
    name = re.sub(r'\s*[-–]\s*[a-z]{2}\s*$', '', name)
    name = re.sub(r'\s*\([a-z]{2}\)\s*$', '', name)
    return name

def utilities_match(name1: str, name2: str) -> bool:
    """Check if two utility names refer to the same utility."""
    n1 = normalize_utility_name(name1)
    n2 = normalize_utility_name(name2)
    
    if not n1 or not n2:
        return False
    
    # Direct match
    if n1 == n2 or n1 in n2 or n2 in n1:
        return True
    
    # Check aliases
    for canonical, aliases in UTILITY_ALIASES.items():
        all_names = [canonical] + aliases
        n1_match = any(a in n1 or n1 in a for a in all_names)
        n2_match = any(a in n2 or n2 in a for a in all_names)
        if n1_match and n2_match:
            return True
    
    # First significant word match
    words1 = [w for w in n1.split() if len(w) > 3]
    words2 = [w for w in n2.split() if len(w) > 3]
    if words1 and words2 and words1[0] == words2[0]:
        return True
    
    return False
