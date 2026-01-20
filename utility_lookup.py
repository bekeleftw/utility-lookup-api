#!/usr/bin/env python3
"""
Utility Provider Lookup - Proof of Concept
Takes an address, geocodes it, and returns the electric utility provider.

ENDPOINTS USED:
- Geocoding: US Census Geocoder (free, no API key)
- Electric Utility: HIFLD ArcGIS FeatureServer (free, no API key)
- Natural Gas Utility: HIFLD ArcGIS FeatureServer (free, no API key)
- Water Utility: EPA SDWIS API (free, no API key)
- Internet Providers: FCC Broadband Map API (free, no API key)

USAGE:
    python utility_lookup.py "1100 Congress Ave, Austin, TX 78701"
    python utility_lookup.py --test   # Run with test addresses
    python utility_lookup.py --coords -97.7431 30.2672  # Skip geocoding
"""

import requests
import sys
import json
import os
import re
from typing import Optional, Tuple, Dict, List, Union
from pathlib import Path
from urllib.parse import quote
from bs4 import BeautifulSoup

# Import state-specific utility verification
from state_utility_verification import verify_electric_provider, verify_gas_provider, check_problem_area
from utility_website_verification import enhance_lookup_with_verification, verify_address_utility, get_supported_states
from special_districts import lookup_special_district, format_district_for_response, has_special_district_data
from confidence_scoring import calculate_confidence, source_to_score_key
from municipal_utilities import lookup_municipal_electric, lookup_municipal_gas, lookup_municipal_water
from brand_resolver import resolve_brand_name_with_fallback
from findenergy_lookup import lookup_findenergy, verify_against_findenergy

# Import new Phase 12-14 modules
from deregulated_markets import is_deregulated_state, get_deregulated_market_info, adjust_electric_result_for_deregulation
from special_areas import get_special_area_info, check_tribal_land, check_incorporated_status, check_military_installation
from building_types import detect_building_type_from_address, adjust_result_for_building_type, get_utility_arrangement
from address_inference import infer_utility_from_nearby, add_verified_address
from ml_enhancements import ensemble_prediction, detect_anomalies, get_source_weight
from propane_service import is_likely_propane_area, get_no_gas_response
from well_septic import get_well_septic_likelihood, is_likely_rural

# GIS-based utility lookups
try:
    from gis_utility_lookup import lookup_water_utility_gis, lookup_electric_utility_gis, lookup_gas_utility_gis
    GIS_LOOKUP_AVAILABLE = True
except ImportError:
    GIS_LOOKUP_AVAILABLE = False

# New pipeline integration
try:
    from pipeline.pipeline import LookupPipeline
    from pipeline.interfaces import UtilityType, LookupContext
    from pipeline.sources.electric import (
        StateGISElectricSource, MunicipalElectricSource, CoopSource,
        EIASource, HIFLDElectricSource, CountyDefaultElectricSource
    )
    from pipeline.sources.gas import (
        StateGISGasSource, MunicipalGasSource,
        ZIPMappingGasSource, HIFLDGasSource, CountyDefaultGasSource
    )
    PIPELINE_AVAILABLE = True
    print(f"[STARTUP] Pipeline available, DATABASE_URL={'set' if os.environ.get('DATABASE_URL') else 'NOT SET'}")
except ImportError as e:
    print(f"[STARTUP] Pipeline not available: {e}")
    PIPELINE_AVAILABLE = False

# Try to load dotenv for API keys
try:
    from dotenv import load_dotenv
    # Try multiple .env locations
    env_paths = [
        Path(__file__).parent / ".env",
        Path(__file__).parent.parent / "PMD_scrape" / ".env",
        Path(__file__).parent.parent / "BrightData_AppFolio_Scraper" / ".env",
    ]
    for env_path in env_paths:
        if env_path.exists():
            load_dotenv(env_path)
            break
except ImportError:
    pass

# Cache file for water utility lookups
WATER_CACHE_FILE = Path(__file__).parent / "water_utility_cache.json"
# Local SDWA water lookup (built from build_water_lookup.py)
WATER_LOOKUP_FILE = Path(__file__).parent / "water_utility_lookup.json"

# BrightData proxy for SERP verification
BRIGHTDATA_PROXY_HOST = "brd.superproxy.io"
BRIGHTDATA_PROXY_PORT = 33335
BRIGHTDATA_PROXY_USER = "brd-customer-hl_6cc76bc7-zone-address_search"
BRIGHTDATA_PROXY_PASS = "n59dskgnctqr"

# BrightData Web Unlocker for FCC API
BRIGHTDATA_UNBLOCKER_USER = "brd-customer-hl_6cc76bc7-zone-unblocker1"
BRIGHTDATA_UNBLOCKER_PASS = "hp8kqmzw2666"

# OpenAI API key for LLM verification
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Google Maps API key for geocoding fallback
GOOGLE_MAPS_API_KEY = os.getenv('GOOGLE_MAPS_API_KEY')

# FCC Broadband Map API - no authentication required
FCC_API_UUID = "ac417bca-6346-46d3-812a-924d11fb7fc0"
FCC_API_BASE = "https://broadbandmap.fcc.gov/nbm/map/api"

# Technology code descriptions for internet providers
TECHNOLOGY_CODES = {
    "10": "Copper/DSL",
    "40": "Cable",
    "50": "Fiber to the Premises",
    "60": "GSO Satellite",
    "61": "NGSO Satellite",
    "70": "Unlicensed Fixed Wireless",
    "71": "Licensed Fixed Wireless",
    "72": "LTE Fixed Wireless",
}

SATELLITE_TECH_CODES = ["60", "61"]
WIRELESS_TECH_CODES = ["70", "71", "72"]

# State abbreviation mapping for Nominatim
STATE_ABBREVS = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
    "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
    "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
    "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT",
    "Vermont": "VT", "Virginia": "VA", "Washington": "WA", "West Virginia": "WV",
    "Wisconsin": "WI", "Wyoming": "WY", "District of Columbia": "DC"
}


# =============================================================================
# GEOCODING FUNCTIONS
# =============================================================================

