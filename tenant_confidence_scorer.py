#!/usr/bin/env python3
"""
Tenant Confidence Scorer

Calculates confidence scores for tenant-reported utilities based on:
- Number of samples (more tenants = higher confidence)
- Agreement rate (all tenants agree = higher confidence)
- Utility type validation (wrong type = lower confidence)

Also includes utility type validation (Phase 1.3).
"""

import re
from collections import Counter
from typing import Dict, List, Optional
from utility_name_normalizer import normalize_utility_name
from deregulated_market_handler import is_retail_provider, is_deregulated_state, should_ignore_tenant_mismatch


# Utility type validation - detect wrong uploads
GAS_INDICATORS = [
    "gas", "piedmont", "atmos", "spire", "nicor", "southern company gas",
    "centerpoint gas", "national fuel", "peoples gas", "washington gas",
    "southwest gas", "northwest natural", "cascade natural", "puget sound gas",
    "questar", "dominion gas", "columbia gas", "nipsco gas"
]

ELECTRIC_INDICATORS = [
    "electric", "power", "edison", "ppl", "emc", "coop", "cooperative",
    "light", "energy", "pge", "sce", "sdge", "fpl", "duke", "dominion",
    "xcel", "entergy", "aep", "ameren", "comed", "pseg", "oncor", "srp"
]


def validate_utility_type(reported_name: str, expected_type: str) -> Dict:
    """
    Check if reported utility matches expected type.
    
    Args:
        reported_name: Utility name from tenant
        expected_type: "electric" or "gas"
        
    Returns:
        {
            "valid": bool,
            "issue": str or None,
            "confidence_penalty": float (0.0 to 0.5)
        }
    """
    if not reported_name:
        return {"valid": False, "issue": "empty_name", "confidence_penalty": 1.0}
    
    name_lower = reported_name.lower()
    
    # Electric field contains gas utility
    if expected_type == "electric":
        for indicator in GAS_INDICATORS:
            if indicator in name_lower and "electric" not in name_lower:
                return {
                    "valid": False,
                    "issue": "gas_in_electric_field",
                    "confidence_penalty": 0.5
                }
    
    # Gas field contains electric utility
    if expected_type == "gas":
        for indicator in ELECTRIC_INDICATORS:
            if indicator in name_lower and "gas" not in name_lower:
                return {
                    "valid": False,
                    "issue": "electric_in_gas_field",
                    "confidence_penalty": 0.5
                }
    
    return {"valid": True, "issue": None, "confidence_penalty": 0.0}


def normalize_street_name(street: str) -> str:
    """Normalize street name for consistent matching."""
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
    """Extract street name from full address."""
    if not address:
        return None
    
    # Match: "123 Main St, City, ST 12345" -> "Main St"
    match = re.match(r'[\d\-]+\s+(.+?),', address)
    if match:
        return normalize_street_name(match.group(1))
    
    return None


def calculate_tenant_confidence(
    zip_code: str,
    street_name: str,
    tenant_records: List[Dict],
    utility_type: str = "electric"
) -> Optional[Dict]:
    """
    Calculate confidence score for tenant-reported utility on a street.
    
    Args:
        zip_code: 5-digit ZIP code
        street_name: Normalized street name
        tenant_records: List of {"utility": "name", "address": "full address"}
        utility_type: "electric" or "gas"
        
    Returns:
        {
            "utility": "Duke Energy",
            "confidence": 0.92,
            "sample_count": 7,
            "agreement_rate": 1.0,
            "action": "hard_override" | "ai_boost" | "ai_context" | "store_only" | "flag_review",
            "all_utilities": {"Duke Energy": 5, "Other": 1},
            "validation_issues": []
        }
    """
    if not tenant_records:
        return None
    
    # Normalize all utility names and validate types
    normalized_utilities = []
    validation_issues = []
    
    for record in tenant_records:
        raw_name = record.get("utility", "")
        
        # Validate utility type
        validation = validate_utility_type(raw_name, utility_type)
        if not validation["valid"]:
            validation_issues.append({
                "utility": raw_name,
                "issue": validation["issue"]
            })
            continue  # Skip invalid entries
        
        # Normalize the name
        normalized = normalize_utility_name(raw_name)
        if normalized:
            normalized_utilities.append(normalized)
    
    if not normalized_utilities:
        return None
    
    # Count occurrences
    counts = Counter(normalized_utilities)
    total = len(normalized_utilities)
    
    # Find dominant utility
    dominant_utility, dominant_count = counts.most_common(1)[0]
    agreement_rate = dominant_count / total
    
    # Determine confidence and action based on thresholds from instructions
    if total >= 10 and agreement_rate == 1.0:
        confidence = 0.99
        action = "hard_override"
    elif total >= 5 and agreement_rate >= 0.95:
        confidence = 0.90
        action = "hard_override"
    elif total >= 3 and agreement_rate >= 0.90:
        confidence = 0.80
        action = "ai_boost"
    elif total >= 2 and agreement_rate >= 0.90:
        confidence = 0.70
        action = "ai_context"
    elif total == 1:
        confidence = 0.50
        action = "store_only"
    else:
        # Disagreement case
        confidence = 0.40
        action = "flag_review"
    
    return {
        "utility": dominant_utility,
        "confidence": confidence,
        "sample_count": total,
        "agreement_rate": round(agreement_rate, 3),
        "action": action,
        "all_utilities": dict(counts),
        "validation_issues": validation_issues
    }


