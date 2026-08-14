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

  ORDER.forEach(k => {
    const s = DATA[k]; if (!s) return;
    const c = document.createElement('div'); c.className = 'card';
    c.innerHTML = '<img src="' + s.thumb + '" alt="">'
      + '<div class="scrim"></div><div class="lbl"><h2>' + s.title + '</h2><span>' + (SUB[k] || '') + '</span></div>'
      + '<div class="arw">&#10095;</div>';
    c.onclick = () => openBook(k);
    grid.appendChild(c);
  });

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
  document.getElementById('back').onclick = () => { viewer.classList.remove('on'); home.classList.remove('gone'); };

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
    if (e.key === 'Escape') { viewer.classList.remove('on'); home.classList.remove('gone'); }
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
