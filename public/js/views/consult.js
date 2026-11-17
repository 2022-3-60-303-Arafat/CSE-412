// Sprint 3 pages: consultations with an advocate (PB-20 to PB-24) and notifications (PB-25).
// A consultation is a free question chat or a paid booking for a time slot.

import { api } from '../api.js';
import { updateBell } from '../app.js';
import { $, CONSULT_STATE, badge, confirmClick, formatDate, html, mount, submitting, taka, toast } from '../ui.js';

const POLL_MS = 8000;

// ------------------------------------------------------------------ chat (PB-21)

function messageList(consultation, user) {
  if (!consultation || !consultation.messages.length) {
    return html`<p class="muted small chat-empty">No messages yet. Write your question below.</p>`;
  }
  return html`${consultation.messages.map(message => html`
    <div class="chat-message ${message.senderId === user.id ? 'mine' : ''}">
      <div class="chat-bubble">${message.body}</div>
      <small>${message.senderId === user.id ? 'You' : message.senderName} · ${formatDate(message.sentAt, true)}</small>
    </div>`)}`;
}

// Draws a chat thread with a box to write in. `send(body)` posts one message and returns the updated consultation.
// Returns a function that redraws the messages (used when new ones arrive).
export function mountChat(container, { consultation, user, send, placeholder = 'Write a message' }) {
  mount(container, html`
    <div class="chat">
      <div class="chat-messages" aria-live="polite">${messageList(consultation, user)}</div>
      <form class="chat-form" novalidate>
        <p class="form-error notice notice-error" hidden></p>
        <label class="field"><span class="sr-only">Message</span>
          <textarea name="body" maxlength="1000" placeholder="${placeholder}"></textarea></label>
        <button class="btn btn-primary" type="submit">Send</button>
      </form>
    </div>`);
  const list = $('.chat-messages', container);
  const form = $('.chat-form', container);
  let shown = consultation ? consultation.messages.length : 0;
  const redraw = updated => {
    if (updated.messages.length === shown) return;
    shown = updated.messages.length;
    mount(list, messageList(updated, user));
    list.scrollTop = list.scrollHeight;
  };
  form.addEventListener('submit', event => {
    event.preventDefault();
    submitting(form, async () => {
      const updated = await send(form.body.value);
      form.body.value = '';
      redraw(updated);
    });
  });
  list.scrollTop = list.scrollHeight;
  return redraw;
}

// Checks for new messages while the page that owns the chat is still on screen.
export function pollChat(load, redraw, isCurrent) {
  const timer = setInterval(async () => {
    if (!isCurrent()) {
      clearInterval(timer);
      return;
    }
    if (document.hidden) return;
    try {
      const updated = await load();
      if (updated && isCurrent()) redraw(updated);
    } catch {
      // A missed check is harmless; the next one tries again.
    }
  }, POLL_MS);
}

// ------------------------------------------------------------------ lists

const stateBadge = state => badge(`consult-${state}`, CONSULT_STATE[state]);
const when = slot => (slot ? html`${formatDate(slot, true)}` : html`<span class="muted">Any time</span>`);

function consultationTable(items, isAdvocate) {
  return html`<div class="table-wrap"><table class="data">
    <thead><tr><th>${isAdvocate ? 'Client' : 'Advocate'}</th><th>Property</th><th>When</th><th class="num">Fee</th><th>Status</th><th class="num"></th></tr></thead>
    <tbody>${items.map(item => html`<tr>
      <td><strong>${isAdvocate ? item.client.name : item.advocate.name}</strong>
        <span class="sub">${item.kind === 'free_chat' ? `Free question · ${item.messageCount} ${item.messageCount === 1 ? 'message' : 'messages'}` : 'Paid consultation'}</span></td>
      <td>${item.property ? html`<a href="#/property/${item.property.id}">${item.property.title}</a><span class="sub">${item.property.areaName}, ${item.property.city}</span>` : ''}</td>
      <td>${item.kind === 'free_chat' ? html`<span class="muted">${item.lastMessageAt ? `Last message ${formatDate(item.lastMessageAt, true)}` : ''}</span>` : when(item.slotStart)}</td>
      <td class="num">${item.fee ? taka(item.fee) : 'Free'}</td>
      <td>${stateBadge(item.state)}</td>
      <td class="num"><a class="btn btn-${['awaiting_payment', 'awaiting_advocate'].includes(item.state) ? 'primary' : 'outline'} btn-small" href="#/consultations/${item.id}">Open</a></td>
    </tr>`)}</tbody></table></div>`;
}

