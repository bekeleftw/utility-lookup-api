# Electric Utility Service Territory GIS Endpoints

Master inventory of verified REST API endpoints for electric utility service territory data.

---

## Verified Endpoints

### South Carolina
**Status:** VERIFIED (2026-01-18)

**Source:** SC Emergency Management Division (SCEMD) via Palmetto EOC

| Layer | ID | Type | Description |
|-------|-----|------|-------------|
| Nuclear Plants | 0 | Point | Nuclear facility locations |
| Power Plants | 1 | Point | Utility power plant facilities |
| (Unknown) | 2 | TBD | Not tested |
| Service Territories | 3 | Polygon | Electric utility service areas |

**Service Territory Endpoint:**
```
https://maps.palmettoeoc.net/arcgis/rest/services/SCEMD_Services/sc_utility_providers/MapServer/3
```

**Query Examples:**
```
# List all providers (no geometry)
/query?where=1=1&outFields=Provider,EMSYS&returnGeometry=false&f=json

# Get features with geometry
/query?where=1=1&outFields=*&f=json&resultRecordCount=10
```

**Key Fields:**
- `Provider` - Utility company name
- `EMSYS` - Emergency management system identifier

**Notes:**
- Server migrated from `pservices.emd.sc.gov` to `maps.palmettoeoc.net`
- Original Web AppBuilder config (2018) referenced defunct server
- Coordinate system: NAD83 UTM Zone 17N (WKID 26917)

---

### Iowa
**Status:** VERIFIED (2026-01-18)

**Source:** Iowa Utilities Commission (IUC)

**Service Territory Endpoint:**
```
https://services.arcgis.com/vPD5PVLI6sfkZ5E4/arcgis/rest/services/Electrical_Service_Boundaries/FeatureServer/14
```

**Query Examples:**
```
# List all providers (no geometry)
/query?where=1=1&outFields=Owner,ESB_Type,WebsiteURL,Emergency_Phone&returnGeometry=false&f=json

# Get features with geometry
/query?where=1=1&outFields=*&f=json&resultRecordCount=10
```

**Key Fields:**
- `Owner` - Utility name
- `ESB_Type` - Utility type (REC, Municipal, IOU, Amana Society, etc.)
- `ESB_ID` - Electric Service Boundary ID
- `WebsiteURL` - Utility website
- `Emergency_Phone` - Emergency contact number

**Geometry Type:** esriGeometryPolygon
**Coordinate System:** WKID 102004 (USA Contiguous Lambert Conformal Conic)

**Data Currency:** Last edited December 2024

**Sample Utilities:**
- Amana Society Service Co.
- Prairie Energy Coop.
- Heartland Power Cooperative
- MidAmerican Energy

---

### Colorado
**Status:** VERIFIED (2026-01-18)

**Source:** Colorado DOT (CDOT) via ArcGIS Online

**Service Territory Endpoint:**
```
https://services.arcgis.com/yzB9WM8W0BO3Ql7d/arcgis/rest/services/Utilities_Boundaries/FeatureServer/0
```

**Query Examples:**
```
# List all providers (no geometry)
/query?where=1=1&outFields=COMPNAME,HOLDINGCO,COMPTYPE,WEBSITE,PHONE&returnGeometry=false&f=json

# Get features with geometry
/query?where=1=1&outFields=*&f=json&resultRecordCount=10
```

**Key Fields:**
- `COMPNAME` - Company name
- `HOLDINGCO` - Holding company
- `COMPTYPE` - Utility type (IOU, MUNI, COOP)
- `COMPID` - Company ID
- `WEBSITE`, `PHONE`, `EMAIL`, `ADDRESS`, `CITY`, `STATE`, `ZIP`
- Revenue/Customer Data:
  - `RESREV`, `RESMWH`, `RESCUST`, `RESRATE` - Residential
  - `COMREV`, `COMMWH`, `COMCUST`, `COMRATE` - Commercial
  - `INDREV`, `INDMWH`, `INDCUST`, `INDRATE` - Industrial
- `YEAR` - Data year

**Geometry Type:** esriGeometryPolygon
**Coordinate System:** Web Mercator (WKID 3857)

**Sample Utilities:**
- Black Hills Energy (IOU)
- PSC of Colorado / Xcel Energy (IOU)
- Aspen Municipal Electric System (MUNI)

**Notes:** Rich dataset derived from HIFLD with detailed revenue and customer statistics.

---

### Virginia
**Status:** VERIFIED (2026-01-18)

**Source:** Virginia State Corporation Commission (SCC) via ArcGIS Online

