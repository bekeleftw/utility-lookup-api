#!/usr/bin/env python3
"""
Build a fast local lookup table for water utilities from SDWA data.
Creates a JSON file indexed by state+county and state+city for quick lookups.
"""

import csv
import json
from collections import defaultdict
from pathlib import Path

SDWA_DIR = Path(__file__).parent / "SDWA_latest_downloads"
OUTPUT_FILE = Path(__file__).parent / "water_utility_lookup.json"


def build_lookup():
    print("Building water utility lookup from SDWA data...")
    
    # Step 1: Load water system details
    print("Loading water systems...")
    water_systems = {}
    with open(SDWA_DIR / "SDWA_PUB_WATER_SYSTEMS.csv", 'r', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f)
        for row in reader:
            pwsid = row.get('PWSID')
            if not pwsid:
                continue
            
            # Only include active community water systems
            if row.get('PWS_ACTIVITY_CODE') != 'A':
                continue
            if row.get('PWS_TYPE_CODE') != 'CWS':
                continue
            # Skip small wholesalers (but keep large ones like Austin Water that also serve retail)
            pop = int(row.get('POPULATION_SERVED_COUNT') or 0)
            if row.get('IS_WHOLESALER_IND') == 'Y' and pop < 100000:
                continue
            
            water_systems[pwsid] = {
                'name': row.get('PWS_NAME'),
                'id': pwsid,
                'state': row.get('STATE_CODE'),
                'phone': row.get('PHONE_NUMBER'),
                'address': row.get('ADDRESS_LINE1'),
                'city': row.get('CITY_NAME'),
                'zip': row.get('ZIP_CODE'),
                'population_served': int(row.get('POPULATION_SERVED_COUNT') or 0),
                'source_type': row.get('PRIMARY_SOURCE_CODE'),
                'owner_type': row.get('OWNER_TYPE_CODE'),
                'service_connections': int(row.get('SERVICE_CONNECTIONS_COUNT') or 0),
            }
    
    print(f"  Loaded {len(water_systems):,} active community water systems")
    
    # Step 2: Build county and city mappings
    print("Loading geographic areas...")
    county_to_pws = defaultdict(set)  # state|county -> set of pwsid
    city_to_pws = defaultdict(set)    # state|city -> set of pwsid
    
    with open(SDWA_DIR / "SDWA_GEOGRAPHIC_AREAS.csv", 'r', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f)
        for row in reader:
            pwsid = row.get('PWSID')
            if pwsid not in water_systems:
                continue
            
            state = water_systems[pwsid]['state']
            
            # County mapping
            county = row.get('COUNTY_SERVED')
            if county and row.get('AREA_TYPE_CODE') == 'CN':
                # Normalize county name
                county = county.upper().replace(' COUNTY', '').strip()
                key = f"{state}|{county}"
                county_to_pws[key].add(pwsid)
            
            # City mapping
            city = row.get('CITY_SERVED')
            if city and row.get('AREA_TYPE_CODE') == 'CI':
                city = city.upper().strip()
                key = f"{state}|{city}"
                city_to_pws[key].add(pwsid)
    
    print(f"  Found {len(county_to_pws):,} county mappings")
    print(f"  Found {len(city_to_pws):,} city mappings")
    
    # Step 3: Build city lookup from water system's own city field
    print("Building city lookup from water system addresses...")
    for pwsid, ws in water_systems.items():
        city = ws.get('city')
        state = ws.get('state')
        if city and state:
            city = city.upper().strip()
            key = f"{state}|{city}"
            if key not in city_to_pws:
                city_to_pws[key] = set()
            city_to_pws[key].add(pwsid)
    
    print(f"  Updated city mappings: {len(city_to_pws):,}")
    
    # Step 4: For each county/city, find the largest water system
    print("Building final lookup...")
    
    def get_best_system(pws_ids, city_name=None):
        """Return the best water system - prefer city-named utilities, then largest population."""
        systems = [water_systems[pid] for pid in pws_ids if pid in water_systems]
        if not systems:
            return None
        
        # If we have a city name, prefer systems with that city in their name
        if city_name:
            city_upper = city_name.upper()
            # Look for patterns like "CITY OF AUSTIN", "AUSTIN WATER", "TOWN OF BOONE"
            city_named = []
            for s in systems:
                name_upper = s['name'].upper()
                # Check for city name with utility keywords
                has_city = city_upper in name_upper
                has_keyword = any(kw in name_upper for kw in ['CITY OF', 'TOWN OF', 'VILLAGE OF', 'WATER', 'UTILITY', 'MUNICIPAL'])
                # Exclude MUDs (Municipal Utility Districts) - they're usually subdivisions
                is_mud = 'MUD' in name_upper or 'M.U.D' in name_upper
                if has_city and has_keyword and not is_mud:
                    city_named.append(s)
            
            if city_named:
                city_named.sort(key=lambda x: x['population_served'], reverse=True)
                return city_named[0]
        
        # Fall back to largest by population (but still exclude MUDs if possible)
        non_muds = [s for s in systems if 'MUD' not in s['name'].upper() and 'M.U.D' not in s['name'].upper()]
        if non_muds:
            non_muds.sort(key=lambda x: x['population_served'], reverse=True)
            return non_muds[0]
        
        systems.sort(key=lambda x: x['population_served'], reverse=True)
        return systems[0]
    
    def get_all_systems_sorted(pws_ids):
        """Return all water systems sorted by population."""
        systems = [water_systems[pid] for pid in pws_ids if pid in water_systems]
        systems.sort(key=lambda x: x['population_served'], reverse=True)
        return systems
    
    lookup = {
        'by_county': {},
        'by_city': {},
    }
    
    # County lookup - store best system for each county
    for key, pws_ids in county_to_pws.items():
        best = get_best_system(pws_ids)
        if best:
            lookup['by_county'][key] = best
            lookup['by_county'][key]['_alternatives_count'] = len(pws_ids)
    
    # City lookup - store best system for each city (prefer city match over county)
    for key, pws_ids in city_to_pws.items():
        city_name = key.split('|')[1] if '|' in key else None
        best = get_best_system(pws_ids, city_name=city_name)
        if best:
            lookup['by_city'][key] = best
            lookup['by_city'][key]['_alternatives_count'] = len(pws_ids)
    
    print(f"  County lookups: {len(lookup['by_county']):,}")
    print(f"  City lookups: {len(lookup['by_city']):,}")
    
    # Step 4: Save to JSON
    print(f"Saving to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(lookup, f)
    
    file_size = OUTPUT_FILE.stat().st_size / (1024 * 1024)
    print(f"  File size: {file_size:.1f} MB")
    print("Done!")
    
    return lookup


if __name__ == "__main__":
    build_lookup()
