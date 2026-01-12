# Utility Lookup Nationwide Reliability Improvements

Implementation guide for Windsurf to systematically improve accuracy across all 50 states.

## Current Status

| Layer | Coverage | Accuracy | Status |
|-------|----------|----------|--------|
| Electric | 50 states | ~90% | EIA 861 + HIFLD, needs muni/co-op work |
| Gas | 50 states | ~85% | ZIP-level boundary errors |
| Water | 50 states | ~75% | Most fragmented, SERP-first helps |
| Internet | 50 states | ~95% | FCC authoritative |
| Special Districts | TX, FL | High where covered | Need CO, CA, AZ, WA |

## Completed

- [x] Texas MUDs (TCEQ data, ~1,200 districts)
- [x] Florida CDDs (~600 districts)
- [x] Texas gas ZIP overrides (Kyle, Buda, San Marcos, etc.)
- [x] SERP-first water lookup
- [x] User feedback system
- [x] Confidence scoring system

---

## PHASE 1: Municipal Utilities (High Impact)

### Task 1.1: APPA Municipal Electric Utilities

~2,000 US cities run their own electric utilities. These are often missing from EIA/HIFLD data.

**Data Source:**
- American Public Power Association (APPA)
- URL: https://www.publicpower.org/public-power-data
- Also try: https://www.publicpower.org/system/files/documents/Public-Power-Statistical-Report-2023.pdf

**Implementation:**

1. Download or scrape the APPA member directory
2. Create `/data/municipal_utilities/electric_munis.json`:

```json
{
  "utilities": [
    {
      "name": "Austin Energy",
      "state": "TX",
      "city": "Austin",
      "zips": ["78701", "78702", "78703", "..."],
      "phone": "512-494-9400",
      "website": "https://austinenergy.com",
      "population_served": 500000,
      "source": "APPA"
    }
  ]
}
```

3. Modify `state_utility_verification.py` to check municipal utilities BEFORE EIA/HIFLD:

```python
def lookup_electric_utility(lat, lon, city, county, state, zip_code):
    # 1. User confirmed corrections
    # 2. Electric cooperatives (already implemented)
    # 3. Municipal utilities (NEW - add here)
    muni = lookup_municipal_electric(city, state, zip_code)
    if muni:
        return {
            'name': muni['name'],
            'confidence': 'verified',
            'confidence_score': 90,
            'source': 'municipal_utility_database',
            'phone': muni.get('phone'),
            'website': muni.get('website')
        }
    # 4. Continue with existing logic...
```

4. Priority cities to verify are in database:
   - Austin Energy (TX)
   - CPS Energy (San Antonio, TX)
   - LA DWP (Los Angeles, CA)
   - Seattle City Light (WA)
   - Sacramento Municipal Utility District (CA)
   - Orlando Utilities Commission (FL)
   - JEA (Jacksonville, FL)
   - Salt River Project (Phoenix, AZ)
   - Colorado Springs Utilities (CO)
   - Memphis Light, Gas & Water (TN)

**Verification:**
```bash
# Test municipal utility detection
curl "https://web-production-9acc6.up.railway.app/api/lookup?address=1100+Congress+Ave+Austin+TX"
# Should return Austin Energy with confidence: verified
```

---

### Task 1.2: Municipal Water Utilities

Many of the same cities run water utilities. Add to supplemental file.

**Implementation:**

1. Cross-reference APPA cities with water service
2. Add to `/data/water_utilities_supplemental.json`:

```json
{
  "TX|AUSTIN": {
    "name": "Austin Water",
    "phone": "512-972-0000",
    "website": "https://www.austintexas.gov/department/austin-water",
    "confidence": "verified",
    "source": "municipal_utility_database"
  },
  "TX|SAN ANTONIO": {
    "name": "San Antonio Water System (SAWS)",
    "phone": "210-704-7297",
    "website": "https://www.saws.org",
    "confidence": "verified",
    "source": "municipal_utility_database"
  }
}
```

3. Target: Add top 100 cities by population that have municipal water

---

## PHASE 2: Colorado Metro Districts

Colorado has ~1,800 metro districts, critical for Denver suburbs.

**Data Source:**
- DOLA (Dept of Local Affairs) Special District Database
- URL: https://dola.colorado.gov/lgis/
- GIS Download: https://dola.colorado.gov/gis-cms/content/special-districts

**Implementation:**

1. Download district boundaries (shapefile or GeoJSON)

2. Filter to water/sewer districts only. District types to include:
   - Water District
   - Water and Sanitation District
   - Metropolitan District (often includes water)
   - Sanitation District

3. Create `/data/special_districts/colorado/metro_districts.json`:

```json
{
  "districts": [
    {
      "district_id": "CO-METRO-001234",
      "name": "Highlands Ranch Metropolitan District",
      "type": "Metropolitan District",
      "services": ["water", "sewer"],
      "county": "Douglas",
      "boundary": {
        "type": "zip_list",
        "zips": ["80126", "80129", "80130"]
      },
      "contact": {
        "phone": "303-791-0430",
        "website": "https://highlandsranch.org"
      },
      "source": "DOLA"
    }
  ]
}
```

4. Create `/data/special_districts/colorado/zip_to_district.json`:

```json
{
  "80126": ["CO-METRO-001234", "CO-METRO-001235"],
  "80129": ["CO-METRO-001234"]
}
```

5. Add Colorado to special district lookup in `utility_lookup.py`:

```python
def lookup_special_district(lat, lon, state, zip_code, service='water'):
    if state == 'TX':
        return lookup_texas_mud(...)
    elif state == 'FL':
        return lookup_florida_cdd(...)
    elif state == 'CO':
        return lookup_colorado_metro_district(zip_code, service)
    # ... etc
```

**Priority Areas:**
- Douglas County (Highlands Ranch, Castle Rock, Parker)
- Arapahoe County (Aurora suburbs, Centennial)
- Jefferson County (Lakewood, Arvada, Golden)
- El Paso County (Colorado Springs suburbs)
- Larimer County (Fort Collins, Loveland)
- Weld County (Greeley, Windsor)

**Verification:**
```bash
# Test Colorado metro district detection
curl "https://web-production-9acc6.up.railway.app/api/lookup?address=9500+Highlands+Ranch+Pkwy+Highlands+Ranch+CO+80129"
# Should return Highlands Ranch Metropolitan District for water
```

---

## PHASE 3: State-by-State Gas LDC Mapping

Replicate Texas gas mapping for other large states.

### Task 3.1: California Gas Utilities

