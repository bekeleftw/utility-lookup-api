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


def lookup_electric_utility(lon: float, lat: float, city: str = None) -> Optional[Dict]:
    """
    Query HIFLD ArcGIS API to find electric utility for a given point.
    Filters out non-retail providers and returns top 3 most likely retail providers.
    Returns utility info dict or None if not found.
    """
    base_url = "https://services5.arcgis.com/HDRa0B57OVrv2E1q/arcgis/rest/services/Electric_Retail_Service_Territories/FeatureServer/0/query"
    
    params = {
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "NAME,ID,STATE,TELEPHONE,ADDRESS,CITY,ZIP,WEBSITE,TYPE",
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
        
        # Extract attributes
        providers = [f["attributes"] for f in features]
        
        # Filter out non-retail providers (wholesale, federal power agencies, irrigation districts)
        non_retail_keywords = ["WAPA", "IRRIGATION", "WATER CONSERV", "USBIA", "BPA", "BONNEVILLE",
                               "WHOLESALE", "TRANSMISSION", "GENERATION", "POWER ADMIN"]
        retail_providers = []
        for p in providers:
            name = (p.get("NAME") or "").upper()
            is_retail = True
            for keyword in non_retail_keywords:
                if keyword in name:
                    is_retail = False
                    break
            if is_retail:
                retail_providers.append(p)
        
        if not retail_providers:
            # If all were filtered out, return original list
            retail_providers = providers
        
        # Score and rank providers
        scored = []
        for p in retail_providers:
            score = 50  # Base score
            name = (p.get("NAME") or "").upper()
            provider_type = (p.get("TYPE") or "").upper()
            provider_city = (p.get("CITY") or "").upper()
            
            # Prioritize by TYPE: IOU > Cooperative > Municipal > Political Subdivision
            type_scores = {
                "INVESTOR OWNED": 30,
                "IOU": 30,
                "COOPERATIVE": 20,
                "COOP": 20,
                "MUNICIPAL": 10,
                "POLITICAL SUBDIVISION": 5,
                "STATE": 5,
                "FEDERAL": 0
            }
            for type_key, type_score in type_scores.items():
                if type_key in provider_type:
                    score += type_score
                    break
            
            # Boost if provider CITY matches geocoded city
            if city and provider_city:
                if city.upper() == provider_city or city.upper() in provider_city:
                    score += 25
            
            # Boost city-named utilities (municipal or not) - this is a strong signal
            if city and city.upper() in name:
                score += 35  # Strong boost for city name in utility name
            
            # Large IOUs get a boost
            large_ious = ["DUKE ENERGY", "DOMINION", "SOUTHERN COMPANY", "ENTERGY", 
                          "XCEL ENERGY", "AMERICAN ELECTRIC", "FIRSTENERGY", "PPL",
                          "PACIFIC GAS", "SOUTHERN CALIFORNIA EDISON", "CON EDISON",
                          "GEORGIA POWER", "FLORIDA POWER", "VIRGINIA ELECTRIC",
                          "PROGRESS ENERGY", "CONSUMERS ENERGY", "DTE ENERGY", 
                          "AMEREN", "EVERGY", "ONCOR", "CENTERPOINT", "EVERSOURCE", 
                          "NATIONAL GRID", "PSEG", "EXELON", "COMMONWEALTH EDISON"]
            for iou in large_ious:
                if iou in name:
                    score += 15
                    break
            
            # Rural EMCs/cooperatives
            if "EMC" in name or "RURAL" in name or "COOPERATIVE" in name or "CO-OP" in name:
                score += 10
            
            # Deprioritize municipal utilities from other cities
            if ("MUNICIPAL" in name or "CITY OF" in name or "TOWN OF" in name):
                if city and city.upper() not in name:
                    score -= 15
            
            p["_score"] = score
            scored.append(p)
        
        # Sort by score descending and return top 3
        scored.sort(key=lambda x: x.get("_score", 0), reverse=True)
        top_providers = scored[:3]
        
        # Set confidence on primary
        if top_providers:
            top_providers[0]["_confidence"] = "high" if len(top_providers) == 1 or (top_providers[0].get("_score", 0) - top_providers[1].get("_score", 0) >= 15) else "medium"
        
        if len(top_providers) == 1:
            return top_providers[0]
        else:
            return top_providers
        
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
        # (State-level fallback was too inaccurate - many areas have regional providers not in dataset)
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
        "resultRecordCount": 1,  # Get the largest provider by customer count
        "f": "json"
    }
    
    try:
        response = requests.get(base_url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        features = data.get("features", [])
        if not features:
            return None
        
        # Return the provider with most customers
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
        "source_type": ws.get("primary_source_code"),  # GW=groundwater, SW=surface water
        "owner_type": ws.get("owner_type_code"),  # F=Federal, S=State, L=Local, M=Public/Private, P=Private
        "service_connections": ws.get("service_connections_count"),
    }


