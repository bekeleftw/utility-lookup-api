"""
Electric utility data source implementations.
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


class StateGISElectricSource(DataSource):
    """Query state-specific GIS APIs for electric utilities."""
    
    # States with electric GIS APIs
    SUPPORTED_STATES = {
        'NJ', 'AR', 'DE', 'HI', 'RI', 'CA', 'TX', 'FL', 'GA', 'NC', 'SC',
        'VA', 'WV', 'KY', 'TN', 'AL', 'MS', 'LA', 'OK', 'KS', 'NE', 'SD',
        'ND', 'MT', 'WY', 'CO', 'NM', 'AZ', 'UT', 'NV', 'ID', 'WA', 'OR', 'DC'
    }
    
    @property
    def name(self) -> str:
        return "state_gis"
    
    @property
    def supported_types(self) -> List[UtilityType]:
        return [UtilityType.ELECTRIC]
    
    @property
    def base_confidence(self) -> int:
        return SOURCE_CONFIDENCE.get('state_gis', 85)
    
    def query(self, context: LookupContext) -> Optional[SourceResult]:
        if context.state not in self.SUPPORTED_STATES:
            return None
        
        if not context.lat or not context.lon:
            return None
        
        try:
            from utility_lookup_v1 import lookup_electric_utility_gis
            
            result = lookup_electric_utility_gis(context.lat, context.lon, context.state)
            
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


class MunicipalElectricSource(DataSource):
    """Look up municipal electric utilities by city."""
    
    @property
    def name(self) -> str:
        return "municipal"
    
    @property
    def supported_types(self) -> List[UtilityType]:
        return [UtilityType.ELECTRIC]
    
    @property
    def base_confidence(self) -> int:
        return SOURCE_CONFIDENCE.get('municipal_utility', 88)
    
    def query(self, context: LookupContext) -> Optional[SourceResult]:
        try:
            from utility_lookup_v1 import lookup_municipal_electric
            
            result = lookup_municipal_electric(context.state, context.city, context.zip_code)
            
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


class CoopSource(DataSource):
    """Look up electric cooperatives by ZIP or county."""
    
    @property
    def name(self) -> str:
        return "electric_coop"
    
    @property
    def supported_types(self) -> List[UtilityType]:
        return [UtilityType.ELECTRIC]
    
    @property
    def base_confidence(self) -> int:
        return SOURCE_CONFIDENCE.get('electric_cooperative', 68)
    
    def query(self, context: LookupContext) -> Optional[SourceResult]:
        try:
            from rural_utilities import lookup_coop_by_zip, lookup_coop_by_county
            
            # Try ZIP first
            result = lookup_coop_by_zip(context.zip_code, context.state)
            match_type = 'zip'
            
            # Fall back to county
            if not result:
                result = lookup_coop_by_county(context.county, context.state)
                match_type = 'county'
            
            if not result or not result.get('name'):
                return None
            
            return SourceResult(
                source_name=self.name,
                utility_name=result.get('name'),
                confidence_score=self.base_confidence,
                match_type=match_type,
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


class EIASource(DataSource):
    """Look up utilities using EIA Form 861 ZIP data."""
    
    @property
    def name(self) -> str:
        return "eia_861"
    
    @property
    def supported_types(self) -> List[UtilityType]:
        return [UtilityType.ELECTRIC]
    
    @property
    def base_confidence(self) -> int:
        return SOURCE_CONFIDENCE.get('eia_861', 70)
    
    def query(self, context: LookupContext) -> Optional[SourceResult]:
        try:
            from state_utility_verification import get_eia_utility_by_zip
            
            result = get_eia_utility_by_zip(context.zip_code)
            
            if not result:
                return None
            
            # EIA returns a list, take the first
            primary = result[0] if isinstance(result, list) else result
            
            return SourceResult(
                source_name=self.name,
                utility_name=primary.get('name'),
                confidence_score=self.base_confidence,
                match_type='zip',
                raw_data=primary
            )
        except Exception as e:
            return SourceResult(
                source_name=self.name,
                utility_name=None,
                confidence_score=0,
                match_type='none',
                error=str(e)
            )


class HIFLDElectricSource(DataSource):
    """
    Query HIFLD electric utility polygons.
    
    FIXED: Now returns all candidates when multiple utilities overlap,
    allowing the Smart Selector to choose the best one.
    """
    
    @property
    def name(self) -> str:
        return "hifld"
    
    @property
    def supported_types(self) -> List[UtilityType]:
        return [UtilityType.ELECTRIC]
    
    @property
    def base_confidence(self) -> int:
        return SOURCE_CONFIDENCE.get('hifld_polygon', 58)
    
    def query(self, context: LookupContext) -> Optional[SourceResult]:
        if not context.lat or not context.lon:
            return None
        
        try:
            from utility_lookup_v1 import lookup_electric_utility
            
            result = lookup_electric_utility(context.lon, context.lat)
            
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


class CountyDefaultElectricSource(DataSource):
    """Look up default electric utility by county."""
    
    @property
    def name(self) -> str:
        return "county_default"
    
    @property
    def supported_types(self) -> List[UtilityType]:
        return [UtilityType.ELECTRIC]
    
    @property
    def base_confidence(self) -> int:
        return SOURCE_CONFIDENCE.get('county_default', 50)
    
    def query(self, context: LookupContext) -> Optional[SourceResult]:
        try:
            from rural_utilities import lookup_county_default_electric
            
            result = lookup_county_default_electric(context.county, context.state)
            
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
