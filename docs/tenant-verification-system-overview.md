# Tenant Verification System Overview

## Executive Summary

We've built a system that uses **87,358 tenant-verified utility records** to improve utility lookup accuracy, especially in ZIP codes where multiple utilities serve different areas. The system processes raw tenant data through confidence scoring, geocoding, and geographic boundary analysis to create actionable rules that integrate into our lookup pipeline.

---

## Data Pipeline

### 1. Raw Data
**Source:** `addresses_with_tenant_verification.csv`
- 87,358 addresses with tenant-reported utilities
- Fields: Address, Electricity, Gas, Water, Internet, Trash, Sewer

### 2. Data Processing Modules

#### a) Utility Name Normalizer (`utility_name_normalizer.py`)
Canonicalizes utility names to handle variations:
```
"ComEd" → "Commonwealth Edison (ComEd)"
"PSE&G" → "Public Service Electric and Gas"
"FPL" → "Florida Power & Light"
```
- 150+ alias mappings
- Handles abbreviations, misspellings, regional variations

#### b) Deregulated Market Handler (`deregulated_market_handler.py`)
Distinguishes between:
- **REPs** (Retail Electric Providers): Customer-chosen suppliers (Reliant, TXU, etc.)
- **TDUs** (Transmission/Distribution Utilities): Infrastructure owners (Oncor, CenterPoint)

In deregulated states (TX, PA, OH, etc.), tenant-reported REPs are valid but we need to identify the underlying TDU for infrastructure questions.

#### c) Tenant Confidence Scorer (`tenant_confidence_scorer.py`)
Calculates confidence scores for tenant-reported utilities:
```python
Factors:
- Sample count (more samples = higher confidence)
- Utility type validation (is this a real utility?)
- Street name consistency (do neighbors agree?)
- Geographic clustering (are reports spatially coherent?)

Output:
- confidence: 0.0 - 1.0
- action: "hard_override" | "ai_context" | "ignore"
```

### 3. Generated Data Files

#### a) Hard Overrides (`data/tenant_hard_overrides.json`)
- **145 ZIP codes** with 90%+ confidence
- Used as **Priority 0.5** in lookup (after user corrections, before AI)
- Example:
```json
{
  "78748": {
    "street_patterns": {
      "S 1ST ST": {"utility": "Pedernales Electric", "confidence": 0.95, "samples": 12}
    }
  }
}
```

#### b) AI Context (`data/tenant_ai_context.json`)
- **1,834 ZIP codes** with medium confidence (50-90%)
- Fed to AI Smart Selector as additional context
- Example:
```json
{
  "30252": {
    "utilities": ["Georgia Power", "Snapping Shoals EMC"],
    "is_split_territory": true,
    "context_text": "ZIP 30252 has multiple utilities. Georgia Power: 67%, Snapping Shoals: 33%"
  }
}
```

### 4. Geocoding (`geocode_tenant_addresses.py`)
Geocoded all 87,358 addresses to lat/lon:
- **Census Geocoder** (free, primary): 78,848 (90%)
- **Google Geocoder** (paid, fallback): 8,509 (10%)
- **Failed**: 1

Output: `data/tenant_addresses_geocoded.json`

### 5. Geographic Boundary Analysis (`geographic_boundary_analyzer.py`)
Analyzes geocoded addresses to find lat/lon boundaries where utilities change:

**Results:**
| Utility Type | Multi-Utility ZIPs | Boundaries Found |
|--------------|-------------------|------------------|
| Electric | 3,628 | 129 |
| Gas | 2,239 | 48 |
| Water | 2,506 | 93 |

**Example boundary:**
```json
{
  "zip_code": "78748",
  "boundary": {
    "type": "latitude",
    "boundary_value": 30.1628,
    "north_utility": "Austin Energy",
    "south_utility": "Pedernales Electric Cooperative",
    "confidence": 0.18,
    "description": "North of 30.1628: Austin Energy, South: Pedernales Electric Cooperative"
  }
}
```

