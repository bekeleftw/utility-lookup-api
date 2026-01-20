# Utility Lookup System - Code Review Brief

## Purpose of This Document

This document is for **Claude Code** to conduct a thorough code review. It combines:
1. Windsurf's current implementation overview
2. Architectural requirements from design sessions
3. Specific verification criteria and questions
4. Known gaps between design and implementation

---

## CRITICAL REVIEW PRIORITIES

### Priority 1: Verify the "100% Accuracy" Claim

Windsurf reported 100% accuracy on the test suite. This is suspicious because:
- They also reported "fixing golden test expectations" - which could mean changing expected answers to match outputs
- 100% on messy GIS boundary data is essentially impossible
- Test suite may be too small (53 cases) or overfit

**VERIFY:**
1. How many of the 53 test cases had their expected values changed recently?
2. Are there any git commits showing "fixed expectations" changes?
3. Does the test suite include true edge cases (municipal/IOU boundaries, recent annexations)?
4. What is the distribution of test cases by state? Are they clustered?

### Priority 2: OpenAI Integration Actually Working

The OpenAI "Smart Selector" was supposed to be the key differentiator. Verify it's actually being called.

**VERIFY:**
1. Is `OPENAI_API_KEY` actually being loaded? Check all code paths.
2. What triggers the OpenAI call? Is it only when sources disagree?
3. Add logging/print to track: How often is OpenAI called during the test suite run?
4. If OpenAI is never called, the cross-validation isn't doing anything useful.

### Priority 3: The Converse, TX Test Case

The entire refactor started because this address returned GVEC (wrong) instead of CPS Energy (correct):
- **Address**: 9212 Groff Landing, Converse, TX 78109
- **Correct utility**: CPS Energy
- **Wrong result**: Guadalupe Valley Electric Cooperative (GVEC)

**VERIFY:**
1. Is this specific address in the test suite?
2. What does the system return for it now?
3. If it's correct now, WHY is it correct? Which source fixed it?

---

## Current Implementation Overview (from Windsurf)

### Project Structure

```
Utility Provider scrape/
├── api.py                      # Flask API server
├── utility_lookup.py           # Core lookup logic (~3200 lines)
├── gis_utility_lookup.py       # GIS API integrations (~1400 lines)
├── pipeline/                   # New modular pipeline
│   ├── interfaces.py           # DataSource, SourceResult, PipelineResult
│   ├── pipeline.py             # LookupPipeline orchestrator
│   └── sources/
│       ├── electric.py         # Electric utility sources
│       └── gas.py              # Gas utility sources
├── test_addresses.py           # Golden test suite (53 cases)
└── [various supporting modules]
```

### Entry Points

1. **API**: `POST /api/lookup` in `api.py`
2. **Main function**: `lookup_utilities_by_address()` in `utility_lookup.py:1854`
3. **Pipeline**: `LookupPipeline.lookup()` in `pipeline/pipeline.py:54`

### Current Source Priority (Electric)

```python
1. StateGISElectricSource (confidence: 85)
2. MunicipalElectricSource (confidence: 88)
3. CoopSource (confidence: 68)
4. EIASource (confidence: 70)
5. HIFLDElectricSource (confidence: 58)
6. CountyDefaultElectricSource (confidence: 50)
```

### Current Source Priority (Gas)

```python
1. StateGISGasSource (confidence: 85)
2. MunicipalGasSource (confidence: 88)
3. ZIPMappingGasSource (confidence: 65)
4. HIFLDGasSource (confidence: 58)
5. CountyDefaultGasSource (confidence: 50)
```

---

## Design Requirements (What SHOULD Be Implemented)

### Multi-Source Cross-Validation Architecture

The system should query multiple sources and compare results:

```
┌─────────────────────────────────────────────────────────────┐
│                    Lookup Pipeline                           │
├─────────────────────────────────────────────────────────────┤
│  1. Query ALL relevant sources in parallel                  │
│     ├── State GIS API (if available for state)              │
│     ├── Municipal database                                  │
│     ├── HIFLD national layer                                │
│     └── EIA ZIP mapping                                     │
│                           │                                 │
│                           ▼                                 │
│  2. Compare Results                                         │
│     ├── All sources agree? → Return with boosted confidence │
│     └── Sources disagree? → Call OpenAI Smart Selector      │
│                           │                                 │
│                           ▼                                 │
│  3. OpenAI Smart Selector (on disagreement)                 │
│     ├── Evaluates all source results                        │
│     ├── Understands name variations (CPS = City Public Svc) │
│     ├── Weighs source authority                             │
│     └── Returns reasoned selection with explanation         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### OpenAI Smart Selector Design

**When to call**: ANY time sources disagree (no threshold, no percentage cutoff)

**Prompt should include**:
- All source results with their confidence scores
- The address context (city name often indicates municipal)
- Rules about municipal vs IOU vs Co-op territory logic

**Expected prompt structure** (verify this matches implementation):
```python
prompt = f"""You are a utility service territory expert. Given an address and results from multiple data sources, determine the most likely correct {utility_type} utility provider.

ADDRESS:
{address}
{city}, {state} {zip_code}

SOURCE RESULTS:
{sources_text}  # e.g., "- State GIS: CPS Energy (confidence: 0.92)"
                #       "- HIFLD: GVEC (confidence: 0.88)"

INSTRUCTIONS:
1. Consider that different sources may use different names for the same utility
2. State GIS data is generally most authoritative
3. If a municipal utility appears inside a co-op/IOU territory, the municipal is likely correct for city addresses
4. Consider the address context (city name often indicates municipal utility)

Respond in JSON format with selected_utility, reasoning, confidence, etc.
"""
```

### HIFLD Gas Integration

HIFLD has a natural gas layer that should be integrated:

**Endpoint**: `maps.nccs.nasa.gov/mapping/rest/services/hifld_open/energy/FeatureServer/29`

**VERIFY**: Is this endpoint actually being queried? The gas sources table in the overview is vague ("Railroad Commission GIS", "CPUC GIS") without actual URLs.

### "No Gas Service" Handling

Unlike electric (everyone has service), many areas have NO gas service at all.

**Expected behavior**:
```json
{
  "gas_utility": null,
  "gas_available": false,
  "confidence": 0.85,
  "reason": "Location outside all known gas service territories"
}
```

**VERIFY**: Does the system distinguish between "no data" and "no gas service area"?

---

## Specific Code Review Questions

### 1. Pipeline Architecture

In `pipeline/pipeline.py`:
- Is `lookup()` actually querying multiple sources?
- Are results being compared/cross-validated?
- What triggers the OpenAI call? Is it `if sources_disagree` or something else?
- Is there dead code from the "legacy" path that should be removed?

### 2. OpenAI Integration

In `utility_lookup.py:1556-1610` (SERP analysis):
- Is this the ONLY place OpenAI is called?
- The prompt mentions "SERP results" - is this actually using web search results or source comparison?
- Is the API key being loaded correctly? Check all `.env` loading paths.

In `pipeline/pipeline.py:364-419` (disagreement resolution):
- Does this actually call OpenAI or just use rule-based logic?
- What happens if OpenAI API fails? Is there fallback logic?

### 3. Test Suite Integrity

In `test_addresses.py`:
- List all addresses and their expected utilities
- Flag any that were recently changed
- Are there addresses specifically testing boundary cases?
- Is the Converse, TX address included?

### 4. Gas Source Implementation

In `pipeline/sources/gas.py`:
- What endpoints are actually being queried?
- Is HIFLD Gas (FeatureServer/29) included?
- Are the state-specific gas APIs real or placeholders?

The overview lists gas APIs for 13 states but no actual URLs. This is suspicious.

### 5. Confidence Scoring

- Is confidence actually being calculated based on source agreement?
- The design called for boosting confidence by 20 when sources agree - is this implemented?
- Is there any logging of confidence calculations?

---

## Verified API Endpoints (From Design Sessions)

### Electric - HIFLD National
```
https://services1.arcgis.com/Hp6G80Pky0om7QvQ/arcgis/rest/services/Electric_Retail_Service_Territories_2/FeatureServer/0
```

### Gas - HIFLD National
```
https://maps.nccs.nasa.gov/mapping/rest/services/hifld_open/energy/FeatureServer/29
```

### Gas - California CEC
```
https://services3.arcgis.com/bWPjFyq029ChCGur/arcgis/rest/services/Natural_Gas_Service_Area/FeatureServer/0
```

### Gas - New Jersey NJDEP
```
https://mapsdep.nj.gov/arcgis/rest/services/Features/Utilities/MapServer/11
```

### Water - Arkansas (Tier 1, 98% coverage)
```
https://gis.arkansas.gov/arcgis/rest/services/ADEQ/Utilities/FeatureServer/15
```

**VERIFY**: Are these exact endpoints in the codebase? Or are there different/older URLs?

---

## Red Flags to Investigate

1. **"Fixed golden test expectations"** - Were answers changed to match outputs?

2. **Gas API table has no URLs** - The electric table has full URLs, gas table has vague descriptions like "Railroad Commission GIS". This suggests gas might be incomplete.

3. **100% accuracy claim** - On 53 test cases with messy real-world data. Statistically improbable.

4. **Pipeline vs Legacy** - There's a `use_pipeline=True` flag. Is the pipeline actually being used? Or does the legacy code path run?

5. **SERP verification is "slow" (25-30s)** - Is it actually being called during lookups? Or is it disabled/bypassed?

6. **3200 lines in utility_lookup.py** - This is a code smell. Is most of this dead code from the "legacy" path?

---

## Deliverables from This Review

Please provide:

1. **Accuracy Assessment**: Run the test suite with verbose logging. Report:
   - How many OpenAI calls were made
   - Which test cases triggered disagreement
   - Which test cases have changed expected values recently

2. **Endpoint Verification**: List every GIS endpoint actually being called with:
   - Full URL
   - What states it covers
   - Whether it's actually queryable (test one request)

3. **Architecture Audit**: Does the implementation match the design?
   - Multi-source parallel querying: YES/NO
   - Cross-validation comparison: YES/NO
   - OpenAI on disagreement: YES/NO
   - Confidence boosting on agreement: YES/NO

4. **Converse, TX Deep Dive**: 
   - What does the system return for 9212 Groff Landing, Converse, TX 78109?
   - Which source(s) returned which utility?
   - Did OpenAI get involved?

5. **Recommended Fixes**: Prioritized list of what needs to change.

---

## Appendix: Original Problem Statement

The utility lookup system helps property managers identify which electric, gas, and water utilities serve a given address. Accuracy is critical because:
- Tenants need to set up service at the correct utility
- Wrong information causes failed setups, tenant frustration, delayed move-ins
- Some areas have overlapping or contested territories

The Converse, TX case exemplified the problem: HIFLD data showed the address in GVEC territory, but the actual provider is CPS Energy. The solution was multi-source cross-validation with an LLM to resolve disagreements intelligently.
