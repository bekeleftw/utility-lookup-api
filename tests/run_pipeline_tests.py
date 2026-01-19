"""
Pipeline Test Runner

Runs the golden address test suite against the NEW pipeline and compares to baseline.

Usage:
    python tests/run_pipeline_tests.py                    # Run all tests
    python tests/run_pipeline_tests.py --state TX         # Run only Texas tests
    python tests/run_pipeline_tests.py --compare          # Compare to baseline results
"""

import argparse
import json
import os
import sys
import time
from typing import Dict, List

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.interfaces import UtilityType, LookupContext
from pipeline.pipeline import LookupPipeline
from pipeline.sources.electric import (
    StateGISElectricSource,
    MunicipalElectricSource,
    CoopSource,
    EIASource,
    HIFLDElectricSource,
    CountyDefaultElectricSource,
)
from pipeline.sources.gas import (
    MunicipalGasSource,
    ZIPMappingGasSource,
    HIFLDGasSource,
    CountyDefaultGasSource,
)
from serp_verification import is_alias

GOLDEN_FILE = os.path.join(os.path.dirname(__file__), 'golden_addresses.json')
PIPELINE_RESULTS_FILE = os.path.join(os.path.dirname(__file__), 'pipeline_results.json')
BASELINE_RESULTS_FILE = os.path.join(os.path.dirname(__file__), 'test_results.json')


def create_pipeline() -> LookupPipeline:
    """Create a pipeline with all sources."""
    pipeline = LookupPipeline()
    
    # Electric sources
    pipeline.add_source(StateGISElectricSource())
    pipeline.add_source(MunicipalElectricSource())
    pipeline.add_source(CoopSource())
    pipeline.add_source(EIASource())
    pipeline.add_source(HIFLDElectricSource())
    pipeline.add_source(CountyDefaultElectricSource())
    
    # Gas sources
    pipeline.add_source(MunicipalGasSource())
    pipeline.add_source(ZIPMappingGasSource())
    pipeline.add_source(HIFLDGasSource())
    pipeline.add_source(CountyDefaultGasSource())
    
    return pipeline


def load_golden_tests(state_filter: str = None) -> List[Dict]:
    """Load golden test cases."""
    with open(GOLDEN_FILE, 'r') as f:
        data = json.load(f)
    
    tests = data.get('tests', [])
    
    if state_filter:
        tests = [t for t in tests if t.get('state', '').upper() == state_filter.upper()]
    
    return tests


def names_match(expected: str, actual: str) -> bool:
    """Check if two utility names match."""
    if not expected:
        return actual is None or actual == ""
    if not actual:
        return False
    
    exp_norm = expected.lower().strip()
    act_norm = actual.lower().strip()
    
    if exp_norm == act_norm:
        return True
    if exp_norm in act_norm or act_norm in exp_norm:
        return True
    
    return is_alias(expected, actual)


def run_test(pipeline: LookupPipeline, test: Dict) -> Dict:
    """Run a single test case with the pipeline."""
    test_id = test.get('test_id', 'unknown')
    
    result = {
        'test_id': test_id,
        'city': test.get('city'),
        'state': test.get('state'),
        'electric': {'expected': test.get('expected_electric'), 'actual': None, 'passed': False},
        'gas': {'expected': test.get('expected_gas'), 'actual': None, 'passed': False},
        'electric_timing_ms': 0,
        'gas_timing_ms': 0,
        'electric_sources': [],
        'gas_sources': [],
    }
    
    # Electric lookup
    try:
        context = LookupContext(
            lat=test.get('lat'),
            lon=test.get('lon'),
            address=test.get('address', ''),
            city=test.get('city'),
            county=test.get('county'),
            state=test.get('state'),
            zip_code=test.get('zip_code'),
            utility_type=UtilityType.ELECTRIC
        )
        
        electric_result = pipeline.lookup(context)
        result['electric']['actual'] = electric_result.utility_name
        result['electric_timing_ms'] = electric_result.timing_ms
        result['electric_sources'] = electric_result.agreeing_sources
        result['electric']['passed'] = names_match(
            test.get('expected_electric'),
            electric_result.utility_name
        )
    except Exception as e:
        result['electric']['error'] = str(e)
    
    # Gas lookup
    try:
        context = LookupContext(
            lat=test.get('lat'),
            lon=test.get('lon'),
            address=test.get('address', ''),
            city=test.get('city'),
            county=test.get('county'),
            state=test.get('state'),
            zip_code=test.get('zip_code'),
            utility_type=UtilityType.GAS
        )
        
        gas_result = pipeline.lookup(context)
        result['gas']['actual'] = gas_result.utility_name
        result['gas_timing_ms'] = gas_result.timing_ms
        result['gas_sources'] = gas_result.agreeing_sources
        
        expected_gas = test.get('expected_gas')
        if expected_gas is None:
            result['gas']['passed'] = gas_result.utility_name is None
        else:
            result['gas']['passed'] = names_match(expected_gas, gas_result.utility_name)
    except Exception as e:
        result['gas']['error'] = str(e)
    
    return result


