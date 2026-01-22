// Utility Lookup Widget with PM Guide Feature
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
 
 let currentAddress = '';
 let currentZipCode = '';
 let currentUtilityResults = null;
 
 // Resident Guide functionality
 const guideBtn = document.getElementById('guideBtn');
 const guideModal = document.getElementById('guideModal');
 const guideModalClose = document.getElementById('guideModalClose');
 const guideModalAddress = document.getElementById('guideModalAddress');
 const guideModalBody = document.getElementById('guideModalBody');
 const guideForm = document.getElementById('guideForm');
 
 if (guideBtn) {
   guideBtn.addEventListener('click', () => {
     guideModalAddress.textContent = currentAddress;
     guideModal.classList.add('open');
   });
 }
 
 if (guideModalClose) {
   guideModalClose.addEventListener('click', () => {
     guideModal.classList.remove('open');
   });
 }
 
 if (guideModal) {
   guideModal.addEventListener('click', (e) => {
     if (e.target === guideModal) {
       guideModal.classList.remove('open');
     }
   });
 }
 
 if (guideForm) {
   guideForm.addEventListener('submit', async (e) => {
     e.preventDefault();
     const submitBtn = document.getElementById('guideSubmit');
     const email = document.getElementById('guideEmail').value.trim();
     const company = document.getElementById('guideCompany').value.trim();
     const website = document.getElementById('guideWebsite').value.trim();
     
     if (!email || !company) {
       alert('Please fill in all required fields');
       return;
     }
     
     submitBtn.disabled = true;
     submitBtn.textContent = 'Sending...';
     
     try {
       const response = await fetch(GUIDE_URL, {
         method: 'POST',
         headers: { 'Content-Type': 'application/json' },
         body: JSON.stringify({
           address: currentAddress,
           utility_results: currentUtilityResults,
           email: email,
           company_name: company,
           website: website || null
         })
       });
       
       const data = await response.json();
       
       if (data.success) {
         guideModalBody.innerHTML = `
           <div class="up-modal-success">
             <div class="up-modal-success-icon">✅</div>
             <h4 class="up-modal-success-title">Guide Request Submitted!</h4>
             <p class="up-modal-success-desc">Your resident guide for <strong>${currentAddress}</strong> will be emailed to <strong>${email}</strong> in 5-10 minutes.</p>
           </div>
         `;
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

 const sourceExplanations = {
   'municipal_utility': 'Verified municipal utility',
   'eia_861': 'EIA federal data',
   'hifld': 'Federal territory data',
   'coop_boundaries': 'Electric co-op territory',
   'serp_api': 'Web search verified',
   'epa_water_boundaries': 'EPA water data',
   'fcc_broadband': 'FCC broadband data',
   'user_confirmed': 'Confirmed by users',
   'special_district': 'Special district boundary'
 };

 function getSourceExplanation(source) {
   if (!source) return null;
   if (sourceExplanations[source]) return sourceExplanations[source];
   const sl = source.toLowerCase();
   if (sl.includes('municipal')) return 'Verified municipal utility';
   if (sl.includes('eia')) return 'Federal utility data';
   if (sl.includes('coop')) return 'Electric co-op territory';
   if (sl.includes('fcc')) return 'FCC broadband data';
   return null;
 }

 // Toggle functionality
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
     if (toggle.querySelector('input').checked) {
       selected.push(toggle.dataset.utility);
     }
   });
   return selected;
 }

 // Form submit
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
   const params = new URLSearchParams({ address, utilities: utilities.join(',') });
   
   results.innerHTML = `
     <div class="up-status-message" id="upStatusMsg">
       <div class="up-loading-spinner"></div>
       <span>Starting lookup...</span>
     </div>
     <div id="upLocationContainer"></div>
     <div class="up-results" id="upStreamResults">
       ${utilities.includes('electric') ? '<div id="upElectricSlot" class="up-result-slot up-loading-slot"><div class="up-loading-spinner-small"></div> Looking up electric...</div>' : ''}
       ${utilities.includes('gas') ? '<div id="upGasSlot" class="up-result-slot up-loading-slot"><div class="up-loading-spinner-small"></div> Looking up gas...</div>' : ''}
       ${utilities.includes('water') ? '<div id="upWaterSlot" class="up-result-slot up-loading-slot"><div class="up-loading-spinner-small"></div> Looking up water...</div>' : ''}
       ${utilities.includes('internet') ? '<div id="upInternetSlot" class="up-result-slot up-loading-slot"><div class="up-loading-spinner-small"></div> Looking up internet...</div>' : ''}
     </div>
   `;

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
         document.getElementById('upLocationContainer').innerHTML = `
           <div class="up-location">
             <span class="up-location-icon">📍</span>
             ${msg.data.city || ''}, ${msg.data.county ? msg.data.county + ' County, ' : ''}${msg.data.state || ''}
           </div>
         `;
       }
       else if (msg.event === 'electric') {
         const slot = document.getElementById('upElectricSlot');
         if (msg.data) {
           streamData.utilities.electric = [msg.data];
           slot.outerHTML = renderUtilityCard(msg.data, 'electric');
         } else {
           slot.innerHTML = `<div class="up-no-result">⚡ ${msg.note || 'No electric provider found'}</div>`;
           slot.classList.remove('up-loading-slot');
         }
       }
       else if (msg.event === 'gas') {
         const slot = document.getElementById('upGasSlot');
         if (msg.data) {
           streamData.utilities.gas = [msg.data];
           slot.outerHTML = renderUtilityCard(msg.data, 'gas');
         } else {
           slot.innerHTML = `<div class="up-no-result">🔥 ${msg.note || 'No gas provider found'}</div>`;
           slot.classList.remove('up-loading-slot');
         }
       }
       else if (msg.event === 'water') {
         const slot = document.getElementById('upWaterSlot');
         if (msg.data) {
           streamData.utilities.water = [msg.data];
           slot.outerHTML = renderUtilityCard(msg.data, 'water');
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

 function renderUtilityCard(util, type) {
   const cardId = `card-${type}-${Date.now()}`;
   let badges = getConfidenceBadge(util, cardId);
   
   let detailsLeft = '';
   if (util.phone && util.phone !== 'NOT AVAILABLE') {
     detailsLeft += `<div class="up-detail"><span class="up-detail-label">Phone</span><span class="up-detail-value"><a href="tel:${util.phone}">${util.phone}</a></span></div>`;
   }
   if (util.website && util.website !== 'NOT AVAILABLE') {
     const url = util.website.startsWith('http') ? util.website : 'https://' + util.website;
     detailsLeft += `<div class="up-detail"><span class="up-detail-label">Website</span><span class="up-detail-value"><a href="${url}" target="_blank">Visit site</a></span></div>`;
   }

   let deregSection = '';
   if (type === 'electric' && util.deregulated && util.deregulated.has_choice) {
     const dereg = util.deregulated;
     deregSection = `
       <div class="up-dereg-banner">
         <div class="up-dereg-header"><span class="up-dereg-icon">🎉</span><span class="up-dereg-title">${dereg.message || 'You have options!'}</span></div>
         <div class="up-dereg-body">
           <p class="up-dereg-explain">${dereg.how_it_works || dereg.explanation || ''}</p>
           ${dereg.choice_website ? `<a href="${dereg.choice_website}" target="_blank" class="up-dereg-cta"><span>🔍</span> Compare Providers</a>` : ''}
         </div>
       </div>
     `;
   }

   return `
     <div class="up-card" id="${cardId}">
       <div class="up-card-header">
         <div class="up-card-type">
           <div class="up-icon up-icon-${type}">${icons[type]}</div>
           <span class="up-type-label">${typeLabels[type]}</span>
         </div>
         <div class="up-header-badges">${badges}</div>
       </div>
       <div class="up-provider-section">
         <div class="up-provider-name">${util.name || 'Unknown Provider'}</div>
       </div>
       ${deregSection}
       <div class="up-details">
         <div class="up-details-left">${detailsLeft}</div>
       </div>
     </div>
   `;
 }

 function getConfidenceBadge(util, cardId) {
   const score = util.confidence_score;
   let badgeClass, badgeLabel;
   if (score >= 85) { badgeClass = 'up-badge-verified'; badgeLabel = 'Verified'; }
   else if (score >= 70) { badgeClass = 'up-badge-high'; badgeLabel = 'High Confidence'; }
   else if (score >= 50) { badgeClass = 'up-badge-medium'; badgeLabel = 'Medium'; }
   else { badgeClass = 'up-badge-low'; badgeLabel = 'Low Confidence'; }
   return `<span class="up-badge ${badgeClass}">${badgeLabel}</span>`;
 }

 function renderInternetCard(inet) {
   const providers = inet.providers || [];
   let badge = inet.has_fiber ? '<span class="up-badge up-badge-verified">Fiber Available</span>' : 
               inet.has_cable ? '<span class="up-badge up-badge-high">Cable Available</span>' : 
               '<span class="up-badge up-badge-medium">Limited Options</span>';
   
   const sorted = [...providers].sort((a, b) => (b.max_download_mbps || 0) - (a.max_download_mbps || 0));
   
   return `
     <div class="up-card">
       <div class="up-card-header">
         <div class="up-card-type">
           <div class="up-icon up-icon-internet">${icons.internet}</div>
           <span class="up-type-label">Internet</span>
         </div>
         <div class="up-header-badges">${badge}</div>
       </div>
       <div class="up-internet-stats">
         <div class="up-stat"><span class="up-stat-value">${inet.provider_count}</span><span class="up-stat-label">Providers</span></div>
       </div>
       <div class="up-internet-list">
         ${sorted.slice(0, 5).map(p => `
           <div class="up-internet-row">
             <div class="up-internet-provider">
               <span class="up-internet-name">${p.name}</span>
               <span class="up-internet-tech">${p.technology || 'Unknown'}</span>
             </div>
             <div class="up-internet-speed">
               <span class="up-internet-down">${p.max_download_mbps || '?'}</span>
               <span class="up-internet-speed-label">↓ Mbps</span>
             </div>
           </div>
         `).join('')}
       </div>
     </div>
   `;
 }
})();
