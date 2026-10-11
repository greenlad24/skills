/* Thai TikTok Studio — single-page UI (vanilla JS, no build step, works in Safari 15+).
 * Every user-facing string goes through the t() function — see i18n.js and /static/lang/*.json.
 * Screens (hash routes): #/home · #/new · #/p/<product>/<step> · #/schedule
 */
const $ = (s, el) => (el || document).querySelector(s);
const $$ = (s, el) => Array.prototype.slice.call((el || document).querySelectorAll(s));
const esc = escHtml;
const clone = (o) => JSON.parse(JSON.stringify(o));
const state = { view: "home", pid: null, project: null, step: "scripts", settings: {}, health: {}, projects: [],
  polls: {}, newFiles: [], sched: null, modalFn: null, dialogFn: null, timers: [] };

const STEPS = [
  { key: "scripts", icon: "📝" }, { key: "film", icon: "🎬" }, { key: "upload", icon: "📤" },
  { key: "make", icon: "✨" }, { key: "post", icon: "📅" },
];
const STYLE_KEYS = ["bouncy", "punchy", "smooth", "playful", "minimal"];

/* ---------------- helpers ---------------- */
async function api(path, opts) {
  const o = Object.assign({}, opts || {});
  if (o.json !== undefined) { o.body = JSON.stringify(o.json); o.headers = { "Content-Type": "application/json" }; delete o.json; }
  const r = await fetch(path, o);
  const data = await r.json().catch(() => ({}));
  if (r.status === 401) { location.href = "/login"; throw new Error("Please log in"); }
  if (!r.ok) { const e = new Error(data.error || `HTTP ${r.status}`); e.status = r.status; throw e; }
  return data;
}
const ERR_MAP = [
  [/log in/i, "err.login"], [/Failed to fetch|NetworkError|Load failed|network/i, "err.offline"],
  [/Paste a product name/i, "err.needProduct"], [/already running/i, "err.renderRunning"],
  [/Folders open only|Open this folder manually/i, "err.folder"], [/^Not found|HTTP 404/i, "err.notFound"],
  [/CSV|transcripts/i, "err.csv"], [/cloudinary/i, "err.cloudinary"], [/postpeer|api key|unauthori|401|403/i, "err.postpeer"],
  [/json|parse|Unexpected token/i, "err.paste"],
];
/* Turn any technical error into a plain message + what to do next; the raw text is shown small. */
function friendly(e, fallbackKey) {
  const msg = String((e && e.message) || e || "");
  const hit = ERR_MAP.find((m) => m[0].test(msg));
  return { text: tt(hit ? hit[1] : (fallbackKey || "err.generic")), detail: msg };
}
function toast(html, ms, kind) {
  const el = $("#toast");
  el.innerHTML = html; el.className = "toast" + (kind ? " " + kind : "");
  clearTimeout(el._h); el._h = setTimeout(() => el.classList.add("hidden"), ms || 2800);
}
function errToast(e, fallbackKey) {
  const f = friendly(e, fallbackKey);
  const d = f.detail && f.detail.length < 300 ? `<small>${esc(t("err.details"))}: ${esc(f.detail.slice(0, 160))}</small>` : "";
  toast(`<b>😕 ${esc(f.text)}</b>${d}`, 7000, "bad");
}
const fmtSize = (b) => b > 1e9 ? (b / 1e9).toFixed(1) + " GB" : b > 1e6 ? (b / 1e6).toFixed(1) + " MB" : Math.round(b / 1e3) + " KB";
const P = () => `/api/projects/${encodeURIComponent(state.pid)}`;
const F = (rel) => `/files/${encodeURIComponent(state.pid)}/${rel.split("/").map(encodeURIComponent).join("/")}`;
const statusLabel = (s) => tOr("status." + s, s);
async function copyText(txt) {
  try { await navigator.clipboard.writeText(txt); }
  catch (e) {  // some app windows block the clipboard API — fall back to a hidden textarea
    const ta = document.createElement("textarea"); ta.value = txt; document.body.appendChild(ta);
    ta.select(); document.execCommand("copy"); ta.remove();
  }
}
function dnd(el, cb) {
  el.addEventListener("dragover", (e) => { e.preventDefault(); el.classList.add("over"); });
  el.addEventListener("dragleave", () => el.classList.remove("over"));
  el.addEventListener("drop", (e) => { e.preventDefault(); el.classList.remove("over"); cb(Array.prototype.slice.call(e.dataTransfer.files)); });
}
function clearTimers() { state.timers.forEach((x) => clearInterval(x)); state.timers = []; }

/* ---------------- modal / dialog / confirm ---------------- */
function openModal(fn, wide) {
  state.modalFn = fn;
  $("#modal .modal-box").classList.toggle("wide", !!wide);
  fn(); $("#modal").classList.remove("hidden");
  document.body.classList.add("noscroll");
  const f = $("#modal .modal-box"); f.scrollTop = 0;
}
function setModal(html) { $("#modalBody").innerHTML = html; }
function closeModal() {
  $("#modal").classList.add("hidden"); state.modalFn = null; document.body.classList.remove("noscroll");
  if (state.onModalClose) { const f = state.onModalClose; state.onModalClose = null; f(); }
}
$("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") closeModal(); });
$("#modalX").onclick = closeModal;
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  if (!$("#dialog").classList.contains("hidden")) $("#dlgNo").click(); else if (!$("#modal").classList.contains("hidden")) closeModal();
});
/* Friendly confirm: ask({ title, text, ok, danger }) → Promise<boolean>. Keys, not text, so it re-translates. */
function ask(o) {
  return new Promise((resolve) => {
    const render = () => {
      $("#dialogBody").innerHTML = `<div class="dlg-ico" aria-hidden="true">${o.danger ? "⚠️" : "🤔"}</div>
        <h2>${t(o.title, o.vars)}</h2>${o.text ? `<p class="muted">${t(o.text, o.vars)}</p>` : ""}
        <div class="dlg-btns"><button class="btn ghost" id="dlgNo">${t("common.no")}</button>
        <button class="btn ${o.danger ? "danger-solid" : "primary"}" id="dlgYes">${t(o.ok || "common.yes")}</button></div>`;
      $("#dlgNo").onclick = () => done(false); $("#dlgYes").onclick = () => done(true);
    };
    const done = (v) => { $("#dialog").classList.add("hidden"); state.dialogFn = null; resolve(v); };
    state.dialogFn = render; render();
    $("#dialog").classList.remove("hidden"); $("#dlgYes").focus();
  });
}

/* ---------------- language switch (instant, keeps state) ---------------- */
function snapshot() {
  const m = {};
  $$("#main input[id], #main textarea[id], #main select[id], #modal input[id], #modal textarea[id], #modal select[id]").forEach((el) => {
    if (el.type === "file") return;
    m[el.id] = el.type === "checkbox" || el.type === "radio" ? el.checked : el.value;
  });
  $$("details[id]").forEach((d) => { m["$" + d.id] = d.open; });
  return m;
}
function restore(m) {
  Object.keys(m).forEach((k) => {
    if (k[0] === "$") { const d = document.getElementById(k.slice(1)); if (d) d.open = m[k]; return; }
    const el = document.getElementById(k);
    if (!el || el.type === "file" || el.classList.contains("lang-sel")) return;
    if (el.type === "checkbox" || el.type === "radio") el.checked = m[k]; else el.value = m[k];
    if (el.dataset.sync) el.dispatchEvent(new Event("change"));
  });
}
async function setLanguage(lang, persist) {
  const snap = snapshot(), y = window.scrollY, my = $("#modal .modal-box").scrollTop;
  applyLang(lang);
  renderChrome();
  renderView();
  if (!$("#updBar").classList.contains("hidden")) checkUpdate();   // re-translate the update banner
  if (state.modalFn) state.modalFn();
  if (state.dialogFn) state.dialogFn();
  restore(snap);
  window.scrollTo(0, y); $("#modal .modal-box").scrollTop = my;
  if (persist) { try { state.settings = await api("/api/settings", { method: "POST", json: { language: I18N.lang } }); } catch (e) { /* offline: localStorage still has it */ } }
}
$("#langSel").onchange = (e) => setLanguage(e.target.value, true);

/* ---------------- boot + routing ---------------- */
async function boot() {
  try { await loadI18n(); } catch (e) { /* keys will show; still usable */ }
  applyLang(storedLang() || "th");
  try {
    state.health = await api("/api/health");
    if (state.health.server) document.body.classList.add("server");
  } catch (e) { state.health = { offline: true }; }
  try { state.settings = await api("/api/settings"); } catch (e) { state.settings = {}; }
  if (!storedLang() && state.settings.language) applyLang(state.settings.language);
  else if (state.settings.language !== I18N.lang) api("/api/settings", { method: "POST", json: { language: I18N.lang } }).catch(() => {});
  await loadProjects();
  renderChrome();
  window.addEventListener("hashchange", route);
  await route();
  if (!state.settings.onboarded) showOnboarding(0);
  checkUpdate();
  setInterval(checkUpdate, 10 * 60 * 1000);
}

/* ---------------- self-update banner (Mac app) ---------------- */
async function checkUpdate() {
  let u;
  try { u = await api("/api/update"); } catch (e) { return; }
  const bar = $("#updBar");
  if (!u.enabled || !u.ready || bar.dataset.dismissed === u.ready) { bar.classList.add("hidden"); return; }
  bar.innerHTML = `<span>🎉 ${t("upd.ready", { v: u.ready })}</span>
    <button class="btn primary" id="updRestart">${t("upd.restart")}</button>
    <button class="btn ghost" id="updLater">${t("upd.later")}</button>`;
  bar.classList.remove("hidden");
  $("#updLater").onclick = () => { bar.dataset.dismissed = u.ready; bar.classList.add("hidden"); };
  $("#updRestart").onclick = async () => {
    try { await api("/api/update/restart", { method: "POST" }); bar.innerHTML = `<span>${t("upd.restarting")}</span>`; }
    catch (e) { bar.innerHTML = `<span>${t("upd.manual")}</span>`; }
  };
}
$("#btnHelp").onclick = () => showOnboarding(0);
$("#btnSettings").onclick = showSettings;

function parseHash() {
  const h = location.hash.slice(1);
  if (!h || h === "/home" || h === "/") return { view: "home" };
  if (h === "/new") return { view: "new" };
  if (h === "/schedule" || h === "schedule") return { view: "schedule" };
  if (h.indexOf("/p/") === 0) { const parts = h.split("/"); return { view: "project", pid: decodeURIComponent(parts[2] || ""), step: parts[3] }; }
  return { view: "project", pid: decodeURIComponent(h) };  // old links: #<product id>
}
function go(hash) { if (location.hash === hash) route(); else location.hash = hash; }
const projHash = (pid, step) => `#/p/${encodeURIComponent(pid)}/${step || "scripts"}`;
async function route() {
  clearTimers();
  const r = parseHash();
  state.view = r.view;
  if (r.view !== "project") { state.pid = null; state.project = null; }
  renderChrome();
  window.scrollTo(0, 0);
  if (r.view === "home") return showHome();
  if (r.view === "new") return renderNew();
  if (r.view === "schedule") return showScheduler();
  return openProject(r.pid, r.step);
}
function renderView() {
  if (state.view === "home") renderHome();
  else if (state.view === "new") renderNew(true);
  else if (state.view === "schedule") { if (state.sched) renderScheduler(); }
  else if (state.project) renderProject();
}

async function loadProjects() {
  try { state.projects = await api("/api/projects"); } catch (e) { state.projects = state.projects || []; }
  renderSidebar();
}

