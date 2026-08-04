package com.stagemix.app

import android.content.Context
import android.util.Log
import com.stagemix.engine.Decision
import com.stagemix.engine.Role
import com.stagemix.engine.StageEngine
import com.stagemix.engine.ToneDoctor
import java.io.File
import java.io.FileWriter
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * The show log: everything the autopilot heard, decided and wrote,
 * written to a plain text file on the tablet as the night happens.
 *
 * The point of this file is a conversation the morning after. It has to
 * be readable by a human, pasteable into a chat window, and complete
 * enough to answer "why did it do that?" without the mixer present — so
 * it carries the levels it heard, the balance it was aiming for, every
 * fader/EQ/compressor move with the reason, and the protocol events
 * (meter dropouts, keep-alives, takeover) that explain the gaps.
 *
 * It is written with no network of any kind: the tablet lives on the
 * mixer's own Wi-Fi all night.
 *
 * Layout, all lines timestamped `HH:MM:SS.mmm` from wall clock plus the
 * show clock in seconds since the log opened:
 *
 *   HEAD   one-time: build, mixer, channels, roles, settings, learning
 *   TAKE   takeover: the fader positions that became the authority
 *   LVL    every [snapshotSec]: one line per channel, everything numeric
 *   MIX    every [snapshotSec]: anchor, health, budget, hold reason
 *   DEC    every engine decision (pyramid, duck, idle, feature, lead…)
 *   FADER  every fader write, dB
 *   EQ     every EQ band move, with the band's drift from soundcheck
 *   COMP   every compressor threshold move, with the GR it is chasing
 *   TONE   every [snapshotSec]: per-channel band shape vs reference,
 *          harshness, detected vocal register, comp gain reduction
 *   NET    protocol: connect, subscribe, meter loss, partial takeover
 *   USER   what the operator did: MIXING, FREEZE, chips, fader grabs
 *   SUM    every minute: a one-line state of the mix
 *
 * Grep-friendly on purpose: `grep ' FADER ' show.log` is a night's fader
 * moves, `grep ' DEC ' show.log` is the reasoning.
 */
class ShowLog(ctx: Context, private val snapshotSec: Double = 5.0) {

    private val dir = File(ctx.getExternalFilesDir(null), "logs")
    val file: File
    private var w: FileWriter? = null
    private val t0 = System.currentTimeMillis()
    private var lastSnap = -1.0
    private var lastTone = -1.0
    private var lastSum = -1.0
    private var lines = 0
    private var dropped = 0

    private val clock = SimpleDateFormat("HH:mm:ss.SSS", Locale.ROOT)
    private val stamp = SimpleDateFormat("yyyy-MM-dd_HH-mm", Locale.ROOT)

    init {
        dir.mkdirs()
        file = File(dir, "stagemix_${stamp.format(Date())}.log")
        w = try { FileWriter(file, true) } catch (e: Exception) {
            Log.w("StageMix", "show log unavailable: ${e.message}"); null
        }
        // keep the last ten nights, no more
        dir.listFiles()?.sortedByDescending { it.name }?.drop(10)
            ?.forEach { runCatching { it.delete() } }
    }

    // ------------------------------------------------------------------
    @Synchronized private fun put(tag: String, body: String) {
        val out = w ?: return
        // A night is bounded: past the cap we keep counting but stop
        // writing, so a runaway loop can never fill the tablet.
        if (lines >= MAX_LINES) { dropped++; return }
        try {
            out.write("%s %7.1f %-5s %s\n".format(Locale.ROOT,
                clock.format(Date()), (System.currentTimeMillis() - t0) / 1000.0,
                tag, body))
            lines++
            if (lines % 40 == 0) out.flush()
        } catch (e: Exception) { /* a full disk must not stop the mix */ }
    }

    @Synchronized fun flush() { runCatching { w?.flush() } }

    @Synchronized fun close() {
        runCatching { w?.flush(); w?.close() }
        w = null
    }

    fun note(tag: String, text: String) = put(tag, text)

    /** the health scores read -1 until there is enough of a night to judge */
    private fun pct(v: Int) = if (v < 0) "n/a" else "$v%"

