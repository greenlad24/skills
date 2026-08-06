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
 * band's, and the most durable identity a channel has is the instrument
 * the audio recognised on it. "The kick sits four dB under the mix"
 * survives a re-patch; "channel 1 sits four dB under the mix" does not.
 *
 * BUT IT MUST NEVER LEARN NOTHING. That identity used to be the only
 * one on offer, so a night where the recogniser had no opinion taught
 * the app precisely nothing — and there was such a night: three and a
 * quarter hours, two presses of KEEP, and both of them logged "learned
 * from 0 balances so far". Pressing that button is the clearest
 * statement of intent in the whole application and it went in the bin
 * twice, because a DIFFERENT component was having a bad night.
 *
 * So identity is a key, and a key can be either thing: the recognised
 * instrument where there is one, the desk's own name for the channel
 * where there is not. The desk name is a weaker identity — it survives
 * a restart but not a re-patch — and it is enormously better than
 * nothing, which was the alternative in practice.
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
     * [heights] maps identity key (see [keyOf]) to that channel's
     * contribution in dB; the reference is worked out here so callers
     * cannot get it wrong.
     */
    fun learn(heights: Map<String, Float>) {
        val real = heights.filterKeys { it.isNotBlank() }
            .filterValues { it.isFinite() }
        if (real.size < 2) return
        // The reference is the power sum of everything playing: what the
        // room hears. Anything else — the loudest channel, the mean —
        // moves when the LINEUP changes rather than when the balance
        // does, and would teach a different shape every time somebody
        // sat out a song.
        val ref = powerSum(real.values.toList())
        for ((key, db) in real) {
            val h = db - ref
            sum[key] = (sum[key] ?: 0f) + h
            n[key] = (n[key] ?: 0) + 1
        }
        kept++
    }

    /** the same, stated in instruments */
    @JvmName("learnByInstrument")
    fun learn(heights: Map<Instrument, Float>) {
        val byKey: Map<String, Float> =
            heights.filterKeys { it != Instrument.UNKNOWN }
                .entries.associate { keyOf(it.key) to it.value }
        learn(byKey)
    }

    /**
     * Where this identity sits, in dB relative to the whole mix, or
     * null if it has not been kept often enough to be worth using.
     */
    fun heightOf(key: String, minKeeps: Int = 2): Float? {
        val c = n[key] ?: return null
        if (c < minKeeps) return null
        return (sum[key] ?: return null) / c
    }

    fun heightOf(inst: Instrument, minKeeps: Int = 2): Float? =
        heightOf(keyOf(inst), minKeeps)

    fun timesKept(key: String): Int = n[key] ?: 0
    fun timesKept(inst: Instrument): Int = timesKept(keyOf(inst))

    /** everything learned so far, for saving */
    fun snapshot(): Map<String, Pair<Float, Int>> =
        n.keys.associateWith { (sum[it] ?: 0f) to (n[it] ?: 0) }

    /** and putting it back on the next night */
    fun restore(saved: Map<String, Pair<Float, Int>>) {
        sum.clear(); n.clear()
        var maxN = 0
        for ((k0, v) in saved) {
            // Prefixes arrived after the first release wrote its
            // preferences, so a bare instrument name is a file from an
            // older build and is worth reading rather than discarding —
            // it is somebody's kept balances.
            val k = normalise(k0) ?: continue
            if (!v.first.isFinite() || v.second <= 0) continue
            sum[k] = v.first; n[k] = v.second
            if (v.second > maxN) maxN = v.second
        }
        kept = maxN
    }

    fun forgetAll() { sum.clear(); n.clear(); kept = 0 }

    /** in words, for the screen: "kick -4.2 · voice +1.8 · …" */
    fun summary(): String = n.keys
        .mapNotNull { k -> heightOf(k)?.let { pretty(k) to it } }
        .sortedByDescending { it.second }
        .joinToString(" · ") {
            "%s %+.1f".format(java.util.Locale.ROOT, it.first, it.second)
        }

    companion object {
        /** the strong identity: what the audio says this is */
        fun keyOf(inst: Instrument): String = "INST:${inst.name}"

        /**
         * The weak identity: what the desk calls it. Used only when the
         * audio has no opinion — but used, rather than dropping the
         * operator's balance on the floor.
         */
        fun keyOf(deskName: String): String =
            "NAME:${deskName.trim().lowercase()}"

        /** a stored key, checked and brought up to date, or null */
        private fun normalise(k: String): String? = when {
            k.startsWith("INST:") ->
                k.takeIf {
                    Instrument.values().any { i -> "INST:${i.name}" == k } &&
                        k != keyOf(Instrument.UNKNOWN)
                }
            k.startsWith("NAME:") -> k.takeIf { it.length > 5 }
            // written by a build before keys had prefixes
            else -> Instrument.values()
                .firstOrNull { it.name == k && it != Instrument.UNKNOWN }
                ?.let { keyOf(it) }
        }

        private fun pretty(k: String): String = when {
            k.startsWith("INST:") -> Instrument.values()
                .firstOrNull { "INST:${it.name}" == k }?.label
                ?: k.removePrefix("INST:")
            else -> k.removePrefix("NAME:")
        }

        fun powerSum(v: List<Float>): Float =
            if (v.isEmpty()) -140f
            else (10.0 * log10(v.sumOf { 10.0.pow(it / 10.0) })).toFloat()
    }
}
