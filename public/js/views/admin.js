// Admin panel: advocates (PB-04), all verification requests, high-demand areas (PB-17), audit log (PB-16).

import { api } from '../api.js';
import {
  $, ACTION_LABELS, REQUEST_STATUS, ROLE_LABELS, badge, confirmClick, describeValue, formatDate, html, mount, submitting, toast,
} from '../ui.js';
import { describeFilters } from './buyer.js';

const TABS = [
  ['advocates', 'Advocates'],
  ['requests', 'Verification requests'],
  ['areas', 'High-demand areas'],
  ['activity', 'Browsing activity'],
  ['audit', 'Audit log'],
];

async function advocatesTab(container, refresh) {
  const { advocates } = await api.get('/api/admin/advocates');
  mount(container, html`
    <div class="panel">
      <div class="panel-title"><h2>Advocate panel</h2><span class="muted small">${advocates.length} advocates</span></div>
      ${advocates.length ? html`<div class="table-wrap"><table class="data">
        <thead><tr><th>Advocate</th><th>Bar Council ID</th><th>Specialization</th><th>Status</th><th class="num">Work</th><th class="num">Actions</th></tr></thead>
        <tbody>${advocates.map(advocate => html`<tr>
          <td><strong>${advocate.fullName}</strong><span class="sub">${advocate.email} · ${advocate.phone}</span></td>
          <td>${advocate.barCouncilId}</td>
          <td>${advocate.specialization}</td>
          <td>${badge(advocate.accountStatus, advocate.accountStatus === 'active' ? 'Active' : 'Blocked')}</td>
          <td class="num">${advocate.activeCases} in review<span class="sub">${advocate.completedCases} decided</span></td>
          <td><div class="actions">
            <button class="btn btn-outline btn-small" type="button" data-status="${advocate.accountStatus === 'active' ? 'blocked' : 'active'}" data-id="${advocate.id}">
              ${advocate.accountStatus === 'active' ? 'Block' : 'Unblock'}</button>
            <button class="btn btn-danger btn-small" type="button" data-remove="${advocate.id}">Remove</button>
          </div></td>
        </tr>`)}</tbody></table></div>` : html`<div class="empty"><h3>No advocates yet</h3><p>Add the first advocate below.</p></div>`}
      <p class="small muted">Blocking or removing an advocate signs them out and returns their open reviews to the queue.</p>
    </div>
    <form class="panel" id="advocate-form" novalidate>
      <h2>Add an advocate</h2>
      <p class="form-error notice notice-error" hidden></p>
      <div class="form-grid">
        <label class="field"><span>Full name</span><input name="fullName" placeholder="Adv. Full Name"></label>
        <label class="field"><span>Email (login)</span><input name="email" type="email"></label>
        <label class="field"><span>Mobile number</span><input name="phone" inputmode="tel" placeholder="01XXXXXXXXX"></label>
        <label class="field"><span>Bar Council ID</span><input name="barCouncilId" placeholder="e.g. DBC-2021-0042"></label>
        <label class="field"><span>Specialization</span><input name="specialization" placeholder="e.g. Land and property documents"></label>
        <label class="field"><span>Temporary password <span class="hint">share it with the advocate privately</span></span><input name="password" type="text" autocomplete="off"></label>
      </div>
      <div class="form-actions"><button class="btn btn-primary" type="submit">Add advocate</button></div>
    </form>`);

  const form = $('#advocate-form', container);
  form.addEventListener('submit', event => {
    event.preventDefault();
    submitting(form, async () => {
      await api.post('/api/admin/advocates', Object.fromEntries(new FormData(form)));
      toast('Advocate added. They can now log in to the Advocate dashboard.');
      refresh();
    });
  });
  container.addEventListener('click', async event => {
    const statusButton = event.target.closest('[data-status]');
    const removeButton = event.target.closest('[data-remove]');
    try {
      if (statusButton) {
        statusButton.disabled = true;
        await api.post(`/api/admin/advocates/${statusButton.dataset.id}/status`, { status: statusButton.dataset.status });
        toast(statusButton.dataset.status === 'blocked' ? 'Advocate blocked.' : 'Advocate unblocked.');
        refresh();
      } else if (removeButton && confirmClick(removeButton, 'Confirm remove')) {
        removeButton.disabled = true;
        await api.del(`/api/admin/advocates/${removeButton.dataset.remove}`);
        toast('Advocate removed.');
        refresh();
      }
    } catch (error) {
      toast(error.message, true);
      if (statusButton) statusButton.disabled = false;
      if (removeButton) removeButton.disabled = false;
    }
  });
}

