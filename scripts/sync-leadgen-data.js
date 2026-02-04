#!/usr/bin/env node
/**
 * Sync HubSpot Companies and Contacts to Airtable for LeadGen Personalization
 * 
 * Usage: node scripts/sync-leadgen-data.js
 * 
 * Environment variables:
 *   HUBSPOT_API_KEY - HubSpot private app token
 *   AIRTABLE_API_KEY - Airtable API key
 *   AIRTABLE_BASE_ID - Airtable base ID
 */

const https = require('https');

// Configuration - all from environment variables
const HUBSPOT_API_KEY = process.env.HUBSPOT_API_KEY;
const AIRTABLE_API_KEY = process.env.AIRTABLE_API_KEY;
const AIRTABLE_BASE_ID = process.env.AIRTABLE_BASE_ID;

// Airtable table IDs (will be set after tables are created)
const LEADGEN_COMPANIES_TABLE_ID = process.env.LEADGEN_COMPANIES_TABLE_ID || 'LeadGen_Companies';
const LEADGEN_CONTACTS_TABLE_ID = process.env.LEADGEN_CONTACTS_TABLE_ID || 'LeadGen_Contacts';

// PMS Configuration
const PMS_CONFIG = {
  'Appfolio': {
    name: 'AppFolio',
    color: '#2596be',
    logo_url: 'https://learn.appfolio.com/apm/www/favicons/fb-icon-554x554.png'
  },
  'Buildium': {
    name: 'Buildium',
    color: '#6eaf7c',
    logo_url: 'https://www.balancedassetsolutions.com/wp-content/uploads/2024/04/buildium.jpg'
  },
  'Propertyware': {
    name: 'Propertyware',
    color: '#023055',
    logo_url: 'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQFzfOq2cQK9zJNDk35kSNVBcDouMSHv0g2Bg&s'
  },
  'Rentvine': {
    name: 'Rentvine',
    color: '#01a04d',
    logo_url: 'https://media.licdn.com/dms/image/v2/D4E0BAQH94ledr4pKhg/company-logo_200_200/B4EZtqf1t0HEAI-/0/1767018290445/rentvine_logo?e=2147483647&v=beta&t=4GzQENJGGYVNpoUXHfNPy2Q9gR78hb9uUX1_wKGbJRY'
  },
  'Yardi': {
    name: 'Yardi',
    color: '#0273d0',
    logo_url: 'https://assets.noviams.com/novi-file-uploads/aaa/members/white-yardi-logo-on-gradient-300px-circle.png'
  }
};

const PMS_FALLBACK = {
  name: 'your PMS',
  color: '#f37023',
  logo_url: 'https://cdn.prod.website-files.com/659dd5a41f44c8d830f6cd7f/697c37dcd58b074371333e0f_sync-icon-orange-circle.svg'
};

// Static address fields
const STATIC_ADDRESSES = {
  address_1_street: '847 Oak St',
  address_2_street: '2156 Maple Ave',
  address_3_street: '31 Willow Creek Ter'
};

// Rate limiting
const HUBSPOT_RATE_LIMIT_MS = 110; // ~10 requests per second
const AIRTABLE_RATE_LIMIT_MS = 210; // ~5 requests per second

// Helper: Sleep
function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// Helper: Make HTTPS request
function makeRequest(options, postData = null) {
  return new Promise((resolve, reject) => {
    const req = https.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          const json = JSON.parse(data);
          if (res.statusCode >= 400) {
            reject({ statusCode: res.statusCode, body: json });
          } else {
            resolve(json);
          }
        } catch (e) {
          if (res.statusCode >= 400) {
            reject({ statusCode: res.statusCode, body: data });
          } else {
            resolve(data);
          }
        }
      });
    });
    req.on('error', reject);
    if (postData) req.write(postData);
    req.end();
  });
}

