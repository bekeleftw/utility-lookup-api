#!/usr/bin/env python3
"""
Phase 0: Snapshot Tests - Capture Current Behavior

Captures current system behavior before refactoring.
Any changes in behavior after refactor need to be intentional.

Run: pytest tests/test_current_behavior.py -v
"""

import json
import os
import sys
import pytest
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Snapshot addresses covering all major scenarios
SNAPSHOT_ADDRESSES = [
    # Texas - Known problem cases
    "1401 Thrasher Dr, Little Elm, TX 75068",  # Gas: CoServ (was returning Atmos)
    "1100 Congress Ave, Austin, TX 78701",      # Municipal: Austin Energy
    "1000 Main St, Houston, TX 77002",          # Deregulated: CenterPoint
    "1500 Marilla St, Dallas, TX 75201",        # Deregulated: Oncor
    "100 Military Plaza, San Antonio, TX 78205", # Municipal: CPS Energy
    "301 Treasure Trove Path, Kyle, TX 78640",  # Co-op: Pedernales
    
    # California
    "200 N Spring St, Los Angeles, CA 90012",
    "1 Dr Carlton B Goodlett Pl, San Francisco, CA 94102",
    "202 C St, San Diego, CA 92101",
    "915 I St, Sacramento, CA 95814",
    
    # Florida
    "100 NE 1st Ave, Miami, FL 33132",
    "315 E Kennedy Blvd, Tampa, FL 33602",
    "400 S Orange Ave, Orlando, FL 32801",
    
    # New York
    "City Hall, New York, NY 10007",
    "65 Niagara Square, Buffalo, NY 14202",
    
    # Illinois
    "121 N LaSalle St, Chicago, IL 60602",
    
    # Georgia
    "55 Trinity Ave SW, Atlanta, GA 30303",
    
    # North Carolina
    "600 E 4th St, Charlotte, NC 28202",
    "1 E Edenton St, Raleigh, NC 27601",
    
    # Tennessee
    "1 Public Square, Nashville, TN 37201",
    "125 N Main St, Memphis, TN 38103",
    
    # Pennsylvania
    "1401 JFK Blvd, Philadelphia, PA 19102",
    "414 Grant St, Pittsburgh, PA 15219",
    
    # Ohio
    "90 W Broad St, Columbus, OH 43215",
    "601 Lakeside Ave, Cleveland, OH 44114",
    
    # Michigan
    "2 Woodward Ave, Detroit, MI 48226",
    
    # Arizona
    "200 W Washington St, Phoenix, AZ 85003",
    "255 W Alameda St, Tucson, AZ 85701",
    
    # Colorado
    "1437 Bannock St, Denver, CO 80202",
    
    # Washington
    "600 4th Ave, Seattle, WA 98104",
    
    # Oregon
    "1221 SW 4th Ave, Portland, OR 97204",
    
    # Nevada
    "495 S Main St, Las Vegas, NV 89101",
    
    # Massachusetts
    "1 City Hall Square, Boston, MA 02201",
    
    # Maryland
    "100 N Holliday St, Baltimore, MD 21202",
    
    # DC
    "1600 Pennsylvania Ave NW, Washington, DC 20500",
    
    # Virginia
    "900 E Broad St, Richmond, VA 23219",
    
    # Louisiana
    "1300 Perdido St, New Orleans, LA 70112",
    
    # Alabama
    "710 N 20th St, Birmingham, AL 35203",
    
    # Oklahoma
    "200 N Walker Ave, Oklahoma City, OK 73102",
    
    # Kansas
    "455 N Main St, Wichita, KS 67202",
    
    # Missouri
    "414 E 12th St, Kansas City, MO 64106",
    "1200 Market St, St. Louis, MO 63103",
    
    # Minnesota
    "350 S 5th St, Minneapolis, MN 55415",
    
    # Wisconsin
    "200 E Wells St, Milwaukee, WI 53202",
    
    # Indiana
    "200 E Washington St, Indianapolis, IN 46204",
    
    # Kentucky
    "601 W Jefferson St, Louisville, KY 40202",
    
    # New Jersey
    "920 Broad St, Newark, NJ 07102",
    
    # Connecticut
    "550 Main St, Hartford, CT 06103",
]


def get_snapshot_path() -> Path:
    """Get path to snapshot file."""
    return Path(__file__).parent / 'snapshots' / 'current_behavior.json'


def load_snapshot() -> Optional[Dict]:
    """Load existing snapshot if available."""
    path = get_snapshot_path()
    if path.exists():
        with open(path, 'r') as f:
            return json.load(f)
    return None


def save_snapshot(results: Dict):
    """Save snapshot to file."""
    path = get_snapshot_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(path, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"Snapshot saved to {path}")


