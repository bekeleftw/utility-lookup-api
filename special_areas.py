#!/usr/bin/env python3
"""
Special area detection for utility lookups.
Handles tribal lands, military bases, unincorporated areas, and other special cases.
"""

import json
import requests
from typing import Dict, Optional, List
from pathlib import Path


# Census Bureau TIGER/Line API for boundary lookups
CENSUS_GEOCODER_URL = "https://geocoding.geo.census.gov/geocoder/geographies/coordinates"


def lookup_census_geographies(lat: float, lon: float) -> Optional[Dict]:
    """
    Query Census Bureau for geographic information at coordinates.
    Returns city, county, state, tribal area, and other boundaries.
    """
    try:
        params = {
            "x": lon,
            "y": lat,
            "benchmark": "Public_AR_Current",
            "vintage": "Current_Current",
            "layers": "all",
            "format": "json"
        }
        
        response = requests.get(CENSUS_GEOCODER_URL, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        result = data.get("result", {})
        geographies = result.get("geographies", {})
        
        return geographies
    except Exception as e:
        return None


def check_tribal_land(lat: float, lon: float) -> Dict:
    """
    Check if coordinates are on tribal land.
    Uses Census Bureau American Indian/Alaska Native/Native Hawaiian Areas.
    """
    geographies = lookup_census_geographies(lat, lon)
    
    if not geographies:
        return {
            "tribal_land": None,
            "error": "Could not query Census geographies"
        }
    
    # Check for tribal areas in Census data
    tribal_areas = []
    
    # American Indian Reservations
    aiannh = geographies.get("American Indian Area/Alaska Native Area/Hawaiian Home Land", [])
    if aiannh:
        for area in aiannh:
            tribal_areas.append({
                "name": area.get("NAME"),
                "type": "American Indian Area/Alaska Native Area",
                "geoid": area.get("GEOID")
            })
    
    # Tribal Census Tracts
    tribal_tracts = geographies.get("Tribal Census Tract", [])
    if tribal_tracts:
        for tract in tribal_tracts:
            tribal_areas.append({
                "name": tract.get("NAME"),
                "type": "Tribal Census Tract",
                "geoid": tract.get("GEOID")
            })
    
    if tribal_areas:
        return {
            "tribal_land": True,
            "tribal_areas": tribal_areas,
            "primary_tribe": tribal_areas[0]["name"] if tribal_areas else None,
            "note": "This address is on tribal land. Utility services may be provided by tribal utilities or BIA. Contact tribal administration for utility information.",
            "confidence_adjustment": -20,
            "special_handling": True
        }
    
    return {
        "tribal_land": False
    }


def check_incorporated_status(lat: float, lon: float) -> Dict:
    """
    Determine if coordinates are in an incorporated city or unincorporated county area.
    """
    geographies = lookup_census_geographies(lat, lon)
    
    if not geographies:
        return {
            "incorporated": None,
            "error": "Could not query Census geographies"
        }
    
    # Check for incorporated places
    places = geographies.get("Incorporated Places", [])
    county_subdivisions = geographies.get("County Subdivisions", [])
    counties = geographies.get("Counties", [])
    
    city_name = None
    county_name = None
    
    if places:
        city_name = places[0].get("NAME")
    
    if counties:
        county_name = counties[0].get("NAME")
    
    if city_name:
        return {
            "incorporated": True,
            "city": city_name,
            "county": county_name,
            "note": None
        }
    else:
        # Unincorporated area
        subdivision_name = None
        if county_subdivisions:
            subdivision_name = county_subdivisions[0].get("NAME")
        
        return {
            "incorporated": False,
            "city": None,
            "county": county_name,
            "subdivision": subdivision_name,
            "jurisdiction": f"Unincorporated {county_name} County" if county_name else "Unincorporated area",
            "note": "This is an unincorporated area. Utility services may be limited or provided by special districts.",
            "water_likelihood": "well_or_special_district",
            "sewer_likelihood": "septic_or_special_district",
            "special_handling": True
        }


# Known military installations with utility information
MILITARY_INSTALLATIONS = {
    "fort_cavazos": {
        "name": "Fort Cavazos (formerly Fort Hood)",
        "state": "TX",
        "cities": ["Killeen", "Copperas Cove", "Harker Heights"],
        "zip_codes": ["76544", "76549"],
        "electric": "TXU Energy (privatized housing)",
        "housing_manager": "Lendlease",
        "note": "Military housing utilities are privatized. Contact housing office."
    },
    "jbsa": {
        "name": "Joint Base San Antonio",
        "state": "TX",
        "cities": ["San Antonio"],
        "zip_codes": ["78234", "78236"],
        "electric": "CPS Energy",
        "housing_manager": "Balfour Beatty",
        "note": "Includes Fort Sam Houston, Lackland AFB, Randolph AFB"
    },
    "fort_bragg": {
        "name": "Fort Liberty (formerly Fort Bragg)",
        "state": "NC",
        "cities": ["Fayetteville"],
        "zip_codes": ["28307", "28310"],
        "electric": "Duke Energy Progress",
        "housing_manager": "Corvias",
        "note": "Military housing utilities are privatized."
    },
    "camp_pendleton": {
        "name": "Camp Pendleton",
        "state": "CA",
        "cities": ["Oceanside"],
        "zip_codes": ["92055", "92058"],
        "electric": "San Diego Gas & Electric",
        "housing_manager": "Lincoln Military Housing",
        "note": "Marine Corps base"
    },
    "fort_campbell": {
        "name": "Fort Campbell",
        "state": "KY",
        "cities": ["Clarksville", "Hopkinsville"],
        "zip_codes": ["42223"],
        "electric": "Pennyrile Electric",
        "housing_manager": "Lendlease",
        "note": "Straddles KY/TN border"
    },
    "jblm": {
        "name": "Joint Base Lewis-McChord",
        "state": "WA",
        "cities": ["Tacoma", "Lakewood"],
        "zip_codes": ["98433", "98438", "98439"],
        "electric": "Tacoma Public Utilities",
        "housing_manager": "Lincoln Military Housing",
        "note": "Army and Air Force joint base"
    },
    "fort_benning": {
        "name": "Fort Moore (formerly Fort Benning)",
        "state": "GA",
        "cities": ["Columbus"],
        "zip_codes": ["31905"],
        "electric": "Georgia Power",
        "housing_manager": "Balfour Beatty",
        "note": "Infantry training center"
    },
    "nellis_afb": {
        "name": "Nellis Air Force Base",
        "state": "NV",
        "cities": ["Las Vegas"],
        "zip_codes": ["89191"],
        "electric": "NV Energy",
        "housing_manager": "Hunt Military Communities",
        "note": "Air Force base"
    },
    "luke_afb": {
        "name": "Luke Air Force Base",
        "state": "AZ",
        "cities": ["Glendale", "Litchfield Park"],
        "zip_codes": ["85309"],
        "electric": "Arizona Public Service",
        "housing_manager": "Hunt Military Communities",
        "note": "Fighter pilot training"
    },
    "peterson_sfb": {
        "name": "Peterson Space Force Base",
        "state": "CO",
        "cities": ["Colorado Springs"],
        "zip_codes": ["80914"],
        "electric": "Colorado Springs Utilities",
        "housing_manager": "Balfour Beatty",
        "note": "Space Force base"
    }
}


def check_military_installation(zip_code: str = None, city: str = None, state: str = None) -> Dict:
    """
    Check if address is on or near a military installation.
    """
    if not zip_code and not city:
        return {"military_installation": False}
    
    for base_key, base_info in MILITARY_INSTALLATIONS.items():
        # Check by ZIP code
        if zip_code and zip_code in base_info.get("zip_codes", []):
            return {
                "military_installation": True,
                "possible_base": True,
                "base_name": base_info["name"],
                "base_key": base_key,
                "electric": base_info.get("electric"),
                "housing_manager": base_info.get("housing_manager"),
                "note": base_info.get("note"),
                "special_handling": True
            }
        
        # Check by city
        if city and state:
            city_upper = city.upper()
            base_cities = [c.upper() for c in base_info.get("cities", [])]
            if city_upper in base_cities and state.upper() == base_info.get("state", "").upper():
                return {
                    "military_installation": False,
                    "near_military_base": True,
                    "nearby_base": base_info["name"],
                    "note": f"Near {base_info['name']}. If on-base housing, contact housing office."
                }
    
    return {"military_installation": False}


def get_special_area_info(
    lat: float = None,
    lon: float = None,
    zip_code: str = None,
    city: str = None,
    state: str = None
) -> Dict:
    """
    Comprehensive check for special areas that affect utility lookups.
    """
    result = {
        "special_areas": [],
        "adjustments": [],
        "notes": []
    }
    
    # Check tribal land (requires coordinates)
    if lat and lon:
        tribal = check_tribal_land(lat, lon)
        if tribal.get("tribal_land"):
            result["special_areas"].append("tribal_land")
            result["tribal_info"] = tribal
            result["adjustments"].append({
                "type": "confidence",
                "value": tribal.get("confidence_adjustment", -20),
                "reason": "Tribal land - utility arrangements may differ"
            })
            result["notes"].append(tribal.get("note"))
    
    # Check incorporated status (requires coordinates)
    if lat and lon:
        incorporated = check_incorporated_status(lat, lon)
        if incorporated.get("incorporated") is False:
            result["special_areas"].append("unincorporated")
            result["incorporated_info"] = incorporated
            result["notes"].append(incorporated.get("note"))
    
    # Check military installation
    military = check_military_installation(zip_code, city, state)
    if military.get("military_installation") or military.get("near_military_base"):
        result["special_areas"].append("military")
        result["military_info"] = military
        if military.get("note"):
            result["notes"].append(military.get("note"))
    
    # Set overall special handling flag
    result["requires_special_handling"] = len(result["special_areas"]) > 0
    
    return result


if __name__ == "__main__":
    print("Special Areas Detection Tests:")
    print("=" * 60)
    
    # Test tribal land check (Navajo Nation area)
    print("\n1. Testing Tribal Land Detection (Window Rock, AZ - Navajo Nation):")
    tribal = check_tribal_land(35.6742, -109.0526)
    print(f"   Tribal land: {tribal.get('tribal_land')}")
    if tribal.get('tribal_areas'):
        print(f"   Area: {tribal['tribal_areas'][0]['name']}")
    
    # Test incorporated status
    print("\n2. Testing Incorporated Status (Austin, TX):")
    inc = check_incorporated_status(30.2672, -97.7431)
    print(f"   Incorporated: {inc.get('incorporated')}")
    print(f"   City: {inc.get('city')}")
    
    # Test military installation
    print("\n3. Testing Military Installation (Fort Cavazos ZIP):")
    mil = check_military_installation(zip_code="76544")
    print(f"   Military: {mil.get('military_installation')}")
    if mil.get('base_name'):
        print(f"   Base: {mil['base_name']}")
