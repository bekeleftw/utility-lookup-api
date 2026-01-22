"""
AI-powered utility signup instruction extraction.
Scrapes utility websites and uses GPT to extract structured signup instructions.
"""

import os
import json
import re
import requests
from typing import Optional, Dict, List
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# BrightData credentials (shared with logo_retrieval)
BRIGHTDATA_HOST = "brd.superproxy.io"
BRIGHTDATA_PORT = 33335
WEB_UNLOCKER_USER = "brd-customer-hl_6cc76bc7-zone-unblocker1"
WEB_UNLOCKER_PASS = os.getenv("BRIGHTDATA_UNBLOCKER_PASS", "hp8kqmzw2666")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Keywords to find signup pages
SIGNUP_KEYWORDS = [
    "start service", "new service", "move-in", "moving", "residential",
    "new customer", "begin service", "establish service", "connect service",
    "new account", "sign up", "enroll"
]


def fetch_page(url: str) -> Optional[str]:
    """Fetch a page using BrightData Web Unlocker."""
    proxy_url = f"http://{WEB_UNLOCKER_USER}:{WEB_UNLOCKER_PASS}@{BRIGHTDATA_HOST}:{BRIGHTDATA_PORT}"
    
    try:
        response = requests.get(
            url,
            proxies={"http": proxy_url, "https": proxy_url},
            timeout=30,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            },
            verify=False
        )
        response.raise_for_status()
        return response.text
    except Exception as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return None


def find_signup_links(html: str, base_url: str) -> List[str]:
    """
    Find links to signup/new service pages.
    
    Args:
        html: HTML content of homepage
        base_url: Base URL for resolving relative links
    
    Returns:
        List of absolute URLs to potential signup pages
    """
    from bs4 import BeautifulSoup
    from urllib.parse import urljoin
    
    soup = BeautifulSoup(html, 'html.parser')
    signup_urls = []
    
    for link in soup.find_all('a', href=True):
        href = link.get('href', '')
        text = link.get_text(strip=True).lower()
        
        # Check if link text or href contains signup keywords
        is_signup = any(kw in text for kw in SIGNUP_KEYWORDS) or \
                   any(kw.replace(' ', '-') in href.lower() for kw in SIGNUP_KEYWORDS) or \
                   any(kw.replace(' ', '_') in href.lower() for kw in SIGNUP_KEYWORDS)
        
        if is_signup:
            absolute_url = urljoin(base_url, href)
            if absolute_url not in signup_urls:
                signup_urls.append(absolute_url)
    
    return signup_urls[:5]  # Limit to 5 most relevant


def extract_text_content(html: str) -> str:
    """Extract readable text content from HTML."""
    from bs4 import BeautifulSoup
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Remove script and style elements
    for element in soup(['script', 'style', 'nav', 'footer', 'header']):
        element.decompose()
    
    # Get text
    text = soup.get_text(separator='\n', strip=True)
    
    # Clean up whitespace
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    text = '\n'.join(lines)
    
    # Truncate to reasonable length for API
    if len(text) > 15000:
        text = text[:15000] + "\n[Content truncated...]"
    
    return text


