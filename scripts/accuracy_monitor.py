#!/usr/bin/env python3
"""
Weekly accuracy validation script.
Samples recent lookups and re-verifies with SERP to detect accuracy drift.

Usage:
    python scripts/accuracy_monitor.py
    python scripts/accuracy_monitor.py --sample-size 50
"""

import json
import os
import sys
import random
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REPORTS_DIR = Path(__file__).parent.parent / 'data' / 'reports'
LOOKUPS_LOG_FILE = Path(__file__).parent.parent / 'data' / 'lookups_log.json'


def get_recent_lookups(limit: int = 1000) -> List[Dict]:
    """Load recent lookups from log file."""
    if not LOOKUPS_LOG_FILE.exists():
        print(f"No lookups log found at {LOOKUPS_LOG_FILE}")
        return []
    
    with open(LOOKUPS_LOG_FILE, 'r') as f:
        lookups = json.load(f)
    
    return lookups[-limit:]


def verify_with_serp_only(address: str) -> Optional[Dict]:
    """
    Verify utilities using only SERP (Google search).
    Returns dict with electric, gas, water providers found.
    """
    try:
        from utility_lookup import verify_utility_with_serp
        
        result = {}
        
        # Verify electric
        serp_electric = verify_utility_with_serp(address, "electric", None)
        if serp_electric and serp_electric.get("serp_provider"):
            result['electric'] = serp_electric.get("serp_provider")
        
        # Verify gas
        serp_gas = verify_utility_with_serp(address, "natural gas", None)
        if serp_gas and serp_gas.get("serp_provider"):
            result['gas'] = serp_gas.get("serp_provider")
        
        # Verify water
        serp_water = verify_utility_with_serp(address, "water", None)
        if serp_water and serp_water.get("serp_provider"):
            result['water'] = serp_water.get("serp_provider")
        
        return result
    except Exception as e:
        print(f"SERP verification error for {address}: {e}")
        return None


def normalize_provider_name(name: str) -> str:
    """Normalize provider name for comparison."""
    if not name:
        return ""
    
    name = name.upper().strip()
    
    # Remove common suffixes
    suffixes = [
        ' INC', ' INC.', ' LLC', ' CORP', ' CORPORATION', ' COMPANY', ' CO',
        ' UTILITY', ' UTILITIES', ' ELECTRIC', ' ENERGY', ' GAS', ' WATER',
        ' DEPARTMENT', ' DEPT', ' DIVISION', ' DIV', ' SERVICE', ' SERVICES',
        ' AUTHORITY', ' DISTRICT', ' SYSTEM', ' SYSTEMS'
    ]
    
    for suffix in suffixes:
        if name.endswith(suffix):
            name = name[:-len(suffix)].strip()
    
    # Remove punctuation
    name = name.replace(',', '').replace('.', '').replace('&', 'AND')
    
    return name


def providers_match(provider1: str, provider2: str) -> bool:
    """Check if two provider names match (fuzzy)."""
    if not provider1 or not provider2:
        return False
    
    norm1 = normalize_provider_name(provider1)
    norm2 = normalize_provider_name(provider2)
    
    # Exact match
    if norm1 == norm2:
        return True
    
    # One contains the other
    if norm1 in norm2 or norm2 in norm1:
        return True
    
    # Check for key word overlap
    words1 = set(norm1.split())
    words2 = set(norm2.split())
    
    # Remove common words
    common_words = {'THE', 'OF', 'AND', 'CITY', 'COUNTY', 'PUBLIC'}
    words1 = words1 - common_words
    words2 = words2 - common_words
    
    # At least 50% word overlap
    if words1 and words2:
        overlap = len(words1 & words2)
        min_words = min(len(words1), len(words2))
        if overlap >= min_words * 0.5:
            return True
    
    return False


