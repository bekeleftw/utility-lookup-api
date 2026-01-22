# Tenant Verification Data Analysis: Approach & Findings

## Executive Summary

We have a dataset of **87,358 addresses with tenant-verified utility providers**. This data comes from tenants who uploaded utility bills as proof of service during an onboarding process. We're using this data to improve the accuracy of our utility lookup API, which currently relies on GIS boundary data, EIA datasets, and other sources that have known accuracy issues in areas with complex utility boundaries.

---

## The Data Source

### What It Is
- **File**: `addresses_with_tenant_verification.csv`
- **Records**: 87,358 addresses
- **Key Fields**:
  - `display`: Full address string (e.g., "123 Main St, Austin, TX 78701")
  - `Electricity`: Tenant-reported electric utility provider
  - `Gas`: Tenant-reported gas utility (if applicable)

### How It Was Collected
Tenants uploaded utility bills or account statements during an onboarding flow. The system extracted the utility provider name from these documents.

### Data Quality Considerations

**Strengths:**
- Real-world ground truth from actual utility customers
- Covers 8,389 unique ZIP codes across all 50 states
- High volume in key states: TX (15K+), CA (8K+), FL (6K+), VA (5K+)

**Weaknesses:**
1. **Tenant errors**: Tenants sometimes upload the wrong document or misidentify their provider
   - Example: Tenant uploads Atmos Energy (gas) bill when asked for electric provider
   - Example: Tenant in deregulated market uploads REP bill instead of TDU
   
2. **Name variations**: Same utility appears under different names
   - "Duke Energy" vs "Duke Energy Carolinas" vs "Duke Energy Corporation"
   - "PG&E" vs "Pacific Gas & Electric" vs "Pacific Gas and Electric Company"
   
3. **REP vs TDU confusion** (Texas and other deregulated states):
   - Tenant reports "TXU Energy" (their retail provider)
   - Our API returns "Oncor" (the actual transmission/distribution utility)
   - Both are technically correct for different purposes

4. **No geocoordinates**: We only have address strings, not lat/lon, limiting geographic analysis

---

## The Problem We're Solving

### Root Cause: 53% of ZIP Codes Have Multiple Utilities

Analysis of EIA (Energy Information Administration) data reveals:
- **33,412 ZIP codes** in our EIA dataset
- **17,940 ZIPs (53.7%)** have multiple electric utilities serving them

This means ZIP-level data is fundamentally insufficient for accurate utility lookup. The boundaries between utilities often run through the middle of ZIP codes, down specific streets, or even split individual blocks.

### Examples of Split-Territory ZIPs

| ZIP | City, State | Utilities | Issue |
|-----|-------------|-----------|-------|
| 28078 | Huntersville, NC | Duke Energy, Energy United | Co-op serves some streets |
| 30045 | Lawrenceville, GA | Georgia Power, Jackson EMC | EMC boundary unclear |
| 85258 | Scottsdale, AZ | APS, Salt River Project | Historic territory split |
| 32825 | Orlando, FL | Duke Energy, OUC | Municipal boundary |

---

## Analysis Approaches Attempted

### Approach 1: Statistical Pattern Matching (No AI)

**Method**: Group addresses by ZIP + street name, count utility occurrences, create rules where one utility dominates.

**Results**:
- Generated 4,380 rules
- Example: "cade* streets in ZIP 85212 → Salt River Project (63 samples, 94% confidence)"

**Limitations**:
- Only finds patterns where same street appears multiple times
- No geographic reasoning
- Can't detect "north of Main St" type boundaries

### Approach 2: AI Analysis of Problem ZIPs

**Method**: For each ZIP with multiple utilities, send address samples to GPT-4o-mini and ask it to identify patterns.

**First Attempt (Flawed)**:
```
Prompt: "Analyze these addresses and find geographic patterns"
Response: "Georgia Power serves northern/western parts"
```

**Problem**: The AI was guessing about "north/south" without any actual geographic data. Street names like "Daisy Cir" and "Crown Landing Pkwy" don't indicate direction.

**Improved Attempt**:
```
Prompt: "Analyze STREET NAMES and STREET NUMBERS to find patterns. 
        Don't guess about north/south unless street names indicate direction."
Response: 
  - "Flounder Run → New Bern NC"
  - "Iverson Ln → Duke Energy"
  - "Meadow Dr → Duke Energy"
  - "Fenwick Ct → York Electric Cooperative"
```

**Results**:
- Analyzed 1,209 problem ZIPs in 43.8 seconds (100 concurrent workers)
- Generated 2,682 specific street-level rules
- Average confidence: 85%
- Cost: ~$0.40

---

## Current Data Assets

### 1. `tenant_verified_lookup.json`
```json
{
  "street_overrides": {
    "92115": {
      "e falls view drive": "San Diego Gas & Electric",
      "tipton street": "San Diego Gas & Electric"
    }
  },
  "zip_alternatives": {
    "28078": ["Energy United", "Duke Energy"],
    "30045": ["Georgia Power Company", "Jackson EMC - GA"]
  }
}
```
- 786 ZIPs with street-level overrides
- 1,292 ZIPs with multiple utilities identified

