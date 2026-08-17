package com.stagemix.engine

import kotlin.math.abs
import kotlin.test.Test
import kotlin.test.assertEquals
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

    @Test fun `the fixed-instrument channels keep their role`() {
        val r = Rig(POLICY)
        r.start(band())
        // corrupt the roles the way the audio listener did on the night
        r.e.state[4]!!.role = Role.FOUNDATION    // ch5  guitar amp -> bass
        r.e.state[5]!!.role = Role.FOUNDATION    // ch6  piano -> bass
        r.e.state[8]!!.role = Role.FOUNDATION    // ch9  vocal -> bass
        r.run(30.0) { band() }
        assertEquals(Role.SOLO_GTR, r.e.state[4]!!.role,
            "ch5 must stay the guitar amp")
        assertEquals(Role.KEYS, r.e.state[5]!!.role, "ch6 must stay piano")
        assertEquals(Role.VOCAL, r.e.state[8]!!.role, "ch9 must stay a vocal")
    }

    @Test fun `the harmonica is held at the operator's middle`() {
        val e = StageEngine(rig, POLICY)
        assertTrue(e.volumeLocked(HARMONICA, e.state[HARMONICA]!!),
            "the harmonica must be held where the operator set it (the middle)")
        val off = StageEngine(rig, EngineSettings(mode = BalanceMode.LEAD))
        assertFalse(off.volumeLocked(HARMONICA, off.state[HARMONICA]!!),
            "with the policy off the harmonica is not held")
    }

    @Test fun `a vocal-named channel stays locked even if reclassified to bass`() {
        val e = StageEngine(rig, POLICY)
        // the audio listener has decided the vocal mic "sounds like bass" —
        // the exact failure the operator hit. Its lock must survive that.
        e.state[8]!!.role = Role.FOUNDATION       // ch09 "Vocal Center"
        assertTrue(e.volumeLocked(8, e.state[8]!!),
            "a channel the operator named a vocal must stay locked even " +
                "after the listener re-roles it")
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

    // ---- the researched balance, with the operator's "leave it"s -----

    @Test fun `the research balance keeps the low end and the colour as is`() {
        // bass + kick (FOUNDATION) and sax + harmonica (COLOR) do not move
        // from the reference pyramid; only the harmony and the vocal do.
        assertEquals(PYRAMID[Role.FOUNDATION], RESEARCH_PYRAMID[Role.FOUNDATION],
            "the low end must be left exactly as is")
        assertEquals(PYRAMID[Role.COLOR], RESEARCH_PYRAMID[Role.COLOR],
            "the sax / harmonica must be left exactly as is")
    }

    @Test fun `the research balance brings the piano and guitar forward`() {
        val ref = PYRAMID
        val res = RESEARCH_PYRAMID
        assertTrue(res[Role.KEYS]!! > ref[Role.KEYS]!!,
            "the piano must come forward toward the research balance")
        assertTrue(res[Role.SOLO_GTR]!! > ref[Role.SOLO_GTR]!!,
            "the guitar amp must come forward")
        assertTrue(res[Role.RHYTHM_GTR]!! > ref[Role.RHYTHM_GTR]!!,
            "the guitar DI must come forward")
        // vocal on top, and more forward than the reference
        assertTrue(res[Role.VOCAL]!! > res[Role.FOUNDATION]!!,
            "the vocal stays on top of the low end")
        assertTrue(res[Role.VOCAL]!! > ref[Role.VOCAL]!!,
            "the vocal sits a touch more forward")
        // the ordering the research asks for: vocal > low end > piano >
        // guitar amp > guitar DI > congas
        assertTrue(res[Role.FOUNDATION]!! > res[Role.KEYS]!!, "low end over piano")
        assertTrue(res[Role.KEYS]!! > res[Role.SOLO_GTR]!!, "piano over guitar amp")
        assertTrue(res[Role.SOLO_GTR]!! > res[Role.RHYTHM_GTR]!!, "amp over DI")
        assertTrue(res[Role.RHYTHM_GTR]!! > res[Role.PERCUSSION]!!, "DI over congas")
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

    @Test fun `the piano is not auto-featured, but the sax still is`() {
        val dec = ArrayList<Decision>()
        val r = Rig(POLICY)
        r.e.onDecision = { dec.add(it) }
        r.start(band())
        r.run(30.0) { band() }                   // settle on the steady band
        // the piano (5,6) AND the sax (14, COLOR) both step well up over
        // the band — a clear solo rise for each
        val stepped = band().also {
            it[5] = -12f; it[6] = -12f; it[14] = -12f }
        r.run(60.0) { stepped }
        val pianoFeat = dec.count {
            it.kind == "feature" && (it.channel == 5 || it.channel == 6) }
        val saxFeat = dec.count { it.kind == "feature" && it.channel == 14 }
        assertTrue(pianoFeat == 0,
            "the piano was auto-featured $pianoFeat times — it must hold " +
                "its place as the harmonic bed")
        assertTrue(saxFeat > 0,
            "the sax was never featured — the piano fix over-reached")
    }

    @Test fun `the stereo piano moves as one`() {
        val r = Rig(POLICY)
        // the two piano halves at different input levels — without pairing
        // the pyramid and the ride would steer them to different places
        val src = band().also { it[5] = -22f; it[6] = -28f }
        r.start(src)
        r.run(300.0) { src }
        val d = abs(r.e.offsetDb(5) - r.e.offsetDb(6))
        assertTrue(d < 0.3f,
            ("the two piano halves drifted %.2f dB apart — a stereo pair " +
                "must move as one").format(d))
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
