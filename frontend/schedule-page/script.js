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
const DAY_CODES = { U: 0, M: 1, T: 2, W: 3, R: 4 };
const SCALE_START = 8 * 60;          // 08:00
const SCALE_END = 24 * 60;           // 24:00
const TIME_STEP = 30;                // minutes
const MAX_RESULTS = 300;
const MAX_CREDITS = 30;
const ROW_HEIGHT = 96;               // px per hour (matches --row-height)

const DEFAULT_SELECTED = ['CS1223', 'CS1241', 'CS1242'];
const IMPORT_COURSES = ['CS1223', 'CS1241', 'CS1242', 'CS2310', 'MATH2201'];
const SAMPLE_FILE = { name: 'KFUPM_Audit_Sample.pdf', size: 248 * 1024 };
const MAX_UPLOAD_SIZE = 15 * 1024 * 1024;

/* ----------------------------------------------------------
   Mock Course Data
   Meeting format: "<days> <start>-<end> <room> [Lab]"
   Days: U = Sun, M = Mon, T = Tue, W = Wed, R = Thu
   seats: [capacity, enrolled]  (enrolled >= capacity → closed)
   ---------------------------------------------------------- */
const COURSE_DATA = [
  {
    code: 'CS1223', name: 'Computer Architecture', short: 'Computer Arch', credits: 3, color: '#16d076',
    exam: '2026-12-31 10:00-11:30',
    sections: [
      { id: 'B01', crn: '29123', seats: [40, 31], instructor: 'Dr. Khalid Al-Harbi', meet: ['UTR 08:00-08:50 2169'] },
      { id: 'B02', crn: '29124', seats: [40, 40], instructor: 'Dr. Khalid Al-Harbi', meet: ['UTR 10:00-10:50 2169'] },
      { id: 'B03', crn: '29125', seats: [35, 22], instructor: '', meet: ['MW 13:00-14:15 2171'] },
    ],
  },
  {
    code: 'CS1241', name: 'Object-Oriented Programming', short: 'OOP', credits: 4, color: '#a855f7',
    exam: '2026-12-27 10:00-12:00',
    sections: [
      { id: 'B01', crn: '29101', seats: [30, 18], instructor: 'Ganesh Kuma Biromal', meet: ['UTR 09:00-09:50 1057', 'W 15:00-16:50 1060 Lab'] },
      { id: 'B02', crn: '29103', seats: [30, 27], instructor: 'Dr. Nora Al-Shehri', meet: ['MW 10:00-11:15 1057', 'R 13:00-14:50 1060 Lab'] },
      { id: 'B03', crn: '29105', seats: [30, 30], instructor: 'Ganesh Kuma Biromal', meet: ['UTR 13:00-13:50 1057', 'M 08:00-09:50 1060 Lab'] },
    ],
  },
  {
    code: 'CS1242', name: 'Data Structures & Algorithms', short: 'Data Structures', credits: 4, color: '#3b82f6',
    exam: '2026-12-27 07:30-09:30',
    sections: [
      { id: 'B01', crn: '29096', seats: [25, 19], instructor: 'Mohamed Hussein Fayez Al-Khatib', meet: ['MW 08:00-09:15 1057', 'T 15:00-16:50 1055 Lab'] },
      { id: 'B02', crn: '29097', seats: [25, 24], instructor: 'Dr. Faisal Al-Mutairi', meet: ['UTR 11:00-11:50 1055', 'W 13:00-14:50 1055 Lab'] },
      { id: 'B03', crn: '29098', seats: [25, 12], instructor: '', meet: ['MW 16:00-17:15 1057', 'R 10:00-11:50 1055 Lab'], exam: '2026-12-29 07:30-09:30' },
    ],
  },
  {
    code: 'CS1201', name: 'Discrete Structures II', short: 'Discrete II', credits: 3, color: '#f97316',
    exam: '2026-12-28 08:00-10:00',
    sections: [
      { id: 'B01', crn: '29140', seats: [45, 30], instructor: 'Dr. Huda Al-Otaibi', meet: ['UTR 10:00-10:50 2203'] },
      { id: 'B02', crn: '29141', seats: [45, 44], instructor: 'Dr. Huda Al-Otaibi', meet: ['MW 11:30-12:45 2203'] },
      { id: 'B03', crn: '29142', seats: [45, 20], instructor: 'Dr. Omar Al-Zahrani', meet: ['UTR 14:00-14:50 2205'] },
    ],
  },
  {
    code: 'CS1220', name: 'Digital Logic Design', short: 'Digital Logic', credits: 3, color: '#06b6d4',
    exam: '2026-12-30 13:00-15:00',
    sections: [
      { id: 'B01', crn: '29150', seats: [30, 25], instructor: 'Dr. Yousef Al-Ghamdi', meet: ['MW 09:30-10:45 3112', 'U 15:00-17:50 3120 Lab'] },
      { id: 'B02', crn: '29151', seats: [30, 29], instructor: 'Dr. Yousef Al-Ghamdi', meet: ['UTR 12:00-12:50 3112', 'W 08:00-10:50 3120 Lab'] },
      { id: 'B03', crn: '29152', seats: [30, 30], instructor: '', meet: ['MW 14:30-15:45 3114', 'T 08:00-10:50 3120 Lab'] },
    ],
  },
  {
    code: 'CS2310', name: 'Operating Systems', short: 'Operating Sys', credits: 3, color: '#ec4899',
    exam: '2026-12-29 10:00-12:00',
    sections: [
      { id: 'B01', crn: '29210', seats: [35, 28], instructor: 'Dr. Majed Al-Dossary', meet: ['UTR 09:00-09:50 1210'] },
      { id: 'B02', crn: '29211', seats: [35, 33], instructor: 'Dr. Reem Al-Saud', meet: ['MW 13:00-14:15 1210'] },
      { id: 'B03', crn: '29212', seats: [35, 35], instructor: 'Dr. Majed Al-Dossary', meet: ['UTR 16:00-16:50 1212'] },
    ],
  },
  {
    code: 'CS2320', name: 'Database Systems', short: 'Databases', credits: 3, color: '#eab308',
    exam: '2026-12-28 13:00-15:00',
    sections: [
      { id: 'B01', crn: '29220', seats: [40, 26], instructor: 'Dr. Abdullah Al-Shammari', meet: ['MW 08:00-09:15 1301'] },
      { id: 'B02', crn: '29221', seats: [40, 39], instructor: 'Dr. Lama Al-Rashed', meet: ['UTR 11:00-11:50 1301'] },
      { id: 'B03', crn: '29222', seats: [40, 15], instructor: '', meet: ['MW 18:00-19:15 1303'] },
    ],
  },
  {
    code: 'CS2350', name: 'Computer Networks', short: 'Networks', credits: 3, color: '#14b8a6',
    exam: '2026-12-30 08:00-10:00',
    sections: [
      { id: 'B01', crn: '29250', seats: [30, 22], instructor: 'Dr. Turki Al-Anazi', meet: ['UTR 08:00-08:50 1405'] },
      { id: 'B02', crn: '29251', seats: [30, 27], instructor: 'Dr. Turki Al-Anazi', meet: ['MW 10:00-11:15 1405'] },
      { id: 'B03', crn: '29252', seats: [30, 10], instructor: '', meet: ['UTR 17:00-17:50 1407'] },
    ],
  },
  {
    code: 'CS2401', name: 'Software Engineering', short: 'Software Eng', credits: 3, color: '#6366f1',
    exam: '2026-12-31 13:00-15:00',
    sections: [
      { id: 'B01', crn: '29401', seats: [40, 36], instructor: 'Dr. Hessa Al-Mansour', meet: ['MW 11:30-12:45 2310'] },
      { id: 'B02', crn: '29402', seats: [40, 18], instructor: 'Dr. Saleh Al-Juhani', meet: ['UTR 15:00-15:50 2310'] },
      { id: 'B03', crn: '29403', seats: [40, 9], instructor: '', meet: ['MW 19:30-20:45 2312'] },
    ],
  },
  {
    code: 'MATH2201', name: 'Linear Algebra', short: 'Linear Algebra', credits: 3, color: '#ef4444',
    exam: '2026-12-26 08:00-10:00',
    sections: [
      { id: 'B01', crn: '30201', seats: [50, 47], instructor: 'Dr. Ibrahim Al-Fahad', meet: ['UTR 08:00-08:50 5101'] },
      { id: 'B02', crn: '30202', seats: [50, 50], instructor: 'Dr. Mona Al-Harthi', meet: ['UTR 12:00-12:50 5101'] },
      { id: 'B03', crn: '30203', seats: [50, 31], instructor: 'Dr. Ibrahim Al-Fahad', meet: ['MW 16:00-17:15 5103'] },
    ],
  },
];

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

