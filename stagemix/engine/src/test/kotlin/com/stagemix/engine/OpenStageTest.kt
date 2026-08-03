package com.stagemix.engine

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * The user's actual night, minute by minute: a singer with an acoustic
 * guitar opens; a piano/vocal duet follows; a drummer joins with no
 * bass player; the bass arrives later. The mix must stay right through
 * every lineup change — with no soundcheck.
 */
class OpenStageTest {

    private val chans = defaultRigProfile()
    private fun engine() = StageEngine(chans)
    private fun faders() = (0 until 16).associateWith { -10f }

    private fun run(e: StageEngine, levels: FloatArray, from: Double,
                    sec: Double): Pair<List<FaderWrite>, Double> {
        val writes = ArrayList<FaderWrite>()
        var t = from
        var nextTick = from + 1.0
        while (t < from + sec) {
            e.onMeters(levels, t)
            if (t >= nextTick) { writes += e.tick(t); nextTick += 1.0 }
            t += 0.05
        }
        return writes to t
    }

    private fun silence() = FloatArray(16) { -80f }

    @Test fun `act 1 - singer plus acoustic guitar alone mixes correctly`() {
        val e = engine()
        var t = 0.0
        // acoustic guitar on Guitar DI (ch 8 -> idx 7), singer on Vocal
        // Center (idx 8). Guitar source hot relative to the voice.
        val duo = silence().also { it[7] = -18f; it[8] = -24f }
        run(e, duo, t, 5.0).also { t = it.second }
        e.takeover(faders(), t)
        val (writes, _) = run(e, duo, t, 240.0)
        assertFalse(e.hasDrums); assertFalse(e.hasBass)
        // with no foundation, the accompaniment anchors: the VOICE must
        // end up above the guitar (pyramid: vocal +1 vs rhythm-gtr -5)
        val gtrLast = writes.filter { it.channel == 7 }.lastOrNull()
        val voxLast = writes.filter { it.channel == 8 }.lastOrNull()
        assertTrue(gtrLast != null || voxLast != null,
            "the duo must be balanced, not left alone")
        val gtrDb = gtrLast?.levelDb ?: -10f
        val voxDb = voxLast?.levelDb ?: -10f
        // contributions: source + fader
        assertTrue((-24f + voxDb) > (-18f + gtrDb),
            "voice must sit above the acoustic guitar: " +
            "vox=${-24f + voxDb} gtr=${-18f + gtrDb}")
    }

    @Test fun `act 3 - drummer joins with no bass - piano covers the low end`() {
        val e = engine()
        var t = 0.0
        // piano + voice playing
        val duet = silence().also {
            it[5] = -24f; it[6] = -24f; it[8] = -22f }
        run(e, duet, t, 5.0).also { t = it.second }
        e.takeover(faders(), t)
        run(e, duet, t, 40.0).also { t = it.second }
        assertFalse(e.keysLowFill, "no drums yet — no low-fill")
        // drummer sits in: kick + snare, NO bass channels
        val drums = duet.copyOf().also { it[0] = -19f; it[1] = -23f }
        run(e, drums, t, 60.0).also { t = it.second }
        assertTrue(e.hasDrums, "drums must be detected")
        assertFalse(e.hasBass, "no bass yet")
        assertTrue(e.keysLowFill,
            "piano must be told to cover the bass frequencies")
        assertTrue(e.decisions.any { it.kind == "ensemble" },
            "lineup change must be logged")
        // -- act 4: bass player arrives
        val full = drums.copyOf().also { it[11] = -20f }
        run(e, full, t, 60.0)
        assertTrue(e.hasBass, "bass must be detected")
        assertFalse(e.keysLowFill, "piano hands the low end back")
    }

    @Test fun `low-fill lifts the keys low band in the doctor`() {
        val d = ToneDoctor(listOf(5), mapOf(5 to Role.KEYS))
        val flat = FloatArray(100) { -30f }
        var t = 0.0
        repeat(30) { d.onRta(5, flat, t); t += 3.0 }
        d.snapshotChannel(5, floatArrayOf(0f, 0f, 0f, 0f), thrDb = null)
        // no low-fill: nothing to do
        assertTrue(d.tick(setOf(5), true, false).none { "eq/1" in it.address })
        // drums-no-bass: low band lifts toward the +2 rail, slewed
        d.setLowFill(5, true)
        val writes = ArrayList<ParamWrite>()
        repeat(12) { writes.addAll(d.tick(setOf(5), true, false)) }
        val low = writes.filter { it.address == "/ch/06/eq/1/g" }
        assertTrue(low.isNotEmpty(), "low band must lift")
        assertTrue(low.last().value <= (2f + 15f) / 30f + 1e-4f, "railed at +2")
        // bass arrives: back to neutral
        d.setLowFill(5, false)
        val back = ArrayList<ParamWrite>()
        repeat(12) { back.addAll(d.tick(setOf(5), true, false)) }
        assertTrue(back.filter { it.address == "/ch/06/eq/1/g" }
            .lastOrNull()?.value?.let { it <= (0f + 15f) / 30f + 1e-4f } != false,
            "low band returns to snapshot once the bass is back")
    }

    @Test fun `duet - both vocal mics sit near the top together`() {
        val e = engine()
        var t = 0.0
        val duet = silence().also {
            it[5] = -24f; it[6] = -24f     // piano bed
            it[8] = -22f; it[9] = -23f     // BOTH singers on
        }
        run(e, duet, t, 5.0).also { t = it.second }
        e.takeover(faders(), t)
        val (_, t2) = run(e, duet, t, 120.0)
        // both vocal contributions must land within ~2 dB of each other
        val c8 = -22f + (-10f + e.offsetDb(8))
        val c9 = -23f + (-10f + e.offsetDb(9))
        assertTrue(kotlin.math.abs(c8 - c9) < 2.5f,
            "duet partners must sit together: $c8 vs $c9")
    }

    @Test fun `lineup changes open the fast lane for everyone`() {
        val e = engine()
        var t = 0.0
        val duo = silence().also { it[7] = -18f; it[8] = -24f }
        run(e, duo, t, 5.0).also { t = it.second }
        e.takeover(faders(), t)
        run(e, duo, t, 30.0).also { t = it.second }
        val before = e.decisions.count { it.kind == "ensemble" }
        val drums = duo.copyOf().also { it[0] = -19f }
        run(e, drums, t, 30.0)
        assertTrue(e.decisions.count { it.kind == "ensemble" } > before)
    }
}
