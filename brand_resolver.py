#!/usr/bin/env python3
"""
Resolve legal utility names to consumer-facing brand names.

Many utilities operate under legal names that differ from what consumers know them as:
- "Wisconsin Electric Power Co" → "WE Energies"
- "Pacific Gas and Electric Company" → "PG&E"
- "Southern California Edison Company" → "SCE"
"""

import json
from pathlib import Path
from typing import Dict, Optional, Tuple

# Load utility directory
UTILITY_DIR_FILE = Path(__file__).parent / "data" / "utility_directory" / "master.json"

# Cache for brand lookups
_brand_cache: Dict[str, Dict] = {}
_alias_to_brand: Dict[str, str] = {}


def _load_utility_directory():
    """Load and index the utility directory for fast lookups."""
    global _brand_cache, _alias_to_brand
    
    if _alias_to_brand:  # Already loaded
        return
    
    try:
        with open(UTILITY_DIR_FILE, 'r') as f:
            data = json.load(f)
        
        for utility in data.get('utilities', []):
            brand_name = utility.get('name', '')
            utility_id = utility.get('id', '')
            
            # Store the full utility info
            _brand_cache[utility_id] = utility
            
            # Index by brand name (lowercase)
            _alias_to_brand[brand_name.lower()] = brand_name
            
            # Index all aliases
            for alias in utility.get('aliases', []):
                _alias_to_brand[alias.lower()] = brand_name
                
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Warning: Could not load utility directory: {e}")


def resolve_brand_name(legal_name: str, state: str = None) -> Tuple[str, Optional[str]]:
    """
    Resolve a legal utility name to its consumer-facing brand name.
    
    Args:
        legal_name: The legal/official name (e.g., "Wisconsin Electric Power Co")
        state: Optional state code to help disambiguate
        
    Returns:
        Tuple of (display_name, legal_name) where:
        - display_name is the consumer-facing brand (e.g., "WE Energies")
        - legal_name is preserved for reference (or None if same as display)
    """
    _load_utility_directory()
    
    if not legal_name:
        return ("Unknown", None)
    
    # Normalize for lookup
    name_lower = legal_name.lower().strip()
    
    # Direct match in aliases
    if name_lower in _alias_to_brand:
        brand = _alias_to_brand[name_lower]
        if brand.lower() != name_lower:
            return (brand, legal_name)
        return (legal_name, None)
    
    # Try partial matching for common patterns
    # Remove common suffixes for matching
    suffixes_to_strip = [
        ' co', ' co.', ' company', ' corp', ' corporation', ' inc', ' inc.',
        ' llc', ' l.l.c.', ' ltd', ' limited', ' lp', ' l.p.'
    ]
    
    normalized = name_lower
    for suffix in suffixes_to_strip:
        if normalized.endswith(suffix):
            normalized = normalized[:-len(suffix)].strip()
            break
    
    # Try matching normalized name
    if normalized in _alias_to_brand:
        brand = _alias_to_brand[normalized]
        return (brand, legal_name)
    
    # Try matching with "the" prefix removed
    if normalized.startswith('the '):
        normalized = normalized[4:]
        if normalized in _alias_to_brand:
            brand = _alias_to_brand[normalized]
            return (brand, legal_name)
    
    # No match found - return original
    return (legal_name, None)


def get_utility_info(name: str) -> Optional[Dict]:
    """Get full utility info by name or alias."""
    _load_utility_directory()
    
    name_lower = name.lower().strip()
    
    if name_lower in _alias_to_brand:
        brand = _alias_to_brand[name_lower]
        # Find the utility with this brand name
        for utility in _brand_cache.values():
            if utility.get('name', '').lower() == brand.lower():
                return utility
    
    return None


def format_utility_name(legal_name: str, include_legal: bool = False) -> str:
    """
    Format a utility name for display.
    
    Args:
        legal_name: The legal/official name
        include_legal: If True, append legal name in parentheses when different
        
    Returns:
        Formatted display name
    """
    brand, legal = resolve_brand_name(legal_name)
    
    if include_legal and legal and legal != brand:
        return f"{brand} ({legal})"
    
    return brand


# Corporate mergers and acquisitions - maps old names to new entities
# Updated as companies merge/rebrand
CORPORATE_MERGERS = {
    # Chesapeake Energy + Southwestern Energy → Expand Energy (Oct 2024)
    "chesapeake energy": "Expand Energy",
    "chesapeake utilities": "Expand Energy",  # Note: Chesapeake Utilities Corp is different, may need verification
    "southwestern energy": "Expand Energy",
    
    # Duke Energy acquisitions
    "progress energy": "Duke Energy",
    # NOTE: Piedmont Natural Gas is owned by Duke but still operates under its own brand for gas
    # Do NOT map piedmont to Duke - they are separate customer-facing brands
    
    # Dominion Energy acquisitions
    "questar": "Dominion Energy",
    "scana": "Dominion Energy",
    
    # WEC Energy Group
    "integrys energy": "WEC Energy Group",
    "peoples gas chicago": "WEC Energy Group",
    
    # Southern Company acquisitions
    "agl resources": "Atlanta Gas Light",
    
    # Berkshire Hathaway Energy
    "midamerican energy": "Berkshire Hathaway Energy",
    "pacificorp": "Berkshire Hathaway Energy",
    "nv energy": "Berkshire Hathaway Energy",
    
    # CenterPoint acquisitions
    "vectren": "CenterPoint Energy",
}

