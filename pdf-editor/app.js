/* Local PDF Editor — everything runs in the browser, offline.
 *
 * Rendering:  pdf.js (legacy/ES5 build, works on Safari 15 / older Chrome)
 * Writing:    pdf-lib
 *
 * Coordinate system used throughout: "base units" = the pdf.js viewport at
 * scale 1, origin top-left, y down. That is the same size as the page in PDF
 * points (with width/height swapped on rotated pages), so it survives zoom
 * changes and converts back to PDF user space exactly via
 * viewport.convertToPdfPoint().
 */
/* global pdfjsLib, PDFLib */
(function () {
'use strict';

var PDFJS = window.pdfjsLib;
PDFJS.GlobalWorkerOptions.workerSrc = 'vendor/pdf.worker.min.js';

// ── Fonts ────────────────────────────────────────────────────────────
// baseline = distance from the top of a CSS line box (line-height 1.2) down to
// the text baseline, in ems. Keeps on-screen text and written text aligned.
var FONTS = {
  helvetica: {
    label: 'Helvetica',
    css: 'Helvetica, Arial, sans-serif',
    baseline: 0.9465,
    pdf: { rr: 'Helvetica', br: 'Helvetica-Bold', ri: 'Helvetica-Oblique', bi: 'Helvetica-BoldOblique' }
  },
  times: {
    label: 'Times',
    css: '"Times New Roman", Times, serif',
    baseline: 0.9375,
    pdf: { rr: 'Times-Roman', br: 'Times-Bold', ri: 'Times-Italic', bi: 'Times-BoldItalic' }
  },
  courier: {
    label: 'Courier',
    css: 'Courier, "Courier New", monospace',
    baseline: 0.8665,
    pdf: { rr: 'Courier', br: 'Courier-Bold', ri: 'Courier-Oblique', bi: 'Courier-BoldOblique' }
  }
};

var LINE_HEIGHT = 1.2;
var MIN_SCALE = 0.25, MAX_SCALE = 4;

// ── State ────────────────────────────────────────────────────────────
var state = {
  pdf: null,           // pdf.js document
  bytes: null,         // Uint8Array of the file as opened
  name: 'document.pdf',
  scale: 1,
  tool: 'select',
  anns: [],
  sel: null,
  nextId: 1,
  pending: null,       // image waiting to be placed: {dataUrl, w, h, kind}
  history: [],
  dirty: false,        // unsaved changes since the last export
  pageBoxes: []        // {el, overlay, canvas, base:{w,h}, rendered, task, dirty}
};

var $ = function (id) { return document.getElementById(id); };
var viewer = $('viewer'), pagesEl = $('pages'), propbar = $('propbar');

// ── Small helpers ────────────────────────────────────────────────────

var statusTimer = null;
function status(msg, isErr, sticky) {
  var el = $('status');
  el.textContent = msg;
  el.className = isErr ? 'err' : '';
  el.hidden = false;
  if (statusTimer) clearTimeout(statusTimer);
  if (!sticky) statusTimer = setTimeout(function () { el.hidden = true; }, isErr ? 7000 : 2600);
}
function hideStatus() { $('status').hidden = true; }

function clamp(v, lo, hi) { return v < lo ? lo : (v > hi ? hi : v); }

function hexToRgb(hex) {
  var m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex || '#000000');
  if (!m) return { r: 0, g: 0, b: 0 };
  return { r: parseInt(m[1], 16) / 255, g: parseInt(m[2], 16) / 255, b: parseInt(m[3], 16) / 255 };
}

function readFile(file) {
  return new Promise(function (res, rej) {
    var fr = new FileReader();
    fr.onload = function () { res(fr.result); };
    fr.onerror = function () { rej(fr.error); };
    fr.readAsArrayBuffer(file);
  });
}

function loadImage(src) {
  return new Promise(function (res, rej) {
    var img = new Image();
    img.onload = function () { res(img); };
    img.onerror = function () { rej(new Error('Could not read that image.')); };
    img.src = src;
  });
}

// ── Opening a document ───────────────────────────────────────────────

$('openBtn').onclick = $('openBtn2').onclick = function () { $('fileInput').click(); };
$('fileInput').onchange = function (e) {
  if (e.target.files && e.target.files[0]) openFile(e.target.files[0]);
  e.target.value = '';
};

['dragenter', 'dragover'].forEach(function (t) {
  viewer.addEventListener(t, function (e) {
    e.preventDefault();
    if (!state.pdf) $('dropzone').classList.add('hot');
  });
});
['dragleave', 'drop'].forEach(function (t) {
  viewer.addEventListener(t, function (e) {
    e.preventDefault();
    $('dropzone').classList.remove('hot');
  });
});
viewer.addEventListener('drop', function (e) {
  var f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
  if (f) openFile(f);
});

async function openFile(file) {
  if (!/\.pdf$/i.test(file.name) && file.type !== 'application/pdf') {
    status('That does not look like a PDF.', true);
    return;
  }
  status('Opening ' + file.name + '…', false, true);
  try {
    var buf = await readFile(file);
    state.bytes = new Uint8Array(buf);
    // pdf.js takes ownership of the buffer it is handed, so give it a copy.
    var doc = await PDFJS.getDocument({
      data: state.bytes.slice(0),
      isEvalSupported: false
    }).promise;

    state.pdf = doc;
    state.name = file.name;
    state.anns = [];
    state.sel = null;
    state.history = [];
    state.dirty = false;
    document.title = file.name + ' — Local PDF Editor';
    $('dropzone').classList.add('hidden');
    $('saveBtn').disabled = false;

    await buildPages();
    fitPage();
    updatePropbar();
    hideStatus();
  } catch (err) {
    console.error(err);
    var msg = String(err && err.message || err);
    if (/password/i.test(msg)) {
      status('That PDF is password-protected. Remove the password first (Preview → Export as PDF).', true, true);
    } else {
      status('Could not open that PDF: ' + msg, true, true);
    }
  }
}

// ── Page layout & rendering ──────────────────────────────────────────

async function buildPages() {
  pagesEl.innerHTML = '';
  state.pageBoxes = [];

  for (var i = 1; i <= state.pdf.numPages; i++) {
    var page = await state.pdf.getPage(i);
    var vp = page.getViewport({ scale: 1 });

    var el = document.createElement('div');
    el.className = 'page';
    el.dataset.page = String(i - 1);

    var canvas = document.createElement('canvas');
    var overlay = document.createElement('div');
    overlay.className = 'overlay';
    var num = document.createElement('div');
    num.className = 'pagenum';
    num.textContent = 'Page ' + i + ' of ' + state.pdf.numPages;

    el.appendChild(canvas);
    el.appendChild(overlay);
    el.appendChild(num);
    pagesEl.appendChild(el);

    state.pageBoxes.push({
      el: el, canvas: canvas, overlay: overlay, page: page,
      base: { w: vp.width, h: vp.height },
      rendered: false, dirty: true, task: null
    });

    attachOverlayHandlers(overlay, i - 1);
  }
  setupObserver();
  updatePageLabel();
}

var observer = null;
function setupObserver() {
  if (observer) observer.disconnect();
  if (typeof IntersectionObserver === 'undefined') {
    state.pageBoxes.forEach(function (_, i) { renderPage(i); });
    return;
  }
  // Render pages a screen ahead of the viewport — keeps a 2014 Mac responsive
  // on long documents instead of rasterising everything up front.
  observer = new IntersectionObserver(function (entries) {
    entries.forEach(function (en) {
      if (en.isIntersecting) renderPage(Number(en.target.dataset.page));
    });
    updatePageLabel();
  }, { root: viewer, rootMargin: '900px 0px' });
  state.pageBoxes.forEach(function (pb) { observer.observe(pb.el); });
}

function applyScale() {
  state.pageBoxes.forEach(function (pb, i) {
    pb.el.style.width = Math.round(pb.base.w * state.scale) + 'px';
    pb.el.style.height = Math.round(pb.base.h * state.scale) + 'px';
    pb.dirty = true;
    if (pb.rendered) renderPage(i);
  });
  $('zoomLabel').textContent = Math.round(state.scale * 100) + '%';
  layoutAnns();
}

function renderPage(i) {
  var pb = state.pageBoxes[i];
  if (!pb || !pb.dirty) return;
  pb.dirty = false;
  pb.rendered = true;

  if (pb.task) { try { pb.task.cancel(); } catch (e) {} pb.task = null; }

  var dpr = Math.min(window.devicePixelRatio || 1, 2);
  var vp = pb.page.getViewport({ scale: state.scale * dpr });
  pb.canvas.width = Math.round(vp.width);
  pb.canvas.height = Math.round(vp.height);

  var ctx = pb.canvas.getContext('2d');
  var task = pb.page.render({ canvasContext: ctx, viewport: vp });
  pb.task = task;
  task.promise.catch(function (e) {
    if (!e || e.name !== 'RenderingCancelledException') console.error(e);
  });
}

// Fit a whole page on screen rather than just its width: when you are signing
// something you want to see the page, and on a Retina Mac fit-to-width alone
// makes a letter page twice as tall as the window.
function fitPage() {
  if (!state.pageBoxes.length) return;
  var b = state.pageBoxes[0].base;
  state.scale = clamp(
    Math.min((viewer.clientWidth - 48) / b.w, (viewer.clientHeight - 44) / b.h),
    MIN_SCALE, MAX_SCALE);
  applyScale();
}

function zoom(mult) {
  state.scale = clamp(state.scale * mult, MIN_SCALE, MAX_SCALE);
  applyScale();
}

$('zoomIn').onclick = function () { zoom(1.2); };
$('zoomOut').onclick = function () { zoom(1 / 1.2); };
$('fitWidth').onclick = fitPage;

var resizeTimer = null;
window.addEventListener('resize', function () {
  if (resizeTimer) clearTimeout(resizeTimer);
  resizeTimer = setTimeout(function () { if (state.pdf) layoutAnns(); }, 150);
});

function updatePageLabel() {
  if (!state.pdf) { $('pageLabel').textContent = '—'; return; }
  var mid = viewer.scrollTop + viewer.clientHeight / 2, cur = 1;
  for (var i = 0; i < state.pageBoxes.length; i++) {
    var el = state.pageBoxes[i].el;
    if (el.offsetTop <= mid) cur = i + 1;
  }
  $('pageLabel').textContent = cur + ' / ' + state.pdf.numPages;
}
viewer.addEventListener('scroll', function () {
  if (state.pdf) updatePageLabel();
});

// ── Tools ────────────────────────────────────────────────────────────

function setTool(t) {
  state.tool = t;
  var btns = document.querySelectorAll('#tools .tool');
  for (var i = 0; i < btns.length; i++) {
    btns[i].classList.toggle('active', btns[i].dataset.tool === t);
  }
  state.pageBoxes.forEach(function (pb) {
    pb.overlay.className = 'overlay t-' + t;
  });
}

document.querySelectorAll('#tools .tool').forEach(function (b) {
  b.onclick = function () {
    var t = b.dataset.tool;
    if (t === 'signature') { setTool('select'); openSigModal(); return; }
    if (t === 'image') { setTool('select'); $('imageInput').click(); return; }
    state.pending = null;
    select(null);
    setTool(t);
  };
});

$('imageInput').onchange = async function (e) {
  var f = e.target.files && e.target.files[0];
  e.target.value = '';
  if (!f) return;
  try {
    var buf = await readFile(f);
    var dataUrl = bytesToDataUrl(new Uint8Array(buf), f.type || 'image/png');
    var img = await loadImage(dataUrl);
    state.pending = { dataUrl: dataUrl, w: img.naturalWidth, h: img.naturalHeight, kind: 'image' };
    setTool('image');
    status('Click on the page to place the image.');
  } catch (err) {
    status(String(err.message || err), true);
  }
};

function bytesToDataUrl(bytes, mime) {
  var CHUNK = 0x8000, out = '';
  for (var i = 0; i < bytes.length; i += CHUNK) {
    out += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK));
  }
  return 'data:' + mime + ';base64,' + btoa(out);
}

