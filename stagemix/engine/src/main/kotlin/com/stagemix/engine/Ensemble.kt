package com.stagemix.engine

import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sqrt

/**
 * What the channels are doing TO EACH OTHER.
 *
 * Everything the app knew about a channel until now came from that
 * channel alone — its average spectrum and the shape of its envelope —
 * and that tops out at four families. It cannot tell a kick from a
 * bass, because both are energy under 200 Hz with no top. It cannot
 * tell a saxophone from a singer, because both are a moving melody in
 * the voice band. No amount of care with one channel's numbers fixes
 * either, and the operator's verdict on the result was fair: it did not
 * know what was plugged in.
 *
 * But the sixteen meters do not arrive one at a time. They arrive
 * TOGETHER, twenty times a second, and what a channel does relative to
 * the other fifteen is a far richer description than anything it does
 * on its own:
 *
 *  · A drum kit fires together. Kick, snare, overheads and congas all
 *    land on the same grid, within a few tens of milliseconds of each
 *    other, all night. Nothing else on stage does that.
 *  · The overheads hear the WHOLE kit, so they coincide with every
 *    other drum channel — which is what makes them overheads rather
 *    than another drum.
 *  · A bass locks to the kick but sustains between hits; a kick is a
 *    hit and then nothing.
 *  · Two piano channels are one piano: their envelopes are the same
 *    curve twice, and no two separate instruments ever are.
 *  · A singer sings in most songs. A saxophone plays in a few, and
 *    when it plays it plays in bursts. Over one song those look alike;
 *    over a set they could not be less alike.
 *
 * So this measures the relationships, and [InstrumentId] uses them
 * alongside the spectrum to name actual instruments rather than
 * families. None of it involves the channel's name.
 */
class Ensemble(private val channels: Int = 16) {

    /** an onset ring: one bit per channel per meter frame */
    private val frames = IntArray(WINDOW)
    private var head = 0
    private var filled = 0

    /** pairwise onset coincidence, decayed */
    private val coin = Array(channels) { FloatArray(channels) }
    private val onsetsOf = FloatArray(channels)

    /** envelope history for pair detection */
    private val env = Array(channels) { FloatArray(PAIR_WINDOW) }
    private var envHead = 0
    private var envFilled = 0

    private val lastDb = FloatArray(channels) { -128f }
    private val wasUp = BooleanArray(channels)

    /** cumulative seconds playing / total, since the set began */
    private val playedSec = DoubleArray(channels)
    private var totalSec = 0.0

    /** per-window duty, for burstiness */
    private val winDuty = Array(channels) { ArrayDeque<Float>() }
    private val winActive = IntArray(channels)
    private var winFrames = 0

    /**
     * One meter frame: every channel's pre-fader level, and whether the
     * gate says it is playing.
     */
    fun onFrame(levels: FloatArray, active: BooleanArray, dtSec: Float) {
        totalSec += dtSec.toDouble()
        var mask = 0
        for (ch in 0 until min(channels, levels.size)) {
            val db = levels[ch]
            if (db.isNaN() || db.isInfinite()) continue
            val on = ch < active.size && active[ch]
            if (on) { playedSec[ch] += dtSec.toDouble(); winActive[ch]++ }
            val d = db - lastDb[ch]
            // The same onset test the per-channel print uses, so "an
            // onset" means one thing in both places: a real step up
            // after not already rising.
            if (on && d >= ONSET_DB && !wasUp[ch]) mask = mask or (1 shl ch)
            wasUp[ch] = d >= 1f
            lastDb[ch] = db

            env[ch][envHead] = if (on) db else -128f
        }
        envHead = (envHead + 1) % PAIR_WINDOW
        if (envFilled < PAIR_WINDOW) envFilled++

        // Smear each onset over a few frames before storing it. Two
        // players hitting "together" are together to within a human's
        // sense of it, not to within fifty milliseconds — and a meter
        // that samples at 20 Hz cannot resolve better than that anyway.
        if (mask != 0) {
            for (k in -SMEAR..SMEAR) {
                val i = ((head + k) % WINDOW + WINDOW) % WINDOW
                frames[i] = frames[i] or mask
            }
            // and count the coincidences this onset creates, now
            for (a in 0 until channels) {
                if (mask and (1 shl a) == 0) continue
                onsetsOf[a] += 1f
                val near = frames[head]
                for (b in 0 until channels) {
                    if (b == a || near and (1 shl b) == 0) continue
                    coin[a][b] += 1f
                }
            }
        }
        head = (head + 1) % WINDOW
        if (filled < WINDOW) filled++

        winFrames++
        if (winFrames >= WIN_FRAMES) {
            for (ch in 0 until channels) {
                val d = winActive[ch].toFloat() / winFrames
                winDuty[ch].addLast(d)
                while (winDuty[ch].size > WINDOWS_KEPT) winDuty[ch].removeFirst()
                winActive[ch] = 0
            }
            winFrames = 0
        }
    }

