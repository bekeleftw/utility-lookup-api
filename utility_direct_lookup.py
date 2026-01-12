#!/usr/bin/env python3
"""
Direct utility company API/website lookups.
Query utility companies directly to confirm if they serve an address.
This is the most authoritative source when available.
"""

import os
import re
import requests
from typing import Dict, Optional, List
from urllib.parse import quote


# Utility lookup endpoints and configurations
UTILITY_LOOKUP_CONFIGS = {
    # Electric Utilities
    "austin_energy": {
        "name": "Austin Energy",
        "type": "electric",
        "state": "TX",
        "method": "gis",
        "url": "https://services.arcgis.com/0L95CJ0VTaxqcmED/arcgis/rest/services/COA_Electric_Service_Area/FeatureServer/0/query",
        "params": lambda lat, lon: {
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "spatialRel": "esriSpatialRelIntersects",
            "returnGeometry": "false",
            "f": "json"
        }
    },
    "oncor": {
        "name": "Oncor Electric Delivery",
        "type": "electric",
        "state": "TX",
        "method": "gis",
        "url": "https://services.arcgis.com/jIL9msH9OI208GCb/arcgis/rest/services/Oncor_Service_Territory/FeatureServer/0/query",
        "params": lambda lat, lon: {
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "spatialRel": "esriSpatialRelIntersects",
            "returnGeometry": "false",
            "f": "json"
        }
    },
    "centerpoint_electric": {
        "name": "CenterPoint Energy",
        "type": "electric",
        "state": "TX",
        "method": "gis",
        "url": "https://services.arcgis.com/jIL9msH9OI208GCb/arcgis/rest/services/CenterPoint_Service_Territory/FeatureServer/0/query",
        "params": lambda lat, lon: {
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "spatialRel": "esriSpatialRelIntersects",
            "returnGeometry": "false",
            "f": "json"
        }
    },
    "ladwp": {
        "name": "Los Angeles Department of Water and Power",
        "type": "electric",
        "state": "CA",
        "method": "gis",
        "url": "https://services1.arcgis.com/RyKAc5Uc0JGfHnHU/arcgis/rest/services/LADWP_Service_Area/FeatureServer/0/query",
        "params": lambda lat, lon: {
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "spatialRel": "esriSpatialRelIntersects",
            "returnGeometry": "false",
            "f": "json"
        }
    },
    "sce": {
        "name": "Southern California Edison",
        "type": "electric",
        "state": "CA",
        "method": "gis",
        "url": "https://services.arcgis.com/jIL9msH9OI208GCb/arcgis/rest/services/SCE_Service_Territory/FeatureServer/0/query",
        "params": lambda lat, lon: {
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "spatialRel": "esriSpatialRelIntersects",
            "returnGeometry": "false",
            "f": "json"
        }
    },
    "pge": {
        "name": "Pacific Gas and Electric",
        "type": "electric",
        "state": "CA",
        "method": "gis",
        "url": "https://services.arcgis.com/jIL9msH9OI208GCb/arcgis/rest/services/PGE_Service_Territory/FeatureServer/0/query",
        "params": lambda lat, lon: {
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "spatialRel": "esriSpatialRelIntersects",
            "returnGeometry": "false",
            "f": "json"
        }
    },
    "sdge": {
        "name": "San Diego Gas & Electric",
        "type": "electric",
        "state": "CA",
        "method": "gis",
        "url": "https://services.arcgis.com/jIL9msH9OI208GCb/arcgis/rest/services/SDGE_Service_Territory/FeatureServer/0/query",
        "params": lambda lat, lon: {
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "spatialRel": "esriSpatialRelIntersects",
            "returnGeometry": "false",
            "f": "json"
        }
    },
    "aps": {
        "name": "Arizona Public Service",
        "type": "electric",
        "state": "AZ",
        "method": "gis",
        "url": "https://services.arcgis.com/jIL9msH9OI208GCb/arcgis/rest/services/APS_Service_Territory/FeatureServer/0/query",
        "params": lambda lat, lon: {
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "spatialRel": "esriSpatialRelIntersects",
            "returnGeometry": "false",
            "f": "json"
        }
    },
    "srp": {
        "name": "Salt River Project",
        "type": "electric",
        "state": "AZ",
        "method": "gis",
        "url": "https://services.arcgis.com/jIL9msH9OI208GCb/arcgis/rest/services/SRP_Service_Territory/FeatureServer/0/query",
        "params": lambda lat, lon: {
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "spatialRel": "esriSpatialRelIntersects",
            "returnGeometry": "false",
            "f": "json"
        }
    },
    
    # Gas Utilities
    "socalgas": {
        "name": "Southern California Gas Company",
        "type": "gas",
        "state": "CA",
        "method": "gis",
        "url": "https://services.arcgis.com/jIL9msH9OI208GCb/arcgis/rest/services/SoCalGas_Service_Territory/FeatureServer/0/query",
        "params": lambda lat, lon: {
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "spatialRel": "esriSpatialRelIntersects",
            "returnGeometry": "false",
            "f": "json"
        }
    },
    "southwest_gas": {
        "name": "Southwest Gas Corporation",
        "type": "gas",
        "state": "AZ",
        "method": "gis",
        "url": "https://services.arcgis.com/jIL9msH9OI208GCb/arcgis/rest/services/SWGas_Service_Territory/FeatureServer/0/query",
        "params": lambda lat, lon: {
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "spatialRel": "esriSpatialRelIntersects",
            "returnGeometry": "false",
            "f": "json"
        }
    },
    
    # Water Utilities
    "denver_water": {
        "name": "Denver Water",
        "type": "water",
        "state": "CO",
        "method": "gis",
        "url": "https://services.arcgis.com/jIL9msH9OI208GCb/arcgis/rest/services/DenverWater_Service_Area/FeatureServer/0/query",
        "params": lambda lat, lon: {
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "spatialRel": "esriSpatialRelIntersects",
            "returnGeometry": "false",
            "f": "json"
        }
    },
    "phoenix_water": {
        "name": "City of Phoenix Water Services",
        "type": "water",
        "state": "AZ",
        "method": "gis",
        "url": "https://services.arcgis.com/jIL9msH9OI208GCb/arcgis/rest/services/PhoenixWater_Service_Area/FeatureServer/0/query",
        "params": lambda lat, lon: {
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "spatialRel": "esriSpatialRelIntersects",
            "returnGeometry": "false",
            "f": "json"
        }
    },
}

