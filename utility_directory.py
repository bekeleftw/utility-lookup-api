#!/usr/bin/env python3
"""
Utility directory for matching and verification.
Provides fuzzy matching of utility names to canonical entries.
"""

import json
import os
import re
from typing import Dict, List, Optional
from pathlib import Path

DIRECTORY_FILE = Path(__file__).parent / "data" / "utility_directory" / "master.json"

_directory_cache = None


def load_directory() -> Dict:
    """Load the utility directory."""
    global _directory_cache
    
    if _directory_cache is not None:
        return _directory_cache
    
    if not DIRECTORY_FILE.exists():
        return {"utilities": []}
    
    with open(DIRECTORY_FILE, 'r') as f:
        _directory_cache = json.load(f)
    
    return _directory_cache


def normalize_utility_name(name: str) -> str:
    """Normalize a utility name for matching."""
    if not name:
        return ""
    
    name = name.upper().strip()
    
    # Remove common suffixes
    suffixes = [
        ' INC', ' INC.', ' LLC', ' CORP', ' CORPORATION', ' COMPANY', ' CO',
        ' CO.', ' UTILITY', ' UTILITIES', ' ELECTRIC', ' ENERGY', ' GAS',
        ' WATER', ' DEPARTMENT', ' DEPT', ' DIVISION', ' DIV', ' SERVICE',
        ' SERVICES', ' AUTHORITY', ' DISTRICT', ' SYSTEM', ' SYSTEMS',
        ' DELIVERY', ' POWER', ' LIGHT', ' LT', ' & COKE', ' AND POWER',
    ]
    
    for suffix in suffixes:
        if name.endswith(suffix):
            name = name[:-len(suffix)].strip()
    
    # Remove punctuation
    name = re.sub(r'[.,&]+', ' ', name)
    name = re.sub(r'\s+', ' ', name).strip()
    
    return name


def match_utility(name: str, utility_type: str = None, state: str = None) -> Optional[Dict]:
    """
    Match a utility name to a canonical entry in the directory.
    
    Args:
        name: Utility name to match
        utility_type: Optional filter by type (electric, gas, water)
        state: Optional filter by state
    
    Returns:
        Matching utility entry or None
    """
    if not name:
        return None
    
    directory = load_directory()
    utilities = directory.get("utilities", [])
    
    # Filter by type and state if specified
    if utility_type:
        utilities = [u for u in utilities if u.get("type") == utility_type]
    if state:
        state = state.upper()
        utilities = [u for u in utilities 
                    if u.get("service_area", {}).get("state") == state]
    
    normalized_input = normalize_utility_name(name)
    
    best_match = None
    best_score = 0
    
    for utility in utilities:
        # Check main name
        normalized_name = normalize_utility_name(utility.get("name", ""))
        score = _calculate_match_score(normalized_input, normalized_name)
        
        if score > best_score:
            best_score = score
            best_match = utility
        
        # Check aliases
        for alias in utility.get("aliases", []):
            normalized_alias = normalize_utility_name(alias)
            score = _calculate_match_score(normalized_input, normalized_alias)
            
            if score > best_score:
                best_score = score
                best_match = utility
    
    # Require minimum match score
    if best_score >= 0.7:
        return best_match
    
    return None


def _calculate_match_score(name1: str, name2: str) -> float:
    """Calculate similarity score between two normalized names."""
    if not name1 or not name2:
        return 0.0
    
    # Exact match
    if name1 == name2:
        return 1.0
    
    # One contains the other
    if name1 in name2:
        return 0.9
    if name2 in name1:
        return 0.85
    
    # Word overlap
    words1 = set(name1.split())
    words2 = set(name2.split())
    
    if not words1 or not words2:
        return 0.0
    
    # Remove common words
    common_words = {'THE', 'OF', 'AND', 'CITY', 'COUNTY', 'PUBLIC', 'MUNICIPAL'}
    words1 = words1 - common_words
    words2 = words2 - common_words
    
    if not words1 or not words2:
        return 0.5  # Only had common words
    
    overlap = len(words1 & words2)
    total = len(words1 | words2)
    
    return overlap / total if total > 0 else 0.0


def get_utility_by_id(utility_id: str) -> Optional[Dict]:
    """Get a utility by its ID."""
    directory = load_directory()
    
    for utility in directory.get("utilities", []):
        if utility.get("id") == utility_id:
            return utility
    
    return None


def get_utilities_by_state(state: str, utility_type: str = None) -> List[Dict]:
    """Get all utilities serving a state."""
    directory = load_directory()
    state = state.upper()
    
    results = []
    for utility in directory.get("utilities", []):
        service_area = utility.get("service_area", {})
        if service_area.get("state") == state:
            if utility_type is None or utility.get("type") == utility_type:
                results.append(utility)
    
    return results


def get_utilities_by_city(city: str, state: str, utility_type: str = None) -> List[Dict]:
    """Get utilities serving a specific city."""
    directory = load_directory()
    city = city.upper()
    state = state.upper()
    
    results = []
    for utility in directory.get("utilities", []):
        service_area = utility.get("service_area", {})
        
        if service_area.get("state") != state:
            continue
        
        if utility_type and utility.get("type") != utility_type:
            continue
        
        # Check if city is in service area
        cities = [c.upper() for c in service_area.get("cities", [])]
        if city in cities:
            results.append(utility)
        elif service_area.get("type") == "territory":
            # Territory-based utilities might serve the city
            results.append(utility)
    
    return results


def enrich_utility_result(result: Dict, utility_type: str, state: str = None) -> Dict:
    """
    Enrich a utility lookup result with directory data.
    Adds phone, website, and canonical name if found.
    """
    if not result:
        return result
    
    name = result.get("NAME") or result.get("name")
    if not name:
        return result
    
    match = match_utility(name, utility_type, state)
    
    if match:
        # Add canonical info
        result["_canonical_name"] = match.get("name")
        result["_canonical_id"] = match.get("id")
        
        # Add contact info if missing
        if not result.get("TELEPHONE") and not result.get("phone"):
            phone_info = match.get("phone", {})
            result["phone"] = phone_info.get("customer_service")
        
        if not result.get("WEBSITE") and not result.get("website"):
            result["website"] = match.get("website")
        
        # Add ownership type
        result["_ownership"] = match.get("ownership")
        
        # Boost confidence if matched to directory
        result["_directory_match"] = True
    
    return result


if __name__ == "__main__":
    # Test matching
    test_names = [
        ("Austin Energy", "electric", "TX"),
        ("PACIFIC GAS AND ELECTRIC COMPANY", "electric", "CA"),
        ("PG&E", "gas", "CA"),
        ("Southern California Gas Co", "gas", "CA"),
        ("Texas Gas Service Company", "gas", "TX"),
        ("LADWP", "water", "CA"),
        ("Denver Water Board", "water", "CO"),
    ]
    
    print("Utility Directory Matching Tests:")
    print("=" * 60)
    
    for name, utype, state in test_names:
        match = match_utility(name, utype, state)
        if match:
            print(f"\n'{name}' -> {match.get('name')}")
            print(f"  ID: {match.get('id')}")
            print(f"  Phone: {match.get('phone', {}).get('customer_service')}")
        else:
            print(f"\n'{name}' -> NO MATCH")
