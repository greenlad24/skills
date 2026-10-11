/* Thai TikTok Studio — single-page UI (vanilla JS, no build step). */
const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const state = { pid: null, project: null, tab: "plan", settings: null, polls: {}, newFiles: [] };

async function api(path, opts = {}) {
  const o = { ...opts };
  if (o.json !== undefined) { o.body = JSON.stringify(o.json); o.headers = { "Content-Type": "application/json" }; delete o.json; }
  const r = await fetch(path, o);
  const data = await r.json().catch(() => ({}));
  if (r.status === 401) { location.href = "/login"; throw new Error("Please log in"); }
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
    state.server = !!h.server;
    if (h.server) document.body.classList.add("server");
    $("#ver").textContent = "v" + h.version;
    $("#health").innerHTML = (h.ffmpeg ? '<span class="ok">● editor ready</span>' : '<span class="bad">● ffmpeg missing</span>')
      + (h.claude_code ? ' · <span class="ok">Claude Code ✓</span>' : ' · <span class="muted" title="Needed only for the \'Your Claude account\' mode">Claude Code ✗</span>');
  } catch (e) { $("#health").textContent = "server offline"; }
  state.settings = await api("/api/settings");
  await loadProjects();
  const pid = location.hash.slice(1);
  if (pid) openProject(decodeURIComponent(pid)); else showNew();
  if (!state.settings.onboarded) showOnboarding(0);
}
$("#btnHelp").onclick = () => showOnboarding(0);
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
  $("#providerNote").innerHTML = prov === "claude_code" ? "AI: <b>your Claude account</b> (setup-token) · change in Settings"
    : prov === "manual" ? "Mode: <b>free copy/paste</b> into ChatGPT or Claude chat"
    : `AI: <b>${prov === "openai" ? "ChatGPT (" + esc(state.settings.openai_model) + ")" : "Claude (" + esc(state.settings.claude_model) + ")"}</b> · change in Settings`;
  const drop = $("#newDrop"), input = $("#newFiles");
  drop.onclick = () => input.click();
  input.onchange = () => addNewFiles([...input.files]);
  dnd(drop, (files) => addNewFiles(files.filter((f) => f.type.startsWith("image/"))));
  $("#btnGenerate").onclick = generate;
  $("#main").insertAdjacentHTML("afterbegin", `<div class="coach"><span class="step">ขั้นที่ 1</span>
    <span class="what">พิมพ์ชื่อสินค้า หรือวางลิงก์ หรือวางรูปหน้าจอสินค้า (กด ⌘V ได้เลย) แล้วกด <b>Generate videos</b> — ระบบจะค้นข้อมูลและเขียนสคริปต์ให้ 5 แบบ</span>
    <button class="ghost" onclick="showOnboarding(0)">ดูวิธีใช้</button></div>`);
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
    ${coachHtml(p)}
    <div class="tabs"><button class="tab ${state.tab === "plan" ? "active" : ""}" data-tab="plan">1 · Scripts & shot lists</button>
      <button class="tab ${state.tab === "edit" ? "active" : ""}" data-tab="edit">2 · Auto-edit videos</button></div>
    <div id="tabBody"></div>`;
  document.querySelectorAll(".tab").forEach((b) => (b.onclick = () => { state.tab = b.dataset.tab; renderProject(); }));
  $("#lnkFolder").onclick = (e) => { e.preventDefault(); api(P() + "/reveal", { method: "POST", json: {} }).catch((er) => toast(er.message, 6000)); };
  $("#btnReplan").onclick = async () => { if (!confirm("Run research + script writing again? (Your edits to this plan will be replaced.)")) return; const r = await api(P() + "/replan", { method: "POST" }); pollJob(r.job.id); };
  $("#btnDelete").onclick = async () => { if (!confirm("Delete this product and all its files?")) return; await api(P(), { method: "DELETE" }); showNew(); };
  const cb = $("#coachBtn");
  if (cb) cb.onclick = () => coachAction(cb.dataset.act);
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
const STYLES = { bouncy: "Bouncy — pops & drop-bounces", punchy: "Punchy — stamps & hard hits", smooth: "Smooth — fades & wipe reveals", playful: "Playful — swings & spins", minimal: "Minimal — soft fades" };
function fileCards(list, kind) {
  return list.map((f) => `<div class="file"><div><b>${esc(f.name)}</b><br><span class="muted">${f.kind} · ${fmtSize(f.size)}${f.duration ? " · " + f.duration + "s" : ""}</span></div><button class="ghost danger" data-del="${esc(f.name)}" data-kind="${kind}">✕</button></div>`).join("");
}
function renderEditTab() {
  const p = state.project, body = $("#tabBody");
  if (!p.plan) { body.innerHTML = `<section class="card muted">Create the plan first (tab 1).</section>`; return; }
  const a = p.assign || { shots: {}, vo: {}, music: [], narration: {} };
  const vids = p.files.filter((f) => f.kind === "video" || f.kind === "image");
  const auds = p.files.filter((f) => f.kind === "audio");
  const nars = p.narration || [];
  const opt = (list, sel) => `<option value="">— none —</option>` + list.map((f) => `<option ${f.name === sel ? "selected" : ""} value="${esc(f.name)}">${esc(f.name)}${f.duration ? ` (${f.duration}s)` : ""}</option>`).join("");
  const running = (p.jobs || []).some((j) => j.kind === "render" && j.status === "running");
  body.innerHTML = `
    <section class="card"><h2>1. Drop all your clips</h2>
      <p class="muted">Videos, photos and optional background music — any filenames. Clips are matched to the shot list by recording time and type (talking vs. B-roll).
      Film the shots in list order for the best match; for retakes the last take is used. You can change any match below.</p>
      <div class="drop" id="footDrop">Drop clips here or <u>browse</u><input type="file" id="footFiles" multiple hidden accept="video/*,image/*,audio/*"></div>
      <div id="upProg"></div>
      <div class="row"><button class="ghost" id="btnFolder">Open clips folder</button><button class="ghost" id="btnRescan">↻ Rescan</button>
        <span class="muted localonly">Huge files? Copy them into the folder in Finder, then Rescan.</span></div>
      <div class="files" style="margin-top:10px">${fileCards(p.files, "footage") || '<span class="muted">No clips yet.</span>'}</div>
    </section>
    <section class="card"><h2>2. Your narration 🎙</h2>
      <p class="muted">Upload your narration — a video or audio of you reading the script (one take per video). The sound is taken from it,
      split into lines at your pauses and placed exactly on each beat. The picture of the narration video is not used.</p>
      <div class="drop" id="narDrop">Drop narration here or <u>browse</u><input type="file" id="narFiles" multiple hidden accept="video/*,audio/*"></div>
      <div id="narProg"></div>
      <div class="files" style="margin-top:10px">${fileCards(nars, "narration") || '<span class="muted">No narration yet.</span>'}</div>
      ${nars.length ? `<table style="margin-top:10px"><tr><th>Video</th><th>Narration</th></tr>${p.plan.videos.map((v) => `<tr><td class="id">${esc(v.id)} · ${esc(v.title_th)}</td><td><select data-nar="${esc(v.id)}">${opt(nars, a.narration[v.id])}</select></td></tr>`).join("")}</table>` : ""}
    </section>
    <section class="card"><h2>3. Check the matching</h2>
      <label>Background music (optional, auto-ducked under the voice)</label>
      <select id="musicSel">${opt(auds, (a.music || [])[0])}</select>
      ${p.plan.videos.map((v) => `<h3>${esc(v.id)} · ${esc(v.title_th)} <span class="pill">${a.narration[v.id] ? "narration" : esc(v.audio_mode)}</span></h3>
        <table><tr><th>Shot</th><th>What it should show</th><th>File</th></tr>
        ${v.shots.map((sh) => `<tr><td class="id">${esc(sh.id)}</td><td>${esc(sh.what_to_film_th)}</td><td><select data-shot="${esc(sh.id)}">${opt(vids, a.shots[sh.id])}</select>${a.shots[sh.id] ? "" : (sh.shot_size === "product_photo" && p.product_images.length ? ' <span class="muted">uses product photo</span>' : ' <span class="warn">missing</span>')}</td></tr>`).join("")}
        </table>`).join("")}
      ${(a.unmatched || []).length ? `<p class="muted">Not used (earlier retakes / extras): ${a.unmatched.map(esc).join(", ")}</p>` : ""}
      <div class="row"><button id="btnSaveAssign">Save matching</button></div>
    </section>
    <section class="card"><h2>4. Animation & render</h2>
      <table><tr><th></th><th>Video</th><th>Animation style</th><th></th></tr>
      ${p.plan.videos.map((v, vi) => `<tr><td><input type="checkbox" class="vchk" value="${esc(v.id)}" checked style="width:auto"></td>
        <td class="id">${esc(v.id)} · ${esc(v.title_th)}</td>
        <td><select data-style="${vi}">${Object.entries(STYLES).map(([k, lbl]) => `<option value="${k}" ${k === v.anim_style ? "selected" : ""}>${lbl}</option>`).join("")}</select></td>
        <td><button class="ghost" data-shuffle="${vi}" title="Same style, different random picks">🎲 New variation</button> <span class="muted">#${v.variation || 0}</span></td></tr>`).join("")}</table>
      <div class="row"><label style="margin:0">Versions per video</label>
        <select id="versions" style="width:auto"><option value="1">1</option><option value="2">2 (A/B test)</option><option value="3">3</option><option value="5">5 — every style</option></select>
        <span class="muted">Each extra version uses the next animation style.</span></div>
      <div class="row"><button class="primary" id="btnRender" ${running ? "disabled" : ""}>🎬 Render selected</button>
        <button id="btnDraft" ${running ? "disabled" : ""}>Quick draft (fast, lower quality)</button></div>
    </section>
    <section class="card"><h2>Finished videos</h2>
      <div class="renders">${p.renders.map((r) => `<div><video src="${F("renders/" + r.name)}" controls preload="metadata"></video>
        <div class="row" style="margin-top:6px"><a href="${F("renders/" + r.name)}?download=1"><button>⬇ ${esc(r.name)}</button></a></div></div>`).join("") || '<span class="muted">Nothing rendered yet.</span>'}</div>
      <div class="row"><button class="ghost" id="btnRendersFolder">Open renders folder</button></div>
    </section>`;
  const wire = (dropSel, inputSel, kind, prog) => {
    const drop = $(dropSel), input = $(inputSel);
    drop.onclick = () => input.click();
    input.onchange = () => upload([...input.files], kind, prog);
    dnd(drop, (files) => upload(files, kind, prog));
  };
  wire("#footDrop", "#footFiles", "footage", "#upProg");
  wire("#narDrop", "#narFiles", "narration", "#narProg");
  $("#btnFolder").onclick = () => api(P() + "/reveal", { method: "POST", json: { sub: "footage" } }).catch((e) => toast(e.message, 6000));
  $("#btnRendersFolder").onclick = () => api(P() + "/reveal", { method: "POST", json: { sub: "renders" } }).catch((e) => toast(e.message, 6000));
  $("#btnRescan").onclick = () => openProject(state.pid, true);
  body.querySelectorAll("[data-del]").forEach((b) => (b.onclick = async () => {
    if (!confirm(`Delete ${b.dataset.del}?`)) return;
    await api(`${P()}/files/${encodeURIComponent(b.dataset.del)}?kind=${b.dataset.kind}`, { method: "DELETE" }); openProject(state.pid, true);
  }));
  body.querySelectorAll("[data-style]").forEach((sel) => (sel.onchange = () => updateVideo(+sel.dataset.style, { anim_style: sel.value })));
  body.querySelectorAll("[data-shuffle]").forEach((b) => (b.onclick = () => {
    const v = state.project.plan.videos[+b.dataset.shuffle];
    updateVideo(+b.dataset.shuffle, { variation: (v.variation || 0) + 1 });
  }));
  $("#btnSaveAssign").onclick = async () => { await saveAssign(); toast("Matching saved"); openProject(state.pid, true); };
  $("#btnRender").onclick = () => startRender(false);
  $("#btnDraft").onclick = () => startRender(true);
}
async function updateVideo(vi, patch) {
  const plan = structuredClone(state.project.plan);
  Object.assign(plan.videos[vi], patch);
  try { await api(P() + "/plan", { method: "POST", json: { plan } }); state.project.plan = plan; toast(patch.anim_style ? "Style saved" : "New variation — render to see it"); renderEditTab(); }
  catch (e) { toast(e.message, 5000); }
}
async function saveAssign() {
  const shots = {}, narration = {};
  document.querySelectorAll("[data-shot]").forEach((s) => { if (s.value) shots[s.dataset.shot] = s.value; });
  document.querySelectorAll("[data-nar]").forEach((s) => { if (s.value) narration[s.dataset.nar] = s.value; });
  const m = $("#musicSel").value;
  await api(P() + "/assign", { method: "POST", json: { shots, vo: state.project.assign?.vo || {}, narration, music: m ? [m] : [] } });
}
async function startRender(draft) {
  await saveAssign();
  const videos = [...document.querySelectorAll(".vchk:checked")].map((c) => c.value);
  if (!videos.length) return toast("Select at least one video");
  const versions = +$("#versions").value || 1;
  try { const r = await api(P() + "/render", { method: "POST", json: { videos, draft, versions } }); window.scrollTo(0, 0); pollJob(r.job.id); $("#jobBox").innerHTML = jobHtml(r.job); }
  catch (e) { toast(e.message, 5000); }
}
function upload(files, kind = "footage", progSel = "#upProg") {
  if (!files.length) return;
  const fd = new FormData(); files.forEach((f) => fd.append("files", f, f.name));
  fd.append("mtimes", JSON.stringify(files.map((f) => f.lastModified || 0)));
  fd.append("kind", kind);
  const xhr = new XMLHttpRequest();
  xhr.open("POST", P() + "/upload");
  xhr.upload.onprogress = (e) => { if (e.lengthComputable) $(progSel).innerHTML = `<div class="progress"><i style="width:${(e.loaded / e.total) * 100}%"></i></div><span class="muted">Uploading ${files.length} file(s)… ${Math.round((e.loaded / e.total) * 100)}%</span>`; };
  xhr.onload = () => { toast(xhr.status < 400 ? `Added ${files.length} file(s)` : "Upload failed"); openProject(state.pid, true); };
  xhr.onerror = () => toast("Upload failed");
  xhr.send(fd);
}

/* ---------------- settings ---------------- */
function showSettings() {
  const s = state.settings;
  modal(`<h2>Settings</h2>
    <label>AI for research + scripts (Tool 1 only — the editor never uses AI)</label>
    <select id="sProvider"><option value="claude_code">Your Claude account (claude setup-token) — recommended</option><option value="claude">Claude (API key)</option><option value="openai">ChatGPT (API key)</option><option value="manual">Free: copy/paste into ChatGPT or Claude chat</option></select>
    <label>Claude setup-token <span class="muted">(Terminal: <code>claude setup-token</code>)</span></label>
    <input id="sCct" value="${esc(s.claude_code_token)}" placeholder="sk-ant-oat01-...">
    <div class="grid2"><div><label>Claude API key</label><input id="sAk" value="${esc(s.anthropic_api_key)}" placeholder="sk-ant-..."></div>
      <div><label>Claude model</label><input id="sCm" value="${esc(s.claude_model)}"></div></div>
    <div class="grid2"><div><label>OpenAI API key</label><input id="sOk" value="${esc(s.openai_api_key)}" placeholder="sk-..."></div>
      <div><label>OpenAI model</label><input id="sOm" value="${esc(s.openai_model)}"></div></div>
    <div class="grid2"><div><label>Videos per product</label><input id="sN" type="number" min="1" max="8" value="${s.videos_per_product}"></div>
      <div><label>Claude effort</label><select id="sEff">${["medium", "high", "xhigh"].map((x) => `<option ${x === s.claude_effort ? "selected" : ""}>${x}</option>`).join("")}</select></div></div>
    <label>Voice-over</label>
    <select id="sVsrc"><option value="mine">My own voice (record each script in one take)</option><option value="tts">Computer Thai voice (macOS Kanya)</option></select>
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
  $("#sVsrc").value = s.voice_source || "mine";
  api("/api/inspiration").then((r) => { $("#sCsvSt").textContent = r.exists ? "✓ dataset loaded" : "none loaded"; });
  $("#sCsvBtn").onclick = async () => {
    const f = $("#sCsv").files[0]; if (!f) return toast("Choose a CSV first");
    const fd = new FormData(); fd.append("file", f);
    try { const r = await api("/api/inspiration", { method: "POST", body: fd }); $("#sCsvSt").textContent = `✓ ${r.examples} examples imported`; }
    catch (e) { toast(e.message, 5000); }
  };
  $("#sSave").onclick = async () => {
    state.settings = await api("/api/settings", { method: "POST", json: {
      provider: $("#sProvider").value, claude_code_token: $("#sCct").value.trim(), anthropic_api_key: $("#sAk").value.trim(), claude_model: $("#sCm").value.trim(),
      openai_api_key: $("#sOk").value.trim(), openai_model: $("#sOm").value.trim(), videos_per_product: +$("#sN").value || 5,
      claude_effort: $("#sEff").value, voice_source: $("#sVsrc").value, tts_voice: $("#sVoice").value.trim(), tts_rate: +$("#sRate").value || 185,
      music_volume: +$("#sMv").value || 0.14, render_crf: +$("#sCrf").value || 20 } });
    closeModal(); toast("Settings saved"); if (!state.pid) showNew();
  };
}

