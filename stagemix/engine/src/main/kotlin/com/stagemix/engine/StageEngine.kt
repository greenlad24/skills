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

/**
 * Balance-ladder roles, bottom to top:
 *   FOUNDATION  kick + bass / synth bass — the dominant anchor
 *   KEYS        piano / keys, sitting on the foundation
 *   PERCUSSION  congas / hand percussion, with the rhythm layer
 *   RHYTHM_GTR  rhythm guitar (when present)
 *   SOLO_GTR    solo guitar
 *   COLOR       featured melodic color — sax, harmonica, horns
 *   BACKING_VOCAL  in the mix, under the main vocal
 *   VOCAL       main vocal on top
 * INSTRUMENT = unclassified (absolute drift correction only);
 * TALK = speech mics (never part of the ladder).
 *
 * The ladder's exact heights come from YOUR soundcheck — roles decide
 * which channels anchor the pyramid, which duck for the vocal, and how
 * strips are labeled; the ratios themselves are whatever you mixed.
 */
enum class Role {
    FOUNDATION, KEYS, PERCUSSION, RHYTHM_GTR, SOLO_GTR, COLOR,
    BACKING_VOCAL, VOCAL, INSTRUMENT, TALK;

    /** Ladder members hold a ratio to the foundation anchor. */
    fun inLadder(): Boolean = this != INSTRUMENT && this != TALK
}

/** Infer a ladder role from a console channel name ("Kick", "SynBass"…). */
fun inferRole(name: String): Role {
    val n = name.lowercase()
    fun has(vararg keys: String) = keys.any { it in n }
    return when {
        has("talk", "tb ", "announce", "speech") -> Role.TALK
        // harmonica BEFORE backing vocals: "harm" alone means harmonies
        has("harmonica", "blues harp", "sax", "horn", "trumpet", "flute",
            "tromb") -> Role.COLOR
        has("bgv", "bvox", "backing", "back ", "choir", "harmony",
            "harm ") -> Role.BACKING_VOCAL
        has("vox", "vocal", "sing", "voice", "lead v") -> Role.VOCAL
        has("conga", "congo", "bongo", "perc", "cajon", "shaker",
            "timbale", "tamb", "snare", "overhead", "oh ", "tom",
            "hat") -> Role.PERCUSSION
        // bass family before keys so "synth bass" never lands in keys;
        // "DI 2"/"DI2" is this rig's synth-bass channel
        has("kick", "bass", "sub", "808", "di 2", "di2") -> Role.FOUNDATION
        has("piano", "keys", "keyb", "rhodes", "organ", "synth",
            "pad") -> Role.KEYS
        has("solo", "lead g", "amp") -> Role.SOLO_GTR
        has("rhythm", "ac g", "acoustic", "gtr", "guitar") -> Role.RHYTHM_GTR
        else -> Role.INSTRUMENT
    }
}

/**
 * The user's rig, channel by channel — used as the default profile so
 * the app understands the band even before console names are read:
 * 1 Kick, 2 Snare, 3 Overheads, 4 Bass Mic, 5 Guitar Amp (solo),
 * 6+7 Piano stereo, 8 Guitar DI (2nd electric), 9 Vocal Center (lead),
 * 10 Vocal Piano (2nd singer), 11 Congo / 3rd singer, 12 Bass DI,
 * 13 Congo 2, 14 DI2 (synth bass), 15 Sax/Flute, 16 Harmonica.
 */
