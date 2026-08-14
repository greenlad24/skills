const loginView = document.getElementById('login-view');
const editorView = document.getElementById('editor-view');
const loginForm = document.getElementById('login-form');
const loginError = document.getElementById('login-error');
const screenEl = document.getElementById('screen');
const navBack = document.getElementById('nav-back');
const navTitle = document.getElementById('nav-title');
const saveBtn = document.getElementById('save');
const saveStatus = document.getElementById('save-status');
const toastEl = document.getElementById('toast');
const fileInput = document.getElementById('file-input');

let menu = null;
let baseUpdatedAt = null;
let dirty = false;

/** Navigation mirrors the app: a stack of screens rather than nested accordions. */
let stack = [{ view: 'home' }];
const here = () => stack[stack.length - 1];
const go = (screen) => { stack.push(screen); render(); };
const back = () => { if (stack.length > 1) { stack.pop(); render(); } };

/* Menu items are text-only by design; Live Shows is fully editable. */
const MENU_FIELDS = {
  item: [
    ['eyebrow', 'Eyebrow', 'input'],
    ['name', 'Name', 'input'],
    ['story', 'Story', 'textarea'],
    ['build', 'Build', 'input', 'Separate with " / " — shown as gold dots.'],
    ['serve', 'Serve', 'input'],
  ],
  back: [
    ['kicker', 'Kicker', 'input'],
    ['quote', 'Quote', 'textarea'],
    ['attrib', 'Attribution', 'input'],
    ['fine', 'Fine print', 'textarea'],
  ],
  list: [
    ['eyebrow', 'Eyebrow', 'input'],
    ['title', 'Title', 'input'],
  ],
};

function api(path, options = {}) {
  const headers = { 'X-Requested-With': 'vibration-admin', ...options.headers };
  if (!(options.body instanceof FormData)) headers['Content-Type'] = 'application/json';
  return fetch(path, { ...options, headers });
}

let toastTimer;
function toast(message, isError = false) {
  toastEl.textContent = message;
  toastEl.className = isError ? 'toast error' : 'toast';
  toastEl.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toastEl.hidden = true; }, isError ? 6000 : 2600);
}

function setDirty(value) {
  dirty = value;
  saveBtn.disabled = !value;
  saveStatus.textContent = value ? 'Unsaved changes' : 'All changes saved';
  saveStatus.className = value ? 'save-status dirty' : 'save-status';
}

window.addEventListener('beforeunload', (event) => { if (dirty) event.preventDefault(); });

const newId = () => (crypto.randomUUID?.() ?? String(Math.random()).slice(2)).slice(0, 8);

/** Today in Koh Samui, so "past" matches what the public page hides. */
const todayISO = () => new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Bangkok', year: 'numeric', month: '2-digit', day: '2-digit',
}).format(new Date());

function prettyDate(on) {
  if (!on) return 'No date';
  const [y, m, d] = on.split('-');
  const dt = new Date(Date.UTC(+y, +m - 1, +d));
  return dt.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC' });
}

/* ---------------- building blocks ---------------- */

function field(label, value, kind, onInput, hint) {
  const wrap = document.createElement('label');
  wrap.className = 'field';
  wrap.append(Object.assign(document.createElement('span'), { className: 'field-label', textContent: label }));
  const input = document.createElement(kind === 'textarea' ? 'textarea' : 'input');
  if (kind === 'textarea') input.rows = 3; else input.type = 'text';
  input.value = value ?? '';
  input.addEventListener('input', () => { onInput(input.value); setDirty(true); });
  wrap.append(input);
  if (hint) wrap.append(Object.assign(document.createElement('p'), { className: 'hint', textContent: hint }));
  return wrap;
}

function dateField(label, value, onInput, hint) {
  const wrap = document.createElement('label');
  wrap.className = 'field';
  wrap.append(Object.assign(document.createElement('span'), { className: 'field-label', textContent: label }));
  const input = document.createElement('input');
  input.type = 'date';
  input.value = value || '';
  input.addEventListener('input', () => { onInput(input.value); setDirty(true); });
  wrap.append(input);
  if (hint) wrap.append(Object.assign(document.createElement('p'), { className: 'hint', textContent: hint }));
  return wrap;
}

