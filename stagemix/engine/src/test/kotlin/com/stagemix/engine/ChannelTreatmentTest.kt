package com.stagemix.engine

import kotlin.math.abs
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * The chain, set once.
 *
 * "once it recognize what is each channel — I want it to do EQ,
 * compression and reverb (only for the ones that need reverb) once —
 * then adjust EQ only if major changes in the sound happen for a
 * channel. If not, it would be only balance work."
 *
 * Every test here is one clause of that sentence, plus the one clause
 * that was not in it and matters more than any of them: this must never
 * write to a monitor bus.
 */
class ChannelTreatmentTest {

    private fun verdict(c: Float) =
        InstrumentId.Verdict(Family.VOICELIKE, c, "because")

    private fun spec(seed: Int = 0): DoubleArray {
        val d = DoubleArray(100)
        for (i in 0 until 100) d[i] = if ((i + seed) % 10 == 0) 0.1 else 0.0
        return d
    }

    // ------------------------------------------------------------------
    @Test fun `an aux send can never be written, however it is asked for`() {
        // The wedges and the in-ears are the band's, absolutely. On this
        // desk the difference between a reverb send and a musician's
        // monitor is one digit in the address, so it is a whitelist and
        // this test's whole job is to try to get past it.
        for (b in AUX_SEND_FIRST..AUX_SEND_LAST)
            assertTrue(!isSafeAddress("/ch/09/mix/%02d/level".format(b)),
                "aux send $b must be refused")
        for (b in FX_SEND_FIRST..FX_SEND_LAST)
            assertTrue(isSafeAddress("/ch/09/mix/%02d/level".format(b)),
                "FX send $b is channel processing, not somebody's ears")
        // and the things that are not sends at all
        assertTrue(isSafeAddress("/ch/01/eq/2/g"))
        assertTrue(isSafeAddress("/ch/16/preamp/hpf"))
        assertTrue(isSafeAddress("/ch/16/dyn/thr"))
        assertTrue(!isSafeAddress("/ch/01/mix/fader"),
            "the fader is the balance's business, not the chain's")
        assertTrue(!isSafeAddress("/bus/1/mix/fader"))
        assertTrue(!isSafeAddress("/ch/01/mix/01/on"))
        assertTrue(!isSafeAddress("/lr/mix/fader"))
        assertTrue(!isSafeAddress("/config/mute/1"))
    }

    @Test fun `no chain ever emits anything but channel processing`() {
        // Belt and braces: run every role's chain and check every single
        // address it produces, rather than trusting the book to be right.
        for (role in Role.values()) {
            val t = ChannelTreatment()
            val w = t.consider(3, role, verdict(0.9f), 1f, spec(), 100.0)
            for (p in w) assertTrue(isSafeAddress(p.address),
                "${role.name} chain produced ${p.address}")
        }
    }

    // ------------------------------------------------------------------
    @Test fun `the chain goes on once and then stops`() {
        val t = ChannelTreatment()
        val first = t.consider(0, Role.VOCAL, verdict(0.9f), 1f, spec(), 100.0)
        assertTrue(first.isNotEmpty(), "a confident vocal gets its chain")
        assertEquals(Role.VOCAL, t.treatedRole(0))
        // and then nothing, for the rest of the night, on the same sound
        for (s in 1..600 step 7)
            assertTrue(t.consider(0, Role.VOCAL, verdict(0.9f), 1f,
                spec(), 100.0 + s).isEmpty(),
                "the chain must not be re-applied at t=$s")
    }

    @Test fun `an unsure identification is not treated at all`() {
        val t = ChannelTreatment()
        assertTrue(t.consider(0, Role.VOCAL, null, 1f, spec(), 100.0).isEmpty(),
            "no verdict, no chain")
        assertTrue(t.consider(0, Role.VOCAL, verdict(0.3f), 1f, spec(), 100.0)
            .isEmpty(), "a coin-flip verdict is not grounds for EQ")
        assertTrue(t.consider(0, Role.VOCAL, verdict(0.9f), 0.2f, spec(), 100.0)
            .isEmpty(), "nor is a confident verdict with no listening behind it")
    }

    @Test fun `the instrument changing is material, immediately`() {
        val t = ChannelTreatment()
        t.consider(0, Role.VOCAL, verdict(0.9f), 1f, spec(), 100.0)
        // too soon: even a new instrument waits out the minimum gap,
        // because a role flapping back and forth must not flap the EQ
        assertTrue(t.consider(0, Role.FOUNDATION, verdict(0.9f), 1f,
            spec(), 150.0).isEmpty())
        val w = t.consider(0, Role.FOUNDATION, verdict(0.9f), 1f, spec(), 400.0)
        assertTrue(w.isNotEmpty(), "a different instrument gets a new chain")
        assertEquals(Role.FOUNDATION, t.treatedRole(0))
    }

