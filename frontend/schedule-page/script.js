/* ==========================================================
   Academic AI - Study Schedule Planner
   ========================================================== */

/* ----------------------------------------------------------
   Session
   ---------------------------------------------------------- */
const SESSION_KEY = 'academic-ai-session';
const SIGN_IN_PAGE = '../sign-in-page/index.html';

function hasSession() {
  try {
    return Boolean(localStorage.getItem(SESSION_KEY) || sessionStorage.getItem(SESSION_KEY));
  } catch {
    return true; // Storage unavailable — don't lock the user out
  }
}

function signOut() {
  try {
    localStorage.removeItem(SESSION_KEY);
    sessionStorage.removeItem(SESSION_KEY);
  } catch {
    /* Nothing to clear */
  }
  window.location.replace(SIGN_IN_PAGE);
}

// Not signed in → back to the Sign In page
if (!hasSession()) window.location.replace(SIGN_IN_PAGE);

/* ----------------------------------------------------------
   Constants
   ---------------------------------------------------------- */
const DAY_NAMES = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday'];
const SCALE_START = 8 * 60;          // 08:00
const SCALE_END = 24 * 60;           // 24:00
const TIME_STEP = 30;                // minutes
let MAX_CREDITS = 18;                 // replaced by the server's default on load
const ROW_HEIGHT = 96;               // px per hour (matches --row-height)

// The CSP scheduler runs in fastapi_app.py (src/scheduling) — same server as the chatbot.
const API_URL = 'http://localhost:8000';
const SERVER_DOWN = `Couldn't reach the Academic AI server at ${API_URL}. Make sure the server is running (Start-API.bat).`;

const DEFAULT_SELECTED = ['ريض 1112', 'عال 1140', 'عال 1220'];
const MAX_UPLOAD_SIZE = 15 * 1024 * 1024;

/* ----------------------------------------------------------
   Helpers
   ---------------------------------------------------------- */
const $ = (selector) => document.querySelector(selector);

const toMinutes = (time) => {
  const [h, m] = time.split(':').map(Number);
  return h * 60 + m;
};

const formatTime = (minutes) =>
  `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`;

const escapeHtml = (text) =>
  String(text).replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));

const formatExamDate = (date) => {
  const [y, m, d] = date.split('-');
  const weekday = new Date(`${date}T00:00:00`).toLocaleDateString('en-US', { weekday: 'long' });
  return `${weekday} (${m}/${d}/${y})`;
};

const formatExam = (exam) => {
  if (!exam) return 'No final exam / not scheduled';
  return `${formatExamDate(exam.date)} • ${formatTime(exam.start)}${exam.end != null ? ` - ${formatTime(exam.end)}` : ''}`;
};

const formatFileSize = (bytes) =>
  bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;

// A section without a capacity has unlimited seats.
const isClosed = (section) => section.capacity != null && section.enrolled >= section.capacity;

// Validation messages from the server use **bold** markers.
const plainText = (text) => String(text).replace(/\*\*/g, '');

/* Course plan, loaded from GET /api/schedule/courses */
let COURSES = [];
let COURSE_BY_CODE = {};

function setCourses(list) {
  COURSES = list.map((course, index) => ({
    ...course,
    index,
    sections: course.sections.map((s) => ({ ...s, exam: course.exam })),
  }));
  COURSE_BY_CODE = Object.fromEntries(COURSES.map((c) => [c.code, c]));
}

async function apiFetch(path, options = {}) {
  let res;
  try {
    res = await fetch(`${API_URL}${path}`, options);
  } catch {
    throw new Error(SERVER_DOWN);
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof data.detail === 'string' ? data.detail : `Server error (${res.status})`;
    throw new Error(detail);
  }
  return data;
}

/* Icons used in rendered markup */
const ICONS = {
  clock: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>',
  lock: '<svg fill="currentColor" viewBox="0 0 24 24"><path d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2z"></path></svg>',
  copy: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>',
  room: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path><polyline points="9 22 9 12 15 12 15 22"></polyline></svg>',
  user: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>',
  calendar: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg>',
  emptyCalendar: '<svg fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line><line x1="9" y1="15" x2="15" y2="15"></line></svg>',
};

/* ----------------------------------------------------------
   State
   ---------------------------------------------------------- */
const state = {
  selected: new Set(DEFAULT_SELECTED),
  listFilter: 'all',     // 'all' | 'selected'
  search: '',
  daysOff: 0,
  locks: {},             // { courseCode: sectionId }
  timeFrom: SCALE_START,
  timeTo: SCALE_END,
  includeClosed: false,
  showDetails: true,
  schedules: [],
  truncated: false,
  emptyReason: '',
  index: 0,
  loading: false,
  completed: null,       // Set of plan codes from an imported transcript (null = unknown)
};

/* ----------------------------------------------------------
   Schedule Generator (CSP on the server: POST /api/schedule/generate)
   Hard constraints (time clash, same final-exam slot, seats, locks,
   time range, days off, credit limit, prerequisites) are enforced by
   the solver; this page only lays out what it returns.
   ---------------------------------------------------------- */
