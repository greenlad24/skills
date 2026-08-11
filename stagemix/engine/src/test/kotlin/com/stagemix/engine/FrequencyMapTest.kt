package com.stagemix.engine

import kotlin.math.abs
import kotlin.test.Test
import kotlin.test.assertTrue

/**
 * A frequency map per channel.
 *
 * "I think the app is missing a frequency map on each channel to
 * understand how to treat it — and understand what is each channel."
 *
 * The RTA was always arriving; both things that consumed it folded a
 * hundred bins into seven band sums or four before anything could
 * reason about the shape. Seven numbers can say "there is energy down
 * low"; they cannot say where THIS kick stops, which is the only
 * honest way to choose a high-pass, and they cannot say that the snare
 * mic and the congas are fighting over the same 250 Hz.
 */
class FrequencyMapTest {

    /** a synthetic instrument: energy between two frequencies */
    private fun band(loHz: Float, hiHz: Float, peakDb: Float = -12f,
                     floorDb: Float = -70f): FloatArray {
        val lo = FrequencyMap.binOf(loHz)
        val hi = FrequencyMap.binOf(hiHz)
        return FloatArray(FrequencyMap.BINS) {
            if (it in lo..hi) peakDb else floorDb
        }
    }

    private fun feed(m: FrequencyMap, ch: Int, spec: FloatArray,
                     seconds: Double = 40.0) {
        var t = 0.0
        while (t < seconds) { m.onRta(ch, spec, true, 0.05f); t += 0.05 }
    }

    // ------------------------------------------------------------------
    @Test fun `it finds where an instrument actually stops`() {
        val m = FrequencyMap()
        // a kick: 40-120 Hz and nothing else
        feed(m, 0, band(40f, 120f))
        assertTrue(m.settled(0), "forty seconds is enough to have an opinion")

        val lo = m.lowEdgeHz(0)!!
        val hi = m.highEdgeHz(0)!!
        println("kick spans %.0f-%.0f Hz, loudest at %.0f"
            .format(lo, hi, m.peakHz(0)!!))
        assertTrue(lo in 30f..55f, "the bottom of it is around 40 Hz: $lo")
        assertTrue(hi in 100f..170f, "and the top around 120: $hi")
    }

    @Test fun `a high-pass belongs under the instrument, not at a preset`() {
        // The point of the whole class. A baritone whose fundamental is
        // 87 Hz gets a 100 Hz high-pass from a per-role preset, which
        // removes the bottom of his voice; the map says where to put it.
        val m = FrequencyMap()
        feed(m, 0, band(87f, 6000f))     // a low male voice
        feed(m, 1, band(180f, 8000f))    // a high female voice

        val bari = m.lowEdgeHz(0)!!
        val sop = m.lowEdgeHz(1)!!
        println("voice edges: baritone %.0f Hz, higher voice %.0f Hz"
            .format(bari, sop))
        assertTrue(bari < 100f,
            "the preset 100 Hz would cut into this singer: $bari")
        assertTrue(sop > bari + 40f,
            "and the two voices must not get the same answer: $bari vs $sop")
    }

    @Test fun `a resonance is a lump over the channel's own trend`() {
        val m = FrequencyMap()
        // a tom with a shell ringing at 250 Hz, on a sloped body
        val spec = FloatArray(FrequencyMap.BINS) { i ->
            val hz = FrequencyMap.hzOf(i)
            val body = if (hz in 80f..900f) -14f else -60f
            val ring = if (abs(i - FrequencyMap.binOf(250f)) <= 1) 9f else 0f
            body + ring
        }
        feed(m, 0, spec)
        val res = m.resonances(0)
        println("resonances: " + res.take(3).map {
            "%.0f Hz +%.1f dB Q%.1f".format(it.hz, it.overTrendDb, it.q) })
        assertTrue(res.isNotEmpty(), "a nine dB lump is worth noticing")
        assertTrue(abs(res.first().hz - 250f) < 60f,
            "and it is at 250 Hz: ${res.first().hz}")
        assertTrue(res.first().q > 1f,
            "a narrow lump wants a narrow cut: Q ${res.first().q}")
    }

    @Test fun `a smoothly tilted instrument has no resonance to fix`() {
        // No instrument is flat, and a tilted instrument is not a fault.
        // Measuring against flat rather than against the channel's own
        // trend would put a "cut" on every guitar cabinet ever made.
        val m = FrequencyMap()
        val tilted = FloatArray(FrequencyMap.BINS) { i -> -8f - i * 0.35f }
        feed(m, 0, tilted)
        assertTrue(m.resonances(0).isEmpty(),
            "a smooth slope is a voicing, not a problem: " +
            m.resonances(0).map { it.hz })
    }

