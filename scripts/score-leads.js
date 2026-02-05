#!/usr/bin/env node
/**
 * Score LeadGen_Contacts using OpenAI
 * 
 * Scores contacts 1-5 based on:
 * - Job title (decision maker vs support vs realtor)
 * - Name presence (first + last vs first only vs none)
 * - Email pattern (name-based vs generic like info@)
 * 
 * Score 1 = Best (Owner, CEO, Property Manager with full name)
 * Score 5 = Skip (Realtor, no name, generic email)
 * 
 * Environment variables:
 *   AIRTABLE_API_KEY
 *   AIRTABLE_BASE_ID
 *   OPENAI_API_KEY
 */

const https = require('https');

const AIRTABLE_API_KEY = process.env.AIRTABLE_API_KEY;
const AIRTABLE_BASE_ID = process.env.AIRTABLE_BASE_ID || 'app3PpZscmxtjR64U';
const OPENAI_API_KEY = process.env.OPENAI_API_KEY;

const LEADGEN_CONTACTS_TABLE_ID = 'LeadGen_Contacts';
const BATCH_SIZE = 20; // Score 20 contacts per OpenAI call
const AIRTABLE_DELAY_MS = 100;

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function makeRequest(options, postData = null) {
  return new Promise((resolve, reject) => {
    const req = https.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          resolve({ status: res.statusCode, body: JSON.parse(data) });
        } catch (e) {
          resolve({ status: res.statusCode, body: data });
        }
      });
    });
    req.on('error', reject);
    if (postData) req.write(postData);
    req.end();
  });
}

// Fetch contacts that need scoring (no lead_score or lead_score is empty)
async function fetchUnscoredContacts() {
  const contacts = [];
  let offset = null;
  
  do {
    const params = new URLSearchParams({
      pageSize: '100',
      filterByFormula: "OR({lead_score}='', {lead_score}=BLANK())"
    });
    if (offset) params.append('offset', offset);
    
    const options = {
      hostname: 'api.airtable.com',
      path: `/v0/${AIRTABLE_BASE_ID}/${LEADGEN_CONTACTS_TABLE_ID}?${params.toString()}`,
      method: 'GET',
      headers: { 'Authorization': `Bearer ${AIRTABLE_API_KEY}` }
    };
    
    const response = await makeRequest(options);
    
    if (response.status === 200) {
      const records = response.body.records || [];
      contacts.push(...records);
      offset = response.body.offset;
      console.log(`  Fetched ${records.length} unscored contacts (total: ${contacts.length})`);
    } else {
      console.error('Error fetching contacts:', response.body);
      break;
    }
    
    await sleep(AIRTABLE_DELAY_MS);
  } while (offset);
  
  return contacts;
}

