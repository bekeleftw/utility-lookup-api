# Sewer Utility Lookup API - Implementation Status

**Last Updated:** February 1, 2026

---

## Overview

The sewer utility lookup has been enhanced with state-specific GIS APIs that provide authoritative service area data. The system uses a hierarchical approach: state APIs first, then CSV database, then HIFLD fallback, then municipal inference.

---

## Implemented State APIs

| State | API Source | Coverage | Confidence | Status |
|-------|-----------|----------|------------|--------|
| **Texas** | PUC Sewer CCN | Statewide | High | ✅ Production |
| **Connecticut** | DEEP Connected Sewer | Statewide | High | ✅ Production |
| **California** | Water Districts (proxy) | Statewide | Medium | ✅ Production |
| **Florida** | DOH FLWMI | Parcel-level | Medium | ✅ Production |
| **Washington** | WASWD Districts | ~21% | Medium | ✅ Production |
| **New Jersey** | DEP SSA | Statewide | High | ⚠️ Endpoint not accessible |
| **Massachusetts** | MassDEP WURP | Statewide | High | ⚠️ Endpoint not accessible |

---

## API Endpoints Used

### Texas PUC Sewer CCN
```
https://services6.arcgis.com/N6Lzvtb46cpxThhu/ArcGIS/rest/services/Sewer_CCN_Service_Areas/FeatureServer/230
```
- **Authority:** Texas Public Utility Commission
- **Key Fields:** CCN_HOLDER, CCN_NUMBER, UTILITY, DBA_NAME
- **Returns:** CCN number included in response

### Connecticut DEEP
```
https://services1.arcgis.com/FjPcSmEFuDYlIdKC/arcgis/rest/services/Connected_Sewer_Service_Areas/FeatureServer/0
```
- **Authority:** CT Department of Energy and Environmental Protection
- **Key Fields:** TOWN, Sewers, SewerStatus, TreatmentFacility

### California Water Districts
```
https://gis.water.ca.gov/arcgis/rest/services/Boundaries/i03_WaterDistricts/FeatureServer/0
```
- **Authority:** State Water Resources Control Board
- **Note:** Water districts used as proxy (many provide sewer service)

### Florida DOH FLWMI
```
https://gis.floridahealth.gov/server/rest/services/FLWMI/FLWMI_Wastewater/MapServer/0
```
- **Authority:** Florida Department of Health
- **Key Fields:** WW (status), WW_SRC_NAME (provider)
- **Note:** Parcel-level precision required

### Washington WASWD
```
https://services8.arcgis.com/J7RBtn4Gc9TK4jT1/arcgis/rest/services/WASWDMap_WFL1/FeatureServer/0
```
- **Coverage:** 182 special purpose districts (~21% of state)

### New Jersey DEP SSA (Pending)
```
https://services2.arcgis.com/XVOqAjTOJ5P6ngMu/arcgis/rest/services/Util_wastewater_servicearea/FeatureServer/0
```
- **Authority:** NJ Department of Environmental Protection
- **Key Fields:** TRT_PLANT, NJPDES, SSA_TYPE
- **Status:** ⚠️ Endpoint returns "Invalid URL" - may require authentication

### Massachusetts MassDEP WURP (Pending)
```
https://services.arcgis.com/hGdibHYSPO59RG1h/arcgis/rest/services/Sewer_Service_Area_POTW/FeatureServer/0
```
- **Authority:** MA Department of Environmental Protection
- **Key Fields:** FACILITY_NAME, NPDES_PERMIT, VERIFICATION_STATUS
- **Status:** ⚠️ Endpoint returns "Invalid URL" - may require authentication

---

## Fallback Chain

For states without dedicated APIs, the system uses:

1. **CSV Providers Database** - 1,706 sewer utility entries
2. **HIFLD Wastewater Treatment Plants** - Nearest facility lookup
3. **Municipal Water Inference** - Assumes sewer from same entity as water

---

## States #12-20 Research Summary

| Rank | State | Pop | Status | Notes |
|------|-------|-----|--------|-------|
| 12 | Virginia | 8.6M | NONE | HRSD regional, county-by-county |
| 13 | Washington | 7.7M | PARTIAL | WASWD ~21% ✅ implemented |
| 14 | Arizona | 7.4M | PROXY | Water only (ADWR CWS) |
| 15 | Tennessee | 7.1M | PROXY | Water only (TDEC) |
| 16 | Maryland | 6.2M | COUNTY | Montgomery, Frederick have data |
| 17 | Colorado | 5.8M | NONE | District boundaries only |
| 18 | Minnesota | 5.7M | REGIONAL | Twin Cities metro only |
| 19 | Indiana | 6.8M | COUNTY | Regional districts |
| 20 | Missouri | 6.2M | CSO ONLY | 5 CSO areas mapped |

**Bottom line:** No new Tier 1 production-ready statewide APIs found in states #12-20.

---

## Test Results

| Address | Sewer Provider | Source |
|---------|---------------|--------|
| Round Rock, TX | City of Round Rock (CCN: 20421) | `texas_puc_sewer_ccn` |
| Hartford, CT | MDC-Hartford | `connecticut_deep` |
| San Francisco, CA | SF Public Utilities Commission | `ca_water_districts` |
| Seattle, WA | King County | `washington_waswd` |

---

## Files Modified

- `sewer_lookup.py` - Main sewer lookup module with all state APIs
- `utility_lookup_v1.py` - Integrated sewer lookup into main utility function
- `api.py` - Added sewer/trash formatting with CCN support
- `municipal_utilities.py` - Added `lookup_municipal_sewer()` function

---

## API Response Example

```json
{
  "utilities": {
    "sewer": [{
      "name": "City of Round Rock",
      "ccn_number": "20421",
      "_source": "texas_puc_sewer_ccn",
      "confidence": "high",
      "_note": "Texas PUC CCN #20421 - Bounded Service Area"
    }]
  }
}
```

---

## Next Steps (Optional Enhancements)

1. **Contact California CIWQS** (SanitarySewer@waterboards.ca.gov) for direct sewer API access
2. **Add county-level data** for MD (Montgomery, Frederick), IN (Indianapolis)
3. **Improve FL FLWMI** with address-to-parcel geocoding for better hit rate
4. **Add NJ DEP SSA** if public endpoint becomes available

---

## Deployment

All changes auto-deploy to Railway on push to `main` branch.

**Production URL:** `https://web-production-9acc6.up.railway.app`
