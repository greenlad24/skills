package com.stagemix.vm18

import com.stagemix.engine.Decision
import com.stagemix.engine.FaderLaw
import com.stagemix.engine.FeedbackWatchdog
import com.stagemix.engine.Meters
import com.stagemix.engine.OscMessage
import com.stagemix.engine.Role
import com.stagemix.engine.ShowLog
import com.stagemix.engine.StageEngine
import com.stagemix.engine.ToneDoctor
import com.stagemix.engine.inferRole
import com.stagemix.engine.isSafeAddress
import com.stagemix.engine.osc
import java.io.File
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.InetSocketAddress
import java.util.Locale
import java.util.concurrent.ConcurrentHashMap
import kotlin.math.abs

/**
 * The autopilot, on the desk side of the wire, for testing without the
 * tablet.
 *
 * It runs the SAME `StageEngine`, `ToneDoctor`, `FeedbackWatchdog` and
 * `ShowLog` the Android app runs, and talks to the console over real
 * UDP: subscribe, read the faders, take over, tick once a second, write.
 * So the whole path is exercised — decode a meter blob, decide, encode a
 * fader, have the console quantize it and hand it back.
 *
 * One honest caveat. The transport loop here is a PORT of the app's
 * `MixerService`, not the same code: the Android service owns a
 * foreground notification, wake locks and Compose state, none of which
 * exist on a desktop. The engine, the doctor, the watchdog and the log —
 * everything that decides anything — are literally the shipping classes.
 * What this cannot catch is a bug that lives only in the Android
 * service. For that, the tablet still has to be in the room.
 */
