package com.stagemix.engine

import kotlin.math.abs

/**
 * Channel Doctor: per-channel EQ + compressor tending, snapshot-anchored.
 *
 * Same constitution as the level engine — the soundcheck is the sound
 * the engineer approved; this only corrects drift back toward it:
 *
 *  EQ: the mixer's 100-bin RTA (round-robined across channels by the
 *  service) is folded into 4 coarse bands aligned with the channel's
 *  4-band EQ. When a band's long-term average drifts >2.5 dB from its
 *  soundcheck reference, the matching EQ band GAIN is corrected —
 *  clamped to +-2 dB from the soundcheck gain, slewed 0.25 dB/tick,
 *  cut-preferred (boosts obey the global upward gate). Band frequency,
 *  Q and type are never touched: tone design stays human.
 *
 *  Comp: the soundcheck records how hard each channel's compressor was
 *  actually working (gain-reduction EMA while active). If the GR
 *  profile collapses (singer backed off the mic -> comp never catches)
 *  or pins deep, the THRESHOLD is eased toward restoring the
 *  soundcheck GR — clamped +-4 dB, slewed, only for channels whose
 *  comp was genuinely working at soundcheck (|ref GR| >= 1 dB). Ratio,
 *  attack, release: never touched.
 */

/** A parameter write in mixer float units, ready to send. */
data class ParamWrite(val address: String, val value: Float)

data class DoctorSettings(
    val eqMaxDb: Float = 2.0f,          // from snapshot gain
    val eqDeadbandDb: Float = 2.5f,     // band drift before correcting
    val eqStepDb: Float = 0.25f,        // per tick
    val thrMaxDb: Float = 4.0f,         // from snapshot threshold
    val thrDeadbandDb: Float = 1.5f,
    val thrStepDb: Float = 0.25f,
    val bandTauSec: Float = 20f,        // RTA band EMA
    val grTauSec: Float = 20f,
)

