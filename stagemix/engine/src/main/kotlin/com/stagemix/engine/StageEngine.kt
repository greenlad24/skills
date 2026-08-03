package com.stagemix.engine

import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

/**
 * StageMix FOH autopilot: leads the MAIN (LR) mix of an M-Air/X-Air
 * console all night, with no soundcheck ritual required — and NEVER
 * touches the six monitor buses. Monitors are human territory
 * (Mixing Station); the only mixer parameter this engine ever writes
 * is the channel fader (/ch/NN/mix/fader). That's an architectural
 * invariant, not a setting: there is no code path that can emit a bus
 * send address.
 *
 * How it leads without a soundcheck:
 *  - It carries a built-in BALANCE PYRAMID (the band's hierarchy):
 *    kick + bass foundation dominant, keys tucked behind, percussion
 *    with the rhythm layer, guitars and featured color above, backing
 *    vocal in the mix, lead vocal on top.
 *  - Channel meters are PRE-fader on /meters/1, so it hears the true
 *    source loudness regardless of its own moves. Each channel's
 *    contribution to the mains ≈ source loudness + fader; the engine
 *    steers contributions toward the pyramid, cross-adaptively
 *    (Perez-Gonzalez/Reiss-style loudness balancing with role targets).
 *  - When MIXING is flipped on it takes over: current fader positions
 *    become the authority bounds' center ([-12, +6] dB around them,
 *    absolute fader cap +2 dB), it listens for a short learning window,
 *    then starts mixing.
 *
 * Everything else carries over from the monitor-era engine: activity
 *  gates, idle easing + fast restore, lead-vocal follow, cut-only vocal
 *  priority (now on the mains), clip/meter-loss/broadband freezes,
 *  watchdog veto, per-channel locks, one-tap revert to takeover.
 */

data class ChannelConfig(
    val index: Int,              // 0-based (ch 1 = 0)
    val name: String,
    val role: Role = Role.INSTRUMENT,
)

/**
 * Balance-ladder roles, bottom to top. INSTRUMENT = unclassified;
 * TALK = speech mics (never automated).
 */