// State name to 2-letter code mapping
const STATE_CODES = {
  'alabama': 'AL', 'alaska': 'AK', 'arizona': 'AZ', 'arkansas': 'AR', 'california': 'CA',
  'colorado': 'CO', 'connecticut': 'CT', 'delaware': 'DE', 'florida': 'FL', 'georgia': 'GA',
  'hawaii': 'HI', 'idaho': 'ID', 'illinois': 'IL', 'indiana': 'IN', 'iowa': 'IA',
  'kansas': 'KS', 'kentucky': 'KY', 'louisiana': 'LA', 'maine': 'ME', 'maryland': 'MD',
  'massachusetts': 'MA', 'michigan': 'MI', 'minnesota': 'MN', 'mississippi': 'MS', 'missouri': 'MO',
  'montana': 'MT', 'nebraska': 'NE', 'nevada': 'NV', 'new hampshire': 'NH', 'new jersey': 'NJ',
  'new mexico': 'NM', 'new york': 'NY', 'north carolina': 'NC', 'north dakota': 'ND', 'ohio': 'OH',
  'oklahoma': 'OK', 'oregon': 'OR', 'pennsylvania': 'PA', 'rhode island': 'RI', 'south carolina': 'SC',
  'south dakota': 'SD', 'tennessee': 'TN', 'texas': 'TX', 'utah': 'UT', 'vermont': 'VT',
  'virginia': 'VA', 'washington': 'WA', 'west virginia': 'WV', 'wisconsin': 'WI', 'wyoming': 'WY',
  'district of columbia': 'DC', 'puerto rico': 'PR'
};

// Convert state name to 2-letter code
function getStateCode(state) {
  if (!state) return '';
  const trimmed = state.trim();
  // Already a 2-letter code
  if (trimmed.length === 2 && /^[A-Za-z]{2}$/.test(trimmed)) {
    return trimmed.toUpperCase();
  }
  // Look up full name
  const code = STATE_CODES[trimmed.toLowerCase()];
  return code || trimmed.toUpperCase().substring(0, 2);
}

// Generate URL-safe ref_id
function generateRefId(companyName, state) {
  if (!companyName) return '';
  const slug = companyName
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, '')
    .replace(/\s+/g, '-')
    .substring(0, 50);
  const stateCode = getStateCode(state) || 'us';
  return `${slug}-${stateCode.toLowerCase()}`;
}

// Format company city
function formatCompanyCity(city, state) {
  if (!city) return '';
  const stateCode = getStateCode(state);
  return stateCode ? `${city}, ${stateCode}` : city;
}

// Get PMS config
function getPmsConfig(currentSoftware) {
  if (!currentSoftware) return PMS_FALLBACK;
  
  // Try exact match first
  if (PMS_CONFIG[currentSoftware]) {
    return PMS_CONFIG[currentSoftware];
  }
  
  // Try case-insensitive match
  const lowerSoftware = currentSoftware.toLowerCase();
  for (const [key, config] of Object.entries(PMS_CONFIG)) {
    if (key.toLowerCase() === lowerSoftware || lowerSoftware.includes(key.toLowerCase())) {
      return config;
    }
  }
  
  return PMS_FALLBACK;
}

