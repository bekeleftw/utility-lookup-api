#!/usr/bin/env python3
"""
Concurrent AI Boundary Analyzer

Processes addresses in parallel for much faster analysis.
"""

import csv
import json
import os
import re
import sys
import time
import requests
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Dict, List, Tuple
import threading

# Thread-safe counter
class Counter:
    def __init__(self):
        self.value = 0
        self.lock = threading.Lock()
    
    def increment(self):
        with self.lock:
            self.value += 1
            return self.value

def load_openai_key():
    key = os.environ.get('OPENAI_API_KEY')
    if key:
        return key
    for env_file in ['.env', os.path.expanduser('~/.env')]:
        if os.path.exists(env_file):
            with open(env_file, 'r') as f:
                for line in f:
                    if line.startswith('OPENAI_API_KEY='):
                        return line.split('=', 1)[1].strip().strip('"\'')
    return None

def compare_single_address(args: Tuple) -> Dict:
    """Compare a single address (for parallel execution)."""
    row, lookup_func = args
    
    address = row.get('display', '')
    tenant = row.get('Electricity', '').strip()
    
    if not address or not tenant:
        return None
    
    zip_match = re.search(r'(\d{5})', address)
    zip_code = zip_match.group(1) if zip_match else None
    
    if not zip_code:
        return None
    
    # Suppress stdout during lookup
    import io
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        result = lookup_func(address, selected_utilities=['electric'])
        ours = result.get('electric', {}).get('NAME', '') if result and result.get('electric') else ''
        source = result.get('electric', {}).get('_source', '') if result and result.get('electric') else ''
    except Exception as e:
        ours = ''
        source = 'error'
    finally:
        sys.stdout = old_stdout
    
    # Check match
    t_norm = tenant.lower()[:15]
    o_norm = ours.lower()[:15]
    is_match = t_norm in o_norm or o_norm in t_norm or t_norm == o_norm
    
    return {
        'address': address,
        'zip_code': zip_code,
        'tenant': tenant,
        'ours': ours,
        'source': source,
        'is_match': is_match
    }

def analyze_zip_with_ai(zip_code: str, records: List[Dict], api_key: str) -> Dict:
    """Use AI to analyze a ZIP's mismatches."""
    city_match = re.search(r',\s*([^,]+),\s*([A-Z]{2})\s+\d{5}', records[0]['address'])
    city = city_match.group(1) if city_match else 'Unknown'
    state = city_match.group(2) if city_match else 'Unknown'
    
    addresses_text = "\n".join([
        f"- {r['address']}\n  Tenant: {r['tenant']}\n  Our API: {r['ours']}"
        for r in records[:15]
    ])
    
    prompt = f"""Analyze utility discrepancies for ZIP {zip_code} ({city}, {state}):

{addresses_text}

Determine:
1. Geographic pattern (street names, areas, number ranges)?
2. Who is correct - tenant or our API?
3. What boundary rule should we add?

JSON response:
{{"insight_type": "boundary_rule|tenant_error|split_territory|data_gap", "description": "summary", "pattern": "geographic pattern or null", "affected_utility": "utility", "confidence": 0.0-1.0, "reasoning": "brief explanation"}}"""

    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "Utility territory expert. Valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.2,
                "max_tokens": 400
            },
            timeout=30
        )
        response.raise_for_status()
        
        result_text = response.json()["choices"][0]["message"]["content"]
        if "```" in result_text:
            result_text = re.search(r'```(?:json)?\s*(.*?)\s*```', result_text, re.DOTALL).group(1)
        
        result = json.loads(result_text.strip())
        return {
            'zip_code': zip_code,
            'city': city,
            'state': state,
            'mismatch_count': len(records),
            **result
        }
    except Exception as e:
        return {
            'zip_code': zip_code,
            'city': city,
            'state': state,
            'error': str(e)
        }

