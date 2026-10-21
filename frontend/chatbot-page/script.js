/* ==========================================================
   Academic AI - AI Chatbot
   Connected to the Smart Academic System RAG server
   (fastapi_app.py → POST /api/chat)
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
const API_URL = 'http://localhost:8000';   // where fastapi_app.py runs
const STORAGE_KEY = 'academic-ai-chats';
const REQUEST_TIMEOUT = 90000;       // ms before a question is given up on
const MAX_MESSAGE_LENGTH = 2000;     // matches ChatRequest.max_length on the server
const USER_NAME = 'Ahmed Al-Rashid';
const FIRST_NAME = 'Ahmed';
const MOBILE_BREAKPOINT = 900;

// Must match the server's markers in src/citation.py
const SOURCES_HEADING = 'المصادر:';
const NO_ANSWER_PREFIX = 'لم أجد إجابة لسؤالك';

// Used when the server has no NEXT_PUBLIC_STARTER_QUESTIONS configured
const DEFAULT_SUGGESTIONS = [
  { icon: 'withdraw', title: 'الانسحاب من مقرر', desc: 'Course withdrawal procedure', prompt: 'ما هي إجراءات الانسحاب من مقرر؟' },
  { icon: 'transfer', title: 'التحويل إلى كلية الحاسب', desc: 'CCIS transfer conditions', prompt: 'ما هي شروط التحويل إلى كلية علوم الحاسب والمعلومات؟' },
  { icon: 'warning', title: 'الإنذار الأكاديمي', desc: 'Academic probation rules', prompt: 'متى يحصل الطالب على إنذار أكاديمي؟' },
  { icon: 'calendar', title: 'الاعتذار عن الفصل', desc: 'Semester deferral', prompt: 'ما هي شروط الاعتذار عن الدراسة لفصل دراسي؟' },
];
const SUGGESTION_ICONS = ['withdraw', 'transfer', 'warning', 'calendar'];

/* ----------------------------------------------------------
   Icons
   ---------------------------------------------------------- */
const ICONS = {
  logo: '<svg fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.2" viewBox="0 0 24 24"><path d="M22 10v6M2 10l10-5 10 5-10 5z"></path><path d="M6 12v5c3 3 9 3 12 0v-5"></path></svg>',
  chat: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>',
  trash: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"></path></svg>',
  file: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>',
  book: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path></svg>',
  chip: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="2"></rect><rect x="9" y="9" width="6" height="6"></rect><path d="M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3"></path></svg>',
  alert: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>',
  info: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>',
  copy: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>',
  send: '<svg fill="none" stroke="currentColor" stroke-width="2.6" viewBox="0 0 24 24"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>',
  stop: '<svg fill="currentColor" viewBox="0 0 24 24"><rect x="5" y="5" width="14" height="14" rx="2"></rect></svg>',
  arrow: '<svg class="suggestion__arrow" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>',
  withdraw: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="9" y1="15" x2="15" y2="15"></line></svg>',
  transfer: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polyline points="17 1 21 5 17 9"></polyline><path d="M3 11V9a4 4 0 0 1 4-4h14"></path><polyline points="7 23 3 19 7 15"></polyline><path d="M21 13v2a4 4 0 0 1-4 4H3"></path></svg>',
  warning: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>',
  calendar: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg>',
};

/* ----------------------------------------------------------
   Helpers
   ---------------------------------------------------------- */
const $ = (selector) => document.querySelector(selector);

const escapeHtml = (text) =>
  String(text).replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));

const makeId = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;

const formatClock = (timestamp) =>
  new Date(timestamp).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });

const startOfDay = (timestamp) => {
  const d = new Date(timestamp);
  d.setHours(0, 0, 0, 0);
  return d.getTime();
};

function historyGroup(timestamp) {
  const days = Math.round((startOfDay(Date.now()) - startOfDay(timestamp)) / 86400000);
  if (days <= 0) return 'Today';
  if (days === 1) return 'Yesterday';
  if (days <= 7) return 'Previous 7 Days';
  return 'Older';
}

