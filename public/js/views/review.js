// Advocate dashboard (PB-12, PB-17) and the checklist review page (PB-13).
// Admins open the same request page read-only.

import { api } from '../api.js';
import { $, BADGE_LEVELS, BADGE_MEANING, REQUEST_STATUS, REVIEW_STATUS, badge, formatDate, html, mount, submitting, toast } from '../ui.js';
import { documentFile, historyList, steps } from './owner.js';

const CHECKLIST = [
  ['land_deed', 'Land deed', 'The deed is genuine, registered, and names the current owner.'],
  ['mutation', 'Mutation paper', 'The mutation (namjari) matches the deed and the plot.'],
  ['tax_receipt', 'Tax receipt', 'Land development tax is paid and up to date.'],
  ['ownership_history', 'Ownership history', 'The chain of ownership is clear, with no dispute or gap.'],
];

function queueRow(item) {
  const ready = item.requiredUploaded >= item.requiredTotal;
  return html`<tr>
    <td><strong>${item.property.title}</strong>
      <span class="sub">Owner: ${item.owner.name}${item.resubmissionCount ? ` · resubmitted ${item.resubmissionCount}×` : ''}</span></td>
    <td>${item.property.areaName}, ${item.property.city}
      ${item.isHighDemand ? html`<span class="sub"><span class="badge badge-hot">High demand</span></span>` : ''}</td>
    <td>${formatDate(item.submittedAt)}</td>
    <td>${ready ? badge('ok', `${item.requiredUploaded} / ${item.requiredTotal}`) : badge('not_checked', `${item.requiredUploaded} / ${item.requiredTotal}`)}
      ${ready ? '' : html`<span class="sub">Waiting for papers</span>`}</td>
    <td>${badge(item.status, REQUEST_STATUS[item.status])}</td>
    <td class="num"><a class="btn btn-${item.status === 'in_review' ? 'primary' : 'outline'} btn-small" href="#/advocate/requests/${item.id}">${item.status === 'in_review' ? 'Continue' : 'Open'}</a></td>
  </tr>`;
}

function queueTable(items) {
  return html`<div class="table-wrap"><table class="data">
    <thead><tr><th>Property</th><th>Area</th><th>Submitted</th><th>Papers</th><th>Status</th><th class="num"></th></tr></thead>
    <tbody>${items.map(queueRow)}</tbody></table></div>`;
}

export async function renderQueue({ root, session }) {
  const { queue, recentDecisions } = await api.get('/api/advocate/queue');
  const mine = queue.filter(item => item.status === 'in_review');
  const waiting = queue.filter(item => item.status === 'pending');
  mount(root, html`
    <div class="page-head"><div><h1>Verification queue</h1>
      <p>Welcome, ${session.user.fullName}. Requests from high-demand areas are shown first, then the oldest.</p></div></div>
    <section class="panel">
      <div class="panel-title"><h2>In review by you</h2><span class="muted small">${mine.length} open</span></div>
      ${mine.length ? queueTable(mine) : html`<p class="muted">You have no open reviews. Pick one from the queue below.</p>`}
    </section>
    <section class="panel">
      <div class="panel-title"><h2>Pending requests</h2><span class="muted small">${waiting.length} waiting</span></div>
      ${waiting.length ? queueTable(waiting) : html`<div class="empty"><h3>The queue is empty</h3><p>New verification requests from owners will appear here.</p></div>`}
    </section>
    <section class="panel">
      <div class="panel-title"><h2>Your recent decisions</h2></div>
      ${recentDecisions.length ? html`<div class="table-wrap"><table class="data">
        <thead><tr><th>Property</th><th>Decided</th><th>Result</th><th class="num"></th></tr></thead>
        <tbody>${recentDecisions.map(item => html`<tr>
          <td><strong>${item.property.title}</strong><span class="sub">${item.property.areaName}</span></td>
          <td>${formatDate(item.completedAt)}</td>
          <td>${badge(item.status, REQUEST_STATUS[item.status])}</td>
          <td class="num"><a class="btn btn-outline btn-small" href="#/advocate/requests/${item.id}">View</a></td>
        </tr>`)}</tbody></table></div>` : html`<p class="muted">No decisions yet.</p>`}
    </section>
  `);
}

