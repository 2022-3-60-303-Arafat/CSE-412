// Owner pages: my listings, the listing form with rent details (PB-05), and
// legal verification requests with paper uploads (PB-10, PB-11, PB-14).

import { api } from '../api.js';
import {
  $, $$, DOCUMENT_LABELS, LISTING_STATUS, REQUEST_STATUS, REVIEW_STATUS, badge, confirmClick, describeValue, formatDate,
  html, mount, numberOrBlank, priceLine, submitting, toast, verificationBadge, ACTION_LABELS,
} from '../ui.js';

const MAX_UPLOAD_BYTES = 5 * 1024 * 1024;
const ALLOWED_EXTENSIONS = ['pdf', 'jpg', 'jpeg', 'png'];

// ------------------------------------------------------------------ my listings

function verificationCell(property) {
  const request = property.verificationRequest;
  if (property.verificationStatus === 'document_verified') {
    return html`${verificationBadge('document_verified')}
      ${request ? html`<a class="sub" href="#/owner/verification/${request.id}">View result</a>` : ''}`;
  }
  if (!request || request.status === 'document_verified') {
    return html`${verificationBadge('unverified')}
      <span class="sub">Not requested</span>`;
  }
  const papers = `${request.requiredUploaded} of ${request.requiredTotal} required papers uploaded`;
  const next = {
    pending: request.requiredUploaded < request.requiredTotal ? 'Upload your papers' : 'Waiting for an advocate',
    in_review: 'An advocate is checking your papers',
    issue_found: 'Issue found: see the notes and fix it',
  }[request.status];
  return html`${badge(request.status)}
    <span class="sub">${next}</span>
    ${request.status === 'pending' ? html`<span class="sub">${papers}</span>` : ''}`;
}

function listingActions(property) {
  const request = property.verificationRequest;
  const canRequest = property.verificationStatus !== 'document_verified' && property.listingStatus === 'active'
    && (!request || request.status === 'document_verified');
  return html`<div class="actions">
    ${canRequest ? html`<button class="btn btn-accent btn-small" type="button" data-request="${property.id}">Request legal verification</button>` : ''}
    ${request && request.status !== 'document_verified' ? html`<a class="btn btn-${request.status === 'issue_found' ? 'warn' : 'outline'} btn-small" href="#/owner/verification/${request.id}">${request.status === 'issue_found' ? 'Fix issue' : 'Papers'}</a>` : ''}
    <a class="btn btn-outline btn-small" href="#/property/${property.id}">View</a>
    <a class="btn btn-outline btn-small" href="#/owner/listings/${property.id}/edit">Edit</a>
    <button class="btn btn-danger btn-small" type="button" data-delete="${property.id}">Delete</button>
  </div>`;
}

export async function renderListings({ root, navigate }) {
  const { properties } = await api.get('/api/my/listings');
  const issues = properties.filter(p => p.verificationRequest?.status === 'issue_found');
  mount(root, html`
    <div class="page-head">
      <div><h1>My listings</h1><p>New listings go live at once as Unverified. Ask for legal verification to earn the Verified badge.</p></div>
      <a class="btn btn-accent" href="#/owner/listings/new">+ List a property</a>
    </div>
    ${issues.length ? html`<div class="notice notice-warn"><strong>An advocate found an issue with ${issues.length === 1 ? 'one listing' : `${issues.length} listings`}</strong>
      <p>Open "Fix issue" to read the notes and upload a corrected paper.</p></div>` : ''}
    ${properties.length ? html`
      <div class="table-wrap"><table class="data">
        <thead><tr><th>Listing</th><th>Price</th><th>Status</th><th class="num">Views</th><th>Legal verification</th><th class="num">Actions</th></tr></thead>
        <tbody>${properties.map(property => html`<tr>
          <td><a href="#/property/${property.id}"><strong>${property.title}</strong></a>
            <span class="sub">${property.areaName}, ${property.city} · ${property.propertyType} · ${property.listingType === 'rent' ? 'For rent' : 'For sale'}</span></td>
          <td>${priceLine(property)}</td>
          <td>${badge(property.listingStatus, LISTING_STATUS[property.listingStatus])}</td>
          <td class="num">${property.views.total}<span class="sub">${property.views.lastWeek} this week</span></td>
          <td>${verificationCell(property)}</td>
          <td>${listingActions(property)}</td>
        </tr>`)}</tbody>
      </table></div>` : html`
      <div class="empty"><h3>You have no listings yet</h3><p>Add your first property for sale or rent. It goes live right away.</p>
        <a class="btn btn-accent" href="#/owner/listings/new">+ List a property</a></div>`}
  `);

  root.addEventListener('click', async event => {
    const requestButton = event.target.closest('[data-request]');
    const deleteButton = event.target.closest('[data-delete]');
    try {
      if (requestButton) {
        requestButton.disabled = true;
        const { requestId } = await api.post(`/api/properties/${requestButton.dataset.request}/verification-request`);
        toast('Verification requested. Now upload your papers.');
        navigate(`/owner/verification/${requestId}`);
      } else if (deleteButton && confirmClick(deleteButton, 'Confirm delete')) {
        deleteButton.disabled = true;
        await api.del(`/api/properties/${deleteButton.dataset.delete}`);
        toast('Listing deleted. It no longer shows in search.');
        navigate('/owner/listings');
      }
    } catch (error) {
      toast(error.message, true);
      if (requestButton) requestButton.disabled = false;
      if (deleteButton) deleteButton.disabled = false;
    }
  });
}

