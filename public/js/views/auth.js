// Log in and sign up. The role is chosen at sign up and saved on the account (PB-02).
// Advocates apply on their own page and are verified by the admin after an in-person meeting.

import { api } from '../api.js';
import { homeFor, refreshSession } from '../app.js';
import { $, ADVOCATE_STATUS, ROLE_LABELS, badge, formatDate, html, mount, submitting, toast } from '../ui.js';

const DEMO_ACCOUNTS = [
  ['tenant@pfb.test', 'buyer_tenant'],
  ['owner@pfb.test', 'owner'],
  ['advocate@pfb.test', 'advocate'],
  ['applicant@pfb.test', 'advocate', 'Advocate (applied, not verified)'],
  ['admin@pfb.test', 'admin'],
];

function afterLogin(session, navigate, user, next) {
  session.user = user;
  toast(`Welcome, ${user.fullName}.`);
  navigate(next && next.startsWith('/') ? next : homeFor(user));
}

export async function renderLogin({ root, query, session, navigate }) {
  if (session.user) {
    navigate(homeFor(session.user));
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
        <p class="small muted">Advocates log in here too. Not registered yet? <a href="#/advocate/signup">Apply as an advocate</a></p>
        <div class="demo-accounts">
          <strong>Demo accounts</strong> <span class="muted">(password <code>Demo@1234</code>), click to fill in:</span>
          <ul>${DEMO_ACCOUNTS.map(([email, role, label]) => html`
            <li><button type="button" data-email="${email}"><span>${email}</span><span class="muted">${label || ROLE_LABELS[role]}</span></button></li>`)}
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

// One sign-up page for all three account types. `preset` picks the type that is selected first.
export async function renderSignup({ root, session, navigate }, preset = 'buyer_tenant') {
  if (session.user) {
    navigate(homeFor(session.user));
    return;
  }
  const checked = role => (preset === role ? html`checked` : '');
  mount(root, html`
    <div class="auth-wrap wide">
      <div class="panel">
        <h1>Create an account</h1>
        <p class="muted">Choose how you will use Property Finder Bangladesh.</p>
        <form id="signup-form" novalidate>
          <p class="form-error notice notice-error" hidden></p>
          <div class="stack">
            <fieldset class="field form-section" data-error-for="role">
              <legend>I want to</legend>
              <div class="role-choice three">
                <label><input type="radio" name="role" value="buyer_tenant" ${checked('buyer_tenant')}>
                  <span><strong>Buy or rent</strong><small>Search homes, save favorites, contact owners.</small></span></label>
                <label><input type="radio" name="role" value="owner" ${checked('owner')}>
                  <span><strong>Sell or rent out</strong><small>List property and get it legally verified.</small></span></label>
                <label><input type="radio" name="role" value="advocate" ${checked('advocate')}>
                  <span><strong>Work as an advocate</strong><small>Check property papers for owners and buyers.</small></span></label>
              </div>
            </fieldset>
            <div class="notice notice-info" id="advocate-steps" hidden>
              <strong>How advocate accounts work</strong>
              <ol class="steps">
                <li>Create your account on this page.</li>
                <li>The admin sends you an appointment. You will see it when you log in.</li>
                <li>Come in person with your Bar Council certificate and national ID.</li>
                <li>After the admin verifies you, the advocate dashboard opens for you.</li>
              </ol>
            </div>
            <label class="field"><span>Full name</span><input name="fullName" autocomplete="name"></label>
            <label class="field"><span>Email</span><input name="email" type="email" autocomplete="email"></label>
            <label class="field"><span>Mobile number</span><input name="phone" inputmode="tel" autocomplete="tel" placeholder="01XXXXXXXXX"></label>
            <div class="stack" id="advocate-fields" hidden>
              <label class="field"><span>Bar Council ID</span><input name="barCouncilId" placeholder="e.g. DBC-2021-0042"></label>
              <label class="field"><span>Specialization</span><input name="specialization" placeholder="e.g. Land and property documents"></label>
            </div>
            <label class="field"><span>Password <span class="hint">at least 8 characters, with a letter and a number</span></span>
              <input name="password" type="password" autocomplete="new-password"></label>
            <button class="btn btn-primary btn-block" type="submit">Create account</button>
          </div>
        </form>
        <p class="small muted">Already have an account? <a href="#/login">Log in</a>.</p>
      </div>
    </div>`);

  const form = $('#signup-form', root);
  const isAdvocate = () => form.role.value === 'advocate';
  function syncRole() {
    $('#advocate-fields', form).hidden = !isAdvocate();
    $('#advocate-steps', form).hidden = !isAdvocate();
    form.querySelector('button[type="submit"]').textContent = isAdvocate() ? 'Send application' : 'Create account';
  }
  form.addEventListener('change', event => { if (event.target.name === 'role') syncRole(); });
  syncRole();

  form.addEventListener('submit', event => {
    event.preventDefault();
    submitting(form, async () => {
      const data = Object.fromEntries(new FormData(form));
      if (isAdvocate()) {
        // Advocates are checked in person by the admin, so they apply through their own endpoint.
        const { user } = await api.post('/api/auth/advocate-signup', data);
        session.user = user;
        toast('Application sent. The admin will send you an appointment.');
        navigate(homeFor(user));
        return;
      }
      delete data.barCouncilId;
      delete data.specialization;
      const { user } = await api.post('/api/auth/signup', data);
      afterLogin(session, navigate, user);
    });
  });
}

// The "Apply as an advocate" links open the same sign-up page with the advocate account chosen.
export const renderAdvocateSignup = context => renderSignup(context, 'advocate');

const APPLICATION_NOTICE = {
  pending: ['notice-info', 'Your application has been received',
    'The admin will send you an appointment for an in-person check. Please log in again later to see it.'],
  appointment_sent: ['notice-warn', 'You have an appointment',
    'Please come in person at the time and place below. Bring your Bar Council certificate and national ID.'],
  verified: ['notice-ok', 'You are verified', 'The admin has verified you in person. Your advocate dashboard is open.'],
  rejected: ['notice-error', 'Your application was not approved', 'The admin could not verify your application.'],
};

// What an advocate sees until the admin has verified them: status, appointment and the admin's message.
export async function renderAdvocateApplication({ root, session, isCurrent }) {
  const { application, user } = await api.get('/api/advocate/application');
  if (!isCurrent()) return;
  // The admin may have changed the status since this browser last loaded the account.
  if (user.advocateStatus !== session.user.advocateStatus) await refreshSession();
  const status = application.advocateStatus;
  const [tone, title, text] = APPLICATION_NOTICE[status];
  mount(root, html`
    <div class="page-head"><div><h1>My advocate application</h1><p>Your account is checked in person before you can review property papers.</p></div></div>
    <div class="panel">
      <div class="panel-title"><h2>Status</h2>${badge(`advocate-${status}`, ADVOCATE_STATUS[status])}</div>
      <div class="notice ${tone}"><strong>${title}</strong><p>${text}</p></div>
      ${status === 'appointment_sent' && application.appointment ? html`
        <ul class="fact-list">
          <li><small>Date and time</small><strong>${formatDate(application.appointment.at, true)}</strong></li>
          <li><small>Place</small><strong>${application.appointment.place}</strong></li>
        </ul>` : ''}
      ${application.adminMessage && status !== 'verified' ? html`
        <h3>Message from the admin</h3>
        <div class="notes-box">${application.adminMessage}</div>` : ''}
      ${status === 'verified' ? html`<p><a class="btn btn-primary" href="#/advocate">Open the verification queue</a></p>` : ''}
      <h3>Your details</h3>
      <ul class="fact-list">
        <li><small>Name</small><strong>${application.fullName}</strong></li>
        <li><small>Bar Council ID</small><strong>${application.barCouncilId}</strong></li>
        <li><small>Specialization</small><strong>${application.specialization}</strong></li>
        <li><small>Applied on</small><strong>${formatDate(application.createdAt)}</strong></li>
      </ul>
    </div>`);
}