/* ---------------- chrome: sidebar (desktop) + bottom nav (phone) ---------------- */
function renderChrome() {
  renderSidebar();
  const v = state.view;
  const item = (hash, ico, key, on, extra) => `<a href="${hash}" class="bn ${on ? "on" : ""} ${extra || ""}" ${on ? 'aria-current="page"' : ""}><span class="bn-ico" aria-hidden="true">${ico}</span><span>${t(key)}</span></a>`;
  $("#bottomnav").innerHTML = item("#/home", "🏠", "nav.home", v === "home" || v === "project")
    + item("#/new", "＋", "nav.newShort", v === "new", "bn-new") + item("#/schedule", "📅", "nav.schedule", v === "schedule");
}
function renderSidebar() {
  const v = state.view;
  const link = (hash, ico, key, on) => `<a href="${hash}" class="side-link ${on ? "on" : ""}" ${on ? 'aria-current="page"' : ""}><span aria-hidden="true">${ico}</span> ${t(key)}</a>`;
  const list = state.projects.map((p) => `<li><a href="${projHash(p.id)}" class="side-prod ${p.id === state.pid ? "on" : ""}">
      <span class="sp-name">${esc(p.name)}</span><span class="sp-st">${statusLabel(p.status)}</span></a></li>`).join("");
  $("#sidebar").innerHTML = `<a href="#/new" class="btn primary wide">＋ ${t("nav.new")}</a>
    ${link("#/home", "🏠", "nav.home", v === "home")}${link("#/schedule", "📅", "nav.schedule", v === "schedule")}
    <div class="side-title">${t("nav.myProducts")}</div>
    <ul class="side-list">${list || `<li class="muted side-empty">${t("nav.noProducts")}</li>`}</ul>`;
}
function healthBanner() {
  const h = state.health;
  if (h.offline) return `<div class="banner bad">📡 ${t("health.offline")}</div>`;
  if (h.ffmpeg === false) return `<div class="banner warn">⚠️ ${t("health.noEditor")}</div>`;
  return "";
}

/* ---------------- home ---------------- */
async function showHome() {
  await loadProjects();
  state.homeProject = null;
  renderHome();
  const latest = state.projects[0];
  if (latest) {
    try { state.homeProject = await api(`/api/projects/${encodeURIComponent(latest.id)}`); } catch (e) { state.homeProject = null; }
    if (state.view === "home") renderHome();
  }
}
function journeyHtml(at) {
  return `<ol class="journey" aria-label="${tt("home.howItWorks")}">${STEPS.map((s, i) => `<li class="${at != null && i < at ? "done" : at === i ? "now" : ""}">
    <span class="j-ico" aria-hidden="true">${at != null && i < at ? "✓" : s.icon}</span><span class="j-lbl">${t("step." + s.key)}</span></li>`).join("")}</ol>`;
}
function renderHome() {
  const ps = state.projects;
  const hp = state.homeProject;
  let main = "";
  if (!ps.length) {
    main = `<section class="card empty">
      <div class="empty-art" aria-hidden="true">🛍️<span>✨</span></div>
      <h2>${t("home.emptyTitle")}</h2><p class="muted">${t("home.emptyText")}</p>
      <a href="#/new" class="btn primary big">＋ ${t("home.emptyBtn")}</a></section>
      <section class="card"><h3>${t("home.howItWorks")}</h3>${journeyHtml(null)}</section>`;
  } else {
    let cont = "";
    if (hp) {
      const n = nextStep(hp);
      cont = `<section class="card continue">
        <div class="eyebrow">${t("home.continue")}</div>
        <h2>${esc(hp.meta.name)}</h2>${journeyHtml(n.at)}
        <p class="next-text">👉 ${t(n.msg, n.vars)}</p>
        <a class="btn primary big" href="${projHash(hp.meta.id, STEPS[Math.min(n.at, 3)].key)}">${t("home.continueBtn")} →</a></section>`;
    }
    main = `${cont}
      <div class="quick">
        <a href="#/new" class="quick-card"><span class="q-ico" aria-hidden="true">➕</span><b>${t("home.quickNew")}</b><span class="muted">${t("home.quickNewSub")}</span></a>
        <a href="#/schedule" class="quick-card"><span class="q-ico" aria-hidden="true">📅</span><b>${t("home.quickSched")}</b><span class="muted">${t("home.quickSchedSub")}</span></a>
      </div>
      <section class="card"><h2>${t("home.myProducts")}</h2>
        <ul class="prod-list">${ps.map((p) => `<li><a href="${projHash(p.id)}" class="prod-row">
          <span class="pr-ico" aria-hidden="true">${p.status === "planned" ? "📦" : p.status === "error" ? "⚠️" : "⏳"}</span>
          <span class="pr-txt"><b>${esc(p.name)}</b><span class="muted">${statusLabel(p.status)}</span></span><span class="chev" aria-hidden="true">›</span></a></li>`).join("")}</ul></section>`;
  }
  $("#main").innerHTML = `${healthBanner()}<div class="page-head"><h1>${t("home.hello")}</h1><p class="muted">${t("home.sub")}</p></div>${main}`;
}

/* ---------------- new product ---------------- */
function providerLabel() {
  const s = state.settings, prov = s.provider;
  return prov === "manual" ? t("prov.manual.short") : prov === "openai" ? t("prov.openai.short") : prov === "claude" ? t("prov.claude.short") : t("prov.claude_code.short");
}
function renderNew(keep) {
  if (!keep) state.newFiles = [];
  $("#main").innerHTML = `${healthBanner()}
    <div class="page-head"><h1>${t("new.title")}</h1><p class="muted">${t("new.sub")}</p></div>
    <section class="card form">
      <label for="newText" class="big-label">${t("new.whatLabel")}</label>
      <textarea id="newText" rows="3" placeholder="${tt("new.whatPh")}"></textarea>
      <p class="hint">${t("new.whatHint")}</p>
      <label class="big-label">${t("new.photosLabel")} <span class="opt">${t("common.optional")}</span></label>
      <div class="drop" id="newDrop" role="button" tabindex="0"><span class="drop-ico" aria-hidden="true">🖼️</span><b>${t("new.drop")}</b><span class="muted">${t("new.dropSub")}</span>
        <input type="file" id="newFiles" accept="image/*" multiple hidden></div>
      <div id="newThumbs" class="thumbs"></div>
      <details id="dNewNotes"><summary>${t("new.moreDetails")}</summary>
        <label for="newNotes">${t("new.notesLabel")}</label>
        <textarea id="newNotes" rows="2" placeholder="${tt("new.notesPh")}"></textarea></details>
      <p class="prov-line">🤖 ${t("new.writer")} <b>${providerLabel()}</b> · <a href="#" id="lnkProv">${t("common.change")}</a></p>
    </section>
    <div class="actionbar"><button class="btn primary big wide" id="btnGenerate">✨ ${t("new.go")}</button>
      <p class="muted center small">${t("new.goHint")}</p></div>`;
  const drop = $("#newDrop"), input = $("#newFiles");
  drop.onclick = () => input.click();
  drop.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } };
  input.onchange = () => addNewFiles(Array.prototype.slice.call(input.files));
  dnd(drop, (files) => addNewFiles(files.filter((f) => f.type.indexOf("image/") === 0)));
  $("#btnGenerate").onclick = generate;
  $("#lnkProv").onclick = (e) => { e.preventDefault(); showSettings(); };
  addNewFiles([]);
}
function addNewFiles(files) {
  state.newFiles.push.apply(state.newFiles, files);
  const box = $("#newThumbs"); if (!box) return;
  box.innerHTML = state.newFiles.map((f, i) => `<div class="thumb"><img src="${URL.createObjectURL(f)}" alt="">
    <button class="thumb-x" data-rm="${i}" aria-label="${tt("common.remove")}">✕</button></div>`).join("");
  $$("[data-rm]", box).forEach((b) => (b.onclick = () => { state.newFiles.splice(+b.dataset.rm, 1); addNewFiles([]); }));
}
document.addEventListener("paste", (e) => {  // paste a screenshot straight from the clipboard
  if (!$("#newDrop")) return;
  const imgs = Array.prototype.slice.call((e.clipboardData && e.clipboardData.files) || []).filter((f) => f.type.indexOf("image/") === 0);
  if (imgs.length) { addNewFiles(imgs); toast(tt("new.pasted")); }
});
async function generate() {
  const text = $("#newText").value.trim();
  if (!text && !state.newFiles.length) { toast(`<b>✍️ ${t("err.needProduct")}</b>`, 4000, "bad"); $("#newText").focus(); return; }
  const fd = new FormData();
  fd.append("text", text);
  fd.append("notes", $("#newNotes").value.trim());
  state.newFiles.forEach((f) => fd.append("images", f, f.name || "screenshot.png"));
  const b = $("#btnGenerate"); b.disabled = true; b.innerHTML = `<span class="spinner sm"></span> ${t("new.starting")}`;
  try {
    const res = await api("/api/projects", { method: "POST", body: fd });
    state.newFiles = [];
    await loadProjects();
    go(projHash(res.project.id, "scripts"));
  } catch (e) { errToast(e); b.disabled = false; b.innerHTML = `✨ ${t("new.go")}`; }
}

/* ---------------- product ---------------- */
async function openProject(pid, step, quiet) {
  const changed = pid !== state.pid;
  state.pid = pid;
  try { state.project = await api(`/api/projects/${encodeURIComponent(pid)}`); }
  catch (e) { toast(`<b>😕 ${t("err.notFound")}</b>`, 4000, "bad"); go("#/home"); return; }
  if (step === "post") { go("#/schedule"); return; }
  if (step && STEPS.some((s) => s.key === step)) state.step = step;
  else if (changed || !state.step) state.step = defaultStep(state.project);
  history.replaceState(null, "", projHash(pid, state.step));
  renderProject();
  if (!quiet) renderSidebar();
  (state.project.jobs || []).filter((j) => j.status === "running").forEach((j) => pollJob(j.id));
}
function refreshProject() { return openProject(state.pid, state.step, true); }
function defaultStep(p) { const at = nextStep(p).at; return STEPS[Math.min(at, 3)].key; }
function setStep(key) {
  if (key === "post") return go("#/schedule");
  state.step = key; history.replaceState(null, "", projHash(state.pid, key)); renderProject(); window.scrollTo(0, 0);
}

function nextStep(p) {
  const running = (p.jobs || []).find((j) => j.status === "running");
  const plan = p.plan, a = p.assign || {};
  if (running && running.kind === "plan") return { at: 0, msg: "next.writing" };
  if (running && running.kind === "render") return { at: 3, msg: "next.rendering" };
  if (!plan && p.meta.status === "waiting_for_paste") return { at: 0, msg: "next.paste" };
  if (!plan) return { at: 0, msg: "next.noPlan", act: "replan", btn: "next.noPlanBtn" };
  const shots = [];
  plan.videos.forEach((v) => v.shots.forEach((s) => shots.push(s.id)));
  const have = shots.filter((id) => a.shots && a.shots[id]).length;
  const needVo = plan.videos.filter((v) => v.audio_mode === "voiceover" && !(a.narration || {})[v.id] && !(a.vo || {})[v.id]);
  if (!p.files.length) return { at: 1, msg: "next.film", act: "film", btn: "next.filmBtn" };
  if (needVo.length) return { at: 2, msg: "next.voice", vars: { ids: needVo.map((v) => v.id).join(", ") }, act: "upload", btn: "next.uploadBtn" };
  if (have < shots.length) return { at: 2, msg: "next.missing", vars: { n: shots.length - have }, act: "upload", btn: "next.uploadBtn" };
  if (!p.renders.length) return { at: 3, msg: "next.make", act: "make", btn: "next.makeBtn" };
  return { at: 4, msg: "next.post", act: "post", btn: "next.postBtn" };
}

