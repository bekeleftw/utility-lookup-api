#!/usr/bin/env python3
"""
Water Provider Reconciler - Uses AI to pick the best water provider
when multiple sources (CSV, EPA, municipal) return different results.
"""

import os
import json
from typing import Optional, Dict, List
from openai import OpenAI

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

def reconcile_water_providers(
    address: str,
    city: str,
    state: str,
    zip_code: str,
    candidates: List[Dict]
) -> Optional[Dict]:
    """
    Use AI to pick the best water provider from multiple candidates.
    
    Args:
        address: Full street address
        city: City name
        state: State abbreviation
        zip_code: ZIP code
        candidates: List of provider dicts from different sources
        
    Returns:
        Best matching provider dict with confidence explanation
    """
    if not candidates:
        return None
    
    if len(candidates) == 1:
        candidates[0]['_reconciliation'] = 'single_source'
        return candidates[0]
    
    # Check if all candidates are the same provider (just different sources)
    names = set()
    for c in candidates:
        name = (c.get('name') or '').lower()
        # Normalize name for comparison
        name = name.replace('water department', '').replace('water utility', '')
        name = name.replace('water', '').replace('utilities', '').strip()
        names.add(name[:20])  # First 20 chars for fuzzy match
    
    if len(names) == 1:
        # All sources agree - return the one with most info
        best = max(candidates, key=lambda c: sum(1 for v in c.values() if v))
        best['_reconciliation'] = 'sources_agree'
        return best
    
    # Sources disagree - use AI to pick
    prompt = f"""You are a utility service territory expert. Given an address and multiple water provider candidates from different data sources, determine which provider most likely serves this specific address.

Address: {address}
City: {city}
State: {state}
ZIP: {zip_code}

Candidates:
{json.dumps(candidates, indent=2, default=str)}

Consider:
1. Municipal/township water departments typically serve addresses within that municipality
2. Regional providers (like "NJ American Water") serve broader areas but may not serve addresses in cities with their own municipal water
3. MUDs (Municipal Utility Districts) serve specific developments, usually identified by number
4. Provider names containing the city name are more likely correct for that city
5. EPA data covers larger service areas; local municipal data is more specific

Return JSON with:
{{
    "best_match_index": <0-based index of best candidate>,
    "confidence": "high" | "medium" | "low",
    "reasoning": "<brief explanation>"
}}

Return ONLY valid JSON, no other text."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=300
        )
        
        content = response.choices[0].message.content.strip()
        # Extract JSON
        if content.startswith('```'):
            content = content.split('```')[1]
            if content.startswith('json'):
                content = content[4:]
        
        result = json.loads(content)
        best_idx = result.get('best_match_index', 0)
        
        if 0 <= best_idx < len(candidates):
            best = candidates[best_idx]
            best['_reconciliation'] = 'ai_selected'
            best['_reconciliation_confidence'] = result.get('confidence', 'medium')
            best['_reconciliation_reasoning'] = result.get('reasoning', '')
            return best
        
    except Exception as e:
        print(f"[Reconciler] AI error: {e}")
    
    # Fallback: prefer municipal/township providers over regional
    for c in candidates:
        name_lower = (c.get('name') or '').lower()
        if 'township' in name_lower or 'municipal' in name_lower or city.lower() in name_lower:
            c['_reconciliation'] = 'heuristic_local'
            return c
    
    # Last resort: return first candidate
    candidates[0]['_reconciliation'] = 'fallback'
    return candidates[0]


def get_all_water_candidates(
    city: str,
    state: str,
    zip_code: str = None,
    county: str = None
) -> List[Dict]:
    """
    Gather water provider candidates from all sources.
    """
    candidates = []
    
    # Source 1: CSV providers
    try:
        from csv_water_lookup import lookup_water_from_csv
        csv_result = lookup_water_from_csv(city, state)
        if csv_result:
            csv_result['_source'] = 'csv_providers'
            candidates.append(csv_result)
    except Exception as e:
        print(f"[Reconciler] CSV lookup error: {e}")
    
    # Source 2: EPA SDWIS
    try:
        from pathlib import Path
        import json as json_mod
        water_file = Path(__file__).parent / "water_utilities_lookup.json"
        if water_file.exists():
            with open(water_file, 'r') as f:
                epa_data = json_mod.load(f)
            city_key = f"{state}|{city.upper()}"
            if city_key in epa_data.get('by_city', {}):
                epa_result = epa_data['by_city'][city_key].copy()
                epa_result['_source'] = 'epa_sdwis'
                candidates.append(epa_result)
    except Exception as e:
        print(f"[Reconciler] EPA lookup error: {e}")
    
    # Source 3: Municipal utilities
    try:
        from municipal_utilities import lookup_municipal_water
        muni_result = lookup_municipal_water(city, state)
        if muni_result:
            muni_result['_source'] = 'municipal_utility'
            candidates.append(muni_result)
    except Exception as e:
        print(f"[Reconciler] Municipal lookup error: {e}")
    
    return candidates


if __name__ == '__main__':
    # Test
    test_cases = [
        ("3211 Ventura Dr", "East Hanover", "NJ", "07936"),
        ("100 Congress Ave", "Austin", "TX", "78701"),
        ("123 Main St", "Short Hills", "NJ", "07078"),
    ]
    
    for addr, city, state, zip_code in test_cases:
        print(f"\n=== {addr}, {city}, {state} {zip_code} ===")
        candidates = get_all_water_candidates(city, state, zip_code)
        print(f"Found {len(candidates)} candidates:")
        for i, c in enumerate(candidates):
            print(f"  {i}: {c.get('name')} ({c.get('_source')})")
        
        if candidates:
            best = reconcile_water_providers(addr, city, state, zip_code, candidates)
            print(f"Best: {best.get('name')} (via {best.get('_reconciliation')})")
