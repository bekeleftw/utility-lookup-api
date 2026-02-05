#!/usr/bin/env node
/**
 * Push contacts to Smartlead with prioritization
 * 
 * Strategy:
 * 1. Group contacts by company
 * 2. For each score level (1, 2, 3), push 1 contact per company
 * 3. Rotate through companies so each gets representation
 * 4. Skip scores 4 and 5
 * 
 * Environment variables:
 *   AIRTABLE_API_KEY
 *   AIRTABLE_BASE_ID
 *   SMARTLEAD_API_KEY
 *   SMARTLEAD_CAMPAIGN_ID
 */

const https = require('https');

const AIRTABLE_API_KEY = process.env.AIRTABLE_API_KEY;
const AIRTABLE_BASE_ID = process.env.AIRTABLE_BASE_ID || 'app3PpZscmxtjR64U';
const SMARTLEAD_API_KEY = process.env.SMARTLEAD_API_KEY;
const SMARTLEAD_CAMPAIGN_ID = process.env.SMARTLEAD_CAMPAIGN_ID;

const LEADGEN_CONTACTS_TABLE_ID = 'LeadGen_Contacts';
const MAX_SCORE = 3; // Only push scores 1, 2, 3
const SMARTLEAD_BATCH_SIZE = 100;
const AIRTABLE_DELAY_MS = 100;
const SMARTLEAD_DELAY_MS = 1000;

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

