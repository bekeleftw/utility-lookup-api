#!/usr/bin/env python3
"""
Utility Lookup v2 - Simplified Pipeline-Based Architecture

This replaces the 3,464-line utility_lookup.py with clean, simple logic.
Pipeline is the ONLY orchestrator for ALL utility types.

Key improvements:
- Single execution path (no priority spaghetti)
- Geocode once, use for all utilities
- Pipeline orchestrates everything
- Legacy functions for backward compatibility

USAGE:
    from utility_lookup_v2 import lookup_utilities_by_address
    
    result = lookup_utilities_by_address("123 Main St, Austin, TX 78701")
    # Returns: { electric: {...}, gas: {...}, water: {...} }
"""

import os
import sys
import time
from typing import Optional, Dict, List, Any
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import geocoding - use the full geocoding with fallbacks (Census -> Google -> Nominatim)
from utility_lookup_v1 import geocode_address

# Re-export functions from v1 that api.py needs for backward compatibility
from utility_lookup_v1 import (
    lookup_utility_json,
    lookup_electric_only,
    lookup_gas_only,
    lookup_water_only,
    lookup_internet_only,
    geocode_with_census,
)

# Import pipeline components
try:
    from pipeline.pipeline import LookupPipeline
    from pipeline.interfaces import UtilityType, LookupContext, PipelineResult
    from pipeline.sources.electric import (
        StateGISElectricSource, MunicipalElectricSource, CoopSource,
        EIASource, HIFLDElectricSource, CountyDefaultElectricSource,
        TenantVerifiedElectricSource
    )
    from pipeline.sources.gas import (
        StateGISGasSource, MunicipalGasSource,
        ZIPMappingGasSource, HIFLDGasSource, CountyDefaultGasSource,
        TenantVerifiedGasSource
    )
    PIPELINE_AVAILABLE = True
except ImportError as e:
    print(f"[WARNING] Pipeline not available: {e}")
    PIPELINE_AVAILABLE = False

# Import monitoring (optional)
try:
    from monitoring.metrics import track_lookup, LookupTimer
    MONITORING_AVAILABLE = True
except ImportError:
    MONITORING_AVAILABLE = False
    def track_lookup(*args, **kwargs): pass
    class LookupTimer:
        def __init__(self, *args): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def set_result(self, *args, **kwargs): pass

# Import user corrections source (highest priority)
try:
    from pipeline.sources.corrections import UserCorrectionSource
    USER_CORRECTIONS_AVAILABLE = True
except ImportError:
    USER_CORRECTIONS_AVAILABLE = False


# =============================================================================
# PIPELINE INITIALIZATION
# =============================================================================

_pipeline_electric = None
_pipeline_gas = None
_pipeline_water = None


def _get_electric_pipeline() -> LookupPipeline:
    """Get or create the electric utility pipeline."""
    global _pipeline_electric
    if _pipeline_electric is None:
        _pipeline_electric = LookupPipeline()
        
        # Add sources in priority order (highest confidence first)
        if USER_CORRECTIONS_AVAILABLE:
            _pipeline_electric.add_source(UserCorrectionSource())
        _pipeline_electric.add_source(MunicipalElectricSource())
        _pipeline_electric.add_source(StateGISElectricSource())
        _pipeline_electric.add_source(CoopSource())
        
        # State-specific sources
        try:
            from pipeline.sources.georgia_emc import GeorgiaEMCSource
            _pipeline_electric.add_source(GeorgiaEMCSource())
        except ImportError:
            pass
        
        _pipeline_electric.add_source(TenantVerifiedElectricSource())  # Tenant-verified ZIP data
        _pipeline_electric.add_source(EIASource())
        _pipeline_electric.add_source(HIFLDElectricSource())
        _pipeline_electric.add_source(CountyDefaultElectricSource())
    
    return _pipeline_electric