# Common brand mappings that might not be in the directory yet
# Maps legal/official names to consumer-facing brand names
# Format: "legal name (lowercase)": "Consumer Brand"
COMMON_BRAND_MAPPINGS = {
    # Wisconsin - WEC Energy Group subsidiaries
    # WE Energies = Wisconsin Electric + Wisconsin Gas (merged brand)
    "wisconsin electric power co": "WE Energies",
    "wisconsin electric power company": "WE Energies",
    "wisconsin electric": "WE Energies",
    "wisconsin gas co": "WE Energies",
    "wisconsin gas llc": "WE Energies",
    "wisconsin gas": "WE Energies",
    "we energies": "WE Energies",
    # Wisconsin Public Service (separate WEC subsidiary, serves NE Wisconsin)
    "wisconsin public service": "Wisconsin Public Service (WEC Energy)",
    "wisconsin public service corp": "Wisconsin Public Service (WEC Energy)",
    "wps": "Wisconsin Public Service (WEC Energy)",
    # Other WEC subsidiaries
    "peoples gas": "Peoples Gas (WEC Energy)",
    "peoples gas light and coke": "Peoples Gas (WEC Energy)",
    "north shore gas": "North Shore Gas (WEC Energy)",
    "michigan gas utilities": "Michigan Gas Utilities (WEC Energy)",
    "minnesota energy resources": "Minnesota Energy Resources (WEC Energy)",
    
    # California
    "pacific gas and electric": "PG&E",
    "pacific gas & electric": "PG&E",
    "southern california edison": "SCE",
    "southern california gas": "SoCalGas",
    "san diego gas & electric": "SDG&E",
    "san diego gas and electric": "SDG&E",
    
    # Texas
    "oncor electric delivery": "Oncor",
    "centerpoint energy houston electric": "CenterPoint Energy",
    "texas-new mexico power": "TNMP",
    
    # Illinois
    "commonwealth edison": "ComEd",
    "northern illinois gas": "Nicor Gas",
    
    # Florida
    "florida power & light": "FPL",
    "florida power and light": "FPL",
    "tampa electric": "TECO Energy",
    
    # Georgia
    "georgia power company": "Georgia Power",
    "atlanta gas light": "AGL Resources",
    
    # New York
    "consolidated edison": "Con Edison",
    "con edison": "Con Edison",
    "national fuel gas": "National Fuel",
    
    # Ohio
    "duke energy ohio": "Duke Energy",
    "american electric power ohio": "AEP Ohio",
    "firstenergy ohio": "FirstEnergy",
    
    # Pennsylvania
    "peco energy": "PECO",
    "duquesne light": "Duquesne Light",
    "pppl electric utilities": "PPL Electric",
    
    # Arizona
    "arizona public service": "APS",
    "salt river project": "SRP",
    "tucson electric power": "TEP",
    
    # Colorado
    "public service company of colorado": "Xcel Energy",
    "xcel energy colorado": "Xcel Energy",
    
    # Washington
    "puget sound energy": "PSE",
}


def resolve_brand_name_with_fallback(legal_name: str, state: str = None) -> Tuple[str, Optional[str]]:
    """
    Resolve brand name using directory first, then fallback mappings.
    Also handles corporate mergers/acquisitions.
    """
    if not legal_name:
        return ("Unknown", None)
    
    name_lower = legal_name.lower().strip()
    
    # Check corporate mergers first (these take priority as they're most current)
    for old_name, new_name in CORPORATE_MERGERS.items():
        if old_name in name_lower:
            return (new_name, f"{legal_name} (now {new_name})")
    
    # Try directory
    brand, legal = resolve_brand_name(legal_name, state)
    
    # If no match, try fallback mappings
    if legal is None:
        if name_lower in COMMON_BRAND_MAPPINGS:
            return (COMMON_BRAND_MAPPINGS[name_lower], legal_name)
    
    return (brand, legal)


if __name__ == "__main__":
    # Test cases
    test_names = [
        "Wisconsin Electric Power Co",
        "Wisconsin Gas Co",
        "Pacific Gas and Electric",
        "Southern California Edison",
        "Commonwealth Edison",
        "Florida Power & Light",
        "Arizona Public Service",
        "Chesapeake Energy",  # Merged with Southwestern → Expand Energy (Oct 2024)
        "Southwestern Energy",  # Merged → Expand Energy
        "Progress Energy",  # Acquired by Duke Energy
        "Some Unknown Utility",
    ]
    
    print("Brand Name Resolution Tests:")
    print("=" * 60)
    
    for name in test_names:
        brand, legal = resolve_brand_name_with_fallback(name)
        if legal:
            print(f"{name}")
            print(f"  → {brand} (legal: {legal})")
        else:
            print(f"{name}")
            print(f"  → {brand} (no change)")
        print()
