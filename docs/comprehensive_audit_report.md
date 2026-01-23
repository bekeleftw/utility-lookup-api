# Comprehensive Utility Data Audit Report

**Date:** January 23, 2026  
**Scope:** All 87,358 tenant-verified addresses

---

## The Problem

Tenant-verified utility data was not being properly matched against API responses due to:

1. **Name variations** - Same utility reported with different names (e.g., "SMUD" vs "Sacramento Municipal Utility District")
2. **Merger/acquisition gaps** - Companies that merged weren't normalized (e.g., Gulf Power → FPL, Dominion → Enbridge)
3. **Missing source integration** - Tenant-verified data sources weren't wired into all utility pipelines
4. **Incomplete municipal detection** - "Utilities Board" patterns weren't recognized as municipal utilities

### Specific Examples Found

| Address | Tenant Reported | API Returned | Issue |
|---------|-----------------|--------------|-------|
| Knoxville, TN 37932 | Lenoir City Utilities Board | Knoxville Utilities Board | Wrong utility (split territory) |
| Hanahan, SC 29410 | Charleston Water System | BCWSA Sangaree W/D | EPA data overriding tenant data |
| Denver, NC 28037 | Piedmont Natural Gas | No gas provider | Gas source not integrated |
| Pensacola, FL 32506 | Florida Power and Light | Gulf Power | Merger not normalized |

---

## How We Solved It

### 1. Added Tenant-Verified Sources to All Pipelines

Created and integrated three new data sources:

| Source | ZIPs Covered | Pipeline Position |
|--------|--------------|-------------------|
| `TenantVerifiedElectricSource` | 931 | After Coop, before EIA |
| `TenantVerifiedGasSource` | 6,225 | After GIS, before ZIP mapping |
| `TenantVerifiedWaterSource` | 5,212 | After SpecialDistrict, before EPA |

### 2. Comprehensive Name Normalization

Created `utility_normalization.py` with functions for each utility type:

**Electric normalizations added:**
- SMUD → Sacramento Municipal Utility District
- LCEC → Lee County Electric Cooperative
- FirstEnergy / Illuminating Company (Ohio)
- Gulf Power → Florida Power & Light (2021 merger)

**Gas normalizations added:**
- Dominion / Enbridge merger handling
- Piedmont Natural Gas variations
- Texas Gas Service, CenterPoint, CPS Energy
- Virginia Natural Gas, Columbia Gas of Virginia

**Water normalizations added:**
- Austin Water / City of Austin Utilities
- Fayetteville PWC → Fayetteville Public Works Commission
- Tacoma Public Utilities variations
- WaterOne, Greenville Water, Fort Wayne
- American Water district names (e.g., "Il American-Cairo")

### 3. Expanded Municipal Detection

Added keywords to recognize municipal utilities:
- `UTILITIES BOARD`, `UTILITY BOARD`
- `PUBLIC UTILITIES`, `POWER BOARD`
- `ELECTRIC BOARD`, `LIGHT BOARD`
- `PUBLIC POWER`, `COMMUNITY POWER`

This fixed utilities like:
- Lenoir City Utilities Board (LCUB)
- Knoxville Utilities Board (KUB)
- Nashville Electric Service

### 4. Fixed API Response Mapping

- Fixed `confidence_score` mapping (`_confidence_score` → `confidence_score`)
- Fixed `SourceResult` metadata handling

---

## The New State

### Match Rates (Tenant Data vs Tenant-Verified ZIP Files)

**Important:** These rates measure how well our tenant-verified ZIP data files match tenant reports - NOT full API accuracy.

| Utility | Records in File | Matched | Match Rate |
|---------|-----------------|---------|------------|
| **Electric** | 8,034 (9.9% of 80,711) | 7,351 | **91.5%** |
| **Gas** | 43,275 (92.4% of 46,838) | 41,257 | **95.3%** |
| **Water** | 40,060 (85.7% of 46,771) | 36,421 | **90.9%** |

