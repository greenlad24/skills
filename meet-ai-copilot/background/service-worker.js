// Background service worker. Holds no state that matters across restarts; its
// job is to run Claude calls off the page so the API key never lives in
// meet.google.com's context, and to stream tokens back to the content script.
import { runGate, streamAnswer, modelLabel } from "../lib/claude-client.js";

// One port per Meet tab. Each request is multiplexed by reqId.
chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== "mc") return;
  const inflight = new Map(); // reqId -> AbortController

  port.onMessage.addListener(async (msg) => {
    if (msg.type === "suggest") return handleSuggest(port, msg, inflight);
    if (msg.type === "ask") return handleAsk(port, msg, inflight);
    if (msg.type === "cancel") {
      inflight.get(msg.reqId)?.abort();
      inflight.delete(msg.reqId);
    }
  });

  port.onDisconnect.addListener(() => {
    for (const ac of inflight.values()) ac.abort();
    inflight.clear();
  });
});

async function handleSuggest(port, msg, inflight) {
  const { reqId, kind, question, speaker, transcript, settings } = msg;
  const ac = new AbortController();
  inflight.set(reqId, ac);
  try {
    // Directed questions are obvious — skip the gate for speed. Everything else
    // goes through the cheap Haiku gate first so the pricey model runs rarely.
    if (settings.useGate && kind !== "directed_question") {
      const respond = await runGate({ settings, transcript, question, speaker });
      if (!respond) {
        post(port, { type: "gate_declined", reqId });
        return;
      }
    }
    post(port, { type: "model", reqId, label: modelLabel(settings.answerModel) });
    await streamAnswer({
      settings,
      transcript,
      question,
      speaker,
      mode: "answer",
      signal: ac.signal,
      onDelta: (text) => post(port, { type: "delta", reqId, text }),
    });
    post(port, { type: "done", reqId });
  } catch (e) {
    if (e.name !== "AbortError")
      post(port, { type: "error", reqId, message: e.message || String(e) });
  } finally {
    inflight.delete(reqId);
  }
}

async function handleAsk(port, msg, inflight) {
  const { reqId, question, transcript, settings } = msg;
  const ac = new AbortController();
  inflight.set(reqId, ac);
  try {
    post(port, { type: "model", reqId, label: modelLabel(settings.answerModel) });
    await streamAnswer({
      settings,
      transcript,
      question,
      mode: "ask",
      signal: ac.signal,
      onDelta: (text) => post(port, { type: "delta", reqId, text }),
    });
    post(port, { type: "done", reqId });
  } catch (e) {
    if (e.name !== "AbortError")
      post(port, { type: "error", reqId, message: e.message || String(e) });
  } finally {
    inflight.delete(reqId);
  }
}

function post(port, msg) {
  try {
    port.postMessage(msg);
  } catch {
    /* port closed */
  }
}

// Toolbar icon toggles the on-screen panel in the active Meet tab.
chrome.action.onClicked?.addListener?.(async (tab) => {
  if (tab?.id) chrome.tabs.sendMessage(tab.id, { type: "toggle-panel" });
});
