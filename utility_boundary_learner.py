#!/usr/bin/env python3
"""
Utility Boundary Learner

Analyzes tenant verification data to discover geographic patterns and build
increasingly granular rules about utility service boundaries.

The system learns patterns like:
- "In ZIP 28078, addresses on streets starting with 'Glen' tend to be Energy United"
- "In Lawrenceville GA, addresses east of Main St are Jackson EMC, west are Georgia Power"
- "Street numbers above 5000 on Oak St in ZIP 30045 are served by the co-op"

These learned rules are stored in a database and improve over time as more
tenant data is added.
"""

import csv
import re
import json
import os
from collections import defaultdict
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime

@dataclass
class BoundaryRule:
    """A learned rule about utility service boundaries."""
    rule_id: str
    zip_code: str
    city: str
    state: str
    utility_name: str
    rule_type: str  # 'street_name', 'street_prefix', 'street_number_range', 'neighborhood'
    pattern: str  # The pattern that triggers this rule
    confidence: float  # 0.0 to 1.0
    sample_count: int  # How many data points support this rule
    conflicting_utility: str  # What our default data shows
    notes: str  # Human-readable explanation
    created_at: str
    updated_at: str

class UtilityBoundaryLearner:
    """
    Learns utility service boundary patterns from tenant verification data.
    """
    
    def __init__(self, rules_file: str = 'data/learned_boundary_rules.json'):
        self.rules_file = rules_file
        self.rules: Dict[str, BoundaryRule] = {}
        self._load_rules()
    
    def _load_rules(self):
        """Load existing rules from disk."""
        if os.path.exists(self.rules_file):
            try:
                with open(self.rules_file, 'r') as f:
                    data = json.load(f)
                    for rule_data in data.get('rules', []):
                        rule = BoundaryRule(**rule_data)
                        self.rules[rule.rule_id] = rule
                print(f"Loaded {len(self.rules)} existing boundary rules")
            except Exception as e:
                print(f"Warning: Failed to load rules: {e}")
    
    def _save_rules(self):
        """Save rules to disk."""
        os.makedirs(os.path.dirname(self.rules_file), exist_ok=True)
        data = {
            'version': '1.0',
            'updated_at': datetime.now().isoformat(),
            'rule_count': len(self.rules),
            'rules': [asdict(r) for r in self.rules.values()]
        }
        with open(self.rules_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    @staticmethod
    def parse_address(address: str) -> Dict:
        """Parse address into components."""
        result = {
            'street_number': None,
            'street_name': None,
            'unit': None,
            'city': None,
            'state': None,
            'zip_code': None
        }
        
        # Extract ZIP
        zip_match = re.search(r'(\d{5})(?:-\d{4})?$', address.strip())
        if zip_match:
            result['zip_code'] = zip_match.group(1)
        
        # Extract state
        state_match = re.search(r',\s*([A-Z]{2})\s+\d{5}', address)
        if state_match:
            result['state'] = state_match.group(1)
        
        # Extract city
        city_match = re.search(r',\s*([^,]+),\s*[A-Z]{2}\s+\d{5}', address)
        if city_match:
            result['city'] = city_match.group(1).strip()
        
        # Extract street number and name
        street_match = re.match(r'(\d+(?:-\d+)?)\s+(.+?),', address)
        if street_match:
            result['street_number'] = street_match.group(1)
            street_name = street_match.group(2)
            # Remove unit info
            street_name = re.sub(r'\s+(apt|unit|ste|suite|#|bldg)\s*\S*$', '', street_name, flags=re.I)
            result['street_name'] = street_name.lower().strip()
        
        return result
    
    @staticmethod
    def get_street_prefix(street_name: str, length: int = 4) -> str:
        """Get the first N characters of street name for pattern matching."""
        if not street_name:
            return ""
        # Remove directional prefixes
        street = re.sub(r'^(n|s|e|w|ne|nw|se|sw)\s+', '', street_name.lower())
        return street[:length] if len(street) >= length else street
    
    @staticmethod
    def get_street_number_range(street_number: str) -> Tuple[int, int]:
        """Convert street number to a range bucket (e.g., 1000-1999)."""
        try:
            num = int(re.match(r'(\d+)', street_number).group(1))
            # Round down to nearest 1000
            lower = (num // 1000) * 1000
            upper = lower + 999
            return (lower, upper)
        except:
            return (0, 0)
    
    def analyze_zip_patterns(self, tenant_data: List[Dict], our_data_lookup) -> List[Dict]:
        """
        Analyze a ZIP code to find patterns where tenant data differs from our data.
        
        Args:
            tenant_data: List of tenant verification records for this ZIP
            our_data_lookup: Function to look up what our API returns for an address
        
        Returns:
            List of discovered patterns
        """
        patterns = []
        
        # Group by street name
        by_street = defaultdict(list)
        for record in tenant_data:
            parsed = self.parse_address(record['address'])
            if parsed['street_name']:
                by_street[parsed['street_name']].append({
                    'address': record['address'],
                    'tenant_utility': record['utility'],
                    'our_utility': record.get('our_utility', ''),
                    'parsed': parsed
                })
        
        # Look for streets where tenant consistently differs from our data
        for street, records in by_street.items():
            if len(records) < 2:
                continue
            
            # Count utilities on this street
            tenant_utils = defaultdict(int)
            our_utils = defaultdict(int)
            for r in records:
                tenant_utils[r['tenant_utility']] += 1
                if r['our_utility']:
                    our_utils[r['our_utility']] += 1
            
            # Find dominant tenant utility
            if not tenant_utils:
                continue
            top_tenant = max(tenant_utils.items(), key=lambda x: x[1])
            top_our = max(our_utils.items(), key=lambda x: x[1]) if our_utils else (None, 0)
            
            # If tenant consistently says something different
            tenant_pct = top_tenant[1] / len(records)
            if tenant_pct >= 0.7 and top_tenant[0] != top_our[0]:
                patterns.append({
                    'type': 'street_name',
                    'pattern': street,
                    'tenant_utility': top_tenant[0],
                    'our_utility': top_our[0],
                    'confidence': tenant_pct,
                    'sample_count': len(records),
                    'zip_code': records[0]['parsed']['zip_code'],
                    'city': records[0]['parsed']['city'],
                    'state': records[0]['parsed']['state']
                })
        
        # Look for street prefix patterns (e.g., all "Oak*" streets)
        by_prefix = defaultdict(list)
        for street, records in by_street.items():
            prefix = self.get_street_prefix(street)
            if prefix:
                by_prefix[prefix].extend(records)
        
        for prefix, records in by_prefix.items():
            if len(records) < 3:  # Need more data for prefix patterns
                continue
            
            tenant_utils = defaultdict(int)
            for r in records:
                tenant_utils[r['tenant_utility']] += 1
            
            top_tenant = max(tenant_utils.items(), key=lambda x: x[1])
            tenant_pct = top_tenant[1] / len(records)
            
            if tenant_pct >= 0.8:  # Higher threshold for prefix patterns
                patterns.append({
                    'type': 'street_prefix',
                    'pattern': f"{prefix}*",
                    'tenant_utility': top_tenant[0],
                    'confidence': tenant_pct,
                    'sample_count': len(records),
                    'zip_code': records[0]['parsed']['zip_code'],
                    'city': records[0]['parsed']['city'],
                    'state': records[0]['parsed']['state']
                })
        
        # Look for street number range patterns
        by_street_and_range = defaultdict(list)
        for street, records in by_street.items():
            for r in records:
                if r['parsed']['street_number']:
                    range_key = self.get_street_number_range(r['parsed']['street_number'])
                    by_street_and_range[(street, range_key)].append(r)
        
        for (street, num_range), records in by_street_and_range.items():
            if len(records) < 2 or num_range == (0, 0):
                continue
            
            tenant_utils = defaultdict(int)
            for r in records:
                tenant_utils[r['tenant_utility']] += 1
            
            top_tenant = max(tenant_utils.items(), key=lambda x: x[1])
            tenant_pct = top_tenant[1] / len(records)
            
            if tenant_pct >= 0.75:
                patterns.append({
                    'type': 'street_number_range',
                    'pattern': f"{street} #{num_range[0]}-{num_range[1]}",
                    'tenant_utility': top_tenant[0],
                    'confidence': tenant_pct,
                    'sample_count': len(records),
                    'zip_code': records[0]['parsed']['zip_code'],
                    'city': records[0]['parsed']['city'],
                    'state': records[0]['parsed']['state']
                })
        
        return patterns
    
    def learn_from_tenant_data(self, csv_file: str, compare_with_api: bool = False):
        """
        Main learning function - analyzes tenant data and discovers patterns.
        
        Args:
            csv_file: Path to tenant verification CSV
            compare_with_api: If True, also look up each address in our API (slow)
        """
        print(f"Loading tenant data from {csv_file}...")
        
        with open(csv_file, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        print(f"Loaded {len(rows):,} records")
        
        # Group by ZIP
        by_zip = defaultdict(list)
        for row in rows:
            address = row.get('display', '')
            electric = row.get('Electricity', '').strip()
            
            if not address or not electric:
                continue
            
            parsed = self.parse_address(address)
            if parsed['zip_code']:
                by_zip[parsed['zip_code']].append({
                    'address': address,
                    'utility': electric,
                    'parsed': parsed
                })
        
        print(f"Data spans {len(by_zip):,} ZIP codes")
        
        # Find ZIPs with multiple utilities (potential boundary issues)
        multi_util_zips = {}
        for zip_code, records in by_zip.items():
            utils = defaultdict(int)
            for r in records:
                utils[r['utility']] += 1
            
            # Keep utilities with at least 2 occurrences
            significant = {u: c for u, c in utils.items() if c >= 2}
            if len(significant) >= 2:
                multi_util_zips[zip_code] = {
                    'records': records,
                    'utilities': significant
                }
        
        print(f"Found {len(multi_util_zips):,} ZIPs with multiple utilities")
        
        # Analyze each multi-utility ZIP for patterns
        all_patterns = []
        for zip_code, data in multi_util_zips.items():
            patterns = self.analyze_zip_patterns(data['records'], None)
            all_patterns.extend(patterns)
        
        print(f"\nDiscovered {len(all_patterns)} patterns")
        
        # Convert patterns to rules
        new_rules = 0
        updated_rules = 0
        
        for pattern in all_patterns:
            rule_id = f"{pattern['zip_code']}:{pattern['type']}:{pattern['pattern']}"
            
            if rule_id in self.rules:
                # Update existing rule
                existing = self.rules[rule_id]
                existing.sample_count = pattern['sample_count']
                existing.confidence = pattern['confidence']
                existing.updated_at = datetime.now().isoformat()
                updated_rules += 1
            else:
                # Create new rule
                rule = BoundaryRule(
                    rule_id=rule_id,
                    zip_code=pattern['zip_code'],
                    city=pattern.get('city', ''),
                    state=pattern.get('state', ''),
                    utility_name=pattern['tenant_utility'],
                    rule_type=pattern['type'],
                    pattern=pattern['pattern'],
                    confidence=pattern['confidence'],
                    sample_count=pattern['sample_count'],
                    conflicting_utility=pattern.get('our_utility', ''),
                    notes=f"Learned from tenant data: {pattern['sample_count']} samples, {pattern['confidence']*100:.0f}% confidence",
                    created_at=datetime.now().isoformat(),
                    updated_at=datetime.now().isoformat()
                )
                self.rules[rule_id] = rule
                new_rules += 1
        
        print(f"Created {new_rules} new rules, updated {updated_rules} existing rules")
        print(f"Total rules: {len(self.rules)}")
        
        # Save rules
        self._save_rules()
        print(f"Saved rules to {self.rules_file}")
        
        # Print summary by state
        print("\n" + "="*60)
        print("RULES BY STATE")
        print("="*60)
        
        by_state = defaultdict(list)
        for rule in self.rules.values():
            by_state[rule.state].append(rule)
        
        for state in sorted([s for s in by_state.keys() if s]):
            rules = by_state[state]
            print(f"\n{state}: {len(rules)} rules")
            # Show top 5 by sample count
            top_rules = sorted(rules, key=lambda r: -r.sample_count)[:5]
            for r in top_rules:
                print(f"  [{r.rule_type}] {r.pattern} → {r.utility_name} ({r.sample_count} samples, {r.confidence*100:.0f}%)")
        
        return self.rules
    
    def get_rules_for_address(self, address: str) -> List[BoundaryRule]:
        """
        Get any learned rules that apply to this address.
        
        Args:
            address: Full address string
        
        Returns:
            List of matching rules, sorted by confidence
        """
        parsed = self.parse_address(address)
        matching = []
        
        for rule in self.rules.values():
            # Check ZIP match
            if rule.zip_code != parsed['zip_code']:
                continue
            
            # Check pattern match based on rule type
            if rule.rule_type == 'street_name':
                if parsed['street_name'] and rule.pattern in parsed['street_name']:
                    matching.append(rule)
            
            elif rule.rule_type == 'street_prefix':
                prefix = self.get_street_prefix(parsed['street_name'])
                if prefix and rule.pattern.rstrip('*') == prefix:
                    matching.append(rule)
            
            elif rule.rule_type == 'street_number_range':
                # Parse the pattern "street #1000-1999"
                match = re.match(r'(.+)\s+#(\d+)-(\d+)', rule.pattern)
                if match:
                    street, low, high = match.groups()
                    if parsed['street_name'] and street in parsed['street_name']:
                        if parsed['street_number']:
                            try:
                                num = int(re.match(r'(\d+)', parsed['street_number']).group(1))
                                if int(low) <= num <= int(high):
                                    matching.append(rule)
                            except:
                                pass
        
        # Sort by confidence
        return sorted(matching, key=lambda r: -r.confidence)
    
    def get_context_for_ai(self, address: str) -> str:
        """
        Get a context string for the AI selector based on learned rules.
        
        Args:
            address: Full address string
        
        Returns:
            Context string to include in AI prompt
        """
        rules = self.get_rules_for_address(address)
        
        if not rules:
            return ""
        
        lines = ["LEARNED BOUNDARY PATTERNS (from historical tenant data):"]
        for rule in rules[:3]:  # Top 3 rules
            lines.append(f"- {rule.notes}")
            lines.append(f"  Pattern: {rule.pattern} → {rule.utility_name}")
            lines.append(f"  Confidence: {rule.confidence*100:.0f}% ({rule.sample_count} samples)")
        
        lines.append("Note: These patterns are learned from tenant uploads and may not be 100% accurate.")
        
        return "\n".join(lines)


def main():
    """Run the learning process."""
    learner = UtilityBoundaryLearner()
    learner.learn_from_tenant_data('addresses_with_tenant_verification.csv')


if __name__ == '__main__':
    main()
