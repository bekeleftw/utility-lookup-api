#!/usr/bin/env python3
"""
Flask API for Utility Lookup
Run with: python api.py
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from utility_lookup import lookup_utilities_by_address, lookup_utility_json
from state_utility_verification import check_problem_area, add_problem_area, load_problem_areas
from special_districts import lookup_special_district, format_district_for_response, get_available_states, has_special_district_data
from datetime import datetime
import hashlib
import json
import os
import re

# Feedback storage
FEEDBACK_DIR = os.path.join(os.path.dirname(__file__), 'data', 'feedback')

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

app = Flask(__name__)
CORS(app)  # Allow cross-origin requests from Webflow

@app.route('/api/lookup', methods=['GET', 'POST'])
def lookup():
    """Look up utilities for an address."""
    if request.method == 'POST':
        data = request.get_json()
        address = data.get('address')
        # SERP verification is now enabled by default
        verify = data.get('verify', True)
        # Parse utilities parameter - default to all if not specified
        utilities_param = data.get('utilities', 'electric,gas,water,internet')
    else:
        address = request.args.get('address')
        # SERP verification is now enabled by default (pass verify=false to disable)
        verify = request.args.get('verify', 'true').lower() != 'false'
        # Parse utilities parameter - default to all if not specified
        utilities_param = request.args.get('utilities', 'electric,gas,water,internet')
    
    # Parse comma-separated utilities into list
    selected_utilities = [u.strip().lower() for u in utilities_param.split(',')]
    
    if not address:
        return jsonify({'error': 'Address is required'}), 400
    
    try:
        result = lookup_utilities_by_address(address, verify_with_serp=verify, selected_utilities=selected_utilities)
        if not result:
            return jsonify({'error': 'Could not geocode address'}), 404
        
        # Format response
        response = {
            'address': address,
            'location': result.get('location', {}),
            'utilities': {}
        }
        
        # Electric - only if selected
        if 'electric' in selected_utilities:
            electric = result.get('electric')
            if electric:
                if isinstance(electric, list):
                    response['utilities']['electric'] = [format_utility(e, 'electric') for e in electric]
                    primary = electric[0]
                else:
                    response['utilities']['electric'] = [format_utility(electric, 'electric')]
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
                    response['utilities']['gas'] = [format_utility(g, 'gas') for g in gas]
                    primary = gas[0]
                else:
                    response['utilities']['gas'] = [format_utility(gas, 'gas')]
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
                response['utilities']['water'] = [format_utility(water, 'water')]
                w = water
                if w.get('_confidence') == 'medium':
                    response['utilities']['water_note'] = f"Matched by county - multiple water systems serve this area. {w.get('_note', '')}"
                elif w.get('_confidence') == 'low':
                    response['utilities']['water_note'] = w.get('_note', 'Estimated based on city name - verify with local utility.')
        
        # Internet - only if selected
        if 'internet' in selected_utilities:
            internet = result.get('internet')
            if internet:
                response['utilities']['internet'] = format_internet_providers(internet)
                if internet.get('has_fiber'):
                    response['utilities']['internet_note'] = f"Fiber available from {internet.get('best_wired', {}).get('name', 'provider')}."
                elif internet.get('has_cable'):
                    response['utilities']['internet_note'] = "Cable internet available. No fiber service found at this address."
                else:
                    response['utilities']['internet_note'] = "Limited wired options. DSL, fixed wireless, or satellite may be available."
            else:
                response['utilities']['internet_note'] = "Could not retrieve internet provider data from FCC."
        
        return jsonify(response)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def format_utility(util, util_type):
    """Format utility data for API response."""
    if util_type == 'water':
        return {
            'name': util.get('name', 'Unknown'),
            'phone': util.get('phone'),
            'website': util.get('website'),
            'address': util.get('address'),
            'city': util.get('city'),
            'state': util.get('state'),
            'zip': util.get('zip'),
            'id': util.get('id'),
            'population_served': util.get('population_served'),
            'source_type': util.get('source_type'),
            'confidence': util.get('_confidence', 'high'),
            'verified': util.get('_serp_verified', False)
        }
    else:
        return {
            'name': util.get('NAME', util.get('name', 'Unknown')),
            'phone': util.get('TELEPHONE', util.get('phone')),
            'website': util.get('WEBSITE', util.get('website')),
            'address': util.get('ADDRESS', util.get('address')),
            'city': util.get('CITY', util.get('city')),
            'state': util.get('STATE', util.get('state')),
            'zip': util.get('ZIP', util.get('zip')),
            'id': util.get('ID') or util.get('SVCTERID') or util.get('id'),
            'type': util.get('TYPE'),
            'confidence': util.get('_confidence', 'high' if util_type == 'electric' else 'medium'),
            'verified': util.get('_serp_verified', False)
        }


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
def health():
    """Health check endpoint."""
    return jsonify({'status': 'ok'})


@app.route('/api/batch', methods=['POST'])
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
    required = ['address', 'utility_type', 'returned_provider', 'correct_provider']
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
    
    # Generate feedback ID
    feedback_id = 'fb_' + hashlib.md5(
        f"{data['address']}_{data['utility_type']}_{datetime.now().isoformat()}".encode()
    ).hexdigest()[:12]
    
    # Create feedback record
    feedback_record = {
        "feedback_id": feedback_id,
        "address": data['address'],
        "zip_code": zip_code,
        "city": city,
        "state": state,
        "utility_type": data['utility_type'],
        "returned_provider": data['returned_provider'],
        "correct_provider": data['correct_provider'],
        "source": data.get('source', 'unknown'),
        "email": data.get('email'),
        "submitted_at": datetime.now().isoformat(),
        "status": "pending",
        "confirmation_count": 1,
        "addresses": [data['address']]
    }
    
    # Load pending feedback
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
    """
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
        "summary": {
            "pending_count": len(pending),
            "confirmed_count": len(confirmed),
            "total_feedback": len(pending) + len(confirmed)
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
    """
    lat = request.args.get('lat', type=float)
    lon = request.args.get('lon', type=float)
    state = request.args.get('state', '').upper()
    zip_code = request.args.get('zip')
    subdivision = request.args.get('subdivision')
    service = request.args.get('service', 'water')
    
    if not state:
        return jsonify({'error': 'state is required'}), 400
    
    if not has_special_district_data(state):
        return jsonify({
            'found': False,
            'message': f'No special district data available for {state}',
            'available_states': get_available_states()
        })
    
    result = lookup_special_district(
        lat=lat,
        lon=lon,
        state=state,
        zip_code=zip_code,
        subdivision=subdivision,
        service=service
    )
    
    if result:
        return jsonify({
            'found': True,
            'district': format_district_for_response(result)
        })
    else:
        return jsonify({
            'found': False,
            'message': 'No special district found for this location'
        })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)