// ── Annotation model ─────────────────────────────────────────────────

function pushHistory() {
  state.dirty = true;
  state.history.push(JSON.stringify(state.anns));
  if (state.history.length > 60) state.history.shift();
}

function undo() {
  if (!state.history.length) { status('Nothing to undo.'); return; }
  state.anns = JSON.parse(state.history.pop());
  state.sel = null;
  renderAnns();
  updatePropbar();
}
$('undoBtn').onclick = undo;

function addAnn(a) {
  pushHistory();
  a.id = state.nextId++;
  state.anns.push(a);
  renderAnns();
  select(a.id);
  return a;
}

function getAnn(id) {
  for (var i = 0; i < state.anns.length; i++) if (state.anns[i].id === id) return state.anns[i];
  return null;
}

function deleteAnn(id) {
  pushHistory();
  state.anns = state.anns.filter(function (a) { return a.id !== id; });
  state.sel = null;
  renderAnns();
  updatePropbar();
}

function duplicateAnn(id) {
  var a = getAnn(id);
  if (!a) return;
  var copy = JSON.parse(JSON.stringify(a));
  copy.x += 12; copy.y += 12;
  addAnn(copy);
}

function select(id) {
  state.sel = id;
  var nodes = pagesEl.querySelectorAll('.ann');
  for (var i = 0; i < nodes.length; i++) {
    nodes[i].classList.toggle('selected', Number(nodes[i].dataset.id) === id);
  }
  syncHandles();
  updatePropbar();
}

