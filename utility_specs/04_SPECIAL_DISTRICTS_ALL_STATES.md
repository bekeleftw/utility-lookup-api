# Special Utility Districts - All 50 States

## Overview

Special districts are independent government entities that provide utilities (water, sewer, sometimes electric) outside traditional city/county boundaries. They go by different names in different states but serve the same function.

This document catalogs data sources for every state. Use this as a reference when implementing special district lookups.

---

## Terminology by State

| State | Primary Terms | Abbreviations |
|-------|--------------|---------------|
| AL | Water Authorities, Utility Boards | - |
| AK | Boroughs, Utility Districts | - |
| AZ | Improvement Districts, Domestic Water Improvement Districts | DWID, ID |
| AR | Water Districts, Public Facility Boards | - |
| CA | Community Services Districts, County Water Districts, Municipal Water Districts | CSD, CWD, MWD |
| CO | Metropolitan Districts, Water & Sanitation Districts, Water Districts | Metro District, W&S |
| CT | Water Pollution Control Authorities, Regional Water Authorities | WPCA |
| DE | Sanitary Districts | - |
| FL | Community Development Districts, Special Districts | CDD |
| GA | Special Service Districts, Water & Sewer Authorities | SSD |
| HI | Board of Water Supply (by county) | BWS |
| ID | Water & Sewer Districts, Irrigation Districts | - |
| IL | Sanitary Districts, Water Districts, Water Reclamation Districts | - |
| IN | Conservancy Districts, Regional Water Districts | - |
| IA | Rural Water Districts, Sanitary Districts | RWD |
| KS | Rural Water Districts, Watershed Districts | RWD |
| KY | Water Districts, Sanitation Districts | - |
| LA | Water Districts, Sewer Districts, Waterworks Districts | - |
| ME | Water Districts, Sewer Districts | - |
| MD | Sanitary Districts, Metropolitan Districts | - |
| MA | Water Districts, Sewer Districts | - |
| MI | Water Authorities, DDA Districts | - |
| MN | Metropolitan Council (Twin Cities), Joint Powers | Met Council |
| MS | Water & Sewer Districts, Utility Authorities | - |
| MO | Water Supply Districts, Sewer Districts | - |
| MT | Water & Sewer Districts, Rural Water Districts | - |
| NE | Natural Resources Districts, Sanitary Improvement Districts | NRD, SID |
| NV | General Improvement Districts, Water Districts | GID |
| NH | Village Districts, Water Districts | - |
| NJ | Sewerage Authorities, Municipal Utilities Authorities | MUA |
| NM | Water & Sanitation Districts, Mutual Domestic Water Associations | MDWA |
| NY | Water Districts (town-level), Sewer Districts, Special Districts | - |
| NC | Sanitary Districts, Metropolitan Water Districts, Water & Sewer Authorities | MSD |
| ND | Rural Water Districts, Water Resource Districts | - |
| OH | Regional Water & Sewer Districts, Conservancy Districts | - |
| OK | Rural Water Districts, Master Conservancy Districts | RWD |
| OR | Special Districts, Water Districts, Sanitary Districts | - |
| PA | Municipal Authorities, Joint Authorities | - |
| RI | Water Districts, Fire Districts (some provide water) | - |
| SC | Special Purpose Districts, Water & Sewer Authorities | - |
| SD | Rural Water Systems, Sanitary Districts | - |
| TN | Utility Districts, Water & Wastewater Authorities | UD |
| TX | Municipal Utility Districts, Water Control & Improvement Districts, Fresh Water Supply Districts | MUD, WCID, FWSD |
| UT | Special Service Districts, Improvement Districts, Metropolitan Water Districts | SSD |
| VT | Fire Districts (some provide water), Water Districts | - |
| VA | Service Districts, Sanitary Districts, Water & Sewer Authorities | - |
| WA | Water-Sewer Districts, Public Utility Districts | PUD |
| WV | Public Service Districts | PSD |
| WI | Sanitary Districts, Metropolitan Sewerage Districts, Utility Districts | - |
| WY | Water & Sewer Districts, Joint Powers Boards | - |

---

## Data Sources by State

### ALABAMA
**Primary Source:** Alabama Department of Environmental Management (ADEM)
- URL: https://adem.alabama.gov/
- Data: Public water system list
- Format: Searchable database
- Boundaries: Not available as GIS

**Secondary:** Alabama Rural Water Association
- URL: https://www.alruralwater.com/
- Data: Member utility list

---

### ALASKA
**Primary Source:** Alaska Department of Environmental Conservation
- URL: https://dec.alaska.gov/eh/dw/
- Data: Public water systems
- Format: Database

