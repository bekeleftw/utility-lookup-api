#!/usr/bin/env python3
"""
BroadbandNow internet provider lookup.
Scrapes BroadbandNow.com for internet provider availability by ZIP code.
"""

import re
import json
import os
from typing import Optional, Dict, List
from urllib.parse import quote

# Use existing SERP infrastructure for requests
try:
    from browser_verification import make_serp_request
except ImportError:
    make_serp_request = None

import requests

# Cache for lookups
CACHE_FILE = os.path.join(os.path.dirname(__file__), 'data', 'broadbandnow_cache.json')

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


def lookup_broadbandnow(zip_code: str, city: str = None, state: str = None) -> Optional[Dict]:
    """
    Look up internet providers from BroadbandNow by ZIP code.
    
    Args:
        zip_code: 5-digit ZIP code
        city: City name (optional, improves URL accuracy)
        state: State name or abbreviation (optional)
        
    Returns:
        Dict with providers list or None if lookup fails
    """
    if not zip_code or len(zip_code) < 5:
        return None
    
    zip_code = zip_code[:5]
    
    # Check cache first
    cache = load_cache()
    if zip_code in cache:
        cached = cache[zip_code]
        # Cache for 7 days
        if cached.get('_cached_at'):
            from datetime import datetime, timedelta
            cached_at = datetime.fromisoformat(cached['_cached_at'])
            if datetime.now() - cached_at < timedelta(days=7):
                return cached
    
    # Build URL - BroadbandNow uses state/city format
    # If we don't have city/state, we'll try to get it from the ZIP
    if not city or not state:
        # Try to get city/state from ZIP using a simple lookup
        city, state = get_city_state_from_zip(zip_code)
    
    if not city or not state:
        print(f"BroadbandNow: Could not determine city/state for ZIP {zip_code}")
        return None
    
    # Format state name for URL (e.g., "New Jersey" -> "New-Jersey")
    state_formatted = format_state_for_url(state)
    city_formatted = city.replace(' ', '-').replace("'", "")
    
    url = f"https://broadbandnow.com/{state_formatted}/{city_formatted}?zip={zip_code}"
    
    try:
        # Try with requests first (faster)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code != 200:
            print(f"BroadbandNow: HTTP {response.status_code} for {url}")
            return None
        
        html = response.text
        providers = parse_broadbandnow_html(html)
        
        if providers:
            result = {
                'providers': providers,
                'provider_count': len(providers),
                'source': 'broadbandnow',
                'zip_code': zip_code,
                '_cached_at': __import__('datetime').datetime.now().isoformat()
            }
            
            # Cache the result
            cache[zip_code] = result
            save_cache(cache)
            
            return result
        
    except Exception as e:
        print(f"BroadbandNow lookup error: {e}")
    
    return None


def parse_broadbandnow_html(html: str) -> List[Dict]:
    """
    Parse BroadbandNow HTML to extract provider information.
    """
    providers = []
    seen = set()
    
    # Method 1: Extract from JSON-LD schema
    schema_pattern = r'\{"@type":"Offer"[^}]+?"itemOffered":\{[^}]+?"name":"([^"]+)"[^}]+?\}[^}]*?"category":"([^"]+)"'
    for match in re.finditer(schema_pattern, html):
        name = match.group(1)
        category = match.group(2)
        if name not in seen:
            seen.add(name)
            providers.append({
                'name': name,
                'technology': category.split(',')[0].strip() if category else 'Unknown',
                'source': 'broadbandnow'
            })
    
    # Method 2: Extract from providersCTAData JavaScript
    cta_pattern = r'window\.providersCTAData\[\d+\]\s*=\s*(\{[^;]+\});'
    for match in re.finditer(cta_pattern, html):
        try:
            data = json.loads(match.group(1))
            name = data.get('serviceProvider')
            if name and name not in seen:
                seen.add(name)
                providers.append({
                    'name': name,
                    'technology': data.get('planInternetType', 'Unknown'),
                    'availability': data.get('planAvailability'),
                    'source': 'broadbandnow'
                })
        except json.JSONDecodeError:
            continue
    
    # Method 3: Simple regex for provider names in structured sections
    # Look for patterns like "Shop Verizon Fios" or provider cards
    shop_pattern = r'\[Shop ([^\]]+)\]'
    for match in re.finditer(shop_pattern, html):
        name = match.group(1).strip()
        if name and name not in seen and len(name) < 50:
            seen.add(name)
            providers.append({
                'name': name,
                'technology': 'Unknown',
                'source': 'broadbandnow'
            })
    
    return providers


