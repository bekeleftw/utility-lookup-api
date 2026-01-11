"""
Special district lookup for water/sewer utilities.
Handles MUDs (TX), CDDs (FL), Metro Districts (CO), etc.
"""

import json
import os
from typing import Dict, List, Optional, Any

DISTRICTS_DIR = os.path.join(os.path.dirname(__file__), 'data', 'special_districts', 'processed')

# Caches
_districts_by_state: Dict[str, List[dict]] = {}
_zip_to_districts: Dict[str, List[str]] = {}
_subdivision_to_district: Dict[str, str] = {}
_prepared_polygons: Dict[str, Any] = {}

# Try to import shapely for polygon operations
try:
    from shapely.geometry import Point, shape
    from shapely.prepared import prep
    SHAPELY_AVAILABLE = True
except ImportError:
    SHAPELY_AVAILABLE = False
    print("Warning: shapely not installed. Polygon-based lookups will be disabled.")


def load_state_districts(state: str) -> List[dict]:
    """Load all districts for a state."""
    if state in _districts_by_state:
        return _districts_by_state[state]
    
    filepath = os.path.join(DISTRICTS_DIR, f'{state.lower()}_districts.json')
    if not os.path.exists(filepath):
        _districts_by_state[state] = []
        return []
    
    with open(filepath, 'r') as f:
        districts = json.load(f)
    
    _districts_by_state[state] = districts
    return districts


def load_zip_index() -> Dict[str, List[str]]:
    """Load ZIP to district ID index."""
    global _zip_to_districts
    if _zip_to_districts:
        return _zip_to_districts
    
    filepath = os.path.join(DISTRICTS_DIR, 'zip_to_district.json')
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            _zip_to_districts = json.load(f)
    
    return _zip_to_districts


def load_subdivision_index() -> Dict[str, str]:
    """Load subdivision name to district ID index."""
    global _subdivision_to_district
    if _subdivision_to_district:
        return _subdivision_to_district
    
    filepath = os.path.join(DISTRICTS_DIR, 'subdivision_to_district.json')
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            _subdivision_to_district = json.load(f)
    
    return _subdivision_to_district


def get_prepared_polygon(district: dict) -> Optional[Any]:
    """Get or create a prepared polygon for fast point-in-polygon tests."""
    if not SHAPELY_AVAILABLE:
        return None
    
    district_id = district['district_id']
    
    if district_id in _prepared_polygons:
        return _prepared_polygons[district_id]
    
    boundary = district.get('boundary', {})
    if boundary.get('type') != 'polygon':
        return None
    
    try:
        polygon = shape(boundary['data'])
        prepared = prep(polygon)
        _prepared_polygons[district_id] = prepared
        return prepared
    except Exception as e:
        print(f"Error creating polygon for {district_id}: {e}")
        return None


def lookup_by_coordinates(lat: float, lon: float, state: str, service: str = 'water') -> Optional[dict]:
    """
    Find special district containing these coordinates.
    
    Args:
        lat: Latitude
        lon: Longitude
        state: 2-letter state code
        service: 'water' or 'sewer'
    
    Returns:
        District dict if found, None otherwise
    """
    if not SHAPELY_AVAILABLE:
        return None
    
    districts = load_state_districts(state)
    point = Point(lon, lat)  # Note: shapely uses (x, y) = (lon, lat)
    
    for district in districts:
        # Check if district provides the requested service
        if service not in district.get('services', []):
            continue
        
        boundary = district.get('boundary', {})
        
        if boundary.get('type') == 'polygon':
            prepared = get_prepared_polygon(district)
            if prepared and prepared.contains(point):
                return district
    
    return None


def lookup_by_zip(zip_code: str, state: str, service: str = 'water') -> List[dict]:
    """
    Find special districts that may serve this ZIP.
    
    Note: ZIP-level lookup is less precise than coordinate lookup.
    Multiple districts may overlap a single ZIP.
    
    Returns:
        List of possible districts
    """
    zip_index = load_zip_index()
    district_ids = zip_index.get(zip_code, [])
    
    if not district_ids:
        return []
    
    districts = load_state_districts(state)
    district_map = {d['district_id']: d for d in districts}
    
    results = []
    for did in district_ids:
        if did in district_map:
            district = district_map[did]
            if service in district.get('services', []):
                results.append(district)
    
    return results


