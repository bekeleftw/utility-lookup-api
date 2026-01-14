#!/usr/bin/env python3
"""
Automated test suite for utility lookups.
Tests known addresses against expected utility providers to catch regressions.

Usage:
    python test_addresses.py              # Run all tests
    python test_addresses.py --verbose    # Show detailed output
    python test_addresses.py --streaming  # Test streaming API functions
    python test_addresses.py --api        # Test against live Railway API
"""

import json
import sys
import argparse
from typing import Dict, List, Optional
from dataclasses import dataclass

# Test addresses with known/expected utility providers
# Format: address, expected_electric, expected_gas, expected_water
TEST_CASES = [
    # Texas - Austin area
    {
        "address": "1725 Toomey Rd, Austin, TX 78704",
        "expected": {
            "electric": "Austin Energy",
            "gas": "Texas Gas Service",
            "water": "Austin Water"
        },
        "notes": "Downtown Austin - municipal utilities"
    },
    {
        "address": "301 Treasure Trove Path, Kyle, TX 78640",
        "expected": {
            "electric": None,  # Could be Pedernales or Bluebonnet
            "gas": None,
            "water": "City of Kyle"
        },
        "notes": "Kyle TX - City water, not Crosswinds MUD"
    },
    {
        "address": "100 Congress Ave, Austin, TX 78701",
        "expected": {
            "electric": "Austin Energy",
            "gas": "Texas Gas Service",
            "water": "Austin Water"
        },
        "notes": "Downtown Austin"
    },
    # Texas - Houston area
    {
        "address": "1000 Main St, Houston, TX 77002",
        "expected": {
            "electric": "CenterPoint Energy",  # or Reliant - deregulated
            "gas": "CenterPoint Energy",
            "water": None
        },
        "notes": "Downtown Houston"
    },
    # Texas - Dallas area
    {
        "address": "1500 Marilla St, Dallas, TX 75201",
        "expected": {
            "electric": None,  # Deregulated - Oncor delivers
            "gas": "Atmos Energy",
            "water": None
        },
        "notes": "Downtown Dallas"
    },
    # Texas - San Antonio
    {
        "address": "100 Military Plaza, San Antonio, TX 78205",
        "expected": {
            "electric": "CPS Energy",
            "gas": "CPS Energy",
            "water": "San Antonio Water System"
        },
        "notes": "San Antonio - CPS serves electric and gas"
    },
    # South Carolina
    {
        "address": "1405 Fernwood Glendale Rd, Spartanburg, SC 29307",
        "expected": {
            "electric": "Duke Energy",
            "gas": None,
            "water": None
        },
        "notes": "Spartanburg SC - Duke Energy territory"
    },
    # California
    {
        "address": "200 N Spring St, Los Angeles, CA 90012",
        "expected": {
            "electric": "LADWP",
            "gas": "SoCalGas",
            "water": "LADWP"
        },
        "notes": "Los Angeles - LADWP municipal"
    },
    {
        "address": "1 Dr Carlton B Goodlett Pl, San Francisco, CA 94102",
        "expected": {
            "electric": "PG&E",
            "gas": "PG&E",
            "water": "San Francisco"
        },
        "notes": "San Francisco City Hall"
    },
    # New York
    {
        "address": "350 5th Ave, New York, NY 10118",
        "expected": {
            "electric": "Con Edison",
            "gas": "Con Edison",
            "water": None
        },
        "notes": "Empire State Building - Con Ed territory"
    },
    # Florida
    {
        "address": "400 S Orange Ave, Orlando, FL 32801",
        "expected": {
            "electric": "OUC",  # Orlando Utilities Commission
            "gas": None,  # Florida has limited natural gas
            "water": "OUC"
        },
        "notes": "Orlando - OUC municipal"
    },
    {
        "address": "100 N Biscayne Blvd, Miami, FL 33132",
        "expected": {
            "electric": "FPL",  # Florida Power & Light
            "gas": None,
            "water": None
        },
        "notes": "Miami - FPL territory"
    },
    # Colorado
    {
        "address": "200 W Colfax Ave, Denver, CO 80202",
        "expected": {
            "electric": "Xcel Energy",
            "gas": "Xcel Energy",
            "water": "Denver Water"
        },
        "notes": "Denver City Hall"
    },
    # Arizona
    {
        "address": "200 W Washington St, Phoenix, AZ 85003",
        "expected": {
            "electric": "APS",  # Arizona Public Service
            "gas": "Southwest Gas",
            "water": None
        },
        "notes": "Phoenix City Hall"
    },
    # Washington
    {
        "address": "600 4th Ave, Seattle, WA 98104",
        "expected": {
            "electric": "Seattle City Light",
            "gas": "Puget Sound Energy",
            "water": "Seattle Public Utilities"
        },
        "notes": "Seattle City Hall - municipal electric"
    },
    # Illinois
    {
        "address": "121 N LaSalle St, Chicago, IL 60602",
        "expected": {
            "electric": "ComEd",
            "gas": "Peoples Gas",
            "water": None
        },
        "notes": "Chicago City Hall"
    },
    # Georgia
    {
        "address": "55 Trinity Ave SW, Atlanta, GA 30303",
        "expected": {
            "electric": "Georgia Power",
            "gas": "Atlanta Gas Light",
            "water": None
        },
        "notes": "Atlanta City Hall"
    },
    # Rural/Edge cases
    {
        "address": "1 Main St, Rural Hall, NC 27045",
        "expected": {
            "electric": "Duke Energy",
            "gas": None,  # May be propane area
            "water": None
        },
        "notes": "Small town NC"
    },
    # Pennsylvania
    {
        "address": "1400 John F Kennedy Blvd, Philadelphia, PA 19107",
        "expected": {
            "electric": "PECO",
            "gas": "PECO",
            "water": None
        },
        "notes": "Philadelphia City Hall"
    },
    # Ohio
    {
        "address": "601 Lakeside Ave, Cleveland, OH 44114",
        "expected": {
            "electric": "Cleveland Public Power",
            "gas": "Dominion Energy",
            "water": None
        },
        "notes": "Cleveland - municipal electric"
    },
    {
        "address": "90 W Broad St, Columbus, OH 43215",
        "expected": {
            "electric": "AEP Ohio",
            "gas": "Columbia Gas",
            "water": None
        },
        "notes": "Columbus OH"
    },
    # Michigan
    {
        "address": "2 Woodward Ave, Detroit, MI 48226",
        "expected": {
            "electric": "DTE Energy",
            "gas": "DTE Energy",
            "water": None
        },
        "notes": "Detroit - DTE territory"
    },
    # Massachusetts
    {
        "address": "1 City Hall Square, Boston, MA 02201",
        "expected": {
            "electric": "Eversource",
            "gas": "National Grid",
            "water": None
        },
        "notes": "Boston City Hall"
    },
    # Virginia
    {
        "address": "900 E Broad St, Richmond, VA 23219",
        "expected": {
            "electric": "Dominion Energy",
            "gas": "Virginia Natural Gas",
            "water": None
        },
        "notes": "Richmond VA"
    },
    {
        "address": "2100 Clarendon Blvd, Arlington, VA 22201",
        "expected": {
            "electric": "Dominion Energy",
            "gas": "Washington Gas",
            "water": None
        },
        "notes": "Arlington VA - DC metro area"
    },
    # Maryland
    {
        "address": "100 N Holliday St, Baltimore, MD 21202",
        "expected": {
            "electric": "BGE",
            "gas": "BGE",
            "water": None
        },
        "notes": "Baltimore City Hall"
    },
    # Tennessee
    {
        "address": "1 Public Square, Nashville, TN 37201",
        "expected": {
            "electric": "Nashville Electric Service",
            "gas": "Piedmont Natural Gas",
            "water": None
        },
        "notes": "Nashville - municipal electric"
    },
    {
        "address": "125 N Main St, Memphis, TN 38103",
        "expected": {
            "electric": "MLGW",
            "gas": "MLGW",
            "water": "MLGW"
        },
        "notes": "Memphis - MLGW municipal"
    },
    # Minnesota
    {
        "address": "350 S 5th St, Minneapolis, MN 55415",
        "expected": {
            "electric": "Xcel Energy",
            "gas": "CenterPoint Energy",
            "water": None
        },
        "notes": "Minneapolis City Hall"
    },
    # Missouri
    {
        "address": "1200 Market St, St. Louis, MO 63103",
        "expected": {
            "electric": "Ameren Missouri",
            "gas": "Spire",
            "water": None
        },
        "notes": "St. Louis City Hall"
    },
    {
        "address": "414 E 12th St, Kansas City, MO 64106",
        "expected": {
            "electric": "Evergy",
            "gas": "Spire",
            "water": None
        },
        "notes": "Kansas City MO"
    },
    # Wisconsin
    {
        "address": "200 E Wells St, Milwaukee, WI 53202",
        "expected": {
            "electric": "WE Energies",
            "gas": "WE Energies",
            "water": None
        },
        "notes": "Milwaukee City Hall"
    },
    # Indiana
    {
        "address": "200 E Washington St, Indianapolis, IN 46204",
        "expected": {
            "electric": "AES Indiana",
            "gas": "Citizens Gas",
            "water": None
        },
        "notes": "Indianapolis"
    },
    # Nevada
    {
        "address": "495 S Main St, Las Vegas, NV 89101",
        "expected": {
            "electric": "NV Energy",
            "gas": "Southwest Gas",
            "water": None
        },
        "notes": "Las Vegas City Hall"
    },
    # Oregon
    {
        "address": "1221 SW 4th Ave, Portland, OR 97204",
        "expected": {
            "electric": "Portland General Electric",
            "gas": "NW Natural",
            "water": None
        },
        "notes": "Portland City Hall"
    },
    # Utah
    {
        "address": "451 S State St, Salt Lake City, UT 84111",
        "expected": {
            "electric": "Rocky Mountain Power",
            "gas": "Dominion Energy",
            "water": None
        },
        "notes": "Salt Lake City"
    },
    # Oklahoma
    {
        "address": "200 N Walker Ave, Oklahoma City, OK 73102",
        "expected": {
            "electric": "OG&E",
            "gas": "Oklahoma Natural Gas",
            "water": None
        },
        "notes": "Oklahoma City"
    },
    # Connecticut
    {
        "address": "165 Capitol Ave, Hartford, CT 06106",
        "expected": {
            "electric": "Eversource",
            "gas": "Eversource",
            "water": None
        },
        "notes": "Hartford CT"
    },
    # Kentucky
    {
        "address": "601 W Jefferson St, Louisville, KY 40202",
        "expected": {
            "electric": "LG&E",
            "gas": "LG&E",
            "water": None
        },
        "notes": "Louisville - LG&E territory"
    },
    # Louisiana
    {
        "address": "1300 Perdido St, New Orleans, LA 70112",
        "expected": {
            "electric": "Entergy New Orleans",
            "gas": "Entergy New Orleans",
            "water": None
        },
        "notes": "New Orleans City Hall"
    },
    # Alabama
    {
        "address": "710 20th St N, Birmingham, AL 35203",
        "expected": {
            "electric": "Alabama Power",
            "gas": "Spire",
            "water": None
        },
        "notes": "Birmingham AL"
    },
    # South Carolina - additional
    {
        "address": "100 Broad St, Charleston, SC 29401",
        "expected": {
            "electric": "Dominion Energy",
            "gas": None,
            "water": None
        },
        "notes": "Charleston SC"
    },
    # New Mexico
    {
        "address": "1 Civic Plaza NW, Albuquerque, NM 87102",
        "expected": {
            "electric": "PNM",
            "gas": "New Mexico Gas Company",
            "water": None
        },
        "notes": "Albuquerque City Hall"
    },
    # Hawaii
    {
        "address": "530 S King St, Honolulu, HI 96813",
        "expected": {
            "electric": "Hawaiian Electric",
            "gas": None,  # Hawaii Gas (propane)
            "water": None
        },
        "notes": "Honolulu - Hawaiian Electric"
    },
    # Alaska
    {
        "address": "632 W 6th Ave, Anchorage, AK 99501",
        "expected": {
            "electric": "Chugach Electric",
            "gas": "ENSTAR Natural Gas",
            "water": None
        },
        "notes": "Anchorage AK"
    },
    # Texas - additional rural
    {
        "address": "100 E Main St, Fredericksburg, TX 78624",
        "expected": {
            "electric": "Pedernales Electric",
            "gas": None,  # Propane area
            "water": None
        },
        "notes": "Fredericksburg TX - PEC territory"
    },
    {
        "address": "200 E San Antonio St, New Braunfels, TX 78130",
        "expected": {
            "electric": "New Braunfels Utilities",
            "gas": None,
            "water": "New Braunfels Utilities"
        },
        "notes": "New Braunfels - municipal"
    },
    # California - additional
    {
        "address": "915 I St, Sacramento, CA 95814",
        "expected": {
            "electric": "SMUD",
            "gas": "PG&E",
            "water": None
        },
        "notes": "Sacramento - SMUD municipal electric"
    },
    {
        "address": "202 C St, San Diego, CA 92101",
        "expected": {
            "electric": "SDG&E",
            "gas": "SDG&E",
            "water": "San Diego"
        },
        "notes": "San Diego City Hall"
    },
]