    // ------------------------------------------------------------------
    fun head(mixer: AppState.MixerInfo, e: StageEngine,
             names: Map<Int, String>, nights: Int, taste: String) {
        put("HEAD", "StageMix show log — this file is the whole night; " +
            "paste it back and it can be read without the mixer present")
        put("HEAD", "date=${SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.ROOT)
            .format(Date())}  night=${nights + 1}")
        put("HEAD", "mixer name='${mixer.name}' model='${mixer.model}' " +
            "fw='${mixer.firmware}' ip=${mixer.ip}")
        put("HEAD", "learned taste: ${taste.ifBlank { "(none yet)" }}")
        val s = e.settings
        put("HEAD", "authority: -%.0f..+%.0f dB around takeover, cap %+.0f dB; "
            .format(Locale.ROOT, s.maxBelowBaselineDb, s.maxAboveBaselineDb,
                s.absFaderCapDb) +
            "deadband %.1f dB; boost budget %.1f dB of mix loudness"
                .format(Locale.ROOT, s.deadbandDb, s.mixBoostBudgetDb))
        put("HEAD", "pace: boost %.1f dB/s, fast lane %.1f, cut %.1f; "
            .format(Locale.ROOT, s.leadPerSecDb, s.fastPerSecDb, s.cutPerSecDb) +
            "listen %.0fs, per-channel audition %.0fs"
                .format(Locale.ROOT, s.learnSec, s.minHeardSec))
        put("HEAD", "feature hold: +%.1f dB over %d s holds the fader %.0f s"
            .format(Locale.ROOT, s.featureRiseDb, s.featureWindowTicks,
                s.featureHoldSec))
        for ((ch, st) in e.state.toSortedMap()) {
            val target = e.pyramid[st.role]
            put("HEAD", "ch%02d %-18s role=%-14s group target %s"
                .format(Locale.ROOT, ch + 1,
                    names[ch] ?: st.cfg.name, st.role.name,
                    target?.let { "%+.0f dB".format(Locale.ROOT, it) } ?: "n/a"))
        }
        put("HEAD", "columns of LVL: ch name | src=pre-fader dB heard | " +
            "fast=3s | fader | off=our offset | duck | contrib=src+fader | " +
            "want=where the pyramid puts it | h=height under anchor | " +
            "flags")
        put("HEAD", "columns of TONE: shape=live 4-band tone (zero-mean) | " +
            "drift=how far that is from the sound approved at soundcheck | " +
            "eq=our correction per band | thr=comp threshold move | " +
            "harsh=2-6 kHz over the channel's own body | gr=gain reduction " +
            "| reg=detected singer register")
        put("HEAD", "MONITORS ARE NEVER TOUCHED — no bus send appears in " +
            "this log because the engine cannot emit one")
    }

    fun takeover(faders: Map<Int, Float>, names: Map<Int, String>) {
        put("TAKE", "MIXING on — these fader positions are now the " +
            "authority bounds' centre (${faders.size} channels)")
        for ((ch, db) in faders.toSortedMap())
            put("TAKE", "ch%02d %-18s %+6.2f dB".format(Locale.ROOT,
                ch + 1, names[ch] ?: "", db))
    }

    fun decision(d: Decision) {
        put("DEC", "%-9s %s %s%s".format(Locale.ROOT, d.kind,
            d.channel?.let { "ch%02d".format(Locale.ROOT, it + 1) } ?: "----",
            if (d.deltaDb != 0f) "%+6.2f dB  ".format(Locale.ROOT, d.deltaDb)
            else "          ", d.reason))
    }

    fun fader(ch: Int, db: Float, name: String) =
        put("FADER", "ch%02d %-18s -> %+6.2f dB".format(Locale.ROOT,
            ch + 1, name, db))

    fun eq(ch: Int, band: Int, db: Float, driftDb: Float, name: String) =
        put("EQ", ("ch%02d %-18s band%d -> %+5.2f dB " +
            "(soundcheck tone had drifted %+.2f dB in this band)")
            .format(Locale.ROOT, ch + 1, name, band + 1, db, driftDb))

    fun comp(ch: Int, thrDb: Float, grDb: Float?, refGr: Float?, name: String) =
        put("COMP", ("ch%02d %-18s threshold -> %+6.2f dB " +
            "(gain reduction now %s, at soundcheck %s)")
            .format(Locale.ROOT, ch + 1, name, thrDb,
                grDb?.let { "%.1f dB".format(Locale.ROOT, it) } ?: "?",
                refGr?.let { "%.1f dB".format(Locale.ROOT, it) } ?: "?"))

    fun net(text: String) = put("NET", text)
    fun user(text: String) = put("USER", text)

