package com.stagemix.engine

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Three nights of a real band, in shadow, on the band's own MR18.
 *
 * The log is 55 MB and the app never wrote a fader — the operator
 * pressed the big button marked "Take over the mains" and it sent a
 * re-baseline. That one is a UI fix. Everything else here is the engine
 * shaking itself apart on material it will meet every night:
 *
 *   · 613 changes of mind about whether the band was playing, median
 *     gap ONE SECOND, one of them reported as "1 of about 5 channels
 *     playing" with the whole band on stage.
 *   · 321 instruments "arriving" and 96 declared silent and marked to
 *     be pulled 12 dB down, over three nights of continuous music.
 *   · An anchor that moved seven dB every five seconds as members fell
 *     in and out of it.
 *   · 37 % of every metered second held under "big level change —
 *     waiting", which is the guard against somebody moving a master
 *     reading a kick drum's decay.
 *
 * One cause under all of it: the activity gate had level hysteresis and
 * no time. A struck instrument is under any gate between hits.
 */
class ThreeNightsTest {

    private val rig = defaultRigProfile()

    private class Run(val e: StageEngine, startAt: Double = 0.0) {
        var t = startAt
        private var next = startAt + 1.0
        val writes = ArrayList<Pair<Double, FaderWrite>>()
        fun run(sec: Double, src: (Double) -> FloatArray) {
            val end = t + sec - 1e-9
            while (t < end) {
                e.onMeters(src(t), t)
                if (t >= next - 1e-9) {
                    for (w in e.tick(t)) writes.add(t to w)
                    next += 1.0
                }
                t += 0.05
            }
        }
        fun start(src: (Double) -> FloatArray) {
            run(5.0, src)
            e.takeover((0 until 16).associateWith { -10f }, t)
        }
    }

    private fun silence() = FloatArray(16) { -80f }

    /** a struck sound: loud for a moment, then nothing until the next one */
    private fun hit(t: Double, per: Double, phase: Double,
                    peak: Float, decay: Double): Float =
        maxOf(peak - (((t - phase) % per + per) % per / decay).toFloat() * 40f,
            -100f)

    /** a rock band: drums that hit, and instruments that sustain */
    private fun band(t: Double): FloatArray {
        val beat = 0.5
        return silence().also {
            it[0] = hit(t, beat * 2, 0.0, -18f, 0.16)     // kick
            it[1] = hit(t, beat * 2, beat, -20f, 0.13)    // snare
            it[2] = hit(t, beat / 2, 0.0, -27f, 0.10)     // overheads
            it[3] = -22f                                   // bass
            it[4] = -21f                                   // guitar
            it[5] = -24f; it[6] = -24f                     // piano
            it[8] = -20f                                   // vocal
            it[11] = -19f                                  // bass DI
            it[14] = -26f                                  // horn
        }
    }

    // ------------------------------------------------------------------
    @Test fun `a drummer is still playing between the hits`() {
        // The gate is what everything else is built on: "is this channel
        // playing" decides the anchor, the ensemble, the arrival test,
        // the silence test and whether the band is between songs. A kick
        // at 120 bpm is over any gate for a tenth of a second and thirty
        // dB under it for the rest of the bar.
        val e = StageEngine(rig, EngineSettings(mode = BalanceMode.KEEP))
        val r = Run(e)
        r.start { band(it) }
        var closed = 0
        var last = true
        val end = r.t + 120.0
        while (r.t < end) {
            r.run(0.25) { band(it) }
            val open = e.state[0]!!.gateOpen
            if (last && !open) closed++
            last = open
        }
        println("the kick's gate shut $closed times in two minutes of playing")
        assertTrue(closed == 0,
            "the drummer never stopped: the gate shut $closed times")
    }

    @Test fun `two minutes of a band is not two hundred songs`() {
        val e = StageEngine(rig, EngineSettings(mode = BalanceMode.KEEP))
        val r = Run(e)
        r.start { band(it) }
        r.run(180.0) { band(it) }
        val flips = e.decisions.count { it.kind == "gap" || it.kind == "music" }
        val arrivals = e.decisions.count { it.kind == "arrive" }
        // only the channels that were actually playing: a channel with
        // nothing plugged into it is silent, and saying so is the job
        val playing = intArrayOf(0, 1, 2, 3, 4, 5, 6, 8, 11, 14)
        val held = e.decisions.count {
            it.kind == "held-down" && it.channel in playing.toList() }
        println("in three minutes: $flips gap/music flips, $arrivals " +
            "arrivals, $held held down")
        assertTrue(flips == 0,
            "the band played the whole time: $flips changes of mind")
        assertTrue(arrivals == 0, "and nothing arrived: $arrivals")
        assertTrue(held == 0,
            "and nothing was silent for twenty-five seconds: $held")
    }