# Map utility names to config keys
UTILITY_NAME_TO_KEY = {
    "austin energy": "austin_energy",
    "oncor": "oncor",
    "oncor electric": "oncor",
    "oncor electric delivery": "oncor",
    "centerpoint": "centerpoint_electric",
    "centerpoint energy": "centerpoint_electric",
    "ladwp": "ladwp",
    "la dwp": "ladwp",
    "los angeles department of water and power": "ladwp",
    "southern california edison": "sce",
    "sce": "sce",
    "pacific gas and electric": "pge",
    "pg&e": "pge",
    "pge": "pge",
    "san diego gas & electric": "sdge",
    "sdg&e": "sdge",
    "sdge": "sdge",
    "arizona public service": "aps",
    "aps": "aps",
    "salt river project": "srp",
    "srp": "srp",
    "southern california gas": "socalgas",
    "socalgas": "socalgas",
    "socal gas": "socalgas",
    "southwest gas": "southwest_gas",
    "sw gas": "southwest_gas",
    "denver water": "denver_water",
    "phoenix water": "phoenix_water",
    "city of phoenix water": "phoenix_water",
}


def _query_arcgis_service(url: str, params: Dict) -> Optional[bool]:
    """
    Query an ArcGIS service to check if point is in service area.
    Returns True if in area, False if not, None if error.
    """
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        features = data.get("features", [])
        return len(features) > 0
    except Exception as e:
        return None


