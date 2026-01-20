# Utility Lookup System - Codebase Overview

This document provides a comprehensive overview of the utility lookup system for onboarding AI assistants for code review.

---

## 1. Project Structure

### Directory Layout

```
Utility Provider scrape/
├── api.py                      # Flask API server (main entry point for Railway)
├── utility_lookup.py           # Core lookup logic (~3200 lines, main orchestrator)
├── gis_utility_lookup.py       # GIS API integrations for all states (~1400 lines)
├── pipeline/                   # New modular pipeline architecture
│   ├── __init__.py
│   ├── interfaces.py           # DataSource, SourceResult, PipelineResult classes
│   ├── pipeline.py             # LookupPipeline orchestrator with cross-validation
│   └── sources/
│       ├── electric.py         # Electric utility data sources
│       └── gas.py              # Gas utility data sources
├── webflow_embed.html          # Frontend widget for Webflow integration
├── test_addresses.py           # Golden test suite (53 test cases)
├── export_to_postgres.py       # Script to export FCC BDC data to PostgreSQL
├── requirements.txt            # Python dependencies
├── Dockerfile                  # Railway deployment config
│
├── # Supporting modules
├── address_cache.py            # Caching layer for geocoding
├── address_inference.py        # Address parsing and normalization
├── brand_resolver.py           # Utility brand name resolution
├── confidence_scoring.py       # Confidence calculation logic
├── cross_validation.py         # Multi-source validation
├── deregulated_markets.py      # Deregulated electricity market handling
├── findenergy_lookup.py        # FindEnergy.com integration
├── geocoding.py                # Geocoding utilities
├── ml_enhancements.py          # ML-based predictions
├── municipal_utilities.py      # Municipal utility database
├── propane_service.py          # Propane area detection
├── rural_utilities.py          # Electric cooperative lookups
├── serp_verification.py        # Google SERP verification
├── special_areas.py            # Special district detection
├── special_districts.py        # MUD/CDD handling (Texas, Florida)
├── state_utility_verification.py # State-specific verification rules
├── well_septic.py              # Private well/septic detection
│
├── # Data files
├── eia_zip_utility_lookup.json # EIA Form 861 ZIP-to-utility mapping
├── water_utility_lookup.json   # EPA SDWIS water utility data
├── water_utilities_supplemental.json # Curated water utility overrides
├── iou_zipcodes.csv            # Investor-owned utility ZIP mappings
└── bdc_internet_new.db         # FCC Broadband Data Collection (55GB SQLite)
```

### Entry Points

1. **API Server** (`api.py`):
   - `POST /api/lookup` - Main lookup endpoint
   - `GET /api/lookup?address=...` - GET variant
   - `POST /api/lookup/stream` - Server-sent events streaming
   - `GET /api/health` - Health check

2. **Main Lookup Function** (`utility_lookup.py:1854`):
   ```python
   def lookup_utilities_by_address(
       address: str,
       filter_by_city: bool = True,
       verify_with_serp: bool = False,
       selected_utilities: list = None,  # ['electric', 'gas', 'water', 'internet']
       skip_internet: bool = False,
       use_pipeline: bool = True
   ) -> Optional[Dict]
   ```

3. **Pipeline Entry** (`pipeline/pipeline.py:54`):
   ```python
   def lookup(self, context: LookupContext) -> PipelineResult
   ```

---

## 2. Data Sources

### Electric Utility GIS APIs

