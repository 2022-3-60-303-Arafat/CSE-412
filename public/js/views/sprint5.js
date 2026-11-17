// Sprint 5 pages and panels: site visits (PB-34), phone confirmation (PB-35), map search (PB-37), compare (PB-38),
// duplicate flags (PB-39), price guide (PB-40), advocate reviews (PB-41) and rent payments (PB-43).
// bKash / Nagad (PB-36) is in consult.js and the Bangla switch (PB-42) is in ../i18n.js.

import { api } from '../api.js';
import {
  $, badge, confirmClick, formatDate, html, loading, mount, photo, priceLine, shortTaka, submitting, taka, toast, verificationBadge,
} from '../ui.js';

// ------------------------------------------------------------------ browser storage (may be blocked: never required)

export function readStore(key, fallback) {
  try {
    const value = localStorage.getItem(key);
    return value === null ? fallback : JSON.parse(value);
  } catch {
    return fallback;
  }
}

export function writeStore(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Private windows can refuse storage; the feature still works for this visit.
  }
}

// ------------------------------------------------------------------ time slots

const dayText = day => new Date(`${day}T00:00:00`).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' });
const hourText = slot => {
  const hour = Number(slot.slice(11, 13));
  return `${hour % 12 || 12}:00 ${hour < 12 ? 'am' : 'pm'}`;
};
export const slotText = slot => `${dayText(slot.slice(0, 10))}, ${hourText(slot)}`;

function slotsByDay(slots) {
  const days = new Map();
  for (const slot of slots) {
    const day = slot.slice(0, 10);
    if (!days.has(day)) days.set(day, []);
    days.get(day).push(slot);
  }
  return days;
}

// ------------------------------------------------------------------ site visits (PB-34)

export const VISIT_STATUS = { requested: 'Waiting for the owner', confirmed: 'Confirmed', declined: 'Declined', cancelled: 'Cancelled' };

function visitFacts(visit) {
  const other = visit.role === 'tenant' ? visit.owner : visit.tenant;
  return html`<ul class="fact-list">
    <li><small>When</small><strong>${slotText(visit.slotStart)}</strong></li>
    <li><small>${visit.role === 'tenant' ? 'Owner' : 'Visitor'}</small><strong>${other.name}</strong>
      ${other.phone ? html`<span class="sub"><a href="tel:${other.phone}">${other.phone}</a></span>` : ''}</li>
    ${visit.property.address ? html`<li><small>Address</small><strong>${visit.property.address}</strong></li>` : ''}
  </ul>
  ${visit.note ? html`<p class="small"><strong>Note:</strong> ${visit.note}</p>` : ''}
  ${visit.ownerReply ? html`<p class="small"><strong>Owner's reply:</strong> ${visit.ownerReply}</p>` : ''}`;
}

export function visitPanel(property, user) {
  if (property.isOwner || property.listingStatus !== 'active') return '';
  if (!user) {
    return html`<div class="panel"><h3>Visit this home</h3>
      <p class="muted">Pick a time to see the home. The owner confirms it here.</p>
      <a class="btn btn-outline btn-block" href="#/login?next=${encodeURIComponent(`/property/${property.id}`)}">Log in to book a visit</a></div>`;
  }
  if (user.role !== 'buyer_tenant') return '';
  return html`<div class="panel" id="visit-panel"><h3>Visit this home</h3><div id="visit-body">${loading}</div></div>`;
}