/* Turns e-mail addresses in already-escaped text into mailto links */
const linkifyEmails = (html) =>
  html.replace(/[\w.+-]+@[\w-]+(?:\.[\w-]+)+/g, (email) => `<a href="mailto:${email}">${email}</a>`);

/* ----------------------------------------------------------
   Server API
   ---------------------------------------------------------- */
/* fetch() with a timeout that can also be cancelled by the Stop button */
async function apiFetch(path, options = {}, { timeout = REQUEST_TIMEOUT, signal } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort('timeout'), timeout);
  const onAbort = () => controller.abort('stopped');
  if (signal) signal.addEventListener('abort', onAbort);

  try {
    return await fetch(`${API_URL}${path}`, { ...options, signal: controller.signal });
  } catch (err) {
    if (controller.signal.aborted) {
      const reason = controller.signal.reason === 'stopped' ? 'stopped' : 'timeout';
      throw Object.assign(new Error(reason), { kind: reason });
    }
    throw Object.assign(new Error(err.message), { kind: 'network' });
  } finally {
    clearTimeout(timer);
    if (signal) signal.removeEventListener('abort', onAbort);
  }
}

/* Converts a failed request into a user-facing error message */
function describeError(err, status, detail) {
  if (err && err.kind === 'stopped') return 'You stopped this response.';
  if (err && err.kind === 'timeout') return 'The server took too long to answer. Please try again.';
  if (err && err.kind === 'network') {
    return `Couldn't reach the Academic AI server at ${API_URL}. Make sure the server is running (Start-API.bat).`;
  }
  if (status === 422) return 'The question is empty or too long. Please shorten it and try again.';
  if (detail) return detail;
  return `The server returned an error (HTTP ${status}). Please try again.`;
}

async function askServer(question, signal) {
  let res;
  try {
    res = await apiFetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: question }),
    }, { signal });
  } catch (err) {
    throw Object.assign(new Error(describeError(err)), { kind: err.kind });
  }

  let data = null;
  try {
    data = await res.json();
  } catch {
    /* Non-JSON body (e.g. a proxy error page) */
  }

  if (!res.ok || !data || typeof data.response !== 'string') {
    const detail = data && typeof data.detail === 'string' ? data.detail : '';
    throw Object.assign(new Error(describeError(null, res.status, detail)), { kind: 'http' });
  }
  return data.response;
}

/* Starter questions come from the server's NEXT_PUBLIC_STARTER_QUESTIONS */
let suggestions = DEFAULT_SUGGESTIONS;

async function loadSuggestions() {
  try {
    const res = await apiFetch('/api/starters', {}, { timeout: 8000 });
    const data = await res.json();
    const questions = (data && Array.isArray(data.questions) ? data.questions : [])
      .filter((q) => typeof q === 'string' && q.trim())
      .slice(0, 4);
    if (!questions.length) return;
    suggestions = questions.map((q, i) => ({
      icon: SUGGESTION_ICONS[i % SUGGESTION_ICONS.length],
      title: q,
      desc: 'Suggested question',
      prompt: q,
    }));
    if (!activeChat()) renderMessages();
  } catch {
    /* Keep the built-in suggestions */
  }
}

/* ----------------------------------------------------------
   State & Storage
   ---------------------------------------------------------- */
const state = {
  chats: loadChats(),   // newest first
  activeId: null,       // null = a fresh, empty chat
};

const pending = new Map();   // botMessageId → AbortController

function loadChats() {
  try {
    const chats = JSON.parse(localStorage.getItem(STORAGE_KEY)) || [];
    // Answers still loading when the page closed can't be resumed
    chats.forEach((chat) => chat.messages.forEach((m) => {
      if (m.status === 'typing') {
        m.status = 'error';
        m.errorText = 'This response was interrupted when the page closed. Press Regenerate to ask again.';
      }
    }));
    return chats;
  } catch {
    return [];
  }
}

function saveChats() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state.chats));
  } catch {
    /* Storage unavailable — chats stay in memory only */
  }
}

const activeChat = () => state.chats.find((c) => c.id === state.activeId) || null;
const isBusy = (chat) => Boolean(chat && chat.messages.some((m) => m.status === 'typing'));

/* ----------------------------------------------------------
   Answer parsing (format produced by src/citation.py)
   ---------------------------------------------------------- */
