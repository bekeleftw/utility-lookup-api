#!/usr/bin/env python3
"""
Utility Provider Lookup - Proof of Concept
Takes an address, geocodes it, and returns the electric utility provider.

ENDPOINTS USED:
- Geocoding: US Census Geocoder (free, no API key)
- Electric Utility: HIFLD ArcGIS FeatureServer (free, no API key)
- Natural Gas Utility: HIFLD ArcGIS FeatureServer (free, no API key)
- Water Utility: EPA SDWIS API (free, no API key)

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
from bs4 import BeautifulSoup

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

# OpenAI API key for LLM verification
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# =============================================================================
# FILTERING CONSTANTS - Used to exclude non-retail providers
# =============================================================================

# Providers to exclude (not retail providers - wholesale, transmission, irrigation, etc.)
EXCLUDED_PROVIDER_PATTERNS = [
    "WAPA", "WESTERN AREA POWER",
    "BPA", "BONNEVILLE POWER",
    "ERCOT",
    "IRRIGATION", "IRRIGAT",
    "WATER CONSERV",
    "USBIA", "BIA-", "BUREAU OF INDIAN",
    "RECLAMATION",
    "GENERATION ONLY",
    "TRANSMISSION ONLY",
    "WHOLESALE",
    "PROJECT",  # e.g., "USBIA-SAN CARLOS PROJECT"
    "AUTHORITY",  # Often wholesale (but not always - check context)
]

# Don't exclude these even if they match above patterns
EXCLUDED_EXCEPTIONS = [
    "TENNESSEE VALLEY",  # TVA does retail in some areas
    "SALT RIVER PROJECT",  # Arizona retail provider
    "LOWER COLORADO RIVER AUTHORITY",  # Texas retail
]

# Texas TDUs (transmission/distribution utilities) - correct for deregulated TX
TEXAS_TDUS = [
    "ONCOR",
    "CENTERPOINT",
    "AEP TEXAS",
    "TNMP",
    "TEXAS-NEW MEXICO POWER",
]

# States with retail electric choice (deregulated)
DEREGULATED_ELECTRIC_STATES = {
    "TX": "Texas has retail electric choice. This is your TDU (delivery company). Visit powertochoose.org to select a retail provider.",
    "PA": "Pennsylvania has retail electric choice. You may choose your electricity supplier.",
    "OH": "Ohio has retail electric choice. You may choose your electricity supplier.",
    "IL": "Illinois has retail electric choice in some areas. Check with your utility.",
    "MD": "Maryland has retail electric choice. You may choose your electricity supplier.",
    "NJ": "New Jersey has retail electric choice. You may choose your electricity supplier.",
    "NY": "New York has retail electric choice in some areas. Check with your utility.",
    "CT": "Connecticut has retail electric choice. You may choose your electricity supplier.",
    "MA": "Massachusetts has retail electric choice. You may choose your electricity supplier.",
    "ME": "Maine has retail electric choice. You may choose your electricity supplier.",
    "NH": "New Hampshire has retail electric choice. You may choose your electricity supplier.",
    "RI": "Rhode Island has retail electric choice. You may choose your electricity supplier.",
    "DC": "Washington DC has retail electric choice. You may choose your electricity supplier.",
}

# Major IOUs and utilities to boost in ranking
MAJOR_ELECTRIC_UTILITIES = [
    "DUKE ENERGY", "DOMINION", "SOUTHERN COMPANY", "ENTERGY",
    "XCEL ENERGY", "AMERICAN ELECTRIC", "FIRSTENERGY", "PPL",
    "PACIFIC GAS", "PG&E", "SOUTHERN CALIFORNIA EDISON", "SCE",
    "CON EDISON", "CONSOLIDATED EDISON",
    "GEORGIA POWER", "FLORIDA POWER", "FPL", "VIRGINIA ELECTRIC",
    "PROGRESS ENERGY", "CAROLINA POWER", "CONSUMERS ENERGY",
    "DTE ENERGY", "AMEREN", "EVERGY", "EVERSOURCE",
    "NATIONAL GRID", "PSEG", "EXELON", "COMMONWEALTH EDISON", "COMED",
    "PECO", "PEPCO", "BGE", "BALTIMORE GAS",
    "ONCOR", "CENTERPOINT", "AEP",
    "WISCONSIN ELECTRIC", "WE ENERGIES", "ALLIANT", "WPS",
    "XCEL", "NORTHERN STATES POWER",
    "AUSTIN ENERGY", "CPS ENERGY", "SAN ANTONIO",
    "SEATTLE CITY LIGHT", "TACOMA POWER", "SNOHOMISH",
    "SALT RIVER PROJECT", "SRP", "APS", "ARIZONA PUBLIC SERVICE",
    "ROCKY MOUNTAIN POWER", "PACIFICORP",
    "NEVADA POWER", "NV ENERGY",
    "PORTLAND GENERAL", "PUGET SOUND ENERGY",
]

MAJOR_GAS_UTILITIES = [
    "ATMOS", "CENTERPOINT", "SOUTHERN CALIFORNIA GAS", "SOCAL GAS",
    "NATIONAL FUEL", "NICOR", "PEOPLES GAS", "SPIRE", "SOUTHWEST GAS",
    "WASHINGTON GAS", "PIEDMONT NATURAL GAS", "DOMINION ENERGY",
    "TEXAS GAS SERVICE", "XCEL", "BLACK HILLS",
    "NORTHWEST NATURAL", "AVISTA", "CASCADE NATURAL GAS",
    "WPS", "WISCONSIN PUBLIC SERVICE", "WE ENERGIES",
    "CONSUMERS ENERGY", "DTE", "COLUMBIA GAS",
    "PSEG", "NATIONAL GRID", "CON EDISON",
]


# =============================================================================
# FILTERING FUNCTIONS
# =============================================================================

def filter_electric_providers(providers: Union[Dict, List[Dict]], city: str = None, state: str = None) -> Tuple[List[Dict], Optional[str]]:
    """
    Filter electric providers to remove non-retail entities and rank by likelihood.
    Returns (filtered_providers_list, deregulation_note).
    """
    if not providers:
        return [], None

    # Ensure we have a list
    if isinstance(providers, dict):
        providers = [providers]

    filtered = []
    for p in providers:
        name = (p.get("NAME") or "").upper()

        # Check if it's an exception first (don't exclude)
        is_exception = False
        for exc in EXCLUDED_EXCEPTIONS:
            if exc in name:
                is_exception = True
                break

        if not is_exception:
            # Check if it should be excluded
            skip = False
            for pattern in EXCLUDED_PROVIDER_PATTERNS:
                if pattern in name:
                    skip = True
                    break

            if skip:
                continue

        filtered.append(p)

    # If nothing left after filtering, return first original (better than nothing)
    if not filtered and providers:
        filtered = [providers[0]]

    # Score and rank remaining providers
    scored = []
    for p in filtered:
        name = (p.get("NAME") or "").upper()
        p_city = (p.get("CITY") or "").upper()
        score = 50  # Base score

        # Boost if provider city matches address city
        if city and city.upper() == p_city:
            score += 40

        # Boost if provider name contains city name (municipal utility)
        if city and city.upper() in name:
            score += 35

        # Boost for Texas TDUs in TX
        if state == "TX":
            for tdu in TEXAS_TDUS:
                if tdu in name:
                    score += 50
                    break

        # Boost major utilities
        for major in MAJOR_ELECTRIC_UTILITIES:
            if major in name:
                score += 25
                break

        # Slight penalty for co-ops when other options exist (they often serve surrounding areas)
        if "COOP" in name or "CO-OP" in name or "COOPERATIVE" in name:
            if len(filtered) > 1:
                score -= 10

        # Penalty for utilities from different cities (if it looks municipal)
        if city and p_city and city.upper() != p_city:
            if "CITY OF" in name or "MUNICIPAL" in name or "TOWN OF" in name:
                score -= 40  # Strong penalty for municipal from wrong city

        # Penalty for generic/ambiguous names
        if "ELECTRIC DIST" in name or "ELECTRICAL DIST" in name:
            score -= 15

        p["_score"] = score
        scored.append(p)

    # Sort by score descending
    scored.sort(key=lambda x: x.get("_score", 0), reverse=True)

    # Set confidence levels
    if scored:
        scored[0]["_confidence"] = "high"
        if len(scored) > 1:
            gap = scored[0].get("_score", 0) - scored[1].get("_score", 0)
            if gap < 15:
                scored[0]["_confidence"] = "medium"
        for other in scored[1:]:
            other["_confidence"] = "medium"

    # Check for deregulation note
    dereg_note = None
    if state in DEREGULATED_ELECTRIC_STATES:
        dereg_note = DEREGULATED_ELECTRIC_STATES[state]

    # Only return primary (or top 2 if scores are close)
    if len(scored) > 1 and (scored[0].get("_score", 0) - scored[1].get("_score", 0)) < 10:
    return scored[:2], dereg_note
return scored[:1], dereg_note


def filter_gas_providers(providers: Union[Dict, List[Dict]], city: str = None, state: str = None) -> List[Dict]:
    """
    Filter gas providers using similar logic to electric.
    Returns filtered and ranked list.
    """
    if not providers:
        return []

    if isinstance(providers, dict):
        providers = [providers]

    filtered = []
    for p in providers:
        name = (p.get("NAME") or "").upper()

        # Skip non-retail patterns for gas
        skip = False
        for pattern in ["IRRIGATION", "TRANSMISSION", "WHOLESALE", "STORAGE", "PIPELINE"]:
            if pattern in name:
                skip = True
                break

        if skip:
            continue

        filtered.append(p)

    if not filtered and providers:
        filtered = [providers[0]]

    # Score and rank
    scored = []
    for p in filtered:
        name = (p.get("NAME") or "").upper()
        p_city = (p.get("CITY") or "").upper()
        score = 50

        if city and city.upper() == p_city:
            score += 40

        if city and city.upper() in name:
            score += 30

        # Major gas utilities
        for major in MAJOR_GAS_UTILITIES:
            if major in name:
                score += 25
                break

        p["_score"] = score
        scored.append(p)

    scored.sort(key=lambda x: x.get("_score", 0), reverse=True)

    # Set confidence
    if scored:
        scored[0]["_confidence"] = "high"
        if len(scored) > 1:
            gap = scored[0].get("_score", 0) - scored[1].get("_score", 0)
            if gap < 15:
                scored[0]["_confidence"] = "medium"
        for other in scored[1:]:
            other["_confidence"] = "medium"

    return scored[:1] if scored else []


# =============================================================================
# GEOCODING
# =============================================================================

def geocode_address(address: str, include_geography: bool = False) -> Optional[Dict]:
    """
    Geocode an address using the US Census Geocoder (free, no API key required).
    Returns dict with coordinates and optionally geography info (county, city).
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
            print(f"No geocoding results for: {address}")
            return None

        match = matches[0]
        coords = match["coordinates"]
        lon = coords["x"]
        lat = coords["y"]
        matched_address = match["matchedAddress"]

        result = {
            "lon": lon,
            "lat": lat,
            "matched_address": matched_address,
            "city": None,
            "county": None,
            "state": None
        }

        # Extract geography info if available
        if include_geography and "geographies" in match:
            geo = match["geographies"]
            # Get county
            counties = geo.get("Counties", [])
            if counties:
                result["county"] = counties[0].get("BASENAME")
            # Get city/place
            places = geo.get("Incorporated Places", []) or geo.get("County Subdivisions", [])
            if places:
                result["city"] = places[0].get("BASENAME")
            # Get state
            states = geo.get("States", [])
            if states:
                result["state"] = states[0].get("STUSAB")

        print(f"Geocoded: {matched_address}")
        print(f"Coordinates: {lat}, {lon}")
        if result.get("city") or result.get("county"):
            print(f"Location: {result.get('city', 'N/A')}, {result.get('county', 'N/A')} County, {result.get('state', 'N/A')}")

        return result

    except requests.RequestException as e:
        print(f"Geocoding error: {e}")
        return None