    @Test fun `a passing change of sound is not a reason to re-EQ`() {
        val t = ChannelTreatment()
        val a = spec(0)
        t.consider(0, Role.VOCAL, verdict(0.9f), 1f, a, 100.0)
        val b = spec(3)                    // a genuinely different spectrum
        assertTrue(distanceOf(a, b) > 0.55f, "the fixture must be a real change")
        // it has to LAST: a chorus, a solo and a singer leaning in all
        // move a spectrum for a few seconds
        assertTrue(t.consider(0, Role.VOCAL, verdict(0.9f), 1f, b, 400.0)
            .isEmpty(), "first sighting only starts the clock")
        assertTrue(t.consider(0, Role.VOCAL, verdict(0.9f), 1f, b, 410.0)
            .isEmpty(), "ten seconds is not a new instrument")
        assertTrue(t.consider(0, Role.VOCAL, verdict(0.9f), 1f, a, 415.0)
            .isEmpty(), "and going back resets it")
        assertTrue(t.consider(0, Role.VOCAL, verdict(0.9f), 1f, b, 500.0)
            .isEmpty())
        assertTrue(t.consider(0, Role.VOCAL, verdict(0.9f), 1f, b, 560.0)
            .isNotEmpty(), "a change that lasts half a minute is real")
    }

    private fun distanceOf(a: DoubleArray, b: DoubleArray): Float {
        var s = 0.0
        for (i in a.indices) s += abs(a[i] - b[i])
        return s.toFloat()
    }

    // ------------------------------------------------------------------
    @Test fun `reverb goes only where it belongs`() {
        // "only for the ones that need reverb". Reverb on the low end is
        // how a room turns to mud; on a talkback mic it is just strange.
        val wet = listOf(Role.VOCAL, Role.BACKING_VOCAL, Role.PERCUSSION,
            Role.KEYS, Role.COLOR, Role.SOLO_GTR)
        val dry = listOf(Role.FOUNDATION, Role.RHYTHM_GTR)
        for (r in wet) assertTrue(STARTING_CHAINS[r]?.reverbSendDb != null,
            "${r.name} should sit in some room")
        for (r in dry) assertTrue(STARTING_CHAINS[r]?.reverbSendDb == null,
            "${r.name} must stay dry")
        assertTrue(STARTING_CHAINS[Role.TALK] == null,
            "a talkback mic gets no chain at all")
        assertTrue(STARTING_CHAINS[Role.INSTRUMENT] == null,
            "an unclassified channel is not a thing to process on a guess")
        // and the backing vocals sit further back than the lead
        assertTrue(STARTING_CHAINS[Role.BACKING_VOCAL]!!.reverbSendDb!! >
            STARTING_CHAINS[Role.VOCAL]!!.reverbSendDb!!)
    }

    @Test fun `reverb can be switched off entirely`() {
        val t = ChannelTreatment(TreatmentSettings(reverbEnabled = false))
        val w = t.consider(0, Role.VOCAL, verdict(0.9f), 1f, spec(), 100.0)
        assertTrue(w.isNotEmpty())
        assertTrue(w.none { "/mix/" in it.address },
            "with reverb off nothing on a send bus is written at all")
    }

    // ------------------------------------------------------------------
    @Test fun `a band the human has moved is never set again`() {
        val t = ChannelTreatment()
        t.humanTouched(0, "/ch/01/eq/3/g")
        val w = t.consider(0, Role.VOCAL, verdict(0.9f), 1f, spec(), 100.0)
        assertTrue(w.none { it.address == "/ch/01/eq/3/g" },
            "the engineer moved that band; it is theirs now")
        assertTrue(w.any { it.address == "/ch/01/eq/1/g" },
            "the bands they did not touch are still ours to set")
    }