function parseAnswer(text) {
  const index = text.lastIndexOf(`\n${SOURCES_HEADING}`);
  if (index === -1) return { body: text.trim(), sources: [] };

  const body = text.slice(0, index).trim();
  const sources = text
    .slice(index + SOURCES_HEADING.length + 1)
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const match = line.match(/^\[(\d+)\]\s*(.*)$/);
      return match ? { num: match[1], text: match[2] } : { num: '•', text: line };
    });
  return { body, sources };
}

function renderAnswerBody(body, msgId) {
  return body
    .split(/\n{2,}/)
    .map((para) => {
      const html = linkifyEmails(escapeHtml(para))
        .replace(/\[(\d+)\]/g, (_, n) =>
          `<button type="button" class="cite" data-cite="${n}" data-msg="${msgId}" title="Show source ${n}">${n}</button>`);
      return `<p dir="auto">${html}</p>`;
    })
    .join('');
}

/* ----------------------------------------------------------
   Rendering
   ---------------------------------------------------------- */
function renderHistory() {
  if (!state.chats.length) {
    $('#history').innerHTML = '<p class="history__empty">No conversations yet. Start a new chat below.</p>';
    return;
  }

  const groups = new Map();
  state.chats.forEach((chat) => {
    const label = historyGroup(chat.updatedAt);
    if (!groups.has(label)) groups.set(label, []);
    groups.get(label).push(chat);
  });

  $('#history').innerHTML = [...groups].map(([label, chats]) => `
    <div class="history__group">
      <span class="history__label">${label}</span>
      ${chats.map((chat) => `
        <div class="history-item${chat.id === state.activeId ? ' is-active' : ''}" role="button" tabindex="0" data-chat="${chat.id}"
          ${chat.id === state.activeId ? 'aria-current="page"' : ''}>
          ${ICONS.chat}
          <span class="history-item__title" dir="auto">${escapeHtml(chat.title)}</span>
          <button type="button" class="history-item__delete" data-delete="${chat.id}" title="Delete chat" aria-label="Delete chat">${ICONS.trash}</button>
        </div>`).join('')}
    </div>`).join('');
}

function renderWelcome() {
  return `
    <div class="welcome">
      <div>
        <div class="logo-mark welcome__emblem" style="margin: 0 auto 20px">${ICONS.logo}</div>
        <h1 class="welcome__title">How can I help you today, ${FIRST_NAME}?</h1>
        <p class="welcome__subtitle">Ask about IMSIU's academic regulations — every answer comes from the official documents, with the source, page and article.</p>
      </div>
      <div class="suggestions">
        <span class="suggestions__label">Suggested prompts for discussion</span>
        <div class="suggestions__grid">
          ${suggestions.map((s, i) => `
            <button type="button" class="suggestion" data-suggestion="${i}">
              <span class="suggestion__top">
                <span class="suggestion__icon">${ICONS[s.icon]}</span>
                ${ICONS.arrow}
              </span>
              <span>
                <span class="suggestion__title" dir="auto">${escapeHtml(s.title)}</span>
                <span class="suggestion__desc">${escapeHtml(s.desc)}</span>
              </span>
            </button>`).join('')}
        </div>
      </div>
    </div>`;
}

function renderUserMessage(msg) {
  // Older chats may still carry an attachment name from the demo version
  const file = msg.attachment
    ? `<span class="msg-file">${ICONS.file}${escapeHtml(msg.attachment.name)}</span>`
    : '';
  const text = msg.text ? `<div dir="auto">${escapeHtml(msg.text)}</div>` : '';
  return `
    <div class="msg-user">
      <div class="msg-meta"><span>${USER_NAME}</span><time>${formatClock(msg.time)}</time></div>
      <div class="msg-user__bubble">${file}${text}</div>
    </div>`;
}

