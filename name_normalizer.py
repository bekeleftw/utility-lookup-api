#!/usr/bin/env python3
"""
Normalize utility names to proper human-readable format.
Called at response time before returning to UI.

Uses caching to avoid repeat OAPI calls for the same name.
"""

import os
import re
import json
import hashlib
from pathlib import Path
from typing import Optional

# In-memory cache for session
_name_cache = {}

# Persistent cache file
CACHE_FILE = Path(__file__).parent / 'data' / 'name_normalization_cache.json'

def _load_persistent_cache():
    """Load persistent cache from disk."""
    global _name_cache
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, 'r') as f:
                _name_cache = json.load(f)
        except:
            _name_cache = {}

def _save_persistent_cache():
    """Save cache to disk."""
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(_name_cache, f, indent=2)
    except:
        pass

def _load_openai_key():
    """Load OpenAI API key from environment or .env files."""
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key
    
    # Try .env files
    for env_file in ['.env', '../.env', '~/.env']:
        path = Path(env_file).expanduser()
        if path.exists():
            try:
                with open(path) as f:
                    for line in f:
                        if line.startswith('OPENAI_API_KEY='):
                            return line.split('=', 1)[1].strip().strip('"\'')
            except:
                pass
    return None

def _needs_normalization(name: str) -> bool:
    """Check if a name needs normalization."""
    if not name or len(name) < 3:
        return False
    
    # ALL CAPS (but not short acronyms like "OUC" or "JEA")
    if name.isupper() and len(name) > 5:
        return True
    
    # Inverted city/village/town names
    upper = name.upper()
    if ', CITY OF' in upper or ', VILLAGE OF' in upper or ', TOWN OF' in upper:
        return True
    if ' CITY OF' in upper or ' VILLAGE OF' in upper or ' TOWN OF' in upper:
        return True
    
    # Ends with "CITY" pattern (likely inverted)
    if upper.endswith(' CITY') or upper.endswith(' VILLAGE'):
        return True
    
    return False

def _normalize_local(name: str) -> str:
    """
    Fast local normalization without OAPI.
    Handles common patterns.
    """
    if not name:
        return name
    
    original = name
    
    # Handle inverted names: "HOLLYWOOD, CITY OF" → "City of Hollywood"
    patterns = [
        (r'^(.+),\s*CITY OF$', r'City of \1'),
        (r'^(.+),\s*VILLAGE OF$', r'Village of \1'),
        (r'^(.+),\s*TOWN OF$', r'Town of \1'),
        (r'^(.+)\s+CITY OF$', r'City of \1'),
        (r'^(.+)\s+VILLAGE OF$', r'Village of \1'),
        (r'^(.+)\s+TOWN OF$', r'Town of \1'),
    ]
    
    name_upper = name.upper().strip()
    for pattern, replacement in patterns:
        match = re.match(pattern, name_upper, re.IGNORECASE)
        if match:
            # Extract the place name and format it
            place = match.group(1).strip()
            place = place.title()
            # Apply the replacement pattern
            name = re.sub(pattern, replacement, name_upper, flags=re.IGNORECASE)
            name = name.title()
            break
    
    # If still ALL CAPS, convert to title case
    if name.isupper():
        name = name.title()
    
    # Fix common words that should be lowercase
    for word in [' Of ', ' The ', ' And ', ' For ', ' At ', ' In ']:
        name = name.replace(word, word.lower())
    
    # Fix abbreviations that should stay uppercase
    abbreviations = [
        'Pud', 'Mud', 'Llc', 'Inc', 'Mwc', 'Wsc', 'Wsd', 'Wcid', 'Did',
        'Pws', 'Rws', 'Mwd', 'Wwd', 'Cwd', 'Swd', 'Dwd',
        'Pwa', 'Mua', 'Usa', 'Wsa',
        'Ws', 'Wd', 'Wc',
        'Ii', 'Iii', 'Iv',
        'Llp', 'Lp', 'Co',
        'Ne', 'Nw', 'Se', 'Sw',
    ]
    for abbrev in abbreviations:
        # Match as whole word
        name = re.sub(r'\b' + abbrev + r'\b', abbrev.upper(), name, flags=re.IGNORECASE)
    
    # Handle Mt./St./Ft. - keep period, ensure uppercase
    name = re.sub(r'\bMt\.?\s', 'Mt. ', name, flags=re.IGNORECASE)
    name = re.sub(r'\bSt\.?\s', 'St. ', name, flags=re.IGNORECASE)
    name = re.sub(r'\bFt\.?\s', 'Ft. ', name, flags=re.IGNORECASE)
    
    # Handle N./S./E./W. directionals
    name = re.sub(r'\bN\.?\s', 'N. ', name)
    name = re.sub(r'\bS\.?\s', 'S. ', name)
    name = re.sub(r'\bE\.?\s', 'E. ', name)
    name = re.sub(r'\bW\.?\s', 'W. ', name)
    
    # Clean up extra spaces
    name = re.sub(r'\s+', ' ', name).strip()
    
    return name