**Note:** Most utilities are borough or city-operated. Few special districts.

---

### ARIZONA
**Primary Source:** Arizona Corporation Commission (ACC)
- URL: https://azcc.gov/utilities
- Data: Regulated water companies
- Format: Searchable database

**Secondary:** Arizona Department of Water Resources
- URL: https://new.azwater.gov/
- Data: Some district boundaries
- Format: GIS available for some areas

**Secondary:** Maricopa Association of Governments
- URL: https://azmag.gov/
- Data: Regional utility mapping

---

### ARKANSAS
**Primary Source:** Arkansas Department of Health - Engineering Section
- URL: https://www.healthy.arkansas.gov/programs-services/topics/engineering
- Data: Public water systems
- Format: Database

**Secondary:** Arkansas Rural Water Association
- URL: https://www.arruralwater.org/

---

### CALIFORNIA
**Primary Source:** State Controller's Office - Special Districts
- URL: https://bythenumbers.sco.ca.gov/
- Data: All special districts, financial data
- Format: Searchable database, downloadable

**Primary Source:** Local Agency Formation Commissions (LAFCOs)
- Each county has a LAFCO with district boundaries
- Example: LA County LAFCO: https://lalafco.org/
- Format: GIS boundaries available by county

**Secondary:** State Water Resources Control Board
- URL: https://www.waterboards.ca.gov/
- Data: Public water systems

**Coverage:** ~2,300 special districts

---

### COLORADO
**Primary Source:** Department of Local Affairs (DOLA) - Special District Database
- URL: https://dola.colorado.gov/lgis/
- Data: All special districts including metro districts
- Format: GIS boundaries available
- Download: https://data.colorado.gov/

**Secondary:** Colorado Special Districts Association
- URL: https://www.sdaco.org/

**Coverage:** ~1,800 metro/special districts

---

### CONNECTICUT
**Primary Source:** CT Department of Public Health - Drinking Water Section
- URL: https://portal.ct.gov/DPH/Drinking-Water/DWS/Drinking-Water-Section
- Data: Public water systems
- Format: Database

**Note:** Water utilities are mostly municipal or regional water authorities.

---

### DELAWARE
**Primary Source:** Delaware Public Service Commission
- URL: https://depsc.delaware.gov/
- Data: Regulated utilities

**Secondary:** DNREC - Division of Water
- URL: https://dnrec.delaware.gov/

**Note:** Small state, few special districts. Most water is municipal or private.

---

### FLORIDA
**Primary Source:** Department of Economic Opportunity - Special District Accountability Program
- URL: https://specialdistrictreports.floridajobs.org/
- Data: All special districts including CDDs
- Format: Searchable database

**Primary Source:** Florida DEP - Drinking Water Program
- URL: https://floridadep.gov/water/drinking-water

**Secondary:** Florida Association of Special Districts
- URL: https://www.fasd.com/

**Coverage:** ~1,800 special districts (600+ CDDs)

**Note:** CDDs are extremely common in new developments. Critical for water/sewer accuracy.

---

### GEORGIA
**Primary Source:** Georgia Department of Community Affairs
- URL: https://www.dca.ga.gov/
- Data: Special district information
- Format: Limited

**Secondary:** Georgia Environmental Protection Division
- URL: https://epd.georgia.gov/
- Data: Public water systems

**Secondary:** Georgia Association of Water Professionals
- URL: https://www.gawp.org/

---

### HAWAII
**Primary Source:** Board of Water Supply (each county)
- Honolulu BWS: https://www.boardofwatersupply.com/
- Maui DWS: https://www.mauicounty.gov/152/Water-Supply
- Hawaii County DWS: https://www.hawaiidws.org/
- Kauai DWS: https://www.kauaiwater.org/

**Note:** Centralized by county. No complex special district landscape.

---

### IDAHO
**Primary Source:** Idaho DEQ - Drinking Water Program
- URL: https://www.deq.idaho.gov/water-quality/drinking-water/
- Data: Public water systems
- Format: Database

**Secondary:** Idaho Rural Water Association
- URL: https://idahoruralwater.com/

---

### ILLINOIS
**Primary Source:** Illinois EPA - Bureau of Water
- URL: https://www2.illinois.gov/epa/topics/drinking-water/
- Data: Public water systems
- Format: Database

**Secondary:** Illinois Association of Wastewater Agencies
- URL: https://www.iawa-il.org/

**Secondary:** Metropolitan Water Reclamation District of Greater Chicago
- URL: https://mwrd.org/
- Data: Service area for Chicago region

---