@dataclass
class TestResult:
    address: str
    utility_type: str
    expected: Optional[str]
    actual: Optional[str]
    passed: bool
    confidence: Optional[str] = None
    error: Optional[str] = None


def normalize_name(name: Optional[str]) -> Optional[str]:
    """Normalize utility name for comparison."""
    if not name:
        return None
    # Remove common suffixes and normalize
    name = name.upper()
    for suffix in [', LLC', ', INC', ' INC', ' LLC', ' CORP', ' CORPORATION', 
                   ' COMPANY', ' CO', ' UTILITY', ' UTILITIES', ' ELECTRIC',
                   ' ENERGY', ' POWER', ' GAS', ' WATER']:
        name = name.replace(suffix, '')
    return name.strip()


def names_match(expected: Optional[str], actual: Optional[str]) -> bool:
    """Check if utility names match (fuzzy)."""
    if expected is None:
        return True  # No expectation = pass
    if actual is None:
        return False
    
    exp_norm = normalize_name(expected)
    act_norm = normalize_name(actual)
    
    # Exact match
    if exp_norm == act_norm:
        return True
    
    # Partial match (expected is contained in actual or vice versa)
    if exp_norm in act_norm or act_norm in exp_norm:
        return True
    
    # Handle common aliases
    aliases = {
        'LADWP': ['LOS ANGELES DEPARTMENT OF WATER', 'LA DEPT OF WATER', 'LOS ANGELES DWP'],
        'PG&E': ['PACIFIC GAS', 'PACIFIC GAS AND ELECTRIC', 'PG AND E', 'PACIFIC GAS & ELECTRIC', 'PACIFIC'],
        'PECO': ['PECO ENERGY', 'PHILADELPHIA ELECTRIC'],
        'COMED': ['COMMONWEALTH EDISON'],
        'CON EDISON': ['CONSOLIDATED EDISON', 'CON ED'],
        'FPL': ['FLORIDA POWER', 'FLORIDA POWER & LIGHT', 'NEXTERA', 'FLORIDA POWER AND LIGHT', 'FLORIDA'],
        'APS': ['ARIZONA PUBLIC SERVICE'],
        'OUC': ['ORLANDO UTILITIES', 'ORLANDO UTIL COMM'],
        'DUKE': ['DUKE ENERGY', 'DUKE CAROLINAS', 'DUKE PROGRESS'],
        'XCEL': ['XCEL ENERGY', 'PUBLIC SERVICE OF COLORADO', 'PUBLIC SERVICE CO OF COLORADO', 'PSCO', 'PUBLIC SERVICE CO', 'PUBLIC SERVICE'],
        'CENTERPOINT': ['CENTERPOINT ENERGY', 'RELIANT'],
        'CPS': ['CPS ENERGY'],
        'SEATTLE CITY LIGHT': ['SEATTLE CITY', 'SCL'],
        'PUGET SOUND': ['PSE', 'PUGET SOUND ENERGY'],
        'PEOPLES GAS': ['PEOPLES', 'PEOPLES GAS LIGHT'],
        'ATLANTA GAS LIGHT': ['AGL', 'ATLANTA GAS'],
        'SOCALGAS': ['SOUTHERN CALIFORNIA GAS', 'SO CAL GAS', 'SOCAL GAS'],
        'SOUTHWEST GAS': ['SW GAS'],
        'DTE': ['DTE ENERGY', 'DETROIT EDISON'],
        'DOMINION': ['DOMINION ENERGY', 'VIRGINIA POWER', 'DOMINION VIRGINIA'],
        'BGE': ['BALTIMORE GAS', 'BALTIMORE GAS AND ELECTRIC'],
        'WE ENERGIES': ['WISCONSIN ELECTRIC', 'WISCONSIN GAS', 'WE'],
        'AMEREN': ['AMEREN MISSOURI', 'AMEREN ILLINOIS', 'UNION ELECTRIC'],
        'EVERGY': ['KANSAS CITY POWER', 'KCP&L', 'WESTAR'],
        'ENTERGY': ['ENTERGY NEW ORLEANS', 'ENTERGY LOUISIANA', 'ENTERGY ARKANSAS'],
        'AEP': ['AEP OHIO', 'AMERICAN ELECTRIC POWER', 'AEP TEXAS'],
        'EVERSOURCE': ['NSTAR', 'NORTHEAST UTILITIES', 'CL&P', 'PSNH'],
        'NATIONAL GRID': ['KEYSPAN', 'NIAGARA MOHAWK'],
        'NV ENERGY': ['NEVADA POWER', 'SIERRA PACIFIC'],
        'ROCKY MOUNTAIN': ['ROCKY MOUNTAIN POWER', 'PACIFICORP'],
        'OG&E': ['OKLAHOMA GAS', 'OKLAHOMA GAS AND ELECTRIC', 'OGE'],
        'LG&E': ['LOUISVILLE GAS', 'LOUISVILLE GAS AND ELECTRIC', 'LGE', 'LG&E AND KU'],
        'ALABAMA POWER': ['ALABAMA', 'SOUTHERN COMPANY'],
        'GEORGIA POWER': ['GEORGIA', 'SOUTHERN COMPANY'],
        'MLGW': ['MEMPHIS LIGHT', 'MEMPHIS LIGHT GAS AND WATER'],
        'NES': ['NASHVILLE ELECTRIC', 'NASHVILLE ELECTRIC SERVICE'],
        'SMUD': ['SACRAMENTO MUNICIPAL', 'SACRAMENTO MUNICIPAL UTILITY'],
        'SDG&E': ['SAN DIEGO GAS', 'SAN DIEGO GAS AND ELECTRIC', 'SDGE', 'SEMPRA'],
        'PNM': ['PUBLIC SERVICE OF NEW MEXICO', 'PUBLIC SERVICE NEW MEXICO'],
        'HAWAIIAN ELECTRIC': ['HECO', 'HAWAIIAN'],
        'CHUGACH': ['CHUGACH ELECTRIC'],
        'PEDERNALES': ['PEDERNALES ELECTRIC', 'PEC'],
        'NEW BRAUNFELS': ['NEW BRAUNFELS UTILITIES', 'NBU'],
        'SPIRE': ['LACLEDE GAS', 'ALAGASCO'],
        'PORTLAND GENERAL': ['PORTLAND GENERAL ELECTRIC', 'PGE OREGON'],
        'NW NATURAL': ['NORTHWEST NATURAL'],
        'AES INDIANA': ['INDIANAPOLIS POWER', 'IPL', 'AES'],
        'CITIZENS GAS': ['CITIZENS'],
    }
    
    for canonical, variations in aliases.items():
        exp_matches = (exp_norm == canonical or 
                       canonical in exp_norm or 
                       any(v in exp_norm for v in variations) or
                       any(exp_norm in v for v in variations))
        act_matches = (act_norm == canonical or 
                       canonical in act_norm or 
                       any(v in act_norm for v in variations) or
                       any(act_norm in v for v in variations))
        if exp_matches and act_matches:
            return True
    
    return False


