#!/usr/bin/env python3
"""
High-concurrency API comparison - 30 workers
For running larger samples from the mapped providers dataset
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
    parser.add_argument('--sample', type=int, default=10000, help='Number of addresses to process')
    parser.add_argument('--output', type=str, default='massive_comparison_results.json', help='Output file')
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
    
    # Load mapped providers
    print(f"Loading mapped providers...")
    df = pd.read_csv("all mapped providers.csv")
    
    # Extract ZIP from address
    df['zip'] = df['Address'].str.extract(r'(\d{5})')
    
    # Rename columns
    df = df.rename(columns={
        'Address': 'address',
        'Electricity': 'electric',
        'Gas': 'gas',
        'Water': 'water'
    })
    
    # Sample - prioritize addresses from ZIPs with known splits
    try:
        with open("data/real_sub_zip_splits.json", "r") as f:
            splits = json.load(f)
        split_zips = set(splits['splits'].keys())
        
        # Get addresses from split ZIPs first
        split_df = df[df['zip'].isin(split_zips)]
        other_df = df[~df['zip'].isin(split_zips)]
        
        # Take all from split ZIPs, then random sample from others
        split_sample = split_df.to_dict('records')
        remaining = args.sample - len(split_sample)
        if remaining > 0:
            other_sample = other_df.sample(n=min(remaining, len(other_df))).to_dict('records')
        else:
            other_sample = []
        
        samples = split_sample + other_sample
        print(f"Sample: {len(split_sample)} from split ZIPs, {len(other_sample)} random")
    except:
        samples = df.sample(n=min(args.sample, len(df))).to_dict('records')
    
    # Filter out already processed addresses if resuming
    if existing_addresses:
        samples = [s for s in samples if s['address'] not in existing_addresses]
        print(f"After filtering already processed: {len(samples)} remaining")
    
    print(f"Processing {len(samples)} addresses with {args.workers} workers")
    print(f"Estimated time: {len(samples) / (args.workers * 0.07):.1f} minutes")
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