**Service Territory Endpoint:**
```
https://services3.arcgis.com/Ww6Zhg5FR2pLMf1C/arcgis/rest/services/VA_Electric_2016/FeatureServer/0
```

**Query Examples:**
```
# List all providers (no geometry)
/query?where=1=1&outFields=Provider,Utility,Website,Phone&returnGeometry=false&f=json

# Get features with geometry
/query?where=1=1&outFields=*&f=json&resultRecordCount=10
```

**Key Fields:**
- `Provider` - Short utility code (e.g., ANEC, APC, BARC)
- `Utility` - Full utility name
- `Website` - Utility website URL
- `Phone` - Contact phone number

**Geometry Type:** esriGeometryPolygon
**Coordinate System:** Lambert Conformal Conic Virginia (NAD83)

**Sample Utilities:**
- A&N Electric Cooperative
- Appalachian Power Company
- BARC Electric Cooperative
- Dominion Energy Virginia

---

### Illinois
**Status:** VERIFIED (2026-01-18)

**Source:** Illinois Office of Broadband / Connected Nation via ArcGIS Online

**Service Territory Endpoint:**
```
https://services.arcgis.com/R0IGaIgf2sox9aCY/arcgis/rest/services/IL_Boundary_Layers/FeatureServer/3
```

**Query Examples:**
```
# List all providers (no geometry)
/query?where=1=1&outFields=NAME,TYPE,HOLDING_CO,CUSTOMERS&returnGeometry=false&f=json

# Get features with geometry
/query?where=1=1&outFields=*&f=json&resultRecordCount=10
```

**Key Fields:**
- `NAME` - Utility name
- `TYPE` - Utility type (INVESTOR OWNED, COOPERATIVE)
- `HOLDING_CO` - Holding company
- `ID` - EIA ID
- `ADDRESS`, `CITY`, `STATE`, `ZIP`, `TELEPHONE`, `WEBSITE`
- `NAICS_CODE`, `NAICS_DESC`
- `CNTRL_AREA` - Control area (MISO, PJM, etc.)
- `PLAN_AREA` - Planning area
- `CUSTOMERS` - Customer count
- `RETAIL_MWH`, `WSALE_MWH`, `TOTAL_MWH` - Sales data
- `SUMMR_PEAK`, `WINTR_PEAK` - Peak demand
- `SUMMER_CAP`, `WINTER_CAP` - Capacity
- `YEAR` - Data year

**Geometry Type:** esriGeometryPolygon
**Coordinate System:** Web Mercator (WKID 3857)
**Record Count:** 69

**Sample Utilities:**
- Ameren Illinois Company (Investor Owned, 1.2M customers)
- Commonwealth Edison Co / Exelon (Investor Owned, 4M customers)
- Southwestern Electric Coop Inc (Cooperative, 23K customers)

**Notes:** HIFLD-derived dataset with comprehensive operational data. Part of IL_Boundary_Layers service which likely contains other boundary types.

---

### North Carolina
**Status:** VERIFIED (2026-01-18)

**Source:** NCDOT via ArcGIS Online

**Service Territory Endpoints (3 layers by type):**
```
# Cooperative utilities (EMCs)
https://services.arcgis.com/04HiymDgLlsbhaV4/arcgis/rest/services/NCDOT_Electric_Power_Retail_Service_Territories_4_WFL1/FeatureServer/1

# Municipal utilities
https://services.arcgis.com/04HiymDgLlsbhaV4/arcgis/rest/services/NCDOT_Electric_Power_Retail_Service_Territories_4_WFL1/FeatureServer/2

# Investor-Owned utilities
https://services.arcgis.com/04HiymDgLlsbhaV4/arcgis/rest/services/NCDOT_Electric_Power_Retail_Service_Territories_4_WFL1/FeatureServer/3
```

**Query Examples:**
```
# Query each layer
/1/query?where=1=1&outFields=NAME,TYPE,CUSTOMERS,TELEPHONE,WEBSITE&returnGeometry=false&f=json
/2/query?where=1=1&outFields=NAME,TYPE,CUSTOMERS&returnGeometry=false&f=json
/3/query?where=1=1&outFields=NAME,TYPE,HOLDING_CO,CUSTOMERS&returnGeometry=false&f=json
```

**Key Fields:**
- `NAME` - Utility name
- `TYPE` - Utility type (COOPERATIVE, MUNICIPAL, INVESTOR OWNED, STATE)
- `HOLDING_CO` - Holding company (Duke Energy Corp, Southern Company, etc.)
- `ADDRESS`, `CITY`, `STATE`, `ZIP`, `TELEPHONE`, `WEBSITE`
- `CNTRL_AREA` - Control area
- `CUSTOMERS` - Customer count
- `RETAIL_MWH`, `WSALE_MWH`, `TOTAL_MWH` - Sales data
- `SUMMR_PEAK`, `WINTR_PEAK` - Peak demand
- `YEAR` - Data year

