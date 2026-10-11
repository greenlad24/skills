/* Thai TikTok Studio — single-page UI (vanilla JS, no build step). */
const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const state = { pid: null, project: null, tab: "plan", settings: null, polls: {}, newFiles: [] };

async function api(path, opts = {}) {
  const o = { ...opts };
  if (o.json !== undefined) { o.body = JSON.stringify(o.json); o.headers = { "Content-Type": "application/json" }; delete o.json; }
  const r = await fetch(path, o);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
  return data;
}
function toast(msg, ms = 2600) { const t = $("#toast"); t.textContent = msg; t.classList.remove("hidden"); clearTimeout(t._h); t._h = setTimeout(() => t.classList.add("hidden"), ms); }
function modal(html) { $("#modalBody").innerHTML = html; $("#modal").classList.remove("hidden"); }
function closeModal() { $("#modal").classList.add("hidden"); }
$("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") closeModal(); });
const fmtSize = (b) => b > 1e9 ? (b / 1e9).toFixed(1) + " GB" : b > 1e6 ? (b / 1e6).toFixed(1) + " MB" : Math.round(b / 1e3) + " KB";
const STATUS = { new: "new", researching: "researching…", writing: "writing scripts…", waiting_for_paste: "waiting for pasted answer", planned: "ready", error: "error" };

/* ---------------- boot ---------------- */
async function boot() {
  try {
    const h = await api("/api/health");
    $("#ver").textContent = "v" + h.version;
    $("#health").innerHTML = `${h.ffmpeg ? '<span class="ok">● editor ready</span>' : '<span class="bad">● ffmpeg missing</span>'} · ${h.tts ? '<span class="ok">Thai voice ✓</span>' : '<span class="warn" title="Install the Thai voice Kanya in System Settings → Accessibility → Spoken Content">Thai voice ✗</span>'}`;
  } catch (e) { $("#health").textContent = "server offline"; }
  state.settings = await api("/api/settings");
  await loadProjects();
  const pid = location.hash.slice(1);
  if (pid) openProject(decodeURIComponent(pid)); else showNew();
}
$("#btnNew").onclick = () => { history.replaceState(null, "", "#"); showNew(); };
$("#btnSettings").onclick = showSettings;

async function loadProjects() {
  const list = await api("/api/projects");
  $("#projectList").innerHTML = list.map((p) => `<li data-id="${esc(p.id)}" class="${p.id === state.pid ? "active" : ""}">${esc(p.name)}<span class="st">${esc(STATUS[p.status] || p.status)}</span></li>`).join("") || '<li class="muted">No products yet</li>';
  $("#projectList").querySelectorAll("li[data-id]").forEach((li) => (li.onclick = () => openProject(li.dataset.id)));
}

/* ---------------- new product ---------------- */
function showNew() {
  state.pid = null; state.project = null; state.newFiles = [];
  $("#main").innerHTML = ""; $("#main").appendChild($("#tplNew").content.cloneNode(true));
  const prov = state.settings.provider;
  $("#providerNote").innerHTML = prov === "manual" ? "Mode: <b>free copy/paste</b> into ChatGPT or Claude chat"
    : `AI: <b>${prov === "openai" ? "ChatGPT (" + esc(state.settings.openai_model) + ")" : "Claude (" + esc(state.settings.claude_model) + ")"}</b> · change in Settings`;
  const drop = $("#newDrop"), input = $("#newFiles");
  drop.onclick = () => input.click();
  input.onchange = () => addNewFiles([...input.files]);
  dnd(drop, (files) => addNewFiles(files.filter((f) => f.type.startsWith("image/"))));
  $("#btnGenerate").onclick = generate;
  loadProjects();
}
function addNewFiles(files) {
  state.newFiles.push(...files);
  $("#newThumbs").innerHTML = state.newFiles.map((f) => `<img src="${URL.createObjectURL(f)}" alt="">`).join("");
}
function dnd(el, cb) {
  el.addEventListener("dragover", (e) => { e.preventDefault(); el.classList.add("over"); });
  el.addEventListener("dragleave", () => el.classList.remove("over"));
  el.addEventListener("drop", (e) => { e.preventDefault(); el.classList.remove("over"); cb([...e.dataTransfer.files]); });
}
document.addEventListener("paste", (e) => {  // paste a screenshot straight from the clipboard
  if (!$("#newDrop")) return;
  const imgs = [...(e.clipboardData?.files || [])].filter((f) => f.type.startsWith("image/"));
  if (imgs.length) addNewFiles(imgs);
});
async function generate() {
  const fd = new FormData();
  fd.append("text", $("#newText").value.trim());
  fd.append("notes", $("#newNotes").value.trim());
  state.newFiles.forEach((f) => fd.append("images", f, f.name || "screenshot.png"));
  $("#btnGenerate").disabled = true;
  try {
    const res = await api("/api/projects", { method: "POST", body: fd });
    await loadProjects();
    openProject(res.project.id);
  } catch (e) { toast(e.message); $("#btnGenerate").disabled = false; }
}