def run_validation(sample_size: int = 100) -> Dict:
    """
    Run accuracy validation on sample of recent lookups.
    
    Returns:
        Report dict with accuracy metrics and mismatches
    """
    print(f"Loading recent lookups...")
    recent_lookups = get_recent_lookups(limit=1000)
    
    if not recent_lookups:
        print("No recent lookups to validate")
        return {'error': 'No recent lookups found'}
    
    print(f"Found {len(recent_lookups)} recent lookups")
    
    # Random sample
    sample = random.sample(recent_lookups, min(sample_size, len(recent_lookups)))
    print(f"Validating {len(sample)} lookups...")
    
    results = []
    for i, lookup in enumerate(sample):
        address = lookup.get('address')
        if not address:
            continue
        
        print(f"  [{i+1}/{len(sample)}] {address[:50]}...")
        
        serp_result = verify_with_serp_only(address)
        
        if not serp_result:
            continue
        
        comparison = {
            'address': address,
            'state': lookup.get('state'),
            'original_electric': lookup.get('electric_provider'),
            'serp_electric': serp_result.get('electric'),
            'electric_match': providers_match(
                lookup.get('electric_provider'),
                serp_result.get('electric')
            ),
            'original_gas': lookup.get('gas_provider'),
            'serp_gas': serp_result.get('gas'),
            'gas_match': providers_match(
                lookup.get('gas_provider'),
                serp_result.get('gas')
            ),
            'original_water': lookup.get('water_provider'),
            'serp_water': serp_result.get('water'),
            'water_match': providers_match(
                lookup.get('water_provider'),
                serp_result.get('water')
            )
        }
        results.append(comparison)
    
    if not results:
        return {'error': 'No results from validation'}
    
    # Calculate accuracy by utility type
    electric_results = [r for r in results if r['original_electric'] or r['serp_electric']]
    gas_results = [r for r in results if r['original_gas'] or r['serp_gas']]
    water_results = [r for r in results if r['original_water'] or r['serp_water']]
    
    accuracy = {
        'electric': sum(r['electric_match'] for r in electric_results) / len(electric_results) if electric_results else None,
        'gas': sum(r['gas_match'] for r in gas_results) / len(gas_results) if gas_results else None,
        'water': sum(r['water_match'] for r in water_results) / len(water_results) if water_results else None,
        'sample_size': len(results),
        'timestamp': datetime.utcnow().isoformat()
    }
    
    # Calculate accuracy by state
    state_accuracy = {}
    for state in set(r['state'] for r in results if r['state']):
        state_results = [r for r in results if r['state'] == state]
        if len(state_results) >= 3:  # Minimum sample size
            state_electric = [r for r in state_results if r['original_electric'] or r['serp_electric']]
            state_gas = [r for r in state_results if r['original_gas'] or r['serp_gas']]
            state_water = [r for r in state_results if r['original_water'] or r['serp_water']]
            
            state_accuracy[state] = {
                'electric': sum(r['electric_match'] for r in state_electric) / len(state_electric) if state_electric else None,
                'gas': sum(r['gas_match'] for r in state_gas) / len(state_gas) if state_gas else None,
                'water': sum(r['water_match'] for r in state_water) / len(state_water) if state_water else None,
                'sample_size': len(state_results)
            }
    
    # Flag mismatches for review
    mismatches = [r for r in results if not all([
        r['electric_match'] or (not r['original_electric'] and not r['serp_electric']),
        r['gas_match'] or (not r['original_gas'] and not r['serp_gas']),
        r['water_match'] or (not r['original_water'] and not r['serp_water'])
    ])]
    
    # Generate alerts
    alerts = []
    if accuracy['electric'] and accuracy['electric'] < 0.90:
        alerts.append(f"Electric accuracy dropped to {accuracy['electric']:.1%}")
    if accuracy['gas'] and accuracy['gas'] < 0.85:
        alerts.append(f"Gas accuracy dropped to {accuracy['gas']:.1%}")
    if accuracy['water'] and accuracy['water'] < 0.80:
        alerts.append(f"Water accuracy dropped to {accuracy['water']:.1%}")
    
    report = {
        'overall_accuracy': accuracy,
        'state_accuracy': state_accuracy,
        'mismatches': mismatches[:20],  # Limit to 20 for readability
        'mismatch_count': len(mismatches),
        'alerts': alerts,
        'generated_at': datetime.utcnow().isoformat()
    }
    
    return report


def save_report(report: Dict):
    """Save report to file."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    
    date_str = datetime.utcnow().strftime('%Y_%m_%d')
    report_file = REPORTS_DIR / f'accuracy_{date_str}.json'
    
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"Report saved to {report_file}")
    
    # Also save as latest
    latest_file = REPORTS_DIR / 'accuracy_latest.json'
    with open(latest_file, 'w') as f:
        json.dump(report, f, indent=2)


def print_report(report: Dict):
    """Print report summary to console."""
    print("\n" + "="*60)
    print("ACCURACY VALIDATION REPORT")
    print("="*60)
    
    if 'error' in report:
        print(f"Error: {report['error']}")
        return
    
    accuracy = report.get('overall_accuracy', {})
    print(f"\nSample Size: {accuracy.get('sample_size', 0)}")
    print(f"Generated: {report.get('generated_at', 'N/A')}")
    
    print("\n--- Overall Accuracy ---")
    if accuracy.get('electric') is not None:
        print(f"  Electric: {accuracy['electric']:.1%}")
    if accuracy.get('gas') is not None:
        print(f"  Gas: {accuracy['gas']:.1%}")
    if accuracy.get('water') is not None:
        print(f"  Water: {accuracy['water']:.1%}")
    
    state_accuracy = report.get('state_accuracy', {})
    if state_accuracy:
        print("\n--- Accuracy by State (top 5) ---")
        sorted_states = sorted(
            state_accuracy.items(),
            key=lambda x: x[1].get('sample_size', 0),
            reverse=True
        )[:5]
        for state, data in sorted_states:
            print(f"  {state}: E={data.get('electric', 'N/A'):.0%} G={data.get('gas', 'N/A'):.0%} W={data.get('water', 'N/A'):.0%} (n={data.get('sample_size', 0)})")
    
    alerts = report.get('alerts', [])
    if alerts:
        print("\n--- ALERTS ---")
        for alert in alerts:
            print(f"  ⚠️  {alert}")
    
    mismatch_count = report.get('mismatch_count', 0)
    if mismatch_count > 0:
        print(f"\n--- Mismatches ({mismatch_count} total) ---")
        for m in report.get('mismatches', [])[:5]:
            print(f"  {m['address'][:40]}...")
            if not m['electric_match'] and (m['original_electric'] or m['serp_electric']):
                print(f"    Electric: {m['original_electric']} vs {m['serp_electric']}")
            if not m['gas_match'] and (m['original_gas'] or m['serp_gas']):
                print(f"    Gas: {m['original_gas']} vs {m['serp_gas']}")
            if not m['water_match'] and (m['original_water'] or m['serp_water']):
                print(f"    Water: {m['original_water']} vs {m['serp_water']}")
    
    print("\n" + "="*60)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Run accuracy validation')
    parser.add_argument('--sample-size', type=int, default=100, help='Number of lookups to validate')
    parser.add_argument('--no-save', action='store_true', help='Do not save report to file')
    args = parser.parse_args()
    
    print("Starting accuracy validation...")
    report = run_validation(sample_size=args.sample_size)
    
    print_report(report)
    
    if not args.no_save and 'error' not in report:
        save_report(report)


if __name__ == '__main__':
    main()
