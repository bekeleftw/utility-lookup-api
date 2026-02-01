#!/usr/bin/env python3
"""
Water utility lookup using state GIS APIs.

These supplement the existing EPA SDWIS data with authoritative state-level
service area boundaries.

Data Sources:
- Texas PUC Water CCN (Certificate of Convenience and Necessity)
- New Jersey DEP Water Purveyors
- Florida DOH FLWMI (Drinking Water field)
"""

import requests
from typing import Optional, Dict
import math

from logging_config import get_logger
logger = get_logger("water_gis_lookup")

# Texas PUC Water CCN endpoint
TX_WATER_CCN_URL = "https://services6.arcgis.com/N6Lzvtb46cpxThhu/ArcGIS/rest/services/Water_CCN_Service_Areas/FeatureServer/210/query"

# New Jersey DEP Water Purveyors
NJ_WATER_PURVEYOR_URL = "https://mapsdep.nj.gov/arcgis/rest/services/Features/Utilities/MapServer/13/query"

# Florida DOH FLWMI (same endpoint as sewer, different fields)
FL_FLWMI_URL = "https://gis.floridahealth.gov/server/rest/services/FLWMI/FLWMI_Wastewater/MapServer/0/query"

# Cache
_water_cache = {}


def wgs84_to_web_mercator(lon: float, lat: float) -> tuple:
    """Convert WGS84 (EPSG:4326) to Web Mercator (EPSG:3857)."""
    x = lon * 20037508.34 / 180
    y = math.log(math.tan((90 + lat) * math.pi / 360)) / (math.pi / 180)
    y = y * 20037508.34 / 180
    return x, y