def _get_gas_pipeline() -> LookupPipeline:
    """Get or create the gas utility pipeline."""
    global _pipeline_gas
    if _pipeline_gas is None:
        _pipeline_gas = LookupPipeline()
        
        # Add sources in priority order
        # NOTE: ZIPMappingGasSource confidence has been lowered to 50
        # so HIFLD and municipal sources win over coarse ZIP mapping
        if USER_CORRECTIONS_AVAILABLE:
            _pipeline_gas.add_source(UserCorrectionSource())
        _pipeline_gas.add_source(MunicipalGasSource())
        _pipeline_gas.add_source(StateGISGasSource())
        _pipeline_gas.add_source(TenantVerifiedGasSource())  # Tenant-verified ZIP data
        _pipeline_gas.add_source(ZIPMappingGasSource())  # Lowered confidence (50)
        _pipeline_gas.add_source(HIFLDGasSource())
        _pipeline_gas.add_source(CountyDefaultGasSource())
    
    return _pipeline_gas


def _get_water_pipeline() -> LookupPipeline:
    """Get or create the water utility pipeline."""
    global _pipeline_water
    if _pipeline_water is None:
        _pipeline_water = LookupPipeline()
        
        # Import water sources
        try:
            from pipeline.sources.water import (
                MunicipalWaterSource,
                StateGISWaterSource,
                SpecialDistrictWaterSource,
                EPAWaterSource,
                CountyDefaultWaterSource,
                TenantVerifiedWaterSource,
            )
            WATER_SOURCES_AVAILABLE = True
        except ImportError:
            WATER_SOURCES_AVAILABLE = False
        
        # Add sources in priority order
        if USER_CORRECTIONS_AVAILABLE:
            _pipeline_water.add_source(UserCorrectionSource())
        
        if WATER_SOURCES_AVAILABLE:
            _pipeline_water.add_source(MunicipalWaterSource())
            _pipeline_water.add_source(StateGISWaterSource())
            _pipeline_water.add_source(SpecialDistrictWaterSource())
            _pipeline_water.add_source(TenantVerifiedWaterSource())  # Tenant-verified ZIP data
            _pipeline_water.add_source(EPAWaterSource())
            _pipeline_water.add_source(CountyDefaultWaterSource())
    
    return _pipeline_water


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def lookup_utilities_by_address(
    address: str,
    selected_utilities: Optional[List[str]] = None,
    use_pipeline: bool = True,
    include_metadata: bool = True,
    verify_with_serp: bool = False,  # Kept for API compatibility
    **kwargs  # Accept any other kwargs for backward compatibility
) -> Optional[Dict]:
    """
    Main entry point for utility lookups.
    
    This is the v2 simplified implementation that uses the pipeline
    as the single orchestrator for all utility types.
    
    Args:
        address: Full street address (e.g., "123 Main St, Austin, TX 78701")
        selected_utilities: List of utility types to look up.
                          Default: ['electric', 'gas', 'water']
        use_pipeline: Must be True in v2 (kept for API compatibility)
        include_metadata: Include _confidence, _source, etc. in results
    
    Returns:
        Dict with electric, gas, water utility info, or None on error
    
    Example:
        >>> lookup_utilities_by_address("123 Main St, Austin, TX 78701")
        {
            "electric": {"NAME": "Austin Energy", "_confidence": "high", ...},
            "gas": {"NAME": "Texas Gas Service", "_confidence": "high", ...},
            "water": {"NAME": "Austin Water", "_confidence": "high", ...}
        }
    """
    start_time = time.time()
    
    # Default to all utilities
    if selected_utilities is None:
        selected_utilities = ['electric', 'gas', 'water']
    
    # Normalize utility names
    selected_utilities = [u.lower() for u in selected_utilities]
    
    # Step 1: Geocode address (once for all utilities)
    geo = geocode_address(address, include_geography=True)
    if not geo:
        return {
            "error": "Could not geocode address",
            "address": address,
            "_version": "v2"
        }
    
    # Extract ZIP code from geocode result or original address
    import re
    zip_code = geo.get('zip') or geo.get('zip_code')
    if not zip_code:
        # Try to extract from matched_address or original address
        for addr_str in [geo.get('matched_address', ''), address]:
            zip_match = re.search(r'\b(\d{5})(?:-\d{4})?\b', addr_str)
            if zip_match:
                zip_code = zip_match.group(1)
                break
    
    # Step 2: Create shared context
    base_context = {
        'lat': geo.get('lat'),
        'lon': geo.get('lon'),
        'address': address,
        'city': geo.get('city'),
        'county': geo.get('county'),
        'state': geo.get('state'),
        'zip_code': zip_code
    }
    
    # Step 3: Query each utility type via pipeline
    results = {}
    
    # Map utility names to pipeline getters and types
    utility_config = {
        'electric': (_get_electric_pipeline, UtilityType.ELECTRIC),
        'gas': (_get_gas_pipeline, UtilityType.GAS),
        'water': (_get_water_pipeline, UtilityType.WATER),
    }
    
    for utility_name in selected_utilities:
        if utility_name not in utility_config:
            continue
        
        pipeline_getter, utility_type = utility_config[utility_name]
        
        # Create context for this utility type
        context = LookupContext(
            lat=base_context['lat'],
            lon=base_context['lon'],
            address=base_context['address'],
            city=base_context['city'],
            county=base_context['county'],
            state=base_context['state'],
            zip_code=base_context['zip_code'],
            utility_type=utility_type
        )
        
        # Track lookup timing
        with LookupTimer(utility_name) as timer:
            try:
                if PIPELINE_AVAILABLE:
                    pipeline = pipeline_getter()
                    result = pipeline.lookup(context)
                    timer.set_result(result.to_dict() if result else None)
                else:
                    # Fallback to legacy lookup if pipeline unavailable
                    result = _legacy_lookup(utility_name, base_context)
                    timer.set_result(result)
            except Exception as e:
                result = None
                timer.error = str(e)
        
        # Format result for API response
        if result and isinstance(result, PipelineResult) and result.utility_name:
            formatted = {
                'NAME': result.brand_name or result.utility_name,
                'TELEPHONE': result.phone,
                'WEBSITE': result.website,
                'STATE': base_context['state'],
                'CITY': base_context['city'],
            }
            
            if include_metadata:
                formatted.update({
                    '_confidence': result.confidence_level,
                    '_confidence_score': result.confidence_score,
                    '_source': result.source,
                    '_legal_name': result.legal_name,
                    '_verification_source': result.source,
                    '_selection_reason': f"Selected by pipeline from {result.source}",
                    '_sources_agreed': result.sources_agreed,
                    '_agreeing_sources': result.agreeing_sources,
                    '_disagreeing_sources': result.disagreeing_sources,
                    '_deregulated_market': result.deregulated_market,
                    '_deregulated_note': result.deregulated_note,
                    '_serp_verified': result.serp_verified,
                    '_timing_ms': result.timing_ms,
                })
            
            results[utility_name] = formatted
        elif result and isinstance(result, dict):
            # Legacy result format
            results[utility_name] = result
        else:
            results[utility_name] = None
    
    # Add version and timing metadata
    if include_metadata:
        results['_version'] = 'v2'
        results['_total_time_ms'] = int((time.time() - start_time) * 1000)
        results['_geocoded'] = {
            'lat': base_context['lat'],
            'lon': base_context['lon'],
            'city': base_context['city'],
            'county': base_context['county'],
            'state': base_context['state'],
            'zip_code': base_context['zip_code'],
        }
    
    return results


