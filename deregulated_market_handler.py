#!/usr/bin/env python3
"""
Deregulated Market Handler

Handles REP (Retail Electric Provider) vs TDU (Transmission/Distribution Utility)
distinction in deregulated states like Texas, Pennsylvania, Ohio, etc.

In deregulated markets:
- Tenant may report their REP (who they pay, e.g., "TXU Energy")
- Our API returns the TDU (who owns the wires, e.g., "Oncor")
- BOTH are correct for different purposes
- For property management, we typically want the TDU
"""

from typing import Optional, Dict, Set

# Texas Retail Electric Providers (REPs) - NOT the utility we want for property management
TEXAS_REPS: Set[str] = {
    "txu energy", "txu", 
    "reliant", "reliant energy",
    "direct energy",
    "gexa energy", "gexa",
    "green mountain energy", "green mountain",
    "constellation", "constellation energy",
    "chariot energy", "chariot",
    "pulse power", "pulse",
    "4change energy", "4change",
    "frontier utilities", "frontier",
    "champion energy", "champion",
    "discount power",
    "express energy",
    "first choice power", "first choice",
    "payless power", "payless",
    "pennywise power", "pennywise",
    "rhythm", "rhythm energy",
    "shell energy",
    "trieagle energy", "trieagle",
    "veteran energy",
    "volt electricity", "volt",
    "xoom energy", "xoom",
    "amigo energy", "amigo",
    "bounce energy", "bounce",
    "cirro energy", "cirro",
    "startex power", "startex",
    "stream energy", "stream",
    "tara energy", "tara",
    "just energy",
    "griddy",  # defunct but may appear in old data
    "octopus energy", "octopus",
    "energy texas",  # This is actually a REP despite the name
    "coserv",  # Can be both REP and TDU in some areas
}

# Texas Transmission/Distribution Utilities (TDUs) - WHAT WE WANT
TEXAS_TDUS: Dict[str, list] = {
    "Oncor": ["oncor", "oncor electric delivery", "oncor electric", "oncor electric delivery company"],
    "CenterPoint Energy": ["centerpoint", "centerpoint energy", "cnp", "centerpoint energy houston"],
    "AEP Texas": ["aep texas", "aep texas north", "aep texas central", "aep"],
    "TNMP": ["tnmp", "texas-new mexico power", "texas new mexico power"],
}

# Pennsylvania
PENNSYLVANIA_REPS: Set[str] = {
    "direct energy",
    "constellation",
    "just energy",
    "verde energy",
    "tomorrow energy",
    "north american power",
    "spark energy",
    "xoom energy",
}

PENNSYLVANIA_TDUS: Dict[str, list] = {
    "PECO": ["peco", "peco energy"],
    "PPL Electric": ["ppl", "ppl electric", "ppl electric utilities"],
    "Duquesne Light": ["duquesne", "duquesne light", "duquesne light company"],
    "FirstEnergy": ["firstenergy", "met-ed", "penelec", "west penn power"],
}

# Ohio
OHIO_REPS: Set[str] = {
    "direct energy",
    "constellation",
    "igs energy",
    "just energy",
    "spark energy",
}

OHIO_TDUS: Dict[str, list] = {
    "AEP Ohio": ["aep ohio", "aep", "ohio power"],
    "Duke Energy Ohio": ["duke energy ohio", "duke energy"],
    "FirstEnergy Ohio": ["firstenergy", "ohio edison", "the illuminating company", "toledo edison"],
    "Dayton Power & Light": ["dayton power", "dp&l", "aes ohio"],
}

# Illinois
ILLINOIS_REPS: Set[str] = {
    "direct energy",
    "constellation",
    "just energy",
    "spark energy",
    "verde energy",
}

ILLINOIS_TDUS: Dict[str, list] = {
    "ComEd": ["comed", "commonwealth edison"],
    "Ameren Illinois": ["ameren", "ameren illinois", "ameren il"],
}

# New York
NEW_YORK_REPS: Set[str] = {
    "direct energy",
    "constellation",
    "just energy",
    "esco",  # Generic term for NY ESCOs
}

NEW_YORK_TDUS: Dict[str, list] = {
    "Con Edison": ["con edison", "coned", "consolidated edison"],
    "National Grid": ["national grid"],
    "NYSEG": ["nyseg", "new york state electric & gas"],
    "Central Hudson": ["central hudson"],
    "Orange & Rockland": ["orange and rockland", "o&r"],
}

# All deregulated states
DEREGULATED_STATES = {"TX", "PA", "OH", "IL", "NY", "NJ", "MD", "CT", "MA", "ME", "NH", "RI", "DE", "DC"}

# Mapping of state to REP set
STATE_REPS = {
    "TX": TEXAS_REPS,
    "PA": PENNSYLVANIA_REPS,
    "OH": OHIO_REPS,
    "IL": ILLINOIS_REPS,
    "NY": NEW_YORK_REPS,
}

# Mapping of state to TDU dict
STATE_TDUS = {
    "TX": TEXAS_TDUS,
    "PA": PENNSYLVANIA_TDUS,
    "OH": OHIO_TDUS,
    "IL": ILLINOIS_TDUS,
    "NY": NEW_YORK_TDUS,
}


def is_deregulated_state(state: str) -> bool:
    """Check if state has deregulated electricity market."""
    return state.upper() in DEREGULATED_STATES


