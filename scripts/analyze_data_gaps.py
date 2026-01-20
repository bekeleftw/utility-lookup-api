#!/usr/bin/env python3
"""
Analyze State Utility Knowledge Base to identify data gaps and generate acquisition plan.

This script reads the state_utility_knowledge.json and outputs:
1. Summary of data confidence by state/utility type
2. List of missing data sources
3. Prioritized data acquisition plan
"""

import json
from pathlib import Path
from collections import defaultdict

def load_knowledge_base():
    """Load the state utility knowledge base."""
    kb_path = Path(__file__).parent.parent / 'data' / 'state_utility_knowledge.json'
    with open(kb_path, 'r') as f:
        return json.load(f)

def analyze_gaps(knowledge_base):
    """Analyze data gaps across all states."""
    
    gaps_by_priority = defaultdict(list)
    confidence_summary = []
    sources_to_acquire = []
    
    for state, state_data in knowledge_base.items():
        if state.startswith('_'):  # Skip metadata
            continue
            
        for utility_type in ['electric', 'gas', 'water']:
            util_data = state_data.get(utility_type, {})
            data_status = util_data.get('data_status', {})
            landscape = util_data.get('landscape', {})
            
            confidence = data_status.get('confidence', 'unknown')
            missing = data_status.get('missing', [])
            sources = util_data.get('data_sources_to_acquire', [])
            
            # Track confidence
            confidence_summary.append({
                'state': state,
                'utility_type': utility_type,
                'confidence': confidence,
                'missing_count': len(missing),
                'missing': missing
            })
            
            # Track sources to acquire
            for source in sources:
                source['state'] = state
                source['utility_type'] = utility_type
                sources_to_acquire.append(source)
            
            # Categorize gaps by priority
            if confidence in ['very_low', 'low', 'low_for_rural']:
                gaps_by_priority['high'].append({
                    'state': state,
                    'utility_type': utility_type,
                    'confidence': confidence,
                    'missing': missing,
                    'insight': landscape.get('key_insight', '')
                })
            elif confidence == 'medium':
                gaps_by_priority['medium'].append({
                    'state': state,
                    'utility_type': utility_type,
                    'missing': missing
                })
    
    return confidence_summary, gaps_by_priority, sources_to_acquire

def print_report(confidence_summary, gaps_by_priority, sources_to_acquire):
    """Print a formatted report."""
    
    print("=" * 60)
    print("STATE UTILITY DATA GAP ANALYSIS")
    print("=" * 60)
    print()
    
    # Confidence summary
    print("## DATA CONFIDENCE BY STATE/UTILITY")
    print("-" * 40)
    
    # Group by confidence level
    by_confidence = defaultdict(list)
    for item in confidence_summary:
        by_confidence[item['confidence']].append(f"{item['state']} {item['utility_type']}")
    
    for conf in ['very_low', 'low', 'low_for_rural', 'medium', 'high', 'unknown']:
        if conf in by_confidence:
            print(f"\n{conf.upper()}:")
            for item in by_confidence[conf]:
                print(f"  - {item}")
    
    print()
    print("=" * 60)
    print("## HIGH PRIORITY DATA GAPS")
    print("-" * 40)
    
    for gap in gaps_by_priority.get('high', []):
        print(f"\n{gap['state']} {gap['utility_type'].upper()}:")
        print(f"  Confidence: {gap['confidence']}")
        if gap['missing']:
            print(f"  Missing: {', '.join(gap['missing'])}")
        if gap['insight']:
            print(f"  Insight: {gap['insight']}")
    
    print()
    print("=" * 60)
    print("## DATA SOURCES TO ACQUIRE")
    print("-" * 40)
    
    # Group by priority
    high_priority = [s for s in sources_to_acquire if s.get('priority') == 'high']
    medium_priority = [s for s in sources_to_acquire if s.get('priority') == 'medium']
    
    if high_priority:
        print("\nHIGH PRIORITY:")
        for source in high_priority:
            print(f"\n  [{source['state']} {source['utility_type']}] {source['name']}")
            print(f"    URL: {source.get('url', 'N/A')}")
            print(f"    Data: {source.get('data_type', 'N/A')}")
    
    if medium_priority:
        print("\nMEDIUM PRIORITY:")
        for source in medium_priority:
            print(f"\n  [{source['state']} {source['utility_type']}] {source['name']}")
            print(f"    URL: {source.get('url', 'N/A')}")
            print(f"    Data: {source.get('data_type', 'N/A')}")
    
    print()
    print("=" * 60)
    print("## RECOMMENDED ACTIONS")
    print("-" * 40)
    
    print("""
1. GEORGIA EMCs (HIGH PRIORITY)
   - Scrape Georgia EMC Association website for member list
   - Get service territory boundaries from Georgia PSC
   - This will fix the Coweta Fayette EMC issue and similar

2. TEXAS CO-OPS (MEDIUM PRIORITY)  
   - Improve co-op boundary data
   - Current data misses some suburban co-ops

3. WATER DATA (ONGOING)
   - Water is fragmented everywhere
   - Consider county-by-county approach for high-volume areas
   - Municipal water data is okay, special districts need work
""")

def main():
    kb = load_knowledge_base()
    confidence_summary, gaps_by_priority, sources_to_acquire = analyze_gaps(kb)
    print_report(confidence_summary, gaps_by_priority, sources_to_acquire)

if __name__ == '__main__':
    main()
