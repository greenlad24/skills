package com.stagemix.engine

import kotlin.random.Random
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * Regressions for every bug the adversarial test team confirmed.
 * Each test asserts the CORRECT behavior; each one failed before the
 * fix that accompanies it.
 */
class AgentRegressionTest {

    private fun rig() = defaultRigProfile()
    private fun faders(v: Float = -10f) = (0 until 16).associateWith { v }

    private fun run(e: StageEngine, lv: FloatArray, from: Double, sec: Double,
                    out: MutableList<FaderWrite>? = null): Double {
        var t = from; var next = from + 1.0
        while (t < from + sec) {
            e.onMeters(lv, t)
            if (t >= next) { e.tick(t).let { out?.addAll(it) }; next += 1.0 }
            t += 0.05
        }
        return t
    }

    private fun band() = FloatArray(16) { -80f }.also {
        it[0] = -20f; it[11] = -21f; it[5] = -24f; it[6] = -24f; it[8] = -22f }

    // ---------- crashes (fuzz team) ----------
    @Test fun `F1 baseline above the absolute cap must not crash`() {
        val e = StageEngine(rig(), LEAD)
        var t = run(e, band(), 0.0, 5.0)
        e.takeover(faders(14f), t)      // faders way above the +2 cap
        run(e, band(), t, 60.0)         // must not throw
    }

    @Test fun `F1b absurd operator override must not crash`() {
        val e = StageEngine(rig(), LEAD)
        var t = run(e, band(), 0.0, 5.0)
        e.takeover(faders(), t)
        t = run(e, band(), t, 30.0)
        e.operatorOverride(4, 100f, t)   // +100 dB from a bad packet
        e.operatorOverride(5, Float.NaN, t)
        run(e, band(), t, 200.0)         // must not throw
        assertTrue((e.state[4]?.baselineDb ?: 99f) <= 2.01f,
            "absurd baselines must be clamped into legal territory")
    }

    @Test fun `F2 meter decode never throws on hostile buffers`() {
        val rnd = Random(7)
        repeat(20000) {
            val n = rnd.nextInt(0, 64)
            val b = ByteArray(n) { rnd.nextInt(256).toByte() }
            Meters.decode(b)             // must never throw
        }
    }

    @Test fun `F3 NaN RTA never reaches an EQ write`() {
        val d = ToneDoctor(listOf(0), mapOf(0 to Role.SOLO_GTR))
        var t = 0.0
        repeat(30) { d.onRta(0, FloatArray(100) { -30f }, t); t += 3.0 }
        d.snapshotChannel(0, floatArrayOf(0f, 0f, 0f, 0f), thrDb = -20f)
        repeat(30) {
            d.onRta(0, FloatArray(100) { if (it == 70) Float.NaN else -20f }, t)
            t += 3.0
        }
        val writes = ArrayList<ParamWrite>()
        repeat(20) { writes.addAll(d.tick(setOf(0), true, false)) }
        assertTrue(writes.none { it.value.isNaN() || it.value.isInfinite() },
            "NaN/Inf must never be sent to the mixer: $writes")
    }

    @Test fun `F4 a long gap cannot buy an oversized single move`() {
        val e = StageEngine(rig(), LEAD)
        var t = run(e, band(), 0.0, 5.0)
        e.takeover(faders(), t)
        t = run(e, band().also { it[4] = -14f }, t, 40.0)
        val before = e.offsetDb(4)
        e.onMeters(band().also { it[4] = -14f }, t)
        val w = e.tick(t + 3600.0)       // an hour later (app was paused)
        val step = kotlin.math.abs(e.offsetDb(4) - before)
        assertTrue(step <= 4.6f, "single-tick move after a 1 h gap: $step dB")
    }

    // ---------- engine correctness (review + chaos team) ----------
    @Test fun `probe2 a quiet channel recovers even when the budget is full`() {
        val e = StageEngine(listOf(
            ChannelConfig(0, "Kick", Role.FOUNDATION),
            ChannelConfig(1, "Piano", Role.KEYS),
            ChannelConfig(2, "Sax", Role.COLOR)), LEAD)
        var t = 0.0
        val lv = floatArrayOf(-20f, -30f, -30f)
        t = run(e, lv, t, 5.0)
        e.takeover(mapOf(0 to -10f, 1 to -18f, 2 to -10f), t)
        t = run(e, lv, t, 300.0)
        assertTrue(e.offsetDb(1) > 1f,
            "a channel climbing back toward baseline spends no headroom " +
            "and must not be starved by other channels' boosts " +
            "(offset=${e.offsetDb(1)})")
    }

