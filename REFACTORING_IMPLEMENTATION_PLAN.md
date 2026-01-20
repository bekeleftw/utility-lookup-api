# Utility Lookup System - Refactoring Implementation Plan

## Quick Wins Completed ✅

### 1. Lower ZIP Mapping Confidence (Done)
**File:** `pipeline/sources/gas.py` lines 142-149
- Changed confidence from 80 → 50 for "verified" ZIP results
- Changed confidence from 75 → 45 for "high" ZIP results
- Now HIFLD polygons (75) and municipal data (85) win over ZIP mapping

### 2. Add CoServ Gas for Denton County (Done)
**File:** `state_utility_verification.py`
- Added `COSERV` to `TEXAS_GAS_LDCS` dictionary (lines 688-693)
- Added 8 Denton County ZIPs to `TEXAS_GAS_ZIP_OVERRIDES` (lines 727-734)
- Test: `get_texas_gas_ldc('75068', 'Little Elm')` → Returns CoServ Gas ✅

---

## Full Refactoring Strategy

### Recommended Approach: Incremental Refactor (Option B)

Based on the assessment, I recommend **Option B: Quick Wins + Incremental Refactor** because:
1. Quick wins already deployed - immediate pain resolved
2. Lower risk than big-bang refactor
3. Can be done in parallel with other work
4. Each phase delivers value independently

---

## Phase 1: Data Consolidation (Week 1-2)

### Goal
Single source of truth for each data type. Eliminate redundant files.

### Tasks

#### 1.1 Audit Data Files
```bash
# List all data files and their sizes
find data/ -name "*.json" -exec wc -l {} \; | sort -n
```

**Files to Keep:**
- `data/municipal_utilities.json` - City-owned utilities
- `data/verified_addresses.json` - User corrections (highest priority)
- `data/county_utility_defaults.json` - County-level fallbacks

**Files to Merge:**
- `data/gas_county_lookups.json` → Merge into `county_utility_defaults.json`
- `data/electric_cooperatives_supplemental.json` → Merge into `municipal_utilities.json`

**Files to Delete (after migration):**
- Redundant state-specific files
- Duplicate mappings

#### 1.2 Create Data Schemas
```json
// schemas/municipal_utilities.schema.json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "state": {
      "type": "object",
      "additionalProperties": {
        "type": "object",
        "properties": {
          "city": {
            "type": "object",
            "properties": {
              "electric": { "$ref": "#/definitions/utility" },
              "gas": { "$ref": "#/definitions/utility" },
              "water": { "$ref": "#/definitions/utility" }
            }
          }
        }
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
        "website": { "type": "string" },
        "verified": { "type": "boolean" },
        "verified_date": { "type": "string", "format": "date" }
      }
    }
  }
}
```

#### 1.3 Migrate Hardcoded Dicts to JSON
Move these from `state_utility_verification.py` to JSON files:
- `TEXAS_GAS_ZIP_PREFIX` → `data/texas_gas_territories.json`
- `TEXAS_GAS_ZIP_OVERRIDES` → `data/texas_gas_territories.json`
- `GAS_ZIP_OVERRIDES` → `data/verified_addresses.json`

**Benefit:** Data changes don't require code deployment

#### 1.4 Validation Script
```python
# scripts/validate_data.py
import json
import jsonschema
from pathlib import Path

def validate_all():
    """Validate all data files against schemas."""
    schemas_dir = Path("schemas")
    data_dir = Path("data")
    
    for schema_file in schemas_dir.glob("*.schema.json"):
        data_file = data_dir / schema_file.stem.replace(".schema", ".json")
        if data_file.exists():
            with open(schema_file) as f:
                schema = json.load(f)
            with open(data_file) as f:
                data = json.load(f)
            jsonschema.validate(data, schema)
            print(f"✅ {data_file.name} valid")
```

### Deliverables
- [ ] Data file audit complete
- [ ] Schemas created for all data files
- [ ] Hardcoded dicts migrated to JSON
- [ ] Validation script passing

---

## Phase 2: Simplify Lookup Logic (Week 3-4)

### Goal
Pipeline is the ONLY orchestrator. Remove priority spaghetti.

### Tasks