def check_utility_serves_address(
    utility_name: str,
    lat: float,
    lon: float,
    utility_type: str = None
) -> Dict:
    """
    Check if a specific utility serves an address by querying their API/GIS.
    
    Args:
        utility_name: Name of the utility to check
        lat: Latitude of the address
        lon: Longitude of the address
        utility_type: Optional filter (electric, gas, water)
    
    Returns:
        Dict with confirmed status and metadata
    """
    # Normalize utility name
    normalized_name = utility_name.lower().strip()
    
    # Find config key
    config_key = UTILITY_NAME_TO_KEY.get(normalized_name)
    
    if not config_key:
        # Try partial match
        for name, key in UTILITY_NAME_TO_KEY.items():
            if name in normalized_name or normalized_name in name:
                config_key = key
                break
    
    if not config_key:
        return {
            "confirmed": None,
            "error": "Utility not in direct lookup database",
            "utility_name": utility_name
        }
    
    config = UTILITY_LOOKUP_CONFIGS.get(config_key)
    if not config:
        return {
            "confirmed": None,
            "error": "Config not found",
            "utility_name": utility_name
        }
    
    # Check type filter
    if utility_type and config.get("type") != utility_type:
        return {
            "confirmed": None,
            "error": f"Utility type mismatch: expected {utility_type}, got {config.get('type')}",
            "utility_name": utility_name
        }
    
    # Query the service
    if config.get("method") == "gis":
        params = config["params"](lat, lon)
        in_service_area = _query_arcgis_service(config["url"], params)
        
        if in_service_area is None:
            return {
                "confirmed": None,
                "error": "GIS query failed",
                "utility_name": config["name"],
                "source": "utility_direct_gis"
            }
        
        return {
            "confirmed": in_service_area,
            "utility_name": config["name"],
            "utility_type": config["type"],
            "source": "utility_direct_gis",
            "confidence_boost": 30 if in_service_area else 0,
            "confidence_penalty": -40 if not in_service_area else 0
        }
    
    return {
        "confirmed": None,
        "error": f"Unknown method: {config.get('method')}",
        "utility_name": utility_name
    }


def verify_utility_direct(
    suspected_utility: str,
    lat: float,
    lon: float,
    utility_type: str
) -> Optional[Dict]:
    """
    Verify a suspected utility by querying them directly.
    
    Args:
        suspected_utility: Name of utility we think serves this address
        lat: Latitude
        lon: Longitude
        utility_type: Type of utility (electric, gas, water)
    
    Returns:
        Verification result or None if utility not in direct lookup DB
    """
    result = check_utility_serves_address(
        suspected_utility, lat, lon, utility_type
    )
    
    if result.get("confirmed") is None:
        return None  # Couldn't verify
    
    return result


def find_serving_utility(
    lat: float,
    lon: float,
    state: str,
    utility_type: str
) -> Optional[Dict]:
    """
    Find which utility serves an address by querying all utilities for that state/type.
    
    Args:
        lat: Latitude
        lon: Longitude
        state: State abbreviation
        utility_type: Type of utility (electric, gas, water)
    
    Returns:
        Serving utility info or None
    """
    state = state.upper()
    
    # Find all utilities for this state and type
    candidates = []
    for key, config in UTILITY_LOOKUP_CONFIGS.items():
        if config.get("state") == state and config.get("type") == utility_type:
            candidates.append((key, config))
    
    if not candidates:
        return None
    
    # Query each one
    for key, config in candidates:
        if config.get("method") == "gis":
            params = config["params"](lat, lon)
            in_service_area = _query_arcgis_service(config["url"], params)
            
            if in_service_area:
                return {
                    "utility_name": config["name"],
                    "utility_key": key,
                    "utility_type": utility_type,
                    "source": "utility_direct_gis",
                    "confidence": "verified"
                }
    
    return None


def get_available_utilities(state: str = None, utility_type: str = None) -> List[Dict]:
    """
    Get list of utilities available for direct lookup.
    
    Args:
        state: Optional state filter
        utility_type: Optional type filter
    
    Returns:
        List of utility configs
    """
    results = []
    
    for key, config in UTILITY_LOOKUP_CONFIGS.items():
        if state and config.get("state") != state.upper():
            continue
        if utility_type and config.get("type") != utility_type:
            continue
        
        results.append({
            "key": key,
            "name": config["name"],
            "type": config["type"],
            "state": config["state"],
            "method": config["method"]
        })
    
    return results


if __name__ == "__main__":
    print("Utility Direct Lookup - Available Utilities:")
    print("=" * 60)
    
    for state in ["TX", "CA", "AZ", "CO"]:
        print(f"\n{state}:")
        utilities = get_available_utilities(state=state)
        for u in utilities:
            print(f"  - {u['name']} ({u['type']})")
    
    print("\n" + "=" * 60)
    print("Total utilities with direct lookup:", len(UTILITY_LOOKUP_CONFIGS))