// Score a batch of contacts using OpenAI
async function scoreContactsBatch(contacts) {
  const contactData = contacts.map(c => ({
    id: c.id,
    first_name: c.fields.first_name || '',
    last_name: c.fields.last_name || '',
    email: c.fields.email || '',
    job_title: c.fields.job_title || ''
  }));
  
  const prompt = `Score these property management contacts for cold email outreach on a scale of 1-5.

SCORING CRITERIA:

1 (Best): Decision makers with name
   Titles: Owner, CEO, President, Partner, Principal, Founder, Broker, Designated Broker, Managing Broker
   Requirements: Has first name OR last name

2 (Great): Senior operators with name
   Titles: Property Manager, Operations Manager, Director, VP, COO, Regional Manager, Portfolio Manager, Asset Manager, General Manager
   Requirements: Has first name OR last name

3 (Good): Mid-level staff OR unknown title with good signals
   Titles: Office Manager, Assistant PM, Leasing Manager, Coordinator (non-maintenance)
   Also: No title BUT has name + personal email (name-based, not generic)

4 (Maybe): Support roles OR good title with missing name
   Titles: Office Assistant, Admin, Receptionist, Accountant, Bookkeeper
   Also: Decision maker title BUT no name (can't personalize)
   Also: No title + generic email but has name

5 (Skip): Low value - do not push
   Titles: Realtor, Agent, Sales, Marketing, Maintenance, Transaction Coordinator
   Also: No name + generic email (info@, contact@, hello@, office@)
   Also: Leasing Agent (not Manager)

MIXED TITLES: If title contains multiple roles (e.g., "Owner/Realtor"), use the higher-authority role.

CONTACTS TO SCORE:
${JSON.stringify(contactData, null, 2)}

Return ONLY a JSON array: [{"id": "...", "score": 1-5}]`;

  const options = {
    hostname: 'api.openai.com',
    path: '/v1/chat/completions',
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${OPENAI_API_KEY}`,
      'Content-Type': 'application/json'
    }
  };
  
  const payload = JSON.stringify({
    model: 'gpt-4o-mini',
    messages: [{ role: 'user', content: prompt }],
    temperature: 0.1,
    max_tokens: 2000
  });
  
  const response = await makeRequest(options, payload);
  
  if (response.status === 200 && response.body.choices) {
    const content = response.body.choices[0].message.content.trim();
    // Extract JSON from response (handle markdown code blocks)
    const jsonMatch = content.match(/\[[\s\S]*\]/);
    if (jsonMatch) {
      try {
        return JSON.parse(jsonMatch[0]);
      } catch (e) {
        console.error('Failed to parse OpenAI response:', content);
        return [];
      }
    }
  }
  
  console.error('OpenAI API error:', response.body);
  return [];
}

// Update contact scores in Airtable
async function updateContactScores(scores) {
  // Batch update in groups of 10
  for (let i = 0; i < scores.length; i += 10) {
    const batch = scores.slice(i, i + 10);
    const records = batch.map(s => ({
      id: s.id,
      fields: { lead_score: s.score }
    }));
    
    const options = {
      hostname: 'api.airtable.com',
      path: `/v0/${AIRTABLE_BASE_ID}/${LEADGEN_CONTACTS_TABLE_ID}`,
      method: 'PATCH',
      headers: {
        'Authorization': `Bearer ${AIRTABLE_API_KEY}`,
        'Content-Type': 'application/json'
      }
    };
    
    const payload = JSON.stringify({ records });
    const response = await makeRequest(options, payload);
    
    if (response.status !== 200) {
      console.error('Error updating scores:', response.body);
    }
    
    await sleep(AIRTABLE_DELAY_MS);
  }
}

async function main() {
  console.log('Starting lead scoring...\n');
  
  if (!AIRTABLE_API_KEY) {
    console.error('ERROR: AIRTABLE_API_KEY required');
    process.exit(1);
  }
  if (!OPENAI_API_KEY) {
    console.error('ERROR: OPENAI_API_KEY required');
    process.exit(1);
  }
  
  // Fetch unscored contacts
  console.log('Fetching unscored contacts...');
  const contacts = await fetchUnscoredContacts();
  console.log(`\nFound ${contacts.length} contacts to score\n`);
  
  if (contacts.length === 0) {
    console.log('No contacts need scoring.');
    return;
  }
  
  // Score in batches
  let scored = 0;
  const scoreCounts = { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 };
  
  for (let i = 0; i < contacts.length; i += BATCH_SIZE) {
    const batch = contacts.slice(i, i + BATCH_SIZE);
    console.log(`Scoring batch ${Math.floor(i/BATCH_SIZE) + 1} (${batch.length} contacts)...`);
    
    const scores = await scoreContactsBatch(batch);
    
    if (scores.length > 0) {
      await updateContactScores(scores);
      scored += scores.length;
      
      for (const s of scores) {
        scoreCounts[s.score] = (scoreCounts[s.score] || 0) + 1;
      }
      
      console.log(`  Scored ${scores.length} contacts`);
    }
    
    // Small delay between OpenAI calls
    await sleep(500);
  }
  
  console.log('\n========== SCORING COMPLETE ==========');
  console.log(`Total scored: ${scored}`);
  console.log('Distribution:');
  console.log(`  Score 1 (Best): ${scoreCounts[1] || 0}`);
  console.log(`  Score 2 (Great): ${scoreCounts[2] || 0}`);
  console.log(`  Score 3 (Good): ${scoreCounts[3] || 0}`);
  console.log(`  Score 4 (Maybe): ${scoreCounts[4] || 0}`);
  console.log(`  Score 5 (Skip): ${scoreCounts[5] || 0}`);
}

main().catch(err => {
  console.error('Scoring failed:', err);
  process.exit(1);
});
