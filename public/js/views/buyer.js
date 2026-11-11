// Saved homes for buyers/tenants, and inquiries (sent by buyers, answered by owners).

import { api } from '../api.js';
import { $, badge, confirmClick, formatDate, html, mount, submitting, taka, toast } from '../ui.js';
import { propertyCard } from './home.js';

// Turn saved search filters into words, e.g. "For rent · Uttara · up to ৳ 40,000 · 2+ bedrooms".
export function describeFilters(filters) {
  const parts = [];
  if (filters.purpose) parts.push(filters.purpose === 'rent' ? 'For rent' : 'For sale');
  if (filters.area) parts.push(filters.area);
  if (filters.type) parts.push(filters.type);
  if (filters.minPrice && filters.maxPrice) parts.push(`${taka(Number(filters.minPrice))} – ${taka(Number(filters.maxPrice))}`);
  else if (filters.minPrice) parts.push(`from ${taka(Number(filters.minPrice))}`);
  else if (filters.maxPrice) parts.push(`up to ${taka(Number(filters.maxPrice))}`);
  if (filters.bedrooms) parts.push(`${filters.bedrooms}+ bedrooms`);
  if (filters.verified) parts.push('verified only');
  return parts.join(' · ') || 'All homes';
}

export async function renderHistory({ root, navigate }) {
  const { views, searches } = await api.get('/api/history');
  mount(root, html`
    <div class="page-head"><div><h1>History</h1>
      <p>Homes you opened and searches you made while logged in. Only you and the site admin can see this.</p></div>
      ${views.length || searches.length ? html`<button class="btn btn-danger" type="button" id="clear-history">Clear my history</button>` : ''}
    </div>
    <section class="panel">
      <div class="panel-title"><h2>Recent searches</h2><span class="muted small">${searches.length} saved</span></div>
      ${searches.length ? html`<div class="table-wrap"><table class="data">
        <thead><tr><th>Search</th><th class="num">Results then</th><th>When</th><th class="num"></th></tr></thead>
        <tbody>${searches.map(search => html`<tr>
          <td>${describeFilters(search.filters)}</td>
          <td class="num">${search.resultCount}</td>
          <td>${formatDate(search.searchedAt, true)}</td>
          <td class="num"><a class="btn btn-outline btn-small" href="#/?${new URLSearchParams(search.filters).toString()}">Search again</a></td>
        </tr>`)}</tbody></table></div>` : html`<p class="muted">No searches yet. Use the filters on the <a href="#/">Find homes</a> page.</p>`}
    </section>
    <section class="panel">
      <div class="panel-title"><h2>Recently viewed homes</h2><span class="muted small">${views.length} homes</span></div>
      ${views.length ? html`<div class="card-grid">${views.map(property => html`<div>
        ${propertyCard(property, 'history')}
        <p class="small muted">Last viewed ${formatDate(property.lastViewedAt, true)}${property.timesViewed > 1 ? ` · ${property.timesViewed} times` : ''}</p>
      </div>`)}</div>` : html`<p class="muted">You have not opened any listings yet.</p>`}
    </section>
  `);

  const clear = $('#clear-history', root);
  clear?.addEventListener('click', async () => {
    if (!confirmClick(clear, 'Click again to clear')) return;
    clear.disabled = true;
    try {
      await api.del('/api/history');
      toast('Your history was cleared.');
      navigate('/history');
    } catch (error) {
      toast(error.message, true);
      clear.disabled = false;
    }
  });
}

export async function renderFavorites({ root }) {
  const { properties } = await api.get('/api/favorites');
  mount(root, html`
    <div class="page-head"><div><h1>Saved homes</h1><p>Homes you saved with the ♡ button.</p></div></div>
    ${properties.length ? html`<div class="card-grid">${properties.map(property => propertyCard(property, 'favorites'))}</div>` : html`
      <div class="empty"><h3>No saved homes yet</h3><p>Open a listing and press "Save home" to keep it here.</p>
        <a class="btn btn-primary" href="#/">Find homes</a></div>`}
  `);
}

export async function renderInquiries({ root, session, navigate }) {
  const { inquiries } = await api.get('/api/inquiries');
  const isOwner = session.user.role === 'owner';
  mount(root, html`
    <div class="page-head"><div>
      <h1>${isOwner ? 'Inquiries from buyers and tenants' : 'My inquiries'}</h1>
      <p>${isOwner ? 'Messages about your listings. Reply so they can plan a visit.' : 'Messages you sent to owners, and their replies.'}</p>
    </div></div>
    ${inquiries.length ? html`<div class="panel">${inquiries.map(inquiry => html`
      <article class="inquiry">
        <div class="head">
          <div><a href="#/property/${inquiry.property.id}"><strong>${inquiry.property.title}</strong></a>
            <span class="muted small"> · ${inquiry.property.areaName}</span></div>
          ${badge(inquiry.status === 'replied' ? 'ok' : 'pending', inquiry.status === 'replied' ? 'Replied' : 'New')}
        </div>
        <p>${inquiry.message}</p>
        <p class="small muted">${isOwner ? html`From ${inquiry.senderName} · ${inquiry.senderPhone} · ` : ''}${formatDate(inquiry.createdAt, true)}</p>
        ${inquiry.replyMessage ? html`<div class="reply"><strong>Owner's reply</strong><p>${inquiry.replyMessage}</p></div>` : ''}
        ${isOwner && !inquiry.replyMessage ? html`
          <form class="reply-form" data-id="${inquiry.id}" novalidate>
            <label class="field"><span>Reply</span><textarea name="reply" rows="2"></textarea></label>
            <div class="form-actions"><button class="btn btn-primary btn-small" type="submit">Send reply</button></div>
          </form>` : ''}
      </article>`)}</div>` : html`
      <div class="empty"><h3>No inquiries yet</h3>
        <p>${isOwner ? 'When a buyer or tenant contacts you about a listing, it shows here.' : 'Open a listing and send a message to the owner.'}</p>
        ${isOwner ? '' : html`<a class="btn btn-primary" href="#/">Find homes</a>`}</div>`}
  `);

  root.addEventListener('submit', event => {
    const form = event.target.closest('.reply-form');
    if (!form) return;
    event.preventDefault();
    submitting(form, async () => {
      await api.post(`/api/inquiries/${form.dataset.id}/reply`, { reply: $('textarea', form).value });
      toast('Reply sent.');
      navigate('/inquiries');
    });
  });
}
