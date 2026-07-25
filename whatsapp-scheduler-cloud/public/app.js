'use strict';

/*
 * WhatsApp Cloud Scheduler — PWA front-end.
 * Talks to the /api/* JSON API defined in SPEC.md.
 */

// ---------------------------------------------------------------------------
// API helper
// ---------------------------------------------------------------------------
const TOKEN_KEY = 'wa_token';

const API = {
  token: localStorage.getItem(TOKEN_KEY) || '',

  setToken(t) {
    this.token = t || '';
    if (t) localStorage.setItem(TOKEN_KEY, t);
    else localStorage.removeItem(TOKEN_KEY);
  },

  async call(path, opts = {}) {
    const headers = Object.assign({}, opts.headers || {});
    if (this.token) headers['Authorization'] = 'Bearer ' + this.token;
    if (opts.body != null) headers['Content-Type'] = 'application/json';
    const res = await fetch(path, Object.assign({}, opts, { headers }));
    if (res.status === 401) {
      API.setToken('');
      showScreen('screen-token');
      startStatusFlow(); // re-evaluate once a token is entered
      throw new Error('Unauthorized');
    }
    let data = {};
    try {
      data = await res.json();
    } catch (_e) {
      data = {};
    }
    if (!res.ok) throw new Error(data.error || 'HTTP ' + res.status);
    return data;
  },
};

// ---------------------------------------------------------------------------
// Screen switching
// ---------------------------------------------------------------------------
const SCREENS = ['screen-loading', 'screen-token', 'screen-qr', 'screen-app'];

function showScreen(id) {
  for (const s of SCREENS) {
    const el = document.getElementById(s);
    if (el) el.hidden = s !== id;
  }
}

// ---------------------------------------------------------------------------
// Timers
// ---------------------------------------------------------------------------
let statusTimer = null;
let listTimer = null;
let appInitialized = false;
let suggestData = null;

function stopStatusPoll() {
  if (statusTimer) {
    clearInterval(statusTimer);
    statusTimer = null;
  }
}

function startStatusPoll() {
  if (statusTimer) return; // idempotent
  statusTimer = setInterval(startStatusFlow, 3000);
}

function stopListPoll() {
  if (listTimer) {
    clearInterval(listTimer);
    listTimer = null;
  }
}

function startListPoll() {
  if (listTimer) return;
  listTimer = setInterval(loadMessages, 5000);
}

// ---------------------------------------------------------------------------
// Status flow — the top-level router
// ---------------------------------------------------------------------------
async function startStatusFlow() {
  let status;
  try {
    status = await API.call('/api/status');
  } catch (_e) {
    return; // 401 already routed to token screen
  }

  updateProviderBadge(status);

  if (status.authRequired && !API.token) {
    stopStatusPoll();
    showScreen('screen-token');
    return;
  }

  if (status.provider === 'personal' && !status.connected) {
    showQr(status);
    showScreen('screen-qr');
    startStatusPoll();
    return;
  }

  // Connected (or business provider ready).
  stopStatusPoll();
  showScreen('screen-app');
  await initApp();
}

function updateProviderBadge(status) {
  const badge = document.getElementById('provider-badge');
  if (!badge || !status.provider) return;
  badge.hidden = false;
  badge.textContent = status.provider;
  badge.classList.toggle('connected', !!status.connected);
}

function showQr(status) {
  const img = document.getElementById('qr-img');
  const waiting = document.getElementById('qr-waiting');
  if (status.qr) {
    img.src = status.qr;
    img.hidden = false;
    if (waiting) waiting.hidden = true;
  } else {
    img.hidden = true;
    if (waiting) waiting.hidden = false;
  }
}

// ---------------------------------------------------------------------------
// Token form
// ---------------------------------------------------------------------------
document.getElementById('token-form').addEventListener('submit', (e) => {
  e.preventDefault();
  const input = document.getElementById('token-input');
  const err = document.getElementById('token-error');
  const val = input.value.trim();
  if (!val) return;
  err.hidden = true;
  API.setToken(val);
  showScreen('screen-loading');
  startStatusFlow();
});

// ---------------------------------------------------------------------------
// App init (composer + list). Runs once.
// ---------------------------------------------------------------------------
async function initApp() {
  if (appInitialized) return;
  appInitialized = true;

  wireComposer();
  await loadSuggest();
  await loadMessages();
  startListPoll();
}

async function loadSuggest() {
  try {
    suggestData = await API.call('/api/suggest');
  } catch (_e) {
    suggestData = null;
    return;
  }
  const whenInput = document.getElementById('when-input');
  whenInput.value = isoToLocalInput(suggestData.defaultSend);

  const banner = document.getElementById('weekend-banner');
  const reason = document.getElementById('weekend-reason');
  if (suggestData.isWeekend) {
    reason.textContent = suggestData.reason || 'It is the weekend.';
    banner.hidden = false;
  } else {
    banner.hidden = true;
  }
}

function wireComposer() {
  const form = document.getElementById('composer');
  const sendNowBtn = document.getElementById('send-now-btn');
  const useMonday = document.getElementById('use-monday');

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    submitComposer(false);
  });

  sendNowBtn.addEventListener('click', () => submitComposer(true));

  useMonday.addEventListener('click', () => {
    if (suggestData && suggestData.suggested) {
      document.getElementById('when-input').value = isoToLocalInput(
        suggestData.suggested,
      );
    }
  });
}

