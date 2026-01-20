#!/usr/bin/env python3
"""
GIS-based utility lookup using ArcGIS REST APIs.

This module provides point-in-polygon lookups for utility service territories
using state-specific and federal GIS APIs.

Data sources:
- EPA Community Water System Service Area Boundaries (nationwide)
- State PUC/PSC ArcGIS services (where available)
- HIFLD baseline (when downloaded locally)
"""

import requests
import json
import os
from typing import Dict, Optional, List
from functools import lru_cache

# Timeout for API requests
API_TIMEOUT = 10

# State FIPS to abbreviation mapping
FIPS_TO_STATE = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA",
    "08": "CO", "09": "CT", "10": "DE", "11": "DC", "12": "FL",
    "13": "GA", "15": "HI", "16": "ID", "17": "IL", "18": "IN",
    "19": "IA", "20": "KS", "21": "KY", "22": "LA", "23": "ME",
    "24": "MD", "25": "MA", "26": "MI", "27": "MN", "28": "MS",
    "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
    "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND",
    "39": "OH", "40": "OK", "41": "OR", "42": "PA", "44": "RI",
    "45": "SC", "46": "SD", "47": "TN", "48": "TX", "49": "UT",
    "50": "VT", "51": "VA", "53": "WA", "54": "WV", "55": "WI",
    "56": "WY", "72": "PR", "78": "VI"
}


def _query_arcgis_point(url: str, lat: float, lon: float, out_fields: str = "*") -> Optional[Dict]:
    """
    Generic ArcGIS REST API point-in-polygon query.
    
    Args:
        url: ArcGIS REST API query endpoint
        lat: Latitude
        lon: Longitude
        out_fields: Fields to return (default "*" for all)
        
    Returns:
        First matching feature's attributes, or None
    """
    params = {
        "where": "1=1",
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": out_fields,
        "returnGeometry": "false",
        "f": "json"
    }
    
    try:
        response = requests.get(url, params=params, timeout=API_TIMEOUT)
        data = response.json()
        
        if data.get("features") and len(data["features"]) > 0:
            return data["features"][0]["attributes"]
        return None
    except Exception as e:
        print(f"GIS API error ({url[:50]}...): {e}")
        return None


# =============================================================================
# WATER UTILITY LOOKUPS
# =============================================================================

def query_epa_water_service_area(lat: float, lon: float) -> Optional[Dict]:
    """
    Query EPA Community Water System Service Area Boundaries.
    
    This is the primary nationwide water utility lookup.
    Coverage: 44,000+ community water systems, 99% of US population.
    
    Returns:
        Dict with PWSID, PWS_Name, Pop_Cat_5, Data_Provider_Type
    """
    url = "https://services.arcgis.com/cJ9YHowT8TU7DUyn/arcgis/rest/services/Water_System_Boundaries/FeatureServer/0/query"
    result = _query_arcgis_point(url, lat, lon, "PWSID,PWS_Name,Pop_Cat_5,Data_Provider_Type,Primacy_Agency")
    
    if result:
        return {
            "name": result.get("PWS_Name", "").strip(),
            "pwsid": result.get("PWSID"),
            "population_category": result.get("Pop_Cat_5"),
            "data_source": result.get("Data_Provider_Type") or "EPA",
            "state": result.get("Primacy_Agency", "")[:2] if result.get("Primacy_Agency") else None,
            "confidence": "high",
            "source": "epa_cws_boundaries"
        }
    return None


def query_texas_water_service_area(lat: float, lon: float) -> Optional[Dict]:
    """
    Query TWDB Public Water Service Areas - the authoritative source for Texas retail water.
    
    This is self-reported by utilities via the Water User Survey program and represents
    actual retail service boundaries (not just legal CCN territories).
    """
    url = "https://services.twdb.texas.gov/arcgis/rest/services/PWS/Public_Water_Service_Areas/FeatureServer/0/query"
    result = _query_arcgis_point(url, lat, lon, "PWSName,PWSId,PWSCode,Active")
    
    if result and result.get("Active") == 1:
        return {
            "name": result.get("PWSName", "").strip(),
            "pws_id": result.get("PWSId"),
            "pws_code": result.get("PWSCode"),
            "confidence": "high",
            "source": "twdb_water_service_areas"
        }
    return None


