"""
SERP Verification Layer for Utility Lookups

Optional verification step that uses web search to triple-check utility lookup results.
Implements caching to minimize API costs.

Usage:
    from serp_verification import verify_utility_via_serp, get_cached_verification
    
    result = verify_utility_via_serp(
        address="123 Main St",
        city="Nashville",
        state="TN",
        utility_type="gas",
        expected_utility="Piedmont Natural Gas"
    )
"""

import json
import os
import re
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, field
import requests
from bs4 import BeautifulSoup

# Configuration
CACHE_DIR = os.path.join(os.path.dirname(__file__), 'data', 'serp_cache')
CACHE_TTL_DAYS = 30  # Cache results for 30 days

# BrightData proxy credentials (from environment or defaults)
BRIGHTDATA_PROXY_HOST = os.getenv('BRIGHTDATA_PROXY_HOST', 'brd.superproxy.io')
BRIGHTDATA_PROXY_PORT = os.getenv('BRIGHTDATA_PROXY_PORT', '33335')
BRIGHTDATA_PROXY_USER = os.getenv('BRIGHTDATA_PROXY_USER', 'brd-customer-hl_6cc76bc7-zone-address_search')
BRIGHTDATA_PROXY_PASS = os.getenv('BRIGHTDATA_PROXY_PASS', 'n59dskgnctqr')

# OpenAI API key
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Known utility name aliases for matching
UTILITY_ALIASES = {
    'fpl': ['florida power & light', 'florida power and light', 'fpl', 'florida power light'],
    'duke': ['duke energy', 'duke energy carolinas', 'duke energy florida', 'duke energy progress'],
    'georgia power': ['georgia power', 'georgia power company', 'southern company'],
    'pge': ['pacific gas & electric', 'pacific gas and electric', 'pg&e', 'pge', 'pacific gas electric'],
    'sce': ['southern california edison', 'sce', 'edison'],
    'sdge': ['san diego gas & electric', 'sdg&e', 'sdge', 'san diego gas electric'],
    'socalgas': ['southern california gas', 'socalgas', 'socal gas'],
    'comed': ['commonwealth edison', 'comed', 'com ed'],
    'oncor': ['oncor', 'oncor electric', 'oncor electric delivery'],
    'centerpoint': ['centerpoint', 'centerpoint energy', 'center point'],
    'atmos': ['atmos', 'atmos energy'],
    'piedmont': ['piedmont', 'piedmont natural gas', 'piedmont ng'],
    'dominion': ['dominion', 'dominion energy', 'dominion energy virginia', 'columbia gas of virginia'],
    'xcel': ['xcel', 'xcel energy', 'northern states power', 'public service co of colorado'],
    'entergy': ['entergy', 'entergy louisiana', 'entergy texas', 'entergy arkansas', 'entergy new orleans'],
    'aep': ['aep', 'american electric power', 'aep texas', 'aep ohio', 'columbus division of power'],
    'peco': ['peco', 'peco energy'],
    'pseg': ['pseg', 'pse&g', 'public service electric and gas', 'public service electric & gas'],
    'national grid': ['national grid', 'nationalgrid', 'niagara mohawk', 'niagara mohawk power'],
    'eversource': ['eversource', 'eversource energy', 'nstar', 'nstar electric', 'connecticut light & power', 'connecticut light and power', 'public service co of nh'],
    'consumers': ['consumers energy', 'consumers'],
    'dte': ['dte', 'dte energy', 'detroit edison'],
    'we energies': ['we energies', 'wisconsin energy', 'wisconsin electric'],
    'austin energy': ['austin energy', 'city of austin'],
    'ladwp': ['ladwp', 'los angeles department of water and power', 'la dwp'],
    'seattle city light': ['seattle city light', 'city of seattle'],
    'pepco': ['pepco', 'potomac electric power'],
    'bge': ['bge', 'baltimore gas and electric', 'baltimore gas & electric'],
    'lge': ['lg&e', 'lge', 'louisville gas & electric', 'louisville gas and electric'],
    'oge': ['og&e', 'oge', 'oklahoma gas & electric', 'oklahoma gas and electric'],
    'ameren': ['ameren', 'ameren missouri', 'ameren illinois', 'union electric'],
    'nw natural': ['nw natural', 'northwest natural', 'northwest natural gas'],
    'rocky mountain power': ['rocky mountain power', 'pacificorp'],
    'pnm': ['pnm', 'public service co of nm', 'public service company of new mexico'],
    'black hills': ['black hills', 'black hills energy', 'cheyenne light fuel & power', 'cheyenne light fuel power'],
    'midamerican': ['midamerican', 'midamerican energy', 'berkshire hathaway energy'],
    'rhode island energy': ['rhode island energy', 'national grid rhode island'],
    'versant': ['versant', 'versant power', 'central maine power'],
    'burlington electric': ['burlington electric', 'burlington electric department', 'bed'],
    'green mountain power': ['green mountain power', 'gmp'],
    'chugach': ['chugach', 'chugach electric', 'anchorage municipal light', 'ml&p'],
    'aes indiana': ['aes indiana', 'indianapolis power & light', 'indianapolis power and light', 'ipl'],
    'spire': ['spire', 'spire mississippi', 'spire missouri', 'spire alabama'],
    'peoples gas': ['peoples gas', 'peoples natural gas', 'equitable gas'],
    'pgw': ['pgw', 'philadelphia gas works'],
    'montana dakota': ['montana-dakota', 'montana dakota', 'montana-dakota utilities', 'mdu'],
    'nv energy': ['nv energy', 'nevada power', 'nevada power co'],
    'entergy arkansas': ['entergy arkansas', 'little rock pine bluff'],
    'citizens gas': ['citizens energy group', 'citizens gas', 'citizens energy'],
    'connecticut natural gas': ['connecticut natural gas', 'conneticut natural gas', 'cng'],
    'northwestern': ['northwestern', 'northwestern energy'],
}


