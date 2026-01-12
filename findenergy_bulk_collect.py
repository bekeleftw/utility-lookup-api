#!/usr/bin/env python3
"""
Bulk data collection for FindEnergy city-to-provider mappings.

Since FindEnergy.com blocks direct scraping (Cloudflare), this script:
1. Uses SERP queries with site:findenergy.com filter
2. Parses results to extract provider names
3. Caches results for future lookups

Usage:
    python findenergy_bulk_collect.py --state TX --cities "Austin,Houston,Dallas"
    python findenergy_bulk_collect.py --state CA --top-cities 20
    python findenergy_bulk_collect.py --all-states --top-cities 10
"""

import argparse
import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

from findenergy_lookup import (
    lookup_findenergy,
    _load_cache,
    _save_cache,
    CITY_CACHE_FILE,
    _get_cache_key
)

# Top cities by state (population-based)
TOP_CITIES_BY_STATE = {
    "AL": ["Birmingham", "Montgomery", "Huntsville", "Mobile", "Tuscaloosa"],
    "AK": ["Anchorage", "Fairbanks", "Juneau", "Sitka", "Ketchikan"],
    "AZ": ["Phoenix", "Tucson", "Mesa", "Chandler", "Scottsdale", "Glendale", "Gilbert", "Tempe", "Peoria", "Surprise"],
    "AR": ["Little Rock", "Fort Smith", "Fayetteville", "Springdale", "Jonesboro"],
    "CA": ["Los Angeles", "San Diego", "San Jose", "San Francisco", "Fresno", "Sacramento", "Long Beach", "Oakland", "Bakersfield", "Anaheim", "Santa Ana", "Riverside", "Stockton", "Irvine", "Chula Vista"],
    "CO": ["Denver", "Colorado Springs", "Aurora", "Fort Collins", "Lakewood", "Thornton", "Arvada", "Westminster", "Pueblo", "Boulder"],
    "CT": ["Bridgeport", "New Haven", "Hartford", "Stamford", "Waterbury"],
    "DE": ["Wilmington", "Dover", "Newark", "Middletown", "Smyrna"],
    "FL": ["Jacksonville", "Miami", "Tampa", "Orlando", "St. Petersburg", "Hialeah", "Tallahassee", "Fort Lauderdale", "Port St. Lucie", "Cape Coral", "Pembroke Pines", "Hollywood", "Gainesville", "Coral Springs"],
    "GA": ["Atlanta", "Augusta", "Columbus", "Macon", "Savannah", "Athens", "Sandy Springs", "Roswell", "Johns Creek", "Albany"],
    "HI": ["Honolulu", "Pearl City", "Hilo", "Kailua", "Waipahu"],
    "ID": ["Boise", "Meridian", "Nampa", "Idaho Falls", "Pocatello"],
    "IL": ["Chicago", "Aurora", "Rockford", "Joliet", "Naperville", "Springfield", "Peoria", "Elgin", "Waukegan", "Champaign"],
    "IN": ["Indianapolis", "Fort Wayne", "Evansville", "South Bend", "Carmel", "Bloomington", "Fishers", "Hammond", "Gary", "Muncie"],
    "IA": ["Des Moines", "Cedar Rapids", "Davenport", "Sioux City", "Iowa City"],
    "KS": ["Wichita", "Overland Park", "Kansas City", "Olathe", "Topeka"],
    "KY": ["Louisville", "Lexington", "Bowling Green", "Owensboro", "Covington"],
    "LA": ["New Orleans", "Baton Rouge", "Shreveport", "Lafayette", "Lake Charles"],
    "ME": ["Portland", "Lewiston", "Bangor", "South Portland", "Auburn"],
    "MD": ["Baltimore", "Frederick", "Rockville", "Gaithersburg", "Bowie"],
    "MA": ["Boston", "Worcester", "Springfield", "Cambridge", "Lowell", "Brockton", "New Bedford", "Quincy", "Lynn", "Fall River"],
    "MI": ["Detroit", "Grand Rapids", "Warren", "Sterling Heights", "Ann Arbor", "Lansing", "Flint", "Dearborn", "Livonia", "Troy"],
    "MN": ["Minneapolis", "St. Paul", "Rochester", "Duluth", "Bloomington"],
    "MS": ["Jackson", "Gulfport", "Southaven", "Hattiesburg", "Biloxi"],
    "MO": ["Kansas City", "St. Louis", "Springfield", "Columbia", "Independence"],
    "MT": ["Billings", "Missoula", "Great Falls", "Bozeman", "Butte"],
    "NE": ["Omaha", "Lincoln", "Bellevue", "Grand Island", "Kearney"],
    "NV": ["Las Vegas", "Henderson", "Reno", "North Las Vegas", "Sparks"],
    "NH": ["Manchester", "Nashua", "Concord", "Derry", "Dover"],
    "NJ": ["Newark", "Jersey City", "Paterson", "Elizabeth", "Edison", "Woodbridge", "Lakewood", "Toms River", "Hamilton", "Trenton"],
    "NM": ["Albuquerque", "Las Cruces", "Rio Rancho", "Santa Fe", "Roswell"],
    "NY": ["New York", "Buffalo", "Rochester", "Yonkers", "Syracuse", "Albany", "New Rochelle", "Mount Vernon", "Schenectady", "Utica"],
    "NC": ["Charlotte", "Raleigh", "Greensboro", "Durham", "Winston-Salem", "Fayetteville", "Cary", "Wilmington", "High Point", "Concord"],
    "ND": ["Fargo", "Bismarck", "Grand Forks", "Minot", "West Fargo"],
    "OH": ["Columbus", "Cleveland", "Cincinnati", "Toledo", "Akron", "Dayton", "Parma", "Canton", "Youngstown", "Lorain"],
    "OK": ["Oklahoma City", "Tulsa", "Norman", "Broken Arrow", "Edmond"],
    "OR": ["Portland", "Salem", "Eugene", "Gresham", "Hillsboro", "Beaverton", "Bend", "Medford", "Springfield", "Corvallis"],
    "PA": ["Philadelphia", "Pittsburgh", "Allentown", "Reading", "Scranton", "Bethlehem", "Lancaster", "Harrisburg", "Altoona", "Erie"],
    "RI": ["Providence", "Warwick", "Cranston", "Pawtucket", "East Providence"],
    "SC": ["Charleston", "Columbia", "North Charleston", "Mount Pleasant", "Rock Hill"],
    "SD": ["Sioux Falls", "Rapid City", "Aberdeen", "Brookings", "Watertown"],
    "TN": ["Nashville", "Memphis", "Knoxville", "Chattanooga", "Clarksville", "Murfreesboro", "Franklin", "Jackson", "Johnson City", "Bartlett"],
    "TX": ["Houston", "San Antonio", "Dallas", "Austin", "Fort Worth", "El Paso", "Arlington", "Corpus Christi", "Plano", "Laredo", "Lubbock", "Garland", "Irving", "Amarillo", "Grand Prairie", "McKinney", "Frisco", "Brownsville", "Pasadena", "Mesquite"],
    "UT": ["Salt Lake City", "West Valley City", "Provo", "West Jordan", "Orem"],
    "VT": ["Burlington", "South Burlington", "Rutland", "Barre", "Montpelier"],
    "VA": ["Virginia Beach", "Norfolk", "Chesapeake", "Richmond", "Newport News", "Alexandria", "Hampton", "Roanoke", "Portsmouth", "Suffolk"],
    "WA": ["Seattle", "Spokane", "Tacoma", "Vancouver", "Bellevue", "Kent", "Everett", "Renton", "Federal Way", "Spokane Valley"],
    "WV": ["Charleston", "Huntington", "Morgantown", "Parkersburg", "Wheeling"],
    "WI": ["Milwaukee", "Madison", "Green Bay", "Kenosha", "Racine", "Appleton", "Waukesha", "Eau Claire", "Oshkosh", "Janesville"],
    "WY": ["Cheyenne", "Casper", "Laramie", "Gillette", "Rock Springs"],
    "DC": ["Washington"]
}


