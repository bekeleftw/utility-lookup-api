#!/usr/bin/env python3
"""
Browser-based utility verification.

Uses Playwright + LLM to navigate utility websites and verify
that they serve a specific address.

Two approaches:
1. Curated URLs: For major utilities, we have direct links to service check pages
2. LLM-guided: For unknown utilities, LLM navigates the site

This adds latency but provides ground-truth verification.
"""

import asyncio
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from enum import Enum

from playwright.async_api import async_playwright, Page, Browser, TimeoutError as PlaywrightTimeout
import requests
from urllib.parse import quote

# BrightData proxy for SERP
BRIGHTDATA_PROXY_HOST = "brd.superproxy.io"
BRIGHTDATA_PROXY_PORT = "33335"
BRIGHTDATA_PROXY_USER = "brd-customer-hl_6cc76bc7-zone-address_search"
BRIGHTDATA_PROXY_PASS = "n59dskgnctqr"

# Load curated service check URLs
SERVICE_CHECK_URLS_FILE = Path(__file__).parent / "data" / "utility_service_check_urls.json"
_service_check_cache = None

def load_service_check_urls() -> Dict:
    """Load curated utility service check URLs."""
    global _service_check_cache
    if _service_check_cache is None:
        if SERVICE_CHECK_URLS_FILE.exists():
            with open(SERVICE_CHECK_URLS_FILE, 'r') as f:
                _service_check_cache = json.load(f)
        else:
            _service_check_cache = {"utilities": {}}
    return _service_check_cache

def get_service_check_url(utility_name: str) -> Optional[Dict]:
    """Get curated service check info for a utility."""
    data = load_service_check_urls()
    utilities = data.get("utilities", {})
    
    # Exact match
    if utility_name in utilities:
        return utilities[utility_name]
    
    # Fuzzy match - check if utility name contains key
    utility_lower = utility_name.lower()
    for name, info in utilities.items():
        if name.lower() in utility_lower or utility_lower in name.lower():
            return info
    
    return None


