package com.stagemix.engine

import kotlin.math.abs
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * The first night on the tablet, on the band's own MR18.
 *
 * Three hours and eighteen minutes, and it went badly in ways the Mac
 * bench could not have shown. Everything here is taken from that log.
 * The headline number is that the lead vocal sat twelve dB down for two
 * and a half hours while the operator pressed REBALANCE twenty times,
 * and the chain that got it there ran through four separate defects, so
 * each of them gets a test:
 *
 *   · The engine was handed a clock whose zero was the tablet's boot
 *     time. "Silent for how long?" is asked against a field that starts
 *     at zero, so the answer on the first pass was 95938 seconds, and
 *     sixty seconds into the show the engine took seven channels out of
 *     the mains — one of them a singer's microphone, logged as "not an
 *     instrument — hum or an open mic nobody is using".
 *
 *   · Every channel it recognised all night, it called congas: both
 *     singers, both pianos, both guitars. The kit test measured whether
 *     a channel plays in time with other channels, which in a band is
 *     everybody.
 *
 *   · Being called percussion is not cosmetic. It took both vocal
 *     channels out of the set of roles the engine promises not to move,
 *     so the guarantee the operator asked for in as many words —
 *     "do not move the singing faders" — was revoked by a spectrum.
 *
 *   · And the operator was muting the band from Mixing Station between
 *     songs, which the engine could not see at all: `/meters/1` is
 *     pre-fader AND pre-mute, so a muted channel meters like a playing
 *     one. "When everything is muted the app shouldn't be balancing."
 */
class TabletNightTest {

    private val rig = defaultRigProfile()

