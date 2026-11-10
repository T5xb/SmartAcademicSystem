/* ==========================================================
   Academic AI - Admin console
   Documents (the chatbot's sources) and Accounts.
   ========================================================== */

const $ = (s) => document.querySelector(s);

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
  collapsed: new Set(),
  highlight: '',
  users: [],
  usersLoaded: false,
  pollTimer: null,
  tickTimer: null,
  sawRunning: false,
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
  return d ? d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '';
}

function formatDateTime(value) {
  const d = toDate(value);
  return d
    ? d.toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
    : '';
}

function formatElapsed(startedAt) {
  const d = toDate(startedAt);
  if (!d) return '';
  const s = Math.max(0, Math.floor((Date.now() - d.getTime()) / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

const folderLabel = (folder) => (folder ? folder.split('/').join(' / ') : 'Top level');

const contentUrl = (path, download = false) =>
  `/api/admin/files/content?path=${encodeURIComponent(path)}${download ? '&download=true' : ''}`;

function fileError(file) {
  if (!ALLOWED_EXT.includes(extOf(file.name))) return 'Only PDF, DOCX, TXT and MD files are allowed.';
  if (file.size > MAX_BYTES) return 'That file is larger than 50 MB.';
  if (file.size === 0) return 'That file is empty.';
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

/* Generic confirmation. `action` runs on confirm; if it throws, the message
   shows in the dialog and the dialog stays open. */
function confirmDialog({ title, body, label, danger = false, action }) {
  $('#confirm-title').textContent = title;
  const bodyEl = $('#confirm-body');
  bodyEl.replaceChildren(...body.map((item) => {
    const p = document.createElement('p');
    p.textContent = item.text;
    if (item.warn) p.className = 'warn';
    if (item.dir) p.dir = 'auto';
    return p;
  }));
  const submit = $('#confirm-submit');
  submit.textContent = label;
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
function showSecret({ title, who, password }) {
  $('#secret-title').textContent = title;
  $('#secret-sub').textContent = who;
  $('#secret-value').textContent = password;
  $('#secret-copy').textContent = 'Copy';
  openDialog($('#secret-dialog'));
}

async function copySecret() {
  const text = $('#secret-value').textContent;
  try {
    await navigator.clipboard.writeText(text);
    $('#secret-copy').textContent = 'Copied';
  } catch {
    const range = document.createRange();
    range.selectNodeContents($('#secret-value'));
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
    toast('Press Ctrl+C to copy the selected password.', 'error');
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
const jobTitle = (job) => (job.kind === 'ocr' ? `Reading ${job.target || 'a PDF'} (OCR)` : 'Rebuilding the index');
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

function showJobResult(job) {
  const box = $('#job-result');
  const failed = job.status === 'error';
  const fallback = failed ? 'The job failed.' : 'Finished.';
  box.className = 'job-result' + (failed ? ' job-result--error' : '');
  box.innerHTML = `
    <div><strong>${esc(jobTitle(job))}:</strong> <span dir="auto">${esc(job.message || fallback)}</span></div>
    <button type="button" class="act" id="job-dismiss">Dismiss</button>`;
  box.hidden = false;
  $('#job-dismiss').addEventListener('click', () => { box.hidden = true; });
  if (!failed) toast(job.message || `${jobTitle(job)} finished`);
}

function renderIndexBar() {
  const bar = $('#index-bar');
  const index = state.index;
  if (!index) {
    bar.className = 'index-bar';
    bar.textContent = 'Checking the index...';
    return;
  }
  const job = index.job || {};

  if (job.status === 'running') {
    bar.className = 'index-bar index-bar--running';
    bar.innerHTML = `
      <div class="index-bar__text">
        <div class="index-bar__title" dir="auto">${esc(jobTitle(job))}</div>
        <div class="index-bar__sub">Running for <span id="job-elapsed">${esc(formatElapsed(job.started_at))}</span>${job.message ? ' &middot; <span dir="auto">' + esc(job.message) + '</span>' : ''}</div>
      </div>
      <button type="button" class="btn btn--outline" disabled>Rebuild index</button>
      <div class="progress" role="progressbar" aria-label="Job in progress"></div>`;
    return;
  }

  if (index.stale) {
    bar.className = 'index-bar index-bar--stale';
    bar.innerHTML = `
      <div class="index-bar__text">
        <div class="index-bar__title">Documents changed since the last index build.</div>
        <div class="index-bar__sub">The chatbot still answers from the old files.</div>
      </div>
      <button type="button" class="btn btn--primary" id="rebuild-btn">Rebuild index</button>`;
  } else {
    const built = formatDateTime(index.built_at);
    bar.className = 'index-bar';
    bar.innerHTML = `
      <div class="index-bar__text">
        <span class="index-bar__title">Index is up to date</span>
        ${built ? `<span class="index-bar__sub"> &middot; last built ${esc(built)}</span>` : ''}
      </div>
      <button type="button" class="btn btn--outline" id="rebuild-btn">Rebuild index</button>`;
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
    title: 'Rebuild the index?',
    body: [
      { text: 'This re-reads every document so the chatbot answers from the current files.' },
      { text: "The chatbot can't answer questions for a few minutes while the index is rebuilt.", warn: true },
    ],
    label: 'Rebuild index',
    action: async () => {
      const res = await Auth.api('/api/admin/index/rebuild', { method: 'POST' });
      setIndex(res.index);
      toast('Index rebuild started');
    },
  });
}

/* ==========================================================
   Documents: list
   ========================================================== */
async function loadFiles({ quiet = false } = {}) {
  if (!quiet && !state.filesLoaded) {
    $('#file-list').innerHTML = '<div class="state">Loading documents...</div>';
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
      $('#file-list').innerHTML = `<div class="state state--error"><strong>Couldn't load documents</strong>${esc(err.message)}</div>`;
    } else {
      toast(err.message, 'error');
    }
  }
}

function renderFolderFilter() {
  const select = $('#folder-filter');
  // Empty on the first load: "" would otherwise match the top-level folder
  const current = select.options.length ? select.value : '__all';
  select.innerHTML = '<option value="__all">All folders</option>' +
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
    ? `${files.length} of ${state.files.length} documents`
    : '';

  if (!files.length) {
    list.innerHTML = state.files.length
      ? '<div class="state"><strong>No files match this search</strong>Try a shorter name, or choose All folders.</div>'
      : '<div class="state"><strong>No documents yet</strong>Use Add document to upload the first one.</div>';
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
    const open = searching || !state.collapsed.has(folder);
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
        <span class="row__cell"><span class="badge badge--${esc(ext)}">${esc(ext.toUpperCase() || 'FILE')}</span></span>
        <span class="row__cell">${esc(formatSize(f.size))}</span>
        <span class="row__cell">${esc(formatDate(f.modified))}</span>
      </div>
      <div class="row__actions">
        <button type="button" class="act" data-act="view" aria-label="View ${esc(f.name)}">View</button>
        <button type="button" class="act" data-act="replace" aria-label="Replace ${esc(f.name)}">Replace</button>
        ${isPdf ? `<button type="button" class="act" data-act="ocr" aria-label="Run OCR on ${esc(f.name)}"${busy ? ' disabled' : ''}>OCR</button>` : ''}
        <button type="button" class="act act--danger" data-act="remove" aria-label="Remove ${esc(f.name)}">Remove</button>
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
    if (open) state.collapsed.delete(folder); else state.collapsed.add(folder);
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
    a.textContent = 'Download the file instead';
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
  $('#preview-pos').textContent = i >= 0 ? `${i + 1} of ${list.length}` : '';
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
  $('#preview-date').textContent = `Modified ${formatDate(file.modified)}`;
  const download = $('#preview-download');
  download.href = contentUrl(file.path, true);
  download.setAttribute('download', file.name);
  download.setAttribute('aria-label', `Download ${file.name}`);
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

  body.replaceChildren(viewerState('Opening the file…'));
  let data;
  try {
    data = await Auth.api(`/api/admin/files/preview?path=${encodeURIComponent(file.path)}`);
  } catch (err) {
    if (seq === previewSeq) body.replaceChildren(viewerState("This file can't be shown here", err.message, true));
    return;
  }
  if (seq !== previewSeq) return;   // another file was opened meanwhile

  if (!data.text) {
    body.replaceChildren(viewerState('This file has no text', 'It may hold only images. Download it to see it.', true));
    return;
  }
  const nodes = [];
  if (ext === 'docx') nodes.push(viewerNotice('Showing the text of this Word file. Download it to see its layout and tables.'));
  if (data.truncated) nodes.push(viewerNotice('This file is long, so only its beginning is shown. Download it to read all of it.'));
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

function openReplace(file) {
  replaceTarget = file;
  replaceFile = null;
  $('#replace-form').reset();
  $('#replace-title').textContent = `Replace ${file.name}`;
  $('#replace-title').dir = 'auto';
  $('#replace-sub').textContent = `In ${folderLabel(file.folder)}`;
  $('#replace-drop').classList.remove('has-file');
  $('#replace-drop-text').textContent = 'Choose the new file, or drop it here';
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
    $('#replace-drop-text').textContent = 'Choose the new file, or drop it here';
    $('#replace-choice').disabled = true;
    $('#replace-submit').disabled = true;
    return;
  }
  replaceFile = file;
  $('#replace-drop').classList.add('has-file');
  $('#replace-drop-text').textContent = `${file.name} (${formatSize(file.size)})`;
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
  submit.textContent = 'Replacing...';
  try {
    const res = await Auth.api('/api/admin/files/replace', { method: 'POST', body });
    $('#replace-dialog').close();
    const newName = res.file?.name || replaceFile.name;
    state.highlight = res.file?.path || '';
    toast(`Replaced ${newName}`);
    await loadFiles({ quiet: true });
    setIndex(res.index);
  } catch (err) {
    setError('#replace-error', err.message);
    submit.disabled = false;
  } finally {
    submit.textContent = 'Replace file';
  }
}

/* ==========================================================
   Documents: add
   ========================================================== */
let addFile = null;

function openAdd() {
  addFile = null;
  $('#add-form').reset();
  const current = $('#folder-filter').value;
  $('#add-folder').innerHTML = state.folders
    .map((f) => `<option value="${esc(f)}">${esc(folderLabel(f))}</option>`).join('');
  $('#add-folder').value = current !== '__all' && state.folders.includes(current) ? current : '';
  $('#add-drop').classList.remove('has-file');
  $('#add-drop-text').textContent = 'Choose a file, or drop it here';
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
    $('#add-drop-text').textContent = 'Choose a file, or drop it here';
    $('#add-submit').disabled = true;
    return;
  }
  addFile = file;
  $('#add-drop').classList.add('has-file');
  $('#add-drop-text').textContent = `${file.name} (${formatSize(file.size)})`;
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
  submit.textContent = 'Adding...';
  try {
    const res = await Auth.api('/api/admin/files', { method: 'POST', body });
    $('#add-dialog').close();
    state.highlight = res.file?.path || '';
    toast(`Added ${res.file?.name || addFile.name}`);
    await loadFiles({ quiet: true });
    setIndex(res.index);
  } catch (err) {
    setError('#add-error', err.message);
    submit.disabled = false;
  } finally {
    submit.textContent = 'Add document';
  }
}

/* ==========================================================
   Documents: remove and OCR
   ========================================================== */
function confirmRemove(file) {
  confirmDialog({
    title: `Remove ${file.name}?`,
    body: [
      { text: 'The file leaves the chatbot\'s sources once the index is rebuilt. A backup copy is kept, so it can be restored.' },
      { text: `Folder: ${folderLabel(file.folder)}`, dir: true },
    ],
    label: 'Remove file',
    danger: true,
    action: async () => {
      const res = await Auth.api('/api/admin/files/remove', { method: 'POST', body: { path: file.path } });
      toast(`Removed ${file.name}`);
      await loadFiles({ quiet: true });
      setIndex(res.index);
    },
  });
}

function confirmOcr(file) {
  confirmDialog({
    title: `Read ${file.name} with OCR?`,
    body: [
      { text: 'This turns a scanned PDF into a text file. It can take several minutes, and you can keep using this page meanwhile.' },
      { text: "The text file replaces the PDF as the chatbot's source." },
    ],
    label: 'Start OCR',
    action: async () => {
      const res = await Auth.api('/api/admin/files/ocr', { method: 'POST', body: { path: file.path } });
      setIndex(res.index);
      toast('OCR started');
    },
  });
}

/* ==========================================================
   Accounts
   ========================================================== */
const ROLE_LABEL = { student: 'Student', advisor: 'Advisor', admin: 'Admin' };

async function loadUsers() {
  if (!state.usersLoaded) $('#user-list').innerHTML = '<div class="state">Loading accounts...</div>';
  try {
    state.users = (await Auth.api('/api/admin/users')).users || [];
    state.usersLoaded = true;
    renderUsers();
  } catch (err) {
    if (!state.usersLoaded) {
      $('#user-list').innerHTML = `<div class="state state--error"><strong>Couldn't load accounts</strong>${esc(err.message)}</div>`;
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
  if (!u.active) return '<span class="badge badge--danger">Disabled</span>';
  if (u.must_change_password) return '<span class="badge badge--warn">Temporary password</span>';
  return '<span class="badge badge--primary">Active</span>';
}

function renderUsers() {
  const users = visibleUsers();
  $('#user-count').textContent = `${users.length} of ${state.users.length} accounts`;
  if (!users.length) {
    $('#user-list').innerHTML = state.users.length
      ? '<div class="state"><strong>No accounts match this search</strong>Try a different name or ID, or choose All roles.</div>'
      : '<div class="state"><strong>No accounts yet</strong>Use Add account to create one.</div>';
    return;
  }
  const me = Auth.user?.id;
  $('#user-list').innerHTML = `
    <div class="table-wrap">
      <table class="table">
        <thead>
          <tr><th>Name</th><th>ID</th><th>Role</th><th>Status</th><th>Created</th><th><span class="sr-only">Actions</span></th></tr>
        </thead>
        <tbody>
          ${users.map((u) => `
            <tr data-id="${esc(u.id)}">
              <td class="cell-name" data-label="Name"><span dir="auto">${esc(u.name)}</span>${u.id === me ? '<span class="you">(you)</span>' : ''}</td>
              <td class="cell-mono" data-label="ID" dir="auto">${esc(u.username)}</td>
              <td data-label="Role"><span class="badge">${esc(ROLE_LABEL[u.role] || u.role)}</span></td>
              <td data-label="Status">${statusBadge(u)}</td>
              <td class="cell-muted" data-label="Created">${esc(formatDate(u.created_at))}</td>
              <td class="cell-actions">${u.id === me ? '' : `
                <button type="button" class="act" data-uact="toggle">${u.active ? 'Disable' : 'Enable'}</button>
                <button type="button" class="act" data-uact="reset">Reset password</button>`}
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

async function toggleUser(user, btn) {
  btn.disabled = true;
  try {
    await Auth.api(`/api/admin/users/${encodeURIComponent(user.id)}`, { method: 'PATCH', body: { active: !user.active } });
    toast(`${user.active ? 'Disabled' : 'Enabled'} ${user.name}`);
    await loadUsers();
  } catch (err) {
    toast(err.message, 'error');
    btn.disabled = false;
  }
}

function confirmReset(user) {
  confirmDialog({
    title: `Reset password for ${user.name}?`,
    body: [
      { text: 'They are signed out of their current password and get a new temporary one. You will see it once, on the next screen.' },
    ],
    label: 'Reset password',
    action: async () => {
      const res = await Auth.api(`/api/admin/users/${encodeURIComponent(user.id)}/reset-password`, { method: 'POST' });
      $('#confirm-dialog').close();
      showSecret({ title: 'Temporary password', who: `For ${user.name} (${user.username})`, password: res.temporary_password });
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
  if (!name) return setError('#account-error', 'Enter the person\'s name.');
  if (!/^[A-Za-z0-9._@-]{3,60}$/.test(username)) {
    return setError('#account-error', 'The ID needs 3 to 60 characters: letters, digits, dot, dash, underscore or @.');
  }
  setError('#account-error', '');
  const submit = $('#account-submit');
  submit.disabled = true;
  try {
    const res = await Auth.api('/api/admin/users', { method: 'POST', body: { username, name, role } });
    $('#account-dialog').close();
    showSecret({ title: 'Account created', who: `For ${res.user.name} (${res.user.username})`, password: res.temporary_password });
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
  $('#add-account-btn').addEventListener('click', openAddAccount);
  $('#account-form').addEventListener('submit', submitAccount);
  $('#secret-copy').addEventListener('click', copySecret);

  renderIndexBar();
  loadFiles();
}

Auth.requireRole('admin').then((user) => {
  Auth.fillUser(user);
  init();
});
