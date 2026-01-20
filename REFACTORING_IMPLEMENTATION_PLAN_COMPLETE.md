# Utility Lookup System - Complete Refactoring Implementation Plan
## Including Electric, Gas, AND Water

> **UPDATE**: Original plan was gas-only. This version includes ALL utility types.

---

## Quick Wins Completed ✅

### 1. Lower ZIP Mapping Confidence for Gas (Done)
**File:** `pipeline/sources/gas.py` lines 142-149
- Changed confidence from 80 → 50 for "verified" ZIP results
- Changed confidence from 75 → 45 for "high" ZIP results
- Now HIFLD polygons (75) and municipal data (85) win over ZIP mapping

### 2. Add CoServ Gas for Denton County (Done)
**File:** `state_utility_verification.py`
- Added `COSERV` to `TEXAS_GAS_LDCS` dictionary
- Added Denton County ZIPs to `TEXAS_GAS_ZIP_OVERRIDES`
- Test: `get_texas_gas_ldc('75068', 'Little Elm')` → Returns CoServ Gas ✅

---

## Architecture Overview

### Current State: Parallel Architectures

The system has **THREE separate but identical** architectures for electric, gas, and water:

```
ELECTRIC                    GAS                         WATER
─────────────────────────────────────────────────────────────────────────
Priority spaghetti          Priority spaghetti          Priority spaghetti
Multiple lookups            Multiple lookups            Multiple lookups
ZIP prefix mapping (TX)     ZIP prefix mapping (TX)     No ZIP mapping ✅
Municipal database          Municipal database          Municipal database
Pipeline sources:           Pipeline sources:           Pipeline sources:
  - StateGISElectricSource    - StateGISGasSource         - MISSING
  - MunicipalElectricSource   - MunicipalGasSource        - MISSING
  - HIFLDElectricSource       - HIFLDGasSource            - MISSING
  - CoopSource                - ZIPMappingGasSource ❌    - MISSING
  - EIASource                 - CountyDefaultGasSource    - MISSING
  - CountyDefaultElectricSource
```

### Target State: Unified Architecture

```
┌─────────────────────────────────────────────────────────┐
│   lookup_utilities_by_address(address)                  │
│   (Geocode once, query all utilities in parallel)       │
└──────────────┬──────────────────────────────────────────┘
               │
    ┌──────────┼──────────┬──────────┐
    ▼          ▼          ▼          ▼
┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
│Electric │ │   Gas   │ │  Water  │ │Internet │
│Pipeline │ │Pipeline │ │Pipeline │ │ (keep)  │
└─────────┘ └─────────┘ └─────────┘ └─────────┘

Each Pipeline queries same source types:
  1. User Corrections (99)
  2. State GIS APIs (90)
  3. Municipal DB (85)
  4. Co-ops/Special (80)
  5. HIFLD Polygons (75)
  6. County Defaults (40)
```

---

## Scope Expansion: What Changes

### Original Plan (Gas Only)
- Delete `ZIPMappingGasSource`
- Fix `HIFLDGasSource`
- Clean up gas priority logic

### Complete Plan (All Utilities)

| Utility Type | Sources to Add | Sources to Fix | Sources to Delete |
|--------------|----------------|----------------|-------------------|
| **Electric** | UserCorrectionSource | HIFLDElectricSource | (EIASource - maybe keep) |
| **Gas** | UserCorrectionSource | HIFLDGasSource | ZIPMappingGasSource ❌ |
| **Water** | UserCorrectionSource | (Build entire pipeline) | N/A |
|  | WaterPipelineSources | StateGISWaterSource | |
|  | | MunicipalWaterSource | |
|  | | HIFLDWaterSource | |

### Additional Work Required

**New for Water:**
- Create `pipeline/sources/water.py` (similar to gas.py)
- Implement 5 water sources (User, StateGIS, Municipal, HIFLD, County)
- Migrate water lookup priority logic to pipeline

**Electric Expansion:**
- Add deregulation handling to pipeline (TX, OH, PA, etc.)
- Fix TDU ZIP mapping (same problem as gas)
- Handle co-ops correctly (already has CoopSource)

**Cross-Cutting:**
- Unified `UserCorrectionSource` for all types
- Consistent confidence scoring across types
- Parallel query optimization

---

## Phase 0: Pre-Refactor Preparation (Week 0)

### Goal
Establish baseline, monitoring, and safety nets before making changes.

### Tasks

#### 0.1 Baseline Metrics
```bash
# Capture current performance
python scripts/benchmark_current.py > baseline_metrics.txt
```

**Metrics to capture:**
- Lookup latency (p50, p95, p99) for each utility type
- Current error rate (from logs or user reports)
- OpenAI API cost per lookup
- Lines of code per file

#### 0.2 Create Comprehensive Test Suite
```python
# tests/test_current_behavior.py
"""
Snapshot tests - capture CURRENT behavior before refactoring.
Any changes in behavior after refactor need to be intentional.
"""
SNAPSHOT_ADDRESSES = [
    "1401 Thrasher Dr, Little Elm, TX 75068",  # Gas: CoServ
    "123 S 2nd St, Yakima, WA 98901",          # Water: Yakima WD
    "500 Pearl St, Austin, TX 78701",          # Electric: Austin Energy
    # ... 100+ addresses covering all states
]

def test_snapshot_all():
    """Capture current results for regression testing."""
    results = {}
    for addr in SNAPSHOT_ADDRESSES:
        results[addr] = lookup_utilities_by_address(addr)

    with open('tests/snapshots/current_behavior.json', 'w') as f:
        json.dump(results, f, indent=2)
```

#### 0.3 Set Up Monitoring
```python
# monitoring/metrics.py
def track_lookup(utility_type: str, result: dict, latency: float):
    """Send metrics to monitoring system."""
    metrics.increment(f'utility_lookup.{utility_type}.count')
    metrics.histogram(f'utility_lookup.{utility_type}.latency', latency)
    metrics.gauge(f'utility_lookup.{utility_type}.confidence',
                  result.get('_confidence_score', 0))

    if result.get('_source') == 'user_corrections':
        metrics.increment(f'utility_lookup.{utility_type}.source.user_corrections')
```

#### 0.4 Document External Dependencies
```markdown
# docs/external_dependencies.md

## Systems That Call This API
1. **Web App** - Main user-facing site
   - Endpoint: /api/lookup
   - Expected format: { electric: {NAME, PHONE}, gas: {...}, water: {...} }
   - SLA: < 3s response time

2. **Mobile App** - iOS/Android
   - Same as web app
   - Critical: Must maintain exact JSON structure

3. **Partner Integrations**
   - RealEstate.com API
   - Contract: JSON schema v1.2
```

### Deliverables
- [ ] Baseline metrics captured (latency, error rate, cost)
- [ ] Snapshot tests for 100+ addresses
- [ ] Monitoring/alerting configured
- [ ] External dependencies documented
- [ ] Git tag: `pre-refactor-baseline`

---

## Phase 1: Data Consolidation (Week 1-2)

### Goal
Single source of truth. No hardcoded dicts. Schema validation.

### Tasks

#### 1.1 Audit Current Data Files

```bash
# Generate data file inventory
find data/ -name "*.json" -exec sh -c 'echo "{}:"; wc -l {}; jq "keys" {} | head -5' \;
```