def get_city_state_from_zip(zip_code: str) -> tuple:
    """Get city and state from ZIP code using Census geocoder or fallback."""
    try:
        # Try Census geocoder
        url = f"https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress?address={zip_code}&benchmark=Public_AR_Current&vintage=Current_Current&format=json"
        response = requests.get(url, timeout=10)
        data = response.json()
        
        matches = data.get('result', {}).get('addressMatches', [])
        if matches:
            components = matches[0].get('addressComponents', {})
            city = components.get('city', '')
            state = components.get('state', '')
            return city, state
    except:
        pass
    
    # Fallback: try a simple ZIP lookup service
    try:
        url = f"https://api.zippopotam.us/us/{zip_code}"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            places = data.get('places', [])
            if places:
                return places[0].get('place name', ''), places[0].get('state', '')
    except:
        pass
    
    return None, None


def format_state_for_url(state: str) -> str:
    """Format state name for BroadbandNow URL."""
    # State abbreviation to full name mapping
    STATE_NAMES = {
        'AL': 'Alabama', 'AK': 'Alaska', 'AZ': 'Arizona', 'AR': 'Arkansas',
        'CA': 'California', 'CO': 'Colorado', 'CT': 'Connecticut', 'DE': 'Delaware',
        'FL': 'Florida', 'GA': 'Georgia', 'HI': 'Hawaii', 'ID': 'Idaho',
        'IL': 'Illinois', 'IN': 'Indiana', 'IA': 'Iowa', 'KS': 'Kansas',
        'KY': 'Kentucky', 'LA': 'Louisiana', 'ME': 'Maine', 'MD': 'Maryland',
        'MA': 'Massachusetts', 'MI': 'Michigan', 'MN': 'Minnesota', 'MS': 'Mississippi',
        'MO': 'Missouri', 'MT': 'Montana', 'NE': 'Nebraska', 'NV': 'Nevada',
        'NH': 'New-Hampshire', 'NJ': 'New-Jersey', 'NM': 'New-Mexico', 'NY': 'New-York',
        'NC': 'North-Carolina', 'ND': 'North-Dakota', 'OH': 'Ohio', 'OK': 'Oklahoma',
        'OR': 'Oregon', 'PA': 'Pennsylvania', 'RI': 'Rhode-Island', 'SC': 'South-Carolina',
        'SD': 'South-Dakota', 'TN': 'Tennessee', 'TX': 'Texas', 'UT': 'Utah',
        'VT': 'Vermont', 'VA': 'Virginia', 'WA': 'Washington', 'WV': 'West-Virginia',
        'WI': 'Wisconsin', 'WY': 'Wyoming', 'DC': 'District-of-Columbia'
    }
    
    state = state.strip().upper()
    if state in STATE_NAMES:
        return STATE_NAMES[state]
    
    # Already a full name, just format it
    return state.title().replace(' ', '-')


if __name__ == '__main__':
    # Test lookups
    test_cases = [
        ('78701', 'Austin', 'TX'),  # Austin, TX
        ('07102', 'Newark', 'NJ'),  # Newark, NJ (should have Verizon Fios)
        ('90210', 'Beverly Hills', 'CA'),  # Beverly Hills, CA
    ]
    
    for zip_code, city, state in test_cases:
        print(f"\n{'='*60}")
        print(f"Looking up {city}, {state} ({zip_code})...")
        result = lookup_broadbandnow(zip_code, city, state)
        
        if result:
            print(f"Found {result['provider_count']} providers:")
            for p in result['providers']:
                print(f"  - {p['name']} ({p.get('technology', 'Unknown')})")
        else:
            print("No results")
