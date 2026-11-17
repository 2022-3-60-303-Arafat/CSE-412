// Admin panel: advocates (PB-04), all verification requests, high-demand areas (PB-17), audit log (PB-16).

import { api } from '../api.js';
import {
  $, ACTION_LABELS, ADVOCATE_STATUS, AGREEMENT_STATUS, REQUEST_STATUS, ROLE_LABELS, badge, taka, confirmClick, describeValue, formatDate, html, mount, submitting, toast,
} from '../ui.js';
import { describeFilters } from './buyer.js';
import { duplicatesTab, priceGuideReport } from './sprint5.js';

const TABS = [
  ['report', 'Platform report'],
  ['advocates', 'Advocates'],
  ['requests', 'Verification requests'],
  ['areas', 'High-demand areas'],
  ['activity', 'Browsing activity'],
  ['reports', 'Listing reports'],
  ['duplicates', 'Duplicate listings'],
  ['audit', 'Audit log'],
];

// Advocates who applied themselves: send an appointment, then verify them after the in-person meeting.
function applicationsPanel(applications) {
  if (!applications.length) return '';
  return html`
    <div class="panel">
      <div class="panel-title"><h2>Advocate applications</h2><span class="muted small">${applications.length} waiting</span></div>
      <p class="muted small">These advocates signed up themselves. Send an appointment, meet them in person and check their Bar Council
        certificate, then mark them verified. They cannot open the verification queue before that.</p>
      ${applications.map(applicant => html`
        <div class="application">
          <div class="application-head">
            <div><strong>${applicant.fullName}</strong>
              <span class="sub">${applicant.email} · ${applicant.phone} · applied ${formatDate(applicant.createdAt)}</span>
              <span class="sub">Bar Council ID ${applicant.barCouncilId} · ${applicant.specialization}</span></div>
            ${badge(`advocate-${applicant.advocateStatus}`, ADVOCATE_STATUS[applicant.advocateStatus])}
          </div>
          ${applicant.appointment && applicant.advocateStatus === 'appointment_sent' ? html`
            <p class="small"><strong>Appointment:</strong> ${formatDate(applicant.appointment.at, true)} at ${applicant.appointment.place}</p>` : ''}
          ${applicant.adminMessage ? html`<p class="small"><strong>Your message:</strong> ${applicant.adminMessage}</p>` : ''}
          <div class="application-actions">
            <details>
              <summary class="btn btn-outline btn-small">${applicant.advocateStatus === 'appointment_sent' ? 'Change appointment' : 'Send appointment'}</summary>
              <form class="appointment-form" data-applicant="${applicant.id}" novalidate>
                <p class="form-error notice notice-error" hidden></p>
                <div class="form-grid">
                  <label class="field"><span>Date and time <span class="hint">Bangladesh time</span></span>
                    <input name="appointmentAt" type="datetime-local" value="${applicant.appointment?.at || ''}"></label>
                  <label class="field"><span>Place</span>
                    <input name="place" maxlength="160" value="${applicant.appointment?.place || ''}" placeholder="e.g. PFB office, House 12, Road 5, Dhanmondi"></label>
                  <label class="field full"><span>Message to the advocate <span class="hint">optional</span></span>
                    <textarea name="message" maxlength="500" placeholder="e.g. Please bring your Bar Council certificate and national ID."></textarea></label>
                </div>
                <div class="form-actions"><button class="btn btn-primary btn-small" type="submit">Send appointment</button></div>
              </form>
            </details>
            <details>
              <summary class="btn btn-outline btn-small">Reject</summary>
              <form class="reject-form" data-applicant="${applicant.id}" novalidate>
                <p class="form-error notice notice-error" hidden></p>
                <label class="field"><span>Reason <span class="hint">the advocate will see this</span></span>
                  <textarea name="note" maxlength="500"></textarea></label>
                <div class="form-actions"><button class="btn btn-danger btn-small" type="submit">Reject application</button></div>
              </form>
            </details>
            ${applicant.advocateStatus === 'appointment_sent' ? html`
              <button class="btn btn-primary btn-small" type="button" data-verify="${applicant.id}">Mark verified in person</button>` : ''}
            <button class="btn btn-danger btn-small" type="button" data-remove="${applicant.id}">Remove</button>
          </div>
        </div>`)}
    </div>`;
}

