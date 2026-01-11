# Utility Provider Verification Guide

## Overview

The Utility Profit lookup system identifies and verifies utility providers for any US address across four categories: **Electric**, **Gas**, **Water**, and **Internet**. Each uses different data sources and verification methods.

---

## Cost Summary

| Utility Type | Data Source | Cost per Lookup | Notes |
|-------------|-------------|-----------------|-------|
| **Electric** | HIFLD + EIA + State data | **$0** | All free government APIs |
| **Gas** | HIFLD + State LDC database | **$0** | All free government APIs |
| **Water** | EPA SDWIS | **$0** | Free government API |
| **Internet** | FCC Broadband Map | **$0** | Free, but slow (~10s/lookup) |
| **Geocoding** | Census Geocoder | **$0** | Free government API |

### Total Cost: **$0 per lookup**

All data sources are free government APIs. The only costs are:
- **Server hosting** (Railway): ~$5-20/month depending on usage
- **Optional SERP verification** (if enabled): ~$0.01/lookup via BrightData proxy

---

## Electric Utility Verification

### How It Works

1. **Geocode the address** → Get coordinates (lat/lon), city, county, state, ZIP
2. **Query HIFLD** → Get all electric utility territories that contain this point
3. **Verify with authoritative data**:
   - **Texas**: ZIP-to-TDU mapping (Oncor, CenterPoint, AEP, TNMP)
   - **Other states**: EIA Form 861 ZIP-to-utility mapping (31,000+ ZIPs)
   - **Fallback**: Ranking heuristics based on utility type and name matching

### Data Sources

| Source | Coverage | Confidence |
|--------|----------|------------|
| **Texas TDU Mapping** | TX only (5 TDUs + municipals) | Verified ✓ |
| **EIA Form 861** | 31,633 ZIPs, 143 IOUs nationwide | Verified ✓ |
| **HIFLD Electric Territories** | National polygon data | High/Medium |
| **State LDC Database** | All 50 states | Medium (fallback) |

### Confidence Levels

- **Verified**: Matched authoritative state/federal data (Texas TDU, EIA)
- **High**: Single provider or strong heuristic match
- **Medium**: Multiple candidates, best guess based on ranking
- **Low**: Uncertain, recommend manual verification

### Texas-Specific Logic

Texas is deregulated with 5 TDUs (Transmission & Distribution Utilities):

| ZIP Prefix | TDU | Service Area |
|------------|-----|--------------|
| 750-769 | Oncor | Dallas/Fort Worth |
| 770-779 | CenterPoint | Houston |
| 786-789 | Oncor | Austin area (parts) |
| 793-796 | AEP North | Lubbock/Abilene |
| 783-785 | AEP Central | Corpus Christi, South TX |

Municipal utilities (Austin Energy, CPS Energy, etc.) are identified by city name and marked as "not in deregulated market."

---

## Gas Utility Verification

### How It Works

1. **Query HIFLD Gas Territories** → Get LDC (Local Distribution Company) candidates
2. **Verify with state-specific data**:
   - **Texas**: ZIP-to-LDC mapping (Atmos, CenterPoint, Texas Gas Service)
   - **Other states**: Match against known state LDCs database
3. **Handle no-service cases** → Return "No natural gas service" for propane/all-electric areas

### Data Sources

| Source | Coverage | Confidence |
|--------|----------|------------|
| **Texas Gas Mapping** | TX only (3 major LDCs) | Verified ✓ |
| **State LDC Database** | All 50 states + DC | High |
| **HIFLD Gas Territories** | National polygon data | Medium |

### Texas Gas LDCs

| ZIP Prefix | Gas LDC | Service Area |
|------------|---------|--------------|
| 750-769, 790-796 | Atmos Energy | DFW, West TX |
| 770-779 | CenterPoint Energy | Houston |
| 786-789, 798-799 | Texas Gas Service | Austin, El Paso |

### No-Service Detection

States with limited gas infrastructure are flagged:
- **Florida**: Very limited outside urban areas
- **Hawaii**: Limited (mostly Oahu)
- **Vermont**: Limited (Burlington area)
- **Maine**: Limited (expanding)

---

## Water Utility Verification

### How It Works

1. **Query EPA SDWIS** → Search by city and county name
2. **Filter results** → Prioritize by population served and name match
3. **Return primary** → Largest water system serving the area

### Data Source

| Source | Coverage | Confidence |
|--------|----------|------------|
| **EPA SDWIS** | All public water systems in US | High |

### Notes

- Water utilities are highly fragmented (thousands of small systems)
- Matching is by city/county name, not precise coordinates
- Large municipal systems are prioritized over small private wells

---

## Internet Provider Verification

### How It Works

1. **Normalize address** → Strip apartment/unit numbers (FCC only accepts building addresses)
2. **Load FCC Broadband Map** → Using Playwright browser automation
3. **Enter address** → Trigger autocomplete and select suggestion
4. **Capture API response** → Intercept the `fabric/detail` API call
5. **Parse providers** → Extract all ISPs with speeds and technology types

### Data Source

| Source | Coverage | Confidence |
|--------|----------|------------|
| **FCC Broadband Map** | All US addresses | Verified ✓ |

### Technical Details

- Uses **Playwright** with Chromium in headed mode (requires virtual display on server)
- Applies **stealth settings** to bypass bot detection
- Takes **~10 seconds per lookup** due to page load and API wait times
- Strips apartment/unit numbers automatically (e.g., "Apt 307" → removed)

### Response Includes

- Provider count
- Fiber availability (yes/no)
- Cable availability (yes/no)
- Best wired option (name, technology, speeds)
- Best wireless option
- Full provider list with download/upload speeds

---

## Geocoding

### How It Works

Address → Coordinates + City + County + State + ZIP

### Data Sources (in order)

1. **US Census Geocoder** (primary) - Free, official
2. **Google Geocoding API** (fallback) - Requires API key
3. **Nominatim/OpenStreetMap** (fallback) - Free, rate-limited

---

## API Response Structure

```json
{
  "address": "1725 Toomey Rd, Austin, TX 78704",
  "location": {
    "city": "Austin",
    "county": "Travis",
    "state": "TX"
  },
  "utilities": {
    "electric": [{
      "name": "AUSTIN ENERGY",
      "phone": "512-494-9400",
      "website": "austinenergy.com",
      "confidence": "verified"
    }],
    "electric_confidence": "verified",
    "electric_note": "✓ Verified: AUSTIN ENERGY. Austin is served by Austin Energy, a municipal utility not in the deregulated ERCOT market.",
    
    "gas": [{
      "name": "Texas Gas Service",
      "phone": "1-800-700-2443"
    }],
    "gas_confidence": "verified",
    "gas_note": "✓ Verified: Texas Gas Service. ZIP 78704 is in Texas Gas Service territory.",
    
    "water": [{
      "name": "CITY OF AUSTIN",
      "phone": "512-972-0000"
    }],
    
    "internet": {
      "provider_count": 8,
      "has_fiber": true,
      "best_wired": {
        "name": "AT&T",
        "technology": "Fiber",
        "max_download_mbps": 5000
      }
    }
  }
}
```

---

## Batch Processing

The `/api/batch` endpoint allows processing up to 100 addresses at once:

- Upload CSV with `address` column
- Or send JSON array of addresses
- Returns all utility data for each address
- Can download results as CSV

---

## Questions?

Contact the development team for technical details or to request additional data sources.
