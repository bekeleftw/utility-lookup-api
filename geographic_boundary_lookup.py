#!/usr/bin/env python3
"""
Geographic Boundary Lookup

Uses lat/lon boundaries from tenant data analysis to determine utilities
based on geographic position within a ZIP code.

Integrates with the main lookup pipeline as an additional data source.
"""

import json
import os
from typing import Dict, Optional, Tuple

# Cache for boundary data (by utility type)
_boundary_cache: Dict[str, Dict] = {}
_geocoded_cache: Dict[str, Dict] = {}


def load_boundary_data(utility_type: str = 'electric') -> Dict:
    """Load geographic boundary analysis data for a specific utility type."""
    global _boundary_cache
    
    if utility_type in _boundary_cache:
        return _boundary_cache[utility_type]
    
    filepath = os.path.join(os.path.dirname(__file__), 'data', f'geographic_boundary_analysis_{utility_type}.json')
    
    if not os.path.exists(filepath):
        _boundary_cache[utility_type] = {}
        return _boundary_cache[utility_type]
    
    with open(filepath, 'r') as f:
        data = json.load(f)
    
    # Index by ZIP code for fast lookup
    _boundary_cache[utility_type] = {}
    for analysis in data.get('zip_analyses', []):
        zip_code = analysis.get('zip_code')
        if zip_code and analysis.get('boundary'):
            _boundary_cache[utility_type][zip_code] = analysis
    
    return _boundary_cache[utility_type]


def load_geocoded_addresses() -> Dict:
    """Load geocoded address data for nearby address lookup."""
    global _geocoded_cache
    
    if _geocoded_cache is not None:
        return _geocoded_cache
    
    filepath = os.path.join(os.path.dirname(__file__), 'data', 'tenant_addresses_geocoded.json')
    
    if not os.path.exists(filepath):
        _geocoded_cache = {}
        return _geocoded_cache
    
    with open(filepath, 'r') as f:
        data = json.load(f)
    
    # Index by ZIP code
    _geocoded_cache = {}
    import re
    for addr in data.get('addresses', []):
        if addr.get('lat') and addr.get('lon'):
            zip_match = re.search(r'(\d{5})', addr.get('address', ''))
            if zip_match:
                zip_code = zip_match.group(1)
                if zip_code not in _geocoded_cache:
                    _geocoded_cache[zip_code] = []
                _geocoded_cache[zip_code].append(addr)
    
    return _geocoded_cache


def check_geographic_boundary(
    zip_code: str,
    lat: float,
    lon: float,
    utility_type: str = 'electric'
) -> Optional[Dict]:
    """
    Check if a lat/lon falls on a known utility boundary.
    
    Returns utility suggestion based on geographic position.
    """
    boundaries = load_boundary_data(utility_type)
    
    if zip_code not in boundaries:
        return None
    
    analysis = boundaries[zip_code]
    boundary = analysis.get('boundary')
    
    if not boundary:
        return None
    
    boundary_type = boundary.get('type')
    boundary_value = boundary.get('boundary_value')
    confidence = boundary.get('confidence', 0)
    
    # Determine which side of the boundary
    if boundary_type == 'latitude':
        if lat > boundary_value:
            utility = boundary.get('north_utility')
            position = 'north'
        else:
            utility = boundary.get('south_utility')
            position = 'south'
    elif boundary_type == 'longitude':
        if lon > boundary_value:
            utility = boundary.get('east_utility')
            position = 'east'
        else:
            utility = boundary.get('west_utility')
            position = 'west'
    else:
        return None
    
    return {
        'utility': utility,
        'confidence': confidence,
        'boundary_type': boundary_type,
        'boundary_value': boundary_value,
        'position': position,
        'description': boundary.get('description'),
        'source': 'geographic_boundary'
    }


def find_nearby_verified_addresses(
    zip_code: str,
    lat: float,
    lon: float,
    max_distance_miles: float = 0.5,
    limit: int = 5,
    utility_type: str = 'electric'
) -> list:
    """
    Find tenant-verified addresses near a given lat/lon.
    
    Returns list of nearby addresses with their utilities.
    """
    from math import radians, sin, cos, sqrt, atan2
    
    def haversine(lat1, lon1, lat2, lon2):
        R = 3959  # Earth radius in miles
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat, dlon = lat2 - lat1, lon2 - lon1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        return R * 2 * atan2(sqrt(a), sqrt(1-a))
    
    # Map utility type to field name
    field_map = {'electric': 'electricity', 'gas': 'gas', 'water': 'water'}
    field = field_map.get(utility_type, 'electricity')
    
    geocoded = load_geocoded_addresses()
    
    if zip_code not in geocoded:
        return []
    
    nearby = []
    for addr in geocoded[zip_code]:
        addr_lat = addr.get('lat')
        addr_lon = addr.get('lon')
        utility_value = addr.get(field)
        if addr_lat and addr_lon and utility_value:
            distance = haversine(lat, lon, addr_lat, addr_lon)
            if distance <= max_distance_miles:
                nearby.append({
                    'address': addr.get('address'),
                    'utility': utility_value,
                    'distance_miles': round(distance, 3),
                    'lat': addr_lat,
                    'lon': addr_lon
                })
    
    # Sort by distance
    nearby.sort(key=lambda x: x['distance_miles'])
    return nearby[:limit]


