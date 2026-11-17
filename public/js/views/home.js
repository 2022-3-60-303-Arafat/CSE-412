// Home page: search with Sale/Rent, area, district, price or rent range, bedrooms, furnished and Verified-only
// filters (PB-07, PB-15), 12 homes per page. Every filter and the page are in the address, so a search can be shared.

import { api } from '../api.js';
import { $, errorPanel, html, mount, photo, priceLine, shortTaka, showErrors, taka, toast, verificationBadge, loading } from '../ui.js';
import { askLocation, distanceLine, googleMap } from './sprint5.js';

const FILTER_KEYS = ['purpose', 'area', 'city', 'type', 'minPrice', 'maxPrice', 'bedrooms', 'furnished', 'verified', 'sort',
  'near', 'radius', 'lat', 'lng'];
// PB-37: places to search near (universities, offices, hospitals). Loaded once.
let landmarks = null;

// Page buttons: the first and last page, and the pages next to the current one, with gaps shown as "…".
function pageList(page, pages) {
  const wanted = [...new Set([1, page - 1, page, page + 1, pages])].filter(n => n >= 1 && n <= pages).sort((a, b) => a - b);
  const list = [];
  wanted.forEach((n, i) => {
    if (i && n - wanted[i - 1] > 1) list.push('gap');
    list.push(n);
  });
  return list;
}

function pager(page, pages) {
  if (pages <= 1) return '';
  return html`<nav class="pager" aria-label="Search result pages">
    <button class="btn btn-outline btn-small" type="button" data-page="${page - 1}" ${page === 1 ? html`disabled` : ''}>&larr; Previous</button>
    ${pageList(page, pages).map(n => (n === 'gap'
    ? html`<span class="pager-gap" aria-hidden="true">…</span>`
    : html`<button class="btn btn-small ${n === page ? 'btn-primary' : 'btn-outline'}" type="button" data-page="${n}"
        aria-label="Page ${n}" ${n === page ? html`aria-current="page"` : ''}>${n}</button>`))}
    <button class="btn btn-outline btn-small" type="button" data-page="${page + 1}" ${page === pages ? html`disabled` : ''}>Next &rarr;</button>
  </nav>`;
}

// `source` records where the visitor found the listing (search, favorites, history) in the browsing history.
// `near` is the place of a near-me search, to say how far the home is.
export function propertyCard(property, source = 'search', near = null) {
  return html`<a class="property-card" href="#/property/${property.id}?from=${source}">
    <div class="card-photo">
      ${photo(property, `${property.title} in ${property.areaName}`, 640)}
      <div class="card-labels">
        <span class="badge badge-${property.listingType}">${property.listingType === 'rent' ? 'For rent' : 'For sale'}</span>
        ${verificationBadge(property.verificationStatus, property.badgeLevel)}
      </div>
    </div>
    <div class="card-body">
      <div class="card-price">${priceLine(property)}</div>
      ${property.rent ? html`<div class="card-sub">Deposit ${taka(property.rent.securityDeposit)} · Move-in ${taka(property.rent.moveInCost)}</div>` : ''}
      <h3 class="card-title">${property.title}</h3>
      <div class="card-sub">${property.areaName}, ${property.city}</div>
      ${distanceLine(property, near)}
      <div class="card-facts">
        <span>${property.propertyType}</span>
        ${property.bedrooms ? html`<span>${property.bedrooms} bed</span>` : ''}
        <span>${property.bathrooms} bath</span>
        <span>${property.sizeSqft.toLocaleString('en-IN')} sqft</span>
      </div>
    </div>
  </a>`;
}