function renderProject() {
  const p = state.project, m = p.meta;
  const n = nextStep(p);
  const job = (p.jobs || []).slice(-1)[0];
  const showJob = job && (job.status === "running" || job.status === "error");
  const stepper = `<nav class="stepper" aria-label="${tt("step.aria")}">${STEPS.map((s, i) => {
    const cls = s.key === state.step ? "on" : i < n.at ? "done" : "";
    return `<button class="st ${cls}" data-step="${s.key}" ${s.key === state.step ? 'aria-current="step"' : ""}>
      <span class="st-dot" aria-hidden="true">${i < n.at && s.key !== state.step ? "✓" : s.icon}</span><span class="st-lbl">${t("step." + s.key)}</span></button>`;
  }).join("")}</nav>`;
  const curIdx = STEPS.findIndex((s) => s.key === state.step);
  const here = curIdx === n.at;
  const coach = curIdx > n.at || (job && job.status === "running") ? "" : `<div class="coach ${here ? "here" : ""}"><span class="coach-ico" aria-hidden="true">💡</span>
    <div class="coach-txt"><b>${t("next.label")}</b> ${t(n.msg, n.vars)}</div>
    ${n.act && !here ? `<button class="btn secondary" id="coachBtn">${t(n.btn)}</button>` : ""}</div>`;
  $("#main").innerHTML = `${healthBanner()}
    <div class="phead"><a href="#/home" class="back" aria-label="${tt("nav.back")}">‹ <span>${t("nav.myProducts")}</span></a>
      <div class="phead-row"><div class="phead-title"><h1>${esc(m.name)}</h1><span class="pill">${statusLabel(m.status)}</span></div>
      <div class="menu-wrap"><button class="iconbtn" id="btnMore" aria-haspopup="true" aria-expanded="false" aria-label="${tt("prod.more")}">⋯</button>
        <div class="menu hidden" id="moreMenu" role="menu">
          <button role="menuitem" id="mReplan">↻ ${t("prod.replan")}</button>
          <button role="menuitem" id="mFolder" class="localonly">📂 ${t("prod.folder")}</button>
          <button role="menuitem" id="mDelete" class="danger">🗑 ${t("prod.delete")}</button></div></div></div></div>
    ${stepper}
    <div id="jobBox">${showJob ? jobHtml(job) : ""}</div>
    ${coach}
    <div id="stepBody" class="step-body"></div>`;
  $$(".stepper .st").forEach((b) => (b.onclick = () => setStep(b.dataset.step)));
  const cb = $("#coachBtn"); if (cb) cb.onclick = () => coachAction(n.act);
  wireMenu();
  wireJobBox();
  const body = $("#stepBody");
  if (state.step === "scripts") renderScripts(body);
  else if (state.step === "film") renderFilm(body);
  else if (state.step === "upload") renderUpload(body);
  else renderMake(body);
}
function wireMenu() {
  const btn = $("#btnMore"), menu = $("#moreMenu");
  btn.onclick = (e) => { e.stopPropagation(); const open = menu.classList.toggle("hidden") === false; btn.setAttribute("aria-expanded", open); };
  document.addEventListener("click", () => { if (menu) menu.classList.add("hidden"); }, { once: true });
  $("#mReplan").onclick = replan;
  $("#mFolder").onclick = () => api(P() + "/reveal", { method: "POST", json: {} }).catch((er) => errToast(er));
  $("#mDelete").onclick = async () => {
    if (!(await ask({ title: "confirm.deleteProduct", text: "confirm.deleteProductText", ok: "confirm.deleteOk", danger: true, vars: { name: state.project.meta.name } }))) return;
    try { await api(P(), { method: "DELETE" }); toast(tt("prod.deleted")); await loadProjects(); go("#/home"); } catch (e) { errToast(e); }
  };
}
async function replan() {
  if (!(await ask({ title: "confirm.replan", text: "confirm.replanText", ok: "confirm.replanOk" }))) return;
  try { const r = await api(P() + "/replan", { method: "POST" }); state.step = "scripts"; await refreshProject(); pollJob(r.job.id); }
  catch (e) { errToast(e); }
}
function coachAction(act) {
  if (act === "replan") replan();
  else if (act === "post") go("#/schedule");
  else setStep(act);
}

/* ---------------- jobs (progress) ---------------- */
function jobHtml(j) {
  const pct = Math.round((j.progress || 0) * 100);
  const plan = j.kind === "plan";
  const log = `<details id="dLog"><summary>${t("job.details")}</summary><div class="log">${esc((j.log || []).join("\n"))}</div></details>`;
  if (j.status === "running") {
    const mins = Math.floor((j.elapsed || 0) / 60), secs = (j.elapsed || 0) % 60;
    return `<section class="card job running" aria-live="polite"><div class="job-head"><span class="spinner"></span>
      <div><h2>${t(plan ? "job.planTitle" : "job.renderTitle")}</h2><p class="muted">${t(plan ? "job.planWait" : "job.renderWait")}</p></div></div>
      <div class="progress" role="progressbar" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100"><i style="width:${Math.max(pct, 3)}%"></i></div>
      <div class="job-meta"><b>${pct}%</b><span class="muted">${t("job.elapsed", { m: mins, s: secs < 10 ? "0" + secs : secs })}</span></div>
      <p class="reassure">☕ ${t("job.leave")}</p>${log}</section>`;
  }
  if (j.status === "error") {
    return `<section class="card job error"><h2>😕 ${t(plan ? "job.planFailedTitle" : "job.renderFailedTitle")}</h2>
      <p>${t(plan ? "job.planFailed" : "job.renderFailed")}</p><p class="muted small">${t("err.details")}: ${esc(String(j.error || "").slice(0, 300))}</p>
      <div class="row"><button class="btn primary" id="jobRetry">↻ ${t("common.tryAgain")}</button></div>${log}</section>`;
  }
  return "";
}
function wireJobBox() {
  const r = $("#jobRetry");
  if (!r) return;
  const j = (state.project.jobs || []).slice(-1)[0];
  r.onclick = () => (j && j.kind === "render" ? setStep("make") : replan());
}
function pollJob(id) {
  if (state.polls[id]) return;
  state.polls[id] = setInterval(async () => {
    let j;
    try { j = await api(`/api/jobs/${id}`); } catch (e) { clearInterval(state.polls[id]); delete state.polls[id]; return; }
    const here = state.view === "project" && j.project_id === state.pid;
    if (here) {
      const box = $("#jobBox");
      if (box && j.status === "running") {
        const open = $("#dLog") && $("#dLog").open;
        box.innerHTML = jobHtml(j);
        if (open) { $("#dLog").open = true; const lg = $(".log", box); if (lg) lg.scrollTop = 1e9; }
      }
    }
    if (j.status !== "running") {
      clearInterval(state.polls[id]); delete state.polls[id];
      loadProjects();
      if (here) {
        if (j.kind === "render" && j.status === "done") state.step = "make";
        if (j.kind === "plan" && j.status === "done") state.step = "scripts";
        await refreshProject();
      }
      if (j.status === "done") {
        if (j.kind === "render") celebrate("celebrate.videosTitle", "celebrate.videosText", j.project_id);
        else toast(`<b>🎉 ${t(here && state.project && !state.project.plan ? "job.pasteReady" : "job.planDone")}</b>`, 4000, "good");
      } else toast(`<b>😕 ${t(j.kind === "plan" ? "job.planFailedTitle" : "job.renderFailedTitle")}</b>`, 5000, "bad");
    }
  }, 1500);
}
function celebrate(titleKey, textKey, pid) {
  openModal(() => {
    setModal(`<div class="celebrate"><div class="confetti" aria-hidden="true">${["🎉", "✨", "🎊", "⭐", "💖"].map((c, i) => `<span style="--i:${i}">${c}</span>`).join("")}</div>
      <div class="big-emoji" aria-hidden="true">🎉</div><h2>${t(titleKey)}</h2><p class="muted">${t(textKey)}</p>
      <div class="col-btns"><button class="btn primary big wide" id="celWatch">${t(pid ? "celebrate.watch" : "celebrate.ok")}</button>
      ${pid ? `<button class="btn secondary wide" id="celSched">📅 ${t("celebrate.schedule")}</button>` : ""}</div></div>`);
    $("#celWatch").onclick = () => { closeModal(); if (pid) { if (state.pid === pid) { setStep("make"); setTimeout(() => { const r = $("#finished"); if (r) r.scrollIntoView({ behavior: "smooth" }); }, 50); } else go(projHash(pid, "make")); } };
    const s = $("#celSched"); if (s) s.onclick = () => { closeModal(); go("#/schedule"); };
  });
}

