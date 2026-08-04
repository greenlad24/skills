package com.stagemix.engine

import kotlin.math.abs
import kotlin.test.Test
import kotlin.test.assertTrue

/**
 * ONE BALANCE, THEN HOLD.
 *
 * The point of the app is a mix that is RIGHT for most of the night, not
 * a mix that is being adjusted all night. Watching a real set, the engine
 * moved something every few seconds for two hours: each move defensible
 * on its own — the source drifted, so the target drifted — and the sum of
 * them a mix with no shape. When the anchor moved, targets swung twelve
 * dB, and a swing that size warps everything around it.
 *
 * So the contract these tests hold the engine to is:
 *
 *   · it converges, once;
 *   · then it stops, and ordinary playing does not restart it;
 *   · a SOLO gets through;
 *   · an INSTRUMENT ARRIVING gets through;
 *   · and what does get through is a trim, not a re-placement.
 */
class HoldTest {

    private val rig = defaultRigProfile()
    private val BASE = -10f

    private fun silence() = FloatArray(16) { -80f }

    private fun band() = silence().also {
        it[0] = -18f;  it[1] = -20f;  it[2] = -26f;  it[3] = -22f
        it[4] = -19f;  it[5] = -25f;  it[6] = -25f;  it[7] = -21f
        it[8] = -23f;  it[9] = -26f;  it[10] = -28f; it[11] = -17f
        it[12] = -29f; it[14] = -20f
        // ch14 Sax present, ch15 Harmonica and ch13 synth bass NOT —
        // they are the ones that will arrive later
    }