function syncHandles() {
  var nodes = pagesEl.querySelectorAll('.ann');
  for (var i = 0; i < nodes.length; i++) {
    var node = nodes[i];
    var a = getAnn(Number(node.dataset.id));
    var old = node.querySelector('.handle');
    var want = a && a.type !== 'text' && a.id === state.sel;
    if (want && !old) {
      var h = document.createElement('div');
      h.className = 'handle';
      node.appendChild(h);
    } else if (!want && old) {
      old.parentNode.removeChild(old);
    }
  }
}

// ── Placing annotations ──────────────────────────────────────────────

var suppressMouseDown = false;

function attachOverlayHandlers(overlay, pageIndex) {
  // Stop the browser's default mousedown focus handling after a tool click:
  // it would otherwise pull focus off the text box we just created, and the
  // first character typed would be lost. The flag is set during pointerdown,
  // which always precedes the matching mousedown.
  overlay.addEventListener('mousedown', function (e) {
    if (suppressMouseDown) { e.preventDefault(); suppressMouseDown = false; }
  });

  overlay.addEventListener('pointerdown', function (e) {
    if (e.target !== overlay) return;          // clicks on an annotation bubble up
    var rect = overlay.getBoundingClientRect();
    var x = (e.clientX - rect.left) / state.scale;
    var y = (e.clientY - rect.top) / state.scale;

    if (state.tool === 'select') { select(null); return; }

    if (state.tool === 'text') {
      suppressMouseDown = true;
      var size = lastTextStyle.size;
      var a = addAnn({
        type: 'text', page: pageIndex,
        x: x, y: y - size * FONTS[lastTextStyle.font].baseline,
        text: '', font: lastTextStyle.font, size: size,
        color: lastTextStyle.color, bold: lastTextStyle.bold, italic: lastTextStyle.italic
      });
      setTool('select');
      beginEdit(a.id);
      return;
    }

    if (state.tool === 'check') {
      var s = 18;
      addAnn({ type: 'check', page: pageIndex, x: x - s / 2, y: y - s / 2, w: s, h: s, color: '#101820' });
      setTool('select');
      return;
    }

    if (state.tool === 'box') { startBoxDrag(e, overlay, pageIndex, x, y); return; }

    if ((state.tool === 'image' || state.tool === 'signature') && state.pending) {
      var p = state.pending;
      var w = p.kind === 'signature' ? 170 : Math.min(240, p.w);
      var h = w * (p.h / p.w);
      addAnn({
        type: 'image', page: pageIndex,
        x: x - (p.kind === 'signature' ? 8 : w / 2),
        y: y - (p.kind === 'signature' ? h * 0.78 : h / 2),
        w: w, h: h, dataUrl: p.dataUrl
      });
      state.pending = null;
      setTool('select');
      return;
    }

    if (state.tool === 'image' && !state.pending) $('imageInput').click();
  });
}

function startBoxDrag(e, overlay, pageIndex, x0, y0) {
  e.preventDefault();
  var ghost = document.createElement('div');
  ghost.className = 'ann ann-box';
  ghost.style.opacity = '0.7';
  ghost.style.outline = '1px solid #2f6fd8';
  overlay.appendChild(ghost);
  var rect = overlay.getBoundingClientRect();
  var cur = { x: x0, y: y0, w: 0, h: 0 };

  function move(ev) {
    var x = (ev.clientX - rect.left) / state.scale;
    var y = (ev.clientY - rect.top) / state.scale;
    cur.x = Math.min(x0, x); cur.y = Math.min(y0, y);
    cur.w = Math.abs(x - x0); cur.h = Math.abs(y - y0);
    ghost.style.left = cur.x * state.scale + 'px';
    ghost.style.top = cur.y * state.scale + 'px';
    ghost.style.width = cur.w * state.scale + 'px';
    ghost.style.height = cur.h * state.scale + 'px';
  }
  function up() {
    document.removeEventListener('pointermove', move);
    document.removeEventListener('pointerup', up);
    if (ghost.parentNode) ghost.parentNode.removeChild(ghost);
    if (cur.w < 4 || cur.h < 4) { cur.w = 120; cur.h = 18; }
    addAnn({ type: 'box', page: pageIndex, x: cur.x, y: cur.y, w: cur.w, h: cur.h, color: '#ffffff' });
    setTool('select');
  }
  document.addEventListener('pointermove', move);
  document.addEventListener('pointerup', up);
}

// ── Annotation DOM ───────────────────────────────────────────────────