/* ---------------- step 1: scripts ---------------- */
function scoreOf(s) {
  if (!s) return 0;
  if (s.total) return Math.round(s.total);
  const keys = ["hook_strength", "pain_or_desire", "proof_demo", "offer_clarity", "trend_fit", "filmability", "compliance_safety"];
  const vals = keys.map((k) => +s[k] || 0);
  return Math.round(vals.reduce((a, b) => a + b, 0) / keys.length * 10);
}
function renderScripts(body) {
  const p = state.project;
  if (!p.plan) {
    if (p.meta.status === "waiting_for_paste") return renderManual(body);
    const running = (p.jobs || []).some((j) => j.status === "running" && j.kind === "plan");
    body.innerHTML = running ? `<section class="card empty"><div class="empty-art" aria-hidden="true">✍️</div><h2>${t("scripts.waitTitle")}</h2><p class="muted">${t("scripts.waitText")}</p></section>`
      : `<section class="card empty"><div class="empty-art" aria-hidden="true">📝</div><h2>${t("scripts.noneTitle")}</h2><p class="muted">${t("scripts.noneText")}</p>
        <button class="btn primary big" id="btnReplan2">↻ ${t("scripts.noneBtn")}</button></section>`;
    if ($("#btnReplan2")) $("#btnReplan2").onclick = replan;
    return;
  }
  const r = p.plan.research || {}, checks = p.checks || {};
  const sec = (key, a) => (a && a.length ? `<div class="r-sec"><h3>${t(key)}</h3><ul>${a.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>` : "");
  const pills = [r.brand, r.category].filter(Boolean).map((x) => `<span class="pill">${esc(x)}</span>`).join("")
    + (r.price_thb ? `<span class="pill y">฿${esc(r.price_thb)}</span>` : "") + (r.target_audience ? `<span class="pill">👥 ${esc(r.target_audience)}</span>` : "");
  body.innerHTML = `
    <div class="intro"><h2>${t("scripts.title", { n: p.plan.videos.length })}</h2><p class="muted">${t("scripts.sub")}</p></div>
    ${(checks.warnings || []).length ? `<div class="banner warn">⚠️ ${checks.warnings.map(esc).join("<br>⚠️ ")}</div>` : ""}
    ${p.plan.videos.map((v, vi) => videoCard(v, vi, (checks.compliance || {})[v.id] || [])).join("")}
    <details class="card fold" id="dResearch"><summary><span>🔎 ${t("scripts.research")}</span><span class="fold-sub">${pills}</span></summary>
      <div class="grid2">${sec("research.features", r.key_features)}${sec("research.pains", r.pain_points)}${sec("research.objections", r.objections)}
        ${sec("research.proof", r.proof_points)}${sec("research.trends", r.niche_trends)}${sec("research.hooks", r.competitor_hooks)}${sec("research.compliance", r.compliance_notes)}</div>
      ${p.research_md ? `<details id="dResearchMd"><summary>${t("research.fullNotes")}</summary><div class="script">${esc(p.research_md)}</div></details>` : ""}
      ${r.sources && r.sources.length ? `<details id="dSources"><summary>${t("research.sources", { n: r.sources.length })}</summary><ul class="sources">${r.sources.map((s) => `<li><a href="${esc(s)}" target="_blank" rel="noopener">${esc(s)}</a></li>`).join("")}</ul></details>` : ""}
    </details>
    <details class="card fold advanced" id="dJson"><summary><span>🛠 ${t("adv.planJson")}</span></summary>
      <p class="muted small">${t("adv.planJsonHint")}</p>
      <textarea id="planJson" rows="14" class="mono">${esc(JSON.stringify(p.plan, null, 2))}</textarea>
      <div class="row"><button class="btn" id="btnSaveJson">💾 ${t("common.save")}</button></div></details>
    <div class="actionbar"><button class="btn primary big wide" id="toFilm">${t("scripts.toFilm")} →</button>
      <a class="btn ghost wide" href="${F("filming_pack.html")}" target="_blank" rel="noopener">🖨 ${t("scripts.openPack")}</a></div>`;
  $$("[data-save]", body).forEach((b) => (b.onclick = () => saveBeats(+b.dataset.save)));
  $$("[data-copy-script]", body).forEach((b) => (b.onclick = async () => { await copyText(p.plan.videos[+b.dataset.copyScript].full_script_th); toast(tt("common.copied")); }));
  $("#toFilm").onclick = () => setStep("film");
  $("#btnSaveJson").onclick = async () => {
    let plan;
    try { plan = JSON.parse($("#planJson").value); } catch (e) { return errToast(e, "err.paste"); }
    try { await api(P() + "/plan", { method: "POST", json: { plan } }); toast(tt("common.saved"), 2500, "good"); refreshProject(); }
    catch (e) { errToast(e); }
  };
}
function videoCard(v, vi, flags) {
  const s = v.score || {};
  const score = scoreOf(s);
  const hard = flags.filter((f) => f.level === "hard");
  const crit = ["hook_strength", "pain_or_desire", "proof_demo", "offer_clarity", "trend_fit", "filmability", "compliance_safety"];
  const total = v.timeline.reduce((a, b) => a + b.duration, 0);
  const lbl = (k) => `data-l="${tt(k)}"`;
  return `<section class="card vcard" id="vc${vi}">
    <div class="vc-top"><span class="rank ${v.rank === 1 ? "first" : ""}">#${v.rank}</span>
      <div class="vc-title"><h3>${esc(v.title_th)}</h3>
        <div class="chips"><span class="pill">⏱ ${t("scripts.seconds", { n: Math.round(total) })}</span>
          <span class="pill">${tOr("audio." + v.audio_mode, v.audio_mode)}</span>
          ${hard.length ? `<span class="pill r">⚠️ ${t("scripts.risky", { n: hard.length })}</span>` : `<span class="pill g">✓ ${t("scripts.safe")}</span>`}
          ${v.rank === 1 ? `<span class="pill y">⭐ ${t("scripts.best")}</span>` : ""}</div></div>
      <div class="vc-score" aria-label="${tt("scripts.scoreAria", { n: score })}"><b>${score}</b><span>/100</span><div class="bar"><i style="width:${score}%"></i></div><small>${t("scripts.score")}</small></div></div>
    ${flags.length ? `<p class="banner ${hard.length ? "bad" : "warn"} small">⚠️ ${t("scripts.flagWords")} ${flags.map((f) => `“${esc(f.word)}” (${esc(f.where)})`).join(", ")}</p>` : ""}
    <div class="script-head"><h4>🗣 ${t("scripts.script")}</h4><button class="btn ghost sm" data-copy-script="${vi}">📋 ${t("common.copy")}</button></div>
    <div class="script">${esc(v.full_script_th)}</div>
    <details id="dShots${vi}"><summary>🎬 ${t("scripts.shots", { n: v.shots.length })}</summary>
      <table class="tbl-cards"><thead><tr><th>${t("tbl.shot")}</th><th>${t("tbl.size")}</th><th>${t("tbl.what")}</th><th>${t("tbl.how")}</th><th>${t("tbl.line")}</th><th>${t("tbl.min")}</th></tr></thead><tbody>
      ${v.shots.map((sh) => `<tr><td class="id">${esc(sh.id)}</td><td ${lbl("tbl.size")}>${tOr("size." + sh.shot_size, sh.shot_size.replace(/_/g, " "))}</td><td ${lbl("tbl.what")}>${esc(sh.what_to_film_th)}</td><td ${lbl("tbl.how")}>${esc(sh.how_to_film_th)}</td><td ${lbl("tbl.line")}>${esc(sh.dialogue_th) || "—"}${sh.audio === "sync" ? " 🎙" : ""}</td><td ${lbl("tbl.min")}>${t("scripts.minSec", { n: sh.min_seconds })}</td></tr>`).join("")}</tbody></table></details>
    <details id="dWhy${vi}"><summary>💡 ${t("scripts.why")}</summary>
      <p><b>${t("scripts.angle")}</b> ${esc(v.angle_en)}<br><b>${t("scripts.whyWorks")}</b> ${esc(v.why_it_works_en)}</p>
      <div class="chips"><span class="pill">${esc(String(v.format || "").replace(/_/g, " "))}</span><span class="pill">${t("scripts.hook")}: ${esc(String(v.hook_type || "").replace(/_/g, " "))}</span><span class="pill">${esc(String(v.theme || "").replace(/_/g, " "))}</span></div>
      <p class="muted small">${crit.map((c) => `${tOr("crit." + c, c.replace(/_/g, " "))} ${s[c] != null ? s[c] : "–"}`).join(" · ")}</p></details>
    <details id="dBeats${vi}"><summary>✏️ ${t("scripts.edit", { n: v.timeline.length })}</summary>
      <p class="muted small">${t("scripts.editHint")}</p>
      <table class="tbl-cards beats"><thead><tr><th>#</th><th>${t("tbl.shot")}</th><th>${t("tbl.sec")}</th><th>${t("tbl.spoken")}</th><th>${t("tbl.captions")}</th><th>${t("tbl.graphics")}</th></tr></thead><tbody>
      ${v.timeline.map((b, bi) => `<tr data-v="${vi}" data-b="${bi}"><td class="id">${bi + 1}<div class="beat-ov">${esc(b.role)} · ${esc(b.effect)}</div></td>
        <td ${lbl("tbl.shot")}><select id="b${vi}_${bi}_shot" data-f="shot_id" aria-label="${tt("tbl.shot")}">${v.shots.map((sh) => `<option ${sh.id === b.shot_id ? "selected" : ""}>${esc(sh.id)}</option>`).join("")}</select></td>
        <td ${lbl("tbl.sec")}><input id="b${vi}_${bi}_dur" data-f="duration" type="number" step="0.1" min="0.4" value="${b.duration}" class="num" aria-label="${tt("tbl.sec")}"></td>
        <td ${lbl("tbl.spoken")}><textarea id="b${vi}_${bi}_vo" data-f="vo_th" rows="2" aria-label="${tt("tbl.spoken")}">${esc(b.vo_th)}</textarea></td>
        <td ${lbl("tbl.captions")}><textarea id="b${vi}_${bi}_cap" data-f="captions" rows="2" aria-label="${tt("tbl.captions")}">${esc(b.captions.map((c) => c.text).join("\n"))}</textarea></td>
        <td ${lbl("tbl.graphics")}>${b.overlays.map((o, oi) => `<div class="beat-ov">${esc(o.type)}</div><input id="b${vi}_${bi}_o${oi}" data-o="${oi}" value="${esc(o.text)}" aria-label="${tt("tbl.graphics")}">`).join("") || '<span class="muted">—</span>'}</td></tr>`).join("")}</tbody></table>
      <div class="row"><button class="btn primary" data-save="${vi}">💾 ${t("scripts.saveEdits")}</button></div></details>
    <div class="caption-box"><b>${t("scripts.postCaption")}</b> ${esc(v.post_caption_th)} <span class="tags">${esc(v.hashtags.join(" "))}</span></div>
  </section>`;
}
async function saveBeats(vi) {
  const plan = clone(state.project.plan);
  const v = plan.videos[vi];
  $$(`tr[data-v="${vi}"]`).forEach((tr) => {
    const b = v.timeline[+tr.dataset.b];
    b.shot_id = $('[data-f="shot_id"]', tr).value;
    b.duration = parseFloat($('[data-f="duration"]', tr).value) || b.duration;
    b.vo_th = $('[data-f="vo_th"]', tr).value.trim();
    const lines = $('[data-f="captions"]', tr).value.split("\n").map((x) => x.trim()).filter(Boolean);
    b.captions = lines.map((tx, i) => ({ text: tx, highlight: ((b.captions[i] && b.captions[i].highlight) || []).filter((h) => tx.indexOf(h) >= 0) }));
    $$("[data-o]", tr).forEach((inp) => { b.overlays[+inp.dataset.o].text = inp.value; });
  });
  try { await api(P() + "/plan", { method: "POST", json: { plan } }); toast(tt("common.saved"), 2500, "good"); refreshProject(); }
  catch (e) { errToast(e); }
}
function renderManual(body) {
  const p = state.project;
  body.innerHTML = `<section class="card manual"><h2>🆓 ${t("manual.title")}</h2><p class="muted">${t("manual.sub")}</p>
    <ol class="big-steps">
      <li><b class="step-h">${t("manual.s1")}</b><button class="btn secondary big wide" id="btnCopy">📋 ${t("manual.copyBtn")}</button></li>
      <li><b class="step-h">${t("manual.s2")}</b><div class="row"><a class="btn secondary" href="https://chatgpt.com" target="_blank" rel="noopener">ChatGPT ↗</a><a class="btn secondary" href="https://claude.ai" target="_blank" rel="noopener">Claude ↗</a></div>
        <p class="muted small">${t("manual.s2hint")}${p.input && p.input.images && p.input.images.length ? " " + t("manual.attach") : ""}</p></li>
      <li><b class="step-h">${t("manual.s3")}</b><label for="pasteBox" class="sr">${t("manual.s3")}</label><textarea id="pasteBox" rows="8" placeholder="${tt("manual.pastePh")}"></textarea></li>
    </ol>
    <div class="actionbar"><button class="btn primary big wide" id="btnImport">✅ ${t("manual.import")}</button></div></section>`;
  $("#btnCopy").onclick = async () => { await copyText(p.manual_prompt); toast(`<b>✓ ${t("manual.copied")}</b>`, 3500, "good"); };
  $("#btnImport").onclick = async () => {
    if (!$("#pasteBox").value.trim()) { toast(`<b>${t("manual.empty")}</b>`, 3500, "bad"); return; }
    try { await api(P() + "/paste", { method: "POST", json: { text: $("#pasteBox").value } }); toast(`<b>🎉 ${t("manual.imported")}</b>`, 3500, "good"); state.step = "scripts"; await loadProjects(); refreshProject(); }
    catch (e) { errToast(e, "err.paste"); }
  };
}