    @Test fun `probe4 a fresh takeover clears stale override holds`() {
        val e = StageEngine(rig(), LEAD)
        var t = run(e, band(), 0.0, 5.0)
        e.takeover(faders(), t)
        t = run(e, band(), t, 30.0)
        e.operatorOverride(4, -13f, t)      // 2-min hold starts
        t = run(e, band(), t, 10.0)
        e.takeover(faders(), t)             // new act, new takeover
        val w = ArrayList<FaderWrite>()
        t = run(e, band().also { it[4] = -12f }, t, 90.0, w)
        assertTrue(w.any { it.channel == 4 },
            "a new takeover is a clean slate — stale holds must not " +
            "leave a channel unmanaged all night")
    }

    @Test fun `probe5 health reports n slash a when no vocal is on stage`() {
        val e = StageEngine(listOf(
            ChannelConfig(0, "Kick", Role.FOUNDATION),
            ChannelConfig(1, "Piano", Role.KEYS)), LEAD)
        var t = run(e, floatArrayOf(-20f, -25f), 0.0, 5.0)
        e.takeover(mapOf(0 to -10f, 1 to -10f), t)
        run(e, floatArrayOf(-20f, -25f), t, 120.0)
        assertEquals(-1, e.health().vocalOnTopPct,
            "with no vocal channel the score must read n/a, never a " +
            "flattering 100%")
    }

    @Test fun `probe6 duck releases when the ducked channel stops playing`() {
        val e = StageEngine(listOf(
            ChannelConfig(0, "Kick", Role.FOUNDATION),
            ChannelConfig(1, "Guitar", Role.RHYTHM_GTR),
            ChannelConfig(2, "Vox", Role.VOCAL)), LEAD)
        var t = 0.0
        // vocal SO buried that the pyramid alone can't rescue it — the
        // duck stays engaged instead of releasing on its own
        val loud = floatArrayOf(-20f, -14f, -42f)
        t = run(e, loud, t, 5.0)
        e.takeover(mapOf(0 to -10f, 1 to -10f, 2 to -10f), t)
        t = run(e, loud, t, 120.0)
        val ducked = e.state[1]!!.duckDb
        assertTrue(ducked < -0.5f, "sanity: guitar was ducked ($ducked)")
        // guitarist stops playing entirely
        t = run(e, floatArrayOf(-20f, -80f, -26f), t, 60.0)
        assertTrue(e.state[1]!!.duckDb > ducked + 0.5f,
            "a duck must release once its channel goes quiet, not linger " +
            "into the next song (${e.state[1]!!.duckDb})")
    }

    @Test fun `probe7 a quiet channel joining is not a broadband event`() {
        val e = StageEngine(listOf(
            ChannelConfig(0, "Kick", Role.FOUNDATION),
            ChannelConfig(1, "Vox", Role.VOCAL),
            ChannelConfig(2, "Sax", Role.COLOR)), LEAD)
        var t = 0.0
        t = run(e, floatArrayOf(-20f, -22f, -80f), t, 5.0)
        e.takeover(mapOf(0 to -10f, 1 to -10f, 2 to -10f), t)
        t = run(e, floatArrayOf(-20f, -22f, -80f), t, 60.0)
        // the sax joins, quietly
        e.onMeters(floatArrayOf(-20f, -22f, -44f), t)
        e.onMeters(floatArrayOf(-20f, -22f, -44f), t + 0.05)
        assertTrue(e.boostsAllowed(t + 0.1),
            "a new quiet channel changes the mean without anything " +
            "happening on stage — it must not freeze the engine")
    }

    // ---------- perception ----------
    @Test fun `probe3 a howl that wanders between bins is still caught`() {
        val w = FeedbackWatchdog()
        var t = 0.0
        repeat(60) { i ->
            val bin = if (i % 2 == 0) 40 else 43
            w.onRta(FloatArray(100) { j -> if (j == bin) -12f else -55f }, t)
            t += 0.05
        }
        assertTrue(w.vetoActive,
            "alternating adjacent bins is one howl, not two notes")
    }

    @Test fun `register does not flap on a boundary singer with vibrato`() {
        val d = ToneDoctor(listOf(0), mapOf(0 to Role.VOCAL))
        var t = 0.0
        var flips = 0
        var last = d.state[0]!!.register
        repeat(400) { i ->
            // tenor sitting right at the boundary, vibrato either side
            val lo = if (i % 2 == 0) -25f else -28f
            val hi = if (i % 2 == 0) -28f else -25f
            d.onRta(0, FloatArray(100) { j ->
                when (j) { in 23..31 -> lo; in 32..40 -> hi; else -> -50f } }, t)
            if (d.state[0]!!.register != last) { flips++; last = d.state[0]!!.register }
            t += 0.05
        }
        assertTrue(flips <= 2,
            "vibrato at the register boundary must not flap the doctor " +
            "blind ($flips flips)")
    }

