/* ==========================================================
   Academic AI - Advisor page
   Tickets (dashboard, inbox, conversation) and students' academic profiles.
   Routes (location.hash):
     #overview                       dashboard
     #tickets/<filter>[/<ticket id>]  inbox; filter = all | new | in_progress | closed
     #students[/<student id>]         academic profiles
   ========================================================== */

const $ = (s) => document.querySelector(s);

/* ---------- Constants ---------- */
const FILTERS = ['all', 'new', 'in_progress', 'closed'];
const T = (key, vars) => I18n.t(key, vars);
const OVERVIEW_POLL_MS = 20000;
const LIST_POLL_MS = 15000;
const CHAT_POLL_MS = 5000;
const COLLAPSED_COUNT = 8;
const QUICK_REPLIES = [
  'السلام عليكم، تم استلام طلبك وجاري مراجعته، وسنعود إليك قريباً.',
  // The advisor already sees the student's academic record, so don't ask for it.
  'نرجو توضيح رمز المقرر أو رقم الشعبة لنتمكن من مساعدتك.',
  'تم تنفيذ طلبك بنجاح. هل هناك شيء آخر يمكننا مساعدتك فيه؟',
  'هذا الطلب يحتاج مراجعة من وكالة الكلية، تم تحويله وسنبلغك بالنتيجة.',
  'تم حل المشكلة، وسيتم إغلاق التذكرة. نتمنى لك التوفيق.',
];

/* ---------- State ---------- */
let me = null;
let counts = null;
let route = { view: 'overview' };
let inboxTickets = [];
let openTicket = null;      // { ticket, messages } shown in the chat pane
let chatToken = 0;          // ignores stale responses when clicking quickly
let timers = [];
let students = [];
let courseInfo = {};
let studentsLoaded = false;
let selectedStudent = null;
let detailToken = 0;
let overviewData = null;    // last dashboard payload, for re-rendering on language change
let overviewAt = null;      // when it was fetched
let selectedData = null;    // last student profile shown in the detail pane

/* ---------- Helpers ---------- */
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
));

const fmtGpa = (g) => (typeof g === 'number' ? g.toFixed(2) : null);

function fmtMinutes(m) {
  if (typeof m !== 'number') return '--:--';
  const h = String(Math.floor(m / 60) % 24).padStart(2, '0');
  return `${h}:${String(m % 60).padStart(2, '0')}`;
}

function fmtDate(iso) {
  return iso ? (I18n.dateTime(iso) || null) : null;
}

const ago = (iso) => (iso ? I18n.relative(iso) : '');

// Count with a unit word; Arabic has separate forms for 1, 2, 3-10 and 11+.
function plural(n, key) {
  let form = 'many';
  if (n === 1) form = 'one';
  else if (I18n.lang === 'ar') {
    if (n === 2) form = 'two';
    else if (n >= 3 && n <= 10) form = 'few';
  }
  return T(`${key}.${form}`, { n });
}

const statusLabel = (s) => (FILTERS.includes(s) && s !== 'all' ? T(`status.${s}`) : s);
const statusBadge = (s) => `<span class="status-badge status-badge--${esc(s)}">${esc(statusLabel(s))}</span>`;

let toastTimer;
function toast(message, error = false) {
  const el = $('#toast');
  el.textContent = message;
  el.classList.toggle('is-error', error);
  el.classList.add('is-visible');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('is-visible'), 2800);
}

function every(ms, fn) {
  timers.push(setInterval(() => { if (document.visibilityState === 'visible') fn(); }, ms));
}

function stopTimers() {
  timers.forEach(clearInterval);
  timers = [];
}

/* ==========================================================
   Sidebar counts
   ========================================================== */
function renderCounts() {
  if (!counts) return;
  document.querySelectorAll('[data-count]').forEach((el) => {
    const n = counts[el.dataset.count] ?? 0;
    el.textContent = n;
    el.hidden = false;
  });
}

function setActiveNav() {
  const key = route.view === 'tickets' ? route.filter : route.view;
  document.querySelectorAll('[data-nav]').forEach((a) => {
    const on = a.dataset.nav === key;
    a.classList.toggle('is-active', on);
    if (on) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  });
}

