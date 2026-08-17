package com.stagemix.replay

import com.stagemix.engine.BalanceMode
import com.stagemix.engine.ChannelConfig
import com.stagemix.engine.EngineSettings
import com.stagemix.engine.FaderLaw
import com.stagemix.engine.Meters
import com.stagemix.engine.RESEARCH_PYRAMID
import com.stagemix.engine.Role
import com.stagemix.engine.ShowLog
import com.stagemix.engine.StageEngine
import com.stagemix.engine.ToneDoctor
import com.stagemix.engine.defaultRigProfile
import com.stagemix.engine.inferRole
import java.io.File
import java.util.Locale
import kotlin.math.abs
import kotlin.math.pow

/**
 * Replay a recorded night through the real StageMix engine.
 *
 * A session recorded off the M18's USB is the same 16 sources the
 * console meters, so it can be fed to the engine exactly as a live
 * stage would be: per-channel level 20x a second, RTA round-robined
 * across the channels, engine ticks at 1 Hz. Nothing is simulated
 * except the passage of time — the engine, the Channel Doctor and the
 * show log are the ones that ship in the app.
 *
 * It answers the question the tests cannot: what would this thing have
 * done to MY band, in MY room, on a night that actually happened?
 *
 * Usage:
 *   ./gradlew :replay:run --args="/path/to/stems"
 *   ./gradlew :replay:run --args="/path/to/stems --render --out ./out"
 *
 * Inputs it accepts:
 *   · a folder of mono WAVs, one per channel — Studio One's
 *     "Export Stems". Channel order comes from a leading number in the
 *     file name ("03 Overheads.wav"), or failing that from alphabetical
 *     order. Names also set the roles, the same way the console's
 *     channel names do live.
 *   · a single interleaved multichannel WAV (up to 16 channels).
 *
 * Outputs, in --out (default: alongside the input):
 *   · logs/replay_<take>.log — the full show log, identical in format
 *     to a live night
 *   · <take>_autopilot.wav — the mix the engine would have made
 *   · <take>_flat.wav — the same stems at the takeover faders, as an
 *     A/B reference
 *   (both only with --render)
 */

private const val METER_HZ = 20
private const val TICK_SEC = 1.0

fun main(args: Array<String>) {
    // A bad recording must fail with one readable line, not a stack
    // trace. The offline tool is fed whatever a DAW or the capture
    // format exported — a non-WAV file, a truncated header, an
    // unsupported bit depth, a corrupt .smcap — and every one of those
    // used to come out of javax.sound as a raw exception dump. Turn the
    // known failures into a sentence and exit non-zero.
    try {
        runReplay(args)
    } catch (e: javax.sound.sampled.UnsupportedAudioFileException) {
        System.err.println("not a WAV this tool can read " +
            "(export 16/24/32-bit PCM or 32-bit float): ${e.message ?: ""}")
        kotlin.system.exitProcess(2)
    } catch (e: IllegalArgumentException) {
        // WavReader's bit-depth guard, and bad CLI arguments
        System.err.println(e.message ?: "bad input")
        kotlin.system.exitProcess(2)
    } catch (e: IllegalStateException) {
        // a corrupt .smcap discovered mid-stream
        System.err.println(e.message ?: "corrupt recording")
        kotlin.system.exitProcess(2)
    } catch (e: java.io.IOException) {
        // a non-gzip .smcap surfaces here as a ZipException
        System.err.println("could not read the recording: ${e.message ?: ""}")
        kotlin.system.exitProcess(2)
    }
}