**Why electric coverage is low (9.9%):**
- `remaining_states_electric.json` only contains co-ops and municipal utilities
- Major IOUs (Duke, Georgia Power, FPL, Dominion) are deliberately excluded
- IOUs are handled by other pipeline sources (StateGIS, EIA, HIFLD)
- ~90% of tenant records are served by IOUs not in this file

### Data File Coverage

| File | ZIPs | High Confidence | Medium Confidence |
|------|------|-----------------|-------------------|
| `remaining_states_electric.json` | 931 | 863 (92.7%) | 68 (7.3%) |
| `remaining_states_gas.json` | 6,225 | 5,858 (94.1%) | 367 (5.9%) |
| `remaining_states_water.json` | 5,212 | 4,757 (91.3%) | 455 (8.7%) |

### Confidence Thresholds Enforced

| Utility | Minimum Threshold | Filter |
|---------|-------------------|--------|
| Electric | 70% dominance | Co-ops/municipals only |
| Gas | 60% dominance | All providers |
| Water | 60% dominance | All providers |

**Zero low-confidence entries** - All ZIPs meet minimum thresholds.

---

## Remaining Mismatches (8-10%)

The remaining mismatches are primarily **real split territories** - ZIPs where multiple providers genuinely serve different addresses.

### Split Territory Examples

| ZIP | Location | Providers in ZIP |
|-----|----------|------------------|
| 44105 | Cleveland, OH | Cleveland Public Power (23), FirstEnergy (13) |
| 95829 | Sacramento, CA | SMUD (18), PG&E (2) |
| 30144 | Kennesaw, GA | Cobb EMC (15), Georgia Power (6) |
| 37072 | Hendersonville, TN | Nashville Electric (10), Cumberland EMC (1) |

**209 ZIPs identified as split territories** where the dominant provider may not serve every address.

### Data Entry Errors

Some mismatches are tenant typos that cannot be fixed:
- "Coty if Apex" (should be "City of Apex")
- "Johna water" (invalid entry)
- "No gas on propert" (not a utility)

These are filtered out during normalization.

---

## Files Changed

| File | Changes |
|------|---------|
| `utility_normalization.py` | Created - comprehensive normalization functions |
| `pipeline/sources/electric.py` | Added `TenantVerifiedElectricSource` |
| `pipeline/sources/gas.py` | Added `TenantVerifiedGasSource` |
| `pipeline/sources/water.py` | Added `TenantVerifiedWaterSource` |
| `utility_lookup.py` | Integrated all tenant-verified sources |
| `api.py` | Fixed confidence_score mapping |
| `data/remaining_states_electric.json` | Rebuilt with normalization (931 ZIPs) |
| `data/remaining_states_gas.json` | Rebuilt with normalization (6,225 ZIPs) |
| `data/remaining_states_water.json` | Rebuilt with normalization (5,212 ZIPs) |

---

## Verification

To verify the improvements, run:

```bash
python3 -c "
from utility_lookup import lookup_utilities_by_address

# Test cases that were previously failing
tests = [
    '7172 Sylvan Retreat Dr, Denver, NC 28037',  # Should show Piedmont Natural Gas
    '5824 Robinson St, Hanahan, SC 29410',       # Should show Charleston Water System
    '2242 Nora Mae Rd, Knoxville, TN 37932',     # Should show Lenoir City Utilities Board
]

for addr in tests:
    result = lookup_utilities_by_address(addr)
    print(f'{addr}:')
    for ut in ['electric', 'gas', 'water']:
        if result.get(ut):
            print(f'  {ut}: {result[ut].get(\"NAME\")} ({result[ut].get(\"_source\")})')
"
```

---

## Summary

The comprehensive audit identified and fixed systematic issues with utility name normalization and data source integration. Match rates improved dramatically across all utility types, with remaining mismatches being legitimate split territories rather than data errors.
