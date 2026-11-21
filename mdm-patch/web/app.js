// Mister Download Manager's remote control page. Served by MDM itself; no other site is
// reached. Every text shown goes through T() (the app's translations, /api/texts); a text the
// catalog does not have is shown in English, as written here.
'use strict';

const $ = (id) => document.getElementById(id);
let TX = {};
let LANG = 'en';
let token = null;
let filter = 'all';
let data = null;
let timer = null;
let failures = 0;
let chosenFile = null;
let authSet = true;
let limitTarget = null;
const rows = new Map();
let ticker = null;
let refreshing = false;
const TITLE = 'Mister Download Manager';

// The tab's title is the live speed while something downloads, the name when nothing does.
function setTitle(speedText) { document.title = speedText || TITLE; }

try { token = localStorage.getItem('mdm-token'); } catch (e) { token = null; }

function T(s) { return TX[s] || s; }
function F(s, args) { return T(s).replace(/\{(\w+)\}/g, (m, k) => (k in args ? String(args[k]) : m)); }
function unit(tpl, n) { return (TX['unit:' + tpl] || tpl).replace('{n}', n); }
function num(n, digits) {
  try {
    return new Intl.NumberFormat(LANG, { maximumFractionDigits: digits, minimumFractionDigits: digits, numberingSystem: 'latn' }).format(n);
  } catch (e) { return n.toFixed(digits); }
}
function size(n) {
  if (n == null) return '?';
  if (n < 1048576) return unit('{n} KB', num(n / 1024, n < 10240 ? 1 : 0));
  if (n < 1073741824) return unit('{n} MB', num(n / 1048576, 1));
  return unit('{n} GB', num(n / 1073741824, 2));
}
function speed(n) {
  if (n < 1048576) return unit('{n} KB/sec', num(n / 1024, 1));
  return unit('{n} MB/sec', num(n / 1048576, 1));
}
function limitLabel(kb) {
  if (!kb) return T('No limit');
  if (kb < 1024) return unit('{n} KB/sec', num(kb, 0));
  return unit('{n} MB/sec', num(kb / 1024, kb % 1024 ? 1 : 0));
}
// Time left: 22h 15m, 3m 20s, 45s.
function duration(s) {
  s = Math.max(0, Math.round(s));
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d) return d + 'd ' + h + 'h';
  if (h) return h + 'h ' + m + 'm';
  if (m) return m + 'm ' + (s % 60) + 's';
  return s + 's';
}

async function loadTexts() {
  const langs = (navigator.languages && navigator.languages.length ? navigator.languages : [navigator.language || 'en']).join(',');
  try {
    const r = await fetch('api/texts?lang=' + encodeURIComponent(langs), { cache: 'no-store' });
    const j = await r.json();
    TX = j.texts || {};
    LANG = j.lang || 'en';
    document.documentElement.lang = LANG;
    document.documentElement.dir = j.rtl ? 'rtl' : 'ltr';
  } catch (e) { /* English, as written */ }
  for (const el of document.querySelectorAll('[data-t]')) el.textContent = T(el.dataset.t);
  for (const el of document.querySelectorAll('[data-ta]')) { el.setAttribute('aria-label', T(el.dataset.ta)); el.title = T(el.dataset.ta); }
  for (const el of document.querySelectorAll('[data-tp]')) el.placeholder = T(el.dataset.tp);
}

class ApiError extends Error {
  constructor(code, body) { super(code); this.code = code; this.body = body; }
}

async function api(path, opts) {
  opts = opts || {};
  const headers = Object.assign({}, opts.headers || {});
  if (token) headers.Authorization = 'Bearer ' + token;
  let body = opts.body;
  if (opts.json !== undefined) { headers['Content-Type'] = 'application/json'; body = JSON.stringify(opts.json); }
  const r = await fetch('api/' + path, { method: body !== undefined || opts.post ? 'POST' : 'GET', headers, body, cache: 'no-store', credentials: 'omit' });
  let j = null;
  try { j = await r.json(); } catch (e) { j = null; }
  if (r.status === 401) { signedOut(); throw new ApiError('not-paired', j); }
  if (!r.ok || (j && j.error)) throw new ApiError((j && j.code) || String(r.status), j);
  return j;
}

