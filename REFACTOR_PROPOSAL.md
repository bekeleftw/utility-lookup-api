# Utility Lookup System Refactor Proposal

**Date:** January 19, 2026  
**Author:** Windsurf Cascade  
**For Review By:** Claude

---

## Executive Summary

The utility lookup system has grown organically over several months, accumulating ~3,000 lines of code in `utility_lookup.py` alone. While functional, the architecture has become difficult to maintain and extend. This document proposes a refactor to a pipeline-based architecture that would improve speed, accuracy, and maintainability.

---

## Current State Analysis

### File Structure

```
utility_lookup.py          (~3,100 lines) - Main lookup logic, SERP verification, formatting
state_utility_verification.py (~1,400 lines) - State-specific verification, gas mappings
utility_website_verification.py (~3,600 lines) - 80+ utility territory verifiers
rural_utilities.py         (~240 lines) - Co-op and county default lookups
special_districts.py       (~330 lines) - MUD/CDD lookups
confidence_scoring.py      (~340 lines) - Confidence calculation (underutilized)
cross_validation.py        (~300 lines) - Cross-validation logic (not integrated)
brand_resolver.py          (~310 lines) - Utility name normalization
serp_verification.py       (~480 lines) - SERP verification with caching (new)
```

### Current Lookup Flow (Electric Example)

```python
def lookup_electric_only(lat, lon, city, county, state, zip_code, address):
    # Priority 0: GIS-based lookup for specific states (NJ, AR, DE, HI, RI)
    if GIS_LOOKUP_AVAILABLE and state in ('NJ', 'AR', 'DE', 'HI', 'RI'):
        gis_electric = lookup_electric_utility_gis(lat, lon, state)
        if gis_electric:
            return _add_deregulated_info(result, state, zip_code)
    
    # Priority 1: Municipal utilities (exempt from deregulation)
    municipal_electric = lookup_municipal_electric(state, city, zip_code)
    if municipal_electric:
        return _add_deregulated_info(result, state, zip_code)
    
    # Priority 2: Electric cooperatives by ZIP
    coop = lookup_coop_by_zip(zip_code, state)
    if coop:
        return result  # Co-ops exempt from deregulation
    
    # Priority 3: EIA ZIP lookup
    eia_result = get_eia_utility_by_zip(zip_code)
    if eia_result:
        return _add_deregulated_info(result, state, zip_code)
    
    # Priority 4: HIFLD polygon lookup
    electric = lookup_electric_utility(lon, lat)
    if not electric:
        # Fallback to county defaults
        county_default = lookup_county_default_electric(county, state)
        if county_default:
            return _add_deregulated_info(result, state, zip_code)
        return None
    
    # Priority 5: Verify with state-specific data
    verification = verify_electric_provider(state, zip_code, city, county, candidates)
    
    # Priority 6: Brand resolution
    brand, legal = resolve_brand_name_with_fallback(primary['NAME'], state)
    
    # Priority 7: Deregulated market adjustment
    if is_deregulated_state(state):
        primary = adjust_electric_result_for_deregulation(primary, state, zip_code)
    
    # Priority 8: Website verification enhancement
    if address and state in get_supported_states():
        primary = enhance_lookup_with_verification(primary, address, city, state, zip_code)
    
    return primary
```

### Problems with Current Architecture

#### 1. Sequential Fallback (Slow)
Each data source is queried one at a time. If the first source fails, we try the second, etc. This means:
- Best case: 1 query (~50ms)
- Worst case: 8 queries (~400ms)
- Average: 3-4 queries (~150-200ms)

#### 2. First Match Wins (Inaccurate)
The first source to return a result is used, even if a later source would have higher confidence. Example:
- HIFLD returns "Duke Energy" (medium confidence)
- County default would return "Nashville Electric Service" (high confidence for Nashville)
- We return Duke Energy because HIFLD was checked first

#### 3. Confidence Scoring is Disconnected
`confidence_scoring.py` has a sophisticated scoring system with:
- Source quality scores (15-95 points)
- Geographic precision bonuses (0-15 points)
- SERP verification adjustments (+20/-25 points)
- Cross-validation bonuses (+10-20 points)
- Problem area penalties (-15 points)

But this is only partially used. Most lookups just set `_confidence: "high"` or `"medium"` as strings.

#### 4. Cross-Validation Not Integrated
`cross_validation.py` can compare results from multiple sources and detect disagreements. But it's never called from the main lookup flow.

