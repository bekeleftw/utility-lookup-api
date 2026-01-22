#!/usr/bin/env python3
"""
Generate Tenant Rules

Processes raw tenant verification data and generates:
1. tenant_hard_overrides.json - High-confidence overrides (95%+)
2. tenant_ai_context.json - Medium-confidence context for AI selector

This is the main script that ties together:
- utility_name_normalizer.py
- deregulated_market_handler.py  
- tenant_confidence_scorer.py
"""

import csv
import json
import os
import re
from collections import defaultdict
from datetime import datetime
from typing import Dict, List

from utility_name_normalizer import normalize_utility_name
from deregulated_market_handler import (
    is_deregulated_state, 
    is_retail_provider, 
    should_ignore_tenant_mismatch,
    classify_utility
)
from tenant_confidence_scorer import (
    calculate_tenant_confidence,
    extract_street_from_address,
    validate_utility_type
)


def load_tenant_data(csv_file: str) -> List[Dict]:
    """Load tenant verification CSV."""
    with open(csv_file, 'r') as f:
        return list(csv.DictReader(f))


def extract_address_components(address: str) -> Dict:
    """Parse address into components."""
    result = {
        'zip_code': None,
        'state': None,
        'city': None,
        'street': None,
        'street_number': None
    }
    
    # ZIP
    zip_match = re.search(r'(\d{5})(?:-\d{4})?$', address.strip())
    if zip_match:
        result['zip_code'] = zip_match.group(1)
    
    # State
    state_match = re.search(r',\s*([A-Z]{2})\s+\d{5}', address)
    if state_match:
        result['state'] = state_match.group(1)
    
    # City
    city_match = re.search(r',\s*([^,]+),\s*[A-Z]{2}\s+\d{5}', address)
    if city_match:
        result['city'] = city_match.group(1).strip()
    
    # Street
    result['street'] = extract_street_from_address(address)
    
    # Street number
    num_match = re.match(r'(\d+)', address)
    if num_match:
        result['street_number'] = num_match.group(1)
    
    return result


def process_all_tenant_data(records: List[Dict]) -> Dict:
    """
    Process all tenant records and group by ZIP+street.
    
    Returns structured data for confidence calculation.
    """
    # Group by ZIP -> street -> list of records
    by_zip_street = defaultdict(lambda: defaultdict(list))
    
    # Track stats
    stats = {
        'total_records': len(records),
        'valid_records': 0,
        'skipped_no_address': 0,
        'skipped_no_utility': 0,
        'skipped_no_zip': 0,
        'skipped_wrong_type': 0,
        'skipped_rep_in_dereg': 0,
        'by_state': defaultdict(int)
    }
    
    for record in records:
        address = record.get('display', '')
        electric = record.get('Electricity', '').strip()
        
        if not address:
            stats['skipped_no_address'] += 1
            continue
        
        if not electric:
            stats['skipped_no_utility'] += 1
            continue
        
        # Parse address
        parsed = extract_address_components(address)
        
        if not parsed['zip_code']:
            stats['skipped_no_zip'] += 1
            continue
        
        # Validate utility type (skip gas utilities in electric field)
        validation = validate_utility_type(electric, 'electric')
        if not validation['valid']:
            stats['skipped_wrong_type'] += 1
            continue
        
        # Handle deregulated markets - skip REPs
        state = parsed['state'] or ''
        if is_deregulated_state(state) and is_retail_provider(electric, state):
            stats['skipped_rep_in_dereg'] += 1
            continue
        
        # Normalize utility name
        normalized = normalize_utility_name(electric)
        
        # Store record
        by_zip_street[parsed['zip_code']][parsed['street'] or 'unknown'].append({
            'address': address,
            'utility': normalized,
            'raw_utility': electric,
            'state': state,
            'city': parsed['city']
        })
        
        stats['valid_records'] += 1
        stats['by_state'][state] += 1
    
    return {
        'by_zip_street': dict(by_zip_street),
        'stats': stats
    }


def generate_override_files(processed_data: Dict) -> Dict:
    """
    Generate hard override and AI context files from processed data.
    
    Returns:
        {
            'hard_overrides': {...},
            'ai_context': {...},
            'stats': {...}
        }
    """
    by_zip_street = processed_data['by_zip_street']
    
    hard_overrides = {}
    ai_context = {}
    
    stats = {
        'total_zip_streets': 0,
        'hard_override_count': 0,
        'ai_boost_count': 0,
        'ai_context_count': 0,
        'store_only_count': 0,
        'flag_review_count': 0,
        'split_territory_zips': []
    }
    
    for zip_code, streets in by_zip_street.items():
        zip_has_override = False
        zip_has_context = False
        zip_utilities = set()
        
        for street, records in streets.items():
            if not street or street == 'unknown':
                continue
            
            stats['total_zip_streets'] += 1
            
            # Calculate confidence
            confidence_data = calculate_tenant_confidence(
                zip_code, street, records, 'electric'
            )
            
            if not confidence_data:
                continue
            
            # Track all utilities seen in this ZIP
            for util in confidence_data['all_utilities'].keys():
                zip_utilities.add(util)
            
            action = confidence_data['action']
            
            if action == 'hard_override':
                # Add to hard overrides
                if zip_code not in hard_overrides:
                    hard_overrides[zip_code] = {}
                
                hard_overrides[zip_code][street] = {
                    'electric': confidence_data['utility'],
                    'confidence': confidence_data['confidence'],
                    'sample_count': confidence_data['sample_count'],
                    'agreement_rate': confidence_data['agreement_rate']
                }
                stats['hard_override_count'] += 1
                zip_has_override = True
            
            elif action in ('ai_boost', 'ai_context'):
                # Add to AI context
                if zip_code not in ai_context:
                    ai_context[zip_code] = {
                        'utilities_observed': [],
                        'patterns': []
                    }
                
                ai_context[zip_code]['patterns'].append({
                    'street': street,
                    'utility': confidence_data['utility'],
                    'confidence': confidence_data['confidence'],
                    'samples': confidence_data['sample_count']
                })
                
                if action == 'ai_boost':
                    stats['ai_boost_count'] += 1
                else:
                    stats['ai_context_count'] += 1
                zip_has_context = True
            
            elif action == 'store_only':
                stats['store_only_count'] += 1
            
            elif action == 'flag_review':
                stats['flag_review_count'] += 1
        
        # Update utilities_observed for AI context
        if zip_code in ai_context:
            ai_context[zip_code]['utilities_observed'] = list(zip_utilities)
        
        # Track split territory ZIPs
        if len(zip_utilities) >= 2:
            stats['split_territory_zips'].append({
                'zip': zip_code,
                'utilities': list(zip_utilities)
            })
    
    return {
        'hard_overrides': hard_overrides,
        'ai_context': ai_context,
        'stats': stats
    }


