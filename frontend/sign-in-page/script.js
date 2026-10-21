/* ==========================================================
   Academic AI - Sign In Page Interactions
   ========================================================== */

// ---------- Session ----------
const SESSION_KEY = 'academic-ai-session';
const HOME_PAGE = '../welcome-page/index.html';

function hasSession() {
  try {
    return Boolean(localStorage.getItem(SESSION_KEY) || sessionStorage.getItem(SESSION_KEY));
  } catch {
    return false;
  }
}

function startSession(user, remember) {
  const session = JSON.stringify({ user, signedInAt: Date.now() });
  try {
    // "Remember me" keeps the session after the browser closes
    (remember ? localStorage : sessionStorage).setItem(SESSION_KEY, session);
  } catch {
    /* Storage unavailable — the other pages will still open */
  }
}

// Already signed in → go straight to the Welcome page
if (hasSession()) window.location.replace(HOME_PAGE);

document.addEventListener('DOMContentLoaded', () => {
  // ---------- Elements ----------
  const form = document.getElementById('auth-form');
  const userInput = document.getElementById('university-id');
  const rememberInput = document.getElementById('remember-me');
  const toggleBtn = document.getElementById('toggle-password-btn');
  const passwordInput = document.getElementById('password');
  const tabSignIn = document.getElementById('tab-sign-in');
  const tabRegister = document.getElementById('tab-register');
  const switchSignupLink = document.getElementById('switch-signup-link');

  // ---------- Password Toggle (Show / Hide) ----------
  if (toggleBtn && passwordInput) {
    toggleBtn.addEventListener('click', () => {
      const isHidden = passwordInput.type === 'password';
      passwordInput.type = isHidden ? 'text' : 'password';
      toggleBtn.classList.toggle('is-visible', isHidden);
    });
  }

  // ---------- Tab Switching (Sign In <-> Create Account) ----------
  function setActiveTab(activeTab, inactiveTab) {
    activeTab.classList.add('is-active');
    inactiveTab.classList.remove('is-active');
  }

  if (tabSignIn && tabRegister) {
    tabSignIn.addEventListener('click', () => setActiveTab(tabSignIn, tabRegister));
    tabRegister.addEventListener('click', () => setActiveTab(tabRegister, tabSignIn));
  }

  if (switchSignupLink && tabSignIn && tabRegister) {
    switchSignupLink.addEventListener('click', (e) => {
      e.preventDefault();
      setActiveTab(tabRegister, tabSignIn);
    });
  }

  // ---------- Sign In (demo: any email + password is accepted) ----------
  if (form) {
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      startSession(userInput.value.trim(), rememberInput.checked);
      window.location.replace(HOME_PAGE);
    });
  }
});
