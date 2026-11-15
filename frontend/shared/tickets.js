/* ==========================================================
   Academic AI - Advising tickets (student pages)
   A header button opens a dialog over the page:
     home -> "Open a new ticket" form | "My tickets" list -> conversation
   Every step has Back. Needs shared/auth.js (Auth.api).
   Pages call Tickets.mount(user) once the user is known.
   ========================================================== */

const Tickets = (() => {
  const POLL_MS = 5000;         // refresh an open conversation
  const BADGE_POLL_MS = 60000;  // refresh the unread badge
  const STATUS_LABEL = { new: 'New', in_progress: 'In progress', closed: 'Closed' };

  const ICON = {
    ticket: '<svg fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" viewBox="0 0 24 24"><path d="M3 7a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v3a2 2 0 0 0 0 4v3a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-3a2 2 0 0 0 0-4z"></path><path d="M13 5v2M13 11v2M13 17v2"></path></svg>',
    plus: '<svg fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" viewBox="0 0 24 24"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>',
    list: '<svg fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" viewBox="0 0 24 24"><line x1="8" y1="6" x2="21" y2="6"></line><line x1="8" y1="12" x2="21" y2="12"></line><line x1="8" y1="18" x2="21" y2="18"></line><line x1="3" y1="6" x2="3.01" y2="6"></line><line x1="3" y1="12" x2="3.01" y2="12"></line><line x1="3" y1="18" x2="3.01" y2="18"></line></svg>',
    back: '<svg fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" viewBox="0 0 24 24"><path d="M15 19l-7-7 7-7"></path></svg>',
    close: '<svg fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>',
    send: '<svg fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" viewBox="0 0 24 24" width="16" height="16"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>',
  };

  let user = null;
  let root = null;
  let stack = [];          // views, newest last: { view, ...data }
  let tickets = [];        // the student's tickets, newest first
  let pollTimer = null;
  let badgeTimer = null;
  let lastFocus = null;

  /* ---------- helpers ---------- */
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
  const when = (iso) => {
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? '' : d.toLocaleString('en-GB', {
      day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
    });
  };
  const statusBadge = (s) => `<span class="tk-status tk-status--${esc(s)}">${esc(STATUS_LABEL[s] || s)}</span>`;
  const current = () => stack[stack.length - 1];

  /* ---------- header button + unread badge ---------- */
  function mount(me) {
    // Tickets are for students; advisors answer them on the advisor page.
    if (!me || me.role !== 'student') return;
    user = me;
    const actions = document.querySelector('.icon-actions');
    if (!actions || document.querySelector('.tk-trigger')) return;
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'icon-btn tk-trigger';
    btn.title = 'Advising tickets';
    btn.setAttribute('aria-label', 'Advising tickets');
    btn.innerHTML = `${ICON.ticket}<span class="tk-trigger__badge" hidden></span>`;
    btn.addEventListener('click', () => open());
    actions.prepend(btn);
    refreshBadge();
    badgeTimer = setInterval(() => { if (!root && document.visibilityState === 'visible') refreshBadge(); }, BADGE_POLL_MS);
  }

  async function loadTickets() {
    const data = await Auth.api('/api/tickets');
    tickets = data.tickets || [];
    setBadge(data.unread || 0);
    return tickets;
  }

  async function refreshBadge() {
    try { await loadTickets(); } catch { /* the badge is optional */ }
  }

  function setBadge(n) {
    const badge = document.querySelector('.tk-trigger__badge');
    if (!badge) return;
    badge.hidden = !n;
    badge.textContent = n > 9 ? '9+' : String(n);
  }

  /* ---------- open / close / navigate ---------- */
  function open(view = 'home', data = {}) {
    if (!root) {
      lastFocus = document.activeElement;
      root = document.createElement('div');
      root.className = 'tk-root';
      root.innerHTML = '<div class="tk-backdrop" data-tk-close></div><div class="tk-dialog" role="dialog" aria-modal="true" aria-labelledby="tk-title"></div>';
      document.body.appendChild(root);
      document.body.style.overflow = 'hidden';
      root.addEventListener('click', onClick);
      root.addEventListener('submit', onSubmit);
      root.addEventListener('keydown', onKey);
    }
    stack = view === 'home' ? [{ view: 'home' }] : [{ view: 'home' }, { view, ...data }];
    render();
  }

  function close() {
    stopPolling();
    if (!root) return;
    root.remove();
    root = null;
    stack = [];
    document.body.style.overflow = '';
    if (lastFocus && lastFocus.focus) lastFocus.focus();
    refreshBadge();
  }

  function go(view, data = {}) {
    stack.push({ view, ...data });
    render();
  }

  function back() {
    if (stack.length > 1) stack.pop();
    render();
  }

  /* ---------- rendering ---------- */
  function frame({ title, sub = '', body, footer = '', chat = false }) {
    const canGoBack = stack.length > 1;
    const dialog = root.querySelector('.tk-dialog');
    dialog.classList.toggle('is-tall', chat || current().view === 'list');
    dialog.innerHTML = `
      <div class="tk-head">
        ${canGoBack ? `<button type="button" class="tk-icon-btn" data-tk-back aria-label="Back">${ICON.back}</button>` : ''}
        <div class="tk-head__text">
          <h2 class="tk-title" id="tk-title" dir="auto">${title}</h2>
          ${sub ? `<p class="tk-sub" dir="auto">${sub}</p>` : ''}
        </div>
        <button type="button" class="tk-icon-btn" data-tk-close aria-label="Close">${ICON.close}</button>
      </div>
      <div class="tk-body${chat ? ' tk-body--chat' : ''}">${body}</div>
      ${footer}`;
  }

  function render() {
    stopPolling();
    const v = current();
    if (v.view === 'home') renderHome();
    else if (v.view === 'new') renderNew(v);
    else if (v.view === 'list') renderList();
    else if (v.view === 'chat') renderChat(v);
    const first = root.querySelector('.tk-body [autofocus], .tk-body button, .tk-body input, .tk-composer textarea');
    if (first) first.focus();
  }

  function renderHome() {
    const open = tickets.filter((t) => t.status !== 'closed').length;
    const unread = tickets.filter((t) => t.unread).length;
    frame({
      title: 'Advising tickets',
      sub: 'Contact academic advising about something the chatbot couldn\'t solve.',
      body: `
        <div class="tk-choices">
          <button type="button" class="tk-choice" data-tk-go="new">
            <span class="tk-choice__icon">${ICON.plus}</span>
            <span class="tk-choice__text">
              <span class="tk-choice__title">Open a new ticket</span>
              <span class="tk-choice__desc">Describe your problem and chat with an academic advisor.</span>
            </span>
          </button>
          <button type="button" class="tk-choice" data-tk-go="list">
            <span class="tk-choice__icon">${ICON.list}</span>
            <span class="tk-choice__text">
              <span class="tk-choice__title">My tickets</span>
              <span class="tk-choice__desc">${tickets.length ? `${tickets.length} in total, ${open} open` : 'See your open and closed tickets.'}</span>
            </span>
            ${unread ? `<span class="tk-choice__count is-unread" title="New replies">${unread} new</span>`
              : tickets.length ? `<span class="tk-choice__count">${tickets.length}</span>` : ''}
          </button>
        </div>
        <p class="tk-note">Advisors usually reply within working hours. You'll see their replies here.</p>`,
    });
  }

  function renderNew(v) {
    frame({
      title: 'New ticket',
      sub: 'All fields are required.',
      body: `
        <form class="tk-form" data-tk-form="new" novalidate>
          <div class="tk-field">
            <label class="tk-label" for="tk-name">Full name (three parts)</label>
            <input class="tk-input" id="tk-name" name="full_name" dir="auto" maxlength="120" autocomplete="name"
                   value="${esc(v.full_name ?? '')}" placeholder="First, father's and family name" autofocus>
          </div>
          <div class="tk-field">
            <label class="tk-label" for="tk-id">University ID</label>
            <input class="tk-input" id="tk-id" name="university_id" inputmode="numeric" maxlength="12"
                   value="${esc(v.university_id ?? (user ? user.username : ''))}" placeholder="e.g. 441000001">
          </div>
          <div class="tk-field">
            <label class="tk-label" for="tk-title-input">Problem title</label>
            <input class="tk-input" id="tk-title-input" name="title" dir="auto" maxlength="150"
                   value="${esc(v.title ?? '')}" placeholder="e.g. Adding a course after the add/drop week">
            <span class="tk-hint">You can explain the details in the chat after opening the ticket.</span>
          </div>
          ${v.message ? `<input type="hidden" name="message" value="${esc(v.message)}">` : ''}
          <p class="tk-error" role="alert"></p>
          <div class="tk-actions">
            <button type="button" class="tk-btn tk-btn--ghost" data-tk-back>Back</button>
            <button type="submit" class="tk-btn tk-btn--primary">Open ticket</button>
          </div>
        </form>`,
    });
  }

  async function renderList() {
    frame({ title: 'My tickets', body: '<div class="tk-loading">Loading your tickets...</div>' });
    try {
      await loadTickets();
    } catch (err) {
      if (current().view !== 'list') return;
      frame({ title: 'My tickets', body: `<div class="tk-empty"><strong>Couldn't load your tickets</strong>${esc(err.message)}</div>` });
      return;
    }
    if (!root || current().view !== 'list') return;
    frame({
      title: 'My tickets',
      sub: tickets.length ? `${tickets.length} ticket${tickets.length === 1 ? '' : 's'}` : '',
      body: tickets.length
        ? `<ul class="tk-list">${tickets.map((t) => `
            <li>
              <button type="button" class="tk-item" data-tk-ticket="${esc(t.id)}">
                <span class="tk-item__code">${esc(t.code)}</span>
                ${statusBadge(t.status)}
                <span class="tk-item__title" dir="auto">${esc(t.title)}</span>
                <span class="tk-item__meta">
                  ${t.unread ? '<span class="tk-dot" title="New reply"></span>' : ''}
                  <span>Opened ${esc(when(t.created_at))}</span>
                </span>
              </button>
            </li>`).join('')}</ul>`
        : `<div class="tk-empty"><strong>No tickets yet</strong>Open a new ticket to contact academic advising.
             <div style="margin-top:14px"><button type="button" class="tk-btn tk-btn--primary" data-tk-go="new">${ICON.plus} Open a new ticket</button></div></div>`,
    });
  }

  function messageHtml(m) {
    const mine = m.sender_id === (user && user.id);
    const role = m.sender_role === 'student' ? '' : ` · ${m.sender_role === 'admin' ? 'Admin' : 'Academic advisor'}`;
    return `
      <div class="tk-msg ${mine ? 'tk-msg--mine' : 'tk-msg--staff'}">
        <div class="tk-msg__meta">
          <span class="tk-msg__who" dir="auto">${mine ? 'You' : esc(m.sender_name) + role}</span>
          <span>${esc(when(m.created_at))}</span>
        </div>
        <div class="tk-msg__bubble" dir="auto">${esc(m.body)}</div>
      </div>`;
  }

  function chatBody(ticket, messages) {
    const opened = `<div class="tk-system">Ticket opened ${esc(when(ticket.created_at))}</div>`;
    const empty = messages.length ? '' : '<div class="tk-system">Write your first message below: explain your problem in detail.</div>';
    const closed = ticket.status === 'closed'
      ? `<div class="tk-system">Closed${ticket.closed_by ? ` by ${esc(ticket.closed_by)}` : ''} on ${esc(when(ticket.closed_at))}</div>`
      : '';
    return opened + messages.map(messageHtml).join('') + empty + closed;
  }

  async function renderChat(v) {
    frame({ title: 'Loading...', body: '<div class="tk-loading">Loading the conversation...</div>', chat: true });
    let data;
    try {
      data = await Auth.api(`/api/tickets/${encodeURIComponent(v.id)}`);
    } catch (err) {
      if (!root || current() !== v) return;
      frame({ title: 'Ticket', body: `<div class="tk-empty"><strong>Couldn't open this ticket</strong>${esc(err.message)}</div>` });
      return;
    }
    if (!root || current() !== v) return;
    showChat(v, data);
    startPolling(v);
  }

  function showChat(v, { ticket, messages }) {
    v.ticket = ticket;
    v.count = messages.length;
    const closed = ticket.status === 'closed';
    frame({
      title: `${esc(ticket.code)} · ${esc(ticket.title)}`,
      sub: `${STATUS_LABEL[ticket.status] || ticket.status} · ${esc(ticket.full_name)} (${esc(ticket.university_id)})`,
      body: chatBody(ticket, messages),
      chat: true,
      footer: closed
        ? '<div class="tk-closed-note">This ticket is closed, so you can\'t send more messages. Open a new ticket if you still need help.</div>'
        : `<form class="tk-composer" data-tk-form="message">
             <label class="tk-label" for="tk-message" style="position:absolute;left:-9999px">Message</label>
             <textarea class="tk-textarea" id="tk-message" name="body" rows="1" maxlength="2000" dir="auto"
                       placeholder="Write a message to academic advising..."></textarea>
             <button type="submit" class="tk-btn tk-btn--primary" aria-label="Send">${ICON.send}</button>
           </form>`,
    });
    scrollToEnd();
  }

  function scrollToEnd() {
    const body = root && root.querySelector('.tk-body');
    if (body) body.scrollTop = body.scrollHeight;
  }

  /* Keeps the conversation current while it is open, without touching what
     the student is typing. */
  function startPolling(v) {
    stopPolling();
    pollTimer = setInterval(async () => {
      if (!root || current() !== v || document.visibilityState !== 'visible') return;
      try {
        const data = await Auth.api(`/api/tickets/${encodeURIComponent(v.id)}`);
        if (!root || current() !== v) return;
        const statusChanged = data.ticket.status !== v.ticket.status;
        if (data.messages.length === v.count && !statusChanged) return;
        if (statusChanged) {
          const draft = root.querySelector('#tk-message')?.value || '';
          showChat(v, data);
          const box = root.querySelector('#tk-message');
          if (box) box.value = draft;
        } else {
          v.count = data.messages.length;
          root.querySelector('.tk-body').innerHTML = chatBody(data.ticket, data.messages);
          scrollToEnd();
        }
      } catch { /* try again on the next tick */ }
    }, POLL_MS);
  }

  function stopPolling() {
    clearInterval(pollTimer);
    pollTimer = null;
  }

  /* ---------- events ---------- */
  function onClick(e) {
    if (e.target.closest('[data-tk-close]')) return close();
    if (e.target.closest('[data-tk-back]')) return back();
    const target = e.target.closest('[data-tk-go]');
    if (target) return target.dataset.tkGo === 'new' ? goNew() : go(target.dataset.tkGo);
    const item = e.target.closest('[data-tk-ticket]');
    if (item) go('chat', { id: item.dataset.tkTicket });
  }

  function goNew(prefill = {}) {
    go('new', { full_name: user ? user.name : '', ...prefill });
  }

  function onKey(e) {
    if (e.key === 'Escape') {
      e.preventDefault();
      close();
    } else if (e.key === 'Enter' && !e.shiftKey && e.target.id === 'tk-message') {
      e.preventDefault();
      e.target.form.requestSubmit();
    }
  }

  function onSubmit(e) {
    e.preventDefault();
    const form = e.target;
    if (form.dataset.tkForm === 'new') submitNew(form);
    if (form.dataset.tkForm === 'message') submitMessage(form);
  }

  function fieldError(form, name, message) {
    const input = form.elements[name];
    if (input) {
      input.setAttribute('aria-invalid', 'true');
      input.focus();
    }
    form.querySelector('.tk-error').textContent = message;
  }

  async function submitNew(form) {
    form.querySelectorAll('[aria-invalid]').forEach((el) => el.removeAttribute('aria-invalid'));
    const fullName = form.elements.full_name.value.trim().replace(/\s+/g, ' ');
    const universityId = form.elements.university_id.value.trim();
    const title = form.elements.title.value.trim();
    // Keep what was typed if the student goes back and forth.
    Object.assign(current(), { full_name: fullName, university_id: universityId, title });
    if (fullName.split(' ').length < 3) return fieldError(form, 'full_name', 'Enter your full name: first, father\'s and family name.');
    if (!/^\d{6,12}$/.test(universityId)) return fieldError(form, 'university_id', 'Enter your university ID: 6 to 12 digits.');
    if (title.length < 3) return fieldError(form, 'title', 'Write a short title for your problem.');

    const submit = form.querySelector('[type="submit"]');
    submit.disabled = true;
    submit.textContent = 'Opening...';
    try {
      const body = { full_name: fullName, university_id: universityId, title };
      if (form.elements.message) body.message = form.elements.message.value;
      const data = await Auth.api('/api/tickets', { method: 'POST', body });
      tickets = [data.ticket, ...tickets];
      // Back from the new conversation goes to the ticket list, not the form.
      stack = [{ view: 'home' }, { view: 'list' }, { view: 'chat', id: data.ticket.id }];
      render();
    } catch (err) {
      form.querySelector('.tk-error').textContent = err.message;
      submit.disabled = false;
      submit.textContent = 'Open ticket';
    }
  }

  async function submitMessage(form) {
    const v = current();
    const box = form.elements.body;
    const text = box.value.trim();
    if (!text) return box.focus();
    const submit = form.querySelector('[type="submit"]');
    submit.disabled = true;
    try {
      await Auth.api(`/api/tickets/${encodeURIComponent(v.id)}/messages`, { method: 'POST', body: { body: text } });
      box.value = '';
      const data = await Auth.api(`/api/tickets/${encodeURIComponent(v.id)}`);
      if (root && current() === v) {
        v.count = data.messages.length;
        v.ticket = data.ticket;
        root.querySelector('.tk-body').innerHTML = chatBody(data.ticket, data.messages);
        scrollToEnd();
      }
    } catch (err) {
      // A ticket closed meanwhile: show its closed state.
      if (err.status === 409) return renderChat(v);
      alert(err.message);
    } finally {
      submit.disabled = false;
      box.focus();
    }
  }

  return {
    mount,
    open,
    /* Opens the new-ticket form, e.g. from the chatbot's ticket suggestion. */
    openNew(prefill = {}) {
      open('new', { full_name: user ? user.name : '', ...prefill });
    },
  };
})();