class ToneDoctor(
    channelIndices: List<Int>,
    roles: Map<Int, Role> = emptyMap(),
    val settings: DoctorSettings = DoctorSettings(),
) {
    class ChState {
        var role: Role = Role.INSTRUMENT
        // soundcheck anchors
        var eqSnapshotDb: FloatArray? = null    // 4 band gains, dB
        var thrSnapshotDb: Float? = null
        var refBands: FloatArray? = null        // 4-band LTAS reference, dB
        var refGr: Float? = null                // soundcheck comp GR EMA
        // live measurement
        var liveBands: FloatArray? = null
        var grEma: Float? = null
        // singer register (vocal channels): 0 = low/male fundamental,
        // 1 = high/female — each keeps its OWN spectral reference so a
        // singer swap is adapted to, never fought
        var register = 0
        val regRefs = HashMap<Int, FloatArray?>()
        // automation offsets (current, slewed) and targets
        val eqOffset = FloatArray(4)
        val eqTarget = FloatArray(4)
        var thrOffset = 0f
        var thrTarget = 0f
        var frozen = false
        var eqEnabled = true
        var compEnabled = true
    }

    val state = channelIndices.associateWith { ChState() }
    var snapshotTaken = false; private set

    init {
        for ((ch, r) in roles) state[ch]?.role = r
    }

    fun setRole(ch: Int, role: Role) { state[ch]?.role = role }

    // ------------------------------------------------------------------
    /** 100-bin RTA frame (dB) attributed to one channel by the service. */
    fun onRta(ch: Int, bins: FloatArray, tSec: Double) {
        val st = state[ch] ?: return
        if (bins.size < 100) return
        // Vocal channels: detect the singer's register from where the
        // fundamental lives. A register change means a DIFFERENT SINGER
        // (or a real range shift) — swap to that register's own
        // reference instead of "correcting" the new voice toward the
        // old one. First sighting of a register adopts its sound as-is.
        if (st.role == Role.VOCAL || st.role == Role.BACKING_VOCAL) {
            val reg = vocalRegister(bins)
            if (reg != null && reg != st.register) {
                st.regRefs[st.register] = st.refBands
                st.register = reg
                st.refBands = st.regRefs[reg]
                st.liveBands = null   // fresh measurement for this voice
            }
        }
        val bands = foldBands(bins)
        val alpha = (3f / settings.bandTauSec).coerceIn(0.01f, 1f)
        val live = st.liveBands
        st.liveBands = if (live == null) bands
        else FloatArray(4) { live[it] + alpha * (bands[it] - live[it]) }
        // lazy reference: first full measurement after snapshot anchors it
        if (snapshotTaken && st.refBands == null) st.refBands = st.liveBands
    }

    /**
     * Register from the RTA's low bins (10 bins/octave from 20 Hz):
     * ~bins 23-31 span ≈ 98-170 Hz (male fundamentals), 32-40 span
     * ≈ 180-320 Hz (female). 3 dB margin = hysteresis.
     */
    private fun vocalRegister(bins: FloatArray): Int? {
        var lo = 0f; var hi = 0f
        for (i in 23..31) lo += bins[i]
        for (i in 32..40) hi += bins[i]
        lo /= 9f; hi /= 9f
        return when {
            lo > hi + 3f -> 0
            hi > lo + 3f -> 1
            else -> null
        }
    }

    /** Comp gain reduction (negative dB) for one channel. */
    fun onGainReduction(ch: Int, grDb: Float, tSec: Double) {
        if (grDb > 0.5f || grDb < -40f) return  // implausible -> ignore
        val st = state[ch] ?: return
        val alpha = (1f / settings.grTauSec).coerceIn(0.01f, 1f)
        st.grEma = st.grEma?.let { it + alpha * (grDb - it) } ?: grDb
        if (snapshotTaken && st.refGr == null) st.refGr = st.grEma
    }

    /**
     * Soundcheck: adopt current EQ gains + comp threshold as anchors,
     * current measurements as references, zero all offsets.
     */
    fun snapshotChannel(ch: Int, eqGainsDb: FloatArray?, thrDb: Float?) {
        val st = state[ch] ?: return
        st.eqSnapshotDb = eqGainsDb?.copyOf()
        st.thrSnapshotDb = thrDb
        st.refBands = st.liveBands?.copyOf()
        st.regRefs[st.register] = st.refBands
        st.refGr = st.grEma
        st.eqOffset.fill(0f); st.eqTarget.fill(0f)
        st.thrOffset = 0f; st.thrTarget = 0f
        snapshotTaken = true
    }

    fun reset(ch: Int): List<ParamWrite> {
        val st = state[ch] ?: return emptyList()
        st.eqOffset.fill(0f); st.eqTarget.fill(0f)
        st.thrOffset = 0f; st.thrTarget = 0f
        return writesFor(ch, st, all = true)
    }

    // ------------------------------------------------------------------
    /**
     * 1 Hz decision + slew. activeCh: channels currently active (from the
     * level engine's gates); upAllowed: the global upward-motion gate —
     * EQ boosts and threshold RAISES both wait for it.
     */
    fun tick(activeCh: Set<Int>, upAllowed: Boolean,
             frozenAll: Boolean): List<ParamWrite> {
        if (!snapshotTaken || frozenAll) return emptyList()
        val out = ArrayList<ParamWrite>()
        for ((ch, st) in state) {
            if (st.frozen || ch !in activeCh) continue
            // -- EQ targets from band drift
            val ref = st.refBands; val live = st.liveBands
            val eqSnap = st.eqSnapshotDb
            if (st.eqEnabled && ref != null && live != null && eqSnap != null) {
                for (b in 0 until 4) {
                    val drift = live[b] - ref[b]
                    st.eqTarget[b] = if (abs(drift) <= settings.eqDeadbandDb) 0f
                    else (-drift).coerceIn(-settings.eqMaxDb, settings.eqMaxDb)
                }
            }
            // -- comp threshold target from GR drift
            val refGr = st.refGr; val gr = st.grEma
            if (st.compEnabled && refGr != null && gr != null
                && st.thrSnapshotDb != null && refGr <= -1f) {
                val delta = refGr - gr   // negative: comp too shallow now
                st.thrTarget = if (abs(delta) <= settings.thrDeadbandDb) 0f
                else delta.coerceIn(-settings.thrMaxDb, settings.thrMaxDb)
            }
            // -- slew + emit
            out.addAll(slewAndWrite(ch, st, upAllowed))
        }
        return out
    }

    private fun slewAndWrite(ch: Int, st: ChState,
                             upAllowed: Boolean): List<ParamWrite> {
        val out = ArrayList<ParamWrite>()
        val eqSnap = st.eqSnapshotDb
        if (eqSnap != null) for (b in 0 until 4) {
            val step = step(st.eqOffset[b], st.eqTarget[b],
                settings.eqStepDb, upAllowed)
            if (step != 0f) {
                st.eqOffset[b] += step
                val db = (eqSnap[b] + st.eqOffset[b]).coerceIn(-15f, 15f)
                out.add(ParamWrite(
                    "/ch/%02d/eq/%d/g".format(ch + 1, b + 1), (db + 15f) / 30f))
            }
        }
        val thrSnap = st.thrSnapshotDb
        if (thrSnap != null) {
            // raising the threshold reduces compression = "upward"/riskier
            val step = step(st.thrOffset, st.thrTarget,
                settings.thrStepDb, upAllowed)
            if (step != 0f) {
                st.thrOffset += step
                val db = (thrSnap + st.thrOffset).coerceIn(-60f, 0f)
                out.add(ParamWrite(
                    "/ch/%02d/dyn/thr".format(ch + 1), (db + 60f) / 60f))
            }
        }
        return out
    }

    private fun step(cur: Float, tgt: Float, maxStep: Float,
                     upAllowed: Boolean): Float {
        val d = tgt - cur
        if (abs(d) < 0.05f) return 0f
        if (d > 0f && !upAllowed) return 0f
        return d.coerceIn(-maxStep, maxStep)
    }

    private fun writesFor(ch: Int, st: ChState, all: Boolean): List<ParamWrite> {
        val out = ArrayList<ParamWrite>()
        st.eqSnapshotDb?.let { snap ->
            for (b in 0 until 4)
                out.add(ParamWrite("/ch/%02d/eq/%d/g".format(ch + 1, b + 1),
                    (snap[b].coerceIn(-15f, 15f) + 15f) / 30f))
        }
        st.thrSnapshotDb?.let {
            out.add(ParamWrite("/ch/%02d/dyn/thr".format(ch + 1),
                (it.coerceIn(-60f, 0f) + 60f) / 60f))
        }
        return out
    }

    fun offsets(ch: Int): Pair<FloatArray, Float>? =
        state[ch]?.let { it.eqOffset.copyOf() to it.thrOffset }

    companion object {
        /**
         * Fold the X-Air 100-bin log RTA (20 Hz..~20 kHz, 10 bins/octave)
         * into 4 bands: low <120, low-mid 120-800, high-mid 800-5k,
         * high >5k — matching a typical 4-band channel EQ layout.
         */
        fun foldBands(bins: FloatArray): FloatArray {
            val edges = intArrayOf(0, 26, 54, 80, 100)
            return FloatArray(4) { b ->
                var sum = 0f; var n = 0
                for (i in edges[b] until minOf(edges[b + 1], bins.size)) {
                    sum += bins[i]; n++
                }
                if (n > 0) sum / n else -90f
            }
        }
    }
}
