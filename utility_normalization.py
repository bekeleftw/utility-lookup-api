"""
Unified utility name normalization for all provider types.
Used to aggregate tenant-verified data and normalize API responses.
"""

import re


def normalize_electric_name(name: str) -> str:
    """Normalize electric utility names."""
    if not name:
        return ""
    
    name = name.upper().strip()
    
    # Skip non-utility entries
    skip = ['LANDLORD', 'OWNER', 'INCLUDED', 'HOA', 'PROPERTY', 'N/A', 'NA', 'NONE']
    if name in skip or any(s in name for s in skip):
        return ""
    
    # Duke Energy variations
    if 'DUKE' in name:
        if 'CAROLINA' in name:
            return 'DUKE ENERGY CAROLINAS'
        if 'PROGRESS' in name or 'FLORIDA' in name:
            return 'DUKE ENERGY FLORIDA'
        if 'INDIANA' in name:
            return 'DUKE ENERGY INDIANA'
        if 'OHIO' in name or 'KENTUCKY' in name:
            return 'DUKE ENERGY OHIO KENTUCKY'
        return 'DUKE ENERGY'
    
    # Dominion Energy
    if 'DOMINION' in name:
        if 'VIRGINIA' in name or 'VA' in name:
            return 'DOMINION ENERGY VIRGINIA'
        if 'SC' in name or 'SOUTH CAROLINA' in name:
            return 'DOMINION ENERGY SOUTH CAROLINA'
        return 'DOMINION ENERGY'
    
    # Georgia Power
    if 'GEORGIA POWER' in name:
        return 'GEORGIA POWER'
    
    # Florida Power & Light (includes Gulf Power, acquired 2021)
    if 'FPL' in name or 'FLORIDA POWER' in name or 'GULF POWER' in name:
        return 'FLORIDA POWER & LIGHT'
    
    # Southern California Edison
    if 'SCE' in name or 'SOUTHERN CALIFORNIA EDISON' in name:
        return 'SOUTHERN CALIFORNIA EDISON'
    
    # PG&E
    if 'PG&E' in name or 'PACIFIC GAS' in name:
        return 'PACIFIC GAS & ELECTRIC'
    
    # SDGE
    if 'SDG&E' in name or 'SAN DIEGO GAS' in name:
        return 'SAN DIEGO GAS & ELECTRIC'
    
    # CenterPoint
    if 'CENTERPOINT' in name or 'CENTER POINT' in name:
        return 'CENTERPOINT ENERGY'
    
    # Oncor
    if 'ONCOR' in name:
        return 'ONCOR'
    
    # AEP
    if 'AEP' in name or 'AMERICAN ELECTRIC POWER' in name:
        return 'AMERICAN ELECTRIC POWER'
    
    # Xcel
    if 'XCEL' in name:
        return 'XCEL ENERGY'
    
    # Entergy
    if 'ENTERGY' in name:
        return 'ENTERGY'
    
    # EMC/Co-op normalization
    if 'EMC' in name or 'ELECTRIC MEMBERSHIP' in name:
        name = re.sub(r'\s*(EMC|ELECTRIC MEMBERSHIP CORP(ORATION)?)\s*$', ' EMC', name)
        return name.strip()
    
    if 'COOPERATIVE' in name or 'CO-OP' in name or 'COOP' in name:
        name = re.sub(r'\s*(ELECTRIC\s*)?(COOPERATIVE|CO-OP|COOP)\s*$', ' ELECTRIC COOPERATIVE', name)
        return name.strip()
    
    return name


