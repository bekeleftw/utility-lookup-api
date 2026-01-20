#!/usr/bin/env python3
"""
Phase 1: Data Validation Script

Validates all data files against their JSON schemas.
Runs as part of CI to ensure data integrity.

Run: python scripts/validate_data.py
"""

import json
import sys
from pathlib import Path
from typing import List, Tuple

# Try to import jsonschema, provide helpful message if not installed
try:
    import jsonschema
    from jsonschema import validate, ValidationError
except ImportError:
    print("ERROR: jsonschema package not installed")
    print("Install with: pip install jsonschema")
    sys.exit(1)


def load_json_file(filepath: Path) -> Tuple[dict, str]:
    """Load a JSON file, return (data, error_message)."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f), None
    except json.JSONDecodeError as e:
        return None, f"Invalid JSON: {e}"
    except Exception as e:
        return None, f"Error reading file: {e}"


def validate_file_against_schema(data_file: Path, schema_file: Path) -> List[str]:
    """
    Validate a data file against its schema.
    
    Returns list of error messages (empty if valid).
    """
    errors = []
    
    # Load schema
    schema, schema_error = load_json_file(schema_file)
    if schema_error:
        errors.append(f"Schema error ({schema_file.name}): {schema_error}")
        return errors
    
    # Load data
    data, data_error = load_json_file(data_file)
    if data_error:
        errors.append(f"Data error ({data_file.name}): {data_error}")
        return errors
    
    # Validate
    try:
        validate(instance=data, schema=schema)
    except ValidationError as e:
        # Get a readable path to the error
        path = " -> ".join(str(p) for p in e.absolute_path) if e.absolute_path else "root"
        errors.append(f"{data_file.name}: {e.message} (at {path})")
    except Exception as e:
        errors.append(f"{data_file.name}: Validation error - {e}")
    
    return errors


def validate_json_syntax(data_dir: Path) -> List[str]:
    """Check all JSON files for syntax errors."""
    errors = []
    
    for json_file in data_dir.rglob('*.json'):
        _, error = load_json_file(json_file)
        if error:
            rel_path = json_file.relative_to(data_dir)
            errors.append(f"{rel_path}: {error}")
    
    return errors


def validate_required_fields(data_dir: Path) -> List[str]:
    """Check that required data files have expected structure."""
    errors = []
    
    # Check municipal_utilities.json
    municipal_path = data_dir / 'municipal_utilities.json'
    if municipal_path.exists():
        data, _ = load_json_file(municipal_path)
        if data:
            if 'electric' not in data:
                errors.append("municipal_utilities.json: Missing 'electric' key")
            else:
                # Check that at least some states have data
                if len(data.get('electric', {})) < 5:
                    errors.append("municipal_utilities.json: 'electric' has fewer than 5 states")
    else:
        errors.append("municipal_utilities.json: File not found")
    
    # Check county_utility_defaults.json
    county_path = data_dir / 'county_utility_defaults.json'
    if county_path.exists():
        data, _ = load_json_file(county_path)
        if data:
            if 'electric' not in data:
                errors.append("county_utility_defaults.json: Missing 'electric' key")
    else:
        errors.append("county_utility_defaults.json: File not found")
    
    # Check verified_addresses.json
    verified_path = data_dir / 'verified_addresses.json'
    if verified_path.exists():
        data, _ = load_json_file(verified_path)
        if data:
            if 'addresses' not in data and 'zip_overrides' not in data:
                errors.append("verified_addresses.json: Missing both 'addresses' and 'zip_overrides' keys")
    else:
        errors.append("verified_addresses.json: File not found")
    
    return errors


def validate_texas_territories(data_dir: Path) -> List[str]:
    """Validate Texas territories data if it exists."""
    errors = []
    
    texas_path = data_dir / 'texas_territories.json'
    if not texas_path.exists():
        # Not an error - file may not have been migrated yet
        return errors
    
    data, error = load_json_file(texas_path)
    if error:
        errors.append(f"texas_territories.json: {error}")
        return errors
    
    # Check electric section
    electric = data.get('electric', {})
    if 'tdus' not in electric:
        errors.append("texas_territories.json: Missing 'electric.tdus'")
    elif len(electric['tdus']) < 4:
        errors.append("texas_territories.json: Expected at least 4 TDUs")
    
    if 'zip_to_tdu' not in electric:
        errors.append("texas_territories.json: Missing 'electric.zip_to_tdu'")
    
    # Check gas section
    gas = data.get('gas', {})
    if 'ldcs' not in gas:
        errors.append("texas_territories.json: Missing 'gas.ldcs'")
    elif len(gas['ldcs']) < 3:
        errors.append("texas_territories.json: Expected at least 3 gas LDCs")
    
    if 'zip_to_ldc' not in gas:
        errors.append("texas_territories.json: Missing 'gas.zip_to_ldc'")
    
    # Check that CoServ is in gas LDCs (critical fix)
    if 'COSERV' not in gas.get('ldcs', {}):
        errors.append("texas_territories.json: Missing 'COSERV' in gas.ldcs (required for Denton County)")
    
    return errors


def validate_zip_codes(data_dir: Path) -> List[str]:
    """Validate ZIP code formats in data files."""
    errors = []
    
    # Check verified_addresses.json ZIP overrides
    verified_path = data_dir / 'verified_addresses.json'
    if verified_path.exists():
        data, _ = load_json_file(verified_path)
        if data and 'zip_overrides' in data:
            for zip_code in data['zip_overrides'].keys():
                if not zip_code.isdigit() or len(zip_code) != 5:
                    errors.append(f"verified_addresses.json: Invalid ZIP code '{zip_code}' in zip_overrides")
    
    # Check texas_territories.json ZIP overrides
    texas_path = data_dir / 'texas_territories.json'
    if texas_path.exists():
        data, _ = load_json_file(texas_path)
        if data:
            gas_overrides = data.get('gas', {}).get('zip_overrides', {})
            for zip_code in gas_overrides.keys():
                if not zip_code.isdigit() or len(zip_code) != 5:
                    errors.append(f"texas_territories.json: Invalid ZIP code '{zip_code}' in gas.zip_overrides")
    
    return errors


def validate_all():
    """Run all validations."""
    base_dir = Path(__file__).parent.parent
    data_dir = base_dir / 'data'
    schemas_dir = base_dir / 'schemas'
    
    all_errors = []
    all_warnings = []
    
    print("=" * 60)
    print("DATA VALIDATION")
    print("=" * 60)
    print()
    
    # 1. JSON syntax check
    print("1. Checking JSON syntax...")
    syntax_errors = validate_json_syntax(data_dir)
    if syntax_errors:
        all_errors.extend(syntax_errors)
        print(f"   ❌ {len(syntax_errors)} syntax errors")
    else:
        print("   ✅ All JSON files have valid syntax")
    
    # 2. Required fields check
    print("\n2. Checking required fields...")
    field_errors = validate_required_fields(data_dir)
    if field_errors:
        all_errors.extend(field_errors)
        print(f"   ❌ {len(field_errors)} missing fields")
    else:
        print("   ✅ All required fields present")
    
    # 3. Texas territories validation
    print("\n3. Validating Texas territories...")
    texas_errors = validate_texas_territories(data_dir)
    if texas_errors:
        all_errors.extend(texas_errors)
        print(f"   ❌ {len(texas_errors)} Texas territory errors")
    else:
        texas_path = data_dir / 'texas_territories.json'
        if texas_path.exists():
            print("   ✅ Texas territories valid")
        else:
            print("   ⚠️  Texas territories not yet migrated")
    
    # 4. ZIP code format validation
    print("\n4. Validating ZIP code formats...")
    zip_errors = validate_zip_codes(data_dir)
    if zip_errors:
        all_errors.extend(zip_errors)
        print(f"   ❌ {len(zip_errors)} invalid ZIP codes")
    else:
        print("   ✅ All ZIP codes valid")
    
    # 5. Schema validation (if schemas exist)
    print("\n5. Validating against schemas...")
    if schemas_dir.exists():
        schema_mappings = [
            ('municipal_utilities.json', 'municipal_utilities.schema.json'),
            ('verified_addresses.json', 'verified_addresses.schema.json'),
            ('county_utility_defaults.json', 'county_defaults.schema.json'),
            ('texas_territories.json', 'texas_territories.schema.json'),
        ]
        
        for data_name, schema_name in schema_mappings:
            data_path = data_dir / data_name
            schema_path = schemas_dir / schema_name
            
            if data_path.exists() and schema_path.exists():
                schema_errors = validate_file_against_schema(data_path, schema_path)
                if schema_errors:
                    all_warnings.extend(schema_errors)  # Schema errors are warnings for now
                    print(f"   ⚠️  {data_name}: {len(schema_errors)} schema warnings")
                else:
                    print(f"   ✅ {data_name} matches schema")
            elif not data_path.exists():
                print(f"   ⏭️  {data_name} not found (skipped)")
            elif not schema_path.exists():
                print(f"   ⏭️  {schema_name} not found (skipped)")
    else:
        print("   ⏭️  No schemas directory found")
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    if all_errors:
        print(f"\n❌ VALIDATION FAILED: {len(all_errors)} errors")
        print("\nErrors:")
        for error in all_errors:
            print(f"  - {error}")
        
        if all_warnings:
            print(f"\n⚠️  {len(all_warnings)} warnings:")
            for warning in all_warnings[:5]:  # Show first 5
                print(f"  - {warning}")
            if len(all_warnings) > 5:
                print(f"  ... and {len(all_warnings) - 5} more")
        
        return False
    else:
        print("\n✅ ALL VALIDATIONS PASSED")
        
        if all_warnings:
            print(f"\n⚠️  {len(all_warnings)} warnings (non-blocking):")
            for warning in all_warnings[:5]:
                print(f"  - {warning}")
        
        return True


if __name__ == "__main__":
    success = validate_all()
    sys.exit(0 if success else 1)
