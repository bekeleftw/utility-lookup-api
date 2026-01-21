#!/usr/bin/env python3
"""
Build tenant-verified utility override data from addresses_with_tenant_verification.csv

This creates:
1. Street-level patterns for ambiguous ZIPs (ZIP + street → utility)
2. Missing utility data to add to EIA (utilities not in our data)
3. Direct address overrides for high-confidence matches
"""

import csv
import re
import json
from collections import defaultdict

def get_zip(addr):
    m = re.search(r'(\d{5})(?:-\d{4})?$', addr.strip())
    return m.group(1) if m else None

def get_state(addr):
    m = re.search(r',\s*([A-Z]{2})\s+\d{5}', addr)
    return m.group(1) if m else None

def get_city(addr):
    m = re.search(r',\s*([^,]+),\s*[A-Z]{2}\s+\d{5}', addr)
    return m.group(1).strip() if m else None

def normalize_street(addr):
    """Extract and normalize street name from address"""
    m = re.match(r'[\d\-]+\s+(.+?),', addr)
    if not m:
        return None
    street = m.group(1).lower().strip()
    # Remove unit/apt numbers
    street = re.sub(r'\s+(apt|unit|ste|suite|#|bldg|building)\s*\S*$', '', street, flags=re.I)
    # Normalize common abbreviations
    replacements = [
        (r'\bst\b', 'street'), (r'\bave\b', 'avenue'), (r'\bblvd\b', 'boulevard'),
        (r'\bdr\b', 'drive'), (r'\bln\b', 'lane'), (r'\brd\b', 'road'),
        (r'\bct\b', 'court'), (r'\bpl\b', 'place'), (r'\bcir\b', 'circle'),
        (r'\bpkwy\b', 'parkway'), (r'\bhwy\b', 'highway'), (r'\bter\b', 'terrace'),
    ]
    for pattern, replacement in replacements:
        street = re.sub(pattern, replacement, street)
    return street

def normalize_utility_name(name):
    """Normalize utility name for matching"""
    if not name:
        return ""
    name = name.lower().strip()
    # Remove state suffixes
    name = re.sub(r'\s*[-–]\s*[a-z]{2}\s*$', '', name)
    name = re.sub(r'\s*\([a-z]{2}\)\s*$', '', name)
    return name

