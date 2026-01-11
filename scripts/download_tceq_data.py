"""
Download Texas MUD/WCID/FWSD data from TCEQ ArcGIS REST API.
This avoids downloading large shapefiles by querying the API directly.

Usage:
    python scripts/download_tceq_data.py
"""

import json
import os
import sys
import requests
from datetime import datetime
from typing import List, Dict, Optional

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'special_districts', 'processed')

# TCEQ Water Districts Viewer ArcGIS endpoints
# Discovered from: https://gisweb.tceq.texas.gov/arcgis/rest/services/iwud/WaterDistricts_PRD/MapServer
# Layer IDs:
#   1: Drainage District
#   2: Fresh Water Supply District (FWSD)
#   3: Irrigation District
#   6: Municipal Utility District (MUD)
#   11: Special Utility District
#   13: Water Control & Improvement District (WCID)
BASE_URL = 'https://gisweb.tceq.texas.gov/arcgis/rest/services/iwud/WaterDistricts_PRD/MapServer'

TCEQ_ENDPOINTS = {
    'MUD': {
        'url': f'{BASE_URL}/6/query',
        'name': 'Municipal Utility Districts',
        'layer_id': 6
    },
    'WCID': {
        'url': f'{BASE_URL}/13/query',
        'name': 'Water Control & Improvement Districts',
        'layer_id': 13
    },
    'FWSD': {
        'url': f'{BASE_URL}/2/query',
        'name': 'Fresh Water Supply Districts',
        'layer_id': 2
    },
    'SUD': {
        'url': f'{BASE_URL}/11/query',
        'name': 'Special Utility Districts',
        'layer_id': 11
    },
}


def query_arcgis_endpoint(url: str, district_type: str, max_records: int = 2000) -> List[Dict]:
    """
    Query an ArcGIS REST endpoint for district data.
    Uses pagination to get all records.
    """
    all_features = []
    offset = 0
    
    while True:
        params = {
            'where': '1=1',  # Get all records
            'outFields': '*',
            'returnGeometry': 'true',
            'f': 'geojson',
            'resultOffset': offset,
            'resultRecordCount': max_records
        }
        
        print(f"  Querying {district_type} (offset {offset})...")
        
        try:
            response = requests.get(url, params=params, timeout=60)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            print(f"  Error querying {url}: {e}")
            break
        except json.JSONDecodeError as e:
            print(f"  Error parsing response: {e}")
            break
        
        features = data.get('features', [])
        if not features:
            break
        
        all_features.extend(features)
        print(f"    Got {len(features)} features (total: {len(all_features)})")
        
        # Check if there are more records
        if len(features) < max_records:
            break
        
        offset += max_records
    
    return all_features


def convert_geojson_to_district(feature: Dict, district_type: str, idx: int) -> Optional[Dict]:
    """Convert a GeoJSON feature to our district format."""
    props = feature.get('properties', {})
    geometry = feature.get('geometry')
    
    if not geometry:
        return None
    
    # Extract district info - field names vary by dataset
    # Try multiple possible field names
    district_name = (
        props.get('DIST_NAME') or 
        props.get('NAME') or 
        props.get('DistrictName') or
        props.get('DISTNAME') or
        f'Unknown {district_type} {idx}'
    )
    
    district_number = (
        props.get('DIST_NO') or 
        props.get('DISTRICT_NUMBER') or 
        props.get('DistrictNo') or
        props.get('DISTNO') or
        str(idx)
    )
    
    county = (
        props.get('COUNTY') or 
        props.get('CO_NAME') or 
        props.get('CountyName') or
        ''
    )
    
    # Create unique ID
    district_id = f"TX-{district_type}-{district_number}"
    
    # Determine services based on district type
    if district_type in ['MUD', 'WCID', 'FWSD']:
        services = ['water', 'sewer']
    elif district_type == 'WSC':
        services = ['water']
    else:
        services = ['water', 'sewer']
    
    district = {
        'district_id': district_id,
        'name': district_name,
        'state': 'TX',
        'county': county,
        'type': district_type,
        'services': services,
        'boundary': {
            'type': 'polygon',
            'data': geometry
        },
        'contact': {
            'phone': props.get('PHONE') or props.get('CONTACT_PHONE'),
            'website': props.get('WEBSITE') or props.get('URL'),
            'address': props.get('ADDRESS') or props.get('MAILING_ADDRESS')
        },
        'raw_properties': props,  # Keep original properties for reference
        'data_source': 'TCEQ',
        'last_updated': datetime.now().isoformat()
    }
    
    return district


def download_all_districts() -> List[Dict]:
    """Download all district types from TCEQ."""
    all_districts = []
    
    for district_type, config in TCEQ_ENDPOINTS.items():
        print(f"\nDownloading {config['name']} ({district_type})...")
        
        features = query_arcgis_endpoint(config['url'], district_type)
        
        if not features:
            print(f"  No data returned for {district_type}")
            continue
        
        print(f"  Converting {len(features)} features...")
        
        for idx, feature in enumerate(features):
            district = convert_geojson_to_district(feature, district_type, idx)
            if district:
                all_districts.append(district)
        
        print(f"  Added {len(features)} {district_type} districts")
    
    return all_districts


def build_zip_index_from_districts(districts: List[Dict]) -> Dict[str, List[str]]:
    """
    Build a simple ZIP index based on district properties.
    This is a fallback if we don't have ZIP boundary shapefiles.
    """
    # For now, we'll rely on coordinate-based lookups
    # A proper ZIP index requires ZIP boundary data
    return {}


def save_districts(districts: List[Dict], output_dir: str):
    """Save districts to JSON file."""
    os.makedirs(output_dir, exist_ok=True)
    
    # Save full district data
    output_file = os.path.join(output_dir, 'tx_districts.json')
    with open(output_file, 'w') as f:
        json.dump(districts, f)
    
    print(f"\nSaved {len(districts)} districts to {output_file}")
    
    # Save lightweight index (without full geometry)
    index = []
    for d in districts:
        index.append({
            'district_id': d['district_id'],
            'name': d['name'],
            'type': d['type'],
            'county': d.get('county', ''),
            'services': d['services']
        })
    
    index_file = os.path.join(output_dir, 'tx_districts_index.json')
    with open(index_file, 'w') as f:
        json.dump(index, f, indent=2)
    
    print(f"Saved index to {index_file}")
    
    # Print summary by type
    type_counts = {}
    for d in districts:
        dtype = d['type']
        type_counts[dtype] = type_counts.get(dtype, 0) + 1
    
    print("\nDistrict counts by type:")
    for dtype, count in sorted(type_counts.items()):
        print(f"  {dtype}: {count}")


def main():
    print("="*60)
    print("TCEQ Texas Water District Data Download")
    print("="*60)
    
    # Download all districts
    districts = download_all_districts()
    
    if not districts:
        print("\nNo districts downloaded. Check network connection and TCEQ API availability.")
        return
    
    # Save to file
    save_districts(districts, OUTPUT_DIR)
    
    print("\n" + "="*60)
    print("Download complete!")
    print("="*60)


if __name__ == '__main__':
    main()
