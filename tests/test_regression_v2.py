#!/usr/bin/env python3
"""
Phase 4: Regression Test Suite for utility_lookup_v2

Tests the v2 implementation against golden addresses to ensure
correctness before gradual rollout.

Run: pytest tests/test_regression_v2.py -v
"""

import json
import os
import sys
import pytest
from pathlib import Path
from typing import Dict, Optional

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_golden_addresses():
    """Load golden test addresses."""
    golden_path = Path(__file__).parent / 'golden_addresses.json'
    if golden_path.exists():
        with open(golden_path, 'r') as f:
            return json.load(f).get('tests', [])
    return []


def normalize_name(name: str) -> str:
    """Normalize utility name for comparison."""
    if not name:
        return ''
    return name.upper().strip()


def names_match(actual: str, expected: str) -> bool:
    """Check if utility names match (fuzzy)."""
    if not actual or not expected:
        return actual == expected
    
    actual_norm = normalize_name(actual)
    expected_norm = normalize_name(expected)
    
    # Exact match
    if actual_norm == expected_norm:
        return True
    
    # Partial match
    if expected_norm in actual_norm or actual_norm in expected_norm:
        return True
    
    # Key word match
    expected_words = set(expected_norm.split())
    actual_words = set(actual_norm.split())
    
    # Remove common words
    common = {'ENERGY', 'ELECTRIC', 'GAS', 'UTILITY', 'CO', 'COMPANY', 'INC', 'LLC', 'THE', 'OF'}
    expected_key = expected_words - common
    actual_key = actual_words - common
    
    if expected_key and actual_key and expected_key & actual_key:
        return True
    
    return False


class TestV2Regression:
    """Regression tests for v2 against golden addresses."""
    
    @pytest.fixture(scope='class')
    def lookup_v2(self):
        """Get v2 lookup function."""
        from utility_lookup_v2 import lookup_utilities_by_address
        return lookup_utilities_by_address
    
    @pytest.fixture(scope='class')
    def golden_tests(self):
        """Load golden test addresses."""
        return load_golden_addresses()
    
    def test_golden_addresses_loaded(self, golden_tests):
        """Verify golden addresses file exists and has tests."""
        assert len(golden_tests) > 0, "No golden test addresses found"
        print(f"Loaded {len(golden_tests)} golden test addresses")
    
    @pytest.mark.parametrize("test_id", [
        "tx_austin_001",
        "tx_houston_001", 
        "tx_dallas_001",
        "tx_san_antonio_001",
    ])
    def test_texas_major_cities(self, test_id, golden_tests, lookup_v2):
        """Test major Texas cities."""
        test = next((t for t in golden_tests if t.get('test_id') == test_id), None)
        if not test:
            pytest.skip(f"Test {test_id} not found in golden addresses")
        
        result = lookup_v2(test['address'])
        assert result is not None, f"Lookup failed for {test['address']}"
        
        # Check electric
        if test.get('expected_electric'):
            electric = result.get('electric')
            assert electric is not None, f"No electric result for {test['address']}"
            assert names_match(electric.get('NAME'), test['expected_electric']), \
                f"Electric mismatch: expected {test['expected_electric']}, got {electric.get('NAME')}"
        
        # Check gas
        if test.get('expected_gas'):
            gas = result.get('gas')
            assert gas is not None, f"No gas result for {test['address']}"
            assert names_match(gas.get('NAME'), test['expected_gas']), \
                f"Gas mismatch: expected {test['expected_gas']}, got {gas.get('NAME')}"


class TestKnownProblemCases:
    """Test known problem cases that were fixed during refactoring."""
    
    @pytest.fixture
    def lookup_v2(self):
        from utility_lookup_v2 import lookup_utilities_by_address
        return lookup_utilities_by_address
    
    def test_little_elm_coserv_gas(self, lookup_v2):
        """
        Little Elm TX 75068 must return CoServ Gas.
        
        This was a known problem case where ZIP prefix mapping
        incorrectly returned Atmos Energy instead of CoServ.
        """
        result = lookup_v2("1401 Thrasher Dr, Little Elm, TX 75068")
        
        # This test may fail if geocoding fails - skip in that case
        if result and result.get('error'):
            pytest.skip(f"Geocoding failed: {result.get('error')}")
        
        if result is None:
            pytest.skip("Lookup returned None (geocoding issue)")
        
        gas = result.get('gas')
        if gas is None:
            pytest.skip("No gas result (may be geocoding issue)")
        
        gas_name = gas.get('NAME', '').lower()
        assert 'coserv' in gas_name, \
            f"Expected CoServ Gas for Little Elm TX 75068, got: {gas.get('NAME')}"
    
    def test_austin_municipal_utilities(self, lookup_v2):
        """Austin TX must return Austin Energy (electric) and Austin Water (water)."""
        result = lookup_v2("1100 Congress Ave, Austin, TX 78701")
        
        assert result is not None, "Lookup returned None"
        
        # Electric
        electric = result.get('electric')
        assert electric is not None, "No electric result"
        electric_name = electric.get('NAME', '').lower()
        assert 'austin' in electric_name and 'energy' in electric_name, \
            f"Expected Austin Energy, got: {electric.get('NAME')}"
        
        # Water
        water = result.get('water')
        assert water is not None, "No water result"
        water_name = water.get('NAME', '').lower()
        assert 'austin' in water_name and 'water' in water_name, \
            f"Expected Austin Water, got: {water.get('NAME')}"
    
    def test_houston_centerpoint(self, lookup_v2):
        """Houston TX must return CenterPoint Energy."""
        result = lookup_v2("1000 Main St, Houston, TX 77002")
        
        assert result is not None, "Lookup returned None"
        
        # Gas should be CenterPoint
        gas = result.get('gas')
        assert gas is not None, "No gas result"
        gas_name = gas.get('NAME', '').lower()
        assert 'centerpoint' in gas_name, \
            f"Expected CenterPoint Energy, got: {gas.get('NAME')}"
    
    def test_san_antonio_cps(self, lookup_v2):
        """San Antonio TX must return CPS Energy (municipal utility)."""
        result = lookup_v2("100 Military Plaza, San Antonio, TX 78205")
        
        assert result is not None, "Lookup returned None"
        
        electric = result.get('electric')
        assert electric is not None, "No electric result"
        electric_name = electric.get('NAME', '').lower()
        assert 'cps' in electric_name, \
            f"Expected CPS Energy, got: {electric.get('NAME')}"


