# Migration Guide: v1 to v2 Utility Lookup

## Overview

This guide covers migrating from `utility_lookup.py` (v1) to `utility_lookup_v2.py` (v2).

**Key Changes:**
- Single pipeline orchestrator for all utility types
- Simplified code: ~300 lines vs ~3,500 lines
- Unified confidence scoring
- Better water utility support
- User corrections as highest priority source

## Quick Start

### Before (v1)
```python
from utility_lookup import lookup_utilities_by_address

result = lookup_utilities_by_address("123 Main St, Austin, TX 78701")
```

### After (v2)
```python
from utility_lookup_v2 import lookup_utilities_by_address

result = lookup_utilities_by_address("123 Main St, Austin, TX 78701")
```

**The API is identical** - just change the import.

## Response Format

Both v1 and v2 return the same response structure:

```python
{
    "electric": {
        "NAME": "Austin Energy",
        "TELEPHONE": "512-494-9400",
        "WEBSITE": "https://austinenergy.com",
        "STATE": "TX",
        "CITY": "Austin",
        "_confidence": "verified",
        "_confidence_score": 96,
        "_source": "municipal",
        ...
    },
    "gas": { ... },
    "water": { ... }
}
```

### Required Fields (unchanged)
- `NAME` - Utility provider name
- `TELEPHONE` - Contact phone
- `WEBSITE` - Provider website
- `STATE` - State code
- `CITY` - City name

### Metadata Fields (may vary)
- `_confidence` - Confidence level (verified/high/medium/low)
- `_confidence_score` - Numeric score (0-100)
- `_source` - Data source identifier
- `_verification_source` - How result was verified

## Gradual Rollout Strategy

### Step 1: Shadow Mode (Week 1)
Run v2 alongside v1, compare results, don't serve v2 to users.

```python
# In your API handler
from utility_lookup import lookup_utilities_by_address as lookup_v1
from utility_lookup_v2 import lookup_utilities_by_address as lookup_v2

def lookup_handler(address):
    v1_result = lookup_v1(address)
    v2_result = lookup_v2(address)
    
    # Log differences for analysis
    log_comparison(v1_result, v2_result)
    
    # Return v1 result (shadow mode)
    return v1_result
```

### Step 2: A/B Testing (Week 2)
Route 10% of traffic to v2.

```python
import random

def lookup_handler(address):
    if random.random() < 0.10:  # 10% to v2
        return lookup_v2(address)
    return lookup_v1(address)
```

### Step 3: Gradual Increase (Weeks 3-4)
- Week 3: 25% v2
- Week 4: 50% v2
- Week 5: 100% v2

### Step 4: Deprecate v1 (Week 6+)
After 2 weeks at 100% v2 with no issues, remove v1 code.

## Testing Your Migration

### Run Regression Tests
```bash
pytest tests/test_regression_v2.py -v
```

### Run A/B Comparison
```bash
python scripts/ab_test_runner.py --limit 10
```

### Test Specific Address
```bash
python utility_lookup_v2.py "123 Main St, Austin, TX 78701"
```

## Known Differences

### Improved in v2

1. **Little Elm TX 75068**: Now correctly returns CoServ Gas (was Atmos)
2. **Water lookups**: Full pipeline support with 5 sources
3. **Confidence scoring**: More consistent across all utility types

### Behavior Changes

1. **HIFLD sources**: Now store all candidates (not just first)
2. **User corrections**: Highest priority (confidence 99)
3. **Water pipeline**: New sources added (MunicipalWater, StateGIS, etc.)

## Rollback Plan

If issues are discovered:

1. **Immediate**: Change import back to v1
   ```python
   from utility_lookup import lookup_utilities_by_address
   ```

2. **A/B rollback**: Set v2 percentage to 0%

3. **Full rollback**: Revert to pre-refactor tag
   ```bash
   git checkout pre-refactor-baseline
   ```

## Support

- **Logs**: Check `data/ab_tests/` for comparison results
- **Metrics**: Check `data/metrics/` for performance data
- **Issues**: Document in `data/problem_areas.json`

## Files Changed

### New Files
- `utility_lookup_v2.py` - Simplified lookup implementation
- `pipeline/sources/water.py` - Water pipeline sources
- `pipeline/sources/corrections.py` - User corrections source
- `data/texas_territories.json` - Migrated Texas data
- `schemas/*.schema.json` - Data validation schemas

### Modified Files
- `pipeline/sources/gas.py` - HIFLD returns all candidates
- `pipeline/sources/electric.py` - HIFLD returns all candidates
- `pipeline/sources/__init__.py` - Export new sources
- `data/verified_addresses.json` - Added zip_overrides
- `data/county_utility_defaults.json` - Merged gas data

### To Be Deleted (after full migration)
- `utility_lookup.py` (3,464 lines → replaced by 300 lines)
- `state_utility_verification.py` (hardcoded dicts migrated to JSON)