    // ---------- the invariant that matters most ----------
    @Test fun `fuzz - only channel faders are ever written, always bounded`() {
        val rnd = Random(99)
        repeat(30) { seed ->
            val e = StageEngine(rig(), LEAD)
            var t = 0.0
            val lv = FloatArray(16) { -30f }
            t = run(e, lv, t, 5.0)
            e.takeover(faders(), t)
            var next = t + 1.0
            val tEnd = t + 400.0
            while (t < tEnd) {
                for (i in lv.indices) lv[i] = when (rnd.nextInt(10)) {
                    0 -> -80f
                    1 -> -2f
                    else -> -40f + rnd.nextFloat() * 30f
                }
                e.onMeters(lv, t)
                if (t >= next) {
                    for (w in e.tick(t)) {
                        assertTrue(Regex("^/ch/\\d\\d/mix/fader$")
                            .matches(w.address), "foreign write ${w.address}")
                        assertTrue(w.levelDb <= 2.01f, "cap: ${w.levelDb}")
                        assertTrue(w.levelDb >= -22.01f, "floor: ${w.levelDb}")
                    }
                    val boost = (0 until 16).sumOf {
                        maxOf(0f, e.offsetDb(it)).toDouble() }
                    assertTrue(boost <= 6.05, "budget breached: $boost")
                    next += 1.0
                }
                t += 0.05
            }
        }
    }
}

/** Round 2: perception bugs found by the DSP agent. */
class PerceptionRegressionTest {

    private fun floor(v: Float = -55f) = FloatArray(100) { v }

    /** an instrument note: fundamental + 2f/3f partners */
    private fun note(bin: Int, level: Float = -12f, floorDb: Float = -55f) =
        floor(floorDb).also {
            it[bin] = level
            it[bin + 10] = level - 12f     // 2f
            it[bin + 16] = level - 20f     // 3f
        }

    @Test fun `the band's own instruments never trip the howl veto`() {
        for ((name, bin) in listOf("harmonica" to 55, "flute" to 62,
                "organ" to 45, "held vocal" to 38)) {
            val w = FeedbackWatchdog()
            var t = 0.0
            repeat(200) { w.onRta(note(bin), t); t += 0.05 }
            assertFalse(w.vetoActive,
                "$name is a sustained NOTE (it has 2f/3f partners) — " +
                "vetoing on it would freeze the mix through every solo")
        }
    }

    @Test fun `a pure parked howl is still caught`() {
        val w = FeedbackWatchdog()
        var t = 0.0
        repeat(15) { w.onRta(floor().also { it[55] = -12f }, t); t += 0.05 }
        assertTrue(w.vetoActive, "a partner-less parked spike is a howl")
        assertTrue(w.lastFreqHz in 700..1200)
    }

    @Test fun `a howl rising under a playing band is caught`() {
        val w = FeedbackWatchdog()
        var t = 0.0
        // the band raises the median, blinding a pure tower test
        repeat(40) { i ->
            w.onRta(floor(-25f).also { it[55] = -50f + 45f * (i / 39f) }, t)
            t += 0.05
        }
        var caught = false
        repeat(100) {
            w.onRta(floor(-25f).also { it[55] = -5f }, t)
            if (w.vetoActive) caught = true
            t += 0.05
        }
        assertTrue(caught,
            "growth is the tell when the band masks the tower test")
    }

    @Test fun `speaker distortion does not disguise a howl as an instrument`() {
        val w = FeedbackWatchdog()
        var t = 0.0
        repeat(15) {
            // a weak driver-distortion harmonic, far below the noise floor
            w.onRta(floor().also { it[55] = -12f; it[65] = -50f }, t)
            t += 0.05
        }
        assertTrue(w.vetoActive, "-38 dBc is not a harmonic partner")
    }

    @Test fun `melodies and crescendos are still ignored`() {
        val w1 = FeedbackWatchdog()
        var t = 0.0
        repeat(60) { w1.onRta(floor(-18f), t); t += 0.05 }
        assertFalse(w1.vetoActive, "broadband crescendo is music")
        val w2 = FeedbackWatchdog()
        t = 0.0
        repeat(60) { i ->
            w2.onRta(floor().also { it[30 + (i % 8) * 5] = -12f }, t); t += 0.05
        }
        assertFalse(w2.vetoActive, "moving peaks are a melody")
    }