**Current state (51 files):**
```
data/municipal_utilities.json           682 lines   ✅ KEEP
data/verified_addresses.json            123 lines   ✅ KEEP
data/county_utility_defaults.json       234 lines   ✅ KEEP
data/gas_county_lookups.json            156 lines   ❌ MERGE into county_defaults
data/electric_cooperatives_supplemental 423 lines   ❌ MERGE into municipal_utilities
data/deregulated_markets.json           89 lines    ✅ KEEP
data/problem_areas.json                 45 lines    ✅ KEEP
... 44 more files to review
```

#### 1.2 Merge Overlapping Data Files

**Task 1.2.1: Merge Gas County Data**
```python
# scripts/merge_data.py
def merge_gas_county_data():
    """Merge gas_county_lookups.json into county_utility_defaults.json"""
    with open('data/county_utility_defaults.json') as f:
        county_defaults = json.load(f)

    with open('data/gas_county_lookups.json') as f:
        gas_lookups = json.load(f)

    # Merge gas data into county_defaults
    for state, counties in gas_lookups.items():
        if state not in county_defaults:
            county_defaults[state] = {}
        for county, data in counties.items():
            if county not in county_defaults[state]:
                county_defaults[state][county] = {}
            county_defaults[state][county]['gas'] = data

    with open('data/county_utility_defaults.json', 'w') as f:
        json.dump(county_defaults, f, indent=2)

    print("✅ Merged gas_county_lookups.json → county_utility_defaults.json")
```

**Task 1.2.2: Merge Co-op Data**
```python
def merge_coop_data():
    """Merge electric_cooperatives_supplemental into municipal_utilities"""
    # Similar merge logic
    # Co-ops go into municipal_utilities['electric'][state][city]
```

#### 1.3 Migrate Hardcoded Python Dicts to JSON

**Current hardcoded dicts to migrate:**

| Dict | Lines | File | Migrate To |
|------|-------|------|------------|
| `TEXAS_GAS_ZIP_PREFIX` | 691-714 | state_utility_verification.py | `data/texas_territories.json` |
| `TEXAS_GAS_ZIP_OVERRIDES` | 718-726 | state_utility_verification.py | `data/texas_territories.json` |
| `GAS_ZIP_OVERRIDES` | 734-780 | state_utility_verification.py | `data/verified_addresses.json` |
| `TEXAS_ZIP_PREFIX_TO_TDU` | 180-268 | state_utility_verification.py | `data/texas_territories.json` |
| `TEXAS_TDUS` | 139-175 | state_utility_verification.py | `data/texas_territories.json` |

**Migration script:**
```python
# scripts/migrate_hardcoded_dicts.py
def migrate_texas_territories():
    """
    Migrate all Texas hardcoded dicts to single JSON file.
    """
    texas_territories = {
        "electric": {
            "zip_to_tdu": {},  # From TEXAS_ZIP_PREFIX_TO_TDU
            "tdus": {},        # From TEXAS_TDUS
            "overrides": {}    # 5-digit ZIP overrides
        },
        "gas": {
            "zip_to_ldc": {},  # From TEXAS_GAS_ZIP_PREFIX
            "ldcs": {},        # From TEXAS_GAS_LDCS
            "overrides": {}    # From TEXAS_GAS_ZIP_OVERRIDES
        }
    }

    # Copy data from Python dicts (imported from state_utility_verification)
    from state_utility_verification import (
        TEXAS_ZIP_PREFIX_TO_TDU,
        TEXAS_TDUS,
        TEXAS_GAS_ZIP_PREFIX,
        TEXAS_GAS_LDCS,
        TEXAS_GAS_ZIP_OVERRIDES
    )

    texas_territories['electric']['zip_to_tdu'] = TEXAS_ZIP_PREFIX_TO_TDU
    texas_territories['electric']['tdus'] = TEXAS_TDUS
    texas_territories['gas']['zip_to_ldc'] = TEXAS_GAS_ZIP_PREFIX
    texas_territories['gas']['ldcs'] = TEXAS_GAS_LDCS
    texas_territories['gas']['overrides'] = TEXAS_GAS_ZIP_OVERRIDES

    with open('data/texas_territories.json', 'w') as f:
        json.dump(texas_territories, f, indent=2)

    print("✅ Created data/texas_territories.json")
```

**Add backward-compatible loader:**
```python
# state_utility_verification.py (during migration)
_TEXAS_TERRITORIES = None

def _load_texas_territories():
    """Load from JSON, fall back to hardcoded during migration."""
    global _TEXAS_TERRITORIES
    if _TEXAS_TERRITORIES is None:
        try:
            with open('data/texas_territories.json') as f:
                _TEXAS_TERRITORIES = json.load(f)
        except FileNotFoundError:
            # Fallback to hardcoded during migration
            _TEXAS_TERRITORIES = {
                'gas': {
                    'zip_to_ldc': TEXAS_GAS_ZIP_PREFIX,
                    'ldcs': TEXAS_GAS_LDCS,
                    'overrides': TEXAS_GAS_ZIP_OVERRIDES
                }
            }
    return _TEXAS_TERRITORIES

# Update all references
# OLD: if zip_prefix in TEXAS_GAS_ZIP_PREFIX:
# NEW: territories = _load_texas_territories()
#      if zip_prefix in territories['gas']['zip_to_ldc']:
```

#### 1.4 Create JSON Schemas

**Create schemas directory:**
```bash
mkdir -p schemas
```

**Schema 1: Municipal Utilities**
```json
// schemas/municipal_utilities.schema.json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Municipal Utilities Database",
  "type": "object",
  "properties": {
    "electric": { "$ref": "#/definitions/utilityMap" },
    "gas": { "$ref": "#/definitions/utilityMap" },
    "water": { "$ref": "#/definitions/utilityMap" }
  },
  "definitions": {
    "utilityMap": {
      "type": "object",
      "additionalProperties": {
        "type": "object",
        "description": "State code (TX, CA, etc.)",
        "additionalProperties": {
          "type": "object",
          "description": "City name",
          "required": ["name"],
          "properties": {
            "name": { "type": "string" },
            "phone": { "type": "string", "pattern": "^[0-9\\-\\(\\) ]+$" },
            "website": { "type": "string", "format": "uri" },
            "zip_codes": {
              "type": "array",
              "items": { "type": "string", "pattern": "^[0-9]{5}$" }
            },
            "services": {
              "type": "array",
              "items": { "enum": ["electric", "gas", "water"] }
            },
            "note": { "type": "string" }
          }
        }
      }
    }
  }
}
```

**Schema 2: Verified Addresses**
```json
// schemas/verified_addresses.schema.json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "User-Verified Utility Corrections",
  "type": "object",
  "properties": {
    "corrections": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["address", "utility_type", "provider_name", "verified_date"],
        "properties": {
          "address": { "type": "string" },
          "zip_code": { "type": "string", "pattern": "^[0-9]{5}$" },
          "utility_type": { "enum": ["electric", "gas", "water"] },
          "provider_name": { "type": "string" },
          "phone": { "type": "string" },
          "website": { "type": "string", "format": "uri" },
          "verified_date": { "type": "string", "format": "date" },
          "verified_by": { "enum": ["user_report", "tenant", "resident", "manual_check"] },
          "confidence": { "type": "integer", "minimum": 1, "maximum": 100 },
          "notes": { "type": "string" }
        }
      }
    }
  }
}
```

