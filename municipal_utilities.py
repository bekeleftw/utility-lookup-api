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
    """Check if city has municipal/regional gas utility (Texas Gas Service, Atmos, CenterPoint, etc.)."""
    data = load_municipal_data()
    state_upper = state.upper() if state else ''
    
    # FIRST: Check dedicated gas section (Texas Gas Service, Atmos, CenterPoint, etc.)
    gas_data = data.get('gas', {}).get(state_upper, {})
    
    for city_name, utility in gas_data.items():
        # Check ZIP first (most accurate)
        if zip_code and zip_code in utility.get('zip_codes', []):
            return {
                'name': utility['name'],
                'phone': utility.get('phone'),
                'website': utility.get('website'),
                'city': city_name,
                'source': 'municipal_gas_data',
                'confidence': 'high',
                'note': utility.get('note', f"Gas utility serving {city_name}")
            }
        
        # Check city name
        if city and city_name.upper() in city.upper():
            return {
                'name': utility['name'],
                'phone': utility.get('phone'),
                'website': utility.get('website'),
                'city': city_name,
                'source': 'municipal_gas_data',
                'confidence': 'medium',
                'note': utility.get('note', f"Gas utility serving {city_name}")
            }
    
    # SECOND: Check electric utilities that also provide gas (CPS Energy, Colorado Springs, etc.)
    electric_data = data.get('electric', {}).get(state_upper, {})
    
    for city_name, utility in electric_data.items():
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
    """Check if city has municipal water utility (SAWS, Denver Water, SFPUC, etc.)."""
    data = load_municipal_data()
    state_upper = state.upper() if state else ''
    
    # FIRST: Check dedicated water section (standalone water utilities)
    water_data = data.get('water', {}).get(state_upper, {})
    
    for city_name, utility in water_data.items():
        # Check ZIP first (most accurate)
        if zip_code and zip_code in utility.get('zip_codes', []):
            return {
                'name': utility['name'],
                'phone': utility.get('phone'),
                'website': utility.get('website'),
                'city': city_name,
                'source': 'municipal_water_data',
                'confidence': 'high',
                'note': utility.get('note', f"Municipal water utility serving {city_name}")
            }
        
        # Check city name
        if city and city_name.upper() in city.upper():
            return {
                'name': utility['name'],
                'phone': utility.get('phone'),
                'website': utility.get('website'),
                'city': city_name,
                'source': 'municipal_water_data',
                'confidence': 'medium',
                'note': utility.get('note', f"Municipal water utility serving {city_name}")
            }
    
    # SECOND: Check electric utilities that also provide water (Austin Energy/Austin Water, OUC, etc.)
    electric_data = data.get('electric', {}).get(state_upper, {})
    
    for city_name, utility in electric_data.items():
        services = utility.get('services', ['electric'])
        if 'water' not in services:
            continue
        
        # Check ZIP
        if zip_code and zip_code in utility.get('zip_codes', []):
            # Use separate water provider info if available (e.g., Austin Water vs Austin Energy)
            water_name = utility.get('water_provider', utility['name'])
            water_phone = utility.get('water_phone', utility.get('phone'))
            water_website = utility.get('water_website', utility.get('website'))
            
            return {
                'name': water_name,
                'phone': water_phone,
                'website': water_website,
                'city': city_name,
                'source': 'municipal_utility',
                'confidence': 'high'
            }
        
        # Check city name
        if city and city_name.upper() in city.upper():
            water_name = utility.get('water_provider', utility['name'])
            water_phone = utility.get('water_phone', utility.get('phone'))
            water_website = utility.get('water_website', utility.get('website'))
            
            return {
                'name': water_name,
                'phone': water_phone,
                'website': water_website,
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
