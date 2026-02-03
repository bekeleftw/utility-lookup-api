#!/usr/bin/env python3
"""
Verify provider disputes by researching official sources.
For each disputed ZIP, search for official utility territory info.
"""

import json
import os
import re
import time
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

def research_provider_dispute(zip_code: str, utility_type: str, 
                               spreadsheet_provider: str, api_provider: str,
                               sample_addresses: list) -> dict:
    """
    Use OpenAI to research which provider actually serves this ZIP.
    Returns verdict with sources.
    """
    
    prompt = f"""Research which {utility_type} utility provider serves ZIP code {zip_code}.

Two sources disagree:
- Source A (spreadsheet): {spreadsheet_provider}
- Source B (API/GIS): {api_provider}

Sample addresses in this ZIP:
{chr(10).join(sample_addresses[:3])}

Please determine:
1. Are these actually the SAME company with different names? (e.g., "Xcel Energy" = "Public Service Co. of Colorado")
2. If different companies, which one actually serves this ZIP? Or do BOTH serve different parts?
3. If it's a split territory, what determines which provider serves which addresses?

Research approach:
- Check if the company names are aliases/subsidiaries of each other
- Look for official utility service territory information
- Consider municipal utilities that may serve specific areas within a ZIP

Respond with JSON only:
{{
    "same_company": true/false,
    "verdict": "source_a" | "source_b" | "both_serve_area" | "uncertain",
    "correct_provider": "Provider Name",
    "reasoning": "Brief explanation",
    "is_split_territory": true/false,
    "split_details": "If split, explain how territory is divided"
}}"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        result['zip'] = zip_code
        result['utility_type'] = utility_type
        result['spreadsheet_provider'] = spreadsheet_provider
        result['api_provider'] = api_provider
        return result
        
    except Exception as e:
        return {
            'zip': zip_code,
            'utility_type': utility_type,
            'error': str(e),
            'verdict': 'error'
        }

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=20, help='Number of ZIPs to verify')
    parser.add_argument('--output', type=str, default='data/verified_disputes.json', help='Output file')
    args = parser.parse_args()
    
    # Load verification queue
    with open("data/verification_queue.json", "r") as f:
        queue_data = json.load(f)
    
    queue = queue_data['queue'][:args.limit]
    print(f"Verifying {len(queue)} ZIPs...")
    
    results = []
    
    for i, entry in enumerate(queue):
        zip_code = entry['zip']
        print(f"\n[{i+1}/{len(queue)}] ZIP {zip_code}...")
        
        # Verify electric if disputed
        if entry.get('electric', {}).get('needs_verification'):
            ss = entry['electric']['spreadsheet_says'][0]
            api = entry['electric']['api_says'][0]
            print(f"  Electric: {ss[:30]} vs {api[:30]}")
            
            result = research_provider_dispute(
                zip_code, 'electric', ss, api, entry['sample_addresses']
            )
            results.append(result)
            print(f"    Verdict: {result.get('verdict')} - {result.get('reasoning', '')[:50]}")
            time.sleep(0.5)  # Rate limit
        
        # Verify gas if disputed
        if entry.get('gas', {}).get('needs_verification'):
            ss = entry['gas']['spreadsheet_says'][0]
            api = entry['gas']['api_says'][0]
            print(f"  Gas: {ss[:30]} vs {api[:30]}")
            
            result = research_provider_dispute(
                zip_code, 'gas', ss, api, entry['sample_addresses']
            )
            results.append(result)
            print(f"    Verdict: {result.get('verdict')} - {result.get('reasoning', '')[:50]}")
            time.sleep(0.5)
    
    # Save results
    with open(args.output, 'w') as f:
        json.dump({
            '_metadata': {
                'description': 'Verified provider disputes using AI research',
                'total_verified': len(results)
            },
            'verifications': results
        }, f, indent=2)
    
    print(f"\nSaved {len(results)} verifications to {args.output}")
    
    # Summary
    same_company = sum(1 for r in results if r.get('same_company'))
    split_territory = sum(1 for r in results if r.get('is_split_territory'))
    source_a_wins = sum(1 for r in results if r.get('verdict') == 'source_a')
    source_b_wins = sum(1 for r in results if r.get('verdict') == 'source_b')
    
    print(f"\nSummary:")
    print(f"  Same company (name variation): {same_company}")
    print(f"  Split territory: {split_territory}")
    print(f"  Spreadsheet correct: {source_a_wins}")
    print(f"  API correct: {source_b_wins}")

if __name__ == "__main__":
    main()
