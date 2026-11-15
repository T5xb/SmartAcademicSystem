/* ==========================================================
   Academic AI - Study Schedule Planner
   ========================================================== */

/* ----------------------------------------------------------
   Session (frontend/shared/auth.js): the planner is the student's
   ---------------------------------------------------------- */
const signOut = Auth.signOut;

/* ----------------------------------------------------------
   Constants
   ---------------------------------------------------------- */
const DAY_COUNT = 5;                 // Sunday - Thursday
const SCALE_START = 8 * 60;          // 08:00
const SCALE_END = 24 * 60;           // 24:00
const TIME_STEP = 30;                // minutes
let MAX_CREDITS = 18;                 // replaced by the server's default on load
const ROW_HEIGHT = 96;               // px per hour (matches --row-height)

// The CSP scheduler runs in fastapi_app.py (src/scheduling) — same server as the chatbot.
const apiFetch = Auth.api;

const DEFAULT_SELECTED = ['ريض 1112', 'عال 1140', 'عال 1220'];
const MAX_UPLOAD_SIZE = 15 * 1024 * 1024;

/* ----------------------------------------------------------
   Helpers
   ---------------------------------------------------------- */
const $ = (selector) => document.querySelector(selector);

const formatTime = (minutes) =>
  `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`;

const escapeHtml = (text) =>
  String(text).replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));

const tr = (key, vars) => I18n.t(key, vars);

// "1 Section" / "2 Sections": picks the .one / .two / .other string of a key.
function plural(base, n, shown = n) {
  const key = `${base}.${n === 1 ? 'one' : n === 2 ? 'two' : 'other'}`;
  const text = I18n.t(key, { n: shown });
  return text === key ? I18n.t(`${base}.other`, { n: shown }) : text;
}

const dayName = (day) => tr(`schedule.day.${day}`);
const dayList = (days) => days.map(dayName).join(tr('schedule.listSep'));

// Meeting types come from the server ('Lecture', 'Lab'...); unknown ones show as they are.
const typeLabel = (type) => {
  const key = `schedule.type.${type}`;
  const text = I18n.t(key);
  return text === key ? type : text;
};

// Times, codes and ids keep left-to-right order inside Arabic sentences.
const ltr = (html) => `<bdi dir="ltr">${html}</bdi>`;
const timeRange = (start, end) => `${formatTime(start)} - ${formatTime(end)}`;

const formatExamDate = (date) => {
  const [y, m, d] = date.split('-');
  const weekday = I18n.date(new Date(`${date}T00:00:00`), { weekday: 'long' });
  return `${weekday} (${m}/${d}/${y})`;
};

const formatExam = (exam) => {
  if (!exam) return escapeHtml(tr('schedule.noExam'));
  const times = `${formatTime(exam.start)}${exam.end != null ? ` - ${formatTime(exam.end)}` : ''}`;
  return `${escapeHtml(formatExamDate(exam.date))} • ${ltr(times)}`;
};

const formatFileSize = (bytes) =>
  bytes >= 1024 * 1024
    ? `${(bytes / 1024 / 1024).toFixed(1)} ${tr('schedule.mb')}`
    : `${Math.max(1, Math.round(bytes / 1024))} ${tr('schedule.kb')}`;

// A section without a capacity has unlimited seats.
const isClosed = (section) => section.capacity != null && section.enrolled >= section.capacity;

// Validation messages from the server use **bold** markers.
const plainText = (text) => String(text).replace(/\*\*/g, '');

/* The scheduling service words its messages in Arabic. In English mode the
   known ones are mapped back here (names inside them are data and stay). */