// HubSpot API: Search companies
async function searchHubSpotCompanies(after = null) {
  const body = {
    filterGroups: [
      {
        filters: [
          {
            propertyName: 'company_type',
            operator: 'IN',
            values: ['Property Manager', 'Mixed']
          }
        ]
      },
      {
        filters: [
          {
            propertyName: 'company_type',
            operator: 'NOT_HAS_PROPERTY'
          }
        ]
      }
    ],
    properties: [
      'hs_object_id',
      'name',
      'company_name__clean_',
      'city',
      'state_',
      'hs_logo_url',
      'current_software',
      'company_type',
      'company_status'
    ],
    limit: 100
  };
  
  if (after) {
    body.after = after;
  }
  
  const options = {
    hostname: 'api.hubapi.com',
    path: '/crm/v3/objects/companies/search',
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${HUBSPOT_API_KEY}`,
      'Content-Type': 'application/json'
    }
  };
  
  await sleep(HUBSPOT_RATE_LIMIT_MS);
  return makeRequest(options, JSON.stringify(body));
}

// HubSpot API: Get company's associated deals
async function getCompanyDeals(companyId) {
  const options = {
    hostname: 'api.hubapi.com',
    path: `/crm/v3/objects/companies/${companyId}/associations/deals`,
    method: 'GET',
    headers: {
      'Authorization': `Bearer ${HUBSPOT_API_KEY}`
    }
  };
  
  await sleep(HUBSPOT_RATE_LIMIT_MS);
  return makeRequest(options);
}

// HubSpot API: Get deal details
async function getDealDetails(dealId) {
  const options = {
    hostname: 'api.hubapi.com',
    path: `/crm/v3/objects/deals/${dealId}?properties=hs_is_closed_won`,
    method: 'GET',
    headers: {
      'Authorization': `Bearer ${HUBSPOT_API_KEY}`
    }
  };
  
  await sleep(HUBSPOT_RATE_LIMIT_MS);
  return makeRequest(options);
}

// HubSpot API: Get company's associated contacts
async function getCompanyContacts(companyId) {
  const options = {
    hostname: 'api.hubapi.com',
    path: `/crm/v3/objects/companies/${companyId}/associations/contacts`,
    method: 'GET',
    headers: {
      'Authorization': `Bearer ${HUBSPOT_API_KEY}`
    }
  };
  
  await sleep(HUBSPOT_RATE_LIMIT_MS);
  return makeRequest(options);
}

// HubSpot API: Get contact details
async function getContactDetails(contactId) {
  const options = {
    hostname: 'api.hubapi.com',
    path: `/crm/v3/objects/contacts/${contactId}?properties=hs_object_id,firstname,first_name_clean,email,jobtitle`,
    method: 'GET',
    headers: {
      'Authorization': `Bearer ${HUBSPOT_API_KEY}`
    }
  };
  
  await sleep(HUBSPOT_RATE_LIMIT_MS);
  return makeRequest(options);
}

// Check if company has closed-won deals
async function hasClosedWonDeal(companyId) {
  try {
    const associations = await getCompanyDeals(companyId);
    const dealIds = (associations.results || []).map(r => r.id);
    
    for (const dealId of dealIds) {
      try {
        const deal = await getDealDetails(dealId);
        if (deal.properties && deal.properties.hs_is_closed_won === 'true') {
          return true;
        }
      } catch (e) {
        // Skip if deal not found
      }
    }
    return false;
  } catch (e) {
    return false;
  }
}

// Airtable API: Find record by field value
async function findAirtableRecord(tableId, fieldName, fieldValue) {
  const formula = encodeURIComponent(`{${fieldName}}='${fieldValue}'`);
  const options = {
    hostname: 'api.airtable.com',
    path: `/v0/${AIRTABLE_BASE_ID}/${encodeURIComponent(tableId)}?filterByFormula=${formula}&maxRecords=1`,
    method: 'GET',
    headers: {
      'Authorization': `Bearer ${AIRTABLE_API_KEY}`
    }
  };
  
  await sleep(AIRTABLE_RATE_LIMIT_MS);
  const result = await makeRequest(options);
  return result.records && result.records.length > 0 ? result.records[0] : null;
}

// Airtable API: Create record
async function createAirtableRecord(tableId, fields) {
  const options = {
    hostname: 'api.airtable.com',
    path: `/v0/${AIRTABLE_BASE_ID}/${encodeURIComponent(tableId)}`,
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${AIRTABLE_API_KEY}`,
      'Content-Type': 'application/json'
    }
  };
  
  await sleep(AIRTABLE_RATE_LIMIT_MS);
  return makeRequest(options, JSON.stringify({ fields }));
}

// Airtable API: Update record
async function updateAirtableRecord(tableId, recordId, fields) {
  const options = {
    hostname: 'api.airtable.com',
    path: `/v0/${AIRTABLE_BASE_ID}/${encodeURIComponent(tableId)}/${recordId}`,
    method: 'PATCH',
    headers: {
      'Authorization': `Bearer ${AIRTABLE_API_KEY}`,
      'Content-Type': 'application/json'
    }
  };
  
  await sleep(AIRTABLE_RATE_LIMIT_MS);
  return makeRequest(options, JSON.stringify({ fields }));
}

