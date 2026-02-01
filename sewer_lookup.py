#!/usr/bin/env python3
"""
Sewer/wastewater utility lookup using multiple data sources.

Data Source Hierarchy:
1. Texas PUC Sewer CCN API (authoritative for TX)
2. HIFLD Wastewater Treatment Plants (national fallback)
3. CSV providers database
4. Municipal water inference (last resort)

Based on: sewer-utility-lookup-spec.md
"""

import requests
from typing import Optional, Dict, List
import math

def wgs84_to_web_mercator(lon: float, lat: float) -> tuple:
    """Convert WGS84 (EPSG:4326) to Web Mercator (EPSG:3857)."""
    x = lon * 20037508.34 / 180
    y = math.log(math.tan((90 + lat) * math.pi / 360)) / (math.pi / 180)
    y = y * 20037508.34 / 180
    return x, y

# Texas PUC Sewer CCN endpoint
TX_SEWER_CCN_URL = "https://services6.arcgis.com/N6Lzvtb46cpxThhu/ArcGIS/rest/services/Sewer_CCN_Service_Areas/FeatureServer/230/query"

# California Water Districts (proxy for sewer - many CA water districts also provide sewer)
CA_WATER_DISTRICTS_URL = "https://gis.water.ca.gov/arcgis/rest/services/Boundaries/i03_WaterDistricts/FeatureServer/0/query"

# Florida DOH FLWMI - parcel-level wastewater data
FL_FLWMI_URL = "https://gis.floridahealth.gov/server/rest/services/FLWMI/FLWMI_Wastewater/MapServer/0/query"

# Connecticut DEEP Connected Sewer Service Areas
CT_SEWER_URL = "https://services1.arcgis.com/FjPcSmEFuDYlIdKC/arcgis/rest/services/Connected_Sewer_Service_Areas/FeatureServer/0/query"

# Washington WASWD Special Purpose Districts (~21% coverage)
WA_WASWD_URL = "https://services8.arcgis.com/J7RBtn4Gc9TK4jT1/arcgis/rest/services/WASWDMap_WFL1/FeatureServer/0/query"

# New Jersey DEP Sewer Service Areas
NJ_DEP_SSA_URL = "https://services2.arcgis.com/XVOqAjTOJ5P6ngMu/arcgis/rest/services/Util_wastewater_servicearea/FeatureServer/0/query"

# Massachusetts MassDEP WURP Sewer Service Areas
MA_MASSDEP_URL = "https://services.arcgis.com/hGdibHYSPO59RG1h/arcgis/rest/services/Sewer_Service_Area_POTW/FeatureServer/0/query"

# HIFLD Wastewater Treatment Plants endpoint
HIFLD_WASTEWATER_URL = "https://services.arcgis.com/XG15cJAlne2vxtgt/ArcGIS/rest/services/wastewater_treatment_plants_epa_frs/FeatureServer/0/query"

# Cache
_sewer_cache = {}


