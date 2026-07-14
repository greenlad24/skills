const FIELDS = ["enabled", "apiKey", "userName", "answerModel", "autoSuggest", "useGate"];
const DEFAULTS = {
  enabled: true,
  apiKey: "",
  userName: "",
  answerModel: "claude-sonnet-5",
  autoSuggest: true,
  useGate: true,
};

const $ = (id) => document.getElementById(id);

async function load() {
  const s = { ...DEFAULTS, ...(await chrome.storage.local.get(Object.keys(DEFAULTS))) };
  $("enabled").checked = s.enabled;
  $("apiKey").value = s.apiKey;
  $("userName").value = s.userName;
  $("answerModel").value = s.answerModel;
  $("autoSuggest").checked = s.autoSuggest;
  $("useGate").checked = s.useGate;
  if (s.apiKey) $("keyHint").textContent = "Key saved. Stored locally only.";
}

async function save() {
  const data = {
    enabled: $("enabled").checked,
    apiKey: $("apiKey").value.trim(),
    userName: $("userName").value.trim(),
    answerModel: $("answerModel").value,
    autoSuggest: $("autoSuggest").checked,
    useGate: $("useGate").checked,
  };
  await chrome.storage.local.set(data);
  const el = $("saved");
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 1200);
}

$("save").onclick = save;
// Persist the enabled toggle immediately so it takes effect without Save.
$("enabled").onchange = () => chrome.storage.local.set({ enabled: $("enabled").checked });

$("toggle").onclick = async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab?.id && /https:\/\/meet\.google\.com\//.test(tab.url || "")) {
    chrome.tabs.sendMessage(tab.id, { type: "toggle-panel" }, () => void chrome.runtime.lastError);
  }
};

$("opts").onclick = (e) => {
  e.preventDefault();
  chrome.runtime.openOptionsPage();
};

load();
