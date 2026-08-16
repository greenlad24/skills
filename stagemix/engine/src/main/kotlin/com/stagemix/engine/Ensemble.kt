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

    /**
     * How hard this channel falls away after it is struck.
     *
     * A drum is a hit and then nothing: 20 Hz metering still catches
     * eight or ten dB of collapse in the quarter-second after a conga
     * lands. A sung note, a held chord, a bowed or blown line does the
     * opposite — it is still there, often louder, a quarter-second in.
     *
     * This exists because "fires on the grid" turned out not to mean
     * "is a drum". It means "is in a band". On a real night every
     * channel — both singers, both pianos, both guitars — coincided
     * beautifully with the drums, because that is what playing together
     * IS, and the engine concluded that all of them were congas. The
     * missing question was never about timing. It was whether the sound
     * stops.
     */
    private val decaySum = FloatArray(channels)
    private val decayN = FloatArray(channels)
    /** frames still to be measured after an onset, per channel */
    private val decayWait = IntArray(channels)
    private val decayPeak = FloatArray(channels)

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
            val onset = on && d >= ONSET_DB && !wasUp[ch]
            if (onset) mask = mask or (1 shl ch)
            // DOES IT STOP? Start a short measurement at every onset and
            // record how far the channel has fallen from its peak by the
            // end of it. Overlapping onsets simply restart the window,
            // which is right: a roll is not a series of measurable
            // decays and should not be counted as one.
            if (onset) { decayWait[ch] = DECAY_FRAMES; decayPeak[ch] = db }
            else if (decayWait[ch] > 0) {
                if (db > decayPeak[ch]) decayPeak[ch] = db
                decayWait[ch]--
                if (decayWait[ch] == 0) {
                    decaySum[ch] += (decayPeak[ch] - db).coerceIn(0f, 40f)
                    decayN[ch] += 1f
                }
            }
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
        decaySum.fill(0f); decayN.fill(0f)
        decayWait.fill(0); decayPeak.fill(-128f)
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
     * Is this channel STRUCK? 0..1, from its own envelope alone.
     *
     * Deliberately independent of every other channel, so that using it
     * to weight the kit test below is not circular.
     */
    fun percussive(ch: Int): Float {
        if (ch !in 0 until channels) return 0f
        if (decayN[ch] < MIN_DECAYS) return 0f
        val mean = decaySum[ch] / decayN[ch]
        return ((mean - DECAY_SOFT) / (DECAY_HARD - DECAY_SOFT))
            .coerceIn(0f, 1f)
    }

    /**
     * How much this channel belongs to the DRUM KIT.
     *
     * Two things at once, and the second one was missing for a night.
     *
     * Firing on the grid with other channels is necessary — but it is
     * not remotely sufficient, because a band playing together is
     * sixteen channels all firing on the same grid. Measured on timing
     * alone this returned a high score for every musician on the stage,
     * which fed a "congas" verdict to both singers, both pianos and
     * both guitars, and — because [InstrumentId] used a high kit score
     * to RULE OUT a voice — made it impossible to recognise a singer
     * who sings in time with the band. Which is all of them.
     *
     * So the partners are weighted by whether they are struck, and the
     * channel itself has to be struck too. A conga that lands with the
     * snare is kit. A guitar that lands with the snare is a guitar.
     *
     * The mean of its two strongest partners rather than its single
     * strongest: ONE strong partner is a bass locking to a kick, TWO is
     * a kit. Three was the first attempt and it was wrong — plenty of
     * bands mic three drums, and averaging in a partner that does not
     * exist dragged every real kit member below the threshold.
     */
    fun kitAffinity(ch: Int): Float {
        if (onsetsOf.getOrElse(ch) { 0f } < MIN_ONSETS) return 0f
        val me = percussive(ch)
        if (me <= 0f) return 0f
        val c = (0 until channels).filter { it != ch }
            .map { coincidence(ch, it) * percussive(it) }.sortedDescending()
        if (c.size < 2) return 0f
        return me * (c[0] + c[1]) / 2f
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
        /** 250 ms — long enough for a drum to be gone, short enough
         *  that a sung note has not yet ended */
        const val DECAY_FRAMES = 5
        const val MIN_DECAYS = 8f
        /** dB fallen from the peak: below `SOFT` it sustains, above
         *  `HARD` it was struck and is already over */
        const val DECAY_SOFT = 3f
        const val DECAY_HARD = 10f
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
    SNARE(Role.DRUMS, "snare"),
    HAND_DRUM(Role.PERCUSSION, "congas / toms"),
    CYMBALS(Role.DRUMS, "overheads"),
    KEYS(Role.KEYS, "piano / keys"),
    GUITAR(Role.RHYTHM_GTR, "guitar"),
    LEAD_GUITAR(Role.SOLO_GTR, "lead guitar"),
    HORN(Role.COLOR, "horn / reed"),
    VOICE(Role.VOCAL, "voice"),
    UNKNOWN(Role.INSTRUMENT, "unclassified"),
}