def lookup_by_subdivision(subdivision: str, state: str) -> Optional[dict]:
    """
    Find special district by subdivision name.
    
    This is useful when the address includes a subdivision name that
    we've mapped to a specific district.
    """
    subdivision_index = load_subdivision_index()
    key = f"{subdivision.upper()}|{state}"
    
    district_id = subdivision_index.get(key)
    if not district_id:
        return None
    
    districts = load_state_districts(state)
    for district in districts:
        if district['district_id'] == district_id:
            return district
    
    return None


def lookup_special_district(
    lat: float,
    lon: float,
    state: str,
    zip_code: str = None,
    subdivision: str = None,
    service: str = 'water'
) -> Optional[dict]:
    """
    Main entry point for special district lookup.
    
    Tries methods in order of precision:
    1. Coordinate lookup (most precise)
    2. Subdivision name lookup
    3. ZIP code lookup (least precise, returns first match)
    
    Returns:
        District dict with match_method field, or None
    """
    # Try coordinate lookup first (most precise)
    if lat and lon:
        district = lookup_by_coordinates(lat, lon, state, service)
        if district:
            district = district.copy()
            district['match_method'] = 'coordinates'
            district['_confidence'] = 'high'
            return district
    
    # Try subdivision name
    if subdivision:
        district = lookup_by_subdivision(subdivision, state)
        if district:
            district = district.copy()
            district['match_method'] = 'subdivision'
            district['_confidence'] = 'high'
            return district
    
    # Fall back to ZIP
    if zip_code:
        districts = lookup_by_zip(zip_code, state, service)
        if len(districts) == 1:
            district = districts[0].copy()
            district['match_method'] = 'zip'
            district['_confidence'] = 'medium'
            return district
        elif len(districts) > 1:
            # Multiple districts in this ZIP - try to disambiguate with coordinates
            if lat and lon and SHAPELY_AVAILABLE:
                from shapely.geometry import Point, shape
                point = Point(lon, lat)
                
                for d in districts:
                    boundary = d.get('boundary', {})
                    if boundary.get('type') == 'polygon' and boundary.get('data'):
                        try:
                            polygon = shape(boundary['data'])
                            if polygon.contains(point):
                                # Found the specific district containing the point
                                district = d.copy()
                                district['match_method'] = 'zip_with_coordinates'
                                district['_confidence'] = 'high'
                                return district
                        except Exception:
                            continue
            
            # Could not disambiguate - return as candidates
            return {
                'multiple_matches': True,
                'candidates': districts,
                'match_method': 'zip',
                '_confidence': 'low',
                'note': f'{len(districts)} special districts overlap this ZIP'
            }
    
    return None


def format_district_for_response(district: dict) -> dict:
    """Format district data for API response."""
    if district.get('multiple_matches'):
        return {
            'name': 'Multiple Special Districts',
            '_confidence': 'low',
            '_note': district['note'],
            '_source': 'special_district',
            'candidates': [
                {
                    'name': d['name'],
                    'type': d['type'],
                    'phone': d.get('contact', {}).get('phone'),
                    'website': d.get('contact', {}).get('website')
                }
                for d in district['candidates']
            ]
        }
    
    return {
        'name': district['name'],
        'type': district.get('type'),
        'phone': district.get('contact', {}).get('phone'),
        'website': district.get('contact', {}).get('website'),
        '_confidence': district.get('_confidence', 'medium'),
        '_source': f"special_district",
        '_match_method': district.get('match_method'),
        '_note': f"This address is served by {district['name']}, a {district.get('type', 'special district')}."
    }


def get_district_types_for_state(state: str) -> List[str]:
    """Get list of special district types used in a state."""
    state_types = {
        'TX': ['MUD', 'WCID', 'FWSD', 'WSC', 'PUD'],
        'FL': ['CDD', 'Special District'],
        'CO': ['Metro District', 'Water & Sanitation District', 'Water District'],
        'CA': ['CSD', 'CWD', 'MWD'],
        'AZ': ['DWID', 'ID'],
        'WA': ['PUD', 'Water-Sewer District'],
        'NV': ['GID'],
        'NE': ['SID'],
        'TN': ['UD'],
    }
    return state_types.get(state, ['Special District'])


def has_special_district_data(state: str) -> bool:
    """Check if we have special district data for a state."""
    filepath = os.path.join(DISTRICTS_DIR, f'{state.lower()}_districts.json')
    return os.path.exists(filepath)


def get_available_states() -> List[str]:
    """Get list of states with special district data."""
    if not os.path.exists(DISTRICTS_DIR):
        return []
    
    states = []
    for filename in os.listdir(DISTRICTS_DIR):
        if filename.endswith('_districts.json'):
            state = filename.replace('_districts.json', '').upper()
            states.append(state)
    
    return sorted(states)