/* ---------------- project view ---------------- */
async function openProject(pid, keepTab) {
  state.pid = pid; if (!keepTab) state.tab = "plan";
  history.replaceState(null, "", "#" + encodeURIComponent(pid));
  try { state.project = await api(`/api/projects/${encodeURIComponent(pid)}`); }
  catch (e) { toast("Project not found"); showNew(); return; }
  renderProject();
  loadProjects();
  (state.project.jobs || []).filter((j) => j.status === "running").forEach((j) => pollJob(j.id));
}
const P = () => `/api/projects/${encodeURIComponent(state.pid)}`;
const F = (rel) => `/files/${encodeURIComponent(state.pid)}/${rel.split("/").map(encodeURIComponent).join("/")}`;

function renderProject() {
  const p = state.project, m = p.meta;
  const jobs = (p.jobs || []).slice(-1);
  $("#main").innerHTML = `
    <section class="card">
      <div class="vhead"><div><h1>${esc(m.name)}</h1>
        <div class="muted">${esc(STATUS[m.status] || m.status)} · <a href="#" id="lnkFolder">open folder</a></div></div>
        <div class="row" style="margin:0">
          ${p.plan ? `<a href="${F("filming_pack.html")}" target="_blank"><button class="secondary">🖨 Filming pack (Thai)</button></a>` : ""}
          <button class="ghost" id="btnReplan">↻ Regenerate</button>
          <button class="ghost danger" id="btnDelete">Delete</button>
        </div></div>
      <div id="jobBox">${jobs.map(jobHtml).join("")}</div>
    </section>
    <div class="tabs"><button class="tab ${state.tab === "plan" ? "active" : ""}" data-tab="plan">1 · Scripts & shot lists</button>
      <button class="tab ${state.tab === "edit" ? "active" : ""}" data-tab="edit">2 · Auto-edit videos</button></div>
    <div id="tabBody"></div>`;
  document.querySelectorAll(".tab").forEach((b) => (b.onclick = () => { state.tab = b.dataset.tab; renderProject(); }));
  $("#lnkFolder").onclick = (e) => { e.preventDefault(); api(P() + "/reveal", { method: "POST", json: {} }).catch((er) => toast(er.message, 6000)); };
  $("#btnReplan").onclick = async () => { if (!confirm("Run research + script writing again? (Your edits to this plan will be replaced.)")) return; const r = await api(P() + "/replan", { method: "POST" }); pollJob(r.job.id); };
  $("#btnDelete").onclick = async () => { if (!confirm("Delete this product and all its files?")) return; await api(P(), { method: "DELETE" }); showNew(); };
  if (state.tab === "plan") renderPlanTab(); else renderEditTab();
}

function jobHtml(j) {
  const pct = Math.round((j.progress || 0) * 100);
  const head = j.status === "running" ? `⏳ ${j.kind === "plan" ? "Researching & writing" : "Rendering"}… ${pct}% (${j.elapsed}s)`
    : j.status === "error" ? `<span class="bad">✗ ${esc(j.error)}</span>` : `<span class="ok">✓ ${j.kind === "plan" ? "Plan ready" : "Render finished"}</span>`;
  return `<div style="margin-top:12px"><b>${head}</b>${j.status === "running" ? `<div class="progress"><i style="width:${pct}%"></i></div>` : ""}
    <details ${j.status !== "done" ? "open" : ""}><summary>log</summary><div class="log">${esc((j.log || []).join("\n"))}</div></details></div>`;
}
function pollJob(id) {
  if (state.polls[id]) return;
  state.polls[id] = setInterval(async () => {
    let j; try { j = await api(`/api/jobs/${id}`); } catch { clearInterval(state.polls[id]); delete state.polls[id]; return; }
    if (j.project_id !== state.pid) return;
    const box = $("#jobBox"); if (box) { box.innerHTML = jobHtml(j); const lg = box.querySelector(".log"); if (lg) lg.scrollTop = 1e9; }
    if (j.status !== "running") {
      clearInterval(state.polls[id]); delete state.polls[id];
      if (j.kind === "render") state.tab = "edit";
      openProject(state.pid, true);
      toast(j.status === "done" ? "Done ✓" : "Failed — see log");
    }
  }, 1500);
}