let toastTimer = null;
function toast(text, bad) {
  const t = $('toast');
  t.textContent = text;
  t.classList.toggle('bad', !!bad);
  t.hidden = false;
  // In the top layer, so it shows above an open sheet too (where the browser has popovers).
  try { if (t.showPopover && !t.matches(':popover-open')) t.showPopover(); } catch (e) { /* plain */ }
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    t.hidden = true;
    try { if (t.hidePopover && t.matches(':popover-open')) t.hidePopover(); } catch (e) { /* plain */ }
  }, bad ? 6000 : 3000);
}

// ---- the password ------------------------------------------------------------------------

function guessName() {
  const ua = navigator.userAgent;
  for (const [re, name] of [[/iPhone/, 'iPhone'], [/iPad/, 'iPad'], [/Android/, 'Android'], [/Windows/, 'Windows'], [/Mac OS X|Macintosh/, 'Mac'], [/CrOS/, 'ChromeOS'], [/Linux/, 'Linux']]) {
    if (re.test(ua)) return name;
  }
  return '';
}

// The first visit asks for a new password; every later device asks for it.
async function showAuth() {
  stopPolling();
  $('main').hidden = true;
  $('menu').hidden = true;
  $('add-open').hidden = true;
  $('summary').textContent = '';
  setTitle(null);
  $('auth-error').textContent = '';
  $('pair').hidden = false;
  try {
    authSet = !!(await api('auth')).set;
  } catch (e) {
    authSet = true;
    $('auth-error').textContent = T('MDM does not answer. Check that it is running and on the same network.');
  }
  $('auth-title').textContent = authSet ? T('Sign in') : T('Create a password');
  $('auth-text').textContent = authSet
    ? T('Enter the password of this Mister Download Manager.')
    : T('Choose a password. Every device that opens this page will ask for it.');
  $('confirm-row').hidden = authSet;
  $('password').autocomplete = authSet ? 'current-password' : 'new-password';
  $('auth-submit').textContent = authSet ? T('Sign in') : T('Save password');
  if (!$('name').value) $('name').value = guessName();
  $('password').focus();
}

function signedOut() {
  token = null;
  try { localStorage.removeItem('mdm-token'); } catch (e) { /* nothing kept */ }
  showAuth();
}

$('auth-form').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const err = $('auth-error');
  err.textContent = '';
  const password = $('password').value;
  if (!authSet) {
    if (password.length < 4) { err.textContent = T('The password needs at least 4 characters.'); return; }
    if (password !== $('password2').value) { err.textContent = T('The two passwords are not the same.'); return; }
  }
  const button = $('auth-submit');
  button.disabled = true;
  try {
    const j = await api(authSet ? 'login' : 'setup', { json: { password, name: $('name').value } });
    token = j.token;
    try { localStorage.setItem('mdm-token', token); } catch (e) { /* this visit only */ }
    $('password').value = '';
    $('password2').value = '';
    showMain();
  } catch (e) {
    if (e.code === 'wrong-password' && e.body && e.body.left > 0) err.textContent = F('Wrong password. Tries left: {n}', { n: e.body.left });
    else if (e.code === 'wrong-password' || e.code === 'too-soon') err.textContent = T('Too many wrong tries. Wait a minute, then try again.');
    else if (e.code === 'password-set') { showAuth(); err.textContent = T('A password was set meanwhile. Sign in with it.'); }
    else if (e.code === 'password-short') err.textContent = T('The password needs at least 4 characters.');
    else err.textContent = T('MDM does not answer. Check that it is running and on the same network.');
  } finally {
    button.disabled = false;
  }
});

// ---- the list ----------------------------------------------------------------------------

function showMain() {
  $('pair').hidden = true;
  $('main').hidden = false;
  $('menu').hidden = false;
  $('add-open').hidden = false;
  refresh();
}

function stopPolling() { clearTimeout(timer); timer = null; }

function schedule() {
  stopPolling();
  if (!token) return;
  // Hidden: the worker's ticks do it (a hidden page's own timers are slowed down).
  if (document.visibilityState !== 'visible' && ticker) return;
  timer = setTimeout(refresh, failures ? Math.min(10000, 1500 * (failures + 1)) : 1500);
}