async function requestsTab(container, refresh, query) {
  const status = query.status || '';
  const { requests } = await api.get(`/api/admin/verification-requests${status ? `?status=${status}` : ''}`);
  mount(container, html`
    <div class="panel">
      <div class="panel-title"><h2>Verification requests</h2>
        <label class="check">Status
          <select id="status-filter"><option value="">All</option>
            ${Object.entries(REQUEST_STATUS).map(([value, label]) => html`<option value="${value}" ${status === value ? html`selected` : ''}>${label}</option>`)}
          </select></label>
      </div>
      ${requests.length ? html`<div class="table-wrap"><table class="data">
        <thead><tr><th>Property</th><th>Owner</th><th>Advocate</th><th>Submitted</th><th>Status</th><th class="num"></th></tr></thead>
        <tbody>${requests.map(item => html`<tr>
          <td><strong>${item.property.title}</strong><span class="sub">${item.property.areaName}, ${item.property.city}
            ${item.isHighDemand ? html` <span class="badge badge-hot">High demand</span>` : ''}</span></td>
          <td>${item.owner.name}</td>
          <td>${item.advocate?.name || html`<span class="muted">Not assigned</span>`}</td>
          <td>${formatDate(item.submittedAt)}</td>
          <td>${badge(item.status, REQUEST_STATUS[item.status])}</td>
          <td class="num"><a class="btn btn-outline btn-small" href="#/admin/requests/${item.id}">Open</a></td>
        </tr>`)}</tbody></table></div>` : html`<div class="empty"><h3>No requests with this status</h3></div>`}
    </div>`);
  $('#status-filter', container).addEventListener('change', event => refresh({ status: event.target.value }));
}

async function areasTab(container, refresh) {
  const { areas } = await api.get('/api/admin/high-demand-areas');
  mount(container, html`
    <div class="panel">
      <h2>High-demand areas</h2>
      <p class="muted">Verification requests from these areas go to the top of the advocate queue. An area also covers its sub-areas, so "Gulshan" includes "Gulshan 2".</p>
      ${areas.length ? html`<div class="table-wrap"><table class="data">
        <thead><tr><th>Area</th><th class="num">Pending requests</th><th>Added</th><th class="num"></th></tr></thead>
        <tbody>${areas.map(area => html`<tr>
          <td><strong>${area.areaName}</strong></td>
          <td class="num">${area.pendingRequests}</td>
          <td>${formatDate(area.createdAt)}</td>
          <td class="num"><button class="btn btn-danger btn-small" type="button" data-remove-area="${area.id}">Remove</button></td>
        </tr>`)}</tbody></table></div>` : html`<p class="muted">No high-demand areas yet.</p>`}
      <form id="area-form" class="form-actions" novalidate>
        <label class="field"><span>Add an area</span><input name="areaName" placeholder="e.g. Dhanmondi"></label>
        <button class="btn btn-primary" type="submit">Mark as high-demand</button>
      </form>
    </div>`);

  const form = $('#area-form', container);
  form.addEventListener('submit', event => {
    event.preventDefault();
    submitting(form, async () => {
      await api.post('/api/admin/high-demand-areas', { areaName: form.areaName.value });
      toast('Area marked as high-demand.');
      refresh();
    });
  });
  container.addEventListener('click', async event => {
    const button = event.target.closest('[data-remove-area]');
    if (!button || !confirmClick(button, 'Confirm')) return;
    try {
      await api.del(`/api/admin/high-demand-areas/${button.dataset.removeArea}`);
      toast('Area removed.');
      refresh();
    } catch (error) {
      toast(error.message, true);
    }
  });
}

const TARGET_TYPES = [['', 'Everything'], ['verification_request', 'Verification requests'], ['property', 'Listings'], ['user', 'Accounts'], ['high_demand_area', 'High-demand areas']];

function targetLink(entry) {
  if (entry.targetType === 'verification_request') return html`<a href="#/admin/requests/${entry.targetId}">Request #${entry.targetId}</a>`;
  if (entry.targetType === 'property') return html`<a href="#/property/${entry.targetId}">Listing #${entry.targetId}</a>`;
  if (entry.targetType === 'user') return `Account #${entry.targetId}`;
  return `Area #${entry.targetId}`;
}

async function auditTab(container, refresh, query) {
  const target = query.target || '';
  const { entries } = await api.get(`/api/admin/audit-log${target ? `?targetType=${target}` : ''}`);
  mount(container, html`
    <div class="panel">
      <div class="panel-title"><h2>Audit log</h2>
        <label class="check">Show
          <select id="target-filter">${TARGET_TYPES.map(([value, label]) => html`<option value="${value}" ${target === value ? html`selected` : ''}>${label}</option>`)}</select></label>
      </div>
      <p class="muted small">Every change is recorded with who did it and when. Entries cannot be edited or deleted. Showing the latest ${entries.length}.</p>
      <div class="table-wrap"><table class="data">
        <thead><tr><th>When</th><th>Who</th><th>Action</th><th>Target</th><th>Change</th><th>Details</th></tr></thead>
        <tbody>${entries.map(entry => html`<tr>
          <td>${formatDate(entry.createdAt, true)}</td>
          <td>${entry.actor ? html`${entry.actor.name}<span class="sub">${ROLE_LABELS[entry.actor.role]}</span>` : html`<span class="muted">System</span>`}</td>
          <td>${ACTION_LABELS[entry.actionType] || entry.actionType}</td>
          <td>${targetLink(entry)}</td>
          <td>${entry.oldValue ? html`${describeValue(entry.oldValue)} &rarr; ` : ''}${describeValue(entry.newValue)}</td>
          <td class="small">${entry.details || ''}</td>
        </tr>`)}</tbody></table></div>
    </div>`);
  $('#target-filter', container).addEventListener('change', event => refresh({ target: event.target.value }));
}

