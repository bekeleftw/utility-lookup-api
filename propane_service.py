#!/usr/bin/env python3
"""
Propane delivery service detection.
Areas without natural gas infrastructure use propane.
"""

from typing import Dict, Optional, List

PROPANE_PROVIDERS = {
    "amerigas": {
        "name": "AmeriGas",
        "website": "https://www.amerigas.com",
        "phone": "1-800-263-7442",
        "coverage": "nationwide"
    },
    "suburban_propane": {
        "name": "Suburban Propane",
        "website": "https://www.suburbanpropane.com",
        "phone": "1-800-776-7263",
        "coverage": "nationwide"
    },
    "ferrellgas": {
        "name": "Ferrellgas",
        "website": "https://www.ferrellgas.com",
        "phone": "1-888-337-7355",
        "coverage": "nationwide"
    }
}

HIGH_PROPANE_STATES = ["ME", "VT", "NH", "MT", "WY", "SD", "ND", "AK"]

RURAL_PROPANE_INDICATORS = [
    "no natural gas service",
    "propane only",
    "lp gas",
    "bottled gas"
]


def get_propane_providers_for_state(state: str) -> List[Dict]:
    """Get propane providers that serve a state."""
    state = state.upper()
    providers = []
    for key, info in PROPANE_PROVIDERS.items():
        if info.get("coverage") == "nationwide":
            providers.append(info)
    return providers


def is_likely_propane_area(state: str, zip_code: str = None, city: str = None) -> Dict:
    """Check if area likely uses propane instead of natural gas."""
    state = state.upper()
    
    if state in HIGH_PROPANE_STATES:
        return {
            "propane_likely": True,
            "reason": "State has limited natural gas infrastructure",
            "providers": get_propane_providers_for_state(state)
        }
    
    return {"propane_likely": False}


def get_no_gas_response(state: str, zip_code: str = None) -> Dict:
    """Build response when no natural gas service is available."""
    propane_info = is_likely_propane_area(state, zip_code)
    
    return {
        "gas_service": False,
        "alternative": "propane",
        "propane_providers": get_propane_providers_for_state(state),
        "note": "Natural gas service not available. Propane delivery is the typical alternative.",
        "propane_likely": propane_info.get("propane_likely", False)
    }


if __name__ == "__main__":
    print("Propane Service Tests:")
    print("=" * 60)
    
    for state in ["TX", "ME", "VT", "CA"]:
        result = is_likely_propane_area(state)
        print(f"{state}: propane_likely={result['propane_likely']}")
