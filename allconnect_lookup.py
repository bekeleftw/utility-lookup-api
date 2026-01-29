#!/usr/bin/env python3
"""
AllConnect.com internet provider lookup.
Scrapes AllConnect.com for internet provider availability by city/ZIP.
Uses BrightData Web Unlocker for reliable scraping.
"""

import re
import json
import os
from typing import Optional, Dict, List
from urllib.parse import quote
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

# BrightData Web Unlocker configuration
BRIGHTDATA_WEB_UNLOCKER_HOST = "brd.superproxy.io"
BRIGHTDATA_WEB_UNLOCKER_PORT = "33335"
BRIGHTDATA_WEB_UNLOCKER_USER = os.environ.get("BRIGHTDATA_WEB_UNLOCKER_USER", "brd-customer-hl_6cc76bc7-zone-web_unlocker1")
BRIGHTDATA_WEB_UNLOCKER_PASS = os.environ.get("BRIGHTDATA_WEB_UNLOCKER_PASS", "1t5cvye3j5zy")

# Cache for lookups
CACHE_FILE = os.path.join(os.path.dirname(__file__), 'data', 'allconnect_cache.json')

# State abbreviation to URL format
STATE_ABBREV = {
    'AL': 'al', 'AK': 'ak', 'AZ': 'az', 'AR': 'ar', 'CA': 'ca', 'CO': 'co',
    'CT': 'ct', 'DE': 'de', 'FL': 'fl', 'GA': 'ga', 'HI': 'hi', 'ID': 'id',
    'IL': 'il', 'IN': 'in', 'IA': 'ia', 'KS': 'ks', 'KY': 'ky', 'LA': 'la',
    'ME': 'me', 'MD': 'md', 'MA': 'ma', 'MI': 'mi', 'MN': 'mn', 'MS': 'ms',
    'MO': 'mo', 'MT': 'mt', 'NE': 'ne', 'NV': 'nv', 'NH': 'nh', 'NJ': 'nj',
    'NM': 'nm', 'NY': 'ny', 'NC': 'nc', 'ND': 'nd', 'OH': 'oh', 'OK': 'ok',
    'OR': 'or', 'PA': 'pa', 'RI': 'ri', 'SC': 'sc', 'SD': 'sd', 'TN': 'tn',
    'TX': 'tx', 'UT': 'ut', 'VT': 'vt', 'VA': 'va', 'WA': 'wa', 'WV': 'wv',
    'WI': 'wi', 'WY': 'wy', 'DC': 'dc'
}


def load_cache() -> Dict:
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}


def save_cache(cache: Dict):
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, 'w') as f:
        json.dump(cache, f, indent=2)


