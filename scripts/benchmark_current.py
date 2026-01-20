#!/usr/bin/env python3
"""
Phase 0: Baseline Metrics Capture

Captures current system performance before refactoring:
- Lookup latency (p50, p95, p99) for each utility type
- Lines of code per file
- Data file inventory
- Error rate estimation

Run: python scripts/benchmark_current.py > baseline_metrics.txt
"""

import json
import os
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import statistics

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Test addresses covering different scenarios
BENCHMARK_ADDRESSES = [
    # Texas - various providers
    ("1100 Congress Ave, Austin, TX 78701", "Austin Energy", "Texas Gas Service"),
    ("1000 Main St, Houston, TX 77002", "CenterPoint Energy", "CenterPoint Energy"),
    ("1500 Marilla St, Dallas, TX 75201", "Oncor", "Atmos Energy"),
    ("100 Military Plaza, San Antonio, TX 78205", "CPS Energy", "CPS Energy"),
    ("1401 Thrasher Dr, Little Elm, TX 75068", "CoServ Electric", "CoServ Gas"),
    
    # California
    ("200 N Spring St, Los Angeles, CA 90012", "LADWP", "Southern California Gas"),
    ("1 Dr Carlton B Goodlett Pl, San Francisco, CA 94102", "Pacific Gas & Electric", "Pacific Gas & Electric"),
    
    # Florida
    ("100 NE 1st Ave, Miami, FL 33132", "Florida Power & Light", None),
    ("315 E Kennedy Blvd, Tampa, FL 33602", "Tampa Electric", "Peoples Gas"),
    
    # New York
    ("City Hall, New York, NY 10007", "Con Edison", "Con Edison"),
    
    # Illinois
    ("121 N LaSalle St, Chicago, IL 60602", "Commonwealth Edison", "Peoples Gas"),
    
    # Georgia
    ("55 Trinity Ave SW, Atlanta, GA 30303", "Georgia Power", "Atlanta Gas Light"),
    
    # Pennsylvania
    ("1401 JFK Blvd, Philadelphia, PA 19102", "PECO", "Philadelphia Gas Works"),
    
    # Ohio
    ("90 W Broad St, Columbus, OH 43215", "AEP Ohio", "Columbia Gas"),
    
    # Arizona
    ("200 W Washington St, Phoenix, AZ 85003", "Arizona Public Service", "Southwest Gas"),
]


def count_lines_of_code(filepath: str) -> int:
    """Count non-empty, non-comment lines in a Python file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        count = 0
        in_multiline_string = False
        
        for line in lines:
            stripped = line.strip()
            
            # Skip empty lines
            if not stripped:
                continue
            
            # Skip single-line comments
            if stripped.startswith('#'):
                continue
            
            # Track multiline strings (docstrings)
            if '"""' in stripped or "'''" in stripped:
                quotes = '"""' if '"""' in stripped else "'''"
                occurrences = stripped.count(quotes)
                if occurrences == 1:
                    in_multiline_string = not in_multiline_string
                    continue
                elif occurrences >= 2:
                    continue  # Single line docstring
            
            if in_multiline_string:
                continue
            
            count += 1
        
        return count
    except Exception as e:
        return -1


def get_file_inventory(directory: str) -> List[Dict]:
    """Get inventory of all files in a directory."""
    inventory = []
    path = Path(directory)
    
    if not path.exists():
        return inventory
    
    for item in sorted(path.rglob('*')):
        if item.is_file():
            rel_path = item.relative_to(path)
            size = item.stat().st_size
            
            entry = {
                'path': str(rel_path),
                'size_bytes': size,
                'extension': item.suffix,
            }
            
            if item.suffix == '.json':
                try:
                    with open(item, 'r') as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        entry['keys'] = list(data.keys())[:5]
                    elif isinstance(data, list):
                        entry['item_count'] = len(data)
                except:
                    pass
            
            inventory.append(entry)
    
    return inventory


