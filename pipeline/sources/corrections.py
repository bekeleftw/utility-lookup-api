"""
User-reported corrections - highest priority source.

Works for ALL utility types (electric, gas, water).
Ground truth from actual tenants/residents.
"""

import json
from typing import List, Optional
from pathlib import Path

from pipeline.interfaces import (
    DataSource,
    UtilityType,
    LookupContext,
    SourceResult,
    SOURCE_CONFIDENCE,
)


class UserCorrectionSource(DataSource):
    """
    User-reported corrections from verified_addresses.json.
    
    Highest priority - ground truth from actual tenants/residents.
    Works for electric, gas, and water.
    
    Priority:
    1. Exact address match (normalized to uppercase)
    2. ZIP-level override (for entire ZIP codes)
    """
    
    _corrections_cache = None
    
    @property
    def name(self) -> str:
        return "user_corrections"
    
    @property
    def supported_types(self) -> List[UtilityType]:
        return [UtilityType.ELECTRIC, UtilityType.GAS, UtilityType.WATER]
    
    @property
    def base_confidence(self) -> int:
        return 99  # Highest confidence - user verified
    
    def query(self, context: LookupContext) -> Optional[SourceResult]:
        """
        Check verified addresses database for user corrections.
        
        Priority:
        1. Exact address match
        2. ZIP-level override
        """
        corrections = self._load_corrections()
        utility_type_str = context.utility_type.value  # 'electric', 'gas', 'water'
        
        # Try exact address match (normalized to uppercase)
        address_key = self._normalize_address(context.address)
        addresses = corrections.get('addresses', {})
        
        if address_key in addresses:
            match = addresses[address_key]
            # Check if this utility type has a correction
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
