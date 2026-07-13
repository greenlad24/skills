package com.stagemix.engine

import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

/**
 * StageMix core: a corrective, cut-biased, snapshot-anchored auto mix
 * engineer for stage monitors on an M-Air/X-Air mixer.
 *
 * Design contract (from the research synthesis — every rule below maps
 * to a cited failure mode of automating live sound):
 *
 *  - The soundcheck snapshot is the constitution. The engine only ever
 *    corrects BACK TOWARD the human-approved balance; it never invents
 *    one.
 *  - It automates BUS SEND LEVELS ONLY (monitor wedges). Never main LR,
 *    never headamp gain, never EQ.
 *  - Asymmetric bounds per send: [snapshot - 9 dB, snapshot + 3 dB].
 *    The +3 cap stays inside a standard 6 dB ring-out margin even if
 *    two paths rise together (NOM rule: 2x open paths = -3 dB GBF).
 *  - Asymmetric slew: boosts creep (<= 1 dB per 3 s), cuts act
 *    (<= 3 dB/s). Total concurrent upward budget per bus <= 3 dB.
 *  - +-2 dB deadband: musicians' dynamics are not drift.
 *  - Freeze conditions kill all UPWARD motion: channel inactive, any
 *    input near clip, meter dropout, sudden broadband change (song
 *    start/stop), external watchdog veto (feedback suspicion).
 *  - Vocal priority is CUT-ONLY: duck the band in the singer's wedge,
 *    never boost the vocal.
 *  - Everything is bounded, logged, reversible (revert-to-snapshot).
 */

enum class Role { VOCAL, INSTRUMENT, TALK }

data class ChannelConfig(
    val index: Int,              // 0-based (ch 1 = 0)
    val name: String,
    val role: Role = Role.INSTRUMENT,
)

data class BusConfig(
    val index: Int,              // 0-based (bus 1 = 0)
    val name: String,
    /** Channel index of the vocal that owns this wedge (for ducking), or null. */
    val vocalChannel: Int? = null,
)

data class EngineSettings(
    val deadbandDb: Float = 2.0f,
    val maxBoostDb: Float = 3.0f,        // above snapshot
    val maxCutDb: Float = 9.0f,          // below snapshot
    val boostPerSecDb: Float = 1f / 3f,  // 1 dB per 3 s
    val cutPerSecDb: Float = 3.0f,
    val busBoostBudgetDb: Float = 3.0f,  // sum of positive offsets per bus
    val emaTauSec: Float = 45f,
    val activityEnterDb: Float = -45f,
    val activityExitDb: Float = -55f,
    val clipFreezeDb: Float = -3f,
    val clipHoldSec: Float = 2f,
    val meterTimeoutSec: Float = 1f,
    val broadbandJumpDb: Float = 6f,
    val broadbandHoldSec: Float = 5f,
    val idleRampAfterSec: Float = 60f,
    val idleCutDb: Float = 6f,
    val duckMaxDb: Float = 4f,
    val duckTriggerDb: Float = 3f,       // ratio worse than snapshot by this
    val restoreVelocityDb: Float = 6f,   // toward snapshot after idle (per s)
)

/** One engine decision, for the on-screen activity feed / audit log. */
data class Decision(
    val tSec: Double,
    val kind: String,        // drift | duck | idle | restore | freeze | revert
    val channel: Int?,
    val bus: Int?,
    val deltaDb: Float,
    val reason: String,
)

/** An OSC-ready send-level write (bus sends are /mix/01../06 on X-Air). */
data class SendWrite(val channel: Int, val bus: Int, val levelDb: Float) {
    val address get() = "/ch/%02d/mix/%02d/level".format(channel + 1, bus + 1)
}

class ChannelState(val cfg: ChannelConfig) {
    var refDb: Float? = null         // soundcheck loudness reference (EMA)
    var liveEma: Float? = null       // running active-only loudness EMA
    var active = false
    var lastActiveT = 0.0
    var lastLevelDb = -128f
    var frozen = false               // per-channel human lock
    var idleRamped = false
}

