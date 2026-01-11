# Confidence Scoring System

## Context

Current confidence levels ("high/medium/low") are vague and inconsistent. Users and internal teams need to understand WHY a result has a certain confidence level.

## Goal

- Replace vague labels with numeric scores (0-100)
- Show transparent breakdown of score factors
- Provide actionable recommendations based on score

## Implementation

### Step 1: Create confidence_scoring.py

```python
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
    'serp_only': 15,            # Google search only (no database match)
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
```

### Step 2: Integrate Into utility_lookup.py

Replace existing confidence assignment with:

```python
from confidence_scoring import calculate_confidence, format_confidence_for_response

def lookup_electric_utility(lat, lon, city, county, state, zip_code, verify=True):
    # ... existing lookup logic ...
    
    # After determining provider and source:
    confidence_data = calculate_confidence(
        source=data_source,  # e.g., 'eia_861', 'hifld_polygon', 'zip_override'
        match_level=match_level,  # e.g., 'zip5', 'subdivision'
        serp_result=serp_result if verify else None,
        agreeing_sources=agreeing_sources,
        data_age_months=get_data_age(data_source),
        is_problem_area=check_problem_area(zip_code, 'electric'),
        utility_type='electric'
    )
    
    return {
        'name': provider_name,
        'phone': phone,
        'website': website,
        'confidence': confidence_data['level'],
        'confidence_score': confidence_data['score'],
        'confidence_factors': confidence_data['factors_summary'],
        'recommendation': confidence_data['recommendation'],
        'source': data_source,
        'verified': confidence_data['level'] == 'verified'
    }
```

### Step 3: Update API Response Format

In api.py, include confidence details:

```python
@app.route('/api/lookup')
def lookup():
    # ... existing logic ...
    
    return jsonify({
        "address": address,
        "location": location_data,
        "utilities": {
            "electric": electric_results,
            "electric_confidence": {
                "score": electric_results[0]['confidence_score'] if electric_results else None,
                "level": electric_results[0]['confidence'] if electric_results else None,
                "factors": electric_results[0].get('confidence_factors', []) if electric_results else [],
                "recommendation": electric_results[0].get('recommendation') if electric_results else None
            },
            # ... same for gas, water, internet
        }
    })
```

## Testing

### Test Confidence Calculation
```python
# Test verified result
result = calculate_confidence(
    source='user_confirmed',
    match_level='address',
    serp_result={'confirmed': True},
    agreeing_sources=['eia_861', 'hifld_polygon'],
    data_age_months=1
)
assert result['score'] >= 80
assert result['level'] == 'verified'

# Test low confidence result
result = calculate_confidence(
    source='heuristic',
    match_level='county',
    serp_result={'contradicted': True},
    is_problem_area=True
)
assert result['score'] < 40
assert result['level'] == 'low'
```

### Test API Response
```bash
curl "https://web-production-9acc6.up.railway.app/api/lookup?address=301+Treasure+Trove+Path+Kyle+TX+78640"
```

Should return:
```json
{
  "utilities": {
    "electric_confidence": {
      "score": 75,
      "level": "high",
      "factors": [
        "+20: HIFLD polygon data",
        "+8: ZIP5-level match",
        "+20: Confirmed by Google search"
      ],
      "recommendation": "Likely correct. Confirm with electric company if needed."
    }
  }
}
```

## Commit Message

```
Add numeric confidence scoring with transparent factors

- New confidence_scoring.py module
- Scores 0-100 based on data source, precision, verification
- Transparent factor breakdown in API response
- Actionable recommendations based on score level
```
