/* Vibration Poster Studio — frontend */

const DAY_KEYS = ['tuesday', 'wednesday', 'thursday', 'friday', 'saturday'];
const DAY_LABEL = { tuesday: 'Tuesday', wednesday: 'Wednesday', thursday: 'Thursday', friday: 'Friday', saturday: 'Saturday' };

const S = {
  activeWeek: '',
  week: null,
  settings: null,
  voice: null,
  brand: null,
  presets: [],
  view: 'overview', // 'overview' | dayKey
  pins: {}, // dayKey -> last pinterest results
  busy: {}, // dayKey -> message
  scheduleResults: null,
  accounts: null,
};

const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];

// ---------- api ----------
async function api(method, url, body) {
  const res = await fetch(url, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const json = await res.json().catch(() => ({ error: 'Bad response' }));
  if (!res.ok || json.error) throw new Error(json.error || `HTTP ${res.status}`);
  return json;
}

function toast(msg, isError = false, ms = 4200) {
  const t = $('#toast');
  t.textContent = msg;
  t.className = 'toast' + (isError ? ' error' : '');
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.add('hidden'), ms);
}

function fmtDate(iso) {
  if (!iso) return '';
  const d = new Date(iso + 'T00:00:00');
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result);
    r.onerror = reject;
    r.readAsDataURL(file);
  });
}

function pickFiles({ multiple = true } = {}) {
  return new Promise((resolve) => {
    const inp = document.createElement('input');
    inp.type = 'file';
    inp.accept = 'image/*';
    inp.multiple = multiple;
    inp.onchange = () => resolve([...inp.files]);
    inp.click();
  });
}

// ---------- boot ----------
async function boot() {
  const data = await api('GET', '/api/bootstrap');
  Object.assign(S, {
    activeWeek: data.activeWeek,
    week: data.week,
    settings: data.settings,
    voice: data.voice,
    brand: data.brand,
    presets: data.presets,
  });
  const hash = location.hash.slice(1);
  if (DAY_KEYS.includes(hash)) S.view = hash;
  renderAll();
}

function renderAll() {
  renderWeekLabel();
  renderTabs();
  renderMain();
}

// ---------- header / week ----------
function renderWeekLabel() {
  const start = S.week.days.tuesday.date;
  const end = S.week.days.saturday.date;
  $('#week-label').textContent = `Tue ${fmtDate(start)} — Sat ${fmtDate(end)}`;
  $('#week-date').value = start;
}

async function switchWeek(dateStr) {
  const data = await api('POST', '/api/week', { weekStart: dateStr });
  S.activeWeek = data.activeWeek;
  S.week = data.week;
  S.scheduleResults = null;
  renderAll();
}

$('#week-prev').onclick = () => shiftWeek(-7);
$('#week-next').onclick = () => shiftWeek(7);
$('#week-date').onchange = (e) => switchWeek(e.target.value);
function shiftWeek(days) {
  const d = new Date(S.activeWeek + 'T00:00:00');
  d.setDate(d.getDate() + days);
  const ymd = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  switchWeek(ymd);
}

// ---------- tabs ----------
function dayStatus(day) {
  if (day.scheduled && (day.scheduled.instagram || day.scheduled.facebook)) return 'scheduled';
  if (day.winner) return 'winner';
  return 'empty';
}

function renderTabs() {
  const el = $('#day-tabs');
  el.innerHTML = '';
  const mk = (key, label, dateStr) => {
    const b = document.createElement('div');
    b.className = 'day-tab' + (S.view === key ? ' active' : '');
    b.innerHTML = key === 'overview'
      ? `<span>Week overview</span>`
      : `<span class="dot ${dayStatus(S.week.days[key])}"></span><span>${label}</span><span class="date">${fmtDate(dateStr)}</span>`;
    b.onclick = () => { S.view = key; renderAll(); };
    el.appendChild(b);
  };
  mk('overview', 'Week overview');
  DAY_KEYS.forEach((k) => mk(k, DAY_LABEL[k], S.week.days[k].date));
}

// ---------- main ----------
function renderMain() {
  history.replaceState(null, '', S.view === 'overview' ? '#' : '#' + S.view);
  const main = $('#main');
  main.innerHTML = '';
  const panel = document.createElement('div');
  panel.className = 'panel';
  main.appendChild(panel);
  if (S.view === 'overview') renderOverview(panel);
  else renderDay(panel, S.view);
}

// ============================================================ overview
function renderOverview(root) {
  const grid = document.createElement('div');
  grid.className = 'overview-grid';
  for (const key of DAY_KEYS) {
    const day = S.week.days[key];
    const card = document.createElement('div');
    card.className = 'ov-card';
    const winnerImg = day.winner ? `<img src="/files/${day.winner}" alt="">` : 'no poster yet';
    const sch = day.scheduled || {};
    card.innerHTML = `
      <div class="ov-thumb">${winnerImg}</div>
      <div class="ov-body">
        <div class="ov-day">${DAY_LABEL[key]} · ${fmtDate(day.date)}</div>
        <div class="ov-artist">${esc(day.info.artistName) || '<span style="color:var(--ink-faint)">untitled</span>'}</div>
        <div class="ov-status">
          <span class="${day.winner ? 'yes' : ''}">${day.winner ? '✓' : '·'} poster picked</span>
          <span class="${day.captions.instagram ? 'yes' : ''}">${day.captions.instagram ? '✓' : '·'} captions</span>
          <span class="${sch.instagram ? 'yes' : ''}">${sch.instagram ? '✓ IG scheduled' : '· instagram'}</span>
          <span class="${sch.facebook ? 'yes' : ''}">${sch.facebook ? '✓ FB scheduled' : '· facebook'}</span>
        </div>
      </div>`;
    card.onclick = () => { S.view = key; renderAll(); };
    grid.appendChild(card);
  }
  root.appendChild(grid);

  const sp = document.createElement('div');
  sp.className = 'schedule-panel';
  sp.innerHTML = `
    <h3 style="margin:0" class="display">Schedule the week</h3>
    <label class="checkbox"><input type="checkbox" id="pf-ig" checked> Instagram</label>
    <label class="checkbox"><input type="checkbox" id="pf-fb" checked> Facebook</label>
    <span style="color:var(--ink-faint);font-size:12.5px">Each poster goes out on its own day at ${esc(S.settings.defaultPostTime)} (change in Settings)</span>
    <button class="primary" id="btn-schedule">📅 Schedule all ready days</button>
  `;
  root.appendChild(sp);

  const resBox = document.createElement('div');
  resBox.className = 'schedule-results';
  root.appendChild(resBox);
  if (S.scheduleResults) renderScheduleResults(resBox);

  $('#btn-schedule', sp).onclick = async (e) => {
    const platforms = [];
    if ($('#pf-ig').checked) platforms.push('instagram');
    if ($('#pf-fb').checked) platforms.push('facebook');
    if (!platforms.length) return toast('Pick at least one platform', true);
    const ready = DAY_KEYS.filter((k) => S.week.days[k].winner && (S.week.days[k].captions.instagram || S.week.days[k].captions.facebook));
    if (!ready.length) return toast('No day is ready yet — each day needs a picked poster and captions.', true);
    e.target.disabled = true;
    e.target.textContent = 'Scheduling…';
    try {
      const out = await api('POST', `/api/week/${S.activeWeek}/schedule`, { days: ready, platforms });
      S.week = out.week;
      S.scheduleResults = out.results;
      renderAll();
      const okCount = out.results.filter((r) => r.ok).length;
      toast(`${okCount}/${out.results.length} days scheduled`);
    } catch (err) {
      toast(err.message, true, 8000);
      e.target.disabled = false;
      e.target.textContent = '📅 Schedule all ready days';
    }
  };
}