    @Test fun `an approved edgy tone is not fought all night`() {
        // a deliberately bright/distorted guitar, harsh from the start
        val d = ToneDoctor(listOf(0), mapOf(0 to Role.SOLO_GTR))
        fun spec(harsh: Float) = FloatArray(100) { i ->
            when (i) { in 26..60 -> -30f; in 66..82 -> harsh; else -> -40f } }
        var t = 0.0
        repeat(40) { d.onRta(0, spec(-18f), t); t += 0.5 }   // +12 harsh
        d.snapshotChannel(0, floatArrayOf(0f, 0f, 0f, 0f), thrDb = null)
        repeat(40) { d.onRta(0, spec(-18f), t); t += 0.5 }
        val w = ArrayList<ParamWrite>()
        repeat(20) { w.addAll(d.tick(setOf(0), true, false)) }
        assertTrue(w.none { it.address == "/ch/01/eq/3/g" },
            "the tone the engineer approved at takeover is the reference — " +
            "an edgy-by-design guitar must not be dulled forever")
    }

    @Test fun `a channel that BECOMES harsh is still eased`() {
        val d = ToneDoctor(listOf(0), mapOf(0 to Role.SOLO_GTR))
        fun spec(harsh: Float) = FloatArray(100) { i ->
            when (i) { in 26..60 -> -30f; in 66..82 -> harsh; else -> -40f } }
        var t = 0.0
        repeat(40) { d.onRta(0, spec(-32f), t); t += 0.5 }   // sweet
        d.snapshotChannel(0, floatArrayOf(0f, 0f, 0f, 0f), thrDb = null)
        repeat(60) { d.onRta(0, spec(-16f), t); t += 0.5 }   // turned shrill
        val w = ArrayList<ParamWrite>()
        repeat(20) { w.addAll(d.tick(setOf(0), true, false)) }
        assertTrue(w.any { it.address == "/ch/01/eq/3/g" },
            "new harshness must still be softened")
    }

    @Test fun `frozen comp telemetry never walks a threshold`() {
        val d = ToneDoctor(listOf(0),
            settings = DoctorSettings(compTendingEnabled = true))
        var t = 0.0
        repeat(30) { d.onRta(0, FloatArray(100) { -30f }, t); t += 1.0 }
        repeat(40) { i ->
            d.onGainReduction(0, -4f + 1.5f * kotlin.math.sin(0.7 * i).toFloat(), t)
            t += 1.0
        }
        d.snapshotChannel(0, floatArrayOf(0f, 0f, 0f, 0f), thrDb = -20f)
        // the parsed field freezes at a plausible-looking value
        repeat(200) { d.onGainReduction(0, -12f, t); t += 1.0
                      d.tick(setOf(0), true, false) }
        assertTrue(kotlin.math.abs(d.state[0]!!.thrOffset) < 2.5f,
            "a frozen non-zero reading is a wrong meter index, not audio " +
            "(offset=${d.state[0]!!.thrOffset})")
    }

    @Test fun `comp tending is off until the meter layout is verified`() {
        val d = ToneDoctor(listOf(0))     // stock settings
        assertFalse(d.settings.compTendingEnabled,
            "never automate on an unverified meter index")
    }

    @Test fun `a band that has drifted down is not pushed back up`() {
        // The drift corrector was symmetrical: a band quieter than it
        // was at snapshot produced a positive target and the doctor
        // walked the EQ up to +2 dB over the engineer's setting. Half
        // of a two-sided corrector is exactly the half that is always
        // safe — take out what has grown, and leave what has gone.
        val d = ToneDoctor(listOf(0), mapOf(0 to Role.KEYS))
        var t = 0.0
        repeat(40) { d.onRta(0, FloatArray(100) { -30f }, t); t += 0.5 }
        d.snapshotChannel(0, floatArrayOf(0f, 0f, 0f, 0f), thrDb = null)
        // this channel goes dull: everything below 300 Hz drops 10 dB
        val dull = FloatArray(100) { i -> if (i < 40) -40f else -30f }
        val writes = ArrayList<ParamWrite>()
        repeat(60) { d.onRta(0, dull, t); t += 0.5
            writes.addAll(d.tick(setOf(0), true, false)) }
        assertTrue(d.state[0]!!.eqTarget.all { it <= 0f },
            "no band may ask to be lifted: " +
            d.state[0]!!.eqTarget.joinToString())
        assertTrue(writes.none { it.value > 0.5f + 1e-4f },
            "and none may be written above flat: " +
            writes.filter { it.value > 0.5f }.map { it.address }.distinct())
    }
}