const SERVER_MESSAGES = [
  [/^لا يمكنك تسجيل \[ (.+?) \] لأنك لم تجتز متطلبه السابق \[ (.+?) \]$/s, 'schedule.srv.prereq', ['a', 'b']],
  [/^⚠️ إجمالي الساعات المختارة \((\d+) ساعة\) يتجاوز الحد الأقصى المسموح \((\d+) ساعة\)\. الرجاء إزالة بعض المقررات\.$/s, 'schedule.srv.credits', ['total', 'max']],
  [/^⚠️ اخترت (\d+) مقررات من مجموعة الاختياريات \((.+)\)، والمسموح به حسب الخطة هو (\d+) فقط\. الرجاء إزالة البعض\.$/s, 'schedule.srv.electives', ['n', 'names', 'max']],
  [/^لا توجد أي شعبة متاحة ضمن القيود المحددة \(الأيام\/الوقت\/السعة\/الشعبة المثبتة\) للمقرر التالي: (.+)\.$/s, 'schedule.srv.noSection', ['names']],
  [/^تعذّر إيجاد جدول خالٍ من التعارض\. أعمق نقطة وصل إليها البحث كانت عند إسناد مقرر «(.+?)» .*$/s, 'schedule.srv.deepest', ['name']],
  [/^تعذّر إيجاد جدول خالٍ من التعارض\.$/, 'schedule.srv.noSchedule', []],
  [/^تعذّر تحليل صف: (.+)$/s, 'schedule.srv.parseRow', ['row']],
  [/^لم يتم العثور على أي مقررات في الملف .*$/s, 'schedule.srv.noCourses', []],
];

function serverText(message) {
  const text = plainText(message || '');
  if (I18n.lang === 'ar') return text;
  for (const [re, key, names] of SERVER_MESSAGES) {
    const m = text.match(re);
    if (m) return tr(key, Object.fromEntries(names.map((n, i) => [n, m[i + 1]])));
  }
  return text;
}

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
  emptyReason: null,     // function returning the text (so it follows the language)
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
  state.emptyReason = null;
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
    const message = err.message;
    state.emptyReason = () => message;
    return;
  }
  if (seq !== requestSeq) return; // a newer request replaced this one
  state.loading = false;

  if (data.errors && data.errors.length) {
    const errors = data.errors;
    state.emptyReason = () => errors.map(serverText).join('\n');
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
    const reason = data.failure_reason;
    state.emptyReason = () => (reason ? serverText(reason) : tr('schedule.noFit'));
  }
}

const currentSchedule = () => state.schedules[state.index] || null;

/* ----------------------------------------------------------
   Rendering: Sidebar
   ---------------------------------------------------------- */
