#!/usr/bin/env python3
"""
Deregulated electricity market handling.
In deregulated states, customers choose their retail provider but the 
transmission/distribution utility (TDU) is fixed by location.
"""

from typing import Dict, Optional, List


# Deregulated electricity states and their market structures
DEREGULATED_STATES = {
    "TX": {
        "name": "Texas",
        "market_type": "retail_choice",
        "grid_operator": "ERCOT",
        "choice_website": "https://powertochoose.org",
        "tdu_term": "TDU",  # Transmission/Distribution Utility
        "rep_term": "REP",  # Retail Electric Provider
        "notes": "Most of Texas is deregulated. Municipal utilities and co-ops are exempt."
    },
    "PA": {
        "name": "Pennsylvania",
        "market_type": "retail_choice",
        "choice_website": "https://www.papowerswitch.com",
        "tdu_term": "EDC",  # Electric Distribution Company
        "rep_term": "EGS",  # Electric Generation Supplier
        "notes": "Full retail choice since 2010."
    },
    "OH": {
        "name": "Ohio",
        "market_type": "retail_choice",
        "choice_website": "https://energychoice.ohio.gov",
        "tdu_term": "EDU",  # Electric Distribution Utility
        "rep_term": "CRES",  # Competitive Retail Electric Service
        "notes": "Full retail choice available."
    },
    "IL": {
        "name": "Illinois",
        "market_type": "retail_choice",
        "choice_website": "https://www.pluginillinois.org",
        "tdu_term": "Utility",
        "rep_term": "ARES",  # Alternative Retail Electric Supplier
        "notes": "Retail choice available but many stay with default utility."
    },
    "NY": {
        "name": "New York",
        "market_type": "retail_choice",
        "choice_website": "https://www.askpsc.com/",
        "tdu_term": "Utility",
        "rep_term": "ESCO",  # Energy Service Company
        "notes": "Retail choice available statewide."
    },
    "NJ": {
        "name": "New Jersey",
        "market_type": "retail_choice",
        "choice_website": "https://nj.gov/bpu/commercial/shopping.html",
        "tdu_term": "EDC",
        "rep_term": "TPS",  # Third Party Supplier
        "notes": "Retail choice since 1999."
    },
    "MD": {
        "name": "Maryland",
        "market_type": "retail_choice",
        "choice_website": "https://www.mdelectricchoice.com",
        "tdu_term": "Utility",
        "rep_term": "Supplier",
        "notes": "Retail choice available."
    },
    "CT": {
        "name": "Connecticut",
        "market_type": "retail_choice",
        "choice_website": "https://energizect.com",
        "tdu_term": "EDC",
        "rep_term": "Supplier",
        "notes": "Retail choice available."
    },
    "MA": {
        "name": "Massachusetts",
        "market_type": "retail_choice",
        "choice_website": "https://www.mass.gov/competitive-electric-supply",
        "tdu_term": "Utility",
        "rep_term": "Competitive Supplier",
        "notes": "Retail choice available."
    },
    "ME": {
        "name": "Maine",
        "market_type": "retail_choice",
        "choice_website": "https://www.maine.gov/mpuc/electricity",
        "tdu_term": "T&D Utility",
        "rep_term": "Competitive Provider",
        "notes": "Retail choice available."
    },
    "NH": {
        "name": "New Hampshire",
        "market_type": "retail_choice",
        "choice_website": "https://www.puc.nh.gov/consumer/energysuppliers.htm",
        "tdu_term": "Utility",
        "rep_term": "Competitive Supplier",
        "notes": "Retail choice available."
    },
    "RI": {
        "name": "Rhode Island",
        "market_type": "retail_choice",
        "choice_website": "http://www.ripuc.ri.gov/utilityinfo/electric.html",
        "tdu_term": "Utility",
        "rep_term": "Competitive Supplier",
        "notes": "Retail choice available."
    },
    "DE": {
        "name": "Delaware",
        "market_type": "retail_choice",
        "choice_website": "https://depsc.delaware.gov",
        "tdu_term": "Utility",
        "rep_term": "Supplier",
        "notes": "Retail choice available."
    },
    "DC": {
        "name": "District of Columbia",
        "market_type": "retail_choice",
        "choice_website": "https://dcpsc.org",
        "tdu_term": "Utility",
        "rep_term": "Supplier",
        "notes": "Retail choice available."
    },
}