def test_with_main_lookup(test_case: Dict, verbose: bool = False) -> List[TestResult]:
    """Test using the main lookup_utilities_by_address function."""
    from utility_lookup import lookup_utilities_by_address
    
    results = []
    address = test_case["address"]
    expected = test_case["expected"]
    
    try:
        result = lookup_utilities_by_address(address)
        
        if not result:
            for util_type in ["electric", "gas", "water"]:
                results.append(TestResult(
                    address=address,
                    utility_type=util_type,
                    expected=expected.get(util_type),
                    actual=None,
                    passed=expected.get(util_type) is None,
                    error="Lookup returned None"
                ))
            return results
        
        # Check electric
        electric_result = result.get("electric", {})
        electric_name = electric_result.get("NAME") if electric_result else None
        results.append(TestResult(
            address=address,
            utility_type="electric",
            expected=expected.get("electric"),
            actual=electric_name,
            passed=names_match(expected.get("electric"), electric_name),
            confidence=electric_result.get("_confidence") if electric_result else None
        ))
        
        # Check gas
        gas_result = result.get("gas", {})
        gas_name = gas_result.get("NAME") if gas_result else None
        results.append(TestResult(
            address=address,
            utility_type="gas",
            expected=expected.get("gas"),
            actual=gas_name,
            passed=names_match(expected.get("gas"), gas_name),
            confidence=gas_result.get("_confidence") if gas_result else None
        ))
        
        # Check water
        water_result = result.get("water", {})
        water_name = water_result.get("NAME") if water_result else None
        results.append(TestResult(
            address=address,
            utility_type="water",
            expected=expected.get("water"),
            actual=water_name,
            passed=names_match(expected.get("water"), water_name),
            confidence=water_result.get("_confidence") if water_result else None
        ))
        
    except Exception as e:
        for util_type in ["electric", "gas", "water"]:
            results.append(TestResult(
                address=address,
                utility_type=util_type,
                expected=expected.get(util_type),
                actual=None,
                passed=False,
                error=str(e)
            ))
    
    return results


