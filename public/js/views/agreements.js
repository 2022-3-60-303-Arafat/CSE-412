// Rent agreements (PB-26, PB-27): the landlord fills one in from a rent listing, an advocate reviews it,
// then the landlord and the tenant sign it. Signing is possible only after the advocate approves it.

import { api } from '../api.js';
import { $, AGREEMENT_STATUS, badge, formatDate, html, mount, submitting, taka, toast } from '../ui.js';

const STEPS = ['draft', 'under_review', 'approved', 'signed'];

function steps(status) {
  const current = STEPS.indexOf(status);
  return html`<ul class="steps">${STEPS.map((step, index) => html`
    <li class="${index < current || status === 'signed' ? 'done' : index === current ? 'current' : ''}">${AGREEMENT_STATUS[step]}</li>`)}</ul>`;
}

const statusBadge = status => badge(`agreement-${status}`, AGREEMENT_STATUS[status]);
const pdfLink = (agreement, label = 'Download PDF') => html`<a class="btn btn-outline" href="/api/agreements/${agreement.id}/pdf" target="_blank" rel="noopener">${label}</a>`;

// What the person looking at the agreement should do next.
function nextStep(agreement) {
  const { status, myRole } = agreement;
  const waitingFor = !agreement.landlordSignedAt ? agreement.landlord.name : agreement.tenant.name;
  const texts = {
    draft: myRole === 'landlord' ? 'Check the details, then send it to an advocate for review.' : 'The landlord is still preparing this agreement.',
    under_review: myRole === 'advocate' ? 'Read the agreement, then approve it or ask the landlord for changes.' : 'An advocate is reviewing the agreement. It can be signed after approval.',
    approved: agreement.canSign ? 'Approved by an advocate. Read it, then sign below.' : `Approved. Waiting for ${waitingFor} to sign.`,
    signed: 'Signed by both the landlord and the tenant. Download the signed copy for your records.',
  };
  return texts[status];
}

// ------------------------------------------------------------------ list

export async function renderList({ root, session }) {
  const { agreements } = await api.get('/api/agreements');
  const role = session.user.role;
  const intro = {
    owner: 'Rent agreements for your rent listings. Start one from My listings.',
    buyer_tenant: 'Rent agreements your landlords have prepared for you.',
    advocate: 'Agreements waiting for your review, and ones you have reviewed.',
    admin: 'All rent agreements on the site.',
  }[role];
  mount(root, html`
    <div class="page-head"><div><h1>Rent agreements</h1><p>${intro}</p></div>
      ${role === 'owner' ? html`<a class="btn btn-outline" href="#/owner/listings">My listings</a>` : ''}</div>
    ${agreements.length ? html`<div class="table-wrap"><table class="data">
      <thead><tr><th>Property</th><th>${role === 'buyer_tenant' ? 'Landlord' : 'Tenant'}</th><th>Term</th><th class="num">Rent</th><th>Status</th><th class="num"></th></tr></thead>
      <tbody>${agreements.map(agreement => html`<tr>
        <td><strong>${agreement.property.title}</strong><span class="sub">${agreement.property.areaName}, ${agreement.property.city}</span></td>
        <td>${role === 'buyer_tenant' ? agreement.landlord.name : agreement.tenant.name}
          ${role === 'advocate' || role === 'admin' ? html`<span class="sub">Landlord: ${agreement.landlord.name}</span>` : ''}</td>
        <td>${formatDate(agreement.startDate)}<span class="sub">to ${formatDate(agreement.endDate)} · ${agreement.leaseMonths} months</span></td>
        <td class="num">${taka(agreement.monthlyRent)}</td>
        <td>${statusBadge(agreement.status)}${agreement.canSign ? html`<span class="sub">Your signature is needed</span>` : ''}</td>
        <td class="num"><a class="btn btn-${agreement.canSign || agreement.canReview ? 'primary' : 'outline'} btn-small" href="#/agreements/${agreement.id}">Open</a></td>
      </tr>`)}</tbody></table></div>` : html`<div class="empty"><h3>No rent agreements yet</h3>
      <p>${role === 'owner' ? 'Open My listings and choose "Rent agreement" on a rent listing.' : role === 'advocate' ? 'Agreements sent for review will appear here.' : 'When a landlord prepares an agreement for you, it appears here.'}</p></div>`}
  `);
}

// ------------------------------------------------------------------ form (new or edit)

