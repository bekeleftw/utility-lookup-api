#!/usr/bin/env python3
"""
Provider ID Matcher - matches provider names to IDs from utility_providers_IDs.csv
Uses OpenAI-generated mappings for fuzzy matching and deduplication.
"""

import csv
import json
import os
import re
from typing import Optional, Dict, Tuple

# Cache for loaded data
_providers_cache = None
_mappings_cache = None
_simple_lookup_cache = None
_match_cache = {}  # In-memory cache for name matches
_canonical_ids_cache = None

MAPPINGS_FILE = os.path.join(os.path.dirname(__file__), 'data', 'provider_name_mappings.json')
SIMPLE_LOOKUP_FILE = os.path.join(os.path.dirname(__file__), 'data', 'provider_simple_lookup.json')
MATCH_CACHE_FILE = os.path.join(os.path.dirname(__file__), 'data', 'provider_match_cache.json')
CANONICAL_IDS_FILE = os.path.join(os.path.dirname(__file__), 'data', 'canonical_provider_ids.json')

# UtilityTypeId mapping
UTILITY_TYPE_MAP = {
    2: 'electric',
    3: 'water',
    4: 'gas',
    5: 'trash',
    6: 'sewer'
}

# Reverse mapping
UTILITY_TYPE_REVERSE = {v: k for k, v in UTILITY_TYPE_MAP.items()}


def normalize_name(name: str) -> str:
    """Normalize provider name for matching."""
    if not name:
        return ''
    # Lowercase
    name = name.lower()
    # Remove common suffixes
    name = re.sub(r'\s*-\s*[a-z]{2}$', '', name)  # State suffix like "- TX"
    name = re.sub(r'\s*\([a-z]{2}\)$', '', name)  # State in parens like "(TX)"
    name = re.sub(r'\s*,\s*[a-z]{2}$', '', name)  # State after comma like ", TX"
    # Remove special characters except spaces
    name = re.sub(r'[^a-z0-9\s]', '', name)
    # Remove common business suffixes (always safe to remove)
    suffix_words = [
        'inc', 'llc', 'corp', 'co', 'company', 'corporation', 'lp', 'ltd',
        'delivery', 'distribution', 
        'department', 'dept', 'division', 'div',
        'authority', 'commission', 'board'
    ]
    for word in suffix_words:
        name = re.sub(rf'\b{word}\b', '', name, flags=re.IGNORECASE)
    # Normalize whitespace
    name = ' '.join(name.split())
    return name


def load_match_cache() -> Dict[str, Dict]:
    """Load persistent match cache from disk."""
    global _match_cache
    
    if _match_cache:
        return _match_cache
    
    if os.path.exists(MATCH_CACHE_FILE):
        try:
            with open(MATCH_CACHE_FILE, 'r') as f:
                _match_cache = json.load(f)
            print(f"[ProviderMatcher] Loaded {len(_match_cache)} cached matches")
        except Exception as e:
            print(f"[ProviderMatcher] Error loading match cache: {e}")
            _match_cache = {}
    else:
        _match_cache = {}
    
    return _match_cache


def save_match_cache():
    """Save match cache to disk."""
    global _match_cache
    try:
        os.makedirs(os.path.dirname(MATCH_CACHE_FILE), exist_ok=True)
        with open(MATCH_CACHE_FILE, 'w') as f:
            json.dump(_match_cache, f, indent=2)
    except Exception as e:
        print(f"[ProviderMatcher] Error saving match cache: {e}")


def cache_match(name: str, utility_type: str, match: Dict):
    """Cache a successful match for future lookups."""
    global _match_cache
    load_match_cache()
    
    key = f"{normalize_name(name)}|{utility_type}"
    _match_cache[key] = {
        'id': match.get('id'),
        'title': match.get('title'),
        'matched_via': match.get('matched_via'),
        'match_score': match.get('match_score'),
        'original_name': name
    }
    
    # Save periodically (every 10 new entries)
    if len(_match_cache) % 10 == 0:
        save_match_cache()


