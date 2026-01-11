"""
Scrapers for utility company address lookup tools.
Uses Playwright for JavaScript-rendered pages.
Provides authoritative verification when utility company confirms service.
"""

import asyncio
import hashlib
import json
import os
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import logging

logger = logging.getLogger(__name__)

# Cache settings
SCRAPER_CACHE_FILE = os.path.join(os.path.dirname(__file__), 'data', 'scraper_cache.json')
CACHE_TTL_DAYS = 30

# Rate limiting
_last_request: Dict[str, float] = defaultdict(float)
MIN_REQUEST_INTERVAL = 5.0  # seconds between requests to same domain

# Try to import Playwright
try:
    from playwright.async_api import async_playwright, Browser, Page
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("Playwright not installed. Utility scrapers will be disabled.")


def get_cache_key(address: str, utility_type: str) -> str:
    """Generate cache key for address lookup."""
    return hashlib.md5(f"{address}|{utility_type}".encode()).hexdigest()


def get_cached_result(address: str, utility_type: str) -> Optional[Dict]:
    """Get cached scraper result if available and not expired."""
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
    """Cache scraper result."""
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
    
    os.makedirs(os.path.dirname(SCRAPER_CACHE_FILE), exist_ok=True)
    with open(SCRAPER_CACHE_FILE, 'w') as f:
        json.dump(cache, f, indent=2)