async function submitComposer(sendImmediately) {
  const to = document.getElementById('to-input').value.trim();
  const text = document.getElementById('text-input').value.trim();
  const whenVal = document.getElementById('when-input').value;
  const errEl = document.getElementById('composer-error');
  errEl.hidden = true;

  if (!to || !text || !whenVal) {
    showComposerError('Please fill in recipient, message and time.');
    return;
  }

  // datetime-local is local wall-clock; convert to an absolute epoch ms.
  const whenMs = new Date(whenVal).getTime();
  if (!Number.isFinite(whenMs)) {
    showComposerError('Invalid date/time.');
    return;
  }

  try {
    const { message } = await API.call('/api/messages', {
      method: 'POST',
      body: JSON.stringify({ to, text, when: whenMs }),
    });
    if (sendImmediately && message && message.id) {
      await API.call('/api/messages/' + encodeURIComponent(message.id) + '/send-now', {
        method: 'POST',
      });
      toast('Sending now…');
    } else {
      toast('Scheduled ✅');
    }
    document.getElementById('text-input').value = '';
    await loadSuggest();
    await loadMessages();
  } catch (err) {
    showComposerError(err.message || 'Could not schedule.');
  }
}

function showComposerError(msg) {
  const errEl = document.getElementById('composer-error');
  errEl.textContent = msg;
  errEl.hidden = false;
}

// ---------------------------------------------------------------------------
// Messages list
// ---------------------------------------------------------------------------
async function loadMessages() {
  let data;
  try {
    data = await API.call('/api/messages');
  } catch (_e) {
    return;
  }
  const messages = (data.messages || [])
    .slice()
    .sort((a, b) => b.when - a.when);
  renderMessages(messages);
}

function renderMessages(messages) {
  const list = document.getElementById('messages');
  const empty = document.getElementById('empty-state');
  const count = document.getElementById('list-count');

  count.textContent = messages.length ? messages.length + ' total' : '';
  empty.hidden = messages.length > 0;

  list.innerHTML = '';
  for (const m of messages) {
    list.appendChild(renderItem(m));
  }
}

function renderItem(m) {
  const li = document.createElement('li');
  li.className = 'message';
  li.dataset.id = m.id;

  const head = document.createElement('div');
  head.className = 'message-head';

  const to = document.createElement('span');
  to.className = 'message-to';
  to.textContent = m.toDisplay || m.to;

  const badge = document.createElement('span');
  badge.className = 'badge badge-' + m.status;
  badge.textContent = m.status;

  head.appendChild(to);
  head.appendChild(badge);

  const body = document.createElement('div');
  body.className = 'message-text';
  body.textContent = m.text;

  const when = document.createElement('div');
  when.className = 'message-when muted small';
  when.textContent = formatWhen(m.when) + (m.source === 'chat' ? ' · via chat' : '');
  if (m.status === 'failed' && m.error) {
    when.textContent += ' · ' + m.error;
  }

  const actions = document.createElement('div');
  actions.className = 'message-actions';

  if (m.status === 'pending') {
    actions.appendChild(actionBtn('Cancel', 'btn-ghost', () => cancelMsg(m.id)));
  }
  actions.appendChild(actionBtn('Send now', 'btn-ghost', () => sendNowMsg(m.id)));
  actions.appendChild(actionBtn('Remove', 'btn-ghost btn-danger', () => removeMsg(m.id)));

  li.appendChild(head);
  li.appendChild(body);
  li.appendChild(when);
  li.appendChild(actions);
  return li;
}

function actionBtn(label, cls, handler) {
  const b = document.createElement('button');
  b.type = 'button';
  b.className = 'btn btn-small ' + cls;
  b.textContent = label;
  b.addEventListener('click', handler);
  return b;
}

async function cancelMsg(id) {
  try {
    await API.call('/api/messages/' + encodeURIComponent(id) + '/cancel', {
      method: 'POST',
    });
    toast('Canceled');
    await loadMessages();
  } catch (err) {
    toast(err.message || 'Failed');
  }
}

async function sendNowMsg(id) {
  try {
    await API.call('/api/messages/' + encodeURIComponent(id) + '/send-now', {
      method: 'POST',
    });
    toast('Sending now…');
    await loadMessages();
  } catch (err) {
    toast(err.message || 'Failed');
  }
}

async function removeMsg(id) {
  try {
    await API.call('/api/messages/' + encodeURIComponent(id), {
      method: 'DELETE',
    });
    toast('Removed');
    await loadMessages();
  } catch (err) {
    toast(err.message || 'Failed');
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function isoToLocalInput(iso) {
  const d = new Date(iso);
  if (!Number.isFinite(d.getTime())) return '';
  const pad = (n) => String(n).padStart(2, '0');
  return (
    d.getFullYear() +
    '-' +
    pad(d.getMonth() + 1) +
    '-' +
    pad(d.getDate()) +
    'T' +
    pad(d.getHours()) +
    ':' +
    pad(d.getMinutes())
  );
}

function formatWhen(ms) {
  try {
    return new Date(ms).toLocaleString();
  } catch (_e) {
    return String(ms);
  }
}

let toastTimer = null;
function toast(msg) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.hidden = false;
  el.classList.add('show');
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    el.classList.remove('show');
    el.hidden = true;
  }, 2500);
}

// ---------------------------------------------------------------------------
// Service worker + boot
// ---------------------------------------------------------------------------
function registerServiceWorker() {
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/sw.js').catch(() => {
        /* SW registration is best-effort */
      });
    });
  }
}

registerServiceWorker();
startStatusFlow();