async function refresh() {
  if (!token || refreshing) return;
  refreshing = true;
  try {
    data = await api('list');
    failures = 0;
    $('offline').hidden = true;
    render();
  } catch (e) {
    if (e.code === 'not-paired') return;
    failures++;
    $('offline').textContent = T('MDM does not answer. Trying again...');
    $('offline').hidden = false;
  } finally {
    refreshing = false;
  }
  schedule();
}

const STATUS = { Queued: 'Queued', Downloading: 'Downloading', Stopped: 'Stopped', Complete: 'Complete', Error: 'Error' };

function fillSelect(sel, options) {
  const key = JSON.stringify(options);
  if (sel.dataset.key === key) return;
  const was = sel.value;
  sel.textContent = '';
  for (const [value, label] of options) {
    const o = document.createElement('option');
    o.value = value;
    o.textContent = label;
    sel.append(o);
  }
  sel.dataset.key = key;
  if (options.some(([v]) => v === was)) sel.value = was;
}

function render() {
  const d = data;
  const running = d.downloads.filter((x) => x.status === 'Downloading').length;
  const parts = [];
  if (running) parts.push(speed(d.speed));
  if (d.free != null) parts.push(F('{size} free', { size: size(d.free) }));
  $('summary').textContent = parts.join(' · ');
  setTitle(running && d.speed > 0 ? '\u2193 ' + speed(d.speed) : null);
  const lim = d.limit_kb || 0;
  $('limit-label').textContent = limitLabel(lim);
  $('limit-btn').classList.toggle('on', lim > 0);

  fillSelect($('category'), [['', T('Automatic (by file type)')]].concat(d.categories.map((c) => [c.key, T(c.name)])));
  fillSelect($('when'), [['', T('Start now')]].concat(d.queues.map((q) => [q.name, F('Wait in {queue}', { queue: T(q.name) })])));

  const chips = $('queues');
  chips.textContent = '';
  for (const q of d.queues) {
    const chip = document.createElement('div');
    chip.className = 'chip' + (q.running ? ' on' : '');
    const label = document.createElement('span');
    label.textContent = T(q.name) + ' (' + q.ids.length + ')';
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = q.running ? T('Stop') : T('Start');
    b.addEventListener('click', () => queueAction(q.name, !q.running));
    chip.append(label, b);
    chips.append(chip);
  }

  const shown = d.downloads.filter((x) => filter === 'all' || (filter === 'done') === (x.status === 'Complete'));
  const list = $('list');
  const keep = new Set();
  for (const x of shown) {
    keep.add(x.id);
    let li = rows.get(x.id);
    if (!li) {
      li = $('item').content.firstElementChild.cloneNode(true);
      li.querySelector('.toggle').addEventListener('click', () => toggle(li.dataset.id));
      li.querySelector('.remove').addEventListener('click', () => askRemove(li.dataset.id));
      li.querySelector('.limit').addEventListener('click', () => openLimit(li.dataset.id));
      rows.set(x.id, li);
    }
    li.dataset.id = x.id;
    fillRow(li, x);
    list.append(li);
  }
  for (const [id, li] of rows) if (!keep.has(id)) { li.remove(); rows.delete(id); }
  $('empty').hidden = shown.length > 0;
}