// Small line icons drawn for this site.
const icon = path => html`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${path}</svg>`;
const ICONS = {
  search: icon(html`<circle cx="11" cy="11" r="7"/><path d="m20 20-3.6-3.6"/>`),
  home: icon(html`<path d="M4 11.5 12 4l8 7.5V20h-5v-5H9v5H4z"/>`),
  paper: icon(html`<path d="M7 3h7l4 4v14H7z"/><path d="M14 3v4h4M10 12h5M10 16h5"/>`),
  shield: icon(html`<path d="M12 3 5 6v5.5c0 4.2 2.9 7.6 7 9.5 4.1-1.9 7-5.3 7-9.5V6z"/><path d="m9 12 2.2 2.2L15 10.4"/>`),
  taka: icon(html`<circle cx="12" cy="12" r="9"/><path d="M9.5 7.5c1.2 0 1.8.7 1.8 1.8v5c0 1.4 1 2.2 2.2 2.2 1.3 0 2.2-.9 2.2-2.2 0-.6-.4-1-1-1M8.5 11h5"/>`),
  calculator: icon(html`<rect x="5" y="3" width="14" height="18" rx="2.5"/><path d="M8.5 7.5h7M8.5 12h.01M12 12h.01M15.5 12h.01M8.5 16h.01M12 16h.01M15.5 16h.01"/>`),
};

function rangeLabels(purpose) {
  return purpose === 'rent'
    ? ['Min rent / month (৳)', 'Max rent / month (৳)', 'e.g. 15000', 'e.g. 50000']
    : purpose === 'sale'
      ? ['Min price (৳)', 'Max price (৳)', 'e.g. 5000000', 'e.g. 20000000']
      : ['Min price (৳)', 'Max price (৳)', 'Any', 'Any'];
}

