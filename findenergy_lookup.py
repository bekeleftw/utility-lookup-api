#!/usr/bin/env python3
"""
FindEnergy.com integration for electric and gas utility verification.

FindEnergy has coverage area maps for 3,530+ electric companies and natural gas
providers in the US. They've corrected many errors in government data (EIA, HIFLD).

Since FindEnergy uses Cloudflare protection, we use multiple approaches:
1. Cached data from previous lookups/bulk collection
2. SERP queries with site:findenergy.com filter
3. Direct scraping (when possible, with proper headers)

URL patterns:
- https://findenergy.com/tx/ (state electric)
- https://findenergy.com/tx/natural-gas/ (state gas)
- https://findenergy.com/tx/austin/ (city electric)
- https://findenergy.com/providers/oncor/ (provider service area)
"""

import json
import os
import re
import time
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

# Data directories
DATA_DIR = Path(__file__).parent / "data" / "findenergy"
ELECTRIC_CACHE_FILE = DATA_DIR / "electric_by_zip.json"
GAS_CACHE_FILE = DATA_DIR / "gas_by_zip.json"
CITY_CACHE_FILE = DATA_DIR / "city_providers.json"
LOOKUP_CACHE_FILE = DATA_DIR / "lookup_cache.json"

# Rate limiting
LAST_REQUEST_TIME = 0
MIN_REQUEST_INTERVAL = 2.0  # seconds between requests

# Headers to mimic browser
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}

# State abbreviations to full names (for URL construction)
STATE_NAMES = {
    "AL": "alabama", "AK": "alaska", "AZ": "arizona", "AR": "arkansas",
    "CA": "california", "CO": "colorado", "CT": "connecticut", "DE": "delaware",
    "FL": "florida", "GA": "georgia", "HI": "hawaii", "ID": "idaho",
    "IL": "illinois", "IN": "indiana", "IA": "iowa", "KS": "kansas",
    "KY": "kentucky", "LA": "louisiana", "ME": "maine", "MD": "maryland",
    "MA": "massachusetts", "MI": "michigan", "MN": "minnesota", "MS": "mississippi",
    "MO": "missouri", "MT": "montana", "NE": "nebraska", "NV": "nevada",
    "NH": "new-hampshire", "NJ": "new-jersey", "NM": "new-mexico", "NY": "new-york",
    "NC": "north-carolina", "ND": "north-dakota", "OH": "ohio", "OK": "oklahoma",
    "OR": "oregon", "PA": "pennsylvania", "RI": "rhode-island", "SC": "south-carolina",
    "SD": "south-dakota", "TN": "tennessee", "TX": "texas", "UT": "utah",
    "VT": "vermont", "VA": "virginia", "WA": "washington", "WV": "west-virginia",
    "WI": "wisconsin", "WY": "wyoming", "DC": "washington-dc"
}