// ------------------------------------------------------------------ listing form (PB-05, PB-09, PB-10)

function today() {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

export async function renderForm({ root, params, session, navigate }) {
  const editing = Boolean(params.id);
  const property = editing ? await api.get(`/api/properties/${params.id}`) : null;
  if (editing && !property.isOwner) {
    mount(root, html`<div class="empty"><h3>You can only edit your own listings</h3><a class="btn btn-primary" href="#/owner/listings">My listings</a></div>`);
    return;
  }
  const p = property || { listingType: 'rent', propertyType: 'Apartment', city: 'Dhaka', furnished: false, bedrooms: 2, bathrooms: 2 };
  const rent = p.rent || { minLeaseMonths: 12, tenantPreference: 'any', utilitiesIncluded: false };
  const { meta } = session;
  const selected = condition => (condition ? html`selected` : '');

  mount(root, html`
    <a class="back-link" href="#/owner/listings">&larr; My listings</a>
    <div class="page-head"><div>
      <h1>${editing ? 'Edit listing' : 'List a property'}</h1>
      <p>${editing ? 'Update the details buyers and tenants see.' : 'Your listing goes live as soon as you save it, with an "Unverified" label until an advocate checks your papers.'}</p>
    </div></div>
    ${editing && p.verificationStatus === 'document_verified' ? html`<div class="notice notice-info"><strong>This listing is verified</strong>
      <p>Changing the address, area, city, property type or Sale/Rent removes the Verified badge until the papers are checked again.</p></div>` : ''}
    <form id="listing-form" class="panel" novalidate>
      <p class="form-error notice notice-error" hidden></p>
      <fieldset class="form-section">
        <legend>Basics</legend>
        <div class="form-grid">
          <fieldset class="field full" data-error-for="listingType">
            <span>I want to</span>
            <div class="segmented" role="radiogroup" aria-label="Sale or rent">
              <label><input type="radio" name="listingType" value="sale" ${p.listingType === 'sale' ? html`checked` : ''}><span>Sell</span></label>
              <label><input type="radio" name="listingType" value="rent" ${p.listingType === 'rent' ? html`checked` : ''}><span>Rent out</span></label>
            </div>
          </fieldset>
          <label class="field full"><span>Title</span><input name="title" maxlength="100" value="${p.title || ''}" placeholder="e.g. Bright 3-bed flat near Dhanmondi Lake"></label>
          <label class="field"><span>Property type</span><select name="propertyType">
            ${meta.propertyTypes.map(type => html`<option ${selected(p.propertyType === type)}>${type}</option>`)}</select></label>
          <label class="field"><span>Size (sqft)</span><input name="sizeSqft" type="number" min="100" inputmode="numeric" value="${p.sizeSqft || ''}"></label>
          <label class="field"><span>Bedrooms</span><input name="bedrooms" type="number" min="0" max="20" value="${p.bedrooms}"></label>
          <label class="field"><span>Bathrooms</span><input name="bathrooms" type="number" min="0" max="20" value="${p.bathrooms}"></label>
          <label class="check full"><input type="checkbox" name="furnished" ${p.furnished ? html`checked` : ''}> Furnished</label>
        </div>
      </fieldset>

      <fieldset class="form-section">
        <legend>Location</legend>
        <div class="form-grid">
          <label class="field"><span>Area</span><input name="areaName" list="area-options" value="${p.areaName || ''}" placeholder="e.g. Gulshan 2">
            <datalist id="area-options">${meta.areas.map(area => html`<option value="${area}">`)}</datalist></label>
          <label class="field"><span>City</span><select name="city">
            ${meta.cities.map(city => html`<option ${selected(p.city === city)}>${city}</option>`)}</select></label>
          <label class="field full"><span>Full address</span><input name="address" value="${p.address || ''}" placeholder="House, road, area, city"></label>
        </div>
      </fieldset>

      <fieldset class="form-section" id="sale-section">
        <legend>Price</legend>
        <div class="form-grid">
          <label class="field"><span>Sale price (৳)</span><input name="price" type="number" min="1" inputmode="numeric" value="${p.price || ''}" placeholder="e.g. 12500000"></label>
        </div>
      </fieldset>

      <fieldset class="form-section rent-box" id="rent-section">
        <legend>Rent details</legend>
        <div class="form-grid">
          <label class="field"><span>Monthly rent (৳)</span><input name="rent.monthlyRent" type="number" min="1" inputmode="numeric" value="${rent.monthlyRent || ''}" placeholder="e.g. 35000"></label>
          <label class="field"><span>Security deposit (৳)</span><input name="rent.securityDeposit" type="number" min="0" inputmode="numeric" value="${rent.securityDeposit ?? ''}" placeholder="e.g. 70000"></label>
          <label class="field"><span>Available from</span><input name="rent.availableFrom" type="date" min="${today()}" value="${rent.availableFrom || ''}"></label>
          <label class="field"><span>Minimum lease (months)</span><input name="rent.minLeaseMonths" type="number" min="1" max="60" value="${rent.minLeaseMonths}"></label>
          <label class="field"><span>Tenant preference</span><select name="rent.tenantPreference">
            ${[['any', 'Anyone'], ['family', 'Family'], ['bachelor', 'Bachelor']].map(([value, label]) => html`<option value="${value}" ${selected(rent.tenantPreference === value)}>${label}</option>`)}
          </select></label>
          <label class="check"><input type="checkbox" name="rent.utilitiesIncluded" ${rent.utilitiesIncluded ? html`checked` : ''}> Utilities included in rent</label>
          <p class="full muted small" id="move-in" aria-live="polite"></p>
        </div>
      </fieldset>

      <fieldset class="form-section">
        <legend>Description</legend>
        <label class="field"><span>Describe the home <span class="hint">at least 20 characters</span></span>
          <textarea name="description" maxlength="2000">${p.description || ''}</textarea></label>
      </fieldset>

      ${editing ? html`
        <fieldset class="form-section"><legend>Listing status</legend>
          <label class="field"><span>Status</span><select name="listingStatus">
            <option value="active" ${selected(p.listingStatus === 'active')}>Active (shown in search)</option>
            <option value="sold_rented" ${selected(p.listingStatus === 'sold_rented')}>Sold / Rented (hidden from search)</option>
          </select></label>
        </fieldset>` : html`
        <div class="notice notice-info">
          <label class="check"><input type="checkbox" name="requestVerification" checked>
            <span><strong>Request Legal Verification</strong></span></label>
          <p>An advocate will check your land deed, mutation paper and tax receipt. You upload them on the next page. Your listing stays live while the check runs.</p>
        </div>`}

      <div class="form-actions">
        <button class="btn btn-primary" type="submit">${editing ? 'Save changes' : 'Publish listing'}</button>
        <a class="btn btn-outline" href="#/owner/listings">Cancel</a>
      </div>
    </form>
  `);

  const form = $('#listing-form', root);
  const field = name => form.querySelector(`[name="${name}"]`);

  function syncType() {
    const isRent = form.querySelector('input[name="listingType"]:checked')?.value === 'rent';
    $('#rent-section', form).hidden = !isRent;
    $('#sale-section', form).hidden = isRent;
    updateMoveIn();
  }
  function updateMoveIn() {
    const monthly = Number(field('rent.monthlyRent').value);
    const deposit = Number(field('rent.securityDeposit').value || 0);
    $('#move-in', form).textContent = monthly > 0 && deposit >= 0
      ? `Tenants will see a move-in cost of ৳ ${(monthly + deposit).toLocaleString('en-IN')} (first month's rent + deposit).`
      : '';
  }
  form.addEventListener('change', event => { if (event.target.name === 'listingType') syncType(); });
  form.addEventListener('input', event => { if (event.target.name?.startsWith('rent.')) updateMoveIn(); });
  syncType();

  form.addEventListener('submit', event => {
    event.preventDefault();
    const listingType = form.querySelector('input[name="listingType"]:checked')?.value || '';
    const data = {
      title: field('title').value,
      description: field('description').value,
      listingType,
      propertyType: field('propertyType').value,
      areaName: field('areaName').value,
      city: field('city').value,
      address: field('address').value,
      sizeSqft: numberOrBlank(field('sizeSqft').value),
      bedrooms: numberOrBlank(field('bedrooms').value),
      bathrooms: numberOrBlank(field('bathrooms').value),
      furnished: field('furnished').checked,
    };
    if (listingType === 'sale') data.price = numberOrBlank(field('price').value);
    if (listingType === 'rent') {
      data.rent = {
        monthlyRent: numberOrBlank(field('rent.monthlyRent').value),
        securityDeposit: numberOrBlank(field('rent.securityDeposit').value),
        availableFrom: field('rent.availableFrom').value,
        minLeaseMonths: numberOrBlank(field('rent.minLeaseMonths').value),
        tenantPreference: field('rent.tenantPreference').value,
        utilitiesIncluded: field('rent.utilitiesIncluded').checked,
      };
    }
    if (editing) data.listingStatus = field('listingStatus').value;
    else data.requestVerification = field('requestVerification').checked;

    submitting(form, async () => {
      if (editing) {
        await api.put(`/api/properties/${p.id}`, data);
        toast('Changes saved.');
        navigate('/owner/listings');
      } else {
        const result = await api.post('/api/properties', data);
        session.meta.areas = [...new Set([...session.meta.areas, result.property.areaName])].sort();
        if (result.verificationRequestId) {
          toast('Your listing is live as Unverified. Now upload your papers.');
          navigate(`/owner/verification/${result.verificationRequestId}`);
        } else {
          toast('Your listing is live as Unverified.');
          navigate('/owner/listings');
        }
      }
    });
  });
}

// ------------------------------------------------------------------ verification request (PB-10, PB-11, PB-14)

export function steps(status) {
  const order = ['pending', 'in_review', 'result'];
  const position = status === 'pending' ? 0 : status === 'in_review' ? 1 : 2;
  const resultLabel = status === 'issue_found' ? 'Issue found' : 'Document Verified';
  return html`<ol class="steps">
    ${order.map((step, index) => {
      let state = index < position ? 'done' : index === position ? 'current' : '';
      if (step === 'result' && status === 'document_verified') state = 'done';
      if (step === 'result' && status === 'issue_found') state = 'warn';
      const label = { pending: 'Requested', in_review: 'Advocate review', result: resultLabel }[step];
      return html`<li class="${state}">${label}</li>`;
    })}
  </ol>`;
}

export function historyList(entries) {
  if (!entries.length) return html`<p class="muted">No activity yet.</p>`;
  return html`<ul class="timeline">${entries.map(entry => html`<li>
    <strong>${ACTION_LABELS[entry.actionType] || entry.actionType}</strong>${entry.oldValue || entry.newValue ? html`: ${entry.oldValue ? html`${describeValue(entry.oldValue)} &rarr; ` : ''}${describeValue(entry.newValue)}` : ''}
    ${entry.details && entry.actionType !== 'verification_status_changed' ? html`<span class="muted"> · ${entry.details}</span>` : ''}
    <time datetime="${entry.createdAt}">${formatDate(entry.createdAt, true)}${entry.actor ? ` · ${entry.actor.name}` : ''}</time>
  </li>`)}</ul>`;
}

export function documentFile(doc, canOpen) {
  return html`<span class="doc-file">
    ${canOpen ? html`<a href="/api/documents/${doc.id}/file" target="_blank" rel="noopener">${doc.fileName}</a>` : doc.fileName}
    <span class="muted"> · ${doc.fileType.toUpperCase()}, ${doc.fileSizeKb} KB · ${formatDate(doc.uploadedAt)}</span>
  </span>`;
}

export async function renderVerification({ root, params, session, navigate }) {
  const request = await api.get(`/api/verification-requests/${params.id}`);
  const currentByType = Object.fromEntries(request.documents.map(doc => [doc.documentType, doc]));
  const types = session.meta.documentTypes;

  mount(root, html`
    <a class="back-link" href="#/owner/listings">&larr; My listings</a>
    <div class="page-head"><div>
      <h1>Legal verification</h1>
      <p><a href="#/property/${request.property.id}">${request.property.title}</a> · ${request.property.areaName}, ${request.property.city}</p>
    </div>${badge(request.status, REQUEST_STATUS[request.status])}</div>

    <div class="grid-2">
      <div class="stack">
        <div class="panel">
          ${steps(request.status)}
          ${request.status === 'pending' && request.missingDocuments.length ? html`<div class="notice notice-info">
            <strong>Upload your papers to join the advocate queue</strong>
            <p>Still needed: ${request.missingDocuments.map(type => DOCUMENT_LABELS[type]).join(', ')}.</p></div>` : ''}
          ${request.status === 'pending' && !request.missingDocuments.length ? html`<div class="notice notice-info">
            <strong>Your papers are in the queue</strong><p>An advocate will pick up your request soon. You can still replace a paper until the review starts.</p></div>` : ''}
          ${request.status === 'in_review' ? html`<div class="notice notice-info">
            <strong>${request.advocate?.name || 'An advocate'} is checking your papers</strong><p>Papers cannot be changed during the review.</p></div>` : ''}
          ${request.status === 'issue_found' ? html`<div class="notice notice-warn">
            <strong>The advocate found an issue</strong>
            <div class="notes-box">${request.advocateNotes}</div>
            <p>Upload a corrected paper below. Your request will go back to the queue as Pending.</p></div>` : ''}
          ${request.status === 'document_verified' ? html`<div class="notice notice-ok">
            <strong>Your listing is Document Verified</strong>
            <div class="notes-box ok">${request.advocateNotes}</div></div>` : ''}
        </div>

        <div class="panel">
          <div class="panel-title"><h2>Papers</h2><span class="muted small">PDF, JPG or PNG, up to 5 MB each. Only you, the assigned advocate and admins can open them.</span></div>
          <ul class="doc-list">${types.map(type => {
            const doc = currentByType[type.value];
            return html`<li class="doc-row">
              <div class="doc-name"><strong>${type.label}</strong>
                <span class="muted small">${type.required ? 'Required' : 'Optional'}</span></div>
              <div>${doc ? html`${documentFile(doc, true)} ${doc.reviewStatus !== 'not_checked' ? badge(doc.reviewStatus, REVIEW_STATUS[doc.reviewStatus]) : ''}` : html`<span class="muted">Not uploaded</span>`}</div>
              <div class="doc-actions">${request.canUpload ? html`
                <label class="btn btn-${doc ? 'outline' : 'primary'} btn-small file-input">${doc ? 'Replace' : 'Upload'}
                  <input type="file" accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png" data-type="${type.value}" aria-label="Upload ${type.label}">
                </label>` : ''}</div>
            </li>`;
          })}</ul>
          ${request.replacedDocuments.length ? html`<details><summary class="small">Replaced papers (${request.replacedDocuments.length})</summary>
            <ul>${request.replacedDocuments.map(doc => html`<li>${doc.label}: ${documentFile(doc, true)}</li>`)}</ul></details>` : ''}
        </div>
      </div>
      <aside class="panel"><h3>History</h3>${historyList(request.history)}</aside>
    </div>
  `);

  root.addEventListener('change', async event => {
    const input = event.target.closest('input[type="file"]');
    if (!input || !input.files.length) return;
    const file = input.files[0];
    const extension = file.name.split('.').pop().toLowerCase();
    if (!ALLOWED_EXTENSIONS.includes(extension)) {
      toast('Only PDF, JPG and PNG files are accepted.', true);
      input.value = '';
      return;
    }
    if (file.size > MAX_UPLOAD_BYTES) {
      toast('This file is larger than 5 MB. Please upload a smaller scan.', true);
      input.value = '';
      return;
    }
    $$('input[type="file"]', root).forEach(other => { other.disabled = true; });
    try {
      const { requestStatus } = await api.upload(request.id, input.dataset.type, file);
      toast(request.status === 'issue_found' && requestStatus === 'pending'
        ? 'Corrected paper uploaded. Your request is back in the queue.'
        : `${DOCUMENT_LABELS[input.dataset.type]} uploaded.`);
      navigate(`/owner/verification/${request.id}`);
    } catch (error) {
      toast(error.message, true);
      $$('input[type="file"]', root).forEach(other => { other.disabled = false; });
      input.value = '';
    }
  });
}
