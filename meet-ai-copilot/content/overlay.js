// The on-screen panel. Draggable, collapsible, and lives only in your own
// browser — the other participants never see it and nothing is injected into
// the Meet call itself.
(() => {
  const MC = window.MeetCopilot;

  let rootEl, bodyEl, dotEl, statusEl, askInput;
  const cards = new Map(); // id -> { el, answerEl }

  function build() {
    if (rootEl) return;
    rootEl = document.createElement("div");
    rootEl.id = "mc-root";
    rootEl.innerHTML = `
      <div class="mc-panel">
        <div class="mc-header" id="mc-header">
          <span class="mc-dot" id="mc-dot"></span>
          <span class="mc-title">AI Copilot <span class="mc-status" id="mc-status">idle</span></span>
          <button class="mc-btn" id="mc-collapse" title="Collapse">–</button>
          <button class="mc-btn" id="mc-hide" title="Hide (toggle from the toolbar icon)">✕</button>
        </div>
        <div class="mc-body" id="mc-body">
          <div class="mc-empty" id="mc-empty">
            Listening to live captions. When someone asks you something —
            or there's a moment worth adding to — a suggested answer appears here.
            <br><br>Turn on captions in Meet (CC button) if you haven't.
          </div>
        </div>
        <div class="mc-footer">
          <input class="mc-ask" id="mc-ask" placeholder="Ask Claude about this meeting…" />
          <button class="mc-send" id="mc-send">Ask</button>
        </div>
      </div>`;
    document.documentElement.appendChild(rootEl);

    bodyEl = rootEl.querySelector("#mc-body");
    dotEl = rootEl.querySelector("#mc-dot");
    statusEl = rootEl.querySelector("#mc-status");
    askInput = rootEl.querySelector("#mc-ask");

    rootEl.querySelector("#mc-collapse").onclick = () =>
      rootEl.querySelector(".mc-panel").classList.toggle("mc-collapsed");
    rootEl.querySelector("#mc-hide").onclick = () => hide();
    rootEl.querySelector("#mc-send").onclick = submitAsk;
    askInput.onkeydown = (e) => {
      if (e.key === "Enter") submitAsk();
    };

    makeDraggable(rootEl.querySelector("#mc-header"), rootEl);
  }

  function submitAsk() {
    const q = askInput.value.trim();
    if (!q) return;
    askInput.value = "";
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

  function hideEmpty() {
    const e = rootEl.querySelector("#mc-empty");
    if (e) e.remove();
  }

  // Create a new suggestion card and return its id.
  function addCard(id, question) {
    build();
    hideEmpty();
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
    el.querySelector(".mc-dismiss").onclick = () => {
      el.remove();
      cards.delete(id);
    };
    bodyEl.prepend(el);
    cards.set(id, { el, answerEl, modelEl: el.querySelector(".mc-card-model") });
    // Keep the panel from growing unbounded.
    while (cards.size > 8) {
      const oldest = [...cards.keys()][0];
      cards.get(oldest)?.el.remove();
      cards.delete(oldest);
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

  function makeDraggable(handle, target) {
    let sx, sy, ox, oy, dragging = false;
    handle.addEventListener("mousedown", (e) => {
      if (e.target.tagName === "BUTTON") return;
      dragging = true;
      sx = e.clientX;
      sy = e.clientY;
      const r = target.getBoundingClientRect();
      ox = r.left;
      oy = r.top;
      e.preventDefault();
    });
    window.addEventListener("mousemove", (e) => {
      if (!dragging) return;
      target.style.left = ox + (e.clientX - sx) + "px";
      target.style.top = oy + (e.clientY - sy) + "px";
      target.style.right = "auto";
      target.style.bottom = "auto";
    });
    window.addEventListener("mouseup", () => (dragging = false));
  }

  MC.overlay = {
    build,
    show,
    hide,
    toggle,
    setStatus,
    addCard,
    appendAnswer,
    setAnswer,
    setCardModel,
    removeCard,
  };
})();