// Upsert company to Airtable
async function upsertCompany(company) {
  const props = company.properties || {};
  const companyId = props.hs_object_id || company.id;
  const companyName = props.company_name__clean_ || props.name || '';
  const city = props.city || '';
  const state = props.state_ || '';
  const companyCity = formatCompanyCity(city, state);
  const pmsConfig = getPmsConfig(props.current_software);
  
  const fields = {
    record_id: companyId,
    ref_id: generateRefId(companyName, state),
    company_name: companyName,
    company_city: companyCity,
    logo_url: props.hs_logo_url || '',
    pms_name: pmsConfig.name,
    pms_color: pmsConfig.color,
    pms_logo_url: pmsConfig.logo_url,
    address_1_street: STATIC_ADDRESSES.address_1_street,
    address_1_city: companyCity,
    address_2_street: STATIC_ADDRESSES.address_2_street,
    address_2_city: companyCity,
    address_3_street: STATIC_ADDRESSES.address_3_street,
    address_3_city: companyCity
  };
  
  try {
    const existing = await findAirtableRecord(LEADGEN_COMPANIES_TABLE_ID, 'record_id', companyId);
    if (existing) {
      await updateAirtableRecord(LEADGEN_COMPANIES_TABLE_ID, existing.id, fields);
      return { action: 'updated', companyId };
    } else {
      await createAirtableRecord(LEADGEN_COMPANIES_TABLE_ID, fields);
      return { action: 'created', companyId };
    }
  } catch (e) {
    console.error(`Error upserting company ${companyId}:`, e.body || e.message || e);
    return { action: 'error', companyId, error: e };
  }
}

// Upsert contact to Airtable
async function upsertContact(contact, companyData) {
  const props = contact.properties || {};
  const contactId = props.hs_object_id || contact.id;
  const firstName = props.first_name_clean || props.firstname || '';
  
  const fields = {
    contact_id: contactId,
    company_record_id: companyData.companyId,
    first_name: firstName,
    email: props.email || '',
    job_title: props.jobtitle || '',
    company_name: companyData.companyName,
    company_city: companyData.companyCity,
    ref_id: companyData.refId
  };
  
  try {
    const existing = await findAirtableRecord(LEADGEN_CONTACTS_TABLE_ID, 'contact_id', contactId);
    if (existing) {
      await updateAirtableRecord(LEADGEN_CONTACTS_TABLE_ID, existing.id, fields);
      return { action: 'updated', contactId };
    } else {
      await createAirtableRecord(LEADGEN_CONTACTS_TABLE_ID, fields);
      return { action: 'created', contactId };
    }
  } catch (e) {
    console.error(`Error upserting contact ${contactId}:`, e.body || e.message || e);
    return { action: 'error', contactId, error: e };
  }
}

