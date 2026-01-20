#!/usr/bin/env python3
"""
Phase 1: Migrate Hardcoded Python Dicts to JSON

Migrates all hardcoded dictionaries from state_utility_verification.py to JSON files.
This creates a single source of truth for Texas territory data.

Run: python scripts/migrate_hardcoded_dicts.py
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def migrate_texas_territories():
    """
    Migrate all Texas hardcoded dicts to single JSON file.
    
    Sources:
    - TEXAS_TDUS (lines 139-175)
    - TEXAS_ZIP_PREFIX_TO_TDU (lines 180-227)
    - TEXAS_MUNICIPAL_CITIES (lines 230-246)
    - TEXAS_COOPS (lines 249-265)
    - TEXAS_GAS_LDCS (lines 669-694)
    - TEXAS_GAS_ZIP_PREFIX (lines 697-720)
    - TEXAS_GAS_ZIP_OVERRIDES (lines 724-743)
    """
    from state_utility_verification import (
        TEXAS_TDUS,
        TEXAS_ZIP_PREFIX_TO_TDU,
        TEXAS_MUNICIPAL_CITIES,
        TEXAS_COOPS,
        TEXAS_GAS_LDCS,
        TEXAS_GAS_ZIP_PREFIX,
        TEXAS_GAS_ZIP_OVERRIDES,
    )
    
    texas_territories = {
        "_metadata": {
            "description": "Texas utility territory mappings - TDUs, gas LDCs, ZIP mappings",
            "last_updated": datetime.now().strftime("%Y-%m-%d"),
            "source": "Migrated from state_utility_verification.py hardcoded dicts",
            "migrated_from": "state_utility_verification.py lines 139-743"
        },
        "electric": {
            "tdus": TEXAS_TDUS,
            "zip_to_tdu": TEXAS_ZIP_PREFIX_TO_TDU,
            "municipal_cities": TEXAS_MUNICIPAL_CITIES,
            "coops": TEXAS_COOPS
        },
        "gas": {
            "ldcs": TEXAS_GAS_LDCS,
            "zip_to_ldc": TEXAS_GAS_ZIP_PREFIX,
            "zip_overrides": TEXAS_GAS_ZIP_OVERRIDES
        }
    }
    
    output_path = Path(__file__).parent.parent / 'data' / 'texas_territories.json'
    
    with open(output_path, 'w') as f:
        json.dump(texas_territories, f, indent=2)
    
    print(f"✅ Created {output_path}")
    print(f"   - {len(TEXAS_TDUS)} TDUs")
    print(f"   - {len(TEXAS_ZIP_PREFIX_TO_TDU)} ZIP-to-TDU mappings")
    print(f"   - {len(TEXAS_MUNICIPAL_CITIES)} municipal cities")
    print(f"   - {len(TEXAS_COOPS)} electric cooperatives")
    print(f"   - {len(TEXAS_GAS_LDCS)} gas LDCs")
    print(f"   - {len(TEXAS_GAS_ZIP_PREFIX)} ZIP-to-LDC mappings")
    print(f"   - {len(TEXAS_GAS_ZIP_OVERRIDES)} gas ZIP overrides")
    
    return output_path


def migrate_gas_zip_overrides():
    """
    Migrate GAS_ZIP_OVERRIDES to verified_addresses.json format.
    
    These are user-verified corrections that should be in the corrections database.
    """
    from state_utility_verification import GAS_ZIP_OVERRIDES
    
    # Load existing verified_addresses.json
    verified_path = Path(__file__).parent.parent / 'data' / 'verified_addresses.json'
    
    if verified_path.exists():
        with open(verified_path, 'r') as f:
            verified = json.load(f)
    else:
        verified = {"addresses": {}, "zip_overrides": {}, "streets": {}}
    
    # Ensure zip_overrides key exists
    if "zip_overrides" not in verified:
        verified["zip_overrides"] = {}
    
    # Add gas ZIP overrides
    added = 0
    for zip_code, override in GAS_ZIP_OVERRIDES.items():
        if zip_code not in verified["zip_overrides"]:
            verified["zip_overrides"][zip_code] = {}
        
        # Only add gas if not already present
        if "gas" not in verified["zip_overrides"][zip_code]:
            verified["zip_overrides"][zip_code]["gas"] = {
                "name": override["name"],
                "phone": override.get("phone"),
                "website": override.get("website"),
                "note": override.get("note"),
                "verified_date": datetime.now().strftime("%Y-%m-%d"),
                "verified_by": "migration"
            }
            added += 1
    
    # Add metadata if not present
    if "_metadata" not in verified:
        verified["_metadata"] = {
            "description": "User-verified utility corrections - highest priority source",
            "last_updated": datetime.now().strftime("%Y-%m-%d"),
            "version": "2.0"
        }
    else:
        verified["_metadata"]["last_updated"] = datetime.now().strftime("%Y-%m-%d")
    
    with open(verified_path, 'w') as f:
        json.dump(verified, f, indent=2)
    
    print(f"✅ Updated {verified_path}")
    print(f"   - Added {added} gas ZIP overrides")
    
    return verified_path


def merge_gas_county_data():
    """
    Merge gas_county_lookups.json into county_utility_defaults.json.
    
    This consolidates county-level gas data into the main county defaults file.
    """
    base_dir = Path(__file__).parent.parent / 'data'
    
    county_defaults_path = base_dir / 'county_utility_defaults.json'
    gas_county_path = base_dir / 'gas_county_lookups.json'
    
    if not gas_county_path.exists():
        print(f"⚠️  {gas_county_path} not found, skipping merge")
        return None
    
    # Load both files
    with open(county_defaults_path, 'r') as f:
        county_defaults = json.load(f)
    
    with open(gas_county_path, 'r') as f:
        gas_lookups = json.load(f)
    
    # Ensure gas key exists in county_defaults
    if "gas" not in county_defaults:
        county_defaults["gas"] = {}
    
    # Merge gas data
    merged_count = 0
    for state, state_data in gas_lookups.items():
        if state.startswith("_"):  # Skip metadata keys
            continue
        
        if state not in county_defaults["gas"]:
            county_defaults["gas"][state] = {}
        
        # Handle counties
        counties = state_data.get("counties", {})
        for county, county_data in counties.items():
            county_upper = county.upper()
            if county_upper not in county_defaults["gas"][state]:
                county_defaults["gas"][state][county_upper] = {
                    "name": county_data.get("utility"),
                    "notes": county_data.get("notes")
                }
                merged_count += 1
    
    # Update metadata
    county_defaults["_metadata"]["last_updated"] = datetime.now().strftime("%Y-%m-%d")
    county_defaults["_metadata"]["note"] = "Includes merged gas county data from gas_county_lookups.json"
    
    with open(county_defaults_path, 'w') as f:
        json.dump(county_defaults, f, indent=2)
    
    print(f"✅ Merged gas county data into {county_defaults_path}")
    print(f"   - Added {merged_count} county gas entries")
    
    return county_defaults_path


def create_backward_compatible_loader():
    """
    Create a loader module that provides backward compatibility.
    
    This allows existing code to continue using the old dict names
    while loading from JSON files.
    """
    loader_code = '''"""
