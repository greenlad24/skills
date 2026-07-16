/* ==========================================================================
   app.js — VOX front-end controller.
   Loads /api/config, runs the chat SSE stream, plays Piper TTS through a
   Web Audio AnalyserNode (which hologram.js reads for lip-sync), and handles
   optional push-to-talk mic capture. 100% offline; no external requests.
   ========================================================================== */

import { createHologram } from './hologram.js';
import { createPanels } from './panels.js';

/* ---- DOM refs ----------------------------------------------------------- */
const $ = (id) => document.getElementById(id);
const els = {
  canvas:    $('holo-canvas'),
  status:    $('statusline'),
  transcript:$('transcript'),
  banner:    $('banner'),
  composer:  $('composer'),
  prompt:    $('prompt'),
  sendBtn:   $('send-btn'),
  micBtn:    $('mic-btn'),
  webToggle: $('web-toggle'),
  panels:    $('holo-panels'),
  wakeGate:  $('wake-gate'),
  wakeBtn:   $('wake-btn'),
  wakeNote:  $('wake-note'),
};

/* ---- App state ---------------------------------------------------------- */
const state = {
  config: null,
  history: [],        // rolling [{role,content}] — excludes system prompt
  busy: false,        // a chat turn is in flight
  awake: false,       // audio unlocked by a user gesture
  web: true,          // v2: consult web sources (only meaningful if web_ready)
};

let audioCtx = null;      // Web Audio graph
let analyser = null;      // shared node the hologram reads
let masterGain = null;
let activeSource = null;   // currently-playing AudioBufferSourceNode

const holo = createHologram(els.canvas);
holo.setPlaceholder();     // draw *something* immediately, before config lands
holo.start();

// v2: floating holographic source/web panels (columns flank Vox's face).
const panels = createPanels(els.panels);

/* ==========================================================================
   Boot
   ========================================================================== */
init();

async function init() {
  try {
    const res = await fetch('/api/config', { cache: 'no-store' });
    if (!res.ok) throw new Error('config ' + res.status);
    state.config = await res.json();
  } catch (e) {
    // Backend not up yet — degrade to a friendly offline shell.
    state.config = {
      name: 'Vox', llm_ready: false, tts_ready: false, stt_ready: false,
      portrait_present: false, portrait_url: '/assets/portrait.png',
    };
    setStatus('Cannot reach VOX server — is it running?', 'err');
  }
  applyConfig(state.config);
}

function applyConfig(cfg) {
  // v2: point lip-sync/blink at the head. Must precede the portrait/placeholder
  // draw so the standing-figure placeholder is built for the right head box.
  if (cfg.face_box) holo.setFaceBox(cfg.face_box);

  // Portrait vs placeholder (a full-body standing figure when no portrait).
  if (cfg.portrait_present && cfg.portrait_url) {
    holo.setPortrait(cfg.portrait_url).then((ok) => {
      if (!ok) holo.setPlaceholder();
    });
  } else {
    holo.setPlaceholder();
  }

  // v2: web-sources toggle. Hidden entirely unless the backend reports web_ready;
  // defaults ON. When off (or web_ready:false) we send web:false and get no panels.
  if (cfg.web_ready) {
    els.webToggle.hidden = false;
    setWeb(true);
    els.webToggle.addEventListener('click', () => setWeb(!state.web));
  } else {
    els.webToggle.hidden = true;
    state.web = false;
  }

  // Mic only if STT is ready AND the browser can record.
  const canRecord = supportsRecording();
  if (cfg.stt_ready && canRecord) {
    els.micBtn.hidden = false;
    wireMic();
  } else {
    els.micBtn.hidden = true;
  }

  // Banners / status.
  if (cfg.llm_ready === false) {
    showBanner('LLM offline — start Ollama or llama.cpp, then reload.');
  } else if (cfg.tts_ready === false) {
    showBanner('Voice offline — text only.');
  } else {
    hideBanner();
  }

  if (state.config && state.config.llm_ready !== false) {
    setStatus('Ready. ' + (cfg.model ? '[' + cfg.model + ']' : ''));
  }

  // Wake gate note reflects whether there will be a voice at all.
  els.wakeNote.textContent = cfg.tts_ready
    ? 'Click to enable Vox’s voice.'
    : 'Voice module offline — text responses only.';
}