@dataclass
class SerpVerificationResult:
    """Result of SERP verification."""
    verified: bool
    serp_utility: Optional[str] = None
    confidence_boost: float = 0.0
    sources: List[str] = field(default_factory=list)
    search_query: str = ""
    cached: bool = False
    notes: str = ""


def normalize_utility_name(name: str) -> str:
    """Normalize utility name for comparison."""
    if not name:
        return ""
    
    normalized = name.lower().strip()
    
    # Remove common suffixes
    suffixes = ['inc', 'inc.', 'llc', 'llc.', 'corp', 'corp.', 'corporation',
                'company', 'co', 'co.', 'ltd', 'lp', 'l.p.']
    for suffix in suffixes:
        normalized = re.sub(rf'\b{suffix}\b', '', normalized)
    
    # Remove punctuation and extra whitespace
    normalized = re.sub(r'[^\w\s]', '', normalized)
    normalized = ' '.join(normalized.split())
    
    return normalized


def is_alias(name1: str, name2: str) -> bool:
    """Check if two utility names are aliases of each other."""
    norm1 = normalize_utility_name(name1)
    norm2 = normalize_utility_name(name2)
    
    if not norm1 or not norm2:
        return False
    
    # Direct match
    if norm1 == norm2:
        return True
    
    # One contains the other
    if len(norm1) > 3 and len(norm2) > 3:
        if norm1 in norm2 or norm2 in norm1:
            return True
    
    # Check alias groups
    for key, aliases in UTILITY_ALIASES.items():
        aliases_lower = [a.lower() for a in aliases]
        if any(a in norm1 or norm1 in a for a in aliases_lower):
            if any(a in norm2 or norm2 in a for a in aliases_lower):
                return True
    
    return False


def get_cache_key(city: str, state: str, zip_prefix: str, utility_type: str) -> str:
    """Generate cache key for SERP result."""
    key_str = f"{utility_type}:{state}:{city}:{zip_prefix}".lower()
    return hashlib.md5(key_str.encode()).hexdigest()