/* ==========================================================
   Dashboard
   ========================================================== */
const STAT_CARDS = [
  { key: 'all', label: 'advisor.filter.all', tone: '', icon: '<path d="M3 7a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v3a2 2 0 0 0 0 4v3a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-3a2 2 0 0 0 0-4z"></path>' },
  // No advisor reply yet.
  { key: 'new', label: 'advisor.stat.new', tone: 'new', icon: '<circle cx="12" cy="12" r="9"></circle><line x1="12" y1="8" x2="12" y2="16"></line><line x1="8" y1="12" x2="16" y2="12"></line>' },
  // An advisor replied, not closed yet.
  { key: 'in_progress', label: 'advisor.stat.in_progress', tone: 'progress', icon: '<circle cx="12" cy="12" r="9"></circle><polyline points="12 7 12 12 15 14"></polyline>' },
  { key: 'closed', label: 'status.closed', tone: 'closed', icon: '<circle cx="12" cy="12" r="9"></circle><polyline points="8 12 11 15 16 9"></polyline>' },
];

const COLUMNS = [
  { status: 'new', title: 'advisor.col.new', tone: 'new' },
  { status: 'in_progress', title: 'advisor.col.in_progress', tone: 'progress' },
  { status: 'closed', title: 'advisor.col.closed', tone: 'closed' },
];

function renderStats() {
  const values = counts;
  $('#stats').innerHTML = STAT_CARDS.map((c) => `
    <div class="stat stat--${c.tone || 'all'}">
      <div class="stat__top">
        <span class="stat__label">${esc(T(c.label))}</span>
        <span class="stat__icon"><svg fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" viewBox="0 0 24 24">${c.icon}</svg></span>
      </div>
      <span class="stat__value">${values[c.key] ?? 0}</span>
    </div>`).join('');
}

function boardCard(t) {
  const closed = t.status === 'closed';
  return `
    <li>
      <a class="board-card" href="#tickets/${t.status}/${encodeURIComponent(t.id)}">
        <span class="board-card__top">
          <span class="ticket-code">${esc(t.code)}</span>
          <span class="muted board-card__time">${esc(ago(closed ? t.closed_at : t.updated_at))}</span>
        </span>
        <span class="board-card__title" dir="auto">${esc(t.title)}</span>
        <span class="board-card__who"><span dir="auto">${esc(t.full_name)}</span> <span class="mono">(${esc(t.university_id)})</span></span>
        ${closed && t.closed_by ? `<span class="board-card__foot">${T('advisor.resolvedBy', { name: esc(t.closed_by) })}</span>` : ''}
      </a>
    </li>`;
}

function renderBoard(recent) {
  $('#board').innerHTML = COLUMNS.map((c) => {
    const list = recent[c.status] || [];
    const total = counts[c.status] || 0;
    return `
      <section class="column column--${c.tone}" aria-label="${esc(T(c.title))}">
        <div class="column__head">
          <span class="side-dot side-dot--${c.tone}"></span>
          <h2 class="column__title">${esc(T(c.title))}</h2>
          <span class="count-pill">${total}</span>
          <a class="column__all" href="#tickets/${c.status}">${esc(T('advisor.viewAll'))}</a>
        </div>
        <ul class="column__list">
          ${list.length ? list.map(boardCard).join('') : `<li class="column__empty">${esc(T(`advisor.colEmpty.${c.status}`))}</li>`}
        </ul>
        ${total > list.length ? `<p class="column__more muted">${esc(T('advisor.showingLatest', { n: list.length, total }))}</p>` : ''}
      </section>`;
  }).join('');
}

function renderUpdated() {
  $('#overview-updated').textContent = overviewAt
    ? T('advisor.updated', { time: I18n.time(overviewAt) })
    : T('advisor.loading');
}

function renderOverview() {
  if (!counts || !overviewData) return;
  renderCounts();
  renderStats();
  renderBoard(overviewData.recent);
  renderUpdated();
}

