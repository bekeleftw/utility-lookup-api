"""
Municipal utility lookup - city-owned utilities that aren't in federal databases.
"""

import json
import os
from typing import Optional, Dict, List

MUNICIPAL_FILE = os.path.join(os.path.dirname(__file__), 'data', 'municipal_utilities.json')
LONG_ISLAND_WATER_FILE = os.path.join(os.path.dirname(__file__), 'data', 'long_island_water_districts.json')

_municipal_data = None
_long_island_water_data = None


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


def lookup_municipal_electric(state: str, city: str = None, zip_code: str = None, county: str = None) -> Optional[Dict]:
    """
    Check if address is served by a municipal electric utility.
    
    Args:
        state: 2-letter state code
        city: City name
        zip_code: 5-digit ZIP code
        county: County name (for fallback)
    
    Returns:
        Municipal utility dict if found, None otherwise
    """
    data = load_municipal_data()
    state_upper = state.upper() if state else ''
    state_data = data.get('electric', {}).get(state_upper, {})
    
    # Check by ZIP code first (most accurate)
    if zip_code and state_data:
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
    if city and state_data:
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
    
    # COUNTY FALLBACK: If no city match, try county-level data
    county_data = data.get('county_electric', {}).get(state_upper, {})
    if county and county_data:
        county_upper = county.upper()
        # Try exact match first
        for county_name, utility in county_data.items():
            if county_name.upper() == county_upper:
                return {
                    'name': utility['name'],
                    'phone': utility.get('phone'),
                    'website': utility.get('website'),
                    'county': county_name,
                    'source': 'county_electric_fallback',
                    'confidence': 'medium',
                    'note': utility.get('note', f"Electric utility serving {county_name} County")
                }
        # Try partial match (e.g., "Jefferson County" matches "Jefferson")
        for county_name, utility in county_data.items():
            if county_name.upper() in county_upper or county_upper in county_name.upper():
                return {
                    'name': utility['name'],
                    'phone': utility.get('phone'),
                    'website': utility.get('website'),
                    'county': county_name,
                    'source': 'county_electric_fallback',
                    'confidence': 'low',
                    'note': utility.get('note', f"Electric utility serving {county_name} County")
                }
    
    return None


def lookup_municipal_gas(state: str, city: str = None, zip_code: str = None, county: str = None) -> Optional[Dict]:
    """Check if city has municipal/regional gas utility (Texas Gas Service, Atmos, CenterPoint, etc.)."""
    data = load_municipal_data()
    state_upper = state.upper() if state else ''
    
    # SPECIAL CASE: NYC boroughs - check county FIRST since city is always "New York"
    # but gas providers differ by borough (county)
    if state_upper == 'NY' and county:
        nyc_counties = ['KINGS', 'QUEENS', 'RICHMOND', 'BRONX', 'NEW YORK', 'NASSAU', 'SUFFOLK']
        county_upper = county.upper()
        if county_upper in nyc_counties:
            county_data = data.get('county_gas', {}).get('NY', {})
            for county_name, utility in county_data.items():
                if county_name.upper() == county_upper:
                    return {
                        'name': utility['name'],
                        'phone': utility.get('phone'),
                        'website': utility.get('website'),
                        'county': county_name,
                        'source': 'county_gas_nyc',
                        'confidence': 'verified',
                        'note': f"Gas utility serving {county_name} County, NY"
                    }
    
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
    
    # COUNTY FALLBACK: If no city match, try county-level gas data
    county_data = data.get('county_gas', {}).get(state_upper, {})
    if county and county_data:
        county_upper = county.upper()
        # Try exact match first
        for county_name, utility in county_data.items():
            if county_name.upper() == county_upper:
                return {
                    'name': utility['name'],
                    'phone': utility.get('phone'),
                    'website': utility.get('website'),
                    'county': county_name,
                    'source': 'county_gas_fallback',
                    'confidence': 'medium',
                    'note': utility.get('note', f"Gas utility serving {county_name} County")
                }
        # Try partial match (e.g., "Jefferson County" matches "Jefferson")
        for county_name, utility in county_data.items():
            if county_name.upper() in county_upper or county_upper in county_name.upper():
                return {
                    'name': utility['name'],
                    'phone': utility.get('phone'),
                    'website': utility.get('website'),
                    'county': county_name,
                    'source': 'county_gas_fallback',
                    'confidence': 'low',
                    'note': utility.get('note', f"Gas utility serving {county_name} County")
                }
    
    return None


def load_long_island_water_data() -> dict:
    """Load Long Island water district data."""
    global _long_island_water_data
    if _long_island_water_data is None:
        if os.path.exists(LONG_ISLAND_WATER_FILE):
            with open(LONG_ISLAND_WATER_FILE, 'r') as f:
                _long_island_water_data = json.load(f)
        else:
            _long_island_water_data = {}
    return _long_island_water_data


def lookup_long_island_water(zip_code: str, county: str = None) -> Optional[Dict]:
    """Look up water district for Long Island (Nassau/Suffolk counties) by ZIP code."""
    if not zip_code or not zip_code.startswith('11'):
        return None
    
    data = load_long_island_water_data()
    
    # Determine which county based on ZIP or provided county
    county_upper = county.upper() if county else ''
    
    # Check Nassau County
    nassau_data = data.get('nassau_county', {})
    if zip_code in nassau_data:
        district = nassau_data[zip_code]
        return {
            'name': district['name'],
            'phone': district.get('phone'),
            'website': district.get('website'),
            'source': 'long_island_water_zip',
            'confidence': 'verified',
            'note': f"Water district serving ZIP {zip_code} in Nassau County"
        }
    
    # Check Suffolk County
    suffolk_data = data.get('suffolk_county', {})
    if zip_code in suffolk_data:
        district = suffolk_data[zip_code]
        return {
            'name': district['name'],
            'phone': district.get('phone'),
            'website': district.get('website'),
            'source': 'long_island_water_zip',
            'confidence': 'verified',
            'note': f"Water district serving ZIP {zip_code} in Suffolk County"
        }
    
    # Suffolk County default (SCWA serves most of Suffolk)
    if county_upper == 'SUFFOLK' or (zip_code.startswith('117') and int(zip_code) >= 11701):
        default = suffolk_data.get('_default', {})
        if default:
            return {
                'name': default['name'],
                'phone': default.get('phone'),
                'website': default.get('website'),
                'source': 'long_island_water_default',
                'confidence': 'high',
                'note': 'Suffolk County Water Authority serves most of Suffolk County'
            }
    
    return None


def lookup_municipal_water(state: str, city: str = None, zip_code: str = None, county: str = None) -> Optional[Dict]:
    """Check if city has municipal water utility (SAWS, Denver Water, SFPUC, etc.)."""
    data = load_municipal_data()
    state_upper = state.upper() if state else ''
    
    # SPECIAL CASE: Long Island (Nassau/Suffolk) - check ZIP-based water districts first
    if state_upper == 'NY' and zip_code and zip_code.startswith('11'):
        li_result = lookup_long_island_water(zip_code, county)
        if li_result:
            return li_result
    
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