boot();


/* ---------------- Thai onboarding (shown once; ❓ วิธีใช้ reopens it) ---------------- */
const OB_STEPS = [
  () => `<div class="big">👋</div><h2>ยินดีต้อนรับสู่ Thai TikTok Studio</h2>
    <p>โปรแกรมนี้ช่วยให้คุณทำคลิปขายของบน TikTok ได้ง่ายมาก มี <b>2 เครื่องมือ</b>:</p>
    <ol><li><b>ผู้ช่วยเขียนสคริปต์</b> — ใส่ชื่อสินค้า ได้สคริปต์ไวรัล 5 แบบ พร้อมรายการช็อตที่ต้องถ่าย</li>
      <li><b>โปรแกรมตัดต่ออัตโนมัติ</b> — ลากคลิปกับเสียงพากย์ใส่ ได้คลิปพร้อมโพสต์ มีซับไตเติลและแอนิเมชันให้เอง</li></ol>
    <div class="flow"><span>📝 ใส่ชื่อสินค้า</span><b>→</b><span>📜 ได้ 5 สคริปต์</span><b>→</b><span>🎬 ถ่ายคลิป</span><b>→</b><span>🎙 อัดเสียง</span><b>→</b><span>📂 ลากไฟล์ใส่</span><b>→</b><span>✅ ได้คลิป</span></div>
    <div class="tip">ใช้เวลาอ่านคู่มือนี้แค่ 1 นาที</div>`,
  () => {
    const p = state.settings.provider;
    const c = (v, t, d) => `<label class="choice ${p === v ? "on" : ""}" data-prov="${v}"><b>${t}</b><br><span class="muted">${d}</span></label>`;
    return `<div class="big">⚙️</div><h2>ตั้งค่า AI (ทำครั้งเดียว)</h2>
    <p>เลือกวิธีให้ AI เขียนสคริปต์:</p>
    ${c("claude_code", "🔑 บัญชี Claude ของคุณ (แนะนำ)", "ใช้แพ็กเกจ Claude ที่คุณมีอยู่ (Pro/Max) ไม่เสียเงินเพิ่ม — เปิด Terminal พิมพ์ <code>claude setup-token</code> แล้ววางโทเค็นด้านล่าง")}
    ${c("manual", "🆓 ฟรี — คัดลอกไปวางใน ChatGPT / Claude เอง", "ไม่ต้องมีคีย์ เหมาะสำหรับเริ่มต้น โปรแกรมจะเตรียมข้อความให้ คุณแค่คัดลอก-วาง")}
    ${c("claude", "⚡ Claude (อัตโนมัติ)", "ใส่ API key ครั้งเดียว ระบบทำทุกอย่างเอง ค่าใช้จ่ายประมาณไม่กี่บาทถึง ~30 บาทต่อสินค้า")}
    ${c("openai", "⚡ ChatGPT (อัตโนมัติ)", "ใส่ OpenAI API key ครั้งเดียว ระบบทำทุกอย่างเอง")}
    <div id="obKeyBox" class="${p === "manual" ? "hidden" : ""}"><label>โทเค็น / API key</label><input id="obKey" placeholder="วางโทเค็นหรือ API key ที่นี่ (เก็บไว้ในเครื่องนี้เท่านั้น)"></div>
    <div class="tip">เปลี่ยนได้ทุกเมื่อที่ปุ่ม ⚙ Settings มุมขวาบน</div>`;
  },
  () => `<div class="big">📜</div><h2>เครื่องมือ 1: สร้างสคริปต์</h2>
    <ol><li>กด <b>＋ New product</b> (ซ้ายบน)</li>
      <li>พิมพ์ชื่อสินค้า หรือวางลิงก์ TikTok Shop / Shopee / Lazada หรือวางรูปหน้าจอ</li>
      <li>กด <b>Generate videos</b> แล้วรอ 2–6 นาที</li></ol>
    <p>คุณจะได้: ข้อมูลสินค้า · <b>สคริปต์ 5 แบบ</b> เรียงจากโอกาสไวรัลมากสุด · รายการช็อตที่ต้องถ่าย · ปุ่ม <b>🖨 Filming pack</b> สำหรับพิมพ์ไปให้คนถ่าย</p>
    <div class="tip">💡 สคริปต์จะไม่บอกราคาขายจริง — พูดได้แค่ "ที่ห้างราคา…" แล้วตามด้วย "แต่เจอตัวนี้ในราคาพิเศษ" และบนจอจะไม่มีตัวเลขราคาเลย</div>`,
  () => `<div class="big">🎬</div><h2>ถ่ายคลิป</h2>
    <ul><li>ถ่าย <b>แนวตั้ง</b> 9:16</li>
      <li>ถ่าย <b>ตามลำดับ</b> ในรายการช็อต (V1-S01, V1-S02 …)</li>
      <li><b>ไม่ต้องตั้งชื่อไฟล์</b> — ระบบจับคู่ให้เองจากเวลาที่ถ่าย</li>
      <li>ถ่ายเผื่อหัว-ท้ายช็อตละ 2–3 วินาที</li>
      <li>ถ่ายซ้ำได้ ระบบจะใช้ <b>เทคสุดท้าย</b></li>
      <li>iPhone: ปิด HDR (ตั้งค่า → กล้อง → บันทึกวิดีโอ) สีจะไม่ซีด</li></ul>`,
  () => `<div class="big">🎙</div><h2>อัดเสียงพากย์ด้วยเสียงของคุณ</h2>
    <ul><li>เปิด Filming pack ดูหัวข้อ <b>🎙 อัดเสียงพากย์</b> ของแต่ละคลิป</li>
      <li>อ่าน <b>ทุกบรรทัดต่อกันในเทคเดียว</b> เว้นจังหวะสั้นๆ (ครึ่งวินาที) ระหว่างบรรทัด</li>
      <li>อัดเป็น <b>วิดีโอหรือไฟล์เสียง</b> ก็ได้ — ระบบดึงเฉพาะเสียงมาใช้</li>
      <li>อัดในห้องเงียบ ถือมือถือห่างปากประมาณ 1 คืบ</li></ul>
    <div class="tip">ระบบจะตัดเสียงเป็นประโยคและวางให้ตรงกับภาพและซับไตเติลอัตโนมัติ</div>`,
  () => `<div class="big">✂️</div><h2>เครื่องมือ 2: ตัดต่ออัตโนมัติ</h2>
    <ol><li>เปิดสินค้า แล้วกดแท็บ <b>2 · Auto-edit videos</b></li>
      <li><b>ลากคลิปทั้งหมด</b> ใส่ช่องที่ 1 (ใส่เพลงประกอบด้วยก็ได้)</li>
      <li><b>ลากเสียงพากย์</b> ใส่ช่อง 🎙 แยกต่างหาก</li>
      <li>ตรวจการจับคู่ (เปลี่ยนได้ถ้าไม่ตรง)</li>
      <li>เลือกสไตล์แอนิเมชัน แล้วกด <b>🎬 Render</b></li>
      <li>ดาวน์โหลด MP4 แล้ว <b>โพสต์ได้เลย</b></li></ol>
    <div class="tip">อยากทดสอบหลายแบบ? เลือก "Versions per video" = 2–5 จะได้หลายเวอร์ชันแอนิเมชันไว้ทำ A/B test</div>`,
  () => `<div class="big">🎉</div><h2>พร้อมแล้ว!</h2>
    <p>ทุกหน้าจะมี <b>แถบ "ขั้นต่อไป"</b> ด้านบน บอกว่าต้องทำอะไรต่อ พร้อมปุ่มให้กด</p>
    <p>เปิดคู่มือนี้อีกครั้งได้ที่ปุ่ม <b>❓ วิธีใช้</b> มุมขวาบน</p>`,
];
let obStep = 0;
function showOnboarding(i) {
  obStep = i;
  const last = OB_STEPS.length - 1;
  modal(`<div class="ob">${OB_STEPS[i]()}
    <div class="dots">${OB_STEPS.map((_, k) => `<i class="${k === i ? "on" : ""}"></i>`).join("")}</div>
    <div class="row" style="justify-content:space-between">
      <button class="ghost" id="obSkip">${i === last ? "" : "ข้าม"}</button>
      <div class="row" style="margin:0">${i > 0 ? '<button id="obBack">← ย้อนกลับ</button>' : ""}
        <button class="primary" id="obNext">${i === last ? "เริ่มสินค้าแรก 🚀" : "ถัดไป →"}</button></div></div></div>`);
  $("#modal .modal-box").style.width = "min(640px,94vw)";
  document.querySelectorAll("[data-prov]").forEach((el) => (el.onclick = () => {
    document.querySelectorAll("[data-prov]").forEach((x) => x.classList.remove("on"));
    el.classList.add("on");
    $("#obKeyBox").classList.toggle("hidden", el.dataset.prov === "manual");
  }));
  const finish = async () => {
    state.settings = await api("/api/settings", { method: "POST", json: { onboarded: true } });
    closeModal();
    if (!state.pid) showNew();
  };
  $("#obSkip").onclick = finish;
  if ($("#obBack")) $("#obBack").onclick = () => showOnboarding(i - 1);
  $("#obNext").onclick = async () => {
    const sel = document.querySelector("[data-prov].on");
    if (sel) {  // AI setup step
      const upd = { provider: sel.dataset.prov };
      const key = ($("#obKey")?.value || "").trim();
      const field = { openai: "openai_api_key", claude: "anthropic_api_key", claude_code: "claude_code_token" }[sel.dataset.prov];
      if (key && field) upd[field] = key;
      if (field && !key && !state.settings[field]) return toast("กรุณาวางโทเค็น/API key หรือเลือกแบบฟรี");
      state.settings = await api("/api/settings", { method: "POST", json: upd });
    }
    if (i === last) return finish();
    showOnboarding(i + 1);
  };
}

