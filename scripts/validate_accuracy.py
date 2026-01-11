"""
Batch validation of utility lookup accuracy.
Samples recent lookups and re-verifies with Google Search.

Usage:
    python scripts/validate_accuracy.py --sample-size 100
    python scripts/validate_accuracy.py --sample-size 50 --state TX
"""

import argparse
import json
import os
import random
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import time
import sys

# Import from main app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cross_validation import providers_match

LOOKUPS_LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'lookup_log.json')
VALIDATION_REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'validation_reports')

# Accuracy thresholds for alerts
THRESHOLDS = {
    'electric': 90,  # Alert if below 90%
    'gas': 85,
    'water': 80
}


def load_recent_lookups(days: int = 30, state: Optional[str] = None) -> List[Dict]:
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


def sample_lookups(lookups: List[Dict], sample_size: int) -> List[Dict]:
    """Randomly sample lookups for validation."""
    if len(lookups) <= sample_size:
        return lookups
    return random.sample(lookups, sample_size)


def validate_lookup(lookup: Dict, use_serp: bool = False) -> Dict:
    """
    Re-verify a lookup and compare to original result.
    
    If use_serp=True, will query Google (slow, rate-limited).
    Otherwise, just returns the lookup data for manual review.
    """
    address = lookup.get('address', '')
    city = lookup.get('city', '')
    state = lookup.get('state', '')
    
    results = {}
    
    for utility_type in ['electric', 'gas', 'water']:
        original_provider = lookup.get(f'{utility_type}_provider')
        
        if not original_provider:
            continue
        
        serp_provider = None
        
        if use_serp:
            try:
                from utility_lookup import verify_utility_with_serp
                serp_query = f"{utility_type} utility provider for {address}"
                serp_result = verify_utility_with_serp(address, utility_type, original_provider)
                serp_provider = serp_result.get('serp_provider') if serp_result else None
                # Rate limit SERP queries
                time.sleep(2)
            except Exception as e:
                print(f"    SERP error: {e}")
        
        # Compare
        if original_provider and serp_provider:
            match = providers_match(original_provider, serp_provider)
        elif not use_serp:
            match = None  # Can't determine without SERP
        elif not original_provider and not serp_provider:
            match = True  # Both empty
        else:
            match = False
        
        results[utility_type] = {
            'original': original_provider,
            'serp': serp_provider,
            'match': match,
            'notes': '' if match else f"Mismatch: DB={original_provider}, SERP={serp_provider}"
        }
    
    return {
        'address': address,
        'city': city,
        'state': state,
        'zip_code': lookup.get('zip_code'),
        'validated_at': datetime.now().isoformat(),
        'original_timestamp': lookup.get('timestamp'),
        'results': results
    }


def calculate_accuracy(validations: List[Dict]) -> Dict:
    """Calculate accuracy metrics from validation results."""
    metrics = {
        'electric': {'total': 0, 'matches': 0, 'mismatches': [], 'unknown': 0},
        'gas': {'total': 0, 'matches': 0, 'mismatches': [], 'unknown': 0},
        'water': {'total': 0, 'matches': 0, 'mismatches': [], 'unknown': 0}
    }
    
    for v in validations:
        for utility_type, result in v.get('results', {}).items():
            if utility_type not in metrics:
                continue
            
            metrics[utility_type]['total'] += 1
            
            if result.get('match') is True:
                metrics[utility_type]['matches'] += 1
            elif result.get('match') is False:
                metrics[utility_type]['mismatches'].append({
                    'address': v['address'],
                    'zip_code': v.get('zip_code'),
                    'original': result.get('original'),
                    'serp': result.get('serp')
                })
            else:
                metrics[utility_type]['unknown'] += 1
    
    # Calculate percentages
    for utility_type in metrics:
        total = metrics[utility_type]['total']
        matches = metrics[utility_type]['matches']
        unknown = metrics[utility_type]['unknown']
        validated = total - unknown
        metrics[utility_type]['accuracy'] = (matches / validated * 100) if validated > 0 else None
        metrics[utility_type]['validated_count'] = validated
    
    return metrics


def check_accuracy_alerts(metrics: Dict) -> List[str]:
    """Check for accuracy issues that need attention."""
    alerts = []
    
    for utility_type, threshold in THRESHOLDS.items():
        accuracy = metrics[utility_type].get('accuracy')
        if accuracy is not None and accuracy < threshold:
            alerts.append(
                f"ALERT: {utility_type} accuracy ({accuracy:.1f}%) "
                f"is below threshold ({threshold}%)"
            )
    
    return alerts


