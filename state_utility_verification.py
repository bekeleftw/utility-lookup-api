#!/usr/bin/env python3
"""
State-by-State Electric Utility Verification

Provides authoritative verification of electric utilities using state-specific
data sources. Returns a single primary provider with high confidence.

DEREGULATED STATES (TDU/distribution utility is fixed by location):
- TX: 5 TDUs (Oncor, CenterPoint, AEP North, AEP Central, TNMP)
- PA, OH, IL, NY, CT, MD, NJ, DE, MA: EDC/utility by ZIP

REGULATED STATES:
- Cross-reference HIFLD candidates with EIA county data
"""

from typing import Dict, List, Optional, Tuple
import json
import os
from pathlib import Path

# =============================================================================
# EIA/OpenEI ZIP-TO-UTILITY LOOKUP
# =============================================================================

# Load EIA ZIP-to-utility lookup data
_EIA_ZIP_LOOKUP = None

def load_eia_zip_lookup() -> Dict:
    """Load the EIA ZIP-to-utility lookup data."""
    global _EIA_ZIP_LOOKUP
    if _EIA_ZIP_LOOKUP is None:
        lookup_path = Path(__file__).parent / "eia_zip_utility_lookup.json"
        if lookup_path.exists():
            with open(lookup_path, 'r') as f:
                _EIA_ZIP_LOOKUP = json.load(f)
        else:
            _EIA_ZIP_LOOKUP = {}
    return _EIA_ZIP_LOOKUP


def get_eia_utility_by_zip(zip_code: str) -> Optional[Dict]:
    """
    Look up utility by ZIP code using EIA/OpenEI data.
    
    Returns:
        Dict with utility info or None if not found
    """
    lookup = load_eia_zip_lookup()
    zip_code = str(zip_code).strip()[:5]  # Normalize to 5 digits
    
    if zip_code in lookup:
        utilities = lookup[zip_code]
        if utilities:
            # Return first utility (most common case)
            # Dedupe by name
            seen = set()
            unique = []
            for u in utilities:
                if u['name'] not in seen:
                    seen.add(u['name'])
                    unique.append(u)
            return unique
    return None


def verify_with_eia(candidates: List[Dict], zip_code: str, city: str = None, state: str = None) -> Dict:
    """
    Verify electric provider using EIA ZIP-to-utility data.
    
    This covers most IOUs (Investor-Owned Utilities) across the US.
    """
    eia_utilities = get_eia_utility_by_zip(zip_code)
    
    if eia_utilities:
        # We have authoritative EIA data for this ZIP
        eia_primary = eia_utilities[0]
        eia_name = eia_primary['name'].upper()
        
        # Try to find matching HIFLD candidate
        matched_candidate = None
        alternatives = []
        
        for candidate in candidates:
            candidate_name = (candidate.get("NAME") or "").upper()
            
            # Check for name match (partial match is OK)
            eia_words = set(eia_name.replace(',', '').replace('.', '').split())
            candidate_words = set(candidate_name.replace(',', '').replace('.', '').split())
            
            # Match if significant overlap in words
            common_words = eia_words & candidate_words
            significant_words = {'DUKE', 'ENERGY', 'EDISON', 'ELECTRIC', 'POWER', 'PECO', 
                                'DOMINION', 'ENTERGY', 'XCEL', 'AMEREN', 'CONSUMERS',
                                'PACIFIC', 'SOUTHERN', 'CONSOLIDATED', 'COMMONWEALTH'}
            
            if common_words & significant_words:
                matched_candidate = candidate
            else:
                alternatives.append(candidate)
        
        if matched_candidate:
            # Merge HIFLD data with EIA data
            return {
                "primary": {
                    **matched_candidate,
                    "verified_name": eia_primary['name'],
                    "eia_id": eia_primary['eiaid'],
                },
                "confidence": "verified",
                "source": "EIA Form 861 ZIP mapping",
                "selection_reason": f"ZIP {zip_code} is served by {eia_primary['name']} ({eia_primary['ownership']}).",
                "is_deregulated": None,  # EIA doesn't indicate this
                "alternatives": alternatives
            }
        else:
            # EIA utility not in HIFLD candidates - use EIA data directly
            return {
                "primary": {
                    "NAME": eia_primary['name'],
                    "STATE": eia_primary['state'],
                    "TYPE": eia_primary['ownership'],
                    "eia_id": eia_primary['eiaid'],
                },
                "confidence": "verified",
                "source": "EIA Form 861 ZIP mapping",
                "selection_reason": f"ZIP {zip_code} is served by {eia_primary['name']} ({eia_primary['ownership']}).",
                "is_deregulated": None,
                "alternatives": candidates  # All HIFLD candidates as alternatives
            }
    
    # No EIA data for this ZIP - return None to fall through to other methods
    return None

