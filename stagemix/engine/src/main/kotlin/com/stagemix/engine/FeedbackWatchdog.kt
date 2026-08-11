package com.stagemix.engine

import kotlin.math.abs
import kotlin.math.pow

/**
 * Audio-feedback (howl) recognizer, running on the console's 100-bin
 * RTA (~20 Hz frames, log-spaced 20 Hz..20 kHz, 10 bins/octave).
 *
 * Telling a howl from a sustained musical note is the whole problem —
 * this band has a HARMONICA, a flute/sax, an organ-ish keyboard and
 * singers who hold notes, and every one of those is a narrow, parked,
 * loud peak. Two discriminators (both validated against synthetic
 * spectra for all four instruments) do the work:
 *
 *  1. HARMONIC PARTNERS. A real instrument puts energy at 2f and 3f
 *     (+10 and +16 bins on a 10-bin/octave log scale). Acoustic
 *     feedback is a single room/mic resonance with no harmonic family
 *     — a driver's distortion harmonic sits far below the noise floor.
 *     A peak with a partner is music, never a howl.
 *  2. GROWTH PATH. The tower test (peak >= median + 25 dB) is blind
 *     while the band plays, because the band raises the median. A howl
 *     that is narrow, parked at one frequency and has RISEN >= 12 dB
 *     within a second is a howl even if it never towers.
 *
 * EVERY PEAK IS EXAMINED, not just the loudest. Watching only the
 * single hottest bin meant a howl ringing up underneath a band went
 * completely unseen: the bass fundamental was louder, it had harmonics,
 * so it was correctly judged to be music — and the watchdog then looked
 * no further. Feedback is only the loudest thing in the room once it is
 * already screaming, which is far too late to be noticing it.
 *
 * The response stays conservative: freeze upward automation and name
 * the frequency for the human to notch. Never auto-EQ.
 */
class FeedbackWatchdog(
    private val towerDb: Float = 25f,
    private val floorDb: Float = -40f,
    private val holdFrames: Int = 10,          // ~0.5 s at 20 Hz
    private val clearSec: Double = 3.0,
    private val riseDb: Float = 12f,
    private val riseWindowFrames: Int = 20,    // ~1 s at 20 Hz
    private val partnerRelDb: Float = 30f,
    private val partnerAboveMedianDb: Float = 8f,
) {
    var vetoActive = false; private set
    var lastFreqHz: Int = 0; private set

    /** how many peaks a frame may put forward; a howl is never far down */
    private val MAX_CANDIDATES = 5

    /** how far a peak may wander and still be the same howl */
    private val CONTINUITY_BINS = 3

    /** a ring of recent spectra, so any bin's growth can be read */
    private val history = ArrayList<FloatArray>()
    /** consecutive frames each bin has looked like a howl */
    private val streak = IntArray(100)
    private var lastSeenT = -1.0

    /**
     * The analyzer has been pointed somewhere else — forget the past.
     *
     * This watchdog fires on "risen twelve dB at a fixed frequency in
     * about a second". Moving `/-stat/rta/source` to another channel is
     * a step change across all one hundred bins at once, which is that
     * pattern exactly — and the app moves it every three seconds,
     * round-robin, all night. The harmonic-partner test was catching
     * most of these, but it was never designed to be the thing standing
     * between a source switch and a false howl; a false howl freezes
     * every boost in the mix.
     *
     * Clearing here also means the detector needs about a second of the
     * new channel before it can fire at all, which is honest: it has
     * not heard enough of that channel to have an opinion yet.
     */
    fun sourceChanged() {
        history.clear()
        streak.fill(0)
    }

    fun onRta(bins: FloatArray, tSec: Double) {
        if (bins.size < 100) return
        for (v in bins) if (v.isNaN() || v.isInfinite()) return

        history.add(bins.copyOf())
        while (history.size > riseWindowFrames + 1) history.removeAt(0)
        val old = if (history.size > riseWindowFrames) history.first() else null

        val sorted = bins.copyOf().also { it.sort() }
        val median = sorted[bins.size / 2]

        // the peaks worth asking about: local maxima above the floor,
        // loudest first, however far down the list they sit
        val peaks = ArrayList<Int>()
        for (i in bins.indices) {
            if (bins[i] < floorDb) continue
            val l = if (i > 0) bins[i - 1] else -128f
            val r = if (i < bins.size - 1) bins[i + 1] else -128f
            if (bins[i] >= l && bins[i] >= r) peaks.add(i)
        }
        peaks.sortByDescending { bins[it] }
        val considered = peaks.take(MAX_CANDIDATES)

        var firing = -1
        val next = IntArray(100)
        for (b in considered) {
            if (!looksLikeHowl(bins, b, median, old)) continue
            // A howl wanders a bin or two as the room warms; that is one
            // event, not a new one each frame. Inherit the run from the
            // neighbourhood rather than starting over.
            var inherited = 0
            for (k in (b - CONTINUITY_BINS)..(b + CONTINUITY_BINS))
                if (k in 0 until 100 && streak[k] > inherited) inherited = streak[k]
            next[b] = inherited + 1
            if (next[b] >= holdFrames && firing < 0) firing = b
        }
        System.arraycopy(next, 0, streak, 0, 100)

        if (streak.any { it > 0 }) lastSeenT = tSec

        if (firing >= 0) {
            if (!vetoActive) { vetoActive = true; lastFreqHz = binHz(firing) }
        } else if (vetoActive && tSec - lastSeenT > clearSec) {
            vetoActive = false
            streak.fill(0)
            history.clear()
        }
    }

    /**
     * Is this peak a howl rather than an instrument? Narrow, no harmonic
     * family, and either towering over the room or climbing fast at a
     * fixed frequency.
     */
    private fun looksLikeHowl(bins: FloatArray, b: Int, median: Float,
                              old: FloatArray?): Boolean {
        val v = bins[b]
        val l = if (b - 2 >= 0) bins[b - 2] else -128f
        val r = if (b + 2 < bins.size) bins[b + 2] else -128f
        if (v - maxOf(l, r) < 12f) return false          // not narrow

        // 2f is +10 bins, 3f is +16 bins on a 10-bin/octave scale
        val hasPartner = intArrayOf(10, 16).any { off ->
            ((b + off - 1)..(b + off + 1)).any { pb ->
                val p = if (pb in bins.indices) bins[pb] else -128f
                p >= v - partnerRelDb && p >= median + partnerAboveMedianDb
            }
        }
        if (hasPartner) return false                      // an instrument

        // A howl is also nobody's harmonic. A held note's own 2f and 3f
        // are narrow and partnerless looking upward, and would otherwise
        // be reported as feedback an octave above the singer.
        val isSomeonesHarmonic = intArrayOf(10, 16).any { off ->
            ((b - off - 1)..(b - off + 1)).any { fb ->
                val f = if (fb in bins.indices) bins[fb] else -128f
                f >= v && f >= median + partnerAboveMedianDb
            }
        }
        if (isSomeonesHarmonic) return false

        val towered = v >= median + towerDb
        val grew = old != null &&
            (b - 1..b + 1).any { k ->
                k in bins.indices && v - old[k] >= riseDb
            }
        return towered || grew
    }

    private fun binHz(bin: Int): Int = (20.0 * 2.0.pow(bin / 10.0)).toInt()
}
