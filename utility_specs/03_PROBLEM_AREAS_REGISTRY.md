# Problem Areas Registry

## Context

Some ZIPs, counties, and areas are known to be problematic. They may span utility boundaries, have multiple providers, or have unreliable data. We should track these explicitly and adjust confidence accordingly.

## Goal

- Maintain a registry of known problem areas
- Automatically lower confidence when hitting a problem area
- Add notes explaining the issue to users
- Track when areas were last reviewed

## Implementation

### Step 1: Create Problem Areas Data File

Create file: `/data/problem_areas.json`

```json
{
  "_metadata": {
    "last_updated": "2026-01-11",
    "version": "1.0"
  },
  "zip": {
    "78640": {
      "state": "TX",
      "city": "Kyle",
      "utilities_affected": ["gas", "water"],
      "issue": "ZIP spans CenterPoint and Texas Gas Service boundary. Multiple MUDs for water.",
      "recommendation": "Always verify with SERP. Cap confidence at 'high' without user confirmation.",
      "known_correct": {
        "gas": {
          "Kyle city limits": "CenterPoint Energy",
          "Plum Creek": "CenterPoint Energy"
        }
      },
      "last_reviewed": "2026-01-11"
    },
    "78653": {
      "state": "TX",
      "city": "Manor",
      "utilities_affected": ["water", "electric"],
      "issue": "Multiple MUDs, city water, and Oncor/Bluebonnet electric boundary.",
      "recommendation": "Require subdivision name for accurate match.",
      "last_reviewed": "2026-01-11"
    },
    "78610": {
      "state": "TX",
      "city": "Buda",
      "utilities_affected": ["gas"],
      "issue": "ZIP spans CenterPoint and Texas Gas Service boundary.",
      "recommendation": "Verify gas provider with SERP.",
      "last_reviewed": "2026-01-11"
    },
    "75013": {
      "state": "TX",
      "city": "Allen",
      "utilities_affected": ["water"],
      "issue": "City of Allen, North Texas MUD 1, and other MUDs overlap.",
      "recommendation": "Check subdivision for MUD membership.",
      "last_reviewed": "2026-01-11"
    },
    "30004": {
      "state": "GA",
      "city": "Alpharetta",
      "utilities_affected": ["water"],
      "issue": "Multiple water providers: Fulton County, City of Alpharetta, North Fulton.",
      "recommendation": "Verify with city or county.",
      "last_reviewed": "2026-01-11"
    },
    "85286": {
      "state": "AZ",
      "city": "Chandler",
      "utilities_affected": ["electric", "water"],
      "issue": "SRP and APS electric boundary. Multiple water districts.",
      "recommendation": "Use utility company address lookup tools.",
      "last_reviewed": "2026-01-11"
    }
  },
  "county": {
    "Hays|TX": {
      "utilities_affected": ["gas"],
      "issue": "County spans CenterPoint, Texas Gas Service, and propane-only areas.",
      "recommendation": "Do not use county-level gas matching. Require ZIP or address verification.",
      "last_reviewed": "2026-01-11"
    },
    "Williamson|TX": {
      "utilities_affected": ["water", "electric"],
      "issue": "High density of MUDs and WSCs. Oncor/Pedernales boundary.",
      "recommendation": "Check MUD database. Verify electric co-op status.",
      "last_reviewed": "2026-01-11"
    },
    "Maricopa|AZ": {
      "utilities_affected": ["electric", "water"],
      "issue": "SRP/APS boundary runs through county. Dozens of water districts.",
      "recommendation": "Use utility address lookup tools.",
      "last_reviewed": "2026-01-11"
    }
  },
  "state": {
    "FL": {
      "utilities_affected": ["water"],
      "issue": "High CDD density. Most new construction served by CDDs, not cities.",
      "recommendation": "Check CDD database before city water utility.",
      "last_reviewed": "2026-01-11"
    },
    "TX": {
      "utilities_affected": ["water"],
      "issue": "Over 1,200 MUDs statewide. New developments almost always in MUDs.",
      "recommendation": "Check MUD database for addresses in new subdivisions.",
      "last_reviewed": "2026-01-11"
    },
    "CO": {
      "utilities_affected": ["water"],
      "issue": "~1,800 metro districts. Most provide water/sewer in suburbs.",
      "recommendation": "Check DOLA special district database.",
      "last_reviewed": "2026-01-11"
    }
  }
}
```

