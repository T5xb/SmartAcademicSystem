/* ==========================================================
   Academic AI - Student profile page
   ========================================================== */

const $ = (s) => document.querySelector(s);

/* ---------- State ---------- */
let courseInfo = {};     // code -> { name, credits }
let saved = {};          // last saved values of the details form
let toastTimer = null;
let lastTranscript;      // what the record / planner sections show, kept for language changes
let lastPlanner;
let loaded = false;
const COLLAPSED_COUNT = 8;
const SCHEDULE_URL = '../schedule-page/index.html?v=2';
const DETAIL_FIELDS = ['email', 'phone', 'major', 'level'];

/* ---------- Helpers ---------- */
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
));

const t = (key, vars) => I18n.t(key, vars);

const plural = (n) => (n === 1 ? t('profile.daysOffOne') : t('profile.daysOffMany', { n }));

function fmtMinutes(m) {
  if (typeof m !== 'number') return '';
  return `${String(Math.floor(m / 60) % 24).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
}

function fmtDate(iso) {
  if (!iso) return null;
  return I18n.dateTime(iso) || null;
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
  const credits = info && info.credits != null ? esc(t('profile.credits', { n: info.credits })) : '';
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
  if (!list.length) return `<div class="sub">${head}<p class="muted">${esc(t('profile.none'))}</p></div>`;
  const first = list.slice(0, COLLAPSED_COUNT).map(courseItem).join('');
  const rest = list.slice(COLLAPSED_COUNT).map(courseItem).join('');
  const more = rest
    ? `<ul class="course-list course-list--rest" hidden>${rest}</ul>
       <button type="button" class="link-btn" data-toggle-rest aria-expanded="false" data-n="${list.length}">${esc(t('profile.showAll', { n: list.length }))}</button>`
    : '';
  return `<div class="sub">${head}<ul class="course-list">${first}</ul>${more}</div>`;
}

/* ==========================================================
   Academic record and planner
   ========================================================== */
function renderRecord(tr) {
  lastTranscript = tr;
  const box = $('#record');
  if (!tr) {
    box.innerHTML = `
      <div class="empty"><strong>${esc(t('profile.noTranscript'))}</strong>
        ${esc(t('profile.noTranscriptHint'))}
        <div><a class="btn btn--outline" href="${SCHEDULE_URL}">${esc(t('profile.importHere'))}</a></div></div>`;
    return;
  }
  const gpa = typeof tr.gpa === 'number' ? tr.gpa.toFixed(2) : '--';
  const hours = tr.earned_hours != null ? esc(tr.earned_hours) : '--';
  const when = fmtDate(tr.parsed_at);
  box.innerHTML = `
    <dl class="standing">
      <div class="standing__item"><dt>${esc(t('profile.gpa'))}</dt><dd>${gpa}<small> / 5</small></dd></div>
      <div class="standing__item"><dt>${esc(t('profile.earned'))}</dt><dd>${hours}</dd></div>
      <div class="standing__item"><dt>${esc(t('profile.completedCount'))}</dt><dd>${(tr.completed || []).length}</dd></div>
    </dl>
    ${typeof tr.gpa === 'number' && tr.gpa < 2 ? `<p class="notice" role="note">${esc(t('profile.warning'))}</p>` : ''}
    <p class="muted" style="font-size:13px">${when ? esc(t('profile.imported', { date: when })) : ''}
      <a class="link-btn" href="${SCHEDULE_URL}">${esc(t('profile.importNewer'))}</a></p>
    ${courseGroup(t('profile.completed'), tr.completed)}
    ${courseGroup(t('profile.eligible'), tr.eligible)}
    ${courseGroup(t('profile.suggested'), tr.suggested)}`;
}

function fact(label, value) {
  return `<div class="fact"><dt>${esc(label)}</dt><dd>${value ? esc(value) : `<span class="muted">${esc(t('profile.notSet'))}</span>`}</dd></div>`;
}

function renderPlanner(p) {
  lastPlanner = p;
  const box = $('#planner');
  if (!p || !Object.keys(p).length) {
    box.innerHTML = `
      <div class="empty"><strong>${esc(t('profile.noChoices'))}</strong>
        ${esc(t('profile.noChoicesHint'))}
        <div><a class="btn btn--outline" href="${SCHEDULE_URL}">${esc(t('profile.openSchedule'))}</a></div></div>`;
    return;
  }
  const selected = Array.isArray(p.selected) ? p.selected : [];
  const saved = fmtDate(p.savedAt);
  const days = p.daysOff != null ? plural(Number(p.daysOff)) : '';
  const window_ = p.timeFrom != null && p.timeTo != null ? t('profile.timeRange', { from: fmtMinutes(p.timeFrom), to: fmtMinutes(p.timeTo) }) : '';
  box.innerHTML = `
    <dl class="facts">
      ${fact(t('profile.daysOffWanted'), days)}
      ${fact(t('profile.timeWindow'), window_)}
      ${fact(t('profile.savedAt'), saved)}
    </dl>
    ${selected.length
      ? `<div class="sub"><h3 class="sub__title">${esc(t('profile.selected'))}<span class="count">${selected.length}</span></h3>
         <ul class="course-list">${selected.map(courseItem).join('')}</ul></div>`
      : `<p class="muted">${esc(t('profile.noneSelected'))}</p>`}
    <p><a class="link-btn" href="${SCHEDULE_URL}">${esc(t('profile.openSchedule'))}</a></p>`;
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
  setStatus('#details-status', t('profile.saving'));
  try {
    const data = await Auth.api('/api/me/profile', { method: 'PUT', body: formValues() });
    fillForm(data.profile);
    setStatus('#details-status', '');
    toast(t('profile.saved'));
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
    next: next && next.length < 8 ? t('profile.pwShort') : '',
    confirm: confirm && confirm !== next ? t('profile.pwMismatch') : '',
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
  setStatus('#password-status', t('profile.changing'));
  try {
    await Auth.api('/api/auth/password', {
      method: 'POST',
      body: { current_password: $('#p-current').value, new_password: $('#p-new').value },
    });
    $('#password-form').reset();
    setStatus('#password-status', '');
    togglePasswords();
    updatePasswordState();
    toast(t('profile.pwChanged'));
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
  status.textContent = t('profile.loading');
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
    loaded = true;
    $('#content').hidden = false;
  } catch (err) {
    status.className = 'status status--error';
    status.textContent = `${err.message} ${t('profile.reloadHint')}`;
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
    btn.textContent = open ? t('profile.showFewer') : t('profile.showAll', { n: btn.dataset.n });
  });

  $('#sign-out-btn').addEventListener('click', () => Auth.signOut());
}

/* ==========================================================
   Language
   ========================================================== */
// Level options keep their stored value ("Level 3"); only the label is translated.
function labelLevels() {
  [...$('#f-level').options].forEach((o) => {
    const m = /^Level (\d+)$/.exec(o.value);
    if (m) o.textContent = t('profile.levelN', { n: m[1] });
  });
}

I18n.onChange(() => {
  labelLevels();
  if (loaded) {
    // Re-render the parts that hold generated text; the form inputs are left alone.
    renderRecord(lastTranscript || null);
    renderPlanner(lastPlanner || null);
    updatePasswordState();
  }
});

/* ==========================================================
   Init
   ========================================================== */
function init() {
  bindEvents();
  labelLevels();
  loadProfile();
}

// Placeholders shown until the profile arrives
$('#load-status').textContent = t('profile.loading');
$('.user__name').textContent = t('common.loading');

Auth.requireRole('student').then((user) => {
  Tickets.mount(user);
  Auth.fillUser(user);
  init(user);
});
