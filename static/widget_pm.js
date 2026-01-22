// Utility Lookup Widget - Full Featured with Guide
(function() {
const API_URL = 'https://web-production-9acc6.up.railway.app/api/lookup';
const FEEDBACK_URL = 'https://web-production-9acc6.up.railway.app/api/feedback';
const GUIDE_URL = 'https://web-production-9acc6.up.railway.app/api/guide/request';
const form = document.getElementById('utilityForm');
const input = document.getElementById('addressInput');
const btn = document.getElementById('searchBtn');
const results = document.getElementById('utilityResults');
const toggles = document.querySelectorAll('.up-toggle');
const icons = { electric: '⚡', gas: '🔥', water: '💧', internet: '🌐' };
const typeLabels = { electric: 'Electric', gas: 'Natural Gas', water: 'Water', internet: 'Internet' };
const sourceExplanations = {
'municipal_utility': 'Verified municipal utility',
'municipal_utility_database': 'Verified municipal utility',
'Municipal Utility Database': 'Verified municipal utility',
'municipal': 'Verified municipal utility',
'municipal_gas': 'Verified municipal utility',
'special_district': 'Special district boundary',
'special_district_boundary': 'Special district boundary',
'texas_mud': 'Texas MUD boundary',
'florida_cdd': 'Florida CDD boundary',
'colorado_metro_district': 'Colorado Metro District',
'user_confirmed': 'Confirmed by users',
'user_feedback': 'Confirmed by users',
'user_correction': 'Confirmed by users',
'verified': 'State regulatory data',
'railroad_commission': 'State regulatory data',
'Texas Railroad Commission territory data': 'State regulatory data',
'texas_railroad_commission': 'State regulatory data',
'state_puc': 'State regulatory data',
'puc_territory': 'State regulatory data',
'hifld_polygon': 'Federal territory data',
'hifld': 'Federal territory data',
'HIFLD': 'Federal territory data',
'HIFLD Electric Cooperative Territory': 'Electric co-op territory',
'hifld_coop': 'Electric co-op territory',
'electric_cooperative': 'Electric co-op territory',
'electric_cooperative_polygon': 'Electric co-op territory',
'eia_861': 'Federal utility data',
'eia': 'Federal utility data',
'EIA': 'Federal utility data',
'EIA Form 861': 'Federal utility data',
'EIA Form 861 ZIP mapping': 'Federal utility data',
'eia_861_zip': 'Federal utility data',
'eia_861_zip_mapping': 'Federal utility data',
'eia_zip': 'Federal utility data',
'google_serp': 'Web search verified',
'serp': 'Web search verified',
'serp_verified': 'Web search verified',
'google': 'Web search verified',
'epa_sdwis': 'EPA water data',
'EPA SDWIS': 'EPA water data',
'epa': 'EPA water data',
'sdwis': 'EPA water data',
'supplemental': 'Curated database',
'Supplemental Data': 'Curated database',
'supplemental_file': 'Curated database',
'curated': 'Curated database',
'zip_override': 'Verified for this ZIP',
'zip_correction': 'Verified for this ZIP',
'manual_override': 'Manually verified',
'FCC Broadband Map': 'FCC broadband data',
'fcc': 'FCC broadband data',
'fcc_broadband': 'FCC broadband data',
'state_gas_mapping': 'State utility territory',
'state_ldc': 'State utility territory',
'ldc_territory': 'State utility territory'
};
function getSourceExplanation(source) {
if (!source) return null;
if (sourceExplanations[source]) return sourceExplanations[source];
const sourceLower = source.toLowerCase();
for (const [key, value] of Object.entries(sourceExplanations)) {
if (key.toLowerCase() === sourceLower) return value;
}
if (sourceLower.includes('municipal')) return 'Verified municipal utility';
if (sourceLower.includes('eia') || sourceLower.includes('861')) return 'Federal utility data';
if (sourceLower.includes('hifld')) return 'Federal territory data';
if (sourceLower.includes('coop') || sourceLower.includes('co-op')) return 'Electric co-op territory';
if (sourceLower.includes('serp') || sourceLower.includes('google')) return 'Web search verified';
if (sourceLower.includes('epa') || sourceLower.includes('sdwis')) return 'EPA water data';
if (sourceLower.includes('fcc') || sourceLower.includes('broadband')) return 'FCC broadband data';
if (sourceLower.includes('user') || sourceLower.includes('confirmed') || sourceLower.includes('feedback')) return 'Confirmed by users';
if (sourceLower.includes('special') || sourceLower.includes('district')) return 'Special district boundary';
if (sourceLower.includes('mud')) return 'Texas MUD boundary';
if (sourceLower.includes('cdd')) return 'Florida CDD boundary';
if (sourceLower.includes('railroad') || sourceLower.includes('puc')) return 'State regulatory data';
if (sourceLower.includes('override') || sourceLower.includes('correction')) return 'Verified for this ZIP';
if (sourceLower.includes('supplemental') || sourceLower.includes('curated')) return 'Curated database';
return null;
}
let currentAddress = '';
let currentZipCode = '';
let currentUtilityResults = null;
// Guide elements
const guideBtn = document.getElementById('guideBtn');
const guideModal = document.getElementById('guideModal');
const guideModalClose = document.getElementById('guideModalClose');
const guideModalAddress = document.getElementById('guideModalAddress');
const guideModalBody = document.getElementById('guideModalBody');
const guideForm = document.getElementById('guideForm');
if (guideBtn) { guideBtn.addEventListener('click', () => { guideModalAddress.textContent = currentAddress; guideModal.classList.add('open'); }); }
if (guideModalClose) { guideModalClose.addEventListener('click', () => { guideModal.classList.remove('open'); }); }
if (guideModal) { guideModal.addEventListener('click', (e) => { if (e.target === guideModal) { guideModal.classList.remove('open'); } }); }
if (guideForm) {
guideForm.addEventListener('submit', async (e) => {
e.preventDefault();
const submitBtn = document.getElementById('guideSubmit');
const email = document.getElementById('guideEmail').value.trim();
const company = document.getElementById('guideCompany').value.trim();
const website = document.getElementById('guideWebsite').value.trim();
if (!email || !company) { alert('Please fill in all required fields'); return; }
submitBtn.disabled = true;
submitBtn.textContent = 'Sending...';
try {
const response = await fetch(GUIDE_URL, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ address: currentAddress, utility_results: currentUtilityResults, email: email, company_name: company, website: website || null }) });
const data = await response.json();
if (data.success) {
guideModalBody.innerHTML = `<div class="up-modal-success"><div class="up-modal-success-icon">✅</div><h4 class="up-modal-success-title">Guide Request Submitted!</h4><p class="up-modal-success-desc">Your resident guide for <strong>${currentAddress}</strong> will be emailed to <strong>${email}</strong> in 5-10 minutes.</p></div>`;
} else {
alert(data.error || 'Failed to submit request. Please try again.');
submitBtn.disabled = false;
submitBtn.textContent = 'Send My Guide';
}
} catch (err) {
console.error('Guide request failed:', err);
alert('Failed to submit request. Please try again.');
submitBtn.disabled = false;
submitBtn.textContent = 'Send My Guide';
}
});
}
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
toggles.forEach(toggle => {
if (toggle.querySelector('input').checked) selected.push(toggle.dataset.utility);
});
return selected;
}
document.addEventListener('click', (e) => {
if (!e.target.closest('.up-badge-confidence')) {
document.querySelectorAll('.up-confidence-dropdown.open').forEach(d => d.classList.remove('open'));
document.querySelectorAll('.up-badge-confidence.open').forEach(b => b.classList.remove('open'));
}
});
form.addEventListener('submit', async (e) => {
e.preventDefault();
const address = input.value.trim();
if (!address) return;
currentAddress = address;
const utilities = getSelectedUtilities();
if (utilities.length === 0) {
results.innerHTML = '<div class="up-error">Please select at least one utility type.</div>';
return;
}
btn.disabled = true;
btn.textContent = 'Searching...';
if (guideBtn) guideBtn.classList.remove('show');
currentUtilityResults = null;
const streamUrl = API_URL.replace('/lookup', '/lookup/stream');
const params = new URLSearchParams({ address: address, utilities: utilities.join(',') });
results.innerHTML = `
<div class="up-status-message" id="upStatusMsg"><div class="up-loading-spinner"></div><span>Starting lookup...</span></div>
<div id="upLocationContainer"></div>
<div class="up-results" id="upStreamResults">
${utilities.includes('electric') ? '<div id="upElectricSlot" class="up-result-slot up-loading-slot"><div class="up-loading-spinner-small"></div> Looking up electric...</div>' : ''}
${utilities.includes('gas') ? '<div id="upGasSlot" class="up-result-slot up-loading-slot"><div class="up-loading-spinner-small"></div> Looking up gas...</div>' : ''}
${utilities.includes('water') ? '<div id="upWaterSlot" class="up-result-slot up-loading-slot"><div class="up-loading-spinner-small"></div> Looking up water...</div>' : ''}
${utilities.includes('internet') ? '<div id="upInternetSlot" class="up-result-slot up-loading-slot"><div class="up-loading-spinner-small"></div> Looking up internet...</div>' : ''}
</div>`;
const streamData = { utilities: {}, location: null };
try {
const eventSource = new EventSource(`${streamUrl}?${params}`);
eventSource.onmessage = (event) => {
const msg = JSON.parse(event.data);
if (msg.event === 'status') {
document.getElementById('upStatusMsg').innerHTML = `<div class="up-loading-spinner"></div><span>${msg.message}</span>`;
}
else if (msg.event === 'geocode') {
streamData.location = msg.data;
currentZipCode = msg.data?.zip_code || '';
document.getElementById('upLocationContainer').innerHTML = `<div class="up-location"><span class="up-location-icon">📍</span>${msg.data.city || ''}, ${msg.data.county ? msg.data.county + ' County, ' : ''}${msg.data.state || ''}</div>`;
}
else if (msg.event === 'electric') {
const slot = document.getElementById('upElectricSlot');
if (msg.data) {
streamData.utilities.electric = [msg.data];
slot.outerHTML = renderUtilityCard(msg.data, 'electric', [], null);
attachBadgeListeners();
attachFeedbackListeners();
} else {
slot.innerHTML = `<div class="up-no-result">⚡ ${msg.note || 'No electric provider found'}</div>`;
slot.classList.remove('up-loading-slot');
}
}
else if (msg.event === 'gas') {
const slot = document.getElementById('upGasSlot');
if (msg.data) {
streamData.utilities.gas = [msg.data];
slot.outerHTML = renderUtilityCard(msg.data, 'gas', [], null);
attachBadgeListeners();
attachFeedbackListeners();
} else {
slot.innerHTML = `<div class="up-no-result">🔥 ${msg.note || 'No gas provider found'}</div>`;
slot.classList.remove('up-loading-slot');
}
}
else if (msg.event === 'water') {
const slot = document.getElementById('upWaterSlot');
if (msg.data) {
streamData.utilities.water = [msg.data];
slot.outerHTML = renderUtilityCard(msg.data, 'water', [], null);
attachBadgeListeners();
attachFeedbackListeners();
} else {
slot.innerHTML = `<div class="up-no-result">💧 ${msg.note || 'No water provider found'}</div>`;
slot.classList.remove('up-loading-slot');
}
}
else if (msg.event === 'internet') {
const slot = document.getElementById('upInternetSlot');
if (msg.data && msg.data.providers && msg.data.providers.length > 0) {
streamData.utilities.internet = msg.data;
slot.outerHTML = renderInternetCard(msg.data);
} else {
slot.innerHTML = `<div class="up-no-result">🌐 ${msg.note || 'No internet data available'}</div>`;
slot.classList.remove('up-loading-slot');
}
}
else if (msg.event === 'complete') {
document.getElementById('upStatusMsg').remove();
eventSource.close();
btn.disabled = false;
btn.textContent = 'Search';
currentUtilityResults = { utilities: streamData.utilities, location: streamData.location };
if (guideBtn) guideBtn.classList.add('show');
}
else if (msg.event === 'error') {
results.innerHTML = `<div class="up-error">${msg.message}</div>`;
eventSource.close();
btn.disabled = false;
btn.textContent = 'Search';
}
};
eventSource.onerror = () => {
eventSource.close();
if (!streamData.location) {
results.innerHTML = '<div class="up-error">Connection lost. Please try again.</div>';
} else {
document.getElementById('upStatusMsg')?.remove();
}
btn.disabled = false;
btn.textContent = 'Search';
};
} catch (error) {
results.innerHTML = '<div class="up-error">Failed to connect to API. Please try again.</div>';
btn.disabled = false;
btn.textContent = 'Search';
}
});
function renderUtilityCard(util, type, alternatives, fallbackSource) {
const cardId = `card-${type}-${Date.now()}`;
let badges = '';
if (util.type && ['MUD', 'CDD', 'PUD', 'WCID', 'Metro District'].includes(util.type)) {
badges += `<span class="up-badge up-badge-district">${util.type}</span>`;
}
badges += getConfidenceBadgeWithDropdown(util, fallbackSource, cardId);
let detailsLeft = '';
if (util.phone && util.phone !== 'NOT AVAILABLE') {
detailsLeft += `<div class="up-detail"><span class="up-detail-label">Phone</span><span class="up-detail-value"><a href="tel:${util.phone}">${util.phone}</a></span></div>`;
}
if (util.website && util.website !== 'NOT AVAILABLE') {
const url = util.website.startsWith('http') ? util.website : 'https://' + util.website;
detailsLeft += `<div class="up-detail"><span class="up-detail-label">Website</span><span class="up-detail-value"><a href="${url}" target="_blank">Visit site</a></span></div>`;
}
let altSection = '';
if (alternatives && alternatives.length > 0) {
altSection = `<div class="up-alternatives"><div class="up-alternatives-label">Other possible providers</div><div class="up-alternatives-list">${alternatives.map(alt => `<div class="up-alt-chip"><span>${icons[type]}</span>${alt.name}</div>`).join('')}</div></div>`;
}
let deregSection = '';
if (type === 'electric' && util.deregulated && util.deregulated.has_choice) {
const dereg = util.deregulated;
deregSection = `<div class="up-dereg-banner"><div class="up-dereg-header"><span class="up-dereg-icon">🎉</span><span class="up-dereg-title">${dereg.message || 'You have options!'}</span></div><div class="up-dereg-body"><p class="up-dereg-explain">${dereg.how_it_works || dereg.explanation || ''}</p>${dereg.choice_website ? `<a href="${dereg.choice_website}" target="_blank" class="up-dereg-cta"><span>🔍</span> Compare Providers${dereg.choice_website_name ? ` on ${dereg.choice_website_name}` : ''}</a>` : ''}</div></div>`;
}
return `<div class="up-card" id="${cardId}">
<div class="up-card-header"><div class="up-card-type"><div class="up-icon up-icon-${type}">${icons[type]}</div><span class="up-type-label">${typeLabels[type]}</span></div><div class="up-header-badges">${badges}</div></div>
<div class="up-provider-section"><div class="up-provider-name">${util.name || 'Unknown Provider'}</div>${util.selection_reason ? `<div class="up-selection-reason">${util.selection_reason}</div>` : ''}</div>
${deregSection}
<div class="up-details"><div class="up-details-left">${detailsLeft}</div>
<div class="up-feedback-inline" data-card="${cardId}" data-type="${type}" data-provider="${util.name || ''}"><span>Correct?</span><button class="up-feedback-btn-small yes" data-response="yes">Yes</button><button class="up-feedback-btn-small no" data-response="no">No</button><span class="up-feedback-done" id="${cardId}-done">Thanks!</span></div></div>
<div class="up-feedback-form" id="${cardId}-form"><label>What's the correct ${typeLabels[type].toLowerCase()} provider?</label><input type="text" placeholder="Enter correct provider name" id="${cardId}-correction" /><button class="up-feedback-submit" data-card="${cardId}" data-type="${type}">Submit</button></div>
${altSection}</div>`;
}
function getConfidenceBadgeWithDropdown(util, fallbackSource, cardId) {
const score = util.confidence_score;
const source = util._source || util.source || util._verification_source || fallbackSource || '';
let badgeClass, badgeLabel;
if (score !== undefined && score !== null) {
if (score >= 85) { badgeClass = 'up-badge-verified'; badgeLabel = 'Verified'; }
else if (score >= 70) { badgeClass = 'up-badge-high'; badgeLabel = 'High Confidence'; }
else if (score >= 50) { badgeClass = 'up-badge-medium'; badgeLabel = 'Medium'; }
else { badgeClass = 'up-badge-low'; badgeLabel = 'Low Confidence'; }
} else {
const confidence = util.confidence || 'medium';
const map = { 'verified': { class: 'up-badge-verified', label: 'Verified' }, 'high': { class: 'up-badge-high', label: 'High Confidence' }, 'medium': { class: 'up-badge-medium', label: 'Medium' }, 'low': { class: 'up-badge-low', label: 'Low Confidence' } };
const m = map[confidence] || map['medium'];
badgeClass = m.class;
badgeLabel = m.label;
}
let explanation = getSourceExplanation(source);
let dropdownContent = '';
if (score !== undefined && score !== null) {
dropdownContent = explanation ? `<span class="score">${score}/100</span> · ${explanation}` : `<span class="score">${score}/100</span> confidence`;
} else {
dropdownContent = explanation || 'Confidence details unavailable';
}
return `<span class="up-badge ${badgeClass} up-badge-confidence" data-dropdown="${cardId}-dropdown">${badgeLabel}<span class="up-badge-caret">▼</span></span><div class="up-confidence-dropdown" id="${cardId}-dropdown">${dropdownContent}</div>`;
}
function renderInternetCard(inet) {
const providers = inet.providers || [];
const best = inet.best_wired;
let badge = inet.has_fiber ? '<span class="up-badge up-badge-verified">Fiber Available</span>' : inet.has_cable ? '<span class="up-badge up-badge-high">Cable Available</span>' : '<span class="up-badge up-badge-medium">Limited Options</span>';
const sortedProviders = [...providers].sort((a, b) => (b.max_download_mbps || 0) - (a.max_download_mbps || 0));
return `<div class="up-card"><div class="up-card-header"><div class="up-card-type"><div class="up-icon up-icon-internet">${icons.internet}</div><span class="up-type-label">Internet</span></div><div class="up-header-badges">${badge}</div></div>
<div class="up-internet-stats"><div class="up-stat"><span class="up-stat-value">${inet.provider_count}</span><span class="up-stat-label">Providers</span></div>${best ? `<div class="up-stat"><span class="up-stat-value">${best.max_download_mbps}</span><span class="up-stat-label">Max Mbps</span></div>` : ''}</div>
<div class="up-internet-list">${sortedProviders.map(provider => {
const isBest = best && provider.name === best.name;
return `<div class="up-internet-row ${isBest ? 'up-internet-row-best' : ''}"><div class="up-internet-provider"><span class="up-internet-name">${provider.name}</span><span class="up-internet-tech">${provider.technology || 'Unknown'}</span></div><div class="up-internet-speed"><span class="up-internet-down">${provider.max_download_mbps || '?'}</span><span class="up-internet-speed-label">↓ / ${provider.max_upload_mbps || '?'} ↑ Mbps</span></div></div>`;
}).join('')}</div></div>`;
}
function attachBadgeListeners() {
document.querySelectorAll('.up-badge-confidence:not([data-listener])').forEach(badge => {
badge.setAttribute('data-listener', 'true');
badge.addEventListener('click', function(e) {
e.stopPropagation();
const dropdownId = this.dataset.dropdown;
const dropdown = document.getElementById(dropdownId);
document.querySelectorAll('.up-confidence-dropdown.open').forEach(d => { if (d.id !== dropdownId) d.classList.remove('open'); });
document.querySelectorAll('.up-badge-confidence.open').forEach(b => { if (b !== this) b.classList.remove('open'); });
dropdown.classList.toggle('open');
this.classList.toggle('open');
});
});
}
function attachFeedbackListeners() {
document.querySelectorAll('.up-feedback-btn-small:not([data-listener])').forEach(btn => {
btn.setAttribute('data-listener', 'true');
btn.addEventListener('click', function() {
const feedback = this.closest('.up-feedback-inline');
const cardId = feedback.dataset.card;
const type = feedback.dataset.type;
const provider = feedback.dataset.provider;
const response = this.dataset.response;
feedback.querySelectorAll('.up-feedback-btn-small').forEach(b => b.classList.remove('selected'));
this.classList.add('selected');
if (response === 'yes') {
feedback.querySelectorAll('.up-feedback-btn-small').forEach(b => b.style.display = 'none');
document.getElementById(`${cardId}-done`).classList.add('show');
fetch(FEEDBACK_URL, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ address: currentAddress, zip_code: currentZipCode, utility_type: type, returned_provider: provider, is_correct: true, source: 'web_widget' }) }).catch(e => console.error('Failed to submit feedback:', e));
} else {
document.getElementById(`${cardId}-form`).classList.add('open');
}
});
});
document.querySelectorAll('.up-feedback-submit:not([data-listener])').forEach(btn => {
btn.setAttribute('data-listener', 'true');
btn.addEventListener('click', async function() {
const cardId = this.dataset.card;
const type = this.dataset.type;
const correction = document.getElementById(`${cardId}-correction`).value.trim();
if (!correction) { alert('Please enter the correct provider name'); return; }
const feedback = document.querySelector(`.up-feedback-inline[data-card="${cardId}"]`);
const returnedProvider = feedback.dataset.provider;
try {
await fetch(FEEDBACK_URL, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ address: currentAddress, zip_code: currentZipCode, utility_type: type, returned_provider: returnedProvider, correct_provider: correction, is_correct: false, source: 'web_widget' }) });
} catch (e) { console.error('Failed to submit feedback:', e); }
document.getElementById(`${cardId}-form`).classList.remove('open');
feedback.querySelectorAll('.up-feedback-btn-small').forEach(b => b.style.display = 'none');
document.getElementById(`${cardId}-done`).classList.add('show');
});
});
}
})();