def lookup_texas_sewer_ccn(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Texas PUC Sewer CCN service areas by coordinates.
    
    Returns the sewer utility with CCN (Certificate of Convenience and Necessity)
    that serves the given location.
    """
    cache_key = f"tx_sewer|{lat:.4f}|{lon:.4f}"
    if cache_key in _sewer_cache:
        return _sewer_cache[cache_key]
    
    try:
        # Convert to Web Mercator (EPSG:3857) - required by this ArcGIS service
        x, y = wgs84_to_web_mercator(lon, lat)
        
        params = {
            "geometry": f"{x},{y}",
            "geometryType": "esriGeometryPoint",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "CCN_NO,UTILITY,DBA_NAME,COUNTY,CCN_TYPE,STATUS,TYPE",
            "returnGeometry": "false",
            "f": "json"
        }
        
        response = requests.get(TX_SEWER_CCN_URL, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        features = data.get("features", [])
        
        # Filter to sewer only (TYPE=2)
        sewer_features = [f for f in features if f.get("attributes", {}).get("TYPE") == 2]
        
        if not sewer_features:
            _sewer_cache[cache_key] = None
            return None
        
        # Take first match (should only be one for a point)
        attrs = sewer_features[0].get("attributes", {})
        
        # Determine confidence based on CCN_TYPE
        ccn_type = attrs.get("CCN_TYPE", "")
        if "Bounded Service Area" in ccn_type:
            confidence = "high"
        elif "Facilities +200 Feet" in ccn_type:
            confidence = "medium"
        else:
            confidence = "low"
        
        # Use DBA_NAME if available and not "NA", otherwise use UTILITY
        dba_name = attrs.get("DBA_NAME", "")
        utility_name = attrs.get("UTILITY", "Unknown")
        display_name = utility_name if (not dba_name or dba_name.upper() == "NA") else dba_name
        
        result = {
            "name": display_name,
            "legal_name": utility_name,
            "ccn_number": attrs.get("CCN_NO"),
            "ccn_type": ccn_type,
            "county": attrs.get("COUNTY"),
            "status": attrs.get("STATUS"),
            "phone": None,  # Not in CCN data
            "website": None,
            "_source": "texas_puc_sewer_ccn",
            "_confidence": confidence,
            "_note": f"Texas PUC CCN #{attrs.get('CCN_NO')} - {ccn_type}"
        }
        
        _sewer_cache[cache_key] = result
        return result
        
    except requests.RequestException as e:
        print(f"[TX Sewer CCN] API error: {e}")
        return None
    except Exception as e:
        print(f"[TX Sewer CCN] Error: {e}")
        return None


def lookup_hifld_wastewater(lat: float, lon: float, radius_miles: float = 10) -> Optional[Dict]:
    """
    Find nearest wastewater treatment plant from HIFLD database.
    
    This is a fallback - returns the nearest facility, NOT a confirmed service provider.
    """
    cache_key = f"hifld_ww|{lat:.4f}|{lon:.4f}"
    if cache_key in _sewer_cache:
        return _sewer_cache[cache_key]
    
    try:
        params = {
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "spatialRel": "esriSpatialRelIntersects",
            "distance": radius_miles,
            "units": "esriSRUnit_StatuteMile",
            "outFields": "NAME,CITY,STATE,COUNTY,NPDES_ID,CWNS_NBR,TREATMENT_LEVEL,POPULATION_SERVED_COUNT",
            "returnGeometry": "true",
            "f": "json"
        }
        
        response = requests.get(HIFLD_WASTEWATER_URL, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        features = data.get("features", [])
        
        if not features:
            _sewer_cache[cache_key] = None
            return None
        
        # Find nearest facility
        nearest = None
        min_distance = float('inf')
        
        for feature in features:
            attrs = feature.get("attributes", {})
            geom = feature.get("geometry", {})
            
            if geom:
                fac_lon = geom.get("x", 0)
                fac_lat = geom.get("y", 0)
                
                # Calculate distance (simple Euclidean for nearby points)
                dist = math.sqrt((fac_lat - lat)**2 + (fac_lon - lon)**2)
                
                if dist < min_distance:
                    min_distance = dist
                    nearest = attrs
        
        if not nearest:
            _sewer_cache[cache_key] = None
            return None
        
        # Convert distance to approximate miles (1 degree ≈ 69 miles at equator)
        distance_miles = min_distance * 69
        
        result = {
            "name": nearest.get("NAME", "Unknown Facility"),
            "city": nearest.get("CITY"),
            "state": nearest.get("STATE"),
            "county": nearest.get("COUNTY"),
            "npdes_id": nearest.get("NPDES_ID"),
            "treatment_level": nearest.get("TREATMENT_LEVEL"),
            "population_served": nearest.get("POPULATION_SERVED_COUNT"),
            "distance_miles": round(distance_miles, 1),
            "phone": None,
            "website": None,
            "_source": "hifld_wastewater",
            "_confidence": "low",
            "_note": f"Nearest wastewater facility ({distance_miles:.1f} mi) - does not confirm service"
        }
        
        _sewer_cache[cache_key] = result
        return result
        
    except requests.RequestException as e:
        print(f"[HIFLD Wastewater] API error: {e}")
        return None
    except Exception as e:
        print(f"[HIFLD Wastewater] Error: {e}")
        return None


def lookup_florida_flwmi(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Florida DOH FLWMI for parcel-level wastewater data.
    Returns sewer status with provider name if available.
    """
    cache_key = f"fl_flwmi|{lat:.4f}|{lon:.4f}"
    if cache_key in _sewer_cache:
        return _sewer_cache[cache_key]
    
    try:
        # Convert to Web Mercator (EPSG:3857) - required by this service
        x, y = wgs84_to_web_mercator(lon, lat)
        
        params = {
            "geometry": f"{x},{y}",
            "geometryType": "esriGeometryPoint",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "WW,WW_SRC_TYP,WW_SRC_NAME",
            "returnGeometry": "false",
            "f": "json"
        }
        
        response = requests.get(FL_FLWMI_URL, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        features = data.get("features", [])
        
        if not features:
            _sewer_cache[cache_key] = None
            return None
        
        attrs = features[0].get("attributes", {})
        ww_status = attrs.get("WW", "")
        ww_source = attrs.get("WW_SRC_NAME", "")
        
        # Map WW status to confidence
        confidence_map = {
            "KnownSewer": "high",
            "LikelySewer": "medium",
            "SomewhatLikelySewer": "low",
            "KnownSeptic": "high",  # High confidence it's septic
            "LikelySeptic": "medium",
            "Unknown": "low"
        }
        
        # Check if septic
        is_septic = "Septic" in ww_status
        
        if is_septic:
            result = {
                "name": "Private Septic System",
                "status": ww_status,
                "phone": None,
                "website": None,
                "_source": "florida_flwmi",
                "_confidence": confidence_map.get(ww_status, "low"),
                "_note": f"Florida DOH indicates {ww_status} - no public sewer service"
            }
        else:
            # Extract provider name from source
            provider_name = ww_source.split(" Sewer")[0] if " Sewer" in ww_source else ww_source
            if not provider_name or provider_name == "Unknown":
                provider_name = "Public Sewer Service"
            
            result = {
                "name": provider_name,
                "status": ww_status,
                "phone": None,
                "website": None,
                "_source": "florida_flwmi",
                "_confidence": confidence_map.get(ww_status, "medium"),
                "_note": f"Florida DOH FLWMI: {ww_status}"
            }
        
        _sewer_cache[cache_key] = result
        return result
        
    except Exception as e:
        print(f"[FL FLWMI] Error: {e}")
        return None


def lookup_connecticut_sewer(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Connecticut DEEP Connected Sewer Service Areas.
    """
    cache_key = f"ct_sewer|{lat:.4f}|{lon:.4f}"
    if cache_key in _sewer_cache:
        return _sewer_cache[cache_key]
    
    try:
        params = {
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "TOWN,Sewers,SewerStatus,TreatmentFacility",
            "returnGeometry": "false",
            "f": "json"
        }
        
        response = requests.get(CT_SEWER_URL, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        features = data.get("features", [])
        
        if not features:
            _sewer_cache[cache_key] = None
            return None
        
        attrs = features[0].get("attributes", {})
        town = attrs.get("TOWN", "")
        sewers = attrs.get("Sewers", "")
        status = attrs.get("SewerStatus", "")
        facility = attrs.get("TreatmentFacility", "")
        
        # Determine confidence based on status
        if status == "Connected":
            confidence = "high"
        elif sewers == "Existing":
            confidence = "medium"
        else:
            confidence = "low"
        
        # Build provider name
        if facility and facility != "Not Applicable":
            provider_name = facility
        elif town:
            provider_name = f"{town} Sewer Service"
        else:
            provider_name = "Connecticut Sewer Service"
        
        result = {
            "name": provider_name,
            "town": town,
            "status": status,
            "phone": None,
            "website": None,
            "_source": "connecticut_deep",
            "_confidence": confidence,
            "_note": f"CT DEEP: {sewers} - {status}"
        }
        
        _sewer_cache[cache_key] = result
        return result
        
    except Exception as e:
        print(f"[CT DEEP] Error: {e}")
        return None


def lookup_new_jersey_dep_ssa(lat: float, lon: float) -> Optional[Dict]:
    """
    Query New Jersey DEP Sewer Service Areas.
    Legally adopted Water Quality Management (WQM) plan boundaries.
    """
    cache_key = f"nj_dep|{lat:.4f}|{lon:.4f}"
    if cache_key in _sewer_cache:
        return _sewer_cache[cache_key]
    
    try:
        params = {
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "TRT_PLANT,NJPDES,SSA_TYPE",
            "returnGeometry": "false",
            "f": "json"
        }
        
        response = requests.get(NJ_DEP_SSA_URL, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        features = data.get("features", [])
        
        if not features:
            _sewer_cache[cache_key] = None
            return None
        
        attrs = features[0].get("attributes", {})
        trt_plant = attrs.get("TRT_PLANT", "")
        njpdes = attrs.get("NJPDES", "")
        ssa_type = attrs.get("SSA_TYPE", "")
        
        if not trt_plant:
            _sewer_cache[cache_key] = None
            return None
        
        result = {
            "name": trt_plant,
            "permit_number": njpdes,
            "ssa_type": ssa_type,
            "phone": None,
            "website": None,
            "_source": "new_jersey_dep_ssa",
            "_confidence": "high",
            "_note": f"NJ DEP Sewer Service Area - {trt_plant}"
        }
        
        _sewer_cache[cache_key] = result
        return result
        
    except Exception as e:
        print(f"[NJ DEP SSA] Error: {e}")
        return None


def lookup_massachusetts_massdep(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Massachusetts MassDEP WURP Sewer Service Areas.
    Water Utility Resilience Program - verified by contacting utilities.
    """
    cache_key = f"ma_massdep|{lat:.4f}|{lon:.4f}"
    if cache_key in _sewer_cache:
        return _sewer_cache[cache_key]
    
    try:
        params = {
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "FACILITY_NAME,NPDES_PERMIT,VERIFICATION_STATUS",
            "returnGeometry": "false",
            "f": "json"
        }
        
        response = requests.get(MA_MASSDEP_URL, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        features = data.get("features", [])
        
        if not features:
            _sewer_cache[cache_key] = None
            return None
        
        attrs = features[0].get("attributes", {})
        facility_name = attrs.get("FACILITY_NAME", "")
        npdes_permit = attrs.get("NPDES_PERMIT", "")
        verification_status = attrs.get("VERIFICATION_STATUS", "")
        
        if not facility_name:
            _sewer_cache[cache_key] = None
            return None
        
        # Confidence based on verification status
        confidence = "high" if verification_status == "Verified" else "medium"
        
        result = {
            "name": facility_name,
            "permit_number": npdes_permit,
            "verification_status": verification_status,
            "phone": None,
            "website": None,
            "_source": "massachusetts_massdep_wurp",
            "_confidence": confidence,
            "_note": f"MA DEP WURP - {facility_name}"
        }
        
        _sewer_cache[cache_key] = result
        return result
        
    except Exception as e:
        print(f"[MA MassDEP] Error: {e}")
        return None


def lookup_washington_waswd(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Washington WASWD Special Purpose Districts.
    Covers ~21% of WA with 182 special purpose districts.
    """
    cache_key = f"wa_waswd|{lat:.4f}|{lon:.4f}"
    if cache_key in _sewer_cache:
        return _sewer_cache[cache_key]
    
    try:
        x, y = wgs84_to_web_mercator(lon, lat)
        
        params = {
            "geometry": f"{x},{y}",
            "geometryType": "esriGeometryPoint",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "JURISDIC_2,JURISDIC_3",
            "returnGeometry": "false",
            "f": "json"
        }
        
        response = requests.get(WA_WASWD_URL, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        features = data.get("features", [])
        
        if not features:
            _sewer_cache[cache_key] = None
            return None
        
        attrs = features[0].get("attributes", {})
        county = attrs.get("JURISDIC_2", "")
        district_name = attrs.get("JURISDIC_3", "")
        
        if not district_name or district_name.strip() == "":
            district_name = f"{county} County Sewer District"
        
        result = {
            "name": district_name,
            "county": county,
            "phone": None,
            "website": None,
            "_source": "washington_waswd",
            "_confidence": "medium",
            "_note": f"WA Special Purpose District - {county} County"
        }
        
        _sewer_cache[cache_key] = result
        return result
        
    except Exception as e:
        print(f"[WA WASWD] Error: {e}")
        return None


def lookup_california_water_district(lat: float, lon: float) -> Optional[Dict]:
    """
    Query California Water Districts as proxy for sewer service.
    Many CA water districts also provide sewer service.
    """
    cache_key = f"ca_water|{lat:.4f}|{lon:.4f}"
    if cache_key in _sewer_cache:
        return _sewer_cache[cache_key]
    
    try:
        x, y = wgs84_to_web_mercator(lon, lat)
        
        params = {
            "geometry": f"{x},{y}",
            "geometryType": "esriGeometryPoint",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "AGENCYNAME,AGENCYUNIQUEID",
            "returnGeometry": "false",
            "f": "json"
        }
        
        response = requests.get(CA_WATER_DISTRICTS_URL, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        features = data.get("features", [])
        
        if not features:
            _sewer_cache[cache_key] = None
            return None
        
        attrs = features[0].get("attributes", {})
        agency_name = attrs.get("AGENCYNAME", "Unknown")
        
        # Check if name suggests sewer service
        name_lower = agency_name.lower()
        has_sewer_indicator = any(kw in name_lower for kw in [
            'sewer', 'sanitary', 'wastewater', 'water & sewer', 'utilities'
        ])
        
        result = {
            "name": agency_name,
            "id": attrs.get("AGENCYUNIQUEID"),
            "phone": None,
            "website": None,
            "_source": "ca_water_districts",
            "_confidence": "medium" if has_sewer_indicator else "low",
            "_note": "California water district - may also provide sewer service"
        }
        
        _sewer_cache[cache_key] = result
        return result
        
    except Exception as e:
        print(f"[CA Water Districts] Error: {e}")
        return None


def lookup_sewer_provider(
    lat: float = None,
    lon: float = None,
    city: str = None,
    state: str = None,
    zip_code: str = None
) -> Optional[Dict]:
    """
    Main sewer lookup function - tries all sources in priority order.
    
    Priority:
    1. Texas PUC Sewer CCN (if TX and coords available)
    2. California Water Districts (if CA and coords available)
    3. CSV providers database
    4. HIFLD wastewater (if coords available)
    5. Municipal water inference
    """
    result = None
    state_upper = state.upper() if state else ""
    
    # Tier 1: State-specific authoritative APIs
    
    # 1. Texas PUC Sewer CCN (authoritative for TX)
    if state_upper == "TX" and lat and lon:
        result = lookup_texas_sewer_ccn(lat, lon)
        if result:
            return result
    
    # 2. Florida DOH FLWMI (parcel-level)
    if state_upper == "FL" and lat and lon:
        result = lookup_florida_flwmi(lat, lon)
        if result:
            return result
    
    # 3. Connecticut DEEP
    if state_upper == "CT" and lat and lon:
        result = lookup_connecticut_sewer(lat, lon)
        if result:
            return result
    
    # 4. Washington WASWD (~21% coverage)
    if state_upper == "WA" and lat and lon:
        result = lookup_washington_waswd(lat, lon)
        if result:
            return result
    
    # 5. New Jersey DEP SSA
    if state_upper == "NJ" and lat and lon:
        result = lookup_new_jersey_dep_ssa(lat, lon)
        if result:
            return result
    
    # 6. Massachusetts MassDEP WURP
    if state_upper == "MA" and lat and lon:
        result = lookup_massachusetts_massdep(lat, lon)
        if result:
            return result
    
    # Tier 2: Water utility proxy
    
    # 7. California Water Districts (proxy for sewer)
    if state_upper == "CA" and lat and lon:
        result = lookup_california_water_district(lat, lon)
        if result:
            return result
    
    # Tier 3: CSV providers database
    try:
        from csv_utility_lookup import lookup_utility_from_csv
        csv_result = lookup_utility_from_csv(city, state, 'sewer')
        if csv_result:
            return {
                "name": csv_result.get('name'),
                "id": csv_result.get('id'),
                "phone": csv_result.get('phone'),
                "website": csv_result.get('website'),
                "city": city,
                "state": state,
                "_source": "csv_providers",
                "_confidence": "high"
            }
    except Exception:
        pass
    
    # 3. HIFLD wastewater treatment plants (fallback)
    if lat and lon:
        result = lookup_hifld_wastewater(lat, lon)
        if result:
            return result
    
    # 4. Municipal water inference (last resort)
    try:
        from municipal_utilities import lookup_municipal_sewer
        muni_result = lookup_municipal_sewer(state, city, zip_code)
        if muni_result:
            return {
                "name": muni_result.get('name'),
                "phone": muni_result.get('phone'),
                "website": muni_result.get('website'),
                "city": city,
                "state": state,
                "_source": muni_result.get('source', 'municipal_inferred'),
                "_confidence": muni_result.get('confidence', 'medium'),
                "_note": muni_result.get('note')
            }
    except Exception:
        pass
    
    return None


if __name__ == "__main__":
    print("Testing sewer lookup...")
    
    # Test Texas PUC Sewer CCN
    print("\n=== Texas PUC Sewer CCN ===")
    tests_tx = [
        (30.2672, -97.7431, "Austin, TX"),  # Downtown Austin
        (29.7604, -95.3698, "Houston, TX"),  # Downtown Houston
        (32.7767, -96.7970, "Dallas, TX"),   # Downtown Dallas
    ]
    
    for lat, lon, name in tests_tx:
        result = lookup_texas_sewer_ccn(lat, lon)
        if result:
            print(f"{name}: {result['name']} (CCN: {result.get('ccn_number')}, conf: {result['_confidence']})")
        else:
            print(f"{name}: No CCN found")
    
    # Test HIFLD fallback
    print("\n=== HIFLD Wastewater (fallback) ===")
    tests_hifld = [
        (40.7128, -74.0060, "New York, NY"),
        (39.9612, -82.9988, "Columbus, OH"),
    ]
    
    for lat, lon, name in tests_hifld:
        result = lookup_hifld_wastewater(lat, lon)
        if result:
            print(f"{name}: {result['name']} ({result.get('distance_miles')} mi away)")
        else:
            print(f"{name}: No facility found")
    
    # Test full lookup
    print("\n=== Full Sewer Lookup ===")
    result = lookup_sewer_provider(lat=30.2672, lon=-97.7431, city="Austin", state="TX", zip_code="78701")
    if result:
        print(f"Austin, TX: {result['name']} (source: {result['_source']})")
