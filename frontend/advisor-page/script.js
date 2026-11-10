/* ==========================================================
   Academic AI - Advisor page
   ========================================================== */

const $ = (s) => document.querySelector(s);

/* ---------- State ---------- */
let students = [];
let courseInfo = {};   // code -> { name, credits }
let selectedId = null;
let detailToken = 0;   // ignores stale responses when clicking quickly
const COLLAPSED_COUNT = 8;

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
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

/* ==========================================================
   Student list
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
    s.has_transcript || gpa ? '' : '<span>No transcript yet</span>',
  ].join('');
  return `
    <li>
      <button type="button" class="student-row${s.active === false ? ' is-inactive' : ''}" data-id="${esc(s.id)}"
              aria-current="${String(s.id) === String(selectedId)}">
        <span class="avatar" aria-hidden="true">${esc(Auth.initials(s.name))}</span>
        <span class="student-row__body">
          <span class="student-row__name" dir="auto" style="display:block">${esc(s.name)}</span>
          <span class="student-row__meta">${meta}</span>
        </span>
        ${right}
      </button>
    </li>`;
}

function renderList() {
  const q = $('#search').value.trim().toLowerCase();
  const shown = students.filter((s) =>
    !q || (s.name || '').toLowerCase().includes(q) || (s.username || '').toLowerCase().includes(q));
  $('#student-count').textContent = students.length ? `${shown.length} of ${students.length}` : '';
  $('#student-list').innerHTML = shown.map(studentRow).join('');
  const status = $('#list-status');
  status.className = 'status';
  if (!students.length) status.textContent = 'No students yet. Students appear here after they sign up.';
  else if (!shown.length) status.textContent = 'No student matches your search. Try a name or a university ID.';
  else status.textContent = '';
}

async function loadStudents() {
  const status = $('#list-status');
  status.className = 'status';
  status.textContent = 'Loading students...';
  try {
    const data = await Auth.api('/api/advisor/students');
    students = data.students || [];
    renderList();
  } catch (err) {
    status.className = 'status status--error';
    status.textContent = `${err.message} Reload the page to try again.`;
  }
}

/* ==========================================================
   Course titles
   ========================================================== */
async function loadCourses() {
  try {
    const data = await Auth.api('/api/schedule/courses');
    (data.courses || []).forEach((c) => {
      courseInfo[c.code] = { name: c.name || c.title || '', credits: c.credits };
    });
  } catch {
    /* Titles are optional; codes alone still show */
  }
}

/* ==========================================================
   Detail rendering
   ========================================================== */
function courseItem(code) {
  const info = courseInfo[code];
  const credits = info && info.credits != null ? `${esc(info.credits)} cr` : '';
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
  if (!list.length) return `<div class="section">${head}<p class="muted">None.</p></div>`;
  const first = list.slice(0, COLLAPSED_COUNT).map(courseItem).join('');
  const rest = list.slice(COLLAPSED_COUNT).map(courseItem).join('');
  const more = rest
    ? `<ul class="course-list" data-rest hidden style="margin-top:-1px;border-top:none;border-radius:0 0 10px 10px">${rest}</ul>
       <button type="button" class="link-btn" data-toggle-rest aria-expanded="false" data-n="${list.length}">Show all ${list.length}</button>`
    : '';
  return `<div class="section">${head}<ul class="course-list">${first}</ul>${more}</div>`;
}

const fact = (label, value, auto) => {
  const blank = value == null || value === '';
  return `<div class="fact"><dt>${esc(label)}</dt>
    <dd class="${blank ? 'is-blank' : ''}"${auto && !blank ? ' dir="auto"' : ''}>${blank ? 'Not provided' : esc(value)}</dd></div>`;
};

function identitySection(user, profile) {
  return `
    <div class="section">
      <h3 class="section__title">Identity</h3>
      <dl class="facts">
        ${fact('Name', user.name, true)}
        ${fact('University ID', user.username)}
        ${fact('Major', profile.major, true)}
        ${fact('Level', profile.level)}
        ${fact('Email', profile.email)}
        ${fact('Phone', profile.phone)}
      </dl>
    </div>`;
}

function standingSection(t) {
  if (!t) {
    return `
      <div class="section">
        <h3 class="section__title">Academic standing</h3>
        <div class="empty"><strong>No transcript yet</strong>
          This student hasn't imported a transcript. Standing and course lists appear after they import it on the schedule page.</div>
      </div>`;
  }
  const gpa = fmtGpa(t.gpa);
  const low = typeof t.gpa === 'number' && t.gpa < 2;
  const hours = t.earned_hours != null ? esc(t.earned_hours) : 'Unknown';
  const done = (t.completed || []).length;
  const when = fmtDate(t.parsed_at);
  return `
    <div class="section">
      <h3 class="section__title">Academic standing</h3>
      <dl class="standing">
        <div class="standing__item"><dt>GPA</dt><dd>${gpa ? esc(gpa) : '--'}<small> / 5</small></dd></div>
        <div class="standing__item"><dt>Earned hours</dt><dd>${hours}</dd></div>
        <div class="standing__item"><dt>Completed courses</dt><dd>${done}</dd></div>
      </dl>
      ${low ? '<p class="notice" role="note">Below 2.00: academic warning range.</p>' : ''}
      <p class="muted" style="font-size:13px">${when ? `Transcript imported ${esc(when)}.` : 'Import date unknown.'}</p>
    </div>`;
}

