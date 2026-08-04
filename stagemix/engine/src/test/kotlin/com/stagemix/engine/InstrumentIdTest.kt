package com.stagemix.engine

import kotlin.math.abs
import kotlin.math.log2
import kotlin.math.pow
import kotlin.math.sin
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Can the engine tell what is plugged in without being told?
 *
 * The rig that prompted this has its LEAD SINGER on a channel the house
 * desk calls "Congo / Vox 3". Reading the label put the lead vocal in
 * the percussion group, eight dB under where it belongs, for a whole
 * night. Channel numbers are no better — the band moves an input and a
 * numbered profile is wrong from then on.
 *
 * The spectra and envelopes here are synthetic but shaped like the real
 * thing: harmonic series where instruments have them, band-limits where
 * cabinets and bodies impose them, and phrasing where a human has to
 * breathe.
 */
class InstrumentIdTest {

    /** RTA bin for a frequency, the way the console lays them out */
    private fun bin(hz: Double) = (10.0 * log2(hz / 20.0)).toInt()

    /**
     * A 100-bin dB spectrum built from partials. [f0] fundamental,
     * [partials] how many, [tilt] dB per octave roll-off, [bandLimitHz]
     * where the source simply stops (a speaker cabinet, a drum head).
     */
    private fun spectrum(f0: Double, partials: Int, tilt: Double,
                         bandLimitHz: Double, floorDb: Double = -70.0,
                         boostHz: Double = 0.0, boostDb: Double = 0.0):
            FloatArray {
        val out = FloatArray(100) { floorDb.toFloat() }
        for (k in 1..partials) {
            val hz = f0 * k
            if (hz < 20 || hz > 20000) continue
            val b = bin(hz)
            if (b !in 0..99) continue
            var db = -tilt * log2(k.toDouble())
            if (hz > bandLimitHz) db -= 12.0 * log2(hz / bandLimitHz)
            if (boostDb != 0.0 && abs(log2(hz / boostHz)) < 0.5) db += boostDb
            // a partial spills into its neighbours, as a real one does
            for (d in -1..1) {
                val i = b + d
                if (i in 0..99) {
                    val v = (db - 6.0 * abs(d)).toFloat()
                    if (v > out[i]) out[i] = v
                }
            }
        }
        return out
    }

    /**
     * Feed a source to the identifier for [seconds] of stage time.
     *
     * Through the console's meter ballistics, not raw — a programme
     * meter rises fast and falls over about 300 ms, so a kick drum does
     * NOT read as silence between hits. Skipping that made every
     * percussive channel look 88 % dead and took a minute of music to
     * accumulate a few seconds of "active" audio.
     */
    private fun play(id: InstrumentId, ch: Int, seconds: Double,
                     level: (Double) -> Float,
                     spec: (Double) -> FloatArray?,
                     gateDb: Float = -45f) {
        val dt = 0.05f                       // the console's meter rate
        val rel = 1f - kotlin.math.exp(-dt / 0.30f)
        var env = -128f
        var t = 0.0
        var frame = 0
        while (t < seconds) {
            val raw = level(t)
            env = if (raw > env) raw else env + rel * (raw - env)
            val on = env > gateDb
            id.onLevel(ch, env, dt, on)
            // the RTA lands on one channel a few times a second
            if (frame % 5 == 0) spec(t)?.let { id.onRta(ch, it, on) }
            t += dt; frame++
        }
    }

    // -- the sources -----------------------------------------------------

    private fun kick(t: Double): Float {
        val phase = (t % 0.6) / 0.6           // 100 bpm
        return if (phase < 0.12) (-8 - 40 * phase / 0.12).toFloat() else -60f
    }
    private val kickSpec = spectrum(55.0, 3, 14.0, 90.0)

    private fun bassLevel(t: Double): Float =
        (-14 + 3 * sin(2 * Math.PI * t / 1.7)).toFloat()
    private val bassSpec = spectrum(65.0, 5, 10.0, 220.0)

    private fun snareLevel(t: Double): Float {
        val phase = (t % 1.2) / 1.2
        return if (phase < 0.08) (-9 - 45 * phase / 0.08).toFloat() else -60f
    }
    // body at 200 Hz plus the wires: broadband up top
    private val snareSpec = FloatArray(100) { i ->
        when {
            i < bin(120.0) -> -55f
            i < bin(400.0) -> -14f
            i < bin(2000.0) -> -22f
            else -> -16f
        }
    }