export async function setUpVisit(root, property, isCurrent) {
  const panel = $('#visit-panel', root);
  if (!panel) return;
  const body = $('#visit-body', panel);

  async function draw() {
    const { slots, myVisit } = await api.get(`/api/properties/${property.id}/visit-slots`);
    if (!isCurrent()) return;
    if (myVisit) {
      mount(body, html`<div class="notice ${myVisit.status === 'confirmed' ? 'notice-ok' : 'notice-info'}">
          <strong>${VISIT_STATUS[myVisit.status]}</strong>
          <p>${myVisit.status === 'confirmed' ? 'The owner expects you.' : 'The owner will confirm or decline your request.'}</p></div>
        ${visitFacts(myVisit)}
        <div class="form-actions"><button class="btn btn-danger btn-small" type="button" data-cancel-visit="${myVisit.id}">Cancel visit</button>
          <a class="btn btn-outline btn-small" href="#/visits">All my visits</a></div>`);
      return;
    }
    const days = slotsByDay(slots);
    if (!days.size) {
      mount(body, html`<p class="muted">No free times in the next two weeks. Send the owner a message instead.</p>`);
      return;
    }
    mount(body, html`<form id="visit-form" novalidate>
      <p class="muted small">Pick a one-hour time in the next 14 days. The owner confirms it, then you both see each other's phone number.</p>
      <p class="form-error notice notice-error" hidden></p>
      <label class="field"><span>Day</span><select name="day">
        ${[...days.keys()].map(day => html`<option value="${day}">${dayText(day)}</option>`)}</select></label>
      <fieldset class="field" data-error-for="slotStart"><legend>Time</legend><div class="slot-grid" id="visit-times"></div></fieldset>
      <label class="field"><span>Note to the owner <span class="hint">optional</span></span>
        <textarea name="note" maxlength="300" placeholder="For example: I will come with my family."></textarea></label>
      <button class="btn btn-primary btn-block" type="submit">Ask for this visit</button>
    </form>`);
    const form = $('#visit-form', body);
    const drawTimes = () => mount($('#visit-times', form), html`${days.get(form.day.value).map((slot, index) => html`
      <label class="slot"><input type="radio" name="slotStart" value="${slot}" ${index === 0 ? html`checked` : ''}><span>${hourText(slot)}</span></label>`)}`);
    drawTimes();
    form.day.addEventListener('change', drawTimes);
    form.addEventListener('submit', event => {
      event.preventDefault();
      submitting(form, async () => {
        await api.post(`/api/properties/${property.id}/visits`, {
          slotStart: form.querySelector('input[name="slotStart"]:checked')?.value || '', note: form.note.value,
        });
        toast('Visit requested. The owner will confirm it.');
        await draw();
      });
    });
  }

  panel.addEventListener('click', async event => {
    const cancel = event.target.closest('[data-cancel-visit]');
    if (!cancel || !confirmClick(cancel, 'Click again to cancel')) return;
    cancel.disabled = true;
    try {
      await api.post(`/api/visits/${cancel.dataset.cancelVisit}/cancel`);
      toast('Visit cancelled.');
      await draw();
    } catch (error) {
      toast(error.message, true);
      cancel.disabled = false;
    }
  });
  try {
    await draw();
  } catch (error) {
    if (isCurrent()) mount(body, html`<p class="muted small">${error.message}</p>`);
  }
}

function visitCard(visit) {
  const open = visit.status === 'requested' || visit.status === 'confirmed';
  return html`<article class="panel visit-card">
    <div class="panel-title"><h3><a href="#/property/${visit.property.id}">${visit.property.title}</a></h3>${badge(`visit-${visit.status}`, VISIT_STATUS[visit.status])}</div>
    <p class="muted small">${visit.property.areaName}, ${visit.property.city}</p>
    ${visitFacts(visit)}
    ${visit.role === 'owner' && visit.status === 'requested' ? html`
      <form class="visit-answer" data-visit="${visit.id}" novalidate>
        <p class="form-error notice notice-error" hidden></p>
        <label class="field"><span>Reply to ${visit.tenant.name} <span class="hint">needed if you decline</span></span>
          <input name="reply" maxlength="300" placeholder="For example: please call when you reach the gate"></label>
        <div class="form-actions">
          <button class="btn btn-ok btn-small" type="submit" value="confirmed">Confirm visit</button>
          <button class="btn btn-danger btn-small" type="submit" value="declined">Decline</button>
        </div>
      </form>` : ''}
    ${visit.role === 'tenant' && open && !visit.isPast ? html`
      <div class="form-actions"><button class="btn btn-danger btn-small" type="button" data-cancel-visit="${visit.id}">Cancel visit</button></div>` : ''}
  </article>`;
}