function renderScheduleResults(box) {
  box.innerHTML = S.scheduleResults
    .map((r) => r.ok
      ? `<div class="ok">✓ ${DAY_LABEL[r.day]}: ${r.steps.join(' → ')}</div>`
      : `<div class="err">✕ ${DAY_LABEL[r.day]}: ${esc(r.error)}</div>`)
    .join('');
}

// ============================================================ day view
function renderDay(root, key) {
  const day = S.week.days[key];
  root.innerHTML = `
    <h2 style="margin:0 0 24px;font-size:26px">${DAY_LABEL[key]} <span style="color:var(--ink-faint);font-size:16px">· ${fmtDate(day.date)}</span></h2>
    <div class="section" id="sec-characters"></div>
    <div class="section" id="sec-style"></div>
    <div class="section" id="sec-details"></div>
    <div class="section" id="sec-generate"></div>
    <div class="section" id="sec-caption"></div>
  `;
  renderCharacters($('#sec-characters', root), key);
  renderStyle($('#sec-style', root), key);
  renderDetails($('#sec-details', root), key);
  renderGenerate($('#sec-generate', root), key);
  renderCaption($('#sec-caption', root), key);
}

// ----- step 1: characters -----
function renderCharacters(el, key) {
  const day = S.week.days[key];
  el.innerHTML = `
    <div class="section-head"><span class="step">1</span><h3>Performers & objects</h3>
      <span class="hint">photos of who (or what) stars on this poster — faces are preserved</span></div>
    <div class="thumb-row" id="char-row"></div>
  `;
  const row = $('#char-row', el);
  for (const c of day.characters) {
    const t = document.createElement('div');
    t.className = 'thumb';
    t.innerHTML = `<img src="/files/${c.file}" alt=""><button class="rm" title="remove">✕</button>`;
    $('img', t).onclick = () => openLightbox(`/files/${c.file}`);
    $('.rm', t).onclick = async () => {
      const out = await api('DELETE', `/api/week/${S.activeWeek}/day/${key}/images/${c.id}`);
      S.week.days[key] = out.day;
      renderDay(el.closest('.panel'), key);
    };
    row.appendChild(t);
  }
  const add = document.createElement('button');
  add.className = 'upload-tile';
  add.innerHTML = '＋<span>add photos</span>';
  add.onclick = async () => {
    const files = await pickFiles();
    if (!files.length) return;
    const images = await Promise.all(files.map(async (f) => ({ name: f.name, dataUrl: await readFileAsDataUrl(f) })));
    const out = await api('POST', `/api/week/${S.activeWeek}/day/${key}/images`, { images, kind: 'character' });
    S.week.days[key] = out.day;
    renderDay(el.closest('.panel'), key);
  };
  row.appendChild(add);
}

