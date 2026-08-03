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
import com.stagemix.engine.OscMessage
import com.stagemix.engine.StageEngine
import com.stagemix.engine.ToneDoctor
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.InetSocketAddress
import java.util.concurrent.ConcurrentHashMap

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
    private var wifiLock: WifiManager.WifiLock? = null
    private var wakeLock: PowerManager.WakeLock? = null
    private var loopJob: Job? = null

    /** parameter enquiry replies parked here by address */
    private val pending = ConcurrentHashMap<String, Float>()

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_CONNECT -> {
                startForegroundNotif()
                acquireLocks()
                connect(intent.getStringExtra("ip") ?: return START_NOT_STICKY)
            }
            ACTION_SNAPSHOT -> scope.launch { takeSnapshot() }
            ACTION_REVERT -> scope.launch { revert() }
            ACTION_DIRECTING -> AppState.directing.value =
                intent.getBooleanExtra("on", false)
            ACTION_FREEZE_ALL -> {
                val on = intent.getBooleanExtra("on", true)
                engine?.frozenAll = on
                AppState.frozenAll.value = on
            }
            ACTION_FREEZE_CH -> {
                val ch = intent.getIntExtra("ch", -1)
                val on = intent.getBooleanExtra("on", true)
                engine?.freezeChannel(ch, on)
                doctor?.state?.get(ch)?.frozen = on
            }
            ACTION_DOCTOR -> AppState.doctorOn.value =
                intent.getBooleanExtra("on", true)
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
                engine = StageEngine(cfg.channels, cfg.buses)
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
                    AppState.conn.value = AppState.Conn.DISCONNECTED
                    AppState.lastError.value =
                        "No mixer answered at $ip:$PORT — check Wi-Fi/IP"
                    return@launch
                }
                AppState.conn.value = AppState.Conn.CONNECTED
                AppState.config.value = cfg.copy(mixerIp = ip)
                fetchNames()
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
                send(OscMessage("/meters", listOf("/meters/4")))  // RTA
                send(OscMessage("/meters", listOf("/meters/6")))  // dynamics
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
                if (directing && e.snapshotTaken) {
                    for (w in e.tick(t)) {
                        send(OscMessage(w.address,
                            listOf(FaderLaw.dbToFloat(w.levelDb))))
                    }
                } else {
                    e.tick(t) // keep state warm; writes discarded when paused
                }
                doctor?.let { d ->
                    if (directing && AppState.doctorOn.value) {
                        for (w in d.tick(e.activeChannels(),
                                upAllowed = e.boostsAllowed(t),
                                frozenAll = e.frozenAll)) {
                            send(OscMessage(w.address, listOf(w.value)))
                        }
                    }
                }
                publishStrips(t)
                AppState.decisions.value = e.decisions.toList()
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
            "/meters/4" -> {
                // 100-bin RTA — attribute to the focused channel once the
                // analyzer has had a moment to settle on it
                if (rtaFocus >= 0 && t - rtaFocusT > 0.5) {
                    m.blobArg(0)?.let { Meters.decode(it) }?.let { bins ->
                        doctor?.onRta(rtaFocus, bins, t)
                    }
                }
            }
            "/meters/6" -> {
                // dynamics bank: assumed layout [gate GR, comp GR] per
                // channel (verify against your firmware — the doctor's
                // sanity gates discard implausible values either way)
                m.blobArg(0)?.let { Meters.decode(it) }?.let { v ->
                    if (v.size >= 32) for (ch in 0 until 16)
                        doctor?.onGainReduction(ch, v[ch * 2 + 1], t)
                }
            }
            else -> {
                // parameter enquiry replies / other-client changes
                (m.args.firstOrNull() as? Float)?.let { pending[m.address] = it }
            }
        }
    }

    private fun publishStrips(t: Double) {
        val e = engine ?: return
        val viewBus = e.buses.firstOrNull()?.index ?: 0
        AppState.strips.value = AppState.config.value.channels.map { ch ->
            val st = e.state[ch.index]
            val tone = doctor?.offsets(ch.index)
            AppState.StripUi(
                channel = ch.index,
                name = AppState.mixerChannelNames.value[ch.index] ?: ch.name,
                role = st?.role ?: ch.role,
                levelDb = st?.lastLevelDb ?: -128f,
                active = st?.active ?: false,
                frozen = st?.frozen ?: false,
                offsetDb = e.offsetDb(ch.index, viewBus),
                targetDb = e.targetDb(ch.index, viewBus),
                eqOffsetDb = tone?.first?.maxByOrNull { kotlin.math.abs(it) } ?: 0f,
                thrOffsetDb = tone?.second ?: 0f,
            )
        }
        AppState.snapshotTaken.value = e.snapshotTaken
    }

    // ------------------------------------------------------------------
    /** Read the console's channel & bus names (nice-to-have, best effort). */
    private suspend fun fetchNames() {
        val names = HashMap<Int, String>()
        for (ch in 0 until 16) send(
            OscMessage("/ch/%02d/config/name".format(ch + 1), emptyList()))
        for (b in 0 until 6) send(
            OscMessage("/bus/%d/config/name".format(b + 1), emptyList()))
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
            val cfgRole = AppState.config.value.channels
                .firstOrNull { it.index == ch }?.role
            if (cfgRole == null || cfgRole == com.stagemix.engine.Role.INSTRUMENT) {
                val r = com.stagemix.engine.inferRole(name)
                e.setRole(ch, r)
                doctor?.setRole(ch, r)
            }
        }
    }

    /**
     * Soundcheck snapshot: enquire every managed send's current level,
     * then hand the map to the engine as the reference mix.
     */
    private suspend fun takeSnapshot() {
        val e = engine ?: return
        pending.clear()
        val wanted = HashMap<String, Pair<Int, Int>>()
        val chans = AppState.config.value.channels
        for (ch in chans) for (b in e.buses) {
            val addr = "/ch/%02d/mix/%02d/level".format(ch.index + 1, b.index + 1)
            wanted[addr] = ch.index to b.index
            send(OscMessage(addr, emptyList()))
        }
        // doctor anchors: current EQ band gains + comp threshold
        for (ch in chans) {
            for (b in 1..4)
                send(OscMessage("/ch/%02d/eq/%d/g".format(ch.index + 1, b),
                    emptyList()))
            send(OscMessage("/ch/%02d/dyn/thr".format(ch.index + 1),
                emptyList()))
        }
        withTimeoutOrNull(3000) {
            while (pending.size < wanted.size) delay(50)
        }
        val sends = HashMap<Pair<Int, Int>, Float>()
        for ((addr, key) in wanted) {
            pending[addr]?.let { sends[key] = FaderLaw.floatToDb(it) }
        }
        if (sends.isEmpty()) {
            AppState.lastError.value =
                "Snapshot failed — no send levels received from the mixer"
            return
        }
        e.takeSnapshot(sends, now())
        doctor?.let { d ->
            for (ch in chans) {
                val gains = FloatArray(4) { b ->
                    pending["/ch/%02d/eq/%d/g".format(ch.index + 1, b + 1)]
                        ?.let { it * 30f - 15f } ?: 0f
                }
                val haveEq = (0 until 4).any {
                    pending.containsKey(
                        "/ch/%02d/eq/%d/g".format(ch.index + 1, it + 1))
                }
                val thr = pending["/ch/%02d/dyn/thr".format(ch.index + 1)]
                    ?.let { it * 60f - 60f }
                d.snapshotChannel(ch.index,
                    if (haveEq) gains else null, thr)
            }
        }
        publishStrips(now())
    }

    private fun revert() {
        val e = engine ?: return
        for (w in e.revertToSnapshot(now()))
            send(OscMessage(w.address, listOf(FaderLaw.dbToFloat(w.levelDb))))
        doctor?.let { d ->
            for (ch in d.state.keys)
                for (w in d.reset(ch)) send(OscMessage(w.address, listOf(w.value)))
        }
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
