// Entry point: session, role-based menu (PB-02) and hash routing.

import { api } from './api.js';
import { $, ROLE_LABELS, avatar, errorPanel, html, loading, mount, toast } from './ui.js';
import * as home from './views/home.js';
import * as property from './views/property.js';
import * as auth from './views/auth.js';
import * as calculator from './views/calculator.js';
import * as owner from './views/owner.js';
import * as buyer from './views/buyer.js';
import * as review from './views/review.js';
import * as admin from './views/admin.js';
import * as consult from './views/consult.js';
import * as agreements from './views/agreements.js';
import * as sprint5 from './views/sprint5.js';
import * as profile from './views/profile.js';
import { languageSwitch, setUpLanguage } from './i18n.js';

export const session = { user: null, meta: { cities: [], propertyTypes: [], areas: [], documentTypes: [] } };

// Pages each role can open. The server checks the same rules on every API call.
const routes = [
  { path: '/', view: home.render },
  { path: '/property/:id', view: property.render },
  { path: '/login', view: auth.renderLogin },
  { path: '/signup', view: auth.renderSignup },
  { path: '/advocate/signup', view: auth.renderAdvocateSignup },
  { path: '/advocate/application', view: auth.renderAdvocateApplication, roles: ['advocate'] },
  { path: '/calculator', view: calculator.render },
  { path: '/favorites', view: buyer.renderFavorites, roles: ['buyer_tenant'] },
  { path: '/inquiries', view: buyer.renderInquiries, roles: ['buyer_tenant', 'owner'] },
  { path: '/history', view: buyer.renderHistory, roles: ['buyer_tenant', 'owner'] },
  { path: '/owner/listings', view: owner.renderListings, roles: ['owner'] },
  { path: '/owner/listings/new', view: owner.renderForm, roles: ['owner'] },
  { path: '/owner/listings/:id/edit', view: owner.renderForm, roles: ['owner'] },
  { path: '/owner/verification/:id', view: owner.renderVerification, roles: ['owner'] },
  { path: '/advocate', view: review.renderQueue, roles: ['advocate'], verifiedOnly: true },
  { path: '/advocate/requests/:id', view: review.renderRequest, roles: ['advocate'], verifiedOnly: true },
  { path: '/consultations', view: consult.renderList, roles: ['buyer_tenant', 'advocate'], verifiedOnly: true },
  { path: '/consultations/new', view: consult.renderBooking, roles: ['buyer_tenant'] },
  { path: '/consultations/:id', view: consult.renderDetail, roles: ['buyer_tenant', 'advocate'], verifiedOnly: true },
  { path: '/notifications', view: consult.renderNotifications, roles: ['buyer_tenant', 'owner', 'advocate', 'admin'] },
  { path: '/agreements', view: agreements.renderList, roles: ['owner', 'buyer_tenant', 'advocate', 'admin'], verifiedOnly: true },
  { path: '/agreements/new', view: agreements.renderNew, roles: ['owner'] },
  { path: '/agreements/:id', view: agreements.renderDetail, roles: ['owner', 'buyer_tenant', 'advocate', 'admin'], verifiedOnly: true },
  { path: '/visits', view: sprint5.renderVisits, roles: ['buyer_tenant', 'owner'] },
  { path: '/profile', view: profile.render, roles: ['buyer_tenant', 'owner', 'advocate', 'admin'] },
  { path: '/compare', view: sprint5.renderCompare },
  { path: '/price-guide', view: sprint5.renderPriceGuide },
  { path: '/admin', view: admin.render, roles: ['admin'] },
  { path: '/admin/requests/:id', view: review.renderRequest, roles: ['admin'] },
];

const MENUS = {
  guest: [['/', 'Find homes'], ['/price-guide', 'Price guide'], ['/calculator', 'Calculators']],
  buyer_tenant: [['/', 'Find homes'], ['/favorites', 'Saved'], ['/visits', 'Visits'], ['/inquiries', 'Inquiries'], ['/consultations', 'Consultations'], ['/agreements', 'Agreements']],
  owner: [['/', 'Find homes'], ['/owner/listings', 'My listings'], ['/visits', 'Visits'], ['/inquiries', 'Inquiries'], ['/agreements', 'Agreements']],
  advocate: [['/advocate', 'Verification queue'], ['/consultations', 'Consultations'], ['/agreements', 'Agreements'], ['/', 'Browse listings']],
  advocate_unverified: [['/advocate/application', 'My application'], ['/', 'Browse listings']],
  admin: [['/admin', 'Admin panel'], ['/', 'Browse listings']],
};