function renderCourseStats() {
  const credits = COURSES.filter((c) => state.selected.has(c.code)).reduce((sum, c) => sum + c.credits, 0);
  $('#stat-selected').textContent = tr('schedule.selected', { n: state.selected.size });
  $('#stat-credits').textContent = tr('schedule.credits', { n: credits, max: MAX_CREDITS });
  $('#stat-credits').parentElement.classList.toggle('is-over', credits > MAX_CREDITS);
  $('#filter-all').textContent = tr('schedule.filterAll', { n: COURSES.length });
  $('#filter-selected').textContent = tr('schedule.filterSelected', { n: state.selected.size });
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
      query ? escapeHtml(tr('schedule.noMatch', { q: state.search.trim() })) : escapeHtml(tr('schedule.noneSelected'))
    }</p>`;
    return;
  }

  $('#course-list').innerHTML = list.map((c) => {
    const selected = state.selected.has(c.code);
    const done = Boolean(state.completed && state.completed.has(c.code));
    const missing = state.completed ? c.prerequisites.filter((p) => !state.completed.has(p.code)) : [];
    const tags = [
      c.elective ? tr('schedule.elective') : '',
      done ? tr('schedule.completed') : '',
      !done && missing.length ? tr('schedule.needs', { list: missing.map((p) => p.name).join(tr('schedule.listSep')) }) : '',
    ].filter(Boolean).map((tag) => ` • ${escapeHtml(tag)}`).join('');
    const prereqTitle = c.prerequisites.length
      ? tr('schedule.prereqs', { list: c.prerequisites.map((p) => `${p.name} (${p.code})`).join(tr('schedule.listSep')) })
      : tr('schedule.noPrereqs');
    return `
      <label class="course-item${selected ? ' is-selected' : ''}" style="--c: ${escapeHtml(c.color)}${done ? '; opacity: .5' : ''}" title="${escapeHtml(prereqTitle)}">
        <input type="checkbox" class="course-item__check" data-code="${escapeHtml(c.code)}" ${selected ? 'checked' : ''} ${done ? 'disabled' : ''}>
        <span class="course-item__text">
          <span class="course-item__name" dir="auto">${escapeHtml(c.name)}</span>
          <span class="course-item__meta">${ltr(escapeHtml(c.code))} • ${escapeHtml(tr('schedule.creditHrs', { n: c.credits }))} • ${escapeHtml(plural('schedule.sections', c.sections.length))}${tags}</span>
        </span>
        <span class="course-item__dot"></span>
      </label>`;
  }).join('');
}

function renderDaysOff() {
  $('#days-off-badge').textContent = plural('schedule.days', state.daysOff);
  document.querySelectorAll('.days-off__btn').forEach((btn) =>
    btn.classList.toggle('is-active', Number(btn.dataset.days) === state.daysOff)
  );
}

function renderLocks() {
  const courses = COURSES.filter((c) => state.selected.has(c.code));
  $('#lock-badge').textContent = tr('schedule.lockedN', { n: Object.keys(state.locks).length });

  if (!courses.length) {
    $('#lock-list').innerHTML = `<p class="muted-note">${escapeHtml(tr('schedule.lockSelect'))}</p>`;
    return;
  }

  $('#lock-list').innerHTML = courses.map((c) => {
    const locked = state.locks[c.code];
    const chips = c.sections.map((s) => {
      const closed = isClosed(s);
      const disabled = closed && !state.includeClosed;
      const isLocked = locked === s.id;
      return `
        <button type="button" class="chip${isLocked ? ' is-locked' : ''}" data-lock="${escapeHtml(c.code)}" data-section="${escapeHtml(s.id)}"
          ${disabled ? `disabled title="${escapeHtml(tr('schedule.fullTitle'))}"` : ''}>
          ${isLocked ? ICONS.lock : ''}${escapeHtml(s.id)}${closed ? ` <small>${escapeHtml(tr('schedule.full'))}</small>` : ''}
        </button>`;
    }).join('');

    return `
      <div class="lock-row" style="--c: ${escapeHtml(c.color)}">
        <div class="lock-row__head">
          <span>${escapeHtml(c.short)} (${escapeHtml(c.code)})</span>
          <span class="lock-row__status${locked ? ' is-locked' : ''}">${escapeHtml(locked ? tr('schedule.lockedSec', { id: locked }) : tr('schedule.anySection'))}</span>
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
  $('#result-count').textContent = plural('schedule.schedules', total, `${total}${state.truncated ? '+' : ''}`);
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
  const label = (entry) => `${escapeHtml(entry.course.short)} (${ltr(escapeHtml(entry.course.code))})`;
  $('#conflict-text').innerHTML = `
    <strong>${escapeHtml(tr('schedule.twoFinals'))}</strong>
    <span class="conflict-banner__date">${escapeHtml(formatExamDate(first.date))}</span>
    <span class="conflict-banner__muted">${escapeHtml(tr('schedule.between'))}</span>
    <span class="conflict-chip">${label(first.a)}</span>
    <span class="conflict-banner__muted">${escapeHtml(tr('schedule.and'))}</span>
    <span class="conflict-chip">${label(first.b)}</span>
    ${rest.length ? `<span class="conflict-banner__muted">${escapeHtml(tr('schedule.more', { n: rest.length }))}</span>` : ''}`;
  banner.hidden = false;
}

