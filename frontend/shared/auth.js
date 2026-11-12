/* ==========================================================
   Academic AI - Account session, shared by every page
   The server keeps the session in a cookie this script can't
   read; who is signed in comes from GET /api/auth/me.
   ========================================================== */

const Auth = (() => {
  // The session cookie only goes to the server the page came from, so a page
  // opened from disk (file://) is sent to the local server instead.
  if (location.protocol === 'file:') location.replace('http://localhost:8000/');

  const API_URL = location.origin;
  const SIGN_IN_PAGE = '../sign-in-page/index.html?v=2';
  const HOME = {
    student: '../welcome-page/index.html?v=2',
    advisor: '../advisor-page/index.html?v=2',
    admin: '../admin-page/index.html?v=2',
  };
  const SERVER_DOWN = `Couldn't reach the Academic AI server at ${API_URL}. Make sure the server is running (Start-API.bat).`;

  let user = null;

  const home = (role) => HOME[role] || SIGN_IN_PAGE;

  /* fetch() for the JSON API. Returns the parsed body; throws an Error with
     the server's message (and .status). A lost session goes back to Sign In. */
  async function api(path, options = {}) {
    const init = { credentials: 'same-origin', ...options };
    if (init.body && !(init.body instanceof FormData) && typeof init.body !== 'string') {
      init.body = JSON.stringify(init.body);
      init.headers = { 'Content-Type': 'application/json', ...(init.headers || {}) };
    }
    let res;
    try {
      res = await fetch(`${API_URL}${path}`, init);
    } catch (err) {
      if (err.name === 'AbortError') throw err;
      throw new Error(SERVER_DOWN);
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      if (res.status === 401 && !options.keepPage) location.replace(SIGN_IN_PAGE);
      const detail = typeof data.detail === 'string' ? data.detail : `Server error (${res.status})`;
      const error = new Error(detail);
      error.status = res.status;
      throw error;
    }
    return data;
  }

  /* Who is signed in, or null. Never redirects. */
  async function whoAmI() {
    try {
      user = (await api('/api/auth/me', { keepPage: true })).user;
    } catch {
      user = null;
    }
    return user;
  }

  /* Gate for a page: resolves with the user when their role is allowed.
     Otherwise the browser is sent to Sign In (or to the role's own home)
     and the promise never resolves, so the page's code doesn't run. */
  function requireRole(...roles) {
    document.documentElement.style.visibility = 'hidden';
    return new Promise((resolve) => {
      whoAmI().then((me) => {
        if (!me || me.must_change_password) {
          location.replace(SIGN_IN_PAGE);
        } else if (roles.length && !roles.includes(me.role)) {
          location.replace(home(me.role));
        } else {
          document.documentElement.style.visibility = '';
          resolve(me);
        }
      });
    });
  }

  async function signOut() {
    try {
      await api('/api/auth/logout', { method: 'POST', keepPage: true });
    } catch {
      /* The server is unreachable; leave the page anyway */
    }
    location.replace(SIGN_IN_PAGE);
  }

  /* Two letters for a Latin name; one for an Arabic name, whose letters
     would join into something that reads as a word. */
  const initials = (name) => {
    const words = (name || '').split(/\s+/).filter(Boolean);
    if (!words.length) return '?';
    const latin = /^[A-Za-z]/.test(words[0]);
    return words.slice(0, latin ? 2 : 1).map((w) => w[0]).join('').toUpperCase();
  };

  const firstName = (name) => (name || '').split(/\s+/).filter(Boolean)[0] || '';

  /* Writes the signed-in user into the header chip the pages share. */
  function fillUser(me = user) {
    if (!me) return;
    document.querySelectorAll('.user__name').forEach((el) => { el.textContent = me.name; el.dir = 'auto'; });
    document.querySelectorAll('.user__id').forEach((el) => { el.textContent = me.username; });
    document.querySelectorAll('.user__avatar, .user .avatar').forEach((el) => { el.textContent = initials(me.name); });
  }

  /* Current term from today's date (Fall: Aug-Dec, Spring: Jan-May, Summer: Jun-Jul),
     so the header pill never shows a past semester. */
  function termLabel(date = new Date()) {
    const m = date.getMonth();
    const term = m >= 7 ? 'Fall' : m <= 4 ? 'Spring' : 'Summer';
    return `${term} ${date.getFullYear()}`;
  }

  function fillTerm() {
    document.querySelectorAll('[data-term]').forEach((el) => {
      el.textContent = `${el.dataset.term}${termLabel()} Online`;
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fillTerm);
  else fillTerm();

  return {
    API_URL, SERVER_DOWN, api, whoAmI, requireRole, signOut, fillUser, home, initials, firstName, termLabel,
    get user() { return user; },
  };
})();
