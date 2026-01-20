# GIS Utility Lookup - Deployment Verification Guide

## Problem
The deployed utility lookup tool is not returning the same results as local testing. For example:
- **Yakima, WA water lookup** returns "NOB HILL WATER ASSOCIATION" (EPA fallback) instead of "YAKIMA WATER DIVISION CITY OF" (Washington DOH state API)

## Root Cause
The deployment likely hasn't pulled the latest code from GitHub that includes state-specific GIS APIs.

---

## Key Files

### 1. `gis_utility_lookup.py`
Contains all state-specific GIS API query functions:
- **Water APIs**: 18 states (AR, AZ, CA, CT, DE, FL, KS, MS, NC, NJ, NM, NY, OK, PA, TN, TX, UT, WA)
- **Electric APIs**: 33 states
- **Gas APIs**: 13 states

Key functions:
- `lookup_water_utility_gis(lat, lon, state)` - Routes to state-specific water API
- `lookup_electric_utility_gis(lat, lon, state)` - Routes to state-specific electric API
- `lookup_gas_utility_gis(lat, lon, state)` - Routes to state-specific gas API

### 2. `utility_lookup.py`
Main orchestrator that imports and calls the GIS functions:
- Line 49: `from gis_utility_lookup import lookup_water_utility_gis, lookup_electric_utility_gis, lookup_gas_utility_gis`
- Line 3254: `gis_water = lookup_water_utility_gis(lat, lon, state)`

### 3. `test_gis_apis.py`
Test script to verify deployment status.

---

## Verification Steps

### Step 1: Run the test script on the deployed server
```bash
python3 test_gis_apis.py
```

### Step 2: Check the output

**Expected output if code is CURRENT:**
```
Water GIS states configured: 18
States: ['AR', 'AZ', 'CA', 'CT', 'DE', 'FL', 'KS', 'MS', 'NC', 'NJ', 'NM', 'NY', 'OK', 'PA', 'TN', 'TX', 'UT', 'WA']

Electric GIS states configured: 33
Gas GIS states configured: 13

WA (Yakima): YAKIMA WATER DIVISION CITY OF [source: washington_doh]
UT (Salt Lake City): Salt Lake City Water System [source: utah_dwre]
TN (Nashville): METRO WATER SERVICES [source: tennessee_tdec]
```

**If you see OUTDATED code:**
- Water GIS states < 18
- WA lookup returns `[source: epa_water_boundaries]` instead of `[source: washington_doh]`
- Missing states like UT, TN, NC, NM, OK, etc.

---

## How the State Routing Works

In `gis_utility_lookup.py`, the `lookup_water_utility_gis` function routes based on state:

```python
def lookup_water_utility_gis(lat: float, lon: float, state: str = None) -> Optional[Dict]:
    # Try state-specific sources first
    if state == "TX":
        result = query_texas_water_service_area(lat, lon)
        if result:
            return result
    elif state == "WA":
        result = query_washington_water(lat, lon)  # <-- This should be called for WA
        if result:
            return result
    # ... more states ...
    
    # Fall back to EPA national dataset
    return query_epa_water_service_area(lat, lon)
```

If the state-specific function (`query_washington_water`) doesn't exist or isn't in the routing, it falls back to EPA.

---

## State-Specific Water API Endpoints

| State | Function | Endpoint | Source |
|-------|----------|----------|--------|
| WA | `query_washington_water` | `services8.arcgis.com/.../Drinking_Water_Service_Areas` | washington_doh |
| UT | `query_utah_water` | `services.arcgis.com/.../CulinaryWaterServiceAreas` | utah_dwre |
| TN | `query_tennessee_water` | `services5.arcgis.com/.../TN_Public_Water_System_Service_Area_Boundaries` | tennessee_tdec |
| NC | `query_north_carolina_water` | `services.nconemap.gov/.../NC1Map_Water_Sewer_2004` | north_carolina_onemap |
| NM | `query_new_mexico_water` | `services2.arcgis.com/.../New_Mexico_Public_Water_Systems_Download` | new_mexico_ose |
| OK | `query_oklahoma_water` | `owrb.csa.ou.edu/.../Water_Systems` | oklahoma_owrb |
| AZ | `query_arizona_water` | `services.arcgis.com/.../CWS_Service_Area` | arizona_adwr |
| CT | `query_connecticut_water` | `maps.ct.gov/.../Test_Map_ESAa_MIL1` | connecticut_dph |
| DE | `query_delaware_water` | `enterprise.firstmap.delaware.gov/.../DE_CPCN` | delaware_psc |
| AR | `query_arkansas_water` | `gis.arkansas.gov/.../Utilities/FeatureServer/15` | arkansas_adh |
| KS | `query_kansas_water` | `services1.arcgis.com/.../KS_RuralWaterDistricts_SHP` | kansas_kdhe |
| FL | `query_florida_sjrwmd_water` | `services.arcgis.com/.../Public_Water_Supply_Area_SJRWMD` | florida_sjrwmd |

---

## Fix Actions

### If deployment is outdated:

1. **Trigger a redeploy** on Railway/hosting platform to pull latest from GitHub
2. **Verify the commit hash** matches the latest on GitHub (`6241568` as of this writing)
3. **Re-run `test_gis_apis.py`** to confirm fix

### If code is current but still not working:

1. Check if `GIS_LOOKUP_AVAILABLE` is `True` in `utility_lookup.py`
2. Check if `state` parameter is being passed correctly to `lookup_water_utility_gis`
3. Check for import errors in the logs

---

## Quick Manual Test

You can also test a specific endpoint directly:

```python
from gis_utility_lookup import query_washington_water

# Test Yakima, WA
result = query_washington_water(46.6021, -120.5059)
print(result)
# Expected: {'name': 'YAKIMA WATER DIVISION CITY OF', 'pws_id': '99150', 'county': 'YAKIMA', 'phone': '(509) 576-6480', 'confidence': 'high', 'source': 'washington_doh'}
```

If this returns `None` or an error, the function isn't working correctly.

---

## Latest Git Commits

```
6241568 Add GIS API test script for deployment verification
8040e61 Fix duplicate query_new_jersey_gas function
bda1b8f Update electric/gas GIS inventory with summary table
d7e1312 Add state-specific electric and gas GIS APIs
6221982 Add confidence explanations for water GIS lookups
44f924d Add Arkansas, Kansas, Florida (SJRWMD) water GIS APIs
7c3e1ea Add Arizona, Connecticut, Delaware water GIS APIs
f31e39b Add Oklahoma water GIS API (OWRB)
151e3af Add state-specific water GIS APIs: WA, UT, TN, NC, NM
```

The state water APIs were added in commit `151e3af`. If the deployment is older than this, it won't have the state-specific routing.
