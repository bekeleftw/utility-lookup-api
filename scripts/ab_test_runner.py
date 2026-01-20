#!/usr/bin/env python3
"""
Phase 2: A/B Testing Infrastructure

Compares v1 (utility_lookup.py) vs v2 (utility_lookup_v2.py) results.
Runs both versions in parallel and logs differences.

Usage:
    python scripts/ab_test_runner.py                    # Run with golden addresses
    python scripts/ab_test_runner.py --address "..."    # Test single address
    python scripts/ab_test_runner.py --report           # Generate comparison report
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class ABTestRunner:
    """
    Runs A/B tests comparing v1 and v2 utility lookup implementations.
    """
    
    def __init__(self, log_dir: str = None):
        self.log_dir = Path(log_dir) if log_dir else Path(__file__).parent.parent / 'data' / 'ab_tests'
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self.results_file = self.log_dir / f"ab_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        self.results = []
        
        # Import both versions
        self._v1_lookup = None
        self._v2_lookup = None
    
    def _get_v1_lookup(self):
        """Lazy load v1 lookup function."""
        if self._v1_lookup is None:
            from utility_lookup import lookup_utilities_by_address
            self._v1_lookup = lookup_utilities_by_address
        return self._v1_lookup
    
    def _get_v2_lookup(self):
        """Lazy load v2 lookup function."""
        if self._v2_lookup is None:
            from utility_lookup_v2 import lookup_utilities_by_address
            self._v2_lookup = lookup_utilities_by_address
        return self._v2_lookup
    
    def compare_single(self, address: str, expected: Dict = None) -> Dict:
        """
        Compare v1 and v2 results for a single address.
        
        Args:
            address: Full street address
            expected: Optional dict with expected results for validation
        
        Returns:
            Comparison result dict
        """
        result = {
            'address': address,
            'timestamp': datetime.now().isoformat(),
            'v1': None,
            'v2': None,
            'comparison': {},
            'expected': expected,
        }
        
        # Run v1
        v1_start = time.time()
        try:
            v1_result = self._get_v1_lookup()(address)
            result['v1'] = {
                'result': self._extract_key_fields(v1_result),
                'time_ms': int((time.time() - v1_start) * 1000),
                'error': None
            }
        except Exception as e:
            result['v1'] = {
                'result': None,
                'time_ms': int((time.time() - v1_start) * 1000),
                'error': str(e)
            }
        
        # Run v2
        v2_start = time.time()
        try:
            v2_result = self._get_v2_lookup()(address)
            result['v2'] = {
                'result': self._extract_key_fields(v2_result),
                'time_ms': int((time.time() - v2_start) * 1000),
                'error': None
            }
        except Exception as e:
            result['v2'] = {
                'result': None,
                'time_ms': int((time.time() - v2_start) * 1000),
                'error': str(e)
            }
        
        # Compare results
        result['comparison'] = self._compare_results(
            result['v1']['result'],
            result['v2']['result'],
            expected
        )
        
        self.results.append(result)
        return result
    
    def _extract_key_fields(self, result: Dict) -> Dict:
        """Extract key fields from lookup result for comparison."""
        if not result:
            return None
        
        extracted = {}
        for utility_type in ['electric', 'gas', 'water']:
            util = result.get(utility_type)
            if util and isinstance(util, dict):
                extracted[utility_type] = {
                    'name': util.get('NAME'),
                    'confidence': util.get('_confidence'),
                    'confidence_score': util.get('_confidence_score'),
                    'source': util.get('_source') or util.get('_verification_source'),
                }
            else:
                extracted[utility_type] = None
        
        return extracted
    
    def _compare_results(self, v1: Dict, v2: Dict, expected: Dict = None) -> Dict:
        """Compare v1 and v2 results."""
        comparison = {
            'match': True,
            'differences': [],
            'v1_correct': None,
            'v2_correct': None,
        }
        
        if v1 is None and v2 is None:
            return comparison
        
        if v1 is None or v2 is None:
            comparison['match'] = False
            comparison['differences'].append({
                'type': 'one_failed',
                'v1_failed': v1 is None,
                'v2_failed': v2 is None,
            })
            return comparison
        
        # Compare each utility type
        for utility_type in ['electric', 'gas', 'water']:
            v1_util = v1.get(utility_type)
            v2_util = v2.get(utility_type)
            
            v1_name = v1_util.get('name') if v1_util else None
            v2_name = v2_util.get('name') if v2_util else None
            
            # Normalize names for comparison
            v1_norm = self._normalize_name(v1_name)
            v2_norm = self._normalize_name(v2_name)
            
            if v1_norm != v2_norm:
                comparison['match'] = False
                comparison['differences'].append({
                    'utility_type': utility_type,
                    'v1_name': v1_name,
                    'v2_name': v2_name,
                    'v1_source': v1_util.get('source') if v1_util else None,
                    'v2_source': v2_util.get('source') if v2_util else None,
                })
        
        # Check against expected if provided
        if expected:
            for utility_type in ['electric', 'gas']:
                expected_name = expected.get(f'expected_{utility_type}')
                if expected_name:
                    expected_norm = self._normalize_name(expected_name)
                    
                    v1_util = v1.get(utility_type)
                    v2_util = v2.get(utility_type)
                    
                    v1_name = v1_util.get('name') if v1_util else None
                    v2_name = v2_util.get('name') if v2_util else None
                    
                    v1_matches = self._names_match(v1_name, expected_name)
                    v2_matches = self._names_match(v2_name, expected_name)
                    
                    if comparison['v1_correct'] is None:
                        comparison['v1_correct'] = {}
                    if comparison['v2_correct'] is None:
                        comparison['v2_correct'] = {}
                    
                    comparison['v1_correct'][utility_type] = v1_matches
                    comparison['v2_correct'][utility_type] = v2_matches
        
        return comparison
    
    def _normalize_name(self, name: str) -> str:
        """Normalize utility name for comparison."""
        if not name:
            return ''
        return name.upper().strip()
    
    def _names_match(self, actual: str, expected: str) -> bool:
        """Check if utility names match (fuzzy)."""
        if not actual or not expected:
            return False
        
        actual_norm = self._normalize_name(actual)
        expected_norm = self._normalize_name(expected)
        
        # Exact match
        if actual_norm == expected_norm:
            return True
        
        # Partial match (one contains the other)
        if expected_norm in actual_norm or actual_norm in expected_norm:
            return True
        
        # Check key words
        expected_words = set(expected_norm.split())
        actual_words = set(actual_norm.split())
        
        # If significant words overlap
        significant = expected_words & actual_words - {'ENERGY', 'ELECTRIC', 'GAS', 'UTILITY', 'CO', 'COMPANY', 'INC', 'LLC'}
        if len(significant) >= 1:
            return True
        
        return False
    
    def run_golden_tests(self, limit: int = None) -> Dict:
        """
        Run A/B tests on golden test addresses.
        
        Args:
            limit: Maximum number of tests to run (None for all)
        
        Returns:
            Summary of test results
        """
        # Load golden addresses
        golden_path = Path(__file__).parent.parent / 'tests' / 'golden_addresses.json'
        
        if not golden_path.exists():
            print(f"Golden addresses file not found: {golden_path}")
            return {'error': 'Golden addresses file not found'}
        
        with open(golden_path, 'r') as f:
            golden = json.load(f)
        
        tests = golden.get('tests', [])
        if limit:
            tests = tests[:limit]
        
        print(f"Running A/B tests on {len(tests)} addresses...")
        print("=" * 60)
        
        for i, test in enumerate(tests):
            address = test.get('address')
            print(f"\n[{i+1}/{len(tests)}] {address}")
            
            expected = {
                'expected_electric': test.get('expected_electric'),
                'expected_gas': test.get('expected_gas'),
            }
            
            result = self.compare_single(address, expected)
            
            # Print quick summary
            if result['comparison']['match']:
                print("  ✓ v1 and v2 match")
            else:
                print("  ✗ DIFFERENCE:")
                for diff in result['comparison']['differences']:
                    if 'utility_type' in diff:
                        print(f"    {diff['utility_type']}: v1={diff['v1_name']} vs v2={diff['v2_name']}")
            
            # Check correctness
            v1_correct = result['comparison'].get('v1_correct', {})
            v2_correct = result['comparison'].get('v2_correct', {})
            
            if v1_correct or v2_correct:
                for ut in ['electric', 'gas']:
                    v1_ok = v1_correct.get(ut)
                    v2_ok = v2_correct.get(ut)
                    if v1_ok is not None or v2_ok is not None:
                        v1_mark = '✓' if v1_ok else '✗'
                        v2_mark = '✓' if v2_ok else '✗'
                        print(f"    {ut}: v1={v1_mark} v2={v2_mark} (expected: {expected.get(f'expected_{ut}')})")
        
        # Save results
        self._save_results()
        
        # Generate summary
        return self._generate_summary()
    
    def _save_results(self):
        """Save results to JSON file."""
        with open(self.results_file, 'w') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'total_tests': len(self.results),
                'results': self.results,
            }, f, indent=2)
        
        print(f"\nResults saved to: {self.results_file}")
    
    def _generate_summary(self) -> Dict:
        """Generate summary statistics from results."""
        total = len(self.results)
        matches = sum(1 for r in self.results if r['comparison']['match'])
        
        v1_correct_electric = 0
        v1_correct_gas = 0
        v2_correct_electric = 0
        v2_correct_gas = 0
        
        v1_faster = 0
        v2_faster = 0
        
        for r in self.results:
            # Correctness
            v1_correct = r['comparison'].get('v1_correct', {})
            v2_correct = r['comparison'].get('v2_correct', {})
            
            if v1_correct.get('electric'):
                v1_correct_electric += 1
            if v1_correct.get('gas'):
                v1_correct_gas += 1
            if v2_correct.get('electric'):
                v2_correct_electric += 1
            if v2_correct.get('gas'):
                v2_correct_gas += 1
            
            # Speed
            v1_time = r['v1'].get('time_ms', 0) if r['v1'] else 0
            v2_time = r['v2'].get('time_ms', 0) if r['v2'] else 0
            
            if v1_time and v2_time:
                if v1_time < v2_time:
                    v1_faster += 1
                else:
                    v2_faster += 1
        
        summary = {
            'total_tests': total,
            'matches': matches,
            'match_rate': f"{matches/total*100:.1f}%" if total > 0 else "N/A",
            'differences': total - matches,
            'correctness': {
                'v1_electric': f"{v1_correct_electric}/{total}",
                'v1_gas': f"{v1_correct_gas}/{total}",
                'v2_electric': f"{v2_correct_electric}/{total}",
                'v2_gas': f"{v2_correct_gas}/{total}",
            },
            'speed': {
                'v1_faster': v1_faster,
                'v2_faster': v2_faster,
            },
            'results_file': str(self.results_file),
        }
        
        print("\n" + "=" * 60)
        print("A/B TEST SUMMARY")
        print("=" * 60)
        print(f"Total tests: {total}")
        print(f"v1/v2 match: {matches} ({summary['match_rate']})")
        print(f"Differences: {total - matches}")
        print(f"\nCorrectness (vs expected):")
        print(f"  v1 electric: {summary['correctness']['v1_electric']}")
        print(f"  v1 gas:      {summary['correctness']['v1_gas']}")
        print(f"  v2 electric: {summary['correctness']['v2_electric']}")
        print(f"  v2 gas:      {summary['correctness']['v2_gas']}")
        print(f"\nSpeed:")
        print(f"  v1 faster: {v1_faster}")
        print(f"  v2 faster: {v2_faster}")
        
        return summary


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='A/B Test Runner for Utility Lookup')
    parser.add_argument('--address', help='Test single address')
    parser.add_argument('--limit', type=int, help='Limit number of golden tests')
    parser.add_argument('--report', action='store_true', help='Generate report from latest results')
    args = parser.parse_args()
    
    runner = ABTestRunner()
    
    if args.address:
        print(f"Testing: {args.address}")
        result = runner.compare_single(args.address)
        print(json.dumps(result, indent=2, default=str))
    
    elif args.report:
        # Find latest results file
        results_dir = Path(__file__).parent.parent / 'data' / 'ab_tests'
        results_files = sorted(results_dir.glob('ab_results_*.json'), reverse=True)
        
        if results_files:
            with open(results_files[0], 'r') as f:
                data = json.load(f)
            
            print(f"Report from: {results_files[0]}")
            print(f"Total tests: {data['total_tests']}")
            # Generate detailed report...
        else:
            print("No results files found. Run tests first.")
    
    else:
        # Run golden tests
        runner.run_golden_tests(limit=args.limit)


if __name__ == "__main__":
    main()
