# Water Utility GIS API Inventory

## Overview

This document catalogs state-level water system service territory GIS APIs for integration into the utility lookup system. Data sourced from EPA's "Community Water System Service Area Boundaries State Dataset Summaries" (June 2024) and direct verification.

**Key finding:** Water data is significantly more fragmented than electric. ~50,000 community water systems vs ~3,000 electric utilities. State coverage varies from 13% to 99%.

---

## Windsurf Integration Guide

### Priority Order for Water Lookups
1. **State GIS API** (this document) - Authoritative, use when available
2. **EPA SDWIS** - Points only, for name verification
3. **HIFLD Water** - National fallback, known accuracy issues

### Standard Query Pattern
All endpoints are ArcGIS FeatureServer REST APIs. Use this spatial query:
```
{endpoint}/query?geometry={lon},{lat}&geometryType=esriGeometryPoint&inSR=4326&spatialRel=esriSpatialRelIntersects&outFields=*&returnGeometry=false&f=json
```

**Note:** Some endpoints use non-WGS84 coordinate systems (e.g., Arkansas uses UTM 15N). Either:
- Transform input coordinates before query, OR
- Let ArcGIS handle it via `inSR=4326` parameter (usually works)

### "No Water Service" Response
Unlike electric (everyone has service), many areas have no public water:
```json
{
  "water_utility": null,
  "water_available": false,
  "confidence": 0.85,
  "reason": "No public water system found - likely private well"
}
```

---

## Tier 1: High Coverage State APIs (>90%)

### Texas ✅ VERIFIED
- **Endpoint:** `https://services.twdb.texas.gov/arcgis/rest/services/PWS/Public_Water_Service_Areas/FeatureServer/0`
- **Source Agency:** Texas Water Development Board (TWDB)
- **Coverage:** Statewide, all community Public Water Systems
- **Fields:** PWS_ID, PWS_NAME, service area polygon
- **Coordinate System:** Verify at runtime
- **Data Quality:** 
  - Self-reported by utilities via annual Water User Survey
  - Authoritative state source
  - Links to TCEQ Drinking Water Watch
- **Alternative Layers:**
  - CCN Boundaries (legal territories): `.../PWS/Public_Utility_Commission_CCN_Water/MapServer`
  - Use actual service areas, NOT CCN, for utility lookup
- **Notes:** This replaces HIFLD for Texas. HIFLD returned "Mustang SUD" for a Little Elm address that should be "Town of Little Elm"

### Arkansas ✅ VERIFIED
- **Endpoint:** `https://gis.arkansas.gov/arcgis/rest/services/FEATURESERVICES/Utilities/FeatureServer/15`
- **Layer:** PUBLIC_WATER_SYSTEMS
- **Source Agency:** Arkansas Department of Health (ADH), Engineering Division
- **Coverage:** 98% (657 of 672 active CWS), 796 total polygons
- **Fields:** PWSID (numeric only - prepend "AR" for SDWIS lookup), system name
- **Coordinate System:** 26915 (UTM Zone 15N) - transformation needed
- **MaxRecordCount:** 500
- **Data Quality (EPA assessment):**
  - Some shapes follow roads/pipes rather than true service boundaries
  - Some overlapping shapes
  - No active/inactive field
- **Bonus:** Same FeatureServer has Layer 12: ELECTRIC_UTILITY_TERRITORY

### New Jersey
- **Hub:** `https://njogis-newjersey.opendata.arcgis.com/datasets/00e7ff046ddb4302abe7b49b2ddee07e_13`
- **Coverage:** 99% (564 of 566 active CWS)
- **Fields:** PWID (SDWIS format), Purveyor_Name, Service_Area_Type
- **Notes:** Excellent data quality, quarterly updates, boundaries are actual served areas (not jurisdictional)

### California
- **DWR Water Districts:** `https://gis.water.ca.gov/arcgis/rest/services/Boundaries/i03_WaterDistricts/FeatureServer/0`
- **Drinking Water Boundaries:** `https://gis.data.ca.gov/datasets/fbba842bf134497c9d611ad506ec48cc`
- **Coverage:** 98% (2,788 of 2,842 active CWS)
- **Fields:** SABL_PWSID, WATER_SYSTEM_NAME, VERIFIED_STATUS, BOUNDARY_TYPE
- **Notes:** Includes verification status per boundary, active verification program

