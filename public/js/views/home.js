// Home page: search with Sale/Rent, price or rent range, bedrooms and Verified-only filters (PB-07, PB-15).

import { api } from '../api.js';
import { $, errorPanel, html, mount, photo, priceLine, showErrors, taka, verificationBadge, loading } from '../ui.js';

const FILTER_KEYS = ['purpose', 'area', 'type', 'minPrice', 'maxPrice', 'bedrooms', 'verified', 'sort'];

// `source` records where the visitor found the listing (search, favorites, history) in the browsing history.
export function propertyCard(property, source = 'search') {
  return html`<a class="property-card" href="#/property/${property.id}?from=${source}">
    <div class="card-photo">
      ${photo(property, `${property.title} in ${property.areaName}`)}
      <div class="card-labels">
        <span class="badge badge-${property.listingType}">${property.listingType === 'rent' ? 'For rent' : 'For sale'}</span>
        ${verificationBadge(property.verificationStatus)}
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

function rangeLabels(purpose) {
  return purpose === 'rent'
    ? ['Min rent / month (৳)', 'Max rent / month (৳)', 'e.g. 15000', 'e.g. 50000']
    : purpose === 'sale'
      ? ['Min price (৳)', 'Max price (৳)', 'e.g. 5000000', 'e.g. 20000000']
      : ['Min price or rent (৳)', 'Max price or rent (৳)', 'Any', 'Any'];
}

export async function render({ root, query, session }) {
  const filters = Object.fromEntries(FILTER_KEYS.map(key => [key, query[key] || '']));
  filters.purpose ||= 'any';
  const [minLabel, maxLabel, minHint, maxHint] = rangeLabels(filters.purpose);

  mount(root, html`
    <section class="hero">
      <div>
        <h1>Find a home you can <em>trust.</em></h1>
        <p>Buy or rent across Bangladesh. Look for the Verified badge: an advocate has checked the land deed, mutation paper and tax receipt.</p>
        <ul class="hero-points"><li>Sale and rent listings</li><li>Full move-in cost for rentals</li><li>Advocate-verified papers</li></ul>
      </div>
      <div class="hero-art"><img src="https://images.unsplash.com/photo-1600210492486-724fe5c67fb0?auto=format&fit=crop&w=1100&q=80" alt="Bright modern living room"></div>
    </section>

    <form class="search-panel" id="search-form" novalidate>
      <div class="segmented" role="radiogroup" aria-label="Listing type">
        ${[['any', 'All'], ['sale', 'Buy'], ['rent', 'Rent']].map(([value, label]) => html`
          <label><input type="radio" name="purpose" value="${value}" ${filters.purpose === value ? html`checked` : ''}><span>${label}</span></label>`)}
      </div>
      <div class="search-grid">
        <label class="field"><span>Area or city</span>
          <input name="area" value="${filters.area}" list="area-list" placeholder="e.g. Gulshan, Dhanmondi, Sylhet" autocomplete="off">
          <datalist id="area-list">${session.meta.areas.map(area => html`<option value="${area}">`)}</datalist>
        </label>
        <label class="field"><span>Property type</span>
          <select name="type"><option value="">Any type</option>
            ${session.meta.propertyTypes.map(type => html`<option ${filters.type === type ? html`selected` : ''}>${type}</option>`)}
          </select>
        </label>
        <label class="field"><span id="min-label">${minLabel}</span>
          <input name="minPrice" type="number" min="0" step="1000" inputmode="numeric" value="${filters.minPrice}" placeholder="${minHint}">
        </label>
        <label class="field"><span id="max-label">${maxLabel}</span>
          <input name="maxPrice" type="number" min="0" step="1000" inputmode="numeric" value="${filters.maxPrice}" placeholder="${maxHint}">
        </label>
        <label class="field"><span>Bedrooms</span>
          <select name="bedrooms">
            ${[['', 'Any'], ['1', '1+'], ['2', '2+'], ['3', '3+'], ['4', '4+']].map(([value, label]) => html`<option value="${value}" ${filters.bedrooms === value ? html`selected` : ''}>${label}</option>`)}
          </select>
        </label>
      </div>
      <div class="search-foot">
        <div class="checks">
          <label class="check"><input type="checkbox" name="verified" value="1" ${filters.verified ? html`checked` : ''}> Verified only</label>
          <label class="check">Sort
            <select name="sort" class="sort-select">
              ${[['recommended', 'Verified first'], ['newest', 'Newest'], ['price_asc', 'Price: low to high'], ['price_desc', 'Price: high to low']].map(([value, label]) => html`<option value="${value}" ${filters.sort === value ? html`selected` : ''}>${label}</option>`)}
            </select>
          </label>
        </div>
        <div class="form-actions">
          <button class="btn btn-outline" type="button" id="clear-search">Clear</button>
          <button class="btn btn-accent" type="submit">Search homes</button>
        </div>
      </div>
      <p class="form-error notice notice-error" hidden></p>
    </form>

    <section aria-live="polite" id="results"></section>
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

  async function load() {
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
        </div>
        ${total ? html`<div class="card-grid">${properties.map(propertyCard)}</div>` : html`
          <div class="empty">
            <h3>No homes match your search yet</h3>
            <p>Try a wider rent or price range, another area, or fewer bedrooms. New listings are added every day.</p>
            <button class="btn btn-primary" type="button" data-clear>Show all homes</button>
          </div>`}
      `);
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

  form.addEventListener('submit', event => { event.preventDefault(); load(); });
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
  results.addEventListener('click', event => { if (event.target.closest('[data-clear]')) clearSearch(); });
  await load();
}