/* ---------------- step 2: film ---------------- */
function renderFilm(body) {
  const p = state.project;
  if (!p.plan) { body.innerHTML = needPlanHtml(); wireNeedPlan(); return; }
  body.innerHTML = `
    <section class="card hero-card"><div class="hero-ico" aria-hidden="true">🖨</div><div><h2>${t("film.packTitle")}</h2><p class="muted">${t("film.packText")}</p>
      <a class="btn secondary big" href="${F("filming_pack.html")}" target="_blank" rel="noopener">🖨 ${t("film.packBtn")}</a></div></section>
    <div class="grid2">
      <section class="card"><h2>🎬 ${t("film.tipsTitle")}</h2><ul class="ticks">
        <li>${t("film.t1")}</li><li>${t("film.t2")}</li><li>${t("film.t3")}</li><li>${t("film.t4")}</li><li>${t("film.t5")}</li><li>${t("film.t6")}</li></ul></section>
      <section class="card"><h2>🎙 ${t("film.voiceTitle")}</h2><ul class="ticks">
        <li>${t("film.v1")}</li><li>${t("film.v2")}</li><li>${t("film.v3")}</li><li>${t("film.v4")}</li></ul>
        <p class="tip">${t("film.voiceTip")}</p></section></div>
    <section class="card"><h2>📋 ${t("film.listTitle")}</h2>
      ${p.plan.videos.map((v, vi) => `<details id="dFilm${vi}"><summary><b>#${v.rank} ${esc(v.title_th)}</b> · ${t("film.nShots", { n: v.shots.length })}</summary>
        <ol class="shot-list">${v.shots.map((sh) => `<li><span class="id">${esc(sh.id)}</span> ${esc(sh.what_to_film_th)}${sh.dialogue_th ? ` <span class="muted">— “${esc(sh.dialogue_th)}”</span>` : ""}</li>`).join("")}</ol></details>`).join("")}</section>
    <div class="actionbar"><button class="btn primary big wide" id="toUpload">📤 ${t("film.done")}</button></div>`;
  $("#toUpload").onclick = () => setStep("upload");
}
function needPlanHtml() {
  return `<section class="card empty"><div class="empty-art" aria-hidden="true">📝</div><h2>${t("need.planTitle")}</h2><p class="muted">${t("need.planText")}</p>
    <button class="btn primary big" id="needPlanBtn">${t("need.planBtn")}</button></section>`;
}
function wireNeedPlan() { $("#needPlanBtn").onclick = () => setStep("scripts"); }

/* ---------------- step 3: upload ---------------- */
function fileCards(list, kind) {
  return list.map((f) => `<li class="file"><span class="f-ico" aria-hidden="true">${f.kind === "audio" ? "🎵" : f.kind === "image" ? "🖼️" : "🎞️"}</span>
    <span class="f-txt"><b>${esc(f.name)}</b><span class="muted">${fmtSize(f.size)}${f.duration ? " · " + f.duration + "s" : ""}</span></span>
    <button class="iconbtn sm" data-del="${esc(f.name)}" data-kind="${kind}" aria-label="${tt("upload.delFile", { name: f.name })}">✕</button></li>`).join("");
}
function renderUpload(body) {
  const p = state.project;
  if (!p.plan) { body.innerHTML = needPlanHtml(); wireNeedPlan(); return; }
  const a = p.assign || { shots: {}, vo: {}, music: [], narration: {} };
  a.shots = a.shots || {}; a.narration = a.narration || {};
  const vids = p.files.filter((f) => f.kind === "video" || f.kind === "image");
  const auds = p.files.filter((f) => f.kind === "audio");
  const nars = p.narration || [];
  const opt = (list, sel) => `<option value="">${t("upload.none")}</option>` + list.map((f) => `<option ${f.name === sel ? "selected" : ""} value="${esc(f.name)}">${esc(f.name)}${f.duration ? ` (${f.duration}s)` : ""}</option>`).join("");
  let total = 0, have = 0;
  p.plan.videos.forEach((v) => v.shots.forEach((sh) => { total++; if (a.shots[sh.id] || (sh.shot_size === "product_photo" && p.product_images.length)) have++; }));
  const allOk = have === total;
  body.innerHTML = `
    <section class="card"><h2>🎞️ ${t("upload.clipsTitle")}</h2><p class="muted">${t("upload.clipsText")}</p>
      <button class="btn ${p.files.length ? "secondary" : "primary"} big wide" data-phone="1">📱 ${t("upload.phone")}</button>
      <div class="or"><span>${t("common.or")}</span></div>
      <div class="drop" id="footDrop" role="button" tabindex="0"><span class="drop-ico" aria-hidden="true">📂</span><b>${t("upload.drop")}</b><span class="muted">${t("upload.dropSub")}</span>
        <input type="file" id="footFiles" multiple hidden accept="video/*,image/*,audio/*"></div>
      <div id="upProg"></div>
      ${p.files.length ? `<p class="list-title">${t("upload.yourClips", { n: p.files.length })}</p><ul class="files">${fileCards(p.files, "footage")}</ul>` : `<p class="muted center">${t("upload.noClips")}</p>`}
      <div class="row localonly"><button class="btn ghost sm" id="btnFolder">📂 ${t("upload.folder")}</button><button class="btn ghost sm" id="btnRescan">↻ ${t("upload.rescan")}</button>
        <span class="muted small">${t("upload.bigFiles")}</span></div>
    </section>
    <section class="card"><h2>🎙 ${t("upload.voiceTitle")}</h2><p class="muted">${t("upload.voiceText")}</p>
      <div class="drop" id="narDrop" role="button" tabindex="0"><span class="drop-ico" aria-hidden="true">🎙</span><b>${t("upload.voiceDrop")}</b><span class="muted">${t("upload.voiceDropSub")}</span>
        <input type="file" id="narFiles" multiple hidden accept="video/*,audio/*"></div>
      <div class="row"><button class="btn secondary" data-phone="1">📱 ${t("upload.voicePhone")}</button></div>
      <div id="narProg"></div>
      ${nars.length ? `<ul class="files">${fileCards(nars, "narration")}</ul>
        <p class="list-title">${t("upload.whichVoice")}</p>
        <div class="match-list">${p.plan.videos.map((v) => `<label class="match-row"><span>#${v.rank} ${esc(v.title_th)}</span><select id="nar_${esc(v.id)}" data-nar="${esc(v.id)}">${opt(nars, a.narration[v.id])}</select></label>`).join("")}</div>`
        : `<p class="muted center">${t("upload.noVoice")}</p>`}
    </section>
    ${!p.files.length ? "" : `<section class="card"><div class="match-sum ${allOk ? "ok" : "warn"}"><span class="ms-ico" aria-hidden="true">${allOk ? "✅" : "🧩"}</span>
      <div><h2>${t("upload.matchTitle")}</h2><p>${t(allOk ? "upload.matchAll" : "upload.matchSome", { have: have, total: total })}</p></div></div>
      <details id="dMatch"><summary>${t("upload.matchOpen")}</summary>
        <p class="muted small">${t("upload.matchHint")}</p>
        <label for="musicSel">🎵 ${t("upload.music")}</label><select id="musicSel">${opt(auds, (a.music || [])[0])}</select>
        ${p.plan.videos.map((v) => `<h3>#${v.rank} ${esc(v.title_th)}</h3>
          <div class="match-list">${v.shots.map((sh) => `<label class="match-row"><span><span class="id">${esc(sh.id)}</span> ${esc(sh.what_to_film_th)}
            ${a.shots[sh.id] ? "" : (sh.shot_size === "product_photo" && p.product_images.length ? `<span class="pill">${t("upload.usesPhoto")}</span>` : `<span class="pill r">${t("upload.missing")}</span>`)}</span>
            <select id="shot_${esc(sh.id)}" data-shot="${esc(sh.id)}">${opt(vids, a.shots[sh.id])}</select></label>`).join("")}</div>`).join("")}
        ${(a.unmatched || []).length ? `<p class="muted small">${t("upload.unused")} ${a.unmatched.map(esc).join(", ")}</p>` : ""}
        <div class="row"><button class="btn" id="btnSaveAssign">💾 ${t("upload.saveMatch")}</button></div></details></section>`}
    ${p.files.length ? `<div class="actionbar"><button class="btn primary big wide" id="toMake">✨ ${t("upload.next")} →</button></div>` : `<p class="muted center small">${t("upload.nextHint")}</p>`}`;
  const wire = (dropSel, inputSel, kind, prog) => {
    const drop = $(dropSel), input = $(inputSel);
    drop.onclick = () => input.click();
    drop.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } };
    input.onchange = () => upload(Array.prototype.slice.call(input.files), kind, prog);
    dnd(drop, (files) => upload(files, kind, prog));
  };
  wire("#footDrop", "#footFiles", "footage", "#upProg");
  wire("#narDrop", "#narFiles", "narration", "#narProg");
  $("#btnFolder").onclick = () => api(P() + "/reveal", { method: "POST", json: { sub: "footage" } }).catch((e) => errToast(e));
  $("#btnRescan").onclick = () => refreshProject();
  $$("[data-del]", body).forEach((b) => (b.onclick = async () => {
    if (!(await ask({ title: "confirm.deleteFile", text: "confirm.deleteFileText", ok: "confirm.deleteOk", danger: true, vars: { name: b.dataset.del } }))) return;
    try { await api(`${P()}/files/${encodeURIComponent(b.dataset.del)}?kind=${b.dataset.kind}`, { method: "DELETE" }); refreshProject(); } catch (e) { errToast(e); }
  }));
  $$("[data-nar]", body).forEach((s) => (s.onchange = () => saveAssign().then(() => toast(tt("common.saved"), 2000, "good")).catch((e) => errToast(e))));
  if ($("#btnSaveAssign")) $("#btnSaveAssign").onclick = async () => { try { await saveAssign(); toast(tt("upload.matchSaved"), 2500, "good"); refreshProject(); } catch (e) { errToast(e); } };
  $$("[data-phone]", body).forEach((b) => (b.onclick = showPhoneLink));
  if ($("#toMake")) $("#toMake").onclick = async () => { try { await saveAssign(); } catch (e) { /* keep going */ } setStep("make"); };
}
async function saveAssign() {
  if (!$("#musicSel") && !$("[data-nar]")) return;  // not on the upload screen
  const a = state.project.assign || {};
  const shots = Object.assign({}, a.shots || {}), narration = Object.assign({}, a.narration || {});
  $$("[data-shot]").forEach((s) => { if (s.value) shots[s.dataset.shot] = s.value; else delete shots[s.dataset.shot]; });
  $$("[data-nar]").forEach((s) => { if (s.value) narration[s.dataset.nar] = s.value; else delete narration[s.dataset.nar]; });
  const m = $("#musicSel") ? $("#musicSel").value : (a.music || [])[0];
  await api(P() + "/assign", { method: "POST", json: { shots, vo: a.vo || {}, narration, music: m ? [m] : [] } });
}
function upload(files, kind, progSel) {
  if (!files.length) return;
  const fd = new FormData(); files.forEach((f) => fd.append("files", f, f.name));
  fd.append("mtimes", JSON.stringify(files.map((f) => f.lastModified || 0)));
  fd.append("kind", kind);
  const xhr = new XMLHttpRequest();
  xhr.open("POST", P() + "/upload");
  const box = $(progSel);
  xhr.upload.onprogress = (e) => {
    if (!e.lengthComputable || !box) return;
    const pc = Math.round((e.loaded / e.total) * 100);
    box.innerHTML = `<div class="upbox"><div class="progress"><i style="width:${pc}%"></i></div><b>${t("upload.uploading", { n: files.length, p: pc })}</b><span class="muted small">${t("upload.keepOpen")}</span></div>`;
  };
  xhr.onload = () => {
    if (xhr.status < 400) toast(`<b>✓ ${t("upload.added", { n: files.length })}</b>`, 3000, "good");
    else errToast({ message: (JSON.parse(xhr.responseText || "{}").error) || "HTTP " + xhr.status }, "err.upload");
    refreshProject();
  };
  xhr.onerror = () => { errToast({ message: "network" }, "err.upload"); if (box) box.innerHTML = ""; };
  xhr.send(fd);
}