const formatExam = (exam) => `${formatExamDate(exam.date)} • ${formatTime(exam.start)} - ${formatTime(exam.end)}`;

const formatFileSize = (bytes) =>
  bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;

const isClosed = (section) => section.enrolled >= section.capacity;

function parseExam(text) {
  const [date, range] = text.split(' ');
  const [start, end] = range.split('-');
  return { date, start: toMinutes(start), end: toMinutes(end) };
}

function parseMeeting(text) {
  const [days, range, room, type = 'Lecture'] = text.split(' ');
  const [start, end] = range.split('-');
  return [...days].map((code) => ({
    day: DAY_CODES[code],
    start: toMinutes(start),
    end: toMinutes(end),
    room,
    type,
  }));
}

/* Normalized courses */
const COURSES = COURSE_DATA.map((course, index) => {
  const exam = parseExam(course.exam);
  return {
    ...course,
    index,
    exam,
    sections: course.sections.map((s) => ({
      id: s.id,
      crn: s.crn,
      capacity: s.seats[0],
      enrolled: s.seats[1],
      instructor: s.instructor,
      meetings: s.meet.flatMap(parseMeeting),
      exam: s.exam ? parseExam(s.exam) : exam,
    })),
  };
});

const COURSE_BY_CODE = Object.fromEntries(COURSES.map((c) => [c.code, c]));

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
};

