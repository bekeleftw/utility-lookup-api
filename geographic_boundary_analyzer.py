#!/usr/bin/env python3
"""
Geographic Boundary Analyzer

Uses geocoded tenant addresses to:
1. Find lat/lon boundaries where utilities change
2. Detect clusters of agreement/disagreement with GIS
3. Identify edge cases where tenant data contradicts GIS

This runs AFTER geocoding and produces actionable boundary rules.
"""

import json
import os
import re
import requests
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from math import radians, sin, cos, sqrt, atan2
import statistics

from utility_name_normalizer import normalize_utility_name, utilities_match


@dataclass
class GeoPoint:
    lat: float
    lon: float
    address: str
    tenant_utility: str
    gis_utility: Optional[str] = None
    agrees_with_gis: Optional[bool] = None


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in miles between two lat/lon points."""
    R = 3959  # Earth's radius in miles
    
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    
    return R * c


def lookup_gis_utility(lat: float, lon: float, state: str) -> Optional[str]:
    """
    Query our GIS sources to get the utility at a lat/lon.
    Uses the existing lookup infrastructure.
    """
    try:
        from gis_lookup import lookup_electric_utility_gis
        result = lookup_electric_utility_gis(lat, lon, state)
        if result and result.get('name'):
            return normalize_utility_name(result['name'])
    except ImportError:
        pass
    except Exception as e:
        pass
    return None


def load_geocoded_addresses(filepath: str = 'data/tenant_addresses_geocoded.json', utility_type: str = 'electric') -> List[GeoPoint]:
    """Load geocoded addresses from JSON file for a specific utility type."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Geocoded data not found: {filepath}")
    
    with open(filepath, 'r') as f:
        data = json.load(f)
    
    # Map utility type to field name
    field_map = {
        'electric': 'electricity',
        'gas': 'gas',
        'water': 'water'
    }
    field = field_map.get(utility_type, 'electricity')
    
    points = []
    for addr in data.get('addresses', []):
        if addr.get('lat') and addr.get('lon'):
            utility_value = addr.get(field, '')
            if utility_value:  # Only include if utility data exists
                points.append(GeoPoint(
                    lat=addr['lat'],
                    lon=addr['lon'],
                    address=addr['address'],
                    tenant_utility=normalize_utility_name(utility_value)
                ))
    
    return points


def group_by_zip(points: List[GeoPoint]) -> Dict[str, List[GeoPoint]]:
    """Group points by ZIP code."""
    by_zip = defaultdict(list)
    for p in points:
        zip_match = re.search(r'(\d{5})', p.address)
        if zip_match:
            by_zip[zip_match.group(1)].append(p)
    return dict(by_zip)


def find_utility_clusters(points: List[GeoPoint], max_distance_miles: float = 0.5) -> List[Dict]:
    """
    Find geographic clusters of addresses with the same utility.
    
    Returns clusters with center point, radius, and utility.
    """
    if not points:
        return []
    
    # Group by utility
    by_utility = defaultdict(list)
    for p in points:
        if p.tenant_utility:
            by_utility[p.tenant_utility].append(p)
    
    clusters = []
    
    for utility, util_points in by_utility.items():
        if len(util_points) < 2:
            continue
        
        # Calculate centroid
        avg_lat = statistics.mean(p.lat for p in util_points)
        avg_lon = statistics.mean(p.lon for p in util_points)
        
        # Calculate max distance from centroid
        max_dist = max(
            haversine_distance(avg_lat, avg_lon, p.lat, p.lon)
            for p in util_points
        )
        
        clusters.append({
            'utility': utility,
            'center_lat': avg_lat,
            'center_lon': avg_lon,
            'radius_miles': max_dist,
            'point_count': len(util_points),
            'points': util_points
        })
    
    return clusters


