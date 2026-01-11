# Cross-Validation System

## Context

Currently we pick the best single source and trust it. This can lead to errors when that source is wrong. Better approach: require multiple sources to agree before marking as "verified."

## Goal

- Query multiple data sources for each utility type
- Compare results and identify agreement/disagreement
- Adjust confidence based on source agreement
- Flag contradictions for review

## Implementation

### Step 1: Create Cross-Validation Module

Create file: `cross_validation.py`

```python
"""
Cross-validation for utility provider lookups.
Compares results from multiple sources and assesses agreement.
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import re


class AgreementLevel(Enum):
    FULL = "full"           # All sources agree
    MAJORITY = "majority"   # Most sources agree
    SPLIT = "split"         # Sources disagree equally
    SINGLE = "single"       # Only one source available
    NONE = "none"           # No sources returned data


@dataclass
class SourceResult:
    """Result from a single data source."""
    source_name: str
    provider_name: Optional[str]
    confidence: str  # 'high', 'medium', 'low'
    raw_data: Optional[dict] = None


@dataclass 
class CrossValidationResult:
    """Result of cross-validating multiple sources."""
    primary_provider: Optional[str]
    agreement_level: AgreementLevel
    agreeing_sources: List[str]
    disagreeing_sources: List[str]
    all_candidates: Dict[str, List[str]]  # provider_name -> [source_names]
    confidence_adjustment: int  # Points to add/subtract from confidence
    notes: List[str]


def normalize_provider_name(name: str) -> str:
    """
    Normalize provider names for comparison.
    E.g., "ONCOR ELECTRIC DELIVERY" == "Oncor" == "oncor electric"
    """
    if not name:
        return ""
    
    # Lowercase
    normalized = name.lower().strip()
    
    # Remove common suffixes
    suffixes = [
        'inc', 'inc.', 'llc', 'llc.', 'corp', 'corp.', 'corporation',
        'company', 'co', 'co.', 'electric', 'energy', 'power',
        'delivery', 'service', 'services', 'utility', 'utilities',
        'gas', 'natural gas', 'coop', 'cooperative', 'ltd', 'lp'
    ]
    
    for suffix in suffixes:
        normalized = re.sub(rf'\b{suffix}\b', '', normalized)
    
    # Remove punctuation and extra whitespace
    normalized = re.sub(r'[^\w\s]', '', normalized)
    normalized = ' '.join(normalized.split())
    
    return normalized


def providers_match(name1: str, name2: str) -> bool:
    """Check if two provider names refer to the same utility."""
    norm1 = normalize_provider_name(name1)
    norm2 = normalize_provider_name(name2)
    
    if not norm1 or not norm2:
        return False
    
    # Exact match after normalization
    if norm1 == norm2:
        return True
    
    # One contains the other (for partial matches)
    if norm1 in norm2 or norm2 in norm1:
        return True
    
    # Check for common abbreviations/aliases
    aliases = {
        'pge': ['pacific gas', 'pg&e', 'pacific gas and electric'],
        'sce': ['southern california edison', 'socal edison'],
        'sdge': ['san diego gas', 'sdg&e'],
        'fpl': ['florida power', 'florida power and light'],
        'duke': ['duke energy'],
        'oncor': ['oncor electric', 'oncor delivery'],
        'centerpoint': ['center point', 'entex'],
        'atmos': ['atmos energy'],
        'aep': ['american electric power', 'aep texas'],
        'txu': ['txu energy'],
        'pec': ['pedernales', 'pedernales electric'],
    }
    
    for key, alias_list in aliases.items():
        matches1 = key in norm1 or any(a in norm1 for a in alias_list)
        matches2 = key in norm2 or any(a in norm2 for a in alias_list)
        if matches1 and matches2:
            return True
    
    return False


def cross_validate(results: List[SourceResult]) -> CrossValidationResult:
    """
    Cross-validate results from multiple sources.
    
    Args:
        results: List of SourceResult from different data sources
    
    Returns:
        CrossValidationResult with agreement analysis
    """
    # Filter out sources with no result
    valid_results = [r for r in results if r.provider_name]
    
    if not valid_results:
        return CrossValidationResult(
            primary_provider=None,
            agreement_level=AgreementLevel.NONE,
            agreeing_sources=[],
            disagreeing_sources=[],
            all_candidates={},
            confidence_adjustment=-20,
            notes=["No data sources returned a provider"]
        )
    
    if len(valid_results) == 1:
        return CrossValidationResult(
            primary_provider=valid_results[0].provider_name,
            agreement_level=AgreementLevel.SINGLE,
            agreeing_sources=[valid_results[0].source_name],
            disagreeing_sources=[],
            all_candidates={valid_results[0].provider_name: [valid_results[0].source_name]},
            confidence_adjustment=0,
            notes=["Only one data source available"]
        )
    
    # Group providers by normalized name
    provider_groups: Dict[str, List[SourceResult]] = {}
    
    for result in valid_results:
        norm_name = normalize_provider_name(result.provider_name)
        
        # Check if this matches an existing group
        matched = False
        for group_name in list(provider_groups.keys()):
            if providers_match(norm_name, group_name):
                provider_groups[group_name].append(result)
                matched = True
                break
        
        if not matched:
            provider_groups[norm_name] = [result]
    
    # Find the group with most sources
    sorted_groups = sorted(provider_groups.items(), key=lambda x: len(x[1]), reverse=True)
    
    top_group_name, top_group_results = sorted_groups[0]
    top_count = len(top_group_results)
    total_count = len(valid_results)
    
    # Determine agreement level
    if top_count == total_count:
        agreement_level = AgreementLevel.FULL
        confidence_adjustment = 20
    elif top_count > total_count / 2:
        agreement_level = AgreementLevel.MAJORITY
        confidence_adjustment = 10
    else:
        agreement_level = AgreementLevel.SPLIT
        confidence_adjustment = -10
    
    # Build candidate map
    all_candidates = {}
    for group_name, group_results in provider_groups.items():
        # Use the first original name (not normalized)
        original_name = group_results[0].provider_name
        all_candidates[original_name] = [r.source_name for r in group_results]
    
    # Identify agreeing and disagreeing sources
    agreeing_sources = [r.source_name for r in top_group_results]
    disagreeing_sources = [
        r.source_name for r in valid_results 
        if r.source_name not in agreeing_sources
    ]
    
    # Build notes
    notes = []
    if agreement_level == AgreementLevel.FULL:
        notes.append(f"All {total_count} sources agree on provider")
    elif agreement_level == AgreementLevel.MAJORITY:
        notes.append(f"{top_count}/{total_count} sources agree on provider")
        notes.append(f"Disagreeing sources: {', '.join(disagreeing_sources)}")
    elif agreement_level == AgreementLevel.SPLIT:
        notes.append("Sources disagree on provider")
        for provider, sources in all_candidates.items():
            notes.append(f"  {provider}: {', '.join(sources)}")
    
    # Use original provider name from highest-confidence agreeing source
    primary_provider = max(
        top_group_results, 
        key=lambda r: {'high': 3, 'medium': 2, 'low': 1}.get(r.confidence, 0)
    ).provider_name
    
    return CrossValidationResult(
        primary_provider=primary_provider,
        agreement_level=agreement_level,
        agreeing_sources=agreeing_sources,
        disagreeing_sources=disagreeing_sources,
        all_candidates=all_candidates,
        confidence_adjustment=confidence_adjustment,
        notes=notes
    )


def format_for_response(cv_result: CrossValidationResult) -> dict:
    """Format cross-validation result for API response."""
    return {
        'provider': cv_result.primary_provider,
        'agreement': cv_result.agreement_level.value,
        'agreeing_sources': cv_result.agreeing_sources,
        'disagreeing_sources': cv_result.disagreeing_sources,
        'all_candidates': cv_result.all_candidates,
        'notes': cv_result.notes
    }
```