### INDIANA
**Primary Source:** Indiana Utility Regulatory Commission (IURC)
- URL: https://www.in.gov/iurc/
- Data: Regulated utilities
- Format: Searchable database

**Secondary:** Indiana Finance Authority - Drinking Water SRF
- URL: https://www.in.gov/ifa/

---

### IOWA
**Primary Source:** Iowa DNR - Drinking Water
- URL: https://www.iowadnr.gov/Environmental-Protection/Water-Quality/Drinking-Water
- Data: Public water systems
- Format: Database

**Secondary:** Iowa Rural Water Association
- URL: https://iowaruralwater.org/

---

### KANSAS
**Primary Source:** Kansas Department of Health and Environment
- URL: https://www.kdhe.ks.gov/353/Public-Water-Supply-Section
- Data: Public water systems
- Format: Database

**Secondary:** Kansas Rural Water Association
- URL: https://www.krwa.net/

---

### KENTUCKY
**Primary Source:** Kentucky Division of Water
- URL: https://eec.ky.gov/Environmental-Protection/Water/
- Data: Public water systems
- Format: Database

**Secondary:** Kentucky Rural Water Association
- URL: https://www.krwa.org/

---

### LOUISIANA
**Primary Source:** Louisiana Department of Health - Drinking Water Program
- URL: https://ldh.la.gov/
- Data: Public water systems
- Format: Database

**Secondary:** Louisiana Rural Water Association
- URL: https://lrwa.org/

---

### MAINE
**Primary Source:** Maine Drinking Water Program
- URL: https://www.maine.gov/dhhs/mecdc/environmental-health/dwp/
- Data: Public water systems
- Format: Database

**Note:** Many small water districts. Limited centralized GIS.

---

### MARYLAND
**Primary Source:** Maryland Department of the Environment
- URL: https://mde.maryland.gov/programs/water/
- Data: Public water systems
- Format: Database

**Secondary:** Washington Suburban Sanitary Commission (WSSC)
- URL: https://www.wsscwater.com/
- Data: Serves Montgomery and Prince George's counties

---

### MASSACHUSETTS
**Primary Source:** MassDEP - Drinking Water Program
- URL: https://www.mass.gov/orgs/drinking-water-program
- Data: Public water systems
- Format: Database

**Secondary:** Massachusetts Water Resources Authority (MWRA)
- URL: https://www.mwra.com/
- Data: Serves Boston metro area

---

### MICHIGAN
**Primary Source:** Michigan EGLE - Drinking Water
- URL: https://www.michigan.gov/egle/about/organization/drinking-water-and-environmental-health
- Data: Public water systems
- Format: Database

**Secondary:** Great Lakes Water Authority
- URL: https://www.glwater.org/
- Data: Serves Detroit metro area

---

### MINNESOTA
**Primary Source:** Minnesota Department of Health - Drinking Water
- URL: https://www.health.state.mn.us/communities/environment/water/
- Data: Public water systems
- Format: Database

**Secondary:** Metropolitan Council (Twin Cities)
- URL: https://metrocouncil.org/Wastewater-Water.aspx
- Data: Regional service for Twin Cities

---

### MISSISSIPPI
**Primary Source:** Mississippi State Department of Health
- URL: https://msdh.ms.gov/msdhsite/_static/30,0,77.html
- Data: Public water systems
- Format: Database

**Secondary:** Mississippi Rural Water Association
- URL: https://msruralwater.com/

---

### MISSOURI
**Primary Source:** Missouri DNR - Drinking Water Section
- URL: https://dnr.mo.gov/water/drinking-water-sanitary-sewer
- Data: Public water systems
- Format: Database

**Secondary:** Missouri Rural Water Association
- URL: https://www.moruralwater.org/

---

### MONTANA
**Primary Source:** Montana DEQ - Public Water Supply
- URL: https://deq.mt.gov/water/Programs/pws
- Data: Public water systems
- Format: Database

**Secondary:** Montana Rural Water Systems
- URL: https://www.mrws.org/

---

### NEBRASKA
**Primary Source:** Nebraska Department of Environment and Energy
- URL: https://dee.ne.gov/
- Data: Public water systems and Sanitary Improvement Districts (SIDs)
- Format: Database

**Note:** SIDs are common in subdivisions around Omaha and Lincoln.

---

### NEVADA
**Primary Source:** Nevada Division of Environmental Protection
- URL: https://ndep.nv.gov/
- Data: Public water systems
- Format: Database

**Secondary:** Las Vegas Valley Water District
- URL: https://www.lvvwd.com/
- Data: Major provider for Las Vegas area

**Secondary:** General Improvement Districts (various)
- County-level data

---

