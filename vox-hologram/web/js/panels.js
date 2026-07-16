/* ==========================================================================
   panels.js — VOX v2 holographic source/web panels.

   Floating translucent holo-cards that materialize beside Vox as he speaks,
   mirroring the film's "AUTHORS — WELLS, H.G." / "SCIENCE FICTION — FILM"
   records: a labelled title bar, a translucent cyan body with scanlines and
   corner ticks, a source/host line, and a close (×). Cards flicker into being,
   are draggable, capped in number, and arranged in columns to Vox's left/right
   so they never cover his face.

   Public interface (consumed by app.js):
     const panels = createPanels(container);
     panels.add(panelObj);   // panelObj = an API.md panel frame {kind, ...}
     panels.clear();         // dismiss all (e.g. at the start of a new turn)
     panels.openUrl(url);    // fetch a page → open a "reader" panel

   Panel kinds (per API.md):
     source : compact citation card — title, snippet, thumbnail, host, "View".
     reader : expanded card — title + cleaned text (scroll) + image gallery;
              optional sandboxed "Live page" iframe when allow_iframe is true.
     image  : an image tile with a caption.

   Everything is DOM + CSS (see hologram.css). Remote text/urls are only ever
   assigned via textContent / element properties — never innerHTML — so page
   content cannot inject markup. Effects are compositor-cheap (transform/opacity).
   ========================================================================== */

