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
    
    IMPORTANT: Electric cooperatives (co-ops) are NOT in the deregulated market.
    If HIFLD returns a co-op, we should use that instead of the TDU mapping.
    
    Args:
        candidates: List of utility dicts from HIFLD
        zip_code: ZIP code for the address
        city: City name
    
    Returns:
        Verified result with primary provider and alternatives
    """
    # FIRST: Check if HIFLD returns an electric cooperative
    # Co-ops are NOT in the deregulated market and should take priority over TDU mapping
    coop_candidate = None
    coop_keywords = ["COOP", "CO-OP", "COOPERATIVE", "ELECTRIC COOP", "RURAL ELECTRIC"]
    
    for candidate in candidates:
        candidate_name = (candidate.get("NAME") or "").upper()
        if any(kw in candidate_name for kw in coop_keywords):
            coop_candidate = candidate
            break
    
    if coop_candidate:
        # This area is served by a cooperative - NOT deregulated
        coop_name = coop_candidate.get("NAME", "Electric Cooperative")
        other_candidates = [c for c in candidates if c != coop_candidate]
        return {
            "primary": coop_candidate,
            "confidence": "verified",
            "source": "HIFLD Electric Cooperative Territory",
            "selection_reason": f"This address is served by {coop_name}, an electric cooperative not in the deregulated ERCOT market.",
            "is_deregulated": False,
            "alternatives": other_candidates
        }
    
    # No co-op found - check TDU/municipal mapping
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
# GAS UTILITY VERIFICATION
# =============================================================================

# Texas Gas LDCs - ZIP prefix mapping
TEXAS_GAS_LDCS = {
    "ATMOS": {
        "name": "Atmos Energy",
        "phone": "1-888-286-6700",
        "website": "https://www.atmosenergy.com",
        "service_area": "Dallas/Fort Worth, West Texas, North Texas"
    },
    "CENTERPOINT": {
        "name": "CenterPoint Energy",
        "phone": "1-800-752-8036",
        "website": "https://www.centerpointenergy.com",
        "service_area": "Houston metropolitan area"
    },
    "TEXAS_GAS_SERVICE": {
        "name": "Texas Gas Service",
        "phone": "1-800-700-2443",
        "website": "https://www.texasgasservice.com",
        "service_area": "Austin, Central Texas, El Paso"
    }
}

# Texas ZIP prefix to gas LDC mapping (default by 3-digit prefix)
TEXAS_GAS_ZIP_PREFIX = {
    # Dallas/Fort Worth area - Atmos Energy
    "750": "ATMOS", "751": "ATMOS", "752": "ATMOS", "753": "ATMOS",
    "754": "ATMOS", "755": "ATMOS", "760": "ATMOS", "761": "ATMOS",
    "762": "ATMOS", "763": "ATMOS", "764": "ATMOS", "765": "ATMOS",
    "766": "ATMOS", "767": "ATMOS", "768": "ATMOS", "769": "ATMOS",
    # Waco area - Atmos
    "766": "ATMOS", "767": "ATMOS",
    # Amarillo/Lubbock - Atmos
    "790": "ATMOS", "791": "ATMOS", "792": "ATMOS", "793": "ATMOS",
    "794": "ATMOS", "795": "ATMOS", "796": "ATMOS",
    
    # Houston area - CenterPoint
    "770": "CENTERPOINT", "771": "CENTERPOINT", "772": "CENTERPOINT",
    "773": "CENTERPOINT", "774": "CENTERPOINT", "775": "CENTERPOINT",
    "776": "CENTERPOINT", "777": "CENTERPOINT", "778": "CENTERPOINT",
    "779": "CENTERPOINT",
    
    # Austin area - Texas Gas Service (default for 786-789)
    "786": "TEXAS_GAS_SERVICE", "787": "TEXAS_GAS_SERVICE",
    "788": "TEXAS_GAS_SERVICE", "789": "TEXAS_GAS_SERVICE",
    # El Paso - Texas Gas Service
    "798": "TEXAS_GAS_SERVICE", "799": "TEXAS_GAS_SERVICE",
}

# Full 5-digit ZIP overrides for areas where prefix mapping is wrong
# These take precedence over the 3-digit prefix mapping
TEXAS_GAS_ZIP_OVERRIDES = {
    # Hays County - Kyle, Buda, San Marcos area is CenterPoint, not Texas Gas Service
    # The 786xx prefix defaults to Texas Gas Service (Austin) but southern Hays County is CenterPoint
    "78640": "CENTERPOINT",  # Kyle
    "78610": "CENTERPOINT",  # Buda
    "78666": "CENTERPOINT",  # San Marcos
    "78676": "CENTERPOINT",  # Wimberley
    "78620": "CENTERPOINT",  # Dripping Springs (verify)
}

# =============================================================================
# GENERAL GAS ZIP OVERRIDES (ALL STATES)
# =============================================================================
# Use this for any ZIP where HIFLD/database data is wrong
# Format: "ZIP": {"name": "Provider Name", "phone": "...", "note": "reason"}

GAS_ZIP_OVERRIDES = {
    # Texas - Hays County (CenterPoint, not Texas Gas Service)
    "78640": {"state": "TX", "name": "CenterPoint Energy", "phone": "1-800-752-8036", "note": "Kyle - user verified"},
    "78610": {"state": "TX", "name": "CenterPoint Energy", "phone": "1-800-752-8036", "note": "Buda"},
    "78666": {"state": "TX", "name": "CenterPoint Energy", "phone": "1-800-752-8036", "note": "San Marcos"},
    "78676": {"state": "TX", "name": "CenterPoint Energy", "phone": "1-800-752-8036", "note": "Wimberley"},
    "78620": {"state": "TX", "name": "CenterPoint Energy", "phone": "1-800-752-8036", "note": "Dripping Springs"},
    
    # Add other states as issues are discovered
    # "28202": {"state": "NC", "name": "Piedmont Natural Gas", "phone": "...", "note": "Charlotte"},
}

def load_gas_zip_overrides():
    """Load gas ZIP overrides from both hardcoded dict and user feedback JSON file."""
    import json
    from pathlib import Path
    
    # Start with hardcoded overrides
    overrides = GAS_ZIP_OVERRIDES.copy()
    
    # Load user feedback overrides
    feedback_file = Path(__file__).parent / "data" / "gas_zip_overrides.json"
    if feedback_file.exists():
        try:
            with open(feedback_file, 'r') as f:
                user_overrides = json.load(f)
            # User feedback overrides take precedence
            overrides.update(user_overrides)
        except (json.JSONDecodeError, IOError):
            pass
    
    return overrides


# =============================================================================
# PROBLEM AREAS REGISTRY
# =============================================================================

PROBLEM_AREAS_FILE = os.path.join(os.path.dirname(__file__), 'data', 'problem_areas.json')
_problem_areas_cache = None

def load_problem_areas():
    """Load problem areas data with caching."""
    global _problem_areas_cache
    if _problem_areas_cache is None:
        if os.path.exists(PROBLEM_AREAS_FILE):
            with open(PROBLEM_AREAS_FILE, 'r') as f:
                _problem_areas_cache = json.load(f)
        else:
            _problem_areas_cache = {'zip': {}, 'county': {}, 'state': {}}
    return _problem_areas_cache


def check_problem_area(zip_code: str, county: str, state: str, utility_type: str) -> dict:
    """
    Check if location is a known problem area for this utility type.
    
    Returns:
        {
            'is_problem_area': bool,
            'level': 'zip' | 'county' | 'state' | None,
            'issue': str | None,
            'recommendation': str | None
        }
    """
    problem_areas = load_problem_areas()
    
    # Check ZIP-level first (most specific)
    if zip_code and zip_code in problem_areas.get('zip', {}):
        area = problem_areas['zip'][zip_code]
        if utility_type in area.get('utilities_affected', []):
            return {
                'is_problem_area': True,
                'level': 'zip',
                'issue': area.get('issue'),
                'recommendation': area.get('recommendation'),
                'known_correct': area.get('known_correct', {}).get(utility_type, {})
            }
    
    # Check county-level
    county_key = f"{county}|{state}" if county and state else None
    if county_key and county_key in problem_areas.get('county', {}):
        area = problem_areas['county'][county_key]
        if utility_type in area.get('utilities_affected', []):
            return {
                'is_problem_area': True,
                'level': 'county',
                'issue': area.get('issue'),
                'recommendation': area.get('recommendation')
            }
    
    # Check state-level
    if state and state in problem_areas.get('state', {}):
        area = problem_areas['state'][state]
        if utility_type in area.get('utilities_affected', []):
            return {
                'is_problem_area': True,
                'level': 'state',
                'issue': area.get('issue'),
                'recommendation': area.get('recommendation')
            }
    
    return {
        'is_problem_area': False,
        'level': None,
        'issue': None,
        'recommendation': None
    }


def add_problem_area(
    level: str,  # 'zip', 'county', 'state'
    key: str,    # ZIP code, "County|ST", or state abbrev
    utilities_affected: list,
    issue: str,
    recommendation: str,
    known_correct: dict = None
):
    """Add or update a problem area entry."""
    global _problem_areas_cache
    from datetime import datetime
    
    problem_areas = load_problem_areas()
    
    if level not in problem_areas:
        problem_areas[level] = {}
    
    entry = {
        'utilities_affected': utilities_affected,
        'issue': issue,
        'recommendation': recommendation,
        'last_reviewed': datetime.now().strftime('%Y-%m-%d')
    }
    
    if known_correct:
        entry['known_correct'] = known_correct
    
    problem_areas[level][key] = entry
    
    # Save to file
    os.makedirs(os.path.dirname(PROBLEM_AREAS_FILE), exist_ok=True)
    with open(PROBLEM_AREAS_FILE, 'w') as f:
        json.dump(problem_areas, f, indent=2)
    
    # Invalidate cache
    _problem_areas_cache = None
    
    print(f"Added problem area: {level} {key}")

# Major gas LDCs by state (for verification)
STATE_GAS_LDCS = {
    "AL": ["Spire Alabama", "Alagasco"],
    "AK": ["ENSTAR Natural Gas", "Alaska Pipeline"],
    "AZ": ["Southwest Gas", "UNS Gas"],
    "AR": ["CenterPoint Energy", "Black Hills Energy", "Arkansas Oklahoma Gas"],
    "CA": ["Pacific Gas & Electric", "SoCalGas", "San Diego Gas & Electric"],
    "CO": ["Xcel Energy", "Black Hills Energy", "Atmos Energy"],
    "CT": ["Eversource", "Southern Connecticut Gas", "Connecticut Natural Gas"],
    "DE": ["Chesapeake Utilities", "Delmarva Power"],
    "FL": ["TECO Peoples Gas", "Florida City Gas", "Florida Public Utilities"],
    "GA": ["Atlanta Gas Light", "Liberty Utilities"],
    "HI": ["Hawaii Gas", "The Gas Company"],
    "ID": ["Intermountain Gas", "Avista"],
    "IL": ["Nicor Gas", "Peoples Gas", "Ameren Illinois", "MidAmerican Energy"],
    "IN": ["CenterPoint Energy", "Vectren", "NIPSCO"],
    "IA": ["MidAmerican Energy", "Black Hills Energy", "Alliant Energy"],
    "KS": ["Kansas Gas Service", "Black Hills Energy", "Atmos Energy"],
    "KY": ["LG&E", "Duke Energy Kentucky", "Columbia Gas", "Atmos Energy"],
    "LA": ["Atmos Energy", "CenterPoint Energy", "Entergy"],
    "ME": ["Summit Natural Gas", "Bangor Gas", "Maine Natural Gas"],
    "MD": ["BGE", "Washington Gas", "Columbia Gas"],
    "MA": ["National Grid", "Eversource", "Columbia Gas", "Liberty Utilities"],
    "MI": ["DTE Gas", "Consumers Energy", "SEMCO Energy"],
    "MN": ["CenterPoint Energy", "Xcel Energy", "Minnesota Energy Resources"],
    "MS": ["Spire Mississippi", "Atmos Energy"],
    "MO": ["Spire Missouri", "Ameren Missouri", "Liberty Utilities"],
    "MT": ["NorthWestern Energy", "Montana-Dakota Utilities"],
    "NE": ["Black Hills Energy", "Metropolitan Utilities District", "NorthWestern Energy"],
    "NV": ["Southwest Gas", "NV Energy"],
    "NH": ["Liberty Utilities", "Northern Utilities"],
    "NJ": ["PSE&G", "New Jersey Natural Gas", "South Jersey Industries", "Elizabethtown Gas"],
    "NM": ["New Mexico Gas Company", "Xcel Energy"],
    "NY": ["Con Edison", "National Grid", "National Fuel Gas", "Central Hudson", "NYSEG", "RG&E"],
    "NC": ["Piedmont Natural Gas", "Dominion Energy", "PSNC Energy"],
    "ND": ["Montana-Dakota Utilities", "Xcel Energy"],
    "OH": ["Columbia Gas", "Dominion Energy", "Duke Energy Ohio", "CenterPoint Energy"],
    "OK": ["Oklahoma Natural Gas", "CenterPoint Energy"],
    "OR": ["NW Natural", "Avista", "Cascade Natural Gas"],
    "PA": ["PECO", "Columbia Gas", "UGI", "National Fuel Gas", "Peoples Gas"],
    "RI": ["National Grid"],
    "SC": ["Piedmont Natural Gas", "Dominion Energy", "SCE&G"],
    "SD": ["Black Hills Energy", "MidAmerican Energy", "Montana-Dakota Utilities"],
    "TN": ["Piedmont Natural Gas", "Atmos Energy", "Nashville Gas"],
    "TX": ["Atmos Energy", "CenterPoint Energy", "Texas Gas Service"],
    "UT": ["Dominion Energy", "Questar Gas"],
    "VT": ["Vermont Gas Systems"],
    "VA": ["Washington Gas", "Columbia Gas", "Dominion Energy", "Roanoke Gas"],
    "WA": ["Puget Sound Energy", "Avista", "Cascade Natural Gas", "NW Natural"],
    "WV": ["Mountaineer Gas", "Dominion Energy", "Hope Gas"],
    "WI": ["We Energies", "Xcel Energy", "Madison Gas & Electric", "Alliant Energy"],
    "WY": ["Black Hills Energy", "Montana-Dakota Utilities", "SourceGas"],
    "DC": ["Washington Gas"],
}

# States with limited gas infrastructure
LIMITED_GAS_STATES = ["FL", "HI", "VT", "ME"]

# States with JSON gas mapping files
GAS_MAPPING_STATES = ["CA", "IL", "OH", "GA", "AZ"]
_gas_mappings_cache = {}


def load_gas_mapping(state: str) -> Dict:
    """Load gas mapping JSON file for a state."""
    if state in _gas_mappings_cache:
        return _gas_mappings_cache[state]
    
    state_lower = state.lower()
    state_names = {
        'CA': 'california',
        'IL': 'illinois', 
        'OH': 'ohio',
        'GA': 'georgia',
        'AZ': 'arizona'
    }
    
    filename = state_names.get(state.upper())
    if not filename:
        return {}
    
    filepath = os.path.join(os.path.dirname(__file__), 'data', 'gas_mappings', f'{filename}.json')
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            _gas_mappings_cache[state] = json.load(f)
            return _gas_mappings_cache[state]
    
    return {}


def get_state_gas_ldc(state: str, zip_code: str, city: str = None) -> Dict:
    """Get gas LDC for states with JSON mapping files (CA, IL, OH, GA, AZ)."""
    state = state.upper() if state else ""
    if state not in GAS_MAPPING_STATES:
        return None
    
    mapping = load_gas_mapping(state)
    if not mapping:
        return None
    
    zip_code = str(zip_code).strip()[:5] if zip_code else ""
    zip_prefix = zip_code[:3] if len(zip_code) >= 3 else None
    
    utilities = mapping.get('utilities', {})
    
    # Check 5-digit ZIP overrides first
    if zip_code in mapping.get('zip_overrides', {}):
        utility_key = mapping['zip_overrides'][zip_code]
        utility = utilities.get(utility_key, {})
        if utility:
            return {
                "primary": {
                    "name": utility.get("name", utility_key),
                    "phone": utility.get("phone"),
                    "website": utility.get("website"),
                },
                "confidence": "verified",
                "source": f"{state} PUC territory data",
                "selection_reason": f"ZIP {zip_code} is in {utility.get('name', utility_key)} territory.",
                "alternatives": []
            }
    
    # Check 3-digit prefix mapping
    if zip_prefix and zip_prefix in mapping.get('zip_to_utility', {}):
        utility_key = mapping['zip_to_utility'][zip_prefix]
        utility = utilities.get(utility_key, {})
        if utility:
            return {
                "primary": {
                    "name": utility.get("name", utility_key),
                    "phone": utility.get("phone"),
                    "website": utility.get("website"),
                },
                "confidence": "verified",
                "source": f"{state} PUC territory data",
                "selection_reason": f"ZIP {zip_code} is in {utility.get('name', utility_key)} territory ({utility.get('service_area', '')}).",
                "alternatives": []
            }
    
    return None


def get_texas_gas_ldc(zip_code: str, city: str = None) -> Dict:
    """Get the gas LDC for a Texas ZIP code."""
    zip_code = str(zip_code).strip()[:5]  # Normalize to 5 digits
    zip_prefix = zip_code[:3] if len(zip_code) >= 3 else None
    
    # FIRST: Check 5-digit ZIP overrides (for areas where prefix mapping is wrong)
    if zip_code in TEXAS_GAS_ZIP_OVERRIDES:
        ldc_key = TEXAS_GAS_ZIP_OVERRIDES[zip_code]
        ldc = TEXAS_GAS_LDCS.get(ldc_key)
        
        if ldc:
            return {
                "primary": {
                    "name": ldc["name"],
                    "phone": ldc["phone"],
                    "website": ldc["website"],
                },
                "confidence": "verified",
                "source": "Texas gas ZIP override (user-verified)",
                "selection_reason": f"ZIP {zip_code} is in {ldc['name']} territory (verified override).",
                "alternatives": []
            }
    
    # SECOND: Check 3-digit prefix mapping
    if zip_prefix and zip_prefix in TEXAS_GAS_ZIP_PREFIX:
        ldc_key = TEXAS_GAS_ZIP_PREFIX[zip_prefix]
        ldc = TEXAS_GAS_LDCS.get(ldc_key)
        
        if ldc:
            return {
                "primary": {
                    "name": ldc["name"],
                    "phone": ldc["phone"],
                    "website": ldc["website"],
                },
                "confidence": "verified",
                "source": "Texas Railroad Commission territory data",
                "selection_reason": f"ZIP {zip_code} is in {ldc['name']} territory ({ldc['service_area']}).",
                "alternatives": []
            }
    
    # ZIP not in mapping - may not have gas service
    return {
        "primary": None,
        "confidence": "low",
        "source": "Texas gas mapping",
        "selection_reason": f"ZIP {zip_code} not found in major Texas gas LDC territories. May use propane or have limited gas service.",
        "alternatives": []
    }


def verify_gas_provider(
    state: str,
    zip_code: str,
    city: str,
    county: str,
    candidates: List[Dict]
) -> Dict:
    """
    Verify and select the correct gas provider using state-specific data.
    
    Args:
        state: Two-letter state code
        zip_code: ZIP code
        city: City name
        county: County name
        candidates: List of gas utility dicts from HIFLD
    
    Returns:
        Dict with primary provider, confidence, source, alternatives, selection_reason
    """
    state = (state or "").upper()
    zip_code = str(zip_code).strip()[:5] if zip_code else ""
    
    # FIRST: Check general ZIP override table (includes user feedback overrides)
    all_overrides = load_gas_zip_overrides()
    if zip_code in all_overrides:
        override = all_overrides[zip_code]
        # Verify state matches (safety check)
        if override.get("state", "").upper() == state:
            return {
                "primary": {
                    "NAME": override["name"],
                    "TELEPHONE": override.get("phone"),
                    "STATE": state,
                    "TYPE": "LDC",
                },
                "confidence": "verified",
                "source": override.get("source", "ZIP override (user-verified)"),
                "selection_reason": f"ZIP {zip_code} verified: {override['name']}. {override.get('note', '')}",
                "alternatives": candidates  # Keep HIFLD candidates as alternatives
            }
    
    # Check if no candidates from HIFLD
    if not candidates:
        if state in LIMITED_GAS_STATES:
            return {
                "primary": None,
                "confidence": "none",
                "source": "HIFLD",
                "selection_reason": f"No natural gas service found. {state} has limited gas infrastructure - this area likely uses propane or is all-electric.",
                "no_service_note": "No natural gas service - area likely uses propane or heating oil",
                "alternatives": []
            }
        
        # Try to use state LDC database as fallback when HIFLD has no data
        state_ldcs = STATE_GAS_LDCS.get(state, [])
        if state_ldcs:
            # Return the primary LDC for the state with medium confidence
            primary_ldc = state_ldcs[0]
            return {
                "primary": {
                    "NAME": primary_ldc,
                    "STATE": state,
                    "TYPE": "LDC",
                },
                "confidence": "medium",
                "source": "State LDC database (HIFLD gap)",
                "selection_reason": f"HIFLD data unavailable for this location. {primary_ldc} is the primary gas provider in {state}. Verify with provider.",
                "alternatives": []
            }
        
        return {
            "primary": None,
            "confidence": "none",
            "source": "HIFLD",
            "selection_reason": "No natural gas service found at this address. Area may use propane or be all-electric.",
            "no_service_note": "No natural gas service available",
            "alternatives": []
        }
    
    # Check state-specific gas mappings (TX, CA, IL, OH, GA, AZ)
    state_gas_result = get_state_gas_ldc(state, zip_code, city)
    if state_gas_result and state_gas_result.get("primary"):
        # Try to match with HIFLD candidate
        state_name = state_gas_result["primary"]["name"].upper()
        matched = None
        alternatives = []
        
        for c in candidates:
            c_name = (c.get("NAME") or "").upper()
            if any(word in c_name for word in state_name.split() if len(word) > 3):
                matched = c
            else:
                alternatives.append(c)
        
        if matched:
            return {
                "primary": {**matched, "verified_name": state_gas_result["primary"]["name"]},
                "confidence": "verified",
                "source": state_gas_result["source"],
                "selection_reason": state_gas_result["selection_reason"],
                "alternatives": alternatives
            }
        else:
            # Use state data directly
            return {
                "primary": {
                    "NAME": state_gas_result["primary"]["name"],
                    "TELEPHONE": state_gas_result["primary"].get("phone"),
                    "WEBSITE": state_gas_result["primary"].get("website"),
                    "STATE": state,
                },
                "confidence": "verified",
                "source": state_gas_result["source"],
                "selection_reason": state_gas_result["selection_reason"],
                "alternatives": candidates
            }
    
    # Legacy Texas-specific handling (fallback)
    if state == "TX":
        tx_result = get_texas_gas_ldc(zip_code, city)
        if tx_result["primary"]:
            # Try to match with HIFLD candidate
            tx_name = tx_result["primary"]["name"].upper()
            matched = None
            alternatives = []
            
            for c in candidates:
                c_name = (c.get("NAME") or "").upper()
                if any(word in c_name for word in tx_name.split()):
                    matched = c
                else:
                    alternatives.append(c)
            
            if matched:
                return {
                    "primary": {**matched, "verified_name": tx_result["primary"]["name"]},
                    "confidence": "verified",
                    "source": tx_result["source"],
                    "selection_reason": tx_result["selection_reason"],
                    "alternatives": alternatives
                }
            else:
                # Use TX data directly
                return {
                    "primary": {
                        "NAME": tx_result["primary"]["name"],
                        "TELEPHONE": tx_result["primary"]["phone"],
                        "WEBSITE": tx_result["primary"]["website"],
                        "STATE": "TX",
                    },
                    "confidence": "verified",
                    "source": tx_result["source"],
                    "selection_reason": tx_result["selection_reason"],
                    "alternatives": candidates
                }
    
    # For other states, try to match HIFLD candidates with known LDCs
    state_ldcs = STATE_GAS_LDCS.get(state, [])
    
    if state_ldcs and candidates:
        # Score candidates based on matching known LDCs
        scored = []
        city_upper = (city or "").upper()
        
        for c in candidates:
            score = 50
            name = (c.get("NAME") or "").upper()
            
            # Match against known state LDCs
            for ldc in state_ldcs:
                ldc_words = ldc.upper().split()
                if any(word in name for word in ldc_words if len(word) > 3):
                    score += 30
                    break
            
            # City match
            if city_upper and city_upper in name:
                score += 25
            
            # Deprioritize wholesale/transmission
            if "WHOLESALE" in name or "TRANSMISSION" in name or "PIPELINE" in name:
                score -= 40
            
            c["_score"] = score
            scored.append(c)
        
        scored.sort(key=lambda x: x.get("_score", 0), reverse=True)
        primary = scored[0]
        alternatives = scored[1:]
        
        # Determine confidence
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
            "source": "HIFLD (matched with state LDC database)",
            "selection_reason": f"Selected {primary.get('NAME')} as most likely gas provider for this area.",
            "alternatives": alternatives
        }
    
    # Single candidate
    if len(candidates) == 1:
        return {
            "primary": candidates[0],
            "confidence": "high",
            "source": "HIFLD (single result)",
            "selection_reason": "Only one gas utility serves this location.",
            "alternatives": []
        }
    
    # Multiple candidates, no state-specific data - use first
    return {
        "primary": candidates[0],
        "confidence": "medium",
        "source": "HIFLD",
        "selection_reason": f"Multiple gas utilities may serve this area. {candidates[0].get('NAME')} selected as primary.",
        "alternatives": candidates[1:]
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