function renderAnns() {
  state.pageBoxes.forEach(function (pb) { pb.overlay.innerHTML = ''; });
  state.anns.forEach(function (a) {
    var pb = state.pageBoxes[a.page];
    if (!pb) return;
    pb.overlay.appendChild(buildAnnNode(a));
  });
  layoutAnns();
  syncHandles();
}

function buildAnnNode(a) {
  var node = document.createElement('div');
  node.className = 'ann ann-' + a.type + (a.id === state.sel ? ' selected' : '');
  node.dataset.id = String(a.id);

  if (a.type === 'text') {
    node.contentEditable = 'false';
    node.classList.add('ann-text');
    node.textContent = a.text;
    node.addEventListener('dblclick', function () { beginEdit(a.id); });
    node.addEventListener('input', function () {
      state.dirty = true;
      if (editSnapshot) { state.history.push(editSnapshot); editSnapshot = null; }
      a.text = node.innerText.replace(/\u00a0/g, ' ');
    });
    node.addEventListener('paste', function (ev) {
      ev.preventDefault();
      var t = (ev.clipboardData || window.clipboardData).getData('text');
      document.execCommand('insertText', false, t.replace(/\r/g, ''));
    });
    node.addEventListener('blur', function () { endEdit(a.id); });
    node.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape') { ev.preventDefault(); node.blur(); }
    });
  } else if (a.type === 'image') {
    var img = document.createElement('img');
    img.src = a.dataUrl;
    node.appendChild(img);
  } else if (a.type === 'check') {
    node.innerHTML = '<svg viewBox="0 0 100 100" preserveAspectRatio="none">' +
      '<polyline points="10,52 38,80 90,16" fill="none" stroke="' + a.color +
      '" stroke-width="13" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  } else if (a.type === 'box') {
    node.style.background = a.color;
  }

  node.addEventListener('pointerdown', function (ev) {
    if (node.classList.contains('editing')) return;   // let the caret work
    ev.stopPropagation();
    select(a.id);
    if (ev.target.classList.contains('handle')) startResize(ev, a, node);
    else startMove(ev, a, node);
  });

  return node;
}

function layoutAnns() {
  var s = state.scale;
  state.anns.forEach(function (a) {
    var node = pagesEl.querySelector('.ann[data-id="' + a.id + '"]');
    if (!node) return;
    node.style.left = (a.x * s) + 'px';
    node.style.top = (a.y * s) + 'px';
    if (a.type === 'text') {
      var f = FONTS[a.font] || FONTS.helvetica;
      node.style.fontFamily = f.css;
      node.style.fontSize = (a.size * s) + 'px';
      node.style.lineHeight = String(LINE_HEIGHT);
      node.style.color = a.color;
      node.style.fontWeight = a.bold ? '700' : '400';
      node.style.fontStyle = a.italic ? 'italic' : 'normal';
    } else {
      node.style.width = (a.w * s) + 'px';
      node.style.height = (a.h * s) + 'px';
    }
  });
}

// ── Move / resize ────────────────────────────────────────────────────

function startMove(ev, a, node) {
  ev.preventDefault();
  var pb = state.pageBoxes[a.page];
  var startX = ev.clientX, startY = ev.clientY, ox = a.x, oy = a.y, moved = false;

  function move(e) {
    var dx = (e.clientX - startX) / state.scale;
    var dy = (e.clientY - startY) / state.scale;
    if (!moved && Math.abs(dx) + Math.abs(dy) < 1.5) return;
    if (!moved) { pushHistory(); moved = true; }
    a.x = clamp(ox + dx, -40, pb.base.w + 40);
    a.y = clamp(oy + dy, -40, pb.base.h + 40);
    node.style.left = (a.x * state.scale) + 'px';
    node.style.top = (a.y * state.scale) + 'px';
  }
  function up() {
    document.removeEventListener('pointermove', move);
    document.removeEventListener('pointerup', up);
  }
  document.addEventListener('pointermove', move);
  document.addEventListener('pointerup', up);
}

function startResize(ev, a, node) {
  ev.preventDefault();
  ev.stopPropagation();
  var startX = ev.clientX, startY = ev.clientY, ow = a.w, oh = a.h;
  var keepRatio = a.type === 'image' || a.type === 'check';
  var pushed = false;

  function move(e) {
    if (!pushed) { pushHistory(); pushed = true; }
    var dx = (e.clientX - startX) / state.scale;
    var dy = (e.clientY - startY) / state.scale;
    if (keepRatio) {
      var k = Math.max((ow + dx) / ow, (oh + dy) / oh);
      a.w = Math.max(8, ow * k);
      a.h = Math.max(8, oh * k);
    } else {
      a.w = Math.max(4, ow + dx);
      a.h = Math.max(4, oh + dy);
    }
    node.style.width = (a.w * state.scale) + 'px';
    node.style.height = (a.h * state.scale) + 'px';
  }
  function up() {
    document.removeEventListener('pointermove', move);
    document.removeEventListener('pointerup', up);
  }
  document.addEventListener('pointermove', move);
  document.addEventListener('pointerup', up);
}

// ── Text editing ─────────────────────────────────────────────────────

function beginEdit(id) {
  var node = pagesEl.querySelector('.ann[data-id="' + id + '"]');
  var ann = getAnn(id);
  if (!node || !ann) return;
  // Editing existing text takes a snapshot on the first keystroke. A brand new
  // box needs none: addAnn() already recorded the state before it existed, so
  // one undo removes the whole thing rather than blanking it.
  editSnapshot = ann.text ? JSON.stringify(state.anns) : null;
  node.contentEditable = 'true';
  node.classList.add('editing');

  function focusEnd() {
    node.focus();
    var r = document.createRange();
    r.selectNodeContents(node);
    r.collapse(false);
    var sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(r);
  }
  focusEnd();
  // Belt and braces, in case something else grabs focus on the way out.
  setTimeout(function () {
    if (document.activeElement !== node && node.isContentEditable) focusEnd();
  }, 0);
}

function endEdit(id) {
  var node = pagesEl.querySelector('.ann[data-id="' + id + '"]');
  var a = getAnn(id);
  if (!node || !a) return;
  node.contentEditable = 'false';
  node.classList.remove('editing');
  a.text = node.innerText.replace(/\u00a0/g, ' ').replace(/\n$/, '');
  if (!a.text.trim()) {
    state.anns = state.anns.filter(function (x) { return x.id !== id; });
    renderAnns();
    if (state.sel === id) select(null);
  }
}