**Major Utilities:**
- SoCalGas (Southern California Gas Company) - SoCal
- PG&E (Pacific Gas & Electric) - NorCal
- SDG&E (San Diego Gas & Electric) - San Diego
- Southwest Gas - Desert areas

**Data Source:**
- CA PUC Service Territory Maps
- URL: https://www.cpuc.ca.gov/industries-and-topics/electrical-energy/electric-costs/utility-service-area-maps

**Implementation:**

1. Create `/data/gas_mappings/california.json`:

```json
{
  "zip_to_utility": {
    "900": "SoCalGas",
    "901": "SoCalGas",
    "902": "SoCalGas",
    "940": "PG&E",
    "941": "PG&E",
    "921": "SDG&E"
  },
  "zip_overrides": {
    "92260": "Southwest Gas"
  },
  "utilities": {
    "SoCalGas": {
      "name": "Southern California Gas Company",
      "phone": "1-800-427-2200",
      "website": "https://www.socalgas.com"
    },
    "PG&E": {
      "name": "Pacific Gas and Electric",
      "phone": "1-800-743-5000",
      "website": "https://www.pge.com"
    }
  }
}
```

2. Add California to `lookup_gas_utility()` in `state_utility_verification.py`

### Task 3.2: Illinois Gas Utilities

**Major Utilities:**
- Nicor Gas - Chicago suburbs, northern IL
- Peoples Gas - City of Chicago
- Ameren Illinois - Central/Southern IL
- North Shore Gas - North suburbs

**Data Source:**
- IL Commerce Commission
- URL: https://www.icc.illinois.gov/

**Implementation:** Same pattern as California.

### Task 3.3: Ohio Gas Utilities

**Major Utilities:**
- Columbia Gas of Ohio - Largest, most of state
- Dominion Energy Ohio - Northeast
- Duke Energy Ohio - Southwest (Cincinnati)
- CenterPoint Energy Ohio - Dayton area

### Task 3.4: Georgia Gas Utilities

**Major Utility:**
- Atlanta Gas Light (AGL) - Serves most of state (deregulated, similar to Texas)

Note: Georgia is deregulated for gas. AGL owns the pipes, but customers choose their marketer. Return AGL as the utility.

### Task 3.5: Arizona Gas Utilities

**Major Utilities:**
- Southwest Gas - Phoenix, Tucson metros
- Unisource Energy - Parts of southern AZ

### Implementation Pattern for All States:

```python
# state_utility_verification.py

GAS_STATE_MAPPINGS = {
    'TX': 'texas',
    'CA': 'california',
    'IL': 'illinois',
    'OH': 'ohio',
    'GA': 'georgia',
    'AZ': 'arizona'
}

def lookup_gas_utility_by_state(state, zip_code):
    if state not in GAS_STATE_MAPPINGS:
        return None
    
    mapping_file = f'/data/gas_mappings/{GAS_STATE_MAPPINGS[state]}.json'
    mapping = load_json(mapping_file)
    
    # Check 5-digit override first
    if zip_code in mapping.get('zip_overrides', {}):
        utility_key = mapping['zip_overrides'][zip_code]
        return mapping['utilities'][utility_key]
    
    # Check 3-digit prefix
    zip3 = zip_code[:3]
    if zip3 in mapping.get('zip_to_utility', {}):
        utility_key = mapping['zip_to_utility'][zip3]
        return mapping['utilities'][utility_key]
    
    return None
```

---

## PHASE 4: Electric Cooperative Complete Coverage

### Task 4.1: Verify NRECA Coverage

**Data Source:**
- NRECA (National Rural Electric Cooperative Association)
- URL: https://www.electric.coop/our-organization/nreca-members
- 832 distribution co-ops nationwide

**Implementation:**

1. Download NRECA member list
2. Cross-reference with HIFLD electric cooperative data
3. Identify gaps (co-ops in NRECA but not in HIFLD)
4. Add missing co-ops to `/data/electric_cooperatives_supplemental.json`:

```json
{
  "cooperatives": [
    {
      "name": "Example Electric Cooperative",
      "state": "OK",
      "counties": ["County1", "County2"],
      "zips": ["73001", "73002"],
      "phone": "405-555-1234",
      "website": "https://example-coop.com",
      "source": "NRECA"
    }
  ]
}
```

**Priority States (high co-op density):**
- Texas (~75 co-ops)
- Georgia (~41 co-ops)
- Oklahoma (~30 co-ops)
- North Carolina (~26 co-ops)
- Arkansas (~17 co-ops)
- Kentucky (~24 co-ops)
- Tennessee (~23 co-ops)

### Task 4.2: Co-op Detection Priority Fix

Ensure co-ops are ALWAYS checked before investor-owned utility data:

```python
def lookup_electric_utility(...):
    # 1. User corrections
    # 2. Electric cooperatives - MUST be before IOU data
    coop = lookup_electric_cooperative(lat, lon, state, county, zip_code)
    if coop:
        return {
            'name': coop['name'],
            'confidence': 'high',
            'source': 'electric_cooperative',
            'note': 'Electric cooperative - not in deregulated market'
        }
    # 3. Then municipal utilities
    # 4. Then IOU data (EIA, TDU mapping, etc.)
```

---

## PHASE 5: Water Supplemental Expansion

### Task 5.1: Top 500 Cities by Population

Systematically add water utilities for largest cities.

**Implementation:**

1. Get list of top 500 US cities by population
2. For each city not already in supplemental file:
   - Search "[city name] water utility"
   - Find official city/utility website
   - Extract phone, website, service area
   - Add to `water_utilities_supplemental.json`

3. Prioritize cities that appear in `/api/missing-cities` endpoint

**Automation approach:**

```python
# scripts/expand_water_supplemental.py

import requests

def research_water_utility(city, state):
    """
    Use SERP to find water utility info for a city.
    Returns structured data or None.
    """
    query = f"{city} {state} water utility department"
    # Use existing SERP verification logic
    # Extract utility name, phone, website from results
    pass

def expand_supplemental():
    # Load missing cities
    missing = requests.get('https://web-production-9acc6.up.railway.app/api/missing-cities').json()
    
    # Sort by count (most requested first)
    sorted_cities = sorted(missing.items(), key=lambda x: x[1]['count'], reverse=True)
    
    # Research top 50
    for city_key, data in sorted_cities[:50]:
        state, city = city_key.split('|')
        result = research_water_utility(city, state)
        if result:
            # Add to supplemental file
            pass
```

### Task 5.2: EPA SDWIS Gap Analysis

Identify cities where EPA data is incomplete.

