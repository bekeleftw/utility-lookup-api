// Utility Lookup Widget - Full Featured (No Guide)
(function() {
const API_URL = 'https://web-production-9acc6.up.railway.app/api/lookup';
const FEEDBACK_URL = 'https://web-production-9acc6.up.railway.app/api/feedback';
const form = document.getElementById('utilityForm');
const input = document.getElementById('addressInput');
const btn = document.getElementById('searchBtn');
const results = document.getElementById('utilityResults');
const toggles = document.querySelectorAll('.up-toggle');
const icons = { electric: '⚡', gas: '🔥', water: '💧', internet: '🌐' };
const typeLabels = { electric: 'Electric', gas: 'Natural Gas', water: 'Water', internet: 'Internet' };
const sourceExplanations = {'municipal_utility':'Verified municipal utility','municipal':'Verified municipal utility','special_district':'Special district boundary','user_confirmed':'Confirmed by users','verified':'State regulatory data','hifld':'Federal territory data','eia_861':'Federal utility data','eia':'Federal utility data','google_serp':'Web search verified','serp':'Web search verified','epa_sdwis':'EPA water data','epa':'EPA water data','fcc':'FCC broadband data','supplemental':'Curated database'};
function getSourceExplanation(source) {
if (!source) return null;
if (sourceExplanations[source]) return sourceExplanations[source];
const sl = source.toLowerCase();
if (sl.includes('municipal')) return 'Verified municipal utility';
if (sl.includes('eia') || sl.includes('861')) return 'Federal utility data';
if (sl.includes('hifld')) return 'Federal territory data';
if (sl.includes('coop')) return 'Electric co-op territory';
if (sl.includes('serp') || sl.includes('google')) return 'Web search verified';
if (sl.includes('epa') || sl.includes('sdwis')) return 'EPA water data';
if (sl.includes('fcc')) return 'FCC broadband data';
if (sl.includes('user') || sl.includes('confirmed')) return 'Confirmed by users';
if (sl.includes('special') || sl.includes('district')) return 'Special district boundary';
return null;
}
let currentAddress = '';
let currentZipCode = '';
toggles.forEach(toggle => {
toggle.addEventListener('click', (e) => {
e.preventDefault();
const checkbox = toggle.querySelector('input');
checkbox.checked = !checkbox.checked;
toggle.classList.toggle('active', checkbox.checked);
});
});
function getSelectedUtilities() {
const selected = [];
toggles.forEach(toggle => { if (toggle.querySelector('input').checked) selected.push(toggle.dataset.utility); });
return selected;
}
document.addEventListener('click', (e) => {
if (!e.target.closest('.up-badge-confidence')) {
document.querySelectorAll('.up-confidence-dropdown.open').forEach(d => d.classList.remove('open'));
document.querySelectorAll('.up-badge-confidence.open').forEach(b => b.classList.remove('open'));
}
});
if (!form) { console.error('Utility widget: form element not found'); return; }
form.addEventListener('submit', async (e) => {
e.preventDefault();
const address = input.value.trim();
if (!address) return;
currentAddress = address;
const utilities = getSelectedUtilities();
if (utilities.length === 0) { results.innerHTML = '<div class="up-error">Please select at least one utility type.</div>'; return; }
btn.disabled = true;
btn.textContent = 'Searching...';
const streamUrl = API_URL.replace('/lookup', '/lookup/stream');
const params = new URLSearchParams({ address: address, utilities: utilities.join(',') });
results.innerHTML = '<div class="up-status-message" id="upStatusMsg"><div class="up-loading-spinner"></div><span>Starting lookup...</span></div><div id="upLocationContainer"></div><div class="up-results" id="upStreamResults">' + (utilities.includes('electric') ? '<div id="upElectricSlot" class="up-result-slot up-loading-slot"><div class="up-loading-spinner-small"></div> Looking up electric...</div>' : '') + (utilities.includes('gas') ? '<div id="upGasSlot" class="up-result-slot up-loading-slot"><div class="up-loading-spinner-small"></div> Looking up gas...</div>' : '') + (utilities.includes('water') ? '<div id="upWaterSlot" class="up-result-slot up-loading-slot"><div class="up-loading-spinner-small"></div> Looking up water...</div>' : '') + (utilities.includes('internet') ? '<div id="upInternetSlot" class="up-result-slot up-loading-slot"><div class="up-loading-spinner-small"></div> Looking up internet...</div>' : '') + '</div>';
const streamData = { utilities: {}, location: null };
try {
const eventSource = new EventSource(streamUrl + '?' + params);
eventSource.onmessage = (event) => {
const msg = JSON.parse(event.data);
if (msg.event === 'status') { document.getElementById('upStatusMsg').innerHTML = '<div class="up-loading-spinner"></div><span>' + msg.message + '</span>'; }
else if (msg.event === 'geocode') { streamData.location = msg.data; currentZipCode = msg.data?.zip_code || ''; document.getElementById('upLocationContainer').innerHTML = '<div class="up-location"><span class="up-location-icon">📍</span>' + (msg.data.city || '') + ', ' + (msg.data.county ? msg.data.county + ' County, ' : '') + (msg.data.state || '') + '</div>'; }
else if (msg.event === 'electric') { const slot = document.getElementById('upElectricSlot'); if (msg.data) { streamData.utilities.electric = [msg.data]; slot.outerHTML = renderUtilityCard(msg.data, 'electric'); attachBadgeListeners(); attachFeedbackListeners(); } else { slot.innerHTML = '<div class="up-no-result">⚡ ' + (msg.note || 'No electric provider found') + '</div>'; slot.classList.remove('up-loading-slot'); } }
else if (msg.event === 'gas') { const slot = document.getElementById('upGasSlot'); if (msg.data) { streamData.utilities.gas = [msg.data]; slot.outerHTML = renderUtilityCard(msg.data, 'gas'); attachBadgeListeners(); attachFeedbackListeners(); } else { slot.innerHTML = '<div class="up-no-result">🔥 ' + (msg.note || 'No gas provider found') + '</div>'; slot.classList.remove('up-loading-slot'); } }
else if (msg.event === 'water') { const slot = document.getElementById('upWaterSlot'); if (msg.data) { streamData.utilities.water = [msg.data]; slot.outerHTML = renderUtilityCard(msg.data, 'water'); attachBadgeListeners(); attachFeedbackListeners(); } else { slot.innerHTML = '<div class="up-no-result">💧 ' + (msg.note || 'No water provider found') + '</div>'; slot.classList.remove('up-loading-slot'); } }
else if (msg.event === 'internet') { const slot = document.getElementById('upInternetSlot'); if (msg.data && msg.data.providers && msg.data.providers.length > 0) { streamData.utilities.internet = msg.data; slot.outerHTML = renderInternetCard(msg.data); } else { slot.innerHTML = '<div class="up-no-result">🌐 ' + (msg.note || 'No internet data available') + '</div>'; slot.classList.remove('up-loading-slot'); } }
else if (msg.event === 'complete') { document.getElementById('upStatusMsg').remove(); eventSource.close(); btn.disabled = false; btn.textContent = 'Search'; }
else if (msg.event === 'error') { results.innerHTML = '<div class="up-error">' + msg.message + '</div>'; eventSource.close(); btn.disabled = false; btn.textContent = 'Search'; }
};
eventSource.onerror = () => { eventSource.close(); if (!streamData.location) { results.innerHTML = '<div class="up-error">Connection lost. Please try again.</div>'; } else { var s = document.getElementById('upStatusMsg'); if(s) s.remove(); } btn.disabled = false; btn.textContent = 'Search'; };
} catch (error) { results.innerHTML = '<div class="up-error">Failed to connect to API. Please try again.</div>'; btn.disabled = false; btn.textContent = 'Search'; }
});
function renderUtilityCard(util, type) {
const cardId = 'card-' + type + '-' + Date.now();
let badges = '';
if (util.type && ['MUD', 'CDD', 'PUD', 'WCID', 'Metro District'].includes(util.type)) { badges += '<span class="up-badge up-badge-district">' + util.type + '</span>'; }
badges += getConfidenceBadgeWithDropdown(util, cardId);
let detailsLeft = '';
if (util.phone && util.phone !== 'NOT AVAILABLE') { detailsLeft += '<div class="up-detail"><span class="up-detail-label">Phone</span><span class="up-detail-value"><a href="tel:' + util.phone + '">' + util.phone + '</a></span></div>'; }
if (util.website && util.website !== 'NOT AVAILABLE') { const url = util.website.startsWith('http') ? util.website : 'https://' + util.website; detailsLeft += '<div class="up-detail"><span class="up-detail-label">Website</span><span class="up-detail-value"><a href="' + url + '" target="_blank">Visit site</a></span></div>'; }
let deregSection = '';
if (type === 'electric' && util.deregulated && util.deregulated.has_choice) { const dereg = util.deregulated; deregSection = '<div class="up-dereg-banner"><div class="up-dereg-header"><span class="up-dereg-icon">🎉</span><span class="up-dereg-title">' + (dereg.message || 'You have options!') + '</span></div><div class="up-dereg-body"><p class="up-dereg-explain">' + (dereg.how_it_works || dereg.explanation || '') + '</p>' + (dereg.choice_website ? '<a href="' + dereg.choice_website + '" target="_blank" class="up-dereg-cta"><span>🔍</span> Compare Providers</a>' : '') + '</div></div>'; }
let otherSection = '';
if (util.other_providers && util.other_providers.length > 0) { otherSection = '<div class="up-other-providers"><div class="up-other-label up-other-toggle" data-card="' + cardId + '">Other possible providers <span class="up-other-caret">▼</span></div><div class="up-other-list up-other-collapsed" id="' + cardId + '-others">' + util.other_providers.map(function(p, i) { const altId = cardId + '-alt-' + i; let altDetails = ''; const pName = p.name ? p.name.split(' ').map(function(w) { return w.charAt(0).toUpperCase() + w.slice(1).toLowerCase(); }).join(' ') : ''; if (p.phone && p.phone !== 'NOT AVAILABLE') { altDetails += '<div class="up-detail"><span class="up-detail-label">Phone</span><span class="up-detail-value"><a href="tel:' + p.phone + '">' + p.phone + '</a></span></div>'; } if (p.website && p.website !== 'NOT AVAILABLE') { const wurl = p.website.startsWith('http') ? p.website : 'https://' + p.website; altDetails += '<div class="up-detail"><span class="up-detail-label">Website</span><span class="up-detail-value"><a href="' + wurl + '" target="_blank">Visit site</a></span></div>'; } return '<div style="padding:12px 0;border-bottom:1px dashed #e5e7eb;" id="' + altId + '"><div class="up-provider-name" style="font-size:16px;">' + pName + '</div><div class="up-details" style="margin-top:4px;"><div class="up-details-left">' + altDetails + '</div><div class="up-feedback-inline" style="margin-left:auto;"><span>Correct?</span><button class="up-feedback-btn-small up-alt-btn yes" data-alt-id="' + altId + '" data-provider="' + p.name + '" data-type="' + type + '" data-response="yes">Yes</button><button class="up-feedback-btn-small up-alt-btn no" data-alt-id="' + altId + '" data-provider="' + p.name + '" data-type="' + type + '" data-response="no">No</button><span class="up-alt-done" id="' + altId + '-done">Thanks!</span></div></div></div>'; }).join('') + '</div></div>'; }
return '<div class="up-card" id="' + cardId + '"><div class="up-card-header"><div class="up-card-type"><div class="up-icon up-icon-' + type + '">' + icons[type] + '</div><span class="up-type-label">' + typeLabels[type] + '</span></div><div class="up-header-badges">' + badges + '</div></div><div class="up-provider-section"><div class="up-provider-name">' + (util.name || 'Unknown Provider') + '</div></div>' + deregSection + '<div class="up-details"><div class="up-details-left">' + detailsLeft + '</div><div class="up-feedback-inline" data-card="' + cardId + '" data-type="' + type + '" data-provider="' + (util.name || '') + '"><span>Correct?</span><button class="up-feedback-btn-small yes" data-response="yes">Yes</button><button class="up-feedback-btn-small no" data-response="no">No</button><span class="up-feedback-done" id="' + cardId + '-done">Thanks!</span></div></div>' + otherSection + '<div class="up-feedback-form" id="' + cardId + '-form"><label>What is the correct ' + typeLabels[type].toLowerCase() + ' provider?</label><input type="text" placeholder="Enter correct provider name" id="' + cardId + '-correction" /><button class="up-feedback-submit" data-card="' + cardId + '" data-type="' + type + '">Submit</button></div><div class="up-url-form" id="' + cardId + '-url-form"><label>Know where to check service? (optional)</label><input type="url" placeholder="https://utility.com/start-service" id="' + cardId + '-service-url" /><div class="up-url-buttons"><button class="up-url-submit" data-card="' + cardId + '" data-type="' + type + '">Submit</button><button class="up-url-skip" data-card="' + cardId + '">Skip</button></div></div></div>';
}
function getConfidenceBadgeWithDropdown(util, cardId) {
const score = util.confidence_score;
const source = util._source || util.source || '';
let badgeClass, badgeLabel;
if (score !== undefined && score !== null) { if (score >= 85) { badgeClass = 'up-badge-verified'; badgeLabel = 'Verified'; } else if (score >= 70) { badgeClass = 'up-badge-high'; badgeLabel = 'High Confidence'; } else if (score >= 50) { badgeClass = 'up-badge-medium'; badgeLabel = 'Medium'; } else { badgeClass = 'up-badge-low'; badgeLabel = 'Low Confidence'; } }
else { const confidence = util.confidence || 'medium'; const map = { 'verified': { c: 'up-badge-verified', l: 'Verified' }, 'high': { c: 'up-badge-high', l: 'High Confidence' }, 'medium': { c: 'up-badge-medium', l: 'Medium' }, 'low': { c: 'up-badge-low', l: 'Low Confidence' } }; const m = map[confidence] || map['medium']; badgeClass = m.c; badgeLabel = m.l; }
const explanation = getSourceExplanation(source);
const dropdownContent = score !== undefined && score !== null ? (explanation ? '<span class="score">' + score + '/100</span> - ' + explanation : '<span class="score">' + score + '/100</span> confidence') : (explanation || 'Confidence details unavailable');
return '<span class="up-badge ' + badgeClass + ' up-badge-confidence" data-dropdown="' + cardId + '-dropdown">' + badgeLabel + '<span class="up-badge-caret">▼</span></span><div class="up-confidence-dropdown" id="' + cardId + '-dropdown">' + dropdownContent + '</div>';
}
function getTechType(tech) {
  if (!tech) return { label: 'Unknown', dot: '' };
  const t = tech.toLowerCase();
  if (t.includes('fiber')) return { label: 'Fiber', dot: 'fiber' };
  if (t.includes('cable') || t.includes('docsis')) return { label: 'Cable', dot: 'cable' };
  if (t.includes('dsl') || t.includes('adsl') || t.includes('vdsl')) return { label: 'DSL', dot: 'dsl' };
  if (t.includes('5g') || t.includes('lte') || t.includes('wireless') || t.includes('fixed')) return { label: 'Wireless', dot: 'wireless' };
  if (t.includes('satellite')) return { label: 'Satellite', dot: 'satellite' };
  return { label: tech, dot: '' };
}
function renderInternetCard(inet) {
  const providers = inet.providers || [];
  if (providers.length === 0) return '<div class="up-card"><div class="up-no-result">🌐 No internet providers found</div></div>';
  const sorted = [...providers].sort((a, b) => (b.max_download_mbps || 0) - (a.max_download_mbps || 0));
  const hasFiber = sorted.some(p => (p.technology || '').toLowerCase().includes('fiber'));
  const hasCable = sorted.some(p => (p.technology || '').toLowerCase().includes('cable'));
  let badge = '<span class="up-badge up-badge-medium">Limited Options</span>';
  if (hasFiber) badge = '<span class="up-badge up-badge-verified">Fiber Available</span>';
  else if (hasCable) badge = '<span class="up-badge up-badge-high">Cable Available</span>';
  const rows = sorted.map(p => {
    const tech = getTechType(p.technology);
    const down = p.max_download_mbps || '?';
    const up = p.max_upload_mbps || '?';
    return '<tr><td class="up-internet-provider-cell">' + (p.name || 'Unknown') + '</td><td><span class="up-internet-type-cell"><span class="up-internet-type-dot ' + tech.dot + '"></span>' + tech.label + '</span></td><td class="up-internet-speed-cell"><span class="up-internet-speed-down">' + down + '</span> / ' + up + ' Mbps</td></tr>';
  }).join('');
  return '<div class="up-card"><div class="up-card-header"><div class="up-card-type"><div class="up-icon up-icon-internet">' + icons.internet + '</div><span class="up-type-label">Internet</span></div><div class="up-header-badges">' + badge + '</div></div><table class="up-internet-table"><thead><tr><th>Provider</th><th>Type</th><th>Speed</th></tr></thead><tbody>' + rows + '</tbody></table></div>';
}
function attachBadgeListeners() {
document.querySelectorAll('.up-badge-confidence:not([data-listener])').forEach(badge => {
badge.setAttribute('data-listener', 'true');
badge.addEventListener('click', function(e) { e.stopPropagation(); const dropdownId = this.dataset.dropdown; const dropdown = document.getElementById(dropdownId); document.querySelectorAll('.up-confidence-dropdown.open').forEach(d => { if (d.id !== dropdownId) d.classList.remove('open'); }); document.querySelectorAll('.up-badge-confidence.open').forEach(b => { if (b !== this) b.classList.remove('open'); }); dropdown.classList.toggle('open'); this.classList.toggle('open'); });
});
}
function attachFeedbackListeners() {
document.querySelectorAll('.up-feedback-btn-small:not([data-listener])').forEach(btn => {
btn.setAttribute('data-listener', 'true');
btn.addEventListener('click', function() { const feedback = this.closest('.up-feedback-inline'); const cardId = feedback.dataset.card; const type = feedback.dataset.type; const provider = feedback.dataset.provider; const response = this.dataset.response; feedback.querySelectorAll('.up-feedback-btn-small').forEach(b => b.classList.remove('selected')); this.classList.add('selected'); if (response === 'yes') { feedback.querySelectorAll('.up-feedback-btn-small').forEach(b => b.style.display = 'none'); document.getElementById(cardId + '-url-form').classList.add('open'); } else { document.getElementById(cardId + '-form').classList.add('open'); } });
});
document.querySelectorAll('.up-feedback-submit:not([data-listener])').forEach(btn => {
btn.setAttribute('data-listener', 'true');
btn.addEventListener('click', function() { const cardId = this.dataset.card; const type = this.dataset.type; const correction = document.getElementById(cardId + '-correction').value.trim(); if (!correction) { alert('Please enter the correct provider name'); return; } const feedback = document.querySelector('.up-feedback-inline[data-card="' + cardId + '"]'); const returnedProvider = feedback.dataset.provider; fetch(FEEDBACK_URL, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ address: currentAddress, zip_code: currentZipCode, utility_type: type, returned_provider: returnedProvider, correct_provider: correction, is_correct: false, source: 'web_widget' }) }).catch(e => console.error('Failed to submit feedback:', e)); document.getElementById(cardId + '-form').classList.remove('open'); feedback.querySelectorAll('.up-feedback-btn-small').forEach(b => b.style.display = 'none'); document.getElementById(cardId + '-done').classList.add('show'); });
});
document.querySelectorAll('.up-url-submit:not([data-listener])').forEach(btn => {
btn.setAttribute('data-listener', 'true');
btn.addEventListener('click', function() { const cardId = this.dataset.card; const type = this.dataset.type; const serviceUrl = document.getElementById(cardId + '-service-url').value.trim(); const feedback = document.querySelector('.up-feedback-inline[data-card="' + cardId + '"]'); const provider = feedback.dataset.provider; fetch(FEEDBACK_URL, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ address: currentAddress, zip_code: currentZipCode, utility_type: type, returned_provider: provider, is_correct: true, service_check_url: serviceUrl || null, source: 'web_widget' }) }).catch(e => console.error('Failed to submit feedback:', e)); document.getElementById(cardId + '-url-form').classList.remove('open'); document.getElementById(cardId + '-done').classList.add('show'); });
});
document.querySelectorAll('.up-url-skip:not([data-listener])').forEach(btn => {
btn.setAttribute('data-listener', 'true');
btn.addEventListener('click', function() { const cardId = this.dataset.card; const feedback = document.querySelector('.up-feedback-inline[data-card="' + cardId + '"]'); const type = feedback.dataset.type; const provider = feedback.dataset.provider; fetch(FEEDBACK_URL, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ address: currentAddress, zip_code: currentZipCode, utility_type: type, returned_provider: provider, is_correct: true, source: 'web_widget' }) }).catch(e => console.error('Failed to submit feedback:', e)); document.getElementById(cardId + '-url-form').classList.remove('open'); document.getElementById(cardId + '-done').classList.add('show'); });
});
// Toggle for other providers section
document.querySelectorAll('.up-other-toggle:not([data-listener])').forEach(toggle => {
toggle.setAttribute('data-listener', 'true');
toggle.addEventListener('click', function() { const cardId = this.dataset.card; const list = document.getElementById(cardId + '-others'); list.classList.toggle('up-other-collapsed'); this.querySelector('.up-other-caret').textContent = list.classList.contains('up-other-collapsed') ? '▼' : '▲'; });
});
// Alternative provider feedback buttons
document.querySelectorAll('.up-alt-btn:not([data-listener])').forEach(btn => {
btn.setAttribute('data-listener', 'true');
btn.addEventListener('click', function() { const altId = this.dataset.altId; const provider = this.dataset.provider; const type = this.dataset.type; const response = this.dataset.response; const item = document.getElementById(altId); item.querySelectorAll('.up-alt-btn').forEach(b => b.style.display = 'none'); document.getElementById(altId + '-done').classList.add('show'); fetch(FEEDBACK_URL, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ address: currentAddress, zip_code: currentZipCode, utility_type: type, returned_provider: provider, is_correct: response === 'yes', is_alternative: true, source: 'web_widget' }) }).catch(e => console.error('Failed to submit feedback:', e)); });
});
}
// Mode Toggle (Single vs Bulk)
const singleModeBtn = document.getElementById('singleModeBtn');
const bulkModeBtn = document.getElementById('bulkModeBtn');
const bulkSection = document.getElementById('bulkSection');
const bulkInput = document.getElementById('bulkInput');
const bulkSearchBtn = document.getElementById('bulkSearchBtn');
const bulkResults = document.getElementById('bulkResults');
const bulkGrid = document.getElementById('bulkGrid');
const bulkStats = document.getElementById('bulkStats');
let bulkVerifiedCount = 0;
let bulkTotalCount = 0;

