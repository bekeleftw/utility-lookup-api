#!/usr/bin/env python3
"""
Multi-source geocoding with consensus for improved accuracy.
Falls back through multiple geocoders and uses consensus when available.
"""

import os
import requests
import math
from typing import Dict, Optional, List, Tuple
from urllib.parse import quote


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points in meters."""
    R = 6371000  # Earth's radius in meters
    
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    
    a = math.sin(delta_phi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    
    return R * c


def geocode_census(address: str) -> Optional[Dict]:
    """
    Geocode using US Census Bureau Geocoder (free, no API key).
    """
    try:
        url = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
        params = {
            "address": address,
            "benchmark": "Public_AR_Current",
            "format": "json"
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        matches = data.get("result", {}).get("addressMatches", [])
        if not matches:
            return None
        
        match = matches[0]
        coords = match.get("coordinates", {})
        
        return {
            "lat": coords.get("y"),
            "lon": coords.get("x"),
            "formatted_address": match.get("matchedAddress"),
            "source": "census",
            "confidence": "high" if match.get("tigerLine") else "medium"
        }
    except Exception as e:
        return None


def geocode_nominatim(address: str) -> Optional[Dict]:
    """
    Geocode using OpenStreetMap Nominatim (free, rate limited).
    """
    try:
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": address,
            "format": "json",
            "limit": 1,
            "countrycodes": "us"
        }
        headers = {
            "User-Agent": "UtilityLookup/1.0"
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if not data:
            return None
        
        result = data[0]
        
        return {
            "lat": float(result.get("lat")),
            "lon": float(result.get("lon")),
            "formatted_address": result.get("display_name"),
            "source": "nominatim",
            "confidence": "medium"
        }
    except Exception as e:
        return None


def geocode_google(address: str) -> Optional[Dict]:
    """
    Geocode using Google Maps API (requires API key, ~$5/1000 requests).
    """
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return None
    
    try:
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {
            "address": address,
            "key": api_key
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get("status") != "OK" or not data.get("results"):
            return None
        
        result = data["results"][0]
        location = result.get("geometry", {}).get("location", {})
        
        return {
            "lat": location.get("lat"),
            "lon": location.get("lng"),
            "formatted_address": result.get("formatted_address"),
            "source": "google",
            "confidence": "high",
            "place_id": result.get("place_id")
        }
    except Exception as e:
        return None


def geocode_smarty(address: str) -> Optional[Dict]:
    """
    Geocode using Smarty (SmartyStreets) API (~$0.01/lookup, CASS certified).
    """
    auth_id = os.environ.get("SMARTY_AUTH_ID")
    auth_token = os.environ.get("SMARTY_AUTH_TOKEN")
    
    if not auth_id or not auth_token:
        return None
    
    try:
        url = "https://us-street.api.smartystreets.com/street-address"
        params = {
            "auth-id": auth_id,
            "auth-token": auth_token,
            "street": address,
            "candidates": 1
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if not data:
            return None
        
        result = data[0]
        metadata = result.get("metadata", {})
        
        return {
            "lat": metadata.get("latitude"),
            "lon": metadata.get("longitude"),
            "formatted_address": f"{result.get('delivery_line_1')}, {result.get('last_line')}",
            "source": "smarty",
            "confidence": "high",
            "dpv_match": result.get("analysis", {}).get("dpv_match_code"),
            "precision": metadata.get("precision")
        }
    except Exception as e:
        return None


def geocode_consensus(address: str, require_consensus: bool = False) -> Dict:
    """
    Query multiple geocoders and use consensus for accuracy.
    
    Args:
        address: Address to geocode
        require_consensus: If True, require 2+ sources to agree
    
    Returns:
        Dict with lat, lon, confidence, and metadata
    """
    results = []
    
    # Try each geocoder
    geocoders = [
        ("census", geocode_census),
        ("google", geocode_google),
        ("smarty", geocode_smarty),
        ("nominatim", geocode_nominatim),
    ]
    
    for name, geocoder in geocoders:
        try:
            result = geocoder(address)
            if result and result.get("lat") and result.get("lon"):
                results.append(result)
        except Exception:
            continue
    
    if not results:
        return {
            "lat": None,
            "lon": None,
            "confidence": "none",
            "error": "All geocoders failed",
            "sources_tried": len(geocoders)
        }
    
    if len(results) == 1:
        result = results[0]
        result["method"] = "single_source"
        result["sources_agreed"] = 1
        return result
    
    # Calculate average position
    lat_avg = sum(r["lat"] for r in results) / len(results)
    lon_avg = sum(r["lon"] for r in results) / len(results)
    
    # Check if all results are within 100 meters of average
    distances = [
        haversine_distance(r["lat"], r["lon"], lat_avg, lon_avg)
        for r in results
    ]
    
    max_distance = max(distances)
    all_close = max_distance < 100  # 100 meters threshold
    
    if all_close:
        # Consensus reached
        return {
            "lat": lat_avg,
            "lon": lon_avg,
            "confidence": "high",
            "method": "multi_geocoder_consensus",
            "sources_agreed": len(results),
            "sources": [r["source"] for r in results],
            "max_deviation_meters": max_distance,
            "formatted_address": results[0].get("formatted_address")
        }
    else:
        # Disagreement - prefer Google if available, then Smarty, then Census
        priority_order = ["google", "smarty", "census", "nominatim"]
        
        for source in priority_order:
            for result in results:
                if result.get("source") == source:
                    result["method"] = "priority_selection"
                    result["sources_disagreed"] = True
                    result["confidence"] = "medium"
                    result["all_results"] = [
                        {"source": r["source"], "lat": r["lat"], "lon": r["lon"]}
                        for r in results
                    ]
                    return result
        
        # Fallback to first result
        result = results[0]
        result["method"] = "fallback"
        result["confidence"] = "low"
        return result


def geocode_with_fallback(address: str) -> Dict:
    """
    Simple geocoding with fallback chain (Census -> Google -> Nominatim).
    Faster than consensus but less accurate.
    """
    # Try Census first (free)
    result = geocode_census(address)
    if result:
        return result
    
    # Try Google if available
    result = geocode_google(address)
    if result:
        return result
    
    # Try Nominatim as last resort
    result = geocode_nominatim(address)
    if result:
        return result
    
    return {
        "lat": None,
        "lon": None,
        "confidence": "none",
        "error": "All geocoders failed"
    }


def extract_location_components(geocode_result: Dict) -> Dict:
    """
    Extract city, county, state, ZIP from a geocode result.
    """
    formatted = geocode_result.get("formatted_address", "")
    
    # Parse from formatted address
    components = {
        "city": None,
        "county": None,
        "state": None,
        "zip_code": None
    }
    
    # Try to extract ZIP
    import re
    zip_match = re.search(r'\b(\d{5})(?:-\d{4})?\b', formatted)
    if zip_match:
        components["zip_code"] = zip_match.group(1)
    
    # Try to extract state (2-letter code)
    state_match = re.search(r'\b([A-Z]{2})\s*\d{5}', formatted)
    if state_match:
        components["state"] = state_match.group(1)
    
    return components


if __name__ == "__main__":
    # Test geocoding
    test_addresses = [
        "1100 Congress Ave, Austin, TX 78701",
        "200 N Spring St, Los Angeles, CA 90012",
        "350 5th Ave, New York, NY 10118",
    ]
    
    print("Multi-Geocoder Tests:")
    print("=" * 60)
    
    for addr in test_addresses:
        print(f"\nAddress: {addr}")
        
        # Test consensus
        result = geocode_consensus(addr)
        print(f"  Lat: {result.get('lat')}")
        print(f"  Lon: {result.get('lon')}")
        print(f"  Method: {result.get('method')}")
        print(f"  Sources: {result.get('sources', [result.get('source')])}")
        print(f"  Confidence: {result.get('confidence')}")
