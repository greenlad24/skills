package com.stagemix.engine

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/** The feedback + cross-night learning loop. */
class LearningTest {

    private fun engine() = StageEngine(defaultRigProfile())

    @Test fun `feedback chips nudge the pyramid, bounded at plus-minus 3`() {
        val e = engine()
        repeat(10) { e.applyFeedback("vocal_up", 0.0) }
        assertEquals(3f, e.pyramidBias[Role.VOCAL]!!, 0.01f,
            "taste is bounded — ten taps cannot push past +3")
        repeat(10) { e.applyFeedback("gtr_down", 0.0) }
        assertEquals(-3f, e.pyramidBias[Role.SOLO_GTR]!!, 0.01f)
        assertTrue(e.decisions.any { it.kind == "feedback" })
    }

    @Test fun `operator override adopts the level, holds off, and learns`() {
        val e = engine()
        var t = 0.0
        val src = FloatArray(16) { -80f }.also {
            it[0] = -20f; it[11] = -21f; it[8] = -22f }
        var next = 1.0
        while (t < 5.0) { e.onMeters(src, t)
            if (t >= next) { e.tick(t); next += 1.0 }; t += 0.05 }
        e.takeover((0 until 16).associateWith { -10f }, t)
        while (t < 40.0) { e.onMeters(src, t)
            if (t >= next) { e.tick(t); next += 1.0 }; t += 0.05 }
        // the human pulls the vocal fader down 3 dB
        e.operatorOverride(8, -13f, t)
        assertEquals(1, e.overrideCount)
        assertTrue(e.decisions.any { it.kind == "override" })
        // adopted as baseline, hands off: no writes for ch 8 for a while
        val writes = ArrayList<FaderWrite>()
        val tEnd = t + 60.0
        while (t < tEnd) { e.onMeters(src, t)
            if (t >= next) { writes += e.tick(t); next += 1.0 }; t += 0.05 }
        assertTrue(writes.none { it.channel == 8 },
            "overridden channel must be left alone during the hold")
        // and the disagreement taught the vocal taste downward (bounded)
        val bias = e.pyramidBias[Role.VOCAL] ?: 0f
        assertTrue(bias in -0.51f..-0.01f,
            "override must teach a small bounded lesson, got $bias")
    }

    @Test fun `learned taste changes where the engine steers`() {
        // same vocal-near-its-place scene, stock vs taste-lowered — the
        // vocal sits close to its pyramid height so neither engine
        // saturates the +6 rail (which would mask the taste difference)
        fun runScene(e: StageEngine): Float {
            var t = 0.0; var next = 1.0
            val src = FloatArray(16) { -80f }.also {
                it[0] = -20f; it[11] = -21f; it[8] = -16f }
            while (t < 5.0) { e.onMeters(src, t)
                if (t >= next) { e.tick(t); next += 1.0 }; t += 0.05 }
            e.takeover((0 until 16).associateWith { -10f }, t)
            val tEnd = t + 240.0
            while (t < tEnd) { e.onMeters(src, t)
                if (t >= next) { e.tick(t); next += 1.0 }; t += 0.05 }
            return e.offsetDb(8)
        }
        val stock = runScene(engine())
        val tuned = engine().also {
            it.pyramidBias[Role.VOCAL] = -3f }.let { runScene(it) }
        assertTrue(tuned < stock - 1f,
            "a learned lower vocal taste must steer lower: " +
            "stock=$stock tuned=$tuned")
    }

    @Test fun `health reports something sane after mixing`() {
        val e = engine()
        var t = 0.0; var next = 1.0
        val src = FloatArray(16) { -80f }.also {
            it[0] = -20f; it[11] = -21f; it[8] = -21f }
        while (t < 5.0) { e.onMeters(src, t)
            if (t >= next) { e.tick(t); next += 1.0 }; t += 0.05 }
        e.takeover((0 until 16).associateWith { -10f }, t)
        val tEnd = t + 120.0
        while (t < tEnd) { e.onMeters(src, t)
            if (t >= next) { e.tick(t); next += 1.0 }; t += 0.05 }
        val h = e.health()
        assertTrue(h.ticks > 60, "health must accumulate")
        assertTrue(h.vocalOnTopPct in 0..100 && h.inPlacePct in 0..100)
        assertEquals(0, h.overrides)
    }
}