function buildSchedule(picks, score) {
  const entries = [...picks].sort((a, b) => a.course.index - b.course.index);
  const meetings = entries.flatMap((e) => e.section.meetings);
  const days = new Set(meetings.map((m) => m.day));

  // Idle minutes between classes on the same day
  let gaps = 0;
  days.forEach((day) => {
    const list = meetings.filter((m) => m.day === day).sort((a, b) => a.start - b.start);
    for (let i = 1; i < list.length; i++) gaps += Math.max(0, list[i].start - list[i - 1].end);
  });

  // Same exam slot is already ruled out by the solver; two finals on the
  // same day is still worth a warning.
  const conflicts = [];
  for (let i = 0; i < entries.length; i++) {
    for (let j = i + 1; j < entries.length; j++) {
      const a = entries[i].section.exam;
      const b = entries[j].section.exam;
      if (a && b && a.date === b.date) {
        conflicts.push({ date: a.date, a: entries[i], b: entries[j] });
      }
    }
  }

  return { entries, daysUsed: days.size, gaps, conflicts, score };
}

function scheduleRequest() {
  return {
    courses: COURSES.filter((c) => state.selected.has(c.code)).map((c) => c.code),
    locks: state.locks,
    time_from: formatTime(state.timeFrom),
    time_to: formatTime(state.timeTo),
    min_days_off: state.daysOff,
    include_closed: state.includeClosed,
    completed_courses: state.completed ? [...state.completed] : null,
    max_credit_hours: MAX_CREDITS,
  };
}

let requestSeq = 0;