| State | API URL | Fields | Notes |
|-------|---------|--------|-------|
| **TX** | `services.twdb.texas.gov/arcgis/.../Public_Utility_Commission_CCN_Water/MapServer/0` | UTILITY, CCN_NO | PUC CCN boundaries |
| **CA** | `services3.arcgis.com/.../ElectricLoadServingEntities_IOU_POU/FeatureServer/0` | Utility, Type, URL, Phone | IOUs and POUs |
| **NJ** | `mapsdep.nj.gov/arcgis/.../Utilities/MapServer/10` | NAME, DISTRICT, TYPE | BPU territories |
| **AR** | `gis.arkansas.gov/arcgis/.../Utilities/FeatureServer/11` | * | PSC boundaries |
| **DE** | `enterprise.firstmaptest.delaware.gov/arcgis/.../DE_CPCN/FeatureServer/2` | ELECTRICPROVIDER | CPCN areas |
| **HI** | `services2.arcgis.com/tONuKShmVp7yWQJL/.../PSC_CurrentCAs/FeatureServer/4` | UTILITY_NA, County | Multiple layers (4,3,1) |
| **PA** | `services.arcgis.com/rD2ylXRs80UroD90/.../PA_Electric_Service_Territories/FeatureServer/0` | NAME | PUC territories |
| **WI** | `services.arcgis.com/rD2ylXRs80UroD90/.../Utility_Service_Territories_in_WI/FeatureServer` | UTIL_LAB, CITY | Multiple layers |
| **OH** | `services.arcgis.com/yzB9WM8W0BO3Ql7d/.../Utilities_Boundaries/FeatureServer/0` | COMPNAME, HOLDINGCO | PUCO boundaries |
| **MI** | `services3.arcgis.com/.../ELECTRIC_UTILITY_SERVICE_AREA_MI_WFL1/FeatureServer/16` | Name, Type, Website, Phone | MPSC territories |
| **IL** | Multiple layers for IOU/MUNI/COOP | COMPANY_NAME, COMPANY_TYPE | ICC boundaries |
| **NY** | `services2.arcgis.com/.../NYS_ElectricUtilityServiceTerritories/FeatureServer/0` | comp_full, comp_short | PSC territories |
| **MO** | `services1.arcgis.com/.../2020_Electric_Service_Area_web/FeatureServer/0` | UTIL_NAME, OWNER, Type | PSC boundaries |
| **SC** | `maps.palmettoeoc.net/arcgis/.../sc_utility_providers/MapServer/3` | Provider, EMSYS | Emergency services |
| **GA** | `services.arcgis.com/vPD5PVLI6sfkZ5E4/.../Electrical_Service_Boundaries/FeatureServer/14` | Owner, ESB_Type | PSC boundaries |
| **VA** | `services3.arcgis.com/.../VA_Electric_2016/FeatureServer/0` | Provider, Utility, Website | SCC territories |
| **IN** | `gisdata.in.gov/server/.../IURC_Prod_Boundaries_View/FeatureServer/0` | utilityname | IURC boundaries |
| **IA** | `services1.arcgis.com/.../2025_Electric/FeatureServer/0` | Company_Na, Main_Pho_1 | IUB territories |
| **NC** | Multiple layers for Coop/Muni/IOU | NAME, TYPE, HOLDING_CO | NCUC boundaries |
| **MN** | Multiple layers at `feat.gisdata.mn.gov` | full_name, type, phone | PUC boundaries |
| **WA** | `services2.arcgis.com/.../WA_Electric_Utilities/FeatureServer/0` | UTIL_NAME | UTC territories |

### Gas Utility GIS APIs

| State | API URL | Fields | Notes |
|-------|---------|--------|-------|
| **TX** | Railroad Commission GIS | Various | RRC gas territories |
| **CA** | CPUC GIS | Utility name | Gas service areas |
| **IL** | ICC GIS | Company name | Gas territories |
| **PA** | PUC GIS | Name | Gas service areas |
| **NY** | PSC GIS | Company | Gas territories |
| **OH** | PUCO GIS | Company | Gas service areas |
| **GA** | PSC GIS | Provider | Gas territories |
| **AZ** | ACC GIS | Utility | Gas service areas |
| **CO** | PUC GIS | Company | Gas territories |
| **NJ** | BPU GIS | Name | Gas service areas |
| **MA** | DPU GIS | Company | Gas territories |
| **MI** | MPSC GIS | Name | Gas service areas |
| **FL** | PSC GIS | Utility | Gas territories |

### Federal Data Sources

1. **HIFLD** (Homeland Infrastructure Foundation-Level Data):
   - Electric utility boundaries (national coverage)
   - URL: `services1.arcgis.com/Hp6G80Pky0om7QvQ/arcgis/rest/services/Electric_Retail_Service_Territories_2/FeatureServer/0`
   - Fields: `NAME`, `HOLDING_CO`, `TYPE`, `CUSTOMERS`
   - Confidence: 58 (lower accuracy, but national coverage)

2. **EIA Form 861**:
   - ZIP code to utility mapping
   - File: `eia_zip_utility_lookup.json`
   - ~10MB JSON with ZIP prefix mappings
   - Confidence: 70

3. **EPA SDWIS** (Safe Drinking Water Information System):
   - Water utility data
   - File: `water_utility_lookup.json`
   - National water system boundaries