def process_tenant_data(records: List[Dict], utility_type: str = "electric") -> Dict:
    """
    Process all tenant records and generate confidence scores by ZIP+street.
    
    Args:
        records: List of {"display": "address", "Electricity": "utility", ...}
        utility_type: "electric" or "gas"
        
    Returns:
        {
            "by_zip_street": {
                "29720": {
                    "meadow drive": {...confidence data...}
                }
            },
            "stats": {...}
        }
    """
    from collections import defaultdict
    
    # Group by ZIP + street
    by_zip_street = defaultdict(lambda: defaultdict(list))
    
    field_name = "Electricity" if utility_type == "electric" else "Gas"
    
    for record in records:
        address = record.get("display", "")
        utility = record.get(field_name, "").strip()
        
        if not address or not utility:
            continue
        
        # Extract ZIP
        zip_match = re.search(r'(\d{5})', address)
        if not zip_match:
            continue
        zip_code = zip_match.group(1)
        
        # Extract street
        street = extract_street_from_address(address)
        if not street:
            continue
        
        by_zip_street[zip_code][street].append({
            "utility": utility,
            "address": address
        })
    
    # Calculate confidence for each ZIP+street
    results = {}
    stats = {
        "total_zips": 0,
        "total_streets": 0,
        "hard_overrides": 0,
        "ai_boost": 0,
        "ai_context": 0,
        "store_only": 0,
        "flag_review": 0
    }
    
    for zip_code, streets in by_zip_street.items():
        results[zip_code] = {}
        stats["total_zips"] += 1
        
        for street, records in streets.items():
            stats["total_streets"] += 1
            
            confidence_data = calculate_tenant_confidence(
                zip_code, street, records, utility_type
            )
            
            if confidence_data:
                results[zip_code][street] = confidence_data
                stats[confidence_data["action"]] = stats.get(confidence_data["action"], 0) + 1
    
    return {
        "by_zip_street": results,
        "stats": stats
    }


# Test function
def _test():
    print("Testing utility type validation:")
    test_cases = [
        ("Duke Energy", "electric", True),
        ("Atmos Energy", "electric", False),  # Gas in electric field
        ("Piedmont Natural Gas", "gas", True),
        ("Duke Energy", "gas", False),  # Electric in gas field
    ]
    
    for utility, utype, expected_valid in test_cases:
        result = validate_utility_type(utility, utype)
        status = "✓" if result["valid"] == expected_valid else "✗"
        print(f"  {status} '{utility}' as {utype} -> valid={result['valid']} (expected: {expected_valid})")
    
    print("\nTesting confidence scoring:")
    test_records = [
        {"utility": "Duke Energy", "address": "123 Main St"},
        {"utility": "Duke Energy Carolinas", "address": "125 Main St"},
        {"utility": "Duke Energy", "address": "127 Main St"},
        {"utility": "Duke Energy Corporation", "address": "129 Main St"},
        {"utility": "Duke Energy", "address": "131 Main St"},
    ]
    
    result = calculate_tenant_confidence("29720", "main street", test_records)
    print(f"  5 Duke Energy variants on Main St:")
    print(f"    Utility: {result['utility']}")
    print(f"    Confidence: {result['confidence']}")
    print(f"    Action: {result['action']}")
    print(f"    Agreement: {result['agreement_rate']}")


if __name__ == "__main__":
    _test()
