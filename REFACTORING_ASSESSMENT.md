# Utility Lookup System - Refactoring Assessment

## Executive Summary

The utility lookup system has evolved through incremental feature additions, resulting in:
- **7,267 lines** of complex priority-based lookup logic
- **51 data files** with overlapping/duplicate information
- **Multiple competing systems** for the same task (manual lookups, pipeline, verification layers)
- **Hardcoded mappings** that cause incorrect results (e.g., ZIP 75068 → Atmos instead of CoServ)

**Recommendation**: Yes, this needs refactoring. The current architecture has classic tech debt that makes it brittle and hard to maintain.

---

## Current System Architecture

### File Structure & Size

```
utility_lookup.py              3,464 lines  - Main lookup orchestrator
state_utility_verification.py  1,401 lines  - State-specific verification logic
gis_utility_lookup.py          1,942 lines  - GIS API queries
pipeline/pipeline.py             460 lines  - Smart pipeline (underutilized)
pipeline/sources/gas.py          264 lines  - Gas data sources
pipeline/sources/electric.py     [similar]  - Electric data sources

data/*.json                      51 files   - Overlapping data
```

### Current Lookup Flow (Gas Example)

```
lookup_utilities_by_address()
  ↓
PRIORITY 0: corrections_lookup (user-reported fixes)
  ↓
PRIORITY 1: lookup_municipal_gas() → municipal_utilities.json
  ↓
PRIORITY 2: Pipeline with OpenAI Smart Selector
  ↓  └─ Queries: municipal_gas, zip_mapping_gas, hifld_gas, county_default
  ↓     └─ zip_mapping_gas calls get_texas_gas_ldc()
  ↓         └─ Uses TEXAS_GAS_ZIP_PREFIX (hardcoded)
  ↓             └─ "750": "ATMOS" (WRONG for Denton County)
  ↓
PRIORITY 3: lookup_municipal_gas() AGAIN (duplicate)
  ↓
PRIORITY 3: lookup_gas_utility() → HIFLD polygons
  ↓
  └─ verify_gas_provider()
      └─ get_texas_gas_ldc() AGAIN
          └─ Uses TEXAS_GAS_ZIP_PREFIX AGAIN
```

### Priority Checks Count

```bash
$ grep -c "PRIORITY\|# FIRST\|# SECOND" utility_lookup.py
30+ distinct priority checks
```

---

## Identified Problems

### 1. Spaghetti Priority Logic

**Evidence:**
- 30+ priority checks scattered across files
- Conflicting numbering systems (PRIORITY 0-3, FIRST/SECOND/THIRD)
- Same data source queried multiple times:
  - `lookup_municipal_gas()` called at PRIORITY 1 (line 2251) AND PRIORITY 3 (line 2271)
  - `get_texas_gas_ldc()` called in multiple code paths
- Pipeline exists but old lookup paths still execute afterward

**Impact:**
- Hard to understand execution flow
- Easy to introduce bugs when adding features
- Maintenance requires changing multiple locations

### 2. Redundant Data Sources

**Gas Provider Lookups (All doing the same thing):**

| Source | Type | Location |
|--------|------|----------|
| `lookup_municipal_gas()` | Function | utility_lookup.py:2251 |
| `municipal_utilities.json` | Data File | data/municipal_utilities.json |
| `ZIPMappingGasSource` | Pipeline Source | pipeline/sources/gas.py:116 |
| `TEXAS_GAS_ZIP_PREFIX` | Hardcoded Dict | state_utility_verification.py:691 |
| `TEXAS_GAS_ZIP_OVERRIDES` | Hardcoded Dict | state_utility_verification.py:718 |
| `GAS_ZIP_OVERRIDES` | Hardcoded Dict | state_utility_verification.py:734 |
| `get_texas_gas_ldc()` | Function | state_utility_verification.py:1073 |
| `get_state_gas_ldc()` | Function | state_utility_verification.py (called from multiple places) |

**Problem Example: Little Elm, TX 75068**
- **Correct**: CoServ Gas (tenant-verified)
- **municipal_utilities.json**: Returns CoServ ✅ (but only after manual addition)
- **TEXAS_GAS_ZIP_PREFIX**: `"750": "ATMOS"` ❌ (wrong - too coarse)
- **HIFLD**: Returns [Atmos, CoServ] but Atmos first ❌ (wrong order)
- **Pipeline without municipal DB**: Returns Atmos ❌ (uses ZIP prefix mapping)