/* ---------------- tab 1: plan ---------------- */
function renderPlanTab() {
  const p = state.project, body = $("#tabBody");
  if (!p.plan) {
    if (p.meta.status === "waiting_for_paste") return renderManual(body);
    body.innerHTML = `<section class="card muted">The plan will appear here when research and writing finish (usually 2–6 minutes).</section>`;
    return;
  }
  const r = p.plan.research, checks = p.checks || {};
  const sec = (title, a) => (a && a.length ? `<h3>${title}</h3><ul>${a.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : "");
  const pills = [r.brand, r.category].filter(Boolean).map((x) => `<span class="pill">${esc(x)}</span>`).join("");
  body.innerHTML = `
    <section class="card"><h2>Research</h2>
      <div>${pills}${r.price_thb ? `<span class="pill y">฿${esc(r.price_thb)}</span>` : ""}${r.original_price_thb ? `<span class="pill">was ฿${esc(r.original_price_thb)}</span>` : ""}
        ${r.target_audience ? `<span class="pill">👥 ${esc(r.target_audience)}</span>` : ""}</div>
      <div class="grid2"><div>${sec("Key features", r.key_features)}${sec("Pain points", r.pain_points)}${sec("Objections", r.objections)}${sec("Proof points", r.proof_points)}</div>
        <div>${sec("What works in this niche now", r.niche_trends)}${sec("Competitor hooks", r.competitor_hooks)}${sec("Compliance", r.compliance_notes)}</div></div>
      ${p.research_md ? `<details><summary>Full research notes</summary><div class="script">${esc(p.research_md)}</div></details>` : ""}
      ${r.sources?.length ? `<details><summary>${r.sources.length} sources</summary><ul>${r.sources.map((s) => `<li><a href="${esc(s)}" target="_blank" rel="noopener">${esc(s)}</a></li>`).join("")}</ul></details>` : ""}
      ${(checks.warnings || []).length ? `<p class="warn">⚠ ${checks.warnings.map(esc).join("<br>⚠ ")}</p>` : ""}
    </section>
    ${p.plan.videos.map((v, vi) => videoCard(v, vi, (checks.compliance || {})[v.id] || [])).join("")}
    <section class="card"><details><summary>Advanced: edit the whole plan as JSON</summary>
      <textarea id="planJson" rows="16" style="font-family:ui-monospace,Menlo,monospace;font-size:12px">${esc(JSON.stringify(p.plan, null, 2))}</textarea>
      <div class="row"><button id="btnSaveJson">Save JSON</button></div></details></section>`;
  body.querySelectorAll("[data-save]").forEach((b) => (b.onclick = () => saveBeats(+b.dataset.save)));
  $("#btnSaveJson").onclick = async () => {
    try { await api(P() + "/plan", { method: "POST", json: { plan: JSON.parse($("#planJson").value) } }); toast("Saved"); openProject(state.pid, true); }
    catch (e) { toast(e.message, 5000); }
  };
}

function videoCard(v, vi, flags) {
  const s = v.score;
  const hard = flags.filter((f) => f.level === "hard");
  const crit = ["hook_strength", "pain_or_desire", "proof_demo", "offer_clarity", "trend_fit", "filmability", "compliance_safety"];
  const total = v.timeline.reduce((a, b) => a + b.duration, 0);
  return `<section class="card" id="vc${vi}">
    <div class="vhead"><div style="display:flex"><span class="rank">#${v.rank}</span><div><h2>${esc(v.id)} · ${esc(v.title_th)}</h2>
      <span class="pill">${esc(v.format)}</span><span class="pill">hook: ${esc(v.hook_type)}</span><span class="pill">${esc(v.audio_mode)}</span>
      <span class="pill">~${Math.round(total)}s</span><span class="pill">${esc(v.theme)}</span>
      ${hard.length ? `<span class="pill r">⚠ ${hard.length} risky claim(s)</span>` : `<span class="pill g">claims OK</span>`}</div></div>
      <div style="min-width:180px"><div class="score"><b>${Math.round(s.total)}</b><div class="bar"><i style="width:${s.total}%"></i></div></div>
      <div class="muted" style="font-size:11px">${crit.map((c) => `${c.replace(/_/g, " ")} ${s[c]}`).join(" · ")}</div></div></div>
    <p><b>Angle:</b> ${esc(v.angle_en)}<br><b>Why it works:</b> ${esc(v.why_it_works_en)}</p>
    ${flags.length ? `<p class="${hard.length ? "bad" : "warn"}">Compliance: ${flags.map((f) => `“${esc(f.word)}” in ${esc(f.where)}`).join(", ")}</p>` : ""}
    <h3>Script (Thai)</h3><div class="script">${esc(v.full_script_th)}</div>
    <h3>Shot list (what to film)</h3>
    <table><tr><th>Shot</th><th>Size</th><th>What to film</th><th>How</th><th>Line</th><th>Rec.</th></tr>
      ${v.shots.map((sh) => `<tr><td class="id">${esc(sh.id)}</td><td>${esc(sh.shot_size.replace(/_/g, " "))}</td><td>${esc(sh.what_to_film_th)}</td><td>${esc(sh.how_to_film_th)}</td><td>${esc(sh.dialogue_th) || "—"}${sh.audio === "sync" ? " 🎙" : ""}</td><td>≥${sh.min_seconds}s</td></tr>`).join("")}</table>
    <details><summary>Edit plan · ${v.timeline.length} beats (voice, captions, timing, graphics)</summary>
      <table><tr><th>#</th><th>Shot</th><th>Sec</th><th>Spoken (Thai)</th><th>Captions (one per line)</th><th>Graphics text</th></tr>
      ${v.timeline.map((b, bi) => `<tr data-v="${vi}" data-b="${bi}"><td>${bi + 1}<div class="beat-ov">${esc(b.role)}<br>${esc(b.effect)}</div></td>
        <td><select data-f="shot_id">${v.shots.map((sh) => `<option ${sh.id === b.shot_id ? "selected" : ""}>${esc(sh.id)}</option>`).join("")}</select></td>
        <td><input data-f="duration" type="number" step="0.1" min="0.4" value="${b.duration}" style="width:64px"></td>
        <td><textarea data-f="vo_th" rows="2">${esc(b.vo_th)}</textarea></td>
        <td><textarea data-f="captions" rows="2">${esc(b.captions.map((c) => c.text).join("\n"))}</textarea></td>
        <td>${b.overlays.map((o, oi) => `<div class="beat-ov">${esc(o.type)}</div><input data-o="${oi}" value="${esc(o.text)}">`).join("") || '<span class="muted">—</span>'}</td></tr>`).join("")}</table>
      <div class="row"><button data-save="${vi}">Save edits</button><span class="muted">Captions keep their highlight words where they still match.</span></div>
    </details>
    <p class="muted"><b>Post caption:</b> ${esc(v.post_caption_th)} ${esc(v.hashtags.join(" "))}</p>
  </section>`;
}

async function saveBeats(vi) {
  const plan = structuredClone(state.project.plan);
  const v = plan.videos[vi];
  document.querySelectorAll(`tr[data-v="${vi}"]`).forEach((tr) => {
    const b = v.timeline[+tr.dataset.b];
    b.shot_id = tr.querySelector('[data-f="shot_id"]').value;
    b.duration = parseFloat(tr.querySelector('[data-f="duration"]').value) || b.duration;
    b.vo_th = tr.querySelector('[data-f="vo_th"]').value.trim();
    const lines = tr.querySelector('[data-f="captions"]').value.split("\n").map((x) => x.trim()).filter(Boolean);
    b.captions = lines.map((t, i) => ({ text: t, highlight: (b.captions[i]?.highlight || []).filter((h) => t.includes(h)) }));
    tr.querySelectorAll("[data-o]").forEach((inp) => { b.overlays[+inp.dataset.o].text = inp.value; });
  });
  try { await api(P() + "/plan", { method: "POST", json: { plan } }); toast("Saved"); openProject(state.pid, true); }
  catch (e) { toast(e.message, 5000); }
}

function renderManual(body) {
  const p = state.project;
  body.innerHTML = `<section class="card"><h2>Free mode: copy → ChatGPT / Claude → paste back</h2>
    <ol><li>Click <b>Copy prompt</b>.</li><li>Open <a href="https://chatgpt.com" target="_blank">chatgpt.com</a> or <a href="https://claude.ai" target="_blank">claude.ai</a> (web search ON), paste, send.${p.input?.images?.length ? " Also attach your screenshot(s)." : ""}</li>
      <li>Copy the whole JSON answer and paste it below.</li></ol>
    <div class="row"><button class="primary" id="btnCopy">Copy prompt</button><span class="muted">${Math.round(p.manual_prompt.length / 1000)}k characters</span></div>
    <label>Paste the JSON answer</label><textarea id="pasteBox" rows="10" placeholder='{"research": {...}, "videos": [...]}'></textarea>
    <div class="row"><button class="primary" id="btnImport">Import plan</button></div></section>`;
  $("#btnCopy").onclick = async () => { await navigator.clipboard.writeText(p.manual_prompt); toast("Prompt copied"); };
  $("#btnImport").onclick = async () => {
    try { await api(P() + "/paste", { method: "POST", json: { text: $("#pasteBox").value } }); toast("Plan imported ✓"); openProject(state.pid, true); }
    catch (e) { toast(e.message, 6000); }
  };
}

/* ---------------- tab 2: edit ---------------- */
function renderEditTab() {
  const p = state.project, body = $("#tabBody");
  if (!p.plan) { body.innerHTML = `<section class="card muted">Create the plan first (tab 1).</section>`; return; }
  const a = p.assign || { shots: {}, vo: {}, music: [] };
  const vids = p.files.filter((f) => f.kind === "video" || f.kind === "image");
  const auds = p.files.filter((f) => f.kind === "audio");
  const opt = (list, sel) => `<option value="">— none —</option>` + list.map((f) => `<option ${f.name === sel ? "selected" : ""} value="${esc(f.name)}">${esc(f.name)}${f.duration ? ` (${f.duration}s)` : ""}</option>`).join("");
  const running = (p.jobs || []).some((j) => j.kind === "render" && j.status === "running");
  body.innerHTML = `
    <section class="card"><h2>1. Drop all your footage</h2>
      <p class="muted">Videos, photos, your voice-over (name it <code>V1-VO.m4a</code>) and optional background music — all at once.
      Name clips by shot id (<code>V1-S01.mov</code>) for perfect matching; unnamed clips are matched in recording order and you can fix them below.</p>
      <div class="drop" id="footDrop">Drop files here or <u>browse</u><input type="file" id="footFiles" multiple hidden accept="video/*,image/*,audio/*"></div>
      <div id="upProg"></div>
      <div class="row"><button class="ghost" id="btnFolder">Open footage folder</button><button class="ghost" id="btnRescan">↻ Rescan folder</button>
        <span class="muted">Huge files? Copy them into the footage folder in Finder, then Rescan.</span></div>
      <div class="files" style="margin-top:10px">${p.files.map((f) => `<div class="file"><div><b>${esc(f.name)}</b><br><span class="muted">${f.kind} · ${fmtSize(f.size)}${f.duration ? " · " + f.duration + "s" : ""}</span></div><button class="ghost danger" data-del="${esc(f.name)}">✕</button></div>`).join("") || '<span class="muted">No files yet.</span>'}</div>
    </section>
    <section class="card"><h2>2. Check the matching</h2>
      <label>Background music (optional, auto-ducked under the voice)</label>
      <select id="musicSel">${opt(auds, (a.music || [])[0])}</select>
      ${p.plan.videos.map((v) => `<h3>${esc(v.id)} · ${esc(v.title_th)} <span class="pill">${esc(v.audio_mode)}</span></h3>
        <table><tr><th>Shot</th><th>What it should show</th><th>File</th></tr>
        ${v.shots.map((sh) => `<tr><td class="id">${esc(sh.id)}</td><td>${esc(sh.what_to_film_th)}</td><td><select data-shot="${esc(sh.id)}">${opt(vids, a.shots[sh.id])}</select>${a.shots[sh.id] ? "" : (sh.shot_size === "product_photo" && p.product_images.length ? ' <span class="muted">uses product photo</span>' : ' <span class="warn">missing</span>')}</td></tr>`).join("")}
        ${v.audio_mode === "voiceover" ? `<tr><td class="id">${esc(v.id)} voice</td><td>Your recorded voice-over (optional — otherwise the Thai TTS voice reads it)</td><td><select data-vo="${esc(v.id)}">${opt(auds, a.vo[v.id])}</select></td></tr>` : ""}
        </table>`).join("")}
      <div class="row"><button id="btnSaveAssign">Save matching</button></div>
    </section>
    <section class="card"><h2>3. Render</h2>
      <div class="row">${p.plan.videos.map((v) => `<label style="margin:0;font-weight:400"><input type="checkbox" class="vchk" value="${esc(v.id)}" checked style="width:auto"> ${esc(v.id)}</label>`).join(" ")}</div>
      <div class="row"><button class="primary" id="btnRender" ${running ? "disabled" : ""}>🎬 Render selected</button>
        <button id="btnDraft" ${running ? "disabled" : ""}>Quick draft (fast, lower quality)</button></div>
    </section>
    <section class="card"><h2>Finished videos</h2>
      <div class="renders">${p.renders.map((r) => `<div><video src="${F("renders/" + r.name)}" controls preload="metadata"></video>
        <div class="row" style="margin-top:6px"><a href="${F("renders/" + r.name)}?download=1"><button>⬇ ${esc(r.name)}</button></a></div></div>`).join("") || '<span class="muted">Nothing rendered yet.</span>'}</div>
      <div class="row"><button class="ghost" id="btnRendersFolder">Open renders folder</button></div>
    </section>`;
  const drop = $("#footDrop"), input = $("#footFiles");
  drop.onclick = () => input.click();
  input.onchange = () => upload([...input.files]);
  dnd(drop, upload);
  $("#btnFolder").onclick = () => api(P() + "/reveal", { method: "POST", json: { sub: "footage" } }).catch((e) => toast(e.message, 6000));
  $("#btnRendersFolder").onclick = () => api(P() + "/reveal", { method: "POST", json: { sub: "renders" } }).catch((e) => toast(e.message, 6000));
  $("#btnRescan").onclick = () => openProject(state.pid, true);
  body.querySelectorAll("[data-del]").forEach((b) => (b.onclick = async () => {
    if (!confirm(`Delete ${b.dataset.del}?`)) return;
    await api(`${P()}/files/${encodeURIComponent(b.dataset.del)}`, { method: "DELETE" }); openProject(state.pid, true);
  }));
  $("#btnSaveAssign").onclick = async () => { await saveAssign(); toast("Matching saved"); openProject(state.pid, true); };
  $("#btnRender").onclick = () => startRender(false);
  $("#btnDraft").onclick = () => startRender(true);
}
async function saveAssign() {
  const shots = {}, vo = {};
  document.querySelectorAll("[data-shot]").forEach((s) => { if (s.value) shots[s.dataset.shot] = s.value; });
  document.querySelectorAll("[data-vo]").forEach((s) => { if (s.value) vo[s.dataset.vo] = s.value; });
  const m = $("#musicSel").value;
  await api(P() + "/assign", { method: "POST", json: { shots, vo, music: m ? [m] : [] } });
}
async function startRender(draft) {
  await saveAssign();
  const videos = [...document.querySelectorAll(".vchk:checked")].map((c) => c.value);
  if (!videos.length) return toast("Select at least one video");
  try { const r = await api(P() + "/render", { method: "POST", json: { videos, draft } }); window.scrollTo(0, 0); pollJob(r.job.id); $("#jobBox").innerHTML = jobHtml(r.job); }
  catch (e) { toast(e.message, 5000); }
}
function upload(files) {
  if (!files.length) return;
  const fd = new FormData(); files.forEach((f) => fd.append("files", f, f.name));
  const xhr = new XMLHttpRequest();
  xhr.open("POST", P() + "/upload");
  xhr.upload.onprogress = (e) => { if (e.lengthComputable) $("#upProg").innerHTML = `<div class="progress"><i style="width:${(e.loaded / e.total) * 100}%"></i></div><span class="muted">Uploading ${files.length} file(s)… ${Math.round((e.loaded / e.total) * 100)}%</span>`; };
  xhr.onload = () => { toast(xhr.status < 400 ? `Added ${files.length} file(s)` : "Upload failed"); openProject(state.pid, true); };
  xhr.onerror = () => toast("Upload failed");
  xhr.send(fd);
}

/* ---------------- settings ---------------- */
function showSettings() {
  const s = state.settings;
  modal(`<h2>Settings</h2>
    <label>AI for research + scripts (Tool 1 only — the editor never uses AI)</label>
    <select id="sProvider"><option value="claude">Claude (API key)</option><option value="openai">ChatGPT (API key)</option><option value="manual">Free: copy/paste into ChatGPT or Claude chat</option></select>
    <div class="grid2"><div><label>Claude API key</label><input id="sAk" value="${esc(s.anthropic_api_key)}" placeholder="sk-ant-..."></div>
      <div><label>Claude model</label><input id="sCm" value="${esc(s.claude_model)}"></div></div>
    <div class="grid2"><div><label>OpenAI API key</label><input id="sOk" value="${esc(s.openai_api_key)}" placeholder="sk-..."></div>
      <div><label>OpenAI model</label><input id="sOm" value="${esc(s.openai_model)}"></div></div>
    <div class="grid2"><div><label>Videos per product</label><input id="sN" type="number" min="1" max="8" value="${s.videos_per_product}"></div>
      <div><label>Claude effort</label><select id="sEff">${["medium", "high", "xhigh"].map((x) => `<option ${x === s.claude_effort ? "selected" : ""}>${x}</option>`).join("")}</select></div></div>
    <div class="grid2"><div><label>Thai TTS voice (macOS)</label><input id="sVoice" value="${esc(s.tts_voice)}"></div>
      <div><label>Voice speed (words/min)</label><input id="sRate" type="number" value="${s.tts_rate}"></div></div>
    <div class="grid2"><div><label>Music volume (0–1)</label><input id="sMv" type="number" step="0.02" value="${s.music_volume}"></div>
      <div><label>Export quality (CRF, lower = better)</label><input id="sCrf" type="number" value="${s.render_crf}"></div></div>
    <label>Your top-video dataset (optional)</label>
    <p class="muted" style="margin:0 0 6px">Export your inspiration sheet as CSV (columns like Transcription, Plays, Video Duration…). The top 25 Thai videos become live examples for every script.</p>
    <div class="row" style="margin-top:0"><input type="file" id="sCsv" accept=".csv,text/csv" style="width:auto"><button id="sCsvBtn">Import CSV</button><span id="sCsvSt" class="muted"></span></div>
    <p class="muted">Keys are stored only on this Mac in ~/ThaiTikTokStudio/settings.json.</p>
    <div class="row"><button class="primary" id="sSave">Save</button><button class="ghost" onclick="closeModal()">Cancel</button></div>`);
  $("#sProvider").value = s.provider;
  api("/api/inspiration").then((r) => { $("#sCsvSt").textContent = r.exists ? "✓ dataset loaded" : "none loaded"; });
  $("#sCsvBtn").onclick = async () => {
    const f = $("#sCsv").files[0]; if (!f) return toast("Choose a CSV first");
    const fd = new FormData(); fd.append("file", f);
    try { const r = await api("/api/inspiration", { method: "POST", body: fd }); $("#sCsvSt").textContent = `✓ ${r.examples} examples imported`; }
    catch (e) { toast(e.message, 5000); }
  };
  $("#sSave").onclick = async () => {
    state.settings = await api("/api/settings", { method: "POST", json: {
      provider: $("#sProvider").value, anthropic_api_key: $("#sAk").value.trim(), claude_model: $("#sCm").value.trim(),
      openai_api_key: $("#sOk").value.trim(), openai_model: $("#sOm").value.trim(), videos_per_product: +$("#sN").value || 5,
      claude_effort: $("#sEff").value, tts_voice: $("#sVoice").value.trim(), tts_rate: +$("#sRate").value || 185,
      music_volume: +$("#sMv").value || 0.14, render_crf: +$("#sCrf").value || 20 } });
    closeModal(); toast("Settings saved"); if (!state.pid) showNew();
  };
}

boot();