### NEW HAMPSHIRE
**Primary Source:** NH DES - Drinking Water Program
- URL: https://www.des.nh.gov/water/drinking-water
- Data: Public water systems
- Format: Database

---

### NEW JERSEY
**Primary Source:** NJ DEP - Water Supply
- URL: https://www.nj.gov/dep/watersupply/
- Data: Public water systems
- Format: Database

**Secondary:** NJ Board of Public Utilities
- URL: https://www.nj.gov/bpu/
- Data: Regulated utilities

**Note:** Many Municipal Utilities Authorities (MUAs).

---

### NEW MEXICO
**Primary Source:** NM Environment Department - Drinking Water Bureau
- URL: https://www.env.nm.gov/drinking_water/
- Data: Public water systems
- Format: Database

**Note:** Many Mutual Domestic Water Associations (MDWAs) in rural areas.

---

### NEW YORK
**Primary Source:** NY DOH - Bureau of Water Supply Protection
- URL: https://www.health.ny.gov/environmental/water/drinking/
- Data: Public water systems
- Format: Database

**Secondary:** Town-level water and sewer districts
- Data at county or town level
- Limited centralized GIS

**Secondary:** NYC DEP (New York City)
- URL: https://www.nyc.gov/site/dep/
- Data: NYC water service

---

### NORTH CAROLINA
**Primary Source:** NC DEQ - Public Water Supply Section
- URL: https://www.deq.nc.gov/about/divisions/water-resources/drinking-water
- Data: Public water systems
- Format: Database

**Secondary:** NC Association of Regional Councils of Government
- Regional utility mapping available

---

### NORTH DAKOTA
**Primary Source:** ND DEQ - Drinking Water Program
- URL: https://deq.nd.gov/MF/
- Data: Public water systems
- Format: Database

**Secondary:** North Dakota Rural Water Systems Association
- URL: https://www.ndrural.org/

---

### OHIO
**Primary Source:** Ohio EPA - Division of Drinking and Ground Waters
- URL: https://epa.ohio.gov/divisions-and-offices/drinking-and-ground-waters
- Data: Public water systems
- Format: Database

**Secondary:** Ohio Water Development Authority
- URL: https://www.owda.org/

---

### OKLAHOMA
**Primary Source:** Oklahoma DEQ - Water Quality Division
- URL: https://www.deq.ok.gov/water-quality-division/
- Data: Public water systems
- Format: Database

**Secondary:** Oklahoma Rural Water Association
- URL: https://www.orwa.org/

---

### OREGON
**Primary Source:** Oregon Health Authority - Drinking Water Services
- URL: https://www.oregon.gov/oha/ph/healthyenvironments/drinkingwater/
- Data: Public water systems
- Format: Database

**Secondary:** Special Districts Association of Oregon
- URL: https://sdao.com/

---

### PENNSYLVANIA
**Primary Source:** PA DEP - Bureau of Safe Drinking Water
- URL: https://www.dep.pa.gov/Business/Water/BureauSafeDrinkingWater/
- Data: Public water systems
- Format: Database

**Note:** Many Municipal Authorities. Data often at county level.

---

### RHODE ISLAND
**Primary Source:** RI DOH - Center for Drinking Water Quality
- URL: https://health.ri.gov/programs/detail.php?pgm_id=113
- Data: Public water systems
- Format: Database

---

### SOUTH CAROLINA
**Primary Source:** SC DHEC - Drinking Water
- URL: https://scdhec.gov/environment/your-water-coast/drinking-water
- Data: Public water systems
- Format: Database

---

### SOUTH DAKOTA
**Primary Source:** SD DENR - Drinking Water Program
- URL: https://denr.sd.gov/des/dw/drinkingwater.aspx
- Data: Public water systems
- Format: Database

**Secondary:** South Dakota Association of Rural Water Systems
- URL: https://www.sdarws.com/

---

### TENNESSEE
**Primary Source:** Tennessee Department of Environment and Conservation
- URL: https://www.tn.gov/environment/program-areas/wr-water-resources/water-quality0/drinking-water.html
- Data: Public water systems
- Format: Database

**Note:** Utility Districts (UDs) are common for water/sewer outside cities.

---

### TEXAS
**Primary Source:** TCEQ - Public Drinking Water
- URL: https://www.tceq.texas.gov/drinkingwater
- Data: Public water systems
- Format: Database

**Primary Source:** TCEQ - Special Districts GIS
- URL: https://www.tceq.texas.gov/gis
- Data: MUD, WCID, FWSD boundaries
- Format: Shapefiles
- Download: Direct download available

**Secondary:** Texas Commission on Environmental Quality
- District boundary maps

