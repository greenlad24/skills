package com.stagemix.engine

import kotlin.math.abs
import kotlin.math.log2
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow

/**
 * What each channel actually SOUNDS like, kept as a shape rather than
 * as a handful of sums.
 *
 * The operator's diagnosis, and it was right: "the app is missing a
 * frequency map on each channel to understand how to treat it — and
 * understand what is each channel."
 *
 * The RTA has always been arriving. A hundred bins, ten per octave from
 * 20 Hz, one channel at a time. But both things that consume it throw
 * the shape away before anyone can reason about it: [InstrumentId]
 * folds the hundred bins into seven band sums, and [ToneDoctor] into
 * four. Seven numbers can say "there is energy down low". They cannot
 * say where this kick actually stops, which is the one thing you need
 * to know before setting a high-pass; and they cannot say that the
 * snare mic and the congas are fighting over 250 Hz, which is how a
 * person decides what to cut and where.
 *
 * So this keeps the shape, and keeps it for a long time. Three kinds of
 * question become answerable that were not:
 *
 *  · WHERE DOES IT LIVE. The lowest frequency this channel has real
 *    energy at, and the highest. A high-pass belongs below the former,
 *    not at a number chosen in advance by somebody who has never heard
 *    the instrument. On the rig this was written for, one preset put a
 *    100 Hz high-pass on every vocal — fine for most singers and wrong
 *    for a baritone whose fundamental is 87 Hz.
 *
 *  · WHAT STICKS OUT. A resonance is a narrow peak standing over the
 *    channel's own smooth trend. That is a different measurement from
 *    "this band is loud", and it is the one worth a narrow cut.
 *
 *  · WHO IS IT FIGHTING. Two channels whose energy sits in the same
 *    place mask each other, and no amount of looking at either one
 *    alone will show it.
 *
 * Everything here is computed from data the app already receives, on
 * the tablet, with no network — see [StageEngine.onRtaFor].
 *
 * A NOTE ON CONFIDENCE. The analyzer visits one channel at a time, so a
 * sixteen-channel stage gives each channel about a sixteenth of the
 * night. [coverage] says how much has actually been heard, and nothing
 * downstream should act on a map that has not been earned. A map built
 * from four seconds of a channel is a guess wearing a lab coat.
 */
class FrequencyMap {

    /** one channel's accumulated shape */
    private class Shape {
        /** long-memory mean of the log spectrum, in dB */
        val mean = DoubleArray(BINS)
        /** running mean of the squared deviation, for stability */
        val varAcc = DoubleArray(BINS)
        var frames = 0
        /** seconds of audio actually folded in */
        var heardSec = 0.0
    }

    private val shapes = HashMap<Int, Shape>()

    /**
     * One RTA frame for one channel.
     *
     * [active] must be false when the channel is not making sound: a
     * spectrum of silence is a spectrum of the room and the preamp, and
     * averaging it in flattens everything this class exists to find.
     */
    fun onRta(ch: Int, bins: FloatArray, active: Boolean, dtSec: Float = 0.05f) {
        if (!active || bins.size < BINS) return
        for (v in bins) if (v.isNaN() || v.isInfinite()) return
        val s = shapes.getOrPut(ch) { Shape() }
        // A long memory on purpose. This is meant to describe an
        // instrument, not a bar of music: the alpha works out at a few
        // minutes of ACTIVE audio, so a shape only settles once the
        // channel has genuinely been listened to.
        val a = 1.0 / min(s.frames + 1, MEMORY).toDouble()
        for (i in 0 until BINS) {
            val d = bins[i].toDouble() - s.mean[i]
            s.mean[i] += a * d
            // deviation from the running mean, same memory
            s.varAcc[i] += a * (d * d - s.varAcc[i])
        }
        s.frames++
        s.heardSec += dtSec.toDouble()
    }

    fun forget(ch: Int) { shapes.remove(ch) }
    fun forgetAll() = shapes.clear()

    /**
     * How much of this channel has been heard, 0..1. One is "enough to
     * act on"; below [MIN_COVERAGE] nothing here should be trusted.
     */
    fun coverage(ch: Int): Float {
        val s = shapes[ch] ?: return 0f
        return min(1.0, s.heardSec / SETTLED_SEC).toFloat()
    }

    fun settled(ch: Int): Boolean = coverage(ch) >= MIN_COVERAGE

