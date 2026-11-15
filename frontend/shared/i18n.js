/* ==========================================================
   Academic AI - Interface language (Arabic / English)
   Loaded first in every page's <head>: it sets <html lang dir>
   before the page paints, so a page never flashes the other
   language. Arabic is the default.

   Markup:  data-i18n="key"              -> textContent
            data-i18n-html="key"         -> innerHTML (team-written strings only)
            data-i18n-placeholder="key"  -> placeholder
            data-i18n-title="key"        -> title
            data-i18n-aria-label="key"   -> aria-label
   Script:  I18n.t(key, vars), I18n.onChange(fn), I18n.date(iso)...
   Content written by people or taken from documents (chat
   answers, course names, names, ticket messages) is never
   translated. Digits stay Western (0-9) in both languages.
   ========================================================== */

const I18n = (() => {
  const KEY = 'sas_lang';
  const DEFAULT = 'ar';
  const tables = { en: {}, ar: {} };
  const listeners = [];

  function stored() {
    try {
      const v = localStorage.getItem(KEY);
      return v === 'en' || v === 'ar' ? v : null;
    } catch {
      return null; // storage blocked: default every visit
    }
  }

  let lang = stored() || DEFAULT;
  const root = document.documentElement;

  function setDocument() {
    root.lang = lang;
    root.dir = lang === 'ar' ? 'rtl' : 'ltr';
  }
  setDocument();
  // Hides [data-i18n] text until the first apply(), so no English flashes.
  root.classList.add('i18n-pending');

  /* ---------- theme (dark by default, light on request) ---------- */
  const THEME_KEY = 'sas_theme';
  const themeListeners = [];

  function storedTheme() {
    try {
      const v = localStorage.getItem(THEME_KEY);
      return v === 'light' || v === 'dark' ? v : null;
    } catch {
      return null;
    }
  }

  let theme = storedTheme() || 'dark';

  function setThemeDocument() {
    root.dataset.theme = theme;
    root.style.colorScheme = theme; // native scrollbars, selects and date inputs follow
  }
  setThemeDocument();

  function setTheme(next) {
    if (next !== 'light' && next !== 'dark') return;
    theme = next;
    try {
      localStorage.setItem(THEME_KEY, next);
    } catch {
      // Not remembered on this browser; still switches now
    }
    setThemeDocument();
    renderThemeButton();
    for (const fn of themeListeners) {
      try { fn(theme); } catch (err) { console.error(err); }
    }
  }

  function onThemeChange(fn) {
    themeListeners.push(fn);
  }

  const SUN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>';
  const MOON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';

  /* The button shows the theme it switches to: a sun in dark mode, a moon in light mode. */
  function renderThemeButton() {
    let btn = document.querySelector('.theme-toggle');
    if (!btn) {
      const anchor = document.querySelector('.lang-switch');
      if (!anchor) return;
      btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'theme-toggle';
      btn.addEventListener('click', () => setTheme(theme === 'dark' ? 'light' : 'dark'));
      anchor.after(btn);
    }
    const label = t(theme === 'dark' ? 'common.themeLight' : 'common.themeDark');
    btn.innerHTML = theme === 'dark' ? SUN : MOON;
    btn.title = label;
    btn.setAttribute('aria-label', label);
    btn.setAttribute('aria-pressed', String(theme === 'light'));
  }

  function add(more) {
    for (const l of ['en', 'ar']) Object.assign(tables[l], (more && more[l]) || {});
  }

  function fill(text, vars) {
    if (!vars) return text;
    return text.replace(/\{(\w+)\}/g, (m, name) => (vars[name] != null ? String(vars[name]) : m));
  }

  function t(key, vars) {
    const text = tables[lang][key] ?? tables.en[key] ?? key;
    return fill(text, vars);
  }

  function apply(scope = document) {
    scope.querySelectorAll('[data-i18n]').forEach((el) => {
      el.textContent = t(el.dataset.i18n);
    });
    scope.querySelectorAll('[data-i18n-html]').forEach((el) => {
      el.innerHTML = t(el.dataset.i18nHtml);
    });
    for (const attr of ['placeholder', 'title', 'aria-label']) {
      const data = `data-i18n-${attr}`;
      scope.querySelectorAll(`[${data}]`).forEach((el) => el.setAttribute(attr, t(el.getAttribute(data))));
    }
    renderSwitch();
    renderThemeButton();
  }

  function set(next) {
    if (next !== 'ar' && next !== 'en') return;
    lang = next;
    try {
      localStorage.setItem(KEY, next);
    } catch {
      // Not remembered on this browser; still switches now
    }
    setDocument();
    apply();
    for (const fn of listeners) {
      try { fn(lang); } catch (err) { console.error(err); }
    }
  }

  function onChange(fn) {
    listeners.push(fn);
  }

  /* ---------- dates (Gregorian, Western digits) ---------- */
  const locale = () => (lang === 'ar' ? 'ar-u-ca-gregory-nu-latn' : 'en-GB');

  function toDate(value) {
    const d = value instanceof Date ? value : new Date(value);
    return Number.isNaN(d.getTime()) ? null : d;
  }

  function date(value, opts = { day: 'numeric', month: 'short', year: 'numeric' }) {
    const d = toDate(value);
    return d ? new Intl.DateTimeFormat(locale(), opts).format(d) : '';
  }

  function time(value) {
    return date(value, { hour: 'numeric', minute: '2-digit' });
  }

  function dateTime(value) {
    return date(value, { day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit' });
  }

  function relative(value) {
    const d = toDate(value);
    if (!d) return '';
    const seconds = Math.round((d.getTime() - Date.now()) / 1000);
    const abs = Math.abs(seconds);
    if (abs < 45) return t('common.justNow');
    const fmt = new Intl.RelativeTimeFormat(locale(), { numeric: 'auto' });
    if (abs < 3600) return fmt.format(Math.round(seconds / 60), 'minute');
    if (abs < 86400) return fmt.format(Math.round(seconds / 3600), 'hour');
    if (abs < 86400 * 7) return fmt.format(Math.round(seconds / 86400), 'day');
    return date(d);
  }

  /* ---------- server messages ----------
     The server answers in English; known messages are shown in
     Arabic here. Patterns hold the parts that vary. */
  const SERVER_PATTERNS = [
    [/^You already have (\d+) open tickets\. Please wait for advising to close one first\.$/, 'server.openTickets', ['n']],
    [/^File is too large\. The maximum size is (\d+)MB\.$/, 'server.fileTooLarge', ['n']],
    [/^Unknown course code\(s\): (.+)$/, 'server.unknownCourses', ['codes']],
    [/^Course (.+) has no section (.+)$/, 'server.noSection', ['code', 'section']],
    [/^Server error \((\d+)\)$/, 'server.error', ['n']],
  ];

  function server(message) {
    if (!message || lang === 'en') return message;
    const exact = tables.ar[`server:${message}`];
    if (exact) return exact;
    for (const [re, key, names] of SERVER_PATTERNS) {
      const m = message.match(re);
      if (m) return t(key, Object.fromEntries(names.map((n, i) => [n, m[i + 1]])));
    }
    return message;
  }

  /* ---------- the EN | ع switch ---------- */
  function renderSwitch() {
    let box = document.querySelector('.lang-switch');
    if (!box) {
      const slot = document.querySelector('.header__right') || document.querySelector('[data-lang-slot]');
      if (!slot) return;
      box = document.createElement('div');
      box.className = 'lang-switch';
      box.setAttribute('role', 'group');
      box.innerHTML = `
        <button type="button" class="lang-switch__btn" data-lang="en" lang="en">EN</button>
        <button type="button" class="lang-switch__btn" data-lang="ar" lang="ar">ع</button>`;
      box.addEventListener('click', (e) => {
        const btn = e.target.closest('[data-lang]');
        if (btn && btn.dataset.lang !== lang) set(btn.dataset.lang);
      });
      slot.prepend(box);
    }
    box.setAttribute('aria-label', t('common.language'));
    box.querySelectorAll('[data-lang]').forEach((btn) => {
      const on = btn.dataset.lang === lang;
      btn.classList.toggle('is-active', on);
      btn.setAttribute('aria-pressed', String(on));
      btn.title = btn.dataset.lang === 'ar' ? 'العربية' : 'English';
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    apply();
    root.classList.remove('i18n-pending');
  });

  /* ---------- shared strings ---------- */
  add({
    en: {
      'common.language': 'Interface language',
      'common.themeLight': 'Switch to light mode',
      'common.themeDark': 'Switch to dark mode',
      'common.justNow': 'Just now',
      'common.signOut': 'Sign out',
      'common.loading': 'Loading',
      'common.retry': 'Try again',
      'common.back': 'Back',
      'common.close': 'Close',
      'common.cancel': 'Cancel',
      'common.save': 'Save',
      'common.search': 'Search',
      'common.notProvided': 'Not provided',
      'common.unknown': 'Unknown',
      'common.serverDown': "Couldn't reach the Academic AI server at {url}. Make sure the server is running (Start-API.bat).",
      'status.new': 'New',
      'status.in_progress': 'In progress',
      'status.closed': 'Resolved',
      'role.student': 'Student',
      'role.advisor': 'Advisor',
      'role.admin': 'Admin',
      'term.fall': 'Fall {year}',
      'term.spring': 'Spring {year}',
      'term.summer': 'Summer {year}',
      'term.online': '{term} Online',
      'server.openTickets': 'You already have {n} open tickets. Please wait for advising to close one first.',
      'server.fileTooLarge': 'File is too large. The maximum size is {n}MB.',
      'server.unknownCourses': 'Unknown course code(s): {codes}',
      'server.noSection': 'Course {code} has no section {section}',
      'server.error': 'Server error ({n})',
    },
    ar: {
      'common.language': 'لغة الواجهة',
      'common.themeLight': 'التبديل إلى الوضع الفاتح',
      'common.themeDark': 'التبديل إلى الوضع الداكن',
      'common.justNow': 'الآن',
      'common.signOut': 'تسجيل الخروج',
      'common.loading': 'جارٍ التحميل',
      'common.retry': 'حاول مرة أخرى',
      'common.back': 'رجوع',
      'common.close': 'إغلاق',
      'common.cancel': 'إلغاء',
      'common.save': 'حفظ',
      'common.search': 'بحث',
      'common.notProvided': 'غير مُدخل',
      'common.unknown': 'غير معروف',
      'common.serverDown': 'تعذّر الوصول إلى خادم Academic AI على {url}. تأكد أن الخادم يعمل (Start-API.bat).',
      'status.new': 'جديدة',
      'status.in_progress': 'قيد المعالجة',
      'status.closed': 'تمت المعالجة',
      'role.student': 'طالب',
      'role.advisor': 'مرشد',
      'role.admin': 'مدير',
      'term.fall': 'الفصل الأول {year}',
      'term.spring': 'الفصل الثاني {year}',
      'term.summer': 'الفصل الصيفي {year}',
      'term.online': '{term} · متصل',
      'server.openTickets': 'لديك {n} تذاكر مفتوحة. انتظر حتى يغلق الإرشاد إحداها قبل فتح تذكرة جديدة.',
      'server.fileTooLarge': 'الملف كبير جدًا. الحد الأقصى {n} ميغابايت.',
      'server.unknownCourses': 'رموز مقررات غير معروفة: {codes}',
      'server.noSection': 'المقرر {code} ليس له الشعبة {section}',
      'server.error': 'خطأ في الخادم ({n})',
      // Exact server messages (key = "server:" + the English text)
      'server:A file with this name is already in this folder. Use Replace on that file instead.': 'يوجد ملف بهذا الاسم في المجلد. استخدم «استبدال» على ذلك الملف بدلًا من ذلك.',
      'server:A text file with this name already exists beside the PDF.': 'يوجد ملف نصي بهذا الاسم بجانب ملف PDF.',
      'server:Account not found.': 'الحساب غير موجود.',
      "server:Another file in this folder already has the new file's name.": 'يوجد ملف آخر في هذا المجلد بنفس اسم الملف الجديد.',
      'server:Another job is still running. Wait for it to finish.': 'هناك مهمة أخرى قيد التشغيل. انتظر حتى تنتهي.',
      'server:Change your own password from the account menu instead.': 'غيّر كلمة مرورك من قائمة الحساب.',
      'server:Change your temporary password first.': 'غيّر كلمة المرور المؤقتة أولًا.',
      'server:Choose a password different from the current one.': 'اختر كلمة مرور مختلفة عن الحالية.',
      'server:Could not read this PDF. Upload the text-based transcript exported from the university system.': 'تعذّرت قراءة ملف PDF هذا. ارفع السجل الأكاديمي النصي المُصدَّر من نظام الجامعة.',
      "server:Couldn't open the ticket right now. Please try again.": 'تعذّر فتح التذكرة الآن. حاول مرة أخرى.',
      'server:File not found.': 'الملف غير موجود.',
      'server:Folder not found.': 'المجلد غير موجود.',
      'server:Invalid chat id.': 'معرّف المحادثة غير صالح.',
      'server:Message is empty.': 'الرسالة فارغة.',
      'server:Only PDF files can be read with OCR.': 'لا يمكن قراءة غير ملفات PDF بالتعرّف الضوئي.',
      'server:Only PDF, DOCX, TXT and MD files can be added to the documents.': 'يمكن إضافة ملفات PDF وDOCX وTXT وMD فقط إلى المستندات.',
      'server:Please sign in.': 'سجّل الدخول من فضلك.',
      'server:Please upload the transcript as a PDF file.': 'ارفع السجل الأكاديمي بصيغة PDF.',
      'server:Student not found.': 'الطالب غير موجود.',
      'server:The advising service could not generate an answer right now. Please try again.': 'تعذّر على خدمة الإرشاد إنشاء إجابة الآن. حاول مرة أخرى.',
      'server:The current password is wrong.': 'كلمة المرور الحالية غير صحيحة.',
      'server:This ID is already used by another account.': 'هذا الرقم مستخدم في حساب آخر.',
      'server:This Word file could not be read.': 'تعذّرت قراءة ملف Word هذا.',
      'server:This account is disabled. Contact the system administrator.': 'هذا الحساب موقوف. تواصل مع مدير النظام.',
      'server:This file is empty.': 'هذا الملف فارغ.',
      "server:This file name can't be used.": 'لا يمكن استخدام اسم الملف هذا.',
      "server:This file type can't be opened here.": 'لا يمكن فتح هذا النوع من الملفات هنا.',
      "server:This file type can't be previewed.": 'لا يمكن معاينة هذا النوع من الملفات.',
      'server:This path is outside the documents folder.': 'هذا المسار خارج مجلد المستندات.',
      'server:This ticket has reached its message limit. Please open a new one.': 'وصلت هذه التذكرة إلى الحد الأقصى للرسائل. افتح تذكرة جديدة.',
      'server:This ticket is closed, so no more messages can be added.': 'تمت معالجة هذه التذكرة، فلا يمكن إضافة رسائل جديدة.',
      'server:Ticket not found.': 'التذكرة غير موجودة.',
      'server:Too many failed sign-in attempts. Try again in a few minutes.': 'محاولات دخول فاشلة كثيرة. حاول بعد بضع دقائق.',
      'server:Too many questions in a short time. Please wait a minute and try again.': 'أسئلة كثيرة في وقت قصير. انتظر دقيقة ثم حاول مرة أخرى.',
      'server:Unknown ticket status.': 'حالة تذكرة غير معروفة.',
      'server:Write a message first.': 'اكتب رسالة أولًا.',
      'server:Wrong ID or password.': 'الرقم أو كلمة المرور غير صحيحة.',
      "server:You can't change your own role.": 'لا يمكنك تغيير دورك بنفسك.',
      "server:You can't disable your own account.": 'لا يمكنك إيقاف حسابك بنفسك.',
      "server:Your account can't open this.": 'حسابك لا يملك صلاحية فتح هذه الصفحة.',
      'server:The profile is too large to save.': 'الملف الشخصي أكبر من أن يُحفظ.',
      'server:This chat is too long to save.': 'هذه المحادثة أطول من أن تُحفظ.',
    },
  });

  return {
    get lang() { return lang; },
    get dir() { return lang === 'ar' ? 'rtl' : 'ltr'; },
    get theme() { return theme; },
    add, t, set, onChange, apply, date, time, dateTime, relative, server, setTheme, onThemeChange,
  };
})();