/** A tappable row that drills into another screen — the app's card, at list scale. */
function navRow(title, meta, onClick, thumb) {
  const row = document.createElement('button');
  row.type = 'button';
  row.className = 'navrow';
  if (thumb) {
    const img = document.createElement('img');
    img.src = thumb; img.alt = ''; img.loading = 'lazy';
    row.append(img);
  }
  const t = document.createElement('span');
  t.className = 'navrow-t';
  t.append(Object.assign(document.createElement('span'), { className: 'serif', textContent: title || 'Untitled' }));
  if (meta) t.append(Object.assign(document.createElement('span'), { className: 'navrow-m', textContent: meta }));
  row.append(t);
  row.append(Object.assign(document.createElement('span'), { className: 'chev', innerHTML: '&#10095;' }));
  row.addEventListener('click', onClick);
  return row;
}

function sectionHead(text) {
  return Object.assign(document.createElement('div'), { className: 'shead', textContent: text });
}

function button(label, onClick, cls = 'btn btn-block btn-dashed') {
  const b = document.createElement('button');
  b.type = 'button'; b.className = cls; b.textContent = label;
  b.addEventListener('click', onClick);
  return b;
}

/** Image picker: uploads immediately, then stores the returned URL on the record. */
function imageField(label, current, onChange, hint) {
  const wrap = document.createElement('div');
  wrap.className = 'field';
  wrap.append(Object.assign(document.createElement('span'), { className: 'field-label', textContent: label }));

  const box = document.createElement('div');
  box.className = 'imgpick';

  const preview = document.createElement('div');
  preview.className = 'imgprev';
  const paint = (url) => {
    preview.replaceChildren();
    if (url) {
      const img = document.createElement('img');
      img.src = url; img.alt = '';
      preview.append(img);
    } else {
      preview.append(Object.assign(document.createElement('span'), { textContent: 'None' }));
    }
  };
  paint(current);

  const actions = document.createElement('div');
  actions.className = 'imgacts';

  const choose = button(current ? 'Replace' : 'Upload', () => {
    fileInput.value = '';
    fileInput.onchange = async () => {
      const file = fileInput.files && fileInput.files[0];
      if (!file) return;
      choose.disabled = true; choose.textContent = 'Uploading…';
      try {
        const body = new FormData();
        body.append('file', file);
        const res = await api('/api/admin/upload', { method: 'POST', body });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.error || 'Upload failed');
        onChange(data.url);
        paint(data.url);
        choose.textContent = 'Replace';
        remove.hidden = false;
        setDirty(true);
        toast('Image uploaded — remember to Save');
      } catch (err) {
        toast(err.message || 'Upload failed', true);
        choose.textContent = current ? 'Replace' : 'Upload';
      } finally {
        choose.disabled = false;
      }
    };
    fileInput.click();
  }, 'btn');

  const remove = button('Remove', () => {
    onChange('');
    paint('');
    choose.textContent = 'Upload';
    remove.hidden = true;
    setDirty(true);
  }, 'btn btn-quiet');
  remove.hidden = !current;

  actions.append(choose, remove);
  box.append(preview, actions);
  wrap.append(box);
  if (hint) wrap.append(Object.assign(document.createElement('p'), { className: 'hint', textContent: hint }));
  return wrap;
}

function moveControls(list, index, onChanged) {
  const row = document.createElement('div');
  row.className = 'rowtools';
  const mk = (label, delta) => {
    const b = document.createElement('button');
    b.type = 'button'; b.className = 'icon-btn'; b.textContent = label;
    b.disabled = delta < 0 ? index === 0 : index === list.length - 1;
    b.addEventListener('click', () => {
      const t = index + delta;
      [list[index], list[t]] = [list[t], list[index]];
      setDirty(true); onChanged();
    });
    return b;
  };
  const del = document.createElement('button');
  del.type = 'button'; del.className = 'icon-btn danger'; del.textContent = '✕';
  del.addEventListener('click', () => {
    if (!confirm('Delete this?')) return;
    list.splice(index, 1);
    setDirty(true); onChanged();
  });
  row.append(mk('↑', -1), mk('↓', 1), del);
  return row;
}


