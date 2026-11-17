// My profile: picture, name, phone, occupation, a short "about me", and the password.

import { api } from '../api.js';
import { refreshSession } from '../app.js';
import { $, ROLE_LABELS, avatar, confirmClick, formatDate, html, mount, submitting, toast } from '../ui.js';

const MAX_AVATAR_BYTES = 2 * 1024 * 1024;
const AVATAR_EXTENSIONS = ['jpg', 'jpeg', 'png', 'webp'];

const COUNT_LABELS = {
  listings: ['Listings', '#/owner/listings'],
  savedHomes: ['Saved homes', '#/favorites'],
  visits: ['Visits', '#/visits'],
  consultations: ['Consultations', '#/consultations'],
};

function pictureBlock(me) {
  return html`<div class="profile-picture">
    ${avatar(me, 'large')}
    <div>
      <label class="btn btn-outline btn-small file-input">${me.avatarUrl ? 'Change picture' : 'Upload a picture'}
        <input type="file" id="avatar-input" accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"></label>
      ${me.avatarUrl ? html`<button class="btn btn-danger btn-small" type="button" id="avatar-remove">Remove</button>` : ''}
      <p class="small muted">JPG, PNG or WebP, up to 2 MB. Your picture shows in the menu and next to your name on your listings.</p>
    </div>
  </div>`;
}

export async function render({ root, navigate }) {
  const me = await api.get('/api/profile');
  const counts = Object.entries(me.counts).filter(([key]) => COUNT_LABELS[key]);
  mount(root, html`
    <div class="page-head"><div><h1>My profile</h1><p>How other people on Property Finder Bangladesh see you, and your account settings.</p></div></div>
    <div class="grid-2">
      <div class="stack">
        <form class="panel" id="profile-form" novalidate>
          <div class="panel-title"><h2>Profile</h2></div>
          <div id="picture">${pictureBlock(me)}</div>
          <p class="form-error notice notice-error" hidden></p>
          <div class="form-grid">
            <label class="field"><span>Full name</span><input name="fullName" value="${me.fullName}" maxlength="80" autocomplete="name"></label>
            <label class="field"><span>Mobile number</span><input name="phone" value="${me.phone}" inputmode="tel" autocomplete="tel"></label>
            <label class="field full"><span>Occupation <span class="hint">optional</span></span>
              <input name="occupation" value="${me.occupation}" maxlength="80" placeholder="For example: Software engineer, Banani"></label>
            <label class="field full"><span>About me <span class="hint">optional, up to 500 characters</span></span>
              <textarea name="bio" maxlength="500" placeholder="A few words about you, for owners and advocates you contact.">${me.bio}</textarea></label>
          </div>
          ${me.role === 'owner' && me.phoneVerified ? html`<p class="small muted">Changing your mobile number means confirming the new number with a code before your next listing.</p>` : ''}
          <div class="form-actions"><button class="btn btn-primary" type="submit">Save profile</button></div>
        </form>

        <form class="panel" id="password-form" novalidate>
          <div class="panel-title"><h2>Change password</h2></div>
          <p class="form-error notice notice-error" hidden></p>
          <div class="form-grid">
            <label class="field full"><span>Current password</span><input name="currentPassword" type="password" autocomplete="current-password"></label>
            <label class="field"><span>New password <span class="hint">8+ characters, a letter and a number</span></span>
              <input name="newPassword" type="password" autocomplete="new-password"></label>
            <label class="field"><span>Repeat the new password</span><input name="repeatPassword" type="password" autocomplete="new-password"></label>
          </div>
          <p class="small muted">You stay signed in here; other phones or computers where you are signed in are signed out.</p>
          <div class="form-actions"><button class="btn btn-primary" type="submit">Change password</button></div>
        </form>
      </div>

      <aside class="stack">
        <div class="panel profile-card">
          ${avatar(me, 'large')}
          <h2>${me.fullName}</h2>
          <p class="muted">${ROLE_LABELS[me.role]}${me.occupation ? html` · ${me.occupation}` : ''}</p>
          ${me.bio ? html`<p class="profile-bio">${me.bio}</p>` : ''}
        </div>
        <div class="panel">
          <h3>Account</h3>
          <ul class="fact-list single">
            <li><small>Email</small><strong>${me.email}</strong></li>
            <li><small>Mobile</small><strong>${me.phone}</strong>
              ${me.role === 'owner' ? html`<span class="sub">${me.phoneVerified ? '✓ Confirmed with a code' : html`Not confirmed yet · <a href="#/owner/listings/new">Confirm now</a>`}</span>` : ''}</li>
            <li><small>Member since</small><strong>${formatDate(me.createdAt)}</strong></li>
          </ul>
          ${counts.length ? html`<ul class="fact-list stat-tiles">${counts.map(([key, count]) => html`
            <li><small>${COUNT_LABELS[key][0]}</small><strong><a href="${COUNT_LABELS[key][1]}">${count}</a></strong></li>`)}</ul>` : ''}
        </div>
      </aside>
    </div>`);

  const reopen = async message => {
    toast(message);
    await refreshSession();   // the header shows the new name and picture
    navigate('/profile');
  };

  const form = $('#profile-form', root);
  form.addEventListener('submit', event => {
    event.preventDefault();
    submitting(form, async () => {
      const updated = await api.put('/api/profile', {
        fullName: form.fullName.value, phone: form.phone.value, occupation: form.occupation.value, bio: form.bio.value,
      });
      await reopen(me.role === 'owner' && me.phoneVerified && !updated.phoneVerified
        ? 'Profile saved. Confirm your new mobile number before your next listing.' : 'Profile saved.');
    });
  });

  root.addEventListener('change', async event => {
    if (event.target.id !== 'avatar-input' || !event.target.files.length) return;
    const file = event.target.files[0];
    const extension = file.name.includes('.') ? file.name.split('.').pop().toLowerCase() : '';
    if (!AVATAR_EXTENSIONS.includes(extension)) {
      toast('Only JPG, PNG and WebP pictures are accepted.', true);
      event.target.value = '';
      return;
    }
    if (file.size > MAX_AVATAR_BYTES) {
      toast('This picture is larger than 2 MB. Please choose a smaller one.', true);
      event.target.value = '';
      return;
    }
    try {
      await api.uploadAvatar(file);
      await reopen('Profile picture updated.');
    } catch (error) {
      toast(error.message, true);
      event.target.value = '';
    }
  });

  root.addEventListener('click', async event => {
    const remove = event.target.closest('#avatar-remove');
    if (!remove || !confirmClick(remove, 'Click again to remove')) return;
    remove.disabled = true;
    try {
      await api.del('/api/profile/avatar');
      await reopen('Profile picture removed.');
    } catch (error) {
      toast(error.message, true);
      remove.disabled = false;
    }
  });

  const passwordForm = $('#password-form', root);
  passwordForm.addEventListener('submit', event => {
    event.preventDefault();
    submitting(passwordForm, async () => {
      if (passwordForm.newPassword.value !== passwordForm.repeatPassword.value) {
        const error = new Error('Please fix the highlighted fields.');
        error.fields = { repeatPassword: 'The two new passwords are not the same.' };
        throw error;
      }
      const result = await api.post('/api/profile/password', {
        currentPassword: passwordForm.currentPassword.value, newPassword: passwordForm.newPassword.value,
      });
      passwordForm.reset();
      toast(result.otherSessionsEnded ? `Password changed. Signed out on ${result.otherSessionsEnded} other device(s).` : 'Password changed.');
    });
  });
}