// ----- step 2: style -----
function renderStyle(el, key) {
  const day = S.week.days[key];
  el.innerHTML = `
    <div class="section-head"><span class="step">2</span><h3>Style</h3>
      <span class="hint">pick one of your signature looks, or hunt a new one on Pinterest</span></div>
    <div class="preset-row" id="preset-row"></div>
    <div style="margin-top:18px" class="pin-search">
      <input id="pin-q" placeholder="Search Pinterest for a style… e.g. “vintage jazz poster gold”" value="${esc(day.keyword)}" />
      <button id="pin-go">Search Pinterest</button>
      <button id="ref-upload" title="Upload your own reference image">⬆ upload reference</button>
    </div>
    <div id="pin-results"></div>
    <div id="ref-row-wrap" style="margin-top:14px"></div>
  `;

  // Presets
  const prow = $('#preset-row', el);
  const auto = document.createElement('div');
  auto.className = 'preset auto-card' + (day.stylePreset === 'auto' ? ' selected' : '');
  auto.textContent = 'No preset — use my reference images only';
  auto.onclick = () => setPreset('auto');
  prow.appendChild(auto);
  for (const p of S.presets) {
    const c = document.createElement('div');
    c.className = 'preset' + (day.stylePreset === p.id ? ' selected' : '');
    c.innerHTML = `<img src="/assets/style-presets/${p.file}" alt=""><div class="preset-name">${esc(p.name)}</div>`;
    c.onclick = () => setPreset(p.id);
    prow.appendChild(c);
  }
  async function setPreset(id) {
    day.stylePreset = id;
    await api('PATCH', `/api/week/${S.activeWeek}/day/${key}`, { stylePreset: id });
    renderStyle(el, key);
  }

  // Pinterest search
  $('#pin-go', el).onclick = doSearch;
  $('#pin-q', el).onkeydown = (e) => { if (e.key === 'Enter') doSearch(); };
  async function doSearch() {
    const q = $('#pin-q', el).value.trim();
    if (!q) return;
    day.keyword = q;
    api('PATCH', `/api/week/${S.activeWeek}/day/${key}`, { keyword: q }).catch(() => {});
    const box = $('#pin-results', el);
    box.innerHTML = `<div class="working"><span class="spinner"></span> Searching Pinterest for “${esc(q)}”…</div>`;
    try {
      const out = await api('GET', `/api/pinterest/search?q=${encodeURIComponent(q)}`);
      S.pins[key] = out.pins;
      renderPins();
    } catch (err) {
      box.innerHTML = `<div style="color:var(--danger);font-size:13px;line-height:1.6">${esc(err.message)}</div>`;
    }
  }

  function renderPins() {
    const box = $('#pin-results', el);
    const pins = S.pins[key] || [];
    if (!pins.length) { box.innerHTML = ''; return; }
    box.innerHTML = `<div class="pin-grid"></div>`;
    const grid = $('.pin-grid', box);
    for (const pin of pins) {
      const d = document.createElement('div');
      d.className = 'pin';
      d.innerHTML = `<img loading="lazy" src="${esc(pin.thumb || pin.image)}" alt="${esc(pin.title)}">`;
      d.onclick = async () => {
        if (d.classList.contains('added')) return;
        d.classList.add('added');
        try {
          const out = await api('POST', `/api/week/${S.activeWeek}/day/${key}/reference-from-url`, { url: pin.image, title: pin.title });
          S.week.days[key] = out.day;
          renderRefs();
          toast('Style reference added');
        } catch (err) {
          d.classList.remove('added');
          toast(err.message, true);
        }
      };
      grid.appendChild(d);
    }
  }
  if (S.pins[key]) renderPins();

  // Manual reference upload
  $('#ref-upload', el).onclick = async () => {
    const files = await pickFiles();
    if (!files.length) return;
    const images = await Promise.all(files.map(async (f) => ({ name: f.name, dataUrl: await readFileAsDataUrl(f) })));
    const out = await api('POST', `/api/week/${S.activeWeek}/day/${key}/images`, { images, kind: 'reference' });
    S.week.days[key] = out.day;
    renderRefs();
  };

  function renderRefs() {
    const day2 = S.week.days[key];
    const wrap = $('#ref-row-wrap', el);
    if (!day2.references.length) { wrap.innerHTML = ''; return; }
    wrap.innerHTML = `<div class="section-head" style="margin-bottom:8px"><span class="hint">chosen style references:</span></div><div class="thumb-row"></div>`;
    const row = $('.thumb-row', wrap);
    for (const r of day2.references) {
      const t = document.createElement('div');
      t.className = 'thumb';
      t.innerHTML = `<img src="/files/${r.file}" alt=""><button class="rm">✕</button>`;
      $('img', t).onclick = () => openLightbox(`/files/${r.file}`);
      $('.rm', t).onclick = async () => {
        const out = await api('DELETE', `/api/week/${S.activeWeek}/day/${key}/images/${r.id}`);
        S.week.days[key] = out.day;
        renderRefs();
      };
      row.appendChild(t);
    }
  }
  renderRefs();
}

// ----- step 3: details -----
function renderDetails(el, key) {
  const day = S.week.days[key];
  const f = (id, label, placeholder, value, wide) => `
    <div class="field" ${wide ? 'style="grid-column:1/-1"' : ''}>
      <label>${label}</label>
      ${wide
        ? `<textarea id="${id}" placeholder="${esc(placeholder)}">${esc(value)}</textarea>`
        : `<input id="${id}" placeholder="${esc(placeholder)}" value="${esc(value)}">`}
    </div>`;
  el.innerHTML = `
    <div class="section-head"><span class="step">3</span><h3>This day's details</h3>
      <span class="hint">what the poster must say — spelling is reproduced exactly</span></div>
    <div class="grid3">
      ${f('d-artist', 'Artist / event name (headline)', 'e.g. ALIONA', day.info.artistName)}
      ${f('d-genres', 'Genre / tagline', 'e.g. RnB - Soul - Pop', day.info.genres)}
      ${f('d-time', 'Time line', 'e.g. Show starts 10pm - late', day.info.showTime)}
    </div>
    <div class="grid2" style="margin-top:14px">
      ${f('d-special', "What's special about this day?", 'e.g. open jam night, ladies night, guest saxophonist…', day.info.special, true)}
    </div>
    <div class="grid2" style="margin-top:14px">
      ${f('d-mustwords', 'Words that MUST appear on the poster', 'e.g. Free entry', day.info.mustWords)}
      ${f('d-notes', 'Extra notes for the designer', 'mood, colors to avoid, props…', day.info.notes)}
    </div>
  `;
  const bind = (id, field) => {
    const inp = $('#' + id, el);
    inp.onchange = () => {
      day.info[field] = inp.value;
      api('PATCH', `/api/week/${S.activeWeek}/day/${key}`, { info: { [field]: inp.value } }).catch((e) => toast(e.message, true));
    };
  };
  bind('d-artist', 'artistName');
  bind('d-genres', 'genres');
  bind('d-time', 'showTime');
  bind('d-special', 'special');
  bind('d-mustwords', 'mustWords');
  bind('d-notes', 'notes');
}