/* ---------------- step 4: make videos ---------------- */
function renderMake(body) {
  const p = state.project;
  if (!p.plan) { body.innerHTML = needPlanHtml(); wireNeedPlan(); return; }
  const running = (p.jobs || []).some((j) => j.kind === "render" && j.status === "running");
  body.innerHTML = `
    <section class="card"><h2>🎨 ${t("make.chooseTitle")}</h2><p class="muted">${t("make.chooseText")}</p>
      <div class="make-list">${p.plan.videos.map((v, vi) => `<div class="make-row">
        <label class="chk"><input type="checkbox" class="vchk" id="vchk_${esc(v.id)}" value="${esc(v.id)}" checked><span class="chk-box" aria-hidden="true"></span>
          <span class="mk-title"><b>#${v.rank} ${esc(v.title_th)}</b></span></label>
        <div class="mk-ctrls"><label class="sr" for="style_${vi}">${t("make.style")}</label>
          <select id="style_${vi}" data-style="${vi}">${STYLE_KEYS.map((k) => `<option value="${k}" ${k === v.anim_style ? "selected" : ""}>${t("style." + k)}</option>`).join("")}</select>
          <button class="btn ghost" data-shuffle="${vi}" title="${tt("make.shuffleHint")}">🎲 ${t("make.shuffle")}${v.variation ? ` <span class="muted">#${v.variation}</span>` : ""}</button></div></div>`).join("")}</div>
      <details id="dVersions"><summary>${t("make.moreOptions")}</summary>
        <label for="versions">${t("make.versions")}</label>
        <select id="versions"><option value="1">${t("make.v1")}</option><option value="2">${t("make.v2")}</option><option value="3">${t("make.v3")}</option><option value="5">${t("make.v5")}</option></select>
        <p class="muted small">${t("make.versionsHint")}</p></details>
    </section>
    <div class="actionbar"><button class="btn primary big wide" id="btnRender" ${running ? "disabled" : ""}>🎬 ${t(running ? "make.running" : "make.go")}</button>
      <button class="btn ghost wide" id="btnDraft" ${running ? "disabled" : ""}>⚡ ${t("make.draft")}</button></div>
    <section class="card" id="finished"><h2>🍿 ${t("make.finished")}</h2>
      ${p.renders.length ? `<div class="renders">${p.renders.map((r) => `<figure class="render"><video src="${F("renders/" + r.name)}" controls preload="metadata" playsinline></video>
        <figcaption class="muted small">${esc(r.name)}</figcaption>
        <a class="btn secondary wide" href="${F("renders/" + r.name)}?download=1" download>⬇ ${t("make.download")}</a></figure>`).join("")}</div>
        <div class="row"><a class="btn secondary big" href="#/schedule">📅 ${t("make.schedule")}</a><button class="btn ghost localonly" id="btnRendersFolder">📂 ${t("make.folder")}</button></div>`
      : `<div class="empty small"><div class="empty-art sm" aria-hidden="true">🎬</div><p class="muted">${t("make.none")}</p></div>`}</section>`;
  $$("[data-style]", body).forEach((sel) => (sel.onchange = () => updateVideo(+sel.dataset.style, { anim_style: sel.value })));
  $$("[data-shuffle]", body).forEach((b) => (b.onclick = () => {
    const v = state.project.plan.videos[+b.dataset.shuffle];
    updateVideo(+b.dataset.shuffle, { variation: (v.variation || 0) + 1 });
  }));
  $("#btnRender").onclick = () => startRender(false);
  $("#btnDraft").onclick = () => startRender(true);
  const rf = $("#btnRendersFolder"); if (rf) rf.onclick = () => api(P() + "/reveal", { method: "POST", json: { sub: "renders" } }).catch((e) => errToast(e));
}
async function updateVideo(vi, patch) {
  const snap = snapshot();
  const plan = clone(state.project.plan);
  Object.assign(plan.videos[vi], patch);
  try {
    await api(P() + "/plan", { method: "POST", json: { plan } }); state.project.plan = plan;
    toast(tt(patch.anim_style ? "make.styleSaved" : "make.shuffled"), 2500, "good"); renderProject(); restore(snap);
  } catch (e) { errToast(e); }
}
async function startRender(draft) {
  const videos = $$(".vchk:checked").map((c) => c.value);
  if (!videos.length) { toast(`<b>${t("make.pickOne")}</b>`, 3500, "bad"); return; }
  const versions = +$("#versions").value || 1;
  try {
    const r = await api(P() + "/render", { method: "POST", json: { videos, draft, versions } });
    state.project.jobs = (state.project.jobs || []).concat([r.job]);
    renderProject(); window.scrollTo({ top: 0, behavior: "smooth" }); pollJob(r.job.id);
  } catch (e) { errToast(e); }
}

/* ---------------- settings ---------------- */
const PROVS = ["claude_code", "manual", "claude", "openai"];
const KEY_FIELD = { claude_code: ["claude_code_token", "set.keyClaudeCode", "sk-ant-oat01-…"], claude: ["anthropic_api_key", "set.keyClaude", "sk-ant-…"], openai: ["openai_api_key", "set.keyOpenai", "sk-…"] };
function provChoices(name, sel) {
  return PROVS.map((v) => `<label class="choice ${sel === v ? "on" : ""}"><input type="radio" name="${name}" id="${name}_${v}" value="${v}" ${sel === v ? "checked" : ""} data-sync="1">
    <span class="choice-txt"><b>${t("prov." + v + ".title")}</b><span class="muted">${t("prov." + v + ".desc")}</span></span></label>`).join("");
}
function wireChoices(root) {
  $$(".choice input", root).forEach((inp) => (inp.onchange = () => {
    $$(`input[name="${inp.name}"]`, root).forEach((x) => x.closest(".choice").classList.toggle("on", x.checked));
    if (inp.name === "sProv" || inp.name === "obProv") $$("[data-keyfor]", root).forEach((k) => k.classList.toggle("hidden", k.dataset.keyfor !== inp.value));
  }));
}
function showSettings() {
  const s = state.settings;
  openModal(() => {
    const prov = s.provider || "claude_code";
    const h = state.health;
    setModal(`<h2 class="m-title">⚙️ ${t("set.title")}</h2>
      <section class="m-sec"><h3>🌐 ${t("set.language")}</h3>
        <select class="lang-sel" id="sLang" aria-label="${tt("set.language")}"><option value="th">ไทย</option><option value="en">English</option></select></section>
      <section class="m-sec"><h3>🤖 ${t("set.whoWrites")}</h3><p class="muted small">${t("set.whoWritesHint")}</p>
        <div class="choices">${provChoices("sProv", prov)}</div>
        ${Object.keys(KEY_FIELD).map((pv) => { const kf = KEY_FIELD[pv]; return `<div class="keybox ${pv === prov ? "" : "hidden"}" data-keyfor="${pv}">
          <label for="sKey_${pv}">${t(kf[1])}</label><input id="sKey_${pv}" data-field="${kf[0]}" value="${esc(s[kf[0]])}" placeholder="${kf[2]}" autocomplete="off" spellcheck="false">
          <p class="hint">${t(kf[1] + "Hint")}</p>
          ${pv === "claude_code" ? `<div class="row"><button class="btn ghost" id="ccTest">🔌 ${t("set.ccTest")}</button><span id="ccTestSt" class="small" aria-live="polite"></span></div>` : ""}</div>`; }).join("")}</section>
      <section class="m-sec"><h3>🎙 ${t("set.voice")}</h3><div class="choices">
        <label class="choice ${s.voice_source !== "tts" ? "on" : ""}"><input type="radio" name="sVsrc" id="sVsrc_mine" value="mine" ${s.voice_source !== "tts" ? "checked" : ""} data-sync="1"><span class="choice-txt"><b>${t("set.voiceMine")}</b><span class="muted">${t("set.voiceMineDesc")}</span></span></label>
        <label class="choice ${s.voice_source === "tts" ? "on" : ""}"><input type="radio" name="sVsrc" id="sVsrc_tts" value="tts" ${s.voice_source === "tts" ? "checked" : ""} data-sync="1"><span class="choice-txt"><b>${t("set.voiceTts")}</b><span class="muted">${t("set.voiceTtsDesc")}</span></span></label></div></section>
      <details class="m-sec adv" id="dAdv"><summary>🛠 ${t("set.advanced")}</summary><p class="muted small">${t("set.advancedHint")}</p>
        <div class="grid2">
          <div><label for="sN">${t("set.videosPer")}</label><input id="sN" type="number" min="1" max="8" value="${s.videos_per_product}"></div>
          <div><label for="sMv">${t("set.musicVol")}</label><input id="sMv" type="number" step="0.02" min="0" max="1" value="${s.music_volume}"><p class="hint">${t("set.musicVolHint")}</p></div>
          <div><label for="sCrf">${t("set.quality")}</label><input id="sCrf" type="number" value="${s.render_crf}"><p class="hint">${t("set.qualityHint")}</p></div>
          <div><label for="sEff">${t("set.effort")}</label><select id="sEff">${["medium", "high", "xhigh"].map((x) => `<option value="${x}" ${x === s.claude_effort ? "selected" : ""}>${t("set.effort_" + x)}</option>`).join("")}</select></div>
          <div><label for="sCm">${t("set.claudeModel")}</label><input id="sCm" value="${esc(s.claude_model)}"></div>
          <div><label for="sOm">${t("set.openaiModel")}</label><input id="sOm" value="${esc(s.openai_model)}"></div>
          <div><label for="sVoice">${t("set.ttsVoice")}</label><input id="sVoice" value="${esc(s.tts_voice)}"></div>
          <div><label for="sRate">${t("set.ttsRate")}</label><input id="sRate" type="number" value="${s.tts_rate}"></div></div>
        <h3>📊 ${t("set.dataset")}</h3><p class="muted small">${t("set.datasetHint")}</p>
        <div class="row"><input type="file" id="sCsv" accept=".csv,text/csv" hidden><button class="btn ghost" id="sCsvPick">📄 ${t("set.datasetChoose")}</button><span id="sCsvName" class="muted small"></span>
          <button class="btn" id="sCsvBtn">${t("set.datasetBtn")}</button><span id="sCsvSt" class="muted small"></span></div>
        <h3>🩺 ${t("set.status")}</h3>
        <ul class="status-list"><li>${t("set.version")}: <b>v${esc(h.version || "?")}</b></li>
          <li>${h.ffmpeg ? `<span class="ok">● ${t("set.editorOk")}</span>` : `<span class="bad">● ${t("set.editorMissing")}</span>`}</li>
          <li>${h.claude_code ? `<span class="ok">● ${t("set.ccOk")}</span>` : `<span class="muted">○ ${t("set.ccMissing")}</span>`}</li></ul></details>
      <p class="muted small">🔒 ${t("set.keysLocal")}</p>
      <div class="m-actions"><button class="btn ghost" id="sCancel">${t("common.cancel")}</button><button class="btn primary big" id="sSave">${t("common.save")}</button></div>`);
    $("#sLang").value = I18N.lang;
    if ($("#ccTest")) $("#ccTest").onclick = async () => {
      const st = $("#ccTestSt"); st.className = "small muted"; st.textContent = tt("set.ccTesting");
      $("#ccTest").disabled = true;
      try {
        await api("/api/claude-code/test", { method: "POST", json: { token: $("#sKey_claude_code").value.trim() } });
        st.className = "small ok"; st.textContent = tt("set.ccTestOk");
      } catch (e) {
        st.className = "small bad"; st.textContent = tt("set.ccTestFail") + " — " + (e.message || "");
      } finally { $("#ccTest").disabled = false; }
    };
    $("#sLang").onchange = (e) => setLanguage(e.target.value, true);
    wireChoices($("#modal"));
    api("/api/inspiration").then((r) => { const el = $("#sCsvSt"); if (el) el.textContent = tt(r.exists ? "set.datasetLoaded" : "set.datasetNone"); }).catch(() => {});
    $("#sCsvPick").onclick = () => $("#sCsv").click();
    $("#sCsv").onchange = () => { $("#sCsvName").textContent = $("#sCsv").files[0] ? $("#sCsv").files[0].name : ""; };
    $("#sCsvBtn").onclick = async () => {
      const f = $("#sCsv").files[0]; if (!f) { toast(`<b>${t("set.datasetPick")}</b>`, 3000, "bad"); return; }
      const fd = new FormData(); fd.append("file", f);
      try { const r = await api("/api/inspiration", { method: "POST", body: fd }); $("#sCsvSt").textContent = tt("set.datasetDone", { n: r.examples }); }
      catch (e) { errToast(e, "err.csv"); }
    };
    $("#sCancel").onclick = closeModal;
    $("#sSave").onclick = async () => {
      const provSel = $('input[name="sProv"]:checked').value;
      const upd = { provider: provSel, claude_model: $("#sCm").value.trim(), openai_model: $("#sOm").value.trim(),
        videos_per_product: +$("#sN").value || 5, claude_effort: $("#sEff").value, voice_source: $('input[name="sVsrc"]:checked').value,
        tts_voice: $("#sVoice").value.trim(), tts_rate: +$("#sRate").value || 185, music_volume: +$("#sMv").value || 0.14,
        render_crf: +$("#sCrf").value || 20, language: I18N.lang };
      $$("[data-field]").forEach((i) => { upd[i.dataset.field] = i.value.trim(); });
      const kf = KEY_FIELD[provSel];
      if (kf && !upd[kf[0]]) { toast(`<b>🔑 ${t("set.needKey")}</b>`, 4500, "bad"); $("#sKey_" + provSel).focus(); return; }
      try { state.settings = await api("/api/settings", { method: "POST", json: upd }); closeModal(); toast(`<b>✓ ${t("set.saved")}</b>`, 2500, "good"); if (state.view === "new") renderNew(true); }
      catch (e) { errToast(e); }
    };
  });
}