export async function renderVisits({ root, session, navigate }) {
  const { visits } = await api.get('/api/visits');
  const isOwner = session.user.role === 'owner';
  const open = visits.filter(v => (v.status === 'requested' || v.status === 'confirmed') && !v.isPast);
  const rest = visits.filter(v => !open.includes(v));
  mount(root, html`
    <div class="page-head"><div><h1>${isOwner ? 'Visit requests' : 'My visits'}</h1>
      <p>${isOwner ? 'Tenants ask to see your homes. Confirm a time or decline with a short reason.'
        : 'Times you asked to see a home. Book a visit from any listing page.'}</p></div></div>
    ${visits.length ? html`
      <section><h2>Upcoming</h2>${open.length ? html`<div class="card-list">${open.map(visitCard)}</div>` : html`<p class="muted">Nothing upcoming.</p>`}</section>
      ${rest.length ? html`<section><h2>Earlier</h2><div class="card-list">${rest.map(visitCard)}</div></section>` : ''}` : html`
      <div class="empty"><h3>No visits yet</h3>
        <p>${isOwner ? 'When a tenant asks to see one of your homes, it shows here.' : 'Open a home you like and pick a time under "Visit this home".'}</p>
        ${isOwner ? '' : html`<a class="btn btn-primary" href="#/">Find homes</a>`}</div>`}`);

  root.addEventListener('submit', event => {
    const form = event.target.closest('.visit-answer');
    if (!form) return;
    event.preventDefault();
    const decision = event.submitter?.value || 'confirmed';
    submitting(form, async () => {
      await api.post(`/api/visits/${form.dataset.visit}/respond`, { decision, reply: form.reply.value });
      toast(decision === 'confirmed' ? 'Visit confirmed. The tenant has been told.' : 'Visit declined. The tenant has been told.');
      navigate('/visits');
    });
  });
  root.addEventListener('click', async event => {
    const cancel = event.target.closest('[data-cancel-visit]');
    if (!cancel || !confirmClick(cancel, 'Click again to cancel')) return;
    cancel.disabled = true;
    try {
      await api.post(`/api/visits/${cancel.dataset.cancelVisit}/cancel`);
      toast('Visit cancelled. The owner has been told.');
      navigate('/visits');
    } catch (error) {
      toast(error.message, true);
      cancel.disabled = false;
    }
  });
}

// ------------------------------------------------------------------ phone confirmation (PB-35)

export function phonePanel(user) {
  return html`<div class="panel phone-panel" id="phone-panel">
    <h2>Confirm your mobile number</h2>
    <p class="muted">Before your first listing goes live we send a 6-digit code to your phone. Buyers then see
      "Phone verified" on your listings, so they know a real person is behind them.</p>
    <form id="phone-send" novalidate>
      <p class="form-error notice notice-error" hidden></p>
      <div class="inline-form">
        <label class="field"><span>Mobile number</span><input name="phone" value="${user.phone}" inputmode="tel" autocomplete="tel"></label>
        <button class="btn btn-primary" type="submit">Send code</button>
      </div>
    </form>
    <form id="phone-verify" novalidate hidden>
      <p class="notice notice-info" id="phone-sent"></p>
      <p class="form-error notice notice-error" hidden></p>
      <div class="inline-form">
        <label class="field"><span>6-digit code</span><input name="code" inputmode="numeric" autocomplete="one-time-code" maxlength="6"></label>
        <button class="btn btn-primary" type="submit">Confirm</button>
      </div>
    </form>
  </div>`;
}

// `onDone(user)` runs after the number is confirmed.
export function setUpPhone(root, session, onDone) {
  const send = $('#phone-send', root);
  const verify = $('#phone-verify', root);
  if (!send) return;
  send.addEventListener('submit', event => {
    event.preventDefault();
    submitting(send, async () => {
      const result = await api.post('/api/phone/send-code', { phone: send.phone.value });
      verify.hidden = false;
      $('#phone-sent', verify).textContent = result.demoCode
        ? `Demo mode (no SMS is sent): your code for ${result.phone} is ${result.demoCode}. It works for ${result.minutes} minutes.`
        : `We sent a code to ${result.phone}. It works for ${result.minutes} minutes.`;
      verify.code.focus();
    });
  });
  verify.addEventListener('submit', event => {
    event.preventDefault();
    submitting(verify, async () => {
      const { user } = await api.post('/api/phone/verify', { code: verify.code.value });
      session.user = user;
      toast('Your mobile number is confirmed.');
      onDone(user);
    });
  });
}

export const phoneBadge = owner => (owner.phoneVerified
  ? html`<span class="badge badge-phone" title="The owner confirmed this mobile number with a one-time code">&#10003; Phone verified</span>` : '');

// ------------------------------------------------------------------ map (PB-37): Google Maps

// Google's embedded map needs no API key. It shows one exact pin at a time.
export const googleMapUrl = (lat, lng, zoom = 15) => `https://www.google.com/maps?q=${lat},${lng}&z=${zoom}&hl=en&output=embed`;
export const directionsUrl = (lat, lng) => `https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}`;
export const openInMapsUrl = (lat, lng) => `https://www.google.com/maps/search/?api=1&query=${lat},${lng}`;

