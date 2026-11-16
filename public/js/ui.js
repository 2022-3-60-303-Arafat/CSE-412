// Rendering helpers, labels and formatting shared by every view.

class SafeHtml {
  constructor(value) { this.value = value; }
  toString() { return this.value; }
}

const escapeHtml = value => String(value).replace(/[&<>"']/g, ch => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]
));

function renderValue(value) {
  if (value === null || value === undefined || value === false) return '';
  if (value instanceof SafeHtml) return value.value;
  if (Array.isArray(value)) return value.map(renderValue).join('');
  return escapeHtml(value);
}

// Tagged template: every ${value} is escaped unless it is itself an html`` result.
export function html(strings, ...values) {
  let out = strings[0];
  values.forEach((value, i) => { out += renderValue(value) + strings[i + 1]; });
  return new SafeHtml(out);
}

export function mount(root, content) {
  root.innerHTML = String(content);
}

export const $ = (selector, root = document) => root.querySelector(selector);
export const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

// ------------------------------------------------------------------ labels

export const ROLE_LABELS = { buyer_tenant: 'Buyer / Tenant', owner: 'Owner', advocate: 'Advocate', admin: 'Admin' };
export const REQUEST_STATUS = {
  pending: 'Pending', in_review: 'In review', document_verified: 'Document Verified', issue_found: 'Issue Found',
};
export const PROPERTY_STATUS = { unverified: 'Unverified', document_verified: 'Verified', issue_found: 'Issue Found' };
export const LISTING_STATUS = { active: 'Active', sold_rented: 'Sold / Rented', removed: 'Removed' };
export const TENANT_PREFERENCE = { family: 'Family', bachelor: 'Bachelor', any: 'Anyone' };
export const DOCUMENT_LABELS = {
  land_deed: 'Land deed', mutation: 'Mutation paper', tax_receipt: 'Tax receipt', ownership_history: 'Ownership history',
};
export const REVIEW_STATUS = { not_checked: 'Not checked', ok: 'OK', problem: 'Problem' };
// An advocate who applied is verified by the admin after an in-person meeting.
export const ADVOCATE_STATUS = {
  pending: 'Waiting for appointment', appointment_sent: 'Appointment sent', verified: 'Verified', rejected: 'Rejected',
};
export const ACTION_LABELS = {
  account_created: 'Account created',
  advocate_added: 'Advocate added',
  advocate_applied: 'Advocate applied',
  advocate_appointment_sent: 'Advocate appointment sent',
  advocate_verification_changed: 'Advocate verification changed',
  account_status_changed: 'Account status changed',
  listing_created: 'Listing created',
  listing_updated: 'Listing updated',
  listing_status_changed: 'Listing status changed',
  verification_requested: 'Verification requested',
  verification_status_changed: 'Verification status changed',
  document_uploaded: 'Paper uploaded',
  high_demand_area_added: 'High-demand area added',
  high_demand_area_removed: 'High-demand area removed',
};

const statusText = value => REQUEST_STATUS[value] || PROPERTY_STATUS[value] || LISTING_STATUS[value]
  || DOCUMENT_LABELS[value] || ROLE_LABELS[value] || REVIEW_STATUS[value] || ADVOCATE_STATUS[value] || value;
export const describeValue = value => (value ? statusText(value) : '');

export function badge(status, text) {
  return html`<span class="badge badge-${status}">${text || statusText(status)}</span>`;
}

export function verificationBadge(status) {
  return status === 'document_verified'
    ? html`<span class="badge badge-verified">&#10003; Verified</span>`
    : status === 'issue_found' ? badge('issue_found') : badge('unverified', 'Unverified');
}

// ------------------------------------------------------------------ formatting

const grouped = new Intl.NumberFormat('en-IN');
export const taka = amount => (amount === null || amount === undefined ? '' : `৳ ${grouped.format(amount)}`);

export function shortTaka(amount) {
  if (amount >= 10_000_000) return `৳ ${+(amount / 10_000_000).toFixed(2)} crore`;
  if (amount >= 100_000) return `৳ ${+(amount / 100_000).toFixed(2)} lakh`;
  return taka(amount);
}

export function priceLine(property) {
  return property.listingType === 'rent'
    ? html`${taka(property.amount)} <small>/ month</small>`
    : html`${shortTaka(property.amount)}`;
}

export function formatDate(value, withTime = false) {
  if (!value) return '';
  const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(value);
  const date = new Date(dateOnly ? `${value}T00:00:00` : value);
  const options = { day: 'numeric', month: 'short', year: 'numeric' };
  if (withTime && !dateOnly) Object.assign(options, { hour: 'numeric', minute: '2-digit' });
  return date.toLocaleString('en-GB', options);
}

export function photo(property, alt) {
  return property.image
    ? html`<img src="${property.image}" alt="${alt}" loading="lazy">`
    : html`<div class="photo-placeholder" role="img" aria-label="${alt}">${property.propertyType}</div>`;
}

// ------------------------------------------------------------------ feedback

let toastTimer;
export function toast(message, isError = false) {
  const element = $('#toast');
  element.textContent = message;
  element.classList.toggle('error', isError);
  element.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => element.classList.remove('show'), 3200);
}

export function clearErrors(form) {
  $$('.field-error', form).forEach(node => node.remove());
  $$('.has-error', form).forEach(node => node.classList.remove('has-error'));
  $$('[aria-invalid]', form).forEach(node => node.removeAttribute('aria-invalid'));
  const summary = $('.form-error', form);
  if (summary) summary.hidden = true;
}

// Show the server's per-field messages next to the matching inputs (by name).
export function showErrors(form, error) {
  clearErrors(form);
  const fields = error.fields || {};
  let first = null;
  for (const [name, message] of Object.entries(fields)) {
    const input = form.querySelector(`[name="${CSS.escape(name)}"]`);
    const holder = $(`[data-error-for="${CSS.escape(name)}"]`, form) || input?.closest('.field');
    if (!holder) continue;
    holder.classList.add('has-error');
    input?.setAttribute('aria-invalid', 'true');
    const note = document.createElement('span');
    note.className = 'field-error';
    note.textContent = message;
    holder.append(note);
    first ||= input;
  }
  const summary = $('.form-error', form);
  if (summary) {
    summary.textContent = error.message;
    summary.hidden = false;
  } else if (!first) {
    toast(error.message, true);
  }
  first?.focus();
}

// Disable the submit button while a request runs; report errors on the form.
export async function submitting(form, task) {
  const buttons = $$('button[type="submit"], button:not([type])', form);
  buttons.forEach(button => { button.disabled = true; });
  clearErrors(form);
  try {
    return await task();
  } catch (error) {
    showErrors(form, error);
    return undefined;
  } finally {
    buttons.forEach(button => { button.disabled = false; });
  }
}

export function numberOrBlank(value) {
  const text = String(value ?? '').trim().replace(/,/g, '');
  return text === '' ? '' : Number(text);
}

// Two-step delete/remove: the first click asks, the second click confirms.
export function confirmClick(button, label = 'Click again to confirm') {
  if (button.dataset.armed === '1') return true;
  const original = button.textContent;
  button.dataset.armed = '1';
  button.textContent = label;
  button.classList.add('confirm');
  setTimeout(() => {
    button.dataset.armed = '';
    button.textContent = original;
    button.classList.remove('confirm');
  }, 4000);
  return false;
}

export const loading = html`<div class="loading">Loading…</div>`;

export function errorPanel(error) {
  return html`<div class="notice notice-error"><strong>Something went wrong</strong><p>${error.message}</p></div>`;
}