// Links in the profile menu (under the picture in the header), so the main menu fits on one line.
const PROFILE_LINKS = {
  buyer_tenant: [['/history', 'History'], ['/calculator', 'Calculators'], ['/price-guide', 'Price guide']],
  owner: [['/history', 'History'], ['/calculator', 'Calculators'], ['/price-guide', 'Price guide']],
  advocate: [],
  admin: [],
};

const HOME_FOR_ROLE = { buyer_tenant: '/', owner: '/owner/listings', advocate: '/advocate', admin: '/admin' };

// An advocate who applied cannot use the advocate pages until the admin has verified them in person.
export const isUnverifiedAdvocate = user => user?.role === 'advocate' && user.advocateStatus !== 'verified';
export const homeFor = user => (isUnverifiedAdvocate(user) ? '/advocate/application' : HOME_FOR_ROLE[user.role]);

export function navigate(path) {
  if (location.hash === `#${path}`) route();
  else location.hash = path;
}

function parseHash() {
  const raw = location.hash.replace(/^#/, '') || '/';
  const [path, queryString = ''] = raw.split('?');
  return { path: path || '/', query: Object.fromEntries(new URLSearchParams(queryString)) };
}

function match(path) {
  for (const route of routes) {
    const names = [];
    const pattern = new RegExp(`^${route.path.replace(/:(\w+)/g, (_, name) => { names.push(name); return '(\\d+)'; })}$`);
    const found = path.match(pattern);
    if (found) return { route, params: Object.fromEntries(names.map((name, i) => [name, Number(found[i + 1])])) };
  }
  return null;
}

function renderNav(path) {
  const user = session.user;
  const links = MENUS[!user ? 'guest' : isUnverifiedAdvocate(user) ? 'advocate_unverified' : user.role];
  const nav = $('#site-nav');
  mount(nav, html`
    ${links.map(([href, label]) => html`<a href="#${href}" class="${path === href ? 'active' : ''}">${label}</a>`)}
    <span class="nav-spacer"></span>
    ${languageSwitch()}
    ${user ? html`
      <a class="bell ${path === '/notifications' ? 'active' : ''}" href="#/notifications" aria-label="Notifications" title="Notifications">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 9a6 6 0 0 1 12 0c0 6 2.5 7 2.5 7h-17S6 15 6 9z"/><path d="M10 20a2 2 0 0 0 4 0"/></svg>
        <span class="bell-count" id="bell-count" hidden></span>
      </a>
      <div class="profile-menu">
        <button class="profile-toggle ${path === '/profile' ? 'active' : ''}" type="button" id="profile-toggle" aria-haspopup="true"
          aria-expanded="false" aria-controls="profile-dropdown" title="${user.fullName}">
          ${avatar(user, 'small')}<span class="profile-name">${user.fullName.replace(/^Adv\.?\s+/i, '').split(' ')[0]}</span>
          <span class="caret" aria-hidden="true">&#9662;</span>
        </button>
        <div class="profile-dropdown" id="profile-dropdown" hidden>
          <div class="profile-dropdown-head">${avatar(user, 'medium')}
            <div><strong>${user.fullName}</strong><small>${ROLE_LABELS[user.role]}${isUnverifiedAdvocate(user) ? ' (not verified)' : ''}</small></div></div>
          <a href="#/profile">My profile</a>
          ${(isUnverifiedAdvocate(user) ? [] : PROFILE_LINKS[user.role]).map(([href, label]) => html`<a href="#${href}">${label}</a>`)}
          <button type="button" class="logout" data-logout>Log out</button>
        </div>
      </div>` : html`
      <a href="#/login" class="${path === '/login' ? 'active' : ''}">Log in</a>
      <a class="btn btn-primary btn-small" href="#/signup">Sign up</a>`}
  `);
}

// PB-25: the bell in the menu shows how many notifications are unread.
let unreadCount = 0;
function showBell() {
  const count = $('#bell-count');
  if (!count) return;
  count.textContent = unreadCount > 99 ? '99+' : String(unreadCount);
  count.hidden = unreadCount === 0;
  count.parentElement.setAttribute('aria-label', unreadCount ? `Notifications, ${unreadCount} unread` : 'Notifications');
}
export async function updateBell() {
  if (!session.user) return;
  try {
    ({ unread: unreadCount } = await api.get('/api/notifications?count=1'));
    showBell();
  } catch {
    // The bell is a convenience; a failed check must not break the page.
  }
}

function forbidden(roles) {
  const needed = roles.map(role => ROLE_LABELS[role]).join(' or ');
  return html`<div class="empty">
    <h3>This page is not available for your account</h3>
    <p>It is only for ${needed} accounts. You are signed in as ${ROLE_LABELS[session.user.role]}.</p>
    <a class="btn btn-primary" href="#${homeFor(session.user)}">Go to my dashboard</a>
  </div>`;
}

let renderCount = 0;

export async function route() {
  const { path, query } = parseHash();
  const ticket = ++renderCount;
  renderNav(path);
  showBell();
  updateBell();
  sprint5.updateCompareBar();
  $('#site-nav').classList.remove('open');
  $('.menu-toggle').setAttribute('aria-expanded', 'false');

  // A fresh element per page, so event listeners from the last page are dropped.
  const root = document.createElement('div');
  $('#main').replaceChildren(root);
  const found = match(path);
  if (!found) {
    mount(root, html`<div class="empty"><h3>Page not found</h3><p>This page does not exist.</p><a class="btn btn-primary" href="#/">Back to search</a></div>`);
    return;
  }
  const { route: current, params } = found;
  if (current.roles) {
    if (!session.user) {
      navigate(`/login?next=${encodeURIComponent(path)}`);
      return;
    }
    if (!current.roles.includes(session.user.role)) {
      mount(root, forbidden(current.roles));
      return;
    }
    if (current.verifiedOnly && isUnverifiedAdvocate(session.user)) {
      navigate('/advocate/application');
      return;
    }
  }
  mount(root, loading);
  try {
    await current.view({ root, params, query, session, navigate, isCurrent: () => ticket === renderCount });
  } catch (error) {
    if (error.status === 401) {
      session.user = null;
      navigate(`/login?next=${encodeURIComponent(path)}`);
      return;
    }
    if (ticket === renderCount) mount(root, errorPanel(error));
  }
  if (ticket === renderCount && !query.keepScroll) window.scrollTo(0, 0);
}

export async function refreshSession() {
  const { user } = await api.get('/api/auth/me');
  session.user = user;
  renderNav(parseHash().path);
  return user;
}

function closeProfileMenu() {
  const dropdown = $('#profile-dropdown');
  if (!dropdown || dropdown.hidden) return;
  dropdown.hidden = true;
  $('#profile-toggle')?.setAttribute('aria-expanded', 'false');
}

document.addEventListener('keydown', event => { if (event.key === 'Escape') closeProfileMenu(); });

document.addEventListener('click', async event => {
  const toggle = event.target.closest('#profile-toggle');
  if (toggle) {
    const dropdown = $('#profile-dropdown');
    dropdown.hidden = !dropdown.hidden;
    toggle.setAttribute('aria-expanded', String(!dropdown.hidden));
    return;
  }
  if (!event.target.closest('#profile-dropdown') || event.target.closest('a')) closeProfileMenu();
  if (event.target.closest('[data-logout]')) {
    try {
      await api.post('/api/auth/logout');
    } catch (error) {
      toast(error.message, true);
    }
    session.user = null;
    toast('You are logged out.');
    navigate('/');
  }
});

$('.menu-toggle').addEventListener('click', event => {
  const open = $('#site-nav').classList.toggle('open');
  event.currentTarget.setAttribute('aria-expanded', String(open));
});

window.addEventListener('hashchange', route);
setUpLanguage();   // PB-42: Bangla / English

async function start() {
  try {
    const [, meta] = await Promise.all([refreshSession(), api.get('/api/meta')]);
    session.meta = meta;
  } catch (error) {
    mount($('#main'), errorPanel(error));
    return;
  }
  route();
}

start();
