package com.stagemix.engine

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
class ShowLog(
    baseDir: File,
    private val snapshotSec: Double = 5.0,
    /** override the file name (the replay tool names logs after the take) */
    name: String? = null,
) {

    private val dir = File(baseDir, "logs")
    val file: File
    private var w: FileWriter? = null
    private val t0 = System.currentTimeMillis()
    private var lastSnap = -1.0
    private var lastTone = -1.0
    private var lastSum = -1.0
    private var lastDgst = -1.0
    private var lastBeat = -1.0
    private var lastCard = -1.0
    private var lines = 0
    private var dropped = 0
    private var warnedHardCap = false

    private val clock = SimpleDateFormat("HH:mm:ss.SSS", Locale.ROOT)
    private val stamp = SimpleDateFormat("yyyy-MM-dd_HH-mm", Locale.ROOT)

    init {
        dir.mkdirs()
        file = File(dir, name ?: "stagemix_${stamp.format(Date())}.log")
        w = try { FileWriter(file, true) } catch (e: Exception) { null }
        // keep the last ten nights, no more
        dir.listFiles()?.sortedByDescending { it.name }?.drop(10)
            ?.forEach { runCatching { it.delete() } }
    }

    // ------------------------------------------------------------------
    /**
     * @param tSec the ENGINE's clock, when the caller has it.
     *
     * Every number the engine prints — "silent 25s", the feature hold,
     * the ride's dwell — is measured on that clock, and the log was
     * stamped with a different one (wall time since the file opened).
     * Close enough to be misleading, and in a replay not close at all.
     * Where the caller knows the engine's time, the line carries it.
     */
    @Synchronized private fun put(tag: String, body: String,
                                  tSec: Double? = null) {
        val out = w ?: return
        // A night is bounded: past the cap we keep counting but stop
        // writing, so a runaway loop can never fill the tablet — EXCEPT
        // for the record of what the app did and what the operator did.
        // §5: "a decision is never dropped, even when a bulk log is
        // trimmed." So the hard cap still throws away the running
        // picture (LVL/TONE, already thinned at the soft cap) but never
        // a DEC, FADER, MARK or USER line. Those are bounded in
        // practice — a night has hundreds of them, not hundreds of
        // thousands — so exempting them cannot fill a disk.
        if (lines >= MAX_LINES && tag !in KEEP_ALWAYS) { dropped++; return }
        if (lines >= MAX_LINES && !warnedHardCap) {
            warnedHardCap = true
            // one honest marker that the picture is being dropped,
            // written on the way past the cliff rather than only in the
            // footer nobody reaches until teardown
            put("MARK", "log passed ${MAX_LINES} lines — the running " +
                "picture is being dropped from here; decisions still kept")
        }
        // AND THE LAST QUARTER OF IT BELONGS TO THE EVIDENCE.
        //
        // The per-channel picture is written every second for every
        // channel — sixteen lines a second, a quarter of a million over
        // four hours — so on a long night it is the snapshot that eats
        // the budget, and everything that says what the app actually
        // DID goes over the cliff with it. On the night of the 7th
        // there was not one FADER line in 48 MB, which meant there was
        // no way to tell how much of the fader travel had been ours.
        //
        // Past the soft cap the running picture stops and the record of
        // decisions, writes, errors and your own presses keeps going.
        // A log that thins out is worth more than one that stops.
        if (lines >= SOFT_LINES && tag in BULK_TAGS) { dropped++; return }
        try {
            // TWO CLOCKS IN ONE COLUMN IS WORSE THAN ONE.
            //
            // Lines that knew the engine's time printed it; the rest
            // printed wall-time since the file opened, in the same
            // column, with nothing to tell them apart. Reading back a
            // three-night file that way produced a phantom fourth
            // evening — the same hours, counted twice on two different
            // scales. The show clock is the engine's or it is blank.
            out.write("%s %9s %-5s %s\n".format(Locale.ROOT,
                clock.format(Date()),
                tSec?.let { "%.1f".format(Locale.ROOT, it) } ?: "-",
                tag, body))
            lines++
            if (lines % 40 == 0) out.flush()
        } catch (e: Exception) { /* a full disk must not stop the mix */ }
    }

    /** put(), with the engine's clock: see the note on [put] */
    private fun putT(t: Double, tag: String, body: String) = put(tag, body, t)

    /** how long this file has been open, in hours */
    fun ageHours(): Double = (System.currentTimeMillis() - t0) / 3_600_000.0

    /**
     * NOTHING IS HAPPENING, SAID ONCE EVERY FIVE MINUTES.
     *
     * The tablet gets left switched on. Over one weekend this wrote
     * three days of five-second snapshots of an empty bar — 55 MB, a
     * quarter of a million lines of sixteen silent channels — and the
     * running picture of the actual gigs went over the line cap because
     * of it. An empty room is one line every five minutes.
     */
    @Synchronized fun heartbeat(tSec: Double, text: String) {
        if (lastBeat >= 0 && tSec - lastBeat < IDLE_BEAT_SEC) return
        lastBeat = tSec
        put("IDLE", text, tSec)
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
    fun head(mixer: String, e: StageEngine,
             names: Map<Int, String>, nights: Int, taste: String,
             build: String = "") {
        put("HEAD", "StageMix show log — this file is the whole night; " +
            "paste it back and it can be read without the mixer present")
        put("HEAD", "date=${SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.ROOT)
            .format(Date())}  night=${nights + 1}")
        // WHICH BUILD WROTE THIS. Without it, reading a log means
        // guessing which version's behaviour is on the page — and the
        // behaviour changes between gigs.
        put("HEAD", "build ${build.ifBlank { "(unknown)" }}")
        put("HEAD", "mixer $mixer")
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
            "plan=the contribution this channel is meant to make | " +
            "err=how far from it we think it is | " +
            "want=where the pyramid puts it | h=height under anchor | " +
            "flags")
        put("HEAD", "columns of DGST and CARD: fader=where it is now | " +
            "Δtake=how far from where you had it at takeover | app=dB of " +
            "fader this app has moved on it | you=dB you moved by hand | " +
            "w/y=writes by us / gestures by you | act=% of the night it " +
            "was playing | map=how much of its spectrum has been heard | " +
            "lowEdge=where its low end really stops | lump=a resonance " +
            "over its own trend")
        put("HEAD", "columns of TONE: shape=live 4-band tone (zero-mean) | " +
            "drift=how far that is from the sound approved at soundcheck | " +
            "eq=our correction per band | thr=comp threshold move | " +
            "harsh=2-6 kHz over the channel's own body | gr=gain reduction " +
            "| reg=detected singer register")
        put("HEAD", "NO BUS MASTER IS EVER MOVED. When monitor keeping " +
            "is on, the app may correct wedge SENDS slightly — cut-first, " +
            "bounded, following your hand — and those appear here as " +
            "'wedge' PARAM lines with MONITOR marks; how loud each wedge " +
            "is stays yours. When it is off (the default) no send is " +
            "written at all.")
        // THE SWITCHES THAT DECIDE WHETHER ANYTHING HAPPENS AT ALL.
        //
        // Every one of these has, at some point, been the reason the
        // app did nothing for an hour. A log that does not say what
        // they were set to cannot answer why.
        put("HEAD", ("gates: mode=%s | between-songs needs the loudest " +
            "channel %.0f dB under this band's own level | ride needs " +
            "%.1f dB held for %.0fs and rests %.0fs | common-mode needs " +
            "%d ridable channels | processing: setup window %.0fs, then " +
            "solo or arrival only | held roles: %s")
            .format(Locale.ROOT, s.mode.name, s.gapQuietDropDb,
                s.rideDeadbandDb, s.rideDwellSec, s.rideMinGapSec,
                s.commonModeMinChannels, SETUP_WINDOW_SEC,
                s.holdRoles.joinToString("+") { it.name }))
        put("HEAD", "TAGS: HEAD setup | TAKE the faders we took over | " +
            "MARK the night's landmarks (start/stop, mutes, solos, " +
            "arrivals, errors) | DEC every decision with its reason | " +
            "FADER every fader write, from -> to | EQ COMP PARAM every " +
            "processing write | LVL the running per-channel picture | " +
            "MIX SUM the state of the mix | DGST the two-minute table | " +
            "NET the protocol | USER what you did | CARD the end-of-night " +
            "report card, one line per channel")
        put("HEAD", "READING IT: start at CARD at the bottom — it says " +
            "what the app did to each channel over the whole night, and " +
            "how much of the movement was yours. Then grep MARK for the " +
            "shape of the night, and DEC for the reasoning behind " +
            "anything that looks wrong.")
    }

    /**
     * The night's landmarks: the handful of lines you would read to
     * know what happened without reading anything else.
     */
    @JvmOverloads
    fun mark(kind: String, text: String, tSec: Double? = null) =
        put("MARK", "%-12s %s".format(Locale.ROOT, kind, text), tSec)

    fun takeover(faders: Map<Int, Float>, names: Map<Int, String>) {
        // NOT "MIXING on". This is a snapshot of the faders, and it
        // happens on the re-baseline button as well as on the mixing
        // switch — so for three nights the log said MIXING on while the
        // app wrote nothing at all, which is how a log stops being
        // evidence and starts being another thing to disbelieve.
        put("TAKE", "took a snapshot of your faders — these positions " +
            "are now the centre of what the app may do " +
            "(${faders.size} channels). Whether it is ALLOWED to write " +
            "is a separate thing: look for MIXING ON.")
        for ((ch, db) in faders.toSortedMap())
            put("TAKE", "ch%02d %-18s %+6.2f dB".format(Locale.ROOT,
                ch + 1, names[ch] ?: "", db))
    }

    fun decision(d: Decision) {
        kinds[d.kind] = (kinds[d.kind] ?: 0) + 1
        // THE SHAPE OF THE NIGHT, on one grep.
        //
        // Some decisions are landmarks — the band stopped, an
        // instrument came in, somebody soloed, you overruled it — and
        // the rest are the running commentary. Both belong in the file
        // and only the first kind belongs in a timeline, so the
        // landmarks are repeated under MARK. `grep MARK` is then the
        // night in fifty lines.
        if (d.kind in MARK_KINDS) mark(d.kind.uppercase(),
            (d.channel?.let { "ch%02d ".format(Locale.ROOT, it + 1) } ?: "") +
            d.reason, d.tSec)
        put("DEC", "%-9s %s %s%s".format(Locale.ROOT, d.kind,
            d.channel?.let { "ch%02d".format(Locale.ROOT, it + 1) } ?: "----",
            if (d.deltaDb != 0f) "%+6.2f dB  ".format(Locale.ROOT, d.deltaDb)
            else "          ", d.reason), d.tSec)
    }

    /**
     * Every fader write, as a MOVE rather than a destination.
     *
     * "-> -12.40 dB" cannot be added up, cannot be compared with what
     * the operator did, and does not say what the app was trying to
     * achieve. From, to, the step, and the reason the engine gave for
     * the correction this step belongs to.
     */
    @JvmOverloads
    fun fader(ch: Int, db: Float, name: String,
              fromDb: Float? = null, why: String? = null,
              tSec: Double? = null) =
        put("FADER", ("ch%02d %-18s %s -> %+6.2f dB %s%s")
            .format(Locale.ROOT, ch + 1, name,
                fromDb?.let { "%+6.2f".format(Locale.ROOT, it) } ?: "     ?",
                db,
                fromDb?.let { "(%+.2f) ".format(Locale.ROOT, db - it) } ?: "",
                why ?: ""), tSec)

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

    /**
     * A processing write, in the units an engineer thinks in.
     *
     * The desk stores everything as a 0..1 float, so a raw log line
     * reads `/ch/09/eq/2/g = 0.400` — which is a 3 dB cut, but only to
     * somebody willing to do the arithmetic. Every write is decoded
     * here instead, once, where the conversion already lives.
     */
    fun param(address: String, value: Float, name: String,
              why: String = "", tSec: Double? = null) {
        val ch = Regex("^/ch/(\\d\\d)/").find(address)
            ?.groupValues?.get(1)?.toIntOrNull()
        val what = when {
            address.endsWith("/preamp/hpf") -> "high-pass at %.0f Hz"
                .format(Locale.ROOT, 20f * Math.pow(20.0,
                    value.toDouble()).toFloat())
            address.endsWith("/preamp/hpon") ->
                if (value > 0.5f) "high-pass ON" else "high-pass off"
            address.endsWith("/eq/on") ->
                if (value > 0.5f) "EQ ON" else "EQ off"
            Regex("/eq/\\d/g$").containsMatchIn(address) ->
                "band %s gain %+.1f dB".format(Locale.ROOT,
                    address.substringAfter("/eq/").take(1),
                    value * 30f - 15f)
            Regex("/eq/\\d/f$").containsMatchIn(address) ->
                "band %s at %.0f Hz".format(Locale.ROOT,
                    address.substringAfter("/eq/").take(1),
                    20f * Math.pow(1000.0, value.toDouble()).toFloat())
            Regex("/eq/\\d/q$").containsMatchIn(address) ->
                "band %s Q %.1f".format(Locale.ROOT,
                    address.substringAfter("/eq/").take(1),
                    10f / Math.pow(10.0 / 0.3, value.toDouble()).toFloat())
            address.endsWith("/dyn/on") ->
                if (value > 0.5f) "compressor ON" else "compressor off"
            address.endsWith("/dyn/thr") -> "threshold %+.1f dB"
                .format(Locale.ROOT, value * 60f - 60f)
            address.endsWith("/dyn/mgain") -> "makeup %+.1f dB"
                .format(Locale.ROOT, value * 24f)
            address.endsWith("/dyn/ratio") -> {
                val r = floatArrayOf(1.1f, 1.3f, 1.5f, 2f, 2.5f, 3f, 4f,
                    5f, 7f, 10f, 20f, 100f)
                "ratio %.1f:1".format(Locale.ROOT,
                    r[(value * (r.size - 1)).toInt().coerceIn(0, r.size - 1)])
            }
            address.endsWith("/dyn/attack") -> "attack %.0f ms"
                .format(Locale.ROOT, value * 120f)
            address.endsWith("/dyn/release") -> "release %.0f ms"
                .format(Locale.ROOT,
                    5f * Math.pow(800.0, value.toDouble()).toFloat())
            Regex("/mix/\\d\\d/level$").containsMatchIn(address) -> {
                // Sends 1-6 are the WEDGES (a musician's ears); 7-10 are
                // the FX engines. They were all logged as "FX send",
                // which on the one write path that reaches the wedges is
                // exactly the wrong noun, and hid the monitor keeper's
                // work from anyone reading the file.
                val send = address.substringAfter("/mix/").take(2)
                    .toIntOrNull() ?: 0
                val kind = if (send in AUX_SEND_FIRST..AUX_SEND_LAST)
                    "wedge send bus %d".format(Locale.ROOT, send)
                    else "FX send %d".format(Locale.ROOT, send)
                "%s at %+.1f dB".format(Locale.ROOT, kind,
                    FaderLaw.floatToDb(value))
            }
            else -> "%.3f".format(Locale.ROOT, value)
        }
        put("PARAM", "ch%s %-18s %-34s %s"
            .format(Locale.ROOT,
                ch?.let { "%02d".format(Locale.ROOT, it) } ?: "??",
                name.take(18), what, why), tSec)
    }

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
        putT(t, "MIX", ("anchor %s (pyramid %+.1f, from %s) | vocal on top %s | " +
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
        if (gc.isNotEmpty()) putT(t, "MIX", "playing now: " +
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
            // PLAN AND ERROR, which in KEEP mode are the only two
            // numbers that explain a fader move: the contribution this
            // channel is meant to be making, and how far from it the
            // engine thinks it is right now. Without them a ride line
            // says "it moved" and the picture beside it cannot say why.
            val plan = st.planContrib
            val err = plan?.let { (st.slowEma ?: src) + base + st.offset - it }
            putT(t, "LVL", ("ch%02d %-18s src%7.1f fast%7.1f fader%+6.2f " +
                "off%+6.2f duck%+5.2f contrib%7.1f plan%s err%s want%s " +
                "h%+6.1f %s")
                .format(Locale.ROOT, ch + 1, names[ch] ?: st.cfg.name,
                    src, st.fastEma ?: src, base + st.offset, st.offset,
                    st.duckDb, contrib,
                    plan?.let { "%7.1f".format(Locale.ROOT, it) } ?: "      -",
                    err?.let { "%+6.2f".format(Locale.ROOT, it) } ?: "     -",
                    want?.let { "%7.1f".format(Locale.ROOT, it) } ?: "      -",
                    e.heightDb(ch), flags.trim()))
        }
        if (lastDgst < 0 || t - lastDgst >= DIGEST_SEC) {
            lastDgst = t
            digest(t, e, names, directing)
        }
        // Tone moves slowly and the RTA only visits each channel every
        // few seconds, so it gets its own, longer beat — otherwise it
        // triples the size of the file for no extra information.
        if (doctor != null && (lastTone < 0 || t - lastTone >= TONE_SEC)) {
            lastTone = t
            tone(doctor, names)
        }
    }

    /** one line per channel: what it is, where it is, and who put it there */
    private fun row(ch: Int, e: StageEngine, names: Map<Int, String>): String {
        val st = e.state[ch] ?: return ""
        val base = st.baselineDb
        val heard = e.recognised[ch]
        val res = e.spectrum.resonances(ch).firstOrNull()
        val activePct = if (st.seenSecTotal > 1f)
            (100f * st.activeSecTotal / st.seenSecTotal).toInt() else 0
        return ("ch%02d %-16s %-13s %-16s %s %s %6.1f %6.1f %2d/%2d %3d%% " +
                "%3.0f%% %s %s")
            .format(Locale.ROOT,
                ch + 1,
                (names[ch] ?: st.cfg.name).take(16),
                st.role.name.take(13),
                heard?.let { "%s(%.2f)".format(Locale.ROOT,
                    it.instrument.label.take(9), it.confidence) } ?: "-",
                base?.let { "%+6.2f".format(Locale.ROOT, it + st.offset) }
                    ?: "     -",
                st.takeoverDb?.let { tk -> base?.let {
                    "%+6.2f".format(Locale.ROOT, it + st.offset - tk) } }
                    ?: "     -",
                st.appDbMoved, st.humanDbMoved,
                st.appWrites.coerceAtMost(99), st.humanMoves.coerceAtMost(99),
                activePct,
                100f * e.spectrum.coverage(ch),
                e.spectrum.lowEdgeHz(ch)?.let {
                    "%4.0fHz".format(Locale.ROOT, it) } ?: "     -",
                res?.let { "%.0fHz+%.0f".format(Locale.ROOT, it.hz,
                    it.overTrendDb) } ?: "")
    }

    private fun rowHeader() =
        ("ch   name             role          heard              fader " +
         "  Δtake    app    you  w/y act  map  lowEdge  lump")

    /**
     * THE TABLE. Every two minutes, the whole stage on one screen.
     *
     * The running LVL picture answers "what is this channel doing right
     * now" and is the wrong shape for the question actually asked of a
     * log afterwards, which is "what has been happening to this channel
     * all night". Cumulative dB moved by the app against dB moved by
     * hand, per channel, is the single most useful number in the file:
     * it says whether the app is helping or being corrected.
     */
    fun digest(t: Double, e: StageEngine, names: Map<Int, String>,
               directing: Boolean) {
        val a = e.anchorInfo()
        val h = e.health()
        putT(t, "DGST", ("── %s | %s | %s | lead %s | anchor %s | vocal on " +
            "top %s | in place %d%% | you out-mixed it %d times")
            .format(Locale.ROOT,
                if (directing) "MIXING" else "watching (shadow)",
                if (e.betweenSongs) "BETWEEN SONGS" else "band playing",
                if (e.stageMuted) "STAGE MUTED BY YOU" else "not muted",
                e.leadVocal?.let { "ch%02d".format(Locale.ROOT, it + 1) }
                    ?: "none",
                a.contributionDb?.let { "%.1f dB".format(Locale.ROOT, it) }
                    ?: "none yet",
                pct(h.vocalOnTopPct), h.inPlacePct, h.overrides))
        putT(t, "DGST", rowHeader())
        for (ch in e.state.keys.sorted()) putT(t, "DGST", row(ch, e, names))
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
        putT(t, "SUM", ("%d ch playing | loudest %s | lead %s | vocal on top " +
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

    /** every decision kind seen tonight, counted — see footer */
    private val kinds = HashMap<String, Int>()

    /**
     * The report card, mid-night.
     *
     * It used to be written only by [footer], on the way out — and the
     * app on the tablet is never shut down, so on a real night it was
     * never written at all. The one block worth reading first was the
     * one block the file did not have.
     */
    fun card(tSec: Double, e: StageEngine, names: Map<Int, String>) {
        if (lastCard >= 0 && tSec - lastCard < CARD_EVERY_SEC) return
        lastCard = tSec
        put("CARD", "── the night so far, one line per channel ──", tSec)
        put("CARD", rowHeader(), tSec)
        for (ch in e.state.keys.sorted()) put("CARD", row(ch, e, names), tSec)
        put("CARD", travelLine(e), tSec)
    }

    private fun travelLine(e: StageEngine): String {
        var app = 0f; var you = 0f
        for (st in e.state.values) { app += st.appDbMoved; you += st.humanDbMoved }
        return ("TOTAL fader travel: this app %.0f dB, you %.0f dB by hand. %s")
            .format(Locale.ROOT, app, you,
                if (you > app) "You out-moved it — read the DEC lines " +
                    "either side of your moves."
                else "It did most of the moving.")
    }

    fun footer(e: StageEngine, names: Map<Int, String> = emptyMap()) {
        val h = e.health()
        put("SUM", "END OF NIGHT — vocal on top ${pct(h.vocalOnTopPct)}, " +
            "channels in place ${h.inPlacePct}%, you out-mixed it " +
            "${h.overrides} times over ${h.ticks} ticks")

        // THE REPORT CARD.
        //
        // One line per channel for the whole night, which is the thing
        // to read first and the thing that was missing. Every question
        // worth asking of a night — did it get this channel's identity
        // right, did it move it, did I have to correct it, did it ever
        // hear enough of it to treat it — is answered on one screen.
        put("CARD", "── the whole night, one line per channel ──")
        put("CARD", rowHeader())
        for (ch in e.state.keys.sorted()) put("CARD", row(ch, e, names))
        put("CARD", travelLine(e))
        for ((ch, st) in e.state.toSortedMap()) {
            val bits = buildString {
                if (st.arrivals > 0) append("arrived ${st.arrivals}x ")
                if (st.placements > 0) append("placed ${st.placements}x ")
                if (st.heldDowns > 0) append("HELD DOWN ${st.heldDowns}x ")
                if (st.placeGaveUp) append("left where you had it ")
                if (st.frozen) append("locked ")
                if (st.isStatic) append("judged ROOM TONE ")
                if (st.deskMuted) append("muted by you at the end ")
                if (st.roleByHand) append("role set by you ")
                else if (st.roleIdentified) append("role decided by the app ")
            }
            if (bits.isNotBlank()) put("CARD",
                "ch%02d %-16s %s".format(Locale.ROOT, ch + 1,
                    (names[ch] ?: st.cfg.name).take(16), bits.trim()))
        }
        // AND EVERY KIND OF DECISION, COUNTED.
        //
        // 281,873 arrivals in one night were invisible until somebody
        // grepped 48 MB for them. A count of every kind, at the end, in
        // order of how often it happened, makes that kind of runaway
        // the first thing you see instead of the last.
        if (kinds.isNotEmpty()) put("SUM", "decisions tonight: " +
            kinds.entries.sortedByDescending { it.value }
                .joinToString("  ") { "${it.key}=${it.value}" })
        if (dropped > 0) put("SUM",
            "$dropped lines of the running picture were dropped — the " +
            "log passed its $SOFT_LINES-line soft cap and gave the rest " +
            "of the night to decisions, fader writes and errors")
        flush()
    }

    companion object {
        /** ~30 MB of text at the widest lines; a long night is ~150k */
        private const val MAX_LINES = 400_000
        /** past this, only the tags below keep their place */
        private const val SOFT_LINES = 300_000
        /** the running picture: useful, and the first thing to go */
        private val BULK_TAGS = setOf("LVL", "TONE")
        /** never dropped, even past the hard cap — the record of what happened */
        private val KEEP_ALWAYS = setOf("DEC", "FADER", "MARK", "USER", "NET", "CARD", "HEAD")
        /** how often the per-channel tone picture is written */
        private const val TONE_SEC = 30.0
        /** and how often the whole stage is tabulated */
        private const val DIGEST_SEC = 120.0
        /** how often an empty room says so */
        const val IDLE_BEAT_SEC = 300.0
        /** and how often the report card is written mid-night */
        const val CARD_EVERY_SEC = 900.0
        /** decisions that are landmarks rather than commentary */
        private val MARK_KINDS = setOf(
            "gap", "music", "stage-mute", "arrive", "feature", "soloride",
            "override", "rebalance", "keep", "feedback", "held-down",
            "ident", "leave", "takeover", "lead")
    }
}
