package com.stagemix.engine

import kotlin.math.abs
import kotlin.math.log10
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow

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
    /**
     * The other half of a stereo pair, if any. Paired channels are one
     * source: they take the SAME correction so the image keeps its
     * width instead of being level-matched toward mono.
     */
    val pairWith: Int? = null,
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
    ChannelConfig(5, "Piano L", Role.KEYS, pairWith = 6),
    ChannelConfig(6, "Piano R", Role.KEYS, pairWith = 5),
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
 * The built-in pyramid: each role's target contribution to the mains as
 * a GROUP, in dB relative to the kick+bass GROUP.
 *
 * Group, not channel. The room hears the sum of the two piano channels
 * and the three drum channels, not each one on its own — so writing
 * these as per-channel heights made the mix depend on how many channels
 * a role happened to occupy. On this rig that put the four foundation
 * channels 6 dB louder as a group than the number says, and the lead
 * vocal — "on top, always" — ended up 5 dB UNDER the low end. Per
 * channel, each group target is shared out across however many of its
 * channels are actually playing (see `height()`), so a rig with one
 * bass and a rig with three get the same mix.
 */
val PYRAMID: Map<Role, Float> = mapOf(
    Role.FOUNDATION to 0f,
    Role.VOCAL to +1f,          // the lead, on top of the whole low end
    Role.BACKING_VOCAL to -8f,  // in the mix, under the lead
    Role.KEYS to -7f,           // rich low-mid bed behind the singer
    Role.PERCUSSION to -6f,
    Role.RHYTHM_GTR to -8f,
    Role.SOLO_GTR to -6f,
    Role.COLOR to -6f,          // sax / harmonica: a texture, until
                                // the player steps up (feature hold)
    Role.INSTRUMENT to -7f,
)

data class EngineSettings(
    val deadbandDb: Float = 2.0f,
    val maxAboveBaselineDb: Float = 6.0f,
    val maxBelowBaselineDb: Float = 12.0f,
    val absFaderCapDb: Float = 2.0f,     // hard ceiling, ever
    val leadPerSecDb: Float = 1.0f,      // autopilot boost pace
    val fastPerSecDb: Float = 2.0f,      // situation-change fast lane
    val cutPerSecDb: Float = 3.0f,
    /**
     * How much extra MIX LOUDNESS the engine's boosts may add, in total.
     * Budgeting the arithmetic sum of positive offsets made a 6 dB lift
     * on a harmonica sitting 30 dB down — worth about 0.02 dB of mix
     * level — cost exactly as much as 6 dB on the kick. It starved the
     * channels that actually needed help, the lead vocal among them.
     * This is the power-weighted rise instead: cheap boosts are cheap.
     */
    val mixBoostBudgetDb: Float = 3.0f,
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
    /** duck must recover this far past its trigger before releasing */
    val duckReleaseHystDb: Float = 1.5f,
    /** a source quieter than (loudest - this) is below the stage floor */
    val relativeGateDb: Float = 25f,
    /** level spread under which a source is "static" (hum, room tone) */
    val staticSpreadDb: Float = 1.5f,
    val staticWindowSec: Float = 90f,
    /** only sources this far under the loudest can be called noise */
    val staticMinDepthDb: Float = 12f,
    val vocalActTauSec: Float = 2.5f,
    val leadHoldSec: Float = 5f,
    /** a fader move smaller than this is the wire, not a human */
    val overrideMinDb: Float = 0.25f,
    /**
     * A player stepping up for a feature. When one channel rises this
     * far over its own 20 s average while the rest of the band has not
     * moved, that is a solo, not drift — the engine holds its fader
     * instead of taking the feature back off the player.
     */
    val featureRiseDb: Float = 3.5f,
    val featureHoldSec: Float = 90f,
    /** ticks a feature must read before the hold latches (leaky count) */
    val featureConfirmTicks: Int = 3,
    /** how far back "stepped up" is measured, in ticks (~seconds) */
    val featureWindowTicks: Int = 8,
    /** short-term loudness EMA used to spot a player stepping up */
    val fastEmaTauSec: Float = 2f,
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
    val address get() = osc("/ch/%02d/mix/fader", channel + 1)
}

class ChannelState(val cfg: ChannelConfig) {
    var role: Role = cfg.role
    var baselineDb: Float? = null    // fader position at takeover
    var preEma: Float? = null        // active-only source loudness EMA
    var fastEma: Float? = null       // ~3 s EMA: spots a player stepping up
    var featureStart = -1.0          // holding a feature for this player
    var featureRef = 0f              // their level when they stepped up
    var duetLatched = false          // singing WITH the lead (latched)
    var featureVotes = 0             // ticks reading as a feature (leaky)
    /** the last few seconds of short-term loudness, at tick rate */
    val riseHist = ArrayDeque<Float>()
    var takeRef: Float? = null       // source loudness when we took over
    var heardSec = 0f                // audition time since takeover
    var active = false
    /** level gate alone (before the "is this actually a source?" test) */
    var gateOpen = false
    var lastActiveT = 0.0
    var lastLevelDb = -128f
    var frozen = false
    var idleRamped = false
    var vocalAct = 0f
    var fastUntil = 0.0
    var overrideUntil = 0.0          // human out-mixed us: hands off
    /** rolling min/max of the source level, for static detection */
    var spreadMin = 0f; var spreadMax = -128f
    var spreadSince = 0.0
    var isStatic = false             // hum / room tone, not an instrument
    /** deadband hysteresis: once engaged we converge fully */
    var engaged = false
    var offset = 0f                  // slewed fader offset from baseline
    var target = 0f
    var duckDb = 0f
}

