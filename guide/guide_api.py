"""
API endpoints for the Resident Guide feature.
Integrates with the main Flask app in api.py.
"""

import os
import json
import secrets
import string
from datetime import datetime
from typing import Optional, Dict
from flask import Blueprint, request, jsonify, render_template_string
import logging

logger = logging.getLogger(__name__)

# Create Blueprint for guide routes
guide_bp = Blueprint('guide', __name__)

# Database connection (will be set by main app)
_db_connection = None

def set_db_connection(conn):
    """Set the database connection for guide operations."""
    global _db_connection
    _db_connection = conn


def generate_short_code(length: int = 8) -> str:
    """Generate a random alphanumeric short code."""
    alphabet = string.ascii_lowercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def parse_address_components(address: str) -> Dict:
    """Parse address into components."""
    import re
    
    components = {
        "street": None,
        "city": None,
        "state": None,
        "zip": None
    }
    
    # Try to parse standard US address format
    # "123 Main St, City, ST 12345"
    match = re.match(
        r'^(.+?),\s*(.+?),\s*([A-Z]{2})\s*(\d{5}(?:-\d{4})?)?',
        address,
        re.IGNORECASE
    )
    
    if match:
        components["street"] = match.group(1).strip()
        components["city"] = match.group(2).strip()
        components["state"] = match.group(3).upper()
        components["zip"] = match.group(4) if match.group(4) else None
    
    return components


@guide_bp.route('/api/guide/request', methods=['POST'])
def request_guide():
    """
    Submit a guide request.
    
    Request body:
    {
        "address": "4521 Riverside Drive, Unit 204, Austin, TX 78741",
        "utility_results": { ... },  // from lookup tool
        "email": "pm@company.com",
        "company_name": "ABC Property Management",
        "website": "https://abcproperties.com"  // optional
    }
    
    Response:
    {
        "success": true,
        "message": "Your guide will be emailed in 5-10 minutes.",
        "request_id": "uuid"
    }
    """
    data = request.get_json()
    
    # Validate required fields (utility_results is optional - will fetch if not provided)
    required_fields = ['address', 'email', 'company_name']
    for field in required_fields:
        if not data.get(field):
            return jsonify({
                'success': False,
                'error': f'Missing required field: {field}'
            }), 400
    
    # Validate email format
    import re
    email = data['email']
    if not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
        return jsonify({
            'success': False,
            'error': 'Invalid email format'
        }), 400
    
    # Validate company name length
    company_name = data['company_name']
    if len(company_name) > 100:
        return jsonify({
            'success': False,
            'error': 'Company name must be 100 characters or less'
        }), 400
    
    # Validate website URL if provided
    website = data.get('website')
    if website:
        if not re.match(r'^https?://', website):
            website = 'https://' + website
        # Basic URL validation
        if not re.match(r'^https?://[^\s/$.?#].[^\s]*$', website):
            return jsonify({
                'success': False,
                'error': 'Invalid website URL'
            }), 400
    
    # Parse address components
    address = data['address']
    address_components = parse_address_components(address)
    
    try:
        # Insert guide request into database
        if _db_connection:
            cursor = _db_connection.cursor()
            cursor.execute("""
                INSERT INTO guide_requests 
                (address, address_components, utility_results, email, company_name, website, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'pending')
                RETURNING id
            """, (
                address,
                json.dumps(address_components),
                json.dumps(data['utility_results']),
                email,
                company_name,
                website
            ))
            request_id = cursor.fetchone()[0]
            _db_connection.commit()
            
            # Queue background job
            # TODO: Implement Redis/RQ job queue
            # For now, we'll process synchronously in development
            from .job_processor import process_guide_request
            # In production: queue.enqueue(process_guide_request, request_id)
            
            logger.info(f"Guide request created: {request_id}")
            
            return jsonify({
                'success': True,
                'message': f'Your resident guide for {address} will be emailed to {email} in 5-10 minutes.',
                'request_id': str(request_id)
            })
        else:
            # No database - return mock response for testing
            logger.warning("No database connection - returning mock response")
            return jsonify({
                'success': True,
                'message': f'Your resident guide for {address} will be emailed to {email} in 5-10 minutes.',
                'request_id': 'mock-' + generate_short_code()
            })
            
    except Exception as e:
        logger.error(f"Failed to create guide request: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to process request. Please try again.'
        }), 500