def get_cached_match(name: str, utility_type: str) -> Optional[Dict]:
    """Check if we have a cached match for this name."""
    load_match_cache()
    
    key = f"{normalize_name(name)}|{utility_type}"
    if key in _match_cache:
        cached = _match_cache[key]
        return {
            'id': cached['id'],
            'title': cached['title'],
            'matched_via': 'cached',
            'match_score': 1.0,  # High confidence for cached matches
            'original_cached_name': cached.get('original_name')
        }
    return None


def normalize_name_aggressive(name: str) -> str:
    """More aggressive normalization for fuzzy matching - strips utility type words."""
    name = normalize_name(name)
    if not name:
        return ''
    # Remove utility type words for better fuzzy matching
    utility_words = [
        'electric', 'electricity', 'energy', 'power', 'light',
        'gas', 'natural',
        'water', 'utilities', 'utility', 'services', 'service',
        'cooperative', 'coop',
        'municipal', 'city of', 'town of', 'village of', 'county',
        'public'
    ]
    for word in utility_words:
        name = re.sub(rf'\b{word}\b', '', name, flags=re.IGNORECASE)
    return ' '.join(name.split())


def load_mappings() -> Dict[str, Dict]:
    """Load OpenAI-generated name mappings."""
    global _mappings_cache
    
    if _mappings_cache is not None:
        return _mappings_cache
    
    if os.path.exists(MAPPINGS_FILE):
        with open(MAPPINGS_FILE, 'r') as f:
            _mappings_cache = json.load(f)
        print(f"[ProviderMatcher] Loaded {len(_mappings_cache)} OpenAI mappings")
    else:
        _mappings_cache = {}
    
    return _mappings_cache


def load_simple_lookup() -> Dict[str, Dict]:
    """Load simple normalized name -> ID lookup."""
    global _simple_lookup_cache
    
    if _simple_lookup_cache is not None:
        return _simple_lookup_cache
    
    if os.path.exists(SIMPLE_LOOKUP_FILE):
        with open(SIMPLE_LOOKUP_FILE, 'r') as f:
            _simple_lookup_cache = json.load(f)
        print(f"[ProviderMatcher] Loaded {len(_simple_lookup_cache)} simple lookups")
    else:
        _simple_lookup_cache = {}
    
    return _simple_lookup_cache


def load_canonical_ids() -> Dict[str, Dict[str, int]]:
    """Load canonical provider ID mappings to resolve duplicates."""
    global _canonical_ids_cache
    
    if _canonical_ids_cache is not None:
        return _canonical_ids_cache
    
    if os.path.exists(CANONICAL_IDS_FILE):
        with open(CANONICAL_IDS_FILE, 'r') as f:
            _canonical_ids_cache = json.load(f)
        # Count non-metadata entries
        count = sum(len(v) for k, v in _canonical_ids_cache.items() if not k.startswith('_') and isinstance(v, dict))
        print(f"[ProviderMatcher] Loaded {count} canonical ID mappings")
    else:
        _canonical_ids_cache = {}
    
    return _canonical_ids_cache


def get_canonical_id(name: str, utility_type: str) -> Optional[int]:
    """
    Check if there's a canonical ID for this provider name.
    Used to resolve duplicate provider entries and parent company names.
    """
    canonical = load_canonical_ids()
    
    if utility_type not in canonical:
        return None
    
    type_mappings = canonical[utility_type]
    if not isinstance(type_mappings, dict):
        return None
    
    # Try exact match first
    name_lower = name.lower().strip()
    if name_lower in type_mappings:
        return type_mappings[name_lower]
    
    # Try normalized match
    normalized = normalize_name(name)
    if normalized in type_mappings:
        return type_mappings[normalized]
    
    return None


def load_providers() -> Dict[str, Dict]:
    """Load providers from CSV file."""
    global _providers_cache
    
    if _providers_cache is not None:
        return _providers_cache
    
    csv_path = os.path.join(os.path.dirname(__file__), 'utility_providers_IDs.csv')
    
    if not os.path.exists(csv_path):
        print(f"[ProviderMatcher] CSV not found: {csv_path}")
        _providers_cache = {}
        return _providers_cache
    
    providers = {}
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                provider_id = row.get('ID', '').strip()
                utility_type_id = int(row.get('UtilityTypeId', 0))
                title = row.get('Title', '').strip()
                
                if not provider_id or not title:
                    continue
                
                utility_type = UTILITY_TYPE_MAP.get(utility_type_id, 'unknown')
                normalized = normalize_name(title)
                
                # Key by normalized name + utility type for exact matching
                key = f"{normalized}|{utility_type}"
                
                providers[key] = {
                    'id': provider_id,
                    'title': title,
                    'utility_type': utility_type,
                    'utility_type_id': utility_type_id,
                    'url': row.get('URL', ''),
                    'phone': row.get('Phone', ''),
                    'normalized': normalized
                }
            except Exception as e:
                continue
    
    print(f"[ProviderMatcher] Loaded {len(providers)} providers")
    _providers_cache = providers
    return providers


