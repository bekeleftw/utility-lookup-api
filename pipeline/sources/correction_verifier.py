"""
Correction verification system using SERP checks.

Evaluates user-submitted corrections to determine appropriate confidence levels.
"""

import os
import re
import requests
from typing import Dict, Optional, Tuple
from dataclasses import dataclass

AIRTABLE_API_KEY = os.getenv('AIRTABLE_API_KEY')
AIRTABLE_BASE_ID = os.getenv('AIRTABLE_BASE_ID')
SERP_API_KEY = os.getenv('SERP_API_KEY')  # For Google search API
CORRECTIONS_TABLE = 'utility_corrections'


@dataclass
class VerificationResult:
    """Result of verifying a correction."""
    is_verified: bool
    confidence: int
    ai_context: str
    notes: str
    serp_confirmed: bool


def verify_correction(
    provider: str,
    city: str,
    state: str,
    zip_code: str,
    utility_type: str
) -> VerificationResult:
    """
    Verify a correction using SERP search.
    
    Returns a VerificationResult with:
    - is_verified: True if SERP confirms the provider serves this area
    - confidence: Recommended confidence score (60-95)
    - ai_context: Context to add to AI prompt for ambiguous cases
    - notes: Human-readable verification notes
    - serp_confirmed: True if SERP results clearly confirm
    """
    
    # Build search query
    query = f"{provider} {city} {state} {utility_type} utility service area"
    
    try:
        search_results = _perform_serp_search(query)
        
        if not search_results:
            return VerificationResult(
                is_verified=False,
                confidence=70,
                ai_context=f"User reported {provider} serves {city}, {state} ({zip_code}) for {utility_type}. Unverified.",
                notes="SERP search returned no results",
                serp_confirmed=False
            )
        
        # Analyze results
        analysis = _analyze_serp_results(search_results, provider, city, state, utility_type)
        
        return analysis
        
    except Exception as e:
        return VerificationResult(
            is_verified=False,
            confidence=70,
            ai_context=f"User reported {provider} serves {city}, {state} for {utility_type}.",
            notes=f"SERP verification failed: {str(e)}",
            serp_confirmed=False
        )