    /** the channel's shape in dB, normalised so its peak is 0 — or null */
    fun shape(ch: Int): FloatArray? {
        val s = shapes[ch] ?: return null
        if (s.frames < 8) return null
        val peak = s.mean.max()
        return FloatArray(BINS) { (s.mean[it] - peak).toFloat() }
    }

    /**
     * WHERE THE INSTRUMENT STOPS, going down.
     *
     * The lowest frequency still within [edgeDropDb] of the channel's
     * loudest region. Below this there is nothing of the instrument —
     * only stage rumble, handling and the room — which makes it the
     * honest place to put a high-pass, and a far better answer than a
     * number chosen per role in advance.
     *
     * Returns null when too little has been heard to say.
     */
    fun lowEdgeHz(ch: Int, edgeDropDb: Float = EDGE_DROP_DB): Float? {
        val sh = shape(ch) ?: return null
        if (!settled(ch)) return null
        val peakBin = sh.indices.maxByOrNull { sh[it] } ?: return null
        var i = peakBin
        while (i > 0 && sh[i] > -edgeDropDb) i--
        return hzOf(i)
    }

    /** and where it stops going up — the top of anything real */
    fun highEdgeHz(ch: Int, edgeDropDb: Float = EDGE_DROP_DB): Float? {
        val sh = shape(ch) ?: return null
        if (!settled(ch)) return null
        val peakBin = sh.indices.maxByOrNull { sh[it] } ?: return null
        var i = peakBin
        while (i < BINS - 1 && sh[i] > -edgeDropDb) i++
        return hzOf(i)
    }

    /** where this channel is loudest */
    fun peakHz(ch: Int): Float? {
        val sh = shape(ch) ?: return null
        val b = sh.indices.maxByOrNull { sh[it] } ?: return null
        return hzOf(b)
    }

    /** a narrow peak standing over the channel's own smooth trend */
    data class Resonance(val hz: Float, val overTrendDb: Float, val q: Float)

    /**
     * Resonances, strongest first.
     *
     * Measured against a smoothed version of the channel's OWN spectrum
     * rather than against flat, because no instrument is flat and a
     * tilted instrument is not a fault. What is worth a narrow cut is a
     * lump that stands proud of the shape around it — a drum shell
     * ringing, a box resonance, a room mode the mic happens to sit in.
     */
    fun resonances(ch: Int, minOverTrendDb: Float = 4f): List<Resonance> {
        val sh = shape(ch) ?: return emptyList()
        if (!settled(ch)) return emptyList()
        val trend = smooth(sh, SMOOTH_BINS)
        val out = ArrayList<Resonance>()
        for (i in 1 until BINS - 1) {
            val over = sh[i] - trend[i]
            if (over < minOverTrendDb) continue
            // a local maximum, or it is the shoulder of one
            if (sh[i] < sh[i - 1] || sh[i] < sh[i + 1]) continue
            // AND IT HAS TO COME BACK DOWN ON BOTH SIDES.
            //
            // A resonance rises and falls. The edge of a band rises and
            // stays up, and a smoothed trend lags at any sharp step, so
            // measuring prominence alone reported the bottom corner of
            // a kick drum as a twenty-one dB lump worth cutting. That
            // would have put a narrow notch exactly where the
            // instrument starts.
            val w = SHOULDER_BINS
            val left = sh[i] - sh[max(0, i - w)]
            val right = sh[i] - sh[min(BINS - 1, i + w)]
            if (left < minOverTrendDb / 2f || right < minOverTrendDb / 2f)
                continue
            // width at half the prominence, converted to Q
            var lo = i; while (lo > 0 && sh[lo] - trend[lo] > over / 2) lo--
            var hi = i; while (hi < BINS - 1 && sh[hi] - trend[hi] > over / 2) hi++
            val octaves = (hi - lo).toFloat() / BINS_PER_OCTAVE
            val q = if (octaves > 0.01f) (1f / octaves).coerceIn(0.3f, 10f) else 10f
            out.add(Resonance(hzOf(i), over, q))
        }
        return out.sortedByDescending { it.overTrendDb }
    }