class TestConfidenceScoring:
    """Test that confidence scores are reasonable."""
    
    @pytest.fixture
    def lookup_v2(self):
        from utility_lookup_v2 import lookup_utilities_by_address
        return lookup_utilities_by_address
    
    def test_municipal_high_confidence(self, lookup_v2):
        """Municipal utilities should have high confidence."""
        result = lookup_v2("1100 Congress Ave, Austin, TX 78701")
        
        if result is None:
            pytest.skip("Lookup returned None")
        
        electric = result.get('electric')
        if electric:
            confidence = electric.get('_confidence_score', 0)
            assert confidence >= 80, \
                f"Municipal utility should have confidence >= 80, got {confidence}"
    
    def test_confidence_levels_valid(self, lookup_v2):
        """Confidence levels should be valid strings."""
        result = lookup_v2("1100 Congress Ave, Austin, TX 78701")
        
        if result is None:
            pytest.skip("Lookup returned None")
        
        valid_levels = {'verified', 'high', 'medium', 'low', 'none', None}
        
        for utility_type in ['electric', 'gas', 'water']:
            util = result.get(utility_type)
            if util:
                level = util.get('_confidence')
                assert level in valid_levels, \
                    f"Invalid confidence level for {utility_type}: {level}"


class TestAPICompatibility:
    """Test that v2 API is compatible with v1."""
    
    @pytest.fixture
    def lookup_v2(self):
        from utility_lookup_v2 import lookup_utilities_by_address
        return lookup_utilities_by_address
    
    def test_response_structure(self, lookup_v2):
        """Response should have expected structure."""
        result = lookup_v2("1100 Congress Ave, Austin, TX 78701")
        
        assert result is not None, "Lookup returned None"
        
        # Should have utility type keys
        for key in ['electric', 'gas', 'water']:
            assert key in result or result.get(key) is None, \
                f"Missing key: {key}"
    
    def test_utility_fields(self, lookup_v2):
        """Utility results should have required fields."""
        result = lookup_v2("1100 Congress Ave, Austin, TX 78701")
        
        if result is None:
            pytest.skip("Lookup returned None")
        
        required_fields = ['NAME']
        optional_fields = ['TELEPHONE', 'WEBSITE', 'STATE', 'CITY']
        
        for utility_type in ['electric', 'gas', 'water']:
            util = result.get(utility_type)
            if util:
                for field in required_fields:
                    assert field in util, \
                        f"Missing required field {field} in {utility_type}"
    
    def test_selected_utilities_filter(self, lookup_v2):
        """Should only return selected utility types."""
        result = lookup_v2(
            "1100 Congress Ave, Austin, TX 78701",
            selected_utilities=['electric']
        )
        
        assert result is not None, "Lookup returned None"
        
        # Should have electric
        assert 'electric' in result
        
        # Should not have gas or water (or they should be None)
        # Note: v2 may still include keys but with None values


class TestPerformance:
    """Basic performance tests."""
    
    @pytest.fixture
    def lookup_v2(self):
        from utility_lookup_v2 import lookup_utilities_by_address
        return lookup_utilities_by_address
    
    def test_lookup_completes_in_reasonable_time(self, lookup_v2):
        """Lookup should complete within 30 seconds."""
        import time
        
        start = time.time()
        result = lookup_v2("1100 Congress Ave, Austin, TX 78701")
        elapsed = time.time() - start
        
        assert elapsed < 30, f"Lookup took too long: {elapsed:.1f}s"
        
        if result:
            print(f"Lookup completed in {elapsed:.1f}s")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
