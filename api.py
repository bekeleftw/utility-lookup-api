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
        verify = data.get('verify', False)
    else:
        address = request.args.get('address')
        verify = request.args.get('verify', 'false').lower() == 'true'
    
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


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)