**Schema 3: County Defaults**
```json
// schemas/county_defaults.schema.json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "County-Level Default Utilities",
  "type": "object",
  "additionalProperties": {
    "type": "object",
    "description": "State code",
    "additionalProperties": {
      "type": "object",
      "description": "County name",
      "properties": {
        "electric": { "$ref": "#/definitions/utility" },
        "gas": { "$ref": "#/definitions/utility" },
        "water": { "$ref": "#/definitions/utility" }
      }
    }
  },
  "definitions": {
    "utility": {
      "type": "object",
      "required": ["name"],
      "properties": {
        "name": { "type": "string" },
        "phone": { "type": "string" },
        "website": { "type": "string", "format": "uri" },
        "confidence": { "enum": ["low", "medium", "high"] }
      }
    }
  }
}
```

#### 1.5 Validation Script + CI Integration

**Validation script:**
```python
# scripts/validate_data.py
import json
import jsonschema
from pathlib import Path

def validate_all():
    """Validate all data files against schemas."""
    schemas_dir = Path("schemas")
    data_dir = Path("data")

    errors = []

    for schema_file in schemas_dir.glob("*.schema.json"):
        # Get corresponding data file
        data_file_name = schema_file.stem.replace(".schema", "") + ".json"
        data_file = data_dir / data_file_name

        if not data_file.exists():
            print(f"⚠️  No data file for schema: {schema_file.name}")
            continue

        # Load and validate
        with open(schema_file) as f:
            schema = json.load(f)

        with open(data_file) as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                errors.append(f"❌ {data_file.name}: Invalid JSON - {e}")
                continue

        try:
            jsonschema.validate(data, schema)
            print(f"✅ {data_file.name} - Valid")
        except jsonschema.ValidationError as e:
            errors.append(f"❌ {data_file.name}: {e.message} at {e.json_path}")

    if errors:
        print("\n=== VALIDATION ERRORS ===")
        for error in errors:
            print(error)
        return False

    print("\n✅ All data files valid!")
    return True

if __name__ == "__main__":
    import sys
    sys.exit(0 if validate_all() else 1)
```

**CI Integration (GitHub Actions):**
```yaml
# .github/workflows/validate-data.yml
name: Validate Data Files

on:
  push:
    paths:
      - 'data/**'
      - 'schemas/**'
  pull_request:
    paths:
      - 'data/**'
      - 'schemas/**'

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.9'

      - name: Install dependencies
        run: pip install jsonschema

      - name: Validate data files
        run: python scripts/validate_data.py
```

### Deliverables
- [ ] Data file audit complete
- [ ] Redundant files merged
- [ ] Hardcoded dicts migrated to `data/texas_territories.json`
- [ ] 3 JSON schemas created
- [ ] Validation script passing
- [ ] CI integration configured
- [ ] **Result:** 51 files → ~10 core files

---

## Phase 2: Simplify Lookup Logic (Week 3-4)

### Goal
Pipeline is the ONLY orchestrator for ALL utility types.

### Tasks

#### 2.1 Create Unified Entry Point

**New file: `utility_lookup_v2.py`**
```python
"""
Simplified utility lookup - Pipeline orchestrates ALL utilities.

This replaces the 3,464-line utility_lookup.py with clean, simple logic.
"""
from typing import Optional, Dict, List
from pipeline.pipeline import LookupPipeline
from pipeline.interfaces import LookupContext, UtilityType
from geocoding import geocode_address

def lookup_utilities_by_address(
    address: str,
    selected_utilities: Optional[List[str]] = None,
    use_pipeline: bool = True
) -> Optional[Dict]:
    """
    Main entry point for utility lookups.

    Args:
        address: Full street address
        selected_utilities: List of utility types to look up.
                          Default: ['electric', 'gas', 'water']
        use_pipeline: Must be True in v2 (kept for API compatibility)

    Returns:
        Dict with electric, gas, water utility info

    Example:
        >>> lookup_utilities_by_address("123 Main St, Austin, TX 78701")
        {
            "electric": {"NAME": "Austin Energy", "_confidence": 90, ...},
            "gas": {"NAME": "Texas Gas Service", "_confidence": 85, ...},
            "water": {"NAME": "Austin Water", "_confidence": 90, ...}
        }
    """
    # Default to all utilities
    if selected_utilities is None:
        selected_utilities = ['electric', 'gas', 'water']

    # Step 1: Geocode address (once for all utilities)
    geo = geocode_address(address, include_geography=True)
    if not geo:
        return {
            "error": "Could not geocode address",
            "address": address
        }

    # Step 2: Create shared context
    base_context = {
        'lat': geo['lat'],
        'lon': geo['lon'],
        'address': address,
        'city': geo.get('city'),
        'county': geo.get('county'),
        'state': geo.get('state'),
        'zip_code': geo.get('zip') or geo.get('zip_code')
    }

    # Step 3: Query each utility type via pipeline
    results = {}
    pipeline = LookupPipeline()

    # Map utility names to enum types
    type_map = {
        'electric': UtilityType.ELECTRIC,
        'gas': UtilityType.GAS,
        'water': UtilityType.WATER
    }

    for utility_name in selected_utilities:
        if utility_name not in type_map:
            continue

        # Create context for this utility type (don't mutate)
        context = LookupContext(
            **base_context,
            utility_type=type_map[utility_name]
        )

        # Pipeline handles everything
        result = pipeline.lookup(context)

        if result and result.utility_name:
            results[utility_name] = {
                'NAME': result.utility_name,
                'TELEPHONE': result.phone,
                'WEBSITE': result.website,
                'STATE': base_context['state'],
                'CITY': base_context['city'],
                '_confidence': result.confidence_level,
                '_confidence_score': result.confidence_score,
                '_source': result.source,
                '_verification_source': result.source,
                '_selection_reason': result.selection_reason,
                '_sources_consulted': list(result.sources_consulted.keys()) if hasattr(result, 'sources_consulted') else [],
                '_agreeing_sources': result.agreeing_sources if hasattr(result, 'agreeing_sources') else [],
                '_disagreeing_sources': result.disagreeing_sources if hasattr(result, 'disagreeing_sources') else []
            }
        else:
            # No result found
            results[utility_name] = None

    return results


# Maintain backward compatibility
def lookup_water_only(lat: float, lon: float, city: str, county: str,
                      state: str, zip_code: str, address: str = None) -> Optional[Dict]:
    """Legacy function - redirects to v2 pipeline."""
    if not address:
        address = f"{city}, {state} {zip_code}"

    result = lookup_utilities_by_address(address, selected_utilities=['water'])
    return result.get('water') if result else None


def lookup_electric_only(lat: float, lon: float, city: str, county: str,
                        state: str, zip_code: str, address: str = None,
                        use_pipeline: bool = True) -> Optional[Dict]:
    """Legacy function - redirects to v2 pipeline."""
    if not address:
        address = f"{city}, {state} {zip_code}"

    result = lookup_utilities_by_address(address, selected_utilities=['electric'])
    return result.get('electric') if result else None


def lookup_gas_only(lat: float, lon: float, city: str, county: str,
                   state: str, zip_code: str, address: str = None,
                   use_pipeline: bool = True) -> Optional[Dict]:
    """Legacy function - redirects to v2 pipeline."""
    if not address:
        address = f"{city}, {state} {zip_code}"

    result = lookup_utilities_by_address(address, selected_utilities=['gas'])
    return result.get('gas') if result else None
```

