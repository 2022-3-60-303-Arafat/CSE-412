// Home page: search with Sale/Rent, price or rent range, bedrooms and Verified-only filters (PB-07, PB-15).

import { api } from '../api.js';
import { $, errorPanel, html, mount, photo, priceLine, showErrors, taka, toast, verificationBadge, loading } from '../ui.js';

// Homes shown before the visitor asks for the rest, so the page does not start as one long list.
const FIRST_PAGE = 12;
const FILTER_KEYS =['purpose', 'area', 'type', 'minPrice', 'maxPrice', 'bedrooms', 'verified', 'sort'];

// `source` records where the visitor found the listing (search, favorites, history) in the browsing history.
export function propertyCard(property, source = 'search') {
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
          <label class="field pill-field"><span>Bedrooms</span>
            <select name="bedrooms">
              ${[['', 'Any'], ['1', '1+'], ['2', '2+'], ['3', '3+'], ['4', '4+']].map(([value, label]) => html`<option value="${value}" ${filters.bedrooms === value ? html`selected` : ''}>${label}</option>`)}
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
              ${[['recommended', 'Verified first'], ['newest', 'Newest'], ['price_asc', 'Price: low to high'], ['price_desc', 'Price: high to low']].map(([value, label]) => html`<option value="${value}" ${filters.sort === value ? html`selected` : ''}>${label}</option>`)}
            </select>
          </label>
          <label class="pill-check"><input type="checkbox" name="verified" value="1" ${filters.verified ? html`checked` : ''}> Verified only</label>
          <button class="link-button" type="button" id="clear-search">Clear</button>
        </div>
        <p class="form-error notice notice-error" hidden></p>
      </div>
    </form>

    <section class="home-section">
      <div class="wrap">
        <h2>Search by city</h2>
        <p class="section-lead">Pick a city to see the homes listed there.</p>
        <div class="chips" id="city-chips">
          ${session.meta.cities.map(city => html`<button type="button" class="chip ${filters.area.toLowerCase() === city.toLowerCase() ? 'active' : ''}" data-city="${city}">${city}</button>`)}
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
    return values;
  }

  function markCity() {
    const area = form.area.value.trim().toLowerCase();
    for (const chip of root.querySelectorAll('[data-city]')) chip.classList.toggle('active', chip.dataset.city.toLowerCase() === area);
  }

  // `byVisitor` is true for a search the visitor started; the page then scrolls to the results.
  async function load(byVisitor = false) {
    markCity();
    const values = currentFilters();
    const params = new URLSearchParams(values).toString();
    history.replaceState(null, '', `#/${params ? `?${params}` : ''}`);
    mount(results, loading);
    try {
      const { properties, total } = await api.get(`/api/properties?${params}`);
      const purposeWord = values.purpose === 'rent' ? 'for rent' : values.purpose === 'sale' ? 'for sale' : '';
      mount(results, html`
        <div class="results-head">
          <h2>${total} ${total === 1 ? 'home' : 'homes'} ${purposeWord}</h2>
          ${values.verified ? html`<span class="badge badge-verified">Showing verified listings only</span>` : ''}
          ${user?.role === 'buyer_tenant' ? html`<button class="btn btn-outline btn-small save-search" type="button" data-save-search>
            Save this search<span class="hint"> · get an alert for new verified homes</span></button>` : ''}
        </div>
        ${total ? html`
          <div class="card-grid">${properties.slice(0, FIRST_PAGE).map(card => propertyCard(card))}</div>
          ${total > FIRST_PAGE ? html`
            <div class="card-grid more-cards" hidden>${properties.slice(FIRST_PAGE).map(card => propertyCard(card))}</div>
            <p class="show-more"><button class="btn btn-outline" type="button" data-show-more>Show all ${total} homes</button></p>` : ''}` : html`
          <div class="empty">
            <h3>No homes match your search yet</h3>
            <p>Try a wider rent or price range, another area, or fewer bedrooms. New listings are added every day.</p>
            <button class="btn btn-primary" type="button" data-clear>Show all homes</button>
          </div>`}
      `);
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
    // Clicking the active city again clears it.
    form.area.value = chip.classList.contains('active') ? '' : chip.dataset.city;
    load(true);
  });
  form.addEventListener('change', event => {
    if (event.target.name === 'purpose') {
      // A sale price range makes no sense as a rent range, so start the range again.
      form.minPrice.value = '';
      form.maxPrice.value = '';
      updateRangeLabels();
    }
    if (['purpose', 'verified', 'sort', 'type', 'bedrooms'].includes(event.target.name)) load();
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
    const more = event.target.closest('[data-show-more]');
    if (more) {
      $('.more-cards', results).hidden = false;
      more.parentElement.remove();
    }
  });
  await load();
}
