# Utility Lookup Accuracy Improvements - Implementation Roadmap

## Overview

This folder contains implementation specs for improving utility provider accuracy. Each file is a standalone task that can be implemented independently.

## File Index

| File | Description | Estimated Effort |
|------|-------------|------------------|
| `01_USER_FEEDBACK_SYSTEM.md` | User correction submission and auto-confirmation | 4-6 hours |
| `02_CONFIDENCE_SCORING.md` | Numeric confidence scores with transparent factors | 3-4 hours |
| `03_PROBLEM_AREAS_REGISTRY.md` | Known problematic ZIPs/counties tracking | 2-3 hours |
| `04_SPECIAL_DISTRICTS_ALL_STATES.md` | MUD/CDD/PUD data sources for all 50 states | Reference doc |
| `05_SPECIAL_DISTRICT_IMPLEMENTATION.md` | Code to ingest and query special districts | 6-8 hours |
| `06_UTILITY_API_SCRAPERS.md` | Direct verification from utility company websites | 8-10 hours |
| `07_CROSS_VALIDATION.md` | Require multiple sources to agree | 3-4 hours |
| `08_BATCH_VALIDATION.md` | Monthly accuracy checks and reporting | 3-4 hours |

## Implementation Order

### Phase 1: Foundation (Do First)
1. `01_USER_FEEDBACK_SYSTEM.md` - Turns every lookup into potential data improvement
2. `03_PROBLEM_AREAS_REGISTRY.md` - Quick win, documents known issues
3. `02_CONFIDENCE_SCORING.md` - Better transparency for users

### Phase 2: Special Districts (High Impact)
4. `04_SPECIAL_DISTRICTS_ALL_STATES.md` - Reference for data sources
5. `05_SPECIAL_DISTRICT_IMPLEMENTATION.md` - Ingest and query logic

### Phase 3: Verification (Polish)
6. `06_UTILITY_API_SCRAPERS.md` - Direct utility company verification
7. `07_CROSS_VALIDATION.md` - Multiple source agreement
8. `08_BATCH_VALIDATION.md` - Ongoing accuracy monitoring

## Current State

### What's Working
- Electric: HIFLD + EIA + Texas TDU mapping + SERP verification
- Gas: HIFLD + State LDC database + Texas ZIP mapping + SERP verification
- Water: SERP-first + supplemental file + EPA SDWIS
- Internet: FCC Broadband Map via BrightData

### Known Gaps
- No special district data (MUDs, CDDs, etc.)
- No user feedback mechanism
- Confidence levels are vague ("high/medium/low")
- No tracking of problem areas
- No direct utility company verification
- No systematic accuracy monitoring

## Files Modified By These Specs

- `api.py` - New endpoints
- `utility_lookup.py` - Confidence scoring, special district priority
- `state_utility_verification.py` - Problem areas integration

## New Files Created By These Specs

```
/data/
  /special_districts/
    /raw/                    # Raw data from state agencies
    index.json               # State → available district types
    zip_to_district.json     # ZIP → [district_ids]
    subdivision_to_district.json
  /feedback/
    pending.json
    confirmed.json
  problem_areas.json
  validation_reports/
    2026-01/
      report.json

/scripts/
  ingest_special_districts.py
  validate_accuracy.py

utility_api_scrapers.py
special_districts.py
confidence_scoring.py
```

## How To Use These Specs

1. Open the relevant `.md` file
2. Read the CONTEXT section to understand the goal
3. Follow the IMPLEMENTATION section step by step
4. Test using the TESTING section
5. Commit with the suggested commit message

Each spec is designed to be completed in one session without dependencies on other specs (except where noted).