**Key improvements:**
- 200 lines vs 3,464 lines
- Single execution path (no priority spaghetti)
- Geocode once, use for all utilities
- Pipeline orchestrates everything
- Legacy functions for backward compatibility

#### 2.2 A/B Testing Infrastructure

**Update main API handler:**
```python
# api/handlers.py
import random
from utility_lookup import lookup_utilities_by_address as lookup_v1
from utility_lookup_v2 import lookup_utilities_by_address as lookup_v2

def lookup_handler(request):
    """
    Main API endpoint with A/B testing.
    """
    address = request.get('address')

    # A/B split: 10% v2, 90% v1
    use_v2 = random.random() < 0.10

    if use_v2:
        result = lookup_v2(address)
        result['_version'] = 'v2'
        log_ab_test('v2', address, result)
    else:
        result = lookup_v1(address)
        result['_version'] = 'v1'
        log_ab_test('v1', address, result)

    return result

def log_ab_test(version: str, address: str, result: dict):
    """Log A/B test results for analysis."""
    metrics.increment(f'api.lookup.version.{version}')
    # Store in database for comparison
    db.ab_tests.insert({
        'version': version,
        'address': address,
        'electric': result.get('electric', {}).get('NAME'),
        'gas': result.get('gas', {}).get('NAME'),
        'water': result.get('water', {}).get('NAME'),
        'timestamp': datetime.now()
    })
```

#### 2.3 Remove Duplicate Lookups

**Current v1 code has these duplicates:**

```python
# utility_lookup.py - BEFORE (duplicates marked)
def lookup_utilities_by_address(address):
    # GAS LOOKUPS
    if 'gas' in selected_utilities:
        # ❌ DUPLICATE 1: Municipal gas at PRIORITY 1
        if (municipal_gas := lookup_municipal_gas(state, city, zip_code)):
            primary_gas = municipal_gas

        # Pipeline at PRIORITY 2
        elif use_pipeline and PIPELINE_AVAILABLE:
            pipeline_result = _pipeline_lookup(..., 'gas')
            primary_gas = pipeline_result

        # ❌ DUPLICATE 2: Municipal gas AGAIN at PRIORITY 3
        if primary_gas is None and (municipal_gas := lookup_municipal_gas(state, city, zip_code)):
            primary_gas = municipal_gas

        # HIFLD + verification
        if primary_gas is None:
            gas = lookup_gas_utility(lon, lat, state=state)
            # ❌ DUPLICATE 3: verify_gas_provider calls get_texas_gas_ldc()
            gas_verification = verify_gas_provider(state, zip_code, city, county, gas)
            primary_gas = gas_verification.get("primary")
```

**v2 code (no duplicates):**
```python
# utility_lookup_v2.py - AFTER (each source called once)
def lookup_utilities_by_address(address):
    # Pipeline queries each source ONCE
    result = pipeline.lookup(context)
    # Done. No post-processing, no verification layer.
```

#### 2.4 Delete Verification Layer

**Files to modify:**

1. **Delete from `utility_lookup.py` (old v1):**
   - Lines 2284-2318: `verify_gas_provider()` call after pipeline
   - Lines 2198-2232: `verify_electric_provider()` call after pipeline
   - Similar blocks for water

2. **Keep `state_utility_verification.py` for now:**
   - Used by pipeline sources temporarily
   - Will delete in Phase 3 after migrating logic to sources

**Why delete verification layer:**
- Pipeline Smart Selector already resolves conflicts
- Verification was overriding pipeline decisions (defeats the purpose!)
- Creates circular logic: Pipeline → Verification → calls same sources again

### Deliverables
- [ ] `utility_lookup_v2.py` created (< 300 lines)
- [ ] A/B test infrastructure deployed
- [ ] Duplicate lookups eliminated in v2
- [ ] Verification layer bypassed in v2
- [ ] Legacy compatibility functions added

---

## Phase 3: Refactor Data Sources (Week 5-7)

### Goal
Clean, modular sources for ALL utility types. Delete broken sources.

### Tasks

#### 3.1 Build Water Pipeline Sources

**NEW FILE: `pipeline/sources/water.py`**

```python
"""
Water utility data source implementations.
"""
from typing import List, Optional
from pipeline.interfaces import (
    DataSource,
    UtilityType,
    LookupContext,
    SourceResult,
    SOURCE_CONFIDENCE,
)


class StateGISWaterSource(DataSource):
    """Query state-specific GIS APIs for water utilities."""

    # States with water GIS APIs (from gis_utility_lookup.py line 461)
    SUPPORTED_STATES = {'CA', 'TX', 'MS', 'PA', 'NY', 'NJ', 'WA', 'UT',
                       'TN', 'NC', 'NM', 'OK', 'AZ', 'CT', 'DE', 'AR', 'KS', 'FL'}

    @property
    def name(self) -> str:
        return "state_gis_water"

    @property
    def supported_types(self) -> List[UtilityType]:
        return [UtilityType.WATER]

    @property
    def base_confidence(self) -> int:
        return SOURCE_CONFIDENCE.get('state_gis', 90)

    def query(self, context: LookupContext) -> Optional[SourceResult]:
        if context.state not in self.SUPPORTED_STATES:
            return None

        if not context.lat or not context.lon:
            return None

        try:
            from gis_utility_lookup import lookup_water_utility_gis

            result = lookup_water_utility_gis(context.lat, context.lon, context.state)

            if not result or not result.get('name'):
                return None

            return SourceResult(
                source_name=self.name,
                utility_name=result.get('name'),
                confidence_score=self.base_confidence,
                match_type='point',
                phone=result.get('phone'),
                website=result.get('website'),
                raw_data=result
            )
        except Exception as e:
            return SourceResult(
                source_name=self.name,
                utility_name=None,
                confidence_score=0,
                match_type='none',
                error=str(e)
            )


class MunicipalWaterSource(DataSource):
    """Look up municipal water utilities from database."""

    @property
    def name(self) -> str:
        return "municipal_water"

    @property
    def supported_types(self) -> List[UtilityType]:
        return [UtilityType.WATER]

    @property
    def base_confidence(self) -> int:
        return SOURCE_CONFIDENCE.get('municipal_utility', 85)

    def query(self, context: LookupContext) -> Optional[SourceResult]:
        try:
            from utility_lookup import lookup_municipal_water

            result = lookup_municipal_water(context.state, context.city, context.zip_code)

            if not result or not result.get('name'):
                return None

            return SourceResult(
                source_name=self.name,
                utility_name=result.get('name'),
                confidence_score=self.base_confidence,
                match_type='city',
                phone=result.get('phone'),
                website=result.get('website'),
                raw_data=result
            )
        except Exception as e:
            return SourceResult(
                source_name=self.name,
                utility_name=None,
                confidence_score=0,
                match_type='none',
                error=str(e)
            )


class EPAWaterSource(DataSource):
    """Look up water from EPA SDWIS database."""

    @property
    def name(self) -> str:
        return "epa_sdwis"

    @property
    def supported_types(self) -> List[UtilityType]:
        return [UtilityType.WATER]

    @property
    def base_confidence(self) -> int:
        return 65  # Lower than state GIS/municipal

    def query(self, context: LookupContext) -> Optional[SourceResult]:
        try:
            from utility_lookup import lookup_water_utility

            result = lookup_water_utility(
                context.city,
                context.county,
                context.state,
                full_address=context.address
            )

            if not result or not result.get('name'):
                return None

            return SourceResult(
                source_name=self.name,
                utility_name=result.get('name'),
                confidence_score=self.base_confidence,
                match_type='city',
                phone=result.get('phone'),
                raw_data=result
            )
        except Exception as e:
            return SourceResult(
                source_name=self.name,
                utility_name=None,
                confidence_score=0,
                match_type='none',
                error=str(e)
            )


class HIFLDWaterSource(DataSource):
    """Query HIFLD water service area boundaries."""

    @property
    def name(self) -> str:
        return "hifld_water"

    @property
    def supported_types(self) -> List[UtilityType]:
        return [UtilityType.WATER]

    @property
    def base_confidence(self) -> int:
        return 70

    def query(self, context: LookupContext) -> Optional[SourceResult]:
        if not context.lat or not context.lon:
            return None

        try:
            from gis_utility_lookup import query_epa_water_service_area

            result = query_epa_water_service_area(context.lat, context.lon)

            if not result or not result.get('name'):
                return None

            return SourceResult(
                source_name=self.name,
                utility_name=result.get('name'),
                confidence_score=self.base_confidence,
                match_type='polygon',
                phone=result.get('phone'),
                raw_data=result
            )
        except Exception as e:
            return SourceResult(
                source_name=self.name,
                utility_name=None,
                confidence_score=0,
                match_type='none',
                error=str(e)
            )
```

