/* Vibration menu — behaviour ported verbatim from the original single-file build.
   The only change: DATA is fetched from /api/menu instead of being inlined, and
   images are real files rather than base64 blobs. Rendering and interaction are
   unchanged. */

(async function () {
  const home = document.getElementById('home'), grid = document.getElementById('grid');
  const viewer = document.getElementById('viewer'), track = document.getElementById('track');
  const bars = document.getElementById('bars'), countEl = document.getElementById('count');
  const sectEl = document.getElementById('sect'), topEl = document.getElementById('top');
  const hint = document.getElementById('hint'), prevB = document.getElementById('prev'), nextB = document.getElementById('next');

  let menu;
  try {
    const res = await fetch('/api/menu');
    if (!res.ok) throw new Error('menu request failed: ' + res.status);
    menu = await res.json();
  } catch (err) {
    console.error(err);
    grid.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;'
      + 'height:100%;color:#8D8778;font-size:13px;letter-spacing:.2em;text-transform:uppercase">'
      + 'Menu unavailable &mdash; please refresh</div>';
    return;
  }

  // Reassemble the shapes the original code expects.
  const DATA = { _logo: menu.brand.logo };
  const ORDER = menu.sections.map((s) => s.key);
  const SUB = {};
  for (const s of menu.sections) {
    DATA[s.key] = { title: s.title, thumb: s.thumb, entries: s.entries };
    SUB[s.key] = s.sub || '';
  }

  const tagEl = document.querySelector('#home .brand .tag');
  const footEl = document.querySelector('#home .foot');
  if (tagEl) tagEl.innerHTML = menu.brand.tag;
  if (footEl) footEl.innerHTML = menu.brand.foot;

  const shows = menu.liveShows;

  function makeCard(thumb, title, sub, onClick) {
    const c = document.createElement('div'); c.className = 'card';
    c.innerHTML = (thumb ? '<img src="' + thumb + '" alt="">' : '')
      + '<div class="scrim"></div><div class="lbl"><h2>' + title + '</h2><span>' + (sub || '') + '</span></div>'
      + '<div class="arw">&#10095;</div>';
    c.onclick = onClick;
    grid.appendChild(c);
  }

  // Live Shows sits above the menu sections. Its card falls back to the first
  // event poster until a dedicated thumbnail is uploaded.
  if (shows) {
    makeCard(shows.thumb || (shows.events.find(e => e.poster) || {}).poster || '',
      shows.title, shows.sub, openShows);
  }

  ORDER.forEach(k => {
    const s = DATA[k]; if (!s) return;
    makeCard(s.thumb, s.title, SUB[k] || '', () => openBook(k));
  });

  // The grid was written for exactly five rows.
  grid.style.gridTemplateRows = 'repeat(' + grid.children.length + ',1fr)';

  /* Card titles scale to the card, not the viewport: adding a section shortens
     every card, and a width-only size would not notice. */
  function sizeCardTitles() {
    const first = grid.firstElementChild;
    if (!first) return;
    const h = first.getBoundingClientRect().height;
    if (!h) return;
    grid.style.setProperty('--cardfs', Math.min(41, Math.max(21, h * 0.30)).toFixed(1) + 'px');
  }
  requestAnimationFrame(sizeCardTitles);
  window.addEventListener('resize', sizeCardTitles);

  const esc = s => String(s == null ? '' : s);
  function buildDots(t) { return esc(t).split(' / ').map(x => x.trim()).join(' <span class="dot">&middot;</span> '); }

  function priceHTML(e) {
    if (e.priceHtml) return e.priceHtml;
    return '<small>THB</small>' + esc(e.price);
  }

  function pageHTML(e) {
    if (e.type === 'back') {
      return '<div class="backpage"><div class="bp-glow"></div>'
        + '<img src="' + DATA._logo + '" alt="Vibration">'
        + (e.stars ? '<div class="bp-stars">&#9733; &#9733; &#9733; &#9733; &#9733;</div>' : '')
        + (e.kicker ? '<div class="bp-kick">' + e.kicker + '</div>' : '')
        + '<div class="bp-quote">' + e.quote + '</div>'
        + (e.attrib ? '<div class="bp-attrib">' + e.attrib + '</div>' : '')
        + (e.fine ? '<div class="bp-fine">' + e.fine + '</div>' : '')
        + '</div>';
    }
    if (e.type === 'list') {
      const blocks = [...(e.col1 || []), ...(e.col2 || [])];
      const body = blocks.map(b =>
        '<div class="lp-cat">' + esc(b.cat) + '</div>' +
        (b.rows || []).map(r => '<div class="lp-row"><div class="lp-nm">' + esc(r[0]) +
          (r[2] ? '<span class="sub">' + esc(r[2]) + '</span>' : '') +
          '</div><div class="lp-dots"></div><div class="lp-pr">' + esc(r[1]) + '</div></div>').join('')
      ).join('');
      return '<div class="listpage">'
        + '<div class="lp-eyebrow">' + esc(e.eyebrow) + '</div><div class="lp-rule"></div>'
        + '<div class="lp-title">' + esc(e.title) + '</div>'
        + body
        + '<div class="lp-end">Vibration &mdash; Koh Samui</div></div>';
    }
    // Per-image mobile framing; the >=700px rule ignores both.
    const frame = (e.zoom ? '--z:' + e.zoom + ';' : '')
      + (e.focusY != null ? '--fy:' + e.focusY + '%;' : '');

    return '<div class="itempage">'
      + '<div class="herobox"><img' + (frame ? ' style="' + frame + '"' : '') + ' src="' + e.hero + '"></div>'
      + '<div class="fadeT"></div><div class="fadeB"></div>'
      + '<div class="eyeb">' + esc(e.eyebrow) + '</div><div class="eyerl"></div>'
      + '<div class="txt">'
      + '<div class="nm">' + esc(e.name) + '</div>'
      + (e.story ? '<div class="st">' + esc(e.story) + '</div>' : '')
      + (e.build ? '<div class="bd">' + buildDots(e.build) + '</div>' : '')
      + (e.serve ? '<div class="sv"><span class="lbl">' + esc(e.serve) + '</span></div>' : '')
      + '<div class="pr">' + priceHTML(e) + '</div>'
      + '</div></div>';
  }

  /* ---------------- Live Shows ---------------- */

  const showsEl = document.getElementById('shows');
  const showsBack = document.getElementById('shows-back');
  let cameFromShows = false;

  /** Display date and weekday come from the ISO date when there is one. */
  function eventWhen(e) {
    if (e.on) {
      const [y, m, d] = e.on.split('-');
      const dt = new Date(Date.UTC(+y, +m - 1, +d));
      return {
        date: d + '.' + m,
        day: dt.toLocaleDateString('en-GB', { weekday: 'long', timeZone: 'UTC' }),
      };
    }
    return { date: e.date || '', day: e.day || '' };
  }

  function eventHTML(e) {
    const w = eventWhen(e);
    const when = [w.date, w.day].filter(Boolean).join(' &middot; ');
    return '<div class="itempage eventpage">'
      + '<div class="herobox posterbox">'
        + (e.poster ? '<img src="' + e.poster + '" alt="">'
                    : '<div class="noposter">Poster coming soon</div>')
      + '</div>'
      + '<div class="eyeb">' + esc(shows.eyebrow || shows.title) + '</div><div class="eyerl"></div>'
      + '<div class="txt">'
        + '<div class="nm">' + esc(e.name) + '</div>'
        + (when ? '<div class="ev-when">' + when + '</div>' : '')
        + (e.genre ? '<div class="bd">' + buildDots(e.genre) + '</div>' : '')
        + (e.description ? '<div class="st">' + esc(e.description) + '</div>' : '')
      + '</div></div>';
  }

  function renderShows() {
    document.getElementById('shows-eyebrow').innerHTML = shows.eyebrow || '';
    // The heading is optional — with none, the eyebrow and rule stand alone.
    const titleEl = document.getElementById('shows-title');
    titleEl.innerHTML = shows.heading || '';
    titleEl.hidden = !shows.heading;
    document.getElementById('shows-foot').innerHTML = shows.foot || '';

    const list = document.getElementById('ev-list');
    list.replaceChildren();
    if (!shows.events.length) {
      list.append(Object.assign(document.createElement('div'),
        { className: 'shows-empty', textContent: 'The next line-up is on its way.' }));
    }
    shows.events.forEach((e, idx) => {
      const row = document.createElement('div');
      row.className = 'ev';
      const w = eventWhen(e);
      row.innerHTML = (e.poster ? '<img class="ev-bg" src="' + e.poster + '" alt="">' : '')
        + '<div class="ev-scrim"></div>'
        + '<div class="ev-date"><div class="ev-d">' + esc(w.date) + '</div>'
          + (w.day ? '<div class="ev-day">' + esc(w.day) + '</div>' : '') + '</div>'
        + '<div class="ev-txt"><div class="ev-nm">' + esc(e.name) + '</div>'
          + (e.genre ? '<div class="ev-gen">' + esc(e.genre) + '</div>' : '') + '</div>'
        + '<div class="ev-arw">&#10095;</div>';
      row.onclick = () => openEvent(idx);
      list.append(row);
    });

    const weekly = (shows.weekly && shows.weekly.items) || [];
    document.getElementById('wk-h').innerHTML = weekly.length ? (shows.weekly.title || '') : '';
    const wkL = document.getElementById('wk-list');
    wkL.replaceChildren();
    weekly.forEach(w => {
      const c = document.createElement('div');
      c.className = 'wkc';
      c.innerHTML = (w.image ? '<img src="' + w.image + '" alt="">' : '')
        + '<div class="sc"></div>'
        + '<div class="nm">' + esc(w.name) + '</div>'
        + (w.when ? '<div class="wh">' + esc(w.when) + '</div>' : '');
      wkL.append(c);
    });
  }

  function openShows() {
    renderShows();
    home.classList.add('gone');
    showsEl.classList.add('on');
    showsBack.classList.add('on');
    showsEl.scrollTop = 0;
  }

  function closeShows() {
    showsEl.classList.remove('on');
    showsBack.classList.remove('on');
    home.classList.remove('gone');
  }

  showsBack.onclick = closeShows;

  function openEvent(start) {
    const list = shows.events;
    book = 'live'; n = list.length; i = start;
    sectEl.textContent = shows.title;
    track.innerHTML = ''; bars.innerHTML = '';
    list.forEach(e => {
      const sl = document.createElement('div');
      sl.className = 'slide';
      sl.innerHTML = eventHTML(e);
      track.appendChild(sl);
      const b = document.createElement('div'); b.className = 'bar'; b.innerHTML = '<i></i>'; bars.appendChild(b);
    });
    cameFromShows = true;
    showsEl.classList.remove('on');
    showsBack.classList.remove('on');
    viewer.classList.add('on');
    fit(); render(false); wake(); autofitNames();
    hint.classList.remove('hide'); setTimeout(() => hint.classList.add('hide'), 3600);
  }

  /** Leaving the viewer returns to wherever it was opened from. */
  function leaveViewer() {
    viewer.classList.remove('on');
    if (cameFromShows) { cameFromShows = false; openShows(); }
    else home.classList.remove('gone');
  }

  let book = null, i = 0, n = 0;
  /* keep every title at 180px; shrink only the rare one that would overflow */
  function autofitLine(el, minRatio) {
    el.style.fontSize = '';
    const p = el.closest('.txt'); if (!p) return;
    const cs = getComputedStyle(p);
    const avail = p.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
    if (!avail || avail <= 0) return;
    const base = parseFloat(getComputedStyle(el).fontSize);
    const w = el.scrollWidth;
    if (w > avail) {
      const want = base * avail / w - 0.5;
      const size = Math.max(14, base * minRatio, want);
      el.style.fontSize = size + 'px';
      /* if 14px still doesn't fit, drop the flanking rules instead of shrinking further */
      if (size <= 14.5 && el.scrollWidth > avail) el.classList.add('norule');
      else el.classList.remove('norule');
    }
  }
  function autofitNames() {
    const MIN = 0.62;   /* never below 62% of the responsive size, and never below 14px */
    document.querySelectorAll('.slide .itempage .sv').forEach(el => autofitLine(el, 0.72));
    document.querySelectorAll('.slide .itempage .nm').forEach(el => {
      el.style.fontSize = '';
      const cs = getComputedStyle(el.parentElement);
      const avail = el.parentElement.clientWidth
        - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
      if (!avail || avail <= 0) return;
      const base = parseFloat(getComputedStyle(el).fontSize);
      const w = el.scrollWidth;
      if (w > avail) {
        const size = Math.max(base * MIN, Math.floor(base * avail / w) - 0.5);
        el.style.fontSize = size + 'px';
      }
    });
  }
  function fit() {
    const w = window.innerWidth, h = window.innerHeight;
    const k = Math.min(w / 2160, h / 3060);
    const ox = (w - 2160 * k) / 2, oy = (h - 3060 * k) / 2;
    /* item pages are responsive now; nothing to scale */
  }
  function openBook(key) {
    cameFromShows = false;
    book = key; const list = DATA[key].entries; n = list.length; i = 0;
    sectEl.textContent = DATA[key].title;
    track.innerHTML = ''; bars.innerHTML = '';
    list.forEach(e => {
      const sl = document.createElement('div'); sl.className = 'slide' + (e.type === 'list' ? ' scrolly' : '');
      sl.innerHTML = pageHTML(e); track.appendChild(sl);
      if (e.type === 'list') {
        sl.addEventListener('scroll', () => {
          const down = sl.scrollTop > 10;
          prevB.classList.toggle('scrollhide', down);
          nextB.classList.toggle('scrollhide', down);
        }, { passive: true });
      }
      const b = document.createElement('div'); b.className = 'bar'; b.innerHTML = '<i></i>'; bars.appendChild(b);
    });
    home.classList.add('gone'); viewer.classList.add('on');
    fit(); render(false); wake(); autofitNames();
    hint.classList.remove('hide'); setTimeout(() => hint.classList.add('hide'), 3600);
  }
  document.getElementById('back').onclick = leaveViewer;

  function render(anim = true) {
    track.style.transition = anim ? 'transform .38s cubic-bezier(.22,.61,.36,1)' : 'none';
    track.style.transform = 'translateX(' + (-i * 100) + '%)';
    countEl.textContent = (i + 1) + ' / ' + n;
    [...bars.children].forEach((b, k) => b.classList.toggle('done', k <= i));
    prevB.classList.toggle('hide', i === 0); nextB.classList.toggle('hide', i === n - 1);
    prevB.classList.remove('scrollhide'); nextB.classList.remove('scrollhide');
  }
  function go(d) { const t = Math.min(n - 1, Math.max(0, i + d)); if (t !== i) { i = t; render(); hint.classList.add('hide'); } }

  let x0, y0, dx = 0, drag = false, lock = null;
  const stage = document.getElementById('stage');
  stage.addEventListener('touchstart', e => { x0 = e.touches[0].clientX; y0 = e.touches[0].clientY; dx = 0; drag = true; lock = null; track.style.transition = 'none'; }, { passive: true });
  stage.addEventListener('touchmove', e => {
    if (!drag) return;
    const ddx = e.touches[0].clientX - x0, ddy = e.touches[0].clientY - y0;
    if (lock === null) lock = Math.abs(ddx) > Math.abs(ddy) ? 'x' : 'y';
    if (lock !== 'x') return;
    dx = ddx; if ((i === 0 && dx > 0) || (i === n - 1 && dx < 0)) dx *= .32;
    track.style.transform = 'translateX(calc(' + (-i * 100) + '% + ' + ((dx / window.innerWidth) * 100) + '%))';
  }, { passive: true });
  stage.addEventListener('touchend', () => {
    if (!drag) return; drag = false;
    if (lock === 'x' && Math.abs(dx) > window.innerWidth * 0.18) go(dx < 0 ? 1 : -1); else render();
    dx = 0;
  }, { passive: true });
  let mx, md = false, mdx = 0;
  stage.addEventListener('mousedown', e => { mx = e.clientX; md = true; mdx = 0; track.style.transition = 'none'; e.preventDefault(); });
  window.addEventListener('mousemove', e => {
    if (!md) return; mdx = e.clientX - mx;
    if ((i === 0 && mdx > 0) || (i === n - 1 && mdx < 0)) mdx *= .32;
    track.style.transform = 'translateX(calc(' + (-i * 100) + '% + ' + ((mdx / window.innerWidth) * 100) + '%))';
  });
  window.addEventListener('mouseup', () => {
    if (!md) return; md = false;
    if (Math.abs(mdx) > window.innerWidth * 0.12) go(mdx < 0 ? 1 : -1); else render();
  });
  window.addEventListener('keydown', e => {
    if (!viewer.classList.contains('on')) return;
    if (e.key === 'ArrowRight') go(1); if (e.key === 'ArrowLeft') go(-1);
    if (e.key === 'Escape') leaveViewer();
  });
  nextB.onclick = () => go(1); prevB.onclick = () => go(-1);
  let idleT;
  function wake() {
    topEl.classList.remove('hide'); bars.classList.remove('hide');
    clearTimeout(idleT); idleT = setTimeout(() => { topEl.classList.add('hide'); bars.classList.add('hide'); }, 2800);
  }
  ['touchstart', 'mousemove', 'keydown', 'click'].forEach(ev => window.addEventListener(ev, wake, { passive: true }));
  window.addEventListener('resize', () => { fit(); autofitNames(); if (viewer.classList.contains('on')) render(false); });
  if (document.fonts && document.fonts.ready) { document.fonts.ready.then(() => autofitNames()); }
})();
