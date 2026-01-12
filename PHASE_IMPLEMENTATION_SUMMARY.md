# Utility Lookup - Phase Implementation Summary

**Date:** January 11, 2026  
**Purpose:** Summary of all phases implemented for updating data source documentation

---

## Overview

We implemented Phases 12, 13, and 14 from the `nationwide_reliability_improvements.md` plan, plus updated confidence scoring to reflect the new data sources.

---

## New Modules Created

### Phase 12: Additional Data Sources

| Module | File | Description |
|--------|------|-------------|
| **Propane Service** | `propane_service.py` | Detects areas without natural gas that use propane. Includes major providers (AmeriGas, Suburban, Ferrellgas) and high-propane states (ME, VT, NH, MT, WY, SD, ND, AK). |
| **Well/Septic Detection** | `well_septic.py` | Estimates likelihood of private well/septic based on location, incorporated status, and rural indicators. Includes county health department contacts. |
| **Franchise Agreements** | `data/franchise_agreements/index.json` | City franchise agreement data for major cities (Austin, Dallas, Houston, San Antonio, LA, Phoenix, Denver, Seattle). Maps utilities to exclusive service territories. |

### Phase 13: Edge Cases & Special Handling

| Module | File | Description |
|--------|------|-------------|
| **Deregulated Markets** | `deregulated_markets.py` | Handles 14 deregulated electricity states (TX, PA, OH, IL, NY, NJ, MD, CT, MA, ME, NH, RI, DE, DC). Distinguishes TDU (infrastructure) from REP (retail provider). Includes Texas TDU lookup by ZIP prefix. |
| **Special Areas** | `special_areas.py` | Detects tribal lands (via Census TIGER API), military installations (10 major bases with utility info), and unincorporated areas. Adjusts confidence for special handling. |
| **Building Types** | `building_types.py` | Detects building type from address (single-family, apartment, condo, townhome, mobile home, commercial). Returns metering arrangement info (direct, master-metered, submetered). |

### Phase 14: ML Enhancements

| Module | File | Description |
|--------|------|-------------|
| **Address Inference** | `address_inference.py` | Infers utilities from nearby verified addresses on same street. Uses 80% agreement threshold. Caches verified address-utility mappings. |
| **ML Enhancements** | `ml_enhancements.py` | Ensemble prediction (combines sources with learned weights), active learning (prioritizes low-confidence for verification), anomaly detection (flags results differing from ZIP patterns). |

---

## Updated Confidence Scoring

### New Source Tiers (`confidence_scoring.py`)

```
TIER 1 (90+) - Skip SERP verification:
  user_confirmed: 95      # Multiple users confirmed
  utility_direct_api: 92  # Direct GIS API (Austin Energy, CA CEC)
  franchise_agreement: 92 # City franchise data
  parcel_data: 90         # County assessor data

TIER 2 (80-89) - Spot-check SERP:
  user_feedback: 88       # Single user feedback
  municipal_utility: 88   # Municipal utility database
  special_district: 85    # MUD/CDD/PUD boundaries
  verified: 85            # State-specific verification
  state_puc_map: 82       # State PUC territory maps
  zip_override: 80        # Manual corrections
  railroad_commission: 80 # Texas RRC

TIER 3 (65-79) - SERP recommended:
  state_puc: 75           # State PUC data
  address_inference: 72   # Inferred from nearby addresses
  eia_861: 70             # EIA federal data
  supplemental: 70        # Curated supplemental files
  electric_cooperative: 68 # NRECA data
  state_ldc_mapping: 65   # State gas LDC mappings

TIER 4-5 (<65) - Always SERP:
  google_serp: 60         # Google search primary
  hifld_polygon: 58       # HIFLD territory polygons
  epa_sdwis: 55           # EPA water systems
  serp_only: 50           # Search only
  county_match: 45        # County-level match
  heuristic: 30           # Name matching fallback
  unknown: 15
```

### New Precision Scores

```
parcel: 15      # Parcel-level match (assessor data)
address: 12     # Exact address match
gis_point: 10   # GIS point-in-polygon query
subdivision: 8  # Subdivision match
special_district: 8
zip5: 5
zip3: 3
county: 1
state: 0
```

---

## Verified Real Data Sources

### Working ArcGIS Endpoints (`utility_direct_lookup.py`)

