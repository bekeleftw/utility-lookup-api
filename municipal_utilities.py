"""
Municipal utility lookup - city-owned utilities that aren't in federal databases.
"""

import json
import os
from typing import Optional, Dict, List

MUNICIPAL_FILE = os.path.join(os.path.dirname(__file__), 'data', 'municipal_utilities.json')
LONG_ISLAND_WATER_FILE = os.path.join(os.path.dirname(__file__), 'data', 'long_island_water_districts.json')
SOCAL_WATER_FILE = os.path.join(os.path.dirname(__file__), 'data', 'socal_water_districts.json')
DFW_WATER_FILE = os.path.join(os.path.dirname(__file__), 'data', 'dfw_water_districts.json')
HOUSTON_WATER_FILE = os.path.join(os.path.dirname(__file__), 'data', 'houston_water_districts.json')
PHILLY_WATER_FILE = os.path.join(os.path.dirname(__file__), 'data', 'philly_water_districts.json')
DC_WATER_FILE = os.path.join(os.path.dirname(__file__), 'data', 'dc_water_districts.json')
ATLANTA_WATER_FILE = os.path.join(os.path.dirname(__file__), 'data', 'atlanta_water_districts.json')
FLORIDA_WATER_FILE = os.path.join(os.path.dirname(__file__), 'data', 'florida_water_districts.json')
REMAINING_STATES_WATER_FILE = os.path.join(os.path.dirname(__file__), 'data', 'remaining_states_water.json')
REMAINING_STATES_ELECTRIC_FILE = os.path.join(os.path.dirname(__file__), 'data', 'remaining_states_electric.json')
REMAINING_STATES_GAS_FILE = os.path.join(os.path.dirname(__file__), 'data', 'remaining_states_gas.json')

