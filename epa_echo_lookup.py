#!/usr/bin/env python3
"""
EPA ECHO API lookup for wastewater/sewer facilities.

Uses the EPA ECHO (Enforcement and Compliance History Online) API
to find wastewater treatment facilities by location.

API Docs: https://echo.epa.gov/tools/web-services/facility-search-water
"""

import requests
from typing import Optional, Dict, List
import time

# EPA ECHO API base URL
ECHO_API_BASE = "https://echodata.epa.gov/echo"

# Cache to avoid repeated API calls
_echo_cache = {}


def lookup_wastewater_facilities(
    city: str = None,
    state: str = None,
    zip_code: str = None,
    lat: float = None,
    lon: float = None,
    radius_miles: float = 10
) -> List[Dict]:
    """
    Look up wastewater/sewer facilities from EPA ECHO.
    
    Args:
        city: City name
        state: State abbreviation (e.g., 'TX')
        zip_code: ZIP code
        lat: Latitude for radius search
        lon: Longitude for radius search
        radius_miles: Search radius in miles (default 10)
    
    Returns:
        List of wastewater facility dicts with name, address, phone, etc.
    """
    cache_key = f"{city}|{state}|{zip_code}|{lat}|{lon}"
    if cache_key in _echo_cache:
        return _echo_cache[cache_key]
    
    try:
        # Build query parameters
        params = {
            "output": "JSON",
            "p_act": "Y",  # Active facilities only
            "p_maj": "Y",  # Major facilities (larger treatment plants)
            "responseset": "10"  # Limit results
        }
        
        # Location filters
        if state:
            params["p_st"] = state
        if city:
            params["p_city"] = city
        if zip_code:
            params["p_zip"] = zip_code
        
        # Radius search if coordinates provided
        if lat and lon:
            params["p_lat"] = lat
            params["p_long"] = lon
            params["p_radius"] = radius_miles
        
        # Call the CWA (Clean Water Act) facility search
        url = f"{ECHO_API_BASE}/cwa_rest_services.get_facilities"
        
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        
        facilities = []
        
        # Parse results
        results = data.get("Results", {})
        facility_list = results.get("Facilities", [])
        
        for fac in facility_list:
            # Filter to POTWs (Publicly Owned Treatment Works) - these are sewer utilities
            sic_codes = fac.get("SICCodes", "") or ""
            naics_codes = fac.get("NAICSCodes", "") or ""
            fac_type = fac.get("CWPFacilityTypeIndicator", "") or ""
            
            # POTW indicator or wastewater SIC/NAICS codes
            is_potw = (
                "POTW" in fac_type.upper() or
                "4952" in sic_codes or  # Sewerage systems
                "221320" in naics_codes  # Sewage treatment facilities
            )
            
            if not is_potw:
                continue
            
            facility = {
                "name": fac.get("FacName", "").strip(),
                "id": fac.get("SourceID") or fac.get("RegistryID"),
                "address": fac.get("FacStreet", ""),
                "city": fac.get("FacCity", ""),
                "state": fac.get("FacState", ""),
                "zip": fac.get("FacZip", ""),
                "phone": None,  # ECHO doesn't provide phone
                "website": None,
                "permit_id": fac.get("CWPPermitStatusDesc", ""),
                "facility_type": fac_type,
                "_source": "epa_echo",
                "_confidence": "high"
            }
            
            # Try to get more details
            if facility["name"]:
                facilities.append(facility)
        
        # Also try minor facilities if no major ones found
        if not facilities:
            params["p_maj"] = "N"
            response = requests.get(url, params=params, timeout=15)
            if response.status_code == 200:
                data = response.json()
                results = data.get("Results", {})
                facility_list = results.get("Facilities", [])
                
                for fac in facility_list:
                    fac_type = fac.get("CWPFacilityTypeIndicator", "") or ""
                    if "POTW" in fac_type.upper():
                        facility = {
                            "name": fac.get("FacName", "").strip(),
                            "id": fac.get("SourceID") or fac.get("RegistryID"),
                            "address": fac.get("FacStreet", ""),
                            "city": fac.get("FacCity", ""),
                            "state": fac.get("FacState", ""),
                            "zip": fac.get("FacZip", ""),
                            "phone": None,
                            "website": None,
                            "facility_type": fac_type,
                            "_source": "epa_echo",
                            "_confidence": "medium"
                        }
                        if facility["name"]:
                            facilities.append(facility)
        
        _echo_cache[cache_key] = facilities
        return facilities
        
    except requests.RequestException as e:
        print(f"[EPA ECHO] API error: {e}")
        return []
    except Exception as e:
        print(f"[EPA ECHO] Error: {e}")
        return []


def get_sewer_provider(city: str, state: str, zip_code: str = None) -> Optional[Dict]:
    """
    Get the primary sewer/wastewater provider for a location.
    
    Returns the most likely sewer utility serving the area.
    """
    facilities = lookup_wastewater_facilities(
        city=city,
        state=state,
        zip_code=zip_code
    )
    
    if not facilities:
        return None
    
    # Prefer facilities that match the city name
    city_lower = city.lower() if city else ""
    
    for fac in facilities:
        fac_name = fac.get("name", "").lower()
        fac_city = fac.get("city", "").lower()
        
        # Exact city match in name or location
        if city_lower in fac_name or fac_city == city_lower:
            return fac
    
    # Return first result as fallback
    return facilities[0] if facilities else None


if __name__ == "__main__":
    # Test
    print("Testing EPA ECHO sewer lookup...")
    
    tests = [
        ("Austin", "TX", "78701"),
        ("Columbus", "OH", "43215"),
        ("East Hanover", "NJ", "07936"),
    ]
    
    for city, state, zip_code in tests:
        print(f"\n{city}, {state} {zip_code}:")
        result = get_sewer_provider(city, state, zip_code)
        if result:
            print(f"  Sewer: {result['name']}")
            print(f"  Address: {result.get('address')}, {result.get('city')}, {result.get('state')}")
        else:
            print("  No sewer facility found")
