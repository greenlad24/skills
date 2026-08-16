package com.stagemix.engine

import kotlin.test.Test
import kotlin.test.assertTrue

/**
 * §4: "never raise a microphone that has been in a ring; no raising
 * anywhere on the stage for several minutes after a howl." A solo on an
 * open mic is exactly what rings it, so once the app has traced a loop
 * to a microphone the mains engine must not lift it straight back in.
 */
class RingMemoryTest {

    private fun engine(): StageEngine {
        val e = StageEngine(defaultRigProfile(),
            EngineSettings(mode = BalanceMode.KEEP))
        val faders = HashMap<Int, Float>()
        for (i in 0 until 16) faders[i] = -6f
        e.takeover(faders, 0.0)
        return e
    }

    /** the sax (ch15 / index 14, a COLOR soloist) at a given level */
    private fun band(saxDb: Float): FloatArray {
        val lv = FloatArray(16) { -70f }
        lv[0] = -14f; lv[1] = -16f          // kit
        lv[8] = -12f                         // lead vocal
        lv[11] = -14f; lv[13] = -15f         // both bass DIs
        lv[14] = saxDb                       // the sax
        return lv
    }

    @Test
    fun `a ring ends a feature already in progress and eases it down`() {
        val e = engine()
        val sax = e.state[14]!!
        // stand a feature up by hand, so the test is about onRing alone
        sax.featureStart = 10.0
        sax.offset = 4f
        e.onRing(14, 12.0)
        assertTrue(sax.featureStart < 0,
            "a ring left the feature latched — the mic stays lifted in the loop")
        assertTrue(sax.featureReleaseAt >= 0.0,
            "a ring did not schedule the lift to ease back down")
        assertTrue(sax.rangAt == 12.0, "the ring time was not remembered")
    }

    @Test
    fun `a mic that just rang is not lifted as a new feature`() {
        val e = engine()
        var t = 0.0
        repeat(300) { e.onMeters(band(-25f), t); e.tick(t); t += 0.25 }
        e.adoptBalance(t)
        repeat(80) { e.onMeters(band(-25f), t); e.tick(t); t += 0.25 }

        // the app traces a howl to this mic and notches it
        e.onRing(14, t)
        val ringT = t

        // the player now steps right out — the classic feature rise, but
        // seconds after the ring, well inside the quiet window
        repeat(200) { e.onMeters(band(-8f), t); e.tick(t); t += 0.25 }

        val sax = e.state[14]!!
        assertTrue(t - ringT < RING_QUIET_SEC,
            "test drove past the quiet window; tighten it")
        assertTrue(sax.featureStart < 0,
            "a mic that rang ${t - sax.rangAt}s ago was featured and " +
            "lifted straight back into the loop")
    }

    @Test
    fun `the ride does not raise a mic that just rang`() {
        val e = engine()
        var t = 0.0
        // settle a balance with the sax present
        repeat(300) { e.onMeters(band(-20f), t); e.tick(t); t += 0.25 }
        e.adoptBalance(t)
        repeat(120) { e.onMeters(band(-20f), t); e.tick(t); t += 0.25 }
        val sax = e.state[14]!!
        val offAtRing = sax.offset

        // it rings, then the player drops well below plan — the exact
        // condition under which the ride would otherwise raise the fader
        e.onRing(14, t)
        val ringT = t
        repeat(760) { e.onMeters(band(-33f), t); e.tick(t); t += 0.25 }

        assertTrue(t - ringT < RING_QUIET_SEC,
            "test drove past the quiet window; tighten it")
        assertTrue(sax.offset <= offAtRing + 0.2f,
            "the ride pushed a mic that rang UP by " +
            "${sax.offset - offAtRing} dB, inside the quiet window")
    }

    @Test
    fun `ringing one half of a stereo pair ends both features`() {
        val e = engine()
        // piano is a stereo pair (idx 5 and 6 in the default rig)
        val l = e.state[5]!!
        val r = e.state[6]!!
        // stand both halves up by hand, as the pair-latch would
        l.featureStart = 10.0; l.offset = 4f
        r.featureStart = 10.0; r.offset = 4f
        r.cfg.pairWith?.let { assertTrue(it == 5, "rig pairing changed") }

        // only the LEFT half rings
        e.onRing(5, 12.0)
        assertTrue(l.featureStart < 0 && r.featureStart < 0,
            "a ring on one half left the other half featured and lifted " +
            "— the image would collapse to one side")
        assertTrue(l.rangAt == 12.0 && r.rangAt == 12.0,
            "both halves must be marked quiet so neither is re-lifted alone")
    }
}
