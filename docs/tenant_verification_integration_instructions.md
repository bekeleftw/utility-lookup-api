# Tenant-Verified Utility Data Integration Instructions

## Objective

Integrate 87,358 tenant-verified utility records into the utility lookup tool to improve accuracy. Tenant data is real ground truth but contains noise (wrong uploads, name variations, REP vs TDU confusion). This document specifies how to filter signal from noise and integrate it into the lookup pipeline.

---

## Phase 1: Data Cleanup (Do This First)

### 1.1 Canonical Name Mapping

Create `utility_name_normalizer.py` with a normalization table. All comparisons must use canonical names.

```python
UTILITY_ALIASES = {
    # Electric
    "Duke Energy": [
        "Duke Energy Carolinas", 
        "Duke Energy Corporation", 
        "Duke Energy Progress",
        "Duke Energy Florida",
        "Duke Energy Indiana"
    ],
    "PG&E": [
        "Pacific Gas & Electric", 
        "Pacific Gas and Electric Company", 
        "PG&E Corporation"
    ],
    "Georgia Power": [
        "Georgia Power Company", 
        "Georgia Power Co", 
        "GA Power"
    ],
    "Southern California Edison": [
        "SCE",
        "SoCal Edison",
        "So Cal Edison"
    ],
    "Florida Power & Light": [
        "FPL",
        "Florida Power and Light",
        "FP&L"
    ],
    # Gas
    "Atmos Energy": [
        "Atmos Energy Corporation",
        "Atmos"
    ],
    "Piedmont Natural Gas": [
        "Piedmont Gas",
        "Piedmont NG"
    ],
    # Add more as discovered
}

def normalize_utility_name(name: str) -> str:
    """Convert any utility name variant to its canonical form."""
    if not name:
        return None
    
    name_lower = name.lower().strip()
    
    for canonical, aliases in UTILITY_ALIASES.items():
        if name_lower == canonical.lower():
            return canonical
        for alias in aliases:
            if name_lower == alias.lower():
                return canonical
    
    # No match found, return original (titlecased)
    return name.strip().title()
```

**Critical:** Run ALL tenant data through this normalizer before any analysis. Without this, "Duke Energy" and "Duke Energy Carolinas" will be counted as different utilities when they're the same.

---

### 1.2 REP vs TDU Tagging (Deregulated Markets)

Create `deregulated_market_handler.py` to handle Texas and other deregulated states.

```python
# Texas Retail Electric Providers (REPs) - NOT the utility we want
TEXAS_REPS = [
    "TXU Energy", "Reliant", "Direct Energy", "Gexa Energy",
    "Green Mountain Energy", "Constellation", "Chariot Energy",
    "Pulse Power", "4Change Energy", "Frontier Utilities",
    "Champion Energy", "Discount Power", "Express Energy",
    "First Choice Power", "Frontier Utilities", "Payless Power",
    "Pennywise Power", "Rhythm", "Shell Energy", "TriEagle Energy",
    "Veteran Energy", "Volt Electricity", "Xoom Energy"
]

# Texas Transmission/Distribution Utilities (TDUs) - WHAT WE WANT
TEXAS_TDUS = {
    "Oncor": ["Oncor Electric Delivery", "Oncor Electric"],
    "CenterPoint": ["CenterPoint Energy", "CNP"],
    "AEP Texas": ["AEP Texas North", "AEP Texas Central", "AEP"],
    "TNMP": ["Texas-New Mexico Power", "Texas New Mexico Power"]
}

# Other deregulated states
PENNSYLVANIA_REPS = ["Direct Energy", "Constellation", ...]
PENNSYLVANIA_TDUS = ["PECO", "PPL Electric", "Duquesne Light", ...]

def is_retail_provider(utility_name: str, state: str) -> bool:
    """Check if this is a retail provider (not the TDU we want)."""
    if state == "TX":
        return utility_name in TEXAS_REPS
    elif state == "PA":
        return utility_name in PENNSYLVANIA_REPS
    # Add other deregulated states
    return False

def get_tdu_for_location(lat: float, lon: float, state: str) -> str:
    """For deregulated markets, return the TDU regardless of what tenant reported."""
    # This should call your existing GIS lookup for the TDU territory
    pass
```