async function generateSchedules() {
  const seq = ++requestSeq;
  state.schedules = [];
  state.truncated = false;
  state.emptyReason = '';
  state.index = 0;

  const body = scheduleRequest();
  if (!body.courses.length) {
    state.loading = false;
    return;
  }

  state.loading = true;
  let data;
  try {
    data = await apiFetch('/api/schedule/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  } catch (err) {
    if (seq !== requestSeq) return;
    state.loading = false;
    state.emptyReason = err.message;
    return;
  }
  if (seq !== requestSeq) return; // a newer request replaced this one
  state.loading = false;

  if (data.errors && data.errors.length) {
    state.emptyReason = data.errors.map(plainText).join('\n');
    return;
  }

  const schedules = data.schedules.map((s) =>
    buildSchedule(
      s.picks.map((p) => {
        const course = COURSE_BY_CODE[p.code];
        return { course, section: course.sections.find((sec) => sec.id === p.section) };
      }),
      s.score
    )
  );
  // Server order is best score first; keep it, but push same-day finals back.
  schedules.sort((a, b) => a.conflicts.length - b.conflicts.length);

  state.schedules = schedules;
  state.truncated = data.truncated;
  if (!schedules.length) {
    state.emptyReason = data.failure_reason ||
      'Every combination of the selected courses clashes in time or breaks your filters. Try fewer days off, a wider time range, or unlocking a section.';
  }
}

const currentSchedule = () => state.schedules[state.index] || null;

/* ----------------------------------------------------------
   Rendering: Sidebar
   ---------------------------------------------------------- */
function renderCourseStats() {
  const credits = COURSES.filter((c) => state.selected.has(c.code)).reduce((sum, c) => sum + c.credits, 0);
  $('#stat-selected').textContent = `Selected: ${state.selected.size}`;
  $('#stat-credits').textContent = `Credits: ${credits} / ${MAX_CREDITS}`;
  $('#stat-credits').parentElement.classList.toggle('is-over', credits > MAX_CREDITS);
  $('#filter-all').textContent = `All (${COURSES.length})`;
  $('#filter-selected').textContent = `Selected (${state.selected.size})`;
}

function renderCourseList() {
  const query = state.search.trim().toLowerCase();
  const list = COURSES.filter((c) =>
    (state.listFilter === 'all' || state.selected.has(c.code)) &&
    (!query || c.code.toLowerCase().includes(query) || c.name.toLowerCase().includes(query))
  );

  document.querySelectorAll('.segmented__btn').forEach((btn) =>
    btn.classList.toggle('is-active', btn.dataset.filter === state.listFilter)
  );

  if (!list.length) {
    $('#course-list').innerHTML = `<p class="course-list__empty">${
      query ? `No courses match “${escapeHtml(state.search.trim())}”.` : 'No courses selected yet.'
    }</p>`;
    return;
  }

  $('#course-list').innerHTML = list.map((c) => {
    const selected = state.selected.has(c.code);
    const done = Boolean(state.completed && state.completed.has(c.code));
    const missing = state.completed ? c.prerequisites.filter((p) => !state.completed.has(p.code)) : [];
    const tags = [
      c.elective ? 'Elective' : '',
      done ? 'Completed' : '',
      !done && missing.length ? `Needs ${missing.map((p) => p.name).join(', ')}` : '',
    ].filter(Boolean).map((t) => ` • ${escapeHtml(t)}`).join('');
    const prereqTitle = c.prerequisites.length
      ? `Prerequisites: ${c.prerequisites.map((p) => `${p.name} (${p.code})`).join(', ')}`
      : 'No prerequisites';
    return `
      <label class="course-item${selected ? ' is-selected' : ''}" style="--c: ${c.color}${done ? '; opacity: .5' : ''}" title="${escapeHtml(prereqTitle)}">
        <input type="checkbox" class="course-item__check" data-code="${escapeHtml(c.code)}" ${selected ? 'checked' : ''} ${done ? 'disabled' : ''}>
        <span class="course-item__text">
          <span class="course-item__name" dir="auto">${escapeHtml(c.name)}</span>
          <span class="course-item__meta">${escapeHtml(c.code)} • ${c.credits} Credit Hrs • ${c.sections.length} Section${c.sections.length === 1 ? '' : 's'}${tags}</span>
        </span>
        <span class="course-item__dot"></span>
      </label>`;
  }).join('');
}

function renderDaysOff() {
  $('#days-off-badge').textContent = `${state.daysOff} Day${state.daysOff === 1 ? '' : 's'}`;
  document.querySelectorAll('.days-off__btn').forEach((btn) =>
    btn.classList.toggle('is-active', Number(btn.dataset.days) === state.daysOff)
  );
}

function renderLocks() {
  const courses = COURSES.filter((c) => state.selected.has(c.code));
  $('#lock-badge').textContent = `${Object.keys(state.locks).length} Locked`;

  if (!courses.length) {
    $('#lock-list').innerHTML = '<p class="muted-note">Select courses to lock their sections.</p>';
    return;
  }

  $('#lock-list').innerHTML = courses.map((c) => {
    const locked = state.locks[c.code];
    const chips = c.sections.map((s) => {
      const closed = isClosed(s);
      const disabled = closed && !state.includeClosed;
      const isLocked = locked === s.id;
      return `
        <button type="button" class="chip${isLocked ? ' is-locked' : ''}" data-lock="${c.code}" data-section="${s.id}"
          ${disabled ? 'disabled title="Section is full — enable “Include Closed Sections”"' : ''}>
          ${isLocked ? ICONS.lock : ''}${s.id}${closed ? ' <small>Full</small>' : ''}
        </button>`;
    }).join('');

    return `
      <div class="lock-row" style="--c: ${c.color}">
        <div class="lock-row__head">
          <span>${escapeHtml(c.short)} (${c.code})</span>
          <span class="lock-row__status${locked ? ' is-locked' : ''}">${locked ? `Locked: ${locked}` : 'Any section'}</span>
        </div>
        <div class="lock-row__chips">${chips}</div>
      </div>`;
  }).join('');
}

function renderTimeRange() {
  $('#time-from').value = state.timeFrom;
  $('#time-to').value = state.timeTo;
  $('#range-from').value = state.timeFrom;
  $('#range-to').value = state.timeTo;
  $('#time-badge').textContent = `${formatTime(state.timeFrom)} — ${formatTime(state.timeTo)}`;

  const span = SCALE_END - SCALE_START;
  const left = ((state.timeFrom - SCALE_START) / span) * 100;
  const right = ((SCALE_END - state.timeTo) / span) * 100;
  $('#range-fill').style.left = `${left}%`;
  $('#range-fill').style.right = `${right}%`;
}

function renderSidebar() {
  renderCourseStats();
  renderCourseList();
  renderDaysOff();
  renderLocks();
  renderTimeRange();
  $('#include-closed').checked = state.includeClosed;
}

/* ----------------------------------------------------------
   Rendering: Results
   ---------------------------------------------------------- */
function scheduleBounds(schedule) {
  const meetings = schedule.entries.flatMap((e) => e.section.meetings);
  const start = Math.floor(Math.min(...meetings.map((m) => m.start)) / 60) * 60;
  const end = Math.ceil(Math.max(...meetings.map((m) => m.end)) / 60) * 60;
  return { start, end };
}

function renderToolbar() {
  const total = state.schedules.length;
  $('#result-count').textContent = `${total}${state.truncated ? '+' : ''} Schedule${total === 1 ? '' : 's'}`;
  $('#page-current').textContent = total ? state.index + 1 : 0;
  $('#page-total').textContent = total;
  $('#prev-btn').disabled = state.index <= 0;
  $('#next-btn').disabled = state.index >= total - 1;
  $('#save-image-btn').disabled = !total;
  $('#copy-all-btn').disabled = !total;
}

function renderConflictBanner(schedule) {
  const banner = $('#conflict-banner');
  if (!schedule || !schedule.conflicts.length) {
    banner.hidden = true;
    return;
  }

  const [first, ...rest] = schedule.conflicts;
  const label = (entry) => `${escapeHtml(entry.course.short)} (${entry.course.code})`;
  $('#conflict-text').innerHTML = `
    <strong>Two Final Exams on the Same Day:</strong>
    <span class="conflict-banner__date">${formatExamDate(first.date)}</span>
    <span class="conflict-banner__muted">between</span>
    <span class="conflict-chip">${label(first.a)}</span>
    <span class="conflict-banner__muted">and</span>
    <span class="conflict-chip">${label(first.b)}</span>
    ${rest.length ? `<span class="conflict-banner__muted">+${rest.length} more</span>` : ''}`;
  banner.hidden = false;
}

function renderEmptyTimetable() {
  const noCourses = state.selected.size === 0;
  const title = noCourses ? 'No courses selected' : state.loading ? 'Generating schedules…' : 'No schedules found';
  const text = noCourses
    ? 'Select courses from the sidebar to start building your schedule.'
    : state.loading ? 'The CSP solver is checking every constraint.' : state.emptyReason;
  $('#timetable').innerHTML = `
    <div class="timetable__empty">
      ${ICONS.emptyCalendar}
      <h3>${title}</h3>
      <p dir="auto" style="white-space: pre-line">${escapeHtml(text)}</p>
    </div>`;
}

function renderTimetable(schedule) {
  if (!schedule) {
    renderEmptyTimetable();
    return;
  }

  const { start, end } = scheduleBounds(schedule);
  const hours = (end - start) / 60;
  const height = hours * ROW_HEIGHT;
  const usedDays = new Set(schedule.entries.flatMap((e) => e.section.meetings.map((m) => m.day)));

  const head = DAY_NAMES.map((name, day) =>
    `<div class="${usedDays.has(day) ? '' : 'is-off'}">${name}</div>`
  ).join('') + '<div class="is-time">Time</div>';

  const columns = DAY_NAMES.map((_, day) => {
    const blocks = schedule.entries.flatMap(({ course, section }) =>
      section.meetings
        .filter((m) => m.day === day)
        .map((m) => {
          const top = ((m.start - start) / 60) * ROW_HEIGHT + 3;
          const blockHeight = ((m.end - m.start) / 60) * ROW_HEIGHT - 6;
          const isLab = m.type !== 'Lecture';
          const title = isLab ? `${course.short} ${m.type}` : `${course.short} (${course.code})`;
          return `
            <div class="tt-block${isLab ? ' tt-block--lab' : ''}" style="--c: ${course.color}; top: ${top}px; height: ${blockHeight}px"
              title="${escapeHtml(course.name)} — ${section.id} • ${formatTime(m.start)}-${formatTime(m.end)}${m.room ? ` • Rm ${m.room}` : ''}">
              <div class="tt-block__top">
                <span class="tt-block__title" dir="auto">${escapeHtml(title)}</span>
                <span class="tt-block__badge">${section.id}</span>
              </div>
              <div class="tt-block__bottom">
                <span>${ICONS.clock}${formatTime(m.start)} - ${formatTime(m.end)}</span>
                ${m.room ? `<span class="tt-block__room">Rm ${m.room}</span>` : ''}
              </div>
            </div>`;
        })
    ).join('');

    const off = !usedDays.has(day);
    return `<div class="tt-col${off ? ' is-off' : ''}" style="height: ${height}px">
      ${off ? '<span class="tt-col__off-label">Day off</span>' : blocks}
    </div>`;
  }).join('');

  const labels = Array.from({ length: hours }, (_, i) =>
    `<span class="tt-time__label" style="top: ${i * ROW_HEIGHT}px">${formatTime(start + i * 60)}</span>`
  ).join('');

  $('#timetable').innerHTML = `
    <div class="timetable__head">${head}</div>
    <div class="timetable__body">${columns}<div class="tt-time" style="height: ${height}px">${labels}</div></div>`;
}

function renderLegend(schedule) {
  $('#summary').hidden = !schedule;
  if (!schedule) return;

  const credits = schedule.entries.reduce((sum, e) => sum + e.course.credits, 0);
  $('#legend').innerHTML = schedule.entries.map(({ course }) => `
    <span class="legend-item" style="--c: ${course.color}">
      <span class="legend-item__swatch"></span>
      <strong>${course.code}</strong> (${escapeHtml(course.short)})
    </span>`).join('') +
    `<span>•</span><span class="summary__total">Total Credit Hours: <strong>${credits} Hrs</strong></span>`;
}

function groupMeetings(meetings) {
  const groups = new Map();
  meetings.forEach((m) => {
    const key = `${m.start}-${m.end}-${m.room}-${m.type}`;
    if (!groups.has(key)) groups.set(key, { ...m, days: [] });
    groups.get(key).days.push(m.day);
  });
  return [...groups.values()];
}

function renderDetails(schedule) {
  $('#details').hidden = !schedule || !state.showDetails;
  $('#toggle-details-btn').setAttribute('aria-expanded', String(state.showDetails));
  if (!schedule) return;

  const conflictCodes = new Set(schedule.conflicts.flatMap((c) => [c.a.course.code, c.b.course.code]));

  $('#details-grid').innerHTML = schedule.entries.map(({ course, section }) => {
    const rooms = [...new Set(section.meetings.map((m) => m.room).filter(Boolean))].join(', ');
    const times = groupMeetings(section.meetings).map((g) => `
      <div class="info-row">
        <span class="info-row__main">${ICONS.clock}
          <span>${g.days.map((d) => DAY_NAMES[d]).join(', ')}: ${formatTime(g.start)} - ${formatTime(g.end)}</span>
          ${g.type !== 'Lecture' ? `<span class="type-tag">${g.type}</span>` : ''}
        </span>
        <span class="info-row__aside">${g.room}</span>
      </div>`).join('');

    return `
      <article class="section-card" style="--c: ${course.color}">
        <div class="section-card__main">
          <div class="section-card__top">
            <div>
              <h4 class="section-card__name" dir="auto">${escapeHtml(course.name)}</h4>
              <div class="section-card__code">${course.code} • ${course.credits} Credit Hrs</div>
            </div>
            <span class="section-card__badge">Section ${section.id}</span>
          </div>

          <div class="section-card__stats">
            <div class="seats">
              <span class="section-card__label">Seats:</span>
              <span class="seats__value${isClosed(section) ? ' is-full' : ''}">${section.capacity == null ? 'Open' : `${section.enrolled} / ${section.capacity}`}${isClosed(section) ? ' Full' : ''}</span>
            </div>
            <div class="crn">
              <span class="section-card__label">CRN:</span>
              <span class="crn__value">${section.crn}</span>
              <button type="button" class="crn__copy" data-copy="${section.crn}" title="Copy CRN" aria-label="Copy CRN ${section.crn}">${ICONS.copy}</button>
            </div>
          </div>

          <div class="info-list">
            ${times}
            ${rooms ? `<div class="info-row">
              <span class="info-row__main">${ICONS.room}<span>Room: <strong>${rooms}</strong></span></span>
            </div>` : ''}
            <div class="info-row">
              <span class="info-row__main">${ICONS.user}
                <span class="instructor${section.instructor ? '' : ' is-tba'}">${escapeHtml(section.instructor || 'To Be Announced')}</span>
              </span>
            </div>
          </div>
        </div>

        <div class="section-card__exam${conflictCodes.has(course.code) ? ' is-conflict' : ''}">
          ${ICONS.calendar}
          <div>
            <span class="section-card__label">Final Exam:</span>
            <span class="section-card__exam-value">${formatExam(section.exam)}</span>
          </div>
        </div>
      </article>`;
  }).join('');
}

function renderResults() {
  const schedule = currentSchedule();
  renderToolbar();
  renderConflictBanner(schedule);
  renderTimetable(schedule);
  renderLegend(schedule);
  renderDetails(schedule);
}

/* Regenerate + redraw everything. The sidebar redraws at once; the solver
   call is debounced so dragging the time slider doesn't flood the server. */
let updateTimer;
let pendingUpdate = null;
function update() {
  renderSidebar();
  state.loading = state.selected.size > 0;
  state.schedules = [];
  renderResults();
  clearTimeout(updateTimer);
  if (!pendingUpdate) {
    let resolve;
    pendingUpdate = { promise: new Promise((r) => { resolve = r; }), resolve };
  }
  const pending = pendingUpdate;
  updateTimer = setTimeout(async () => {
    pendingUpdate = null;
    const seq = requestSeq + 1;
    await generateSchedules();
    if (seq === requestSeq) renderResults();
    pending.resolve();
  }, 200);
  return pending.promise;
}

/* ----------------------------------------------------------
   Toast & Clipboard
   ---------------------------------------------------------- */
let toastTimer;
function showToast(message) {
  const toast = $('#toast');
  toast.textContent = message;
  toast.classList.add('is-visible');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove('is-visible'), 2600);
}