if (singleModeBtn && bulkModeBtn) {
  singleModeBtn.addEventListener('click', () => {
    singleModeBtn.classList.add('active');
    bulkModeBtn.classList.remove('active');
    form.classList.remove('up-hidden');
    if (bulkSection) bulkSection.classList.add('up-hidden');
    if (bulkResults) bulkResults.classList.add('up-hidden');
    results.classList.remove('up-hidden');
  });
  bulkModeBtn.addEventListener('click', () => {
    bulkModeBtn.classList.add('active');
    singleModeBtn.classList.remove('active');
    form.classList.add('up-hidden');
    if (bulkSection) bulkSection.classList.remove('up-hidden');
    results.classList.add('up-hidden');
  });
}

if (bulkSearchBtn) {
  bulkSearchBtn.addEventListener('click', async () => {
    const text = bulkInput.value.trim();
    if (!text) { alert('Please enter at least one address'); return; }
    const addresses = text.split('\n').map(a => a.trim()).filter(a => a.length > 0);
    if (addresses.length === 0) { alert('Please enter at least one address'); return; }
    if (addresses.length > 20) { alert('Maximum 20 addresses at a time'); return; }
    const utilities = getSelectedUtilities();
    if (utilities.length === 0) { alert('Please select at least one utility type'); return; }
    
    bulkResults.classList.remove('up-hidden');
    bulkGrid.innerHTML = '';
    bulkVerifiedCount = 0;
    bulkTotalCount = 0;
    updateBulkStats();
    
    // Create placeholder rows
    addresses.forEach((addr, i) => {
      const rowId = 'bulk-row-' + i;
      bulkGrid.innerHTML += '<div class="up-bulk-row loading" id="' + rowId + '"><div class="up-bulk-address">' + addr + '</div><div class="up-bulk-utilities"><div class="up-bulk-util"><span style="color:#9ca3af;">Loading...</span></div></div></div>';
    });
    
    // Process each address
    for (let i = 0; i < addresses.length; i++) {
      const addr = addresses[i];
      const rowId = 'bulk-row-' + i;
      const row = document.getElementById(rowId);
      
      try {
        const params = new URLSearchParams({ address: addr, utilities: utilities.join(',') });
        const response = await fetch(API_URL + '?' + params);
        const data = await response.json();
        
        if (data.error) {
          row.innerHTML = '<div class="up-bulk-address">' + addr + '</div><div class="up-bulk-utilities"><div class="up-bulk-util" style="color:#ef4444;">Error: ' + data.error + '</div></div>';
          row.classList.remove('loading');
          continue;
        }
        
        let utilsHtml = '';
        const utilTypes = ['electric', 'gas', 'water'];
        utilTypes.forEach(type => {
          if (!utilities.includes(type)) return;
          const util = data.utilities[type]?.[0];
          if (!util) return;
          const utilId = rowId + '-' + type;
          bulkTotalCount++;
          utilsHtml += '<div class="up-bulk-util" id="' + utilId + '"><div class="up-bulk-util-info"><span class="up-bulk-util-icon">' + icons[type] + '</span><span class="up-bulk-util-name">' + (util.name || 'Unknown') + '</span></div><div class="up-bulk-actions"><button class="up-bulk-btn yes" data-util-id="' + utilId + '" data-addr="' + addr.replace(/"/g, '&quot;') + '" data-type="' + type + '" data-provider="' + (util.name || '').replace(/"/g, '&quot;') + '">✓</button><button class="up-bulk-btn no" data-util-id="' + utilId + '" data-addr="' + addr.replace(/"/g, '&quot;') + '" data-type="' + type + '" data-provider="' + (util.name || '').replace(/"/g, '&quot;') + '">✗</button></div></div>';
        });
        
        row.innerHTML = '<div class="up-bulk-address">' + addr + '</div><div class="up-bulk-utilities">' + (utilsHtml || '<div class="up-bulk-util" style="color:#9ca3af;">No utilities found</div>') + '</div>';
        row.classList.remove('loading');
        updateBulkStats();
        attachBulkFeedbackListeners();
        
      } catch (e) {
        row.innerHTML = '<div class="up-bulk-address">' + addr + '</div><div class="up-bulk-utilities"><div class="up-bulk-util" style="color:#ef4444;">Failed to fetch</div></div>';
        row.classList.remove('loading');
      }
    }
  });
}

