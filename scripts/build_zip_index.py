"""
Build ZIP code to district index for fast lookups.
Uses the district polygon boundaries to find which ZIPs they intersect.

Since we don't have ZIP boundary shapefiles locally, this script uses
the TCEQ ZIP layer from their MapServer to build the index.

Usage:
    python scripts/build_zip_index.py
"""

import json
import os
import sys
import requests
from typing import Dict, List, Set

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DISTRICTS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 
                              'data', 'special_districts', 'processed', 'tx_districts.json')
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 
                           'data', 'special_districts', 'processed', 'zip_to_district.json')

# TCEQ ZIP codes layer
ZIP_LAYER_URL = 'https://gisweb.tceq.texas.gov/arcgis/rest/services/iwud/WaterDistricts_PRD/MapServer/18/query'


def get_texas_zips() -> Dict[str, dict]:
    """Get all Texas ZIP codes from TCEQ layer."""
    print("Fetching Texas ZIP codes from TCEQ...")
    
    all_zips = {}
    offset = 0
    max_records = 1000
    
    while True:
        params = {
            'where': '1=1',
            'outFields': 'ZIP_CODE,PO_NAME',
            'returnGeometry': 'true',
            'f': 'json',
            'resultOffset': offset,
            'resultRecordCount': max_records
        }
        
        try:
            response = requests.get(ZIP_LAYER_URL, params=params, timeout=60)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            print(f"  Error fetching ZIPs: {e}")
            break
        
        features = data.get('features', [])
        if not features:
            break
        
        for f in features:
            attrs = f.get('attributes', {})
            zip_code = str(attrs.get('ZIP_CODE', ''))
            if zip_code and len(zip_code) == 5:
                all_zips[zip_code] = {
                    'name': attrs.get('PO_NAME', ''),
                    'geometry': f.get('geometry')
                }
        
        print(f"  Fetched {len(all_zips)} ZIPs...")
        
        if len(features) < max_records:
            break
        offset += max_records
    
    print(f"  Total: {len(all_zips)} Texas ZIP codes")
    return all_zips


def point_in_ring(point: tuple, ring: list) -> bool:
    """Check if a point is inside a polygon ring using ray casting."""
    x, y = point
    n = len(ring)
    inside = False
    
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    
    return inside


def polygons_intersect_simple(geom1: dict, geom2: dict) -> bool:
    """
    Simple check if two geometries might intersect.
    Uses bounding box check and centroid containment.
    """
    # Get rings from both geometries
    rings1 = geom1.get('rings', [])
    rings2 = geom2.get('rings', [])
    
    if not rings1 or not rings2:
        return False
    
    # Get bounding boxes
    def get_bbox(rings):
        all_points = [p for ring in rings for p in ring]
        if not all_points:
            return None
        xs = [p[0] for p in all_points]
        ys = [p[1] for p in all_points]
        return (min(xs), min(ys), max(xs), max(ys))
    
    bbox1 = get_bbox(rings1)
    bbox2 = get_bbox(rings2)
    
    if not bbox1 or not bbox2:
        return False
    
    # Check if bounding boxes intersect
    if (bbox1[2] < bbox2[0] or bbox1[0] > bbox2[2] or
        bbox1[3] < bbox2[1] or bbox1[1] > bbox2[3]):
        return False
    
    # Bounding boxes intersect - check if centroids are contained
    cx1 = (bbox1[0] + bbox1[2]) / 2
    cy1 = (bbox1[1] + bbox1[3]) / 2
    cx2 = (bbox2[0] + bbox2[2]) / 2
    cy2 = (bbox2[1] + bbox2[3]) / 2
    
    # Check if centroid of geom1 is in geom2
    for ring in rings2:
        if point_in_ring((cx1, cy1), ring):
            return True
    
    # Check if centroid of geom2 is in geom1
    for ring in rings1:
        if point_in_ring((cx2, cy2), ring):
            return True
    
    # Check if any vertex of geom1 is in geom2
    for ring1 in rings1:
        for point in ring1[:10]:  # Check first 10 points for speed
            for ring2 in rings2:
                if point_in_ring(point, ring2):
                    return True
    
    return False


def build_zip_index():
    """Build ZIP to district index."""
    # Load districts
    print(f"Loading districts from {DISTRICTS_FILE}...")
    with open(DISTRICTS_FILE, 'r') as f:
        districts = json.load(f)
    print(f"  Loaded {len(districts)} districts")
    
    # Get Texas ZIPs
    texas_zips = get_texas_zips()
    
    if not texas_zips:
        print("No ZIP data available. Using fallback method...")
        # Fallback: create index based on district properties if available
        return build_fallback_index(districts)
    
    # Build index
    print("\nBuilding ZIP to district index...")
    zip_to_districts: Dict[str, List[str]] = {}
    
    total = len(texas_zips)
    checked = 0
    
    for zip_code, zip_data in texas_zips.items():
        zip_geom = zip_data.get('geometry')
        if not zip_geom:
            continue
        
        matching_districts = []
        
        for district in districts:
            boundary = district.get('boundary', {})
            if boundary.get('type') != 'polygon':
                continue
            
            district_geom = boundary.get('data')
            if not district_geom:
                continue
            
            # Convert GeoJSON to ESRI format if needed
            if 'coordinates' in district_geom:
                # GeoJSON format - convert to rings
                coords = district_geom.get('coordinates', [])
                if district_geom.get('type') == 'Polygon':
                    district_geom = {'rings': coords}
                elif district_geom.get('type') == 'MultiPolygon':
                    # Flatten multipolygon
                    all_rings = []
                    for poly in coords:
                        all_rings.extend(poly)
                    district_geom = {'rings': all_rings}
            
            if polygons_intersect_simple(zip_geom, district_geom):
                matching_districts.append(district['district_id'])
        
        if matching_districts:
            zip_to_districts[zip_code] = matching_districts
        
        checked += 1
        if checked % 100 == 0:
            print(f"  Checked {checked}/{total} ZIPs, found {len(zip_to_districts)} with districts...")
    
    # Save index
    print(f"\nSaving index to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(zip_to_districts, f, indent=2)
    
    print(f"  Saved {len(zip_to_districts)} ZIP entries")
    
    # Print stats
    total_mappings = sum(len(v) for v in zip_to_districts.values())
    print(f"\nStatistics:")
    print(f"  ZIPs with districts: {len(zip_to_districts)}")
    print(f"  Total ZIP-district mappings: {total_mappings}")
    print(f"  Average districts per ZIP: {total_mappings / len(zip_to_districts):.1f}" if zip_to_districts else "  N/A")
    
    return zip_to_districts


def build_fallback_index(districts: list) -> Dict[str, List[str]]:
    """
    Build a simple index based on county if ZIP geometry isn't available.
    This is less accurate but better than nothing.
    """
    print("Building fallback county-based index...")
    
    # Group districts by county
    county_to_districts: Dict[str, List[str]] = {}
    for d in districts:
        county = d.get('county', '').upper()
        if county:
            if county not in county_to_districts:
                county_to_districts[county] = []
            county_to_districts[county].append(d['district_id'])
    
    print(f"  Found districts in {len(county_to_districts)} counties")
    
    # Save county index as fallback
    county_file = OUTPUT_FILE.replace('zip_to_district', 'county_to_district')
    with open(county_file, 'w') as f:
        json.dump(county_to_districts, f, indent=2)
    print(f"  Saved county index to {county_file}")
    
    return {}


if __name__ == '__main__':
    build_zip_index()
