/* ==========================================================
   Academic AI - Admin console
   Documents (the chatbot's sources) and Accounts.
   ========================================================== */

const $ = (s) => document.querySelector(s);
const t = (key, vars) => I18n.t(key, vars);
// Wraps a name (file, folder, person) so it keeps its own direction inside a sentence
const iso = (value) => '\u2068' + value + '\u2069';

/* ==========================================================
   Constants & state
   ========================================================== */
const ALLOWED_EXT = ['pdf', 'docx', 'txt', 'md'];
const MAX_BYTES = 50 * 1024 * 1024;
const POLL_MS = 3000;

const state = {
  files: [],
  folders: [''],
  index: null,
  filesLoaded: false,
  // Folders start collapsed; this holds the ones the admin has opened.
  expanded: new Set(),
  highlight: '',
  users: [],
  usersLoaded: false,
  pollTimer: null,
  tickTimer: null,
  sawRunning: false,
  // What the open dialogs / panels were built from, so a language switch can redraw them
  jobResult: null,
  confirmText: null,
  secret: null,
  secretCopied: false,
};

/* ==========================================================
   Helpers
   ========================================================== */
function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

const extOf = (name) => {
  const i = name.lastIndexOf('.');
  return i > 0 ? name.slice(i + 1).toLowerCase() : '';
};

const stemOf = (name) => {
  const i = name.lastIndexOf('.');
  return i > 0 ? name.slice(0, i) : name;
};

