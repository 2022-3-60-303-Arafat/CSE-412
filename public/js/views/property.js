// Listing page: full rent costs (PB-06), verification label (PB-09, PB-15), favorites and inquiries.

import { api } from '../api.js';
import {
  $, LISTING_STATUS, REQUEST_STATUS, TENANT_PREFERENCE, formatDate, html, mount, photo, shortTaka, submitting, taka, toast,
  verificationBadge,
} from '../ui.js';

function pricePanel(property) {
  if (!property.rent) {
    return html`<div class="panel price-panel">
      <p class="muted small">Asking price</p>
      <p class="big">${shortTaka(property.amount)}</p>
      <p class="muted">${taka(property.amount)}</p>
      <a class="btn btn-outline btn-block" href="#/calculator?tab=emi&amp;loan=${Math.round(property.amount * 0.7)}">Estimate the monthly EMI</a>
    </div>`;
  }
  const rent = property.rent;
  return html`<div class="panel price-panel">
    <p class="muted small">Monthly rent</p>
    <p class="big">${taka(rent.monthlyRent)} <small>/ month</small></p>
    <table class="cost-table" aria-label="Move-in cost">
      <tr><td>First month's rent</td><td>${taka(rent.monthlyRent)}</td></tr>
      <tr><td>Security deposit</td><td>${taka(rent.securityDeposit)}</td></tr>
      <tr class="total"><td>Total move-in cost</td><td>${taka(rent.moveInCost)}</td></tr>
    </table>
    <ul class="fact-list">
      <li><small>Available from</small><strong>${formatDate(rent.availableFrom)}</strong></li>
      <li><small>Minimum lease</small><strong>${rent.minLeaseMonths} months</strong></li>
      <li><small>Utilities</small><strong>${rent.utilitiesIncluded ? 'Included' : 'Not included'}</strong></li>
      <li><small>Preferred tenant</small><strong>${TENANT_PREFERENCE[rent.tenantPreference]}</strong></li>
    </ul>
    <a class="btn btn-outline btn-block" href="#/calculator?tab=rent&amp;rent=${rent.monthlyRent}">Can I afford this rent?</a>
  </div>`;
}

function verificationPanel(property) {
  if (property.verificationStatus === 'document_verified') {
    return html`<div class="panel verify-box">
      <span class="verify-icon ok" aria-hidden="true">&#10003;</span>
      <div><h3>Document Verified</h3>
        <p class="muted">An advocate on our panel checked the land deed, mutation paper, tax receipt and ownership history of this property and found them in order.</p></div>
    </div>`;
  }
  return html`<div class="panel verify-box">
    <span class="verify-icon" aria-hidden="true">?</span>
    <div><h3>Unverified</h3>
      <p class="muted">The legal papers of this listing have not been checked by an advocate yet. Ask the owner for the papers before you pay anything.</p></div>
  </div>`;
}

function ownerPanel(property) {
  const request = property.verificationRequest;
  return html`<div class="panel">
    <h3>This is your listing</h3>
    <p class="muted">Status: ${LISTING_STATUS[property.listingStatus]}.
      ${request ? html`Verification: <strong>${REQUEST_STATUS[request.status]}</strong>.` : 'No legal verification requested yet.'}</p>
    <p class="muted">Viewed ${property.views.total} times in total, ${property.views.lastWeek} in the last 7 days.</p>
    <div class="form-actions">
      <a class="btn btn-primary" href="#/owner/listings/${property.id}/edit">Edit listing</a>
      ${request ? html`<a class="btn btn-outline" href="#/owner/verification/${request.id}">Verification details</a>` : ''}
    </div>
  </div>`;
}

function contactPanel(property, user) {
  if (!user) {
    return html`<div class="panel"><h3>Interested?</h3>
      <p class="muted">Log in as a buyer or tenant to save this home and send a message to the owner.</p>
      <a class="btn btn-primary btn-block" href="#/login?next=${encodeURIComponent(`/property/${property.id}`)}">Log in to contact the owner</a></div>`;
  }
  if (user.role !== 'buyer_tenant') return '';
  return html`<div class="panel">
    <div class="panel-title"><h3>Contact the owner</h3>
      <button class="btn btn-outline btn-small" type="button" id="favorite">${property.isFavorite ? '♥ Saved' : '♡ Save home'}</button>
    </div>
    <form id="inquiry-form" novalidate>
      <label class="field"><span>Your phone number</span><input name="phone" value="${user.phone}" inputmode="tel" autocomplete="tel"></label>
      <label class="field"><span>Message to ${property.owner.name}</span>
        <textarea name="message">Hi, I am interested in "${property.title}". Is it still available?</textarea></label>
      <p class="form-error notice notice-error" hidden></p>
      <button class="btn btn-primary btn-block" type="submit">Send inquiry</button>
    </form>
  </div>`;
}

export async function render({ root, params, query, session }) {
  const from = ['search', 'favorites', 'history'].includes(query.from) ? `?from=${query.from}` : '';
  const property = await api.get(`/api/properties/${params.id}${from}`);
  const user = session.user;
  mount(root, html`
    <a class="back-link" href="#/">&larr; Back to search</a>
    <div class="grid-2">
      <div>
        <div class="detail-photo">${photo(property, property.title)}</div>
        <div class="detail-badges">
          <span class="badge badge-${property.listingType}">${property.listingType === 'rent' ? 'For rent' : 'For sale'}</span>
          ${verificationBadge(property.verificationStatus)}
          ${property.listingStatus !== 'active' ? html`<span class="badge badge-sold_rented">${LISTING_STATUS[property.listingStatus]}</span>` : ''}
        </div>
        <h1>${property.title}</h1>
        <p class="muted">${property.address}</p>
        <ul class="fact-list">
          <li><small>Type</small><strong>${property.propertyType}</strong></li>
          <li><small>Bedrooms</small><strong>${property.bedrooms}</strong></li>
          <li><small>Bathrooms</small><strong>${property.bathrooms}</strong></li>
          <li><small>Size</small><strong>${property.sizeSqft.toLocaleString('en-IN')} sqft</strong></li>
          <li><small>Furnished</small><strong>${property.furnished ? 'Yes' : 'No'}</strong></li>
          <li><small>Listed</small><strong>${formatDate(property.createdAt)}</strong></li>
        </ul>
        ${property.description ? html`
          <h2>About this home</h2>
          <p>${property.description}</p>` : ''}
        <p class="muted small">Listed by ${property.owner.name}</p>
      </div>
      <aside class="stack">
        ${pricePanel(property)}
        ${verificationPanel(property)}
        ${property.isOwner ? ownerPanel(property) : contactPanel(property, user)}
      </aside>
    </div>
  `);

  const favorite = $('#favorite', root);
  favorite?.addEventListener('click', async () => {
    favorite.disabled = true;
    try {
      const { saved } = property.isFavorite
        ? await api.del(`/api/favorites/${property.id}`)
        : await api.put(`/api/favorites/${property.id}`);
      property.isFavorite = saved;
      favorite.textContent = saved ? '♥ Saved' : '♡ Save home';
      toast(saved ? 'Saved to your homes.' : 'Removed from saved homes.');
    } catch (error) {
      toast(error.message, true);
    } finally {
      favorite.disabled = false;
    }
  });

  const form = $('#inquiry-form', root);
  form?.addEventListener('submit', event => {
    event.preventDefault();
    submitting(form, async () => {
      await api.post(`/api/properties/${property.id}/inquiries`, { phone: form.phone.value, message: form.message.value });
      form.message.value = '';
      toast('Your message was sent to the owner.');
    });
  });
}