const SOURCE_LABELS = { search: 'Search results', favorites: 'Saved homes', history: 'History page', direct: 'Direct link' };

async function activityTab(container, refresh, query) {
  const days = query.days || '7';
  const data = await api.get(`/api/admin/activity?days=${encodeURIComponent(days)}`);
  const { totals } = data;
  mount(container, html`
    <div class="panel">
      <div class="panel-title"><h2>Browsing activity</h2>
        <label class="check">Period
          <select id="days-filter">${[['1', 'Last 24 hours'], ['7', 'Last 7 days'], ['30', 'Last 30 days'], ['365', 'Last year']].map(([value, label]) => html`<option value="${value}" ${days === value ? html`selected` : ''}>${label}</option>`)}</select></label>
      </div>
      <ul class="fact-list">
        <li><small>Listing views</small><strong>${totals.views}</strong></li>
        <li><small>Views by guests</small><strong>${totals.guestViews}</strong></li>
        <li><small>Signed-in viewers</small><strong>${totals.signedInViewers}</strong></li>
        <li><small>Searches by users</small><strong>${totals.searches}</strong></li>
      </ul>
      <p class="small muted">Guests are counted without any personal details. Users can clear their own history from their History page.</p>
    </div>
    <div class="grid-2">
      <div class="panel">
        <div class="panel-title"><h3>Most viewed listings</h3></div>
        ${data.topListings.length ? html`<div class="table-wrap"><table class="data">
          <thead><tr><th>Listing</th><th class="num">Views</th></tr></thead>
          <tbody>${data.topListings.map(item => html`<tr>
            <td><a href="#/property/${item.id}">${item.title}</a><span class="sub">${item.areaName}, ${item.city} · for ${item.listingType}</span></td>
            <td class="num">${item.views}</td></tr>`)}</tbody></table></div>` : html`<p class="muted">No views in this period.</p>`}
      </div>
      <div class="panel">
        <div class="panel-title"><h3>Most searched areas</h3></div>
        ${data.topAreas.length ? html`<div class="table-wrap"><table class="data">
          <thead><tr><th>Area</th><th class="num">Searches</th></tr></thead>
          <tbody>${data.topAreas.map(item => html`<tr><td>${item.area}</td><td class="num">${item.searches}</td></tr>`)}</tbody></table></div>`
          : html`<p class="muted">No area searches in this period.</p>`}
      </div>
    </div>
    <div class="panel">
      <div class="panel-title"><h3>Latest listing views</h3></div>
      <div class="table-wrap"><table class="data">
        <thead><tr><th>When</th><th>Who</th><th>Listing</th><th>Found through</th></tr></thead>
        <tbody>${data.recentViews.map(view => html`<tr>
          <td>${formatDate(view.viewedAt, true)}</td>
          <td>${view.viewer ? html`${view.viewer.name}<span class="sub">${ROLE_LABELS[view.viewer.role]}</span>` : html`<span class="muted">Guest</span>`}</td>
          <td><a href="#/property/${view.property.id}">${view.property.title}</a></td>
          <td>${SOURCE_LABELS[view.source]}</td></tr>`)}</tbody></table></div>
    </div>
    <div class="panel">
      <div class="panel-title"><h3>Latest searches</h3></div>
      ${data.recentSearches.length ? html`<div class="table-wrap"><table class="data">
        <thead><tr><th>When</th><th>Who</th><th>Search</th><th class="num">Results</th></tr></thead>
        <tbody>${data.recentSearches.map(search => html`<tr>
          <td>${formatDate(search.searchedAt, true)}</td>
          <td>${search.user.name}<span class="sub">${ROLE_LABELS[search.user.role]}</span></td>
          <td>${describeFilters(search.filters)}</td>
          <td class="num">${search.resultCount}</td></tr>`)}</tbody></table></div>` : html`<p class="muted">No searches yet.</p>`}
    </div>`);
  $('#days-filter', container).addEventListener('change', event => refresh({ days: event.target.value }));
}

const RENDERERS = { advocates: advocatesTab, requests: requestsTab, areas: areasTab, activity: activityTab, audit: auditTab };

export async function render({ root, query, navigate }) {
  const tab = RENDERERS[query.tab] ? query.tab : 'advocates';
  mount(root, html`
    <div class="page-head"><div><h1>Admin panel</h1><p>Manage advocates, follow verification work and review the audit log.</p></div></div>
    <nav class="tabs" aria-label="Admin sections">
      ${TABS.map(([key, label]) => html`<a href="#/admin?tab=${key}" class="${tab === key ? 'active' : ''}">${label}</a>`)}
    </nav>
    <div id="tab-content"></div>`);
  const container = document.createElement('div');
  $('#tab-content', root).replaceWith(container);
  const refresh = (extra = {}) => navigate(`/admin?${new URLSearchParams({ tab, ...query, ...extra, keepScroll: '1' })}`);
  await RENDERERS[tab](container, refresh, query);
}