    fun forgetAll() {
        frames.fill(0); head = 0; filled = 0
        for (r in coin) r.fill(0f)
        onsetsOf.fill(0f)
        playedSec.fill(0.0); totalSec = 0.0
        for (w in winDuty) w.clear()
        winActive.fill(0); winFrames = 0
        envFilled = 0
    }

    // ------------------------------------------------------------------
    /**
     * How often [a]'s onsets have one from [b] beside them, 0..1. Not
     * symmetric on purpose: the overheads hear every snare hit, but the
     * snare is silent for most of what the overheads pick up.
     */
    fun coincidence(a: Int, b: Int): Float {
        if (a == b || a !in 0 until channels || b !in 0 until channels)
            return 0f
        val n = onsetsOf[a]
        if (n < MIN_ONSETS) return 0f
        return (coin[a][b] / n).coerceIn(0f, 1f)
    }

    /**
     * How much this channel belongs to whatever cluster of channels is
     * playing together on a grid — a drum kit, in practice, since
     * nothing else on a stage fires in lock-step all night.
     *
     * The mean of its two strongest coincidences rather than its single
     * strongest: ONE strong partner is a bass locking to a kick, TWO is
     * a kit. Three was the first attempt and it was wrong — plenty of
     * bands mic three drums, and averaging in a partner that does not
     * exist dragged every real kit member below the threshold.
     */
    fun kitAffinity(ch: Int): Float {
        if (onsetsOf.getOrElse(ch) { 0f } < MIN_ONSETS) return 0f
        val c = (0 until channels).filter { it != ch }
            .map { coincidence(ch, it) }.sortedDescending()
        if (c.size < 2) return 0f
        return (c[0] + c[1]) / 2f
    }

    /** how many other channels this one fires with at all */
    fun partners(ch: Int, atLeast: Float = 0.4f): Int =
        (0 until channels).count { it != ch && coincidence(ch, it) >= atLeast }

    /**
     * The channel whose envelope is this one's envelope, or null.
     *
     * Two halves of a stereo piano are not two instruments that happen
     * to agree; they are one instrument, measured twice, and their
     * level curves are the same curve. Nothing else on a stage
     * correlates like that — not even a kick and a bass playing the
     * same line, because their decays differ.
     */
    fun stereoMate(ch: Int): Int? {
        if (envFilled < PAIR_WINDOW / 2) return null
        var best = -1; var bestR = 0f
        for (o in 0 until channels) {
            if (o == ch) continue
            val r = correlation(ch, o)
            if (r > bestR) { bestR = r; best = o }
        }
        return if (bestR >= PAIR_R) best else null
    }

