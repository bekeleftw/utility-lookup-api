"""
Municipal utility lookup - city-owned utilities that aren't in federal databases.
"""

import json
import os
from typing import Optional, Dict, List

MUNICIPAL_FILE = os.path.join(os.path.dirname(__file__), 'data', 'municipal_utilities.json')

_municipal_data = None


def load_municipal_data() -> dict:
    """Load municipal utility data."""
    global _municipal_data
    if _municipal_data is None:
        if os.path.exists(MUNICIPAL_FILE):
            with open(MUNICIPAL_FILE, 'r') as f:
                _municipal_data = json.load(f)
        else:
            _municipal_data = {'electric': {}, 'gas': {}, 'water': {}}
    return _municipal_data


def lookup_municipal_electric(state: str, city: str = None, zip_code: str = None) -> Optional[Dict]:
    """
    Check if address is served by a municipal electric utility.
    
    Args:
        state: 2-letter state code
        city: City name
        zip_code: 5-digit ZIP code
    
    Returns:
        Municipal utility dict if found, None otherwise
    """
    data = load_municipal_data()
    state_data = data.get('electric', {}).get(state.upper() if state else '', {})
    
    if not state_data:
        return None
    
    # Check by ZIP code first (most accurate)
    if zip_code:
        for city_name, utility in state_data.items():
            if zip_code in utility.get('zip_codes', []):
                return {
                    'name': utility['name'],
                    'phone': utility.get('phone'),
                    'website': utility.get('website'),
                    'city': city_name,
                    'source': 'municipal_utility',
                    'confidence': 'high',
                    'note': utility.get('note', f"Municipal utility serving {city_name}")
                }
    
    # Fall back to city name match
    if city:
        city_upper = city.upper()
        for city_name, utility in state_data.items():
            if city_name.upper() == city_upper or city_name.upper() in city_upper:
                return {
                    'name': utility['name'],
                    'phone': utility.get('phone'),
                    'website': utility.get('website'),
                    'city': city_name,
                    'source': 'municipal_utility',
                    'confidence': 'medium',
                    'note': utility.get('note', f"Municipal utility serving {city_name}")
                }
    
    return None


def lookup_municipal_gas(state: str, city: str = None, zip_code: str = None) -> Optional[Dict]:
    """Check if city has municipal gas utility (CPS Energy, MLGW, etc.)."""
    data = load_municipal_data()
    
    # Check electric utilities that also provide gas
    state_data = data.get('electric', {}).get(state.upper() if state else '', {})
    
    for city_name, utility in state_data.items():
        services = utility.get('services', ['electric'])
        if 'gas' not in services:
            continue
        
        # Check ZIP
        if zip_code and zip_code in utility.get('zip_codes', []):
            return {
                'name': utility['name'],
                'phone': utility.get('phone'),
                'website': utility.get('website'),
                'city': city_name,
                'source': 'municipal_utility',
                'confidence': 'high',
                'note': f"Municipal utility providing gas service"
            }
        
        # Check city name
        if city and city_name.upper() in city.upper():
            return {
                'name': utility['name'],
                'phone': utility.get('phone'),
                'website': utility.get('website'),
                'city': city_name,
                'source': 'municipal_utility',
                'confidence': 'medium'
            }
    
    return None


def lookup_municipal_water(state: str, city: str = None, zip_code: str = None) -> Optional[Dict]:
    """Check if city has municipal water utility (LADWP, MLGW, etc.)."""
    data = load_municipal_data()
    
    # Check electric utilities that also provide water
    state_data = data.get('electric', {}).get(state.upper() if state else '', {})
    
    for city_name, utility in state_data.items():
        services = utility.get('services', ['electric'])
        if 'water' not in services:
            continue
        
        # Check ZIP
        if zip_code and zip_code in utility.get('zip_codes', []):
            return {
                'name': utility['name'],
                'phone': utility.get('phone'),
                'website': utility.get('website'),
                'city': city_name,
                'source': 'municipal_utility',
                'confidence': 'high'
            }
        
        # Check city name
        if city and city_name.upper() in city.upper():
            return {
                'name': utility['name'],
                'phone': utility.get('phone'),
                'website': utility.get('website'),
                'city': city_name,
                'source': 'municipal_utility',
                'confidence': 'medium'
            }
    
    return None


def get_all_municipal_utilities(state: str = None) -> Dict:
    """Get all municipal utilities, optionally filtered by state."""
    data = load_municipal_data()
    
    if state:
        return {
            'electric': data.get('electric', {}).get(state.upper(), {}),
        }
    
    return data.get('electric', {})


def get_municipal_stats() -> Dict:
    """Get statistics about municipal utilities in the database."""
    data = load_municipal_data()
    electric = data.get('electric', {})
    
    total_utilities = 0
    total_zips = 0
    states_covered = len(electric)
    
    for state, cities in electric.items():
        total_utilities += len(cities)
        for city, utility in cities.items():
            total_zips += len(utility.get('zip_codes', []))
    
    return {
        'total_utilities': total_utilities,
        'total_states': states_covered,
        'total_zip_codes': total_zips,
        'states': list(electric.keys())
    }
