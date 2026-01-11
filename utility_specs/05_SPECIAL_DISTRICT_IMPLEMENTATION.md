# Special District Implementation

## Context

Special districts (MUDs, CDDs, PUDs, etc.) provide water and sewer to millions of addresses but aren't in our current data. This spec covers how to ingest, store, and query special district data.

## Prerequisites

- Read `04_SPECIAL_DISTRICTS_ALL_STATES.md` for data sources
- Start with Texas (TCEQ) as the first implementation

## Goal

- Ingest special district boundary data from state sources
- Create fast lookup by coordinates and ZIP
- Integrate into water utility lookup flow
- Return special district as primary provider when applicable

## Implementation

### Step 1: Create Directory Structure

```bash
mkdir -p data/special_districts/raw
mkdir -p data/special_districts/processed
```

### Step 2: Create Schema

Create file: `data/special_districts/schema.json`

```json
{
  "district": {
    "district_id": "string (e.g., TX-MUD-001234)",
    "name": "string",
    "state": "string (2-letter)",
    "type": "string (MUD, CDD, PUD, etc.)",
    "services": ["water", "sewer"],
    "boundary": {
      "type": "polygon | zip_list | subdivision_list",
      "data": "GeoJSON polygon OR array of ZIPs OR array of subdivision names"
    },
    "contact": {
      "phone": "string",
      "website": "string",
      "address": "string"
    },
    "data_source": "string (e.g., TCEQ)",
    "last_updated": "ISO date string"
  }
}
```

### Step 3: Create Special Districts Module

Create file: `special_districts.py`

```python
"""
Special district lookup for water/sewer utilities.
Handles MUDs (TX), CDDs (FL), Metro Districts (CO), etc.
"""

import json
import os
from typing import Dict, List, Optional, Tuple
from shapely.geometry import Point, shape
from shapely.prepared import prep

DISTRICTS_DIR = os.path.join(os.path.dirname(__file__), 'data', 'special_districts', 'processed')

# Caches
_districts_by_state: Dict[str, List[dict]] = {}
_zip_to_districts: Dict[str, List[str]] = {}
_subdivision_to_district: Dict[str, str] = {}
_prepared_polygons: Dict[str, any] = {}


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


def get_prepared_polygon(district: dict) -> Optional[any]:
    """Get or create a prepared polygon for fast point-in-polygon tests."""
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
    district = lookup_by_coordinates(lat, lon, state, service)
    if district:
        district = district.copy()
        district['match_method'] = 'coordinates'
        district['confidence'] = 'high'
        return district
    
    # Try subdivision name
    if subdivision:
        district = lookup_by_subdivision(subdivision, state)
        if district:
            district = district.copy()
            district['match_method'] = 'subdivision'
            district['confidence'] = 'high'
            return district
    
    # Fall back to ZIP
    if zip_code:
        districts = lookup_by_zip(zip_code, state, service)
        if len(districts) == 1:
            district = districts[0].copy()
            district['match_method'] = 'zip'
            district['confidence'] = 'medium'
            return district
        elif len(districts) > 1:
            # Multiple districts in this ZIP - return as candidates
            # Let caller handle disambiguation
            return {
                'multiple_matches': True,
                'candidates': districts,
                'match_method': 'zip',
                'confidence': 'low',
                'note': f'{len(districts)} special districts overlap this ZIP'
            }
    
    return None


def format_district_for_response(district: dict) -> dict:
    """Format district data for API response."""
    if district.get('multiple_matches'):
        return {
            'name': 'Multiple Special Districts',
            'confidence': 'low',
            'note': district['note'],
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
        'type': district['type'],
        'phone': district.get('contact', {}).get('phone'),
        'website': district.get('contact', {}).get('website'),
        'confidence': district.get('confidence', 'medium'),
        'source': f"Special District ({district['type']})",
        'match_method': district.get('match_method'),
        'note': f"This address is served by {district['name']}, a {district['type']}."
    }
```

### Step 4: Create Texas MUD Ingestion Script

Create file: `scripts/ingest_texas_muds.py`

