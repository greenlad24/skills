package com.stagemix.engine

import kotlin.math.abs
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class ToneDoctorTest {

    private fun rta(low: Float, lowMid: Float, highMid: Float, high: Float) =
        FloatArray(100) { i ->
            when {
                i < 26 -> low
                i < 54 -> lowMid
                i < 80 -> highMid
                else -> high
            }
        }

    // comp tending is opt-in (see DoctorSettings.compTendingEnabled);
    // these tests exercise it explicitly
    private fun doctor(): ToneDoctor = ToneDoctor(listOf(0, 1),
        settings = DoctorSettings(compTendingEnabled = true))

    private fun soundcheck(d: ToneDoctor, t0: Double = 0.0): Double {
        var t = t0
        repeat(20) { d.onRta(0, rta(-30f, -25f, -28f, -35f), t); t += 3.0 }
        repeat(40) { i ->
            // realistic GR: breathing with the music (a frozen value is
            // telemetry, not audio, and is distrusted by design)
            d.onGainReduction(0, -4f + 1.5f * kotlin.math.sin(0.7 * i).toFloat(), t)
            t += 1.0
        }
        d.snapshotChannel(0, floatArrayOf(0f, 1f, -1f, 0f), thrDb = -20f)
        return t
    }

    @Test fun `no writes before snapshot`() {
        val d = doctor()
        d.onRta(0, rta(-30f, -25f, -28f, -35f), 0.0)
        assertTrue(d.tick(setOf(0), upAllowed = true, frozenAll = false).isEmpty())
    }

    @Test fun `band drift corrected within 2db of snapshot gain, slewed`() {
        val d = doctor()
        var t = soundcheck(d)
        // high-mids climb 6 dB over time (harsh guitar amp crept up)
        repeat(60) { d.onRta(0, rta(-30f, -25f, -22f, -35f), t); t += 3.0 }
        val writes = ArrayList<ParamWrite>()
        repeat(30) { writes.addAll(d.tick(setOf(0), true, false)) }
        val hm = writes.filter { it.address == "/ch/01/eq/3/g" }
        assertTrue(hm.isNotEmpty(), "high-mid band must be corrected")
        // snapshot gain -1 dB, correction floor -2 => min float (-3+15)/30
        val minVal = hm.minOf { it.value }
        assertTrue(minVal >= (-3f + 15f) / 30f - 1e-4f,
            "EQ cut beyond snapshot-2dB rail: $minVal")
        // slew: consecutive writes differ by <= 0.25 dB (0.25/30 float)
        for (i in 1 until hm.size)
            assertTrue(abs(hm[i].value - hm[i - 1].value) <= 0.26f / 30f,
                "EQ must slew")
        // untouched bands stay untouched
        assertTrue(writes.none { it.address == "/ch/01/eq/1/g" })
    }

    @Test fun `small tonal drift inside deadband does nothing`() {
        val d = doctor()
        var t = soundcheck(d)
        repeat(60) { d.onRta(0, rta(-30f, -25f, -26.5f, -35f), t); t += 3.0 }
        assertTrue(d.tick(setOf(0), true, false)
            .none { "eq" in it.address }, "2 dB drift is inside the deadband")
    }

    @Test fun `eq boost waits for the upward gate`() {
        val d = doctor()
        var t = soundcheck(d)
        // highs collapse 6 dB (dull) -> wants a boost; gate closed
        repeat(60) { d.onRta(0, rta(-30f, -25f, -28f, -41f), t); t += 3.0 }
        assertTrue(d.tick(setOf(0), upAllowed = false, frozenAll = false)
            .none { "eq" in it.address }, "boost must respect the gate")
        val open = d.tick(setOf(0), upAllowed = true, frozenAll = false)
        assertTrue(open.any { it.address == "/ch/01/eq/4/g" })
    }

    @Test fun `comp threshold restores soundcheck gr profile, railed`() {
        val d = doctor()
        var t = soundcheck(d)  // ref GR -4 dB
        // singer backs off: comp stops catching (GR ~0)
        repeat(160) { i ->
            d.onGainReduction(0, -0.2f + 0.15f * kotlin.math.sin(0.9 * i).toFloat(), t)
            t += 1.0
        }
        val writes = ArrayList<ParamWrite>()
        repeat(40) { writes.addAll(d.tick(setOf(0), true, false)) }
        val thr = writes.filter { it.address == "/ch/01/dyn/thr" }
        assertTrue(thr.isNotEmpty(), "threshold must ease down")
        // -20 snapshot, max -4 rail -> floor float (-24+60)/60
        assertTrue(thr.minOf { it.value } >= (-24f + 60f) / 60f - 1e-4f)
        assertTrue(thr.all { it.value <= (-20f + 60f) / 60f + 1e-4f },
            "easing down means threshold only moves below snapshot here")
    }

    @Test fun `comp untouched when soundcheck showed no real compression`() {
        val d = doctor()
        var t = 0.0
        repeat(20) { d.onRta(1, rta(-30f, -25f, -28f, -35f), t); t += 3.0 }
        repeat(40) { i ->  // barely working, but breathing
            d.onGainReduction(1, -0.2f + 0.1f * kotlin.math.sin(0.6 * i).toFloat(), t)
            t += 1.0
        }
        d.snapshotChannel(1, floatArrayOf(0f, 0f, 0f, 0f), thrDb = -10f)
        repeat(80) { i ->
            d.onGainReduction(1, -8f + 1.2f * kotlin.math.sin(0.8 * i).toFloat(), t)
            t += 1.0
        }
        assertTrue(d.tick(setOf(1), true, false)
            .none { it.address == "/ch/02/dyn/thr" },
            "no comp tending when soundcheck GR was ~0 (comp not in use)")
    }

    @Test fun `implausible gr telemetry is ignored`() {
        val d = doctor()
        soundcheck(d)
        d.onGainReduction(0, +12f, 999.0)   // nonsense (positive)
        d.onGainReduction(0, -70f, 999.5)   // nonsense (too deep)
        // GR EMA still the soundcheck-ish value; no wild threshold moves
        val w = d.tick(setOf(0), true, false)
        assertTrue(w.none { it.address == "/ch/01/dyn/thr" })
    }

    @Test fun `frozen channel and frozen all stop everything`() {
        val d = doctor()
        var t = soundcheck(d)
        repeat(60) { d.onRta(0, rta(-30f, -25f, -20f, -35f), t); t += 3.0 }
        assertTrue(d.tick(setOf(0), true, frozenAll = true).isEmpty())
        d.state[0]!!.frozen = true
        assertTrue(d.tick(setOf(0), true, frozenAll = false).isEmpty())
    }

    @Test fun `inactive channel is never doctored`() {
        val d = doctor()
        var t = soundcheck(d)
        repeat(60) { d.onRta(0, rta(-30f, -25f, -20f, -35f), t); t += 3.0 }
        assertTrue(d.tick(emptySet(), true, false).isEmpty())
    }

    @Test fun `new singer register is adopted, not fought`() {
        // vocal channel: male singer at soundcheck (fundamental ~120 Hz)
        val d = ToneDoctor(listOf(0), mapOf(0 to Role.VOCAL))
        // floor high enough that neither voice trips the harshness
        // guard — this test is about register adoption, not harshness
        fun voice(fundLo: Float, fundHi: Float, presence: Float) =
            FloatArray(100) { i ->
                when (i) {
                    in 23..31 -> fundLo
                    in 32..40 -> fundHi
                    in 54..79 -> presence
                    else -> -45f
                }
            }
        var t = 0.0
        repeat(30) { d.onRta(0, voice(-18f, -30f, -30f), t); t += 3.0 }
        d.snapshotChannel(0, floatArrayOf(0f, 0f, 0f, 0f), thrDb = -20f)
        // female singer takes the mic: fundamental an octave up AND a
        // brighter presence — a naive doctor would slam the EQ
        repeat(40) { d.onRta(0, voice(-32f, -16f, -28f), t); t += 3.0 }
        val writes = ArrayList<ParamWrite>()
        repeat(20) { writes.addAll(d.tick(setOf(0), true, false)) }
        assertTrue(writes.none { "eq" in it.address },
            "the new voice's sound must be ADOPTED as its own reference, " +
            "not corrected toward the previous singer: $writes")
        // and switching BACK to the male singer recalls his reference
        repeat(40) { d.onRta(0, voice(-18f, -30f, -30f), t); t += 3.0 }
        val back = ArrayList<ParamWrite>()
        repeat(10) { back.addAll(d.tick(setOf(0), true, false)) }
        assertTrue(back.none { "eq" in it.address },
            "returning singer matches his own stored reference")
    }

    @Test fun `band folding reports tone SHAPE, not absolute level`() {
        // shape is what matters: the same tone 20 dB louder must fold to
        // the same four numbers, or "got louder" reads as "changed tone"
        val quiet = ToneDoctor.foldBands(rta(-10f, -20f, -30f, -40f))
        val loud = ToneDoctor.foldBands(rta(10f, 0f, -10f, -20f))
        for (b in 0 until 4)
            assertEquals(quiet[b], loud[b], 0.01f,
                "band $b changed when only the level did")
        // and the shape itself is still resolved: low band is the
        // brightest of this spectrum, high band the darkest
        assertTrue(quiet[0] > quiet[1] && quiet[1] > quiet[2] &&
                quiet[2] > quiet[3], "band ordering lost: ${quiet.toList()}")
        assertEquals(0f, quiet.sum(), 0.01f, "shape must be zero-mean")
    }
}