enum class Role {
    FOUNDATION, KEYS, PERCUSSION, RHYTHM_GTR, SOLO_GTR, COLOR,
    BACKING_VOCAL, VOCAL, INSTRUMENT, TALK;

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
 * The user's rig, channel by channel — the built-in default profile:
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

/**
 * The built-in pyramid: each role's target contribution to the mains,
 * in dB relative to the foundation anchor. This encodes "a good
 * sounding balance" for the band; the takeover bounds keep it from
 * ever straying far from sane fader territory.
 */
val PYRAMID: Map<Role, Float> = mapOf(
    Role.FOUNDATION to 0f,
    Role.KEYS to -4f,           // rich low-mid bed behind the singer
    Role.PERCUSSION to -6f,
    Role.RHYTHM_GTR to -5f,
    Role.SOLO_GTR to -3f,
    Role.COLOR to -3f,          // sax / harmonica features
    Role.BACKING_VOCAL to -2f,  // in the mix, under the lead
    Role.VOCAL to +1f,          // on top, always
    Role.INSTRUMENT to -4f,
)

data class EngineSettings(
    val deadbandDb: Float = 2.0f,
    val maxAboveBaselineDb: Float = 6.0f,
    val maxBelowBaselineDb: Float = 12.0f,
    val absFaderCapDb: Float = 2.0f,     // hard ceiling, ever
    val leadPerSecDb: Float = 1.0f,      // autopilot boost pace
    val fastPerSecDb: Float = 2.0f,      // situation-change fast lane
    val cutPerSecDb: Float = 3.0f,
    val mixBoostBudgetDb: Float = 6.0f,  // total concurrent boost, mains
    val emaTauSec: Float = 20f,
    val learnSec: Float = 20f,           // listen before leading
    val minHeardSec: Float = 5f,         // per-channel audition time
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
    val duckTriggerDb: Float = 3f,
    val fastWindowSec: Float = 6f,
    val vocalActTauSec: Float = 2.5f,
    val leadHoldSec: Float = 5f,
)

data class Decision(
    val tSec: Double,
    val kind: String,     // pyramid | duck | idle | restore | freeze |
                          // revert | lead | takeover
    val channel: Int?,
    val bus: Int?,        // always null now — kept for UI compatibility
    val deltaDb: Float,
    val reason: String,
)

/**
 * The ONLY thing the engine can write: a channel fader (mains path).
 * Bus sends have no representation here at all.
 */
data class FaderWrite(val channel: Int, val levelDb: Float) {
    val address get() = "/ch/%02d/mix/fader".format(channel + 1)
}

class ChannelState(val cfg: ChannelConfig) {
    var role: Role = cfg.role
    var baselineDb: Float? = null    // fader position at takeover
    var preEma: Float? = null        // active-only source loudness EMA
    var takeRef: Float? = null       // source loudness when we took over
    var heardSec = 0f                // audition time since takeover
    var active = false
    var lastActiveT = 0.0
    var lastLevelDb = -128f
    var frozen = false
    var idleRamped = false
    var vocalAct = 0f
    var fastUntil = 0.0
    var offset = 0f                  // slewed fader offset from baseline
    var target = 0f
    var duckDb = 0f
}

class StageEngine(
    channels: List<ChannelConfig>,
    val settings: EngineSettings = EngineSettings(),
    val pyramid: Map<Role, Float> = PYRAMID,
) {
    val channels = channels.associateBy { it.index }
    val state = channels.associate { it.index to ChannelState(it) }

    /** true once takeover happened and the learning window elapsed */
    val ready: Boolean get() = takeoverT >= 0 && lastTickT - takeoverT >= settings.learnSec
    var takeoverT = -1.0; private set
    var frozenAll = false
    var watchdogVeto = false

    var leadVocal: Int? = null; private set
    private var lastLeadSwitch = 0.0

    /** Ensemble awareness: who is on stage right now. */
    var hasBass = false; private set      // bass instrument playing
    var hasDrums = false; private set     // kick / percussion playing
    /** drums but no bass -> the piano fills the low end */
    val keysLowFill: Boolean get() = hasDrums && !hasBass

    private var lastMeterT = -1.0
    private var lastTickT = -1.0
    private var clipHoldUntil = 0.0
    private var broadbandHoldUntil = 0.0
    private var lastMixMean: Float? = null
    val decisions = ArrayDeque<Decision>()

    // ------------------------------------------------------------------
    /** ~20 Hz pre-fader input meters (/meters/1, first 16 values). */
    fun onMeters(levels: FloatArray, tSec: Double) {
        val dtFrame = 0.05f
        lastMeterT = tSec
        var mean = 0f
        var n = 0
        for ((idx, st) in state) {
            val db = levels.getOrNull(idx) ?: continue
            st.lastLevelDb = db
            if (!st.active && db > settings.activityEnterDb) st.active = true
            else if (st.active && db < settings.activityExitDb) st.active = false
            if (st.active) {
                st.lastActiveT = tSec
                if (takeoverT >= 0) st.heardSec += dtFrame
                val alpha = (dtFrame / settings.emaTauSec).coerceIn(0f, 1f)
                st.preEma = st.preEma?.let { it + alpha * (db - it) } ?: db
                mean += db; n += 1
            }
            if (st.role == Role.VOCAL || st.role == Role.BACKING_VOCAL) {
                val a = (dtFrame / settings.vocalActTauSec).coerceIn(0f, 1f)
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

    // ------------------------------------------------------------------
    /**
     * MIXING flipped on: current fader positions (read from the
     * console) become the authority bounds' center. No ceremony — the
     * engine listens for learnSec, then leads.
     */
    fun takeover(faderDb: Map<Int, Float>, tSec: Double) {
        for ((ch, db) in faderDb) {
            val st = state[ch] ?: continue
            st.baselineDb = db
            st.offset = 0f; st.target = 0f; st.duckDb = 0f
            st.heardSec = 0f
            st.takeRef = null   // re-learned during the listening window
        }
        takeoverT = tSec
        lastLeadSwitch = tSec
        // initial lead: the configured lead vocal (Vocal Center)
        leadVocal = state.values.firstOrNull { it.role == Role.VOCAL }
            ?.cfg?.index
        log(tSec, "takeover", null, 0f,
            "autopilot took the mains — listening for " +
            "${settings.learnSec.toInt()}s, then leading " +
            "(${faderDb.size} faders bounded, monitors untouched)")
    }

    /** Hands the mains back exactly as they were at takeover. */
    fun revertToBaseline(tSec: Double): List<FaderWrite> {
        val out = ArrayList<FaderWrite>()
        for (st in state.values) {
            val base = st.baselineDb ?: continue
            st.offset = 0f; st.target = 0f; st.duckDb = 0f
            out.add(FaderWrite(st.cfg.index, base))
        }
        log(tSec, "revert", null, 0f, "mains returned to takeover positions")
        return out
    }

    // ------------------------------------------------------------------
    private fun upwardAllowed(tSec: Double): Boolean =
        !frozenAll && !watchdogVeto && tSec >= clipHoldUntil &&
                tSec >= broadbandHoldUntil && meterFresh(tSec)

    private fun anyMotionAllowed(tSec: Double): Boolean =
        !frozenAll && meterFresh(tSec)

    fun tick(tSec: Double): List<FaderWrite> {
        val dt = if (lastTickT < 0) 1.0 else (tSec - lastTickT).coerceIn(0.0, 5.0)
        lastTickT = tSec
        if (takeoverT < 0 || !ready) return emptyList()
        if (!anyMotionAllowed(tSec)) return emptyList()
        val up = upwardAllowed(tSec)

        // -- 0. lead-vocal follow ----------------------------------------
        run {
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
                for (st in group) st.fastUntil = tSec + settings.fastWindowSec
                log(tSec, "lead", cand.cfg.index, 0f,
                    "${cand.cfg.name} is carrying the song — lead balance " +
                    "moves there")
            }
        }

        // -- 0.5 ensemble detection: the lineup changes all night --------
        run {
            val bassNow = state.values.any {
                it.role == Role.FOUNDATION && isBassName(it.cfg.name) &&
                        it.active && it.heardSec >= settings.minHeardSec }
            val drumsNow = state.values.any {
                ((it.role == Role.FOUNDATION && !isBassName(it.cfg.name))
                        || it.role == Role.PERCUSSION) &&
                        it.active && it.heardSec >= settings.minHeardSec }
            if (bassNow != hasBass || drumsNow != hasDrums) {
                hasBass = bassNow; hasDrums = drumsNow
                for (st in state.values)
                    st.fastUntil = tSec + settings.fastWindowSec
                val who = buildString {
                    append(if (drumsNow) "drums" else "no drums")
                    append(", ")
                    append(if (bassNow) "bass" else "no bass")
                }
                log(tSec, "ensemble", null, 0f, "lineup changed ($who)" +
                        if (keysLowFill)
                            " — piano covers the low end" else "")
            }
        }

        // -- 1. pyramid targets (cross-adaptive). Anchor cascade: the
        // foundation when present; otherwise the active accompaniment
        // (solo guitar behind a singer, piano in a duet); otherwise the
        // lead voice itself — so a lone singer+guitar mixes just as
        // correctly as the full band.
        val (anchor, anchorPyr) = anchorContribution()
        for ((idx, st) in state) {
            if (st.frozen || st.role == Role.TALK) continue
            val base = st.baselineDb ?: continue
            val idleFor = tSec - st.lastActiveT
            if (idleFor > settings.idleRampAfterSec) {
                if (!st.idleRamped) {
                    st.idleRamped = true
                    st.target = -settings.idleCutDb
                    log(tSec, "idle", idx, -settings.idleCutDb,
                        "${st.cfg.name} idle ${idleFor.toInt()}s — easing " +
                        "out of the mains")
                }
                continue
            }
            if (st.idleRamped && st.active) {
                st.idleRamped = false
                st.target = 0f
                st.fastUntil = tSec + settings.fastWindowSec
                log(tSec, "restore", idx, 0f,
                    "${st.cfg.name} back — rejoining the mix")
            }
            if (!st.active || st.heardSec < settings.minHeardSec) continue
            val pre = st.preEma ?: continue
            if (st.takeRef == null) st.takeRef = pre  // audition complete
            // effective role height: lead-follow decides who is on top;
            // a genuine duet (both mics strongly on) puts BOTH near it
            val lead = leadVocal?.let { state[it] }
            val height = when {
                (st.role == Role.VOCAL || st.role == Role.BACKING_VOCAL) ->
                    when {
                        idx == leadVocal -> pyramid[Role.VOCAL] ?: 1f
                        st.vocalAct > 0.55f && (lead?.vocalAct ?: 0f) > 0.55f ->
                            (pyramid[Role.VOCAL] ?: 1f) - 1f   // duet partner
                        else -> pyramid[Role.BACKING_VOCAL] ?: -2f
                    }
                st.role == Role.KEYS && keysLowFill ->
                    (pyramid[Role.KEYS] ?: -4f) + 2f  // fill the missing bass
                else -> pyramid[st.role] ?: -4f
            }
            val tgt: Float = if (st.role == Role.FOUNDATION || anchor == null) {
                // the foundation anchors the mix (and anchor-less moments
                // hold): correct source drift since takeover only
                0f - driftSinceTakeover(st)
            } else {
                // contribution error vs (anchor + relative pyramid height)
                val contrib = pre + base + st.offset
                st.offset - (contrib - (anchor + (height - anchorPyr)))
            }
            val bounded = tgt.coerceIn(-settings.maxBelowBaselineDb,
                min(settings.maxAboveBaselineDb,
                    settings.absFaderCapDb - base))
            if (abs(bounded - st.target) > 0.5f &&
                abs(bounded - st.offset) > settings.deadbandDb) {
                st.target = bounded
                log(tSec, "pyramid", idx, bounded,
                    "${st.cfg.name} steering to its place in the pyramid " +
                    "(%+.1f dB)".format(bounded))
            } else if (abs(bounded - st.offset) <= settings.deadbandDb
                       && !st.idleRamped && st.duckDb == 0f) {
                st.target = st.offset  // inside deadband: rest
            }
        }

        // -- 2. vocal priority on the mains (cut-only) --------------------
        run {
            val lead = leadVocal?.let { state[it] } ?: return@run
            val leadPre = lead.preEma
            val leadBase = lead.baselineDb
            if (!lead.active || leadPre == null || leadBase == null) {
                for (st in state.values) if (st.duckDb < 0f)
                    st.duckDb = min(0f, st.duckDb + (1f * dt).toFloat())
                return@run
            }
            val band = state.values.filter {
                it.role != Role.VOCAL && it.role != Role.BACKING_VOCAL &&
                        it.role != Role.TALK && it.active &&
                        it.preEma != null && it.baselineDb != null
            }
            if (band.isEmpty()) return@run
            val leadContrib = leadPre + leadBase + lead.offset
            val bandContrib = band.map {
                it.preEma!! + it.baselineDb!! + it.offset }.average().toFloat()
            val wantGap = (pyramid[Role.VOCAL] ?: 1f) -
                    band.map { pyramid[it.role] ?: -4f }.average().toFloat()
            val gap = leadContrib - bandContrib
            val needDuck = gap < wantGap - settings.duckTriggerDb
            for (st in band) {
                if (needDuck) {
                    val want = -min(settings.duckMaxDb, wantGap - gap)
                    if (want < st.duckDb - 0.5f) {
                        st.duckDb = want
                        log(tSec, "duck", st.cfg.index, want,
                            "lead vocal buried — ducking ${st.cfg.name} " +
                            "in the mains")
                    }
                } else if (st.duckDb < -0.01f) {
                    st.duckDb = min(0f, st.duckDb + (1f * dt).toFloat())
                }
            }
        }

        // -- 3. slew + rails + budget -> fader writes ---------------------
        val writes = ArrayList<FaderWrite>()
        var boostUsed = state.values.sumOf {
            max(0f, it.offset).toDouble() }.toFloat()
        for ((_, st) in state) {
            if (st.frozen || st.role == Role.TALK) continue
            val base = st.baselineDb ?: continue
            val tgt = (st.target + st.duckDb)
                .coerceIn(-settings.maxBelowBaselineDb,
                    min(settings.maxAboveBaselineDb,
                        settings.absFaderCapDb - base))
            val cur = st.offset
            if (abs(tgt - cur) < 0.05f) continue
            val step: Float = if (tgt > cur) {
                if (!up) 0f
                else {
                    val fast = tSec < st.fastUntil && cur < 0f
                    val rate = if (fast) settings.fastPerSecDb
                               else settings.leadPerSecDb
                    val room = (settings.mixBoostBudgetDb -
                            (boostUsed - max(0f, cur))).coerceAtLeast(0f)
                    min(min((rate * dt).toFloat(), tgt - cur),
                        max(0f, room - max(0f, cur)))
                }
            } else {
                -min((settings.cutPerSecDb * dt).toFloat(), cur - tgt)
            }
            if (abs(step) < 0.01f) continue
            boostUsed += max(0f, (cur + step)) - max(0f, cur)
            st.offset = cur + step
            writes.add(FaderWrite(st.cfg.index,
                (base + st.offset).coerceIn(FaderLaw.MIN_DB,
                    settings.absFaderCapDb)))
        }
        return writes
    }

    /** + means the source got louder than when we took over. */
    private fun driftSinceTakeover(st: ChannelState): Float {
        val pre = st.preEma ?: return 0f
        return pre - (st.takeRef ?: pre)
    }

    private fun isBassName(name: String): Boolean {
        val n = name.lowercase()
        return listOf("bass", "di 2", "di2", "sub", "808").any { it in n }
    }

    private fun contributionMean(roles: Set<Role>): Pair<Float, Float>? {
        var sum = 0f; var pyr = 0f; var n = 0
        for (st in state.values) {
            if (st.role !in roles || !st.active) continue
            val pre = st.preEma ?: continue
            val base = st.baselineDb ?: continue
            if (st.heardSec < settings.minHeardSec) continue
            sum += pre + base + st.offset
            pyr += pyramid[st.role] ?: -4f
            n++
        }
        return if (n > 0) (sum / n) to (pyr / n) else null
    }

    /**
     * Anchor cascade for an ever-changing stage: foundation when a
     * rhythm section is playing; otherwise the active accompaniment
     * (guitar/piano behind a singer); otherwise the lead voice itself.
     * Returns (anchor contribution, that anchor's pyramid height).
     */
    private fun anchorContribution(): Pair<Float?, Float> {
        contributionMean(setOf(Role.FOUNDATION))?.let { return it.first to it.second }
        contributionMean(setOf(Role.KEYS, Role.RHYTHM_GTR, Role.SOLO_GTR,
            Role.PERCUSSION, Role.COLOR, Role.INSTRUMENT))
            ?.let { return it.first to it.second }
        val lead = leadVocal?.let { state[it] }
        if (lead != null && lead.active &&
            lead.heardSec >= settings.minHeardSec) {
            val pre = lead.preEma; val base = lead.baselineDb
            if (pre != null && base != null)
                return (pre + base + lead.offset) to (pyramid[Role.VOCAL] ?: 1f)
        }
        return null to 0f
    }

    // ------------------------------------------------------------------
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

    fun offsetDb(ch: Int): Float = state[ch]?.offset ?: 0f
    fun targetDb(ch: Int): Float = state[ch]?.let {
        it.target + it.duckDb } ?: 0f

    fun activeChannels(): Set<Int> = state.filterValues { it.active }.keys
    fun boostsAllowed(tSec: Double): Boolean = upwardAllowed(tSec)

    fun meterFresh(tSec: Double): Boolean =
        lastMeterT >= 0 && tSec - lastMeterT <= settings.meterTimeoutSec

    fun holdReason(tSec: Double): String? = when {
        frozenAll -> "FROZEN by operator"
        watchdogVeto -> "feedback watchdog veto"
        takeoverT >= 0 && !ready -> "listening — leading in " +
                "${(settings.learnSec - (tSec - takeoverT)).toInt().coerceAtLeast(0)}s"
        !meterFresh(tSec) -> "meters lost — holding still"
        tSec < clipHoldUntil -> "input near clip — no boosts"
        tSec < broadbandHoldUntil -> "big level change — waiting"
        else -> null
    }

    private fun log(t: Double, kind: String, ch: Int?, delta: Float,
                    reason: String) {
        decisions.addFirst(Decision(t, kind, ch, null, delta, reason))
        while (decisions.size > 60) decisions.removeLast()
    }
}