4. **FCC BDC** (Broadband Data Collection):
   - Internet provider data by census block
   - Local: `bdc_internet_new.db` (55GB SQLite)
   - Railway: PostgreSQL on `gondola.proxy.rlwy.net:21850`
   - ~5.5 million census blocks with Fiber/Cable providers

---

## 3. Lookup Pipeline

### Step-by-Step Flow

```
1. GEOCODING
   └── geocode_address(address, include_geography=True)
       ├── Try Census Geocoder (free, no API key)
       │   └── Uses Census2020_Current vintage for block_geoid
       └── Fallback to Google Maps API (if GOOGLE_MAPS_API_KEY set)
       
2. SPECIAL AREA DETECTION
   └── check_special_areas(lat, lon, state, city)
       ├── Texas MUDs (Municipal Utility Districts)
       ├── Florida CDDs (Community Development Districts)
       └── Other special districts

3. ELECTRIC LOOKUP (if selected)
   └── Priority order:
       1. User corrections (ZIP overrides)
       2. Pipeline (if use_pipeline=True)
          ├── StateGISElectricSource (confidence: 85)
          ├── MunicipalElectricSource (confidence: 88)
          ├── CoopSource (confidence: 68)
          ├── EIASource (confidence: 70)
          ├── HIFLDElectricSource (confidence: 58)
          └── CountyDefaultElectricSource (confidence: 50)
       3. GIS-based lookup (state-specific)
       4. Municipal utility check
       5. HIFLD fallback
       6. State-specific verification

4. GAS LOOKUP (if selected)
   └── Priority order:
       1. User corrections
       2. Pipeline (if use_pipeline=True)
          ├── StateGISGasSource (confidence: 85)
          ├── MunicipalGasSource (confidence: 88)
          ├── ZIPMappingGasSource (confidence: 65)
          ├── HIFLDGasSource (confidence: 58)
          └── CountyDefaultGasSource (confidence: 50)
       3. Municipal gas check
       4. State LDC mapping
       5. HIFLD fallback

5. WATER LOOKUP (if selected)
   └── Priority order:
       1. Supplemental data (curated overrides)
       2. EPA SDWIS lookup
       3. GIS-based lookup
       4. Heuristic matching

6. INTERNET LOOKUP (if selected)
   └── Priority order:
       1. PostgreSQL (if DATABASE_URL set) - fast
       2. Local SQLite BDC data - fast
       3. Playwright FCC scraping - slow fallback (~25-30s)

7. CONFIDENCE SCORING
   └── calculate_confidence(result, utility_type)
       ├── Base score from source
       ├── Precision bonus (point > zip > county > city)
       ├── Cross-validation adjustment
       └── SERP verification bonus

8. RESULT ASSEMBLY
   └── Combine all results with metadata
```

### Source Priority and Confidence Scores

```python
SOURCE_CONFIDENCE = {
    'municipal_utility': 88,    # Most authoritative for cities
    'state_gis': 85,            # Authoritative point-in-polygon
    'state_puc': 82,            # State regulatory data
    'eia_861': 70,              # Good ZIP-level data
    'electric_cooperative': 68, # Reliable for rural areas
    'state_ldc_mapping': 65,    # State gas LDC mappings
    'hifld': 58,                # National but less accurate
    'county_default': 50,       # Last resort fallback
}

PRECISION_BONUS = {
    'point': 15,    # Exact point-in-polygon match
    'zip': 5,       # ZIP code match
    'county': 0,    # County-level match
    'city': 5,      # City-level match
    'state': -10,   # State-level only (penalty)
}
```

---

## 4. OpenAI Integration

### Where It's Used

1. **SERP Verification** (`utility_lookup.py:1556-1610`):
   - Called when sources disagree or confidence is low
   - Analyzes Google search results to verify utility provider

2. **Smart Selector** (in pipeline cross-validation):
   - Breaks ties when multiple sources return different utilities
   - Uses SERP results to validate or override selections

### The Exact Prompt

```python
# From utility_lookup.py:1559-1570
prompt = f"""Analyze these Google search results to identify the {utility_type} utility provider for the address: {address}

Search results:
{search_text}

Our database suggests: {candidate_name or 'Unknown'}

IMPORTANT: Only set matches_database to true if the search results explicitly confirm "{candidate_name}" serves this specific address. If the results mention a DIFFERENT provider (even if our database provider is also mentioned), set matches_database to false and return the provider the search results indicate is correct.

Based on the search results, what is the actual {utility_type} utility provider for this address?
Reply with ONLY a JSON object in this exact format:
{{"provider": "COMPANY NAME", "confidence": "high/medium/low", "matches_database": true/false, "notes": "brief explanation"}}"""
```