### Step 2: Create Problem Area Lookup Function

Add to `state_utility_verification.py`:

```python
import json
import os

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
    with open(PROBLEM_AREAS_FILE, 'w') as f:
        json.dump(problem_areas, f, indent=2)
    
    # Invalidate cache
    _problem_areas_cache = None
    
    print(f"Added problem area: {level} {key}")
```

### Step 3: Integrate Into Lookup Functions

In `utility_lookup.py`:

```python
from state_utility_verification import check_problem_area

def lookup_gas_utility(lat, lon, city, county, state, zip_code, verify=True):
    # Check if this is a known problem area
    problem = check_problem_area(zip_code, county, state, 'gas')
    
    if problem['is_problem_area']:
        # Log for tracking
        print(f"Problem area hit: {zip_code} for gas - {problem['issue']}")
        
        # If we have known correct data for this specific context, use it
        if problem.get('known_correct'):
            # Try to match subdivision or area
            # ... matching logic ...
            pass
    
    # ... rest of lookup logic ...
    
    # When building response, include problem area info
    if problem['is_problem_area']:
        result['problem_area_warning'] = problem['issue']
        result['verification_recommendation'] = problem['recommendation']
        # This will be used by confidence scoring to lower the score
```

### Step 4: Add API Endpoint for Managing Problem Areas

In `api.py`:

```python
@app.route('/api/problem-areas', methods=['GET'])
def list_problem_areas():
    """List all known problem areas."""
    problem_areas = load_problem_areas()
    
    # Remove metadata
    result = {k: v for k, v in problem_areas.items() if not k.startswith('_')}
    
    return jsonify(result)


@app.route('/api/problem-areas', methods=['POST'])
def add_problem_area_endpoint():
    """Add a new problem area (internal use)."""
    data = request.get_json()
    
    required = ['level', 'key', 'utilities_affected', 'issue', 'recommendation']
    for field in required:
        if field not in data:
            return jsonify({'error': f'Missing required field: {field}'}), 400
    
    add_problem_area(
        level=data['level'],
        key=data['key'],
        utilities_affected=data['utilities_affected'],
        issue=data['issue'],
        recommendation=data['recommendation'],
        known_correct=data.get('known_correct')
    )
    
    return jsonify({'status': 'added', 'key': data['key']})
```

## Testing

### Test Problem Area Detection
```python
# Test ZIP-level problem area
result = check_problem_area('78640', 'Hays', 'TX', 'gas')
assert result['is_problem_area'] == True
assert result['level'] == 'zip'
assert 'CenterPoint' in result['issue']

# Test non-problem area
result = check_problem_area('75201', 'Dallas', 'TX', 'gas')
assert result['is_problem_area'] == False
```

### Test API Endpoint
```bash
# List problem areas
curl https://web-production-9acc6.up.railway.app/api/problem-areas

# Add new problem area
curl -X POST https://web-production-9acc6.up.railway.app/api/problem-areas \
  -H "Content-Type: application/json" \
  -d '{
    "level": "zip",
    "key": "78666",
    "utilities_affected": ["gas", "water"],
    "issue": "San Marcos area spans multiple utility boundaries",
    "recommendation": "Verify with SERP"
  }'
```

## Commit Message

```
Add problem areas registry for known difficult locations

- problem_areas.json with ZIP, county, state level entries
- check_problem_area() function for lookups
- Integration with confidence scoring
- API endpoints to view and add problem areas
```