def verify_url_accessible(url: str, timeout: int = 5) -> bool:
    """Check if a URL returns a successful response (not 404, 500, etc)."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }
        response = requests.head(url, headers=headers, timeout=timeout, allow_redirects=True)
        # Accept 200-399 as valid (includes redirects that resolved)
        return 200 <= response.status_code < 400
    except Exception:
        # If HEAD fails, try GET (some servers don't support HEAD)
        try:
            response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
            return 200 <= response.status_code < 400
        except Exception:
            return False


def find_service_check_url_via_serp(utility_name: str, city: str, state: str) -> Optional[str]:
    """
    Use Google SERP to find a utility's service area check page.
    
    Uses site: operator to search directly on the utility's domain.
    Verifies URLs are accessible before returning.
    """
    # Get likely domain for the utility
    domain = _get_utility_domain(utility_name)
    
    # If domain is just a guess (ends with utility name + .com), be more careful
    # Only proceed if we have a known domain mapping
    name_clean = utility_name.lower().replace(' ', '').replace('&', '').replace("'", '').replace('-', '')
    if domain == f"{name_clean}.com":
        # This is a guessed domain - check if it's likely valid
        # Skip SERP for completely unknown utilities
        return None
    
    queries = [
        f'{utility_name} start service check address site:{domain}',
        f'{utility_name} service area address verification',
    ]
    
    proxy_url = f"http://{BRIGHTDATA_PROXY_USER}:{BRIGHTDATA_PROXY_PASS}@{BRIGHTDATA_PROXY_HOST}:{BRIGHTDATA_PROXY_PORT}"
    proxies = {"http": proxy_url, "https": proxy_url}
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }
    
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    for query in queries:
        try:
            search_url = f"https://www.google.com/search?q={quote(query)}"
            
            response = requests.get(
                search_url,
                proxies=proxies,
                headers=headers,
                timeout=15,
                verify=False
            )
            
            if response.status_code != 200:
                continue
            
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for external links (not Google internal)
            for tag in soup.find_all(href=True):
                href = tag.get('href', '')
                
                # Skip Google internal links
                if not href.startswith('http') or 'google' in href.lower():
                    continue
                
                url_lower = href.lower()
                
                # Check if URL looks like a service check page
                service_keywords = ['start', 'stop', 'move', 'service', 'address', 'check', 'area', 'apply']
                if any(kw in url_lower for kw in service_keywords):
                    # Skip social media and unrelated sites
                    skip_domains = ['youtube.', 'facebook.', 'twitter.', 'linkedin.', 'wikipedia.', 
                                    'yelp.', 'smarty.', 'indeed.', 'glassdoor.', 'reddit.', 'quora.']
                    if not any(skip in url_lower for skip in skip_domains):
                        # Verify the URL is likely from the utility (contains part of utility name)
                        utility_words = utility_name.lower().split()
                        # Check if at least one significant word from utility name is in URL
                        significant_words = [w for w in utility_words if len(w) > 3 and w not in ['energy', 'power', 'electric', 'gas', 'utility', 'utilities', 'board', 'the']]
                        if significant_words:
                            if not any(word in url_lower for word in significant_words):
                                continue  # URL doesn't seem related to this utility
                        
                        # Clean up URL (remove tracking params)
                        clean_url = href.split('&')[0] if '&ved=' in href else href
                        
                        # Verify URL is accessible (not 404)
                        if verify_url_accessible(clean_url):
                            return clean_url
                        # If not accessible, continue looking for other URLs
            
        except Exception as e:
            print(f"SERP query failed: {e}")
            continue
    
    return None


def _get_utility_domain(utility_name: str) -> str:
    """Guess the utility's domain from their name."""
    # Known domain mappings for tricky utilities
    known_domains = {
        'austin energy': 'austinenergy.com',
        'cps energy': 'cpsenergy.com',
        'duke energy': 'duke-energy.com',
        'georgia power': 'georgiapower.com',
        'florida power & light': 'fpl.com',
        'fpl': 'fpl.com',
        'pacific gas & electric': 'pge.com',
        'pg&e': 'pge.com',
        'southern california edison': 'sce.com',
        'con edison': 'coned.com',
        'knoxville utilities board': 'kub.org',
        'kub': 'kub.org',
        'ladwp': 'ladwp.com',
        'xcel energy': 'xcelenergy.com',
        'dominion energy': 'dominionenergy.com',
        'entergy': 'entergy.com',
        'ameren': 'ameren.com',
        'centerpoint': 'centerpointenergy.com',
        'nv energy': 'nvenergy.com',
        'puget sound energy': 'pse.com',
        'seattle city light': 'seattle.gov',
        'baltimore gas & electric': 'bge.com',
        'bge': 'bge.com',
        'pepco': 'pepco.com',
        'peco': 'peco.com',
        'pseg': 'pseg.com',
        'national grid': 'nationalgridus.com',
        'eversource': 'eversource.com',
    }
    
    name_lower = utility_name.lower()
    
    # Check known mappings first
    if name_lower in known_domains:
        return known_domains[name_lower]
    
    # Check partial matches
    for key, domain in known_domains.items():
        if key in name_lower or name_lower in key:
            return domain
    
    # Fall back to guessing - keep "energy" in the domain
    clean_name = name_lower.replace(' ', '').replace('&', '').replace("'", '').replace('-', '')
    
    return f"{clean_name}.com"


class VerificationResult(Enum):
    VERIFIED = "verified"          # Utility confirmed they serve this address
    NOT_SERVED = "not_served"      # Utility confirmed they DON'T serve this address
    UNKNOWN = "unknown"            # Could not determine (form not found, error, etc.)
    TIMEOUT = "timeout"            # Page load or interaction timed out
    NO_WEBSITE = "no_website"      # No website available for this utility
    SERVICE_CHECK_FOUND = "service_check_found"  # Found service check URL but didn't automate


@dataclass
class BrowserVerificationResult:
    result: VerificationResult
    utility_name: str
    address: str
    message: Optional[str] = None
    screenshot_path: Optional[str] = None
    page_text: Optional[str] = None
    service_check_url: Optional[str] = None  # URL where user can verify themselves
    confidence: float = 0.0


# Common patterns for service area check pages
SERVICE_CHECK_PATTERNS = [
    r"check.*service",
    r"service.*area",
    r"do we serve",
    r"start.*service",
    r"new.*service",
    r"check.*address",
    r"verify.*address",
    r"enter.*address",
    r"service.*address",
    r"coverage.*area",
]

# Patterns indicating the address IS served
SERVED_PATTERNS = [
    r"we serve this address",
    r"service is available",
    r"you('re| are) in our service area",
    r"we can serve you",
    r"start service",
    r"sign up",
    r"create account",
    r"service available at this location",
    r"good news",
    r"congratulations",
]