| Utility | Type | State | URL |
|---------|------|-------|-----|
| **Austin Energy** | Electric | TX | `maps.austintexas.gov/arcgis/rest/services/Shared/BoundariesGrids_2/MapServer/1` |
| **CA Gas Service (CEC)** | Gas | CA | `services3.arcgis.com/bWPjFyq029ChCGur/arcgis/rest/services/Natural_Gas_Service_Area/FeatureServer/0` |

The CA Gas endpoint covers: PG&E, SoCalGas, SDG&E, Southwest Gas in California.

---

## Integration into Main Lookup (`utility_lookup.py`)

The main `lookup_utilities_by_address()` function now includes:

1. **Special area detection** - Checks for tribal lands, military bases, unincorporated areas
2. **Building type detection** - Identifies apartments, condos, etc. with metering notes
3. **Deregulated market handling** - Adds TDU/REP info for deregulated states
4. **Propane detection** - When no gas service found, checks if propane area
5. **Anomaly detection** - Flags results that differ from ZIP patterns

### New Result Metadata

```python
result = {
    "electric": {...},
    "gas": {...},
    "water": {...},
    "internet": {...},
    "location": {
        "city": "...",
        "county": "...",
        "state": "...",
        "zip_code": "..."
    },
    "_metadata": {
        "building_type": "apartment_garden",
        "deregulated_market": True,
        "deregulated_info": {...},
        "special_areas": ["tribal_land", "military"],
        "requires_special_handling": True
    },
    "_special_area_notes": [...],
    "_tribal_info": {...},
    "_military_info": {...},
    "_anomalies": [...]
}
```

---

## Complete Data Source Inventory

### Government Sources (Free)
- US Census Geocoder
- US Census TIGER (tribal boundaries, incorporated places)
- EPA SDWIS (water systems)
- EIA Form 861 (electric utilities)
- HIFLD (utility boundaries)
- FCC Broadband Map
- State PUC territory maps
- TCEQ (Texas special districts)
- FL DEO (Florida CDDs)
- DOLA (Colorado metro districts)
- California Energy Commission (gas service areas)
- City of Austin GIS (Austin Energy)

### Curated Data Files
- `data/municipal_utilities.json` - Municipal electric/gas/water
- `data/gas_mappings/*.json` - State gas LDC mappings
- `data/electric_cooperatives_supplemental.json` - Electric co-ops
- `data/water_utilities_supplemental.json` - Water utilities
- `data/special_districts/` - TX MUDs, FL CDDs, CO districts, CA districts, AZ districts, WA PUDs
- `data/franchise_agreements/index.json` - City franchise agreements
- `data/utility_directory/master.json` - Master utility list with aliases
- `data/problem_areas.json` - Known problematic areas

### User/Crowdsourced
- User feedback system
- Verified address cache (`data/verified_addresses.json`)
- Lookup history for ML learning (`data/lookup_history.json`)

### Direct API Sources
- Austin Energy GIS (verified, working)
- California Energy Commission Gas Service Areas (verified, working)
- Other utility GIS endpoints (placeholders, need verification)

---

## Files Changed/Created

### New Files
- `deregulated_markets.py`
- `special_areas.py`
- `building_types.py`
- `address_inference.py`
- `ml_enhancements.py`
- `propane_service.py`
- `well_septic.py`
- `data/franchise_agreements/index.json`
- `data/verified_addresses.json`

### Modified Files
- `utility_lookup.py` - Added imports and integration
- `utility_direct_lookup.py` - Updated with verified real endpoints
- `confidence_scoring.py` - Updated tiers and source mappings

---

## Target Accuracy After All Phases

| Utility | Before | After Phase 11 | After Phase 12-14 |
|---------|--------|----------------|-------------------|
| Electric | 90% | 98% | 99% |
| Gas | 85% | 95% | 97% |
| Water | 75% | 92% | 95% |

---

## Cost Optimization

With more Tier 1 & 2 authoritative sources, SERP verification is skipped more often:
- **Tier 1 sources** (utility_direct_api, franchise_agreement, parcel_data): Always skip SERP
- **Tier 2 sources** (municipal_utility, special_district, verified): Skip SERP
- **Savings**: ~$0.01 per lookup when using authoritative sources
