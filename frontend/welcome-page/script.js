/* ==========================================================
   Academic AI - Welcome Page Interactions
   ========================================================== */

// Students only; advisors and admins are sent to their own home page.
const escHtml = (v) => String(v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

let currentUser = null;

function renderWelcome() {
  const el = document.getElementById('welcome-name');
  if (!currentUser) { el.textContent = I18n.t('welcome.back'); return; }
  const name = `<bdi>${escHtml(Auth.firstName(currentUser.name))}</bdi>`;
  el.innerHTML = I18n.t('welcome.backName', { name });
}
renderWelcome();
I18n.onChange(renderWelcome);

Auth.requireRole('student').then((user) => {
  currentUser = user;
  Tickets.mount(user);
  Auth.fillUser(user);
  renderWelcome();

  // ---------- Sign Out: back to the Sign In page ----------
  document.getElementById('sign-out-btn').addEventListener('click', Auth.signOut);
});
