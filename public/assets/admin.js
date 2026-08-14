const loginView = document.getElementById('login-view');
const editorView = document.getElementById('editor-view');
const loginForm = document.getElementById('login-form');
const loginError = document.getElementById('login-error');
const sectionsEl = document.getElementById('sections');
const saveBtn = document.getElementById('save');
const saveStatus = document.getElementById('save-status');
const toastEl = document.getElementById('toast');

let menu = null;
let baseUpdatedAt = null;
let dirty = false;

/* Only these are editable. Structure, images and layout are fixed — the server
   enforces the same list, this is just what gets rendered. */
const FIELDS = {
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
  return fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-Requested-With': 'vibration-admin',
      ...options.headers,
    },
  });
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

window.addEventListener('beforeunload', (event) => {
  if (dirty) event.preventDefault();
});

/* ---------------- field builders ---------------- */

function field(label, value, kind, onInput, hint) {
  const wrap = document.createElement('label');
  wrap.className = 'field';

  const name = document.createElement('span');
  name.className = 'field-label';
  name.textContent = label;
  wrap.append(name);

  const input = document.createElement(kind === 'textarea' ? 'textarea' : 'input');
  if (kind === 'textarea') input.rows = 2; else input.type = 'text';
  input.value = value ?? '';
  input.addEventListener('input', () => { onInput(input.value); setDirty(true); });
  wrap.append(input);

  if (hint) {
    const h = document.createElement('p');
    h.className = 'hint';
    h.textContent = hint;
    wrap.append(h);
  }
  return wrap;
}

function priceRow(entry) {
  const row = document.createElement('div');
  row.className = 'price-row';
  row.append(
    field('Price', entry.price, 'input', (v) => { entry.price = v; },
      'Number only — THB is added automatically.'),
  );
  if (entry.priceHtml) {
    row.append(field('Price (custom)', entry.priceHtml, 'input', (v) => { entry.priceHtml = v; }));
  }
  return row;
}

function listBlocks(entry) {
  const frag = document.createDocumentFragment();

  for (const col of ['col1', 'col2']) {
    for (const block of entry[col] || []) {
      const wrap = document.createElement('div');
      wrap.className = 'block';
      wrap.append(field('Category', block.cat, 'input', (v) => { block.cat = v; }));

      for (const row of block.rows || []) {
        const line = document.createElement('div');
        line.className = 'lrow';

        const mk = (cls, index, placeholder) => {
          const input = document.createElement('input');
          input.type = 'text';
          input.className = cls;
          input.value = row[index] ?? '';
          input.placeholder = placeholder;
          input.setAttribute('aria-label', placeholder);
          input.addEventListener('input', () => { row[index] = input.value; setDirty(true); });
          return input;
        };

        line.append(mk('nm', 0, 'Name'), mk('pr', 1, 'Price'), mk('sz', 2, 'Size'));
        wrap.append(line);
      }
      frag.append(wrap);
    }
  }
  return frag;
}

function entryCard(entry, index) {
  const card = document.createElement('div');
  card.className = 'entry';

  const head = document.createElement('div');
  head.className = 'entry-head';

  if (entry.hero) {
    const img = document.createElement('img');
    img.src = entry.hero;
    img.alt = '';
    img.loading = 'lazy';
    head.append(img);
  }

  const who = document.createElement('div');
  who.className = 'who';
  const title = document.createElement('span');
  title.className = 'serif';
  title.textContent = entry.name || entry.title || (entry.type === 'back' ? 'Back cover' : 'Page ' + (index + 1));
  const kind = document.createElement('span');
  kind.className = 'kind';
  kind.textContent = entry.type === 'item' ? 'Item' : entry.type === 'back' ? 'Back cover' : 'List page';
  who.append(title, kind);
  head.append(who);
  card.append(head);

  for (const [key, label, kind_, hint] of FIELDS[entry.type] || []) {
    card.append(field(label, entry[key], kind_, (v) => {
      entry[key] = v;
      if (key === 'name' || key === 'title') title.textContent = v || 'Untitled';
    }, hint));
  }

  if (entry.type === 'item') card.append(priceRow(entry));
  if (entry.type === 'list') card.append(listBlocks(entry));

  return card;
}