    @Test fun `a kick drum is not somebody moving a master fader`() {
        // The broadband guard measured the mean level change between
        // consecutive 50 ms frames of RAW meter, and a kick decays
        // thirty dB inside a fifth of a second. On three nights it held
        // the engine still for 37 % of every metered second — and what
        // it exists for, somebody changing a master or a preamp, is
        // still perfectly visible on a three-second average.
        val e = StageEngine(rig, EngineSettings(mode = BalanceMode.KEEP))
        val r = Run(e)
        r.start { band(it) }
        r.run(60.0) { band(it) }
        var held = 0; var n = 0
        val end = r.t + 60.0
        while (r.t < end) {
            r.run(1.0) { band(it) }
            n++
            if (e.holdReason(r.t)?.contains("big level change") == true) held++
        }
        println("held for a big level change on $held of $n seconds")
        assertTrue(held == 0, "drums are not a level change: $held of $n")

        // and the thing it is actually for still works: everything on
        // the stage drops 12 dB at once, which is a hand on a master
        r.run(3.0) { band(it).also { b -> for (i in b.indices) b[i] -= 12f } }
        assertTrue(e.holdReason(r.t)?.contains("big level change") == true,
            "the whole stage moved together and nothing noticed: " +
            e.holdReason(r.t))
    }

    @Test fun `the anchor does not change its mind every five seconds`() {
        val e = StageEngine(rig, EngineSettings(mode = BalanceMode.KEEP))
        val r = Run(e)
        r.start { band(it) }
        r.run(90.0) { band(it) }
        val seen = ArrayList<Float>()
        val members = HashSet<String>()
        val end = r.t + 60.0
        while (r.t < end) {
            r.run(2.0) { band(it) }
            val a = e.anchorInfo()
            a.contributionDb?.let { seen.add(it) }
            members.add(a.members.sorted().joinToString("+"))
        }
        val spread = (seen.maxOrNull() ?: 0f) - (seen.minOrNull() ?: 0f)
        println("anchor moved %.1f dB over a minute, membership seen: %s"
            .format(spread, members))
        assertTrue(spread < 3f,
            "the mix's reference level wandered %.1f dB while the band " .format(spread) +
            "played the same thing")
        assertTrue(members.size == 1,
            "and it was measured from a different set of channels " +
            "${members.size} times: $members")
    }

    @Test fun `a rest in the part is not a channel that needs lifting`() {
        // The gate hold keeps a channel in the mix through the gaps in
        // its part. It must not also make those gaps look like a player
        // who has got quieter — or every rest becomes a lift and every
        // re-entry a jump.
        val e = StageEngine(rig, EngineSettings(mode = BalanceMode.LEAD))
        val r = Run(e)
        // a horn that plays two bars and rests two, forever
        fun withHorn(t: Double) = band(t).also {
            it[14] = if ((t / 4.0).toInt() % 2 == 0) -26f else -90f
        }
        r.start { withHorn(it) }
        r.run(120.0) { withHorn(it) }
        r.writes.clear()
        r.run(60.0) { withHorn(it) }
        // A lift during a BAR OF REST is the fault; a lift while the
        // horn is playing is the engine doing its job in LEAD mode.
        val duringRest = r.writes.filter { it.second.channel == 14 }
            .zipWithNext()
            .count { (a, b) ->
                b.second.levelDb > a.second.levelDb + 0.1f &&
                    (b.first / 4.0).toInt() % 2 == 1 }
        println("horn raised $duringRest times while resting between phrases")
        assertTrue(duringRest == 0,
            "the horn was lifted $duringRest times for resting")
    }

    @Test fun `the rig's locks survive being saved and loaded`() {
        // The app rebuilt each ChannelConfig from stored preferences —
        // index, name and role — which quietly dropped `locked` and
        // `pairWith`. So the first time it saved anything, the kick,
        // the snare and BOTH bass DIs stopped being locked, and on the
        // next real night the listener re-roled "BASS DI" and "DI 2" to
        // congas. The engine's half of that contract is tested here;
        // the app rebuilds structure from the profile by index.
        val profile = defaultRigProfile()
        assertTrue(profile[0].locked && profile[1].locked,
            "the kick and snare microphones are taped to a drum kit")
        assertTrue(profile[11].locked && profile[13].locked,
            "and both bass DIs are the bass")
        val e = StageEngine(profile, EngineSettings(mode = BalanceMode.KEEP))
        for (i in intArrayOf(0, 1, 11, 13))
            assertTrue(e.state[i]!!.roleLocked,
                "ch${i + 1} arrived unlocked")
    }

    @Test fun `a console that truncates names still says drums`() {
        // "DRUM OVRH", "DRUM SNAR", "DRUM KICK" — eight characters is
        // all this desk stores, so "overhead" never matched and the
        // overheads were re-roled between percussion and VOCAL eight
        // times over three nights. A vocal role is one the engine
        // promises not to move.
        val id = InstrumentId()
        assertEquals(listOf(Role.PERCUSSION), id.namedRoles("DRUM OVRH_11"))
        assertEquals(listOf(Role.PERCUSSION), id.namedRoles("DRUM SNAR_4"))
        assertTrue(Role.FOUNDATION in id.namedRoles("DRUM KICK_2"),
            "a kick is still the low end: " + id.namedRoles("DRUM KICK_2"))
        assertTrue(Role.VOCAL !in id.namedRoles("DRUM OVRH_11"),
            "and nothing called DRUM is a singer")
    }
}