function fillRow(li, x) {
  const name = li.querySelector('.name');
  name.textContent = x.file;
  name.title = x.file;
  const state = li.querySelector('.state');
  state.textContent = T(STATUS[x.status] || x.status);
  state.className = 'state s-' + x.status.toLowerCase();
  const done = x.status === 'Complete';
  const running = x.status === 'Downloading';
  const pct = x.size ? Math.min(100, (100 * x.downloaded) / x.size) : (done ? 100 : 0);
  li.querySelector('.bar-fill').style.width = pct + '%';
  li.querySelector('.bar-track').hidden = done;
  let detail;
  if (done) detail = size(x.size != null ? x.size : x.downloaded);
  else if (x.size) detail = num(pct, 1) + '% · ' + F('{done} of {size}', { done: size(x.downloaded), size: size(x.size) });
  else detail = size(x.downloaded);
  li.querySelector('.detail').textContent = detail;
  li.querySelector('.speed-now').textContent = running && x.speed ? speed(x.speed) : '';

  // Time left, while it goes with a known size.
  const eta = li.querySelector('.eta');
  const left = running && x.left != null ? F('{time} left', { time: duration(x.left) }) : '';
  eta.hidden = !left;
  eta.querySelector('.eta-text').textContent = left;

  // A file: can it go on from where it stopped, or does a stop start it over?
  const resume = li.querySelector('.resume');
  const file = !x.kind && !done;
  if (file && x.resumable === true) {
    resume.hidden = false;
    resume.className = 'resume ok';
    resume.textContent = T('Resume supported');
  } else if (file && x.resumable === false) {
    resume.hidden = false;
    resume.className = 'resume no';
    resume.textContent = T('No resume: a stop starts it over');
  } else if (file && running) {
    resume.hidden = false;
    resume.className = 'resume wait';
    resume.textContent = T('Checking resume support...');
  } else {
    resume.hidden = true;
  }

  const limit = li.querySelector('.limit');
  limit.hidden = done;
  limit.classList.toggle('on', !!x.limit_kb);
  li.querySelector('.limit-name').textContent = x.limit_kb ? limitLabel(x.limit_kb) : T('Limit');
  const toggleBtn = li.querySelector('.toggle');
  toggleBtn.hidden = done;
  toggleBtn.textContent = running ? T('Pause') : T('Start');
  const err = li.querySelector('.error-text');
  err.hidden = !x.error;
  err.textContent = x.error || '';
}

function byId(id) { return data && data.downloads.find((x) => String(x.id) === String(id)); }

async function act(action, ids) {
  const j = await api('act', { json: { action, ids } });
  return j;
}

async function toggle(id) {
  const x = byId(id);
  if (!x) return;
  try {
    await act(x.status === 'Downloading' ? 'pause' : 'start', [x.id]);
  } catch (e) { toast(T('MDM could not do it.'), true); }
  refresh();
}

let removing = null;
function askRemove(id) {
  const x = byId(id);
  if (!x) return;
  removing = x;
  $('confirm-text').textContent = F('Remove {name} from the list?', { name: x.file });
  $('confirm-file').checked = false;
  $('confirm').showModal();
}

$('confirm').addEventListener('close', async () => {
  const x = removing;
  removing = null;
  if (!x || $('confirm').returnValue !== 'ok') return;
  try {
    if (x.status === 'Downloading') await act('pause', [x.id]);
    const j = await act($('confirm-file').checked ? 'delete' : 'remove', [x.id]);
    if (j.skipped && j.skipped.length) toast(T('MDM could not do it.'), true);
  } catch (e) { toast(T('MDM could not do it.'), true); }
  refresh();
});

async function queueAction(name, start) {
  try { await api('queue', { json: { name, start } }); } catch (e) { toast(T('MDM could not do it.'), true); }
  refresh();
}

for (const tab of document.querySelectorAll('[data-filter]')) {
  tab.addEventListener('click', () => {
    filter = tab.dataset.filter;
    for (const t of document.querySelectorAll('[data-filter]')) t.setAttribute('aria-selected', String(t === tab));
    if (data) render();
  });
}

// ---- adding ------------------------------------------------------------------------------

$('file').addEventListener('change', () => {
  const f = $('file').files[0];
  chosenFile = null;
  $('file-name').hidden = true;
  if (!f) return;
  if (f.size > 10 * 1024 * 1024) { toast(T('This file is too large to be a torrent.'), true); $('file').value = ''; return; }
  chosenFile = f;
  $('url').value = '';
  $('file-name').textContent = f.name;
  $('file-name').hidden = false;
});
$('url').addEventListener('input', () => {
  if ($('url').value) { chosenFile = null; $('file').value = ''; $('file-name').hidden = true; }
});
document.querySelector('label.file').addEventListener('keydown', (ev) => {
  if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); $('file').click(); }
});

$('add').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const category = $('category').value;
  const queue = $('when').value;
  const start = queue === '';
  const url = $('url').value.trim();
  if (!url && !chosenFile) { $('url').focus(); return; }
  const button = $('add').querySelector('button[type=submit]');
  button.disabled = true;
  try {
    let j;
    if (chosenFile) {
      const q = new URLSearchParams({ category, queue, start: String(start) });
      j = await api('torrent?' + q, { body: await chosenFile.arrayBuffer(), headers: { 'Content-Type': 'application/x-bittorrent' } });
    } else {
      j = await api('add', { json: { url, category, queue, start } });
    }
    $('add-dialog').close();
    toast(j && j.pending ? T('Added. MDM is reading the torrent: it joins the list in a moment.') : T('Added.'));
    $('url').value = '';
    $('file').value = '';
    chosenFile = null;
    $('file-name').hidden = true;
  } catch (e) {
    if (e.code === 'unsupported') toast(T('MDM cannot download this address.'), true);
    else if (e.code === 'not-a-torrent') toast(T('This is not a torrent file.'), true);
    else if (e.code !== 'not-paired') toast(T('MDM could not add it.'), true);
  } finally {
    button.disabled = false;
  }
  refresh();
});