#### 5. Duplicated Logic
Each utility type (electric, gas, water) has its own lookup function with similar but slightly different logic:
- Municipal check
- GIS lookup
- County fallback
- Verification step
- Brand resolution

Changes must be made in 3 places.

#### 6. Hard to Add New Data Sources
Adding a new data source (e.g., a new state GIS API) requires:
1. Writing the query function
2. Finding the right place in the priority chain
3. Adding conditional logic
4. Testing all code paths

#### 7. Inline Imports
Functions import dependencies inline:
```python
def lookup_gas_only(...):
    from rural_utilities import lookup_county_default_gas  # Line 2798
    from state_utility_verification import get_state_gas_ldc  # Line 2798
```
This makes dependencies unclear and slows down execution.

---

## Data Sources Inventory

### Electric (8 sources)
| Source | Type | Coverage | Confidence |
|--------|------|----------|------------|
| State GIS APIs | Point-in-polygon | 33 states + DC | High |
| Municipal database | City lookup | ~500 cities | High |
| Electric co-ops | ZIP/county | Rural areas | High |
| EIA Form 861 | ZIP lookup | National | Medium |
| HIFLD polygons | Point-in-polygon | National | Medium |
| County defaults | County lookup | All 3,159 counties | Medium |
| Utility website verification | Territory check | 80+ utilities | High |
| SERP verification | Web search | On-demand | Variable |

### Gas (6 sources)
| Source | Type | Coverage | Confidence |
|--------|------|----------|------------|
| State GIS APIs | Point-in-polygon | 13 states | High |
| Municipal database | City lookup | ~200 cities | High |
| ZIP prefix mappings | 3-digit ZIP | All 50 states | High |
| HIFLD polygons | Point-in-polygon | Partial | Medium |
| County defaults | County lookup | Partial | Low |
| SERP verification | Web search | On-demand | Variable |

### Water (5 sources)
| Source | Type | Coverage | Confidence |
|--------|------|----------|------------|
| EPA CWS boundaries | Point-in-polygon | National | High |
| Municipal database | City lookup | ~500 cities | High |
| Special districts (MUDs) | Point-in-polygon | TX (2,268 districts) | High |
| Supplemental data | City overrides | Manual entries | High |
| EPA SDWIS | Name matching | National | Medium |

---

## Proposed Architecture

### Pipeline Design

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          LOOKUP PIPELINE                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────┐                                                        │
│  │  1. GEOCODE  │  Parse address → lat/lon, city, county, state, zip    │
│  └──────┬───────┘                                                        │
│         │                                                                │
│         ▼                                                                │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  2. QUERY DATA SOURCES (PARALLEL)                                 │   │
│  │                                                                    │   │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐     │   │
│  │  │State GIS│ │Municipal│ │  Co-op  │ │  EIA    │ │  HIFLD  │     │   │
│  │  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘     │   │
│  │       │           │           │           │           │           │   │
│  │       └───────────┴───────────┴───────────┴───────────┘           │   │
│  │                               │                                    │   │
│  └───────────────────────────────┼──────────────────────────────────┘   │
│                                  │                                       │
│                                  ▼                                       │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  3. CROSS-VALIDATE                                                 │  │
│  │                                                                     │  │
│  │  Compare all results:                                               │  │
│  │  - Group by normalized utility name                                 │  │
│  │  - Detect agreement/disagreement                                    │  │
│  │  - Calculate confidence adjustments                                 │  │
│  │  - Flag conflicts for review                                        │  │
│  └───────────────────────────────┬───────────────────────────────────┘  │
│                                  │                                       │
│                                  ▼                                       │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  4. SELECT PRIMARY                                                 │  │
│  │                                                                     │  │
│  │  Pick best result based on:                                         │  │
│  │  - Source confidence score                                          │  │
│  │  - Geographic precision                                             │  │
│  │  - Cross-validation agreement                                       │  │
│  │  - Recency of data                                                  │  │
│  └───────────────────────────────┬───────────────────────────────────┘  │
│                                  │                                       │
│                                  ▼                                       │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  5. ENRICH                                                         │  │
│  │                                                                     │  │
│  │  - Add phone/website from utility database                          │  │
│  │  - Resolve brand name (legal → consumer-facing)                     │  │
│  │  - Add deregulated market info (TX, PA, etc.)                       │  │
│  │  - Add confidence details for UI                                    │  │
│  └───────────────────────────────┬───────────────────────────────────┘  │
│                                  │                                       │
│                                  ▼                                       │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  6. VERIFY (OPTIONAL)                                              │  │
│  │                                                                     │  │
│  │  If confidence < threshold OR known problem area:                   │  │
│  │  - Query SERP for verification                                      │  │
│  │  - Adjust confidence based on result                                │  │
│  │  - Log disagreements for review                                     │  │
│  └───────────────────────────────┬───────────────────────────────────┘  │
│                                  │                                       │
│                                  ▼                                       │
│                           ┌──────────────┐                               │
│                           │   RESPONSE   │                               │
│                           └──────────────┘                               │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Core Interfaces

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional
from enum import Enum