def normalize_gas_name(name: str) -> str:
    """Normalize gas utility names."""
    if not name:
        return ""
    
    name = name.upper().strip()
    
    # Skip non-utility entries
    skip_exact = ['NONE', 'N/A', 'NA', 'OWNER', 'SELF SERVICE', 'LANDLORD', 'HOA', 'INCLUDED']
    if name in skip_exact:
        return ""
    
    skip_contains = ['PROPANE', 'NOT APPLICABLE', 'NOT NEEDED', 'NO GAS', 'AMERIGAS', 
                     'BLOSSMAN', 'FERRELL GAS', 'SUBURBAN PROPANE', 'LP GAS', 
                     'TRACTOR SUPPLY', 'REPUBLIC SERVICES', ' OIL']
    if any(s in name for s in skip_contains):
        return ""
    
    # Piedmont Natural Gas
    if 'PIEDMONT' in name and 'GAS' in name:
        return 'PIEDMONT NATURAL GAS'
    
    # Dominion / Enbridge (they merged)
    if 'DOMINION' in name or 'ENBRIDGE' in name or 'ENBR' in name or 'INBRIDGE' in name:
        return 'ENBRIDGE GAS'
    
    # Atmos Energy
    if 'ATMOS' in name:
        return 'ATMOS ENERGY'
    
    # Southern California Gas
    if 'SOCALGAS' in name or 'SOUTHERN CALIFORNIA GAS' in name:
        return 'SOUTHERN CALIFORNIA GAS'
    
    # National Fuel Gas
    if 'NATIONAL FUEL' in name:
        return 'NATIONAL FUEL GAS'
    
    # Spire (formerly Laclede)
    if 'SPIRE' in name or 'LACLEDE' in name:
        return 'SPIRE'
    
    # CenterPoint
    if 'CENTERPOINT' in name:
        return 'CENTERPOINT ENERGY'
    
    # NiSource / Columbia Gas
    if 'COLUMBIA GAS' in name or 'NISOURCE' in name:
        return 'COLUMBIA GAS'
    
    # Washington Gas
    if 'WASHINGTON GAS' in name:
        return 'WASHINGTON GAS'
    
    # Nicor Gas
    if 'NICOR' in name:
        return 'NICOR GAS'
    
    # Peoples Gas
    if 'PEOPLES GAS' in name or 'PEOPLE\'S GAS' in name:
        return 'PEOPLES GAS'
    
    # TECO Peoples Gas (Florida)
    if 'TECO' in name:
        return 'TECO PEOPLES GAS'
    
    # Con Edison
    if 'CON ED' in name or 'CONED' in name or 'CONSOLIDATED EDISON' in name:
        return 'CON EDISON'
    
    # National Grid
    if 'NATIONAL GRID' in name:
        return 'NATIONAL GRID'
    
    # PSE&G
    if 'PSEG' in name or 'PSE&G' in name or 'PUBLIC SERVICE' in name:
        return 'PSE&G'
    
    # Greenville Utilities
    if 'GREENVILLE' in name and ('UTIL' in name or 'GUC' in name):
        return 'GREENVILLE UTILITIES COMMISSION'
    if name == 'GUC':
        return 'GREENVILLE UTILITIES COMMISSION'
    
    return name


def normalize_water_name(name: str) -> str:
    """Normalize water utility names."""
    if not name:
        return ""
    
    name = name.upper().strip()
    
    # Skip non-utility entries
    skip = ['WELL', 'PRIVATE', 'SEPTIC', 'HOA', 'LANDLORD', 'OWNER', 'INCLUDED', 
            'N/A', 'NA', 'NONE', 'PROPERTY MANAGEMENT']
    if name in skip or any(s in name for s in skip):
        return ""
    
    # American Water variations
    if 'AMERICAN WATER' in name:
        states = {'NJ': 'NEW JERSEY', 'PA': 'PENNSYLVANIA', 'CA': 'CALIFORNIA', 
                  'IL': 'ILLINOIS', 'IN': 'INDIANA', 'MO': 'MISSOURI', 'WV': 'WEST VIRGINIA'}
        for abbr, full in states.items():
            if abbr in name or full in name:
                return f'AMERICAN WATER - {abbr}'
        return 'AMERICAN WATER'
    
    # Aqua America variations
    if 'AQUA' in name:
        if 'PA' in name or 'PENNSYLVANIA' in name:
            return 'AQUA PENNSYLVANIA'
        if 'NC' in name or 'NORTH CAROLINA' in name:
            return 'AQUA NORTH CAROLINA'
        if 'OH' in name or 'OHIO' in name:
            return 'AQUA OHIO'
        return 'AQUA AMERICA'
    
    # WSSC (Washington Suburban)
    if 'WSSC' in name or 'WASHINGTON SUBURBAN' in name:
        return 'WSSC WATER'
    
    # Fairfax Water
    if 'FAIRFAX' in name and 'WATER' in name:
        return 'FAIRFAX WATER'
    
    # Charlotte Water
    if 'CHARLOTTE' in name and 'WATER' in name:
        return 'CHARLOTTE WATER'
    
    # Denver Water
    if 'DENVER WATER' in name:
        return 'DENVER WATER'
    
    # Las Vegas Valley Water
    if 'LAS VEGAS' in name and 'WATER' in name:
        return 'LAS VEGAS VALLEY WATER DISTRICT'
    
    # Phoenix Water
    if 'PHOENIX' in name and 'WATER' in name:
        return 'CITY OF PHOENIX WATER'
    
    # Normalize "City of X" and "Town of X"
    if name.startswith('CITY OF '):
        city = name.replace('CITY OF ', '').split(' - ')[0].split(',')[0].strip()
        return f'CITY OF {city}'
    
    if name.startswith('TOWN OF '):
        town = name.replace('TOWN OF ', '').split(' - ')[0].split(',')[0].strip()
        return f'TOWN OF {town}'
    
    # Remove state suffixes like "- NC", "- TX"
    name = re.sub(r'\s*-\s*[A-Z]{2}\s*$', '', name)
    
    return name


def normalize_utility_name(name: str, utility_type: str) -> str:
    """
    Normalize a utility name based on type.
    
    Args:
        name: Raw utility name
        utility_type: One of 'electric', 'gas', 'water'
    
    Returns:
        Normalized name or empty string if should be skipped
    """
    if utility_type == 'electric':
        return normalize_electric_name(name)
    elif utility_type == 'gas':
        return normalize_gas_name(name)
    elif utility_type == 'water':
        return normalize_water_name(name)
    else:
        return name.upper().strip() if name else ""
