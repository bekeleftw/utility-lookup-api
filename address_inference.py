#!/usr/bin/env python3
"""
Address similarity inference for utility lookups.
If we know utilities for nearby addresses, we can infer for unknown addresses.
"""

import json
import re
from typing import Dict, Optional, List, Tuple
from pathlib import Path
from collections import defaultdict


# Cache of verified address-utility mappings
VERIFIED_CACHE_FILE = Path(__file__).parent / "data" / "verified_addresses.json"

_verified_cache = None


def load_verified_cache() -> Dict:
    """Load cache of verified address-utility mappings."""
    global _verified_cache
    
    if _verified_cache is not None:
        return _verified_cache
    
    if VERIFIED_CACHE_FILE.exists():
        try:
            with open(VERIFIED_CACHE_FILE, 'r') as f:
                _verified_cache = json.load(f)
        except (json.JSONDecodeError, IOError):
            _verified_cache = {"addresses": {}, "streets": {}}
    else:
        _verified_cache = {"addresses": {}, "streets": {}}
    
    return _verified_cache


def save_verified_cache(cache: Dict) -> None:
    """Save verified address cache."""
    try:
        VERIFIED_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(VERIFIED_CACHE_FILE, 'w') as f:
            json.dump(cache, f, indent=2)
    except IOError:
        pass


def parse_street_address(address: str) -> Optional[Dict]:
    """
    Parse a street address into components.
    Returns street number, street name, city, state, zip.
    """
    if not address:
        return None
    
    address = address.upper().strip()
    
    # Try to extract house number
    number_match = re.match(r'^(\d+[-\d]*)\s+', address)
    if not number_match:
        return None
    
    street_number = number_match.group(1)
    rest = address[number_match.end():]
    
    # Split by comma
    parts = [p.strip() for p in rest.split(',')]
    
    street_name = parts[0] if parts else None
    city = parts[1] if len(parts) > 1 else None
    
    # Extract state and ZIP from last parts
    state = None
    zip_code = None
    
    if len(parts) >= 2:
        last_part = parts[-1]
        # Look for ZIP
        zip_match = re.search(r'\b(\d{5})(?:-\d{4})?\b', last_part)
        if zip_match:
            zip_code = zip_match.group(1)
        
        # Look for state
        state_match = re.search(r'\b([A-Z]{2})\b', last_part)
        if state_match:
            state = state_match.group(1)
    
    # Normalize street name
    if street_name:
        # Remove common suffixes for matching
        street_name = re.sub(r'\s+(ST|STREET|AVE|AVENUE|BLVD|BOULEVARD|DR|DRIVE|RD|ROAD|LN|LANE|CT|COURT|WAY|PL|PLACE|CIR|CIRCLE)\.?$', '', street_name)
    
    return {
        "number": street_number,
        "street": street_name,
        "city": city,
        "state": state,
        "zip": zip_code,
        "original": address
    }


def get_street_key(parsed: Dict) -> str:
    """Generate a key for street-level grouping."""
    if not parsed:
        return ""
    
    parts = []
    if parsed.get("street"):
        parts.append(parsed["street"])
    if parsed.get("city"):
        parts.append(parsed["city"])
    if parsed.get("state"):
        parts.append(parsed["state"])
    if parsed.get("zip"):
        parts.append(parsed["zip"])
    
    return "|".join(parts)


def add_verified_address(
    address: str,
    electric: str = None,
    gas: str = None,
    water: str = None,
    source: str = "user_verified"
) -> None:
    """
    Add a verified address-utility mapping to the cache.
    """
    cache = load_verified_cache()
    
    parsed = parse_street_address(address)
    if not parsed:
        return
    
    # Store by full address
    address_key = address.upper().strip()
    cache["addresses"][address_key] = {
        "electric": electric,
        "gas": gas,
        "water": water,
        "source": source,
        "parsed": parsed
    }
    
    # Also index by street for inference
    street_key = get_street_key(parsed)
    if street_key:
        if street_key not in cache["streets"]:
            cache["streets"][street_key] = []
        
        cache["streets"][street_key].append({
            "number": parsed["number"],
            "electric": electric,
            "gas": gas,
            "water": water
        })
    
    save_verified_cache(cache)


def find_nearby_verified_addresses(
    address: str,
    within_numbers: int = 20
) -> List[Dict]:
    """
    Find verified addresses on the same street within a range of house numbers.
    """
    cache = load_verified_cache()
    
    parsed = parse_street_address(address)
    if not parsed or not parsed.get("number"):
        return []
    
    try:
        target_number = int(re.sub(r'[^\d]', '', parsed["number"]))
    except ValueError:
        return []
    
    street_key = get_street_key(parsed)
    if not street_key or street_key not in cache.get("streets", {}):
        return []
    
    nearby = []
    for entry in cache["streets"][street_key]:
        try:
            entry_number = int(re.sub(r'[^\d]', '', entry["number"]))
            if abs(entry_number - target_number) <= within_numbers:
                nearby.append({
                    "number": entry["number"],
                    "distance": abs(entry_number - target_number),
                    "electric": entry.get("electric"),
                    "gas": entry.get("gas"),
                    "water": entry.get("water")
                })
        except ValueError:
            continue
    
    # Sort by distance
    nearby.sort(key=lambda x: x["distance"])
    
    return nearby