    /** a night, at the app's real cadence: meters 20 Hz, engine 1 Hz */
    private inner class Rig(settings: EngineSettings = EngineSettings()) {
        val e = StageEngine(rig, settings)
        private val rnd = java.util.Random(90210L)
        private val walk = FloatArray(16)
        private val buf = FloatArray(16)
        var t = 0.0
        val writes = ArrayList<Pair<Double, FaderWrite>>()

        /** the source, plus the wander a real player has on the meter */
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
                    for (w in e.tick(t)) writes.add(t to w)
                    next += 1.0
                }
                t += 0.05
            }
        }

        fun start(src: FloatArray) {
            run(5.0) { src }
            e.takeover((0 until 16).associateWith { BASE }, t)
        }

        fun fader(i: Int) = BASE + e.offsetDb(i)
        fun since(t0: Double) = writes.filter { it.first > t0 }
        /** total fader travel per channel since [t0] */
        fun travel(t0: Double): FloatArray {
            val last = FloatArray(16) { Float.NaN }
            val out = FloatArray(16)
            for ((tt, w) in writes) {
                if (tt <= t0) { last[w.channel] = w.levelDb; continue }
                if (!last[w.channel].isNaN())
                    out[w.channel] += abs(w.levelDb - last[w.channel])
                last[w.channel] = w.levelDb
            }
            return out
        }
    }

    // ------------------------------------------------------------------

    @Test fun `the mix settles and then stops moving`() {
        val r = Rig()
        val src = band()
        r.start(src)
        r.run(200.0) { src }          // converge and settle

        assertTrue(r.e.balanced,
            "after three minutes of one steady band the mix had still not " +
            "settled: ${r.e.settledCount()}")

        val mark = r.t
        r.run(400.0) { src }          // another seven minutes of the same

        val moved = r.travel(mark)
        val worst = moved.indices.maxByOrNull { moved[it] }!!
        val total = moved.sum()
        println("after settling, 400 s of ordinary playing moved the faders " +
            "%.2f dB in total (worst channel %s: %.2f dB)"
            .format(total, rig[worst].name, moved[worst]))
        // A held mix is allowed to breathe a little; it is not allowed to
        // keep working. Before this change the same stretch cost several
        // dB per channel.
        assertTrue(moved[worst] < 1.0f,
            "${rig[worst].name} moved ${moved[worst]} dB after the balance " +
            "was found — the mix is still being adjusted")
        assertTrue(total < 4f,
            "the whole desk moved $total dB after settling")
    }

    @Test fun `a solo still gets through`() {
        val r = Rig()
        val src = band()
        r.start(src)
        r.run(200.0) { src }
        assertTrue(r.e.balanced, "did not settle before the solo")

        val mark = r.t
        val before = r.fader(14)
        // the sax steps out front — 6 dB over where it has been sitting
        val solo = band().also { it[14] = -12f }
        r.run(120.0) { solo }

        val after = r.fader(14)
        println("sax fader %+.2f dB -> %+.2f dB during its solo"
            .format(before, after))
        assertTrue(r.since(mark).any { it.second.channel == 14 },
            "the sax took a solo and the engine did not move its fader at all")

        // and the rest of the band did NOT get re-placed around it
        val moved = r.travel(mark)
        val others = (0 until 16).filter { it != 14 }
        val worst = others.maxByOrNull { moved[it] }!!
        println("meanwhile the loudest other move was %s at %.2f dB"
            .format(rig[worst].name, moved[worst]))
        assertTrue(moved[worst] < 2.5f,
            "a sax solo re-warped ${rig[worst].name} by ${moved[worst]} dB")
    }

    @Test fun `an instrument arriving gets through`() {
        val r = Rig()
        val src = band()
        r.start(src)
        r.run(200.0) { src }
        assertTrue(r.e.balanced, "did not settle before the entry")

        val mark = r.t
        // the harmonica player picks up and comes in for the middle eight
        val withHarp = band().also { it[15] = -24f }
        r.run(120.0) { withHarp }

        assertTrue(r.since(mark).any { it.second.channel == 15 },
            "an instrument came in and the engine never gave it a place")
        val moved = r.travel(mark)
        println("harmonica arrived: its fader moved %.2f dB, the rest %.2f dB"
            .format(moved[15], moved.sum() - moved[15]))
    }

    @Test fun `a voice on a mic that was not in use gets through`() {
        val r = Rig()
        // ch10 ("Congo / Vox 3" — the third singer) is silent all set
        val src = band().also { it[10] = -80f }
        r.start(src)
        r.run(200.0) { src }
        assertTrue(r.e.balanced, "did not settle before the singer came in")

        val mark = r.t
        val singing = band().also { it[10] = -24f }
        r.run(120.0) { singing }

        assertTrue(r.since(mark).any { it.second.channel == 10 },
            "a singer picked up an unused mic and it was never placed")
        println("third singer came in; fader now %+.2f dB".format(r.fader(10)))
    }

    @Test fun `drift alone never restarts the mixing`() {
        val r = Rig()
        val src = band()
        r.start(src)
        r.run(200.0) { src }
        assertTrue(r.e.balanced)

        val mark = r.t
        // the whole band plays a quiet verse, then a loud chorus, twice —
        // a real dynamic, and not a reason to re-balance anything
        r.run(300.0) { t ->
            val d = if (((t - mark) / 60).toInt() % 2 == 0) -4f else +3f
            FloatArray(16) { if (src[it] <= -60f) src[it] else src[it] + d }
        }
        val moved = r.travel(mark)
        val worst = moved.indices.maxByOrNull { moved[it] }!!
        println("five minutes of verse/chorus dynamics moved the faders " +
            "%.2f dB in total (worst %s %.2f dB)"
            .format(moved.sum(), rig[worst].name, moved[worst]))
        assertTrue(moved[worst] < 1.5f,
            "${rig[worst].name} was re-mixed by ${moved[worst]} dB because " +
            "the band played a chorus")
    }

    @Test fun `the old continuously-steering behaviour is still available`() {
        // holding is a choice, not a hard-wiring: an operator who wants
        // the engine riding the faders all night can still have it
        val r = Rig(EngineSettings(holdAfterBalance = false))
        val src = band()
        r.start(src)
        r.run(200.0) { src }
        assertTrue(!r.e.balanced,
            "hold was switched off but the engine still declared a balance")
    }
}