def benchmark_lookup_latency(iterations: int = 3) -> Dict:
    """Benchmark lookup latency for sample addresses."""
    try:
        from utility_lookup import lookup_utilities_by_address
    except ImportError as e:
        return {'error': f'Could not import utility_lookup: {e}'}
    
    results = {
        'total': [],
        'electric': [],
        'gas': [],
        'water': [],
        'errors': [],
        'by_address': {}
    }
    
    for addr, expected_electric, expected_gas in BENCHMARK_ADDRESSES[:5]:  # Limit for speed
        addr_results = []
        
        for i in range(iterations):
            try:
                start = time.time()
                result = lookup_utilities_by_address(addr)
                elapsed = time.time() - start
                
                results['total'].append(elapsed)
                addr_results.append(elapsed)
                
                if result:
                    if result.get('electric'):
                        results['electric'].append(elapsed / 3)  # Approximate
                    if result.get('gas'):
                        results['gas'].append(elapsed / 3)
                    if result.get('water'):
                        results['water'].append(elapsed / 3)
                        
            except Exception as e:
                results['errors'].append({'address': addr, 'error': str(e)})
        
        if addr_results:
            results['by_address'][addr] = {
                'avg': statistics.mean(addr_results),
                'min': min(addr_results),
                'max': max(addr_results)
            }
    
    return results


def calculate_percentiles(values: List[float]) -> Dict:
    """Calculate p50, p95, p99 for a list of values."""
    if not values:
        return {'p50': None, 'p95': None, 'p99': None, 'avg': None}
    
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    
    return {
        'p50': sorted_vals[int(n * 0.50)] if n > 0 else None,
        'p95': sorted_vals[int(n * 0.95)] if n > 0 else None,
        'p99': sorted_vals[int(n * 0.99)] if n > 0 else None,
        'avg': statistics.mean(values),
        'count': n
    }


