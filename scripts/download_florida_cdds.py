"""
Download Florida CDD (Community Development District) boundaries from state GIS services.
Florida CDDs are similar to Texas MUDs - they provide water, sewer, and infrastructure
in new developments, especially common in Orlando, Tampa, Jacksonville, and South Florida.

Usage:
    python scripts/download_florida_cdds.py
"""

import requests
import json
import os
import sys
from datetime import datetime
from typing import List, Dict, Optional

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'special_districts', 'raw', 'florida')
PROCESSED_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'special_districts', 'processed')

# Florida GIS endpoints - county-level sources (more reliable than statewide)
COUNTY_ENDPOINTS = [
    {
        'name': 'Hillsborough County CDDs',
        'url': 'https://services.arcgis.com/EvFQzFPiDlAJEJii/arcgis/rest/services/CommunityDevelopmentDistricts/FeatureServer/0',
        'county': 'Hillsborough'
    },
    {
        'name': 'Miami-Dade County CDDs',
        'url': 'https://gisfs.miamidade.gov/mdarcgis/rest/services/OpenData/MD_PhysicalCulturalLandmarks/MapServer/11',
        'county': 'Miami-Dade'
    },
    {
        'name': 'Orange County CDDs',
        'url': 'https://services1.arcgis.com/GGQC3PB4eVPnfRmL/arcgis/rest/services/CDD_Boundaries/FeatureServer/0',
        'county': 'Orange'
    },
    {
        'name': 'Osceola County CDDs',
        'url': 'https://services.arcgis.com/1Aq2enyHnN8DPHBQ/arcgis/rest/services/CDD/FeatureServer/0',
        'county': 'Osceola'
    },
    {
        'name': 'Polk County CDDs',
        'url': 'https://services.arcgis.com/aKxrz4vDVjfUwBWJ/arcgis/rest/services/CDD/FeatureServer/0',
        'county': 'Polk'
    },
    {
        'name': 'Lee County CDDs',
        'url': 'https://services.arcgis.com/dqvPHtZpMXoYET5f/arcgis/rest/services/CDD/FeatureServer/0',
        'county': 'Lee'
    },
    {
        'name': 'Manatee County CDDs',
        'url': 'https://services.arcgis.com/apTfC6SUmnNfnxuF/arcgis/rest/services/CDD/FeatureServer/0',
        'county': 'Manatee'
    },
    {
        'name': 'Pasco County CDDs',
        'url': 'https://services.arcgis.com/EvFQzFPiDlAJEJii/arcgis/rest/services/CDD/FeatureServer/0',
        'county': 'Pasco'
    }
]

# Statewide endpoints (may not work)
ENDPOINTS = [
    {
        'name': 'Florida DEO Special Districts',
        'url': 'https://services1.arcgis.com/O1JpcwDW8sjYuddV/arcgis/rest/services/CDD_Boundaries/FeatureServer/0',
        'type': 'CDD'
    },
]

# Alternative: Direct download URLs
DIRECT_DOWNLOADS = [
    'https://opendata.arcgis.com/api/v3/datasets/florida-community-development-districts/downloads/data?format=geojson',
]


def query_arcgis_endpoint(base_url: str, offset: int = 0, limit: int = 1000) -> Optional[Dict]:
    """Query ArcGIS REST API with pagination."""
    query_url = f"{base_url}/query"
    
    params = {
        'where': '1=1',
        'outFields': '*',
        'returnGeometry': 'true',
        'f': 'geojson',
        'resultOffset': offset,
        'resultRecordCount': limit,
        'outSR': '4326'  # Request WGS84 coordinates
    }
    
    try:
        response = requests.get(query_url, params=params, timeout=60)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"    Error querying {base_url}: {e}")
        return None


def download_all_features(base_url: str) -> List[Dict]:
    """Download all features with pagination."""
    all_features = []
    offset = 0
    limit = 1000
    
    while True:
        print(f"  Fetching records {offset} to {offset + limit}...")
        
        data = query_arcgis_endpoint(base_url, offset, limit)
        if not data:
            break
        
        features = data.get('features', [])
        if not features:
            break
        
        all_features.extend(features)
        print(f"    Got {len(features)} features (total: {len(all_features)})")
        
        if len(features) < limit:
            break
        
        offset += limit
    
    return all_features