def find_boundary_line(points: List[GeoPoint]) -> Optional[Dict]:
    """
    Try to find a lat or lon line that separates utilities.
    
    For example: "Utility A is north of lat 35.5, Utility B is south"
    """
    if len(points) < 4:
        return None
    
    # Get unique utilities
    utilities = list(set(p.tenant_utility for p in points if p.tenant_utility))
    if len(utilities) != 2:
        return None  # Only works for 2-utility splits
    
    util_a, util_b = utilities
    points_a = [p for p in points if p.tenant_utility == util_a]
    points_b = [p for p in points if p.tenant_utility == util_b]
    
    if len(points_a) < 2 or len(points_b) < 2:
        return None
    
    # Try latitude boundary
    avg_lat_a = statistics.mean(p.lat for p in points_a)
    avg_lat_b = statistics.mean(p.lat for p in points_b)
    
    if abs(avg_lat_a - avg_lat_b) > 0.005:  # ~0.3 miles difference
        boundary_lat = (avg_lat_a + avg_lat_b) / 2
        
        # Check how well this boundary separates them
        a_north = sum(1 for p in points_a if p.lat > boundary_lat)
        a_south = len(points_a) - a_north
        b_north = sum(1 for p in points_b if p.lat > boundary_lat)
        b_south = len(points_b) - b_north
        
        # If one utility is mostly north and other mostly south
        if (a_north > a_south * 2 and b_south > b_north * 2) or \
           (a_south > a_north * 2 and b_north > b_south * 2):
            north_util = util_a if a_north > a_south else util_b
            south_util = util_b if north_util == util_a else util_a
            
            return {
                'type': 'latitude',
                'boundary_value': boundary_lat,
                'north_utility': north_util,
                'south_utility': south_util,
                'confidence': min(a_north + b_south, a_south + b_north) / len(points),
                'description': f"North of {boundary_lat:.4f}: {north_util}, South: {south_util}"
            }
    
    # Try longitude boundary
    avg_lon_a = statistics.mean(p.lon for p in points_a)
    avg_lon_b = statistics.mean(p.lon for p in points_b)
    
    if abs(avg_lon_a - avg_lon_b) > 0.005:
        boundary_lon = (avg_lon_a + avg_lon_b) / 2
        
        a_east = sum(1 for p in points_a if p.lon > boundary_lon)
        a_west = len(points_a) - a_east
        b_east = sum(1 for p in points_b if p.lon > boundary_lon)
        b_west = len(points_b) - b_east
        
        if (a_east > a_west * 2 and b_west > b_east * 2) or \
           (a_west > a_east * 2 and b_east > b_west * 2):
            east_util = util_a if a_east > a_west else util_b
            west_util = util_b if east_util == util_a else util_a
            
            return {
                'type': 'longitude',
                'boundary_value': boundary_lon,
                'east_utility': east_util,
                'west_utility': west_util,
                'confidence': min(a_east + b_west, a_west + b_east) / len(points),
                'description': f"East of {boundary_lon:.4f}: {east_util}, West: {west_util}"
            }
    
    return None


def validate_against_gis(points: List[GeoPoint], sample_size: int = 50) -> Dict:
    """
    Compare tenant-reported utilities against GIS data.
    
    Returns agreement/disagreement stats and specific disagreements.
    """
    import random
    
    # Sample if too many points
    if len(points) > sample_size:
        sample = random.sample(points, sample_size)
    else:
        sample = points
    
    results = {
        'total_checked': 0,
        'agreements': 0,
        'disagreements': 0,
        'gis_unavailable': 0,
        'disagreement_details': []
    }
    
    for point in sample:
        # Extract state from address
        state_match = re.search(r',\s*([A-Z]{2})\s+\d{5}', point.address)
        if not state_match:
            continue
        state = state_match.group(1)
        
        gis_utility = lookup_gis_utility(point.lat, point.lon, state)
        
        if not gis_utility:
            results['gis_unavailable'] += 1
            continue
        
        results['total_checked'] += 1
        point.gis_utility = gis_utility
        
        if utilities_match(point.tenant_utility, gis_utility):
            results['agreements'] += 1
            point.agrees_with_gis = True
        else:
            results['disagreements'] += 1
            point.agrees_with_gis = False
            results['disagreement_details'].append({
                'address': point.address,
                'lat': point.lat,
                'lon': point.lon,
                'tenant_says': point.tenant_utility,
                'gis_says': gis_utility
            })
    
    if results['total_checked'] > 0:
        results['agreement_rate'] = results['agreements'] / results['total_checked']
    else:
        results['agreement_rate'] = None
    
    return results


def analyze_zip_geography(zip_code: str, points: List[GeoPoint]) -> Dict:
    """
    Full geographic analysis for a single ZIP.
    """
    result = {
        'zip_code': zip_code,
        'point_count': len(points),
        'utilities': {},
        'clusters': [],
        'boundary': None,
        'gis_validation': None
    }
    
    # Count utilities
    for p in points:
        if p.tenant_utility:
            result['utilities'][p.tenant_utility] = result['utilities'].get(p.tenant_utility, 0) + 1
    
    # Only analyze if multiple utilities
    if len(result['utilities']) < 2:
        result['analysis'] = 'single_utility'
        return result
    
    # Find clusters
    result['clusters'] = find_utility_clusters(points)
    
    # Try to find boundary line
    result['boundary'] = find_boundary_line(points)
    
    # Validate against GIS (sample)
    result['gis_validation'] = validate_against_gis(points, sample_size=20)
    
    return result