def get_cached_verification(city: str, state: str, zip_code: str, utility_type: str) -> Optional[SerpVerificationResult]:
    """Check cache for existing SERP verification."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    
    zip_prefix = zip_code[:3] if zip_code and len(zip_code) >= 3 else ""
    cache_key = get_cache_key(city, state, zip_prefix, utility_type)
    cache_file = os.path.join(CACHE_DIR, f"{cache_key}.json")
    
    if not os.path.exists(cache_file):
        return None
    
    try:
        with open(cache_file, 'r') as f:
            cached = json.load(f)
        
        # Check if cache is still valid
        cached_time = datetime.fromisoformat(cached.get('timestamp', '2000-01-01'))
        if datetime.now() - cached_time > timedelta(days=CACHE_TTL_DAYS):
            return None
        
        return SerpVerificationResult(
            verified=cached.get('verified', False),
            serp_utility=cached.get('serp_utility'),
            confidence_boost=cached.get('confidence_boost', 0.0),
            sources=cached.get('sources', []),
            search_query=cached.get('search_query', ''),
            cached=True,
            notes=cached.get('notes', '')
        )
    except (json.JSONDecodeError, KeyError):
        return None


def save_to_cache(city: str, state: str, zip_code: str, utility_type: str, result: SerpVerificationResult):
    """Save SERP verification result to cache."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    
    zip_prefix = zip_code[:3] if zip_code and len(zip_code) >= 3 else ""
    cache_key = get_cache_key(city, state, zip_prefix, utility_type)
    cache_file = os.path.join(CACHE_DIR, f"{cache_key}.json")
    
    cache_data = {
        'timestamp': datetime.now().isoformat(),
        'city': city,
        'state': state,
        'zip_prefix': zip_prefix,
        'utility_type': utility_type,
        'verified': result.verified,
        'serp_utility': result.serp_utility,
        'confidence_boost': result.confidence_boost,
        'sources': result.sources,
        'search_query': result.search_query,
        'notes': result.notes
    }
    
    with open(cache_file, 'w') as f:
        json.dump(cache_data, f, indent=2)


def search_google(query: str) -> Optional[str]:
    """Execute Google search via BrightData proxy."""
    if not BRIGHTDATA_PROXY_PASS:
        return None
    
    search_url = f"https://www.google.com/search?q={requests.utils.quote(query)}"
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
            timeout=10,
            verify=False,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        )
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Remove scripts and styles
        for script in soup(["script", "style"]):
            script.decompose()
        
        return soup.get_text(separator=' ')[:5000]
        
    except Exception as e:
        print(f"SERP search error: {e}")
        return None