// ---- the add sheet and the speed limits ----------------------------------------------------

function closeOnBackdrop(dlg) {
  dlg.addEventListener('click', (ev) => { if (ev.target === dlg) dlg.close(); });
}
closeOnBackdrop($('add-dialog'));
closeOnBackdrop($('limit-dialog'));

$('paste').addEventListener('click', async () => {
  try {
    const text = ((await navigator.clipboard.readText()) || '').trim();
    if (!text) { toast(T('The clipboard is empty.'), true); return; }
    $('url').value = text;
    $('url').dispatchEvent(new Event('input'));
    $('url').focus();
  } catch (e) {
    toast(T('The browser did not allow reading the clipboard. Paste into the box by hand.'), true);
    $('url').focus();
  }
});

$('add-open').addEventListener('click', () => { $('add-dialog').showModal(); $('url').focus(); });
$('add-close').addEventListener('click', () => $('add-dialog').close());
$('limit-close').addEventListener('click', () => $('limit-dialog').close());

// The limit for all downloads together (id: null), or for one download.
function openLimit(id) {
  limitTarget = id == null ? null : id;
  const x = limitTarget == null ? null : byId(limitTarget);
  $('limit-title').textContent = x ? T('Limit this download') : T('Speed limit');
  $('limit-for').textContent = x ? x.file : T('For all downloads together.');
  const cur = (x ? x.limit_kb : data && data.limit_kb) || 0;
  const box = $('limit-presets');
  box.textContent = '';
  for (const kb of [0, 128, 256, 512, 1024, 2048, 5120, 10240]) {
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = limitLabel(kb);
    b.setAttribute('aria-pressed', String(kb === cur));
    b.addEventListener('click', () => setLimit(kb));
    box.append(b);
  }
  $('limit-kb').value = cur || '';
  $('limit-dialog').showModal();
}

async function setLimit(kb) {
  try {
    await api('limit', { json: limitTarget == null ? { kb } : { kb, id: Number(limitTarget) } });
    $('limit-dialog').close();
    toast(kb ? F('Speed limit: {speed}', { speed: limitLabel(kb) }) : T('Speed limit removed.'));
  } catch (e) {
    if (e.code !== 'not-paired') toast(T('MDM could not do it.'), true);
  }
  refresh();
}

$('limit-btn').addEventListener('click', () => openLimit(null));
$('limit-set').addEventListener('click', () => {
  const kb = Math.floor(Number($('limit-kb').value));
  if (!(kb >= 1 && kb <= 10000000)) { $('limit-kb').focus(); return; }
  setLimit(kb);
});

// ---- the menu ----------------------------------------------------------------------------

$('menu').addEventListener('click', (ev) => {
  ev.stopPropagation();
  const open = $('menu-list').hidden;
  $('menu-list').hidden = !open;
  $('menu').setAttribute('aria-expanded', String(open));
});
document.addEventListener('click', () => { $('menu-list').hidden = true; $('menu').setAttribute('aria-expanded', 'false'); });
$('forget').addEventListener('click', async () => {
  if (!confirm(T('Forget this device? It needs a new code to connect again.'))) return;
  try { await api('forget', { post: true }); } catch (e) { /* unpaired here anyway */ }
  signedOut();
});

document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible' && token) refresh(); else if (ticker) stopPolling();
});

// A tab in the background has its own timers slowed down (to one a minute after a few minutes);
// a worker's are not, so the speed in the tab's title stays live.
try {
  ticker = new Worker('ticker.js');
  ticker.onmessage = () => { if (document.visibilityState !== 'visible' && token) refresh(); };
} catch (e) { ticker = null; }

loadTexts().then(() => { if (token) showMain(); else showAuth(); });