**Register water sources in pipeline:**
```python
# pipeline/pipeline.py
from pipeline.sources.water import (
    StateGISWaterSource,
    MunicipalWaterSource,
    EPAWaterSource,
    HIFLDWaterSource
)

class LookupPipeline:
    def __init__(self):
        self.sources = {
            UtilityType.WATER: [
                UserCorrectionSource(),      # Confidence: 99
                StateGISWaterSource(),        # Confidence: 90
                MunicipalWaterSource(),       # Confidence: 85
                HIFLDWaterSource(),          # Confidence: 70
                EPAWaterSource(),            # Confidence: 65
            ],
            # ... electric and gas sources
        }
```

#### 3.2 Delete ZIP Mapping Sources

**DELETE ENTIRELY:**

1. **Gas ZIP Mapping** (pipeline/sources/gas.py lines 116-165)
   ```python
   # DELETE THIS CLASS
   class ZIPMappingGasSource(DataSource):
       """DEPRECATED - ZIP prefixes too coarse for metro areas."""
       pass
   ```

2. **Remove from pipeline registration** (pipeline/pipeline.py)
   ```python
   # OLD:
   UtilityType.GAS: [
       StateGISGasSource(),
       MunicipalGasSource(),
       ZIPMappingGasSource(),  # ❌ DELETE THIS LINE
       HIFLDGasSource(),
       CountyDefaultGasSource(),
   ]

   # NEW:
   UtilityType.GAS: [
       UserCorrectionSource(),
       StateGISGasSource(),
       MunicipalGasSource(),
       HIFLDGasSource(),
       CountyDefaultGasSource(),
   ]
   ```

**Why delete:**
- 3-digit ZIP prefixes can't distinguish providers in same metro
- Example: 750xx covers both Atmos (Dallas) and CoServ (Denton County)
- Causes systematic errors, requires endless manual overrides
- HIFLD polygons are more accurate (actual geographic boundaries)

#### 3.3 Fix HIFLD Sources to Return Multiple Candidates

**Problem:** Current code picks first result, which may be wrong.

**Fix for Gas:**
```python
# pipeline/sources/gas.py - HIFLDGasSource.query()

# OLD (lines 196-212):
if isinstance(result, list):
    primary = result[0] if result else None  # ❌ Blindly takes first
else:
    primary = result

if not primary or not primary.get('NAME'):
    return None

return SourceResult(
    source_name=self.name,
    utility_name=primary.get('NAME'),  # ❌ Only returns one
    confidence_score=self.base_confidence,
    ...
)

# NEW:
# Return ALL candidates, let Smart Selector choose
candidates = result if isinstance(result, list) else [result] if result else []

if not candidates:
    return None

# Don't pick one - return all options
return SourceResult(
    source_name=self.name,
    utility_name=None,  # ⚠️ Interface change needed
    confidence_score=self.base_confidence,
    match_type='polygon',
    candidates=[{
        'name': c.get('NAME'),
        'phone': c.get('TELEPHONE'),
        'website': c.get('WEBSITE'),
        'distance': c.get('_distance', 0)
    } for c in candidates],
    raw_data=result
)
```

**⚠️ INTERFACE CHANGE REQUIRED:**

This requires updating `SourceResult` to support multiple candidates:

```python
# pipeline/interfaces.py

@dataclass
class SourceResult:
    source_name: str
    utility_name: Optional[str]  # Single result
    confidence_score: int
    match_type: str  # 'point', 'polygon', 'zip', 'city', 'county'
    phone: Optional[str] = None
    website: Optional[str] = None
    raw_data: Optional[dict] = None
    error: Optional[str] = None

    # NEW: Support multiple candidates
    candidates: Optional[List[dict]] = None  # List of {name, phone, website, distance}
```

**Update Smart Selector to handle candidates:**

```python
# pipeline/smart_selector.py

def select_best_result(self, source_results: List[SourceResult]) -> str:
    """
    Use OpenAI to select best utility from multiple sources.
    Now handles sources that return multiple candidates.
    """
    # Flatten candidates from all sources
    all_options = []

    for result in source_results:
        if result.candidates:
            # Source returned multiple candidates
            for candidate in result.candidates:
                all_options.append({
                    'name': candidate['name'],
                    'source': result.source_name,
                    'confidence': result.confidence_score,
                    'distance': candidate.get('distance', 0)
                })
        elif result.utility_name:
            # Source returned single result
            all_options.append({
                'name': result.utility_name,
                'source': result.source_name,
                'confidence': result.confidence_score
            })

    # OpenAI picks best from all options
    return self._query_openai(all_options, context)
```

**Apply same fix to Electric and Water HIFLD sources.**

#### 3.4 Add Unified UserCorrectionSource

**NEW FILE: `pipeline/sources/corrections.py`**

```python
"""
User-reported corrections - highest priority source.
Works for ALL utility types.
"""
import json
from typing import List, Optional
from pathlib import Path
from pipeline.interfaces import (
    DataSource,
    UtilityType,
    LookupContext,
    SourceResult,
    SOURCE_CONFIDENCE,
)


class UserCorrectionSource(DataSource):
    """
    User-reported corrections from verified_addresses.json.

    Highest priority - ground truth from actual tenants/residents.
    Works for electric, gas, and water.
    """

    @property
    def name(self) -> str:
        return "user_corrections"

    @property
    def supported_types(self) -> List[UtilityType]:
        return [UtilityType.ELECTRIC, UtilityType.GAS, UtilityType.WATER]

    @property
    def base_confidence(self) -> int:
        return SOURCE_CONFIDENCE.get('user_corrections', 99)

    def query(self, context: LookupContext) -> Optional[SourceResult]:
        """
        Check verified addresses database for user corrections.

        Priority:
        1. Exact address match
        2. ZIP-level override
        """
        corrections = self._load_corrections()

        # Try exact address match
        address_key = self._normalize_address(context.address)
        if address_key in corrections.get('addresses', {}):
            match = corrections['addresses'][address_key]
            if context.utility_type.value in match:
                return self._build_result(
                    match[context.utility_type.value],
                    'exact_address'
                )

        # Try ZIP-level override
        if context.zip_code in corrections.get('zip_overrides', {}):
            zip_data = corrections['zip_overrides'][context.zip_code]
            if context.utility_type.value in zip_data:
                return self._build_result(
                    zip_data[context.utility_type.value],
                    'zip_override'
                )

        return None

    def _load_corrections(self) -> dict:
        """Load verified addresses from JSON."""
        try:
            path = Path(__file__).parent.parent.parent / 'data' / 'verified_addresses.json'
            with open(path) as f:
                return json.load(f)
        except FileNotFoundError:
            return {'addresses': {}, 'zip_overrides': {}}

    def _normalize_address(self, address: str) -> str:
        """Normalize address for matching."""
        return address.lower().strip()

    def _build_result(self, data: dict, match_type: str) -> SourceResult:
        """Build SourceResult from correction data."""
        return SourceResult(
            source_name=self.name,
            utility_name=data.get('name'),
            confidence_score=self.base_confidence,
            match_type=match_type,
            phone=data.get('phone'),
            website=data.get('website'),
            raw_data=data
        )
```

