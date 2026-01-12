#!/usr/bin/env python3
"""
Well and septic system detection.
Areas with private wells/septic don't have public water/sewer service.
"""

from typing import Dict, Optional, List

# Indicators that suggest well/septic usage
RURAL_INDICATORS = [
    "unincorporated",
    "rural route",
    "rr ",
    "county road",
    "cr ",
    "farm road",
    "fm ",
    "ranch road"
]

# States with high well/septic usage rates
HIGH_WELL_SEPTIC_STATES = {
    "ME": {"well_pct": 45, "septic_pct": 55},
    "VT": {"well_pct": 40, "septic_pct": 50},
    "NH": {"well_pct": 38, "septic_pct": 45},
    "AK": {"well_pct": 35, "septic_pct": 40},
    "MT": {"well_pct": 30, "septic_pct": 35},
    "WY": {"well_pct": 28, "septic_pct": 32},
    "NC": {"well_pct": 25, "septic_pct": 48},
    "SC": {"well_pct": 22, "septic_pct": 40},
}

# County health department contacts for well/septic permits
COUNTY_HEALTH_CONTACTS = {
    "TX": {
        "agency": "County Health Department or TCEQ",
        "well_permits": "Texas Commission on Environmental Quality",
        "septic_permits": "County Environmental Health",
        "website": "https://www.tceq.texas.gov"
    },
    "CA": {
        "agency": "County Environmental Health",
        "well_permits": "State Water Resources Control Board",
        "septic_permits": "County Environmental Health",
        "website": "https://www.waterboards.ca.gov"
    },
    "FL": {
        "agency": "County Health Department",
        "well_permits": "Water Management District",
        "septic_permits": "Florida Department of Health",
        "website": "https://www.floridahealth.gov"
    }
}


def is_likely_rural(address: str, city: str = None) -> bool:
    """Check if address appears to be rural (likely well/septic)."""
    if not address:
        return False
    
    address_lower = address.lower()
    return any(indicator in address_lower for indicator in RURAL_INDICATORS)


def get_well_septic_likelihood(
    state: str,
    is_incorporated: bool = True,
    address: str = None
) -> Dict:
    """Estimate likelihood of well/septic based on location."""
    state = state.upper()
    
    base_likelihood = 0.1  # 10% baseline
    
    # Adjust for state
    if state in HIGH_WELL_SEPTIC_STATES:
        state_data = HIGH_WELL_SEPTIC_STATES[state]
        base_likelihood = state_data.get("well_pct", 20) / 100
    
    # Adjust for incorporated status
    if not is_incorporated:
        base_likelihood = min(base_likelihood * 2.5, 0.8)
    
    # Adjust for rural address indicators
    if address and is_likely_rural(address):
        base_likelihood = min(base_likelihood * 2, 0.9)
    
    return {
        "well_likelihood": base_likelihood,
        "septic_likelihood": base_likelihood * 1.1,  # Septic slightly more common
        "state": state,
        "is_incorporated": is_incorporated
    }


def get_no_public_water_response(state: str, county: str = None) -> Dict:
    """Build response when no public water service is available."""
    contact = COUNTY_HEALTH_CONTACTS.get(state, {})
    
    return {
        "water_service": False,
        "source": "private_well",
        "note": "No public water service. Property likely uses private well.",
        "permit_info": {
            "agency": contact.get("well_permits", "County Health Department"),
            "website": contact.get("website")
        },
        "recommendations": [
            "Verify well exists and is permitted",
            "Request water quality test results",
            "Check well depth and capacity"
        ]
    }


def get_no_public_sewer_response(state: str, county: str = None) -> Dict:
    """Build response when no public sewer service is available."""
    contact = COUNTY_HEALTH_CONTACTS.get(state, {})
    
    return {
        "sewer_service": False,
        "source": "septic_system",
        "note": "No public sewer service. Property likely uses septic system.",
        "permit_info": {
            "agency": contact.get("septic_permits", "County Health Department"),
            "website": contact.get("website")
        },
        "recommendations": [
            "Verify septic permit and inspection history",
            "Request septic tank pumping records",
            "Check system age and capacity"
        ]
    }


if __name__ == "__main__":
    print("Well/Septic Detection Tests:")
    print("=" * 60)
    
    test_cases = [
        ("TX", True, "123 Main St"),
        ("TX", False, "Rural Route 5 Box 100"),
        ("ME", True, "456 Oak Ave"),
        ("ME", False, "County Road 12"),
    ]
    
    for state, incorporated, addr in test_cases:
        result = get_well_septic_likelihood(state, incorporated, addr)
        print(f"\n{state}, incorporated={incorporated}, addr='{addr}'")
        print(f"  Well likelihood: {result['well_likelihood']:.1%}")
        print(f"  Septic likelihood: {result['septic_likelihood']:.1%}")