# Patterns indicating the address is NOT served
NOT_SERVED_PATTERNS = [
    r"not in our service area",
    r"we do not serve",
    r"outside our service area",
    r"not available at this address",
    r"sorry.*not serve",
    r"unfortunately.*not",
    r"different provider",
    r"contact.*instead",
]


async def find_service_check_link(page: Page) -> Optional[str]:
    """Find a link to service area check or start service page."""
    links = await page.query_selector_all("a")
    
    for link in links:
        try:
            text = await link.inner_text()
            href = await link.get_attribute("href")
            
            if not text or not href:
                continue
                
            text_lower = text.lower()
            
            for pattern in SERVICE_CHECK_PATTERNS:
                if re.search(pattern, text_lower):
                    return href
        except:
            continue
    
    return None


async def find_address_input(page: Page) -> Optional[any]:
    """Find an address input field on the page."""
    # Common selectors for address inputs
    selectors = [
        'input[name*="address" i]',
        'input[placeholder*="address" i]',
        'input[id*="address" i]',
        'input[aria-label*="address" i]',
        'input[name*="street" i]',
        'input[placeholder*="street" i]',
        'input[type="text"][name*="location" i]',
        'input[placeholder*="enter your address" i]',
        'input[placeholder*="service address" i]',
    ]
    
    for selector in selectors:
        try:
            element = await page.query_selector(selector)
            if element and await element.is_visible():
                return element
        except:
            continue
    
    return None


async def find_submit_button(page: Page) -> Optional[any]:
    """Find a submit button near an address form."""
    selectors = [
        'button[type="submit"]',
        'input[type="submit"]',
        'button:has-text("Check")',
        'button:has-text("Search")',
        'button:has-text("Submit")',
        'button:has-text("Verify")',
        'button:has-text("Find")',
        'button:has-text("Continue")',
        'button:has-text("Start")',
    ]
    
    for selector in selectors:
        try:
            element = await page.query_selector(selector)
            if element and await element.is_visible():
                return element
        except:
            continue
    
    return None


async def check_page_for_result(page: Page) -> Tuple[VerificationResult, str]:
    """Check the current page content for service verification result."""
    try:
        # Wait for page to settle
        await asyncio.sleep(2)
        
        # Get page text
        body = await page.query_selector("body")
        if not body:
            return VerificationResult.UNKNOWN, "Could not read page"
        
        text = await body.inner_text()
        text_lower = text.lower()
        
        # Check for "served" patterns
        for pattern in SERVED_PATTERNS:
            if re.search(pattern, text_lower):
                return VerificationResult.VERIFIED, f"Found: {pattern}"
        
        # Check for "not served" patterns
        for pattern in NOT_SERVED_PATTERNS:
            if re.search(pattern, text_lower):
                return VerificationResult.NOT_SERVED, f"Found: {pattern}"
        
        return VerificationResult.UNKNOWN, "No clear indication found"
        
    except Exception as e:
        return VerificationResult.UNKNOWN, str(e)