export async function renderList({ root, session }) {
  const { consultations } = await api.get('/api/consultations');
  const isAdvocate = session.user.role === 'advocate';
  // What the signed-in person has to act on comes first.
  const todo = consultations.filter(item => item.state === (isAdvocate ? 'awaiting_advocate' : 'awaiting_payment'));
  const booked = consultations.filter(item => item.state === 'booked');
  const chats = consultations.filter(item => item.kind === 'free_chat');
  const rest = consultations.filter(item => item.kind === 'paid' && !todo.includes(item) && !booked.includes(item));
  mount(root, html`
    <div class="page-head"><div><h1>Consultations</h1>
      <p>${isAdvocate ? 'Questions and paid consultations from buyers and tenants.' : 'Your questions to advocates and your paid consultations.'}</p></div></div>
    ${consultations.length ? '' : html`<div class="empty"><h3>No consultations yet</h3>
      <p>${isAdvocate ? 'Questions and booking requests from buyers will appear here.' : 'Open a verified home and choose Ask an Advocate to send a free question or book a paid consultation.'}</p>
      ${isAdvocate ? '' : html`<a class="btn btn-primary" href="#/?verified=1">See verified homes</a>`}</div>`}
    ${todo.length ? html`<section class="panel">
      <div class="panel-title"><h2>${isAdvocate ? 'Requests waiting for your answer' : 'Waiting for your payment'}</h2><span class="muted small">${todo.length}</span></div>
      ${consultationTable(todo, isAdvocate)}</section>` : ''}
    ${booked.length ? html`<section class="panel">
      <div class="panel-title"><h2>Booked</h2><span class="muted small">${booked.length}</span></div>
      ${consultationTable(booked, isAdvocate)}</section>` : ''}
    ${chats.length ? html`<section class="panel">
      <div class="panel-title"><h2>Free questions</h2><span class="muted small">${chats.length}</span></div>
      ${consultationTable(chats, isAdvocate)}</section>` : ''}
    ${rest.length ? html`<section class="panel">
      <div class="panel-title"><h2>Other consultations</h2></div>
      ${consultationTable(rest, isAdvocate)}</section>` : ''}
  `);
}

// ------------------------------------------------------------------ one consultation

function receiptPanel(receipt) {
  if (!receipt) return '';
  return html`<div class="panel receipt">
    <div class="panel-title"><h2>Payment receipt</h2>${badge('ok', 'Paid')}</div>
    <ul class="fact-list">
      <li><small>Transaction</small><strong>${receipt.transactionRef}</strong></li>
      <li><small>Amount</small><strong>${taka(receipt.amount)}</strong></li>
      <li><small>Method</small><strong>${receipt.method}</strong></li>
      <li><small>Paid on</small><strong>${formatDate(receipt.paidAt, true)}</strong></li>
    </ul>
  </div>`;
}

function clientActions(item) {
  if (item.state === 'awaiting_advocate') {
    return html`<div class="panel"><div class="notice notice-info"><strong>Waiting for the advocate</strong>
      <p>${item.advocate.name} has been asked. Your slot is held. You pay only after the advocate accepts.</p></div>
      <button class="btn btn-danger" type="button" data-cancel>Cancel request</button></div>`;
  }
  if (item.state === 'awaiting_payment') {
    return html`<form class="panel" id="pay-form" novalidate>
      <div class="notice notice-warn"><strong>Accepted. Pay to confirm your booking.</strong>
        <p>${item.advocate.name} accepted your slot. The booking is confirmed when the fee of ${taka(item.fee)} is paid.</p></div>
      <p class="form-error notice notice-error" hidden></p>
      <div class="form-grid">
        <label class="field"><span>Payment method</span>
          <select name="method"><option value="bkash">bKash</option><option value="nagad">Nagad</option><option value="card">Card</option></select></label>
        <label class="field"><span id="account-label">bKash mobile number</span>
          <input name="account" inputmode="numeric" autocomplete="off" placeholder="01XXXXXXXXX"></label>
      </div>
      <p class="small muted">Demo payment: no real money is taken. A number that ends in 0000 shows what a failed payment looks like.</p>
      <div class="form-actions">
        <button class="btn btn-accent" type="submit">Pay ${taka(item.fee)}</button>
        <button class="btn btn-danger" type="button" data-cancel>Cancel booking</button>
      </div>
    </form>`;
  }
  if (item.state === 'booked') {
    return html`<div class="panel"><div class="notice notice-ok"><strong>Booking confirmed</strong>
      <p>Your consultation with ${item.advocate.name} is on ${formatDate(item.slotStart, true)} (Bangladesh time). The advocate will add notes here after the session.</p></div></div>`;
  }
  return '';
}