class DeskClient(
    private val host: String,
    private val port: Int,
    private val logDir: File,
) {
    val engine = StageEngine(emptyList<com.stagemix.engine.ChannelConfig>()
        .ifEmpty { com.stagemix.engine.defaultRigProfile() },
        com.stagemix.engine.EngineSettings(operatorPolicy = true))
    var doctor: ToneDoctor? = null; private set
    private val watchdog = FeedbackWatchdog()
    /**
     * The ring-out, on the bench too — so the Mac can actually notch the
     * emulator's modelled feedback, not just detect it. Same engine class
     * the tablet runs.
     */
    private val ringOut = com.stagemix.engine.RingOut()
    private var lastRingAction = ""
    /** the feedback carried in from earlier bench runs (ch, Hz, rings) */
    private var carriedFeedback = emptyList<Triple<Int, Float, Int>>()
    /** pre-ring the known feedback at takeover — ON by default on the bench */
    var preRing = true
    /**
     * The monitors, on the bench too — the same MonitorMap/MonitorBalance
     * the tablet runs, so the Mac can test the wedge balancing, the
     * in-ears/wedge choice and the drummer's floor mix, not just the mains.
     */
    private val monitors = com.stagemix.engine.MonitorMap()
    private val monBal = com.stagemix.engine.MonitorBalance(monitors)
    /** keep the wedges balanced — ON by default on the bench so it is visible */
    var keepMonitors = true
    /** the operator's per-bus in-ears/wedge choice */
    private val monitorInEars = HashMap<Int, Boolean>()
    /** bus names read from the console, 0-indexed like `names` */
    private val busNames = HashMap<Int, String>()
    private var sendsReadT = -1e9
    private var lastMonMatrix = -1e9
    private var show: ShowLog? = null
    /** the last level written per channel, so the log can say from -> to */
    private val lastFader = HashMap<Int, Float>()

    private val sock = DatagramSocket().apply { soTimeout = 200 }
    private val addr = InetSocketAddress(InetAddress.getByName(host), port)
    private val pending = ConcurrentHashMap<String, Float>()
    private val lastSent = ConcurrentHashMap<Int, Float>()
    /** channel-processing values we wrote, so an echo is not a human */
    private val lastParam = ConcurrentHashMap<String, Float>()
    @Volatile private var collecting = false
    @Volatile private var running = false
    /** the loop thread, so stop() can wait for it before tearing down */
    private var worker: Thread? = null

    var directing = false
        set(v) {
            field = v
            show?.user(if (v) "MIXING on" else "MIXING off (shadow)")
            if (v) takeover()
        }
    var doctorOn = true
    val names = HashMap<Int, String>()
    var log: ((String) -> Unit)? = null
    var onDecision: ((Decision) -> Unit)? = null

    private var t0 = System.nanoTime()
    private fun now() = (System.nanoTime() - t0) / 1e9

    /**
     * The engine's clock. Anything that hands the engine a timestamp —
     * a freeze, a feedback tap, a hold check — has to use THIS, not the
     * wall clock: the two differ by however long the JVM has been up,
     * which would put every hold decades in the past.
     */
    fun clock(): Double = now()

    private var rtaFocus = -1
    private var rtaFocusT = 0.0
    private var lastKeep = -99.0
    private var lastTick = -99.0
    private var lastRx = 0.0
    private var lastVeto = false

    fun start() {
        running = true
        show = ShowLog(logDir, name = "bench_" +
            java.text.SimpleDateFormat("yyyy-MM-dd_HH-mm", Locale.ROOT)
                .format(java.util.Date()) + ".log")
        engine.onDecision = { d ->
            show?.decision(d)
            onDecision?.invoke(d)
            log?.invoke("%-8s %s %s".format(Locale.ROOT, d.kind,
                d.channel?.let { "ch%02d".format(Locale.ROOT, it + 1) } ?: "  --",
                d.reason))
        }
        worker = Thread({ loop() }, "desk-client").apply {
            isDaemon = true; start() }
    }

    fun stop() {
        // Wait for the loop thread to actually leave its body before
        // closing the socket and the log out from under it. Without the
        // join, stop() raced the worker: it could close `show` while the
        // loop was still writing a snapshot to it, or close `sock` mid
        // send/receive. soTimeout is 200ms, so one tick is the longest
        // the join can block; the 1s cap is just a backstop.
        running = false
        worker?.join(1000)
        worker = null
        show?.let { s -> s.footer(engine, names); s.close() }
        sock.close()
    }

    fun logFile(): File? = show?.file

    /**
     * The balance this engineer keeps arriving at, kept beside the logs
     * so a bench session tomorrow starts where tonight left off. Losing
     * it on a restart would throw away the only real knowledge the app
     * has about this band.
     */
    private fun learnedFile() = File(logDir, "learned-balance.txt")

    fun saveLearned() = runCatching {
        learnedFile().writeText(
            engine.learned.snapshot().entries.joinToString("\n") {
                "${it.key} ${it.value.first} ${it.value.second}"
            })
    }

    fun loadLearned() = runCatching {
        val f = learnedFile()
        if (!f.exists()) return@runCatching
        val out = HashMap<String, Pair<Float, Int>>()
        for (line in f.readLines()) {
            val p = line.trim().split(" ")
            if (p.size != 3) continue
            val v = p[1].toFloatOrNull() ?: continue
            val n = p[2].toIntOrNull() ?: continue
            out[p[0]] = v to n
        }
        engine.learned.restore(out)
        if (engine.learned.kept > 0)
            log?.invoke("carrying ${engine.learned.kept} kept balances " +
                "forward: ${engine.learned.summary()}")
    }

    // ------------------------------------------------------------------
    private fun loop() {
        send(OscMessage("/xinfo", emptyList()))
        var ok = false
        val start = now()
        while (now() - start < 3.0 && !ok) {
            receiveOnce()?.let { if (it.address == "/xinfo") {
                log?.invoke("found ${it.stringArg(1)} ${it.stringArg(2)} " +
                    "fw ${it.stringArg(3)} at $host")
                ok = true
            } }
        }
        if (!ok) { log?.invoke("no console answered at $host:$port"); return }
        loadLearned()
        fetchNames()
        show?.head("bench: $host:$port", engine, names, 0, "")

        while (running) {
            val t = now()
            if (t - lastKeep > 5.0) {
                lastKeep = t
                send(OscMessage("/xremotenfb", emptyList()))
                send(OscMessage("/meters",
                    listOf("/meters/${Meters.BANK_INPUTS}")))
                send(OscMessage("/meters", listOf("/meters/${Meters.BANK_RTA}")))
                send(OscMessage("/meters",
                    listOf("/meters/${Meters.BANK_DYNAMICS}")))
            }
            receiveOnce()?.let { handle(it, t); lastRx = t }

            // while hunting a howl, sweep the stage fast (every channel in
            // turn) so the ring-out can find the microphone; otherwise dawdle
            if (t - rtaFocusT > (if (ringOut.hunting) 0.5 else 3.0)) {
                val active = if (ringOut.hunting)
                    (0 until Meters.INPUT_COUNT).toList()
                    else engine.activeChannels().sorted()
                if (active.isNotEmpty()) {
                    val next = active[(active.indexOf(rtaFocus) + 1)
                        .mod(active.size)]
                    if (next != rtaFocus) {
                        rtaFocus = next
                        send(OscMessage("/-stat/rta/source", listOf(rtaFocus)))
                        watchdog.sourceChanged()
                    }
                    rtaFocusT = t
                }
            }

            if (t - lastTick >= 1.0) {
                lastTick = t
                if (directing) for (w in engine.tick(t)) {
                    lastSent[w.channel] = w.levelDb
                    show?.fader(w.channel, w.levelDb, nameOf(w.channel),
                        lastFader[w.channel],
                        engine.decisions.firstOrNull { it.channel == w.channel }
                            ?.let { "— ${it.kind}: ${it.reason}" }, t)
                    lastFader[w.channel] = w.levelDb
                    send(OscMessage(w.address,
                        listOf(FaderLaw.dbToFloat(w.levelDb))))
                } else engine.tick(t)
                // the once-per-instrument chain — behind the same
                // switch as the rest of the tone work, so "do not touch
                // my channel processing" means one thing on the bench
                // and on the tablet
                if (directing && doctorOn) for (w in engine.treatmentPass(t)) {
                    lastParam[w.address] = w.value
                    send(OscMessage(w.address, listOf(w.value)))
                    log?.invoke("treat %s = %.3f".format(
                        java.util.Locale.ROOT, w.address, w.value))
                }
                doctor?.let { d ->
                    if (directing && doctorOn)
                        for (w in d.tick(engine.activeChannels(),
                                engine.boostsAllowed(t), engine.frozenAll)) {
                            send(OscMessage(w.address, listOf(w.value)))
                            logDoctor(d, w.address, w.value)
                        }
                }
                // RING OUT THE STAGE. Safety, not tone, so it writes even
                // while only watching — but on the bench there is no harm
                // either way. Cut-only, on the channel, same as the tablet.
                for (w in ringOut.tick(t, mayWrite = directing))
                    send(OscMessage(w.address, listOf(w.value)))
                if (ringOut.lastAction != lastRingAction) {
                    lastRingAction = ringOut.lastAction
                    show?.mark("RING-OUT", ringOut.lastAction, t)
                    log?.invoke("RING-OUT ${ringOut.lastAction}")
                    saveFeedbackProfile()
                }
                // a microphone that actually howled is not lifted again for
                // a few minutes — on the mains AND on the wedges (a guard is
                // not a live ring, so it is skipped)
                for (n in ringOut.active()) if (!n.guard) {
                    monBal.onRing(n.ch, t); engine.onRing(n.ch, t)
                }
                // THE WEDGES, SLIGHTLY: cut-first, one small move per bus,
                // never against a hand, never into a live howl, only when
                // keeping is on — the same keeper the tablet runs.
                if (directing && keepMonitors && !engine.frozenAll)
                    applyMonitorPlan(monBal.plan(
                        tSec = t,
                        roles = engine.state.mapValues { it.value.role },
                        kit = engine.drumKit(),
                        playing = !engine.betweenSongs && engine.ready,
                        feedbackActive = ringOut.hunting || engine.watchdogVeto), t)
                // re-read the sends now and then, to notice a hand on a wedge
                if (directing && keepMonitors && t - sendsReadT > 25.0) {
                    sendsReadT = t
                    pollSends()
                }
                show?.snapshot(t, engine, doctor, names, directing)
                show?.summary(t, engine, names)
                // the whole monitor picture on a cadence, into the log
                if (t - lastMonMatrix >= 60.0) { lastMonMatrix = t; dumpMonitorMatrix(t) }
            }
        }
    }

    /** write the keeper's cuts (monitor sends only) and log its notes */
    private fun applyMonitorPlan(
        writes: List<com.stagemix.engine.ParamWrite>, t: Double) {
        for (w in writes) {
            if (!com.stagemix.engine.isMonitorSend(w.address)) continue
            lastParam[w.address] = w.value          // our own write, echo-safe
            send(OscMessage(w.address, listOf(w.value)))
            log?.invoke("wedge %s = %.3f".format(
                java.util.Locale.ROOT, w.address, w.value))
        }
        for (n in monBal.drainNotes()) show?.mark("MONITOR", n, t)
    }

    /** ask the console for every monitor send, paced like the tablet */
    private fun pollSends() {
        for (ch in 0 until 16)
            for (b in com.stagemix.engine.AUX_SEND_FIRST..
                     com.stagemix.engine.AUX_SEND_LAST) {
                send(OscMessage(osc("/ch/%02d/mix/%02d/level", ch + 1, b),
                    emptyList()))
                Thread.sleep(2)
            }
    }

    /** the complete monitor picture — every wedge, every send — for the log */
    private fun dumpMonitorMatrix(t: Double) {
        val lg = show ?: return
        val roles = engine.state.mapValues { it.value.role }
        val kit = engine.drumKit()
        val floor = com.stagemix.engine.MonitorMap.MONITOR_FLOOR_DB
        fun nm(ch: Int) = (names[ch] ?: "ch%02d".format(ch + 1)).take(8)
        for (w in monitors.all()) {
            val targets = monitors.critique(w.bus, roles, kit)
                .mapNotNull { n -> n.wantDb?.let { n.ch to it } }.toMap()
            val live = w.sends.entries.filter { it.value > floor }
                .sortedByDescending { it.value }
            val off = w.sends.entries.filter { it.value <= floor }
                .map { it.key }.sorted()
            lg.note("MON", "bus%02d %-12s [%s · %s] — %d live, %d not sent"
                .format(java.util.Locale.ROOT, w.bus,
                    (busNames[w.bus - 1] ?: w.name).take(12),
                    w.kind.name.lowercase(),
                    if (w.inEars) "in-ears" else "wedge", live.size, off.size))
            for ((ch, db) in live) {
                val tgt = targets[ch]?.let {
                    " (wants %+.1f, %+.1f off)".format(
                        java.util.Locale.ROOT, it, db - it) } ?: ""
                lg.note("MON", "    %-8s %+6.1f dB%s".format(
                    java.util.Locale.ROOT, nm(ch), db, tgt))
            }
            if (off.isNotEmpty())
                lg.note("MON", "    not sent: " + off.joinToString(" ") { nm(it) })
        }
    }

    // ---- read accessors + controls for the bench UI ---------------------
    fun wedges(): List<com.stagemix.engine.MonitorMap.Wedge> = monitors.all()
    fun wedgeNotes(bus: Int) = monitors.critique(bus,
        engine.state.mapValues { it.value.role }, engine.drumKit())
    fun monitorMoves() = monBal.moved()
    fun busName(bus: Int) = busNames[bus - 1] ?: "MON $bus"
    fun inEarsFor(bus: Int) = monitors.inEarsFor(bus)
    fun setMonitorInEars(bus: Int, inEars: Boolean) {
        if (bus < 1) return
        monitorInEars[bus] = inEars
        monitors.setInEars(bus, inEars)
    }

    private fun handle(m: OscMessage, t: Double) {
        when (m.address) {
            "/meters/${Meters.BANK_INPUTS}" ->
                m.blobArg(0)?.let { Meters.decode(it) }
                    ?.let { engine.onMeters(it, t) }
            "/meters/${Meters.BANK_RTA}" ->
                m.blobArg(0)?.let { Meters.decode(it) }?.let { bins ->
                    watchdog.onRta(bins, t)
                    if (watchdog.vetoActive != lastVeto) {
                        lastVeto = watchdog.vetoActive
                        engine.watchdogVeto = watchdog.vetoActive
                        // start / stop the hunt for the microphone in the loop
                        if (watchdog.vetoActive)
                            ringOut.ringing(watchdog.lastFreqHz, t)
                        else ringOut.cleared(t)
                        show?.note("HOWL", if (watchdog.vetoActive)
                            "feedback suspected at ~${watchdog.lastFreqHz} Hz"
                            else "feedback cleared")
                    }
                    // the hunt needs every channel's level at the ring
                    // frequency, so feed RingOut on every frame while it is
                    // sweeping (it self-gates when not hunting)
                    ringOut.onRta(rtaFocus, bins, t)
                    if (rtaFocus >= 0 && t - rtaFocusT > 0.5) {
                        doctor?.onRta(rtaFocus, bins, t)
                        // and the same frame to the listener that works
                        // out what is plugged in here. BRACES: without
                        // them only the doctor was guarded, and this ran
                        // on every frame — including before the analyzer
                        // had settled on its new focus, which feeds one
                        // channel's spectrum in under another's name.
                        engine.onRtaFor(rtaFocus, bins, t)
                    }
                }
            "/meters/${Meters.BANK_DYNAMICS}" ->
                m.blobArg(0)?.let { Meters.decode(it) }?.let { v ->
                    if (v.size >= Meters.DYN_COUNT)
                        for (ch in 0 until Meters.INPUT_COUNT)
                            doctor?.onGainReduction(
                                ch, v[Meters.compGrIndex(ch)], t)
                }
            else -> {
                val s = m.stringArg(0)
                if (s != null && m.address.endsWith("/config/name")) {
                    Regex("/ch/(\\d\\d)/config/name").find(m.address)
                        ?.groupValues?.get(1)?.toIntOrNull()?.let { ch ->
                            if (s.isNotBlank()) {
                                names[ch - 1] = s
                                engine.setChannelName(ch - 1, s)
                                engine.setRoleFromName(ch - 1, inferRole(s))
                            }
                        }
                    // a monitor bus name, so the app knows what the wedge is for
                    Regex("/bus/(\\d)/config/name").find(m.address)
                        ?.groupValues?.get(1)?.toIntOrNull()?.let { b ->
                            if (s.isNotBlank()) busNames[b - 1] = s
                        }
                    return
                }
                // the mute keys — the only honest report of what is
                // actually reaching the mains, since the meters we run
                // on are pre-fader and pre-mute
                Regex("^/ch/(\\d\\d)/mix/on$").find(m.address)?.let { mt ->
                    val ch = mt.groupValues[1].toInt() - 1
                    val on = when (val a = m.args.firstOrNull()) {
                        is Int -> a != 0
                        is Float -> a > 0.5f
                        else -> return
                    }
                    if (engine.setChannelMuted(ch, !on))
                        log?.invoke("ch%02d %s".format(ch + 1,
                            if (on) "un-muted on the desk"
                            else "muted on the desk — left alone"))
                    return
                }
                val v = m.args.firstOrNull() as? Float ?: return
                pending[m.address] = v
                // a monitor send came back — keep the map current so the
                // keeper can see the engineer's hand on a wedge (skip while
                // collecting, so takeover's own reads are not read as a hand)
                if (com.stagemix.engine.isMonitorSend(m.address) && !collecting)
                    Regex("^/ch/(\\d\\d)/mix/(\\d\\d)/level$").find(m.address)
                        ?.let { mm ->
                            val ch = mm.groupValues[1].toInt() - 1
                            val bus = mm.groupValues[2].toInt()
                            val db = FaderLaw.floatToDb(v)
                            monitors.onSend(bus, ch, db)
                            monBal.onSend(bus, ch, db, now())
                        }
                if (!collecting && directing && engine.ready) {
                    Regex("^/ch/(\\d\\d)/mix/fader$").find(m.address)
                        ?.let { mt ->
                            val ch = mt.groupValues[1].toInt() - 1
                            val db = FaderLaw.floatToDb(v)
                            val mine = lastSent[ch]
                            if (mine == null || abs(db - mine) > 0.1f) {
                                engine.operatorOverride(ch, db, now())
                                lastSent.remove(ch)
                            }
                        }
                    // an EQ band or a compressor setting changing under us
                    // is the engineer disagreeing with the chain we set:
                    // that parameter is theirs from here on
                    if (isSafeAddress(m.address))
                        Regex("^/ch/(\\d\\d)/").find(m.address)?.let { mt ->
                            val ch = mt.groupValues[1].toInt() - 1
                            val ours = lastParam[m.address]
                            if (ours == null || abs(v - ours) > 0.005f)
                                engine.treatmentOverride(ch, m.address)
                        }
                }
            }
        }
    }

    private fun fetchNames() {
        for (ch in 0 until 16)
            send(OscMessage(osc("/ch/%02d/config/name", ch + 1), emptyList()))
        // and the six monitor buses, so the app can tell what each wedge is
        for (b in 0 until 6)
            send(OscMessage(osc("/bus/%d/config/name", b + 1), emptyList()))
        val stop = now() + 2.0
        while (now() < stop) receiveOnce()?.let { handle(it, now()) }
        doctor = ToneDoctor((0 until 16).toList(),
            (0 until 16).associateWith { engine.state[it]?.role
                ?: Role.INSTRUMENT })
        log?.invoke("channel names: " + (0 until 16).joinToString(", ") {
            names[it] ?: "ch${it + 1}" })
    }

    private fun takeover() {
        collecting = true
        pending.clear()
        for (ch in 0 until 16) {
            send(OscMessage(osc("/ch/%02d/mix/fader", ch + 1), emptyList()))
            send(OscMessage(osc("/ch/%02d/mix/on", ch + 1), emptyList()))
            for (b in 1..4)
                send(OscMessage(osc("/ch/%02d/eq/%d/g", ch + 1, b), emptyList()))
            send(OscMessage(osc("/ch/%02d/dyn/thr", ch + 1), emptyList()))
            // and every monitor send, so the keeper has a balance to read
            for (b in com.stagemix.engine.AUX_SEND_FIRST..
                     com.stagemix.engine.AUX_SEND_LAST)
                send(OscMessage(osc("/ch/%02d/mix/%02d/level", ch + 1, b),
                    emptyList()))
            Thread.sleep(3)
        }
        val stop = now() + 2.5
        while (now() < stop) receiveOnce()?.let { handle(it, now()) }
        val faders = HashMap<Int, Float>()
        for (ch in 0 until 16)
            pending[osc("/ch/%02d/mix/fader", ch + 1)]
                ?.let { faders[ch] = FaderLaw.floatToDb(it) }
        collecting = false
        if (faders.isEmpty()) { log?.invoke("takeover failed — no faders"); return }
        if (faders.size < 16)
            log?.invoke("PARTIAL takeover: only ${faders.size}/16 answered")
        engine.takeover(faders, now())
        show?.takeover(faders, names)
        lastSent.clear()
        doctor?.let { d ->
            for (ch in 0 until 16) {
                val g = FloatArray(4) { b ->
                    pending[osc("/ch/%02d/eq/%d/g", ch + 1, b + 1)]
                        ?.let { it * 30f - 15f } ?: 0f }
                val thr = pending[osc("/ch/%02d/dyn/thr", ch + 1)]
                    ?.let { it * 60f - 60f }
                d.snapshotChannel(ch, g, thr)
            }
        }
        // THE WEDGES: read every monitor send the console answered, seed
        // all six buses (named or "MON n"), re-apply the in-ears choices,
        // and write the opening picture to the log
        for (ch in 0 until 16)
            for (b in com.stagemix.engine.AUX_SEND_FIRST..
                     com.stagemix.engine.AUX_SEND_LAST)
                pending[osc("/ch/%02d/mix/%02d/level", ch + 1, b)]?.let {
                    val db = FaderLaw.floatToDb(it)
                    monitors.onSend(b, ch, db)
                    monBal.onSend(b, ch, db, now())
                }
        for (b in com.stagemix.engine.AUX_SEND_FIRST..
                 com.stagemix.engine.AUX_SEND_LAST)
            monitors.onBusName(b,
                busNames[b - 1]?.takeIf { it.isNotBlank() } ?: "MON $b")
        for ((bus, ie) in monitorInEars) monitors.setInEars(bus, ie)
        dumpMonitorMatrix(now())

        log?.invoke("took over ${faders.size} faders — listening, then leading")
        preRingSetup()
    }

    /** carry this rig's known feedback forward, log it, and (if on) guard it */
    private fun preRingSetup() {
        carriedFeedback = loadFeedbackProfile()
        if (carriedFeedback.isEmpty()) {
            show?.note("HOWL", "no feedback history yet — the bench will " +
                "learn each ring and carry it forward")
            return
        }
        show?.note("HOWL", "── feedback carried forward from earlier runs ──")
        for ((ch, hz, rings) in carriedFeedback.sortedByDescending { it.third })
            show?.note("HOWL", "  %s has howled at %.0f Hz %d time%s before"
                .format(Locale.ROOT, nameOf(ch), hz, rings,
                    if (rings == 1) "" else "s"))
        if (!preRing) {
            show?.note("HOWL", "pre-ring is OFF — recorded, not pre-cut")
            return
        }
        val placed = ringOut.seedGuards(carriedFeedback.map {
            com.stagemix.engine.RingOut.Learned(it.first, it.second, it.third) },
            minRings = 2, guardDb = 3f)
        for (p in placed)
            show?.mark("HOWL", ("PRE-RING %s at %.0f Hz — a 3.0 dB guard cut, " +
                "because it has howled %d times here")
                .format(Locale.ROOT, nameOf(p.ch), p.hz, p.rings), now())
        if (placed.isNotEmpty())
            log?.invoke("pre-ring placed ${placed.size} guard cut(s)")
    }

    private fun feedbackFile() = File(logDir, "feedback-profile.txt")

    private fun loadFeedbackProfile(): List<Triple<Int, Float, Int>> =
        runCatching {
            val f = feedbackFile()
            if (!f.exists()) return emptyList()
            f.readLines().mapNotNull { line ->
                val p = line.trim().split(" ")
                if (p.size != 3) return@mapNotNull null
                val ch = p[0].toIntOrNull() ?: return@mapNotNull null
                val hz = p[1].toFloatOrNull() ?: return@mapNotNull null
                val n = p[2].toIntOrNull() ?: return@mapNotNull null
                Triple(ch, hz, n)
            }
        }.getOrDefault(emptyList())

    /** the carried-in counts plus this run's, absolute so it never double-adds */
    private fun saveFeedbackProfile() = runCatching {
        fun key(ch: Int, hz: Float) = "$ch:${Math.round(hz)}"
        val m = HashMap<String, Triple<Int, Float, Int>>()
        for (e in carriedFeedback) m[key(e.first, e.second)] = e
        for (n in ringOut.learnedProfile()) {
            val k = key(n.ch, n.hz)
            m[k] = Triple(n.ch, n.hz, (m[k]?.third ?: 0) + n.rings)
        }
        feedbackFile().writeText(m.values.joinToString("\n") {
            "${it.first} ${it.second} ${it.third}" })
    }

    private fun logDoctor(d: ToneDoctor, addr: String, value: Float) {
        val m = Regex("^/ch/(\\d\\d)/(eq/(\\d)/g|dyn/thr)$").find(addr) ?: return
        val ch = m.groupValues[1].toInt() - 1
        val st = d.state[ch] ?: return
        if (m.groupValues[3].isNotEmpty()) {
            val b = m.groupValues[3].toInt() - 1
            val live = st.liveBands; val ref = st.refBands
            show?.eq(ch, b, value * 30f - 15f,
                if (live != null && ref != null) live[b] - ref[b] else 0f,
                nameOf(ch))
        } else show?.comp(ch, value * 60f - 60f, st.grEma, st.refGr, nameOf(ch))
    }

    private fun nameOf(ch: Int) = names[ch]
        ?: engine.state[ch]?.cfg?.name ?: "ch${ch + 1}"

    private fun send(m: OscMessage) {
        try {
            val b = m.encode()
            sock.send(DatagramPacket(b, b.size, addr))
        } catch (e: Exception) { /* the bench is not the show */ }
    }

    private fun receiveOnce(): OscMessage? = try {
        val buf = ByteArray(8192)
        val p = DatagramPacket(buf, buf.size)
        sock.receive(p)
        OscMessage.decode(p.data.copyOf(p.length))
    } catch (e: Exception) { null }
}