class StageEngine(
    channels: List<ChannelConfig>,
    val buses: List<BusConfig>,
    val settings: EngineSettings = EngineSettings(),
) {
    val channels = channels.associateBy { it.index }
    val state = channels.associate { it.index to ChannelState(it) }

    /** snapshot send levels in dB: (ch, bus) -> dB */
    private val snapshot = HashMap<Pair<Int, Int>, Float>()
    /** current automation offset from snapshot in dB, slewed */
    private val offset = HashMap<Pair<Int, Int>, Float>()
    /** where the offset is headed */
    private val target = HashMap<Pair<Int, Int>, Float>()
    /** duck offsets (kept separate so they release independently) */
    private val duck = HashMap<Pair<Int, Int>, Float>()

    var snapshotTaken = false; private set
    var frozenAll = false
    var watchdogVeto = false          // external feedback watchdog authority

    private var lastMeterT = -1.0
    private var lastTickT = -1.0
    private var clipHoldUntil = 0.0
    private var broadbandHoldUntil = 0.0
    private var lastMixMean: Float? = null
    val decisions = ArrayDeque<Decision>()

    // ------------------------------------------------------------------
    /** Feed one /meters/1 frame (~20 Hz). levels[i] = input ch i dBFS. */
    fun onMeters(levels: FloatArray, tSec: Double) {
        lastMeterT = tSec
        var mean = 0f
        var n = 0
        for ((idx, st) in state) {
            val db = levels.getOrNull(idx) ?: continue
            st.lastLevelDb = db
            // activity hysteresis
            if (!st.active && db > settings.activityEnterDb) st.active = true
            else if (st.active && db < settings.activityExitDb) st.active = false
            if (st.active) {
                st.lastActiveT = tSec
                // EMA over active samples only (Mansbridge-style gate)
                val alpha = (0.05f / settings.emaTauSec).coerceIn(0f, 1f)
                st.liveEma = st.liveEma?.let { it + alpha * (db - it) } ?: db
                mean += db; n += 1
            }
            if (db > settings.clipFreezeDb)
                clipHoldUntil = tSec + settings.clipHoldSec
        }
        if (n > 0) {
            val m = mean / n
            lastMixMean?.let {
                if (abs(m - it) > settings.broadbandJumpDb)
                    broadbandHoldUntil = tSec + settings.broadbandHoldSec
            }
            lastMixMean = m
        }
    }

    /**
     * Soundcheck: adopt the mixer's CURRENT send levels + current channel
     * loudness as the reference. sends: (ch, bus) -> current level dB.
     */
    fun takeSnapshot(sends: Map<Pair<Int, Int>, Float>, tSec: Double) {
        snapshot.clear(); snapshot.putAll(sends)
        offset.keys.retainAll(sends.keys)
        for (k in sends.keys) { offset[k] = 0f; target[k] = 0f; duck[k] = 0f }
        for (st in state.values) {
            st.refDb = st.liveEma
            st.idleRamped = false
        }
        snapshotTaken = true
        log(tSec, "revert", null, null, 0f, "soundcheck snapshot taken " +
                "(${sends.size} sends, ${state.values.count { it.refDb != null }} refs)")
    }

    /** Full reset to the human-approved mix. Returns the writes to send. */
    fun revertToSnapshot(tSec: Double): List<SendWrite> {
        if (!snapshotTaken) return emptyList()
        val out = ArrayList<SendWrite>()
        for ((k, snapDb) in snapshot) {
            offset[k] = 0f; target[k] = 0f; duck[k] = 0f
            out.add(SendWrite(k.first, k.second, snapDb))
        }
        log(tSec, "revert", null, null, 0f, "reverted all sends to soundcheck")
        return out
    }

    // ------------------------------------------------------------------
    private fun upwardAllowed(tSec: Double): Boolean =
        !frozenAll && !watchdogVeto && tSec >= clipHoldUntil &&
                tSec >= broadbandHoldUntil &&
                (lastMeterT >= 0 && tSec - lastMeterT <= settings.meterTimeoutSec)

    private fun anyMotionAllowed(tSec: Double): Boolean =
        !frozenAll &&
                (lastMeterT >= 0 && tSec - lastMeterT <= settings.meterTimeoutSec)

    /**
     * Decision + slew tick (~1 Hz). Returns the OSC writes to apply.
     */
    fun tick(tSec: Double): List<SendWrite> {
        if (!snapshotTaken) { lastTickT = tSec; return emptyList() }
        val dt = if (lastTickT < 0) 1.0 else (tSec - lastTickT).coerceIn(0.0, 5.0)
        lastTickT = tSec
        if (!anyMotionAllowed(tSec)) return emptyList()
        val up = upwardAllowed(tSec)

        // -- 1. drift correction targets ---------------------------------
        for ((idx, st) in state) {
            if (st.frozen) continue
            val ref = st.refDb ?: continue
            val live = st.liveEma ?: continue
            val idleFor = tSec - st.lastActiveT
            if (idleFor > settings.idleRampAfterSec) {
                // idle channel: ease its sends down (not a mute)
                if (!st.idleRamped) {
                    st.idleRamped = true
                    forEachSend(idx) { k -> target[k] = -settings.idleCutDb }
                    log(tSec, "idle", idx, null, -settings.idleCutDb,
                        "${st.cfg.name} idle ${idleFor.toInt()}s — easing out of wedges")
                }
                continue
            }
            if (st.idleRamped && st.active) {
                st.idleRamped = false
                forEachSend(idx) { k -> target[k] = 0f }
                log(tSec, "restore", idx, null, 0f,
                    "${st.cfg.name} back — restoring to soundcheck level")
            }
            if (!st.active) continue
            val drift = live - ref                    // + means got louder
            if (abs(drift) <= settings.deadbandDb) {
                forEachSend(idx) { k ->
                    if (!st.idleRamped && abs(target[k] ?: 0f) > 0.01f
                        && (duck[k] ?: 0f) == 0f) target[k] = 0f
                }
                continue
            }
            // correction opposes drift, clamped to rails
            val corr = (-drift).coerceIn(-settings.maxCutDb, settings.maxBoostDb)
            forEachSend(idx) { k ->
                if ((target[k] ?: 0f) != corr) {
                    target[k] = corr
                    log(tSec, "drift", idx, k.second, corr,
                        "${st.cfg.name} drifted %+.1f dB vs soundcheck".format(drift))
                }
            }
        }

        // -- 2. vocal priority: cut-only ducking per wedge ----------------
        for (bus in buses) {
            val vIdx = bus.vocalChannel ?: continue
            val v = state[vIdx] ?: continue
            val vRef = v.refDb; val vLive = v.liveEma
            if (vRef == null || vLive == null) continue
            val band = state.values.filter {
                it.cfg.index != vIdx && it.cfg.role == Role.INSTRUMENT &&
                        it.active && it.refDb != null && it.liveEma != null
            }
            if (band.isEmpty()) continue
            val bandLive = band.map { it.liveEma!! }.average().toFloat()
            val bandRef = band.map { it.refDb!! }.average().toFloat()
            val ratioNow = vLive - bandLive
            val ratioRef = vRef - bandRef
            val needDuck = v.active && ratioNow < ratioRef - settings.duckTriggerDb
            for (st in band) {
                val k = st.cfg.index to bus.index
                if (k !in snapshot) continue
                val want = if (needDuck)
                    -min(settings.duckMaxDb, (ratioRef - ratioNow))
                else 0f
                val cur = duck[k] ?: 0f
                if (needDuck && want < cur - 0.5f) {
                    duck[k] = want
                    log(tSec, "duck", st.cfg.index, bus.index, want,
                        "vocal buried in ${bus.name} — ducking ${st.cfg.name}")
                } else if (!needDuck && cur < -0.01f) {
                    // slow release: 1 dB per tick
                    duck[k] = min(0f, cur + (1f * dt).toFloat())
                }
            }
        }

        // -- 3. slew offsets toward target+duck, apply rails --------------
        val writes = ArrayList<SendWrite>()
        val busBoostUsed = HashMap<Int, Float>()
        for ((k, snapDb) in snapshot) {
            val st = state[k.first] ?: continue
            if (st.frozen) continue
            val tgt = ((target[k] ?: 0f) + (duck[k] ?: 0f))
                .coerceIn(-settings.maxCutDb, settings.maxBoostDb)
            var cur = offset[k] ?: 0f
            if (abs(tgt - cur) < 0.05f) continue
            var step = if (tgt > cur) {
                if (!up) 0f
                else {
                    // per-bus upward budget
                    val used = busBoostUsed.getOrDefault(k.second, currentBusBoost(k.second, k.first))
                    val room = (settings.busBoostBudgetDb - used).coerceAtLeast(0f)
                    min(min((settings.boostPerSecDb * dt).toFloat(), tgt - cur),
                        max(0f, room - max(0f, cur)))
                }
            } else {
                -min((settings.cutPerSecDb * dt).toFloat(), cur - tgt)
            }
            if (abs(step) < 0.01f) continue
            cur += step
            offset[k] = cur
            if (cur > 0f) busBoostUsed[k.second] =
                busBoostUsed.getOrDefault(k.second, currentBusBoost(k.second, k.first)) + step
            writes.add(SendWrite(k.first, k.second,
                (snapDb + cur).coerceIn(FaderLaw.MIN_DB, FaderLaw.MAX_DB)))
        }
        return writes
    }

    private fun currentBusBoost(bus: Int, exceptCh: Int): Float =
        offset.entries.filter { it.key.second == bus && it.key.first != exceptCh }
            .sumOf { max(0f, it.value).toDouble() }.toFloat()

    private inline fun forEachSend(ch: Int, f: (Pair<Int, Int>) -> Unit) {
        for (bus in buses) {
            val k = ch to bus.index
            if (k in snapshot) f(k)
        }
    }

    // ------------------------------------------------------------------
    fun freezeChannel(ch: Int, frozen: Boolean): Boolean {
        val st = state[ch] ?: return false
        st.frozen = frozen
        return true
    }

    fun offsetDb(ch: Int, bus: Int): Float = offset[ch to bus] ?: 0f
    fun targetDb(ch: Int, bus: Int): Float =
        ((target[ch to bus] ?: 0f) + (duck[ch to bus] ?: 0f))
            .coerceIn(-settings.maxCutDb, settings.maxBoostDb)

    fun meterFresh(tSec: Double): Boolean =
        lastMeterT >= 0 && tSec - lastMeterT <= settings.meterTimeoutSec

    fun holdReason(tSec: Double): String? = when {
        frozenAll -> "FROZEN by operator"
        watchdogVeto -> "feedback watchdog veto"
        !meterFresh(tSec) -> "meters lost — holding still"
        tSec < clipHoldUntil -> "input near clip — no boosts"
        tSec < broadbandHoldUntil -> "big level change — waiting"
        else -> null
    }

    private fun log(t: Double, kind: String, ch: Int?, bus: Int?,
                    delta: Float, reason: String) {
        decisions.addFirst(Decision(t, kind, ch, bus, delta, reason))
        while (decisions.size > 60) decisions.removeLast()
    }
}
