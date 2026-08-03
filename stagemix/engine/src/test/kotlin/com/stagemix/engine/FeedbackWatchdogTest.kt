package com.stagemix.engine

import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class FeedbackWatchdogTest {

    private fun frame(base: Float = -55f, spikeBin: Int = -1,
                      spikeDb: Float = -10f) =
        FloatArray(100) { i -> if (i == spikeBin) spikeDb else base }

    @Test fun `sustained narrow spike triggers the veto with frequency`() {
        val w = FeedbackWatchdog()
        var t = 0.0
        repeat(12) { w.onRta(frame(spikeBin = 55, spikeDb = -12f), t); t += 0.05 }
        assertTrue(w.vetoActive, "a parked towering bin IS a howl")
        // bin 55 ~ 20*2^5.5 ≈ 905 Hz
        assertTrue(w.lastFreqHz in 700..1200, "freq ~905 Hz, got ${w.lastFreqHz}")
    }

    @Test fun `broadband crescendo never triggers`() {
        val w = FeedbackWatchdog()
        var t = 0.0
        repeat(40) { w.onRta(frame(base = -18f), t); t += 0.05 }
        assertFalse(w.vetoActive, "loud-everywhere is music, not feedback")
    }

    @Test fun `moving peak (a melody) never triggers`() {
        val w = FeedbackWatchdog()
        var t = 0.0
        repeat(40) { i ->
            w.onRta(frame(spikeBin = 30 + (i % 8) * 4, spikeDb = -12f), t)
            t += 0.05
        }
        assertFalse(w.vetoActive, "notes move; howls park")
    }

    @Test fun `quiet narrow peak (soft flute) never triggers`() {
        val w = FeedbackWatchdog()
        var t = 0.0
        repeat(40) { w.onRta(frame(base = -75f, spikeBin = 40,
            spikeDb = -50f), t); t += 0.05 }
        assertFalse(w.vetoActive, "below the floor is not a howl")
    }

    @Test fun `veto clears after the howl is gone`() {
        val w = FeedbackWatchdog()
        var t = 0.0
        repeat(12) { w.onRta(frame(spikeBin = 55, spikeDb = -12f), t); t += 0.05 }
        assertTrue(w.vetoActive)
        repeat(80) { w.onRta(frame(), t); t += 0.05 }  // 4 s clean
        assertFalse(w.vetoActive, "veto must release once it's notched/gone")
    }
}