function advocateActions(item) {
  if (item.state === 'awaiting_advocate') {
    return html`<div class="panel">
      <h2>Answer this request</h2>
      <p class="muted">${item.client.name} asked for ${formatDate(item.slotStart, true)}. If you accept, the client pays ${taka(item.fee)} to confirm.</p>
      <div class="form-actions"><button class="btn btn-ok" type="button" data-accept>Accept this slot</button></div>
      <form id="refuse-form" class="stack" novalidate>
        <p class="form-error notice notice-error" hidden></p>
        <label class="field"><span>Or refuse, with a reason <span class="hint">the client will see this</span></span>
          <textarea name="reason" maxlength="500"></textarea></label>
        <div class="form-actions"><button class="btn btn-danger" type="submit">Refuse</button></div>
      </form>
    </div>`;
  }
  if (item.state === 'awaiting_payment') {
    return html`<div class="panel"><div class="notice notice-info"><strong>Waiting for the client's payment</strong>
      <p>You accepted this slot. It is booked once ${item.client.name} pays the fee.</p></div></div>`;
  }
  if (item.state === 'booked') {
    return html`<form class="panel" id="complete-form" novalidate>
      <div class="notice notice-ok"><strong>Booked and paid</strong>
        <p>The session is on ${formatDate(item.slotStart, true)} (Bangladesh time).</p></div>
      <p class="form-error notice notice-error" hidden></p>
      <label class="field"><span>Follow-up notes <span class="hint">after the session: a record of your advice for the client</span></span>
        <textarea name="notes" maxlength="2000"></textarea></label>
      <div class="form-actions"><button class="btn btn-primary" type="submit">Save notes and mark completed</button></div>
    </form>`;
  }
  return '';
}

function outcome(item) {
  if (item.state === 'refused') {
    return html`<div class="panel"><div class="notice notice-error"><strong>The advocate refused this request</strong>
      <p>${item.followUpNotes || 'No reason was given.'}</p></div>
      ${item.property ? html`<a class="btn btn-outline" href="#/consultations/new?property=${item.property.id}">Choose another slot</a>` : ''}</div>`;
  }
  if (item.state === 'cancelled') {
    return html`<div class="panel"><div class="notice notice-info"><strong>This request was cancelled</strong><p>The time slot is free again.</p></div></div>`;
  }
  if (item.state === 'completed') {
    return html`<div class="panel"><h2>Follow-up notes from ${item.advocate.name}</h2>
      <div class="notes-box ok">${item.followUpNotes}</div></div>`;
  }
  return '';
}

