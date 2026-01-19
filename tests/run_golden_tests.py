"""
Golden Test Runner for Utility Lookup

Runs the golden address test suite against the current system and reports results.

Usage:
    python tests/run_golden_tests.py                    # Run all tests
    python tests/run_golden_tests.py --capture         # Capture current outputs as expected
    python tests/run_golden_tests.py --state TX        # Run only Texas tests
    python tests/run_golden_tests.py --verbose         # Show all results, not just failures
"""

import argparse
import json
import os
import sys
import time
from typing import Dict, List, Optional

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utility_lookup import lookup_electric_only, lookup_gas_only
from serp_verification import is_alias

GOLDEN_FILE = os.path.join(os.path.dirname(__file__), 'golden_addresses.json')
RESULTS_FILE = os.path.join(os.path.dirname(__file__), 'test_results.json')


def load_golden_tests(state_filter: str = None) -> List[Dict]:
    """Load golden test cases."""
    with open(GOLDEN_FILE, 'r') as f:
        data = json.load(f)
    
    tests = data.get('tests', [])
    
    if state_filter:
        tests = [t for t in tests if t.get('state', '').upper() == state_filter.upper()]
    
    return tests


def normalize_name(name: str) -> str:
    """Normalize utility name for comparison."""
    if not name:
        return ""
    return name.lower().strip()


def names_match(expected: str, actual: str) -> bool:
    """Check if two utility names match (including aliases)."""
    if not expected:
        return actual is None or actual == ""
    if not actual:
        return False
    
    # Direct match
    exp_norm = normalize_name(expected)
    act_norm = normalize_name(actual)
    
    if exp_norm == act_norm:
        return True
    
    # Partial match
    if exp_norm in act_norm or act_norm in exp_norm:
        return True
    
    # Alias match
    return is_alias(expected, actual)


def run_test(test: Dict) -> Dict:
    """Run a single test case."""
    test_id = test.get('test_id', 'unknown')
    
    result = {
        'test_id': test_id,
        'address': test.get('address'),
        'city': test.get('city'),
        'state': test.get('state'),
        'electric': {'expected': test.get('expected_electric'), 'actual': None, 'passed': False},
        'gas': {'expected': test.get('expected_gas'), 'actual': None, 'passed': False},
        'timing_ms': 0
    }
    
    start = time.time()
    
    try:
        # Electric lookup
        electric_result = lookup_electric_only(
            lat=test.get('lat'),
            lon=test.get('lon'),
            city=test.get('city'),
            county=test.get('county'),
            state=test.get('state'),
            zip_code=test.get('zip_code')
        )
        
        if electric_result:
            result['electric']['actual'] = electric_result.get('NAME')
        
        result['electric']['passed'] = names_match(
            test.get('expected_electric'),
            result['electric']['actual']
        )
        
        # Gas lookup
        gas_result = lookup_gas_only(
            lat=test.get('lat'),
            lon=test.get('lon'),
            city=test.get('city'),
            county=test.get('county'),
            state=test.get('state'),
            zip_code=test.get('zip_code')
        )
        
        if gas_result:
            result['gas']['actual'] = gas_result.get('NAME')
        
        # Handle expected null for gas
        expected_gas = test.get('expected_gas')
        if expected_gas is None:
            result['gas']['passed'] = result['gas']['actual'] is None or result['gas']['actual'] == 'No piped natural gas'
        else:
            result['gas']['passed'] = names_match(expected_gas, result['gas']['actual'])
        
    except Exception as e:
        result['error'] = str(e)
    
    result['timing_ms'] = int((time.time() - start) * 1000)
    
    return result