/* ==========================================================================
   Audio unlock (autoplay policy) — the wake gate
   ========================================================================== */
els.wakeBtn.addEventListener('click', awaken);

function awaken() {
  if (!state.awake) {
    try {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (AC) {
        audioCtx = new AC();
        masterGain = audioCtx.createGain();
        masterGain.gain.value = 1.0;
        analyser = audioCtx.createAnalyser();
        analyser.fftSize = 1024;
        analyser.smoothingTimeConstant = 0.6;
        // graph: source -> analyser -> masterGain -> destination
        analyser.connect(masterGain);
        masterGain.connect(audioCtx.destination);
      }
      // Some browsers start the context suspended until a gesture resumes it.
      if (audioCtx && audioCtx.state === 'suspended') audioCtx.resume();
    } catch (e) {
      // Audio simply won't be available; text still works.
      audioCtx = null;
    }
    state.awake = true;
  }

  els.wakeGate.classList.add('hidden');
  setTimeout(() => { els.wakeGate.style.display = 'none'; }, 700);
  els.prompt.focus();

  // Greet on first awakening (spoken if TTS is up).
  greet();
}

let greeted = false;
function greet() {
  if (greeted) return;
  greeted = true;
  const name = (state.config && state.config.name) || 'Vox';
  const text = 'I am ' + name + ', a compendium of all human knowledge. How may I assist you?';
  addLine('vox', name, text);
  state.history.push({ role: 'assistant', content: text });
  speak(text);
}

/* ==========================================================================
   Chat send flow (SSE)
   ========================================================================== */
els.composer.addEventListener('submit', (e) => {
  e.preventDefault();
  send(els.prompt.value);
});
// Enter-to-send is native (form submit); Shift not needed for single-line input.

async function send(raw) {
  const text = (raw || '').trim();
  if (!text || state.busy) return;
  if (state.config && state.config.llm_ready === false) {
    showBanner('LLM offline — start Ollama or llama.cpp, then reload.');
    return;
  }

  els.prompt.value = '';
  addLine('user', 'You', text);
  state.history.push({ role: 'user', content: text });

  // Fresh turn → clear the previous answer's holo source cards.
  panels.clear();

  setBusy(true);
  const name = (state.config && state.config.name) || 'Vox';
  const lineEl = addLine('vox', name, '');
  lineEl.querySelector('.msg').classList.add('cursor');

  let full = '';
  try {
    full = await streamChat(text, (tok) => {
      full += tok;
      updateLine(lineEl, full);
    });
  } catch (err) {
    lineEl.querySelector('.msg').classList.remove('cursor');
    updateLine(lineEl, '[transmission error] ' + (err && err.message ? err.message : err));
    setBusy(false);
    return;
  }

  lineEl.querySelector('.msg').classList.remove('cursor');
  full = (full || '').trim();
  updateLine(lineEl, full);
  if (full) state.history.push({ role: 'assistant', content: full });
  trimHistory();
  setBusy(false);

  if (full) speak(full);
}

/* Consume the POST /api/chat SSE stream.
   EventSource can't POST, so we read the fetch body ourselves. On older Safari
   without streaming bodies we fall back to reading the whole response. */
async function streamChat(message, onToken) {
  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' },
    body: JSON.stringify({ message, history: historyForSend(), web: !!state.web }),
  });
  if (!res.ok) throw new Error('chat ' + res.status);

  // Streaming path (Safari 15.4+, Chrome, Firefox).
  if (res.body && res.body.getReader) {
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';
    let finalText = '';
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const parsed = drainEvents(buf);
      buf = parsed.rest;
      for (const evt of parsed.events) {
        const r = handleEvent(evt, onToken);
        if (r.done) finalText = r.text;
        if (r.error) throw new Error(r.error);
      }
    }
    // Flush any trailing event without a blank-line terminator.
    const tail = drainEvents(buf + '\n\n');
    for (const evt of tail.events) {
      const r = handleEvent(evt, onToken);
      if (r.done) finalText = r.text;
      if (r.error) throw new Error(r.error);
    }
    return finalText || null;
  }

  // Fallback: no streaming — parse the whole SSE payload at once.
  const whole = await res.text();
  const parsed = drainEvents(whole + '\n\n');
  let finalText = '';
  for (const evt of parsed.events) {
    const r = handleEvent(evt, onToken);
    if (r.done) finalText = r.text;
    if (r.error) throw new Error(r.error);
  }
  return finalText || null;
}