# =============================================================================
# LEGACY FALLBACK (for utilities without pipeline sources)
# =============================================================================

def _legacy_lookup(utility_type: str, context: Dict) -> Optional[Dict]:
    """
    Fallback to legacy lookup for utilities without pipeline sources.
    
    This is primarily used for water until Phase 3 adds water pipeline sources.
    """
    if utility_type == 'water':
        try:
            from utility_lookup import lookup_water_utility
            
            result = lookup_water_utility(
                context['city'],
                context['county'],
                context['state'],
                full_address=context['address'],
                lat=context['lat'],
                lon=context['lon'],
                zip_code=context['zip_code']
            )
            
            if result:
                return {
                    'NAME': result.get('name'),
                    'TELEPHONE': result.get('phone'),
                    'WEBSITE': result.get('website'),
                    'STATE': context['state'],
                    'CITY': context['city'],
                    '_confidence': result.get('_confidence', 'medium'),
                    '_source': result.get('_source', 'legacy_water_lookup'),
                    '_verification_source': 'legacy',
                }
        except ImportError:
            pass
    
    return None


# =============================================================================
# BACKWARD COMPATIBILITY FUNCTIONS
# =============================================================================

def lookup_water_only(
    lat: float, 
    lon: float, 
    city: str, 
    county: str,
    state: str, 
    zip_code: str, 
    address: str = None
) -> Optional[Dict]:
    """
    Legacy function - redirects to v2 pipeline.
    
    Maintained for backward compatibility with existing code.
    """
    if not address:
        address = f"{city}, {state} {zip_code}"
    
    result = lookup_utilities_by_address(address, selected_utilities=['water'])
    return result.get('water') if result else None