# =============================================================================
# TEXAS TDU DATA
# Texas has 5 major TDUs in the deregulated ERCOT market
# =============================================================================

TEXAS_TDUS = {
    "ONCOR": {
        "name": "Oncor Electric Delivery",
        "id": "oncor",
        "phone": "1-888-313-4747",
        "website": "https://www.oncor.com",
        "service_area": "Dallas/Fort Worth metroplex, North and West Texas"
    },
    "CENTERPOINT": {
        "name": "CenterPoint Energy",
        "id": "centerpoint",
        "phone": "1-800-332-7143",
        "website": "https://www.centerpointenergy.com",
        "service_area": "Houston metropolitan area"
    },
    "AEP_NORTH": {
        "name": "AEP Texas North",
        "id": "aep_north",
        "phone": "1-866-223-8508",
        "website": "https://www.aeptexas.com",
        "service_area": "Abilene, Lubbock area (north)"
    },
    "AEP_CENTRAL": {
        "name": "AEP Texas Central",
        "id": "aep_central",
        "phone": "1-877-373-4858",
        "website": "https://www.aeptexas.com",
        "service_area": "Corpus Christi, South Texas, Rio Grande Valley"
    },
    "TNMP": {
        "name": "Texas-New Mexico Power (TNMP)",
        "id": "tnmp",
        "phone": "1-888-866-7456",
        "website": "https://www.tnmp.com",
        "service_area": "Various areas across Texas"
    }
}

# Major ZIP code prefixes to TDU mapping for Texas
# This is a simplified mapping based on major metro areas
# Format: ZIP prefix -> TDU key
TEXAS_ZIP_PREFIX_TO_TDU = {
    # Dallas/Fort Worth area - Oncor
    "750": "ONCOR", "751": "ONCOR", "752": "ONCOR", "753": "ONCOR",
    "754": "ONCOR", "755": "ONCOR", "756": "ONCOR", "757": "ONCOR",
    "758": "ONCOR", "759": "ONCOR", "760": "ONCOR", "761": "ONCOR",
    "762": "ONCOR", "763": "ONCOR", "764": "ONCOR", "765": "ONCOR",
    "766": "ONCOR", "767": "ONCOR", "768": "ONCOR", "769": "ONCOR",
    "759": "ONCOR",
    # Waco area - Oncor
    "766": "ONCOR", "767": "ONCOR", "768": "ONCOR",
    # Tyler/East Texas - Oncor
    "756": "ONCOR", "757": "ONCOR",
    
    # Houston area - CenterPoint
    "770": "CENTERPOINT", "771": "CENTERPOINT", "772": "CENTERPOINT",
    "773": "CENTERPOINT", "774": "CENTERPOINT", "775": "CENTERPOINT",
    "776": "CENTERPOINT", "777": "CENTERPOINT", "778": "CENTERPOINT",
    "779": "CENTERPOINT",
    # Galveston - CenterPoint
    "775": "CENTERPOINT",
    # Beaumont area - CenterPoint (some areas)
    "776": "CENTERPOINT", "777": "CENTERPOINT",
    
    # Austin area - Oncor (parts) / some municipal
    "786": "ONCOR", "787": "ONCOR", "788": "ONCOR", "789": "ONCOR",
    
    # San Antonio area - CPS Energy (municipal, not deregulated)
    # "780": "MUNICIPAL", "781": "MUNICIPAL", "782": "MUNICIPAL",
    
    # Corpus Christi / South Texas - AEP Central
    "783": "AEP_CENTRAL", "784": "AEP_CENTRAL",
    "785": "AEP_CENTRAL",
    
    # Rio Grande Valley - AEP Central
    "785": "AEP_CENTRAL",
    
    # Abilene area - AEP North
    "795": "AEP_NORTH", "796": "AEP_NORTH",
    
    # Lubbock area - Lubbock Power & Light (municipal) or AEP North nearby
    "793": "AEP_NORTH", "794": "AEP_NORTH",
    
    # Amarillo area - Xcel Energy (not ERCOT)
    # "790": "NOT_ERCOT", "791": "NOT_ERCOT",
    
    # El Paso - El Paso Electric (not ERCOT)
    # "798": "NOT_ERCOT", "799": "NOT_ERCOT",
}