function formatSize(bytes) {
  if (!Number.isFinite(bytes)) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(bytes < 10240 ? 1 : 0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function toDate(value) {
  if (value === null || value === undefined || value === '') return null;
  const d = typeof value === 'number' ? new Date(value < 1e11 ? value * 1000 : value) : new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
}

function formatDate(value) {
  const d = toDate(value);
  return d ? I18n.date(d) : '';
}

function formatDateTime(value) {
  const d = toDate(value);
  return d ? I18n.dateTime(d) : '';
}

function formatElapsed(startedAt) {
  const d = toDate(startedAt);
  if (!d) return '';
  const s = Math.max(0, Math.floor((Date.now() - d.getTime()) / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

const folderLabel = (folder) => (folder ? folder.split('/').join(' / ') : t('admin.topLevel'));

const contentUrl = (path, download = false) =>
  `/api/admin/files/content?path=${encodeURIComponent(path)}${download ? '&download=true' : ''}`;

function fileError(file) {
  if (!ALLOWED_EXT.includes(extOf(file.name))) return t('admin.errType');
  if (file.size > MAX_BYTES) return t('admin.errSize');
  if (file.size === 0) return t('admin.errEmpty');
  return '';
}

/* ==========================================================
   Toasts
   ========================================================== */
function toast(message, kind = 'ok') {
  const el = document.createElement('div');
  el.className = 'toast' + (kind === 'error' ? ' toast--error' : '');
  el.textContent = message;
  $('#toasts').appendChild(el);
  setTimeout(() => el.remove(), kind === 'error' ? 7000 : 4000);
}

/* ==========================================================
   Dialog helpers
   ========================================================== */
function openDialog(dialog) {
  dialog.showModal();
}

function setError(id, message) {
  const el = $(id);
  el.textContent = message || '';
  el.hidden = !message;
}

function initDialogs() {
  document.querySelectorAll('dialog').forEach((dialog) => {
    dialog.querySelectorAll('[data-close]').forEach((btn) => btn.addEventListener('click', () => dialog.close()));
    // Clicking the dimmed area outside the box closes it
    dialog.addEventListener('mousedown', (e) => {
      if (e.target === dialog) dialog.close();
    });
  });
}

/* The confirmation's words come from `text()` so they can be rebuilt when
   the language changes while the dialog is open. */
function renderConfirmText() {
  if (!state.confirmText) return;
  const { title, body, label } = state.confirmText();
  $('#confirm-title').textContent = title;
  $('#confirm-body').replaceChildren(...body.map((item) => {
    const p = document.createElement('p');
    p.textContent = item.text;
    if (item.warn) p.className = 'warn';
    if (item.dir) p.dir = 'auto';
    return p;
  }));
  $('#confirm-submit').textContent = label;
}

/* Generic confirmation. `action` runs on confirm; if it throws, the message
   shows in the dialog and the dialog stays open. */
function confirmDialog({ text, danger = false, action }) {
  state.confirmText = text;
  renderConfirmText();
  const submit = $('#confirm-submit');
  submit.className = 'btn ' + (danger ? 'btn--danger' : 'btn--primary');
  submit.disabled = false;
  setError('#confirm-error', '');

  const form = $('#confirm-form');
  form.onsubmit = async (e) => {
    e.preventDefault();
    submit.disabled = true;
    try {
      await action();
      $('#confirm-dialog').close();
    } catch (err) {
      setError('#confirm-error', err.message);
      submit.disabled = false;
    }
  };
  openDialog($('#confirm-dialog'));
}

/* Temporary password shown once */
function renderSecret() {
  const secret = state.secret;
  if (!secret) return;
  $('#secret-title').textContent = t(secret.titleKey);
  $('#secret-sub').innerHTML = esc(t('admin.forWho', { name: '\u0000n', username: '\u0000u' }))
    .replace('\u0000n', `<bdi>${esc(secret.name)}</bdi>`)
    .replace('\u0000u', `<bdi>${esc(secret.username)}</bdi>`);
  $('#secret-copy').textContent = t(state.secretCopied ? 'admin.copied' : 'admin.copy');
}

function showSecret({ titleKey, name, username, password }) {
  state.secret = { titleKey, name, username };
  state.secretCopied = false;
  renderSecret();
  $('#secret-value').textContent = password;
  openDialog($('#secret-dialog'));
}

async function copySecret() {
  const text = $('#secret-value').textContent;
  try {
    await navigator.clipboard.writeText(text);
    state.secretCopied = true;
    renderSecret();
  } catch {
    const range = document.createRange();
    range.selectNodeContents($('#secret-value'));
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
    toast(t('admin.copyHint'), 'error');
  }
}

/* File picker + drop zone wiring. Calls onPick(file or null). */
function wireDropZone({ drop, input, onPick }) {
  const zone = $(drop);
  const field = $(input);
  field.addEventListener('change', () => onPick(field.files[0] || null));
  ['dragenter', 'dragover'].forEach((type) => zone.addEventListener(type, (e) => {
    e.preventDefault();
    zone.classList.add('is-over');
  }));
  ['dragleave', 'drop'].forEach((type) => zone.addEventListener(type, (e) => {
    e.preventDefault();
    zone.classList.remove('is-over');
  }));
  zone.addEventListener('drop', (e) => {
    const file = e.dataTransfer.files[0];
    if (!file) return;
    const transfer = new DataTransfer();
    transfer.items.add(file);
    field.files = transfer.files;
    onPick(file);
  });
}

/* ==========================================================
   Tabs
   ========================================================== */
function selectTab(name) {
  const tabs = { docs: $('#tab-docs'), accounts: $('#tab-accounts') };
  Object.entries(tabs).forEach(([key, tab]) => {
    const on = key === name;
    tab.classList.toggle('is-active', on);
    tab.setAttribute('aria-selected', String(on));
    tab.tabIndex = on ? 0 : -1;
    $(`#panel-${key}`).hidden = !on;
  });
  if (name === 'accounts' && !state.usersLoaded) loadUsers();
}

function initTabs() {
  const order = ['docs', 'accounts'];
  order.forEach((name, i) => {
    const tab = $(`#tab-${name}`);
    tab.addEventListener('click', () => selectTab(name));
    tab.addEventListener('keydown', (e) => {
      if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
      const next = order[(i + (e.key === 'ArrowRight' ? 1 : order.length - 1)) % order.length];
      selectTab(next);
      $(`#tab-${next}`).focus();
    });
  });
}

/* ==========================================================
   Documents: index status bar and background job
   ========================================================== */
const jobTitle = (job) => (job.kind === 'ocr'
  ? t('admin.jobOcr', { target: iso(job.target || t('admin.jobOcrFallback')) })
  : t('admin.jobRebuild'));
const isRunning = () => state.index?.job?.status === 'running';

function setIndex(index) {
  if (!index) return;
  const prev = state.index?.job?.status;
  state.index = index;
  const status = index.job?.status;

  if (status === 'running') {
    state.sawRunning = true;
  } else if (state.sawRunning && (status === 'done' || status === 'error')) {
    state.sawRunning = false;
    showJobResult(index.job);
    loadFiles({ quiet: true });
  } else if (prev === 'running' && status === 'idle') {
    state.sawRunning = false;
    loadFiles({ quiet: true });
  }

  renderIndexBar();
  syncPolling();
}

function renderJobResult() {
  const job = state.jobResult;
  const box = $('#job-result');
  if (!job) { box.hidden = true; return; }
  const failed = job.status === 'error';
  const fallback = failed ? t('admin.jobFailed') : t('admin.jobFinished');
  box.className = 'job-result' + (failed ? ' job-result--error' : '');
  box.innerHTML = `
    <div><strong>${esc(jobTitle(job))}:</strong> <span dir="auto">${esc(job.message || fallback)}</span></div>
    <button type="button" class="act" id="job-dismiss">${esc(t('admin.dismiss'))}</button>`;
  box.hidden = false;
  $('#job-dismiss').addEventListener('click', () => { state.jobResult = null; box.hidden = true; });
}

function showJobResult(job) {
  state.jobResult = job;
  renderJobResult();
  if (job.status !== 'error') toast(job.message || t('admin.jobFinishedToast', { title: jobTitle(job) }));
}

function renderIndexBar() {
  const bar = $('#index-bar');
  const index = state.index;
  if (!index) {
    bar.className = 'index-bar';
    bar.textContent = t('admin.checkingIndex');
    return;
  }
  const job = index.job || {};

  if (job.status === 'running') {
    bar.className = 'index-bar index-bar--running';
    bar.innerHTML = `
      <div class="index-bar__text">
        <div class="index-bar__title" dir="auto">${esc(jobTitle(job))}</div>
        <div class="index-bar__sub">${esc(t('admin.runningFor'))} <span id="job-elapsed">${esc(formatElapsed(job.started_at))}</span>${job.message ? ' &middot; <span dir="auto">' + esc(job.message) + '</span>' : ''}</div>
      </div>
      <button type="button" class="btn btn--outline" disabled>${esc(t('admin.rebuildIndex'))}</button>
      <div class="progress" role="progressbar" aria-label="${esc(t('admin.jobInProgress'))}"></div>`;
    return;
  }

  if (index.stale) {
    bar.className = 'index-bar index-bar--stale';
    bar.innerHTML = `
      <div class="index-bar__text">
        <div class="index-bar__title">${esc(t('admin.indexStale'))}</div>
        <div class="index-bar__sub">${esc(t('admin.indexStaleSub'))}</div>
      </div>
      <button type="button" class="btn btn--primary" id="rebuild-btn">${esc(t('admin.rebuildIndex'))}</button>`;
  } else {
    const built = formatDateTime(index.built_at);
    bar.className = 'index-bar';
    bar.innerHTML = `
      <div class="index-bar__text">
        <span class="index-bar__title">${esc(t('admin.indexUpToDate'))}</span>
        ${built ? `<span class="index-bar__sub"> &middot; ${esc(t('admin.lastBuilt', { date: built }))}</span>` : ''}
      </div>
      <button type="button" class="btn btn--outline" id="rebuild-btn">${esc(t('admin.rebuildIndex'))}</button>`;
  }
  $('#rebuild-btn').addEventListener('click', confirmRebuild);
}

function syncPolling() {
  if (isRunning()) {
    if (!state.pollTimer) state.pollTimer = setInterval(pollIndex, POLL_MS);
    if (!state.tickTimer) state.tickTimer = setInterval(tickElapsed, 1000);
  } else {
    clearInterval(state.pollTimer);
    clearInterval(state.tickTimer);
    state.pollTimer = null;
    state.tickTimer = null;
  }
  // OCR buttons follow the job state
  document.querySelectorAll('[data-act="ocr"]').forEach((btn) => { btn.disabled = isRunning(); });
}

function tickElapsed() {
  const el = $('#job-elapsed');
  if (el) el.textContent = formatElapsed(state.index?.job?.started_at);
}

async function pollIndex() {
  try {
    const res = await Auth.api('/api/admin/index');
    setIndex(res.index || res);
  } catch {
    /* Keep polling; a blip shouldn't stop the status bar */
  }
}

function confirmRebuild() {
  confirmDialog({
    text: () => ({
      title: t('admin.rebuildTitle'),
      body: [
        { text: t('admin.rebuildBody1') },
        { text: t('admin.rebuildBody2'), warn: true },
      ],
      label: t('admin.rebuildIndex'),
    }),
    action: async () => {
      const res = await Auth.api('/api/admin/index/rebuild', { method: 'POST' });
      setIndex(res.index);
      toast(t('admin.rebuildStarted'));
    },
  });
}

/* ==========================================================
   Documents: list
   ========================================================== */
async function loadFiles({ quiet = false } = {}) {
  if (!quiet && !state.filesLoaded) {
    $('#file-list').innerHTML = `<div class="state">${esc(t('admin.loadingDocs'))}</div>`;
  }
  try {
    const data = await Auth.api('/api/admin/files');
    state.files = data.files || [];
    state.folders = data.folders || [''];
    state.filesLoaded = true;
    setIndex(data.index);
    renderFolderFilter();
    renderFiles();
  } catch (err) {
    if (!state.filesLoaded) {
      $('#file-list').innerHTML = `<div class="state state--error"><strong>${esc(t('admin.loadDocsFail'))}</strong>${esc(err.message)}</div>`;
    } else {
      toast(err.message, 'error');
    }
  }
}

function renderFolderFilter() {
  const select = $('#folder-filter');
  // Empty on the first load: "" would otherwise match the top-level folder
  const current = select.options.length ? select.value : '__all';
  select.innerHTML = `<option value="__all">${esc(t('admin.allFolders'))}</option>` +
    state.folders.map((f) => `<option value="${esc(f)}">${esc(folderLabel(f))}</option>`).join('');
  select.value = [...select.options].some((o) => o.value === current) ? current : '__all';
}

function visibleFiles() {
  const q = $('#file-search').value.trim().toLowerCase();
  const folder = $('#folder-filter').value;
  return state.files.filter((f) => {
    if (folder !== '__all' && !(f.folder === folder || (folder && f.folder.startsWith(folder + '/')))) return false;
    return !q || f.path.toLowerCase().includes(q);
  });
}

function renderFiles() {
  const list = $('#file-list');
  const files = visibleFiles();
  const searching = $('#file-search').value.trim() !== '';
  $('#file-count').textContent = state.filesLoaded
    ? t('admin.docCount', { shown: files.length, total: state.files.length })
    : '';

  if (!files.length) {
    list.innerHTML = state.files.length
      ? `<div class="state"><strong>${esc(t('admin.noFilesMatch'))}</strong>${esc(t('admin.noFilesMatchHint'))}</div>`
      : `<div class="state"><strong>${esc(t('admin.noDocs'))}</strong>${esc(t('admin.noDocsHint'))}</div>`;
    return;
  }

  const groups = new Map();
  files.forEach((f) => {
    if (!groups.has(f.folder)) groups.set(f.folder, []);
    groups.get(f.folder).push(f);
  });

  const busy = isRunning();
  const html = [...groups.keys()].sort((a, b) => a.localeCompare(b)).map((folder) => {
    const items = groups.get(folder).sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
    const open = searching || state.expanded.has(folder);
    return `
      <div class="group${open ? ' is-open' : ''}" data-folder="${esc(folder)}">
        <button type="button" class="group__head" aria-expanded="${open}" data-toggle>
          <svg class="group__chev" fill="none" stroke="currentColor" stroke-width="2.2" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7"></path></svg>
          <span class="group__path" dir="auto">${esc(folderLabel(folder))}</span>
          <span class="count">${items.length}</span>
        </button>
        <ul class="rows"${open ? '' : ' hidden'}>${items.map((f) => fileRow(f, busy)).join('')}</ul>
      </div>`;
  }).join('');
  list.innerHTML = html;

  if (state.highlight) {
    const row = [...list.querySelectorAll('.row')].find((r) => r.dataset.path === state.highlight);
    if (row) {
      row.classList.add('is-new');
      row.scrollIntoView({ block: 'center', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
      setTimeout(() => row.classList.remove('is-new'), 2500);
    }
    state.highlight = '';
  }
}

function fileRow(f, busy) {
  const ext = extOf(f.name);
  const isPdf = ext === 'pdf';
  return `
    <li class="row" data-path="${esc(f.path)}">
      <div class="row__name" dir="auto">${esc(f.name)}</div>
      <div class="row__meta">
        <span class="row__cell"><span class="badge badge--${esc(ext)}">${esc(ext.toUpperCase() || t('admin.fileLabel'))}</span></span>
        <span class="row__cell">${esc(formatSize(f.size))}</span>
        <span class="row__cell">${esc(formatDate(f.modified))}</span>
      </div>
      <div class="row__actions">
        <button type="button" class="act" data-act="view" aria-label="${esc(t('admin.viewFile', { name: iso(f.name) }))}">${esc(t('admin.view'))}</button>
        <button type="button" class="act" data-act="replace" aria-label="${esc(t('admin.replaceFileAria', { name: iso(f.name) }))}">${esc(t('admin.replace'))}</button>
        ${isPdf ? `<button type="button" class="act" data-act="ocr" aria-label="${esc(t('admin.ocrFile', { name: iso(f.name) }))}"${busy ? ' disabled' : ''}>${esc(t('admin.ocr'))}</button>` : ''}
        <button type="button" class="act act--danger" data-act="remove" aria-label="${esc(t('admin.removeFile', { name: iso(f.name) }))}">${esc(t('admin.remove'))}</button>
      </div>
    </li>`;
}

function onFileListClick(e) {
  const toggle = e.target.closest('[data-toggle]');
  if (toggle) {
    const group = toggle.closest('.group');
    const folder = group.dataset.folder;
    const open = !group.classList.contains('is-open');
    group.classList.toggle('is-open', open);
    group.querySelector('.rows').hidden = !open;
    toggle.setAttribute('aria-expanded', String(open));
    if (open) state.expanded.add(folder); else state.expanded.delete(folder);
    return;
  }
  const btn = e.target.closest('[data-act]');
  if (!btn) return;
  const path = btn.closest('.row').dataset.path;
  const file = state.files.find((f) => f.path === path);
  if (!file) return;
  if (btn.dataset.act === 'view') openPreview(file);
  if (btn.dataset.act === 'replace') openReplace(file, btn);
  if (btn.dataset.act === 'remove') confirmRemove(file);
  if (btn.dataset.act === 'ocr') confirmOcr(file);
}

/* ==========================================================
   Documents: viewer
   Shows the file in the page (PDF in the browser's own viewer, Word and
   text files as text). Previous / Next step through the files the list
   shows now, so a folder can be reviewed one file after another.
   ========================================================== */
let previewFile = null;
let previewSeq = 0;

function viewerState(title, detail, withDownload) {
  const box = document.createElement('div');
  box.className = 'viewer__state';
  const strong = document.createElement('strong');
  strong.textContent = title;
  box.append(strong);
  if (detail) {
    const p = document.createElement('p');
    p.textContent = detail;
    box.append(p);
  }
  if (withDownload) {
    const a = document.createElement('a');
    a.className = 'btn btn--outline';
    a.href = contentUrl(previewFile.path, true);
    a.textContent = t('admin.downloadInstead');
    box.append(a);
  }
  return box;
}

function viewerNotice(text) {
  const p = document.createElement('p');
  p.className = 'viewer__notice';
  p.textContent = text;
  return p;
}

function updatePreviewNav() {
  const list = visibleFiles();
  const i = list.findIndex((f) => f.path === previewFile.path);
  $('#preview-prev').disabled = i <= 0;
  $('#preview-next').disabled = i < 0 || i >= list.length - 1;
  $('#preview-pos').textContent = i >= 0 ? t('admin.position', { n: i + 1, total: list.length }) : '';
}

async function showPreview(file) {
  previewFile = file;
  const seq = ++previewSeq;
  const ext = extOf(file.name);

  $('#preview-title').textContent = file.name;
  const badge = $('#preview-badge');
  badge.className = `badge badge--${ext}`;
  badge.textContent = ext.toUpperCase();
  $('#preview-folder').textContent = folderLabel(file.folder);
  $('#preview-size').textContent = formatSize(file.size);
  $('#preview-date').textContent = t('admin.modified', { date: formatDate(file.modified) });
  const download = $('#preview-download');
  download.href = contentUrl(file.path, true);
  download.setAttribute('download', file.name);
  download.setAttribute('aria-label', t('admin.downloadAria', { name: iso(file.name) }));
  updatePreviewNav();

  const body = $('#preview-body');
  body.classList.remove('has-notice');
  if (ext === 'pdf') {
    const frame = document.createElement('iframe');
    frame.className = 'viewer__frame';
    frame.title = file.name;
    frame.src = contentUrl(file.path);
    body.replaceChildren(frame);
    return;
  }

  body.replaceChildren(viewerState(t('admin.opening')));
  let data;
  try {
    data = await Auth.api(`/api/admin/files/preview?path=${encodeURIComponent(file.path)}`);
  } catch (err) {
    if (seq === previewSeq) body.replaceChildren(viewerState(t('admin.cantShow'), err.message, true));
    return;
  }
  if (seq !== previewSeq) return;   // another file was opened meanwhile

  if (!data.text) {
    body.replaceChildren(viewerState(t('admin.noText'), t('admin.noTextHint'), true));
    return;
  }
  const nodes = [];
  if (ext === 'docx') nodes.push(viewerNotice(t('admin.docxNotice')));
  if (data.truncated) nodes.push(viewerNotice(t('admin.truncatedNotice')));
  const pre = document.createElement('pre');
  pre.className = 'viewer__text';
  pre.dir = 'auto';
  pre.tabIndex = 0;
  pre.textContent = data.text;
  nodes.push(pre);
  body.classList.toggle('has-notice', nodes.length > 1);
  body.replaceChildren(...nodes);
}

function openPreview(file) {
  const dialog = $('#preview-dialog');
  if (!dialog.open) openDialog(dialog);
  showPreview(file);
}

function stepPreview(delta) {
  const list = visibleFiles();
  const next = list[list.findIndex((f) => f.path === previewFile.path) + delta];
  if (next) showPreview(next);
}

function initPreview() {
  const dialog = $('#preview-dialog');
  $('#preview-prev').addEventListener('click', () => stepPreview(-1));
  $('#preview-next').addEventListener('click', () => stepPreview(1));
  $('#preview-replace').addEventListener('click', () => {
    const file = previewFile;
    dialog.close();
    openReplace(file);
  });
  $('#preview-remove').addEventListener('click', () => {
    const file = previewFile;
    dialog.close();
    confirmRemove(file);
  });
  // Alt + Down / Up move between files; plain arrows keep scrolling the text
  dialog.addEventListener('keydown', (e) => {
    if (!e.altKey) return;
    if (e.key === 'ArrowDown') { e.preventDefault(); stepPreview(1); }
    if (e.key === 'ArrowUp') { e.preventDefault(); stepPreview(-1); }
  });
  // Unload the file when the viewer closes, so a big PDF stops using memory
  dialog.addEventListener('close', () => {
    previewSeq += 1;
    $('#preview-body').replaceChildren();
  });
}

/* ==========================================================
   Documents: replace
   ========================================================== */
let replaceTarget = null;
let replaceFile = null;

function renderReplaceTexts() {
  if (!replaceTarget) return;
  $('#replace-title').textContent = t('admin.replaceTitle', { name: iso(replaceTarget.name) });
  $('#replace-sub').textContent = t('admin.inFolder', { folder: iso(folderLabel(replaceTarget.folder)) });
  $('#replace-drop-text').textContent = replaceFile
    ? `${replaceFile.name} (${formatSize(replaceFile.size)})`
    : t('admin.dropNew');
}

function openReplace(file) {
  replaceTarget = file;
  replaceFile = null;
  $('#replace-form').reset();
  $('#replace-drop').classList.remove('has-file');
  renderReplaceTexts();
  $('#replace-choice').disabled = true;
  $('#replace-submit').disabled = true;
  $('#replace-keep').textContent = '-';
  $('#replace-new').textContent = '-';
  setError('#replace-error', '');
  openDialog($('#replace-dialog'));
}

function onReplacePick(file) {
  setError('#replace-error', '');
  replaceFile = null;
  if (!file) return;
  const problem = fileError(file);
  if (problem) {
    setError('#replace-error', problem);
    $('#replace-file').value = '';
    $('#replace-drop').classList.remove('has-file');
    renderReplaceTexts();
    $('#replace-choice').disabled = true;
    $('#replace-submit').disabled = true;
    return;
  }
  replaceFile = file;
  $('#replace-drop').classList.add('has-file');
  renderReplaceTexts();
  $('#replace-drop-text').dir = 'auto';
  $('#replace-keep').textContent = `${stemOf(replaceTarget.name)}.${extOf(file.name)}`;
  $('#replace-new').textContent = file.name;
  $('#replace-choice').disabled = false;
  $('#replace-submit').disabled = false;
}

async function submitReplace(e) {
  e.preventDefault();
  if (!replaceFile || !replaceTarget) return;
  const keep = $('#replace-form').elements.keep_name.value;
  const body = new FormData();
  body.append('path', replaceTarget.path);
  body.append('keep_name', keep);
  body.append('file', replaceFile);
  const submit = $('#replace-submit');
  submit.disabled = true;
  submit.textContent = t('admin.replacing');
  try {
    const res = await Auth.api('/api/admin/files/replace', { method: 'POST', body });
    $('#replace-dialog').close();
    const newName = res.file?.name || replaceFile.name;
    state.highlight = res.file?.path || '';
    if (res.file) state.expanded.add(res.file.folder);  // so the highlighted row is visible
    toast(t('admin.replacedToast', { name: iso(newName) }));
    await loadFiles({ quiet: true });
    setIndex(res.index);
  } catch (err) {
    setError('#replace-error', err.message);
    submit.disabled = false;
  } finally {
    submit.textContent = t('admin.replaceFile');
  }
}

/* ==========================================================
   Documents: add
   ========================================================== */
let addFile = null;

function renderAddFolders(selected) {
  const select = $('#add-folder');
  select.innerHTML = state.folders
    .map((f) => `<option value="${esc(f)}">${esc(folderLabel(f))}</option>`).join('');
  select.value = selected;
}

function renderAddDropText() {
  $('#add-drop-text').textContent = addFile ? `${addFile.name} (${formatSize(addFile.size)})` : t('admin.dropFile');
}

function openAdd() {
  addFile = null;
  $('#add-form').reset();
  const current = $('#folder-filter').value;
  renderAddFolders(current !== '__all' && state.folders.includes(current) ? current : '');
  $('#add-drop').classList.remove('has-file');
  renderAddDropText();
  $('#add-submit').disabled = true;
  setError('#add-error', '');
  openDialog($('#add-dialog'));
}

function onAddPick(file) {
  setError('#add-error', '');
  addFile = null;
  if (!file) return;
  const problem = fileError(file);
  if (problem) {
    setError('#add-error', problem);
    $('#add-file').value = '';
    $('#add-drop').classList.remove('has-file');
    renderAddDropText();
    $('#add-submit').disabled = true;
    return;
  }
  addFile = file;
  $('#add-drop').classList.add('has-file');
  renderAddDropText();
  $('#add-drop-text').dir = 'auto';
  $('#add-submit').disabled = false;
}

async function submitAdd(e) {
  e.preventDefault();
  if (!addFile) return;
  const body = new FormData();
  body.append('folder', $('#add-folder').value);
  body.append('file', addFile);
  const submit = $('#add-submit');
  submit.disabled = true;
  submit.textContent = t('admin.adding');
  try {
    const res = await Auth.api('/api/admin/files', { method: 'POST', body });
    $('#add-dialog').close();
    state.highlight = res.file?.path || '';
    if (res.file) state.expanded.add(res.file.folder);  // so the highlighted row is visible
    toast(t('admin.addedToast', { name: iso(res.file?.name || addFile.name) }));
    await loadFiles({ quiet: true });
    setIndex(res.index);
  } catch (err) {
    setError('#add-error', err.message);
    submit.disabled = false;
  } finally {
    submit.textContent = t('admin.addDocument');
  }
}

/* ==========================================================
   Documents: remove and OCR
   ========================================================== */
function confirmRemove(file) {
  confirmDialog({
    text: () => ({
      title: t('admin.removeTitle', { name: iso(file.name) }),
      body: [
        { text: t('admin.removeBody') },
        { text: t('admin.folderLine', { folder: iso(folderLabel(file.folder)) }), dir: true },
      ],
      label: t('admin.removeFileBtn'),
    }),
    danger: true,
    action: async () => {
      const res = await Auth.api('/api/admin/files/remove', { method: 'POST', body: { path: file.path } });
      toast(t('admin.removedToast', { name: iso(file.name) }));
      await loadFiles({ quiet: true });
      setIndex(res.index);
    },
  });
}

function confirmOcr(file) {
  confirmDialog({
    text: () => ({
      title: t('admin.ocrTitle', { name: iso(file.name) }),
      body: [
        { text: t('admin.ocrBody1') },
        { text: t('admin.ocrBody2') },
      ],
      label: t('admin.startOcr'),
    }),
    action: async () => {
      const res = await Auth.api('/api/admin/files/ocr', { method: 'POST', body: { path: file.path } });
      setIndex(res.index);
      toast(t('admin.ocrStarted'));
    },
  });
}

/* ==========================================================
   Accounts
   ========================================================== */
const roleLabel = (role) => (['student', 'advisor', 'admin'].includes(role) ? t(`role.${role}`) : role);
const ROLES = ['student', 'advisor', 'admin'];

/* Your own role is shown, not editable (the server refuses it too). */
function roleCell(u, me) {
  if (u.id === me) return `<span class="badge">${esc(roleLabel(u.role))}</span>`;
  return `
    <select class="input input--role" data-urole aria-label="${esc(t('admin.roleFor', { name: iso(u.name) }))}">
      ${ROLES.map((r) => `<option value="${r}"${r === u.role ? ' selected' : ''}>${esc(roleLabel(r))}</option>`).join('')}
    </select>`;
}

async function loadUsers() {
  if (!state.usersLoaded) $('#user-list').innerHTML = `<div class="state">${esc(t('admin.loadingAccounts'))}</div>`;
  try {
    state.users = (await Auth.api('/api/admin/users')).users || [];
    state.usersLoaded = true;
    renderUsers();
  } catch (err) {
    if (!state.usersLoaded) {
      $('#user-list').innerHTML = `<div class="state state--error"><strong>${esc(t('admin.loadAccountsFail'))}</strong>${esc(err.message)}</div>`;
    } else {
      toast(err.message, 'error');
    }
  }
}

function visibleUsers() {
  const q = $('#user-search').value.trim().toLowerCase();
  const role = $('#role-filter').value;
  return state.users.filter((u) => (
    (!role || u.role === role) &&
    (!q || u.name.toLowerCase().includes(q) || u.username.toLowerCase().includes(q))
  ));
}

function statusBadge(u) {
  if (!u.active) return `<span class="badge badge--danger">${esc(t('admin.statusDisabled'))}</span>`;
  if (u.must_change_password) return `<span class="badge badge--warn">${esc(t('admin.statusTemp'))}</span>`;
  return `<span class="badge badge--primary">${esc(t('admin.statusActive'))}</span>`;
}

function renderUsers() {
  const users = visibleUsers();
  $('#user-count').textContent = t('admin.accountCount', { shown: users.length, total: state.users.length });
  if (!users.length) {
    $('#user-list').innerHTML = state.users.length
      ? `<div class="state"><strong>${esc(t('admin.noAccountsMatch'))}</strong>${esc(t('admin.noAccountsMatchHint'))}</div>`
      : `<div class="state"><strong>${esc(t('admin.noAccounts'))}</strong>${esc(t('admin.noAccountsHint'))}</div>`;
    return;
  }
  const me = Auth.user?.id;
  $('#user-list').innerHTML = `
    <div class="table-wrap">
      <table class="table">
        <thead>
          <tr><th>${esc(t('admin.name'))}</th><th>${esc(t('admin.id'))}</th><th>${esc(t('admin.role'))}</th><th>${esc(t('admin.status'))}</th><th>${esc(t('admin.created'))}</th><th><span class="sr-only">${esc(t('admin.actions'))}</span></th></tr>
        </thead>
        <tbody>
          ${users.map((u) => `
            <tr data-id="${esc(u.id)}">
              <td class="cell-name" data-label="${esc(t('admin.name'))}"><span dir="auto">${esc(u.name)}</span>${u.id === me ? `<span class="you">${esc(t('admin.you'))}</span>` : ''}</td>
              <td class="cell-mono" data-label="${esc(t('admin.id'))}" dir="auto">${esc(u.username)}</td>
              <td data-label="${esc(t('admin.role'))}">${roleCell(u, me)}</td>
              <td data-label="${esc(t('admin.status'))}">${statusBadge(u)}</td>
              <td class="cell-muted" data-label="${esc(t('admin.created'))}">${esc(formatDate(u.created_at))}</td>
              <td class="cell-actions">${u.id === me ? '' : `
                <button type="button" class="act" data-uact="toggle">${esc(t(u.active ? 'admin.disable' : 'admin.enable'))}</button>
                <button type="button" class="act" data-uact="reset">${esc(t('admin.resetPassword'))}</button>`}
              </td>
            </tr>`).join('')}
        </tbody>
      </table>
    </div>`;
}

function onUserListClick(e) {
  const btn = e.target.closest('[data-uact]');
  if (!btn) return;
  const user = state.users.find((u) => u.id === btn.closest('tr').dataset.id);
  if (!user) return;
  if (btn.dataset.uact === 'toggle') toggleUser(user, btn);
  if (btn.dataset.uact === 'reset') confirmReset(user);
}

function onUserListChange(e) {
  const select = e.target.closest('[data-urole]');
  if (!select) return;
  const user = state.users.find((u) => u.id === select.closest('tr').dataset.id);
  if (!user || select.value === user.role) return;
  confirmRoleChange(user, select.value);
}

function confirmRoleChange(user, role) {
  // Cancel puts the dropdown back; after a change it shows the saved role.
  $('#confirm-dialog').addEventListener('close', renderUsers, { once: true });
  confirmDialog({
    text: () => ({
      title: t('admin.roleTitle', { name: iso(user.name), role: roleLabel(role) }),
      body: [
        { text: t('admin.roleBody', { from: roleLabel(user.role), to: roleLabel(role) }) },
        ...(role === 'admin'
          ? [{ text: t('admin.roleAdminWarn'), warn: true }]
          : []),
      ],
      label: t('admin.changeRole'),
    }),
    action: async () => {
      await Auth.api(`/api/admin/users/${encodeURIComponent(user.id)}`, { method: 'PATCH', body: { role } });
      toast(t('admin.roleChanged', { name: iso(user.name), role: roleLabel(role) }));
      await loadUsers();
    },
  });
}

async function toggleUser(user, btn) {
  btn.disabled = true;
  try {
    await Auth.api(`/api/admin/users/${encodeURIComponent(user.id)}`, { method: 'PATCH', body: { active: !user.active } });
    toast(t(user.active ? 'admin.disabledToast' : 'admin.enabledToast', { name: iso(user.name) }));
    await loadUsers();
  } catch (err) {
    toast(err.message, 'error');
    btn.disabled = false;
  }
}

function confirmReset(user) {
  confirmDialog({
    text: () => ({
      title: t('admin.resetTitle', { name: iso(user.name) }),
      body: [{ text: t('admin.resetBody') }],
      label: t('admin.resetPassword'),
    }),
    action: async () => {
      const res = await Auth.api(`/api/admin/users/${encodeURIComponent(user.id)}/reset-password`, { method: 'POST' });
      $('#confirm-dialog').close();
      showSecret({ titleKey: 'admin.tempPassword', name: user.name, username: user.username, password: res.temporary_password });
      loadUsers();
    },
  });
}

function openAddAccount() {
  $('#account-form').reset();
  setError('#account-error', '');
  $('#account-submit').disabled = false;
  openDialog($('#account-dialog'));
}

async function submitAccount(e) {
  e.preventDefault();
  const name = $('#account-name').value.trim();
  const username = $('#account-username').value.trim();
  const role = $('#account-role').value;
  if (!name) return setError('#account-error', t('admin.errName'));
  if (!/^[A-Za-z0-9._@-]{3,60}$/.test(username)) {
    return setError('#account-error', t('admin.errId'));
  }
  setError('#account-error', '');
  const submit = $('#account-submit');
  submit.disabled = true;
  try {
    const res = await Auth.api('/api/admin/users', { method: 'POST', body: { username, name, role } });
    $('#account-dialog').close();
    showSecret({ titleKey: 'admin.accountCreated', name: res.user.name, username: res.user.username, password: res.temporary_password });
    loadUsers();
  } catch (err) {
    setError('#account-error', err.message);
    submit.disabled = false;
  }
}

/* ==========================================================
   Init
   ========================================================== */
function init() {
  initTabs();
  initDialogs();

  $('#sign-out-btn').addEventListener('click', () => Auth.signOut());

  // Documents
  $('#file-search').addEventListener('input', renderFiles);
  $('#folder-filter').addEventListener('change', renderFiles);
  $('#file-list').addEventListener('click', onFileListClick);
  initPreview();
  $('#add-doc-btn').addEventListener('click', openAdd);
  wireDropZone({ drop: '#replace-drop', input: '#replace-file', onPick: onReplacePick });
  wireDropZone({ drop: '#add-drop', input: '#add-file', onPick: onAddPick });
  $('#replace-form').addEventListener('submit', submitReplace);
  $('#add-form').addEventListener('submit', submitAdd);

  // Accounts
  $('#user-search').addEventListener('input', renderUsers);
  $('#role-filter').addEventListener('change', renderUsers);
  $('#user-list').addEventListener('click', onUserListClick);
  $('#user-list').addEventListener('change', onUserListChange);
  $('#add-account-btn').addEventListener('click', openAddAccount);
  $('#account-form').addEventListener('submit', submitAccount);
  $('#secret-copy').addEventListener('click', copySecret);

  // Redraw everything the script wrote when the language switches
  I18n.onChange(() => {
    renderIndexBar();
    renderJobResult();
    if (state.filesLoaded) {
      renderFolderFilter();
      renderFiles();
    } else {
      $('#file-list').innerHTML = `<div class="state">${esc(t('admin.loadingDocs'))}</div>`;
    }
    if (state.usersLoaded) renderUsers();
    else if (!$('#panel-accounts').hidden) $('#user-list').innerHTML = `<div class="state">${esc(t('admin.loadingAccounts'))}</div>`;
    if ($('#confirm-dialog').open) renderConfirmText();
    if ($('#secret-dialog').open) renderSecret();
    if ($('#replace-dialog').open) renderReplaceTexts();
    if ($('#add-dialog').open) {
      renderAddFolders($('#add-folder').value);
      renderAddDropText();
    }
    if ($('#preview-dialog').open && previewFile) {
      $('#preview-date').textContent = t('admin.modified', { date: formatDate(previewFile.modified) });
      $('#preview-folder').textContent = folderLabel(previewFile.folder);
      $('#preview-download').setAttribute('aria-label', t('admin.downloadAria', { name: iso(previewFile.name) }));
      updatePreviewNav();
    }
  });

  renderConfirmText();
  renderIndexBar();
  loadFiles();
}

Auth.requireRole('admin').then((user) => {
  Auth.fillUser(user);
  init();
});