def _perform_serp_search(query: str) -> list:
    """
    Perform a web search using available SERP API.
    
    Tries multiple methods:
    1. SerpAPI if SERP_API_KEY is set
    2. Fallback to basic requests if no API key
    """
    
    if SERP_API_KEY:
        # Use SerpAPI
        try:
            response = requests.get(
                "https://serpapi.com/search",
                params={
                    "q": query,
                    "api_key": SERP_API_KEY,
                    "num": 5
                },
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("organic_results", [])
        except Exception:
            pass
    
    # Fallback: Use DuckDuckGo instant answers (free, no API key)
    try:
        response = requests.get(
            "https://api.duckduckgo.com/",
            params={
                "q": query,
                "format": "json",
                "no_html": 1
            },
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            results = []
            if data.get("AbstractText"):
                results.append({
                    "title": data.get("Heading", ""),
                    "snippet": data.get("AbstractText", ""),
                    "link": data.get("AbstractURL", "")
                })
            for topic in data.get("RelatedTopics", [])[:5]:
                if isinstance(topic, dict) and topic.get("Text"):
                    results.append({
                        "title": topic.get("FirstURL", "").split("/")[-1],
                        "snippet": topic.get("Text", ""),
                        "link": topic.get("FirstURL", "")
                    })
            return results
    except Exception:
        pass
    
    return []


def _analyze_serp_results(
    results: list,
    provider: str,
    city: str,
    state: str,
    utility_type: str
) -> VerificationResult:
    """
    Analyze SERP results to determine if provider serves the area.
    """
    
    provider_lower = provider.lower()
    city_lower = city.lower()
    state_lower = state.lower()
    
    # Count positive and negative signals
    positive_signals = 0
    negative_signals = 0
    evidence = []
    
    for result in results:
        title = (result.get("title") or "").lower()
        snippet = (result.get("snippet") or "").lower()
        combined = f"{title} {snippet}"
        
        # Check if provider is mentioned with the city
        provider_mentioned = provider_lower in combined or _fuzzy_match(provider_lower, combined)
        city_mentioned = city_lower in combined
        
        if provider_mentioned and city_mentioned:
            # Strong positive signal
            if any(word in combined for word in ["serves", "service area", "customers", "provides", "utility"]):
                positive_signals += 2
                evidence.append(f"Found: '{snippet[:100]}...'")
            else:
                positive_signals += 1
        
        # Check for contradicting info (another provider mentioned as serving the city)
        if city_mentioned and not provider_mentioned:
            if any(word in combined for word in ["serves", "service area", "electric utility"]):
                negative_signals += 1
    
    # Determine verification result
    if positive_signals >= 3:
        # Strong confirmation
        return VerificationResult(
            is_verified=True,
            confidence=95,
            ai_context="",  # No context needed, high confidence
            notes=f"SERP strongly confirms {provider} serves {city}, {state}. Evidence: {'; '.join(evidence[:2])}",
            serp_confirmed=True
        )
    elif positive_signals >= 1 and negative_signals == 0:
        # Moderate confirmation
        return VerificationResult(
            is_verified=True,
            confidence=85,
            ai_context=f"User feedback and search results suggest {provider} may serve parts of {city}, {state} for {utility_type}.",
            notes=f"SERP moderately confirms {provider} serves {city}. {positive_signals} positive signals.",
            serp_confirmed=True
        )
    elif positive_signals > 0 and negative_signals > 0:
        # Ambiguous - multiple providers may serve the area
        return VerificationResult(
            is_verified=False,
            confidence=75,
            ai_context=f"User reported {provider} serves {city}, {state} for {utility_type}, but multiple providers may serve this area. Consider location carefully.",
            notes=f"Ambiguous results: {positive_signals} positive, {negative_signals} negative signals.",
            serp_confirmed=False
        )
    else:
        # No confirmation
        return VerificationResult(
            is_verified=False,
            confidence=70,
            ai_context=f"User reported {provider} serves {city}, {state} for {utility_type}. Unverified - treat as suggestion.",
            notes="SERP did not confirm provider serves this area.",
            serp_confirmed=False
        )


def _fuzzy_match(provider: str, text: str) -> bool:
    """Check for fuzzy matches of provider name in text."""
    # Handle common variations
    variations = [
        provider,
        provider.replace(" ", ""),
        provider.replace("energy", "").strip(),
        provider.replace("services", "").strip(),
    ]
    
    for var in variations:
        if var and len(var) > 3 and var in text:
            return True
    
    return False


def verify_and_update_correction(record_id: str) -> VerificationResult:
    """
    Verify a correction in Airtable and update its fields.
    
    Args:
        record_id: Airtable record ID to verify
        
    Returns:
        VerificationResult with the verification outcome
    """
    if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID:
        raise ValueError("Airtable credentials not configured")
    
    # Fetch the record
    response = requests.get(
        f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{CORRECTIONS_TABLE}/{record_id}",
        headers={'Authorization': f'Bearer {AIRTABLE_API_KEY}'},
        timeout=10
    )
    
    if response.status_code != 200:
        raise ValueError(f"Failed to fetch record: {response.text}")
    
    fields = response.json().get('fields', {})
    
    # Verify
    result = verify_correction(
        provider=fields.get('correct_provider', ''),
        city=fields.get('city', ''),
        state=fields.get('state', ''),
        zip_code=fields.get('zip_code', ''),
        utility_type=fields.get('utility_type', '')
    )
    
    # Update the record
    update_data = {
        "fields": {
            "serp_verified": result.serp_confirmed,
            "confidence_override": result.confidence,
            "ai_context": result.ai_context,
            "verification_notes": result.notes
        }
    }
    
    update_response = requests.patch(
        f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{CORRECTIONS_TABLE}/{record_id}",
        headers={
            'Authorization': f'Bearer {AIRTABLE_API_KEY}',
            'Content-Type': 'application/json'
        },
        json=update_data,
        timeout=10
    )
    
    if update_response.status_code != 200:
        raise ValueError(f"Failed to update record: {update_response.text}")
    
    return result


def verify_all_unverified_corrections() -> Dict[str, VerificationResult]:
    """
    Find and verify all corrections that haven't been verified yet.
    
    Returns:
        Dict mapping record IDs to their verification results
    """
    if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID:
        raise ValueError("Airtable credentials not configured")
    
    # Fetch unverified records
    response = requests.get(
        f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{CORRECTIONS_TABLE}",
        headers={'Authorization': f'Bearer {AIRTABLE_API_KEY}'},
        params={
            'filterByFormula': 'AND({serp_verified} = FALSE(), {verified} = FALSE())'
        },
        timeout=10
    )
    
    if response.status_code != 200:
        raise ValueError(f"Failed to fetch records: {response.text}")
    
    records = response.json().get('records', [])
    results = {}
    
    for record in records:
        record_id = record.get('id')
        try:
            result = verify_and_update_correction(record_id)
            results[record_id] = result
        except Exception as e:
            results[record_id] = VerificationResult(
                is_verified=False,
                confidence=70,
                ai_context="",
                notes=f"Verification error: {str(e)}",
                serp_confirmed=False
            )
    
    return results
