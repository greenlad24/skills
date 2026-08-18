package com.stagemix.app

/**
 * NaN AND INFINITY ARE THE ONE INPUT A CANVAS COORDINATE MUST NEVER SEE.
 *
 * Compose draws through Skia, and Skia crashes the WHOLE PROCESS natively
 * on a non-finite vertex — no Java exception, no ANR dialog, the app just
 * vanishes. That is exactly the failure the boot log caught: the app dies
 * at takeover, the instant the strips first render live values from a
 * real desk, with no crash trace of any kind.
 *
 * `coerceIn` does NOT protect against it: NaN fails both the `<` and `>`
 * comparisons, so `NaN.coerceIn(0f, 1f)` returns NaN unchanged, straight
 * into the draw. These do protect against it, and are applied both where
 * the engine's numbers become UI state (so nothing bad ever propagates)
 * and at the draw sites themselves (so nothing bad is ever plotted).
 *
 * The engine's synthetic demo values are always finite, which is why CI
 * never saw this and a real MR18 did.
 */
fun Float.finite(fallback: Float = 0f): Float = if (isFinite()) this else fallback

/** coerceIn, but a non-finite value lands on [lo] instead of passing through */
fun Float.clampFinite(lo: Float, hi: Float): Float =
    if (isFinite()) coerceIn(lo, hi) else lo