    /**
     * HOW MUCH TWO CHANNELS ARE IN EACH OTHER'S WAY, 0..1.
     *
     * The overlap of their normalised energy: 1 means they occupy the
     * same place in the spectrum entirely, 0 means they never meet.
     * This is the measurement no single channel can offer, and it is
     * the one a person is really making when they decide to take 300 Hz
     * out of the guitar rather than out of the piano.
     */
    fun overlap(a: Int, b: Int): Float {
        val sa = linear(a) ?: return 0f
        val sb = linear(b) ?: return 0f
        var inter = 0.0
        for (i in 0 until BINS) inter += min(sa[i], sb[i])
        return inter.toFloat().coerceIn(0f, 1f)
    }

    /** the channels this one is most in the way of, worst first */
    fun rivals(ch: Int, others: Collection<Int>, min: Float = 0.35f):
        List<Pair<Int, Float>> =
        others.filter { it != ch }
            .map { it to overlap(ch, it) }
            .filter { it.second >= min }
            .sortedByDescending { it.second }

    /**
     * How settled the shape is, 0..1 — one means it has stopped moving.
     *
     * A map that is still changing describes a channel that is still
     * changing, and treating it is guesswork. Worth having explicitly:
     * it is the difference between "I know what this is" and "I have
     * heard it for four seconds".
     */
    fun stability(ch: Int): Float {
        val s = shapes[ch] ?: return 0f
        if (s.frames < 16) return 0f
        var sd = 0.0
        for (i in 0 until BINS) sd += kotlin.math.sqrt(max(0.0, s.varAcc[i]))
        val mean = sd / BINS
        return (1.0 - (mean / STABLE_SD_DB)).coerceIn(0.0, 1.0).toFloat()
    }

    /** in words, for the log and the screen */
    fun describe(ch: Int): String {
        if (!settled(ch)) return "still listening (%.0f%%)"
            .format(java.util.Locale.ROOT, coverage(ch) * 100)
        val lo = lowEdgeHz(ch); val pk = peakHz(ch); val hi = highEdgeHz(ch)
        val res = resonances(ch).firstOrNull()
        return buildString {
            append("%s-%s, loudest at %s".format(java.util.Locale.ROOT,
                hz(lo), hz(hi), hz(pk)))
            if (res != null) append(", a %.0f dB lump at %s"
                .format(java.util.Locale.ROOT, res.overTrendDb, hz(res.hz)))
        }
    }

    // ------------------------------------------------------------------
    /** normalised linear energy, summing to 1 — for overlap */
    private fun linear(ch: Int): DoubleArray? {
        val sh = shape(ch) ?: return null
        val lin = DoubleArray(BINS) { 10.0.pow(sh[it] / 10.0) }
        val tot = lin.sum()
        if (tot <= 0.0) return null
        for (i in 0 until BINS) lin[i] /= tot
        return lin
    }

    private fun smooth(v: FloatArray, halfWidth: Int): FloatArray =
        FloatArray(v.size) { i ->
            var s = 0f; var n = 0
            for (k in max(0, i - halfWidth)..min(v.size - 1, i + halfWidth)) {
                s += v[k]; n++
            }
            s / n
        }

    companion object {
        const val BINS = 100
        /** the RTA is ten bins per octave from 20 Hz */
        const val BINS_PER_OCTAVE = 10f
        fun hzOf(bin: Int): Float =
            (20.0 * 2.0.pow(bin / BINS_PER_OCTAVE.toDouble())).toFloat()
        fun binOf(hz: Float): Int =
            (BINS_PER_OCTAVE * log2(hz / 20f)).toInt().coerceIn(0, BINS - 1)

        /** frames of ACTIVE audio the mean converges over */
        const val MEMORY = 1200
        /** active seconds before a map is worth acting on */
        const val SETTLED_SEC = 25.0
        const val MIN_COVERAGE = 1.0f
        /** how far down from the peak still counts as the instrument */
        const val EDGE_DROP_DB = 18f
        /** half-width of the trend used to find lumps, in bins */
        const val SMOOTH_BINS = 7
        /** how far either side a real resonance must fall away */
        const val SHOULDER_BINS = 3
        /** per-bin standard deviation at which a shape reads as unsettled */
        const val STABLE_SD_DB = 6.0

        private fun hz(f: Float?): String = when {
            f == null -> "?"
            f >= 1000f -> "%.1fk".format(java.util.Locale.ROOT, f / 1000f)
            else -> "%.0f Hz".format(java.util.Locale.ROOT, f)
        }
    }
}
