# Utility Company API Scrapers

## Context

Some utility companies have address lookup tools on their websites. These are authoritative sources. If Oncor's website says they serve an address, that's verified.

## Goal

- Scrape utility company address lookup tools
- Use as verification for high-confidence results
- Prioritize major utilities with largest coverage

## Priority Utilities

### Electric Utilities

| Utility | States | Customers | Website |
|---------|--------|-----------|---------|
| Duke Energy | NC, SC, FL, IN, OH, KY | 8.2M | duke-energy.com |
| Southern Company (Georgia Power, Alabama Power) | GA, AL, MS | 9M | southerncompany.com |
| Dominion Energy | VA, NC, SC, OH | 7M | dominionenergy.com |
| Xcel Energy | MN, CO, TX, WI, MI, NM, SD, ND | 3.7M | xcelenergy.com |
| Entergy | LA, AR, TX, MS | 3M | entergy.com |
| AEP (multiple brands) | TX, OH, OK, IN, MI, KY, TN, VA, WV | 5.5M | aep.com |
| Oncor | TX | 10M+ meters | oncor.com |
| CenterPoint | TX, MN, IN, OH, LA, MS | 7M+ | centerpointenergy.com |
| PG&E | CA | 16M | pge.com |
| SCE (Southern California Edison) | CA | 15M | sce.com |
| Florida Power & Light | FL | 5.6M | fpl.com |
| Con Edison | NY | 3.5M | coned.com |

### Gas Utilities

| Utility | States | Website |
|---------|--------|---------|
| Atmos Energy | TX, CO, KY, LA, MS, TN, VA, KS | atmosenergy.com |
| CenterPoint Energy | TX, MN, IN, OH, LA, MS | centerpointenergy.com |
| NiSource (Columbia Gas, NIPSCO) | OH, PA, VA, KY, MD, IN | nisource.com |
| Spire | MO, AL, MS | spireenergy.com |
| Southwest Gas | AZ, NV, CA | swgas.com |
| National Fuel Gas | NY, PA | natfuel.com |
| SoCalGas | CA | socalgas.com |
| Piedmont Natural Gas | NC, SC, TN | piedmontng.com |

## Implementation

### Step 1: Create Scraper Base Class

Create file: `utility_scrapers.py`

