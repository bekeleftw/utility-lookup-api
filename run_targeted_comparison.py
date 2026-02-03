#!/usr/bin/env python3
"""
Targeted API comparison - prioritizes high-value and uncovered ZIPs
"""

import sys
import json
import time
import os
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

os.environ['DATABASE_URL'] = "postgresql://postgres:uLsIMDrAWOhRMynIASQVrRcHpnCfLRki@gondola.proxy.rlwy.net:21850/railway"

sys.path.insert(0, '.')
from utility_lookup_currently_deployed import lookup_utilities_by_address

def process_address(row_data):
    """Process a single address."""
    addr = row_data['address']
    
    try:
        result = lookup_utilities_by_address(
            addr, 
            selected_utilities=['electric', 'gas', 'water'],
            skip_internet=True
        )
        
        if result:
            return {
                'address': addr,
                'zip': row_data.get('zip', ''),
                'mapped_electric': row_data.get('electric', ''),
                'mapped_gas': row_data.get('gas', ''),
                'mapped_water': row_data.get('water', ''),
                'api_electric': result.get('electric', {}).get('NAME', '') if result.get('electric') else '',
                'api_gas': result.get('gas', {}).get('NAME', '') if result.get('gas') else '',
                'api_water': result.get('water', {}).get('name', '') if result.get('water') else '',
                'success': True
            }
        return {'address': addr, 'success': False, 'error': 'No result'}
    except Exception as e:
        return {'address': addr, 'success': False, 'error': str(e)[:100]}

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--workers', type=int, default=30, help='Number of parallel workers')
    parser.add_argument('--input', type=str, default='targeted_sample_74k.json', help='Input sample file')
    parser.add_argument('--output', type=str, default='targeted_comparison_74k.json', help='Output file')
    parser.add_argument('--resume', action='store_true', help='Resume from existing output file')
    args = parser.parse_args()
    
    # Load existing results if resuming
    existing_addresses = set()
    existing_results = []
    if args.resume:
        try:
            with open(args.output, 'r') as f:
                existing_results = json.load(f)
            existing_addresses = {r['address'] for r in existing_results}
            print(f"Resuming: {len(existing_results)} already processed")
        except:
            print("No existing results found, starting fresh")
    
    # Load sample
    print(f"Loading sample from {args.input}...")
    with open(args.input, 'r') as f:
        samples = json.load(f)
    
    # Filter out already processed
    if existing_addresses:
        samples = [s for s in samples if s['address'] not in existing_addresses]
        print(f"After filtering: {len(samples)} remaining")
    
    print(f"Processing {len(samples)} addresses with {args.workers} workers")
    print(f"Estimated time: {len(samples) / 1.7 / 3600:.1f} hours (at 1.7/s)")
    print("-" * 50)
    
    results = existing_results.copy()
    errors = 0
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process_address, s): i for i, s in enumerate(samples)}
        
        completed = 0
        for future in as_completed(futures):
            result = future.result()
            completed += 1
            
            if result.get('success'):
                results.append(result)
            else:
                errors += 1
            
            if completed % 100 == 0:
                elapsed = time.time() - start_time
                rate = completed / elapsed
                remaining = len(samples) - completed
                eta = remaining / rate / 60
                print(f"  {completed}/{len(samples)} ({len(results)} ok, {errors} err) - {rate:.1f}/s - ETA: {eta:.1f}m")
                
                # Checkpoint save
                with open(args.output, 'w') as f:
                    json.dump(results, f)
    
    elapsed = time.time() - start_time
    print(f"\nCompleted in {elapsed/60:.1f} minutes")
    print(f"Results: {len(results)} success, {errors} errors")
    print(f"Rate: {len(samples)/elapsed:.2f} addresses/second")
    
    with open(args.output, 'w') as f:
        json.dump(results, f)
    print(f"Saved to {args.output}")

if __name__ == "__main__":
    main()