def query_texas_water_ccn(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Texas PUC Water CCN (Certificate of Convenience and Necessity).
    
    CCN boundaries are legal service territories but may differ from actual service.
    Used as fallback if TWDB service areas don't have coverage.
    """
    url = "https://services.twdb.texas.gov/arcgis/rest/services/PWS/Public_Utility_Commission_CCN_Water/MapServer/0/query"
    result = _query_arcgis_point(url, lat, lon, "UTILITY,CCN_NO,COUNTY,STATUS")
    
    if result:
        return {
            "name": result.get("UTILITY", "").strip(),
            "ccn_number": result.get("CCN_NO"),
            "county": result.get("COUNTY"),
            "status": result.get("STATUS"),
            "confidence": "medium",
            "source": "texas_puc_ccn"
        }
    return None


def query_california_water(lat: float, lon: float) -> Optional[Dict]:
    """
    Query California SWRCB Drinking Water System Area Boundaries.
    This is more authoritative than EPA for California.
    """
    url = "https://gispublic.waterboards.ca.gov/portalserver/rest/services/Drinking_Water/California_Drinking_Water_System_Area_Boundaries/MapServer/0/query"
    result = _query_arcgis_point(url, lat, lon, "WATER_SYSTEM_NAME,WATER_SYSTEM_NUMBER,COUNTY")
    
    if result:
        return {
            "name": result.get("WATER_SYSTEM_NAME", "").strip(),
            "system_number": result.get("WATER_SYSTEM_NUMBER"),
            "county": result.get("COUNTY"),
            "confidence": "high",
            "source": "california_swrcb"
        }
    return None


# States with state-specific water APIs (more authoritative than EPA)
STATES_WITH_WATER_GIS = {'CA', 'TX', 'MS'}


def lookup_water_utility_gis(lat: float, lon: float, state: str = None) -> Optional[Dict]:
    """
    Look up water utility using GIS APIs.
    
    Uses state-specific sources where available, falls back to EPA national.
    
    Args:
        lat: Latitude
        lon: Longitude
        state: State abbreviation (optional, for routing to state-specific API)
        
    Returns:
        Dict with water utility info, or None
    """
    # Try state-specific sources first
    if state == "TX":
        # Tier 1: TWDB Public Water Service Areas (self-reported retail boundaries)
        result = query_texas_water_service_area(lat, lon)
        if result:
            return result
        # Tier 2: Texas PUC CCN (legal service territories)
        result = query_texas_water_ccn(lat, lon)
        if result:
            return result
    elif state == "CA":
        result = query_california_water(lat, lon)
        if result:
            return result
    elif state == "MS":
        result = query_mississippi_water(lat, lon)
        if result:
            return result
    
    # Fall back to EPA national dataset
    return query_epa_water_service_area(lat, lon)


# =============================================================================
# ELECTRIC UTILITY LOOKUPS
# =============================================================================

def query_new_jersey_electric(lat: float, lon: float) -> Optional[Dict]:
    """
    Query New Jersey DEP Electric Utilities Territory Map.
    """
    url = "https://mapsdep.nj.gov/arcgis/rest/services/Features/Utilities/MapServer/10/query"
    result = _query_arcgis_point(url, lat, lon, "NAME,DISTRICT,TYPE")
    
    if result:
        return {
            "name": result.get("NAME", "").strip(),
            "district": result.get("DISTRICT"),
            "type": result.get("TYPE"),
            "confidence": "high",
            "source": "new_jersey_dep"
        }
    return None


def query_arkansas_electric(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Arkansas GIS Office Electric Utility Service Territories.
    """
    url = "https://gis.arkansas.gov/arcgis/rest/services/FEATURESERVICES/Utilities/FeatureServer/11/query"
    result = _query_arcgis_point(url, lat, lon, "*")
    
    if result:
        # Arkansas data has different field names
        name = result.get("dma") or result.get("marketone") or result.get("name")
        return {
            "name": name.strip() if name else None,
            "state": result.get("state"),
            "confidence": "high",
            "source": "arkansas_gis"
        }
    return None


def query_delaware_electric(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Delaware FirstMap CPCN Electric Service Areas.
    """
    url = "https://enterprise.firstmaptest.delaware.gov/arcgis/rest/services/Boundaries/DE_CPCN/FeatureServer/2/query"
    result = _query_arcgis_point(url, lat, lon, "ELECTRICPROVIDER")
    
    if result:
        return {
            "name": result.get("ELECTRICPROVIDER", "").strip(),
            "confidence": "high",
            "source": "delaware_firstmap"
        }
    return None


def query_mississippi_electric(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Mississippi PSC Electric Certificated Areas (Layer 4).
    """
    url = "https://services2.arcgis.com/tONuKShmVp7yWQJL/arcgis/rest/services/PSC_CurrentCAs/FeatureServer/4/query"
    result = _query_arcgis_point(url, lat, lon, "UTILITY_NA,County")
    
    if result and result.get("UTILITY_NA"):
        return {
            "name": result.get("UTILITY_NA", "").strip(),
            "county": result.get("County"),
            "confidence": "high",
            "source": "mississippi_psc"
        }
    return None


def query_mississippi_gas(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Mississippi PSC Gas Certificated Areas (Layer 3).
    """
    url = "https://services2.arcgis.com/tONuKShmVp7yWQJL/arcgis/rest/services/PSC_CurrentCAs/FeatureServer/3/query"
    result = _query_arcgis_point(url, lat, lon, "UTILITY_NA,County")
    
    if result and result.get("UTILITY_NA"):
        return {
            "name": result.get("UTILITY_NA", "").strip(),
            "county": result.get("County"),
            "confidence": "high",
            "source": "mississippi_psc"
        }
    return None


def query_mississippi_water(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Mississippi PSC Water Certificated Areas (Layer 1).
    """
    url = "https://services2.arcgis.com/tONuKShmVp7yWQJL/arcgis/rest/services/PSC_CurrentCAs/FeatureServer/1/query"
    result = _query_arcgis_point(url, lat, lon, "UTILITY_NA,County")
    
    if result and result.get("UTILITY_NA"):
        return {
            "name": result.get("UTILITY_NA", "").strip(),
            "county": result.get("County"),
            "confidence": "high",
            "source": "mississippi_psc"
        }
    return None


def lookup_hawaii_electric(lat: float, lon: float) -> Optional[Dict]:
    """
    Simple lookup for Hawaii based on island coordinates.
    Hawaii has very simple utility structure - one utility per island.
    """
    # Simplified island detection based on longitude/latitude
    if lon > -156.0 and lon < -154.8:  # Big Island
        return {
            "name": "Hawaii Electric Light Company (HELCO)",
            "island": "Hawaii",
            "confidence": "high",
            "source": "hawaii_island_mapping"
        }
    elif lon > -156.7 and lon < -155.9 and lat > 20.5:  # Maui area
        return {
            "name": "Maui Electric Company (MECO)",
            "island": "Maui/Lanai/Molokai",
            "confidence": "high",
            "source": "hawaii_island_mapping"
        }
    elif lon > -159.8 and lon < -159.2:  # Kauai
        return {
            "name": "Kauai Island Utility Cooperative (KIUC)",
            "island": "Kauai",
            "confidence": "high",
            "source": "hawaii_island_mapping"
        }
    elif lon > -158.3 and lon < -157.6:  # Oahu
        return {
            "name": "Hawaiian Electric Company (HECO)",
            "island": "Oahu",
            "confidence": "high",
            "source": "hawaii_island_mapping"
        }
    return None


def lookup_rhode_island_electric(lat: float, lon: float) -> Optional[Dict]:
    """
    Simple lookup for Rhode Island.
    Nearly entire state served by Rhode Island Energy (National Grid).
    Only exception is Pascoag Utility District in Burrillville.
    """
    # Burrillville approximate bounds (northwest RI)
    if lat > 41.93 and lat < 42.03 and lon > -71.78 and lon < -71.65:
        return {
            "name": "Pascoag Utility District",
            "note": "Small service area in Burrillville",
            "confidence": "medium",
            "source": "rhode_island_mapping"
        }
    return {
        "name": "Rhode Island Energy",
        "confidence": "high",
        "source": "rhode_island_mapping"
    }


def lookup_dc_electric(lat: float, lon: float) -> Optional[Dict]:
    """
    Simple lookup for Washington DC.
    Entire district served by Pepco (Potomac Electric Power Company).
    """
    return {
        "name": "Pepco",
        "full_name": "Potomac Electric Power Company",
        "confidence": "high",
        "source": "dc_single_utility"
    }


def query_pennsylvania_electric(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Pennsylvania Electric Service Territories.
    """
    url = "https://services.arcgis.com/rD2ylXRs80UroD90/arcgis/rest/services/PA_Electric_Service_Territories/FeatureServer/0/query"
    result = _query_arcgis_point(url, lat, lon, "NAME")
    
    if result:
        return {
            "name": result.get("NAME", "").strip(),
            "confidence": "high",
            "source": "pennsylvania_puc"
        }
    return None


def query_wisconsin_electric(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Wisconsin Electric Service Territories.
    Checks IOU, Municipal, and Coop layers.
    """
    base_url = "https://services.arcgis.com/rD2ylXRs80UroD90/arcgis/rest/services/Utility_Service_Territories_in_WI/FeatureServer"
    
    # Layer 12 = IOUs, Layer 11 = Municipal, Layer 13 = Coops
    for layer_id in [12, 11, 13]:
        url = f"{base_url}/{layer_id}/query"
        result = _query_arcgis_point(url, lat, lon, "UTIL_LAB,CITY,PSC_ID")
        if result and result.get("UTIL_LAB"):
            return {
                "name": result.get("UTIL_LAB", "").strip(),
                "city": result.get("CITY"),
                "psc_id": result.get("PSC_ID"),
                "confidence": "high",
                "source": "wisconsin_psc"
            }
    return None


def query_colorado_electric(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Colorado Electric Utility Service Territories (CDOT).
    """
    url = "https://services.arcgis.com/yzB9WM8W0BO3Ql7d/arcgis/rest/services/Utilities_Boundaries/FeatureServer/0/query"
    result = _query_arcgis_point(url, lat, lon, "COMPNAME,HOLDINGCO")
    
    if result and result.get("COMPNAME"):
        return {
            "name": result.get("COMPNAME", "").strip(),
            "holding_company": result.get("HOLDINGCO"),
            "confidence": "high",
            "source": "colorado_cdot"
        }
    return None


def query_california_electric(lat: float, lon: float) -> Optional[Dict]:
    """
    Query California Electric Load Serving Entities (CEC).
    Verified Jan 2026 - includes IOUs and POUs.
    """
    url = "https://services3.arcgis.com/bWPjFyq029ChCGur/arcgis/rest/services/ElectricLoadServingEntities_IOU_POU/FeatureServer/0/query"
    result = _query_arcgis_point(url, lat, lon, "Utility,Acronym,Type,URL,Phone,Address")
    
    if result and result.get("Utility"):
        return {
            "name": result.get("Utility", "").strip(),
            "acronym": result.get("Acronym"),
            "utility_type": result.get("Type"),
            "website": result.get("URL"),
            "phone": result.get("Phone"),
            "confidence": "high",
            "source": "california_cec"
        }
    return None


def query_michigan_electric(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Michigan Electric Utility Service Areas (MPSC).
    Verified Jan 2026 - includes IOUs, munis, and co-ops.
    """
    url = "https://services3.arcgis.com/943LBv9FP414WfDO/arcgis/rest/services/ELECTRIC_UTILITY_SERVICE_AREA_MI_WFL1/FeatureServer/16/query"
    result = _query_arcgis_point(url, lat, lon, "Name,Type,Customers,Website,Phone,Counties_1")
    
    if result and result.get("Name"):
        return {
            "name": result.get("Name", "").strip(),
            "utility_type": result.get("Type"),
            "customers": result.get("Customers"),
            "website": result.get("Website"),
            "phone": result.get("Phone"),
            "counties": result.get("Counties_1"),
            "confidence": "high",
            "source": "michigan_mpsc"
        }
    return None


def query_texas_electric(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Texas Electric Utility Service Areas (PUC).
    Verified Jan 2026 - queries IOU, MUNI, and COOP layers.
    IMPORTANT: Use inSR=4326 for WGS84 coordinates.
    """
    # Query all three layers - IOU, MUNI, COOP
    layers = [
        ("https://services6.arcgis.com/N6Lzvtb46cpxThhu/arcgis/rest/services/IOU/FeatureServer/300/query", "IOU"),
        ("https://services6.arcgis.com/N6Lzvtb46cpxThhu/arcgis/rest/services/MUNI/FeatureServer/320/query", "MUNI"),
        ("https://services6.arcgis.com/N6Lzvtb46cpxThhu/arcgis/rest/services/COOP_DIST/FeatureServer/310/query", "COOP"),
    ]
    
    for url, layer_type in layers:
        result = _query_arcgis_point(url, lat, lon, "COMPANY_NAME,COMPANY_ABBREVIATION,COMPANY_TYPE,COMPANY_WEBSITE")
        if result and result.get("COMPANY_NAME"):
            return {
                "name": result.get("COMPANY_NAME", "").strip(),
                "abbreviation": result.get("COMPANY_ABBREVIATION"),
                "utility_type": result.get("COMPANY_TYPE") or layer_type,
                "website": result.get("COMPANY_WEBSITE"),
                "confidence": "high",
                "source": "texas_puc"
            }
    return None


def query_new_york_electric(lat: float, lon: float) -> Optional[Dict]:
    """
    Query New York Electric Utility Service Territories (NY PSC).
    """
    url = "https://services2.arcgis.com/Iru0GxDFgGL6jQqp/arcgis/rest/services/NYS_ElectricUtilityServiceTerritories/FeatureServer/0/query"
    result = _query_arcgis_point(url, lat, lon, "comp_full,comp_short,comp_id")
    
    if result and result.get("comp_full"):
        return {
            "name": result.get("comp_full", "").strip(),
            "short_name": result.get("comp_short"),
            "company_id": result.get("comp_id"),
            "confidence": "high",
            "source": "new_york_psc"
        }
    return None


def query_maine_electric(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Maine Electric Service Areas (ME PUC).
    """
    url = "https://services1.arcgis.com/RbMX0mRVOFNTdLzd/arcgis/rest/services/2020_Electric_Service_Area_web/FeatureServer/0/query"
    result = _query_arcgis_point(url, lat, lon, "UTIL_NAME,OWNER,Type,DISTRICT")
    
    if result and result.get("UTIL_NAME"):
        return {
            "name": result.get("UTIL_NAME", "").strip(),
            "owner": result.get("OWNER"),
            "utility_type": result.get("Type"),
            "district": result.get("DISTRICT"),
            "confidence": "high",
            "source": "maine_puc"
        }
    return None


def query_south_carolina_electric(lat: float, lon: float) -> Optional[Dict]:
    """
    Query South Carolina Electric Utility Service Territories (SCEMD).
    Verified Jan 2026 - via Palmetto EOC.
    """
    url = "https://maps.palmettoeoc.net/arcgis/rest/services/SCEMD_Services/sc_utility_providers/MapServer/3/query"
    result = _query_arcgis_point(url, lat, lon, "Provider,EMSYS")
    
    if result and result.get("Provider"):
        return {
            "name": result.get("Provider", "").strip(),
            "emsys_id": result.get("EMSYS"),
            "confidence": "high",
            "source": "south_carolina_scemd"
        }
    return None


def query_iowa_electric(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Iowa Electric Service Boundaries (IUC).
    Verified Jan 2026 - includes RECs, Municipals, IOUs.
    """
    url = "https://services.arcgis.com/vPD5PVLI6sfkZ5E4/arcgis/rest/services/Electrical_Service_Boundaries/FeatureServer/14/query"
    result = _query_arcgis_point(url, lat, lon, "Owner,ESB_Type,WebsiteURL,Emergency_Phone")
    
    if result and result.get("Owner"):
        return {
            "name": result.get("Owner", "").strip(),
            "utility_type": result.get("ESB_Type"),
            "website": result.get("WebsiteURL"),
            "emergency_phone": result.get("Emergency_Phone"),
            "confidence": "high",
            "source": "iowa_iuc"
        }
    return None


def query_virginia_electric(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Virginia Electric Utility Service Territories (SCC).
    Verified Jan 2026 - includes IOUs and cooperatives.
    """
    url = "https://services3.arcgis.com/Ww6Zhg5FR2pLMf1C/arcgis/rest/services/VA_Electric_2016/FeatureServer/0/query"
    result = _query_arcgis_point(url, lat, lon, "Provider,Utility,Website,Phone")
    
    if result and result.get("Utility"):
        return {
            "name": result.get("Utility", "").strip(),
            "provider_code": result.get("Provider"),
            "website": result.get("Website"),
            "phone": result.get("Phone"),
            "confidence": "high",
            "source": "virginia_scc"
        }
    return None


def query_indiana_electric(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Indiana Electric Utility Service Territories (IURC).
    Verified Jan 2026 - via Indiana GIS Portal.
    """
    url = "https://gisdata.in.gov/server/rest/services/Hosted/IURC_Prod_Boundaries_View/FeatureServer/0/query"
    result = _query_arcgis_point(url, lat, lon, "utilityname,name_abreviations")
    
    if result and result.get("utilityname"):
        return {
            "name": result.get("utilityname", "").strip(),
            "abbreviation": result.get("name_abreviations"),
            "confidence": "high",
            "source": "indiana_iurc"
        }
    return None


def query_kansas_electric(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Kansas Electric Utility Service Territories (KCC).
    Verified Jan 2026 - Certified Electric Areas.
    """
    url = "https://services1.arcgis.com/q2CglofYX6ACNEeu/arcgis/rest/services/2025_Electric/FeatureServer/0/query"
    result = _query_arcgis_point(url, lat, lon, "Company_Na,CO_CODE,Main_Pho_1,Outage_Map")
    
    if result and result.get("Company_Na"):
        return {
            "name": result.get("Company_Na", "").strip(),
            "company_code": result.get("CO_CODE"),
            "phone": result.get("Main_Pho_1"),
            "outage_map": result.get("Outage_Map"),
            "confidence": "high",
            "source": "kansas_kcc"
        }
    return None


def query_north_carolina_electric(lat: float, lon: float) -> Optional[Dict]:
    """
    Query North Carolina Electric Utility Service Territories (NCDOT).
    Verified Jan 2026 - queries Coop, Muni, and IOU layers.
    """
    layers = [
        ("https://services.arcgis.com/04HiymDgLlsbhaV4/arcgis/rest/services/NCDOT_Electric_Power_Retail_Service_Territories_4_WFL1/FeatureServer/1/query", "Cooperative"),
        ("https://services.arcgis.com/04HiymDgLlsbhaV4/arcgis/rest/services/NCDOT_Electric_Power_Retail_Service_Territories_4_WFL1/FeatureServer/2/query", "Municipal"),
        ("https://services.arcgis.com/04HiymDgLlsbhaV4/arcgis/rest/services/NCDOT_Electric_Power_Retail_Service_Territories_4_WFL1/FeatureServer/3/query", "IOU"),
    ]
    
    for url, layer_type in layers:
        result = _query_arcgis_point(url, lat, lon, "NAME,TYPE,HOLDING_CO,CUSTOMERS,TELEPHONE,WEBSITE")
        if result and result.get("NAME"):
            return {
                "name": result.get("NAME", "").strip(),
                "utility_type": result.get("TYPE"),
                "holding_company": result.get("HOLDING_CO"),
                "customers": result.get("CUSTOMERS"),
                "phone": result.get("TELEPHONE"),
                "website": result.get("WEBSITE"),
                "confidence": "high",
                "source": "north_carolina_ncdot"
            }
    return None


def query_minnesota_electric(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Minnesota Electric Utility Service Territories (MN PUC).
    Verified Jan 2026 - queries Muni, Coop, and IOU layers.
    Uses feat.gisdata.mn.gov subdomain (not app.gisdata.mn.gov).
    """
    layers = [
        ("https://feat.gisdata.mn.gov/arcgis/rest/services/EUSA/EUSA_Type/MapServer/0/query", "Municipal"),
        ("https://feat.gisdata.mn.gov/arcgis/rest/services/EUSA/EUSA_Type/MapServer/1/query", "Cooperative"),
        ("https://feat.gisdata.mn.gov/arcgis/rest/services/EUSA/EUSA_Type/MapServer/2/query", "IOU"),
    ]
    
    for url, layer_type in layers:
        result = _query_arcgis_point(url, lat, lon, "full_name,type,phone,website,abbrev")
        if result and result.get("full_name"):
            return {
                "name": result.get("full_name", "").strip(),
                "abbreviation": result.get("abbrev"),
                "utility_type": result.get("type"),
                "phone": result.get("phone"),
                "website": result.get("website"),
                "confidence": "high",
                "source": "minnesota_puc"
            }
    return None


def query_washington_electric(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Washington State Electric Utility Service Areas.
    """
    url = "https://services2.arcgis.com/lXwA5ckdH5etcXUm/ArcGIS/rest/services/WA_Electric_Utilities/FeatureServer/0/query"
    result = _query_arcgis_point(url, lat, lon, "NAME,FULLNAME,CAT")
    
    if result:
        return {
            "name": result.get("NAME") or result.get("FULLNAME", "").strip(),
            "category": result.get("CAT"),
            "confidence": "high",
            "source": "washington_utc"
        }
    return None


def query_oregon_electric(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Oregon Electric Utility Service Areas.
    """
    url = "https://services.arcgis.com/uUvqNMGPm7axC2dD/arcgis/rest/services/OregonElectric_Utilities_WGS_1984_6_26_2023/FeatureServer/0/query"
    result = _query_arcgis_point(url, lat, lon, "*")
    
    if result:
        # Oregon data has utility name in various fields
        name = result.get("NAME") or result.get("name") or result.get("UTILITY")
        return {
            "name": name.strip() if name else None,
            "confidence": "high",
            "source": "oregon_puc"
        }
    return None


def query_utah_electric(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Utah Electric Service Areas.
    """
    url = "https://services1.arcgis.com/99lidPhWCzftIe9K/arcgis/rest/services/UtahElectricServiceAreas/FeatureServer/0/query"
    result = _query_arcgis_point(url, lat, lon, "PROVIDER,ADDRESS,TELEPHONE,WEBLINK")
    
    if result:
        return {
            "name": result.get("PROVIDER", "").strip(),
            "phone": result.get("TELEPHONE"),
            "website": result.get("WEBLINK"),
            "confidence": "high",
            "source": "utah_agrc"
        }
    return None


def query_massachusetts_electric(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Massachusetts Electric Utility Providers (MassGIS).
    """
    url = "https://arcgisserver.digital.mass.gov/arcgisserver/rest/services/AGOL/ElectricityProviders/MapServer/0/query"
    result = _query_arcgis_point(url, lat, lon, "ELEC,TOWN")
    
    if result and result.get("ELEC"):
        return {
            "name": result.get("ELEC", "").strip(),
            "town": result.get("TOWN"),
            "confidence": "high",
            "source": "massgis"
        }
    return None


def query_vermont_electric(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Vermont Electric Utility Service Territories (VCGI).
    """
    url = "https://maps.vcgi.vermont.gov/arcgis/rest/services/PSD_services/PSD_Published_Layers/MapServer/0/query"
    result = _query_arcgis_point(url, lat, lon, "COMPANYNAM,Customer_Num")
    
    if result and result.get("COMPANYNAM"):
        return {
            "name": result.get("COMPANYNAM", "").strip(),
            "confidence": "high",
            "source": "vermont_psd"
        }
    return None


def query_florida_electric(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Florida Electric Utility Service Areas (Orange County GIS - statewide data).
    """
    url = "https://ocgis4.ocfl.net/arcgis/rest/services/AGOL_Open_Data/MapServer/68/query"
    result = _query_arcgis_point(url, lat, lon, "COMPANY")
    
    if result and result.get("COMPANY"):
        return {
            "name": result.get("COMPANY", "").strip(),
            "confidence": "high",
            "source": "florida_psc"
        }
    return None


def query_illinois_electric(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Illinois Electric Utility Boundaries (Illinois Office of Broadband).
    Verified Jan 2026 - HIFLD-derived with comprehensive operational data.
    """
    url = "https://services.arcgis.com/R0IGaIgf2sox9aCY/arcgis/rest/services/IL_Boundary_Layers/FeatureServer/3/query"
    result = _query_arcgis_point(url, lat, lon, "NAME,TYPE,HOLDING_CO,CUSTOMERS,TELEPHONE,WEBSITE")
    
    if result and result.get("NAME"):
        return {
            "name": result.get("NAME", "").strip(),
            "utility_type": result.get("TYPE"),
            "holding_company": result.get("HOLDING_CO"),
            "customers": result.get("CUSTOMERS"),
            "phone": result.get("TELEPHONE"),
            "website": result.get("WEBSITE"),
            "confidence": "high",
            "source": "illinois_iob"
        }
    return None


def query_ohio_electric(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Ohio PUCO Electric Service Areas (via ODOT TIMS).
    """
    url = "https://tims.dot.state.oh.us/ags/rest/services/Boundaries/PUCO_Electric_Service_Areas/MapServer/0/query"
    result = _query_arcgis_point(url, lat, lon, "COMPANY_NAME,COMPANY_CD,COMPANY_TYPE")
    
    if result and result.get("COMPANY_NAME"):
        return {
            "name": result.get("COMPANY_NAME", "").strip(),
            "company_code": result.get("COMPANY_CD"),
            "company_type": result.get("COMPANY_TYPE"),
            "confidence": "high",
            "source": "ohio_puco"
        }
    return None


def query_kentucky_electric(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Kentucky Electric Service Areas (KyGIS).
    """
    url = "https://kygisserver.ky.gov/arcgis/rest/services/WGS84WM_Services/Ky_Electric_Service_Areas_WGS84WM/MapServer/1/query"
    result = _query_arcgis_point(url, lat, lon, "COMPANY_NA,UTILITY_TY,ELEC_TYPE")
    
    if result and result.get("COMPANY_NA"):
        return {
            "name": result.get("COMPANY_NA", "").strip(),
            "utility_type": result.get("UTILITY_TY"),
            "electric_type": result.get("ELEC_TYPE"),
            "confidence": "high",
            "source": "kentucky_psc"
        }
    return None


def query_alaska_electric(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Alaska RCA Electric Utility Service Areas (DCCED).
    """
    url = "https://maps.commerce.alaska.gov/server/rest/services/Services/CDO_Utilities/MapServer/90/query"
    result = _query_arcgis_point(url, lat, lon, "UtilityName,CertificateNumber,UtilityType")
    
    if result and result.get("UtilityName"):
        return {
            "name": result.get("UtilityName", "").strip(),
            "certificate_number": result.get("CertificateNumber"),
            "utility_type": result.get("UtilityType"),
            "confidence": "high",
            "source": "alaska_rca"
        }
    return None


def query_nebraska_electric(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Nebraska Power Districts (NE GIS).
    Nebraska is 100% public power - no IOUs.
    """
    url = "https://gis.ne.gov/Enterprise/rest/services/Power_Districts/FeatureServer/0/query"
    result = _query_arcgis_point(url, lat, lon, "DISTRICT,SearchName")
    
    if result and result.get("DISTRICT"):
        return {
            "name": result.get("DISTRICT", "").strip(),
            "search_name": result.get("SearchName"),
            "confidence": "high",
            "source": "nebraska_gis"
        }
    return None


# State-specific electric lookup functions
STATE_ELECTRIC_APIS = {
    "NJ": query_new_jersey_electric,
    "AR": query_arkansas_electric,
    "DE": query_delaware_electric,
    "MS": query_mississippi_electric,
    "HI": lookup_hawaii_electric,
    "RI": lookup_rhode_island_electric,
    "PA": query_pennsylvania_electric,
    "WI": query_wisconsin_electric,
    "CO": query_colorado_electric,
    "WA": query_washington_electric,
    "OR": query_oregon_electric,
    "UT": query_utah_electric,
    "MA": query_massachusetts_electric,
    "VT": query_vermont_electric,
    "FL": query_florida_electric,
    "IL": query_illinois_electric,
    "OH": query_ohio_electric,
    "KY": query_kentucky_electric,
    "AK": query_alaska_electric,
    "NE": query_nebraska_electric,
    "CA": query_california_electric,
    "MI": query_michigan_electric,
    "TX": query_texas_electric,
    "NY": query_new_york_electric,
    "ME": query_maine_electric,
    "SC": query_south_carolina_electric,
    "IA": query_iowa_electric,
    "VA": query_virginia_electric,
    "IN": query_indiana_electric,
    "KS": query_kansas_electric,
    "DC": lookup_dc_electric,
    "NC": query_north_carolina_electric,
    "MN": query_minnesota_electric,
}


def query_hifld_electric(lat: float, lon: float) -> Optional[Dict]:
    """
    Query HIFLD Electric Retail Service Territories (nationwide fallback).
    This is the same API used by utility_lookup.py but wrapped for GIS module.
    """
    url = "https://services5.arcgis.com/HDRa0B57OVrv2E1q/arcgis/rest/services/Electric_Retail_Service_Territories/FeatureServer/0/query"
    result = _query_arcgis_point(url, lat, lon, "NAME,STATE,TELEPHONE,WEBSITE,TYPE")
    
    if result:
        return {
            "name": result.get("NAME", "").strip(),
            "state": result.get("STATE"),
            "phone": result.get("TELEPHONE"),
            "website": result.get("WEBSITE"),
            "type": result.get("TYPE"),
            "confidence": "medium",
            "source": "hifld_electric"
        }
    return None


def query_hifld_gas(lat: float, lon: float) -> Optional[Dict]:
    """
    Query HIFLD Natural Gas LDC Service Territories (nationwide fallback).
    """
    url = "https://services5.arcgis.com/HDRa0B57OVrv2E1q/arcgis/rest/services/Natural_Gas_Local_Distribution_Company_Service_Territories/FeatureServer/0/query"
    result = _query_arcgis_point(url, lat, lon, "NAME,STATE,TELEPHONE,WEBSITE,TYPE,HOLDINGCO")
    
    if result:
        return {
            "name": result.get("NAME", "").strip(),
            "state": result.get("STATE"),
            "phone": result.get("TELEPHONE"),
            "website": result.get("WEBSITE"),
            "type": result.get("TYPE"),
            "holding_company": result.get("HOLDINGCO"),
            "confidence": "medium",
            "source": "hifld_gas"
        }
    return None


def lookup_electric_utility_gis(lat: float, lon: float, state: str = None, use_hifld_fallback: bool = False) -> Optional[Dict]:
    """
    Look up electric utility using GIS APIs.
    
    Uses state-specific sources where available, optionally falls back to HIFLD.
    
    Args:
        lat: Latitude
        lon: Longitude
        state: State abbreviation (optional, for routing to state-specific API)
        use_hifld_fallback: If True, use HIFLD as fallback for states without specific APIs
        
    Returns:
        Dict with electric utility info, or None
    """
    # Try state-specific API first
    if state and state in STATE_ELECTRIC_APIS:
        result = STATE_ELECTRIC_APIS[state](lat, lon)
        if result:
            return result
    
    # Fall back to HIFLD if enabled
    if use_hifld_fallback:
        return query_hifld_electric(lat, lon)
    
    return None


# =============================================================================
# GAS UTILITY LOOKUPS
# =============================================================================

def query_new_jersey_gas(lat: float, lon: float) -> Optional[Dict]:
    """
    Query New Jersey DEP Gas Utilities Territory Map.
    """
    url = "https://mapsdep.nj.gov/arcgis/rest/services/Features/Utilities/MapServer/11/query"
    result = _query_arcgis_point(url, lat, lon, "NAME,DISTRICT,TYPE")
    
    if result:
        return {
            "name": result.get("NAME", "").strip(),
            "district": result.get("DISTRICT"),
            "type": result.get("TYPE"),
            "confidence": "high",
            "source": "new_jersey_dep"
        }
    return None


def query_california_gas(lat: float, lon: float) -> Optional[Dict]:
    """
    Query California Natural Gas Service Areas (CalEMA).
    """
    url = "https://services3.arcgis.com/bWPjFyq029ChCGur/arcgis/rest/services/Natural_Gas_Service_Area/FeatureServer/0/query"
    result = _query_arcgis_point(url, lat, lon, "SERVICE,ABR,CATEGORY")
    
    if result and result.get("SERVICE"):
        return {
            "name": result.get("SERVICE", "").strip(),
            "abbreviation": result.get("ABR"),
            "category": result.get("CATEGORY"),
            "confidence": "high",
            "source": "california_calema"
        }
    return None


def query_kentucky_gas(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Kentucky Gas Distribution Utilities (KY PSC via watermaps.ky.gov).
    Updated Jan 2026 - uses state-hosted endpoint with more detailed data.
    Layers: 1=Overlapping, 2=Municipal, 3=LDCs
    """
    # Primary: State-hosted endpoint (more detailed)
    url = "https://watermaps.ky.gov/arcgis/rest/services/WebMapServices/KY_Gas_Utility_Territories_WGS85WM/MapServer/3/query"
    result = _query_arcgis_point(url, lat, lon, "NAME,ABBREV,PSC_ID,PSC_Reg,TYPE_CODE")
    
    if result and result.get("NAME"):
        return {
            "name": result.get("NAME", "").strip(),
            "abbreviation": result.get("ABBREV"),
            "psc_id": result.get("PSC_ID"),
            "psc_regulated": result.get("PSC_Reg"),
            "type_code": result.get("TYPE_CODE"),
            "confidence": "high",
            "source": "kentucky_psc"
        }
    
    # Fallback: ArcGIS Online endpoint
    url_fallback = "https://services3.arcgis.com/ghsX9CKghMvyYjBU/arcgis/rest/services/Gas_Distribution_Utilities/FeatureServer/0/query"
    result = _query_arcgis_point(url_fallback, lat, lon, "NAME,TYPE_CODE")
    
    if result and result.get("NAME"):
        return {
            "name": result.get("NAME", "").strip(),
            "type_code": result.get("TYPE_CODE"),
            "confidence": "high",
            "source": "kentucky_psc"
        }
    return None


def query_wisconsin_gas(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Wisconsin Natural Gas Service Areas (PSC).
    """
    url = "https://services8.arcgis.com/IqcU3SH8HrYEvDe4/arcgis/rest/services/WI_Utilities_Natural_Gas_Service_Areas_(PSC_Data)/FeatureServer/0/query"
    result = _query_arcgis_point(url, lat, lon, "Util_Name,Util_ID")
    
    if result and result.get("Util_Name"):
        return {
            "name": result.get("Util_Name", "").strip(),
            "utility_id": result.get("Util_ID"),
            "confidence": "high",
            "source": "wisconsin_psc"
        }
    return None


def query_massachusetts_gas(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Massachusetts Natural Gas Utility Providers (MassGIS).
    """
    url = "https://arcgisserver.digital.mass.gov/arcgisserver/rest/services/AGOL/NatGasProviders/MapServer/0/query"
    result = _query_arcgis_point(url, lat, lon, "GAS,TOWN")
    
    if result and result.get("GAS"):
        return {
            "name": result.get("GAS", "").strip(),
            "town": result.get("TOWN"),
            "confidence": "high",
            "source": "massgis"
        }
    return None


def query_utah_gas(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Utah Natural Gas Service Areas (AGRC).
    """
    url = "https://services1.arcgis.com/99lidPhWCzftIe9K/arcgis/rest/services/UtahNaturalGasServiceAreas_Approx/FeatureServer/0/query"
    result = _query_arcgis_point(url, lat, lon, "PROVIDER,Name,TELEPHONE,WEBLINK")
    
    if result and result.get("PROVIDER"):
        return {
            "name": result.get("PROVIDER", "").strip(),
            "phone": result.get("TELEPHONE"),
            "website": result.get("WEBLINK"),
            "confidence": "high",
            "source": "utah_agrc"
        }
    return None


def query_washington_gas(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Washington State Natural Gas Utilities (UTC).
    """
    url = "https://services2.arcgis.com/lXwA5ckdH5etcXUm/ArcGIS/rest/services/WA_Natural_Gas_Utilities/FeatureServer/0/query"
    result = _query_arcgis_point(url, lat, lon, "OPER_NM,Website,Phone")
    
    if result and result.get("OPER_NM"):
        return {
            "name": result.get("OPER_NM", "").strip(),
            "website": result.get("Website"),
            "phone": result.get("Phone"),
            "confidence": "high",
            "source": "washington_utc"
        }
    return None


def query_alaska_gas(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Alaska RCA Natural Gas Service Areas (DCCED).
    """
    url = "https://maps.commerce.alaska.gov/server/rest/services/Services/CDO_Utilities/MapServer/93/query"
    result = _query_arcgis_point(url, lat, lon, "UtilityName,CertificateNumber,UtilityType")
    
    if result and result.get("UtilityName"):
        return {
            "name": result.get("UtilityName", "").strip(),
            "certificate_number": result.get("CertificateNumber"),
            "confidence": "high",
            "source": "alaska_rca"
        }
    return None


def query_oregon_gas(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Oregon Natural Gas Utilities (ODOE).
    """
    url = "https://services.arcgis.com/uUvqNMGPm7axC2dD/arcgis/rest/services/Oregon_Natural_Gas_and_Electric_Utility_Incentive_Layer_Update_13Dec2024_v01/FeatureServer/0/query"
    result = _query_arcgis_point(url, lat, lon, "Utility_Name,NG_or_Electric,Utility_Type,Home_Page")
    
    # Only return if it's a gas utility (field value is "Natural Gas")
    if result and result.get("Utility_Name") and "gas" in str(result.get("NG_or_Electric", "")).lower():
        return {
            "name": result.get("Utility_Name", "").strip(),
            "utility_type": result.get("Utility_Type"),
            "website": result.get("Home_Page"),
            "confidence": "high",
            "source": "oregon_odoe"
        }
    return None


def query_michigan_gas(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Michigan Natural Gas Utility Service Areas (MPSC).
    Verified Jan 2026 - Layer 27.
    """
    url = "https://services3.arcgis.com/943LBv9FP414WfDO/arcgis/rest/services/NATURAL_GAS_UTILITY_SERVICE_AREA_MI_WFL1/FeatureServer/27/query"
    result = _query_arcgis_point(url, lat, lon, "Name,Type,Customers,Website,Phone")
    
    if result and result.get("Name"):
        return {
            "name": result.get("Name", "").strip(),
            "utility_type": result.get("Type"),
            "customers": result.get("Customers"),
            "website": result.get("Website"),
            "phone": result.get("Phone"),
            "confidence": "high",
            "source": "michigan_mpsc"
        }
    return None


def query_virginia_gas(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Virginia Natural Gas Service Areas (SCC).
    Verified Jan 2026 - Layer 3.
    """
    url = "https://services3.arcgis.com/Ww6Zhg5FR2pLMf1C/arcgis/rest/services/gas_map_2020/FeatureServer/3/query"
    result = _query_arcgis_point(url, lat, lon, "PROVIDER,NAME,Type,CertificateLink")
    
    if result and result.get("PROVIDER"):
        return {
            "name": result.get("PROVIDER", "").strip(),
            "service_area": result.get("NAME"),
            "utility_type": result.get("Type"),
            "certificate_link": result.get("CertificateLink"),
            "confidence": "high",
            "source": "virginia_scc"
        }
    return None


def query_ohio_gas(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Ohio Natural Gas Service Territories.
    Verified Jan 2026.
    """
    url = "https://services3.arcgis.com/ccRMrVzOSHBUG6X2/arcgis/rest/services/Natural_Gas_Territories_Ohio/FeatureServer/0/query"
    result = _query_arcgis_point(url, lat, lon, "NAME,ADDRESS,CITY,STATE,ZIP,TELEPHONE,TYPE")
    
    if result and result.get("NAME"):
        return {
            "name": result.get("NAME", "").strip(),
            "address": result.get("ADDRESS"),
            "city": result.get("CITY"),
            "phone": result.get("TELEPHONE"),
            "utility_type": result.get("TYPE"),
            "confidence": "high",
            "source": "ohio_gas"
        }
    return None


# County-based gas utility lookup data
_GAS_COUNTY_LOOKUP_DATA = None

def _load_gas_county_lookups() -> Dict:
    """Load county-based gas utility lookup data."""
    global _GAS_COUNTY_LOOKUP_DATA
    if _GAS_COUNTY_LOOKUP_DATA is None:
        data_path = os.path.join(os.path.dirname(__file__), "data", "gas_county_lookups.json")
        try:
            with open(data_path, 'r') as f:
                _GAS_COUNTY_LOOKUP_DATA = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            _GAS_COUNTY_LOOKUP_DATA = {}
    return _GAS_COUNTY_LOOKUP_DATA


def lookup_gas_by_county(state: str, county: str, city: str = None) -> Optional[Dict]:
    """
    Look up gas utility by county for states without GIS APIs.
    
    Args:
        state: State abbreviation (IL, PA, NY, TX)
        county: County name
        city: City name (optional, for city-specific overrides)
        
    Returns:
        Dict with gas utility info, or None
    """
    data = _load_gas_county_lookups()
    
    if state not in data:
        return None
    
    state_data = data[state]
    
    # Check city-specific override first
    if city and "cities" in state_data:
        city_key = city.title()
        if city_key in state_data["cities"]:
            city_info = state_data["cities"][city_key]
            return {
                "name": city_info["utility"],
                "confidence": "high",
                "source": f"{state.lower()}_county_lookup",
                "notes": city_info.get("notes", "")
            }
    
    # Check county lookup
    if "counties" in state_data:
        # Normalize county name
        county_key = county.replace(" County", "").replace(" county", "").title()
        if county_key in state_data["counties"]:
            county_info = state_data["counties"][county_key]
            return {
                "name": county_info["utility"],
                "confidence": "medium",
                "source": f"{state.lower()}_county_lookup",
                "notes": county_info.get("notes", "")
            }
    
    # Return default if available
    if "_default" in state_data:
        return {
            "name": state_data["_default"],
            "confidence": "low",
            "source": f"{state.lower()}_county_lookup",
            "notes": "Default utility for state"
        }
    
    return None


# States with county-based gas lookups
STATES_WITH_GAS_COUNTY_LOOKUP = {'IL', 'PA', 'NY', 'TX'}


# States with working GIS APIs for electric
STATES_WITH_ELECTRIC_GIS = {'NJ', 'AR', 'DE', 'HI', 'RI', 'PA', 'WI', 'CO', 'WA', 'OR', 'UT', 'MA', 'VT', 'FL', 'IL', 'MS', 'OH', 'KY', 'AK', 'NE', 'CA', 'MI', 'TX', 'NY', 'ME', 'SC', 'IA', 'VA', 'IN', 'KS', 'DC', 'NC', 'MN'}

# States with working GIS APIs for gas
STATES_WITH_GAS_GIS = {'NJ', 'MS', 'CA', 'KY', 'WI', 'MA', 'UT', 'WA', 'AK', 'OR', 'MI', 'VA', 'OH'}

STATE_GAS_APIS = {
    "NJ": query_new_jersey_gas,
    "MS": query_mississippi_gas,
    "CA": query_california_gas,
    "KY": query_kentucky_gas,
    "WI": query_wisconsin_gas,
    "MA": query_massachusetts_gas,
    "UT": query_utah_gas,
    "WA": query_washington_gas,
    "AK": query_alaska_gas,
    "OR": query_oregon_gas,
    "MI": query_michigan_gas,
    "VA": query_virginia_gas,
    "OH": query_ohio_gas,
}


def lookup_gas_utility_gis(lat: float, lon: float, state: str = None, use_hifld_fallback: bool = False) -> Optional[Dict]:
    """
    Look up gas utility using GIS APIs.
    
    Args:
        lat: Latitude
        lon: Longitude
        state: State abbreviation
        use_hifld_fallback: If True, use HIFLD as fallback
        
    Returns:
        Dict with gas utility info, or None
    """
    # Try state-specific API first
    if state and state in STATE_GAS_APIS:
        result = STATE_GAS_APIS[state](lat, lon)
        if result:
            return result
    
    # Fall back to HIFLD if enabled
    if use_hifld_fallback:
        return query_hifld_gas(lat, lon)
    
    return None


# =============================================================================
# UNIFIED LOOKUP
# =============================================================================

def lookup_utilities_gis(lat: float, lon: float, state: str = None) -> Dict:
    """
    Look up all utilities (electric, gas, water) using GIS APIs.
    
    Args:
        lat: Latitude
        lon: Longitude
        state: State abbreviation (optional)
        
    Returns:
        Dict with electric, gas, and water utility info
    """
    result = {
        "electric": None,
        "gas": None,
        "water": None,
        "source": "gis_api"
    }
    
    # Electric lookup
    electric = lookup_electric_utility_gis(lat, lon, state)
    if electric:
        result["electric"] = electric
    
    # Gas lookup
    gas = lookup_gas_utility_gis(lat, lon, state)
    if gas:
        result["gas"] = gas
    
    # Water lookup (EPA has nationwide coverage)
    water = lookup_water_utility_gis(lat, lon, state)
    if water:
        result["water"] = water
    
    return result


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    # Test with Harvest, AL
    print("Testing Harvest, AL (34.789, -86.7889):")
    result = lookup_utilities_gis(34.789, -86.7889, "AL")
    print(f"  Water: {result.get('water')}")
    
    # Test with Newark, NJ
    print("\nTesting Newark, NJ (40.74, -74.17):")
    result = lookup_utilities_gis(40.74, -74.17, "NJ")
    print(f"  Electric: {result.get('electric')}")
    print(f"  Water: {result.get('water')}")
    
    # Test with Little Rock, AR
    print("\nTesting Little Rock, AR (34.75, -92.29):")
    result = lookup_utilities_gis(34.75, -92.29, "AR")
    print(f"  Electric: {result.get('electric')}")
    print(f"  Water: {result.get('water')}")
    
    # Test with Honolulu, HI
    print("\nTesting Honolulu, HI (21.31, -157.86):")
    result = lookup_utilities_gis(21.31, -157.86, "HI")
    print(f"  Electric: {result.get('electric')}")
