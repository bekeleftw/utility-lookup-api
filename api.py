#!/usr/bin/env python3
"""
Flask API for Utility Lookup
Run with: python api.py
"""

from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from concurrent.futures import ThreadPoolExecutor, as_completed
from utility_lookup_v1 import lookup_utilities_by_address, lookup_utility_json, lookup_electric_only, lookup_gas_only, lookup_water_only, lookup_internet_only, geocode_address

# Resident Guide feature
from guide.guide_api import guide_bp, set_db_connection as set_guide_db_connection
from state_utility_verification import check_problem_area, add_problem_area, load_problem_areas
from special_districts import lookup_special_district, format_district_for_response, get_available_states, has_special_district_data
from utility_scrapers import get_available_scrapers, get_scrapers_for_state, verify_with_utility_api_sync
from cross_validation import cross_validate, SourceResult, format_for_response as format_cv_response, get_disagreements, providers_match
from municipal_utilities import get_all_municipal_utilities, lookup_municipal_electric, get_municipal_stats
from address_cache import cache_confirmation, get_cached_utilities, get_cache_stats
from provider_id_matcher import get_provider_id, match_provider

# Load service check URLs
_service_check_urls = None
def get_service_check_url(utility_name: str) -> str:
    """Get the service check/verification URL for a utility."""
    global _service_check_urls
    if _service_check_urls is None:
        try:
            import json
            from pathlib import Path
            urls_file = Path(__file__).parent / 'data' / 'service_check_urls.json'
            if urls_file.exists():
                with open(urls_file, 'r') as f:
                    data = json.load(f)
                    _service_check_urls = data.get('urls', {})
            else:
                _service_check_urls = {}
        except Exception:
            _service_check_urls = {}
    
    if not utility_name:
        return None
    
    # Try exact match first
    if utility_name in _service_check_urls:
        return _service_check_urls[utility_name]
    
    # Try case-insensitive match
    name_lower = utility_name.lower()
    for key, url in _service_check_urls.items():
        if key.lower() == name_lower:
            return url
    
    # Try partial match (utility name contains key or vice versa)
    for key, url in _service_check_urls.items():
        if key.lower() in name_lower or name_lower in key.lower():
            return url
    
    return None
from datetime import datetime
from functools import wraps
import hashlib
import json
import os
import re
import secrets
import time
from functools import lru_cache

from logging_config import get_logger
logger = get_logger("api")

# Simple in-memory cache for address lookups (TTL: 1 hour)
_address_cache = {}
_cache_ttl = 3600  # 1 hour

def get_cached_result(address, utilities_key):
    """Get cached result if not expired."""
    cache_key = f"{address}|{utilities_key}"
    if cache_key in _address_cache:
        result, timestamp = _address_cache[cache_key]
        if time.time() - timestamp < _cache_ttl:
            return result
        else:
            del _address_cache[cache_key]
    return None

def set_cached_result(address, utilities_key, result):
    """Cache a result."""
    cache_key = f"{address}|{utilities_key}"
    _address_cache[cache_key] = (result, time.time())
    # Limit cache size to 10000 entries
    if len(_address_cache) > 10000:
        # Remove oldest entries
        sorted_keys = sorted(_address_cache.keys(), key=lambda k: _address_cache[k][1])
        for k in sorted_keys[:1000]:
            del _address_cache[k]

# Feedback storage
FEEDBACK_DIR = os.path.join(os.path.dirname(__file__), 'data', 'feedback')

# API Keys storage
API_KEYS_FILE = os.path.join(os.path.dirname(__file__), 'data', 'api_keys.json')

def load_api_keys():
    """Load API keys from file."""
    if os.path.exists(API_KEYS_FILE):
        with open(API_KEYS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_api_keys(keys):
    """Save API keys to file."""
    os.makedirs(os.path.dirname(API_KEYS_FILE), exist_ok=True)
    with open(API_KEYS_FILE, 'w') as f:
        json.dump(keys, f, indent=2)

def validate_api_key(api_key):
    """Validate an API key and return the associated metadata."""
    # Check master API key from environment variable first (survives deploys)
    master_key = os.getenv('MASTER_API_KEY')
    if master_key and api_key == master_key:
        return {
            'name': 'Master API Key',
            'active': True,
            'is_master': True
        }
    
    # Check file-based keys
    keys = load_api_keys()
    if api_key in keys:
        key_data = keys[api_key]
        if key_data.get('active', True):
            # Update last used timestamp
            key_data['last_used'] = datetime.utcnow().isoformat()
            key_data['usage_count'] = key_data.get('usage_count', 0) + 1
            save_api_keys(keys)
            return key_data
    return None

def require_api_key(f):
    """Decorator to require API key for endpoint access."""
    @wraps(f)
    def decorated(*args, **kwargs):
        # Check for API key in header or query param
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        
        # If no API key, allow access (for web widget which uses session auth)
        # But if API key is provided, validate it
        if api_key:
            key_data = validate_api_key(api_key)
            if not key_data:
                return jsonify({'error': 'Invalid or inactive API key'}), 401
            request.api_key_data = key_data
        else:
            request.api_key_data = None
        
        return f(*args, **kwargs)
    return decorated

def load_feedback(filename):
    filepath = os.path.join(FEEDBACK_DIR, filename)
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            return json.load(f)
    return {}

def save_feedback(filename, data):
    filepath = os.path.join(FEEDBACK_DIR, filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)

def extract_zip(address):
    """Extract ZIP code from address string."""
    match = re.search(r'\b(\d{5})(?:-\d{4})?\b', address)
    return match.group(1) if match else None

def extract_city_state(address):
    """Extract city and state from address string."""
    match = re.search(r',\s*([A-Za-z\s]+),\s*([A-Z]{2})\s*\d{5}', address)
    if match:
        return match.group(1).strip().upper(), match.group(2).upper()
    return None, None

app = Flask(__name__, static_folder='static', static_url_path='/static')
CORS(app)  # Allow cross-origin requests from Webflow

# Serve static files from /public (for leadgen JS)
from flask import send_from_directory
@app.route('/js/<path:filename>')
def serve_js(filename):
    return send_from_directory(os.path.join(os.path.dirname(__file__), 'public', 'js'), filename)

# Register Resident Guide Blueprint
app.register_blueprint(guide_bp)

# Register Utility Auth Blueprint
try:
    from utility_auth import utility_auth_bp
    app.register_blueprint(utility_auth_bp)
    print("[API] Utility auth blueprint registered successfully")
except Exception as e:
    print(f"[API] Failed to register utility auth blueprint: {e}")

# Set up database connection for guide feature (uses separate GUIDE_DATABASE_URL)
GUIDE_DATABASE_URL = os.getenv('GUIDE_DATABASE_URL')
if GUIDE_DATABASE_URL:
    try:
        import psycopg2
        guide_db_conn = psycopg2.connect(GUIDE_DATABASE_URL)
        set_guide_db_connection(guide_db_conn)
    except Exception as e:
        print(f"Warning: Could not connect to database for guide feature: {e}")

# Rate limiting disabled - internal use only
# limiter = Limiter(
#     get_remote_address,
#     app=app,
#     default_limits=["500 per day"],
#     storage_uri="memory://",
#     strategy="fixed-window"
# )
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],  # No limits
    storage_uri="memory://",
    enabled=False  # Disable rate limiting entirely
)

# Custom error handler for rate limit exceeded
@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({
        'error': 'Rate limit exceeded',
        'message': 'You have exceeded the limit of 500 lookups per 24 hours. Please try again tomorrow.',
        'retry_after': e.description
    }), 429

@app.route('/api/version')
def version():
    return jsonify({'version': '2026-01-31-v36', 'changes': 'batch_endpoint_with_caching'})

# ============ API Key Management ============

@app.route('/api/keys/generate', methods=['POST'])
def generate_api_key():
    """Generate a new API key. Requires admin secret."""
    data = request.get_json() or {}
    admin_secret = data.get('admin_secret') or request.headers.get('X-Admin-Secret')
    
    # Verify admin secret (set via environment variable)
    expected_secret = os.getenv('ADMIN_SECRET', 'utility-admin-2026')
    if admin_secret != expected_secret:
        return jsonify({'error': 'Unauthorized'}), 401
    
    # Generate new API key
    api_key = 'ulk_' + secrets.token_hex(24)  # ulk = utility lookup key
    
    keys = load_api_keys()
    keys[api_key] = {
        'name': data.get('name', 'Unnamed Key'),
        'created_at': datetime.utcnow().isoformat(),
        'created_by': data.get('created_by', 'admin'),
        'active': True,
        'usage_count': 0,
        'last_used': None
    }
    save_api_keys(keys)
    
    return jsonify({
        'api_key': api_key,
        'name': keys[api_key]['name'],
        'message': 'Store this key securely - it cannot be retrieved later'
    })

@app.route('/api/keys', methods=['GET'])
def list_api_keys():
    """List all API keys (without revealing full keys). Requires admin secret."""
    admin_secret = request.headers.get('X-Admin-Secret')
    expected_secret = os.getenv('ADMIN_SECRET', 'utility-admin-2026')
    if admin_secret != expected_secret:
        return jsonify({'error': 'Unauthorized'}), 401
    
    keys = load_api_keys()
    # Return masked keys
    masked = []
    for key, data in keys.items():
        masked.append({
            'key_prefix': key[:12] + '...',
            'name': data.get('name'),
            'created_at': data.get('created_at'),
            'active': data.get('active', True),
            'usage_count': data.get('usage_count', 0),
            'last_used': data.get('last_used')
        })
    return jsonify({'keys': masked})

@app.route('/api/keys/revoke', methods=['POST'])
def revoke_api_key():
    """Revoke an API key. Requires admin secret."""
    data = request.get_json() or {}
    admin_secret = data.get('admin_secret') or request.headers.get('X-Admin-Secret')
    expected_secret = os.getenv('ADMIN_SECRET', 'utility-admin-2026')
    if admin_secret != expected_secret:
        return jsonify({'error': 'Unauthorized'}), 401
    
    api_key = data.get('api_key')
    if not api_key:
        return jsonify({'error': 'api_key required'}), 400
    
    keys = load_api_keys()
    if api_key in keys:
        keys[api_key]['active'] = False
        save_api_keys(keys)
        return jsonify({'message': 'API key revoked'})
    return jsonify({'error': 'API key not found'}), 404

# ============ Batch Lookup Endpoint ============