**Geometry Type:** esriGeometryPolygon
**Coordinate System:** Web Mercator (WKID 3857)

**Sample Utilities:**
- Cooperative: EnergyUnited, French Broad EMC, Tideland EMC
- Municipal: City of Wilson, Town of Sharpsburg, City of Highlands
- Investor-Owned: Duke Energy Progress, Duke Energy Carolinas, Dominion NC

**Notes:** HIFLD-derived dataset. Query all three layers for complete coverage. Similar structure to Texas and Minnesota.

---

### Minnesota
**Status:** VERIFIED (2026-01-18)

**Source:** Minnesota PUC / MnGeo

**IMPORTANT:** Use `feat.gisdata.mn.gov` subdomain (not `app.gisdata.mn.gov` which has DNS issues)

**Service Territory Endpoints (3 layers by type):**
```
# Municipal utilities
https://feat.gisdata.mn.gov/arcgis/rest/services/EUSA/EUSA_Type/MapServer/0

# Cooperative utilities  
https://feat.gisdata.mn.gov/arcgis/rest/services/EUSA/EUSA_Type/MapServer/1

# Investor-Owned utilities
https://feat.gisdata.mn.gov/arcgis/rest/services/EUSA/EUSA_Type/MapServer/2
```

**Query Examples:**
```
# Query all three layers for complete coverage
/0/query?where=1=1&outFields=full_name,type,phone,website&returnGeometry=false&f=json
/1/query?where=1=1&outFields=full_name,type,phone,website&returnGeometry=false&f=json
/2/query?where=1=1&outFields=full_name,type,phone,website&returnGeometry=false&f=json

# Spatial query with coordinates (UTM Zone 15N, WKID 26915)
/query?geometry={x},{y}&geometryType=esriGeometryPoint&inSR=4326&outFields=*&f=json
```

**Key Fields:**
- `full_name` - Full utility name
- `abbrev` - Abbreviation
- `type` - Utility type (Municipal, Cooperative, Investor-Owned)
- `street`, `city`, `state`, `zip`, `zip4`
- `phone`, `website`, `email`
- `mn_utility_id` - Minnesota utility ID
- `eia_utility_id` - EIA utility ID
- `mpuc_name` - MPUC registered name

**Geometry Type:** esriGeometryPolygon
**Coordinate System:** NAD83 UTM Zone 15N (WKID 26915)

**Sample Utilities:**
- Municipal: Rochester Public Utilities, City of Luverne
- Cooperative: People's Energy, McLeod Coop, Agralite
- Investor-Owned: Xcel Energy, Minnesota Power, Otter Tail Power

**Notes:** Official EUSA (Electric Utility Service Areas) data from Minnesota PUC. Query all three layers for complete coverage.

---

## HIFLD National Dataset
**Status:** VERIFIED (2026-01-18)

National coverage via Homeland Infrastructure Foundation-Level Data (DHS/ORNL):

**Base Service:**
```
https://maps.nccs.nasa.gov/mapping/rest/services/hifld_open/energy/FeatureServer
```

**Electric Retail Service Territories Layer:** Layer ID to be confirmed (listed as `electric_retail_service_territories`)

**Query for specific state:**
```
/query?where=STATE='XX'&outFields=*&f=json
```

**Pros:** Covers all 50 states in single endpoint
**Cons:** Less granular than state-specific data

**Alternative Access Points:**
- HIFLD Hub: https://hifld-geoplatform.hub.arcgis.com/datasets/geoplatform::electric-retail-service-territories-2
- EIA Atlas: https://atlas.eia.gov/datasets/geoplatform::electric-retail-service-territories
- OpenEnergyHub (ORNL): https://openenergyhub.ornl.gov/explore/dataset/electric-retail-service-territories/

---

## Extraction Method

For ArcGIS Hub "view only" pages:

1. Open the web map or app URL
2. Open browser DevTools (F12) → Network tab
3. Filter by `FeatureServer` or `MapServer`
4. Look for requests to `services*.arcgis.com` or state-hosted servers
5. Extract the base service URL
6. Test with `/query?where=1=1&outFields=*&f=json&resultRecordCount=5`
7. Verify `geometryType: esriGeometryPolygon` for service territories

Alternative: Hub pages often have an `/api` route (e.g., `/datasets/{dataset-name}/api`) showing the Query URL directly.

---

*Last updated: 2026-01-18*