def save_output_files(results: Dict, output_dir: str = 'data'):
    """Save generated files to disk."""
    os.makedirs(output_dir, exist_ok=True)
    
    # Hard overrides
    hard_override_file = os.path.join(output_dir, 'tenant_hard_overrides.json')
    with open(hard_override_file, 'w') as f:
        json.dump({
            'version': datetime.now().strftime('%Y-%m-%d'),
            'description': 'High-confidence tenant-verified utility mappings. Use as primary source.',
            'override_count': len(results['hard_overrides']),
            'overrides': results['hard_overrides']
        }, f, indent=2)
    print(f"Saved {len(results['hard_overrides'])} ZIP overrides to {hard_override_file}")
    
    # AI context
    ai_context_file = os.path.join(output_dir, 'tenant_ai_context.json')
    with open(ai_context_file, 'w') as f:
        json.dump({
            'version': datetime.now().strftime('%Y-%m-%d'),
            'description': 'Medium-confidence tenant patterns. Feed to AI selector as context.',
            'context_count': len(results['ai_context']),
            'context_rules': results['ai_context']
        }, f, indent=2)
    print(f"Saved {len(results['ai_context'])} ZIP contexts to {ai_context_file}")
    
    # Stats
    stats_file = os.path.join(output_dir, 'tenant_processing_stats.json')
    with open(stats_file, 'w') as f:
        json.dump({
            'generated_at': datetime.now().isoformat(),
            'processing_stats': results.get('processing_stats', {}),
            'override_stats': results['stats']
        }, f, indent=2)
    print(f"Saved stats to {stats_file}")


def main():
    print("="*60)
    print("GENERATING TENANT RULES")
    print("="*60)
    
    # Load data
    print("\nLoading tenant data...")
    records = load_tenant_data('addresses_with_tenant_verification.csv')
    print(f"Loaded {len(records):,} records")
    
    # Process data
    print("\nProcessing records...")
    processed = process_all_tenant_data(records)
    
    print(f"\nProcessing stats:")
    stats = processed['stats']
    print(f"  Total records: {stats['total_records']:,}")
    print(f"  Valid records: {stats['valid_records']:,}")
    print(f"  Skipped (no address): {stats['skipped_no_address']:,}")
    print(f"  Skipped (no utility): {stats['skipped_no_utility']:,}")
    print(f"  Skipped (no ZIP): {stats['skipped_no_zip']:,}")
    print(f"  Skipped (wrong type): {stats['skipped_wrong_type']:,}")
    print(f"  Skipped (REP in dereg): {stats['skipped_rep_in_dereg']:,}")
    
    print(f"\nTop states:")
    for state, count in sorted(stats['by_state'].items(), key=lambda x: -x[1])[:10]:
        print(f"  {state}: {count:,}")
    
    # Generate override files
    print("\nGenerating override files...")
    results = generate_override_files(processed)
    results['processing_stats'] = stats
    
    print(f"\nOverride stats:")
    ostats = results['stats']
    print(f"  Total ZIP+street combos: {ostats['total_zip_streets']:,}")
    print(f"  Hard overrides (95%+): {ostats['hard_override_count']:,}")
    print(f"  AI boost (80-95%): {ostats['ai_boost_count']:,}")
    print(f"  AI context (70-80%): {ostats['ai_context_count']:,}")
    print(f"  Store only (<70%): {ostats['store_only_count']:,}")
    print(f"  Flag for review: {ostats['flag_review_count']:,}")
    print(f"  Split territory ZIPs: {len(ostats['split_territory_zips']):,}")
    
    # Save files
    print("\nSaving output files...")
    save_output_files(results)
    
    # Show sample overrides
    print("\n" + "="*60)
    print("SAMPLE HARD OVERRIDES")
    print("="*60)
    
    sample_count = 0
    for zip_code, streets in list(results['hard_overrides'].items())[:5]:
        print(f"\nZIP {zip_code}:")
        for street, data in list(streets.items())[:3]:
            print(f"  {street} → {data['electric']} ({data['sample_count']} samples, {data['confidence']*100:.0f}%)")
        sample_count += 1
    
    print("\n" + "="*60)
    print("DONE")
    print("="*60)


if __name__ == '__main__':
    main()