/**
 * Show/hide switch for anything on the menu — a section, a page, or a single
 * line on a list. Hidden things stay in the editor and simply stop being
 * published, so "we're out of the snapper tonight" is one tap, and so is
 * putting it back.
 */
function visibilityToggle(read, write, onChanged, labels = {}) {
  const {
    on = 'Hidden', off = 'Shown',
    // Which of the two states is the quiet one — hidden is, weekly is not.
    mutedWhen = true,
    titles = { on: 'Hidden from the menu — tap to show it', off: 'On the menu — tap to hide it' },
  } = labels;

  const b = document.createElement('button');
  b.type = 'button';
  const paint = () => {
    const state = read() === true;
    b.className = state === mutedWhen ? 'pill off' : 'pill';
    b.textContent = state ? on : off;
    b.setAttribute('aria-pressed', String(state));
    b.title = state ? titles.on : titles.off;
  };
  paint();
  b.addEventListener('click', (event) => {
    event.stopPropagation();
    write(read() !== true);
    setDirty(true);
    paint();
    if (onChanged) onChanged();
  });
  return b;
}

/** A list row plus its show/hide switch, dimmed while it is hidden. */
function withVisibility(node, read, write, onChanged) {
  const wrap = document.createElement('div');
  wrap.className = read() === true ? 'listitem dim' : 'listitem';
  wrap.append(node, visibilityToggle(read, write, onChanged));
  return wrap;
}

/** Drop zone for a batch of posters: drag a week's worth in, or tap to pick. */
function posterDropZone() {
  const zone = document.createElement('button');
  zone.type = 'button';
  zone.className = 'dropzone';
  zone.append(
    Object.assign(document.createElement('span'), { className: 'dz-mark', textContent: '+' }),
    Object.assign(document.createElement('span'), { className: 'dz-t', textContent: 'Add posters' }),
    Object.assign(document.createElement('span'), {
      className: 'dz-s', textContent: 'Drag them here, or tap to choose',
    }),
  );

  const take = async (files) => {
    if (!files.length) return;
    zone.disabled = true;
    zone.classList.add('over');
    try {
      await addPostersFromFiles(files);
    } finally {
      // render() replaces this element, so only a failed batch lands here.
      zone.disabled = false;
      zone.classList.remove('over');
    }
  };

  zone.addEventListener('click', () => {
    fileInput.value = '';
    fileInput.multiple = true;
    fileInput.onchange = async () => {
      const files = [...(fileInput.files || [])];
      fileInput.multiple = false;
      await take(files);
    };
    fileInput.click();
  });

  // Children are pointer-events:none, so dragleave only fires on a real exit.
  zone.addEventListener('dragenter', (e) => { e.preventDefault(); zone.classList.add('over'); });
  zone.addEventListener('dragover', (e) => {
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
  });
  zone.addEventListener('dragleave', () => { if (!zone.disabled) zone.classList.remove('over'); });
  zone.addEventListener('drop', async (e) => {
    e.preventDefault();
    zone.classList.remove('over');
    if (zone.disabled) return;
    const files = [...(e.dataTransfer?.files || [])]
      .filter((f) => /^image\/(jpeg|png|webp)$/.test(f.type));
    if (!files.length) {
      toast('Drop poster images — JPEG, PNG or WebP', true);
      return;
    }
    await take(files);
  });

  return zone;
}

// A poster dropped anywhere else would otherwise navigate away from the editor,
// losing unsaved edits. The zone's own handler runs first, so this only catches misses.
for (const type of ['dragover', 'drop']) {
  window.addEventListener(type, (e) => e.preventDefault());
}

/**
 * Add a batch of posters in one go: upload each, then ask the model to read the
 * act, date and genre off it. Extraction is best-effort — a poster that cannot
 * be read still becomes an event with its poster attached, ready to fill in.
 */