export function googleMap(lat, lng, label, zoom = 15) {
  return html`<iframe class="google-map" src="${googleMapUrl(lat, lng, zoom)}" title="Google map: ${label}" loading="lazy"
    referrerpolicy="no-referrer-when-downgrade" allowfullscreen></iframe>`;
}

// Asks the browser for the visitor's exact position. The browser shows its own "Allow location?" question.
// Resolves to { lat, lng, accuracy } or rejects with a message that says how to fix the problem.
export function askLocation() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error('This browser cannot share your location. Choose a place from the list instead.'));
      return;
    }
    if (!window.isSecureContext) {
      reject(new Error('Location only works on a secure (https) address. Open the site with https:// or on this computer.'));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      position => resolve({
        lat: Number(position.coords.latitude.toFixed(6)),
        lng: Number(position.coords.longitude.toFixed(6)),
        accuracy: Math.round(position.coords.accuracy),
      }),
      error => reject(new Error({
        1: 'Location permission is blocked. Click the lock icon next to the web address, set Location to "Allow", then press "Try again".',
        2: 'Your device location is turned off. Turn on Location (Windows: Settings > Privacy > Location; phone: the GPS / Location switch), then press "Try again".',
        3: 'Finding your location took too long. Check that Location is on and press "Try again".',
      }[error.code] || 'Your location could not be read. Choose a place from the list instead.')),
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 },
    );
  });
}

// The listing page: where the home is, with directions from where the visitor is now.
export function locationPanel(property) {
  if (property.latitude === null || property.latitude === undefined) return '';
  return html`<section class="location-panel">
    <h2>Location</h2>
    ${googleMap(property.latitude, property.longitude, property.title, 16)}
    <div class="form-actions">
      <a class="btn btn-primary btn-small" href="${directionsUrl(property.latitude, property.longitude)}" target="_blank" rel="noopener">Get directions</a>
      <a class="btn btn-outline btn-small" href="${openInMapsUrl(property.latitude, property.longitude)}" target="_blank" rel="noopener">Open in Google Maps</a>
    </div>
    <p class="small muted">${property.areaName}, ${property.city}. Directions start from your current location.</p>
  </section>`;
}

// Turns "23.7808, 90.4167" (as copied from Google Maps) into numbers, or null.
export function parseCoordinates(text) {
  const match = String(text).trim().match(/^(-?\d{1,2}(?:\.\d+)?)\s*[,\s]\s*(-?\d{1,3}(?:\.\d+)?)$/);
  if (!match) return null;
  const lat = Number(match[1]);
  const lng = Number(match[2]);
  return lat >= 20.5 && lat <= 26.7 && lng >= 88 && lng <= 92.7 ? { lat, lng } : null;
}

export function distanceLine(property, near) {
  if (property.distanceKm === undefined) return '';
  return html`<div class="card-distance">${property.distanceKm} km from ${near?.name || 'the chosen place'}</div>`;
}

// ------------------------------------------------------------------ compare (PB-38)

const COMPARE_KEY = 'pfb-compare';
export const MAX_COMPARE = 3;

export const compareList = () => readStore(COMPARE_KEY, []).filter(Number.isInteger).slice(0, MAX_COMPARE);

export function toggleCompare(id) {
  const list = compareList();
  if (list.includes(id)) {
    writeStore(COMPARE_KEY, list.filter(item => item !== id));
    return 'removed';
  }
  if (list.length >= MAX_COMPARE) return 'full';
  writeStore(COMPARE_KEY, [...list, id]);
  return 'added';
}

export function compareButton(property) {
  const listed = compareList().includes(property.id);
  return html`<button class="btn btn-outline btn-small" type="button" data-compare="${property.id}" aria-pressed="${String(listed)}">
    ${listed ? '✓ In compare list' : '+ Compare'}</button>`;
}

// A small bar at the bottom of the screen while the compare list has homes in it.
export function updateCompareBar() {
  let bar = document.getElementById('compare-bar');
  const count = compareList().length;
  if (!count || location.hash.startsWith('#/compare')) {
    bar?.remove();
    return;
  }
  if (!bar) {
    bar = document.createElement('a');
    bar.id = 'compare-bar';
    bar.className = 'compare-bar';
    bar.href = '#/compare';
    document.body.append(bar);
  }
  bar.textContent = `Compare ${count} ${count === 1 ? 'home' : 'homes'} →`;
}