```python
"""
Scrapers for utility company address lookup tools.
Uses Playwright for JavaScript-rendered pages.
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Optional, Dict
from playwright.async_api import async_playwright, Browser, Page
import logging

logger = logging.getLogger(__name__)


class UtilityScraper(ABC):
    """Base class for utility company scrapers."""
    
    name: str = "Unknown"
    utility_type: str = "electric"  # or "gas"
    states_served: list = []
    
    def __init__(self):
        self.browser: Optional[Browser] = None
    
    async def init_browser(self):
        """Initialize Playwright browser."""
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(headless=True)
    
    async def close(self):
        """Close browser."""
        if self.browser:
            await self.browser.close()
    
    @abstractmethod
    async def check_address(self, address: str) -> Dict:
        """
        Check if utility serves this address.
        
        Returns:
            {
                'serves': bool,
                'confidence': 'verified',
                'provider_name': str,
                'details': dict (optional extra info)
            }
        """
        pass
    
    async def safe_check(self, address: str) -> Optional[Dict]:
        """Wrapper with error handling."""
        try:
            await self.init_browser()
            result = await self.check_address(address)
            return result
        except Exception as e:
            logger.error(f"{self.name} scraper error: {e}")
            return None
        finally:
            await self.close()


class OncorScraper(UtilityScraper):
    """Scraper for Oncor Electric (Texas)."""
    
    name = "Oncor"
    utility_type = "electric"
    states_served = ["TX"]
    
    async def check_address(self, address: str) -> Dict:
        page = await self.browser.new_page()
        
        try:
            # Navigate to Oncor's service area lookup
            await page.goto('https://www.oncor.com/content/oncorwww/us/en/home/smart-energy/am-i-in-oncor-territory.html')
            
            # Wait for the address input field
            await page.wait_for_selector('input[type="text"]', timeout=10000)
            
            # Enter address
            await page.fill('input[type="text"]', address)
            
            # Submit form
            await page.click('button[type="submit"]')
            
            # Wait for result
            await page.wait_for_timeout(3000)
            
            # Check for result indicators
            content = await page.content()
            
            if 'is in Oncor' in content or 'you are in Oncor' in content.lower():
                return {
                    'serves': True,
                    'confidence': 'verified',
                    'provider_name': 'Oncor Electric Delivery',
                    'source': 'Oncor website lookup'
                }
            elif 'not in Oncor' in content or 'outside' in content.lower():
                return {
                    'serves': False,
                    'confidence': 'verified',
                    'provider_name': None,
                    'source': 'Oncor website lookup'
                }
            else:
                # Couldn't determine
                return {
                    'serves': None,
                    'confidence': 'inconclusive',
                    'provider_name': None
                }
        
        finally:
            await page.close()


class CenterPointScraper(UtilityScraper):
    """Scraper for CenterPoint Energy (Texas, Minnesota, etc.)."""
    
    name = "CenterPoint"
    utility_type = "electric"  # Also does gas
    states_served = ["TX", "MN", "IN", "OH", "LA", "MS"]
    
    async def check_address(self, address: str) -> Dict:
        page = await self.browser.new_page()
        
        try:
            # CenterPoint has different sites per region
            # This example is for Texas
            await page.goto('https://www.centerpointenergy.com/en-us/residential')
            
            # Look for service area verification
            # Implementation depends on their actual UI
            
            # Placeholder - implement based on actual page structure
            return {
                'serves': None,
                'confidence': 'inconclusive',
                'provider_name': None
            }
        
        finally:
            await page.close()


class PGEScraper(UtilityScraper):
    """Scraper for PG&E (California)."""
    
    name = "PG&E"
    utility_type = "electric"  # Also does gas
    states_served = ["CA"]
    
    async def check_address(self, address: str) -> Dict:
        page = await self.browser.new_page()
        
        try:
            await page.goto('https://www.pge.com/')
            
            # PG&E requires login for detailed lookup
            # May need to use their public service area map instead
            
            return {
                'serves': None,
                'confidence': 'inconclusive',
                'provider_name': None
            }
        
        finally:
            await page.close()


class DukeEnergyScraper(UtilityScraper):
    """Scraper for Duke Energy (Carolinas, Florida, Midwest)."""
    
    name = "Duke Energy"
    utility_type = "electric"
    states_served = ["NC", "SC", "FL", "IN", "OH", "KY"]
    
    async def check_address(self, address: str) -> Dict:
        page = await self.browser.new_page()
        
        try:
            await page.goto('https://www.duke-energy.com/home/service-area')
            
            # Implementation based on Duke's actual UI
            
            return {
                'serves': None,
                'confidence': 'inconclusive',
                'provider_name': None
            }
        
        finally:
            await page.close()


class AtmosEnergyScraper(UtilityScraper):
    """Scraper for Atmos Energy (gas utility, multiple states)."""
    
    name = "Atmos Energy"
    utility_type = "gas"
    states_served = ["TX", "CO", "KY", "LA", "MS", "TN", "VA", "KS"]
    
    async def check_address(self, address: str) -> Dict:
        page = await self.browser.new_page()
        
        try:
            await page.goto('https://www.atmosenergy.com/')
            
            # Implementation based on Atmos's actual UI
            
            return {
                'serves': None,
                'confidence': 'inconclusive',
                'provider_name': None
            }
        
        finally:
            await page.close()


# Registry of available scrapers
SCRAPERS = {
    'oncor': OncorScraper,
    'centerpoint': CenterPointScraper,
    'pge': PGEScraper,
    'duke_energy': DukeEnergyScraper,
    'atmos': AtmosEnergyScraper,
}


def get_scrapers_for_state(state: str, utility_type: str = None) -> list:
    """Get list of scrapers that serve a given state."""
    matching = []
    for name, scraper_class in SCRAPERS.items():
        if state in scraper_class.states_served:
            if utility_type is None or scraper_class.utility_type == utility_type:
                matching.append(scraper_class)
    return matching


async def verify_with_utility_api(
    address: str,
    state: str,
    expected_provider: str = None,
    utility_type: str = 'electric'
) -> Optional[Dict]:
    """
    Try to verify address with utility company scraper.
    
    Args:
        address: Full street address
        state: 2-letter state code
        expected_provider: Provider name we expect (to pick right scraper)
        utility_type: 'electric' or 'gas'
    
    Returns:
        Verification result or None if no scraper available
    """
    scrapers = get_scrapers_for_state(state, utility_type)
    
    if not scrapers:
        return None
    
    # If we have an expected provider, try that scraper first
    if expected_provider:
        provider_lower = expected_provider.lower()
        for scraper_class in scrapers:
            if scraper_class.name.lower() in provider_lower or provider_lower in scraper_class.name.lower():
                scraper = scraper_class()
                result = await scraper.safe_check(address)
                if result and result.get('serves') is not None:
                    return result
    
    # Otherwise try all scrapers for this state
    for scraper_class in scrapers:
        scraper = scraper_class()
        result = await scraper.safe_check(address)
        if result and result.get('serves') is True:
            return result
    
    return None
```

