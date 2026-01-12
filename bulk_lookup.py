#!/usr/bin/env python3
"""
Bulk utility lookup from CSV file.

Usage:
    python bulk_lookup.py input.csv output.csv
    python bulk_lookup.py input.csv output.csv --utilities electric,gas
    python bulk_lookup.py input.csv output.csv --workers 4

Input CSV format:
    Must have an 'address' column (or 'full_address', 'street_address')
    Optional: 'city', 'state', 'zip' columns for better geocoding

Output CSV:
    Original columns + electric_provider, gas_provider, water_provider, etc.
"""

import argparse
import csv
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional

from utility_lookup import lookup_utilities_by_address


def find_address_column(headers: List[str]) -> Optional[str]:
    """Find the address column in the CSV headers."""
    address_columns = [
        'address', 'full_address', 'street_address', 'property_address',
        'addr', 'location', 'street', 'address_line_1', 'address1'
    ]
    headers_lower = [h.lower().strip() for h in headers]
    
    for col in address_columns:
        if col in headers_lower:
            return headers[headers_lower.index(col)]
    
    return None


def find_optional_columns(headers: List[str]) -> Dict[str, Optional[str]]:
    """Find optional city, state, zip columns."""
    headers_lower = [h.lower().strip() for h in headers]
    
    result = {'city': None, 'state': None, 'zip': None}
    
    city_cols = ['city', 'city_name', 'municipality']
    state_cols = ['state', 'state_code', 'st', 'province']
    zip_cols = ['zip', 'zip_code', 'zipcode', 'postal_code', 'postal']
    
    for col in city_cols:
        if col in headers_lower:
            result['city'] = headers[headers_lower.index(col)]
            break
    
    for col in state_cols:
        if col in headers_lower:
            result['state'] = headers[headers_lower.index(col)]
            break
    
    for col in zip_cols:
        if col in headers_lower:
            result['zip'] = headers[headers_lower.index(col)]
            break
    
    return result


def lookup_single_address(
    row: Dict,
    address_col: str,
    optional_cols: Dict[str, Optional[str]],
    utilities: List[str],
    row_num: int
) -> Dict:
    """Lookup utilities for a single address."""
    address = row.get(address_col, '').strip()
    
    if not address:
        return {
            '_row_num': row_num,
            '_status': 'error',
            '_error': 'Empty address',
            **row
        }
    
    # Build full address if we have separate columns
    city = row.get(optional_cols.get('city', ''), '').strip() if optional_cols.get('city') else None
    state = row.get(optional_cols.get('state', ''), '').strip() if optional_cols.get('state') else None
    zip_code = row.get(optional_cols.get('zip', ''), '').strip() if optional_cols.get('zip') else None
    
    # If address doesn't include city/state, append them
    full_address = address
    if city and city.lower() not in address.lower():
        full_address += f", {city}"
    if state and state.upper() not in address.upper():
        full_address += f", {state}"
    if zip_code and zip_code not in address:
        full_address += f" {zip_code}"
    
    try:
        result = lookup_utilities_by_address(
            address=full_address,
            selected_utilities=utilities
        )
        
        if not result:
            return {
                '_row_num': row_num,
                '_status': 'no_result',
                '_error': 'Lookup returned no result',
                **row
            }
        
        # Extract provider names
        output = {
            '_row_num': row_num,
            '_status': 'success',
            **row
        }
        
        # Electric
        if 'electric' in utilities:
            elec = result.get('electric')
            if elec:
                if isinstance(elec, list):
                    elec = elec[0] if elec else {}
                output['electric_provider'] = elec.get('NAME', '')
                output['electric_confidence'] = elec.get('confidence_score', '')
                output['electric_source'] = elec.get('_source', '')
                output['electric_findenergy_verified'] = elec.get('_findenergy_verified', False)
            else:
                output['electric_provider'] = ''
                output['electric_confidence'] = ''
                output['electric_source'] = ''
                output['electric_findenergy_verified'] = ''
        
        # Gas
        if 'gas' in utilities:
            gas = result.get('gas')
            if gas:
                if isinstance(gas, list):
                    gas = gas[0] if gas else {}
                output['gas_provider'] = gas.get('NAME', '')
                output['gas_confidence'] = gas.get('confidence_score', '')
                output['gas_source'] = gas.get('_source', '')
                output['gas_findenergy_verified'] = gas.get('_findenergy_verified', False)
            else:
                output['gas_provider'] = ''
                output['gas_confidence'] = ''
                output['gas_source'] = ''
                output['gas_findenergy_verified'] = ''
        
        # Water
        if 'water' in utilities:
            water = result.get('water')
            if water:
                if isinstance(water, list):
                    water = water[0] if water else {}
                output['water_provider'] = water.get('NAME', '')
                output['water_confidence'] = water.get('confidence_score', '')
                output['water_source'] = water.get('_source', '')
            else:
                output['water_provider'] = ''
                output['water_confidence'] = ''
                output['water_source'] = ''
        
        # Location info
        location = result.get('location', {})
        output['_geocoded_city'] = location.get('city', '')
        output['_geocoded_state'] = location.get('state', '')
        output['_geocoded_county'] = location.get('county', '')
        
        return output
        
    except Exception as e:
        return {
            '_row_num': row_num,
            '_status': 'error',
            '_error': str(e),
            **row
        }


