"""The Control Room page — single-file, self-contained, offline.

Design language: broadcast console. Dark surface, recessive chrome,
status always shown as dot + label (never color alone), meters as
single-hue magnitude bars, text in ink tokens.
"""

CONTROL_ROOM_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AutoDirector — Control Room</title>
<style>
:root{
  --bg:#0a0d12; --panel:#12161d; --panel-2:#161b24; --inset:#0d1117;
  --line:#222a35; --line-2:#2c3644;
  --ink:#e9eef5; --ink-2:#9fabb9; --muted:#5f6c7b;
  --accent:#4fb8ff; --accent-dim:#2a6a96;
  --ok:#3fd68f; --warn:#ffc24b; --bad:#ff5d5d;
  --live:#ff4652;
  --radius:12px;
  font-synthesis:none;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%}
body{
  background:
    radial-gradient(1200px 600px at 70% -10%, #101826 0%, transparent 60%),
    var(--bg);
  color:var(--ink);
  font:14px/1.45 -apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",Roboto,sans-serif;
  -webkit-font-smoothing:antialiased;
}
.mono{font-family:ui-monospace,"SF Mono",SFMono-Regular,Menlo,monospace}

/* ---------- header ---------- */
header{
  display:flex;align-items:center;gap:18px;
  padding:14px 22px;border-bottom:1px solid var(--line);
  background:rgba(13,17,23,.75);backdrop-filter:blur(10px);
  position:sticky;top:0;z-index:50;
}
.brand{display:flex;align-items:baseline;gap:10px}
.brand .logo{font-size:18px}
.brand .name{font-weight:700;letter-spacing:.14em;font-size:13px}
.brand .name em{color:var(--accent);font-style:normal}
.chip{
  font-size:10px;font-weight:700;letter-spacing:.12em;
  padding:4px 10px;border-radius:999px;border:1px solid var(--line-2);
  color:var(--ink-2);background:var(--panel-2);white-space:nowrap;
}
.pills{display:flex;gap:10px;margin-left:auto;align-items:center}
.pill{
  display:flex;align-items:center;gap:7px;font-size:11px;font-weight:600;
  letter-spacing:.06em;color:var(--ink-2);
  padding:5px 11px;border:1px solid var(--line);border-radius:999px;
  background:var(--inset);
}
.dot{width:8px;height:8px;border-radius:50%;background:var(--muted);flex:none}
.dot.ok{background:var(--ok);box-shadow:0 0 8px rgba(63,214,143,.5)}
.dot.bad{background:var(--bad);box-shadow:0 0 8px rgba(255,93,93,.5)}
.dot.warn{background:var(--warn)}

/* directing switch */
.switch{display:flex;align-items:center;gap:10px;cursor:pointer;user-select:none}
.switch .label{font-size:11px;font-weight:700;letter-spacing:.12em;color:var(--ink-2)}
.track{width:52px;height:28px;border-radius:999px;background:var(--inset);
  border:1px solid var(--line-2);position:relative;transition:all .2s}
.knob{width:22px;height:22px;border-radius:50%;background:var(--ink-2);
  position:absolute;top:2px;left:2px;transition:all .2s}
.switch.on .track{background:rgba(255,70,82,.18);border-color:var(--live)}
.switch.on .knob{left:26px;background:var(--live);box-shadow:0 0 12px rgba(255,70,82,.6)}
.iconbtn{background:var(--panel-2);border:1px solid var(--line-2);color:var(--ink-2);
  border-radius:9px;padding:7px 12px;font-size:12px;cursor:pointer;font-weight:600}
.iconbtn:hover{color:var(--ink);border-color:var(--accent-dim)}

/* ---------- layout ---------- */
main{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(320px,1fr);
  gap:16px;padding:18px 22px;max-width:1400px;margin:0 auto}
@media(max-width:960px){main{grid-template-columns:1fr}}
.col{display:flex;flex-direction:column;gap:16px;min-width:0}
.card{background:linear-gradient(180deg,var(--panel-2),var(--panel));
  border:1px solid var(--line);border-radius:var(--radius);padding:16px 18px}
.card h2{font-size:10px;font-weight:700;letter-spacing:.16em;color:var(--muted);
  text-transform:uppercase;margin-bottom:12px;display:flex;align-items:center;gap:8px}
.card h2 .spacer{margin-left:auto}

/* ---------- on air ---------- */
.onair-badge{display:inline-flex;align-items:center;gap:8px;font-size:10px;
  font-weight:800;letter-spacing:.18em;color:var(--live);
  border:1px solid rgba(255,70,82,.4);border-radius:6px;padding:4px 10px;
  background:rgba(255,70,82,.08)}
.onair-badge .dot{background:var(--live)}
.onair-badge.paused{color:var(--warn);border-color:rgba(255,194,75,.4);
  background:rgba(255,194,75,.07)}
.onair-badge.paused .dot{background:var(--warn);box-shadow:none}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}}
.onair-badge:not(.paused) .dot{animation:pulse 2s ease-in-out infinite}
.scene-name{font-size:34px;font-weight:800;letter-spacing:-.01em;margin:10px 0 2px;
  min-height:44px}
.scene-sub{color:var(--muted);font-size:12px}

/* ---------- confidence gauge ---------- */
.gauge{position:relative;height:14px;border-radius:999px;background:var(--inset);
  border:1px solid var(--line);overflow:hidden;margin:14px 0 6px}