function agreementForm(property, agreement) {
  const today = new Date().toISOString().slice(0, 10);
  const minLease = property.rent?.minLeaseMonths || 1;
  return html`<form class="panel" id="agreement-form" novalidate>
    <p class="form-error notice notice-error" hidden></p>
    <div class="notice notice-info"><strong>Filled in from your listing</strong>
      <p>Rent ${taka(property.rent.monthlyRent)} a month, deposit ${taka(property.rent.securityDeposit)},
        utilities ${property.rent.utilitiesIncluded ? 'included' : 'paid by the tenant'}. To change these, edit the listing first.</p></div>
    <div class="form-grid">
      <label class="field full"><span>Tenant's email <span class="hint">the tenant needs a Buy or rent account on this site</span></span>
        <input name="tenantEmail" type="email" value="${agreement?.tenant.email || ''}" placeholder="tenant@example.com"></label>
      <label class="field"><span>Move-in date</span><input name="startDate" type="date" min="${today}" value="${agreement?.startDate || property.rent.availableFrom || ''}"></label>
      <label class="field"><span>Lease length (months) <span class="hint">at least ${minLease}</span></span>
        <input name="leaseMonths" type="number" min="${minLease}" max="60" value="${agreement?.leaseMonths || Math.max(minLease, 12)}"></label>
      <label class="field full"><span>Special terms <span class="hint">optional</span></span>
        <textarea name="specialTerms" maxlength="1000" placeholder="e.g. The tenant may keep one small pet.">${agreement?.specialTerms || ''}</textarea></label>
    </div>
    <div class="form-actions">
      <button class="btn btn-primary" type="submit">${agreement ? 'Save changes' : 'Create draft'}</button>
      <a class="btn btn-outline" href="${agreement ? `#/agreements/${agreement.id}` : '#/owner/listings'}">Cancel</a>
    </div>
  </form>`;
}

function formData(form) {
  return {
    tenantEmail: form.tenantEmail.value, startDate: form.startDate.value,
    leaseMonths: form.leaseMonths.value === '' ? '' : Number(form.leaseMonths.value), specialTerms: form.specialTerms.value,
  };
}

export async function renderNew({ root, query, navigate }) {
  const property = await api.get(`/api/properties/${Number(query.property)}`);
  if (!property.rent) {
    mount(root, html`<div class="empty"><h3>Rent agreements are for rent listings</h3><p>This home is listed for sale.</p>
      <a class="btn btn-primary" href="#/owner/listings">Back to my listings</a></div>`);
    return;
  }
  mount(root, html`
    <a class="back-link" href="#/owner/listings">&larr; My listings</a>
    <div class="page-head"><div><h1>New rent agreement</h1><p>For <strong>${property.title}</strong>, ${property.address}</p></div></div>
    ${steps('draft')}
    ${agreementForm(property)}`);
  const form = $('#agreement-form', root);
  form.addEventListener('submit', event => {
    event.preventDefault();
    submitting(form, async () => {
      const agreement = await api.post(`/api/properties/${property.id}/agreements`, formData(form));
      toast('Draft created. Check it, then send it for review.');
      navigate(`/agreements/${agreement.id}`);
    });
  });
}

// ------------------------------------------------------------------ one agreement

function actionPanel(agreement) {
  if (agreement.canEdit) {
    return html`<div class="panel">
      <h2>Send for review</h2>
      ${agreement.reviewNotes ? html`<div class="notice notice-warn"><strong>The advocate asked for changes</strong><p>${agreement.reviewNotes}</p></div>` : ''}
      <p class="muted">An advocate checks the agreement before anyone can sign it. You cannot change it while it is being reviewed.</p>
      <div class="form-actions">
        <button class="btn btn-primary" type="button" data-submit>Send to an advocate</button>
        <button class="btn btn-outline" type="button" data-edit>Edit details</button>
      </div>
      <div id="edit-box"></div>
    </div>`;
  }
  if (agreement.canReview) {
    return html`<form class="panel" id="review-form" novalidate>
      <h2>Your review</h2>
      <p class="muted">Check that the parties, rent, deposit, dates and special terms are fair and lawful.</p>
      <p class="form-error notice notice-error" hidden></p>
      <label class="field"><span>Notes <span class="hint">required when you ask for changes; the landlord sees them</span></span>
        <textarea name="notes" maxlength="2000"></textarea></label>
      <div class="form-actions">
        <button class="btn btn-ok" type="submit" value="approved">&#10003; Approve</button>
        <button class="btn btn-warn" type="submit" value="changes_requested">Ask for changes</button>
      </div>
    </form>`;
  }
  if (agreement.canSign) {
    return html`<form class="panel" id="sign-form" novalidate>
      <h2>Sign the agreement</h2>
      <p class="muted">Read the whole agreement (download the PDF), then type your full name to sign it.</p>
      <p class="form-error notice notice-error" hidden></p>
      <label class="field"><span>Your full name</span><input name="signature" autocomplete="name"></label>
      <label class="check"><input type="checkbox" name="agree"> I have read the agreement and agree to its terms.</label>
      <div class="form-actions"><button class="btn btn-accent" type="submit">Sign agreement</button>${pdfLink(agreement, 'Read the PDF')}</div>
    </form>`;
  }
  return '';
}

export async function renderDetail({ root, params, navigate }) {
  const agreement = await api.get(`/api/agreements/${params.id}`);
  const signedLine = (name, at) => (at ? html`<strong>&#10003; ${name}</strong><span class="sub">signed ${formatDate(at, true)}</span>` : html`${name}<span class="sub">not signed yet</span>`);
  mount(root, html`
    <a class="back-link" href="#/agreements">&larr; Rent agreements</a>
    <div class="page-head"><div><h1>Rent agreement</h1>
      <p><a href="#/property/${agreement.property.id}">${agreement.property.title}</a>, ${agreement.property.address}</p></div>
      <div class="detail-badges">${statusBadge(agreement.status)}</div></div>
    ${steps(agreement.status)}
    <div class="grid-2">
      <div class="stack">
        <div class="panel">
          <div class="notice ${agreement.status === 'signed' ? 'notice-ok' : 'notice-info'}"><strong>${AGREEMENT_STATUS[agreement.status]}</strong><p>${nextStep(agreement)}</p></div>
          <ul class="fact-list">
            <li><small>Landlord</small><strong>${agreement.landlord.name}</strong></li>
            <li><small>Tenant</small><strong>${agreement.tenant.name}</strong></li>
            <li><small>Monthly rent</small><strong>${taka(agreement.monthlyRent)}</strong></li>
            <li><small>Security deposit</small><strong>${taka(agreement.securityDeposit)}</strong></li>
            <li><small>Move-in</small><strong>${formatDate(agreement.startDate)}</strong></li>
            <li><small>Ends</small><strong>${formatDate(agreement.endDate)}</strong></li>
            <li><small>Lease</small><strong>${agreement.leaseMonths} months</strong></li>
            <li><small>Utilities</small><strong>${agreement.utilitiesIncluded ? 'Included' : 'Paid by tenant'}</strong></li>
          </ul>
          ${agreement.specialTerms ? html`<h3>Special terms</h3><div class="notes-box">${agreement.specialTerms}</div>` : ''}
          <div class="form-actions">${pdfLink(agreement)}</div>
        </div>
        ${actionPanel(agreement)}
      </div>
      <aside class="panel">
        <h3>Review and signatures</h3>
        <ul class="fact-list single">
          <li><small>Advocate review</small>${agreement.reviewer ? html`<strong>${agreement.reviewer.name}</strong><span class="sub">${formatDate(agreement.reviewedAt, true)}</span>` : html`<strong>Not reviewed yet</strong>`}</li>
          <li><small>Landlord</small>${signedLine(agreement.landlord.name, agreement.landlordSignedAt)}</li>
          <li><small>Tenant</small>${signedLine(agreement.tenant.name, agreement.tenantSignedAt)}</li>
        </ul>
        ${agreement.reviewNotes && !agreement.canEdit ? html`<h3>Advocate's notes</h3><div class="notes-box">${agreement.reviewNotes}</div>` : ''}
      </aside>
    </div>`);

  const reopen = message => {
    toast(message);
    navigate(`/agreements/${agreement.id}`);
  };
  $('[data-submit]', root)?.addEventListener('click', async event => {
    event.target.disabled = true;
    try {
      await api.post(`/api/agreements/${agreement.id}/submit`);
      reopen('Sent for review. An advocate will check it.');
    } catch (error) {
      toast(error.message, true);
      event.target.disabled = false;
    }
  });
  $('[data-edit]', root)?.addEventListener('click', async () => {
    const property = await api.get(`/api/properties/${agreement.property.id}`);
    const box = $('#edit-box', root);
    mount(box, agreementForm(property, agreement));
    const form = $('#agreement-form', box);
    form.addEventListener('submit', event => {
      event.preventDefault();
      submitting(form, async () => {
        await api.put(`/api/agreements/${agreement.id}`, formData(form));
        reopen('Changes saved.');
      });
    });
  });

  const reviewForm = $('#review-form', root);
  reviewForm?.addEventListener('submit', event => {
    event.preventDefault();
    const decision = event.submitter?.value;
    submitting(reviewForm, async () => {
      await api.post(`/api/agreements/${agreement.id}/review`, { decision, notes: reviewForm.notes.value });
      reopen(decision === 'approved' ? 'Approved. The landlord and the tenant can now sign.' : 'Sent back to the landlord with your notes.');
    });
  });

  const signForm = $('#sign-form', root);
  signForm?.addEventListener('submit', event => {
    event.preventDefault();
    if (!signForm.agree.checked) {
      toast('Tick the box to confirm you have read the agreement.', true);
      return;
    }
    submitting(signForm, async () => {
      const result = await api.post(`/api/agreements/${agreement.id}/sign`, { signature: signForm.signature.value });
      reopen(result.status === 'signed' ? 'Signed by both sides. The agreement is complete.' : 'Signed. Waiting for the other side to sign.');
    });
  });
}
