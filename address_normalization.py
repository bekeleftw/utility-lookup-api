#!/usr/bin/env python3
"""
Address normalization for utility lookups.
Standardizes addresses to USPS format to improve matching accuracy.
"""

import re
from typing import Dict, Optional, Tuple


# USPS standard abbreviations
STREET_TYPE_ABBREV = {
    'ALLEY': 'ALY', 'AVENUE': 'AVE', 'BOULEVARD': 'BLVD', 'BRIDGE': 'BRG',
    'BYPASS': 'BYP', 'CAUSEWAY': 'CSWY', 'CENTER': 'CTR', 'CIRCLE': 'CIR',
    'COURT': 'CT', 'COVE': 'CV', 'CROSSING': 'XING', 'DRIVE': 'DR',
    'EXPRESSWAY': 'EXPY', 'EXTENSION': 'EXT', 'FREEWAY': 'FWY', 'GROVE': 'GRV',
    'HARBOR': 'HBR', 'HEIGHTS': 'HTS', 'HIGHWAY': 'HWY', 'HILL': 'HL',
    'HOLLOW': 'HOLW', 'ISLAND': 'IS', 'JUNCTION': 'JCT', 'LAKE': 'LK',
    'LANDING': 'LNDG', 'LANE': 'LN', 'LOOP': 'LOOP', 'MANOR': 'MNR',
    'MEADOW': 'MDW', 'MEADOWS': 'MDWS', 'MOUNT': 'MT', 'MOUNTAIN': 'MTN',
    'PARKWAY': 'PKWY', 'PASS': 'PASS', 'PATH': 'PATH', 'PIKE': 'PIKE',
    'PLACE': 'PL', 'PLAZA': 'PLZ', 'POINT': 'PT', 'RIDGE': 'RDG',
    'ROAD': 'RD', 'ROUTE': 'RTE', 'RUN': 'RUN', 'SHORE': 'SHR',
    'SPRING': 'SPG', 'SPRINGS': 'SPGS', 'SQUARE': 'SQ', 'STATION': 'STA',
    'STREET': 'ST', 'SUMMIT': 'SMT', 'TERRACE': 'TER', 'TRACE': 'TRCE',
    'TRACK': 'TRAK', 'TRAIL': 'TRL', 'TUNNEL': 'TUNL', 'TURNPIKE': 'TPKE',
    'VALLEY': 'VLY', 'VIEW': 'VW', 'VILLAGE': 'VLG', 'VISTA': 'VIS',
    'WALK': 'WALK', 'WAY': 'WAY', 'WELLS': 'WLS',
}

# Directional abbreviations
DIRECTIONAL_ABBREV = {
    'NORTH': 'N', 'SOUTH': 'S', 'EAST': 'E', 'WEST': 'W',
    'NORTHEAST': 'NE', 'NORTHWEST': 'NW', 'SOUTHEAST': 'SE', 'SOUTHWEST': 'SW',
}

# Unit type abbreviations
UNIT_TYPE_ABBREV = {
    'APARTMENT': 'APT', 'BUILDING': 'BLDG', 'DEPARTMENT': 'DEPT',
    'FLOOR': 'FL', 'SUITE': 'STE', 'UNIT': 'UNIT', 'ROOM': 'RM',
    'SPACE': 'SPC', 'STOP': 'STOP', 'TRAILER': 'TRLR', 'BOX': 'BOX',
}

