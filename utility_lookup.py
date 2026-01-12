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
from special_districts import lookup_special_district, format_district_for_response, has_special_district_data
from confidence_scoring import calculate_confidence, source_to_score_key
from municipal_utilities import lookup_municipal_electric, lookup_municipal_gas, lookup_municipal_water
from brand_resolver import resolve_brand_name_with_fallback

# Import new Phase 12-14 modules
from deregulated_markets import is_deregulated_state, get_deregulated_market_info, adjust_electric_result_for_deregulation
from special_areas import get_special_area_info, check_tribal_land, check_incorporated_status, check_military_installation
from building_types import detect_building_type_from_address, adjust_result_for_building_type, get_utility_arrangement
from address_inference import infer_utility_from_nearby, add_verified_address
from ml_enhancements import ensemble_prediction, detect_anomalies, get_source_weight
from propane_service import is_likely_propane_area, get_no_gas_response
from well_septic import get_well_septic_likelihood, is_likely_rural

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
            "vintage": "Current_Current",
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
        
        result = {
            "lon": coords["x"],
            "lat": coords["y"],
            "matched_address": match["matchedAddress"],
            "city": None,
            "county": None,
            "state": None,
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
    
    # Always skip for authoritative sources
    for auth_source in AUTHORITATIVE_SOURCES:
        if auth_source in source:
            return True, f"Authoritative source: {source}"
    
    # Skip if confidence is already very high (90+)
    if confidence_score >= 90:
        return True, f"High confidence score: {confidence_score}"
    
    # Skip if marked as verified
    if confidence_level == 'verified':
        return True, "Already verified"
    
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


def lookup_internet_providers(address: str) -> Optional[Dict]:
    """
    Look up internet providers using Playwright to handle FCC's session requirements.
    Uses Chromium with stealth settings to bypass bot detection.
    Loads the FCC broadband map homepage, enters address, clicks autocomplete suggestion,
    and intercepts the fabric/detail API response.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright not installed, skipping internet lookup")
        return None
    
    # Normalize address to remove apartment/unit numbers (FCC only accepts building addresses)
    normalized_address = normalize_address_for_fcc(address)
    if normalized_address != address:
        print(f"  Normalized address for FCC: {normalized_address}")
    
    result_data = None
    
    def handle_response(response):
        nonlocal result_data
        # Capture the fabric/detail API (not hex tiles)
        if "fabric/detail" in response.url and "hex" not in response.url and response.status == 200:
            try:
                result_data = response.json()
            except:
                pass
    
    try:
        with sync_playwright() as p:
            # Check if we have a display available (for headed mode)
            import os
            import sys
            display = os.environ.get('DISPLAY')
            use_headed = display is not None and display != ''
            
            if use_headed:
                print(f"  Using headed mode with DISPLAY={display}", flush=True)
            else:
                print("  No DISPLAY available, falling back to headless (may not work)", flush=True)
            
            sys.stdout.flush()
            
            # Use Chromium with stealth settings to bypass bot detection
            browser = p.chromium.launch(
                headless=not use_headed,  # Use headed if DISPLAY available
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
            
            # Remove webdriver property to avoid detection
            page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            """)
            
            # Listen for API responses
            page.on("response", handle_response)
            
            # Go to FCC broadband map HOMEPAGE
            # Use domcontentloaded instead of networkidle to avoid timeout
            print("  Loading FCC homepage...", flush=True)
            page.goto("https://broadbandmap.fcc.gov/", timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(5000)  # Wait for JS to initialize
            print("  FCC page loaded", flush=True)
            
            # Find and click the address input
            search_input = page.locator('#addrSearch')
            if not search_input.is_visible():
                print("  FCC: Search input not visible", flush=True)
                browser.close()
                return None
            
            print("  Typing address...", flush=True)
            search_input.click()
            page.wait_for_timeout(500)
            
            # Type NORMALIZED address (without apt/unit) to trigger autocomplete
            page.keyboard.type(normalized_address, delay=80)
            
            # Wait for autocomplete suggestions to appear
            page.wait_for_timeout(3000)
            
            # Check if autocomplete appeared by looking for address in page content
            content = page.content()
            address_street = normalized_address.split(',')[0].upper().strip()
            
            if address_street in content.upper():
                print(f"  Autocomplete found for: {address_street}", flush=True)
                # Click the suggestion
                suggestion = page.locator(f'text={address_street}').first
                if suggestion.is_visible():
                    suggestion.click()
                    print("  Clicked suggestion, waiting for API...", flush=True)
                    page.wait_for_timeout(8000)  # Wait for API response
            else:
                print("  No autocomplete, using keyboard fallback", flush=True)
                # Fallback: try arrow down + enter
                page.keyboard.press("ArrowDown")
                page.wait_for_timeout(500)
                page.keyboard.press("Enter")
                page.wait_for_timeout(8000)
            
            print(f"  API captured: {result_data is not None}", flush=True)
            browser.close()
            
    except Exception as e:
        print(f"Playwright error: {e}")
        return None
    
    # Process the captured API response
    if not result_data:
        print("FCC API: No data captured")
        return None
    
    if result_data.get("status") != "successful" or not result_data.get("data"):
        print("FCC API: No provider data found")
        return None
    
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
    
    return {
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
            timeout=15,
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
# MAIN LOOKUP FUNCTION
# =============================================================================

def lookup_utilities_by_address(address: str, filter_by_city: bool = True, verify_with_serp: bool = False, selected_utilities: list = None) -> Optional[Dict]:
    """
    Main function: takes an address string, returns electric, gas, water, and internet utility info.
    Uses city name to filter out municipal utilities from other cities.
    Optionally verifies gas/water with SERP search.
    
    Args:
        selected_utilities: List of utility types to look up. Default is all: ['electric', 'gas', 'water', 'internet']
    """
    # Default to all utilities if not specified
    if selected_utilities is None:
        selected_utilities = ['electric', 'gas', 'water', 'internet']
    
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
        # Try to extract ZIP from matched address
        zip_match = re.search(r'\b(\d{5})\b', geo_result.get("matched_address", ""))
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
    
    # Step 2: Electric lookup - only if selected
    if 'electric' in selected_utilities:
        # PRIORITY 1: Check municipal utilities first (Austin Energy, CPS Energy, LADWP, etc.)
        municipal_electric = lookup_municipal_electric(state, city, zip_code)
        if municipal_electric:
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
        else:
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
        # PRIORITY 1: Check municipal gas utilities (CPS Energy, MLGW, etc.)
        municipal_gas = lookup_municipal_gas(state, city, zip_code)
        if municipal_gas:
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
        else:
            # PRIORITY 2: HIFLD and state-specific verification
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
    # Priority: Municipal utilities > Special districts > SERP > EPA SDWIS
    if 'water' in selected_utilities:
        water = None
        
        # PRIORITY 1: Check municipal water utilities (LADWP, MLGW, etc.)
        municipal_water = lookup_municipal_water(state, city, zip_code)
        if municipal_water:
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
        
        # PRIORITY 2: Check special districts (MUDs, CDDs)
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
    
    # Add confidence score to electric result
    if primary_electric:
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
    
    # Add confidence score to gas result
    if primary_gas:
        # Use _verification_source first, then _source, then default to hifld
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
    
    result = {
        "electric": electric_result,
        "gas": gas_result,
        "gas_no_service": gas_no_service,  # Set if no gas service available
        "water": water,
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
            "requires_special_handling": special_areas.get("requires_special_handling", False)
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
    
    return result


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