/* ==========================================================================
   hologram.js — the VOX holographic face renderer + audio-driven lip-sync.

   Design targets an OLD Intel integrated GPU on Safari (Big Sur), so the hot
   render path uses only Canvas2D drawImage blits (GPU-accelerated) and a
   handful of gradient fills. The expensive work — turning a portrait into a
   translucent cyan hologram with chromatic-aberration channels — happens ONCE
   at load time, not per frame.

   Public interface (consumed by app.js):
     const holo = createHologram(canvasEl);
     holo.start();                 // begin the render loop
     holo.stop();
     await holo.setPortrait(url);  // load a user photo, build holo channels
     holo.setPlaceholder();        // built-in generic stylized face
     holo.speak(analyserNode);     // drive the mouth from live audio amplitude
     holo.stopSpeaking();
     holo.isReady();               // portrait/placeholder prepared?
   ========================================================================== */

export function createHologram(canvas) {
  const ctx = canvas.getContext('2d', { alpha: true });

  // Internal offscreen buffers ------------------------------------------------
  // `face` is the fully-composited static hologram (cyan tint + translucency +
  // baked chromatic aberration). We blit it every frame with cheap transforms.
  const face = document.createElement('canvas');
  const fctx = face.getContext('2d', { alpha: true });

  // Per-color-channel monochrome buffers used to bake chromatic aberration.
  const chR = document.createElement('canvas');
  const chG = document.createElement('canvas');
  const chB = document.createElement('canvas');

  // Logical (CSS) size of the face buffers. Kept modest for Intel GPUs.
  let W = 480, H = 640;

  // Region of the face treated as the mouth/jaw, in normalized [0..1] coords.
  // Tuned for a typical head-and-shoulders portrait; also matches placeholder.
  const MOUTH = { cx: 0.5, cy: 0.72, w: 0.30, h: 0.16, jawTop: 0.66 };
  const EYES  = { cy: 0.44, h: 0.07 };

  // State ---------------------------------------------------------------------
  let ready = false;
  let currentSource = null; // last image/canvas used, so we can re-bake on resize
  let running = false;
  let rafId = 0;
  let t0 = performance.now();

  // Lip-sync
  let analyser = null;
  let timeData = null;     // Uint8Array reused each frame
  let mouthOpen = 0;       // smoothed 0..1 openness actually drawn
  let speaking = false;

  // Idle animation timers
  let nextBlink = 1200 + Math.random() * 3000;
  let blinkClock = 0;
  let blinkPhase = 0;      // 0 = open; >0 = blinking (eased)
  let nextGlitch = 2000 + Math.random() * 4000;
  let glitchClock = 0;
  let glitchAmt = 0;

  const prefersReduced = window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---- Sizing ------------------------------------------------------------ */
  function resize() {
    const rect = canvas.getBoundingClientRect();
    // Cap device-pixel-ratio: on weak GPUs 2x fill-rate is a real cost.
    const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    const cw = Math.max(1, Math.round((rect.width || 360) * dpr));
    const ch = Math.max(1, Math.round((rect.height || 480) * dpr));
    canvas.width = cw;
    canvas.height = ch;

    // Face buffers use a fixed logical resolution capped for performance;
    // we letterbox/scale to the visible canvas each frame.
    W = Math.min(512, cw);
    H = Math.round(W * 4 / 3);
    for (const c of [face, chR, chG, chB]) { c.width = W; c.height = H; }
  }

  /* ---- Turn an arbitrary source image/canvas into holo channels ----------
     For every pixel we compute luminance, then:
       - alpha  ∝ luminance      → dark areas become transparent (translucency,
                                    the classic "you can see through the ghost")
       - channels are pure R / G / B monochrome images. Recombining G+B with
         additive ('lighter') compositing yields cyan; a faint R lifts the
         brightest highlights toward white. Drawing R and B with opposite
         horizontal offsets fakes chromatic aberration for free.                */
  function buildChannels(srcCanvas) {
    currentSource = srcCanvas;
    const tmp = document.createElement('canvas');
    tmp.width = W; tmp.height = H;
    const tctx = tmp.getContext('2d');

    // Fit the source into the buffer with "cover" framing.
    drawCover(tctx, srcCanvas, W, H);

    let img;
    try {
      img = tctx.getImageData(0, 0, W, H);
    } catch (e) {
      // Should not happen for same-origin assets, but never hard-fail.
      return false;
    }
    const s = img.data;

    const rImg = ctxFor(chR).createImageData(W, H);
    const gImg = ctxFor(chG).createImageData(W, H);
    const bImg = ctxFor(chB).createImageData(W, H);
    const r = rImg.data, g = gImg.data, b = bImg.data;

    for (let i = 0; i < s.length; i += 4) {
      const a0 = s[i + 3] / 255;
      // Rec. 601 luma.
      let lum = (0.299 * s[i] + 0.587 * s[i + 1] + 0.114 * s[i + 2]) / 255;
      lum *= a0; // respect source transparency (placeholder uses it)

      // Gamma-ish lift so mid-tones glow more; keeps darks translucent.
      const v = Math.pow(lum, 0.85);
      const alpha = Math.min(255, v * 300) | 0;      // translucency curve
      const bright = Math.min(255, v * 255 * 1.15) | 0;

      // Green + Blue carry the cyan body; Red is a faint highlight tint.
      g[i + 1] = bright;  g[i + 3] = alpha;
      b[i + 2] = bright;  b[i + 3] = alpha;
      r[i]     = bright;  r[i + 3] = Math.min(255, v * 120) | 0;
    }

    ctxFor(chR).putImageData(rImg, 0, 0);
    ctxFor(chG).putImageData(gImg, 0, 0);
    ctxFor(chB).putImageData(bImg, 0, 0);

    compositeFace();
    return true;
  }

  // Recombine the channels into the static hologram `face` buffer, baking a
  // constant chromatic-aberration offset. Done once per portrait load.
  function compositeFace() {
    fctx.clearRect(0, 0, W, H);
    const ca = Math.max(1, Math.round(W * 0.006)); // aberration in px
    fctx.globalCompositeOperation = 'lighter';
    fctx.drawImage(chB, -ca, 0);  // blue fringe left
    fctx.drawImage(chG, 0, 0);    // green centred
    fctx.drawImage(chR, ca, 0);   // red fringe right
    fctx.globalCompositeOperation = 'source-over';
  }

  /* ---- Built-in placeholder face (generic, non-specific) ---------------- */
  // Drawn in grayscale then run through the same holo pipeline, so it matches
  // the real-portrait look. No real person is depicted.
  function drawPlaceholderSource() {
    const c = document.createElement('canvas');
    c.width = W; c.height = H;
    const p = c.getContext('2d');
    p.fillStyle = '#000';
    p.fillRect(0, 0, W, H);

    const cx = W * 0.5, cy = H * 0.46;
    const fw = W * 0.30, fh = H * 0.30;

    // Soft head/face oval (radial so it glows at centre, fades at edges).
    const grad = p.createRadialGradient(cx, cy, fw * 0.2, cx, cy, fh * 1.15);
    grad.addColorStop(0, '#d8d8d8');
    grad.addColorStop(0.55, '#8a8a8a');
    grad.addColorStop(1, '#101010');
    p.fillStyle = grad;
    ellipse(p, cx, cy, fw, fh); p.fill();

    // Neck / shoulders hint.
    p.fillStyle = '#3a3a3a';
    ellipse(p, cx, H * 0.98, W * 0.34, H * 0.20); p.fill();
    p.fillStyle = grad; // re-cover chin
    ellipse(p, cx, cy, fw, fh); p.fill();

    // Brow ridge shadow.
    p.strokeStyle = 'rgba(0,0,0,0.4)';
    p.lineWidth = fh * 0.06;
    p.beginPath();
    p.arc(cx, cy - fh * 0.05, fw * 0.7, Math.PI * 1.15, Math.PI * 1.85);
    p.stroke();

    // Glowing eyes.
    const eyeY = cy - fh * 0.02, eyeDX = fw * 0.42, eyeR = fw * 0.14;
    for (const sx of [-1, 1]) {
      const ex = cx + sx * eyeDX;
      const eg = p.createRadialGradient(ex, eyeY, 0, ex, eyeY, eyeR);
      eg.addColorStop(0, '#ffffff');
      eg.addColorStop(0.6, '#bfbfbf');
      eg.addColorStop(1, '#202020');
      p.fillStyle = eg;
      ellipse(p, ex, eyeY, eyeR, eyeR * 0.7); p.fill();
    }

    // Nose highlight.
    p.fillStyle = 'rgba(200,200,200,0.6)';
    ellipse(p, cx, cy + fh * 0.28, fw * 0.08, fh * 0.16); p.fill();

    // Closed mouth line (the lip-sync will open it).
    p.strokeStyle = 'rgba(210,210,210,0.7)';
    p.lineWidth = Math.max(2, fh * 0.03);
    p.beginPath();
    p.moveTo(cx - fw * 0.34, cy + fh * 0.62);
    p.quadraticCurveTo(cx, cy + fh * 0.70, cx + fw * 0.34, cy + fh * 0.62);
    p.stroke();

    return c;
  }

  /* ---- Public: load a real portrait ------------------------------------- */
  function setPortrait(url) {
    return new Promise((resolve) => {
      const img = new Image();
      // Same-origin local asset; this keeps getImageData untainted.
      img.crossOrigin = 'anonymous';
      img.onload = () => {
        const ok = buildChannels(img);
        if (!ok) { setPlaceholder(); resolve(false); return; }
        ready = true;
        resolve(true);
      };
      img.onerror = () => { setPlaceholder(); resolve(false); };
      img.src = url;
    });
  }

  function setPlaceholder() {
    buildChannels(drawPlaceholderSource());
    ready = true;
  }

  /* ---- Public: lip-sync control ----------------------------------------- */
  function speak(node) {
    analyser = node || null;
    if (analyser) {
      analyser.fftSize = 1024;
      timeData = new Uint8Array(analyser.fftSize);
      speaking = true;
    }
  }
  function stopSpeaking() { speaking = false; analyser = null; }

  /* ---- Amplitude → target mouth openness -------------------------------- */
  function sampleAmplitude() {
    if (!analyser || !timeData) return 0;
    analyser.getByteTimeDomainData(timeData);
    // RMS around the 128 midpoint of the 0..255 time-domain signal.
    let sum = 0;
    for (let i = 0; i < timeData.length; i++) {
      const d = (timeData[i] - 128) / 128;
      sum += d * d;
    }
    const rms = Math.sqrt(sum / timeData.length);
    // Map RMS (~0..0.5 for speech) into 0..1 with a little gain + knee.
    return Math.min(1, Math.max(0, (rms - 0.02) * 4.2));
  }

  /* ---- The render loop --------------------------------------------------- */
  function frame(now) {
    if (!running) return;
    rafId = requestAnimationFrame(frame);
    const dt = Math.min(64, now - (frame._prev || now));
    frame._prev = now;
    const t = (now - t0) / 1000;

    // --- Update lip-sync (attack fast, decay slower → natural, not jittery) --
    const target = speaking ? sampleAmplitude() : 0;
    const k = target > mouthOpen ? 0.55 : 0.18; // attack vs decay
    mouthOpen += (target - mouthOpen) * k;

    // --- Idle blink scheduling ----------------------------------------------
    blinkClock += dt;
    if (blinkPhase > 0) {
      blinkPhase += dt / 150;            // ~150ms blink
      if (blinkPhase >= 1) { blinkPhase = 0; nextBlink = 1600 + Math.random() * 3800; blinkClock = 0; }
    } else if (blinkClock > nextBlink) {
      blinkPhase = 0.0001;
    }
    // 0→1→0 eased shutter amount.
    const blink = blinkPhase > 0 ? Math.sin(blinkPhase * Math.PI) : 0;

    // --- Rare glitch jitter --------------------------------------------------
    glitchClock += dt;
    if (glitchAmt > 0) {
      glitchAmt -= dt / 180;
      if (glitchAmt < 0) glitchAmt = 0;
    } else if (glitchClock > nextGlitch) {
      glitchAmt = 1; glitchClock = 0; nextGlitch = 2600 + Math.random() * 5000;
    }
    const glitch = prefersReduced ? 0 : glitchAmt;

    // --- Composite the frame -------------------------------------------------
    const cw = canvas.width, ch = canvas.height;
    ctx.clearRect(0, 0, cw, ch);
    if (!ready) return;

    // Fit the face buffer into the canvas with "cover".
    const scale = Math.max(cw / W, ch / H);
    const dw = W * scale, dh = H * scale;
    let dx = (cw - dw) / 2;
    let dy = (ch - dh) / 2;

    // Slow float/sway + breathing (also compositor-cheap since it's one blit).
    const floatY = prefersReduced ? 0 : Math.sin(t * 0.9) * ch * 0.012;
    const swayX  = prefersReduced ? 0 : Math.sin(t * 0.6 + 1) * cw * 0.006;
    dy += floatY; dx += swayX;

    // Glitch: horizontal jump + brief RGB split re-blit.
    if (glitch > 0) dx += (Math.random() - 0.5) * glitch * cw * 0.05;

    ctx.save();
    ctx.globalAlpha = 0.92;
    ctx.drawImage(face, dx, dy, dw, dh);

    // Extra chromatic split flash during a glitch (cheap: two offset blits).
    if (glitch > 0.15) {
      ctx.globalCompositeOperation = 'lighter';
      ctx.globalAlpha = 0.25 * glitch;
      const gx = glitch * cw * 0.02;
      ctx.drawImage(chB, dx - gx, dy, dw, dh);
      ctx.drawImage(chR, dx + gx, dy, dw, dh);
      ctx.globalCompositeOperation = 'source-over';
      ctx.globalAlpha = 0.92;
    }

    // --- Mouth / jaw ---------------------------------------------------------
    drawMouth(dx, dy, dw, dh, mouthOpen);

    // --- Blink: dark bars sweeping over the eye band -------------------------
    if (blink > 0.01) {
      const eyeY = dy + dh * EYES.cy;
      const bandH = dh * EYES.h * (0.4 + blink);
      ctx.globalCompositeOperation = 'multiply';
      ctx.fillStyle = 'rgba(2,10,12,' + (0.85 * blink).toFixed(3) + ')';
      ctx.fillRect(dx, eyeY - bandH / 2, dw, bandH);
      ctx.globalCompositeOperation = 'source-over';
    }

    ctx.restore();
  }

  /* ---- Mouth rendering ---------------------------------------------------
     Two combined illusions from a single still portrait:
       1. Jaw drop: re-blit the lower-face slice of the static face, shifted &
          stretched downward proportionally to openness. This physically moves
          the chin/lips down like a hinge.
       2. Inner mouth: carve a dark cavity, then add a growing cyan glow — the
          lit "throat" that reads unmistakably as an open, speaking mouth.
     The hologram's flicker/scanlines hide the seams.                          */
  function drawMouth(dx, dy, dw, dh, open) {
    const mcx = dx + dw * MOUTH.cx;
    const mcy = dy + dh * MOUTH.cy;
    const mw  = dw * MOUTH.w;
    const mh  = dh * MOUTH.h;
    const drop = open * dh * 0.055; // how far the jaw hinges down

    // 1) Jaw slice. Source = lower face of the STATIC buffer (buffer coords).
    if (open > 0.02) {
      const sy = H * MOUTH.jawTop;
      const sh = H - sy;
      const scaleX = dw / W;
      const sdx = dx;                       // dest x aligns with full face
      const sdy = dy + (H * MOUTH.jawTop) * (dh / H);
      const sdw = W * scaleX;
      const sdh = sh * (dh / H) * (1 + open * 0.10);
      ctx.save();
      ctx.globalAlpha = 0.9;
      // Clip to the lower region so the shifted slice can't cover the eyes.
      ctx.beginPath();
      ctx.rect(dx, sdy - dh * 0.01, dw, dh);
      ctx.clip();
      ctx.drawImage(face, 0, sy, W, sh, sdx, sdy + drop, sdw, sdh);
      ctx.restore();
    }

    // 2) Inner mouth cavity (dark) then glow (bright) — scales with openness.
    const openH = mh * (0.12 + open * 0.95);
    const openW = mw * (0.55 + open * 0.35);

    // Dark cavity: subtractive so it reads as a hole in the glow.
    ctx.save();
    ctx.globalCompositeOperation = 'multiply';
    const dark = ctx.createRadialGradient(mcx, mcy + drop, 0, mcx, mcy + drop, openW);
    dark.addColorStop(0, 'rgba(0,0,0,1)');
    dark.addColorStop(0.7, 'rgba(2,14,16,0.8)');
    dark.addColorStop(1, 'rgba(255,255,255,1)'); // multiply by white = no change
    ctx.fillStyle = dark;
    ellipse(ctx, mcx, mcy + drop, openW, openH); ctx.fill();
    ctx.restore();

    // Bright inner glow that grows with amplitude (the lit throat / voice).
    if (open > 0.05) {
      ctx.save();
      ctx.globalCompositeOperation = 'lighter';
      const glow = ctx.createRadialGradient(mcx, mcy + drop, 0, mcx, mcy + drop, openW * 0.85);
      const a = Math.min(0.9, open);
      glow.addColorStop(0, 'rgba(214,255,255,' + (a * 0.9).toFixed(3) + ')');
      glow.addColorStop(0.5, 'rgba(127,246,255,' + (a * 0.5).toFixed(3) + ')');
      glow.addColorStop(1, 'rgba(63,185,201,0)');
      ctx.fillStyle = glow;
      ellipse(ctx, mcx, mcy + drop, openW * 0.8, openH * 0.85); ctx.fill();
      ctx.restore();
    }
  }

  /* ---- Small canvas helpers --------------------------------------------- */
  function ellipse(c, x, y, rx, ry) {
    c.beginPath();
    if (c.ellipse) c.ellipse(x, y, rx, ry, 0, 0, Math.PI * 2);
    else { // very old fallback
      c.save(); c.translate(x, y); c.scale(rx, ry);
      c.arc(0, 0, 1, 0, Math.PI * 2); c.restore();
    }
  }
  function ctxFor(c) { return c.getContext('2d'); }

  // "cover" draw: fill the target, cropping overflow, centred.
  function drawCover(c, src, tw, th) {
    const sw = src.width || src.naturalWidth;
    const sh = src.height || src.naturalHeight;
    const scale = Math.max(tw / sw, th / sh);
    const w = sw * scale, h = sh * scale;
    c.clearRect(0, 0, tw, th);
    c.drawImage(src, (tw - w) / 2, (th - h) / 2, w, h);
  }

  /* ---- Lifecycle --------------------------------------------------------- */
  function start() {
    if (running) return;
    running = true;
    t0 = performance.now();
    rafId = requestAnimationFrame(frame);
  }
  function stop() {
    running = false;
    if (rafId) cancelAnimationFrame(rafId);
  }

  // Debounced resize.
  let rz;
  window.addEventListener('resize', () => {
    clearTimeout(rz);
    rz = setTimeout(() => {
      resize();
      // Channel/face buffers are resolution-specific and were just cleared by
      // resize(); re-bake from the source we last used so the face survives.
      if (currentSource) buildChannels(currentSource);
    }, 200);
  });

  resize();

  return {
    start, stop,
    setPortrait, setPlaceholder,
    speak, stopSpeaking,
    isReady: () => ready,
  };
}
