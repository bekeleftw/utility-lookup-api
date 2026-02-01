# Comparison Analysis - API vs Internal Mapping

**Date:** February 1, 2026

## Summary

| Category | Count | Status |
|----------|-------|--------|
| ID Mismatches (same provider, different ID) | ~50 | ✅ Fixed |
| Name Variations (same provider, different spelling) | ~40 | ✅ Fixed |
| Wrong Provider (API returned different provider) | 14 | ⚠️ Needs investigation |

## What Was Fixed

Created `data/canonical_provider_ids.json` with 72+ mappings to resolve duplicate IDs and name variations.

## Truly Wrong Lookups (14 cases)

### WATER
1. **202 Hanover Pl, Cibolo, TX** - Expected: Green Valley SUD, Got: City of Cibolo
2. **27 S Main St, Dry Ridge, KY** - Expected: City of Dry Ridge Water, Got: Williamstown Municipal
3. **282 E 12200 S, Draper, UT** - Expected: Water Pro Inc, Got: Draper City
4. **34 Lafayette St, Rochester, NH** - Expected: City of Rochester NH, Got: Chester Brook
5. **401 N Wheeling Ave, Muncie, IN** - Expected: Indiana American Water, Got: Delaware Acres Mhc
6. **4910 Stapper Rd, Saint Hedwig, TX** - Expected: Green Valley SUD, Got: East Central SUD
7. **6076 Regent Mnr, Lithonia, GA** - Expected: Dekalb County Watershed, Got: Atlanta
8. **8883 Curie St, Manassas, VA** - Expected: Prince William Water, Got: Manassas Virginia

### ELECTRIC
9. **3171 Fairmount St, Los Angeles, CA** - Expected: LADWP, Got: SCE
10. **515 Ambassador Way, Mountain Home, AR** - Expected: Entergy Arkansas, Got: Springfield
11. **522 S Oak St, Little Rock, AR** - Expected: North Little Rock Electric, Got: Little Rock Pine Bluff
12. **7440 S Blackhawk St, Englewood, CO** - Expected: Xcel Energy, Got: Intermountain Rural

### GAS
13. **4910 Stapper Rd, Saint Hedwig, TX** - Expected: Grey Forest Utilities, Got: CPS Energy

## Root Causes

1. **GIS boundary inaccuracies** - Service territory boundaries in GIS data don't match actual service
2. **Geocoding precision** - Address geocodes to wrong side of boundary line
3. **Overlapping service areas** - Multiple providers serve same area

## Recommendations

1. Add address-level overrides for known problem addresses
2. Verify GIS data sources for AR, TX, CO, VA
3. Consider using utility website verification for edge cases