def test_with_streaming_api(test_case: Dict, verbose: bool = False) -> List[TestResult]:
    """Test using the streaming API individual lookup functions."""
    from utility_lookup import (
        geocode_address, 
        lookup_electric_only, 
        lookup_gas_only, 
        lookup_water_only
    )
    
    results = []
    address = test_case["address"]
    expected = test_case["expected"]
    
    try:
        # Geocode first
        location = geocode_address(address)
        if not location:
            for util_type in ["electric", "gas", "water"]:
                results.append(TestResult(
                    address=address,
                    utility_type=util_type,
                    expected=expected.get(util_type),
                    actual=None,
                    passed=False,
                    error="Geocoding failed"
                ))
            return results
        
        lat, lon = location["lat"], location["lon"]
        city = location.get("city")
        county = location.get("county")
        state = location.get("state")
        zip_code = location.get("zip_code")
        
        # Test electric
        try:
            electric = lookup_electric_only(lat, lon, city, county, state, zip_code)
            electric_name = electric.get("NAME") if electric else None
            results.append(TestResult(
                address=address,
                utility_type="electric",
                expected=expected.get("electric"),
                actual=electric_name,
                passed=names_match(expected.get("electric"), electric_name),
                confidence=electric.get("_confidence") if electric else None
            ))
        except Exception as e:
            results.append(TestResult(
                address=address,
                utility_type="electric",
                expected=expected.get("electric"),
                actual=None,
                passed=False,
                error=str(e)
            ))
        
        # Test gas
        try:
            gas = lookup_gas_only(lat, lon, city, county, state, zip_code)
            gas_name = gas.get("NAME") if gas else None
            results.append(TestResult(
                address=address,
                utility_type="gas",
                expected=expected.get("gas"),
                actual=gas_name,
                passed=names_match(expected.get("gas"), gas_name),
                confidence=gas.get("_confidence") if gas else None
            ))
        except Exception as e:
            results.append(TestResult(
                address=address,
                utility_type="gas",
                expected=expected.get("gas"),
                actual=None,
                passed=False,
                error=str(e)
            ))
        
        # Test water
        try:
            water = lookup_water_only(lat, lon, city, county, state, zip_code, address)
            water_name = water.get("NAME") if water else None
            results.append(TestResult(
                address=address,
                utility_type="water",
                expected=expected.get("water"),
                actual=water_name,
                passed=names_match(expected.get("water"), water_name),
                confidence=water.get("_confidence") if water else None
            ))
        except Exception as e:
            results.append(TestResult(
                address=address,
                utility_type="water",
                expected=expected.get("water"),
                actual=None,
                passed=False,
                error=str(e)
            ))
        
    except Exception as e:
        for util_type in ["electric", "gas", "water"]:
            results.append(TestResult(
                address=address,
                utility_type=util_type,
                expected=expected.get(util_type),
                actual=None,
                passed=False,
                error=str(e)
            ))
    
    return results