async function loadOverview(quiet = false) {
  if (!quiet) { overviewAt = null; renderUpdated(); }
  try {
    const data = await Auth.api('/api/advisor/tickets/overview');
    counts = data.counts;
    overviewData = data;
    overviewAt = new Date();
    renderOverview();
  } catch (err) {
    $('#overview-updated').textContent = err.message;
    if (!quiet) toast(err.message, true);
  }
}

/* ==========================================================
   Inbox (ticket list)
   ========================================================== */
function ticketRow(t) {
  const selected = openTicket && openTicket.ticket.id === t.id;
  return `
    <li>
      <a class="ticket-row${selected ? ' is-selected' : ''}" href="#tickets/${route.filter}/${encodeURIComponent(t.id)}"
         ${selected ? 'aria-current="true"' : ''}>
        <span class="ticket-row__top">
          <span class="ticket-code">${esc(t.code)}</span>
          ${statusBadge(t.status)}
        </span>
        <span class="ticket-row__title" dir="auto">${esc(t.title)}</span>
        <span class="ticket-row__meta">
          <span dir="auto">${esc(t.full_name)}</span>
          <span class="mono">${esc(t.university_id)}</span>
          <span>${esc(ago(t.updated_at))}</span>
        </span>
      </a>
    </li>`;
}

function renderInbox() {
  $('#inbox-title').textContent = T(`advisor.filterTitle.${route.filter}`);
  $('#inbox-count').textContent = inboxTickets.length;
  $('#ticket-list').innerHTML = inboxTickets.map(ticketRow).join('');
  const status = $('#ticket-list-status');
  const q = $('#ticket-search').value.trim();
  status.className = 'status';
  status.textContent = inboxTickets.length ? ''
    : q ? T('advisor.noMatch')
      : T(`advisor.none.${route.filter}`);
}

let searchTimer;
async function loadInbox(quiet = false) {
  const status = $('#ticket-list-status');
  if (!quiet) {
    status.className = 'status';
    status.textContent = T('advisor.loadingTickets');
    $('#ticket-list').innerHTML = '';
  }
  const params = new URLSearchParams();
  if (route.filter !== 'all') params.set('status', route.filter);
  const q = $('#ticket-search').value.trim();
  if (q) params.set('q', q);
  const filter = route.filter;
  try {
    const data = await Auth.api(`/api/advisor/tickets?${params}`);
    if (route.view !== 'tickets' || route.filter !== filter) return;
    inboxTickets = data.tickets || [];
    counts = data.counts;
    renderCounts();
    renderInbox();
  } catch (err) {
    status.className = 'status status--error';
    status.textContent = err.message;
  }
}

/* ==========================================================
   Conversation
   ========================================================== */
function messageHtml(m) {
  const staff = m.sender_role !== 'student';
  const mine = me && m.sender_id === me.id;
  const role = T(`advisor.role.${staff ? (m.sender_role === 'admin' ? 'admin' : 'advisor') : 'student'}`);
  return `
    <div class="msg ${staff ? 'msg--staff' : 'msg--student'}">
      <span class="avatar avatar--sm" aria-hidden="true">${esc(Auth.initials(m.sender_name))}</span>
      <div class="msg__body">
        <div class="msg__meta">
          <span class="msg__who" dir="auto">${mine ? esc(T('advisor.you')) : esc(m.sender_name)}</span>
          <span class="msg__role">${role}</span>
          <span class="muted">${esc(fmtDate(m.created_at))}</span>
        </div>
        <div class="msg__bubble" dir="auto">${esc(m.body)}</div>
      </div>
    </div>`;
}

function renderMessages({ ticket, messages }) {
  const opened = `<div class="system-line">${T('advisor.ticketOpenedBy', { name: esc(ticket.full_name), date: esc(fmtDate(ticket.created_at)) })}</div>`;
  const none = messages.length ? '' : `<div class="system-line">${esc(T('advisor.noMessages'))}</div>`;
  const closed = ticket.status === 'closed'
    ? `<div class="system-line">${ticket.closed_by
      ? T('advisor.resolvedByLine', { name: esc(ticket.closed_by), date: esc(fmtDate(ticket.closed_at)) })
      : T('advisor.resolvedLine', { date: esc(fmtDate(ticket.closed_at)) })}</div>`
    : '';
  const box = $('#chat-messages');
  const atEnd = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
  box.innerHTML = opened + messages.map(messageHtml).join('') + none + closed;
  if (atEnd || box.dataset.ticket !== ticket.id) box.scrollTop = box.scrollHeight;
  box.dataset.ticket = ticket.id;
}