.gauge .fill{height:100%;width:0%;border-radius:999px;
  background:linear-gradient(90deg,var(--accent-dim),var(--accent));
  transition:width .12s linear}
.gauge .tick{position:absolute;top:-3px;bottom:-3px;width:2px;
  background:rgba(255,255,255,.28)}
.shotpool{display:flex;flex-wrap:wrap;gap:8px}
.shot{font-size:12px;font-weight:600;color:var(--ink-2);padding:7px 13px;
  border:1px solid var(--line-2);border-radius:8px;background:var(--inset)}
.shot.on{color:#ffd8da;border-color:var(--live);background:rgba(255,70,82,.1);
  box-shadow:0 0 12px rgba(255,70,82,.15)}
.shot .k{font-size:9px;letter-spacing:.1em;color:var(--muted);display:block}
/* mixer console */
.strips{display:grid;grid-template-columns:repeat(auto-fill,minmax(148px,1fr));
  gap:10px}
.strip{border:1px solid var(--line);border-radius:9px;padding:10px;
  background:var(--inset);transition:border-color .15s}
.strip.active{border-color:rgba(79,184,255,.45)}
.strip .nm{font-size:12px;font-weight:700;display:flex;gap:6px;
  align-items:center;margin-bottom:6px;min-height:16px}
.strip .role{font-size:8px;font-weight:800;letter-spacing:.1em;
  color:var(--muted);border:1px solid var(--line-2);border-radius:4px;
  padding:1px 5px}