def extract_instructions_with_ai(
    utility_name: str,
    utility_type: str,
    website_url: str,
    page_content: str
) -> Optional[Dict]:
    """
    Use GPT to extract structured signup instructions from page content.
    
    Args:
        utility_name: Name of the utility
        utility_type: Type (electric, gas, water, internet)
        website_url: URL of the utility website
        page_content: Text content from scraped pages
    
    Returns:
        Extracted instructions dict, or None if failed
    """
    if not OPENAI_API_KEY:
        logger.error("OPENAI_API_KEY not set")
        return None
    
    prompt = f"""You are extracting utility signup instructions from a utility company's website.

UTILITY INFORMATION:
- Name: {utility_name}
- Type: {utility_type} (electric, gas, water, internet)
- Website: {website_url}

WEBSITE CONTENT:
{page_content}

Extract the following information and return as JSON:

{{
  "signup_method": "online" | "phone" | "in_person" | "multiple",
  "online_signup_url": "direct URL to start service page, or null",
  "steps": [
    "Step 1 description",
    "Step 2 description"
  ],
  "required_documents": [
    "Document or info needed"
  ],
  "deposit": {{
    "required": true | false | "varies",
    "amount": "$X" or "varies based on credit" or null,
    "waiver_conditions": "description or null"
  }},
  "timeline": "typical time from request to service activation",
  "phone_number": "customer service number for signup",
  "hours": "business hours if mentioned",
  "notes": "any other relevant info (restrictions, special requirements, etc.)"
}}

RULES:
- Only include information explicitly stated on the website
- If information is not available, use null
- Steps should be actionable and specific
- Keep steps concise (one sentence each)
- Do not invent or assume information
- If the website doesn't have clear signup info, return {{"extraction_failed": true, "reason": "description"}}"""

    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "max_tokens": 1000
            },
            timeout=60
        )
        response.raise_for_status()
        
        result = response.json()
        content = result["choices"][0]["message"]["content"]
        
        # Parse JSON from response
        # Handle markdown code blocks
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        
        return json.loads(content.strip())
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse AI response as JSON: {e}")
        return None
    except Exception as e:
        logger.error(f"AI extraction failed: {e}")
        return None


def research_utility_instructions(
    utility_name: str,
    utility_type: str,
    website_url: Optional[str]
) -> Dict:
    """
    Research signup instructions for a utility.
    
    Args:
        utility_name: Name of the utility
        utility_type: Type (electric, gas, water, internet)
        website_url: URL of the utility website (optional)
    
    Returns:
        Instructions dict (either AI-extracted or indicates failure)
    """
    if not website_url:
        return {
            "extraction_failed": True,
            "reason": "No website URL available"
        }
    
    # Normalize URL
    if not website_url.startswith(('http://', 'https://')):
        website_url = 'https://' + website_url
    
    logger.info(f"Researching instructions for {utility_name} at {website_url}")
    
    # Step 1: Fetch homepage
    homepage_html = fetch_page(website_url)
    if not homepage_html:
        return {
            "extraction_failed": True,
            "reason": "Could not fetch utility website"
        }
    
    # Step 2: Find signup page links
    signup_urls = find_signup_links(homepage_html, website_url)
    
    # Step 3: Collect content from homepage and signup pages
    all_content = [f"=== HOMEPAGE ({website_url}) ===\n{extract_text_content(homepage_html)}"]
    
    for url in signup_urls[:3]:  # Max 3 additional pages
        page_html = fetch_page(url)
        if page_html:
            all_content.append(f"\n\n=== PAGE ({url}) ===\n{extract_text_content(page_html)}")
    
    combined_content = '\n'.join(all_content)
    
    # Truncate if too long
    if len(combined_content) > 20000:
        combined_content = combined_content[:20000] + "\n[Content truncated...]"
    
    # Step 4: Extract with AI
    instructions = extract_instructions_with_ai(
        utility_name=utility_name,
        utility_type=utility_type,
        website_url=website_url,
        page_content=combined_content
    )
    
    if instructions:
        # Add metadata
        instructions["source_urls"] = [website_url] + signup_urls[:3]
        return instructions
    else:
        return {
            "extraction_failed": True,
            "reason": "AI extraction returned no results"
        }