def match_provider(name: str, utility_type: str) -> Optional[Dict]:
    """
    Match a provider name to an ID using multiple strategies:
    0. Check persistent cache first (instant, high confidence)
    1. OpenAI-generated mappings (best for fuzzy matching like "Oncor" -> "Oncor Electric-TX")
    2. Simple normalized lookup
    3. CSV-based exact match
    4. Partial string matching
    5. Aggressive normalization
    6. OpenAI fallback for matches below 80% confidence
    
    Args:
        name: Provider name from lookup
        utility_type: Type of utility (electric, gas, water, internet)
        
    Returns:
        Dict with provider info including 'id', or None if no match
    """
    if not name:
        return None
    
    normalized = normalize_name(name)
    
    # Strategy 0: Check canonical ID mappings first (resolves duplicates and parent companies)
    canonical_id = get_canonical_id(name, utility_type)
    if canonical_id:
        # Look up the provider details from the canonical ID
        providers = load_providers()
        for key, provider in providers.items():
            if provider.get('id') == str(canonical_id) and provider.get('utility_type') == utility_type:
                return {
                    'id': str(canonical_id),
                    'title': provider.get('title', name),
                    'matched_via': 'canonical_mapping',
                    'match_score': 1.0
                }
        # If not found in providers, still return the canonical ID
        return {
            'id': str(canonical_id),
            'title': name,
            'matched_via': 'canonical_mapping',
            'match_score': 1.0
        }
    
    # Strategy 0.5: Check persistent cache (instant, high confidence)
    cached = get_cached_match(name, utility_type)
    if cached:
        return cached
    
    # Strategy 1: Check OpenAI mappings (best for deduped names)
    mappings = load_mappings()
    if normalized in mappings:
        mapping = mappings[normalized]
        return {
            'id': mapping['id'],
            'title': mapping.get('canonical', mapping.get('original', name)),
            'matched_via': 'openai_mapping'
        }
    
    # Strategy 2: Simple lookup (normalized name -> ID)
    simple = load_simple_lookup()
    if normalized in simple:
        entry = simple[normalized]
        return {
            'id': entry['id'] if isinstance(entry, dict) else entry,
            'title': entry.get('title', name) if isinstance(entry, dict) else name,
            'matched_via': 'simple_lookup'
        }
    
    # Strategy 3: CSV-based exact match with utility type
    providers = load_providers()
    key = f"{normalized}|{utility_type}"
    if key in providers:
        providers[key]['matched_via'] = 'csv_exact'
        return providers[key]
    
    # Try without utility type constraint
    for pkey, pdata in providers.items():
        if pdata['normalized'] == normalized:
            pdata['matched_via'] = 'csv_any_type'
            return pdata
    
    # Strategy 4: Partial matching - provider name contains or is contained
    best_match = None
    best_score = 0
    
    for pkey, pdata in providers.items():
        pnorm = pdata['normalized']
        
        # Skip if utility types don't match
        if pdata['utility_type'] != utility_type:
            continue
        
        # Check if one contains the other
        if normalized in pnorm or pnorm in normalized:
            score = min(len(normalized), len(pnorm)) / max(len(normalized), len(pnorm))
            if score > best_score:
                best_score = score
                best_match = pdata
    
    if best_match and best_score > 0.8:
        # High confidence match - return directly and cache
        best_match['matched_via'] = 'partial'
        best_match['match_score'] = best_score
        cache_match(name, utility_type, best_match)
        return best_match
    
    # Strategy 5: Aggressive normalization matching
    normalized_agg = normalize_name_aggressive(name)
    if normalized_agg and len(normalized_agg) >= 3:
        for pkey, pdata in providers.items():
            if pdata['utility_type'] != utility_type:
                continue
            pnorm_agg = normalize_name_aggressive(pdata['title'])
            if normalized_agg == pnorm_agg:
                pdata['matched_via'] = 'aggressive_exact'
                pdata['match_score'] = 1.0
                cache_match(name, utility_type, pdata)
                return pdata
            # Check containment with aggressive normalization
            if normalized_agg in pnorm_agg or pnorm_agg in normalized_agg:
                score = min(len(normalized_agg), len(pnorm_agg)) / max(len(normalized_agg), len(pnorm_agg))
                if score > best_score:
                    best_score = score
                    best_match = pdata
        
        if best_match and best_score > 0.8:
            # High confidence aggressive match
            best_match['matched_via'] = 'aggressive_partial'
            best_match['match_score'] = best_score
            cache_match(name, utility_type, best_match)
            return best_match
    
    # Strategy 6: OpenAI fallback for matches below 80% confidence
    # This includes any match we found so far with score <= 0.8
    if best_match or len(name) >= 3:
        # Gather candidates for OpenAI
        candidates_for_ai = [best_match] if best_match else None
        ai_match = _openai_match_provider(name, utility_type, candidates_for_ai)
        if ai_match:
            cache_match(name, utility_type, ai_match)
            return ai_match
        
        # If OpenAI didn't help but we have a low-confidence match, return it
        if best_match and best_score > 0.3:
            best_match['matched_via'] = 'low_confidence'
            best_match['match_score'] = best_score
            return best_match
    
    return None


