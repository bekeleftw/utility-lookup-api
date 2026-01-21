"""
Water utility data sources for the pipeline.

Sources in priority order:
1. UserCorrectionSource (in corrections.py) - 99 confidence
2. MunicipalWaterSource - 88 confidence (city-owned utilities)
3. StateGISWaterSource - 85 confidence (state GIS APIs)
4. SpecialDistrictWaterSource - 80 confidence (MUDs, CDDs)
5. EPAWaterSource - 65 confidence (EPA SDWIS data)
6. CountyDefaultWaterSource - 40 confidence (fallback)
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


class MunicipalWaterSource(DataSource):
    """
    Municipal water utilities from municipal_utilities.json.
    
    City-owned water utilities like Austin Water, LADWP, etc.
    High confidence - authoritative for cities they serve.
    """
    
    _cache = None
    
    @property
    def name(self) -> str:
        return "municipal_water"
    
    @property
    def supported_types(self) -> List[UtilityType]:
        return [UtilityType.WATER]
    
    @property
    def base_confidence(self) -> int:
        return SOURCE_CONFIDENCE.get('municipal_utility', 88)
    
    def query(self, context: LookupContext) -> Optional[SourceResult]:
        data = self._load_data()
        
        if not context.state or not context.city:
            return None
        
        # Check water section
        water_data = data.get('water', {})
        state_data = water_data.get(context.state, {})
        
        # Try exact city match
        city_upper = context.city.upper()
        for city_name, utility_info in state_data.items():
            if city_name.upper() == city_upper:
                return self._build_result(utility_info, context.city)
        
        # Try ZIP code match if available
        for city_name, utility_info in state_data.items():
            zip_codes = utility_info.get('zip_codes', [])
            if context.zip_code and context.zip_code in zip_codes:
                return self._build_result(utility_info, city_name)
        
        # Check electric section for combined utilities (Austin Energy + Austin Water)
        electric_data = data.get('electric', {})
        state_electric = electric_data.get(context.state, {})
        
        for city_name, utility_info in state_electric.items():
            if city_name.upper() == city_upper:
                # Check if this utility also provides water
                if 'water' in utility_info.get('services', []):
                    water_name = utility_info.get('water_provider', f"{city_name} Water")
                    return SourceResult(
                        source_name=self.name,
                        utility_name=water_name,
                        confidence_score=self.base_confidence,
                        match_type='city',
                        phone=utility_info.get('water_phone') or utility_info.get('phone'),
                        website=utility_info.get('water_website') or utility_info.get('website'),
                        raw_data={'city': city_name, 'combined_utility': True}
                    )
        
        return None
    
    def _build_result(self, utility_info: dict, city: str) -> SourceResult:
        # Boost confidence if this municipal utility has priority over special districts
        # (e.g., cities that have absorbed MUDs but MUD boundaries still exist in data)
        confidence = self.base_confidence
        if utility_info.get('priority_over_special_districts'):
            confidence = 95  # Higher than special_district (85) to ensure municipal wins
        
        return SourceResult(
            source_name=self.name,
            utility_name=utility_info.get('name'),
            confidence_score=confidence,
            match_type='city' if not utility_info.get('priority_over_special_districts') else 'city_priority',
            phone=utility_info.get('phone'),
            website=utility_info.get('website'),
            raw_data={'city': city, 'priority_over_special_districts': utility_info.get('priority_over_special_districts', False)}
        )
    
    def _load_data(self) -> dict:
        if MunicipalWaterSource._cache is not None:
            return MunicipalWaterSource._cache
        
        try:
            path = Path(__file__).parent.parent.parent / 'data' / 'municipal_utilities.json'
            if path.exists():
                with open(path, 'r') as f:
                    MunicipalWaterSource._cache = json.load(f)
                    return MunicipalWaterSource._cache
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        
        MunicipalWaterSource._cache = {}
        return MunicipalWaterSource._cache


class StateGISWaterSource(DataSource):
    """
    State GIS APIs for water utility boundaries.
    
    Uses gis_utility_lookup.py for states with water GIS APIs.
    High confidence - authoritative point-in-polygon.
    """
    
    @property
    def name(self) -> str:
        return "state_gis_water"
    
    @property
    def supported_types(self) -> List[UtilityType]:
        return [UtilityType.WATER]
    
    @property
    def base_confidence(self) -> int:
        return SOURCE_CONFIDENCE.get('state_gis', 85)
    
    def query(self, context: LookupContext) -> Optional[SourceResult]:
        if not context.lat or not context.lon:
            return None
        
        try:
            from gis_utility_lookup import lookup_water_utility_gis
            
            result = lookup_water_utility_gis(
                context.lon, context.lat,
                state=context.state,
                city=context.city
            )
            
            if not result:
                return None
            
            # Handle list or single result
            if isinstance(result, list):
                primary = result[0] if result else None
            else:
                primary = result
            
            if not primary:
                return None
            
            # Extract name from various possible fields
            name = (
                primary.get('name') or 
                primary.get('NAME') or 
                primary.get('PWSNAME') or
                primary.get('SystemName')
            )
            
            if not name:
                return None
            
            return SourceResult(
                source_name=self.name,
                utility_name=name,
                confidence_score=self.base_confidence,
                match_type='point',
                phone=primary.get('phone') or primary.get('PHONE'),
                website=primary.get('website') or primary.get('WEBSITE'),
                raw_data=primary
            )
            
        except ImportError:
            return None
        except Exception as e:
            return SourceResult(
                source_name=self.name,
                utility_name=None,
                confidence_score=0,
                match_type='none',
                error=str(e)
            )


class SpecialDistrictWaterSource(DataSource):
    """
    Special districts (MUDs, CDDs, Water Districts).
    
    Uses special_districts module for Texas MUDs, Florida CDDs, etc.
    Good confidence - authoritative for district boundaries.
    """
    
    @property
    def name(self) -> str:
        return "special_district_water"
    
    @property
    def supported_types(self) -> List[UtilityType]:
        return [UtilityType.WATER]
    
    @property
    def base_confidence(self) -> int:
        return SOURCE_CONFIDENCE.get('special_district', 85)
    
    def query(self, context: LookupContext) -> Optional[SourceResult]:
        if not context.lat or not context.lon:
            return None
        
        try:
            from special_districts import lookup_special_district, format_district_for_response
            
            district = lookup_special_district(
                context.lat, context.lon,
                context.state, context.zip_code,
                'water'
            )
            
            if not district:
                return None
            
            formatted = format_district_for_response(district)
            
            return SourceResult(
                source_name=self.name,
                utility_name=formatted.get('name'),
                confidence_score=self.base_confidence,
                match_type='point',
                phone=formatted.get('phone'),
                website=formatted.get('website'),
                raw_data=district
            )
            
        except ImportError:
            return None
        except Exception as e:
            return SourceResult(
                source_name=self.name,
                utility_name=None,
                confidence_score=0,
                match_type='none',
                error=str(e)
            )


class EPAWaterSource(DataSource):
    """
    EPA SDWIS (Safe Drinking Water Information System) data.
    
    National coverage but less precise than state GIS.
    Medium confidence - good for verification.
    """
    
    _cache = None
    
    @property
    def name(self) -> str:
        return "epa_sdwis"
    
    @property
    def supported_types(self) -> List[UtilityType]:
        return [UtilityType.WATER]
    
    @property
    def base_confidence(self) -> int:
        return SOURCE_CONFIDENCE.get('epa_sdwis', 55)
    
    def query(self, context: LookupContext) -> Optional[SourceResult]:
        data = self._load_data()
        
        if not data:
            return None
        
        # Try city + state lookup
        if context.city and context.state:
            city_key = f"{context.city.upper()}|{context.state.upper()}"
            if city_key in data:
                entry = data[city_key]
                return self._build_result(entry, 'city')
        
        # Try county + state lookup
        if context.county and context.state:
            county_key = f"{context.county.upper()}|{context.state.upper()}"
            if county_key in data:
                entry = data[county_key]
                return self._build_result(entry, 'county')
        
        return None
    
    def _build_result(self, entry: dict, match_type: str) -> SourceResult:
        return SourceResult(
            source_name=self.name,
            utility_name=entry.get('name'),
            confidence_score=self.base_confidence,
            match_type=match_type,
            phone=entry.get('phone'),
            website=entry.get('website'),
            raw_data=entry
        )
    
    def _load_data(self) -> dict:
        if EPAWaterSource._cache is not None:
            return EPAWaterSource._cache
        
        try:
            path = Path(__file__).parent.parent.parent / 'water_utility_lookup.json'
            if path.exists():
                with open(path, 'r') as f:
                    raw_data = json.load(f)
                    
                # Handle new structure: {'by_county': {...}, 'by_city': {...}}
                indexed = {}
                
                # Load by_city entries (key format: "STATE|CITY")
                by_city = raw_data.get('by_city', {})
                for key, entry in by_city.items():
                    if isinstance(entry, dict):
                        # Key is already "STATE|CITY", we need "CITY|STATE" for lookup
                        parts = key.split('|')
                        if len(parts) == 2:
                            state, city = parts
                            indexed[f"{city}|{state}"] = entry
                
                # Load by_county entries (key format: "STATE|COUNTY")
                by_county = raw_data.get('by_county', {})
                for key, entry in by_county.items():
                    if isinstance(entry, dict):
                        parts = key.split('|')
                        if len(parts) == 2:
                            state, county = parts
                            # Only add if not already covered by city
                            county_key = f"{county}|{state}"
                            if county_key not in indexed:
                                indexed[county_key] = entry
                
                EPAWaterSource._cache = indexed
                return EPAWaterSource._cache
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        
        EPAWaterSource._cache = {}
        return EPAWaterSource._cache


class CountyDefaultWaterSource(DataSource):
    """
    County-level default water utilities.
    
    Fallback when other sources fail.
    Low confidence - should be verified.
    """
    
    _cache = None
    
    @property
    def name(self) -> str:
        return "county_default_water"
    
    @property
    def supported_types(self) -> List[UtilityType]:
        return [UtilityType.WATER]
    
    @property
    def base_confidence(self) -> int:
        return SOURCE_CONFIDENCE.get('county_default', 50)
    
    def query(self, context: LookupContext) -> Optional[SourceResult]:
        data = self._load_data()
        
        if not context.state or not context.county:
            return None
        
        water_data = data.get('water', {})
        state_data = water_data.get(context.state, {})
        
        county_upper = context.county.upper()
        if county_upper in state_data:
            entry = state_data[county_upper]
            return SourceResult(
                source_name=self.name,
                utility_name=entry.get('name'),
                confidence_score=self.base_confidence,
                match_type='county',
                phone=entry.get('phone'),
                website=entry.get('website'),
                raw_data=entry
            )
        
        return None
    
    def _load_data(self) -> dict:
        if CountyDefaultWaterSource._cache is not None:
            return CountyDefaultWaterSource._cache
        
        try:
            path = Path(__file__).parent.parent.parent / 'data' / 'county_utility_defaults.json'
            if path.exists():
                with open(path, 'r') as f:
                    CountyDefaultWaterSource._cache = json.load(f)
                    return CountyDefaultWaterSource._cache
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        
        CountyDefaultWaterSource._cache = {}
        return CountyDefaultWaterSource._cache