# Database cache functions
def get_cached_instructions(
    utility_id: str,
    utility_type: str,
    db_connection
) -> Optional[Dict]:
    """
    Check cache for existing instructions.
    
    Args:
        utility_id: Utility identifier
        utility_type: Type (electric, gas, water, internet)
        db_connection: Database connection
    
    Returns:
        Cached instructions dict, or None if not cached/expired
    """
    try:
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT instructions, is_generic, extraction_method
            FROM utility_instructions_cache
            WHERE utility_id = %s AND utility_type = %s AND expires_at > NOW()
        """, (utility_id, utility_type))
        
        row = cursor.fetchone()
        if row:
            instructions = row[0] if isinstance(row[0], dict) else json.loads(row[0])
            instructions["_cached"] = True
            instructions["_is_generic"] = row[1]
            instructions["_extraction_method"] = row[2]
            return instructions
        
        return None
    except Exception as e:
        logger.error(f"Cache lookup failed: {e}")
        return None


def cache_instructions(
    utility_id: str,
    utility_name: str,
    utility_type: str,
    instructions: Dict,
    source_urls: List[str],
    is_generic: bool,
    extraction_method: str,
    db_connection
) -> bool:
    """
    Store instructions in cache.
    
    Args:
        utility_id: Utility identifier
        utility_name: Utility name
        utility_type: Type (electric, gas, water, internet)
        instructions: Instructions dict
        source_urls: URLs that were scraped
        is_generic: True if using fallback template
        extraction_method: 'ai', 'fallback', or 'manual'
        db_connection: Database connection
    
    Returns:
        True if cached successfully
    """
    try:
        cursor = db_connection.cursor()
        cursor.execute("""
            INSERT INTO utility_instructions_cache 
            (utility_id, utility_name, utility_type, instructions, source_urls, 
             is_generic, extraction_method, fetched_at, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), NOW() + INTERVAL '90 days')
            ON CONFLICT (utility_id, utility_type) 
            DO UPDATE SET
                instructions = EXCLUDED.instructions,
                source_urls = EXCLUDED.source_urls,
                is_generic = EXCLUDED.is_generic,
                extraction_method = EXCLUDED.extraction_method,
                fetched_at = NOW(),
                expires_at = NOW() + INTERVAL '90 days'
        """, (
            utility_id,
            utility_name,
            utility_type,
            json.dumps(instructions),
            source_urls,
            is_generic,
            extraction_method
        ))
        db_connection.commit()
        return True
    except Exception as e:
        logger.error(f"Cache storage failed: {e}")
        return False


def get_utility_instructions(
    utility_id: str,
    utility_name: str,
    utility_type: str,
    website_url: Optional[str],
    state: str,
    is_deregulated: bool = False,
    is_mud: bool = False,
    db_connection = None
) -> Dict:
    """
    Main entry point for getting utility instructions.
    Checks cache first, then researches if needed, with fallback templates.
    
    Args:
        utility_id: Utility identifier
        utility_name: Utility name
        utility_type: Type (electric, gas, water, internet)
        website_url: Utility website URL
        state: Two-letter state code
        is_deregulated: True if deregulated electricity market
        is_mud: True if MUD/special district
        db_connection: Database connection (optional, for caching)
    
    Returns:
        Instructions dict
    """
    from .fallback_templates import get_fallback_template
    
    # Step 1: Check cache
    if db_connection:
        cached = get_cached_instructions(utility_id, utility_type, db_connection)
        if cached:
            logger.info(f"Using cached instructions for {utility_name}")
            return cached
    
    # Step 2: Research fresh
    instructions = research_utility_instructions(
        utility_name=utility_name,
        utility_type=utility_type,
        website_url=website_url
    )
    
    # Step 3: Use fallback if extraction failed
    if instructions.get("extraction_failed"):
        logger.info(f"Using fallback template for {utility_name}")
        instructions = get_fallback_template(
            utility_type=utility_type,
            state=state,
            is_mud=is_mud,
            is_deregulated=is_deregulated
        )
        extraction_method = "fallback"
        is_generic = True
    else:
        extraction_method = "ai"
        is_generic = False
    
    # Step 4: Cache the result
    if db_connection:
        cache_instructions(
            utility_id=utility_id,
            utility_name=utility_name,
            utility_type=utility_type,
            instructions=instructions,
            source_urls=instructions.get("source_urls", []),
            is_generic=is_generic,
            extraction_method=extraction_method,
            db_connection=db_connection
        )
    
    return instructions