    fun correlation(a: Int, b: Int): Float {
        if (a !in 0 until channels || b !in 0 until channels) return 0f
        var n = 0; var sa = 0f; var sb = 0f
        for (i in 0 until envFilled) {
            val x = env[a][i]; val y = env[b][i]
            if (x <= -100f || y <= -100f) continue
            sa += x; sb += y; n++
        }
        if (n < PAIR_WINDOW / 4) return 0f
        val ma = sa / n; val mb = sb / n
        var num = 0f; var da = 0f; var db = 0f
        for (i in 0 until envFilled) {
            val x = env[a][i]; val y = env[b][i]
            if (x <= -100f || y <= -100f) continue
            val u = x - ma; val v = y - mb
            num += u * v; da += u * u; db += v * v
        }
        val den = sqrt(da.toDouble() * db.toDouble()).toFloat()
        return if (den <= 1e-6f) 0f else (num / den).coerceIn(-1f, 1f)
    }

    /** the share of the whole set this channel has been playing, 0..1 */
    fun setDuty(ch: Int): Float =
        if (totalSec <= 0.0 || ch !in 0 until channels) 0f
        else (playedSec[ch] / totalSec).toFloat().coerceIn(0f, 1f)

    /**
     * Does it play all the time, or in bursts?
     *
     * The rhythm section is playing in nearly every half-minute of the
     * night; a soloist is playing in almost none of them and then in
     * all of one. That is the difference between a singer and a
     * saxophone as far as a meter can see it, and it is the ONLY
     * difference a meter can see — over a single chorus the two are
     * indistinguishable, and any honest system says so.
     *
     * Returned as 0..1, where 0 is "the same amount every window" and 1
     * is "all or nothing".
     */
    fun burstiness(ch: Int): Float {
        val w = winDuty.getOrNull(ch) ?: return 0f
        if (w.size < 4) return 0f
        val m = w.sum() / w.size
        if (m <= 1e-4f) return 0f
        var v = 0f
        for (d in w) v += (d - m) * (d - m)
        val sd = sqrt((v / w.size).toDouble()).toFloat()
        // normalised so a channel that is on in half the windows and
        // off in the other half comes out near 1
        return (sd / max(m * (1f - m), 1e-4f).let { sqrt(it.toDouble()).toFloat() })
            .coerceIn(0f, 1f)
    }

    /** how many half-minute windows have been observed */
    fun windows(ch: Int): Int = winDuty.getOrNull(ch)?.size ?: 0

    fun onsets(ch: Int): Float = onsetsOf.getOrElse(ch) { 0f }

    /** total seconds the ensemble has been watched */
    fun observedSec(): Double = totalSec

    private companion object {
        /** two minutes of 50 ms frames */
        const val WINDOW = 2400
        /** ±100 ms counts as "together" */
        const val SMEAR = 2
        const val ONSET_DB = 4f
        const val MIN_ONSETS = 12f
        /** thirty seconds of envelope, for stereo pairing */
        const val PAIR_WINDOW = 600
        const val PAIR_R = 0.92f
        /** half-minute windows, and how many to remember */
        const val WIN_FRAMES = 600
        const val WINDOWS_KEPT = 40
    }
}

/**
 * An actual instrument, not a family.
 *
 * The families ([Family]) are what one channel's own spectrum can
 * settle. These are what the spectrum plus the ENSEMBLE can settle, and
 * the difference is the difference between "something low" and "the
 * kick drum".
 */
enum class Instrument(val role: Role, val label: String) {
    KICK(Role.FOUNDATION, "kick"),
    BASS(Role.FOUNDATION, "bass"),
    SNARE(Role.PERCUSSION, "snare"),
    HAND_DRUM(Role.PERCUSSION, "congas / toms"),
    CYMBALS(Role.PERCUSSION, "overheads"),
    KEYS(Role.KEYS, "piano / keys"),
    GUITAR(Role.RHYTHM_GTR, "guitar"),
    LEAD_GUITAR(Role.SOLO_GTR, "lead guitar"),
    HORN(Role.COLOR, "horn / reed"),
    VOICE(Role.VOCAL, "voice"),
    UNKNOWN(Role.INSTRUMENT, "unclassified"),
}