function renderChat(data) {
  openTicket = data;
  const { ticket } = data;
  const closed = ticket.status === 'closed';
  $('#chat-empty').hidden = true;
  $('#chat').hidden = false;
  $('#view-tickets').classList.add('has-chat');
  $('#chat-code').textContent = ticket.code;
  $('#chat-status').innerHTML = statusBadge(ticket.status);
  $('#chat-title').textContent = ticket.title;
  $('#chat-meta').innerHTML = `
    <span dir="auto">${esc(ticket.full_name)}</span>
    <span class="mono">${esc(ticket.university_id)}</span>
    <span>${esc(T('advisor.opened', { date: fmtDate(ticket.created_at) || '' }))}</span>`;
  $('#close-ticket-btn').hidden = closed;
  $('#reopen-ticket-btn').hidden = !closed;
  $('#composer').hidden = closed;
  renderChatProfile(data.student, ticket.id);
  $('#closed-note').hidden = !closed;
  $('#closed-note').textContent = closed ? T('advisor.closedNote') : '';
  renderMessages(data);
  // Highlight it in the list.
  document.querySelectorAll('.ticket-row').forEach((a) => {
    const on = a.getAttribute('href').endsWith(`/${encodeURIComponent(ticket.id)}`);
    a.classList.toggle('is-selected', on);
  });
}

function renderChatProfile(student, ticketId) {
  const body = $('#chat-profile-body');
  // Polling re-renders the chat; keep the profile (and its expanded lists) unless the ticket changed.
  if (body.dataset.ticket === ticketId) return;
  body.dataset.ticket = ticketId;
  body.innerHTML = student ? detailHtml(student) : `<p class="muted">${esc(T('advisor.studentNotFound'))}</p>`;
}

function clearChat() {
  openTicket = null;
  chatToken++;
  $('#chat').hidden = true;
  $('#chat-empty').hidden = false;
  $('#view-tickets').classList.remove('has-chat');
  $('#chat-messages').dataset.ticket = '';
  $('#chat-profile-body').dataset.ticket = '';
}

async function loadChat(id, quiet = false) {
  const token = ++chatToken;
  if (!quiet) {
    $('#chat-empty').hidden = true;
    $('#chat').hidden = false;
    $('#view-tickets').classList.add('has-chat');
    if (!openTicket || openTicket.ticket.id !== id) {
      $('#chat-messages').innerHTML = `<div class="system-line">${esc(T('advisor.loadingChat'))}</div>`;
    }
  }
  try {
    const data = await Auth.api(`/api/advisor/tickets/${encodeURIComponent(id)}`);
    if (token !== chatToken) return;
    // Polling: re-render only when something changed, so the reply box keeps focus.
    if (quiet && openTicket && openTicket.messages.length === data.messages.length
        && openTicket.ticket.status === data.ticket.status) return;
    renderChat(data);
  } catch (err) {
    if (token !== chatToken) return;
    if (!quiet) {
      $('#chat-messages').innerHTML = `<div class="empty"><strong>${esc(T('advisor.openFailed'))}</strong>${esc(err.message)}</div>`;
    }
  }
}

async function sendReply(e) {
  e.preventDefault();
  if (!openTicket) return;
  const resolve = !!(e.submitter && e.submitter.id === 'resolve-btn');
  const box = $('#reply');
  const body = box.value.trim();
  if (!body) return box.focus();
  const btns = [$('#send-btn'), $('#resolve-btn')];
  btns.forEach((b) => { b.disabled = true; });
  const { ticket } = openTicket;
  try {
    await Auth.api(`/api/advisor/tickets/${encodeURIComponent(ticket.id)}/messages`, {
      method: 'POST',
      body: resolve ? { body, close: true } : { body },
    });
    box.value = '';
    if (resolve) toast(T('advisor.toast.resolved', { code: ticket.code }));
    await loadChat(ticket.id);
    loadInbox(true);
  } catch (err) {
    toast(err.message, true);
    if (err.status === 409) loadChat(ticket.id);
  } finally {
    btns.forEach((b) => { b.disabled = false; });
    box.focus();
  }
}