export function setUpCompareButtons(root) {
  root.addEventListener('click', event => {
    const button = event.target.closest('[data-compare]');
    if (!button) return;
    event.preventDefault();
    const result = toggleCompare(Number(button.dataset.compare));
    if (result === 'full') {
      toast(`You can compare up to ${MAX_COMPARE} homes. Remove one first.`, true);
      return;
    }
    button.setAttribute('aria-pressed', String(result === 'added'));
    button.textContent = result === 'added' ? '✓ In compare list' : '+ Compare';
    updateCompareBar();
  });
}

const BEST_ROWS = [
  ['amount', 'Price / rent', item => priceLine(item)],
  ['deposit', 'Security deposit', item => (item.deposit === null ? '–' : taka(item.deposit))],
  ['moveInCost', 'Move-in cost', item => (item.moveInCost === null ? '–' : taka(item.moveInCost))],
  ['sizeSqft', 'Size', item => `${item.sizeSqft.toLocaleString('en-IN')} sqft`],
  ['pricePerSqft', 'Price per sqft', item => (item.pricePerSqft === null ? '–' : taka(item.pricePerSqft))],
  ['bedrooms', 'Bedrooms', item => item.bedrooms],
  ['bathrooms', 'Bathrooms', item => item.bathrooms],
];

export async function renderCompare({ root, navigate }) {
  const ids = compareList();
  if (!ids.length) {
    mount(root, html`<div class="page-head"><div><h1>Compare homes</h1></div></div>
      <div class="empty"><h3>Your compare list is empty</h3>
        <p>Open a home and press "+ Compare". You can put up to ${MAX_COMPARE} homes side by side.</p>
        <a class="btn btn-primary" href="#/">Find homes</a></div>`);
    return;
  }
  const result = await api.get(`/api/compare?ids=${ids.join(',')}`);
  if (result.missing.length) writeStore(COMPARE_KEY, ids.filter(id => !result.missing.includes(id)));
  const items = result.properties;
  const best = (key, item) => (result.best[key] || []).includes(item.id);
  mount(root, html`
    <div class="page-head"><div><h1>Compare homes</h1>
      <p>The best value in each row is marked. ${result.sameKind ? '' : 'Sale prices and monthly rents are not compared with each other.'}</p></div>
      <button class="btn btn-outline" type="button" data-clear-compare>Clear the list</button></div>
    ${result.missing.length ? html`<div class="notice notice-info">${result.missing.length} home in your list is no longer online and was taken out.</div>` : ''}
    <div class="table-wrap"><table class="data compare-table">
      <thead><tr><th scope="col"><span class="sr-only">Detail</span></th>${items.map(item => html`<th scope="col">
        <a href="#/property/${item.id}"><div class="compare-photo">${photo(item, item.title, 640)}</div>${item.title}</a>
        <span class="sub">${item.areaName}, ${item.city}</span>
        <button class="link-button" type="button" data-remove="${item.id}">Remove</button></th>`)}</tr></thead>
      <tbody>
        ${BEST_ROWS.map(([key, label, show]) => html`<tr><th scope="row">${label}</th>
          ${items.map(item => html`<td class="${best(key, item) ? 'best' : ''}">${show(item)}${best(key, item) ? html` <span class="best-mark">Best</span>` : ''}</td>`)}</tr>`)}
        <tr><th scope="row">Type</th>${items.map(item => html`<td>${item.listingType === 'rent' ? 'For rent' : 'For sale'} · ${item.propertyType}</td>`)}</tr>
        <tr><th scope="row">Furnished</th>${items.map(item => html`<td>${item.furnished ? 'Yes' : 'No'}</td>`)}</tr>
        <tr><th scope="row">Legal check</th>${items.map(item => html`<td>${verificationBadge(item.verificationStatus, item.badgeLevel)}</td>`)}</tr>
        <tr><th scope="row">Owner</th>${items.map(item => html`<td>${item.owner.name} ${phoneBadge(item.owner)}</td>`)}</tr>
      </tbody>
    </table></div>`);
  root.addEventListener('click', event => {
    const remove = event.target.closest('[data-remove]');
    if (remove) {
      toggleCompare(Number(remove.dataset.remove));
      navigate('/compare');
    }
    if (event.target.closest('[data-clear-compare]')) {
      writeStore(COMPARE_KEY, []);
      navigate('/compare');
    }
  });
}