### Model Configuration

```python
data = {
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": prompt}],
    "temperature": 0,
    "max_tokens": 200
}
```

### Disagreement Resolution

From `pipeline/pipeline.py:364-419`:

1. If sources agree → Use the agreed result, boost confidence by 20
2. If majority agrees → Use majority result, boost confidence by 10
3. If split/tie → Trigger SERP verification
4. SERP confirms selection → Boost confidence by 15, mark as "verified"
5. SERP disagrees → Switch to SERP-suggested utility if it matches any source
6. SERP finds new utility → Use SERP result with confidence 75

---

## 5. Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | For Railway | PostgreSQL connection string for internet lookups |
| `OPENAI_API_KEY` | Optional | Enables LLM-based SERP analysis |
| `GOOGLE_MAPS_API_KEY` | Optional | Fallback geocoding for hard addresses |
| `SERP_API_KEY` | Optional | Alternative SERP provider |

### How API Keys Are Loaded

```python
# utility_lookup.py:72-90
try:
    from dotenv import load_dotenv
    env_paths = [
        Path(__file__).parent / ".env",
        Path(__file__).parent.parent / "PMD_scrape" / ".env",
        Path(__file__).parent.parent / "BrightData_AppFolio_Scraper" / ".env",
    ]
    for env_path in env_paths:
        if env_path.exists():
            load_dotenv(env_path)
except ImportError:
    pass

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
GOOGLE_MAPS_API_KEY = os.getenv('GOOGLE_MAPS_API_KEY')
```

### Feature Flags

```python
# In LookupPipeline.__init__
self.enable_cross_validation = True
self.enable_serp_verification = True
self.serp_confidence_threshold = 70

# In lookup_utilities_by_address
use_pipeline: bool = True  # Use new pipeline vs legacy code
skip_internet: bool = False  # Skip slow internet lookup
```

---

## 6. Testing

### Golden Test Suite

**File**: `test_addresses.py`
**Test Cases**: 53 addresses across multiple states

### Coverage

- **Texas**: Austin, Houston, Dallas, San Antonio, Kyle (MUD areas)
- **California**: Los Angeles, San Francisco, San Diego
- **New York**: NYC (Con Edison territory)
- **Florida**: Miami, Tampa, Orlando
- **Other states**: SC, NC, GA, VA, PA, OH, IL, WA, OR, etc.

### Test Case Structure

```python
{
    "address": "1725 Toomey Rd, Austin, TX 78704",
    "expected": {
        "electric": "Austin Energy",
        "gas": "Texas Gas Service",
        "water": "Austin Water"
    },
    "notes": "Downtown Austin - municipal utilities"
}
```

### Running Tests

```bash
python test_addresses.py              # Run all tests
python test_addresses.py --verbose    # Show detailed output
python test_addresses.py --streaming  # Test streaming API
python test_addresses.py --api        # Test against live Railway API
python test_addresses.py --limit 10   # Run first 10 tests only
```

### Known Limitations

1. Some expected values are `None` for deregulated markets (Texas ERCOT)
2. Water utility coverage is incomplete in some areas
3. Internet tests not included (too slow with Playwright fallback)

---

## 7. Recent Changes (This Session)

### PostgreSQL Internet Lookup Migration

1. **Exported FCC BDC data to PostgreSQL** (`export_to_postgres.py`)
   - 5.5 million census blocks with Fiber/Cable providers
   - Database size: ~3.6 GB on Railway
   - Uses `DATABASE_URL` environment variable

2. **Fixed Census API vintage** (`utility_lookup.py:159`)
   - Changed from `Current_Current` to `Census2020_Current`
   - Required to get `block_geoid` for PostgreSQL lookup

3. **Added block_geoid extraction** (`utility_lookup.py:214-217`)
   - Extracts Census Block GEOID from geocoding response

### Pipeline Integration Fixes

4. **Fixed gas source imports** (`utility_lookup.py:62-65`)
   - Changed `DirectGasGISSource` → `StateGISGasSource`
   - Removed non-existent `HIFLDNationalGasSource`