export async function render({ root, query, session }) {
  const filters = Object.fromEntries(FILTER_KEYS.map(key => [key, query[key] || '']));
  filters.purpose ||= 'any';
  filters.radius ||= '5';
  let view = query.view === 'map' ? 'map' : 'list';
  let locationProblem = '';   // why the visitor's location could not be read, shown above the map
  if (!landmarks) {
    try {
      ({ landmarks } = await api.get('/api/landmarks'));
    } catch {
      landmarks = [];
    }
  }
  const landmarkCities = [...new Set(landmarks.map(place => place.city))];
  const firstPage = Math.max(1, Number.parseInt(query.page, 10) || 1);
  const [minLabel, maxLabel, minHint, maxHint] = rangeLabels(filters.purpose);

  const user = session.user;
  // Where "List your property" leads: owners go to the form, visitors sign up first.
  const listHref = user?.role === 'owner' ? '#/owner/listings/new' : !user ? '#/signup' : '';

  mount(root, html`
    <section class="hero">
      <h1>Find a home you can trust</h1>
      <p>Buy or rent across Bangladesh, with legal papers checked by an advocate.</p>
    </section>

    <form class="search" id="search-form" novalidate>
      <div class="segmented" role="radiogroup" aria-label="Listing type">
        ${[['any', 'All'], ['sale', 'Buy'], ['rent', 'Rent']].map(([value, label]) => html`
          <label><input type="radio" name="purpose" value="${value}" ${filters.purpose === value ? html`checked` : ''}><span>${label}</span></label>`)}
      </div>
      <div class="search-card">
        <div class="search-bar">
          ${ICONS.search}
          <label class="sr-only" for="search-area">Area or city</label>
          <input id="search-area" name="area" value="${filters.area}" list="area-list" placeholder="Area or city, e.g. Gulshan, Dhanmondi, Sylhet" autocomplete="off">
          <datalist id="area-list">${session.meta.areas.map(area => html`<option value="${area}">`)}</datalist>
          <button class="btn btn-accent" type="submit">Search</button>
        </div>
        <div class="filter-row">
          <label class="field pill-field"><span>Property type</span>
            <select name="type"><option value="">Any type</option>
              ${session.meta.propertyTypes.map(type => html`<option ${filters.type === type ? html`selected` : ''}>${type}</option>`)}
            </select>
          </label>
          <label class="field pill-field"><span>District</span>
            <select name="city"><option value="">Any district</option>
              ${session.meta.cities.map(city => html`<option ${filters.city === city ? html`selected` : ''}>${city}</option>`)}
            </select>
          </label>
          <label class="field pill-field"><span>Bedrooms</span>
            <select name="bedrooms">
              ${[['', 'Any'], ['1', '1+'], ['2', '2+'], ['3', '3+'], ['4', '4+']].map(([value, label]) => html`<option value="${value}" ${filters.bedrooms === value ? html`selected` : ''}>${label}</option>`)}
            </select>
          </label>
          <label class="field pill-field"><span>Furnished</span>
            <select name="furnished">
              ${[['', 'Any'], ['yes', 'Furnished'], ['no', 'Unfurnished']].map(([value, label]) => html`<option value="${value}" ${filters.furnished === value ? html`selected` : ''}>${label}</option>`)}
            </select>
          </label>
          <label class="field pill-field"><span id="min-label">${minLabel}</span>
            <input name="minPrice" type="number" min="0" step="1000" inputmode="numeric" value="${filters.minPrice}" placeholder="${minHint}">
          </label>
          <label class="field pill-field"><span id="max-label">${maxLabel}</span>
            <input name="maxPrice" type="number" min="0" step="1000" inputmode="numeric" value="${filters.maxPrice}" placeholder="${maxHint}">
          </label>
          <label class="field pill-field"><span>Sort by</span>
            <select name="sort" class="sort-select">
              ${[['recommended', 'Verified first'], ['newest', 'Newest'], ['price_asc', 'Price: low to high'], ['price_desc', 'Price: high to low'], ['distance', 'Nearest first']].map(([value, label]) => html`<option value="${value}" ${filters.sort === value ? html`selected` : ''}>${label}</option>`)}
            </select>
          </label>
          <label class="field pill-field"><span>Near a place</span>
            <select name="near"><option value="">Anywhere</option>
              ${filters.lat ? html`<option value="" selected>My location</option>` : ''}
              ${landmarkCities.map(city => html`<optgroup label="${city}">${landmarks.filter(place => place.city === city).map(place => html`
                <option value="${place.id}" ${filters.near === place.id ? html`selected` : ''}>${place.name}</option>`)}</optgroup>`)}
            </select>
          </label>
          <label class="field pill-field"><span>Within</span>
            <select name="radius">${['1', '3', '5', '10'].map(km => html`<option value="${km}" ${filters.radius === km ? html`selected` : ''}>${km} km</option>`)}</select>
          </label>
          <input type="hidden" name="lat" value="${filters.lat}"><input type="hidden" name="lng" value="${filters.lng}">
          <button class="link-button" type="button" id="my-location">Use my location</button>
          <label class="pill-check"><input type="checkbox" name="verified" value="1" ${filters.verified ? html`checked` : ''}> Verified only</label>
          <button class="link-button" type="button" id="clear-search">Clear</button>
        </div>
        <p class="form-error notice notice-error" hidden></p>
      </div>
    </form>

    <section class="home-section">
      <div class="wrap">
        <h2>Search by district</h2>
        <p class="section-lead">Pick a district to see the homes listed there.</p>
        <div class="chips" id="city-chips">
          ${session.meta.cities.map(city => html`<button type="button" class="chip ${filters.city === city ? 'active' : ''}" data-city="${city}" aria-pressed="${String(filters.city === city)}">${city}</button>`)}
        </div>
      </div>
    </section>

    <section class="home-section">
      <div class="wrap" aria-live="polite" id="results"></div>
    </section>

    <section class="band">
      <div class="wrap band-inner">
        <div>
          <h2>Sell or rent out your property</h2>
          <p>Your listing goes live at once. Add your legal papers and an advocate checks them for the Verified badge.</p>
          ${listHref ? html`<a class="btn btn-accent" href="${listHref}">List your property</a>` : ''}
        </div>
        <ol class="step-cards">
          <li><span class="icon" aria-hidden="true">${ICONS.home}</span>
            <strong>Add your property details</strong><span>Price or rent, deposit, size and location.</span></li>
          <li><span class="icon" aria-hidden="true">${ICONS.paper}</span>
            <strong>Upload your legal papers</strong><span>Land deed, mutation paper and tax receipt, kept private.</span></li>
          <li><span class="icon" aria-hidden="true">${ICONS.shield}</span>
            <strong>Get the Verified badge</strong><span>An advocate reviews the papers and buyers can trust the listing.</span></li>
        </ol>
      </div>
    </section>

    <section class="home-section home-end">
      <div class="wrap">
        <h2>Why Property Finder Bangladesh</h2>
        <p class="section-lead">Built for the way people buy and rent homes here.</p>
        <div class="feature-grid">
          <div class="feature"><span class="icon" aria-hidden="true">${ICONS.shield}</span>
            <h3>Papers checked by an advocate</h3>
            <p>A Verified badge means an advocate has reviewed the land deed, mutation paper and tax receipt.</p>
            <a href="#/?verified=1">See verified homes</a></div>
          <div class="feature red"><span class="icon" aria-hidden="true">${ICONS.taka}</span>
            <h3>The full move-in cost, up front</h3>
            <p>Every rent listing shows the monthly rent, the deposit and the total you pay to move in.</p>
            <a href="#/?purpose=rent">Browse homes for rent</a></div>
          <div class="feature"><span class="icon" aria-hidden="true">${ICONS.calculator}</span>
            <h3>Know what you can afford</h3>
            <p>Check a rent against your income, or estimate the monthly EMI on a home loan.</p>
            <a href="#/calculator">Open the calculators</a></div>
        </div>
      </div>
    </section>
  `);

  const form = $('#search-form', root);
  const results = $('#results', root);

  function currentFilters() {
    const data = new FormData(form);
    const values = {};
    for (const key of FILTER_KEYS) {
      const value = String(data.get(key) ?? '').trim();
      if (value && !(key === 'purpose' && value === 'any') && !(key === 'sort' && value === 'recommended')) values[key] = value;
    }
    // A distance only means something next to a place.
    if (!values.near && !values.lat) delete values.radius;
    if (values.near) {
      delete values.lat;
      delete values.lng;
    }
    return values;
  }

  function markCity() {
    for (const chip of root.querySelectorAll('[data-city]')) {
      const active = chip.dataset.city === form.city.value;
      chip.classList.toggle('active', active);
      chip.setAttribute('aria-pressed', String(active));
    }
  }

  // The address holds the filters and the page (page 1 is left out), so a search can be shared.
  function setAddress(values, page) {
    const params = new URLSearchParams(values);
    if (page > 1) params.set('page', page);
    const text = params.toString();
    const shown = new URLSearchParams(params);
    if (view === 'map') shown.set('view', 'map');
    history.replaceState(null, '', `#/${shown.toString() ? `?${shown}` : ''}`);
    return text;
  }

  // PB-37: Google Maps next to every matching home (no pages). The map shows one pin: the chosen place or
  // your location first, then the home you press in the list.
  async function showMap(values, result) {
    const params = new URLSearchParams(values).toString();
    const { pins, near } = await api.get(`/api/properties/map?${params}`);
    const box = $('#results-map', results);
    if (!box) return;
    const place = near || result.near;
    const centre = place || pins[0];
    const where = place?.name === 'Your location' ? 'You are here' : place?.name;
    mount(box, html`
      <div class="map-layout">
        <div class="map-frame" id="map-frame">${centre ? googleMap(centre.lat, centre.lng, where || pins[0].title, place ? 14 : 16) : ''}</div>
        <ol class="map-list" aria-label="Homes on the map">${pins.map(pin => html`<li>
          <button type="button" class="map-row" data-pin="${pin.id}" data-lat="${pin.lat}" data-lng="${pin.lng}" data-title="${pin.title}">
            <strong>${pin.title}</strong>
            <span>${pin.listingType === 'rent' ? `${taka(pin.amount)} / month` : shortTaka(pin.amount)} · ${pin.areaName}</span>
            ${pin.distanceKm !== null && pin.distanceKm !== undefined ? html`<span class="map-distance">${pin.distanceKm} km away</span>` : ''}
          </button>
          <a class="map-open" href="#/property/${pin.id}?from=search">Open</a></li>`)}</ol>
      </div>
      <p class="small muted">${where ? html`The map shows <strong>${where}</strong>. ` : ''}Press a home in the list to see exactly where it is.
        ${place ? html`<button class="link-button" type="button" data-map-home>Show ${where === 'You are here' ? 'my location' : where} again</button>` : ''}</p>`);
    box.addEventListener('click', event => {
      const row = event.target.closest('[data-pin]');
      if (row) {
        mount($('#map-frame', box), googleMap(row.dataset.lat, row.dataset.lng, row.dataset.title, 17));
        box.querySelectorAll('.map-row.active').forEach(other => other.classList.remove('active'));
        row.classList.add('active');
      }
      if (event.target.closest('[data-map-home]') && place) {
        mount($('#map-frame', box), googleMap(place.lat, place.lng, where, 14));
        box.querySelectorAll('.map-row.active').forEach(other => other.classList.remove('active'));
      }
    });
  }

  // Asks for the visitor's location (the browser asks for permission), then searches around it.
  async function locate() {
    const button = $('#my-location', root);
    button.disabled = true;
    button.textContent = 'Finding you…';
    try {
      const here = await askLocation();
      locationProblem = '';
      form.near.value = '';
      form.lat.value = here.lat;
      form.lng.value = here.lng;
      form.sort.value = 'distance';
      toast(`Location found (within about ${here.accuracy} m).`);
      await load(true);
    } catch (error) {
      locationProblem = error.message;
      if (view === 'map') await load(false, 1);
      else toast(error.message, true);
    } finally {
      button.disabled = false;
      button.textContent = 'Use my location';
    }
  }

  // `byVisitor` is true for a search the visitor started; the page then scrolls to the results.
  // Changing a filter starts again at page 1; the page buttons pass the page they show.
  async function load(byVisitor = false, toPage = 1) {
    markCity();
    const values = currentFilters();
    const params = setAddress(values, toPage);
    mount(results, loading);
    try {
      const result = await api.get(`/api/properties?${params}`);
      const { properties, total, page, pages } = result;
      // A page past the end comes back as the last page; keep the address in step.
      if (page !== toPage) setAddress(values, page);
      const first = (page - 1) * result.pageSize + 1;
      const last = first + properties.length - 1;
      const purposeWord = values.purpose === 'rent' ? 'for rent' : values.purpose === 'sale' ? 'for sale' : '';
      mount(results, html`
        <div class="results-head">
          <h2>${total} ${total === 1 ? 'home' : 'homes'} ${purposeWord}</h2>
          ${pages > 1 && view === 'list' ? html`<span class="muted">Showing ${first}–${last} · page ${page} of ${pages}</span>` : ''}
          ${result.near ? html`<span class="badge badge-near">Within ${result.near.radiusKm} km of ${result.near.name === 'Your location' ? 'you' : result.near.name}</span>` : ''}
          <div class="view-switch" role="group" aria-label="Show results as">
            <button type="button" data-view="list" aria-pressed="${String(view === 'list')}" class="${view === 'list' ? 'active' : ''}">List</button>
            <button type="button" data-view="map" aria-pressed="${String(view === 'map')}" class="${view === 'map' ? 'active' : ''}">Map</button>
          </div>
          ${values.verified ? html`<span class="badge badge-verified">Showing verified listings only</span>` : ''}
          ${user?.role === 'buyer_tenant' ? html`<button class="btn btn-outline btn-small save-search" type="button" data-save-search>
            Save this search<span class="hint"> · get an alert for new verified homes</span></button>` : ''}
        </div>
        ${total ? html`
          ${view === 'map' && locationProblem ? html`<div class="notice notice-warn location-notice"><strong>We could not get your location</strong>
            <p>${locationProblem}</p>
            <button class="btn btn-outline btn-small" type="button" data-retry-location>Try again</button></div>` : ''}
          ${view === 'map' ? html`<div class="results-map" id="results-map">${loading}</div>` : html`
            <div class="card-grid">${properties.map(card => propertyCard(card, 'search', result.near))}</div>
            ${pager(page, pages)}`}` : html`
          <div class="empty">
            <h3>No homes match your search yet</h3>
            <p>Try a wider rent or price range, another area, or fewer bedrooms. New listings are added every day.</p>
            <button class="btn btn-primary" type="button" data-clear>Show all homes</button>
          </div>`}
      `);
      if (view === 'map' && total) showMap(values, result);
      if (byVisitor) results.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (error) {
      if (error.fields && Object.keys(error.fields).length) {
        showErrors(form, error);
        mount(results, '');
      } else {
        mount(results, errorPanel(error));
      }
    }
  }

  function updateRangeLabels() {
    const purpose = new FormData(form).get('purpose');
    const [min, max, minHintText, maxHintText] = rangeLabels(purpose);
    $('#min-label', form).textContent = min;
    $('#max-label', form).textContent = max;
    form.minPrice.placeholder = minHintText;
    form.maxPrice.placeholder = maxHintText;
  }

  function clearSearch() {
    form.reset();
    form.querySelector('input[name="purpose"][value="any"]').checked = true;
    form.area.value = '';
    form.minPrice.value = '';
    form.maxPrice.value = '';
    form.type.value = '';
    form.city.value = '';
    form.furnished.value = '';
    form.near.value = '';
    form.radius.value = '5';
    form.lat.value = '';
    form.lng.value = '';
    form.bedrooms.value = '';
    form.verified.checked = false;
    form.sort.value = 'recommended';
    updateRangeLabels();
    load();
  }

  form.addEventListener('submit', event => { event.preventDefault(); load(true); });
  $('#city-chips', root).addEventListener('click', event => {
    const chip = event.target.closest('[data-city]');
    if (!chip) return;
    // Clicking the active district again clears it.
    form.city.value = chip.classList.contains('active') ? '' : chip.dataset.city;
    load(true);
  });
  form.addEventListener('change', event => {
    if (event.target.name === 'purpose') {
      // A sale price range makes no sense as a rent range, so start the range again.
      form.minPrice.value = '';
      form.maxPrice.value = '';
      updateRangeLabels();
    }
    if (event.target.name === 'near') {
      // A chosen place replaces "my location".
      form.lat.value = '';
      form.lng.value = '';
      if (!form.near.value && form.sort.value === 'distance') form.sort.value = 'recommended';
    }
    if (['purpose', 'verified', 'sort', 'type', 'city', 'bedrooms', 'furnished', 'near', 'radius'].includes(event.target.name)) load();
  });
  $('#clear-search', root).addEventListener('click', clearSearch);
  results.addEventListener('click', async event => {
    if (event.target.closest('[data-clear]')) clearSearch();
    const save = event.target.closest('[data-save-search]');
    if (save) {
      save.disabled = true;
      try {
        await api.post('/api/saved-searches', { filters: currentFilters() });
        save.textContent = 'Search saved ✓';
        toast('Search saved. You will get a notification when a new verified home matches it.');
      } catch (error) {
        toast(error.message, true);
        save.disabled = false;
      }
    }
    const pageButton = event.target.closest('[data-page]');
    if (pageButton && !pageButton.disabled) load(true, Number(pageButton.dataset.page));
    const viewButton = event.target.closest('[data-view]');
    if (viewButton && viewButton.dataset.view !== view) {
      view = viewButton.dataset.view;
      // Opening the map without a place asks for the visitor's location, to show where they are.
      if (view === 'map' && !form.near.value && !form.lat.value) locate();
      else load(false, 1);
    }
    if (event.target.closest('[data-retry-location]')) locate();
  });
  $('#my-location', root).addEventListener('click', locate);
  await load(false, firstPage);
}