// ------------------------------------------------------------------ price guide (PB-40)

export function priceGuideNote(property) {
  const guide = property.priceGuide;
  if (!guide) return '';
  const what = property.listingType === 'rent' ? 'rent' : 'price';
  const homes = `${guide.count} other ${guide.bedrooms}-bedroom ${property.listingType === 'rent' ? 'rentals' : 'homes for sale'}`;
  const where = guide.scope === 'area' ? guide.place : `${guide.place} district`;
  const diff = guide.differencePercent;
  const verdict = Math.abs(diff) <= 5 ? 'close to the average' : `${Math.abs(diff)}% ${diff < 0 ? 'below' : 'above'} the average`;
  return html`<div class="price-guide-note ${diff > 15 ? 'high' : diff < -5 ? 'low' : ''}">
    <strong>This ${what} is ${verdict}</strong>
    <span>of ${homes} in ${where} (${property.listingType === 'rent' ? taka(guide.average) : shortTaka(guide.average)};
      ${property.listingType === 'rent' ? `${taka(guide.lowest)} to ${taka(guide.highest)}` : `${shortTaka(guide.lowest)} to ${shortTaka(guide.highest)}`}).
      <a href="#/price-guide?listingType=${property.listingType}&amp;city=${encodeURIComponent(property.city)}">Price guide</a></span>
  </div>`;
}

function guideTable(rows, listingType, withArea) {
  const money = listingType === 'rent' ? taka : shortTaka;
  return html`<div class="table-wrap"><table class="data">
    <thead><tr>${withArea ? html`<th>Area</th>` : ''}<th>District</th><th class="num">Bedrooms</th><th class="num">Homes</th>
      <th class="num">Average</th><th class="num">Lowest – highest</th></tr></thead>
    <tbody>${rows.map(row => html`<tr>${withArea ? html`<td>${row.area}</td>` : ''}<td>${row.city}</td><td class="num">${row.bedrooms}</td>
      <td class="num">${row.count}</td><td class="num"><strong>${money(row.average)}</strong></td>
      <td class="num">${money(row.lowest)} – ${money(row.highest)}</td></tr>`)}</tbody></table></div>`;
}

export async function renderPriceGuide({ root, query, session, navigate }) {
  const listingType = query.listingType === 'sale' ? 'sale' : 'rent';
  const city = session.meta.cities.includes(query.city) ? query.city : '';
  const guide = await api.get(`/api/price-guide?${new URLSearchParams({ listingType, ...(city ? { city } : {}) })}`);
  mount(root, html`
    <div class="page-head"><div><h1>Area price guide</h1>
      <p>Average ${listingType === 'rent' ? 'monthly rent' : 'sale price'} of the homes listed on PFB right now, by bedroom count.
        A group is shown only when it has at least ${guide.minimumListings} homes.</p></div></div>
    <form class="panel inline-form" id="guide-form">
      <div class="segmented" role="radiogroup" aria-label="Rent or sale">
        <label><input type="radio" name="listingType" value="rent" ${listingType === 'rent' ? html`checked` : ''}><span>Rent</span></label>
        <label><input type="radio" name="listingType" value="sale" ${listingType === 'sale' ? html`checked` : ''}><span>Sale</span></label>
      </div>
      <label class="field"><span>District</span><select name="city"><option value="">All districts</option>
        ${session.meta.cities.map(name => html`<option ${name === city ? html`selected` : ''}>${name}</option>`)}</select></label>
    </form>
    <section class="panel"><div class="panel-title"><h2>By district</h2></div>
      ${guide.districts.length ? guideTable(guide.districts, listingType, false) : html`<p class="muted">Not enough listings yet for a fair average.</p>`}</section>
    <section class="panel"><div class="panel-title"><h2>By area</h2></div>
      ${guide.areas.length ? guideTable(guide.areas, listingType, true) : html`<p class="muted">No area has ${guide.minimumListings} or more homes with the same bedroom count yet, so the district averages above are used.</p>`}</section>
    <p class="small muted">Averages are worked out from active listings, not from completed deals. Use them as a guide when you talk about the price.</p>`);
  $('#guide-form', root).addEventListener('change', event => {
    const form = event.currentTarget;
    navigate(`/price-guide?${new URLSearchParams({ listingType: form.listingType.value, city: form.city.value })}`);
  });
}

// ------------------------------------------------------------------ advocate reviews (PB-41)