// Main sync function
async function syncLeadGenData() {
  console.log('Starting HubSpot to Airtable sync...');
  console.log(`Airtable Base: ${AIRTABLE_BASE_ID}`);
  console.log(`Companies Table: ${LEADGEN_COMPANIES_TABLE_ID}`);
  console.log(`Contacts Table: ${LEADGEN_CONTACTS_TABLE_ID}`);
  console.log('');
  
  if (!HUBSPOT_API_KEY) {
    console.error('ERROR: HUBSPOT_API_KEY environment variable is required');
    process.exit(1);
  }
  
  if (!AIRTABLE_API_KEY) {
    console.error('ERROR: AIRTABLE_API_KEY environment variable is required');
    process.exit(1);
  }
  
  if (!AIRTABLE_BASE_ID) {
    console.error('ERROR: AIRTABLE_BASE_ID environment variable is required');
    process.exit(1);
  }
  
  const stats = {
    companiesProcessed: 0,
    companiesCreated: 0,
    companiesUpdated: 0,
    companiesSkipped: 0,
    companiesError: 0,
    contactsProcessed: 0,
    contactsCreated: 0,
    contactsUpdated: 0,
    contactsError: 0
  };
  
  let after = null;
  let totalCompanies = 0;
  let processedCount = 0;
  
  // First pass: count total companies
  console.log('Fetching companies from HubSpot...');
  
  do {
    try {
      const response = await searchHubSpotCompanies(after);
      const companies = response.results || [];
      totalCompanies += companies.length;
      after = response.paging?.next?.after || null;
    } catch (e) {
      console.error('Error fetching companies:', e.body || e.message || e);
      break;
    }
  } while (after);
  
  console.log(`Found ${totalCompanies} companies matching criteria`);
  console.log('');
  
  // Second pass: process companies
  after = null;
  
  do {
    try {
      const response = await searchHubSpotCompanies(after);
      const companies = response.results || [];
      
      for (const company of companies) {
        processedCount++;
        const props = company.properties || {};
        const companyId = props.hs_object_id || company.id;
        const companyName = props.company_name__clean_ || props.name || 'Unknown';
        const companyStatus = props.company_status || '';
        
        console.log(`Processing company ${processedCount} of ${totalCompanies}: ${companyName} (${companyId})`);
        
        // Skip if status is Onboarding or Pending Decision
        if (companyStatus === 'Onboarding' || companyStatus === 'Pending Decision') {
          console.log(`  Skipping: status is ${companyStatus}`);
          stats.companiesSkipped++;
          continue;
        }
        
        // Skip if has closed-won deal
        const hasWonDeal = await hasClosedWonDeal(companyId);
        if (hasWonDeal) {
          console.log(`  Skipping: has closed-won deal`);
          stats.companiesSkipped++;
          continue;
        }
        
        // Upsert company
        const companyResult = await upsertCompany(company);
        stats.companiesProcessed++;
        
        if (companyResult.action === 'created') {
          stats.companiesCreated++;
          console.log(`  Company created`);
        } else if (companyResult.action === 'updated') {
          stats.companiesUpdated++;
          console.log(`  Company updated`);
        } else {
          stats.companiesError++;
          console.log(`  Company error`);
          continue;
        }
        
        // Prepare company data for contacts
        const city = props.city || '';
        const state = props.state_ || '';
        const companyCity = formatCompanyCity(city, state);
        const refId = generateRefId(companyName, state);
        
        const companyData = {
          companyId,
          companyName,
          companyCity,
          refId
        };
        
        // Fetch and process contacts
        try {
          const contactAssociations = await getCompanyContacts(companyId);
          const contactIds = (contactAssociations.results || []).map(r => r.id);
          
          for (const contactId of contactIds) {
            try {
              const contact = await getContactDetails(contactId);
              const contactResult = await upsertContact(contact, companyData);
              stats.contactsProcessed++;
              
              if (contactResult.action === 'created') {
                stats.contactsCreated++;
              } else if (contactResult.action === 'updated') {
                stats.contactsUpdated++;
              } else {
                stats.contactsError++;
              }
            } catch (e) {
              console.log(`  Error processing contact ${contactId}`);
              stats.contactsError++;
            }
          }
          
          if (contactIds.length > 0) {
            console.log(`  Processed ${contactIds.length} contacts`);
          }
        } catch (e) {
          // No contacts or error fetching
        }
      }
      
      after = response.paging?.next?.after || null;
    } catch (e) {
      console.error('Error in sync loop:', e.body || e.message || e);
      break;
    }
  } while (after);
  
  // Print summary
  console.log('');
  console.log('=== Sync Complete ===');
  console.log(`Companies processed: ${stats.companiesProcessed}`);
  console.log(`  Created: ${stats.companiesCreated}`);
  console.log(`  Updated: ${stats.companiesUpdated}`);
  console.log(`  Skipped: ${stats.companiesSkipped}`);
  console.log(`  Errors: ${stats.companiesError}`);
  console.log(`Contacts processed: ${stats.contactsProcessed}`);
  console.log(`  Created: ${stats.contactsCreated}`);
  console.log(`  Updated: ${stats.contactsUpdated}`);
  console.log(`  Errors: ${stats.contactsError}`);
}

// Run
syncLeadGenData().catch(e => {
  console.error('Fatal error:', e);
  process.exit(1);
});
