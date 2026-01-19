# GIS Utility API Status Summary

**Last Updated:** January 18, 2026

This document summarizes the current state of GIS-based utility lookup APIs integrated into the system.

---

## Electric Utility APIs (33 States + DC)

### Working State APIs

| State | API Source | Endpoint | Key Fields | Status |
|-------|------------|----------|------------|--------|
| **AK** | Alaska RCA (DCCED) | `maps.commerce.alaska.gov/.../MapServer/90` | UtilityName, CertificateNumber | ✅ Verified |
| **AR** | Arkansas GIS Office | `gis.arkansas.gov/.../FeatureServer/11` | NAME | ✅ Verified |
| **CA** | California CEC | `services3.arcgis.com/bWPjFyq029ChCGur/.../FeatureServer/0` | Utility, Acronym, Type, URL, Phone | ✅ Verified |
| **CO** | Colorado CDOT | `services.arcgis.com/yzB9WM8W0BO3Ql7d/.../FeatureServer/0` | COMPNAME, HOLDINGCO | ✅ Verified |
| **DE** | Delaware FirstMap | `enterprise.firstmaptest.delaware.gov/.../FeatureServer/2` | ELECTRICPROVIDER | ✅ Verified |
| **FL** | Florida PSC | `services.arcgis.com/LBbVDC0hKPAnLRpO/.../FeatureServer/0` | UTILITY | ✅ Verified |
| **HI** | Island Mapping | Hardcoded by island coordinates | HECO/MECO/HELCO/KIUC | ✅ Simple state |
| **IL** | Illinois Broadband Office | `services2.arcgis.com/aIextLMvCaGy1odc/.../FeatureServer/0` | COMPANY | ✅ Verified |
| **KY** | Kentucky PSC (KyGIS) | `kygisserver.ky.gov/.../MapServer/1` | COMPANY_NA | ✅ Verified |
| **MA** | MassGIS | `arcgisserver.digital.mass.gov/.../MapServer/0` | ELEC, TOWN | ✅ Verified |
| **ME** | Maine PUC | `services1.arcgis.com/RbMX0mRVOFNTdLzd/.../FeatureServer/0` | UTIL_NAME, OWNER, Type | ✅ Verified |
| **MI** | Michigan MPSC | `services3.arcgis.com/943LBv9FP414WfDO/.../FeatureServer/16` | Name, Type, Customers, Website, Phone | ✅ Verified |
| **MS** | Mississippi PSC (MDEQ) | `gisonline.ms.gov/.../MapServer/149` | NAME | ✅ Verified |
| **NE** | Nebraska GIS | `gis.ne.gov/.../FeatureServer/0` | DISTRICT, SearchName | ✅ Verified |
| **NJ** | New Jersey DEP | `mapsdep.nj.gov/.../MapServer/10` | NAME | ✅ Verified |
| **NY** | New York PSC | `services2.arcgis.com/Iru0GxDFgGL6jQqp/.../FeatureServer/0` | comp_full, comp_short | ✅ Verified |
| **OH** | Ohio PUCO (TIMS) | `gis.dot.state.oh.us/.../MapServer/12` | COMPANY_NAME | ✅ Verified |
| **OR** | Oregon ODOE | `services.arcgis.com/uUvqNMGPm7axC2dD/.../FeatureServer/0` | NAME | ✅ Verified |
| **PA** | Pennsylvania PUC | `services1.arcgis.com/vN4mLviHyDbqMDjA/.../FeatureServer/0` | COMPANY | ✅ Verified |
| **RI** | Simple State | Hardcoded (Rhode Island Energy) | ~99% one utility | ✅ Simple state |
| **TX** | Texas PUC | `services6.arcgis.com/N6Lzvtb46cpxThhu/...` | COMPANY_NAME, COMPANY_TYPE | ✅ Verified |
| **UT** | Utah AGRC | `services1.arcgis.com/99lidPhWCzftIe9K/.../FeatureServer/0` | PROVIDER | ✅ Verified |
| **VT** | Vermont PSD (VCGI) | `maps.vcgi.vermont.gov/.../MapServer/0` | COMPANYNAM | ✅ Verified |
| **WA** | Washington UTC | `services2.arcgis.com/lXwA5ckdH5etcXUm/.../FeatureServer/0` | NAME, FULLNAME | ✅ Verified |
| **WI** | Wisconsin PSC | `maps.psc.wi.gov/.../MapServer/0` | Util_Name | ✅ Verified |
| **SC** | SC Emergency Mgmt (Palmetto EOC) | `maps.palmettoeoc.net/.../MapServer/3` | Provider, EMSYS | ✅ Verified |
| **IA** | Iowa Utilities Commission | `services.arcgis.com/vPD5PVLI6sfkZ5E4/.../FeatureServer/14` | Owner, ESB_Type, WebsiteURL | ✅ Verified |
| **VA** | Virginia SCC | `services3.arcgis.com/Ww6Zhg5FR2pLMf1C/.../FeatureServer/0` | Utility, Provider, Website, Phone | ✅ Verified |
| **IN** | Indiana IURC | `gisdata.in.gov/.../FeatureServer/0` | utilityname, name_abreviations | ✅ Verified |
| **KS** | Kansas KCC | `services1.arcgis.com/q2CglofYX6ACNEeu/.../FeatureServer/0` | Company_Na, CO_CODE, Outage_Map | ✅ Verified |
| **DC** | Simple Territory | Hardcoded (Pepco) | 100% single utility | ✅ Simple |
| **NC** | NCDOT | `services.arcgis.com/04HiymDgLlsbhaV4/.../FeatureServer/1,2,3` | NAME, TYPE, HOLDING_CO, CUSTOMERS | ✅ Verified |
| **MN** | Minnesota PUC | `feat.gisdata.mn.gov/.../MapServer/0,1,2` | full_name, type, phone, website | ✅ Verified |

