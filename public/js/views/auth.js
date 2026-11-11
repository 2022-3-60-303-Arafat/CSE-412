// Log in and sign up. The role is chosen at sign up and saved on the account (PB-02).

import { api } from '../api.js';
import { HOME_FOR_ROLE } from '../app.js';
import { $, ROLE_LABELS, html, mount, submitting, toast } from '../ui.js';

const DEMO_ACCOUNTS = [
  ['tenant@pfb.test', 'buyer_tenant'],
  ['owner@pfb.test', 'owner'],
  ['advocate@pfb.test', 'advocate'],
  ['admin@pfb.test', 'admin'],
];

function afterLogin(session, navigate, user, next) {
  session.user = user;
  toast(`Welcome, ${user.fullName}.`);
  navigate(next && next.startsWith('/') ? next : HOME_FOR_ROLE[user.role]);
}

export async function renderLogin({ root, query, session, navigate }) {
  if (session.user) {
    navigate(HOME_FOR_ROLE[session.user.role]);
    return;
  }
  mount(root, html`
    <div class="auth-wrap">
      <div class="panel">
        <h1>Log in</h1>
        <p class="muted">Welcome back to Property Finder Bangladesh.</p>
        <form id="login-form" novalidate>
          <p class="form-error notice notice-error" hidden></p>
          <div class="stack">
            <label class="field"><span>Email</span><input name="email" type="email" autocomplete="email" required></label>
            <label class="field"><span>Password</span><input name="password" type="password" autocomplete="current-password" required></label>
            <button class="btn btn-primary btn-block" type="submit">Log in</button>
          </div>
        </form>
        <p class="small muted">New here? <a href="#/signup">Create an account</a></p>
        <div class="demo-accounts">
          <strong>Demo accounts</strong> <span class="muted">(password <code>Demo@1234</code>), click to fill in:</span>
          <ul>${DEMO_ACCOUNTS.map(([email, role]) => html`
            <li><button type="button" data-email="${email}"><span>${email}</span><span class="muted">${ROLE_LABELS[role]}</span></button></li>`)}
          </ul>
        </div>
      </div>
    </div>`);

  const form = $('#login-form', root);
  root.addEventListener('click', event => {
    const button = event.target.closest('[data-email]');
    if (!button) return;
    form.email.value = button.dataset.email;
    form.password.value = 'Demo@1234';
    form.password.focus();
  });
  form.addEventListener('submit', event => {
    event.preventDefault();
    submitting(form, async () => {
      const { user } = await api.post('/api/auth/login', { email: form.email.value, password: form.password.value });
      afterLogin(session, navigate, user, query.next);
    });
  });
  form.email.focus();
}

export async function renderSignup({ root, session, navigate }) {
  if (session.user) {
    navigate(HOME_FOR_ROLE[session.user.role]);
    return;
  }
  mount(root, html`
    <div class="auth-wrap">
      <div class="panel">
        <h1>Create an account</h1>
        <p class="muted">Choose how you will use Property Finder Bangladesh.</p>
        <form id="signup-form" novalidate>
          <p class="form-error notice notice-error" hidden></p>
          <div class="stack">
            <fieldset class="field form-section" data-error-for="role">
              <legend>I want to</legend>
              <div class="role-choice">
                <label><input type="radio" name="role" value="buyer_tenant" checked>
                  <span><strong>Buy or rent</strong><small>Search homes, save favorites, contact owners.</small></span></label>
                <label><input type="radio" name="role" value="owner">
                  <span><strong>Sell or rent out</strong><small>List property and get it legally verified.</small></span></label>
              </div>
            </fieldset>
            <label class="field"><span>Full name</span><input name="fullName" autocomplete="name"></label>
            <label class="field"><span>Email</span><input name="email" type="email" autocomplete="email"></label>
            <label class="field"><span>Mobile number</span><input name="phone" inputmode="tel" autocomplete="tel" placeholder="01XXXXXXXXX"></label>
            <label class="field"><span>Password <span class="hint">at least 8 characters, with a letter and a number</span></span>
              <input name="password" type="password" autocomplete="new-password"></label>
            <button class="btn btn-primary btn-block" type="submit">Create account</button>
          </div>
        </form>
        <p class="small muted">Already have an account? <a href="#/login">Log in</a>. Advocate accounts are created by the admin.</p>
      </div>
    </div>`);

  const form = $('#signup-form', root);
  form.addEventListener('submit', event => {
    event.preventDefault();
    submitting(form, async () => {
      const data = Object.fromEntries(new FormData(form));
      const { user } = await api.post('/api/auth/signup', data);
      afterLogin(session, navigate, user);
    });
  });
}
