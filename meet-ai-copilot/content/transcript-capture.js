// Captures Google Meet's live captions straight from the DOM — no audio is
// recorded and no speech-to-text API is used, so the transcript is free.
//
// Algorithm follows the approach proven by open-source Meet transcribers
// (e.g. TranscripTonic): anchor on the caption REGION by ARIA role (stable
// across Meet redesigns and languages), observe characterData mutations,
// de-duplicate by REPLACING the growing line instead of appending, flush an
// utterance when the speaker changes / block changes / a silence elapses, and
// — critically — re-attach the observer every couple of seconds because Meet
// swaps out the whole region when captions are toggled or the language changes.
(() => {
  const MC = window.MeetCopilot;

  const FINALIZE_MS = 2000; // silence after which a line is considered done
  const SCAN_THROTTLE_MS = 120; // coalesce bursts of mutations
  const REATTACH_MS = 2000; // re-check the region node
  const NAME_MAX_LEN = 40;
  const LONG_RESET_DROP = 250; // sudden text shrink => Meet restarted the line

  let region = null;
  let observer = null;
  let reattachTimer = null;
  let scanTimer = null;

  // Current in-progress utterance.
  let buf = null; // { el, speaker, text, base, timer }
  const emittedByEl = new WeakMap(); // node -> last fully-emitted text

  // ---- Find + attach ----------------------------------------------------

  function findRegion() {
    // Primary anchor — present even when CC is visually off; language-neutral.
    let el = document.querySelector('div[role="region"][tabindex="0"]');
    if (el) return el;
    // Fallbacks for layout variations.
    el =
      document.querySelector('[role="region"][aria-label*="aption" i]') ||
      document.querySelector('[aria-live="polite"][role="region"]');
    return el || heuristicRegion();
  }

  function heuristicRegion() {
    for (const el of document.querySelectorAll("div")) {
      if (el.childElementCount < 1 || el.childElementCount > 12) continue;
      const t = (el.innerText || "").trim();
      if (t.length < 8 || t.length > 1000) continue;
      for (const c of el.children) {
        const ct = (c.innerText || "").trim();
        const nl = ct.indexOf("\n");
        if (nl > 0 && nl <= NAME_MAX_LEN && ct.length - nl > 4) return el;
      }
    }
    return null;
  }

  function attach(node) {
    detachObserver();
    region = node;
    observer = new MutationObserver(scheduleScan);
    observer.observe(region, {
      childList: true,
      subtree: true,
      characterData: true,
    });
    scheduleScan();
    MC.log("attached to caption region", region);
    if (MC.onCaptureState) MC.onCaptureState("capturing");
  }

  function detachObserver() {
    if (observer) observer.disconnect();
    observer = null;
  }

  // Meet replaces the region on CC toggle / language change, which silently
  // kills the observer. Poll and re-attach if the node changed or dropped out.
  function reattachLoop() {
    const node = findRegion();
    if (node && node !== region) {
      flush(); // don't merge pre-/post-swap text
      attach(node);
    } else if (!node) {
      region = null;
      detachObserver();
      if (MC.settings.autoCaptions) tryEnableCaptions();
      if (MC.onCaptureState) MC.onCaptureState("waiting-for-captions");
    } else if (region && !region.isConnected) {
      detachObserver();
      region = null;
    }
  }

  // ---- Parse ------------------------------------------------------------

  function parseRow(el) {
    const raw = (el.innerText || "").replace(/ /g, " ").trim();
    if (!raw) return null;
    const nl = raw.indexOf("\n");
    if (nl > 0 && nl <= NAME_MAX_LEN) {
      return {
        speaker: raw.slice(0, nl).trim(),
        text: raw.slice(nl + 1).replace(/\s+/g, " ").trim(),
      };
    }
    // No inline name — maybe the name is a preceding sibling block.
    const prev = el.previousElementSibling;
    const pt = prev && (prev.innerText || "").trim();
    if (pt && pt.length <= NAME_MAX_LEN && !pt.includes("\n")) {
      return { speaker: pt, text: raw.replace(/\s+/g, " ").trim() };
    }
    return { speaker: "", text: raw.replace(/\s+/g, " ").trim() };
  }

  // Leaf caption blocks under the region; the active one is the last.
  function activeBlock() {
    if (!region) return null;
    const nodes = region.querySelectorAll("div, span");
    let last = null;
    for (const el of nodes) {
      if (el.childElementCount > 4) continue;
      const p = parseRow(el);
      if (!p || !p.text || p.text.length < 2) continue;
      last = { el, speaker: p.speaker, text: p.text };
    }
    return last;
  }

  // ---- Buffer / finalize ------------------------------------------------

  function scheduleScan() {
    if (scanTimer) return;
    scanTimer = setTimeout(() => {
      scanTimer = null;
      scan();
    }, SCAN_THROTTLE_MS);
  }

  function scan() {
    const active = activeBlock();
    if (!active) return;

    const changedTarget =
      !buf || buf.el !== active.el || buf.speaker !== active.speaker;

    if (changedTarget) {
      flush(); // finalize whatever we had
      const prior = emittedByEl.get(active.el) || "";
      // If this node was reused for the same continuing turn, suppress the
      // already-emitted prefix; if reused for a new turn, prior won't match.
      const base = active.text.startsWith(prior) ? prior : "";
      buf = { el: active.el, speaker: active.speaker, text: active.text, base, timer: null };
    } else {
      // Same speaker + node: the line is being rewritten in place.
      if (active.text.length - buf.text.length < -LONG_RESET_DROP) {
        flush();
        buf = { el: active.el, speaker: active.speaker, text: active.text, base: "", timer: null };
      } else {
        buf.text = active.text; // replace, never append
      }
    }

    clearTimeout(buf.timer);
    buf.timer = setTimeout(flush, FINALIZE_MS);
  }

  function flush() {
    if (!buf) return;
    clearTimeout(buf.timer);
    const b = buf;
    buf = null;
    const remainder = b.text.startsWith(b.base) ? b.text.slice(b.base.length) : b.text;
    const text = remainder.trim();
    emittedByEl.set(b.el, b.text);
    if (text) emit(b.speaker, text);
  }

  function emit(speaker, text) {
    const name = (speaker || "").trim();
    const self = isSelf(name);
    const utt = { speaker: name, text, isSelf: self, ts: Date.now() };
    MC.transcript.push(utt);
    if (MC.transcript.length > 400) MC.transcript.shift();
    MC.log("utterance", self ? "(you)" : name || "?", "→", text);
    if (MC.onUtterance) MC.onUtterance(utt);
  }

  function isSelf(name) {
    if (!name) return false;
    const n = name.toLowerCase();
    if (n === "you") return true;
    const me = (MC.settings.userName || "").trim().toLowerCase();
    if (!me) return false;
    return n === me || n.includes(me) || me.includes(n);
  }

  // ---- Auto-enable captions (optional) ----------------------------------

  function tryEnableCaptions() {
    // Meet's CC button carries a Material-symbols ligature; match on the text,
    // not a class, so it survives redesigns.
    for (const el of document.querySelectorAll(".google-symbols, .material-icons, .material-symbols-outlined")) {
      if ((el.textContent || "").trim() === "closed_caption_off") {
        const btn = el.closest("button") || el.parentElement;
        if (btn) {
          btn.click();
          MC.log("auto-enabled captions");
          return true;
        }
      }
    }
    return false;
  }

  // ---- Public -----------------------------------------------------------

  function start() {
    if (reattachTimer) return;
    if (MC.settings.autoCaptions) setTimeout(tryEnableCaptions, 1500);
    const node = findRegion();
    if (node) attach(node);
    else if (MC.onCaptureState) MC.onCaptureState("waiting-for-captions");
    reattachTimer = setInterval(reattachLoop, REATTACH_MS);
  }

  function stop() {
    detachObserver();
    if (reattachTimer) clearInterval(reattachTimer);
    reattachTimer = null;
    if (scanTimer) clearTimeout(scanTimer);
    scanTimer = null;
    region = null;
    buf = null;
    if (MC.onCaptureState) MC.onCaptureState("stopped");
  }

  MC.capture = { start, stop, _enableCaptions: tryEnableCaptions };
})();
