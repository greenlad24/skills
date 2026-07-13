"""Guided onboarding wizard — injected into the Control Room page.

A full-screen, step-by-step setup guide that tells the operator exactly
what to click in OBS / Studio One / Windows, verifies each step live
against the running engine (OBS connected? scenes found? MIDI heard?),
and offers a curated YouTube walkthrough video for every part. Videos
are embedded on click (privacy-friendly: nothing loads until tapped)
with an "open on YouTube" fallback for offline rigs.

Kept out of html.py so the console page and the wizard can evolve
independently; html.py splices ONBOARDING_SNIPPET in before </body>.
"""

ONBOARDING_SNIPPET = r"""
<style>
/* ---------- onboarding wizard ---------- */
.wiz{position:fixed;inset:0;z-index:80;display:none;background:rgba(6,8,11,.94);
  backdrop-filter:blur(6px)}
.wiz.open{display:flex}
.wiz .frame{margin:auto;width:min(1060px,96vw);height:min(760px,94vh);
  display:flex;background:var(--panel);border:1px solid var(--line);
  border-radius:14px;overflow:hidden;box-shadow:0 30px 80px rgba(0,0,0,.6)}
.wiz .rail{width:250px;flex:none;background:var(--inset);
  border-right:1px solid var(--line);padding:22px 0;display:flex;
  flex-direction:column;overflow-y:auto}
.wiz .rail .hd{padding:0 20px 16px;font-size:11px;letter-spacing:.14em;
  color:var(--muted)}
.wiz .rstep{display:flex;align-items:center;gap:10px;padding:9px 20px;
  cursor:pointer;color:var(--ink-2);font-size:13px;border-left:2px solid transparent}
.wiz .rstep:hover{color:var(--ink)}
.wiz .rstep.cur{color:var(--ink);border-left-color:var(--accent);
  background:rgba(79,184,255,.06)}
.wiz .rstep .n{width:22px;height:22px;flex:none;border-radius:50%;
  border:1px solid var(--line-2);display:flex;align-items:center;
  justify-content:center;font-size:11px;font-family:var(--mono, monospace)}
.wiz .rstep.done .n{background:var(--ok);border-color:var(--ok);color:#08130d}
.wiz .rstep.cur .n{border-color:var(--accent);color:var(--accent)}
.wiz .rstep .opt{margin-left:auto;font-size:9px;letter-spacing:.1em;
  color:var(--muted)}
.wiz .body{flex:1;display:flex;flex-direction:column;min-width:0}
.wiz .content{flex:1;overflow-y:auto;padding:30px 34px}
.wiz h2.title{font-size:22px;margin-bottom:6px}
.wiz .sub{color:var(--ink-2);font-size:13px;line-height:1.55;margin-bottom:20px;
  max-width:640px}
.wiz .todo{display:flex;gap:14px;background:var(--panel-2);
  border:1px solid var(--line);border-radius:10px;padding:14px 16px;
  margin-bottom:10px}
.wiz .todo .tn{width:24px;height:24px;flex:none;border-radius:50%;
  background:var(--inset);border:1px solid var(--line-2);display:flex;
  align-items:center;justify-content:center;font-size:12px;color:var(--accent)}
.wiz .todo .tt{font-size:13px;line-height:1.55;color:var(--ink)}
.wiz .todo .tt .hint{color:var(--ink-2);font-size:12px;margin-top:2px}
.wiz kbd.path{background:var(--inset);border:1px solid var(--line-2);
  border-radius:5px;padding:1px 7px;font-size:12px;color:var(--accent);
  font-family:inherit;white-space:nowrap}
.wiz .check{display:inline-flex;align-items:center;gap:8px;margin:12px 0;
  padding:8px 14px;border-radius:999px;border:1px solid var(--line-2);
  background:var(--inset);font-size:12px;color:var(--ink-2)}
.wiz .check .dot{width:9px;height:9px}
.wiz .vids{display:flex;gap:12px;flex-wrap:wrap;margin-top:18px}
.wiz .vcard{width:252px;background:var(--panel-2);border:1px solid var(--line);
  border-radius:10px;overflow:hidden}
.wiz .vcard .thumb{position:relative;aspect-ratio:16/9;background:#000;
  cursor:pointer;display:block}
.wiz .vcard .thumb img{width:100%;height:100%;object-fit:cover;opacity:.85}
.wiz .vcard .thumb .play{position:absolute;inset:0;display:flex;
  align-items:center;justify-content:center;font-size:34px;
  text-shadow:0 2px 12px rgba(0,0,0,.8)}
.wiz .vcard iframe{width:100%;aspect-ratio:16/9;border:0;display:block}
.wiz .vcard .cap{padding:9px 12px;font-size:12px;line-height:1.4;
  color:var(--ink)}
.wiz .vcard .cap .yt{display:block;margin-top:4px;font-size:11px;
  color:var(--accent);text-decoration:none}
.wiz .vhd{margin-top:22px;font-size:11px;letter-spacing:.14em;
  color:var(--muted)}
.wiz .foot{flex:none;display:flex;align-items:center;gap:10px;
  padding:16px 34px;border-top:1px solid var(--line);background:var(--panel-2)}
.wiz .foot .spacer{flex:1}
.wiz .modecards{display:flex;gap:14px;margin:8px 0 4px}
.wiz .mcard{flex:1;padding:20px;background:var(--panel-2);cursor:pointer;
  border:1px solid var(--line);border-radius:12px}
.wiz .mcard:hover{border-color:var(--line-2)}
.wiz .mcard.sel{border-color:var(--accent);
  box-shadow:0 0 0 1px var(--accent), 0 0 24px rgba(79,184,255,.15)}
.wiz .mcard .ic{font-size:26px}
.wiz .mcard h4{margin:8px 0 4px;font-size:15px}
.wiz .mcard p{font-size:12px;color:var(--ink-2);line-height:1.5}
.wiz .wfield{margin-bottom:12px}
.wiz .wfield label{display:block;font-size:11px;letter-spacing:.08em;
  color:var(--ink-2);margin-bottom:5px}
.wiz .wfield input,.wiz .wfield select,.wiz .wfield textarea{width:100%;
  max-width:420px;background:var(--inset);border:1px solid var(--line-2);
  border-radius:8px;color:var(--ink);padding:9px 12px;font-size:13px}
.wiz .frow2{display:flex;gap:12px;flex-wrap:wrap}
.wiz .frow2 .wfield{flex:1;min-width:170px}
.wiz .note{border-left:3px solid var(--warn);background:rgba(255,194,75,.06);
  padding:10px 14px;border-radius:0 8px 8px 0;font-size:12px;
  color:var(--ink-2);line-height:1.55;margin:14px 0;max-width:640px}
.wiz .osseg{display:inline-flex;border:1px solid var(--line-2);
  border-radius:8px;overflow:hidden;margin-bottom:14px}
.wiz .osseg button{background:none;border:0;color:var(--ink-2);
  padding:7px 16px;font-size:12px;cursor:pointer}
.wiz .osseg button.sel{background:var(--accent-dim);color:var(--ink)}
</style>

<div class="wiz" id="wiz">
  <div class="frame">
    <div class="rail">
      <div class="hd">SETUP GUIDE</div>
      <div id="wizRail"></div>
    </div>
    <div class="body">
      <div class="content" id="wizContent"></div>
      <div class="foot">
        <button class="btn ghost" id="wizClose">Close guide</button>
        <span class="spacer"></span>
        <button class="btn ghost" id="wizBack">← Back</button>
        <button class="btn" id="wizNext">Next →</button>
      </div>
    </div>
  </div>
</div>

<script>
"use strict";
/* ---------- onboarding wizard ---------- */

/* Curated walkthrough videos. Nothing loads until the user clicks the
   thumbnail (then it swaps to an embedded player); every card also
   links out to YouTube for phones / offline rigs. */
const WVID = {
  obsws:    {id: "pXuwOIYnDfo", t: "Set up the WebSocket server in OBS — 2026 easy guide"},
  obsws2:   {id: "3OQIR0x8URw", t: "OBS WebSocket server — the easiest way (2026)"},
  scenes:   {id: "J0uYidmfRM4", t: "Add scenes & sources in OBS — step-by-step beginner guide"},
  scenes2:  {id: "N9B-g4ixhMM", t: "OBS Studio: beginner's guide to scenes & sources"},
  audiocap: {id: "T_5Qf0Dk2us", t: "Audio input & output capture in OBS Studio"},
  micguide: {id: "gNUwAwrNiV0", t: "OBS ultimate microphone guide (mics, filters, settings)"},
  blackhole:{id: "YVRijTXsyA4", t: "macOS audio routing with BlackHole"},
  mcu:      {id: "oNVwBmQdRcw", t: "Setting up a control surface in Studio One"},
  mcu2:     {id: "1u4NtT0vsOU", t: "Using a control surface in Studio One — Pro Mix Academy"},
  clink:    {id: "Vq0GMDvagi4", t: "Assign MIDI controls with Control Link — PreSonus official"},
  clink2:   {id: "0iLyRAikTSo", t: "MIDI controllers, Control Link & Focus mode — PreSonus"},
  loopmidi: {id: "37j33Oy6tg0", t: "loopMIDI installation on Windows"},
  golive:   {id: "HMjtJBYAERE", t: "Go live on YouTube with OBS — best settings (2026)"},
};
function vcard(k){
  const v = WVID[k];
  return `<div class="vcard" data-vid="${v.id}">
    <a class="thumb" title="Play video">
      <img src="https://img.youtube.com/vi/${v.id}/hqdefault.jpg" alt=""
           onerror="this.style.display='none'">
      <span class="play">▶</span></a>
    <div class="cap">${v.t}
      <a class="yt" href="https://www.youtube.com/watch?v=${v.id}"
         target="_blank" rel="noopener">Open on YouTube ↗</a></div>
  </div>`;
}
function vids(...keys){
  return `<div class="vhd">▶ WATCH HOW — YOUTUBE WALKTHROUGHS</div>
    <div class="vids">${keys.map(vcard).join("")}</div>`;
}
function todo(n, html, hint){
  return `<div class="todo"><span class="tn">${n}</span>
    <div class="tt">${html}${hint ? `<div class="hint">${hint}</div>` : ""}</div></div>`;
}
function chk(state, label){  /* state: ok | warn | bad */
  return `<div class="check"><span class="dot ${state}"></span>
    <b>LIVE CHECK</b>&nbsp; ${label}</div>`;
}

let wcfg = null;          // wizard's working copy of the config
let wizStep = 0;
let wizMode = "live";
let wizOS = navigator.platform.toLowerCase().includes("win") ? "win" : "mac";
const wizDone = new Set(JSON.parse(localStorage.getItem("ad_wiz_done") || "[]"));

function wizSteps(){
  const live = wizMode === "live";
  return [
    {id: "welcome",  name: "Welcome"},
    {id: "obs",      name: "Connect OBS"},
    {id: "scenes",   name: "Build your shots"},
    {id: "audio",    name: "Audio feed"},
    ...(live ? [
      {id: "mixer",  name: "AI mix engineer", opt: true},
      {id: "knobs",  name: "VST tweaks", opt: true},
      {id: "cal",    name: "Calibrate"},
    ] : [
      {id: "voice",  name: "Voice check"},
    ]),
    {id: "golive",   name: "Go live"},
  ];
}

/* ---------- step renderers ---------- */
const WREND = {

welcome(){
  return `<h2 class="title">Welcome — let's wire everything up</h2>
  <p class="sub">In about ten minutes AutoDirector will be cutting your
    cameras and riding your mix like a broadcast crew. This guide walks
    you through every connection, checks each one <i>live</i> as you go,
    and has a video for every part. First: what are you making?</p>
  <div class="modecards">
    <div class="mcard ${wizMode === "live" ? "sel" : ""}" data-m="live">
      <div class="ic">🎸</div><h4>Live show</h4>
      <p>A band or artist performing. AutoDirector detects singing in
        your mix, cuts to the singer, rotates instrument shots with
        professional pacing — and can rebalance your Studio One mix
        while the show runs.</p></div>
    <div class="mcard ${wizMode === "podcast" ? "sel" : ""}" data-m="podcast">
      <div class="ic">🎙️</div><h4>Podcast</h4>
      <p>Two people talking. AutoDirector follows the active speaker,
        chooses medium vs close-up shots, and keeps each voice sounding
        polished automatically.</p></div>
  </div>
  <div class="note">You'll need: <b>OBS Studio</b> installed with its
    WebSocket server enabled (step 2 shows you), your cameras added to
    OBS scenes, and an audio input this computer can hear. Everything is
    reversible — you can re-run this guide any time from the
    <b>🧭 Guide</b> button.</div>`;
},

obs(){
  const ok = S && S.obs_state === "connected";
  return `<h2 class="title">Connect to OBS</h2>
  <p class="sub">AutoDirector talks to OBS through its built-in WebSocket
    server — that's how it switches your scenes. Enable it once and
    paste the password below.</p>
  ${todo(1, `In OBS open <kbd class="path">Tools → WebSocket Server
    Settings</kbd>`, "It ships with OBS 28+ — nothing to install.")}
  ${todo(2, `Tick <kbd class="path">Enable WebSocket server</kbd>, then
    click <kbd class="path">Show Connect Info</kbd> and copy the
    password`, "Leave the port at 4455.")}
  ${todo(3, `Paste it here and hit <b>Test connection</b>`)}
  <div class="frow2">
    <div class="wfield" style="flex:2"><label>HOST</label>
      <input id="wHost" placeholder="127.0.0.1"></div>
    <div class="wfield"><label>PORT</label>
      <input id="wPort" placeholder="4455"></div>
    <div class="wfield" style="flex:2"><label>WEBSOCKET PASSWORD</label>
      <input id="wPass" type="password"></div>
  </div>
  <button class="btn" id="wObsTest">Test connection</button>
  ${chk(ok ? "ok" : "bad", ok
    ? `connected — OBS is listening`
    : `not connected yet — waiting for a successful test`)}
  ${vids("obsws", "obsws2")}`;
},

scenes(){
  const sc = (S && S.obs_state === "connected") ? wizScenes : [];
  const so = (sel, none) => (none ? `<option value="">(none)</option>` : "") +
    sc.map(s => `<option ${s === sel ? "selected" : ""}>${s}</option>`).join("") +
    (sel && !sc.includes(sel) ? `<option selected>${sel}</option>` : "");
  const L = wcfg?.live || {}, P = wcfg?.podcast || {};
  const spk = P.speakers?.length ? P.speakers
    : [{name: "Host"}, {name: "Guest"}];
  const body = wizMode === "live" ? `
    ${todo(1, `In OBS create one scene per shot: a <b>singer scene</b>
      (camera on your main singer) plus 2–4 <b>instrumental scenes</b> —
      a wide shot first, then guitar / drums / keys close-ups`,
      "Name them clearly: “Singer”, “Wide”, “Guitar”…")}
    ${todo(2, `Come back here and assign them:`)}
    <div class="frow2">
      <div class="wfield"><label>SINGER SCENE</label>
        <select id="wSinger">${so(L.singer_scene || "")}</select></div>
    </div>
    <div class="wfield"><label>INSTRUMENTAL SCENES — one per line, wide
      shot first</label>
      <textarea id="wInstr" rows="4">${(L.instrumental_scenes || []).join("\n")}</textarea></div>`
  : `
    ${todo(1, `In OBS create <b>five scenes</b>: a medium and a close-up
      per speaker, plus one wide two-shot`,
      "“Host Medium”, “Host Close”, “Guest Medium”, “Guest Close”, “Two Shot”.")}
    ${todo(2, `Assign them per speaker:`)}
    ${spk.slice(0, 2).map((s, i) => `
      <div class="frow2">
        <div class="wfield"><label>SPEAKER ${i + 1} NAME</label>
          <input class="wSpkName" value="${s.name || ""}"></div>
        <div class="wfield"><label>MEDIUM SCENE</label>
          <select class="wSpkMed">${so(s.medium_scene || "")}</select></div>
        <div class="wfield"><label>CLOSE-UP SCENE</label>
          <select class="wSpkClose">${so(s.closeup_scene || "", true)}</select></div>
      </div>`).join("")}
    <div class="wfield"><label>WIDE / TWO-SHOT SCENE</label>
      <select id="wWide">${so(P.wide_scene || "", true)}</select></div>`;
  return `<h2 class="title">Build your shots</h2>
  <p class="sub">Every camera angle lives in its own OBS scene —
    AutoDirector cuts between whole scenes, exactly like a director
    calling cameras.</p>
  ${body}
  ${chk(sc.length ? "ok" : "warn", sc.length
    ? `${sc.length} scenes found in OBS`
    : `no scenes visible — finish the OBS connection in step 2 first`)}
  ${vids("scenes", "scenes2")}`;
},

audio(){
  const alive = S && S.audio_alive;
  const dv = sel => `<option value="">(default input)</option>` +
    wizDevices.map(d =>
      `<option ${d === sel ? "selected" : ""}>${d}</option>`).join("");
  const L = wcfg?.live || {}, P = wcfg?.podcast || {};
  const spk = P.speakers?.length ? P.speakers
    : [{name: "Host"}, {name: "Guest"}];
  const body = wizMode === "live" ? `
    ${todo(1, `Route <b>one mixed feed</b> of the whole band to an input
      this computer can hear`, wizOS === "mac"
      ? `Interface with loopback (RME/MOTU/Focusrite): just pick its input below. No loopback? Install the free <b>BlackHole 2ch</b> driver and set your DAW's main out to it — the video below shows the whole thing.`
      : `Interface with loopback: pick its input below. Otherwise use a physical loop (main out → spare line-in) or VB-Cable.`)}
    ${todo(2, `Pick that device:`)}
    <div class="wfield"><label>AUDIO INPUT — THE MIXED FEED</label>
      <select id="wDevice">${dv(L.device || "")}</select></div>
    <div class="note">This same feed is what OBS should broadcast (add it
      there as an <i>Audio Input Capture</i> source). macOS input devices
      are multi-client — OBS and AutoDirector can share it.</div>`
  : `
    ${todo(1, `Each speaker needs their own mic on its own input device
      — that's how AutoDirector knows who's talking`)}
    ${todo(2, `In OBS, add each mic as an <i>Audio Input Capture</i>
      source and note the source names`,
      "AutoDirector polishes each voice through that source.")}
    ${spk.slice(0, 2).map((s, i) => `
      <div class="frow2">
        <div class="wfield"><label>${(s.name || "SPEAKER " + (i + 1)).toUpperCase()} — MIC DEVICE</label>
          <select class="wSpkDev">${dv(s.device || "")}</select></div>
        <div class="wfield"><label>OBS AUDIO SOURCE NAME</label>
          <input class="wSpkSrc" value="${s.obs_source || ""}"
                 placeholder="Mic - ${s.name || "…"}"></div>
      </div>`).join("")}`;
  return `<h2 class="title">Audio feed</h2>
  <p class="sub">${wizMode === "live"
    ? "The director listens to your actual mix — one stereo feed is all it needs to hear who's playing and who's singing."
    : "The director follows voices — each speaker gets their own mic and their own OBS source."}</p>
  ${body}
  ${chk(alive ? "ok" : "warn", alive
    ? "audio is flowing — AutoDirector can hear you"
    : "no audio yet — apply this step, then make some noise and watch the AUDIO pill turn green")}
  ${wizMode === "live" && wizOS === "mac" ? vids("audiocap", "blackhole")
    : wizMode === "live" ? vids("audiocap")
    : vids("micguide", "audiocap")}`;
},

mixer(){
  const M = S && S.mixer;
  const st = !M ? ["warn", "mixer not enabled yet — apply this step to turn it on"]
    : !M.midi_available ? ["bad", "MIDI ports unavailable — see the note below"]
    : M.daw_heard ? ["ok", "Studio One is talking — fader wiring confirmed"]
    : ["warn", "ports open — wiggle any fader in Studio One to confirm"];
  return `<h2 class="title">AI mix engineer <span class="chip">OPTIONAL</span></h2>
  <p class="sub">For live shows mixed in a DAW: AutoDirector listens to
    your mix and rides the faders — gently, within hard limits — like a
    trusted engineer at front of house. Works with Studio One, Cubase,
    Logic, REAPER (anything that speaks Mackie Control).</p>
  ${wizOS === "win" ? todo(1, `Windows only: create two virtual MIDI
    ports named <kbd class="path">AutoDirector MCU 1</kbd> and
    <kbd class="path">AutoDirector MCU 2</kbd> in the free
    <a href="https://www.tobias-erichsen.de/software/loopmidi.html"
       target="_blank" rel="noopener" style="color:var(--accent)">loopMIDI</a>`,
    "On a Mac these ports appear automatically — skip this.") : ""}
  ${todo(wizOS === "win" ? 2 : 1, `In Studio One open
    <kbd class="path">Preferences → External Devices → Add…</kbd> and add
    <b>two</b> devices: <kbd class="path">Mackie → Control</kbd> on
    “AutoDirector MCU 1”, and <kbd class="path">Mackie → Control XT</kbd>
    on “AutoDirector MCU 2”`,
    "Receive From and Send To both set to the matching port. That's 16 fader strips under AutoDirector's control.")}
  ${todo(wizOS === "win" ? 3 : 2, `Turn the mixer on and apply — then
    <b>wiggle any fader in Studio One</b> and watch the check below turn
    green`)}
  <div class="wfield"><label>MIX ENGINEER</label>
    <select id="wMixEn">
      <option value="off" ${wcfg?.live?.mixer?.enabled ? "" : "selected"}>Off</option>
      <option value="on" ${wcfg?.live?.mixer?.enabled ? "selected" : ""}>On — ride my mix</option>
    </select></div>
  ${chk(st[0], st[1])}
  <div class="note">Your channel names travel over the wire automatically
    (“Lead Vox”, “Kick”…) so the AI rebalances <i>by instrument</i>. It
    can never move a fader more than a few dB from your soundcheck, and
    you can freeze any strip — or the whole mix — from the console.</div>
  ${wizOS === "win" ? vids("mcu", "mcu2", "loopmidi") : vids("mcu", "mcu2")}`;
},

knobs(){
  const nk = (wcfg?.live?.mixer?.knobs || []).length;
  return `<h2 class="title">Slight VST tweaks <span class="chip">OPTIONAL</span></h2>
  <p class="sub">Your plugins stay inside Studio One. Map just the
    parameters you're happy to have nudged — say the vocal compressor's
    threshold — and the AI may adjust <i>only those</i>, very slightly,
    with a written reason every time.</p>
  ${todo(1, `In Studio One add one more external device:
    <kbd class="path">Preferences → External Devices → Add… → New Control
    Surface</kbd>, Receive From <kbd class="path">AutoDirector Params</kbd>`)}
  ${todo(2, `Open the plugin, right-click the knob you want tweakable →
    <kbd class="path">Assign to Control Link</kbd>, and map it to CC 1
    (next knob CC 2, and so on)`,
    "The official PreSonus video below shows Control Link in one minute.")}
  ${todo(3, `List what you mapped (name + CC), one per line, as
    <b>CC number : name</b>:`)}
  <div class="wfield"><label>MAPPED KNOBS</label>
    <textarea id="wKnobs" rows="3" placeholder="1: Vox Comp Threshold&#10;2: Vox Reverb Send">${
      (wcfg?.live?.mixer?.knobs || [])
        .map(k => `${k.cc}: ${k.name}`).join("\n")}</textarea></div>
  ${chk(nk ? "ok" : "warn", nk ? `${nk} knob${nk > 1 ? "s" : ""} mapped — they'll appear in the mixer console`
    : "no knobs mapped yet — this feature stays off until you add one")}
  <div class="note">Unmapped parameters can never be touched. Moves are
    capped at ±6 ticks (of 127) per review and ±16 total from soundcheck
    — about 12% of the knob's travel — applied slowly, with a freeze
    lock per knob in the console.</div>
  ${vids("clink", "clink2")}`;
},

cal(){
  const c = S?.live?.calibration;
  return `<h2 class="title">Calibrate the vocal detector</h2>
  <p class="sub">Twenty seconds of your actual material teaches the
    director what vocals sound like <i>in your mix</i> — much sharper
    than the generic detector.</p>
  ${todo(1, `Get the band ready, then press <b>Run calibration</b>
    below`)}
  ${todo(2, `Record <b>10 s instrumental</b> (band plays, nobody sings),
    then <b>10 s with the main singer</b>`)}
  ${todo(3, `Finish — you'll get a quality score (d′). Above 1.5 is
    great; below, the director simply switches more cautiously`)}
  <button class="btn" id="wCalBtn">Run calibration</button>
  ${chk(c?.calibrated ? "ok" : "warn", c?.calibrated
    ? `calibrated — d′ ${c.d_prime}`
    : "not calibrated yet — you can also skip and use the generic detector")}`;
},

voice(){
  const alive = S && S.audio_alive;
  return `<h2 class="title">Voice check</h2>
  <p class="sub">Have both speakers say a few sentences at normal volume.
    AutoDirector learns each room's noise floor by itself and keeps each
    voice gated, leveled and EQ'd automatically from here on.</p>
  ${todo(1, `Speaker 1: talk for ~10 seconds`)}
  ${todo(2, `Speaker 2: talk for ~10 seconds`)}
  ${todo(3, `Watch the speaker cards on the console — you should see the
    VU meters move and the active speaker light up`)}
  ${chk(alive ? "ok" : "warn", alive
    ? "audio flowing — the director can hear the room"
    : "no audio yet — check the mic devices from the previous step")}`;
},

golive(){
  const live = wizMode === "live";
  const M = S && S.mixer;
  return `<h2 class="title">Go live</h2>
  <p class="sub">Everything's wired. The launch ritual is three moves:</p>
  ${live ? todo(1, `<b>Soundcheck:</b> play for ~45 seconds at show
    level${M ? " — AutoDirector snapshots the baseline itself (or press <i>Soundcheck snapshot</i> on the mixer card)" : ""}`,
    "The mix you soundcheck is the mix it protects all night.") : ""}
  ${todo(live ? 2 : 1, `Flip the <b>DIRECTING</b> switch in the header
    (or press <kbd class="path">D</kbd>) — the ON AIR card goes live and
    the director takes the wheel`)}
  ${todo(live ? 3 : 2, `In OBS: <kbd class="path">Settings → Stream</kbd>
    → paste your YouTube stream key → <kbd class="path">Start
    Streaming</kbd>`, "The video below covers the best YouTube settings end to end.")}
  <div class="note"><b>Fail-safe by design:</b> if AutoDirector ever
    hiccups, OBS keeps streaming and your DAW keeps playing exactly as
    they were — cuts just pause. For unattended shows: disable sleep &
    auto-updates, schedule Do&nbsp;Not&nbsp;Disturb, use wired Ethernet,
    and turn on OBS's auto-reconnect.</div>
  <button class="btn" id="wFinish">Finish — I'm broadcast ready 🎬</button>
  ${vids("golive")}`;
},
};

/* ---------- wizard machinery ---------- */
let wizScenes = [], wizDevices = [];

function wizPaint(){
  const steps = wizSteps();
  if (wizStep >= steps.length) wizStep = steps.length - 1;
  const cur = steps[wizStep];
  $("wizRail").innerHTML = steps.map((s, i) => `
    <div class="rstep ${i === wizStep ? "cur" : ""} ${wizDone.has(s.id) ? "done" : ""}"
         data-i="${i}">
      <span class="n">${wizDone.has(s.id) ? "✓" : i + 1}</span>
      <span>${s.name}</span>${s.opt ? `<span class="opt">OPTIONAL</span>` : ""}
    </div>`).join("");
  $("wizContent").innerHTML =
    (cur.id === "mixer" || cur.id === "knobs" || (cur.id === "audio" && wizMode === "live")
      ? `<div class="osseg" id="wizOsSeg">
           <button data-os="mac" class="${wizOS === "mac" ? "sel" : ""}">macOS</button>
           <button data-os="win" class="${wizOS === "win" ? "sel" : ""}">Windows</button>
         </div>` : "")
    + WREND[cur.id]();
  $("wizBack").style.visibility = wizStep === 0 ? "hidden" : "visible";
  $("wizNext").textContent = cur.opt ? "Skip / Next →"
    : wizStep === steps.length - 1 ? "Done" : "Next →";
  wizBind(cur.id);
}

function wizBind(id){
  const seg = $("wizOsSeg");
  if (seg) seg.onclick = e => {
    if (e.target.dataset.os){ wizOS = e.target.dataset.os; wizPaint(); } };
  document.querySelectorAll("#wizRail .rstep").forEach(el =>
    el.onclick = () => { wizApply(); wizStep = +el.dataset.i; wizRefresh(); });
  document.querySelectorAll("#wiz .vcard .thumb").forEach(th =>
    th.onclick = () => {
      const card = th.closest(".vcard");
      th.outerHTML = `<iframe src="https://www.youtube.com/embed/${card.dataset.vid}?autoplay=1"
        allow="autoplay; encrypted-media; picture-in-picture" allowfullscreen></iframe>`;
    });
  if (id === "welcome")
    document.querySelectorAll("#wiz .mcard").forEach(c =>
      c.onclick = () => { wizMode = c.dataset.m; wizPaint(); });
  if (id === "obs"){
    $("wHost").value = wcfg?.obs?.host ?? "127.0.0.1";
    $("wPort").value = wcfg?.obs?.port ?? 4455;
    $("wPass").value = wcfg?.obs?.password ?? "";
    $("wObsTest").onclick = async () => {
      await wizApply();
      $("wObsTest").textContent = "testing…";
      await new Promise(r => setTimeout(r, 1400));
      await wizRefresh();
      toast(S.obs_state === "connected"
        ? `✓ Connected — ${wizScenes.length} scenes found`
        : "✗ Not connected — re-check the password in OBS",
        S.obs_state !== "connected");
    };
  }
  if (id === "cal") $("wCalBtn").onclick = () => {
    $("wiz").classList.remove("open"); openCal();
    toast("Guide paused — press 🧭 Guide to come back after calibrating");
  };
  if (id === "golive") $("wFinish").onclick = () => {
    wizSteps().forEach(s => wizDone.add(s.id)); wizPersist();
    localStorage.setItem("ad_wiz_finished", "1");
    $("wiz").classList.remove("open");
    toast("You're broadcast ready 🎬 — re-run the guide any time");
  };
}

/* Save whatever the current step edited into the config. */
async function wizApply(){
  if (!wcfg) return;
  const id = wizSteps()[wizStep].id;
  const c = JSON.parse(JSON.stringify(wcfg));
  let dirty = false;
  if (id === "welcome" && c.mode !== wizMode){ c.mode = wizMode; dirty = true; }
  if (id === "obs" && $("wHost")){
    c.obs = {host: $("wHost").value || "127.0.0.1",
             port: parseInt($("wPort").value) || 4455,
             password: $("wPass").value};
    dirty = true;
  }
  if (id === "scenes"){
    if (wizMode === "live" && $("wSinger")){
      c.live = c.live || {};
      c.live.singer_scene = $("wSinger").value;
      c.live.instrumental_scenes = $("wInstr").value.split("\n")
        .map(s => s.trim()).filter(Boolean);
      dirty = true;
    } else if ($("wWide")){
      c.podcast = c.podcast || {};
      const names = [...document.querySelectorAll(".wSpkName")];
      const meds = [...document.querySelectorAll(".wSpkMed")];
      const closes = [...document.querySelectorAll(".wSpkClose")];
      c.podcast.speakers = names.map((n, i) => Object.assign(
        (c.podcast.speakers || [])[i] || {}, {
          name: n.value || `Speaker ${i + 1}`,
          medium_scene: meds[i].value, closeup_scene: closes[i].value}));
      c.podcast.wide_scene = $("wWide").value;
      dirty = true;
    }
  }
  if (id === "audio"){
    if (wizMode === "live" && $("wDevice")){
      c.live = c.live || {};
      c.live.device = $("wDevice").value || null;
      dirty = true;
    } else if (document.querySelector(".wSpkDev")){
      c.podcast = c.podcast || {};
      const devs = [...document.querySelectorAll(".wSpkDev")];
      const srcs = [...document.querySelectorAll(".wSpkSrc")];
      c.podcast.speakers = devs.map((d, i) => Object.assign(
        (c.podcast.speakers || [])[i] || {name: `Speaker ${i + 1}`}, {
          device: d.value || null, obs_source: srcs[i].value}));
      dirty = true;
    }
  }
  if (id === "mixer" && $("wMixEn")){
    c.live = c.live || {}; c.live.mixer = c.live.mixer || {};
    c.live.mixer.enabled = $("wMixEn").value === "on";
    dirty = true;
  }
  if (id === "knobs" && $("wKnobs")){
    c.live = c.live || {}; c.live.mixer = c.live.mixer || {};
    c.live.mixer.knobs = $("wKnobs").value.split("\n").map(line => {
      const m = line.match(/^\s*(\d+)\s*[:\-]\s*(.+?)\s*$/);
      return m ? {cc: parseInt(m[1]), name: m[2]} : null;
    }).filter(Boolean);
    dirty = true;
  }
  if (dirty){
    const r = await api.post("/api/config", c);
    wcfg = c; cfg = c;
    if (r.error) toast("Saved, but: " + r.error, true);
  }
}

async function wizRefresh(){
  try{
    const [sc, dv] = await Promise.all([api.get("/api/scenes"),
                                        api.get("/api/devices")]);
    wizScenes = sc.scenes || [];
    wizDevices = (dv.devices || []).map(d => d.name);
  }catch(e){ /* offline check chips will say so */ }
  wizPaint();
}

function wizPersist(){
  localStorage.setItem("ad_wiz_done", JSON.stringify([...wizDone]));
}

async function openWizard(step){
  wcfg = await api.get("/api/config");
  wizMode = wcfg.mode === "podcast" ? "podcast" : "live";
  if (typeof step === "number") wizStep = step;
  $("wiz").classList.add("open");
  await wizRefresh();
}

$("wizClose").onclick = () => $("wiz").classList.remove("open");
$("wizBack").onclick = async () => {
  await wizApply(); wizStep = Math.max(0, wizStep - 1); wizRefresh(); };
$("wizNext").onclick = async () => {
  const steps = wizSteps();
  await wizApply();
  wizDone.add(steps[wizStep].id); wizPersist();
  if (wizStep >= steps.length - 1){ $("wiz").classList.remove("open"); return; }
  wizStep += 1; wizRefresh();
};
document.addEventListener("keydown", e => {
  if (e.key === "Escape") $("wiz").classList.remove("open");
});
window.openWizard = openWizard;
const _wizGuideBtn = $("btnGuide");
if (_wizGuideBtn) _wizGuideBtn.onclick = () => openWizard();

/* Auto-open on first run: never finished the guide and OBS isn't
   connected yet -> this person needs the tour. One-shot per load. */
let _wizAutoTried = false;
setTimeout(function autoOpen(){
  if (_wizAutoTried) return;
  _wizAutoTried = true;
  if (!localStorage.getItem("ad_wiz_finished")
      && (!S || S.obs_state !== "connected" || S.mode === "setup"))
    openWizard(0);
}, 900);

/* Keep the live-check chips honest while the wizard is open. */
setInterval(() => {
  if (!$("wiz").classList.contains("open") || !S) return;
  /* re-render only when no input is focused, so typing never resets */
  const a = document.activeElement;
  if (a && (a.tagName === "INPUT" || a.tagName === "TEXTAREA"
            || a.tagName === "IFRAME" || a.tagName === "SELECT")) return;
  if ($("wiz").querySelector("iframe")) return;  /* don't kill playback */
  /* preserve anything typed but not applied yet across the repaint */
  const vals = {};
  $("wizContent").querySelectorAll("input,select,textarea").forEach((el, i) =>
    vals[el.id || el.className + i] = el.value);
  wizPaint();
  $("wizContent").querySelectorAll("input,select,textarea").forEach((el, i) => {
    const k = el.id || el.className + i;
    if (k in vals) el.value = vals[k];
  });
}, 2000);
</script>
"""