_municipal_data = None
_long_island_water_data = None
_socal_water_data = None
_dfw_water_data = None
_houston_water_data = None
_philly_water_data = None
_dc_water_data = None
_atlanta_water_data = None
_florida_water_data = None
_remaining_states_water_data = None
_remaining_states_electric_data = None
_remaining_states_gas_data = None


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
    """Check if city has municipal electric utility.
    
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
    
    # Check remaining states electric co-ops/municipals first (tenant-verified)
    if zip_code:
        remaining_result = lookup_remaining_states_electric(zip_code, state_upper)
        if remaining_result:
            return remaining_result
    
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


def load_socal_water_data() -> dict:
    """Load Southern California water district data."""
    global _socal_water_data
    if _socal_water_data is None:
        if os.path.exists(SOCAL_WATER_FILE):
            with open(SOCAL_WATER_FILE, 'r') as f:
                _socal_water_data = json.load(f)
        else:
            _socal_water_data = {}
    return _socal_water_data


def lookup_socal_water(zip_code: str) -> Optional[Dict]:
    """Look up water district for Southern California by ZIP code."""
    if not zip_code:
        return None
    
    data = load_socal_water_data()
    zip_mappings = data.get('zip_mappings', {})
    
    if zip_code in zip_mappings:
        district = zip_mappings[zip_code]
        return {
            'name': district['name'],
            'phone': district.get('phone'),
            'website': district.get('website'),
            'source': 'socal_water_zip',
            'confidence': 'verified',
            'note': f"Water district serving ZIP {zip_code} (tenant-verified)"
        }
    
    return None


def load_dfw_water_data() -> dict:
    """Load Dallas-Fort Worth water district data."""
    global _dfw_water_data
    if _dfw_water_data is None:
        if os.path.exists(DFW_WATER_FILE):
            with open(DFW_WATER_FILE, 'r') as f:
                _dfw_water_data = json.load(f)
        else:
            _dfw_water_data = {}
    return _dfw_water_data


def lookup_dfw_water(zip_code: str) -> Optional[Dict]:
    """Look up water utility for Dallas-Fort Worth by ZIP code."""
    if not zip_code:
        return None
    
    data = load_dfw_water_data()
    zip_mappings = data.get('zip_mappings', {})
    
    if zip_code in zip_mappings:
        district = zip_mappings[zip_code]
        return {
            'name': district['name'],
            'phone': district.get('phone'),
            'website': district.get('website'),
            'source': 'dfw_water_zip',
            'confidence': 'verified',
            'note': f"Water utility serving ZIP {zip_code} (tenant-verified)"
        }
    
    return None


def load_houston_water_data() -> dict:
    """Load Houston metro water district data."""
    global _houston_water_data
    if _houston_water_data is None:
        if os.path.exists(HOUSTON_WATER_FILE):
            with open(HOUSTON_WATER_FILE, 'r') as f:
                _houston_water_data = json.load(f)
        else:
            _houston_water_data = {}
    return _houston_water_data


def lookup_houston_water(zip_code: str) -> Optional[Dict]:
    """Look up water utility for Houston metro by ZIP code."""
    if not zip_code:
        return None
    
    data = load_houston_water_data()
    zip_mappings = data.get('zip_mappings', {})
    
    if zip_code in zip_mappings:
        district = zip_mappings[zip_code]
        return {
            'name': district['name'],
            'phone': district.get('phone'),
            'website': district.get('website'),
            'source': 'houston_water_zip',
            'confidence': 'verified',
            'note': f"Water utility serving ZIP {zip_code} (tenant-verified)"
        }
    
    return None


def load_philly_water_data() -> dict:
    """Load Philadelphia metro water district data."""
    global _philly_water_data
    if _philly_water_data is None:
        if os.path.exists(PHILLY_WATER_FILE):
            with open(PHILLY_WATER_FILE, 'r') as f:
                _philly_water_data = json.load(f)
        else:
            _philly_water_data = {}
    return _philly_water_data


def lookup_philly_water(zip_code: str) -> Optional[Dict]:
    """Look up water utility for Philadelphia metro by ZIP code."""
    if not zip_code:
        return None
    
    data = load_philly_water_data()
    zip_mappings = data.get('zip_mappings', {})
    
    if zip_code in zip_mappings:
        district = zip_mappings[zip_code]
        return {
            'name': district['name'],
            'phone': district.get('phone'),
            'website': district.get('website'),
            'source': 'philly_water_zip',
            'confidence': 'verified',
            'note': f"Water utility serving ZIP {zip_code} (tenant-verified)"
        }
    
    return None


def load_dc_water_data() -> dict:
    """Load Washington DC metro water district data."""
    global _dc_water_data
    if _dc_water_data is None:
        if os.path.exists(DC_WATER_FILE):
            with open(DC_WATER_FILE, 'r') as f:
                _dc_water_data = json.load(f)
        else:
            _dc_water_data = {}
    return _dc_water_data


def lookup_dc_water(zip_code: str) -> Optional[Dict]:
    """Look up water utility for DC metro by ZIP code."""
    if not zip_code:
        return None
    
    data = load_dc_water_data()
    zip_mappings = data.get('zip_mappings', {})
    
    if zip_code in zip_mappings:
        district = zip_mappings[zip_code]
        return {
            'name': district['name'],
            'phone': district.get('phone'),
            'website': district.get('website'),
            'source': 'dc_water_zip',
            'confidence': 'verified',
            'note': f"Water utility serving ZIP {zip_code} (tenant-verified)"
        }
    
    return None


def load_atlanta_water_data() -> dict:
    """Load Atlanta metro water district data."""
    global _atlanta_water_data
    if _atlanta_water_data is None:
        if os.path.exists(ATLANTA_WATER_FILE):
            with open(ATLANTA_WATER_FILE, 'r') as f:
                _atlanta_water_data = json.load(f)
        else:
            _atlanta_water_data = {}
    return _atlanta_water_data


def lookup_atlanta_water(zip_code: str) -> Optional[Dict]:
    """Look up water utility for Atlanta metro by ZIP code."""
    if not zip_code:
        return None
    
    data = load_atlanta_water_data()
    zip_mappings = data.get('zip_mappings', {})
    
    if zip_code in zip_mappings:
        district = zip_mappings[zip_code]
        return {
            'name': district['name'],
            'phone': district.get('phone'),
            'website': district.get('website'),
            'source': 'atlanta_water_zip',
            'confidence': 'verified',
            'note': f"Water utility serving ZIP {zip_code} (tenant-verified)"
        }
    
    return None


def load_florida_water_data() -> dict:
    """Load Florida water district data."""
    global _florida_water_data
    if _florida_water_data is None:
        if os.path.exists(FLORIDA_WATER_FILE):
            with open(FLORIDA_WATER_FILE, 'r') as f:
                _florida_water_data = json.load(f)
        else:
            _florida_water_data = {}
    return _florida_water_data


def lookup_florida_water(zip_code: str) -> Optional[Dict]:
    """Look up water utility for Florida by ZIP code."""
    if not zip_code:
        return None
    
    data = load_florida_water_data()
    zip_mappings = data.get('zip_mappings', {})
    
    if zip_code in zip_mappings:
        district = zip_mappings[zip_code]
        return {
            'name': district['name'],
            'phone': district.get('phone'),
            'website': district.get('website'),
            'source': 'florida_water_zip',
            'confidence': 'verified',
            'note': f"Water utility serving ZIP {zip_code} (tenant-verified)"
        }
    
    return None


def load_remaining_states_water_data() -> dict:
    """Load remaining states water district data."""
    global _remaining_states_water_data
    if _remaining_states_water_data is None:
        if os.path.exists(REMAINING_STATES_WATER_FILE):
            with open(REMAINING_STATES_WATER_FILE, 'r') as f:
                _remaining_states_water_data = json.load(f)
        else:
            _remaining_states_water_data = {}
    return _remaining_states_water_data


def lookup_remaining_states_water(zip_code: str, state: str) -> Optional[Dict]:
    """Look up water utility for remaining states by ZIP code."""
    if not zip_code or not state:
        return None
    
    data = load_remaining_states_water_data()
    states_data = data.get('states', {})
    
    state_upper = state.upper()
    if state_upper in states_data:
        zip_mappings = states_data[state_upper]
        if zip_code in zip_mappings:
            district = zip_mappings[zip_code]
            confidence_level = district.get('confidence_level', 'medium')
            dominance_pct = district.get('dominance_pct', 50)
            sample_count = district.get('sample_count', 1)
            is_split = district.get('possible_split_territory', False)
            
            # Adjust confidence score based on split territory flag
            if confidence_level == 'high':
                conf_score = 70
            elif is_split:
                conf_score = 50  # Lower score for possible split territories
            else:
                conf_score = 55
            
            note = f"Water utility serving ZIP {zip_code} ({dominance_pct}% of {sample_count} verified addresses)"
            if is_split:
                note += " - POSSIBLE SPLIT TERRITORY"
            
            return {
                'name': district['name'],
                'phone': district.get('phone'),
                'website': district.get('website'),
                'source': 'tenant_verified_zip',
                'confidence': confidence_level,
                'confidence_score': conf_score,
                'dominance_pct': dominance_pct,
                'sample_count': sample_count,
                'possible_split_territory': is_split,
                'note': note
            }
    
    return None


def load_remaining_states_electric_data() -> dict:
    """Load remaining states electric co-op/municipal data."""
    global _remaining_states_electric_data
    if _remaining_states_electric_data is None:
        if os.path.exists(REMAINING_STATES_ELECTRIC_FILE):
            with open(REMAINING_STATES_ELECTRIC_FILE, 'r') as f:
                _remaining_states_electric_data = json.load(f)
        else:
            _remaining_states_electric_data = {}
    return _remaining_states_electric_data


def lookup_remaining_states_electric(zip_code: str, state: str) -> Optional[Dict]:
    """Look up electric co-op/municipal for remaining states by ZIP code."""
    if not zip_code or not state:
        return None
    
    data = load_remaining_states_electric_data()
    states_data = data.get('states', {})
    
    state_upper = state.upper()
    if state_upper in states_data:
        zip_mappings = states_data[state_upper]
        if zip_code in zip_mappings:
            utility = zip_mappings[zip_code]
            confidence_level = utility.get('confidence_level', 'medium')
            dominance_pct = utility.get('dominance_pct', 60)
            sample_count = utility.get('sample_count', 1)
            is_split = utility.get('possible_split_territory', False)
            
            # Adjust confidence score based on split territory flag
            if confidence_level == 'high':
                conf_score = 75
            elif is_split:
                conf_score = 55  # Lower score for possible split territories
            else:
                conf_score = 60
            
            note = f"Electric utility serving ZIP {zip_code} ({dominance_pct}% of {sample_count} verified addresses)"
            if is_split:
                note += " - POSSIBLE SPLIT TERRITORY"
            
            return {
                'name': utility['name'],
                'phone': utility.get('phone'),
                'website': utility.get('website'),
                'source': 'tenant_verified_zip',
                'confidence': confidence_level,
                'confidence_score': conf_score,
                'dominance_pct': dominance_pct,
                'sample_count': sample_count,
                'possible_split_territory': is_split,
                'note': note
            }
    
    return None


def load_remaining_states_gas_data() -> dict:
    """Load remaining states gas utility data."""
    global _remaining_states_gas_data
    if _remaining_states_gas_data is None:
        if os.path.exists(REMAINING_STATES_GAS_FILE):
            with open(REMAINING_STATES_GAS_FILE, 'r') as f:
                _remaining_states_gas_data = json.load(f)
        else:
            _remaining_states_gas_data = {}
    return _remaining_states_gas_data


def lookup_remaining_states_gas(zip_code: str, state: str) -> Optional[Dict]:
    """Look up gas utility for remaining states by ZIP code."""
    if not zip_code or not state:
        return None
    
    data = load_remaining_states_gas_data()
    states_data = data.get('states', {})
    
    state_upper = state.upper()
    if state_upper in states_data:
        zip_mappings = states_data[state_upper]
        if zip_code in zip_mappings:
            utility = zip_mappings[zip_code]
            confidence_level = utility.get('confidence_level', 'medium')
            dominance_pct = utility.get('dominance_pct', 60)
            sample_count = utility.get('sample_count', 1)
            is_split = utility.get('possible_split_territory', False)
            
            # Adjust confidence score based on split territory flag
            if confidence_level == 'high':
                conf_score = 75
            elif is_split:
                conf_score = 55
            else:
                conf_score = 60
            
            note = f"Gas utility serving ZIP {zip_code} ({dominance_pct}% of {sample_count} verified addresses)"
            if is_split:
                note += " - POSSIBLE SPLIT TERRITORY"
            
            return {
                'name': utility['name'],
                'phone': utility.get('phone'),
                'website': utility.get('website'),
                'source': 'tenant_verified_zip',
                'confidence': confidence_level,
                'confidence_score': conf_score,
                'dominance_pct': dominance_pct,
                'sample_count': sample_count,
                'possible_split_territory': is_split,
                'note': note
            }
    
    return None


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
    
    # SPECIAL CASE: Southern California - check ZIP-based water districts
    if state_upper == 'CA' and zip_code:
        prefix = zip_code[:3]
        if prefix in ['900', '901', '902', '903', '904', '905', '906', '907', '908', 
                      '910', '911', '912', '913', '914', '915', '916', '917', '918',
                      '926', '927', '928', '925', '951', '952', '923', '924', '935']:
            socal_result = lookup_socal_water(zip_code)
            if socal_result:
                return socal_result
    
    # SPECIAL CASE: Dallas-Fort Worth - check ZIP-based water utilities
    if state_upper == 'TX' and zip_code and zip_code[:2] in ['75', '76']:
        dfw_result = lookup_dfw_water(zip_code)
        if dfw_result:
            return dfw_result
    
    # SPECIAL CASE: Houston metro - check ZIP-based water utilities
    if state_upper == 'TX' and zip_code and zip_code.startswith('77'):
        houston_result = lookup_houston_water(zip_code)
        if houston_result:
            return houston_result
    
    # SPECIAL CASE: Philadelphia metro (PA 19xxx, NJ 080-086xxx)
    if zip_code:
        if (state_upper == 'PA' and zip_code.startswith('19')) or \
           (state_upper == 'NJ' and zip_code[:3] in ['080', '081', '082', '083', '084', '085', '086']):
            philly_result = lookup_philly_water(zip_code)
            if philly_result:
                return philly_result
    
    # SPECIAL CASE: DC metro (DC 200-205, MD 206-219, VA 220-223)
    if zip_code:
        prefix = zip_code[:3]
        if (state_upper == 'DC' and prefix in ['200', '201', '202', '203', '204', '205']) or \
           (state_upper == 'MD' and prefix in ['206', '207', '208', '209', '210', '211', '212', '214', '215', '217', '218', '219']) or \
           (state_upper == 'VA' and prefix in ['220', '221', '222', '223', '201']):
            dc_result = lookup_dc_water(zip_code)
            if dc_result:
                return dc_result
    
    # SPECIAL CASE: Atlanta metro (GA 30xxx, 31xxx)
    if state_upper == 'GA' and zip_code and zip_code[:2] in ['30', '31']:
        atlanta_result = lookup_atlanta_water(zip_code)
        if atlanta_result:
            return atlanta_result
    
    # SPECIAL CASE: Florida (33xxx, 34xxx)
    if state_upper == 'FL' and zip_code and zip_code[:2] in ['33', '34']:
        florida_result = lookup_florida_water(zip_code)
        if florida_result:
            return florida_result
    
    # FALLBACK: Check remaining states water mappings
    remaining_result = lookup_remaining_states_water(zip_code, state_upper)
    if remaining_result:
        return remaining_result
    
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
