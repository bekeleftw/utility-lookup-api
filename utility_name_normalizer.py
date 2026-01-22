#!/usr/bin/env python3
"""
Utility Name Normalizer

Converts utility name variants to canonical forms for consistent comparison.
This MUST be used before any tenant data analysis or comparison.
"""

import re
from typing import Optional

# Canonical name -> list of known aliases
UTILITY_ALIASES = {
    # Major IOUs - Electric
    "Duke Energy": [
        "Duke Energy Carolinas",
        "Duke Energy Corporation", 
        "Duke Energy Progress",
        "Duke Energy Florida",
        "Duke Energy Indiana",
        "Duke Energy Ohio",
        "Duke Energy Kentucky",
        "Duke Power",
    ],
    "PG&E": [
        "Pacific Gas & Electric",
        "Pacific Gas and Electric",
        "Pacific Gas and Electric Company",
        "PG&E Corporation",
        "Pacific Gas & Electric Company",
    ],
    "Southern California Edison": [
        "SCE",
        "SoCal Edison",
        "So Cal Edison",
        "Southern Cal Edison",
    ],
    "SDG&E": [
        "San Diego Gas & Electric",
        "San Diego Gas and Electric",
        "SDGE",
        "San Diego Gas & Electric Company",
    ],
    "Georgia Power": [
        "Georgia Power Company",
        "Georgia Power Co",
        "GA Power",
    ],
    "Florida Power & Light": [
        "FPL",
        "Florida Power and Light",
        "FP&L",
        "Florida Power & Light Company",
    ],
    "Dominion Energy": [
        "Dominion Virginia Power",
        "Dominion Virginia Power - VA",
        "Dominion Energy Virginia",
        "Dominion",
    ],
    "Xcel Energy": [
        "Xcel",
        "Northern States Power",
        "NSP",
    ],
    "Entergy": [
        "Entergy Louisiana",
        "Entergy Texas",
        "Entergy Arkansas",
        "Entergy Mississippi",
        "Entergy New Orleans",
    ],
    "AEP": [
        "American Electric Power",
        "AEP Ohio",
        "AEP Texas",
        "AEP (OHIO)",
        "AEP Texas North",
        "AEP Texas Central",
    ],
    "Ameren": [
        "Ameren Illinois",
        "Ameren IL",
        "Ameren Missouri",
        "Ameren MO",
        "Ameren Corporation",
    ],
    "ComEd": [
        "Commonwealth Edison",
        "Commonwealth Edison (ComEd)",
        "Com Ed",
    ],
    "Con Edison": [
        "Consolidated Edison",
        "ConEd",
        "Con Ed",
        "Consolidated Edison Company of New York",
    ],
    "National Grid": [
        "National Grid USA",
        "KeySpan",
    ],
    "Eversource": [
        "Eversource Energy",
        "Eversource, CT",
        "NSTAR",
        "YANKEE GAS SERVICE CO (EVERSOURCE)",
    ],
    "PSEG": [
        "PSE&G",
        "Public Service Electric and Gas",
        "Public Service Electric & Gas",
        "PSE&G (Public Service Electric and Gas) - NJ",
    ],
    "PPL Electric": [
        "PPL",
        "PPL Electric Utilities",
        "Pennsylvania Power & Light",
    ],
    "We Energies": [
        "Wisconsin Energy",
        "Wisconsin Electric Power",
    ],
    "DTE Energy": [
        "DTE",
        "Detroit Edison",
    ],
    "Consumers Energy": [
        "Consumers Power",
    ],
    "Puget Sound Energy": [
        "PSE",
        "Puget Power",
    ],
    "Portland General Electric": [
        "PGE",
        "Portland General Electric - PGE",
    ],
    "PacifiCorp": [
        "Pacific Power",
        "PacifiCorp (Pacific Power)",
        "Rocky Mountain Power",
    ],
    "Salt River Project": [
        "SRP",
        "Salt River Project (SRP)",
    ],
    "Arizona Public Service": [
        "APS",
        "Arizona Public Service (APS)",
        "Arizona Public Service Co",
    ],
    "NV Energy": [
        "Nevada Power",
        "Sierra Pacific Power",
    ],
    "CPS Energy": [
        "City Public Service",
        "CPS",
    ],
    "Austin Energy": [
        "City of Austin Utilities",
        "City of Austin",
        "Austin Utilities",
    ],
    "OUC": [
        "Orlando Utilities Commission",
        "Orlando Utilities Commission (OUC)",
    ],
    "JEA": [
        "JEA - FL",
        "Jacksonville Electric Authority",
    ],
    "TECO Energy": [
        "Tampa Electric",
        "Tampa Electric Company",
        "Tampa Electric Co",
    ],
    
    # Texas TDUs
    "Oncor": [
        "Oncor Electric Delivery",
        "Oncor Electric",
        "Oncor Electric Delivery Company",
    ],
    "CenterPoint Energy": [
        "CenterPoint",
        "CNP",
        "CenterPoint Energy Houston Electric",
    ],
    "TNMP": [
        "Texas-New Mexico Power",
        "Texas New Mexico Power",
        "Texas-New Mexico Power Company",
    ],
    
    # Gas Utilities
    "Atmos Energy": [
        "Atmos Energy Corporation",
        "Atmos",
    ],
    "Piedmont Natural Gas": [
        "Piedmont Gas",
        "Piedmont NG",
    ],
    "Spire": [
        "Spire Energy",
        "Laclede Gas",
        "Spire Missouri",
    ],
    "NiSource": [
        "Columbia Gas",
        "NIPSCO",
    ],
    "Southern Company Gas": [
        "Atlanta Gas Light",
        "Nicor Gas",
        "Virginia Natural Gas",
    ],
    
    # Co-ops (common ones)
    "Pedernales Electric Cooperative": [
        "PEC",
        "Pedernales Electric",
        "PECO Electric",  # Note: different from PECO in PA
    ],
    "Jackson EMC": [
        "Jackson EMC - GA",
        "Jackson Electric Membership Corporation",
    ],
    "Energy United": [
        "EnergyUnited",
        "Energy United EMC",
    ],
}

