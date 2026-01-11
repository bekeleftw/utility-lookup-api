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
import sys
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
    """Ingest Texas TCEQ MUD data from shapefile."""
    try:
        import geopandas as gpd
        from shapely.geometry import mapping
    except ImportError:
        print("Error: geopandas and shapely required. Install with: pip install geopandas shapely")
        sys.exit(1)
    
    print(f"Reading shapefile: {filepath}")
    gdf = gpd.read_file(filepath)
    print(f"Found {len(gdf)} features")
    
    districts = []
    
    for idx, row in gdf.iterrows():
        # Extract district info from shapefile attributes
        # Field names may vary - adjust based on actual TCEQ data
        district_name = row.get('DIST_NAME') or row.get('NAME') or row.get('DISTNAME') or f'Unknown District {idx}'
        district_type = row.get('DIST_TYPE') or row.get('TYPE') or 'MUD'
        
        # Normalize district type
        district_type = district_type.upper() if district_type else 'MUD'
        if 'MUD' in district_type or 'MUNICIPAL UTILITY' in district_type:
            district_type = 'MUD'
        elif 'WCID' in district_type or 'WATER CONTROL' in district_type:
            district_type = 'WCID'
        elif 'FWSD' in district_type or 'FRESH WATER' in district_type:
            district_type = 'FWSD'
        
        district_id = f"TX-{district_type}-{idx:06d}"
        
        # Get geometry as GeoJSON
        geometry = mapping(row.geometry)
        
        district = {
            'district_id': district_id,
            'name': district_name,
            'state': 'TX',
            'type': district_type,
            'services': ['water', 'sewer'],  # MUDs typically provide both
            'boundary': {
                'type': 'polygon',
                'data': geometry
            },
            'contact': {
                'phone': row.get('PHONE') or row.get('TELEPHONE'),
                'website': row.get('WEBSITE') or row.get('URL'),
                'address': row.get('ADDRESS')
            },
            'data_source': 'TCEQ',
            'last_updated': datetime.now().isoformat()
        }
        
        districts.append(district)
        
        if idx % 100 == 0 and idx > 0:
            print(f"Processed {idx} districts...")
    
    return districts


def ingest_florida_deo(filepath: str) -> list:
    """Ingest Florida DEO special district data."""
    # Florida data may be CSV or JSON from their portal
    with open(filepath, 'r') as f:
        if filepath.endswith('.json'):
            raw_data = json.load(f)
        else:
            import csv
            reader = csv.DictReader(f)
            raw_data = list(reader)
    
    districts = []
    for idx, record in enumerate(raw_data):
        district_type = record.get('district_type', record.get('DISTRICT_TYPE', ''))
        
        # Filter for CDDs and water-related districts
        if not any(t in district_type.upper() for t in ['CDD', 'COMMUNITY DEVELOPMENT', 'WATER', 'UTILITY']):
            continue
        
        district = {
            'district_id': f"FL-CDD-{record.get('id', idx):06d}",
            'name': record.get('name', record.get('NAME', f'Unknown {idx}')),
            'state': 'FL',
            'type': 'CDD' if 'CDD' in district_type.upper() else 'Special District',
            'services': ['water', 'sewer'],
            'boundary': {
                'type': 'zip_list',
                'data': record.get('zip_codes', [])
            },
            'contact': {
                'phone': record.get('phone', record.get('PHONE')),
                'website': record.get('website', record.get('WEBSITE'))
            },
            'data_source': 'FL DEO',
            'last_updated': datetime.now().isoformat()
        }
        districts.append(district)
    
    return districts


def ingest_colorado_dola(filepath: str) -> list:
    """Ingest Colorado DOLA metro district data."""
    try:
        import geopandas as gpd
        from shapely.geometry import mapping
    except ImportError:
        print("Error: geopandas and shapely required. Install with: pip install geopandas shapely")
        sys.exit(1)
    
    gdf = gpd.read_file(filepath)
    districts = []
    
    for idx, row in gdf.iterrows():
        name = row.get('DIST_NAME') or row.get('NAME') or f'Unknown {idx}'
        
        # Determine services from name
        services = determine_services_from_name(name)
        
        district = {
            'district_id': f"CO-METRO-{idx:06d}",
            'name': name,
            'state': 'CO',
            'type': 'Metro District',
            'services': services,
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


def ingest_california_lafco(filepath: str) -> list:
    """Ingest California LAFCO district data."""
    try:
        import geopandas as gpd
        from shapely.geometry import mapping
    except ImportError:
        print("Error: geopandas and shapely required")
        sys.exit(1)
    
    gdf = gpd.read_file(filepath)
    districts = []
    
    for idx, row in gdf.iterrows():
        name = row.get('AGENCY_NAME') or row.get('NAME') or f'Unknown {idx}'
        district_type = row.get('AGENCY_TYPE') or 'CSD'
        
        district = {
            'district_id': f"CA-{district_type}-{idx:06d}",
            'name': name,
            'state': 'CA',
            'type': district_type,
            'services': determine_services_from_name(name),
            'boundary': {
                'type': 'polygon',
                'data': mapping(row.geometry)
            },
            'contact': {
                'phone': row.get('PHONE'),
                'website': row.get('WEBSITE')
            },
            'data_source': 'LAFCO',
            'last_updated': datetime.now().isoformat()
        }
        districts.append(district)
    
    return districts


def determine_services_from_name(name: str) -> list:
    """Determine which services a district provides based on name."""
    name_upper = name.upper()
    services = []
    
    if any(w in name_upper for w in ['WATER', 'AQUA', 'H2O']):
        services.append('water')
    if any(w in name_upper for w in ['SEWER', 'SANITATION', 'WASTEWATER', 'SANITARY']):
        services.append('sewer')
    if 'METRO' in name_upper or 'MUD' in name_upper:
        services.extend(['water', 'sewer'])
    
    return list(set(services)) if services else ['water', 'sewer']


def build_zip_index(districts: list, output_dir: str):
    """Build ZIP to district index from districts with zip_list boundaries."""
    zip_to_district = {}
    
    for district in districts:
        boundary = district.get('boundary', {})
        if boundary.get('type') == 'zip_list':
            for zip_code in boundary.get('data', []):
                if zip_code not in zip_to_district:
                    zip_to_district[zip_code] = []
                zip_to_district[zip_code].append(district['district_id'])
    
    if zip_to_district:
        filepath = os.path.join(output_dir, 'zip_to_district.json')
        with open(filepath, 'w') as f:
            json.dump(zip_to_district, f, indent=2)
        print(f"Saved ZIP index with {len(zip_to_district)} entries")


def main():
    parser = argparse.ArgumentParser(description='Ingest special district data')
    parser.add_argument('--state', required=True, help='State code (TX, FL, CO, etc.)')
    parser.add_argument('--source', required=True, help='Data source (tceq, deo, dola, etc.)')
    parser.add_argument('--file', required=True, help='Path to data file')
    parser.add_argument('--output', help='Output directory', 
                        default=os.path.join(os.path.dirname(os.path.dirname(__file__)), 
                                            'data', 'special_districts', 'processed'))
    
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
    
    # Build ZIP index if applicable
    build_zip_index(districts, args.output)
    
    # Create simplified index without full polygons
    index = []
    for d in districts:
        index.append({
            'district_id': d['district_id'],
            'name': d['name'],
            'type': d['type'],
            'services': d['services']
        })
    
    index_file = os.path.join(args.output, f'{state.lower()}_districts_index.json')
    with open(index_file, 'w') as f:
        json.dump(index, f, indent=2)
    
    print(f"Saved index to {index_file}")


if __name__ == '__main__':
    main()