def geocode_with_census(address: str, include_geography: bool = False) -> Optional[Dict]:
    """
    Geocode using US Census Geocoder (free, no API key).
    Best for established addresses, may fail for new construction.
    """
    if include_geography:
        base_url = "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress"
        params = {
            "address": address,
            "benchmark": "Public_AR_Current",
            "vintage": "Census2020_Current",  # Need this vintage to get Census Blocks
            "format": "json"
        }
    else:
        base_url = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
        params = {
            "address": address,
            "benchmark": "Public_AR_Current",
            "format": "json"
        }
    
    try:
        response = requests.get(base_url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        matches = data.get("result", {}).get("addressMatches", [])
        if not matches:
            return None
        
        match = matches[0]
        coords = match["coordinates"]
        
        # Extract ZIP code from matched address (format: "123 MAIN ST, CITY, ST, 12345")
        matched_addr = match["matchedAddress"]
        zip_code = None
        if matched_addr:
            import re
            zip_match = re.search(r'\b(\d{5})(?:-\d{4})?\s*$', matched_addr)
            if zip_match:
                zip_code = zip_match.group(1)
        
        result = {
            "lon": coords["x"],
            "lat": coords["y"],
            "matched_address": matched_addr,
            "city": None,
            "county": None,
            "state": None,
            "zip_code": zip_code,
            "source": "Census"
        }
        
        # Extract geography info if available
        if include_geography and "geographies" in match:
            geo = match["geographies"]
            counties = geo.get("Counties", [])
            if counties:
                result["county"] = counties[0].get("BASENAME")
            places = geo.get("Incorporated Places", []) or geo.get("County Subdivisions", [])
            if places:
                result["city"] = places[0].get("BASENAME")
            states = geo.get("States", [])
            if states:
                result["state"] = states[0].get("STUSAB")
            # Extract Census Block GEOID for internet provider lookup
            blocks = geo.get("Census Blocks", [])
            if blocks:
                result["block_geoid"] = blocks[0].get("GEOID")
        
        return result
        
    except requests.RequestException:
        return None


def geocode_with_google(address: str) -> Optional[Dict]:
    """
    Geocode using Google Maps API (paid, but has free tier).
    Good for new construction and hard-to-find addresses.
    """
    if not GOOGLE_MAPS_API_KEY:
        return None
    
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "address": address,
        "key": GOOGLE_MAPS_API_KEY
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get("status") != "OK" or not data.get("results"):
            return None
        
        result = data["results"][0]
        location = result["geometry"]["location"]
        
        # Extract city, county, state from address components
        city = None
        county = None
        state = None
        
        for component in result.get("address_components", []):
            types = component.get("types", [])
            if "locality" in types:
                city = component["long_name"]
            elif "administrative_area_level_2" in types:
                # Remove " County" suffix if present
                county = component["long_name"].replace(" County", "")
            elif "administrative_area_level_1" in types:
                state = component["short_name"]
        
        return {
            "lon": location["lng"],
            "lat": location["lat"],
            "matched_address": result.get("formatted_address"),
            "city": city,
            "county": county,
            "state": state,
            "source": "Google"
        }
        
    except requests.RequestException:
        return None


def geocode_with_nominatim(address: str) -> Optional[Dict]:
    """
    Geocode using Nominatim/OpenStreetMap (free, rate limited).
    Fallback when Census and Google fail.
    """
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": address,
        "format": "json",
        "addressdetails": 1,
        "limit": 1,
        "countrycodes": "us"
    }
    headers = {
        "User-Agent": "UtilityLookupTool/1.0"
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if not data:
            return None
        
        result = data[0]
        addr = result.get("address", {})
        
        # Convert state name to abbreviation
        state_name = addr.get("state", "")
        state = STATE_ABBREVS.get(state_name, state_name)
        
        # Get county and remove " County" suffix
        county = addr.get("county", "")
        if county.endswith(" County"):
            county = county[:-7]
        
        return {
            "lon": float(result["lon"]),
            "lat": float(result["lat"]),
            "matched_address": result.get("display_name"),
            "city": addr.get("city") or addr.get("town") or addr.get("village"),
            "county": county,
            "state": state,
            "source": "Nominatim"
        }
        
    except requests.RequestException:
        return None


def geocode_address(address: str, include_geography: bool = False) -> Optional[Dict]:
    """
    Geocode an address using a three-tier fallback system:
    1. Census Geocoder (free, best for established addresses)
    2. Google Maps API (handles new construction)
    3. Nominatim/OSM (free fallback)
    """
    print(f"Looking up utilities for: {address}\n")
    
    # Tier 1: Census Geocoder
    result = geocode_with_census(address, include_geography)
    if result:
        print(f"Geocoded (Census): {result.get('matched_address')}")
        print(f"Coordinates: {result.get('lat')}, {result.get('lon')}")
        if result.get('city') or result.get('county'):
            print(f"Location: {result.get('city', 'N/A')}, {result.get('county', 'N/A')} County, {result.get('state', 'N/A')}")
        return result
    
    print("Census geocoder failed, trying Google...")
    
    # Tier 2: Google Maps API
    result = geocode_with_google(address)
    if result:
        print(f"Geocoded (Google): {result.get('matched_address')}")
        print(f"Coordinates: {result.get('lat')}, {result.get('lon')}")
        if result.get('city') or result.get('county'):
            print(f"Location: {result.get('city', 'N/A')}, {result.get('county', 'N/A')} County, {result.get('state', 'N/A')}")
        return result
    
    print("Google geocoder failed, trying Nominatim...")
    
    # Tier 3: Nominatim/OSM
    result = geocode_with_nominatim(address)
    if result:
        print(f"Geocoded (Nominatim): {result.get('matched_address')}")
        print(f"Coordinates: {result.get('lat')}, {result.get('lon')}")
        if result.get('city') or result.get('county'):
            print(f"Location: {result.get('city', 'N/A')}, {result.get('county', 'N/A')} County, {result.get('state', 'N/A')}")
        return result
    
    print(f"No geocoding results for: {address}")
    return None


# =============================================================================
# UTILITY LOOKUP FUNCTIONS
# =============================================================================

def lookup_electric_utility(lon: float, lat: float) -> Optional[Dict]:
    """
    Query HIFLD ArcGIS API to find electric utility for a given point.
    Returns utility info dict or None if not found.
    """
    base_url = "https://services5.arcgis.com/HDRa0B57OVrv2E1q/arcgis/rest/services/Electric_Retail_Service_Territories/FeatureServer/0/query"
    
    params = {
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "NAME,ID,STATE,TELEPHONE,ADDRESS,CITY,ZIP,WEBSITE",
        "returnGeometry": "false",
        "f": "json"
    }
    
    try:
        response = requests.get(base_url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        features = data.get("features", [])
        if not features:
            print("No electric utility found for this location.")
            return None
        
        # Return all matches (territories can overlap)
        if len(features) == 1:
            return features[0]["attributes"]
        else:
            return [f["attributes"] for f in features]
        
    except requests.RequestException as e:
        print(f"Electric utility lookup error: {e}")
        return None


def lookup_gas_utility(lon: float, lat: float, state: str = None) -> Optional[Dict]:
    """
    Query HIFLD ArcGIS API to find natural gas utility for a given point.
    Falls back to state-level lookup if spatial query returns no results.
    Returns utility info dict or None if not found.
    """
    base_url = "https://services5.arcgis.com/HDRa0B57OVrv2E1q/arcgis/rest/services/Natural_Gas_Local_Distribution_Company_Service_Territories/FeatureServer/0/query"
    
    # First try spatial query
    params = {
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "NAME,SVCTERID,STATE,TELEPHONE,ADDRESS,CITY,ZIP,WEBSITE,TYPE,HOLDINGCO,AREASQMI",
        "returnGeometry": "false",
        "f": "json"
    }
    
    try:
        response = requests.get(base_url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        features = data.get("features", [])
        if features:
            # Return all matches (territories can overlap)
            if len(features) == 1:
                return features[0]["attributes"]
            else:
                return [f["attributes"] for f in features]
        
        # No spatial match found - return None rather than guessing
        print("No natural gas utility found in database for this location.")
        return None
        
    except requests.RequestException as e:
        print(f"Gas utility lookup error: {e}")
        return None


def lookup_gas_utility_by_state(state: str) -> Optional[Dict]:
    """
    Fallback: Query gas utilities by state, return the largest by customer count.
    Used when spatial query fails due to incomplete polygon data.
    """
    base_url = "https://services5.arcgis.com/HDRa0B57OVrv2E1q/arcgis/rest/services/Natural_Gas_Local_Distribution_Company_Service_Territories/FeatureServer/0/query"
    
    params = {
        "where": f"STATE='{state}'",
        "outFields": "NAME,SVCTERID,STATE,TELEPHONE,ADDRESS,CITY,ZIP,WEBSITE,TYPE,HOLDINGCO,TOTAL_CUST",
        "orderByFields": "TOTAL_CUST DESC",
        "returnGeometry": "false",
        "resultRecordCount": 1,
        "f": "json"
    }
    
    try:
        response = requests.get(base_url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        features = data.get("features", [])
        if not features:
            return None
        
        largest = features[0]["attributes"]
        return largest
        
    except requests.RequestException as e:
        print(f"Gas utility state lookup error: {e}")
        return None


def load_water_cache() -> Dict:
    """Load water utility cache from file."""
    if WATER_CACHE_FILE.exists():
        try:
            with open(WATER_CACHE_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def save_water_cache(cache: Dict) -> None:
    """Save water utility cache to file."""
    try:
        with open(WATER_CACHE_FILE, 'w') as f:
            json.dump(cache, f, indent=2)
    except IOError as e:
        print(f"Warning: Could not save water cache: {e}")


WATER_SUPPLEMENTAL_FILE = Path(__file__).parent / "water_utilities_supplemental.json"


def _check_water_supplemental(state: str, city: str) -> Optional[Dict]:
    """
    Check supplemental water file for city-level overrides.
    This takes priority over MUD/special district data for cities that have
    taken over water service from MUDs.
    """
    if not WATER_SUPPLEMENTAL_FILE.exists() or not city:
        return None
    
    try:
        with open(WATER_SUPPLEMENTAL_FILE, 'r') as f:
            supplemental = json.load(f)
        
        # Build city variants to check
        city_upper = city.upper()
        city_variants = [city_upper]
        
        # Handle hyphenated cities (e.g., "Kyle-Buda")
        if '-' in city_upper:
            for part in city_upper.split('-'):
                if part.strip() not in city_variants:
                    city_variants.append(part.strip())
        
        for city_variant in city_variants:
            city_key = f"{state}|{city_variant}"
            if city_key in supplemental.get('by_city', {}):
                entry = supplemental['by_city'][city_key]
                return {
                    "name": entry.get('name'),
                    "id": None,
                    "state": state,
                    "phone": entry.get('phone'),
                    "address": None,
                    "city": city_variant,
                    "zip": None,
                    "population_served": None,
                    "source_type": None,
                    "owner_type": "Municipal",
                    "service_connections": None,
                    "_confidence": entry.get('_confidence', 'high'),
                    "_source": "supplemental",
                    "_note": entry.get('_note', 'City water utility')
                }
    except (json.JSONDecodeError, IOError):
        pass
    
    return None


WATER_MISSING_CITIES_FILE = Path(__file__).parent / "water_missing_cities.json"
LOOKUPS_LOG_FILE = Path(__file__).parent / "data" / "lookup_log.json"
MAX_LOG_ENTRIES = 10000  # Keep last 10k lookups

# Authoritative sources that don't need SERP verification (cost optimization)
# TIER 1 & 2 sources - Skip SERP verification (saves ~$0.01/lookup)
AUTHORITATIVE_SOURCES = {
    # Tier 1: Ground truth (95+ confidence)
    'user_confirmed',
    'utility_direct_api',
    'arcgis',
    'franchise_agreement',
    'parcel_data',
    'user_feedback',
    'municipal_utility',
    'municipal_utility_database',
    # Tier 2: High quality (80-89 confidence)
    'special_district',
    'special_district_boundary',
    'verified',
    'zip_override',
    'electric_cooperative_polygon',
    'texas_railroad_commission',
    'railroad_commission',
    'state_puc_territory',
    'state_puc_map',
    'puc territory',
}

# TIER 4 & 5 sources - Always SERP verify
ALWAYS_VERIFY_SOURCES = {
    'eia_861',
    'hifld',
    'hifld_polygon',
    'hifld_iou_polygon',
    'epa_sdwis',
    'heuristic',
    'heuristic_city_match',
    'county_match',
    'unknown',
}


def should_skip_serp(result: Dict, utility_type: str) -> tuple:
    """
    Determine if SERP verification can be skipped based on source authority.
    Returns (skip: bool, reason: str)
    
    This saves ~$0.01 per lookup when we have authoritative data.
    
    SELECTIVE SERP STRATEGY (Phase 3):
    - Skip SERP for HIGH confidence results (verified, user-confirmed, municipal)
    - Use SERP for LOW/MEDIUM confidence results (especially gas)
    - Gas territories are complex but we now have comprehensive ZIP mappings
    """
    if not result:
        return False, "No result to verify"
    
    # Get source from various possible fields
    source = (
        result.get('_source') or 
        result.get('_verification_source') or 
        result.get('source') or 
        ''
    ).lower()
    
    confidence_score = result.get('confidence_score', 0)
    confidence_level = result.get('_confidence', '').lower()
    
    # ALWAYS skip for user-reported corrections (highest authority)
    if 'correction_db' in source or 'user_feedback' in source or 'user_confirmed' in source:
        return True, f"User-reported correction: {source}"
    
    # Skip for truly authoritative sources (municipal, direct API, etc.)
    truly_authoritative = {
        'municipal_utility', 'municipal_utility_database', 'utility_direct_api',
        'arcgis', 'franchise_agreement', 'parcel_data'
    }
    for auth_source in truly_authoritative:
        if auth_source in source:
            return True, f"Authoritative source: {source}"
    
    # Skip if confidence is already very high (90+)
    if confidence_score >= 90:
        return True, f"High confidence score: {confidence_score}"
    
    # Skip if marked as verified
    if confidence_level == 'verified':
        return True, "Already verified"
    
    # For gas: Skip SERP if we have a high-confidence ZIP mapping
    if utility_type == 'gas':
        # Skip if from state PUC territory data with high confidence
        if 'puc' in source or 'territory' in source:
            if confidence_level == 'high' or confidence_score >= 80:
                return True, f"High-confidence gas mapping: {source}"
        # Otherwise, use SERP for gas (complex territories)
        return False, "Gas lookup needs SERP verification (medium/low confidence)"
    
    # Don't skip for sources that need verification
    for verify_source in ALWAYS_VERIFY_SOURCES:
        if verify_source in source:
            return False, f"Non-authoritative source: {source}"
    
    # Default: skip if confidence >= 85 (our threshold for "verified" level)
    if confidence_score >= 85:
        return True, f"Good confidence: {confidence_score}"
    
    # Default: verify
    return False, "Default behavior"


def log_lookup(
    address: str,
    city: str,
    county: str,
    state: str,
    zip_code: str,
    electric_provider: str = None,
    gas_provider: str = None,
    water_provider: str = None,
    internet_count: int = None
):
    """Log a lookup for later validation."""
    from datetime import datetime
    
    try:
        LOOKUPS_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        if LOOKUPS_LOG_FILE.exists():
            with open(LOOKUPS_LOG_FILE, 'r') as f:
                lookups = json.load(f)
        else:
            lookups = []
        
        entry = {
            'timestamp': datetime.now().isoformat(),
            'address': address,
            'city': city,
            'county': county,
            'state': state,
            'zip_code': zip_code,
            'electric_provider': electric_provider,
            'gas_provider': gas_provider,
            'water_provider': water_provider,
            'internet_count': internet_count
        }
        
        lookups.append(entry)
        
        # Trim to max entries
        if len(lookups) > MAX_LOG_ENTRIES:
            lookups = lookups[-MAX_LOG_ENTRIES:]
        
        with open(LOOKUPS_LOG_FILE, 'w') as f:
            json.dump(lookups, f)
    except Exception:
        pass  # Don't fail if logging fails

def log_missing_water_city(state: str, city: str, county: str, match_type: str):
    """Log cities that are missing from EPA SDWIS data for later addition to supplemental file."""
    if not state or not city:
        return
    
    try:
        # Load existing missing cities
        if WATER_MISSING_CITIES_FILE.exists():
            with open(WATER_MISSING_CITIES_FILE, 'r') as f:
                missing = json.load(f)
        else:
            missing = {"_description": "Cities missing from EPA SDWIS - candidates for supplemental file", "cities": {}}
        
        key = f"{state}|{city.upper()}"
        if key not in missing.get("cities", {}):
            missing["cities"][key] = {
                "state": state,
                "city": city.upper(),
                "county": county,
                "match_type": match_type,  # "county_fallback" or "heuristic"
                "first_seen": str(Path(__file__).stat().st_mtime),  # timestamp
                "count": 1
            }
        else:
            missing["cities"][key]["count"] = missing["cities"][key].get("count", 0) + 1
        
        with open(WATER_MISSING_CITIES_FILE, 'w') as f:
            json.dump(missing, f, indent=2)
    except Exception:
        pass  # Don't fail the lookup if logging fails

def lookup_water_utility(city: str, county: str, state: str, full_address: str = None, 
                         lat: float = None, lon: float = None, zip_code: str = None) -> Optional[Dict]:
    """
    Look up water utility using local SDWA data (fast) or fallback to heuristic.
    
    Priority order:
    1. Special districts (MUDs, CDDs, etc.) - most precise for new developments
    2. Supplemental file (manually curated for cities missing from EPA)
    3. EPA SDWA data (by city)
    4. EPA SDWA data (by county)
    5. Heuristic fallback
    """
    if not state:
        return None
    
    # PRIORITY 0: Check special districts first (MUDs, CDDs, etc.)
    if has_special_district_data(state):
        special_result = lookup_special_district(
            lat=lat,
            lon=lon,
            state=state,
            zip_code=zip_code,
            service='water'
        )
        if special_result:
            formatted = format_district_for_response(special_result)
            # Add standard fields expected by the rest of the system
            formatted['state'] = state
            formatted['city'] = city
            # Add confidence scoring
            match_method = special_result.get('match_method', 'zip')
            match_level = 'address' if match_method in ['coordinates', 'zip_with_coordinates'] else 'special_district'
            confidence_data = calculate_confidence(
                source='special_district',
                match_level=match_level,
                utility_type='water'
            )
            formatted['confidence_score'] = confidence_data['score']
            formatted['confidence_factors'] = [
                f"{f['points']:+d}: {f['description']}" 
                for f in confidence_data['factors']
            ]
            return formatted
    
    # Try to extract city from full address if provided (more reliable than geocoder city)
    address_city = None
    if full_address:
        # Try to extract city from address like "301 Treasure Trove Path, Kyle, TX 78640"
        import re
        # Pattern: city name before state abbreviation
        match = re.search(r',\s*([A-Za-z\s]+),\s*[A-Z]{2}\s*\d{5}', full_address)
        if match:
            address_city = match.group(1).strip().upper()
    
    # Build list of city variants to try
    city_variants = []
    if address_city:
        city_variants.append(address_city)
    if city:
        city_upper = city.upper()
        if city_upper not in city_variants:
            city_variants.append(city_upper)
        if '-' in city_upper:
            for part in city_upper.split('-'):
                if part.strip() not in city_variants:
                    city_variants.append(part.strip())
    
    # FIRST: Check supplemental file for cities missing from EPA
    if WATER_SUPPLEMENTAL_FILE.exists():
        try:
            with open(WATER_SUPPLEMENTAL_FILE, 'r') as f:
                supplemental = json.load(f)
            
            for city_variant in city_variants:
                city_key = f"{state}|{city_variant}"
                if city_key in supplemental.get('by_city', {}):
                    result = supplemental['by_city'][city_key].copy()
                    result['_confidence'] = result.get('_confidence', 'high')
                    result['_source'] = 'supplemental'
                    # Add confidence scoring
                    confidence_data = calculate_confidence(
                        source='supplemental',
                        match_level='zip5',
                        utility_type='water'
                    )
                    result['confidence_score'] = confidence_data['score']
                    result['confidence_factors'] = [
                        f"{f['points']:+d}: {f['description']}" 
                        for f in confidence_data['factors']
                    ]
                    return result
        except (json.JSONDecodeError, IOError):
            pass
    
    # SECOND: Try EPA SDWA lookup
    if WATER_LOOKUP_FILE.exists():
        try:
            with open(WATER_LOOKUP_FILE, 'r') as f:
                lookup_data = json.load(f)
            
            # Also try without common suffixes
            for variant in city_variants[:]:
                if variant.endswith(' CITY'):
                    city_variants.append(variant[:-5])
            
            for city_variant in city_variants:
                city_key = f"{state}|{city_variant.strip()}"
                if city_key in lookup_data.get('by_city', {}):
                    result = lookup_data['by_city'][city_key].copy()
                    result['_confidence'] = 'high'
                    result['_source'] = 'epa_sdwis'
                    # Add confidence scoring
                    confidence_data = calculate_confidence(
                        source='epa_sdwis',
                        match_level='zip5',
                        utility_type='water'
                    )
                    result['confidence_score'] = confidence_data['score']
                    result['confidence_factors'] = [
                        f"{f['points']:+d}: {f['description']}" 
                        for f in confidence_data['factors']
                    ]
                    return result
            
            # Fall back to county lookup
            if county:
                county_key = f"{state}|{county.upper()}"
                if county_key in lookup_data.get('by_county', {}):
                    result = lookup_data['by_county'][county_key].copy()
                    result['_confidence'] = 'medium'
                    result['_source'] = 'epa_sdwis'
                    result['_note'] = 'Matched by county - verify for specific address'
                    # Add confidence scoring
                    confidence_data = calculate_confidence(
                        source='county_match',
                        match_level='county',
                        utility_type='water'
                    )
                    result['confidence_score'] = confidence_data['score']
                    result['confidence_factors'] = [
                        f"{f['points']:+d}: {f['description']}" 
                        for f in confidence_data['factors']
                    ]
                    # Log this city as missing from EPA city-level data
                    primary_city = city_variants[0] if city_variants else city
                    log_missing_water_city(state, primary_city, county, "county_fallback")
                    return result
        except (json.JSONDecodeError, IOError):
            pass
    
    # Fallback to heuristic if no local data
    heuristic_confidence = calculate_confidence(
        source='heuristic',
        match_level='county',
        utility_type='water'
    )
    heuristic_factors = [
        f"{f['points']:+d}: {f['description']}" 
        for f in heuristic_confidence['factors']
    ]
    
    if city:
        # Log this city as completely missing from EPA data
        log_missing_water_city(state, city, county, "heuristic")
        return {
            "name": f"City of {city} Water Utilities",
            "id": None,
            "state": state,
            "phone": None,
            "address": None,
            "city": city,
            "zip": None,
            "population_served": None,
            "source_type": None,
            "owner_type": "M",
            "service_connections": None,
            "_confidence": "low",
            "_source": "heuristic",
            "_note": "Estimated - no SDWA data available",
            "confidence_score": heuristic_confidence['score'],
            "confidence_factors": heuristic_factors
        }
    elif county:
        return {
            "name": f"{county} County Water",
            "id": None,
            "state": state,
            "phone": None,
            "address": None,
            "city": None,
            "zip": None,
            "population_served": None,
            "source_type": None,
            "owner_type": "L",
            "service_connections": None,
            "_confidence": "low",
            "_source": "heuristic",
            "_note": "Estimated - no SDWA data available",
            "confidence_score": heuristic_confidence['score'],
            "confidence_factors": heuristic_factors
        }
    
    return None


def _format_water_result(ws: Dict) -> Dict:
    """Format EPA SDWIS water system data into standard format."""
    return {
        "name": ws.get("pws_name"),
        "id": ws.get("pwsid"),
        "state": ws.get("state_code"),
        "phone": ws.get("phone_number"),
        "address": ws.get("address_line1"),
        "city": ws.get("city_name"),
        "zip": ws.get("zip_code"),
        "population_served": ws.get("population_served_count"),
        "source_type": ws.get("primary_source_code"),
        "owner_type": ws.get("owner_type_code"),
        "service_connections": ws.get("service_connections_count"),
    }

# =============================================================================
# INTERNET PROVIDER LOOKUP (FCC Broadband Map via Playwright)
# =============================================================================

def normalize_address_for_fcc(address: str) -> str:
    """
    Normalize address for FCC lookup by removing apartment/unit numbers.
    FCC Broadband Map only accepts building addresses, not unit-level.
    
    Examples:
    - "1725 Toomey Rd Apt 307 Austin TX 78704" -> "1725 Toomey Rd Austin TX 78704"
    - "123 Main St Unit 4B, City, ST 12345" -> "123 Main St, City, ST 12345"
    - "456 Oak Ave #201, Town, ST 54321" -> "456 Oak Ave, Town, ST 54321"
    """
    import re
    
    # Patterns to match apartment/unit designations
    # Match: Apt, Apt., Apartment, Unit, Ste, Suite, #, Fl, Floor, Bldg, Building
    # Followed by alphanumeric unit number
    patterns = [
        r'\s+(?:apt\.?|apartment)\s*#?\s*\w+',  # Apt 307, Apt. 4B, Apartment 12
        r'\s+(?:unit)\s*#?\s*\w+',              # Unit 4B, Unit #12
        r'\s+(?:ste\.?|suite)\s*#?\s*\w+',      # Ste 100, Suite 200
        r'\s+(?:fl\.?|floor)\s*#?\s*\d+',       # Fl 3, Floor 5
        r'\s+(?:bldg\.?|building)\s*#?\s*\w+',  # Bldg A, Building 2
        r'\s+#\s*\w+',                          # #201, # 4B
    ]
    
    normalized = address
    for pattern in patterns:
        normalized = re.sub(pattern, '', normalized, flags=re.IGNORECASE)
    
    # Clean up any double spaces
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    
    # Clean up comma spacing
    normalized = re.sub(r'\s*,\s*', ', ', normalized)
    
    return normalized


def generate_neighbor_addresses(address: str, offsets: list = None) -> list:
    """
    Generate nearby street addresses by adjusting the street number.
    FCC broadband data has gaps, but neighbors typically have the same providers.
    
    Args:
        address: Original address like "1542 N Hoover St, Los Angeles, CA 90027"
        offsets: List of offsets to try (default: [-6, -4, -2, +2, +4, +6])
    
    Returns:
        List of (address, offset) tuples to try
    """
    import re
    
    if offsets is None:
        offsets = [-6, -4, -2, 2, 4, 6]  # Try nearby even numbers first
    
    # Extract street number from beginning of address
    match = re.match(r'^(\d+)\s+(.+)$', address.strip())
    if not match:
        return []
    
    street_num = int(match.group(1))
    rest_of_address = match.group(2)
    
    neighbors = []
    for offset in offsets:
        new_num = street_num + offset
        if new_num > 0:
            new_address = f"{new_num} {rest_of_address}"
            neighbors.append((new_address, offset))
    
    return neighbors


def _lookup_internet_single(address: str) -> Optional[Dict]:
    """
    Internal function to look up internet providers for a single address.
    Returns None if address not found in FCC database.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright not installed, skipping internet lookup")
        return None
    
    # Normalize address to remove apartment/unit numbers
    normalized_address = normalize_address_for_fcc(address)
    
    result_data = None
    
    def handle_response(response):
        nonlocal result_data
        if "fabric/detail" in response.url and "hex" not in response.url and response.status == 200:
            try:
                result_data = response.json()
            except:
                pass
    
    try:
        with sync_playwright() as p:
            import os
            import sys
            display = os.environ.get('DISPLAY')
            use_headed = display is not None and display != ''
            
            browser = p.chromium.launch(
                headless=not use_headed,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-software-rasterizer'
                ]
            )
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            
            page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            """)
            
            page.on("response", handle_response)
            
            page.goto("https://broadbandmap.fcc.gov/", timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(5000)
            
            search_input = page.locator('#addrSearch')
            if not search_input.is_visible():
                browser.close()
                return None
            
            search_input.click()
            page.wait_for_timeout(500)
            page.keyboard.type(normalized_address, delay=80)
            page.wait_for_timeout(3000)
            
            content = page.content()
            address_street = normalized_address.split(',')[0].upper().strip()
            
            if address_street in content.upper():
                suggestion = page.locator(f'text={address_street}').first
                if suggestion.is_visible():
                    suggestion.click()
                    page.wait_for_timeout(8000)
            else:
                page.keyboard.press("ArrowDown")
                page.wait_for_timeout(500)
                page.keyboard.press("Enter")
                page.wait_for_timeout(8000)
            
            browser.close()
            
    except Exception as e:
        print(f"Playwright error: {e}")
        return None
    
    if not result_data:
        return None
    
    if result_data.get("status") != "successful" or not result_data.get("data"):
        return None
    
    return result_data


def _lookup_internet_postgres(block_geoid: str) -> Optional[Dict]:
    """Look up internet providers from PostgreSQL database."""
    database_url = os.environ.get('DATABASE_URL')
    if not database_url or not block_geoid:
        return None
    try:
        import psycopg2
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()
        cursor.execute("SELECT providers FROM internet_providers WHERE block_geoid = %s", (block_geoid,))
        row = cursor.fetchone()
        conn.close()
        if row and row[0]:
            providers_json = row[0] if isinstance(row[0], list) else json.loads(row[0])
            # Map FCC technology codes to names
            tech_names = {
                '50': 'Fiber', '40': 'Cable', '10': 'DSL', 
                '70': 'Fixed Wireless', '60': 'Satellite',
                50: 'Fiber', 40: 'Cable', 10: 'DSL',
                70: 'Fixed Wireless', 60: 'Satellite'
            }
            # Deduplicate by (name, technology, download, upload)
            seen = set()
            providers = []
            for p in providers_json:
                tech_code = p.get('tech')
                tech_name = tech_names.get(tech_code, tech_code)
                key = (p.get('name'), tech_code, p.get('down', 0), p.get('up', 0))
                if key not in seen:
                    seen.add(key)
                    providers.append({
                        'name': p.get('name'),
                        'technology': tech_name,
                        'technology_code': tech_code,
                        'max_download_mbps': p.get('down', 0),
                        'max_upload_mbps': p.get('up', 0),
                        'low_latency': p.get('low_lat', 0)
                    })
            return {
                "providers": providers,
                "provider_count": len(providers),
                "max_download": max((p.get('max_download_mbps', 0) for p in providers), default=0),
                "max_upload": max((p.get('max_upload_mbps', 0) for p in providers), default=0),
                "has_fiber": any('fiber' in str(p.get('technology', '')).lower() for p in providers),
                "has_cable": any('cable' in str(p.get('technology', '')).lower() for p in providers),
                "_source": "fcc_bdc_postgres",
                "_block_geoid": block_geoid
            }
    except Exception as e:
        print(f"  PostgreSQL lookup error: {e}")
    return None


def lookup_internet_providers(address: str, try_neighbors: bool = True) -> Optional[Dict]:
    """
    Look up internet providers using PostgreSQL (Railway), local SQLite, or Playwright fallback.
    
    Priority:
    1. PostgreSQL (if DATABASE_URL set) - fast, works on Railway
    2. Local SQLite BDC data - fast, local only
    3. Playwright FCC scraping - slow fallback (~25-30s)
    """
    # First, get the census block GEOID for this address
    geo_result = geocode_address(address, include_geography=True)
    block_geoid = geo_result.get('block_geoid') if geo_result else None
    
    database_url = os.environ.get('DATABASE_URL')
    print(f"  [Internet] block_geoid={block_geoid}, DATABASE_URL={'set' if database_url else 'NOT SET'}")
    
    # Try PostgreSQL first (Railway deployment)
    if block_geoid and database_url:
        print(f"  Trying PostgreSQL lookup for block {block_geoid}...")
        pg_result = _lookup_internet_postgres(block_geoid)
        if pg_result and pg_result.get('providers'):
            print(f"  PostgreSQL found {len(pg_result['providers'])} providers")
            return pg_result
        else:
            print(f"  PostgreSQL returned no providers for this block")
    
    # Try fast BDC local lookup (SQLite)
    try:
        from bdc_internet_lookup import lookup_internet_fast, get_available_states
        bdc_states = get_available_states()
        if bdc_states:
            print(f"  Trying fast BDC lookup (available states: {', '.join(bdc_states)})...")
            bdc_result = lookup_internet_fast(address)
            if bdc_result and bdc_result.get('providers'):
                print(f"  BDC lookup found {len(bdc_result['providers'])} providers")
                return {
                    "providers": bdc_result['providers'],
                    "provider_count": bdc_result['provider_count'],
                    "max_download": max((p.get('max_download_mbps', 0) for p in bdc_result['providers']), default=0),
                    "max_upload": max((p.get('max_upload_mbps', 0) for p in bdc_result['providers']), default=0),
                    "has_fiber": any(p.get('technology') == 'Fiber' for p in bdc_result['providers']),
                    "has_cable": any(p.get('technology') == 'Cable' for p in bdc_result['providers']),
                    "_source": bdc_result.get('source', 'fcc_bdc_local'),
                    "_block_geoid": bdc_result.get('block_geoid')
                }
            elif bdc_result:
                print(f"  BDC lookup: no providers for this block (may need more state data)")
    except ImportError:
        pass  # BDC module not available
    except Exception as e:
        print(f"  BDC lookup error: {e}")
    
    # Fall back to slow Playwright scraping
    print("  Falling back to Playwright (slow)...")
    
    # Normalize address first
    normalized_address = normalize_address_for_fcc(address)
    if normalized_address != address:
        print(f"  Normalized address for FCC: {normalized_address}")
    
    # Try the exact address first
    print(f"  Trying exact address: {normalized_address}")
    result_data = _lookup_internet_single(normalized_address)
    
    neighbor_used = None
    
    # If exact address failed and neighbors enabled, try nearby addresses
    if not result_data and try_neighbors:
        neighbors = generate_neighbor_addresses(normalized_address)
        if neighbors:
            print(f"  Exact address not in FCC database, trying {len(neighbors)} neighbor addresses...")
            for neighbor_addr, offset in neighbors:
                print(f"    Trying neighbor: {neighbor_addr} (offset {offset:+d})")
                result_data = _lookup_internet_single(neighbor_addr)
                if result_data:
                    neighbor_used = (neighbor_addr, offset)
                    print(f"    Found data from neighbor address!")
                    break
    
    if not result_data:
        print("FCC API: No data found for address or neighbors")
        return None
    
    # Process the captured API response
    location_data = result_data["data"][0]
    providers_raw = location_data.get("detail", [])
    
    # Process and dedupe providers
    providers = []
    seen = set()
    
    for p in providers_raw:
        key = f"{p.get('brand_name')}|{p.get('technology_code')}"
        if key in seen:
            continue
        seen.add(key)
        
        tech_code = str(p.get("technology_code", ""))
        provider = {
            "name": p.get("brand_name") or p.get("provider_name"),
            "provider_name": p.get("provider_name"),
            "holding_company": p.get("holding_company_name"),
            "technology": TECHNOLOGY_CODES.get(tech_code, tech_code),
            "technology_code": tech_code,
            "max_download_mbps": p.get("maxdown"),
            "max_upload_mbps": p.get("maxup"),
            "low_latency": p.get("lowlatency") == 1,
        }
        providers.append(provider)
    
    # Sort by download speed descending
    providers.sort(key=lambda x: x.get("max_download_mbps", 0) or 0, reverse=True)
    
    # Find best options by category
    best_fiber = None
    best_cable = None
    best_dsl = None
    best_wireless = None
    best_satellite = None
    
    for prov in providers:
        tech = prov.get("technology_code", "")
        if tech == "50" and not best_fiber:
            best_fiber = prov
        elif tech == "40" and not best_cable:
            best_cable = prov
        elif tech == "10" and not best_dsl:
            best_dsl = prov
        elif tech in WIRELESS_TECH_CODES and not best_wireless:
            best_wireless = prov
        elif tech in SATELLITE_TECH_CODES and not best_satellite:
            best_satellite = prov
    
    best_wired = best_fiber or best_cable or best_dsl
    
    result = {
        "location_id": location_data.get("location_id"),
        "address": location_data.get("address_primary"),
        "city": location_data.get("city"),
        "state": location_data.get("state"),
        "zip": location_data.get("zip_code"),
        "unit_count": location_data.get("unitCount", 1),
        "providers": providers,
        "provider_count": len(providers),
        "has_fiber": best_fiber is not None,
        "has_cable": best_cable is not None,
        "best_wired": best_wired,
        "best_wireless": best_wireless,
        "best_satellite": best_satellite,
    }
    
    # Add neighbor inference metadata if we used a neighbor address
    if neighbor_used:
        result["_neighbor_inference"] = True
        result["_neighbor_address"] = neighbor_used[0]
        result["_neighbor_offset"] = neighbor_used[1]
        result["_note"] = f"Data from nearby address ({neighbor_used[1]:+d} house numbers). Providers should be the same."
    
    return result
# =============================================================================
# RANKING AND FILTERING FUNCTIONS
# =============================================================================

def rank_electric_providers(providers: List[Dict], city: str = None, county: str = None) -> Tuple[Dict, List[Dict]]:
    """
    Rank electric providers to identify the most likely one.
    Returns (primary_provider, other_providers).
    """
    if not providers:
        return None, []
    
    if len(providers) == 1:
        providers[0]["_confidence"] = "high"
        return providers[0], []
    
    scored = []
    for p in providers:
        name = p.get("NAME", "").upper()
        score = 50  # Base score
        notes = []
        
        # Check if it's a city municipal utility matching the address city
        if city:
            city_upper = city.upper()
            if city_upper in name or f"CITY OF {city_upper}" in name:
                score += 30
                notes.append("City municipal match")
        
        # Large IOUs are usually correct when present
        large_ious = ["DUKE ENERGY", "DOMINION", "SOUTHERN COMPANY", "ENTERGY", 
                      "XCEL ENERGY", "AMERICAN ELECTRIC", "FIRSTENERGY", "PPL",
                      "PACIFIC GAS", "SOUTHERN CALIFORNIA EDISON", "CON EDISON",
                      "GEORGIA POWER", "FLORIDA POWER", "VIRGINIA ELECTRIC",
                      "PROGRESS ENERGY", "CAROLINA POWER", "CONSUMERS ENERGY",
                      "DTE ENERGY", "AMEREN", "EVERGY", "ONCOR", "CENTERPOINT",
                      "EVERSOURCE", "NATIONAL GRID", "PSEG", "EXELON", "COMMONWEALTH EDISON"]
        for iou in large_ious:
            if iou in name:
                score += 20
                notes.append("Major IOU")
                break
        
        # Rural EMCs are common in rural areas
        if "EMC" in name or "RURAL" in name or "COOPERATIVE" in name or "CO-OP" in name:
            score += 10
            notes.append("Rural cooperative")
        
        # Municipal utilities from OTHER cities should be deprioritized
        if "MUNICIPAL" in name or "CITY OF" in name or "TOWN OF" in name:
            if city and city.upper() not in name:
                score -= 20
                notes.append("Different city municipal")
        
        # Wholesale/transmission utilities are rarely retail providers
        if "WHOLESALE" in name or "TRANSMISSION" in name or "GENERATION" in name:
            score -= 30
            notes.append("Wholesale/transmission")
        
        p["_score"] = score
        p["_ranking_notes"] = notes
        scored.append(p)
    
    # Sort by score descending
    scored.sort(key=lambda x: x.get("_score", 0), reverse=True)
    
    primary = scored[0]
    others = scored[1:]
    
    # Set confidence based on score gap
    if len(others) > 0:
        score_gap = primary.get("_score", 0) - others[0].get("_score", 0)
        if score_gap >= 20:
            primary["_confidence"] = "high"
        else:
            primary["_confidence"] = "medium"
            primary["_note"] = f"Close match with {others[0].get('NAME', 'other provider')}"
    else:
        primary["_confidence"] = "high"
    
    return primary, others


def _water_fallback(city: str, state: str, reason: str) -> Dict:
    """Return a fallback water utility result with low confidence."""
    fallback_name = f"{city} Water Department" if city else f"{state} Water Utility"
    return {
        "name": fallback_name,
        "id": None,
        "state": state,
        "phone": None,
        "address": None,
        "city": city,
        "zip": None,
        "population_served": None,
        "source_type": None,
        "owner_type": None,
        "service_connections": None,
        "_confidence": "low",
        "_fallback_reason": reason,
    }


def filter_utilities_by_location(utilities: Union[Dict, List[Dict]], city: str = None) -> Union[Dict, List[Dict]]:
    """
    Filter utilities to remove municipal utilities from other cities.
    """
    if not utilities or not city:
        return utilities
    
    city_upper = city.upper()
    
    def is_relevant_utility(util: Dict) -> bool:
        name = util.get("NAME", "").upper()
        
        # Check if it's a municipal utility (CITY OF, VILLAGE OF, TOWN OF)
        municipal_prefixes = ["CITY OF ", "VILLAGE OF ", "TOWN OF "]
        for prefix in municipal_prefixes:
            if name.startswith(prefix):
                util_city = name[len(prefix):].strip().split(" - ")[0].split(",")[0].strip()
                return util_city == city_upper
        
        # Check for pattern like "OCONOMOWOC UTILITIES"
        municipal_suffixes = [" UTILITIES", " UTILITY", " ELECTRIC", " LIGHT", " POWER", " WATER & LIGHT", " ELECTRIC & WATER"]
        for suffix in municipal_suffixes:
            if name.endswith(suffix):
                util_city = name[:-len(suffix)].strip()
                if util_city and " " not in util_city:
                    return util_city == city_upper
        
        # Filter out wholesale power suppliers
        wholesale_indicators = ["WPPI ", "WHOLESALE", "GENERATION", "TRANSMISSION"]
        if any(indicator in name for indicator in wholesale_indicators):
            return False
        
        return True
    
    if isinstance(utilities, list):
        filtered = [u for u in utilities if is_relevant_utility(u)]
        if len(filtered) == 1:
            return filtered[0]
        return filtered if filtered else None
    else:
        return utilities if is_relevant_utility(utilities) else None


# =============================================================================
# SERP VERIFICATION FUNCTIONS
# =============================================================================

def verify_utility_with_serp(address: str, utility_type: str, candidate_name: str = None) -> Optional[Dict]:
    """
    Use BrightData proxy to search Google, then OpenAI to analyze results.
    Returns dict with verified provider info or None if unavailable.
    """
    if not BRIGHTDATA_PROXY_PASS:
        return None
    
    # Build search query
    query = f"{address} {utility_type} utility provider"
    search_url = f"https://www.google.com/search?q={requests.utils.quote(query)}"
    
    # Set up proxy
    proxy_url = f"http://{BRIGHTDATA_PROXY_USER}:{BRIGHTDATA_PROXY_PASS}@{BRIGHTDATA_PROXY_HOST}:{BRIGHTDATA_PROXY_PORT}"
    proxies = {
        "http": proxy_url,
        "https": proxy_url
    }
    
    try:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        response = requests.get(
            search_url,
            proxies=proxies,
            timeout=5,  # Phase 3: Hard timeout to avoid slowing down lookups
            verify=False
        )
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        for script in soup(["script", "style"]):
            script.decompose()
        
        search_text = soup.get_text(separator=' ')[:4000]
        
        if OPENAI_API_KEY:
            return analyze_serp_with_llm(search_text, address, utility_type, candidate_name)
        
        return analyze_serp_with_regex(search_text.upper(), candidate_name)
        
    except Exception as e:
        return None


def analyze_serp_with_llm(search_text: str, address: str, utility_type: str, candidate_name: str = None) -> Optional[Dict]:
    """Use OpenAI to analyze search results and identify the correct utility provider."""
    try:
        prompt = f"""Analyze these Google search results to identify the {utility_type} utility provider for the address: {address}

Search results:
{search_text}

Our database suggests: {candidate_name or 'Unknown'}

IMPORTANT: Only set matches_database to true if the search results explicitly confirm "{candidate_name}" serves this specific address. If the results mention a DIFFERENT provider (even if our database provider is also mentioned), set matches_database to false and return the provider the search results indicate is correct.

Based on the search results, what is the actual {utility_type} utility provider for this address?
Reply with ONLY a JSON object in this exact format:
{{"provider": "COMPANY NAME", "confidence": "high/medium/low", "matches_database": true/false, "notes": "brief explanation"}}"""

        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": 200
        }
        
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=15
        )
        response.raise_for_status()
        
        result = response.json()
        content = result["choices"][0]["message"]["content"]
        
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        
        llm_result = json.loads(content.strip())
        
        return {
            "verified": llm_result.get("matches_database", False),
            "serp_provider": llm_result.get("provider"),
            "confidence": llm_result.get("confidence", "medium"),
            "notes": llm_result.get("notes", "")
        }
        
    except Exception as e:
        return None


def analyze_serp_with_regex(combined_text: str, candidate_name: str = None) -> Optional[Dict]:
    """Fallback regex-based analysis when OpenAI is unavailable."""
    utility_patterns = [
        r'\b(BLUE RIDGE ENERGY)\b',
        r'\b(PIEDMONT NATURAL GAS)\b',
        r'\b(DUKE ENERGY[A-Z\s]*)\b',
        r'\b(FRONTIER NATURAL GAS)\b',
        r'\b([A-Z][A-Z]+\s+(?:ENERGY|ELECTRIC|GAS|WATER|UTILITIES))\b',
        r'\b(CITY OF [A-Z]+(?:\s+WATER)?)\b',
        r'\b(TOWN OF [A-Z]+)\b',
    ]
    
    found_utilities = []
    for pattern in utility_patterns:
        matches = re.findall(pattern, combined_text)
        found_utilities.extend(matches)
    
    found_utilities = list(set([
        u.strip() for u in found_utilities 
        if len(u) > 8 and len(u) < 50 and not any(x in u for x in ['SEARCH', 'GOOGLE', 'CLICK', 'SIGN', 'FILTER'])
    ]))
    
    if candidate_name and found_utilities:
        candidate_upper = candidate_name.upper()
        for found in found_utilities:
            if candidate_upper in found or found in candidate_upper:
                return {"verified": True, "serp_match": found, "confidence": "high"}
        return {"verified": False, "serp_suggestions": found_utilities[:3], "confidence": "low"}
    elif found_utilities:
        return {"verified": False, "serp_suggestions": found_utilities[:3], "confidence": "medium"}
    
    return None


# =============================================================================
# OUTPUT FORMATTING FUNCTIONS
# =============================================================================

def format_utility_result(utility: dict, utility_type: str = "ELECTRIC") -> str:
    """Format utility dict into readable output."""
    utility_id = utility.get('ID') or utility.get('SVCTERID') or utility.get('id', 'N/A')
    is_fallback = utility.get('_fallback', False)
    confidence = utility.get('_confidence')
    
    if confidence is None:
        if utility_type == "ELECTRIC":
            confidence = "high"
        elif utility_type == "NATURAL GAS":
            confidence = "medium"
        else:
            confidence = "low"
    
    confidence_labels = {
        "high": "✓",
        "medium": "⚠ verify",
        "low": "? estimated"
    }
    confidence_label = confidence_labels.get(confidence, "")
    
    header = f"{utility_type} UTILITY PROVIDER [{confidence_label}]"
    if is_fallback:
        header = f"{utility_type} UTILITY PROVIDER [⚠ estimated - largest in state]"
    elif confidence == "low" and utility.get('_note'):
        header = f"{utility_type} UTILITY PROVIDER [? estimated]"
    
    name = utility.get('NAME') or utility.get('name', 'N/A')
    state = utility.get('STATE') or utility.get('state', 'N/A')
    phone = utility.get('TELEPHONE') or utility.get('phone', 'N/A')
    website = utility.get('WEBSITE') or utility.get('website', 'N/A')
    address = utility.get('ADDRESS') or utility.get('address', 'N/A')
    city = utility.get('CITY') or utility.get('city', 'N/A')
    zip_code = utility.get('ZIP') or utility.get('zip', 'N/A')
    
    lines = [
        "",
        "=" * 50,
        header,
        "=" * 50,
        f"Name:      {name}",
        f"State:     {state}",
        f"Phone:     {phone}",
    ]
    
    if utility_type != "WATER":
        lines.append(f"Website:   {website}")
    
    lines.extend([
        f"Address:   {address}",
        f"City:      {city}",
        f"ZIP:       {zip_code}",
        f"Utility ID: {utility_id}",
    ])
    
    if utility_type == "NATURAL GAS":
        lines.append(f"Type:      {utility.get('TYPE', 'N/A')}")
    
    if utility_type == "WATER":
        pop = utility.get('population_served')
        if pop:
            lines.append(f"Pop Served: {pop:,}")
        source = utility.get('source_type')
        if source:
            source_desc = {"GW": "Groundwater", "GWP": "Groundwater", "SW": "Surface Water", "SWP": "Surface Water"}.get(source, source)
            lines.append(f"Source:    {source_desc}")
        total = utility.get('_total_matches')
        if total and total > 1:
            lines.append(f"Note:      {total} water systems serve this county")
    
    lines.append("=" * 50)
    return "\n".join(lines)


def format_internet_result(result: Dict) -> str:
    """Format internet provider results for display."""
    if not result:
        return "No internet provider data found."
    
    lines = [
        "",
        "=" * 50,
        "INTERNET PROVIDERS (FCC Broadband Map)",
        "=" * 50,
        f"Address:   {result.get('address')}",
        f"City:      {result.get('city')}, {result.get('state')} {result.get('zip')}",
        f"Providers: {result.get('provider_count')} available",
        f"Has Fiber: {'Yes' if result.get('has_fiber') else 'No'}",
        f"Has Cable: {'Yes' if result.get('has_cable') else 'No'}",
        ""
    ]
    
    best = result.get("best_wired")
    if best:
        lines.append(f"RECOMMENDED (Wired):")
        lines.append(f"  {best.get('name')} - {best.get('technology')}")
        lines.append(f"  Speed: {best.get('max_download_mbps')} Mbps down / {best.get('max_upload_mbps')} Mbps up")
        lines.append("")
    
    lines.append("ALL PROVIDERS:")
    for p in result.get("providers", []):
        speed = f"{p.get('max_download_mbps')}/{p.get('max_upload_mbps')} Mbps"
        lines.append(f"  - {p.get('name')}: {p.get('technology')} ({speed})")
    
    lines.append("=" * 50)
    return "\n".join(lines)


# =============================================================================
# JSON OUTPUT FUNCTION
# =============================================================================

def lookup_utility_json(address: str) -> Dict:
    """
    Returns structured JSON-friendly dict for integration.
    """
    result = {
        "input_address": address,
        "geocoded_address": None,
        "coordinates": None,
        "electric_utility": None,
        "gas_utility": None,
        "error": None
    }
    
    coords = geocode_address(address)
    if not coords:
        result["error"] = "Geocoding failed"
        return result
    
    lon, lat = coords["lon"], coords["lat"]
    result["coordinates"] = {"longitude": lon, "latitude": lat}
    
    electric = lookup_electric_utility(lon, lat)
    if electric:
        result["electric_utility"] = {
            "name": electric.get("NAME"),
            "id": electric.get("ID"),
            "state": electric.get("STATE"),
            "phone": electric.get("TELEPHONE"),
            "website": electric.get("WEBSITE"),
            "address": electric.get("ADDRESS"),
            "city": electric.get("CITY"),
            "zip": electric.get("ZIP"),
        }
    
    gas = lookup_gas_utility(lon, lat)
    if gas:
        result["gas_utility"] = {
            "name": gas.get("NAME"),
            "id": gas.get("SVCTERID"),
            "state": gas.get("STATE"),
            "phone": gas.get("TELEPHONE"),
            "website": gas.get("WEBSITE"),
            "address": gas.get("ADDRESS"),
            "city": gas.get("CITY"),
            "zip": gas.get("ZIP"),
            "type": gas.get("TYPE"),
        }
    
    if not electric and not gas:
        result["error"] = "No utilities found for location"
    
    return result


# =============================================================================
# NEW PIPELINE INTEGRATION
# =============================================================================

_pipeline_instance = None

def _get_pipeline():
    """Get or create the pipeline instance with all sources."""
    global _pipeline_instance
    if _pipeline_instance is None and PIPELINE_AVAILABLE:
        _pipeline_instance = LookupPipeline()
        _pipeline_instance.add_source(StateGISElectricSource())
        _pipeline_instance.add_source(MunicipalElectricSource())
        _pipeline_instance.add_source(CoopSource())
        _pipeline_instance.add_source(EIASource())
        _pipeline_instance.add_source(HIFLDElectricSource())
        _pipeline_instance.add_source(CountyDefaultElectricSource())
        _pipeline_instance.add_source(StateGISGasSource())
        _pipeline_instance.add_source(MunicipalGasSource())
        _pipeline_instance.add_source(ZIPMappingGasSource())
        _pipeline_instance.add_source(HIFLDGasSource())
        _pipeline_instance.add_source(CountyDefaultGasSource())
    return _pipeline_instance


def _pipeline_lookup(lat: float, lon: float, address: str, city: str, county: str, state: str, zip_code: str, utility_type: str) -> Optional[Dict]:
    """Use the new pipeline for utility lookup."""
    pipeline = _get_pipeline()
    if not pipeline:
        return None
    try:
        type_map = {'electric': UtilityType.ELECTRIC, 'gas': UtilityType.GAS, 'water': UtilityType.WATER}
        if utility_type not in type_map:
            return None
        context = LookupContext(lat=lat, lon=lon, address=address, city=city, county=county or '', state=state, zip_code=zip_code, utility_type=type_map[utility_type])
        result = pipeline.lookup(context)
        if not result or not result.utility_name:
            return None
        return {
            'NAME': result.utility_name, 'TELEPHONE': result.phone, 'WEBSITE': result.website,
            'STATE': state, 'CITY': city, '_confidence': result.confidence_level,
            'confidence_score': result.confidence_score, '_source': result.source,
            '_verification_source': result.source,
            '_selection_reason': f"Pipeline: {result.source} ({len(result.agreeing_sources)} sources agreed)" if result.sources_agreed else f"Pipeline: Smart Selector chose {result.source}",
            '_sources_agreed': result.sources_agreed, '_agreeing_sources': result.agreeing_sources,
            '_disagreeing_sources': result.disagreeing_sources, '_serp_verified': result.serp_verified,
        }
    except Exception as e:
        print(f"Pipeline lookup error: {e}")
        return None


# =============================================================================
# MAIN LOOKUP FUNCTION
# =============================================================================

def lookup_utilities_by_address(address: str, filter_by_city: bool = True, verify_with_serp: bool = False, selected_utilities: list = None, skip_internet: bool = False, use_pipeline: bool = True) -> Optional[Dict]:
    """
    Main function: takes an address string, returns electric, gas, water, and internet utility info.
    Uses city name to filter out municipal utilities from other cities.
    Optionally verifies gas/water with SERP search.
    
    Args:
        selected_utilities: List of utility types to look up. Default is all: ['electric', 'gas', 'water', 'internet']
        skip_internet: If True, skip internet lookup (faster)
    """
    # Default to all utilities if not specified
    if selected_utilities is None:
        selected_utilities = ['electric', 'gas', 'water', 'internet']
    
    # Remove internet from selected if skip_internet is True
    if skip_internet and 'internet' in selected_utilities:
        selected_utilities = [u for u in selected_utilities if u != 'internet']
    
    # Step 1: Geocode with geography info for filtering
    geo_result = geocode_address(address, include_geography=filter_by_city)
    if not geo_result:
        return None
    
    lon = geo_result["lon"]
    lat = geo_result["lat"]
    city = geo_result.get("city")
    state = geo_result.get("state")
    county = geo_result.get("county")
    
    # Get ZIP code from geocoded address for verification
    zip_code = geo_result.get("zip") or ""
    if not zip_code and geo_result.get("matched_address"):
        # Try to extract ZIP from END of matched address (avoid matching street numbers)
        # ZIP codes appear at the end, optionally with +4 extension
        zip_match = re.search(r'\b(\d{5})(?:-\d{4})?\s*$', geo_result.get("matched_address", ""))
        if zip_match:
            zip_code = zip_match.group(1)
    
    # ==========================================================================
    # NEW: Detect special areas (tribal lands, military bases, unincorporated)
    # ==========================================================================
    special_areas = get_special_area_info(
        lat=lat, lon=lon, zip_code=zip_code, city=city, state=state
    )
    
    # ==========================================================================
    # NEW: Detect building type for metering arrangement info
    # ==========================================================================
    building_type = detect_building_type_from_address(address)
    
    # ==========================================================================
    # NEW: Check if deregulated electricity market
    # ==========================================================================
    deregulated_info = None
    if is_deregulated_state(state):
        deregulated_info = get_deregulated_market_info(state)
    
    # Initialize results
    primary_electric = None
    other_electric = []
    primary_gas = None
    other_gas = []
    gas_no_service = None
    water = None
    internet = None
    
    # ==========================================================================
    # PRIORITY 0: Check corrections database FIRST
    # User-reported corrections override all other data sources
    # ==========================================================================
    corrections_applied = {}
    try:
        from corrections_lookup import check_correction
        
        for util_type in selected_utilities:
            correction = check_correction(
                state=state,
                zip_code=zip_code,
                city=city,
                utility_type=util_type,
                full_address=address
            )
            if correction:
                corrections_applied[util_type] = correction
                
    except ImportError:
        pass  # corrections_lookup module not available
    except Exception as e:
        print(f"Warning: corrections lookup failed: {e}")
    
    # Step 2: Electric lookup - only if selected
    if 'electric' in selected_utilities:
        # PRIORITY 0: Check if correction exists
        if 'electric' in corrections_applied:
            correction = corrections_applied['electric']
            primary_electric = {
                'NAME': correction['name'],
                'TELEPHONE': correction.get('phone'),
                'WEBSITE': correction.get('website'),
                'STATE': state,
                'CITY': city,
                '_confidence': correction.get('_confidence', 'user_reported'),
                '_verification_source': correction.get('_source', 'correction_db'),
                '_selection_reason': f"User-reported correction ({correction.get('_confirmation_count', 1)} confirmations)",
                '_is_deregulated': False
            }
            other_electric = []
        # PRIORITY 1: NEW PIPELINE with OpenAI Smart Selector
        elif use_pipeline and PIPELINE_AVAILABLE:
            pipeline_result = _pipeline_lookup(lat, lon, address, city, county, state, zip_code, 'electric')
            if pipeline_result:
                primary_electric = pipeline_result
                primary_electric['_is_deregulated'] = is_deregulated_state(state)
                if deregulated_info:
                    primary_electric = adjust_electric_result_for_deregulation(primary_electric, state, zip_code)
                other_electric = []
        # PRIORITY 2: GIS-based lookup for states with authoritative APIs (fallback)
        if primary_electric is None and GIS_LOOKUP_AVAILABLE and state in ('NJ', 'AR', 'DE', 'HI', 'RI', 'PA', 'WI', 'CO', 'WA', 'OR', 'UT', 'MA', 'VT', 'FL', 'IL', 'MS', 'OH', 'KY', 'AK', 'NE', 'CA', 'MI', 'TX', 'NY', 'ME', 'SC', 'IA', 'VA', 'IN', 'KS', 'DC', 'NC', 'MN'):
            gis_electric = lookup_electric_utility_gis(lat, lon, state)
            if gis_electric and gis_electric.get('name'):
                primary_electric = {
                    'NAME': gis_electric['name'],
                    'STATE': state,
                    'CITY': city,
                    '_confidence': gis_electric.get('confidence', 'high'),
                    '_verification_source': gis_electric.get('source', 'gis_state_api'),
                    '_selection_reason': f"GIS lookup from {gis_electric.get('source', 'state API')}",
                    '_is_deregulated': is_deregulated_state(state)
                }
                if deregulated_info:
                    primary_electric = adjust_electric_result_for_deregulation(primary_electric, state, zip_code)
                other_electric = []
            else:
                # Fall through to next priority
                primary_electric = None
        # PRIORITY 2: Check municipal utilities first (Austin Energy, CPS Energy, LADWP, etc.)
        if primary_electric is None and (municipal_electric := lookup_municipal_electric(state, city, zip_code)):
            primary_electric = {
                'NAME': municipal_electric['name'],
                'TELEPHONE': municipal_electric.get('phone'),
                'WEBSITE': municipal_electric.get('website'),
                'STATE': state,
                'CITY': municipal_electric.get('city', city),
                '_confidence': municipal_electric['confidence'],
                '_verification_source': 'municipal_utility_database',
                '_selection_reason': f"Municipal utility serving {municipal_electric.get('city', city)}",
                '_is_deregulated': False,
                '_note': municipal_electric.get('note')
            }
            other_electric = []
        elif primary_electric is None:
            # PRIORITY 2: HIFLD and state-specific verification
            electric_candidates = lookup_electric_utility(lon, lat)
            
            # Filter by city to remove irrelevant municipal utilities
            if filter_by_city and city:
                electric_candidates = filter_utilities_by_location(electric_candidates, city)
            
            # Convert to list if single result
            if electric_candidates and not isinstance(electric_candidates, list):
                electric_candidates = [electric_candidates]
            
            # Use state-specific verification
            verification_result = verify_electric_provider(
                state=state,
                zip_code=zip_code,
                city=city,
                county=county,
                candidates=electric_candidates or []
            )
            
            primary_electric = verification_result.get("primary")
            other_electric = verification_result.get("alternatives", [])
            
            # Add verification metadata to primary
            if primary_electric:
                primary_electric["_confidence"] = verification_result.get("confidence", "medium")
                primary_electric["_verification_source"] = verification_result.get("source")
                primary_electric["_selection_reason"] = verification_result.get("selection_reason")
                primary_electric["_is_deregulated"] = verification_result.get("is_deregulated")
                
                # NEW: Add deregulated market info if applicable
                if deregulated_info:
                    primary_electric = adjust_electric_result_for_deregulation(
                        primary_electric, state, zip_code
                    )
    
    # Step 3: Gas lookup - only if selected
    if 'gas' in selected_utilities:
        # PRIORITY 0: Check if correction exists
        if 'gas' in corrections_applied:
            correction = corrections_applied['gas']
            primary_gas = {
                'NAME': correction['name'],
                'TELEPHONE': correction.get('phone'),
                'WEBSITE': correction.get('website'),
                'STATE': state,
                'CITY': city,
                '_confidence': correction.get('_confidence', 'user_reported'),
                '_verification_source': correction.get('_source', 'correction_db'),
                '_selection_reason': f"User-reported correction ({correction.get('_confirmation_count', 1)} confirmations)"
            }
            other_gas = []
        # PRIORITY 1: NEW PIPELINE with OpenAI Smart Selector
        elif use_pipeline and PIPELINE_AVAILABLE:
            pipeline_result = _pipeline_lookup(lat, lon, address, city, county, state, zip_code, 'gas')
            if pipeline_result:
                primary_gas = pipeline_result
                other_gas = []
        # PRIORITY 2: Check municipal gas utilities (fallback)
        if primary_gas is None and (municipal_gas := lookup_municipal_gas(state, city, zip_code)):
            primary_gas = {
                'NAME': municipal_gas['name'],
                'TELEPHONE': municipal_gas.get('phone'),
                'WEBSITE': municipal_gas.get('website'),
                'STATE': state,
                'CITY': municipal_gas.get('city', city),
                '_confidence': municipal_gas['confidence'],
                '_verification_source': 'municipal_utility_database',
                '_selection_reason': f"Municipal utility providing gas in {municipal_gas.get('city', city)}"
            }
            other_gas = []
            gas_candidates = []
        # PRIORITY 3: HIFLD and state-specific verification
        if primary_gas is None:
            gas = lookup_gas_utility(lon, lat, state=state)
            
            # Filter by city to remove irrelevant municipal utilities
            if filter_by_city and city:
                gas = filter_utilities_by_location(gas, city)
            
            gas_candidates = gas if isinstance(gas, list) else ([gas] if gas else [])
            
            gas_verification = verify_gas_provider(
                state=state,
                zip_code=zip_code,
                city=city,
                county=county,
                candidates=gas_candidates
            )
            
            primary_gas = gas_verification.get("primary")
            other_gas = gas_verification.get("alternatives", [])
            
            # Add verification metadata to gas
            if primary_gas:
                primary_gas["_confidence"] = gas_verification.get("confidence", "medium")
                primary_gas["_verification_source"] = gas_verification.get("source")
                primary_gas["_selection_reason"] = gas_verification.get("selection_reason")
            
            # Handle no gas service case
            gas_no_service = gas_verification.get("no_service_note")
            
            # NEW: If no gas service, check if propane area
            if gas_no_service or not primary_gas:
                propane_info = is_likely_propane_area(state, zip_code, city)
                if propane_info.get("propane_likely"):
                    gas_no_service = get_no_gas_response(state, zip_code)
    
    # Step 4: Water lookup - only if selected
    # Priority: Corrections > Municipal utilities > Supplemental (city overrides) > Special districts > SERP > EPA SDWIS
    water_no_service = None
    if 'water' in selected_utilities:
        water = None
        
        # PRIORITY 0: Check if correction exists
        if 'water' in corrections_applied:
            correction = corrections_applied['water']
            water = {
                "name": correction['name'],
                "id": None,
                "state": state,
                "phone": correction.get('phone'),
                "address": None,
                "city": city,
                "zip": zip_code,
                "population_served": None,
                "source_type": None,
                "owner_type": "Unknown",
                "service_connections": None,
                "_confidence": correction.get('_confidence', 'user_reported'),
                "_source": correction.get('_source', 'correction_db'),
                "_note": f"User-reported correction ({correction.get('_confirmation_count', 1)} confirmations)"
            }
        # PRIORITY 1: Check municipal water utilities (LADWP, MLGW, etc.)
        elif (municipal_water := lookup_municipal_water(state, city, zip_code)):
            water = {
                "name": municipal_water['name'],
                "id": None,
                "state": state,
                "phone": municipal_water.get('phone'),
                "address": None,
                "city": municipal_water.get('city', city),
                "zip": zip_code,
                "population_served": None,
                "source_type": None,
                "owner_type": "Municipal",
                "service_connections": None,
                "_confidence": municipal_water['confidence'],
                "_source": "municipal_utility",
                "_note": f"Municipal utility providing water service"
            }
        
        # PRIORITY 2: Check supplemental file (city-level overrides, takes priority over MUDs)
        # This handles cases where cities have taken over MUD service areas
        if not water:
            supplemental_water = _check_water_supplemental(state, city)
            if supplemental_water:
                water = supplemental_water
        
        # PRIORITY 3: Check special districts (MUDs, CDDs)
        if not water:
            district = lookup_special_district(lat, lon, state, zip_code, 'water')
            if district:
                water = format_district_for_response(district)
                water['_source'] = 'special_district'
        
        # PRIORITY 3: SERP verification (if enabled)
        if not water and verify_with_serp:
            print(f"Looking up water provider via Google search...")
            serp_result = verify_utility_with_serp(address, "water", None)
            if serp_result and serp_result.get("serp_provider"):
                serp_provider = serp_result.get("serp_provider")
                serp_confidence = serp_result.get("confidence", "medium")
                print(f"  SERP found: {serp_provider} (confidence: {serp_confidence})")
                
                water = {
                    "name": serp_provider,
                    "id": None,
                    "state": state,
                    "phone": None,
                    "address": None,
                    "city": city,
                    "zip": None,
                    "population_served": None,
                    "source_type": None,
                    "owner_type": None,
                    "service_connections": None,
                    "_confidence": "high" if serp_confidence == "high" else "medium",
                    "_source": "google_serp",
                    "_serp_verified": True,
                    "_note": serp_result.get("notes", "Found via Google search")
                }
        
        # PRIORITY 4: Fall back to EPA/supplemental data
        if not water:
            water = lookup_water_utility(city, county, state, full_address=address,
                                        lat=lat, lon=lon, zip_code=zip_code)
        
        # If still no water provider, check if likely private well area
        if not water:
            from well_septic import get_well_septic_likelihood, get_no_public_water_response
            well_likelihood = get_well_septic_likelihood(state, is_incorporated=True, address=address)
            if well_likelihood.get('well_likelihood', 0) > 0.15:  # >15% likelihood
                water_no_service = get_no_public_water_response(state, county)
                water_no_service['_well_likelihood'] = f"{well_likelihood['well_likelihood']:.0%}"
            else:
                water_no_service = {
                    "note": "No public water provider found for this address. May use private well or small community system.",
                    "recommendations": ["Contact county health department", "Check property records for well permit"]
                }
    
    # Step 5: Internet lookup - only if selected
    if 'internet' in selected_utilities:
        print(f"Looking up internet providers...")
        internet = lookup_internet_providers(address=address)
        if internet:
            print(f"  Found {internet.get('provider_count', 0)} internet providers")
            if internet.get('has_fiber'):
                print(f"  Fiber available: {internet.get('best_wired', {}).get('name')}")
        else:
            print("  Could not retrieve internet provider data")
    
    # Step 6: Optional SERP verification for electric, gas, and water
    # Cost optimization: Skip SERP for authoritative sources (saves ~$0.01/lookup)
    serp_calls = 0
    serp_skipped = {'electric': False, 'gas': False, 'water': False}
    
    if verify_with_serp:
        # Verify electric - only if selected and not authoritative
        if 'electric' in selected_utilities and primary_electric:
            skip_serp, skip_reason = should_skip_serp(primary_electric, 'electric')
            if skip_serp:
                print(f"  ⏭ Skipping SERP for electric: {skip_reason}")
                primary_electric["_serp_skipped"] = True
                primary_electric["_skip_reason"] = skip_reason
                serp_skipped['electric'] = True
            else:
                electric_name = primary_electric.get("NAME") if isinstance(primary_electric, dict) else None
                if electric_name:
                    print(f"Verifying electric provider with SERP search...")
                    serp_calls += 1
                    serp_result = verify_utility_with_serp(address, "electric", electric_name)
                    if serp_result:
                        if serp_result.get("verified"):
                            primary_electric["_serp_verified"] = True
                            primary_electric["_confidence"] = "high"
                            print(f"  ✓ SERP verified: {electric_name}")
                        else:
                            primary_electric["_serp_verified"] = False
                            serp_provider = serp_result.get("serp_provider")
                            if serp_provider and other_electric:
                                for alt in other_electric:
                                    alt_name = alt.get("NAME", "")
                                    if serp_provider.upper() in alt_name.upper() or alt_name.upper() in serp_provider.upper():
                                        print(f"  ⚠ SERP suggests: {serp_provider} (swapping primary)")
                                        other_electric.remove(alt)
                                        other_electric.insert(0, primary_electric)
                                        primary_electric = alt
                                        primary_electric["_serp_verified"] = True
                                        primary_electric["_confidence"] = "high"
                                        break
                                else:
                                    print(f"  ⚠ SERP suggests: {serp_provider}")
                            else:
                                print(f"  ⚠ SERP suggests: {serp_result.get('serp_provider', 'unknown')}")
        
        # Verify gas - only if selected and not authoritative
        if 'gas' in selected_utilities:
            if primary_gas:
                skip_serp, skip_reason = should_skip_serp(primary_gas, 'gas')
                if skip_serp:
                    print(f"  ⏭ Skipping SERP for gas: {skip_reason}")
                    primary_gas["_serp_skipped"] = True
                    primary_gas["_skip_reason"] = skip_reason
                    serp_skipped['gas'] = True
                else:
                    gas_name = primary_gas.get("NAME") if isinstance(primary_gas, dict) else None
                    if gas_name:
                        print(f"Verifying gas provider with SERP search...")
                        serp_calls += 1
                        serp_result = verify_utility_with_serp(address, "natural gas", gas_name)
                        if serp_result:
                            if serp_result.get("verified"):
                                primary_gas["_serp_verified"] = True
                                primary_gas["_confidence"] = "high"
                                print(f"  ✓ SERP verified: {gas_name}")
                            else:
                                primary_gas["_serp_verified"] = False
                                primary_gas["_serp_suggestion"] = serp_result.get("serp_provider")
                                primary_gas["_confidence"] = "low"
                                print(f"  ⚠ SERP suggests: {serp_result.get('serp_provider', 'unknown')}")
            elif not gas_no_service:
                # No gas in HIFLD - try to find via SERP
                print(f"Searching for gas provider via SERP...")
                serp_result = verify_utility_with_serp(address, "natural gas", None)
                if serp_result and serp_result.get("serp_provider"):
                    primary_gas = {
                        "NAME": serp_result.get("serp_provider"),
                        "_source": "serp",
                        "_confidence": serp_result.get("confidence", "medium"),
                        "_notes": serp_result.get("notes", "Found via Google search")
                    }
                    print(f"  Found via SERP: {serp_result.get('serp_provider')}")
        
        # Verify water - only if selected AND not already from SERP
        if 'water' in selected_utilities and water:
            # Skip verification if water was already found via SERP (it's already verified)
            if water.get("_source") == "google_serp":
                serp_skipped['water'] = True  # Already verified via SERP
            else:
                skip_serp, skip_reason = should_skip_serp(water, 'water')
                if skip_serp:
                    print(f"  ⏭ Skipping SERP for water: {skip_reason}")
                    water["_serp_skipped"] = True
                    water["_skip_reason"] = skip_reason
                    serp_skipped['water'] = True
                else:
                    water_name = water.get("name") if isinstance(water, dict) else None
                    if water_name:
                        print(f"Verifying water provider with SERP search...")
                        serp_calls += 1
                        serp_result = verify_utility_with_serp(address, "water", water_name)
                        if serp_result:
                            if serp_result.get("verified"):
                                water["_serp_verified"] = True
                                water["_confidence"] = "high"
                                print(f"  ✓ SERP verified: {water_name}")
                            else:
                                # SERP found a different provider - use that instead
                                serp_provider = serp_result.get("serp_provider")
                                if serp_provider:
                                    print(f"  ⚠ SERP suggests different provider: {serp_provider}")
                                    # Replace with SERP result
                                    water = {
                                        "name": serp_provider,
                                        "id": None,
                                        "state": water.get("state"),
                                        "phone": None,
                                        "address": None,
                                        "city": water.get("city"),
                                        "zip": None,
                                        "population_served": None,
                                        "source_type": None,
                                        "owner_type": None,
                                        "service_connections": None,
                                        "_confidence": serp_result.get("confidence", "medium"),
                                        "_source": "google_serp",
                                        "_serp_verified": True,
                                        "_note": f"SERP override: {serp_result.get('notes', '')}"
                                    }
    
    # Build electric result - primary first, then others
    electric_result = None
    if primary_electric:
        if other_electric:
            electric_result = [primary_electric] + other_electric
        else:
            electric_result = primary_electric
    
    # Build gas result - primary first, then others
    gas_result = None
    if primary_gas:
        if other_gas:
            gas_result = [primary_gas] + other_gas
        else:
            gas_result = primary_gas
    
    # Check if this is a problem area for any utility type
    is_problem_electric = False
    is_problem_gas = False
    is_problem_water = False
    try:
        problem_check = check_problem_area(zip_code=zip_code, county=county, state=state, utility_type='electric')
        is_problem_electric = problem_check.get('is_problem_area', False) if problem_check else False
        problem_check = check_problem_area(zip_code=zip_code, county=county, state=state, utility_type='gas')
        is_problem_gas = problem_check.get('is_problem_area', False) if problem_check else False
        problem_check = check_problem_area(zip_code=zip_code, county=county, state=state, utility_type='water')
        is_problem_water = problem_check.get('is_problem_area', False) if problem_check else False
    except Exception:
        pass  # Don't fail lookup if problem area check fails
    
    # Add confidence score to water result
    if water:
        water_source = water.get('_source', 'unknown')
        water_match = 'special_district' if water_source == 'special_district' else 'zip5'
        if water.get('_match_method') == 'coordinates':
            water_match = 'address'
        
        water_confidence = calculate_confidence(
            source=source_to_score_key(water_source),
            match_level=water_match,
            is_problem_area=is_problem_water,
            utility_type='water',
            state=state
        )
        water['confidence_score'] = water_confidence['score']
        water['confidence_factors'] = [
            f"{f['points']:+d}: {f['description']}" 
            for f in water_confidence['factors']
        ]
    
    # NEW: FindEnergy verification for electric (cross-check against EIA/HIFLD)
    findenergy_verification = {}
    if primary_electric and city:
        try:
            elec_name = primary_electric.get('NAME', '')
            # Also try brand name resolution for verification
            elec_brand, _ = resolve_brand_name_with_fallback(elec_name, state)
            
            fe_verify = verify_against_findenergy(
                provider_name=elec_name,
                city=city,
                state=state,
                zip_code=zip_code,
                utility_type='electric'
            )
            # If legal name didn't verify, try brand name
            if fe_verify and not fe_verify.get('verified') and elec_brand != elec_name:
                fe_verify_brand = verify_against_findenergy(
                    provider_name=elec_brand,
                    city=city,
                    state=state,
                    zip_code=zip_code,
                    utility_type='electric'
                )
                if fe_verify_brand and fe_verify_brand.get('verified'):
                    fe_verify = fe_verify_brand
            
            if fe_verify:
                findenergy_verification['electric'] = fe_verify
                # If FindEnergy disagrees and has high confidence, flag it
                if not fe_verify.get('verified') and fe_verify.get('recommendation') == 'use_findenergy':
                    primary_electric['_findenergy_disagrees'] = True
                    primary_electric['_findenergy_suggestion'] = fe_verify.get('findenergy_providers', [])[:1]
                elif fe_verify.get('verified'):
                    primary_electric['_findenergy_verified'] = True
        except Exception as e:
            pass  # Don't fail lookup if FindEnergy check fails
    
    # NEW: FindEnergy verification for gas
    if primary_gas and city:
        try:
            gas_name = primary_gas.get('NAME', '')
            # Also try brand name resolution for verification
            gas_brand, _ = resolve_brand_name_with_fallback(gas_name, state)
            
            fe_verify = verify_against_findenergy(
                provider_name=gas_name,
                city=city,
                state=state,
                zip_code=zip_code,
                utility_type='gas'
            )
            # If legal name didn't verify, try brand name
            if fe_verify and not fe_verify.get('verified') and gas_brand != gas_name:
                fe_verify_brand = verify_against_findenergy(
                    provider_name=gas_brand,
                    city=city,
                    state=state,
                    zip_code=zip_code,
                    utility_type='gas'
                )
                if fe_verify_brand and fe_verify_brand.get('verified'):
                    fe_verify = fe_verify_brand
            
            if fe_verify:
                findenergy_verification['gas'] = fe_verify
                if not fe_verify.get('verified') and fe_verify.get('recommendation') == 'use_findenergy':
                    primary_gas['_findenergy_disagrees'] = True
                    primary_gas['_findenergy_suggestion'] = fe_verify.get('findenergy_providers', [])[:1]
                elif fe_verify.get('verified'):
                    primary_gas['_findenergy_verified'] = True
        except Exception as e:
            pass
    
    # Add confidence score to electric result (preserve pipeline score if present)
    if primary_electric:
        if not primary_electric.get('confidence_score'):
            elec_source = primary_electric.get('_verification_source', 'hifld')
            elec_confidence = calculate_confidence(
                source=source_to_score_key(elec_source),
                match_level='zip5',
                is_problem_area=is_problem_electric,
                utility_type='electric',
                state=state
            )
            primary_electric['confidence_score'] = elec_confidence['score']
            primary_electric['confidence_factors'] = [
                f"{f['points']:+d}: {f['description']}" 
                for f in elec_confidence['factors']
            ]
        elif not primary_electric.get('confidence_factors'):
            primary_electric['confidence_factors'] = [f"+{primary_electric['confidence_score']}: Pipeline ({primary_electric.get('_source', 'unknown')})"]
    
    # Add confidence score to gas result (preserve pipeline score if present)
    if primary_gas:
        if not primary_gas.get('confidence_score'):
            gas_source = primary_gas.get('_verification_source') or primary_gas.get('_source', 'hifld')
            gas_confidence = calculate_confidence(
                source=source_to_score_key(gas_source),
                match_level='zip5',
                is_problem_area=is_problem_gas,
                utility_type='gas',
                state=state
            )
            primary_gas['confidence_score'] = gas_confidence['score']
            primary_gas['confidence_factors'] = [
                f"{f['points']:+d}: {f['description']}" 
                for f in gas_confidence['factors']
            ]
        elif not primary_gas.get('confidence_factors'):
            primary_gas['confidence_factors'] = [f"+{primary_gas['confidence_score']}: Pipeline ({primary_gas.get('_source', 'unknown')})"]
    
    result = {
        "electric": electric_result,
        "gas": gas_result,
        "gas_no_service": gas_no_service,  # Set if no gas service available
        "water": water,
        "water_no_service": water_no_service,  # Set if no public water (likely private well)
        "internet": internet,
        "location": {
            "city": city,
            "county": county,
            "state": state,
            "zip_code": zip_code
        },
        # NEW: Phase 12-14 metadata
        "_metadata": {
            "building_type": building_type.value if building_type else None,
            "deregulated_market": deregulated_info is not None,
            "deregulated_info": deregulated_info,
            "special_areas": special_areas.get("special_areas", []),
            "requires_special_handling": special_areas.get("requires_special_handling", False),
            "findenergy_verification": findenergy_verification if findenergy_verification else None
        }
    }
    
    # NEW: Add special area notes if applicable
    if special_areas.get("notes"):
        result["_special_area_notes"] = special_areas["notes"]
    
    # NEW: Add tribal land info if applicable
    if special_areas.get("tribal_info"):
        result["_tribal_info"] = special_areas["tribal_info"]
    
    # NEW: Add military base info if applicable
    if special_areas.get("military_info"):
        result["_military_info"] = special_areas["military_info"]
    
    # NEW: Adjust results for building type (add metering notes)
    if building_type:
        result = adjust_result_for_building_type(result, address, building_type)
    
    # NEW: Detect anomalies (results that differ from ZIP patterns)
    anomalies = detect_anomalies(result, zip_code)
    if anomalies:
        result["_anomalies"] = anomalies
    
    # NEW: Resolve legal names to consumer-facing brand names
    if primary_electric and primary_electric.get('NAME'):
        brand, legal = resolve_brand_name_with_fallback(primary_electric['NAME'], state)
        if legal:  # Brand differs from legal name
            primary_electric['_legal_name'] = legal
            primary_electric['NAME'] = brand
    
    if primary_gas and primary_gas.get('NAME'):
        brand, legal = resolve_brand_name_with_fallback(primary_gas['NAME'], state)
        if legal:  # Brand differs from legal name
            primary_gas['_legal_name'] = legal
            primary_gas['NAME'] = brand
    
    if water and water.get('name'):
        brand, legal = resolve_brand_name_with_fallback(water['name'], state)
        if legal:  # Brand differs from legal name
            water['_legal_name'] = legal
            water['name'] = brand
    
    # Log lookup for validation
    try:
        log_lookup(
            address=address,
            city=city,
            county=county,
            state=state,
            zip_code=zip_code,
            electric_provider=primary_electric.get('NAME') if primary_electric else None,
            gas_provider=primary_gas.get('NAME') if primary_gas else None,
            water_provider=water.get('name') if water else None,
            internet_count=internet.get('provider_count') if internet else None
        )
    except Exception:
        pass  # Don't fail lookup if logging fails
    
    # NEW: LLM reasoning layer - analyze all candidates with geographic context
    # This catches errors like "North Shore Gas serves north suburbs, Glencoe is a north suburb"
    try:
        from llm_analyzer import analyze_utility_candidates, get_openai_key
        if get_openai_key():
            # Analyze gas (most error-prone due to complex territories)
            if primary_gas:
                gas_candidates = [primary_gas] + (other_gas or [])
                llm_result = analyze_utility_candidates(
                    address=address,
                    city=city,
                    county=county,
                    state=state,
                    zip_code=zip_code,
                    utility_type="gas",
                    candidates=gas_candidates,
                    database_recommendation=primary_gas
                )
                if llm_result and llm_result.get("llm_used"):
                    primary_gas["_llm_analyzed"] = True
                    if not llm_result.get("matches_database", True):
                        # LLM disagrees with our recommendation
                        primary_gas["_llm_override"] = llm_result["provider"]
                        primary_gas["_llm_reasoning"] = llm_result["reasoning"]
                        primary_gas["_llm_confidence"] = llm_result["confidence"]
                        # Add note for user
                        primary_gas["_note"] = f"AI suggests: {llm_result['provider']}. {llm_result['reasoning']}"
                    else:
                        primary_gas["_llm_verified"] = True
            
            # Analyze electric (less error-prone but still useful)
            if primary_electric:
                elec_candidates = [primary_electric] + (other_electric or [])
                llm_result = analyze_utility_candidates(
                    address=address,
                    city=city,
                    county=county,
                    state=state,
                    zip_code=zip_code,
                    utility_type="electric",
                    candidates=elec_candidates,
                    database_recommendation=primary_electric
                )
                if llm_result and llm_result.get("llm_used"):
                    primary_electric["_llm_analyzed"] = True
                    if not llm_result.get("matches_database", True):
                        primary_electric["_llm_override"] = llm_result["provider"]
                        primary_electric["_llm_reasoning"] = llm_result["reasoning"]
                    else:
                        primary_electric["_llm_verified"] = True
    except Exception as e:
        pass  # Don't fail lookup if LLM analysis fails
    
    return result


# =============================================================================
# INDIVIDUAL UTILITY LOOKUPS (for streaming API)
# =============================================================================

def _zip_only_fallback(address: str) -> Optional[Dict]:
    """
    Fallback when all geocoders fail - extract ZIP code and return partial result.
    This allows utility lookup by ZIP even for unusual/new addresses.
    """
    import re
    
    # Extract ZIP code
    zip_match = re.search(r'\b(\d{5})(?:-\d{4})?\b', address)
    if not zip_match:
        return None
    
    zip_code = zip_match.group(1)
    
    # Try to extract state from address
    state = None
    state_match = re.search(r',\s*([A-Z]{2})\s*\d{5}', address.upper())
    if state_match:
        state = state_match.group(1)
    
    # Try to extract city
    city = None
    city_match = re.search(r',\s*([A-Za-z\s]+),\s*[A-Z]{2}\s*\d{5}', address)
    if city_match:
        city = city_match.group(1).strip()
    
    print(f"Geocoding failed - using ZIP-only fallback for {zip_code}")
    
    return {
        "lat": None,
        "lon": None,
        "city": city,
        "county": None,
        "state": state,
        "zip_code": zip_code,
        "formatted_address": address,
        "_zip_only_fallback": True,
        "_note": "Address could not be geocoded - results based on ZIP code only"
    }


def geocode_address_streaming(address: str) -> Optional[Dict]:
    """
    Geocode an address and return location info.
    Used by streaming API to get location first, then lookup utilities.
    Falls back to ZIP-only lookup if all geocoders fail.
    """
    # Try Census geocoder first (with geography for city/county/state)
    geocode_result = geocode_with_census(address, include_geography=True)
    
    if not geocode_result:
        # Try Google Maps fallback
        geocode_result = geocode_with_google(address)
    
    if not geocode_result:
        # Try Nominatim as third fallback
        geocode_result = geocode_with_nominatim(address)
    
    if not geocode_result:
        # ZIP-only fallback - extract ZIP and return partial result
        return _zip_only_fallback(address)
    
    lat = geocode_result.get("lat")
    lon = geocode_result.get("lon")
    city = geocode_result.get("city")
    county = geocode_result.get("county")
    state = geocode_result.get("state")
    zip_code = geocode_result.get("zip")
    
    # Extract ZIP from matched_address if not provided directly
    if not zip_code and geocode_result.get("matched_address"):
        import re
        zip_match = re.search(r'\b(\d{5})(?:-\d{4})?\b', geocode_result["matched_address"])
        if zip_match:
            zip_code = zip_match.group(1)
    
    # Also try extracting from original address if still missing
    if not zip_code:
        import re
        zip_match = re.search(r'\b(\d{5})(?:-\d{4})?\b', address)
        if zip_match:
            zip_code = zip_match.group(1)
    
    return {
        "lat": lat,
        "lon": lon,
        "city": city,
        "county": county,
        "state": state,
        "zip_code": zip_code,
        "formatted_address": geocode_result.get("matched_address", geocode_result.get("formatted_address"))
    }


def _add_deregulated_info(result: Dict, state: str, zip_code: str) -> Dict:
    """Add deregulated market info to electric result if applicable."""
    if not result:
        return result
    from deregulated_markets import is_deregulated_state, adjust_electric_result_for_deregulation
    if is_deregulated_state(state):
        # Check if this is a municipal utility (exempt from deregulation)
        is_municipal = (
            result.get('_verification_source') == 'municipal_utility_database' or
            'municipal' in result.get('NAME', '').lower() or
            'city of' in result.get('NAME', '').lower()
        )
        if is_municipal:
            result['_deregulated_market'] = False
            result['_note'] = 'Municipal utility - exempt from retail choice'
        else:
            result = adjust_electric_result_for_deregulation(result, state, zip_code)
    return result


def lookup_electric_only(lat: float, lon: float, city: str, county: str, state: str, zip_code: str, address: str = None) -> Optional[Dict]:
    """Look up electric utility only. Fast - typically < 1 second.
    
    If address is provided and state supports website verification, 
    the result will be enhanced with utility website verification.
    """
    try:
        # Priority 0: GIS-based lookup for states with authoritative APIs (NJ, AR, DE, HI, RI)
        if GIS_LOOKUP_AVAILABLE and lat and lon and state in ('NJ', 'AR', 'DE', 'HI', 'RI'):
            gis_electric = lookup_electric_utility_gis(lat, lon, state)
            if gis_electric and gis_electric.get('name'):
                result = {
                    'NAME': gis_electric['name'],
                    'STATE': state,
                    'CITY': city,
                    '_confidence': gis_electric.get('confidence', 'high'),
                    '_verification_source': gis_electric.get('source', 'gis_state_api')
                }
                return _add_deregulated_info(result, state, zip_code)
        
        # Check municipal first (exempt from deregulation)
        municipal_electric = lookup_municipal_electric(state, city, zip_code)
        if municipal_electric:
            result = {
                'NAME': municipal_electric['name'],
                'TELEPHONE': municipal_electric.get('phone'),
                'WEBSITE': municipal_electric.get('website'),
                'STATE': state,
                'CITY': municipal_electric.get('city', city),
                '_confidence': municipal_electric['confidence'],
                '_verification_source': 'municipal_utility_database'
            }
            return _add_deregulated_info(result, state, zip_code)
        
        # Check electric cooperatives by ZIP (rural areas)
        from rural_utilities import lookup_coop_by_zip, lookup_coop_by_county, lookup_county_default_electric
        coop = lookup_coop_by_zip(zip_code, state)
        if coop:
            result = {
                'NAME': coop['name'],
                'TELEPHONE': coop.get('phone'),
                'WEBSITE': coop.get('website'),
                'STATE': state,
                'CITY': city,
                '_confidence': coop['confidence'],
                '_verification_source': coop['source']
            }
            # Check if this is actually a TDU in a deregulated market (not a true co-op)
            is_tdu = 'deregulated' in coop.get('note', '').lower() or coop.get('is_tdu', False)
            if is_tdu:
                # This is a TDU, apply deregulated market info
                return _add_deregulated_info(result, state, zip_code)
            else:
                # True co-ops are exempt from deregulation
                result['_deregulated_market'] = False
                result['_note'] = 'Electric cooperative - exempt from retail choice'
                return result
        
        # Check EIA ZIP lookup (authoritative source)
        from state_utility_verification import get_eia_utility_by_zip
        eia_result = get_eia_utility_by_zip(zip_code)
        if eia_result:
            eia_primary = eia_result[0]
            result = {
                'NAME': eia_primary['name'],
                'TELEPHONE': None,
                'WEBSITE': None,
                'STATE': state,
                'CITY': city,
                '_confidence': 'medium',
                '_verification_source': 'eia_zip_lookup',
                '_note': f"Based on ZIP {zip_code} - {eia_primary.get('ownership', 'Unknown')} utility"
            }
            return _add_deregulated_info(result, state, zip_code)
        
        # HIFLD lookup (requires lat/lon)
        electric = None
        if lat is not None and lon is not None:
            electric = lookup_electric_utility(lon, lat)
        if not electric:
            # Try co-op by county as fallback (exempt from deregulation)
            coop = lookup_coop_by_county(county, state)
            if coop:
                result = {
                    'NAME': coop['name'],
                    'TELEPHONE': coop.get('phone'),
                    'WEBSITE': coop.get('website'),
                    'STATE': state,
                    'CITY': city,
                    '_confidence': coop['confidence'],
                    '_verification_source': coop['source'],
                    '_deregulated_market': False,
                    '_note': 'Electric cooperative - exempt from retail choice'
                }
                return result
            # Try county default as last resort
            county_default = lookup_county_default_electric(county, state)
            if county_default:
                result = {
                    'NAME': county_default['name'],
                    'TELEPHONE': county_default.get('phone'),
                    'WEBSITE': county_default.get('website'),
                    'STATE': state,
                    'CITY': city,
                    '_confidence': county_default['confidence'],
                    '_verification_source': county_default['source']
                }
                return _add_deregulated_info(result, state, zip_code)
            return None
        
        electric_candidates = electric if isinstance(electric, list) else ([electric] if electric else [])
        
        # Verify
        verification = verify_electric_provider(
            state=state,
            zip_code=zip_code,
            city=city,
            county=county,
            candidates=electric_candidates
        )
        
        primary = verification.get("primary")
        if primary:
            primary["_confidence"] = verification.get("confidence", "medium")
            primary["_verification_source"] = verification.get("source")
            
            # Brand name resolution
            if primary.get('NAME'):
                brand, legal = resolve_brand_name_with_fallback(primary['NAME'], state)
                if legal:
                    primary['_legal_name'] = legal
                    primary['NAME'] = brand
            
            # Add deregulated market info if applicable
            from deregulated_markets import is_deregulated_state, adjust_electric_result_for_deregulation
            if is_deregulated_state(state):
                primary = adjust_electric_result_for_deregulation(primary, state, zip_code)
            
            # Enhance with utility website verification if address provided
            if address and state in get_supported_states():
                primary = enhance_lookup_with_verification(
                    primary, address, city, state, zip_code
                )
        
        return primary
    except Exception as e:
        print(f"Electric lookup error: {e}")
        return None


def lookup_gas_only(lat: float, lon: float, city: str, county: str, state: str, zip_code: str) -> Optional[Dict]:
    """Look up gas utility only. Fast - typically < 1 second."""
    try:
        # Check municipal first
        municipal_gas = lookup_municipal_gas(state, city, zip_code)
        if municipal_gas:
            return {
                'NAME': municipal_gas['name'],
                'TELEPHONE': municipal_gas.get('phone'),
                'WEBSITE': municipal_gas.get('website'),
                'STATE': state,
                'CITY': municipal_gas.get('city', city),
                '_confidence': municipal_gas['confidence'],
                '_verification_source': 'municipal_utility_database'
            }
        
        # HIFLD lookup (requires lat/lon)
        gas = None
        if lat is not None and lon is not None:
            gas = lookup_gas_utility(lon, lat, state=state)
        if not gas:
            # FIRST: Try state-specific ZIP prefix mappings (most accurate)
            from state_utility_verification import get_state_gas_ldc
            state_gas_result = get_state_gas_ldc(state, zip_code, city)
            if state_gas_result and state_gas_result.get("primary"):
                return {
                    'NAME': state_gas_result["primary"]["name"],
                    'TELEPHONE': state_gas_result["primary"].get("phone"),
                    'WEBSITE': state_gas_result["primary"].get("website"),
                    'STATE': state,
                    'CITY': city,
                    '_confidence': state_gas_result.get("confidence", "high"),
                    '_verification_source': state_gas_result["source"]
                }
            
            # SECOND: Try county default for gas
            from rural_utilities import lookup_county_default_gas
            county_default = lookup_county_default_gas(county, state)
            if county_default:
                return {
                    'NAME': county_default['name'],
                    'TELEPHONE': county_default.get('phone'),
                    'WEBSITE': county_default.get('website'),
                    'STATE': state,
                    'CITY': city,
                    '_confidence': county_default['confidence'],
                    '_verification_source': county_default['source']
                }
            # Check if propane area
            propane_info = is_likely_propane_area(state, zip_code, city)
            if propane_info.get("propane_likely"):
                return {
                    'NAME': 'No piped natural gas',
                    '_no_service': True,
                    '_note': get_no_gas_response(state, zip_code)
                }
            return None
        
        gas_candidates = gas if isinstance(gas, list) else ([gas] if gas else [])
        
        # Verify
        verification = verify_gas_provider(
            state=state,
            zip_code=zip_code,
            city=city,
            county=county,
            candidates=gas_candidates
        )
        
        primary = verification.get("primary")
        if primary:
            primary["_confidence"] = verification.get("confidence", "medium")
            primary["_verification_source"] = verification.get("source")
            
            # Brand name resolution
            if primary.get('NAME'):
                brand, legal = resolve_brand_name_with_fallback(primary['NAME'], state)
                if legal:
                    primary['_legal_name'] = legal
                    primary['NAME'] = brand
        
        return primary
    except Exception as e:
        print(f"Gas lookup error: {e}")
        return None


def lookup_water_only(lat: float, lon: float, city: str, county: str, state: str, zip_code: str, address: str = None) -> Optional[Dict]:
    """Look up water utility only. Fast - typically < 1 second."""
    try:
        # Note: Special districts (MUDs/CDDs) are checked AFTER municipal/GIS
        # because major cities (Houston, Austin, Dallas) provide municipal water
        # even in areas that have MUD boundaries. MUDs are primarily for:
        # - New developments outside city limits
        # - Unincorporated areas
        # We'll add MUD info as a note when relevant, not as primary provider
        
        # Priority 1: GIS-based lookup (EPA CWS boundaries - most authoritative)
        if GIS_LOOKUP_AVAILABLE and lat and lon:
            gis_water = lookup_water_utility_gis(lat, lon, state)
            if gis_water and gis_water.get('name'):
                gis_name = gis_water['name'].upper()
                city_upper = (city or '').upper()
                
                # Validate: if GIS result doesn't match city, check if we should use municipal instead
                # This handles boundary edge cases (e.g., point near Chicago returning Evanston)
                city_matches = (
                    city_upper in gis_name or 
                    gis_name in city_upper or
                    city_upper.replace(' ', '') in gis_name.replace(' ', '')
                )
                
                if city_matches:
                    # GIS result matches city - use it, but try to enrich with contact info
                    result = {
                        "NAME": gis_water['name'],
                        "PWSID": gis_water.get('pwsid'),
                        "STATE": gis_water.get('state') or state,
                        "CITY": city,
                        "_confidence": gis_water.get('confidence', 'high'),
                        "_source": gis_water.get('source', 'gis_epa')
                    }
                    # Try to enrich with contact info from municipal database
                    municipal_water = lookup_municipal_water(state, city, zip_code)
                    if municipal_water:
                        result["TELEPHONE"] = municipal_water.get('phone')
                        result["WEBSITE"] = municipal_water.get('website')
                    return result
                else:
                    # GIS result doesn't match city - check municipal first
                    municipal_water = lookup_municipal_water(state, city, zip_code)
                    if municipal_water:
                        return {
                            "NAME": municipal_water['name'],
                            "TELEPHONE": municipal_water.get('phone'),
                            "WEBSITE": municipal_water.get('website'),
                            "STATE": state,
                            "CITY": municipal_water.get('city', city),
                            "_confidence": municipal_water['confidence'],
                            "_source": "municipal_utility"
                        }
                    # No municipal match - use GIS result anyway (it's still authoritative)
                    return {
                        "NAME": gis_water['name'],
                        "PWSID": gis_water.get('pwsid'),
                        "STATE": gis_water.get('state') or state,
                        "CITY": city,
                        "_confidence": 'medium',  # Lower confidence due to city mismatch
                        "_source": gis_water.get('source', 'gis_epa'),
                        "_note": f"GIS boundary lookup - verify with {city} water department"
                    }
        
        # Priority 2: Municipal
        municipal_water = lookup_municipal_water(state, city, zip_code)
        if municipal_water:
            return {
                "NAME": municipal_water['name'],
                "TELEPHONE": municipal_water.get('phone'),
                "WEBSITE": municipal_water.get('website'),
                "STATE": state,
                "CITY": municipal_water.get('city', city),
                "_confidence": municipal_water['confidence'],
                "_source": "municipal_utility"
            }
        
        # Priority 3: Supplemental (city overrides)
        supplemental = _check_water_supplemental(state, city)
        if supplemental:
            return supplemental
        
        # Priority 4: Special districts (MUDs/CDDs) - only for unincorporated areas
        # Major Texas cities (Houston, Austin, Dallas, San Antonio, Fort Worth) have municipal water
        # MUDs are primarily for new developments OUTSIDE city limits
        major_tx_cities = ['HOUSTON', 'AUSTIN', 'DALLAS', 'SAN ANTONIO', 'FORT WORTH', 'EL PASO', 
                          'ARLINGTON', 'PLANO', 'IRVING', 'FRISCO', 'MCKINNEY', 'DENTON']
        city_upper = (city or '').upper()
        
        # Only use MUD if NOT in a major city
        if city_upper not in major_tx_cities:
            district = lookup_special_district(lat, lon, state, zip_code, service='water')
            if district and not district.get('multiple_matches'):
                water = format_district_for_response(district)
                water['_source'] = 'special_district'
                return water
        
        # Priority 5: EPA SDWIS
        water = lookup_water_utility(city, county, state, full_address=address, lat=lat, lon=lon, zip_code=zip_code)
        return water
    except Exception as e:
        print(f"Water lookup error: {e}")
        return None


def lookup_internet_only(address: str) -> Optional[Dict]:
    """Look up internet providers. SLOW - typically 10-15 seconds (uses Playwright)."""
    try:
        return lookup_internet_providers(address)
    except Exception as e:
        print(f"Internet lookup error: {e}")
        return None


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    # Test addresses
    test_addresses = [
        "1100 Congress Ave, Austin, TX 78701",
        "200 S Tryon St, Charlotte, NC 28202",
        "350 5th Ave, New York, NY 10118",
    ]
    
    # Check for --verify flag
    verify_mode = "--verify" in sys.argv
    if verify_mode:
        sys.argv.remove("--verify")
        if BRIGHTDATA_PROXY_PASS:
            print("SERP verification enabled")
        else:
            print("Warning: BrightData proxy not configured, SERP verification disabled")
            verify_mode = False
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "--test":
            # Run all test addresses
            for address in test_addresses:
                result = lookup_utilities_by_address(address, verify_with_serp=verify_mode)
                if result:
                    electric = result.get("electric")
                    if electric:
                        if isinstance(electric, list):
                            for e in electric:
                                print(format_utility_result(e, "ELECTRIC"))
                        else:
                            print(format_utility_result(electric, "ELECTRIC"))
                    gas = result.get("gas")
                    if gas:
                        if isinstance(gas, list):
                            for g in gas:
                                print(format_utility_result(g, "NATURAL GAS"))
                        else:
                            print(format_utility_result(gas, "NATURAL GAS"))
                    water = result.get("water")
                    if water:
                        print(format_utility_result(water, "WATER"))
                    internet = result.get("internet")
                    if internet:
                        print(format_internet_result(internet))
                print()
                
        elif sys.argv[1] == "--coords" and len(sys.argv) >= 4:
            # Direct coordinate lookup: --coords <lon> <lat>
            lon = float(sys.argv[2])
            lat = float(sys.argv[3])
            print(f"Looking up utilities for coordinates: {lat}, {lon}")
            electric = lookup_electric_utility(lon, lat)
            if electric:
                print(format_utility_result(electric, "ELECTRIC"))
            gas = lookup_gas_utility(lon, lat)
            if gas:
                print(format_utility_result(gas, "NATURAL GAS"))
                
        elif sys.argv[1] == "--json" and len(sys.argv) >= 3:
            # JSON output: --json "address"
            address = " ".join(sys.argv[2:])
            result = lookup_utility_json(address)
            print(json.dumps(result, indent=2))
            
        else:
            # Single address lookup
            address = " ".join(sys.argv[1:])
            result = lookup_utilities_by_address(address, verify_with_serp=verify_mode)
            if result:
                electric = result.get("electric")
                if electric:
                    if isinstance(electric, list):
                        print(f"\n*** {len(electric)} overlapping electric service territories found ***")
                        for e in electric:
                            print(format_utility_result(e, "ELECTRIC"))
                    else:
                        print(format_utility_result(electric, "ELECTRIC"))
                gas = result.get("gas")
                if gas:
                    if isinstance(gas, list):
                        print(f"\n*** {len(gas)} overlapping gas service territories found ***")
                        for g in gas:
                            print(format_utility_result(g, "NATURAL GAS"))
                    else:
                        print(format_utility_result(gas, "NATURAL GAS"))
                water = result.get("water")
                if water:
                    print(format_utility_result(water, "WATER"))
                internet = result.get("internet")
                if internet:
                    print(format_internet_result(internet))
    else:
        print("Usage:")
        print('  python utility_lookup.py "123 Main St, City, ST 12345"')
        print('  python utility_lookup.py --verify "123 Main St, City, ST 12345"  # With SERP verification')
        print('  python utility_lookup.py --coords <longitude> <latitude>')
        print('  python utility_lookup.py --json "123 Main St, City, ST 12345"')
        print('  python utility_lookup.py --test')