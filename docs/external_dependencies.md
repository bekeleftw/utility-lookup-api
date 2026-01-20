# External Dependencies Documentation

## Overview

This document lists all external systems and APIs that depend on or are called by the utility lookup system. **Critical for refactoring** - any changes must maintain compatibility with these systems.

---

## Systems That Call This API

### 1. Web Application (Primary)

**Endpoint:** `/api/lookup`

**Request Format:**
```json
{
  "address": "123 Main St, Austin, TX 78701",
  "selected_utilities": ["electric", "gas", "water"]
}
```

**Expected Response Format:**
```json
{
  "electric": {
    "NAME": "Austin Energy",
    "TELEPHONE": "512-494-9400",
    "WEBSITE": "https://austinenergy.com",
    "STATE": "TX",
    "CITY": "Austin",
    "_confidence": "high",
    "_confidence_score": 90,
    "_source": "municipal_utility",
    "_verification_source": "municipal_utility",
    "_selection_reason": "City-owned utility for Austin"
  },
  "gas": {
    "NAME": "Texas Gas Service",
    "TELEPHONE": "800-700-2443",
    "WEBSITE": "https://texasgasservice.com",
    ...
  },
  "water": {
    "NAME": "Austin Water",
    ...
  }
}
```

**SLA Requirements:**
- Response time: < 3 seconds (p95)
- Availability: 99.5%
- Error rate: < 1%

**Critical Fields (MUST NOT CHANGE):**
- `NAME` - Utility provider name
- `TELEPHONE` - Contact phone number
- `WEBSITE` - Provider website URL
- `STATE` - State code
- `CITY` - City name

**Metadata Fields (Can evolve):**
- `_confidence` - Confidence level string
- `_confidence_score` - Numeric confidence (0-100)
- `_source` - Data source identifier
- All fields prefixed with `_` are metadata

---

### 2. Mobile Application (iOS/Android)

**Same as Web Application**

Uses identical endpoint and expects identical response format.

**Additional Considerations:**
- May cache responses locally
- Handles `null` values for utilities not found
- Displays `_confidence` to users

---

### 3. Partner Integrations

#### RealEstate.com API

**Contract Version:** v1.2

**Endpoint Called:** `/api/lookup`

**Special Requirements:**
- Must return `null` (not empty object) when utility not found
- Phone numbers must be formatted consistently
- Website URLs must include protocol (https://)

#### PropertyData.io

**Contract Version:** v1.0

**Batch Endpoint:** `/api/bulk_lookup`

**Rate Limits:**
- 100 requests per minute
- 1000 requests per day

---

## External APIs Called By This System

### 1. Geocoding Services

#### Google Maps Geocoding API

**Used By:** `geocoding.py`

**Purpose:** Convert addresses to lat/lon coordinates

**API Key:** Environment variable `GOOGLE_MAPS_API_KEY`

**Rate Limits:** 50 requests/second

**Fallback:** OpenStreetMap Nominatim (slower, no API key)

---

### 2. State GIS APIs

#### Texas Railroad Commission

**Used By:** `gis_utility_lookup.py`

**Endpoint:** `https://gis.rrc.texas.gov/arcgis/rest/services/`

**Data:** Gas utility service territories

**Rate Limits:** None documented

---

#### California Energy Commission

**Used By:** `gis_utility_lookup.py`

**Endpoint:** `https://cecgis-caenergy.opendata.arcgis.com/`

**Data:** Electric and gas utility territories

---

#### Other State GIS APIs

See `gis_utility_lookup.py` for full list of state-specific GIS endpoints.

**States with GIS APIs:**
- TX, CA, FL, NY, PA, OH, IL, GA, NC, AZ, CO, WA, OR, NV, etc.

---

### 3. Federal Data Sources

#### HIFLD (Homeland Infrastructure Foundation-Level Data)

**Used By:** `utility_lookup.py`, `pipeline/sources/gas.py`

**Data:** Electric and gas utility service area polygons

**Update Frequency:** Quarterly

**Local Cache:** `utility_gis_data/` directory

---

#### EIA Form 861

**Used By:** `pipeline/sources/electric.py`

**Data:** Electric utility service territories by ZIP code

**Local Cache:** `eia_zip_utility_lookup.json`

**Update Frequency:** Annual

---

#### EPA SDWIS (Safe Drinking Water Information System)

**Used By:** `utility_lookup.py`

**Data:** Water utility information

**Local Cache:** `water_utility_lookup.json`

---

### 4. OpenAI API

**Used By:** `pipeline/smart_selector.py`

**Purpose:** Resolve conflicts when multiple sources disagree

**Model:** GPT-4

**API Key:** Environment variable `OPENAI_API_KEY`

**Cost:** ~$0.01-0.02 per lookup (when Smart Selector is invoked)

**Rate Limits:** Depends on account tier

---

## Database Dependencies

### 1. Local JSON Files

**Location:** `data/` directory

**Critical Files:**
- `municipal_utilities.json` - City-owned utility mappings
- `verified_addresses.json` - User-reported corrections
- `county_utility_defaults.json` - County-level fallbacks
- `deregulated_markets.json` - Deregulated state info

**Backup:** Should be version controlled in git

---

### 2. Internet Provider Database

**File:** `bdc_internet_new.db` (SQLite)

**Size:** ~55 GB

**Purpose:** Broadband/internet provider lookups

**Not affected by utility refactor**

---

## Environment Variables Required

```bash
# Required
GOOGLE_MAPS_API_KEY=xxx        # Geocoding
OPENAI_API_KEY=xxx             # Smart Selector

# Optional
SERP_API_KEY=xxx               # Google search verification (disabled)
REDIS_URL=xxx                  # Caching (if enabled)
```

---

## Backward Compatibility Requirements

### Must Maintain

1. **Response Structure:** The top-level keys (`electric`, `gas`, `water`) must remain unchanged
2. **Field Names:** `NAME`, `TELEPHONE`, `WEBSITE`, `STATE`, `CITY` are contractual
3. **Null Handling:** Return `null` for utilities not found, not empty objects
4. **Error Format:** Errors should include `error` key with message

### Can Change

1. **Metadata Fields:** Any field starting with `_` can be added/modified
2. **Internal Implementation:** How results are computed
3. **Confidence Scoring:** Numeric values can be recalibrated
4. **Source Names:** `_source` values can change

---

## Migration Strategy

### Phase 1: Shadow Mode

Run v2 in parallel with v1, compare results, don't serve v2 to users.

### Phase 2: A/B Testing

Route 10% of traffic to v2, monitor for regressions.

### Phase 3: Gradual Rollout

Increase v2 traffic: 10% → 25% → 50% → 100%

### Phase 4: Deprecate v1

After 2 weeks at 100% v2 with no issues, remove v1 code.

---

## Contacts

- **API Support:** [internal contact]
- **Partner Integrations:** [internal contact]
- **Infrastructure:** [internal contact]

---

**Document Version:** 1.0
**Last Updated:** 2026-01-20
**Author:** Refactoring Team
