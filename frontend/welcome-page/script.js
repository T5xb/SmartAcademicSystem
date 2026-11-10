/* ==========================================================
   Academic AI - Welcome Page Interactions
   ========================================================== */

// Students only; advisors and admins are sent to their own home page.
Auth.requireRole('student').then((user) => {
  Auth.fillUser(user);
  document.getElementById('welcome-name').textContent = `Welcome back, ${Auth.firstName(user.name)}.`;
  document.getElementById('welcome-name').dir = 'auto';

  // ---------- Sign Out: back to the Sign In page ----------
  document.getElementById('sign-out-btn').addEventListener('click', Auth.signOut);
});
