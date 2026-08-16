package com.stagemix.engine

import kotlin.math.abs
import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * THE OPERATOR'S VOLUME LAW, in tests.
 *
 * The rules the engineer gave in their own words, made executable:
 *  · "1.2.3 channels should be locked and never touched in volume, as well
 *     vocal channels."
 *  · "bass channels should go down only if they are overwhelming and go up
 *     if they are underwhelming."
 *  · "the piano should be in a good spot in the middle most of the time
 *     (never be low)" and "piano and guitar should be sitting in the
 *     medium level."
 *  · "piano and guitar … EQed to never cancel each other."
 *  · "usually channel 11 is for another instrument solo."
 *
 * All of it rides behind EngineSettings.operatorPolicy, which the shipping
 * app and the bench turn on and the bare engine leaves off — so this suite
 * asks for it explicitly.
 */
class OperatorPolicyTest {

    private val rig = defaultRigProfile()
    private val POLICY = EngineSettings(mode = BalanceMode.LEAD, operatorPolicy = true)
    private val BASE = -10f

    // In the default rig: 0 kick, 1 snare, 2 overheads (the kit); 3/11/13
    // bass; 4 guitar amp, 7 guitar DI; 5/6 piano; 8/9 the vocal mics;
    // 10 "Conga / Vox 3", the guest-soloist channel.
    private val KIT = listOf(0, 1, 2)
    private val VOX = listOf(8, 9)
    private val PIANO = listOf(5, 6)
    private val GUITAR = listOf(4, 7)
    private val BASS = listOf(3, 11, 13)
    private val GUEST = 10
    private val HARMONICA = 15

    // ---- the predicates, directly -----------------------------------

    @Test fun `the kit and the vocals are locked, the guest channel is not`() {
        val e = StageEngine(rig, POLICY)
        for (i in KIT + VOX)
            assertTrue(e.volumeLocked(i, e.state[i]!!),
                "ch${i + 1} must be volume-locked under the policy")
        assertFalse(e.volumeLocked(GUEST, e.state[GUEST]!!),
            "ch11 (the guest soloist) must never be locked, even named a vocal")
    }

    @Test fun `the harmonica is held at the operator's middle`() {
        val e = StageEngine(rig, POLICY)
        assertTrue(e.volumeLocked(HARMONICA, e.state[HARMONICA]!!),
            "the harmonica must be held where the operator set it (the middle)")
        val off = StageEngine(rig, EngineSettings(mode = BalanceMode.LEAD))
        assertFalse(off.volumeLocked(HARMONICA, off.state[HARMONICA]!!),
            "with the policy off the harmonica is not held")
    }

    @Test fun `nothing is locked with the policy off`() {
        val e = StageEngine(rig, EngineSettings(mode = BalanceMode.LEAD))
        for (i in 0 until 16)
            assertFalse(e.volumeLocked(i, e.state[i]!!),
                "ch${i + 1} must not be locked when operatorPolicy is off")
    }

    @Test fun `the guest channel and the bass may solo, only under the policy`() {
        val on = StageEngine(rig, POLICY)
        val off = StageEngine(rig, EngineSettings(mode = BalanceMode.LEAD))
        assertTrue(on.isSoloist(on.state[GUEST]!!), "ch11 must be a soloist")
        assertTrue(on.isSoloist(on.state[3]!!), "the bass may solo (rarely)")
        assertFalse(off.isSoloist(off.state[3]!!),
            "with the policy off the bass is not a soloist")
    }

    // ---- complementary EQ: piano and guitar never cancel -------------

    @Test fun `piano and guitar carve complementary pockets, cut-only`() {
        val keys = STARTING_CHAINS[Role.KEYS]!!.eq
        val gtr = STARTING_CHAINS[Role.SOLO_GTR]!!.eq
        val rhythm = STARTING_CHAINS[Role.RHYTHM_GTR]!!.eq
        // Nothing is boosted into the other — the whole scheme is cut-only.
        assertTrue((keys + gtr + rhythm).all { it.gainDb < 0f },
            "the complementary carves must be cut-only")
        // The piano cedes the presence band (~2.5 kHz) to the guitar's pick.
        assertTrue(keys.any { it.hz in 2000f..3000f && it.gainDb < 0f },
            "the piano must cede the presence band to the guitar")
        // Both guitar roles cede the low-mid body (~350 Hz) to the piano.
        assertTrue(gtr.any { it.hz in 250f..500f && it.gainDb < 0f },
            "the guitar amp must cede the low-mid body to the piano")
        assertTrue(rhythm.any { it.hz in 250f..500f && it.gainDb < 0f },
            "the guitar DI must cede the low-mid body to the piano")
    }

