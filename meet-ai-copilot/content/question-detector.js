// Cheap, local pre-filter that runs before any paid API call. Its only job is
// to drop the obvious non-events so the Haiku gate and the answer model run as
// rarely as possible. False positives are fine (the gate catches them); false
// negatives are what we avoid.
//
// Works across languages: word boundaries are Unicode-aware (so Cyrillic,
// Hebrew, etc. match), and both English and Russian trigger words are included.
// A trailing "?" is a universal signal regardless of language.
(() => {
  const MC = window.MeetCopilot;

  // Unicode letter/number boundaries — ASCII \b does NOT work for Cyrillic.
  const L = "(?<![\\p{L}\\p{N}])";
  const R = "(?![\\p{L}\\p{N}])";
  const rx = (body) => new RegExp(L + "(?:" + body + ")" + R, "iu");

  const QUESTION_WORDS = rx(
    // English
    "what|why|how|when|where|which|who|whom|whose|can|could|would|will|do|does|did|is|are|should|" +
      // Russian
      "что|почему|зачем|как|когда|где|куда|какой|какая|какое|какие|кто|кого|кому|можешь|можете|" +
      "могли|будешь|будете|есть\\s+ли|стоит\\s+ли"
  );
  const SECOND_PERSON = rx(
    // English
    "you|your|you're|you've|you'd|you'll|" +
      // Russian
      "ты|вы|вас|вам|тебя|тебе|тобой|твой|твоя|твоё|твое|твои|ваш|ваша|ваше|ваши|вами"
  );
  // Phrases that hand the floor to the listener.
  const HANDOFF =
    /(over to you|what do you think|any thoughts|your thoughts|go ahead|take it away|curious (what|to hear)|tell (me|us) (more|about)|elaborate|expand on|что (ты |вы )?думаешь|что скажешь|что скажете|тво[ёе] мнение|ваше мнение|тебе слово|вам слово|передаю слово|расскажи|расскажите|поясни|поясните)/iu;

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

    const directedQuestion =
      (hasQ || hasQWord) && (hasYou || namedYou || hasHandoff);
    const openQuestion = hasQ && words >= 3;
    const elaboratable =
      opts.autoSuggest && words >= 12 && !hasQ && (namedYou || hasYou);

    if (!directedQuestion && !openQuestion && !elaboratable) return null;

    let kind = "open_question";
    let priority = 2;
    if (directedQuestion || namedYou) {
      kind = "directed_question";
      priority = 3;
    } else if (elaboratable) {
      kind = "elaboration";
      priority = 1;
    }

    return { kind, priority, text, speaker: utt.speaker, namedYou };
  }

  function mentionsUser(text) {
    const me = (MC.settings.userName || "").trim();
    if (!me) return false;
    const first = me.split(/\s+/)[0];
    if (!first || first.length < 2) return false;
    try {
      return rx(escapeRe(first)).test(text);
    } catch {
      return text.toLowerCase().includes(first.toLowerCase());
    }
  }

  function escapeRe(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  MC.detector = { evaluate };
})();