def run_all_tests(pipeline: LookupPipeline, tests: List[Dict], verbose: bool = False) -> Dict:
    """Run all test cases."""
    results = []
    
    electric_passed = 0
    electric_failed = 0
    gas_passed = 0
    gas_failed = 0
    gas_skipped = 0
    
    total_electric_time = 0
    total_gas_time = 0
    
    for i, test in enumerate(tests, 1):
        print(f"[{i}/{len(tests)}] {test.get('test_id')}...", end=' ', flush=True)
        
        result = run_test(pipeline, test)
        results.append(result)
        
        total_electric_time += result['electric_timing_ms']
        total_gas_time += result['gas_timing_ms']
        
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
        
        timing = result['electric_timing_ms'] + result['gas_timing_ms']
        status = f"E:{elec_status} G:{gas_status} ({timing}ms)"
        
        if verbose or not (result['electric']['passed'] and (result['gas']['passed'] or test.get('expected_gas') is None)):
            print(status)
            if not result['electric']['passed']:
                print(f"    Electric: expected '{result['electric']['expected']}', got '{result['electric']['actual']}'")
            if not result['gas']['passed'] and test.get('expected_gas') is not None:
                print(f"    Gas: expected '{result['gas']['expected']}', got '{result['gas']['actual']}'")
        else:
            print(status)
    
    summary = {
        'total_tests': len(tests),
        'electric': {
            'passed': electric_passed,
            'failed': electric_failed,
            'accuracy': round(electric_passed / len(tests) * 100, 1) if tests else 0,
            'total_time_ms': total_electric_time,
            'avg_time_ms': round(total_electric_time / len(tests)) if tests else 0,
        },
        'gas': {
            'passed': gas_passed,
            'failed': gas_failed,
            'skipped': gas_skipped,
            'accuracy': round(gas_passed / (gas_passed + gas_failed) * 100, 1) if (gas_passed + gas_failed) > 0 else 0,
            'total_time_ms': total_gas_time,
            'avg_time_ms': round(total_gas_time / len(tests)) if tests else 0,
        },
        'results': results
    }
    
    return summary


def compare_to_baseline(pipeline_summary: Dict) -> None:
    """Compare pipeline results to baseline."""
    if not os.path.exists(BASELINE_RESULTS_FILE):
        print("\nNo baseline results found for comparison.")
        return
    
    with open(BASELINE_RESULTS_FILE, 'r') as f:
        baseline = json.load(f)
    
    print("\n" + "=" * 60)
    print("COMPARISON TO BASELINE")
    print("=" * 60)
    
    # Electric
    base_elec = baseline.get('electric', {})
    pipe_elec = pipeline_summary.get('electric', {})
    
    elec_acc_diff = pipe_elec.get('accuracy', 0) - base_elec.get('accuracy', 0)
    elec_time_diff = pipe_elec.get('avg_time_ms', 0) - base_elec.get('avg_time_ms', 0)
    
    print(f"\nElectric:")
    print(f"  Accuracy: {base_elec.get('accuracy', 0)}% → {pipe_elec.get('accuracy', 0)}% ({elec_acc_diff:+.1f}%)")
    print(f"  Avg Time: {base_elec.get('avg_time_ms', 0)}ms → {pipe_elec.get('avg_time_ms', 0)}ms ({elec_time_diff:+d}ms)")
    
    # Gas
    base_gas = baseline.get('gas', {})
    pipe_gas = pipeline_summary.get('gas', {})
    
    gas_acc_diff = pipe_gas.get('accuracy', 0) - base_gas.get('accuracy', 0)
    gas_time_diff = pipe_gas.get('avg_time_ms', 0) - base_gas.get('avg_time_ms', 0)
    
    print(f"\nGas:")
    print(f"  Accuracy: {base_gas.get('accuracy', 0)}% → {pipe_gas.get('accuracy', 0)}% ({gas_acc_diff:+.1f}%)")
    print(f"  Avg Time: {base_gas.get('avg_time_ms', 0)}ms → {pipe_gas.get('avg_time_ms', 0)}ms ({gas_time_diff:+d}ms)")


def main():
    parser = argparse.ArgumentParser(description='Run pipeline tests')
    parser.add_argument('--state', type=str, help='Filter by state')
    parser.add_argument('--verbose', action='store_true', help='Show all results')
    parser.add_argument('--compare', action='store_true', help='Compare to baseline')
    
    args = parser.parse_args()
    
    tests = load_golden_tests(args.state)
    print(f"Loaded {len(tests)} test cases")
    
    pipeline = create_pipeline()
    print(f"Created pipeline with {len(pipeline.sources)} sources")
    print()
    
    summary = run_all_tests(pipeline, tests, args.verbose)
    
    # Print summary
    print()
    print("=" * 60)
    print("PIPELINE RESULTS")
    print("=" * 60)
    print(f"Total tests: {summary['total_tests']}")
    print()
    print(f"Electric: {summary['electric']['passed']}/{summary['total_tests']} ({summary['electric']['accuracy']}%)")
    print(f"  Avg time: {summary['electric']['avg_time_ms']}ms")
    print(f"Gas: {summary['gas']['passed']}/{summary['gas']['passed'] + summary['gas']['failed']} ({summary['gas']['accuracy']}%)")
    print(f"  Avg time: {summary['gas']['avg_time_ms']}ms")
    
    # Save results
    with open(PIPELINE_RESULTS_FILE, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"\nResults saved to {PIPELINE_RESULTS_FILE}")
    
    # Compare to baseline
    if args.compare:
        compare_to_baseline(summary)
    
    pipeline.shutdown()


if __name__ == '__main__':
    main()