async function advocatesTab(container, refresh) {
  const { advocates: everyone } = await api.get('/api/admin/advocates');
  const advocates = everyone.filter(advocate => advocate.advocateStatus === 'verified');
  const applications = everyone.filter(advocate => advocate.advocateStatus !== 'verified');
  mount(container, html`
    ${applicationsPanel(applications)}
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
        </tr>`)}</tbody></table></div>` : html`<div class="empty"><h3>No verified advocates yet</h3><p>Verify an application above or add an advocate below.</p></div>`}
      <p class="small muted">Blocking or removing an advocate signs them out and returns their open reviews to the queue.</p>
    </div>
    <form class="panel" id="advocate-form" novalidate>
      <h2>Add an advocate</h2>
      <p class="muted small">Use this for an advocate you have already checked in person. The account is verified at once.</p>
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
  container.addEventListener('submit', event => {
    const appointmentForm = event.target.closest('.appointment-form');
    const rejectForm = event.target.closest('.reject-form');
    if (!appointmentForm && !rejectForm) return;
    event.preventDefault();
    const form = appointmentForm || rejectForm;
    const id = form.dataset.applicant;
    submitting(form, async () => {
      if (appointmentForm) {
        await api.post(`/api/admin/advocates/${id}/appointment`, Object.fromEntries(new FormData(form)));
        toast('Appointment sent. The advocate will see it when they log in.');
      } else {
        await api.post(`/api/admin/advocates/${id}/verification`, { decision: 'rejected', note: form.note.value });
        toast('Application rejected.');
      }
      refresh();
    });
  });
  container.addEventListener('click', async event => {
    const statusButton = event.target.closest('[data-status]');
    const removeButton = event.target.closest('[data-remove]');
    const verifyButton = event.target.closest('[data-verify]');
    if (verifyButton) {
      if (!confirmClick(verifyButton, 'Confirm: met in person')) return;
      verifyButton.disabled = true;
      try {
        await api.post(`/api/admin/advocates/${verifyButton.dataset.verify}/verification`, { decision: 'verified' });
        toast('Advocate verified. They can now use the verification queue.');
        refresh();
      } catch (error) {
        toast(error.message, true);
        verifyButton.disabled = false;
      }
      return;
    }
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

// PB-29: one page with the numbers the admin watches.
const share = (part, whole) => (whole ? Math.round((part / whole) * 100) : 0);

async function reportTab(container, refresh) {
  const report = await api.get('/api/admin/report');
  const { listings, verification } = report;
  const row = (label, kind) => html`<tr><th scope="row">${label}</th>
    <td class="num">${listings.byType[kind].verified}</td>
    <td class="num">${listings.byType[kind].unverified}${listings.byType[kind].issueFound ? html`<span class="sub">${listings.byType[kind].issueFound} with an issue</span>` : ''}</td>
    <td class="num"><strong>${listings[kind]}</strong></td></tr>`;
  mount(container, html`
    <div class="panel">
      <div class="panel-title"><h2>Platform report</h2><span class="muted small">As of ${formatDate(report.generatedAt, true)}</span></div>
      <ul class="fact-list stat-tiles">
        <li><small>Active listings</small><strong>${listings.active}</strong></li>
        <li><small>Verified</small><strong>${listings.verified}</strong><span class="sub">${share(listings.verified, listings.active)}% of active</span></li>
        <li><small>Unverified</small><strong>${listings.unverified}</strong><span class="sub">${listings.issueFound} with an issue found</span></li>
        <li><small>For sale</small><strong>${listings.sale}</strong></li>
        <li><small>For rent</small><strong>${listings.rent}</strong></li>
        <li><small>Open listing reports</small><strong>${report.listingReports.open}</strong></li>
        <li><small>Possible duplicates</small><strong>${report.duplicateFlags.open}</strong>
          <span class="sub"><a href="#/admin?tab=duplicates">Check them</a></span></li>
        <li><small>Site visits booked</small><strong>${report.siteVisits.requested + report.siteVisits.confirmed}</strong>
          <span class="sub">${report.siteVisits.confirmed} confirmed</span></li>
      </ul>
      <div class="share-bar" role="img" aria-label="${share(listings.verified, listings.active)}% of active listings are verified">
        <span style="width: ${share(listings.verified, listings.active)}%"></span></div>
      <p class="small muted">Share of active listings that are verified.</p>
    </div>
    <div class="grid-2">
      <div class="panel">
        <div class="panel-title"><h3>Verified and unverified, by sale and rent</h3></div>
        <div class="table-wrap"><table class="data">
          <thead><tr><th></th><th class="num">Verified</th><th class="num">Unverified</th><th class="num">Total</th></tr></thead>
          <tbody>${row('For sale', 'sale')}${row('For rent', 'rent')}
            <tr class="total"><th scope="row">All active</th><td class="num">${listings.verified}</td><td class="num">${listings.unverified}</td><td class="num"><strong>${listings.active}</strong></td></tr></tbody>
        </table></div>
        <p class="small muted">Verified listings by badge level: ${listings.badgeLevels.document_verified} Document Verified,
          ${listings.badgeLevels.site_visited} Site Visited, ${listings.badgeLevels.fully_verified} Fully Verified.
          Not counted above: ${listings.soldOrRented} sold or rented, ${listings.removed} removed.</p>
      </div>
      <div class="panel">
        <div class="panel-title"><h3>Verification pipeline</h3></div>
        <table class="data"><tbody>
          <tr><td>Waiting for an advocate</td><td class="num"><strong>${verification.waitingForAdvocate}</strong></td></tr>
          <tr><td>Waiting for the owner's papers</td><td class="num">${verification.waitingForPapers}</td></tr>
          <tr><td>In review</td><td class="num">${verification.inReview}</td></tr>
          <tr><td>Issue found, waiting for the owner</td><td class="num">${verification.issueFound}</td></tr>
          <tr><td>Rent agreements to review</td><td class="num">${report.agreementsToReview}</td></tr>
        </tbody></table>
        ${verification.oldestWaitingSince ? html`<p class="small muted">Oldest request waiting since ${formatDate(verification.oldestWaitingSince)}.</p>` : ''}
      </div>
    </div>
    <div class="panel">
      <div class="panel-title"><h3>Advocates' pending work</h3><a class="btn btn-outline btn-small" href="#/admin?tab=advocates">Manage advocates</a></div>
      <div class="table-wrap"><table class="data">
        <thead><tr><th>Advocate</th><th class="num">Reviews in progress</th><th class="num">Consultation requests</th><th class="num">Sessions booked</th><th class="num">Decided so far</th></tr></thead>
        <tbody>${report.advocates.map(advocate => html`<tr>
          <td><strong>${advocate.name}</strong>${advocate.accountStatus === 'blocked' ? html` ${badge('blocked', 'Blocked')}` : ''}</td>
          <td class="num">${advocate.inReview}</td><td class="num">${advocate.consultationRequests}</td>
          <td class="num">${advocate.sessionsBooked}</td><td class="num">${advocate.decided}</td></tr>`)}</tbody></table></div>
    </div>
    <div class="grid-2">
      <div class="panel"><div class="panel-title"><h3>Consultations</h3></div>
        <table class="data"><tbody>
          <tr><td>Free questions</td><td class="num">${report.consultations.freeQuestions}</td></tr>
          <tr><td>Paid consultations</td><td class="num">${report.consultations.paidBookings}</td></tr>
          <tr><td>Fees collected (demo)</td><td class="num">${taka(report.consultations.feesCollected)}</td></tr>
        </tbody></table></div>
      <div class="panel"><div class="panel-title"><h3>Rent agreements</h3></div>
        <table class="data"><tbody>${Object.entries(report.agreements).map(([status, count]) => html`
          <tr><td>${AGREEMENT_STATUS[status]}</td><td class="num">${count}</td></tr>`)}</tbody></table></div>
    </div>
    ${priceGuideReport(report.priceGuide)}`);
}

// PB-30: reports of fake or wrong listings. The admin dismisses them or removes the listing.
async function listingReportsTab(container, refresh, query) {
  const status = ['open', 'dismissed', 'removed'].includes(query.status) ? query.status : 'open';
  const { reports } = await api.get(`/api/admin/listing-reports?status=${status}`);
  mount(container, html`
    <div class="panel">
      <div class="panel-title"><h2>Listing reports</h2>
        <label class="check">Show
          <select id="report-filter">${[['open', 'Open'], ['dismissed', 'Dismissed'], ['removed', 'Listing removed']].map(([value, label]) => html`<option value="${value}" ${status === value ? html`selected` : ''}>${label}</option>`)}</select></label></div>
      ${reports.length ? reports.map(report => html`
        <div class="application">
          <div class="application-head">
            <div><strong><a href="#/property/${report.property.id}">${report.property.title}</a></strong>
              <span class="sub">${report.property.areaName}, ${report.property.city} · owner ${report.property.ownerName}</span>
              <span class="sub">Reported by ${report.reporter.name} (${ROLE_LABELS[report.reporter.role]}) on ${formatDate(report.createdAt, true)}
                ${report.openForListing > 1 && report.status === 'open' ? ` · ${report.openForListing} open reports on this listing` : ''}</span></div>
            ${badge(report.status === 'open' ? 'pending' : report.status === 'removed' ? 'blocked' : 'not_checked', report.status === 'open' ? 'Open' : report.status === 'removed' ? 'Listing removed' : 'Dismissed')}
          </div>
          <p><strong>${report.reasonLabel}.</strong> ${report.details || ''}</p>
          ${report.adminNote ? html`<p class="small muted">Admin note: ${report.adminNote}${report.resolvedBy ? ` (${report.resolvedBy}, ${formatDate(report.resolvedAt)})` : ''}</p>` : ''}
          ${report.status === 'open' ? html`<form class="resolve-form application-actions" data-report="${report.id}" novalidate>
            <p class="form-error notice notice-error" hidden></p>
            <label class="field"><span>Note <span class="hint">required to remove; the owner sees it</span></span><input name="note" maxlength="500"></label>
            <div class="form-actions">
              <button class="btn btn-danger btn-small" type="submit" value="remove">Remove the listing</button>
              <button class="btn btn-outline btn-small" type="submit" value="dismiss">Dismiss report</button>
            </div>
          </form>` : ''}
        </div>`) : html`<div class="empty"><h3>No ${status === 'open' ? 'open ' : ''}reports</h3><p>Reports that buyers, owners and advocates send about listings appear here.</p></div>`}
    </div>`);
  $('#report-filter', container).addEventListener('change', event => refresh({ status: event.target.value }));
  container.addEventListener('submit', event => {
    const form = event.target.closest('.resolve-form');
    if (!form) return;
    event.preventDefault();
    const action = event.submitter?.value;
    submitting(form, async () => {
      await api.post(`/api/admin/listing-reports/${form.dataset.report}/resolve`, { action, note: form.note.value });
      toast(action === 'remove' ? 'Listing removed. It no longer shows in search.' : 'Report dismissed.');
      refresh();
    });
  });
}

const RENDERERS = {
  report: reportTab, advocates: advocatesTab, requests: requestsTab, areas: areasTab, activity: activityTab,
  reports: listingReportsTab, duplicates: duplicatesTab, audit: auditTab,
};

export async function render({ root, query, navigate }) {
  const tab = RENDERERS[query.tab] ? query.tab : 'report';
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