function decisionForm(request) {
  const checklist = request.checklist || {};
  return html`<form id="decision-form" class="panel" novalidate>
    <h2>Checklist</h2>
    <p class="muted small">Open each paper, then mark every check. All four must be OK to verify; mark at least one Problem to report an issue.</p>
    <p class="form-error notice notice-error" hidden></p>
    <table class="checklist">
      <thead><tr><th>Check</th><th class="choice">OK</th><th class="choice">Problem</th></tr></thead>
      <tbody>${CHECKLIST.map(([key, label, help]) => html`<tr>
        <td data-error-for="checklist.${key}"><strong>${label}</strong><span class="muted small"> ${help}</span></td>
        <td class="choice"><input type="radio" name="checklist.${key}" value="ok" aria-label="${label} OK" ${checklist[key] === 'ok' ? html`checked` : ''}></td>
        <td class="choice"><input type="radio" name="checklist.${key}" value="problem" aria-label="${label} problem" ${checklist[key] === 'problem' ? html`checked` : ''}></td>
      </tr>`)}</tbody>
    </table>
    <label class="field"><span>Notes for the owner <span class="hint">required: explain what you checked or what must be fixed</span></span>
      <textarea name="notes" maxlength="2000"></textarea></label>
    <div class="form-actions" data-error-for="decision">
      <button class="btn btn-ok" type="submit" value="document_verified">&#10003; Mark Document Verified</button>
      <button class="btn btn-warn" type="submit" value="issue_found">! Mark Issue Found</button>
    </div>
  </form>`;
}

function resultPanel(request) {
  if (!['document_verified', 'issue_found'].includes(request.status)) return '';
  const ok = request.status === 'document_verified';
  return html`<div class="panel">
    <h2>Decision: ${REQUEST_STATUS[request.status]}</h2>
    <p class="muted small">By ${request.advocate?.name} on ${formatDate(request.completedAt, true)}</p>
    <div class="notes-box ${ok ? 'ok' : ''}">${request.advocateNotes}</div>
    ${request.checklist ? html`<table class="checklist"><tbody>${CHECKLIST.map(([key, label]) => html`<tr>
      <td>${label}</td><td>${badge(request.checklist[key], REVIEW_STATUS[request.checklist[key]])}</td></tr>`)}</tbody></table>` : ''}
  </div>
  ${levelPanel(request)}`;
}

// PB-19: after verifying, the advocate records how much checking was done. Everyone else just sees the level.
function levelPanel(request) {
  if (!request.badgeLevel) return '';
  if (!request.canSetBadgeLevel) {
    return html`<div class="panel"><h2>Badge level: ${BADGE_LEVELS[request.badgeLevel]}</h2>
      <p class="muted">${BADGE_MEANING[request.badgeLevel]}</p>
      <a class="btn btn-outline" href="/api/properties/${request.property.id}/legal-report" target="_blank" rel="noopener">Open the legal report (PDF)</a></div>`;
  }
  return html`<form class="panel" id="level-form" novalidate>
    <h2>Badge level</h2>
    <p class="muted small">Raise the level when you have done more than check the papers. The listing and the legal report show it.</p>
    <p class="form-error notice notice-error" hidden></p>
    <div class="level-choice">
      ${Object.entries(BADGE_LEVELS).map(([value, label]) => html`
        <label><input type="radio" name="level" value="${value}" ${request.badgeLevel === value ? html`checked` : ''}>
          <span><strong>${label}</strong><small>${BADGE_MEANING[value]}</small></span></label>`)}
    </div>
    <div class="form-actions">
      <button class="btn btn-primary" type="submit">Save badge level</button>
      <a class="btn btn-outline" href="/api/properties/${request.property.id}/legal-report" target="_blank" rel="noopener">Open the legal report (PDF)</a>
    </div>
  </form>`;
}