async function setTicketState(action) {
  if (!openTicket) return;
  const { ticket } = openTicket;
  if (action === 'close' && !confirm(T('advisor.confirmClose', { code: ticket.code }))) return;
  const btn = action === 'close' ? $('#close-ticket-btn') : $('#reopen-ticket-btn');
  btn.disabled = true;
  try {
    await Auth.api(`/api/advisor/tickets/${encodeURIComponent(ticket.id)}/${action}`, { method: 'POST' });
    toast(T(action === 'close' ? 'advisor.toast.resolved' : 'advisor.toast.reopened', { code: ticket.code }));
    await loadChat(ticket.id);
    loadInbox(true);
  } catch (err) {
    toast(err.message, true);
  } finally {
    btn.disabled = false;
  }
}

/* ==========================================================
   Students (academic profiles)
   ========================================================== */
function studentRow(s) {
  const gpa = fmtGpa(s.gpa);
  const low = typeof s.gpa === 'number' && s.gpa < 2;
  const right = gpa
    ? `<span class="student-row__gpa${low ? ' student-row__gpa--low' : ''}">${esc(gpa)}</span>`
    : '';
  const meta = [
    `<span class="mono">${esc(s.username)}</span>`,
    s.major ? `<span dir="auto">${esc(s.major)}</span>` : '',
    s.has_transcript || gpa ? '' : `<span>${esc(T('advisor.noTranscriptYet'))}</span>`,
  ].join('');
  return `
    <li>
      <button type="button" class="student-row${s.active === false ? ' is-inactive' : ''}" data-id="${esc(s.id)}"
              aria-current="${String(s.id) === String(selectedStudent)}">
        <span class="avatar" aria-hidden="true">${esc(Auth.initials(s.name))}</span>
        <span class="student-row__body">
          <span class="student-row__name" dir="auto" style="display:block">${esc(s.name)}</span>
          <span class="student-row__meta">${meta}</span>
        </span>
        ${right}
      </button>
    </li>`;
}

function renderStudentList() {
  const q = $('#search').value.trim().toLowerCase();
  const shown = students.filter((s) =>
    !q || (s.name || '').toLowerCase().includes(q) || (s.username || '').toLowerCase().includes(q));
  $('#student-count').textContent = students.length ? T('advisor.countOf', { n: shown.length, total: students.length }) : '';
  $('#student-list').innerHTML = shown.map(studentRow).join('');
  const status = $('#list-status');
  status.className = 'status';
  if (!students.length) status.textContent = T('advisor.noStudents');
  else if (!shown.length) status.textContent = T('advisor.noStudentMatch');
  else status.textContent = '';
}

async function loadStudents() {
  const status = $('#list-status');
  status.className = 'status';
  status.textContent = T('advisor.loadingStudents');
  try {
    const [data] = await Promise.all([Auth.api('/api/advisor/students'), loadCourses()]);
    students = data.students || [];
    studentsLoaded = true;
    renderStudentList();
  } catch (err) {
    status.className = 'status status--error';
    status.textContent = `${err.message} ${T('advisor.reloadHint')}`;
  }
}

async function loadCourses() {
  try {
    const data = await Auth.api('/api/schedule/courses');
    (data.courses || data || []).forEach((c) => {
      courseInfo[c.code] = { name: c.name || c.title || '', credits: c.credits };
    });
  } catch {
    /* Titles are optional; codes alone still show */
  }
}

function courseItem(code) {
  const info = courseInfo[code];
  const credits = info && info.credits != null ? esc(T('advisor.cr', { n: info.credits })) : '';
  return `
    <li>
      <span class="course-list__code">${esc(code)}</span>
      <span class="course-list__title">${info && info.name ? esc(info.name) : ''}</span>
      <span class="course-list__credits">${credits}</span>
    </li>`;
}

