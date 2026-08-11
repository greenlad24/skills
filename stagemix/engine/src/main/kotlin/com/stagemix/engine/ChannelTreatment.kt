package com.stagemix.engine

import kotlin.math.abs
import kotlin.math.ln
import kotlin.math.max

/**
 * The chain you would set up at soundcheck, set up once, when the app
 * works out what the channel is.
 *
 * The operator's ask, in full: "once it recognize what is each channel —
 * I want it to do EQ, compression and reverb (only for the ones that
 * need reverb) once — then adjust EQ only if major changes in the sound
 * happen for a channel. If not, it would be only balance work."
 *
 * That is a different job from the [ToneDoctor], and they are kept
 * apart deliberately. The Doctor is a caretaker: it holds a channel's
 * tone where the engineer left it and corrects drift, forever. This is
 * a STARTING POINT — the high-pass, the one or two EQ moves, the
 * compressor and the reverb send that every engineer makes on a kick or
 * a vocal before the first song — applied once and then left alone.
 *
 * Three rules govern it, and all three exist because an autopilot that
 * keeps re-EQing is worse than one that never EQs at all:
 *
 *  1. ONCE. A chain is applied the first time the audio (not the
 *     channel name) is confident about what the channel is.
 *  2. AGAIN ONLY ON A MATERIAL CHANGE. Not drift, not a quieter verse:
 *     the instrument itself changed, or the channel went away and came
 *     back sounding like something else. That is checked against the
 *     spectrum the chain was built for.
 *  3. NEVER OVER A HUMAN. A band the engineer has since moved is theirs;
 *     the treatment will not put its own value back.
 *
 * ## What it is allowed to write
 *
 * Channel processing only: the channel high-pass, the channel EQ, the
 * channel gate and compressor, and the FX SENDS. Never an aux send.
 *
 * That distinction is the app's oldest and least negotiable rule —
 * monitor buses are the band's ears and are 100 % human territory — and
 * on this desk it is a matter of one digit: sends 1-6 are the aux buses
 * that feed the wedges and the in-ears, sends 7-10 are the effects
 * engines. A reverb send is 7-10. So rather than trusting a format
 * string, every write this class produces is passed through
 * [isSafeAddress], which refuses anything else, and there is a test
 * whose only job is to try to get an aux send past it.
 */

/** the four FX buses on an X-Air/M-Air desk, as channel send indices */
const val FX_SEND_FIRST = 7
const val FX_SEND_LAST = 10

/** the aux buses. Named here so the guard can say what it is refusing. */
const val AUX_SEND_FIRST = 1
const val AUX_SEND_LAST = 6

/**
 * True if this address is channel processing or an FX send.
 *
 * Deliberately a whitelist. A blacklist of "not the aux sends" would
 * have let through every address nobody thought of, and the failure
 * mode of getting this wrong is a fader move in a musician's ears in
 * the middle of a song.
 */
/**
 * NOTHING THIS APP WRITES MAY ADD GAIN. Not anywhere, not on any
 * channel, not by any route.
 *
 * Stated by the operator as a requirement, and it is the right one:
 * "messing with gain WILL cause feedback problems on the stage that
 * the app will find hard to resolve — I want this app to be precise
 * and never cause problems."
 *
 * The preamp was never writable, which is necessary and nowhere near
 * sufficient, because a microphone's loop does not care WHICH gain
 * stage the dB came from. Two other routes were open and both were
 * being used:
 *
 *  · EQ BOOSTS ON OPEN MICROPHONES. The book carried +2 dB at 3 kHz
 *    for a lead vocal and +2 dB at 6 kHz for the drum and conga mics.
 *    2-4 kHz is where a cardioid's presence peak, a wedge horn's
 *    output and a bar room's worst mode all coincide — it is the band
 *    a ring-out cuts most often — and this was applied automatically,
 *    mid-set, to the channels carrying the most gain on the stage.
 *
 *  · MAKEUP GAIN, up to +4 dB on every vocal. Worse than the EQ, for
 *    a reason that falls straight out of the gain curve: a downward
 *    compressor's gain is at its MAXIMUM below the threshold, and
 *    incipient ringing starts from the noise floor. So the full makeup
 *    is applied at exactly the level at which feedback is deciding
 *    whether to start.
 *
 * And on an X-Air the aux sends tap the channel AFTER the EQ and the
 * dynamics, so both of those land in all six wedges at full value —
 * which means the monitor guarantee, which is about faders, never
 * covered them at all.
 *
 * So the rule is not "be careful with boosts", it is that the
 * processing path is CUT-ONLY, enforced here rather than trusted to
 * the book. If a chain ever asks for gain again, this refuses it and
 * says so, and the test in ChannelTreatmentTest exists to try.
 */