async def verify_utility_serves_address(
    utility_name: str,
    utility_website: str,
    address: str,
    timeout_seconds: int = 30,
    headless: bool = True,
    save_screenshot: bool = False
) -> BrowserVerificationResult:
    """
    Verify that a utility serves a specific address by visiting their website.
    
    Args:
        utility_name: Name of the utility
        utility_website: URL of the utility's website
        address: Full address to verify
        timeout_seconds: Max time to wait for page loads
        headless: Run browser in headless mode
        save_screenshot: Save screenshot of result page
        
    Returns:
        BrowserVerificationResult with verification status
    """
    if not utility_website:
        return BrowserVerificationResult(
            result=VerificationResult.NO_WEBSITE,
            utility_name=utility_name,
            address=address,
            message="No website available"
        )
    
    # Normalize URL
    if not utility_website.startswith("http"):
        utility_website = "https://" + utility_website
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = await context.new_page()
        
        try:
            # Step 1: Navigate to utility website
            await page.goto(utility_website, timeout=timeout_seconds * 1000)
            await asyncio.sleep(2)  # Let page settle
            
            # Step 2: Look for service check link
            service_link = await find_service_check_link(page)
            if service_link:
                if not service_link.startswith("http"):
                    service_link = utility_website.rstrip("/") + "/" + service_link.lstrip("/")
                await page.goto(service_link, timeout=timeout_seconds * 1000)
                await asyncio.sleep(2)
            
            # Step 3: Find address input
            address_input = await find_address_input(page)
            if not address_input:
                # Try scrolling down to find it
                await page.evaluate("window.scrollBy(0, 500)")
                await asyncio.sleep(1)
                address_input = await find_address_input(page)
            
            if not address_input:
                return BrowserVerificationResult(
                    result=VerificationResult.UNKNOWN,
                    utility_name=utility_name,
                    address=address,
                    message="Could not find address input field"
                )
            
            # Step 4: Enter address
            await address_input.fill(address)
            await asyncio.sleep(1)
            
            # Step 5: Find and click submit
            submit_btn = await find_submit_button(page)
            if submit_btn:
                await submit_btn.click()
                await asyncio.sleep(3)  # Wait for result
            else:
                # Try pressing Enter
                await address_input.press("Enter")
                await asyncio.sleep(3)
            
            # Step 6: Check result
            result, message = await check_page_for_result(page)
            
            # Optional: save screenshot
            screenshot_path = None
            if save_screenshot:
                screenshot_path = f"/tmp/utility_verify_{utility_name.replace(' ', '_')}.png"
                await page.screenshot(path=screenshot_path)
            
            # Get page text for debugging
            body = await page.query_selector("body")
            page_text = await body.inner_text() if body else None
            
            return BrowserVerificationResult(
                result=result,
                utility_name=utility_name,
                address=address,
                message=message,
                screenshot_path=screenshot_path,
                page_text=page_text[:1000] if page_text else None,
                confidence=0.9 if result == VerificationResult.VERIFIED else 0.7
            )
            
        except PlaywrightTimeout:
            return BrowserVerificationResult(
                result=VerificationResult.TIMEOUT,
                utility_name=utility_name,
                address=address,
                message="Page load timed out"
            )
        except Exception as e:
            return BrowserVerificationResult(
                result=VerificationResult.UNKNOWN,
                utility_name=utility_name,
                address=address,
                message=str(e)
            )
        finally:
            await browser.close()


async def get_page_summary_for_llm(page: Page) -> str:
    """Extract a summary of the page for LLM analysis."""
    try:
        # Get page title
        title = await page.title()
        
        # Get all visible text (truncated)
        body = await page.query_selector("body")
        text = await body.inner_text() if body else ""
        text = text[:3000]  # Limit for token efficiency
        
        # Get all links
        links = await page.query_selector_all("a")
        link_texts = []
        for i, link in enumerate(links[:20]):  # First 20 links
            try:
                link_text = await link.inner_text()
                href = await link.get_attribute("href")
                if link_text and len(link_text.strip()) > 2:
                    link_texts.append(f"[{i}] {link_text.strip()[:50]} -> {href}")
            except:
                continue
        
        # Get all input fields
        inputs = await page.query_selector_all("input, textarea")
        input_info = []
        for i, inp in enumerate(inputs[:10]):
            try:
                name = await inp.get_attribute("name") or ""
                placeholder = await inp.get_attribute("placeholder") or ""
                inp_type = await inp.get_attribute("type") or "text"
                if name or placeholder:
                    input_info.append(f"[input-{i}] type={inp_type} name={name} placeholder={placeholder}")
            except:
                continue
        
        # Get buttons
        buttons = await page.query_selector_all("button, input[type='submit']")
        button_info = []
        for i, btn in enumerate(buttons[:10]):
            try:
                btn_text = await btn.inner_text()
                if btn_text and len(btn_text.strip()) > 0:
                    button_info.append(f"[btn-{i}] {btn_text.strip()[:30]}")
            except:
                continue
        
        return f"""
PAGE TITLE: {title}

LINKS:
{chr(10).join(link_texts)}

INPUT FIELDS:
{chr(10).join(input_info)}

BUTTONS:
{chr(10).join(button_info)}

PAGE TEXT (truncated):
{text[:1500]}
"""
    except Exception as e:
        return f"Error extracting page: {e}"