export async function renderDetail({ root, params, session, navigate, isCurrent }) {
  const item = await api.get(`/api/consultations/${params.id}`);
  const user = session.user;
  const isAdvocate = user.role === 'advocate';
  const other = isAdvocate ? item.client.name : item.advocate.name;
  const isChat = item.kind === 'free_chat';
  mount(root, html`
    <a class="back-link" href="#/consultations">&larr; Consultations</a>
    <div class="page-head"><div>
      <h1>${isChat ? 'Question for' : 'Consultation with'} ${isAdvocate && isChat ? 'you from ' : ''}${other}</h1>
      <p>${item.property ? html`About <a href="#/property/${item.property.id}">${item.property.title}</a>, ${item.property.areaName}` : ''}</p>
    </div><div class="detail-badges">${stateBadge(item.state)}</div></div>
    <div class="grid-2">
      <div class="stack">
        ${isChat ? html`<div class="panel"><div class="panel-title"><h2>Messages</h2><span class="muted small">Free question</span></div><div id="chat"></div></div>` : html`
          ${isAdvocate ? advocateActions(item) : clientActions(item)}
          ${outcome(item)}
          ${receiptPanel(item.receipt)}`}
      </div>
      <aside class="panel">
        <h3>Details</h3>
        <ul class="fact-list">
          <li><small>${isAdvocate ? 'Client' : 'Advocate'}</small><strong>${other}</strong></li>
          ${isAdvocate ? '' : html`<li><small>Specialization</small><strong>${item.advocate.specialization}</strong></li>`}
          <li><small>Type</small><strong>${isChat ? 'Free question' : 'Paid consultation'}</strong></li>
          ${isChat ? '' : html`<li><small>Time (Bangladesh)</small><strong>${formatDate(item.slotStart, true)}</strong></li>
            <li><small>Fee</small><strong>${taka(item.fee)}</strong></li>`}
          <li><small>Started</small><strong>${formatDate(item.createdAt)}</strong></li>
        </ul>
      </aside>
    </div>`);

  const reopen = message => {
    toast(message);
    navigate(`/consultations/${item.id}`);
  };
  const act = async (button, path, body, message) => {
    button.disabled = true;
    try {
      await api.post(`/api/consultations/${item.id}/${path}`, body);
      reopen(message);
    } catch (error) {
      toast(error.message, true);
      button.disabled = false;
    }
  };

  if (isChat) {
    const redraw = mountChat($('#chat', root), {
      consultation: item, user, placeholder: isAdvocate ? 'Write your answer' : 'Write a message',
      send: body => api.post(`/api/consultations/${item.id}/messages`, { body }),
    });
    pollChat(() => api.get(`/api/consultations/${item.id}`), redraw, isCurrent);
    return;
  }

  root.addEventListener('click', event => {
    const cancel = event.target.closest('[data-cancel]');
    const accept = event.target.closest('[data-accept]');
    if (cancel && confirmClick(cancel, 'Confirm cancel')) act(cancel, 'cancel', {}, 'Cancelled. The slot is free again.');
    if (accept) act(accept, 'respond', { decision: 'confirmed' }, 'Accepted. The client can now pay to confirm.');
  });

  const payForm = $('#pay-form', root);
  payForm?.addEventListener('change', event => {
    if (event.target.name !== 'method') return;
    const card = payForm.method.value === 'card';
    $('#account-label', payForm).textContent = card ? 'Card number' : `${payForm.method.selectedOptions[0].textContent} mobile number`;
    payForm.account.placeholder = card ? '16 digits' : '01XXXXXXXXX';
  });
  payForm?.addEventListener('submit', event => {
    event.preventDefault();
    submitting(payForm, async () => {
      await api.post(`/api/consultations/${item.id}/pay`, { method: payForm.method.value, account: payForm.account.value });
      reopen('Payment received. Your booking is confirmed.');
    });
  });

  const refuseForm = $('#refuse-form', root);
  refuseForm?.addEventListener('submit', event => {
    event.preventDefault();
    submitting(refuseForm, async () => {
      await api.post(`/api/consultations/${item.id}/respond`, { decision: 'refused', reason: refuseForm.reason.value });
      reopen('Request refused. The client has been told.');
    });
  });

  const completeForm = $('#complete-form', root);
  completeForm?.addEventListener('submit', event => {
    event.preventDefault();
    submitting(completeForm, async () => {
      await api.post(`/api/consultations/${item.id}/complete`, { notes: completeForm.notes.value });
      reopen('Notes saved. The client can read them now.');
    });
  });
}

// ------------------------------------------------------------------ booking (PB-22)

function slotPicker(slots) {
  if (!slots.length) return html`<p class="muted">This advocate has no free slots in the next week. Choose another advocate.</p>`;
  const days = new Map();
  for (const slot of slots) {
    const day = slot.slice(0, 10);
    days.set(day, [...(days.get(day) || []), slot]);
  }
  return html`${[...days].map(([day, times]) => html`
    <div class="slot-day">
      <strong>${new Date(`${day}T00:00:00`).toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'short' })}</strong>
      <div class="slot-list">${times.map(slot => html`
        <label class="slot"><input type="radio" name="slotStart" value="${slot}"><span>${new Date(slot).toLocaleTimeString('en-GB', { hour: 'numeric', minute: '2-digit', hour12: true })}</span></label>`)}
      </div>
    </div>`)}`;
}