```python
# Compare EPA SDWIS coverage to Census city list
# Flag cities with population > 10,000 that have no EPA match
# These need manual addition to supplemental file
```

---

## PHASE 6: California Special Districts

California is complex. Approach incrementally by county.

**Data Sources:**
- CA State Controller's Office: https://bythenumbers.sco.ca.gov/
- Individual county LAFCOs (Local Agency Formation Commissions)

### Task 6.1: Priority Counties

Start with highest-population counties:

| Rank | County | Population | LAFCO URL |
|------|--------|------------|-----------|
| 1 | Los Angeles | 10M | https://lalafco.org/ |
| 2 | San Diego | 3.3M | https://www.sdlafco.org/ |
| 3 | Orange | 3.2M | https://www.oclafco.org/ |
| 4 | Riverside | 2.4M | https://www.lafco.org/ |
| 5 | San Bernardino | 2.2M | https://www.sbclafco.org/ |
| 6 | Santa Clara | 1.9M | https://www.santaclaralafco.org/ |
| 7 | Alameda | 1.7M | https://www.acgov.org/lafco/ |
| 8 | Sacramento | 1.6M | https://www.saclafco.org/ |
| 9 | Contra Costa | 1.2M | https://www.contracostalafco.org/ |
| 10 | Fresno | 1M | https://www.fresnolafco.org/ |

### Task 6.2: Implementation per County

For each county:

1. Download district boundary data from LAFCO
2. Filter to water/sewer districts:
   - Community Services District (CSD)
   - County Water District (CWD)
   - Municipal Water District (MWD)
   - Irrigation District
   - Public Utility District

3. Create `/data/special_districts/california/{county}.json`

4. Add to ZIP mapping

**Note:** This is high effort. Do 1-2 counties per sprint.

---

## PHASE 7: Arizona Improvement Districts

### Task 7.1: Maricopa County (Phoenix Metro)

**Data Source:**
- Maricopa County Assessor
- AZ Dept of Water Resources: https://new.azwater.gov/

**District Types:**
- Domestic Water Improvement District (DWID)
- Improvement District
- Community Facilities District

**Implementation:**

1. Download district boundaries for Maricopa County
2. Create `/data/special_districts/arizona/maricopa.json`
3. Follow same pattern as Texas MUDs

### Task 7.2: Pima County (Tucson Metro)

Same approach for Tucson area.

---

## PHASE 8: Washington PUDs

### Task 8.1: PUD Coverage

**Data Source:**
- WA PUD Association: https://www.wpuda.org/
- ~60 PUDs statewide

**Note:** Washington PUDs provide ELECTRIC, not just water. Some also provide water.

**Implementation:**

1. Download PUD service territory data
2. Create `/data/electric_puds/washington.json`:

```json
{
  "puds": [
    {
      "name": "Snohomish County PUD",
      "services": ["electric"],
      "counties": ["Snohomish", "Island", "Camano"],
      "phone": "425-783-1000",
      "website": "https://www.snopud.com"
    },
    {
      "name": "Clark Public Utilities",
      "services": ["electric", "water"],
      "counties": ["Clark"],
      "phone": "360-992-3000",
      "website": "https://www.clarkpublicutilities.com"
    }
  ]
}
```

3. Add Washington PUD check to electric lookup (before IOU data)

---

## PHASE 9: Operational Excellence

### Task 9.1: Automated Accuracy Monitoring

**Implementation:**

Create `/scripts/accuracy_monitor.py`:

```python
"""
Weekly accuracy validation script.
Run via cron or Railway scheduled job.
"""

import random
import json
from datetime import datetime

def run_validation(sample_size=100):
    # 1. Get recent lookups from logs
    recent_lookups = get_recent_lookups(limit=1000)
    
    # 2. Random sample
    sample = random.sample(recent_lookups, min(sample_size, len(recent_lookups)))
    
    # 3. Re-verify each with SERP only
    results = []
    for lookup in sample:
        serp_result = verify_with_serp_only(lookup['address'])
        
        comparison = {
            'address': lookup['address'],
            'state': lookup['state'],
            'original_electric': lookup['electric'],
            'serp_electric': serp_result.get('electric'),
            'electric_match': lookup['electric'] == serp_result.get('electric'),
            'original_gas': lookup['gas'],
            'serp_gas': serp_result.get('gas'),
            'gas_match': lookup['gas'] == serp_result.get('gas'),
            'original_water': lookup['water'],
            'serp_water': serp_result.get('water'),
            'water_match': lookup['water'] == serp_result.get('water')
        }
        results.append(comparison)
    
    # 4. Calculate accuracy by utility type
    accuracy = {
        'electric': sum(r['electric_match'] for r in results) / len(results),
        'gas': sum(r['gas_match'] for r in results) / len(results),
        'water': sum(r['water_match'] for r in results) / len(results),
        'sample_size': len(results),
        'timestamp': datetime.utcnow().isoformat()
    }
    
    # 5. Calculate accuracy by state
    state_accuracy = {}
    for state in set(r['state'] for r in results):
        state_results = [r for r in results if r['state'] == state]
        if len(state_results) >= 5:  # Minimum sample size
            state_accuracy[state] = {
                'electric': sum(r['electric_match'] for r in state_results) / len(state_results),
                'gas': sum(r['gas_match'] for r in state_results) / len(state_results),
                'water': sum(r['water_match'] for r in state_results) / len(state_results),
                'sample_size': len(state_results)
            }
    
    # 6. Flag mismatches for review
    mismatches = [r for r in results if not all([
        r['electric_match'], r['gas_match'], r['water_match']
    ])]
    
    # 7. Save report
    report = {
        'overall_accuracy': accuracy,
        'state_accuracy': state_accuracy,
        'mismatches': mismatches,
        'alerts': generate_alerts(accuracy, state_accuracy)
    }
    
    save_report(report)
    
    # 8. Send alerts if thresholds breached
    if accuracy['electric'] < 0.90:
        send_alert(f"Electric accuracy dropped to {accuracy['electric']:.1%}")
    if accuracy['gas'] < 0.85:
        send_alert(f"Gas accuracy dropped to {accuracy['gas']:.1%}")
    if accuracy['water'] < 0.80:
        send_alert(f"Water accuracy dropped to {accuracy['water']:.1%}")
    
    return report
```

**API Endpoint:**

```python
@app.route('/api/admin/accuracy-report')
def get_accuracy_report():
    # Return latest accuracy report
    report = load_latest_report()
    return jsonify(report)
```

### Task 9.2: Problem Areas Auto-Detection