export function createPanels(container) {
  const MAX_PANELS = 5;             // cap concurrent cards; retire the oldest
  const APPEAR_MS  = 520;           // must match .panel__frame panelIn duration
  const DISMISS_MS = 340;           // must match panelOut duration

  // Two edge columns so cards flank Vox without covering his face. Built here so
  // index.html only needs the empty #holo-panels container.
  const colLeft  = makeColumn('left');
  const colRight = makeColumn('right');
  container.appendChild(colLeft);
  container.appendChild(colRight);

  const live = [];                  // active panel records, oldest first
  let seq = 0;                      // fallback id source

  function makeColumn(side) {
    const col = document.createElement('div');
    col.className = 'holo-panels__col holo-panels__col--' + side;
    return col;
  }

  /* ---- Public: add a panel frame ---------------------------------------- */
  function add(panel) {
    if (!panel || typeof panel !== 'object') return null;
    const kind = panel.kind === 'reader' || panel.kind === 'image'
      ? panel.kind : 'source';
    const id = panel.id || ('panel-' + (++seq));

    // De-dupe: if a panel with this id already exists, don't stack a copy.
    if (live.some((r) => r.id === id)) return null;

    // Enforce the cap by retiring the oldest before adding.
    while (live.length >= MAX_PANELS) retire(live[0], true);

    const side = pickSide();
    const el = buildPanel(kind, panel);
    const col = side === 'left' ? colLeft : colRight;
    col.appendChild(el);

    const rec = { id, el, side, kind };
    live.push(rec);
    makeDraggable(rec);

    // Materialize on the next frame so the CSS transition/animation runs.
    requestAnimationFrame(() => el.classList.add('is-in'));
    return rec;
  }

  // Send the next card to whichever column has fewer, alternating on ties.
  function pickSide() {
    const l = colLeft.childElementCount, r = colRight.childElementCount;
    if (l < r) return 'left';
    if (r < l) return 'right';
    return (seq % 2 === 0) ? 'left' : 'right';
  }

  /* ---- Public: dismiss all ---------------------------------------------- */
  function clear() {
    for (const rec of live.slice()) retire(rec, false);
  }

  function retire(rec, immediate) {
    const idx = live.indexOf(rec);
    if (idx === -1) return;
    live.splice(idx, 1);
    const el = rec.el;
    el.classList.remove('is-in');
    el.classList.add('is-out');
    const remove = () => { if (el.parentNode) el.parentNode.removeChild(el); };
    // Let the dismiss animation play unless we're urgently making room.
    setTimeout(remove, immediate ? 0 : DISMISS_MS);
  }

  /* ---- Public: fetch a page and open a reader panel --------------------- */
  async function openUrl(url) {
    if (!url) return;
    let data;
    try {
      const res = await fetch('/api/fetch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url }),
      });
      if (!res.ok) return;                 // 503 / disabled → degrade silently
      data = await res.json();
    } catch (e) {
      return;                              // offline → silent, never break chat
    }
    if (!data) return;
    data.kind = 'reader';
    if (!data.url) data.url = url;
    add(data);
  }

  /* ======================================================================
     Panel construction
     ====================================================================== */
  function buildPanel(kind, p) {
    const el = document.createElement('div');
    el.className = 'panel panel--' + kind;

    const frame = document.createElement('div');
    frame.className = 'panel__frame';
    el.appendChild(frame);

    // Corner ticks + scanline overlay (pure decoration).
    for (const c of ['tl', 'tr', 'bl', 'br']) {
      const tick = document.createElement('span');
      tick.className = 'panel__tick panel__tick--' + c;
      tick.setAttribute('aria-hidden', 'true');
      frame.appendChild(tick);
    }
    const scan = document.createElement('div');
    scan.className = 'panel__scan';
    scan.setAttribute('aria-hidden', 'true');
    frame.appendChild(scan);

    frame.appendChild(buildTitleBar(kind, p));

    const body = document.createElement('div');
    body.className = 'panel__body';
    if (kind === 'reader')      buildReaderBody(body, p);
    else if (kind === 'image')  buildImageBody(body, p);
    else                        buildSourceBody(body, p);
    frame.appendChild(body);

    return el;
  }

  function buildTitleBar(kind, p) {
    const bar = document.createElement('div');
    bar.className = 'panel__titlebar';

    const label = document.createElement('span');
    label.className = 'panel__label';
    label.textContent = kindLabel(kind);
    bar.appendChild(label);

    const host = document.createElement('span');
    host.className = 'panel__host';
    host.textContent = hostOf(p);
    bar.appendChild(host);

    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'panel__close';
    close.setAttribute('aria-label', 'Dismiss panel');
    close.textContent = '×';           // ×
    close.addEventListener('click', (e) => {
      e.stopPropagation();
      const rec = live.find((r) => r.el.contains(close));
      if (rec) retire(rec, false);
    });
    bar.appendChild(close);

    return bar;
  }

  /* ---- source: compact citation card ------------------------------------ */
  function buildSourceBody(body, p) {
    if (p.image) {
      const thumb = document.createElement('img');
      thumb.className = 'panel__thumb';
      thumb.alt = '';
      thumb.loading = 'lazy';
      thumb.referrerPolicy = 'no-referrer';
      thumb.src = p.image;
      thumb.addEventListener('error', () => { thumb.style.display = 'none'; });
      body.appendChild(thumb);
    }

    const title = document.createElement('div');
    title.className = 'panel__title';
    title.textContent = p.title || p.url || 'Untitled source';
    body.appendChild(title);

    if (p.snippet) {
      const snip = document.createElement('p');
      snip.className = 'panel__snippet';
      snip.textContent = p.snippet;
      body.appendChild(snip);
    }

    const actions = document.createElement('div');
    actions.className = 'panel__actions';
    if (p.url) {
      const view = actionBtn('View', () => openUrl(p.url));
      actions.appendChild(view);
      actions.appendChild(extLink('Open', p.url));
    }
    body.appendChild(actions);
  }

  /* ---- reader: expanded page view --------------------------------------- */
  function buildReaderBody(body, p) {
    const title = document.createElement('div');
    title.className = 'panel__title panel__title--reader';
    title.textContent = p.title || p.url || 'Reader';
    body.appendChild(title);

    // Scrollable cleaned text.
    const scroll = document.createElement('div');
    scroll.className = 'panel__text';
    scroll.tabIndex = 0;
    if (p.text) {
      // Preserve paragraph breaks without trusting markup.
      for (const para of String(p.text).split(/\n{2,}/)) {
        const t = para.trim();
        if (!t) continue;
        const pEl = document.createElement('p');
        pEl.textContent = t;
        scroll.appendChild(pEl);
      }
    } else {
      const pEl = document.createElement('p');
      pEl.className = 'panel__muted';
      pEl.textContent = 'No readable text extracted.';
      scroll.appendChild(pEl);
    }
    body.appendChild(scroll);

    // Image gallery.
    const imgs = Array.isArray(p.images) ? p.images.filter(Boolean) : [];
    if (imgs.length) {
      const gallery = document.createElement('div');
      gallery.className = 'panel__gallery';
      for (const src of imgs.slice(0, 8)) {
        const im = document.createElement('img');
        im.className = 'panel__img';
        im.alt = '';
        im.loading = 'lazy';
        im.referrerPolicy = 'no-referrer';
        im.src = src;
        im.addEventListener('error', () => { im.style.display = 'none'; });
        gallery.appendChild(im);
      }
      body.appendChild(gallery);
    }

    // Live-page toggle (only if the backend says the page allows embedding),
    // otherwise an "Open in browser" link.
    const actions = document.createElement('div');
    actions.className = 'panel__actions';
    if (p.url && p.allow_iframe) {
      let frameEl = null;
      const toggle = actionBtn('Live page', () => {
        if (frameEl) {
          frameEl.remove(); frameEl = null;
          scroll.style.display = '';
          toggle.textContent = 'Live page';
          toggle.setAttribute('aria-pressed', 'false');
          return;
        }
        frameEl = document.createElement('iframe');
        frameEl.className = 'panel__iframe';
        frameEl.setAttribute('sandbox', 'allow-scripts allow-forms allow-popups');
        frameEl.setAttribute('referrerpolicy', 'no-referrer');
        frameEl.setAttribute('loading', 'lazy');
        frameEl.title = p.title || 'Live page';
        frameEl.src = p.url;
        scroll.style.display = 'none';
        body.insertBefore(frameEl, actions);
        toggle.textContent = 'Reader';
        toggle.setAttribute('aria-pressed', 'true');
      });
      toggle.setAttribute('aria-pressed', 'false');
      actions.appendChild(toggle);
      actions.appendChild(extLink('Open', p.url));
    } else if (p.url) {
      actions.appendChild(extLink('Open in browser', p.url));
    }
    if (actions.childElementCount) body.appendChild(actions);
  }

  /* ---- image: tile with caption ----------------------------------------- */
  function buildImageBody(body, p) {
    const src = p.image || p.url;
    if (src) {
      const im = document.createElement('img');
      im.className = 'panel__img panel__img--tile';
      im.alt = p.title || '';
      im.loading = 'lazy';
      im.referrerPolicy = 'no-referrer';
      im.src = src;
      im.addEventListener('error', () => { im.style.display = 'none'; });
      body.appendChild(im);
    }
    if (p.title) {
      const cap = document.createElement('div');
      cap.className = 'panel__caption';
      cap.textContent = p.title;
      body.appendChild(cap);
    }
  }

  /* ---- small builders --------------------------------------------------- */
  function actionBtn(text, onClick) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'panel__btn';
    b.textContent = text;
    b.addEventListener('click', (e) => { e.stopPropagation(); onClick(); });
    return b;
  }

  function extLink(text, url) {
    const a = document.createElement('a');
    a.className = 'panel__btn panel__link';
    a.textContent = text;
    a.href = url;
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    a.addEventListener('pointerdown', (e) => e.stopPropagation());
    return a;
  }

  function kindLabel(kind) {
    if (kind === 'reader') return 'READER — PAGE';
    if (kind === 'image')  return 'IMAGE — PLATE';
    return 'SOURCE — RECORD';
  }

  function hostOf(p) {
    if (p.source) return String(p.source);
    if (p.url) {
      try { return new URL(p.url).hostname.replace(/^www\./, ''); }
      catch (e) { /* fall through */ }
    }
    return 'local';
  }

  /* ======================================================================
     Dragging (pointer events; transform-only so it's compositor-cheap).
     The drag transform lives on `.panel`; the appear/dismiss animation lives
     on the inner `.panel__frame`, so the two never fight over `transform`.
     ====================================================================== */
  function makeDraggable(rec) {
    const el = rec.el;
    const bar = el.querySelector('.panel__titlebar');
    if (!bar) return;
    let dragging = false;
    let startX = 0, startY = 0;
    let baseX = 0, baseY = 0;   // committed offset
    rec.dx = 0; rec.dy = 0;

    const onDown = (e) => {
      // Ignore drags that start on the close button.
      if (e.target.closest('.panel__close')) return;
      dragging = true;
      startX = e.clientX; startY = e.clientY;
      baseX = rec.dx; baseY = rec.dy;
      el.classList.add('is-dragging');
      try { bar.setPointerCapture(e.pointerId); } catch (_) {}
      e.preventDefault();
    };
    const onMove = (e) => {
      if (!dragging) return;
      rec.dx = baseX + (e.clientX - startX);
      rec.dy = baseY + (e.clientY - startY);
      el.style.transform = 'translate(' + rec.dx + 'px,' + rec.dy + 'px)';
    };
    const onUp = (e) => {
      if (!dragging) return;
      dragging = false;
      el.classList.remove('is-dragging');
      try { bar.releasePointerCapture(e.pointerId); } catch (_) {}
    };

    bar.addEventListener('pointerdown', onDown);
    bar.addEventListener('pointermove', onMove);
    bar.addEventListener('pointerup', onUp);
    bar.addEventListener('pointercancel', onUp);
  }

  return { add, clear, openUrl };
}
