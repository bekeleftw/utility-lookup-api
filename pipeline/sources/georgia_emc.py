"""
Georgia EMC (Electric Membership Corporation) data source.

Georgia has 41 EMCs serving 4.7 million members across 65% of the state's land area.
This source provides county-level EMC lookup for Georgia addresses.
"""

import json
from pathlib import Path
from typing import List, Optional

from ..interfaces import (
    DataSource,
    SourceResult,
    LookupContext,
    UtilityType,
    SOURCE_CONFIDENCE,
)


class GeorgiaEMCSource(DataSource):
    """
    Georgia Electric Membership Corporation lookup.
    
    Uses county-to-EMC mapping from georgia_emcs.json.
    High confidence for rural/suburban Georgia addresses.
    """
    
    _cache = None
    
    @property
    def name(self) -> str:
        return "georgia_emc"
    
    @property
    def supported_types(self) -> List[UtilityType]:
        return [UtilityType.ELECTRIC]
    
    @property
    def base_confidence(self) -> int:
        return 82  # High confidence for county-level EMC data
    
    def query(self, context: LookupContext) -> Optional[SourceResult]:
        # Only for Georgia
        if context.state != 'GA':
            return None
        
        if not context.county:
            return None
        
        data = self._load_data()
        if not data:
            return None
        
        # Normalize county name (remove " County" suffix if present)
        county = context.county.replace(' County', '').strip()
        
        # Look up EMCs for this county
        county_to_emc = data.get('county_to_emc', {})
        emcs = county_to_emc.get(county, [])
        
        if not emcs:
            return None
        
        # If only one EMC serves this county, return it
        if len(emcs) == 1:
            emc_name = emcs[0]
            emc_info = data.get('emcs', {}).get(emc_name, {})
            return SourceResult(
                source_name=self.name,
                utility_name=emc_name,
                confidence_score=self.base_confidence + 5,  # Bonus for single match
                match_type='county_single',
                phone=emc_info.get('phone'),
                website=emc_info.get('website'),
                raw_data={
                    'county': county,
                    'emc_count': 1,
                    'all_emcs': emcs
                }
            )
        
        # Multiple EMCs serve this county - return the first one but lower confidence
        # The AI selector will need to decide based on more context
        emc_name = emcs[0]
        emc_info = data.get('emcs', {}).get(emc_name, {})
        return SourceResult(
            source_name=self.name,
            utility_name=emc_name,
            confidence_score=self.base_confidence - 10,  # Lower confidence for multi-EMC county
            match_type='county_multiple',
            phone=emc_info.get('phone'),
            website=emc_info.get('website'),
            raw_data={
                'county': county,
                'emc_count': len(emcs),
                'all_emcs': emcs,
                'note': f'Multiple EMCs serve {county} County: {", ".join(emcs)}'
            }
        )
    
    def _load_data(self) -> dict:
        if GeorgiaEMCSource._cache is not None:
            return GeorgiaEMCSource._cache
        
        try:
            path = Path(__file__).parent.parent.parent / 'data' / 'georgia_emcs.json'
            if path.exists():
                with open(path, 'r') as f:
                    GeorgiaEMCSource._cache = json.load(f)
                    return GeorgiaEMCSource._cache
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Error loading Georgia EMC data: {e}")
        
        GeorgiaEMCSource._cache = {}
        return GeorgiaEMCSource._cache