# Texas TDUs (Transmission/Distribution Utilities)
TEXAS_TDUS = {
    "oncor": {
        "name": "Oncor Electric Delivery",
        "service_area": "North/Central Texas (Dallas, Fort Worth, Waco, Midland)",
        "phone": "1-888-313-4747",
        "website": "https://www.oncor.com",
        "zip_prefixes": ["750", "751", "752", "753", "754", "755", "756", "757", "760", "761", "762", "763", "764", "765", "766", "767", "768", "769", "790", "791", "793", "794", "795", "796", "797", "798", "799"]
    },
    "centerpoint": {
        "name": "CenterPoint Energy",
        "service_area": "Houston metro area",
        "phone": "713-207-2222",
        "website": "https://www.centerpointenergy.com",
        "zip_prefixes": ["770", "771", "772", "773", "774", "775", "776", "777", "778", "779"]
    },
    "aep_texas_north": {
        "name": "AEP Texas North",
        "service_area": "West Texas (Abilene area)",
        "phone": "1-866-223-8508",
        "website": "https://www.aeptexas.com",
        "zip_prefixes": ["795", "796"]
    },
    "aep_texas_central": {
        "name": "AEP Texas Central",
        "service_area": "South Texas (Corpus Christi, McAllen, Laredo)",
        "phone": "1-877-373-4858",
        "website": "https://www.aeptexas.com",
        "zip_prefixes": ["780", "781", "782", "783", "784", "785", "786", "787", "788", "789"]
    },
    "tnmp": {
        "name": "Texas-New Mexico Power (TNMP)",
        "service_area": "Various areas across Texas",
        "phone": "1-888-866-7456",
        "website": "https://www.tnmp.com",
        "zip_prefixes": []  # Scattered service areas
    },
    "lp_and_l": {
        "name": "Lubbock Power & Light",
        "service_area": "Lubbock",
        "phone": "806-775-2509",
        "website": "https://www.lpandl.com",
        "zip_prefixes": ["793", "794"]
    }
}

# Ohio EDUs (Electric Distribution Utilities)
OHIO_EDUS = {
    "aep_ohio": {
        "name": "AEP Ohio",
        "service_area": "Central and Southern Ohio",
        "phone": "1-800-672-2231",
        "website": "https://www.aepohio.com"
    },
    "duke_ohio": {
        "name": "Duke Energy Ohio",
        "service_area": "Southwest Ohio (Cincinnati area)",
        "phone": "1-800-544-6900",
        "website": "https://www.duke-energy.com"
    },
    "firstenergy_ohio": {
        "name": "FirstEnergy Ohio (Ohio Edison, CEI, Toledo Edison)",
        "service_area": "Northern Ohio",
        "phone": "1-800-633-4766",
        "website": "https://www.firstenergycorp.com"
    },
    "dayton_power": {
        "name": "Dayton Power & Light (AES Ohio)",
        "service_area": "Dayton area",
        "phone": "1-800-433-8500",
        "website": "https://www.aes-ohio.com"
    }
}

# Pennsylvania EDCs (Electric Distribution Companies)
PENNSYLVANIA_EDCS = {
    "peco": {
        "name": "PECO Energy",
        "service_area": "Philadelphia and surrounding counties",
        "phone": "1-800-494-4000",
        "website": "https://www.peco.com"
    },
    "ppl": {
        "name": "PPL Electric Utilities",
        "service_area": "Central and Eastern Pennsylvania",
        "phone": "1-800-342-5775",
        "website": "https://www.pplelectric.com"
    },
    "duquesne": {
        "name": "Duquesne Light",
        "service_area": "Pittsburgh area",
        "phone": "412-393-7100",
        "website": "https://www.duquesnelight.com"
    },
    "penelec": {
        "name": "Penelec (FirstEnergy)",
        "service_area": "Northern and Western Pennsylvania",
        "phone": "1-800-545-7741",
        "website": "https://www.firstenergycorp.com"
    },
    "met_ed": {
        "name": "Met-Ed (FirstEnergy)",
        "service_area": "Eastern Pennsylvania",
        "phone": "1-800-545-7741",
        "website": "https://www.firstenergycorp.com"
    },
    "west_penn": {
        "name": "West Penn Power (FirstEnergy)",
        "service_area": "Southwestern Pennsylvania",
        "phone": "1-800-545-7741",
        "website": "https://www.firstenergycorp.com"
    }
}


def is_deregulated_state(state: str) -> bool:
    """Check if a state has deregulated electricity market."""
    return state.upper() in DEREGULATED_STATES