```python
"""
Ingest Texas MUD/WCID/FWSD data from TCEQ.

Data source: https://www.tceq.texas.gov/gis
Download: MUD shapefiles

Run: python scripts/ingest_texas_muds.py /path/to/mud_shapefile.shp
"""

import json
import sys
import os
from datetime import datetime

try:
    import geopandas as gpd
    from shapely.geometry import mapping
except ImportError:
    print("Install required packages: pip install geopandas shapely")
    sys.exit(1)


def ingest_texas_muds(shapefile_path: str, output_dir: str):
    """
    Parse TCEQ MUD shapefile and output processed JSON.
    """
    print(f"Reading shapefile: {shapefile_path}")
    gdf = gpd.read_file(shapefile_path)
    
    print(f"Found {len(gdf)} districts")
    
    districts = []
    zip_to_district = {}
    
    for idx, row in gdf.iterrows():
        # Extract district info from shapefile attributes
        # Adjust field names based on actual TCEQ data
        district_name = row.get('DIST_NAME', row.get('NAME', f'Unknown District {idx}'))
        district_type = row.get('DIST_TYPE', 'MUD')
        district_id = f"TX-{district_type}-{idx:06d}"
        
        # Get geometry as GeoJSON
        geometry = mapping(row.geometry)
        
        district = {
            'district_id': district_id,
            'name': district_name,
            'state': 'TX',
            'type': district_type,
            'services': ['water', 'sewer'],  # Assume both for MUDs
            'boundary': {
                'type': 'polygon',
                'data': geometry
            },
            'contact': {
                'phone': row.get('PHONE', None),
                'website': row.get('WEBSITE', None),
                'address': row.get('ADDRESS', None)
            },
            'data_source': 'TCEQ',
            'last_updated': datetime.now().isoformat()
        }
        
        districts.append(district)
        
        # Build ZIP index by finding ZIPs that intersect this polygon
        # This requires a ZIP boundary file - skip for now, can add later
        
        if idx % 100 == 0:
            print(f"Processed {idx} districts...")
    
    # Save processed districts
    output_file = os.path.join(output_dir, 'tx_districts.json')
    with open(output_file, 'w') as f:
        json.dump(districts, f)
    
    print(f"Saved {len(districts)} districts to {output_file}")
    
    # Create simplified index without full polygons (for faster loading)
    index = []
    for d in districts:
        index.append({
            'district_id': d['district_id'],
            'name': d['name'],
            'type': d['type'],
            'services': d['services']
        })
    
    index_file = os.path.join(output_dir, 'tx_districts_index.json')
    with open(index_file, 'w') as f:
        json.dump(index, f)
    
    print(f"Saved index to {index_file}")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python ingest_texas_muds.py /path/to/shapefile.shp")
        sys.exit(1)
    
    shapefile_path = sys.argv[1]
    output_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'special_districts', 'processed')
    os.makedirs(output_dir, exist_ok=True)
    
    ingest_texas_muds(shapefile_path, output_dir)
```

### Step 5: Integrate Into Water Lookup

In `utility_lookup.py`, update `lookup_water_utility`:

```python
from special_districts import lookup_special_district, format_district_for_response

def lookup_water_utility(lat, lon, city, county, state, zip_code, verify=True, subdivision=None):
    """
    Lookup water utility with special district priority.
    """
    
    # === PRIORITY 1: Check special districts ===
    special_district = lookup_special_district(
        lat=lat,
        lon=lon,
        state=state,
        zip_code=zip_code,
        subdivision=subdivision,
        service='water'
    )
    
    if special_district:
        if special_district.get('multiple_matches'):
            # Multiple districts - still return but flag for verification
            result = format_district_for_response(special_district)
            result['needs_verification'] = True
            return [result]
        else:
            # Single district match - high confidence
            result = format_district_for_response(special_district)
            return [result]
    
    # === PRIORITY 2: SERP verification (if enabled) ===
    if verify:
        serp_result = verify_with_serp(f"water utility for {city} {state}")
        if serp_result and serp_result.get('provider'):
            return [{
                'name': serp_result['provider'],
                'confidence': 'high',
                'source': 'Google Search',
                'verified': True
            }]
    
    # === PRIORITY 3: Supplemental file ===
    # ... existing logic ...
    
    # === PRIORITY 4: EPA SDWIS ===
    # ... existing logic ...
    
    # === PRIORITY 5: Heuristics ===
    # ... existing logic ...
```

### Step 6: Add Dependencies

Add to `requirements.txt`:
```
geopandas>=0.14.0
shapely>=2.0.0
pyproj>=3.6.0
```

Note: These are only needed for the ingestion script. The runtime lookup uses pre-processed JSON.

### Step 7: Create Generic Ingestion Script

Create file: `scripts/ingest_special_districts.py`