def generate_report(validations: List[Dict], metrics: Dict, alerts: List[str]) -> Dict:
    """Generate validation report."""
    report = {
        'generated_at': datetime.now().isoformat(),
        'sample_size': len(validations),
        'summary': {
            'electric_accuracy': metrics['electric'].get('accuracy'),
            'gas_accuracy': metrics['gas'].get('accuracy'),
            'water_accuracy': metrics['water'].get('accuracy'),
            'electric_validated': metrics['electric'].get('validated_count', 0),
            'gas_validated': metrics['gas'].get('validated_count', 0),
            'water_validated': metrics['water'].get('validated_count', 0)
        },
        'alerts': alerts,
        'details': {
            k: {key: val for key, val in v.items() if key != 'mismatches'} 
            for k, v in metrics.items()
        },
        'mismatches': {
            k: v['mismatches'] for k, v in metrics.items()
        },
        'validations': validations
    }
    
    return report


def save_report(report: Dict) -> str:
    """Save validation report to file."""
    os.makedirs(VALIDATION_REPORTS_DIR, exist_ok=True)
    
    # Filename with date
    date_str = datetime.now().strftime('%Y-%m-%d_%H%M%S')
    filename = f"validation_{date_str}.json"
    filepath = os.path.join(VALIDATION_REPORTS_DIR, filename)
    
    with open(filepath, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"Report saved to {filepath}")
    return filepath


def print_summary(metrics: Dict, alerts: List[str]):
    """Print accuracy summary to console."""
    print("\n" + "="*50)
    print("VALIDATION SUMMARY")
    print("="*50)
    
    for utility_type in ['electric', 'gas', 'water']:
        m = metrics[utility_type]
        accuracy = m.get('accuracy')
        total = m['total']
        matches = m['matches']
        validated = m.get('validated_count', 0)
        
        if total > 0:
            print(f"\n{utility_type.upper()}:")
            if accuracy is not None:
                print(f"  Accuracy: {accuracy:.1f}% ({matches}/{validated} validated)")
            else:
                print(f"  Accuracy: N/A (no SERP validation)")
            print(f"  Total lookups: {total}")
            
            if m['mismatches']:
                print(f"  Mismatches ({len(m['mismatches'])}):")
                for mm in m['mismatches'][:5]:  # Show first 5
                    print(f"    - {mm['address']}")
                    print(f"      DB: {mm['original']} | SERP: {mm['serp']}")
                if len(m['mismatches']) > 5:
                    print(f"    ... and {len(m['mismatches']) - 5} more")
    
    if alerts:
        print("\n" + "-"*50)
        print("ALERTS:")
        for alert in alerts:
            print(f"  ⚠️  {alert}")
    
    print("\n" + "="*50)


def main():
    parser = argparse.ArgumentParser(description='Validate utility lookup accuracy')
    parser.add_argument('--sample-size', type=int, default=50, help='Number of lookups to validate')
    parser.add_argument('--state', type=str, help='Filter by state (e.g., TX)')
    parser.add_argument('--days', type=int, default=30, help='Look back N days for lookups')
    parser.add_argument('--use-serp', action='store_true', help='Use SERP for validation (slow)')
    
    args = parser.parse_args()
    
    print(f"Loading lookups from last {args.days} days...")
    lookups = load_recent_lookups(days=args.days, state=args.state)
    print(f"Found {len(lookups)} lookups")
    
    if not lookups:
        print("No lookups to validate. Make sure lookup logging is enabled.")
        return
    
    print(f"Sampling {min(args.sample_size, len(lookups))} lookups...")
    sample = sample_lookups(lookups, args.sample_size)
    
    print(f"Validating {len(sample)} lookups...")
    if args.use_serp:
        print("  (Using SERP - this may take a while)")
    
    validations = []
    for i, lookup in enumerate(sample):
        addr = lookup.get('address', 'Unknown')[:40]
        print(f"  [{i+1}/{len(sample)}] {addr}...")
        validation = validate_lookup(lookup, use_serp=args.use_serp)
        validations.append(validation)
    
    print("Calculating metrics...")
    metrics = calculate_accuracy(validations)
    
    print("Checking alerts...")
    alerts = check_accuracy_alerts(metrics)
    
    print_summary(metrics, alerts)
    
    print("\nGenerating report...")
    report = generate_report(validations, metrics, alerts)
    save_report(report)
    
    # Print alerts to stderr for logging
    for alert in alerts:
        print(f"[ACCURACY ALERT] {alert}", file=sys.stderr)


if __name__ == '__main__':
    main()