function renderBotBody(msg) {
  if (msg.status === 'typing') {
    return `
      <div class="typing" aria-live="polite">
        <span class="typing__dots"><span></span><span></span><span></span></span>
        <span>Searching the official regulations…</span>
      </div>`;
  }

  if (msg.status === 'error') {
    return `
      <div class="msg-error" role="alert">
        ${ICONS.alert}
        <div>
          <div class="msg-error__title">Error</div>
          <p class="msg-error__text">${escapeHtml(msg.errorText || 'Something went wrong while generating a response. Please try again.')}</p>
        </div>
      </div>`;
  }

  // The server's hand-off when the documents don't cover the question
  if (msg.text.startsWith(NO_ANSWER_PREFIX)) {
    return `
      <div class="msg-notice">
        ${ICONS.info}
        <div class="answer">${renderAnswerBody(msg.text, msg.id)}</div>
      </div>`;
  }

  const { body, sources } = parseAnswer(msg.text);
  const sourcesHtml = sources.length
    ? `<div class="sources">
         <span class="sources__title">${ICONS.book}Sources · المصادر</span>
         <ol class="sources__list">
           ${sources.map((s) => `
             <li class="source" data-source="${escapeHtml(s.num)}">
               <span class="source__num">${escapeHtml(s.num)}</span>
               <span class="source__parts">
                 ${s.text.split(' — ').map((part, i) =>
                   `<span class="source__part${i === 0 ? ' source__part--file' : ''}" dir="auto">${escapeHtml(part)}</span>`).join('')}
               </span>
             </li>`).join('')}
         </ol>
       </div>`
    : '';

  return `<div class="answer">${renderAnswerBody(body, msg.id)}</div>${sourcesHtml}`;
}

function renderBotActions(msg) {
  if (msg.status !== 'done') return '';
  return `
    <div class="msg-actions">
      <div class="msg-actions__group">
        <button type="button" class="action-btn" data-action="copy" data-id="${msg.id}" title="Copy response">${ICONS.copy}Copy</button>
      </div>
    </div>`;
}

function renderBotMessage(msg) {
  const typing = msg.status === 'typing';
  return `
    <div class="msg-bot" data-msg-id="${msg.id}">
      <div class="msg-bot__head">
        <div class="msg-bot__identity">
          <span class="logo-mark msg-bot__logo">${ICONS.logo}</span>
          <span class="msg-bot__name">Academic AI</span>
          <span class="msg-bot__mode">${typing ? 'Thinking…' : 'Official Regulations'}</span>
        </div>
        ${!typing && msg.thinking ? `<span class="msg-bot__time">${ICONS.chip}${(msg.thinking / 1000).toFixed(2)}s response time</span>` : ''}
      </div>
      <div class="msg-bot__body">${renderBotBody(msg)}${renderBotActions(msg)}</div>
    </div>`;
}

function renderMessages() {
  const chat = activeChat();
  $('#messages').innerHTML = chat && chat.messages.length
    ? chat.messages.map((m) => (m.role === 'user' ? renderUserMessage(m) : renderBotMessage(m))).join('')
    : renderWelcome();
  scrollToBottom();
}

function renderComposer() {
  const busy = isBusy(activeChat());
  const length = $('#prompt').value.length;
  const hasText = $('#prompt').value.trim().length > 0;
  const sendBtn = $('#send-btn');

  // While an answer loads, the send button turns into Stop
  sendBtn.classList.toggle('is-stop', busy);
  sendBtn.innerHTML = busy ? ICONS.stop : ICONS.send;
  sendBtn.title = busy ? 'Stop response' : 'Send message';
  sendBtn.setAttribute('aria-label', sendBtn.title);
  sendBtn.disabled = !busy && !hasText;

  const count = $('#char-count');
  count.textContent = `${length} / ${MAX_MESSAGE_LENGTH}`;
  count.classList.toggle('is-near', length > MAX_MESSAGE_LENGTH * 0.9);
}

function render() {
  renderHistory();
  renderMessages();
  renderComposer();
}

function scrollToBottom() {
  const scroller = $('#chat-scroll');
  scroller.scrollTop = scroller.scrollHeight;
}

function autoSizePrompt() {
  const input = $('#prompt');
  input.style.height = 'auto';
  input.style.height = `${Math.min(input.scrollHeight, 200)}px`;
}

/* ----------------------------------------------------------
   Chat Actions
   ---------------------------------------------------------- */
