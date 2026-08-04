package com.stagemix.engine

import kotlin.math.abs
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * FOH autopilot scenarios: the engine leads the MAINS with its built-in
 * pyramid, no soundcheck — and can never touch a monitor bus.
 */
class FohEngineTest {

    private val chans = defaultRigProfile()

    private fun engine() = StageEngine(chans)

    /** pre-fader source levels for a sane band take */
    private fun sources() = FloatArray(16) { -80f }.also {
        it[0] = -20f   // kick
        it[11] = -21f  // bass di
        it[5] = -24f; it[6] = -24f   // piano
        it[4] = -23f   // guitar amp (solo)
        it[8] = -22f   // vocal center
    }

    private fun faders() = (0 until 16).associateWith { -10f }

    private fun run(e: StageEngine, levels: FloatArray, from: Double,
                    sec: Double): Pair<List<FaderWrite>, Double> {
        val writes = ArrayList<FaderWrite>()
        var t = from
        var nextTick = from + 1.0
        while (t < from + sec) {
            e.onMeters(levels, t)
            if (t >= nextTick) { writes += e.tick(t); nextTick += 1.0 }
            t += 0.05
        }
        return writes to t
    }

    private fun takeover(e: StageEngine): Double {
        var t = 0.0
        run(e, sources(), t, 5.0).also { t = it.second }
        e.takeover(faders(), t)
        return t
    }

    // ------------------------------------------------------------------
    @Test fun `THE invariant - only channel faders are ever written`() {
        val e = engine()
        var t = takeover(e)
        // run through drift, ducking, idle, restore situations
        val wild = sources().also { it[4] = -12f; it[8] = -35f; it[1] = -18f }
        val (w1, t1) = run(e, wild, t, 120.0)
        val (w2, _) = run(e, sources(), t1, 120.0)
        val all = w1 + w2 + e.revertToBaseline(t1 + 120.0)
        assertTrue(all.isNotEmpty())
        for (w in all)
            assertTrue(Regex("^/ch/\\d\\d/mix/fader$").matches(w.address),
                "monitor territory breached: ${w.address}")
    }

    @Test fun `no moves before takeover or during the learning window`() {
        val e = engine()
        var t = 0.0
        val (before, t1) = run(e, sources(), t, 30.0)
        assertTrue(before.isEmpty(), "must not move before takeover")
        e.takeover(faders(), t1)
        val (learning, _) = run(e, sources(), t1, 15.0)  // learnSec = 20
        assertTrue(learning.isEmpty(), "must listen before leading")
    }

    @Test fun `leads toward the pyramid - solo guitar too loud gets seated`() {
        val e = engine()
        var t = takeover(e)
        // guitar amp source way hotter than its pyramid place (-3 vs
        // foundation) warrants
        val hot = sources().also { it[4] = -14f }
        val (writes, _) = run(e, hot, t, 180.0)
        val gtr = writes.filter { it.channel == 4 }
        assertTrue(gtr.isNotEmpty(), "hot solo guitar must be seated")
        assertTrue(gtr.last().levelDb < -10f, "seat = fader below takeover")
        // slew: consecutive fader steps bounded (cut rate 3 dB/s)
        val steps = gtr.map { it.levelDb }
        for (i in 1 until steps.size)
            assertTrue(abs(steps[i] - steps[i - 1]) <= 3.05f, "no jumps")
    }

    @Test fun `vocal is steered to the top of the pyramid`() {
        val e = engine()
        var t = takeover(e)
        // vocal source quiet relative to the band: pyramid wants it on
        // top (+1 over foundation) -> engine lifts, bounded
        val buried = sources().also { it[8] = -30f }
        val (writes, _) = run(e, buried, t, 300.0)
        val vox = writes.filter { it.channel == 8 }
        assertTrue(vox.isNotEmpty(), "buried lead must be lifted")
        assertTrue(vox.last().levelDb > -10f)
        for (w in vox) {
            assertTrue(w.levelDb <= -10f + 6.01f, "bounds: baseline+6 max")
            assertTrue(w.levelDb <= 2.01f, "absolute fader cap")
        }
    }