/* ---------------- onboarding (shown once; ❓ reopens it) ---------------- */
const OB_STEPS = [
  () => `<div class="big-emoji" aria-hidden="true">👋</div><h2>${t("ob.welcomeTitle")}</h2><p>${t("ob.welcomeText")}</p>
    <ol class="ob-tools"><li><span aria-hidden="true">📝</span><div>${t("ob.tool1")}</div></li><li><span aria-hidden="true">✂️</span><div>${t("ob.tool2")}</div></li><li><span aria-hidden="true">📅</span><div>${t("ob.tool3")}</div></li></ol>
    ${journeyHtml(null)}<p class="tip">⏱ ${t("ob.welcomeTip")}</p>`,
  () => {
    const p = state.settings.provider || "claude_code";
    return `<div class="big-emoji" aria-hidden="true">🤖</div><h2>${t("ob.aiTitle")}</h2><p>${t("ob.aiText")}</p>
      <div class="choices">${provChoices("obProv", p)}</div>
      ${Object.keys(KEY_FIELD).map((pv) => `<div class="keybox ${pv === p ? "" : "hidden"}" data-keyfor="${pv}"><label for="obKey_${pv}">${t(KEY_FIELD[pv][1])}</label>
        <input id="obKey_${pv}" placeholder="${tt("ob.keyPh")}" autocomplete="off" spellcheck="false"><p class="hint">${t(KEY_FIELD[pv][1] + "Hint")}</p></div>`).join("")}
      <p class="tip">${t("ob.aiTip")}</p>`;
  },
  () => `<div class="big-emoji" aria-hidden="true">📝</div><h2>${t("ob.s1Title")}</h2><ol class="big-steps"><li>${t("ob.s1a")}</li><li>${t("ob.s1b")}</li><li>${t("ob.s1c")}</li></ol>
    <p>${t("ob.s1get")}</p><p class="tip">💡 ${t("ob.s1tip")}</p>`,
  () => `<div class="big-emoji" aria-hidden="true">🎬</div><h2>${t("ob.filmTitle")}</h2><ul class="ticks"><li>${t("film.t1")}</li><li>${t("film.t2")}</li><li>${t("film.t3")}</li><li>${t("film.t4")}</li><li>${t("film.t5")}</li><li>${t("film.t6")}</li></ul>`,
  () => `<div class="big-emoji" aria-hidden="true">🎙</div><h2>${t("ob.voiceTitle")}</h2><ul class="ticks"><li>${t("film.v1")}</li><li>${t("film.v2")}</li><li>${t("film.v3")}</li><li>${t("film.v4")}</li></ul><p class="tip">${t("film.voiceTip")}</p>`,
  () => `<div class="big-emoji" aria-hidden="true">✂️</div><h2>${t("ob.editTitle")}</h2><ol class="big-steps"><li>${t("ob.edit1")}</li><li>${t("ob.edit2")}</li><li>${t("ob.edit3")}</li><li>${t("ob.edit4")}</li><li>${t("ob.edit5")}</li></ol><p class="tip">${t("ob.editTip")}</p>`,
  () => `<div class="big-emoji" aria-hidden="true">📅</div><h2>${t("ob.schedTitle")}</h2><ol class="big-steps"><li>${t("ob.sched1")}</li><li>${t("ob.sched2")}</li><li>${t("ob.sched3")}</li><li>${t("ob.sched4")}</li></ol><p class="tip">${t("ob.schedTip")}</p>`,
  () => `<div class="big-emoji" aria-hidden="true">🎉</div><h2>${t("ob.readyTitle")}</h2><p>${t("ob.ready1")}</p><p>${t("ob.ready2")}</p>`,
];
function showOnboarding(i) {
  const last = OB_STEPS.length - 1;
  openModal(() => {
    setModal(`<div class="ob">${OB_STEPS[i]()}
      <div class="dots" aria-label="${tt("ob.progress", { n: i + 1, total: OB_STEPS.length })}">${OB_STEPS.map((_, k) => `<i class="${k === i ? "on" : ""}"></i>`).join("")}</div>
      <div class="ob-nav">${i === last ? "<span></span>" : `<button class="btn ghost" id="obSkip">${t("ob.skip")}</button>`}
        <div class="row">${i > 0 ? `<button class="btn" id="obBack">← ${t("common.back")}</button>` : ""}
        <button class="btn primary big" id="obNext">${i === last ? t("ob.start") + " 🚀" : t("common.next") + " →"}</button></div></div></div>`);
    wireChoices($("#modal"));
    const finish = async () => {
      try { state.settings = await api("/api/settings", { method: "POST", json: { onboarded: true, language: I18N.lang } }); } catch (e) { /* show again next time */ }
      closeModal();
      if (i === last && state.view !== "project") go("#/new");
    };
    if ($("#obSkip")) $("#obSkip").onclick = finish;
    if ($("#obBack")) $("#obBack").onclick = () => showOnboarding(i - 1);
    $("#obNext").onclick = async () => {
      const sel = $('input[name="obProv"]:checked');
      if (sel) {  // AI setup step
        const upd = { provider: sel.value };
        const kf = KEY_FIELD[sel.value];
        const key = kf ? ($("#obKey_" + sel.value).value || "").trim() : "";
        if (kf && key) upd[kf[0]] = key;
        if (kf && !key && !state.settings[kf[0]]) { toast(`<b>🔑 ${t("ob.needKey")}</b>`, 4500, "bad"); return; }
        try { state.settings = await api("/api/settings", { method: "POST", json: upd }); } catch (e) { return errToast(e); }
      }
      if (i === last) return finish();
      showOnboarding(i + 1);
    };
  });
}

/* ---------------- send files from a phone (QR over Wi-Fi) ---------------- */
async function showPhoneLink() {
  let r;
  try { r = await api(P() + "/phone-link", { method: "POST" }); } catch (e) { return errToast(e); }
  const url = r.url + (r.url.indexOf("?") >= 0 ? "&" : "?") + "lang=" + I18N.lang;
  const before = (state.project.files.length || 0) + ((state.project.narration || []).length || 0);
  let got = 0;
  const render = () => {
    setModal(`<div class="ob phone-modal"><h2>📱 ${t("phone.title")}</h2>
      <img src="${r.qr}" alt="${tt("phone.qrAlt")}" class="qr">
      <ol class="big-steps"><li>${t(state.health.server ? "phone.s1web" : "phone.s1")}</li><li>${t("phone.s2")}</li><li>${t("phone.s3")}</li></ol>
      <details id="dPhoneUrl"><summary>${t("phone.link")}</summary><p class="muted small breakall">${esc(r.url)}</p></details>
      <p class="phone-count" aria-live="polite">${got > 0 ? `<b class="ok">✓ ${t("phone.got", { n: got })}</b>` : `<span class="spinner sm"></span> ${t("phone.waiting")}`}</p>
      <p class="tip">${t("phone.tip", { h: r.hours })}</p>
      <button class="btn primary big wide" id="phoneDone">${t("phone.done")}</button></div>`);
    $("#phoneDone").onclick = closeModal;
  };
  state.onModalClose = () => { clearInterval(timer); refreshProject(); };
  openModal(render);
  const timer = setInterval(async () => {
    if ($("#modal").classList.contains("hidden")) return clearInterval(timer);
    try {
      const p = await api(P());
      const n = Math.max(0, p.files.length + (p.narration || []).length - before);
      if (n !== got) { got = n; if (state.modalFn === render) render(); }
    } catch (e) { /* keep polling */ }
  }, 3000);
}

