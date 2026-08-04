package com.stagemix.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.wifi.WifiManager
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.util.Log
import com.stagemix.engine.FaderLaw
import com.stagemix.engine.Meters
import com.stagemix.engine.osc
import com.stagemix.engine.OscMessage
import com.stagemix.engine.REVERT_HOLD_SEC
import com.stagemix.engine.ShowLog
import com.stagemix.engine.StageEngine
import com.stagemix.engine.ToneDoctor
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withTimeoutOrNull
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.InetSocketAddress
import java.util.concurrent.ConcurrentHashMap
import kotlin.math.abs

/**
 * Foreground service that owns the UDP socket, the /xremote + /meters
 * keep-alives, and the engine loop. Fail-safe posture mirrors
 * AutoDirector: if this app dies, the mixer keeps the last human mix —
 * we only ever *send* bounded corrections, we hold nothing open.
 */
class MixerService : Service() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var socket: DatagramSocket? = null
    private var mixerAddr: InetSocketAddress? = null
    private var engine: StageEngine? = null
    private var doctor: ToneDoctor? = null
    private val watchdog = com.stagemix.engine.FeedbackWatchdog()
    private var lastVeto = false
    private var wifiLock: WifiManager.WifiLock? = null
    private var wakeLock: PowerManager.WakeLock? = null
    private var loopJob: Job? = null

    /** parameter enquiry replies parked here by address */
    private val pending = ConcurrentHashMap<String, Float>()
    /** last fader value we sent per channel (dB) */
    private val lastSent = ConcurrentHashMap<Int, Float>()
    /** channel-processing values we wrote, so an echo is not a human */
    private val lastParam = ConcurrentHashMap<String, Float>()
    /** true while takeoverNow() is collecting enquiry replies */
    @Volatile private var collecting = false
    /** only one takeover may own `pending`/`collecting` at a time */
    private val takeoverLock = Mutex()
    /** the night's show log — levels, EQ, comp, and every decision */
    private var show: ShowLog? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_CONNECT -> {
                startForegroundNotif()
                acquireLocks()
                connect(intent.getStringExtra("ip") ?: return START_NOT_STICKY)
            }
            ACTION_SNAPSHOT -> scope.launch { takeoverNow() }  // re-baseline
            ACTION_REVERT -> scope.launch { revert() }
            ACTION_DIRECTING -> {
                val on = intent.getBooleanExtra("on", false)
                AppState.directing.value = on
                show?.user(if (on) "you switched MIXING ON"
                           else "you switched MIXING OFF (shadow mode)")
                if (on) scope.launch { takeoverNow() }
            }
            ACTION_FREEZE_ALL -> {
                val on = intent.getBooleanExtra("on", true)
                engine?.frozenAll = on
                AppState.frozenAll.value = on
                show?.user(if (on) "you pressed FREEZE ALL"
                           else "you released FREEZE ALL")
            }
            ACTION_FREEZE_CH -> {
                val ch = intent.getIntExtra("ch", -1)
                val on = intent.getBooleanExtra("on", true)
                engine?.freezeChannel(ch, on)
                doctor?.state?.get(ch)?.frozen = on
                show?.user("you ${if (on) "locked" else "unlocked"} " +
                    "ch%02d %s".format(java.util.Locale.ROOT, ch + 1,
                        chName(ch)))
            }
            ACTION_DOCTOR -> {
                val on = intent.getBooleanExtra("on", true)
                AppState.doctorOn.value = on
                show?.user("you turned the Channel Doctor " +
                    (if (on) "ON" else "OFF"))
            }
            ACTION_FEEDBACK -> {
                val kind = intent.getStringExtra("kind") ?: return START_NOT_STICKY
                engine?.let { e ->
                    e.applyFeedback(kind, now())
                    AppState.saveBias(this, e.pyramidBias)
                    show?.user("you tapped '$kind' — taste is now " +
                        AppState.tasteSummary.value.ifBlank { "neutral" })
                }
            }
            ACTION_DISCONNECT -> shutdown()
        }
        return START_NOT_STICKY
    }

    // ------------------------------------------------------------------
    /**
     * Broadcast /xinfo on the local network (the M18's own AP included)
     * and return the first mixer that answers. Fully offline.
     */
    private fun discover(timeoutSec: Double = 3.0): String? {
        return try {
            DatagramSocket().use { s ->
                s.broadcast = true
                s.soTimeout = 300
                val probe = OscMessage("/xinfo", emptyList()).encode()
                s.send(DatagramPacket(probe, probe.size,
                    InetAddress.getByName("255.255.255.255"), PORT))
                val start = now()
                while (now() - start < timeoutSec) {
                    try {
                        val buf = ByteArray(1024)
                        val p = DatagramPacket(buf, buf.size)
                        s.receive(p)
                        val m = OscMessage.decode(buf.copyOf(p.length))
                        if (m?.address == "/xinfo")
                            return p.address.hostAddress
                    } catch (e: Exception) { /* timeout tick */ }
                }
                null
            }
        } catch (e: Exception) {
            Log.w(TAG, "discovery failed: ${e.message}")
            null
        }
    }

    private fun connect(ipWanted: String) {
        AppState.conn.value = AppState.Conn.CONNECTING
        AppState.lastError.value = null
        loopJob?.cancel()
        loopJob = scope.launch {
            try {
                // Empty IP -> find the mixer ourselves (tablet lives on
                // the M18's own Wi-Fi; the console answers broadcasts).
                val ip = ipWanted.ifBlank { discover() ?: "" }
                if (ip.isBlank()) {
                    AppState.conn.value = AppState.Conn.DISCONNECTED
                    AppState.lastError.value =
                        "No mixer found — is the tablet on the M18's Wi-Fi?"
                    return@launch
                }
                socket?.close()
                val s = DatagramSocket().apply { soTimeout = 200 }
                socket = s
                mixerAddr = InetSocketAddress(InetAddress.getByName(ip), PORT)

                val cfg = AppState.config.value
                show?.close()
                show = ShowLog(getExternalFilesDir(null) ?: filesDir)
                AppState.logPath.value = show?.file?.absolutePath ?: ""
                engine = StageEngine(cfg.channels).also { eng ->
                    // continue from last night's progress
                    eng.pyramidBias.putAll(
                        AppState.loadBias(this@MixerService))
                    // every decision goes to the show log as it is made;
                    // the console's own list only keeps the last 60
                    eng.onDecision = { d -> show?.decision(d) }
                }
                AppState.loadNights(this@MixerService)
                doctor = ToneDoctor(cfg.channels.map { it.index },
                    cfg.channels.associate { it.index to it.role })
                AppState.snapshotTaken.value = false

                // verify the mixer is there
                send(OscMessage("/xinfo", emptyList()))
                var ok = false
                val start = now()
                while (now() - start < 3.0 && !ok) {
                    receiveOnce()?.let { m ->
                        if (m.address == "/xinfo") {
                            AppState.mixer.value = AppState.MixerInfo(
                                ip, m.stringArg(1) ?: "", m.stringArg(2) ?: "",
                                m.stringArg(3) ?: "")
                            ok = true
                        }
                    }
                }
                if (!ok) {
                    show?.net("no mixer answered at $ip:$PORT")
                    AppState.conn.value = AppState.Conn.DISCONNECTED
                    AppState.lastError.value =
                        "No mixer answered at $ip:$PORT — check Wi-Fi/IP"
                    return@launch
                }
                AppState.conn.value = AppState.Conn.CONNECTED
                AppState.config.value = cfg.copy(mixerIp = ip)
                fetchNames()
                engine?.let { eng ->
                    val mi = AppState.mixer.value
                    show?.head("name='${mi.name}' model='${mi.model}' " +
                        "fw='${mi.firmware}' ip=${mi.ip}", eng,
                        AppState.mixerChannelNames.value,
                        AppState.nightsCount.value,
                        AppState.tasteSummary.value)
                }
                show?.net("connected to $ip:$PORT — meters and RTA " +
                    "subscribed, offline on the mixer's own Wi-Fi")
                runLoop()
            } catch (e: Exception) {
                Log.w(TAG, "connect failed", e)
                AppState.conn.value = AppState.Conn.DISCONNECTED
                AppState.lastError.value = e.message
            }
        }
    }

    /**
     * The whole show loop: keep-alives, meters, RTA round-robin, engine
     * + doctor ticks, writes. Wi-Fi hiccups (common on the M18's own
     * 2.4 GHz AP) are survived in place: UDP is connectionless, the
     * engine freezes itself while meters are stale, and the keep-alives
     * re-establish everything the moment packets flow again.
     */
    private suspend fun runLoop() {
        var lastKeepalive = 0.0
        var lastTick = 0.0
        var lastRx = now()
        var rtaFocus = -1
        var rtaFocusT = 0.0
        while (scope.isActive && AppState.conn.value != AppState.Conn.DISCONNECTED) {
            val t = now()
            if (t - lastKeepalive > 5.0) {
                lastKeepalive = t
                send(OscMessage("/xremotenfb", emptyList()))
                send(OscMessage("/meters", listOf("/meters/${Meters.BANK_INPUTS}")))
                send(OscMessage("/meters",
                    listOf("/meters/${Meters.BANK_RTA}")))       // RTA
                send(OscMessage("/meters",
                    listOf("/meters/${Meters.BANK_DYNAMICS}")))  // gate+comp GR
            }
            val m = receiveOnce()
            if (m != null) {
                lastRx = t
                if (AppState.conn.value == AppState.Conn.CONNECTING)
                    AppState.conn.value = AppState.Conn.CONNECTED
                handle(m, t, rtaFocus, rtaFocusT)
            } else if (t - lastRx > 10.0 &&
                       AppState.conn.value == AppState.Conn.CONNECTED) {
                // radio dropout: show it, keep trying — engine is frozen
                // by meter staleness already
                AppState.conn.value = AppState.Conn.CONNECTING
                AppState.lastError.value = "Mixer silent — waiting for Wi-Fi…"
                show?.net("METERS LOST — %.0fs with no packet from the mixer; "
                    .format(java.util.Locale.ROOT, t - lastRx) +
                    "the engine is holding every fader still")
            }
            val e = engine ?: continue
            // RTA round-robin: park the console's RTA on each active
            // channel for ~3 s so the doctor hears everyone regularly.
            if (t - rtaFocusT > 3.0) {
                val active = e.activeChannels().sorted()
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
                AppState.holdReason.value = e.holdReason(t)
                val directing = AppState.directing.value
                if (directing) {
                    // the ONLY writes the engine can produce are channel
                    // faders (mains) — monitor buses are human territory
                    for (w in e.tick(t)) sendFader(w.channel, w.levelDb)
                } else {
                    e.tick(t) // keep state warm; writes discarded when paused
                }
                // The chain an engineer would set at soundcheck, set once
                // per instrument and then left alone. Channel processing
                // and FX sends only — ChannelTreatment.isSafeAddress
                // refuses an aux send outright, because the wedges are
                // not ours.
                if (directing) for (w in e.treatmentPass(t)) {
                    lastParam[w.address] = w.value
                    send(OscMessage(w.address, listOf(w.value)))
                }
                doctor?.let { d ->
                    // ensemble hook: while drums play without a bass, the
                    // piano channels fill the low end (EQ low band lift)
                    for (ch in AppState.config.value.channels)
                        if (ch.role == com.stagemix.engine.Role.KEYS)
                            d.setLowFill(ch.index, e.keysLowFill)
                    if (directing && AppState.doctorOn.value) {
                        for (w in d.tick(e.activeChannels(),
                                upAllowed = e.boostsAllowed(t),
                                frozenAll = e.frozenAll)) {
                            send(OscMessage(w.address, listOf(w.value)))
                            logDoctorWrite(d, w)
                        }
                    }
                }
                publishStrips(t)
                AppState.decisions.value = e.decisions.toList()
                show?.let { lg ->
                    lg.snapshot(t, e, doctor, AppState.mixerChannelNames.value,
                        directing)
                    lg.summary(t, e, AppState.mixerChannelNames.value)
                }
            }
        }
    }

    private fun handle(m: OscMessage, t: Double, rtaFocus: Int,
                       rtaFocusT: Double) {
        val e = engine ?: return
        when (m.address) {
            "/meters/${Meters.BANK_INPUTS}" -> {
                m.blobArg(0)?.let { Meters.decode(it) }?.let { levels ->
                    e.onMeters(levels, t)
                }
            }
            "/meters/${Meters.BANK_RTA}" -> {
                m.blobArg(0)?.let { Meters.decode(it) }?.let { bins ->
                    // every RTA frame feeds the howl recognizer — a howl
                    // circulates acoustically, so any open mic hears it
                    watchdog.onRta(bins, t)
                    if (watchdog.vetoActive != lastVeto) {
                        lastVeto = watchdog.vetoActive
                        e.watchdogVeto = watchdog.vetoActive
                        show?.note("HOWL", if (watchdog.vetoActive)
                            "feedback suspected at ~${watchdog.lastFreqHz} Hz " +
                            "— every boost frozen until it clears"
                            else "feedback cleared — boosts allowed again")
                        AppState.lastError.value = if (watchdog.vetoActive)
                            "⚠ FEEDBACK suspected ~${watchdog.lastFreqHz} Hz " +
                            "— boosts frozen; notch it on the GEQ"
                        else null
                    }
                    // channel attribution for the doctor needs the
                    // analyzer settled on its focus source
                    if (rtaFocus >= 0 && t - rtaFocusT > 0.5) {
                        doctor?.onRta(rtaFocus, bins, t)
                        // and the same frame to the listener that works
                        // out what is plugged in here. BRACES: without
                        // them only the doctor was guarded, and this ran
                        // on every frame — including before the analyzer
                        // had settled on its new focus, which feeds one
                        // channel's spectrum in under another's name.
                        engine?.onRtaFor(rtaFocus, bins)
                    }
                }
            }
            "/meters/${Meters.BANK_DYNAMICS}" -> {
                // 39 values in blocks: 16 gate GR, then 16 comp GR, then
                // 6 bus and the main. Not interleaved — reading it as
                // [gate, comp] pairs fed channel 2's GATE into channel
                // 1's compressor tending.
                m.blobArg(0)?.let { Meters.decode(it) }?.let { v ->
                    if (v.size >= Meters.DYN_COUNT)
                        for (ch in 0 until Meters.INPUT_COUNT)
                            doctor?.onGainReduction(
                                ch, v[Meters.compGrIndex(ch)], t)
                }
            }
            else -> {
                // parameter enquiry replies / other-client changes
                val v = m.args.firstOrNull() as? Float
                if (v != null) {
                    pending[m.address] = v
                    // /xremotenfb means our own writes are never echoed —
                    // a fader update arriving here is a HUMAN move (or
                    // another client). While mixing, the human wins.
                    if (!collecting && AppState.directing.value && e.ready) {
                        Regex("^/ch/(\\d\\d)/mix/fader$")
                            .find(m.address)?.let { match ->
                                val ch = match.groupValues[1].toInt() - 1
                                val db = FaderLaw.floatToDb(v)
                                // our own write coming back is not a human
                                val mine = lastSent[ch]
                                if (mine == null || abs(db - mine) > ECHO_TOL_DB) {
                                    e.operatorOverride(ch, db, t)
                                    lastSent.remove(ch)
                                }
                            }
                        // The same argument for channel processing: an EQ
                        // band or a compressor setting arriving here is
                        // somebody at the desk disagreeing with the chain
                        // we set. That parameter is theirs from now on —
                        // a re-treat will skip it rather than argue.
                        if (com.stagemix.engine.isSafeAddress(m.address))
                            Regex("^/ch/(\\d\\d)/").find(m.address)
                                ?.let { match ->
                                val ch = match.groupValues[1].toInt() - 1
                                val ours = lastParam[m.address]
                                if (ours == null || abs(v - ours) > 0.005f)
                                    e.treatmentOverride(ch, m.address)
                            }
                    }
                }
            }
        }
    }

    private fun publishStrips(t: Double) {
        val e = engine ?: return
        AppState.strips.value = AppState.config.value.channels.map { ch ->
            val st = e.state[ch.index]
            val tone = doctor?.offsets(ch.index)
            val id = e.channelIdent(ch.index)
            AppState.StripUi(
                channel = ch.index,
                name = AppState.mixerChannelNames.value[ch.index] ?: ch.name,
                role = st?.role ?: ch.role,
                levelDb = st?.lastLevelDb ?: -128f,
                active = st?.active ?: false,
                frozen = st?.frozen ?: false,
                offsetDb = e.offsetDb(ch.index),
                targetDb = e.targetDb(ch.index),
                eqOffsetDb = tone?.first?.maxByOrNull { kotlin.math.abs(it) } ?: 0f,
                thrOffsetDb = tone?.second ?: 0f,
                identLabel = id?.label ?: "",
                identHeard = id?.heard ?: false,
                identEvidence = id?.evidence ?: 0f,
            )
        }
        AppState.snapshotTaken.value = e.ready
        AppState.health.value = e.health()
    }

    // ------------------------------------------------------------------
    /** Read the console's channel & bus names (nice-to-have, best effort). */
    private suspend fun fetchNames() {
        val names = HashMap<Int, String>()
        for (ch in 0 until 16) send(
            OscMessage(osc("/ch/%02d/config/name", ch + 1), emptyList()))
        for (b in 0 until 6) send(
            OscMessage(osc("/bus/%d/config/name", b + 1), emptyList()))
        val stop = now() + 2.0
        val busNames = HashMap<Int, String>()
        while (now() < stop) {
            val m = receiveOnce() ?: continue
            val name = m.stringArg(0) ?: continue
            Regex("/ch/(\\d+)/config/name").find(m.address)?.let {
                if (name.isNotBlank())
                    names[it.groupValues[1].toInt() - 1] = name
            }
            Regex("/bus/(\\d+)/config/name").find(m.address)?.let {
                if (name.isNotBlank())
                    busNames[it.groupValues[1].toInt() - 1] = name
            }
        }
        if (names.isNotEmpty()) AppState.mixerChannelNames.value = names
        if (busNames.isNotEmpty()) AppState.busNames.value = busNames
        // Automatic balance-ladder roles from the console's own channel
        // names ("Kick", "SynBass", "Piano", "Sax", "BVox"...). Manual
        // overrides (non-INSTRUMENT in config) are respected.
        val e = engine ?: return
        for ((ch, name) in names) {
            // the desk's label, unconditionally: even a hand-pinned role
            // deserves to be reasoned about under the name on the console
            e.setChannelName(ch, name)
            val cfgRole = AppState.config.value.channels
                .firstOrNull { it.index == ch }?.role
            if (cfgRole == null || cfgRole == com.stagemix.engine.Role.INSTRUMENT) {
                val r = com.stagemix.engine.inferRole(name)
                // setRoleFromName, not setRole: a name is a starting
                // guess, and locking the role to it would switch off the
                // listener that exists to second-guess exactly this.
                e.setRoleFromName(ch, r)
                doctor?.setRole(ch, r)
            }
        }
    }

    /**
     * Takeover (no soundcheck ritual): read the CURRENT channel fader
     * positions — they become the autopilot's authority bounds — plus
     * the current EQ/comp settings as the doctor's anchors. Monitor
     * buses are never read for automation and never written, period.
     */
    private suspend fun takeoverNow() = takeoverLock.withLock {
        // Serialized: two takeovers racing (flip MIXING on while a
        // re-baseline is in flight) both cleared `pending` and both
        // flipped `collecting`, so one of them built an empty map and
        // reported "no fader positions received" with the console
        // answering perfectly.
        val e = engine ?: return@withLock
        collecting = true          // our own enquiry replies are NOT
        pending.clear()            // human fader moves

        val chans = AppState.config.value.channels
        fun enquire(ch: Int) {
            send(OscMessage(osc("/ch/%02d/mix/fader", ch + 1), emptyList()))
            for (b in 1..4)
                send(OscMessage(osc("/ch/%02d/eq/%d/g", ch + 1, b),
                    emptyList()))
            send(OscMessage(osc("/ch/%02d/dyn/thr", ch + 1), emptyList()))
        }
        // Paced, not fired as one 96-packet burst: a burst that big is
        // routinely clipped by the console's receive buffer or the
        // tablet's Wi-Fi, and every dropped reply is a channel the
        // autopilot then leaves unmanaged all night.
        for (ch in chans) { enquire(ch.index); delay(3) }
        withTimeoutOrNull(3000) {
            while (chans.any {
                    !pending.containsKey(
                        osc("/ch/%02d/mix/fader", it.index + 1)) })
                delay(50)
        }
        // one retry pass for whatever did not answer
        val missing = chans.filter {
            !pending.containsKey(osc("/ch/%02d/mix/fader", it.index + 1)) }
        if (missing.isNotEmpty()) {
            for (ch in missing) { enquire(ch.index); delay(3) }
            withTimeoutOrNull(1500) {
                while (missing.any {
                        !pending.containsKey(
                            osc("/ch/%02d/mix/fader", it.index + 1)) })
                    delay(50)
            }
        }
        val faders = HashMap<Int, Float>()
        for (ch in chans) {
            pending[osc("/ch/%02d/mix/fader", ch.index + 1)]
                ?.let { faders[ch.index] = FaderLaw.floatToDb(it) }
        }
        if (faders.isEmpty()) {
            collecting = false
            AppState.lastError.value =
                "Takeover failed — no fader positions received from the mixer"
            return@withLock
        }
        // A PARTIAL takeover is not a success. Channels with no fader
        // reading get no baseline, which means the engine skips them in
        // every branch for the rest of the night — silently, while the
        // console log says takeover worked.
        if (faders.size < chans.size) {
            val silent = chans.filter { it.index !in faders.keys }
            show?.net("PARTIAL TAKEOVER: only ${faders.size}/${chans.size} " +
                "faders answered; " + silent.joinToString(",") {
                    "ch%02d".format(java.util.Locale.ROOT, it.index + 1) } +
                " are NOT being mixed")
            AppState.lastError.value =
                "Only ${faders.size} of ${chans.size} faders answered — " +
                silent.joinToString(", ") { "ch%02d".format(it.index + 1) } +
                " are NOT being mixed. Tap MIXING again to retry."
        }
        e.takeover(faders, now())
        show?.takeover(faders, AppState.mixerChannelNames.value)
        lastSent.clear()
        lastParam.clear()
        collecting = false
        doctor?.let { d ->
            for (ch in chans) {
                val gains = FloatArray(4) { b ->
                    pending[osc("/ch/%02d/eq/%d/g", ch.index + 1, b + 1)]
                        ?.let { it * 30f - 15f } ?: 0f
                }
                val haveEq = (0 until 4).any {
                    pending.containsKey(
                        osc("/ch/%02d/eq/%d/g", ch.index + 1, it + 1))
                }
                val thr = pending[osc("/ch/%02d/dyn/thr", ch.index + 1)]
                    ?.let { it * 60f - 60f }
                d.snapshotChannel(ch.index,
                    if (haveEq) gains else null, thr)
            }
        }
        publishStrips(now())
    }

    private fun revert() {
        val e = engine ?: return
        // handing back means handing back: pause the autopilot too, or
        // the next tick would immediately mix away from these faders
        AppState.directing.value = false
        show?.user("you handed the mains back — restoring the takeover " +
            "faders and pausing for ${REVERT_HOLD_SEC.toInt()}s")
        for (w in e.revertToBaseline(now())) sendFader(w.channel, w.levelDb)
        doctor?.let { d ->
            for (ch in d.state.keys)
                for (w in d.reset(ch)) send(OscMessage(w.address, listOf(w.value)))
        }
    }

    /**
     * Write a channel fader and remember what we asked for. The echo
     * filter in [handle] needs that memory: on firmware that reflects
     * parameter changes back to the sender (or if `/xremotenfb` is not
     * honoured), our own writes arrive looking exactly like a human on
     * the console — and every one of them used to hand that channel to
     * "the human" for two minutes. Sixteen writes, sixteen channels
     * frozen, autopilot dead twenty-five seconds after takeover.
     */
    /** the console's name for a channel, falling back to the profile */
    private fun chName(ch: Int): String =
        AppState.mixerChannelNames.value[ch]
            ?: AppState.config.value.channels.firstOrNull { it.index == ch }
                ?.name ?: "ch%02d".format(java.util.Locale.ROOT, ch + 1)

    /**
     * Explain a Channel Doctor write in the log: which band moved, how
     * far the channel's tone had drifted from the sound the operator
     * approved, and — for the compressor — the gain reduction it is
     * trying to restore.
     */
    private fun logDoctorWrite(d: ToneDoctor, w: com.stagemix.engine.ParamWrite) {
        val lg = show ?: return
        val m = Regex("^/ch/(\\d\\d)/(eq/(\\d)/g|dyn/thr)$").find(w.address)
            ?: return
        val ch = m.groupValues[1].toInt() - 1
        val st = d.state[ch] ?: return
        if (m.groupValues[3].isNotEmpty()) {
            val band = m.groupValues[3].toInt() - 1
            val live = st.liveBands; val ref = st.refBands
            val drift = if (live != null && ref != null) live[band] - ref[band]
                        else 0f
            lg.eq(ch, band, w.value * 30f - 15f, drift, chName(ch))
        } else {
            lg.comp(ch, w.value * 60f - 60f, st.grEma, st.refGr, chName(ch))
        }
    }

    private fun sendFader(ch: Int, db: Float) {
        lastSent[ch] = db
        show?.fader(ch, db, chName(ch))
        send(OscMessage(osc("/ch/%02d/mix/fader", ch + 1),
            listOf(FaderLaw.dbToFloat(db))))
    }

    // ------------------------------------------------------------------
    private fun send(m: OscMessage) {
        val s = socket ?: return
        val a = mixerAddr ?: return
        try {
            val b = m.encode()
            s.send(DatagramPacket(b, b.size, a))
        } catch (e: Exception) {
            Log.w(TAG, "send failed: ${e.message}")
        }
    }

    private fun receiveOnce(): OscMessage? {
        val s = socket ?: return null
        return try {
            val buf = ByteArray(4096)
            val p = DatagramPacket(buf, buf.size)
            s.receive(p)
            OscMessage.decode(buf.copyOf(p.length))
        } catch (e: Exception) {
            null // timeout — normal
        }
    }

    private fun now(): Double = System.nanoTime() / 1e9

    // ------------------------------------------------------------------
    private fun acquireLocks() {
        val wm = applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
        wifiLock = wm.createWifiLock(
            WifiManager.WIFI_MODE_FULL_LOW_LATENCY, "stagemix:wifi").apply { acquire() }
        val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
        wakeLock = pm.newWakeLock(
            PowerManager.PARTIAL_WAKE_LOCK, "stagemix:engine").apply {
            setReferenceCounted(false); acquire()
        }
    }

    private fun startForegroundNotif() {
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel(
            CHANNEL, getString(R.string.svc_channel),
            NotificationManager.IMPORTANCE_LOW))
        val notif = Notification.Builder(this, CHANNEL)
            .setSmallIcon(android.R.drawable.ic_media_play)
            .setContentTitle(getString(R.string.app_name))
            .setContentText(getString(R.string.svc_running))
            .setOngoing(true)
            .build()
        if (Build.VERSION.SDK_INT >= 29) {
            startForeground(1, notif,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE)
        } else {
            startForeground(1, notif)
        }
    }

    private fun shutdown() {
        // the night ends: bank what we learned + how it went
        engine?.let { e ->
            AppState.saveBias(this, e.pyramidBias)
            val h = e.health()
            if (h.ticks > 600) AppState.saveNight(this, h)  // >10 min mixed
            show?.footer(e)
        }
        show?.close()
        AppState.conn.value = AppState.Conn.DISCONNECTED
        AppState.directing.value = false
        loopJob?.cancel()
        socket?.close(); socket = null
        wifiLock?.let { if (it.isHeld) it.release() }
        wakeLock?.let { if (it.isHeld) it.release() }
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    override fun onDestroy() {
        shutdown()
        super.onDestroy()
    }

    companion object {
        private const val TAG = "StageMix"
        /**
         * How far an incoming fader value may sit from what we last
         * wrote and still be our own echo rather than a human. The
         * console quantizes faders to a 1024-step float, which is about
         * 0.04 dB where the engine works — a tenth of a dB is comfortably
         * above the wire's noise and far below any real fader move.
         */
        private const val ECHO_TOL_DB = 0.1f
        const val PORT = 10024
        const val CHANNEL = "stagemix"
        const val ACTION_CONNECT = "com.stagemix.CONNECT"
        const val ACTION_DISCONNECT = "com.stagemix.DISCONNECT"
        const val ACTION_SNAPSHOT = "com.stagemix.SNAPSHOT"
        const val ACTION_REVERT = "com.stagemix.REVERT"
        const val ACTION_DIRECTING = "com.stagemix.DIRECTING"
        const val ACTION_FREEZE_ALL = "com.stagemix.FREEZE_ALL"
        const val ACTION_FREEZE_CH = "com.stagemix.FREEZE_CH"
        const val ACTION_DOCTOR = "com.stagemix.DOCTOR"
        const val ACTION_FEEDBACK = "com.stagemix.FEEDBACK"

        fun cmd(ctx: Context, action: String, vararg extras: Pair<String, Any>) {
            val i = Intent(ctx, MixerService::class.java).setAction(action)
            for ((k, v) in extras) when (v) {
                is String -> i.putExtra(k, v)
                is Boolean -> i.putExtra(k, v)
                is Int -> i.putExtra(k, v)
            }
            if (action == ACTION_CONNECT) ctx.startForegroundService(i)
            else ctx.startService(i)
        }
    }
}
