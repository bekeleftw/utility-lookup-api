# Utility Data Audit Summary

## Overview

This document summarizes the systematic audit and improvement of utility provider data accuracy across the United States, using 87,000 tenant-verified addresses as ground truth.

## Objective

Improve utility lookup accuracy by:
1. Building ZIP-to-utility mappings from tenant-verified data
2. Identifying and fixing mismatches between API results and verified data
3. Adding confidence markers so the AI selector can weight results appropriately

---

## Data Source

**Tenant-Verified Dataset**: 87,000 addresses with verified electric, gas, and water providers
- Source: Actual tenant-reported utility providers
- Format: CSV with address, electricity, gas, water columns
- Coverage: All 50 US states

---

## Manual Metro Audits (9 metros)

### 1. NYC Metro
| Utility | Match Rate | Fixes |
|---------|------------|-------|
| Electric | 100% | None needed |
| Gas | Fixed | Brooklyn → National Grid (was Con Edison) |
| Water | 92 ZIPs | Long Island water districts mapped |

### 2. LA Metro
| Utility | Match Rate | Fixes |
|---------|------------|-------|
| Electric | 90% | Lake Los Angeles → SCE |
| Gas | 100% | Long Beach → Long Beach Gas & Oil |
| Water | 312 ZIPs | SoCal water districts mapped |

### 3. Chicago Metro
| Utility | Match Rate | Fixes |
|---------|------------|-------|
| Electric | 98% | Naperville, Geneva, St. Charles, Batavia municipal utilities |
| Gas | 100% | None needed |
| Water | 0 ZIPs | Already accurate |

### 4. DFW Metro
| Utility | Match Rate | Fixes |
|---------|------------|-------|
| Electric | OK | Deregulated market - TDU vs REP correctly handled |
| Gas | 83% | Boundary edge cases (Atmos dominant) |
| Water | 295 ZIPs | DFW water districts mapped |

### 5. Houston Metro
| Utility | Match Rate | Fixes |
|---------|------------|-------|
| Electric | 95% | Cleveland → Entergy, Magnolia → San Bernard EC |
| Gas | 95% | Cleveland → Universal Natural Gas |
| Water | 130 ZIPs | Houston water districts mapped |

### 6. Philadelphia Metro
| Utility | Match Rate | Fixes |
|---------|------------|-------|
| Electric | 98% | 1 boundary mismatch |
| Gas | 100% | None needed |
| Water | 64 ZIPs | Aqua PA dominant, mapped across PA/NJ |

### 7. Washington DC Metro
| Utility | Match Rate | Fixes |
|---------|------------|-------|
| Electric | 90% | SMECO (21 ZIPs), NOVEC (7 ZIPs) |
| Gas | 95% | Columbia Gas VA (9 ZIPs), MD (1 ZIP) |
| Water | 146 ZIPs | Fairfax Water, WSSC, Arlington, etc. |

### 8. Atlanta Metro
| Utility | Match Rate | Fixes |
|---------|------------|-------|
| Electric | 85% | 10 Georgia EMCs added (37 ZIPs total) |
| Gas | 89% | Deregulated - AGL is correct distribution |
| Water | 199 ZIPs | County water authorities mapped |

### 9. Florida (Miami/Tampa/Orlando)
| Utility | Match Rate | Fixes |
|---------|------------|-------|
| Electric | 90% | 4 co-ops added (LCEC, Withlacoochee, Peace River, SECO) - 33 ZIPs |
| Gas | 100% | TECO Peoples Gas dominant |
| Water | 278 ZIPs | County utilities mapped |

---

## Autopilot Nationwide Processing

After establishing patterns from manual audits, batch processing was applied to remaining states.

### Water Utility Mappings
| States | Total ZIPs | High Confidence | Medium | Low |
|--------|------------|-----------------|--------|-----|
| 39 | 2,983 | 2,494 (84%) | 270 (9%) | 219 (7%) |

### Electric Co-op/Municipal Mappings
| States | Total ZIPs | High Confidence | Medium | Low |
|--------|------------|-----------------|--------|-----|
| 25 | 184 | 119 (65%) | 27 (15%) | 38 (20%) |

---

## Confidence Level System

### Definition
Each ZIP mapping includes confidence markers based on provider dominance:

```json
{
  "name": "Fairfax Water",
  "sample_count": 12,
  "total_count": 15,
  "dominance_pct": 80.0,
  "confidence_level": "high"
}
```

