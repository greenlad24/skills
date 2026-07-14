const DEFAULTS = {
  apiKey: "",
  userName: "",
  userContext: "",
  language: "auto",
  answerModel: "claude-sonnet-5",
  gateModel: "claude-haiku-4-5",
  useGate: true,
  autoSuggest: true,
  autoCaptions: true,
  minSecondsBetweenCalls: 8,
  maxTranscriptChars: 6000,
};

const $ = (id) => document.getElementById(id);
const CHECKS = ["useGate", "autoSuggest", "autoCaptions"];
const NUMS = ["minSecondsBetweenCalls", "maxTranscriptChars"];

async function load() {
  const s = { ...DEFAULTS, ...(await chrome.storage.local.get(Object.keys(DEFAULTS))) };
  for (const [k, v] of Object.entries(s)) {
    const el = $(k);
    if (!el) continue;
    if (CHECKS.includes(k)) el.checked = !!v;
    else el.value = v;
  }
}

async function save() {
  const data = {};
  for (const k of Object.keys(DEFAULTS)) {
    const el = $(k);
    if (!el) continue;
    if (CHECKS.includes(k)) data[k] = el.checked;
    else if (NUMS.includes(k)) data[k] = Number(el.value) || DEFAULTS[k];
    else data[k] = el.value.trim ? el.value.trim() : el.value;
  }
  await chrome.storage.local.set(data);
  const el = $("saved");
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 1400);
}

$("save").onclick = save;
load();