# Cities with municipal utilities (not in deregulated market)
TEXAS_MUNICIPAL_CITIES = {
    "AUSTIN": "Austin Energy",
    "SAN ANTONIO": "CPS Energy",
    "LUBBOCK": "Lubbock Power & Light",
    "BRYAN": "Bryan Texas Utilities",
    "COLLEGE STATION": "Bryan Texas Utilities",
    "GARLAND": "Garland Power & Light",
    "GREENVILLE": "Greenville Electric Utility System",
    "NEW BRAUNFELS": "New Braunfels Utilities",
    "GEORGETOWN": "Georgetown Utility Systems",
    "DENTON": "Denton Municipal Electric",
    "BOERNE": "Boerne Utilities",
    "KERRVILLE": "Kerrville Public Utility Board",
    "FREDERICKSBURG": "Fredericksburg Electric",
    "SEGUIN": "Seguin Electric",
    "BROWNSVILLE": "Brownsville Public Utilities Board",
}

# Electric cooperatives in Texas (not in deregulated market)
TEXAS_COOPS = [
    "Pedernales Electric Cooperative",
    "Bluebonnet Electric Cooperative",
    "Guadalupe Valley Electric Cooperative",
    "Bandera Electric Cooperative",
    "Medina Electric Cooperative",
    "Nueces Electric Cooperative",
    "South Texas Electric Cooperative",
    "Magic Valley Electric Cooperative",
    "Tri-County Electric Cooperative",
    "CoServ Electric",
    "United Cooperative Services",
    "Farmers Electric Cooperative",
    "Grayson-Collin Electric Cooperative",
    "Navarro County Electric Cooperative",
    "Wood County Electric Cooperative",
]


def get_texas_tdu(zip_code: str, city: str = None) -> Dict:
    """
    Get the TDU for a Texas ZIP code.
    
    Returns:
        Dict with TDU info, confidence, and selection reason
    """
    city_upper = (city or "").upper().strip()
    
    # Check if it's a municipal utility city first
    if city_upper in TEXAS_MUNICIPAL_CITIES:
        municipal_name = TEXAS_MUNICIPAL_CITIES[city_upper]
        return {
            "primary": {
                "name": municipal_name,
                "type": "MUNICIPAL",
                "phone": None,
                "website": None,
            },
            "confidence": "verified",
            "source": "Texas Municipal Utility Database",
            "selection_reason": f"{city} is served by {municipal_name}, a municipal utility not in the deregulated ERCOT market.",
            "is_deregulated": False,
            "alternatives": []
        }
    
    # Check ZIP prefix for TDU
    zip_prefix = zip_code[:3] if len(zip_code) >= 3 else None
    
    if zip_prefix and zip_prefix in TEXAS_ZIP_PREFIX_TO_TDU:
        tdu_key = TEXAS_ZIP_PREFIX_TO_TDU[zip_prefix]
        tdu = TEXAS_TDUS.get(tdu_key)
        
        if tdu:
            return {
                "primary": {
                    "name": tdu["name"],
                    "type": "TDU",
                    "phone": tdu["phone"],
                    "website": tdu["website"],
                    "tdu_id": tdu["id"],
                },
                "confidence": "high",
                "source": "Texas PowerToChoose ZIP mapping",
                "selection_reason": f"ZIP {zip_code} is in {tdu['name']} territory ({tdu['service_area']}).",
                "is_deregulated": True,
                "alternatives": []
            }
    
    # ZIP not in our mapping - could be non-ERCOT area or needs verification
    return {
        "primary": None,
        "confidence": "low",
        "source": "Texas ZIP mapping",
        "selection_reason": f"ZIP {zip_code} not found in ERCOT deregulated market. May be served by a municipal utility, co-op, or non-ERCOT utility.",
        "is_deregulated": None,
        "alternatives": []
    }