fun isGainAdding(address: String, value: Float): Boolean = when {
    // an EQ band gain above the centre of its 0..1 range is a boost
    Regex("^/ch/\\d\\d/eq/[1-4]/g$").matches(address) ->
        value > 0.5f + GAIN_EPS
    // makeup is 0..24 dB over 0..1: anything above zero adds gain
    Regex("^/ch/\\d\\d/dyn/mgain$").matches(address) -> value > GAIN_EPS
    else -> false
}

/** float slop, so an exact unity write is not read as a boost */
const val GAIN_EPS = 0.002f

fun isSafeAddress(address: String): Boolean {
    Regex("^/ch/(\\d\\d)/mix/(\\d\\d)/level$").find(address)?.let { m ->
        val send = m.groupValues[2].toIntOrNull() ?: return false
        return send in FX_SEND_FIRST..FX_SEND_LAST
    }
    return Regex("^/ch/\\d\\d/(preamp/(hpon|hpf)|" +
        "eq/(on|[1-4]/(f|g|q|type))|" +
        "(gate|dyn)/(on|thr|ratio|attack|release|mgain|knee))$")
        .matches(address)
}

/** one EQ band, in the units an engineer thinks in */
data class EqBand(val band: Int, val hz: Float, val gainDb: Float,
                  val q: Float)

/**
 * A starting chain for one kind of instrument.
 *
 * Everything is optional, because "leave it alone" is a real and often
 * correct answer: a DI bass wants no high-pass and no reverb, and
 * saying so by omission is safer than encoding a zero.
 */
data class Chain(
    val hpfHz: Float? = null,
    val eq: List<EqBand> = emptyList(),
    val compThrDb: Float? = null,
    val compRatio: Float? = null,
    val compAttackMs: Float? = null,
    val compReleaseMs: Float? = null,
    val compMakeupDb: Float? = null,
    /**
     * Reverb send level, in dB, or null for none.
     *
     * "only for the ones that need reverb" was explicit, and it is the
     * part of this that an autopilot most obviously gets wrong. A kick,
     * a bass, a DI and a talkback mic get none — reverb on the low end
     * is how a room turns to mud, and reverb on a talkback mic is just
     * strange. Voices, a snare and a horn get some.
     */
    val reverbSendDb: Float? = null,
    val why: String = "",
)

/**
 * The book. One chain per role, written the way an engineer would set
 * one up cold — conservative, because these are applied without anybody
 * listening first, and a chain that is merely unhelpful is recoverable
 * where one that is wrong is not.
 */
