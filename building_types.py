#!/usr/bin/env python3
"""
Building type detection and utility arrangement handling.
Different building types have different utility arrangements (master-metered, submetered, etc.)
"""

from typing import Dict, Optional, List
from enum import Enum


class BuildingType(Enum):
    SINGLE_FAMILY = "single_family"
    TOWNHOME = "townhome"
    CONDO = "condo"
    APARTMENT_GARDEN = "apartment_garden"
    APARTMENT_HIGHRISE = "apartment_highrise"
    MOBILE_HOME = "mobile_home"
    MOBILE_HOME_PARK = "mobile_home_park"
    COMMERCIAL = "commercial"
    MIXED_USE = "mixed_use"
    UNKNOWN = "unknown"


class MeteringType(Enum):
    DIRECT = "direct"  # Tenant has direct account with utility
    MASTER_METERED = "master_metered"  # Building has one meter, included in rent
    SUBMETERED = "submetered"  # Building has one meter, landlord bills tenants
    RUBS = "rubs"  # Ratio Utility Billing System
    UNKNOWN = "unknown"


# Typical utility arrangements by building type
BUILDING_TYPE_DEFAULTS = {
    BuildingType.SINGLE_FAMILY: {
        "electric": {"metering": MeteringType.DIRECT, "tenant_account": True},
        "gas": {"metering": MeteringType.DIRECT, "tenant_account": True},
        "water": {"metering": MeteringType.DIRECT, "tenant_account": True},
        "notes": "Single-family homes typically have direct utility accounts."
    },
    BuildingType.TOWNHOME: {
        "electric": {"metering": MeteringType.DIRECT, "tenant_account": True},
        "gas": {"metering": MeteringType.DIRECT, "tenant_account": True},
        "water": {"metering": MeteringType.DIRECT, "tenant_account": True, "may_vary": True},
        "notes": "Townhomes usually have direct accounts. Water may be HOA-managed in some communities."
    },
    BuildingType.CONDO: {
        "electric": {"metering": MeteringType.DIRECT, "tenant_account": True},
        "gas": {"metering": MeteringType.DIRECT, "tenant_account": True, "may_vary": True},
        "water": {"metering": MeteringType.MASTER_METERED, "tenant_account": False, "may_vary": True},
        "notes": "Condos typically have direct electric. Water often billed through HOA."
    },
    BuildingType.APARTMENT_GARDEN: {
        "electric": {"metering": MeteringType.DIRECT, "tenant_account": True},
        "gas": {"metering": MeteringType.MASTER_METERED, "tenant_account": False, "may_vary": True},
        "water": {"metering": MeteringType.MASTER_METERED, "tenant_account": False},
        "notes": "Garden apartments usually have direct electric. Gas and water often master-metered."
    },
    BuildingType.APARTMENT_HIGHRISE: {
        "electric": {"metering": MeteringType.DIRECT, "tenant_account": True, "may_vary": True},
        "gas": {"metering": MeteringType.MASTER_METERED, "tenant_account": False},
        "water": {"metering": MeteringType.MASTER_METERED, "tenant_account": False},
        "notes": "High-rise apartments often have master-metered gas and water. Electric varies."
    },
    BuildingType.MOBILE_HOME: {
        "electric": {"metering": MeteringType.DIRECT, "tenant_account": True},
        "gas": {"metering": MeteringType.DIRECT, "tenant_account": True, "may_vary": True},
        "water": {"metering": MeteringType.DIRECT, "tenant_account": True, "may_vary": True},
        "notes": "Mobile homes on private land typically have direct accounts."
    },
    BuildingType.MOBILE_HOME_PARK: {
        "electric": {"metering": MeteringType.SUBMETERED, "tenant_account": False, "may_vary": True},
        "gas": {"metering": MeteringType.SUBMETERED, "tenant_account": False, "may_vary": True},
        "water": {"metering": MeteringType.SUBMETERED, "tenant_account": False},
        "notes": "Mobile home parks often submeter utilities through park management."
    },
    BuildingType.COMMERCIAL: {
        "electric": {"metering": MeteringType.DIRECT, "tenant_account": True},
        "gas": {"metering": MeteringType.DIRECT, "tenant_account": True},
        "water": {"metering": MeteringType.DIRECT, "tenant_account": True},
        "notes": "Commercial properties typically have direct accounts with commercial rates."
    },
    BuildingType.MIXED_USE: {
        "electric": {"metering": MeteringType.DIRECT, "tenant_account": True, "may_vary": True},
        "gas": {"metering": MeteringType.DIRECT, "tenant_account": True, "may_vary": True},
        "water": {"metering": MeteringType.DIRECT, "tenant_account": True, "may_vary": True},
        "notes": "Mixed-use buildings vary widely. Contact property management."
    },
}


# Keywords that suggest building types
BUILDING_TYPE_KEYWORDS = {
    BuildingType.APARTMENT_GARDEN: ["apt", "apartment", "unit", "garden"],
    BuildingType.APARTMENT_HIGHRISE: ["tower", "high-rise", "highrise", "plaza", "suite"],
    BuildingType.CONDO: ["condo", "condominium"],
    BuildingType.TOWNHOME: ["townhome", "townhouse", "th"],
    BuildingType.MOBILE_HOME: ["mobile", "manufactured", "trailer"],
    BuildingType.COMMERCIAL: ["suite", "ste", "floor", "office", "retail", "shop"],
}