// ----- step 4: generate -----
function renderGenerate(el, key) {
  const day = S.week.days[key];
  el.innerHTML = `
    <div class="section-head"><span class="step">4</span><h3>Generate & pick</h3>
      <span class="hint">three art-directed takes: faithful · recomposed · type-forward</span></div>
    <div class="gen-bar">
      <button class="primary" id="btn-generate">✨ Generate 3 variations</button>
      <span id="gen-status"></span>
    </div>
    <div id="gen-gallery"></div>
  `;

  const btn = $('#btn-generate', el);
  const status = $('#gen-status', el);
  if (S.busy[key]) {
    btn.disabled = true;
    status.innerHTML = `<span class="working"><span class="spinner"></span> ${esc(S.busy[key])}</span>`;
  }

  btn.onclick = async () => {
    if (!day.info.artistName && !day.info.special) {
      return toast('Give the day at least a headline (step 3) first.', true);
    }
    S.busy[key] = 'Designing 3 posters… this takes 1–3 minutes. You can switch to other days meanwhile.';
    renderGenerate(el, key);
    try {
      const out = await api('POST', `/api/week/${S.activeWeek}/day/${key}/generate`, { count: 3 });
      S.week.days[key] = out.day;
      if (out.generation.errors?.length) toast('Some variations failed: ' + out.generation.errors.join(' | '), true, 8000);
      else toast('3 variations ready — pick your favourite');
    } catch (err) {
      toast(err.message, true, 10000);
    } finally {
      delete S.busy[key];
      if (S.view === key) { renderGenerate($('#sec-generate'), key); renderTabs(); }
    }
  };

  const gallery = $('#gen-gallery', el);
  const gens = [...day.generations].reverse();
  if (!gens.length) {
    gallery.innerHTML = `<div style="color:var(--ink-faint);font-size:13px">Nothing generated yet for this day.</div>`;
    return;
  }
  gens.forEach((gen, gi) => {
    const wrap = document.createElement('div');
    wrap.style.marginBottom = '18px';
    if (gi > 0) {
      wrap.innerHTML = `<div class="gen-history">older generation · ${new Date(gen.createdAt).toLocaleString()}</div>`;
    }
    const grid = document.createElement('div');
    grid.className = 'variants';
    if (gi > 0) grid.style.opacity = '0.7';
    for (const v of gen.variants) {
      const card = document.createElement('div');
      const isWinner = day.winner === v.file;
      card.className = 'variant' + (isWinner ? ' winner' : '');
      card.innerHTML = `
        ${isWinner ? '<div class="crown">★ CHOSEN</div>' : ''}
        <img src="/files/${v.file}" alt="">
        <div class="v-foot">
          <span class="v-label">${esc(v.label)}</span>
          <button class="${isWinner ? '' : 'primary'}">${isWinner ? 'un-pick' : 'Pick this one'}</button>
        </div>`;
      $('img', card).onclick = () => openLightbox(`/files/${v.file}`, v.file, key);
      $('button', card).onclick = async () => {
        const winner = isWinner ? '' : v.file;
        day.winner = winner;
        await api('PATCH', `/api/week/${S.activeWeek}/day/${key}`, { winner });
        renderGenerate(el, key);
        renderTabs();
      };
      grid.appendChild(card);
    }
    wrap.appendChild(grid);
    gallery.appendChild(wrap);
  });
}

// ----- step 5: captions -----
function renderCaption(el, key) {
  const day = S.week.days[key];
  const voiceHint = S.voice.hasProfile
    ? `writing in your voice (${S.voice.examplesCount} past captions learned)`
    : `⚠ no voice profile yet — click “🎙 Voice” up top and paste past captions so these sound like you`;
  el.innerHTML = `
    <div class="section-head"><span class="step">5</span><h3>Captions</h3><span class="hint">${voiceHint}</span></div>
    <div class="gen-bar">
      <button id="btn-captions">📝 Write captions for this day</button>
      <span id="cap-status"></span>
    </div>
    <div class="caption-grid">
      <div class="field"><label>Instagram (incl. hashtags)</label><textarea id="cap-ig">${esc(day.captions.instagram)}</textarea></div>
      <div class="field"><label>Facebook</label><textarea id="cap-fb">${esc(day.captions.facebook)}</textarea></div>
    </div>
  `;
  $('#btn-captions', el).onclick = async (e) => {
    e.target.disabled = true;
    $('#cap-status', el).innerHTML = '<span class="working"><span class="spinner"></span> writing…</span>';
    try {
      const out = await api('POST', `/api/week/${S.activeWeek}/day/${key}/captions`);
      S.week.days[key] = out.day;
      renderCaption(el, key);
      renderTabs();
    } catch (err) {
      toast(err.message, true, 8000);
      e.target.disabled = false;
      $('#cap-status', el).innerHTML = '';
    }
  };
  const save = (field, value) => {
    day.captions[field] = value;
    api('PATCH', `/api/week/${S.activeWeek}/day/${key}`, { captions: { [field]: value } }).catch((e) => toast(e.message, true));
  };
  $('#cap-ig', el).onchange = (e) => save('instagram', e.target.value);
  $('#cap-fb', el).onchange = (e) => save('facebook', e.target.value);
}

// ---------- lightbox ----------
function openLightbox(src, file, dayKey) {
  $('#lightbox-img').src = src;
  const actions = $('#lightbox-actions');
  actions.innerHTML = '';
  if (file && dayKey) {
    const b = document.createElement('button');
    b.className = 'primary';
    b.textContent = '★ Pick this poster';
    b.onclick = async () => {
      S.week.days[dayKey].winner = file;
      await api('PATCH', `/api/week/${S.activeWeek}/day/${dayKey}`, { winner: file });
      closeLightbox();
      renderAll();
    };
    actions.appendChild(b);
  }
  $('#lightbox').classList.remove('hidden');
}
function closeLightbox() { $('#lightbox').classList.add('hidden'); }
$('#lightbox').onclick = (e) => { if (e.target.id === 'lightbox' || e.target.id === 'lightbox-img') closeLightbox(); };
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') { closeLightbox(); closeModal('settings-modal'); closeModal('voice-modal'); } });

// ---------- modals ----------
function openModal(id) { $('#' + id).classList.remove('hidden'); }
function closeModal(id) { $('#' + id).classList.add('hidden'); }
$$('[data-close]').forEach((b) => (b.onclick = () => closeModal(b.dataset.close)));

// ---------- settings ----------
$('#btn-settings').onclick = () => { renderSettings(); openModal('settings-modal'); };

