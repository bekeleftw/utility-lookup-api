"""
Confidence scoring for utility provider lookups.
Returns numeric score 0-100 with transparent factor breakdown.
"""

from datetime import datetime
from typing import Dict, List, Optional, Any

# Import state data availability (for "best available" boost)
try:
    from state_data_quality import calculate_data_availability_boost, get_state_tier
except ImportError:
    # Fallback if module not available
    def calculate_data_availability_boost(state, utility_type, source):
        return {"boost": 0, "reason": None}
    def get_state_tier(state):
        return 3

# Source quality scores (max one applies)
# Scale: 0-100 where 85+ = high confidence, 65-84 = medium, <65 = low
# Updated with Phase 12-14 data sources
SOURCE_SCORES = {
    # === TIER 1: Authoritative (90+) - Skip SERP verification ===
    'user_confirmed': 95,       # Multiple users confirmed this - ground truth
    'utility_direct_api': 92,   # Direct from utility GIS API (Austin Energy, CA CEC, etc.)
    'franchise_agreement': 92,  # City franchise agreement data
    'parcel_data': 90,          # County assessor parcel-level data
    'user_feedback': 88,        # Single user feedback
    'municipal_utility': 88,    # Municipal utility database (Austin Energy, CPS, LADWP, etc.)
    
    # === TIER 2: High Quality (80-89) - Spot-check SERP ===
    'special_district': 85,     # MUD/CDD/PUD boundary data (TCEQ, FL DEO, etc.)
    'verified': 85,             # Verified by state-specific data (TX RRC, etc.)
    'utility_api': 85,          # Direct from utility company lookup (legacy)
    'state_puc_map': 82,        # State PUC territory maps
    'zip_override': 80,         # Manual ZIP correction table
    'railroad_commission': 80,  # Texas RRC (gas) - authoritative
    
    # === TIER 3: Good Quality (65-79) - SERP recommended ===
    'state_puc': 75,            # State PUC data (non-map)
    'address_inference': 72,    # Inferred from nearby verified addresses
    'eia_861': 70,              # EIA federal data (electric)
    'supplemental': 70,         # Supplemental data file (curated)
    'electric_cooperative': 68, # NRECA cooperative data
    'state_ldc_mapping': 65,    # State-level gas LDC mapping (JSON files)
    
    # === TIER 4: Needs Verification (50-64) - Always SERP ===
    'google_serp': 60,          # Google search as primary source
    'hifld_polygon': 58,        # HIFLD territory polygon
    'epa_sdwis': 55,            # EPA water systems
    'serp_only': 50,            # Google search only (no database match)
    
    # === TIER 5: Low Confidence (<50) - Requires verification ===
    'county_match': 45,         # County-level match (water)
    'heuristic': 30,            # Name matching / fallback
    'unknown': 15
}

# Geographic precision scores (additive bonus)
PRECISION_SCORES = {
    'parcel': 15,               # Parcel-level match (assessor data)
    'address': 12,              # Exact address match
    'gis_point': 10,            # GIS point-in-polygon query
    'subdivision': 8,           # Subdivision/neighborhood match
    'special_district': 8,      # Within special district boundary
    'zip5': 5,                  # 5-digit ZIP match
    'zip3': 3,                  # 3-digit ZIP prefix match
    'county': 1,                # County-level only
    'state': 0                  # State-level only
}


def calculate_confidence(
    source: str,
    match_level: str = 'zip5',
    serp_result: Optional[Dict] = None,
    agreeing_sources: Optional[List[str]] = None,
    data_age_months: int = 6,
    is_problem_area: bool = False,
    utility_type: str = 'electric',
    state: str = None
) -> Dict[str, Any]:
    """
    Calculate confidence score with breakdown.
    
    Args:
        source: Primary data source used (key from SOURCE_SCORES)
        match_level: Geographic precision (key from PRECISION_SCORES)
        serp_result: Dict with 'confirmed', 'contradicted', or 'inconclusive'
        agreeing_sources: List of other sources that returned same provider
        data_age_months: How old the data is
        is_problem_area: Whether this ZIP/area is flagged as problematic
        utility_type: 'electric', 'gas', 'water', 'internet'
        state: State code for data availability adjustment
    
    Returns:
        Dict with score, level, factors, and recommendation
    """
    score = 0
    factors = []
    
    # === DATA SOURCE QUALITY ===
    source_score = SOURCE_SCORES.get(source, 0)
    score += source_score
    source_label = source.replace('_', ' ').title()
    factors.append({
        'category': 'Data Source',
        'points': source_score,
        'description': f"{source_label} data"
    })
    
    # === GEOGRAPHIC PRECISION ===
    precision_score = PRECISION_SCORES.get(match_level, 0)
    if precision_score > 0:
        score += precision_score
        precision_label = match_level.replace('_', ' ').title()
        factors.append({
            'category': 'Geographic Precision',
            'points': precision_score,
            'description': f"{precision_label}-level match"
        })
    
    # === SERP VERIFICATION ===
    if serp_result:
        if serp_result.get('confirmed'):
            score += 20
            factors.append({
                'category': 'Search Verification',
                'points': 20,
                'description': 'Confirmed by Google search'
            })
        elif serp_result.get('contradicted'):
            score -= 25
            factors.append({
                'category': 'Search Verification',
                'points': -25,
                'description': 'Contradicted by Google search'
            })
        elif serp_result.get('inconclusive'):
            factors.append({
                'category': 'Search Verification',
                'points': 0,
                'description': 'Google search inconclusive'
            })
    
    # === MULTIPLE SOURCES AGREE ===
    if agreeing_sources:
        num_agreeing = len(agreeing_sources)
        if num_agreeing >= 3:
            score += 20
            factors.append({
                'category': 'Cross-Validation',
                'points': 20,
                'description': f'{num_agreeing} sources agree'
            })
        elif num_agreeing == 2:
            score += 10
            factors.append({
                'category': 'Cross-Validation',
                'points': 10,
                'description': '2 sources agree'
            })
    
    # === PROBLEM AREA PENALTY ===
    # Don't penalize high-confidence sources (Tier 1 & 2)
    high_confidence_sources = {
        'user_confirmed', 'user_feedback', 'municipal_utility', 'utility_api', 
        'verified', 'utility_direct_api', 'franchise_agreement', 'parcel_data',
        'special_district', 'state_puc_map', 'zip_override', 'railroad_commission'
    }
    if is_problem_area and source not in high_confidence_sources:
        score -= 15
        factors.append({
            'category': 'Known Issues',
            'points': -15,
            'description': 'Known problem area (boundary zone)'
        })
    
    # === DATA FRESHNESS ===
    if data_age_months > 24:
        score -= 10
        factors.append({
            'category': 'Data Freshness',
            'points': -10,
            'description': 'Data over 2 years old'
        })
    elif data_age_months > 12:
        score -= 5
        factors.append({
            'category': 'Data Freshness',
            'points': -5,
            'description': 'Data over 1 year old'
        })
    
    # === STATE DATA AVAILABILITY BOOST ===
    # If we're using the best available data for this state, boost confidence
    # A human couldn't do better without calling the utility directly
    if state:
        availability_boost = calculate_data_availability_boost(state, utility_type, source)
        boost = availability_boost.get("boost", 0)
        if boost > 0:
            score += boost
            factors.append({
                'category': 'Data Availability',
                'points': boost,
                'description': availability_boost.get("reason", "Best available for state")
            })
    
    # === CALCULATE FINAL SCORE ===
    final_score = max(0, min(100, score))
    
    # Determine level
    if final_score >= 80:
        level = 'verified'
    elif final_score >= 60:
        level = 'high'
    elif final_score >= 40:
        level = 'medium'
    else:
        level = 'low'
    
    # Generate recommendation
    recommendation = get_recommendation(level, utility_type)
    
    return {
        'score': final_score,
        'level': level,
        'factors': factors,
        'recommendation': recommendation
    }


