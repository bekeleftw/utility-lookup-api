"""
Logo retrieval service for PM company branding.
Uses BrightData Web Unlocker for homepage scraping and SERP API for fallback.
"""

import os
import re
import requests
from urllib.parse import urljoin, urlparse
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)

# BrightData credentials
BRIGHTDATA_HOST = "brd.superproxy.io"
BRIGHTDATA_PORT = 33335

# Web Unlocker (primary for homepage scraping)
WEB_UNLOCKER_USER = "brd-customer-hl_6cc76bc7-zone-unblocker1"
WEB_UNLOCKER_PASS = os.getenv("BRIGHTDATA_UNBLOCKER_PASS", "hp8kqmzw2666")

# SERP API (for Google Images fallback)
SERP_API_USER = "brd-customer-hl_6cc76bc7-zone-serp_api1"
SERP_API_PASS = os.getenv("BRIGHTDATA_SERP_PASS", "tsvzh3vjpprl")

# Browser API (backup if web unlocker gets blocked)
BROWSER_API_USER = "brd-customer-hl_6cc76bc7-zone-pm_homepage_scraper"
BROWSER_API_PASS = os.getenv("BRIGHTDATA_BROWSER_PASS", "lz9gg157wl2v")

# Image dimension constraints
MIN_WIDTH = 100
MIN_HEIGHT = 30
MAX_WIDTH = 1000
MAX_HEIGHT = 500
FAVICON_MIN_SIZE = 64


def fetch_with_brightdata(url: str, use_browser_api: bool = False) -> Optional[str]:
    """
    Fetch a URL using BrightData proxy.
    
    Args:
        url: URL to fetch
        use_browser_api: If True, use Browser API instead of Web Unlocker
    
    Returns:
        HTML content or None if failed
    """
    if use_browser_api:
        # Browser API uses Playwright/Puppeteer remotely
        # For now, fall back to web unlocker - Browser API needs async handling
        pass
    
    proxy_url = f"http://{WEB_UNLOCKER_USER}:{WEB_UNLOCKER_PASS}@{BRIGHTDATA_HOST}:{BRIGHTDATA_PORT}"
    
    try:
        response = requests.get(
            url,
            proxies={"http": proxy_url, "https": proxy_url},
            timeout=30,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            },
            verify=False  # BrightData handles SSL
        )
        response.raise_for_status()
        return response.text
    except Exception as e:
        logger.warning(f"Failed to fetch {url} with BrightData: {e}")
        return None


def check_image_accessible(url: str) -> bool:
    """Check if an image URL is accessible via HEAD request."""
    try:
        response = requests.head(url, timeout=10, allow_redirects=True)
        return response.status_code == 200
    except:
        return False


def get_image_dimensions(url: str) -> Optional[Tuple[int, int]]:
    """
    Get image dimensions without downloading the full image.
    Returns (width, height) or None if can't determine.
    """
    try:
        # Try to get just the header bytes to determine dimensions
        response = requests.get(url, timeout=10, stream=True, headers={
            "Range": "bytes=0-1024"
        })
        
        # For a full implementation, we'd parse image headers
        # For now, return None and skip dimension check
        return None
    except:
        return None


def extract_logo_from_html(html: str, base_url: str) -> Optional[str]:
    """
    Extract logo URL from HTML content using priority order:
    1. <img> inside <header>
    2. <img> inside element with class containing "logo"
    3. <img> with src/alt containing "logo"
    4. OpenGraph image
    5. Apple touch icon
    6. Favicon (if 64x64 or larger)
    
    Args:
        html: HTML content
        base_url: Base URL for resolving relative paths
    
    Returns:
        Absolute URL to logo image, or None
    """
    from bs4 import BeautifulSoup
    
    soup = BeautifulSoup(html, 'html.parser')
    candidates = []
    
    # 1. <img> inside <header>
    header = soup.find('header')
    if header:
        img = header.find('img')
        if img and img.get('src'):
            candidates.append(('header', img['src']))
    
    # 2. <img> inside element with class containing "logo"
    logo_containers = soup.find_all(class_=lambda c: c and 'logo' in c.lower() if isinstance(c, str) else any('logo' in cls.lower() for cls in c) if c else False)
    for container in logo_containers:
        img = container.find('img') if container.name != 'img' else container
        if img and img.get('src'):
            candidates.append(('logo_class', img['src']))
            break
    
    # 3. <img> with src or alt containing "logo"
    for img in soup.find_all('img'):
        src = img.get('src', '')
        alt = img.get('alt', '')
        if 'logo' in src.lower() or 'logo' in alt.lower():
            candidates.append(('logo_attr', src))
            break
    
    # 4. OpenGraph image
    og_image = soup.find('meta', property='og:image')
    if og_image and og_image.get('content'):
        candidates.append(('og_image', og_image['content']))
    
    # 5. Apple touch icon
    apple_icon = soup.find('link', rel=lambda r: r and 'apple-touch-icon' in r if isinstance(r, str) else 'apple-touch-icon' in ' '.join(r) if r else False)
    if apple_icon and apple_icon.get('href'):
        candidates.append(('apple_icon', apple_icon['href']))
    
    # 6. Favicon (only if likely large enough)
    favicon = soup.find('link', rel=lambda r: r and 'icon' in str(r).lower())
    if favicon and favicon.get('href'):
        href = favicon['href']
        # Check for size hints
        sizes = favicon.get('sizes', '')
        if sizes:
            try:
                w, h = sizes.split('x')
                if int(w) >= FAVICON_MIN_SIZE and int(h) >= FAVICON_MIN_SIZE:
                    candidates.append(('favicon', href))
            except:
                pass
        elif '.svg' in href or '.png' in href:
            # SVG or PNG favicons are often higher quality
            candidates.append(('favicon', href))
    
    # Process candidates in priority order
    for source, url in candidates:
        # Resolve relative URLs
        absolute_url = urljoin(base_url, url)
        
        # Verify accessible
        if check_image_accessible(absolute_url):
            logger.info(f"Found logo via {source}: {absolute_url}")
            return absolute_url
    
    return None


