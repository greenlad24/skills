# WhatsApp Message Scheduler

A Chrome extension that adds a **Schedule** button to WhatsApp Web. Compose a
message, pick when it should go out, and the extension sends it for you. If
today is **Saturday or Sunday**, it points that out and offers to send on
**Monday** instead.

## Features

- ⏰ **Schedule button** injected right next to WhatsApp's send button.
- 📅 **Date/time picker** pre-filled with a sensible default (1 hour out).
- 🗓️ **Weekend awareness** — on Sat/Sun it warns you and one click reschedules
  to Monday 9:00 AM.
- 📤 **Send now** option straight from the dialog.
- 📋 **Popup manager** (toolbar icon) to review, send-now, or cancel anything
  you've queued.
- 🔔 Desktop notification when a message sends (or fails).

## How it works

- The **content script** (`content.js`) injects the button and dialog into
  `web.whatsapp.com`, reads the open chat + typed text, and — when a message is
  due — opens the target chat via search and sends it.
- The **service worker** (`background.js`) stores the queue in
  `chrome.storage.local` and uses `chrome.alarms` to wake at send time. Alarms
  are rebuilt on startup, so pending messages survive the worker sleeping.
- The **popup** (`popup.html/js`) lists everything you've scheduled.

## Install (unpacked)

1. Go to `chrome://extensions`.
2. Turn on **Developer mode** (top right).
3. Click **Load unpacked** and select this `whatsapp-scheduler/` folder.
4. Open [web.whatsapp.com](https://web.whatsapp.com/), open a chat, type a
   message, and click the **clock** icon by the send button.

## Notes & limitations

- Chrome must be **running** at send time (the browser can be minimized). A
  WhatsApp Web tab is opened automatically if one isn't already open, but you
  must be **logged in**.
- Sending relies on WhatsApp Web's DOM. WhatsApp changes its markup often; the
  selectors here use fallbacks, but a future redesign may need an update to the
  selectors in `content.js`.
- The target chat is matched by the name shown in WhatsApp. Very similar names
  can be ambiguous — double-check group/contact names.
- Nothing leaves your browser: there is no server and no network calls beyond
  WhatsApp Web itself.

## Permissions

| Permission | Why |
|---|---|
| `storage` | Persist the scheduled-message queue. |
| `alarms` | Wake the worker at send time. |
| `tabs` | Find/open the WhatsApp Web tab to deliver into. |
| `notifications` | Tell you when a message was sent or failed. |
| `host_permissions: web.whatsapp.com` | Inject the button and deliver messages. |
