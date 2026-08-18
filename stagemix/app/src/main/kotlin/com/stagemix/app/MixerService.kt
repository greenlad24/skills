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
import com.stagemix.engine.EngineSettings
import com.stagemix.engine.RESEARCH_PYRAMID
import com.stagemix.engine.StageEngine
import com.stagemix.engine.ToneDoctor
import kotlinx.coroutines.CoroutineExceptionHandler
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.cancelChildren
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

    /**
     * When this service started. Declared FIRST on purpose — see [now].
     *
     * `now()` was `System.nanoTime() / 1e9`, whose origin is arbitrary:
     * on Android it is time since the device booted. A tablet that had
     * been awake for a day handed the engine a first timestamp of about
     * 96 000, and every "how long has this been quiet for" question in
     * there is `now - lastActiveT` against a field that starts at zero.
     * So on the first pass every channel had been silent for twenty-six
     * hours, and sixty seconds into the night the engine took seven
     * channels out of the mains at once — one of them a singer's
     * microphone, logged as "not an instrument — hum or an open mic
     * nobody is using". The lead vocal never fully came back.
     *
     * The bench never showed it: the desk client subtracts its own `t0`
     * and hands the engine a clock that starts at zero. Same engine,
     * same night, different answer — exactly the class of bug the Mac
     * cannot catch. It starts at zero here too now, and it is declared
     * above every other property so that no initializer can run before
     * it and reintroduce the same thing by the back door.
     */
    private val t0 = System.nanoTime()

    // A FAILURE IN A LAUNCHED COROUTINE MUST NOT KILL THE APP. The tick
    // loop guards itself, but the takeover coroutine (scope.launch {
    // takeoverNow() }) ran on a scope with no handler — so any throwable it
    // hit against a live console went straight to Android's default handler
    // and crashed the process. On a real mixer, mid-show. This routes every
    // uncaught coroutine failure — Exception or Error — into the same
    // fail-safe path the loop uses: log it, show it, hold the last mix.
    private val scope = CoroutineScope(
        SupervisorJob() + Dispatchers.IO +
        CoroutineExceptionHandler { _, ex -> engineFailed(ex) })
    private var socket: DatagramSocket? = null
    private var mixerAddr: InetSocketAddress? = null
    private var engine: StageEngine? = null
    private var doctor: ToneDoctor? = null
    private val watchdog = com.stagemix.engine.FeedbackWatchdog()
    /** ringing the stage out: a narrow cut on the mic that is howling */
    private val ringOut = com.stagemix.engine.RingOut()
    /** what is in each wedge — read and understood */
    private val monitors = com.stagemix.engine.MonitorMap()
    /** and the half that corrects one, slightly, cut-first */
    private val monBal = com.stagemix.engine.MonitorBalance(monitors)
    /** when the wedge sends were last re-read, to notice a hand on one */
    private var sendsReadT = -1e9
    private var lastVeto = false
    private var wifiLock: WifiManager.WifiLock? = null

    /**
     * THE MIXER'S WI-FI HAS NO INTERNET, AND ANDROID HATES THAT.
     *
     * At a venue the tablet is on the M18's own access point and nothing
     * else. Android decides within seconds that such a network is
     * useless — it shows "Wi-Fi has no internet access", and if there is
     * ANY cellular data it quietly routes the process's traffic out the
     * mobile interface instead. The app then sends its OSC into a phone
     * network and never reaches the console standing next to it, while
     * the Wi-Fi icon sits there looking connected. On some builds the
     * system goes further and drops the network to "avoid poor
     * connections".
     *
     * The cure is to ask for exactly the network we want and pin our
     * sockets to it: TRANSPORT_WIFI, and deliberately WITHOUT
     * NET_CAPABILITY_INTERNET, because not having internet is the whole
     * point of this one. Holding the request open also tells the system
     * somebody is using the network, so it stops trying to tidy it away.
     */
    private var wifiNetwork: android.net.Network? = null
    private var netCallback: android.net.ConnectivityManager.NetworkCallback? = null
    private var wakeLock: PowerManager.WakeLock? = null
    private var loopJob: Job? = null
    // RTA frames in since the last source switch. It is reset in runLoop
    // (on a source change) but read/incremented in handle(), which is a
    // class method and cannot see runLoop's locals — so it lives here.
    // The first frame after a switch can still be the PREVIOUS channel's
    // spectrum (the console has not swapped yet), and RingOut keeps a
    // per-channel max at the ring frequency, so one stale loud frame
    // would permanently inflate an innocent channel's reading and could
    // point the notch at the wrong mic. Drop that first frame.
    private var rtaFramesSinceSwitch = 0
    /** engine exceptions survived this session — see the tick guard */
    private var tickFailures = 0
    /** last time the full monitor matrix was written to the log */
    private var lastMonMatrix = -1e9
    /** the feedback profile carried in from earlier nights (ch, Hz, rings) */
    private var carriedFeedback: List<Triple<Int, Float, Int>> = emptyList()
    /** the exact banner engineFailed raises, so a clean tick can retract it */
    private val ENGINE_ERROR_MSG =
        "⚠ Something went wrong inside the app — the mixer is " +
        "holding your last mix. Export the log."
    /** the worst fault last written to the log, so it is not repeated */
    private var lastAdviceKey = ""
    /**
     * When a meter frame last arrived, as a field rather than a local.
     *
     * The adviser needs it — "meters have stopped" is one of the faults
     * it reports — and it runs from publishStrips, outside the loop
     * where the local lives.
     */
    @Volatile private var lastRxT = 0.0
    /** the last thing the ring-out said, so it is logged once */
    private var lastRingAction = ""

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
            ACTION_SNAPSHOT -> {
                if (engine == null) noEngine("RE-BASELINE")
                else {
                    show?.user("you pressed RE-BASELINE — reading the " +
                        "desk again and making the current faders the " +
                        "new centre of the app's authority")
                    scope.launch { takeoverNow() }
                }
            }
            ACTION_REVERT -> scope.launch { revert() }
            ACTION_DIRECTING -> {
                val on = intent.getBooleanExtra("on", false)
                AppState.directing.value = on
                show?.user(if (on) "you switched MIXING ON"
                           else "you switched MIXING OFF (shadow mode)")
                show?.mark(if (on) "MIXING ON" else "MIXING OFF",
                    if (on) "the app has the mains"
                    else "you have the mains; the app is only watching",
                    now())
                // Switching it back on is the operator saying "try
                // again": start the error count from zero, or the next
                // single exception trips a limit that was reached an
                // hour ago and switches them straight off again.
                if (on) {
                    tickFailures = 0
                    AppState.mixingSinceMs.value =
                        android.os.SystemClock.elapsedRealtime()
                    scope.launch { takeoverNow() }
                }
                updateNotif()
            }
            ACTION_FREEZE_ALL -> {
                val on = intent.getBooleanExtra("on", true)
                engine?.frozenAll = on
                AppState.frozenAll.value = on
                updateNotif()
                show?.user(if (on) "you pressed FREEZE ALL"
                           else "you released FREEZE ALL")
            }
            ACTION_SET_ROLE -> {
                val ch = intent.getIntExtra("ch", -1)
                val name = intent.getStringExtra("role") ?: return START_NOT_STICKY
                val role = runCatching {
                    com.stagemix.engine.Role.valueOf(name) }.getOrNull()
                    ?: return START_NOT_STICKY
                (engine ?: run { noEngine("Instrument change"); null })?.let { e ->
                    e.setRole(ch, role)
                    doctor?.setRole(ch, role)
                    AppState.saveKnownInstruments(this, e.knownInstruments)
                    show?.user(("you said ch%02d %s is %s — remembered for " +
                        "that channel name from now on").format(
                            java.util.Locale.ROOT, ch + 1,
                            e.state[ch]?.name ?: "", role.name.lowercase()))
                }
            }
            ACTION_KEEP_BALANCE -> (engine ?: run { noEngine("KEEP"); null })?.let { e ->
                val n = e.adoptBalance(now())
                AppState.saveLearnedBalance(this, e.learned.snapshot())
                show?.user(if (n > 0)
                    "you pressed KEEP THIS BALANCE — $n channels held; " +
                    "learned from ${e.learned.kept} balances so far"
                    else "you pressed KEEP THIS BALANCE, but nothing is playing")
            }
            // REBALANCE: one deliberate pass over both mixes.
            //
            // The mains get re-laddered against the balance being
            // defended. The wedges get a push pass — a few moves per
            // bus at double the usual step instead of one — still
            // inside every night-long total, still cut-first, still
            // silent between songs and still refusing any bus the
            // engineer has a hand on. A button press is permission to
            // act now; it is not permission to act differently.
            ACTION_REBALANCE -> (engine ?: run { noEngine("RE-BALANCE"); null })?.let { e ->
                val t = now()
                e.rebalance(t)
                show?.user("you pressed REBALANCE — re-laddering the " +
                    "mains and taking one pass at the wedges")
                if (AppState.keepMonitors.value && AppState.directing.value &&
                    !e.frozenAll) {
                    // ON THE IO SCOPE, NOT HERE. onStartCommand runs on
                    // the main thread, and a DatagramSocket.send() from
                    // the main thread throws NetworkOnMainThreadException
                    // on this targetSdk — which send() then swallowed
                    // into a log line. The keeper had already banked
                    // every move, so the screen and the show log both
                    // reported wedge corrections that never left the
                    // tablet, and the night's authority was spent on
                    // nothing. FREEZE and the listen window are checked
                    // here too: the tick path always honoured them and
                    // this path did not, so the panic button did not
                    // stop the one control that reaches a musician's ears.
                    scope.launch {
                        // POLL, WAIT, THEN PLAN. The send levels may be
                        // up to 25s stale, so a hand on a wedge in that
                        // window would be invisible and the push would
                        // fight it. Read the desk first, give the replies
                        // a moment to land in handle(), then plan against
                        // what is actually there.
                        pollSends()
                        delay(400)
                        applyMonitorPlan(monBal.plan(
                            tSec = now(),
                            roles = e.state.mapValues { it.value.role },
                            kit = e.drumKit(),
                            playing = !e.betweenSongs && e.ready,
                            push = true,
                            feedbackActive = ringOut.hunting || e.watchdogVeto),
                            now())
                    }
                } else if (!AppState.keepMonitors.value) {
                    show?.user("(monitor keeping is off, so only the " +
                        "mains were rebalanced)")
                }
            }
            ACTION_KEEP_MONITORS -> {
                val on = intent.getBooleanExtra("on", true)
                AppState.keepMonitors.value = on
                AppState.saveSwitches(this)
                show?.user("you turned monitor keeping " +
                    (if (on) "ON — wedges may be corrected slightly, " +
                        "cut-first, never against your hand"
                     else "OFF — the wedges are untouched"))
            }
            ACTION_AUTO_START -> {
                val on = intent.getBooleanExtra("on", true)
                AppState.autoStart.value = on
                AppState.saveSwitches(this)
                show?.user("you turned auto-start " +
                    (if (on) "ON — it connects and mixes on its own"
                     else "OFF — it will wait for you to tap MIX"))
            }
            ACTION_PRE_RING -> {
                val on = intent.getBooleanExtra("on", true)
                AppState.preRing.value = on
                AppState.saveSwitches(this)
                show?.user("you turned pre-ring " +
                    (if (on) "ON — at takeover it puts a shallow guard cut " +
                        "on frequencies this rig has howled at before, so the " +
                        "recurring monitor feedback is pre-empted"
                     else "OFF — feedback is still learned and logged, but " +
                        "nothing is pre-cut"))
                // apply/remove takes effect at the next takeover; if already
                // mixing, place them now so the operator sees it act
                if (on && engine?.let { it.takeoverT >= 0 } == true) preRingSetup()
            }
            ACTION_MONITOR_INEARS -> {
                val bus = intent.getIntExtra("bus", -1)
                val inEars = intent.getBooleanExtra("inEars", true)
                if (bus >= 1) {
                    AppState.monitorInEars.value =
                        AppState.monitorInEars.value + (bus to inEars)
                    AppState.saveSwitches(this)
                    monitors.setInEars(bus, inEars)
                    show?.user("you set the ${monitors.wedge(bus)?.name ?: "bus $bus"} " +
                        "monitor to ${if (inEars) "IN-EARS — it wants the whole " +
                        "mix, kit included" else "a FLOOR WEDGE — the band in " +
                        "front of it, vocals on top, kit not on top"}")
                }
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
                (engine ?: run { noEngine("Taste"); null })?.let { e ->
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
                // the broadcast has to go out the console's own AP too,
                // or it is shouted at a phone network that cannot hear it
                bindSocket(s)
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
        // Idempotent: the two auto-connect call sites (MainActivity and
        // the console's LaunchedEffect) can both fire on launch, and a
        // second CONNECT while the first is in flight used to cancel the
        // loop and rebuild the engine and show log — losing the night's
        // baselines. If a connection is already up or coming up, ignore.
        if (loopJob?.isActive == true &&
            AppState.conn.value != AppState.Conn.DISCONNECTED) return
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
                bindSocket(s)
                socket = s
                mixerAddr = InetSocketAddress(InetAddress.getByName(ip), PORT)

                val cfg = AppState.config.value
                show?.close()
                show = ShowLog(getExternalFilesDir(null) ?: filesDir)
                AppState.logPath.value = show?.file?.absolutePath ?: ""
                engine = StageEngine(cfg.channels,
                    EngineSettings(operatorPolicy = true),
                    RESEARCH_PYRAMID).also { eng ->
                    // CONTINUE FROM LAST NIGHT'S PROGRESS — through the
                    // front door.
                    //
                    // This used to `putAll` into `pyramidBias`, which is
                    // the OUTPUT of the taste calculation, not its
                    // input. `chipBias` — what the feedback chips
                    // actually accumulate into — was left empty, so the
                    // first chip press of the night computed 0 + 1 and
                    // overwrote everything the app had learned. On the
                    // night this was found, the operator's one explicit
                    // instruction all evening was "more vocal", and it
                    // took the lead vocal from +3.0 dB to +1.0.
                    eng.loadBias(AppState.loadBias(this@MixerService))
                    // and from everything the operator has ever told us
                    // is on a channel — the calls the audio cannot make
                    eng.knownInstruments.putAll(
                        AppState.loadKnownInstruments(this@MixerService))
                    // and the balance they keep arriving at
                    eng.learned.restore(
                        AppState.loadLearnedBalance(this@MixerService))
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
                // The console has answered at least once this session.
                // This gates every "the mixer is gone" surface (opState's
                // NO_MIXER, the lost-mixer advice) — and it must be set on
                // the FIRST connect, not only after a dropout→recovery, or
                // the very first mid-show disconnect reads as "still
                // mixing" over a dead console.
                AppState.everConnected.value = true
                AppState.config.value = cfg.copy(mixerIp = ip)
                fetchNames()
                engine?.let { eng ->
                    val mi = AppState.mixer.value
                    show?.head("name='${mi.name}' model='${mi.model}' " +
                        "fw='${mi.firmware}' ip=${mi.ip}", eng,
                        AppState.mixerChannelNames.value,
                        AppState.nightsCount.value,
                        AppState.tasteSummary.value,
                        build = "${BuildConfig.GIT_SHA} " +
                            "(built ${BuildConfig.BUILT_AT}, " +
                            "v${BuildConfig.VERSION_NAME})")
                }
                show?.net("connected to $ip:$PORT — meters and RTA " +
                    "subscribed, offline on the mixer's own Wi-Fi")
                // AND START MIXING, WITHOUT BEING ASKED.
                //
                // The app used to come up watching and wait to be
                // armed. It was never armed, for three shows, and
                // nothing said so. Taking the mains is now the default
                // and NOT taking them is the thing that has to be
                // chosen — with the twenty-second listen still in front
                // of every fader it writes, and one tap to hand them
                // back.
                if (AppState.autoStart.value &&
                    (!AppState.directing.value ||
                     (engine?.takeoverT ?: -1.0) < 0.0)) {
                    AppState.directing.value = true
                    tickFailures = 0
                    AppState.mixingSinceMs.value =
                        android.os.SystemClock.elapsedRealtime()
                    show?.mark("MIXING ON",
                        "auto-start: the app took the mains as soon as it " +
                        "found the desk — it listens for " +
                        "${engine?.settings?.learnSec?.toInt() ?: 20}s " +
                        "before it writes anything", now())
                    scope.launch { takeoverNow() }
                    updateNotif()
                } else if (AppState.directing.value &&
                           (engine?.takeoverT ?: -1.0) < 0.0) {
                    // Leftover directing from a previous session, but
                    // auto-start is off, so nothing armed the takeover.
                    // Claiming MIXING with nothing mixed is exactly the
                    // status-lie §5 forbids — so pause instead and let
                    // the operator tap MIX when they mean it.
                    AppState.directing.value = false
                    AppState.mixingSinceMs.value = 0L
                    updateNotif()
                }
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
        var lastRx = now(); lastRxT = lastRx
        var rtaFocus = -1
        var rtaFocusT = 0.0
        var lastResync = 0.0
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
            // ASK AGAIN, ALL NIGHT.
            //
            // Two things drift out of sync over UDP on a busy AP, and
            // both did, for hours:
            //
            //  · A channel whose fader position was lost at takeover has
            //    no baseline, so it is skipped everywhere. Re-asking is
            //    the only way back in, and it costs one packet.
            //  · The mute keys. They are pushed to us when they change,
            //    and a pushed packet that goes missing is gone for good
            //    — leaving the engine mixing a channel the operator has
            //    switched off, or leaving a channel alone that they
            //    switched back on. Re-reading them costs sixteen small
            //    packets a minute and removes the whole failure mode.
            if (AppState.directing.value && t - lastResync > RESYNC_SEC) {
                lastResync = t
                for (ch in engine?.unmanagedChannels().orEmpty()) {
                    send(OscMessage(osc("/ch/%02d/mix/fader", ch + 1),
                        emptyList()))
                    delay(8)
                }
                for (ch in 0 until AppState.MIXER_CHANNELS) {
                    send(OscMessage(osc("/ch/%02d/mix/on", ch + 1),
                        emptyList()))
                    delay(4)
                }
            }
            val m = receiveOnce()
            if (m != null) {
                lastRx = t; lastRxT = t
                if (AppState.conn.value == AppState.Conn.CONNECTING) {
                    AppState.conn.value = AppState.Conn.CONNECTED
                    AppState.everConnected.value = true
                    AppState.lastError.value = null
                    updateNotif()
                }
                // Inside the guard as well — see below. `handle` is
                // what feeds the engine its meters, twenty times a
                // second, and an exception there kills the same
                // coroutine just as dead as one from `tick`.
                try { handle(m, t, rtaFocus, rtaFocusT) }
                catch (ex: Exception) { engineFailed(ex) }
            } else if (t - lastRx > 10.0 &&
                       AppState.conn.value == AppState.Conn.CONNECTED) {
                // radio dropout: show it, keep trying — engine is frozen
                // by meter staleness already
                AppState.conn.value = AppState.Conn.CONNECTING
                AppState.lastError.value = "Mixer silent — waiting for Wi-Fi…"
                updateNotif()
                show?.net("METERS LOST — %.0fs with no packet from the mixer; "
                    .format(java.util.Locale.ROOT, t - lastRx) +
                    "the engine is holding every fader still")
            }
            val e = engine ?: continue
            // RTA round-robin: park the console's RTA on each active
            // channel for ~3 s so the doctor hears everyone regularly.
            //
            // WHILE A RING IS BEING HUNTED, sweep fast and sweep
            // EVERYTHING. A howl is a loop through one microphone and
            // the point of the sweep is to find which one — including
            // channels the engine currently thinks are silent, because
            // a mic pointed into a wedge that is ringing may be doing
            // nothing else at all.
            val hunting = ringOut.hunting
            if (t - rtaFocusT > (if (hunting) 0.5 else 3.0)) {
                val active = if (hunting) (0 until AppState.MIXER_CHANNELS).toList()
                             else e.activeChannels().sorted()
                if (active.isNotEmpty()) {
                    val next = active[(active.indexOf(rtaFocus) + 1)
                        .mod(active.size)]
                    if (next != rtaFocus) {
                        rtaFocus = next
                        rtaFramesSinceSwitch = 0
                        send(OscMessage("/-stat/rta/source", listOf(rtaFocus)))
                        // a different channel's spectrum is not this
                        // one's getting louder — see sourceChanged()
                        watchdog.sourceChanged()
                    }
                    rtaFocusT = t
                }
            }
            // A BUG IN THE ENGINE MUST NOT END THE SHOW.
            //
            // Everything below runs inside the one coroutine that also
            // receives meters and answers the console. An exception
            // escaping here kills that loop: no more writes, no more
            // reads, no more log — and nothing on screen would say so,
            // because the service is still alive and the notification
            // still says MIXING. There was a real one to find, a
            // NullPointerException out of `tick()` when a stereo-paired
            // channel went active before the mix had an anchor.
            //
            // The mixer holds its last state when we stop talking, so
            // the safe response is to say so loudly and keep the loop
            // running rather than to die quietly.
            try {
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
                // Behind the same switch as the rest of the tone work.
                //
                // It was behind no switch at all, which went unnoticed
                // only because it never fired: the one-shot chain needs
                // a confident instrument recognition, and recognition
                // was naming everything congas at low confidence, so it
                // wrote nothing all night. Fixing recognition turns this
                // on for real — sixteen channels of EQ, compressor and
                // HPF that the operator has never seen it touch — and
                // an autopilot that starts reaching for new controls
                // mid-gig with no way to stop it is not one anybody
                // should take to a show.
                // RingOut owns the ring band (4) whenever it has a live
                // cut on a channel. A first-time treatment pass reads the
                // desk from the TAKEOVER snapshot, which can show a stale
                // band-4 boost, and flattening that would wipe a notch
                // written after takeover and re-open the loop. So drop any
                // treatment write to the ring band on a channel that
                // currently has an active notch — the boost-flatten still
                // runs on every other channel, closing the §0.1 leak
                // without ever fighting a live ring-out.
                val ringed = ringOut.active().map { it.ch }.toSet()
                val ringBandRe = Regex(
                    "^/ch/(\\d\\d)/eq/${com.stagemix.engine.RingOut.RING_BAND}/")
                if (directing && AppState.doctorOn.value)
                    for (w in e.treatmentPass(t)) {
                        val ringBandCh = ringBandRe.find(w.address)
                            ?.groupValues?.get(1)?.toIntOrNull()?.minus(1)
                        if (ringBandCh != null && ringBandCh in ringed) continue
                        lastParam[w.address] = w.value
                        send(OscMessage(w.address, listOf(w.value)))
                        // Every processing write, decoded. The engine
                        // logs one "treat" line with the reasoning; the
                        // actual values that reached the desk were not
                        // in the file at all, which makes a chain
                        // impossible to check afterwards.
                        val ch = Regex("^/ch/(\\d\\d)/").find(w.address)
                            ?.groupValues?.get(1)?.toIntOrNull()?.minus(1)
                        show?.param(w.address, w.value,
                            ch?.let { chName(it) } ?: "", tSec = t)
                    }
                // RINGING OUT IS SAFETY, NOT TONE, so it is not behind
                // the EQ switch — but it still needs the mains, because
                // an app that is only watching must write nothing at
                // all. In shadow the hunt still runs and the log says
                // which microphone it would have cut.
                for (w in ringOut.tick(t, mayWrite = directing)) {
                    lastParam[w.address] = w.value
                    send(OscMessage(w.address, listOf(w.value)))
                    val rch = Regex("^/ch/(\\d\\d)/").find(w.address)
                        ?.groupValues?.get(1)?.toIntOrNull()?.minus(1)
                    show?.param(w.address, w.value,
                        rch?.let { chName(it) } ?: "",
                        "— ringing out", t)
                }
                if (ringOut.lastAction != lastRingAction) {
                    lastRingAction = ringOut.lastAction
                    show?.mark("RING-OUT", ringOut.lastAction, t)
                    // a ring happened: fold it into the carried-forward
                    // feedback profile now, so it survives even if the
                    // tablet never gets a clean shutdown
                    persistFeedback()
                }
                // ANY MICROPHONE THAT HAS RUNG STOPS BEING RAISED.
                //
                // The keeper is not the only thing that can add gain: the
                // MAINS engine lifts a soloing mic up to +6 dB, and a solo
                // on an open mic is exactly what rings it. So BOTH sides
                // are told about every notch — the keeper quiets that
                // wedge-send, and the engine bars a new feature on the mic
                // and eases off any lift it was mid-way through, for a few
                // minutes after the howl (§4). A pre-ring GUARD is skipped:
                // it is a standing cut on a known-bad frequency, not a mic
                // that has howled tonight, so it does not bar a raise.
                for (n in ringOut.active()) {
                    if (n.guard) continue
                    monBal.onRing(n.ch, t)
                    e.onRing(n.ch, t)
                }

                // THE WEDGES, SLIGHTLY.
                //
                // Cut-first, one move per bus per twenty seconds, never
                // between songs, never against a hand, never a bus
                // master. Behind its own switch and behind MIXING, so
                // an app that is only watching still cannot reach a
                // musician's ears.
                if (directing && AppState.keepMonitors.value &&
                    !e.frozenAll) {
                    applyMonitorPlan(monBal.plan(
                        tSec = t,
                        roles = e.state.mapValues { it.value.role },
                        kit = e.drumKit(),
                        playing = !e.betweenSongs && e.ready,
                        // a howl is live from the moment the RTA watchdog
                        // vetoes until the hunt has finished — no send may
                        // go up anywhere on the stage during that window
                        feedbackActive = ringOut.hunting || e.watchdogVeto), t)
                }
                // Re-read the sends now and then: it is the only way to
                // notice the engineer's hand on a wedge, and following
                // that hand is the whole agreement.
                if (directing && AppState.keepMonitors.value &&
                    t - sendsReadT > 25.0) {
                    sendsReadT = t
                    scope.launch { pollSends() }
                }
                doctor?.let { d ->
                    // NOT BETWEEN SONGS, AND NOT WHILE THE STAGE IS
                    // MUTED. The doctor was the one write path with no
                    // gap gate: applause is broadband and HF-heavy and
                    // keeps the vocal mics above their gate, so between
                    // numbers it would quietly EQ four open mics against
                    // the sound of a room clapping — audible tone change
                    // at the one moment the audience is listening to the
                    // PA, and a poisoned reference for the next song.
                    if (directing && AppState.doctorOn.value &&
                        !e.betweenSongs && !e.stageMuted) {
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
                    // AN EMPTY ROOM IS NOT A SHOW.
                    //
                    // The tablet gets left switched on. Left alone over
                    // a weekend this wrote three days of five-second
                    // snapshots of an empty bar — 55 MB, a quarter of a
                    // million lines of sixteen silent channels — and
                    // the running picture of the three actual gigs went
                    // over the file's line cap because of it.
                    val names = AppState.mixerChannelNames.value
                    if (e.stageQuiet(t)) {
                        lg.heartbeat(t, "nothing on any channel — the app " +
                            "is awake and waiting for the band")
                        // A new night deserves a new file. Rotated only
                        // while it is quiet, so a gig is never split.
                        if (lg.ageHours() > LOG_ROTATE_HOURS) {
                            lg.footer(e, names)
                            lg.close()
                            show = ShowLog(getExternalFilesDir(null) ?: filesDir)
                            AppState.logPath.value = show?.file?.absolutePath ?: ""
                            show?.head("(same session, new night)", e, names,
                                AppState.nightsCount.value,
                                AppState.tasteSummary.value,
                                build = "${BuildConfig.GIT_SHA} " +
                                    "(built ${BuildConfig.BUILT_AT}, " +
                                    "v${BuildConfig.VERSION_NAME})")
                        }
                    } else {
                        lg.snapshot(t, e, doctor, names, directing)
                        lg.summary(t, e, names)
                        // and the report card mid-night, because this
                        // app is never shut down and the card used to
                        // be written only on the way out
                        lg.card(t, e, names)
                        // the complete monitor picture on a cadence, so
                        // the whole night's wedge state is in the log —
                        // every send, every wedge, not just the takeover
                        if (t - lastMonMatrix >= MON_MATRIX_SEC) {
                            lastMonMatrix = t
                            dumpMonitorMatrix(t)
                        }
                    }
                }
                // A tick that got all the way through is the only
                // evidence that whatever went wrong is over. INSIDE the
                // once-a-second block: this sat at loop-body level, and
                // the loop spins five times a second on the receive
                // timeout, so a tick that threw was followed 200 ms
                // later by an iteration that did no work at all and
                // cleared the count. The counter could never reach two,
                // and the "five in a row and it stops writing" guard
                // could never fire.
                tickFailures = 0
                // A clean tick is also the all-clear for a RECOVERED
                // engine blip. Without this, one transient exception left
                // `lastError` set for the rest of the night: the header
                // stuck on red PROBLEM (and the show clock greyed) while
                // the advice list and the progress bar both read healthy —
                // a surface contradiction, and the header lying "broken"
                // over an app that is mixing correctly. Only clear OUR
                // engine-error banner, and only while still directing, so
                // a 5-in-a-row auto-off keeps its explanation on screen.
                if (AppState.directing.value &&
                    AppState.lastError.value == ENGINE_ERROR_MSG) {
                    AppState.lastError.value = null
                    updateNotif()
                }
            }
            } catch (ex: Throwable) {
                engineFailed(ex)
            }
        }
    }

    /**
     * Something threw inside the engine. Say it in the one place the
     * operator will look, and in the log they will send afterwards,
     * then carry on: the console is still holding the last mix we gave
     * it.
     *
     * The count is CONSECUTIVE. It used to only ever go up, so five
     * unrelated blips spread across a whole night — one an hour, each
     * survived — added up to switching mixing off during the last set;
     * and because nothing reset it, switching mixing back on left the
     * counter at five, where the very next exception killed it again.
     * Repeating is what "it is not a blip" means, and repeating is what
     * this now counts.
     */
    private fun engineFailed(ex: Throwable) {
        tickFailures++
        show?.mark("ERROR", "${ex.javaClass.simpleName}: " +
            (ex.message ?: "") + " (#$tickFailures in a row)", now())
        show?.net("ENGINE ERROR ($tickFailures in a row): " +
            "${ex.javaClass.simpleName} ${ex.message ?: ""} — the " +
            "mixer is holding the last mix; nothing new is being " +
            "written")
        AppState.lastError.value = ENGINE_ERROR_MSG
        if (tickFailures >= MAX_TICK_FAILURES) {
            // Repeating means it is not a blip. Stop writing rather
            // than keep throwing once a second all night.
            AppState.directing.value = false
            show?.net("MIXING switched off after $tickFailures " +
                "errors in a row — the faders are where the app left them")
        }
        // AFTER the state has settled, not before: refreshing first
        // left the status bar reading MIXING once the guard had turned
        // it off.
        try { updateNotif() } catch (_: Exception) {}
    }

    private fun handle(m: OscMessage, t: Double, rtaFocus: Int,
                       rtaFocusT: Double) {
        val e = engine ?: return
        when (m.address) {
            "/meters/${Meters.BANK_INPUTS}" -> {
                m.blobArg(0)?.let { Meters.decode(it) }?.let { levels ->
                    e.onMeters(levels, t)
                    // and straight to the screen's own draw clock, at
                    // the rate they arrive. Deliberately not Compose
                    // state: sixteen meters at twenty frames a second
                    // through the strip model recomposed a hundred text
                    // nodes every time the drummer hit something.
                    com.stagemix.app.ui.Levels.publish(levels)
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
                        show?.mark(if (watchdog.vetoActive) "FEEDBACK"
                                   else "FEEDBACK CLEAR",
                            "~${watchdog.lastFreqHz} Hz", t)
                        // and do something about it: find the
                        // microphone the ring is living in and notch it
                        if (watchdog.vetoActive)
                            ringOut.ringing(watchdog.lastFreqHz, t)
                        else ringOut.cleared(t)
                        show?.note("HOWL", if (watchdog.vetoActive)
                            "feedback suspected at ~${watchdog.lastFreqHz} Hz " +
                            "— every boost frozen until it clears"
                            else "feedback cleared — boosts allowed again")
                        AppState.lastError.value = if (watchdog.vetoActive)
                            "⚠ FEEDBACK suspected ~${watchdog.lastFreqHz} Hz " +
                            "— boosts frozen; notch it on the GEQ"
                        else null
                    }
                    // skip the first frame after a source switch (it may
                    // still be the previous channel's spectrum); the hunt
                    // dwells 0.5 s per channel, so every later frame in
                    // the dwell still feeds RingOut
                    rtaFramesSinceSwitch++
                    if (rtaFramesSinceSwitch > 1)
                        ringOut.onRta(rtaFocus, bins, t)
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
                        engine?.onRtaFor(rtaFocus, bins, t)
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
                // THE MUTE KEYS — read, never written.
                //
                // Handled before the float branch because the console
                // answers this one as an int, and because it is the only
                // way to know a channel is out of the mains: `/meters/1`
                // is pre-fader and pre-mute. On the night this comes
                // from, the operator muted the band from Mixing Station
                // every time the music stopped, and the engine — seeing
                // full-strength meters on all sixteen — went on
                // balancing a stage that was sending nothing anywhere.
                //
                // 1 is ON. 0 is muted.
                Regex("^/ch/(\\d\\d)/mix/on$").find(m.address)?.let { match ->
                    val ch = match.groupValues[1].toInt() - 1
                    val on = when (val a = m.args.firstOrNull()) {
                        is Int -> a != 0
                        is Float -> a > 0.5f
                        else -> return
                    }
                    if (e.setChannelMuted(ch, !on)) {
                        show?.note("MUTE", "${chName(ch)} " +
                            (if (on) "un-muted on the desk — back in the mix"
                             else "muted on the desk — left alone until " +
                                  "it comes back"))
                        publishStrips(t)
                    }
                    return
                }
                // parameter enquiry replies / other-client changes
                val v = m.args.firstOrNull() as? Float
                if (v != null) {
                    pending[m.address] = v
                    // A WEDGE SEND CAME BACK. Route it, or the keeper is
                    // blind: monitors.onSend/monBal.onSend used to be
                    // called only during takeover, so the 25-second
                    // re-read asked ninety-six questions a night and
                    // threw every answer away. That made hand-detection
                    // — "understand what the engineer is doing and go
                    // with it" — dead code, and left the keeper unable
                    // to see its own effect.
                    if (com.stagemix.engine.isMonitorSend(m.address)) {
                        Regex("^/ch/(\\d\\d)/mix/(\\d\\d)/level$")
                            .find(m.address)?.let { mm ->
                                val ch = mm.groupValues[1].toInt() - 1
                                val bus = mm.groupValues[2].toInt()
                                val db = FaderLaw.floatToDb(v)
                                if (!collecting) {
                                    monitors.onSend(bus, ch, db)
                                    monBal.onSend(bus, ch, db, now())
                                }
                            }
                    }
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
                                // A channel that missed the takeover has
                                // no authority to override — this reply
                                // is the answer we have been re-asking
                                // for, and it puts the channel INTO the
                                // mix rather than moving it inside one.
                                if (e.adoptLateChannel(ch, db, t)) {
                                    show?.net("${chName(ch)} answered at " +
                                        "last — being mixed from now on")
                                    publishStrips(t)
                                } else if (mine == null ||
                                           abs(db - mine) > ECHO_TOL_DB) {
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
                heldByYou = e.held(ch.index),
                deskMuted = e.isDeskMuted(ch.index),
                baselineDb = st?.baselineDb ?: -10f,
                takeoverDb = st?.takeoverDb ?: st?.baselineDb ?: -10f,
                riding = st?.riding ?: false,
            )
        }
        AppState.snapshotTaken.value = e.ready
        AppState.balanceKept.value = e.balanceAdopted
        if (AppState.stageMuted.value != e.stageMuted) {
            AppState.stageMuted.value = e.stageMuted
            updateNotif()
        }
        AppState.health.value = e.health()
        AppState.leadVocal.value = e.leadVocal
        // THE VOICE, AND EVERYTHING ELSE. Both as contributions to the
        // mains — what the room is actually getting — so the master
        // meter shows the one relationship the whole engine defends.
        var bandPow = 0.0
        var leadPow = 0.0
        for ((ch, st) in e.state) {
            if (!st.active) continue
            val base = st.baselineDb ?: continue
            val c = ((st.preEma ?: st.lastLevelDb) + base + st.offset)
                .toDouble()
            val p = Math.pow(10.0, c / 10.0)
            if (ch == e.leadVocal) leadPow += p else bandPow += p
        }
        AppState.leadDb.value = if (leadPow > 0)
            (10.0 * Math.log10(leadPow)).toFloat() else -128f
        AppState.bandDb.value = if (bandPow > 0)
            (10.0 * Math.log10(bandPow)).toFloat() else -128f
        AppState.channelsMixed.value = e.state.count {
            it.value.baselineDb != null }
        AppState.tickMs.value = android.os.SystemClock.elapsedRealtime()
        // the per-channel spectrum for the strips: the accumulated
        // shape, not the momentary one — the analyzer only visits one
        // channel at a time, so what a strip can honestly draw is what
        // that channel has sounded like, not what it is doing this
        // instant
        for (ch in 0 until AppState.MIXER_CHANNELS)
            e.spectrum.shape(ch)?.let { com.stagemix.app.ui.Spectra.publish(ch, it) }
        AppState.phase.value = phaseOf(e, t)
        publishAdviceAndWork(e, t)
        AppState.ringNotches.value = ringOut.active().associate {
            it.ch to "%.0f Hz -%.1f dB".format(java.util.Locale.ROOT,
                it.hz, it.cutDb) }
        val roles = e.state.mapValues { it.value.role }
        val kit = e.drumKit()
        val moves = monBal.moved().groupBy { it.bus }
        AppState.wedges.value = monitors.all().map { w ->
            val notes = monitors.critique(w.bus, roles, kit)
            val worst = notes.firstOrNull { kotlin.math.abs(it.offDb) > 3f }
            AppState.WedgeUi(
                bus = w.bus,
                name = AppState.busNames.value[w.bus - 1] ?: w.name,
                kind = w.kind.name,
                inEars = w.inEars,
                top = w.sends.entries
                    .filter { it.value > com.stagemix.engine.MonitorMap
                        .MONITOR_FLOOR_DB }
                    .sortedByDescending { it.value }.take(3).map { it.key },
                worstOffDb = worst?.offDb ?: 0f,
                worstCh = worst?.ch,
                // the wedge as a mix, one entry per channel
                sendDb = w.sends.toMap(),
                targetDb = notes.mapNotNull { n ->
                    n.wantDb?.let { n.ch to it } }.toMap(),
                appDb = moves[w.bus]?.associate { it.ch to it.appDb }
                    ?: emptyMap())
        }
    }

    /**
     * Everything that is wrong with the remedy for each, and what the
     * app is doing right now with a bar that fills.
     *
     * Both are published on every tick and neither is ever empty. A
     * panel that goes blank when things are fine trains you to read
     * "blank" as "fine", and then a blank panel because the app has
     * stopped looks exactly the same — which is the whole history of
     * this project in one sentence.
     */
    private fun publishAdviceAndWork(e: StageEngine, t: Double) {
        val total = AppState.config.value.channels.size
        val mixed = e.state.count { it.value.baselineDb != null }
        val wedgesOut = AppState.wedges.value.count {
            kotlin.math.abs(it.worstOffDb) > 3f }
        AppState.advice.value = com.stagemix.engine.adviseOn(
            com.stagemix.engine.Situation(
                connected = AppState.conn.value == AppState.Conn.CONNECTED,
                connecting = AppState.conn.value == AppState.Conn.CONNECTING,
                everConnected = AppState.everConnected.value,
                autoStart = AppState.autoStart.value,
                directing = AppState.directing.value,
                frozenAll = AppState.frozenAll.value,
                stageMuted = AppState.stageMuted.value,
                balanceKept = AppState.balanceKept.value,
                doctorOn = AppState.doctorOn.value,
                channelsTotal = total,
                channelsMixed = mixed,
                metersAgeSec = (t - lastRxT).toFloat().coerceAtLeast(0f),
                engineError = AppState.lastError.value,
                consecutiveErrors = tickFailures,
                hunting = ringOut.hunting,
                ringNotches = ringOut.active().size,
                wedgesRead = monitors.all().size,
                wedgesOut = wedgesOut,
                monitorsEnabled = AppState.keepMonitors.value,
                mixingSec = if (e.takeoverT >= 0) t - e.takeoverT else -1.0))

        // THE FAULT THE OPERATOR SAW GOES IN THE LOG TOO. It was only
        // ever pixels — so the morning-after question "what was it
        // telling me at 22:40?" had no answer. Only the worst
        // non-note item, and only when it changes, so the file is not
        // flooded with the same line every second.
        AppState.advice.value.firstOrNull {
            it.level != com.stagemix.engine.Level.NOTE }?.let { top ->
            if (top.key != lastAdviceKey) {
                lastAdviceKey = top.key
                show?.mark("STATUS", top.what + " — " + top.doThis, t)
            }
        } ?: run { lastAdviceKey = "" }

        // The bar. A countdown when there is one; otherwise how much of
        // the mix is sitting where it should be, which moves all night.
        val ph = AppState.phase.value
        // BEFORE the phase countdown and the steady-state bar: is the app
        // actually sending to the desk at all? If it is watching, frozen,
        // muted, or has lost the mixer, the honest bar says so in amber —
        // it must never show the green "finding the balance" fill NOR a
        // blue "setting up channels" countdown, both of which read as work
        // in progress. This takes precedence over `ph` because a phase
        // (the 10-minute setup window, the 20s listen) can still be live
        // in engine state after a hand-back — takeoverT is never reset —
        // so a phase countdown over a paused app is the same §5 lie. When
        // the app is genuinely not sending, nothing is "in progress".
        val notMixing: com.stagemix.engine.Work? =
            when (AppState.opState()) {
                AppState.OpState.NO_MIXER ->
                    com.stagemix.engine.pausedWork("no-mixer",
                        "No mixer — nothing being sent",
                        "lost the console; reconnecting when it is back")
                AppState.OpState.FROZEN ->
                    com.stagemix.engine.pausedWork("frozen",
                        "Frozen — every fader held where it is",
                        "press FREEZE again to hand the mix back")
                AppState.OpState.MUTED ->
                    com.stagemix.engine.pausedWork("muted",
                        "Waiting — the stage is muted",
                        "holding still until the main mix is live again")
                AppState.OpState.WATCHING ->
                    com.stagemix.engine.pausedWork("watching",
                        "Watching only — nothing being sent",
                        "press MIX to let the app move the faders")
                AppState.OpState.MIXING -> null
            }
        AppState.work.value = if (notMixing != null) notMixing
        else if (ph != null) {
            val nowMs = android.os.SystemClock.elapsedRealtime()
            val span = (ph.endsAtMs - ph.startedAtMs).coerceAtLeast(1L)
            com.stagemix.engine.Work(
                key = ph.key, label = ph.label, detail = ph.why,
                frac = ((nowMs - ph.startedAtMs).toFloat() / span)
                    .coerceIn(0f, 1f),
                secsLeft = kotlin.math.ceil((ph.endsAtMs - nowMs) / 1000.0)
                    .toInt().coerceAtLeast(0),
                alarm = ph.alarm)
        } else {
            // THE ENGINE ALREADY KNOWS THIS NUMBER. The first version
            // counted channels whose fader was still near where the
            // operator left it — which is the count of channels the app
            // has NOT moved, very nearly the inverse of "sitting where
            // they should be". It read low exactly when the engine was
            // working hardest, on the one bar an operator watches to
            // decide whether the thing is doing anything.
            com.stagemix.engine.holdingWork(
                inPlace = Math.round(
                    e.health().inPlacePct / 100f * mixed),
                total = mixed.coerceAtLeast(1),
                kept = AppState.balanceKept.value)
        }
    }

    /**
     * The one thing the app is waiting for, if it is waiting for
     * anything — with the deadline, so the screen can draw a bar that
     * fills toward a number of seconds instead of a spinner that says
     * nothing.
     */
    private fun phaseOf(e: StageEngine, t: Double): com.stagemix.app.ui.Phase? {
        val nowMs = android.os.SystemClock.elapsedRealtime()
        fun phase(key: String, label: String, why: String, left: Double,
                  span: Double, alarm: Boolean = false) =
            com.stagemix.app.ui.Phase(
                key = key, label = label, why = why,
                startedAtMs = nowMs - ((span - left) * 1000).toLong(),
                endsAtMs = nowMs + (left * 1000).toLong(), alarm = alarm)

        // A REAL DEADLINE, not a constant. This used to return a fixed
        // 4-of-8 every tick, so the published Work never changed, the
        // bar's effect never restarted, and during the app's most
        // time-critical operation the operator saw a red bar frozen at
        // half with the countdown pinned at "0s". The hunt has an
        // actual clock — RingOut knows how much of it is left.
        if (ringOut.hunting) return phase("hunt",
            "Feedback — finding which microphone",
            "sweeping the stage at the ringing frequency",
            ringOut.huntLeft(t), ringOut.huntSpan, alarm = true)
        val take = e.takeoverT
        if (take >= 0 && !e.ready) {
            val left = (e.settings.learnSec - (t - take)).coerceAtLeast(0.0)
            return phase("listen", "Listening before it leads",
                "learning where this band sits before touching anything",
                left, e.settings.learnSec.toDouble())
        }
        if (take >= 0 && AppState.doctorOn.value) {
            val left = (com.stagemix.engine.SETUP_WINDOW_SEC - (t - take))
            if (left > 0) return phase("setup",
                "Setting up channels",
                "the high-pass and the compressor an engineer would set " +
                "at soundcheck — once each, then it leaves them alone",
                left, com.stagemix.engine.SETUP_WINDOW_SEC.toDouble())
        }
        return null
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
    private suspend fun takeoverNow(): Unit = try { takeoverLock.withLock {
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
            // The mute key. Nothing else on the desk can tell us: the
            // meters we run on are pre-fader AND pre-mute, so a muted
            // channel reads exactly like a playing one.
            send(OscMessage(osc("/ch/%02d/mix/on", ch + 1), emptyList()))
            for (b in 1..4)
                send(OscMessage(osc("/ch/%02d/eq/%d/g", ch + 1, b),
                    emptyList()))
            send(OscMessage(osc("/ch/%02d/dyn/thr", ch + 1), emptyList()))
            send(OscMessage(osc("/ch/%02d/dyn/on", ch + 1), emptyList()))
            // The high-pass the engineer had. Read so the chain can
            // prove it only ever steepens it, never lowers it into a
            // low ring.
            send(OscMessage(osc("/ch/%02d/preamp/hpon", ch + 1), emptyList()))
            send(OscMessage(osc("/ch/%02d/preamp/hpf", ch + 1), emptyList()))
            // and the reverb (FX-7) send, so the chain does not write
            // over a reverb choice the engineer already made
            send(OscMessage(osc("/ch/%02d/mix/07/level", ch + 1), emptyList()))
        }
        // Paced, not fired as one 96-packet burst: a burst that big is
        // routinely clipped by the console's receive buffer or the
        // tablet's Wi-Fi, and every dropped reply is a channel the
        // autopilot then leaves unmanaged all night.
        for (ch in chans) { enquire(ch.index); delay(3) }
        // AND WHAT IS IN THE WEDGES.
        //
        // Read only. Six sends per channel is ninety-six small packets,
        // paced like everything else, and it is the first time this app
        // has looked at the monitors at all — which is why it has never
        // been able to say anything useful about a stage that was
        // ringing. Nothing here is ever written back: see MonitorMap.
        for (ch in chans) {
            for (b in com.stagemix.engine.AUX_SEND_FIRST..
                     com.stagemix.engine.AUX_SEND_LAST) {
                send(OscMessage(osc("/ch/%02d/mix/%02d/level",
                    ch.index + 1, b), emptyList()))
                delay(2)
            }
        }
        withTimeoutOrNull(3000) {
            while (chans.any {
                    !pending.containsKey(
                        osc("/ch/%02d/mix/fader", it.index + 1)) })
                delay(50)
        }
        // KEEP ASKING. A dropped UDP packet must not cost a channel the
        // whole night.
        //
        // There was one retry pass here, and on the venue's own Wi-Fi —
        // a 2.4 GHz AP in a room full of phones, which is what an M18
        // always is — one retry was not enough twice in a row. Five
        // channels went unmixed on the first takeover and five on the
        // second, and the two sets were not the same five: it was
        // simply whichever replies happened to be lost, and one of them
        // was the bass. Nothing was wrong with those channels. The
        // replies just did not arrive.
        //
        // Retries are individually addressed and paced, so each pass is
        // smaller and likelier to survive than the one before it.
        for (attempt in 1..TAKEOVER_TRIES) {
            val missing = chans.filter {
                !pending.containsKey(osc("/ch/%02d/mix/fader", it.index + 1)) }
            if (missing.isEmpty()) break
            if (attempt > 1) show?.net(
                "still waiting on ${missing.size} fader" +
                (if (missing.size == 1) "" else "s") +
                " — asking again (try $attempt of $TAKEOVER_TRIES)")
            for (ch in missing) { enquire(ch.index); delay(8) }
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
            // The engine never took over (takeoverT stays -1 and every
            // tick writes nothing), so leaving directing=true would have
            // every status surface assert MIXING over a console the app
            // never took. Drop back to watching so the truth shows and
            // the operator can retry.
            AppState.directing.value = false
            AppState.lastError.value =
                "Takeover failed — no fader positions received from the mixer"
            updateNotif()
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
        show?.mark("TAKEOVER", "${faders.size} channels adopted as the " +
            "centre of the app's authority", now())
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
        // The chain gets the SAME snapshot — the high-pass corner the
        // desk had, whether it was in, and the four band gains — so it
        // can refuse to lower a high-pass or flatten a cut. Read
        // outside the doctor block because the chain runs even when the
        // doctor is off.
        engine?.let { eng ->
            for (ch in chans) {
                val eqDb = FloatArray(4) { b ->
                    pending[osc("/ch/%02d/eq/%d/g", ch.index + 1, b + 1)]
                        ?.let { it * 30f - 15f } ?: 0f
                }
                val haveEq = (0 until 4).any {
                    pending.containsKey(
                        osc("/ch/%02d/eq/%d/g", ch.index + 1, it + 1)) }
                val hpOn = pending[osc("/ch/%02d/preamp/hpon", ch.index + 1)]
                    ?.let { it > 0.5f }
                val hpHz = pending[osc("/ch/%02d/preamp/hpf", ch.index + 1)]
                    // invert hpfToFloat: 20 * 20^v
                    ?.let { 20f * Math.pow(20.0, it.toDouble()).toFloat() }
                val thrDb = pending[osc("/ch/%02d/dyn/thr", ch.index + 1)]
                    ?.let { it * 60f - 60f }
                val compOn = pending[osc("/ch/%02d/dyn/on", ch.index + 1)]
                    ?.let { it > 0.5f } ?: false
                val revDb = pending[osc("/ch/%02d/mix/07/level", ch.index + 1)]
                    ?.let { FaderLaw.floatToDb(it) }
                eng.treatment.snapshotDesk(ch.index, hpHz, hpOn ?: false,
                    if (haveEq) eqDb else null, thrDb, compOn, revDb)
            }
        }
        // the wedges, as the engineer has them right now
        for (ch in chans) {
            for (b in com.stagemix.engine.AUX_SEND_FIRST..
                     com.stagemix.engine.AUX_SEND_LAST) {
                pending[osc("/ch/%02d/mix/%02d/level", ch.index + 1, b)]
                    ?.let {
                        val db = FaderLaw.floatToDb(it)
                        monitors.onSend(b, ch.index, db)
                        // and the keeper, which compares this against
                        // what it last wrote — that difference is how a
                        // hand on a wedge send is detected at all
                        monBal.onSend(b, ch.index, db, now())
                    }
            }
        }
        // SHOW ALL SIX AUX BUSES, always. The M18 has six monitor sends,
        // and a wedge used to appear only once it had a name or a routed
        // send — so a monitor with nothing up yet, or an unnamed bus,
        // simply went missing (the piano in-ears on bus 6 among them). Seed
        // every bus so all six are on the glass; a bus with no name reads
        // as "MON n" until the console gives it one.
        for (b in com.stagemix.engine.AUX_SEND_FIRST..
                 com.stagemix.engine.AUX_SEND_LAST)
            monitors.onBusName(b,
                AppState.busNames.value[b - 1]?.takeIf { it.isNotBlank() }
                    ?: "MON $b")
        // re-apply the operator's saved in-ears/wedge choices: a name read
        // can rebuild a wedge, and the drummer's floor-wedge choice must
        // survive that
        for ((bus, ie) in AppState.monitorInEars.value) monitors.setInEars(bus, ie)
        logMonitors()
        preRingSetup()
        publishStrips(now())
    } } catch (ex: Throwable) {
        // A takeover that throws — a real M18 reply the emulator never
        // sends, say — must not crash the app or leave it "MIXING" with a
        // half-built engine. Drop cleanly back to WATCHING and report it,
        // the same fail-safe posture the tick loop takes.
        collecting = false
        AppState.directing.value = false
        engineFailed(ex)
    }

    /**
     * The pre-ring: carry this rig's known feedback forward, document it,
     * and — if the operator has turned pre-ring on — put a shallow guard
     * cut on every frequency that has howled here before often enough to
     * count, so the recurring monitor feedback is pre-empted rather than
     * hunted from cold. The profile is always LOGGED; the guards are only
     * PLACED when the switch is on.
     */
    private fun preRingSetup() {
        val lg = show ?: return
        carriedFeedback = AppState.loadFeedbackProfile(this)
        val names = AppState.mixerChannelNames.value
        fun nm(ch: Int) = names[ch] ?: "ch%02d".format(ch + 1)
        if (carriedFeedback.isEmpty()) {
            lg.note("HOWL", "no feedback history for this rig yet — the app " +
                "will learn each ring and carry it forward")
            return
        }
        lg.note("HOWL", "── feedback carried forward from earlier nights ──")
        for ((ch, hz, rings) in carriedFeedback.sortedByDescending { it.third })
            lg.note("HOWL", "  %s has howled at %.0f Hz %d time%s before"
                .format(java.util.Locale.ROOT, nm(ch), hz, rings,
                    if (rings == 1) "" else "s"))
        if (!AppState.preRing.value) {
            lg.note("HOWL", "pre-ring is OFF — these are recorded, not " +
                "pre-cut. Turn PRE-RING on in SETUP to guard them from cold.")
            return
        }
        val placed = ringOut.seedGuards(
            carriedFeedback.map {
                com.stagemix.engine.RingOut.Learned(it.first, it.second, it.third) },
            PRE_RING_MIN_RINGS, PRE_RING_GUARD_DB)
        if (placed.isEmpty())
            lg.note("HOWL", "pre-ring is on, but nothing has howled enough " +
                "times yet to guard (needs $PRE_RING_MIN_RINGS)")
        else {
            for (p in placed)
                lg.mark("HOWL", ("PRE-RING %s at %.0f Hz — a %.1f dB guard " +
                    "cut, because it has howled %d times here")
                    .format(java.util.Locale.ROOT, nm(p.ch), p.hz,
                        PRE_RING_GUARD_DB, p.rings), now())
            show?.user("pre-ring placed ${placed.size} shallow guard cut" +
                (if (placed.size == 1) "" else "s") + " on frequencies this " +
                "rig has howled at before — cut-only, and they deepen if it " +
                "still rings")
        }
    }

    /**
     * Save the feedback profile: the carried-in counts plus what has rung
     * this session, as an ABSOLUTE total, so it is idempotent to call
     * repeatedly (it never double-counts a ring).
     */
    private fun persistFeedback() {
        fun key(ch: Int, hz: Float) = "$ch:${Math.round(hz)}"
        val m = HashMap<String, Triple<Int, Float, Int>>()
        for (e in carriedFeedback) m[key(e.first, e.second)] = e
        for (n in ringOut.learnedProfile()) {
            val k = key(n.ch, n.hz)
            val prev = m[k]?.third ?: 0
            m[k] = Triple(n.ch, n.hz, prev + n.rings)
        }
        AppState.saveFeedbackProfile(this, m.values.toList())
    }

    /**
     * Send the keeper's writes, and say what they were.
     *
     * Every one of these is an aux send. They are filtered twice — once
     * inside [com.stagemix.engine.MonitorBalance.plan] and again here —
     * because this is the only route in the app that reaches a
     * musician's ears, and a filter you can see at the point of use is
     * worth more than one you have to go and look up.
     */
    private fun applyMonitorPlan(
        writes: List<com.stagemix.engine.ParamWrite>, t: Double,
    ) {
        for (w in writes) {
            if (!com.stagemix.engine.isMonitorSend(w.address)) continue
            lastParam[w.address] = w.value
            send(OscMessage(w.address, listOf(w.value)))
            // the channel name, so the wedge line reads legibly rather
            // than "ch07" with no idea what it is
            val wch = Regex("^/ch/(\\d\\d)/").find(w.address)
                ?.groupValues?.get(1)?.toIntOrNull()?.minus(1)
            show?.param(w.address, w.value,
                wch?.let { chName(it) } ?: "", "— wedge", t)
        }
        val notes = monBal.drainNotes()
        for (n in notes) show?.mark("MONITOR", n, t)
        if (writes.isNotEmpty() || notes.isNotEmpty())
            AppState.wedgeMoves.value = monBal.moved().map {
                AppState.WedgeMove(it.bus, it.ch, it.appDb) }
    }

    /**
     * Ask the desk what the wedge sends are now.
     *
     * The keeper can only follow a hand it can see, and the console
     * does not volunteer send levels — so they have to be asked for,
     * paced like every other read on a venue's Wi-Fi.
     */
    private suspend fun pollSends() {
        val chans = AppState.config.value.channels
        for (ch in chans) {
            for (b in com.stagemix.engine.AUX_SEND_FIRST..
                     com.stagemix.engine.AUX_SEND_LAST) {
                send(OscMessage(osc("/ch/%02d/mix/%02d/level",
                    ch.index + 1, b), emptyList()))
                delay(4)
            }
        }
    }

    /**
     * What is in each wedge, and how far it is from what a monitor mix
     * for that position wants.
     */
    /**
     * THE COMPLETE MONITOR PICTURE — every wedge, every send, in dB, with
     * its in-ears/wedge type and, when the keeper is on, where it wants
     * each send. Written at takeover and then on a cadence, so the log
     * holds the whole night's monitor state, not just a snapshot of the
     * loudest few at the start. Nothing here writes a send; it only reads.
     */
    private fun dumpMonitorMatrix(t: Double) {
        val e = engine ?: return
        val lg = show ?: return
        val names = AppState.mixerChannelNames.value
        val roles = e.state.mapValues { it.value.role }
        val kit = e.drumKit()
        val floor = com.stagemix.engine.MonitorMap.MONITOR_FLOOR_DB
        fun nm(ch: Int) = (names[ch] ?: "ch%02d".format(ch + 1)).take(8)
        for (w in monitors.all()) {
            val busName = (AppState.busNames.value[w.bus - 1] ?: w.name).take(12)
            val targets = monitors.critique(w.bus, roles, kit)
                .mapNotNull { n -> n.wantDb?.let { n.ch to it } }.toMap()
            val live = w.sends.entries.filter { it.value > floor }
                .sortedByDescending { it.value }
            val off = w.sends.entries.filter { it.value <= floor }
                .map { it.key }.sorted()
            lg.note("MON", "bus%02d %-12s [%s · %s] — %d live, %d not sent"
                .format(java.util.Locale.ROOT, w.bus, busName,
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
                lg.note("MON", "    not sent: " +
                    off.joinToString(" ") { nm(it) })
        }
        lastMonMatrix = t
    }

    private fun logMonitors() {
        val e = engine ?: return
        val names = AppState.mixerChannelNames.value
        val roles = e.state.mapValues { it.value.role }
        val lg = show ?: return
        lg.note("MON", "── the monitors, read only: this app does not " +
            "write a monitor send or a bus master ──")
        dumpMonitorMatrix(now())
        for (w in monitors.all()) {
            lg.note("MON", monitors.describe(w.bus, names))
            for (n in monitors.critique(w.bus, roles, e.drumKit()).take(5)) {
                val what = if (n.wantDb == null)
                    ("%s is in this wedge at %+.1f dB and a %s monitor " +
                     "does not want it there")
                        .format(java.util.Locale.ROOT,
                            names[n.ch] ?: "ch%02d".format(n.ch + 1),
                            n.nowDb, w.kind.name.lowercase())
                else if (kotlin.math.abs(n.offDb) < 3f) continue
                else ("%s is %+.1f dB from where a %s monitor would put " +
                      "it (%s is %+.1f, the mix wants %+.1f)")
                        .format(java.util.Locale.ROOT,
                            names[n.ch] ?: "ch%02d".format(n.ch + 1),
                            -n.offDb, w.kind.name.lowercase(),
                            n.role.name.lowercase(), n.nowDb, n.wantDb)
                lg.note("MON", "  " + what)
            }
        }
    }

    private fun revert() {
        // UNDO pauses the autopilot whether or not there is an engine
        // to restore faders from — the flag flips first, so the key is
        // never silently dead. (It is also flipped at the click site
        // now, like MIX and FREEZE; this is the backstop.)
        AppState.directing.value = false
        val e = engine ?: run { noEngine("UNDO"); return }
        show?.user("you handed the mains back — restoring the takeover " +
            "faders and pausing for ${REVERT_HOLD_SEC.toInt()}s")
        for (w in e.revertToBaseline(now())) sendFader(w.channel, w.levelDb)
        doctor?.let { d ->
            for (ch in d.state.keys)
                for (w in d.reset(ch)) send(OscMessage(w.address, listOf(w.value)))
        }
        // the status bar must follow UNDO too — this was the one
        // state-changing handler that left it reading MIXING
        updateNotif()
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
        val from = lastSent[ch]
        lastSent[ch] = db
        // The reason the engine last gave for touching this channel:
        // a fader line that says only where the fader went is a number
        // without a cause, and a night of those cannot be read.
        show?.fader(ch, db, chName(ch), from,
            engine?.decisions?.firstOrNull { it.channel == ch }
                ?.let { "— ${it.kind}: ${it.reason}" }, now())
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

    private fun now(): Double = (System.nanoTime() - t0) / 1e9

    /**
     * A control was pressed before the app had an engine to act on —
     * connected but pre-takeover, or not connected at all. §5: a key
     * that does nothing and says nothing is the purest form of the
     * failure this whole project is built around not repeating. So it
     * says so, on screen and in the log.
     */
    private fun noEngine(what: String) {
        AppState.lastError.value =
            "$what needs the app to be mixing — tap MIX first"
        show?.user("$what pressed, but there is nothing to act on yet " +
            "(not mixing)")
        // refresh the status surface here too: the no-engine UNDO path
        // returns before revert()'s own updateNotif(), so without this
        // the one background surface could stay reading MIXING.
        updateNotif()
    }

    // ------------------------------------------------------------------
    /**
     * Ask for the console's Wi-Fi and hold on to it. Best effort: if the
     * request is refused or times out the app still works exactly as it
     * did before, because an unbound socket on a tablet with no cellular
     * goes out over Wi-Fi anyway. This is insurance for the tablet that
     * has a SIM in it.
     */
    private fun bindToMixerWifi() {
        if (netCallback != null) return
        val cm = getSystemService(Context.CONNECTIVITY_SERVICE)
            as? android.net.ConnectivityManager ?: return
        val req = android.net.NetworkRequest.Builder()
            .addTransportType(android.net.NetworkCapabilities.TRANSPORT_WIFI)
            // NOT NET_CAPABILITY_INTERNET: the console's AP has none, and
            // asking for it is asking for the cellular network instead
            .removeCapability(android.net.NetworkCapabilities.NET_CAPABILITY_INTERNET)
            .build()
        val cb = object : android.net.ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: android.net.Network) {
                wifiNetwork = network
                runCatching { socket?.let { network.bindSocket(it) } }
                Log.i(TAG, "bound to the mixer's Wi-Fi")
            }
            override fun onLost(network: android.net.Network) {
                if (wifiNetwork == network) wifiNetwork = null
            }
        }
        runCatching { cm.requestNetwork(req, cb); netCallback = cb }
            .onFailure { Log.w(TAG, "could not pin to Wi-Fi: ${it.message}") }
    }

    private fun releaseWifiBinding() {
        val cm = getSystemService(Context.CONNECTIVITY_SERVICE)
            as? android.net.ConnectivityManager
        netCallback?.let { cb -> runCatching { cm?.unregisterNetworkCallback(cb) } }
        netCallback = null
        wifiNetwork = null
    }

    /** send this socket out over the console's Wi-Fi, not the phone network */
    private fun bindSocket(s: DatagramSocket) {
        wifiNetwork?.let { runCatching { it.bindSocket(s) } }
    }

    private fun acquireLocks() {
        // Release any pair already held before making a new one — a
        // repeat CONNECT (the double auto-connect, a reconnect) would
        // otherwise overwrite these fields and leak the old locks for
        // the life of the process.
        runCatching { wifiLock?.takeIf { it.isHeld }?.release() }
        runCatching { wakeLock?.takeIf { it.isHeld }?.release() }
        bindToMixerWifi()
        val wm = applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
        wifiLock = wm.createWifiLock(
            WifiManager.WIFI_MODE_FULL_LOW_LATENCY, "stagemix:wifi").apply { acquire() }
        val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
        wakeLock = pm.newWakeLock(
            PowerManager.PARTIAL_WAKE_LOCK, "stagemix:engine").apply {
            setReferenceCounted(false); acquire()
        }
    }

    /**
     * The line on the tablet's status bar, which is the only thing
     * visible while the app is in the background — so it says which of
     * the two states the app is actually in rather than "running".
     * Three nights were spent in shadow without anybody noticing.
     */
    /**
     * The line in the status bar — the only thing visible while the app
     * is in the background, and the reason it exists is three shows in
     * watching mode with nothing saying so.
     *
     * It had two states and was refreshed from one place, so after
     * FREEZE, after UNDO, and after the engine gave up following five
     * errors, it went on reading "MIXING — the app has the mains" while
     * nothing whatever was being sent. That is the original failure,
     * reproduced on the one surface built to prevent it.
     */
    // Same one reading of the state as the header word and the progress
    // bar (AppState.opState), so the background notification can never
    // contradict the glass about whether — or why — the app is not mixing.
    private fun notifText(): String = when (AppState.opState()) {
        AppState.OpState.NO_MIXER -> "NO MIXER — the desk is holding your last mix"
        AppState.OpState.FROZEN -> "FROZEN — every fader held, nothing is moving"
        AppState.OpState.MUTED -> "WAITING — you have the band muted"
        AppState.OpState.WATCHING -> "SHADOW — watching only, nothing sent to the mixer"
        AppState.OpState.MIXING -> "MIXING — the app has the mains"
    }

    private fun updateNotif() {
        val nm = getSystemService(NotificationManager::class.java) ?: return
        val notif = Notification.Builder(this, CHANNEL)
            .setSmallIcon(android.R.drawable.ic_media_play)
            .setContentTitle(getString(R.string.app_name))
            .setContentText(notifText())
            .setOngoing(true)
            .build()
        runCatching { nm.notify(1, notif) }
    }

    private fun startForegroundNotif() {
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel(
            CHANNEL, getString(R.string.svc_channel),
            NotificationManager.IMPORTANCE_LOW))
        val notif = Notification.Builder(this, CHANNEL)
            .setSmallIcon(android.R.drawable.ic_media_play)
            .setContentTitle(getString(R.string.app_name))
            .setContentText(notifText())
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
            show?.footer(e, AppState.mixerChannelNames.value)
        }
        show?.close()
        AppState.conn.value = AppState.Conn.DISCONNECTED
        // NOT `directing`. A service teardown rewriting the operator's
        // own switch is how a state change gets undone behind their
        // back — and it is what made MIX look dead: the key set it, a
        // bare background service was created and immediately
        // reclaimed, and onDestroy put it straight back.
        loopJob?.cancel()
        // and every other coroutine this service launched (takeover,
        // pollSends, the rebalance pass) — they outlive the socket
        // otherwise and go on writing AppState on a dead service.
        scope.coroutineContext.cancelChildren()
        socket?.close(); socket = null
        releaseWifiBinding()
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
        /** how many times to re-ask for a fader position at takeover */
        private const val TAKEOVER_TRIES = 4
        /** how often to re-read the mute keys and chase missing faders */
        private const val RESYNC_SEC = 30.0
        /** how many engine errors before it stops trying to mix */
        private const val MAX_TICK_FAILURES = 5
        const val PORT = 10024
        const val CHANNEL = "stagemix"
        const val ACTION_CONNECT = "com.stagemix.CONNECT"
        const val ACTION_DISCONNECT = "com.stagemix.DISCONNECT"
        const val ACTION_SNAPSHOT = "com.stagemix.SNAPSHOT"
        const val ACTION_REVERT = "com.stagemix.REVERT"
        /** a log file covers one night; see the rotate above */
        const val LOG_ROTATE_HOURS = 10.0
        /** how often the whole monitor matrix is written to the log */
        const val MON_MATRIX_SEC = 60.0
        /** a frequency must have howled this often before a guard is placed */
        const val PRE_RING_MIN_RINGS = 2
        /** how deep a pre-ring guard cut is — shallow, and inaudible */
        const val PRE_RING_GUARD_DB = 3f
        const val ACTION_DIRECTING = "com.stagemix.DIRECTING"
        const val ACTION_FREEZE_ALL = "com.stagemix.FREEZE_ALL"
        const val ACTION_FREEZE_CH = "com.stagemix.FREEZE_CH"
        const val ACTION_SET_ROLE = "com.stagemix.SET_ROLE"
        const val ACTION_KEEP_BALANCE = "com.stagemix.KEEP_BALANCE"
        const val ACTION_REBALANCE = "com.stagemix.REBALANCE"
        const val ACTION_KEEP_MONITORS = "com.stagemix.KEEP_MONITORS"
        const val ACTION_MONITOR_INEARS = "com.stagemix.MONITOR_INEARS"
        const val ACTION_PRE_RING = "com.stagemix.PRE_RING"
        const val ACTION_AUTO_START = "com.stagemix.AUTO_START"
        const val ACTION_DOCTOR = "com.stagemix.DOCTOR"
        const val ACTION_FEEDBACK = "com.stagemix.FEEDBACK"

        fun cmd(ctx: Context, action: String, vararg extras: Pair<String, Any>) {
            // In the demo there is no console and there must be no
            // service. The transport keys already flip AppState at the
            // tap; starting a real service here would spin up a bare
            // instance with no engine, which Android reclaims — and its
            // onDestroy calls shutdown(), which sets conn=DISCONNECTED
            // and corrupts the very demo state the key just changed. So
            // in demo the click-site flip is the whole behaviour.
            if (DemoStage.running) return
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