def search_logo_serp(company_name: str) -> Optional[str]:
    """
    Search for company logo using BrightData SERP API.
    
    Args:
        company_name: Company name to search for
    
    Returns:
        URL to logo image, or None
    """
    search_query = f"{company_name} logo"
    search_url = f"https://www.google.com/search?q={requests.utils.quote(search_query)}&tbm=isch"
    
    proxy_url = f"http://{SERP_API_USER}:{SERP_API_PASS}@{BRIGHTDATA_HOST}:{BRIGHTDATA_PORT}"
    
    try:
        response = requests.get(
            search_url,
            proxies={"http": proxy_url, "https": proxy_url},
            timeout=30,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            },
            verify=False
        )
        response.raise_for_status()
        
        # Parse image results
        # Google Images embeds image URLs in the page
        # Look for image URLs in the response
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find image URLs - Google encodes them in data attributes or scripts
        # This is a simplified extraction - real implementation would parse more thoroughly
        img_tags = soup.find_all('img')
        
        for img in img_tags:
            src = img.get('src') or img.get('data-src')
            if not src:
                continue
            
            # Skip Google's own assets
            if 'google.com' in src or 'gstatic.com' in src:
                continue
            
            # Skip base64 thumbnails
            if src.startswith('data:'):
                continue
            
            # Check if it looks like a logo (reasonable dimensions, not stock site)
            stock_sites = ['shutterstock', 'istockphoto', 'gettyimages', 'depositphotos']
            if any(site in src.lower() for site in stock_sites):
                continue
            
            if check_image_accessible(src):
                logger.info(f"Found logo via SERP: {src}")
                return src
        
        return None
        
    except Exception as e:
        logger.warning(f"SERP logo search failed for {company_name}: {e}")
        return None


def retrieve_logo(website_url: Optional[str], company_name: str) -> Optional[str]:
    """
    Main entry point for logo retrieval.
    
    Args:
        website_url: PM's website URL (optional)
        company_name: PM's company name
    
    Returns:
        URL to logo image, or None if not found
    """
    logo_url = None
    
    # Step 1: Try homepage scrape if website provided
    if website_url:
        # Normalize URL
        if not website_url.startswith(('http://', 'https://')):
            website_url = 'https://' + website_url
        
        logger.info(f"Attempting homepage scrape for {website_url}")
        html = fetch_with_brightdata(website_url)
        
        if html:
            logo_url = extract_logo_from_html(html, website_url)
    
    # Step 2: SERP fallback if homepage scrape failed
    if not logo_url:
        logger.info(f"Homepage scrape failed, trying SERP for {company_name}")
        logo_url = search_logo_serp(company_name)
    
    return logo_url


# Storage functions (to be implemented with R2/S3)
def download_and_store_logo(logo_url: str, guide_request_id: str) -> Optional[str]:
    """
    Download logo and store in cloud storage.
    
    Args:
        logo_url: URL of the logo to download
        guide_request_id: ID of the guide request (for naming)
    
    Returns:
        Stored URL, or None if failed
    """
    # TODO: Implement R2/S3 storage
    # For now, return the original URL
    # In production:
    # 1. Download the image
    # 2. Upload to R2/S3 with key like logos/{guide_request_id}.{ext}
    # 3. Return the stored URL
    
    logger.info(f"Logo storage not yet implemented, using original URL: {logo_url}")
    return logo_url