    @Test fun `it says which two channels are in each other's way`() {
        val m = FrequencyMap()
        feed(m, 0, band(40f, 120f))       // kick
        feed(m, 1, band(180f, 400f))      // congas
        feed(m, 2, band(190f, 420f))      // snare mic, same territory
        feed(m, 3, band(3000f, 12000f))   // cymbals, nowhere near

        val congaVsSnare = m.overlap(1, 2)
        val congaVsKick = m.overlap(1, 0)
        val congaVsCym = m.overlap(1, 3)
        println("overlap  congas/snare %.2f  congas/kick %.2f  congas/cymbals %.2f"
            .format(congaVsSnare, congaVsKick, congaVsCym))

        assertTrue(congaVsSnare > 0.6f,
            "two channels in the same 200-400 Hz are masking each other")
        assertTrue(congaVsKick < 0.25f, "the kick is somewhere else")
        assertTrue(congaVsCym < 0.05f, "and the cymbals are nowhere near")

        val rivals = m.rivals(1, listOf(0, 2, 3))
        assertTrue(rivals.firstOrNull()?.first == 2,
            "the snare is what the congas are fighting: $rivals")
    }

    // ------------------------------------------------------------------
    @Test fun `nothing is claimed before it has been heard`() {
        // The analyzer visits one channel at a time, so a sixteen-piece
        // stage gives each channel a sixteenth of the night. A map built
        // from four seconds is a guess wearing a lab coat, and every
        // reader has to be able to tell the difference.
        val m = FrequencyMap()
        feed(m, 0, band(40f, 120f), seconds = 3.0)
        assertTrue(!m.settled(0), "three seconds is not a map")
        assertTrue(m.lowEdgeHz(0) == null, "so it declines to say")
        assertTrue(m.resonances(0).isEmpty())
        assertTrue(m.coverage(0) < 0.2f, "and it says how far along it is")
        assertTrue(m.describe(0).startsWith("still listening"))

        feed(m, 0, band(40f, 120f), seconds = 40.0)
        assertTrue(m.settled(0) && m.lowEdgeHz(0) != null,
            "and once it has been heard, it answers")
        println("described: " + m.describe(0))
    }

    @Test fun `silence is never folded into a channel's shape`() {
        // A spectrum taken while nothing is playing is a picture of the
        // room and the preamp. Averaging it in flattens everything this
        // class exists to find.
        val m = FrequencyMap()
        val quiet = FloatArray(FrequencyMap.BINS) { -95f }
        repeat(2000) { m.onRta(0, quiet, false, 0.05f) }
        assertTrue(m.coverage(0) == 0f, "nothing was playing, so nothing was learned")
        feed(m, 0, band(40f, 120f))
        assertTrue(abs(m.peakHz(0)!! - 70f) < 60f,
            "and the real shape is not diluted by it: ${m.peakHz(0)}")
    }

    @Test fun `a shape that is still moving reports itself unsettled`() {
        val m = FrequencyMap()
        val rnd = java.util.Random(4)
        var t = 0.0
        while (t < 60.0) {
            // a channel whose spectrum lurches around
            val jump = if ((t.toInt() / 2) % 2 == 0) 0f else 2500f
            m.onRta(0, band(200f + jump, 800f + jump), true, 0.05f)
            t += 0.05
        }
        val moving = m.stability(0)

        val m2 = FrequencyMap()
        feed(m2, 0, band(200f, 800f), seconds = 60.0)
        val steady = m2.stability(0)

        println("stability: lurching %.2f, steady %.2f".format(moving, steady))
        assertTrue(steady > moving + 0.2f,
            "an instrument that keeps its shape is the one worth treating: " +
            "$steady vs $moving")
    }

    @Test fun `bins and frequencies agree in both directions`() {
        for (hz in listOf(20f, 40f, 80f, 200f, 1000f, 5000f, 16000f)) {
            val b = FrequencyMap.binOf(hz)
            val back = FrequencyMap.hzOf(b)
            assertTrue(abs(back / hz - 1f) < 0.10f,
                "$hz Hz -> bin $b -> $back Hz")
        }
        // ten bins is one octave, which is what the console gives us
        assertTrue(abs(FrequencyMap.hzOf(10) - 40f) < 1f)
        assertTrue(abs(FrequencyMap.hzOf(20) - 80f) < 1f)
    }
}
