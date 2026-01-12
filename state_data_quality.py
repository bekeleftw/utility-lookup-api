#!/usr/bin/env python3
"""
State data availability and quality assessment.
Adjusts confidence scores based on what data sources are available for each state.

The idea: If EIA + HIFLD is the BEST available data for a state, and a human
couldn't do better without calling the utility directly, then our confidence
should reflect that we're using the best available source.
"""

from typing import Dict, Optional

# Data availability tiers by state
# Tier 1: We have authoritative sources (municipal DB, special districts, verified GIS)
# Tier 2: We have good state-level data (state PUC maps, gas mappings)
# Tier 3: We rely on federal data (EIA, HIFLD, EPA) - but it's the best available
STATE_DATA_AVAILABILITY = {
    # === TIER 1: Excellent data availability ===
    # These states have special district data, municipal utilities, or verified GIS
    "TX": {
        "tier": 1,
        "electric_sources": ["municipal_utility", "special_district", "eia_861", "hifld"],
        "gas_sources": ["railroad_commission", "state_ldc_mapping", "zip_override"],
        "water_sources": ["special_district", "municipal_utility", "epa_sdwis"],
        "notes": "Excellent coverage: TCEQ MUDs, municipal utilities, RRC gas data",
        "confidence_boost": 0
    },
    "CA": {
        "tier": 1,
        "electric_sources": ["municipal_utility", "state_puc_map", "eia_861"],
        "gas_sources": ["utility_direct_api", "state_puc_map"],  # CEC gas service areas
        "water_sources": ["special_district", "municipal_utility", "epa_sdwis"],
        "notes": "Good coverage: CPUC maps, CEC data, LAFCO districts",
        "confidence_boost": 0
    },
    "FL": {
        "tier": 1,
        "electric_sources": ["municipal_utility", "eia_861", "hifld"],
        "gas_sources": ["state_ldc_mapping", "hifld"],
        "water_sources": ["special_district", "epa_sdwis"],  # CDDs
        "notes": "Good coverage: FL DEO CDDs, municipal utilities",
        "confidence_boost": 0
    },
    "CO": {
        "tier": 1,
        "electric_sources": ["municipal_utility", "eia_861", "hifld"],
        "gas_sources": ["state_ldc_mapping", "hifld"],
        "water_sources": ["special_district", "municipal_utility", "epa_sdwis"],
        "notes": "Good coverage: DOLA metro districts",
        "confidence_boost": 0
    },
    "AZ": {
        "tier": 1,
        "electric_sources": ["municipal_utility", "eia_861", "hifld"],
        "gas_sources": ["state_ldc_mapping", "hifld"],
        "water_sources": ["special_district", "municipal_utility", "epa_sdwis"],
        "notes": "Good coverage: improvement districts, municipal utilities",
        "confidence_boost": 0
    },
    "WA": {
        "tier": 1,
        "electric_sources": ["special_district", "municipal_utility", "eia_861"],  # PUDs
        "gas_sources": ["state_ldc_mapping", "hifld"],
        "water_sources": ["special_district", "municipal_utility", "epa_sdwis"],
        "notes": "Good coverage: PUDs, municipal utilities",
        "confidence_boost": 0
    },
    
    # === TIER 2: Good state-level data ===
    # These states have state PUC data or good LDC mappings
    "NY": {
        "tier": 2,
        "electric_sources": ["state_puc", "eia_861", "hifld"],
        "gas_sources": ["state_ldc_mapping", "hifld"],
        "water_sources": ["epa_sdwis"],
        "notes": "NY PSC has territory data but not fully integrated",
        "confidence_boost": 5
    },
    "PA": {
        "tier": 2,
        "electric_sources": ["state_puc", "eia_861", "hifld"],
        "gas_sources": ["state_ldc_mapping", "hifld"],
        "water_sources": ["epa_sdwis"],
        "notes": "PA PUC has territory data",
        "confidence_boost": 5
    },
    "OH": {
        "tier": 2,
        "electric_sources": ["state_puc", "eia_861", "hifld"],
        "gas_sources": ["state_ldc_mapping", "hifld"],
        "water_sources": ["epa_sdwis"],
        "notes": "PUCO has territory data",
        "confidence_boost": 5
    },
    "IL": {
        "tier": 2,
        "electric_sources": ["state_puc", "eia_861", "hifld"],
        "gas_sources": ["state_ldc_mapping", "hifld"],
        "water_sources": ["epa_sdwis"],
        "notes": "ICC has territory data",
        "confidence_boost": 5
    },
    "GA": {
        "tier": 2,
        "electric_sources": ["electric_cooperative", "eia_861", "hifld"],
        "gas_sources": ["state_ldc_mapping", "hifld"],
        "water_sources": ["epa_sdwis"],
        "notes": "Good EMC cooperative data",
        "confidence_boost": 5
    },
    "NC": {
        "tier": 2,
        "electric_sources": ["electric_cooperative", "eia_861", "hifld"],
        "gas_sources": ["state_ldc_mapping", "hifld"],
        "water_sources": ["epa_sdwis"],
        "notes": "Good cooperative data",
        "confidence_boost": 5
    },
    
    # === TIER 3: Federal data is best available ===
    # EIA + HIFLD is the best we can do - boost confidence accordingly
}

