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

  const tabs = document.getElementById('auth-tabs');
  const tabSignIn = document.getElementById('tab-sign-in');
  const tabRegister = document.getElementById('tab-register');
  const registerForm = document.getElementById('register-form');
  const regId = document.getElementById('reg-id');
  const regName = document.getElementById('reg-name');
  const regPassword = document.getElementById('reg-password');
  const regConfirm = document.getElementById('reg-confirm');
  const registerBtn = document.getElementById('register-btn');
  const registerError = document.getElementById('register-error');
  const promptToRegister = document.getElementById('prompt-to-register');
  const promptToSignIn = document.getElementById('prompt-to-sign-in');

  const regFields = [regId, regName, regPassword, regConfirm];

  let temporaryPassword = '';

  // An error shown right under its field, with the field outlined in red.
  function setFieldError(input, message) {
    showError(document.getElementById(`${input.id}-error`), message);
    input.classList.toggle('is-invalid', Boolean(message));
    input.setAttribute('aria-invalid', String(Boolean(message)));
  }
  // Typing in a field clears its error.
  regFields.forEach((input) => input.addEventListener('input', () => setFieldError(input, '')));

  // ---------- Sign in / Create account tabs ----------
  function showMode(mode) {
    const registering = mode === 'register';
    form.hidden = registering;
    registerForm.hidden = !registering;
    tabSignIn.classList.toggle('is-active', !registering);
    tabRegister.classList.toggle('is-active', registering);
    tabSignIn.setAttribute('aria-selected', String(!registering));
    tabRegister.setAttribute('aria-selected', String(registering));
    promptToRegister.hidden = registering;
    promptToSignIn.hidden = !registering;
    showError(authError, '');
    showError(registerError, '');
    regFields.forEach((input) => setFieldError(input, ''));
    (registering ? regId : userInput).focus();
  }

  tabSignIn.addEventListener('click', () => showMode('sign-in'));
  tabRegister.addEventListener('click', () => showMode('register'));
  document.querySelectorAll('[data-switch]').forEach((btn) =>
    btn.addEventListener('click', () => showMode(btn.dataset.switch)));

  // ---------- Where a signed-in user goes ----------
  function enter(user) {
    if (user.must_change_password) {
      tabs.hidden = true;
      promptToRegister.hidden = true;
      promptToSignIn.hidden = true;
      registerForm.hidden = true;
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
      showError(authError, I18n.t('signin.enterBoth'));
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

  // ---------- Create a student account ----------
  registerForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = regId.value.trim();
    const name = regName.value.trim().replace(/\s+/g, ' ');
    const password = regPassword.value;
    const problems = new Map();
    if (!/^\d{6,12}$/.test(username)) problems.set(regId, I18n.t('signin.badId'));
    if (name.length < 3 || name.split(' ').length < 2) problems.set(regName, I18n.t('signin.badName'));
    if (password.length < MIN_PASSWORD_LENGTH) problems.set(regPassword, I18n.t('signin.minLength', { n: MIN_PASSWORD_LENGTH }));
    else if (password !== regConfirm.value) problems.set(regConfirm, I18n.t('signin.mismatch'));
    showError(registerError, '');
    regFields.forEach((input) => setFieldError(input, problems.get(input) || ''));
    if (problems.size) {
      problems.keys().next().value.focus();
      return;
    }
    setBusy(registerBtn, true);
    try {
      const data = await Auth.api('/api/auth/register', {
        method: 'POST',
        body: { username, name, password, remember: rememberInput.checked },
        keepPage: true,
      });
      enter(data.user);
    } catch (err) {
      // An ID that is already taken is about the ID field; anything else
      // (sign-up off, too many tries, server down) goes under the form.
      if (err.status === 409) {
        setFieldError(regId, err.message);
        regId.focus();
      } else {
        showError(registerError, err.message);
      }
    } finally {
      setBusy(registerBtn, false);
    }
  });

  // ---------- Replace a temporary password ----------
  passwordForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const next = newPasswordInput.value;
    if (next.length < MIN_PASSWORD_LENGTH) {
      showError(passwordError, I18n.t('signin.minLength', { n: MIN_PASSWORD_LENGTH }));
      return;
    }
    if (next !== confirmInput.value) {
      showError(passwordError, I18n.t('signin.mismatch'));
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