private fun runReplay(args: Array<String>) {
    if (args.isEmpty()) { usage(); return }
    val opts = Opts.parse(args)
    val input = File(opts.path)
    if (!input.exists()) { System.err.println("not found: $input"); return }

    val take = if (input.isDirectory) input.name
               else input.name.substringBeforeLast('.')
    val outDir = File(opts.out ?: (if (input.isDirectory) input.path
                                   else input.parent)).apply { mkdirs() }

    if (input.isFile && input.name.lowercase().endsWith(".smcap")) {
        replayCapture(input, opts, outDir, take)
        return
    }

    val src = openSources(input, opts) ?: return
    println("replaying $take: ${src.count} channels at ${src.sampleRate} Hz" +
        (if (src.frames > 0) ", %.1f minutes"
            .format(Locale.ROOT, src.frames / src.sampleRate / 60.0) else ""))
    for ((i, n) in src.names.withIndex())
        println("  ch%02d  %-24s %s".format(Locale.ROOT, i + 1, n,
            src.profile[i].role.name))

    val engine = StageEngine(src.profile,
        EngineSettings(mode = opts.mode, operatorPolicy = opts.policy), RESEARCH_PYRAMID)
    val doctor = ToneDoctor(src.profile.map { it.index },
        src.profile.associate { it.index to it.role })
    val log = ShowLog(outDir, snapshotSec = opts.snapshotSec,
        name = "replay_$take.log")
    engine.onDecision = { d -> log.decision(d) }
    val names = src.profile.associate { it.index to it.name }
    log.head("(replay of a recorded take — no console)", engine, names, 0, "")
    log.note("NET", "mode ${opts.mode} — " +
        (if (opts.mode == BalanceMode.LEAD)
            "deriving a balance from scratch, which is what a folder of " +
            "stems can be asked; pass --keep for the other question"
         else "defending the balance the starting faders describe") + "\n")
    log.note("NET", "replaying ${input.name}: ${src.count} channels, " +
        "${src.sampleRate} Hz, meters at $METER_HZ Hz, ticks at " +
        "%.0f s — the engine and doctor are the shipping ones"
            .format(Locale.ROOT, TICK_SEC))

    val r = Replay(src, engine, doctor, log, opts, outDir, take)
    r.run()
    log.footer(engine, names)
    log.close()

    println()
    println(r.report())
    println("show log: ${log.file}")
    if (opts.render) {
        println("autopilot mix: ${r.autopilotFile}")
        println("flat mix:      ${r.flatFile}")
    }
}

private fun usage() = println("""
    StageMix replay — run the real engine over a recorded night.

      :replay:run --args="<folder of mono stems | multichannel wav> [options]"

    options
      --render            also write the mix the autopilot would have made,
                          plus a flat reference mix at the takeover faders
      --out <dir>         where to write (default: next to the input)
      --fader <dB>        takeover fader position for every channel
                          (default -10; this is where the engine starts)
      --start <sec>       skip this far into the take
      --length <sec>      replay only this much
      --snapshot <sec>    how often the log writes a level picture (default 5)
      --shadow            decide and log, but do not apply the moves to the
                          rendered mix (what the app's shadow mode does)
      --lead              derive a balance from scratch. The default here,
                          and the only question a folder of stems can
                          answer: there is no desk and no human mix in a
                          recording, only the flat --fader position.
      --keep              defend the balance the starting faders describe,
                          as the tablet does on a real desk — for asking
                          what KEEP would have done to a mix that existed.
      --capture <file>    also write a METER TAPE: the sixteen levels and
                          the spectra, and nothing else. About a megabyte
                          for a whole night, against tens of gigabytes of
                          audio, and it replays to the same decisions —
                          so the recording never has to leave this machine

    a .smcap capture can be replayed anywhere, exactly like the audio:
      :replay:run --args="night.smcap"
""".trimIndent())

