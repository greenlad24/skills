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
        .ifEmpty { com.stagemix.engine.defaultRigProfile() })
    var doctor: ToneDoctor? = null; private set
    private val watchdog = FeedbackWatchdog()
    private var show: ShowLog? = null

    private val sock = DatagramSocket().apply { soTimeout = 200 }
    private val addr = InetSocketAddress(InetAddress.getByName(host), port)
    private val pending = ConcurrentHashMap<String, Float>()
    private val lastSent = ConcurrentHashMap<Int, Float>()
    @Volatile private var collecting = false
    @Volatile private var running = false

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
        Thread({ loop() }, "desk-client").apply { isDaemon = true }.start()
    }

    fun stop() {
        running = false
        show?.let { s -> s.footer(engine); s.close() }
        sock.close()
    }

    fun logFile(): File? = show?.file

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

            if (t - rtaFocusT > 3.0) {
                val active = engine.activeChannels().sorted()
                if (active.isNotEmpty()) {
                    val next = active[(active.indexOf(rtaFocus) + 1)
                        .mod(active.size)]
                    if (next != rtaFocus) {
                        rtaFocus = next
                        send(OscMessage("/-stat/rta/source", listOf(rtaFocus)))
                    }
                    rtaFocusT = t
                }
            }

            if (t - lastTick >= 1.0) {
                lastTick = t
                if (directing) for (w in engine.tick(t)) {
                    lastSent[w.channel] = w.levelDb
                    show?.fader(w.channel, w.levelDb, nameOf(w.channel))
                    send(OscMessage(w.address,
                        listOf(FaderLaw.dbToFloat(w.levelDb))))
                } else engine.tick(t)
                doctor?.let { d ->
                    for (ch in engine.state.keys)
                        if (engine.state[ch]?.role == Role.KEYS)
                            d.setLowFill(ch, engine.keysLowFill)
                    if (directing && doctorOn)
                        for (w in d.tick(engine.activeChannels(),
                                engine.boostsAllowed(t), engine.frozenAll)) {
                            send(OscMessage(w.address, listOf(w.value)))
                            logDoctor(d, w.address, w.value)
                        }
                }
                show?.snapshot(t, engine, doctor, names, directing)
                show?.summary(t, engine, names)
            }
        }
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
                        show?.note("HOWL", if (watchdog.vetoActive)
                            "feedback suspected at ~${watchdog.lastFreqHz} Hz"
                            else "feedback cleared")
                    }
                    if (rtaFocus >= 0 && t - rtaFocusT > 0.5)
                        doctor?.onRta(rtaFocus, bins, t)
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
                                engine.setRole(ch - 1, inferRole(s))
                            }
                        }
                    return
                }
                val v = m.args.firstOrNull() as? Float ?: return
                pending[m.address] = v
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
                }
            }
        }
    }

    private fun fetchNames() {
        for (ch in 0 until 16)
            send(OscMessage(osc("/ch/%02d/config/name", ch + 1), emptyList()))
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
            for (b in 1..4)
                send(OscMessage(osc("/ch/%02d/eq/%d/g", ch + 1, b), emptyList()))
            send(OscMessage(osc("/ch/%02d/dyn/thr", ch + 1), emptyList()))
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
        log?.invoke("took over ${faders.size} faders — listening, then leading")
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
