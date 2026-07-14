// Cheap, local pre-filter that runs before any paid API call.
// Its job is only to throw away the obvious non-events so the Haiku gate and
// the answer model run as rarely as possible. False positives are fine here
// (the gate catches them); false negatives are what we avoid.
(() => {
  const MC = window.MeetCopilot;

  const QUESTION_WORDS =
    /\b(what|why|how|when|where|which|who|whom|whose|can|could|would|will|do|does|did|is|are|should|have|has|any thoughts|thoughts on|your take|walk (me|us) through)\b/i;
  const SECOND_PERSON = /\b(you|your|you're|you've|you'd|you'll)\b/i;
  // Phrases that hand the floor to the listener.
  const HANDOFF =
    /\b(over to you|what do you think|any thoughts|your thoughts|go ahead|take it away|curious (what|to hear)|tell (me|us) (more|about)|elaborate|expand on)\b/i;

  // Returns a small object describing why this utterance might need a reply,
  // or null to drop it entirely.
  function evaluate(utt, opts = {}) {
    if (!utt || utt.isSelf) return null; // never react to your own words
    const text = (utt.text || "").trim();
    if (text.length < 6) return null;

    const words = text.split(/\s+/).length;
    const hasQ = text.includes("?");
    const hasQWord = QUESTION_WORDS.test(text);
    const hasYou = SECOND_PERSON.test(text);
    const hasHandoff = HANDOFF.test(text);
    const namedYou = mentionsUser(text);

    // A directed question is the strongest signal.
    const directedQuestion = (hasQ || hasQWord) && (hasYou || namedYou || hasHandoff);
    // A general question to the room is a medium signal.
    const openQuestion = hasQ && words >= 3;
    // A substantive statement you could enrich — only when auto-suggest is on.
    const elaboratable =
      opts.autoSuggest && words >= 12 && !hasQ && (namedYou || hasYou);

    if (!directedQuestion && !openQuestion && !elaboratable) return null;

    let kind = "open_question";
    let priority = 1;
    if (directedQuestion || namedYou) {
      kind = "directed_question";
      priority = 3;
    } else if (elaboratable) {
      kind = "elaboration";
      priority = 1;
    } else {
      priority = 2;
    }

    return { kind, priority, text, speaker: utt.speaker, namedYou };
  }

  function mentionsUser(text) {
    const me = (MC.settings.userName || "").trim();
    if (!me) return false;
    const first = me.split(/\s+/)[0];
    if (!first || first.length < 2) return false;
    return new RegExp(`\\b${escapeRe(first)}\\b`, "i").test(text);
  }

  function escapeRe(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  MC.detector = { evaluate };
})();