# State abbreviations
STATE_ABBREV = {
    'ALABAMA': 'AL', 'ALASKA': 'AK', 'ARIZONA': 'AZ', 'ARKANSAS': 'AR',
    'CALIFORNIA': 'CA', 'COLORADO': 'CO', 'CONNECTICUT': 'CT', 'DELAWARE': 'DE',
    'FLORIDA': 'FL', 'GEORGIA': 'GA', 'HAWAII': 'HI', 'IDAHO': 'ID',
    'ILLINOIS': 'IL', 'INDIANA': 'IN', 'IOWA': 'IA', 'KANSAS': 'KS',
    'KENTUCKY': 'KY', 'LOUISIANA': 'LA', 'MAINE': 'ME', 'MARYLAND': 'MD',
    'MASSACHUSETTS': 'MA', 'MICHIGAN': 'MI', 'MINNESOTA': 'MN', 'MISSISSIPPI': 'MS',
    'MISSOURI': 'MO', 'MONTANA': 'MT', 'NEBRASKA': 'NE', 'NEVADA': 'NV',
    'NEW HAMPSHIRE': 'NH', 'NEW JERSEY': 'NJ', 'NEW MEXICO': 'NM', 'NEW YORK': 'NY',
    'NORTH CAROLINA': 'NC', 'NORTH DAKOTA': 'ND', 'OHIO': 'OH', 'OKLAHOMA': 'OK',
    'OREGON': 'OR', 'PENNSYLVANIA': 'PA', 'RHODE ISLAND': 'RI', 'SOUTH CAROLINA': 'SC',
    'SOUTH DAKOTA': 'SD', 'TENNESSEE': 'TN', 'TEXAS': 'TX', 'UTAH': 'UT',
    'VERMONT': 'VT', 'VIRGINIA': 'VA', 'WASHINGTON': 'WA', 'WEST VIRGINIA': 'WV',
    'WISCONSIN': 'WI', 'WYOMING': 'WY', 'DISTRICT OF COLUMBIA': 'DC',
}


def normalize_address(raw_address: str) -> Dict:
    """
    Normalize an address to USPS standard format.
    
    Args:
        raw_address: Raw address string (e.g., "123 Main Street, Austin, Texas 78701")
    
    Returns:
        Dict with normalized components and full normalized address
    """
    if not raw_address:
        return {'normalized': '', 'valid': False}
    
    # Clean up the input
    address = raw_address.upper().strip()
    address = re.sub(r'\s+', ' ', address)  # Normalize whitespace
    address = re.sub(r'[.,]+', ',', address)  # Normalize punctuation
    address = address.replace('#', ' # ')  # Space around unit numbers
    
    # Try to parse components
    result = {
        'original': raw_address,
        'street_number': None,
        'street_name': None,
        'street_type': None,
        'unit_type': None,
        'unit_number': None,
        'city': None,
        'state': None,
        'zip_code': None,
        'zip4': None,
    }
    
    # Extract ZIP code (5 or 9 digit)
    zip_match = re.search(r'\b(\d{5})(?:-(\d{4}))?\b', address)
    if zip_match:
        result['zip_code'] = zip_match.group(1)
        result['zip4'] = zip_match.group(2)
        address = address[:zip_match.start()] + address[zip_match.end():]
    
    # Extract state
    for state_name, state_abbrev in STATE_ABBREV.items():
        if f' {state_name}' in address or f',{state_name}' in address:
            result['state'] = state_abbrev
            address = address.replace(state_name, '')
            break
        elif f' {state_abbrev} ' in address or f',{state_abbrev}' in address or address.endswith(f' {state_abbrev}'):
            result['state'] = state_abbrev
            break
    
    # Split by comma to separate street from city/state
    parts = [p.strip() for p in address.split(',') if p.strip()]
    
    if len(parts) >= 2:
        street_part = parts[0]
        city_part = parts[1] if len(parts) > 1 else ''
        
        # Extract city (remove state if present)
        city = city_part
        for state_abbrev in STATE_ABBREV.values():
            city = re.sub(rf'\b{state_abbrev}\b', '', city).strip()
        result['city'] = city.strip() if city.strip() else None
    else:
        street_part = parts[0] if parts else ''
    
    # Parse street address
    street_part = street_part.strip()
    
    # Extract unit number (Apt, Suite, Unit, #)
    unit_patterns = [
        r'\b(APT|APARTMENT|STE|SUITE|UNIT|RM|ROOM|FL|FLOOR|BLDG|BUILDING|#)\s*[#]?\s*(\w+)\b',
    ]
    for pattern in unit_patterns:
        unit_match = re.search(pattern, street_part, re.IGNORECASE)
        if unit_match:
            unit_type = unit_match.group(1).upper()
            result['unit_type'] = UNIT_TYPE_ABBREV.get(unit_type, unit_type)
            result['unit_number'] = unit_match.group(2)
            street_part = street_part[:unit_match.start()] + street_part[unit_match.end():]
            break
    
    # Extract street number
    number_match = re.match(r'^(\d+[-\d]*)\s+', street_part)
    if number_match:
        result['street_number'] = number_match.group(1)
        street_part = street_part[number_match.end():]
    
    # Normalize directionals
    for direction, abbrev in DIRECTIONAL_ABBREV.items():
        street_part = re.sub(rf'\b{direction}\b', abbrev, street_part)
    
    # Normalize street types
    for street_type, abbrev in STREET_TYPE_ABBREV.items():
        street_part = re.sub(rf'\b{street_type}\b', abbrev, street_part)
    
    # Clean up street name
    street_part = re.sub(r'\s+', ' ', street_part).strip()
    
    # Split street name and type
    words = street_part.split()
    if words:
        # Check if last word is a street type
        if words[-1] in STREET_TYPE_ABBREV.values():
            result['street_type'] = words[-1]
            result['street_name'] = ' '.join(words[:-1])
        else:
            result['street_name'] = street_part
    
    # Build normalized address
    normalized_parts = []
    
    if result['street_number']:
        normalized_parts.append(result['street_number'])
    if result['street_name']:
        normalized_parts.append(result['street_name'])
    if result['street_type']:
        normalized_parts.append(result['street_type'])
    
    street_line = ' '.join(normalized_parts)
    
    if result['unit_type'] and result['unit_number']:
        street_line += f" {result['unit_type']} {result['unit_number']}"
    
    full_parts = [street_line]
    if result['city']:
        full_parts.append(result['city'])
    if result['state']:
        full_parts.append(result['state'])
    if result['zip_code']:
        zip_str = result['zip_code']
        if result['zip4']:
            zip_str += f"-{result['zip4']}"
        full_parts.append(zip_str)
    
    result['normalized'] = ', '.join(full_parts)
    result['valid'] = bool(result['street_number'] and result['street_name'])
    
    return result