def test_with_live_api(test_case: Dict, api_url: str, verbose: bool = False) -> List[TestResult]:
    """Test against the live Railway API."""
    import requests
    
    results = []
    address = test_case["address"]
    expected = test_case["expected"]
    
    try:
        response = requests.get(
            f"{api_url}/api/lookup",
            params={"address": address},
            timeout=30
        )
        response.raise_for_status()
        result = response.json()
        
        # Check electric
        electric_result = result.get("electric", {})
        electric_name = electric_result.get("name") if electric_result else None
        results.append(TestResult(
            address=address,
            utility_type="electric",
            expected=expected.get("electric"),
            actual=electric_name,
            passed=names_match(expected.get("electric"), electric_name),
            confidence=electric_result.get("confidence") if electric_result else None
        ))
        
        # Check gas
        gas_result = result.get("gas", {})
        gas_name = gas_result.get("name") if gas_result else None
        results.append(TestResult(
            address=address,
            utility_type="gas",
            expected=expected.get("gas"),
            actual=gas_name,
            passed=names_match(expected.get("gas"), gas_name),
            confidence=gas_result.get("confidence") if gas_result else None
        ))
        
        # Check water
        water_result = result.get("water", {})
        water_name = water_result.get("name") if water_result else None
        results.append(TestResult(
            address=address,
            utility_type="water",
            expected=expected.get("water"),
            actual=water_name,
            passed=names_match(expected.get("water"), water_name),
            confidence=water_result.get("confidence") if water_result else None
        ))
        
    except Exception as e:
        for util_type in ["electric", "gas", "water"]:
            results.append(TestResult(
                address=address,
                utility_type=util_type,
                expected=expected.get(util_type),
                actual=None,
                passed=False,
                error=str(e)
            ))
    
    return results


