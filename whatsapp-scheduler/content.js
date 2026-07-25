/* WhatsApp Message Scheduler — content script
 *
 * Responsibilities:
 *   1. Inject a "Schedule" (clock) button into the WhatsApp Web composer.
 *   2. Open a scheduling modal that reads the currently typed message + chat,
 *      lets the user pick a date/time, and — if today is a weekend — suggests
 *      sending on the coming Monday instead.
 *   3. When the background service worker fires a due message, open the target
 *      chat, type the text, and press send.
 *
 * WhatsApp's DOM changes often, so every selector below has fallbacks and is
 * looked up lazily at the moment of use rather than cached.
 */

(() => {
  "use strict";

  const WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

  /* ----------------------------- DOM helpers ----------------------------- */

  function firstMatch(selectors, root = document) {
    for (const sel of selectors) {
      const el = root.querySelector(sel);
      if (el) return el;
    }
    return null;
  }

  function getComposer() {
    return firstMatch([
      'footer div[contenteditable="true"][role="textbox"]',
      'footer div[contenteditable="true"]',
      '#main footer div[contenteditable="true"]',
    ]);
  }

  function getSendButton() {
    const btn = firstMatch([
      'footer button[aria-label="Send"]',
      'footer button[aria-label*="Send" i]',
    ]);
    if (btn) return btn;
    const icon = firstMatch(['footer span[data-icon="send"]', 'footer span[data-icon="wds-ic-send-filled"]']);
    return icon ? icon.closest("button") : null;
  }

  function getChatTitle() {
    const el = firstMatch(['#main header span[title]', '#main header ._amig span', '#main header span[dir="auto"]']);
    return el ? (el.getAttribute("title") || el.textContent || "").trim() : "";
  }

  function getSearchBox() {
    return firstMatch([
      '#side div[contenteditable="true"][role="textbox"]',
      'div[contenteditable="true"][data-tab="3"]',
      '#side div[contenteditable="true"]',
    ]);
  }

  function getComposerText() {
    const c = getComposer();
    return c ? (c.innerText || c.textContent || "").trim() : "";
  }

  /* Insert text into WhatsApp's Lexical editor by simulating a paste, which is
   * the most reliable way to get React/Lexical to register the value. */
  function insertText(el, text) {
    el.focus();
    try {
      const dt = new DataTransfer();
      dt.setData("text/plain", text);
      el.dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true }));
      return true;
    } catch (_) {
      try {
        document.execCommand("insertText", false, text);
        return true;
      } catch (e) {
        return false;
      }
    }
  }

  function delay(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  async function waitFor(fn, { timeout = 8000, interval = 200 } = {}) {
    const end = Date.now() + timeout;
    while (Date.now() < end) {
      const v = fn();
      if (v) return v;
      await delay(interval);
    }
    return null;
  }

  /* ------------------------- Scheduling date logic ------------------------ */

  function isWeekend(d) {
    const day = d.getDay(); // 0 = Sun, 6 = Sat
    return day === 0 || day === 6;
  }

  function nextMonday9am(from) {
    const d = new Date(from);
    d.setHours(9, 0, 0, 0);
    // Advance to the next Monday (day index 1). If already Monday, keep today.
    const day = d.getDay();
    const add = day === 1 ? 0 : (8 - day) % 7 || 7;
    d.setDate(d.getDate() + add);
    if (d <= from) d.setDate(d.getDate() + 7);
    return d;
  }

  // Format a Date into the value a datetime-local input expects (local time).
  function toLocalInputValue(d) {
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  /* ------------------------------- Modal UI ------------------------------ */

  function buildModal() {
    const now = new Date();
    const weekend = isWeekend(now);

    // Default: 1 hour from now, rounded to the next 5 minutes.
    const defaultTime = new Date(now.getTime() + 60 * 60 * 1000);
    defaultTime.setMinutes(Math.ceil(defaultTime.getMinutes() / 5) * 5, 0, 0);
    const suggested = weekend ? nextMonday9am(now) : defaultTime;

    const overlay = document.createElement("div");
    overlay.className = "wams-overlay";

    const chat = getChatTitle();
    const message = getComposerText();

    overlay.innerHTML = `
      <div class="wams-modal" role="dialog" aria-modal="true" aria-label="Schedule message">
        <div class="wams-header">
          <span class="wams-clock">🕑</span>
          <h2>Schedule message</h2>
          <button class="wams-close" title="Close" aria-label="Close">&times;</button>
        </div>
        <div class="wams-body">
          <label class="wams-field">
            <span class="wams-label">To</span>
            <input class="wams-chat" type="text" value="${escapeHtml(chat)}" placeholder="Contact or group name" />
          </label>
          <label class="wams-field">
            <span class="wams-label">Message</span>
            <textarea class="wams-message" rows="3" placeholder="Type your message">${escapeHtml(message)}</textarea>
          </label>
          <label class="wams-field">
            <span class="wams-label">Send at</span>
            <input class="wams-datetime" type="datetime-local" value="${toLocalInputValue(suggested)}" />
          </label>
          ${
            weekend
              ? `<div class="wams-weekend">
                   <strong>It's the ${WEEKDAYS[now.getDay()]}.</strong>
                   Messages sent on the weekend often get missed — how about
                   <button class="wams-suggest" type="button">Monday ${suggested.getHours()}:${String(
                    suggested.getMinutes()
                  ).padStart(2, "0")}</button> instead?
                 </div>`
              : ""
          }
          <div class="wams-error" hidden></div>
        </div>
        <div class="wams-footer">
          <button class="wams-cancel" type="button">Cancel</button>
          <button class="wams-send-now" type="button">Send now</button>
          <button class="wams-schedule" type="button">Schedule</button>
        </div>
      </div>`;

    document.body.appendChild(overlay);

    const $ = (sel) => overlay.querySelector(sel);
    const close = () => overlay.remove();

    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) close();
    });
    $(".wams-close").addEventListener("click", close);
    $(".wams-cancel").addEventListener("click", close);
    document.addEventListener("keydown", function onEsc(e) {
      if (e.key === "Escape") {
        close();
        document.removeEventListener("keydown", onEsc);
      }
    });

    const suggestBtn = $(".wams-suggest");
    if (suggestBtn) {
      suggestBtn.addEventListener("click", () => {
        $(".wams-datetime").value = toLocalInputValue(nextMonday9am(new Date()));
      });
    }

    const showError = (msg) => {
      const box = $(".wams-error");
      box.textContent = msg;
      box.hidden = false;
    };

    function collect() {
      const chatName = $(".wams-chat").value.trim();
      const text = $(".wams-message").value.trim();
      const dtVal = $(".wams-datetime").value;
      if (!chatName) return showError("Please enter who to send to."), null;
      if (!text) return showError("Please enter a message."), null;
      if (!dtVal) return showError("Please pick a date and time."), null;
      const when = new Date(dtVal).getTime();
      if (isNaN(when)) return showError("That date/time looks invalid."), null;
      return { chatName, text, when };
    }

    $(".wams-schedule").addEventListener("click", () => {
      const data = collect();
      if (!data) return;
      if (data.when <= Date.now()) {
        showError("Pick a time in the future (or use “Send now”).");
        return;
      }
      chrome.runtime.sendMessage(
        { type: "SCHEDULE_MESSAGE", payload: { ...data, chatTitleAtSchedule: chat, createdAt: Date.now() } },
        (res) => {
          if (chrome.runtime.lastError || !res || !res.ok) {
            showError("Could not schedule: " + ((res && res.error) || chrome.runtime.lastError?.message || "unknown"));
            return;
          }
          close();
          toast(`Scheduled for ${new Date(data.when).toLocaleString()}`);
        }
      );
    });

    $(".wams-send-now").addEventListener("click", async () => {
      const data = collect();
      if (!data) return;
      $(".wams-send-now").disabled = true;
      const ok = await deliverMessage({ chatName: data.chatName, text: data.text });
      if (ok) {
        close();
        toast("Message sent");
      } else {
        $(".wams-send-now").disabled = false;
        showError("Could not send. Make sure the chat exists and try again.");
      }
    });
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function toast(msg) {
    const t = document.createElement("div");
    t.className = "wams-toast";
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(() => t.classList.add("wams-toast-in"), 10);
    setTimeout(() => {
      t.classList.remove("wams-toast-in");
      setTimeout(() => t.remove(), 300);
    }, 3200);
  }

  /* ----------------------- Delivering a message ------------------------- */

  // Open the chat with the given name via the search box, then verify it's active.
  async function openChat(chatName) {
    if (getChatTitle().toLowerCase() === chatName.toLowerCase()) return true;

    const search = getSearchBox();
    if (!search) return false;
    insertText(search, "");
    search.focus();
    // Clear any existing search text.
    document.execCommand("selectAll", false, null);
    document.execCommand("delete", false, null);
    insertText(search, chatName);
    await delay(1200);

    const result = await waitFor(() => {
      const nodes = document.querySelectorAll('#pane-side span[title]');
      for (const n of nodes) {
        if ((n.getAttribute("title") || "").toLowerCase() === chatName.toLowerCase()) return n;
      }
      // Fall back to the first result row if no exact title match.
      return document.querySelector('#pane-side [role="listitem"]');
    }, { timeout: 5000 });

    if (!result) return false;
    (result.closest('[role="listitem"]') || result).click();

    const opened = await waitFor(
      () => getChatTitle().toLowerCase() === chatName.toLowerCase() || getComposer(),
      { timeout: 5000 }
    );
    return !!opened;
  }

  async function deliverMessage({ chatName, text }) {
    try {
      const opened = await openChat(chatName);
      if (!opened) return false;
      const composer = await waitFor(getComposer, { timeout: 5000 });
      if (!composer) return false;
      composer.focus();
      insertText(composer, text);
      await delay(400);
      const sendBtn = await waitFor(getSendButton, { timeout: 3000 });
      if (sendBtn) {
        sendBtn.click();
      } else {
        composer.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true }));
      }
      await delay(500);
      return true;
    } catch (e) {
      console.error("[WA Scheduler] deliver failed", e);
      return false;
    }
  }

  /* --------------------- Button injection & lifecycle -------------------- */

  function injectButton() {
    const footer = document.querySelector("#main footer") || document.querySelector("footer");
    if (!footer) return;
    if (footer.querySelector(".wams-schedule-btn")) return;

    const sendBtn = getSendButton();
    const anchor = sendBtn ? sendBtn.parentElement : footer;

    const btn = document.createElement("button");
    btn.className = "wams-schedule-btn";
    btn.type = "button";
    btn.title = "Schedule this message";
    btn.setAttribute("aria-label", "Schedule this message");
    btn.innerHTML =
      '<svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"></circle><polyline points="12 7 12 12 15.5 14"></polyline></svg>';
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (!document.querySelector(".wams-overlay")) buildModal();
    });

    if (sendBtn && anchor) {
      anchor.insertBefore(btn, sendBtn);
    } else {
      footer.appendChild(btn);
    }
  }

  const observer = new MutationObserver(() => injectButton());
  observer.observe(document.body, { childList: true, subtree: true });
  injectButton();

  /* ----------------- Respond to background delivery requests ------------- */

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (msg && msg.type === "DELIVER_MESSAGE") {
      deliverMessage(msg.payload).then((ok) => sendResponse({ ok }));
      return true; // async response
    }
    if (msg && msg.type === "PING") {
      sendResponse({ ok: true });
      return false;
    }
  });
})();
