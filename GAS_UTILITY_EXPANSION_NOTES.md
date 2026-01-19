# Gas Utility Data Expansion Notes

**For Claude - January 18, 2026**

This document summarizes the current state of gas utility data coverage and provides guidance for further expansion.

---

## Current Gas Coverage

### GIS APIs (13 States)

| State | Source | Endpoint | Key Fields |
|-------|--------|----------|------------|
| **AK** | Alaska RCA | `maps.commerce.alaska.gov/.../MapServer/93` | UtilityName |
| **CA** | California CalEMA | `services3.arcgis.com/bWPjFyq029ChCGur/.../FeatureServer/0` | SERVICE, ABR |
| **KY** | Kentucky PSC | `services3.arcgis.com/ghsX9CKghMvyYjBU/.../FeatureServer/0` | NAME |
| **MA** | MassGIS | `arcgisserver.digital.mass.gov/.../MapServer/0` | GAS, TOWN |
| **MI** | Michigan MPSC | `services3.arcgis.com/943LBv9FP414WfDO/.../FeatureServer/27` | Name, Type |
| **MS** | Mississippi PSC | `services2.arcgis.com/tONuKShmVp7yWQJL/.../FeatureServer/3` | UTILITY_NA |
| **NJ** | New Jersey DEP | `mapsdep.nj.gov/.../MapServer/9` | NAME |
| **OH** | Ohio | `services3.arcgis.com/ccRMrVzOSHBUG6X2/.../FeatureServer/0` | NAME, TYPE |
| **OR** | Oregon ODOE | `services.arcgis.com/uUvqNMGPm7axC2dD/.../FeatureServer/0` | Utility_Name |
| **UT** | Utah AGRC | `services1.arcgis.com/99lidPhWCzftIe9K/.../FeatureServer/0` | PROVIDER |
| **VA** | Virginia SCC | `services3.arcgis.com/Ww6Zhg5FR2pLMf1C/.../FeatureServer/3` | PROVIDER |
| **WA** | Washington UTC | `services2.arcgis.com/lXwA5ckdH5etcXUm/.../FeatureServer/0` | OPER_NM |
| **WI** | Wisconsin PSC | `services8.arcgis.com/IqcU3SH8HrYEvDe4/.../FeatureServer/0` | Util_Name |

### County-Based Lookups (4 States)

For states without GIS APIs, we built county-to-utility mappings:

| State | Major Utilities | Data File |
|-------|-----------------|-----------|
| **IL** | Nicor Gas, Peoples Gas, Ameren, MidAmerican, North Shore | `data/gas_county_lookups.json` |
| **PA** | PGW, PECO, UGI, Columbia Gas, Peoples, National Fuel | `data/gas_county_lookups.json` |
| **NY** | Con Edison, National Grid, National Fuel, Central Hudson, NYSEG, RG&E | `data/gas_county_lookups.json` |
| **TX** | Atmos Energy, CenterPoint, Texas Gas Service | `data/gas_county_lookups.json` |

### HIFLD Fallback (33 Remaining States)

States without specific coverage use HIFLD nationwide data:
```
https://services5.arcgis.com/HDRa0B57OVrv2E1q/arcgis/rest/services/Natural_Gas_Local_Distribution_Company_Service_Territories/FeatureServer/0
```

---

## Claude's Findings (Jan 18, 2026)

### Alternative Kentucky Endpoint
- **State-hosted:** `watermaps.ky.gov/arcgis/rest/services/WebMapServices/KY_Gas_Utility_Territories_WGS85WM/MapServer`
- **3 layers:** Overlapping Areas (1), Municipal (2), LDCs (3)
- **Fields:** NAME, ABBREV, PSC_ID, PSC_Reg
- More detailed than the existing services3.arcgis.com endpoint
- Verified working: Returns "Louisville Gas and Electric Company"

### Dead Ends Confirmed
- **EIA Atlas:** Down for maintenance
- **Southwest Gas:** No public GIS endpoint (AZ/NV rely on HIFLD)
- **Spire/Missouri:** No state GIS for gas
- **Tennessee:** No gas utility data in state GIS portal
- **Arizona:** Only HIFLD available