# Build reverse lookup for efficiency
_ALIAS_TO_CANONICAL = {}
for canonical, aliases in UTILITY_ALIASES.items():
    _ALIAS_TO_CANONICAL[canonical.lower()] = canonical
    for alias in aliases:
        _ALIAS_TO_CANONICAL[alias.lower()] = canonical


def normalize_utility_name(name: str) -> Optional[str]:
    """
    Convert any utility name variant to its canonical form.
    
    Args:
        name: Raw utility name from tenant data or other source
        
    Returns:
        Canonical utility name, or cleaned original if no match found
    """
    if not name:
        return None
    
    # Clean up the name
    name_clean = name.strip()
    name_lower = name_clean.lower()
    
    # Remove common suffixes that don't affect identity
    name_lower = re.sub(r'\s*-\s*[a-z]{2}\s*$', '', name_lower)  # " - TX", " - CA"
    name_lower = re.sub(r'\s*\([a-z]{2}\)\s*$', '', name_lower)  # " (TX)", " (CA)"
    name_lower = re.sub(r',?\s*(inc\.?|llc|corp\.?|corporation|company|co\.?)$', '', name_lower)
    name_lower = name_lower.strip()
    
    # Direct lookup
    if name_lower in _ALIAS_TO_CANONICAL:
        return _ALIAS_TO_CANONICAL[name_lower]
    
    # Partial match - check if any alias is contained in the name
    for alias_lower, canonical in _ALIAS_TO_CANONICAL.items():
        if len(alias_lower) > 5:  # Only match on longer aliases to avoid false positives
            if alias_lower in name_lower or name_lower in alias_lower:
                return canonical
    
    # No match found - return cleaned original with title case
    return name_clean.title() if name_clean else None


def utilities_match(name1: str, name2: str) -> bool:
    """
    Check if two utility names refer to the same utility.
    
    Args:
        name1: First utility name
        name2: Second utility name
        
    Returns:
        True if they're the same utility, False otherwise
    """
    if not name1 or not name2:
        return False
    
    norm1 = normalize_utility_name(name1)
    norm2 = normalize_utility_name(name2)
    
    if norm1 == norm2:
        return True
    
    # Also check if one contains the other after normalization
    if norm1 and norm2:
        n1_lower = norm1.lower()
        n2_lower = norm2.lower()
        if n1_lower in n2_lower or n2_lower in n1_lower:
            return True
    
    return False


def get_canonical_name(name: str) -> Optional[str]:
    """Alias for normalize_utility_name for clarity."""
    return normalize_utility_name(name)


# Test function
def _test():
    test_cases = [
        ("Duke Energy Carolinas", "Duke Energy"),
        ("duke energy corporation", "Duke Energy"),
        ("PG&E", "PG&E"),
        ("Pacific Gas & Electric", "PG&E"),
        ("Georgia Power Company", "Georgia Power"),
        ("FPL", "Florida Power & Light"),
        ("Oncor Electric Delivery", "Oncor"),
        ("Salt River Project (SRP)", "Salt River Project"),
        ("Some Unknown Utility", "Some Unknown Utility"),
        ("Dominion Virginia Power - VA", "Dominion Energy"),
        ("AEP (OHIO)", "AEP"),
    ]
    
    print("Testing utility name normalizer:")
    for input_name, expected in test_cases:
        result = normalize_utility_name(input_name)
        status = "✓" if result == expected else "✗"
        print(f"  {status} '{input_name}' -> '{result}' (expected: '{expected}')")


if __name__ == "__main__":
    _test()