/* ---------------- "next step" coach (Thai) ---------------- */
function nextStep(p) {
  const running = (p.jobs || []).find((j) => j.status === "running");
  const plan = p.plan, a = p.assign || {};
  const steps = ["สคริปต์", "ถ่ายคลิป", "อัดเสียง", "อัปโหลด", "เรนเดอร์", "โพสต์"];
  if (running && running.kind === "plan") return { at: 0, text: "⏳ กำลังค้นข้อมูลและเขียนสคริปต์… ใช้เวลา 2–6 นาที รอได้เลย ไม่ต้องทำอะไร", steps };
  if (running && running.kind === "render") return { at: 4, text: "⏳ กำลังตัดต่อ… ดูความคืบหน้าด้านบน เสร็จแล้วคลิปจะขึ้นในแท็บ 2", steps };
  if (!plan && p.meta.status === "waiting_for_paste") return { at: 0, text: "กด <b>Copy prompt</b> → วางใน ChatGPT หรือ Claude → คัดลอกคำตอบทั้งหมดกลับมาวางในช่องด้านล่าง แล้วกด <b>Import plan</b>", steps };
  if (!plan) return { at: 0, text: "ยังไม่มีสคริปต์ — กด <b>↻ Regenerate</b> เพื่อลองใหม่", steps, act: "replan", btn: "↻ ลองใหม่" };
  const shots = plan.videos.flatMap((v) => v.shots.map((s) => s.id));
  const have = shots.filter((id) => a.shots && a.shots[id]).length;
  const needVo = plan.videos.filter((v) => v.audio_mode === "voiceover" && !(a.narration || {})[v.id] && !(a.vo || {})[v.id]);
  if (!p.files.length) return { at: 1, text: "อ่านสคริปต์ด้านล่าง แล้วเปิด <b>🖨 Filming pack</b> ถ่ายคลิปตามรายการ (ไม่ต้องตั้งชื่อไฟล์) เสร็จแล้วไปแท็บ 2 ลากไฟล์ใส่", steps, act: "pack", btn: "🖨 เปิด Filming pack" };
  if (needVo.length) return { at: 2, text: `อัดเสียงพากย์สำหรับ <b>${needVo.map((v) => v.id).join(", ")}</b> (อ่านทุกบรรทัดในเทคเดียว) แล้วลากใส่ช่อง 🎙 ในแท็บ 2`, steps, act: "edit", btn: "ไปแท็บ 2" };
  if (have < shots.length) return { at: 3, text: `ยังขาดคลิป <b>${shots.length - have}</b> ช็อต — ถ่ายเพิ่มแล้วลากใส่ หรือกดเรนเดอร์ดูก่อนก็ได้ (ช็อตที่ขาดจะเป็นการ์ดสีเทา)`, steps, act: "edit", btn: "ไปแท็บ 2" };
  if (!p.renders.length) return { at: 4, text: "ทุกอย่างพร้อม! เลือกสไตล์แอนิเมชันแล้วกด <b>🎬 Render selected</b>", steps, act: "edit", btn: "ไปเรนเดอร์" };
  return { at: 5, text: "🎉 คลิปเสร็จแล้ว! ดาวน์โหลดในแท็บ 2 แล้วโพสต์ได้เลย — อยากได้แบบอื่นกด 🎲 New variation แล้วเรนเดอร์ใหม่", steps, act: "edit", btn: "ดูคลิป" };
}
function coachHtml(p) {
  const n = nextStep(p);
  return `<div class="track">${n.steps.map((s, k) => `<span class="${k < n.at ? "done" : k === n.at ? "now" : ""}">${k < n.at ? "✓ " : ""}${s}</span>`).join("")}</div>
    <div class="coach"><span class="step">ขั้นต่อไป</span><span class="what">${n.text}</span>${n.act ? `<button class="primary" id="coachBtn" data-act="${n.act}">${n.btn}</button>` : ""}</div>`;
}
function coachAction(act) {
  if (act === "pack") window.open(F("filming_pack.html"), "_blank");
  else if (act === "replan") $("#btnReplan").click();
  else if (act === "edit") { state.tab = "edit"; renderProject(); window.scrollTo(0, document.querySelector(".tabs").offsetTop - 70); }
}