# =============================================================================
# UTILITY LOOKUPS
# =============================================================================

def lookup_electric_utility(lon: float, lat: float) -> Optional[Union[Dict, List[Dict]]]:
    """
    Query HIFLD ArcGIS API to find electric utility for a given point.
    Returns utility info dict or list of dicts if multiple, or None if not found.
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


def lookup_gas_utility(lon: float, lat: float, state: str = None) -> Optional[Union[Dict, List[Dict]]]:
    """
    Query HIFLD ArcGIS API to find natural gas utility for a given point.
    Returns utility info dict or list of dicts, or None if not found.
    """
    base_url = "https://services5.arcgis.com/HDRa0B57OVrv2E1q/arcgis/rest/services/Natural_Gas_Local_Distribution_Company_Service_Territories/FeatureServer/0/query"

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
            if len(features) == 1:
                return features[0]["attributes"]
            else:
                return [f["attributes"] for f in features]

        print("No natural gas utility found in database for this location.")
        return None

    except requests.RequestException as e:
        print(f"Gas utility lookup error: {e}")
        return None


def lookup_water_utility(city: str, county: str, state: str, full_address: str = None) -> Optional[Dict]:
    """
    Look up water utility using local SDWA data (fast) or fallback to heuristic.
    """
    if not state:
        return None

    # Try local SDWA lookup first
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

    # Fallback to heuristic
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


# =============================================================================
# SERP VERIFICATION (Optional)
# =============================================================================

def verify_utility_with_serp(address: str, utility_type: str, candidate_name: str = None) -> Optional[Dict]:
    """
    Use BrightData proxy to search Google, then OpenAI to analyze results.
    Returns dict with verified provider info or None if unavailable.
    """
    if not BRIGHTDATA_PROXY_PASS:
        return None

    query = f"{address} {utility_type} utility provider"
    search_url = f"https://www.google.com/search?q={requests.utils.quote(query)}"

    proxy_url = f"http://{BRIGHTDATA_PROXY_USER}:{BRIGHTDATA_PROXY_PASS}@{BRIGHTDATA_PROXY_HOST}:{BRIGHTDATA_PROXY_PORT}"
    proxies = {"http": proxy_url, "https": proxy_url}

    try:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        response = requests.get(search_url, proxies=proxies, timeout=15, verify=False)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        for script in soup(["script", "style"]):
            script.decompose()
        search_text = soup.get_text(separator=' ')[:4000]

        if OPENAI_API_KEY:
            return analyze_serp_with_llm(search_text, address, utility_type, candidate_name)

        return analyze_serp_with_regex(search_text.upper(), candidate_name)

    except Exception:
        return None


def analyze_serp_with_llm(search_text: str, address: str, utility_type: str, candidate_name: str = None) -> Optional[Dict]:
    """Use OpenAI to analyze search results."""
    try:
        prompt = f"""Analyze these Google search results to identify the {utility_type} utility provider for the address: {address}

