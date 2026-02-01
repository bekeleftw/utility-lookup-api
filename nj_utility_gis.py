#!/usr/bin/env python3
"""
New Jersey utility lookups using NJ DEP MapServer.

Covers all utility types from a single authoritative source:
- Layer 8: Sewer Service Areas
- Layer 10: Electric Utilities Territory
- Layer 11: Gas Utilities Territory  
- Layer 13: Water Purveyors

Source: https://mapsdep.nj.gov/arcgis/rest/services/Features/Utilities/MapServer
"""

import requests
from typing import Optional, Dict

from logging_config import get_logger
logger = get_logger("nj_utility_gis")

# NJ DEP MapServer base URL
NJ_MAPSERVER_BASE = "https://mapsdep.nj.gov/arcgis/rest/services/Features/Utilities/MapServer"

# Layer IDs
NJ_ELECTRIC_LAYER = 10
NJ_GAS_LAYER = 11

# Cache
_nj_cache = {}


def lookup_nj_electric(lat: float, lon: float) -> Optional[Dict]:
    """
    Query NJ DEP Electric Utilities Territory Map.
    Returns the electric utility serving the given location.
    """
    cache_key = f"nj_electric|{lat:.4f}|{lon:.4f}"
    if cache_key in _nj_cache:
        return _nj_cache[cache_key]
    
    try:
        url = f"{NJ_MAPSERVER_BASE}/{NJ_ELECTRIC_LAYER}/query"
        params = {
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "NAME,LABEL,TYPE,PARENT",
            "returnGeometry": "false",
            "f": "json"
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        features = data.get("features", [])
        
        if not features:
            _nj_cache[cache_key] = None
            return None
        
        attrs = features[0].get("attributes", {})
        name = attrs.get("NAME", "")
        label = attrs.get("LABEL", "")
        utility_type = attrs.get("TYPE", "")
        parent = attrs.get("PARENT", "")
        
        if not name:
            _nj_cache[cache_key] = None
            return None
        
        result = {
            "NAME": name,
            "label": label,
            "utility_type": utility_type,
            "parent_company": parent,
            "TELEPHONE": None,
            "WEBSITE": None,
            "STATE": "NJ",
            "_source": "new_jersey_dep_electric",
            "_confidence": "high",
            "_note": f"NJ DEP Electric Territory - {label or name}"
        }
        
        _nj_cache[cache_key] = result
        return result
        
    except Exception as e:
        logger.error("NJ Electric lookup error", extra={"endpoint": "new_jersey_dep_electric", "error": str(e)})
        return None


def lookup_nj_gas(lat: float, lon: float) -> Optional[Dict]:
    """
    Query NJ DEP Gas Utilities Territory Map.
    Returns the gas utility serving the given location.
    """
    cache_key = f"nj_gas|{lat:.4f}|{lon:.4f}"
    if cache_key in _nj_cache:
        return _nj_cache[cache_key]
    
    try:
        url = f"{NJ_MAPSERVER_BASE}/{NJ_GAS_LAYER}/query"
        params = {
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "NAME,LABEL",
            "returnGeometry": "false",
            "f": "json"
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        features = data.get("features", [])
        
        if not features:
            _nj_cache[cache_key] = None
            return None
        
        attrs = features[0].get("attributes", {})
        name = attrs.get("NAME", "")
        label = attrs.get("LABEL", "")
        
        if not name:
            _nj_cache[cache_key] = None
            return None
        
        result = {
            "NAME": name,
            "label": label,
            "TELEPHONE": None,
            "WEBSITE": None,
            "STATE": "NJ",
            "_source": "new_jersey_dep_gas",
            "_confidence": "high",
            "_note": f"NJ DEP Gas Territory - {label or name}"
        }
        
        _nj_cache[cache_key] = result
        return result
        
    except Exception as e:
        logger.error("NJ Gas lookup error", extra={"endpoint": "new_jersey_dep_gas", "error": str(e)})
        return None


# Test function
if __name__ == "__main__":
    print("=== NJ Electric ===")
    result = lookup_nj_electric(40.2171, -74.7429)  # Trenton
    print(f"Trenton: {result.get('NAME') if result else 'Not found'} ({result.get('label') if result else ''})")
    
    print("\n=== NJ Gas ===")
    result = lookup_nj_gas(40.2171, -74.7429)  # Trenton
    print(f"Trenton: {result.get('NAME') if result else 'Not found'} ({result.get('label') if result else ''})")