def run_concurrent_analysis(
    csv_file: str,
    max_addresses: int = None,
    max_zips: int = None,
    address_workers: int = 20,
    ai_workers: int = 10
):
    """
    Run the full analysis with concurrency.
    
    Args:
        csv_file: Path to tenant verification CSV
        max_addresses: Limit addresses (None = all)
        max_zips: Limit ZIPs for AI analysis (None = all)
        address_workers: Concurrent threads for address comparison
        ai_workers: Concurrent threads for AI analysis
    """
    print("="*60)
    print("CONCURRENT AI BOUNDARY ANALYZER")
    print("="*60)
    
    api_key = load_openai_key()
    if not api_key:
        print("ERROR: No OpenAI API key found")
        return
    print(f"API key loaded (ends with ...{api_key[-4:]})")
    
    # Load data
    print(f"\nLoading {csv_file}...")
    with open(csv_file, 'r') as f:
        rows = list(csv.DictReader(f))
    
    if max_addresses:
        rows = rows[:max_addresses]
    
    print(f"Processing {len(rows):,} addresses with {address_workers} workers...")
    
    # Phase 1: Concurrent address comparison
    from utility_lookup_v1 import lookup_utilities_by_address
    
    results = []
    counter = Counter()
    start_time = time.time()
    
    def process_with_progress(row):
        result = compare_single_address((row, lookup_utilities_by_address))
        count = counter.increment()
        if count % 100 == 0:
            elapsed = time.time() - start_time
            rate = count / elapsed
            remaining = (len(rows) - count) / rate if rate > 0 else 0
            print(f"  {count:,}/{len(rows):,} ({rate:.1f}/sec, ~{remaining:.0f}s remaining)")
        return result
    
    with ThreadPoolExecutor(max_workers=address_workers) as executor:
        futures = [executor.submit(process_with_progress, row) for row in rows]
        for future in as_completed(futures):
            result = future.result()
            if result:
                results.append(result)
    
    elapsed = time.time() - start_time
    print(f"\nPhase 1 complete: {len(results):,} addresses in {elapsed:.1f}s ({len(results)/elapsed:.1f}/sec)")
    
    # Group mismatches by ZIP
    mismatches = defaultdict(list)
    matches = 0
    for r in results:
        if r['is_match']:
            matches += 1
        else:
            mismatches[r['zip_code']].append(r)
    
    mismatch_count = sum(len(v) for v in mismatches.values())
    print(f"Matches: {matches:,} ({matches/len(results)*100:.1f}%)")
    print(f"Mismatches: {mismatch_count:,} ({mismatch_count/len(results)*100:.1f}%)")
    print(f"ZIPs with mismatches: {len(mismatches)}")
    
    # Save Phase 1 results
    os.makedirs('data', exist_ok=True)
    with open('data/phase1_comparison_results.json', 'w') as f:
        json.dump({
            'stats': {'total': len(results), 'matches': matches, 'mismatches': mismatch_count},
            'mismatches': {k: v for k, v in mismatches.items()}
        }, f, indent=2)
    print("Saved Phase 1 results to data/phase1_comparison_results.json")
    
    # Phase 2: Concurrent AI analysis
    zips_to_analyze = sorted(mismatches.items(), key=lambda x: -len(x[1]))
    if max_zips:
        zips_to_analyze = zips_to_analyze[:max_zips]
    
    print(f"\nPhase 2: AI analyzing {len(zips_to_analyze)} ZIPs with {ai_workers} workers...")
    
    insights = []
    ai_counter = Counter()
    ai_start = time.time()
    
    def analyze_with_progress(item):
        zip_code, records = item
        result = analyze_zip_with_ai(zip_code, records, api_key)
        count = ai_counter.increment()
        if count % 10 == 0:
            print(f"  AI: {count}/{len(zips_to_analyze)} ZIPs analyzed...")
        return result
    
    with ThreadPoolExecutor(max_workers=ai_workers) as executor:
        futures = [executor.submit(analyze_with_progress, item) for item in zips_to_analyze]
        for future in as_completed(futures):
            result = future.result()
            if result and 'error' not in result:
                insights.append(result)
    
    ai_elapsed = time.time() - ai_start
    print(f"\nPhase 2 complete: {len(insights)} insights in {ai_elapsed:.1f}s")
    
    # Save insights
    with open('data/ai_boundary_insights.json', 'w') as f:
        json.dump({
            'version': '1.0',
            'updated_at': datetime.now().isoformat(),
            'insight_count': len(insights),
            'insights': insights
        }, f, indent=2)
    print("Saved insights to data/ai_boundary_insights.json")
    
    # Summary
    print("\n" + "="*60)
    print("INSIGHTS SUMMARY")
    print("="*60)
    
    by_type = defaultdict(list)
    for i in insights:
        by_type[i.get('insight_type', 'unknown')].append(i)
    
    for itype, items in sorted(by_type.items(), key=lambda x: -len(x[1])):
        print(f"\n{itype.upper()}: {len(items)} ZIPs")
        for item in items[:3]:
            print(f"  {item['zip_code']} ({item['city']}, {item['state']}): {item.get('description', 'N/A')[:60]}...")
    
    return insights


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--max-addresses', type=int, default=None, help='Limit addresses')
    parser.add_argument('--max-zips', type=int, default=None, help='Limit ZIPs for AI')
    parser.add_argument('--address-workers', type=int, default=20, help='Concurrent address lookups')
    parser.add_argument('--ai-workers', type=int, default=10, help='Concurrent AI calls')
    args = parser.parse_args()
    
    run_concurrent_analysis(
        'addresses_with_tenant_verification.csv',
        max_addresses=args.max_addresses,
        max_zips=args.max_zips,
        address_workers=args.address_workers,
        ai_workers=args.ai_workers
    )
