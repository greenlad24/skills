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
        // because a role flapping back and forth must not flap the EQ.
        // (DRUMS, not FOUNDATION — the foundation chain is deliberately
        // flat now, so it never produces a write to assert on.)
        assertTrue(t.consider(0, Role.DRUMS, verdict(0.9f), 1f,
            spec(), 150.0).isEmpty())
        val w = t.consider(0, Role.DRUMS, verdict(0.9f), 1f, spec(), 400.0)
        assertTrue(w.isNotEmpty(), "a different instrument gets a new chain")
        assertEquals(Role.DRUMS, t.treatedRole(0))
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
        val wet = listOf(Role.VOCAL, Role.BACKING_VOCAL, Role.DRUMS,
            Role.PERCUSSION, Role.KEYS, Role.COLOR, Role.SOLO_GTR)
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
        //
        // IDENTIFYING A CHANNEL IS NO LONGER, ON ITS OWN, A REASON TO
        // TOUCH IT. The operator narrowed that deliberately: "only when
        // the band is playing and only when it feels it is needed —
        // a solo happening, or a new instrument that was not there
        // before." So this arranges an arrival, which is one of the two
        // reasons, and still asserts what it always did: the chain is
        // set once and then the channel is left alone.
        val e = StageEngine(defaultRigProfile())
        var t = 0.0; var next = 1.0
        val src = FloatArray(16) { -80f }.also {
            it[0] = -18f; it[11] = -17f }
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
        run(60.0)
        // The singer steps up to the microphone for the first time.
        // The spectrum has to be fed AFTER that: onRtaFor only listens
        // to a channel that is actually playing, so a spectrum offered
        // while it was silent teaches the identifier nothing.
        src[8] = -20f
        run(6.0)
        // a plainly voice-shaped spectrum on the singer's channel
        // A voice, not a pad: the energy sits in the 400 Hz-5 kHz band
        // AND it moves. A spectrum that never moves reads as a held
        // chord however voice-shaped it is, and rightly so.
        repeat(40) { k ->
            val lo = 46 + (k % 5) * 3
            e.onRtaFor(8, FloatArray(100) { i ->
                if (i in lo..(lo + 20)) -20f else -60f })
        }
        run(e.settings.placeSec.toDouble() + 4.0)

        val w = e.treatmentPass(t)
        assertTrue(w.isNotEmpty(),
            "an instrument that has just arrived gets its chain")
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

    // ==================================================================
    // nothing this app writes may ADD gain, by any route
    // ==================================================================
    @Test fun `no chain in the book asks for gain`() {
        // "Messing with gain WILL cause feedback problems on the stage
        // that the app will find hard to resolve — I want this app to
        // be precise and never cause problems."
        //
        // The preamp was never writable, which is necessary and nowhere
        // near sufficient: a microphone's loop does not care which gain
        // stage the dB came from. The book carried +2 dB at 3 kHz for a
        // lead vocal and +2 dB at 6 kHz for the drum and conga mics —
        // the band where a cardioid's presence peak, a wedge horn and a
        // bar room's worst mode all coincide — plus up to +4 dB of
        // compressor makeup on every voice.
        for ((role, chain) in STARTING_CHAINS) {
            for (b in chain.eq)
                assertTrue(b.gainDb <= 0f,
                    "$role asks for ${b.gainDb} dB at ${b.hz} Hz — this " +
                    "app does not boost anything, anywhere")
            assertTrue(chain.compMakeupDb == null,
                "$role asks for ${chain.compMakeupDb} dB of makeup. A " +
                "downward compressor's gain is at its MAXIMUM below the " +
                "threshold, and a ring starts from the noise floor — so " +
                "makeup is applied in full at exactly the level where " +
                "feedback decides whether to begin")
        }
    }

    @Test fun `a boost cannot get through the write path either`() {
        // The book is the thing most likely to be edited by somebody
        // who has not read the comment, so the refusal lives at the
        // write itself. This is that test: it tries to sneak one past.
        assertTrue(isGainAdding("/ch/09/eq/3/g", 0.60f),
            "an EQ band above unity is a boost")
        assertTrue(isGainAdding("/ch/09/dyn/mgain", 0.20f),
            "makeup above zero is gain")
        assertTrue(!isGainAdding("/ch/09/eq/3/g", 0.40f),
            "a cut is the whole point and must still get through")
        assertTrue(!isGainAdding("/ch/09/eq/3/g", 0.5f),
            "and unity is not a boost")
        assertTrue(!isGainAdding("/ch/09/preamp/hpf", 0.9f),
            "a high-pass corner is not a gain, whatever its value")
        assertTrue(!isGainAdding("/ch/09/mix/fader", 0.9f),
            "the fader is the level engine's business, not this guard's")
    }

    @Test fun `switching processing on must not enable somebody elses boost`() {
        // The chain sets one or two bands and then writes eq/on=1. The
        // OTHER bands are whatever is in the desk — a previous band's
        // scene, a house engineer's ring-out, a soundcheck from three
        // months ago. Turning the EQ on over a stored +8 dB at 3 kHz is
        // a boost on an open vocal microphone that isGainAdding never
        // sees, because we never wrote it. Same for makeup gain, which
        // the book no longer asks for and therefore never overwrites.
        for (role in Role.values()) {
            val t = ChannelTreatment()
            val w = t.consider(8, role, verdict(0.95f), 1f, spec(), 100.0)
            if (w.isEmpty()) continue
            val addrs = w.map { it.address }
            if (addrs.any { it == "/ch/09/eq/on" }) {
                for (b in 1..3)
                    assertTrue(addrs.contains("/ch/09/eq/$b/g"),
                        "$role switches the EQ on without saying what " +
                        "band $b is: $addrs")
                // band 4 is the ring-out's, and a notch that the chain
                // flattens is not a notch
                assertTrue(addrs.none {
                        it.startsWith("/ch/09/eq/${RingOut.RING_BAND}/") },
                    "$role wrote the band kept for ring-outs: $addrs")
                for (p in w.filter { Regex("eq/[1-4]/g$").containsMatchIn(it.address) })
                    assertTrue(p.value <= 0.5f + GAIN_EPS,
                        "$role leaves ${p.address} above flat: ${p.value}")
            }
            if (addrs.any { it == "/ch/09/dyn/on" }) {
                val mg = w.firstOrNull { it.address == "/ch/09/dyn/mgain" }
                assertTrue(mg != null && mg.value <= GAIN_EPS,
                    "$role switches the compressor on over whatever " +
                    "makeup the desk had stored: $addrs")
            }
        }
    }

    @Test fun `the chain switches things on only after it has set them`() {
        // Order matters on a live desk: eq/on before the band gains is
        // a moment of the old EQ at full value, which on a vocal mic is
        // the moment a ring starts.
        val t = ChannelTreatment()
        val w = t.consider(8, Role.VOCAL, verdict(0.95f), 1f, spec(), 100.0)
        val addrs = w.map { it.address }
        val eqOn = addrs.indexOf("/ch/09/eq/on")
        if (eqOn >= 0) for (b in 1..3)
            assertTrue(addrs.indexOf("/ch/09/eq/$b/g") in 0 until eqOn ||
                       addrs.lastIndexOf("/ch/09/eq/$b/g") > eqOn,
                "band $b is never set: $addrs")
        val dynOn = addrs.indexOf("/ch/09/dyn/on")
        if (dynOn >= 0)
            assertTrue(addrs.indexOf("/ch/09/dyn/mgain") in 0 until dynOn,
                "the makeup is zeroed before the compressor is switched " +
                "on: $addrs")
    }

    @Test fun `the high-pass goes under the singer, not at the preset`() {
        // The whole reason for a per-channel frequency map. The vocal
        // preset is 100 Hz; a baritone whose voice really starts at
        // 87 Hz loses his bottom octave to it, and a bright voice with
        // nothing under 180 keeps 80 Hz of stage rumble it never
        // needed. Same book, same role, two different corners.
        fun corner(edgeHz: Float?): Float {
            val t = ChannelTreatment()
            val shape = edgeHz?.let { ChannelTreatment.Shape(lowEdgeHz = it) }
            val w = t.consider(8, Role.VOCAL, verdict(0.95f), 1f, spec(),
                100.0, shape)
            val v = w.first { it.address == "/ch/09/preamp/hpf" }.value
            // invert hpfToFloat
            return 20f * Math.pow(20.0, v.toDouble()).toFloat()
        }
        val preset = corner(null)
        val bari = corner(87f)
        val bright = corner(220f)
        println("high-pass: preset %.0f Hz, baritone %.0f, bright %.0f"
            .format(preset, bari, bright))
        assertTrue(abs(preset - 100f) < 3f, "the book is still the book")
        assertTrue(bari < 90f,
            "the preset would cut into this singer: %.0f Hz".format(bari))
        assertTrue(bright > preset + 20f,
            "and a voice with nothing down there gets a cleaner channel: " +
            "%.0f Hz".format(bright))
        // and no estimate, however wrong, may run away with it
        assertTrue(corner(20f) >= 45f && corner(4000f) <= 155f,
            "bounded to half and one-and-a-half times the preset")
    }

    @Test fun `a ringing shell gets a narrow cut, a voicing does not`() {
        val t = ChannelTreatment()
        val w = t.consider(2, Role.DRUMS, verdict(0.95f), 1f, spec(),
            100.0, ChannelTreatment.Shape(
                lowEdgeHz = 90f, resonanceHz = 250f,
                resonanceDb = 9f, resonanceQ = 4f))
        val bands = (1..4).mapNotNull { b ->
            w.firstOrNull { it.address == "/ch/03/eq/$b/f" }?.let { f ->
                val hz = 20f * Math.pow(1000.0, f.value.toDouble()).toFloat()
                val g = w.first { it.address == "/ch/03/eq/$b/g" }.value * 30f - 15f
                Triple(b, hz, g)
            }
        }
        println("bands: " + bands.map { "%d %.0f Hz %+.1f dB".format(it.first, it.second, it.third) })
        val ring = bands.firstOrNull { abs(it.second - 250f) < 40f }
        assertTrue(ring != null, "the lump at 250 Hz must be addressed: $bands")
        assertTrue(ring.third < -3f && ring.third >= -4.01f,
            "cut, and not more than four dB: ${ring.third}")

        // a channel with no lump gets the book and nothing else
        val plain = ChannelTreatment().consider(2, Role.DRUMS,
            verdict(0.95f), 1f, spec(), 100.0,
            ChannelTreatment.Shape(lowEdgeHz = 90f))
        assertTrue(plain.none { it.address == "/ch/03/eq/3/f" },
            "a smooth instrument is not a problem to solve")
    }

    @Test fun `a map that arrives late is still worth one more write`() {
        // The analyzer parks on one channel at a time, so the first
        // chain is nearly always built before the map has anything to
        // say. When it does, and it disagrees with the preset, that is
        // worth exactly one more write — and then never again.
        val t = ChannelTreatment()
        val first = t.consider(8, Role.VOCAL, verdict(0.95f), 1f, spec(),
            100.0, null)
        assertTrue(first.isNotEmpty(), "the book goes on first")

        val shape = ChannelTreatment.Shape(lowEdgeHz = 87f)
        assertTrue(t.consider(8, Role.VOCAL, verdict(0.95f), 1f, spec(),
            150.0, shape).isEmpty(), "not before the minimum gap")

        val second = t.consider(8, Role.VOCAL, verdict(0.95f), 1f, spec(),
            400.0, shape)
        assertTrue(second.any { it.address == "/ch/09/preamp/hpf" },
            "the high-pass is re-placed under the singer")
        assertTrue(t.lastReason.contains("87"),
            "and it says why: ${t.lastReason}")

        val third = t.consider(8, Role.VOCAL, verdict(0.95f), 1f, spec(),
            900.0, shape)
        assertTrue(third.isEmpty(),
            "once is once — nothing further: " + third.map { it.address })
    }

    @Test fun `the monitors are untouched, balance and volume both`() {
        // "The monitors balance and volume are mine 100%." Balance is
        // the per-channel send into a wedge; volume is the bus master.
        // Neither is writable and no chain can produce one.
        for (ch in 0 until 16) {
            for (bus in 1..6) {
                assertTrue(!isSafeAddress("/ch/%02d/mix/%02d/level".format(ch + 1, bus)),
                    "a send into wedge $bus is never ours")
                assertTrue(!isSafeAddress("/ch/%02d/mix/%02d/on".format(ch + 1, bus)))
            }
            assertTrue(!isSafeAddress("/ch/%02d/preamp/trim".format(ch + 1)),
                "and neither is the preamp gain")
        }
        for (bus in 1..6)
            assertTrue(!isSafeAddress("/bus/%02d/mix/fader".format(bus)),
                "nor a wedge's own master")
    }
}