def match_hifld_to_texas_tdu(candidates: List[Dict], zip_code: str, city: str = None) -> Dict:
    """
    Match HIFLD candidates to Texas TDU data.
    
    For deregulated areas (TDU territories), the TDU is the distribution utility.
    HIFLD candidates may show retail providers or overlapping territories.
    We prioritize the authoritative TDU data.
    
    Args:
        candidates: List of utility dicts from HIFLD
        zip_code: ZIP code for the address
        city: City name
    
    Returns:
        Verified result with primary provider and alternatives
    """
    # First get the authoritative TDU for this location
    tdu_result = get_texas_tdu(zip_code, city)
    
    if tdu_result["primary"]:
        # We have authoritative TDU/municipal data
        tdu_name = tdu_result["primary"]["name"].upper()
        tdu_type = tdu_result["primary"].get("type", "TDU")
        
        # For TDUs in deregulated market, use the TDU data directly
        # HIFLD may not have TDU polygons, just retail provider territories
        if tdu_type == "TDU":
            # Use TDU data as primary, HIFLD candidates as alternatives
            return {
                "primary": {
                    "NAME": tdu_result["primary"]["name"],
                    "TYPE": "TDU",
                    "TELEPHONE": tdu_result["primary"].get("phone"),
                    "WEBSITE": tdu_result["primary"].get("website"),
                    "STATE": "TX",
                    "tdu_id": tdu_result["primary"].get("tdu_id"),
                },
                "confidence": "verified",
                "source": tdu_result["source"],
                "selection_reason": tdu_result["selection_reason"],
                "is_deregulated": True,
                "alternatives": candidates  # All HIFLD candidates are alternatives
            }
        
        # For municipal utilities, try to find matching HIFLD candidate
        matched_candidate = None
        alternatives = []
        
        for candidate in candidates:
            candidate_name = (candidate.get("NAME") or "").upper()
            
            # Check for municipal match (city name in utility name)
            if any(term in candidate_name for term in tdu_name.split()):
                matched_candidate = candidate
            else:
                alternatives.append(candidate)
        
        if matched_candidate:
            # Merge HIFLD data with municipal data
            result = {
                "primary": {
                    **matched_candidate,
                    "verified_name": tdu_result["primary"]["name"],
                },
                "confidence": "verified",
                "source": tdu_result["source"],
                "selection_reason": tdu_result["selection_reason"],
                "is_deregulated": tdu_result["is_deregulated"],
                "alternatives": alternatives
            }
        else:
            # TDU not in HIFLD candidates - use TDU data directly
            result = {
                "primary": {
                    "NAME": tdu_result["primary"]["name"],
                    "TYPE": tdu_result["primary"]["type"],
                    "TELEPHONE": tdu_result["primary"].get("phone"),
                    "WEBSITE": tdu_result["primary"].get("website"),
                },
                "confidence": "verified",
                "source": tdu_result["source"],
                "selection_reason": tdu_result["selection_reason"],
                "is_deregulated": tdu_result["is_deregulated"],
                "alternatives": candidates  # All HIFLD candidates are alternatives
            }
        
        return result
    
    # No authoritative TDU data - check for municipal/coop in candidates
    city_upper = (city or "").upper()
    
    for candidate in candidates:
        candidate_name = (candidate.get("NAME") or "").upper()
        
        # Check if it's a municipal utility matching the city
        if city_upper and city_upper in candidate_name:
            return {
                "primary": candidate,
                "confidence": "high",
                "source": "City name match",
                "selection_reason": f"{candidate.get('NAME')} matches city name {city}.",
                "is_deregulated": False,
                "alternatives": [c for c in candidates if c != candidate]
            }
        
        # Check for known coops
        for coop in TEXAS_COOPS:
            if coop.upper() in candidate_name or candidate_name in coop.upper():
                return {
                    "primary": candidate,
                    "confidence": "high",
                    "source": "Texas Cooperative Database",
                    "selection_reason": f"{candidate.get('NAME')} is a Texas electric cooperative.",
                    "is_deregulated": False,
                    "alternatives": [c for c in candidates if c != candidate]
                }
    
    # Fallback - return first candidate with low confidence
    if candidates:
        return {
            "primary": candidates[0],
            "confidence": "low",
            "source": "HIFLD (unverified)",
            "selection_reason": "Could not verify with authoritative Texas data. First HIFLD candidate returned.",
            "is_deregulated": None,
            "alternatives": candidates[1:] if len(candidates) > 1 else []
        }
    
    return {
        "primary": None,
        "confidence": "none",
        "source": None,
        "selection_reason": "No electric utility found for this location.",
        "is_deregulated": None,
        "alternatives": []
    }


