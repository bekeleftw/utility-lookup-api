#!/usr/bin/env python3
"""
Tenant Override Lookup

Provides functions to check tenant-verified overrides and context
for use in the main utility lookup pipeline.

This is the integration point between tenant data and the lookup system.
"""

import json
import os
import re
from typing import Dict, Optional

# Cache loaded data
_HARD_OVERRIDES = None
_AI_CONTEXT = None

DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')


def _load_hard_overrides():
    """Load hard overrides from disk."""
    global _HARD_OVERRIDES
    if _HARD_OVERRIDES is None:
        filepath = os.path.join(DATA_DIR, 'tenant_hard_overrides.json')
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                data = json.load(f)
                _HARD_OVERRIDES = data.get('overrides', {})
        else:
            _HARD_OVERRIDES = {}
    return _HARD_OVERRIDES


def _load_ai_context():
    """Load AI context from disk."""
    global _AI_CONTEXT
    if _AI_CONTEXT is None:
        filepath = os.path.join(DATA_DIR, 'tenant_ai_context.json')
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                data = json.load(f)
                _AI_CONTEXT = data.get('context_rules', {})
        else:
            _AI_CONTEXT = {}
    return _AI_CONTEXT


def normalize_street_for_lookup(street: str) -> str:
    """Normalize street name for lookup matching."""
    if not street:
        return ""
    
    street = street.lower().strip()
    
    # Remove unit/apt numbers
    street = re.sub(r'\s+(apt|unit|ste|suite|#|bldg|building)\s*\S*$', '', street, flags=re.I)
    
    # Normalize common abbreviations
    replacements = [
        (r'\bst\b', 'street'), (r'\bave\b', 'avenue'), (r'\bblvd\b', 'boulevard'),
        (r'\bdr\b', 'drive'), (r'\bln\b', 'lane'), (r'\brd\b', 'road'),
        (r'\bct\b', 'court'), (r'\bpl\b', 'place'), (r'\bcir\b', 'circle'),
        (r'\bpkwy\b', 'parkway'), (r'\bhwy\b', 'highway'), (r'\bter\b', 'terrace'),
    ]
    for pattern, replacement in replacements:
        street = re.sub(pattern, replacement, street)
    
    return street.strip()


def extract_street_from_address(address: str) -> Optional[str]:
    """Extract and normalize street name from full address."""
    if not address:
        return None
    
    match = re.match(r'[\d\-]+\s+(.+?),', address)
    if match:
        return normalize_street_for_lookup(match.group(1))
    
    return None


def check_tenant_override(
    zip_code: str,
    street: str,
    utility_type: str = "electric"
) -> Optional[Dict]:
    """
    Check if we have a high-confidence tenant override for this location.
    
    Args:
        zip_code: 5-digit ZIP code
        street: Street name (will be normalized)
        utility_type: "electric" or "gas"
        
    Returns:
        {
            "utility": "Duke Energy",
            "confidence": 0.95,
            "sample_count": 7,
            "source": "tenant_verified"
        }
        or None if no override exists
    """
    if utility_type != "electric":
        return None  # Currently only have electric data
    
    overrides = _load_hard_overrides()
    
    if not zip_code or zip_code not in overrides:
        return None
    
    zip_overrides = overrides[zip_code]
    normalized_street = normalize_street_for_lookup(street)
    
    # Try exact match first
    if normalized_street in zip_overrides:
        data = zip_overrides[normalized_street]
        return {
            "utility": data["electric"],
            "confidence": data["confidence"],
            "sample_count": data["sample_count"],
            "source": "tenant_verified"
        }
    
    # Try partial match (street prefix)
    for override_street, data in zip_overrides.items():
        if normalized_street.startswith(override_street.split()[0]) or \
           override_street.startswith(normalized_street.split()[0]):
            # Only match if first word is same and has 4+ chars
            if len(normalized_street.split()[0]) >= 4:
                return {
                    "utility": data["electric"],
                    "confidence": data["confidence"] * 0.9,  # Slightly lower for partial match
                    "sample_count": data["sample_count"],
                    "source": "tenant_verified_partial"
                }
    
    return None