function courseSection(title, codes) {
  const list = Array.isArray(codes) ? codes : [];
  const head = `<h3 class="section__title">${esc(title)}<span class="count">${list.length}</span></h3>`;
  if (!list.length) return `<div class="section">${head}<p class="muted">${esc(T('advisor.none'))}</p></div>`;
  const first = list.slice(0, COLLAPSED_COUNT).map(courseItem).join('');
  const rest = list.slice(COLLAPSED_COUNT).map(courseItem).join('');
  const more = rest
    ? `<ul class="course-list" data-rest hidden style="margin-top:-1px;border-top:none;border-radius:0 0 10px 10px">${rest}</ul>
       <button type="button" class="link-btn" data-toggle-rest aria-expanded="false" data-n="${list.length}">${esc(T('advisor.showAll', { n: list.length }))}</button>`
    : '';
  return `<div class="section">${head}<ul class="course-list">${first}</ul>${more}</div>`;
}

const fact = (label, value, auto) => {
  const blank = value == null || value === '';
  return `<div class="fact"><dt>${esc(T(label))}</dt>
    <dd class="${blank ? 'is-blank' : ''}"${auto && !blank ? ' dir="auto"' : ''}>${blank ? esc(T('advisor.notProvided')) : esc(value)}</dd></div>`;
};

function identitySection(user, profile) {
  return `
    <div class="section">
      <h3 class="section__title">${esc(T('advisor.identity'))}</h3>
      <dl class="facts">
        ${fact('advisor.f.name', user.name, true)}
        ${fact('advisor.f.universityId', user.username)}
        ${fact('advisor.f.major', profile.major, true)}
        ${fact('advisor.f.level', profile.level)}
        ${fact('advisor.f.email', profile.email)}
        ${fact('advisor.f.phone', profile.phone)}
      </dl>
    </div>`;
}

function standingSection(t) {
  if (!t) {
    return `
      <div class="section">
        <h3 class="section__title">${esc(T('advisor.standing'))}</h3>
        <div class="empty"><strong>${esc(T('advisor.noTranscriptTitle'))}</strong>
          ${esc(T('advisor.noTranscriptText'))}</div>
      </div>`;
  }
  const gpa = fmtGpa(t.gpa);
  const low = typeof t.gpa === 'number' && t.gpa < 2;
  const hours = t.earned_hours != null ? esc(t.earned_hours) : esc(T('advisor.unknown'));
  const done = (t.completed || []).length;
  const when = fmtDate(t.parsed_at);
  return `
    <div class="section">
      <h3 class="section__title">${esc(T('advisor.standing'))}</h3>
      <dl class="standing">
        <div class="standing__item"><dt>${esc(T('advisor.gpa'))}</dt><dd>${gpa ? esc(gpa) : '--'}<small> / 5</small></dd></div>
        <div class="standing__item"><dt>${esc(T('advisor.earnedHours'))}</dt><dd>${hours}</dd></div>
        <div class="standing__item"><dt>${esc(T('advisor.completedCourses'))}</dt><dd>${done}</dd></div>
      </dl>
      ${low ? `<p class="notice" role="note">${esc(T('advisor.lowGpa'))}</p>` : ''}
      <p class="muted" style="font-size:13px">${when ? esc(T('advisor.importedOn', { date: when })) : esc(T('advisor.importUnknown'))}</p>
    </div>`;
}

function plannerSection(p) {
  const head = `<h3 class="section__title">${esc(T('advisor.planner'))}</h3>`;
  if (!p || !Object.keys(p).length) {
    return `<div class="section">${head}<p class="muted">${esc(T('advisor.plannerNone'))}</p></div>`;
  }
  const selected = Array.isArray(p.selected) ? p.selected : [];
  const saved = fmtDate(p.savedAt);
  const days = p.daysOff != null ? plural(Number(p.daysOff), 'advisor.daysOff') : null;
  return `
    <div class="section">
      ${head}
      <dl class="facts">
        ${fact('advisor.f.daysOff', days)}
        ${fact('advisor.f.timeWindow', p.timeFrom != null && p.timeTo != null ? T('advisor.timeRange', { from: fmtMinutes(p.timeFrom), to: fmtMinutes(p.timeTo) }) : '')}
        ${fact('advisor.f.closedSections', p.includeClosed == null ? '' : T(p.includeClosed ? 'advisor.included' : 'advisor.notIncluded'))}
        ${fact('advisor.f.saved', saved)}
      </dl>
      ${selected.length
        ? `<h3 class="section__title" style="margin-top:16px">${esc(T('advisor.selectedCourses'))}<span class="count">${selected.length}</span></h3>
           <ul class="course-list">${selected.map(courseItem).join('')}</ul>`
        : `<p class="muted" style="margin-top:12px">${esc(T('advisor.noSelected'))}</p>`}
    </div>`;
}