// ── Property bar ─────────────────────────────────────────────────────

var editSnapshot = null;
var lastTextStyle = { font: 'helvetica', size: 12, color: '#101820', bold: false, italic: false };

function updatePropbar() {
  var a = state.sel != null ? getAnn(state.sel) : null;
  propbar.innerHTML = '';

  function el(tag, cls, txt) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (txt != null) e.textContent = txt;
    return e;
  }

  // The bar stays in the layout whether or not something is selected —
  // showing and hiding it would shift the page under the pointer mid-edit.
  if (!a) {
    propbar.appendChild(el('span', 'hint',
      state.pdf ? 'Pick a tool above, then click on the page. Click anything you have added to change it.'
                : 'Open a PDF to get started.'));
    return;
  }

  if (a.type === 'text') {
    var fl = el('label', null, 'Font');
    var fs = document.createElement('select');
    Object.keys(FONTS).forEach(function (k) {
      var o = document.createElement('option');
      o.value = k; o.textContent = FONTS[k].label;
      if (k === a.font) o.selected = true;
      fs.appendChild(o);
    });
    fs.onchange = function () { pushHistory(); a.font = fs.value; lastTextStyle.font = fs.value; layoutAnns(); };
    fl.appendChild(fs);
    propbar.appendChild(fl);

    var sl = el('label', null, 'Size');
    var si = document.createElement('input');
    si.type = 'number'; si.min = '4'; si.max = '96'; si.step = '1'; si.value = String(a.size);
    si.style.width = '58px';
    si.onchange = si.oninput = function () {
      var v = clamp(parseFloat(si.value) || 12, 4, 96);
      pushHistory(); a.size = v; lastTextStyle.size = v; layoutAnns();
    };
    sl.appendChild(si);
    propbar.appendChild(sl);

    var bb = el('button', 'pbtn' + (a.bold ? ' on' : ''), 'B');
    bb.style.fontWeight = '700';
    bb.onclick = function () { pushHistory(); a.bold = !a.bold; lastTextStyle.bold = a.bold; layoutAnns(); updatePropbar(); };
    propbar.appendChild(bb);

    var ib = el('button', 'pbtn' + (a.italic ? ' on' : ''), 'I');
    ib.style.fontStyle = 'italic';
    ib.onclick = function () { pushHistory(); a.italic = !a.italic; lastTextStyle.italic = a.italic; layoutAnns(); updatePropbar(); };
    propbar.appendChild(ib);
  }

  if (a.type === 'text' || a.type === 'check' || a.type === 'box') {
    var cl = el('label', null, 'Colour');
    var ci = document.createElement('input');
    ci.type = 'color'; ci.value = a.color;
    ci.oninput = function () {
      a.color = ci.value;
      if (a.type === 'text') lastTextStyle.color = ci.value;
      renderAnns(); select(a.id);
    };
    cl.appendChild(ci);
    propbar.appendChild(cl);
  }

  if (a.type !== 'text') {
    var wl = el('label', null, 'Width');
    var wi = document.createElement('input');
    wi.type = 'number'; wi.min = '4'; wi.max = '2000'; wi.step = '1';
    wi.value = String(Math.round(a.w));
    wi.style.width = '68px';
    wi.onchange = function () {
      var v = clamp(parseFloat(wi.value) || a.w, 4, 2000);
      pushHistory();
      if (a.type === 'image' || a.type === 'check') a.h = a.h * (v / a.w);
      a.w = v;
      layoutAnns();
    };
    wl.appendChild(wi);
    propbar.appendChild(wl);
  }

  var dup = el('button', 'pbtn', 'Duplicate');
  dup.onclick = function () { duplicateAnn(a.id); };
  propbar.appendChild(dup);

  var del = el('button', 'pbtn danger', 'Delete');
  del.onclick = function () { deleteAnn(a.id); };
  propbar.appendChild(del);

  propbar.appendChild(el('span', 'hint',
    a.type === 'text' ? 'Double-click the text to edit it. Return starts a new line.'
                      : 'Drag to move, drag the blue corner to resize.'));
}

// ── Keyboard ─────────────────────────────────────────────────────────

document.addEventListener('keydown', function (e) {
  var editing = document.activeElement &&
    (document.activeElement.isContentEditable ||
     /^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement.tagName));

  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 's') {
    e.preventDefault(); savePdf(); return;
  }
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'z') {
    e.preventDefault(); undo(); return;
  }
  if (editing) return;
  if (!sigModal.hidden) {
    if (e.key === 'Escape') closeSigModal();
    return;
  }

  if ((e.key === 'Backspace' || e.key === 'Delete') && state.sel != null) {
    e.preventDefault(); deleteAnn(state.sel); return;
  }
  if (e.key === 'Escape') { select(null); setTool('select'); return; }

  if (!e.metaKey && !e.ctrlKey && !e.altKey) {
    var map = { v: 'select', t: 'text', c: 'check', b: 'box' };
    var k = e.key.toLowerCase();
    if (map[k]) { setTool(map[k]); select(null); }
    else if (k === 's') { openSigModal(); }
    else if (k === 'i') { $('imageInput').click(); }
  }

  // Nudge with the arrow keys.
  if (state.sel != null && /^Arrow/.test(e.key)) {
    var a = getAnn(state.sel);
    if (!a) return;
    e.preventDefault();
    var step = e.shiftKey ? 10 : 1;
    if (e.key === 'ArrowLeft') a.x -= step;
    if (e.key === 'ArrowRight') a.x += step;
    if (e.key === 'ArrowUp') a.y -= step;
    if (e.key === 'ArrowDown') a.y += step;
    layoutAnns();
  }
});

// ── Signature dialog ─────────────────────────────────────────────────

var sigModal = $('sigModal'), sigPad = $('sigPad'), sigCtx = sigPad.getContext('2d');
var sigTab = 'draw', sigDrawn = false, sigUploadUrl = null;