def _normalize_with_oapi(name: str) -> Optional[str]:
    """Use OAPI for complex normalization."""
    api_key = _load_openai_key()
    if not api_key:
        return None
    
    try:
        import openai
        client = openai.OpenAI(api_key=api_key)
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """Normalize this utility company name to proper human-readable format.

Rules:
1. Use proper title case (capitalize major words)
2. Fix inverted names: "HOLLYWOOD, CITY OF" → "City of Hollywood"
3. Keep abbreviations uppercase: PUD, MUD, LLC, Inc, MWC, WSC, WSD, WCID, PWS, RWS
4. Keep acronyms that are the actual name: "LADWP", "OUC", "JEA"
5. "City of X" or "Town of X" should come first
6. Remove trailing punctuation except periods in abbreviations

Return ONLY the normalized name."""
                },
                {"role": "user", "content": name}
            ],
            max_tokens=100,
            temperature=0
        )
        
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        print(f"OAPI normalization error: {e}")
        return None

def normalize_utility_name(name: str, use_oapi: bool = True) -> str:
    """
    Normalize a utility name to proper human-readable format.
    
    Args:
        name: Raw utility name
        use_oapi: Whether to use OAPI for complex cases (default True)
    
    Returns:
        Normalized name
    """
    if not name:
        return name
    
    # Check cache first
    cache_key = name.lower().strip()
    if cache_key in _name_cache:
        return _name_cache[cache_key]
    
    # Load persistent cache on first call
    if not _name_cache:
        _load_persistent_cache()
        if cache_key in _name_cache:
            return _name_cache[cache_key]
    
    # Check if normalization is needed
    if not _needs_normalization(name):
        return name
    
    # Try local normalization first
    normalized = _normalize_local(name)
    
    # Use OAPI for complex cases if enabled and local result still looks off
    if use_oapi and _needs_normalization(normalized):
        oapi_result = _normalize_with_oapi(name)
        if oapi_result:
            normalized = oapi_result
    
    # Cache the result
    _name_cache[cache_key] = normalized
    _save_persistent_cache()
    
    return normalized

def normalize_result(result: dict) -> dict:
    """
    Normalize utility names in a lookup result before returning to UI.
    
    Args:
        result: Lookup result dict with 'electric', 'gas', 'water' keys
    
    Returns:
        Result with normalized utility names
    """
    if not result:
        return result
    
    for utility_type in ['electric', 'gas', 'water']:
        if utility_type in result and result[utility_type]:
            entry = result[utility_type]
            if isinstance(entry, dict) and 'name' in entry:
                entry['name'] = normalize_utility_name(entry['name'])
            elif isinstance(entry, list):
                for item in entry:
                    if isinstance(item, dict) and 'name' in item:
                        item['name'] = normalize_utility_name(item['name'])
    
    return result


# Test
if __name__ == '__main__':
    test_names = [
        "HOLLYWOOD, CITY OF",
        "PRESCOTT WATER CITY OF",
        "MENEMSHA WATER COMPANY",
        "SUTTONS BAY, VILLAGE OF",
        "MT. PLEASANT",
        "MDWASA - MAIN SYSTEM",
        "Austin Energy",  # Already good
        "JEA",  # Short acronym, keep as-is
    ]
    
    print("Testing name normalization:")
    for name in test_names:
        normalized = normalize_utility_name(name, use_oapi=False)
        print(f"  {name} → {normalized}")