async def ask_llm_for_action(page_summary: str, utility_name: str, address: str, goal: str) -> Dict:
    """Ask OpenAI what action to take on the page."""
    import openai
    
    client = openai.OpenAI()
    
    prompt = f"""You are helping verify if a utility company serves a specific address.

UTILITY: {utility_name}
ADDRESS TO VERIFY: {address}
GOAL: {goal}

CURRENT PAGE STATE:
{page_summary}

Based on the page state, what should we do next? Respond with JSON:
{{
    "action": "click_link" | "fill_input" | "click_button" | "done_served" | "done_not_served" | "done_unknown",
    "target": "<index number or input name>",
    "value": "<text to type if fill_input>",
    "reasoning": "<brief explanation>"
}}

If you see evidence the address IS served (signup forms, service available messages), return "done_served".
If you see evidence the address is NOT served (not in service area, different provider), return "done_not_served".
If you can't determine, try to find a service area check or address lookup form.
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=200
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        return {"action": "done_unknown", "reasoning": str(e)}


async def verify_with_llm(
    utility_name: str,
    utility_website: str,
    address: str,
    openai_api_key: Optional[str] = None,
    max_steps: int = 8,
    headless: bool = True
) -> BrowserVerificationResult:
    """
    Use LLM-guided browser automation for utility website verification.
    
    The LLM analyzes each page and decides what action to take next.
    """
    if not utility_website:
        return BrowserVerificationResult(
            result=VerificationResult.NO_WEBSITE,
            utility_name=utility_name,
            address=address,
            message="No website available"
        )
    
    if not utility_website.startswith("http"):
        utility_website = "https://" + utility_website
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = await context.new_page()
        
        try:
            # Navigate to utility website
            await page.goto(utility_website, timeout=30000)
            await asyncio.sleep(2)
            
            goal = "Find a way to check if this utility serves the address"
            
            for step in range(max_steps):
                # Get page state
                page_summary = await get_page_summary_for_llm(page)
                
                # Ask LLM what to do
                action = await ask_llm_for_action(page_summary, utility_name, address, goal)
                
                action_type = action.get("action", "done_unknown")
                target = action.get("target", "")
                value = action.get("value", "")
                
                if action_type == "done_served":
                    return BrowserVerificationResult(
                        result=VerificationResult.VERIFIED,
                        utility_name=utility_name,
                        address=address,
                        message=action.get("reasoning", "LLM determined address is served"),
                        confidence=0.85
                    )
                
                elif action_type == "done_not_served":
                    return BrowserVerificationResult(
                        result=VerificationResult.NOT_SERVED,
                        utility_name=utility_name,
                        address=address,
                        message=action.get("reasoning", "LLM determined address is not served"),
                        confidence=0.85
                    )
                
                elif action_type == "done_unknown":
                    return BrowserVerificationResult(
                        result=VerificationResult.UNKNOWN,
                        utility_name=utility_name,
                        address=address,
                        message=action.get("reasoning", "Could not determine service status"),
                        confidence=0.5
                    )
                
                elif action_type == "click_link":
                    try:
                        links = await page.query_selector_all("a")
                        idx = int(target)
                        if 0 <= idx < len(links):
                            await links[idx].click()
                            await asyncio.sleep(2)
                            goal = "Check if we can verify the address is served"
                    except:
                        pass
                
                elif action_type == "fill_input":
                    try:
                        # Try by index first
                        if target.startswith("input-"):
                            idx = int(target.replace("input-", ""))
                            inputs = await page.query_selector_all("input, textarea")
                            if 0 <= idx < len(inputs):
                                await inputs[idx].fill(value or address)
                        else:
                            # Try by name
                            inp = await page.query_selector(f'input[name="{target}"]')
                            if inp:
                                await inp.fill(value or address)
                        await asyncio.sleep(1)
                        goal = "Submit the form or look for results"
                    except:
                        pass
                
                elif action_type == "click_button":
                    try:
                        buttons = await page.query_selector_all("button, input[type='submit']")
                        idx = int(target.replace("btn-", "")) if "btn-" in str(target) else int(target)
                        if 0 <= idx < len(buttons):
                            await buttons[idx].click()
                            await asyncio.sleep(3)
                            goal = "Check the result to see if address is served"
                    except:
                        pass
            
            # Max steps reached
            return BrowserVerificationResult(
                result=VerificationResult.UNKNOWN,
                utility_name=utility_name,
                address=address,
                message="Max steps reached without determination",
                confidence=0.3
            )
            
        except PlaywrightTimeout:
            return BrowserVerificationResult(
                result=VerificationResult.TIMEOUT,
                utility_name=utility_name,
                address=address,
                message="Page load timed out"
            )
        except Exception as e:
            return BrowserVerificationResult(
                result=VerificationResult.UNKNOWN,
                utility_name=utility_name,
                address=address,
                message=str(e)
            )
        finally:
            await browser.close()


def find_service_check_url(
    utility_name: str,
    city: str = None,
    state: str = None,
    verify_accessible: bool = True
) -> Optional[str]:
    """
    Find a utility's service check URL using curated data or SERP.
    
    This is the main entry point - returns a URL where users can verify
    if the utility serves their address.
    
    Args:
        utility_name: Name of the utility
        city: City name (for SERP queries)
        state: State abbreviation (for SERP queries)
        verify_accessible: Whether to verify URLs return 200 (default True)
        
    Returns:
        URL to service check page, or None if not found
    """
    # Step 1: Check curated URLs first (fastest, most reliable)
    curated = get_service_check_url(utility_name)
    if curated and curated.get("service_check_url"):
        url = curated["service_check_url"]
        # Verify curated URL is still accessible
        if verify_accessible:
            if verify_url_accessible(url):
                return url
            # Curated URL is broken - fall through to SERP
        else:
            return url
    
    # Step 2: Use SERP to find service check page (already verifies URLs)
    if city and state:
        serp_url = find_service_check_url_via_serp(utility_name, city, state)
        if serp_url:
            return serp_url
    
    return None


async def verify_utility(
    utility_name: str,
    address: str,
    city: str = None,
    state: str = None,
    utility_website: Optional[str] = None,
    attempt_automation: bool = False,
    headless: bool = True
) -> BrowserVerificationResult:
    """
    Find service check URL and optionally attempt automated verification.
    
    By default, just finds the URL and returns it for user to verify.
    Set attempt_automation=True to try filling forms (less reliable).
    
    Args:
        utility_name: Name of the utility to verify
        address: Address to check
        city: City name (for SERP queries)
        state: State abbreviation (for SERP queries)
        utility_website: Optional website URL
        attempt_automation: Whether to try automated form filling
        headless: Run browser in headless mode
        
    Returns:
        BrowserVerificationResult with service_check_url
    """
    # Find service check URL
    service_url = find_service_check_url(utility_name, city, state)
    
    if service_url:
        # If not attempting automation, just return the URL
        if not attempt_automation:
            return BrowserVerificationResult(
                result=VerificationResult.SERVICE_CHECK_FOUND,
                utility_name=utility_name,
                address=address,
                message=f"Service check page found - user can verify at this URL",
                service_check_url=service_url,
                confidence=0.7
            )
        
        # Attempt automated verification
        result = await verify_utility_serves_address(
            utility_name=utility_name,
            utility_website=service_url,
            address=address,
            headless=headless
        )
        result.service_check_url = service_url
        
        if result.result != VerificationResult.UNKNOWN:
            return result
    
    # Fall back to LLM-guided if we have a website
    if attempt_automation and utility_website:
        return await verify_with_llm(
            utility_name=utility_name,
            utility_website=utility_website,
            address=address,
            headless=headless
        )
    
    # No verification possible
    return BrowserVerificationResult(
        result=VerificationResult.UNKNOWN,
        utility_name=utility_name,
        address=address,
        message="Could not find service check page"
    )


# Quick test
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    async def test():
        print("Testing Service Check URL Discovery")
        print("="*60)
        
        # Test the main find_service_check_url function
        test_cases = [
            ("Duke Energy", "Charlotte", "NC"),
            ("Knoxville Utilities Board", "Knoxville", "TN"),
            ("Austin Energy", "Austin", "TX"),
            ("Georgia Power", "Atlanta", "GA"),
            ("Some Random Utility", "Nowhere", "XX"),  # Should fail gracefully
        ]
        
        for utility, city, state in test_cases:
            print(f"\n{utility} ({city}, {state}):")
            url = find_service_check_url(utility, city, state)
            if url:
                print(f"   ✓ Found: {url}")
            else:
                print(f"   ✗ Not found")
        
        # Test the verify_utility function (without automation)
        print("\n" + "="*60)
        print("Testing verify_utility (returns URL for user to check)")
        result = await verify_utility(
            utility_name="Duke Energy",
            address="123 Main St, Charlotte, NC 28202",
            city="Charlotte",
            state="NC"
        )
        print(f"Result: {result.result.value}")
        print(f"Service Check URL: {result.service_check_url}")
        print(f"Message: {result.message}")
    
    asyncio.run(test())