class UtilityScraper(ABC):
    """Base class for utility company scrapers."""
    
    name: str = "Unknown"
    utility_type: str = "electric"  # or "gas"
    states_served: List[str] = []
    base_url: str = ""
    
    def __init__(self):
        self.browser: Optional['Browser'] = None
        self.playwright = None
    
    async def init_browser(self):
        """Initialize Playwright browser."""
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright not installed")
        
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=True)
    
    async def close(self):
        """Close browser."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
    
    @abstractmethod
    async def check_address(self, address: str) -> Dict:
        """
        Check if utility serves this address.
        
        Returns:
            {
                'serves': bool or None,
                'confidence': 'verified' | 'inconclusive',
                'provider_name': str or None,
                'source': str,
                'details': dict (optional extra info)
            }
        """
        pass
    
    async def safe_check(self, address: str) -> Optional[Dict]:
        """Wrapper with error handling and rate limiting."""
        if not PLAYWRIGHT_AVAILABLE:
            return None
        
        # Check cache first
        cached = get_cached_result(address, f"{self.name}_{self.utility_type}")
        if cached:
            logger.info(f"Using cached result for {self.name}")
            return cached
        
        # Rate limiting
        domain = self.name.lower()
        elapsed = time.time() - _last_request[domain]
        if elapsed < MIN_REQUEST_INTERVAL:
            await asyncio.sleep(MIN_REQUEST_INTERVAL - elapsed)
        
        try:
            await self.init_browser()
            result = await self.check_address(address)
            _last_request[domain] = time.time()
            
            # Cache result
            if result and result.get('serves') is not None:
                cache_result(address, f"{self.name}_{self.utility_type}", result)
            
            return result
        except Exception as e:
            logger.error(f"{self.name} scraper error: {e}")
            return None
        finally:
            await self.close()


class OncorScraper(UtilityScraper):
    """Scraper for Oncor Electric (Texas TDU)."""
    
    name = "Oncor"
    utility_type = "electric"
    states_served = ["TX"]
    base_url = "https://www.oncor.com"
    
    async def check_address(self, address: str) -> Dict:
        page = await self.browser.new_page()
        
        try:
            # Navigate to Oncor's service area lookup
            await page.goto(f'{self.base_url}/content/oncorwww/us/en/home/smart-energy/am-i-in-oncor-territory.html', 
                          timeout=30000)
            
            # Wait for the address input field
            await page.wait_for_selector('input[type="text"]', timeout=10000)
            
            # Enter address
            await page.fill('input[type="text"]', address)
            
            # Submit form (look for submit button)
            submit_btn = await page.query_selector('button[type="submit"], input[type="submit"], .submit-btn')
            if submit_btn:
                await submit_btn.click()
            else:
                await page.keyboard.press('Enter')
            
            # Wait for result
            await page.wait_for_timeout(3000)
            
            # Check for result indicators
            content = await page.content()
            content_lower = content.lower()
            
            if 'is in oncor' in content_lower or 'you are in oncor' in content_lower or 'oncor territory' in content_lower:
                return {
                    'serves': True,
                    'confidence': 'verified',
                    'provider_name': 'Oncor Electric Delivery',
                    'source': 'Oncor website lookup',
                    'utility_type': 'electric_tdu'
                }
            elif 'not in oncor' in content_lower or 'outside' in content_lower or 'not served' in content_lower:
                return {
                    'serves': False,
                    'confidence': 'verified',
                    'provider_name': None,
                    'source': 'Oncor website lookup'
                }
            else:
                return {
                    'serves': None,
                    'confidence': 'inconclusive',
                    'provider_name': None,
                    'source': 'Oncor website lookup'
                }
        
        finally:
            await page.close()


class CenterPointScraper(UtilityScraper):
    """Scraper for CenterPoint Energy (Texas, Minnesota, etc.)."""
    
    name = "CenterPoint"
    utility_type = "gas"  # Primary use is gas verification
    states_served = ["TX", "MN", "IN", "OH", "LA", "MS"]
    base_url = "https://www.centerpointenergy.com"
    
    async def check_address(self, address: str) -> Dict:
        page = await self.browser.new_page()
        
        try:
            # CenterPoint has different sites per region
            await page.goto(f'{self.base_url}/en-us/residential', timeout=30000)
            
            # Look for service area verification
            # Note: Implementation depends on their actual UI which may require login
            
            return {
                'serves': None,
                'confidence': 'inconclusive',
                'provider_name': None,
                'source': 'CenterPoint website'
            }
        
        finally:
            await page.close()


class TexasGasServiceScraper(UtilityScraper):
    """Scraper for Texas Gas Service."""
    
    name = "Texas Gas Service"
    utility_type = "gas"
    states_served = ["TX"]
    base_url = "https://www.texasgasservice.com"
    
    async def check_address(self, address: str) -> Dict:
        page = await self.browser.new_page()
        
        try:
            await page.goto(self.base_url, timeout=30000)
            
            # Texas Gas Service may have a service area lookup
            # Implementation depends on their actual UI
            
            return {
                'serves': None,
                'confidence': 'inconclusive',
                'provider_name': None,
                'source': 'Texas Gas Service website'
            }
        
        finally:
            await page.close()


class AtmosEnergyScraper(UtilityScraper):
    """Scraper for Atmos Energy (gas utility, multiple states)."""
    
    name = "Atmos Energy"
    utility_type = "gas"
    states_served = ["TX", "CO", "KY", "LA", "MS", "TN", "VA", "KS"]
    base_url = "https://www.atmosenergy.com"
    
    async def check_address(self, address: str) -> Dict:
        page = await self.browser.new_page()
        
        try:
            await page.goto(self.base_url, timeout=30000)
            
            # Atmos may have a service area lookup
            # Implementation depends on their actual UI
            
            return {
                'serves': None,
                'confidence': 'inconclusive',
                'provider_name': None,
                'source': 'Atmos Energy website'
            }
        
        finally:
            await page.close()


class DukeEnergyScraper(UtilityScraper):
    """Scraper for Duke Energy (Carolinas, Florida, Midwest)."""
    
    name = "Duke Energy"
    utility_type = "electric"
    states_served = ["NC", "SC", "FL", "IN", "OH", "KY"]
    base_url = "https://www.duke-energy.com"
    
    async def check_address(self, address: str) -> Dict:
        page = await self.browser.new_page()
        
        try:
            await page.goto(f'{self.base_url}/home/service-area', timeout=30000)
            
            # Implementation based on Duke's actual UI
            
            return {
                'serves': None,
                'confidence': 'inconclusive',
                'provider_name': None,
                'source': 'Duke Energy website'
            }
        
        finally:
            await page.close()


class FPLScraper(UtilityScraper):
    """Scraper for Florida Power & Light."""
    
    name = "FPL"
    utility_type = "electric"
    states_served = ["FL"]
    base_url = "https://www.fpl.com"
    
    async def check_address(self, address: str) -> Dict:
        page = await self.browser.new_page()
        
        try:
            await page.goto(self.base_url, timeout=30000)
            
            return {
                'serves': None,
                'confidence': 'inconclusive',
                'provider_name': None,
                'source': 'FPL website'
            }
        
        finally:
            await page.close()


class PGEScraper(UtilityScraper):
    """Scraper for PG&E (California)."""
    
    name = "PG&E"
    utility_type = "electric"
    states_served = ["CA"]
    base_url = "https://www.pge.com"
    
    async def check_address(self, address: str) -> Dict:
        page = await self.browser.new_page()
        
        try:
            await page.goto(self.base_url, timeout=30000)
            
            # PG&E requires login for detailed lookup
            
            return {
                'serves': None,
                'confidence': 'inconclusive',
                'provider_name': None,
                'source': 'PG&E website'
            }
        
        finally:
            await page.close()


# Registry of available scrapers
SCRAPERS = {
    'oncor': OncorScraper,
    'centerpoint': CenterPointScraper,
    'texas_gas_service': TexasGasServiceScraper,
    'atmos': AtmosEnergyScraper,
    'duke_energy': DukeEnergyScraper,
    'fpl': FPLScraper,
    'pge': PGEScraper,
}


def get_scrapers_for_state(state: str, utility_type: str = None) -> List[type]:
    """Get list of scraper classes that serve a given state."""
    matching = []
    for name, scraper_class in SCRAPERS.items():
        if state in scraper_class.states_served:
            if utility_type is None or scraper_class.utility_type == utility_type:
                matching.append(scraper_class)
    return matching


def get_available_scrapers() -> Dict[str, Dict]:
    """Get info about all available scrapers."""
    return {
        name: {
            'name': cls.name,
            'utility_type': cls.utility_type,
            'states_served': cls.states_served
        }
        for name, cls in SCRAPERS.items()
    }


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
    if not PLAYWRIGHT_AVAILABLE:
        return None
    
    scrapers = get_scrapers_for_state(state, utility_type)
    
    if not scrapers:
        return None
    
    # If we have an expected provider, try that scraper first
    if expected_provider:
        provider_lower = expected_provider.lower()
        for scraper_class in scrapers:
            scraper_name_lower = scraper_class.name.lower()
            if scraper_name_lower in provider_lower or provider_lower in scraper_name_lower:
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


def verify_with_utility_api_sync(
    address: str,
    state: str,
    expected_provider: str = None,
    utility_type: str = 'electric'
) -> Optional[Dict]:
    """Synchronous wrapper for verify_with_utility_api."""
    if not PLAYWRIGHT_AVAILABLE:
        return None
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(
        verify_with_utility_api(address, state, expected_provider, utility_type)
    )