def print_results(all_results: List[TestResult], verbose: bool = False):
    """Print test results summary."""
    passed = sum(1 for r in all_results if r.passed)
    failed = sum(1 for r in all_results if not r.passed)
    total = len(all_results)
    
    print("\n" + "=" * 70)
    print(f"TEST RESULTS: {passed}/{total} passed ({100*passed/total:.1f}%)")
    print("=" * 70)
    
    # Group by address
    by_address = {}
    for r in all_results:
        if r.address not in by_address:
            by_address[r.address] = []
        by_address[r.address].append(r)
    
    # Print failures first
    failures = [(addr, results) for addr, results in by_address.items() 
                if any(not r.passed for r in results)]
    
    if failures:
        print("\n❌ FAILURES:")
        print("-" * 70)
        for addr, results in failures:
            print(f"\n📍 {addr}")
            for r in results:
                if not r.passed:
                    status = "❌ FAIL"
                    if r.error:
                        print(f"  {status} [{r.utility_type}] Error: {r.error}")
                    else:
                        print(f"  {status} [{r.utility_type}] Expected: {r.expected or 'None'}, Got: {r.actual or 'None'}")
                elif verbose:
                    print(f"  ✅ PASS [{r.utility_type}] {r.actual} ({r.confidence})")
    
    if verbose:
        print("\n✅ PASSES:")
        print("-" * 70)
        passes = [(addr, results) for addr, results in by_address.items() 
                  if all(r.passed for r in results)]
        for addr, results in passes:
            print(f"\n📍 {addr}")
            for r in results:
                print(f"  ✅ [{r.utility_type}] {r.actual or 'None'} ({r.confidence})")
    
    print("\n" + "=" * 70)
    print(f"SUMMARY: {passed} passed, {failed} failed")
    if failed > 0:
        print("Run with --verbose for more details")
    print("=" * 70)
    
    return failed == 0