/* Split an SSE buffer into complete events (separated by a blank line).
   Returns {events:[{data:"..."}], rest:"<incomplete tail>"}. */
function drainEvents(buf) {
  const events = [];
  const chunks = buf.split(/\r?\n\r?\n/);
  const rest = chunks.pop(); // last piece may be incomplete
  for (const chunk of chunks) {
    let data = '';
    for (const line of chunk.split(/\r?\n/)) {
      if (line.startsWith('data:')) data += line.slice(5).trimStart();
      // (ignore event:/id:/comment lines — backend only sends data:)
    }
    if (data) events.push({ data });
  }
  return { events, rest };
}

/* Interpret one SSE data payload per API.md. */
function handleEvent(evt, onToken) {
  let obj;
  try { obj = JSON.parse(evt.data); }
  catch (e) { return {}; } // ignore keep-alives / malformed
  if (obj.type === 'token') {
    if (obj.text) onToken(obj.text);
    return {};
  }
  // v2: a holographic source/web card materializes beside Vox as he speaks.
  if (obj.type === 'panel') {
    if (obj.panel) { try { panels.add(obj.panel); } catch (e) {} }
    return {};
  }
  if (obj.type === 'done') return { done: true, text: obj.text || '' };
  if (obj.type === 'error') return { error: obj.message || 'unknown error' };
  return {};
}

/* ==========================================================================
   TTS playback → analyser → hologram lip-sync
   ========================================================================== */