def get_utility_from_nearby_consensus(
    zip_code: str,
    lat: float,
    lon: float,
    max_distance_miles: float = 0.25,
    utility_type: str = 'electric'
) -> Optional[Dict]:
    """
    Get utility based on consensus of nearby verified addresses.
    
    Only returns if there's strong agreement among nearby addresses.
    """
    nearby = find_nearby_verified_addresses(zip_code, lat, lon, max_distance_miles, limit=10, utility_type=utility_type)
    
    if len(nearby) < 3:  # Require at least 3 samples to avoid flukes
        return None
    
    # Count utilities
    utility_counts = {}
    for addr in nearby:
        util = addr.get('utility')
        if util:
            utility_counts[util] = utility_counts.get(util, 0) + 1
    
    if not utility_counts:
        return None
    
    # Find dominant utility
    total = sum(utility_counts.values())
    best_utility = max(utility_counts, key=utility_counts.get)
    best_count = utility_counts[best_utility]
    
    # Require 70%+ agreement
    agreement_rate = best_count / total
    if agreement_rate < 0.7:
        return None
    
    avg_distance = sum(a['distance_miles'] for a in nearby) / len(nearby)
    
    return {
        'utility': best_utility,
        'confidence': agreement_rate,
        'nearby_count': len(nearby),
        'agreement_count': best_count,
        'avg_distance_miles': round(avg_distance, 3),
        'source': 'nearby_consensus'
    }


def get_geographic_context_for_ai(zip_code: str, utility_type: str = 'electric') -> Optional[str]:
    """
    Get geographic boundary context for AI smart selector prompt.
    """
    boundaries = load_boundary_data(utility_type)
    
    if zip_code not in boundaries:
        return None
    
    analysis = boundaries[zip_code]
    boundary = analysis.get('boundary')
    utilities = analysis.get('utilities', {})
    
    if not boundary and len(utilities) < 2:
        return None
    
    lines = [f"GEOGRAPHIC ANALYSIS for ZIP {zip_code} ({utility_type}):"]
    
    # List utilities found
    if utilities:
        sorted_utils = sorted(utilities.items(), key=lambda x: -x[1])
        util_str = ", ".join(f"{u} ({c} addresses)" for u, c in sorted_utils[:4])
        lines.append(f"- Tenant-verified utilities: {util_str}")
    
    # Boundary info
    if boundary:
        lines.append(f"- Geographic boundary detected: {boundary['description']}")
        lines.append(f"- Boundary confidence: {boundary['confidence']*100:.0f}%")
    
    return "\n".join(lines)


# Quick test
if __name__ == '__main__':
    print("Loading boundary data...")
    boundaries = load_boundary_data()
    print(f"Loaded {len(boundaries)} ZIPs with boundaries")
    
    print("\nLoading geocoded addresses...")
    geocoded = load_geocoded_addresses()
    total_addrs = sum(len(v) for v in geocoded.values())
    print(f"Loaded {total_addrs} addresses across {len(geocoded)} ZIPs")
    
    # Test a boundary lookup
    if boundaries:
        test_zip = list(boundaries.keys())[0]
        print(f"\nTest boundary lookup for ZIP {test_zip}:")
        # Use a test lat/lon
        result = check_geographic_boundary(test_zip, 35.0, -80.0)
        print(f"  Result: {result}")
    
    # Test nearby lookup
    if geocoded:
        test_zip = list(geocoded.keys())[0]
        if geocoded[test_zip]:
            test_addr = geocoded[test_zip][0]
            print(f"\nTest nearby lookup for ZIP {test_zip}:")
            nearby = find_nearby_verified_addresses(
                test_zip, 
                test_addr['lat'], 
                test_addr['lon'],
                max_distance_miles=1.0
            )
            print(f"  Found {len(nearby)} nearby addresses")
            for n in nearby[:3]:
                print(f"    {n['distance_miles']}mi: {n['utility']}")