def infer_utility_from_nearby(
    address: str,
    utility_type: str,
    min_matches: int = 3,
    within_numbers: int = 20
) -> Optional[Dict]:
    """
    Infer utility for an address based on nearby verified addresses.
    
    Args:
        address: Address to infer utility for
        utility_type: 'electric', 'gas', or 'water'
        min_matches: Minimum number of nearby addresses needed
        within_numbers: House number range to search
    
    Returns:
        Inference result or None if not enough data
    """
    nearby = find_nearby_verified_addresses(address, within_numbers)
    
    if len(nearby) < min_matches:
        return None
    
    # Count utility occurrences
    utility_counts = defaultdict(int)
    for entry in nearby:
        utility = entry.get(utility_type)
        if utility:
            utility_counts[utility] += 1
    
    if not utility_counts:
        return None
    
    # Find most common utility
    most_common = max(utility_counts.items(), key=lambda x: x[1])
    utility_name, count = most_common
    
    # Calculate agreement percentage
    total_with_data = sum(utility_counts.values())
    agreement = count / total_with_data if total_with_data > 0 else 0
    
    # Only infer if high agreement
    if agreement < 0.8:  # 80% agreement threshold
        return None
    
    confidence = "high" if agreement >= 0.9 and count >= 5 else "medium"
    
    return {
        "inferred": True,
        "utility": utility_name,
        "utility_type": utility_type,
        "confidence": confidence,
        "method": "nearby_address_inference",
        "supporting_addresses": count,
        "total_nearby": len(nearby),
        "agreement_rate": agreement,
        "note": f"Inferred from {count} nearby addresses on same street"
    }


def infer_all_utilities(address: str) -> Dict:
    """
    Try to infer all utility types for an address.
    """
    results = {}
    
    for utility_type in ["electric", "gas", "water"]:
        inference = infer_utility_from_nearby(address, utility_type)
        if inference:
            results[utility_type] = inference
    
    return results


def get_street_utility_summary(street: str, city: str, state: str) -> Dict:
    """
    Get a summary of utilities for a street.
    Useful for understanding coverage and patterns.
    """
    cache = load_verified_cache()
    
    # Build street key
    street_key = f"{street.upper()}|{city.upper()}|{state.upper()}"
    
    # Also try with ZIP variations
    matching_keys = [k for k in cache.get("streets", {}).keys() if k.startswith(f"{street.upper()}|{city.upper()}")]
    
    if not matching_keys:
        return {"found": False}
    
    all_entries = []
    for key in matching_keys:
        all_entries.extend(cache["streets"][key])
    
    if not all_entries:
        return {"found": False}
    
    # Summarize utilities
    electric_counts = defaultdict(int)
    gas_counts = defaultdict(int)
    water_counts = defaultdict(int)
    
    for entry in all_entries:
        if entry.get("electric"):
            electric_counts[entry["electric"]] += 1
        if entry.get("gas"):
            gas_counts[entry["gas"]] += 1
        if entry.get("water"):
            water_counts[entry["water"]] += 1
    
    return {
        "found": True,
        "address_count": len(all_entries),
        "electric": dict(electric_counts),
        "gas": dict(gas_counts),
        "water": dict(water_counts),
        "primary_electric": max(electric_counts.items(), key=lambda x: x[1])[0] if electric_counts else None,
        "primary_gas": max(gas_counts.items(), key=lambda x: x[1])[0] if gas_counts else None,
        "primary_water": max(water_counts.items(), key=lambda x: x[1])[0] if water_counts else None
    }


if __name__ == "__main__":
    print("Address Inference Tests:")
    print("=" * 60)
    
    # Add some test verified addresses
    print("\n1. Adding verified addresses...")
    test_addresses = [
        ("100 Main St, Austin, TX 78701", "Austin Energy", "Texas Gas Service", "Austin Water"),
        ("102 Main St, Austin, TX 78701", "Austin Energy", "Texas Gas Service", "Austin Water"),
        ("104 Main St, Austin, TX 78701", "Austin Energy", "Texas Gas Service", "Austin Water"),
        ("106 Main St, Austin, TX 78701", "Austin Energy", "Texas Gas Service", "Austin Water"),
        ("108 Main St, Austin, TX 78701", "Austin Energy", "Texas Gas Service", "Austin Water"),
    ]
    
    for addr, elec, gas, water in test_addresses:
        add_verified_address(addr, elec, gas, water, "test")
        print(f"   Added: {addr}")
    
    # Test inference
    print("\n2. Testing inference for 110 Main St...")
    test_addr = "110 Main St, Austin, TX 78701"
    
    nearby = find_nearby_verified_addresses(test_addr)
    print(f"   Found {len(nearby)} nearby addresses")
    
    inference = infer_all_utilities(test_addr)
    for utility_type, result in inference.items():
        print(f"   {utility_type}: {result.get('utility')} (confidence: {result.get('confidence')})")
    
    # Test street summary
    print("\n3. Street summary for Main St, Austin:")
    summary = get_street_utility_summary("Main St", "Austin", "TX")
    print(f"   Addresses: {summary.get('address_count')}")
    print(f"   Primary electric: {summary.get('primary_electric')}")
