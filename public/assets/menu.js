const menuEl = document.getElementById('menu');
const navEl = document.getElementById('section-nav');

function setText(id, value) {
  const el = document.getElementById(id);
  if (!el) return;
  if (value) {
    el.textContent = value;
    el.hidden = false;
  } else {
    el.hidden = true;
  }
}

/** Prices are free text ("14", "9 / 12", "market"); only prefix bare numbers. */
function formatPrice(price, currency) {
  if (!price) return '';
  return /^[\d.,]+$/.test(price) ? `${currency}${price}` : price;
}

function renderItem(item, currency) {
  const li = document.createElement('li');
  li.className = item.available ? 'item' : 'item unavailable';

  const head = document.createElement('div');
  head.className = 'item-head';

  const name = document.createElement('span');
  name.className = 'item-name';
  name.textContent = item.name;
  head.append(name);

  if (!item.available) {
    const badge = document.createElement('span');
    badge.className = 'sold-out';
    badge.textContent = 'Sold out';
    name.append(badge);
  }

  head.append(Object.assign(document.createElement('span'), { className: 'leader' }));

  const price = formatPrice(item.price, currency);
  if (price) {
    const priceEl = document.createElement('span');
    priceEl.className = 'item-price';
    priceEl.textContent = price;
    head.append(priceEl);
  }

  li.append(head);

  if (item.description) {
    const desc = document.createElement('p');
    desc.className = 'item-desc';
    desc.textContent = item.description;
    li.append(desc);
  }

  return li;
}

function renderSection(section, currency) {
  const wrapper = document.createElement('section');
  wrapper.className = 'menu-section';
  wrapper.id = `section-${section.id}`;

  const heading = document.createElement('h2');
  heading.textContent = section.name;
  wrapper.append(heading);

  if (section.description) {
    const desc = document.createElement('p');
    desc.className = 'section-desc';
    desc.textContent = section.description;
    wrapper.append(desc);
  }

  const list = document.createElement('ul');
  for (const item of section.items) list.append(renderItem(item, currency));
  wrapper.append(list);

  return wrapper;
}

function renderNav(sections) {
  navEl.replaceChildren();
  // One section needs no jump list.
  if (sections.length < 2) {
    navEl.hidden = true;
    return;
  }
  for (const section of sections) {
    const link = document.createElement('a');
    link.href = `#section-${section.id}`;
    link.textContent = section.name;
    navEl.append(link);
  }
  navEl.hidden = false;
}

function render(menu) {
  document.title = `${menu.restaurant.name} — Menu`;
  setText('venue-name', menu.restaurant.name);
  setText('venue-tagline', menu.restaurant.tagline);
  setText('venue-note', menu.restaurant.note);

  const sections = menu.sections.filter((section) => section.items.length > 0);

  if (sections.length === 0) {
    navEl.hidden = true;
    menuEl.replaceChildren(
      Object.assign(document.createElement('p'), {
        className: 'state',
        textContent: 'Our menu is being updated. Please check back shortly.',
      }),
    );
    menuEl.setAttribute('aria-busy', 'false');
    return;
  }

  renderNav(sections);
  menuEl.replaceChildren(...sections.map((section) => renderSection(section, menu.currency)));
  menuEl.setAttribute('aria-busy', 'false');

  if (menu.updatedAt) {
    const stamp = new Date(menu.updatedAt);
    setText('updated', `Updated ${stamp.toLocaleDateString(undefined, {
      day: 'numeric',
      month: 'long',
      year: 'numeric',
    })}`);
  }
}

async function load() {
  try {
    const response = await fetch('/api/menu');
    if (!response.ok) throw new Error(`Menu request failed: ${response.status}`);
    render(await response.json());
  } catch (error) {
    console.error(error);
    menuEl.replaceChildren(
      Object.assign(document.createElement('p'), {
        className: 'state',
        textContent: 'We could not load the menu just now. Please refresh to try again.',
      }),
    );
    menuEl.setAttribute('aria-busy', 'false');
  }
}

load();
