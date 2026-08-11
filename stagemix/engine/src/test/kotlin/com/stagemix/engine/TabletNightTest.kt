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

    @Test fun `coming back from a mute is not an instrument arriving`() {
        // The operator mutes the band whenever the music stops. If
        // un-muting reads as sixteen instruments arriving at once, the
        // mix re-places itself from scratch between every song — which
        // is the single thing they asked most plainly for it not to do.
        val e = StageEngine(rig, EngineSettings(mode = BalanceMode.KEEP))
        val r = Run(e)
        val band = silence().also {
            it[0] = -18f; it[1] = -20f; it[3] = -22f
            it[8] = -20f; it[11] = -17f
        }
        r.start { band }
        r.run(90.0) { band }
        e.adoptBalance(r.t)
        val plans = (0 until 16).associateWith { e.state[it]!!.planContrib }

        // the song ends: everything muted, a minute of nothing, back on
        for (ch in 0 until 16) e.setChannelMuted(ch, true)
        r.run(120.0) { band }
        for (ch in 0 until 16) e.setChannelMuted(ch, false)
        r.writes.clear()
        val before = e.decisions.count { it.kind == "arrive" }
        r.run(120.0) { band }

        assertEquals(before, e.decisions.count { it.kind == "arrive" },
            "nobody arrived — they were muted and now they are not")
        for (ch in intArrayOf(0, 1, 3, 8, 11))
            assertEquals(plans[ch], e.state[ch]!!.planContrib,
                "ch$ch must keep the place it had before the break")
        assertTrue(r.writes.isEmpty(),
            "and the band comes back to the faders they left. Moved: " +
            r.writes.map { "ch${it.second.channel}" }.distinct())
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

    // ==================================================================
    // 9. the second real night: an arrival storm, and a kick called congas
    // ==================================================================
    @Test fun `a muted channel cannot arrive, over and over, all night`() {
        // 281,873 arrivals in one night — nine a second for eight hours,
        // 99.3 % of every decision the engine made, 48 MB of log, and
        // the whole 400,000-line budget spent before the night ended.
        //
        // Making `active` mean "gate open AND not muted" turned
        // `!active && gateOpen` from a one-frame edge into a permanent
        // state, because the meters are pre-mute: a muted channel with a
        // player behind it holds the gate open forever.
        val e = StageEngine(rig, EngineSettings(mode = BalanceMode.KEEP))
        val r = Run(e)
        val band = silence().also {
            it[0] = -18f; it[1] = -20f; it[3] = -22f
            it[8] = -20f; it[11] = -17f
        }
        r.start { band }
        r.run(60.0) { band }
        e.adoptBalance(r.t)

        // the operator mutes half the band — and the players keep
        // playing, which is exactly what the pre-fader meters report
        for (ch in intArrayOf(0, 1, 3)) e.setChannelMuted(ch, true)
        val before = e.decisions.count { it.kind == "arrive" }
        r.run(600.0) { band }
        val arrivals = e.decisions.count { it.kind == "arrive" } - before

        assertTrue(arrivals == 0,
            "a channel that is muted is not arriving — it is muted. " +
            "Fired $arrivals times in ten minutes")
    }

    @Test fun `one arrival cannot repeat on the very next frame`() {
        // Belt to the braces above: whatever the reason a channel looks
        // like it is arriving, answering "has it been away a while?"
        // from a timestamp the arrival itself just set makes a storm
        // structurally impossible rather than merely fixed this once.
        val e = StageEngine(rig, EngineSettings(mode = BalanceMode.KEEP))
        val r = Run(e)
        val band = silence().also {
            it[0] = -18f; it[3] = -22f; it[8] = -20f; it[11] = -17f
        }
        r.start { band }
        r.run(60.0) { band }
        e.adoptBalance(r.t)
        // a genuine arrival: silent, then playing
        val withHarp = band.copyOf().also { it[15] = -24f }
        r.run(300.0) { withHarp }
        val n = e.decisions.count { it.kind == "arrive" && it.channel == 15 }
        assertTrue(n in 1..2,
            "an instrument coming in is one arrival, not a stream: $n")
    }

    @Test fun `a kick is not a conga, and neither is a strummed guitar`() {
        // Both were, on the second night. A kick is low, struck, over
        // before the next one, and lands with the kit — every test the
        // hand-drum score applied, passed perfectly — so the kick was
        // declared congas and taken out of FOUNDATION, the one channel
        // the whole pyramid is measured from.
        val ens = Ensemble(6)
        val id = InstrumentId()
        val beat = 0.5
        var t = 0.0
        val lv = FloatArray(6)
        val act = BooleanArray(6)
        while (t < 240.0) {
            lv[0] = hit(t, beat * 2, 0.0, -18f, 0.18)   // kick
            lv[1] = hit(t, beat * 2, beat, -20f, 0.15)  // snare
            lv[2] = hit(t, beat, 0.0, -24f, 0.22)       // congas: struck
            // a strummed chord RINGS — that is the whole difference
            lv[3] = hit(t, beat, 0.0, -22f, 0.70)
            lv[4] = -100f; lv[5] = -100f
            for (k in 0 until 6) act[k] = lv[k] > -90f
            ens.onFrame(lv, act, 0.05f)
            // the envelope half — WITHOUT this `recognise` has no
            // active seconds on the channel and declines to answer,
            // which made the first version of this test pass on a null
            for (k in 0 until 6) id.onLevel(k, lv[k], 0.05f, act[k])
            t += 0.05
        }
        // spectra: a kick is all underneath; a conga has its body around
        // 200 Hz and nothing below; a guitar carries a line
        fun feed(ch: Int, bins: FloatArray) = repeat(120) { id.onRta(ch, bins, true) }
        fun band(lo: Int, hi: Int, peak: Float) = FloatArray(100) { i ->
            if (i in lo..hi) peak else -70f }
        // The RTA is 10 bins per octave from 20 Hz, so bin n is
        // 20 * 2^(n/10) Hz. Getting this wrong is how the first draft
        // of this test built a "conga" that lived at 53-160 Hz — which
        // is a kick drum, and the engine was right to say so.
        feed(0, band(0, 14, -12f))          // kick:   20-53 Hz
        feed(2, band(30, 54, -12f))         // conga:  160-1.2k, no sub
        feed(3, band(22, 62, -12f))         // guitar: 90-3.6k
        for (ch in intArrayOf(0, 2, 3)) {
            val rd = id.recognise(ch, ens)
            println("ch$ch -> ${rd?.instrument} conf %.2f  ${rd?.why}"
                .format(rd?.confidence ?: 0f))
        }
        val kick = id.recognise(0, ens)
        val conga = id.recognise(2, ens)
        val gtr = id.recognise(3, ens)
        // A null verdict would satisfy every assertion below without
        // the scoring ever running. Say so out loud.
        for ((n, rd) in listOf("kick" to kick, "conga" to conga,
                               "guitar" to gtr))
            assertTrue(rd != null, "$n was never actually judged")
        assertEquals(Instrument.KICK, kick!!.instrument,
            "all underneath and struck is a kick: ${kick.why}")
        assertTrue(conga!!.instrument != Instrument.KICK,
            "and a drum with its body at 200 Hz and nothing below is " +
            "not a kick: ${conga.instrument} (${conga.why})")
        // The guitar may still be misread — what must not happen is the
        // engine ACTING on a misreading. Below the recognise threshold
        // it keeps its opinion to itself, which is the design.
        val acts = gtr!!.instrument == Instrument.HAND_DRUM &&
            gtr.confidence >= IdSettings().recogniseConfidence
        assertTrue(!acts,
            "a ringing chord must not be re-roled to percussion: " +
            "${gtr.instrument} at %.2f".format(gtr.confidence))
    }

    @Test fun `an approved balance is not reclassified out from under you`() {
        // The kick was re-roled to percussion at 21:59 on a balance
        // adopted at 21:45. Every other channel's target is measured
        // from the foundation, so re-roling it moves the whole mix —
        // which is just a slower way of moving the faders the operator
        // asked us to leave alone.
        val e = StageEngine(rig, EngineSettings(mode = BalanceMode.KEEP))
        val kick = rig.first { it.role == Role.FOUNDATION }.index
        val r = Run(e)
        val band = silence().also {
            it[kick] = -18f; it[8] = -20f; it[11] = -17f; it[1] = -21f
        }
        r.start { band }
        r.run(60.0) { band }
        e.adoptBalance(r.t)
        r.run(900.0) { band }
        assertEquals(Role.FOUNDATION, e.state[kick]!!.role,
            "the foundation the mix is measured from does not get " +
            "reclassified after the operator has approved that mix")
    }

    // ==================================================================
    // 10. the parts of the rig that are physically fixed
    // ==================================================================
    @Test fun `channels one and two are the kick and snare, and stay that way`() {
        // "The first and second channels will always be Kick and Snare
        // mics." Microphones taped to a drum kit are not a question the
        // listener gets to re-open every night — and it had already got
        // this wrong in the most expensive way available, moving the
        // kick out of FOUNDATION, which is what every other channel's
        // height is measured against.
        val e = StageEngine(rig, EngineSettings(mode = BalanceMode.KEEP))
        assertEquals(Role.FOUNDATION, e.state[0]!!.role)
        assertEquals(Role.PERCUSSION, e.state[1]!!.role)
        assertTrue(e.state[0]!!.roleLocked && e.state[1]!!.roleLocked,
            "both are locked before a single meter frame arrives")

        // A whole night of the band playing, with no balance adopted —
        // the window in which re-roling is otherwise cheapest.
        val r = Run(e)
        val beat = 0.5
        fun band(t: Double) = silence().also {
            it[0] = hit(t, beat * 2, 0.0, -18f, 0.18)
            it[1] = hit(t, beat * 2, beat, -20f, 0.15)
            it[8] = -20f; it[11] = -17f
        }
        r.start { band(it) }
        r.run(1200.0) { band(it) }

        assertEquals(Role.FOUNDATION, e.state[0]!!.role,
            "the kick is a kick: " + e.decisions
                .filter { it.kind == "ident" && it.channel == 0 }
                .map { it.reason })
        assertEquals(Role.PERCUSSION, e.state[1]!!.role, "and the snare a snare")

        // The desk's own label does not get a vote either — on this rig
        // the console's names are a previous band's.
        e.setChannelName(0, "VOCAL CEN_50")
        assertEquals(Role.FOUNDATION, e.state[0]!!.role,
            "a leftover label on the console does not un-tape a mic " +
            "from a drum")

        // But the operator still can, by hand. It is their rig.
        assertTrue(e.setRole(0, Role.VOCAL))
        assertEquals(Role.VOCAL, e.state[0]!!.role,
            "locked against the listener, never against the person")
    }

    @Test fun `both bass DIs hold the low end, and split it between them`() {
        // "Bass DI and DI 2 are very important (both are the bass — in
        // the pyramid)", and neither channel ever moves.
        val e = StageEngine(rig, EngineSettings(mode = BalanceMode.KEEP))
        for (ch in intArrayOf(11, 13)) {
            assertEquals(Role.FOUNDATION, e.state[ch]!!.role, "ch$ch is low end")
            assertTrue(e.state[ch]!!.roleLocked, "ch$ch is fixed in place")
        }

        // Two DIs carrying the same line are one bass to the room, so
        // they share the bass side of the low end — while the kick,
        // which occupies a different moment and a different octave,
        // keeps its own. The three together must still sum to the one
        // low end the pyramid asked for, or the whole bottom of the mix
        // moves with the lineup.
        val r = Run(e)
        val beat = 0.5
        fun band(t: Double) = silence().also {
            it[0] = hit(t, beat * 2, 0.0, -18f, 0.18)
            it[1] = hit(t, beat * 2, beat, -20f, 0.15)
            it[11] = -22f; it[13] = -23f
            it[8] = -20f
        }
        r.start { band(it) }
        r.run(120.0) { band(it) }
        for (ch in intArrayOf(0, 11, 13))
            assertTrue(e.state[ch]!!.role == Role.FOUNDATION,
                "ch$ch stayed in the low end")
    }

    // ==================================================================
    // 11. tick() must not throw — it is the call the whole show runs on
    // ==================================================================
    @Test fun `a stereo pair going active before there is an anchor`() {
        // NullPointerException out of tick(). The target above this is
        // explicitly written to cope with there being no anchor yet —
        // "everyone is still auditioning" — and then the stereo-pair
        // branch force-unwrapped it anyway. An exception here kills the
        // one coroutine that receives meters, writes faders and keeps
        // the log, while the notification still says MIXING.
        val chans = listOf(
            ChannelConfig(5, "Vox B", Role.BACKING_VOCAL, pairWith = 6),
            ChannelConfig(6, "Piano R", Role.KEYS, pairWith = 5))
        val e = StageEngine(chans, EngineSettings(mode = BalanceMode.LEAD))
        val lv = FloatArray(16) { -128f }
        lv[5] = -30f                       // one half plays from the start
        var t = 0.0
        while (t < 2.0) { e.onMeters(lv, t); t += 0.05 }
        e.takeover(mapOf(5 to -5f, 6 to -5f), t)
        var next = t + 1.0
        val end = t + 60.0
        while (t < end) {
            if (t > 32.0) lv[6] = -30f     // the pair joins, still unheard
            e.onMeters(lv, t)
            if (t >= next) { e.tick(t); next += 1.0 }
            t += 0.05
        }
        // reaching here at all is the assertion
        assertTrue(true)
    }

    // ==================================================================
    // 12. asking for more must never give less
    // ==================================================================
    @Test fun `a chip moves last night's taste, it does not replace it`() {
        // The operator tapped "vocal_up" once, and the lead vocal taste
        // went from +3.0 dB to +1.0. Everything the app had learned
        // about this band's vocal over previous nights was thrown away
        // by the request for more of it.
        val e = StageEngine(rig, EngineSettings(mode = BalanceMode.KEEP))
        e.loadBias(mapOf(Role.VOCAL to 1.5f, Role.KEYS to -1.0f))
        assertEquals(1.5f, e.pyramidBias[Role.VOCAL],
            "the taste is carried forward")

        e.applyFeedback("vocal_up", 0.0)
        val after = e.pyramidBias[Role.VOCAL] ?: 0f
        assertTrue(after > 1.5f,
            "asking for more vocal must give more vocal, counted from " +
            "wherever it already was: 1.5 -> $after")

        e.applyFeedback("vocal_down", 1.0)
        assertTrue((e.pyramidBias[Role.VOCAL] ?: 0f) < after,
            "and down is down from there, not from zero")
        assertEquals(-1.0f, e.pyramidBias[Role.KEYS],
            "a chip for one role does not disturb another")

        // Taste is deliberately bounded to +/-3 dB. At the ceiling,
        // asking for more must hold — never fall back to a fresh +1.
        val hot = StageEngine(rig, EngineSettings(mode = BalanceMode.KEEP))
        hot.loadBias(mapOf(Role.VOCAL to 3.0f))
        hot.applyFeedback("vocal_up", 0.0)
        assertEquals(3.0f, hot.pyramidBias[Role.VOCAL],
            "at the ceiling it stays at the ceiling — this is the one " +
            "that took the operator's vocal from +3.0 to +1.0")
    }

    // ==================================================================
    // 13. between songs, nothing at all
    // ==================================================================
    private fun quietThenLoud(e: StageEngine, r: Run) {
        val beat = 0.5
        fun playing(t: Double) = silence().also {
            it[0] = hit(t, beat * 2, 0.0, -18f, 0.18)
            it[1] = hit(t, beat * 2, beat, -20f, 0.15)
            it[3] = -22f; it[8] = -20f; it[11] = -17f
        }
        r.start { playing(it) }
        r.run(90.0) { playing(it) }
        e.adoptBalance(r.t)
        // The song ends: the stage falls away together. Kept short on
        // purpose — `betweenSongs` contrasts what is playing NOW against
        // what was playing recently, so it is a state that decays. The
        // gap between two songs is what it is for.
        r.run(12.0) { silence() }
    }

    @Test fun `between songs the engine does nothing whatever the mode`() {
        // "In between songs I don't want the app to do rebalancing or
        // EQ/Compression." The gap was only guarded in KEEP, and only
        // once a balance had been adopted — so the mode that has not
        // settled yet, which is the one most inclined to move things,
        // was free to move them in the silence.
        for (mode in listOf(BalanceMode.KEEP, BalanceMode.LEAD)) {
            val e = StageEngine(rig, EngineSettings(mode = mode))
            val r = Run(e)
            quietThenLoud(e, r)
            assertTrue(e.betweenSongs, "$mode: the stage has gone quiet")
            r.writes.clear()
            r.run(20.0) { silence() }
            assertTrue(r.writes.isEmpty(),
                "$mode: nothing moves in the gap. Moved: " +
                r.writes.map { "ch${it.second.channel}" }.distinct())
            assertTrue(e.treatmentPass(r.t).isEmpty(),
                "$mode: and no EQ or compressor is set in the gap either")
        }
    }

    @Test fun `processing is set for a solo or an arrival, and nothing else`() {
        // The two reasons given: "Solo happening (Sax, guitar,
        // harmonica)" and "A new instrument has entered that was not
        // there before". A drifting spectrum is explicitly not one of
        // them — a chain that re-applies itself because a number moved
        // changes a performance nobody asked it to change.
        val e = StageEngine(rig, EngineSettings(mode = BalanceMode.KEEP))
        val r = Run(e)
        val beat = 0.5
        var extra = false
        fun band(t: Double) = silence().also {
            it[0] = hit(t, beat * 2, 0.0, -18f, 0.18)
            it[1] = hit(t, beat * 2, beat, -20f, 0.15)
            it[3] = -22f; it[8] = -20f; it[11] = -17f
            if (extra) it[14] = -24f          // a horn picks up mid-song
        }
        r.start { band(it) }
        r.run(120.0) { band(it) }
        e.adoptBalance(r.t)

        // Steady state: everyone playing, nobody soloing, nothing new.
        // Whatever the identifier thinks it has learned, this is not a
        // moment to be reaching for anybody's EQ.
        for (ch in 0 until 16)
            assertTrue(!e.wantsTreatment(ch, r.t),
                "ch$ch has no reason to be treated mid-song")

        // Something arrives.
        extra = true
        r.run(settings2(e).placeSec.toDouble() + 8.0) { band(it) }
        assertTrue(e.wantsTreatment(14, r.t),
            "an instrument that was not there before is a reason")
        assertTrue(!e.wantsTreatment(0, r.t),
            "and it is a reason for THAT channel, not for the kick")
    }

    private fun settings2(e: StageEngine) = e.settings

    // ==================================================================
    // 14. the band playing together is not sixteen channels drifting
    // ==================================================================
    @Test fun `a band lifting together moves nothing`() {
        // "If one channel changed, it is technique — correct it. If
        // several changed together, it is the music — leave it alone."
        // The ride error was absolute, so a chorus, a build or simply
        // three sets of a stage getting louder read as every ridable
        // channel drifting at once. And the ride cannot touch the
        // voices, the kick, the snare or the bass, so a band-wide rise
        // came out of the guitars, the piano and the horns ALONE — over
        // a night the mix drifts to drums, bass and voice with the
        // harmony instruments squeezed out.
        val e = StageEngine(rig, EngineSettings(mode = BalanceMode.KEEP))
        val r = Run(e)
        var lift = 0f
        // EVERYONE lifts — the drums and the voices too. That is what a
        // chorus is, and it is the distinction the common-mode term is
        // measuring: the first draft of this fixture raised only the
        // ridable channels, which is not a band digging in, it is four
        // channels drifting, and the engine was right to correct it.
        fun band(t: Double) = silence().also {
            it[0] = -18f + lift; it[1] = -21f + lift
            it[3] = -22f + lift; it[11] = -17f + lift
            it[4] = -20f + lift; it[5] = -23f + lift
            it[7] = -24f + lift; it[14] = -25f + lift
            it[8] = -19f + lift
        }
        r.start { band(it) }
        r.run(120.0) { band(it) }
        e.adoptBalance(r.t)
        r.writes.clear()

        // the whole band digs in for the last chorus, and stays there
        lift = 5f
        r.run(300.0) { band(it) }
        val moved = r.writes.map { it.second.channel }.distinct().sorted()
        assertTrue(moved.isEmpty(),
            "the band got louder together — that is the song, not a " +
            "fault. Moved: $moved")
    }

    @Test fun `but one player who changed alone is still corrected`() {
        // The other half: the common-mode term must not become a way of
        // never doing anything. A singer backing off the microphone is
        // one channel moving against the rest, and that is the job.
        val e = StageEngine(rig, EngineSettings(mode = BalanceMode.KEEP))
        val r = Run(e)
        var solo = 0f
        fun band(t: Double) = silence().also {
            it[0] = -18f; it[1] = -21f; it[3] = -22f; it[11] = -17f
            it[4] = -20f + solo          // guitar amp alone
            it[5] = -23f; it[7] = -24f; it[14] = -25f; it[8] = -19f
        }
        r.start { band(it) }
        r.run(120.0) { band(it) }
        e.adoptBalance(r.t)
        r.writes.clear()

        solo = -7f                        // his amp got quieter, alone
        r.run(300.0) { band(it) }
        assertTrue(r.writes.any { it.second.channel == 4 },
            "one channel out of step with the rest is exactly what the " +
            "ride is for: " + r.writes.map { it.second.channel }.distinct())
    }

    @Test fun `no chain is written while a howl is suspected`() {
        // The tone doctor is handed `boostsAllowed` and respects it;
        // the chain pass was handed nothing, so during a feedback veto
        // it could still write +2 dB at 3 kHz onto a vocal microphone
        // and up to +4 dB of compressor makeup.
        val e = StageEngine(rig, EngineSettings(mode = BalanceMode.KEEP))
        val r = Run(e)
        val band = silence().also {
            it[0] = -18f; it[3] = -22f; it[8] = -20f; it[11] = -17f
        }
        r.start { band }
        r.run(60.0) { band }
        e.watchdogVeto = true
        assertTrue(e.treatmentPass(r.t).isEmpty(),
            "nothing reaches upward while a howl is suspected")
    }
}
