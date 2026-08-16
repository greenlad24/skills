package com.stagemix.app.ui

import androidx.compose.animation.core.FastOutLinearInEasing
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.LinearOutSlowInEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween

/**
 * How this app is allowed to move.
 *
 * One vocabulary for the whole screen, because motion in a room where
 * people are playing music has to mean something. Two rules:
 *
 *  1. ORDINARY MOTION NEVER LOOKS URGENT. Everything here is critically
 *     damped — no overshoot, ever. A fader readout that bounces past its
 *     value and comes back implies the app overshot the mix, which is
 *     the one thing it must never look like it is doing.
 *
 *  2. THE ALARM IS THE ONLY THING THAT REPEATS. Exactly one
 *     infiniteRepeatable exists in this app. If something on screen is
 *     pulsing, it is feedback or a fault, and the operator can learn
 *     that in one night.
 *
 * Clocks are never eased. A countdown that slows down as it approaches
 * zero is a countdown that lies.
 */
object Motion {
    /** a fader readout catching up with a move the engine has made */
    val FaderMove = spring<Float>(
        dampingRatio = Spring.DampingRatioNoBouncy, stiffness = 140f)

    /** a state word, a badge, a colour: quick, but not a snap */
    val StateChange = tween<Float>(220, easing = FastOutSlowInEasing)

    /** something new on the stage */
    val Arrive = tween<Float>(400, easing = LinearOutSlowInEasing)
    val Leave = tween<Float>(260, easing = FastOutLinearInEasing)

    /** anything with a deadline: linear, always */
    val Countdown = tween<Float>(1000, easing = LinearEasing)

    /** panels and overlays */
    val Fade = tween<Float>(180, easing = LinearEasing)

    /**
     * Meter ballistics, in dB per second. Not an animation — a meter
     * rises instantly and falls at a fixed rate, the way every meter
     * ever built behaves, so that what the eye reads is the envelope of
     * the music and not the frame rate of the tablet.
     */
    const val METER_FALL_DB_PER_S = 20f
    const val PEAK_FALL_DB_PER_S = 6f

    /** THE alarm. The only repeating animation in the app. */
    val Alarm = infiniteRepeatable<Float>(
        animation = tween(360, easing = LinearEasing),
        repeatMode = RepeatMode.Reverse)
}

/**
 * The levels, at the rate they actually arrive.
 *
 * Deliberately NOT Compose state. Meters arrive twenty times a second;
 * putting them in the strip model meant sixteen strips and a hundred
 * text nodes recomposed every time a drummer hit something, for four
 * hours. The network loop writes here, the draw phase reads here, and
 * composition never hears about it at all.
 */
object Levels {
    const val N = 16
    val db = FloatArray(N) { -128f }

    @Volatile
    var seq = 0
        private set

    fun publish(v: FloatArray) {
        val n = minOf(v.size, N)
        for (i in 0 until n) db[i] = v[i]
        seq++
    }
}

/**
 * The shape of each channel, for the little spectrum under each strip.
 *
 * Same reasoning as [Levels]: this is a picture, it changes constantly,
 * and it has no business in the strip model where it would recompose
 * text nodes for a living. Twenty-four bands is all a strip that wide
 * can show, folded down from the console's hundred-bin analyzer.
 */
object Spectra {
    const val BANDS = 24
    val band = Array(Levels.N) { FloatArray(BANDS) { -60f } }

    /** fold a 100-bin RTA-derived shape into what a strip can draw */
    fun publish(ch: Int, bins: FloatArray) {
        if (ch !in 0 until Levels.N) return
        val out = band[ch]
        val per = bins.size.toFloat() / BANDS
        for (b in 0 until BANDS) {
            var peak = -120f
            var i = (b * per).toInt()
            val end = ((b + 1) * per).toInt().coerceAtMost(bins.size)
            while (i < end) { if (bins[i] > peak) peak = bins[i]; i++ }
            // ease it, so a strip does not flicker with the music
            out[b] = out[b] + 0.25f * (peak - out[b])
        }
    }
}

/**
 * Something the app is doing that has a KNOWN END.
 *
 * Every long-running state in this engine has a deadline — the twenty
 * seconds it listens before leading, the ten-minute window in which it
 * may set up a channel's processing, the thirty seconds an error must
 * persist before a fader moves, the eight seconds it spends sweeping
 * the stage for a howl, the two minutes it keeps its hands off a
 * channel you touched. None of them is a spinner, and none of them
 * should ever be drawn as one: a bar that fills toward a number of
 * seconds is the difference between "it is thinking" and "it is stuck".
 *
 * @param endsAtMs on the monotonic clock, so a phase survives the
 *        tablet's wall clock being corrected mid-show.
 */
data class Phase(
    val key: String,
    /** what it is doing, in the operator's language */
    val label: String,
    /** and why, in one short clause */
    val why: String,
    val startedAtMs: Long,
    val endsAtMs: Long,
    /** null for the whole stage, or the channel this belongs to */
    val channel: Int? = null,
    val alarm: Boolean = false,
)
