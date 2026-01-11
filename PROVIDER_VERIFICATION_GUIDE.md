# Utility Provider Verification Guide

## Overview

The Utility Profit lookup system identifies and verifies utility providers for any US address across four categories: **Electric**, **Gas**, **Water**, and **Internet**.

For each lookup, we use a multi-step verification process combining government databases, state-specific authoritative data, and Google Search verification via AI.

---

## Cost Per Lookup: ~$0.02

| Component | Cost | Source |
|-----------|------|--------|
| Geocoding | $0 | US Census Geocoder (free) |
| Electric/Gas database lookup | $0 | HIFLD, EIA, EPA (free government APIs) |
| Internet providers | ~$0.01 | FCC Broadband Map via BrightData |
| Google Search verification | ~$0.01 | BrightData SERP + GPT-4o-mini |
| **Total** | **~$0.02** | |

**Monthly costs:**
- Server hosting (Railway): ~$5-20/month
- BrightData usage: Based on lookup volume

---

## How We Verify Each Provider

### Step 1: Geocode the Address

**What happens:** Convert street address to coordinates + location metadata

**Data source:** US Census Geocoder (free, official government API)

**Output:** Latitude, longitude, city, county, state, ZIP code

---

### Step 2: Electric Utility

**What happens:**

1. **Query HIFLD** - Federal database of electric utility service territories. Returns all utilities whose polygon contains this coordinate. Often returns multiple overlapping territories.

2. **Verify with authoritative state data:**
   - **Texas:** ZIP-to-TDU mapping. Texas has only 5 TDUs (Oncor, CenterPoint, AEP North, AEP Central, TNMP) plus municipal utilities (Austin Energy, CPS Energy, etc.)
   - **Other states:** EIA Form 861 data - maps 31,633 ZIP codes to 143 investor-owned utilities nationwide

3. **Google Search verification (via BrightData):**
   - Search: `"electric utility provider for [full address]"`
   - GPT-4o-mini analyzes the search results
   - Confirms if our database match is correct
   - If Google suggests a different provider, we flag it or swap

**Cost:** ~$0.01 (BrightData SERP + OpenAI)

**Confidence levels:**
- **Verified:** Matched state/federal data AND confirmed by Google
- **High:** Strong database match, Google confirms
- **Medium:** Database match, Google inconclusive
- **Low:** Uncertain, recommend manual verification

---

### Step 3: Gas Utility

**What happens:**

1. **Query HIFLD** - Federal database of natural gas LDC (Local Distribution Company) territories. Returns candidates.

2. **Verify with state data:**
   - **Texas:** ZIP-to-LDC mapping (Atmos Energy for DFW, CenterPoint for Houston, Texas Gas Service for Austin)
   - **Other states:** Match against our database of major gas LDCs for all 50 states

3. **Handle no-service cases:**
   - If HIFLD returns nothing, check if state has limited gas infrastructure (FL, HI, VT, ME)
   - Return "No natural gas service - area likely uses propane"

4. **Google Search verification (via BrightData):**
   - Search: `"natural gas provider for [full address]"`
   - GPT-4o-mini confirms the match

**Cost:** ~$0.01 (BrightData SERP + OpenAI)

---

### Step 4: Water Utility

**What happens:**

1. **Query EPA SDWIS** - Federal database of all public water systems in the US

2. **Filter by location:**
   - Search by city name and county
   - Prioritize by population served (larger systems first)
   - Match utility name to city name when possible

3. **Google Search verification (via BrightData):**
   - Search: `"water utility for [full address]"`
   - GPT-4o-mini confirms the match

**Cost:** ~$0.01 (BrightData SERP + OpenAI)

**Note:** Water utilities are highly fragmented - thousands of small municipal and private systems. Matching is less precise than electric/gas.

---

### Step 5: Internet Providers

**What happens:**

1. **Normalize address** - Strip apartment/unit numbers (FCC only accepts building-level addresses)
   - Example: "1725 Toomey Rd Apt 307" → "1725 Toomey Rd"

2. **Scrape FCC Broadband Map (via BrightData):**
   - Load https://broadbandmap.fcc.gov using Playwright browser automation
   - Enter the normalized address
   - Click autocomplete suggestion
   - Intercept the API response with provider data

3. **Parse results:**
   - Extract all ISPs serving the address
   - Identify fiber/cable availability
   - Find best wired and wireless options
   - Include download/upload speeds for each provider

**Cost:** ~$0.01 (BrightData proxy)

**Technical notes:**
- FCC site has strong anti-bot detection
- Uses Playwright with Chromium in headed mode
- Requires virtual display (Xvfb) on server
- Takes ~10 seconds per lookup

---

## Data Sources Summary

| Utility | Primary Source | Verification |
|---------|---------------|--------------|
| **Electric** | HIFLD territories + EIA Form 861 + Texas TDU mapping | Google Search + GPT-4o-mini |
| **Gas** | HIFLD territories + State LDC database + Texas gas mapping | Google Search + GPT-4o-mini |
| **Water** | EPA SDWIS | Google Search + GPT-4o-mini |
| **Internet** | FCC Broadband Map (scraped via BrightData) | Direct from FCC (authoritative) |

---

## Texas-Specific Data

### Electric TDUs (Transmission & Distribution Utilities)

| ZIP Prefix | TDU | Service Area |
|------------|-----|--------------|
| 750-769 | Oncor | Dallas/Fort Worth, North Texas |
| 770-779 | CenterPoint | Houston metro |
| 786-789 | Oncor | Parts of Austin area |
| 793-796 | AEP North | Lubbock, Abilene |
| 783-785 | AEP Central | Corpus Christi, South Texas |

**Municipal utilities** (not in deregulated market): Austin Energy, CPS Energy (San Antonio), Denton Municipal, Garland Power & Light, etc.

### Gas LDCs

| ZIP Prefix | Gas LDC | Service Area |
|------------|---------|--------------|
| 750-769, 790-796 | Atmos Energy | DFW, West Texas, Panhandle |
| 770-779 | CenterPoint Energy | Houston metro |
| 786-789, 798-799 | Texas Gas Service | Austin, El Paso |

---

## API Usage

### Single Lookup
```
GET /api/lookup?address=1725 Toomey Rd Austin TX 78704
```

### Disable SERP Verification (faster, less accurate)
```
GET /api/lookup?address=...&verify=false
```

### Batch Processing (up to 100 addresses)
```
POST /api/batch
Content-Type: multipart/form-data
file: addresses.csv (must have 'address' column)
```

---

## Response Example

```json
{
  "address": "1725 Toomey Rd, Austin, TX 78704",
  "location": {
    "city": "Austin",
    "county": "Travis",
    "state": "TX"
  },
  "utilities": {
    "electric": [{"name": "AUSTIN ENERGY", "phone": "512-494-9400"}],
    "electric_confidence": "verified",
    "electric_note": "✓ Verified: Austin is served by Austin Energy, a municipal utility.",
    
    "gas": [{"name": "Texas Gas Service", "phone": "1-800-700-2443"}],
    "gas_confidence": "verified",
    "gas_note": "✓ Verified: ZIP 78704 is in Texas Gas Service territory.",
    
    "water": [{"name": "CITY OF AUSTIN", "phone": "512-972-0000"}],
    
    "internet": {
      "provider_count": 8,
      "has_fiber": true,
      "best_wired": {"name": "AT&T", "technology": "Fiber", "max_download_mbps": 5000}
    }
  }
}
```
