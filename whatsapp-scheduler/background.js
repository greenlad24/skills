/* WhatsApp Message Scheduler — background service worker
 *
 * Owns the durable list of scheduled messages (chrome.storage.local) and the
 * chrome.alarms that wake it when one is due. When an alarm fires it locates a
 * WhatsApp Web tab (opening one if needed) and asks the content script to
 * deliver the message, then records the result.
 */

const STORE_KEY = "scheduled";
const ALARM_PREFIX = "wams:";

/* ------------------------------ storage ------------------------------ */

async function getAll() {
  const data = await chrome.storage.local.get(STORE_KEY);
  return Array.isArray(data[STORE_KEY]) ? data[STORE_KEY] : [];
}

async function saveAll(items) {
  await chrome.storage.local.set({ [STORE_KEY]: items });
}

async function upsert(item) {
  const items = await getAll();
  const idx = items.findIndex((i) => i.id === item.id);
  if (idx >= 0) items[idx] = item;
  else items.push(item);
  await saveAll(items);
}

async function patch(id, fields) {
  const items = await getAll();
  const idx = items.findIndex((i) => i.id === id);
  if (idx >= 0) {
    items[idx] = { ...items[idx], ...fields };
    await saveAll(items);
  }
}

function makeId() {
  return "m_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 8);
}

/* ------------------------------ alarms ------------------------------ */

function scheduleAlarm(item) {
  chrome.alarms.create(ALARM_PREFIX + item.id, { when: item.when });
}

async function rebuildAlarms() {
  const items = await getAll();
  const now = Date.now();
  for (const item of items) {
    if (item.status === "pending") {
      if (item.when <= now) {
        // Missed while the worker was asleep — fire as soon as possible.
        chrome.alarms.create(ALARM_PREFIX + item.id, { when: now + 1000 });
      } else {
        scheduleAlarm(item);
      }
    }
  }
}

/* -------------------------- delivery pipeline -------------------------- */

async function findWhatsAppTab() {
  const tabs = await chrome.tabs.query({ url: "https://web.whatsapp.com/*" });
  return tabs[0] || null;
}

async function ensureWhatsAppTab() {
  let tab = await findWhatsAppTab();
  if (tab) return tab;
  tab = await chrome.tabs.create({ url: "https://web.whatsapp.com/", active: false });
  // Give WhatsApp Web time to load and the content script to attach.
  await waitForContentScript(tab.id, 30000);
  return tab;
}

function sendToTab(tabId, message) {
  return new Promise((resolve) => {
    chrome.tabs.sendMessage(tabId, message, (res) => {
      if (chrome.runtime.lastError) resolve(null);
      else resolve(res);
    });
  });
}

async function waitForContentScript(tabId, timeoutMs) {
  const end = Date.now() + timeoutMs;
  while (Date.now() < end) {
    const res = await sendToTab(tabId, { type: "PING" });
    if (res && res.ok) return true;
    await new Promise((r) => setTimeout(r, 1000));
  }
  return false;
}

async function deliver(item) {
  try {
    const tab = await ensureWhatsAppTab();
    if (!tab) throw new Error("No WhatsApp Web tab available");
    const ready = await waitForContentScript(tab.id, 20000);
    if (!ready) throw new Error("WhatsApp Web not ready");
    const res = await sendToTab(tab.id, {
      type: "DELIVER_MESSAGE",
      payload: { chatName: item.chatName, text: item.text },
    });
    if (res && res.ok) {
      await patch(item.id, { status: "sent", sentAt: Date.now() });
      notify("Message sent", `To ${item.chatName}: ${truncate(item.text)}`);
    } else {
      throw new Error("Delivery failed in page");
    }
  } catch (e) {
    await patch(item.id, { status: "failed", error: String(e.message || e), failedAt: Date.now() });
    notify("Couldn't send scheduled message", `To ${item.chatName}. Open WhatsApp Web and try again.`);
  }
}

function truncate(s, n = 80) {
  s = String(s);
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

function notify(title, message) {
  try {
    chrome.notifications.create({
      type: "basic",
      iconUrl: "icons/icon128.png",
      title,
      message,
    });
  } catch (_) {
    /* notifications permission may be unavailable; ignore */
  }
}

/* ------------------------------ events ------------------------------ */

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (!alarm.name.startsWith(ALARM_PREFIX)) return;
  const id = alarm.name.slice(ALARM_PREFIX.length);
  const items = await getAll();
  const item = items.find((i) => i.id === id);
  if (item && item.status === "pending") await deliver(item);
});

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  (async () => {
    try {
      if (msg.type === "SCHEDULE_MESSAGE") {
        const p = msg.payload;
        const item = {
          id: makeId(),
          chatName: p.chatName,
          text: p.text,
          when: p.when,
          status: "pending",
          createdAt: p.createdAt || Date.now(),
        };
        await upsert(item);
        scheduleAlarm(item);
        sendResponse({ ok: true, id: item.id });
      } else if (msg.type === "GET_SCHEDULED") {
        sendResponse({ ok: true, items: await getAll() });
      } else if (msg.type === "CANCEL_MESSAGE") {
        chrome.alarms.clear(ALARM_PREFIX + msg.id);
        const items = (await getAll()).filter((i) => i.id !== msg.id);
        await saveAll(items);
        sendResponse({ ok: true });
      } else if (msg.type === "SEND_NOW") {
        const items = await getAll();
        const item = items.find((i) => i.id === msg.id);
        if (item) {
          chrome.alarms.clear(ALARM_PREFIX + item.id);
          await deliver(item);
        }
        sendResponse({ ok: true });
      } else {
        sendResponse({ ok: false, error: "unknown message type" });
      }
    } catch (e) {
      sendResponse({ ok: false, error: String(e.message || e) });
    }
  })();
  return true; // keep the channel open for async sendResponse
});

chrome.runtime.onInstalled.addListener(rebuildAlarms);
chrome.runtime.onStartup.addListener(rebuildAlarms);
// Also rebuild whenever the worker spins up.
rebuildAlarms();