**Update verified_addresses.json format:**
```json
{
  "addresses": {
    "1401 thrasher dr, little elm, tx 75068": {
      "gas": {
        "name": "CoServ Gas",
        "phone": "940-321-7800",
        "website": "https://www.coserv.com",
        "verified_date": "2026-01-20",
        "verified_by": "tenant"
      }
    }
  },
  "zip_overrides": {
    "75068": {
      "gas": {
        "name": "CoServ Gas",
        "phone": "940-321-7800",
        "note": "Denton County - CoServ serves entire ZIP"
      },
      "electric": {
        "name": "CoServ Electric",
        "phone": "940-321-7400"
      }
    }
  }
}
```

#### 3.5 Update Confidence Hierarchy

**FILE: `pipeline/interfaces.py`**

```python
# Updated confidence scores (applies to ALL utility types)
SOURCE_CONFIDENCE = {
    # Tier 1: Ground truth
    "user_corrections": 99,        # Tenant/resident reports

    # Tier 2: Authoritative government data
    "state_gis": 90,              # State GIS APIs (point-in-polygon)

    # Tier 3: Municipal databases
    "municipal_utility": 85,       # City-owned utilities

    # Tier 4: Specialized sources
    "electric_coop": 80,           # Rural electric co-ops

    # Tier 5: Geographic boundaries
    "hifld_polygon": 75,           # HIFLD geographic data
    "eia_861": 70,                 # EIA Form 861 (electric only)
    "epa_sdwis": 65,               # EPA water database

    # Tier 6: Fallbacks
    "county_default": 40,          # County-level defaults

    # DELETED (too coarse, causes errors):
    # "zip_mapping": 50,           # ZIP prefix mapping ❌ REMOVED
    # "state_ldc_mapping": 65,     # State LDC ZIP mapping ❌ REMOVED
}
```

### Deliverables
- [ ] Water pipeline sources created (4 sources)
- [ ] ZIPMappingGasSource deleted
- [ ] HIFLD sources return multiple candidates
- [ ] SourceResult interface updated
- [ ] Smart Selector handles candidate lists
- [ ] UserCorrectionSource created (all utilities)
- [ ] Confidence hierarchy updated
- [ ] All changes applied to electric, gas, AND water

---

## Phase 4: Testing & Validation (Week 8-9)

### Goal
No regressions. Verify improvements across ALL utility types.

### Tasks

#### 4.1 Comprehensive Regression Tests

```python
# tests/test_regression_all_utilities.py
import pytest
from utility_lookup_v2 import lookup_utilities_by_address

# Known correct answers for ALL utility types
TEST_CASES = [
    # Gas corrections
    {
        "address": "1401 Thrasher Dr, Little Elm, TX 75068",
        "expected": {
            "gas": "CoServ Gas",
            "electric": "CoServ Electric"
        }
    },
    # Water corrections
    {
        "address": "123 S 2nd St, Yakima, WA 98901",
        "expected": {
            "water": "Yakima Water Division City of"
        }
    },
    # Municipal utilities
    {
        "address": "500 Pearl St, Austin, TX 78701",
        "expected": {
            "electric": "Austin Energy",
            "gas": "Texas Gas Service",
            "water": "Austin Water"
        }
    },
    # Deregulated electric (TDU)
    {
        "address": "1200 Smith St, Houston, TX 77002",
        "expected": {
            "electric": "CenterPoint Energy",  # TDU, not retail
            "gas": "CenterPoint Energy",
            "water": "City of Houston"
        }
    },
    # Rural co-op
    {
        "address": "100 Main St, Fayetteville, AR 72701",
        "expected": {
            "electric": contains("Carroll Electric")  # Co-op
        }
    },
    # Add 95+ more covering all states, all utility types
]

@pytest.mark.parametrize("case", TEST_CASES)
def test_known_addresses(case):
    """Test v2 returns correct results for known addresses."""
    result = lookup_utilities_by_address(case["address"])

    assert result is not None, f"Lookup failed for {case['address']}"

    for utility_type, expected_name in case["expected"].items():
        assert result.get(utility_type) is not None, \
            f"No {utility_type} result for {case['address']}"

        actual_name = result[utility_type].get('NAME', '')

        if callable(expected_name):  # e.g., contains()
            assert expected_name(actual_name), \
                f"{utility_type}: Expected {expected_name}, got {actual_name}"
        else:
            assert expected_name.lower() in actual_name.lower(), \
                f"{utility_type}: Expected '{expected_name}', got '{actual_name}'"
```

#### 4.2 A/B Comparison: V1 vs V2

```python
# scripts/compare_v1_v2_all_utilities.py
"""
Compare v1 (old) vs v2 (new) results for all utility types.
"""
from utility_lookup import lookup_utilities_by_address as lookup_v1
from utility_lookup_v2 import lookup_utilities_by_address as lookup_v2
import json

def compare_versions(addresses: list):
    """Compare v1 vs v2 for electric, gas, AND water."""
    differences = []
    improvements = []
    regressions = []

    for addr in addresses:
        print(f"Testing: {addr}")

        v1_result = lookup_v1(addr)
        v2_result = lookup_v2(addr)

        for utility_type in ['electric', 'gas', 'water']:
            v1_name = v1_result.get(utility_type, {}).get('NAME') if v1_result else None
            v2_name = v2_result.get(utility_type, {}).get('NAME') if v2_result else None

            if v1_name != v2_name:
                diff = {
                    "address": addr,
                    "utility": utility_type,
                    "v1": v1_name,
                    "v2": v2_name,
                    "v1_source": v1_result.get(utility_type, {}).get('_source') if v1_result else None,
                    "v2_source": v2_result.get(utility_type, {}).get('_source') if v2_result else None
                }
                differences.append(diff)

                # Categorize as improvement or regression
                if is_improvement(v1_name, v2_name, addr, utility_type):
                    improvements.append(diff)
                else:
                    regressions.append(diff)

    # Generate report
    print(f"\n=== COMPARISON REPORT ===")
    print(f"Total addresses: {len(addresses)}")
    print(f"Differences: {len(differences)}")
    print(f"Improvements: {len(improvements)}")
    print(f"Regressions: {len(regressions)}")

    if regressions:
        print(f"\n⚠️  REGRESSIONS FOUND:")
        for reg in regressions:
            print(f"  {reg['address']} ({reg['utility']}): {reg['v1']} → {reg['v2']}")

    # Save detailed report
    with open('comparison_report.json', 'w') as f:
        json.dump({
            'summary': {
                'total': len(addresses),
                'differences': len(differences),
                'improvements': len(improvements),
                'regressions': len(regressions)
            },
            'differences': differences,
            'improvements': improvements,
            'regressions': regressions
        }, f, indent=2)

    return len(regressions) == 0  # Pass if no regressions

def is_improvement(v1_name: str, v2_name: str, address: str, utility_type: str) -> bool:
    """
    Determine if v2 result is an improvement over v1.
    Check against verified_addresses.json for ground truth.
    """
    # Load verified addresses
    with open('data/verified_addresses.json') as f:
        verified = json.load(f)

    # Check if we have ground truth
    addr_key = address.lower().strip()
    if addr_key in verified.get('addresses', {}):
        ground_truth = verified['addresses'][addr_key].get(utility_type, {}).get('name')
        if ground_truth:
            # v2 matches ground truth = improvement
            if ground_truth.lower() in (v2_name or '').lower():
                return True
            # v1 matches ground truth, v2 doesn't = regression
            if ground_truth.lower() in (v1_name or '').lower():
                return False

    # No ground truth - can't determine
    return False  # Conservative: treat as potential regression

if __name__ == "__main__":
    # Test with snapshot addresses
    with open('tests/snapshots/test_addresses.json') as f:
        test_addresses = json.load(f)

    success = compare_versions(test_addresses)
    exit(0 if success else 1)
```

