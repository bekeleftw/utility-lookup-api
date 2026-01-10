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
        
        # Electric - now ranked with primary first
        electric = result.get('electric')
        if electric:
            if isinstance(electric, list):
                response['utilities']['electric'] = [format_utility(e, 'electric') for e in electric]
                if len(electric) > 1:
                    primary = electric[0]
                    others = electric[1:]
                    other_names = [e.get('NAME', 'Unknown') for e in others]
                    primary_name = primary.get('NAME', 'Unknown')
                    if primary.get('_serp_verified'):
                        response['utilities']['electric_note'] = f"Verified: {primary_name}. Other territories in area: {', '.join(other_names)}."
                    else:
                        response['utilities']['electric_note'] = f"Most likely: {primary_name} (ranked by location match). Other possibilities: {', '.join(other_names)}."
            else:
                response['utilities']['electric'] = [format_utility(electric, 'electric')]
        
        # Gas
        gas = result.get('gas')
        if gas:
            if isinstance(gas, list):
                response['utilities']['gas'] = [format_utility(g, 'gas') for g in gas]
                if len(gas) > 1:
                    names = [g.get('NAME', 'Unknown') for g in gas]
                    response['utilities']['gas_note'] = f"Multiple overlapping service territories found: {', '.join(names)}. The actual provider depends on exact location."
            else:
                response['utilities']['gas'] = [format_utility(gas, 'gas')]
                # Add notes for gas confidence issues
                g = gas
                if g.get('_source') == 'serp':
                    response['utilities']['gas_note'] = f"Found via web search (not in database). {g.get('_notes', '')}"
                elif g.get('_confidence') == 'medium' or not g.get('_serp_verified'):
                    response['utilities']['gas_note'] = "Gas data may be less accurate in some areas. Verify with the provider."
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


@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