def get_tenant_context(
    zip_code: str,
    street: str = None,
    utility_type: str = "electric"
) -> Optional[Dict]:
    """
    Get tenant context for AI selector.
    
    Args:
        zip_code: 5-digit ZIP code
        street: Optional street name for more specific context
        utility_type: "electric" or "gas"
        
    Returns:
        {
            "utilities_observed": ["Duke Energy", "York Electric"],
            "patterns": [
                {"street": "meadow drive", "utility": "Duke Energy", "confidence": 0.75}
            ],
            "is_split_territory": True,
            "context_text": "Human-readable context for AI"
        }
        or None if no context exists
    """
    if utility_type != "electric":
        return None
    
    context = _load_ai_context()
    
    if not zip_code or zip_code not in context:
        return None
    
    zip_context = context[zip_code]
    
    result = {
        "utilities_observed": zip_context.get("utilities_observed", []),
        "patterns": zip_context.get("patterns", []),
        "is_split_territory": len(zip_context.get("utilities_observed", [])) >= 2
    }
    
    # Build context text for AI
    lines = []
    if result["is_split_territory"]:
        lines.append(f"TENANT DATA: ZIP {zip_code} has multiple utilities: {', '.join(result['utilities_observed'][:3])}")
    
    # Find relevant patterns
    if street:
        normalized_street = normalize_street_for_lookup(street)
        for pattern in result["patterns"]:
            if pattern["street"] in normalized_street or normalized_street in pattern["street"]:
                lines.append(f"Street pattern: {pattern['street']} → {pattern['utility']} ({pattern['samples']} samples, {pattern['confidence']*100:.0f}%)")
    
    if not lines and result["patterns"]:
        # Show top patterns even if no street match
        for pattern in result["patterns"][:3]:
            lines.append(f"Area pattern: {pattern['street']} → {pattern['utility']} ({pattern['samples']} samples)")
    
    result["context_text"] = "\n".join(lines) if lines else None
    
    return result


def check_tenant_override_for_address(
    address: str,
    utility_type: str = "electric"
) -> Optional[Dict]:
    """
    Convenience function to check override using full address.
    
    Args:
        address: Full address string
        utility_type: "electric" or "gas"
        
    Returns:
        Override dict or None
    """
    # Extract ZIP
    zip_match = re.search(r'(\d{5})', address)
    if not zip_match:
        return None
    zip_code = zip_match.group(1)
    
    # Extract street
    street = extract_street_from_address(address)
    if not street:
        return None
    
    return check_tenant_override(zip_code, street, utility_type)


def get_tenant_context_for_address(
    address: str,
    utility_type: str = "electric"
) -> Optional[Dict]:
    """
    Convenience function to get context using full address.
    
    Args:
        address: Full address string
        utility_type: "electric" or "gas"
        
    Returns:
        Context dict or None
    """
    # Extract ZIP
    zip_match = re.search(r'(\d{5})', address)
    if not zip_match:
        return None
    zip_code = zip_match.group(1)
    
    # Extract street
    street = extract_street_from_address(address)
    
    return get_tenant_context(zip_code, street, utility_type)


# Test function
def _test():
    print("Testing tenant override lookup:")
    
    # Test with known override ZIP (from our generated data)
    test_cases = [
        ("66502", "laramie street", True),  # Should have override
        ("29544", "evergreen drive", True),  # Should have override
        ("00000", "fake street", False),  # Should not exist
    ]
    
    for zip_code, street, should_exist in test_cases:
        result = check_tenant_override(zip_code, street)
        exists = result is not None
        status = "✓" if exists == should_exist else "✗"
        if result:
            print(f"  {status} {zip_code}/{street} → {result['utility']} ({result['confidence']*100:.0f}%)")
        else:
            print(f"  {status} {zip_code}/{street} → No override")
    
    print("\nTesting context lookup:")
    context = get_tenant_context("29544", "evergreen drive")
    if context:
        print(f"  ZIP 29544 utilities: {context['utilities_observed']}")
        print(f"  Is split territory: {context['is_split_territory']}")
        if context['context_text']:
            print(f"  Context: {context['context_text'][:100]}...")


if __name__ == "__main__":
    _test()
