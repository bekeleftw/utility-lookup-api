# Provider Lookup Refinement Project

## Status: In Progress
**Last Updated:** February 3, 2026

---

## Overview

This project aims to improve utility provider lookup accuracy by analyzing a large dataset of 384,000 mapped addresses and comparing them against our GIS-based API lookups. The goal is to identify and resolve discrepancies, build sub-ZIP provider boundaries, and create verified correction rules.

---

## Completed Work

### Phase 1: Data Analysis
- **Input:** `all mapped providers.csv` (384,350 addresses across 24,528 ZIPs)
- Separated regulated vs deregulated states
- Normalized provider names and detected conflicts
- Identified 3,187 ZIPs with 2+ electric providers

### Phase 2: API Comparison
- **50K addresses compared** against our GIS-based lookup API
- **46,146 successful lookups** (92% success rate)
- **9,708 unique ZIPs** covered (40% of total)
- **507 ZIPs with confirmed provider splits** identified

### Phase 3: Disagreement Analysis
| Utility | Agree | Disagree | Disagree % |
|---------|-------|----------|------------|
| Electric | 19,288 | 25,468 | 56.9% |
| Gas | 23,998 | 18,958 | 44.1% |

**7,693 ZIPs** have disagreements between the spreadsheet and API that need verification.

### Phase 4: Verification Workflow
Verified top 20 disputed ZIPs using AI research:

| Category | Count | Description |
|----------|-------|-------------|
| Name variations | 18 | Same company, different names (e.g., "Xcel Energy" = "PSC of Colorado") |
| Split territories | 11 | Both providers legitimately serve the area |
| Corrections needed | 11 | One source is definitively wrong |

**Key findings:**
- Spreadsheet has systematic errors listing "Enbridge Gas" for areas where Enbridge doesn't operate (Utah, North Carolina, Ohio)
- API sometimes returns municipal utilities that only serve small portions of a ZIP
- Many "disagreements" are actually name variations of the same company

---

## Files Created

| File | Description |
|------|-------------|
| `data/real_sub_zip_splits_50k.json` | 507 ZIPs with confirmed provider splits |
| `data/sub_zip_provider_rules_50k.json` | 9,860 street-level provider rules |
| `data/verification_queue.json` | 7,693 ZIPs needing verification |
| `data/verified_disputes.json` | AI research results for 20 ZIPs |
| `data/verified_provider_rules.json` | Categorized verification results |
| `data/smartselector_enhancement.json` | Ambiguous ZIP guidance for AI prompt |
| `data/texas_tdu_mappings.json` | Texas TDU mappings by ZIP |
| `massive_comparison_50k.json` | Full 46K comparison results |
| `targeted_sample_74k_clean.json` | Prioritized sample for next run |

---

## Scripts Created

| Script | Purpose |
|--------|---------|
| `run_massive_comparison.py` | Parallel API comparison with checkpointing |
| `run_targeted_comparison.py` | Prioritized comparison for uncovered ZIPs |
| `verify_provider_disputes.py` | AI-powered dispute verification |

---

## Next Steps

### Immediate (Ready to Run)
1. **Run 74K targeted comparison** on separate computer (~12 hours)
   - Prioritizes high-lookup-volume ZIPs not yet covered
   - Adds more data for known split ZIPs
   ```bash
   python3 run_targeted_comparison.py --workers 30 --input targeted_sample_74k_clean.json --output targeted_comparison_74k.json
   ```

2. **Run full verification** on all 7,693 disputed ZIPs (~$20 OpenAI cost, ~2 hours)
   ```bash
   python3 verify_provider_disputes.py --limit 7693 --output data/verified_disputes_full.json
   ```

### Integration
3. **Build canonical name mapping** from verified name variations
4. **Apply corrections** to lookup system for verified errors
5. **Integrate street-level rules** for split territory ZIPs
6. **Update SmartSelector prompt** with verified ambiguous ZIP guidance

### Ongoing
7. **Monitor user feedback** via Airtable for additional corrections
8. **Periodic re-verification** as utility territories change

---

## Key Insights

### Why 50% Disagreement Rate?
1. **Name variations** - Same company with different names in different sources
2. **Municipal utilities** - Small municipal utilities serve portions of ZIPs dominated by larger IOUs
3. **Boundary precision** - GIS boundaries may not perfectly align with actual service territories
4. **Data staleness** - Utility mergers/acquisitions not reflected in all sources

### Verification Approach
Rather than blindly trusting either source, we:
1. Identify disagreements between spreadsheet and API
2. Research each disputed ZIP using official utility territory information
3. Categorize as: name variation, split territory, or correction needed
4. Build verified rules from ground truth

---

## Cost Summary

| Resource | Cost |
|----------|------|
| Census geocoder | Free |
| Google geocoder fallback (~5%) | ~$12 for 50K run |
| OpenAI verification (20 ZIPs) | ~$0.50 |
| Full verification (7,693 ZIPs) | ~$20 estimated |

---

## Repository Structure

```
Utility Provider scrape/
├── data/
│   ├── electric_zip_corrections.json
│   ├── gas_zip_corrections.json
│   ├── water_zip_corrections.json
│   ├── smartselector_enhancement.json
│   ├── texas_tdu_mappings.json
│   ├── real_sub_zip_splits_50k.json
│   ├── sub_zip_provider_rules_50k.json
│   ├── verification_queue.json
│   ├── verified_disputes.json
│   └── verified_provider_rules.json
├── run_massive_comparison.py
├── run_targeted_comparison.py
├── verify_provider_disputes.py
├── utility_lookup_currently_deployed.py
└── PROVIDER_LOOKUP_REFINEMENT_STATUS.md
```