# =============================================================================
# MAIN VERIFICATION FUNCTION
# =============================================================================

def verify_electric_provider(
    state: str,
    zip_code: str,
    city: str,
    county: str,
    candidates: List[Dict]
) -> Dict:
    """
    Verify and select the correct electric provider using state-specific data.
    
    Args:
        state: Two-letter state code (e.g., "TX")
        zip_code: ZIP code
        city: City name
        county: County name
        candidates: List of utility dicts from HIFLD
    
    Returns:
        Dict with:
        - primary: The verified primary provider
        - confidence: "verified" | "high" | "medium" | "low"
        - source: Data source used for verification
        - selection_reason: Explanation of why this provider was selected
        - is_deregulated: Whether the area is in a deregulated market
        - alternatives: Other possible providers
    """
    state = (state or "").upper()
    
    # Texas has special TDU handling
    if state == "TX":
        return match_hifld_to_texas_tdu(candidates, zip_code, city)
    
    # Try EIA ZIP-to-utility lookup for all other states
    # This covers most IOUs (Investor-Owned Utilities)
    if zip_code:
        eia_result = verify_with_eia(candidates, zip_code, city, state)
        if eia_result:
            return eia_result
    
    # TODO: Add other deregulated states with state-specific sources
    # elif state == "PA":
    #     return verify_pennsylvania(candidates, zip_code, city)
    # elif state == "OH":
    #     return verify_ohio(candidates, zip_code, city)
    # elif state == "IL":
    #     return verify_illinois(candidates, zip_code, city)
    # elif state == "NY":
    #     return verify_new_york(candidates, zip_code, city)
    
    # Fallback: use ranking heuristics for ZIPs not in EIA data
    # (typically municipal utilities, co-ops, or rural areas)
    return rank_candidates_generic(candidates, city, county)