### Texas Special Notes
Texas has **3 separate layers** that must be queried:
- **IOU:** `services6.arcgis.com/N6Lzvtb46cpxThhu/arcgis/rest/services/IOU/FeatureServer/300`
- **MUNI:** `services6.arcgis.com/N6Lzvtb46cpxThhu/arcgis/rest/services/MUNI/FeatureServer/320`
- **COOP:** `services6.arcgis.com/N6Lzvtb46cpxThhu/arcgis/rest/services/COOP_DIST/FeatureServer/310`

**IMPORTANT:** Use `inSR=4326` parameter when querying with WGS84 coordinates.

---

## Gas Utility APIs (10 States)

| State | API Source | Endpoint | Key Fields | Status |
|-------|------------|----------|------------|--------|
| **AK** | Alaska RCA (DCCED) | `maps.commerce.alaska.gov/.../MapServer/93` | UtilityName | ✅ Verified |
| **CA** | California CalEMA | `services3.arcgis.com/bWPjFyq029ChCGur/.../FeatureServer/0` | SERVICE, ABR | ✅ Verified |
| **KY** | Kentucky PSC | `services3.arcgis.com/ghsX9CKghMvyYjBU/.../FeatureServer/0` | NAME | ✅ Verified |
| **MA** | MassGIS | `arcgisserver.digital.mass.gov/.../MapServer/0` | GAS, TOWN | ✅ Verified |
| **MS** | Mississippi PSC | `gisonline.ms.gov/.../MapServer/...` | NAME | ✅ Verified |
| **NJ** | New Jersey DEP | `mapsdep.nj.gov/.../MapServer/9` | NAME | ✅ Verified |
| **OR** | Oregon ODOE | `services.arcgis.com/uUvqNMGPm7axC2dD/.../FeatureServer/0` | Utility_Name (NG_or_Electric="Natural Gas") | ✅ Verified |
| **UT** | Utah AGRC | `services1.arcgis.com/99lidPhWCzftIe9K/.../FeatureServer/0` | PROVIDER | ✅ Verified |
| **WA** | Washington UTC | `services2.arcgis.com/lXwA5ckdH5etcXUm/.../FeatureServer/0` | OPER_NM | ✅ Verified |
| **WI** | Wisconsin PSC | `services8.arcgis.com/IqcU3SH8HrYEvDe4/.../FeatureServer/0` | Util_Name | ✅ Verified |

---

## Remaining States Without GIS APIs

These states don't have publicly accessible state-maintained FeatureServer endpoints:

| State | Notes |
|-------|-------|
| **GA** | Georgia Power map only - no statewide data |
| **TN** | TVA region - no state GIS found |
| **AL** | No statewide FeatureServer found |
| **LA** | Only Baton Rouge area available |
| **MO** | Only co-op map found (not statewide) |
| **OK** | No statewide FeatureServer found |
| **AZ** | No statewide FeatureServer found |
| **NV** | NV Energy dominates (~90%) but no GIS |
| **NM** | PNM dominates but no GIS |
| **MT** | NorthWestern Energy dominates but no GIS |
| **ID** | Idaho Power dominates but no GIS |
| **WY** | Rocky Mountain Power dominates but no GIS |
| **ND** | Xcel Energy dominates but no GIS |
| **SD** | Xcel/Black Hills dominate but no GIS |
| **WV** | Appalachian Power dominates but no GIS |
| **CT** | Eversource dominates but no GIS |
| **NH** | Eversource dominates but no GIS |
| **MD** | BGE/Pepco dominate but no GIS |

---

## States Using HIFLD Fallback

These states use HIFLD nationwide data as fallback:

**Electric (17 states):** AL, AZ, CT, GA, ID, LA, MD, MO, MT, ND, NH, NM, NV, OK, SD, TN, WV, WY

**Gas (40 states):** All states except AK, CA, KY, MA, MS, NJ, OR, UT, WA, WI

---

## Fallback APIs (Nationwide)

### HIFLD Electric
- **URL:** `https://services5.arcgis.com/HDRa0B57OVrv2E1q/arcgis/rest/services/Electric_Retail_Service_Territories/FeatureServer/0`
- **Fields:** NAME, STATE, TELEPHONE, WEBSITE, TYPE
- **Confidence:** Medium

### HIFLD Gas
- **URL:** `https://services5.arcgis.com/HDRa0B57OVrv2E1q/arcgis/rest/services/Natural_Gas_Local_Distribution_Company_Service_Territories/FeatureServer/0`
- **Fields:** NAME, STATE, TELEPHONE, WEBSITE, TYPE, HOLDINGCO
- **Confidence:** Medium

---

## Network Inspection Technique

For "view only" ArcGIS Hub and Experience Builder apps, use browser DevTools Network tab to capture the underlying FeatureServer URLs:

1. Open the web map in browser
2. Open DevTools (F12) → Network tab
3. Filter by "query" or "FeatureServer"
4. Click on the map to trigger a query
5. Copy the request URL and extract the FeatureServer endpoint

**Successfully extracted via network inspection:**
- Texas PUC (IOU/MUNI/COOP layers)
- Michigan MPSC
- California CEC
- South Carolina SCEMD (Palmetto EOC)
- Iowa IUC
- Virginia SCC
- Indiana IURC
- Kansas KCC
- North Carolina NCDOT (3 layers: Coop/Muni/IOU)
- Minnesota PUC (3 layers: Muni/Coop/IOU)

---

## Summary Statistics

| Category | Count |
|----------|-------|
| Electric APIs (state-specific) | 33 + DC |
| Gas APIs (state-specific) | 10 |
| States using HIFLD fallback (electric) | 17 |
| States using HIFLD fallback (gas) | 40 |
| Total US coverage | 50 states + DC |

---

## Files Modified

- `/Users/marklindquist/CascadeProjects/Utility Provider scrape/gis_utility_lookup.py` - Contains all state-specific lookup functions
- `/Users/marklindquist/CascadeProjects/Utility Provider scrape/utility_lookup.py` - Main lookup module with GIS integration

---

## Next Steps

1. **Add simple state lookups** for states with dominant single utilities (NV, MT, WY, etc.)
2. **Test Minnesota** - DNS resolution issues with `app.gisdata.mn.gov`
3. **Add more gas APIs** - Most states only have HIFLD coverage
4. **Consider Playwright scrapers** for states with address lookup tools only (MO, etc.)

---

## Simple State Candidates

These states have very simple utility landscapes that could use hardcoded lookups:

| State | Dominant Utility | Coverage | Notes |
|-------|-----------------|----------|-------|
| **DC** | Pepco | 100% | ✅ Already implemented |
| **NV** | NV Energy | ~90% | Las Vegas + Reno areas |
| **MT** | NorthWestern Energy | ~70% | Major cities |
| **WY** | Rocky Mountain Power | ~60% | PacifiCorp subsidiary |
| **ID** | Idaho Power | ~60% | Southern Idaho |
| **NM** | PNM | ~50% | Albuquerque + Santa Fe |
| **WV** | Appalachian Power | ~50% | Southern WV |
| **CT** | Eversource | ~80% | Formerly CL&P |
| **NH** | Eversource | ~70% | Formerly PSNH |