def main():
    print("Loading tenant verification data...")
    with open('addresses_with_tenant_verification.csv', 'r') as f:
        rows = list(csv.DictReader(f))
    print(f"Loaded {len(rows):,} rows")

    print("Loading EIA data...")
    with open('eia_zip_utility_lookup.json', 'r') as f:
        eia = json.load(f)
    print(f"Loaded {len(eia):,} ZIPs")

    # Identify ambiguous ZIPs (multiple utilities in EIA)
    ambiguous_zips = {z for z, utils in eia.items() if len(utils) > 1}
    print(f"Ambiguous ZIPs: {len(ambiguous_zips):,}")

    # Data structures to build
    street_patterns = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    # {zip: {street: {utility: count}}}
    
    zip_utility_counts = defaultdict(lambda: defaultdict(int))
    # {zip: {utility: count}}
    
    missing_utilities = defaultdict(lambda: defaultdict(int))
    # {zip: {utility: count}} - utilities not in EIA for that ZIP

    # Process tenant data
    for row in rows:
        addr = row.get('display', '')
        elec = row.get('Electricity', '').strip()
        
        if not addr or not elec:
            continue
        
        zip_code = get_zip(addr)
        street = normalize_street(addr)
        state = get_state(addr)
        
        if not zip_code:
            continue
        
        # Track ZIP-level utility counts
        zip_utility_counts[zip_code][elec] += 1
        
        # Track street-level patterns for ambiguous ZIPs
        if street and zip_code in ambiguous_zips:
            street_patterns[zip_code][street][elec] += 1
        
        # Check if utility is missing from EIA for this ZIP
        if zip_code in eia:
            eia_names = [normalize_utility_name(u['name']) for u in eia[zip_code]]
            elec_norm = normalize_utility_name(elec)
            found = any(
                en in elec_norm or elec_norm in en or 
                en.split()[0] == elec_norm.split()[0] if en and elec_norm else False
                for en in eia_names
            )
            if not found:
                missing_utilities[zip_code][elec] += 1

    # Build output structures
    
    # 1. Street-level overrides (high confidence)
    street_overrides = []
    for zip_code, streets in street_patterns.items():
        for street, utils in streets.items():
            total = sum(utils.values())
            if total >= 2:  # At least 2 data points
                top_util, top_count = max(utils.items(), key=lambda x: x[1])
                confidence = top_count / total
                if confidence >= 0.75:  # 75%+ agreement
                    street_overrides.append({
                        'zip': zip_code,
                        'street': street,
                        'utility': top_util,
                        'count': top_count,
                        'total': total,
                        'confidence': round(confidence, 2)
                    })
    
    print(f"\nStreet-level overrides (75%+ confidence): {len(street_overrides):,}")

    # 2. ZIP-level additions (utilities to add to EIA)
    zip_additions = []
    for zip_code, utils in missing_utilities.items():
        for util, count in utils.items():
            if count >= 3:  # At least 3 occurrences
                state = None
                # Get state from any address with this ZIP
                for row in rows:
                    if get_zip(row.get('display', '')) == zip_code:
                        state = get_state(row.get('display', ''))
                        break
                zip_additions.append({
                    'zip': zip_code,
                    'utility': util,
                    'count': count,
                    'state': state,
                    'source': 'tenant_verification'
                })
    
    print(f"ZIP-level additions needed: {len(zip_additions):,}")

    # 3. Identify specific utilities completely missing from EIA
    all_missing_utils = defaultdict(int)
    for zip_code, utils in missing_utilities.items():
        for util, count in utils.items():
            all_missing_utils[util] += count
    
    print(f"\nTop 20 utilities missing from EIA data:")
    for util, count in sorted(all_missing_utils.items(), key=lambda x: -x[1])[:20]:
        print(f"  {count:5}x {util}")

    # Build ZIP-level utility counts (ALL utilities seen, not just missing from EIA)
    all_zip_utilities = defaultdict(lambda: defaultdict(int))
    for row in rows:
        addr = row.get('display', '')
        elec = row.get('Electricity', '').strip()
        if not addr or not elec:
            continue
        zip_code = get_zip(addr)
        if zip_code:
            all_zip_utilities[zip_code][elec] += 1
    
    # Find ZIPs with multiple significant utilities (context for AI)
    multi_utility_zips = {}
    for zip_code, utils in all_zip_utilities.items():
        # Keep utilities with at least 2 occurrences
        significant = {u: c for u, c in utils.items() if c >= 2}
        if len(significant) >= 2:
            # Sort by count, keep top 5
            sorted_utils = sorted(significant.items(), key=lambda x: -x[1])[:5]
            multi_utility_zips[zip_code] = [u for u, c in sorted_utils]
    
    print(f"ZIPs with multiple utilities seen: {len(multi_utility_zips):,}")
    
    # Save outputs
    output = {
        'street_overrides': sorted(street_overrides, key=lambda x: -x['count']),
        'zip_additions': sorted(zip_additions, key=lambda x: -x['count']),
        'missing_utilities_summary': dict(sorted(all_missing_utils.items(), key=lambda x: -x[1])[:100])
    }
    
    with open('tenant_verified_overrides.json', 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\nSaved to tenant_verified_overrides.json")
    
    # Also create a simple lookup format for the API
    api_lookup = {
        'street_overrides': {},  # {zip: {street: utility}}
        'zip_utilities': {},  # {zip: [utilities]} - utilities missing from EIA
        'zip_alternatives': {}  # {zip: [utilities]} - ALL utilities seen in this ZIP (for AI context)
    }
    
    for override in street_overrides:
        zip_code = override['zip']
        if zip_code not in api_lookup['street_overrides']:
            api_lookup['street_overrides'][zip_code] = {}
        api_lookup['street_overrides'][zip_code][override['street']] = override['utility']
    
    for addition in zip_additions:
        zip_code = addition['zip']
        if zip_code not in api_lookup['zip_utilities']:
            api_lookup['zip_utilities'][zip_code] = []
        if addition['utility'] not in api_lookup['zip_utilities'][zip_code]:
            api_lookup['zip_utilities'][zip_code].append(addition['utility'])
    
    # Add multi-utility ZIPs for AI context
    api_lookup['zip_alternatives'] = multi_utility_zips
    
    with open('tenant_verified_lookup.json', 'w') as f:
        json.dump(api_lookup, f, indent=2)
    
    print(f"Saved API lookup to tenant_verified_lookup.json")
    print(f"  - Street overrides for {len(api_lookup['street_overrides'])} ZIPs")
    print(f"  - ZIP utility additions for {len(api_lookup['zip_utilities'])} ZIPs")

if __name__ == '__main__':
    main()