    // ------------------------------------------------------------------
    @Test fun `the parameter laws land where an engineer would expect`() {
        // A wrong law is silent: it writes a plausible float and the
        // console does something entirely different with it.
        val C = ChannelTreatment.Companion
        assertEquals(0.5f, C.eqGainToFloat(0f), 0.001f)
        assertEquals(1f, C.eqGainToFloat(15f), 0.001f)
        assertEquals(0f, C.eqGainToFloat(-15f), 0.001f)
        assertEquals(0.5f, C.eqGainToFloat(100f), 0.001f + 0.5f)  // clamped

        assertEquals(1f, C.thrToFloat(0f), 0.001f)
        assertEquals(0f, C.thrToFloat(-60f), 0.001f)
        assertEquals(0.5f, C.thrToFloat(-30f), 0.001f)

        // 20 Hz at the bottom, 20 kHz at the top, and a decade is a third
        assertEquals(0f, C.freqToFloat(20f), 0.001f)
        assertEquals(1f, C.freqToFloat(20000f), 0.001f)
        assertEquals(1f / 3f, C.freqToFloat(200f), 0.005f)

        assertEquals(0f, C.hpfToFloat(20f), 0.001f)
        assertEquals(1f, C.hpfToFloat(400f), 0.001f)

        // Q is stored inverted: wide is 0, narrow is 1
        assertTrue(C.qToFloat(10f) < C.qToFloat(0.3f))
        assertEquals(0f, C.qToFloat(10f), 0.001f)
        assertEquals(1f, C.qToFloat(0.3f), 0.001f)

        // every value the book actually uses stays inside 0..1
        for (c in STARTING_CHAINS.values) {
            c.hpfHz?.let { assertTrue(C.hpfToFloat(it) in 0f..1f) }
            for (b in c.eq) {
                assertTrue(C.freqToFloat(b.hz) in 0f..1f)
                assertTrue(C.eqGainToFloat(b.gainDb) in 0f..1f)
                assertTrue(C.qToFloat(b.q) in 0f..1f)
            }
            c.compThrDb?.let { assertTrue(C.thrToFloat(it) in 0f..1f) }
            c.compRatio?.let { assertTrue(C.ratioToFloat(it) in 0f..1f) }
        }
    }

    // ------------------------------------------------------------------
    @Test fun `the engine treats a channel it has identified, once`() {
        // End to end through the engine, so the wiring is tested and not
        // just the book.
        val e = StageEngine(defaultRigProfile())
        var t = 0.0; var next = 1.0
        val src = FloatArray(16) { -80f }.also {
            it[0] = -18f; it[8] = -20f; it[11] = -17f }
        fun run(sec: Double) {
            val end = t + sec - 1e-9
            while (t < end) {
                e.onMeters(src, t)
                if (t >= next - 1e-9) { e.tick(t); next += 1.0 }
                t += 0.05
            }
        }
        run(5.0)
        e.takeover((0 until 16).associateWith { -10f }, t)
        // a plainly voice-shaped spectrum on the singer's channel
        // A voice, not a pad: the energy sits in the 400 Hz-5 kHz band
        // AND it moves. A spectrum that never moves reads as a held
        // chord however voice-shaped it is, and rightly so.
        repeat(40) { k ->
            val lo = 46 + (k % 5) * 3
            e.onRtaFor(8, FloatArray(100) { i ->
                if (i in lo..(lo + 20)) -20f else -60f })
        }
        run(60.0)

        val w = e.treatmentPass(t)
        assertTrue(w.isNotEmpty(), "an identified channel gets its chain")
        assertTrue(w.all { isSafeAddress(it.address) })
        assertTrue(w.any { it.address.startsWith("/ch/09/") },
            "and it is the channel that was identified: ${w.map { it.address }}")
        assertTrue(e.decisions.any { it.kind == "treat" },
            "and the log says so")
        assertTrue(e.treatmentPass(t + 1.0).none {
            it.address.startsWith("/ch/09/") },
            "and then it is left alone")
    }

    @Test fun `treatment can be switched off and then writes nothing`() {
        val e = StageEngine(defaultRigProfile(),
            EngineSettings(treatChannels = false))
        var t = 0.0; var next = 1.0
        val src = FloatArray(16) { -80f }.also {
            it[0] = -18f; it[8] = -20f; it[11] = -17f }
        while (t < 5.0) { e.onMeters(src, t)
            if (t >= next) { e.tick(t); next += 1.0 }; t += 0.05 }
        e.takeover((0 until 16).associateWith { -10f }, t)
        // A voice, not a pad: the energy sits in the 400 Hz-5 kHz band
        // AND it moves. A spectrum that never moves reads as a held
        // chord however voice-shaped it is, and rightly so.
        repeat(40) { k ->
            val lo = 46 + (k % 5) * 3
            e.onRtaFor(8, FloatArray(100) { i ->
                if (i in lo..(lo + 20)) -20f else -60f })
        }
        while (t < 80.0) { e.onMeters(src, t)
            if (t >= next) { e.tick(t); next += 1.0 }; t += 0.05 }
        assertTrue(e.treatmentPass(t).isEmpty())
    }
}
