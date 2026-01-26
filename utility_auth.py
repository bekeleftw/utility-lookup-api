"""
Utility Lookup Authentication and Usage Tracking
Integrates with Airtable for user management and usage logging.
"""

import os
import jwt
import bcrypt
import requests
from datetime import datetime, timedelta
from functools import wraps
from flask import Blueprint, request, jsonify
from collections import defaultdict

# Airtable configuration
AIRTABLE_API_KEY = os.getenv('AIRTABLE_API_KEY')
AIRTABLE_BASE_ID = os.getenv('AIRTABLE_BASE_ID')
JWT_SECRET = os.getenv('JWT_SECRET', 'utility-lookup-secret-key-change-in-production')

# Table names
USERS_TABLE = 'utility_users'
USAGE_LOG_TABLE = 'utility_usage_log'

utility_auth_bp = Blueprint('utility_auth', __name__)


def airtable_request(table: str, method: str = 'GET', record_id: str = None, 
                     data: dict = None, params: dict = None) -> dict:
    """Make a request to Airtable API."""
    if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID:
        raise ValueError("Airtable credentials not configured")
    
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{table}"
    if record_id:
        url += f"/{record_id}"
    
    headers = {
        'Authorization': f'Bearer {AIRTABLE_API_KEY}',
        'Content-Type': 'application/json'
    }
    
    if method == 'GET':
        response = requests.get(url, headers=headers, params=params)
    elif method == 'POST':
        response = requests.post(url, headers=headers, json=data)
    elif method == 'PATCH':
        response = requests.patch(url, headers=headers, json=data)
    else:
        raise ValueError(f"Unsupported method: {method}")
    
    response.raise_for_status()
    return response.json()