def lookup_texas_water_ccn(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Texas PUC Water CCN service areas by coordinates.
    Returns the water utility with CCN that serves the given location.
    """
    cache_key = f"tx_water|{lat:.4f}|{lon:.4f}"
    if cache_key in _water_cache:
        return _water_cache[cache_key]
    
    try:
        params = {
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "CCN_NO,UTILITY,DBA_NAME,COUNTY,STATUS,CCN_TYPE",
            "returnGeometry": "false",
            "f": "json"
        }
        
        response = requests.get(TX_WATER_CCN_URL, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        features = data.get("features", [])
        
        if not features:
            _water_cache[cache_key] = None
            return None
        
        attrs = features[0].get("attributes", {})
        
        # Determine confidence based on CCN_TYPE
        ccn_type = attrs.get("CCN_TYPE", "")
        if "Bounded Service Area" in ccn_type:
            confidence = "high"
        elif "Facilities +200 Feet" in ccn_type:
            confidence = "medium"
        else:
            confidence = "medium"
        
        # Use DBA_NAME if available and not "NA", otherwise use UTILITY
        dba_name = attrs.get("DBA_NAME", "")
        utility_name = attrs.get("UTILITY", "Unknown")
        display_name = utility_name if (not dba_name or dba_name.upper() == "NA") else dba_name
        
        result = {
            "NAME": display_name,
            "legal_name": utility_name,
            "ccn_number": attrs.get("CCN_NO"),
            "ccn_type": ccn_type,
            "county": attrs.get("COUNTY"),
            "TELEPHONE": None,
            "WEBSITE": None,
            "_source": "texas_puc_water_ccn",
            "_confidence": confidence,
            "_note": f"Texas PUC Water CCN #{attrs.get('CCN_NO')} - {ccn_type}"
        }
        
        _water_cache[cache_key] = result
        return result
        
    except Exception as e:
        logger.error("TX Water CCN lookup error", extra={"endpoint": "texas_puc_water_ccn", "error": str(e)})
        return None


def lookup_new_jersey_water_purveyor(lat: float, lon: float) -> Optional[Dict]:
    """
    Query New Jersey DEP Water Purveyors by coordinates.
    Returns the water utility serving the given location.
    """
    cache_key = f"nj_water|{lat:.4f}|{lon:.4f}"
    if cache_key in _water_cache:
        return _water_cache[cache_key]
    
    try:
        params = {
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "SYS_NAME,PWID,AGENCY_URL,AREA_TYPE",
            "returnGeometry": "false",
            "f": "json"
        }
        
        response = requests.get(NJ_WATER_PURVEYOR_URL, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        features = data.get("features", [])
        
        if not features:
            _water_cache[cache_key] = None
            return None
        
        attrs = features[0].get("attributes", {})
        sys_name = attrs.get("SYS_NAME", "")
        
        if not sys_name:
            _water_cache[cache_key] = None
            return None
        
        result = {
            "NAME": sys_name,
            "PWSID": attrs.get("PWID"),
            "WEBSITE": attrs.get("AGENCY_URL"),
            "TELEPHONE": None,
            "_source": "new_jersey_dep_water",
            "_confidence": "high",
            "_note": f"NJ DEP Water Purveyor - {sys_name}"
        }
        
        _water_cache[cache_key] = result
        return result
        
    except Exception as e:
        logger.error("NJ Water Purveyor lookup error", extra={"endpoint": "new_jersey_dep_water", "error": str(e)})
        return None


def lookup_florida_water_flwmi(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Florida DOH FLWMI for drinking water data.
    Returns the water utility serving the given location.
    """
    cache_key = f"fl_water|{lat:.4f}|{lon:.4f}"
    if cache_key in _water_cache:
        return _water_cache[cache_key]
    
    try:
        # Convert to Web Mercator (EPSG:3857) - required by this service
        x, y = wgs84_to_web_mercator(lon, lat)
        
        params = {
            "geometry": f"{x},{y}",
            "geometryType": "esriGeometryPoint",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "DW,DW_SRC_NAME",
            "returnGeometry": "false",
            "f": "json"
        }
        
        response = requests.get(FL_FLWMI_URL, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        features = data.get("features", [])
        
        if not features:
            _water_cache[cache_key] = None
            return None
        
        attrs = features[0].get("attributes", {})
        dw_status = attrs.get("DW", "")
        dw_source = attrs.get("DW_SRC_NAME", "")
        
        # Map DW status to confidence
        confidence_map = {
            "KnownPublic": "high",
            "LikelyPublic": "medium",
            "SomewhatLikelyPublic": "low",
            "KnownWell": "high",  # Private well
            "LikelyWell": "medium",
            "Unknown": "low"
        }
        
        # Check if private well
        is_well = "Well" in dw_status
        
        if is_well:
            result = {
                "NAME": "Private Well",
                "status": dw_status,
                "TELEPHONE": None,
                "WEBSITE": None,
                "_source": "florida_flwmi",
                "_confidence": confidence_map.get(dw_status, "low"),
                "_note": f"Florida DOH indicates {dw_status} - no public water service"
            }
        else:
            # Extract provider name from source (format: "PWSID - NAME ...")
            provider_name = dw_source
            if " - " in dw_source:
                parts = dw_source.split(" - ", 1)
                if len(parts) > 1:
                    # Extract just the utility name, remove the method description
                    name_part = parts[1].strip()
                    # Remove trailing method info like "Water meter or service point..."
                    for sep in ["Water meter", "Service point", "within"]:
                        if sep in name_part:
                            name_part = name_part.split(sep)[0].strip()
                    provider_name = name_part if name_part else dw_source
            
            if not provider_name or provider_name == "Unknown":
                provider_name = "Public Water Service"
            
            result = {
                "NAME": provider_name,
                "status": dw_status,
                "TELEPHONE": None,
                "WEBSITE": None,
                "_source": "florida_flwmi",
                "_confidence": confidence_map.get(dw_status, "medium"),
                "_note": f"Florida DOH FLWMI: {dw_status}"
            }
        
        _water_cache[cache_key] = result
        return result
        
    except Exception as e:
        logger.error("FL FLWMI water lookup error", extra={"endpoint": "florida_flwmi", "error": str(e)})
        return None


def lookup_state_water_gis(lat: float, lon: float, state: str) -> Optional[Dict]:
    """
    Main entry point for state GIS water lookups.
    Returns water utility data from state-specific GIS APIs.
    
    This should be called BEFORE EPA SDWIS for these states to get
    more accurate service area data.
    """
    state_upper = state.upper() if state else ""
    
    if state_upper == "TX":
        return lookup_texas_water_ccn(lat, lon)
    elif state_upper == "NJ":
        return lookup_new_jersey_water_purveyor(lat, lon)
    elif state_upper == "FL":
        return lookup_florida_water_flwmi(lat, lon)
    
    return None


# Test function
if __name__ == "__main__":
    print("=== Texas Water CCN ===")
    result = lookup_texas_water_ccn(30.5170, -97.6825)  # Round Rock
    print(f"Round Rock: {result.get('NAME') if result else 'Not found'}")
    
    print("\n=== New Jersey Water Purveyor ===")
    result = lookup_new_jersey_water_purveyor(40.2171, -74.7429)  # Trenton
    print(f"Trenton: {result.get('NAME') if result else 'Not found'}")
    
    print("\n=== Florida FLWMI Water ===")
    result = lookup_florida_water_flwmi(28.5383, -81.3789)  # Orlando
    print(f"Orlando: {result.get('NAME') if result else 'Not found'}")