// Fetch all scored contacts that haven't been synced to Smartlead
async function fetchScoredContacts() {
  const contacts = [];
  let offset = null;
  
  do {
    const params = new URLSearchParams({
      pageSize: '100',
      filterByFormula: `AND({lead_score}!='', {lead_score}<=3, OR({smartlead_synced}='', {smartlead_synced}=FALSE()))`
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
      console.log(`  Fetched ${records.length} contacts (total: ${contacts.length})`);
    } else {
      console.error('Error fetching contacts:', response.body);
      break;
    }
    
    await sleep(AIRTABLE_DELAY_MS);
  } while (offset);
  
  return contacts;
}

// Group contacts by company and score
function groupAndPrioritize(contacts) {
  // Group by company_record_id
  const byCompany = {};
  
  for (const contact of contacts) {
    const companyId = contact.fields.company_record_id || 'unknown';
    if (!byCompany[companyId]) {
      byCompany[companyId] = { 1: [], 2: [], 3: [] };
    }
    const score = parseInt(contact.fields.lead_score) || 3;
    if (score <= 3) {
      byCompany[companyId][score].push(contact);
    }
  }
  
  // Build prioritized list:
  // Round 1: First score-1 contact from each company
  // Round 2: First score-2 contact from each company (if no score-1 was sent)
  // Round 3: First score-3 contact from each company (if no score-1 or 2 was sent)
  // Round 4: Second score-1 contact from each company
  // ... and so on
  
  const prioritized = [];
  const companyIds = Object.keys(byCompany);
  let hasMore = true;
  let round = 0;
  
  while (hasMore) {
    hasMore = false;
    round++;
    
    for (const companyId of companyIds) {
      const company = byCompany[companyId];
      
      // For each round, try to get the next contact
      // Round 1: score 1, index 0
      // Round 2: score 2, index 0 (or score 1, index 1 if score 2 empty)
      // etc.
      
      for (let score = 1; score <= 3; score++) {
        const contacts = company[score];
        // Calculate which index we're on for this score
        // We want to exhaust score 1 before moving to score 2
        const prevScoreCounts = [1, 2, 3].slice(0, score - 1).reduce((sum, s) => sum + company[s].length, 0);
        const indexForThisRound = round - 1 - prevScoreCounts;
        
        if (indexForThisRound >= 0 && indexForThisRound < contacts.length) {
          prioritized.push(contacts[indexForThisRound]);
          hasMore = true;
          break; // Only one contact per company per round
        }
      }
    }
    
    // Safety limit
    if (round > 100) break;
  }
  
  return prioritized;
}

// Get email quality score (lower = better)
// 1 = Personal (john.smith@, jsmith@)
// 2 = Role-based (propertymanager@, owner@)
// 3 = Generic (info@, contact@, hello@, office@)
function getEmailQuality(email) {
  if (!email) return 3;
  const localPart = email.split('@')[0].toLowerCase();
  
  // Generic emails
  const genericPrefixes = ['info', 'contact', 'hello', 'office', 'admin', 'support', 'sales', 'team', 'mail', 'enquiries', 'inquiries'];
  if (genericPrefixes.some(p => localPart === p || localPart.startsWith(p + '.'))) {
    return 3;
  }
  
  // Role-based emails
  const rolePrefixes = ['propertymanager', 'pm', 'owner', 'manager', 'leasing', 'accounting', 'maintenance', 'operations'];
  if (rolePrefixes.some(p => localPart === p || localPart.startsWith(p + '.'))) {
    return 2;
  }
  
  // Personal email (has name-like pattern)
  return 1;
}

// Simpler prioritization: score 1s first (round robin), then 2s, then 3s
// Within each score, sort by email quality (personal > role-based > generic)
function simplePrioritize(contacts) {
  const byCompany = {};
  
  for (const contact of contacts) {
    const companyId = contact.fields.company_record_id || 'unknown';
    if (!byCompany[companyId]) {
      byCompany[companyId] = [];
    }
    byCompany[companyId].push(contact);
  }
  
  // Sort each company's contacts by score, then by email quality
  for (const companyId of Object.keys(byCompany)) {
    byCompany[companyId].sort((a, b) => {
      const scoreA = parseInt(a.fields.lead_score) || 5;
      const scoreB = parseInt(b.fields.lead_score) || 5;
      if (scoreA !== scoreB) return scoreA - scoreB;
      
      // Secondary sort by email quality
      const emailQualityA = getEmailQuality(a.fields.email);
      const emailQualityB = getEmailQuality(b.fields.email);
      return emailQualityA - emailQualityB;
    });
  }
  
  // Round robin: take 1st contact from each company, then 2nd, etc.
  const prioritized = [];
  const companyIds = Object.keys(byCompany);
  let index = 0;
  let hasMore = true;
  
  while (hasMore) {
    hasMore = false;
    for (const companyId of companyIds) {
      if (index < byCompany[companyId].length) {
        prioritized.push(byCompany[companyId][index]);
        hasMore = true;
      }
    }
    index++;
    if (index > 50) break; // Safety limit
  }
  
  return prioritized;
}

// Transform contact to Smartlead format
function toSmartleadLead(contact) {
  const f = contact.fields;
  return {
    first_name: f.first_name || '',
    last_name: f.last_name || '',
    email: f.email || '',
    company_name: f.company_name || '',
    location: f.company_city || '',
    custom_fields: {
      ref_id: f.ref_id || '',
      job_title: f.job_title || '',
      company_city: f.company_city || '',
      lead_score: String(f.lead_score || ''),
      airtable_record_id: contact.id
    }
  };
}

// Push leads to Smartlead
async function pushToSmartlead(leads) {
  const options = {
    hostname: 'server.smartlead.ai',
    path: `/api/v1/campaigns/${SMARTLEAD_CAMPAIGN_ID}/leads?api_key=${SMARTLEAD_API_KEY}`,
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
  };
  
  const payload = JSON.stringify({
    lead_list: leads,
    settings: {
      ignore_global_block_list: false,
      ignore_unsubscribe_list: false,
      ignore_duplicate_leads_in_other_campaign: false
    }
  });
  
  return makeRequest(options, payload);
}

// Mark contacts as synced in Airtable
async function markSynced(recordIds) {
  for (let i = 0; i < recordIds.length; i += 10) {
    const batch = recordIds.slice(i, i + 10);
    const records = batch.map(id => ({
      id,
      fields: { smartlead_synced: true }
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
    
    await makeRequest(options, JSON.stringify({ records }));
    await sleep(AIRTABLE_DELAY_MS);
  }
}

async function main() {
  console.log('Starting prioritized Smartlead push...\n');
  console.log(`Campaign ID: ${SMARTLEAD_CAMPAIGN_ID}`);
  console.log(`Max score to include: ${MAX_SCORE}\n`);
  
  if (!AIRTABLE_API_KEY || !SMARTLEAD_API_KEY || !SMARTLEAD_CAMPAIGN_ID) {
    console.error('ERROR: Missing required environment variables');
    process.exit(1);
  }
  
  // Fetch scored, unsynced contacts
  console.log('Fetching scored contacts (score 1-3, not yet synced)...');
  const contacts = await fetchScoredContacts();
  console.log(`\nFound ${contacts.length} contacts to push\n`);
  
  if (contacts.length === 0) {
    console.log('No contacts to push.');
    return;
  }
  
  // Prioritize
  console.log('Prioritizing contacts (round-robin by company, sorted by score)...');
  const prioritized = simplePrioritize(contacts);
  console.log(`Prioritized ${prioritized.length} contacts\n`);
  
  // Show score distribution
  const scoreCounts = { 1: 0, 2: 0, 3: 0 };
  for (const c of prioritized) {
    const score = parseInt(c.fields.lead_score) || 3;
    scoreCounts[score]++;
  }
  console.log('Score distribution:');
  console.log(`  Score 1: ${scoreCounts[1]}`);
  console.log(`  Score 2: ${scoreCounts[2]}`);
  console.log(`  Score 3: ${scoreCounts[3]}\n`);
  
  // Push in batches
  let totalUploaded = 0;
  const syncedIds = [];
  
  for (let i = 0; i < prioritized.length; i += SMARTLEAD_BATCH_SIZE) {
    const batch = prioritized.slice(i, i + SMARTLEAD_BATCH_SIZE);
    const leads = batch.map(toSmartleadLead);
    
    console.log(`Pushing batch ${Math.floor(i/SMARTLEAD_BATCH_SIZE) + 1} (${leads.length} leads)...`);
    
    const response = await pushToSmartlead(leads);
    
    if (response.status === 200 && response.body.ok) {
      console.log(`  Uploaded: ${response.body.upload_count || 0}`);
      console.log(`  Duplicates: ${response.body.duplicate_count || 0}`);
      totalUploaded += response.body.upload_count || 0;
      syncedIds.push(...batch.map(c => c.id));
    } else {
      console.error('  Error:', response.body);
    }
    
    await sleep(SMARTLEAD_DELAY_MS);
  }
  
  // Mark as synced
  if (syncedIds.length > 0) {
    console.log(`\nMarking ${syncedIds.length} contacts as synced...`);
    await markSynced(syncedIds);
  }
  
  console.log('\n========== PUSH COMPLETE ==========');
  console.log(`Total uploaded to Smartlead: ${totalUploaded}`);
  console.log(`Records marked as synced: ${syncedIds.length}`);
}

main().catch(err => {
  console.error('Push failed:', err);
  process.exit(1);
});