function renderSettings() {
  const s = S.settings;
  const body = $('#settings-body');
  body.innerHTML = `
    <div class="settings-note">Keys are stored only on this computer (in the app's <b>data/</b> folder). Nothing runs on a server.</div>
    <div class="grid2">
      <div class="field"><label>OpenAI API key</label><input id="st-openai" type="password" placeholder="sk-…" value="${esc(s.openaiApiKey)}"></div>
      <div class="field"><label>Scheduling service</label>
        <select id="st-scheduler">
          <option value="buffer" ${s.scheduler !== 'postiz' ? 'selected' : ''}>Buffer (free plan: 3 channels)</option>
          <option value="postiz" ${s.scheduler === 'postiz' ? 'selected' : ''}>Postiz</option>
        </select></div>
    </div>
    <div class="grid3">
      <div class="field"><label>Poster quality</label>
        <select id="st-quality">
          ${['high', 'medium', 'low'].map((q) => `<option ${s.imageQuality === q ? 'selected' : ''}>${q}</option>`).join('')}
        </select></div>
      <div class="field"><label>Caption model</label><input id="st-capmodel" value="${esc(s.captionModel)}"></div>
      <div class="field"><label>Default post time</label><input id="st-posttime" type="time" value="${esc(s.defaultPostTime)}"></div>
    </div>
    <div class="grid2">
      <div class="field"><label>Venue name</label><input id="st-venue" value="${esc(s.venueName)}"></div>
      <div class="field"><label>Venue one-liner (for captions)</label><input id="st-blurb" value="${esc(s.venueBlurb)}"></div>
    </div>

    <hr class="settings-sep">
    <h3 style="margin:0 0 4px">Brand logo</h3>
    <div class="settings-note">Upload your circular V logo (PNG with transparency is best). It is attached to every generation so the badge comes out exact.</div>
    <div style="display:flex;gap:14px;align-items:center">
      ${S.brand.logoFile ? `<img src="/files/${S.brand.logoFile}" style="width:64px;height:64px;object-fit:contain;border-radius:10px;background:#000">` : '<span style="color:var(--ink-faint)">no logo uploaded</span>'}
      <button id="st-logo">Upload logo</button>
      ${S.brand.logoFile ? '<button id="st-logo-rm" class="danger">remove</button>' : ''}
    </div>

    <hr class="settings-sep">
    <h3 style="margin:0 0 4px">Scheduling & channels</h3>

    <div id="st-buffer-block">
      <div class="settings-note">
        <b>Buffer setup (free):</b> create an account at <a href="https://buffer.com" target="_blank">buffer.com</a>,
        connect your Instagram (must be a professional/business account) and your Facebook page —
        the free plan includes 3 channels. Then generate an API key under
        <b>Buffer → Settings → API</b> and paste it here.
      </div>
      <div class="field"><label>Buffer API key</label><input id="st-buffer" type="password" placeholder="Buffer → Settings → API" value="${esc(s.bufferApiKey)}"></div>
      <div class="settings-note">
        <b>Image hosting (free, required for Buffer):</b> Buffer downloads the poster from a URL,
        so the app publishes it via a free <a href="https://cloudinary.com" target="_blank">Cloudinary</a> account:
        Settings → Upload → Upload presets → Add preset → Signing mode "Unsigned". Paste your
        cloud name and preset name below.
      </div>
      <div class="grid2">
        <div class="field"><label>Cloudinary cloud name</label><input id="st-cld-name" value="${esc(s.cloudinaryCloudName)}"></div>
        <div class="field"><label>Cloudinary upload preset</label><input id="st-cld-preset" value="${esc(s.cloudinaryUploadPreset)}"></div>
      </div>
    </div>

    <div id="st-postiz-block">
      <div class="settings-note">
        <b>Postiz setup:</b> connect Instagram & your Facebook page inside
        <a href="https://platform.postiz.com" target="_blank">Postiz</a> (self-hosted works too — set the base URL),
        then create an API key under Settings → Public API.
      </div>
      <div class="grid2">
        <div class="field"><label>Postiz API key</label><input id="st-postiz" type="password" placeholder="Postiz → Settings → Public API" value="${esc(s.postizApiKey)}"></div>
        <div class="field"><label>Postiz API base URL</label><input id="st-postiz-url" placeholder="https://api.postiz.com/public/v1" value="${esc(s.postizBaseUrl)}"></div>
      </div>
    </div>

    <button id="st-load-accts">Load my channels</button>
    <div id="st-accts"></div>
    <input type="hidden" id="st-ig-ident" value="${esc(s.instagramIdentifier)}">
    <input type="hidden" id="st-fb-ident" value="${esc(s.facebookIdentifier)}">
    <div class="grid2" style="margin-top:14px">
      <div class="field"><label>Instagram channel ID</label><input id="st-ig" value="${esc(s.instagramIntegrationId)}"></div>
      <div class="field"><label>Facebook channel ID</label><input id="st-fb" value="${esc(s.facebookIntegrationId)}"></div>
    </div>

    <hr class="settings-sep">
    <h3 style="margin:0 0 4px">Post time per day</h3>
    <div class="grid3" id="st-day-times">
      ${DAY_KEYS.map((k) => `
        <div class="field"><label>${DAY_LABEL[k]}</label>
          <input type="time" data-day="${k}" value="${esc(s.postTimes[k] || '')}" placeholder="${esc(s.defaultPostTime)}"></div>`).join('')}
    </div>

    <div style="display:flex;justify-content:flex-end;margin-top:18px">
      <button class="primary" id="st-save">Save settings</button>
    </div>
  `;

  $('#st-logo', body).onclick = async () => {
    const [f] = await pickFiles({ multiple: false });
    if (!f) return;
    const dataUrl = await readFileAsDataUrl(f);
    const out = await api('POST', '/api/brand/logo', { dataUrl });
    S.brand = out.brand;
    renderSettings();
  };
  const rm = $('#st-logo-rm', body);
  if (rm) rm.onclick = async () => {
    const out = await api('POST', '/api/brand/logo', { dataUrl: '' });
    S.brand = out.brand;
    renderSettings();
  };

  // Show only the selected scheduler's config block.
  const syncSchedulerBlocks = () => {
    const isBuffer = $('#st-scheduler', body).value === 'buffer';
    $('#st-buffer-block', body).style.display = isBuffer ? '' : 'none';
    $('#st-postiz-block', body).style.display = isBuffer ? 'none' : '';
  };
  $('#st-scheduler', body).onchange = syncSchedulerBlocks;
  syncSchedulerBlocks();

  $('#st-load-accts', body).onclick = async (e) => {
    e.target.disabled = true;
    e.target.textContent = 'Loading…';
    const box = $('#st-accts', body);
    try {
      // Save the API keys first so the server can use them.
      await saveSettings();
      const out = await api('GET', '/api/channels');
      const channels = Array.isArray(out.channels) ? out.channels : [];
      if (!channels.length) {
        box.innerHTML = `<div class="acct-list">No channels found — connect Instagram & your Facebook page in your scheduling service first.</div>`;
      } else {
        box.innerHTML = `<div class="acct-list">${channels.map((c) => `
          <div style="display:flex;align-items:center;gap:10px;margin:4px 0">
            <b>${esc(c.identifier || '?')}</b> ${esc(c.name || '')} <span style="color:var(--ink-faint)">· ${esc(c.id)}</span>
            <button data-use="ig" data-id="${esc(c.id)}" data-ident="${esc(c.identifier || '')}" style="padding:3px 10px;font-size:11.5px">→ Instagram</button>
            <button data-use="fb" data-id="${esc(c.id)}" data-ident="${esc(c.identifier || '')}" style="padding:3px 10px;font-size:11.5px">→ Facebook</button>
          </div>`).join('')}</div>`;
        $$('button[data-use]', box).forEach((b) => (b.onclick = () => {
          if (b.dataset.use === 'ig') {
            $('#st-ig', body).value = b.dataset.id;
            $('#st-ig-ident', body).value = b.dataset.ident || 'instagram';
          } else {
            $('#st-fb', body).value = b.dataset.id;
            $('#st-fb-ident', body).value = b.dataset.ident || 'facebook';
          }
          toast('Channel set — remember to Save settings');
        }));
      }
    } catch (err) {
      box.innerHTML = `<div class="acct-list" style="color:var(--danger)">${esc(err.message)}</div>`;
    } finally {
      e.target.disabled = false;
      e.target.textContent = 'Load my channels';
    }
  };

  async function saveSettings() {
    const postTimes = {};
    $$('#st-day-times input', body).forEach((i) => { if (i.value) postTimes[i.dataset.day] = i.value; });
    const out = await api('PUT', '/api/settings', {
      settings: {
        openaiApiKey: $('#st-openai', body).value.trim(),
        scheduler: $('#st-scheduler', body).value,
        bufferApiKey: $('#st-buffer', body).value.trim(),
        cloudinaryCloudName: $('#st-cld-name', body).value.trim(),
        cloudinaryUploadPreset: $('#st-cld-preset', body).value.trim(),
        postizApiKey: $('#st-postiz', body).value.trim(),
        postizBaseUrl: $('#st-postiz-url', body).value.trim() || 'https://api.postiz.com/public/v1',
        imageQuality: $('#st-quality', body).value,
        captionModel: $('#st-capmodel', body).value.trim() || 'gpt-4.1',
        defaultPostTime: $('#st-posttime', body).value || '17:00',
        venueName: $('#st-venue', body).value.trim() || 'Vibration',
        venueBlurb: $('#st-blurb', body).value,
        instagramIntegrationId: $('#st-ig', body).value.trim(),
        instagramIdentifier: $('#st-ig-ident', body).value.trim() || 'instagram',
        facebookIntegrationId: $('#st-fb', body).value.trim(),
        facebookIdentifier: $('#st-fb-ident', body).value.trim() || 'facebook',
        postTimes,
      },
    });
    S.settings = out.settings;
  }

  $('#st-save', body).onclick = async () => {
    try {
      await saveSettings();
      toast('Settings saved');
      closeModal('settings-modal');
      renderMain();
    } catch (err) {
      toast(err.message, true);
    }
  };
}

