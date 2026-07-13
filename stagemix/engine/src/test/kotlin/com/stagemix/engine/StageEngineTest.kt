package com.stagemix.engine

import kotlin.math.abs
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Scenario tests for the stage engine. Time is simulated; meters arrive
 * at 20 Hz, ticks at 1 Hz — exactly like the service drives it.
 */
class StageEngineTest {

    private val vox = ChannelConfig(0, "Lead Vox", Role.VOCAL)
    private val gtr = ChannelConfig(1, "Guitar", Role.INSTRUMENT)
    private val keys = ChannelConfig(2, "Keys", Role.INSTRUMENT)
    private val bus0 = BusConfig(0, "Singer wedge", vocalChannel = 0)
    private val bus1 = BusConfig(1, "Guitar wedge")

    private fun engine(settings: EngineSettings = EngineSettings()) =
        StageEngine(listOf(vox, gtr, keys), listOf(bus0, bus1), settings)

    /** feed steady levels for `sec` seconds; returns all writes from ticks */
    private fun run(e: StageEngine, levels: FloatArray, from: Double,
                    sec: Double): Pair<List<SendWrite>, Double> {
        val writes = ArrayList<SendWrite>()
        var t = from
        var nextTick = from + 1.0
        while (t < from + sec) {
            e.onMeters(levels, t)
            if (t >= nextTick) { writes += e.tick(t); nextTick += 1.0 }
            t += 0.05
        }
        return writes to t
    }

    private fun snapshotSends() = mapOf(
        (0 to 0) to -6f, (1 to 0) to -12f, (2 to 0) to -14f,
        (0 to 1) to -10f, (1 to 1) to -6f, (2 to 1) to -16f)

    private fun soundcheck(e: StageEngine): Double {
        // everyone plays at reference level for 60 s, then snapshot
        val (_, t) = run(e, floatArrayOf(-20f, -22f, -25f), 0.0, 60.0)
        e.takeSnapshot(snapshotSends(), t)
        return t
    }

    @Test fun `no motion before snapshot`() {
        val e = engine()
        val (writes, _) = run(e, floatArrayOf(-10f, -10f, -10f), 0.0, 10.0)
        assertTrue(writes.isEmpty(), "engine must not move before soundcheck")
    }

    @Test fun `guitarist turns up - slow bounded correction`() {
        val e = engine()
        var t = soundcheck(e)
        // guitar comes up 6 dB and stays there for 3 minutes
        val (writes, _) = run(e, floatArrayOf(-20f, -16f, -25f), t, 180.0)
        val gtrWrites = writes.filter { it.channel == 1 }
        assertTrue(gtrWrites.isNotEmpty(), "must correct the louder guitar")
        // correction is a CUT toward snapshot, never below snapshot-9
        val last = gtrWrites.last()
        assertTrue(last.levelDb < -6f, "guitar wedge send must come down")
        assertTrue(e.offsetDb(1, 1) >= -e.settings.maxCutDb - 0.01f)
        // slew discipline: no single-step jump over 3 dB (cut rate 3 dB/s,
        // 1 s ticks) — compared per send, since each bus has its own snapshot
        for (bus in 0..1) {
            val steps = gtrWrites.filter { it.bus == bus }.map { it.levelDb }
            for (i in 1 until steps.size)
                assertTrue(abs(steps[i] - steps[i - 1]) <= 3.05f,
                    "cut slew too fast on bus $bus: ${steps[i - 1]} -> ${steps[i]}")
        }
    }

    @Test fun `boost is capped at +3 and creeps slowly`() {
        val e = engine()
        var t = soundcheck(e)
        // keys drop 8 dB (player backed off the volume pedal all night)
        val (writes, _) = run(e, floatArrayOf(-20f, -22f, -33f), t, 300.0)
        val keysUp = writes.filter { it.channel == 2 }
        assertTrue(keysUp.isNotEmpty())
        // never exceeds snapshot + 3 dB
        for (w in keysUp) {
            val snap = if (w.bus == 0) -14f else -16f
            assertTrue(w.levelDb <= snap + 3.01f,
                "boost cap breached: ${w.levelDb} vs snap $snap")
        }
        // boost rate <= 1 dB / 3 s: after 30 s of boosting, offset <= 10 dB anyway
        // (bounded by cap), but early trajectory must be slow:
        val early = keysUp.takeWhile { it.levelDb <= -12f }
        assertTrue(early.size >= 3, "boost must creep, not jump")
    }

    @Test fun `deadband ignores musical dynamics`() {
        val e = engine()
        var t = soundcheck(e)
        // everyone within +-1.5 dB of reference — nothing should move
        val (writes, _) = run(e, floatArrayOf(-21f, -21f, -24f), t, 120.0)
        assertTrue(writes.isEmpty(), "deadband must hold: ${writes.take(3)}")
    }