def process_csv(
    input_file: str,
    output_file: str,
    utilities: List[str] = None,
    max_workers: int = 2,
    delay_between: float = 0.5
) -> Dict:
    """
    Process a CSV file of addresses and output results.
    
    Args:
        input_file: Path to input CSV
        output_file: Path to output CSV
        utilities: List of utility types to lookup (default: all)
        max_workers: Number of parallel workers (default: 2)
        delay_between: Delay between lookups in seconds
        
    Returns:
        Dict with processing stats
    """
    if utilities is None:
        utilities = ['electric', 'gas', 'water']
    
    input_path = Path(input_file)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")
    
    # Read input CSV
    with open(input_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames
        rows = list(reader)
    
    if not rows:
        raise ValueError("Input CSV is empty")
    
    # Limit to 100 addresses to prevent abuse
    MAX_ADDRESSES = 100
    if len(rows) > MAX_ADDRESSES:
        print(f"Warning: Input has {len(rows)} rows, limiting to {MAX_ADDRESSES}")
        rows = rows[:MAX_ADDRESSES]
    
    # Find address column
    address_col = find_address_column(headers)
    if not address_col:
        raise ValueError(
            f"Could not find address column. Headers: {headers}\n"
            "Expected one of: address, full_address, street_address, etc."
        )
    
    optional_cols = find_optional_columns(headers)
    
    print(f"Input file: {input_file}")
    print(f"Rows to process: {len(rows)}")
    print(f"Address column: {address_col}")
    print(f"Optional columns: {optional_cols}")
    print(f"Utilities: {utilities}")
    print(f"Workers: {max_workers}")
    print()
    
    # Process rows
    results = []
    stats = {'success': 0, 'error': 0, 'no_result': 0}
    
    start_time = time.time()
    
    # Use ThreadPoolExecutor for parallel processing
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        
        for i, row in enumerate(rows):
            # Submit job
            future = executor.submit(
                lookup_single_address,
                row,
                address_col,
                optional_cols,
                utilities,
                i + 1
            )
            futures[future] = i + 1
            
            # Small delay to avoid overwhelming the system
            time.sleep(delay_between)
        
        # Collect results
        for future in as_completed(futures):
            row_num = futures[future]
            try:
                result = future.result()
                results.append(result)
                
                status = result.get('_status', 'unknown')
                stats[status] = stats.get(status, 0) + 1
                
                # Progress update
                processed = len(results)
                if processed % 10 == 0 or processed == len(rows):
                    elapsed = time.time() - start_time
                    rate = processed / elapsed if elapsed > 0 else 0
                    print(f"Processed {processed}/{len(rows)} ({rate:.1f}/sec)")
                    
            except Exception as e:
                print(f"Error processing row {row_num}: {e}")
                stats['error'] += 1
    
    # Sort results by row number
    results.sort(key=lambda x: x.get('_row_num', 0))
    
    # Determine output columns
    output_headers = list(headers)  # Original columns
    
    # Add utility columns
    if 'electric' in utilities:
        output_headers.extend([
            'electric_provider', 'electric_confidence', 
            'electric_source', 'electric_findenergy_verified'
        ])
    if 'gas' in utilities:
        output_headers.extend([
            'gas_provider', 'gas_confidence',
            'gas_source', 'gas_findenergy_verified'
        ])
    if 'water' in utilities:
        output_headers.extend([
            'water_provider', 'water_confidence', 'water_source'
        ])
    
    # Add metadata columns
    output_headers.extend([
        '_geocoded_city', '_geocoded_state', '_geocoded_county',
        '_status', '_error'
    ])
    
    # Write output CSV
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=output_headers, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(results)
    
    elapsed = time.time() - start_time
    
    print()
    print(f"=== Complete ===")
    print(f"Output file: {output_file}")
    print(f"Total time: {elapsed:.1f}s")
    print(f"Success: {stats.get('success', 0)}")
    print(f"No result: {stats.get('no_result', 0)}")
    print(f"Errors: {stats.get('error', 0)}")
    
    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Bulk utility lookup from CSV file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python bulk_lookup.py addresses.csv results.csv
    python bulk_lookup.py addresses.csv results.csv --utilities electric,gas
    python bulk_lookup.py addresses.csv results.csv --workers 4
        """
    )
    
    parser.add_argument('input', help='Input CSV file with addresses')
    parser.add_argument('output', help='Output CSV file for results')
    parser.add_argument(
        '--utilities', '-u',
        default='electric,gas,water',
        help='Comma-separated list of utilities to lookup (default: electric,gas,water)'
    )
    parser.add_argument(
        '--workers', '-w',
        type=int,
        default=2,
        help='Number of parallel workers (default: 2, max recommended: 4)'
    )
    parser.add_argument(
        '--delay', '-d',
        type=float,
        default=0.5,
        help='Delay between lookups in seconds (default: 0.5)'
    )
    
    args = parser.parse_args()
    
    utilities = [u.strip().lower() for u in args.utilities.split(',')]
    
    try:
        process_csv(
            args.input,
            args.output,
            utilities=utilities,
            max_workers=args.workers,
            delay_between=args.delay
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
