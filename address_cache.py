"""
Address-level caching for utility lookups.
Stores confirmed utility mappings to improve accuracy over time.
"""

import json
import os
import hashlib
from datetime import datetime
from typing import Optional, Dict, List
from pathlib import Path

CACHE_FILE = Path(__file__).parent / "data" / "address_cache.json"
_cache = None


def _normalize_address(address: str) -> str:
    """Normalize address for consistent cache keys."""
    # Remove extra whitespace, lowercase, standardize abbreviations
    addr = address.upper().strip()
    # Standardize common abbreviations
    replacements = {
        ' STREET': ' ST',
        ' AVENUE': ' AVE',
        ' BOULEVARD': ' BLVD',
        ' DRIVE': ' DR',
        ' ROAD': ' RD',
        ' LANE': ' LN',
        ' COURT': ' CT',
        ' PLACE': ' PL',
        ' CIRCLE': ' CIR',
        ' APARTMENT': ' APT',
        ' SUITE': ' STE',
        ' UNIT': ' UNIT',
        ', ': ',',
        '  ': ' ',
    }
    for old, new in replacements.items():
        addr = addr.replace(old, new)
    return addr


def _get_cache_key(address: str) -> str:
    """Generate cache key from normalized address."""
    normalized = _normalize_address(address)
    return hashlib.md5(normalized.encode()).hexdigest()[:16]


def _get_zip_key(address: str) -> Optional[str]:
    """Extract ZIP code from address for nearby lookups."""
    import re
    match = re.search(r'\b(\d{5})(?:-\d{4})?\b', address)
    return match.group(1) if match else None


def load_cache() -> Dict:
    """Load address cache from disk."""
    global _cache
    if _cache is None:
        if CACHE_FILE.exists():
            try:
                with open(CACHE_FILE, 'r') as f:
                    _cache = json.load(f)
            except (json.JSONDecodeError, IOError):
                _cache = {"addresses": {}, "by_zip": {}, "_metadata": {}}
        else:
            _cache = {
                "addresses": {},
                "by_zip": {},
                "_metadata": {
                    "created": datetime.now().isoformat(),
                    "description": "User-confirmed utility mappings"
                }
            }
    return _cache


def save_cache():
    """Save address cache to disk."""
    global _cache
    if _cache:
        _cache["_metadata"]["last_updated"] = datetime.now().isoformat()
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, 'w') as f:
            json.dump(_cache, f, indent=2)


def get_cached_utilities(address: str) -> Optional[Dict]:
    """
    Look up cached utilities for an address.
    
    Returns:
        Dict with electric, gas, water if found, None otherwise
    """
    cache = load_cache()
    cache_key = _get_cache_key(address)
    
    # Direct address match
    if cache_key in cache["addresses"]:
        entry = cache["addresses"][cache_key]
        if entry.get("confirmation_count", 0) >= 1:
            return {
                "electric": entry.get("electric"),
                "gas": entry.get("gas"),
                "water": entry.get("water"),
                "_source": "address_cache",
                "_confidence": "verified" if entry.get("confirmation_count", 0) >= 3 else "high",
                "_confirmations": entry.get("confirmation_count", 0)
            }
    
    return None


def get_cached_by_zip(zip_code: str, utility_type: str) -> Optional[Dict]:
    """
    Look up most common utility for a ZIP code based on cached confirmations.
    
    Args:
        zip_code: 5-digit ZIP
        utility_type: 'electric', 'gas', or 'water'
    
    Returns:
        Utility info if enough confirmations exist, None otherwise
    """
    cache = load_cache()
    
    if zip_code not in cache.get("by_zip", {}):
        return None
    
    zip_data = cache["by_zip"][zip_code]
    type_data = zip_data.get(utility_type, {})
    
    if not type_data:
        return None
    
    # Find utility with most confirmations
    best_utility = None
    best_count = 0
    
    for utility_name, data in type_data.items():
        count = data.get("confirmation_count", 0)
        if count > best_count:
            best_count = count
            best_utility = {
                "name": utility_name,
                "phone": data.get("phone"),
                "website": data.get("website"),
                "confirmation_count": count
            }
    
    # Only return if we have enough confirmations
    if best_utility and best_count >= 2:
        return {
            **best_utility,
            "_source": "zip_cache",
            "_confidence": "high" if best_count >= 5 else "medium"
        }
    
    return None


