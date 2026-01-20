"""
Gas utility data source implementations.
"""

import sys
import os
from typing import List, Optional

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from pipeline.interfaces import (
    DataSource,
    UtilityType,
    LookupContext,
    SourceResult,
    SOURCE_CONFIDENCE,
)


class StateGISGasSource(DataSource):
    """Query state-specific GIS APIs for gas utilities."""
    
    # States with gas GIS APIs
    SUPPORTED_STATES = {'TX', 'CA', 'IL', 'PA', 'NY', 'OH', 'GA', 'AZ', 'CO', 'NJ', 'MA', 'MI', 'FL'}
    
    @property
    def name(self) -> str:
        return "state_gis_gas"
    
    @property
    def supported_types(self) -> List[UtilityType]:
        return [UtilityType.GAS]
    
    @property
    def base_confidence(self) -> int:
        return SOURCE_CONFIDENCE.get('state_gis', 85)
    
    def query(self, context: LookupContext) -> Optional[SourceResult]:
        if context.state not in self.SUPPORTED_STATES:
            return None
        
        if not context.lat or not context.lon:
            return None
        
        try:
            from utility_lookup_v1 import lookup_gas_utility_gis
            
            result = lookup_gas_utility_gis(context.lat, context.lon, context.state)
            
            if not result or not result.get('name'):
                return None
            
            return SourceResult(
                source_name=self.name,
                utility_name=result.get('name'),
                confidence_score=self.base_confidence,
                match_type='point',
                phone=result.get('phone'),
                website=result.get('website'),
                raw_data=result
            )
        except Exception as e:
            return SourceResult(
                source_name=self.name,
                utility_name=None,
                confidence_score=0,
                match_type='none',
                error=str(e)
            )


class MunicipalGasSource(DataSource):
    """Look up municipal gas utilities by city."""
    
    @property
    def name(self) -> str:
        return "municipal_gas"
    
    @property
    def supported_types(self) -> List[UtilityType]:
        return [UtilityType.GAS]
    
    @property
    def base_confidence(self) -> int:
        return SOURCE_CONFIDENCE.get('municipal_utility', 88)
    
    def query(self, context: LookupContext) -> Optional[SourceResult]:
        try:
            from utility_lookup_v1 import lookup_municipal_gas
            
            result = lookup_municipal_gas(context.state, context.city, context.zip_code)
            
            if not result or not result.get('name'):
                return None
            
            return SourceResult(
                source_name=self.name,
                utility_name=result.get('name'),
                confidence_score=self.base_confidence,
                match_type='city',
                phone=result.get('phone'),
                website=result.get('website'),
                raw_data=result
            )
        except Exception as e:
            return SourceResult(
                source_name=self.name,
                utility_name=None,
                confidence_score=0,
                match_type='none',
                error=str(e)
            )


class ZIPMappingGasSource(DataSource):
    """Look up gas utilities using ZIP prefix mappings."""
    
    @property
    def name(self) -> str:
        return "zip_mapping_gas"
    
    @property
    def supported_types(self) -> List[UtilityType]:
        return [UtilityType.GAS]
    
    @property
    def base_confidence(self) -> int:
        return SOURCE_CONFIDENCE.get('state_ldc_mapping', 65)
    
    def query(self, context: LookupContext) -> Optional[SourceResult]:
        try:
            from state_utility_verification import get_state_gas_ldc
            
            result = get_state_gas_ldc(context.state, context.zip_code, context.city)
            
            if not result or not result.get('primary'):
                return None
            
            primary = result['primary']
            
            # ZIP prefix mapping is too coarse - lower confidence so HIFLD/municipal wins
            # The 3-digit ZIP prefix can't distinguish between providers in same metro area
            # e.g., 750xx covers both Atmos (Dallas) AND CoServ (Denton County)
            confidence = self.base_confidence
            if result.get('confidence') == 'verified':
                confidence = 50  # Was 80 - lowered to let geographic sources win
            elif result.get('confidence') == 'high':
                confidence = 45  # Was 75 - lowered to let geographic sources win
            
            return SourceResult(
                source_name=self.name,
                utility_name=primary.get('name'),
                confidence_score=confidence,
                match_type='zip',
                phone=primary.get('phone'),
                website=primary.get('website'),
                raw_data=result
            )
        except Exception as e:
            return SourceResult(
                source_name=self.name,
                utility_name=None,
                confidence_score=0,
                match_type='none',
                error=str(e)
            )


class HIFLDGasSource(DataSource):
    """
    Query HIFLD gas utility polygons.
    
    FIXED: Now returns all candidates when multiple utilities overlap,
    allowing the Smart Selector to choose the best one.
    """
    
    @property
    def name(self) -> str:
        return "hifld_gas"
    
    @property
    def supported_types(self) -> List[UtilityType]:
        return [UtilityType.GAS]
    
    @property
    def base_confidence(self) -> int:
        return SOURCE_CONFIDENCE.get('hifld_polygon', 58)
    
    def query(self, context: LookupContext) -> Optional[SourceResult]:
        if not context.lat or not context.lon:
            return None
        
        try:
            from utility_lookup_v1 import lookup_gas_utility
            
            result = lookup_gas_utility(context.lon, context.lat, state=context.state)
            
            if not result:
                return None
            
            # HIFLD can return a list or single result
            # FIXED: Store all candidates in raw_data for Smart Selector
            if isinstance(result, list):
                candidates = result
                primary = result[0] if result else None
            else:
                candidates = [result]
                primary = result
            
            if not primary or not primary.get('NAME'):
                return None
            
            # Store all candidates for Smart Selector to evaluate
            return SourceResult(
                source_name=self.name,
                utility_name=primary.get('NAME'),
                confidence_score=self.base_confidence,
                match_type='point',
                phone=primary.get('TELEPHONE'),
                website=primary.get('WEBSITE'),
                raw_data={
                    'primary': primary,
                    'all_candidates': candidates,
                    'candidate_count': len(candidates),
                    'candidate_names': [c.get('NAME') for c in candidates if c.get('NAME')]
                }
            )
        except Exception as e:
            return SourceResult(
                source_name=self.name,
                utility_name=None,
                confidence_score=0,
                match_type='none',
                error=str(e)
            )


class CountyDefaultGasSource(DataSource):
    """Look up default gas utility by county."""
    
    @property
    def name(self) -> str:
        return "county_default_gas"
    
    @property
    def supported_types(self) -> List[UtilityType]:
        return [UtilityType.GAS]
    
    @property
    def base_confidence(self) -> int:
        return SOURCE_CONFIDENCE.get('county_default', 50)
    
    def query(self, context: LookupContext) -> Optional[SourceResult]:
        try:
            from rural_utilities import lookup_county_default_gas
            
            result = lookup_county_default_gas(context.county, context.state)
            
            if not result or not result.get('name'):
                return None
            
            return SourceResult(
                source_name=self.name,
                utility_name=result.get('name'),
                confidence_score=self.base_confidence,
                match_type='county',
                phone=result.get('phone'),
                website=result.get('website'),
                raw_data=result
            )
        except Exception as e:
            return SourceResult(
                source_name=self.name,
                utility_name=None,
                confidence_score=0,
                match_type='none',
                error=str(e)
            )