val STARTING_CHAINS: Map<Role, Chain> = mapOf(
    Role.FOUNDATION to Chain(
        // No high-pass worth the name: this is where the low end lives.
        // The 400 Hz dip is the one move that is right on nearly every
        // kick and most basses — the box, the boxiness.
        hpfHz = 30f,
        eq = listOf(EqBand(2, 400f, -3f, 1.8f)),
        compThrDb = -18f, compRatio = 4f,
        compAttackMs = 10f, compReleaseMs = 120f, compMakeupDb = null,
        reverbSendDb = null,
        why = "low end: keep the bottom, take out the box, hold it steady"),
    Role.PERCUSSION to Chain(
        hpfHz = 80f,
        eq = listOf(EqBand(2, 400f, -3f, 1.5f)),
        compThrDb = -16f, compRatio = 3f,
        compAttackMs = 15f, compReleaseMs = 100f, compMakeupDb = null,
        reverbSendDb = -14f,
        why = "kit: high-passed, a little air, a touch of room"),
    Role.VOCAL to Chain(
        hpfHz = 100f,
        eq = listOf(EqBand(1, 300f, -3f, 1.5f)),
        compThrDb = -20f, compRatio = 3f,
        compAttackMs = 20f, compReleaseMs = 150f, compMakeupDb = null,
        reverbSendDb = -10f,
        why = "lead vocal: high-passed, chest trimmed, presence up, " +
            "held level, real reverb"),
    Role.BACKING_VOCAL to Chain(
        hpfHz = 120f,
        eq = listOf(EqBand(1, 300f, -3f, 1.5f)),
        compThrDb = -20f, compRatio = 3f,
        compAttackMs = 20f, compReleaseMs = 150f, compMakeupDb = null,
        reverbSendDb = -8f,
        why = "backing vocal: further back, wetter, out of the lead's way"),
    Role.KEYS to Chain(
        hpfHz = 60f,
        eq = listOf(EqBand(2, 300f, -2f, 1.2f)),
        compThrDb = -22f, compRatio = 2f,
        compAttackMs = 30f, compReleaseMs = 200f, compMakeupDb = null,
        reverbSendDb = -16f,
        why = "keys: a wide bed, cleared out of the vocal's low-mids"),
    Role.COLOR to Chain(
        hpfHz = 120f,
        eq = listOf(EqBand(3, 2500f, -2f, 1.5f)),
        compThrDb = -18f, compRatio = 3f,
        compAttackMs = 20f, compReleaseMs = 150f, compMakeupDb = null,
        reverbSendDb = -12f,
        why = "horn or harp: the honk taken off, sitting in some room"),
    Role.SOLO_GTR to Chain(
        hpfHz = 100f,
        eq = listOf(EqBand(3, 2500f, -2f, 1.5f)),
        compThrDb = -18f, compRatio = 3f,
        compAttackMs = 20f, compReleaseMs = 150f, compMakeupDb = null,
        reverbSendDb = -16f,
        why = "lead guitar: harshness trimmed, a little room behind it"),
    Role.RHYTHM_GTR to Chain(
        hpfHz = 120f,
        eq = listOf(EqBand(2, 350f, -2f, 1.2f)),
        compThrDb = -20f, compRatio = 3f,
        compAttackMs = 25f, compReleaseMs = 180f, compMakeupDb = null,
        reverbSendDb = null,
        why = "rhythm guitar: out of the vocal's way, dry, in the bed"),
    // INSTRUMENT and TALK get nothing at all. An unclassified channel is
    // one the app does not understand, and a talkback mic is somebody
    // saying "two, two" into the wedges — neither is a thing to process
    // on a guess.
)

data class TreatmentSettings(
    /** the FX bus reverb is sent to (7..10) */
    val reverbSend: Int = 7,
    /** audio confidence before a chain is worth applying at all */
    val minConfidence: Float = 0.6f,
    /** and how much listening is behind it */
    val minEvidence: Float = 1.0f,
    /**
     * How far the channel's spectrum must move before the chain is
     * reconsidered. Measured as the L1 distance between the normalised
     * spectrum now and the one the chain was built for — the same
     * quantity the identifier uses for flux, so the number means the
     * same thing in both places. A guitarist changing pickup moves this
     * a few hundredths; a different instrument on the socket moves it a
     * great deal.
     */
    val materialChange: Float = 0.55f,
    /** and it must stay changed this long: a solo is not a new instrument */
    val materialHoldSec: Float = 30f,
    /** never re-treat a channel more often than this */
    val minGapSec: Float = 120f,
    /** treat reverb sends as writable at all */
    val reverbEnabled: Boolean = true,
)

/**
 * Applies a starting chain once per instrument, and keeps out of the
 * way afterwards.
 */