### Key Insight
> Gas utility GIS data is significantly rarer than electric. Most state-level gas data doesn't exist publicly. The 13 states with gas GIS APIs is likely the ceiling without major new data sources becoming available. HIFLD fallback for the remaining 37 states is the right approach.

---

## States That Need Work

### High Priority (Large Population, No Coverage)

| State | Notes | Potential Approach |
|-------|-------|-------------------|
| **FL** | No state GIS found | County lookup (TECO, Peoples Gas, Florida City Gas) |
| **GA** | No state GIS found | County lookup (Atlanta Gas Light dominates) |
| **NC** | NCDOT has electric but no gas | County lookup (Piedmont, PSNC, Dominion) |
| **IN** | IURC has electric but no gas | County lookup (CenterPoint, Vectren, NIPSCO) |
| **MN** | feat.gisdata.mn.gov has electric but no gas | County lookup (CenterPoint, Xcel, Great Plains) |
| **CO** | CDOT has electric but no gas | County lookup (Xcel, Black Hills, Atmos) |
| **MO** | No state GIS found | County lookup (Spire dominates) |
| **TN** | TVA region, no state GIS | County lookup (Piedmont, Atmos) |
| **AZ** | No state GIS found | County lookup (Southwest Gas dominates) |

### Medium Priority

| State | Notes |
|-------|-------|
| **CT** | Eversource, Southern CT Gas |
| **MD** | BGE, Washington Gas |
| **NV** | Southwest Gas dominates |
| **SC** | Dominion, Piedmont |

---

## Search Strategies That Worked

### 1. Check Same Org as Electric API
Gas is often a different layer in the same service:
- MI: Electric = Layer 16, Gas = Layer 27
- VA: Electric = Layer 0, Gas = Layer 3
- NJ: Electric = Layer 10, Gas = Layer 9

### 2. ArcGIS Online Search
```
https://www.arcgis.com/sharing/rest/search?q={State}+natural+gas+service+territory+type:Feature+Service&f=json
```

### 3. Network Inspection
For "view only" web maps, use browser DevTools Network tab to capture FeatureServer URLs.

---

## EIA Data (Not Directly Usable)

EIA Form 176 has company-level gas utility data but:
- No direct API access to company-level data
- Requires manual export from NGQS web interface
- Shows which companies operate in each state, not precise boundaries

NGQS: https://www.eia.gov/naturalgas/ngqs/

---

## Code Structure

### Files
- `gis_utility_lookup.py` - All GIS lookup functions
- `data/gas_county_lookups.json` - County-to-utility mappings

### Key Functions
```python
# GIS-based lookup
lookup_gas_utility_gis(lat, lon, state)

# County-based lookup
lookup_gas_by_county(state, county, city=None)

# Constants
STATES_WITH_GAS_GIS = {'AK', 'CA', 'KY', 'MA', 'MI', 'MS', 'NJ', 'OH', 'OR', 'UT', 'VA', 'WA', 'WI'}
STATES_WITH_GAS_COUNTY_LOOKUP = {'IL', 'PA', 'NY', 'TX'}
```

---

## Next Steps

1. **Add county lookups for more states** (FL, GA, NC, IN, MN, CO, MO, TN, AZ)
2. **Research state PUC websites** for certified gas utility lists
3. **Check for simple states** where one utility dominates (AZ, NV, MO)
4. **Integrate county lookup into main utility_lookup.py** flow

---

## County Lookup Data Format

```json
{
  "STATE": {
    "_notes": "Description",
    "_default": "Default utility if county not found",
    "counties": {
      "CountyName": {"utility": "Utility Name", "notes": "optional"},
      ...
    },
    "cities": {
      "CityName": {"utility": "Utility Name", "notes": "optional"},
      ...
    }
  }
}
```

---

*Created by Windsurf Cascade - January 18, 2026*