def analyze_with_llm(search_text: str, address: str, utility_type: str, expected_utility: str) -> Optional[Dict]:
    """Use OpenAI to analyze search results."""
    if not OPENAI_API_KEY:
        return None
    
    try:
        prompt = f"""Analyze these Google search results to identify the {utility_type} utility provider for: {address}

Search results:
{search_text[:3000]}

Our database suggests: {expected_utility}

Based on the search results, what is the actual {utility_type} utility provider?
Reply with ONLY a JSON object:
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
        
        # Parse JSON from response
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        
        return json.loads(content.strip())
        
    except Exception as e:
        print(f"LLM analysis error: {e}")
        return None


def analyze_with_regex(search_text: str, expected_utility: str) -> Optional[Dict]:
    """Fallback regex-based analysis."""
    text_upper = search_text.upper()
    
    # Look for utility name patterns
    utility_patterns = [
        r'\b([A-Z][A-Z]+\s+(?:ENERGY|ELECTRIC|GAS|POWER|UTILITIES?))\b',
        r'\b(CITY OF [A-Z]+(?:\s+(?:WATER|UTILITIES?))?)\b',
        r'\b(PIEDMONT NATURAL GAS)\b',
        r'\b(DUKE ENERGY[A-Z\s]*)\b',
        r'\b(GEORGIA POWER)\b',
        r'\b(FLORIDA POWER\s*(?:&|AND)?\s*LIGHT)\b',
        r'\b(CENTERPOINT ENERGY)\b',
        r'\b(ATMOS ENERGY)\b',
    ]
    
    found_utilities = []
    for pattern in utility_patterns:
        matches = re.findall(pattern, text_upper)
        found_utilities.extend(matches)
    
    # Clean up results
    found_utilities = list(set([
        u.strip() for u in found_utilities 
        if len(u) > 5 and len(u) < 50 
        and not any(x in u for x in ['SEARCH', 'GOOGLE', 'CLICK', 'SIGN', 'FILTER', 'MENU'])
    ]))
    
    if not found_utilities:
        return None
    
    # Check if expected utility is in results
    expected_upper = expected_utility.upper() if expected_utility else ""
    for found in found_utilities:
        if is_alias(expected_upper, found):
            return {
                "provider": found,
                "confidence": "high",
                "matches_database": True,
                "notes": "Regex match confirmed"
            }
    
    # Return first found utility as alternative
    return {
        "provider": found_utilities[0],
        "confidence": "medium",
        "matches_database": False,
        "notes": f"Found {len(found_utilities)} utilities, none matched expected"
    }


def calculate_confidence_adjustment(expected: str, serp_result: Dict, sources: List[str]) -> float:
    """Calculate confidence adjustment based on SERP verification."""
    if serp_result is None:
        return 0.0
    
    serp_provider = serp_result.get('provider', '')
    matches = serp_result.get('matches_database', False)
    
    if matches or is_alias(expected, serp_provider):
        # SERP confirms our result
        if len(sources) >= 2:
            return 0.15  # Strong confirmation
        return 0.10  # Weak confirmation
    
    # SERP suggests different utility
    return -0.20  # Flag for review


def verify_utility_via_serp(
    address: str,
    city: str,
    state: str,
    utility_type: str,
    expected_utility: str,
    zip_code: str = "",
    confidence_threshold: float = 0.7,
    use_cache: bool = True
) -> SerpVerificationResult:
    """
    Optional verification step using web search.
    
    Args:
        address: Full street address
        city: City name
        state: 2-letter state code
        utility_type: "electric" or "gas"
        expected_utility: The utility we found via GIS/county lookup
        zip_code: ZIP code (used for caching)
        confidence_threshold: Only verify if below this (not used currently)
        use_cache: Whether to use cached results
    
    Returns:
        SerpVerificationResult with verification details
    """
    # Check cache first
    if use_cache:
        cached = get_cached_verification(city, state, zip_code, utility_type)
        if cached:
            # Update verification based on expected utility
            cached.verified = is_alias(expected_utility, cached.serp_utility) if cached.serp_utility else False
            return cached
    
    # Build search query
    query = f'"{city}" "{state}" {utility_type} utility provider'
    
    # Execute search
    search_text = search_google(query)
    
    if not search_text:
        return SerpVerificationResult(
            verified=False,
            confidence_boost=0.0,
            search_query=query,
            notes="Search failed"
        )
    
    # Analyze results
    if OPENAI_API_KEY:
        analysis = analyze_with_llm(search_text, f"{address}, {city}, {state}", utility_type, expected_utility)
    else:
        analysis = analyze_with_regex(search_text, expected_utility)
    
    if not analysis:
        return SerpVerificationResult(
            verified=False,
            confidence_boost=0.0,
            search_query=query,
            notes="Analysis failed"
        )
    
    # Build result
    serp_utility = analysis.get('provider')
    matches = analysis.get('matches_database', False) or is_alias(expected_utility, serp_utility)
    confidence_boost = calculate_confidence_adjustment(expected_utility, analysis, [])
    
    result = SerpVerificationResult(
        verified=matches,
        serp_utility=serp_utility,
        confidence_boost=confidence_boost,
        sources=[],
        search_query=query,
        cached=False,
        notes=analysis.get('notes', '')
    )
    
    # Save to cache
    if use_cache and zip_code:
        save_to_cache(city, state, zip_code, utility_type, result)
    
    return result


def batch_verify(lookups: List[Dict], utility_type: str = "electric") -> List[Dict]:
    """
    Batch verify multiple lookups with SERP.
    
    Args:
        lookups: List of dicts with 'address', 'city', 'state', 'zip_code', 'expected_utility'
        utility_type: "electric" or "gas"
    
    Returns:
        List of verification results
    """
    results = []
    
    for lookup in lookups:
        result = verify_utility_via_serp(
            address=lookup.get('address', ''),
            city=lookup.get('city', ''),
            state=lookup.get('state', ''),
            utility_type=utility_type,
            expected_utility=lookup.get('expected_utility', ''),
            zip_code=lookup.get('zip_code', '')
        )
        
        results.append({
            'lookup': lookup,
            'verification': {
                'verified': result.verified,
                'serp_utility': result.serp_utility,
                'confidence_boost': result.confidence_boost,
                'cached': result.cached,
                'notes': result.notes
            }
        })
    
    return results


# CLI for testing
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 4:
        print("Usage: python serp_verification.py <city> <state> <utility_type> [expected_utility]")
        print("Example: python serp_verification.py Nashville TN gas 'Piedmont Natural Gas'")
        sys.exit(1)
    
    city = sys.argv[1]
    state = sys.argv[2]
    utility_type = sys.argv[3]
    expected = sys.argv[4] if len(sys.argv) > 4 else ""
    
    print(f"Verifying {utility_type} utility for {city}, {state}...")
    print(f"Expected: {expected}")
    
    result = verify_utility_via_serp(
        address="",
        city=city,
        state=state,
        utility_type=utility_type,
        expected_utility=expected,
        zip_code=""
    )
    
    print(f"\nResult:")
    print(f"  Verified: {result.verified}")
    print(f"  SERP Utility: {result.serp_utility}")
    print(f"  Confidence Boost: {result.confidence_boost}")
    print(f"  Cached: {result.cached}")
    print(f"  Notes: {result.notes}")