#### 4.3 Performance & Cost Benchmarking

```python
# scripts/benchmark_all.py
"""
Benchmark latency and OpenAI cost for all utility types.
"""
import time
import tiktoken
from utility_lookup_v2 import lookup_utilities_by_address

def benchmark_latency(addresses: list, iterations: int = 3):
    """Measure lookup latency for each utility type."""
    results = {
        'electric': [],
        'gas': [],
        'water': [],
        'total': []
    }

    for addr in addresses:
        print(f"Benchmarking: {addr}")

        for _ in range(iterations):
            start = time.time()
            result = lookup_utilities_by_address(addr)
            total_time = time.time() - start

            results['total'].append(total_time)

            # Individual utility times (approximate)
            if result:
                for util_type in ['electric', 'gas', 'water']:
                    if result.get(util_type):
                        # Rough estimate: total / 3
                        results[util_type].append(total_time / 3)

    # Calculate statistics
    for key, times in results.items():
        if times:
            avg = sum(times) / len(times)
            p50 = sorted(times)[len(times) // 2]
            p95 = sorted(times)[int(len(times) * 0.95)]
            print(f"{key:10} - Avg: {avg:.2f}s, P50: {p50:.2f}s, P95: {p95:.2f}s")


def benchmark_cost(addresses: list):
    """Estimate OpenAI API cost per lookup."""
    # Track tokens used
    encoding = tiktoken.encoding_for_model("gpt-4")

    total_tokens = 0

    for addr in addresses:
        # Simulate Smart Selector query
        # (In real system, intercept OpenAI calls)
        prompt = f"Select best utility for {addr} from sources..."
        tokens = len(encoding.encode(prompt))
        total_tokens += tokens

    # GPT-4 pricing (example)
    cost_per_1k_tokens = 0.03  # $0.03 per 1K tokens
    total_cost = (total_tokens / 1000) * cost_per_1k_tokens
    cost_per_lookup = total_cost / len(addresses)

    print(f"\n=== COST ESTIMATE ===")
    print(f"Total tokens: {total_tokens:,}")
    print(f"Total cost: ${total_cost:.4f}")
    print(f"Cost per lookup: ${cost_per_lookup:.4f}")

    return cost_per_lookup


if __name__ == "__main__":
    test_addresses = [
        "1401 Thrasher Dr, Little Elm, TX 75068",
        "123 S 2nd St, Yakima, WA 98901",
        "500 Pearl St, Austin, TX 78701",
        # ... 20+ more
    ]

    print("=== LATENCY BENCHMARK ===")
    benchmark_latency(test_addresses)

    print("\n=== COST BENCHMARK ===")
    benchmark_cost(test_addresses)
```

#### 4.4 Gradual Rollout Plan

**Week 8: 10% Traffic**
```python
# api/handlers.py
AB_TEST_PERCENTAGE = 0.10  # 10% to v2

def lookup_handler(request):
    use_v2 = random.random() < AB_TEST_PERCENTAGE
    # ... (same as before)
```

**Monitor:**
- Error rate v1 vs v2
- Latency p95
- User corrections submitted
- Disagreements between v1/v2

**Success criteria to increase to 25%:**
- ✅ Error rate v2 ≤ v1
- ✅ Latency p95 < 3s
- ✅ No critical bugs

**Week 9: 25% Traffic**
```python
AB_TEST_PERCENTAGE = 0.25
```

**Week 10: 50% Traffic**
```python
AB_TEST_PERCENTAGE = 0.50
```

**Week 11: 100% Traffic**
```python
AB_TEST_PERCENTAGE = 1.00  # All traffic to v2
```

**Week 12: Delete v1 Code**
```bash
# Archive old code
git mv utility_lookup.py archive/utility_lookup_v1.py
git mv utility_lookup_v2.py utility_lookup.py

# Delete old files
rm state_utility_verification.py  # Logic now in pipeline sources
rm -rf archive/
```

### Deliverables
- [ ] Regression tests passing (100+ addresses, all utilities)
- [ ] A/B comparison shows ≤5% differences
- [ ] No critical regressions
- [ ] Latency < 2s (p95)
- [ ] Cost ≤ $0.02 per lookup
- [ ] Gradual rollout complete
- [ ] v1 code deleted

---

## Phase 5: Documentation & Cleanup (Week 10)

### Goal
Clean repository. Up-to-date documentation. Knowledge transfer.

### Tasks

#### 5.1 Update README

```markdown
# Utility Lookup System v2

## Overview
Clean, pipeline-based utility lookup for electric, gas, and water providers.

## Architecture

### Entry Point
```python
from utility_lookup import lookup_utilities_by_address

result = lookup_utilities_by_address("123 Main St, Austin, TX 78701")
# Returns: { electric: {...}, gas: {...}, water: {...} }
```

### Pipeline Sources
Each utility type queries 5-6 sources in priority order:

1. **User Corrections** (99) - Verified tenant reports
2. **State GIS APIs** (90) - Authoritative government data
3. **Municipal Database** (85) - City-owned utilities
4. **HIFLD Polygons** (75) - Geographic boundaries
5. **County Defaults** (40) - Fallback

### Smart Selector
When sources disagree, OpenAI GPT-4 selects the most likely correct provider based on:
- Source confidence scores
- Geographic proximity
- Service area boundaries
- Historical accuracy

## Adding New Data

### User Corrections
Edit `data/verified_addresses.json`:
```json
{
  "addresses": {
    "123 main st, city, st 12345": {
      "gas": {
        "name": "Provider Name",
        "verified_date": "2026-01-20",
        "verified_by": "tenant"
      }
    }
  }
}
```

### Municipal Utilities
Edit `data/municipal_utilities.json`:
```json
{
  "electric": {
    "TX": {
      "Austin": {
        "name": "Austin Energy",
        "phone": "512-494-9400",
        "zip_codes": ["78701", "78702", ...]
      }
    }
  }
}
```

## Testing

Run regression tests:
```bash
pytest tests/test_regression_all_utilities.py
```

Compare v1 vs v2:
```bash
python scripts/compare_v1_v2_all_utilities.py
```

Benchmark performance:
```bash
python scripts/benchmark_all.py
```

## Monitoring

Key metrics tracked:
- `utility_lookup.{type}.latency` - Response time
- `utility_lookup.{type}.source.{source_name}` - Source usage
- `utility_lookup.{type}.confidence` - Result confidence

Dashboard: https://monitoring.example.com/utility-lookup
```