function openSigModal() {
  sigModal.hidden = false;
  sizeSigPad();
  renderSavedSigs();
  if (sigTab === 'type') renderTypedSig();
}
function closeSigModal() { sigModal.hidden = true; }

$('sigClose').onclick = $('sigCancel').onclick = closeSigModal;
sigModal.addEventListener('pointerdown', function (e) {
  if (e.target === sigModal) closeSigModal();
});

document.querySelectorAll('#sigModal .tab').forEach(function (t) {
  t.onclick = function () {
    sigTab = t.dataset.tab;
    document.querySelectorAll('#sigModal .tab').forEach(function (x) {
      x.classList.toggle('active', x === t);
    });
    document.querySelectorAll('#sigModal .tabpane').forEach(function (p) {
      p.hidden = p.dataset.pane !== sigTab;
    });
    if (sigTab === 'draw') sizeSigPad();
    if (sigTab === 'type') renderTypedSig();
  };
});

function sizeSigPad() {
  var dpr = Math.min(window.devicePixelRatio || 1, 2);
  var w = sigPad.clientWidth || 760, h = 240;
  if (sigPad.width === Math.round(w * dpr) && sigDrawn) return;
  sigPad.width = Math.round(w * dpr);
  sigPad.height = Math.round(h * dpr);
  sigCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
  sigCtx.clearRect(0, 0, w, h);
  sigDrawn = false;
}

(function initPad() {
  var drawing = false, last = null;

  function pt(e) {
    var r = sigPad.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  }
  sigPad.addEventListener('pointerdown', function (e) {
    e.preventDefault();
    if (sigPad.setPointerCapture) { try { sigPad.setPointerCapture(e.pointerId); } catch (err) {} }
    drawing = true;
    last = pt(e);
    sigCtx.lineCap = 'round';
    sigCtx.lineJoin = 'round';
    sigCtx.strokeStyle = $('sigColor').value;
    sigCtx.lineWidth = parseFloat($('penSize').value);
    // A dot, so a tap still leaves a mark.
    sigCtx.beginPath();
    sigCtx.arc(last.x, last.y, sigCtx.lineWidth / 2, 0, Math.PI * 2);
    sigCtx.fillStyle = $('sigColor').value;
    sigCtx.fill();
    sigDrawn = true;
    document.querySelector('.sig-hint').style.display = 'none';
  });
  sigPad.addEventListener('pointermove', function (e) {
    if (!drawing) return;
    e.preventDefault();
    var p = pt(e);
    sigCtx.beginPath();
    sigCtx.moveTo(last.x, last.y);
    // Quadratic through the midpoint smooths out trackpad jitter.
    var mid = { x: (last.x + p.x) / 2, y: (last.y + p.y) / 2 };
    sigCtx.quadraticCurveTo(last.x, last.y, mid.x, mid.y);
    sigCtx.stroke();
    last = p;
  });
  ['pointerup', 'pointercancel', 'pointerleave'].forEach(function (t) {
    sigPad.addEventListener(t, function () { drawing = false; });
  });
})();

$('sigClear').onclick = function () {
  sigCtx.clearRect(0, 0, sigPad.width, sigPad.height);
  sigDrawn = false;
  document.querySelector('.sig-hint').style.display = '';
};

$('sigTypeText').oninput = renderTypedSig;
$('sigTypeFont').onchange = renderTypedSig;
$('sigTypeColor').onchange = renderTypedSig;

// Typed signatures are rasterised with a macOS system script font — PDF's
// built-in fonts have nothing handwriting-like, and embedding a font file
// would mean shipping one.
function typedSigCanvas() {
  var text = $('sigTypeText').value;
  if (!text.trim()) return null;
  var font = $('sigTypeFont').value;
  var color = $('sigTypeColor').value;
  var size = 130;                       // rasterise big, place small
  var c = document.createElement('canvas');
  var ctx = c.getContext('2d');
  ctx.font = size + 'px ' + font;
  var w = Math.ceil(ctx.measureText(text).width) + size;
  c.width = Math.max(40, w);
  c.height = Math.round(size * 2.1);
  ctx = c.getContext('2d');
  ctx.font = size + 'px ' + font;
  ctx.fillStyle = color;
  ctx.textBaseline = 'alphabetic';
  ctx.fillText(text, size / 2, size * 1.35);
  return c;
}

function renderTypedSig() {
  var box = $('sigTypePreview');
  var c = typedSigCanvas();
  box.innerHTML = '';
  if (!c) {
    box.innerHTML = '<span class="placeholder">Your signature appears here</span>';
    return;
  }
  var t = trimCanvas(c);
  var img = new Image();
  img.src = t.toDataURL('image/png');
  box.appendChild(img);
}

$('sigUpload').onchange = async function (e) {
  var f = e.target.files && e.target.files[0];
  if (!f) return;
  try {
    var buf = await readFile(f);
    var img = await loadImage(bytesToDataUrl(new Uint8Array(buf), f.type || 'image/png'));
    var c = document.createElement('canvas');
    c.width = img.naturalWidth; c.height = img.naturalHeight;
    c.getContext('2d').drawImage(img, 0, 0);
    if ($('sigRemoveBg').checked) removeWhite(c);
    sigUploadUrl = trimCanvas(c).toDataURL('image/png');
    var box = $('sigUploadPreview');
    box.innerHTML = '';
    var prev = new Image();
    prev.src = sigUploadUrl;
    box.appendChild(prev);
  } catch (err) {
    status(String(err.message || err), true);
  }
};
$('sigRemoveBg').onchange = function () {
  if ($('sigUpload').files && $('sigUpload').files[0]) $('sigUpload').onchange({ target: $('sigUpload') });
};

// Knock out the paper behind a photographed signature: fully transparent above
// the light threshold, feathered below it so strokes keep their edges.
function removeWhite(canvas) {
  var ctx = canvas.getContext('2d');
  var d = ctx.getImageData(0, 0, canvas.width, canvas.height);
  var p = d.data;
  for (var i = 0; i < p.length; i += 4) {
    var lum = 0.299 * p[i] + 0.587 * p[i + 1] + 0.114 * p[i + 2];
    if (lum > 210) {
      p[i + 3] = 0;
    } else if (lum > 120) {
      p[i + 3] = Math.round(p[i + 3] * (210 - lum) / 90);
    }
  }
  ctx.putImageData(d, 0, 0);
}