const wait = (seconds) => new Promise((r) => setTimeout(r, seconds * 1000));

/* ---------------- batch progress ---------------- */

/**
 * A run of posters can take a minute or more — uploads, a model read each, and
 * a rate limit waited out in between. A toast that replaces itself every few
 * seconds cannot carry that, so the batch keeps its own panel: a bar for how
 * far along it is, and a line per poster saying what happened to it.
 *
 * It lives outside the screen it is drawn on, so re-rendering the event list
 * after each poster puts the same element back rather than a fresh empty one.
 */
let batch = null;

function startBatch(total) {
  const el = document.createElement('section');
  el.className = 'batch';

  const head = document.createElement('div');
  head.className = 'batch-head';
  const title = Object.assign(document.createElement('span'), { textContent: 'Adding posters' });
  const count = Object.assign(document.createElement('span'), { className: 'batch-count' });
  head.append(title, count);

  const track = document.createElement('div');
  track.className = 'bar-track';
  const fill = document.createElement('div');
  fill.className = 'bar-fill';
  track.append(fill);
  track.setAttribute('role', 'progressbar');
  track.setAttribute('aria-valuemin', '0');
  track.setAttribute('aria-valuemax', String(total));

  const list = document.createElement('ol');
  list.className = 'batch-log';
  // Announced politely, so a screen reader follows the run without interrupting.
  list.setAttribute('aria-live', 'polite');

  el.append(head, track, list);
  batch = { el, fill, count, list, track, total, done: 0 };
  paintBatch();
  return el;
}

function paintBatch() {
  const { done, total } = batch;
  batch.count.textContent = `${done} of ${total}`;
  batch.fill.style.width = `${total ? (done / total) * 100 : 0}%`;
  batch.track.setAttribute('aria-valuenow', String(done));
  keepBatchInView();
}

/**
 * The drop zone sits below the event list, and that list grows by a row with
 * every poster — so the panel walks down the page as the run goes on. This
 * keeps it where it can be read; `nearest` means it only moves when it has to.
 */
function keepBatchInView() {
  batch?.el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
}

/** Adds a line to the log and hands it back, so it can be updated in place. */
function batchLine(text) {
  const li = document.createElement('li');
  li.className = 'blog work';
  li.textContent = text;
  batch.list.append(li);
  batch.list.scrollTop = batch.list.scrollHeight;
  return li;
}

const setLine = (li, text, kind) => { li.textContent = text; li.className = `blog ${kind}`; };

/** Leaves the log on screen to be read, with a way to put it away. */
function endBatch(summary, bad) {
  batch.el.append(Object.assign(document.createElement('p'), {
    className: bad ? 'batch-done bad' : 'batch-done',
    textContent: summary,
  }));
  batch.el.append(button('Close', () => { batch = null; render(); }));
  render();
  keepBatchInView();
}

/** Reads one uploaded poster, waiting out Groq's free-tier rate limit once. */
async function readPoster(key, onWait) {
  for (let attempt = 0; ; attempt += 1) {
    const res = await api('/api/admin/extract', { method: 'POST', body: JSON.stringify({ key }) });
    const data = await res.json().catch(() => ({}));
    if (res.ok || attempt > 0 || data.reason !== 'rate_limit') return { res, data };

    // The free tier counts tokens per minute, and a poster is a lot of them, so
    // the wait is measured in tens of seconds rather than retried immediately.
    // Groq asks for tens of seconds; waiting less than it asked just fails again.
    const seconds = Math.min(60, Number(data.retryAfter) || 20);
    if (onWait) onWait(seconds);
    await wait(seconds);
  }
}