def lookup_allconnect(zip_code: str, city: str = None, state: str = None) -> Optional[Dict]:
    """
    Look up internet providers from AllConnect by city/ZIP.
    
    Args:
        zip_code: 5-digit ZIP code
        city: City name (required for URL)
        state: State abbreviation (required for URL)
        
    Returns:
        Dict with providers list or None if lookup fails
    """
    if not zip_code or len(zip_code) < 5:
        return None
    
    zip_code = zip_code[:5]
    
    # Check cache first
    cache_key = f"{zip_code}_{city}_{state}".lower()
    cache = load_cache()
    if cache_key in cache:
        cached = cache[cache_key]
        if cached.get('_cached_at'):
            cached_at = datetime.fromisoformat(cached['_cached_at'])
            if datetime.now() - cached_at < timedelta(days=7):
                return cached
    
    # Need city and state for AllConnect URL
    if not city or not state:
        city, state = get_city_state_from_zip(zip_code)
    
    if not city or not state:
        print(f"AllConnect: Could not determine city/state for ZIP {zip_code}")
        return None
    
    # Format for URL
    state_code = state.upper()
    if state_code not in STATE_ABBREV:
        print(f"AllConnect: Unknown state {state}")
        return None
    
    state_url = STATE_ABBREV[state_code]
    city_url = city.lower().replace(' ', '-').replace("'", "")
    
    # AllConnect URL format: /local/tx/austin?zip=78701
    url = f"https://www.allconnect.com/local/{state_url}/{city_url}?zip={zip_code}"
    
    try:
        # Use BrightData Web Unlocker
        proxy_url = f"http://{BRIGHTDATA_WEB_UNLOCKER_USER}:{BRIGHTDATA_WEB_UNLOCKER_PASS}@{BRIGHTDATA_WEB_UNLOCKER_HOST}:{BRIGHTDATA_WEB_UNLOCKER_PORT}"
        proxies = {"http": proxy_url, "https": proxy_url}
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }
        
        print(f"  AllConnect: Fetching {url}")
        
        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            response = requests.get(url, headers=headers, proxies=proxies, timeout=30, verify=False)
        except Exception as proxy_err:
            print(f"  AllConnect: Web Unlocker failed ({proxy_err}), trying direct...")
            response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code != 200:
            print(f"AllConnect: HTTP {response.status_code} for {url}")
            return None
        
        html = response.text
        providers = parse_allconnect_html(html)
        
        if providers:
            result = {
                'providers': providers,
                'provider_count': len(providers),
                'source': 'allconnect',
                'zip_code': zip_code,
                'city': city,
                'state': state,
                '_cached_at': datetime.now().isoformat()
            }
            
            # Cache the result
            cache[cache_key] = result
            save_cache(cache)
            
            return result
        
    except Exception as e:
        print(f"AllConnect lookup error: {e}")
    
    return None