#### 2.1 Create New Entry Point
```python
# utility_lookup_v2.py (< 200 lines)
"""
Simplified utility lookup - Pipeline is the only orchestrator.
"""
from pipeline.pipeline import LookupPipeline
from pipeline.interfaces import LookupContext, UtilityType

def lookup_utilities_by_address(address: str, use_pipeline: bool = True) -> dict:
    """
    Main entry point for utility lookups.
    
    Args:
        address: Full street address
        use_pipeline: Always True in v2
        
    Returns:
        Dict with electric, gas, water utility info
    """
    # Step 1: Geocode
    geo = geocode_address(address)
    if not geo:
        return {"error": "Could not geocode address"}
    
    # Step 2: Create context
    context = LookupContext(
        lat=geo['lat'],
        lon=geo['lon'],
        address=address,
        city=geo['city'],
        county=geo['county'],
        state=geo['state'],
        zip_code=geo['zip']
    )
    
    # Step 3: Pipeline handles everything
    results = {}
    for utility_type in [UtilityType.ELECTRIC, UtilityType.GAS, UtilityType.WATER]:
        context.utility_type = utility_type
        result = LookupPipeline.lookup(context)
        results[utility_type.value] = result
    
    return results
```

#### 2.2 A/B Test Setup
```python
# In main API handler
def lookup_handler(address: str):
    # 10% to v2, 90% to v1
    if random.random() < 0.10:
        return lookup_utilities_by_address_v2(address)
    else:
        return lookup_utilities_by_address(address)
```

#### 2.3 Remove Duplicate Lookups
In current `utility_lookup.py`, these are called multiple times:
- `lookup_municipal_gas()` - called at PRIORITY 1 AND PRIORITY 3
- `get_texas_gas_ldc()` - called in pipeline AND verification

**Fix:** Each source called exactly once by pipeline.

#### 2.4 Delete Verification Layer
Current flow:
```
Pipeline result → verify_gas_provider() → may override result
```

New flow:
```
Pipeline result → return directly (no post-processing)
```

### Deliverables
- [ ] `utility_lookup_v2.py` created
- [ ] A/B test infrastructure in place
- [ ] Duplicate lookups removed
- [ ] Verification layer deleted

---

## Phase 3: Refactor Data Sources (Week 5-6)

### Goal
Each source is independent, well-scored, auditable.

### Tasks

#### 3.1 Delete ZIPMappingGasSource
**File:** `pipeline/sources/gas.py` lines 116-165

**Reason:** ZIP prefix mapping is fundamentally flawed for metro areas.

**Replacement:** Let HIFLD polygons and municipal data handle it.

```python
# DELETE this entire class
class ZIPMappingGasSource(DataSource):
    """DEPRECATED - ZIP prefixes too coarse for metro areas."""
    pass
```

#### 3.2 Fix HIFLDGasSource
**Current:** Returns first result from list (wrong)
**New:** Returns all candidates, let Smart Selector choose

```python
# pipeline/sources/gas.py
class HIFLDGasSource(DataSource):
    def lookup(self, context: LookupContext) -> SourceResult:
        result = query_hifld_gas(context.lat, context.lon)
        
        if not result:
            return None
        
        # Return ALL candidates, not just first
        candidates = result if isinstance(result, list) else [result]
        
        return SourceResult(
            source_name=self.name,
            utility_name=None,  # Let Smart Selector choose
            confidence_score=self.base_confidence,
            match_type='polygon',
            candidates=[{
                "name": c.get("NAME"),
                "phone": c.get("TELEPHONE"),
                "website": c.get("WEBSITE"),
                "distance": c.get("_distance", 0)
            } for c in candidates],
            raw_data=result
        )
```

#### 3.3 Add UserCorrectionSource
**New source** - highest priority (confidence: 99)

```python
# pipeline/sources/corrections.py
class UserCorrectionSource(DataSource):
    """
    User-reported corrections from verified_addresses.json.
    Highest priority - ground truth from tenants/residents.
    """
    name = "user_corrections"
    base_confidence = 99
    
    def lookup(self, context: LookupContext) -> SourceResult:
        corrections = load_verified_addresses()
        
        # Check exact address match
        key = f"{context.address}|{context.zip_code}"
        if key in corrections:
            return self._build_result(corrections[key], "exact_address")
        
        # Check ZIP-level override
        if context.zip_code in corrections.get("zip_overrides", {}):
            return self._build_result(
                corrections["zip_overrides"][context.zip_code],
                "zip_override"
            )
        
        return None
```

#### 3.4 Update Confidence Hierarchy
```python
# pipeline/interfaces.py
SOURCE_CONFIDENCE = {
    "user_corrections": 99,    # Ground truth
    "state_gis": 90,           # Authoritative government data
    "municipal_db": 85,        # City-owned utilities
    "electric_coops": 80,      # Rural co-ops
    "hifld_polygon": 75,       # Geographic boundaries
    "county_default": 40,      # Fallback only
    # DELETED: "zip_mapping": 50  # Too coarse, causes errors
}
```

### Deliverables
- [ ] ZIPMappingGasSource deleted
- [ ] HIFLDGasSource returns all candidates
- [ ] UserCorrectionSource created
- [ ] Confidence hierarchy updated

