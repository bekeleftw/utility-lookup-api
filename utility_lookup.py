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
from state_utility_verification import verify_electric_provider

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


def lookup_water_utility(city: str, county: str, state: str, full_address: str = None) -> Optional[Dict]:
    """
    Look up water utility using local SDWA data (fast) or fallback to heuristic.
    """
    if not state:
        return None
    
    # Try local SDWA lookup first (built from build_water_lookup.py)
    if WATER_LOOKUP_FILE.exists():
        try:
            with open(WATER_LOOKUP_FILE, 'r') as f:
                lookup_data = json.load(f)
            
            # Try city lookup first
            if city:
                city_key = f"{state}|{city.upper()}"
                if city_key in lookup_data.get('by_city', {}):
                    result = lookup_data['by_city'][city_key].copy()
                    result['_confidence'] = 'high'
                    return result
            
            # Fall back to county lookup
            if county:
                county_key = f"{state}|{county.upper()}"
                if county_key in lookup_data.get('by_county', {}):
                    result = lookup_data['by_county'][county_key].copy()
                    result['_confidence'] = 'medium'
                    result['_note'] = 'Matched by county - verify for specific address'
                    return result
        except (json.JSONDecodeError, IOError):
            pass
    
    # Fallback to heuristic if no local data
    if city:
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
            "_note": "Estimated - no SDWA data available"
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
            "_note": "Estimated - no SDWA data available"
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
            
            # Type address slowly using keyboard to trigger autocomplete
            page.keyboard.type(address, delay=80)
            
            # Wait for autocomplete suggestions to appear
            page.wait_for_timeout(3000)
            
            # Check if autocomplete appeared by looking for address in page content
            content = page.content()
            address_street = address.split(',')[0].upper().strip()
            
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

def lookup_utilities_by_address(address: str, filter_by_city: bool = True, verify_with_serp: bool = False) -> Optional[Dict]:
    """
    Main function: takes an address string, returns electric, gas, water, and internet utility info.
    Uses city name to filter out municipal utilities from other cities.
    Optionally verifies gas/water with SERP search.
    """
    # Step 1: Geocode with geography info for filtering
    geo_result = geocode_address(address, include_geography=filter_by_city)
    if not geo_result:
        return None
    
    lon = geo_result["lon"]
    lat = geo_result["lat"]
    city = geo_result.get("city")
    state = geo_result.get("state")
    county = geo_result.get("county")
    
    # Step 2: Query utilities from HIFLD
    electric_candidates = lookup_electric_utility(lon, lat)
    gas = lookup_gas_utility(lon, lat, state=state)
    
    # Step 3: Filter by city to remove irrelevant municipal utilities
    if filter_by_city and city:
        electric_candidates = filter_utilities_by_location(electric_candidates, city)
        gas = filter_utilities_by_location(gas, city)
    
    # Step 4: Verify electric provider using state-specific data
    # Convert to list if single result
    if electric_candidates and not isinstance(electric_candidates, list):
        electric_candidates = [electric_candidates]
    
    # Get ZIP code from geocoded address for verification
    zip_code = geo_result.get("zip") or ""
    if not zip_code and geo_result.get("matched_address"):
        # Try to extract ZIP from matched address
        import re
        zip_match = re.search(r'\b(\d{5})\b', geo_result.get("matched_address", ""))
        if zip_match:
            zip_code = zip_match.group(1)
    
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
    
    # Step 5: Query water utility
    water = lookup_water_utility(city, county, state, full_address=address)
    
    # Step 6: Query internet providers (FCC Broadband Map)
    print(f"Looking up internet providers...")
    internet = lookup_internet_providers(address=address)
    if internet:
        print(f"  Found {internet.get('provider_count', 0)} internet providers")
        if internet.get('has_fiber'):
            print(f"  Fiber available: {internet.get('best_wired', {}).get('name')}")
    else:
        print("  Could not retrieve internet provider data")
    
    # Step 7: Optional SERP verification for electric, gas, and water
    if verify_with_serp:
        # Verify electric
        if primary_electric:
            electric_name = primary_electric.get("NAME") if isinstance(primary_electric, dict) else None
            if electric_name:
                print(f"Verifying electric provider with SERP search...")
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
        
        # Verify gas (or find it if HIFLD returned nothing)
        if gas:
            gas_name = gas.get("NAME") if isinstance(gas, dict) else None
            if gas_name:
                print(f"Verifying gas provider with SERP search...")
                serp_result = verify_utility_with_serp(address, "natural gas", gas_name)
                if serp_result:
                    if serp_result.get("verified"):
                        gas["_serp_verified"] = True
                        gas["_confidence"] = "high"
                        print(f"  ✓ SERP verified: {gas_name}")
                    else:
                        gas["_serp_verified"] = False
                        gas["_serp_suggestion"] = serp_result.get("serp_provider")
                        gas["_confidence"] = "low"
                        print(f"  ⚠ SERP suggests: {serp_result.get('serp_provider', 'unknown')}")
        else:
            # No gas in HIFLD - try to find via SERP
            print(f"Searching for gas provider via SERP...")
            serp_result = verify_utility_with_serp(address, "natural gas", None)
            if serp_result and serp_result.get("serp_provider"):
                gas = {
                    "NAME": serp_result.get("serp_provider"),
                    "_source": "serp",
                    "_confidence": serp_result.get("confidence", "medium"),
                    "_notes": serp_result.get("notes", "Found via Google search")
                }
                print(f"  Found via SERP: {serp_result.get('serp_provider')}")
        
        # Verify water
        if water:
            water_name = water.get("name") if isinstance(water, dict) else None
            if water_name:
                print(f"Verifying water provider with SERP search...")
                serp_result = verify_utility_with_serp(address, "water", water_name)
                if serp_result:
                    if serp_result.get("verified"):
                        water["_serp_verified"] = True
                        water["_confidence"] = "high"
                        print(f"  ✓ SERP verified: {water_name}")
                    else:
                        water["_serp_verified"] = False
                        water["_serp_suggestions"] = serp_result.get("serp_suggestions", [])
                        print(f"  ⚠ SERP suggests: {', '.join(serp_result.get('serp_suggestions', []))}")
    
    # Build electric result - primary first, then others
    electric_result = None
    if primary_electric:
        if other_electric:
            electric_result = [primary_electric] + other_electric
        else:
            electric_result = primary_electric
    
    result = {
        "electric": electric_result,
        "gas": gas,
        "water": water,
        "internet": internet,
        "location": {
            "city": city,
            "county": county,
            "state": state
        }
    }
    
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