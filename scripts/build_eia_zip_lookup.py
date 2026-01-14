#!/usr/bin/env python3
"""
Build comprehensive EIA ZIP-to-utility lookup by combining:
1. Existing EIA data
2. Municipal utilities data
3. Electric cooperative data
4. County defaults

This creates a unified lookup that covers more ZIP codes.
"""

import json
import os
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path(__file__).parent.parent

def load_existing_eia():
    """Load existing EIA ZIP lookup."""
    path = BASE_DIR / "eia_zip_utility_lookup.json"
    if path.exists():
        with open(path, 'r') as f:
            return json.load(f)
    return {}

def load_municipal():
    """Load municipal utilities."""
    path = BASE_DIR / "data" / "municipal_utilities.json"
    if path.exists():
        with open(path, 'r') as f:
            return json.load(f)
    return {}

def load_coops():
    """Load electric cooperatives."""
    path = BASE_DIR / "data" / "electric_cooperatives_supplemental.json"
    if path.exists():
        with open(path, 'r') as f:
            data = json.load(f)
            return data.get('cooperatives', [])
    return []

def load_findenergy():
    """Load FindEnergy utility data."""
    path = BASE_DIR / "data" / "findenergy" / "utilities_by_state.json"
    if path.exists():
        with open(path, 'r') as f:
            return json.load(f)
    return {}

def build_comprehensive_lookup():
    """Build comprehensive ZIP-to-utility lookup."""
    
    # Start with existing EIA data
    lookup = load_existing_eia()
    print(f"Starting with {len(lookup)} ZIPs from existing EIA data")
    
    added_municipal = 0
    added_coop = 0
    added_findenergy = 0
    
    # Add municipal utilities
    municipal = load_municipal()
    for util_type in ['electric']:
        for state, cities in municipal.get(util_type, {}).items():
            for city, utility in cities.items():
                for zip_code in utility.get('zip_codes', []):
                    if zip_code not in lookup:
                        lookup[zip_code] = []
                    
                    # Check if already have this utility for this ZIP
                    existing_names = [u['name'].upper() for u in lookup[zip_code]]
                    if utility['name'].upper() not in existing_names:
                        lookup[zip_code].insert(0, {  # Insert at front (higher priority)
                            "eiaid": None,
                            "name": utility['name'],
                            "state": state,
                            "ownership": "Municipal",
                            "service_type": "Bundled",
                            "phone": utility.get('phone'),
                            "website": utility.get('website'),
                            "source": "municipal_utilities"
                        })
                        added_municipal += 1
    
    print(f"Added {added_municipal} municipal utility entries")
    
    # Add electric cooperatives
    coops = load_coops()
    for coop in coops:
        for zip_code in coop.get('zips', []):
            if zip_code not in lookup:
                lookup[zip_code] = []
            
            existing_names = [u['name'].upper() for u in lookup[zip_code]]
            if coop['name'].upper() not in existing_names:
                lookup[zip_code].append({
                    "eiaid": None,
                    "name": coop['name'],
                    "state": coop.get('state'),
                    "ownership": "Cooperative",
                    "service_type": "Bundled",
                    "phone": coop.get('phone'),
                    "website": coop.get('website'),
                    "source": "electric_cooperatives"
                })
                added_coop += 1
    
    print(f"Added {added_coop} cooperative entries")
    
    # Add FindEnergy data
    findenergy = load_findenergy()
    for state, utilities in findenergy.items():
        for utility in utilities:
            for zip_code in utility.get('zip_codes', []):
                if zip_code not in lookup:
                    lookup[zip_code] = []
                
                existing_names = [u['name'].upper() for u in lookup[zip_code]]
                if utility['name'].upper() not in existing_names:
                    lookup[zip_code].append({
                        "eiaid": None,
                        "name": utility['name'],
                        "state": state,
                        "ownership": utility.get('type', 'Unknown'),
                        "service_type": "Bundled",
                        "phone": utility.get('phone'),
                        "website": utility.get('website'),
                        "source": "findenergy"
                    })
                    added_findenergy += 1
    
    print(f"Added {added_findenergy} FindEnergy entries")
    
    # Sort each ZIP's utilities by priority (municipal first, then existing EIA, then coops)
    for zip_code in lookup:
        lookup[zip_code].sort(key=lambda u: (
            0 if u.get('source') == 'municipal_utilities' else
            1 if u.get('ownership') == 'Municipal' else
            2 if u.get('source') == 'findenergy' else
            3 if u.get('ownership') == 'Investor Owned' else
            4
        ))
    
    return lookup

def main():
    lookup = build_comprehensive_lookup()
    
    print(f"\nTotal ZIPs in comprehensive lookup: {len(lookup)}")
    
    # Test some ZIPs
    test_zips = ['78704', '78701', '77002', '29307', '78640', '90012', '10001']
    print("\nTest lookups:")
    for z in test_zips:
        if z in lookup and lookup[z]:
            print(f"  {z}: {lookup[z][0]['name']} ({lookup[z][0].get('ownership', 'Unknown')})")
        else:
            print(f"  {z}: NOT FOUND")
    
    # Save
    output_path = BASE_DIR / "eia_zip_utility_lookup.json"
    with open(output_path, 'w') as f:
        json.dump(lookup, f, indent=2)
    
    print(f"\nSaved to {output_path}")
    print(f"File size: {output_path.stat().st_size / 1024 / 1024:.2f} MB")

if __name__ == "__main__":
    main()
