package com.stagemix.engine

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * The wedges are the band's ears. Every test here is about what this
 * class REFUSES to do.
 */
class MonitorBalanceTest {

    /** the stage as described: bus 1 centre vocal, bus 2 guitar wedge */
    private fun rig(): Pair<MonitorMap, MonitorBalance> {
        val m = MonitorMap()
        m.onBusName(1, "CENTER MON")
        m.onBusName(2, "PIANO MON")
        m.onBusName(3, "DRUM IEM")
        return m to MonitorBalance(m)
    }

    private val roles = mapOf(
        0 to Role.FOUNDATION,      // kick
        1 to Role.DRUMS,           // snare
        3 to Role.RHYTHM_GTR,      // DI 1, the acoustic
        4 to Role.SOLO_GTR,
        8 to Role.VOCAL,
        9 to Role.VOCAL,
        11 to Role.FOUNDATION)     // bass

    private fun load(m: MonitorMap, b: MonitorBalance,
                     bus: Int, sends: Map<Int, Float>) {
        for ((ch, db) in sends) {
            m.onSend(bus, ch, db)
            b.onSend(bus, ch, db, 0.0)
        }
    }

    @Test
    fun `never writes a bus master or anything but an aux send`() {
        val (m, b) = rig()
        load(m, b, 1, mapOf(0 to -6f, 1 to -6f, 3 to -20f, 8 to -20f,
            9 to -20f, 11 to -6f))
        val w = b.plan(100.0, roles, kit = setOf(0, 1), playing = true,
            push = true)
        assertTrue(w.isNotEmpty(), "should have something to say")
        for (p in w) {
            assertTrue(isMonitorSend(p.address), "not a send: ${p.address}")
            assertFalse(p.address.startsWith("/bus/"),
                "touched a bus master: ${p.address}")
            // and the OTHER gate still refuses every one of them
            assertFalse(isSafeAddress(p.address),
                "an aux send got past isSafeAddress: ${p.address}")
        }
    }

    @Test
    fun `does nothing at all between songs`() {
        val (m, b) = rig()
        load(m, b, 1, mapOf(0 to -6f, 1 to -6f, 3 to -20f, 8 to -20f,
            9 to -20f, 11 to -6f))
        assertEquals(emptyList(), b.plan(100.0, roles, setOf(0, 1),
            playing = false, push = true))
    }

    @Test
    fun `to make the vocal louder it turns something else down`() {
        val (m, b) = rig()
        // the centre wedge with the voice buried and the bass shouting
        load(m, b, 1, mapOf(3 to -14f, 8 to -18f, 9 to -18f, 11 to -2f))
        val w = b.plan(100.0, roles, kit = emptySet(), playing = true)
        assertEquals(1, w.size)
        val ch = Regex("/ch/(\\d\\d)/").find(w[0].address)!!
            .groupValues[1].toInt() - 1
        assertTrue(ch != 8 && ch != 9,
            "raised a vocal send instead of cutting something (ch$ch)")
        // and it went DOWN
        val before = FaderLaw.dbToFloat(-2f)
        assertTrue(w[0].value < before, "that was not a cut")
    }

    @Test
    fun `takes the drum kit out of a floor wedge`() {
        val (m, b) = rig()
        load(m, b, 1, mapOf(0 to -8f, 1 to -8f, 3 to -14f, 8 to -10f,
            11 to -14f))
        val w = b.plan(100.0, roles, kit = setOf(0, 1), playing = true,
            push = true)
        val chans = w.map {
            Regex("/ch/(\\d\\d)/").find(it.address)!!
                .groupValues[1].toInt() - 1 }
        assertTrue(chans.any { it == 0 || it == 1 },
            "left the kit in a floor wedge: $chans")
    }

    @Test
    fun `leaves the kit alone in an in-ear`() {
        val (m, b) = rig()
        // bus 3 is the drummer's ears: the kit belongs there
        load(m, b, 3, mapOf(0 to -4f, 1 to -4f, 8 to -12f, 11 to -8f))
        val w = b.plan(100.0, roles, kit = setOf(0, 1), playing = true,
            push = true)
        val cut = w.mapNotNull {
            Regex("/ch/(\\d\\d)/mix/03/level").find(it.address)
                ?.groupValues?.get(1)?.toInt()?.minus(1) }
        assertFalse(0 in cut && 1 in cut,
            "took the kit out of the drummer's own in-ear")
    }

    @Test
    fun `a hand on a send is adopted and the bus is left alone`() {
        val (m, b) = rig()
        load(m, b, 1, mapOf(3 to -14f, 8 to -18f, 9 to -18f, 11 to -2f))
        // the app moves something
        val first = b.plan(100.0, roles, kit = emptySet(), playing = true)
        assertTrue(first.isNotEmpty())
        // the engineer then moves a send themselves
        b.onSend(1, 8, -9f, 200.0)
        assertTrue(b.following(1, 200.0), "did not back off after a hand")
        assertEquals(emptyList(),
            b.plan(300.0, roles, emptySet(), playing = true, push = true),
            "argued with the engineer inside the back-off window")
        // and five minutes later it is allowed again
        assertFalse(b.following(1, 520.0))
    }

