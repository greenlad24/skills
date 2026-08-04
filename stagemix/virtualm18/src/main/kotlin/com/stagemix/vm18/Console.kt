package com.stagemix.vm18

import com.stagemix.engine.FaderLaw
import com.stagemix.engine.Meters
import com.stagemix.engine.OscMessage
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetSocketAddress
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.concurrent.ConcurrentHashMap

/**
 * A Midas M18 that isn't there.
 *
 * Speaks the console's OSC on UDP 10024 well enough that the shipping
 * Android app cannot tell the difference: it answers `/xinfo`, honours
 * `/xremote`/`/xremotenfb` subscriptions with the real 10-second
 * timeout, streams `/meters/1`, `/meters/4` and `/meters/6` at the
 * console's own 50 ms cadence, answers parameter enquiries, and stores
 * every parameter the app writes.
 *
 * The faders it stores are then applied to the audio you hear, so the
 * tablet is genuinely mixing — the moves are audible in the room, not
 * just numbers on a screen.
 *
 * Two deliberate fidelities, because both have bitten this app before:
 *
 *  · faders are QUANTIZED to the console's 1024-step float, so the app
 *    gets its own writes back a hundredth of a dB off, exactly as it
 *    would live;
 *  · the echo policy is switchable. `/xremotenfb` means "do not feed
 *    my own changes back to me", and firmware that ignores that is what
 *    made the app read its first sixteen writes as sixteen human
 *    overrides and freeze solid. Run with `--echo` to be that console.
 */