@guide_bp.route('/api/guide/status/<request_id>', methods=['GET'])
def get_guide_status(request_id: str):
    """
    Check status of a guide request.
    
    Response:
    {
        "status": "completed",
        "short_code": "abc12345",
        "shareable_url": "https://utilityprofit.com/u/abc12345",
        "pdf_url": "https://..."
    }
    """
    if not _db_connection:
        return jsonify({'error': 'Database not available'}), 503
    
    try:
        cursor = _db_connection.cursor()
        
        # Get request status
        cursor.execute("""
            SELECT gr.status, gr.error_message, go.short_code, go.pdf_url
            FROM guide_requests gr
            LEFT JOIN guide_outputs go ON go.guide_request_id = gr.id
            WHERE gr.id = %s
        """, (request_id,))
        
        row = cursor.fetchone()
        if not row:
            return jsonify({'error': 'Request not found'}), 404
        
        status, error_message, short_code, pdf_url = row
        
        response = {'status': status}
        
        if status == 'failed' and error_message:
            response['error'] = error_message
        
        if status == 'completed' and short_code:
            base_url = os.getenv('BASE_URL', 'https://utilityprofit.com')
            response['short_code'] = short_code
            response['shareable_url'] = f'{base_url}/u/{short_code}'
            response['pdf_url'] = pdf_url
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Failed to get guide status: {e}")
        return jsonify({'error': 'Failed to retrieve status'}), 500