def lookup_electric_only(
    lat: float, 
    lon: float, 
    city: str, 
    county: str,
    state: str, 
    zip_code: str, 
    address: str = None,
    use_pipeline: bool = True
) -> Optional[Dict]:
    """
    Legacy function - redirects to v2 pipeline.
    
    Maintained for backward compatibility with existing code.
    """
    if not address:
        address = f"{city}, {state} {zip_code}"
    
    result = lookup_utilities_by_address(address, selected_utilities=['electric'])
    return result.get('electric') if result else None


def lookup_gas_only(
    lat: float, 
    lon: float, 
    city: str, 
    county: str,
    state: str, 
    zip_code: str, 
    address: str = None,
    use_pipeline: bool = True
) -> Optional[Dict]:
    """
    Legacy function - redirects to v2 pipeline.
    
    Maintained for backward compatibility with existing code.
    """
    if not address:
        address = f"{city}, {state} {zip_code}"
    
    result = lookup_utilities_by_address(address, selected_utilities=['gas'])
    return result.get('gas') if result else None


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description='Utility Lookup v2')
    parser.add_argument('address', nargs='?', help='Address to look up')
    parser.add_argument('--test', action='store_true', help='Run test addresses')
    parser.add_argument('--compare', action='store_true', help='Compare v1 vs v2')
    args = parser.parse_args()
    
    if args.test:
        # Test addresses
        test_addresses = [
            "1401 Thrasher Dr, Little Elm, TX 75068",  # CoServ Gas (was returning Atmos)
            "1100 Congress Ave, Austin, TX 78701",      # Austin Energy
            "1000 Main St, Houston, TX 77002",          # CenterPoint
            "City Hall, New York, NY 10007",            # Con Edison
            "121 N LaSalle St, Chicago, IL 60602",      # ComEd
        ]
        
        for addr in test_addresses:
            print(f"\n{'='*60}")
            print(f"Address: {addr}")
            print('='*60)
            
            result = lookup_utilities_by_address(addr)
            
            if result:
                for utility_type in ['electric', 'gas', 'water']:
                    util = result.get(utility_type)
                    if util:
                        print(f"\n{utility_type.upper()}:")
                        print(f"  Name: {util.get('NAME')}")
                        print(f"  Confidence: {util.get('_confidence')} ({util.get('_confidence_score')})")
                        print(f"  Source: {util.get('_source')}")
                    else:
                        print(f"\n{utility_type.upper()}: Not found")
                
                print(f"\nTotal time: {result.get('_total_time_ms')}ms")
            else:
                print("Lookup failed")
    
    elif args.compare:
        # Compare v1 vs v2
        from utility_lookup import lookup_utilities_by_address as lookup_v1
        
        test_addr = args.address or "1401 Thrasher Dr, Little Elm, TX 75068"
        
        print(f"Comparing v1 vs v2 for: {test_addr}\n")
        
        print("V1 Result:")
        v1_result = lookup_v1(test_addr)
        print(json.dumps({k: v.get('NAME') if v else None for k, v in v1_result.items() if k in ['electric', 'gas', 'water']}, indent=2))
        
        print("\nV2 Result:")
        v2_result = lookup_utilities_by_address(test_addr)
        print(json.dumps({k: v.get('NAME') if v else None for k, v in v2_result.items() if k in ['electric', 'gas', 'water']}, indent=2))
    
    elif args.address:
        # Single address lookup
        result = lookup_utilities_by_address(args.address)
        print(json.dumps(result, indent=2, default=str))
    
    else:
        parser.print_help()