function trimCanvas(canvas) {
  var ctx = canvas.getContext('2d');
  var w = canvas.width, h = canvas.height;
  var d = ctx.getImageData(0, 0, w, h).data;
  var minX = w, minY = h, maxX = -1, maxY = -1;
  for (var y = 0; y < h; y++) {
    for (var x = 0; x < w; x++) {
      if (d[(y * w + x) * 4 + 3] > 8) {
        if (x < minX) minX = x;
        if (x > maxX) maxX = x;
        if (y < minY) minY = y;
        if (y > maxY) maxY = y;
      }
    }
  }
  if (maxX < 0) return canvas;
  var pad = 6;
  minX = Math.max(0, minX - pad); minY = Math.max(0, minY - pad);
  maxX = Math.min(w - 1, maxX + pad); maxY = Math.min(h - 1, maxY + pad);
  var out = document.createElement('canvas');
  out.width = maxX - minX + 1;
  out.height = maxY - minY + 1;
  out.getContext('2d').drawImage(canvas, minX, minY, out.width, out.height, 0, 0, out.width, out.height);
  return out;
}

$('sigUse').onclick = async function () {
  var dataUrl = null;
  if (sigTab === 'draw') {
    if (!sigDrawn) { status('Draw your signature first.', true); return; }
    dataUrl = trimCanvas(sigPad).toDataURL('image/png');
  } else if (sigTab === 'type') {
    var c = typedSigCanvas();
    if (!c) { status('Type your name first.', true); return; }
    dataUrl = trimCanvas(c).toDataURL('image/png');
  } else {
    if (!sigUploadUrl) { status('Choose an image first.', true); return; }
    dataUrl = sigUploadUrl;
  }
  if ($('sigRemember').checked) saveSignature(dataUrl);
  await useSignature(dataUrl);
};

async function useSignature(dataUrl) {
  var img = await loadImage(dataUrl);
  state.pending = { dataUrl: dataUrl, w: img.naturalWidth, h: img.naturalHeight, kind: 'signature' };
  closeSigModal();
  setTool('signature');
  state.pageBoxes.forEach(function (pb) { pb.overlay.className = 'overlay t-signature'; });
  status('Click where the signature should go.');
}

// ── Saved signatures (localStorage; stays on this Mac) ───────────────

var LS_KEY = 'localPdfEditor.signatures.v1';

function loadSignatures() {
  try { return JSON.parse(localStorage.getItem(LS_KEY) || '[]'); } catch (e) { return []; }
}
function saveSignature(dataUrl) {
  try {
    var list = loadSignatures();
    if (list.indexOf(dataUrl) === -1) list.unshift(dataUrl);
    localStorage.setItem(LS_KEY, JSON.stringify(list.slice(0, 6)));
  } catch (e) { /* private browsing / quota — not worth interrupting for */ }
}
function renderSavedSigs() {
  var list = loadSignatures();
  var wrap = $('sigSaved'), box = $('sigSavedList');
  wrap.hidden = list.length === 0;
  box.innerHTML = '';
  list.forEach(function (url, i) {
    var item = document.createElement('div');
    item.className = 'saved-item';
    var pick = document.createElement('button');
    pick.className = 'pick';
    var img = new Image();
    img.src = url;
    pick.appendChild(img);
    pick.onclick = function () { useSignature(url); };
    var del = document.createElement('button');
    del.className = 'del';
    del.textContent = '✕';
    del.title = 'Forget this signature';
    del.onclick = function (ev) {
      ev.stopPropagation();
      var l = loadSignatures();
      l.splice(i, 1);
      try { localStorage.setItem(LS_KEY, JSON.stringify(l)); } catch (e) {}
      renderSavedSigs();
    };
    item.appendChild(pick);
    item.appendChild(del);
    box.appendChild(item);
  });
}

// ── Saving the PDF ───────────────────────────────────────────────────

$('saveBtn').onclick = savePdf;