def _load_cache(cache_file: Path) -> Dict:
    """Load a cache file."""
    if cache_file.exists():
        try:
            with open(cache_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def _save_cache(cache_file: Path, data: Dict):
    """Save data to cache file."""
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(cache_file, 'w') as f:
            json.dump(data, f, indent=2)
    except IOError as e:
        print(f"Warning: Could not save cache: {e}")


def _rate_limit():
    """Enforce rate limiting between requests."""
    global LAST_REQUEST_TIME
    elapsed = time.time() - LAST_REQUEST_TIME
    if elapsed < MIN_REQUEST_INTERVAL:
        time.sleep(MIN_REQUEST_INTERVAL - elapsed)
    LAST_REQUEST_TIME = time.time()


def _make_request(url: str, timeout: int = 10) -> Optional[requests.Response]:
    """Make a rate-limited request with browser headers."""
    _rate_limit()
    try:
        response = requests.get(url, headers=BROWSER_HEADERS, timeout=timeout)
        if response.status_code == 200:
            return response
        elif response.status_code == 403:
            # Cloudflare block
            return None
    except requests.RequestException:
        pass
    return None


def _normalize_city_name(city: str) -> str:
    """Normalize city name for URL construction."""
    return city.lower().replace(" ", "-").replace(".", "").replace("'", "")


def _get_cache_key(city: str, state: str, utility_type: str) -> str:
    """Generate a cache key for lookups."""
    return f"{state.upper()}:{city.lower()}:{utility_type}"


def lookup_from_cache(
    zip_code: str = None,
    city: str = None,
    state: str = None,
    utility_type: str = "electric"
) -> Optional[Dict]:
    """
    Look up utility provider from cached FindEnergy data.
    
    Args:
        zip_code: ZIP code to look up
        city: City name
        state: State abbreviation
        utility_type: 'electric' or 'gas'
        
    Returns:
        Dict with provider info or None if not cached
    """
    if utility_type == "electric":
        cache = _load_cache(ELECTRIC_CACHE_FILE)
    else:
        cache = _load_cache(GAS_CACHE_FILE)
    
    # Try ZIP lookup first
    if zip_code and zip_code in cache:
        return cache[zip_code]
    
    # Try city lookup
    if city and state:
        city_cache = _load_cache(CITY_CACHE_FILE)
        key = _get_cache_key(city, state, utility_type)
        if key in city_cache:
            return city_cache[key]
    
    return None


def query_findenergy_serp(
    query: str,
    utility_type: str = "electric"
) -> Optional[Dict]:
    """
    Query FindEnergy via Google SERP with site: filter.
    
    This is the fallback when direct scraping is blocked.
    Uses BrightData proxy for Google search (same as main SERP verification).
    
    Args:
        query: Search query (address, city, or ZIP)
        utility_type: 'electric' or 'gas'
        
    Returns:
        Dict with provider info extracted from SERP results
    """
    # BrightData credentials (same as utility_lookup.py)
    proxy_host = "brd.superproxy.io"
    proxy_port = "33335"
    proxy_user = "brd-customer-hl_6cc76bc7-zone-address_search"
    proxy_pass = "n59dskgnctqr"
    
    if not proxy_pass:
        # No proxy available - can't do SERP lookup
        return None
    
    # Construct site-specific query
    if utility_type == "gas":
        serp_query = f'site:findenergy.com "{query}" natural gas provider'
    else:
        serp_query = f'site:findenergy.com "{query}" electric provider'
    
    search_url = f"https://www.google.com/search?q={quote(serp_query)}"
    
    proxy_url = f"http://{proxy_user}:{proxy_pass}@{proxy_host}:{proxy_port}"
    proxies = {
        "http": proxy_url,
        "https": proxy_url
    }
    
    try:
        _rate_limit()
        
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        response = requests.get(
            search_url,
            proxies=proxies,
            headers=BROWSER_HEADERS,
            timeout=15,
            verify=False
        )
        
        if response.status_code != 200:
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Remove scripts and styles
        for script in soup(["script", "style"]):
            script.decompose()
        
        search_text = soup.get_text(separator=' ')
        
        providers = []
        
        # Look for provider patterns in search results
        # These patterns match FindEnergy's SERP result format
        provider_patterns = [
            # Match "Provider Name: Rates, Coverage" format from SERP titles (most reliable)
            r"([A-Z][A-Za-z\s&\-\']{3,40}(?:Electric|Energy|Power|Gas|Light|Utility|Utilities|Cooperative|Association)):\s*Rates",
            # Match table entries like "; Provider Name, BUNDLED"
            r";\s*([A-Z][A-Za-z\s&\-\']{3,40}(?:Electric|Energy|Power|Gas|Cooperative|Association)),\s*BUNDLED",
            # Match "Provider Name produces/supplies/provides/serves" 
            r"\b([A-Z][A-Za-z]{2,20}(?:\s+[A-Z][A-Za-z]{2,20}){0,3}\s+(?:Electric|Energy|Power|Gas|Light|Cooperative|Association))\s+(?:produces|supplies|provides|serves)\b",
            # Match known utility name patterns (2-4 words ending in Electric/Energy/Gas/Power)
            r"\b([A-Z][a-z]{2,15}(?:\s+[A-Z][a-z]{2,15}){0,2}\s+(?:Electric|Energy|Power|Gas))\b",
        ]
        
        for pattern in provider_patterns:
            matches = re.findall(pattern, search_text)
            for match in matches:
                provider_name = match.strip()
                # Clean up the name
                provider_name = re.sub(r'\s+', ' ', provider_name)
                # Filter out common false positives
                if provider_name and len(provider_name) > 8 and len(provider_name) < 50:
                    skip_words = ['findenergy', 'google', 'search', 'click', 'more', 'read more', 
                                  'find energy', 'results', 'electricity', 'different energy',
                                  'electric rates', 'average electric', 'cities ', 'natural ',
                                  'many ', 'while ', 'how ', 'what ', 'does ', 'the ', 'your ']
                    # Also skip if it's just a state abbreviation + "electric/gas"
                    state_abbrev_pattern = r'^[A-Z]{2}\s+(?:electric|gas)$'
                    name_lower = provider_name.lower()
                    if not any(skip in name_lower for skip in skip_words):
                        if not re.match(state_abbrev_pattern, provider_name, re.IGNORECASE):
                            # Clean up prefixes
                            if name_lower.startswith('cities '):
                                provider_name = provider_name[7:]
                            providers.append({
                                "name": provider_name,
                                "source": "findenergy_serp"
                            })
        
        if providers:
            # Deduplicate and return
            seen = set()
            unique_providers = []
            for p in providers:
                name_lower = p["name"].lower()
                if name_lower not in seen:
                    seen.add(name_lower)
                    unique_providers.append(p)
            
            return {
                "providers": unique_providers[:5],  # Limit to top 5
                "utility_type": utility_type,
                "source": "findenergy_serp",
                "query": query
            }
    
    except Exception as e:
        print(f"FindEnergy SERP query failed: {e}")
    
    return None


def scrape_findenergy_city(
    city: str,
    state: str,
    utility_type: str = "electric"
) -> Optional[Dict]:
    """
    Attempt to scrape FindEnergy city page directly.
    
    Note: This may be blocked by Cloudflare. Falls back to SERP if blocked.
    
    Args:
        city: City name
        state: State abbreviation (e.g., "TX")
        utility_type: 'electric' or 'gas'
        
    Returns:
        Dict with provider info or None if blocked/failed
    """
    state_lower = state.lower()
    city_slug = _normalize_city_name(city)
    
    if utility_type == "gas":
        url = f"https://findenergy.com/{state_lower}/{city_slug}/natural-gas/"
    else:
        url = f"https://findenergy.com/{state_lower}/{city_slug}/"
    
    response = _make_request(url)
    if not response:
        # Blocked or failed - try SERP fallback
        return query_findenergy_serp(f"{city}, {state}", utility_type)
    
    try:
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Look for provider information in the page
        providers = []
        
        # FindEnergy typically lists providers in tables or cards
        # Look for common patterns
        
        # Pattern 1: Provider cards/links
        provider_links = soup.find_all('a', href=re.compile(r'/providers/'))
        for link in provider_links:
            name = link.get_text(strip=True)
            if name and len(name) > 2:
                providers.append({
                    "name": name,
                    "source_url": urljoin(url, link.get('href', '')),
                    "source": "findenergy_scrape"
                })
        
        # Pattern 2: Table rows with provider names
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                for cell in cells:
                    text = cell.get_text(strip=True)
                    # Check if it looks like a utility name
                    if any(kw in text.lower() for kw in ['energy', 'electric', 'power', 'gas', 'utility']):
                        providers.append({
                            "name": text,
                            "source": "findenergy_scrape"
                        })
        
        # Pattern 3: Look for specific div classes (may vary)
        provider_divs = soup.find_all('div', class_=re.compile(r'provider|company|utility', re.I))
        for div in provider_divs:
            name = div.get_text(strip=True)
            if name and len(name) > 2 and len(name) < 100:
                providers.append({
                    "name": name,
                    "source": "findenergy_scrape"
                })
        
        if providers:
            # Deduplicate
            seen = set()
            unique_providers = []
            for p in providers:
                name_lower = p["name"].lower()
                if name_lower not in seen and len(name_lower) > 3:
                    seen.add(name_lower)
                    unique_providers.append(p)
            
            result = {
                "providers": unique_providers[:10],  # Limit to top 10
                "utility_type": utility_type,
                "city": city,
                "state": state,
                "source": "findenergy_scrape",
                "source_url": url
            }
            
            # Cache the result
            city_cache = _load_cache(CITY_CACHE_FILE)
            key = _get_cache_key(city, state, utility_type)
            city_cache[key] = result
            _save_cache(CITY_CACHE_FILE, city_cache)
            
            return result
    
    except Exception as e:
        print(f"Error parsing FindEnergy page: {e}")
    
    # Fall back to SERP
    return query_findenergy_serp(f"{city}, {state}", utility_type)


def lookup_findenergy(
    address: str = None,
    city: str = None,
    state: str = None,
    zip_code: str = None,
    utility_type: str = "electric"
) -> Optional[Dict]:
    """
    Look up utility provider from FindEnergy.com.
    
    Tries multiple approaches in order:
    1. Cached data (fastest)
    2. Direct scraping (if not blocked)
    3. SERP fallback (most reliable)
    
    Args:
        address: Full address (optional)
        city: City name
        state: State abbreviation
        zip_code: ZIP code
        utility_type: 'electric' or 'gas'
        
    Returns:
        Dict with provider info:
        {
            "providers": [{"name": "...", "source": "..."}],
            "utility_type": "electric" or "gas",
            "source": "findenergy_cache" | "findenergy_scrape" | "findenergy_serp",
            "confidence": "high" | "medium" | "low"
        }
    """
    # Try cache first
    cached = lookup_from_cache(zip_code, city, state, utility_type)
    if cached:
        cached["source"] = "findenergy_cache"
        cached["confidence"] = "high"
        return cached
    
    # Try direct scraping if we have city/state
    if city and state:
        result = scrape_findenergy_city(city, state, utility_type)
        if result:
            result["confidence"] = "medium" if result.get("source") == "findenergy_scrape" else "low"
            return result
    
    # Try SERP with address or ZIP
    query = address or f"{city}, {state}" if city and state else zip_code
    if query:
        result = query_findenergy_serp(query, utility_type)
        if result:
            result["confidence"] = "low"
            return result
    
    return None


def verify_against_findenergy(
    provider_name: str,
    city: str,
    state: str,
    zip_code: str = None,
    utility_type: str = "electric"
) -> Dict:
    """
    Verify a provider name against FindEnergy data.
    
    Args:
        provider_name: The provider name to verify
        city: City name
        state: State abbreviation
        zip_code: ZIP code (optional)
        utility_type: 'electric' or 'gas'
        
    Returns:
        Dict with verification result:
        {
            "verified": True/False,
            "findenergy_providers": [...],
            "match_type": "exact" | "partial" | "none",
            "confidence": "high" | "medium" | "low",
            "recommendation": "use_current" | "use_findenergy" | "flag_for_review"
        }
    """
    result = {
        "verified": False,
        "findenergy_providers": [],
        "match_type": "none",
        "confidence": "low",
        "recommendation": "use_current"
    }
    
    # Get FindEnergy data
    fe_result = lookup_findenergy(
        city=city,
        state=state,
        zip_code=zip_code,
        utility_type=utility_type
    )
    
    if not fe_result or not fe_result.get("providers"):
        result["recommendation"] = "use_current"
        return result
    
    result["findenergy_providers"] = fe_result["providers"]
    result["confidence"] = fe_result.get("confidence", "low")
    
    # Normalize provider name for comparison
    provider_lower = provider_name.lower().strip()
    provider_words = set(provider_lower.split())
    
    for fe_provider in fe_result["providers"]:
        fe_name = fe_provider.get("name", "").lower().strip()
        fe_legal = fe_provider.get("legal_name", "").lower().strip()
        fe_words = set(fe_name.split())
        
        # Also check against legal name if present
        if fe_legal and provider_lower == fe_legal:
            result["verified"] = True
            result["match_type"] = "exact"
            result["recommendation"] = "use_current"
            return result
        
        # Exact match
        if provider_lower == fe_name:
            result["verified"] = True
            result["match_type"] = "exact"
            result["recommendation"] = "use_current"
            return result
        
        # Partial match (significant word overlap)
        common_words = provider_words & fe_words
        # Remove common utility words for comparison
        utility_words = {'energy', 'electric', 'power', 'gas', 'utility', 'co', 'company', 'corp', 'inc', 'llc', 'the', 'of'}
        significant_common = common_words - utility_words
        significant_provider = provider_words - utility_words
        significant_fe = fe_words - utility_words
        
        if significant_common and (
            len(significant_common) >= len(significant_provider) * 0.5 or
            len(significant_common) >= len(significant_fe) * 0.5
        ):
            result["verified"] = True
            result["match_type"] = "partial"
            result["recommendation"] = "use_current"
            return result
    
    # No match - FindEnergy disagrees
    result["verified"] = False
    result["match_type"] = "none"
    
    # Determine recommendation based on confidence
    if fe_result.get("confidence") == "high":
        result["recommendation"] = "use_findenergy"
    elif fe_result.get("confidence") == "medium":
        result["recommendation"] = "flag_for_review"
    else:
        result["recommendation"] = "use_current"
    
    return result


def get_findenergy_providers_for_state(state: str, utility_type: str = "electric") -> List[Dict]:
    """
    Get list of providers for a state from FindEnergy.
    
    Args:
        state: State abbreviation
        utility_type: 'electric' or 'gas'
        
    Returns:
        List of provider dicts
    """
    state_lower = state.lower()
    
    if utility_type == "gas":
        url = f"https://findenergy.com/{state_lower}/natural-gas/"
    else:
        url = f"https://findenergy.com/{state_lower}/"
    
    response = _make_request(url)
    if not response:
        # Fall back to SERP
        result = query_findenergy_serp(f"{STATE_NAMES.get(state.upper(), state)} {utility_type} providers", utility_type)
        return result.get("providers", []) if result else []
    
    try:
        soup = BeautifulSoup(response.text, 'html.parser')
        providers = []
        
        # Look for provider links
        provider_links = soup.find_all('a', href=re.compile(r'/providers/'))
        for link in provider_links:
            name = link.get_text(strip=True)
            href = link.get('href', '')
            if name and len(name) > 2:
                providers.append({
                    "name": name,
                    "url": urljoin(url, href),
                    "state": state,
                    "utility_type": utility_type
                })
        
        return providers
    
    except Exception as e:
        print(f"Error getting state providers: {e}")
        return []


# Initialize cache directory
DATA_DIR.mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    print("FindEnergy Lookup Tests")
    print("=" * 60)
    
    # Test 1: Texas electric (Austin)
    print("\n1. Looking up Austin, TX electric providers...")
    result = lookup_findenergy(city="Austin", state="TX", utility_type="electric")
    if result:
        print(f"   Source: {result.get('source')}")
        print(f"   Confidence: {result.get('confidence')}")
        for p in result.get("providers", [])[:3]:
            print(f"   - {p.get('name')}")
    else:
        print("   No results")
    
    # Test 2: Virginia gas
    print("\n2. Looking up Richmond, VA gas providers...")
    result = lookup_findenergy(city="Richmond", state="VA", utility_type="gas")
    if result:
        print(f"   Source: {result.get('source')}")
        print(f"   Confidence: {result.get('confidence')}")
        for p in result.get("providers", [])[:3]:
            print(f"   - {p.get('name')}")
    else:
        print("   No results")
    
    # Test 3: Verification
    print("\n3. Verifying 'Austin Energy' for Austin, TX...")
    verify_result = verify_against_findenergy(
        provider_name="Austin Energy",
        city="Austin",
        state="TX",
        utility_type="electric"
    )
    print(f"   Verified: {verify_result.get('verified')}")
    print(f"   Match type: {verify_result.get('match_type')}")
    print(f"   Recommendation: {verify_result.get('recommendation')}")