function renderEmptyTimetable() {
  const noCourses = state.selected.size === 0;
  const title = tr(noCourses ? 'schedule.noCoursesTitle' : state.loading ? 'schedule.generatingTitle' : 'schedule.noSchedulesTitle');
  const text = noCourses
    ? tr('schedule.noCoursesText')
    : state.loading ? tr('schedule.generatingText') : (state.emptyReason ? state.emptyReason() : '');
  $('#timetable').innerHTML = `
    <div class="timetable__empty">
      ${ICONS.emptyCalendar}
      <h3>${escapeHtml(title)}</h3>
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

  const days = Array.from({ length: DAY_COUNT }, (_, day) => day);
  const head = days.map((day) =>
    `<div class="${usedDays.has(day) ? '' : 'is-off'}">${escapeHtml(dayName(day))}</div>`
  ).join('') + `<div class="is-time">${escapeHtml(tr('schedule.time'))}</div>`;

  const columns = days.map((day) => {
    const blocks = schedule.entries.flatMap(({ course, section }) =>
      section.meetings
        .filter((m) => m.day === day)
        .map((m) => {
          const top = ((m.start - start) / 60) * ROW_HEIGHT + 3;
          const blockHeight = ((m.end - m.start) / 60) * ROW_HEIGHT - 6;
          const isLab = m.type !== 'Lecture';
          const title = isLab ? `${course.short} ${typeLabel(m.type)}` : `${course.short} (${course.code})`;
          return `
            <div class="tt-block${isLab ? ' tt-block--lab' : ''}" style="--c: ${escapeHtml(course.color)}; top: ${top}px; height: ${blockHeight}px"
              title="${escapeHtml(course.name)} — ${escapeHtml(section.id)} • ${formatTime(m.start)}-${formatTime(m.end)}${m.room ? ` • ${escapeHtml(tr('schedule.rm', { room: m.room }))}` : ''}">
              <div class="tt-block__top">
                <span class="tt-block__title" dir="auto">${escapeHtml(title)}</span>
                <span class="tt-block__badge">${escapeHtml(section.id)}</span>
              </div>
              <div class="tt-block__bottom">
                <span>${ICONS.clock}${ltr(timeRange(m.start, m.end))}</span>
                ${m.room ? `<span class="tt-block__room">${escapeHtml(tr('schedule.rm', { room: m.room }))}</span>` : ''}
              </div>
            </div>`;
        })
    ).join('');

    const off = !usedDays.has(day);
    return `<div class="tt-col${off ? ' is-off' : ''}" style="height: ${height}px">
      ${off ? `<span class="tt-col__off-label">${escapeHtml(tr('schedule.dayOff'))}</span>` : blocks}
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
    <span class="legend-item" style="--c: ${escapeHtml(course.color)}">
      <span class="legend-item__swatch"></span>
      <strong>${ltr(escapeHtml(course.code))}</strong> (${escapeHtml(course.short)})
    </span>`).join('') +
    `<span>•</span><span class="summary__total">${tr('schedule.totalCredits', { n: credits })}</span>`;
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
          <span>${escapeHtml(dayList(g.days))}: ${ltr(timeRange(g.start, g.end))}</span>
          ${g.type !== 'Lecture' ? `<span class="type-tag">${escapeHtml(typeLabel(g.type))}</span>` : ''}
        </span>
        <span class="info-row__aside" dir="auto">${escapeHtml(g.room)}</span>
      </div>`).join('');

    return `
      <article class="section-card" style="--c: ${escapeHtml(course.color)}">
        <div class="section-card__main">
          <div class="section-card__top">
            <div>
              <h4 class="section-card__name" dir="auto">${escapeHtml(course.name)}</h4>
              <div class="section-card__code">${ltr(escapeHtml(course.code))} • ${escapeHtml(tr('schedule.creditHrs', { n: course.credits }))}</div>
            </div>
            <span class="section-card__badge">${tr('schedule.sectionN', { id: ltr(escapeHtml(section.id)) })}</span>
          </div>

          <div class="section-card__stats">
            <div class="seats">
              <span class="section-card__label">${escapeHtml(tr('schedule.seats'))}</span>
              <span class="seats__value${isClosed(section) ? ' is-full' : ''}">${section.capacity == null ? escapeHtml(tr('schedule.seatsOpen')) : ltr(`${section.enrolled} / ${section.capacity}`)}${isClosed(section) ? ` ${escapeHtml(tr('schedule.fullTag'))}` : ''}</span>
            </div>
            <div class="crn">
              <span class="section-card__label">${escapeHtml(tr('schedule.crn'))}</span>
              <span class="crn__value">${escapeHtml(section.crn)}</span>
              <button type="button" class="crn__copy" data-copy="${escapeHtml(section.crn)}" title="${escapeHtml(tr('schedule.copyCrn'))}" aria-label="${escapeHtml(tr('schedule.copyCrnN', { crn: section.crn }))}">${ICONS.copy}</button>
            </div>
          </div>

          <div class="info-list">
            ${times}
            ${rooms ? `<div class="info-row">
              <span class="info-row__main">${ICONS.room}<span>${tr('schedule.room', { rooms: `<bdi>${escapeHtml(rooms)}</bdi>` })}</span></span>
            </div>` : ''}
            <div class="info-row">
              <span class="info-row__main">${ICONS.user}
                <span class="instructor${section.instructor ? '' : ' is-tba'}" dir="auto">${escapeHtml(section.instructor || tr('schedule.tba'))}</span>
              </span>
            </div>
          </div>
        </div>

        <div class="section-card__exam${conflictCodes.has(course.code) ? ' is-conflict' : ''}">
          ${ICONS.calendar}
          <div>
            <span class="section-card__label">${escapeHtml(tr('schedule.finalExam'))}</span>
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
  savePlanner();
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
    showToast(ok ? message : tr('schedule.copyFailed'));
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
  const FONT = 'Inter, "IBM Plex Sans Arabic", sans-serif';
  ctx.font = `700 18px ${FONT}`;
  ctx.fillText(tr('schedule.imageTitle'), pad, pad + 18);
  const credits = schedule.entries.reduce((sum, e) => sum + e.course.credits, 0);
  ctx.fillStyle = '#8b949e';
  ctx.font = `500 12px ${FONT}`;
  ctx.fillText(
    tr('schedule.imageSub', { i: state.index + 1, n: state.schedules.length, credits }) +
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
  ctx.font = `600 12px ${FONT}`;
  for (let d = 0; d < DAY_COUNT; d++) {
    ctx.fillStyle = '#e2e8f0';
    ctx.fillText(dayName(d), pad + d * colW + colW / 2, gridTop + 23);
  }
  ctx.fillStyle = '#8b949e';
  ctx.font = '600 11px "JetBrains Mono", monospace';
  ctx.fillText(tr('schedule.imageTime'), pad + 5 * colW + timeW / 2, gridTop + 23);

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
      ctx.font = `700 11px ${FONT}`;
      const title = m.type === 'Lecture' ? `${course.short} · ${section.id}` : `${course.short} ${typeLabel(m.type)} · ${section.id}`;
      ctx.fillText(fitText(ctx, title, w - 16), x + 8, y + 16);

      ctx.font = '500 10px "JetBrains Mono", monospace';
      ctx.fillText(`${formatTime(m.start)}-${formatTime(m.end)}${m.room ? `  ${tr('schedule.rm', { room: m.room })}` : ''}`, x + 8, Math.min(y + h - 8, y + 32));
    });
  });

  const link = document.createElement('a');
  link.download = `academic-ai-schedule-${state.index + 1}.png`;
  link.href = canvas.toDataURL('image/png');
  link.click();
  showToast(tr('schedule.imageSaved'));
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
    $('#dz-file-meta').textContent = tr('schedule.fileReady', { size: formatFileSize(importSource.size) });
  }
}

// The message may be a function so it can be written again when the language changes.
let importError = null;

function setImportError(message) {
  importError = message || null;
  const error = $('#dz-error');
  const text = typeof importError === 'function' ? importError() : importError;
  error.textContent = text || '';
  error.hidden = !text;
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
    setImportError(() => tr('schedule.badType'));
    return;
  }
  if (file.size > MAX_UPLOAD_SIZE) {
    setImportError(() => tr('schedule.tooLarge'));
    return;
  }
  setImportError('');
  importSource = { name: file.name, size: file.size, file };
  renderImport();
}

async function processImport() {
  if (!importSource || processing) return;
  processing = true;
  setImportError('');
  const button = $('#process-btn');
  button.disabled = true;
  $('#process-label').textContent = tr('schedule.processing');
  button.querySelector('svg').outerHTML = '<span class="spinner"></span>';

  const finish = () => {
    processing = false;
    $('#process-label').textContent = tr('schedule.process');
    button.querySelector('.spinner').outerHTML = '<svg class="flip-rtl" fill="none" stroke="currentColor" stroke-width="2.2" viewBox="0 0 24 24"><polyline points="9 18 15 12 9 6"></polyline></svg>';
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
    const message = err.message;
    setImportError(() => message);
    return;
  }
  finish();

  if (!data.parsed_courses) {
    const warning = data.warnings[0];
    setImportError(() => (warning ? serverText(warning) : tr('schedule.noCoursesFound')));
    return;
  }

  const name = importSource.name;
  state.completed = new Set(data.completed);
  state.selected = new Set(data.suggested);
  state.locks = {};
  state.listFilter = 'selected';

  closeImportModal();
  update();
  const gpa = data.gpa != null ? tr('schedule.importedGpa', { gpa: data.gpa }) : '';
  showToast(tr('schedule.imported', { name, done: data.completed.length, gpa, n: data.suggested.length }));
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
  showToast(tr('schedule.filtersReset'));
}

function bindEvents() {
  // Header
  $('#sign-out-btn').addEventListener('click', signOut);
  $('#notifications-btn').addEventListener('click', () => showToast(tr('schedule.noNotifications')));
  $('#settings-btn').addEventListener('click', () => showToast(tr('schedule.settingsSoon')));

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
    showToast(total ? plural('schedule.generated', total, `${total}${state.truncated ? '+' : ''}`) : tr('schedule.noneMatch'));
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
    // In Arabic the "previous" button sits on the right, so the arrows swap.
    const back = I18n.dir === 'rtl' ? 'ArrowRight' : 'ArrowLeft';
    const forward = I18n.dir === 'rtl' ? 'ArrowLeft' : 'ArrowRight';
    if (e.key === back) $('#prev-btn').click();
    if (e.key === forward) $('#next-btn').click();
  });

  // Resolve exam conflict → jump to the next conflict-free schedule
  $('#resolve-btn').addEventListener('click', () => {
    const total = state.schedules.length;
    for (let step = 1; step < total; step++) {
      const i = (state.index + step) % total;
      if (!state.schedules[i].conflicts.length) {
        state.index = i;
        renderResults();
        showToast(tr('schedule.switched', { i: i + 1 }));
        return;
      }
    }
    showToast(tr('schedule.allConflict'));
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
    copyText(crns, tr('schedule.copiedCrns', { n: schedule.entries.length, crns }));
  });
  $('#details-grid').addEventListener('click', (e) => {
    const btn = e.target.closest('[data-copy]');
    if (btn) copyText(btn.dataset.copy, tr('schedule.copiedCrn', { crn: btn.dataset.copy }));
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

/* ----------------------------------------------------------
   Saved in the student's profile (PUT /api/me/planner), so the
   planner opens as it was left, on any device.
   ---------------------------------------------------------- */
const PLANNER_SAVE_DELAY = 800;
let plannerTimer;
let plannerSaved = '';

function plannerSnapshot() {
  return {
    selected: [...state.selected],
    locks: state.locks,
    daysOff: state.daysOff,
    timeFrom: state.timeFrom,
    timeTo: state.timeTo,
    includeClosed: state.includeClosed,
  };
}

function savePlanner() {
  clearTimeout(plannerTimer);
  plannerTimer = setTimeout(async () => {
    const snapshot = plannerSnapshot();
    const json = JSON.stringify(snapshot);
    if (json === plannerSaved) return;
    try {
      await apiFetch('/api/me/planner', {
        method: 'PUT',
        body: { planner: { ...snapshot, savedAt: new Date().toISOString() } },
      });
      plannerSaved = json;
    } catch {
      /* Not saved this time; the next change tries again */
    }
  }, PLANNER_SAVE_DELAY);
}

/* Puts back the imported transcript and the last planner choices. Courses
   or sections no longer offered this term are dropped. */
function restoreProfile(profile) {
  const known = (code) => Boolean(COURSE_BY_CODE[code]);
  const transcript = profile.transcript;
  if (transcript && Array.isArray(transcript.completed)) {
    state.completed = new Set(transcript.completed);
  }
  const planner = profile.planner;
  if (planner && Array.isArray(planner.selected)) {
    state.selected = new Set(planner.selected.filter(known));
    state.locks = Object.fromEntries(
      Object.entries(planner.locks || {}).filter(([code, sectionId]) =>
        state.selected.has(code) && COURSE_BY_CODE[code].sections.some((s) => s.id === sectionId)),
    );
    state.daysOff = Number(planner.daysOff) || 0;
    if (Number.isFinite(planner.timeFrom) && Number.isFinite(planner.timeTo) && planner.timeTo > planner.timeFrom) {
      state.timeFrom = Math.max(SCALE_START, planner.timeFrom);
      state.timeTo = Math.min(SCALE_END, planner.timeTo);
    }
    state.includeClosed = Boolean(planner.includeClosed);
  } else if (transcript && Array.isArray(transcript.suggested)) {
    state.selected = new Set(transcript.suggested.filter(known));
  }
  plannerSaved = JSON.stringify(plannerSnapshot());
}

/* Dynamic text follows the language at once. The search box and the
   file input are not rebuilt, so what the student typed stays. */
I18n.onChange(() => {
  if (!COURSES.length) return;
  renderSidebar();
  renderResults();
  renderImport();
  setImportError(importError);
  if (processing) $('#process-label').textContent = tr('schedule.processing');
});

Auth.requireRole('student').then(async (user) => {
  Auth.fillUser(user);
  Tickets.mount(user);
  fillTimeSelects();
  bindEvents();
  if (!(await loadCourses())) return;
  try {
    restoreProfile((await apiFetch('/api/me/profile')).profile || {});
  } catch {
    /* The planner still works; it just starts from the defaults */
  }
  update();
});