def get_recommendation(level: str, utility_type: str) -> Optional[str]:
    """Get actionable recommendation based on confidence level."""
    if level == 'verified':
        return None
    elif level == 'high':
        return f"Likely correct. Confirm with {utility_type} company if needed."
    elif level == 'medium':
        return f"Verify {utility_type} provider before move-in."
    else:
        return f"Low confidence. Contact city/county for correct {utility_type} provider."


def format_confidence_for_response(confidence: Dict) -> Dict:
    """
    Format confidence data for API response.
    Simplified version for external consumers.
    """
    return {
        'score': confidence['score'],
        'level': confidence['level'],
        'recommendation': confidence['recommendation'],
        'factors_summary': [
            f"{f['points']:+d}: {f['description']}" 
            for f in confidence['factors']
        ]
    }


def format_confidence_for_display(confidence: Dict) -> str:
    """
    Format confidence as human-readable string.
    """
    lines = [f"Confidence: {confidence['score']}/100 ({confidence['level']})"]
    lines.append("Breakdown:")
    for factor in confidence['factors']:
        sign = '+' if factor['points'] >= 0 else ''
        lines.append(f"  {sign}{factor['points']}: {factor['description']}")
    if confidence['recommendation']:
        lines.append(f"Recommendation: {confidence['recommendation']}")
    return '\n'.join(lines)


def source_to_score_key(source_string: str) -> str:
    """Convert source strings from lookup results to score keys."""
    source_lower = source_string.lower() if source_string else 'unknown'
    
    # Map common source strings to score keys (ordered by tier)
    mappings = {
        'user confirmed': 'user_confirmed',
        'user_confirmed': 'user_confirmed',
        'utility_direct_api': 'utility_direct_api',
        'arcgis': 'utility_direct_api',
        'gis api': 'utility_direct_api',
        'franchise_agreement': 'franchise_agreement',
        'parcel_data': 'parcel_data',
        'assessor': 'parcel_data',
        'user feedback': 'user_feedback',
        'user_feedback': 'user_feedback',
        'municipal_utility': 'municipal_utility',
        'municipal utility': 'municipal_utility',
        'municipal_utility_database': 'municipal_utility',
        'special_district': 'special_district',
        'special district': 'special_district',
        'mud': 'special_district',
        'wcid': 'special_district',
        'fwsd': 'special_district',
        'cdd': 'special_district',
        'pud': 'special_district',
        'verified': 'verified',
        'railroad commission': 'railroad_commission',
        'state_puc_map': 'state_puc_map',
        'puc territory': 'state_puc_map',
        'zip override': 'zip_override',
        'zip_override': 'zip_override',
        'state puc': 'state_puc',
        'state_puc': 'state_puc',
        'address_inference': 'address_inference',
        'inferred': 'address_inference',
        'eia': 'eia_861',
        'eia_861': 'eia_861',
        'supplemental': 'supplemental',
        'electric_cooperative': 'electric_cooperative',
        'co-op': 'electric_cooperative',
        'state ldc': 'state_ldc_mapping',
        'state_ldc_mapping': 'state_ldc_mapping',
        'google_serp': 'google_serp',
        'serp': 'google_serp',
        'hifld': 'hifld_polygon',
        'epa': 'epa_sdwis',
        'epa_sdwis': 'epa_sdwis',
        'county': 'county_match',
        'heuristic': 'heuristic',
        'utility_api': 'utility_api',
        'fcc': 'utility_api',
    }
    
    for key, value in mappings.items():
        if key in source_lower:
            return value
    
    return 'unknown'