// ---------------------------------------------------------------------
private class Opts(
    val path: String,
    val render: Boolean,
    val out: String?,
    val faderDb: Float,
    val startSec: Double,
    val lengthSec: Double,
    val snapshotSec: Double,
    val shadow: Boolean,
    /** write a meter tape instead of / as well as replaying */
    val capture: String?,
    /**
     * Which job the engine is doing.
     *
     * LEAD by default, and that is a deliberate difference from the
     * tablet, which ships as KEEP. KEEP defends the balance already on
     * the desk — but a folder of stems has no desk and no balance on
     * it, only whatever flat starting fader `--fader` puts there, so
     * KEEP would faithfully preserve a mix nobody made and the tool
     * would render silence-shaped nothing. What a replay is FOR is
     * "what would the app have done with this night from scratch", and
     * that is LEAD. Pass --keep to ask the other question: what would
     * KEEP have done to a mix that already existed.
     */
    val mode: BalanceMode,
    /**
     * The operator's volume policy — the locks, the pinned instruments, the
     * bass deadband. ON by default so a replay matches the shipping app and
     * the bench; --no-policy asks the bare-engine question instead (what the
     * pyramid alone does), which is what the mode-comparison test wants.
     */
    val policy: Boolean,
) {
    companion object {
        fun parse(a: Array<String>): Opts {
            var path = ""; var render = false; var out: String? = null
            var fader = -10f; var start = 0.0; var len = 0.0
            var snap = 5.0; var shadow = false; var cap: String? = null
            var mode = BalanceMode.LEAD; var policy = true
            var i = 0
            // A flag with no value used to walk off the end of the array
            // and throw an ArrayIndexOutOfBounds; a non-number after
            // --fader threw a raw NumberFormatException. Both now fail
            // with a sentence naming the flag.
            fun value(flag: String): String {
                if (i + 1 >= a.size)
                    throw IllegalArgumentException("$flag needs a value")
                return a[++i]
            }
            fun num(flag: String): Double = value(flag).let {
                it.toDoubleOrNull()
                    ?: throw IllegalArgumentException("$flag needs a number, got '$it'")
            }
            while (i < a.size) {
                when (a[i]) {
                    "--render" -> render = true
                    "--shadow" -> shadow = true
                    "--out" -> out = value("--out")
                    "--fader" -> fader = num("--fader").toFloat()
                    "--start" -> start = num("--start")
                    "--length" -> len = num("--length")
                    "--snapshot" -> snap = num("--snapshot")
                    "--capture" -> cap = value("--capture")
                    "--keep" -> mode = BalanceMode.KEEP
                    "--lead" -> mode = BalanceMode.LEAD
                    "--no-policy" -> policy = false
                    "--policy" -> policy = true
                    else -> if (path.isEmpty()) path = a[i]
                }
                i++
            }
            return Opts(path, render, out, fader, start, len, snap, shadow,
                cap, mode, policy)
        }
    }
}

/** the stems, however they were exported */
private class Sources(
    val readers: List<WavReader>,
    /** for a multichannel file, which channel of it each strip is */
    val channelOf: List<Int>,
    val names: List<String>,
    val profile: List<ChannelConfig>,
    val sampleRate: Int,
    val frames: Double,
) {
    val count get() = names.size
}

private fun openSources(input: File, opts: Opts): Sources? {
    val rig = defaultRigProfile()
    if (input.isDirectory) {
        val wavs = input.listFiles { f: File ->
            f.isFile && f.name.lowercase().endsWith(".wav") }
            ?.sortedBy { it.name } ?: emptyList()
        if (wavs.isEmpty()) {
            System.err.println("no .wav files in $input"); return null
        }
        // a leading number in the file name is the channel number
        val byNum = wavs.mapNotNull { f ->
            Regex("^\\s*(\\d{1,2})\\b").find(f.name)?.groupValues?.get(1)
                ?.toIntOrNull()?.let { it to f }
        }
        val ordered = if (byNum.size == wavs.size)
            byNum.sortedBy { it.first }.map { it.second } else wavs
        val use = ordered.take(16)
        val readers = use.map { WavReader(it) }
        if (readers.any { it.channels != 1 })
            println("note: some stems are not mono; only their left " +
                "channel is used")
        val names = use.map {
            it.name.substringBeforeLast('.')
                .replace(Regex("^\\s*\\d{1,2}[ _.-]*"), "").trim()
                .ifBlank { it.name } }
        return Sources(readers, use.indices.map { 0 }, names,
            profileFor(names, rig), readers[0].sampleRate,
            frames = 0.0)
    }
    val rd = WavReader(input)
    val n = minOf(rd.channels, 16)
    val names = (0 until n).map { rig.getOrNull(it)?.name ?: "ch${it + 1}" }
    return Sources(List(n) { rd }, (0 until n).toList(), names,
        profileFor(names, rig), rd.sampleRate, 0.0)
}