### 2. `data/learned_boundary_rules.json`
```json
{
  "rules": [
    {
      "rule_id": "85212:street_prefix:cade*",
      "zip_code": "85212",
      "utility_name": "Salt River Project",
      "rule_type": "street_prefix",
      "pattern": "cade*",
      "confidence": 0.94,
      "sample_count": 63
    }
  ]
}
```
- 4,380 statistical rules
- Rule types: street_name, street_prefix, street_number_range

### 3. `data/ai_boundary_insights_v2.json`
```json
{
  "insights": [
    {
      "zip": "29720",
      "city": "Lancaster",
      "state": "SC",
      "utilities": {"Duke Energy": 9, "York Electric Cooperative": 2},
      "utility_rules": [
        {"street_match": "Meadow Dr", "utility": "Duke Energy"},
        {"street_match": "Fenwick Ct", "utility": "York Electric Cooperative"}
      ],
      "confidence": 0.85,
      "notes": "Duke Energy serves Meadow Dr and Plantation Rd, York Electric serves Fenwick Ct"
    }
  ]
}
```
- 647 AI-analyzed ZIPs with insights
- 529 have specific utility rules
- 2,682 total street-level rules

---

## Integration Points

### Current Integration
The `smart_selector.py` module (which uses GPT-4o-mini to resolve conflicts between data sources) now receives this context:

```
AI-ANALYZED BOUNDARY INSIGHT for ZIP 30252:
- Primary utility: Georgia Power Company
- Secondary utility: Snapping Shoals EMC
- Boundary: Georgia Power serves Meadow Dr, Snapping Shoals serves rural areas
- Confidence: 85%

Utilities seen in this ZIP: Georgia Power Company, Snapping Shoals EMC
```

### Potential Integration Approaches

1. **Hard Override**: If we have a street-level rule with high confidence, use it directly
   - Pro: Fast, deterministic
   - Con: Tenant data isn't always correct

2. **AI Context**: Feed rules to AI selector as additional context
   - Pro: AI can weigh against other sources
   - Con: Still relies on AI judgment

3. **Confidence Boosting**: Increase confidence score for utilities that match tenant patterns
   - Pro: Soft influence, not hard override
   - Con: May not be enough to change outcomes

4. **Hybrid**: Use hard override for very high confidence (95%+), context for medium confidence

---

## Open Questions

1. **How should we handle tenant errors?**
   - Some tenants definitely uploaded wrong utility
   - Should we require N confirmations before trusting a pattern?

2. **REP vs TDU in deregulated markets**
   - Tenant says "TXU Energy", we say "Oncor"
   - Both are correct - should we return both?

3. **Geocoding for better analysis?**
   - We could geocode all 87K addresses to get lat/lon
   - Would enable true geographic boundary detection
   - Cost: ~$8-15 for Google Geocoding API

4. **Continuous learning?**
   - Should we re-run analysis as new tenant data comes in?
   - How do we handle conflicting rules over time?

5. **Accuracy target**
   - Current estimated accuracy: ~80%
   - Target: 90%+
   - Is tenant data sufficient to close the gap?

---

## Appendix: Sample Data

### Raw Tenant Record
```csv
display,Electricity,Gas
"123 Meadow Dr, Lancaster, SC 29720","Duke Energy","Piedmont Natural Gas"
```

### Statistical Rule
```json
{
  "rule_id": "29720:street_name:meadow dr",
  "zip_code": "29720",
  "utility_name": "Duke Energy",
  "rule_type": "street_name",
  "pattern": "meadow dr",
  "confidence": 1.0,
  "sample_count": 5
}
```

### AI Insight
```json
{
  "zip": "29720",
  "city": "Lancaster",
  "state": "SC",
  "utility_rules": [
    {"street_match": "Meadow Dr", "utility": "Duke Energy"},
    {"street_match": "Plantation Rd", "utility": "Duke Energy"},
    {"street_match": "Fenwick Ct", "utility": "York Electric Cooperative"}
  ],
  "confidence": 0.85,
  "notes": "Duke Energy serves all addresses on Meadow Dr and Plantation Rd, while York Electric serves Fenwick Ct"
}
```

---

## Files Reference

| File | Description |
|------|-------------|
| `addresses_with_tenant_verification.csv` | Raw tenant data (87K records) |
| `tenant_verified_lookup.json` | Street overrides + ZIP alternatives |
| `data/learned_boundary_rules.json` | 4,380 statistical rules |
| `data/ai_boundary_insights_v2.json` | 647 AI-analyzed ZIP insights |
| `utility_boundary_learner.py` | Statistical pattern discovery |
| `ai_boundary_analyzer_concurrent.py` | AI analysis with 100 concurrent workers |
| `pipeline/smart_selector.py` | AI selector that uses these insights |