function plannerSection(p) {
  const head = '<h3 class="section__title">Saved schedule choices</h3>';
  if (!p || !Object.keys(p).length) {
    return `<div class="section">${head}<p class="muted">The student hasn't saved any schedule choices yet.</p></div>`;
  }
  const selected = Array.isArray(p.selected) ? p.selected : [];
  const saved = fmtDate(p.savedAt);
  const days = p.daysOff != null ? plural(Number(p.daysOff), 'day off', 'days off') : null;
  return `
    <div class="section">
      ${head}
      <dl class="facts">
        ${fact('Days off wanted', days)}
        ${fact('Time window', p.timeFrom != null && p.timeTo != null ? `${fmtMinutes(p.timeFrom)} to ${fmtMinutes(p.timeTo)}` : '')}
        ${fact('Closed sections', p.includeClosed == null ? '' : (p.includeClosed ? 'Included' : 'Not included'))}
        ${fact('Saved', saved)}
      </dl>
      ${selected.length
        ? `<h3 class="section__title" style="margin-top:16px">Selected courses<span class="count">${selected.length}</span></h3>
           <ul class="course-list">${selected.map(courseItem).join('')}</ul>`
        : '<p class="muted" style="margin-top:12px">No courses selected.</p>'}
    </div>`;
}

function chatSection(n) {
  return `
    <div class="section">
      <h3 class="section__title">Chatbot use</h3>
      <p>${plural(Number(n) || 0, 'conversation', 'conversations')}</p>
      <p class="chat-note">The messages themselves are private to the student.</p>
    </div>`;
}

function renderDetail({ user, profile, chat_count }) {
  const p = profile || {};
  const t = p.transcript || null;
  const active = user.active !== false;
  $('#detail').innerHTML = `
    <div class="profile-head">
      <div class="avatar avatar--lg" aria-hidden="true">${esc(Auth.initials(user.name))}</div>
      <div>
        <h2 class="profile-head__name" dir="auto">${esc(user.name)}</h2>
        <div class="profile-head__sub">
          <span class="mono">${esc(user.username)}</span>
          <span class="badge ${active ? 'badge--ok' : 'badge--off'}">${active ? 'Active account' : 'Account disabled'}</span>
        </div>
      </div>
    </div>
    ${identitySection(user, p)}
    ${standingSection(t)}
    ${t ? courseSection('Completed', t.completed) : ''}
    ${t ? courseSection('Not passed (failed or withdrawn)', t.not_passed) : ''}
    ${t ? courseSection('Eligible now', t.eligible) : ''}
    ${t ? courseSection('Suggested next term', t.suggested) : ''}
    ${plannerSection(p.planner)}
    ${chatSection(chat_count)}`;
}

/* ==========================================================
   Selection
   ========================================================== */
function showPlaceholder() {
  $('#layout').classList.remove('has-selection');
  $('#detail').innerHTML = `
    <div class="empty"><strong>Select a student</strong>Choose a student from the list to see their academic profile.</div>`;
}

async function selectStudent(id) {
  selectedId = id;
  const token = ++detailToken;
  $('#layout').classList.add('has-selection');
  $('#detail').innerHTML = '<div class="skeleton" style="width:40%;height:24px"></div><div class="skeleton" style="width:80%"></div><div class="skeleton" style="width:65%"></div><p class="muted">Loading profile...</p>';
  renderList();
  try {
    const data = await Auth.api(`/api/advisor/students/${encodeURIComponent(id)}`);
    if (token !== detailToken) return;
    renderDetail(data);
  } catch (err) {
    if (token !== detailToken) return;
    $('#detail').innerHTML = `
      <div class="empty"><strong>Couldn't load this student</strong>${esc(err.message)}
        <div><button type="button" class="link-btn" id="retry-btn">Try again</button></div></div>`;
  }
}

function applyHash() {
  const id = decodeURIComponent(location.hash.replace(/^#/, ''));
  if (id) selectStudent(id);
  else {
    selectedId = null;
    detailToken++;
    renderList();
    showPlaceholder();
  }
}

/* ==========================================================
   Events
   ========================================================== */
function bindEvents() {
  $('#search').addEventListener('input', renderList);

  $('#student-list').addEventListener('click', (e) => {
    const row = e.target.closest('.student-row');
    if (!row) return;
    const id = row.dataset.id;
    if (location.hash === `#${encodeURIComponent(id)}`) selectStudent(id);
    else location.hash = encodeURIComponent(id);
  });

  $('#back-btn').addEventListener('click', () => {
    history.pushState('', document.title, location.pathname + location.search);
    applyHash();
  });

  $('#detail').addEventListener('click', (e) => {
    if (e.target.closest('#retry-btn') && selectedId) selectStudent(selectedId);
    const btn = e.target.closest('[data-toggle-rest]');
    if (btn) {
      const rest = btn.previousElementSibling;
      const open = rest.hidden;
      rest.hidden = !open;
      btn.setAttribute('aria-expanded', String(open));
      btn.textContent = open ? 'Show fewer' : `Show all ${btn.dataset.n}`;
    }
  });

  window.addEventListener('hashchange', applyHash);
  $('#sign-out-btn').addEventListener('click', () => Auth.signOut());
}

/* ==========================================================
   Init
   ========================================================== */
function init(user) {
  if (user.role === 'admin') $('#admin-link').hidden = false;
  bindEvents();
  showPlaceholder();
  Promise.all([loadStudents(), loadCourses()]).then(applyHash);
}

Auth.requireRole('advisor', 'admin').then((user) => {
  Auth.fillUser(user);
  init(user);
});