```python
def detect_problem_areas():
    """
    Analyze recent lookups to identify ZIPs with high SERP disagreement.
    """
    # Get all lookups with SERP verification from past 30 days
    lookups = get_recent_verified_lookups(days=30)
    
    # Group by ZIP
    zip_results = {}
    for lookup in lookups:
        zip_code = lookup['zip_code']
        if zip_code not in zip_results:
            zip_results[zip_code] = {'total': 0, 'serp_disagreed': 0}
        
        zip_results[zip_code]['total'] += 1
        if lookup.get('serp_contradicted'):
            zip_results[zip_code]['serp_disagreed'] += 1
    
    # Flag ZIPs with >20% disagreement rate (minimum 5 samples)
    problem_zips = []
    for zip_code, data in zip_results.items():
        if data['total'] >= 5:
            disagreement_rate = data['serp_disagreed'] / data['total']
            if disagreement_rate > 0.20:
                problem_zips.append({
                    'zip': zip_code,
                    'disagreement_rate': disagreement_rate,
                    'sample_size': data['total']
                })
    
    # Add to problem_areas.json
    for pz in problem_zips:
        add_to_problem_areas(pz['zip'], f"High SERP disagreement ({pz['disagreement_rate']:.0%})")
    
    return problem_zips
```

### Task 9.3: Scheduled Jobs

Set up Railway cron jobs:

```
# Weekly accuracy validation (Sunday 2am)
0 2 * * 0 python scripts/accuracy_monitor.py

# Daily missing cities check (6am)
0 6 * * * python scripts/check_missing_cities.py

# Monthly problem area detection (1st of month)
0 3 1 * * python scripts/detect_problem_areas.py
```

---

## File Structure Summary

After all phases, the data directory should look like:

```
/data/
  /municipal_utilities/
    electric_munis.json          # APPA municipal electric utilities
  
  /electric_cooperatives/
    cooperatives.json            # NRECA co-op data
    supplemental.json            # Gaps not in HIFLD
  
  /electric_puds/
    washington.json              # WA PUDs
  
  /gas_mappings/
    texas.json                   # Already done
    california.json
    illinois.json
    ohio.json
    georgia.json
    arizona.json
  
  /special_districts/
    /texas/
      muds.json                  # Already done
      zip_to_district.json
    /florida/
      cdds.json                  # Already done
      zip_to_district.json
    /colorado/
      metro_districts.json
      zip_to_district.json
    /california/
      los_angeles.json
      san_diego.json
      orange.json
      # ... etc by county
    /arizona/
      maricopa.json
      pima.json
  
  /water_utilities_supplemental.json  # Manual city additions
  
  /problem_areas.json                 # Known data quality issues
  
  /reports/
    accuracy_2026_01_11.json
    accuracy_2026_01_18.json
    # ... weekly reports
```

---

## Testing Checklist

After each phase, verify with test addresses:

### Phase 1 (Municipal Utilities)
```bash
# Austin Energy
curl "API_URL?address=1100+Congress+Ave+Austin+TX"
# Expected: Austin Energy (electric), Austin Water (water)

# LA DWP
curl "API_URL?address=200+N+Spring+St+Los+Angeles+CA"
# Expected: LADWP (electric and water)
```

### Phase 2 (Colorado)
```bash
# Highlands Ranch
curl "API_URL?address=9500+Highlands+Ranch+Pkwy+Highlands+Ranch+CO"
# Expected: Highlands Ranch Metro District (water)

# Castle Rock
curl "API_URL?address=100+N+Wilcox+St+Castle+Rock+CO"
# Expected: Castle Rock Water
```

### Phase 3 (Gas Mapping)
```bash
# Los Angeles (SoCalGas)
curl "API_URL?address=200+N+Spring+St+Los+Angeles+CA"
# Expected: Southern California Gas Company

# San Francisco (PG&E)
curl "API_URL?address=1+Dr+Carlton+B+Goodlett+Pl+San+Francisco+CA"
# Expected: Pacific Gas and Electric
```

---

## Priority Order

| Phase | Tasks | Effort | Impact | Do First |
|-------|-------|--------|--------|----------|
| 1 | Municipal utilities | Medium | High | Yes |
| 2 | Colorado metro districts | Medium | High (CO) | Yes |
| 3 | State gas mappings (CA, IL) | Medium | Medium | Yes |
| 4 | Electric co-op verification | Low | Medium | Yes |
| 5 | Water supplemental expansion | Ongoing | High | Yes |
| 6 | California special districts | High | Medium (CA) | Later |
| 7 | Arizona districts | Medium | Medium (AZ) | Later |
| 8 | Washington PUDs | Low | Medium (WA) | Later |
| 9 | Accuracy monitoring | Medium | High | Yes |

**Recommended order:** 1 → 9 → 5 → 2 → 3 → 4 → 6 → 7 → 8

---

## PHASE 10: Cost Optimization (Skip SERP When Authoritative)

Once data quality is high, skip the ~$0.01 SERP verification for authoritative matches.

### Current Cost Breakdown

| Component | Cost | When Used |
|-----------|------|-----------|
| Geocoding | $0 | Every lookup |
| Electric/Gas/Water DB | $0 | Every lookup |
| FCC Broadband | ~$0.01 | Every lookup with internet |
| SERP Verification | ~$0.01 | Every lookup (currently) |
| **Total** | **~$0.02** | |

### Optimization Goal

Skip SERP when we have authoritative data. Target: 60-70% of lookups skip SERP.

| Scenario | Current Cost | Optimized Cost |
|----------|--------------|----------------|
| 1,000 lookups | $20 | $8-12 |
| 10,000 lookups | $200 | $80-120 |

### Authoritative Sources (No SERP Needed)

These sources are definitive. If we get a match, skip SERP:

| Source | Utility Type | Why Authoritative |
|--------|--------------|-------------------|
| Special district boundary match | Water | Legal boundaries, address is inside polygon |
| Municipal utility (city match) | Electric, Water | City runs utility, address in city limits |
| Electric cooperative polygon | Electric | HIFLD boundaries are surveyed |
| User confirmed (3+ votes) | All | Crowdsourced verification |
| ZIP override table | All | Manual correction, already verified |
| State regulatory data | Gas | PUC/Railroad Commission territories |

### Non-Authoritative Sources (Still Need SERP)

| Source | Why SERP Still Needed |
|--------|----------------------|
| EIA 861 ZIP mapping | ZIP boundaries don't match utility boundaries |
| HIFLD IOU polygons | Less accurate than co-op polygons |
| EPA SDWIS | Database gaps, naming inconsistencies |
| 3-digit ZIP gas mapping | Boundary zones between utilities |
| Heuristic city match | Guessing, not verified |