export async function renderRequest({ root, params, session, navigate }) {
  const request = await api.get(`/api/verification-requests/${params.id}`);
  const user = session.user;
  const isAdmin = user.role === 'admin';
  const isMine = request.advocate?.id === user.id;
  const back = isAdmin ? ['#/admin?tab=requests', 'Admin panel'] : ['#/advocate', 'Verification queue'];

  mount(root, html`
    <a class="back-link" href="${back[0]}">&larr; ${back[1]}</a>
    <div class="page-head"><div>
      <h1>${request.property.title}</h1>
      <p>${request.property.address} · ${request.property.propertyType}, for ${request.property.listingType}
        · <a href="#/property/${request.property.id}">View listing</a></p>
    </div>
    <div class="detail-badges">${request.isHighDemand ? html`<span class="badge badge-hot">High demand</span>` : ''}${badge(request.status, REQUEST_STATUS[request.status])}</div></div>

    <div class="grid-2">
      <div class="stack">
        <div class="panel">
          ${steps(request.status)}
          <ul class="fact-list">
            <li><small>Owner</small><strong>${request.owner.name}</strong></li>
            <li><small>Submitted</small><strong>${formatDate(request.submittedAt)}</strong></li>
            <li><small>Advocate</small><strong>${request.advocate?.name || 'Not assigned'}</strong></li>
            <li><small>Resubmissions</small><strong>${request.resubmissionCount}</strong></li>
          </ul>
        </div>

        <div class="panel">
          <div class="panel-title"><h2>Papers</h2>
            ${request.canOpenFiles ? '' : html`<span class="muted small">You can open the files after you start the review.</span>`}</div>
          ${request.documents.length ? html`<ul class="doc-list">${request.documents.map(doc => html`<li class="doc-row">
            <div class="doc-name"><strong>${doc.label}</strong></div>
            <div>${documentFile(doc, request.canOpenFiles)}</div>
            <div class="doc-actions">${badge(doc.reviewStatus, REVIEW_STATUS[doc.reviewStatus])}</div>
          </li>`)}</ul>` : html`<p class="muted">No papers uploaded yet.</p>`}
          ${request.missingDocuments.length ? html`<div class="notice notice-info"><strong>Still missing</strong>
            <p>${request.missingDocuments.map(type => ({ land_deed: 'Land deed', mutation: 'Mutation paper', tax_receipt: 'Tax receipt' }[type])).join(', ')}</p></div>` : ''}
        </div>

        ${!isAdmin && request.status === 'pending' ? html`<div class="panel">
          <h2>Start the review</h2>
          <p class="muted">The request will be assigned to you and the owner can no longer change the papers until you decide.</p>
          <button class="btn btn-primary" type="button" id="start-review" ${request.missingDocuments.length ? html`disabled` : ''}>Start review</button>
          ${request.missingDocuments.length ? html`<p class="small muted">Available once the owner uploads all required papers.</p>` : ''}
        </div>` : ''}
        ${!isAdmin && isMine && request.status === 'in_review' ? decisionForm(request) : ''}
        ${resultPanel(request)}
      </div>
      <aside class="panel"><h3>Audit trail</h3>${historyList(request.history)}</aside>
    </div>
  `);

  const startButton = $('#start-review', root);
  startButton?.addEventListener('click', async () => {
    startButton.disabled = true;
    try {
      await api.post(`/api/verification-requests/${request.id}/start-review`);
      toast('Review started. The papers are now open to you.');
      navigate(`/advocate/requests/${request.id}`);
    } catch (error) {
      toast(error.message, true);
      startButton.disabled = false;
    }
  });

  const levelForm = $('#level-form', root);
  levelForm?.addEventListener('submit', event => {
    event.preventDefault();
    submitting(levelForm, async () => {
      const result = await api.post(`/api/verification-requests/${request.id}/badge-level`, { level: levelForm.level.value });
      toast(`Badge level saved: ${BADGE_LEVELS[result.badgeLevel]}.`);
      navigate(`/advocate/requests/${request.id}`);
    });
  });

  const form = $('#decision-form', root);
  form?.addEventListener('submit', event => {
    event.preventDefault();
    const decision = event.submitter?.value;
    const checklist = Object.fromEntries(CHECKLIST.map(([key]) => [key, form.querySelector(`input[name="checklist.${key}"]:checked`)?.value || null]));
    submitting(form, async () => {
      const result = await api.post(`/api/verification-requests/${request.id}/decision`, {
        decision, checklist, notes: form.notes.value,
      });
      toast(result.status === 'document_verified' ? 'Marked Document Verified. The badge is now on the listing.' : 'Issue reported. The owner can now see your notes.');
      navigate(`/advocate/requests/${request.id}`);
    });
  });
}