async function requestAnswer(chatId, botMessageId, question) {
  const controller = new AbortController();
  pending.set(botMessageId, controller);
  const started = performance.now();

  let result;
  try {
    result = { status: 'done', text: await askServer(question, controller.signal) };
  } catch (err) {
    result = { status: 'error', errorText: err.message };
  }
  pending.delete(botMessageId);

  // The chat may have been deleted while waiting
  const chat = state.chats.find((c) => c.id === chatId);
  const msg = chat && chat.messages.find((m) => m.id === botMessageId);
  if (!msg) return;

  Object.assign(msg, { text: '', errorText: '' }, result, { thinking: performance.now() - started });
  chat.updatedAt = Date.now();
  saveChats();

  if (state.activeId === chatId) {
    renderMessages();
    renderComposer();
  }
  renderHistory();
}

function sendMessage(text) {
  const content = text.trim().slice(0, MAX_MESSAGE_LENGTH);
  if (!content) return;

  let chat = activeChat();
  if (isBusy(chat)) return;

  // First message starts a new conversation in the history
  if (!chat) {
    chat = {
      id: makeId(),
      title: content.length > 48 ? `${content.slice(0, 48)}…` : content,
      createdAt: Date.now(),
      updatedAt: Date.now(),
      messages: [],
    };
    state.chats.unshift(chat);
    state.activeId = chat.id;
  }

  const now = Date.now();
  const user = { id: makeId(), role: 'user', text: content, time: now };
  const bot = { id: makeId(), role: 'bot', status: 'typing', time: now };
  chat.messages.push(user, bot);
  chat.updatedAt = now;

  // Move the chat to the top of the history
  state.chats = [chat, ...state.chats.filter((c) => c.id !== chat.id)];

  $('#prompt').value = '';
  autoSizePrompt();

  saveChats();
  render();
  requestAnswer(chat.id, bot.id, content);
}

function stopActiveResponse() {
  const chat = activeChat();
  if (!chat) return;
  chat.messages
    .filter((m) => m.status === 'typing')
    .forEach((m) => pending.get(m.id)?.abort());
}

function startNewChat() {
  state.activeId = null;
  $('#prompt').value = '';
  autoSizePrompt();
  render();
  closeSidebarOnMobile();
  $('#prompt').focus();
}

function openChat(id) {
  state.activeId = id;
  render();
  closeSidebarOnMobile();
}

function deleteChat(id) {
  const chat = state.chats.find((c) => c.id === id);
  if (!chat) return;
  chat.messages.forEach((m) => pending.get(m.id)?.abort());
  state.chats = state.chats.filter((c) => c.id !== id);
  if (state.activeId === id) state.activeId = null;
  saveChats();
  render();
  showToast('Chat deleted');
}

function clearAllChats() {
  if (!state.chats.length) {
    showToast('There are no chats to clear');
    return;
  }
  if (!window.confirm('Delete all conversations? This cannot be undone.')) return;
  pending.forEach((controller) => controller.abort());
  state.chats = [];
  state.activeId = null;
  saveChats();
  render();
  showToast('All chats cleared');
}

function handleMessageAction(action, id) {
  const chat = activeChat();
  const msg = chat && chat.messages.find((m) => m.id === id);
  if (!msg) return;

  if (action === 'copy') copyText(msg.text, 'Response copied');
}

/* Clicking a [n] marker highlights that source */
function flashSource(msgId, num) {
  const item = document.querySelector(`[data-msg-id="${msgId}"] [data-source="${num}"]`);
  if (!item) return;
  item.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  item.classList.add('is-flash');
  setTimeout(() => item.classList.remove('is-flash'), 700);
}

/* ----------------------------------------------------------
   Settings (empty for now — add future options to #settings-body)
   ---------------------------------------------------------- */
function openSettings() {
  $('#settings-modal').hidden = false;
}

function closeSettings() {
  $('#settings-modal').hidden = true;
}

/* ----------------------------------------------------------
   Sidebar
   ---------------------------------------------------------- */
const isMobile = () => window.innerWidth < MOBILE_BREAKPOINT;

function setSidebar(open) {
  document.body.classList.toggle('sidebar-collapsed', !open);
}