def process_florida_cdds(features: List[Dict]) -> List[Dict]:
    """Process raw GeoJSON features into our district format."""
    districts = []
    
    for i, feature in enumerate(features):
        props = feature.get('properties', {})
        geom = feature.get('geometry')
        
        if not geom:
            continue
        
        # Extract district info - field names vary by source
        name = (
            props.get('NAME') or 
            props.get('CDD_NAME') or 
            props.get('DISTNAME') or
            props.get('District_Name') or
            props.get('DISTRICT_NAME') or
            f"Florida CDD {i}"
        )
        
        county = (
            props.get('COUNTY') or 
            props.get('CO_NAME') or
            props.get('COUNTY_NAME') or
            props.get('CountyName') or
            ''
        )
        
        # Get district number/ID
        district_num = (
            props.get('DIST_NUM') or
            props.get('DISTRICT_NUM') or
            props.get('CDD_NUM') or
            props.get('OBJECTID') or
            str(i)
        )
        
        # Determine district type
        dist_type = props.get('DIST_TYPE') or props.get('TYPE') or 'CDD'
        if 'CDD' in name.upper() or 'COMMUNITY DEVELOPMENT' in name.upper():
            dist_type = 'CDD'
        
        # Create unique ID
        district_id = f"FL-{dist_type}-{district_num}"
        
        # CDDs typically provide water and sewer
        services = ['water', 'sewer']
        
        # Check for additional services in properties
        if props.get('PROVIDES_ELECTRIC') or 'ELECTRIC' in str(props).upper():
            services.append('electric')
        
        district = {
            'district_id': district_id,
            'name': name,
            'state': 'FL',
            'county': county,
            'type': dist_type,
            'services': services,
            'boundary': {
                'type': 'polygon',
                'data': geom
            },
            'contact': {
                'phone': props.get('PHONE') or props.get('CONTACT_PHONE'),
                'website': props.get('WEBSITE') or props.get('URL') or props.get('WEB'),
                'address': props.get('ADDRESS') or props.get('MAILING_ADDRESS'),
                'manager': props.get('MANAGER') or props.get('DISTRICT_MANAGER')
            },
            'raw_properties': props,
            'data_source': 'Florida DEO',
            'last_updated': datetime.now().isoformat()
        }
        
        districts.append(district)
    
    return districts


def save_districts(districts: List[Dict], output_file: str):
    """Save processed districts to JSON file."""
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    with open(output_file, 'w') as f:
        json.dump(districts, f)
    
    print(f"Saved {len(districts)} districts to {output_file}")


def save_raw_geojson(features: List[Dict], output_file: str):
    """Save raw GeoJSON for reference."""
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    geojson = {
        'type': 'FeatureCollection',
        'features': features
    }
    
    with open(output_file, 'w') as f:
        json.dump(geojson, f)
    
    print(f"Saved raw GeoJSON to {output_file}")


def try_endpoints() -> List[Dict]:
    """Try multiple endpoints until one works."""
    all_features = []
    
    # First try county-level endpoints
    print("\n--- Trying County-Level Endpoints ---")
    for endpoint in COUNTY_ENDPOINTS:
        print(f"\nTrying: {endpoint['name']}")
        print(f"  URL: {endpoint['url']}")
        
        features = download_all_features(endpoint['url'])
        
        if features:
            print(f"  Success! Got {len(features)} features from {endpoint['county']} County")
            # Add county info to features
            for f in features:
                if 'properties' not in f:
                    f['properties'] = {}
                f['properties']['_source_county'] = endpoint['county']
            all_features.extend(features)
        else:
            print(f"  No data returned")
    
    if all_features:
        return all_features
    
    # Fall back to statewide endpoints
    print("\n--- Trying Statewide Endpoints ---")
    for endpoint in ENDPOINTS:
        print(f"\nTrying: {endpoint['name']}")
        print(f"  URL: {endpoint['url']}")
        
        features = download_all_features(endpoint['url'])
        
        if features:
            print(f"  Success! Got {len(features)} features")
            return features
        else:
            print(f"  No data returned")
    
    return []


def main():
    print("="*60)
    print("Florida CDD Data Download")
    print("="*60)
    
    # Try to download from endpoints
    features = try_endpoints()
    
    if not features:
        print("\nNo data downloaded from any endpoint.")
        print("You may need to manually download from:")
        print("  https://specialdistrictreports.floridajobs.org/")
        return
    
    # Save raw data
    raw_file = os.path.join(OUTPUT_DIR, 'fl_cdds_raw.geojson')
    save_raw_geojson(features, raw_file)
    
    # Process into our format
    print(f"\nProcessing {len(features)} features...")
    districts = process_florida_cdds(features)
    print(f"Created {len(districts)} district records")
    
    # Save processed data
    processed_file = os.path.join(PROCESSED_DIR, 'fl_districts.json')
    save_districts(districts, processed_file)
    
    # Create lightweight index
    index = []
    for d in districts:
        index.append({
            'district_id': d['district_id'],
            'name': d['name'],
            'type': d['type'],
            'county': d.get('county', ''),
            'services': d['services']
        })
    
    index_file = os.path.join(PROCESSED_DIR, 'fl_districts_index.json')
    with open(index_file, 'w') as f:
        json.dump(index, f, indent=2)
    print(f"Saved index to {index_file}")
    
    # Print summary by county
    county_counts = {}
    for d in districts:
        county = d.get('county', 'Unknown')
        county_counts[county] = county_counts.get(county, 0) + 1
    
    print("\nDistricts by county (top 10):")
    for county, count in sorted(county_counts.items(), key=lambda x: -x[1])[:10]:
        print(f"  {county}: {count}")
    
    print("\n" + "="*60)
    print("Download complete!")
    print("="*60)


if __name__ == '__main__':
    main()