fun defaultRigProfile(): List<ChannelConfig> = listOf(
    ChannelConfig(0, "Kick Drum", Role.FOUNDATION),
    ChannelConfig(1, "Snare", Role.PERCUSSION),
    ChannelConfig(2, "Overheads", Role.PERCUSSION),
    ChannelConfig(3, "Bass Mic", Role.FOUNDATION),
    ChannelConfig(4, "Guitar Amp", Role.SOLO_GTR),
    ChannelConfig(5, "Piano L", Role.KEYS),
    ChannelConfig(6, "Piano R", Role.KEYS),
    ChannelConfig(7, "Guitar DI", Role.RHYTHM_GTR),
    ChannelConfig(8, "Vocal Center", Role.VOCAL),
    ChannelConfig(9, "Vocal Piano", Role.VOCAL),
    ChannelConfig(10, "Congo / Vox 3", Role.BACKING_VOCAL),
    ChannelConfig(11, "Bass DI", Role.FOUNDATION),
    ChannelConfig(12, "Congo 2", Role.PERCUSSION),
    ChannelConfig(13, "DI2 Synth Bass", Role.FOUNDATION),
    ChannelConfig(14, "Sax / Flute", Role.COLOR),
    ChannelConfig(15, "Harmonica", Role.COLOR),
)

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
    // Responsiveness: when the SITUATION changes (lead singer switches
    // mics, an idle channel wakes up), converging on soundcheck-derived
    // targets is safe at speed — the values are human-approved. Only
    // creeping BEYOND the soundcheck stays slow.
    val fastWindowSec: Float = 6f,
    val fastBoostPerSecDb: Float = 2f,
    val vocalActTauSec: Float = 2.5f,    // how fast we notice a singer
    val leadHoldSec: Float = 5f,         // min time between lead switches
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
    var role: Role = cfg.role        // mutable: console names refine it
    var refDb: Float? = null         // soundcheck loudness reference (EMA)
    var ratioRef: Float? = null      // soundcheck (this - foundation) ratio
    var liveEma: Float? = null       // running active-only loudness EMA
    var active = false
    var lastActiveT = 0.0
    var lastLevelDb = -128f
    var frozen = false               // per-channel human lock
    var idleRamped = false
    var vocalAct = 0f                // singing-now score (vocal group)
    var fastUntil = 0.0              // situation-change fast-lane window
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

    /** Which vocal mic carries the song right now (lead-follow). */
    var leadVocal: Int? = null; private set
    private var topRatioRef: Float? = null      // the lead's pyramid height
    private var backingRatioRef: Float? = null  // where non-leads sit
    private var lastLeadSwitch = 0.0

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
            // singing-now score for the vocal group (fast tau — this is
            // how quickly a mid-song singer switch is noticed)
            if (st.role == Role.VOCAL || st.role == Role.BACKING_VOCAL) {
                val a = (0.05f / settings.vocalActTauSec).coerceIn(0f, 1f)
                st.vocalAct += a * ((if (st.active) 1f else 0f) - st.vocalAct)
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
        // Balance-ladder references: each layer's soundcheck ratio to
        // the foundation (kick + bass) anchor. The pyramid you mixed IS
        // the target; the engine holds these ratios from now on.
        val anchorRef = foundationLevel { it.refDb }
        for (st in state.values) {
            st.ratioRef = if (anchorRef != null && st.role.inLadder()
                && st.role != Role.FOUNDATION && st.refDb != null)
                st.refDb!! - anchorRef else null
        }
        // Vocal group heights: the loudest vocal ratio at soundcheck is
        // "the lead's place on top"; the next one down is where any
        // non-lead vocal sits. Lead-follow swaps WHO gets the top spot.
        val vocalRatios = state.values
            .filter { it.role == Role.VOCAL || it.role == Role.BACKING_VOCAL }
            .mapNotNull { it.ratioRef }.sortedDescending()
        topRatioRef = vocalRatios.firstOrNull()
        backingRatioRef = vocalRatios.getOrNull(1)
            ?: topRatioRef?.minus(3f)
        leadVocal = state.values.firstOrNull {
            (it.role == Role.VOCAL || it.role == Role.BACKING_VOCAL) &&
                    it.ratioRef != null && it.ratioRef == topRatioRef
        }?.cfg?.index
        snapshotTaken = true
        log(tSec, "revert", null, null, 0f, "soundcheck snapshot taken " +
                "(${sends.size} sends, ${state.values.count { it.refDb != null }} refs" +
                (if (anchorRef != null) ", pyramid anchored to foundation)"
                 else ", no foundation channels — absolute mode)"))
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

        // -- 0. lead-vocal follow: whoever carries the song gets the top
        // of the pyramid, switchable mid-song with hysteresis ------------
        run {
            val top = topRatioRef ?: return@run
            val group = state.values.filter {
                it.role == Role.VOCAL || it.role == Role.BACKING_VOCAL }
            if (group.size < 2 || tSec - lastLeadSwitch < settings.leadHoldSec)
                return@run
            val cur = leadVocal?.let { state[it] }
            val cand = group.maxByOrNull { it.vocalAct } ?: return@run
            if (cand.cfg.index != leadVocal && cand.vocalAct > 0.6f
                && (cur == null || cur.vocalAct < 0.3f)) {
                leadVocal = cand.cfg.index
                lastLeadSwitch = tSec
                // a singer we never heard at soundcheck still gets the
                // lead height — soundcheck-derived, so safe to adopt
                if (cand.ratioRef == null) cand.ratioRef = top
                // situation changed: open the fast lane for the whole
                // vocal group to settle the new balance quickly
                for (st in group) st.fastUntil = tSec + settings.fastWindowSec
                log(tSec, "lead", cand.cfg.index, null, 0f,
                    "${cand.cfg.name} is carrying the song — giving them " +
                    "the lead balance")
            }
        }

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
                // channel woke up: fast lane back to its approved level
                st.fastUntil = tSec + settings.fastWindowSec
                log(tSec, "restore", idx, null, 0f,
                    "${st.cfg.name} back — restoring to soundcheck level")
            }
            if (!st.active) continue
            // Balance ladder: layers correct RELATIVE to the live
            // foundation, so the whole band breathing together is not
            // "drift" — only a layer leaving its place in the pyramid
            // is. Foundation itself (and unclassified channels) anchor
            // on absolute soundcheck level.
            val anchorLive = if (st.role.inLadder()
                && st.role != Role.FOUNDATION) foundationLevel {
                    if (it.active) it.liveEma else null } else null
            // vocal group: the current lead is held at the TOP height,
            // everyone else at the backing height — this is what makes
            // "balance between singers perfect at all times" true even
            // when they trade the lead mid-song
            val isVocalGroup = st.role == Role.VOCAL ||
                    st.role == Role.BACKING_VOCAL
            val ratioRef = if (isVocalGroup && topRatioRef != null) {
                if (st.cfg.index == leadVocal) topRatioRef
                else st.ratioRef?.coerceAtMost(
                    backingRatioRef ?: st.ratioRef!!) ?: backingRatioRef
            } else st.ratioRef
            val drift = if (anchorLive != null && ratioRef != null)
                (live - anchorLive) - ratioRef       // + = above its layer
            else live - ref                          // + means got louder
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
        // the CURRENT lead singer is the priority voice, wherever the
        // song moved (Vocal Center, Vocal Piano, or channel 11)
        for (bus in buses) {
            val vIdx = leadVocal ?: bus.vocalChannel ?: continue
            val v = state[vIdx] ?: continue
            val vRef = v.refDb; val vLive = v.liveEma
            if (vRef == null || vLive == null) continue
            val band = state.values.filter {
                it.cfg.index != vIdx && it.role != Role.VOCAL &&
                        it.role != Role.BACKING_VOCAL &&
                        it.role != Role.TALK &&
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
                    // Responsive fast lane: after a situation change
                    // (lead switch, channel wake-up) converge quickly
                    // while still at-or-below the soundcheck level;
                    // creeping past the snapshot always crawls.
                    val fast = tSec < st.fastUntil && cur < 0f
                    val rate = if (fast) settings.fastBoostPerSecDb
                               else settings.boostPerSecDb
                    // per-bus upward budget
                    val used = busBoostUsed.getOrDefault(k.second, currentBusBoost(k.second, k.first))
                    val room = (settings.busBoostBudgetDb - used).coerceAtLeast(0f)
                    min(min((rate * dt).toFloat(), tgt - cur),
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
    /** Mean level of active foundation channels via the given getter. */
    private inline fun foundationLevel(get: (ChannelState) -> Float?): Float? {
        var sum = 0f; var n = 0
        for (st in state.values) if (st.role == Role.FOUNDATION) {
            val v = get(st) ?: continue
            sum += v; n++
        }
        return if (n > 0) sum / n else null
    }

    fun setRole(ch: Int, role: Role): Boolean {
        val st = state[ch] ?: return false
        st.role = role
        return true
    }

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

    /** Public upward gate, shared with the tone doctor. */
    fun boostsAllowed(tSec: Double): Boolean = upwardAllowed(tSec)

    /** Channels currently passing the activity gate. */
    fun activeChannels(): Set<Int> =
        state.filterValues { it.active }.keys

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