function copyText(text, message) {
  const fallback = () => {
    const area = document.createElement('textarea');
    area.value = text;
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand('copy');
    area.remove();
    showToast(ok ? message : 'Could not copy — please copy manually');
  };

  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(() => showToast(message), fallback);
  } else {
    fallback();
  }
}

/* ----------------------------------------------------------
   Save Image (draws the current timetable onto a canvas)
   ---------------------------------------------------------- */
function hexToRgba(hex, alpha) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

function mixWithWhite(hex, amount) {
  const n = parseInt(hex.slice(1), 16);
  const mix = (c) => Math.round(c + (255 - c) * amount);
  return `rgb(${mix((n >> 16) & 255)}, ${mix((n >> 8) & 255)}, ${mix(n & 255)})`;
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function fitText(ctx, text, maxWidth) {
  if (ctx.measureText(text).width <= maxWidth) return text;
  let trimmed = text;
  while (trimmed.length > 1 && ctx.measureText(`${trimmed}…`).width > maxWidth) trimmed = trimmed.slice(0, -1);
  return `${trimmed}…`;
}

async function saveImage() {
  const schedule = currentSchedule();
  if (!schedule) return;
  if (document.fonts && document.fonts.ready) await document.fonts.ready;

  const { start, end } = scheduleBounds(schedule);
  const hours = (end - start) / 60;
  const pad = 24, headerH = 60, dayHeadH = 36, rowH = 64, timeW = 70, width = 1000;
  const gridW = width - pad * 2;
  const colW = (gridW - timeW) / 5;
  const gridTop = pad + headerH;
  const height = gridTop + dayHeadH + hours * rowH + pad;
  const scale = 2;

  const canvas = document.createElement('canvas');
  canvas.width = width * scale;
  canvas.height = height * scale;
  const ctx = canvas.getContext('2d');
  ctx.scale(scale, scale);

  // Background & title
  ctx.fillStyle = '#0c0f10';
  ctx.fillRect(0, 0, width, height);
  ctx.fillStyle = '#ffffff';
  ctx.font = '700 18px Inter, sans-serif';
  ctx.fillText('Academic AI — Study Schedule', pad, pad + 18);
  const credits = schedule.entries.reduce((sum, e) => sum + e.course.credits, 0);
  ctx.fillStyle = '#8b949e';
  ctx.font = '500 12px Inter, sans-serif';
  ctx.fillText(
    `Option ${state.index + 1} of ${state.schedules.length} • ${credits} credit hours • ` +
    schedule.entries.map((e) => `${e.course.code} ${e.section.id} (CRN ${e.section.crn})`).join('  ·  '),
    pad, pad + 40
  );

  // Grid frame
  roundRect(ctx, pad, gridTop, gridW, dayHeadH + hours * rowH, 12);
  ctx.fillStyle = '#111415';
  ctx.fill();
  ctx.strokeStyle = '#2a2e30';
  ctx.lineWidth = 1;
  ctx.stroke();

  // Day headers & column lines
  ctx.textAlign = 'center';
  ctx.font = '600 12px Inter, sans-serif';
  DAY_NAMES.forEach((name, d) => {
    ctx.fillStyle = '#e2e8f0';
    ctx.fillText(name, pad + d * colW + colW / 2, gridTop + 23);
  });
  ctx.fillStyle = '#8b949e';
  ctx.font = '600 11px "JetBrains Mono", monospace';
  ctx.fillText('TIME', pad + 5 * colW + timeW / 2, gridTop + 23);

  ctx.beginPath();
  for (let d = 1; d <= 5; d++) {
    ctx.moveTo(pad + d * colW + 0.5, gridTop);
    ctx.lineTo(pad + d * colW + 0.5, gridTop + dayHeadH + hours * rowH);
  }
  for (let h = 0; h < hours; h++) {
    const y = gridTop + dayHeadH + h * rowH + 0.5;
    ctx.moveTo(pad, y);
    ctx.lineTo(pad + gridW, y);
  }
  ctx.stroke();

  // Time labels
  ctx.font = '700 11px "JetBrains Mono", monospace';
  for (let h = 0; h < hours; h++) {
    ctx.fillText(formatTime(start + h * 60), pad + 5 * colW + timeW / 2, gridTop + dayHeadH + h * rowH + rowH / 2 + 4);
  }

  // Course blocks
  ctx.textAlign = 'left';
  schedule.entries.forEach(({ course, section }) => {
    section.meetings.forEach((m) => {
      const x = pad + m.day * colW + 4;
      const y = gridTop + dayHeadH + ((m.start - start) / 60) * rowH + 3;
      const w = colW - 8;
      const h = ((m.end - m.start) / 60) * rowH - 6;

      roundRect(ctx, x, y, w, h, 8);
      ctx.fillStyle = hexToRgba(course.color, m.type === 'Lecture' ? 0.16 : 0.09);
      ctx.fill();
      ctx.strokeStyle = hexToRgba(course.color, m.type === 'Lecture' ? 0.85 : 0.55);
      ctx.stroke();

      ctx.fillStyle = mixWithWhite(course.color, 0.55);
      ctx.font = '700 11px Inter, sans-serif';
      const title = m.type === 'Lecture' ? `${course.short} · ${section.id}` : `${course.short} ${m.type} · ${section.id}`;
      ctx.fillText(fitText(ctx, title, w - 16), x + 8, y + 16);

      ctx.font = '500 10px "JetBrains Mono", monospace';
      ctx.fillText(`${formatTime(m.start)}-${formatTime(m.end)}${m.room ? `  Rm ${m.room}` : ''}`, x + 8, Math.min(y + h - 8, y + 32));
    });
  });

  const link = document.createElement('a');
  link.download = `academic-ai-schedule-${state.index + 1}.png`;
  link.href = canvas.toDataURL('image/png');
  link.click();
  showToast('Schedule image saved');
}

/* ----------------------------------------------------------
   Import Academic Record Modal
   ---------------------------------------------------------- */
let importSource = null;   // { name, size, file }
let processing = false;

function renderImport() {
  const hasFile = Boolean(importSource);
  $('#dz-empty').hidden = hasFile;
  $('#dz-file').hidden = !hasFile;
  $('#dropzone').classList.toggle('has-file', hasFile);
  $('#process-btn').disabled = !hasFile || processing;

  if (hasFile) {
    $('#dz-file-name').textContent = importSource.name;
    $('#dz-file-meta').textContent = `${formatFileSize(importSource.size)} • Ready to process`;
  }
}

function setImportError(message) {
  const error = $('#dz-error');
  error.textContent = message || '';
  error.hidden = !message;
}

function openImportModal() {
  $('#import-modal').hidden = false;
  document.body.classList.add('modal-open');
  $('#dropzone').focus();
}

function closeImportModal() {
  if (processing) return;
  $('#import-modal').hidden = true;
  document.body.classList.remove('modal-open');
  importSource = null;
  $('#file-input').value = '';
  setImportError('');
  renderImport();
}

function handleFile(file) {
  if (!file) return;
  const valid = /\.pdf$/i.test(file.name);
  if (!valid) {
    setImportError('Unsupported file type. Please upload your transcript as a PDF.');
    return;
  }
  if (file.size > MAX_UPLOAD_SIZE) {
    setImportError('File is too large. The maximum size is 15MB.');
    return;
  }
  setImportError('');
  importSource = { name: file.name, size: file.size, file };
  renderImport();
}

function setUser(student) {
  if (!student) return;
  if (student.name) {
    $('.user__name').textContent = student.name;
    const initials = student.name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join('');
    $('.user__avatar').textContent = initials.toUpperCase();
  }
  if (student.id) $('.user__id').textContent = student.id;
}

async function processImport() {
  if (!importSource || processing) return;
  processing = true;
  setImportError('');
  const button = $('#process-btn');
  button.disabled = true;
  $('#process-label').textContent = 'Processing…';
  button.querySelector('svg').outerHTML = '<span class="spinner"></span>';

  const finish = () => {
    processing = false;
    $('#process-label').textContent = 'Process Transcript & Auto-fill';
    button.querySelector('.spinner').outerHTML = '<svg fill="none" stroke="currentColor" stroke-width="2.2" viewBox="0 0 24 24"><polyline points="9 18 15 12 9 6"></polyline></svg>';
    renderImport();
  };

  // The transcript is parsed on the server (pdfplumber) and mapped to plan codes.
  const form = new FormData();
  form.append('file', importSource.file, importSource.name);
  let data;
  try {
    data = await apiFetch('/api/schedule/transcript', { method: 'POST', body: form });
  } catch (err) {
    finish();
    setImportError(err.message);
    return;
  }
  finish();

  if (!data.parsed_courses) {
    setImportError(data.warnings[0] || 'No courses were found in this file.');
    return;
  }

  const name = importSource.name;
  state.completed = new Set(data.completed);
  state.selected = new Set(data.suggested);
  state.locks = {};
  state.listFilter = 'selected';
  setUser(data.student);

  closeImportModal();
  update();
  const gpa = data.gpa != null ? ` • GPA ${data.gpa}` : '';
  showToast(`${name}: ${data.completed.length} completed courses${gpa} — suggested ${data.suggested.length} courses`);
}

/* ----------------------------------------------------------
   Events
   ---------------------------------------------------------- */
function fillTimeSelects() {
  const options = [];
  for (let t = SCALE_START; t <= SCALE_END; t += TIME_STEP) {
    options.push(`<option value="${t}">${formatTime(t)}</option>`);
  }
  $('#time-from').innerHTML = options.join('');
  $('#time-to').innerHTML = options.join('');
}

function setTimeRange(from, to, changed) {
  // Keep at least one step between the handles
  if (to - from < TIME_STEP) {
    if (changed === 'from') from = to - TIME_STEP;
    else to = from + TIME_STEP;
  }
  state.timeFrom = Math.max(SCALE_START, from);
  state.timeTo = Math.min(SCALE_END, to);
  if (state.timeTo - state.timeFrom < TIME_STEP) state.timeFrom = state.timeTo - TIME_STEP;
  update();
}

function resetAll() {
  state.selected = new Set(DEFAULT_SELECTED);
  state.listFilter = 'all';
  state.search = '';
  state.daysOff = 0;
  state.locks = {};
  state.timeFrom = SCALE_START;
  state.timeTo = SCALE_END;
  state.includeClosed = false;
  $('#course-search').value = '';
  update();
  showToast('Filters reset');
}

function bindEvents() {
  // Header
  $('#sign-out-btn').addEventListener('click', signOut);
  $('#notifications-btn').addEventListener('click', () => showToast('No new notifications'));
  $('#settings-btn').addEventListener('click', () => showToast('Settings are coming soon'));

  // Courses
  $('#course-search').addEventListener('input', (e) => {
    state.search = e.target.value;
    renderCourseList();
  });

  $('#course-filter').addEventListener('click', (e) => {
    const btn = e.target.closest('[data-filter]');
    if (!btn) return;
    state.listFilter = btn.dataset.filter;
    renderCourseList();
  });

  $('#course-list').addEventListener('change', (e) => {
    const code = e.target.dataset.code;
    if (!code) return;
    if (e.target.checked) {
      state.selected.add(code);
    } else {
      state.selected.delete(code);
      delete state.locks[code];
    }
    update();
  });

  // Days off
  $('#days-off').addEventListener('click', (e) => {
    const btn = e.target.closest('[data-days]');
    if (!btn) return;
    state.daysOff = Number(btn.dataset.days);
    update();
  });

  // Section locks
  $('#lock-list').addEventListener('click', (e) => {
    const chip = e.target.closest('[data-lock]');
    if (!chip || chip.disabled) return;
    const { lock: code, section } = chip.dataset;
    if (state.locks[code] === section) delete state.locks[code];
    else state.locks[code] = section;
    update();
  });

  // Time range
  $('#time-from').addEventListener('change', (e) => setTimeRange(Number(e.target.value), state.timeTo, 'from'));
  $('#time-to').addEventListener('change', (e) => setTimeRange(state.timeFrom, Number(e.target.value), 'to'));
  $('#range-from').addEventListener('input', (e) => setTimeRange(Number(e.target.value), state.timeTo, 'from'));
  $('#range-to').addEventListener('input', (e) => setTimeRange(state.timeFrom, Number(e.target.value), 'to'));

  // Closed sections
  $('#include-closed').addEventListener('change', (e) => {
    state.includeClosed = e.target.checked;
    if (!state.includeClosed) {
      Object.entries(state.locks).forEach(([code, id]) => {
        const section = COURSE_BY_CODE[code].sections.find((s) => s.id === id);
        if (section && isClosed(section)) delete state.locks[code];
      });
    }
    update();
  });

  // Generate & reset
  $('#generate-btn').addEventListener('click', async () => {
    await update();
    const total = state.schedules.length;
    showToast(total ? `Generated ${total}${state.truncated ? '+' : ''} schedule${total === 1 ? '' : 's'}` : 'No schedules match your filters');
    if (window.innerWidth < 1024) $('.content').scrollIntoView({ behavior: 'smooth' });
  });
  $('#reset-btn').addEventListener('click', resetAll);

  // Pagination
  $('#prev-btn').addEventListener('click', () => {
    if (state.index > 0) {
      state.index--;
      renderResults();
    }
  });
  $('#next-btn').addEventListener('click', () => {
    if (state.index < state.schedules.length - 1) {
      state.index++;
      renderResults();
    }
  });
  document.addEventListener('keydown', (e) => {
    if (!$('#import-modal').hidden || e.target.matches('input, select, textarea')) return;
    if (e.key === 'ArrowLeft') $('#prev-btn').click();
    if (e.key === 'ArrowRight') $('#next-btn').click();
  });

  // Resolve exam conflict → jump to the next conflict-free schedule
  $('#resolve-btn').addEventListener('click', () => {
    const total = state.schedules.length;
    for (let step = 1; step < total; step++) {
      const i = (state.index + step) % total;
      if (!state.schedules[i].conflicts.length) {
        state.index = i;
        renderResults();
        showToast(`Switched to schedule ${i + 1} — no two finals on the same day`);
        return;
      }
    }
    showToast('Every matching schedule has two finals on one day — try a different course or section');
  });

  // Toolbar & details
  $('#save-image-btn').addEventListener('click', saveImage);
  $('#toggle-details-btn').addEventListener('click', () => {
    state.showDetails = !state.showDetails;
    renderDetails(currentSchedule());
  });
  $('#copy-all-btn').addEventListener('click', () => {
    const schedule = currentSchedule();
    if (!schedule) return;
    const crns = schedule.entries.map((e) => e.section.crn).join(', ');
    copyText(crns, `Copied ${schedule.entries.length} CRNs: ${crns}`);
  });
  $('#details-grid').addEventListener('click', (e) => {
    const btn = e.target.closest('[data-copy]');
    if (btn) copyText(btn.dataset.copy, `Copied CRN ${btn.dataset.copy}`);
  });

  // Import modal
  const dropzone = $('#dropzone');
  const fileInput = $('#file-input');

  $('#open-import-btn').addEventListener('click', openImportModal);
  document.querySelectorAll('[data-close-modal]').forEach((el) => el.addEventListener('click', closeImportModal));
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !$('#import-modal').hidden) closeImportModal();
  });

  dropzone.addEventListener('click', (e) => {
    if (e.target.closest('#dz-remove')) return;
    fileInput.click();
  });
  dropzone.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      fileInput.click();
    }
  });
  fileInput.addEventListener('change', () => handleFile(fileInput.files[0]));

  ['dragenter', 'dragover'].forEach((type) =>
    dropzone.addEventListener(type, (e) => {
      e.preventDefault();
      dropzone.classList.add('is-dragging');
    })
  );
  ['dragleave', 'drop'].forEach((type) =>
    dropzone.addEventListener(type, (e) => {
      e.preventDefault();
      dropzone.classList.remove('is-dragging');
    })
  );
  dropzone.addEventListener('drop', (e) => handleFile(e.dataTransfer.files[0]));

  $('#dz-remove').addEventListener('click', (e) => {
    e.stopPropagation();
    importSource = null;
    fileInput.value = '';
    renderImport();
  });

  $('#process-btn').addEventListener('click', processImport);
}

/* ----------------------------------------------------------
   Init
   ---------------------------------------------------------- */
async function loadCourses() {
  try {
    const data = await apiFetch('/api/schedule/courses');
    setCourses(data.courses);
    MAX_CREDITS = data.default_max_credits || MAX_CREDITS;
    return true;
  } catch (err) {
    state.selected = new Set();
    renderSidebar();
    $('#course-list').innerHTML = `<p class="course-list__empty">${escapeHtml(err.message)}</p>`;
    return false;
  }
}

document.addEventListener('DOMContentLoaded', async () => {
  fillTimeSelects();
  bindEvents();
  if (await loadCourses()) update();
});