def cache_confirmation(
    address: str,
    utility_type: str,
    utility_name: str,
    phone: str = None,
    website: str = None,
    zip_code: str = None
):
    """
    Cache a user confirmation for a utility.
    
    Args:
        address: Full address
        utility_type: 'electric', 'gas', or 'water'
        utility_name: Name of the utility
        phone: Utility phone number
        website: Utility website
        zip_code: ZIP code (extracted from address if not provided)
    """
    cache = load_cache()
    cache_key = _get_cache_key(address)
    zip_code = zip_code or _get_zip_key(address)
    
    # Update address-level cache
    if cache_key not in cache["addresses"]:
        cache["addresses"][cache_key] = {
            "original_address": address,
            "normalized": _normalize_address(address),
            "zip_code": zip_code,
            "created": datetime.now().isoformat(),
            "confirmation_count": 0
        }
    
    entry = cache["addresses"][cache_key]
    entry[utility_type] = {
        "name": utility_name,
        "phone": phone,
        "website": website,
        "confirmed_at": datetime.now().isoformat()
    }
    entry["confirmation_count"] = entry.get("confirmation_count", 0) + 1
    entry["last_confirmed"] = datetime.now().isoformat()
    
    # Update ZIP-level aggregation
    if zip_code:
        if zip_code not in cache["by_zip"]:
            cache["by_zip"][zip_code] = {}
        if utility_type not in cache["by_zip"][zip_code]:
            cache["by_zip"][zip_code][utility_type] = {}
        
        utility_key = utility_name.upper()
        if utility_key not in cache["by_zip"][zip_code][utility_type]:
            cache["by_zip"][zip_code][utility_type][utility_key] = {
                "name": utility_name,
                "phone": phone,
                "website": website,
                "confirmation_count": 0,
                "addresses": []
            }
        
        zip_entry = cache["by_zip"][zip_code][utility_type][utility_key]
        zip_entry["confirmation_count"] += 1
        if address not in zip_entry["addresses"]:
            zip_entry["addresses"].append(address)
        zip_entry["last_confirmed"] = datetime.now().isoformat()
    
    save_cache()


def get_cache_stats() -> Dict:
    """Get statistics about the address cache."""
    cache = load_cache()
    
    total_addresses = len(cache.get("addresses", {}))
    total_zips = len(cache.get("by_zip", {}))
    
    # Count confirmations by type
    electric_confirmations = 0
    gas_confirmations = 0
    water_confirmations = 0
    
    for zip_code, data in cache.get("by_zip", {}).items():
        for utility_name, info in data.get("electric", {}).items():
            electric_confirmations += info.get("confirmation_count", 0)
        for utility_name, info in data.get("gas", {}).items():
            gas_confirmations += info.get("confirmation_count", 0)
        for utility_name, info in data.get("water", {}).items():
            water_confirmations += info.get("confirmation_count", 0)
    
    return {
        "total_addresses": total_addresses,
        "total_zips": total_zips,
        "confirmations": {
            "electric": electric_confirmations,
            "gas": gas_confirmations,
            "water": water_confirmations,
            "total": electric_confirmations + gas_confirmations + water_confirmations
        },
        "last_updated": cache.get("_metadata", {}).get("last_updated")
    }


if __name__ == "__main__":
    # Test
    print("Cache stats:", get_cache_stats())
    
    # Simulate a confirmation
    cache_confirmation(
        address="1725 Toomey Rd, Austin, TX 78704",
        utility_type="electric",
        utility_name="Austin Energy",
        phone="512-494-9400",
        website="https://austinenergy.com"
    )
    
    print("After confirmation:", get_cache_stats())
    
    # Test lookup
    result = get_cached_utilities("1725 Toomey Rd, Austin, TX 78704")
    print("Cached lookup:", result)