    // ------------------------------------------------------------------
    /** the periodic picture: what it heard and what it is aiming for */
    fun snapshot(t: Double, e: StageEngine, doctor: ToneDoctor?,
                 names: Map<Int, String>, directing: Boolean) {
        if (lastSnap >= 0 && t - lastSnap < snapshotSec) return
        lastSnap = t
        val a = e.anchorInfo()
        val h = e.health()
        put("MIX", ("anchor %s (pyramid %+.1f, from %s) | vocal on top %s | " +
            "in place %d%% | boosts have added %.2f dB to the mix | %s%s")
            .format(Locale.ROOT,
                a.contributionDb?.let { "%.1f dB".format(Locale.ROOT, it) }
                    ?: "none yet",
                a.pyramidDb,
                if (a.members.isEmpty()) "-" else a.members.sorted()
                    .joinToString("+") { "ch%02d".format(Locale.ROOT, it + 1) },
                pct(h.vocalOnTopPct), h.inPlacePct, e.boostLoudnessDb(),
                if (directing) "MIXING" else "watching (shadow)",
                e.holdReason(t)?.let { " | HOLD: $it" } ?: ""))
        val gc = e.groupCounts()
        if (gc.isNotEmpty()) put("MIX", "playing now: " +
            gc.entries.sortedBy { it.key.name }.joinToString("  ") {
                "${it.key.name}x${it.value}" })
        for ((ch, st) in e.state.toSortedMap()) {
            val base = st.baselineDb ?: continue
            val src = st.preEma ?: st.lastLevelDb
            val contrib = src + base + st.offset
            val want = a.contributionDb?.let {
                it + (e.heightDb(ch) - a.pyramidDb) }
            val flags = buildString {
                if (!st.active) append("silent ")
                if (st.isStatic) append("ROOM-TONE ")
                if (st.idleRamped) append("idle-eased ")
                if (st.featureStart >= 0) append("FEATURE-HOLD ")
                if (st.frozen) append("locked ")
                if (t < st.overrideUntil) append("YOURS(%ds) "
                    .format(Locale.ROOT, (st.overrideUntil - t).toInt()))
                if (ch == e.leadVocal) append("LEAD ")
                if (st.heardSec < e.settings.minHeardSec) append("auditioning ")
            }
            put("LVL", ("ch%02d %-18s src%7.1f fast%7.1f fader%+6.2f " +
                "off%+6.2f duck%+5.2f contrib%7.1f want%s h%+6.1f %s")
                .format(Locale.ROOT, ch + 1, names[ch] ?: st.cfg.name,
                    src, st.fastEma ?: src, base + st.offset, st.offset,
                    st.duckDb, contrib,
                    want?.let { "%7.1f".format(Locale.ROOT, it) } ?: "      -",
                    e.heightDb(ch), flags.trim()))
        }
        // Tone moves slowly and the RTA only visits each channel every
        // few seconds, so it gets its own, longer beat — otherwise it
        // triples the size of the file for no extra information.
        if (doctor != null && (lastTone < 0 || t - lastTone >= TONE_SEC)) {
            lastTone = t
            tone(doctor, names)
        }
    }

    private fun tone(d: ToneDoctor, names: Map<Int, String>) {
        for ((ch, st) in d.state.toSortedMap()) {
            val live = st.liveBands ?: continue
            val ref = st.refBands
            val drift = ref?.let { r -> FloatArray(4) { live[it] - r[it] } }
            put("TONE", ("ch%02d %-18s shape[%s] drift[%s] eq[%s] " +
                "thr%+5.2f harsh%s gr%s reg%s%s")
                .format(Locale.ROOT, ch + 1, names[ch] ?: "",
                    live.joinToString(" ") { "%+5.1f".format(Locale.ROOT, it) },
                    drift?.joinToString(" ") { "%+5.1f".format(Locale.ROOT, it) }
                        ?: "  no soundcheck ",
                    st.eqOffset.joinToString(" ") {
                        "%+4.2f".format(Locale.ROOT, it) },
                    st.thrOffset,
                    st.harshEma?.let { "%+5.1f".format(Locale.ROOT, it) } ?: "    -",
                    st.grEma?.let { "%5.1f".format(Locale.ROOT, it) } ?: "    -",
                    when (st.register) {
                        1 -> "male"; 2 -> "female"; else -> "-" },
                    buildString {
                        if (st.lowFill) append(" LOW-FILL")
                        if (!st.grTrusted) append(" gr-untrusted")
                        if (st.frozen) append(" locked")
                    }))
        }
    }

    /** once a minute: the single line you would read first */
    fun summary(t: Double, e: StageEngine, names: Map<Int, String>) {
        if (lastSum >= 0 && t - lastSum < 60.0) return
        lastSum = t
        val h = e.health()
        val a = e.anchorInfo()
        val loudest = e.state.entries
            .filter { it.value.active && it.value.baselineDb != null }
            .maxByOrNull { (it.value.preEma ?: -128f) + it.value.baselineDb!! +
                    it.value.offset }
        val moved = e.state.entries.filter {
            kotlin.math.abs(it.value.offset) > 1f }
            .sortedByDescending { kotlin.math.abs(it.value.offset) }
            .take(4).joinToString(" ") {
                "ch%02d%+.1f".format(Locale.ROOT, it.key + 1, it.value.offset) }
        put("SUM", ("%d ch playing | loudest %s | lead %s | vocal on top " +
            "%s | in place %d%% | you out-mixed it %d times | biggest " +
            "moves: %s")
            .format(Locale.ROOT, a.members.size.coerceAtLeast(
                e.activeChannels().size),
                loudest?.let { names[it.key] ?: it.value.cfg.name } ?: "-",
                e.leadVocal?.let { names[it] ?: "ch%02d".format(Locale.ROOT, it + 1) }
                    ?: "none",
                pct(h.vocalOnTopPct), h.inPlacePct, h.overrides,
                moved.ifBlank { "none" }))
    }

    fun footer(e: StageEngine) {
        val h = e.health()
        put("SUM", "END OF NIGHT — vocal on top ${pct(h.vocalOnTopPct)}, " +
            "channels in place ${h.inPlacePct}%, you out-mixed it " +
            "${h.overrides} times over ${h.ticks} ticks")
        if (dropped > 0) put("SUM",
            "$dropped lines were dropped after the $MAX_LINES-line cap")
        flush()
    }

    companion object {
        /** ~30 MB of text at the widest lines; a long night is ~150k */
        private const val MAX_LINES = 400_000
        /** how often the per-channel tone picture is written */
        private const val TONE_SEC = 30.0
    }
}