def collect_city_data(
    city: str,
    state: str,
    utility_types: List[str] = ["electric", "gas"],
    force_refresh: bool = False
) -> Dict:
    """
    Collect FindEnergy data for a city.
    
    Args:
        city: City name
        state: State abbreviation
        utility_types: List of utility types to collect
        force_refresh: If True, refresh even if cached
        
    Returns:
        Dict with results for each utility type
    """
    results = {}
    cache = _load_cache(CITY_CACHE_FILE)
    
    for utility_type in utility_types:
        cache_key = _get_cache_key(city, state, utility_type)
        
        # Check if already cached
        if not force_refresh and cache_key in cache:
            print(f"  {city}, {state} ({utility_type}): Already cached")
            results[utility_type] = cache[cache_key]
            continue
        
        print(f"  {city}, {state} ({utility_type}): Querying...")
        
        # Query FindEnergy
        result = lookup_findenergy(
            city=city,
            state=state,
            utility_type=utility_type
        )
        
        if result and result.get("providers"):
            results[utility_type] = result
            # Save to cache
            cache[cache_key] = result
            _save_cache(CITY_CACHE_FILE, cache)
            print(f"    Found: {[p.get('name') for p in result.get('providers', [])[:3]]}")
        else:
            print(f"    No results")
        
        # Rate limit
        time.sleep(2)
    
    return results