def hash_password(plain: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a password against its hash."""
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


def create_token(email: str, name: str, is_admin: bool) -> str:
    """Create a JWT token for a user."""
    payload = {
        "email": email,
        "name": name,
        "is_admin": is_admin,
        "exp": datetime.utcnow() + timedelta(days=30)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def verify_token(token: str) -> dict | None:
    """Verify and decode a JWT token."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        return None


def require_auth(f):
    """Decorator to require authentication."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]
        else:
            token = request.json.get('token') if request.is_json else None
        
        if not token:
            return jsonify({"success": False, "error": "No token provided"}), 401
        
        user = verify_token(token)
        if not user:
            return jsonify({"success": False, "error": "Invalid or expired token"}), 401
        
        request.current_user = user
        return f(*args, **kwargs)
    return decorated


def require_admin(f):
    """Decorator to require admin privileges."""
    @wraps(f)
    @require_auth
    def decorated(*args, **kwargs):
        if not request.current_user.get('is_admin'):
            return jsonify({"success": False, "error": "Admin access required"}), 403
        return f(*args, **kwargs)
    return decorated


# ============================================
# AUTH ENDPOINTS
# ============================================

@utility_auth_bp.route('/api/utility-auth/debug', methods=['GET'])
def debug_config():
    """Debug endpoint to check configuration."""
    try:
        result = airtable_request(USERS_TABLE, params={'maxRecords': 1})
        # Get field names from first record
        fields = []
        sample_email = None
        if result.get('records'):
            fields = list(result['records'][0].get('fields', {}).keys())
            sample_email = result['records'][0].get('fields', {}).get('Email')
        return jsonify({
            "airtable_connected": True,
            "base_id_set": bool(AIRTABLE_BASE_ID),
            "api_key_set": bool(AIRTABLE_API_KEY),
            "jwt_secret_set": bool(JWT_SECRET),
            "sample_record": bool(result.get('records')),
            "field_names": fields,
            "record_count": len(result.get('records', [])),
            "sample_email": sample_email
        })
    except Exception as e:
        return jsonify({
            "airtable_connected": False,
            "error": str(e),
            "base_id_set": bool(AIRTABLE_BASE_ID),
            "api_key_set": bool(AIRTABLE_API_KEY)
        })

@utility_auth_bp.route('/api/utility-auth/test-query', methods=['GET'])
def test_query():
    """Test the user query and password verification."""
    email = request.args.get('email', 'mark@utilityprofit.com').lower()
    test_password = request.args.get('password', '')
    try:
        params = {
            'filterByFormula': f"AND(LOWER({{Email}}) = '{email}', {{is_active}} = TRUE())"
        }
        result = airtable_request(USERS_TABLE, params=params)
        records = result.get('records', [])
        
        if not records:
            return jsonify({"error": "User not found", "email": email})
        
        fields = records[0].get('fields', {})
        password_hash = fields.get('password_hash', '')
        
        # Test password verification if password provided
        password_valid = None
        if test_password:
            try:
                password_valid = verify_password(test_password, password_hash)
            except Exception as e:
                password_valid = f"Error: {str(e)}"
        
        return jsonify({
            "email": email,
            "found": True,
            "has_password_hash": bool(password_hash),
            "hash_length": len(password_hash),
            "hash_prefix": password_hash[:20] if password_hash else None,
            "password_valid": password_valid
        })
    except Exception as e:
        return jsonify({"error": str(e)})

@utility_auth_bp.route('/api/utility-auth/login', methods=['POST'])
def login():
    """Authenticate user and return JWT token."""
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        
        if not email or not password:
            return jsonify({"success": False, "error": "Email and password required"})
        
        # Query Airtable for user (Note: Airtable field is "Email" with capital E)
        params = {
            'filterByFormula': f"AND(LOWER({{Email}}) = '{email}', {{is_active}} = TRUE())"
        }
        result = airtable_request(USERS_TABLE, params=params)
        records = result.get('records', [])
        
        if not records:
            return jsonify({"success": False, "error": "Invalid email or password"})
        
        user_record = records[0]
        fields = user_record.get('fields', {})
        password_hash = fields.get('password_hash', '')
        
        if not verify_password(password, password_hash):
            return jsonify({"success": False, "error": "Invalid email or password"})
        
        # Update last_login
        airtable_request(
            USERS_TABLE, 
            method='PATCH', 
            record_id=user_record['id'],
            data={"fields": {"last_login": datetime.utcnow().isoformat()}}
        )
        
        # Create token
        name = fields.get('name', email.split('@')[0])
        is_admin = fields.get('is_admin', False)
        token = create_token(email, name, is_admin)
        
        return jsonify({
            "success": True,
            "token": token,
            "user": {
                "email": email,
                "name": name,
                "is_admin": is_admin
            }
        })
        
    except Exception as e:
        print(f"Login error: {e}")
        return jsonify({"success": False, "error": "Login failed. Please try again."})


@utility_auth_bp.route('/api/utility-auth/verify', methods=['POST'])
def verify():
    """Verify if a token is still valid."""
    try:
        data = request.get_json()
        token = data.get('token', '')
        
        if not token:
            return jsonify({"valid": False})
        
        user = verify_token(token)
        if not user:
            return jsonify({"valid": False})
        
        return jsonify({
            "valid": True,
            "user": {
                "email": user.get('email'),
                "name": user.get('name'),
                "is_admin": user.get('is_admin', False)
            }
        })
        
    except Exception as e:
        print(f"Verify error: {e}")
        return jsonify({"valid": False})


# ============================================
# USAGE LOGGING ENDPOINTS
# ============================================

@utility_auth_bp.route('/api/utility-usage/log', methods=['POST'])
@require_auth
def log_usage():
    """Log a utility search."""
    try:
        data = request.get_json()
        user = request.current_user
        
        address = data.get('address', '')
        utilities_requested = data.get('utilities_requested', [])
        results = data.get('results', {})
        
        # Calculate average confidence
        confidences = []
        for util_type, util_data in results.items():
            if util_data and isinstance(util_data, dict):
                conf = util_data.get('confidence')
                if conf is not None:
                    confidences.append(conf)
        
        avg_confidence = sum(confidences) / len(confidences) if confidences else None
        
        # Prepare record for Airtable
        record_fields = {
            "user_email": user.get('email'),
            "timestamp": datetime.utcnow().isoformat(),
            "address": address,
            "utilities_requested": ','.join(utilities_requested) if isinstance(utilities_requested, list) else utilities_requested,
            "electric_provider": results.get('electric', {}).get('provider') if results.get('electric') else None,
            "gas_provider": results.get('gas', {}).get('provider') if results.get('gas') else None,
            "water_provider": results.get('water', {}).get('provider') if results.get('water') else None,
            "internet_providers": json.dumps(results.get('internet', {}).get('providers', [])) if results.get('internet') else None,
        }
        
        if avg_confidence is not None:
            record_fields["avg_confidence"] = avg_confidence
        
        # Remove None values
        record_fields = {k: v for k, v in record_fields.items() if v is not None}
        
        # Create record in Airtable
        result = airtable_request(
            USAGE_LOG_TABLE,
            method='POST',
            data={"fields": record_fields}
        )
        
        return jsonify({
            "success": True,
            "log_id": result.get('id')
        })
        
    except Exception as e:
        print(f"Log usage error: {e}")
        return jsonify({"success": False, "error": "Failed to log search"})


@utility_auth_bp.route('/api/utility-usage/feedback', methods=['POST'])
@require_auth
def submit_feedback():
    """Submit feedback for a logged search."""
    try:
        data = request.get_json()
        
        log_id = data.get('log_id')
        feedback = data.get('feedback')  # 'correct' or 'incorrect'
        details = data.get('details', '')
        
        if not log_id or not feedback:
            return jsonify({"success": False, "error": "log_id and feedback required"})
        
        if feedback not in ['correct', 'incorrect']:
            return jsonify({"success": False, "error": "feedback must be 'correct' or 'incorrect'"})
        
        # Update record in Airtable
        update_fields = {"feedback": feedback}
        if details:
            update_fields["feedback_details"] = details
        
        airtable_request(
            USAGE_LOG_TABLE,
            method='PATCH',
            record_id=log_id,
            data={"fields": update_fields}
        )
        
        return jsonify({"success": True})
        
    except Exception as e:
        print(f"Feedback error: {e}")
        return jsonify({"success": False, "error": "Failed to submit feedback"})


# ============================================
# ADMIN STATS ENDPOINT
# ============================================

@utility_auth_bp.route('/api/utility-usage/stats', methods=['GET'])
@require_admin
def get_stats():
    """Get usage statistics (admin only)."""
    try:
        # Fetch all usage logs from Airtable (paginated)
        all_records = []
        offset = None
        
        while True:
            params = {}
            if offset:
                params['offset'] = offset
            
            result = airtable_request(USAGE_LOG_TABLE, params=params)
            all_records.extend(result.get('records', []))
            
            offset = result.get('offset')
            if not offset:
                break
        
        # Fetch all users for name lookup
        users_result = airtable_request(USERS_TABLE)
        user_names = {}
        for record in users_result.get('records', []):
            fields = record.get('fields', {})
            email = fields.get('email', '').lower()
            user_names[email] = fields.get('name', email.split('@')[0])
        
        # Aggregate stats by user
        by_user = defaultdict(lambda: {
            "total_searches": 0,
            "addresses": set(),
            "by_type": {"electric": 0, "gas": 0, "water": 0, "internet": 0},
            "correct": 0,
            "incorrect": 0,
            "confidence_sum": 0,
            "confidence_count": 0,
            "last_active": None
        })
        
        for record in all_records:
            fields = record.get('fields', {})
            email = (fields.get('user_email') or '').lower()
            if not email:
                continue
            
            u = by_user[email]
            u["total_searches"] += 1
            
            address = fields.get('address', '')
            if address:
                u["addresses"].add(address)
            
            # Count by type
            utilities_str = fields.get('utilities_requested', '')
            for utype in utilities_str.split(','):
                utype = utype.strip().lower()
                if utype in u["by_type"]:
                    u["by_type"][utype] += 1
            
            # Feedback
            feedback = fields.get('feedback')
            if feedback == 'correct':
                u["correct"] += 1
            elif feedback == 'incorrect':
                u["incorrect"] += 1
            
            # Confidence
            avg_conf = fields.get('avg_confidence')
            if avg_conf is not None:
                u["confidence_sum"] += avg_conf
                u["confidence_count"] += 1
            
            # Last active
            ts = fields.get('timestamp')
            if ts and (not u["last_active"] or ts > u["last_active"]):
                u["last_active"] = ts
        
        # Format output
        users = []
        for email, u in by_user.items():
            total_feedback = u["correct"] + u["incorrect"]
            users.append({
                "email": email,
                "name": user_names.get(email, email.split('@')[0]),
                "total_searches": u["total_searches"],
                "unique_addresses": len(u["addresses"]),
                "searches_by_type": u["by_type"],
                "feedback_given": total_feedback,
                "marked_correct": u["correct"],
                "marked_incorrect": u["incorrect"],
                "accuracy_rate": u["correct"] / total_feedback if total_feedback > 0 else 0,
                "feedback_rate": total_feedback / u["total_searches"] if u["total_searches"] > 0 else 0,
                "avg_confidence": u["confidence_sum"] / u["confidence_count"] if u["confidence_count"] > 0 else 0,
                "last_active": u["last_active"]
            })
        
        # Sort by total searches descending
        users.sort(key=lambda x: x["total_searches"], reverse=True)
        
        # Calculate totals
        total_searches = sum(u["total_searches"] for u in users)
        total_correct = sum(u["marked_correct"] for u in users)
        total_feedback = sum(u["feedback_given"] for u in users)
        
        return jsonify({
            "success": True,
            "users": users,
            "totals": {
                "total_searches": total_searches,
                "total_users": len(users),
                "overall_accuracy": total_correct / total_feedback if total_feedback > 0 else 0,
                "overall_feedback_rate": total_feedback / total_searches if total_searches > 0 else 0
            }
        })
        
    except Exception as e:
        print(f"Stats error: {e}")
        return jsonify({"success": False, "error": "Failed to load statistics"})


# ============================================
# UTILITY: Create initial admin user
# ============================================

def create_admin_user(email: str, password: str, name: str):
    """
    Utility function to create an admin user.
    Run this once to set up the first admin.
    
    Usage:
        from utility_auth import create_admin_user
        create_admin_user('admin@example.com', 'securepassword', 'Admin User')
    """
    password_hash = hash_password(password)
    
    record_fields = {
        "email": email,
        "password_hash": password_hash,
        "name": name,
        "is_admin": True,
        "is_active": True,
        "created_at": datetime.utcnow().isoformat()
    }
    
    result = airtable_request(
        USERS_TABLE,
        method='POST',
        data={"fields": record_fields}
    )
    
    print(f"Created admin user: {email}")
    return result


# Need to import json for the internet_providers field
import json