    @Test fun `whole band swells together - pyramid intact, minimal motion`() {
        val e = engine()
        var t = takeover(e)
        run(e, sources(), t, 60.0).also { t = it.second }
        // encore: EVERYTHING +4 — contributions move with the anchor,
        // ratios intact; only foundation drift-correction may trim
        val encore = FloatArray(16) { i ->
            val s = sources()[i]; if (s > -70f) s + 4f else s }
        val (writes, _) = run(e, encore, t, 120.0)
        val ladderMoves = writes.filter {
            it.channel !in setOf(0, 3, 11, 13) }  // non-foundation
        // allow small settling motion but no big re-mix
        for (w in ladderMoves)
            assertTrue(abs(w.levelDb - (-10f)) < 3.5f,
                "encore must not trigger a re-mix: ch${w.channel} ${w.levelDb}")
    }

    @Test fun `near-clip freezes boosts, cuts still allowed`() {
        val e = engine()
        var t = takeover(e)
        // vocal buried (wants boost) but kick is slamming -1 dBFS
        val clip = sources().also { it[8] = -30f; it[0] = -1f }
        val (writes, _) = run(e, clip, t, 60.0)
        assertTrue(writes.none { it.channel == 8 && it.levelDb > -10f },
            "no boosts while an input is near clip")
    }

    @Test fun `meter dropout freezes everything`() {
        val e = engine()
        var t = takeover(e)
        run(e, sources().also { it[4] = -14f }, t, 30.0).also { t = it.second }
        val writes = ArrayList<FaderWrite>()
        repeat(20) { t += 1.0; writes += e.tick(t) }
        assertTrue(writes.isEmpty(), "no motion without fresh meters")
        assertEquals("meters lost — holding still", e.holdReason(t))
    }

    @Test fun `watchdog veto blocks all upward motion`() {
        val e = engine()
        var t = takeover(e)
        e.watchdogVeto = true
        val (writes, _) = run(e, sources().also { it[8] = -30f }, t, 120.0)
        assertTrue(writes.none { it.levelDb > -10f + 0.01f })
    }

    @Test fun `lead follows the singing mic and ducking re-aims`() {
        val e = engine()
        var t = takeover(e)
        run(e, sources(), t, 30.0).also { t = it.second }
        assertEquals(8, e.leadVocal, "initial lead is Vocal Center")
        // vocal center silent; vocal piano (9) carries the song
        val switched = sources().also { it[8] = -80f; it[9] = -22f }
        run(e, switched, t, 40.0)
        assertEquals(9, e.leadVocal, "lead must follow the song")
        assertTrue(e.decisions.any { it.kind == "lead" })
    }

    @Test fun `idle channel eases out and rejoins fast`() {
        val e = engine()
        var t = takeover(e)
        run(e, sources(), t, 30.0).also { t = it.second }
        // solo guitar tacet for 90s
        val tacet = sources().also { it[4] = -80f }
        val (w1, t1) = run(e, tacet, t, 90.0)
        assertTrue(w1.any { it.channel == 4 && it.levelDb < -10f },
            "idle guitar eases out of the mains")
        // guitar returns — fast lane back toward takeover level
        val (w2, _) = run(e, sources(), t1, 30.0)
        val back = w2.filter { it.channel == 4 }
        assertTrue(back.isNotEmpty(), "returning channel rejoins")
        assertTrue(back.last().levelDb > -13f, "restored near baseline")
    }

    @Test fun `revert hands back the exact takeover mains`() {
        val e = engine()
        var t = takeover(e)
        run(e, sources().also { it[4] = -14f; it[8] = -30f }, t, 120.0)
            .also { t = it.second }
        val writes = e.revertToBaseline(t)
        assertTrue(writes.isNotEmpty())
        for (w in writes) assertEquals(-10f, w.levelDb, 0.001f)
        assertEquals(0f, e.offsetDb(4))
    }

    @Test fun `frozen channel and frozen all never move`() {
        val e = engine()
        var t = takeover(e)
        e.freezeChannel(4, true)
        val (w1, t1) = run(e, sources().also { it[4] = -12f }, t, 60.0)
        assertTrue(w1.none { it.channel == 4 }, "frozen channel moved")
        e.frozenAll = true
        val (w2, _) = run(e, sources().also { it[8] = -30f }, t1, 30.0)
        assertTrue(w2.isEmpty(), "FREEZE ALL must stop the engine")
    }

