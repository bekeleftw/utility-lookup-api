# Batch Validation Workflow

## Context

We need to systematically verify that our data is accurate over time. This means periodically checking recent lookups against independent sources (SERP) and tracking accuracy metrics.

## Goal

- Sample recent lookups and re-verify with SERP
- Compare database results vs SERP results
- Track accuracy rate over time
- Flag systematic errors for correction

## Implementation

### Step 1: Create Validation Script

Create file: `scripts/validate_accuracy.py`

```python
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

# Import from main app
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utility_lookup import verify_with_serp
from cross_validation import providers_match


LOOKUPS_LOG_FILE = 'data/lookup_log.json'
VALIDATION_REPORTS_DIR = 'data/validation_reports'


def load_recent_lookups(days: int = 30, state: Optional[str] = None) -> List[Dict]:
    """Load recent lookup results from log."""
    if not os.path.exists(LOOKUPS_LOG_FILE):
        print(f"No lookup log found at {LOOKUPS_LOG_FILE}")
        return []
    
    with open(LOOKUPS_LOG_FILE, 'r') as f:
        all_lookups = json.load(f)
    
    # Filter by date
    cutoff = datetime.now() - timedelta(days=days)
    recent = [
        l for l in all_lookups 
        if datetime.fromisoformat(l.get('timestamp', '2000-01-01')) > cutoff
    ]
    
    # Filter by state if specified
    if state:
        recent = [l for l in recent if l.get('state') == state]
    
    return recent


def sample_lookups(lookups: List[Dict], sample_size: int) -> List[Dict]:
    """Randomly sample lookups for validation."""
    if len(lookups) <= sample_size:
        return lookups
    return random.sample(lookups, sample_size)


def validate_lookup(lookup: Dict) -> Dict:
    """
    Re-verify a lookup with SERP and compare to original result.
    
    Returns:
        {
            'address': str,
            'utility_type': str,
            'original': {provider, source},
            'serp': {provider, verified},
            'match': bool,
            'notes': str
        }
    """
    address = lookup.get('address', '')
    city = lookup.get('city', '')
    state = lookup.get('state', '')
    
    results = {}
    
    for utility_type in ['electric', 'gas', 'water']:
        original_provider = lookup.get(f'{utility_type}_provider')
        
        if not original_provider:
            continue
        
        # Query SERP for this utility
        serp_query = f"{utility_type} utility provider for {address}"
        serp_result = verify_with_serp(serp_query)
        
        serp_provider = serp_result.get('provider') if serp_result else None
        
        # Compare
        if original_provider and serp_provider:
            match = providers_match(original_provider, serp_provider)
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
        
        # Rate limit SERP queries
        time.sleep(1)
    
    return {
        'address': address,
        'city': city,
        'state': state,
        'zip_code': lookup.get('zip_code'),
        'timestamp': datetime.now().isoformat(),
        'results': results
    }


def calculate_accuracy(validations: List[Dict]) -> Dict:
    """Calculate accuracy metrics from validation results."""
    metrics = {
        'electric': {'total': 0, 'matches': 0, 'mismatches': []},
        'gas': {'total': 0, 'matches': 0, 'mismatches': []},
        'water': {'total': 0, 'matches': 0, 'mismatches': []}
    }
    
    for v in validations:
        for utility_type, result in v.get('results', {}).items():
            if utility_type not in metrics:
                continue
            
            metrics[utility_type]['total'] += 1
            
            if result.get('match'):
                metrics[utility_type]['matches'] += 1
            else:
                metrics[utility_type]['mismatches'].append({
                    'address': v['address'],
                    'zip_code': v.get('zip_code'),
                    'original': result.get('original'),
                    'serp': result.get('serp')
                })
    
    # Calculate percentages
    for utility_type in metrics:
        total = metrics[utility_type]['total']
        matches = metrics[utility_type]['matches']
        metrics[utility_type]['accuracy'] = (matches / total * 100) if total > 0 else None
    
    return metrics


def generate_report(validations: List[Dict], metrics: Dict) -> Dict:
    """Generate validation report."""
    report = {
        'generated_at': datetime.now().isoformat(),
        'sample_size': len(validations),
        'summary': {
            'electric_accuracy': metrics['electric'].get('accuracy'),
            'gas_accuracy': metrics['gas'].get('accuracy'),
            'water_accuracy': metrics['water'].get('accuracy')
        },
        'details': metrics,
        'validations': validations
    }
    
    return report


def save_report(report: Dict):
    """Save validation report to file."""
    os.makedirs(VALIDATION_REPORTS_DIR, exist_ok=True)
    
    # Filename with date
    date_str = datetime.now().strftime('%Y-%m-%d')
    filename = f"validation_{date_str}.json"
    filepath = os.path.join(VALIDATION_REPORTS_DIR, filename)
    
    with open(filepath, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"Report saved to {filepath}")
    return filepath


def print_summary(metrics: Dict):
    """Print accuracy summary to console."""
    print("\n" + "="*50)
    print("VALIDATION SUMMARY")
    print("="*50)
    
    for utility_type in ['electric', 'gas', 'water']:
        m = metrics[utility_type]
        accuracy = m.get('accuracy')
        total = m['total']
        matches = m['matches']
        
        if accuracy is not None:
            print(f"\n{utility_type.upper()}:")
            print(f"  Accuracy: {accuracy:.1f}% ({matches}/{total})")
            
            if m['mismatches']:
                print(f"  Mismatches ({len(m['mismatches'])}):")
                for mm in m['mismatches'][:5]:  # Show first 5
                    print(f"    - {mm['address']}")
                    print(f"      DB: {mm['original']} | SERP: {mm['serp']}")
                if len(m['mismatches']) > 5:
                    print(f"    ... and {len(m['mismatches']) - 5} more")
    
    print("\n" + "="*50)


def main():
    parser = argparse.ArgumentParser(description='Validate utility lookup accuracy')
    parser.add_argument('--sample-size', type=int, default=50, help='Number of lookups to validate')
    parser.add_argument('--state', type=str, help='Filter by state (e.g., TX)')
    parser.add_argument('--days', type=int, default=30, help='Look back N days for lookups')
    
    args = parser.parse_args()
    
    print(f"Loading lookups from last {args.days} days...")
    lookups = load_recent_lookups(days=args.days, state=args.state)
    print(f"Found {len(lookups)} lookups")
    
    if not lookups:
        print("No lookups to validate. Make sure lookup logging is enabled.")
        return
    
    print(f"Sampling {args.sample_size} lookups...")
    sample = sample_lookups(lookups, args.sample_size)
    
    print(f"Validating {len(sample)} lookups (this may take a while)...")
    validations = []
    for i, lookup in enumerate(sample):
        print(f"  [{i+1}/{len(sample)}] {lookup.get('address', 'Unknown')[:50]}...")
        validation = validate_lookup(lookup)
        validations.append(validation)
    
    print("Calculating metrics...")
    metrics = calculate_accuracy(validations)
    
    print_summary(metrics)
    
    print("\nGenerating report...")
    report = generate_report(validations, metrics)
    save_report(report)


if __name__ == '__main__':
    main()
```