// ---------- voice ----------
$('#btn-voice').onclick = () => { renderVoice(); openModal('voice-modal'); };

function renderVoice() {
  const body = $('#voice-body');
  const profile = S.voice.profile;
  body.innerHTML = `
    <div class="settings-note">
      Paste your past Instagram/Facebook captions below (the ones that sound like you) —
      separate captions with a line containing <b>---</b>. The app learns your tone, structure,
      emoji & hashtag habits and reuses them for every new caption.
    </div>
    <div class="field"><textarea id="voice-input" style="min-height:220px" placeholder="🔥 This Saturday… &#10;---&#10;Next caption…"></textarea></div>
    <div style="display:flex;gap:12px;align-items:center">
      <button class="primary" id="voice-analyze">Learn my voice</button>
      <span id="voice-status">${S.voice.hasProfile ? `✓ profile learned from ${S.voice.examplesCount} captions` : 'no profile yet'}</span>
    </div>
    ${profile ? `<div class="acct-list" style="margin-top:16px">
      <b>Tone:</b> ${esc(profile.tone || '')}<br>
      <b>Structure:</b> ${esc(profile.structure || '')}<br>
      <b>Emoji:</b> ${esc(profile.emojiUsage || '')}<br>
      <b>Hashtags:</b> ${esc(profile.hashtagStyle || '')}<br>
      <b>CTA:</b> ${esc(profile.callToAction || '')}
    </div>` : ''}
  `;
  $('#voice-analyze', body).onclick = async (e) => {
    const captions = $('#voice-input', body).value;
    if (!captions.trim()) return toast('Paste some captions first', true);
    e.target.disabled = true;
    $('#voice-status', body).innerHTML = '<span class="working"><span class="spinner"></span> analyzing…</span>';
    try {
      const out = await api('POST', '/api/voice/analyze', { captions });
      S.voice = out.voice;
      renderVoice();
      toast('Voice learned — captions will now sound like you');
    } catch (err) {
      toast(err.message, true, 8000);
      e.target.disabled = false;
      $('#voice-status', body).textContent = 'failed';
    }
  };
}

// ---------- onboarding wizard ----------
const OB = { step: 0 };
$('#btn-onboarding').onclick = () => { OB.step = 0; renderOnboarding(); openModal('onboarding-modal'); };