### Implementation

```python
# utility_lookup.py

def should_skip_serp(result, utility_type):
    """
    Determine if SERP verification can be skipped based on source authority.
    Returns (skip: bool, reason: str)
    """
    source = result.get('source', '')
    confidence_score = result.get('confidence_score', 0)
    
    # Always skip SERP for these authoritative sources
    AUTHORITATIVE_SOURCES = {
        'special_district_boundary',
        'municipal_utility_database', 
        'user_confirmed',
        'zip_override',
        'electric_cooperative_polygon',
        'texas_railroad_commission',  # Gas territories
        'state_puc_territory',
    }
    
    if source in AUTHORITATIVE_SOURCES:
        return True, f"Authoritative source: {source}"
    
    # Skip if confidence already very high from multiple agreeing sources
    if confidence_score >= 90:
        return True, f"High confidence: {confidence_score}"
    
    # Skip if in a known-good area (opposite of problem area)
    if is_verified_area(result.get('zip_code')):
        return True, "Verified area"
    
    # Don't skip for these
    ALWAYS_VERIFY_SOURCES = {
        'eia_861',
        'hifld_iou_polygon',
        'epa_sdwis',
        'heuristic_city_match',
        'supplemental_file',  # Until it's been SERP-verified once
    }
    
    if source in ALWAYS_VERIFY_SOURCES:
        return False, f"Non-authoritative source: {source}"
    
    # Don't skip in problem areas
    if is_problem_area(result.get('zip_code')):
        return False, "Problem area"
    
    # Default: verify
    return False, "Default behavior"


def lookup_with_smart_verification(address, utilities=['electric', 'gas', 'water', 'internet']):
    """
    Main lookup function with conditional SERP verification.
    """
    # Step 1: Geocode
    location = geocode(address)
    
    # Step 2: Get results from all data sources
    results = {}
    serp_skipped = {}
    
    for utility_type in utilities:
        if utility_type == 'internet':
            # Internet is always authoritative (FCC)
            results['internet'] = lookup_internet(location)
            serp_skipped['internet'] = True
            continue
        
        # Get initial result from databases
        result = lookup_utility_from_databases(utility_type, location)
        
        # Decide if SERP is needed
        skip, reason = should_skip_serp(result, utility_type)
        
        if skip:
            # Mark as verified without SERP
            result['verification_method'] = 'authoritative_source'
            result['serp_skipped'] = True
            result['skip_reason'] = reason
            serp_skipped[utility_type] = True
        else:
            # Run SERP verification
            serp_result = verify_with_serp(utility_type, location, result)
            result = merge_with_serp(result, serp_result)
            result['verification_method'] = 'serp_verified'
            result['serp_skipped'] = False
            serp_skipped[utility_type] = False
        
        results[utility_type] = result
    
    # Add cost tracking
    serp_calls = sum(1 for v in serp_skipped.values() if not v)
    estimated_cost = 0.01 * serp_calls  # Only count SERP calls
    
    return {
        'location': location,
        'utilities': results,
        'meta': {
            'serp_calls': serp_calls,
            'serp_skipped': serp_skipped,
            'estimated_cost': estimated_cost
        }
    }
```

### Graduated Trust System

Build trust in sources over time:

```python
# Track source accuracy over time
SOURCE_TRUST_SCORES = {
    'special_district_boundary': 0.98,  # Very high
    'municipal_utility_database': 0.95,
    'user_confirmed': 0.95,
    'electric_cooperative_polygon': 0.93,
    'zip_override': 0.99,  # Manual corrections
    'eia_861': 0.82,  # ZIP-level, boundary issues
    'supplemental_file': 0.85,  # Good but not verified
    'heuristic_city_match': 0.60,  # Guessing
}

def update_trust_scores():
    """
    Run monthly. Compares source results to SERP ground truth.
    Adjusts trust scores based on actual accuracy.
    """
    for source in SOURCE_TRUST_SCORES:
        # Get all lookups where this source was used
        lookups = get_lookups_by_source(source, days=30)
        
        # Calculate accuracy vs SERP
        if len(lookups) >= 50:
            correct = sum(1 for l in lookups if l['serp_agreed'])
            accuracy = correct / len(lookups)
            
            # Update trust score (weighted average with prior)
            prior = SOURCE_TRUST_SCORES[source]
            SOURCE_TRUST_SCORES[source] = (prior * 0.7) + (accuracy * 0.3)
    
    save_trust_scores(SOURCE_TRUST_SCORES)
```

### Skip Logic by Utility Type

| Utility | Skip SERP When |
|---------|----------------|
| Electric | Co-op polygon match, municipal utility, user confirmed, ZIP override |
| Gas | State LDC territory match, user confirmed, ZIP override |
| Water | Special district match, municipal utility, user confirmed |
| Internet | Always skip (FCC is authoritative) |

### Verified Areas Registry

Track ZIPs where our data has been validated:

```json
// /data/verified_areas.json
{
  "78701": {
    "verified_date": "2026-01-10",
    "sample_size": 25,
    "accuracy": 0.96,
    "sources_validated": ["municipal_utility_database"]
  },
  "80126": {
    "verified_date": "2026-01-08", 
    "sample_size": 15,
    "accuracy": 0.93,
    "sources_validated": ["special_district_boundary"]
  }
}
```

A ZIP becomes "verified" when:
- 10+ lookups with SERP verification
- 90%+ agreement between database and SERP
- No user corrections submitted in past 30 days

### Fallback: Spot-Check Mode

Even for authoritative sources, randomly verify 5% of lookups to catch drift:

```python
import random

def should_spot_check():
    """5% of authoritative matches still get SERP verified."""
    return random.random() < 0.05

def lookup_with_spot_check(result, utility_type, location):
    skip, reason = should_skip_serp(result, utility_type)
    
    if skip and should_spot_check():
        # Spot check - verify anyway, but async (don't slow down response)
        queue_async_verification(result, utility_type, location)
        result['spot_checked'] = True
    
    return result
```

### API Response Changes

Add transparency about verification method:

```json
{
  "utilities": {
    "electric": {
      "name": "Austin Energy",
      "confidence_score": 95,
      "source": "municipal_utility_database",
      "verification": {
        "method": "authoritative_source",
        "serp_skipped": true,
        "reason": "Municipal utility database match"
      }
    },
    "water": {
      "name": "Travis County MUD 4",
      "confidence_score": 92,
      "source": "special_district_boundary",
      "verification": {
        "method": "authoritative_source", 
        "serp_skipped": true,
        "reason": "Special district boundary match"
      }
    }
  },
  "meta": {
    "serp_calls": 0,
    "estimated_cost": 0.00
  }
}
```