class ChannelTreatment(
    private val settings: TreatmentSettings = TreatmentSettings(),
) {
    private class Applied(
        val role: Role,
        val spec: DoubleArray,
        val tSec: Double,
    ) {
        var driftSince = -1.0
    }

    private val applied = HashMap<Int, Applied>()
    /** writes refused because they would have added gain — see put() */
    var refusedGain = 0; private set
    /** bands the human has moved since we set them: never ours again */
    private val handsOff = HashMap<Int, MutableSet<String>>()

    /** what has been done to a channel, for the screen and the log */
    fun treatedRole(ch: Int): Role? = applied[ch]?.role
    fun treatedAt(ch: Int): Double? = applied[ch]?.tSec

    /**
     * The engineer moved something we had set. From here on that
     * parameter is theirs — a re-treat will skip it rather than argue.
     */
    fun humanTouched(ch: Int, address: String) {
        handsOff.getOrPut(ch) { HashSet() }.add(address)
    }

    fun forget(ch: Int) { applied.remove(ch); handsOff.remove(ch) }

    /**
     * Decide whether this channel wants treating, and produce the
     * writes if it does. Empty means "nothing to do", which is the
     * answer almost every time it is called — by design.
     */
    fun consider(
        ch: Int,
        role: Role,
        verdict: InstrumentId.Verdict?,
        evidence: Float,
        spectrum: DoubleArray?,
        tSec: Double,
    ): List<ParamWrite> {
        val chain = STARTING_CHAINS[role] ?: return emptyList()
        val prev = applied[ch]

        if (prev == null) {
            // First time. The AUDIO has to be sure, not the label: a
            // chain built on a channel name is exactly the mistake the
            // whole identifier exists to stop making.
            if (verdict == null || verdict.confidence < settings.minConfidence)
                return emptyList()
            if (evidence < settings.minEvidence) return emptyList()
            return apply(ch, role, chain, spectrum, tSec,
                "first time — ${chain.why}")
        }

        if (tSec - prev.tSec < settings.minGapSec) return emptyList()

        // The instrument itself changed. That is material by definition
        // and needs no spectral corroboration.
        if (role != prev.role)
            return apply(ch, role, chain, spectrum, tSec,
                "now ${role.name.lowercase()} — ${chain.why}")

        // Otherwise the sound has to have genuinely moved, and stayed
        // moved. A solo, a chorus and a singer leaning into the mic all
        // shift a spectrum for a few seconds; none of them is a reason
        // to re-EQ a channel mid-song.
        val now = spectrum ?: return emptyList()
        val d = distance(prev.spec, now)
        if (d < settings.materialChange) { prev.driftSince = -1.0; return emptyList() }
        if (prev.driftSince < 0) { prev.driftSince = tSec; return emptyList() }
        if (tSec - prev.driftSince < settings.materialHoldSec) return emptyList()
        return apply(ch, role, chain, now, tSec,
            "the sound on this channel has changed (%.2f) — re-treating"
                .format(java.util.Locale.ROOT, d))
    }

    /** L1 distance between two normalised spectra, 0..2 */
    private fun distance(a: DoubleArray, b: DoubleArray): Float {
        if (a.size != b.size) return 0f
        var s = 0.0
        for (i in a.indices) s += abs(a[i] - b[i])
        return s.toFloat()
    }

    /** the last reason a chain was applied, for the log */
    var lastReason: String = ""; private set

    private fun apply(
        ch: Int, role: Role, chain: Chain,
        spectrum: DoubleArray?, tSec: Double, why: String,
    ): List<ParamWrite> {
        val out = ArrayList<ParamWrite>()
        val skip = handsOff[ch] ?: emptySet<String>()
        fun put(addr: String, v: Float) {
            if (addr in skip) return
            if (!isSafeAddress(addr)) return   // belt and braces; see the test
            val clamped = v.coerceIn(0f, 1f)
            // NEVER ADD GAIN — see isGainAdding. Checked at the write
            // itself rather than trusted to the book above, because the
            // book is the thing most likely to be edited by somebody who
            // has not read this comment.
            if (isGainAdding(addr, clamped)) { refusedGain++; return }
            out.add(ParamWrite(addr, clamped))
        }
        // The channel number, in ASCII digits, whatever the tablet's
        // locale is. `"%02d".format(ch)` on a device set to a locale
        // with native digits produces a non-ASCII address that the
        // console does not answer to and isSafeAddress rejects — which
        // would silently disable channel treatment for the whole night.
        val c = osc("%02d", ch + 1)

        chain.hpfHz?.let {
            put("/ch/$c/preamp/hpon", 1f)
            put("/ch/$c/preamp/hpf", hpfToFloat(it))
        }
        if (chain.eq.isNotEmpty()) {
            // SWITCHING THE EQ ON IS NOT A NEUTRAL ACT.
            //
            // The chain sets one or two bands and then writes eq/on=1,
            // and the other bands are whatever is in the desk from the
            // last time anybody touched it — a previous band's scene, a
            // house engineer's ring-out, the settings from a soundcheck
            // three months ago. Turning the EQ on over a stored +8 dB
            // at 3 kHz is a boost on an open vocal microphone that
            // isGainAdding never sees, because we never wrote it.
            //
            // So every band this chain does not set is written flat
            // first. What comes out of the EQ is then exactly what this
            // book asked for and nothing else.
            val mine = chain.eq.map { it.band }.toSet()
            for (b in 1..4) if (b !in mine)
                put("/ch/$c/eq/$b/g", eqGainToFloat(0f))
            put("/ch/$c/eq/on", 1f)
            for (b in chain.eq) {
                put("/ch/$c/eq/${b.band}/f", freqToFloat(b.hz))
                put("/ch/$c/eq/${b.band}/g", eqGainToFloat(b.gainDb))
                put("/ch/$c/eq/${b.band}/q", qToFloat(b.q))
            }
        }
        if (chain.compThrDb != null) {
            put("/ch/$c/dyn/thr", thrToFloat(chain.compThrDb))
            chain.compRatio?.let { put("/ch/$c/dyn/ratio", ratioToFloat(it)) }
            chain.compAttackMs?.let {
                put("/ch/$c/dyn/attack", (it / 120f).coerceIn(0f, 1f)) }
            chain.compReleaseMs?.let { put("/ch/$c/dyn/release",
                msToFloat(it, 5f, 4000f)) }
            // The same argument, and a sharper one: makeup is at its
            // maximum below the threshold, which is where a ring
            // decides whether to start. The book never asks for makeup
            // any more, so the desk's stored value is the only way any
            // could arrive — write zero and it cannot.
            put("/ch/$c/dyn/mgain", 0f)
            put("/ch/$c/dyn/on", 1f)
        }
        if (settings.reverbEnabled) chain.reverbSendDb?.let {
            put(osc("/ch/$c/mix/%02d/level", settings.reverbSend),
                FaderLaw.dbToFloat(it))
        }
        if (out.isEmpty()) return emptyList()
        applied[ch] = Applied(role, spectrum ?: DoubleArray(0), tSec)
        lastReason = why
        return out
    }

    companion object {
        /** X-Air parameter laws, in the units the console stores */
        fun eqGainToFloat(db: Float): Float =
            ((db.coerceIn(-15f, 15f) + 15f) / 30f)

        fun thrToFloat(db: Float): Float =
            ((db.coerceIn(-60f, 0f) + 60f) / 60f)

        /** 20 Hz - 20 kHz, logarithmic */
        fun freqToFloat(hz: Float): Float =
            (ln(hz.coerceIn(20f, 20000f) / 20f) / ln(1000f))
                .coerceIn(0f, 1f)

        /** the channel high-pass: 20 - 400 Hz, logarithmic */
        fun hpfToFloat(hz: Float): Float =
            (ln(hz.coerceIn(20f, 400f) / 20f) / ln(20f)).coerceIn(0f, 1f)

        /** Q 10 down to 0.3, logarithmic and INVERTED, as the desk stores it */
        fun qToFloat(q: Float): Float =
            (ln(10f / q.coerceIn(0.3f, 10f)) / ln(10f / 0.3f))
                .coerceIn(0f, 1f)

        /** the desk's ratio list, as an index over its own enumeration */
        private val RATIOS = floatArrayOf(1.1f, 1.3f, 1.5f, 2f, 2.5f, 3f,
            4f, 5f, 7f, 10f, 20f, 100f)

        fun ratioToFloat(r: Float): Float {
            var best = 0
            for (i in RATIOS.indices)
                if (abs(RATIOS[i] - r) < abs(RATIOS[best] - r)) best = i
            return best / max(1f, (RATIOS.size - 1).toFloat())
        }

        fun msToFloat(ms: Float, lo: Float, hi: Float): Float =
            (ln(ms.coerceIn(lo, hi) / lo) / ln(hi / lo)).coerceIn(0f, 1f)
    }
}