def _openai_match_provider(name: str, utility_type: str, candidates: list = None) -> Optional[Dict]:
    """Use OpenAI to match a provider name when standard matching fails."""
    try:
        import os
        from openai import OpenAI
        
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            return None
        
        client = OpenAI(api_key=api_key)
        
        # Get top candidates from CSV if not provided
        if candidates is None:
            providers = load_providers()
            # Find potential matches
            normalized = normalize_name(name)
            candidates = []
            for pkey, pdata in providers.items():
                if pdata['utility_type'] != utility_type:
                    continue
                # Simple word overlap check
                name_words = set(normalized.split())
                prov_words = set(pdata['normalized'].split())
                if name_words & prov_words:  # Any word overlap
                    candidates.append(pdata)
                    if len(candidates) >= 10:
                        break
        
        if not candidates:
            return None
        
        # Build prompt
        candidate_list = "\n".join([f"{i+1}. {c['title']} (ID: {c['id']})" for i, c in enumerate(candidates[:10])])
        
        prompt = f"""Match this utility provider name to the best candidate from the list.

Provider name to match: "{name}"
Utility type: {utility_type}

Candidates:
{candidate_list}

If one of these candidates is clearly the same company (accounting for name variations, abbreviations, parent companies), return the candidate number (1-{len(candidates[:10])}).
If none match, return 0.

Return ONLY a single number, nothing else."""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=10
        )
        
        result = response.choices[0].message.content.strip()
        try:
            idx = int(result) - 1
            if 0 <= idx < len(candidates):
                match = candidates[idx].copy()
                match['matched_via'] = 'openai'
                match['match_score'] = 0.8  # AI confidence
                return match
        except ValueError:
            pass
        
    except Exception as e:
        print(f"[ProviderMatcher] OpenAI error: {e}")
    
    return None


def get_provider_id(name: str, utility_type: str) -> Optional[str]:
    """
    Get just the provider ID for a name.
    
    Args:
        name: Provider name from lookup
        utility_type: Type of utility
        
    Returns:
        Provider ID string or None
    """
    match = match_provider(name, utility_type)
    return match['id'] if match else None


# Pre-load on import
load_providers()


if __name__ == '__main__':
    # Test matching
    test_cases = [
        ('Austin Energy', 'electric'),
        ('Texas Gas Service', 'gas'),
        ('City of Austin Water', 'water'),
        ('AT&T', 'internet'),
        ('Oncor Electric', 'electric'),
    ]
    
    for name, utype in test_cases:
        result = match_provider(name, utype)
        if result:
            print(f"{name} ({utype}) -> ID: {result['id']}, Title: {result['title']}")
        else:
            print(f"{name} ({utype}) -> No match")