### Expected Impact

| Metric | Before | After |
|--------|--------|-------|
| SERP calls per lookup | 3 (elec + gas + water) | 0.5-1.0 avg |
| Cost per lookup | $0.02 | $0.005-0.01 |
| Latency | 2-3 sec | 0.5-1 sec (no SERP) |
| Accuracy | ~90% | ~90% (maintained) |

### Implementation Order

1. **Add `should_skip_serp()` function** with initial authoritative sources list
2. **Track SERP skip rate** in logs/analytics
3. **Build verified areas registry** from historical data
4. **Implement spot-check mode** (5% random verification)
5. **Add trust score tracking** and monthly updates
6. **Tune skip thresholds** based on actual accuracy data

### Monitoring

Track these metrics to ensure accuracy doesn't degrade:

```python
# Dashboard metrics
{
  "serp_skip_rate": 0.65,  # 65% of lookups skip SERP
  "accuracy_with_serp": 0.91,
  "accuracy_without_serp": 0.89,  # Should be close
  "cost_per_1000_lookups": 8.50,
  "avg_latency_with_serp": 2.4,
  "avg_latency_without_serp": 0.6
}
```

Alert if `accuracy_without_serp` drops more than 3% below `accuracy_with_serp`.

---

## PHASE 11: Maximalist Accuracy (Every Corner of Every State)

Go beyond "good enough" to definitively correct for every US address.

### 11.1: Parcel-Level Data (County Assessor Records)

County assessor databases often contain utility account information at the parcel level. This is the gold standard.

**Why it's better:**
- Parcel boundaries are exact (not ZIP approximations)
- Many counties track which utilities serve each parcel
- Updated when properties change hands or utilities change

**Challenge:** 3,143 counties, each with different data formats and access methods.

**Implementation approach:**

```
Priority counties (by SFR rental density):
1. Maricopa County, AZ (Phoenix) - https://mcassessor.maricopa.gov/
2. Harris County, TX (Houston) - https://hcad.org/
3. Los Angeles County, CA - https://assessor.lacounty.gov/
4. Clark County, NV (Las Vegas) - https://www.clarkcountynv.gov/assessor/
5. Tarrant County, TX (Fort Worth) - https://www.tad.org/
6. Bexar County, TX (San Antonio) - https://www.bcad.org/
7. Dallas County, TX - https://www.dallascad.org/
8. Orange County, CA - https://www.ocgov.com/gov/assessor
9. Riverside County, CA - https://www.rivcoassessor.org/
10. San Bernardino County, CA - https://www.sbcounty.gov/assessor/

For each county:
1. Check if assessor data is downloadable or has API
2. Identify fields containing utility info
3. Build parcel-to-utility mapping
4. Cross-reference with address geocoding
```

**Data structure:**

```json
// /data/parcel_data/harris_county_tx.json
{
  "parcels": {
    "0001234567890": {
      "address": "123 Main St, Houston, TX 77001",
      "electric_account": "CenterPoint Energy",
      "water_account": "City of Houston",
      "gas_account": "CenterPoint Energy",
      "last_updated": "2025-12-15"
    }
  }
}
```

### 11.2: Utility Company Address Lookup Tools

Many utilities have "Do we serve your address?" tools on their websites. Query them directly.

**Utilities with address lookup APIs/tools:**

| Utility | Type | URL | Method |
|---------|------|-----|--------|
| Austin Energy | Electric | austinenergy.com/go/service | Form submission |
| PG&E | Electric/Gas | pge.com/en/account/service | Address lookup |
| Duke Energy | Electric | duke-energy.com | Service area checker |
| Dominion Energy | Electric/Gas | dominionenergy.com | Address validation |
| Xcel Energy | Electric/Gas | xcelenergy.com | Service territory |
| LADWP | Electric/Water | ladwp.com | Service area map |
| SoCalGas | Gas | socalgas.com | Service lookup |

**Implementation:**

```python
# utility_direct_lookup.py

UTILITY_LOOKUP_ENDPOINTS = {
    'austin_energy': {
        'url': 'https://austinenergy.com/api/service-area',
        'method': 'POST',
        'params': lambda addr: {'address': addr},
        'parse': lambda r: r.json().get('serves_address', False)
    },
    'pge': {
        'url': 'https://pge.com/api/address-check',
        'method': 'GET',
        'params': lambda addr: {'street': addr},
        'parse': lambda r: 'PG&E' if r.json().get('in_territory') else None
    }
}

async def check_utility_direct(utility_key, address):
    """Query utility company directly to confirm service."""
    config = UTILITY_LOOKUP_ENDPOINTS.get(utility_key)
    if not config:
        return None
    
    try:
        response = await http_client.request(
            config['method'],
            config['url'],
            params=config['params'](address)
        )
        return config['parse'](response)
    except Exception:
        return None  # Fall back to other methods

def verify_with_utility_direct(address, suspected_utility):
    """
    If we think the utility is X, ask X directly if they serve this address.
    """
    utility_key = UTILITY_KEY_MAP.get(suspected_utility)
    if utility_key:
        confirmed = check_utility_direct(utility_key, address)
        if confirmed:
            return {
                'confirmed': True,
                'source': 'utility_direct_api',
                'confidence_boost': 30
            }
        elif confirmed is False:
            return {
                'confirmed': False,
                'source': 'utility_direct_api',
                'confidence_penalty': -40  # They said no!
            }
    return None
```

**Build out for top 50 utilities by customer count.**

### 11.3: State PUC Service Territory Maps

Every state Public Utility Commission has official service territory maps. Digitize them.

**Data sources by state:**

| State | Agency | Data Quality |
|-------|--------|--------------|
| Texas | PUCT + Railroad Commission | Good, partially digitized |
| California | CPUC | PDFs, needs digitization |
| Florida | PSC | GIS available |
| New York | PSC | GIS available |
| Pennsylvania | PUC | PDFs |
| Ohio | PUCO | GIS available |
| Illinois | ICC | Mixed |
| Georgia | PSC | GIS available |

**Implementation:**

```
For each state:
1. Find PUC service territory data
2. If GIS format: ingest directly
3. If PDF maps: use AI to digitize boundaries
4. Create state_puc_territories/{state}.geojson
5. Add point-in-polygon lookup
```

### 11.4: Enhanced Geocoding (Multi-Source Consensus)

Census geocoder is free but not always accurate. Use multiple sources.