export function stars(rating) {
  const full = Math.round(rating);
  return html`<span class="stars" aria-label="${rating} out of 5 stars">${'★'.repeat(full)}${'☆'.repeat(5 - full)}</span>`;
}

export function ratingLine(advocate) {
  if (!advocate.reviewCount) return html`<small class="muted">No reviews yet</small>`;
  return html`<small>${stars(advocate.rating)} ${advocate.rating.toFixed(1)} (${advocate.reviewCount} ${advocate.reviewCount === 1 ? 'review' : 'reviews'})</small>`;
}

export function reviewPanel(item, user) {
  if (item.kind !== 'paid' || item.state !== 'completed') return '';
  if (item.review) {
    return html`<div class="panel"><h2>${user.role === 'advocate' ? 'The client\'s rating' : 'Your rating'}</h2>
      <p>${stars(item.review.rating)} ${item.review.rating} out of 5</p>
      ${item.review.comment ? html`<div class="notes-box">${item.review.comment}</div>` : ''}</div>`;
  }
  if (user.role !== 'buyer_tenant') return '';
  return html`<form class="panel" id="review-form" novalidate>
    <h2>Rate ${item.advocate.name}</h2>
    <p class="muted">Your rating helps other buyers choose an advocate. You can rate each consultation once.</p>
    <p class="form-error notice notice-error" hidden></p>
    <fieldset class="field star-input" data-error-for="rating"><legend>Stars</legend>
      ${[5, 4, 3, 2, 1].map(n => html`<label><input type="radio" name="rating" value="${n}"><span>${'★'.repeat(n)}</span> ${n}</label>`)}
    </fieldset>
    <label class="field"><span>Comment <span class="hint">optional</span></span><textarea name="comment" maxlength="500"></textarea></label>
    <button class="btn btn-primary" type="submit">Send rating</button>
  </form>`;
}

export function setUpReview(root, item, reopen) {
  const form = $('#review-form', root);
  form?.addEventListener('submit', event => {
    event.preventDefault();
    submitting(form, async () => {
      const rating = Number(form.querySelector('input[name="rating"]:checked')?.value || 0);
      await api.post(`/api/consultations/${item.id}/review`, { rating, comment: form.comment.value });
      reopen('Thank you. Your rating was saved.');
    });
  });
}

// ------------------------------------------------------------------ rent payments (PB-43)

const RENT_STATUS = { due: 'Due', marked_paid: 'Paid, waiting for landlord', confirmed: 'Confirmed' };

export async function mountRentPayments(container, agreement, navigate) {
  if (agreement.status !== 'signed') return;
  const data = await api.get(`/api/agreements/${agreement.id}/payments`);
  const { payments, summary, role } = data;
  mount(container, html`<div class="panel">
    <div class="panel-title"><h2>Monthly rent</h2>
      <span class="muted small">${summary.confirmed} of ${summary.total} confirmed${summary.overdue ? html` · <strong class="text-warn">${summary.overdue} overdue</strong>` : ''}</span></div>
    <p class="muted small">${role === 'tenant'
      ? 'You get a reminder 3 days before each due date. After paying, mark the month as paid; the landlord then confirms it.'
      : 'The tenant marks a month as paid; confirm when the money has arrived. You can also confirm cash you received.'}</p>
    <div class="table-wrap"><table class="data">
      <thead><tr><th>Due</th><th class="num">Amount</th><th>Status</th><th>Note</th><th><span class="sr-only">Action</span></th></tr></thead>
      <tbody>${payments.map(p => html`<tr class="${p.overdue ? 'row-warn' : ''}">
        <td>${formatDate(p.dueDate)}</td><td class="num">${taka(p.amount)}</td>
        <td>${badge(`rent-${p.overdue ? 'overdue' : p.status}`, p.overdue ? 'Overdue' : RENT_STATUS[p.status])}</td>
        <td class="small">${p.note || ''}</td>
        <td class="num">${role === 'tenant' && p.status === 'due' ? html`<button class="btn btn-outline btn-small" type="button" data-mark-paid="${p.id}">Mark as paid</button>` : ''}
          ${role === 'landlord' && p.status !== 'confirmed' ? html`<button class="btn btn-ok btn-small" type="button" data-confirm-rent="${p.id}">Confirm received</button>` : ''}</td>
      </tr>`)}</tbody></table></div>
  </div>`);
  container.addEventListener('click', async event => {
    const mark = event.target.closest('[data-mark-paid]');
    const confirm = event.target.closest('[data-confirm-rent]');
    const button = mark || confirm;
    if (!button) return;
    let note = '';
    if (mark) {
      note = window.prompt('How did you pay? For example: bKash, transaction ID 8N7A6B5C (optional)') ?? null;
      if (note === null) return;
    }
    button.disabled = true;
    try {
      if (mark) await api.post(`/api/rent-payments/${mark.dataset.markPaid}/mark-paid`, { note });
      else await api.post(`/api/rent-payments/${confirm.dataset.confirmRent}/confirm`);
      toast(mark ? 'Marked as paid. The landlord will confirm it.' : 'Payment confirmed. The tenant has been told.');
      navigate(`/agreements/${agreement.id}`);
    } catch (error) {
      toast(error.message, true);
      button.disabled = false;
    }
  });
}

