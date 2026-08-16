package com.stagemix.engine

/**
 * X-Air / X32 fader float<->dB law (piecewise linear, from Patrick-Gilles
 * Maillot's unofficial protocol docs; identical in every known client).
 * Float range 0..1 maps to -oo..+10 dB; we treat -90 dB as -oo.
 */
object FaderLaw {
    const val MIN_DB = -90f
    const val MAX_DB = 10f

    fun floatToDb(f: Float): Float {
        // NaN IS NOT SILENT-DROPPED BY coerceIn. Kotlin's coerceIn is a
        // pair of `<`/`>` comparisons, both false for NaN, so a NaN
        // sails through and every `when` branch below is false too —
        // the result is NaN, which then poisons whatever engine state
        // reads it (a NaN OSC value off the wire reached operatorOverride
        // this way). Treat a non-finite input as fully down: silent is
        // the safe reading of a garbage level.
        if (!f.isFinite()) return MIN_DB
        val x = f.coerceIn(0f, 1f)
        return when {
            x >= 0.5f -> x * 40f - 30f
            x >= 0.25f -> x * 80f - 50f
            x >= 0.0625f -> x * 160f - 70f
            else -> x * 480f - 90f
        }
    }

    fun dbToFloat(db: Float): Float {
        // Same guard on the WRITE side: a NaN dB must never become a NaN
        // fader float sent to the desk. Fully down.
        if (!db.isFinite()) return 0f
        val d = db.coerceIn(MIN_DB, MAX_DB)
        return when {
            d >= -10f -> (d + 30f) / 40f
            d >= -30f -> (d + 50f) / 80f
            d >= -60f -> (d + 70f) / 160f
            else -> (d + 90f) / 480f
        }.coerceIn(0f, 1f)
    }
}