class UtilityType(Enum):
    ELECTRIC = "electric"
    GAS = "gas"
    WATER = "water"

@dataclass
class LookupContext:
    """Input context for all data sources."""
    lat: float
    lon: float
    address: str
    city: str
    county: str
    state: str
    zip_code: str
    utility_type: UtilityType

@dataclass
class SourceResult:
    """Result from a single data source."""
    source_name: str
    utility_name: Optional[str]
    confidence_score: int  # 0-100
    match_type: str  # 'point', 'zip', 'county', 'city'
    phone: Optional[str] = None
    website: Optional[str] = None
    raw_data: Optional[dict] = None
    
class DataSource(ABC):
    """Abstract base class for all data sources."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this source."""
        pass
    
    @property
    @abstractmethod
    def supported_types(self) -> List[UtilityType]:
        """Which utility types this source can look up."""
        pass
    
    @property
    @abstractmethod
    def base_confidence(self) -> int:
        """Base confidence score for this source (0-100)."""
        pass
    
    @abstractmethod
    def query(self, context: LookupContext) -> Optional[SourceResult]:
        """
        Query this data source.
        Returns SourceResult if found, None if not applicable.
        Should be fast (<100ms) and handle its own errors.
        """
        pass
    
    def supports(self, utility_type: UtilityType) -> bool:
        """Check if this source supports the given utility type."""
        return utility_type in self.supported_types

@dataclass
class PipelineResult:
    """Final result from the lookup pipeline."""
    utility_name: str
    utility_type: UtilityType
    confidence_score: int
    confidence_level: str  # 'verified', 'high', 'medium', 'low'
    source: str
    phone: Optional[str] = None
    website: Optional[str] = None
    
    # Cross-validation info
    agreeing_sources: List[str] = None
    disagreeing_sources: List[str] = None
    
    # Enrichment
    brand_name: Optional[str] = None
    legal_name: Optional[str] = None
    deregulated_market: bool = False
    
    # Verification
    serp_verified: Optional[bool] = None
    
    # Debug info
    all_results: List[SourceResult] = None
    timing_ms: int = 0
```

### Data Source Implementations

```python
class StateGISSource(DataSource):
    """Query state-specific GIS APIs."""
    
    name = "state_gis"
    supported_types = [UtilityType.ELECTRIC, UtilityType.GAS]
    base_confidence = 90
    
    # States with GIS APIs
    ELECTRIC_STATES = {'NJ', 'AR', 'DE', 'HI', 'RI', 'CA', 'TX', ...}  # 33 states
    GAS_STATES = {'TX', 'CA', 'IL', 'PA', 'NY', ...}  # 13 states
    
    def query(self, context: LookupContext) -> Optional[SourceResult]:
        if context.utility_type == UtilityType.ELECTRIC:
            if context.state not in self.ELECTRIC_STATES:
                return None
            result = lookup_electric_utility_gis(context.lat, context.lon, context.state)
        elif context.utility_type == UtilityType.GAS:
            if context.state not in self.GAS_STATES:
                return None
            result = lookup_gas_utility_gis(context.lat, context.lon, context.state)
        else:
            return None
        
        if not result:
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

class MunicipalSource(DataSource):
    """Look up municipal utilities by city."""
    
    name = "municipal"
    supported_types = [UtilityType.ELECTRIC, UtilityType.GAS, UtilityType.WATER]
    base_confidence = 88
    
    def query(self, context: LookupContext) -> Optional[SourceResult]:
        if context.utility_type == UtilityType.ELECTRIC:
            result = lookup_municipal_electric(context.state, context.city, context.zip_code)
        elif context.utility_type == UtilityType.GAS:
            result = lookup_municipal_gas(context.state, context.city, context.zip_code)
        elif context.utility_type == UtilityType.WATER:
            result = lookup_municipal_water(context.state, context.city, context.zip_code)
        else:
            return None
        
        if not result:
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

