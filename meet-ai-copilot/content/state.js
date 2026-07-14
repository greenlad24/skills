// Shared state + settings for all content-script modules.
// Content scripts declared in the same manifest entry share one isolated-world
// scope, so we hang everything off a single global namespace.
(() => {
  const MC = (window.MeetCopilot = window.MeetCopilot || {});

  MC.DEFAULTS = {
    enabled: true,
    apiKey: "",
    userName: "", // your display name in Meet, used to tell "you" from "them"
    userContext: "", // background about you, so answers are tailored
    answerModel: "claude-sonnet-5",
    gateModel: "claude-haiku-4-5",
    useGate: true, // cheap Haiku pass decides whether the pricey model runs
    autoSuggest: true, // surface answers without being asked
    autoCaptions: true, // auto-click Meet's CC button when it's off
    minSecondsBetweenCalls: 8, // debounce the paid API
    maxTranscriptChars: 6000, // rolling context window sent to Claude
    language: "auto",
  };

  MC.settings = { ...MC.DEFAULTS };

  MC.loadSettings = async () => {
    const stored = await chrome.storage.local.get(Object.keys(MC.DEFAULTS));
    MC.settings = { ...MC.DEFAULTS, ...stored };
    return MC.settings;
  };

  // React to settings changes made in the popup/options while a call is open.
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== "local") return;
    for (const [k, { newValue }] of Object.entries(changes)) {
      if (k in MC.DEFAULTS) MC.settings[k] = newValue;
    }
    if (MC.onSettingsChanged) MC.onSettingsChanged(changes);
  });

  // Rolling transcript: array of finalized utterances.
  // { speaker, text, isSelf, ts }
  MC.transcript = [];

  MC.transcriptText = () => {
    let out = MC.transcript
      .map((u) => `${u.isSelf ? "You" : u.speaker || "Them"}: ${u.text}`)
      .join("\n");
    const max = MC.settings.maxTranscriptChars;
    if (out.length > max) out = out.slice(out.length - max);
    return out;
  };

  MC.log = (...a) => console.debug("%c[MeetCopilot]", "color:#7c6cf5", ...a);
})();