**Rule:** When tenant reports a REP in a deregulated ZIP:
- Do NOT treat this as a GIS mismatch
- Store both: `{rep: "TXU Energy", tdu: "Oncor"}`
- Return the TDU in API responses (that's what property managers need)

---

### 1.3 Utility Type Validation

Flag likely errors where tenant uploaded wrong document:

```python
def validate_utility_type(reported_name: str, expected_type: str) -> bool:
    """
    Check if reported utility matches expected type.
    expected_type: "electric" or "gas"
    """
    name_lower = reported_name.lower()
    
    # Electric field contains gas utility
    if expected_type == "electric":
        gas_indicators = ["gas", "piedmont", "atmos", "spire", "nicor"]
        if any(indicator in name_lower for indicator in gas_indicators):
            return False  # Likely wrong upload
    
    # Gas field contains electric utility
    if expected_type == "gas":
        electric_indicators = ["electric", "power", "edison", "ppl", "emc", "coop"]
        if any(indicator in name_lower for indicator in electric_indicators):
            return False  # Likely wrong upload
    
    return True
```

---

## Phase 2: Confidence Scoring

Create `tenant_confidence_scorer.py`. Not all tenant data points are equal.

### 2.1 Confidence Tiers

| Condition | Confidence | Action |
|-----------|------------|--------|
| 10+ tenants, same street, same utility, 100% agreement | 99% | Hard override |
| 5-9 tenants, same street, same utility, 95%+ agreement | 90% | Hard override |
| 3-4 tenants, same street, same utility, 90%+ agreement | 80% | Strong boost to AI selector |
| 2 tenants, same street, same utility | 70% | Context for AI selector |
| 1 tenant only | 50% | Store but don't use for decisions |
| Tenants disagree on same street | Flag | Manual review queue |

### 2.2 Implementation

```python
def calculate_tenant_confidence(
    zip_code: str, 
    street_name: str, 
    tenant_records: List[dict]
) -> dict:
    """
    Calculate confidence score for tenant-reported utility on a street.
    
    Returns:
        {
            "utility": "Duke Energy",
            "confidence": 0.92,
            "sample_count": 7,
            "agreement_rate": 1.0,
            "action": "hard_override"  # or "ai_context" or "store_only"
        }
    """
    # Normalize all utility names first
    utilities = [normalize_utility_name(r["utility"]) for r in tenant_records]
    
    # Count occurrences
    from collections import Counter
    counts = Counter(utilities)
    total = len(utilities)
    
    if total == 0:
        return None
    
    # Find dominant utility
    dominant_utility, dominant_count = counts.most_common(1)[0]
    agreement_rate = dominant_count / total
    
    # Determine confidence and action
    if total >= 10 and agreement_rate == 1.0:
        confidence = 0.99
        action = "hard_override"
    elif total >= 5 and agreement_rate >= 0.95:
        confidence = 0.90
        action = "hard_override"
    elif total >= 3 and agreement_rate >= 0.90:
        confidence = 0.80
        action = "ai_boost"
    elif total >= 2 and agreement_rate >= 0.90:
        confidence = 0.70
        action = "ai_context"
    elif total == 1:
        confidence = 0.50
        action = "store_only"
    else:
        # Disagreement case
        confidence = 0.40
        action = "flag_review"
    
    return {
        "utility": dominant_utility,
        "confidence": confidence,
        "sample_count": total,
        "agreement_rate": agreement_rate,
        "action": action,
        "all_utilities": dict(counts)  # For review/debugging
    }
```

**Key rule:** A single tenant is NOT enough to override GIS. Require corroboration.

---

## Phase 3: Generate Override Files

After processing all tenant data, generate two output files:

### 3.1 Hard Overrides (99%+ confidence)

File: `tenant_hard_overrides.json`

```json
{
  "version": "2025-01-21",
  "description": "High-confidence tenant-verified utility mappings. Use as primary source.",
  "overrides": {
    "29720": {
      "meadow dr": {
        "electric": "Duke Energy",
        "confidence": 0.99,
        "sample_count": 12,
        "agreement_rate": 1.0
      },
      "plantation rd": {
        "electric": "Duke Energy",
        "confidence": 0.95,
        "sample_count": 6,
        "agreement_rate": 1.0
      }
    },
    "85212": {
      "cade": {
        "electric": "Salt River Project",
        "confidence": 0.94,
        "sample_count": 63,
        "match_type": "street_prefix"
      }
    }
  }
}
```

### 3.2 AI Context Rules (70-90% confidence)

File: `tenant_ai_context.json`

```json
{
  "version": "2025-01-21",
  "description": "Medium-confidence tenant patterns. Feed to AI selector as context.",
  "context_rules": {
    "30045": {
      "utilities_observed": ["Georgia Power Company", "Jackson EMC"],
      "patterns": [
        {"street": "crown landing", "utility": "Georgia Power Company", "confidence": 0.75, "samples": 3},
        {"street": "daisy", "utility": "Jackson EMC", "confidence": 0.70, "samples": 2}
      ],
      "notes": "Split territory - both utilities serve this ZIP"
    }
  }
}
```

---

## Phase 4: Integration Logic

Modify the main lookup function to use tenant data:

```python
def lookup_utility(address: str, utility_type: str = "electric") -> dict:
    """
    Main utility lookup with tenant data integration.
    """
    # Parse address
    parsed = parse_address(address)
    zip_code = parsed["zip"]
    street = normalize_street_name(parsed["street"])
    state = parsed["state"]
    
    # Get coordinates
    lat, lon = geocode(address)
    
    # STEP 1: Check tenant hard overrides (99%+ confidence)
    override = check_tenant_override(zip_code, street, utility_type)
    if override and override["confidence"] >= 0.95:
        return {
            "utility": override["utility"],
            "confidence": override["confidence"],
            "source": "tenant_verified",
            "sample_count": override["sample_count"]
        }
    
    # STEP 2: Query state-specific GIS API
    gis_result = lookup_state_gis(lat, lon, state, utility_type)
    
    # STEP 3: Query HIFLD/EPA fallback
    fallback_result = lookup_hifld(lat, lon, utility_type)
    
    # STEP 4: If GIS sources agree, return with tenant confirmation boost
    if gis_result and fallback_result:
        if normalize_utility_name(gis_result["utility"]) == normalize_utility_name(fallback_result["utility"]):
            result = gis_result
            # Boost confidence if tenant data confirms
            tenant_context = get_tenant_context(zip_code, street, utility_type)
            if tenant_context and normalize_utility_name(tenant_context["utility"]) == normalize_utility_name(result["utility"]):
                result["confidence"] = min(0.99, result["confidence"] + 0.1)
                result["tenant_confirmed"] = True
            return result
    
    # STEP 5: Sources disagree or low confidence - use AI selector with tenant context
    tenant_context = get_tenant_context(zip_code, street, utility_type)
    
    ai_input = {
        "address": address,
        "gis_result": gis_result,
        "fallback_result": fallback_result,
        "tenant_context": tenant_context  # Include tenant patterns
    }
    
    return ai_selector.resolve(ai_input)
```

---

## Phase 5: Edge Case Handling

### 5.1 Tenant Contradicts High-Confidence GIS

```python
def resolve_tenant_vs_gis(tenant_confidence: float, gis_confidence: float, tenant_utility: str, gis_utility: str) -> dict:
    if tenant_confidence < 0.80 and gis_confidence > 0.90:
        # Trust GIS, flag tenant for review
        return {
            "utility": gis_utility,
            "source": "gis",
            "flag": "tenant_contradiction",
            "tenant_claimed": tenant_utility
        }
    elif tenant_confidence > 0.90 and gis_confidence < 0.70:
        # Trust tenant, flag GIS as potentially outdated
        return {
            "utility": tenant_utility,
            "source": "tenant_verified",
            "flag": "gis_potentially_outdated",
            "gis_claimed": gis_utility
        }
    else:
        # Send to AI selector
        return None  # Caller should invoke AI selector
```

### 5.2 Tenants Disagree With Each Other

```python
def handle_tenant_disagreement(zip_code: str, street: str, utilities: dict) -> dict:
    """
    When tenants report different utilities for same street.
    utilities: {"Duke Energy": 3, "York Electric": 2}
    """
    total = sum(utilities.values())
    dominant = max(utilities.items(), key=lambda x: x[1])
    
    disagreement_rate = 1 - (dominant[1] / total)
    
    if disagreement_rate > 0.20:
        # Likely a boundary runs through this street
        return {
            "utilities": list(utilities.keys()),
            "note": "Multiple utilities serve this area",
            "is_split_territory": True
        }
    else:
        # Minor disagreement, trust dominant
        return {
            "utility": dominant[0],
            "confidence": dominant[1] / total,
            "minority_reports": {k: v for k, v in utilities.items() if k != dominant[0]}
        }
```

---

## Phase 6: Geocoding (Recommended)

Geocode all 87K addresses to enable geographic analysis.

**Cost:** ~$8-15 via Google Geocoding API

**Benefits:**
1. Plot utility assignments on map to see actual boundaries
2. Distance-based confidence ("0.1 miles from 5 confirmed addresses")
3. Cross-validate tenant data against GIS polygons
4. Cluster analysis for boundary detection

**Implementation:**
```python
# Batch geocode with rate limiting
import googlemaps
from time import sleep

def geocode_tenant_data(records: List[dict], api_key: str) -> List[dict]:
    gmaps = googlemaps.Client(key=api_key)
    
    for record in records:
        try:
            result = gmaps.geocode(record["display"])
            if result:
                location = result[0]["geometry"]["location"]
                record["lat"] = location["lat"]
                record["lon"] = location["lng"]
            sleep(0.05)  # Rate limit: 20 requests/second
        except Exception as e:
            record["geocode_error"] = str(e)
    
    return records
```

---

## Files to Create

| File | Purpose |
|------|---------|
| `utility_name_normalizer.py` | Canonical name mapping for all utilities |
| `deregulated_market_handler.py` | REP vs TDU logic for TX, PA, etc. |
| `tenant_confidence_scorer.py` | Calculate confidence from samples + agreement |
| `tenant_hard_overrides.json` | High-confidence overrides (generated) |
| `tenant_ai_context.json` | Medium-confidence AI context (generated) |
| `generate_tenant_rules.py` | Script to process raw data and generate above files |

---

## Success Metrics

Track these to verify the integration is working:

| Metric | Description | Target |
|--------|-------------|--------|
| Override hit rate | How often tenant hard overrides fire | Track only |
| GIS confirmation rate | Tenant agrees with GIS | > 80% |
| Contradiction rate | Tenant disagrees with GIS | < 20% |
| AI selector influence | When tenant context provided, AI picks tenant utility | Track only |
| End-to-end accuracy | Correct utility returned | > 90% |

---

## Execution Order

1. **Phase 1.1**: Build utility name normalizer (MUST BE FIRST)
2. **Phase 1.2**: Build REP vs TDU handler for deregulated markets
3. **Phase 1.3**: Add utility type validation
4. **Phase 2**: Implement confidence scoring
5. **Phase 3**: Generate override and context files
6. **Phase 4**: Integrate into main lookup function
7. **Phase 5**: Add edge case handling
8. **Phase 6**: Geocode addresses (optional but recommended)

**Do not skip Phase 1. The rest is useless if name normalization isn't working.**

---

## Test Cases

After implementation, verify with these known cases:

| Address | Expected Electric | Expected Gas | Notes |
|---------|-------------------|--------------|-------|
| Yakima, WA | Yakima Water Division | - | Should use WA DOH, not EPA |
| Little Elm, TX | Oncor | Atmos Energy | TDU, not REP |
| Lancaster, SC 29720 | Duke Energy (most streets) | Piedmont | Check street-level override |
| Huntersville, NC 28078 | Duke or Energy United | Piedmont | Split territory |
