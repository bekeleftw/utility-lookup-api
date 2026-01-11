#!/usr/bin/env python3
"""
Flask API for Utility Lookup
Run with: python api.py
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from utility_lookup import lookup_utilities_by_address, lookup_utility_json

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
    else:
        address = request.args.get('address')
        # SERP verification is now enabled by default (pass verify=false to disable)
        verify = request.args.get('verify', 'true').lower() != 'false'
    
    if not address:
        return jsonify({'error': 'Address is required'}), 400
    
    try:
        result = lookup_utilities_by_address(address, verify_with_serp=verify)
        if not result:
            return jsonify({'error': 'Could not geocode address'}), 404
        
        # Format response
        response = {
            'address': address,
            'location': result.get('location', {}),
            'utilities': {}
        }
        
        # Electric - now verified with state-specific data
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
        
        # Gas - now verified with state-specific data
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
        
        # Water
        water = result.get('water')
        if water:
            response['utilities']['water'] = [format_utility(water, 'water')]
            w = water
            if w.get('_confidence') == 'medium':
                response['utilities']['water_note'] = f"Matched by county - multiple water systems serve this area. {w.get('_note', '')}"
            elif w.get('_confidence') == 'low':
                response['utilities']['water_note'] = w.get('_note', 'Estimated based on city name - verify with local utility.')
        
        # Internet (NEW)
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


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)