// ------------------------------------------------------------------ duplicate flags for the admin (PB-39)

export async function duplicatesTab(container, refresh, query) {
  const status = ['open', 'dismissed', 'removed', 'all'].includes(query.status) ? query.status : 'open';
  const { flags } = await api.get(`/api/admin/duplicate-flags?status=${status}`);
  const listing = item => html`<a href="#/property/${item.id}">${item.title}</a>
    <span class="sub">${item.areaName}, ${item.city} · ${item.owner} · listed ${formatDate(item.createdAt)}${item.listingStatus === 'removed' ? ' · removed' : ''}</span>`;
  mount(container, html`<div class="panel">
    <div class="panel-title"><h2>Possible duplicate listings</h2>
      <nav class="tabs small-tabs">${['open', 'dismissed', 'removed', 'all'].map(s => html`<a href="#/admin?tab=duplicates&amp;status=${s}" class="${s === status ? 'active' : ''}">${s[0].toUpperCase() + s.slice(1)}</a>`)}</nav></div>
    <p class="muted small">Flagged automatically when a listing uses the same photo as another owner's listing, or text that is at least 85% the same.
      An owner reusing their own photos is not flagged. Check both listings before you act.</p>
    ${flags.length ? html`<div class="table-wrap"><table class="data">
      <thead><tr><th>Listing</th><th>Looks like</th><th>Why</th><th>Status</th><th><span class="sr-only">Action</span></th></tr></thead>
      <tbody>${flags.map(flag => html`<tr>
        <td>${listing(flag.listing)}</td><td>${listing(flag.matchedListing)}</td>
        <td>${flag.kind === 'photo' ? 'Same photo' : `Text ${flag.similarity}% the same`}<span class="sub">${formatDate(flag.createdAt, true)}</span></td>
        <td>${badge(`flag-${flag.status}`, flag.status)}${flag.resolvedBy ? html`<span class="sub">${flag.resolvedBy}</span>` : ''}</td>
        <td class="num">${flag.status === 'open' ? html`
          <button class="btn btn-outline btn-small" type="button" data-flag="${flag.id}" data-action="dismiss">Dismiss</button>
          <button class="btn btn-danger btn-small" type="button" data-flag="${flag.id}" data-action="remove">Remove listing</button>` : ''}</td>
      </tr>`)}</tbody></table></div>` : html`<p class="muted">No ${status === 'all' ? '' : status} flags.</p>`}
  </div>`);
  container.addEventListener('click', async event => {
    const button = event.target.closest('[data-flag]');
    if (!button) return;
    if (button.dataset.action === 'remove' && !confirmClick(button, 'Click again to remove')) return;
    button.disabled = true;
    try {
      await api.post(`/api/admin/duplicate-flags/${button.dataset.flag}/resolve`, { action: button.dataset.action });
      toast(button.dataset.action === 'remove' ? 'Listing removed. The owner has been told.' : 'Flag dismissed.');
      refresh();
    } catch (error) {
      toast(error.message, true);
      button.disabled = false;
    }
  });
}

export function priceGuideReport(guide) {
  const block = (kind, rows) => html`<div><h3>${kind === 'rent' ? 'Average rent' : 'Average sale price'}</h3>
    ${rows.length ? guideTable(rows, kind, false) : html`<p class="muted small">Not enough listings yet.</p>`}</div>`;
  return html`<div class="panel"><div class="panel-title"><h3>Area price guide</h3>
    <a class="btn btn-outline btn-small" href="#/price-guide">Open the price guide</a></div>
    ${block('rent', guide.rent)}${block('sale', guide.sale)}</div>`;
}

