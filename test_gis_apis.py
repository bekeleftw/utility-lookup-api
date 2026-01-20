#!/usr/bin/env python3
"""
Test script to verify state-specific GIS APIs are working.
Run this on the deployed server to check if the latest code is deployed.
"""

from gis_utility_lookup import (
    lookup_water_utility_gis,
    lookup_electric_utility_gis, 
    lookup_gas_utility_gis,
    STATES_WITH_WATER_GIS,
    STATE_ELECTRIC_APIS,
    STATE_GAS_APIS
)

print("=" * 60)
print("GIS API Integration Test")
print("=" * 60)

# Check what states are configured
print(f"\nWater GIS states configured: {len(STATES_WITH_WATER_GIS)}")
print(f"States: {sorted(STATES_WITH_WATER_GIS)}")

print(f"\nElectric GIS states configured: {len(STATE_ELECTRIC_APIS)}")
print(f"States: {sorted(STATE_ELECTRIC_APIS.keys())}")

print(f"\nGas GIS states configured: {len(STATE_GAS_APIS)}")
print(f"States: {sorted(STATE_GAS_APIS.keys())}")

# Test specific lookups
print("\n" + "=" * 60)
print("Testing Water Lookups")
print("=" * 60)

water_tests = [
    ("WA", 46.6021, -120.5059, "Yakima"),  # Should return YAKIMA WATER DIVISION
    ("UT", 40.7608, -111.891, "Salt Lake City"),
    ("TN", 36.1627, -86.7816, "Nashville"),
    ("MI", 42.3314, -83.0458, "Detroit"),  # No state water API, should use EPA
]

for state, lat, lon, city in water_tests:
    result = lookup_water_utility_gis(lat, lon, state)
    if result:
        print(f"{state} ({city}): {result.get('name', 'N/A')} [source: {result.get('source', 'unknown')}]")
    else:
        print(f"{state} ({city}): NO RESULT")

print("\n" + "=" * 60)
print("Testing Electric Lookups")
print("=" * 60)

electric_tests = [
    ("MI", 42.3314, -83.0458, "Detroit"),
    ("KY", 38.2527, -85.7585, "Louisville"),
    ("IN", 39.7684, -86.1581, "Indianapolis"),
    ("NJ", 40.7357, -74.1724, "Newark"),
]

for state, lat, lon, city in electric_tests:
    result = lookup_electric_utility_gis(lat, lon, state)
    if result:
        print(f"{state} ({city}): {result.get('name', 'N/A')} [source: {result.get('source', 'unknown')}]")
    else:
        print(f"{state} ({city}): NO RESULT")

print("\n" + "=" * 60)
print("Testing Gas Lookups")
print("=" * 60)

gas_tests = [
    ("MI", 42.3314, -83.0458, "Detroit"),
    ("WI", 43.0731, -89.4012, "Madison"),
    ("NJ", 40.7357, -74.1724, "Newark"),
]

for state, lat, lon, city in gas_tests:
    result = lookup_gas_utility_gis(lat, lon, state)
    if result:
        print(f"{state} ({city}): {result.get('name', 'N/A')} [source: {result.get('source', 'unknown')}]")
    else:
        print(f"{state} ({city}): NO RESULT")

print("\n" + "=" * 60)
print("Test Complete")
print("=" * 60)