---

## Integration into Lookup Pipeline

### Priority Order for Electric Lookup

```
Priority 0:   User-reported corrections (manual overrides)
Priority 0.5: Tenant hard overrides (90%+ confidence street patterns)
Priority 0.6: Geographic boundary (lat/lon based)
Priority 0.6: Nearby consensus (80%+ agreement within 0.25mi)
Priority 1:   AI Smart Selector (with tenant context)
Priority 2:   GIS state APIs
Priority 3:   Municipal utility database
Priority 4:   HIFLD federal dataset
Priority 5:   EIA-861 data
```

### Code Integration Points

#### 1. Hard Override Check (`utility_lookup_v1.py:2236-2257`)
```python
# PRIORITY 0.5: Check tenant-verified hard overrides
from tenant_override_lookup import check_tenant_override_for_address
tenant_override = check_tenant_override_for_address(address, 'electric')
if tenant_override and tenant_override.get('confidence', 0) >= 0.90:
    primary_electric = {
        'NAME': tenant_override['utility'],
        '_confidence': tenant_override['confidence'],
        '_verification_source': tenant_override['source'],
        '_selection_reason': f"Tenant-verified ({tenant_override['sample_count']} samples)"
    }
```

#### 2. Geographic Boundary Check (`utility_lookup_v1.py:2258-2296`)
```python
# PRIORITY 0.6: Check geographic boundary (lat/lon based)
from geographic_boundary_lookup import check_geographic_boundary
geo_result = check_geographic_boundary(zip_code, lat, lon, utility_type='electric')
if geo_result and geo_result.get('confidence', 0) >= 0.15:
    primary_electric = {
        'NAME': geo_result['utility'],
        '_verification_source': 'geographic_boundary',
        '_selection_reason': f"Geographic boundary: {geo_result['description']}"
    }
```

#### 3. Nearby Consensus Check
```python
nearby_result = get_utility_from_nearby_consensus(zip_code, lat, lon)
if nearby_result and nearby_result.get('confidence', 0) >= 0.80:
    # Use consensus of nearby tenant-verified addresses
```

---

## How the AI Uses This Data

### AI Smart Selector (`pipeline/smart_selector.py`)

When multiple data sources conflict, the AI Smart Selector receives a prompt with:

1. **Source Results** (from GIS, HIFLD, municipal DB, etc.)
2. **AI Boundary Insights** (pre-analyzed patterns)
3. **Tenant-Verified Context** (from tenant data)
4. **Geographic Analysis** (from boundary detection)

### Example AI Prompt Context

```
ADDRESS:
123 Main St, Matthews, NC 28104

SOURCE RESULTS:
- state_gis: Duke Energy (confidence: high)
- hifld: Union Power Cooperative (confidence: medium)

AI-ANALYZED BOUNDARY INSIGHT for ZIP 28104:
- Primary utility: Duke Energy
- Secondary utility: Union Power Cooperative
- Boundary: Duke serves southern/central, Union Power serves northern areas
- Confidence: 75%

TENANT-VERIFIED DATA:
ZIP 28104 has multiple utilities: Duke Energy (65%), Union Power (35%)
Note: This ZIP has split utility territories.

GEOGRAPHIC ANALYSIS for ZIP 28104 (electric):
- Tenant-verified utilities: Duke Energy (42 addresses), Union Power Cooperative (23 addresses)
- Geographic boundary detected: North of 35.1099: Union Power Cooperative, South: Duke Energy
- Boundary confidence: 12%
```

### AI Decision Process

The AI is instructed to:

1. **Evaluate source reliability** - GIS is usually authoritative, but tenant data reveals edge cases
2. **Consider geographic position** - If boundary data exists, use lat/lon to determine which side
3. **Weight tenant consensus** - High agreement among nearby tenants is strong signal
4. **Apply domain knowledge** - Municipal utilities serve city limits, co-ops serve rural areas

