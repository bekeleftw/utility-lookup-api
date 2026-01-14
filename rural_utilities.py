"""
Rural utility lookup - electric cooperatives and county-level defaults.
Improves coverage for rural areas where HIFLD boundary data is inaccurate.
"""

import json
import os
from typing import Optional, Dict, List

# Data files
COOPS_FILE = os.path.join(os.path.dirname(__file__), 'data', 'electric_cooperatives_supplemental.json')
COUNTY_DEFAULTS_FILE = os.path.join(os.path.dirname(__file__), 'data', 'county_utility_defaults.json')

_coops_data = None
_county_defaults = None


def load_coops_data() -> List[Dict]:
    """Load electric cooperative data."""
    global _coops_data
    if _coops_data is None:
        if os.path.exists(COOPS_FILE):
            with open(COOPS_FILE, 'r') as f:
                data = json.load(f)
                _coops_data = data.get('cooperatives', [])
        else:
            _coops_data = []
    return _coops_data


def load_county_defaults() -> Dict:
    """Load county-level utility defaults."""
    global _county_defaults
    if _county_defaults is None:
        if os.path.exists(COUNTY_DEFAULTS_FILE):
            with open(COUNTY_DEFAULTS_FILE, 'r') as f:
                _county_defaults = json.load(f)
        else:
            _county_defaults = {'electric': {}, 'gas': {}}
    return _county_defaults


def lookup_coop_by_zip(zip_code: str, state: str = None) -> Optional[Dict]:
    """
    Look up electric cooperative by ZIP code.
    
    Args:
        zip_code: 5-digit ZIP code
        state: Optional 2-letter state code to filter
    
    Returns:
        Cooperative info dict if found, None otherwise
    """
    if not zip_code:
        return None
    
    coops = load_coops_data()
    
    for coop in coops:
        # Filter by state if provided
        if state and coop.get('state') != state.upper():
            continue
        
        if zip_code in coop.get('zips', []):
            return {
                'name': coop['name'],
                'phone': coop.get('phone'),
                'website': coop.get('website'),
                'state': coop.get('state'),
                'source': 'electric_cooperative_data',
                'confidence': 'high',
                'note': coop.get('note', 'Rural electric cooperative')
            }
    
    return None


def lookup_coop_by_county(county: str, state: str) -> Optional[Dict]:
    """
    Look up electric cooperative by county.
    Less accurate than ZIP but useful as fallback.
    
    Args:
        county: County name
        state: 2-letter state code
    
    Returns:
        Cooperative info dict if found, None otherwise
    """
    if not county or not state:
        return None
    
    coops = load_coops_data()
    county_upper = county.upper().replace(' COUNTY', '').strip()
    
    matches = []
    for coop in coops:
        if coop.get('state') != state.upper():
            continue
        
        coop_counties = [c.upper() for c in coop.get('counties', [])]
        if county_upper in coop_counties:
            matches.append(coop)
    
    # If exactly one match, return it with high confidence
    if len(matches) == 1:
        coop = matches[0]
        return {
            'name': coop['name'],
            'phone': coop.get('phone'),
            'website': coop.get('website'),
            'state': coop.get('state'),
            'source': 'electric_cooperative_data',
            'confidence': 'medium',
            'note': f"Serves {county} County"
        }
    
    # Multiple matches - return largest by membership
    if len(matches) > 1:
        matches.sort(key=lambda x: x.get('members', 0), reverse=True)
        coop = matches[0]
        return {
            'name': coop['name'],
            'phone': coop.get('phone'),
            'website': coop.get('website'),
            'state': coop.get('state'),
            'source': 'electric_cooperative_data',
            'confidence': 'low',
            'note': f"Largest co-op in {county} County (multiple co-ops serve this area)"
        }
    
    return None


def lookup_county_default_electric(county: str, state: str) -> Optional[Dict]:
    """
    Look up default electric utility for a county.
    Used as last resort when HIFLD and co-op lookups fail.
    
    Args:
        county: County name
        state: 2-letter state code
    
    Returns:
        Utility info dict if found, None otherwise
    """
    if not county or not state:
        return None
    
    defaults = load_county_defaults()
    state_data = defaults.get('electric', {}).get(state.upper(), {})
    
    county_key = county.upper().replace(' COUNTY', '').strip()
    
    if county_key in state_data:
        utility = state_data[county_key]
        return {
            'name': utility['name'],
            'phone': utility.get('phone'),
            'website': utility.get('website'),
            'state': state,
            'source': 'county_default',
            'confidence': 'low',
            'note': f"Primary electric provider for {county} County"
        }
    
    return None


def lookup_county_default_gas(county: str, state: str) -> Optional[Dict]:
    """
    Look up default gas utility for a county.
    
    Args:
        county: County name  
        state: 2-letter state code
    
    Returns:
        Utility info dict if found, None otherwise
    """
    if not county or not state:
        return None
    
    defaults = load_county_defaults()
    state_data = defaults.get('gas', {}).get(state.upper(), {})
    
    county_key = county.upper().replace(' COUNTY', '').strip()
    
    if county_key in state_data:
        utility = state_data[county_key]
        return {
            'name': utility['name'],
            'phone': utility.get('phone'),
            'website': utility.get('website'),
            'state': state,
            'source': 'county_default',
            'confidence': 'low',
            'note': f"Primary gas provider for {county} County"
        }
    
    return None


def get_coop_stats() -> Dict:
    """Get statistics about cooperative data."""
    coops = load_coops_data()
    
    states = set()
    total_zips = 0
    total_members = 0
    
    for coop in coops:
        states.add(coop.get('state'))
        total_zips += len(coop.get('zips', []))
        total_members += coop.get('members', 0)
    
    return {
        'total_coops': len(coops),
        'states_covered': len(states),
        'total_zip_codes': total_zips,
        'total_members': total_members,
        'states': sorted(list(states))
    }


if __name__ == "__main__":
    # Test
    print("Co-op Stats:", get_coop_stats())
    
    # Test ZIP lookup
    result = lookup_coop_by_zip("78640", "TX")
    print(f"\nZIP 78640 (Kyle, TX): {result}")
    
    # Test county lookup
    result = lookup_coop_by_county("Hays", "TX")
    print(f"\nHays County, TX: {result}")