def collect_state_data(
    state: str,
    num_cities: int = 10,
    utility_types: List[str] = ["electric", "gas"],
    force_refresh: bool = False
) -> Dict:
    """
    Collect FindEnergy data for top cities in a state.
    """
    cities = TOP_CITIES_BY_STATE.get(state.upper(), [])[:num_cities]
    
    if not cities:
        print(f"No cities found for state: {state}")
        return {}
    
    print(f"\nCollecting data for {state} ({len(cities)} cities)...")
    
    results = {}
    for city in cities:
        city_results = collect_city_data(city, state, utility_types, force_refresh)
        if city_results:
            results[city] = city_results
    
    return results


def collect_all_states(
    num_cities_per_state: int = 5,
    utility_types: List[str] = ["electric", "gas"],
    force_refresh: bool = False
) -> Dict:
    """
    Collect FindEnergy data for top cities in all states.
    """
    all_results = {}
    
    for state in sorted(TOP_CITIES_BY_STATE.keys()):
        state_results = collect_state_data(
            state,
            num_cities_per_state,
            utility_types,
            force_refresh
        )
        if state_results:
            all_results[state] = state_results
    
    return all_results


def generate_cache_stats() -> Dict:
    """Generate statistics about the current cache."""
    cache = _load_cache(CITY_CACHE_FILE)
    
    stats = {
        "total_entries": len(cache),
        "by_state": {},
        "by_utility_type": {"electric": 0, "gas": 0},
        "cities_covered": set()
    }
    
    for key, value in cache.items():
        if key.startswith("_"):
            continue
        
        parts = key.split(":")
        if len(parts) >= 3:
            state, city, utility_type = parts[0], parts[1], parts[2]
            
            if state not in stats["by_state"]:
                stats["by_state"][state] = {"electric": 0, "gas": 0}
            
            stats["by_state"][state][utility_type] = stats["by_state"][state].get(utility_type, 0) + 1
            stats["by_utility_type"][utility_type] += 1
            stats["cities_covered"].add(f"{city}, {state}")
    
    stats["cities_covered"] = len(stats["cities_covered"])
    
    return stats


def main():
    parser = argparse.ArgumentParser(description="Bulk collect FindEnergy data")
    parser.add_argument("--state", help="State abbreviation (e.g., TX)")
    parser.add_argument("--cities", help="Comma-separated list of cities")
    parser.add_argument("--top-cities", type=int, default=10, help="Number of top cities per state")
    parser.add_argument("--all-states", action="store_true", help="Collect for all states")
    parser.add_argument("--electric-only", action="store_true", help="Only collect electric data")
    parser.add_argument("--gas-only", action="store_true", help="Only collect gas data")
    parser.add_argument("--force-refresh", action="store_true", help="Refresh even if cached")
    parser.add_argument("--stats", action="store_true", help="Show cache statistics")
    
    args = parser.parse_args()
    
    if args.stats:
        stats = generate_cache_stats()
        print("\n=== FindEnergy Cache Statistics ===")
        print(f"Total entries: {stats['total_entries']}")
        print(f"Cities covered: {stats['cities_covered']}")
        print(f"Electric entries: {stats['by_utility_type']['electric']}")
        print(f"Gas entries: {stats['by_utility_type']['gas']}")
        print("\nBy state:")
        for state in sorted(stats['by_state'].keys()):
            data = stats['by_state'][state]
            print(f"  {state}: {data.get('electric', 0)} electric, {data.get('gas', 0)} gas")
        return
    
    # Determine utility types
    utility_types = ["electric", "gas"]
    if args.electric_only:
        utility_types = ["electric"]
    elif args.gas_only:
        utility_types = ["gas"]
    
    if args.all_states:
        collect_all_states(args.top_cities, utility_types, args.force_refresh)
    elif args.state:
        if args.cities:
            cities = [c.strip() for c in args.cities.split(",")]
            for city in cities:
                collect_city_data(city, args.state, utility_types, args.force_refresh)
        else:
            collect_state_data(args.state, args.top_cities, utility_types, args.force_refresh)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
