const loginView = document.getElementById('login-view');
const editorView = document.getElementById('editor-view');
const loginForm = document.getElementById('login-form');
const loginError = document.getElementById('login-error');
const sectionsEl = document.getElementById('sections');
const saveBtn = document.getElementById('save');
const saveStatus = document.getElementById('save-status');
const toastEl = document.getElementById('toast');

const sectionTemplate = document.getElementById('section-template');
const itemTemplate = document.getElementById('item-template');

/** Working copy of the menu, plus the version stamp we loaded it at. */
let menu = null;
let baseUpdatedAt = null;
let dirty = false;

// Each maps to the matching key on menu.restaurant.
const VENUE_FIELDS = ['venue-name', 'venue-tagline', 'venue-note'];

function api(path, options = {}) {
  return fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      // Paired with the SameSite=Strict cookie, this blocks cross-site posts.
      'X-Requested-With': 'vibration-admin',
      ...options.headers,
    },
  });
}

function newId() {
  return (crypto.randomUUID?.() ?? String(Math.random()).slice(2)).slice(0, 8);
}

let toastTimer;
function toast(message, isError = false) {
  toastEl.textContent = message;
  toastEl.className = isError ? 'toast error' : 'toast';
  toastEl.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toastEl.hidden = true;
  }, isError ? 6000 : 2500);
}

function setDirty(value) {
  dirty = value;
  saveBtn.disabled = !value;
  saveStatus.textContent = value ? 'Unsaved changes' : 'All changes saved';
  saveStatus.className = value ? 'save-status dirty' : 'save-status';
}

// Guards against losing edits to an accidental back-swipe or tab close.
window.addEventListener('beforeunload', (event) => {
  if (dirty) event.preventDefault();
});

/* ---------------- Sign in ---------------- */