### Step 2: Add Lookup Logging

To validate, we need to log lookups. Add to `utility_lookup.py`:

```python
import json
from datetime import datetime

LOOKUPS_LOG_FILE = 'data/lookup_log.json'
MAX_LOG_ENTRIES = 10000  # Keep last 10k lookups

def log_lookup(
    address: str,
    city: str,
    county: str,
    state: str,
    zip_code: str,
    electric_provider: str = None,
    gas_provider: str = None,
    water_provider: str = None,
    internet_count: int = None
):
    """Log a lookup for later validation."""
    try:
        with open(LOOKUPS_LOG_FILE, 'r') as f:
            lookups = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        lookups = []
    
    entry = {
        'timestamp': datetime.now().isoformat(),
        'address': address,
        'city': city,
        'county': county,
        'state': state,
        'zip_code': zip_code,
        'electric_provider': electric_provider,
        'gas_provider': gas_provider,
        'water_provider': water_provider,
        'internet_count': internet_count
    }
    
    lookups.append(entry)
    
    # Trim to max entries
    if len(lookups) > MAX_LOG_ENTRIES:
        lookups = lookups[-MAX_LOG_ENTRIES:]
    
    with open(LOOKUPS_LOG_FILE, 'w') as f:
        json.dump(lookups, f)


# Call in main lookup function
def lookup_all_utilities(address, verify=True):
    # ... existing lookup logic ...
    
    # Log the lookup
    log_lookup(
        address=address,
        city=location['city'],
        county=location['county'],
        state=location['state'],
        zip_code=location['zip_code'],
        electric_provider=electric_result[0]['name'] if electric_result else None,
        gas_provider=gas_result[0]['name'] if gas_result else None,
        water_provider=water_result[0]['name'] if water_result else None,
        internet_count=internet_result.get('provider_count') if internet_result else None
    )
    
    return result
```

### Step 3: Add API Endpoint for Reports

In `api.py`:

```python
import os
import glob

VALIDATION_REPORTS_DIR = 'data/validation_reports'

@app.route('/api/validation-reports', methods=['GET'])
def list_validation_reports():
    """List available validation reports."""
    if not os.path.exists(VALIDATION_REPORTS_DIR):
        return jsonify({'reports': []})
    
    reports = []
    for filepath in glob.glob(os.path.join(VALIDATION_REPORTS_DIR, '*.json')):
        filename = os.path.basename(filepath)
        
        # Load summary only
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        reports.append({
            'filename': filename,
            'generated_at': data.get('generated_at'),
            'sample_size': data.get('sample_size'),
            'summary': data.get('summary')
        })
    
    # Sort by date descending
    reports.sort(key=lambda x: x['generated_at'], reverse=True)
    
    return jsonify({'reports': reports})


@app.route('/api/validation-reports/<filename>', methods=['GET'])
def get_validation_report(filename):
    """Get a specific validation report."""
    filepath = os.path.join(VALIDATION_REPORTS_DIR, filename)
    
    if not os.path.exists(filepath):
        return jsonify({'error': 'Report not found'}), 404
    
    with open(filepath, 'r') as f:
        report = json.load(f)
    
    return jsonify(report)


@app.route('/api/accuracy-trend', methods=['GET'])
def get_accuracy_trend():
    """Get accuracy trend over time."""
    if not os.path.exists(VALIDATION_REPORTS_DIR):
        return jsonify({'trend': []})
    
    trend = []
    for filepath in sorted(glob.glob(os.path.join(VALIDATION_REPORTS_DIR, '*.json'))):
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        trend.append({
            'date': data.get('generated_at', '')[:10],
            'electric': data.get('summary', {}).get('electric_accuracy'),
            'gas': data.get('summary', {}).get('gas_accuracy'),
            'water': data.get('summary', {}).get('water_accuracy')
        })
    
    return jsonify({'trend': trend})
```

### Step 4: Schedule Regular Validation

Add to Railway or cron:

```bash
# Run weekly validation (100 samples)
0 0 * * 0 cd /app && python scripts/validate_accuracy.py --sample-size 100

# Run monthly deep validation (500 samples)
0 0 1 * * cd /app && python scripts/validate_accuracy.py --sample-size 500
```

Or use Railway scheduled jobs.

### Step 5: Create Alert for Low Accuracy

```python
# In validate_accuracy.py, add alert function

def check_accuracy_alerts(metrics: Dict) -> List[str]:
    """Check for accuracy issues that need attention."""
    alerts = []
    
    THRESHOLDS = {
        'electric': 90,  # Alert if below 90%
        'gas': 85,
        'water': 80
    }
    
    for utility_type, threshold in THRESHOLDS.items():
        accuracy = metrics[utility_type].get('accuracy')
        if accuracy is not None and accuracy < threshold:
            alerts.append(
                f"ALERT: {utility_type} accuracy ({accuracy:.1f}%) "
                f"is below threshold ({threshold}%)"
            )
    
    return alerts


def send_alerts(alerts: List[str]):
    """Send alerts via email or Slack."""
    if not alerts:
        return
    
    # Option 1: Print to log (Railway will capture)
    for alert in alerts:
        print(f"[ACCURACY ALERT] {alert}")
    
    # Option 2: Send to Slack webhook
    # import requests
    # SLACK_WEBHOOK = os.environ.get('SLACK_WEBHOOK')
    # if SLACK_WEBHOOK:
    #     requests.post(SLACK_WEBHOOK, json={'text': '\n'.join(alerts)})
```

## Testing

### Test Validation Script
```bash
# First, ensure some lookups are logged
curl "https://web-production-9acc6.up.railway.app/api/lookup?address=123+Main+St+Dallas+TX+75201"
curl "https://web-production-9acc6.up.railway.app/api/lookup?address=456+Oak+Ave+Austin+TX+78704"

# Run validation
python scripts/validate_accuracy.py --sample-size 10 --state TX
```

### Test API Endpoints
```bash
# List reports
curl https://web-production-9acc6.up.railway.app/api/validation-reports

# Get specific report
curl https://web-production-9acc6.up.railway.app/api/validation-reports/validation_2026-01-11.json

# Get trend
curl https://web-production-9acc6.up.railway.app/api/accuracy-trend
```

## Metrics to Track

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| Electric accuracy | >95% | <90% |
| Gas accuracy | >90% | <85% |
| Water accuracy | >85% | <80% |
| Mismatches per week | <10 | >25 |

## Commit Message

```
Add batch validation for accuracy monitoring

- validate_accuracy.py script for sampling and validation
- Lookup logging for validation dataset
- API endpoints for viewing reports and trends
- Accuracy alerts when below thresholds
- Weekly/monthly scheduled validation
```
