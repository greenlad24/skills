package com.stagemix.engine

import kotlin.math.log10
import kotlin.math.pow

/**
 * The mix this engineer actually makes.
 *
 * "Every time I clicked on keep this balance — this is the balance I
 * want it to create automatically. That is the base scenario."
 *
 * Which reframes the whole problem, and better than the built-in
 * pyramid ever did. That pyramid is a guess about where instruments
 * belong, written by somebody who has never heard this band in this
 * room; it was always going to be approximately wrong, and every log so
 * far has said so. But a balance the operator built and then pressed
 * KEEP on is not a guess about anything. It is the answer, stated.
 *
 * So every KEEP is training data. What gets recorded is each channel's
 * CONTRIBUTION — source plus fader — measured against the whole mix, so
 * that what is learned is the SHAPE of the balance and not how loud the
 * night happened to be. A quiet ballad set and a loud one produce the
 * same numbers.
 *
 * It is keyed by what the channel IS, not by which socket it was in.
 * The band re-patches between nights, the desk's labels are a previous
 * band's, and the only durable identity a channel has is the instrument
 * the audio recognised on it. "The kick sits four dB under the mix"
 * survives a re-patch; "channel 1 sits four dB under the mix" does not.
 *
 * A mean, not the last one. One night is one room, one crowd and one
 * mood; the balance worth reproducing is the one this engineer keeps
 * arriving at.
 */
class LearnedBalance {

    private val sum = HashMap<String, Float>()
    private val n = HashMap<String, Int>()

    /** how many balances have been learned from, in total */
    var kept = 0; private set

    /**
     * Record a balance the operator has just kept.
     *
     * [heights] is each channel's contribution in dB; the reference is
     * worked out here so callers cannot get it wrong.
     */
    fun learn(heights: Map<Instrument, Float>) {
        val real = heights.filterKeys { it != Instrument.UNKNOWN }
        if (real.size < 2) return
        // The reference is the power sum of everything playing: what the
        // room hears. Anything else — the loudest channel, the mean —
        // moves when the LINEUP changes rather than when the balance
        // does, and would teach a different shape every time somebody
        // sat out a song.
        val ref = powerSum(real.values.toList())
        for ((inst, db) in real) {
            val h = db - ref
            sum[inst.name] = (sum[inst.name] ?: 0f) + h
            n[inst.name] = (n[inst.name] ?: 0) + 1
        }
        kept++
    }

    /**
     * Where this instrument sits, in dB relative to the whole mix, or
     * null if it has not been kept often enough to be worth using.
     */
    fun heightOf(inst: Instrument, minKeeps: Int = 2): Float? {
        val c = n[inst.name] ?: return null
        if (c < minKeeps) return null
        return (sum[inst.name] ?: return null) / c
    }

    fun timesKept(inst: Instrument): Int = n[inst.name] ?: 0

    /** everything learned so far, for saving */
    fun snapshot(): Map<String, Pair<Float, Int>> =
        n.keys.associateWith { (sum[it] ?: 0f) to (n[it] ?: 0) }

    /** and putting it back on the next night */
    fun restore(saved: Map<String, Pair<Float, Int>>) {
        sum.clear(); n.clear()
        var maxN = 0
        for ((k, v) in saved) {
            if (Instrument.values().none { it.name == k }) continue
            if (!v.first.isFinite() || v.second <= 0) continue
            sum[k] = v.first; n[k] = v.second
            if (v.second > maxN) maxN = v.second
        }
        kept = maxN
    }

    fun forgetAll() { sum.clear(); n.clear(); kept = 0 }

    /** in words, for the screen: "kick -4.2 · voice +1.8 · …" */
    fun summary(): String = n.keys
        .mapNotNull { k ->
            val inst = Instrument.values().firstOrNull { it.name == k }
                ?: return@mapNotNull null
            heightOf(inst)?.let { inst to it }
        }
        .sortedByDescending { it.second }
        .joinToString(" · ") {
            "%s %+.1f".format(java.util.Locale.ROOT, it.first.label, it.second)
        }

    private companion object {
        fun powerSum(v: List<Float>): Float =
            if (v.isEmpty()) -140f
            else (10.0 * log10(v.sumOf { 10.0.pow(it / 10.0) })).toFloat()
    }
}
