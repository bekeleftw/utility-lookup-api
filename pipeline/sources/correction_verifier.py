"""
Correction verification system using BrightData SERP checks.

Evaluates user-submitted corrections to determine appropriate confidence levels.
Uses the existing serp_verification.py module for BrightData Google searches.
"""

import os
import sys
import requests
from typing import Dict, Optional
from dataclasses import dataclass

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

AIRTABLE_API_KEY = os.getenv('AIRTABLE_API_KEY')
AIRTABLE_BASE_ID = os.getenv('AIRTABLE_BASE_ID')
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
    Verify a correction using BrightData SERP search.
    
    Returns a VerificationResult with:
    - is_verified: True if SERP confirms the provider serves this area
    - confidence: Recommended confidence score (60-95)
    - ai_context: Context to add to AI prompt for ambiguous cases
    - notes: Human-readable verification notes
    - serp_confirmed: True if SERP results clearly confirm
    """
    
    try:
        # Use the existing BrightData SERP verification module
        from serp_verification import verify_utility_via_serp, is_alias
        
        result = verify_utility_via_serp(
            address="",
            city=city,
            state=state,
            utility_type=utility_type,
            expected_utility=provider,
            zip_code=zip_code,
            use_cache=True
        )
        
        # Convert to our VerificationResult format
        if result.verified:
            # SERP confirms the provider
            if result.confidence_boost >= 0.10:
                # Strong confirmation
                return VerificationResult(
                    is_verified=True,
                    confidence=95,
                    ai_context="",  # No context needed, high confidence
                    notes=f"BrightData SERP confirms {provider} serves {city}, {state}. {result.notes}",
                    serp_confirmed=True
                )
            else:
                # Moderate confirmation
                return VerificationResult(
                    is_verified=True,
                    confidence=85,
                    ai_context=f"Search results suggest {provider} serves {city}, {state} for {utility_type}.",
                    notes=f"BrightData SERP moderately confirms. {result.notes}",
                    serp_confirmed=True
                )
        elif result.serp_utility:
            # SERP found a different provider
            if is_alias(provider, result.serp_utility):
                # Actually a match (alias)
                return VerificationResult(
                    is_verified=True,
                    confidence=90,
                    ai_context="",
                    notes=f"BrightData SERP found {result.serp_utility} (alias match). {result.notes}",
                    serp_confirmed=True
                )
            else:
                # Different provider found - ambiguous
                return VerificationResult(
                    is_verified=False,
                    confidence=75,
                    ai_context=f"User reported {provider} serves {city}, {state} for {utility_type}, but search found {result.serp_utility}. Multiple providers may serve this area.",
                    notes=f"BrightData SERP found different provider: {result.serp_utility}. {result.notes}",
                    serp_confirmed=False
                )
        else:
            # No results
            return VerificationResult(
                is_verified=False,
                confidence=70,
                ai_context=f"User reported {provider} serves {city}, {state} for {utility_type}. Unverified.",
                notes=f"BrightData SERP returned no conclusive results. {result.notes}",
                serp_confirmed=False
            )
            
    except ImportError as e:
        return VerificationResult(
            is_verified=False,
            confidence=70,
            ai_context=f"User reported {provider} serves {city}, {state} for {utility_type}.",
            notes=f"SERP verification module not available: {str(e)}",
            serp_confirmed=False
        )
    except Exception as e:
        return VerificationResult(
            is_verified=False,
            confidence=70,
            ai_context=f"User reported {provider} serves {city}, {state} for {utility_type}.",
            notes=f"BrightData SERP verification failed: {str(e)}",
            serp_confirmed=False
        )


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