### Step 2: Integrate Into Lookup Flow

In `utility_lookup.py`:

```python
from cross_validation import SourceResult, cross_validate, format_for_response

def lookup_electric_utility(lat, lon, city, county, state, zip_code, verify=True):
    """Lookup electric utility with cross-validation."""
    
    results = []
    
    # === Source 1: EIA Form 861 ===
    eia_result = lookup_eia_861(zip_code)
    if eia_result:
        results.append(SourceResult(
            source_name='EIA Form 861',
            provider_name=eia_result.get('name'),
            confidence='high'
        ))
    
    # === Source 2: HIFLD Polygon ===
    hifld_result = lookup_hifld_electric(lat, lon)
    if hifld_result:
        results.append(SourceResult(
            source_name='HIFLD Territory',
            provider_name=hifld_result.get('name'),
            confidence='medium'
        ))
    
    # === Source 3: State-specific mapping (e.g., Texas TDU) ===
    state_result = lookup_state_electric(state, zip_code, city)
    if state_result:
        results.append(SourceResult(
            source_name=f'{state} State Data',
            provider_name=state_result.get('name'),
            confidence='high'
        ))
    
    # === Source 4: SERP (if verification enabled) ===
    if verify:
        serp_result = verify_electric_with_serp(f"{city}, {state} {zip_code}")
        if serp_result and serp_result.get('provider'):
            results.append(SourceResult(
                source_name='Google Search',
                provider_name=serp_result.get('provider'),
                confidence='high' if serp_result.get('verified') else 'medium'
            ))
    
    # === Cross-validate ===
    cv_result = cross_validate(results)
    
    # === Build response ===
    if not cv_result.primary_provider:
        return {
            'name': None,
            'confidence': 'none',
            'note': 'No electric utility found'
        }
    
    # Calculate final confidence
    base_confidence = 50  # Start at 50
    
    # Add source quality points
    for r in results:
        if r.provider_name and providers_match(r.provider_name, cv_result.primary_provider):
            if r.confidence == 'high':
                base_confidence += 15
            elif r.confidence == 'medium':
                base_confidence += 8
    
    # Add cross-validation adjustment
    base_confidence += cv_result.confidence_adjustment
    
    # Cap at 100
    final_score = max(0, min(100, base_confidence))
    
    # Determine level
    if final_score >= 80:
        level = 'verified'
    elif final_score >= 60:
        level = 'high'
    elif final_score >= 40:
        level = 'medium'
    else:
        level = 'low'
    
    return {
        'name': cv_result.primary_provider,
        'confidence': level,
        'confidence_score': final_score,
        'cross_validation': format_for_response(cv_result),
        'verified': level == 'verified'
    }
```