**Coverage:** ~1,200+ MUDs, plus WCID, FWSD, WSC

**Note:** This is highest priority. MUDs are critical for Texas accuracy.

---

### UTAH
**Primary Source:** Utah DEQ - Division of Drinking Water
- URL: https://deq.utah.gov/drinking-water
- Data: Public water systems
- Format: Database

**Secondary:** Special Service District database
- Available through Lieutenant Governor's office

---

### VERMONT
**Primary Source:** Vermont DEC - Drinking Water Program
- URL: https://dec.vermont.gov/water/drinking-water
- Data: Public water systems
- Format: Database

**Note:** Small state, most utilities are municipal or fire district.

---

### VIRGINIA
**Primary Source:** Virginia Department of Health - Office of Drinking Water
- URL: https://www.vdh.virginia.gov/drinking-water/
- Data: Public water systems
- Format: Database

**Secondary:** Virginia Association of Counties
- Service district information

---

### WASHINGTON
**Primary Source:** WA DOH - Office of Drinking Water
- URL: https://doh.wa.gov/community-and-environment/drinking-water
- Data: Public water systems (SENTRY database)
- Format: Database, downloadable

**Secondary:** WA MRSC - Special Purpose Districts
- URL: https://mrsc.org/explore-topics/governance/special-purpose-districts
- Data: PUDs, water-sewer districts
- Format: Documentation and some GIS

**Note:** PUDs provide electric and sometimes water in many areas.

---

### WEST VIRGINIA
**Primary Source:** WV DHHR - Environmental Health Services
- URL: https://dhhr.wv.gov/
- Data: Public water systems
- Format: Database

**Note:** Public Service Districts (PSDs) are common for water/sewer.

---

### WISCONSIN
**Primary Source:** Wisconsin DNR - Drinking Water
- URL: https://dnr.wisconsin.gov/topic/DrinkingWater
- Data: Public water systems
- Format: Database

---

### WYOMING
**Primary Source:** Wyoming DEQ - Water Quality Division
- URL: https://deq.wyoming.gov/water-quality/
- Data: Public water systems
- Format: Database

**Secondary:** Wyoming Rural Water Association
- URL: https://wyomingwater.org/

---

## National/Federal Data Sources

### US Census Bureau - Census of Governments
- URL: https://www.census.gov/programs-surveys/cog.html
- Data: List of all special districts by state and type
- Limitation: Names and types only, NO boundaries
- Use for: Validation, completeness checking

### EPA SDWIS (Safe Drinking Water Information System)
- URL: https://www.epa.gov/enviro/sdwis-search
- Data: All public water systems nationwide
- Format: Searchable database, downloadable
- Already integrated

### HIFLD (Homeland Infrastructure Foundation-Level Data)
- URL: https://hifld-geoplatform.opendata.arcgis.com/
- Data: Electric utility territories, some water
- Format: GIS
- Already integrated

---

## Priority Order for Implementation

### Tier 1 (High Volume, Good Data Available)
1. **Texas** - TCEQ GIS data for 1,200+ MUDs
2. **Florida** - Special District database, 600+ CDDs
3. **Colorado** - DOLA GIS data, 1,800 metro districts
4. **California** - LAFCO data by county (start with LA, Orange, San Diego, Riverside, San Bernardino)

### Tier 2 (Medium Volume, Moderate Data)
5. **Arizona** - ACC + county data
6. **Washington** - DOH SENTRY + PUD data
7. **Nevada** - GIDs + LVVWD
8. **Georgia** - Water authorities
9. **North Carolina** - Sanitary districts
10. **Tennessee** - Utility Districts

### Tier 3 (Lower Volume, Basic Integration)
11-50. Remaining states - integrate with EPA SDWIS as baseline, add state-specific sources where available

---

## Data Ingestion Strategy

For each state:

1. **Identify available data format**
   - GIS shapefiles → parse polygons, create point-in-polygon lookup
   - Database/CSV → create ZIP or city lookup table
   - PDF maps → manual data entry for major districts

2. **Normalize district records**
   ```json
   {
     "district_id": "TX-MUD-001234",
     "name": "Travis County MUD No. 4",
     "state": "TX",
     "type": "MUD",
     "services": ["water", "sewer"],
     "boundary_type": "polygon",
     "contact_phone": "512-555-1234",
     "contact_website": "https://..."
   }
   ```

3. **Create lookup indexes**
   - ZIP → [district_ids] for fast filtering
   - Subdivision name → district_id where available
   - Point-in-polygon for precise boundary matching

4. **Integrate into lookup priority**
   - Special districts checked BEFORE city utilities
   - Higher confidence when matched