def parse_allconnect_html(html: str) -> List[Dict]:
    """
    Parse AllConnect HTML to extract provider information.
    """
    providers = []
    seen = set()  # Track normalized names to avoid duplicates
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Canonical provider names (for deduplication)
    CANONICAL_NAMES = {
        'at&t': 'AT&T', 'att': 'AT&T',
        'xfinity': 'Xfinity', 'comcast': 'Xfinity',
        'spectrum': 'Spectrum', 'charter': 'Spectrum',
        'verizon': 'Verizon', 'fios': 'Verizon Fios',
        'google fiber': 'Google Fiber',
        'frontier': 'Frontier',
        'centurylink': 'CenturyLink', 'lumen': 'CenturyLink',
        'cox': 'Cox',
        'optimum': 'Optimum', 'altice': 'Optimum',
        'mediacom': 'Mediacom',
        'windstream': 'Windstream',
        'hughesnet': 'HughesNet',
        'viasat': 'Viasat',
        't-mobile': 'T-Mobile',
        'starlink': 'Starlink',
        'earthlink': 'EarthLink',
        'astound': 'Astound', 'rcn': 'Astound',
        'grande': 'Grande',
        'ziply': 'Ziply Fiber',
        'consolidated': 'Consolidated',
        'tds': 'TDS',
        'breezeline': 'Breezeline',
        'wow': 'WOW',
        'metronet': 'Metronet',
        'ting': 'Ting',
        'fidium': 'Fidium',
    }
    
    def normalize_name(name):
        """Normalize provider name for deduplication."""
        return name.lower().strip()
    
    def get_canonical_name(name):
        """Get canonical provider name."""
        normalized = normalize_name(name)
        return CANONICAL_NAMES.get(normalized, name)
    
    # Find provider names in headings/titles
    provider_patterns = [
        r'(AT&T|Xfinity|Spectrum|Verizon|Google Fiber|Frontier|CenturyLink|Cox|Optimum|Mediacom|Windstream|HughesNet|Viasat|T-Mobile|Starlink|EarthLink|Astound|Grande|Ziply|Consolidated|TDS|Breezeline|Altice|RCN|WOW|Metronet|Ting|Fidium)\s*(Internet|Fiber|5G)?',
    ]
    
    for pattern in provider_patterns:
        for match in re.finditer(pattern, html, re.IGNORECASE):
            raw_name = match.group(1)
            tech_hint = match.group(2) if match.lastindex >= 2 else None
            
            # Get canonical name and check for duplicates
            canonical = get_canonical_name(raw_name)
            normalized = normalize_name(canonical)
            
            if normalized not in seen:
                seen.add(normalized)
                
                # Try to determine technology
                technology = 'Unknown'
                if tech_hint:
                    if 'fiber' in tech_hint.lower():
                        technology = 'Fiber'
                    elif '5g' in tech_hint.lower():
                        technology = '5G'
                
                # Look for speed info near the provider name
                speed_match = re.search(rf'{re.escape(raw_name)}[^0-9]*(\d+(?:,\d+)?)\s*Mbps', html, re.IGNORECASE)
                max_speed = None
                if speed_match:
                    max_speed = int(speed_match.group(1).replace(',', ''))
                
                providers.append({
                    'name': canonical,
                    'technology': technology,
                    'max_download_mbps': max_speed,
                    'source': 'allconnect'
                })
    
    # Method 2: Parse JSON-LD schema if available
    schema_scripts = soup.find_all('script', type='application/ld+json')
    for script in schema_scripts:
        try:
            data = json.loads(script.string)
            if isinstance(data, dict):
                desc = data.get('description', '')
                for provider in ['AT&T', 'Spectrum', 'Xfinity', 'Verizon', 'Google Fiber', 'Frontier']:
                    canonical = get_canonical_name(provider)
                    normalized = normalize_name(canonical)
                    if provider.lower() in desc.lower() and normalized not in seen:
                        seen.add(normalized)
                        providers.append({
                            'name': canonical,
                            'technology': 'Unknown',
                            'source': 'allconnect'
                        })
        except:
            continue
    
    # Method 3: Look for provider cards by class patterns
    cards = soup.find_all(['div', 'article'], class_=re.compile(r'provider|card|plan', re.I))
    for card in cards:
        text = card.get_text()
        for provider in ['AT&T', 'Spectrum', 'Xfinity', 'Verizon', 'Google Fiber', 'Frontier', 'Cox', 'CenturyLink']:
            canonical = get_canonical_name(provider)
            normalized = normalize_name(canonical)
            if provider in text and normalized not in seen:
                seen.add(normalized)
                
                speed_match = re.search(r'(\d+(?:,\d+)?)\s*Mbps', text)
                max_speed = int(speed_match.group(1).replace(',', '')) if speed_match else None
                
                technology = 'Unknown'
                if 'fiber' in text.lower():
                    technology = 'Fiber'
                elif 'cable' in text.lower():
                    technology = 'Cable'
                elif '5g' in text.lower():
                    technology = '5G'
                elif 'dsl' in text.lower():
                    technology = 'DSL'
                
                providers.append({
                    'name': canonical,
                    'technology': technology,
                    'max_download_mbps': max_speed,
                    'source': 'allconnect'
                })
    
    return providers


def get_city_state_from_zip(zip_code: str) -> tuple:
    """Get city and state from ZIP code."""
    try:
        url = f"https://api.zippopotam.us/us/{zip_code}"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            places = data.get('places', [])
            if places:
                return places[0].get('place name', ''), places[0].get('state abbreviation', '')
    except:
        pass
    return None, None


if __name__ == '__main__':
    # Test lookups
    test_cases = [
        ('78701', 'Austin', 'TX'),
        ('07102', 'Newark', 'NJ'),
        ('90210', 'Beverly Hills', 'CA'),
    ]
    
    for zip_code, city, state in test_cases:
        print(f"\n{'='*60}")
        print(f"Looking up {city}, {state} ({zip_code})...")
        result = lookup_allconnect(zip_code, city, state)
        
        if result:
            print(f"Found {result['provider_count']} providers:")
            for p in result['providers']:
                speed = f" ({p.get('max_download_mbps')} Mbps)" if p.get('max_download_mbps') else ""
                print(f"  - {p['name']} ({p.get('technology', 'Unknown')}){speed}")
        else:
            print("No results")
