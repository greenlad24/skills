package com.stagemix.engine

import kotlin.math.abs
import kotlin.test.Test
import kotlin.test.assertTrue

/**
 * Regressions from the venue test team — the room itself misbehaving
 * rather than the band: a ground loop, an open mic nobody is using, a
 * DJ's stereo feed, a quietly playing trio, a channel muted mid-set.
 */
class VenueRegressionTest {
    private fun silence() = FloatArray(16) { -80f }

    private class R(val e: StageEngine = StageEngine(defaultRigProfile())) {
        var t = 0.0
        val writes = HashMap<Int, Int>(); val revs = HashMap<Int, Int>()
        private val dir = HashMap<Int, Int>(); private val last = HashMap<Int, Float>()
        fun takeover() = e.takeover((0 until 16).associateWith { -10f }, t)
        fun feed(l: FloatArray, sec: Double) {
            val end = t + sec; var nt = kotlin.math.floor(t) + 1.0
            while (t < end) {
                e.onMeters(l, t)
                if (t >= nt) {
                    for (w in e.tick(t)) {
                        writes.merge(w.channel, 1, Int::plus)
                        val d = w.levelDb - (last[w.channel] ?: -10f)
                        if (d != 0f) { val s = if (d > 0) 1 else -1
                            if ((dir[w.channel] ?: 0).let { it != 0 && it != s })
                                revs.merge(w.channel, 1, Int::plus)
                            dir[w.channel] = s }
                        last[w.channel] = w.levelDb
                    }
                    nt += 1.0
                }
                t += 0.05
            }
        }
        fun reset() { writes.clear(); revs.clear(); dir.clear() }
    }

    @Test fun `REG1 a static stage must produce a static mix`() {
        val r = R(); val lvl = silence().also { it[5] = -20f; it[6] = -20f; it[8] = -24f }
        r.feed(lvl, 5.0); r.takeover(); r.feed(lvl, 120.0); r.reset(); r.feed(lvl, 600.0)
        val w = r.writes[5] ?: 0; val rv = r.revs[5] ?: 0
        assertTrue(w <= 20 && rv <= 3, "keys fader must settle: $w writes, $rv reversals in 10 min")
    }

    @Test fun `REG2 a quiet band is mixed the same as a loud one`() {
        // The engine must not hear "quiet" as "not really playing". The
        // honest test is not that a quiet band is left flat — the pyramid
        // still applies — but that it gets the SAME mix a band 20 dB
        // louder would get. An activity gate that deafened the engine to
        // a quiet trio shows up here as a difference; nothing else does.
        val trioCh = listOf(2, 5, 6, 11)
        fun run(shift: Float): R {
            val r = R(); val trio = silence().also {
                it[5] = -47f + shift; it[6] = -47f + shift
                it[11] = -46f + shift; it[2] = -48f + shift }
            r.feed(trio, 5.0); r.takeover(); r.feed(trio, 600.0)
            return r
        }
        val q = run(0f); val l = run(20f)
        for (ch in trioCh)
            assertTrue(abs(q.e.offsetDb(ch) - l.e.offsetDb(ch)) <= 0.5f,
                ("ch%02d: the same trio 20 dB louder was mixed differently " +
                 "(%+.1f quiet vs %+.1f loud) — the engine is hearing " +
                 "level as intent").format(ch + 1, q.e.offsetDb(ch),
                    l.e.offsetDb(ch)))
        // and nobody was mistaken for silence and eased out of the mains
        for (ch in trioCh) {
            assertTrue(ch in q.e.activeChannels(),
                "ch%02d carries a real -47 dBFS source but left the ensemble"
                    .format(ch + 1))
            assertTrue(!q.e.isStaticSource(ch),
                "ch%02d is playing, not room tone".format(ch + 1))
        }
    }

    @Test fun `REG3 an open mic with only room noise is never boosted`() {
        val r = R()
        fun band(m: Float) = silence().also {
            it[0] = -20f; it[11] = -21f; it[5] = -24f; it[6] = -24f; it[8] = -22f; it[9] = m }
        r.feed(band(-23f), 5.0); r.takeover(); r.feed(band(-23f), 120.0); r.feed(band(-50f), 600.0)
        assertTrue(r.e.offsetDb(9) <= 1f,
            "an empty open mic at -50 dBFS was boosted %+.1f dB".format(r.e.offsetDb(9)))
        assertTrue(r.e.isStaticSource(9),
            "a mic sitting at a dead -50 dBFS under a -20 dB band must be " +
            "recognised as room tone, not treated as a quiet singer")
    }

    @Test fun `REG4 a constant hum channel never becomes the mix anchor`() {
        val ctl = R(); val solo = silence().also { it[8] = -24f }
        ctl.feed(solo, 5.0); ctl.takeover(); ctl.feed(solo, 300.0)
        val r = R(); val hum = silence().also { it[4] = -38f; it[8] = -24f }
        r.feed(hum, 5.0); r.takeover(); r.feed(hum, 300.0)
        val delta = r.e.offsetDb(8) - ctl.e.offsetDb(8)
        assertTrue(abs(delta) <= 3f, "a -38 dB ground loop moved the singer %+.1f dB".format(delta))
    }

    @Test fun `REG5 a mute and rejoin leaves no ratchet`() {
        // The resting fader may land anywhere inside the deadband — that
        // is what a deadband is — but repeating the same mute/rejoin
        // cycle must not walk it a little further every time.
        val r = R()
        fun band() = silence().also {
            it[0] = -20f; it[11] = -21f; it[5] = -24f; it[6] = -24f; it[4] = -22f; it[8] = -22f }
        r.feed(band(), 5.0); r.takeover(); r.feed(band(), 150.0)
        val rest = ArrayList<Float>()
        repeat(3) {
            r.feed(band().also { it[4] = -80f }, 90.0)
            r.feed(band(), 180.0)
            rest.add(r.e.offsetDb(4))
        }
        val db = r.e.settings.deadbandDb
        assertTrue(rest.max() - rest.min() <= 0.5f,
            "three identical mute/rejoin cycles rested at ${rest} — the " +
            "fader is walking, not settling")
        assertTrue(abs(rest.last()) <= db + 4f,
            "the fader wandered far outside its deadband: ${rest.last()}")
    }

    @Test fun `REG6 a stereo pair keeps its width`() {
        val r = R(); val dj = silence().also { it[5] = -16f; it[6] = -22f }
        r.feed(dj, 5.0); r.takeover(); r.feed(dj, 600.0)
        val width = (-16f + r.e.offsetDb(5)) - (-22f + r.e.offsetDb(6))
        assertTrue(width >= 5f, "6 dB of stereo width was squeezed to %.1f dB".format(width))
    }
}