### Thresholds

**Water:**
| Level | Dominance % | Confidence Score |
|-------|-------------|------------------|
| High | >80% | 70 |
| Medium | 60-80% | 55 |
| Low | 50-60% | 45 |

**Electric:**
| Level | Dominance % | Confidence Score |
|-------|-------------|------------------|
| High | >80% | 75 |
| Medium | 70-80% | 60 |
| Low | 60-70% | 50 |

### AI Selector Weighting

The `SmartSelector` now considers confidence levels:

```python
SOURCE_PRIORITY = {
    'municipal': 100,
    'municipal_water': 95,
    'tenant_verified_zip': 85,  # High confidence
    'state_gis': 90,
    # ... etc
}

# Adjusted by confidence level:
if confidence_level == 'high':
    base_priority = 85
elif confidence_level == 'medium':
    base_priority = 70
else:  # low
    base_priority = 55
```

---

## Files Created/Modified

### New Data Files
| File | Description | Records |
|------|-------------|---------|
| `data/long_island_water_districts.json` | Nassau/Suffolk water | 92 ZIPs |
| `data/socal_water_districts.json` | LA metro water | 312 ZIPs |
| `data/dfw_water_districts.json` | Dallas-Fort Worth water | 295 ZIPs |
| `data/houston_water_districts.json` | Houston metro water | 130 ZIPs |
| `data/philly_water_districts.json` | Philadelphia metro water | 64 ZIPs |
| `data/dc_water_districts.json` | DC metro water | 146 ZIPs |
| `data/atlanta_water_districts.json` | Atlanta metro water | 199 ZIPs |
| `data/florida_water_districts.json` | Florida water | 278 ZIPs |
| `data/remaining_states_water.json` | All other states water | 2,983 ZIPs |
| `data/remaining_states_electric.json` | Co-ops/municipals | 184 ZIPs |

### Modified Files
| File | Changes |
|------|---------|
| `municipal_utilities.py` | Added lookup functions for all new data files |
| `data/municipal_utilities.json` | Added EMCs, co-ops, boundary fixes |
| `pipeline/smart_selector.py` | Updated weighting for tenant_verified_zip source |

---

## Total Improvements

| Metric | Count |
|--------|-------|
| **Water ZIP mappings** | 4,499 |
| **Electric ZIP mappings** | 292 |
| **Individual utility fixes** | 15+ |
| **States covered** | 50 |

---

## Known Limitations

1. **ZIP-level granularity**: Some ZIPs straddle utility boundaries. Low-confidence ZIPs (50-60% dominance) may have split territories.

2. **New developments**: Recent construction may have different providers than older parts of a ZIP.

3. **Apartment complexes**: Some have bulk utility agreements that differ from surrounding area.

4. **Deregulated markets**: Texas electric and Pennsylvania show retail providers (TXU, Reliant) but API correctly returns transmission/distribution utilities (CenterPoint, PECO).

5. **Propane/rural areas**: Some rural addresses use propane delivery instead of natural gas infrastructure. API returns the default gas utility but actual service may be propane.

---

## Methodology

### Batch Processing Approach
```python
# 1. Aggregate tenant data by state/ZIP
for row in tenant_data:
    water_by_state_zip[state][zip][provider] += 1

# 2. Find dominant provider per ZIP
for zip, providers in zip_data.items():
    top_provider = max(providers, key=providers.get)
    if providers[top_provider] / total >= 0.5:
        mappings[zip] = {
            'name': top_provider,
            'dominance_pct': pct,
            'confidence_level': 'high' if pct > 0.8 else 'medium' if pct > 0.6 else 'low'
        }

# 3. Integrate into lookup pipeline
def lookup_remaining_states_water(zip_code, state):
    if zip_code in mappings[state]:
        return mappings[state][zip_code]
```

### Why This Works
- **Ground truth**: Tenant-verified data is what people actually pay for utilities
- **Statistical significance**: Only ZIPs with >50% provider dominance are mapped
- **Confidence weighting**: AI selector treats low-confidence data as supporting evidence, not authoritative

---

## Next Steps

1. **Webflow embeds**: Update embed code for production pages
2. **Parcel-level data**: For truly accurate results, integrate parcel/address-level utility data where available
3. **Continuous improvement**: As more tenant data comes in, update mappings and confidence levels