    private fun congaLevel(t: Double): Float {
        val phase = (t % 0.45) / 0.45
        return if (phase < 0.13) (-11 - 40 * phase / 0.13).toFloat() else -58f
    }
    private val congaSpec = spectrum(190.0, 6, 8.0, 1400.0)

    /** a singer: phrases with breaths, and a spectrum that never sits still */
    private fun voiceLevel(t: Double): Float {
        val bar = t % 6.0
        if (bar > 4.0) return -70f                       // breathing
        return (-13 + 5 * sin(2 * Math.PI * t / 0.9)).toFloat()
    }
    private fun voiceSpec(t: Double): FloatArray {
        // The note moves, and the formants move with it. ~3 dB/octave,
        // not 7: a close-miked voice through a desk's high-pass is NOT
        // dominated by its fundamental — measured vocal spectra stay
        // within about 10 dB from 300 Hz to 4 kHz, and that is the whole
        // reason a voice and a bass guitar can be told apart. The
        // singer's formant near 2.8 kHz is the other half of it.
        val f0 = 180.0 * 2.0.pow(((t * 1.7).toInt() % 5) / 12.0)
        return spectrum(f0, 22, 3.0, 6000.0,
            boostHz = 2800.0, boostDb = 7.0)
    }

    /** a piano: many notes at once, always there, barely moving */
    private fun pianoLevel(t: Double): Float =
        (-16 + 2 * sin(2 * Math.PI * t / 3.1)).toFloat()
    private fun pianoSpec(t: Double): FloatArray {
        val a = spectrum(130.0, 20, 4.5, 5000.0)
        val b = spectrum(196.0, 20, 4.5, 5000.0)
        val c = spectrum(261.0, 20, 4.5, 5000.0)
        return FloatArray(100) { maxOf(a[it], b[it], c[it]) }
    }

    // -- the tests -------------------------------------------------------

    @Test fun `each family is told apart from the audio alone`() {
        val cases = listOf(
            Triple("kick", Family.LOW_END, 0),
            Triple("bass", Family.LOW_END, 1),
            Triple("snare", Family.HITS, 2),
            Triple("congas", Family.HITS, 3),
            Triple("voice", Family.VOICELIKE, 4),
            Triple("piano", Family.BED, 5))

        val id = InstrumentId()
        play(id, 0, 90.0, ::kick, { kickSpec })
        play(id, 1, 90.0, ::bassLevel, { bassSpec })
        play(id, 2, 90.0, ::snareLevel, { snareSpec })
        play(id, 3, 90.0, ::congaLevel, { congaSpec })
        play(id, 4, 90.0, ::voiceLevel, ::voiceSpec)
        play(id, 5, 90.0, ::pianoLevel, ::pianoSpec)

        for ((name, want, ch) in cases) {
            val v = id.verdict(ch)
            assertTrue(v != null, "$name: no verdict at all")
            println("%-7s -> %-9s conf %.2f  (%s)".format(
                name, v!!.family, v.confidence, v.why))
            assertEquals(want, v.family, "$name came out as ${v.family}")
            // and clear enough of the runner-up to be worth acting on —
            // a right answer nobody trusts changes nothing
            assertTrue(v.confidence >= 0.55f,
                "$name was right but only %.2f confident".format(v.confidence))
        }
    }

    @Test fun `an ambiguous label is settled by what it sounds like`() {
        // THE bug: "Congo / Vox 3" is the lead singer on this rig, and
        // the words alone say conga just as loudly as they say vocal.
        val singing = InstrumentId()
        play(singing, 10, 90.0, ::voiceLevel, ::voiceSpec)
        val asVocal = singing.resolve(10, "Congo / Vox 3", Role.PERCUSSION)
        assertTrue(asVocal != null,
            "a singer on an ambiguous channel was not recognised")
        assertEquals(Role.VOCAL, asVocal!!.role,
            "the lead singer stayed in the percussion group: ${asVocal.why}")
        println("singing:  ${asVocal.why}")

        // and the same label with an actual conga on it must go the
        // other way, or this is just a rule that always says "vocal"
        val drumming = InstrumentId()
        play(drumming, 10, 90.0, ::congaLevel, { congaSpec })
        val asPerc = drumming.resolve(10, "Congo / Vox 3", Role.VOCAL)
        assertTrue(asPerc != null, "a conga on an ambiguous channel was not read")
        assertEquals(Role.PERCUSSION, asPerc!!.role,
            "a conga was called a vocal: ${asPerc.why}")
        println("drumming: ${asPerc.why}")
    }

