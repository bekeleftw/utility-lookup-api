# Production Deployment Verification Checklist

## Summary
This checklist verifies that production has the latest code and data files to correctly return utility providers.

---

## Known Issues Fixed by Latest Deployment

### Issue 1: Yakima, WA Returns Wrong Water Provider ✅ FIXED
- **Symptom**: Returns "NOB HILL WATER ASSOCIATION" (EPA fallback)
- **Expected**: "YAKIMA WATER DIVISION CITY OF" (Washington DOH state API)
- **Fix**: Commit `151e3af` - Added state-specific water GIS APIs
- **Files Changed**: `gis_utility_lookup.py`

### Issue 2: Little Elm, TX Returns Wrong Gas Provider ✅ FIXED
- **Symptom**: Returns "Atmos Energy" (HIFLD federal data, wrong result)
- **Expected**: "CoServ Gas" (Municipal gas database, tenant-confirmed)
- **Fix**: Commit `8d3829c` - Added CoServ Gas for Denton County ZIP codes
- **Files Changed**: `data/municipal_utilities.json`

---

## Verification Tests

Run these commands on the production server to verify the deployment:

### Test 1: Water API - Yakima, WA
```bash
python3 -c "
from utility_lookup import lookup_utilities_by_address
result = lookup_utilities_by_address('123 S 2nd St, Yakima, WA 98901')
water = result.get('water') if result else None
if water:
    print(f'Water Provider: {water.get(\"NAME\")}')
    print(f'Source: {water.get(\"_verification_source\")}')
else:
    print('ERROR: No water result')
"
```

**Expected Output:**
```
Water Provider: Yakima Water Division City of
Source: washington_doh
```

**If fails (returns "NOB HILL WATER ASSOCIATION")**: Missing commit `151e3af`

---

### Test 2: Gas API - Little Elm, TX
```bash
python3 -c "
from utility_lookup import lookup_utilities_by_address
result = lookup_utilities_by_address('1401 Thrasher Dr, Little Elm, TX 75068')
gas = result.get('gas') if result else None
if gas:
    print(f'Gas Provider: {gas.get(\"NAME\")}')
    print(f'Source: {gas.get(\"_verification_source\")}')
else:
    print('ERROR: No gas result')
"
```

**Expected Output:**
```
Gas Provider: CoServ Gas
Source: municipal_gas_data
```

**If fails (returns "Atmos Energy")**: Missing commit `8d3829c` or data file not synced

---

### Test 3: Data File Integrity Check
```bash
python3 -c "
import json

# Check municipal_utilities.json has CoServ Gas
with open('data/municipal_utilities.json') as f:
    data = json.load(f)

coserv = data.get('gas', {}).get('TX', {}).get('Denton County CoServ', {})
has_zip = '75068' in coserv.get('zip_codes', [])

print(f'CoServ Gas entry exists: {bool(coserv)}')
print(f'ZIP 75068 included: {has_zip}')
print(f'CoServ name: {coserv.get(\"name\", \"NOT FOUND\")}')
"
```

**Expected Output:**
```
CoServ Gas entry exists: True
ZIP 75068 included: True
CoServ name: CoServ Gas
```

---

### Test 4: GIS API State Coverage
```bash
python3 test_gis_apis.py
```

**Expected Output:**
```
Water GIS states configured: 18
States: ['AR', 'AZ', 'CA', 'CT', 'DE', 'FL', 'KS', 'MS', 'NC', 'NJ', 'NM', 'NY', 'OK', 'PA', 'TN', 'TX', 'UT', 'WA']

WA (Yakima): YAKIMA WATER DIVISION CITY OF [source: washington_doh]
```

**If fails (WA not in list or returns NO RESULT)**: Missing commit `151e3af`

---

## Deployment Steps

1. **Pull latest code from GitHub**
   ```bash
   git pull origin main
   ```

2. **Verify current commit**
   ```bash
   git log --oneline -1
   ```
   Should be commit `c8f608e` or later (Jan 20, 2026)

3. **Check for uncommitted changes**
   ```bash
   git status
   ```
   Should show clean working directory

4. **Verify data files are present**
   ```bash
   ls -lh data/municipal_utilities.json
   ```
   Should be ~50KB or larger

5. **Run all verification tests** (see above)

6. **Test with real addresses**
   - Yakima, WA: `123 S 2nd St, Yakima, WA 98901`
   - Little Elm, TX: `1401 Thrasher Dr, Little Elm, TX 75068`

---

## Critical Commits Required

| Commit | Date | Description | Impact |
|--------|------|-------------|--------|
| `151e3af` | Jan 19, 2026 | Add state-specific water GIS APIs: WA, UT, TN, NC, NM | Fixes Yakima water lookup |
| `8d3829c` | Jan 20, 2026 | Add CoServ Gas for Denton County ZIP codes | Fixes Little Elm gas lookup |
| `c8f608e` | Jan 20, 2026 | Add deployment verification guide | Documentation |

---

## Rollback Procedure

If issues occur after deployment:

1. **Revert to previous stable commit**
   ```bash
   git log --oneline -10  # Find last stable commit
   git checkout <commit-hash>
   ```

2. **Restart services**
   ```bash
   # Restart Python processes or web server
   ```

3. **Verify rollback worked**
   ```bash
   git log --oneline -1
   ```

---

## Contact

For deployment issues, contact the development team with:
- Output from all verification tests
- Current commit hash (`git rev-parse HEAD`)
- Any error messages from logs