async function addPostersFromFiles(files) {
  const shows = menu.liveShows;
  const total = files.length;
  let read = 0, failed = 0, weekly = 0, off = false;

  startBatch(total);
  render();

  for (let i = 0; i < total; i += 1) {
    const label = files[i].name.replace(/\.[^.]+$/, '');
    const short = label.length > 28 ? `${label.slice(0, 27)}…` : label;
    const line = batchLine(`${short} — uploading`);
    const event = {
      id: newId(), on: '', name: '', genre: '', poster: '', description: '', repeat: '',
    };

    try {
      const body = new FormData();
      body.append('file', files[i]);
      const up = await api('/api/admin/upload', { method: 'POST', body });
      const upData = await up.json().catch(() => ({}));
      if (!up.ok) throw new Error(upData.error || 'Upload failed');
      event.poster = upData.url;

      setLine(line, `${short} — reading the poster`, 'work');
      const { res, data } = await readPoster(
        upData.url.split('/').pop(),
        (seconds) => setLine(line, `${short} — Groq is busy, waiting ${seconds}s`, 'wait'),
      );

      if (res.ok && data.configured && data.event) {
        Object.assign(event, data.event);
        // A poster naming only a weekday is a weekly night: it keeps its place
        // on the schedule instead of dropping off after the first one.
        if (data.recurring) { event.repeat = 'weekly'; weekly += 1; }
        read += 1;
        const said = [event.name || short, prettyDate(event.on), event.repeat ? 'weekly' : '']
          .filter(Boolean).join(' · ');
        setLine(line, said, 'ok');
      } else if (res.ok && data.configured === false) {
        // No API key on the site — posters still attach, fields stay blank.
        off = true;
        setLine(line, `${short} — added, reading is switched off on this site`, 'warn');
      } else {
        failed += 1;
        setLine(line, `${short} — ${data.error || 'could not be read'}`, 'bad');
      }
    } catch (err) {
      setLine(line, `${short} — ${err.message || 'could not be added'}`, 'bad');
      batch.done += 1;
      paintBatch();
      continue;
    }

    if (!event.name) event.name = label;
    shows.events.push(event);
    batch.done += 1;
    paintBatch();
    setDirty(true);
    render();
  }

  // Blank fields have two very different causes, and saying which saves a hunt:
  // the site has no key at all, or the model could not read that poster.
  if (off) {
    endBatch(`${total} added — reading posters is switched off on this site, `
      + 'so fill the details in by hand', true);
    return;
  }

  const parts = [`${total} poster${total === 1 ? '' : 's'} added`];
  if (read) parts.push(`${read} filled in automatically`);
  if (weekly) parts.push(`${weekly} set to repeat weekly`);
  if (failed) parts.push(`${failed} could not be read`);
  endBatch(`${parts.join(' · ')} — review, then Save`, failed > 0);
}

/* ---------------- screens ---------------- */

function screenHome() {
  navTitle.textContent = 'Editor';
  navBack.hidden = true;
  const f = document.createDocumentFragment();

  const cover = document.createElement('div');
  cover.className = 'listitem';
  cover.append(
    navRow('Cover', 'Tagline and footer', () => go({ view: 'cover' })),
    // The cover is the menu itself, so it has no switch — just the space one takes.
    Object.assign(document.createElement('span'), { className: 'pillspace', ariaHidden: 'true' }),
  );
  f.append(cover);

  const shows = menu.liveShows;
  f.append(withVisibility(
    navRow(shows.title || 'Live Shows',
      `${shows.events.length} events · ${shows.weekly.items.length} weekly`,
      () => go({ view: 'shows' }),
      shows.thumb || (shows.events.find((e) => e.poster) || {}).poster || ''),
    () => shows.hidden, (v) => { shows.hidden = v; }, render,
  ));

  menu.sections.forEach((s, idx) => {
    f.append(withVisibility(
      navRow(s.title, `${s.entries.length} pages`, () => go({ view: 'section', idx }), s.thumb),
      () => s.hidden, (v) => { s.hidden = v; }, render,
    ));
  });
  screenEl.replaceChildren(f);
}

function screenCover() {
  navTitle.textContent = 'Cover';
  navBack.hidden = false;
  const f = document.createDocumentFragment();
  f.append(field('Tagline', menu.brand.tag, 'input', (v) => { menu.brand.tag = v; },
    'Shown under the logo on the cover screen.'));
  f.append(field('Footer', menu.brand.foot, 'input', (v) => { menu.brand.foot = v; }));
  screenEl.replaceChildren(f);
}