def get_deregulated_market_info(state: str) -> Optional[Dict]:
    """Get deregulated market information for a state."""
    state = state.upper()
    if state not in DEREGULATED_STATES:
        return None
    return DEREGULATED_STATES[state]


def lookup_texas_tdu(zip_code: str) -> Optional[Dict]:
    """
    Look up the TDU for a Texas ZIP code.
    """
    if not zip_code or len(zip_code) < 3:
        return None
    
    prefix = zip_code[:3]
    
    for tdu_key, tdu_info in TEXAS_TDUS.items():
        if prefix in tdu_info.get("zip_prefixes", []):
            return {
                "tdu_key": tdu_key,
                "name": tdu_info["name"],
                "service_area": tdu_info["service_area"],
                "phone": tdu_info["phone"],
                "website": tdu_info["website"]
            }
    
    # Default to Oncor for unknown ZIP prefixes in Texas
    return {
        "tdu_key": "unknown",
        "name": "Unknown TDU",
        "note": "Could not determine TDU from ZIP code. Check powertochoose.org"
    }


def get_deregulated_electric_response(
    state: str,
    zip_code: str = None,
    tdu_name: str = None
) -> Dict:
    """
    Build a response for deregulated electricity markets.
    Returns both the infrastructure owner (TDU/EDC) and retail choice info.
    """
    state = state.upper()
    
    if state not in DEREGULATED_STATES:
        return {
            "deregulated": False,
            "note": "This state does not have retail electricity choice."
        }
    
    market_info = DEREGULATED_STATES[state]
    
    result = {
        "deregulated": True,
        "state": state,
        "market_type": market_info["market_type"],
        "choice_website": market_info["choice_website"],
        "notes": market_info["notes"]
    }
    
    # Add TDU/EDC information
    tdu_term = market_info["tdu_term"]
    rep_term = market_info["rep_term"]
    
    # State-specific TDU lookup
    if state == "TX" and zip_code:
        tdu = lookup_texas_tdu(zip_code)
        if tdu:
            result["infrastructure_provider"] = {
                "term": tdu_term,
                "name": tdu.get("name"),
                "role": "Owns and maintains power lines, meters, and responds to outages",
                "phone": tdu.get("phone"),
                "website": tdu.get("website"),
                "service_area": tdu.get("service_area")
            }
    elif tdu_name:
        result["infrastructure_provider"] = {
            "term": tdu_term,
            "name": tdu_name,
            "role": "Owns and maintains power lines, meters, and responds to outages"
        }
    
    # Add retail provider information
    result["retail_provider"] = {
        "term": rep_term,
        "name": None,  # Customer chooses
        "role": "Sells electricity to customer. Customer can choose their provider.",
        "how_to_choose": f"Visit {market_info['choice_website']} to compare providers and rates"
    }
    
    return result


def adjust_electric_result_for_deregulation(result: Dict, state: str, zip_code: str = None) -> Dict:
    """
    Adjust an electric utility result to account for deregulated markets.
    """
    if not is_deregulated_state(state):
        return result
    
    market_info = DEREGULATED_STATES[state.upper()]
    
    # The utility we found is likely the TDU/EDC, not the retail provider
    original_name = result.get("NAME") or result.get("name")
    
    result["_deregulated_market"] = True
    result["_market_info"] = {
        "state": state,
        "choice_website": market_info["choice_website"],
        "tdu_term": market_info["tdu_term"],
        "rep_term": market_info["rep_term"]
    }
    
    # Clarify what this utility is
    result["_role"] = f"{market_info['tdu_term']} (infrastructure owner)"
    result["_note"] = f"In {market_info['name']}, customers choose their {market_info['rep_term']}. {original_name} owns the power lines and meters."
    
    # Add retail choice info
    result["_retail_choice"] = {
        "available": True,
        "website": market_info["choice_website"],
        "note": f"Visit {market_info['choice_website']} to choose your electricity provider"
    }
    
    return result


if __name__ == "__main__":
    print("Deregulated Electricity Markets:")
    print("=" * 60)
    
    for state, info in DEREGULATED_STATES.items():
        print(f"\n{state} - {info['name']}")
        print(f"  Choice website: {info['choice_website']}")
        print(f"  TDU term: {info['tdu_term']}, REP term: {info['rep_term']}")
    
    print("\n" + "=" * 60)
    print("\nTexas TDU Lookup Examples:")
    
    test_zips = ["75201", "77001", "78701", "79401"]
    for zip_code in test_zips:
        tdu = lookup_texas_tdu(zip_code)
        print(f"  {zip_code}: {tdu.get('name') if tdu else 'Unknown'}")
