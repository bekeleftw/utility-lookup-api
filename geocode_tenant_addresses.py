#!/usr/bin/env python3
"""
Geocode Tenant Addresses

Geocodes all 87K tenant addresses using:
1. Census Geocoder (free, primary)
2. Nominatim/OSM (free, fallback)
3. Google (paid, last resort)

Saves results to data/tenant_addresses_geocoded.json
"""

import csv
import json
import os
import re
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Dict, Optional
import threading

# Rate limiting
census_semaphore = threading.Semaphore(5)  # Census: conservative to avoid blocking
nominatim_semaphore = threading.Semaphore(1)  # Nominatim: 1 req/sec strict
google_semaphore = threading.Semaphore(20)  # Google fallback

# Stats tracking
stats = {
    'total': 0,
    'success': 0,
    'census_success': 0,
    'nominatim_success': 0,
    'google_success': 0,
    'failed': 0
}
stats_lock = threading.Lock()

def load_google_api_key():
    """Load Google API key from environment or .env file."""
    key = os.environ.get('GOOGLE_MAPS_API_KEY') or os.environ.get('GOOGLE_API_KEY')
    if key:
        return key
    
    for env_file in ['.env', os.path.expanduser('~/.env')]:
        if os.path.exists(env_file):
            with open(env_file, 'r') as f:
                for line in f:
                    if 'GOOGLE' in line and 'API' in line and 'KEY' in line:
                        return line.split('=', 1)[1].strip().strip('"\'')
    return None

GOOGLE_API_KEY = load_google_api_key()


def geocode_census(address: str) -> Optional[Dict]:
    """Geocode using US Census Bureau geocoder."""
    with census_semaphore:
        try:
            url = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
            params = {
                'address': address,
                'benchmark': 'Public_AR_Current',
                'format': 'json'
            }
            response = requests.get(url, params=params, timeout=8)
            response.raise_for_status()
            data = response.json()
            
            matches = data.get('result', {}).get('addressMatches', [])
            if matches:
                match = matches[0]
                coords = match.get('coordinates', {})
                return {
                    'lat': coords.get('y'),
                    'lon': coords.get('x'),
                    'formatted_address': match.get('matchedAddress'),
                    'source': 'census'
                }
        except Exception as e:
            pass
        return None


