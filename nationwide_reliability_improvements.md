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