/* ----------------------------------------------------------
   Schedule Generator
   ---------------------------------------------------------- */
function isSectionAllowed(course, section) {
  const locked = state.locks[course.code];
  if (locked && locked !== section.id) return false;
  if (!state.includeClosed && isClosed(section)) return false;
  return section.meetings.every((m) => m.start >= state.timeFrom && m.end <= state.timeTo);
}

const overlaps = (a, b) => a.day === b.day && a.start < b.end && b.start < a.end;

function buildSchedule(picks) {
  const entries = [...picks].sort((a, b) => a.course.index - b.course.index);
  const meetings = entries.flatMap((e) => e.section.meetings);
  const days = new Set(meetings.map((m) => m.day));

  // Idle minutes between classes on the same day
  let gaps = 0;
  days.forEach((day) => {
    const list = meetings.filter((m) => m.day === day).sort((a, b) => a.start - b.start);
    for (let i = 1; i < list.length; i++) gaps += Math.max(0, list[i].start - list[i - 1].end);
  });

  // Two final exams on the same date = conflict
  const conflicts = [];
  for (let i = 0; i < entries.length; i++) {
    for (let j = i + 1; j < entries.length; j++) {
      if (entries[i].section.exam.date === entries[j].section.exam.date) {
        conflicts.push({ date: entries[i].section.exam.date, a: entries[i], b: entries[j] });
      }
    }
  }

  return { entries, daysUsed: days.size, gaps, conflicts };
}