async function speak(text) {
  if (!text) return;
  if (!state.config || state.config.tts_ready === false) return;
  if (!audioCtx || !analyser) return; // not awake / no Web Audio

  let buf;
  try {
    const res = await fetch('/api/tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    if (res.status === 503) return;         // TTS unavailable — stay silent
    if (!res.ok) return;
    const bytes = await res.arrayBuffer();
    buf = await decodeAudio(bytes);
  } catch (e) {
    return; // never let audio failure break the conversation
  }
  if (!buf) return;

  // Stop anything currently speaking.
  stopAudio();

  try {
    if (audioCtx.state === 'suspended') await audioCtx.resume();
    const src = audioCtx.createBufferSource();
    src.buffer = buf;
    src.connect(analyser); // → masterGain → destination (built in awaken())
    activeSource = src;
    holo.speak(analyser);  // hand the live node to the renderer
    src.onended = () => {
      if (activeSource === src) {
        activeSource = null;
        holo.stopSpeaking();
      }
    };
    src.start(0);
  } catch (e) {
    holo.stopSpeaking();
  }
}

function stopAudio() {
  if (activeSource) {
    try { activeSource.onended = null; activeSource.stop(0); } catch (e) {}
    activeSource = null;
  }
  holo.stopSpeaking();
}

// decodeAudioData with both promise and legacy-callback signatures (Safari).
function decodeAudio(arrayBuffer) {
  return new Promise((resolve, reject) => {
    try {
      const p = audioCtx.decodeAudioData(arrayBuffer, resolve, reject);
      if (p && typeof p.then === 'function') p.then(resolve, reject);
    } catch (e) { reject(e); }
  });
}

/* ==========================================================================
   Mic (push-to-talk) — only wired when stt_ready && MediaRecorder present
   ========================================================================== */
function supportsRecording() {
  return !!(navigator.mediaDevices &&
            navigator.mediaDevices.getUserMedia &&
            window.MediaRecorder);
}

let mediaRecorder = null;
let micChunks = [];
let micStream = null;
let recording = false;

function wireMic() {
  const start = (e) => { e.preventDefault(); startRecording(); };
  const stop  = (e) => { e.preventDefault(); stopRecording(); };
  // Pointer events cover mouse + touch on Safari 15.
  els.micBtn.addEventListener('pointerdown', start);
  els.micBtn.addEventListener('pointerup', stop);
  els.micBtn.addEventListener('pointerleave', () => { if (recording) stopRecording(); });
  els.micBtn.addEventListener('pointercancel', () => { if (recording) stopRecording(); });
}

async function startRecording() {
  if (recording || state.busy) return;
  try {
    micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (e) {
    showBanner('Microphone access denied.');
    return;
  }
  micChunks = [];
  // Let the browser pick a supported container (Safari → mp4/aac, others → webm).
  let mr;
  try { mr = new MediaRecorder(micStream); }
  catch (e) { releaseMic(); return; }
  mediaRecorder = mr;
  mr.ondataavailable = (ev) => { if (ev.data && ev.data.size) micChunks.push(ev.data); };
  mr.onstop = onRecordingStopped;
  mr.start();
  recording = true;
  els.micBtn.classList.add('recording');
  setStatus('Listening…');
}

function stopRecording() {
  if (!recording) return;
  recording = false;
  els.micBtn.classList.remove('recording');
  try { if (mediaRecorder && mediaRecorder.state !== 'inactive') mediaRecorder.stop(); }
  catch (e) { releaseMic(); }
}

async function onRecordingStopped() {
  const type = (mediaRecorder && mediaRecorder.mimeType) || 'audio/webm';
  const blob = new Blob(micChunks, { type });
  releaseMic();
  if (!blob.size) { setStatus('Ready.'); return; }

  setStatus('Transcribing…');
  try {
    const fd = new FormData();
    fd.append('audio', blob, 'speech');
    const res = await fetch('/api/stt', { method: 'POST', body: fd });
    if (res.status === 503) { showBanner('Speech recognition offline.'); setStatus('Ready.'); return; }
    if (!res.ok) throw new Error('stt ' + res.status);
    const data = await res.json();
    const text = (data && data.text || '').trim();
    setStatus('Ready.');
    if (text) {
      els.prompt.value = text;
      send(text); // auto-send the transcribed utterance
    }
  } catch (e) {
    setStatus('Transcription failed.', 'err');
  }
}

function releaseMic() {
  if (micStream) { micStream.getTracks().forEach((t) => t.stop()); micStream = null; }
  mediaRecorder = null;
}

/* ==========================================================================
   Transcript + history helpers
   ========================================================================== */
function addLine(kind, who, text) {
  const line = document.createElement('div');
  line.className = 'line ' + kind;
  const whoEl = document.createElement('span');
  whoEl.className = 'who';
  whoEl.textContent = who;
  const msg = document.createElement('span');
  msg.className = 'msg';
  msg.textContent = text;
  line.appendChild(whoEl);
  line.appendChild(document.createTextNode(' '));
  line.appendChild(msg);
  els.transcript.appendChild(line);
  scrollTranscript();
  return line;
}
function updateLine(line, text) {
  line.querySelector('.msg').textContent = text;
  scrollTranscript();
}
function scrollTranscript() {
  els.transcript.scrollTop = els.transcript.scrollHeight;
}

// Keep the rolling history from growing unbounded (protects the tiny model's
// context window). Retain the most recent turns.
function trimHistory() {
  const MAX = 20; // last ~10 exchanges
  if (state.history.length > MAX) {
    state.history = state.history.slice(state.history.length - MAX);
  }
}
// History to send excludes the message we just pushed (it goes in `message`).
function historyForSend() {
  const h = state.history.slice(0, -1); // drop the current user turn
  return h.map((m) => ({ role: m.role, content: m.content }));
}

/* ==========================================================================
   Small UI helpers
   ========================================================================== */
function setBusy(b) {
  state.busy = b;
  els.sendBtn.disabled = b;
  els.prompt.disabled = b;
  if (b) setStatus('Vox is thinking…');
  else { setStatus('Ready.'); els.prompt.focus(); }
}
function setStatus(text, cls) {
  els.status.textContent = text;
  els.status.className = 'statusline' + (cls ? ' ' + cls : '');
}
// v2: reflect the web-sources toggle in state + button styling.
function setWeb(on) {
  state.web = !!on;
  els.webToggle.setAttribute('aria-pressed', state.web ? 'true' : 'false');
  els.webToggle.classList.toggle('is-on', state.web);
  els.webToggle.title = state.web
    ? 'Web records ON — Vox consults the library'
    : 'Web records OFF — Vox answers from local knowledge';
}
function showBanner(text) {
  els.banner.textContent = text;
  els.banner.hidden = false;
}
function hideBanner() {
  els.banner.hidden = true;
}