class Console(
    private val port: Int = 10024,
    private val echoOwnWrites: Boolean = false,
    private val quantize: Boolean = true,
    private val name: String = "StageMix Bench",
    private val model: String = "MR18",
    private val firmware: String = "1.21",
) {
    /** every parameter the app has written or asked about */
    val params = ConcurrentHashMap<String, Float>()
    val names = ConcurrentHashMap<Int, String>()

    /** the RTA source the app has selected (channel index, 0-based) */
    @Volatile var rtaSource = 0; private set

    /** what the desk is hearing, pre-fader, per input — set by the player */
    @Volatile var inputDb = FloatArray(16) { -128f }
    @Volatile var rtaBins = FloatArray(100) { -128f }
    @Volatile var gateGr = FloatArray(16) { 0f }
    @Volatile var compGr = FloatArray(16) { 0f }

    /** fader positions in dB, for the player and the UI */
    fun faderDb(ch: Int): Float =
        FaderLaw.floatToDb(params["/ch/%02d/mix/fader".fmt(ch + 1)] ?: 0.75f)

    var onWrite: ((String, Float) -> Unit)? = null
    var log: ((String) -> Unit)? = null

    private val sock = DatagramSocket(port)
    private val subs = ConcurrentHashMap<InetSocketAddress, Long>()
    private val meterSubs = ConcurrentHashMap<Pair<InetSocketAddress, String>, Long>()
    @Volatile private var running = true
    var packetsIn = 0L; private set
    var packetsOut = 0L; private set
    var packetsDropped = 0L; private set

    /**
     * Wi-Fi, modelled. On loopback nothing is ever lost, so the engine's
     * meter-timeout freeze and its recovery never run — and those are
     * the paths that decide what happens when the radio dies mid-show.
     */
    @Volatile var lossPercent = 0.0
    @Volatile private var stallUntil = 0L
    private val rnd = java.util.Random(12345)

    /** go silent for [seconds], as a radio dropout would */
    fun stall(seconds: Double) {
        stallUntil = System.currentTimeMillis() + (seconds * 1000).toLong()
    }

    fun stalled(): Boolean = System.currentTimeMillis() < stallUntil

    init {
        for (ch in 0 until 16) {
            params["/ch/%02d/mix/fader".fmt(ch + 1)] = FaderLaw.dbToFloat(-10f)
            for (b in 1..4) params["/ch/%02d/eq/$b/g".fmt(ch + 1)] = 0.5f
            params["/ch/%02d/dyn/thr".fmt(ch + 1)] = (-20f + 60f) / 60f
        }
    }

    fun start() {
        Thread({ receiveLoop() }, "vm18-rx").apply { isDaemon = true }.start()
        Thread({ meterLoop() }, "vm18-meters").apply { isDaemon = true }.start()
        log?.invoke("virtual M18 listening on UDP $port " +
            "(${if (echoOwnWrites) "ECHOING own writes — hostile firmware"
                else "not echoing, /xremotenfb behaviour"})")
    }

    fun stop() { running = false; sock.close() }

    // ------------------------------------------------------------------
    private fun receiveLoop() {
        val buf = ByteArray(4096)
        while (running) {
            try {
                val p = DatagramPacket(buf, buf.size)
                sock.receive(p)
                packetsIn++
                val m = OscMessage.decode(p.data.copyOf(p.length)) ?: continue
                handle(m, InetSocketAddress(p.address, p.port))
            } catch (e: Exception) {
                if (running) log?.invoke("rx: ${e.message}")
            }
        }
    }

    private fun handle(m: OscMessage, from: InetSocketAddress) {
        val now = System.currentTimeMillis()
        when {
            m.address == "/xinfo" -> {
                send(from, OscMessage("/xinfo",
                    listOf(localIp(), name, model, firmware)))
            }
            m.address == "/xremote" || m.address == "/xremotenfb" -> {
                subs[from] = now
            }
            m.address == "/meters" -> {
                val id = m.stringArg(0) ?: return
                meterSubs[from to id] = now
                log?.invoke("meter subscription: $id from ${from.hostString}")
            }
            m.address == "/-stat/rta/source" -> {
                val v = m.intArg(0)
                if (v != null) {
                    rtaSource = v.coerceIn(0, 15)
                } else {
                    send(from, OscMessage(m.address, listOf(rtaSource)))
                }
            }
            m.address.endsWith("/config/name") -> {
                val ch = Regex("/ch/(\\d\\d)/config/name").find(m.address)
                    ?.groupValues?.get(1)?.toIntOrNull()
                val n = if (ch != null) names[ch - 1] ?: "" else ""
                send(from, OscMessage(m.address, listOf(n)))
            }
            else -> {
                val v = m.args.firstOrNull() as? Float
                if (v == null) {
                    // an enquiry: answer with what we hold
                    params[m.address]?.let {
                        send(from, OscMessage(m.address, listOf(it)))
                    }
                } else {
                    val stored = if (quantize) quant(v) else v
                    params[m.address] = stored
                    onWrite?.invoke(m.address, stored)
                    // a real console tells the OTHER subscribed clients;
                    // whether it tells the sender too is the nfb question
                    for (s in subs.keys) {
                        if (s == from && !echoOwnWrites) continue
                        if (now - (subs[s] ?: 0) > TTL_MS) continue
                        send(s, OscMessage(m.address, listOf(stored)))
                    }
                }
            }
        }
    }

    /** the console's fader resolution: 1024 steps over the float range */
    private fun quant(f: Float): Float =
        (Math.round(f.coerceIn(0f, 1f) * 1023f) / 1023f)

    // ------------------------------------------------------------------
    private fun meterLoop() {
        while (running) {
            try {
                val now = System.currentTimeMillis()
                for ((key, at) in meterSubs) {
                    if (now - at > TTL_MS) { meterSubs.remove(key); continue }
                    val (to, id) = key
                    when (id) {
                        "/meters/${Meters.BANK_INPUTS}" ->
                            send(to, OscMessage(id, listOf(blob(bank1()))))
                        "/meters/${Meters.BANK_RTA}" ->
                            send(to, OscMessage(id, listOf(blob(rtaBins))))
                        "/meters/${Meters.BANK_DYNAMICS}" ->
                            send(to, OscMessage(id, listOf(blob(bank6()))))
                    }
                }
                Thread.sleep(50)          // the console's own cadence
            } catch (e: Exception) {
                if (running) log?.invoke("meters: ${e.message}")
            }
        }
    }

    /** 40 values: 16 mono inputs (pre), then returns, buses, sends, mains */
    private fun bank1(): FloatArray {
        val v = FloatArray(40) { -128f }
        val src = inputDb
        for (c in 0 until 16) v[c] = src.getOrElse(c) { -128f }
        return v
    }

    /** 39 values: 16 gate GR, 16 comp GR, 6 bus, 1 main — in blocks */
    private fun bank6(): FloatArray {
        val v = FloatArray(Meters.DYN_COUNT) { 0f }
        for (c in 0 until 16) {
            v[Meters.gateGrIndex(c)] = gateGr.getOrElse(c) { 0f }
            v[Meters.compGrIndex(c)] = compGr.getOrElse(c) { 0f }
        }
        return v
    }

    /** the X-Air meter blob: LE int32 count, then LE int16 of dB x 256 */
    private fun blob(v: FloatArray): ByteArray {
        val b = ByteBuffer.allocate(4 + v.size * 2).order(ByteOrder.LITTLE_ENDIAN)
        b.putInt(v.size)
        for (x in v) b.putShort((x.coerceIn(-128f, 20f) * 256f).toInt().toShort())
        return b.array()
    }

    private fun send(to: InetSocketAddress, m: OscMessage) {
        if (stalled()) { packetsDropped++; return }
        if (lossPercent > 0 && rnd.nextDouble() * 100.0 < lossPercent) {
            packetsDropped++; return
        }
        try {
            val b = m.encode()
            sock.send(DatagramPacket(b, b.size, to))
            packetsOut++
        } catch (e: Exception) { /* the bench is not the show */ }
    }

    private fun localIp(): String = try {
        java.net.NetworkInterface.getNetworkInterfaces().toList()
            .filter { it.isUp && !it.isLoopback }
            .flatMap { it.inetAddresses.toList() }
            .firstOrNull { it is java.net.Inet4Address }?.hostAddress ?: "0.0.0.0"
    } catch (e: Exception) { "0.0.0.0" }

    fun subscriberCount(): Int {
        val now = System.currentTimeMillis()
        return subs.count { now - it.value <= TTL_MS }
    }

    companion object {
        /** the console drops a subscription after ten silent seconds */
        const val TTL_MS = 10_000L
    }
}

private fun String.fmt(vararg a: Any) =
    String.format(java.util.Locale.ROOT, this, *a)