def capture_current_behavior() -> Dict:
    """Capture current system behavior for all snapshot addresses."""
    from utility_lookup import lookup_utilities_by_address
    
    results = {
        '_metadata': {
            'captured_at': datetime.now().isoformat(),
            'version': 'v1_pre_refactor',
            'total_addresses': len(SNAPSHOT_ADDRESSES),
        },
        'results': {}
    }
    
    for addr in SNAPSHOT_ADDRESSES:
        print(f"Capturing: {addr}")
        try:
            result = lookup_utilities_by_address(addr)
            
            # Extract key fields for comparison
            captured = {
                'address': addr,
                'success': result is not None,
            }
            
            if result:
                for utility_type in ['electric', 'gas', 'water']:
                    util_result = result.get(utility_type)
                    if util_result:
                        captured[utility_type] = {
                            'name': util_result.get('NAME'),
                            'phone': util_result.get('TELEPHONE'),
                            'confidence': util_result.get('_confidence'),
                            'confidence_score': util_result.get('_confidence_score'),
                            'source': util_result.get('_source'),
                        }
                    else:
                        captured[utility_type] = None
            
            results['results'][addr] = captured
            
        except Exception as e:
            results['results'][addr] = {
                'address': addr,
                'success': False,
                'error': str(e)
            }
    
    return results


class TestSnapshotCapture:
    """Tests for capturing and comparing snapshots."""
    
    def test_capture_snapshot(self):
        """Capture current behavior snapshot (run once before refactor)."""
        # Only run if explicitly requested
        if os.environ.get('CAPTURE_SNAPSHOT', 'false').lower() != 'true':
            pytest.skip("Set CAPTURE_SNAPSHOT=true to capture new snapshot")
        
        results = capture_current_behavior()
        save_snapshot(results)
        
        assert results['_metadata']['total_addresses'] == len(SNAPSHOT_ADDRESSES)
        assert len(results['results']) == len(SNAPSHOT_ADDRESSES)


class TestRegressionAgainstSnapshot:
    """Compare current behavior against saved snapshot."""
    
    @pytest.fixture
    def snapshot(self):
        """Load the saved snapshot."""
        snap = load_snapshot()
        if snap is None:
            pytest.skip("No snapshot available. Run with CAPTURE_SNAPSHOT=true first.")
        return snap
    
    @pytest.fixture
    def lookup_func(self):
        """Get the lookup function."""
        from utility_lookup import lookup_utilities_by_address
        return lookup_utilities_by_address
    
    def test_snapshot_exists(self, snapshot):
        """Verify snapshot exists and has expected structure."""
        assert '_metadata' in snapshot
        assert 'results' in snapshot
        assert len(snapshot['results']) > 0
    
    @pytest.mark.parametrize("address", SNAPSHOT_ADDRESSES[:10])  # Test subset for speed
    def test_address_matches_snapshot(self, address, snapshot, lookup_func):
        """Test that current behavior matches snapshot for each address."""
        if address not in snapshot['results']:
            pytest.skip(f"Address not in snapshot: {address}")
        
        expected = snapshot['results'][address]
        
        # Get current result
        result = lookup_func(address)
        
        # Compare key fields
        for utility_type in ['electric', 'gas']:
            expected_util = expected.get(utility_type)
            
            if expected_util is None:
                # Expected no result
                if result and result.get(utility_type):
                    # Got a result when we didn't expect one - might be improvement
                    print(f"NEW: {address} now has {utility_type}: {result[utility_type].get('NAME')}")
                continue
            
            if result is None or result.get(utility_type) is None:
                pytest.fail(f"REGRESSION: {address} - {utility_type} was {expected_util['name']}, now None")
            
            actual_name = result[utility_type].get('NAME', '')
            expected_name = expected_util.get('name', '')
            
            # Fuzzy match - check if names are similar
            if expected_name and actual_name:
                expected_lower = expected_name.lower()
                actual_lower = actual_name.lower()
                
                # Allow partial matches (e.g., "Austin Energy" matches "City of Austin - Austin Energy")
                if expected_lower not in actual_lower and actual_lower not in expected_lower:
                    # Check if it's a known acceptable change
                    if not self._is_acceptable_change(address, utility_type, expected_name, actual_name):
                        pytest.fail(
                            f"CHANGE: {address} - {utility_type}\n"
                            f"  Expected: {expected_name}\n"
                            f"  Actual:   {actual_name}"
                        )
    
    def _is_acceptable_change(self, address: str, utility_type: str, old: str, new: str) -> bool:
        """Check if a change is an acceptable improvement."""
        # Known improvements from quick wins
        acceptable_changes = {
            ("1401 Thrasher Dr, Little Elm, TX 75068", "gas"): ("Atmos", "CoServ"),
        }
        
        key = (address, utility_type)
        if key in acceptable_changes:
            old_pattern, new_pattern = acceptable_changes[key]
            if old_pattern.lower() in old.lower() and new_pattern.lower() in new.lower():
                return True
        
        return False