def geocode_nominatim(address: str) -> Optional[Dict]:
    """Geocode using OpenStreetMap Nominatim (free)."""
    with nominatim_semaphore:
        try:
            url = "https://nominatim.openstreetmap.org/search"
            params = {
                'q': address,
                'format': 'json',
                'limit': 1,
                'countrycodes': 'us'
            }
            headers = {'User-Agent': 'UtilityLookup/1.0'}
            response = requests.get(url, params=params, headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            if data:
                result = data[0]
                return {
                    'lat': float(result.get('lat')),
                    'lon': float(result.get('lon')),
                    'formatted_address': result.get('display_name'),
                    'source': 'nominatim'
                }
            time.sleep(1)  # Rate limit
        except Exception as e:
            pass
        return None


def geocode_google(address: str) -> Optional[Dict]:
    """Geocode using Google Maps API (paid)."""
    if not GOOGLE_API_KEY:
        return None
    
    with google_semaphore:
        try:
            url = "https://maps.googleapis.com/maps/api/geocode/json"
            params = {
                'address': address,
                'key': GOOGLE_API_KEY
            }
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get('status') == 'OK' and data.get('results'):
                result = data['results'][0]
                location = result.get('geometry', {}).get('location', {})
                return {
                    'lat': location.get('lat'),
                    'lon': location.get('lng'),
                    'formatted_address': result.get('formatted_address'),
                    'source': 'google'
                }
        except Exception as e:
            pass
        return None


def geocode_address(address: str, prefer_google: bool = False) -> Optional[Dict]:
    """
    Geocode an address using cascading fallback.
    
    If prefer_google=True: Google -> Census -> Nominatim (faster)
    If prefer_google=False: Census -> Nominatim -> Google (cheaper)
    """
    if prefer_google and GOOGLE_API_KEY:
        # Google first for speed
        result = geocode_google(address)
        if result:
            with stats_lock:
                stats['google_success'] += 1
            return result
        
        # Census fallback
        result = geocode_census(address)
        if result:
            with stats_lock:
                stats['census_success'] += 1
            return result
    else:
        # Census first for cost
        result = geocode_census(address)
        if result:
            with stats_lock:
                stats['census_success'] += 1
            return result
        
        # Google fallback
        result = geocode_google(address)
        if result:
            with stats_lock:
                stats['google_success'] += 1
            return result
    
    # Nominatim as last resort (slow)
    result = geocode_nominatim(address)
    if result:
        with stats_lock:
            stats['nominatim_success'] += 1
        return result
    
    return None


def geocode_single_record(record: Dict, prefer_google: bool = False) -> Dict:
    """Geocode a single tenant record."""
    address = record.get('display', '')
    
    result = geocode_address(address, prefer_google=prefer_google)
    
    if result:
        with stats_lock:
            stats['success'] += 1
        return {
            'address': address,
            'lat': result['lat'],
            'lon': result['lon'],
            'geocode_source': result['source'],
            'electricity': record.get('Electricity', ''),
            'gas': record.get('Gas', '')
        }
    else:
        with stats_lock:
            stats['failed'] += 1
        return {
            'address': address,
            'lat': None,
            'lon': None,
            'geocode_source': 'failed',
            'electricity': record.get('Electricity', ''),
            'gas': record.get('Gas', '')
        }


def geocode_all_addresses(
    csv_file: str,
    output_file: str = 'data/tenant_addresses_geocoded.json',
    max_records: int = None,
    workers: int = 20,
    prefer_google: bool = False
):
    """
    Geocode all addresses from tenant CSV.
    
    Args:
        csv_file: Path to tenant verification CSV
        output_file: Where to save results
        max_records: Limit records (None = all)
        workers: Concurrent workers (limited by API rate limits)
    """
    print("="*60)
    print("GEOCODING TENANT ADDRESSES")
    print("="*60)
    
    # Check for Google API key
    if GOOGLE_API_KEY:
        print(f"Google API key loaded (fallback available)")
    else:
        print("No Google API key - using Census + Nominatim only")
    
    # Load data
    print(f"\nLoading {csv_file}...")
    with open(csv_file, 'r') as f:
        records = list(csv.DictReader(f))
    
    if max_records:
        records = records[:max_records]
    
    stats['total'] = len(records)
    print(f"Processing {len(records):,} addresses with {workers} workers...", flush=True)
    
    # Process with concurrency
    results = []
    start_time = time.time()
    completed = 0
    
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(geocode_single_record, r, prefer_google): r for r in records}
        
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            completed += 1
            
            if completed % 100 == 0:
                elapsed = time.time() - start_time
                rate = completed / elapsed
                remaining = (len(records) - completed) / rate if rate > 0 else 0
                print(f"  {completed:,}/{len(records):,} ({rate:.1f}/sec, ~{remaining/60:.1f}min left) | Census: {stats['census_success']}, Google: {stats['google_success']}, Failed: {stats['failed']}", flush=True)
    
    elapsed = time.time() - start_time
    
    # Save results
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w') as f:
        json.dump({
            'generated_at': datetime.now().isoformat(),
            'total_records': len(results),
            'geocoded': stats['success'],
            'failed': stats['failed'],
            'by_source': {
                'census': stats['census_success'],
                'nominatim': stats['nominatim_success'],
                'google': stats['google_success']
            },
            'addresses': results
        }, f, indent=2)
    
    print(f"\n" + "="*60)
    print("GEOCODING COMPLETE")
    print("="*60)
    print(f"Total: {len(results):,} addresses in {elapsed:.1f}s ({len(results)/elapsed:.1f}/sec)")
    print(f"Success: {stats['success']:,} ({stats['success']/len(results)*100:.1f}%)")
    print(f"  Census: {stats['census_success']:,}")
    print(f"  Nominatim: {stats['nominatim_success']:,}")
    print(f"  Google: {stats['google_success']:,}")
    print(f"Failed: {stats['failed']:,}")
    print(f"\nSaved to {output_file}")
    
    return results


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--max', type=int, default=None, help='Max records to process')
    parser.add_argument('--workers', type=int, default=20, help='Concurrent workers')
    parser.add_argument('--fast', action='store_true', help='Use Google first (faster but costs money)')
    args = parser.parse_args()
    
    geocode_all_addresses(
        'addresses_with_tenant_verification.csv',
        max_records=args.max,
        workers=args.workers,
        prefer_google=args.fast
    )