function chatSection(n) {
  return `
    <div class="section">
      <h3 class="section__title">${esc(T('advisor.chatUse'))}</h3>
      <p>${esc(plural(Number(n) || 0, 'advisor.conv'))}</p>
      <p class="chat-note">${esc(T('advisor.chatPrivate'))}</p>
    </div>`;
}

function detailHtml({ user, profile, chat_count }) {
  const p = profile || {};
  const t = p.transcript || null;
  const active = user.active !== false;
  return `
    <div class="profile-head">
      <div class="avatar avatar--lg" aria-hidden="true">${esc(Auth.initials(user.name))}</div>
      <div>
        <h2 class="profile-head__name" dir="auto">${esc(user.name)}</h2>
        <div class="profile-head__sub">
          <span class="mono">${esc(user.username)}</span>
          <span class="badge ${active ? 'badge--ok' : 'badge--off'}">${esc(T(active ? 'advisor.activeAccount' : 'advisor.disabledAccount'))}</span>
        </div>
      </div>
    </div>
    ${identitySection(user, p)}
    ${standingSection(t)}
    ${t ? courseSection(T('advisor.sec.completed'), t.completed) : ''}
    ${t ? courseSection(T('advisor.sec.notPassed'), t.not_passed) : ''}
    ${t ? courseSection(T('advisor.sec.eligible'), t.eligible) : ''}
    ${t ? courseSection(T('advisor.sec.suggested'), t.suggested) : ''}
    ${plannerSection(p.planner)}
    ${chatSection(chat_count)}`;
}

function renderDetail(data) {
  selectedData = data;
  $('#detail').innerHTML = detailHtml(data);
}

function showStudentPlaceholder() {
  $('#layout').classList.remove('has-selection');
  $('#detail').innerHTML = `
    <div class="empty"><strong>${esc(T('advisor.selectStudent'))}</strong>${esc(T('advisor.selectStudentHint'))}</div>`;
}

async function selectStudent(id) {
  selectedStudent = id;
  const token = ++detailToken;
  $('#layout').classList.add('has-selection');
  $('#detail').innerHTML = '<div class="skeleton" style="width:40%;height:24px"></div><div class="skeleton" style="width:80%"></div><div class="skeleton" style="width:65%"></div><p class="muted">' + esc(T('advisor.loadingProfile')) + '</p>';
  selectedData = null;
  renderStudentList();
  try {
    const data = await Auth.api(`/api/advisor/students/${encodeURIComponent(id)}`);
    if (token !== detailToken) return;
    renderDetail(data);
  } catch (err) {
    if (token !== detailToken) return;
    $('#detail').innerHTML = `
      <div class="empty"><strong>${esc(T('advisor.studentFailed'))}</strong>${esc(err.message)}
        <div><button type="button" class="link-btn" id="retry-btn">${esc(T('common.retry'))}</button></div></div>`;
  }
}

/* ==========================================================
   Routing
   ========================================================== */
