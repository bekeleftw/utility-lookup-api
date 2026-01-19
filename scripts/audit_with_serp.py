"""
Batch SERP Audit Script

Samples recent lookups and verifies them with SERP to track accuracy.

Usage:
    python scripts/audit_with_serp.py --sample-size 50
    python scripts/audit_with_serp.py --sample-size 20 --state TX
    python scripts/audit_with_serp.py --utility-type gas --sample-size 30
"""

import argparse
import json
import os
import sys
import random
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from serp_verification import verify_utility_via_serp, is_alias

LOOKUPS_LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'lookup_log.json')
AUDIT_REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'audit_reports')


def load_recent_lookups(days: int = 30, state: str = None) -> list:
    """Load recent lookup results from log."""
    if not os.path.exists(LOOKUPS_LOG_FILE):
        print(f"No lookup log found at {LOOKUPS_LOG_FILE}")
        return []
    
    with open(LOOKUPS_LOG_FILE, 'r') as f:
        all_lookups = json.load(f)
    
    # Filter by date
    cutoff = datetime.now() - timedelta(days=days)
    recent = []
    for l in all_lookups:
        try:
            ts = datetime.fromisoformat(l.get('timestamp', '2000-01-01'))
            if ts > cutoff:
                recent.append(l)
        except (ValueError, TypeError):
            continue
    
    # Filter by state if specified
    if state:
        recent = [l for l in recent if l.get('state', '').upper() == state.upper()]
    
    return recent


def sample_lookups(lookups: list, sample_size: int) -> list:
    """Randomly sample lookups for validation."""
    if len(lookups) <= sample_size:
        return lookups
    return random.sample(lookups, sample_size)


def audit_lookup(lookup: dict, utility_type: str) -> dict:
    """Verify a single lookup with SERP."""
    address = lookup.get('address', '')
    city = lookup.get('city', '')
    state = lookup.get('state', '')
    zip_code = lookup.get('zip_code', '')
    
    # Get the expected utility based on type
    if utility_type == 'electric':
        expected = lookup.get('electric_provider', '')
    elif utility_type == 'gas':
        expected = lookup.get('gas_provider', '')
    elif utility_type == 'water':
        expected = lookup.get('water_provider', '')
    else:
        expected = ''
    
    if not expected:
        return {
            'address': address,
            'city': city,
            'state': state,
            'utility_type': utility_type,
            'expected': None,
            'skipped': True,
            'reason': f'No {utility_type} provider in lookup'
        }
    
    # Verify with SERP
    result = verify_utility_via_serp(
        address=address,
        city=city,
        state=state,
        utility_type=utility_type,
        expected_utility=expected,
        zip_code=zip_code
    )
    
    return {
        'address': address,
        'city': city,
        'state': state,
        'zip_code': zip_code,
        'utility_type': utility_type,
        'expected': expected,
        'serp_utility': result.serp_utility,
        'verified': result.verified,
        'confidence_boost': result.confidence_boost,
        'cached': result.cached,
        'notes': result.notes
    }


def calculate_metrics(results: list) -> dict:
    """Calculate accuracy metrics from audit results."""
    total = 0
    verified = 0
    contradicted = 0
    skipped = 0
    cached = 0
    
    contradictions = []
    
    for r in results:
        if r.get('skipped'):
            skipped += 1
            continue
        
        total += 1
        if r.get('cached'):
            cached += 1
        
        if r.get('verified'):
            verified += 1
        else:
            contradicted += 1
            contradictions.append({
                'address': f"{r.get('city')}, {r.get('state')}",
                'expected': r.get('expected'),
                'serp_found': r.get('serp_utility'),
                'notes': r.get('notes')
            })
    
    accuracy = (verified / total * 100) if total > 0 else 0
    
    return {
        'total_audited': total,
        'verified': verified,
        'contradicted': contradicted,
        'skipped': skipped,
        'cached_results': cached,
        'accuracy_percent': round(accuracy, 1),
        'contradictions': contradictions
    }


def save_report(metrics: dict, utility_type: str, state: str = None):
    """Save audit report to file."""
    os.makedirs(AUDIT_REPORTS_DIR, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    state_suffix = f"_{state}" if state else ""
    filename = f"audit_{utility_type}{state_suffix}_{timestamp}.json"
    filepath = os.path.join(AUDIT_REPORTS_DIR, filename)
    
    report = {
        'timestamp': datetime.now().isoformat(),
        'utility_type': utility_type,
        'state_filter': state,
        'metrics': metrics
    }
    
    with open(filepath, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"\nReport saved to: {filepath}")
    return filepath


def main():
    parser = argparse.ArgumentParser(description='Audit utility lookups with SERP verification')
    parser.add_argument('--sample-size', type=int, default=20, help='Number of lookups to audit')
    parser.add_argument('--state', type=str, help='Filter by state (e.g., TX, CA)')
    parser.add_argument('--utility-type', type=str, default='electric', 
                        choices=['electric', 'gas', 'water'], help='Utility type to audit')
    parser.add_argument('--days', type=int, default=30, help='Look back this many days')
    parser.add_argument('--no-cache', action='store_true', help='Skip cached results')
    
    args = parser.parse_args()
    
    print(f"=== SERP Audit: {args.utility_type.upper()} ===")
    print(f"Sample size: {args.sample_size}")
    if args.state:
        print(f"State filter: {args.state}")
    print()
    
    # Load and sample lookups
    lookups = load_recent_lookups(days=args.days, state=args.state)
    print(f"Found {len(lookups)} recent lookups")
    
    if not lookups:
        print("No lookups to audit")
        return
    
    sampled = sample_lookups(lookups, args.sample_size)
    print(f"Auditing {len(sampled)} lookups...")
    print()
    
    # Audit each lookup
    results = []
    for i, lookup in enumerate(sampled, 1):
        city = lookup.get('city', 'Unknown')
        state = lookup.get('state', 'XX')
        print(f"[{i}/{len(sampled)}] Auditing {city}, {state}...", end=' ')
        
        result = audit_lookup(lookup, args.utility_type)
        results.append(result)
        
        if result.get('skipped'):
            print("SKIPPED")
        elif result.get('verified'):
            print("✓ VERIFIED" + (" (cached)" if result.get('cached') else ""))
        else:
            print(f"✗ MISMATCH: expected '{result.get('expected')}', SERP found '{result.get('serp_utility')}'")
    
    # Calculate and display metrics
    metrics = calculate_metrics(results)
    
    print()
    print("=" * 50)
    print("AUDIT RESULTS")
    print("=" * 50)
    print(f"Total audited: {metrics['total_audited']}")
    print(f"Verified:      {metrics['verified']}")
    print(f"Contradicted:  {metrics['contradicted']}")
    print(f"Skipped:       {metrics['skipped']}")
    print(f"Cached:        {metrics['cached_results']}")
    print()
    print(f"ACCURACY: {metrics['accuracy_percent']}%")
    
    if metrics['contradictions']:
        print()
        print("CONTRADICTIONS:")
        for c in metrics['contradictions'][:10]:  # Show first 10
            print(f"  - {c['address']}: expected '{c['expected']}', SERP found '{c['serp_found']}'")
    
    # Save report
    save_report(metrics, args.utility_type, args.state)


if __name__ == '__main__':
    main()