### Arizona
- **Hub:** `https://gisdata2016-11-18t150447874z-azwater.opendata.arcgis.com/datasets/cws-service-area-1`
- **Coverage:** 96% (717 of 746 active CWS)
- **Fields:** ADEQ_ID (PWSID), CWS_NAME, STATUS, POPULATION
- **Notes:** Updated every 5 years, includes active/inactive flag

### Connecticut
- **Portal:** `https://maps.ct.gov/portal/home/item.html?id=684908bf05a2430f8a60d58a96d640d6`
- **Coverage:** 94% (448 of 477 active CWS)
- **Fields:** PWS_Name, PWSID
- **Notes:** Buffered approximation based on service lines

### Pennsylvania
- **PASDA:** `https://www.pasda.psu.edu/uci/DataSummary.aspx?dataset=1090`
- **Open Data:** `https://newdata-padep-1.opendata.arcgis.com`
- **Coverage:** 93% (1,767 of 1,887 active CWS)
- **Fields:** PWS_ID, NAME, OWNERSHIP, GW_SOURCE, SW_SOURCE, LAST_DATE
- **Notes:** Half updated since 2015, includes source type indicators

### New Mexico
- **OSE Portal:** `https://geospatialdata-ose.opendata.arcgis.com/datasets/OSE::new-mexico-public-water-system-boundaries`
- **Coverage:** 93% (526 of 564 active CWS)
- **Fields:** Water_System_ID (NM format), System_Name, System_Type, Boundary_Source
- **Last Updated:** January 2024
- **Notes:** Includes boundary quality field, actively maintained

### Kansas
- **Hub:** `https://hub.kansasgis.org/maps/KSDOT::rural-water-districts`
- **Coverage:** 90% (779 of 864 active CWS)
- **Fields:** FED_ID (SDWIS PWSID), KDHE_ID, NAME
- **Notes:** Rural water districts + municipalities

---

## Tier 2: Medium Coverage State APIs (50-90%)

### Oklahoma
- **OWRB:** `https://oklahoma.gov/owrb/data-and-maps/gis-data.html`
- **Coverage:** 80% (707 of 880 active CWS)
- **Fields:** PWSID, NAME, SOURCE (boundary origin)
- **Notes:** Based on 1995 rural water survey with updates, approximate boundaries

### New Hampshire
- **Source:** NHDES (not publicly available, requires request)
- **Coverage:** 58% (414 of 710 active CWS)
- **Notes:** EPIC/SimpleLab has processed version at github.com/ewiggansLI/NH_DES_PWS

---

## Tier 3: Low Coverage State APIs (<50%)

### Florida (Partial - 3 Water Management Districts)
- **St. Johns River WMD:** `https://services.arcgis.com/s8wtJX9suxFen6TA/ArcGIS/rest/services/Public_Water_Supply_Area_SJRWMD/FeatureServer`
  - Coverage: 21% of state (344 of 1,605 active CWS)
  - Fields: UTILITY, CUP_NUMBER, PWS_ID, UTIL_CAT
- **South Florida WMD:** `https://geo-sfwmd.hub.arcgis.com`
  - 161 PWSs, no PWSID field
- **Southwest Florida WMD:** `https://data-swfwmd.opendata.arcgis.com`
  - 350 PWSs, detailed source attribution

### North Carolina
- **NC OneMap:** `https://www.nconemap.gov/datasets/58548b90bdfd4148829103ac7f4db9ce_4`
- **Coverage:** 23% (475 of 1,989 active CWS)
- **Notes:** OLD DATA (2004), Type A systems only

### New York
- **DEC MapServer:** `https://gisservices.dec.ny.gov/arcgis/rest/services/der/der_viewer/MapServer/4`
- **Coverage:** 13% (302 of 2,267 active CWS)
- **Notes:** Only systems serving >3,300 people

### Missouri
- **MSDIS:** `https://data-msdis.opendata.arcgis.com/datasets/c00f4e1d0fac49c5ad8cb32a163ab2b5_0`
- **Coverage:** 17% (247 of 1,434 active CWS)
- **Fields:** IPWS (SDWIS PWSID), PWSSNAME, STATUS
- **Notes:** Old data, mostly not updated since 2012

### Mississippi
- **PSC Open Data:** `https://mpscmississippi.opendata.arcgis.com`
- **Coverage:** Unknown (no PWSID to link)
- **Fields:** UTILITY_NA, CREDITUTIL (state ID)
- **Notes:** Minimal metadata, no SDWIS linkage

