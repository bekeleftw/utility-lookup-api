"""
User-reported corrections - highest priority source.

Works for ALL utility types (electric, gas, water, internet).
Ground truth from actual tenants/residents.

Sources:
1. Airtable utility_corrections table (primary - synced from user feedback)
2. Local verified_addresses.json (fallback)
"""

import json
import os
import requests
from typing import List, Optional
from pathlib import Path

from pipeline.interfaces import (
    DataSource,
    UtilityType,
    LookupContext,
    SourceResult,
    SOURCE_CONFIDENCE,
)

# Airtable configuration
AIRTABLE_API_KEY = os.getenv('AIRTABLE_API_KEY')
AIRTABLE_BASE_ID = os.getenv('AIRTABLE_BASE_ID')
CORRECTIONS_TABLE = 'utility_corrections'


class UserCorrectionSource(DataSource):
    """
    User-reported corrections from Airtable and local JSON.
    
    Highest priority - ground truth from actual tenants/residents.
    Works for electric, gas, water, and internet.
    
    Priority:
    1. Airtable corrections (ZIP match)
    2. Local JSON exact address match
    3. Local JSON ZIP-level override
    """
    
    _corrections_cache = None
    _airtable_cache = None
    _airtable_cache_time = None
    
    @property
    def name(self) -> str:
        return "user_corrections"
    
    @property
    def supported_types(self) -> List[UtilityType]:
        return [UtilityType.ELECTRIC, UtilityType.GAS, UtilityType.WATER, UtilityType.INTERNET]
    
    @property
    def base_confidence(self) -> int:
        return 95  # High confidence - user verified (but allow other high-confidence sources to compete)
    
    def query(self, context: LookupContext) -> Optional[SourceResult]:
        """
        Check for user corrections.
        
        Priority:
        1. Airtable corrections by ZIP code
        2. Local JSON exact address match
        3. Local JSON ZIP-level override
        """
        utility_type_str = context.utility_type.value  # 'electric', 'gas', 'water', 'internet'
        
        # 1. Try Airtable corrections first (by ZIP)
        airtable_result = self._query_airtable(context.zip_code, context.city, context.state, utility_type_str)
        if airtable_result:
            return airtable_result
        
        # 2. Fall back to local JSON
        corrections = self._load_corrections()
        
        # Try exact address match (normalized to uppercase)
        address_key = self._normalize_address(context.address)
        addresses = corrections.get('addresses', {})
        
        if address_key in addresses:
            match = addresses[address_key]
            if utility_type_str in match:
                utility_name = match[utility_type_str]
                if isinstance(utility_name, str):
                    return self._build_result(
                        {'name': utility_name},
                        'exact_address',
                        f"User-verified correction for exact address"
                    )
                elif isinstance(utility_name, dict):
                    return self._build_result(
                        utility_name,
                        'exact_address',
                        f"User-verified correction for exact address"
                    )
        
        # Try ZIP-level override
        zip_overrides = corrections.get('zip_overrides', {})
        if context.zip_code and context.zip_code in zip_overrides:
            zip_data = zip_overrides[context.zip_code]
            if utility_type_str in zip_data:
                utility_data = zip_data[utility_type_str]
                if isinstance(utility_data, dict):
                    return self._build_result(
                        utility_data,
                        'zip_override',
                        f"ZIP {context.zip_code} override: {utility_data.get('note', 'user verified')}"
                    )
                elif isinstance(utility_data, str):
                    return self._build_result(
                        {'name': utility_data},
                        'zip_override',
                        f"ZIP {context.zip_code} override"
                    )
        
        return None
    
    def _query_airtable(self, zip_code: str, city: str, state: str, utility_type: str) -> Optional[SourceResult]:
        """Query Airtable utility_corrections table for matching corrections."""
        if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID:
            return None
        
        if not zip_code:
            return None
        
        try:
            # Query by ZIP code and utility type
            filter_formula = f"AND({{zip_code}} = '{zip_code}', {{utility_type}} = '{utility_type}')"
            
            response = requests.get(
                f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{CORRECTIONS_TABLE}",
                headers={'Authorization': f'Bearer {AIRTABLE_API_KEY}'},
                params={'filterByFormula': filter_formula, 'maxRecords': 5},
                timeout=5
            )
            
            if response.status_code != 200:
                return None
            
            records = response.json().get('records', [])
            
            if not records:
                # Try city-level match if no ZIP match
                filter_formula = f"AND({{city}} = '{city}', {{state}} = '{state}', {{utility_type}} = '{utility_type}')"
                response = requests.get(
                    f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{CORRECTIONS_TABLE}",
                    headers={'Authorization': f'Bearer {AIRTABLE_API_KEY}'},
                    params={'filterByFormula': filter_formula, 'maxRecords': 5},
                    timeout=5
                )
                if response.status_code == 200:
                    records = response.json().get('records', [])
            
            if not records:
                return None
            
            # Use the first matching correction (could add voting/count logic later)
            fields = records[0].get('fields', {})
            correct_provider = fields.get('correct_provider')
            
            if not correct_provider:
                return None
            
            # Calculate confidence boost based on number of matching corrections
            confidence_boost = min(len(records) * 5, 20)  # Up to +20 for multiple confirmations
            
            return SourceResult(
                source_name=self.name,
                utility_name=correct_provider,
                confidence_score=self.base_confidence + confidence_boost,
                match_type='user_feedback',
                raw_data={
                    '_selection_reason': f"User-verified correction (ZIP: {zip_code}, {len(records)} confirmation(s))",
                    '_correction_count': len(records),
                    '_source_address': fields.get('source_address'),
                    '_submitted_by': fields.get('submitted_by'),
                }
            )
            
        except Exception as e:
            print(f"Airtable correction query error: {e}")
            return None
    
    def _load_corrections(self) -> dict:
        """Load verified addresses from JSON with caching."""
        if UserCorrectionSource._corrections_cache is not None:
            return UserCorrectionSource._corrections_cache
        
        try:
            # Try multiple possible locations
            paths = [
                Path(__file__).parent.parent.parent / 'data' / 'verified_addresses.json',
                Path(__file__).parent.parent.parent / 'verified_addresses.json',
            ]
            
            for path in paths:
                if path.exists():
                    with open(path, 'r') as f:
                        UserCorrectionSource._corrections_cache = json.load(f)
                        return UserCorrectionSource._corrections_cache
            
            # No file found
            UserCorrectionSource._corrections_cache = {'addresses': {}, 'zip_overrides': {}}
            return UserCorrectionSource._corrections_cache
            
        except (FileNotFoundError, json.JSONDecodeError) as e:
            UserCorrectionSource._corrections_cache = {'addresses': {}, 'zip_overrides': {}}
            return UserCorrectionSource._corrections_cache
    
    def _normalize_address(self, address: str) -> str:
        """Normalize address for matching."""
        if not address:
            return ""
        return address.upper().strip()
    
    def _build_result(self, data: dict, match_type: str, reason: str) -> SourceResult:
        """Build SourceResult from correction data."""
        return SourceResult(
            source_name=self.name,
            utility_name=data.get('name'),
            confidence_score=self.base_confidence,
            match_type=match_type,
            phone=data.get('phone'),
            website=data.get('website'),
            raw_data={
                **data,
                '_selection_reason': reason,
                '_verified_date': data.get('verified_date'),
                '_verified_by': data.get('verified_by'),
            }
        )
    
    @classmethod
    def clear_cache(cls):
        """Clear the corrections cache (useful for testing)."""
        cls._corrections_cache = None
    
    @classmethod
    def add_correction(
        cls,
        address: str,
        utility_type: str,
        utility_name: str,
        phone: str = None,
        website: str = None,
        verified_by: str = 'user_report'
    ) -> bool:
        """
        Add a new correction to the database.
        
        Args:
            address: Full address (will be normalized)
            utility_type: 'electric', 'gas', or 'water'
            utility_name: Name of the utility provider
            phone: Contact phone number
            website: Provider website
            verified_by: Who verified this ('user_report', 'tenant', 'manual_check')
        
        Returns:
            True if correction was added successfully
        """
        from datetime import datetime
        
        try:
            path = Path(__file__).parent.parent.parent / 'data' / 'verified_addresses.json'
            
            # Load existing
            if path.exists():
                with open(path, 'r') as f:
                    data = json.load(f)
            else:
                data = {'addresses': {}, 'zip_overrides': {}}
            
            # Ensure structure
            if 'addresses' not in data:
                data['addresses'] = {}
            
            # Normalize address
            address_key = address.upper().strip()
            
            # Add or update
            if address_key not in data['addresses']:
                data['addresses'][address_key] = {}
            
            data['addresses'][address_key][utility_type] = {
                'name': utility_name,
                'phone': phone,
                'website': website,
                'verified_date': datetime.now().strftime('%Y-%m-%d'),
                'verified_by': verified_by,
            }
            
            # Save
            with open(path, 'w') as f:
                json.dump(data, f, indent=2)
            
            # Clear cache
            cls.clear_cache()
            
            return True
            
        except Exception as e:
            print(f"Error adding correction: {e}")
            return False