async function obSave(fields) {
  const out = await api('PUT', '/api/settings', { settings: fields });
  S.settings = out.settings;
}

function obShell(inner, { title, sub, showBack = true, nextLabel = 'Next →', onNext, hero } = {}) {
  const body = $('#onboarding-body');
  const total = 7;
  body.innerHTML = `
    <div class="ob-dots">${Array.from({ length: total }, (_, i) =>
      `<span class="ob-dot ${i === OB.step ? 'active' : i < OB.step ? 'done' : ''}"></span>`).join('')}</div>
    <div class="ob-step">
      ${hero ? '<div class="ob-hero">V</div>' : ''}
      <h2>${title}</h2>
      ${sub ? `<div class="ob-sub">${sub}</div>` : ''}
      <div id="ob-inner">${inner}</div>
      <div class="ob-nav">
        ${showBack ? '<button class="ghost" id="ob-back">← Back</button>' : '<span></span>'}
        <span class="spacer"></span>
        <button class="ob-skip" id="ob-skip">skip setup for now</button>
        <button class="primary" id="ob-next" style="margin-left:14px">${nextLabel}</button>
      </div>
    </div>`;
  const back = $('#ob-back', body);
  if (back) back.onclick = () => { OB.step = Math.max(0, OB.step - 1); renderOnboarding(); };
  $('#ob-skip', body).onclick = async () => {
    await obSave({ onboarded: true }).catch(() => {});
    closeModal('onboarding-modal');
    toast('You can reopen the guide anytime with 🧭 Setup');
  };
  $('#ob-next', body).onclick = async (e) => {
    e.target.disabled = true;
    try {
      if (onNext) await onNext(body);
      OB.step += 1;
      renderOnboarding();
    } catch (err) {
      toast(err.message, true, 8000);
      e.target.disabled = false;
    }
  };
  return body;
}

function obField(id, label, value, placeholder, type = 'text') {
  return `<div class="field" style="margin-bottom:12px"><label>${label}</label>
    <input id="${id}" type="${type}" value="${esc(value || '')}" placeholder="${esc(placeholder || '')}"></div>`;
}

