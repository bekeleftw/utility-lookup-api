#!/usr/bin/env python3
"""
Build canonical name mappings using OpenAI.
Processes utility_providers_IDs.csv to create a lookup table of variations → canonical ID.
Run this once to generate the mappings file, then use it for fast matching.
"""

import csv
import json
import os
import asyncio
from openai import AsyncOpenAI
from collections import defaultdict
import re

# Output file
MAPPINGS_FILE = os.path.join(os.path.dirname(__file__), 'data', 'provider_name_mappings.json')
CSV_FILE = os.path.join(os.path.dirname(__file__), 'utility_providers_IDs.csv')

client = AsyncOpenAI(api_key=os.getenv('OPENAI_API_KEY'))

def normalize_simple(name: str) -> str:
    """Simple normalization for grouping similar names."""
    if not name:
        return ''
    name = name.lower()
    # Remove state suffixes
    name = re.sub(r'\s*-\s*[a-z]{2}$', '', name)
    name = re.sub(r'\s*\([a-z]{2}\)$', '', name)
    # Remove common suffixes
    name = re.sub(r'\s+(inc|llc|corp|co|company|corporation|l\.?l\.?c\.?|lp|ltd)\.?$', '', name, flags=re.IGNORECASE)
    # Remove special chars
    name = re.sub(r'[^a-z0-9\s]', '', name)
    return ' '.join(name.split())


def load_providers():
    """Load all providers from CSV."""
    providers = []
    with open(CSV_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            providers.append({
                'id': row.get('ID', '').strip(),
                'title': row.get('Title', '').strip(),
                'utility_type_id': row.get('UtilityTypeId', ''),
                'normalized': normalize_simple(row.get('Title', ''))
            })
    return providers


def group_similar_names(providers):
    """Group providers by similar normalized names."""
    groups = defaultdict(list)
    
    for p in providers:
        # Create a key from first few chars of normalized name
        norm = p['normalized']
        if len(norm) >= 3:
            # Group by first word
            key = norm.split()[0] if norm.split() else norm[:5]
            groups[key].append(p)
    
    # Filter to groups with potential duplicates (>1 provider with similar names)
    potential_dupes = {}
    for key, items in groups.items():
        if len(items) > 1:
            # Check if names are actually similar (not just same first word)
            titles = [p['title'] for p in items]
            # Only include if there are genuinely similar names
            potential_dupes[key] = items
    
    return potential_dupes


async def dedupe_batch(names_batch: list, batch_id: int) -> dict:
    """Use OpenAI to identify canonical names for a batch of similar provider names."""
    
    prompt = f"""You are a utility company name normalizer. Given these utility provider names, identify which ones refer to the SAME company and provide a canonical (standard) name for each group.

Provider names:
{json.dumps(names_batch, indent=2)}

For each unique company, output a JSON object with:
- "canonical": the standard/official company name
- "variations": list of input names that refer to this company

Only group names that clearly refer to the same company. If unsure, keep them separate.

Output valid JSON array only, no explanation."""

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=2000
        )
        
        content = response.choices[0].message.content.strip()
        # Extract JSON from response
        if content.startswith('```'):
            content = content.split('```')[1]
            if content.startswith('json'):
                content = content[4:]
        
        result = json.loads(content)
        print(f"  Batch {batch_id}: processed {len(names_batch)} names -> {len(result)} groups")
        return result
        
    except Exception as e:
        print(f"  Batch {batch_id} error: {e}")
        return []


async def process_all_groups(groups: dict, concurrency: int = 10):
    """Process all groups with OpenAI at specified concurrency."""
    
    # Flatten groups into batches of names
    all_batches = []
    for key, items in groups.items():
        names = [p['title'] for p in items]
        if len(names) > 1:  # Only process groups with potential dupes
            all_batches.append(names)
    
    print(f"Processing {len(all_batches)} batches with concurrency {concurrency}")
    
    # Process in parallel with semaphore for rate limiting
    semaphore = asyncio.Semaphore(concurrency)
    
    async def process_with_semaphore(batch, batch_id):
        async with semaphore:
            return await dedupe_batch(batch, batch_id)
    
    tasks = [process_with_semaphore(batch, i) for i, batch in enumerate(all_batches)]
    results = await asyncio.gather(*tasks)
    
    return results


def build_mappings(providers, dedupe_results):
    """Build final mappings from provider names to IDs."""
    
    # Create title -> ID lookup
    title_to_id = {p['title']: p['id'] for p in providers}
    title_to_type = {p['title']: p['utility_type_id'] for p in providers}
    
    # Build variation -> canonical ID mappings
    mappings = {}
    
    for result_batch in dedupe_results:
        if not result_batch:
            continue
        for group in result_batch:
            canonical = group.get('canonical', '')
            variations = group.get('variations', [])
            
            # Find the ID for the canonical name (or first variation that has an ID)
            canonical_id = title_to_id.get(canonical)
            if not canonical_id:
                for var in variations:
                    if var in title_to_id:
                        canonical_id = title_to_id[var]
                        break
            
            if canonical_id:
                # Map all variations to this ID
                for var in variations:
                    norm_var = normalize_simple(var)
                    mappings[norm_var] = {
                        'id': canonical_id,
                        'canonical': canonical,
                        'original': var
                    }
    
    return mappings


async def main():
    print("Loading providers...")
    providers = load_providers()
    print(f"Loaded {len(providers)} providers")
    
    print("Grouping similar names...")
    groups = group_similar_names(providers)
    print(f"Found {len(groups)} groups with potential duplicates")
    
    print("Processing with OpenAI...")
    results = await process_all_groups(groups, concurrency=20)
    
    print("Building mappings...")
    mappings = build_mappings(providers, results)
    print(f"Created {len(mappings)} name mappings")
    
    # Save mappings
    os.makedirs(os.path.dirname(MAPPINGS_FILE), exist_ok=True)
    with open(MAPPINGS_FILE, 'w') as f:
        json.dump(mappings, f, indent=2)
    
    print(f"Saved to {MAPPINGS_FILE}")
    
    # Also create a simple normalized name -> ID lookup for all providers
    simple_lookup = {}
    for p in providers:
        norm = normalize_simple(p['title'])
        if norm and norm not in simple_lookup:
            simple_lookup[norm] = p['id']
    
    simple_file = os.path.join(os.path.dirname(__file__), 'data', 'provider_simple_lookup.json')
    with open(simple_file, 'w') as f:
        json.dump(simple_lookup, f, indent=2)
    print(f"Saved simple lookup ({len(simple_lookup)} entries) to {simple_file}")


if __name__ == '__main__':
    asyncio.run(main())