5. **Added `_source` to water utility response** (`api.py:259`)
   - Was missing, causing "Confidence details unavailable"

6. **Added pipeline source explanations** (`webflow_embed.html`)
   - Added mappings for `StateGISElectricSource`, `StateGISGasSource`, etc.

### Internet Display Improvements

7. **Map FCC technology codes to names** (`utility_lookup.py:1158-1164`)
   - `50` → "Fiber", `40` → "Cable", `10` → "DSL"

8. **Deduplicate providers** (`utility_lookup.py:1165-1184`)
   - Show only fastest plan per provider

9. **Clarify speed format** (`webflow_embed.html:606`)
   - Changed to `8000 ↓ / 8000 ↑ Mbps`

---

## 8. Known Issues / TODOs

### Incomplete / Hacky

1. **PostgreSQL data has duplicates**
   - The export stored raw FCC data with many duplicate entries
   - Deduplication happens at query time, not in storage
   - Could reduce DB size from 3.6GB to ~220MB by deduping in place

2. **SERP verification is slow**
   - Uses Playwright to scrape Google (~25-30s)
   - Should consider caching or alternative APIs

3. **Pipeline not used for water**
   - Water lookups still use legacy code path
   - No `WaterSource` implementations in pipeline

4. **Some GIS APIs are flaky**
   - State GIS services occasionally timeout or return errors
   - No retry logic implemented

### Edge Cases Not Handled

1. **New construction addresses**
   - Census geocoder fails for addresses < 1 year old
   - Google Maps fallback helps but not always

2. **Multi-utility addresses**
   - Some addresses have multiple valid utilities (e.g., overlapping co-op territories)
   - Currently returns first match, not all options

3. **Deregulated market complexity**
   - Texas ERCOT: Returns transmission company, not retail provider
   - Should clarify this in the UI

4. **Puerto Rico / Virgin Islands**
   - Limited GIS coverage
   - HIFLD data may be outdated

### Technical Debt

1. **`utility_lookup.py` is too large** (~3200 lines)
   - Should be split into modules
   - Pipeline architecture is the start of this refactor

2. **Inconsistent error handling**
   - Some functions return `None`, others raise exceptions
   - Should standardize

3. **No database migrations**
   - PostgreSQL schema changes require manual intervention

4. **Logging is inconsistent**
   - Mix of `print()` statements and no logging
   - Should use proper logging framework

---

## Quick Reference

### Key Functions

| Function | File | Purpose |
|----------|------|---------|
| `lookup_utilities_by_address()` | utility_lookup.py:1854 | Main entry point |
| `lookup_electric_utility_gis()` | gis_utility_lookup.py:948 | State GIS electric lookup |
| `lookup_gas_utility_gis()` | gis_utility_lookup.py:1318 | State GIS gas lookup |
| `lookup_water_utility_gis()` | gis_utility_lookup.py:149 | Water utility lookup |
| `lookup_internet_providers()` | utility_lookup.py:1200 | Internet provider lookup |
| `_lookup_internet_postgres()` | utility_lookup.py:1144 | PostgreSQL internet lookup |
| `LookupPipeline.lookup()` | pipeline/pipeline.py:54 | Pipeline orchestrator |
| `analyze_serp_with_llm()` | utility_lookup.py:1556 | OpenAI SERP analysis |

### Key Classes

| Class | File | Purpose |
|-------|------|---------|
| `LookupPipeline` | pipeline/pipeline.py | Orchestrates multi-source lookups |
| `LookupContext` | pipeline/interfaces.py | Input context for lookups |
| `SourceResult` | pipeline/interfaces.py | Result from a single source |
| `PipelineResult` | pipeline/interfaces.py | Final combined result |
| `DataSource` | pipeline/interfaces.py | Abstract base for data sources |

### API Response Format

```json
{
  "address": "1725 Toomey Rd, Austin, TX 78704",
  "utilities": {
    "electric": {
      "name": "Austin Energy",
      "phone": "512-494-9400",
      "website": "https://austinenergy.com",
      "confidence": "verified",
      "confidence_score": 100,
      "_source": "state_gis"
    },
    "gas": { ... },
    "water": { ... },
    "internet": {
      "provider_count": 4,
      "has_fiber": true,
      "providers": [
        {"name": "Google Fiber", "technology": "Fiber", "max_download_mbps": 8000}
      ]
    }
  }
}
```
