/* ==========================================================
   Academic AI - Welcome Page Interactions
   ========================================================== */

// ---------- Session ----------
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

document.addEventListener('DOMContentLoaded', () => {
  // ---------- Sign Out: back to the Sign In page ----------
  const signOutBtn = document.getElementById('sign-out-btn');

  if (signOutBtn) {
    signOutBtn.addEventListener('click', signOut);
  }
});