def rank_electric_providers(providers: List[Dict], city: str = None, county: str = None) -> Tuple[Dict, List[Dict]]:
    """
    Rank electric providers to identify the most likely one.
    Returns (primary_provider, other_providers).
    
    Ranking logic:
    1. City-named municipal utilities get highest priority if city matches
    2. Large IOUs (investor-owned utilities) like Duke, Dominion get high priority
    3. Rural EMCs get medium priority
    4. Wholesale/transmission utilities get lowest priority
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
            verify=False  # BrightData proxy uses its own SSL
        )
        response.raise_for_status()
        
        # Parse HTML response - extract all text
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
        
        # Get text content (limit to first 4000 chars for LLM)
        search_text = soup.get_text(separator=' ')[:4000]
        
        # Use OpenAI to analyze the search results
        if OPENAI_API_KEY:
            return analyze_serp_with_llm(search_text, address, utility_type, candidate_name)
        
        # Fallback to regex if no OpenAI key
        return analyze_serp_with_regex(search_text.upper(), candidate_name)
        
    except Exception as e:
        # Silently fail - SERP is optional verification
        return None


def analyze_serp_with_llm(search_text: str, address: str, utility_type: str, candidate_name: str = None) -> Optional[Dict]:
    """Use OpenAI to analyze search results and identify the correct utility provider."""
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
        
        # Parse JSON response
        # Handle markdown code blocks if present
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


def filter_utilities_by_location(utilities: Union[Dict, List[Dict]], city: str = None) -> Union[Dict, List[Dict]]:
    """
    Filter utilities to remove municipal utilities from other cities.
    Municipal utilities typically have "CITY OF", "VILLAGE OF", or city name + "UTILITIES" in their name.
    """
    if not utilities or not city:
        return utilities
    
    # Normalize city name for comparison
    city_upper = city.upper()
    
    def is_relevant_utility(util: Dict) -> bool:
        name = util.get("NAME", "").upper()
        
        # Check if it's a municipal utility (CITY OF, VILLAGE OF, TOWN OF)
        municipal_prefixes = ["CITY OF ", "VILLAGE OF ", "TOWN OF "]
        for prefix in municipal_prefixes:
            if name.startswith(prefix):
                # Extract city from utility name (e.g., "CITY OF OCONOMOWOC" -> "OCONOMOWOC")
                util_city = name[len(prefix):].strip().split(" - ")[0].split(",")[0].strip()
                return util_city == city_upper
        
        # Check for pattern like "OCONOMOWOC UTILITIES" or "BROOKFIELD ELECTRIC"
        municipal_suffixes = [" UTILITIES", " UTILITY", " ELECTRIC", " LIGHT", " POWER", " WATER & LIGHT", " ELECTRIC & WATER"]
        for suffix in municipal_suffixes:
            if name.endswith(suffix):
                util_city = name[:-len(suffix)].strip()
                # If the utility name is just a city name + suffix, check if it matches
                if util_city and " " not in util_city:  # Single word = likely city name
                    return util_city == city_upper
        
        # Filter out wholesale power suppliers (they don't serve retail customers directly)
        wholesale_indicators = ["WPPI ", "WHOLESALE", "GENERATION", "TRANSMISSION"]
        if any(indicator in name for indicator in wholesale_indicators):
            return False
        
        # Non-municipal utilities (investor-owned, cooperatives, regional) are relevant
        # These typically have company names like "WISCONSIN ELECTRIC POWER CO", "DUKE ENERGY", etc.
        return True
    
    if isinstance(utilities, list):
        filtered = [u for u in utilities if is_relevant_utility(u)]
        if len(filtered) == 1:
            return filtered[0]
        return filtered if filtered else None
    else:
        return utilities if is_relevant_utility(utilities) else None


def format_utility_result(utility: dict, utility_type: str = "ELECTRIC") -> str:
    """Format utility dict into readable output."""
    # Handle different ID field names between electric and gas datasets
    utility_id = utility.get('ID') or utility.get('SVCTERID') or utility.get('id', 'N/A')
    is_fallback = utility.get('_fallback', False)
    confidence = utility.get('_confidence')
    
    # Set default confidence based on utility type and data source
    if confidence is None:
        if utility_type == "ELECTRIC":
            confidence = "high"  # Electric data is reliable
        elif utility_type == "NATURAL GAS":
            confidence = "medium"  # Gas data has known quality issues
        else:
            confidence = "low"  # Water is estimated
    
    # Build header with confidence indicator
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
    
    # Handle both uppercase (electric/gas) and lowercase (water) field names
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
    
    # Add website for electric/gas, not for water
    if utility_type != "WATER":
        lines.append(f"Website:   {website}")
    
    lines.extend([
        f"Address:   {address}",
        f"City:      {city}",
        f"ZIP:       {zip_code}",
        f"Utility ID: {utility_id}",
    ])
    
    # Add type field for gas utilities
    if utility_type == "NATURAL GAS":
        lines.append(f"Type:      {utility.get('TYPE', 'N/A')}")
    
    # Add water-specific fields
    if utility_type == "WATER":
        pop = utility.get('population_served')
        if pop:
            lines.append(f"Pop Served: {pop:,}")
        source = utility.get('source_type')
        if source:
            source_desc = {"GW": "Groundwater", "GWP": "Groundwater", "SW": "Surface Water", "SWP": "Surface Water"}.get(source, source)
            lines.append(f"Source:    {source_desc}")
        # Show alternatives count if multiple matches
        total = utility.get('_total_matches')
        if total and total > 1:
            lines.append(f"Note:      {total} water systems serve this county")
    
    lines.append("=" * 50)
    return "\n".join(lines)


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
    
    lon, lat = coords
    result["coordinates"] = {"longitude": lon, "latitude": lat}
    
    # Lookup electric utility
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
    
    # Lookup gas utility
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


def lookup_utilities_by_address(address: str, filter_by_city: bool = True, verify_with_serp: bool = False) -> Optional[Dict]:
    """
    Main function: takes an address string, returns both electric and gas utility info.
    Uses city name to filter out municipal utilities from other cities.
    Optionally verifies gas/water with SERP search.
    """
    print(f"\nLooking up utilities for: {address}\n")
    
    # Step 1: Geocode with geography info for filtering
    geo_result = geocode_address(address, include_geography=filter_by_city)
    if not geo_result:
        return None
    
    lon = geo_result["lon"]
    lat = geo_result["lat"]
    city = geo_result.get("city")
    
    # Step 2: Query utilities (pass city for electric ranking, state for gas fallback)
    state = geo_result.get("state")
    county = geo_result.get("county")
    electric = lookup_electric_utility(lon, lat, city=city)  # Now filters and ranks internally
    gas = lookup_gas_utility(lon, lat, state=state)
    
    # Step 3: Filter gas by city to remove irrelevant municipal utilities
    # (Electric filtering/ranking is now done in lookup_electric_utility)
    if filter_by_city and city:
        gas = filter_utilities_by_location(gas, city)
    
    # Step 4: Extract primary electric provider (already ranked by lookup_electric_utility)
    primary_electric = None
    other_electric = []
    if electric:
        if isinstance(electric, list) and len(electric) > 1:
            # Already ranked - first is primary, rest are alternatives
            primary_electric = electric[0]
            other_electric = electric[1:]
            if not primary_electric.get("_confidence"):
                primary_electric["_confidence"] = "high"
        elif isinstance(electric, list) and len(electric) == 1:
            primary_electric = electric[0]
            if not primary_electric.get("_confidence"):
                primary_electric["_confidence"] = "high"
        else:
            primary_electric = electric
            if not primary_electric.get("_confidence"):
                primary_electric["_confidence"] = "high"
    
    # Step 5: Query water utility
    water = lookup_water_utility(city, county, state, full_address=address)
    
    # Step 6: Optional SERP verification for electric, gas, and water
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
                        # Check if SERP suggests one of our other candidates
                        serp_provider = serp_result.get("serp_provider")
                        if serp_provider and other_electric:
                            for alt in other_electric:
                                alt_name = alt.get("NAME", "")
                                if serp_provider.upper() in alt_name.upper() or alt_name.upper() in serp_provider.upper():
                                    # Swap - SERP found a different provider from our list
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
                        gas["_serp_suggestions"] = serp_result.get("serp_suggestions", [])
                        print(f"  ⚠ SERP suggests: {', '.join(serp_result.get('serp_suggestions', []))}")
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
            # Return primary as first item, others follow
            electric_result = [primary_electric] + other_electric
        else:
            electric_result = primary_electric
    
    result = {
        "electric": electric_result,
        "gas": gas,
        "water": water,
        "location": {
            "city": city,
            "county": county,
            "state": state
        }
    }
    
    return result


if __name__ == "__main__":
    # Test addresses
    test_addresses = [
        "1100 Congress Ave, Austin, TX 78701",           # Austin Energy territory
        "200 S Tryon St, Charlotte, NC 28202",           # Duke Energy territory  
        "350 5th Ave, New York, NY 10118",               # Con Edison territory
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
    else:
        print("Usage:")
        print('  python utility_lookup.py "123 Main St, City, ST 12345"')
        print('  python utility_lookup.py --verify "123 Main St, City, ST 12345"  # With SERP verification')
        print('  python utility_lookup.py --coords <longitude> <latitude>')
        print('  python utility_lookup.py --json "123 Main St, City, ST 12345"')
        print('  python utility_lookup.py --test')