    // ---- the same rules, across a running mix ------------------------

    /** meters at 20 Hz, engine at 1 Hz — the app's real cadence */
    private inner class Rig(settings: EngineSettings) {
        val e = StageEngine(rig, settings)
        private val rnd = java.util.Random(4242L)
        private val walk = FloatArray(16)
        private val buf = FloatArray(16)
        var t = 0.0
        val writes = ArrayList<FaderWrite>()

        private fun live(s: FloatArray): FloatArray {
            for (i in 0 until 16) {
                if (s[i] <= -60f) { buf[i] = s[i]; walk[i] = 0f; continue }
                walk[i] += -0.05f * walk[i] + rnd.nextGaussian().toFloat() * 0.6f
                buf[i] = s[i] + walk[i]
            }
            return buf
        }

        fun run(sec: Double, srcAt: (Double) -> FloatArray) {
            val end = t + sec - 1e-9
            var next = t + 1.0
            while (t < end) {
                e.onMeters(live(srcAt(t)), t)
                if (t >= next - 1e-9) {
                    for (w in e.tick(t)) writes.add(w)
                    next += 1.0
                }
                t += 0.05
            }
        }

        fun start(src: FloatArray) {
            run(5.0) { src }
            e.takeover((0 until 16).associateWith { BASE }, t)
        }
    }

    /** a full band, everything present */
    private fun band() = FloatArray(16) { -80f }.also {
        it[0] = -18f; it[1] = -20f; it[2] = -26f; it[3] = -22f
        it[4] = -19f; it[5] = -25f; it[6] = -25f; it[7] = -21f
        it[8] = -23f; it[9] = -26f; it[10] = -28f; it[11] = -17f
        it[12] = -20f; it[13] = -24f; it[14] = -20f
    }

    @Test fun `the locked channels are never written, all night`() {
        val r = Rig(POLICY)
        val src = band()
        r.start(src)
        r.run(300.0) { src }
        for (i in KIT + VOX + HARMONICA)
            assertTrue(r.writes.none { it.channel == i },
                "ch${i + 1} is locked but the app wrote its fader " +
                    "${r.writes.count { it.channel == i }} times")
    }

    @Test fun `piano and guitar are never held low`() {
        val r = Rig(POLICY)
        val src = band()
        r.start(src)
        r.run(300.0) { src }
        for (i in PIANO + GUITAR) {
            val off = r.e.offsetDb(i)
            assertTrue(off >= POLICY.midFloorDb - 0.25f,
                "ch${i + 1} was held at ${off} dB — below the middle floor " +
                    "of ${POLICY.midFloorDb} dB")
        }
    }

    @Test fun `the bass is not ridden by small errors`() {
        // The bass sits where the operator put it and is not chased by the
        // ordinary drift that moves everything else. Off vs on: the wide
        // deadband must cost the bass far less travel.
        fun bassTravel(settings: EngineSettings): Float {
            val r = Rig(settings)
            val src = band()
            r.start(src)
            val last = HashMap<Int, Float>()
            var moved = 0f
            r.run(300.0) { src }
            for (w in r.writes) if (w.channel in BASS) {
                last[w.channel]?.let { moved += abs(w.levelDb - it) }
                last[w.channel] = w.levelDb
            }
            return moved
        }
        val on = bassTravel(POLICY)
        println("bass travel over 5 min — policy on: %.2f dB".format(on))
        // With the deadband the bass barely moves; a couple of dB of
        // one-time convergence is fine, a continuous chase is not.
        assertTrue(on < 3f, "the bass moved $on dB under the policy — it is " +
            "being ridden, not held")
    }
}