### Step 2: Integrate Into Lookup Flow

In `utility_lookup.py`:

```python
from utility_scrapers import verify_with_utility_api
import asyncio

def lookup_electric_utility(lat, lon, city, county, state, zip_code, verify=True):
    # ... existing lookup logic to get candidate provider ...
    
    candidate_provider = "Oncor"  # From HIFLD/EIA/etc
    
    # If verification enabled, try utility company API
    if verify and candidate_provider:
        try:
            loop = asyncio.get_event_loop()
            api_result = loop.run_until_complete(
                verify_with_utility_api(
                    address=f"{lat},{lon}",  # Or construct full address
                    state=state,
                    expected_provider=candidate_provider,
                    utility_type='electric'
                )
            )
            
            if api_result:
                if api_result.get('serves') is True:
                    # Confirmed by utility API
                    return {
                        'name': api_result['provider_name'] or candidate_provider,
                        'confidence': 'verified',
                        'source': api_result.get('source', 'Utility company website'),
                        'verified': True
                    }
                elif api_result.get('serves') is False:
                    # Utility says they don't serve this address
                    # Our candidate is wrong - fall back to other methods
                    pass
        except Exception as e:
            print(f"Utility API verification failed: {e}")
    
    # ... rest of existing logic ...
```

### Step 3: Add Caching

To avoid scraping the same address repeatedly:

```python
import hashlib
import json
from datetime import datetime, timedelta

SCRAPER_CACHE_FILE = 'data/scraper_cache.json'
CACHE_TTL_DAYS = 30

def get_cache_key(address: str, utility_type: str) -> str:
    return hashlib.md5(f"{address}|{utility_type}".encode()).hexdigest()

def get_cached_result(address: str, utility_type: str) -> Optional[Dict]:
    try:
        with open(SCRAPER_CACHE_FILE, 'r') as f:
            cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    
    key = get_cache_key(address, utility_type)
    entry = cache.get(key)
    
    if not entry:
        return None
    
    # Check TTL
    cached_at = datetime.fromisoformat(entry['cached_at'])
    if datetime.now() - cached_at > timedelta(days=CACHE_TTL_DAYS):
        return None
    
    return entry['result']

def cache_result(address: str, utility_type: str, result: Dict):
    try:
        with open(SCRAPER_CACHE_FILE, 'r') as f:
            cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        cache = {}
    
    key = get_cache_key(address, utility_type)
    cache[key] = {
        'result': result,
        'cached_at': datetime.now().isoformat()
    }
    
    with open(SCRAPER_CACHE_FILE, 'w') as f:
        json.dump(cache, f)
```

### Step 4: Rate Limiting

To avoid overwhelming utility websites:

```python
import time
from collections import defaultdict

# Track last request time per domain
_last_request: Dict[str, float] = defaultdict(float)
MIN_REQUEST_INTERVAL = 5.0  # seconds between requests to same domain

async def rate_limited_request(scraper: UtilityScraper, address: str) -> Dict:
    domain = scraper.name.lower()
    
    # Check if we need to wait
    elapsed = time.time() - _last_request[domain]
    if elapsed < MIN_REQUEST_INTERVAL:
        await asyncio.sleep(MIN_REQUEST_INTERVAL - elapsed)
    
    result = await scraper.check_address(address)
    _last_request[domain] = time.time()
    
    return result
```

## Testing

### Test Individual Scraper
```python
import asyncio
from utility_scrapers import OncorScraper

async def test_oncor():
    scraper = OncorScraper()
    result = await scraper.safe_check("1234 Main St, Dallas, TX 75201")
    print(f"Oncor serves address: {result}")

asyncio.run(test_oncor())
```

### Test Verification Flow
```python
import asyncio
from utility_scrapers import verify_with_utility_api

async def test_verify():
    result = await verify_with_utility_api(
        address="1234 Main St, Dallas, TX 75201",
        state="TX",
        expected_provider="Oncor",
        utility_type="electric"
    )
    print(f"Verification result: {result}")

asyncio.run(test_verify())
```

## Notes

- Scrapers will break when utility websites change. Plan for maintenance.
- Some utilities require CAPTCHA or login. These may not be scrapable.
- Consider using utility APIs where available (some have partner/developer programs).
- Rate limit aggressively to avoid IP blocks.
- Cache results for 30 days (utility territories rarely change).

## Commit Message

```
Add utility company website scrapers for verification

- UtilityScraper base class with Playwright
- Oncor, CenterPoint, PG&E, Duke, Atmos scrapers
- Integration with lookup flow for verification
- Caching and rate limiting
```