class TestKnownCorrectResults:
    """Test known correct results that must always pass."""
    
    @pytest.fixture
    def lookup_func(self):
        """Get the lookup function."""
        from utility_lookup import lookup_utilities_by_address
        return lookup_utilities_by_address
    
    def test_little_elm_coserv_gas(self, lookup_func):
        """Little Elm TX 75068 must return CoServ Gas (tenant verified)."""
        result = lookup_func("1401 Thrasher Dr, Little Elm, TX 75068")
        
        assert result is not None, "Lookup returned None"
        assert result.get('gas') is not None, "No gas result"
        
        gas_name = result['gas'].get('NAME', '').lower()
        assert 'coserv' in gas_name, f"Expected CoServ Gas, got: {result['gas'].get('NAME')}"
    
    def test_austin_municipal_utilities(self, lookup_func):
        """Austin TX must return Austin Energy (municipal utility)."""
        result = lookup_func("1100 Congress Ave, Austin, TX 78701")
        
        assert result is not None, "Lookup returned None"
        assert result.get('electric') is not None, "No electric result"
        
        electric_name = result['electric'].get('NAME', '').lower()
        assert 'austin' in electric_name and 'energy' in electric_name, \
            f"Expected Austin Energy, got: {result['electric'].get('NAME')}"
    
    def test_houston_centerpoint(self, lookup_func):
        """Houston TX must return CenterPoint (TDU in deregulated market)."""
        result = lookup_func("1000 Main St, Houston, TX 77002")
        
        assert result is not None, "Lookup returned None"
        assert result.get('electric') is not None, "No electric result"
        
        electric_name = result['electric'].get('NAME', '').lower()
        assert 'centerpoint' in electric_name, \
            f"Expected CenterPoint, got: {result['electric'].get('NAME')}"
    
    def test_san_antonio_cps(self, lookup_func):
        """San Antonio TX must return CPS Energy (municipal utility)."""
        result = lookup_func("100 Military Plaza, San Antonio, TX 78205")
        
        assert result is not None, "Lookup returned None"
        assert result.get('electric') is not None, "No electric result"
        
        electric_name = result['electric'].get('NAME', '').lower()
        assert 'cps' in electric_name, \
            f"Expected CPS Energy, got: {result['electric'].get('NAME')}"
    
    def test_chicago_comed(self, lookup_func):
        """Chicago IL must return Commonwealth Edison."""
        result = lookup_func("121 N LaSalle St, Chicago, IL 60602")
        
        assert result is not None, "Lookup returned None"
        assert result.get('electric') is not None, "No electric result"
        
        electric_name = result['electric'].get('NAME', '').lower()
        assert 'comed' in electric_name or 'commonwealth' in electric_name, \
            f"Expected ComEd, got: {result['electric'].get('NAME')}"
    
    def test_nyc_con_edison(self, lookup_func):
        """New York City must return Con Edison."""
        result = lookup_func("City Hall, New York, NY 10007")
        
        assert result is not None, "Lookup returned None"
        assert result.get('electric') is not None, "No electric result"
        
        electric_name = result['electric'].get('NAME', '').lower()
        assert 'con' in electric_name and 'edison' in electric_name, \
            f"Expected Con Edison, got: {result['electric'].get('NAME')}"


if __name__ == "__main__":
    # Quick test run
    import argparse
    
    parser = argparse.ArgumentParser(description='Snapshot tests for utility lookup')
    parser.add_argument('--capture', action='store_true', help='Capture new snapshot')
    parser.add_argument('--compare', action='store_true', help='Compare against snapshot')
    args = parser.parse_args()
    
    if args.capture:
        os.environ['CAPTURE_SNAPSHOT'] = 'true'
        results = capture_current_behavior()
        save_snapshot(results)
        print(f"\nCaptured {len(results['results'])} addresses")
    
    elif args.compare:
        snapshot = load_snapshot()
        if snapshot:
            print(f"Snapshot has {len(snapshot['results'])} addresses")
            print(f"Captured at: {snapshot['_metadata']['captured_at']}")
        else:
            print("No snapshot found. Run with --capture first.")
    
    else:
        print("Usage: python test_current_behavior.py [--capture|--compare]")
        print("Or run with pytest: pytest tests/test_current_behavior.py -v")
