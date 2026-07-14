// Orchestrator: capture -> local filter -> background (Claude) -> overlay.
(() => {
  const MC = window.MeetCopilot;

  let port = null;
  let lastCallTs = 0;
  let reqSeq = 0;
  const pending = new Map(); // reqId -> cardId

  function connect() {
    port = chrome.runtime.connect({ name: "mc" });
    port.onMessage.addListener(onBackgroundMessage);
    port.onDisconnect.addListener(() => {
      port = null;
      // Reconnect lazily on next use.
    });
  }

  function send(msg) {
    if (!port) connect();
    try {
      port.postMessage(msg);
    } catch (e) {
      connect();
      port.postMessage(msg);
    }
  }

  function onBackgroundMessage(msg) {
    const cardId = pending.get(msg.reqId);
    switch (msg.type) {
      case "gate_declined":
        if (cardId) MC.overlay.removeCard(cardId);
        pending.delete(msg.reqId);
        MC.overlay.setStatus("live", "live");
        break;
      case "model":
        MC.overlay.setCardModel(cardId, msg.label);
        MC.overlay.setStatus("answering", "thinking");
        break;
      case "delta":
        MC.overlay.appendAnswer(cardId, msg.text);
        break;
      case "done":
        MC.overlay.setStatus("live", "live");
        pending.delete(msg.reqId);
        break;
      case "error":
        MC.overlay.setAnswer(cardId, "⚠ " + msg.message);
        MC.overlay.setStatus("error", "warn");
        pending.delete(msg.reqId);
        break;
    }
  }

  // ---- Utterance handling ----------------------------------------------

  MC.onUtterance = (utt) => {
    if (!MC.settings.enabled) return;
    // Always show the finalized line in the transcript feed — even with no key.
    MC.overlay.pushTranscriptLine(utt.speaker, utt.text, utt.isSelf);
    MC.overlay.setStatus("live", "live");

    if (!MC.settings.apiKey) return; // captured, just can't answer yet
    const cand = MC.detector.evaluate(utt, {
      autoSuggest: MC.settings.autoSuggest,
    });
    if (!cand) return;

    const now = Date.now();
    const throttle = MC.settings.minSecondsBetweenCalls * 1000;
    const isUrgent = cand.priority >= 3;
    if (now - lastCallTs < throttle && !isUrgent) return;
    lastCallTs = now;

    fire(cand);
  };

  function fire(cand) {
    const reqId = ++reqSeq;
    const cardId = "mc-card-" + reqId;
    MC.overlay.addCard(cardId, cand.text);
    MC.overlay.setStatus("thinking", "thinking");
    pending.set(reqId, cardId);
    send({
      type: "suggest",
      reqId,
      kind: cand.kind,
      question: cand.text,
      speaker: cand.speaker,
      transcript: MC.transcriptText(),
      settings: pick(),
    });
  }

  MC.onManualAsk = (question) => {
    if (!MC.settings.apiKey) {
      MC.overlay.setStatus("add API key", "warn");
      return;
    }
    const reqId = ++reqSeq;
    const cardId = "mc-card-" + reqId;
    MC.overlay.addCard(cardId, question);
    MC.overlay.setStatus("thinking", "thinking");
    pending.set(reqId, cardId);
    send({
      type: "ask",
      reqId,
      question,
      transcript: MC.transcriptText(),
      settings: pick(),
    });
  };

  // Only forward the fields the background needs (never log the key elsewhere).
  function pick() {
    const s = MC.settings;
    return {
      apiKey: s.apiKey,
      answerModel: s.answerModel,
      gateModel: s.gateModel,
      useGate: s.useGate,
      userName: s.userName,
      userContext: s.userContext,
      language: s.language,
    };
  }

  // ---- Capture status ---------------------------------------------------

  MC.onInterim = (u) => {
    MC.overlay.setInterim(u.speaker, u.text, u.isSelf);
  };

  MC.onCaptureState = (state) => {
    if (state === "capturing") MC.overlay.setStatus("listening…", "live");
    else if (state === "waiting-for-captions")
      MC.overlay.setStatus("waiting for Meet", "warn");
    else if (state === "captions-off")
      MC.overlay.setStatus("turn on CC", "warn");
    else if (state === "stopped") MC.overlay.setStatus("off", "");
  };

  MC.onSettingsChanged = (changes) => {
    if ("enabled" in changes) {
      if (MC.settings.enabled) {
        MC.overlay.show();
        MC.capture.start();
      } else {
        MC.capture.stop();
        MC.overlay.setStatus("disabled", "");
      }
    }
  };

  // ---- Messages from popup ----------------------------------------------

  chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
    if (msg.type === "toggle-panel") {
      MC.overlay.toggle();
      reply({ ok: true });
    } else if (msg.type === "ping") {
      reply({ ok: true, capturing: MC.settings.enabled });
    }
    return true;
  });

  // ---- Boot -------------------------------------------------------------

  async function boot() {
    await MC.loadSettings();
    connect();
    MC.overlay.build();
    if (MC.settings.enabled) {
      MC.overlay.show();
      MC.capture.start();
    } else {
      MC.overlay.setStatus("disabled", "");
    }
    MC.log("booted", { model: MC.settings.answerModel });
  }

  boot();
})();
