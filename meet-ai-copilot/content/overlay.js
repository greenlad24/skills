// The on-screen panel. Draggable, collapsible, private to you. Two tabs:
//   • Transcript — the live caption feed (proves capture is working)
//   • Answers    — Claude's streamed suggestions
(() => {
  const MC = window.MeetCopilot;

  let rootEl, dotEl, statusEl;
  let answersEl, transcriptEl, interimEl, askInput, badgeEl;
  const cards = new Map(); // id -> { el, answerEl, modelEl }
  let activeTab = "answers";
  let unseenAnswers = 0;

  function build() {
    if (rootEl) return;
    rootEl = document.createElement("div");
    rootEl.id = "mc-root";
    rootEl.innerHTML = `
      <div class="mc-panel">
        <div class="mc-header" id="mc-header">
          <span class="mc-dot" id="mc-dot"></span>
          <span class="mc-title">AI Copilot <span class="mc-status" id="mc-status">starting…</span></span>
          <button class="mc-btn mc-font" id="mc-smaller" title="Smaller text">A−</button>
          <button class="mc-btn mc-font" id="mc-bigger" title="Bigger text">A+</button>
          <button class="mc-btn" id="mc-collapse" title="Collapse / expand">▾</button>
          <button class="mc-btn" id="mc-hide" title="Hide (toggle from the toolbar icon)">✕</button>
        </div>
        <div class="mc-tabs">
          <button class="mc-tab mc-active" data-tab="answers">Answers <span class="mc-badge" id="mc-badge"></span></button>
          <button class="mc-tab" data-tab="transcript">Transcript</button>
        </div>
        <div class="mc-body">
          <div class="mc-pane mc-active" id="mc-answers">
            <div class="mc-empty" id="mc-aempty">
              When someone asks you something — or there's a moment worth adding to —
              value-packed bullet points stream in here. You can also just ask below.
              <br><br>Switch to <b>Transcript</b> to watch the live captions.
            </div>
          </div>
          <div class="mc-pane" id="mc-transcript">
            <div class="mc-empty" id="mc-tempty">
              Waiting for Google Meet captions…<br><br>
              Make sure captions are <b>on</b> (the <b>CC</b> button at the bottom of Meet).
              Spoken text will stream in here as it's captured.
            </div>
            <div class="mc-feed" id="mc-feed"></div>
            <div class="mc-interim" id="mc-interim"></div>
          </div>
        </div>
        <div class="mc-footer">
          <input class="mc-ask" id="mc-ask" placeholder="Ask Claude about this meeting…" />
          <button class="mc-send" id="mc-send">Ask</button>
        </div>
      </div>`;
    document.documentElement.appendChild(rootEl);

    dotEl = rootEl.querySelector("#mc-dot");
    statusEl = rootEl.querySelector("#mc-status");
    answersEl = rootEl.querySelector("#mc-answers");
    transcriptEl = rootEl.querySelector("#mc-feed");
    interimEl = rootEl.querySelector("#mc-interim");
    askInput = rootEl.querySelector("#mc-ask");
    badgeEl = rootEl.querySelector("#mc-badge");

    rootEl.querySelector("#mc-smaller").onclick = () => bumpScale(-0.1);
    rootEl.querySelector("#mc-bigger").onclick = () => bumpScale(0.1);
    rootEl.querySelector("#mc-collapse").onclick = (e) => {
      const collapsed = rootEl
        .querySelector(".mc-panel")
        .classList.toggle("mc-collapsed");
      e.target.textContent = collapsed ? "▸" : "▾";
      // Don't let a fixed resize height crop the header when expanding back.
      if (collapsed) rootEl.style.height = "auto";
    };
    rootEl.querySelector("#mc-hide").onclick = () => hide();
    rootEl.querySelector("#mc-send").onclick = submitAsk;
    askInput.onkeydown = (e) => e.key === "Enter" && submitAsk();
    rootEl.querySelectorAll(".mc-tab").forEach((t) => {
      t.onclick = () => switchTab(t.dataset.tab);
    });

    makeDraggable(rootEl);

    // Double-click the header to snap back to the bottom-right.
    rootEl.querySelector("#mc-header").addEventListener("dblclick", resetPosition);

    // Restore saved font scale + position.
    chrome.storage.local.get({ panelScale: 1, panelPos: null }).then((s) => {
      applyScale(s.panelScale);
      if (s.panelPos) applyPosition(s.panelPos.left, s.panelPos.top);
    });

    // Keep it on-screen if the window shrinks.
    window.addEventListener("resize", () => clampIntoView());
  }

  function applyPosition(left, top) {
    const r = rootEl.getBoundingClientRect();
    const w = r.width || 360;
    const l = Math.max(0, Math.min(left, window.innerWidth - w));
    const t = Math.max(0, Math.min(top, window.innerHeight - 40));
    rootEl.style.left = l + "px";
    rootEl.style.top = t + "px";
    rootEl.style.right = "auto";
    rootEl.style.bottom = "auto";
  }

  function clampIntoView() {
    if (!rootEl || rootEl.classList.contains("mc-hidden")) return;
    const r = rootEl.getBoundingClientRect();
    if (rootEl.style.left === "" || rootEl.style.left === "auto") return; // still default-anchored
    applyPosition(r.left, r.top);
  }

  function resetPosition() {
    rootEl.style.left = "auto";
    rootEl.style.top = "auto";
    rootEl.style.right = "16px";
    rootEl.style.bottom = "76px";
    chrome.storage.local.remove("panelPos");
  }

  let scale = 1;
  function applyScale(v) {
    scale = Math.min(2, Math.max(0.7, v));
    if (rootEl) rootEl.style.setProperty("--mc-scale", scale.toFixed(2));
  }
  function bumpScale(delta) {
    applyScale(scale + delta);
    chrome.storage.local.set({ panelScale: scale });
  }

  function switchTab(name) {
    activeTab = name;
    rootEl.querySelectorAll(".mc-tab").forEach((t) =>
      t.classList.toggle("mc-active", t.dataset.tab === name)
    );
    rootEl.querySelectorAll(".mc-pane").forEach((p) =>
      p.classList.toggle("mc-active", p.id === "mc-" + name)
    );
    if (name === "answers") {
      unseenAnswers = 0;
      updateBadge();
    }
  }

  function updateBadge() {
    if (!badgeEl) return;
    badgeEl.textContent = unseenAnswers ? String(unseenAnswers) : "";
    badgeEl.style.display = unseenAnswers ? "inline-block" : "none";
  }

  function submitAsk() {
    const q = askInput.value.trim();
    if (!q) return;
    askInput.value = "";
    switchTab("answers");
    if (MC.onManualAsk) MC.onManualAsk(q);
  }

  function setStatus(text, mode) {
    if (!statusEl) return;
    statusEl.textContent = text;
    dotEl.className = "mc-dot";
    if (mode === "live") dotEl.classList.add("mc-live");
    else if (mode === "thinking") dotEl.classList.add("mc-thinking");
    else if (mode === "warn") dotEl.classList.add("mc-warn");
  }

  // ---- Transcript feed --------------------------------------------------

  function pushTranscriptLine(speaker, text, isSelf) {
    build();
    const e = rootEl.querySelector("#mc-tempty");
    if (e) e.remove();
    const line = document.createElement("div");
    line.className = "mc-tline" + (isSelf ? " mc-self" : "");
    const who = isSelf ? "You" : speaker || "Speaker";
    line.innerHTML = `<span class="mc-who"></span><span class="mc-said"></span>`;
    line.querySelector(".mc-who").textContent = who + ": ";
    line.querySelector(".mc-said").textContent = text;
    transcriptEl.appendChild(line);
    while (transcriptEl.childElementCount > 80) transcriptEl.firstChild.remove();
    // clear the interim line now that it's finalized
    if (interimEl) interimEl.textContent = "";
    autoscroll();
  }

  function setInterim(speaker, text, isSelf) {
    build();
    const e = rootEl.querySelector("#mc-tempty");
    if (e) e.remove();
    if (!interimEl) return;
    const who = isSelf ? "You" : speaker || "Speaker";
    interimEl.textContent = `${who}: ${text}`;
    autoscroll();
  }

  function autoscroll() {
    const pane = rootEl.querySelector("#mc-transcript");
    if (pane && activeTab === "transcript") pane.scrollTop = pane.scrollHeight;
  }

  // ---- Answer cards -----------------------------------------------------

  function addCard(id, question) {
    build();
    const e = rootEl.querySelector("#mc-aempty");
    if (e) e.remove();
    const el = document.createElement("div");
    el.className = "mc-card";
    el.innerHTML = `
      <div class="mc-card-q"></div>
      <div class="mc-card-a"></div>
      <div class="mc-card-meta">
        <span class="mc-card-model"></span>
        <button class="mc-copy">Copy</button>
        <button class="mc-dismiss">Dismiss</button>
      </div>`;
    el.querySelector(".mc-card-q").textContent = question ? `“${question}”` : "";
    const answerEl = el.querySelector(".mc-card-a");
    el.querySelector(".mc-copy").onclick = () =>
      navigator.clipboard.writeText(answerEl.textContent || "");
    el.querySelector(".mc-dismiss").onclick = () => removeCard(id);
    answersEl.prepend(el);
    cards.set(id, { el, answerEl, modelEl: el.querySelector(".mc-card-model") });
    while (cards.size > 8) {
      const oldest = [...cards.keys()][0];
      cards.get(oldest)?.el.remove();
      cards.delete(oldest);
    }
    if (activeTab !== "answers") {
      unseenAnswers++;
      updateBadge();
    }
    return id;
  }

  function appendAnswer(id, chunk) {
    const c = cards.get(id);
    if (c) c.answerEl.textContent += chunk;
  }
  function setAnswer(id, text) {
    const c = cards.get(id);
    if (c) c.answerEl.textContent = text;
  }
  function setCardModel(id, label) {
    const c = cards.get(id);
    if (c) c.modelEl.textContent = label;
  }
  function removeCard(id) {
    const c = cards.get(id);
    if (c) {
      c.el.remove();
      cards.delete(id);
    }
  }

  // ---- Window controls --------------------------------------------------

  function show() {
    build();
    rootEl.classList.remove("mc-hidden");
  }
  function hide() {
    if (rootEl) rootEl.classList.add("mc-hidden");
  }
  function toggle() {
    build();
    rootEl.classList.toggle("mc-hidden");
  }

  // Whole panel is a drag surface. We only skip interactive controls (so
  // buttons/inputs still work) and the bottom-right resize grip.
  function makeDraggable(target) {
    const SKIP = "button, input, select, textarea, a, label";
    let sx, sy, ox, oy, dragging = false;

    target.addEventListener("mousedown", (e) => {
      if (e.button !== 0) return;
      if (e.target.closest(SKIP)) return;
      const r = target.getBoundingClientRect();
      // leave the ~20px bottom-right corner to the native resize handle
      if (e.clientX > r.right - 20 && e.clientY > r.bottom - 20) return;
      dragging = true;
      sx = e.clientX;
      sy = e.clientY;
      ox = r.left;
      oy = r.top;
      // switch from bottom/right anchoring to top/left so it follows the mouse
      target.style.left = r.left + "px";
      target.style.top = r.top + "px";
      target.style.right = "auto";
      target.style.bottom = "auto";
      document.body.style.userSelect = "none";
      e.preventDefault();
    });

    window.addEventListener("mousemove", (e) => {
      if (!dragging) return;
      const r = target.getBoundingClientRect();
      let nl = ox + (e.clientX - sx);
      let nt = oy + (e.clientY - sy);
      nl = Math.max(0, Math.min(nl, window.innerWidth - r.width));
      nt = Math.max(0, Math.min(nt, window.innerHeight - 40)); // keep header reachable
      target.style.left = nl + "px";
      target.style.top = nt + "px";
    });

    window.addEventListener("mouseup", () => {
      if (!dragging) return;
      dragging = false;
      document.body.style.userSelect = "";
      const r = target.getBoundingClientRect();
      chrome.storage.local.set({ panelPos: { left: r.left, top: r.top } });
    });
  }

  MC.overlay = {
    build,
    show,
    hide,
    toggle,
    switchTab,
    setStatus,
    pushTranscriptLine,
    setInterim,
    addCard,
    appendAnswer,
    setAnswer,
    setCardModel,
    removeCard,
  };
})();