Search results:
{search_text}

Our database suggests: {candidate_name or 'Unknown'}

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

    except Exception:
        return None


def analyze_serp_with_regex(combined_text: str, candidate_name: str = None) -> Optional[Dict]:
    """Fallback regex-based analysis."""
    utility_patterns = [
        r'\b(DUKE ENERGY[A-Z\s]*)\b',
        r'\b(DOMINION ENERGY[A-Z\s]*)\b',
        r'\b([A-Z][A-Z]+\s+(?:ENERGY|ELECTRIC|GAS|WATER|UTILITIES))\b',
        r'\b(CITY OF [A-Z]+(?:\s+WATER)?)\b',
    ]

    found_utilities = []
    for pattern in utility_patterns:
        matches = re.findall(pattern, combined_text)
        found_utilities.extend(matches)

    found_utilities = list(set([
        u.strip() for u in found_utilities
        if len(u) > 8 and len(u) < 50 and not any(x in u for x in ['SEARCH', 'GOOGLE', 'CLICK'])
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
# FORMATTING
# =============================================================================

def format_utility_result(utility: dict, utility_type: str = "ELECTRIC") -> str:
    """Format utility dict into readable output."""
    utility_id = utility.get('ID') or utility.get('SVCTERID') or utility.get('id', 'N/A')
    confidence = utility.get('_confidence', 'medium')

    confidence_labels = {
        "high": "✓",
        "medium": "⚠ verify",
        "low": "? estimated"
    }
    confidence_label = confidence_labels.get(confidence, "")

    header = f"{utility_type} UTILITY PROVIDER [{confidence_label}]"

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

    lines.append("=" * 50)
    return "\n".join(lines)


# =============================================================================
# MAIN LOOKUP FUNCTION
# =============================================================================

def lookup_utilities_by_address(address: str, filter_by_city: bool = True, verify_with_serp: bool = False) -> Optional[Dict]:
    """
    Main function: takes an address string, returns electric, gas, and water utility info.
    Filters out non-retail providers and adds deregulation notes where applicable.
    """
    print(f"\nLooking up utilities for: {address}\n")

    # Step 1: Geocode with geography info
    geo_result = geocode_address(address, include_geography=True)
    if not geo_result:
        return None

    lon = geo_result["lon"]
    lat = geo_result["lat"]
    city = geo_result.get("city")
    state = geo_result.get("state")
    county = geo_result.get("county")

    # Step 2: Query raw utilities
    electric_raw = lookup_electric_utility(lon, lat)
    gas_raw = lookup_gas_utility(lon, lat, state=state)

    # Step 3: Filter and rank providers
    electric_filtered, electric_note = filter_electric_providers(electric_raw, city, state)
    gas_filtered = filter_gas_providers(gas_raw, city, state)

    # Step 4: Query water utility
    water = lookup_water_utility(city, county, state, full_address=address)

    # Step 5: Optional SERP verification
    if verify_with_serp and electric_filtered:
        primary = electric_filtered[0]
        electric_name = primary.get("NAME")
        if electric_name:
            print(f"Verifying electric provider with SERP search...")
            serp_result = verify_utility_with_serp(address, "electric", electric_name)
            if serp_result:
                if serp_result.get("verified"):
                    primary["_serp_verified"] = True
                    primary["_confidence"] = "high"
                    print(f"  ✓ SERP verified: {electric_name}")
                else:
                    primary["_serp_verified"] = False
                    print(f"  ⚠ SERP suggests: {serp_result.get('serp_provider', 'unknown')}")

    # Step 6: Build result
    # Return primary as single dict if only one, otherwise list with primary first
    electric_result = None
    if electric_filtered:
        if len(electric_filtered) == 1:
            electric_result = electric_filtered[0]
        else:
            electric_result = electric_filtered  # List with primary first

    gas_result = None
    if gas_filtered:
        if len(gas_filtered) == 1:
            gas_result = gas_filtered[0]
        else:
            gas_result = gas_filtered

    result = {
        "electric": electric_result,
        "electric_note": electric_note,
        "gas": gas_result,
        "gas_note": None,  # Gas is not deregulated in most states
        "water": water,
        "water_note": None,
        "location": {
            "city": city,
            "county": county,
            "state": state
        }
    }

    return result


def lookup_utility_json(address: str) -> Dict:
    """Returns structured JSON-friendly dict for integration."""
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

    lon, lat = coords
    result["coordinates"] = {"longitude": lon, "latitude": lat}

    electric = lookup_electric_utility(lon, lat)
    if electric:
        if isinstance(electric, list):
            electric = electric[0]
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
        if isinstance(gas, list):
            gas = gas[0]
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
# CLI
# =============================================================================

if __name__ == "__main__":
    test_addresses = [
        "1100 Congress Ave, Austin, TX 78701",
        "200 S Tryon St, Charlotte, NC 28202",
        "350 5th Ave, New York, NY 10118",
        "3027 W Coronado Rd, Phoenix, AZ 85009",
    ]

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
            for address in test_addresses:
                result = lookup_utilities_by_address(address, verify_with_serp=verify_mode)
                if result:
                    electric = result.get("electric")
                    if electric:
                        if isinstance(electric, list):
                            print(f"\n*** Primary + {len(electric)-1} other providers ***")
                            for i, e in enumerate(electric):
                                label = "PRIMARY" if i == 0 else f"OTHER {i}"
                                print(f"\n--- {label} ---")
                                print(format_utility_result(e, "ELECTRIC"))
                        else:
                            print(format_utility_result(electric, "ELECTRIC"))

                        if result.get("electric_note"):
                            print(f"\n📌 NOTE: {result['electric_note']}")

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
                print("\n" + "="*60 + "\n")

        elif sys.argv[1] == "--json" and len(sys.argv) >= 3:
            address = " ".join(sys.argv[2:])
            result = lookup_utility_json(address)
            print(json.dumps(result, indent=2))

        else:
            address = " ".join(sys.argv[1:])
            result = lookup_utilities_by_address(address, verify_with_serp=verify_mode)
            if result:
                electric = result.get("electric")
                if electric:
                    if isinstance(electric, list):
                        print(f"\n*** Primary + {len(electric)-1} other providers ***")
                        for i, e in enumerate(electric):
                            label = "PRIMARY" if i == 0 else f"OTHER {i}"
                            print(f"\n--- {label} ---")
                            print(format_utility_result(e, "ELECTRIC"))
                    else:
                        print(format_utility_result(electric, "ELECTRIC"))

                    if result.get("electric_note"):
                        print(f"\n📌 NOTE: {result['electric_note']}")

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
    else:
        print("Usage:")
        print('  python utility_lookup.py "123 Main St, City, ST 12345"')
        print('  python utility_lookup.py --verify "123 Main St, City, ST 12345"')
        print('  python utility_lookup.py --json "123 Main St, City, ST 12345"')
        print('  python utility_lookup.py --test')