function updateBulkStats() {
  if (bulkStats) bulkStats.textContent = bulkVerifiedCount + '/' + bulkTotalCount + ' verified';
}

function attachBulkFeedbackListeners() {
  document.querySelectorAll('.up-bulk-btn:not([data-listener])').forEach(btn => {
    btn.setAttribute('data-listener', 'true');
    btn.addEventListener('click', function() {
      const utilId = this.dataset.utilId;
      const addr = this.dataset.addr;
      const type = this.dataset.type;
      const provider = this.dataset.provider;
      const isYes = this.classList.contains('yes');
      const utilRow = document.getElementById(utilId);
      const actions = utilRow.querySelector('.up-bulk-actions');
      
      if (isYes) {
        // Show URL input form for verification link
        actions.innerHTML = '<div class="up-bulk-correction"><input type="url" placeholder="Verification URL (optional)" id="' + utilId + '-url" /><button class="up-bulk-url-submit" data-util-id="' + utilId + '" data-addr="' + addr.replace(/"/g, '&quot;') + '" data-type="' + type + '" data-provider="' + provider.replace(/"/g, '&quot;') + '">Submit</button><button class="up-bulk-url-skip" data-util-id="' + utilId + '" data-addr="' + addr.replace(/"/g, '&quot;') + '" data-type="' + type + '" data-provider="' + provider.replace(/"/g, '&quot;') + '" style="background:#f3f4f6;color:#6b7280;">Skip</button></div>';
        // Attach submit listener
        actions.querySelector('.up-bulk-url-submit').addEventListener('click', function() {
          const serviceUrl = document.getElementById(utilId + '-url').value.trim();
          actions.innerHTML = '<span class="up-bulk-done">✓ Verified</span>';
          utilRow.closest('.up-bulk-row').classList.add('verified');
          bulkVerifiedCount++;
          updateBulkStats();
          fetch(FEEDBACK_URL, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ address: addr, utility_type: type, returned_provider: provider, is_correct: true, service_check_url: serviceUrl || null, source: 'bulk_verify' }) }).catch(e => console.error('Feedback error:', e));
        });
        // Attach skip listener
        actions.querySelector('.up-bulk-url-skip').addEventListener('click', function() {
          actions.innerHTML = '<span class="up-bulk-done">✓ Verified</span>';
          utilRow.closest('.up-bulk-row').classList.add('verified');
          bulkVerifiedCount++;
          updateBulkStats();
          fetch(FEEDBACK_URL, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ address: addr, utility_type: type, returned_provider: provider, is_correct: true, source: 'bulk_verify' }) }).catch(e => console.error('Feedback error:', e));
        });
      } else {
        // Show correction input
        actions.innerHTML = '<div class="up-bulk-correction"><input type="text" placeholder="Correct provider?" id="' + utilId + '-input" /><button data-util-id="' + utilId + '" data-addr="' + addr.replace(/"/g, '&quot;') + '" data-type="' + type + '" data-provider="' + provider.replace(/"/g, '&quot;') + '">Submit</button></div>';
        utilRow.closest('.up-bulk-row').classList.add('corrected');
        // Attach submit listener
        actions.querySelector('button').addEventListener('click', function() {
          const correction = document.getElementById(utilId + '-input').value.trim();
          if (!correction) { alert('Please enter the correct provider'); return; }
          actions.innerHTML = '<span class="up-bulk-done" style="color:#f59e0b;">✓ Corrected</span>';
          bulkVerifiedCount++;
          updateBulkStats();
          fetch(FEEDBACK_URL, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ address: addr, utility_type: type, returned_provider: provider, correct_provider: correction, is_correct: false, source: 'bulk_verify' }) }).catch(e => console.error('Feedback error:', e));
        });
      }
    });
  });
}

