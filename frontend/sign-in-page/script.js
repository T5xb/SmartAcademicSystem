/* ==========================================================
   Academic AI - Sign In Page Interactions
   Accounts live on the server (POST /api/auth/login); each
   role lands on its own home page.
   ========================================================== */

const MIN_PASSWORD_LENGTH = 8;   // matches the server (src/accounts/security.py)

function showError(el, message) {
  el.textContent = message;
  el.hidden = !message;
}

function setBusy(button, busy) {
  button.disabled = busy;
}

document.addEventListener('DOMContentLoaded', async () => {
  // ---------- Elements ----------
  const form = document.getElementById('auth-form');
  const userInput = document.getElementById('university-id');
  const passwordInput = document.getElementById('password');
  const rememberInput = document.getElementById('remember-me');
  const toggleBtn = document.getElementById('toggle-password-btn');
  const signInBtn = document.getElementById('sign-in-btn');
  const authError = document.getElementById('auth-error');

  const passwordForm = document.getElementById('password-form');
  const newPasswordInput = document.getElementById('new-password');
  const confirmInput = document.getElementById('confirm-password');
  const savePasswordBtn = document.getElementById('save-password-btn');
  const passwordError = document.getElementById('password-error');

  let temporaryPassword = '';

  // ---------- Where a signed-in user goes ----------
  function enter(user) {
    if (user.must_change_password) {
      form.hidden = true;
      passwordForm.hidden = false;
      newPasswordInput.focus();
    } else {
      window.location.replace(Auth.home(user.role));
    }
  }

  // Already signed in → straight to the role's home page
  const current = await Auth.whoAmI();
  if (current && !current.must_change_password) {
    enter(current);
    return;
  }
  // A session that still has a temporary password starts over, since the
  // temporary password is needed again to replace it.
  if (current) await Auth.api('/api/auth/logout', { method: 'POST', keepPage: true }).catch(() => {});

  // ---------- Password Toggle (Show / Hide) ----------
  toggleBtn.addEventListener('click', () => {
    const isHidden = passwordInput.type === 'password';
    passwordInput.type = isHidden ? 'text' : 'password';
    toggleBtn.classList.toggle('is-visible', isHidden);
  });

  // ---------- Sign In ----------
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = userInput.value.trim();
    const password = passwordInput.value;
    if (!username || !password) {
      showError(authError, 'Enter your university ID and password.');
      return;
    }
    showError(authError, '');
    setBusy(signInBtn, true);
    try {
      const data = await Auth.api('/api/auth/login', {
        method: 'POST',
        body: { username, password, remember: rememberInput.checked },
        keepPage: true,
      });
      temporaryPassword = password;
      enter(data.user);
    } catch (err) {
      showError(authError, err.message);
      passwordInput.select();
    } finally {
      setBusy(signInBtn, false);
    }
  });

  // ---------- Replace a temporary password ----------
  passwordForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const next = newPasswordInput.value;
    if (next.length < MIN_PASSWORD_LENGTH) {
      showError(passwordError, `Use at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }
    if (next !== confirmInput.value) {
      showError(passwordError, 'The two passwords are not the same.');
      return;
    }
    showError(passwordError, '');
    setBusy(savePasswordBtn, true);
    try {
      await Auth.api('/api/auth/password', {
        method: 'POST',
        body: { current_password: temporaryPassword, new_password: next },
        keepPage: true,
      });
      const user = await Auth.whoAmI();
      if (user) enter(user);
      else window.location.reload();
    } catch (err) {
      showError(passwordError, err.message);
    } finally {
      setBusy(savePasswordBtn, false);
    }
  });

  document.getElementById('cancel-password-btn').addEventListener('click', Auth.signOut);
});