    @Test fun `total boost budget bounds concurrent lifts`() {
        val e = engine()
        var t = takeover(e)
        // several channels quiet at once — all want lifts
        val quiet = sources().also {
            it[8] = -30f; it[5] = -32f; it[6] = -32f; it[4] = -31f }
        run(e, quiet, t, 300.0)
        // the budget is power-weighted: how much LOUDER the boosts made
        // the mains, not the arithmetic sum of the offsets
        val added = e.boostLoudnessDb()
        assertTrue(added <= e.settings.mixBoostBudgetDb + 0.6f,
            "mains boost budget exceeded: the boosts added $added dB")
    }

    @Test fun `talk channels are never automated`() {
        val e = StageEngine(listOf(
            ChannelConfig(0, "Kick", Role.FOUNDATION),
            ChannelConfig(1, "Talkback", Role.TALK)))
        var t = 0.0
        val src = floatArrayOf(-20f, -15f)
        run(e, src, t, 5.0).also { t = it.second }
        e.takeover(mapOf(0 to -10f, 1 to -10f), t)
        val (writes, _) = run(e, floatArrayOf(-20f, -5f), t, 120.0)
        assertTrue(writes.none { it.channel == 1 })
    }
}

class RolesTest {
    @Test fun `role inference matches the user's console names`() {
        assertEquals(Role.FOUNDATION, inferRole("Kick Drum"))
        assertEquals(Role.PERCUSSION, inferRole("Snare"))
        assertEquals(Role.PERCUSSION, inferRole("Overheads"))
        assertEquals(Role.FOUNDATION, inferRole("Bass Mic"))
        assertEquals(Role.SOLO_GTR, inferRole("Guitar AMP"))
        assertEquals(Role.RHYTHM_GTR, inferRole("Guitar DI"))
        assertEquals(Role.VOCAL, inferRole("Vocal Center"))
        assertEquals(Role.VOCAL, inferRole("Vocal Piano"))
        assertEquals(Role.FOUNDATION, inferRole("Bass DI"))
        assertEquals(Role.FOUNDATION, inferRole("DI2"))
        assertEquals(Role.FOUNDATION, inferRole("DI 2"))
        assertEquals(Role.FOUNDATION, inferRole("Synth Bass"))
        assertEquals(Role.KEYS, inferRole("Piano"))
        assertEquals(Role.KEYS, inferRole("Keyboard"))
        assertEquals(Role.COLOR, inferRole("Saxophone"))
        assertEquals(Role.COLOR, inferRole("Flute"))
        assertEquals(Role.COLOR, inferRole("Harmonica"))
        assertEquals(Role.PERCUSSION, inferRole("Congo 2"))
        assertEquals(Role.BACKING_VOCAL, inferRole("BGV 1"))
        assertEquals(Role.TALK, inferRole("Talkback"))
        assertEquals(Role.INSTRUMENT, inferRole("Ch 12"))
    }

    @Test fun `default rig profile is complete and sane`() {
        val rig = defaultRigProfile()
        assertEquals(16, rig.size)
        assertEquals(Role.VOCAL, rig[8].role)
        assertEquals(Role.VOCAL, rig[9].role)
        assertEquals(Role.BACKING_VOCAL, rig[10].role)
        assertEquals(Role.FOUNDATION, rig[0].role)
        assertEquals(Role.FOUNDATION, rig[11].role)
        assertEquals(Role.FOUNDATION, rig[13].role)
        assertEquals(Role.COLOR, rig[15].role)
    }

    @Test fun `pyramid puts the vocal on top and foundation dominant`() {
        assertTrue(PYRAMID[Role.VOCAL]!! > PYRAMID[Role.BACKING_VOCAL]!!)
        assertTrue(PYRAMID[Role.VOCAL]!! > PYRAMID[Role.SOLO_GTR]!!)
        assertTrue(PYRAMID[Role.FOUNDATION]!! > PYRAMID[Role.KEYS]!!)
        assertTrue(PYRAMID[Role.FOUNDATION]!! > PYRAMID[Role.PERCUSSION]!!)
    }
}
