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

/**
 * coerceIn, made total. Two inputs it must survive that plain coerceIn
 * does not:
 *  · a non-finite value (NaN/Infinity) — lands on [lo] instead of passing
 *    through, since NaN fails every comparison;
 *  · an INVERTED range, hi < lo — coerceIn throws
 *    "Cannot coerce value to an empty range" on it, and that is exactly
 *    what took the app down: a strip drawn on a zero-height Canvas frame
 *    computes clampFinite(6f, h-6f) with h≈0, i.e. coerceIn(6f, -6f).
 *    A degenerate range has one point; return it ([lo]) rather than throw.
 */
fun Float.clampFinite(lo: Float, hi: Float): Float {
    if (!isFinite()) return lo
    if (hi <= lo) return lo
    return coerceIn(lo, hi)
}