// CSV Bulk Upload
const csvDropZone = document.getElementById('csvDropZone');
const csvInput = document.getElementById('csvInput');
const csvSelectBtn = document.getElementById('csvSelectBtn');
const csvProgress = document.getElementById('csvProgress');
const csvProgressFill = document.getElementById('csvProgressFill');
const csvProgressText = document.getElementById('csvProgressText');
const csvResults = document.getElementById('csvResults');
const csvSuccessCount = document.getElementById('csvSuccessCount');
const csvErrorCount = document.getElementById('csvErrorCount');
const csvDownloadBtn = document.getElementById('csvDownloadBtn');
let csvResultsData = [];
if (csvDropZone) { csvDropZone.addEventListener('dragover', e => { e.preventDefault(); csvDropZone.classList.add('dragover'); }); csvDropZone.addEventListener('dragleave', () => csvDropZone.classList.remove('dragover')); csvDropZone.addEventListener('drop', e => { e.preventDefault(); csvDropZone.classList.remove('dragover'); const file = e.dataTransfer.files[0]; if (file && file.name.endsWith('.csv')) processCSVFile(file); else alert('Please upload a CSV file'); }); }
if (csvSelectBtn) csvSelectBtn.addEventListener('click', e => { e.stopPropagation(); csvInput.click(); });
if (csvInput) csvInput.addEventListener('change', e => { const file = e.target.files[0]; if (file) processCSVFile(file); });
if (csvDownloadBtn) csvDownloadBtn.addEventListener('click', () => { if (csvResultsData.length === 0) return; const headers = Object.keys(csvResultsData[0]); const csvContent = [headers.join(','), ...csvResultsData.map(row => headers.map(h => { const val = row[h] || ''; if (val.toString().includes(',') || val.toString().includes('"')) return '"' + val.toString().replace(/"/g, '""') + '"'; return val; }).join(','))].join('\n'); const blob = new Blob([csvContent], { type: 'text/csv' }); const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = 'utility_lookup_results.csv'; a.click(); URL.revokeObjectURL(url); });
function parseCSV(text) { const lines = text.split('\n').filter(line => line.trim()); if (lines.length < 2) return { headers: [], rows: [] }; const parseRow = line => { const result = []; let current = ''; let inQuotes = false; for (let i = 0; i < line.length; i++) { const char = line[i]; if (char === '"') inQuotes = !inQuotes; else if (char === ',' && !inQuotes) { result.push(current.trim()); current = ''; } else current += char; } result.push(current.trim()); return result; }; const headers = parseRow(lines[0]); const rows = lines.slice(1).map(line => { const values = parseRow(line); const obj = {}; headers.forEach((h, i) => obj[h] = values[i] || ''); return obj; }); return { headers, rows }; }
function findAddressColumn(headers) { const addressCols = ['address', 'full_address', 'street_address', 'property_address', 'addr', 'location']; const headersLower = headers.map(h => h.toLowerCase().trim()); for (const col of addressCols) { const idx = headersLower.indexOf(col); if (idx !== -1) return headers[idx]; } return null; }
async function processCSVFile(file) { const text = await file.text(); const { headers, rows } = parseCSV(text); if (rows.length === 0) { alert('CSV file is empty'); return; } const addressCol = findAddressColumn(headers); if (!addressCol) { alert('Could not find address column.'); return; } const MAX_ROWS = 100; const processRows = rows.slice(0, MAX_ROWS); if (rows.length > MAX_ROWS) alert('Processing first ' + MAX_ROWS + ' addresses only'); const utilities = getSelectedUtilities(); if (utilities.length === 0) { alert('Please select at least one utility type'); return; } csvProgress.classList.add('show'); csvResults.classList.remove('show'); csvResultsData = []; let successCount = 0; let errorCount = 0; for (let i = 0; i < processRows.length; i++) { const row = processRows[i]; const address = row[addressCol]; const pct = Math.round(((i + 1) / processRows.length) * 100); csvProgressFill.style.width = pct + '%'; csvProgressText.textContent = 'Processing ' + (i + 1) + ' of ' + processRows.length + '...'; if (!address || !address.trim()) { csvResultsData.push({ ...row, _status: 'error', _error: 'Empty address', electric_provider: '', gas_provider: '', water_provider: '' }); errorCount++; continue; } try { const params = new URLSearchParams({ address: address.trim(), verify: 'true', utilities: utilities.join(',') }); const response = await fetch(API_URL + '?' + params); const data = await response.json(); if (data.error) { csvResultsData.push({ ...row, _status: 'error', _error: data.error, electric_provider: '', gas_provider: '', water_provider: '' }); errorCount++; } else { const result = { ...row, _status: 'success', _error: '' }; if (utilities.includes('electric') && data.utilities.electric?.length > 0) result.electric_provider = data.utilities.electric[0].name || ''; else result.electric_provider = ''; if (utilities.includes('gas') && data.utilities.gas?.length > 0) result.gas_provider = data.utilities.gas[0].name || ''; else result.gas_provider = ''; if (utilities.includes('water') && data.utilities.water?.length > 0) result.water_provider = data.utilities.water[0].name || ''; else result.water_provider = ''; if (data.location) { result._geocoded_city = data.location.city || ''; result._geocoded_state = data.location.state || ''; } csvResultsData.push(result); successCount++; } } catch (e) { csvResultsData.push({ ...row, _status: 'error', _error: e.message || 'API error', electric_provider: '', gas_provider: '', water_provider: '' }); errorCount++; } await new Promise(r => setTimeout(r, 200)); } csvProgress.classList.remove('show'); csvResults.classList.add('show'); csvSuccessCount.textContent = successCount; csvErrorCount.textContent = errorCount; }
})();
