"""
Confidence scoring for utility provider lookups.
Returns numeric score 0-100 with transparent factor breakdown.
"""

from datetime import datetime
from typing import Dict, List, Optional, Any

# Source quality scores (max one applies)
SOURCE_SCORES = {
    'user_confirmed': 45,       # Multiple users confirmed this
    'user_feedback': 35,        # Single user feedback
    'utility_api': 40,          # Direct from utility company lookup
    'special_district': 35,     # MUD/CDD/PUD boundary data
    'zip_override': 30,         # Manual ZIP correction table
    'eia_861': 25,              # EIA federal data (electric)
    'railroad_commission': 25,  # Texas RRC (gas)
    'state_puc': 25,            # State PUC data
    'hifld_polygon': 20,        # HIFLD territory polygon
    'epa_sdwis': 20,            # EPA water systems
    'state_ldc_mapping': 20,    # State-level gas LDC mapping
    'google_serp': 25,          # Google search as primary source
    'serp_only': 15,            # Google search only (no database match)
    'supplemental': 25,         # Supplemental data file
    'county_match': 10,         # County-level match (water)
    'heuristic': 5,             # Name matching / fallback
    'unknown': 0
}

# Geographic precision scores (additive)
PRECISION_SCORES = {
    'address': 15,              # Exact address match
    'subdivision': 12,          # Subdivision/neighborhood match
    'special_district': 12,     # Within special district boundary
    'zip5': 8,                  # 5-digit ZIP match
    'zip3': 4,                  # 3-digit ZIP prefix match
    'county': 2,                # County-level only
    'state': 0                  # State-level only
}


def calculate_confidence(
    source: str,
    match_level: str = 'zip5',
    serp_result: Optional[Dict] = None,
    agreeing_sources: Optional[List[str]] = None,
    data_age_months: int = 6,
    is_problem_area: bool = False,
    utility_type: str = 'electric'
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
    if is_problem_area:
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
    
    # Map common source strings to score keys
    mappings = {
        'google_serp': 'google_serp',
        'serp': 'google_serp',
        'supplemental': 'supplemental',
        'epa': 'epa_sdwis',
        'epa_sdwis': 'epa_sdwis',
        'eia': 'eia_861',
        'eia_861': 'eia_861',
        'hifld': 'hifld_polygon',
        'zip override': 'zip_override',
        'zip_override': 'zip_override',
        'user feedback': 'user_feedback',
        'user_feedback': 'user_feedback',
        'user confirmed': 'user_confirmed',
        'texas gas zip override': 'zip_override',
        'texas railroad commission': 'railroad_commission',
        'state ldc': 'state_ldc_mapping',
        'county': 'county_match',
        'heuristic': 'heuristic',
        'fcc': 'utility_api',
        'fcc broadband': 'utility_api',
    }
    
    for key, value in mappings.items():
        if key in source_lower:
            return value
    
    return 'unknown'
