"""
Confidence scoring for utility provider lookups.
Returns numeric score 0-100 with transparent factor breakdown.
"""

from datetime import datetime
from typing import Dict, List, Optional, Any

# Source quality scores (max one applies)
# Scale: 0-100 where 85+ = high confidence, 65-84 = medium, <65 = low
SOURCE_SCORES = {
    'user_confirmed': 90,       # Multiple users confirmed this
    'user_feedback': 85,        # Single user feedback
    'municipal_utility': 85,    # Municipal utility database (Austin Energy, CPS, LADWP, etc.)
    'utility_api': 85,          # Direct from utility company lookup
    'special_district': 80,     # MUD/CDD/PUD boundary data
    'verified': 80,             # Verified by state-specific data (TX RRC, etc.)
    'zip_override': 75,         # Manual ZIP correction table
    'railroad_commission': 75,  # Texas RRC (gas) - authoritative
    'state_puc': 70,            # State PUC data
    'eia_861': 65,              # EIA federal data (electric)
    'supplemental': 65,         # Supplemental data file (curated)
    'google_serp': 60,          # Google search as primary source
    'hifld_polygon': 55,        # HIFLD territory polygon
    'epa_sdwis': 55,            # EPA water systems
    'state_ldc_mapping': 50,    # State-level gas LDC mapping
    'serp_only': 45,            # Google search only (no database match)
    'county_match': 40,         # County-level match (water)
    'heuristic': 25,            # Name matching / fallback
    'unknown': 10
}

# Geographic precision scores (additive bonus)
PRECISION_SCORES = {
    'address': 10,              # Exact address match
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
    # Don't penalize high-confidence sources (municipal utilities, user confirmed, etc.)
    high_confidence_sources = {'user_confirmed', 'user_feedback', 'municipal_utility', 'utility_api', 'verified'}
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
        # Municipal utilities - highest confidence
        'municipal_utility': 'municipal_utility',
        'municipal utility': 'municipal_utility',
        'municipal_utility_database': 'municipal_utility',
        'municipal utility database': 'municipal_utility',
        
        # Verified state-specific data
        'verified': 'verified',
        'texas railroad commission': 'verified',
        'railroad commission': 'verified',
        'state puc': 'state_puc',
        
        # User feedback
        'user feedback': 'user_feedback',
        'user_feedback': 'user_feedback',
        'user confirmed': 'user_confirmed',
        'user_confirmed': 'user_confirmed',
        
        # Special districts
        'special_district': 'special_district',
        'special district': 'special_district',
        'mud': 'special_district',
        'wcid': 'special_district',
        'fwsd': 'special_district',
        'cdd': 'special_district',
        
        # ZIP overrides
        'zip override': 'zip_override',
        'zip_override': 'zip_override',
        'texas gas zip override': 'zip_override',
        
        # Federal/state data
        'eia': 'eia_861',
        'eia_861': 'eia_861',
        'epa': 'epa_sdwis',
        'epa_sdwis': 'epa_sdwis',
        'supplemental': 'supplemental',
        
        # SERP
        'google_serp': 'google_serp',
        'serp': 'google_serp',
        
        # HIFLD
        'hifld': 'hifld_polygon',
        
        # Other
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