# Default for states not explicitly listed (Tier 3)
DEFAULT_STATE_DATA = {
    "tier": 3,
    "electric_sources": ["eia_861", "hifld"],
    "gas_sources": ["hifld"],
    "water_sources": ["epa_sdwis"],
    "notes": "Federal data sources only - but this is the best available",
    "confidence_boost": 10  # Boost because we're using best available
}


def get_state_data_availability(state: str) -> Dict:
    """Get data availability info for a state."""
    return STATE_DATA_AVAILABILITY.get(state.upper(), DEFAULT_STATE_DATA)


def get_best_available_source(state: str, utility_type: str) -> str:
    """Get the best available source for a utility type in a state."""
    availability = get_state_data_availability(state)
    
    source_key = f"{utility_type}_sources"
    sources = availability.get(source_key, [])
    
    if sources:
        return sources[0]  # First is best
    return "unknown"


def calculate_data_availability_boost(
    state: str,
    utility_type: str,
    source_used: str
) -> Dict:
    """
    Calculate confidence boost based on data availability.
    
    If we're using the best available source for this state,
    we should boost confidence because a human couldn't do better.
    """
    availability = get_state_data_availability(state)
    tier = availability.get("tier", 3)
    
    source_key = f"{utility_type}_sources"
    best_sources = availability.get(source_key, [])
    
    # Check if we're using one of the best available sources for this state
    source_lower = source_used.lower().replace(" ", "_")
    using_best_available = any(
        best.lower() in source_lower or source_lower in best.lower()
        for best in best_sources[:2]  # Top 2 sources
    )
    
    result = {
        "state": state,
        "tier": tier,
        "utility_type": utility_type,
        "source_used": source_used,
        "best_sources": best_sources,
        "using_best_available": using_best_available,
        "boost": 0,
        "reason": None
    }
    
    if tier == 3 and using_best_available:
        # Tier 3 state using federal data - this IS the best available
        result["boost"] = 10
        result["reason"] = "Using best available data for this state (federal sources)"
    elif tier == 2 and using_best_available:
        # Tier 2 state using state-level data
        result["boost"] = 5
        result["reason"] = "Using best available data for this state"
    elif tier == 3:
        # Tier 3 but not using best source
        result["boost"] = 5
        result["reason"] = "Limited data availability for this state"
    
    return result


def is_best_available_for_state(state: str, utility_type: str, source: str) -> bool:
    """Check if a source is the best available for this state/utility combo."""
    availability = get_state_data_availability(state)
    source_key = f"{utility_type}_sources"
    best_sources = availability.get(source_key, [])
    
    if not best_sources:
        return True  # No data = anything is "best"
    
    source_lower = source.lower().replace(" ", "_")
    return any(
        best.lower() in source_lower or source_lower in best.lower()
        for best in best_sources[:2]
    )


def get_state_tier(state: str) -> int:
    """Get the data availability tier for a state."""
    availability = get_state_data_availability(state)
    return availability.get("tier", 3)


if __name__ == "__main__":
    print("State Data Availability Tests:")
    print("=" * 60)
    
    test_cases = [
        ("TX", "electric", "municipal_utility"),
        ("TX", "gas", "railroad_commission"),
        ("WI", "electric", "eia_861"),
        ("WI", "gas", "hifld"),
        ("WI", "water", "epa_sdwis"),
        ("CA", "gas", "utility_direct_api"),
    ]
    
    for state, utility_type, source in test_cases:
        result = calculate_data_availability_boost(state, utility_type, source)
        print(f"\n{state} - {utility_type} ({source}):")
        print(f"  Tier: {result['tier']}")
        print(f"  Using best available: {result['using_best_available']}")
        print(f"  Boost: +{result['boost']}")
        if result['reason']:
            print(f"  Reason: {result['reason']}")