/* ---------------- Tool 3: TikTok post scheduler (PostPeer + Cloudinary) ---------------- */
const POST_ST = { planned: "", queued: "g", posted: "g", missed: "r", cancelled: "", failed: "r" };
async function showScheduler() {
  if (!state.sched) $("#main").innerHTML = `<div class="loading-screen"><div class="spinner"></div></div>`;
  try {
    const res = await Promise.all([api("/api/schedule"), api("/api/settings")]);
    state.sched = res[0]; state.settings = res[1];
  } catch (e) { errToast(e); return; }
  if (state.view !== "schedule") return;
  renderScheduler();
  if (state.settings.postpeer_key && !state.sched.connected) loadAccts(true);
}
function fmtDay(iso) {
  const dt = new Date(iso + "T12:00:00");
  return t("sched.dayLabel", { day: tt("day." + dt.getDay()), d: dt.getDate(), m: dt.getMonth() + 1 });
}
function renderScheduler() {
  const d = state.sched, s = state.settings;
  const upcoming = d.posts.filter((p) => ["cancelled", "posted"].indexOf(p.status) < 0);
  const done = d.posts.filter((p) => ["cancelled", "posted"].indexOf(p.status) >= 0);
  const groups = {};
  upcoming.forEach((p) => { const k = p.at.slice(0, 10); (groups[k] = groups[k] || []).push(p); });
  const fileUrl = (p) => `/files/${encodeURIComponent(p.project_id)}/renders/${encodeURIComponent(p.render)}`;
  const card = (p) => `<article class="card post" data-post="${esc(p.id)}">
      <div class="post-top"><video src="${fileUrl(p)}" preload="metadata" muted controls playsinline class="post-vid"></video>
        <div class="post-meta"><b>${esc(p.project_name)}</b> <span class="muted">· ${esc(p.video_id)}</span>
          <div><span class="pill ${POST_ST[p.status] || ""}">${tOr("post." + p.status, p.status)}</span></div>
          <label for="at_${esc(p.id)}">🕒 ${t("sched.time")}</label><input type="datetime-local" id="at_${esc(p.id)}" data-f="at" value="${esc(p.at)}"></div></div>
      <label for="cap_${esc(p.id)}">💬 ${t("sched.caption")}</label><textarea id="cap_${esc(p.id)}" data-f="caption" rows="3">${esc(p.caption)}</textarea>
      <label for="tag_${esc(p.id)}"># ${t("sched.hashtags")}</label><input id="tag_${esc(p.id)}" data-f="hashtags" value="${esc(p.hashtags.join(" "))}">
      ${p.error ? `<p class="banner bad small">⚠️ ${esc(friendly({ message: p.error }, "err.postFailed").text)}<br><small>${t("err.details")}: ${esc(p.error)}</small></p>` : ""}
      ${p.post_url ? `<p><a href="${esc(p.post_url)}" target="_blank" rel="noopener">${t("sched.viewPost")} ↗</a></p>` : ""}
      <div class="post-actions"><button class="btn" data-act="save">💾 ${t("common.save")}</button>
        <button class="btn ghost" data-act="newcap">🔄 ${t("sched.newCaption")}</button>
        <button class="btn ghost" data-act="copy">📋 ${t("common.copy")}</button>
        <button class="btn secondary" data-act="now">🚀 ${t("sched.postNow")}</button>
        <button class="btn ghost danger" data-act="cancel">🗑 ${t("sched.cancel")}</button></div></article>`;
  const hostNote = tOr("sched.host." + d.hosting, "");
  const modeTxt = s.postpeer_mode === "direct" ? t("sched.modeDirect") : t("sched.modeInbox");
  const setup = `
    <ol class="setup-steps">
      <li><h3>${t("sched.s1Title")}</h3><p class="muted">${t("sched.s1Text")}</p>
        <label for="ppKey">${t("sched.ppKey")}</label>
        <div class="inline"><input id="ppKey" placeholder="pp_…" value="${esc(s.postpeer_key)}" autocomplete="off"><button class="btn" id="ppSave">${t("common.save")}</button></div>
        <p class="hint">${t("sched.ppKeyHint")}</p>
        <div class="row"><button class="btn primary" id="ppConnect">🔗 ${t("sched.connect")}</button><button class="btn ghost" id="ppRefresh">↻ ${t("sched.loadAccts")}</button></div>
        <label for="ppAcct">${t("sched.pickAcct")}</label><select id="ppAcct"><option value="">${t("sched.pickAcctNone")}</option></select></li>
      <li><h3>${t("sched.s2Title")} <span class="opt">${t("sched.recommended")}</span></h3><p class="muted">${t("sched.s2Text")}</p>
        <label for="cdUrl">${t("sched.cdUrl")}</label>
        <div class="inline"><input id="cdUrl" placeholder="cloudinary://API_KEY:API_SECRET@CLOUD_NAME" value="${esc(s.cloudinary_url)}" autocomplete="off"><button class="btn" id="cdSave">${t("sched.cdSave")}</button></div></li>
      <li><h3>${t("sched.s3Title")}</h3><div class="choices">
        <label class="choice ${s.postpeer_mode !== "direct" ? "on" : ""}"><input type="radio" name="ppMode" id="ppMode_inbox" value="inbox" ${s.postpeer_mode !== "direct" ? "checked" : ""}>
          <span class="choice-txt"><b>📥 ${t("sched.modeInboxTitle")}</b><span class="muted">${t("sched.modeInboxDesc")}</span></span></label>
        <label class="choice ${s.postpeer_mode === "direct" ? "on" : ""}"><input type="radio" name="ppMode" id="ppMode_direct" value="direct" ${s.postpeer_mode === "direct" ? "checked" : ""}>
          <span class="choice-txt"><b>⚡ ${t("sched.modeDirectTitle")}</b><span class="muted">${t("sched.modeDirectDesc")}</span></span></label></div></li></ol>`;
  $("#main").innerHTML = `${healthBanner()}
    <div class="page-head"><h1>📅 ${t("sched.title")}</h1><p class="muted">${t("sched.sub")}</p></div>
    ${d.connected ? `<section class="card connected"><div class="conn-row"><span class="conn-ico" aria-hidden="true">✅</span>
        <div><b>${t("sched.connectedTo", { name: s.postpeer_account_name || s.postpeer_account_id })}</b><br><span class="muted small">${t("sched.modeIs")} ${modeTxt} · ${hostNote}</span></div></div>
        <details id="dSetup"><summary>${t("sched.changeSetup")}</summary>${setup}</details></section>`
      : `<section class="card setup"><h2>🔗 ${t("sched.setupTitle")}</h2><p class="muted">${t("sched.setupSub")}</p>${setup}</section>`}
    <section class="card plan-card"><div class="ready-num"><b>${d.ready.length}</b><span>${t("sched.readyLabel")}</span></div>
      <p class="muted">${t("sched.autoText")}</p>
      <label for="perDay">${t("sched.perDay")}</label>
      <select id="perDay">${[1, 2, 3].map((n) => `<option ${+s.posts_per_day === n ? "selected" : ""} value="${n}">${t("sched.perDay" + n)}</option>`).join("")}</select>
      ${d.ready.length ? `<button class="btn primary big wide" id="schAuto">✨ ${t("sched.autoBtn", { n: d.ready.length })}</button>`
        : `<p class="banner warn small">🎬 ${t("sched.noneReady")}</p>`}
      <p class="small"><button class="linkbtn" id="schSync">↻ ${t("sched.sync")}</button> <span class="muted">${t("sched.syncHint")}</span></p>
      <p class="muted small">🕗 ${t("sched.times")}</p></section>
    ${Object.keys(groups).sort().map((day) => `<h2 class="day-title">${fmtDay(day)}</h2>${groups[day].map(card).join("")}`).join("")
      || `<section class="card empty"><div class="empty-art" aria-hidden="true">🗓️</div><h2>${t("sched.emptyTitle")}</h2><p class="muted">${t("sched.emptyText")}</p></section>`}
    ${done.length ? `<details class="card fold" id="dDone"><summary><span>${t("sched.done", { n: done.length })}</span></summary>${done.map(card).join("")}</details>` : ""}`;
  wireScheduler();
}
const saveSet = async (u) => { state.settings = await api("/api/settings", { method: "POST", json: u }); };
async function loadAccts(quiet) {
  const s = state.settings;
  try {
    const r = await api("/api/postpeer/accounts");
    const sel = $("#ppAcct"); if (!sel) return;
    sel.innerHTML = `<option value="">${t("sched.pickAcctNone")}</option>` + r.accounts.map((a) => `<option value="${esc(a.id)}" data-name="${esc(a.name)}" ${a.id === s.postpeer_account_id ? "selected" : ""}>${esc(a.name || a.id)}</option>`).join("");
    if (!r.accounts.length && !quiet) toast(`<b>${t("sched.noAccts")}</b>`, 5000, "bad");
    if (r.accounts.length === 1 && !s.postpeer_account_id) { sel.value = r.accounts[0].id; sel.onchange(); }
  } catch (e) { if (!quiet) errToast(e, "err.postpeer"); }
}
function wireScheduler() {
  $("#ppSave").onclick = async () => { try { await saveSet({ postpeer_key: $("#ppKey").value.trim() }); toast(`<b>✓ ${t("sched.keySaved")}</b>`, 2500, "good"); } catch (e) { errToast(e); } };
  $("#ppConnect").onclick = async () => {
    if (!$("#ppKey").value.trim()) { toast(`<b>🔑 ${t("sched.needKey")}</b>`, 4000, "bad"); $("#ppKey").focus(); return; }
    try {
      await saveSet({ postpeer_key: $("#ppKey").value.trim() });
      const r = await api("/api/postpeer/connect", { method: "POST" }); window.open(r.url, "_blank");
      toast(`<b>${t("sched.loginHint")}</b>`, 7000);
    } catch (e) { errToast(e, "err.postpeer"); }
  };
  $("#ppRefresh").onclick = () => loadAccts(false);
  $("#ppAcct").onchange = async () => {
    const o = $("#ppAcct").selectedOptions[0];
    if (!o || !o.value) return;
    try { await saveSet({ postpeer_account_id: o.value, postpeer_account_name: o.dataset.name || "" }); celebrateSmall("sched.acctConnected"); showScheduler(); } catch (e) { errToast(e); }
  };
  $("#cdSave").onclick = async () => {
    try {
      await saveSet({ cloudinary_url: $("#cdUrl").value.trim() });
      const r = await api("/api/cloudinary/check", { method: "POST" });
      toast(`<b>✓ ${t("sched.cdOk", { cloud: r.cloud })}</b>`, 3500, "good"); showScheduler();
    } catch (e) { errToast(e, "err.cloudinary"); }
  };
  $$('[name="ppMode"]').forEach((r) => (r.onchange = () => {
    $$('[name="ppMode"]').forEach((x) => x.closest(".choice").classList.toggle("on", x.checked));
    saveSet({ postpeer_mode: r.value }).then(() => toast(tt("common.saved"), 2000, "good")).catch((e) => errToast(e));
  }));
  if ($("#schAuto")) $("#schAuto").onclick = async () => {
    try {
      const r = await api("/api/schedule/auto", { method: "POST", json: { per_day: +$("#perDay").value } });
      await showScheduler();
      openModal(() => {
        setModal(`<div class="celebrate"><div class="big-emoji" aria-hidden="true">🗓️</div><h2>${t("celebrate.schedTitle", { n: r.created })}</h2>
          <p class="muted">${t(state.sched.connected ? "celebrate.schedText" : "celebrate.schedTextNoConn")}</p>
          <button class="btn primary big wide" id="celOk">${t("celebrate.ok")}</button></div>`);
        $("#celOk").onclick = closeModal;
      });
    } catch (e) { errToast(e); }
  };
  $("#schSync").onclick = async () => { try { await api("/api/schedule/sync", { method: "POST" }); toast(`<b>✓ ${t("sched.synced")}</b>`, 2500, "good"); showScheduler(); } catch (e) { errToast(e, "err.postpeer"); } };
  $$("[data-post]").forEach((el) => {
    const id = el.dataset.post;
    $$("[data-act]", el).forEach((b) => (b.onclick = async () => {
      try {
        const act = b.dataset.act;
        if (act === "save") {
          await api(`/api/schedule/${id}`, { method: "PATCH", json: { at: $('[data-f="at"]', el).value,
            caption: $('[data-f="caption"]', el).value, hashtags: $('[data-f="hashtags"]', el).value.split(/\s+/).filter(Boolean) } });
          toast(tt("common.saved"), 2000, "good");
        } else if (act === "newcap") {
          await api(`/api/schedule/${id}/caption`, { method: "POST", json: { variant: Math.floor(Math.random() * 1000) + 1 } });
          toast(tt("sched.newCapDone"), 2000, "good");
        } else if (act === "copy") {
          await copyText($('[data-f="caption"]', el).value + "\n\n" + $('[data-f="hashtags"]', el).value);
          return toast(tt("common.copied"), 2000, "good");
        } else if (act === "now") {
          if (!(await ask({ title: "confirm.postNow", text: "confirm.postNowText", ok: "confirm.postNowOk" }))) return;
          await api(`/api/schedule/${id}/post-now`, { method: "POST" }); toast(`<b>🚀 ${t("sched.sent")}</b>`, 3500, "good");
        } else if (act === "cancel") {
          if (!(await ask({ title: "confirm.cancelPost", text: "confirm.cancelPostText", ok: "confirm.cancelPostOk", danger: true }))) return;
          await api(`/api/schedule/${id}`, { method: "DELETE" });
        }
        showScheduler();
      } catch (e) { errToast(e, "err.postFailed"); }
    }));
  });
}
function celebrateSmall(key) { toast(`<b>🎉 ${t(key)}</b>`, 3500, "good"); }

boot();