function generateSchedules() {
  state.schedules = [];
  state.truncated = false;
  state.emptyReason = '';
  state.index = 0;

  const courses = COURSES.filter((c) => state.selected.has(c.code));
  if (!courses.length) return;

  const options = courses.map((c) => c.sections.filter((s) => isSectionAllowed(c, s)));
  const blockedIndex = options.findIndex((list) => !list.length);
  if (blockedIndex !== -1) {
    const course = courses[blockedIndex];
    state.emptyReason = `No section of ${course.code} (${course.short}) fits your current filters. Try widening the time range, including closed sections, or unlocking its section.`;
    return;
  }

  // Courses with fewer options first → faster pruning
  const order = courses.map((_, i) => i).sort((a, b) => options[a].length - options[b].length);
  const maxDays = 5 - state.daysOff;
  const results = [];
  const picks = [];

  const walk = (depth, taken, days) => {
    if (results.length >= MAX_RESULTS) {
      state.truncated = true;
      return;
    }
    if (depth === order.length) {
      results.push(buildSchedule(picks));
      return;
    }
    const course = courses[order[depth]];
    for (const section of options[order[depth]]) {
      if (section.meetings.some((m) => taken.some((t) => overlaps(m, t)))) continue;
      const nextDays = new Set(days);
      section.meetings.forEach((m) => nextDays.add(m.day));
      if (nextDays.size > maxDays) continue;

      picks.push({ course, section });
      walk(depth + 1, taken.concat(section.meetings), nextDays);
      picks.pop();
    }
  };

  walk(0, [], new Set());

  // Best first: no exam conflicts, fewer campus days, fewer idle gaps
  results.sort((a, b) =>
    a.conflicts.length - b.conflicts.length ||
    a.daysUsed - b.daysUsed ||
    a.gaps - b.gaps
  );

  state.schedules = results;
  if (!results.length) {
    state.emptyReason = 'Every combination of the selected courses clashes in time or breaks your filters. Try fewer days off, a wider time range, or unlocking a section.';
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
    return `
      <label class="course-item${selected ? ' is-selected' : ''}" style="--c: ${c.color}">
        <input type="checkbox" class="course-item__check" data-code="${c.code}" ${selected ? 'checked' : ''}>
        <span class="course-item__text">
          <span class="course-item__name">${escapeHtml(c.name)}</span>
          <span class="course-item__meta">${c.code} • ${c.credits} Credit Hrs • ${c.sections.length} Sections</span>
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
    <strong>Final Exam Conflict Detected:</strong>
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
  $('#timetable').innerHTML = `
    <div class="timetable__empty">
      ${ICONS.emptyCalendar}
      <h3>${noCourses ? 'No courses selected' : 'No schedules found'}</h3>
      <p>${noCourses ? 'Select courses from the sidebar to start building your schedule.' : escapeHtml(state.emptyReason)}</p>
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
              title="${escapeHtml(course.name)} — ${section.id} • ${formatTime(m.start)}-${formatTime(m.end)} • Rm ${m.room}">
              <div class="tt-block__top">
                <span class="tt-block__title">${escapeHtml(title)}</span>
                <span class="tt-block__badge">${section.id}</span>
              </div>
              <div class="tt-block__bottom">
                <span>${ICONS.clock}${formatTime(m.start)} - ${formatTime(m.end)}</span>
                <span class="tt-block__room">Rm ${m.room}</span>
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
    const rooms = [...new Set(section.meetings.map((m) => m.room))].join(', ');
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
              <h4 class="section-card__name">${escapeHtml(course.name)}</h4>
              <div class="section-card__code">${course.code} • ${course.credits} Credit Hrs</div>
            </div>
            <span class="section-card__badge">Section ${section.id}</span>
          </div>

          <div class="section-card__stats">
            <div class="seats">
              <span class="section-card__label">Seats:</span>
              <span class="seats__value${isClosed(section) ? ' is-full' : ''}">${section.enrolled} / ${section.capacity}${isClosed(section) ? ' Full' : ''}</span>
            </div>
            <div class="crn">
              <span class="section-card__label">CRN:</span>
              <span class="crn__value">${section.crn}</span>
              <button type="button" class="crn__copy" data-copy="${section.crn}" title="Copy CRN" aria-label="Copy CRN ${section.crn}">${ICONS.copy}</button>
            </div>
          </div>

          <div class="info-list">
            ${times}
            <div class="info-row">
              <span class="info-row__main">${ICONS.room}<span>Room: <strong>${rooms}</strong></span></span>
            </div>
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

/* Regenerate + redraw everything */
function update() {
  generateSchedules();
  renderSidebar();
  renderResults();
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
      ctx.fillText(`${formatTime(m.start)}-${formatTime(m.end)}  Rm ${m.room}`, x + 8, Math.min(y + h - 8, y + 32));
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
let importSource = null;   // { name, size, sample }
let processing = false;

function renderImport() {
  const hasFile = Boolean(importSource);
  $('#dz-empty').hidden = hasFile;
  $('#dz-file').hidden = !hasFile;
  $('#dropzone').classList.toggle('has-file', hasFile);
  $('#process-btn').disabled = !hasFile || processing;

  if (hasFile) {
    $('#dz-file-name').textContent = importSource.name;
    $('#dz-file-meta').textContent = `${formatFileSize(importSource.size)} • ${importSource.sample ? 'Sample audit' : 'Ready to process'}`;
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
  const valid = /\.(pdf|html?)$/i.test(file.name);
  if (!valid) {
    setImportError('Unsupported file type. Please upload a PDF or HTML file.');
    return;
  }
  if (file.size > MAX_UPLOAD_SIZE) {
    setImportError('File is too large. The maximum size is 15MB.');
    return;
  }
  setImportError('');
  importSource = { name: file.name, size: file.size, sample: false };
  renderImport();
}

function processImport() {
  if (!importSource || processing) return;
  processing = true;
  const button = $('#process-btn');
  button.disabled = true;
  $('#process-label').textContent = 'Processing…';
  button.querySelector('svg').outerHTML = '<span class="spinner"></span>';

  // Demo: parsing is simulated — the record auto-fills a recommended course set
  setTimeout(() => {
    const name = importSource.name;
    state.selected = new Set(IMPORT_COURSES);
    state.locks = {};
    state.listFilter = 'selected';

    processing = false;
    $('#process-label').textContent = 'Process Transcript & Auto-fill';
    button.querySelector('.spinner').outerHTML = '<svg fill="none" stroke="currentColor" stroke-width="2.2" viewBox="0 0 24 24"><polyline points="9 18 15 12 9 6"></polyline></svg>';

    closeImportModal();
    update();
    showToast(`Auto-filled ${IMPORT_COURSES.length} courses from ${name}`);
  }, 1200);
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
  $('#generate-btn').addEventListener('click', () => {
    update();
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
        showToast(`Switched to schedule ${i + 1} — no exam conflicts`);
        return;
      }
    }
    showToast('Every matching schedule has an exam clash — try a different course or section');
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

  $('#load-sample-btn').addEventListener('click', () => {
    setImportError('');
    importSource = { ...SAMPLE_FILE, sample: true };
    renderImport();
  });

  $('#process-btn').addEventListener('click', processImport);
}

/* ----------------------------------------------------------
   Init
   ---------------------------------------------------------- */
document.addEventListener('DOMContentLoaded', () => {
  fillTimeSelects();
  bindEvents();
  update();
});