**Geocoding sources:**

| Source | Cost | Accuracy | Speed |
|--------|------|----------|-------|
| US Census | Free | Good | Fast |
| Google Maps | $5/1000 | Excellent | Fast |
| Smarty (SmartyStreets) | $0.01/lookup | Excellent | Fast |
| HERE | $0.01/lookup | Very Good | Fast |
| Mapbox | $0.50/1000 | Very Good | Fast |

**Multi-geocoder approach:**

```python
# geocoding.py

async def geocode_consensus(address):
    """
    Query multiple geocoders, use consensus for accuracy.
    """
    results = await asyncio.gather(
        geocode_census(address),
        geocode_google(address),  # If budget allows
        geocode_smarty(address),
        return_exceptions=True
    )
    
    valid_results = [r for r in results if not isinstance(r, Exception)]
    
    if len(valid_results) == 0:
        raise GeocodingError("All geocoders failed")
    
    if len(valid_results) == 1:
        return valid_results[0]
    
    # Check for consensus (within 100 meters)
    lat_avg = sum(r['lat'] for r in valid_results) / len(valid_results)
    lon_avg = sum(r['lon'] for r in valid_results) / len(valid_results)
    
    # Check if all results are close to average
    all_close = all(
        haversine_distance(r['lat'], r['lon'], lat_avg, lon_avg) < 100
        for r in valid_results
    )
    
    if all_close:
        # Consensus reached, use average
        return {
            'lat': lat_avg,
            'lon': lon_avg,
            'confidence': 'high',
            'method': 'multi_geocoder_consensus',
            'sources': len(valid_results)
        }
    else:
        # Disagreement - flag for review, use Google if available
        google_result = next((r for r in valid_results if r.get('source') == 'google'), None)
        return google_result or valid_results[0]
```

### 11.5: Address Normalization (USPS CASS)

Standardize addresses before lookup to avoid mismatches.

**Why it matters:**
- "123 Main Street" vs "123 Main St" vs "123 Main St."
- "Apt 4" vs "#4" vs "Unit 4"
- Directionals: "N Main St" vs "North Main Street"

**Implementation:**

```python
# Use Smarty or similar for CASS-certified normalization
def normalize_address(raw_address):
    """
    Normalize address to USPS standard format.
    """
    response = smarty_client.verify(raw_address)
    
    if response.is_valid:
        return {
            'normalized': response.delivery_line_1,
            'city': response.city_name,
            'state': response.state_abbreviation,
            'zip': response.zipcode,
            'zip4': response.plus4_code,
            'dpv_match': response.dpv_match_code,  # Deliverable?
            'latitude': response.metadata.latitude,
            'longitude': response.metadata.longitude
        }
    else:
        return {'normalized': raw_address, 'validation_failed': True}
```

### 11.6: New Construction / Builder Data

New developments often aren't in databases yet. Track them proactively.

**Data sources:**

| Source | What It Provides |
|--------|------------------|
| Building permit databases | New construction before occupancy |
| Builder websites | Subdivision utility assignments |
| Title company data | Utility commitments at closing |
| HOA registrations | Master-planned community utilities |

**Implementation:**

```python
# For new construction addresses that fail lookup:

def handle_new_construction(address, geocode_result):
    """
    Special handling for addresses not in standard databases.
    """
    # Check if in known new development
    subdivision = lookup_subdivision(geocode_result)
    if subdivision:
        return {
            'electric': subdivision.get('electric_provider'),
            'water': subdivision.get('water_provider'),
            'gas': subdivision.get('gas_provider'),
            'source': 'subdivision_master_data',
            'note': f"Part of {subdivision['name']} development"
        }
    
    # Check building permit database
    permit = lookup_building_permit(address)
    if permit and permit.get('utility_connections'):
        return {
            'source': 'building_permit',
            'utilities': permit['utility_connections']
        }
    
    # Fall back to SERP with "new construction" context
    return verify_with_serp(address, context="new construction")
```

**Track major builders:**
- D.R. Horton
- Lennar
- PulteGroup
- NVR (Ryan Homes)
- Meritage Homes
- Taylor Morrison
- KB Home

Many publish utility info for their communities.

### 11.7: Bulk Verification Partnerships

Partner with companies that have ground-truth data.

**Potential partners:**

| Partner Type | Data They Have | Value |
|--------------|----------------|-------|
| Property management software | Utility accounts for millions of units | Direct verification |
| Title companies | Utility info at closing | Historical + current |
| Utility billing aggregators | Actual utility relationships | Ground truth |
| Real estate data providers | Property utility fields | Bulk data |

**AppFolio/Buildium integration concept:**

```python
# When a PM connects their AppFolio account:

def ingest_pm_portfolio(pm_account):
    """
    Ingest property data from PM software.
    Verify against our data, flag mismatches.
    """
    properties = pm_account.get_properties()
    
    for prop in properties:
        our_result = lookup_utilities(prop.address)
        
        # Compare to what PM has on file
        if prop.electric_provider:
            if prop.electric_provider != our_result['electric']['name']:
                log_mismatch('electric', prop.address, 
                           our_result['electric']['name'], 
                           prop.electric_provider)
                # PM data is ground truth - add as user confirmation
                submit_correction(
                    address=prop.address,
                    utility_type='electric',
                    correct_provider=prop.electric_provider,
                    source='pm_portfolio_import',
                    confidence='high'
                )
```

### 11.8: Utility Bill OCR

Users upload utility bills = 100% accuracy for that address.

**Implementation:**

```python
# bill_ocr.py

def extract_utility_info_from_bill(image_or_pdf):
    """
    Extract utility provider and service address from bill.
    """
    # Use Claude vision or Google Document AI
    extracted = ocr_service.extract(image_or_pdf, fields=[
        'utility_company_name',
        'service_address',
        'account_number',
        'service_type'  # electric, gas, water
    ])
    
    if extracted.confidence > 0.9:
        # Add to verified data
        add_verified_utility(
            address=extracted.service_address,
            utility_type=extracted.service_type,
            provider=extracted.utility_company_name,
            source='utility_bill_ocr',
            confidence_score=98
        )
    
    return extracted
```

**UI flow:**
1. User does lookup, sees result
2. "Have a utility bill? Upload it to verify" option
3. User uploads bill
4. We extract and verify
5. Data improves for everyone

### 11.9: Reverse Lookup (Phone/Website → Service Area)

Build database of utility contact info, then match.

**Approach:**

