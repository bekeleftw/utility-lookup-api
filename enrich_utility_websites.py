#!/usr/bin/env python3
"""
Batch script to find and add websites for utilities that are missing them.
Saves progress incrementally to avoid losing work.
"""

import json
import time
from browser_verification import find_utility_website

def load_data(filepath):
    with open(filepath, 'r') as f:
        return json.load(f)

def save_data(filepath, data):
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)

def enrich_remaining_states_electric():
    """Enrich remaining_states_electric.json with discovered websites."""
    filepath = 'data/remaining_states_electric.json'
    data = load_data(filepath)
    states_data = data.get('states', {})
    
    # Track unique utilities we've already looked up
    looked_up = {}
    enriched_count = 0
    failed_count = 0
    
    for state, zips in states_data.items():
        for zip_code, info in zips.items():
            if not isinstance(info, dict):
                continue
                
            name = info.get('name') or info.get('normalized_name')
            website = info.get('website')
            
            # Skip if already has website
            if website and website not in ['', None, 'Unknown']:
                continue
            
            if not name:
                continue
            
            # Check if we already looked this up
            if name in looked_up:
                if looked_up[name]:
                    info['website'] = looked_up[name]
                    enriched_count += 1
                continue
            
            # Look up website
            print(f"Looking up: {name} ({state})...", end=" ", flush=True)
            found_website = find_utility_website(name, state)
            
            if found_website:
                print(f"✓ {found_website}")
                info['website'] = found_website
                looked_up[name] = found_website
                enriched_count += 1
            else:
                print("✗ Not found")
                looked_up[name] = None
                failed_count += 1
            
            # Rate limit - be nice to Google
            time.sleep(1)
            
            # Save progress every 10 lookups
            if (enriched_count + failed_count) % 10 == 0:
                save_data(filepath, data)
                print(f"  [Saved progress: {enriched_count} enriched, {failed_count} failed]")
    
    # Final save
    save_data(filepath, data)
    print(f"\nDone! Enriched {enriched_count} utilities, {failed_count} not found")
    return enriched_count, failed_count


def enrich_remaining_states_gas():
    """Enrich remaining_states_gas.json with discovered websites."""
    filepath = 'data/remaining_states_gas.json'
    data = load_data(filepath)
    states_data = data.get('states', {})
    
    looked_up = {}
    enriched_count = 0
    failed_count = 0
    
    for state, zips in states_data.items():
        for zip_code, info in zips.items():
            if not isinstance(info, dict):
                continue
                
            name = info.get('name') or info.get('normalized_name')
            website = info.get('website')
            
            if website and website not in ['', None, 'Unknown']:
                continue
            
            if not name:
                continue
            
            if name in looked_up:
                if looked_up[name]:
                    info['website'] = looked_up[name]
                    enriched_count += 1
                continue
            
            print(f"Looking up: {name} ({state})...", end=" ", flush=True)
            found_website = find_utility_website(name, state)
            
            if found_website:
                print(f"✓ {found_website}")
                info['website'] = found_website
                looked_up[name] = found_website
                enriched_count += 1
            else:
                print("✗ Not found")
                looked_up[name] = None
                failed_count += 1
            
            time.sleep(1)
            
            if (enriched_count + failed_count) % 10 == 0:
                save_data(filepath, data)
                print(f"  [Saved progress: {enriched_count} enriched, {failed_count} failed]")
    
    save_data(filepath, data)
    print(f"\nDone! Enriched {enriched_count} utilities, {failed_count} not found")
    return enriched_count, failed_count


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    print("=" * 60)
    print("Enriching Electric Utilities")
    print("=" * 60)
    e_enriched, e_failed = enrich_remaining_states_electric()
    
    print("\n" + "=" * 60)
    print("Enriching Gas Utilities")
    print("=" * 60)
    g_enriched, g_failed = enrich_remaining_states_gas()
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Electric: {e_enriched} enriched, {e_failed} not found")
    print(f"Gas: {g_enriched} enriched, {g_failed} not found")
    print(f"Total: {e_enriched + g_enriched} enriched")