### Colorado
- **State Data:** `https://data.colorado.gov/Local-Aggregation/Water-and-Sanitation-Districts-in-Colorado/d6bs-3kgu`
- **Coverage:** 25-50% (254-531 of 949 active CWS)
- **Notes:** Requires linking multiple sources, includes sanitation districts

---

## States in EPA Document (Need Endpoint Extraction)

These states are documented by EPA but need FeatureServer endpoint verification:

| State | EPA Coverage | Notes |
|-------|-------------|-------|
| Tennessee | Unknown | Vanderbilt DWJL project |
| Utah | Unknown | In EPA document |
| Washington | Unknown | In EPA document |
| West Virginia | Unknown | In EPA document |

---

## National Fallback: EPA CWS Data

**SDWIS Database:** Primary source for system identification
- Contains all ~50,000 community water systems
- No service area boundaries, only point locations
- Use for verification and name matching

**HIFLD:** Does NOT have a national water system boundary layer equivalent to electric utilities

---

## Comparison: Water vs Electric Data Availability

| Metric | Electric | Water |
|--------|----------|-------|
| National systems | ~3,000 | ~50,000 |
| National boundary layer | Yes (HIFLD) | No |
| States with >90% GIS | ~35 | ~8 |
| Dominant providers | Yes (Duke, Xcel, etc.) | No |
| Well/self-supply | Rare | Common (rural) |

---

## Implementation Recommendations

### Priority States for Water API Integration

**Phase 1 (Immediate - VERIFIED):**
1. ✅ Texas - TWDB endpoint verified, authoritative
2. ✅ Arkansas - 98%, direct FeatureServer verified
3. New Jersey - 99%, excellent quality (needs endpoint extraction)
4. California - 98%, multiple sources (needs endpoint extraction)
5. Pennsylvania - 93%, good coverage (needs endpoint extraction)

**Phase 2:**
6. Arizona - 96%
7. Kansas - 90%
8. New Mexico - 93%
9. Connecticut - 94%

**Phase 3:**
10. Oklahoma - 80%
11. Florida WMDs - partial coverage
12. New Hampshire - request data

### Data Quality Considerations

1. **PWSID Matching:** Critical for cross-validation
   - Some states use state-specific IDs
   - Need mapping table for non-standard formats

2. **Boundary Types:**
   - Service areas (actual delivery) - preferred
   - Jurisdictional/franchise areas - may overstate coverage
   - Buffered pipe networks - approximate

3. **Update Frequency:**
   - CA, NJ, NM: Active maintenance
   - NC, MO: Stale data (2004-2012)
   - Most others: Periodic updates (1-5 years)

### SERP Verification for Water

Less effective than electric because:
- Many small systems have no web presence
- People often don't know their water provider name
- Searches return unhelpful results for rural areas

Better alternatives:
- State drinking water program contacts
- County government websites
- City utility department pages

### "No Utility Found" as Valid Answer

Unlike electric, many areas genuinely have no water utility:
- Well water (common in rural areas)
- Unincorporated areas
- Very small communities

System should return:
```json
{
  "water_utility": null,
  "water_source": "likely_private_well",
  "confidence": 0.75,
  "note": "No public water system found in service area databases"
}
```

---

## Verification Status

| State | Endpoint Verified | Query Tested | Added to System |
|-------|------------------|--------------|-----------------|
| **Texas** | ✅ Jan 2025 | Pending | Pending |
| **Arkansas** | ✅ Jan 2025 | Pending | Pending |
| New Jersey | ✓ (Hub) | Pending | Pending |
| California | ✓ | Pending | Pending |
| Arizona | ✓ (Hub) | Pending | Pending |
| Pennsylvania | ✓ | Pending | Pending |
| Kansas | ✓ (Hub) | Pending | Pending |
| New Mexico | ✓ | Pending | Pending |
| Connecticut | ✓ | Pending | Pending |
| Oklahoma | ✓ | Pending | Pending |
| FL - SJRWMD | ✓ | Pending | Pending |

---

## Source

EPA Office of Water, "Community Water System Service Area Boundaries State Dataset Summaries," June 2024
https://www.epa.gov/system/files/documents/2024-04/cws-service-area-boundaries-state-dataset-summaries.pdf