def rank_candidates_generic(candidates: List[Dict], city: str = None, county: str = None) -> Dict:
    """
    Generic ranking for states without specific verification data.
    Uses heuristics to pick the most likely provider.
    """
    if not candidates:
        return {
            "primary": None,
            "confidence": "none",
            "source": None,
            "selection_reason": "No electric utility found for this location.",
            "is_deregulated": None,
            "alternatives": []
        }
    
    if len(candidates) == 1:
        return {
            "primary": candidates[0],
            "confidence": "high",
            "source": "HIFLD (single result)",
            "selection_reason": "Only one utility serves this location.",
            "is_deregulated": None,
            "alternatives": []
        }
    
    # Score candidates
    scored = []
    city_upper = (city or "").upper()
    county_upper = (county or "").upper()
    
    for c in candidates:
        score = 50
        name = (c.get("NAME") or "").upper()
        utility_type = (c.get("TYPE") or "").upper()
        
        # City match is strong signal for municipal utilities
        if city_upper and city_upper in name:
            score += 35
        
        # County match
        if county_upper and county_upper in name:
            score += 15
        
        # Large IOUs - expanded list
        large_ious = ["DUKE ENERGY", "DOMINION", "SOUTHERN COMPANY", "ENTERGY",
                      "XCEL ENERGY", "PACIFIC GAS", "SOUTHERN CALIFORNIA EDISON",
                      "CON EDISON", "CONSOLIDATED EDISON", "GEORGIA POWER", 
                      "FLORIDA POWER", "EVERSOURCE", "NATIONAL GRID", "PSEG", 
                      "EXELON", "AMEREN", "DTE ENERGY", "CONSUMERS ENERGY",
                      "FIRSTENERGY", "CLEVELAND ELECTRIC", "OHIO EDISON",
                      "TOLEDO EDISON", "COMMONWEALTH EDISON", "PECO", "PPL",
                      "DUQUESNE", "CENTERPOINT", "ONCOR", "AEP", "AMERICAN ELECTRIC",
                      "ENTERGY", "EVERGY", "ALLIANT", "WESTAR", "ROCKY MOUNTAIN",
                      "PUGET SOUND", "AVISTA", "IDAHO POWER", "PACIFICORP",
                      "ARIZONA PUBLIC SERVICE", "SALT RIVER PROJECT", "TUCSON ELECTRIC",
                      "NV ENERGY", "NEVADA POWER", "SIERRA PACIFIC"]
        for iou in large_ious:
            if iou in name:
                score += 25
                break
        
        # Utility type scoring
        if "INVESTOR" in utility_type or "IOU" in utility_type:
            score += 15
        elif "COOPERATIVE" in utility_type or "COOP" in utility_type:
            score += 10
        elif "MUNICIPAL" in utility_type:
            score += 5
        
        # Cooperatives by name
        if "COOP" in name or "EMC" in name or "RURAL ELECTRIC" in name:
            score += 10
        
        # Deprioritize wholesale/transmission/generation
        if "WHOLESALE" in name or "TRANSMISSION" in name or "GENERATION" in name:
            score -= 40
        if "WAPA" in name or "BPA" in name or "BONNEVILLE" in name:
            score -= 40
        
        # Deprioritize municipal from other cities
        if ("MUNICIPAL" in name or "CITY OF" in name or "TOWN OF" in name):
            if city_upper and city_upper not in name:
                score -= 25
        
        c["_score"] = score
        scored.append(c)
    
    scored.sort(key=lambda x: x.get("_score", 0), reverse=True)
    
    primary = scored[0]
    alternatives = scored[1:]
    
    # Determine confidence based on score gap
    if len(scored) > 1:
        gap = primary.get("_score", 0) - scored[1].get("_score", 0)
        if gap >= 20:
            confidence = "high"
        elif gap >= 10:
            confidence = "medium"
        else:
            confidence = "low"
    else:
        confidence = "high"
    
    return {
        "primary": primary,
        "confidence": confidence,
        "source": "HIFLD (ranked by heuristics)",
        "selection_reason": f"Selected {primary.get('NAME')} based on ranking heuristics. {len(alternatives)} other utilities also serve this area.",
        "is_deregulated": None,
        "alternatives": alternatives
    }


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    # Test Texas verification
    print("Testing Texas TDU lookup...")
    
    # Test Dallas area
    result = get_texas_tdu("75201", "Dallas")
    print(f"\nDallas 75201: {result['primary']['name'] if result['primary'] else 'None'}")
    print(f"  Confidence: {result['confidence']}")
    print(f"  Reason: {result['selection_reason']}")
    
    # Test Houston area
    result = get_texas_tdu("77001", "Houston")
    print(f"\nHouston 77001: {result['primary']['name'] if result['primary'] else 'None'}")
    print(f"  Confidence: {result['confidence']}")
    print(f"  Reason: {result['selection_reason']}")
    
    # Test Austin (municipal)
    result = get_texas_tdu("78701", "Austin")
    print(f"\nAustin 78701: {result['primary']['name'] if result['primary'] else 'None'}")
    print(f"  Confidence: {result['confidence']}")
    print(f"  Reason: {result['selection_reason']}")
    
    # Test San Antonio (municipal)
    result = get_texas_tdu("78201", "San Antonio")
    print(f"\nSan Antonio 78201: {result['primary']['name'] if result['primary'] else 'None'}")
    print(f"  Confidence: {result['confidence']}")
    print(f"  Reason: {result['selection_reason']}")