```python
"""
Generic special district ingestion script.
Handles multiple states and data formats.

Usage:
    python scripts/ingest_special_districts.py --state TX --source tceq --file /path/to/data
    python scripts/ingest_special_districts.py --state FL --source deo --file /path/to/data
    python scripts/ingest_special_districts.py --state CO --source dola --file /path/to/data
"""

import argparse
import json
import os
from datetime import datetime

# State-specific ingestors
INGESTORS = {
    'TX': {
        'tceq': 'ingest_texas_tceq',
    },
    'FL': {
        'deo': 'ingest_florida_deo',
    },
    'CO': {
        'dola': 'ingest_colorado_dola',
    },
    'CA': {
        'lafco': 'ingest_california_lafco',
    }
}


def ingest_texas_tceq(filepath: str) -> list:
    """Ingest Texas TCEQ MUD data."""
    import geopandas as gpd
    from shapely.geometry import mapping
    
    gdf = gpd.read_file(filepath)
    districts = []
    
    for idx, row in gdf.iterrows():
        district = {
            'district_id': f"TX-MUD-{idx:06d}",
            'name': row.get('DIST_NAME', f'Unknown {idx}'),
            'state': 'TX',
            'type': row.get('DIST_TYPE', 'MUD'),
            'services': ['water', 'sewer'],
            'boundary': {
                'type': 'polygon',
                'data': mapping(row.geometry)
            },
            'contact': {
                'phone': row.get('PHONE'),
                'website': row.get('WEBSITE')
            },
            'data_source': 'TCEQ',
            'last_updated': datetime.now().isoformat()
        }
        districts.append(district)
    
    return districts


def ingest_florida_deo(filepath: str) -> list:
    """Ingest Florida DEO special district data."""
    # Florida data may be CSV or JSON from their portal
    with open(filepath, 'r') as f:
        raw_data = json.load(f)
    
    districts = []
    for record in raw_data:
        if record.get('district_type') not in ['Community Development District', 'CDD']:
            continue
        
        district = {
            'district_id': f"FL-CDD-{record.get('id', len(districts)):06d}",
            'name': record.get('name'),
            'state': 'FL',
            'type': 'CDD',
            'services': ['water', 'sewer'],  # Verify per-district
            'boundary': {
                'type': 'zip_list',
                'data': record.get('zip_codes', [])
            },
            'contact': {
                'phone': record.get('phone'),
                'website': record.get('website')
            },
            'data_source': 'FL DEO',
            'last_updated': datetime.now().isoformat()
        }
        districts.append(district)
    
    return districts


def ingest_colorado_dola(filepath: str) -> list:
    """Ingest Colorado DOLA metro district data."""
    import geopandas as gpd
    from shapely.geometry import mapping
    
    gdf = gpd.read_file(filepath)
    districts = []
    
    for idx, row in gdf.iterrows():
        district = {
            'district_id': f"CO-METRO-{idx:06d}",
            'name': row.get('DIST_NAME', f'Unknown {idx}'),
            'state': 'CO',
            'type': 'Metro District',
            'services': determine_services(row),
            'boundary': {
                'type': 'polygon',
                'data': mapping(row.geometry)
            },
            'contact': {
                'phone': row.get('PHONE'),
                'website': row.get('WEBSITE')
            },
            'data_source': 'DOLA',
            'last_updated': datetime.now().isoformat()
        }
        districts.append(district)
    
    return districts


def determine_services(row) -> list:
    """Determine which services a district provides based on name/type."""
    name = str(row.get('DIST_NAME', '')).upper()
    services = []
    
    if 'WATER' in name:
        services.append('water')
    if 'SEWER' in name or 'SANITATION' in name or 'WASTEWATER' in name:
        services.append('sewer')
    if 'METRO' in name:
        services.extend(['water', 'sewer'])  # Metro districts often do both
    
    return list(set(services)) if services else ['water', 'sewer']


def main():
    parser = argparse.ArgumentParser(description='Ingest special district data')
    parser.add_argument('--state', required=True, help='State code (TX, FL, CO, etc.)')
    parser.add_argument('--source', required=True, help='Data source (tceq, deo, dola, etc.)')
    parser.add_argument('--file', required=True, help='Path to data file')
    parser.add_argument('--output', help='Output directory', 
                        default='data/special_districts/processed')
    
    args = parser.parse_args()
    
    state = args.state.upper()
    source = args.source.lower()
    
    if state not in INGESTORS:
        print(f"No ingestor available for state: {state}")
        print(f"Available states: {list(INGESTORS.keys())}")
        return
    
    if source not in INGESTORS[state]:
        print(f"No ingestor for source '{source}' in {state}")
        print(f"Available sources: {list(INGESTORS[state].keys())}")
        return
    
    ingestor_name = INGESTORS[state][source]
    ingestor_func = globals()[ingestor_name]
    
    print(f"Ingesting {state} data from {source}...")
    districts = ingestor_func(args.file)
    
    print(f"Processed {len(districts)} districts")
    
    # Save
    os.makedirs(args.output, exist_ok=True)
    output_file = os.path.join(args.output, f'{state.lower()}_districts.json')
    
    with open(output_file, 'w') as f:
        json.dump(districts, f)
    
    print(f"Saved to {output_file}")


if __name__ == '__main__':
    main()
```

## Testing

### Test Special District Lookup
```python
from special_districts import lookup_special_district

# Test Texas MUD lookup (requires data to be ingested)
result = lookup_special_district(
    lat=30.1234,
    lon=-97.5678,
    state='TX',
    zip_code='78640',
    service='water'
)

if result:
    print(f"Found district: {result['name']}")
    print(f"Confidence: {result['confidence']}")
else:
    print("No special district found")
```

### Test API Response
```bash
curl "https://web-production-9acc6.up.railway.app/api/lookup?address=123+New+Development+Dr+Kyle+TX+78640"
```

Should return special district as water provider if address is in a MUD.

## Commit Message

```
Add special district support for water/sewer utilities

- special_districts.py module for lookup logic
- Point-in-polygon matching for precise boundaries
- ZIP and subdivision fallback matching
- Texas MUD ingestion script (TCEQ data)
- Generic ingestion script for multiple states
- Integration with water utility lookup
```