# Similar implementations for:
# - CoopSource (electric cooperatives)
# - EIASource (EIA Form 861)
# - HIFLDSource (HIFLD polygons)
# - CountyDefaultSource (county-level defaults)
# - ZIPMappingSource (gas ZIP prefix mappings)
# - SpecialDistrictSource (MUDs/CDDs)
# - EPASource (water systems)
# - UtilityWebsiteSource (territory verification)
```

### Pipeline Orchestrator

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List

class LookupPipeline:
    """Orchestrates the lookup process."""
    
    def __init__(self):
        self.sources: List[DataSource] = [
            StateGISSource(),
            MunicipalSource(),
            CoopSource(),
            EIASource(),
            HIFLDSource(),
            CountyDefaultSource(),
            ZIPMappingSource(),
            SpecialDistrictSource(),
            EPASource(),
        ]
        self.executor = ThreadPoolExecutor(max_workers=5)
    
    def lookup(self, context: LookupContext) -> PipelineResult:
        """
        Main entry point for utility lookup.
        """
        start_time = time.time()
        
        # 1. Query all applicable sources in parallel
        applicable_sources = [s for s in self.sources if s.supports(context.utility_type)]
        results = self._query_parallel(applicable_sources, context)
        
        # 2. Cross-validate results
        cv_result = cross_validate([
            SourceResult(r.source_name, r.utility_name, r.confidence_score)
            for r in results if r
        ])
        
        # 3. Select primary result
        primary = self._select_primary(results, cv_result)
        
        if not primary:
            return PipelineResult(
                utility_name=None,
                utility_type=context.utility_type,
                confidence_score=0,
                confidence_level='none',
                source='none'
            )
        
        # 4. Enrich result
        enriched = self._enrich(primary, context)
        
        # 5. Optional SERP verification
        if enriched.confidence_score < 70:
            enriched = self._verify_with_serp(enriched, context)
        
        enriched.timing_ms = int((time.time() - start_time) * 1000)
        enriched.all_results = results
        
        return enriched
    
    def _query_parallel(self, sources: List[DataSource], context: LookupContext) -> List[SourceResult]:
        """Query multiple sources in parallel."""
        futures = []
        for source in sources:
            future = self.executor.submit(self._safe_query, source, context)
            futures.append(future)
        
        results = []
        for future in futures:
            try:
                result = future.result(timeout=2.0)  # 2 second timeout per source
                if result:
                    results.append(result)
            except Exception:
                pass
        
        return results
    
    def _safe_query(self, source: DataSource, context: LookupContext) -> Optional[SourceResult]:
        """Query a source with error handling."""
        try:
            return source.query(context)
        except Exception as e:
            print(f"Error querying {source.name}: {e}")
            return None
    
    def _select_primary(self, results: List[SourceResult], cv_result) -> Optional[SourceResult]:
        """Select the best result based on confidence and cross-validation."""
        if not results:
            return None
        
        # Score each result
        scored = []
        for r in results:
            score = r.confidence_score
            
            # Bonus for cross-validation agreement
            if r.source_name in cv_result.agreeing_sources:
                score += cv_result.confidence_adjustment
            
            # Bonus for geographic precision
            precision_bonus = {'point': 15, 'zip': 5, 'county': 1, 'city': 8}.get(r.match_type, 0)
            score += precision_bonus
            
            scored.append((score, r))
        
        # Return highest scoring result
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]
    
    def _enrich(self, result: SourceResult, context: LookupContext) -> PipelineResult:
        """Enrich result with additional data."""
        # Brand resolution
        brand, legal = resolve_brand_name_with_fallback(result.utility_name, context.state)
        
        # Deregulated market check
        deregulated = is_deregulated_state(context.state)
        
        # Confidence level
        if result.confidence_score >= 85:
            level = 'verified'
        elif result.confidence_score >= 70:
            level = 'high'
        elif result.confidence_score >= 50:
            level = 'medium'
        else:
            level = 'low'
        
        return PipelineResult(
            utility_name=brand or result.utility_name,
            utility_type=context.utility_type,
            confidence_score=result.confidence_score,
            confidence_level=level,
            source=result.source_name,
            phone=result.phone,
            website=result.website,
            brand_name=brand,
            legal_name=legal,
            deregulated_market=deregulated
        )
```

---

## Estimated Impact

### Speed Improvement

| Metric | Current | Refactored | Improvement |
|--------|---------|------------|-------------|
| Best case | 50ms | 50ms | - |
| Average case | 150-200ms | 80-100ms | **40-50% faster** |
| Worst case | 400ms | 150ms | **60% faster** |

