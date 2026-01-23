# Utility Name Normalization - Problem & Solution

## The Problem

When aggregating tenant-verified utility data by ZIP code, **name variations caused incorrect confidence scores and missed mappings**.

### Example: Gas Utilities in North Carolina

Tenants reported the same utility with different names:
```
"Piedmont Natural Gas"
"piedmont Natrual gas"
"Piedmont Natural Gas, Dominion Energy"
"Dominion NC, Piedmont Natural Gas"
```

Without normalization, these were counted as **4 different providers** instead of 1, causing:
1. **Artificially low dominance percentages** - A ZIP with 100% Piedmont coverage might show 25% for each variation
2. **Missed mappings** - ZIPs that should meet the 60% threshold didn't because votes were split
3. **Inconsistent API responses** - Same utility returned with different names depending on data source

### Example: Electric Utilities

```
"Duke Energy"
"Duke Energy Carolinas"
"Duke Energy Carolinas, LLC"
"Duke energy"
```

### Example: Water Utilities

```
"Charlotte Water"
"Charlotte-Mecklenburg Utilities"
"City of Charlotte Water"
"Charlotte Water - NC"
```

---

## The Solution

Created `utility_normalization.py` with three functions that normalize names **before aggregation**:

### 1. `normalize_electric_name()`

```python
# Input variations → Normalized output
"Duke Energy Carolinas, LLC" → "DUKE ENERGY CAROLINAS"
"Duke energy" → "DUKE ENERGY"
"FPL" → "FLORIDA POWER & LIGHT"
"Georgia EMC" → "GEORGIA EMC"
"Cobb Electric Cooperative" → "COBB ELECTRIC COOPERATIVE"
```

**Key normalizations:**
- Duke Energy → regional variants (Carolinas, Florida, Indiana, Ohio/Kentucky)
- Dominion Energy → regional variants
- Co-op suffixes: EMC, Electric Membership Corp, Cooperative, Co-op → standardized
- Major IOUs: FPL, SCE, PG&E, SDGE, CenterPoint, Oncor, AEP, Xcel, Entergy

### 2. `normalize_gas_name()`

```python
# Input variations → Normalized output
"Piedmont Natural Gas" → "PIEDMONT NATURAL GAS"
"piedmont Natrual gas" → "PIEDMONT NATURAL GAS"
"Dominion Energy" → "ENBRIDGE GAS"
"Dominion NC" → "ENBRIDGE GAS"
"Enbridge Gas NC" → "ENBRIDGE GAS"
"Atmos" → "ATMOS ENERGY"
```

**Key normalizations:**
- Piedmont Natural Gas (all variations)
- Dominion/Enbridge merger handled (both → ENBRIDGE GAS)
- Atmos Energy
- Spire (formerly Laclede)
- Columbia Gas / NiSource
- City utilities (Greenville Utilities Commission, etc.)

**Filters out non-utilities:**
- Propane providers (Amerigas, Blossman, Suburban Propane)
- "No gas", "N/A", "None", "Landlord", "HOA"

### 3. `normalize_water_name()`

```python
# Input variations → Normalized output
"Charlotte Water" → "CHARLOTTE WATER"
"Charlotte-Mecklenburg Utilities" → "CHARLOTTE WATER"
"American Water - NJ" → "AMERICAN WATER - NJ"
"New Jersey American Water" → "AMERICAN WATER - NJ"
"Aqua PA" → "AQUA PENNSYLVANIA"
"City of Austin - TX" → "CITY OF AUSTIN"
```

**Key normalizations:**
- American Water → regional variants (NJ, PA, CA, IL, etc.)
- Aqua America → regional variants
- WSSC / Washington Suburban
- City/Town utilities → standardized format
- State suffixes removed ("- NC", "- TX")

**Filters out non-utilities:**
- Private wells, septic
- HOA, landlord, property management
- "Included", "N/A", "None"

---

## Results

### Before Normalization

| Utility Type | ZIPs Mapped | Issue |
|--------------|-------------|-------|
| Electric | 184 | Many co-ops missed due to name variations |
| Gas | 264 | Piedmont had 0 NC ZIPs (variations split votes) |
| Water | 2,983 | Inconsistent city utility names |

### After Normalization

| Utility Type | ZIPs Mapped | Improvement |
|--------------|-------------|-------------|
| Electric | 494 | +168% (co-ops properly aggregated) |
| Gas | 6,222 | +2,256% (Piedmont now has 116 NC ZIPs) |
| Water | 5,201 | +74% (city utilities consolidated) |

---

## Implementation

### Aggregation Process

```python
from utility_normalization import normalize_gas_name

# Before: Raw names counted separately
gas_counts = {"Piedmont Natural Gas": 5, "piedmont Natrual gas": 2, "Dominion NC, Piedmont Natural Gas": 1}
# Dominance: 5/8 = 62.5% (barely meets threshold)

# After: Normalized names aggregated
for raw_name in tenant_reports:
    normalized = normalize_gas_name(raw_name)  # → "PIEDMONT NATURAL GAS"
    gas_counts[normalized] += 1
# Dominance: 8/8 = 100% (high confidence)
```

### API Response Normalization

The normalization functions can also be used to standardize API responses:

```python
from utility_normalization import normalize_utility_name

# Normalize any utility name by type
normalize_utility_name("Duke energy carolinas", "electric")  # → "DUKE ENERGY CAROLINAS"
normalize_utility_name("Enbridge Gas NC", "gas")  # → "ENBRIDGE GAS"
normalize_utility_name("City of Austin - TX", "water")  # → "CITY OF AUSTIN"
```

---

## Files Changed

| File | Description |
|------|-------------|
| `utility_normalization.py` | New module with normalization functions |
| `data/remaining_states_electric.json` | Rebuilt with normalization (494 ZIPs) |
| `data/remaining_states_gas.json` | Rebuilt with normalization (6,222 ZIPs) |
| `data/remaining_states_water.json` | Rebuilt with normalization (5,201 ZIPs) |

---

## Specific Fix: Denver, NC (ZIP 28037)

### Before
- **Gas**: "No gas provider found" (2 Piedmont records split by name variations)

### After
- **Gas**: "Piedmont Natural Gas" (100% confidence, 2/2 verified addresses)

The normalization correctly identified that both tenant reports were for the same provider, allowing the ZIP to meet the confidence threshold.