```
1. Compile list of all US utilities (electric, gas, water)
   - ~3,000 electric utilities
   - ~1,500 gas utilities  
   - ~50,000+ water systems

2. For each utility, collect:
   - Official name and variations
   - Phone numbers (customer service, emergency)
   - Website URL
   - Service area description
   - Cities/counties served

3. Use this for:
   - Matching SERP results to known utilities
   - Validating user corrections
   - Filling in contact info
```

**Data structure:**

```json
// /data/utility_directory/master.json
{
  "utilities": [
    {
      "id": "util_001",
      "name": "Austin Energy",
      "aliases": ["City of Austin Electric", "COA Electric"],
      "type": "electric",
      "ownership": "municipal",
      "phone": {
        "customer_service": "512-494-9400",
        "outage": "512-322-9100"
      },
      "website": "https://austinenergy.com",
      "service_area": {
        "type": "municipal",
        "cities": ["Austin"],
        "counties": ["Travis", "Williamson"],
        "state": "TX"
      },
      "customers": 500000
    }
  ]
}
```

### 11.10: Real-Time Utility API Aggregation

Some utilities expose APIs or data feeds. Tap into them.

**Known utility APIs:**

| Utility | API Type | Data Available |
|---------|----------|----------------|
| Green Button | Standard | Usage data, account info |
| PG&E Share My Data | OAuth | Service status |
| ComEd | API | Outage data, service area |
| Austin Energy | GIS | Service territory |

**Implementation:**

```python
# For utilities with public GIS services:

UTILITY_GIS_SERVICES = {
    'austin_energy': {
        'type': 'arcgis',
        'url': 'https://services.arcgis.com/.../AustinEnergy/FeatureServer/0',
        'query_type': 'point_in_polygon'
    },
    'ladwp': {
        'type': 'arcgis', 
        'url': 'https://services.arcgis.com/.../LADWP_ServiceArea/FeatureServer/0',
        'query_type': 'point_in_polygon'
    }
}

async def check_utility_gis(utility_key, lat, lon):
    """Query utility's own GIS service."""
    config = UTILITY_GIS_SERVICES.get(utility_key)
    if not config:
        return None
    
    # ArcGIS point-in-polygon query
    query = {
        'geometry': f'{lon},{lat}',
        'geometryType': 'esriGeometryPoint',
        'spatialRel': 'esriSpatialRelIntersects',
        'returnGeometry': 'false',
        'f': 'json'
    }
    
    response = await http_client.get(f"{config['url']}/query", params=query)
    features = response.json().get('features', [])
    
    return len(features) > 0  # True if point is in service area
```

### 11.11: Boundary Edge Case Handling

Special logic for addresses near utility boundaries.

**Problem:**
- Utilities have boundaries
- Addresses near boundaries can be misclassified
- Same street might have different utilities on each side

**Solution:**

```python
def is_near_boundary(lat, lon, utility_polygon):
    """Check if point is within 200m of polygon boundary."""
    point = Point(lon, lat)
    boundary = utility_polygon.boundary
    distance = point.distance(boundary)
    return distance < 0.002  # ~200 meters

def handle_boundary_address(address, lat, lon, candidates):
    """
    Special handling for addresses near utility boundaries.
    """
    near_boundary = any(
        is_near_boundary(lat, lon, c['polygon']) 
        for c in candidates if c.get('polygon')
    )
    
    if near_boundary:
        # Flag as boundary case
        # Run extra verification
        # Reduce confidence
        # Add note to response
        return {
            'boundary_case': True,
            'confidence_adjustment': -15,
            'note': 'Address is near utility service boundary. Verification recommended.',
            'verification_sources': ['serp', 'utility_direct']  # Always verify these
        }
    
    return {'boundary_case': False}
```

### 11.12: Historical Change Tracking

Utility territories change. Track them over time.

**Implementation:**

```python
# /data/territory_changes/log.json
{
  "changes": [
    {
      "date": "2025-06-15",
      "type": "annexation",
      "utility": "Austin Energy",
      "description": "Annexed portions of Travis County",
      "affected_zips": ["78653", "78660"],
      "source": "Austin City Council Resolution"
    },
    {
      "date": "2025-03-01",
      "type": "new_district",
      "utility": "Blackhawk MUD",
      "description": "New MUD created in Hays County",
      "affected_area": "Polygon...",
      "source": "TCEQ"
    }
  ]
}
```

**Monitor for changes:**
- State PUC announcements
- Municipal annexation notices
- New special district formations
- Utility merger/acquisition news

### Summary: Maximalist Data Stack

```
TIER 1: Authoritative (Skip SERP)
├── Special district boundaries (TX, FL, CO, CA, etc.)
├── Municipal utility database
├── Electric cooperative polygons
├── User confirmed (3+ votes)
├── ZIP overrides (manual corrections)
├── Utility direct API confirmation
└── Parcel-level data (where available)

TIER 2: High Quality (Spot-check SERP)
├── State PUC territory maps
├── County assessor data
├── EIA 861 with boundary refinement
├── Builder/subdivision data
└── PM portfolio imports

TIER 3: Needs Verification (Always SERP)
├── EPA SDWIS
├── HIFLD IOU polygons
├── Heuristic matches
└── New construction guesses

TIER 4: Ground Truth Collection
├── Utility bill OCR
├── User feedback system
├── PM software integrations
└── Title company partnerships
```

### Target Accuracy by Phase

| Phase | Electric | Gas | Water | Notes |
|-------|----------|-----|-------|-------|
| Current | 90% | 85% | 75% | Baseline |
| After Phase 1-5 | 93% | 88% | 82% | Core improvements |
| After Phase 6-9 | 95% | 90% | 85% | State expansions |
| After Phase 10 | 95% | 90% | 85% | Cost optimized |
| After Phase 11 | 98% | 95% | 92% | Maximalist |

### Implementation Priority for Phase 11

| Task | Effort | Impact | Priority |
|------|--------|--------|----------|
| 11.5 Address normalization | Low | High | Do first |
| 11.9 Utility directory | Medium | High | Do second |
| 11.4 Multi-geocoder | Low | Medium | Do third |
| 11.2 Utility direct APIs | High | High | Incremental |
| 11.7 PM partnerships | Medium | Very High | Strategic |
| 11.1 Parcel data | Very High | Very High | County by county |
| 11.3 State PUC maps | High | High | State by state |
| 11.8 Bill OCR | Medium | Medium | Nice to have |
| 11.6 Builder data | Medium | Medium | For new construction |
| 11.10 Utility GIS APIs | Medium | Medium | Where available |
| 11.11 Boundary handling | Low | Medium | After polygons done |
| 11.12 Change tracking | Low | Low | Maintenance mode |