async function savePdf() {
  if (!state.pdf) return;
  if (state.sel != null) {
    var node = pagesEl.querySelector('.ann[data-id="' + state.sel + '"]');
    if (node && node.classList.contains('editing')) node.blur();
  }
  status('Writing PDF…', false, true);

  try {
    var L = window.PDFLib;
    var out = await L.PDFDocument.load(state.bytes.slice(0).buffer, {
      ignoreEncryption: true,
      updateMetadata: false
    });

    if ($('flattenForms').checked) {
      try {
        var form = out.getForm();
        if (form.getFields().length) form.flatten();
      } catch (e) {
        console.warn('Could not flatten form fields:', e);
        status('Saved, but the form fields could not be flattened.', true);
      }
    }

    var fontCache = {};
    async function font(name) {
      if (!fontCache[name]) fontCache[name] = await out.embedFont(name);
      return fontCache[name];
    }
    var imgCache = {};
    async function image(dataUrl) {
      if (!imgCache[dataUrl]) {
        var bin = dataUrlToBytes(dataUrl);
        imgCache[dataUrl] = /^data:image\/(jpeg|jpg)/i.test(dataUrl)
          ? await out.embedJpg(bin)
          : await out.embedPng(bin);
      }
      return imgCache[dataUrl];
    }

    var pages = out.getPages();
    var byPage = {};
    state.anns.forEach(function (a) {
      (byPage[a.page] = byPage[a.page] || []).push(a);
    });

    for (var pi = 0; pi < state.pageBoxes.length; pi++) {
      var list = byPage[pi];
      if (!list || !list.length) continue;

      var page = pages[pi];
      if (!page) continue;

      // Map viewport (screen) space back to PDF user space. Using pdf.js's own
      // viewport keeps /Rotate, non-zero origins and odd MediaBoxes correct.
      var vp = state.pageBoxes[pi].page.getViewport({ scale: 1 });
      var toPdf = function (x, y) {
        var p = vp.convertToPdfPoint(x, y);
        return { x: p[0], y: p[1] };
      };
      // Direction that "one unit to the right on screen" points in user space.
      var o = toPdf(0, 0), rx = toPdf(1, 0);
      var dx = rx.x - o.x, dy = rx.y - o.y;
      var unit = Math.sqrt(dx * dx + dy * dy) || 1;
      var angle = Math.atan2(dy, dx) * 180 / Math.PI;
      var rot = L.degrees(angle);

      for (var ai = 0; ai < list.length; ai++) {
        var a = list[ai];

        if (a.type === 'text') {
          if (!a.text.trim()) continue;
          await drawTextAnn(a, page, toPdf, rot, unit, font, image, L);

        } else if (a.type === 'image') {
          var im = await image(a.dataUrl);
          var bl = toPdf(a.x, a.y + a.h);
          page.drawImage(im, {
            x: bl.x, y: bl.y,
            width: a.w * unit, height: a.h * unit,
            rotate: rot
          });

        } else if (a.type === 'box') {
          var b = toPdf(a.x, a.y + a.h);
          var c = hexToRgb(a.color);
          page.drawRectangle({
            x: b.x, y: b.y,
            width: a.w * unit, height: a.h * unit,
            color: L.rgb(c.r, c.g, c.b),
            rotate: rot,
            borderWidth: 0
          });

        } else if (a.type === 'check') {
          // Same three points as the on-screen SVG polyline, in page space.
          var pts = [[0.10, 0.52], [0.38, 0.80], [0.90, 0.16]].map(function (p) {
            return toPdf(a.x + p[0] * a.w, a.y + p[1] * a.h);
          });
          var cc = hexToRgb(a.color);
          var thickness = Math.max(1, a.w * 0.13 * unit);
          for (var s = 0; s < 2; s++) {
            page.drawLine({
              start: { x: pts[s].x, y: pts[s].y },
              end: { x: pts[s + 1].x, y: pts[s + 1].y },
              thickness: thickness,
              color: L.rgb(cc.r, cc.g, cc.b),
              lineCap: L.LineCapStyle.Round
            });
          }
        }
      }
    }

    var bytes = await out.save();
    state.dirty = false;
    download(bytes, suggestName(state.name));
    status('Saved. Check your Downloads folder.');
  } catch (err) {
    console.error(err);
    status('Could not save: ' + (err && err.message || err), true, true);
  }
}

async function drawTextAnn(a, page, toPdf, rot, unit, font, image, L) {
  var f = FONTS[a.font] || FONTS.helvetica;
  var key = (a.bold ? 'b' : 'r') + (a.italic ? 'i' : 'r');
  var pdfFont = await font(f.pdf[key]);
  var color = hexToRgb(a.color);
  var lines = a.text.split('\n');

  // The standard PDF fonts are WinAnsi-only. If the text has something they
  // can't encode (emoji, curly quotes from another app, accents outside
  // Latin-1…), fall back to rasterising the text box so nothing is lost.
  var encodable = true;
  try {
    lines.forEach(function (ln) { if (ln) pdfFont.encodeText(ln); });
  } catch (e) {
    encodable = false;
  }

  if (!encodable) {
    var raster = rasterizeText(a, f);
    var im = await image(raster.dataUrl);
    var bl = toPdf(a.x, a.y + raster.h);
    page.drawImage(im, { x: bl.x, y: bl.y, width: raster.w * unit, height: raster.h * unit, rotate: rot });
    return;
  }

  for (var i = 0; i < lines.length; i++) {
    if (!lines[i]) continue;
    var baselineY = a.y + i * a.size * LINE_HEIGHT + a.size * f.baseline;
    var p = toPdf(a.x, baselineY);
    page.drawText(lines[i], {
      x: p.x, y: p.y,
      size: a.size * unit,
      font: pdfFont,
      color: L.rgb(color.r, color.g, color.b),
      rotate: rot
    });
  }
}

function rasterizeText(a, f) {
  var SS = 4;                                     // supersample for crisp glyphs
  var lines = a.text.split('\n');
  var probe = document.createElement('canvas').getContext('2d');
  var cssFont = (a.italic ? 'italic ' : '') + (a.bold ? '700 ' : '') + (a.size * SS) + 'px ' + f.css;
  probe.font = cssFont;
  var w = 1;
  lines.forEach(function (ln) { w = Math.max(w, probe.measureText(ln).width); });

  var c = document.createElement('canvas');
  c.width = Math.ceil(w) + SS * 2;
  c.height = Math.ceil(lines.length * a.size * LINE_HEIGHT * SS);
  var ctx = c.getContext('2d');
  ctx.font = cssFont;
  ctx.fillStyle = a.color;
  ctx.textBaseline = 'alphabetic';
  lines.forEach(function (ln, i) {
    ctx.fillText(ln, 0, (i * a.size * LINE_HEIGHT + a.size * f.baseline) * SS);
  });
  return { dataUrl: c.toDataURL('image/png'), w: c.width / SS, h: c.height / SS };
}

function dataUrlToBytes(dataUrl) {
  var bin = atob(dataUrl.split(',')[1]);
  var out = new Uint8Array(bin.length);
  for (var i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

function suggestName(name) {
  return name.replace(/\.pdf$/i, '') + '-signed.pdf';
}

function download(bytes, filename) {
  var blob = new Blob([bytes], { type: 'application/pdf' });
  var url = URL.createObjectURL(blob);
  var a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  setTimeout(function () {
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, 4000);
}

// ── Leave-page guard ─────────────────────────────────────────────────

window.addEventListener('beforeunload', function (e) {
  if (state.dirty && state.anns.length) {
    e.preventDefault();
    e.returnValue = '';
  }
});

// ── Boot ─────────────────────────────────────────────────────────────

setTool('select');
renderSavedSigs();
updatePropbar();

if (location.protocol === 'file:') {
  // pdf.js falls back to running its worker on the main thread here, which
  // works but is slower. The launcher script serves over localhost instead.
  console.info('Running from file:// — for best performance use "Open PDF Editor.command".');
}

})();
