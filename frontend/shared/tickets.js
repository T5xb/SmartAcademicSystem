/* ==========================================================
   Academic AI - Advising tickets (student pages)
   A header button opens a dialog over the page:
     home -> "Open a new ticket" form | "My tickets" list -> conversation
   Every step has Back. Needs shared/auth.js (Auth.api).
   Pages call Tickets.mount(user) once the user is known.
   ========================================================== */

const Tickets = (() => {
  /* ---------- strings (shared by four pages, so they live here) ---------- */
  I18n.add({
    en: {
      'tickets.fab': 'Advising tickets',
      'tickets.homeTitle': 'Advising tickets',
      'tickets.homeSub': "Contact academic advising about something the chatbot couldn't solve.",
      'tickets.newChoice': 'Open a new ticket',
      'tickets.newDesc': 'Describe your problem and chat with an academic advisor.',
      'tickets.myTickets': 'My tickets',
      'tickets.myDesc': '{n} in total, {open} open',
      'tickets.seeDesc': 'See your open and closed tickets.',
      'tickets.unreadCount': '{n} new',
      'tickets.unreadTitle': 'New replies',
      'tickets.note': "Advisors usually reply within working hours. You'll see their replies here.",
      'tickets.newTitle': 'New ticket',
      'tickets.sentAs': 'Sent as {name} ({username})',
      'tickets.problemTitle': 'Problem title',
      'tickets.titlePh': 'e.g. Adding a course after the add/drop week',
      'tickets.problemLabel': 'Your problem or request',
      'tickets.messagePh': 'Explain what happened or what you need.',
      'tickets.hint': 'An academic advisor will reply here, and you can keep chatting in the ticket.',
      'tickets.back': 'Back',
      'tickets.close': 'Close',
      'tickets.openTicket': 'Open ticket',
      'tickets.opening': 'Opening...',
      'tickets.errTitle': 'Write a short title for your problem.',
      'tickets.errMessage': 'Describe your problem in a few words (at least 10 characters).',
      'tickets.loadingList': 'Loading your tickets...',
      'tickets.listFail': "Couldn't load your tickets",
      'tickets.countOne': '1 ticket',
      'tickets.countMany': '{n} tickets',
      'tickets.none': 'No tickets yet',
      'tickets.noneHint': 'Open a new ticket to contact academic advising.',
      'tickets.newReply': 'New reply',
      'tickets.opened': 'Opened {date}',
      'tickets.you': 'You',
      'tickets.admin': 'Admin',
      'tickets.advisor': 'Academic advisor',
      'tickets.ticketOpened': 'Ticket opened {date}',
      'tickets.firstMsg': 'Write your first message below: explain your problem in detail.',
      'tickets.closedByOn': 'Closed by {by} on {date}',
      'tickets.closedOn': 'Closed on {date}',
      'tickets.loading': 'Loading...',
      'tickets.loadingConv': 'Loading the conversation...',
      'tickets.ticket': 'Ticket',
      'tickets.openFail': "Couldn't open this ticket",
      'tickets.closedNote': "This ticket is closed, so you can't send more messages. Open a new ticket if you still need help.",
      'tickets.message': 'Message',
      'tickets.writePh': 'Write a message to academic advising...',
      'tickets.send': 'Send',
    },
    ar: {
      'tickets.fab': 'تذاكر الإرشاد الأكاديمي',
      'tickets.homeTitle': 'تذاكر الإرشاد الأكاديمي',
      'tickets.homeSub': 'تواصل مع الإرشاد الأكاديمي بشأن أمر لم يستطع المساعد الذكي حلّه.',
      'tickets.newChoice': 'فتح تذكرة جديدة',
      'tickets.newDesc': 'اشرح مشكلتك وتحدّث مع المرشد الأكاديمي.',
      'tickets.myTickets': 'تذاكري',
      'tickets.myDesc': 'الإجمالي {n}، المفتوحة {open}',
      'tickets.seeDesc': 'اطّلع على تذاكرك المفتوحة والمعالَجة.',
      'tickets.unreadCount': '{n} جديدة',
      'tickets.unreadTitle': 'ردود جديدة',
      'tickets.note': 'يرد المرشدون عادةً خلال ساعات العمل. ستظهر ردودهم هنا.',
      'tickets.newTitle': 'تذكرة جديدة',
      'tickets.sentAs': 'أُرسلت باسم {name} ({username})',
      'tickets.problemTitle': 'عنوان المشكلة',
      'tickets.titlePh': 'مثال: إضافة مقرر بعد أسبوع الحذف والإضافة',
      'tickets.problemLabel': 'مشكلتك أو طلبك',
      'tickets.messagePh': 'اشرح ما حدث أو ما تحتاجه.',
      'tickets.hint': 'سيرد عليك مرشد أكاديمي هنا، ويمكنك متابعة المحادثة داخل التذكرة.',
      'tickets.back': 'رجوع',
      'tickets.close': 'إغلاق',
      'tickets.openTicket': 'فتح التذكرة',
      'tickets.opening': 'جارٍ الفتح...',
      'tickets.errTitle': 'اكتب عنوانًا قصيرًا لمشكلتك.',
      'tickets.errMessage': 'صِف مشكلتك بكلمات قليلة (10 أحرف على الأقل).',
      'tickets.loadingList': 'جارٍ تحميل تذاكرك...',
      'tickets.listFail': 'تعذّر تحميل تذاكرك',
      'tickets.countOne': 'تذكرة واحدة',
      'tickets.countMany': '{n} تذاكر',
      'tickets.none': 'لا توجد تذاكر بعد',
      'tickets.noneHint': 'افتح تذكرة جديدة للتواصل مع الإرشاد الأكاديمي.',
      'tickets.newReply': 'رد جديد',
      'tickets.opened': 'فُتحت في {date}',
      'tickets.you': 'أنت',
      'tickets.admin': 'مدير النظام',
      'tickets.advisor': 'المرشد الأكاديمي',
      'tickets.ticketOpened': 'فُتحت التذكرة في {date}',
      'tickets.firstMsg': 'اكتب رسالتك الأولى أدناه واشرح مشكلتك بالتفصيل.',
      'tickets.closedByOn': 'أُغلقت بواسطة {by} في {date}',
      'tickets.closedOn': 'أُغلقت في {date}',
      'tickets.loading': 'جارٍ التحميل...',
      'tickets.loadingConv': 'جارٍ تحميل المحادثة...',
      'tickets.ticket': 'التذكرة',
      'tickets.openFail': 'تعذّر فتح هذه التذكرة',
      'tickets.closedNote': 'هذه التذكرة مغلقة، لذا لا يمكنك إرسال رسائل أخرى. افتح تذكرة جديدة إن كنت لا تزال بحاجة إلى مساعدة.',
      'tickets.message': 'الرسالة',
      'tickets.writePh': 'اكتب رسالة إلى الإرشاد الأكاديمي...',
      'tickets.send': 'إرسال',
    },
  });
  const t = (key, vars) => I18n.t(key, vars);

  const POLL_MS = 5000;         // refresh an open conversation
  const BADGE_POLL_MS = 60000;  // refresh the unread badge

  const ICON = {
    ticket: '<svg fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" viewBox="0 0 24 24"><path d="M3 7a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v3a2 2 0 0 0 0 4v3a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-3a2 2 0 0 0 0-4z"></path><path d="M13 5v2M13 11v2M13 17v2"></path></svg>',
    plus: '<svg fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" viewBox="0 0 24 24"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>',
    list: '<svg fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" viewBox="0 0 24 24"><line x1="8" y1="6" x2="21" y2="6"></line><line x1="8" y1="12" x2="21" y2="12"></line><line x1="8" y1="18" x2="21" y2="18"></line><line x1="3" y1="6" x2="3.01" y2="6"></line><line x1="3" y1="12" x2="3.01" y2="12"></line><line x1="3" y1="18" x2="3.01" y2="18"></line></svg>',
    back: '<svg class="flip-rtl" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" viewBox="0 0 24 24"><path d="M15 19l-7-7 7-7"></path></svg>',
    close: '<svg fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>',
    send: '<svg class="flip-rtl" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" viewBox="0 0 24 24" width="16" height="16"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>',
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
  const when = (iso) => I18n.dateTime(iso);
  const statusLabel = (s) => {
    const key = `status.${s}`;
    const text = t(key);
    return text === key ? s : text;
  };
  const statusBadge = (s) => `<span class="tk-status tk-status--${esc(s)}">${esc(statusLabel(s))}</span>`;
  const current = () => stack[stack.length - 1];

  /* ---------- header button + unread badge ---------- */
  function mount(me) {
    // Tickets are for students; advisors answer them on the advisor page.
    if (!me || me.role !== 'student') return;
    user = me;
    if (document.querySelector('.tk-trigger')) return;
    // A small round button fixed at the bottom-right of every student page.
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'tk-trigger tk-fab';
    btn.title = t('tickets.fab');
    btn.setAttribute('aria-label', t('tickets.fab'));
    btn.innerHTML = `${ICON.ticket}<span class="tk-trigger__badge" hidden></span>`;
    btn.addEventListener('click', () => (root ? close() : open()));
    // On the chat page it sits above the message box, not over its send button.
    if (document.querySelector('.composer')) document.body.classList.add('tk-raised');
    // On the schedule page in Arabic the sidebar (with its Generate button) is on the right.
    if (document.querySelector('#generate-btn')) document.body.classList.add('tk-raised-low');
    document.body.appendChild(btn);
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

  // Re-renders the open dialog in the new language, keeping what was typed.
  function onLanguage() {
    const btn = document.querySelector('.tk-trigger');
    if (btn) {
      btn.title = t('tickets.fab');
      btn.setAttribute('aria-label', t('tickets.fab'));
    }
    if (!root) return;
    const v = current();
    if (v.view === 'new') {
      const form = root.querySelector('[data-tk-form="new"]');
      if (form) Object.assign(v, { title: form.elements.title.value, message: form.elements.message.value });
    }
    if (v.view === 'chat' && v.ticket) {
      const draft = root.querySelector('#tk-message')?.value || '';
      showChat(v, { ticket: v.ticket, messages: v.messages || [] });
      const box = root.querySelector('#tk-message');
      if (box) box.value = draft;
      return;
    }
    render(false);
  }
  I18n.onChange(onLanguage);

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
        ${canGoBack ? `<button type="button" class="tk-icon-btn" data-tk-back aria-label="${esc(t('tickets.back'))}">${ICON.back}</button>` : ''}
        <div class="tk-head__text">
          <h2 class="tk-title" id="tk-title" dir="auto">${title}</h2>
          ${sub ? `<p class="tk-sub" dir="auto">${sub}</p>` : ''}
        </div>
        <button type="button" class="tk-icon-btn" data-tk-close aria-label="${esc(t('tickets.close'))}">${ICON.close}</button>
      </div>
      <div class="tk-body${chat ? ' tk-body--chat' : ''}">${body}</div>
      ${footer}`;
  }

  function render(refocus = true) {
    stopPolling();
    const v = current();
    if (v.view === 'home') renderHome();
    else if (v.view === 'new') renderNew(v);
    else if (v.view === 'list') renderList();
    else if (v.view === 'chat') renderChat(v);
    if (!refocus) return;
    const first = root.querySelector('.tk-body [autofocus], .tk-body button, .tk-body input, .tk-composer textarea');
    if (first) first.focus();
  }

  function renderHome() {
    const open = tickets.filter((t) => t.status !== 'closed').length;
    const unread = tickets.filter((t) => t.unread).length;
    frame({
      title: esc(t('tickets.homeTitle')),
      sub: esc(t('tickets.homeSub')),
      body: `
        <div class="tk-choices">
          <button type="button" class="tk-choice" data-tk-go="new">
            <span class="tk-choice__icon">${ICON.plus}</span>
            <span class="tk-choice__text">
              <span class="tk-choice__title">${esc(t('tickets.newChoice'))}</span>
              <span class="tk-choice__desc">${esc(t('tickets.newDesc'))}</span>
            </span>
          </button>
          <button type="button" class="tk-choice" data-tk-go="list">
            <span class="tk-choice__icon">${ICON.list}</span>
            <span class="tk-choice__text">
              <span class="tk-choice__title">${esc(t('tickets.myTickets'))}</span>
              <span class="tk-choice__desc">${esc(tickets.length ? t('tickets.myDesc', { n: tickets.length, open }) : t('tickets.seeDesc'))}</span>
            </span>
            ${unread ? `<span class="tk-choice__count is-unread" title="${esc(t('tickets.unreadTitle'))}">${esc(t('tickets.unreadCount', { n: unread }))}</span>`
              : tickets.length ? `<span class="tk-choice__count">${tickets.length}</span>` : ''}
          </button>
        </div>
        <p class="tk-note">${esc(t('tickets.note'))}</p>`,
    });
  }

  function renderNew(v) {
    frame({
      title: esc(t('tickets.newTitle')),
      sub: user ? t('tickets.sentAs', { name: `<bdi>${esc(user.name)}</bdi>`, username: `<bdi>${esc(user.username)}</bdi>` }) : '',
      body: `
        <form class="tk-form" data-tk-form="new" novalidate>
          <div class="tk-field">
            <label class="tk-label" for="tk-title-input">${esc(t('tickets.problemTitle'))}</label>
            <input class="tk-input" id="tk-title-input" name="title" dir="auto" maxlength="150"
                   value="${esc(v.title ?? '')}" placeholder="${esc(t('tickets.titlePh'))}" autofocus>
          </div>
          <div class="tk-field">
            <label class="tk-label" for="tk-message">${esc(t('tickets.problemLabel'))}</label>
            <textarea class="tk-input tk-textarea" id="tk-message" name="message" dir="auto" maxlength="2000" rows="5"
                      placeholder="${esc(t('tickets.messagePh'))}">${esc(v.message ?? '')}</textarea>
            <span class="tk-hint">${esc(t('tickets.hint'))}</span>
          </div>
          <p class="tk-error" role="alert"></p>
          <div class="tk-actions">
            <button type="button" class="tk-btn tk-btn--ghost" data-tk-back>${esc(t('tickets.back'))}</button>
            <button type="submit" class="tk-btn tk-btn--primary">${esc(t('tickets.openTicket'))}</button>
          </div>
        </form>`,
    });
  }

  async function renderList() {
    frame({ title: esc(t('tickets.myTickets')), body: `<div class="tk-loading">${esc(t('tickets.loadingList'))}</div>` });
    try {
      await loadTickets();
    } catch (err) {
      if (current().view !== 'list') return;
      frame({ title: esc(t('tickets.myTickets')), body: `<div class="tk-empty"><strong>${esc(t('tickets.listFail'))}</strong>${esc(err.message)}</div>` });
      return;
    }
    if (!root || current().view !== 'list') return;
    frame({
      title: esc(t('tickets.myTickets')),
      sub: tickets.length ? esc(tickets.length === 1 ? t('tickets.countOne') : t('tickets.countMany', { n: tickets.length })) : '',
      body: tickets.length
        ? `<ul class="tk-list">${tickets.map((tk) => `
            <li>
              <button type="button" class="tk-item" data-tk-ticket="${esc(tk.id)}">
                <span class="tk-item__code">${esc(tk.code)}</span>
                ${statusBadge(tk.status)}
                <span class="tk-item__title" dir="auto">${esc(tk.title)}</span>
                <span class="tk-item__meta">
                  ${tk.unread ? '<span class="tk-dot" title="' + esc(t('tickets.newReply')) + '"></span>' : ''}
                  <span>${esc(t('tickets.opened', { date: when(tk.created_at) }))}</span>
                </span>
              </button>
            </li>`).join('')}</ul>`
        : `<div class="tk-empty"><strong>${esc(t('tickets.none'))}</strong>${esc(t('tickets.noneHint'))}
             <div style="margin-top:14px"><button type="button" class="tk-btn tk-btn--primary" data-tk-go="new">${ICON.plus} ${esc(t('tickets.newChoice'))}</button></div></div>`,
    });
  }

  function messageHtml(m) {
    const mine = m.sender_id === (user && user.id);
    const role = m.sender_role === 'student' ? '' : ` · ${t(m.sender_role === 'admin' ? 'tickets.admin' : 'tickets.advisor')}`;
    return `
      <div class="tk-msg ${mine ? 'tk-msg--mine' : 'tk-msg--staff'}">
        <div class="tk-msg__meta">
          <span class="tk-msg__who" dir="auto">${mine ? esc(t('tickets.you')) : `<bdi>${esc(m.sender_name)}</bdi>` + esc(role)}</span>
          <span>${esc(when(m.created_at))}</span>
        </div>
        <div class="tk-msg__bubble" dir="auto">${esc(m.body)}</div>
      </div>`;
  }

  function chatBody(ticket, messages) {
    const opened = `<div class="tk-system">${esc(t('tickets.ticketOpened', { date: when(ticket.created_at) }))}</div>`;
    const empty = messages.length ? '' : `<div class="tk-system">${esc(t('tickets.firstMsg'))}</div>`;
    const closed = ticket.status === 'closed'
      ? `<div class="tk-system">${ticket.closed_by
        ? t('tickets.closedByOn', { by: `<bdi>${esc(ticket.closed_by)}</bdi>`, date: esc(when(ticket.closed_at)) })
        : t('tickets.closedOn', { date: esc(when(ticket.closed_at)) })}</div>`
      : '';
    return opened + messages.map(messageHtml).join('') + empty + closed;
  }

  async function renderChat(v) {
    frame({ title: esc(t('tickets.loading')), body: `<div class="tk-loading">${esc(t('tickets.loadingConv'))}</div>`, chat: true });
    let data;
    try {
      data = await Auth.api(`/api/tickets/${encodeURIComponent(v.id)}`);
    } catch (err) {
      if (!root || current() !== v) return;
      frame({ title: esc(t('tickets.ticket')), body: `<div class="tk-empty"><strong>${esc(t('tickets.openFail'))}</strong>${esc(err.message)}</div>` });
      return;
    }
    if (!root || current() !== v) return;
    showChat(v, data);
    startPolling(v);
  }

  function showChat(v, { ticket, messages }) {
    v.ticket = ticket;
    v.count = messages.length;
    v.messages = messages;
    const closed = ticket.status === 'closed';
    frame({
      title: `${esc(ticket.code)} · <bdi>${esc(ticket.title)}</bdi>`,
      sub: `${esc(statusLabel(ticket.status))} · <bdi>${esc(ticket.full_name)}</bdi> (${esc(ticket.university_id)})`,
      body: chatBody(ticket, messages),
      chat: true,
      footer: closed
        ? `<div class="tk-closed-note">${esc(t('tickets.closedNote'))}</div>`
        : `<form class="tk-composer" data-tk-form="message">
             <label class="tk-label" for="tk-message" style="position:absolute;left:-9999px">${esc(t('tickets.message'))}</label>
             <textarea class="tk-textarea" id="tk-message" name="body" rows="1" maxlength="2000" dir="auto"
                       placeholder="${esc(t('tickets.writePh'))}"></textarea>
             <button type="submit" class="tk-btn tk-btn--primary" aria-label="${esc(t('tickets.send'))}">${ICON.send}</button>
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
          v.messages = data.messages;
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
    go('new', { ...prefill });
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
    const title = form.elements.title.value.trim();
    const message = form.elements.message.value.trim();
    // Keep what was typed if the student goes back and forth.
    Object.assign(current(), { title, message });
    if (title.length < 3) return fieldError(form, 'title', t('tickets.errTitle'));
    if (message.length < 10) return fieldError(form, 'message', t('tickets.errMessage'));

    const submit = form.querySelector('[type="submit"]');
    submit.disabled = true;
    submit.textContent = t('tickets.opening');
    try {
      const body = { title, message };
      const data = await Auth.api('/api/tickets', { method: 'POST', body });
      tickets = [data.ticket, ...tickets];
      // Back from the new conversation goes to the ticket list, not the form.
      stack = [{ view: 'home' }, { view: 'list' }, { view: 'chat', id: data.ticket.id }];
      render();
    } catch (err) {
      form.querySelector('.tk-error').textContent = err.message;
      submit.disabled = false;
      submit.textContent = t('tickets.openTicket');
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
        v.messages = data.messages;
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
      open('new', { ...prefill });
    },
  };
})();