def run_all_tests(tests: List[Dict], verbose: bool = False) -> Dict:
    """Run all test cases and return summary."""
    results = []
    
    electric_passed = 0
    electric_failed = 0
    gas_passed = 0
    gas_failed = 0
    gas_skipped = 0
    
    total_time = 0
    
    for i, test in enumerate(tests, 1):
        print(f"[{i}/{len(tests)}] {test.get('test_id')}...", end=' ', flush=True)
        
        result = run_test(test)
        results.append(result)
        total_time += result['timing_ms']
        
        # Electric
        if result['electric']['passed']:
            electric_passed += 1
            elec_status = "✓"
        else:
            electric_failed += 1
            elec_status = "✗"
        
        # Gas
        if test.get('expected_gas') is None:
            gas_skipped += 1
            gas_status = "-"
        elif result['gas']['passed']:
            gas_passed += 1
            gas_status = "✓"
        else:
            gas_failed += 1
            gas_status = "✗"
        
        status = f"E:{elec_status} G:{gas_status}"
        
        if verbose or not (result['electric']['passed'] and (result['gas']['passed'] or test.get('expected_gas') is None)):
            print(f"{status} ({result['timing_ms']}ms)")
            if not result['electric']['passed']:
                print(f"    Electric: expected '{result['electric']['expected']}', got '{result['electric']['actual']}'")
            if not result['gas']['passed'] and test.get('expected_gas') is not None:
                print(f"    Gas: expected '{result['gas']['expected']}', got '{result['gas']['actual']}'")
        else:
            print(f"{status}")
    
    summary = {
        'total_tests': len(tests),
        'electric': {
            'passed': electric_passed,
            'failed': electric_failed,
            'accuracy': round(electric_passed / len(tests) * 100, 1) if tests else 0
        },
        'gas': {
            'passed': gas_passed,
            'failed': gas_failed,
            'skipped': gas_skipped,
            'accuracy': round(gas_passed / (gas_passed + gas_failed) * 100, 1) if (gas_passed + gas_failed) > 0 else 0
        },
        'total_time_ms': total_time,
        'avg_time_ms': round(total_time / len(tests)) if tests else 0,
        'results': results
    }
    
    return summary


def capture_outputs(tests: List[Dict]) -> None:
    """Capture current system outputs and update golden file."""
    print("Capturing current system outputs...")
    
    for i, test in enumerate(tests, 1):
        print(f"[{i}/{len(tests)}] {test.get('test_id')}...", end=' ', flush=True)
        
        # Electric
        try:
            electric_result = lookup_electric_only(
                lat=test.get('lat'),
                lon=test.get('lon'),
                city=test.get('city'),
                county=test.get('county'),
                state=test.get('state'),
                zip_code=test.get('zip_code')
            )
            if electric_result:
                test['captured_electric'] = electric_result.get('NAME')
        except Exception as e:
            test['captured_electric_error'] = str(e)
        
        # Gas
        try:
            gas_result = lookup_gas_only(
                lat=test.get('lat'),
                lon=test.get('lon'),
                city=test.get('city'),
                county=test.get('county'),
                state=test.get('state'),
                zip_code=test.get('zip_code')
            )
            if gas_result:
                test['captured_gas'] = gas_result.get('NAME')
        except Exception as e:
            test['captured_gas_error'] = str(e)
        
        print("done")
    
    # Save updated golden file
    with open(GOLDEN_FILE, 'r') as f:
        data = json.load(f)
    
    data['tests'] = tests
    data['_metadata']['last_captured'] = time.strftime('%Y-%m-%d %H:%M:%S')
    
    with open(GOLDEN_FILE, 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"\nCaptured outputs saved to {GOLDEN_FILE}")


def main():
    parser = argparse.ArgumentParser(description='Run golden address tests')
    parser.add_argument('--capture', action='store_true', help='Capture current outputs')
    parser.add_argument('--state', type=str, help='Filter by state')
    parser.add_argument('--verbose', action='store_true', help='Show all results')
    
    args = parser.parse_args()
    
    tests = load_golden_tests(args.state)
    print(f"Loaded {len(tests)} test cases")
    
    if args.capture:
        capture_outputs(tests)
        return
    
    print()
    summary = run_all_tests(tests, args.verbose)
    
    # Print summary
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total tests: {summary['total_tests']}")
    print()
    print(f"Electric: {summary['electric']['passed']}/{summary['total_tests']} ({summary['electric']['accuracy']}%)")
    print(f"Gas: {summary['gas']['passed']}/{summary['gas']['passed'] + summary['gas']['failed']} ({summary['gas']['accuracy']}%) [skipped: {summary['gas']['skipped']}]")
    print()
    print(f"Total time: {summary['total_time_ms']}ms")
    print(f"Avg time per test: {summary['avg_time_ms']}ms")
    
    # Save results
    with open(RESULTS_FILE, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"\nResults saved to {RESULTS_FILE}")
    
    # Exit with error if any failures
    if summary['electric']['failed'] > 0 or summary['gas']['failed'] > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()