**Why:** Parallel queries to all sources instead of sequential fallback.

### Accuracy Improvement

| Metric | Current | Refactored | Improvement |
|--------|---------|------------|-------------|
| Electric | ~100% | ~100% | - |
| Gas | ~89% | ~95% | **+6%** |
| Water | ~85% | ~90% | **+5%** |

**Why:** Cross-validation catches errors where sources disagree. Best confidence wins instead of first match.

### Maintainability Improvement

| Metric | Current | Refactored |
|--------|---------|------------|
| Lines in utility_lookup.py | 3,100 | ~500 |
| Adding new data source | 4-6 hours | 1-2 hours |
| Testing a single source | Difficult | Easy (isolated) |
| Understanding the flow | Complex | Clear pipeline |

### Cost Optimization

| Metric | Current | Refactored |
|--------|---------|------------|
| SERP calls | Variable | Only when needed |
| OpenAI calls | Per lookup | Only low confidence |
| Caching | Partial | Systematic |

---

## Migration Strategy

### Phase 1: Define Interfaces (Low Risk)
- Create `pipeline/` directory
- Define `DataSource`, `SourceResult`, `PipelineResult` classes
- No changes to existing code

### Phase 2: Wrap Existing Sources (Low Risk)
- Create DataSource implementations that wrap existing functions
- Test each source independently
- No changes to main lookup flow

### Phase 3: Build Pipeline Orchestrator (Medium Risk)
- Implement `LookupPipeline` class
- Add parallel query execution
- Integrate cross-validation

### Phase 4: Migrate Lookups (Higher Risk)
- Replace `lookup_electric_only` with pipeline
- Replace `lookup_gas_only` with pipeline
- Replace `lookup_water_only` with pipeline
- Extensive regression testing

### Phase 5: Cleanup (Low Risk)
- Remove deprecated code
- Update documentation
- Performance tuning

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Regression in accuracy | Medium | High | Extensive test suite before migration |
| Performance degradation | Low | Medium | Benchmark before/after each phase |
| Incomplete migration | Low | Medium | Feature flags to switch between old/new |
| Parallel query issues | Medium | Low | Timeouts and error handling per source |

---

## Questions for Claude

1. **Architecture:** Does the pipeline design make sense? Are there better patterns for this use case?

2. **Parallel Queries:** Is ThreadPoolExecutor the right choice, or should we use asyncio? The data sources are mostly I/O bound (HTTP requests, file reads).

3. **Cross-Validation Integration:** Should cross-validation happen before or after source selection? Current proposal is before (to inform selection).

4. **Confidence Scoring:** The current system has numeric scores (0-100) but the API returns string levels ('high', 'medium', 'low'). Should we expose numeric scores to the frontend?

5. **Caching Strategy:** Should we cache at the source level (each source caches its own results) or at the pipeline level (cache final results)?

6. **Testing Strategy:** What's the best way to ensure no regressions? Should we build a test suite of known addresses with expected results before starting?

7. **Incremental vs Big Bang:** Is it better to migrate one utility type at a time (electric → gas → water) or all at once?

---

## Appendix: Current Function Call Graph

```
lookup_utilities()
├── geocode_address()
├── lookup_electric_only()
│   ├── lookup_electric_utility_gis()
│   ├── lookup_municipal_electric()
│   ├── lookup_coop_by_zip()
│   ├── get_eia_utility_by_zip()
│   ├── lookup_electric_utility()  # HIFLD
│   ├── lookup_coop_by_county()
│   ├── lookup_county_default_electric()
│   ├── verify_electric_provider()
│   ├── resolve_brand_name_with_fallback()
│   ├── is_deregulated_state()
│   ├── adjust_electric_result_for_deregulation()
│   └── enhance_lookup_with_verification()
├── lookup_gas_only()
│   ├── lookup_municipal_gas()
│   ├── lookup_gas_utility()  # HIFLD
│   ├── get_state_gas_ldc()
│   ├── lookup_county_default_gas()
│   ├── is_likely_propane_area()
│   ├── verify_gas_provider()
│   └── resolve_brand_name_with_fallback()
├── lookup_water_only()
│   ├── lookup_water_utility_gis()
│   ├── lookup_municipal_water()
│   ├── lookup_special_district()
│   ├── _check_water_supplemental()
│   └── lookup_water_utility()  # EPA
└── lookup_internet_only()
    └── lookup_internet_providers()  # Playwright
```

---

*Document prepared for Claude review - January 19, 2026*