def run_full_analysis(geocoded_file: str = 'data/tenant_addresses_geocoded.json', utility_type: str = 'electric') -> Dict:
    """
    Run full geographic analysis on all geocoded addresses.
    """
    print("="*60)
    print("GEOGRAPHIC BOUNDARY ANALYSIS")
    print("="*60)
    
    # Load data
    print(f"\nLoading geocoded addresses from {geocoded_file} for {utility_type}...")
    points = load_geocoded_addresses(geocoded_file, utility_type=utility_type)
    print(f"Loaded {len(points):,} geocoded addresses")
    
    # Group by ZIP
    by_zip = group_by_zip(points)
    print(f"Spanning {len(by_zip)} ZIP codes")
    
    # Find ZIPs with multiple utilities
    multi_util_zips = {
        z: pts for z, pts in by_zip.items()
        if len(set(p.tenant_utility for p in pts if p.tenant_utility)) >= 2
    }
    print(f"Found {len(multi_util_zips)} ZIPs with multiple utilities")
    
    # Analyze each
    results = {
        'total_zips': len(by_zip),
        'multi_utility_zips': len(multi_util_zips),
        'boundaries_found': 0,
        'gis_agreement_rate': None,
        'zip_analyses': []
    }
    
    all_agreements = 0
    all_checked = 0
    
    print(f"\nAnalyzing {len(multi_util_zips)} multi-utility ZIPs...")
    
    for i, (zip_code, pts) in enumerate(multi_util_zips.items()):
        analysis = analyze_zip_geography(zip_code, pts)
        results['zip_analyses'].append(analysis)
        
        if analysis.get('boundary'):
            results['boundaries_found'] += 1
        
        if analysis.get('gis_validation'):
            gv = analysis['gis_validation']
            all_agreements += gv.get('agreements', 0)
            all_checked += gv.get('total_checked', 0)
        
        if (i + 1) % 100 == 0:
            print(f"  Analyzed {i+1}/{len(multi_util_zips)} ZIPs...")
    
    if all_checked > 0:
        results['gis_agreement_rate'] = all_agreements / all_checked
    
    # Save results
    output_file = f'data/geographic_boundary_analysis_{utility_type}.json'
    with open(output_file, 'w') as f:
        # Convert to serializable format
        serializable = {
            'total_zips': results['total_zips'],
            'multi_utility_zips': results['multi_utility_zips'],
            'boundaries_found': results['boundaries_found'],
            'gis_agreement_rate': results['gis_agreement_rate'],
            'zip_analyses': [
                {
                    'zip_code': a['zip_code'],
                    'point_count': a['point_count'],
                    'utilities': a['utilities'],
                    'boundary': a['boundary'],
                    'gis_validation': {
                        k: v for k, v in (a.get('gis_validation') or {}).items()
                        if k != 'disagreement_details'
                    } if a.get('gis_validation') else None
                }
                for a in results['zip_analyses']
            ]
        }
        json.dump(serializable, f, indent=2)
    
    print(f"\n" + "="*60)
    print("ANALYSIS COMPLETE")
    print("="*60)
    print(f"Multi-utility ZIPs analyzed: {len(multi_util_zips)}")
    print(f"Geographic boundaries found: {results['boundaries_found']}")
    print(f"GIS agreement rate: {results['gis_agreement_rate']*100:.1f}%" if results['gis_agreement_rate'] else "GIS agreement rate: N/A")
    print(f"\nSaved to {output_file}")
    
    # Show sample boundaries
    print("\n" + "="*60)
    print("SAMPLE BOUNDARIES FOUND")
    print("="*60)
    for analysis in results['zip_analyses'][:10]:
        if analysis.get('boundary'):
            b = analysis['boundary']
            print(f"\nZIP {analysis['zip_code']}:")
            print(f"  {b['description']}")
            print(f"  Confidence: {b['confidence']*100:.0f}%")
    
    return results


def run_all_utility_types():
    """Run analysis for electric, gas, and water."""
    for utility_type in ['electric', 'gas', 'water']:
        print(f"\n{'='*60}")
        print(f"ANALYZING {utility_type.upper()}")
        print(f"{'='*60}")
        run_full_analysis(utility_type=utility_type)


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        utility_type = sys.argv[1]
        run_full_analysis(utility_type=utility_type)
    else:
        run_all_utility_types()