@app.route('/api/lookup/batch', methods=['POST'])
@require_api_key
def lookup_batch():
    """
    Batch lookup - process multiple addresses in parallel.
    Optimized for high-volume requests (hundreds of addresses).
    
    Request body:
    {
        "addresses": ["123 Main St, Austin TX", "456 Oak Ave, Dallas TX", ...],
        "utilities": "electric,gas,water"  // optional, default: electric,gas,water
    }
    
    Response:
    {
        "results": [
            {"address": "123 Main St, Austin TX", "utilities": {...}, "status": "success"},
            {"address": "456 Oak Ave, Dallas TX", "utilities": {...}, "status": "success"},
            ...
        ],
        "summary": {"total": 100, "success": 98, "failed": 2}
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body required'}), 400
    
    addresses = data.get('addresses', [])
    if not addresses:
        return jsonify({'error': 'addresses array required'}), 400
    
    if len(addresses) > 500:
        return jsonify({'error': 'Maximum 500 addresses per batch'}), 400
    
    utilities_param = data.get('utilities', 'electric,gas,water')
    selected_utilities = [u.strip().lower() for u in utilities_param.split(',')]
    
    utilities_key = ','.join(sorted(selected_utilities))
    
    def process_single_address(address):
        """Process a single address and return result."""
        try:
            # Check cache first
            cached = get_cached_result(address, utilities_key)
            if cached:
                cached['_cached'] = True
                return cached
            
            result = lookup_utilities_by_address(
                address, 
                verify_with_serp=False, 
                selected_utilities=selected_utilities
            )
            if not result:
                return {'address': address, 'status': 'error', 'error': 'Could not geocode'}
            
            geocoded = result.get('_geocoded', {})
            city = geocoded.get('city')
            state = geocoded.get('state')
            
            utilities = {}
            
            if 'electric' in selected_utilities and result.get('electric'):
                electric = result['electric']
                if isinstance(electric, list):
                    utilities['electric'] = [format_utility(e, 'electric', city, state) for e in electric]
                else:
                    utilities['electric'] = [format_utility(electric, 'electric', city, state)]
            
            if 'gas' in selected_utilities and result.get('gas'):
                gas = result['gas']
                if isinstance(gas, list):
                    utilities['gas'] = [format_utility(g, 'gas', city, state) for g in gas]
                else:
                    utilities['gas'] = [format_utility(gas, 'gas', city, state)]
            
            if 'water' in selected_utilities and result.get('water'):
                water = result['water']
                if isinstance(water, list):
                    utilities['water'] = [format_utility(w, 'water', city, state) for w in water]
                else:
                    utilities['water'] = [format_utility(water, 'water', city, state)]
            
            if 'internet' in selected_utilities and result.get('internet'):
                utilities['internet'] = result['internet']
            
            if 'trash' in selected_utilities and result.get('trash'):
                trash = result['trash']
                if isinstance(trash, list):
                    utilities['trash'] = [format_utility(t, 'trash', city, state) for t in trash]
                else:
                    utilities['trash'] = [format_utility(trash, 'trash', city, state)]
            
            if 'sewer' in selected_utilities and result.get('sewer'):
                sewer = result['sewer']
                if isinstance(sewer, list):
                    utilities['sewer'] = [format_utility(s, 'sewer', city, state) for s in sewer]
                else:
                    utilities['sewer'] = [format_utility(sewer, 'sewer', city, state)]
            
            response = {
                'address': address,
                'location': result.get('location', {}),
                'utilities': utilities,
                'status': 'success'
            }
            
            # Cache the result
            set_cached_result(address, utilities_key, response)
            
            return response
        except Exception as e:
            return {'address': address, 'status': 'error', 'error': str(e)}
    
    # Process in parallel with ThreadPoolExecutor
    results = []
    max_workers = min(50, len(addresses))  # Cap at 50 concurrent workers
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_addr = {executor.submit(process_single_address, addr): addr for addr in addresses}
        for future in as_completed(future_to_addr):
            results.append(future.result())
    
    # Sort results to match input order
    addr_to_result = {r['address']: r for r in results}
    ordered_results = [addr_to_result.get(addr, {'address': addr, 'status': 'error', 'error': 'Not processed'}) for addr in addresses]
    
    success_count = sum(1 for r in ordered_results if r['status'] == 'success')
    
    return jsonify({
        'results': ordered_results,
        'summary': {
            'total': len(addresses),
            'success': success_count,
            'failed': len(addresses) - success_count
        }
    })

@app.route('/api/lookup', methods=['GET', 'POST'])
@require_api_key
def lookup():
    """Look up utilities for an address."""
    if request.method == 'POST':
        data = request.get_json()
        address = data.get('address')
        # SERP verification disabled by default - should_skip_serp handles confidence-based verification
        verify = data.get('verify', False)
        # Parse utilities parameter - default excludes internet (slow Playwright)
        utilities_param = data.get('utilities', 'electric,gas,water')
    else:
        address = request.args.get('address')
        # SERP verification disabled by default - should_skip_serp handles confidence-based verification
        verify = request.args.get('verify', 'false').lower() == 'true'
        # Parse utilities parameter - default excludes internet (slow Playwright)
        utilities_param = request.args.get('utilities', 'electric,gas,water')
    
    # Parse comma-separated utilities into list
    selected_utilities = [u.strip().lower() for u in utilities_param.split(',')]
    
    if not address:
        logger.warning("Lookup request missing address")
        return jsonify({'error': 'Address is required'}), 400
    
    try:
        start_time = time.time()
        logger.info("Lookup request", extra={"address": address, "utilities": utilities_param})
        result = lookup_utilities_by_address(address, verify_with_serp=verify, selected_utilities=selected_utilities)
        if not result:
            return jsonify({'error': 'Could not geocode address'}), 404
        
        # Format response
        response = {
            'address': address,
            'location': result.get('location', {}),
            'utilities': {}
        }
        
        # Extract city/state for service check URL lookup
        geocoded = result.get('_geocoded', {})
        city = geocoded.get('city')
        state = geocoded.get('state')
        
        # Electric - only if selected
        if 'electric' in selected_utilities:
            electric = result.get('electric')
            if electric:
                if isinstance(electric, list):
                    response['utilities']['electric'] = [format_utility(e, 'electric', city, state) for e in electric]
                    primary = electric[0]
                else:
                    response['utilities']['electric'] = [format_utility(electric, 'electric', city, state)]
                    primary = electric
                
                # Build electric note with verification info
                primary_name = primary.get('NAME', 'Unknown')
                confidence = primary.get('_confidence', 'medium')
                selection_reason = primary.get('_selection_reason', '')
                verification_source = primary.get('_verification_source', '')
                is_deregulated = primary.get('_is_deregulated')
                
                # Get alternative names
                others = electric[1:] if isinstance(electric, list) and len(electric) > 1 else []
                other_names = [e.get('NAME', 'Unknown') for e in others]
                
                if confidence == 'verified':
                    note = f"✓ Verified: {primary_name}."
                    if selection_reason:
                        note += f" {selection_reason}"
                elif confidence == 'high':
                    note = f"{primary_name} (high confidence)."
                    if selection_reason:
                        note += f" {selection_reason}"
                else:
                    note = f"Most likely: {primary_name}."
                    if selection_reason:
                        note += f" {selection_reason}"
                
                if other_names:
                    note += f" Other territories in area: {', '.join(other_names)}."
                
                if is_deregulated is True:
                    note += " This is a deregulated market - you can choose your electricity supplier."
                elif is_deregulated is False:
                    note += " This utility is not in the deregulated market."
                
                response['utilities']['electric_note'] = note
                response['utilities']['electric_confidence'] = confidence
                if verification_source:
                    response['utilities']['electric_source'] = verification_source
        
        # Gas - only if selected
        if 'gas' in selected_utilities:
            gas = result.get('gas')
            gas_no_service = result.get('gas_no_service')
            
            if gas:
                if isinstance(gas, list):
                    response['utilities']['gas'] = [format_utility(g, 'gas', city, state) for g in gas]
                    primary = gas[0]
                else:
                    response['utilities']['gas'] = [format_utility(gas, 'gas', city, state)]
                    primary = gas
                
                # Build gas note with verification info
                primary_name = primary.get('NAME', 'Unknown')
                confidence = primary.get('_confidence', 'medium')
                selection_reason = primary.get('_selection_reason', '')
                verification_source = primary.get('_verification_source', '')
                
                # Get alternative names
                others = gas[1:] if isinstance(gas, list) and len(gas) > 1 else []
                other_names = [g.get('NAME', 'Unknown') for g in others]
                
                if confidence == 'verified':
                    note = f"✓ Verified: {primary_name}."
                    if selection_reason:
                        note += f" {selection_reason}"
                elif confidence == 'high':
                    note = f"{primary_name} (high confidence)."
                    if selection_reason:
                        note += f" {selection_reason}"
                else:
                    note = f"Most likely: {primary_name}."
                    if selection_reason:
                        note += f" {selection_reason}"
                
                if other_names:
                    note += f" Other providers in area: {', '.join(other_names)}."
                
                response['utilities']['gas_note'] = note
                response['utilities']['gas_confidence'] = confidence
                if verification_source:
                    response['utilities']['gas_source'] = verification_source
            elif gas_no_service:
                response['utilities']['gas_note'] = gas_no_service
            else:
                response['utilities']['gas_note'] = "No piped natural gas provider found. This area may use propane or have no gas service."
        
        # Water - only if selected
        if 'water' in selected_utilities:
            water = result.get('water')
            if water:
                response['utilities']['water'] = [format_utility(water, 'water', city, state)]
                w = water
                if w.get('_confidence') == 'medium':
                    response['utilities']['water_note'] = f"Matched by county - multiple water systems serve this area. {w.get('_note', '')}"
                elif w.get('_confidence') == 'low':
                    response['utilities']['water_note'] = w.get('_note', 'Estimated based on city name - verify with local utility.')
        
        # Internet - only if selected (call lookup_internet_only directly)
        if 'internet' in selected_utilities:
            internet = lookup_internet_only(address)
            if internet and internet.get('providers'):
                response['utilities']['internet'] = format_internet_providers(internet)
                if internet.get('has_fiber'):
                    response['utilities']['internet_note'] = f"Fiber available from {internet.get('best_wired', {}).get('name', 'provider')}."
                elif internet.get('has_cable'):
                    response['utilities']['internet_note'] = "Cable internet available. No fiber service found at this address."
                else:
                    response['utilities']['internet_note'] = "Limited wired options. DSL, fixed wireless, or satellite may be available."
            else:
                response['utilities']['internet_note'] = "Could not retrieve internet provider data from FCC."
        
        # Trash - only if selected
        if 'trash' in selected_utilities:
            trash = result.get('trash')
            if trash:
                response['utilities']['trash'] = [format_utility(trash, 'trash', city, state)]
        
        # Sewer - only if selected
        if 'sewer' in selected_utilities:
            sewer = result.get('sewer')
            if sewer:
                response['utilities']['sewer'] = [format_utility(sewer, 'sewer', city, state)]
        
        duration_ms = int((time.time() - start_time) * 1000)
        logger.info("Lookup completed", extra={"address": address, "duration_ms": duration_ms, "state": state})
        return jsonify(response)
        
    except Exception as e:
        logger.error("Lookup failed", extra={"address": address, "error": str(e)})
        return jsonify({'error': str(e)}), 500


def format_utility(util, util_type, city=None, state=None):
    """Format utility data for API response."""
    from name_normalizer import normalize_utility_name
    from browser_verification import find_utility_website
    
    # Blocklist of non-utility websites that should never be returned
    BLOCKED_WEBSITE_DOMAINS = [
        'mapquest.com', 'yelp.com', 'yellowpages.com', 'whitepages.com',
        'facebook.com', 'twitter.com', 'linkedin.com', 'instagram.com',
        'bbb.org', 'manta.com', 'chamberofcommerce.com', 'bizapedia.com',
        'opencorporates.com', 'dnb.com', 'zoominfo.com', 'crunchbase.com',
        'wikipedia.org', 'ncbi.nlm.nih.gov', 'indeed.com', 'glassdoor.com',
        'google.com', 'bing.com', 'yahoo.com', 'reddit.com',
    ]
    
    def is_blocked_website(url):
        if not url:
            return False
        url_lower = url.lower()
        return any(domain in url_lower for domain in BLOCKED_WEBSITE_DOMAINS)
    
    # Get raw name and normalize it
    raw_name = util.get('NAME', util.get('name', 'Unknown'))
    normalized_name = normalize_utility_name(raw_name)
    
    # Get existing website and filter blocked domains
    website = util.get('WEBSITE', util.get('website'))
    if is_blocked_website(website):
        website = None
    
    # If no website, try to find one via SERP
    if (not website or website in ['NOT AVAILABLE', '', None]) and normalized_name:
        try:
            found_website = find_utility_website(
                normalized_name,
                state or util.get('STATE', util.get('state'))
            )
            if found_website:
                website = found_website
        except Exception:
            pass  # Don't fail if website lookup fails
    
    if util_type == 'water':
        util_state = util.get('STATE', util.get('state'))
        provider_id = get_provider_id(normalized_name, 'water', util_state)
        return {
            'name': normalized_name,
            'phone': util.get('TELEPHONE', util.get('phone')),
            'website': website,
            'address': util.get('ADDRESS', util.get('address')),
            'city': util.get('CITY', util.get('city')),
            'state': util.get('STATE', util.get('state')),
            'zip': util.get('ZIP', util.get('zip')),
            'id': util.get('PWSID', util.get('id')),
            'provider_id': provider_id,
            'population_served': util.get('POPULATION_SERVED', util.get('population_served')),
            'source_type': util.get('SOURCE_TYPE', util.get('source_type')),
            'confidence': util.get('_confidence', 'high'),
            'confidence_score': util.get('_confidence_score') or util.get('confidence_score'),
            'confidence_factors': util.get('confidence_factors'),
            'verified': util.get('_serp_verified', False),
            '_source': util.get('_source') or util.get('_verification_source') or util.get('source')
        }
    
    # Sewer utilities - include CCN info for Texas
    if util_type == 'sewer':
        util_state = util.get('STATE', util.get('state'))
        provider_id = get_provider_id(normalized_name, 'sewer', util_state)
        return {
            'name': normalized_name,
            'phone': util.get('TELEPHONE', util.get('phone')),
            'website': website,
            'address': util.get('ADDRESS', util.get('address')),
            'city': util.get('CITY', util.get('city')),
            'state': util.get('STATE', util.get('state')),
            'zip': util.get('ZIP', util.get('zip')),
            'id': util.get('id'),
            'provider_id': provider_id,
            'ccn_number': util.get('ccn_number'),  # Texas PUC CCN
            'confidence': util.get('_confidence', 'medium'),
            'confidence_score': util.get('_confidence_score') or util.get('confidence_score'),
            'confidence_factors': util.get('confidence_factors'),
            'verified': util.get('_serp_verified', False),
            '_source': util.get('_source') or util.get('source'),
            '_note': util.get('_note')
        }
    
    # Trash utilities
    if util_type == 'trash':
        util_state = util.get('STATE', util.get('state'))
        provider_id = get_provider_id(normalized_name, 'trash', util_state)
        return {
            'name': normalized_name,
            'phone': util.get('TELEPHONE', util.get('phone')),
            'website': website,
            'address': util.get('ADDRESS', util.get('address')),
            'city': util.get('CITY', util.get('city')),
            'state': util.get('STATE', util.get('state')),
            'zip': util.get('ZIP', util.get('zip')),
            'id': util.get('id'),
            'provider_id': provider_id,
            'confidence': util.get('_confidence', 'medium'),
            'confidence_score': util.get('_confidence_score') or util.get('confidence_score'),
            'verified': util.get('_serp_verified', False),
            '_source': util.get('_source') or util.get('source'),
            '_note': util.get('_note')
        }
    
    # Electric and Gas utilities
    confidence = util.get('_confidence') or util.get('confidence') or ('high' if util_type == 'electric' else 'medium')
    confidence_score = util.get('_confidence_score') or util.get('confidence_score')
    
    # Known municipal utilities with exclusive territory - these are 100% certain
    EXCLUSIVE_MUNICIPAL_UTILITIES = {
        'austin energy', 'cps energy', 'ladwp', 'los angeles department of water and power',
        'seattle city light', 'sacramento municipal utility district', 'smud',
        'austin water', 'san antonio water system', 'ouc', 'orlando utilities commission',
        'jea', 'lpnt', 'lubbock power & light', 'garland power & light', 'new braunfels utilities',
        'texas gas service', 'atmos energy', 'centerpoint energy'
    }
    
    name_lower = (normalized_name or '').lower()
    is_exclusive_municipal = any(muni in name_lower for muni in EXCLUSIVE_MUNICIPAL_UTILITIES)
    
    # Ensure confidence_score matches confidence level for proper frontend display
    # Frontend uses score >= 85 for "Verified", >= 70 for "High"
    if is_exclusive_municipal:
        confidence_score = 98
        confidence = 'verified'
    elif confidence_score is None or confidence_score < 50:
        if confidence == 'verified':
            confidence_score = 95
        elif confidence == 'high':
            confidence_score = 85
        elif confidence == 'medium':
            confidence_score = 60
    
    # Match to provider ID from utility_providers_IDs.csv
    util_state = util.get('STATE', util.get('state'))
    provider_id = get_provider_id(normalized_name, util_type, util_state)
    
    # Get service check URL for this utility
    service_check_url = get_service_check_url(normalized_name)
    
    result = {
        'name': normalized_name,
        'phone': util.get('TELEPHONE', util.get('phone')),
        'website': website,
        'service_check_url': service_check_url,
        'address': util.get('ADDRESS', util.get('address')),
        'city': util.get('CITY', util.get('city')),
        'state': util.get('STATE', util.get('state')),
        'zip': util.get('ZIP', util.get('zip')),
        'id': util.get('ID') or util.get('SVCTERID') or util.get('id'),
        'provider_id': provider_id,
        'type': util.get('TYPE'),
        'confidence': confidence,
        'confidence_score': confidence_score,
        'confidence_factors': util.get('confidence_factors'),
        'verified': util.get('_serp_verified', False),
        '_source': util.get('_source') or util.get('_verification_source') or util.get('source'),
        'other_providers': util.get('_other_providers')
    }
    
    # Add deregulated market info for electric utilities
    # Check both the flag AND the state directly as fallback
    from deregulated_markets import is_deregulated_state, get_deregulated_market_info
    state = util.get('STATE') or util.get('state')
    
    # Check if this is a municipal utility or co-op (exempt from deregulation)
    # These utilities are in deregulated states but customers cannot choose their provider
    name_lower = normalized_name.lower() if normalized_name else ''
    
    # Specific exempt utilities
    exempt_utilities = [
        # Texas municipal utilities
        'austin energy', 'cps energy', 'garland power', 'lubbock power', 
        'new braunfels utilities', 'georgetown utility', 'greenville electric',
        'brownsville public', 'bryan texas utilities', 'college station utilities',
        'kerrville public', 'seguin electric', 'boerne utilities', 'fredericksburg electric',
        # Ohio municipal utilities
        'cleveland public power', 'american municipal power', 'amp ohio',
        # Illinois municipal utilities  
        'springfield city water', 'cwlp',
        # New York - LIPA operates differently
        'long island power', 'lipa', 'pseg long island',
        # Pennsylvania municipal utilities
        'lansdale borough',
    ]
    
    # Generic patterns that indicate exempt utilities
    exempt_patterns = [
        'cooperative', 'co-op', 'coop', 'electric co-op',  # Electric cooperatives
        'municipal', 'city of', 'city utilities', 'city light', 'city power',
        'public power', 'public utility', 'pud',  # Public utility districts
        'rural electric', 'rec', 'emc',  # Rural electric cooperatives
    ]
    
    is_exempt = (
        any(exempt in name_lower for exempt in exempt_utilities) or
        any(pattern in name_lower for pattern in exempt_patterns)
    )
    
    # Deregulated if flag is set OR state is deregulated (but NOT if exempt utility)
    is_dereg = util.get('_deregulated_market') or (state and is_deregulated_state(state) and not is_exempt)
    
    if util_type == 'electric' and is_dereg:
        # Get market info from util or fetch it
        market_info = util.get('_market_info') or (get_deregulated_market_info(state) if state else {})
        result['deregulated'] = {
            'is_deregulated': True,
            'has_choice': True,
            'message': "You have options! You can choose your electricity provider.",
            'provider_role': util.get('_role', 'TDU (infrastructure owner)'),
            'explanation': util.get('_note', f"{normalized_name} delivers the electricity, but you choose who you buy it from."),
            'choice_website': market_info.get('choice_website'),
            'choice_website_name': _get_choice_website_name(market_info.get('choice_website')),
            'how_it_works': f"{normalized_name} owns the power lines and meters. You choose a retail provider ({market_info.get('rep_term', 'supplier')}) who sells you electricity."
        }
    elif util_type == 'electric':
        # Explicitly mark as NOT deregulated so UI knows
        result['deregulated'] = {
            'is_deregulated': False,
            'has_choice': False,
            'message': None
        }
    
    return result


def _get_choice_website_name(url):
    """Get friendly name for choice website."""
    if not url:
        return None
    website_names = {
        'powertochoose.org': 'Power to Choose (Texas)',
        'papowerswitch.com': 'PA Power Switch',
        'energychoice.ohio.gov': 'Energy Choice Ohio',
        'pluginillinois.org': 'Plug In Illinois',
        'askpsc.com': 'NY Public Service Commission',
        'mdelectricchoice.com': 'MD Electric Choice',
        'energizect.com': 'Energize CT',
    }
    for domain, name in website_names.items():
        if domain in url.lower():
            return name
    return 'Compare Providers'


def format_internet_providers(internet_data):
    """Format internet provider data for API response."""
    if not internet_data:
        return []
    
    providers = internet_data.get('providers', [])
    formatted = []
    
    for p in providers:
        formatted.append({
            'name': p.get('name'),
            'technology': p.get('technology'),
            'technology_code': p.get('technology_code'),
            'max_download_mbps': p.get('max_download_mbps'),
            'max_upload_mbps': p.get('max_upload_mbps'),
            'low_latency': p.get('low_latency'),
            'holding_company': p.get('holding_company'),
        })
    
    # Add summary info at the start
    result = {
        'providers': formatted,
        'provider_count': internet_data.get('provider_count', 0),
        'has_fiber': internet_data.get('has_fiber', False),
        'has_cable': internet_data.get('has_cable', False),
        'best_wired': None,
        'best_wireless': None,
        'fcc_location_id': internet_data.get('location_id'),
    }
    
    # Add best options
    if internet_data.get('best_wired'):
        bw = internet_data['best_wired']
        result['best_wired'] = {
            'name': bw.get('name'),
            'technology': bw.get('technology'),
            'max_download_mbps': bw.get('max_download_mbps'),
            'max_upload_mbps': bw.get('max_upload_mbps'),
        }
    
    if internet_data.get('best_wireless'):
        bwl = internet_data['best_wireless']
        result['best_wireless'] = {
            'name': bwl.get('name'),
            'technology': bwl.get('technology'),
            'max_download_mbps': bwl.get('max_download_mbps'),
            'max_upload_mbps': bwl.get('max_upload_mbps'),
        }
    
    return result


@app.route('/api/health', methods=['GET'])
@limiter.exempt
def health():
    """Health check endpoint."""
    return jsonify({'status': 'ok', 'version': '2026-01-21-dereg-v7'})


@app.route('/api/rate-limit', methods=['GET'])
@limiter.exempt
def rate_limit_status():
    """Check current rate limit status for the requesting IP."""
    # This endpoint is exempt from rate limiting
    return jsonify({
        'limit': '500 per day',
        'message': 'Rate limit is 500 lookups per 24 hours per IP address.',
        'batch_limit': '10 per day',
        'note': 'Batch endpoint is limited to 10 requests per day (up to 100 addresses each).'
    })


@app.route('/api/lookup/stream', methods=['GET', 'POST'])
@require_api_key
def lookup_stream():
    """
    Streaming lookup - returns results as Server-Sent Events (SSE).
    Each utility type is sent as soon as it's found, so users see progress.
    
    Events sent:
    - geocode: Location info (first, fast)
    - electric: Electric utility (fast)
    - gas: Gas utility (fast)
    - water: Water utility (fast)
    - sewer: Sewer utility (fast)
    - internet: Internet providers (slow, last)
    - complete: All done
    - error: If something fails
    """
    if request.method == 'POST':
        data = request.get_json()
        address = data.get('address')
        utilities_param = data.get('utilities', 'electric,gas,water,internet')
    else:
        address = request.args.get('address')
        utilities_param = request.args.get('utilities', 'electric,gas,water,internet')
    
    selected_utilities = [u.strip().lower() for u in utilities_param.split(',')]
    
    if not address:
        return jsonify({'error': 'Address is required'}), 400
    
    def generate():
        """Generator that yields SSE events as utilities are found."""
        try:
            # Step 1: Geocode (fast)
            yield f"data: {json.dumps({'event': 'status', 'message': 'Geocoding address...'})}\n\n"
            
            location = geocode_address(address, include_geography=True)
            if not location:
                yield f"data: {json.dumps({'event': 'error', 'message': 'Could not geocode address'})}\n\n"
                return
            
            yield f"data: {json.dumps({'event': 'geocode', 'data': location})}\n\n"
            
            lat = location.get('lat')
            lon = location.get('lon')
            city = location.get('city')
            county = location.get('county')
            state = location.get('state')
            zip_code = location.get('zip_code', '')
            
            # Step 2: Look up ALL utilities concurrently
            yield f"data: {json.dumps({'event': 'status', 'message': 'Looking up utility providers...'})}\n\n"
            
            non_internet_utilities = [u for u in selected_utilities if u != 'internet']
            v2_result = None
            internet_result = None
            
            # Run electric/gas/water and internet lookups concurrently
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = {}
                
                if non_internet_utilities:
                    # SERP verification disabled for speed - should_skip_serp was causing delays
                    futures['utilities'] = executor.submit(
                        lookup_utilities_by_address, address, 
                        selected_utilities=non_internet_utilities, verify_with_serp=False
                    )
                
                if 'internet' in selected_utilities:
                    futures['internet'] = executor.submit(lookup_internet_only, address)
                
                # Collect results as they complete
                for future in as_completed(futures.values()):
                    pass  # Just wait for all to complete
                
                if 'utilities' in futures:
                    v2_result = futures['utilities'].result()
                if 'internet' in futures:
                    internet_result = futures['internet'].result()
            
            # Stream electric result
            if 'electric' in selected_utilities:
                electric = v2_result.get('electric') if v2_result else None
                if electric:
                    primary = electric[0] if isinstance(electric, list) else electric
                    raw_confidence = primary.get('_confidence') or 'high'
                    formatted = format_utility(primary, 'electric', city, state)
                    formatted['confidence'] = raw_confidence
                    yield f"data: {json.dumps({'event': 'electric', 'data': formatted})}\n\n"
                else:
                    yield f"data: {json.dumps({'event': 'electric', 'data': None, 'note': 'No electric provider found'})}\n\n"
            
            # Stream gas result
            if 'gas' in selected_utilities:
                gas = v2_result.get('gas') if v2_result else None
                if gas:
                    primary = gas[0] if isinstance(gas, list) else gas
                    if primary.get('_no_service'):
                        yield f"data: {json.dumps({'event': 'gas', 'data': None, 'note': 'No piped natural gas service - area may use propane'})}\n\n"
                    else:
                        raw_confidence = primary.get('_confidence') or 'high'
                        formatted = format_utility(primary, 'gas', city, state)
                        formatted['confidence'] = raw_confidence
                        yield f"data: {json.dumps({'event': 'gas', 'data': formatted})}\n\n"
                else:
                    yield f"data: {json.dumps({'event': 'gas', 'data': None, 'note': 'No gas provider found'})}\n\n"
            
            # Stream water result
            if 'water' in selected_utilities:
                water = v2_result.get('water') if v2_result else None
                if water:
                    primary = water[0] if isinstance(water, list) else water
                    yield f"data: {json.dumps({'event': 'water', 'data': format_utility(primary, 'water', city, state)})}\n\n"
                else:
                    yield f"data: {json.dumps({'event': 'water', 'data': None, 'note': 'No water provider found - may be private well'})}\n\n"
            
            # Stream sewer result
            if 'sewer' in selected_utilities:
                sewer = v2_result.get('sewer') if v2_result else None
                if sewer:
                    primary = sewer[0] if isinstance(sewer, list) else sewer
                    yield f"data: {json.dumps({'event': 'sewer', 'data': format_utility(primary, 'sewer', city, state)})}\n\n"
                else:
                    yield f"data: {json.dumps({'event': 'sewer', 'data': None, 'note': 'No sewer provider found - may be septic'})}\n\n"
            
            # Stream internet result
            if 'internet' in selected_utilities:
                if internet_result:
                    yield f"data: {json.dumps({'event': 'internet', 'data': format_internet_providers(internet_result)})}\n\n"
                else:
                    yield f"data: {json.dumps({'event': 'internet', 'data': None, 'note': 'Could not retrieve internet data'})}\n\n"
            
            # Done!
            yield f"data: {json.dumps({'event': 'complete', 'message': 'Lookup complete'})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'event': 'error', 'message': str(e)})}\n\n"
    
    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Access-Control-Allow-Origin': '*',
            'X-Accel-Buffering': 'no'  # Disable nginx buffering
        }
    )


@app.route('/api/batch', methods=['POST'])
# @limiter.limit("10 per day")  # Rate limiting disabled
def batch_lookup():
    """
    Batch lookup utilities for multiple addresses from CSV.
    
    Accepts:
    - CSV file upload with 'address' column
    - OR JSON with 'addresses' array
    
    Returns JSON with results array and can be downloaded as CSV.
    Processes in batches and includes progress tracking.
    """
    import csv
    import io
    import time
    
    addresses = []
    
    # Check for file upload
    if 'file' in request.files:
        file = request.files['file']
        if file.filename.endswith('.csv'):
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            reader = csv.DictReader(stream)
            
            # Find address column (case-insensitive)
            address_col = None
            for col in reader.fieldnames or []:
                if col.lower() in ['address', 'full_address', 'property_address', 'street_address']:
                    address_col = col
                    break
            
            if not address_col:
                return jsonify({'error': 'CSV must have an address column (address, full_address, property_address, or street_address)'}), 400
            
            for row in reader:
                addr = row.get(address_col, '').strip()
                if addr:
                    addresses.append({'address': addr, 'original_row': row})
    
    # Check for JSON body
    elif request.is_json:
        data = request.get_json()
        if 'addresses' in data:
            for addr in data['addresses']:
                if isinstance(addr, str):
                    addresses.append({'address': addr, 'original_row': {}})
                elif isinstance(addr, dict) and 'address' in addr:
                    addresses.append({'address': addr['address'], 'original_row': addr})
    
    if not addresses:
        return jsonify({'error': 'No addresses provided. Upload a CSV with address column or send JSON with addresses array.'}), 400
    
    # Limit batch size
    max_batch = 100
    if len(addresses) > max_batch:
        return jsonify({'error': f'Maximum {max_batch} addresses per batch. You provided {len(addresses)}.'}), 400
    
    # Process addresses
    results = []
    batch_size = 10
    
    for i, item in enumerate(addresses):
        addr = item['address']
        original = item['original_row']
        
        try:
            result = lookup_utilities_by_address(addr, verify_with_serp=False)
            
            if result:
                # Extract primary utilities
                electric = result.get('electric')
                gas = result.get('gas')
                water = result.get('water')
                internet = result.get('internet')
                location = result.get('location', {})
                
                electric_primary = electric[0] if isinstance(electric, list) else electric
                gas_primary = gas[0] if isinstance(gas, list) else gas
                
                row_result = {
                    'input_address': addr,
                    'status': 'success',
                    'city': location.get('city'),
                    'county': location.get('county'),
                    'state': location.get('state'),
                    # Electric
                    'electric_provider': electric_primary.get('NAME') if electric_primary else None,
                    'electric_confidence': electric_primary.get('_confidence') if electric_primary else None,
                    'electric_phone': electric_primary.get('TELEPHONE') if electric_primary else None,
                    'electric_website': electric_primary.get('WEBSITE') if electric_primary else None,
                    # Gas
                    'gas_provider': gas_primary.get('NAME') if gas_primary else None,
                    'gas_confidence': gas_primary.get('_confidence') if gas_primary else None,
                    'gas_phone': gas_primary.get('TELEPHONE') if gas_primary else None,
                    # Water
                    'water_provider': water.get('name') if water else None,
                    'water_phone': water.get('phone') if water else None,
                    # Internet
                    'internet_provider_count': internet.get('provider_count') if internet else 0,
                    'has_fiber': internet.get('has_fiber') if internet else False,
                    'best_internet': internet.get('best_wired', {}).get('name') if internet else None,
                }
            else:
                row_result = {
                    'input_address': addr,
                    'status': 'geocode_failed',
                }
        except Exception as e:
            row_result = {
                'input_address': addr,
                'status': 'error',
                'error': str(e),
            }
        
        # Preserve original columns
        row_result['_original'] = original
        results.append(row_result)
        
        # Log progress every batch_size
        if (i + 1) % batch_size == 0:
            print(f"Batch progress: {i + 1}/{len(addresses)} addresses processed")
    
    # Return format based on Accept header
    if request.headers.get('Accept') == 'text/csv':
        # Return as CSV
        output = io.StringIO()
        if results:
            fieldnames = [k for k in results[0].keys() if k != '_original']
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            for r in results:
                row = {k: v for k, v in r.items() if k != '_original'}
                writer.writerow(row)
        
        from flask import Response
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=utility_lookup_results.csv'}
        )
    
    # Return as JSON
    return jsonify({
        'total': len(addresses),
        'processed': len(results),
        'results': results
    })


@app.route('/api/missing-cities', methods=['GET'])
def missing_cities():
    """
    View cities that are missing from EPA SDWIS data.
    These are candidates for adding to the supplemental file.
    """
    from pathlib import Path
    
    missing_file = Path(__file__).parent / "water_missing_cities.json"
    
    if not missing_file.exists():
        return jsonify({
            'count': 0,
            'cities': {},
            'note': 'No missing cities logged yet'
        })
    
    try:
        with open(missing_file, 'r') as f:
            data = json.load(f)
        
        cities = data.get('cities', {})
        
        # Sort by count (most frequent first)
        sorted_cities = dict(sorted(
            cities.items(),
            key=lambda x: x[1].get('count', 0),
            reverse=True
        ))
        
        return jsonify({
            'count': len(sorted_cities),
            'cities': sorted_cities,
            'note': 'Cities missing from EPA SDWIS - add to water_utilities_supplemental.json'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# =============================================================================
# USER FEEDBACK SYSTEM
# =============================================================================

@app.route('/api/feedback', methods=['POST'])
def submit_feedback():
    """
    Accept user corrections for utility providers.
    
    Request body:
    {
        "address": "301 Treasure Trove Path, Kyle, TX 78640",
        "zip_code": "78640",
        "utility_type": "gas",
        "returned_provider": "Texas Gas Service",
        "correct_provider": "CenterPoint Energy",
        "source": "resident",
        "email": null
    }
    """
    data = request.get_json()
    
    # Validate required fields
    required = ['address', 'utility_type', 'correct_provider']
    for field in required:
        if not data.get(field):
            return jsonify({"error": f"Missing required field: {field}"}), 400
    
    # Validate utility type
    valid_types = ['electric', 'gas', 'water', 'internet']
    if data['utility_type'] not in valid_types:
        return jsonify({"error": f"Invalid utility_type. Must be one of: {valid_types}"}), 400
    
    # Extract ZIP and city/state from address
    zip_code = data.get('zip_code') or extract_zip(data['address'])
    city, state = extract_city_state(data['address'])
    
    if not state:
        return jsonify({"error": "Could not determine state from address"}), 400
    if not zip_code:
        return jsonify({"error": "Could not determine ZIP code from address"}), 400
    
    # Use SQLite corrections database
    try:
        from corrections_lookup import add_correction, init_db
        
        # Ensure DB exists
        init_db()
        
        result = add_correction(
            utility_type=data['utility_type'],
            correct_provider=data['correct_provider'],
            state=state,
            zip_code=zip_code,
            street=data.get('address'),
            city=city,
            incorrect_provider=data.get('returned_provider'),
            source=data.get('source', 'user_feedback'),
            full_address=data.get('address')
        )
        
        if result['status'] == 'updated':
            if result['confirmation_count'] >= 3:
                return jsonify({
                    "status": "verified",
                    "message": f"Correction verified with {result['confirmation_count']} confirmations and is now active.",
                    "confirmation_count": result['confirmation_count']
                })
            else:
                return jsonify({
                    "status": "confirmation_added",
                    "message": f"Thanks! {result['confirmation_count']}/3 confirmations for this correction.",
                    "confirmation_count": result['confirmation_count']
                })
        else:
            return jsonify({
                "status": "received",
                "message": "Thank you. This correction will be applied after additional confirmations.",
                "correction_id": result['id']
            })
            
    except Exception as e:
        print(f"Error adding correction to SQLite: {e}")
        # Fall back to JSON-based system
        pass
    
    # Fallback: JSON-based system
    feedback_id = 'fb_' + hashlib.md5(
        f"{data['address']}_{data['utility_type']}_{datetime.now().isoformat()}".encode()
    ).hexdigest()[:12]
    
    feedback_record = {
        "feedback_id": feedback_id,
        "address": data['address'],
        "zip_code": zip_code,
        "city": city,
        "state": state,
        "utility_type": data['utility_type'],
        "returned_provider": data.get('returned_provider'),
        "correct_provider": data['correct_provider'],
        "is_correct": data.get('is_correct', False),
        "service_check_url": data.get('service_check_url'),
        "source": data.get('source', 'unknown'),
        "email": data.get('email'),
        "submitted_at": datetime.now().isoformat(),
        "status": "pending",
        "confirmation_count": 1,
        "addresses": [data['address']]
    }
    
    pending = load_feedback('pending.json')
    
    # Check if similar feedback already exists (same ZIP + utility + correction)
    correction_key = f"{zip_code}_{data['utility_type']}_{data['correct_provider'].upper()}"
    
    existing = None
    for fid, record in pending.items():
        existing_key = f"{record.get('zip_code')}_{record['utility_type']}_{record['correct_provider'].upper()}"
        if existing_key == correction_key:
            existing = fid
            break
    
    if existing:
        # Increment confirmation count
        pending[existing]['confirmation_count'] += 1
        if data['address'] not in pending[existing].get('addresses', []):
            pending[existing]['addresses'].append(data['address'])
        
        # Auto-confirm if threshold reached
        if pending[existing]['confirmation_count'] >= 3:
            auto_confirm_feedback(existing, pending[existing])
            del pending[existing]
            save_feedback('pending.json', pending)
            return jsonify({
                "status": "auto_confirmed",
                "feedback_id": existing,
                "message": "Correction confirmed by multiple users and applied."
            })
        
        save_feedback('pending.json', pending)
        return jsonify({
            "status": "confirmation_added",
            "feedback_id": existing,
            "confirmation_count": pending[existing]['confirmation_count'],
            "message": f"Thanks! {pending[existing]['confirmation_count']}/3 confirmations for this correction."
        })
    
    # New feedback
    pending[feedback_id] = feedback_record
    save_feedback('pending.json', pending)
    
    return jsonify({
        "status": "received",
        "feedback_id": feedback_id,
        "message": "Thank you. This correction will be reviewed."
    })


def auto_confirm_feedback(feedback_id, feedback_record):
    """
    When 3+ users confirm same correction, auto-apply it.
    """
    # Load confirmed feedback
    confirmed = load_feedback('confirmed.json')
    
    # Add to confirmed
    feedback_record['status'] = 'auto_confirmed'
    feedback_record['confirmed_at'] = datetime.now().isoformat()
    confirmed[feedback_id] = feedback_record
    save_feedback('confirmed.json', confirmed)
    
    # Add to override table based on utility type
    zip_code = feedback_record.get('zip_code')
    utility_type = feedback_record['utility_type']
    correct_provider = feedback_record['correct_provider']
    city = feedback_record.get('city')
    state = feedback_record.get('state')
    
    if utility_type == 'gas' and zip_code:
        add_gas_zip_override(zip_code, correct_provider, state, f"User feedback ({feedback_record['confirmation_count']} confirmations)")
    elif utility_type == 'water' and city and state:
        add_water_override(city, state, correct_provider)
    
    print(f"Auto-confirmed feedback {feedback_id}: {zip_code} {utility_type} → {correct_provider}")


def add_gas_zip_override(zip_code, provider_name, state, source):
    """Add a ZIP code override for gas utility."""
    from pathlib import Path
    
    # Update the GAS_ZIP_OVERRIDES in state_utility_verification.py
    # For now, save to a JSON file that can be loaded
    overrides_file = Path(__file__).parent / "data" / "gas_zip_overrides.json"
    overrides_file.parent.mkdir(parents=True, exist_ok=True)
    
    if overrides_file.exists():
        with open(overrides_file, 'r') as f:
            overrides = json.load(f)
    else:
        overrides = {}
    
    overrides[zip_code] = {
        "state": state,
        "name": provider_name,
        "source": source,
        "added_at": datetime.now().isoformat()
    }
    
    with open(overrides_file, 'w') as f:
        json.dump(overrides, f, indent=2)
    
    print(f"Added gas override: {zip_code} → {provider_name}")


def add_water_override(city, state, provider_name):
    """Add a city-level override for water utility."""
    from pathlib import Path
    
    filepath = Path(__file__).parent / "water_utilities_supplemental.json"
    
    if filepath.exists():
        with open(filepath, 'r') as f:
            data = json.load(f)
    else:
        data = {"_description": "Supplemental water utility data", "by_city": {}}
    
    key = f"{state}|{city}".upper()
    data['by_city'][key] = {
        "name": provider_name,
        "state": state,
        "city": city,
        "_source": "user_feedback",
        "_confidence": "high",
        "added_at": datetime.now().isoformat()
    }
    
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"Added water override: {city}, {state} → {provider_name}")


@app.route('/api/feedback/dashboard', methods=['GET'])
def feedback_dashboard():
    """
    Internal dashboard showing feedback status.
    Shows data from both SQLite corrections DB and legacy JSON files.
    """
    # Get SQLite stats
    sqlite_stats = {}
    try:
        from corrections_lookup import get_stats, get_pending_corrections, get_verified_corrections
        sqlite_stats = get_stats()
    except Exception as e:
        sqlite_stats = {"error": str(e)}
    
    # Legacy JSON data
    pending = load_feedback('pending.json')
    confirmed = load_feedback('confirmed.json')
    
    # Sort pending by confirmation count (highest first)
    pending_sorted = sorted(
        pending.values(),
        key=lambda x: x.get('confirmation_count', 0),
        reverse=True
    )
    
    # Recent confirmed
    confirmed_sorted = sorted(
        confirmed.values(),
        key=lambda x: x.get('confirmed_at', ''),
        reverse=True
    )[:20]
    
    # Stats by ZIP
    zip_stats = {}
    for record in list(pending.values()) + list(confirmed.values()):
        zip_code = record.get('zip_code', 'unknown')
        if zip_code not in zip_stats:
            zip_stats[zip_code] = {'pending': 0, 'confirmed': 0}
        if record.get('status') == 'pending':
            zip_stats[zip_code]['pending'] += 1
        else:
            zip_stats[zip_code]['confirmed'] += 1
    
    # Top problem ZIPs
    problem_zips = sorted(
        zip_stats.items(),
        key=lambda x: x[1]['pending'] + x[1]['confirmed'],
        reverse=True
    )[:10]
    
    return jsonify({
        "sqlite_corrections": sqlite_stats,
        "legacy_json": {
            "pending_count": len(pending),
            "confirmed_count": len(confirmed),
            "total_feedback": len(pending) + len(confirmed)
        },
        "summary": {
            "total_corrections": sqlite_stats.get('total', 0) + len(pending) + len(confirmed),
            "verified_corrections": sqlite_stats.get('address_verified', 0) + sqlite_stats.get('zip_verified', 0) + len(confirmed)
        },
        "pending": pending_sorted[:20],
        "recent_confirmed": confirmed_sorted,
        "problem_zips": problem_zips
    })


@app.route('/api/feedback/<feedback_id>/confirm', methods=['POST'])
def manually_confirm_feedback(feedback_id):
    """
    Manually confirm a pending feedback item (admin action).
    """
    pending = load_feedback('pending.json')
    
    if feedback_id not in pending:
        return jsonify({"error": "Feedback not found"}), 404
    
    record = pending[feedback_id]
    auto_confirm_feedback(feedback_id, record)
    del pending[feedback_id]
    save_feedback('pending.json', pending)
    
    return jsonify({
        "status": "confirmed",
        "feedback_id": feedback_id,
        "message": "Feedback confirmed and override applied."
    })


@app.route('/api/confirm', methods=['POST'])
def confirm_utility():
    """
    User confirms a utility result is correct (clicks "Yes").
    This caches the confirmation and records in verified_utilities table.
    
    Request body:
    {
        "address": "1725 Toomey Rd, Austin, TX 78704",
        "utility_type": "electric",
        "utility_name": "Austin Energy",
        "phone": "512-494-9400",
        "website": "https://austinenergy.com"
    }
    """
    data = request.get_json()
    
    required = ['address', 'utility_type', 'utility_name']
    for field in required:
        if not data.get(field):
            return jsonify({"error": f"Missing required field: {field}"}), 400
    
    # Cache the confirmation
    cache_confirmation(
        address=data['address'],
        utility_type=data['utility_type'],
        utility_name=data['utility_name'],
        phone=data.get('phone'),
        website=data.get('website')
    )
    
    # Also record in SQLite verified_utilities for tracking
    zip_code = extract_zip(data['address'])
    city, state = extract_city_state(data['address'])
    
    try:
        from corrections_lookup import add_verification, init_db
        init_db()
        result = add_verification(
            utility_type=data['utility_type'],
            provider_name=data['utility_name'],
            state=state or '',
            zip_code=zip_code,
            city=city,
            address=data['address'],
            phone=data.get('phone'),
            website=data.get('website')
        )
        verification_count = result.get('verification_count', 1)
    except Exception as e:
        print(f"Error recording verification: {e}")
        verification_count = 1
    
    return jsonify({
        "status": "confirmed",
        "message": "Thank you! Your confirmation helps improve accuracy.",
        "verification_count": verification_count
    })


@app.route('/api/cache/stats', methods=['GET'])
def cache_stats():
    """Get address cache statistics."""
    return jsonify(get_cache_stats())


@app.route('/api/feedback/<feedback_id>/reject', methods=['POST'])
def reject_feedback(feedback_id):
    """
    Reject a pending feedback item (admin action).
    """
    pending = load_feedback('pending.json')
    
    if feedback_id not in pending:
        return jsonify({"error": "Feedback not found"}), 404
    
    record = pending[feedback_id]
    record['status'] = 'rejected'
    record['rejected_at'] = datetime.now().isoformat()
    
    # Move to confirmed file (for record keeping)
    confirmed = load_feedback('confirmed.json')
    confirmed[feedback_id] = record
    save_feedback('confirmed.json', confirmed)
    
    del pending[feedback_id]
    save_feedback('pending.json', pending)
    
    return jsonify({
        "status": "rejected",
        "feedback_id": feedback_id
    })


# =============================================================================
# CORRECTIONS ADMIN API (SQLite-based)
# =============================================================================

@app.route('/api/corrections', methods=['GET'])
def list_corrections():
    """
    List corrections from SQLite database.
    Query params: status (pending|verified|all), limit
    """
    try:
        from corrections_lookup import get_pending_corrections, get_verified_corrections, get_stats, init_db
        init_db()
        
        status = request.args.get('status', 'pending')
        limit = int(request.args.get('limit', 50))
        
        if status == 'pending':
            corrections = get_pending_corrections(limit)
        elif status == 'verified':
            corrections = get_verified_corrections(limit)
        else:
            corrections = get_pending_corrections(limit) + get_verified_corrections(limit)
        
        return jsonify({
            "status": status,
            "count": len(corrections),
            "corrections": corrections,
            "stats": get_stats()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/corrections/<int:correction_id>/approve', methods=['POST'])
def approve_correction(correction_id):
    """Approve a pending correction (admin action)."""
    try:
        from corrections_lookup import approve_correction as do_approve, init_db
        init_db()
        
        success = do_approve(correction_id)
        if success:
            return jsonify({"status": "approved", "correction_id": correction_id})
        else:
            return jsonify({"error": "Correction not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/corrections/<int:correction_id>/reject', methods=['POST'])
def reject_correction(correction_id):
    """Reject a pending correction (admin action)."""
    try:
        from corrections_lookup import reject_correction as do_reject, init_db
        init_db()
        
        success = do_reject(correction_id)
        if success:
            return jsonify({"status": "rejected", "correction_id": correction_id})
        else:
            return jsonify({"error": "Correction not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/corrections/stats', methods=['GET'])
def corrections_stats():
    """Get correction statistics."""
    try:
        from corrections_lookup import get_stats, init_db
        init_db()
        return jsonify(get_stats())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/corrections/apply', methods=['POST'])
def apply_corrections():
    """
    Apply all verified corrections to the JSON data files.
    This updates the actual data files with user-submitted corrections.
    """
    try:
        from corrections_lookup import apply_corrections_to_data, get_unapplied_corrections, init_db
        init_db()
        
        # Check how many are pending
        unapplied = get_unapplied_corrections()
        if not unapplied:
            return jsonify({
                "status": "no_changes",
                "message": "No unapplied corrections to apply"
            })
        
        # Apply them
        result = apply_corrections_to_data()
        
        return jsonify({
            "status": "success",
            "applied": result['applied'],
            "skipped": result['skipped'],
            "errors": result['errors'],
            "details": result['details']
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/corrections/pending', methods=['GET'])
def list_unapplied_corrections():
    """List verified corrections that haven't been applied to data files yet."""
    try:
        from corrections_lookup import get_unapplied_corrections, init_db
        init_db()
        
        unapplied = get_unapplied_corrections()
        return jsonify({
            "count": len(unapplied),
            "corrections": unapplied
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =============================================================================
# PROBLEM AREAS REGISTRY
# =============================================================================

@app.route('/api/problem-areas', methods=['GET'])
def list_problem_areas():
    """List all known problem areas."""
    problem_areas = load_problem_areas()
    
    # Count by level
    summary = {
        'zip_count': len(problem_areas.get('zip', {})),
        'county_count': len(problem_areas.get('county', {})),
        'state_count': len(problem_areas.get('state', {}))
    }
    
    return jsonify({
        'summary': summary,
        'zip': problem_areas.get('zip', {}),
        'county': problem_areas.get('county', {}),
        'state': problem_areas.get('state', {})
    })


@app.route('/api/problem-areas/check', methods=['GET'])
def check_problem_area_endpoint():
    """Check if a location is a known problem area."""
    zip_code = request.args.get('zip')
    county = request.args.get('county')
    state = request.args.get('state')
    utility_type = request.args.get('utility_type')
    
    if not utility_type:
        return jsonify({'error': 'utility_type is required'}), 400
    
    result = check_problem_area(zip_code, county, state, utility_type)
    return jsonify(result)


@app.route('/api/problem-areas', methods=['POST'])
def add_problem_area_endpoint():
    """Add a new problem area (internal use)."""
    data = request.get_json()
    
    required = ['level', 'key', 'utilities_affected', 'issue', 'recommendation']
    for field in required:
        if field not in data:
            return jsonify({'error': f'Missing required field: {field}'}), 400
    
    if data['level'] not in ['zip', 'county', 'state']:
        return jsonify({'error': 'level must be zip, county, or state'}), 400
    
    add_problem_area(
        level=data['level'],
        key=data['key'],
        utilities_affected=data['utilities_affected'],
        issue=data['issue'],
        recommendation=data['recommendation'],
        known_correct=data.get('known_correct')
    )
    
    return jsonify({'status': 'added', 'level': data['level'], 'key': data['key']})


# =============================================================================
# SPECIAL DISTRICTS
# =============================================================================

@app.route('/api/special-districts', methods=['GET'])
def list_special_districts_info():
    """Get info about available special district data."""
    available_states = get_available_states()
    
    return jsonify({
        'available_states': available_states,
        'total_states': len(available_states),
        'note': 'Special districts include MUDs (TX), CDDs (FL), Metro Districts (CO), etc.'
    })


@app.route('/api/special-districts/lookup', methods=['GET'])
def lookup_special_district_endpoint():
    """
    Look up special district for coordinates.
    
    Query params:
        lat: Latitude
        lon: Longitude
        state: 2-letter state code
        zip: ZIP code (optional, fallback)
        subdivision: Subdivision name (optional)
        service: 'water' or 'sewer' (default: water)
        debug: Include debug info (optional)
    """
    lat = request.args.get('lat', type=float)
    lon = request.args.get('lon', type=float)
    state = request.args.get('state', '').upper()
    zip_code = request.args.get('zip')
    subdivision = request.args.get('subdivision')
    service = request.args.get('service', 'water')
    debug = request.args.get('debug', '').lower() == 'true'
    
    if not state:
        return jsonify({'error': 'state is required'}), 400
    
    # Import here to get debug info
    from special_districts import load_state_districts, SHAPELY_AVAILABLE
    
    debug_info = {}
    if debug:
        districts = load_state_districts(state)
        debug_info = {
            'shapely_available': SHAPELY_AVAILABLE,
            'districts_loaded': len(districts),
            'has_data': has_special_district_data(state),
            'lat': lat,
            'lon': lon
        }
        # Check if any district has valid geometry
        if districts and SHAPELY_AVAILABLE:
            from shapely.geometry import shape
            valid_geom_count = 0
            for d in districts[:100]:  # Check first 100
                try:
                    boundary = d.get('boundary', {})
                    if boundary.get('data'):
                        geom = shape(boundary['data'])
                        if geom.is_valid:
                            valid_geom_count += 1
                except:
                    pass
            debug_info['valid_geometries_sample'] = valid_geom_count
    
    if not has_special_district_data(state):
        response = {
            'found': False,
            'message': f'No special district data available for {state}',
            'available_states': get_available_states()
        }
        if debug:
            response['debug'] = debug_info
        return jsonify(response)
    
    result = lookup_special_district(
        lat=lat,
        lon=lon,
        state=state,
        zip_code=zip_code,
        subdivision=subdivision,
        service=service
    )
    
    if result:
        response = {
            'found': True,
            'district': format_district_for_response(result)
        }
        if debug:
            response['debug'] = debug_info
        return jsonify(response)
    else:
        response = {
            'found': False,
            'message': 'No special district found for this location'
        }
        if debug:
            response['debug'] = debug_info
        return jsonify(response)


# =============================================================================
# UTILITY SCRAPERS
# =============================================================================

@app.route('/api/scrapers', methods=['GET'])
def list_scrapers():
    """List available utility company scrapers."""
    scrapers = get_available_scrapers()
    return jsonify({
        'scrapers': scrapers,
        'count': len(scrapers),
        'note': 'Scrapers verify addresses directly with utility company websites'
    })


@app.route('/api/scrapers/verify', methods=['GET', 'POST'])
def verify_with_scraper():
    """
    Verify address with utility company scraper.
    
    Query params / JSON body:
        address: Full street address
        state: 2-letter state code
        utility_type: 'electric' or 'gas' (default: electric)
        expected_provider: Provider name to verify (optional)
    """
    if request.method == 'POST':
        data = request.get_json()
        address = data.get('address')
        state = data.get('state', '').upper()
        utility_type = data.get('utility_type', 'electric')
        expected_provider = data.get('expected_provider')
    else:
        address = request.args.get('address')
        state = request.args.get('state', '').upper()
        utility_type = request.args.get('utility_type', 'electric')
        expected_provider = request.args.get('expected_provider')
    
    if not address:
        return jsonify({'error': 'address is required'}), 400
    if not state:
        return jsonify({'error': 'state is required'}), 400
    
    # Check if we have scrapers for this state
    available = get_scrapers_for_state(state, utility_type)
    if not available:
        return jsonify({
            'verified': False,
            'message': f'No {utility_type} scrapers available for {state}',
            'available_scrapers': list(get_available_scrapers().keys())
        })
    
    # Run verification
    result = verify_with_utility_api_sync(
        address=address,
        state=state,
        expected_provider=expected_provider,
        utility_type=utility_type
    )
    
    if result:
        return jsonify({
            'verified': result.get('serves') is True,
            'result': result
        })
    else:
        return jsonify({
            'verified': False,
            'message': 'Could not verify with utility company website'
        })


# =============================================================================
# CROSS-VALIDATION
# =============================================================================

@app.route('/api/cross-validate', methods=['POST'])
def cross_validate_endpoint():
    """
    Cross-validate provider results from multiple sources.
    
    JSON body:
    {
        "results": [
            {"source_name": "EIA", "provider_name": "Oncor", "confidence": "high"},
            {"source_name": "HIFLD", "provider_name": "Oncor Electric Delivery", "confidence": "medium"},
            {"source_name": "SERP", "provider_name": "Oncor", "confidence": "high"}
        ]
    }
    """
    data = request.get_json()
    results_data = data.get('results', [])
    
    if not results_data:
        return jsonify({'error': 'results array is required'}), 400
    
    # Convert to SourceResult objects
    results = []
    for r in results_data:
        results.append(SourceResult(
            source_name=r.get('source_name', 'Unknown'),
            provider_name=r.get('provider_name'),
            confidence=r.get('confidence', 'medium')
        ))
    
    cv_result = cross_validate(results)
    
    return jsonify({
        'cross_validation': format_cv_response(cv_result)
    })


@app.route('/api/disagreements', methods=['GET'])
def list_disagreements():
    """List cross-validation disagreements for review."""
    limit = request.args.get('limit', 100, type=int)
    disagreements = get_disagreements(limit)
    
    return jsonify({
        'count': len(disagreements),
        'disagreements': disagreements
    })


@app.route('/api/providers/match', methods=['GET'])
def check_provider_match():
    """
    Check if two provider names match (for testing normalization).
    
    Query params:
        name1: First provider name
        name2: Second provider name
    """
    name1 = request.args.get('name1', '')
    name2 = request.args.get('name2', '')
    
    if not name1 or not name2:
        return jsonify({'error': 'name1 and name2 are required'}), 400
    
    match = providers_match(name1, name2)
    
    return jsonify({
        'name1': name1,
        'name2': name2,
        'match': match
    })


# =============================================================================
# VALIDATION REPORTS
# =============================================================================

import glob

VALIDATION_REPORTS_DIR = os.path.join(os.path.dirname(__file__), 'data', 'validation_reports')
LOOKUPS_LOG_FILE = os.path.join(os.path.dirname(__file__), 'data', 'lookup_log.json')

@app.route('/api/validation-reports', methods=['GET'])
def list_validation_reports():
    """List available validation reports."""
    if not os.path.exists(VALIDATION_REPORTS_DIR):
        return jsonify({'reports': [], 'count': 0})
    
    reports = []
    for filepath in glob.glob(os.path.join(VALIDATION_REPORTS_DIR, '*.json')):
        filename = os.path.basename(filepath)
        
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            reports.append({
                'filename': filename,
                'generated_at': data.get('generated_at'),
                'sample_size': data.get('sample_size'),
                'summary': data.get('summary'),
                'alerts': data.get('alerts', [])
            })
        except (json.JSONDecodeError, IOError):
            continue
    
    # Sort by date descending
    reports.sort(key=lambda x: x.get('generated_at', ''), reverse=True)
    
    return jsonify({'reports': reports, 'count': len(reports)})


@app.route('/api/validation-reports/<filename>', methods=['GET'])
def get_validation_report(filename):
    """Get a specific validation report."""
    # Sanitize filename
    if '..' in filename or '/' in filename:
        return jsonify({'error': 'Invalid filename'}), 400
    
    filepath = os.path.join(VALIDATION_REPORTS_DIR, filename)
    
    if not os.path.exists(filepath):
        return jsonify({'error': 'Report not found'}), 404
    
    with open(filepath, 'r') as f:
        report = json.load(f)
    
    return jsonify(report)


@app.route('/api/accuracy-trend', methods=['GET'])
def get_accuracy_trend():
    """Get accuracy trend over time from validation reports."""
    if not os.path.exists(VALIDATION_REPORTS_DIR):
        return jsonify({'trend': []})
    
    trend = []
    for filepath in sorted(glob.glob(os.path.join(VALIDATION_REPORTS_DIR, '*.json'))):
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            trend.append({
                'date': data.get('generated_at', '')[:10],
                'electric': data.get('summary', {}).get('electric_accuracy'),
                'gas': data.get('summary', {}).get('gas_accuracy'),
                'water': data.get('summary', {}).get('water_accuracy')
            })
        except (json.JSONDecodeError, IOError):
            continue
    
    return jsonify({'trend': trend})


@app.route('/api/lookup-log', methods=['GET'])
def get_lookup_log():
    """Get recent lookup log entries."""
    limit = request.args.get('limit', 100, type=int)
    state = request.args.get('state', '').upper()
    
    if not os.path.exists(LOOKUPS_LOG_FILE):
        return jsonify({'lookups': [], 'count': 0})
    
    try:
        with open(LOOKUPS_LOG_FILE, 'r') as f:
            lookups = json.load(f)
    except (json.JSONDecodeError, IOError):
        return jsonify({'lookups': [], 'count': 0})
    
    # Filter by state if specified
    if state:
        lookups = [l for l in lookups if l.get('state', '').upper() == state]
    
    # Sort by timestamp descending and limit
    lookups.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    lookups = lookups[:limit]
    
    return jsonify({
        'lookups': lookups,
        'count': len(lookups)
    })


# =============================================================================
# MUNICIPAL UTILITIES
# =============================================================================

@app.route('/api/municipal-utilities', methods=['GET'])
def list_municipal_utilities():
    """List all municipal utilities."""
    state = request.args.get('state', '').upper() if request.args.get('state') else None
    utilities = get_all_municipal_utilities(state)
    stats = get_municipal_stats()
    
    return jsonify({
        'stats': stats,
        'utilities': utilities
    })


@app.route('/api/municipal-utilities/lookup', methods=['GET'])
def lookup_municipal():
    """Check if address is served by municipal utility."""
    state = request.args.get('state', '').upper() if request.args.get('state') else None
    city = request.args.get('city')
    zip_code = request.args.get('zip')
    county = request.args.get('county')
    
    if not state:
        return jsonify({'error': 'state parameter required'}), 400
    
    result = lookup_municipal_electric(state, city, zip_code, county)
    
    if result:
        return jsonify({'found': True, 'utility': result})
    else:
        return jsonify({'found': False, 'message': 'No municipal utility found for this location'})


# =============================================================================
# LEADGEN ENDPOINTS
# =============================================================================

import requests
import string
import random
from datetime import datetime, timedelta

# Airtable configuration for LeadGen
AIRTABLE_API_KEY = os.getenv('AIRTABLE_API_KEY')
AIRTABLE_BASE_ID = os.getenv('AIRTABLE_BASE_ID')
LEADGEN_LOOKUPS_TABLE_ID = os.getenv('LEADGEN_LOOKUPS_TABLE_ID', 'LeadGen_Lookups')
LEADGEN_REFCODES_TABLE_ID = os.getenv('LEADGEN_REFCODES_TABLE_ID', 'LeadGen_RefCodes')

def get_airtable_headers():
    """Get headers for Airtable API requests."""
    return {
        'Authorization': f'Bearer {AIRTABLE_API_KEY}',
        'Content-Type': 'application/json'
    }

def airtable_url(table_id):
    """Get Airtable API URL for a table."""
    return f'https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{table_id}'

def resolve_ref_code_to_email(ref_code):
    """Look up email from ref_code in Airtable."""
    if not ref_code or not AIRTABLE_API_KEY:
        return None
    
    try:
        url = airtable_url(LEADGEN_REFCODES_TABLE_ID)
        params = {'filterByFormula': f"{{ref_code}}='{ref_code}'"}
        resp = requests.get(url, headers=get_airtable_headers(), params=params, timeout=10)
        if resp.status_code == 200:
            records = resp.json().get('records', [])
            if records:
                return records[0].get('fields', {}).get('email')
    except Exception as e:
        logger.error(f"Error resolving ref_code: {e}")
    return None

def get_client_ip():
    """Get client IP from request headers."""
    return request.headers.get('x-forwarded-for', '').split(',')[0].strip() or \
           request.headers.get('x-real-ip') or \
           request.remote_addr or 'unknown'

# Whitelisted emails and IPs that bypass rate limiting
LEADGEN_WHITELIST_EMAILS = {'mark@utilityprofit.com'}
LEADGEN_WHITELIST_IPS = {'104.6.39.39'}

def count_recent_lookups(email=None, ip_address=None):
    """Count lookups in last 24 hours for email or IP."""
    # Check whitelist - return 0 to bypass limits
    if email and email.lower() in LEADGEN_WHITELIST_EMAILS:
        return 0
    if ip_address and ip_address in LEADGEN_WHITELIST_IPS:
        return 0
    
    if not AIRTABLE_API_KEY:
        return 0
    
    try:
        url = airtable_url(LEADGEN_LOOKUPS_TABLE_ID)
        # Airtable formula for last 24 hours
        twenty_four_hours_ago = (datetime.utcnow() - timedelta(hours=24)).isoformat()
        
        conditions = []
        if email:
            conditions.append(f"{{email}}='{email}'")
        if ip_address:
            conditions.append(f"{{ip_address}}='{ip_address}'")
        
        if not conditions:
            return 0
        
        # Use OR for email or IP match
        formula = f"AND(IS_AFTER({{created_at}}, '{twenty_four_hours_ago}'), OR({','.join(conditions)}))"
        params = {'filterByFormula': formula}
        
        resp = requests.get(url, headers=get_airtable_headers(), params=params, timeout=10)
        if resp.status_code == 200:
            return len(resp.json().get('records', []))
    except Exception as e:
        logger.error(f"Error counting lookups: {e}")
    return 0

def log_leadgen_lookup(ref_code, email, ip_address, address, utilities, results, source='organic'):
    """Log a lookup to Airtable LeadGen_Lookups table."""
    if not AIRTABLE_API_KEY:
        return
    
    try:
        url = airtable_url(LEADGEN_LOOKUPS_TABLE_ID)
        data = {
            'fields': {
                'ref_code': ref_code or '',
                'email': email,
                'ip_address': ip_address,
                'address_searched': address,
                'utilities_requested': utilities,
                'results_json': json.dumps(results) if results else '',
                'cta_clicked': False,
                'created_at': datetime.utcnow().isoformat(),
                'source': 'cold_email' if ref_code else source
            }
        }
        requests.post(url, headers=get_airtable_headers(), json=data, timeout=10)
    except Exception as e:
        logger.error(f"Error logging leadgen lookup: {e}")

def generate_ref_code():
    """Generate a random 6-character alphanumeric ref code."""
    chars = string.ascii_lowercase + string.digits
    return ''.join(random.choice(chars) for _ in range(6))


@app.route('/api/leadgen/lookup', methods=['POST'])
def leadgen_lookup():
    """Main leadgen lookup endpoint with tracking and limits."""
    data = request.get_json() or {}
    
    address = data.get('address')
    utilities = data.get('utilities', 'electric,gas,water')
    email = data.get('email')
    ref_code = data.get('ref_code')
    
    if not address:
        return jsonify({'status': 'error', 'message': 'Address is required'}), 400
    
    if not email and not ref_code:
        return jsonify({'status': 'error', 'message': 'Email or ref_code is required'}), 400
    
    # Resolve ref_code to email if needed
    if ref_code and not email:
        email = resolve_ref_code_to_email(ref_code)
        if not email:
            return jsonify({'status': 'error', 'message': 'Invalid ref code'}), 400
    
    # Get client IP
    ip_address = get_client_ip()
    
    # Check limits (5 per 24 hours per email or IP)
    lookup_count = count_recent_lookups(email=email, ip_address=ip_address)
    if lookup_count >= 5:
        return jsonify({
            'status': 'limit_exceeded',
            'message': "You've reached the search limit. Book a demo for unlimited access."
        })
    
    # Call internal lookup
    try:
        utility_list = [u.strip() for u in utilities.split(',')]
        skip_internet = 'internet' not in utility_list
        result = lookup_utilities_by_address(address, selected_utilities=utility_list, skip_internet=skip_internet)
        
        # Format response - use format_utility for consistent output
        formatted_results = {}
        location = result.get('location', {}) if result else {}
        city = location.get('city')
        state = location.get('state')
        
        for util_type in utility_list:
            util_data = result.get(util_type) if result else None
            if util_data:
                # Internet has different structure (providers array with 'providers' key)
                if util_type == 'internet' and isinstance(util_data, dict) and 'providers' in util_data:
                    formatted_results[util_type] = [
                        {
                            'name': p.get('name', ''),
                            'technology': p.get('technology', ''),
                            'max_download_mbps': p.get('max_download_mbps', 0),
                            'max_upload_mbps': p.get('max_upload_mbps', 0)
                        }
                        for p in util_data.get('providers', [])[:5]  # Top 5 providers
                    ]
                # Other utilities - use format_utility for consistent formatting
                elif isinstance(util_data, list) and len(util_data) > 0:
                    formatted = format_utility(util_data[0], util_type, city, state)
                    formatted_results[util_type] = [{
                        'name': formatted.get('name', ''),
                        'phone': formatted.get('phone', ''),
                        'website': formatted.get('website') or formatted.get('service_check_url', '')
                    }]
                elif isinstance(util_data, dict):
                    formatted = format_utility(util_data, util_type, city, state)
                    formatted_results[util_type] = [{
                        'name': formatted.get('name', ''),
                        'phone': formatted.get('phone', ''),
                        'website': formatted.get('website') or formatted.get('service_check_url', '')
                    }]
                else:
                    formatted_results[util_type] = []
            else:
                formatted_results[util_type] = []
        
        # Log to Airtable
        log_leadgen_lookup(ref_code, email, ip_address, address, utilities, formatted_results)
        
        searches_remaining = max(0, 5 - lookup_count - 1)
        
        return jsonify({
            'status': 'success',
            'utilities': formatted_results,
            'searches_remaining': searches_remaining
        })
        
    except Exception as e:
        logger.error(f"Leadgen lookup error: {e}")
        return jsonify({'status': 'error', 'message': 'Lookup failed'}), 500


@app.route('/api/leadgen/check-limit', methods=['GET'])
def leadgen_check_limit():
    """Check if user can search before they try."""
    email = request.args.get('email')
    ref_code = request.args.get('ref')
    
    # Resolve ref_code to email if needed
    if ref_code and not email:
        email = resolve_ref_code_to_email(ref_code)
    
    ip_address = get_client_ip()
    
    lookup_count = count_recent_lookups(email=email, ip_address=ip_address)
    searches_remaining = max(0, 5 - lookup_count)
    
    return jsonify({
        'can_search': searches_remaining > 0,
        'searches_remaining': searches_remaining
    })


@app.route('/api/leadgen/resolve-ref', methods=['GET'])
def leadgen_resolve_ref():
    """Resolve a ref code to its associated email."""
    ref_code = request.args.get('ref')
    
    if not ref_code:
        return jsonify({'error': 'ref parameter required'}), 400
    
    email = resolve_ref_code_to_email(ref_code)
    
    if email:
        return jsonify({'email': email})
    else:
        return jsonify({'error': 'Invalid ref code'}), 404


@app.route('/api/leadgen/track-cta', methods=['POST'])
def leadgen_track_cta():
    """Track when someone clicks the CTA button."""
    data = request.get_json() or {}
    email = data.get('email')
    ref_code = data.get('ref_code')
    
    if not email and not ref_code:
        return jsonify({'error': 'email or ref_code required'}), 400
    
    if not AIRTABLE_API_KEY:
        return jsonify({'success': True})  # Silently succeed if no Airtable
    
    try:
        # Find most recent record matching email or ref_code
        url = airtable_url(LEADGEN_LOOKUPS_TABLE_ID)
        conditions = []
        if email:
            conditions.append(f"{{email}}='{email}'")
        if ref_code:
            conditions.append(f"{{ref_code}}='{ref_code}'")
        
        formula = f"OR({','.join(conditions)})"
        params = {
            'filterByFormula': formula,
            'sort[0][field]': 'created_at',
            'sort[0][direction]': 'desc',
            'maxRecords': 1
        }
        
        resp = requests.get(url, headers=get_airtable_headers(), params=params, timeout=10)
        if resp.status_code == 200:
            records = resp.json().get('records', [])
            if records:
                record_id = records[0]['id']
                # Update cta_clicked
                update_url = f"{url}/{record_id}"
                requests.patch(update_url, headers=get_airtable_headers(), 
                             json={'fields': {'cta_clicked': True}}, timeout=10)
        
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error tracking CTA: {e}")
        return jsonify({'success': True})  # Don't fail the request


@app.route('/api/leadgen/generate-ref', methods=['POST'])
def leadgen_generate_ref():
    """Generate a new ref code for cold email campaigns."""
    data = request.get_json() or {}
    email = data.get('email')
    campaign = data.get('campaign', '')
    
    if not email:
        return jsonify({'error': 'email required'}), 400
    
    if not AIRTABLE_API_KEY:
        return jsonify({'error': 'Airtable not configured'}), 500
    
    try:
        # Generate unique ref code
        for _ in range(10):  # Try up to 10 times to avoid collisions
            ref_code = generate_ref_code()
            
            # Check for collision
            existing = resolve_ref_code_to_email(ref_code)
            if not existing:
                break
        else:
            return jsonify({'error': 'Could not generate unique ref code'}), 500
        
        # Insert into Airtable
        url = airtable_url(LEADGEN_REFCODES_TABLE_ID)
        data = {
            'fields': {
                'ref_code': ref_code,
                'email': email,
                'campaign': campaign,
                'created_at': datetime.utcnow().isoformat()
            }
        }
        resp = requests.post(url, headers=get_airtable_headers(), json=data, timeout=10)
        
        if resp.status_code in [200, 201]:
            return jsonify({
                'ref_code': ref_code,
                'url': f'https://www.utilityprofit.com/utility-lookup?ref={ref_code}'
            })
        else:
            return jsonify({'error': 'Failed to create ref code'}), 500
            
    except Exception as e:
        logger.error(f"Error generating ref code: {e}")
        return jsonify({'error': 'Failed to generate ref code'}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)# Version: 1768787780