def main():
    parser = argparse.ArgumentParser(description="Test utility lookups against known addresses")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output")
    parser.add_argument("--streaming", "-s", action="store_true", help="Test streaming API functions")
    parser.add_argument("--api", "-a", action="store_true", help="Test against live Railway API")
    parser.add_argument("--api-url", default="https://utility-lookup-api-production.up.railway.app",
                        help="API URL for live testing")
    parser.add_argument("--limit", "-l", type=int, help="Limit number of test cases")
    args = parser.parse_args()
    
    test_cases = TEST_CASES[:args.limit] if args.limit else TEST_CASES
    
    print(f"\n🧪 Running {len(test_cases)} test cases...")
    
    if args.api:
        print(f"   Mode: Live API ({args.api_url})")
        test_func = lambda tc, v: test_with_live_api(tc, args.api_url, v)
    elif args.streaming:
        print("   Mode: Streaming API functions")
        test_func = test_with_streaming_api
    else:
        print("   Mode: Main lookup function")
        test_func = test_with_main_lookup
    
    all_results = []
    for i, test_case in enumerate(test_cases, 1):
        print(f"   [{i}/{len(test_cases)}] Testing: {test_case['address'][:50]}...")
        results = test_func(test_case, args.verbose)
        all_results.extend(results)
    
    success = print_results(all_results, args.verbose)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