function parseHash() {
  const parts = location.hash.replace(/^#\/?/, '').split('/').map(decodeURIComponent);
  if (parts[0] === 'tickets' && FILTERS.includes(parts[1])) return { view: 'tickets', filter: parts[1], id: parts[2] || null };
  if (parts[0] === 'students') return { view: 'students', id: parts[1] || null };
  return { view: 'overview' };
}

function showView(name) {
  ['overview', 'tickets', 'students'].forEach((v) => { $(`#view-${v}`).hidden = v !== name; });
}

async function applyRoute() {
  const prev = route;
  route = parseHash();
  stopTimers();
  setActiveNav();
  showView(route.view);

  if (route.view === 'overview') {
    loadOverview();
    every(OVERVIEW_POLL_MS, () => loadOverview(true));
  } else if (route.view === 'tickets') {
    if (prev.view !== 'tickets' || prev.filter !== route.filter) {
      $('#ticket-search').value = '';
      await loadInbox();
    }
    if (route.id) loadChat(route.id);
    else clearChat();
    every(LIST_POLL_MS, () => loadInbox(true));
    every(CHAT_POLL_MS, () => { if (openTicket && route.id) loadChat(route.id, true); });
  } else {
    if (!studentsLoaded) await loadStudents();
    if (route.id) selectStudent(route.id);
    else {
      selectedStudent = null;
      detailToken++;
      renderStudentList();
      showStudentPlaceholder();
    }
  }
}

/* ==========================================================
   Events
   ========================================================== */
function toggleRest(e) {
  const btn = e.target.closest('[data-toggle-rest]');
  if (!btn) return;
  const rest = btn.previousElementSibling;
  const open = rest.hidden;
  rest.hidden = !open;
  btn.setAttribute('aria-expanded', String(open));
  btn.textContent = open ? T('advisor.showFewer') : T('advisor.showAll', { n: btn.dataset.n });
}

function bindEvents() {
  window.addEventListener('hashchange', applyRoute);
  $('#sign-out-btn').addEventListener('click', () => Auth.signOut());
  $('#refresh-btn').addEventListener('click', () => loadOverview());

  // Inbox
  $('#ticket-search').addEventListener('input', () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => loadInbox(), 250);
  });
  $('#chat-back').addEventListener('click', () => { location.hash = `#tickets/${route.filter}`; });
  $('#composer').addEventListener('submit', sendReply);
  $('#reply').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      $('#composer').requestSubmit();
    }
  });
  $('#close-ticket-btn').addEventListener('click', () => setTicketState('close'));
  $('#reopen-ticket-btn').addEventListener('click', () => setTicketState('reopen'));

  const quick = $('#quick-reply');
  // The replies are Arabic text sent to students, shown as they are; only the placeholder option is translated.
  quick.innerHTML += QUICK_REPLIES.map((r, i) => `<option value="${i}" dir="auto">${esc(r.length > 60 ? `${r.slice(0, 60)}…` : r)}</option>`).join('');
  quick.addEventListener('change', () => {
    if (quick.value === '') return;
    const box = $('#reply');
    box.value = box.value ? `${box.value.trimEnd()}\n${QUICK_REPLIES[quick.value]}` : QUICK_REPLIES[quick.value];
    quick.value = '';
    box.focus();
  });

  // Students
  $('#search').addEventListener('input', renderStudentList);
  $('#student-list').addEventListener('click', (e) => {
    const row = e.target.closest('.student-row');
    if (row) location.hash = `#students/${encodeURIComponent(row.dataset.id)}`;
  });
  $('#back-btn').addEventListener('click', () => { location.hash = '#students'; });
  $('#detail').addEventListener('click', (e) => {
    if (e.target.closest('#retry-btn') && selectedStudent) selectStudent(selectedStudent);
    toggleRest(e);
  });
  $('#chat-profile-body').addEventListener('click', toggleRest);
}

/* ==========================================================
   Language change: re-render what is on screen. The reply textarea
   is never rebuilt, so a typed reply stays.
   ========================================================== */
function rerender() {
  setActiveNav();
  renderOverview();
  if (route.view === 'tickets') {
    renderInbox();
    if (openTicket) {
      $('#chat-profile-body').dataset.ticket = '';   // rebuild the profile in the new language
      renderChat(openTicket);
    }
  } else if (route.view === 'students') {
    renderStudentList();
    if (selectedData) renderDetail(selectedData);
    else if (!selectedStudent) showStudentPlaceholder();
  }
  if (me) Auth.fillUser(me);
}

/* ==========================================================
   Init
   ========================================================== */
Auth.requireRole('advisor', 'admin').then((user) => {
  me = user;
  Auth.fillUser(user);
  if (user.role === 'admin') $('#admin-link').hidden = false;
  bindEvents();
  I18n.onChange(rerender);
  applyRoute();
});