function closeSidebarOnMobile() {
  if (isMobile()) setSidebar(false);
}

function toggleProfileMenu(force) {
  const menu = $('#profile-menu');
  const open = typeof force === 'boolean' ? force : menu.hidden;
  menu.hidden = !open;
  $('#profile-menu-btn').setAttribute('aria-expanded', String(open));
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
    showToast(ok ? message : 'Could not copy');
  };

  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(() => showToast(message), fallback);
  } else {
    fallback();
  }
}

/* ----------------------------------------------------------
   Events
   ---------------------------------------------------------- */
function bindEvents() {
  // Header & strip
  document.querySelectorAll('[data-sign-out]').forEach((btn) => btn.addEventListener('click', signOut));
  $('#notifications-btn').addEventListener('click', () => showToast('No new notifications'));
  $('#settings-btn').addEventListener('click', openSettings);

  // Sidebar
  $('#collapse-btn').addEventListener('click', () => setSidebar(false));
  $('#open-sidebar-btn').addEventListener('click', () => setSidebar(true));
  $('#sidebar-backdrop').addEventListener('click', () => setSidebar(false));
  $('#new-chat-btn').addEventListener('click', startNewChat);

  $('#history').addEventListener('click', (e) => {
    const del = e.target.closest('[data-delete]');
    if (del) {
      e.stopPropagation();
      deleteChat(del.dataset.delete);
      return;
    }
    const item = e.target.closest('[data-chat]');
    if (item) openChat(item.dataset.chat);
  });
  $('#history').addEventListener('keydown', (e) => {
    const item = e.target.closest('[data-chat]');
    if (item && (e.key === 'Enter' || e.key === ' ')) {
      e.preventDefault();
      openChat(item.dataset.chat);
    }
  });

  // Profile menu
  $('#profile-menu-btn').addEventListener('click', (e) => {
    e.stopPropagation();
    toggleProfileMenu();
  });
  document.addEventListener('click', (e) => {
    if (!e.target.closest('#profile-menu')) toggleProfileMenu(false);
  });
  $('#clear-chats-btn').addEventListener('click', () => {
    toggleProfileMenu(false);
    clearAllChats();
  });

  // Messages (suggestions, citations, actions)
  $('#messages').addEventListener('click', (e) => {
    const suggestion = e.target.closest('[data-suggestion]');
    if (suggestion) {
      sendMessage(suggestions[Number(suggestion.dataset.suggestion)].prompt);
      return;
    }
    const cite = e.target.closest('[data-cite]');
    if (cite) {
      flashSource(cite.dataset.msg, cite.dataset.cite);
      return;
    }
    const action = e.target.closest('[data-action]');
    if (action) handleMessageAction(action.dataset.action, action.dataset.id);
  });

  // Composer
  const prompt = $('#prompt');
  $('#composer').addEventListener('submit', (e) => {
    e.preventDefault();
    if (isBusy(activeChat())) stopActiveResponse();
    else sendMessage(prompt.value);
  });
  prompt.addEventListener('input', () => {
    autoSizePrompt();
    renderComposer();
  });
  prompt.addEventListener('keydown', (e) => {
    // Enter sends, Shift+Enter adds a new line
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      if (!isBusy(activeChat()) && prompt.value.trim()) sendMessage(prompt.value);
    }
  });

  // The RAG server answers from the official regulations only — it has no upload endpoint
  $('#attach-btn').addEventListener('click', () =>
    showToast("Attachments aren't supported yet — the advisor answers from the official regulations. Type your question instead.")
  );

  // Settings (empty placeholder)
  document.querySelectorAll('[data-close-settings]').forEach((el) => el.addEventListener('click', closeSettings));

  // Keyboard: Escape closes dialogs, menus and the mobile sidebar
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    if (!$('#settings-modal').hidden) {
      closeSettings();
      return;
    }
    toggleProfileMenu(false);
    closeSidebarOnMobile();
  });
}

/* ----------------------------------------------------------
   Init
   ---------------------------------------------------------- */
document.addEventListener('DOMContentLoaded', () => {
  if (isMobile()) setSidebar(false);
  bindEvents();
  render();
  loadSuggestions();
  $('#prompt').focus();
});