def extract_address_components(address: str) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Extract city, state, and ZIP from an address string.
    Returns (street, city, state, zip_code)
    """
    normalized = normalize_address(address)
    
    street = None
    if normalized.get('street_number') and normalized.get('street_name'):
        street = f"{normalized['street_number']} {normalized['street_name']}"
        if normalized.get('street_type'):
            street += f" {normalized['street_type']}"
    
    return (
        street,
        normalized.get('city'),
        normalized.get('state'),
        normalized.get('zip_code')
    )


def addresses_match(addr1: str, addr2: str) -> bool:
    """
    Check if two addresses refer to the same location.
    Uses normalized comparison.
    """
    norm1 = normalize_address(addr1)
    norm2 = normalize_address(addr2)
    
    # Must have same ZIP
    if norm1.get('zip_code') != norm2.get('zip_code'):
        return False
    
    # Must have same street number
    if norm1.get('street_number') != norm2.get('street_number'):
        return False
    
    # Street names must match (after normalization)
    name1 = (norm1.get('street_name') or '').upper()
    name2 = (norm2.get('street_name') or '').upper()
    
    if name1 == name2:
        return True
    
    # Check if one contains the other (handles partial matches)
    if name1 in name2 or name2 in name1:
        return True
    
    return False


def strip_unit_from_address(address: str) -> str:
    """
    Remove unit/apartment number from address for utility lookup.
    Utilities serve the building, not individual units.
    """
    normalized = normalize_address(address)
    
    parts = []
    if normalized.get('street_number'):
        parts.append(normalized['street_number'])
    if normalized.get('street_name'):
        parts.append(normalized['street_name'])
    if normalized.get('street_type'):
        parts.append(normalized['street_type'])
    
    street = ' '.join(parts)
    
    full_parts = [street]
    if normalized.get('city'):
        full_parts.append(normalized['city'])
    if normalized.get('state'):
        full_parts.append(normalized['state'])
    if normalized.get('zip_code'):
        full_parts.append(normalized['zip_code'])
    
    return ', '.join(full_parts)


if __name__ == '__main__':
    # Test cases
    test_addresses = [
        "123 Main Street, Austin, Texas 78701",
        "456 N. Oak Avenue Apt 4, Los Angeles, CA 90012",
        "789 Southwest Parkway #100, Houston, TX 77001-1234",
        "1100 Congress Ave, Austin, TX 78701",
        "200 S Spring St, Los Angeles, California",
    ]
    
    print("Address Normalization Tests:")
    print("=" * 60)
    
    for addr in test_addresses:
        result = normalize_address(addr)
        print(f"\nOriginal: {addr}")
        print(f"Normalized: {result['normalized']}")
        print(f"Components: {result['street_number']} | {result['street_name']} | {result['street_type']}")
        print(f"City: {result['city']} | State: {result['state']} | ZIP: {result['zip_code']}")