function screenSection(idx) {
  const s = menu.sections[idx];
  navTitle.textContent = s.title || 'Section';
  navBack.hidden = false;
  const f = document.createDocumentFragment();
  f.append(field('Section title', s.title, 'input', (v) => { s.title = v; navTitle.textContent = v; }));
  f.append(field('Subtitle', s.sub, 'input', (v) => { s.sub = v; },
    'Shown under the section name on the cover.'));
  f.append(sectionHead('Pages'));
  s.entries.forEach((e, eIdx) => {
    const label = e.name || e.title || (e.type === 'back' ? 'Back cover' : 'Page ' + (eIdx + 1));
    const kind = e.type === 'item' ? 'Item' : e.type === 'back' ? 'Back cover' : 'List page';
    f.append(withVisibility(
      navRow(label, kind, () => go({ view: 'entry', sIdx: idx, eIdx }), e.hero),
      () => e.hidden, (v) => { e.hidden = v; }, render,
    ));
  });
  f.append(Object.assign(document.createElement('p'), {
    className: 'hint',
    textContent: 'Hidden pages stay here but come off the menu — useful when a dish is off.',
  }));
  screenEl.replaceChildren(f);
}

function screenEntry(sIdx, eIdx) {
  const entry = menu.sections[sIdx].entries[eIdx];
  navTitle.textContent = entry.name || entry.title || 'Page';
  navBack.hidden = false;
  const f = document.createDocumentFragment();

  if (entry.hero) {
    const img = document.createElement('img');
    img.className = 'heroprev'; img.src = entry.hero; img.alt = '';
    f.append(img);
  }

  const vis = document.createElement('div');
  vis.className = 'visrow';
  vis.append(
    Object.assign(document.createElement('span'), { textContent: 'On the menu' }),
    visibilityToggle(() => entry.hidden, (v) => { entry.hidden = v; }, () => render()),
  );
  f.append(vis);

  for (const [key, label, kind, hint] of MENU_FIELDS[entry.type] || []) {
    f.append(field(label, entry[key], kind, (v) => {
      entry[key] = v;
      if (key === 'name' || key === 'title') navTitle.textContent = v || 'Untitled';
    }, hint));
  }

  if (entry.type === 'item') {
    if (entry.priceHtml) {
      f.append(field('Price', entry.priceHtml, 'textarea', (v) => { entry.priceHtml = v; },
        'This item shows two prices, so it carries layout markup. Change the numbers and leave the tags alone.'));
    } else {
      f.append(field('Price', entry.price, 'input', (v) => { entry.price = v; },
        'Number only — THB is added automatically.'));
    }
  }

  if (entry.type === 'list') {
    for (const col of ['col1', 'col2']) {
      for (const block of entry[col] || []) {
        f.append(sectionHead(block.cat || 'Category'));
        f.append(field('Category', block.cat, 'input', (v) => { block.cat = v; }));
        for (const row of block.rows || []) {
          const line = document.createElement('div');
          const paintLine = () => { line.className = row[3] === true ? 'lrow dim' : 'lrow'; };
          paintLine();
          const mk = (cls, i, ph) => {
            const input = document.createElement('input');
            input.type = 'text'; input.className = cls; input.value = row[i] ?? '';
            input.placeholder = ph; input.setAttribute('aria-label', ph);
            input.addEventListener('input', () => { row[i] = input.value; setDirty(true); });
            return input;
          };
          line.append(mk('nm', 0, 'Name'), mk('pr', 1, 'Price'), mk('sz', 2, 'Size'));
          // Each line on a list is a menu item in its own right, so it hides on its own.
          line.append(visibilityToggle(() => row[3], (v) => { row[3] = v; }, paintLine));
          f.append(line);
        }
      }
    }
  }
  screenEl.replaceChildren(f);
}

