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
    // harshness guard: 2-6 kHz towering over the channel's own body
    val harshThresholdDb: Float = 6f,
    val harshMaxCutDb: Float = 2f,
    val harshTauSec: Float = 8f,        // reacts in seconds, not minutes
    val harshAllowanceDb: Float = 3f,   // headroom over the approved tone
    /**
     * Compressor-threshold tending rides on the /meters/6 layout, which
     * is an ASSUMPTION about which field carries comp gain reduction.
     * Automating on an unverified meter index is how a plausible-looking
     * wrong field walks a threshold to its rail, so this stays OFF until
     * the layout is confirmed against the actual console. EQ tending
     * (from the RTA, whose layout is verified) is unaffected.
     */
    val compTendingEnabled: Boolean = false,
)

/** consecutive RTA frames a new vocal register must hold to be adopted */
const val REGISTER_DEBOUNCE_FRAMES = 40

/** samples inspected by the stuck-GR-telemetry gate, and its floor */
const val GR_WINDOW = 30
const val GR_MIN_VARIANCE = 0.05f

/** above this mean GR the compressor is simply idle, not mis-metered */
const val GR_IDLE_DB = -1.0f

/** identical non-zero GR readings in a row that mark frozen telemetry */
const val GR_FROZEN_STREAK = 4

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
        /** harshness score: 2-6 kHz vs the channel's own body (EMA) */
        var harshEma: Float? = null
        /** register-change debounce state */
        var pendingReg = -1
        var pendingRegCount = 0
        var lastRtaT = -1.0
        var lastGrT = -1.0
        /** rolling GR window for the stuck-telemetry gate */
        val grWindow = ArrayList<Float>()
        var grSameCount = 0
        var grTrusted = true
        /** harshness measured at snapshot: the approved tone */
        var refHarsh: Float? = null
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
        // NaN/Inf in one bin must never propagate into an EQ write
        for (v in bins) if (v.isNaN() || v.isInfinite()) return
        // Vocal channels: detect the singer's register from where the
        // fundamental lives. A register change means a DIFFERENT SINGER
        // (or a real range shift) — swap to that register's own
        // reference instead of "correcting" the new voice toward the
        // old one. First sighting of a register adopts its sound as-is.
        if (st.role == Role.VOCAL || st.role == Role.BACKING_VOCAL) {
            val reg = vocalRegister(bins)
            // Debounce: a singer near the male/female boundary (or with
            // vibrato) must not flap registers frame to frame — each
            // flap would blind the doctor by resetting its measurement.
            if (reg != null && reg != st.register) {
                st.pendingReg = if (reg == st.pendingReg) st.pendingReg else reg
                st.pendingRegCount = if (reg == st.pendingReg)
                    st.pendingRegCount + 1 else 1
            } else if (reg == st.register) {
                st.pendingRegCount = 0
            }
            if (reg != null && reg != st.register &&
                st.pendingRegCount >= REGISTER_DEBOUNCE_FRAMES) {
                st.pendingRegCount = 0
                st.regRefs[st.register] = st.refBands
                st.register = reg
                st.refBands = st.regRefs[reg]
                st.liveBands = null   // fresh measurement for this voice
            }
        }
        val bands = foldBands(bins)
        // The service feeds RTA at the console's ~20 Hz, not the 3 s
        // this used to assume — the "20 second average" was really a
        // third of a second, so the doctor corrected tone against a
        // single chorus.
        val dt = if (st.lastRtaT < 0) 0.05f
        else (tSec - st.lastRtaT).toFloat().coerceIn(0f, 3f)
        st.lastRtaT = tSec
        val alpha = (dt / settings.bandTauSec).coerceIn(0.0005f, 1f)
        val live = st.liveBands
        st.liveBands = if (live == null) bands
        else FloatArray(4) { live[it] + alpha * (bands[it] - live[it]) }
        // lazy reference: first full measurement after snapshot anchors it
        if (snapshotTaken && st.refBands == null) st.refBands = st.liveBands
        // harshness: 2-6 kHz (bins ~66..82) vs the channel's own body
        // (~120 Hz-1.6 kHz, bins 26..60). ABSOLUTE, unlike the drift
        // reference — a channel that ARRIVES harsh is still harsh.
        var hi = 0f; var body = 0f
        for (i in 66..82) hi += bins[i]
        for (i in 26..60) body += bins[i]
        val harsh = hi / 17f - body / 35f
        val ha = (dt / settings.harshTauSec).coerceIn(0.0005f, 1f)
        st.harshEma = st.harshEma?.let { it + ha * (harsh - it) } ?: harsh
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
        if (grDb.isNaN() || grDb.isInfinite()) return
        if (grDb > 0.5f || grDb < -40f) return  // implausible -> ignore
        val st = state[ch] ?: return
        // Stuck-telemetry gate: the /meters/6 layout is an assumption,
        // so a plausible-LOOKING but frozen value must never be allowed
        // to walk a compressor threshold to its rail. Real gain
        // reduction breathes with the music; a constant is a wrong
        // index, not a compressor.
        // exact repeats: real GR is quantized but rarely bit-identical
        // many times in a row — a frozen field is telemetry, not audio
        if (st.grWindow.isNotEmpty() && st.grWindow.last() == grDb)
            st.grSameCount++
        else st.grSameCount = 0
        st.grWindow.add(grDb)
        if (st.grWindow.size > GR_WINDOW) st.grWindow.removeAt(0)
        if (st.grSameCount >= GR_FROZEN_STREAK && grDb <= GR_IDLE_DB) {
            st.grTrusted = false
            return
        }
        if (st.grWindow.size >= GR_WINDOW) {
            val m = st.grWindow.sum() / st.grWindow.size
            val v = st.grWindow.sumOf { ((it - m) * (it - m)).toDouble() }
                .toFloat() / st.grWindow.size
            // A frozen NON-ZERO reading is a wrong meter index. A
            // steady near-zero reading is a compressor that simply
            // isn't working right now — which is exactly the signal we
            // must act on when a singer backs off the mic.
            st.grTrusted = v > GR_MIN_VARIANCE || m > GR_IDLE_DB
        }
        val gdt = if (st.lastGrT < 0) 0.05f
        else (tSec - st.lastGrT).toFloat().coerceIn(0f, 3f)
        st.lastGrT = tSec
        val alpha = (gdt / settings.grTauSec).coerceIn(0.0005f, 1f)
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
        st.refHarsh = st.harshEma
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
                    var t = if (abs(drift) <= settings.eqDeadbandDb) 0f
                    else (-drift).coerceIn(-settings.eqMaxDb, settings.eqMaxDb)
                    // harshness guard (cut-only, high-mid band): shrill
                    // guitar amps, piercing harmonica, edgy vocal mics —
                    // softened up to the rail, released when it passes.
                    // Foundation & percussion excluded (kick click and
                    // cymbals are bright by nature).
                    if (b == 2 && st.role != Role.FOUNDATION &&
                        st.role != Role.PERCUSSION) {
                        // The tone at takeover is the tone the engineer
                        // approved: a deliberately edgy guitar or a
                        // belting singer with real presence must not be
                        // fought all night. Only harshness ABOVE that
                        // approved level (or above the absolute
                        // threshold, whichever is higher) is eased.
                        val anchor = st.refHarsh?.let {
                            maxOf(settings.harshThresholdDb,
                                  it + settings.harshAllowanceDb)
                        } ?: settings.harshThresholdDb
                        val over = (st.harshEma ?: -99f) - anchor
                        if (over > 0f) {
                            val cut = -over.coerceAtMost(settings.harshMaxCutDb)
                            t = minOf(t, cut)
                                .coerceIn(-settings.eqMaxDb, settings.eqMaxDb)
                        }
                    }
                    // CUT-ONLY, LIKE EVERYTHING ELSE THIS APP WRITES.
                    //
                    // The rest of the processing path was made cut-only
                    // and this was left behind: a band that has drifted
                    // DOWN produced a positive target, so the doctor
                    // pushed the band up to two dB above the setting the
                    // engineer approved — on an open microphone, and on
                    // an X-Air the aux sends tap after the EQ, so it
                    // landed in all six wedges as well.
                    //
                    // A band being quieter than it was is not a fault
                    // worth reaching for. What is left is the half that
                    // is always safe: take out what has grown, release
                    // it when it goes away. Zero is the snapshot, so
                    // releasing a cut still moves upward — back to what
                    // the engineer set and no further.
                    st.eqTarget[b] = minOf(t, 0f)
                }
            }
            // -- comp threshold target from GR drift
            val refGr = st.refGr; val gr = st.grEma
            if (settings.compTendingEnabled && st.compEnabled && st.grTrusted
                && refGr != null && gr != null
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
                    osc("/ch/%02d/eq/%d/g", ch + 1, b + 1), (db + 15f) / 30f))
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
                    osc("/ch/%02d/dyn/thr", ch + 1), (db + 60f) / 60f))
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
                out.add(ParamWrite(osc("/ch/%02d/eq/%d/g", ch + 1, b + 1),
                    (snap[b].coerceIn(-15f, 15f) + 15f) / 30f))
        }
        st.thrSnapshotDb?.let {
            out.add(ParamWrite(osc("/ch/%02d/dyn/thr", ch + 1),
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
            val raw = FloatArray(4) { b ->
                var sum = 0f; var n = 0
                for (i in edges[b] until minOf(edges[b + 1], bins.size)) {
                    sum += bins[i]; n++
                }
                if (n > 0) sum / n else -90f
            }
            // Normalise to the frame's own broadband mean, so what is
            // compared is the SHAPE of the tone. On absolute levels a
            // channel that merely got louder than at takeover read as
            // drift in all four bands at once, and the doctor answered
            // with a +-2 dB gain trim through the EQ — a hidden second
            // gain stage fighting the level engine.
            val mean = raw.sum() / 4f
            return FloatArray(4) { raw[it] - mean }
        }
    }
}