export async function renderBooking({ root, query, navigate, isCurrent }) {
  const propertyId = Number(query.property);
  if (!propertyId) {
    navigate('/consultations');
    return;
  }
  const [property, { advocates }] = await Promise.all([api.get(`/api/properties/${propertyId}`), api.get('/api/advocates')]);
  mount(root, html`
    <a class="back-link" href="#/property/${property.id}">&larr; Back to the listing</a>
    <div class="page-head"><div><h1>Book a paid consultation</h1>
      <p>About <strong>${property.title}</strong>, ${property.areaName}. Pick an advocate and a free time slot.</p></div></div>
    <form id="booking-form" novalidate>
      <p class="form-error notice notice-error" hidden></p>
      <fieldset class="form-section" data-error-for="advocateId">
        <legend>1. Choose an advocate</legend>
        <div class="role-choice">
          ${advocates.map((advocate, index) => html`
            <label><input type="radio" name="advocateId" value="${advocate.id}" ${index === 0 ? html`checked` : ''}>
              <span><strong>${advocate.name}</strong><small>${advocate.specialization}</small><small>Fee: ${taka(advocate.fee)}</small></span></label>`)}
        </div>
      </fieldset>
      <fieldset class="form-section" data-error-for="slotStart">
        <legend>2. Choose a time slot <span class="hint">Bangladesh time, next 7 days</span></legend>
        <div id="slots"></div>
      </fieldset>
      <div class="notice notice-info"><strong>How booking works</strong>
        <p>Your slot is held when you send the request. The advocate accepts or refuses it. You pay the fee after the advocate accepts, and then the booking is confirmed.</p></div>
      <div class="form-actions">
        <button class="btn btn-primary" type="submit">Send booking request</button>
        <a class="btn btn-outline" href="#/property/${property.id}">Cancel</a>
      </div>
    </form>`);

  const form = $('#booking-form', root);
  const slotsBox = $('#slots', form);
  async function loadSlots() {
    mount(slotsBox, html`<p class="muted">Loading free slots…</p>`);
    try {
      const { slots } = await api.get(`/api/advocates/${form.advocateId.value}/slots`);
      if (isCurrent()) mount(slotsBox, slotPicker(slots));
    } catch (error) {
      mount(slotsBox, html`<p class="field-error">${error.message}</p>`);
    }
  }
  form.addEventListener('change', event => { if (event.target.name === 'advocateId') loadSlots(); });
  form.addEventListener('submit', event => {
    event.preventDefault();
    submitting(form, async () => {
      const slot = form.querySelector('input[name="slotStart"]:checked')?.value || '';
      try {
        const booking = await api.post('/api/consultations', { propertyId: property.id, advocateId: Number(form.advocateId.value), slotStart: slot });
        toast('Request sent. The advocate will accept or refuse it.');
        navigate(`/consultations/${booking.id}`);
      } catch (error) {
        if (error.status === 409) loadSlots();  // someone else took the slot: show what is still free
        throw error;
      }
    });
  });
  if (advocates.length) await loadSlots();
  else mount(slotsBox, html`<p class="muted">No advocate is available right now.</p>`);
}

// ------------------------------------------------------------------ notifications (PB-25)

export async function renderNotifications({ root, navigate }) {
  const { notifications, unread } = await api.get('/api/notifications');
  mount(root, html`
    <div class="page-head"><div><h1>Notifications</h1><p>${unread ? `${unread} unread` : 'You have read everything.'}</p></div>
      ${unread ? html`<button class="btn btn-outline" type="button" id="read-all">Mark all as read</button>` : ''}</div>
    ${notifications.length ? html`<div class="panel notification-list">
      ${notifications.map(note => html`
        <button type="button" class="notification ${note.isRead ? '' : 'unread'}" data-id="${note.id}" data-link="${note.link || ''}">
          <span class="dot" aria-hidden="true"></span>
          <span class="notification-text"><strong>${note.title}</strong>${note.body ? html`<span>${note.body}</span>` : ''}
            <small>${formatDate(note.createdAt, true)}${note.isRead ? '' : ' · unread'}</small></span>
        </button>`)}
    </div>` : html`<div class="empty"><h3>No notifications yet</h3><p>Verification results, consultation requests and replies will appear here.</p></div>`}`);

  $('#read-all', root)?.addEventListener('click', async () => {
    await api.post('/api/notifications/read', { all: true });
    updateBell();
    navigate('/notifications');
  });
  root.addEventListener('click', async event => {
    const note = event.target.closest('.notification');
    if (!note) return;
    try {
      await api.post('/api/notifications/read', { id: Number(note.dataset.id) });
    } catch (error) {
      toast(error.message, true);
    }
    updateBell();
    navigate(note.dataset.link || '/notifications');
  });
}