function sectionPanel(section) {
  const panel = document.createElement('details');
  panel.className = 'panel';

  const summary = document.createElement('summary');
  summary.innerHTML = '<span class="serif"></span>'
    + '<span class="count"></span><span class="chev">&#10095;</span>';
  summary.querySelector('.serif').textContent = section.title;
  summary.querySelector('.count').textContent = section.entries.length + ' pages';
  panel.append(summary);

  const body = document.createElement('div');
  body.className = 'panel-body';

  body.append(field('Section title', section.title, 'input', (v) => {
    section.title = v;
    summary.querySelector('.serif').textContent = v || 'Untitled';
  }));
  body.append(field('Subtitle', section.sub, 'input', (v) => { section.sub = v; },
    'Shown under the section name on the cover.'));

  section.entries.forEach((entry, index) => body.append(entryCard(entry, index)));

  panel.append(body);
  return panel;
}

function render() {
  document.getElementById('brand-tag').value = menu.brand.tag;
  document.getElementById('brand-foot').value = menu.brand.foot;
  sectionsEl.replaceChildren(...menu.sections.map(sectionPanel));
}

document.getElementById('brand-tag').addEventListener('input', (e) => {
  menu.brand.tag = e.target.value; setDirty(true);
});
document.getElementById('brand-foot').addEventListener('input', (e) => {
  menu.brand.foot = e.target.value; setDirty(true);
});

/* ---------------- auth ---------------- */

function showLogin(message) {
  loginView.hidden = false;
  editorView.hidden = true;
  if (message) { loginError.textContent = message; loginError.hidden = false; }
}

loginForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  loginError.hidden = true;
  const button = loginForm.querySelector('button');
  button.disabled = true;
  button.textContent = 'Signing in…';

  try {
    const response = await api('/api/admin/login', {
      method: 'POST',
      body: JSON.stringify({ password: document.getElementById('password').value }),
    });
    if (!response.ok) {
      const { error } = await response.json().catch(() => ({}));
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
    button.disabled = false;
    button.textContent = 'Sign in';
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
  const response = await api('/api/admin/menu');
  if (response.status === 401) { showLogin(); return; }
  if (!response.ok) { toast('Could not load the menu', true); return; }

  menu = await response.json();
  baseUpdatedAt = menu.updatedAt ?? null;
  editorView.hidden = false;
  render();
  setDirty(false);
}

saveBtn.addEventListener('click', async () => {
  saveBtn.disabled = true;
  saveStatus.textContent = 'Saving…';
  saveStatus.className = 'save-status';

  try {
    const response = await api('/api/admin/menu', {
      method: 'PUT',
      body: JSON.stringify({ menu, baseUpdatedAt }),
    });

    if (response.status === 401) {
      showLogin('Your session expired. Sign in again — your edits are still on screen.');
      return;
    }
    if (response.status === 409) {
      const { error } = await response.json();
      saveStatus.textContent = 'Not saved';
      saveStatus.className = 'save-status error';
      toast(error, true);
      saveBtn.disabled = false;
      return;
    }
    if (!response.ok) {
      const { error } = await response.json().catch(() => ({}));
      throw new Error(error || 'Save failed');
    }

    const saved = await response.json();
    baseUpdatedAt = saved.updatedAt;
    setDirty(false);
    toast('Menu updated — live now');
  } catch (error) {
    saveStatus.textContent = 'Not saved';
    saveStatus.className = 'save-status error';
    toast(error.message || 'Could not save', true);
    saveBtn.disabled = false;
  }
});

loadMenu().catch(() => showLogin());