/**
 * Roles come from the track names, exactly as they do live from the
 * console's channel names — with the built-in rig profile as the
 * fallback when a name says nothing useful.
 */
private fun profileFor(names: List<String>,
                       rig: List<ChannelConfig>): List<ChannelConfig> =
    names.mapIndexed { i, n ->
        val inferred = inferRole(n)
        val fallback = rig.getOrNull(i)
        ChannelConfig(
            index = i,
            name = n,
            role = if (inferred != Role.INSTRUMENT) inferred
                   else fallback?.role ?: Role.INSTRUMENT,
            pairWith = fallback?.pairWith?.takeIf { it < names.size },
        )
    }

// ---------------------------------------------------------------------
private class Replay(
    val src: Sources,
    val engine: StageEngine,
    val doctor: ToneDoctor,
    val log: ShowLog,
    val opts: Opts,
    val outDir: File,
    val take: String,
) {
    val autopilotFile = File(outDir, "${take}_autopilot.wav")
    val flatFile = File(outDir, "${take}_flat.wav")

    private val n = src.count
    private val sr = src.sampleRate
    private val blockFrames = sr / METER_HZ            // one meter frame
    private val buf = Array(n) { FloatArray(blockFrames) }
    private val multi = Array(16) { FloatArray(blockFrames) }
    private val meters = List(n) { LevelMeter(sr) }
    private val rta = List(n) { Rta(sr) }
    private val levels = FloatArray(16) { -128f }

    // rendering
    private val gain = FloatArray(n) { db2lin(opts.faderDb) }
    private val flatGain = db2lin(opts.faderDb)
    private val outL = FloatArray(blockFrames)
    private val outR = FloatArray(blockFrames)
    private val flatL = FloatArray(blockFrames)
    private val flatR = FloatArray(blockFrames)
    private val statsAuto = MixStats()
    private val statsFlat = MixStats()

    private var cap: Capture.Writer? = null
    private var t = 0.0
    private var nextTick = 0.0
    private var rtaFocus = 0
    private var rtaFocusT = 0.0
    var faderWrites = 0; private set
    var eqWrites = 0; private set
    var compWrites = 0; private set

    fun run() {
        cap = opts.capture?.let {
            Capture.Writer(File(it), sr, METER_HZ,
                (0 until n).map { c -> src.profile[c].name })
        }
        val wa = if (opts.render) WavWriter(autopilotFile, sr) else null
        val wf = if (opts.render) WavWriter(flatFile, sr) else null
        val skip = opts.startSec
        val stop = if (opts.lengthSec > 0) skip + opts.lengthSec
                   else Double.MAX_VALUE
        var tookOver = false

        while (true) {
            val got = readBlock()
            if (got <= 0) break
            t += got.toDouble() / sr
            if (t < skip) continue
            if (t > stop) break

            for (c in 0 until n) levels[c] = meters[c].push(buf[c], got)
            engine.onMeters(levels, t)
            cap?.level(t, levels)

            // the app takes over once it has heard the room for a moment
            if (!tookOver && t >= skip + 2.0) {
                tookOver = true
                val faders = (0 until n).associateWith { opts.faderDb }
                engine.takeover(faders, t)
                log.takeover(faders, src.profile.associate { it.index to it.name })
                log.user("MIXING on (replay takes over at %.0f s)"
                    .format(Locale.ROOT, t))
            }

            // RTA round-robin, the same ~3 s dwell the app uses
            if (t - rtaFocusT > 3.0) {
                val active = engine.activeChannels().filter { it < n }.sorted()
                if (active.isNotEmpty())
                    rtaFocus = active[(active.indexOf(rtaFocus) + 1)
                        .mod(active.size)]
                rtaFocusT = t
            }
            if (rtaFocus < n) rta[rtaFocus].push(buf[rtaFocus], got)?.let {
                doctor.onRta(rtaFocus, it, t)
                cap?.rta(t, rtaFocus, it)
            }

            if (t >= nextTick) {
                nextTick = t + TICK_SEC
                for (w in engine.tick(t)) {
                    faderWrites++
                    if (w.channel < n) gain[w.channel] = db2lin(w.levelDb)
                    log.fader(w.channel, w.levelDb,
                        src.profile.getOrNull(w.channel)?.name ?: "",
                        null,
                        engine.decisions.firstOrNull { it.channel == w.channel }
                            ?.let { "— ${it.kind}: ${it.reason}" }, t)
                }
                for (w in doctor.tick(engine.activeChannels(),
                        upAllowed = engine.boostsAllowed(t),
                        frozenAll = engine.frozenAll)) {
                    val m = Regex("^/ch/(\\d\\d)/(eq/(\\d)/g|dyn/thr)$")
                        .find(w.address) ?: continue
                    val ch = m.groupValues[1].toInt() - 1
                    val st = doctor.state[ch]
                    if (m.groupValues[3].isNotEmpty()) {
                        eqWrites++
                        val b = m.groupValues[3].toInt() - 1
                        val live = st?.liveBands; val ref = st?.refBands
                        log.eq(ch, b, w.value * 30f - 15f,
                            if (live != null && ref != null) live[b] - ref[b]
                            else 0f, src.profile.getOrNull(ch)?.name ?: "")
                    } else {
                        compWrites++
                        log.comp(ch, w.value * 60f - 60f, st?.grEma, st?.refGr,
                            src.profile.getOrNull(ch)?.name ?: "")
                    }
                }
                // the doctor's soundcheck anchor: taken once, from the
                // tone it has heard by the time the engine starts leading
                if (!doctor.snapshotTaken && t > skip + engine.settings.learnSec)
                    for (ch in 0 until n)
                        doctor.snapshotChannel(ch, FloatArray(4), -20f)
                log.snapshot(t, engine, doctor,
                    src.profile.associate { it.index to it.name }, !opts.shadow)
                log.summary(t, engine,
                    src.profile.associate { it.index to it.name })
            }

            if (opts.render) render(got, wa!!, wf!!)
        }
        wa?.close(); wf?.close()
        cap?.let {
            it.close()
            println("meter tape: ${opts.capture} " +
                "(${it.levelFrames} level frames, ${it.rtaFrames} spectra, " +
                "%.1f MB)".format(Locale.ROOT,
                    File(opts.capture!!).length() / 1048576.0))
        }
        src.readers.distinct().forEach { it.close() }
    }

    /** one meter block from every stem, whatever shape the input has */
    private fun readBlock(): Int {
        var got = 0
        if (src.readers.distinct().size == 1 && src.channelOf.distinct().size > 1) {
            // one interleaved multichannel file
            got = src.readers[0].read(multi, blockFrames)
            for (c in 0 until n)
                System.arraycopy(multi[src.channelOf[c]], 0, buf[c], 0, got)
        } else {
            for (c in 0 until n) {
                val g = src.readers[c].read(arrayOf(buf[c]).let { one ->
                    if (src.readers[c].channels == 1) one
                    else Array(src.readers[c].channels) {
                        if (it == 0) buf[c] else FloatArray(blockFrames) }
                }, blockFrames)
                if (c == 0) got = g else got = minOf(got, g)
            }
        }
        return got
    }

    private fun render(count: Int, wa: WavWriter, wf: WavWriter) {
        java.util.Arrays.fill(outL, 0, count, 0f)
        java.util.Arrays.fill(outR, 0, count, 0f)
        java.util.Arrays.fill(flatL, 0, count, 0f)
        java.util.Arrays.fill(flatR, 0, count, 0f)
        for (c in 0 until n) {
            // stereo pairs keep their sides; everything else sits centre
            val mate = src.profile[c].pairWith
            val left = mate == null || c < mate
            val g = if (opts.shadow) flatGain else gain[c]
            val x = buf[c]
            for (i in 0 until count) {
                val v = x[i] * g
                if (mate == null) { outL[i] += v; outR[i] += v }
                else if (left) outL[i] += v * 2f else outR[i] += v * 2f
                val f = x[i] * flatGain
                if (mate == null) { flatL[i] += f; flatR[i] += f }
                else if (left) flatL[i] += f * 2f else flatR[i] += f * 2f
            }
        }
        statsAuto.push(outL, outR, count)
        statsFlat.push(flatL, flatR, count)
        wa.write(outL, outR, count)
        wf.write(flatL, flatR, count)
    }

    fun report(): String {
        val h = engine.health()
        val sb = StringBuilder()
        sb.appendLine("=== replay of $take ===")
        sb.appendLine("  %.1f minutes replayed".format(Locale.ROOT, t / 60.0))
        sb.appendLine("  $faderWrites fader moves, $eqWrites EQ moves, " +
            "$compWrites compressor moves")
        sb.appendLine("  mix health: vocal on top " +
            (if (h.vocalOnTopPct < 0) "n/a" else "${h.vocalOnTopPct}%") +
            ", channels in place ${h.inPlacePct}%")
        sb.appendLine("  where it left every fader, against where it started:")
        for (c in 0 until n) {
            val off = engine.offsetDb(c)
            sb.appendLine("    ch%02d %-22s %+6.2f dB %s".format(Locale.ROOT,
                c + 1, src.profile[c].name, off,
                if (abs(off) < 0.05f) "" else bar(off)))
        }
        if (opts.render) {
            sb.appendLine("  rendered: autopilot %.1f dB rms / %.1f dB peak, "
                .format(Locale.ROOT, statsAuto.rmsDb(), statsAuto.peakDb()) +
                "flat %.1f dB rms / %.1f dB peak"
                    .format(Locale.ROOT, statsFlat.rmsDb(), statsFlat.peakDb()))
        }
        return sb.toString()
    }

    private fun bar(db: Float): String {
        val k = (abs(db) * 2).toInt().coerceAtMost(24)
        return if (db > 0) "+".repeat(k) else "-".repeat(k)
    }

    private fun db2lin(db: Float) = 10.0.pow(db / 20.0).toFloat()
}