# Shareable guide page template
SHAREABLE_PAGE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Utility Setup Guide - {{ address }}</title>
    <style>
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background: #f5f5f5;
            color: #333;
            line-height: 1.5;
        }
        
        .container {
            max-width: 600px;
            margin: 0 auto;
            background: white;
            min-height: 100vh;
        }
        
        .header {
            padding: 20px;
            border-bottom: 3px solid #7AC143;
            display: flex;
            align-items: center;
            gap: 15px;
        }
        
        .header img {
            max-height: 40px;
            max-width: 150px;
        }
        
        .header-text {
            flex: 1;
        }
        
        .company-name {
            font-weight: 600;
            font-size: 16px;
        }
        
        .guide-title {
            font-size: 12px;
            color: #666;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        .address-block {
            padding: 20px;
            background: #f9f9f9;
            border-bottom: 1px solid #eee;
        }
        
        .address-label {
            font-size: 11px;
            color: #666;
            text-transform: uppercase;
            margin-bottom: 5px;
        }
        
        .address {
            font-size: 18px;
            font-weight: 500;
        }
        
        .utility-section {
            border-bottom: 1px solid #eee;
        }
        
        .utility-header {
            padding: 15px 20px;
            display: flex;
            align-items: center;
            gap: 12px;
            cursor: pointer;
            background: white;
        }
        
        .utility-header:hover {
            background: #fafafa;
        }
        
        .utility-icon {
            font-size: 24px;
        }
        
        .utility-info {
            flex: 1;
        }
        
        .utility-type {
            font-size: 11px;
            color: #666;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        .utility-name {
            font-size: 16px;
            font-weight: 600;
        }
        
        .utility-contact {
            font-size: 13px;
            color: #555;
        }
        
        .utility-contact a {
            color: #7AC143;
            text-decoration: none;
        }
        
        .expand-icon {
            font-size: 20px;
            color: #999;
            transition: transform 0.2s;
        }
        
        .utility-section.expanded .expand-icon {
            transform: rotate(180deg);
        }
        
        .utility-details {
            display: none;
            padding: 0 20px 20px 56px;
        }
        
        .utility-section.expanded .utility-details {
            display: block;
        }
        
        .detail-section {
            margin-bottom: 15px;
        }
        
        .detail-title {
            font-size: 11px;
            font-weight: 600;
            color: #666;
            text-transform: uppercase;
            margin-bottom: 8px;
        }
        
        .steps {
            padding-left: 20px;
        }
        
        .steps li {
            margin-bottom: 5px;
            font-size: 14px;
        }
        
        .requirements {
            padding-left: 20px;
            list-style-type: disc;
        }
        
        .requirements li {
            margin-bottom: 3px;
            font-size: 14px;
        }
        
        .info-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
        }
        
        .info-item {
            background: #f5f5f5;
            padding: 10px;
            border-radius: 6px;
        }
        
        .info-label {
            font-size: 10px;
            color: #666;
            text-transform: uppercase;
        }
        
        .info-value {
            font-size: 13px;
            font-weight: 500;
        }
        
        .signup-btn {
            display: inline-block;
            margin-top: 10px;
            padding: 10px 20px;
            background: #7AC143;
            color: white;
            text-decoration: none;
            border-radius: 6px;
            font-weight: 500;
            font-size: 14px;
        }
        
        .signup-btn:hover {
            background: #6ab038;
        }
        
        .deregulated-banner {
            margin: 15px 0;
            padding: 15px;
            background: #fff8e6;
            border: 1px solid #ffd966;
            border-radius: 8px;
        }
        
        .deregulated-title {
            font-weight: 600;
            color: #b8860b;
            margin-bottom: 8px;
        }
        
        .deregulated-content {
            font-size: 13px;
        }
        
        .footer {
            padding: 20px;
            text-align: center;
            font-size: 12px;
            color: #999;
        }
        
        .footer-brand {
            margin-top: 10px;
            padding-top: 10px;
            border-top: 1px solid #eee;
        }
        
        .footer-brand a {
            color: #7AC143;
            text-decoration: none;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            {% if logo_url %}
            <img src="{{ logo_url }}" alt="{{ company_name }}">
            {% endif %}
            <div class="header-text">
                <div class="company-name">{{ company_name }}</div>
                <div class="guide-title">Utility Setup Guide</div>
            </div>
        </div>
        
        <div class="address-block">
            <div class="address-label">Property Address</div>
            <div class="address">{{ address }}</div>
        </div>
        
        {% for utility in utilities %}
        <div class="utility-section" data-utility="{{ utility.type }}">
            <div class="utility-header" onclick="toggleSection(this.parentElement)">
                <span class="utility-icon">{{ utility.icon }}</span>
                <div class="utility-info">
                    <div class="utility-type">{{ utility.type }}</div>
                    <div class="utility-name">{{ utility.name }}</div>
                    <div class="utility-contact">
                        {% if utility.phone %}
                        <a href="tel:{{ utility.phone }}">{{ utility.phone }}</a>
                        {% endif %}
                        {% if utility.phone and utility.website %} · {% endif %}
                        {% if utility.website %}
                        <a href="{{ utility.website }}" target="_blank">Website</a>
                        {% endif %}
                    </div>
                </div>
                <span class="expand-icon">▼</span>
            </div>
            
            <div class="utility-details">
                {% if utility.instructions.steps %}
                <div class="detail-section">
                    <div class="detail-title">How to Start Service</div>
                    <ol class="steps">
                        {% for step in utility.instructions.steps %}
                        <li>{{ step }}</li>
                        {% endfor %}
                    </ol>
                </div>
                {% endif %}
                
                {% if utility.instructions.required_documents %}
                <div class="detail-section">
                    <div class="detail-title">What You'll Need</div>
                    <ul class="requirements">
                        {% for doc in utility.instructions.required_documents %}
                        <li>{{ doc }}</li>
                        {% endfor %}
                    </ul>
                </div>
                {% endif %}
                
                <div class="info-grid">
                    {% if utility.instructions.deposit %}
                    <div class="info-item">
                        <div class="info-label">Deposit</div>
                        <div class="info-value">{{ utility.instructions.deposit.amount or 'May be required' }}</div>
                    </div>
                    {% endif %}
                    {% if utility.instructions.timeline %}
                    <div class="info-item">
                        <div class="info-label">Timeline</div>
                        <div class="info-value">{{ utility.instructions.timeline }}</div>
                    </div>
                    {% endif %}
                </div>
                
                {% if utility.instructions.online_signup_url %}
                <a href="{{ utility.instructions.online_signup_url }}" class="signup-btn" target="_blank">
                    Start Service →
                </a>
                {% endif %}
            </div>
        </div>
        
        {% if utility.type == 'electric' and deregulated_explainer %}
        <div class="deregulated-banner">
            <div class="deregulated-title">{{ deregulated_explainer.title }}</div>
            <div class="deregulated-content">
                {{ deregulated_explainer.intro }}
                <br><br>
                <a href="{{ deregulated_explainer.comparison_site.url }}" target="_blank">
                    Compare plans at {{ deregulated_explainer.comparison_site.name }} →
                </a>
            </div>
        </div>
        {% endif %}
        {% endfor %}
        
        <div class="footer">
            Generated {{ generated_date }}
            <div class="footer-brand">
                Powered by <a href="https://utilityprofit.com">Utility Profit</a>
            </div>
        </div>
    </div>
    
    <script>
        function toggleSection(section) {
            section.classList.toggle('expanded');
        }
    </script>
</body>
</html>
"""


@guide_bp.route('/u/<short_code>')
def view_guide(short_code: str):
    """
    Serve the shareable guide page.
    """
    if not _db_connection:
        return "Service temporarily unavailable", 503
    
    try:
        cursor = _db_connection.cursor()
        
        # Get guide data
        cursor.execute("""
            SELECT go.guide_data, gr.address, gr.company_name, gr.logo_url, gr.website
            FROM guide_outputs go
            JOIN guide_requests gr ON gr.id = go.guide_request_id
            WHERE go.short_code = %s
        """, (short_code,))
        
        row = cursor.fetchone()
        if not row:
            return "Guide not found", 404
        
        guide_data, address, company_name, logo_url, website = row
        
        if isinstance(guide_data, str):
            guide_data = json.loads(guide_data)
        
        # Prepare template data
        icons = {
            "electric": "⚡",
            "gas": "🔥",
            "water": "💧",
            "internet": "📶"
        }
        
        utilities = []
        for utility_type in ["electric", "gas", "water", "internet"]:
            utility_data = guide_data.get("utilities", {}).get(utility_type)
            if utility_data:
                if isinstance(utility_data, list):
                    for provider in utility_data:
                        utilities.append({
                            "type": utility_type,
                            "icon": icons.get(utility_type, "📋"),
                            "name": provider.get("name", "Unknown"),
                            "phone": provider.get("phone"),
                            "website": provider.get("website"),
                            "instructions": provider.get("instructions", {})
                        })
                else:
                    utilities.append({
                        "type": utility_type,
                        "icon": icons.get(utility_type, "📋"),
                        "name": utility_data.get("name", "Unknown"),
                        "phone": utility_data.get("phone"),
                        "website": utility_data.get("website"),
                        "instructions": utility_data.get("instructions", {})
                    })
        
        return render_template_string(
            SHAREABLE_PAGE_TEMPLATE,
            address=address,
            company_name=company_name,
            logo_url=logo_url,
            utilities=utilities,
            deregulated_explainer=guide_data.get("deregulated_explainer"),
            generated_date=datetime.now().strftime("%B %d, %Y")
        )
        
    except Exception as e:
        logger.error(f"Failed to render guide page: {e}")
        return "Error loading guide", 500
