/* ==========================================================
   Academic AI - Student profile page
   ========================================================== */

const $ = (s) => document.querySelector(s);

/* ---------- State ---------- */
let courseInfo = {};     // code -> { name, credits }
let saved = {};          // last saved values of the details form
let toastTimer = null;
const COLLAPSED_COUNT = 8;
const SCHEDULE_URL = '../schedule-page/index.html?v=2';
const DETAIL_FIELDS = ['email', 'phone', 'major', 'level'];

/* ---------- Helpers ---------- */
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
));

const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

function fmtMinutes(m) {
  if (typeof m !== 'number') return '';
  return `${String(Math.floor(m / 60) % 24).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
}

function fmtDate(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function toast(message, isError) {
  const el = $('#toast');
  el.textContent = message;
  el.classList.toggle('is-error', !!isError);
  el.classList.add('is-visible');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('is-visible'), 3000);
}

function setStatus(sel, text, kind) {
  const el = $(sel);
  el.textContent = text || '';
  el.className = `status status--inline${kind ? ` status--${kind}` : ''}`;
}

/* ==========================================================
   Course lists
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

function courseGroup(title, codes) {
  const list = Array.isArray(codes) ? codes : [];
  const head = `<h3 class="sub__title">${esc(title)}<span class="count">${list.length}</span></h3>`;
  if (!list.length) return `<div class="sub">${head}<p class="muted">None.</p></div>`;
  const first = list.slice(0, COLLAPSED_COUNT).map(courseItem).join('');
  const rest = list.slice(COLLAPSED_COUNT).map(courseItem).join('');
  const more = rest
    ? `<ul class="course-list course-list--rest" hidden>${rest}</ul>
       <button type="button" class="link-btn" data-toggle-rest aria-expanded="false" data-n="${list.length}">Show all ${list.length}</button>`
    : '';
  return `<div class="sub">${head}<ul class="course-list">${first}</ul>${more}</div>`;
}

/* ==========================================================
   Academic record and planner
   ========================================================== */
function renderRecord(t) {
  const box = $('#record');
  if (!t) {
    box.innerHTML = `
      <div class="empty"><strong>No transcript imported yet</strong>
        Import your transcript PDF to see your GPA, earned hours and the courses you can take next.
        <div><a class="btn btn--outline" href="${SCHEDULE_URL}">Import transcript on the schedule page</a></div></div>`;
    return;
  }
  const gpa = typeof t.gpa === 'number' ? t.gpa.toFixed(2) : '--';
  const hours = t.earned_hours != null ? esc(t.earned_hours) : '--';
  const when = fmtDate(t.parsed_at);
  box.innerHTML = `
    <dl class="standing">
      <div class="standing__item"><dt>GPA</dt><dd>${gpa}<small> / 5</small></dd></div>
      <div class="standing__item"><dt>Earned hours</dt><dd>${hours}</dd></div>
      <div class="standing__item"><dt>Completed courses</dt><dd>${(t.completed || []).length}</dd></div>
    </dl>
    ${typeof t.gpa === 'number' && t.gpa < 2 ? '<p class="notice" role="note">Below 2.00: academic warning range. Talk to your academic advisor.</p>' : ''}
    <p class="muted" style="font-size:13px">${when ? `Transcript imported ${esc(when)}.` : ''}
      <a class="link-btn" href="${SCHEDULE_URL}">Import a newer transcript</a></p>
    ${courseGroup('Completed', t.completed)}
    ${courseGroup('Eligible now', t.eligible)}
    ${courseGroup('Suggested next term', t.suggested)}`;
}

function fact(label, value) {
  return `<div class="fact"><dt>${esc(label)}</dt><dd>${value ? esc(value) : '<span class="muted">Not set</span>'}</dd></div>`;
}

function renderPlanner(p) {
  const box = $('#planner');
  if (!p || !Object.keys(p).length) {
    box.innerHTML = `
      <div class="empty"><strong>No saved choices yet</strong>
        Pick your courses and preferences on the schedule page and they are saved here.
        <div><a class="btn btn--outline" href="${SCHEDULE_URL}">Open the schedule page</a></div></div>`;
    return;
  }
  const selected = Array.isArray(p.selected) ? p.selected : [];
  const saved = fmtDate(p.savedAt);
  const days = p.daysOff != null ? plural(Number(p.daysOff), 'day off', 'days off') : '';
  const window_ = p.timeFrom != null && p.timeTo != null ? `${fmtMinutes(p.timeFrom)} to ${fmtMinutes(p.timeTo)}` : '';
  box.innerHTML = `
    <dl class="facts">
      ${fact('Days off wanted', days)}
      ${fact('Time window', window_)}
      ${fact('Saved', saved)}
    </dl>
    ${selected.length
      ? `<div class="sub"><h3 class="sub__title">Selected courses<span class="count">${selected.length}</span></h3>
         <ul class="course-list">${selected.map(courseItem).join('')}</ul></div>`
      : '<p class="muted">No courses selected.</p>'}
    <p><a class="link-btn" href="${SCHEDULE_URL}">Open the schedule page</a></p>`;
}

/* ==========================================================
   Identity and details form
   ========================================================== */
function formValues() {
  return {
    email: $('#f-email').value.trim(),
    phone: $('#f-phone').value.trim(),
    major: $('#f-major').value,
    level: $('#f-level').value,
  };
}

function fillForm(profile) {
  saved = {};
  DETAIL_FIELDS.forEach((k) => { saved[k] = (profile && profile[k]) || ''; });
  $('#f-email').value = saved.email;
  $('#f-phone').value = saved.phone;
  // A stored value that is not in the list is still shown, so nothing is lost
  [['major', '#f-major'], ['level', '#f-level']].forEach(([k, sel]) => {
    const el = $(sel);
    if (saved[k] && ![...el.options].some((o) => o.value === saved[k])) {
      el.add(new Option(saved[k], saved[k]));
    }
    el.value = saved[k];
  });
  updateSaveState();
}

function updateSaveState() {
  const now = formValues();
  $('#save-btn').disabled = DETAIL_FIELDS.every((k) => now[k] === saved[k]);
}

async function saveDetails(e) {
  e.preventDefault();
  const btn = $('#save-btn');
  btn.disabled = true;
  setStatus('#details-status', 'Saving...');
  try {
    const data = await Auth.api('/api/me/profile', { method: 'PUT', body: formValues() });
    fillForm(data.profile);
    setStatus('#details-status', '');
    toast('Changes saved');
  } catch (err) {
    setStatus('#details-status', err.message, 'error');
    updateSaveState();
  }
}

/* ==========================================================
   Password form
   ========================================================== */
function passwordErrors() {
  const next = $('#p-new').value;
  const confirm = $('#p-confirm').value;
  return {
    next: next && next.length < 8 ? 'Use at least 8 characters.' : '',
    confirm: confirm && confirm !== next ? 'The two passwords do not match.' : '',
  };
}

function updatePasswordState() {
  const errs = passwordErrors();
  $('#p-new-err').textContent = errs.next;
  $('#p-confirm-err').textContent = errs.confirm;
  $('#p-new').setAttribute('aria-invalid', String(!!errs.next));
  $('#p-confirm').setAttribute('aria-invalid', String(!!errs.confirm));
  const ready = $('#p-current').value && $('#p-new').value.length >= 8 && $('#p-confirm').value === $('#p-new').value;
  $('#password-btn').disabled = !ready;
}

async function changePassword(e) {
  e.preventDefault();
  $('#password-btn').disabled = true;
  setStatus('#password-status', 'Changing...');
  try {
    await Auth.api('/api/auth/password', {
      method: 'POST',
      body: { current_password: $('#p-current').value, new_password: $('#p-new').value },
    });
    $('#password-form').reset();
    setStatus('#password-status', '');
    togglePasswords();
    updatePasswordState();
    toast('Password changed');
  } catch (err) {
    setStatus('#password-status', err.message, 'error');
    updatePasswordState();
  }
}

function togglePasswords() {
  const type = $('#p-show').checked ? 'text' : 'password';
  ['#p-current', '#p-new', '#p-confirm'].forEach((s) => { $(s).type = type; });
}

/* ==========================================================
   Load
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

async function loadProfile() {
  const status = $('#load-status');
  status.className = 'status';
  status.textContent = 'Loading your profile...';
  try {
    const [data] = await Promise.all([Auth.api('/api/me/profile'), loadCourses()]);
    const user = data.user || {};
    const profile = data.profile || {};
    $('#id-avatar').textContent = Auth.initials(user.name);
    $('#id-name').textContent = user.name || '';
    $('#id-username').textContent = user.username || '';
    fillForm(profile);
    renderRecord(profile.transcript || null);
    renderPlanner(profile.planner || null);
    updatePasswordState();
    status.textContent = '';
    $('#content').hidden = false;
  } catch (err) {
    status.className = 'status status--error';
    status.textContent = `${err.message} Reload the page to try again.`;
  }
}

/* ==========================================================
   Events
   ========================================================== */
function bindEvents() {
  $('#details-form').addEventListener('submit', saveDetails);
  $('#details-form').addEventListener('input', updateSaveState);
  $('#details-form').addEventListener('change', updateSaveState);

  $('#password-form').addEventListener('submit', changePassword);
  $('#password-form').addEventListener('input', updatePasswordState);
  $('#p-show').addEventListener('change', togglePasswords);

  $('#content').addEventListener('click', (e) => {
    const btn = e.target.closest('[data-toggle-rest]');
    if (!btn) return;
    const rest = btn.previousElementSibling;
    const open = rest.hidden;
    rest.hidden = !open;
    btn.setAttribute('aria-expanded', String(open));
    btn.textContent = open ? 'Show fewer' : `Show all ${btn.dataset.n}`;
  });

  $('#sign-out-btn').addEventListener('click', () => Auth.signOut());
}

/* ==========================================================
   Init
   ========================================================== */
function init() {
  bindEvents();
  loadProfile();
}

Auth.requireRole('student').then((user) => {
  Auth.fillUser(user);
  init(user);
});