function screenShows() {
  const s = menu.liveShows;
  navTitle.textContent = s.title || 'Live Shows';
  navBack.hidden = false;
  const f = document.createDocumentFragment();

  f.append(field('Section name', s.title, 'input', (v) => { s.title = v; navTitle.textContent = v; },
    'The card on the home screen.'));
  f.append(field('Card subtitle', s.sub, 'input', (v) => { s.sub = v; }));
  f.append(imageField('Card image', s.thumb, (url) => { s.thumb = url; },
    'Optional. Falls back to the first event poster.'));
  f.append(field('Heading', s.heading, 'input', (v) => { s.heading = v; }, 'The big title, e.g. the month.'));
  f.append(field('Eyebrow', s.eyebrow, 'input', (v) => { s.eyebrow = v; }));
  f.append(field('Footer line', s.foot, 'input', (v) => { s.foot = v; }));

  f.append(sectionHead('Events'));
  s.events.forEach((e, idx) => {
    const wrap = document.createElement('div');
    wrap.className = 'listitem';
    const past = e.on && e.on < todayISO();
    wrap.append(navRow(e.name, [prettyDate(e.on), e.genre, past ? 'Past' : ''].filter(Boolean).join(' · '),
      () => go({ view: 'event', idx }), e.poster));
    wrap.append(moveControls(s.events, idx, render));
    f.append(wrap);
  });
  if (batch) f.append(batch.el);
  f.append(posterDropZone());
  f.append(Object.assign(document.createElement('p'), {
    className: 'hint',
    textContent: 'A whole month at once is fine. Each poster is read for the act, date and genre — check them before saving.',
  }));

  f.append(button('+ Add an event by hand', () => {
    s.events.push({ id: newId(), on: '', name: 'New event', genre: '', poster: '', description: '' });
    setDirty(true);
    go({ view: 'event', idx: s.events.length - 1 });
  }));

  f.append(sectionHead('Weekly entertainment'));
  f.append(field('Heading', s.weekly.title, 'input', (v) => { s.weekly.title = v; }));
  s.weekly.items.forEach((w, idx) => {
    const wrap = document.createElement('div');
    wrap.className = 'listitem';
    wrap.append(navRow(w.name, w.when, () => go({ view: 'weekly', idx }), w.image));
    wrap.append(moveControls(s.weekly.items, idx, render));
    f.append(wrap);
  });
  f.append(button('+ Add a weekly slot', () => {
    s.weekly.items.push({ id: newId(), name: 'New night', when: '', image: '' });
    setDirty(true);
    go({ view: 'weekly', idx: s.weekly.items.length - 1 });
  }));

  screenEl.replaceChildren(f);
}

function screenEvent(idx) {
  const e = menu.liveShows.events[idx];
  if (!e) { back(); return; }
  navTitle.textContent = e.name || 'Event';
  navBack.hidden = false;
  const f = document.createDocumentFragment();
  f.append(imageField('Poster', e.poster, (url) => { e.poster = url; },
    'Instagram post size works best. JPEG, PNG or WebP, up to 8MB.'));
  f.append(field('Name', e.name, 'input', (v) => { e.name = v; navTitle.textContent = v || 'Event'; }));
  f.append(dateField('Date', e.on, (v) => { e.on = v; },
    e.repeat === 'weekly'
      ? 'The next time this night runs. It moves on a week by itself, so it never drops off.'
      : 'The day and date shown on the card come from this. Once it passes, the show drops off the schedule automatically.'));

  const rep = document.createElement('div');
  rep.className = 'visrow';
  rep.append(
    Object.assign(document.createElement('span'), { textContent: 'Every week' }),
    visibilityToggle(
      () => e.repeat === 'weekly',
      (v) => { e.repeat = v ? 'weekly' : ''; },
      () => render(),
      {
        on: 'Weekly', off: 'One-off', mutedWhen: false,
        titles: {
          on: 'Runs every week — tap to make it a one-off',
          off: 'A single night — tap if it runs every week',
        },
      },
    ),
  );
  f.append(rep);
  f.append(field('Genre', e.genre, 'input', (v) => { e.genre = v; }, 'Separate with " / " for gold dots.'));
  f.append(field('Description', e.description, 'textarea', (v) => { e.description = v; },
    'Shown under the poster on the event page.'));
  screenEl.replaceChildren(f);
}