function renderOnboarding() {
  const s = S.settings;
  switch (OB.step) {
    case 0:
      obShell(
        `<ul class="ob-list">
          <li><span class="n">1</span><span>Every week you design 5 posters (Tue–Sat): upload the performer's photo, pick a style, type the details — the app generates 3 designer-grade variations and you pick the winner.</span></li>
          <li><span class="n">2</span><span>Captions are written in <b>your</b> voice, learned from your past posts.</span></li>
          <li><span class="n">3</span><span>One click schedules the whole week to Instagram + Facebook.</span></li>
        </ul>
        <div class="settings-note">You'll need about 30 minutes and these free accounts: OpenAI (~$4/week of image credit), Buffer, Cloudinary. The guide walks you through each. The full manual lives in <b>SETUP.md</b> in the app folder.</div>`,
        { title: 'Welcome to your Poster Studio', sub: 'a 6-step setup, done once', showBack: false, nextLabel: "Let's set up →", hero: true }
      );
      break;

    case 1:
      obShell(
        `<ul class="ob-list">
          <li><span class="n">1</span><span>Sign up / log in at <a href="https://platform.openai.com" target="_blank">platform.openai.com</a></span></li>
          <li><span class="n">2</span><span><b>Billing:</b> Settings → Billing → add ~$10 credit (a week of posters ≈ $4).</span></li>
          <li><span class="n">3</span><span><b>Verify organization:</b> Settings → Organization → Verification. Required for the image model — without it, generation fails.</span></li>
          <li><span class="n">4</span><span><a href="https://platform.openai.com/api-keys" target="_blank">Create an API key</a> and paste it below.</span></li>
        </ul>` + obField('ob-openai', 'OpenAI API key', s.openaiApiKey, 'sk-…', 'password'),
        {
          title: 'Step 1 · OpenAI', sub: 'this generates the posters',
          onNext: async (b) => obSave({ openaiApiKey: $('#ob-openai', b).value.trim() }),
        }
      );
      break;

    case 2:
      obShell(
        `<ul class="ob-list">
          <li><span class="n">1</span><span><b>Facebook Page:</b> the bar needs a Page (not just a profile). Create one on Facebook → Menu → Pages if needed.</span></li>
          <li><span class="n">2</span><span><b>Instagram professional:</b> Instagram app → profile → ≡ → Settings → Account type and tools → <b>Switch to professional account</b> → Business (free).</span></li>
          <li><span class="n">3</span><span><b>Link them:</b> Instagram → Edit profile → Page → connect your Facebook Page.</span></li>
        </ul>
        <div class="settings-note">Automatic posting only works with a professional Instagram linked to a Facebook Page — this is a Meta rule, not the app's.</div>`,
        { title: 'Step 2 · Instagram & Facebook', sub: 'prepare the accounts (free)' }
      );
      break;

    case 3:
      obShell(
        `<ul class="ob-list">
          <li><span class="n">1</span><span>Sign up at <a href="https://buffer.com" target="_blank">buffer.com</a> — the free plan includes 3 channels (you need 2).</span></li>
          <li><span class="n">2</span><span><b>Channels → Connect channel:</b> connect your Instagram and your Facebook Page.</span></li>
          <li><span class="n">3</span><span>Avatar (top right) → <b>Settings → API</b> → Generate API key → paste below.</span></li>
        </ul>` + obField('ob-buffer', 'Buffer API key', s.bufferApiKey, 'from Buffer → Settings → API', 'password'),
        {
          title: 'Step 3 · Buffer', sub: 'this does the actual posting — free',
          onNext: async (b) => obSave({ scheduler: 'buffer', bufferApiKey: $('#ob-buffer', b).value.trim() }),
        }
      );
      break;

    case 4:
      obShell(
        `<ul class="ob-list">
          <li><span class="n">1</span><span>Sign up free at <a href="https://cloudinary.com" target="_blank">cloudinary.com</a> (no card).</span></li>
          <li><span class="n">2</span><span>Your <b>cloud name</b> is on the dashboard (short word like <code>dq2abcxyz</code>).</span></li>
          <li><span class="n">3</span><span>Gear icon → <b>Upload</b> tab → Upload presets → <b>Add upload preset</b> → Signing mode <b>Unsigned</b> → Save. Note the preset name.</span></li>
        </ul>` +
        obField('ob-cld-name', 'Cloudinary cloud name', s.cloudinaryCloudName, 'e.g. dq2abcxyz') +
        obField('ob-cld-preset', 'Cloudinary upload preset', s.cloudinaryUploadPreset, 'e.g. ml_default'),
        {
          title: 'Step 4 · Cloudinary', sub: 'free image hosting Buffer needs to fetch your posters',
          onNext: async (b) => obSave({
            cloudinaryCloudName: $('#ob-cld-name', b).value.trim(),
            cloudinaryUploadPreset: $('#ob-cld-preset', b).value.trim(),
          }),
        }
      );
      break;

    case 5: {
      const body = obShell(
        `<div class="settings-note">Click the button — your Buffer channels appear. Then press "→ Instagram" next to your Instagram and "→ Facebook" next to your Page.</div>
        <button id="ob-load">Load my channels</button>
        <div id="ob-channels"></div>
        <div class="ob-check" id="ob-assigned"></div>`,
        { title: 'Step 5 · Pick your channels', sub: 'tell the app where to post' }
      );
      const refreshAssigned = () => {
        const a = [];
        if (S.settings.instagramIntegrationId) a.push('✓ Instagram set');
        if (S.settings.facebookIntegrationId) a.push('✓ Facebook set');
        $('#ob-assigned', body).textContent = a.join('   ');
      };
      refreshAssigned();
      $('#ob-load', body).onclick = async (e) => {
        e.target.disabled = true; e.target.textContent = 'Loading…';
        try {
          const out = await api('GET', '/api/channels');
          const channels = out.channels || [];
          $('#ob-channels', body).innerHTML = `<div class="acct-list">${channels.map((c) => `
            <div style="display:flex;align-items:center;gap:10px;margin:4px 0">
              <b>${esc(c.identifier || '?')}</b> ${esc(c.name || '')}
              <button data-ch="ig" data-id="${esc(c.id)}" data-ident="${esc(c.identifier || '')}" style="padding:3px 10px;font-size:11.5px">→ Instagram</button>
              <button data-ch="fb" data-id="${esc(c.id)}" data-ident="${esc(c.identifier || '')}" style="padding:3px 10px;font-size:11.5px">→ Facebook</button>
            </div>`).join('') || 'No channels found — connect them in Buffer first.'}</div>`;
          $$('button[data-ch]', body).forEach((btn) => (btn.onclick = async () => {
            const f = btn.dataset.ch === 'ig'
              ? { instagramIntegrationId: btn.dataset.id, instagramIdentifier: btn.dataset.ident || 'instagram' }
              : { facebookIntegrationId: btn.dataset.id, facebookIdentifier: btn.dataset.ident || 'facebook' };
            await obSave(f);
            refreshAssigned();
            toast('Channel set');
          }));
        } catch (err) {
          $('#ob-channels', body).innerHTML = `<div class="acct-list" style="color:var(--danger)">${esc(err.message)}</div>`;
        } finally {
          e.target.disabled = false; e.target.textContent = 'Load my channels';
        }
      };
      break;
    }

    case 6: {
      const body = obShell(
        `<div class="settings-note"><b>Logo:</b> upload your circular V logo (transparent PNG is best) — it's attached to every generation so the badge comes out exact.</div>
        <div style="display:flex;gap:12px;align-items:center;margin-bottom:16px">
          <button id="ob-logo">Upload logo</button><span id="ob-logo-status" class="ob-check">${S.brand.logoFile ? '✓ logo uploaded' : ''}</span>
        </div>
        <div class="settings-note"><b>Your caption voice:</b> paste 5–15 past captions below, separated by a line with just <b>---</b>, and press Learn.</div>
        <div class="field"><textarea id="ob-voice" style="min-height:120px" placeholder="🔥 This Saturday…&#10;---&#10;Next caption…"></textarea></div>
        <div style="display:flex;gap:12px;align-items:center">
          <button id="ob-learn">Learn my voice</button>
          <span id="ob-voice-status" class="ob-check">${S.voice.hasProfile ? `✓ learned from ${S.voice.examplesCount} captions` : ''}</span>
        </div>`,
        {
          title: 'Step 6 · Brand & voice', sub: 'make it unmistakably Vibration',
          nextLabel: 'Finish ✓',
          onNext: async () => {
            await obSave({ onboarded: true });
            closeModal('onboarding-modal');
            toast('Setup complete — pick a day and start designing!');
            renderAll();
          },
        }
      );
      $('#ob-logo', body).onclick = async () => {
        const [f] = await pickFiles({ multiple: false });
        if (!f) return;
        const out = await api('POST', '/api/brand/logo', { dataUrl: await readFileAsDataUrl(f) });
        S.brand = out.brand;
        $('#ob-logo-status', body).textContent = '✓ logo uploaded';
      };
      $('#ob-learn', body).onclick = async (e) => {
        const captions = $('#ob-voice', body).value;
        if (!captions.trim()) return toast('Paste some captions first', true);
        e.target.disabled = true; e.target.textContent = 'Analyzing…';
        try {
          const out = await api('POST', '/api/voice/analyze', { captions });
          S.voice = out.voice;
          $('#ob-voice-status', body).textContent = `✓ learned from ${out.voice.examplesCount} captions`;
        } catch (err) {
          toast(err.message, true, 8000);
        } finally {
          e.target.disabled = false; e.target.textContent = 'Learn my voice';
        }
      };
      break;
    }

    default: {
      obSave({ onboarded: true }).catch(() => {});
      closeModal('onboarding-modal');
    }
  }
}

// ---------- go ----------
boot()
  .then(() => {
    if (!S.settings.onboarded) {
      OB.step = 0;
      renderOnboarding();
      openModal('onboarding-modal');
    }
  })
  .catch((e) => toast('Could not start: ' + e.message, true, 10000));