function showLogin(message) {
  loginView.hidden = false;
  editorView.hidden = true;
  if (message) {
    loginError.textContent = message;
    loginError.hidden = false;
  }
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
    loginError.textContent = 'Network problem. Check your connection and try again.';
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

/* ---------------- Load ---------------- */

async function loadMenu() {
  const response = await api('/api/admin/menu');
  if (response.status === 401) {
    showLogin();
    return;
  }
  if (!response.ok) {
    toast('Could not load the menu', true);
    return;
  }

  menu = await response.json();
  baseUpdatedAt = menu.updatedAt;

  document.getElementById('venue-name').value = menu.restaurant.name;
  document.getElementById('venue-tagline').value = menu.restaurant.tagline;
  document.getElementById('venue-note').value = menu.restaurant.note;
  document.getElementById('currency').value = menu.currency;

  editorView.hidden = false;
  renderSections();
  setDirty(false);
}

/* ---------------- Venue fields ---------------- */

for (const id of VENUE_FIELDS) {
  document.getElementById(id).addEventListener('input', (event) => {
    const key = id.replace('venue-', '');
    menu.restaurant[key] = event.target.value;
    setDirty(true);
  });
}

document.getElementById('currency').addEventListener('input', (event) => {
  menu.currency = event.target.value;
  setDirty(true);
});

/* ---------------- Rendering ----------------
   Structural changes (add/remove/reorder) re-render; plain typing mutates the
   model in place so the field never loses focus mid-word. */

function findSection(id) {
  return menu.sections.find((section) => section.id === id);
}

function buildItem(item, section, index, total) {
  const node = itemTemplate.content.firstElementChild.cloneNode(true);
  node.dataset.itemId = item.id;

  const name = node.querySelector('.item-name');
  const price = node.querySelector('.item-price');
  const desc = node.querySelector('.item-desc');
  const available = node.querySelector('.item-available');

  name.value = item.name;
  price.value = item.price;
  desc.value = item.description;
  available.checked = item.available;
  price.placeholder = menu.currency ? `Price (${menu.currency})` : 'Price';

  name.addEventListener('input', () => {
    item.name = name.value;
    setDirty(true);
  });
  price.addEventListener('input', () => {
    item.price = price.value;
    setDirty(true);
  });
  desc.addEventListener('input', () => {
    item.description = desc.value;
    setDirty(true);
  });
  available.addEventListener('change', () => {
    item.available = available.checked;
    setDirty(true);
  });

  node.querySelector('[data-act="item-up"]').disabled = index === 0;
  node.querySelector('[data-act="item-down"]').disabled = index === total - 1;

  node.querySelector('[data-act="item-up"]').addEventListener('click', () => {
    moveWithin(section.items, index, -1);
  });
  node.querySelector('[data-act="item-down"]').addEventListener('click', () => {
    moveWithin(section.items, index, 1);
  });
  node.querySelector('[data-act="item-delete"]').addEventListener('click', () => {
    if (item.name && !confirm(`Delete "${item.name}"?`)) return;
    section.items.splice(index, 1);
    renderSections();
    setDirty(true);
  });

  return node;
}

function buildSection(section, index, total) {
  const node = sectionTemplate.content.firstElementChild.cloneNode(true);
  node.dataset.sectionId = section.id;

  const name = node.querySelector('.section-name');
  const desc = node.querySelector('.section-desc');
  name.value = section.name;
  desc.value = section.description;

  name.addEventListener('input', () => {
    section.name = name.value;
    setDirty(true);
  });
  desc.addEventListener('input', () => {
    section.description = desc.value;
    setDirty(true);
  });

  node.querySelector('[data-act="section-up"]').disabled = index === 0;
  node.querySelector('[data-act="section-down"]').disabled = index === total - 1;

  node.querySelector('[data-act="section-up"]').addEventListener('click', () => {
    moveWithin(menu.sections, index, -1);
  });
  node.querySelector('[data-act="section-down"]').addEventListener('click', () => {
    moveWithin(menu.sections, index, 1);
  });
  node.querySelector('[data-act="section-delete"]').addEventListener('click', () => {
    const label = section.name || 'this section';
    const count = section.items.length;
    const warning = count
      ? `Delete "${label}" and its ${count} item${count === 1 ? '' : 's'}?`
      : `Delete "${label}"?`;
    if (!confirm(warning)) return;
    menu.sections.splice(index, 1);
    renderSections();
    setDirty(true);
  });

  const itemsEl = node.querySelector('.items');
  if (section.items.length === 0) {
    itemsEl.append(
      Object.assign(document.createElement('p'), {
        className: 'empty-hint',
        textContent: 'No items in this section yet.',
      }),
    );
  } else {
    section.items.forEach((item, itemIndex) => {
      itemsEl.append(buildItem(item, section, itemIndex, section.items.length));
    });
  }

  node.querySelector('[data-act="item-add"]').addEventListener('click', () => {
    section.items.push({ id: newId(), name: '', description: '', price: '', available: true });
    renderSections();
    setDirty(true);
    // Drop the cursor straight into the new item's name field.
    const cards = sectionsEl
      .querySelector(`[data-section-id="${section.id}"]`)
      .querySelectorAll('.item-card');
    cards[cards.length - 1]?.querySelector('.item-name')?.focus();
  });

  return node;
}

function moveWithin(list, index, delta) {
  const target = index + delta;
  if (target < 0 || target >= list.length) return;
  [list[index], list[target]] = [list[target], list[index]];
  renderSections();
  setDirty(true);
}

function renderSections() {
  sectionsEl.replaceChildren(
    ...menu.sections.map((section, index) => buildSection(section, index, menu.sections.length)),
  );
}

document.getElementById('add-section').addEventListener('click', () => {
  menu.sections.push({ id: newId(), name: '', description: '', items: [] });
  renderSections();
  setDirty(true);
  const cards = sectionsEl.querySelectorAll('.section-card');
  cards[cards.length - 1]?.querySelector('.section-name')?.focus();
});

/* ---------------- Bulk paste ---------------- */

function parseBulk(text) {
  const sections = [];
  let current = null;

  for (const rawLine of text.split('\n')) {
    const line = rawLine.trim();
    if (!line) continue;

    if (line.startsWith('##')) {
      current = { id: newId(), name: line.replace(/^#+/, '').trim(), description: '', items: [] };
      sections.push(current);
      continue;
    }

    // Items before any heading still need somewhere to live.
    if (!current) {
      current = { id: newId(), name: 'Menu', description: '', items: [] };
      sections.push(current);
    }

    const [name, price = '', description = ''] = line.split('|').map((part) => part.trim());
    if (!name) continue;
    current.items.push({ id: newId(), name, price, description, available: true });
  }

  return sections;
}

document.getElementById('bulk-apply').addEventListener('click', () => {
  const text = document.getElementById('bulk-input').value;
  const parsed = parseBulk(text);

  if (parsed.length === 0) {
    toast('Nothing to import — check the format', true);
    return;
  }

  const itemCount = parsed.reduce((total, section) => total + section.items.length, 0);
  if (!confirm(`Replace the whole menu with ${parsed.length} section(s) and ${itemCount} item(s)?`)) {
    return;
  }

  menu.sections = parsed;
  renderSections();
  setDirty(true);
  document.getElementById('bulk-input').value = '';
  toast(`Loaded ${itemCount} items — review, then Save`);
});

/* ---------------- Save ---------------- */

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
    toast('Menu updated — it is live now');
  } catch (error) {
    saveStatus.textContent = 'Not saved';
    saveStatus.className = 'save-status error';
    toast(error.message || 'Could not save', true);
    saveBtn.disabled = false;
  }
});

/* ---------------- Start ---------------- */

// An existing cookie means we can skip the login screen entirely.
loadMenu().catch(() => showLogin());