function screenWeekly(idx) {
  const w = menu.liveShows.weekly.items[idx];
  if (!w) { back(); return; }
  navTitle.textContent = w.name || 'Weekly';
  navBack.hidden = false;
  const f = document.createDocumentFragment();
  f.append(imageField('Image', w.image, (url) => { w.image = url; }, 'Optional background for the card.'));
  f.append(field('Name', w.name, 'input', (v) => { w.name = v; navTitle.textContent = v || 'Weekly'; }));
  f.append(field('When', w.when, 'input', (v) => { w.when = v; }, 'e.g. Tue — Sat · 6PM'));
  screenEl.replaceChildren(f);
}

function render() {
  const s = here();
  if (s.view === 'home') return screenHome();
  if (s.view === 'cover') return screenCover();
  if (s.view === 'section') return screenSection(s.idx);
  if (s.view === 'entry') return screenEntry(s.sIdx, s.eIdx);
  if (s.view === 'shows') return screenShows();
  if (s.view === 'event') return screenEvent(s.idx);
  if (s.view === 'weekly') return screenWeekly(s.idx);
  return screenHome();
}

navBack.addEventListener('click', back);

/* ---------------- auth ---------------- */

function showLogin(message) {
  loginView.hidden = false;
  editorView.hidden = true;
  if (message) { loginError.textContent = message; loginError.hidden = false; }
}

loginForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  loginError.hidden = true;
  const b = loginForm.querySelector('button');
  b.disabled = true; b.textContent = 'Signing in…';
  try {
    const res = await api('/api/admin/login', {
      method: 'POST',
      body: JSON.stringify({ password: document.getElementById('password').value }),
    });
    if (!res.ok) {
      const { error } = await res.json().catch(() => ({}));
      loginError.textContent = error || 'Could not sign in';
      loginError.hidden = false;
      return;
    }
    document.getElementById('password').value = '';
    loginView.hidden = true;
    await loadMenu();
  } catch {
    loginError.textContent = 'Network problem — check your connection.';
    loginError.hidden = false;
  } finally {
    b.disabled = false; b.textContent = 'Sign in';
  }
});

document.getElementById('logout').addEventListener('click', async () => {
  if (dirty && !confirm('You have unsaved changes. Sign out anyway?')) return;
  await api('/api/admin/logout', { method: 'POST' }).catch(() => {});
  setDirty(false);
  location.reload();
});

/* ---------------- load & save ---------------- */

async function loadMenu() {
  const res = await api('/api/admin/menu');
  if (res.status === 401) { showLogin(); return; }
  if (!res.ok) { toast('Could not load the menu', true); return; }
  menu = await res.json();
  baseUpdatedAt = menu.updatedAt ?? null;
  stack = [{ view: 'home' }];
  editorView.hidden = false;
  render();
  setDirty(false);
}

saveBtn.addEventListener('click', async () => {
  saveBtn.disabled = true;
  saveStatus.textContent = 'Saving…';
  saveStatus.className = 'save-status';
  try {
    const res = await api('/api/admin/menu', {
      method: 'PUT',
      body: JSON.stringify({ menu, baseUpdatedAt }),
    });
    if (res.status === 401) {
      showLogin('Your session expired. Sign in again — your edits are still on screen.');
      return;
    }
    if (res.status === 409) {
      const { error } = await res.json();
      saveStatus.textContent = 'Not saved';
      saveStatus.className = 'save-status error';
      toast(error, true);
      saveBtn.disabled = false;
      return;
    }
    if (!res.ok) {
      const { error } = await res.json().catch(() => ({}));
      throw new Error(error || 'Save failed');
    }
    const saved = await res.json();
    baseUpdatedAt = saved.updatedAt;
    menu.liveShows = saved.liveShows;   // ids the server assigned to new records
    setDirty(false);
    render();
    toast('Updated — live now');
  } catch (err) {
    saveStatus.textContent = 'Not saved';
    saveStatus.className = 'save-status error';
    toast(err.message || 'Could not save', true);
    saveBtn.disabled = false;
  }
});

loadMenu().catch(() => showLogin());