// ---------------------------------------------------------------------
/**
 * Replay a meter tape. This is the same engine, the same doctor and the
 * same show log as a live night or an audio replay — the only thing
 * missing is the audio itself, which the engine never sees anyway.
 */
private fun replayCapture(file: File, opts: Opts, outDir: File, take: String) {
    var engine: StageEngine? = null
    var doctor: ToneDoctor? = null
    var log: ShowLog? = null
    var names: Map<Int, String> = emptyMap()
    var profile: List<ChannelConfig> = emptyList()
    var nextTick = 0.0
    var tookOver = false
    var faderWrites = 0; var eqWrites = 0; var compWrites = 0
    var last = 0.0

    Capture.read(file,
        onHeader = { tape ->
            profile = profileFor(tape.names, defaultRigProfile())
            names = profile.associate { it.index to it.name }
            val e = StageEngine(profile, EngineSettings(mode = opts.mode, operatorPolicy = opts.policy), RESEARCH_PYRAMID)
            val d = ToneDoctor(profile.map { it.index },
                profile.associate { it.index to it.role })
            val l = ShowLog(outDir, snapshotSec = opts.snapshotSec,
                name = "replay_$take.log")
            e.onDecision = { dec -> l.decision(dec) }
            l.head("(replay of a meter tape — no console, no audio)",
                e, names, 0, "")
            l.note("NET", "replaying ${file.name}: ${tape.names.size} " +
                "channels captured at ${tape.meterHz} Hz from a " +
                "${tape.sampleRate} Hz recording")
            engine = e; doctor = d; log = l
            println("replaying ${file.name}: ${tape.names.size} channels")
            for ((i, nm) in tape.names.withIndex())
                println("  ch%02d  %-24s %s".format(Locale.ROOT, i + 1, nm,
                    profile[i].role.name))
        },
        onLevel = { t, db ->
            val e = engine!!; val d = doctor!!; val l = log!!
            last = t
            e.onMeters(db, t)
            if (!tookOver && t >= 2.0) {
                tookOver = true
                val faders = profile.indices.associateWith { opts.faderDb }
                e.takeover(faders, t)
                l.takeover(faders, names)
                l.user("MIXING on (replay takes over at %.0f s)"
                    .format(Locale.ROOT, t))
            }
            if (t >= nextTick) {
                nextTick = t + TICK_SEC
                for (w in e.tick(t)) {
                    faderWrites++
                    l.fader(w.channel, w.levelDb, names[w.channel] ?: "",
                        null,
                        e.decisions.firstOrNull { it.channel == w.channel }
                            ?.let { "— ${it.kind}: ${it.reason}" }, t)
                }
                for (w in d.tick(e.activeChannels(),
                        upAllowed = e.boostsAllowed(t),
                        frozenAll = e.frozenAll)) {
                    val m = Regex("^/ch/(\\d\\d)/(eq/(\\d)/g|dyn/thr)$")
                        .find(w.address) ?: continue
                    val ch = m.groupValues[1].toInt() - 1
                    val st = d.state[ch]
                    if (m.groupValues[3].isNotEmpty()) {
                        eqWrites++
                        val b = m.groupValues[3].toInt() - 1
                        val live = st?.liveBands; val ref = st?.refBands
                        l.eq(ch, b, w.value * 30f - 15f,
                            if (live != null && ref != null) live[b] - ref[b]
                            else 0f, names[ch] ?: "")
                    } else {
                        compWrites++
                        l.comp(ch, w.value * 60f - 60f, st?.grEma, st?.refGr,
                            names[ch] ?: "")
                    }
                }
                if (!d.snapshotTaken && t > 2.0 + e.settings.learnSec)
                    for (ch in profile.indices)
                        d.snapshotChannel(ch, FloatArray(4), -20f)
                l.snapshot(t, e, d, names, !opts.shadow)
                l.summary(t, e, names)
            }
        },
        onRta = { t, ch, bins -> doctor?.onRta(ch, bins, t) })

    val e = engine ?: return
    log?.footer(e, names); log?.close()
    println()
    println("=== replay of $take (meter tape) ===")
    println("  %.1f minutes replayed".format(Locale.ROOT, last / 60.0))
    println("  $faderWrites fader moves, $eqWrites EQ moves, " +
        "$compWrites compressor moves")
    val h = e.health()
    println("  mix health: vocal on top " +
        (if (h.vocalOnTopPct < 0) "n/a" else "${h.vocalOnTopPct}%") +
        ", channels in place ${h.inPlacePct}%")
    println("  where it left every fader:")
    for (c in profile.indices)
        println("    ch%02d %-22s %+6.2f dB".format(Locale.ROOT, c + 1,
            profile[c].name, e.offsetDb(c)))
    println("show log: ${log?.file}")
}
