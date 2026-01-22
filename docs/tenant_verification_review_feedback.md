# Tenant Verification System Review Feedback

## Overview

This document contains review feedback on the tenant verification system implementation. Address each section before considering the system production-ready.

---

## Critical Issues

### 1. Missing Test Validation

**Problem:** No evidence the system produces correct results. Documentation describes architecture but doesn't prove it works.

**Required Action:** Run the integrated pipeline against these known test cases and report results:

| Test Address | Utility Type | Expected Result | Why |
|--------------|--------------|-----------------|-----|
| 123 Little Elm Trail, Little Elm, TX 75068 | Electric | Oncor (TDU) | Deregulated market - should return TDU, not REP |
| 8500 Fourwinds Dr, Converse, TX 78109 | Electric | CPS Energy | HIFLD incorrectly shows Randolph AFB |
| 1000 N 40th Ave, Yakima, WA 98908 | Water | City of Yakima | Should use WA DOH state API, not EPA fallback |
| 206 Overlook Dr, Hanover, PA 17331 | Electric | Met-Ed (FirstEnergy) | Pennsylvania address |
| 1234 Main St, Matthews, NC 28104 | Electric | Duke Energy or Union Power | Split territory ZIP |

**Report format for each test:**
```
Address: [address]
Utility Type: [electric/gas/water]
Expected: [utility name]
Actual: [what system returned]
Data Source Used: [which priority level triggered]
Match: YES/NO
If NO, explain why
```

---

### 2. Hard Override Count Seems Low

**Problem:** Only 145 ZIPs have 90%+ confidence, but dataset contains 87,358 addresses across 8,389 unique ZIPs.

**Questions to answer:**
1. How many ZIPs have 100% agreement among all tenant reports? Those should all be hard overrides.
2. Is the confidence scorer penalizing single-utility ZIPs? It shouldn't.
3. What's the distribution of confidence scores across all ZIPs?

**Provide:**
```
ZIPs with 95-100% confidence: [count]
ZIPs with 90-95% confidence: [count]
ZIPs with 80-90% confidence: [count]
ZIPs with 50-80% confidence: [count]
ZIPs with <50% confidence: [count]
```

---

### 3. Geographic Boundary Confidence is Very Low

**Problem:** Example boundary has 0.18 confidence, another shows 0.12. These are barely better than random.

**Questions to answer:**
1. What's the distribution of boundary confidence scores?
2. How many boundaries have confidence > 0.5?
3. How many boundaries have confidence > 0.3?

**If most boundaries are below 0.3:** Consider disabling geographic boundary feature until algorithm improves. Low-confidence boundaries may introduce more errors than they prevent.

**Recommendation:** Raise minimum confidence threshold from 0.15 to 0.30, or require corroboration from another source.

---

### 4. Name Normalizer Integration Not Verified

**Problem:** Document says normalizer exists but doesn't confirm it's being applied before confidence scoring and comparison.

**Required verification:**

1. When a tenant reports "ComEd" and GIS returns "Commonwealth Edison", does the system recognize these as the same utility?

2. Run this test:
```python
# Test that normalizer is integrated
tenant_report = "ComEd"
gis_result = "Commonwealth Edison"
# After normalization, these should match
assert normalize(tenant_report) == normalize(gis_result)
```

3. Confirm normalizer is called:
   - Before confidence scoring (so "ComEd" x 5 and "Commonwealth Edison" x 3 count as 8 reports for same utility)
   - Before comparing tenant data to GIS results
   - Before comparing tenant data to HIFLD results

---

## Questions Requiring Answers

### Nearby Consensus Logic

The doc says "80%+ agreement within 0.25mi" but is vague on details.

**Answer these:**
1. How many addresses typically fall within 0.25mi of a query address?
2. What's the minimum sample size required? (Should be at least 3)
3. What happens if only 2 addresses exist nearby and they disagree?
4. Are you using Haversine distance or Euclidean approximation?
5. Is 0.25mi the right radius? Rural areas may need larger, urban areas smaller.

---

### Deregulated Market Handling

**Verify these scenarios work correctly:**

1. Tenant in Houston reports "Reliant Energy" for electric
   - System should identify Reliant as REP
   - System should return CenterPoint as TDU
   - Response should indicate deregulated market with retail choice

2. Tenant in Dallas reports "TXU Energy" for electric
   - System should identify TXU as REP
   - System should return Oncor as TDU

3. Tenant in Austin reports "Austin Energy" for electric
   - Austin Energy is municipal (not deregulated)
   - System should return Austin Energy directly

---

## Code Review Requests

### 1. Show the actual integration point

Provide the exact code from `utility_lookup_v1.py` where tenant overrides are checked. Confirm it matches the documented priority order:

```
Priority 0:   User-reported corrections
Priority 0.5: Tenant hard overrides
Priority 0.6: Geographic boundary
Priority 0.6: Nearby consensus
Priority 1:   AI Smart Selector
Priority 2:   GIS state APIs
...
```

### 2. Show confidence scorer calculation

Provide the actual formula used in `tenant_confidence_scorer.py`. Specifically:
- How is sample count weighted?
- How is street name consistency calculated?
- What causes a ZIP to get <90% confidence when all tenants agree?

### 3. Show geographic boundary detection algorithm

Provide the algorithm from `geographic_boundary_analyzer.py`. Specifically:
- How do you determine if a boundary is latitude-based vs longitude-based?
- How is confidence calculated?
- Why are most confidences so low (0.12-0.18)?

---

## Recommended Threshold Adjustments

| Parameter | Current | Recommended | Reason |
|-----------|---------|-------------|--------|
| Hard override threshold | 90% | 90% | Keep as-is |
| AI context threshold | 50% | 50% | Keep as-is |
| Geographic boundary threshold | 15% | 30% | Current is too permissive |
| Nearby consensus agreement | 80% | 80% | Keep as-is |
| Nearby consensus min samples | ? | 3 | Prevent 2-sample flukes |
| Nearby consensus radius | 0.25mi | 0.25mi urban, 1mi rural | Adapt to density |

---

## Data Freshness Concern

**Problem:** Tenant data is a point-in-time snapshot. Utility territories change (annexations, mergers, new service areas).

**Required addition:**
1. Add `last_verified` timestamp to each record
2. Implement confidence decay: reduce confidence by 10% per year since verification
3. Flag records older than 24 months for re-verification

---

## Deliverables Checklist

Before this system is production-ready, provide:

- [ ] Test results for all 5 test addresses listed above
- [ ] Confidence score distribution across all ZIPs
- [ ] Geographic boundary confidence distribution
- [ ] Proof that name normalizer is integrated at all comparison points
- [ ] Answers to nearby consensus questions
- [ ] Deregulated market scenario verification
- [ ] Actual code snippets for integration points, confidence scorer, and boundary detector

---

## Summary

The architecture is sound, but there's no evidence the implementation actually works. The geographic boundary feature may be too unreliable to use. Test validation is mandatory before deployment.

Priority order for addressing issues:
1. **Run test cases** - Proves system works end-to-end
2. **Verify name normalizer integration** - Without this, comparisons fail silently
3. **Review geographic boundary value** - May need to disable or raise threshold
4. **Answer technical questions** - Nearby consensus, confidence calculation details