    @Test
    fun `never raises a send on a microphone that has rung`() {
        val (m, b) = rig()
        // a wedge where the only fix would be to raise the vocal:
        // nothing else is above its target
        load(m, b, 1, mapOf(3 to -12f, 8 to -26f, 9 to -12f, 11 to -12f))
        b.onRing(8, 10.0)
        // well past the ring-quiet window, so only ringProne can refuse
        val w = b.plan(1000.0, roles, kit = emptySet(), playing = true,
            push = true)
        for (p in w) {
            val ch = Regex("/ch/(\\d\\d)/").find(p.address)!!
                .groupValues[1].toInt() - 1
            if (ch == 8) {
                val now = FaderLaw.floatToDb(p.value)
                assertTrue(now <= -26f + 0.01f,
                    "raised a microphone that has been in a ring")
            }
        }
    }

    @Test
    fun `no raising anywhere for a few minutes after a ring`() {
        val (_, b) = rig()
        b.onRing(4, 100.0)
        assertTrue(b.raiseBarred(1, 200.0))
        assertTrue(b.raiseBarred(2, 200.0))
        assertFalse(b.raiseBarred(1, 400.0))
    }

    @Test
    fun `a wedge already close enough is left completely alone`() {
        val (m, b) = rig()
        // Built directly from what the centre position wants, using the
        // roles this test actually declares: two voices on top, the
        // acoustic under them, the bass at the bottom. Centred on the
        // ladder's own mean, because only the gaps between the rungs
        // are the app's business — see MonitorMap.critique.
        val want = mapOf(
            8 to 8f,          // VOCAL
            9 to 8f,          // VOCAL as well, in this rig
            3 to 3f,          // RHYTHM_GTR — the DI 1 acoustic
            11 to -3f)        // FOUNDATION
        val ladderMean = want.values.average().toFloat()
        val mean = -14f
        load(m, b, 1, want.mapValues { mean + it.value - ladderMean })
        assertEquals(emptyList(),
            b.plan(100.0, roles, kit = emptySet(), playing = true,
                push = true))
    }

    @Test
    fun `total movement on one send is bounded all night`() {
        val (m, b) = rig()
        load(m, b, 1, mapOf(3 to -14f, 8 to -18f, 9 to -18f, 11 to 4f))
        var t = 100.0
        repeat(200) {
            b.plan(t, roles, kit = emptySet(), playing = true, push = true)
            t += 30.0
        }
        for (s in b.moved()) {
            assertTrue(s.appDb >= -b.maxCutDb - 0.01f,
                "cut ${s.appDb} on b${s.bus} ch${s.ch}, cap ${b.maxCutDb}")
            assertTrue(s.appDb <= b.maxRaiseDb + 0.01f,
                "raised ${s.appDb} on b${s.bus} ch${s.ch}, " +
                "cap ${b.maxRaiseDb}")
        }
    }

    @Test
    fun `one move per bus per beat unless pushed`() {
        val (m, b) = rig()
        load(m, b, 1, mapOf(0 to -4f, 1 to -4f, 3 to -24f, 8 to -24f,
            9 to -24f, 11 to -4f))
        assertEquals(1, b.plan(100.0, roles, setOf(0, 1),
            playing = true).size)
        assertTrue(b.plan(200.0, roles, setOf(0, 1),
            playing = true, push = true).size > 1)
    }

    @Test
    fun `an unknown wedge is never touched`() {
        val m = MonitorMap()
        m.onBusName(5, "AUX 5")
        val b = MonitorBalance(m)
        for (ch in listOf(0, 1, 8, 11)) {
            m.onSend(5, ch, -20f)
            b.onSend(5, ch, -20f, 0.0)
        }
        assertEquals(emptyList(), b.plan(100.0, roles, setOf(0, 1),
            playing = true, push = true))
    }

    @Test
    fun `a cut never un-routes a send below the floor`() {
        val (m, b) = rig()
        // a wedge sitting low, one channel a touch too loud
        load(m, b, 1, mapOf(3 to -55f, 8 to -52f, 9 to -55f, 11 to -50f))
        var t = 100.0
        repeat(100) {
            b.plan(t, roles, kit = emptySet(), playing = true, push = true)
            t += 30.0
        }
        for (s in b.moved())
            assertTrue(s.nowDb > com.stagemix.engine.MonitorMap.MONITOR_FLOOR_DB + 2f,
                "b${s.bus} ch${s.ch} was cut to ${s.nowDb} dB — near the " +
                "floor, effectively un-routed")
    }

    @Test
    fun `a push moves several channels but no single send twice in one press`() {
        val (m, b) = rig()
        load(m, b, 1, mapOf(3 to -14f, 8 to -18f, 9 to -18f, 11 to -2f))
        val w = b.plan(100.0, roles, kit = emptySet(), playing = true, push = true)
        val perSend = w.groupingBy { it.address }.eachCount()
        assertTrue(perSend.values.all { it == 1 },
            "a single send was moved more than once in one press: $perSend")
    }

    @Test
    fun `a stale reply just after a write is not read as a hand`() {
        val (m, b) = rig()
        load(m, b, 1, mapOf(3 to -14f, 8 to -18f, 9 to -18f, 11 to -2f))
        val w = b.plan(100.0, roles, kit = emptySet(), playing = true)
        assertTrue(w.isNotEmpty())
        val movedCh = Regex("/ch/(\\d\\d)/").find(w[0].address)!!
            .groupValues[1].toInt() - 1
        // the desk replies a moment later with the OLD level (packet lost)
        b.onSend(1, movedCh, -2f, 101.0)
        assertTrue(!b.following(1, 101.0),
            "a stale reply within the guard window tripped hand-detection")
    }
}
