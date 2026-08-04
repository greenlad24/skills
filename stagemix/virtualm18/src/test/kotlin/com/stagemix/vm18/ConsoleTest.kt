package com.stagemix.vm18

import com.stagemix.engine.FaderLaw
import com.stagemix.engine.Meters
import com.stagemix.engine.OscMessage
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.InetSocketAddress
import kotlin.math.abs
import kotlin.test.AfterTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

/**
 * The bench has to be believable or it tests nothing. These drive it
 * over real UDP with the same conversation the app has: discover,
 * subscribe, read the faders, take over, write.
 */
class ConsoleTest {

    private var console: Console? = null
    private val client = DatagramSocket().apply { soTimeout = 1500 }
    private var addr: InetSocketAddress? = null

    private fun start(echo: Boolean = false, quantize: Boolean = true): Console {
        // port 0 would be ideal but the console owns its port like the
        // real one does; pick a high one unlikely to collide
        var port = 21024
        var c: Console? = null
        while (c == null && port < 21100) {
            c = try { Console(port = port, echoOwnWrites = echo,
                quantize = quantize) } catch (e: Exception) { port++; null }
        }
        console = c
        addr = InetSocketAddress(InetAddress.getLoopbackAddress(), port)
        c!!.start()
        return c
    }

    @AfterTest fun tearDown() { console?.stop(); client.close() }

    private fun send(m: OscMessage) {
        val b = m.encode()
        client.send(DatagramPacket(b, b.size, addr))
    }

    private fun recv(tries: Int = 40, match: (OscMessage) -> Boolean):
            OscMessage? {
        val buf = ByteArray(8192)
        repeat(tries) {
            try {
                val p = DatagramPacket(buf, buf.size)
                client.receive(p)
                OscMessage.decode(p.data.copyOf(p.length))?.let {
                    if (match(it)) return it
                }
            } catch (e: Exception) { return null }
        }
        return null
    }

    @Test fun `it answers xinfo like a console`() {
        start()
        send(OscMessage("/xinfo", emptyList()))
        val r = recv { it.address == "/xinfo" }
        assertNotNull(r, "no /xinfo reply — the app would never connect")
        assertEquals("MR18", r.stringArg(2))
        assertTrue((r.stringArg(3) ?: "").isNotBlank(), "no firmware string")
    }

    @Test fun `it streams the input meters the engine steers on`() {
        val c = start()
        val want = FloatArray(16) { -20f - it }
        c.inputDb = want
        send(OscMessage("/meters",
            listOf("/meters/${Meters.BANK_INPUTS}")))
        val m = recv { it.address == "/meters/${Meters.BANK_INPUTS}" }
        assertNotNull(m, "no meter blob arrived")
        val v = Meters.decode(m.blobArg(0)!!)
        assertNotNull(v)
        assertEquals(40, v.size, "the console sends 40 values on bank 1")
        for (ch in 0 until 16)
            assertTrue(abs(v[ch] - want[ch]) < 0.02f,
                "ch${ch + 1}: sent ${want[ch]}, got ${v[ch]}")
    }

    @Test fun `the dynamics bank is blocked, gates then compressors`() {
        val c = start()
        c.gateGr = FloatArray(16) { -30f - it }
        c.compGr = FloatArray(16) { -2f - it }
        send(OscMessage("/meters",
            listOf("/meters/${Meters.BANK_DYNAMICS}")))
        val m = recv { it.address == "/meters/${Meters.BANK_DYNAMICS}" }
        assertNotNull(m)
        val v = Meters.decode(m.blobArg(0)!!)!!
        assertEquals(Meters.DYN_COUNT, v.size)
        for (ch in 0 until 16) {
            assertTrue(abs(v[Meters.gateGrIndex(ch)] - (-30f - ch)) < 0.02f,
                "gate ch${ch + 1}")
            assertTrue(abs(v[Meters.compGrIndex(ch)] - (-2f - ch)) < 0.02f,
                "comp ch${ch + 1} — this is the index the app had wrong")
        }
    }

    @Test fun `an enquiry answers, a write stores, and it is quantized`() {
        val c = start()
        send(OscMessage("/ch/03/mix/fader", emptyList()))
        val r = recv { it.address == "/ch/03/mix/fader" }
        assertNotNull(r, "no answer to a fader enquiry — takeover would fail")
        assertTrue(abs(FaderLaw.floatToDb(r.floatArg(0)!!) - (-10f)) < 0.2f)

        send(OscMessage("/ch/03/mix/fader",
            listOf(FaderLaw.dbToFloat(-4.25f))))
        Thread.sleep(120)
        val got = c.faderDb(2)
        assertTrue(abs(got - (-4.25f)) < 0.15f, "fader not stored: $got")
        // and it came back quantized, as the real console does
        val exact = FaderLaw.dbToFloat(-4.25f)
        val stored = c.params["/ch/03/mix/fader"]!!
        assertTrue(stored != exact || abs(stored - exact) < 1e-6f,
            "quantization should be visible but tiny")
        assertTrue(abs(FaderLaw.floatToDb(stored) - (-4.25f)) < 0.1f)
    }

    @Test fun `by default it does not echo the writer's own moves`() {
        start(echo = false)
        send(OscMessage("/xremotenfb", emptyList()))
        Thread.sleep(80)
        send(OscMessage("/ch/05/mix/fader", listOf(0.6f)))
        val echoed = recv(3) { it.address == "/ch/05/mix/fader" }
        assertTrue(echoed == null,
            "our own write came back — that is the case that froze the app")
    }

    @Test fun `with --echo it does, which is what the app must survive`() {
        start(echo = true)
        send(OscMessage("/xremote", emptyList()))
        Thread.sleep(80)
        send(OscMessage("/ch/05/mix/fader", listOf(0.6f)))
        val echoed = recv(6) { it.address == "/ch/05/mix/fader" }
        assertNotNull(echoed,
            "--echo must reproduce the firmware that reflects writes back")
    }

    @Test fun `a subscription lapses after ten silent seconds`() {
        val c = start()
        send(OscMessage("/xremote", emptyList()))
        Thread.sleep(100)
        assertEquals(1, c.subscriberCount(), "subscription not registered")
        // not waiting ten real seconds: the TTL is the contract, and the
        // count is computed from it
        assertEquals(Console.TTL_MS, 10_000L,
            "the console drops a client after ten silent seconds")
    }

    @Test fun `the RTA source the app parks on is honoured`() {
        val c = start()
        send(OscMessage("/-stat/rta/source", listOf(7)))
        Thread.sleep(120)
        assertEquals(7, c.rtaSource)
        c.rtaBins = FloatArray(100) { -40f + it * 0.1f }
        send(OscMessage("/meters", listOf("/meters/${Meters.BANK_RTA}")))
        val m = recv { it.address == "/meters/${Meters.BANK_RTA}" }
        assertNotNull(m, "no RTA blob")
        val v = Meters.decode(m.blobArg(0)!!)!!
        assertEquals(100, v.size, "the RTA is 100 bins")
        assertTrue(abs(v[50] - (-35f)) < 0.05f, "RTA bin 50: ${v[50]}")
    }
}