### 3. Pipeline is Underutilized

**Current State:**
- Pipeline with OpenAI Smart Selector built and working (pipeline/pipeline.py)
- Positioned as PRIORITY 2 (runs AFTER manual lookups)
- Even when pipeline runs, old verification logic executes afterward
- Pipeline sources query same broken data as manual lookups

**What Should Happen:**
- Pipeline should BE the orchestrator
- All data sources should be pipeline sources
- OpenAI selector should resolve ALL conflicts
- No post-pipeline verification needed

### 4. Hardcoded Territory Mappings

**The Fatal Flaw:**

```python
# state_utility_verification.py:691-714
TEXAS_GAS_ZIP_PREFIX = {
    # Dallas/Fort Worth area - Atmos Energy
    "750": "ATMOS",  # ← Covers 75000-75099
    "751": "ATMOS",
    # ... more prefixes
}
```

**Why This Breaks:**
- ZIP prefix "750" covers ~10,000 addresses
- Dallas/Fort Worth metro has MULTIPLE providers:
  - Dallas proper → Atmos Energy ✅
  - Denton County (75068, 75022, etc.) → CoServ Gas ✅
  - Some areas → Texas Gas Service ✅
- 3-digit mapping cannot distinguish between these

**Impact:**
- Returns wrong provider for entire counties
- Requires manual ZIP overrides (doesn't scale)
- Pipeline sources inherit this broken data (confidence: 80!)
- User-reported corrections patch over systematic problem

### 5. Data File Proliferation

**51 JSON files with overlapping data:**

```
data/municipal_utilities.json        - Manual utility mappings
data/county_utility_defaults.json    - County-level defaults
data/gas_county_lookups.json        - Gas provider by county (overlaps above)
data/verified_addresses.json        - User corrections
data/deregulated_markets.json       - Deregulated state info
data/electric_cooperatives_supplemental.json  - Co-op data
data/problem_areas.json             - Known problem areas
... 44 more files
```

**Problems:**
- No schema validation
- No single source of truth
- Updates require changing multiple files
- Hard to know which file takes precedence

---

## Root Cause Analysis: Why Little Elm Returns Wrong Provider

### The Failure Cascade

**Production Behavior:**
1. Municipal database missing (deployment lag) → Skipped
2. Pipeline runs:
   - `MunicipalGasSource` returns None (no data)
   - `ZIPMappingGasSource` returns "Atmos Energy" (confidence: 80)
     - Calls `get_state_gas_ldc()` → `get_texas_gas_ldc()`
     - Matches ZIP 75068 prefix "750" → TEXAS_GAS_ZIP_PREFIX["750"] = "ATMOS"
   - `HIFLDGasSource` returns "Atmos Energy" (confidence: 58)
     - HIFLD polygon query returns [Atmos, CoServ]
     - Takes first result → Atmos
3. Pipeline Smart Selector sees:
   - 2 sources agree: Atmos (ZIP mapping + HIFLD)
   - 0 sources say: CoServ
   - Decision: **Atmos Energy** ❌

**Why Automated Systems Failed:**
- ❌ ZIP mapping uses too-coarse 3-digit prefix
- ❌ HIFLD returns results in wrong order
- ⏸️ SERP verification disabled (too slow/expensive)
- ✅ OpenAI pipeline working correctly given bad input data

**Local Behavior (Correct):**
1. Municipal database has CoServ entry → Returns immediately ✅
2. Pipeline never consulted (PRIORITY 1 wins)

---

## Proposed Refactored Architecture

### New Design Principles

1. **Single Orchestrator**: Pipeline is the ONLY entry point
2. **Source = Plugin**: Each data source is independent, scored
3. **Data Beats Code**: No hardcoded mappings, all data in JSON
4. **Transparency**: Log why each source returned what it did
5. **Trust Hierarchy**: User fixes > Geographic boundaries > Fallbacks

### Simplified Flow

```
┌─────────────────────────────────────────┐
│   lookup_utilities_by_address(address)  │
│   (Thin wrapper - just geocodes)        │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│   Pipeline.lookup(context)               │
│   - Queries ALL sources in parallel      │
│   - Logs each source result             │
│   - OpenAI resolves conflicts           │
│   - Returns single answer + reasoning   │
└──────────────┬──────────────────────────┘
               │
    ┌──────────┼──────────┬──────────┬──────────┬──────────┐
    ▼          ▼          ▼          ▼          ▼          ▼
┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
│ User   │ │ State  │ │ HIFLD  │ │ Muni   │ │ Co-ops │ │ County │
│ Fixes  │ │  GIS   │ │Polygon │ │  DB    │ │  Data  │ │Default │
└────────┘ └────────┘ └────────┘ └────────┘ └────────┘ └────────┘
  (JSON)     (API)      (Geo)     (JSON)     (JSON)     (JSON)
  conf:99    conf:90    conf:75   conf:85    conf:80    conf:40
```

### Source Confidence Hierarchy

| Priority | Source | Confidence | Why |
|----------|--------|-----------|-----|
| 1 | User Corrections | 99 | Ground truth from tenants/residents |
| 2 | State GIS APIs | 90 | Authoritative government data |
| 3 | Municipal Database | 85 | City-owned utilities (verified) |
| 4 | Electric Co-ops | 80 | Rural co-ops know their territory |
| 5 | HIFLD Polygons | 75 | Geographic boundaries (but outdated) |
| 6 | County Defaults | 40 | Fallback only |
| 7 | ~~ZIP Prefix Mapping~~ | ~~DELETE~~ | Too coarse, causes errors |

---

## Refactoring Plan

### Phase 1: Consolidate Data (1-2 days)

**Goal**: Single source of truth for each data type

**Tasks:**
1. **Merge ZIP/territory mappings**
   - Delete `TEXAS_GAS_ZIP_PREFIX` (Python dict)
   - Delete `TEXAS_GAS_ZIP_OVERRIDES` (Python dict)
   - Delete `GAS_ZIP_OVERRIDES` (Python dict)
   - Keep only: `data/verified_addresses.json` (user corrections)

2. **Consolidate municipal utilities**
   - Already have: `data/municipal_utilities.json` ✅
   - Verify all entries are present
   - Add schema validation

3. **Merge county defaults**
   - Combine `data/county_utility_defaults.json` + `data/gas_county_lookups.json`
   - Single file: `data/county_defaults.json`

4. **Create data schemas**
   ```json
   {
     "user_corrections": "schema for verified_addresses.json",
     "municipal_utilities": "schema for municipal_utilities.json",
     "county_defaults": "schema for county_defaults.json"
   }
   ```

**Files to Delete:**
- `state_utility_verification.py` (move logic to pipeline sources)
- All hardcoded Python dicts

**Output**: Clean data directory with clear ownership

---

### Phase 2: Simplify Lookup Logic (2-3 days)

**Goal**: Pipeline is the ONLY orchestrator

**Tasks:**

1. **Rewrite main entry point**
   ```python
   # New utility_lookup.py (< 200 lines)
   def lookup_utilities_by_address(address: str) -> Dict:
       """Main entry point - just geocode and call pipeline."""
       geo = geocode_address(address)
       if not geo:
           return None

       context = LookupContext(
           lat=geo['lat'], lon=geo['lon'],
           address=address, city=geo['city'],
           county=geo['county'], state=geo['state'],
           zip_code=geo['zip']
       )

       results = {}
       for utility_type in ['electric', 'gas', 'water']:
           context.utility_type = utility_type
           result = Pipeline.lookup(context)
           results[utility_type] = result

       return results
   ```

2. **Delete priority spaghetti**
   - Remove all `PRIORITY 0/1/2/3` blocks
   - Remove `verify_gas_provider()`, `verify_electric_provider()`, etc.
   - Remove duplicate lookups

3. **Pipeline becomes orchestrator**
   - Pipeline queries sources in parallel
   - Pipeline handles ALL conflict resolution
   - No post-pipeline verification

**Files to Delete:**
- Current `utility_lookup.py` (3,464 lines) → Replace with < 300 lines
- `state_utility_verification.py` (1,401 lines) → Logic moves to sources

**Output**: Single, clear execution path

---

### Phase 3: Refactor Data Sources (2-3 days)

**Goal**: Each source is independent, well-scored, auditable

**Tasks:**

1. **Fix existing sources**

   **ZIPMappingGasSource** (pipeline/sources/gas.py:116)
   - **DELETE THIS ENTIRELY** ❌
   - Reason: ZIP prefixes too coarse, causes errors
   - Replacement: Let HIFLD polygons handle it

   **HIFLDGasSource** (pipeline/sources/gas.py:168)
   - Current: Returns first result from list
   - **Fix**: Return ALL results, let Smart Selector choose
   - Add geographic confidence scoring

   **MunicipalGasSource** (pipeline/sources/gas.py:73)
   - Keep as-is ✅
   - Boost confidence to 85

2. **Add new sources**

   **UserCorrectionSource** (NEW)
   - Highest priority (confidence: 99)
   - Queries `data/verified_addresses.json`
   - Exact address match or ZIP-level

   **StateGISGasSource** (EXISTS, needs work)
   - Already implemented for some states
   - Expand coverage, improve error handling

3. **Improve Smart Selector**
   - Add reasoning transparency
   - Log why each source was chosen/rejected
   - Handle ties better (prefer geographic over ZIP-based)

**Output**: Clean, modular sources with clear confidence scores

---

### Phase 4: Testing & Validation (1-2 days)

**Goal**: No regressions, verify improvements

**Tasks:**

1. **Regression testing**
   - Test against `data/verified_addresses.json`
   - Compare old vs new system on 1,000 random addresses
   - Flag any differences for review

2. **Known problem addresses**
   - Little Elm, TX 75068 → Should return CoServ Gas ✅
   - Yakima, WA → Should return Washington DOH water ✅
   - All addresses in `data/problem_areas.json`

3. **Performance testing**
   - Measure latency (should be < 2 seconds)
   - Check if parallel queries help
   - Monitor OpenAI API costs

4. **Deploy gradually**
   - Deploy to staging
   - A/B test: 10% new system, 90% old system
   - Monitor error rates
   - Ramp to 100%

**Output**: Confident deployment

---

## Immediate Quick Wins (No Full Refactor)

If full refactor is not feasible right now, these quick fixes provide immediate value:

### Quick Win 1: Lower ZIP Mapping Confidence (5 minutes)

**File**: `pipeline/sources/gas.py`

**Change**:
```python
# Line 143-146
# OLD:
if result.get('confidence') == 'verified':
    confidence = 80

# NEW:
if result.get('confidence') == 'verified':
    confidence = 50  # Lower than HIFLD (75), municipal (85)
```

**Impact**: ZIP mapping no longer overrides better sources

---

### Quick Win 2: Delete ZIP Prefix Mapping (15 minutes)

**File**: `state_utility_verification.py`

**Delete**:
- Lines 691-714: `TEXAS_GAS_ZIP_PREFIX = {...}`
- Lines 718-726: `TEXAS_GAS_ZIP_OVERRIDES = {...}`
- Lines 734-780: `GAS_ZIP_OVERRIDES = {...}`

**Update**:
- Line 1097: `if zip_prefix and zip_prefix in TEXAS_GAS_ZIP_PREFIX:` → Delete this entire block

**Impact**: Stops returning Atmos for Denton County

---

### Quick Win 3: Make Pipeline Priority 1 (10 minutes)

**File**: `utility_lookup.py`

**Change**:
```python
# OLD (lines 2250-2269):
# PRIORITY 1: Check municipal/regional gas data FIRST
elif (municipal_gas := lookup_municipal_gas(...)):
    ...
# PRIORITY 2: NEW PIPELINE with OpenAI Smart Selector
elif use_pipeline and PIPELINE_AVAILABLE:
    ...

# NEW:
# PRIORITY 1: NEW PIPELINE with OpenAI Smart Selector
if use_pipeline and PIPELINE_AVAILABLE:
    pipeline_result = _pipeline_lookup(...)
    if pipeline_result:
        primary_gas = pipeline_result
# PRIORITY 2: Check municipal/regional gas data (fallback)
elif (municipal_gas := lookup_municipal_gas(...)):
    ...
```

**Impact**: Pipeline's Smart Selector gets first choice

---

### Quick Win 4: Fix HIFLD Source to Return All Results (20 minutes)

**File**: `pipeline/sources/gas.py`

**Change**:
```python
# Lines 196-199
# OLD:
if isinstance(result, list):
    primary = result[0] if result else None  # ← Takes first blindly
else:
    primary = result

# NEW:
# Return all candidates, let Smart Selector choose
candidates = result if isinstance(result, list) else [result]
return SourceResult(
    source_name=self.name,
    utility_name=None,  # No automatic choice
    confidence_score=self.base_confidence,
    match_type='point',
    candidates=candidates,  # Smart Selector will choose
    raw_data=result
)
```

**Impact**: OpenAI sees all options, not just first

---

## Decision Matrix

### Should You Do Full Refactor?

| Factor | Full Refactor | Quick Wins Only |
|--------|---------------|-----------------|
| **Time Investment** | 6-10 days | 1 hour |
| **Risk** | Medium (regressions possible) | Low (targeted changes) |
| **Maintenance Long-term** | Much easier | Same complexity |
| **Scalability** | Easy to add sources | Hard to add sources |
| **Code Quality** | Clean, modern | Tech debt remains |
| **User Impact** | Better accuracy | Fixes known issues |

### When to Do Full Refactor:

✅ **YES, if:**
- You're getting frequent user-reported errors
- You plan to add more states/utilities
- You have 1-2 weeks for this project
- You want long-term maintainability
- Data maintenance is eating your time

❌ **NO, if:**
- This is "done" - production is stable
- You're not actively maintaining it
- Time better spent on other projects
- Quick wins solve the immediate pain

---

## Rollback & Risk Mitigation

### If Refactor Goes Wrong:

1. **Keep old system running**
   - Tag current code: `git tag pre-refactor`
   - Deploy new system as `lookup_v2()`
   - A/B test: randomly route 10% to v2

2. **Comprehensive logging**
   - Log every source result
   - Log Smart Selector reasoning
   - Compare v1 vs v2 outputs

3. **Circuit breaker**
   - If error rate > 5%, auto-rollback to v1
   - If latency > 5s, fallback to v1

4. **User feedback loop**
   - Add "Report incorrect result" button
   - Track which version produced the error
   - Use feedback to improve v2

---

## Metrics to Track

### Before & After Refactor:

| Metric | Current | Target |
|--------|---------|--------|
| Lookup latency | ~2-5s | < 2s |
| Error rate (user-reported) | ? | < 1% |
| Lines of code | 7,267 | < 2,000 |
| Data files | 51 | < 10 |
| Priority checks | 30+ | 1 (pipeline) |
| OpenAI API cost/lookup | ~$0.01 | Same |

---

## Recommended Approach

### Option A: Full Refactor (Recommended if time permits)

**Timeline**: 6-10 days
**Phases**: Data consolidation → Logic simplification → Source refactor → Testing
**Outcome**: Clean, maintainable system

### Option B: Quick Wins + Incremental Refactor

**Week 1**: Apply all 4 quick wins (1 hour)
**Week 2-3**: Phase 1 (data consolidation)
**Week 4-5**: Phase 2 (simplify lookup)
**Week 6-7**: Phase 3 (refactor sources)
**Week 8**: Testing & deployment

**Outcome**: Gradual improvement, less risk

### Option C: Quick Wins Only (Minimum viable fix)

**Timeline**: 1 hour
**Tasks**: Apply quick wins 1-4
**Outcome**: Fixes Little Elm bug, stops ZIP mapping errors

---

## Next Steps

1. **Decide**: Full refactor, incremental, or quick wins only?
2. **If refactor**: Review this doc, create detailed implementation plan
3. **If quick wins**: Apply changes, test, deploy
4. **Either way**: Set up monitoring for user-reported errors

---

## Questions for Decision Making

1. How often are you getting user-reported incorrect results?
2. Do you plan to expand to more states in next 6 months?
3. How much time can you dedicate to this project?
4. Is the current system "done" or actively evolving?
5. What's the cost of maintenance vs. refactoring?

---

## Appendix: File Inventory

### Files to Keep (Refactored)
- `utility_lookup.py` (rewritten, < 300 lines)
- `pipeline/pipeline.py` (enhanced)
- `pipeline/sources/*.py` (cleaned up)
- `gis_utility_lookup.py` (GIS API calls only)
- `data/municipal_utilities.json`
- `data/verified_addresses.json`
- `data/county_defaults.json` (consolidated)

### Files to Delete
- `state_utility_verification.py` (1,401 lines)
- All hardcoded Python dicts
- Redundant data files (~40 files)

### Files to Merge
- `data/county_utility_defaults.json` + `data/gas_county_lookups.json` → `data/county_defaults.json`

---

**Document Version**: 1.0
**Date**: 2026-01-20
**Author**: Claude (Diagnostic Analysis)
**Purpose**: Refactoring assessment for Cascade/development team