### AI Output

```json
{
  "selected_utility": "Duke Energy",
  "confidence": 0.85,
  "reasoning": "Address is in southern Matthews (lat 35.08), south of the detected boundary at 35.1099. GIS confirms Duke Energy, and 65% of tenant reports in this ZIP also report Duke Energy."
}
```

---

## File Structure

```
/Utility Provider scrape/
├── utility_name_normalizer.py      # Canonical name mapping
├── deregulated_market_handler.py   # REP vs TDU handling
├── tenant_confidence_scorer.py     # Confidence calculation
├── generate_tenant_rules.py        # Generate override/context files
├── tenant_override_lookup.py       # API for checking overrides
├── geocode_tenant_addresses.py     # Batch geocoding
├── geographic_boundary_analyzer.py # Lat/lon boundary detection
├── geographic_boundary_lookup.py   # API for boundary checks
├── utility_lookup_v1.py            # Main lookup (integrated)
├── pipeline/
│   └── smart_selector.py           # AI selector (integrated)
└── data/
    ├── tenant_hard_overrides.json           # 145 high-confidence ZIPs
    ├── tenant_ai_context.json               # 1,834 medium-confidence ZIPs
    ├── tenant_addresses_geocoded.json       # 87,357 geocoded addresses
    ├── geographic_boundary_analysis_electric.json  # 129 electric boundaries
    ├── geographic_boundary_analysis_gas.json       # 48 gas boundaries
    └── geographic_boundary_analysis_water.json     # 93 water boundaries
```

---

## Key Design Decisions

### 1. Confidence Thresholds
- **90%+**: Hard override (bypass AI entirely)
- **50-90%**: AI context (inform AI decision)
- **<50%**: Ignore (too noisy)

### 2. Geographic Boundary Confidence
- **15%+**: Use boundary rule
- Lower threshold because even weak geographic signal is useful when combined with other data

### 3. Nearby Consensus
- **80%+ agreement** among addresses within 0.25 miles
- Requires at least 2 nearby addresses

### 4. Deregulated Market Handling
- Don't reject tenant data just because they report a REP
- Map REPs to underlying TDUs when needed
- Flag deregulated markets so users understand retail choice

---

## Metrics

| Metric | Value |
|--------|-------|
| Total tenant records | 87,358 |
| Geocoded successfully | 87,357 (99.99%) |
| High-confidence overrides | 145 ZIPs |
| AI context ZIPs | 1,834 |
| Electric boundaries | 129 |
| Gas boundaries | 48 |
| Water boundaries | 93 |
| Multi-utility ZIPs (electric) | 3,628 |

---

## Example: How a Lookup Works

**Input:** `10000 S 1st St, Austin, TX 78748`

**Step 1: Geocode**
```
lat: 30.1605, lon: -97.8008
```

**Step 2: Check Hard Overrides**
- ZIP 78748 not in hard overrides (confidence < 90%)

**Step 3: Check Geographic Boundary**
- ZIP 78748 has boundary at lat 30.1628
- Address lat (30.1605) < boundary (30.1628)
- **Result: Pedernales Electric Cooperative** (south of boundary)

**Step 4: Return**
```json
{
  "name": "Pedernales Electric Cooperative",
  "_verification_source": "geographic_boundary",
  "_selection_reason": "Geographic boundary: North of 30.1628: Austin Energy, South: Pedernales Electric Cooperative"
}
```

---

## Questions for Review

1. **Confidence thresholds** - Are 90%/50%/15% appropriate, or should they be adjusted?
2. **Boundary detection algorithm** - Currently uses simple lat/lon splits. Should we implement more sophisticated clustering?
3. **AI prompt design** - Is the context we're providing to the AI optimal? Too much? Too little?
4. **Fallback behavior** - When tenant data conflicts with GIS, how should we weight each source?
5. **Data freshness** - Tenant data is a snapshot. How do we handle utility territory changes over time?