#### 5.2 API Documentation

```markdown
# API Documentation

## Endpoint: POST /api/lookup

### Request
```json
{
  "address": "123 Main St, Austin, TX 78701",
  "selected_utilities": ["electric", "gas", "water"]  // optional
}
```

### Response
```json
{
  "electric": {
    "NAME": "Austin Energy",
    "TELEPHONE": "512-494-9400",
    "WEBSITE": "https://austinenergy.com",
    "STATE": "TX",
    "CITY": "Austin",
    "_confidence": "high",
    "_confidence_score": 90,
    "_source": "municipal_utility",
    "_selection_reason": "City-owned utility for Austin"
  },
  "gas": {
    "NAME": "Texas Gas Service",
    ...
  },
  "water": {
    "NAME": "Austin Water",
    ...
  }
}
```

### Confidence Levels
- **high** (80-100) - Very likely correct
- **medium** (60-79) - Probably correct, verify if critical
- **low** (40-59) - Uncertain, manual verification recommended
- **none** (0-39) - No reliable data found

### Error Responses
```json
{
  "error": "Could not geocode address",
  "address": "invalid address"
}
```

## Rate Limits
- 100 requests per minute per IP
- 1000 requests per day per API key
```

#### 5.3 Troubleshooting Guide

```markdown
# Troubleshooting Guide

## Common Issues

### "Wrong provider returned"

1. Check verified addresses:
   ```bash
   grep "address" data/verified_addresses.json
   ```

2. Check which source was used:
   ```python
   result = lookup_utilities_by_address(address)
   print(result['gas']['_source'])  # e.g., "hifld_gas"
   ```

3. Add correction if needed:
   - Edit `data/verified_addresses.json`
   - Set confidence to 99 (overrides all sources)

### "No result found"

Check pipeline logs:
```bash
tail -f logs/pipeline.log | grep "address"
```

Look for:
- Geocoding failures
- All sources returning None
- Exceptions in source queries

### "Latency too high"

1. Check which utility type is slow:
   ```python
   # Individual utility lookups
   lookup_utilities_by_address(addr, selected_utilities=['electric'])
   ```

2. Check source latency:
   - State GIS APIs: 1-3s (external API call)
   - HIFLD: 0.5-1s (local shapefile query)
   - Municipal DB: <0.1s (JSON lookup)

3. Optimize slow sources or increase timeout

## Debugging

Enable debug logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Run single lookup:
```bash
python -m utility_lookup "123 Main St, Austin, TX"
```

Compare sources:
```bash
python scripts/compare_sources.py "address"
```
```

#### 5.4 Delete Old Code

**Files to delete:**
```bash
# Archive v1 for reference
mkdir -p archive/v1
git mv utility_lookup.py archive/v1/
git mv state_utility_verification.py archive/v1/

# Move v2 to main
git mv utility_lookup_v2.py utility_lookup.py

# Delete old data files (already merged)
rm data/gas_county_lookups.json
rm data/electric_cooperatives_supplemental.json
# ... (40+ redundant files)

# Clean up
rm -rf __pycache__/
rm -rf .pytest_cache/
```

**Update imports across codebase:**
```bash
# Find all imports of old files
grep -r "from state_utility_verification import" .

# Update to new sources
# OLD: from state_utility_verification import verify_gas_provider
# NEW: (no longer needed - pipeline handles it)
```

### Deliverables
- [ ] README updated with v2 architecture
- [ ] API documentation complete
- [ ] Troubleshooting guide written
- [ ] Old code deleted/archived
- [ ] Clean repository (51 data files → 10)

---

## Metrics Summary

### Before Refactor
| Metric | Value |
|--------|-------|
| Lines of code | 7,267 |
| Data files | 51 |
| Priority checks | 30+ |
| Lookup latency (p95) | ~3-5s |
| Error rate | Unknown |
| OpenAI cost/lookup | ~$0.01 |

### After Refactor
| Metric | Target |
|--------|--------|
| Lines of code | < 2,000 |
| Data files | < 10 |
| Priority checks | 1 (pipeline) |
| Lookup latency (p95) | < 2s |
| Error rate | < 1% |
| OpenAI cost/lookup | ~$0.01-0.02 |

---

## Timeline Summary

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| 0: Prep | 1 week | Baseline metrics, monitoring |
| 1: Data | 2 weeks | Clean data, schemas, validation |
| 2: Logic | 2 weeks | utility_lookup_v2.py, A/B test |
| 3: Sources | 3 weeks | Water sources, fix HIFLD, delete ZIP mapping |
| 4: Testing | 2 weeks | Regression tests, gradual rollout |
| 5: Docs | 1 week | Documentation, cleanup |

**Total: 11 weeks** (can compress to 8 weeks with dedicated focus)

---

## Risk Mitigation

### Rollback Plan
```bash
# Tag before each phase
git tag phase-0-baseline
git tag phase-1-data-complete
git tag phase-2-logic-complete
# ...

# Rollback if needed
git checkout phase-1-data-complete
```

### Circuit Breaker
```python
# Auto-rollback if error rate spikes
if error_rate_v2 > error_rate_v1 * 1.5:
    AB_TEST_PERCENTAGE = 0.0  # Revert to v1
    send_alert("Circuit breaker triggered - rolled back to v1")
```

### Monitoring Alerts
- Error rate > 2%
- Latency p95 > 3s
- Cost > $0.03/lookup
- v1 vs v2 disagreement > 10%

---

## Success Criteria

### Must Have (Go/No-Go)
- ✅ All regression tests passing
- ✅ No increase in error rate
- ✅ Latency < 3s (p95)
- ✅ A/B comparison shows ≤5% differences

### Should Have
- ✅ Latency < 2s (p95)
- ✅ Error rate < 1%
- ✅ Cost ≤ $0.02/lookup
- ✅ 95% user corrections preserved

### Nice to Have
- ✅ Latency < 1.5s (p95)
- ✅ Error rate < 0.5%
- ✅ 100% test coverage

---

## Next Steps

1. **Week 0:** Start Phase 0 (pre-refactor prep)
   - Capture baseline metrics
   - Create snapshot tests
   - Set up monitoring

2. **Decision Point:** Review this plan with team
   - Approve timeline
   - Allocate resources
   - Confirm go/no-go

3. **Week 1:** Begin Phase 1 (data consolidation)
   - Audit data files
   - Create schemas
   - Start migration

---

## Questions for Decision

1. ✅ **Scope confirmed:** Electric, gas, AND water refactor
2. **Timeline:** 11 weeks acceptable? Or compress to 8 weeks?
3. **Resources:** Dedicated developer or part-time?
4. **External dependencies:** Any systems depend on exact v1 API format?
5. **Cost:** OpenAI API budget for Smart Selector?

---

**Document Version**: 2.0 - Complete (All Utilities)
**Date**: 2026-01-20
**Changes from v1.0**: Added electric and water refactoring scope