---

## Phase 4: Testing & Validation (Week 7-8)

### Goal
No regressions, verify improvements.

### Tasks

#### 4.1 Regression Test Suite
```python
# tests/test_regression.py
import pytest
from utility_lookup_v2 import lookup_utilities_by_address

# Known correct answers
TEST_CASES = [
    {
        "address": "1401 Thrasher Dr, Little Elm, TX 75068",
        "expected_gas": "CoServ Gas",
        "expected_electric": "CoServ Electric"
    },
    {
        "address": "202 N 66th Ave F, Yakima, WA 98908",
        "expected_water": "YAKIMA WATER DIVISION"
    },
    # Add more from verified_addresses.json
]

@pytest.mark.parametrize("case", TEST_CASES)
def test_known_addresses(case):
    result = lookup_utilities_by_address(case["address"])
    
    if "expected_gas" in case:
        assert case["expected_gas"] in result["gas"]["name"]
    if "expected_electric" in case:
        assert case["expected_electric"] in result["electric"]["name"]
    if "expected_water" in case:
        assert case["expected_water"] in result["water"]["name"]
```

#### 4.2 A/B Comparison
```python
# scripts/compare_v1_v2.py
def compare_versions(addresses: list):
    """Compare v1 vs v2 results for a list of addresses."""
    differences = []
    
    for addr in addresses:
        v1 = lookup_utilities_by_address_v1(addr)
        v2 = lookup_utilities_by_address_v2(addr)
        
        for utility_type in ['electric', 'gas', 'water']:
            if v1.get(utility_type, {}).get('name') != v2.get(utility_type, {}).get('name'):
                differences.append({
                    "address": addr,
                    "utility": utility_type,
                    "v1": v1.get(utility_type, {}).get('name'),
                    "v2": v2.get(utility_type, {}).get('name')
                })
    
    return differences
```

#### 4.3 Performance Benchmarks
```python
# scripts/benchmark.py
import time

def benchmark(addresses: list, iterations: int = 3):
    """Measure lookup latency."""
    for addr in addresses:
        times = []
        for _ in range(iterations):
            start = time.time()
            lookup_utilities_by_address(addr)
            times.append(time.time() - start)
        
        avg = sum(times) / len(times)
        print(f"{addr}: {avg:.2f}s avg")
```

#### 4.4 Gradual Rollout
1. **Week 1:** 10% traffic to v2
2. **Week 2:** 25% traffic to v2 (if no issues)
3. **Week 3:** 50% traffic to v2
4. **Week 4:** 100% traffic to v2
5. **Week 5:** Delete v1 code

### Deliverables
- [ ] Regression test suite passing
- [ ] A/B comparison shows improvement
- [ ] Performance benchmarks acceptable (< 2s)
- [ ] Gradual rollout complete

---

## Metrics to Track

| Metric | Current | Target | How to Measure |
|--------|---------|--------|----------------|
| Lookup latency | ~2-5s | < 2s | API response time |
| Error rate | ? | < 1% | User-reported corrections |
| Lines of code | 7,267 | < 2,000 | `wc -l *.py` |
| Data files | 51 | < 10 | `ls data/*.json | wc -l` |
| Priority checks | 30+ | 1 | `grep -c PRIORITY` |

---

## Risk Mitigation

### Rollback Plan
```bash
# Tag current working version
git tag pre-refactor-v1

# If issues, rollback
git checkout pre-refactor-v1
```

### Circuit Breaker
```python
# In API handler
if error_rate > 0.05:  # 5% errors
    use_v1_fallback = True
    alert_on_call()
```

### Monitoring
- Log every source result
- Log Smart Selector reasoning
- Track v1 vs v2 disagreements
- Alert on latency spikes

---

## Timeline Summary

| Week | Phase | Deliverable |
|------|-------|-------------|
| 1-2 | Data Consolidation | Clean data directory, schemas |
| 3-4 | Simplify Logic | utility_lookup_v2.py, A/B test |
| 5-6 | Refactor Sources | New sources, delete ZIP mapping |
| 7-8 | Testing & Rollout | Full deployment |

**Total: 8 weeks** (can be compressed to 4-6 weeks with dedicated focus)

---

## Next Steps

1. **Immediate:** Deploy Quick Wins (already done ✅)
2. **This week:** Start Phase 1 data audit
3. **Decision:** Full refactor or stop at Quick Wins?

---

## Questions for Decision

1. Is the current system "done" or actively evolving?
2. How much time can be dedicated to refactoring?
3. Are there other high-priority features competing for time?
4. What's the cost of user-reported errors vs. refactoring time?