    /** meters at 20 Hz, engine at 1 Hz, as the app really runs them */
    private class Run(val e: StageEngine, val base: Float = -10f,
                      /** where the caller's clock starts */
                      startAt: Double = 0.0) {
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
            e.takeover((0 until 16).associateWith { base }, t)
        }
    }

    private fun silence() = FloatArray(16) { -80f }

    /** a struck sound: up fast, gone within a beat */
    private fun hit(t: Double, per: Double, phase: Double,
                    peak: Float, decay: Double): Float =
        maxOf(peak - (((t - phase) % per + per) % per / decay).toFloat() * 40f,
            -100f)

    // ==================================================================
    // 1. the clock
    // ==================================================================
    @Test fun `a clock that does not start at zero must not empty the mix`() {
        // The tablet handed the engine System.nanoTime(), which on
        // Android is time since the device booted. This one has been
        // awake for a day and a bit — exactly the log's 95938.
        val e = StageEngine(rig, EngineSettings(mode = BalanceMode.LEAD))
        val r = Run(e, startAt = 95_877.0)
        // the whole band, so that nothing is legitimately silent
        val band = FloatArray(16) { -20f - (it % 5) }
        r.start { band }
        r.run(90.0) { band }

        val muted = e.decisions.filter { it.kind == "mute" }
        assertTrue(muted.isEmpty(),
            "every channel is playing and the engine has been listening " +
            "for ninety seconds. Muted anyway: " + muted.map { it.reason })

        // And the duration it reports has to be a duration it observed.
        // "silent 95938s" was the tell: twenty-six hours of evidence
        // gathered in the first minute of the show.
        val e2 = StageEngine(rig, EngineSettings(mode = BalanceMode.LEAD))
        val r2 = Run(e2, startAt = 95_877.0)
        val sparse = silence().also {
            it[0] = -18f; it[1] = -20f; it[8] = -23f; it[11] = -17f
        }
        r2.start { sparse }
        r2.run(120.0) { sparse }
        val claims = Regex("silent (\\d+)s")
        for (d in e2.decisions.filter { it.kind == "mute" }) {
            val n = claims.find(d.reason)?.groupValues?.get(1)?.toInt()
                ?: continue
            assertTrue(n <= 130,
                "the engine cannot have watched this channel for longer " +
                "than it has been running: ${d.reason}")
        }
    }

    @Test fun `silence is measured from when we started listening`() {
        // The same rig on a clock that DOES start at zero, so the two
        // can be compared: whatever the caller's zero is, the engine
        // must reach the same conclusions.
        fun mutesAfter(startAt: Double): List<String> {
            val e = StageEngine(rig, EngineSettings(mode = BalanceMode.LEAD))
            val r = Run(e, startAt = startAt)
            val band = silence().also {
                it[0] = -18f; it[1] = -20f; it[8] = -23f; it[11] = -17f
            }
            r.start { band }
            r.run(120.0) { band }
            return e.decisions.filter { it.kind == "mute" }
                .map { "ch${it.channel}" }
        }
        assertEquals(mutesAfter(0.0), mutesAfter(95_877.0),
            "the engine's conclusions must not depend on what the " +
            "caller's clock happens to call 'now'")
    }

    // ==================================================================
    // 2. the recogniser
    // ==================================================================
    @Test fun `a singer who sings in time with the band is not a conga`() {
        // This is the night's identification defect, reduced. A drum
        // kit and a singer, and the singer is ON THE BEAT — because
        // singers are. The old kit test measured coincidence alone, so
        // the singer scored as high as the congas did, and the log says
        // what came of that: "VOCAL CEN_50: vocal -> percussion — it
        // sounds like congas / toms".
        val ens = Ensemble(6)
        val beat = 0.5
        var t = 0.0
        val lv = FloatArray(6)
        val act = BooleanArray(6) { true }
        while (t < 240.0) {
            lv[0] = hit(t, beat * 2, 0.0, -18f, 0.18)   // kick
            lv[1] = hit(t, beat * 2, beat, -20f, 0.15)  // snare
            lv[2] = hit(t, beat, 0.0, -24f, 0.22)       // congas
            // The singer. Enters on the beat, exactly like the congas —
            // and then HOLDS the note, which is the whole difference.
            val phrase = ((t / beat).toInt()) % 4
            lv[3] = if (phrase < 3) -21f + (phrase * 0.4f) else -100f
            lv[4] = -22f                                 // bass, sustained
            lv[5] = -100f
            for (k in 0 until 6) act[k] = lv[k] > -90f
            ens.onFrame(lv, act, 0.05f)
            t += 0.05
        }
        val kit = (0..4).map { ens.kitAffinity(it) }
        val perc = (0..4).map { ens.percussive(it) }
        println("kit:        " + kit.mapIndexed { c, v ->
            "ch$c %.2f".format(v) }.joinToString("  "))
        println("percussive: " + perc.mapIndexed { c, v ->
            "ch$c %.2f".format(v) }.joinToString("  "))

        for (drum in 0..2)
            assertTrue(kit[drum] > kit[3] * 2f + 0.05f,
                "the drums must be far more of a kit than the singer is " +
                "(drum ch$drum ${kit[drum]}, singer ${kit[3]})")
        assertTrue(perc[3] < 0.5f,
            "a held note is not a struck one, however well it is timed " +
            "(${perc[3]})")
        assertTrue(perc[4] < 0.5f, "nor is a bass (${perc[4]})")
        assertTrue(perc[0] > 0.5f, "a kick is (${perc[0]})")
    }

    @Test fun `playing in time is not on its own enough to be a drum`() {
        // Two channels that lock perfectly to each other, and neither
        // of them stops. A guitar and a keyboard playing the same
        // rhythm part scored a full kit affinity before this.
        val ens = Ensemble(4)
        val beat = 0.5
        var t = 0.0
        val lv = FloatArray(4)
        val act = BooleanArray(4)
        while (t < 200.0) {
            val on = ((t / beat).toInt()) % 2 == 0
            lv[0] = if (on) -20f else -24f    // never falls away
            lv[1] = if (on) -22f else -26f    // and neither does this
            lv[2] = -100f; lv[3] = -100f
            for (k in 0 until 4) act[k] = lv[k] > -90f
            ens.onFrame(lv, act, 0.05f)
            t += 0.05
        }
        assertTrue(ens.coincidence(0, 1) > 0.5f,
            "they are locked together — that much was always true " +
            "(${ens.coincidence(0, 1)})")
        assertTrue(ens.kitAffinity(0) < 0.25f,
            "but neither of them is struck, so neither is a drum " +
            "(${ens.kitAffinity(0)})")
    }

    // ==================================================================
    // 3. a guess may not revoke a promise
    // ==================================================================
    @Test fun `recognition cannot take a singer out of the held roles`() {
        val e = StageEngine(rig, EngineSettings(mode = BalanceMode.KEEP))
        val vox = rig.first { it.role == Role.VOCAL }.index
        val r = Run(e)
        val band = silence().also {
            it[0] = -18f; it[3] = -22f; it[vox] = -20f; it[11] = -17f
        }
        r.start { band }
        r.run(60.0) { band }
        e.adoptBalance(r.t)
        assertTrue(e.balanceAdopted, "there is a balance to defend")

        // Now the recogniser changes its mind, as confidently and for
        // as long as it likes.
        r.run(600.0) { band }
        assertEquals(Role.VOCAL, e.state[vox]!!.role,
            "a balance the operator approved is not overturned by a " +
            "spectrum: whatever the audio thinks it heard, this channel " +
            "was a singer when they said keep it")
    }

    @Test fun `telling it what a channel is releases what it did while wrong`() {
        // The half of this that was missing. Locking the role stopped
        // the engine getting it wrong again; it did nothing about the
        // channel already being pinned at the bottom of the authority
        // range — and handing THAT to the hold meant twelve dB down,
        // now with a guarantee.
        val e = StageEngine(rig, EngineSettings(mode = BalanceMode.KEEP))
        val ch = rig.first { it.role == Role.VOCAL }.index
        val r = Run(e)
        val band = silence().also {
            it[0] = -18f; it[3] = -22f; it[ch] = -20f; it[11] = -17f
        }
        r.start { band }
        r.run(60.0) { band }

        // put it where the night put it: at the floor, and held there
        val st = e.state[ch]!!
        st.offset = -12f
        st.planContrib = -40f
        st.planFaderDb = -22f
        st.settled = true

        assertTrue(e.setRole(ch, Role.VOCAL))
        assertEquals(0f, st.target,
            "being told what a channel is means giving the fader back " +
            "to where the operator had it, not defending our mistake")
        assertTrue(st.planContrib == null,
            "and throwing away the plan that put it there")
    }

    // ==================================================================
    // 4. the mute keys
    // ==================================================================
    @Test fun `a muted stage is not balanced at all`() {
        val e = StageEngine(rig, EngineSettings(mode = BalanceMode.KEEP))
        val r = Run(e)
        // pre-fader meters: a full-strength signal on every channel,
        // which is exactly what a muted desk still reports
        val band = silence().also {
            it[0] = -18f; it[1] = -20f; it[3] = -22f
            it[8] = -23f; it[11] = -17f
        }
        r.start { band }
        r.run(90.0) { band }
        r.writes.clear()

        // the operator mutes the band from Mixing Station
        for (ch in 0 until 16) e.setChannelMuted(ch, true)
        assertTrue(e.stageMuted, "the whole stage is out")
        r.run(240.0) { band }
        assertTrue(r.writes.isEmpty(),
            "there is no mix, so there is nothing to balance. Wrote: " +
            r.writes.map { "ch${it.second.channel}" }.distinct())
    }

    @Test fun `a muted channel is left alone, and is not pulled down`() {
        val e = StageEngine(rig, EngineSettings(mode = BalanceMode.KEEP))
        val r = Run(e)
        val band = silence().also {
            it[0] = -18f; it[1] = -20f; it[3] = -22f
            it[8] = -23f; it[11] = -17f
        }
        r.start { band }
        r.run(90.0) { band }
        e.adoptBalance(r.t)
        r.writes.clear()

        e.setChannelMuted(1, true)
        assertTrue(!e.stageMuted, "the rest of the band is still playing")
        r.run(300.0) { band }

        assertTrue(r.writes.none { it.second.channel == 1 },
            "a channel the operator has switched off is theirs: the " +
            "engine has nothing to correct and moving it would only " +
            "mean a jump when they switch it back on")
        assertTrue(e.decisions.none { it.kind == "mute" && it.channel == 1 },
            "and it certainly must not be 'muted' a second time by us")
    }

    @Test fun `unmuting listens again before touching it`() {
        val e = StageEngine(rig, EngineSettings(mode = BalanceMode.KEEP))
        val r = Run(e)
        val band = silence().also {
            it[0] = -18f; it[1] = -20f; it[3] = -22f; it[11] = -17f
        }
        r.start { band }
        r.run(60.0) { band }
        e.setChannelMuted(1, true)
        r.run(120.0) { band }
        assertTrue(e.setChannelMuted(1, false), "it comes back")
        assertEquals(0f, e.state[1]!!.heardSec,
            "it has to be listened to again — the loudness average from " +
            "before the mute describes a channel that has not been in " +
            "the mix for two minutes")
    }

    // ==================================================================
    // 5. a lost packet must not cost a channel the night
    // ==================================================================
    @Test fun `a channel that missed the takeover can still join`() {
        val e = StageEngine(rig, EngineSettings(mode = BalanceMode.KEEP))
        val r = Run(e)
        val band = silence().also {
            it[0] = -18f; it[3] = -22f; it[8] = -23f; it[11] = -17f
        }
        // ch11 is the bass on this rig, and its reply was one of the
        // five lost on the night — twice, on two consecutive takeovers
        r.run(5.0) { band }
        e.takeover((0 until 16).filter { it != 11 }
            .associateWith { -10f }, r.t)
        assertTrue(11 in e.unmanagedChannels(),
            "with no fader position there is no authority over it")
        r.run(60.0) { band }

        assertTrue(e.adoptLateChannel(11, -9.5f, r.t),
            "the reply finally arrived, and being unmanaged is a state " +
            "a channel must be able to leave")
        assertTrue(11 !in e.unmanagedChannels())
        assertTrue(e.decisions.any { it.kind == "joined" && it.channel == 11 },
            "and it says so, because three hours of a silently unmixed " +
            "bass is what the alternative looked like")
        assertTrue(!e.adoptLateChannel(11, -9.5f, r.t),
            "a channel already being mixed is not re-taken-over by a " +
            "routine re-read of its fader")
    }

    // ==================================================================
    // 6. pressing KEEP must always teach it something
    // ==================================================================
    @Test fun `KEEP is learned from even when nothing was recognised`() {
        // Both presses on the night logged "learned from 0 balances so
        // far", because learning was keyed on the recogniser and the
        // recogniser had nothing to say. Pressing that button is the
        // clearest statement of intent in the application.
        val e = StageEngine(rig, EngineSettings(mode = BalanceMode.KEEP))
        val r = Run(e)
        val rnd = java.util.Random(7)
        val walk = FloatArray(16)
        fun band(t: Double) = silence().also {
            it[0] = -18f; it[1] = -21f; it[3] = -22f
            it[8] = -19f; it[11] = -17f
            for (k in intArrayOf(0, 1, 3, 8, 11)) {
                walk[k] += -0.05f * walk[k] + rnd.nextGaussian().toFloat() * 0.8f
                it[k] += walk[k]
            }
        }
        for (ch in intArrayOf(0, 1, 3, 8, 11))
            e.setChannelName(ch, "DESK NAME $ch")
        r.start { band(it) }
        r.run(90.0) { band(it) }

        assertTrue(e.recognised.values.none {
            it.instrument != Instrument.UNKNOWN &&
                it.confidence >= 0.45f
        }, "nothing has been named — this is the night's situation")

        e.adoptBalance(r.t)
        assertTrue(e.learned.kept >= 1,
            "the operator has stated the answer; it must be written down")
        assertTrue(e.decisions.any { it.kind == "learned" },
            "and reported: " + e.decisions.map { it.kind }.distinct())
        println("learned by name: " + e.learned.summary())
    }

    // ==================================================================
    // 7. a rail is not a place
    // ==================================================================
    @Test fun `a placement that runs off the end of the scale is refused`() {
        val lb = LearnedBalance()
        // a balance that asks for something far below what any fader
        // move is allowed to do
        repeat(2) {
            lb.learn(mapOf(
                LearnedBalance.keyOf("kick") to -20f,
                LearnedBalance.keyOf("flute") to -60f))
        }
        assertTrue(lb.heightOf(LearnedBalance.keyOf("flute"))!! <
            lb.heightOf(LearnedBalance.keyOf("kick"))!! - 30f,
            "the learned shape really does ask for a huge gap")

        val e = StageEngine(rig, EngineSettings(mode = BalanceMode.KEEP))
        val r = Run(e)
        val band = silence().also {
            it[0] = -18f; it[3] = -22f; it[8] = -23f; it[11] = -17f
        }
        r.start { band }
        r.run(60.0) { band }
        e.adoptBalance(r.t)

        // a channel arrives into that balance
        val late = silence().also {
            it[0] = -18f; it[3] = -22f; it[8] = -23f; it[11] = -17f
            it[14] = -30f
        }
        r.run(180.0) { late }

        val placed = e.decisions.filter { it.kind == "placed" }
        for (p in placed)
            assertTrue(abs(p.deltaDb) < 11.9f,
                "the bottom of the authority range is a limit, not a " +
                "judgement — nothing may be 'placed' there: ${p.reason}")
    }

    @Test fun `one channel is not placed over and over`() {
        val e = StageEngine(rig, EngineSettings(mode = BalanceMode.KEEP))
        val r = Run(e)
        val beat = 0.5
        fun band(t: Double, extra: Boolean) = silence().also {
            it[0] = hit(t, beat * 2, 0.0, -18f, 0.18)
            it[3] = -22f
            it[8] = -20f
            it[11] = -17f
            if (extra) it[14] = -26f
        }
        r.start { band(it, false) }
        r.run(60.0) { band(it, false) }
        e.adoptBalance(r.t)
        // in and out, in and out — nine times on the night for the kick
        repeat(9) {
            r.run(60.0) { band(it, true) }
            r.run(60.0) { band(it, false) }
        }
        val n = e.decisions.count { it.kind == "placed" && it.channel == 14 }
        assertTrue(e.decisions.any { it.kind == "leave" && it.channel == 14 },
            "and when it stops, it says so rather than going quiet: " +
            e.decisions.filter { it.channel == 14 }.map { it.kind })
        assertTrue(n <= MAX_PLACEMENTS,
            "a channel that keeps being lost and re-found is a channel " +
            "the audience hears being re-found: $n placements")
    }

    // ==================================================================
    // 8. the ride must not chase the band playing
    // ==================================================================
    private fun rideCount(swingDb: Float, seconds: Double,
                          gainStepAt: Double = -1.0): Pair<Int, Float> {
        val e = StageEngine(rig, EngineSettings(mode = BalanceMode.KEEP))
        val r = Run(e)
        var step = 0f
        fun band(t: Double) = silence().also {
            it[0] = -18f; it[3] = -22f; it[8] = -20f; it[11] = -17f
            // the guitar amp: loud for a chorus, quiet for a verse, on
            // a forty-second cycle — which is a band playing, not a
            // fault, and is exactly what was chased all night
            it[4] = -21f + swingDb *
                kotlin.math.sin(2 * Math.PI * t / 40.0).toFloat() + step
        }
        r.start { band(it) }
        r.run(60.0) { band(it) }
        e.adoptBalance(r.t)
        if (gainStepAt > 0) {
            r.run(gainStepAt) { band(it) }
            step = -8f                      // somebody turned the amp down
        }
        r.writes.clear()
        r.run(seconds) { band(it) }
        // Counted from the WRITES, not from `decisions` — that is a
        // sixty-entry ring and a half-hour scenario laps it many times
        // over, which quietly turned this test into a no-op.
        val rides = r.writes.count { it.second.channel == 4 }
        var travel = 0f; var prev = 0f; var first = true
        for ((_, w) in r.writes) {
            if (w.channel != 4) continue
            if (!first) travel += abs(w.levelDb - prev)
            prev = w.levelDb; first = false
        }
        return rides to travel
    }

    @Test fun `a verse and a chorus are not a fault to be corrected`() {
        // 120 corrections on one guitar in three hours, 340 dB of fader
        // commanded, up three and down three on a forty-second cycle.
        // Every one was arithmetically right; the sum of them is the
        // restlessness KEEP exists to end.
        val (rides, travel) = rideCount(swingDb = 3f, seconds = 1800.0)
        println("half an hour of ±3 dB playing: $rides fader moves, " +
            "%.1f dB of fader".format(travel))
        assertTrue(rides <= 8,
            "the band getting louder for a chorus is the band's " +
            "business: $rides fader moves in half an hour")
        assertTrue(travel < 30f,
            "and the fader should barely move: %.1f dB".format(travel))
    }

    @Test fun `but a preamp that really moved is still caught`() {
        // The other half. A level that changes and STAYS changed is
        // what the ride is for, and it must still answer for it —
        // otherwise this is just a switch turned off.
        val (rides, _) = rideCount(swingDb = 1f, seconds = 900.0,
            gainStepAt = 120.0)
        println("after somebody moved the amp: $rides fader moves")
        assertTrue(rides >= 1,
            "a source that has genuinely moved and stayed moved is " +
            "exactly what this is for: $rides corrections")
    }
}