/** how long "hand back the mains" keeps the autopilot off the faders */
const val REVERT_HOLD_SEC = 120.0

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
    /** revert hands the mix back AND keeps hands off until re-armed */
    private var revertHoldUntil = 0.0

    /** Ensemble awareness: who is on stage right now. */
    var hasBass = false; private set      // bass instrument playing
    var hasDrums = false; private set     // kick / percussion playing
    /** drums but no bass -> the piano fills the low end */
    val keysLowFill: Boolean get() = hasDrums && !hasBass

    /**
     * Taste learned from the operator's feedback (👍/👎 chips): bounded
     * per-role nudges on the built-in pyramid, persisted by the app.
     */
    val pyramidBias = HashMap<Role, Float>()
    /** taste taught by the feedback chips (explicit human intent) */
    private val chipBias = HashMap<Role, Float>()
    /** running mean of fader-override lessons, per role */
    private val ovSum = HashMap<Role, Float>()
    private val ovN = HashMap<Role, Int>()

    /** chips + averaged override lessons, clamped */
    private fun recomputeBias(role: Role) {
        val chip = chipBias[role] ?: 0f
        val n = ovN[role] ?: 0
        val ov = if (n > 0) (ovSum[role] ?: 0f) / n else 0f
        val v = (chip + ov).coerceIn(-3f, 3f)
        if (abs(v) < 0.001f) pyramidBias.remove(role) else pyramidBias[role] = v
    }
    var overrideCount = 0; private set

    /** restore taste persisted from previous nights */
    fun loadBias(saved: Map<Role, Float>) {
        for ((r, v) in saved) {
            chipBias[r] = v.coerceIn(-3f, 3f)
            recomputeBias(r)
        }
    }

    // mix-health rolling scores (EMAs over ~5 min of ticks)
    private var vocalOnTopEma = 1f
    private var vocalHealthSamples = 0
    private var inPlaceEma = 1f
    private var healthTicks = 0

    data class MixHealth(
        val vocalOnTopPct: Int,   // % of time the lead sits on top
        val inPlacePct: Int,      // % of active channels at their height
        val overrides: Int,       // times a human out-mixed us (adopted)
        val ticks: Int,           // decision cycles since takeover
    )

    fun health() = MixHealth(
        if (vocalHealthSamples < 20) -1
        else (vocalOnTopEma * 100).toInt().coerceIn(0, 100),
        (inPlaceEma * 100).toInt().coerceIn(0, 100),
        overrideCount, healthTicks)

    /**
     * Operator feedback chips -> persistent, bounded taste adjustments.
     * Returns a human description of what was learned.
     */
    fun applyFeedback(kind: String, tSec: Double): String {
        fun nudge(role: Role, d: Float): Float {
            chipBias[role] = ((chipBias[role] ?: 0f) + d).coerceIn(-3f, 3f)
            recomputeBias(role)
            return pyramidBias[role] ?: 0f
        }
        val what = when (kind) {
            "good" -> "noted — keeping this taste"
            "vocal_up" -> "lead vocal now %+.0f dB vs stock"
                .format(nudge(Role.VOCAL, +1f))
            "vocal_down" -> "lead vocal now %+.0f dB vs stock"
                .format(nudge(Role.VOCAL, -1f))
            "gtr_down" -> "guitars now %+.0f dB vs stock".format(
                min(nudge(Role.SOLO_GTR, -1f), nudge(Role.RHYTHM_GTR, -1f)))
            "gtr_up" -> "guitars now %+.0f dB vs stock".format(
                max(nudge(Role.SOLO_GTR, +1f), nudge(Role.RHYTHM_GTR, +1f)))
            "keys_up" -> "piano now %+.0f dB vs stock"
                .format(nudge(Role.KEYS, +1f))
            "keys_down" -> "piano now %+.0f dB vs stock"
                .format(nudge(Role.KEYS, -1f))
            "low_up" -> {
                // low end weak = foundation more dominant: every layer
                // steps down half a dB relative to it
                for (r in listOf(Role.KEYS, Role.PERCUSSION, Role.RHYTHM_GTR,
                    Role.SOLO_GTR, Role.COLOR, Role.BACKING_VOCAL,
                    Role.VOCAL, Role.INSTRUMENT)) nudge(r, -0.5f)
                "foundation more dominant (everything else −0.5 dB)"
            }
            "perc_down" -> "percussion now %+.0f dB vs stock"
                .format(nudge(Role.PERCUSSION, -1f))
            "color_down" -> "sax/harmonica now %+.0f dB vs stock"
                .format(nudge(Role.COLOR, -1f))
            else -> return "unknown feedback"
        }
        log(tSec, "feedback", null, 0f, "you said '$kind' — $what")
        return what
    }

    /**
     * A human moved a fader we manage while we were mixing. The human
     * wins twice: their position is adopted as the new baseline (hands
     * off that channel for a while), AND the disagreement teaches the
     * pyramid a small, bounded lesson — so every correction makes the
     * next night's mix start closer to your taste.
     */
    fun operatorOverride(ch: Int, faderDb: Float, tSec: Double) {
        val st = state[ch] ?: return
        // a fader nudge cannot grant the engine authority it was never
        // given — that comes from takeover() alone
        if (takeoverT < 0 || st.baselineDb == null) return
        val safe = if (faderDb.isNaN()) return
                   else faderDb.coerceIn(FaderLaw.MIN_DB, settings.absFaderCapDb)
        val disagreement = safe - ((st.baselineDb ?: safe) + st.offset)
        // A human move has to be bigger than the wire's own noise. The
        // console quantizes every fader to a 1024-step float, so our own
        // write comes back a hundredth of a dB off — and on firmware
        // that echoes parameter changes back to the sender, the engine
        // read its own first 16 writes as 16 human overrides and handed
        // every channel off for two minutes. Nothing moved again all
        // night. One fader step is ~0.04 dB where the engine works, so
        // anything under a quarter of a dB is the protocol, not a person.
        if (abs(disagreement) < settings.overrideMinDb) return
        st.baselineDb = safe
        st.offset = 0f; st.target = 0f; st.duckDb = 0f
        st.overrideUntil = tSec + 120.0
        overrideCount++
        var learned = ""
        if (st.role.inLadder() && abs(disagreement) >= 1f) {
            // AVERAGE the lessons instead of integrating them: a fixed
            // step per correction pinned the taste to its rail on the
            // second night, and even zero-mean corrections random-walked
            // there. A mean converges on what the engineer actually
            // prefers and lets inconsistent nights cancel out.
            val lesson = disagreement.coerceIn(-0.5f, 0.5f)
            ovSum[st.role] = (ovSum[st.role] ?: 0f) + lesson
            ovN[st.role] = (ovN[st.role] ?: 0) + 1
            recomputeBias(st.role)
            learned = " — learned: ${st.role.name.lowercase()} taste " +
                    "now %+.1f dB".format(pyramidBias[st.role] ?: 0f)
        }
        log(tSec, "override", ch, disagreement,
            "${st.cfg.name} — you moved it %+.1f dB; adopting your level, "
                .format(disagreement) + "holding off 2 min$learned")
    }

    private var lastMeterT = -1.0
    private var lastTickT = -1.0
    private var clipHoldUntil = 0.0
    private var broadbandHoldUntil = 0.0
    private var lastMixMean: Float? = null
    private var lastMixCount = 0
    private val prevLevel = HashMap<Int, Float>()
    private val prevActive = HashSet<Int>()
    val decisions = ArrayDeque<Decision>()

    // ------------------------------------------------------------------
    /** ~20 Hz pre-fader input meters (/meters/1, first 16 values). */
    fun onMeters(levels: FloatArray, tSec: Double) {
        // Real elapsed time, not an assumed frame period: a burst of
        // buffered frames after a Wi-Fi stutter used to lurch the
        // loudness measurement and credit audition time for 0 seconds.
        val dtFrame = if (lastMeterT < 0) 0.05f
        else (tSec - lastMeterT).toFloat().coerceIn(0f, 0.25f)
        lastMeterT = tSec
        var mean = 0f
        var n = 0
        // A quiet acoustic trio can live 20 dB under a rock band, so an
        // absolute gate either deafens the engine to them or lets room
        // tone in. The gate follows the stage: loudest source - 25 dB,
        // never stricter than the absolute floor.
        var loudest = -128f
        for ((idx, st) in state) {
            val db = sane(levels.getOrNull(idx) ?: continue) ?: continue
            if (db > loudest) loudest = db
        }
        val enterGate = min(settings.activityEnterDb,
            loudest - settings.relativeGateDb)
        val exitGate = enterGate - 10f
        for ((idx, st) in state) {
            val db = sane(levels.getOrNull(idx) ?: continue) ?: continue
            st.lastLevelDb = db
            if (!st.gateOpen && db > enterGate) st.gateOpen = true
            else if (st.gateOpen && db < exitGate) st.gateOpen = false
            // Static-source detection: music moves, a ground loop and an
            // empty open mic do not. A source whose level has barely
            // moved for a long while is not an instrument — and it is
            // not a member of the ensemble at all: leaving it "active"
            // let a -50 dBFS open mic earn a boost and a -38 dB ground
            // loop sit in the anchor. Judged on the level gate, not on
            // `active`, so the verdict can survive its own consequence.
            if (db > st.spreadMax) st.spreadMax = db
            if (db < st.spreadMin) st.spreadMin = db
            if (tSec - st.spreadSince > settings.staticWindowSec) {
                st.isStatic = st.gateOpen &&
                        (st.spreadMax - st.spreadMin) < settings.staticSpreadDb &&
                        st.spreadMax < loudest - settings.staticMinDepthDb
                st.spreadSince = tSec
                st.spreadMin = db; st.spreadMax = db
            }
            st.active = st.gateOpen
            if (st.active) {
                st.lastActiveT = tSec
                if (takeoverT >= 0) st.heardSec += dtFrame
                val alpha = (dtFrame / settings.emaTauSec).coerceIn(0f, 1f)
                st.preEma = st.preEma?.let { it + alpha * (db - it) } ?: db
                val fa = (dtFrame / settings.fastEmaTauSec).coerceIn(0f, 1f)
                st.fastEma = st.fastEma?.let { it + fa * (db - it) } ?: db
                mean += db; n += 1
            }
            val a = (dtFrame / settings.vocalActTauSec).coerceIn(0f, 1f)
            val singing = if ((st.role == Role.VOCAL ||
                        st.role == Role.BACKING_VOCAL) &&
                    st.active && !st.isStatic) 1f else 0f
            // decays for everyone: a channel that stops being a vocal
            // must not keep a frozen "still singing" score forever
            st.vocalAct += a * (singing - st.vocalAct)
            if (db > settings.clipFreezeDb)
                clipHoldUntil = tSec + settings.clipHoldSec
        }
        // Broadband guard over the INTERSECTION of channels active in
        // both frames. Bailing out whenever the active set changed made
        // the guard disarm itself exactly when it was needed — at a song
        // end, when applause opens every mic at once and the engine
        // starts re-balancing the audience.
        var interSum = 0f; var interN = 0
        for ((idx, st) in state) {
            val prev = prevLevel[idx] ?: continue
            // active in BOTH frames — a channel that just woke up is a
            // new source, not a level change on an existing one
            if (!st.active || idx !in prevActive) continue
            interSum += st.lastLevelDb - prev; interN++
        }
        if (interN >= 2 && abs(interSum / interN) > settings.broadbandJumpDb)
            broadbandHoldUntil = tSec + settings.broadbandHoldSec
        prevActive.clear()
        for ((idx, st) in state) {
            prevLevel[idx] = st.lastLevelDb
            if (st.active) prevActive.add(idx)
        }
        if (n > 0) { lastMixMean = mean / n; lastMixCount = n }
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
            if (!db.isFinite()) continue
            st.baselineDb = db.coerceIn(FaderLaw.MIN_DB, settings.absFaderCapDb)
            st.offset = 0f; st.target = 0f; st.duckDb = 0f
            st.heardSec = 0f
            st.takeRef = null   // re-learned during the listening window
            // a fresh takeover is a clean slate: stale override holds,
            // idle flags and fast lanes from the previous act must go
            st.overrideUntil = 0.0
            st.fastUntil = 0.0
            st.idleRamped = false
        }
        // channels the console did not report: drop authority entirely
        // rather than keep stale offsets under a fresh takeover
        for ((ch, st) in state) if (ch !in faderDb) {
            st.baselineDb = null
            st.offset = 0f; st.target = 0f; st.duckDb = 0f
            st.heardSec = 0f; st.takeRef = null
            st.overrideUntil = 0.0; st.fastUntil = 0.0
            st.idleRamped = false; st.engaged = false
        }
        takeoverT = tSec
        revertHoldUntil = 0.0
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
            st.engaged = false
            // BUG 7: revert is not a licence to move what the human
            // has explicitly taken off the table
            if (st.role == Role.TALK || st.frozen) continue
            out.add(FaderWrite(st.cfg.index, base))
        }
        // the same respect a single overridden fader gets, for all of them
        revertHoldUntil = tSec + REVERT_HOLD_SEC
        log(tSec, "revert", null, 0f,
            "mains handed back — hands off for " +
            "${REVERT_HOLD_SEC.toInt()}s (tap MIXING to resume sooner)")
        return out
    }

    // ------------------------------------------------------------------
    private fun upwardAllowed(tSec: Double): Boolean =
        !frozenAll && !watchdogVeto && tSec >= clipHoldUntil &&
                tSec >= broadbandHoldUntil && meterFresh(tSec)

    private fun anyMotionAllowed(tSec: Double): Boolean =
        !frozenAll && meterFresh(tSec) && tSec >= revertHoldUntil

    fun tick(tSec: Double): List<FaderWrite> {
        // A long gap (app paused, Wi-Fi outage, clock jump) must never
        // buy a giant single move: cap the effective step to ~1 tick.
        val dt = if (lastTickT < 0) 1.0
                 else (tSec - lastTickT).coerceIn(0.0, 1.5)
        lastTickT = tSec
        if (takeoverT < 0 || !ready) return emptyList()
        if (!anyMotionAllowed(tSec)) return emptyList()
        val up = upwardAllowed(tSec)

        // -- 0. lead-vocal follow ----------------------------------------
        // the pointer is state, so it must be re-validated: a channel
        // re-roled mid-show (or one that lost its baseline in a partial
        // takeover) can no longer be the lead
        leadVocal?.let { cur ->
            val st = state[cur]
            if (st == null || st.baselineDb == null ||
                (st.role != Role.VOCAL && st.role != Role.BACKING_VOCAL)) {
                leadVocal = state.values.firstOrNull {
                    (it.role == Role.VOCAL || it.role == Role.BACKING_VOCAL) &&
                            it.baselineDb != null
                }?.cfg?.index
                lastLeadSwitch = tSec
                log(tSec, "lead", leadVocal, 0f,
                    if (leadVocal == null)
                        "no vocal channel on stage — vocal priority off"
                    else "${state[leadVocal!!]?.cfg?.name} now carries the " +
                         "lead (the previous lead left the vocal group)")
            }
        }
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
        recountGroups()
        val anch = anchorContribution()
        val anchor = anch.db
        val anchorPyr = anch.pyr
        // How far the ensemble as a whole has jumped over its own 20 s
        // average. A player who steps up for a solo rises well past
        // this; a chorus where everyone digs in does not.
        // How far the band as a whole has drifted since takeover (median,
        // so one hot channel cannot speak for everyone). Only drift
        // RELATIVE to this is the engine's business: a band that plays a
        // whole song quieter is playing a ballad, not drifting.
        val ensembleDrift = run {
            val d = ArrayList<Float>()
            for (st in state.values) {
                if (!st.active || st.isStatic) continue
                if (st.heardSec < settings.minHeardSec) continue
                if (st.preEma == null || st.takeRef == null) continue
                d.add(driftSinceTakeover(st))
            }
            if (d.isEmpty()) 0f else { d.sort(); d[d.size / 2] }
        }
        val anchorMeanOffset = run {
            val m = anch.members.mapNotNull { state[it]?.offset }
            if (m.isEmpty()) 0f else m.average().toFloat()
        }
        // the anchor group's own drift, as a group: what the LEVEL rule
        // below answers to. Per-channel drift is the BALANCE rule's job,
        // and charging both for it would correct the same dB twice.
        val anchorDrift = run {
            val m = anch.members.mapNotNull { i ->
                state[i]?.let { driftSinceTakeover(it) } }
            if (m.isEmpty()) 0f else m.average().toFloat()
        }
        val ensembleRise = run {
            var s = 0f; var k = 0
            for (st in state.values) {
                if (!st.active) continue
                val f = st.fastEma ?: continue
                if (st.riseHist.size < settings.featureWindowTicks) continue
                s += f - st.riseHist.first(); k++
            }
            if (k > 0) s / k else 0f
        }
        for ((idx, st) in state) {
            if (st.frozen) continue
            if (st.role == Role.TALK) {
                // handed to a human: give the fader back, then let go
                if (abs(st.offset) > 0.01f) { st.target = 0f; st.engaged = true }
                continue
            }
            if (tSec < st.overrideUntil) continue  // human owns it right now
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
                // never re-open an idle mic during a broadband event
                // (applause): that is the classic howl setup
                if (tSec < broadbandHoldUntil) continue
                st.idleRamped = false
                st.target = 0f
                st.fastUntil = tSec + settings.fastWindowSec
                log(tSec, "restore", idx, 0f,
                    "${st.cfg.name} back — rejoining the mix")
            }
            if (!st.active || st.heardSec < settings.minHeardSec) continue
            val pre = st.preEma ?: continue
            if (st.takeRef == null) st.takeRef = pre  // audition complete
            // FEATURE HOLD. A player who steps up for a solo is not
            // drift: without this the engine waited out the 20 s EMA and
            // then took the whole feature back off them, so a 90 s sax
            // solo ended exactly as loud as it started — and left the
            // player buried for half a minute after they stepped back.
            val fast = st.fastEma ?: pre
            // How far this channel has come up over the last few seconds.
            // Measured against its own level a fixed window ago, not
            // against its 20 s average: the difference of two EMAs can
            // only ever show about two thirds of a step, which put the
            // whole test inside the noise and let real solos through
            // unrecognised.
            val hadWindow = st.riseHist.size >= settings.featureWindowTicks
            val rose = if (hadWindow) fast - st.riseHist.first() else 0f
            st.riseHist.addLast(fast)
            while (st.riseHist.size > settings.featureWindowTicks)
                st.riseHist.removeFirst()
            if (st.featureStart < 0) {
                // A player digging in for a few seconds is not a solo,
                // and a short EMA of a dynamic channel crosses any single
                // threshold constantly — one noisy frame used to buy a
                // 90 s hold, and channels dropping in and out of hold at
                // random made the whole mix ride. Confirm it first.
                // a leaky counter, not a run: the short EMA of a real
                // solo dips below the line now and then, and demanding
                // an unbroken run let a genuine 90 s feature go
                // unrecognised
                if (hadWindow && rose - ensembleRise > settings.featureRiseDb)
                    st.featureVotes++
                else st.featureVotes = max(0, st.featureVotes - 1)
                if (st.featureVotes >= settings.featureConfirmTicks) {
                    st.featureStart = tSec
                    // freeze the reference at the moment of the step: the
                    // 20 s average catches up within half a minute, so
                    // "still above my own average" would end the hold
                    // while the player is mid-solo — which is exactly how
                    // a 90 s solo used to finish no louder than it began.
                    st.featureRef = pre
                    st.featureVotes = 0
                    // hold the fader exactly where it is: whatever the
                    // pyramid had already decided during the seconds it
                    // took to recognise the solo is not the plan any more
                    st.target = st.offset
                    st.engaged = false
                    log(tSec, "feature", idx, rose,
                        "${st.cfg.name} stepped up — leaving the feature " +
                        "with the player")
                }
            } else {
                // Ending the hold takes as much confirmation as starting
                // it. A single quiet bar inside a solo used to end it,
                // and the engine then cut the player 6 dB with two
                // seconds of their feature left to play.
                if (fast - st.featureRef < settings.featureRiseDb * 0.5f)
                    st.featureVotes++
                else st.featureVotes = max(0, st.featureVotes - 1)
                if (tSec - st.featureStart >= settings.featureHoldSec ||
                    st.featureVotes >= settings.featureConfirmTicks) {
                    st.featureStart = -1.0   // played out, or stepped back
                    st.featureVotes = 0
                    st.engaged = false
                }
            }
            if (st.featureStart >= 0) { st.target = st.offset; continue }
            val height = effHeight(st)
            val contrib = pre + base + st.offset
            val tgt: Float = if (anchor == null) {
                // nothing to anchor against (everyone still auditioning):
                // hold, correcting only this source's drift since takeover
                0f - driftSinceTakeover(st)
            } else if (idx in anch.members) {
                // The anchor sets the level of the whole mix, so it gets
                // its own two rules rather than being steered against
                // itself (which was a fixed point wherever it happened to
                // be — a ground loop that dragged the singer 10 dB down
                // left them there for the rest of the night):
                //  · BALANCE inside the group. A kick 10 dB under-gained
                //    used to get exactly zero correction and the whole
                //    band simply followed it down all night.
                //  · LEVEL back at the human's faders, but only for drift
                //    RELATIVE to the band. A band that plays a whole song
                //    quieter is a ballad and must stay one; a drummer
                //    whose kick channel is 9 dB hotter than everyone
                //    else's is a gain knob, and gets seated.
                val balance = -(contrib - anchor)
                val level = -(anchorMeanOffset + (anchorDrift - ensembleDrift))
                st.offset + balance + level
            } else {
                // contribution error vs (anchor + relative pyramid height)
                st.offset - (contrib - (anchor + (height - anchorPyr)))
            }
            // A source the engine has judged to be room tone, a ground
            // loop or an open mic nobody is using can be seated, never
            // lifted. Turning up an empty mic only turns up the room —
            // and it is the classic way to walk a stage into feedback.
            val bounded = boundOffset(
                if (st.isStatic) min(tgt, 0f) else tgt, base)
            // Deadband as HYSTERESIS: a small error is ignored, but once
            // we start moving we converge all the way. Resting where the
            // error happened to fall made the final fader depend on
            // which side it approached from.
            // stereo pair: decide once, from the pair's mean
            // contribution, and give both halves the same offset
            val mate = st.cfg.pairWith?.let { state[it] }
            val boundedPair = if (mate != null && mate.baselineDb != null &&
                mate.active && !st.isStatic) {
                val mPre = mate.preEma
                if (mPre != null) {
                    val mContrib = mPre + mate.baselineDb!! + mate.offset
                    val myContrib = pre + base + st.offset
                    val pairErr = ((myContrib + mContrib) / 2f) -
                            (anchor!! + (height - anchorPyr))
                    boundOffset(st.offset - pairErr, base)
                } else bounded
            } else bounded
            val err = abs(boundedPair - st.offset)
            if (err > settings.deadbandDb) st.engaged = true
            // Disengage at HALF the trigger, not at 0.25 dB: chasing a
            // moving source all the way down to a quarter of a dB turned
            // dynamic playing into 1.65 dB of fader travel per channel
            // per minute. Real hysteresis instead of noise-tracking.
            else if (err < settings.deadbandDb * 0.5f) st.engaged = false
            if (st.engaged) {
                if (abs(boundedPair - st.target) > 0.25f) {
                    st.target = boundedPair
                    log(tSec, "pyramid", idx, boundedPair,
                        "${st.cfg.name} steering to its place in the pyramid " +
                        "(%+.1f dB)".format(boundedPair))
                }
            } else if (!st.idleRamped && st.duckDb == 0f) {
                st.target = st.offset  // settled
            }
        }

        // -- 2. vocal priority on the mains (cut-only) --------------------
        run {
            val lead = leadVocal?.let { state[it] }
            if (lead == null) {
                // nobody is leading: release every duck rather than
                // leaving the band pinned for the rest of the night
                for (st in state.values) if (st.duckDb < -0.01f)
                    st.duckDb = min(0f,
                        st.duckDb + (settings.leadPerSecDb * dt).toFloat())
                return@run
            }
            val leadPre = lead.preEma
            val leadBase = lead.baselineDb
            if (!lead.active || leadPre == null || leadBase == null) {
                for (st in state.values) if (st.duckDb < 0f)
                    st.duckDb = min(0f, st.duckDb + (1f * dt).toFloat())
                return@run
            }
            val band = state.values.filter {
                it.cfg.index != lead.cfg.index &&
                        it.role != Role.VOCAL && it.role != Role.BACKING_VOCAL &&
                        it.role != Role.TALK && it.active &&
                        it.preEma != null && it.baselineDb != null
            }
            if (band.isEmpty()) return@run
            // Measure the lead against what the room hears — the POWER
            // SUM of the band, not the average of its channels. Against
            // the average, a vocal 10 dB under the band as a whole
            // scored "on top 99 % of the night": the health readout and
            // the duck were both being told a comfortable lie.
            val leadContrib = leadPre + leadBase + lead.offset
            val bandContrib = powerSum(band.map {
                it.preEma!! + it.baselineDb!! + it.offset })
            val wantGap = height(Role.VOCAL) -
                    powerSum(band.map { effHeight(it) })
            val gap = leadContrib - bandContrib
            // health sample: is the lead where it belongs?
            val hOk = if (gap >= wantGap - settings.duckTriggerDb) 1f else 0f
            vocalOnTopEma += 0.02f * (hOk - vocalOnTopEma)
            vocalHealthSamples++
            // any channel that left the band (went quiet) must release
            for (st in state.values)
                if (st.duckDb < -0.01f && (!st.active || st !in band))
                    st.duckDb = min(0f, st.duckDb + (1f * dt).toFloat())

            // CLOSED LOOP, not a switch. The duck changes the very gap it
            // is judging, so "duck hard the moment the gap is bad,
            // release the moment it is good" has no resting place: it
            // ducked 4 dB, the gap read fine, it released, the gap read
            // bad — an audible sawtooth across the whole band, which got
            // far worse once the gap was measured honestly (power sum)
            // and a rail-limited vocal could never reach its target.
            // Instead: one slewed controller whose fixed point is the
            // trigger itself, so it settles wherever the vocal needs it.
            val err = (wantGap - settings.duckTriggerDb) - gap
            if (abs(err) > 0.5f) {
                val step = (settings.leadPerSecDb * dt).toFloat()
                val move = min(step, abs(err) * 0.5f) * (if (err > 0) -1f else 1f)
                for (st in band) {
                    val was = st.duckDb
                    st.duckDb = (st.duckDb + move)
                        .coerceIn(-settings.duckMaxDb, 0f)
                    if (was > -0.01f && st.duckDb < -0.01f)
                        log(tSec, "duck", st.cfg.index, st.duckDb,
                            "lead vocal buried — ducking the band in the mains")
                }
            }
        }

        // health sample: fraction of active channels sitting at their
        // targets (inside the deadband)
        run {
            var ok = 0; var n = 0
            for (st in state.values) {
                if (!st.active || st.role == Role.TALK ||
                    st.baselineDb == null) continue
                n++
                if (kotlin.math.abs(st.target - st.offset) <=
                    settings.deadbandDb + 0.5f) ok++
            }
            if (n > 0) inPlaceEma += 0.02f * (ok.toFloat() / n - inPlaceEma)
            healthTicks++
        }

        // -- 3. slew + rails + budget -> fader writes ---------------------
        val writes = ArrayList<FaderWrite>()
        for ((_, st) in state) {
            if (st.frozen) continue
            // TALK channels are released, not driven: the only move
            // allowed is the slew back to where the human left it
            if (st.role == Role.TALK && abs(st.offset) <= 0.01f) continue
            if (tSec < st.overrideUntil) continue
            val base = st.baselineDb ?: continue
            val tgt = boundOffset(st.target + st.duckDb, base)
            val cur = st.offset
            if (abs(tgt - cur) < 0.05f) continue
            val step: Float = if (tgt > cur) {
                if (!up) 0f
                else {
                    val fast = tSec < st.fastUntil && cur < 0f
                    val rate = if (fast) settings.fastPerSecDb
                               else settings.leadPerSecDb
                    val wanted = min((rate * dt).toFloat(), tgt - cur)
                    // Budget governs POSITIVE offset only: climbing back
                    // from below baseline toward 0 spends no headroom,
                    // so a quiet channel can always recover even when
                    // other channels hold the whole boost budget. Above
                    // baseline, what is spent is how much LOUDER the
                    // boosts have actually made the mix.
                    // ask what the step WOULD cost, not what has already
                    // been spent: sixteen channels each granted a full
                    // fast-lane step on the strength of one "there is
                    // room" reading is how a budget gets blown.
                    val end = if (cur + wanted <= 0f ||
                                  boostLoudnessDb(st.cfg.index, cur + wanted) <=
                                      settings.mixBoostBudgetDb)
                              cur + wanted else max(cur, 0f)
                    (end - cur).coerceAtLeast(0f)
                }
            } else {
                -min((settings.cutPerSecDb * dt).toFloat(), cur - tgt)
            }
            val minStep = min(0.01f, (settings.cutPerSecDb * dt).toFloat() * 0.5f)
            if (abs(step) < minStep) continue
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

    /** live count of channels sharing each height group */
    private val groupN = HashMap<Role, Int>()

    /**
     * Which group's height a channel is steered to. Vocals are placed by
     * who is carrying the song, not by which socket they are plugged
     * into: the lead (and a genuine duet partner) belong to the VOCAL
     * group, every other mic to the backing group.
     */
    private fun heightRole(st: ChannelState): Role = when (st.role) {
        Role.VOCAL, Role.BACKING_VOCAL ->
            if (st.cfg.index == leadVocal || isDuetPartner(st)) Role.VOCAL
            else Role.BACKING_VOCAL
        else -> st.role
    }

    /**
     * A second voice singing WITH the lead, not behind it.
     *
     * Restricted to channels configured as VOCAL. "Congo / Vox 3" is a
     * conga most of the night, and level-based vocal activity reads a
     * drum as a singer perfectly — it was being promoted to duet
     * partner and landing 2.6 dB over an identical conga on the next
     * channel, purely because of the channel's name. When a third
     * singer really does take that mic, lead-follow hands them the lead
     * (and the top of the pyramid) on the evidence of them carrying
     * the song.
     */
    private fun isDuetPartner(st: ChannelState): Boolean {
        if (st.role != Role.VOCAL || st.cfg.index == leadVocal) {
            st.duetLatched = false
            return false
        }
        val lead = leadVocal?.let { state[it] }
        if (lead == null) { st.duetLatched = false; return false }
        // Latched, because joining the vocal group moves the whole
        // group's per-channel height (two voices share one group
        // target): a bare threshold let a mic hovering at the line
        // hand every channel a 3 dB step several times a minute.
        val both = min(st.vocalAct, lead.vocalAct)
        if (!st.duetLatched && both > 0.6f) st.duetLatched = true
        else if (st.duetLatched && both < 0.4f) st.duetLatched = false
        return st.duetLatched
    }

    private fun recountGroups() {
        groupN.clear()
        for (st in state.values) {
            if (!st.active || st.isStatic || st.role == Role.TALK) continue
            if (st.baselineDb == null || st.preEma == null) continue
            if (st.heardSec < settings.minHeardSec) continue
            groupN.merge(heightRole(st), 1, Int::plus)
        }
    }

    /**
     * Per-channel pyramid height: the role's GROUP target (plus the
     * taste learned from feedback) shared out across however many of
     * its channels are playing right now. Three congas together hit the
     * percussion group's target; one conga alone hits it on its own.
     */
    private fun height(role: Role): Float {
        val n = (groupN[role] ?: 1).coerceAtLeast(1)
        return (pyramid[role] ?: -7f) + (pyramidBias[role] ?: 0f) -
                10f * log10(n.toFloat())
    }

    /** height for this channel, including duet and low-fill adjustments */
    private fun effHeight(st: ChannelState): Float {
        val h = height(heightRole(st))
        return when {
            isDuetPartner(st) -> h - 1f
            st.role == Role.KEYS && keysLowFill -> h + 2f
            else -> h
        }
    }

    /** incoherent (power) sum of a set of dB values — what the room hears */
    private fun powerSum(v: List<Float>): Float =
        if (v.isEmpty()) -140f
        else (10.0 * log10(v.sumOf { 10.0.pow(it / 10.0) })).toFloat()

    /**
     * How much louder the engine's boosts have made the mains, in dB:
     * the mix as it stands, against the same mix with every positive
     * offset taken back out. This is what `mixBoostBudgetDb` limits.
     */
    @JvmOverloads
    fun boostLoudnessDb(ch: Int = -1, offsetIfMoved: Float = 0f): Float {
        var on = 0.0; var off = 0.0
        for (st in state.values) {
            if (!st.active) continue
            val pre = st.preEma ?: continue
            val base = st.baselineDb ?: continue
            val o = if (st.cfg.index == ch) offsetIfMoved else st.offset
            val c = (pre + base + o).toDouble()
            on += 10.0.pow(c / 10.0)
            off += 10.0.pow((c - max(0f, o)) / 10.0)
        }
        return if (off <= 0.0 || on <= 0.0) 0f
               else (10.0 * log10(on / off)).toFloat()
    }

    /**
     * Clamp an offset into the authority window for a channel whose
     * fader baseline is [base]. A baseline already above the absolute
     * cap makes the upper limit smaller than the lower one — clamp the
     * window itself instead of crashing (kotlin's coerceIn throws when
     * min > max).
     */
    private fun boundOffset(v: Float, base: Float): Float {
        if (v.isNaN()) return 0f
        val lo = max(-settings.maxBelowBaselineDb, FaderLaw.MIN_DB - base)
        val hi = min(settings.maxAboveBaselineDb, settings.absFaderCapDb - base)
        return if (hi <= lo) lo else v.coerceIn(lo, hi)
    }

    /** Meter sanitation: NaN/Inf/absurd values can never reach state. */
    private fun sane(db: Float): Float? =
        if (db.isNaN() || db.isInfinite() || db < -200f || db > 60f) null
        else db

    private fun isBassName(name: String): Boolean {
        val n = name.lowercase()
        return listOf("bass", "di 2", "di2", "sub", "808").any { it in n }
    }

    /** the mix anchor: its contribution, its pyramid height, its members */
    private class Anchor(val db: Float?, val pyr: Float, val members: Set<Int>)

    private fun contributionMean(roles: Set<Role>): Anchor? {
        var sum = 0f; var pyr = 0f
        val members = HashSet<Int>()
        for (st in state.values) {
            if (st.role !in roles || !st.active || st.isStatic) continue
            val pre = st.preEma ?: continue
            val base = st.baselineDb ?: continue
            if (st.heardSec < settings.minHeardSec) continue
            sum += pre + base + st.offset
            pyr += effHeight(st)
            members.add(st.cfg.index)
        }
        val n = members.size
        return if (n > 0) Anchor(sum / n, pyr / n, members) else null
    }

    /**
     * Anchor cascade for an ever-changing stage: foundation when a
     * rhythm section is playing; otherwise the active accompaniment
     * (guitar/piano behind a singer); otherwise the lead voice itself.
     */
    private fun anchorContribution(): Anchor {
        contributionMean(setOf(Role.FOUNDATION))?.let { return it }
        contributionMean(setOf(Role.KEYS, Role.RHYTHM_GTR, Role.SOLO_GTR,
            Role.PERCUSSION, Role.COLOR, Role.INSTRUMENT))?.let { return it }
        val lead = leadVocal?.let { state[it] }
        if (lead != null && lead.active &&
            lead.heardSec >= settings.minHeardSec) {
            val pre = lead.preEma; val base = lead.baselineDb
            if (pre != null && base != null)
                return Anchor(pre + base + lead.offset, height(Role.VOCAL),
                    setOf(lead.cfg.index))
        }
        return Anchor(null, 0f, emptySet())
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

    /**
     * True when this channel's level has barely moved for a minute and a
     * half while sitting well under the stage: a ground loop, room tone,
     * or an open mic nobody is using. Such a channel is kept out of the
     * mix anchor and can never earn a boost.
     */
    fun isStaticSource(ch: Int): Boolean = state[ch]?.isStatic == true
    fun boostsAllowed(tSec: Double): Boolean = upwardAllowed(tSec)

    fun meterFresh(tSec: Double): Boolean =
        lastMeterT >= 0 && tSec - lastMeterT <= settings.meterTimeoutSec

    fun holdReason(tSec: Double): String? = when {
        frozenAll -> "FROZEN by operator"
        tSec < revertHoldUntil ->
            "handed back to you — resuming in " +
                    "${(revertHoldUntil - tSec).toInt()}s"
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
        val d = Decision(t, kind, ch, null, delta, reason)
        decisions.addFirst(d)
        while (decisions.size > 60) decisions.removeLast()
        onDecision?.invoke(d)
    }

    /**
     * Every decision, as it is made. The `decisions` deque only keeps
     * the last 60 for the console; a show log wants all of them.
     */
    var onDecision: ((Decision) -> Unit)? = null

    /** what the mix is currently anchored to — the reference every
     *  pyramid height is measured from */
    data class AnchorInfo(val contributionDb: Float?, val pyramidDb: Float,
                          val members: Set<Int>)

    fun anchorInfo(): AnchorInfo {
        recountGroups()
        val a = anchorContribution()
        return AnchorInfo(a.db, a.pyr, a.members)
    }

    /** this channel's current pyramid height, in dB under the anchor */
    fun heightDb(ch: Int): Float =
        state[ch]?.let { recountGroups(); effHeight(it) } ?: 0f

    /** the live count of channels sharing each height group */
    fun groupCounts(): Map<Role, Int> {
        recountGroups()
        return groupN.toMap()
    }
}
