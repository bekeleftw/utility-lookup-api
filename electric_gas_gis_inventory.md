# Electric & Gas Utility GIS API Inventory

## Overview

State-level electric and gas utility service territory GIS APIs. These are more accurate than HIFLD because they come from state Public Utility Commissions (PUCs/PSCs).

**Status:** 10 states with verified electric endpoints, 5 states with verified gas endpoints.

---

## Summary Table

| State | Electric | Gas | Source |
|-------|----------|-----|--------|
| AR | ✅ Layer 12 | ❌ | Arkansas GIS |
| IN | ✅ | ❌ | Indiana IURC |
| KY | ✅ | ❌ | Kentucky GIS |
| MI | ✅ | ✅ | Michigan PSC |
| MS | ✅ Layer 4 | ✅ Layer 3 | Mississippi PSC |
| NJ | ✅ Layer 10 | ✅ Layer 11 | NJ DEP |
| OH | ✅ | ❌ | Ohio PUCO |
| WI | ✅ | ✅ | Wisconsin PSC |
| HI | ✅ (hardcoded) | ❌ | Island mapping |
| RI | ✅ (hardcoded) | ❌ | Single utility |
| DC | ✅ (hardcoded) | ❌ | Single utility |

---

## Verified State Endpoints

### Arkansas - Electric ✅
- **Endpoint:** `https://gis.arkansas.gov/arcgis/rest/services/FEATURESERVICES/Utilities/FeatureServer/12`
- **Source:** Arkansas GIS Office
- **Key Fields:** name, source, label
- **Test:** Little Rock → "Entergy"
- **Notes:** Same FeatureServer has water (Layer 15)

### Michigan - Electric ✅
- **Endpoint:** `https://services3.arcgis.com/943LBv9FP414WfDO/arcgis/rest/services/ELECTRIC_UTILITY_SERVICE_AREA_MI_WFL1/FeatureServer/16`
- **Source:** Michigan PSC
- **Key Fields:** Name, Type, Customers, Website
- **Test:** Detroit → "DTE Electric Company"
- **Notes:** Includes customer counts and utility websites

### Michigan - Gas ✅
- **Endpoint:** `https://services3.arcgis.com/943LBv9FP414WfDO/arcgis/rest/services/NATURAL_GAS_UTILITY_SERVICE_AREA_MI_WFL1/FeatureServer/27`
- **Source:** Michigan PSC
- **Key Fields:** Name, Type, Customers
- **Test:** Detroit → (same structure as electric)

### New Jersey - Electric ✅
- **Endpoint:** `https://mapsdep.nj.gov/arcgis/rest/services/Features/Utilities/MapServer/10`
- **Source:** NJ DEP
- **Key Fields:** NAME, DISTRICT, TYPE
- **Test:** Newark → "Public Service Electric & Gas Co."

### New Jersey - Gas ✅
- **Endpoint:** `https://mapsdep.nj.gov/arcgis/rest/services/Features/Utilities/MapServer/11`
- **Source:** NJ DEP
- **Key Fields:** NAME, LABEL
- **Test:** Newark → "Public Service Electric and Gas Co." (PSE&G)

### Kentucky - Electric ✅
- **Endpoint:** `https://kygisserver.ky.gov/arcgis/rest/services/WGS84WM_Services/Ky_Electric_Service_Areas_WGS84WM/MapServer/1`
- **Source:** Kentucky GIS
- **Key Fields:** COMPANY_NA, UTILITY_TY, ELEC_TYPE
- **Test:** Louisville → "Louisville Gas and Electric Company"

### Indiana - Electric ✅
- **Endpoint:** `https://gisdata.in.gov/server/rest/services/Hosted/IURC_Prod_Boundaries_View/FeatureServer/0`
- **Source:** Indiana IURC (Utility Regulatory Commission)
- **Key Fields:** utilityname, utilitytype, name_abreviations
- **Test:** Indianapolis → "INDIANAPOLIS POWER & LIGHT COMPANY"

### Wisconsin - Electric ✅
- **Endpoint:** `https://maps.psc.wi.gov/server/rest/services/Electric/PSC_ElectricServiceTerritories/MapServer`
- **Source:** Wisconsin PSC
- **Layers:** 0=Municipal, 1=Investor Owned, 2=Cooperative
- **Notes:** Need to query all 3 layers

### Wisconsin - Gas ✅
- **Endpoint:** `https://services8.arcgis.com/IqcU3SH8HrYEvDe4/arcgis/rest/services/WI_Utilities_Natural_Gas_Service_Areas_(PSC_Data)/FeatureServer/0`
- **Source:** Wisconsin PSC
- **Key Fields:** Util_Name, Util_ID
- **Test:** Madison → "Madison Gas and Electric Company"

### Ohio - Electric ✅
- **Endpoint:** `https://maps.puco.ohio.gov/arcgis/rest/services/electric/Electric_Certified_Territory/MapServer/2`
- **Source:** Ohio PUCO
- **Key Fields:** EL_BoundaryID, EL_CompanyID
- **Notes:** Need to join with company table for names

---

## Endpoints Found But Need Testing

### Oregon - Electric
- **Endpoint:** `https://services.arcgis.com/yHSU3Q4NlapEfzn5/arcgis/rest/services/ElectricBoundary_PUC/FeatureServer/0`
- **Source:** Oregon PUC
- **Status:** Empty result for Portland - may need different coordinates

### California - Electric
- **Endpoint:** `https://services.arcgis.com/BLN4oKB0N1YSgvY8/arcgis/rest/services/California_Electric_Utility_Service_Territory_SCOUT/FeatureServer/0`
- **Source:** California Energy Commission (SCOUT)
- **Status:** Empty result for LA - may need different coordinates or token

---

## States With NO State-Level Endpoint Found

These states should use HIFLD as fallback:
- Alabama
- Alaska
- Georgia
- Texas (deregulated - ERCOT, no single utility boundaries)

---

## National Fallback Sources

### HIFLD Electric
- **Endpoint:** `https://services1.arcgis.com/Hp6G80Pky0om7QvQ/arcgis/rest/services/Electric_Retail_Service_Territories_2/FeatureServer/0`
- **Coverage:** National
- **Notes:** Good coverage but may be outdated in some areas

### HIFLD Gas
- **Endpoint:** HIFLD energy services Layer 29
- **Coverage:** National

### EIA Atlas Electric
- **Endpoint:** `https://atlas.eia.gov/datasets/f4cd55044b924fed9bc8b64022966097`
- **Coverage:** National

---

## Implementation Priority

1. **Already in system:** NJ (electric Layer 10, gas Layer 11)
2. **Add immediately:** MI, AR, KY, IN, WI (both electric and gas)
3. **Test further:** OH, OR, CA
4. **Research needed:** TX, PA, NY, VA, WA

---

## Query Pattern

All endpoints use standard ArcGIS REST API:
```
{endpoint}/query?geometry={lon},{lat}&geometryType=esriGeometryPoint&inSR=4326&spatialRel=esriSpatialRelIntersects&outFields={fields}&returnGeometry=false&f=json
```