Backward-compatible loader for Texas territory data.

During migration, this module loads data from JSON files but exposes
the same dict names as the original hardcoded dicts.

Usage:
    from data.texas_loader import (
        TEXAS_TDUS,
        TEXAS_ZIP_PREFIX_TO_TDU,
        TEXAS_GAS_LDCS,
        TEXAS_GAS_ZIP_PREFIX,
        TEXAS_GAS_ZIP_OVERRIDES,
    )
"""

import json
from pathlib import Path

_TEXAS_TERRITORIES = None

def _load_texas_territories():
    """Load Texas territories from JSON file."""
    global _TEXAS_TERRITORIES
    if _TEXAS_TERRITORIES is None:
        path = Path(__file__).parent / 'texas_territories.json'
        if path.exists():
            with open(path, 'r') as f:
                _TEXAS_TERRITORIES = json.load(f)
        else:
            # Fallback to empty structure
            _TEXAS_TERRITORIES = {
                'electric': {'tdus': {}, 'zip_to_tdu': {}, 'municipal_cities': {}, 'coops': []},
                'gas': {'ldcs': {}, 'zip_to_ldc': {}, 'zip_overrides': {}}
            }
    return _TEXAS_TERRITORIES


# Lazy-loaded properties that match original dict names
class _LazyDict(dict):
    """Dict that loads data on first access."""
    def __init__(self, loader):
        self._loader = loader
        self._loaded = False
    
    def _ensure_loaded(self):
        if not self._loaded:
            data = self._loader()
            self.update(data)
            self._loaded = True
    
    def __getitem__(self, key):
        self._ensure_loaded()
        return super().__getitem__(key)
    
    def __contains__(self, key):
        self._ensure_loaded()
        return super().__contains__(key)
    
    def get(self, key, default=None):
        self._ensure_loaded()
        return super().get(key, default)
    
    def keys(self):
        self._ensure_loaded()
        return super().keys()
    
    def values(self):
        self._ensure_loaded()
        return super().values()
    
    def items(self):
        self._ensure_loaded()
        return super().items()


# Electric
TEXAS_TDUS = _LazyDict(lambda: _load_texas_territories()['electric']['tdus'])
TEXAS_ZIP_PREFIX_TO_TDU = _LazyDict(lambda: _load_texas_territories()['electric']['zip_to_tdu'])
TEXAS_MUNICIPAL_CITIES = _LazyDict(lambda: _load_texas_territories()['electric']['municipal_cities'])

# Gas
TEXAS_GAS_LDCS = _LazyDict(lambda: _load_texas_territories()['gas']['ldcs'])
TEXAS_GAS_ZIP_PREFIX = _LazyDict(lambda: _load_texas_territories()['gas']['zip_to_ldc'])
TEXAS_GAS_ZIP_OVERRIDES = _LazyDict(lambda: _load_texas_territories()['gas']['zip_overrides'])

# List (not a dict)
def get_texas_coops():
    """Get list of Texas electric cooperatives."""
    return _load_texas_territories()['electric']['coops']

TEXAS_COOPS = get_texas_coops()
'''
    
    loader_path = Path(__file__).parent.parent / 'data' / 'texas_loader.py'
    
    with open(loader_path, 'w') as f:
        f.write(loader_code)
    
    print(f"✅ Created {loader_path}")
    print("   - Provides backward-compatible access to Texas territory data")
    
    return loader_path


def main():
    """Run all migrations."""
    print("=" * 60)
    print("PHASE 1: MIGRATE HARDCODED DICTS TO JSON")
    print("=" * 60)
    print()
    
    # 1. Migrate Texas territories
    print("1. Migrating Texas territories...")
    migrate_texas_territories()
    print()
    
    # 2. Migrate gas ZIP overrides to verified_addresses
    print("2. Migrating gas ZIP overrides...")
    migrate_gas_zip_overrides()
    print()
    
    # 3. Merge gas county data
    print("3. Merging gas county data...")
    merge_gas_county_data()
    print()
    
    # 4. Create backward-compatible loader
    print("4. Creating backward-compatible loader...")
    create_backward_compatible_loader()
    print()
    
    print("=" * 60)
    print("MIGRATION COMPLETE")
    print("=" * 60)
    print()
    print("Next steps:")
    print("1. Run: python scripts/validate_data.py")
    print("2. Update imports in state_utility_verification.py to use data/texas_loader.py")
    print("3. Test with: pytest tests/test_current_behavior.py -v")


if __name__ == "__main__":
    main()
