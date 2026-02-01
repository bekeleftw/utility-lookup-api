# Utility Lookup API - Developer Handoff Guide

**Last Updated:** February 1, 2026

---

## Quick Start

```bash
# Clone the repo
git clone https://github.com/bekeleftw/utility-lookup-api.git
cd utility-lookup-api

# Install dependencies
pip install -r requirements.txt

# Run locally
python api.py
# API runs at http://localhost:5000

# Test it
curl "http://localhost:5000/api/lookup?address=123+Main+St,+Austin,+TX&utilities=electric,gas,water,sewer" \
  -H "X-API-Key: ulk_utilityprofit_master_2026_x7k9m2"
```

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         api.py (Flask)                          │
│  /api/lookup, /api/lookup/batch, /api/lookup/stream            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    utility_lookup_v1.py                         │
│  Main orchestrator - geocodes address, calls utility lookups    │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│ Electric/Gas  │   │    Water      │   │    Sewer      │
│ - EIA data    │   │ - EPA SDWIS   │   │ - State APIs  │
│ - State GIS   │   │ - Municipal   │   │ - HIFLD       │
│ - Municipal   │   │ - CSV         │   │ - CSV         │
└───────────────┘   └───────────────┘   └───────────────┘
```

---

## Key Files

| File | Purpose |
|------|---------|
| `api.py` | Flask API endpoints, request handling, response formatting |
| `utility_lookup_v1.py` | Main lookup orchestrator, geocoding, utility type routing |
| `sewer_lookup.py` | Sewer utility lookups (TX, CT, CA, FL, WA, NJ, MA) |
| `municipal_utilities.py` | City-owned utility database and lookups |
| `csv_utility_lookup.py` | CSV-based utility provider database |
| `logging_config.py` | Centralized logging configuration |
| `geocoding.py` | Address geocoding (Census, Google fallback) |

### Data Files

| File | Purpose |
|------|---------|
| `data/providers.csv` | Master utility provider database |
| `data/provider_match_cache.json` | Cached provider name matches |
| `data/municipal_utilities.json` | Municipal utility data |

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | Yes | - | For AI-powered provider matching |
| `GOOGLE_API_KEY` | No | - | Geocoding fallback (Census is primary) |
| `LOG_LEVEL` | No | `INFO` | DEBUG, INFO, WARNING, ERROR |
| `LOG_FORMAT` | No | console | Set to `json` for structured logs |
| `PORT` | No | `5000` | Server port |

---

## API Endpoints

### Single Address Lookup
```
GET /api/lookup?address=123+Main+St,+City,+ST&utilities=electric,gas,water,sewer
Header: X-API-Key: <api_key>
```

### Batch Lookup (up to 500 addresses)
```
POST /api/lookup/batch
Header: X-API-Key: <api_key>
Body: {
  "addresses": ["123 Main St, City, ST", ...],
  "utilities": "electric,gas,water"
}
```

### Streaming Lookup
```
GET /api/lookup/stream?address=...&utilities=...
Header: X-API-Key: <api_key>
```

---

## Utility Types

| Type | Sources (Priority Order) |
|------|--------------------------|
| `electric` | EIA → State GIS → Municipal → CSV |
| `gas` | State LDC mapping → Municipal → CSV |
| `water` | EPA SDWIS → Municipal → CSV |
| `sewer` | State APIs → CSV → HIFLD → Municipal inference |
| `trash` | CSV → Municipal inference |
| `internet` | FCC BDC → Playwright scraping (slow) |

---

## Sewer API Coverage

| State | API Source | Status |
|-------|-----------|--------|
| Texas | PUC Sewer CCN | ✅ Production |
| Connecticut | DEEP Connected Sewer | ✅ Production |
| California | Water Districts (proxy) | ✅ Production |
| Florida | DOH FLWMI | ✅ Production |
| Washington | WASWD Districts | ✅ Production |
| New Jersey | DEP SSA | ⚠️ Endpoint pending |
| Massachusetts | MassDEP WURP | ⚠️ Endpoint pending |

---

## Deployment

### Railway (Current)

Auto-deploys on push to `main` branch.

```bash
git push origin main  # Triggers deploy
```

**Dashboard:** https://railway.app/dashboard

**Production URL:** https://web-production-9acc6.up.railway.app

### Manual Deploy

```bash
# Railway CLI
railway up

# Or Docker
docker build -t utility-api .
docker run -p 5000:5000 utility-api
```

---

## Logging & Monitoring

**View logs in Railway:**
1. Dashboard → Project → Deployments → View Logs

**Log format:**
```
09:45:23 INFO     [api] Lookup request [address=123 Main St, utilities=sewer]
09:45:24 INFO     [api] Lookup completed [address=123 Main St, duration_ms=1234, state=TX]
09:45:25 ERROR    [sewer_lookup] TX Sewer CCN API error [endpoint=texas_puc_sewer_ccn, error=timeout]
```

**What to monitor:**
- `ERROR` logs = something broke
- `duration_ms` > 5000 = slow requests
- Repeated errors on same endpoint = external API down

---

## Testing

### Postman Collection
Import `postman_collection.json` for pre-configured API tests.

### Test Addresses
```bash
# Texas (sewer CCN)
curl "...?address=1000+N+Mays+St,+Round+Rock,+TX+78664&utilities=sewer"

# Connecticut (DEEP)
curl "...?address=165+Capitol+Ave,+Hartford,+CT+06106&utilities=sewer"

# California (water proxy)
curl "...?address=500+Castro+St,+San+Francisco,+CA+94114&utilities=sewer"
```

---

## Common Issues

### "Could not geocode address"
- Address format issue - try standardizing (123 Main St, City, ST 12345)
- Census geocoder down - check https://geocoding.geo.census.gov/

### Slow responses (>10s)
- Internet lookup uses Playwright (browser automation) - disable with `utilities=electric,gas,water`
- External GIS API slow - check state API status

### Missing utility data
- Check if state has GIS API coverage (see SEWER_API_STATUS.md)
- Fallback to CSV/municipal inference may not have data for that city

---

## Adding New State Sewer APIs

1. Find the ArcGIS FeatureServer endpoint
2. Test with curl:
   ```bash
   curl "https://...FeatureServer/0/query?geometry=-122,47&geometryType=esriGeometryPoint&inSR=4326&outFields=*&f=json"
   ```
3. Add endpoint constant to `sewer_lookup.py`
4. Create `lookup_<state>_<source>()` function
5. Add to `lookup_sewer_provider()` state routing
6. Test and deploy

---

## Key Contacts

| Role | Contact |
|------|---------|
| Project Owner | Mark Lindquist |
| Technical Advisor | Darius |
| GitHub Repo | https://github.com/bekeleftw/utility-lookup-api |

---

## Related Documentation

- `CODEBASE_OVERVIEW.md` - Detailed module descriptions
- `SEWER_API_STATUS.md` - Sewer API implementation status
- `GIS_API_STATUS_SUMMARY.md` - Electric/gas GIS coverage
- `postman_collection.json` - API test collection

---

## TODO / Known Issues

1. **NJ/MA sewer endpoints** - Added but returning "Invalid URL" - may need auth
2. **FL FLWMI** - Requires parcel-level precision, point queries often miss
3. **Internet lookup** - Slow (Playwright) - consider caching or async
4. **Rate limiting** - Currently basic, may need Redis for production scale