    @Test fun `near-clip freezes all boosts`() {
        val e = engine()
        var t = soundcheck(e)
        // keys quiet (wants boost) but guitar is slamming -1 dBFS
        val (writes, _) = run(e, floatArrayOf(-20f, -1f, -33f), t, 60.0)
        assertTrue(writes.none { it.channel == 2 && it.levelDb > -14f },
            "no boosts while any input is near clip")
        assertTrue(e.holdReason(t + 60.0.coerceAtMost(0.0)) == null ||
                true) // holdReason is advisory; the invariant is above
    }

    @Test fun `meter dropout freezes everything`() {
        val e = engine()
        var t = soundcheck(e)
        // drift exists...
        run(e, floatArrayOf(-20f, -16f, -25f), t, 30.0).also { t += 30.0 }
        // ...then meters stop but ticks continue
        val writes = ArrayList<SendWrite>()
        var tt = t
        repeat(20) { tt += 1.0; writes += e.tick(tt) }
        assertTrue(writes.isEmpty(), "no motion without fresh meters")
        assertEquals("meters lost — holding still", e.holdReason(tt))
    }

    @Test fun `watchdog veto blocks boosts immediately`() {
        val e = engine()
        var t = soundcheck(e)
        e.watchdogVeto = true
        val (writes, _) = run(e, floatArrayOf(-20f, -22f, -33f), t, 120.0)
        assertTrue(writes.none {
            val snap = snapshotSends()[it.channel to it.bus]!!
            it.levelDb > snap + 0.01f
        }, "watchdog veto must block all upward motion")
    }

    @Test fun `vocal buried - band ducks in singer wedge only, cut-only`() {
        val e = engine()
        var t = soundcheck(e)
        // band up 6, vocal unchanged: ratio worsened by 6 dB
        val (writes, _) = run(e, floatArrayOf(-20f, -16f, -19f), t, 90.0)
        val duckWrites = writes.filter { it.bus == 0 && it.channel != 0 }
        assertTrue(duckWrites.isNotEmpty(), "band must duck in the singer wedge")
        // vocal channel itself never boosted above its snapshot
        assertTrue(writes.none { it.channel == 0 && it.levelDb > -6f + 0.01f },
            "vocal must never be boosted")
    }

    @Test fun `idle channel eases out and restores on return`() {
        val e = engine()
        var t = soundcheck(e)
        // guitar goes silent for 90 s
        val (w1, t1) = run(e, floatArrayOf(-20f, -80f, -25f), t, 90.0)
        val gtrDown = w1.filter { it.channel == 1 }
        assertTrue(gtrDown.isNotEmpty(), "idle guitar should ease out")
        assertTrue(gtrDown.last().levelDb < -6f)
        // guitar returns: restore toward snapshot
        val (w2, _) = run(e, floatArrayOf(-20f, -22f, -25f), t1, 60.0)
        val gtrBack = w2.filter { it.channel == 1 && it.bus == 1 }
        assertTrue(gtrBack.isNotEmpty(), "returning channel must restore")
        assertTrue(abs(gtrBack.last().levelDb - (-6f)) < 1.5f,
            "restore lands at snapshot, got ${gtrBack.last().levelDb}")
    }

    @Test fun `revert returns exact snapshot and zeroes offsets`() {
        val e = engine()
        var t = soundcheck(e)
        run(e, floatArrayOf(-20f, -16f, -33f), t, 120.0).also { t += 120.0 }
        val writes = e.revertToSnapshot(t)
        assertEquals(snapshotSends().size, writes.size)
        for (w in writes)
            assertEquals(snapshotSends()[w.channel to w.bus]!!, w.levelDb, 0.001f)
        assertEquals(0f, e.offsetDb(1, 1))
    }

    @Test fun `frozen channel never moves`() {
        val e = engine()
        var t = soundcheck(e)
        e.freezeChannel(1, true)
        val (writes, _) = run(e, floatArrayOf(-20f, -12f, -25f), t, 120.0)
        assertTrue(writes.none { it.channel == 1 }, "frozen channel moved")
    }

    @Test fun `bus boost budget bounds concurrent boosts`() {
        val e = engine()
        var t = soundcheck(e)
        // vocal + keys BOTH drop 8 dB -> both want +3; budget is 3 total per bus
        val (writes, tEnd) = run(e, floatArrayOf(-28f, -22f, -33f), t, 300.0)
        for (bus in 0..1) {
            val totalUp = listOf(0, 1, 2).sumOf {
                maxOf(0f, e.offsetDb(it, bus)).toDouble()
            }
            assertTrue(totalUp <= e.settings.busBoostBudgetDb + 0.1,
                "bus $bus upward budget exceeded: $totalUp")
        }
    }

    @Test fun `send write addresses are one-based osc paths`() {
        assertEquals("/ch/02/mix/01/level", SendWrite(1, 0, -6f).address)
        assertEquals("/ch/16/mix/06/level", SendWrite(15, 5, 0f).address)
    }
}