.strip .role.voc{color:#ffd8da;border-color:rgba(255,70,82,.4)}
.strip .fader{display:flex;align-items:center;gap:6px;margin-top:6px;
  font-size:11px}
.strip .fval{font-variant-numeric:tabular-nums;color:var(--ink)}
.tag.dead{color:#fff;background:var(--bad)}
.mixbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;
  margin-bottom:12px}
.masking{font-size:11px;color:var(--ink-2)}
.masking b.badval{color:var(--warn)}
.gauge-legend{display:flex;justify-content:space-between;color:var(--muted);
  font-size:10px;letter-spacing:.08em}
.state-row{display:flex;align-items:center;gap:10px;margin-top:12px}
.state-tag{font-size:12px;font-weight:800;letter-spacing:.14em;padding:6px 12px;
  border-radius:8px;border:1px solid var(--line-2);color:var(--ink-2)}
.state-tag.vocal{color:#ffd8da;border-color:rgba(255,70,82,.5);
  background:rgba(255,70,82,.1)}
.state-tag.inst{color:#cfe9ff;border-color:rgba(79,184,255,.4);
  background:rgba(79,184,255,.08)}
.cal-chip{margin-left:auto;font-size:11px;color:var(--ink-2)}
.cal-chip b{color:var(--ok)}
.cal-chip b.weak{color:var(--warn)}
.btn{background:var(--accent-dim);border:none;color:#eaf6ff;border-radius:8px;
  padding:8px 14px;font-size:12px;font-weight:700;cursor:pointer;letter-spacing:.04em}
.btn:hover{background:#337fb0}
.btn.ghost{background:transparent;border:1px solid var(--line-2);color:var(--ink-2)}
.btn.ghost:hover{color:var(--ink);border-color:var(--accent-dim)}
.btn.danger{background:rgba(255,93,93,.15);color:#ffb9b9;border:1px solid rgba(255,93,93,.4)}

/* ---------- speakers (podcast) ---------- */
.speakers{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:700px){.speakers{grid-template-columns:1fr}}
.speaker{border:1px solid var(--line);border-radius:10px;padding:14px;
  background:var(--inset);transition:border-color .15s, box-shadow .15s}
.speaker.talking{border-color:rgba(63,214,143,.55);
  box-shadow:0 0 0 1px rgba(63,214,143,.25), 0 0 18px rgba(63,214,143,.08)}
.speaker .top{display:flex;align-items:center;gap:8px;margin-bottom:10px}
.speaker .name{font-weight:700;font-size:15px}
.tag{font-size:9px;font-weight:800;letter-spacing:.12em;padding:3px 8px;
  border-radius:5px}
.tag.talk{color:#0e2b1d;background:var(--ok)}
.tag.floor{color:#241a03;background:var(--warn)}
.vu{position:relative;height:10px;border-radius:999px;background:#0a0e14;
  border:1px solid var(--line);overflow:hidden}
.vu .fill{height:100%;width:0%;background:linear-gradient(90deg,#2a6a96,var(--accent));
  transition:width .1s linear}
.vu .floorline{position:absolute;top:-2px;bottom:-2px;width:2px;background:var(--warn);opacity:.7}
.vu-scale{display:flex;justify-content:space-between;font-size:9px;color:var(--muted);
  margin-top:4px}
.chain{margin-top:12px;border-top:1px dashed var(--line);padding-top:10px;
  display:flex;flex-direction:column;gap:7px}
.rail{display:grid;grid-template-columns:110px 1fr 52px 24px;gap:8px;
  align-items:center;font-size:11px}
.rail .pname{color:var(--ink-2)}
.rail .bar{height:5px;border-radius:999px;background:#0a0e14;border:1px solid var(--line);
  position:relative;overflow:hidden}
.rail .bar i{position:absolute;top:0;bottom:0;left:0;background:var(--accent-dim);
  border-radius:999px}
.rail .val{text-align:right;color:var(--ink)}
.lock{cursor:pointer;opacity:.45;font-size:12px;background:none;border:none;
  color:var(--ink)}
.lock.frozen{opacity:1;color:var(--warn)}

/* ---------- log ---------- */
.log{display:flex;flex-direction:column;gap:0;max-height:70vh;overflow-y:auto}
.log::-webkit-scrollbar{width:8px}
.log::-webkit-scrollbar-thumb{background:var(--line-2);border-radius:99px}
.cut{display:flex;gap:12px;padding:9px 6px;border-bottom:1px solid #1a212b;
  align-items:baseline}
.cut:first-child{animation:flash 1.2s ease-out}
@keyframes flash{0%{background:rgba(79,184,255,.14)}100%{background:transparent}}
.cut .t{color:var(--muted);font-size:11px;flex:none;width:58px}
.cut .scene{font-weight:700;flex:none}
.cut .why{color:var(--ink-2);font-size:12px}
.cut.prio{border-left:3px solid var(--live);padding-left:8px}
.cut .ptag{font-size:8px;font-weight:800;letter-spacing:.1em;color:var(--live);
  border:1px solid rgba(255,70,82,.5);padding:2px 5px;border-radius:4px;flex:none}
.empty{color:var(--muted);font-size:12px;padding:20px 4px;text-align:center}

/* ---------- AI feed ---------- */
.ai-entry{padding:8px 6px;border-bottom:1px solid #1a212b;font-size:12px}
.ai-entry .head{display:flex;gap:8px;color:var(--ink)}
.ai-entry .why{color:var(--ink-2);margin-top:2px}
.badge-ai{font-size:9px;font-weight:800;letter-spacing:.1em;color:#0a0d12;
  background:linear-gradient(90deg,#d8b4fe,#818cf8);padding:2px 7px;border-radius:4px}

/* ---------- modal / drawer ---------- */
.overlay{position:fixed;inset:0;background:rgba(5,8,12,.7);backdrop-filter:blur(6px);
  display:none;align-items:center;justify-content:center;z-index:100}
.overlay.open{display:flex}
.modal{background:var(--panel);border:1px solid var(--line-2);border-radius:16px;
  padding:26px;width:min(560px,92vw);max-height:88vh;overflow-y:auto}
.modal h3{font-size:16px;margin-bottom:6px}
.modal p.sub{color:var(--ink-2);font-size:12.5px;margin-bottom:18px}
.steps{display:flex;flex-direction:column;gap:12px}
.step{display:flex;gap:14px;align-items:center;border:1px solid var(--line);
  border-radius:10px;padding:14px;background:var(--inset)}
.step .num{width:26px;height:26px;border-radius:50%;border:1px solid var(--line-2);
  display:flex;align-items:center;justify-content:center;font-size:12px;
  font-weight:700;color:var(--ink-2);flex:none}
.step.done .num{background:var(--ok);color:#0e2b1d;border-color:var(--ok)}
.step .grow{flex:1}
.step .title{font-weight:600;font-size:13px}
.step .hint{color:var(--muted);font-size:11.5px}
.count{font-size:22px;font-weight:800;font-variant-numeric:tabular-nums;
  color:var(--accent);width:64px;text-align:center}
.verdict{margin-top:16px;padding:14px;border-radius:10px;font-size:13px;display:none}
.verdict.good{display:block;background:rgba(63,214,143,.08);
  border:1px solid rgba(63,214,143,.4)}
.verdict.weak{display:block;background:rgba(255,194,75,.08);
  border:1px solid rgba(255,194,75,.4)}
.modal .actions{display:flex;gap:10px;margin-top:20px;justify-content:flex-end}

/* setup drawer */
.drawer{position:fixed;inset:0 0 0 auto;width:min(640px,100vw);z-index:90;
  background:var(--panel);border-left:1px solid var(--line-2);
  transform:translateX(102%);transition:transform .25s ease;overflow-y:auto;
  padding:24px 26px}
.drawer.open{transform:none}
.drawer h3{font-size:16px;margin-bottom:2px}
.drawer .sub{color:var(--ink-2);font-size:12px;margin-bottom:20px}
fieldset{border:1px solid var(--line);border-radius:12px;padding:16px;
  margin-bottom:16px;background:var(--inset)}
legend{font-size:10px;font-weight:700;letter-spacing:.14em;color:var(--muted);
  padding:0 8px;text-transform:uppercase}
.frow{display:flex;gap:10px;margin-bottom:10px;flex-wrap:wrap}
.field{flex:1;min-width:140px}
.field label{display:block;font-size:11px;color:var(--ink-2);margin-bottom:4px}
.field input,.field select,.field textarea{width:100%;background:#0a0e14;
  border:1px solid var(--line-2);color:var(--ink);border-radius:8px;
  padding:8px 10px;font-size:13px;font-family:inherit}
.field input:focus,.field select:focus,.field textarea:focus{outline:none;
  border-color:var(--accent-dim)}
.seg{display:flex;border:1px solid var(--line-2);border-radius:9px;overflow:hidden;
  width:fit-content;margin-bottom:16px}
.seg button{background:transparent;border:none;color:var(--ink-2);padding:8px 18px;
  font-size:12px;font-weight:700;cursor:pointer;letter-spacing:.06em}
.seg button.sel{background:var(--accent-dim);color:#eaf6ff}
.testline{font-size:12px;color:var(--ink-2);margin-top:6px;min-height:16px}
.toast{position:fixed;bottom:22px;left:50%;transform:translateX(-50%) translateY(80px);
  background:var(--panel-2);border:1px solid var(--line-2);color:var(--ink);
  border-radius:10px;padding:11px 18px;font-size:13px;z-index:200;
  transition:transform .25s ease;box-shadow:0 8px 30px rgba(0,0,0,.5)}
.toast.show{transform:translateX(-50%) translateY(0)}
.toast.err{border-color:rgba(255,93,93,.5)}
.setup-hero{grid-column:1/-1;text-align:center;padding:60px 20px}
.setup-hero h1{font-size:22px;margin-bottom:8px}
.setup-hero p{color:var(--ink-2);margin-bottom:22px}
kbd{background:var(--inset);border:1px solid var(--line-2);border-bottom-width:2px;
  border-radius:5px;padding:1px 6px;font-size:11px;font-family:inherit}
</style>
</head>
<body>

<header>
  <div class="brand"><span class="logo">🎬</span>
    <span class="name">AUTO<em>DIRECTOR</em></span>
    <span class="chip" id="modeChip">…</span>
  </div>
  <div class="pills">
    <span class="pill"><span class="dot" id="dotAudio"></span>AUDIO</span>
    <span class="pill"><span class="dot" id="dotObs"></span>OBS</span>
    <div class="switch" id="dirSwitch" title="Toggle directing (D)">
      <span class="label">DIRECTING</span>
      <span class="track"><span class="knob"></span></span>
    </div>
    <button class="iconbtn" id="btnSetup">⚙︎ Setup</button>
  </div>
</header>

<main id="main">
  <div class="col" id="colMain"></div>
  <div class="col">
    <div class="card" style="flex:1">
      <h2>Director&rsquo;s log <span class="spacer"></span>
        <span class="chip mono" id="clock">0:00</span></h2>
      <div class="log" id="log"><div class="empty">No cuts yet — the
        director is watching.</div></div>
    </div>
    <div class="card" id="aiCard" style="display:none">
      <h2><span class="badge-ai">AI</span> Engineer adjustments</h2>
      <div id="aiLog"><div class="empty">No adjustments yet.</div></div>
    </div>
  </div>
</main>

<!-- calibration modal -->
<div class="overlay" id="calOverlay">
  <div class="modal">
    <h3>Calibrate to your mix</h3>
    <p class="sub">20 seconds of your actual material teaches the director
      what vocals sound like <i>in your mix</i>. Have the band ready.</p>
    <div class="steps">
      <div class="step" id="calStep1">
        <span class="num">1</span>
        <div class="grow"><div class="title">Instrumental only</div>
          <div class="hint">Band plays, nobody sings.</div></div>
        <span class="count mono" id="calCount1">10s</span>
        <button class="btn" id="calBtn1">Record</button>
      </div>
      <div class="step" id="calStep2">
        <span class="num">2</span>
        <div class="grow"><div class="title">With vocals</div>
          <div class="hint">Main singer sings over the band.</div></div>
        <span class="count mono" id="calCount2">10s</span>
        <button class="btn" id="calBtn2">Record</button>
      </div>
    </div>
    <div class="verdict" id="calVerdict"></div>
    <div class="actions">
      <button class="btn ghost" id="calCancel">Cancel</button>
      <button class="btn" id="calFinish">Finish calibration</button>
    </div>
  </div>
</div>

<!-- setup drawer -->
<div class="drawer" id="drawer">
  <h3>Setup</h3>
  <p class="sub">Changes apply immediately when saved.</p>
  <div class="seg" id="modeSeg">
    <button data-mode="live">LIVE SHOW</button>
    <button data-mode="podcast">PODCAST</button>
  </div>

  <fieldset><legend>OBS connection</legend>
    <div class="frow">
      <div class="field" style="flex:2"><label>Host</label>
        <input id="cfgHost" placeholder="127.0.0.1"></div>
      <div class="field"><label>Port</label>
        <input id="cfgPort" placeholder="4455"></div>
    </div>
    <div class="frow">
      <div class="field"><label>WebSocket password
        <span style="color:var(--muted)">(OBS → Tools → WebSocket Server
        Settings)</span></label>
        <input id="cfgPass" type="password"></div>
    </div>
    <button class="btn ghost" id="btnTest">Test connection</button>
    <div class="testline" id="testLine"></div>
  </fieldset>

  <fieldset id="fsLive"><legend>Live show</legend>
    <div class="frow">
      <div class="field"><label>Audio input (the mixed feed)</label>
        <select id="cfgLiveDevice"></select></div>
    </div>
    <div class="frow">
      <div class="field"><label>Singer scene</label>
        <select id="cfgSinger"></select></div>
    </div>
    <div class="field"><label>Instrumental scenes — one per line, wide
      first</label>
      <textarea id="cfgInstrumentals" rows="4"></textarea></div>
  </fieldset>

  <fieldset id="fsPodcast"><legend>Podcast</legend>
    <div id="spkForms"></div>
    <div class="frow">
      <div class="field"><label>Wide / two-shot scene (optional)</label>
        <select id="cfgWide"></select></div>
    </div>
    <div class="frow">
      <div class="field"><label>AI engineer review</label>
        <select id="cfgAI">
          <option value="off">Off</option>
          <option value="on">On (uses ANTHROPIC_API_KEY)</option>
        </select></div>
    </div>
  </fieldset>

  <div style="display:flex;gap:10px;justify-content:flex-end;margin-top:6px">
    <button class="btn ghost" id="btnCloseSetup">Close</button>
    <button class="btn" id="btnSave">Save &amp; apply</button>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
"use strict";
const $ = id => document.getElementById(id);
const api = {
  get: p => fetch(p).then(r => r.json()),
  post: (p, b) => fetch(p, {method:"POST", headers:{"Content-Type":"application/json"},
                            body: JSON.stringify(b||{})}).then(r => r.json()),
};
let S = null;          // latest state
let cfg = null;        // latest config
let lastCutKey = "";
let toastTimer = null;

function toast(msg, err){
  const t = $("toast");
  t.textContent = msg; t.className = "toast show" + (err ? " err" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.className = "toast", 3200);
}
function fmtT(s){
  s = Math.max(0, s|0);
  return `${(s/60)|0}:${String(s%60).padStart(2,"0")}`;
}

/* ---------- header ---------- */
function renderHeader(){
  $("modeChip").textContent = S.mode === "setup" ? "SETUP NEEDED"
      : S.mode === "live" ? "LIVE SHOW" : "PODCAST";
  $("dotAudio").className = "dot " + (S.audio_alive ? "ok" : "bad");
  const obsOk = S.obs_state === "connected";
  $("dotObs").className = "dot " + (obsOk ? "ok" :
      S.obs_state === "connecting" ? "warn" : "bad");
  $("dirSwitch").classList.toggle("on", !!S.active);
  $("clock").textContent = fmtT(S.clock);
}

/* ---------- main column ---------- */
function onAirCard(){
  const paused = !S.active;
  return `<div class="card">
    <h2>Program</h2>
    <span class="onair-badge ${paused ? "paused" : ""}">
      <span class="dot"></span>${paused ? "PAUSED — MANUAL CONTROL" : "ON AIR — AUTO"}</span>
    <div class="scene-name">${S.current_scene || "—"}</div>
    <div class="scene-sub">${S.cuts[0] ?
      `last cut: ${S.cuts[0].reason}` : "waiting for the first cut"}</div>
  </div>`;
}

function liveCards(){
  const L = S.live, cal = L.calibration;
  const conf = L.vocal_conf, vocal = L.state === "VOCAL";
  const calChip = cal.calibrated
    ? `calibrated · d&prime; <b class="${cal.d_prime < 1.5 ? "weak" : ""}">${cal.d_prime}</b>`
    : `<b class="weak">not calibrated</b> — using generic detector`;
  return onAirCard() + `
  <div class="card">
    <h2>Vocal detector <span class="spacer"></span>
      <span class="cal-chip">${calChip}</span></h2>
    <div class="gauge">
      <div class="fill" style="width:${(conf*100).toFixed(1)}%"></div>
      <div class="tick" style="left:40%"></div>
      <div class="tick" style="left:65%"></div>
    </div>
    <div class="gauge-legend"><span>INSTRUMENTAL</span>
      <span>exit ·40&emsp;enter ·65</span><span>VOCAL</span></div>
    <div class="state-row">
      <span class="state-tag ${vocal ? "vocal" : "inst"}">${L.state}</span>
      <span style="color:var(--muted);font-size:12px">confidence
        <span class="mono">${conf.toFixed(2)}</span></span>
      <span class="spacer" style="margin-left:auto"></span>
      <button class="btn ghost" id="btnCal">Calibrate…</button>
    </div>
  </div>
  <div class="card">
    <h2>Shot pool</h2>
    <div class="shotpool">
      <span class="shot ${S.current_scene === L.singer_scene ? "on" : ""}">
        <span class="k">SINGER</span>${L.singer_scene || "—"}</span>
      ${L.instrumental_scenes.map((s, i) =>
        `<span class="shot ${S.current_scene === s ? "on" : ""}">
           <span class="k">${i === 0 ? "WIDE" : "INSTRUMENTAL"}</span>${s}</span>`
      ).join("")}
    </div>
  </div>` + mixerCard();
}

const PARAM_LABEL = {expander_threshold:"Gate thresh", gain_db:"Gain",
                     comp_threshold:"Comp thresh", eq_low:"EQ low",
                     eq_high:"EQ high"};
function railRow(spk, p, v, bounds, frozen){
  const [lo, hi] = bounds;
  const pct = Math.max(0, Math.min(100, (v - lo) / (hi - lo) * 100));
  const label = PARAM_LABEL[p] || p;
  return `<div class="rail">
    <span class="pname">${label}</span>
    <span class="bar"><i style="width:${pct}%"></i></span>
    <span class="val mono">${v > 0 && p === "gain_db" ? "+" : ""}${v} dB</span>
    <button class="lock ${frozen ? "frozen" : ""}" title="${frozen ?
      "Frozen — AI/auto may not move this" : "Click to freeze"}"
      onclick="toggleFreeze('${spk}','${p}',${!frozen})">${frozen ? "🔒" : "🔓"}</button>
  </div>`;
}

function podcastCards(){
  const P = S.podcast;
  const cards = P.speakers.map(sp => {
    const vu = Math.max(0, Math.min(100, (sp.level_db + 60) / 60 * 100));
    const floorPct = Math.max(0, Math.min(100, (sp.floor_db + 60) / 60 * 100));
    const chain = sp.chain ? `<div class="chain">` +
      Object.entries(sp.chain.rails).map(([p, v]) =>
        railRow(sp.name, p, v, sp.chain.bounds[p],
                sp.chain.frozen.includes(p))).join("") + `</div>` : "";
    return `<div class="speaker ${sp.talking ? "talking" : ""}">
      <div class="top"><span class="name">${sp.name}</span>
        ${sp.talking ? '<span class="tag talk">TALKING</span>' : ""}
        ${sp.has_floor ? '<span class="tag floor">HAS FLOOR</span>' : ""}</div>
      <div class="vu"><div class="fill" style="width:${vu}%"></div>
        <div class="floorline" style="left:${floorPct}%"
             title="room noise floor"></div></div>
      <div class="vu-scale"><span>-60</span><span>-30</span><span>0 dB</span></div>
      ${chain}
    </div>`;
  }).join("");
  return onAirCard() + `
  <div class="card"><h2>Speakers &amp; voice chains
    <span class="spacer"></span>
    <span class="chip">shot: ${P.wide ? "WIDE" : P.shot.toUpperCase()}</span></h2>
    <div class="speakers">${cards}</div>
  </div>`;
}

function mixerCard(){
  const M = S.mixer;
  if (!M) return "";
  const strips = M.stems.map(st => {
    const vu = Math.max(0, Math.min(100, (st.level_db + 60) / 60 * 100));
    const roleCls = st.role.includes("vocal") ? "voc" : "";
    return `<div class="strip ${st.active ? "active" : ""}">
      <div class="nm">${st.name}
        ${st.role ? `<span class="role ${roleCls}">${st.role
          .replace("_", " ").toUpperCase()}</span>` : ""}
        ${st.dead ? '<span class="tag dead">DEAD</span>' : ""}</div>
      <div class="vu"><div class="fill" style="width:${vu}%"></div></div>
      <div class="fader">
        <span class="fval mono">${st.fader_db > 0 ? "+" : ""}${st.fader_db} dB</span>
        ${Math.abs(st.target_db - st.fader_db) > 0.05 ?
          `<span style="color:var(--muted)">→ ${st.target_db > 0 ? "+" : ""}${st.target_db}</span>` : ""}
        <span style="margin-left:auto"></span>
        <button class="lock ${st.frozen ? "frozen" : ""}"
          onclick="mixerFreezeStem(${st.channel}, ${!st.frozen})">
          ${st.frozen ? "🔒" : "🔓"}</button>
      </div>
    </div>`;
  }).join("");
  const mask = M.vocal_masking_db;
  const advisory = M.control_mode === "advisory";
  return `<div class="card">
    <h2>Mix engineer <span class="chip">${advisory ?
        "ADVISORY — you ride the faders" : "AUTO FADERS"}</span>
      ${M.analysis_mode === "stereo" ?
        '<span class="chip">STEREO MIX ANALYSIS</span>' : ""}
      <span class="spacer"></span>
      ${advisory ? "" : `<span class="pill"><span class="dot ${M.midi_available ?
        (M.daw_heard ? "ok" : "warn") : "bad"}"></span>MIDI</span>`}</h2>
    <div class="mixbar">
      <button class="btn ${M.frozen_all ? "" : "danger"}"
        onclick="mixerAction('${M.frozen_all ? "unfreeze_all" : "freeze_all"}')">
        ${M.frozen_all ? "▶ Resume mix" : "⏸ FREEZE MIX"}</button>
      <button class="btn ghost" onclick="mixerSnapshot()">Soundcheck
        snapshot${M.baselined ? " ✓" : ""}</button>
      ${M.ai_enabled ? `<button class="btn ghost"
        onclick="mixerAction('review_now')">AI review now</button>` : ""}
      <span class="masking">${mask === null ? "" :
        `vocal masking: <b class="${mask > 0 ? "badval" : ""}">${mask > 0 ? "+" : ""}${mask} dB</b>`}</span>
      ${!M.daw_heard && M.midi_available ?
        `<span class="masking">wiggle a fader in Studio One to confirm
         the MCU wiring</span>` : ""}
    </div>
    <div class="strips">${strips}</div>
  </div>`;
}

function setupHero(){
  return `<div class="card setup-hero">
    <h1>Welcome to AutoDirector</h1>
    <p>${S.error ? "⚠︎ " + S.error : "Let’s wire up OBS and your audio."}</p>
    <button class="btn" onclick="openSetup()">Open setup</button>
  </div>`;
}

function renderMain(){
  const col = $("colMain");
  const html = S.mode === "live" ? liveCards()
             : S.mode === "podcast" ? podcastCards() : setupHero();
  if (col.dataset.html !== html){ col.innerHTML = html; col.dataset.html = html;
    const b = $("btnCal"); if (b) b.onclick = openCal; }
  $("aiCard").style.display =
    ((S.mode === "podcast" && S.podcast.ai_enabled) ||
     (S.mixer && S.mixer.ai_enabled)) ? "" : "none";
}

/* ---------- log ---------- */
function renderLog(){
  const key = S.cuts.length ? S.cuts[0].t + S.cuts[0].scene : "";
  if (key === lastCutKey) return;
  lastCutKey = key;
  $("log").innerHTML = S.cuts.length ? S.cuts.map(c =>
    `<div class="cut ${c.priority ? "prio" : ""}">
       <span class="t mono">${fmtT(c.t)}</span>
       <span class="scene">${c.scene}</span>
       ${c.priority ? '<span class="ptag">PRIORITY</span>' : ""}
       <span class="why">${c.reason}${c.applied === false ?
         " · ⚠︎ OBS down" : ""}</span>
     </div>`).join("")
    : '<div class="empty">No cuts yet — the director is watching.</div>';
  const aiEntries = S.mode === "podcast" ? (S.podcast.ai_log || [])
      : S.mixer ? (S.mixer.ai_log || []) : [];
  $("aiLog").innerHTML = aiEntries.length ? aiEntries.map(e => {
    const db = e.advisory ? +e.suggested : +e.applied;
    return `<div class="ai-entry"><div class="head mono">
       ${e.speaker || e.stem} ·
       ${PARAM_LABEL[e.param] || e.param || "fader"}
       ${e.advisory ? "suggest " : ""}${db >= 0 ? "+" : ""}${db.toFixed(1)} dB</div>
     <div class="why">${e.reason}</div></div>`;
  }).join("") : '<div class="empty">No adjustments yet.</div>';
}
window.mixerAction = a => api.post("/api/mixer", {action: a});
window.mixerFreezeStem = (ch, frozen) =>
  api.post("/api/mixer", {action: "freeze_stem", channel: ch, frozen});
window.mixerSnapshot = async () => {
  const r = await api.post("/api/mixer", {action: "snapshot"});
  toast(`Soundcheck snapshot: ${r.faders_heard ?? 0} faders heard, ` +
        `${r.stems_referenced ?? 0} stems referenced`);
};

/* ---------- calibration ---------- */
function openCal(){ $("calOverlay").classList.add("open"); $("calVerdict").className = "verdict"; }
function closeCal(){ $("calOverlay").classList.remove("open"); }
$("calCancel").onclick = async () => { await api.post("/api/calibration", {action:"cancel"}); closeCal(); };
$("calBtn1").onclick = () => api.post("/api/calibration", {action:"start_instrumental"});
$("calBtn2").onclick = () => api.post("/api/calibration", {action:"start_vocal"});
$("calFinish").onclick = async () => {
  const r = await api.post("/api/calibration", {action:"finish"});
  const v = $("calVerdict");
  if (r.ok){
    v.className = "verdict " + (r.weak ? "weak" : "good");
    v.innerHTML = r.weak
      ? `⚠︎ Calibrated, but separation is weak (d&prime; = ${r.d_prime}).
         The director will switch more deliberately. Consider re-running
         with more representative material.`
      : `✓ Calibrated — d&prime; = ${r.d_prime}. The detector knows your mix.`;
    toast("Calibration saved");
  } else { v.className = "verdict weak"; v.textContent = "⚠︎ " + r.error; }
};
function renderCal(){
  if (S.mode !== "live") return;
  const c = S.live.calibration;
  const rec = c.phase;
  $("calCount1").textContent = rec === "instrumental" ? c.remaining_s + "s"
      : c.instrumental_samples > 0 ? "✓" : "10s";
  $("calCount2").textContent = rec === "vocal" ? c.remaining_s + "s"
      : c.vocal_samples > 0 ? "✓" : "10s";
  $("calStep1").classList.toggle("done", !rec && c.instrumental_samples > 0);
  $("calStep2").classList.toggle("done", !rec && c.vocal_samples > 0);
  $("calBtn1").disabled = $("calBtn2").disabled = !!rec;
}

/* ---------- setup drawer ---------- */
let setupMode = "live";
function openSetup(){ loadSetup(); $("drawer").classList.add("open"); }
$("btnSetup").onclick = openSetup;
$("btnCloseSetup").onclick = () => $("drawer").classList.remove("open");
$("modeSeg").onclick = e => {
  const m = e.target.dataset.mode; if (!m) return;
  setupMode = m; paintModeSeg();
};
function paintModeSeg(){
  document.querySelectorAll("#modeSeg button").forEach(b =>
    b.classList.toggle("sel", b.dataset.mode === setupMode));
  $("fsLive").style.display = setupMode === "live" ? "" : "none";
  $("fsPodcast").style.display = setupMode === "podcast" ? "" : "none";
}
function opt(v, sel){ return `<option ${v === sel ? "selected" : ""}>${v}</option>`; }

async function loadSetup(){
  cfg = await api.get("/api/config");
  setupMode = cfg.mode || "live";
  paintModeSeg();
  $("cfgHost").value = cfg.obs?.host ?? "127.0.0.1";
  $("cfgPort").value = cfg.obs?.port ?? 4455;
  $("cfgPass").value = cfg.obs?.password ?? "";
  const [dev, sc] = await Promise.all([api.get("/api/devices"),
                                       api.get("/api/scenes")]);
  const devices = dev.devices.map(d => d.name);
  const scenes = sc.scenes;
  const devOpts = sel => `<option value="">(default input)</option>` +
    devices.map(d => opt(d, sel)).join("");
  const sceneOpts = (sel, none) => (none ? `<option value="">(none)</option>` : "") +
    (scenes.length ? scenes.map(s => opt(s, sel)).join("")
                   : (sel ? opt(sel, sel) : ""));
  $("cfgLiveDevice").innerHTML = devOpts(cfg.live?.device || "");
  $("cfgSinger").innerHTML = sceneOpts(cfg.live?.singer_scene || "");
  $("cfgInstrumentals").value = (cfg.live?.instrumental_scenes || []).join("\n");
  $("cfgWide").innerHTML = sceneOpts(cfg.podcast?.wide_scene || "", true);
  $("cfgAI").value = cfg.podcast?.ai_review?.enabled ? "on" : "off";
  const spk = cfg.podcast?.speakers?.length ? cfg.podcast.speakers :
    [{name:"Host"}, {name:"Guest"}];
  $("spkForms").innerHTML = spk.slice(0, 2).map((s, i) => `
    <fieldset style="margin-bottom:10px"><legend>Speaker ${i+1}</legend>
      <div class="frow">
        <div class="field"><label>Name</label>
          <input class="spkName" value="${s.name || ""}"></div>
        <div class="field"><label>Mic device</label>
          <select class="spkDev">${devOpts(s.device || "")}</select></div>
      </div>
      <div class="frow">
        <div class="field"><label>OBS audio source (voice chain)</label>
          <input class="spkSrc" value="${s.obs_source || ""}"
                 placeholder="Mic - ${s.name || "…"}"></div>
      </div>
      <div class="frow">
        <div class="field"><label>Medium scene</label>
          <select class="spkMed">${sceneOpts(s.medium_scene || "")}</select></div>
        <div class="field"><label>Close-up scene</label>
          <select class="spkClose">${sceneOpts(s.closeup_scene || "", true)}</select></div>
      </div>
    </fieldset>`).join("");
}

$("btnTest").onclick = async () => {
  $("testLine").textContent = "testing…";
  await saveObsOnly();
  await new Promise(r => setTimeout(r, 1200));
  const sc = await api.get("/api/scenes");
  $("testLine").textContent = sc.obs_state === "connected"
    ? `✓ connected — ${sc.scenes.length} scenes found`
    : `✗ ${sc.obs_state} — check OBS WebSocket settings & password`;
};

function collectCfg(){
  const c = JSON.parse(JSON.stringify(cfg || {}));
  c.mode = setupMode;
  c.obs = {host: $("cfgHost").value || "127.0.0.1",
           port: parseInt($("cfgPort").value) || 4455,
           password: $("cfgPass").value};
  c.live = Object.assign(c.live || {}, {
    device: $("cfgLiveDevice").value || null,
    singer_scene: $("cfgSinger").value,
    instrumental_scenes: $("cfgInstrumentals").value.split("\n")
      .map(s => s.trim()).filter(Boolean),
  });
  c.live.calibration_file = c.live.calibration_file || "~/.autodirector/live_cal.json";
  const speakers = [...document.querySelectorAll("#spkForms fieldset")].map(f => ({
    name: f.querySelector(".spkName").value || "Speaker",
    device: f.querySelector(".spkDev").value || null,
    obs_source: f.querySelector(".spkSrc").value,
    medium_scene: f.querySelector(".spkMed").value,
    closeup_scene: f.querySelector(".spkClose").value,
  }));
  c.podcast = Object.assign(c.podcast || {}, {
    speakers, wide_scene: $("cfgWide").value,
  });
  c.podcast.voice_chain = c.podcast.voice_chain || {enabled: true};
  c.podcast.ai_review = Object.assign(c.podcast.ai_review || {},
    {enabled: $("cfgAI").value === "on"});
  c.ui = c.ui || {port: 8787, open_browser: true};
  return c;
}
async function saveObsOnly(){
  const c = JSON.parse(JSON.stringify(cfg || {}));
  c.obs = {host: $("cfgHost").value || "127.0.0.1",
           port: parseInt($("cfgPort").value) || 4455,
           password: $("cfgPass").value};
  await api.post("/api/config", c);
  cfg = c;
}
$("btnSave").onclick = async () => {
  const r = await api.post("/api/config", collectCfg());
  if (r.engine_ok){ toast("Saved — directing with new settings");
    $("drawer").classList.remove("open"); }
  else toast("Saved, but: " + (r.error || "engine not running"), true);
};

/* ---------- global controls ---------- */
window.toggleFreeze = (spk, p, frozen) =>
  api.post("/api/freeze", {speaker: spk, param: p, frozen});
$("dirSwitch").onclick = () =>
  api.post("/api/active", {active: !(S && S.active)});
document.addEventListener("keydown", e => {
  if (e.key === "Escape"){
    $("drawer").classList.remove("open"); closeCal(); return;
  }
  if (e.key.toLowerCase() === "d" && !e.metaKey && !e.ctrlKey
      && document.activeElement.tagName !== "INPUT"
      && document.activeElement.tagName !== "TEXTAREA")
    $("dirSwitch").onclick();
});

/* ---------- poll loop ---------- */
async function tick(){
  try{
    S = await api.get("/api/state");
    renderHeader(); renderMain(); renderLog(); renderCal();
  }catch(e){ $("dotObs").className = "dot bad"; }
}
setInterval(tick, 250);
tick();
</script>
</body>
</html>
"""