def detect_building_type_from_address(address: str) -> BuildingType:
    """
    Attempt to detect building type from address string.
    """
    if not address:
        return BuildingType.UNKNOWN
    
    address_lower = address.lower()
    
    # Check for unit indicators (suggests multi-family)
    has_unit = any(indicator in address_lower for indicator in 
                   ["apt", "unit", "#", "suite", "ste", "floor", "fl"])
    
    # Check for specific keywords
    for building_type, keywords in BUILDING_TYPE_KEYWORDS.items():
        if any(kw in address_lower for kw in keywords):
            return building_type
    
    # If has unit number but no specific type, assume apartment
    if has_unit:
        return BuildingType.APARTMENT_GARDEN
    
    return BuildingType.UNKNOWN


def get_utility_arrangement(
    building_type: BuildingType,
    utility_type: str
) -> Dict:
    """
    Get typical utility arrangement for a building type.
    """
    defaults = BUILDING_TYPE_DEFAULTS.get(building_type, {})
    arrangement = defaults.get(utility_type, {})
    
    return {
        "metering": arrangement.get("metering", MeteringType.UNKNOWN).value,
        "tenant_account_likely": arrangement.get("tenant_account", None),
        "may_vary": arrangement.get("may_vary", False),
        "building_type": building_type.value,
        "notes": defaults.get("notes")
    }


def adjust_result_for_building_type(
    result: Dict,
    address: str = None,
    building_type: BuildingType = None
) -> Dict:
    """
    Adjust utility lookup result based on building type.
    Adds notes about metering arrangements.
    """
    if not building_type and address:
        building_type = detect_building_type_from_address(address)
    
    if not building_type or building_type == BuildingType.UNKNOWN:
        return result
    
    defaults = BUILDING_TYPE_DEFAULTS.get(building_type, {})
    
    result["_building_type"] = building_type.value
    result["_building_notes"] = defaults.get("notes")
    
    # Add metering info for each utility type
    for utility_type in ["electric", "gas", "water"]:
        if utility_type in result:
            arrangement = defaults.get(utility_type, {})
            metering = arrangement.get("metering", MeteringType.UNKNOWN)
            
            if metering == MeteringType.MASTER_METERED:
                result[utility_type]["_metering_note"] = (
                    "This utility is often master-metered in this building type. "
                    "May be included in rent or billed through property management."
                )
                result[utility_type]["_tenant_action"] = "Contact property management"
            elif metering == MeteringType.SUBMETERED:
                result[utility_type]["_metering_note"] = (
                    "This utility may be submetered. Billing often handled by "
                    "property management or third-party billing company."
                )
                result[utility_type]["_tenant_action"] = "Contact property management"
            
            if arrangement.get("may_vary"):
                result[utility_type]["_arrangement_varies"] = True
    
    return result


def is_likely_master_metered(
    building_type: BuildingType,
    utility_type: str
) -> bool:
    """
    Check if a utility is likely master-metered for this building type.
    """
    defaults = BUILDING_TYPE_DEFAULTS.get(building_type, {})
    arrangement = defaults.get(utility_type, {})
    metering = arrangement.get("metering", MeteringType.UNKNOWN)
    
    return metering in [MeteringType.MASTER_METERED, MeteringType.SUBMETERED]


def get_tenant_action(
    building_type: BuildingType,
    utility_type: str
) -> str:
    """
    Get recommended tenant action for setting up utility.
    """
    if is_likely_master_metered(building_type, utility_type):
        return "Contact property management - utility may be included or billed separately"
    else:
        return "Set up direct account with utility provider"


# Known submetering companies
SUBMETERING_COMPANIES = [
    {"name": "Conservice", "website": "conservice.com", "coverage": "nationwide"},
    {"name": "NWP Services", "website": "nwpsc.com", "coverage": "nationwide"},
    {"name": "Livable", "website": "livable.com", "coverage": "nationwide"},
    {"name": "SimpleBills", "website": "simplebills.com", "coverage": "student housing"},
    {"name": "American Utility Management", "website": "ikisum.com", "coverage": "nationwide"},
    {"name": "Guardian Water & Power", "website": "guardianwp.com", "coverage": "southwest"},
    {"name": "Minol", "website": "minol.com", "coverage": "nationwide"},
]


if __name__ == "__main__":
    print("Building Type Detection Tests:")
    print("=" * 60)
    
    test_addresses = [
        "123 Main St, Austin, TX 78701",
        "456 Oak Ave Apt 201, Dallas, TX 75201",
        "789 Tower Blvd Unit 1502, Houston, TX 77001",
        "100 Condo Way #5, San Antonio, TX 78201",
        "200 Mobile Home Park Lot 45, El Paso, TX 79901",
    ]
    
    for addr in test_addresses:
        building_type = detect_building_type_from_address(addr)
        print(f"\n{addr}")
        print(f"  Type: {building_type.value}")
        
        for utility in ["electric", "gas", "water"]:
            arrangement = get_utility_arrangement(building_type, utility)
            print(f"  {utility}: {arrangement['metering']} (tenant account: {arrangement['tenant_account_likely']})")