def main():
    """Generate baseline metrics report."""
    base_dir = Path(__file__).parent.parent
    
    print("=" * 70)
    print("UTILITY LOOKUP SYSTEM - BASELINE METRICS")
    print(f"Generated: {datetime.now().isoformat()}")
    print("=" * 70)
    
    # 1. Lines of Code Analysis
    print("\n" + "=" * 70)
    print("1. LINES OF CODE ANALYSIS")
    print("=" * 70)
    
    key_files = [
        'utility_lookup.py',
        'state_utility_verification.py',
        'gis_utility_lookup.py',
        'pipeline/pipeline.py',
        'pipeline/interfaces.py',
        'pipeline/smart_selector.py',
        'pipeline/sources/gas.py',
        'pipeline/sources/electric.py',
        'api.py',
        'geocoding.py',
        'confidence_scoring.py',
    ]
    
    total_loc = 0
    print(f"\n{'File':<45} {'Lines':>10}")
    print("-" * 57)
    
    for filepath in key_files:
        full_path = base_dir / filepath
        if full_path.exists():
            loc = count_lines_of_code(str(full_path))
            if loc > 0:
                total_loc += loc
            print(f"{filepath:<45} {loc:>10,}")
        else:
            print(f"{filepath:<45} {'NOT FOUND':>10}")
    
    print("-" * 57)
    print(f"{'TOTAL':<45} {total_loc:>10,}")
    
    # 2. Data File Inventory
    print("\n" + "=" * 70)
    print("2. DATA FILE INVENTORY")
    print("=" * 70)
    
    data_dir = base_dir / 'data'
    inventory = get_file_inventory(str(data_dir))
    
    json_files = [f for f in inventory if f['extension'] == '.json']
    print(f"\nTotal JSON files: {len(json_files)}")
    print(f"\n{'File':<50} {'Size':>12}")
    print("-" * 64)
    
    for f in sorted(json_files, key=lambda x: x['size_bytes'], reverse=True)[:20]:
        size_kb = f['size_bytes'] / 1024
        print(f"{f['path']:<50} {size_kb:>10.1f} KB")
    
    total_size = sum(f['size_bytes'] for f in json_files)
    print("-" * 64)
    print(f"{'TOTAL':<50} {total_size/1024:>10.1f} KB")
    
    # 3. Pipeline Source Inventory
    print("\n" + "=" * 70)
    print("3. PIPELINE SOURCE INVENTORY")
    print("=" * 70)
    
    sources_dir = base_dir / 'pipeline' / 'sources'
    if sources_dir.exists():
        for source_file in sources_dir.glob('*.py'):
            if source_file.name != '__init__.py':
                loc = count_lines_of_code(str(source_file))
                print(f"\n{source_file.name}: {loc} lines")
                
                # Try to extract source classes
                try:
                    with open(source_file, 'r') as f:
                        content = f.read()
                    
                    import re
                    classes = re.findall(r'class (\w+)\(DataSource\):', content)
                    if classes:
                        print(f"  Sources: {', '.join(classes)}")
                except:
                    pass
    
    # 4. Latency Benchmark (optional - can be slow)
    print("\n" + "=" * 70)
    print("4. LATENCY BENCHMARK")
    print("=" * 70)
    
    run_latency = os.environ.get('RUN_LATENCY_BENCHMARK', 'false').lower() == 'true'
    
    if run_latency:
        print("\nRunning latency benchmark (this may take a few minutes)...")
        latency_results = benchmark_lookup_latency(iterations=2)
        
        if 'error' in latency_results:
            print(f"Error: {latency_results['error']}")
        else:
            print("\nLatency Statistics (seconds):")
            print("-" * 40)
            
            for category in ['total', 'electric', 'gas', 'water']:
                if latency_results.get(category):
                    stats = calculate_percentiles(latency_results[category])
                    print(f"\n{category.upper()}:")
                    print(f"  Count: {stats['count']}")
                    print(f"  Avg:   {stats['avg']:.3f}s")
                    print(f"  P50:   {stats['p50']:.3f}s")
                    print(f"  P95:   {stats['p95']:.3f}s")
                    print(f"  P99:   {stats['p99']:.3f}s")
            
            if latency_results.get('errors'):
                print(f"\nErrors: {len(latency_results['errors'])}")
                for err in latency_results['errors'][:5]:
                    print(f"  - {err['address']}: {err['error']}")
    else:
        print("\nSkipped (set RUN_LATENCY_BENCHMARK=true to enable)")
    
    # 5. Test Coverage Summary
    print("\n" + "=" * 70)
    print("5. TEST COVERAGE SUMMARY")
    print("=" * 70)
    
    tests_dir = base_dir / 'tests'
    if tests_dir.exists():
        golden_file = tests_dir / 'golden_addresses.json'
        if golden_file.exists():
            with open(golden_file, 'r') as f:
                golden = json.load(f)
            tests = golden.get('tests', [])
            print(f"\nGolden test addresses: {len(tests)}")
            
            # Count by state
            states = {}
            for test in tests:
                state = test.get('state', 'Unknown')
                states[state] = states.get(state, 0) + 1
            
            print("\nTests by state:")
            for state, count in sorted(states.items(), key=lambda x: -x[1])[:10]:
                print(f"  {state}: {count}")
    
    # 6. Summary
    print("\n" + "=" * 70)
    print("6. SUMMARY - REFACTORING TARGETS")
    print("=" * 70)
    
    print(f"""
Current State:
  - Total lines of code (key files): {total_loc:,}
  - Data files: {len(json_files)}
  - Pipeline sources: Electric, Gas (Water missing)

Target State (after refactor):
  - Lines of code: < 2,000
  - Data files: < 10
  - Pipeline sources: Electric, Gas, Water (unified)

Key Files to Refactor:
  - utility_lookup.py (3,464 lines → < 300 lines)
  - state_utility_verification.py (1,401 lines → DELETE)
  - pipeline/sources/water.py (NEW)
""")
    
    print("\n" + "=" * 70)
    print("END OF BASELINE METRICS REPORT")
    print("=" * 70)


if __name__ == "__main__":
    main()