    @Test fun `a channel with a meaningless label is named by its audio`() {
        // "DI 1", "Ch 11", "" — most of a house desk, most nights
        val id = InstrumentId()
        play(id, 3, 90.0, ::bassLevel, { bassSpec })
        val r = id.resolve(3, "DI 1", Role.INSTRUMENT)
        assertTrue(r != null, "an unlabelled bass was left unclassified")
        assertEquals(Role.FOUNDATION, r!!.role, r.why)
        println(r.why)
    }

    @Test fun `a flatly wrong label is overruled`() {
        // someone typed "Vocal 4" on the bass DI. The room can hear what
        // is on the channel; the label cannot.
        val id = InstrumentId()
        play(id, 7, 90.0, ::bassLevel, { bassSpec })
        val r = id.resolve(7, "Vocal 4", Role.VOCAL)
        assertTrue(r != null,
            "a bass labelled as a vocal kept the vocal's place in the mix")
        assertEquals(Role.FOUNDATION, r!!.role, r.why)
        println(r.why)
    }

    @Test fun `an unambiguous label that fits is left alone`() {
        val id = InstrumentId()
        play(id, 0, 90.0, ::kick, { kickSpec })
        // "Kick Drum" means one thing and the audio agrees: no change
        assertTrue(id.resolve(0, "Kick Drum", Role.FOUNDATION) == null,
            "a correctly labelled kick was re-roled anyway")
    }

    @Test fun `nothing is decided before there is enough to go on`() {
        val id = InstrumentId()
        play(id, 4, 3.0, ::voiceLevel, ::voiceSpec)      // three seconds
        assertTrue(id.verdict(4) == null,
            "a verdict was reached on three seconds of audio")
        assertTrue(id.resolve(4, "Congo / Vox 3", Role.PERCUSSION) == null,
            "a channel was re-roled before there was evidence")
        assertTrue(id.evidence(4) < 1f, "evidence was reported as complete")
    }

    @Test fun `a channel that changes instrument is heard changing`() {
        // The harmonica player on this rig sings backing vocals between
        // solos, on the same microphone. A fingerprint averaged over the
        // whole night is a blend of a reed and a throat and is neither,
        // so the identifier has to track what the channel is being used
        // for NOW — and be willing to change its mind more than once.
        val id = InstrumentId()

        // a reed: the same band as a voice, but held and steady
        val harpSpec = spectrum(440.0, 12, 3.5, 5000.0)
        fun harpLevel(t: Double) =
            (-15 + 2 * sin(2 * Math.PI * t / 2.3)).toFloat()

        play(id, 15, 120.0, ::harpLevel, { harpSpec })
        val asHarp = id.verdict(15)
        // NB: never .format() a string carrying `why` — it is full of
        // per-cent signs and they are not format specifiers
        println("playing harmonica -> ${asHarp?.family} " +
            "${asHarp?.confidence} (${asHarp?.why})")

        // then they put it down and sing for two minutes
        play(id, 15, 150.0, ::voiceLevel, ::voiceSpec)
        val asSinger = id.verdict(15)
        println("then singing     -> ${asSinger?.family} " +
            "${asSinger?.confidence} (${asSinger?.why})")

        assertTrue(asSinger != null, "no verdict once they started singing")
        assertEquals(Family.VOICELIKE, asSinger!!.family,
            "the channel kept its harmonica reading after two minutes of " +
            "singing — the fingerprint is not tracking what it hears")
        assertTrue(asSinger.confidence >= 0.55f,
            "changed its mind but only %.2f confident".format(asSinger.confidence))

        // and back again when they pick it up
        play(id, 15, 150.0, ::harpLevel, { harpSpec })
        val backToHarp = id.verdict(15)
        println("back on the harp -> ${backToHarp?.family} " +
            "${backToHarp?.confidence}")
        assertTrue(backToHarp!!.family != Family.VOICELIKE ||
            backToHarp.confidence < asSinger.confidence,
            "the channel never came back off the vocal reading")
    }

    @Test fun `a talkback mic is never re-roled`() {
        // TALK is a safety property, not a classification: the engine
        // must never automate a speech mic, whatever it sounds like.
        val id = InstrumentId()
        play(id, 12, 90.0, ::voiceLevel, ::voiceSpec)
        assertTrue(id.resolve(12, "Talkback", Role.TALK) == null,
            "a talkback mic was re-roled")
        assertTrue(id.resolve(12, "TB Mic", Role.VOCAL) == null,
            "a channel named as talkback was re-roled")
    }
}