def is_retail_provider(utility_name: str, state: str) -> bool:
    """
    Check if this is a retail provider (REP), not the TDU we want.
    
    Args:
        utility_name: Name reported by tenant
        state: Two-letter state code
        
    Returns:
        True if this is a REP (not the infrastructure owner)
    """
    if not utility_name or not state:
        return False
    
    state = state.upper()
    name_lower = utility_name.lower().strip()
    
    reps = STATE_REPS.get(state, set())
    return name_lower in reps or any(rep in name_lower for rep in reps if len(rep) > 4)


def is_tdu(utility_name: str, state: str) -> bool:
    """
    Check if this is a TDU (transmission/distribution utility).
    
    Args:
        utility_name: Name to check
        state: Two-letter state code
        
    Returns:
        True if this is a TDU
    """
    if not utility_name or not state:
        return False
    
    state = state.upper()
    name_lower = utility_name.lower().strip()
    
    tdus = STATE_TDUS.get(state, {})
    for canonical, aliases in tdus.items():
        if name_lower in aliases or any(alias in name_lower for alias in aliases):
            return True
    
    return False


def get_canonical_tdu(utility_name: str, state: str) -> Optional[str]:
    """
    Get the canonical TDU name if this matches a known TDU.
    
    Args:
        utility_name: Name to check
        state: Two-letter state code
        
    Returns:
        Canonical TDU name or None
    """
    if not utility_name or not state:
        return None
    
    state = state.upper()
    name_lower = utility_name.lower().strip()
    
    tdus = STATE_TDUS.get(state, {})
    for canonical, aliases in tdus.items():
        if name_lower in aliases or any(alias in name_lower for alias in aliases):
            return canonical
    
    return None


def classify_utility(utility_name: str, state: str) -> Dict:
    """
    Classify a utility as REP, TDU, or unknown.
    
    Args:
        utility_name: Name reported by tenant
        state: Two-letter state code
        
    Returns:
        {
            "type": "rep" | "tdu" | "unknown",
            "canonical_name": str or None,
            "is_deregulated_state": bool
        }
    """
    if not utility_name:
        return {"type": "unknown", "canonical_name": None, "is_deregulated_state": False}
    
    state = state.upper() if state else ""
    is_dereg = is_deregulated_state(state)
    
    if is_retail_provider(utility_name, state):
        return {
            "type": "rep",
            "canonical_name": utility_name.strip().title(),
            "is_deregulated_state": is_dereg
        }
    
    tdu_name = get_canonical_tdu(utility_name, state)
    if tdu_name:
        return {
            "type": "tdu",
            "canonical_name": tdu_name,
            "is_deregulated_state": is_dereg
        }
    
    return {
        "type": "unknown",
        "canonical_name": utility_name.strip().title(),
        "is_deregulated_state": is_dereg
    }


def should_ignore_tenant_mismatch(tenant_utility: str, our_utility: str, state: str) -> bool:
    """
    Check if a tenant vs API mismatch should be ignored because it's REP vs TDU.
    
    Args:
        tenant_utility: What tenant reported
        our_utility: What our API returned
        state: Two-letter state code
        
    Returns:
        True if this is a REP vs TDU situation (not a real mismatch)
    """
    if not is_deregulated_state(state):
        return False
    
    tenant_class = classify_utility(tenant_utility, state)
    our_class = classify_utility(our_utility, state)
    
    # If tenant reported REP and we returned TDU, that's expected
    if tenant_class["type"] == "rep" and our_class["type"] == "tdu":
        return True
    
    # If both are TDUs but different names for same utility
    if tenant_class["type"] == "tdu" and our_class["type"] == "tdu":
        if tenant_class["canonical_name"] == our_class["canonical_name"]:
            return True
    
    return False


# Test function
def _test():
    test_cases = [
        ("TXU Energy", "TX", "rep"),
        ("Oncor", "TX", "tdu"),
        ("Reliant", "TX", "rep"),
        ("CenterPoint Energy", "TX", "tdu"),
        ("PECO", "PA", "tdu"),
        ("Direct Energy", "PA", "rep"),
        ("Duke Energy", "NC", "unknown"),  # NC is not deregulated
        ("ComEd", "IL", "tdu"),
        ("Energy Texas", "TX", "rep"),
    ]
    
    print("Testing deregulated market handler:")
    for utility, state, expected_type in test_cases:
        result = classify_utility(utility, state)
        status = "✓" if result["type"] == expected_type else "✗"
        print(f"  {status} '{utility}' ({state}) -> {result['type']} (expected: {expected_type})")
    
    print("\nTesting REP vs TDU mismatch detection:")
    mismatch_cases = [
        ("TXU Energy", "Oncor", "TX", True),  # REP vs TDU - should ignore
        ("Reliant", "CenterPoint Energy", "TX", True),  # REP vs TDU - should ignore
        ("Duke Energy", "Georgia Power", "GA", False),  # Not deregulated - real mismatch
        ("PECO", "PPL Electric", "PA", False),  # Both TDUs but different - real mismatch
    ]
    
    for tenant, ours, state, expected in mismatch_cases:
        result = should_ignore_tenant_mismatch(tenant, ours, state)
        status = "✓" if result == expected else "✗"
        print(f"  {status} '{tenant}' vs '{ours}' ({state}) -> ignore={result} (expected: {expected})")


if __name__ == "__main__":
    _test()