### Step 3: Log Disagreements for Review

```python
import json
from datetime import datetime

DISAGREEMENTS_FILE = 'data/cross_validation_disagreements.json'

def log_disagreement(
    address: str,
    utility_type: str,
    cv_result: CrossValidationResult
):
    """Log cross-validation disagreements for manual review."""
    
    if cv_result.agreement_level in [AgreementLevel.FULL, AgreementLevel.SINGLE]:
        return  # No disagreement to log
    
    try:
        with open(DISAGREEMENTS_FILE, 'r') as f:
            disagreements = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        disagreements = []
    
    entry = {
        'timestamp': datetime.now().isoformat(),
        'address': address,
        'utility_type': utility_type,
        'agreement_level': cv_result.agreement_level.value,
        'candidates': cv_result.all_candidates,
        'selected_provider': cv_result.primary_provider,
        'notes': cv_result.notes
    }
    
    disagreements.append(entry)
    
    # Keep only last 1000 entries
    if len(disagreements) > 1000:
        disagreements = disagreements[-1000:]
    
    with open(DISAGREEMENTS_FILE, 'w') as f:
        json.dump(disagreements, f, indent=2)


# Add API endpoint to review disagreements
@app.route('/api/disagreements', methods=['GET'])
def list_disagreements():
    """List cross-validation disagreements for review."""
    try:
        with open(DISAGREEMENTS_FILE, 'r') as f:
            disagreements = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        disagreements = []
    
    # Sort by most recent
    disagreements = sorted(disagreements, key=lambda x: x['timestamp'], reverse=True)
    
    return jsonify({
        'count': len(disagreements),
        'disagreements': disagreements[:100]  # Return latest 100
    })
```

## Testing

### Test Provider Matching
```python
from cross_validation import providers_match, normalize_provider_name

# Should match
assert providers_match("ONCOR ELECTRIC DELIVERY", "Oncor")
assert providers_match("Pacific Gas & Electric Co.", "PG&E")
assert providers_match("DUKE ENERGY CAROLINAS", "Duke Energy")

# Should not match
assert not providers_match("Oncor", "CenterPoint")
assert not providers_match("Duke Energy", "Dominion Energy")
```

### Test Cross-Validation
```python
from cross_validation import SourceResult, cross_validate, AgreementLevel

# Test full agreement
results = [
    SourceResult("EIA", "Oncor Electric", "high"),
    SourceResult("HIFLD", "ONCOR ELECTRIC DELIVERY", "medium"),
    SourceResult("SERP", "Oncor", "high")
]
cv = cross_validate(results)
assert cv.agreement_level == AgreementLevel.FULL
assert cv.confidence_adjustment == 20

# Test split
results = [
    SourceResult("EIA", "Oncor", "high"),
    SourceResult("HIFLD", "CenterPoint", "medium"),
]
cv = cross_validate(results)
assert cv.agreement_level == AgreementLevel.SPLIT
assert cv.confidence_adjustment == -10
```

### Test API Response
```bash
curl "https://web-production-9acc6.up.railway.app/api/lookup?address=301+Treasure+Trove+Path+Kyle+TX+78640"
```

Should include:
```json
{
  "utilities": {
    "electric": [{
      "name": "Pedernales Electric Cooperative",
      "cross_validation": {
        "agreement": "full",
        "agreeing_sources": ["HIFLD Territory", "Google Search"],
        "all_candidates": {
          "Pedernales Electric Cooperative": ["HIFLD Territory", "Google Search"]
        }
      }
    }]
  }
}
```

## Commit Message

```
Add cross-validation for multiple data sources

- cross_validation.py module
- Provider name normalization and matching
- Agreement level detection (full/majority/split)
- Confidence adjustment based on agreement
- Disagreement logging for review
- API endpoint to view disagreements
```
