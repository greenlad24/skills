package com.stagemix.engine

import java.io.File
import kotlin.math.abs
import kotlin.random.Random
import kotlin.test.Test
import kotlin.test.assertTrue

/**
 * Chaos / open-stage quality harness. Simulates the venue's randomness
 * and measures mix QUALITY, not just crashes:
 *  - travel: total |fader step| per channel (dB) - audible wandering
 *    (flag > 40 dB / 10 min)
 *  - direction reversals per channel per minute - pumping (flag > 4/min)
 *  - time-to-sensible-balance after each lineup event
 *  - hard invariants every tick: offset in [-12,+6], fader <= +2,
 *    total concurrent boost <= budget (6 dB)
 */
class ChaosTest {

    companion object {
        private val REPORT = File("/tmp/chaos-stagemix/chaos-report.txt")
        fun rep(s: String) {
            println(s)
            REPORT.appendText(s + "\n")
        }
        val NAMES = defaultRigProfile().associate { it.index to it.name }
    }

    private fun silence() = FloatArray(16) { -80f }

    /** Instrumented simulation: 20 Hz meters, 1 Hz ticks, metrics. */
    private class Sim(
        val e: StageEngine = StageEngine(defaultRigProfile()),
        val baseline: Float = -10f,
    ) {
        var t = 0.0
        var cur = FloatArray(16) { -80f }
        val lastW = HashMap<Int, Float>()
        val lastDir = HashMap<Int, Int>()
        val travel = HashMap<Int, Double>()
        val revs = HashMap<Int, Int>()
        val nWrites = HashMap<Int, Int>()
        val viol = LinkedHashMap<String, Int>()

        fun takeover() = e.takeover((0 until 16).associateWith { baseline }, t)

        fun resetMetrics() {
            travel.clear(); revs.clear(); nWrites.clear(); lastDir.clear()
        }

        fun feed(levels: FloatArray, sec: Double,
                 onTick: ((Double) -> Unit)? = null) =
            feedDyn({ levels }, sec, onTick)

        fun feedDyn(provider: (Double) -> FloatArray, sec: Double,
                    onTick: ((Double) -> Unit)? = null) {
            val end = t + sec
            var nextTick = kotlin.math.floor(t) + 1.0
            while (t < end) {
                cur = provider(t)
                e.onMeters(cur, t)
                if (t >= nextTick) {
                    for (w in e.tick(t)) {
                        val prev = lastW[w.channel] ?: baseline
                        val d = w.levelDb - prev
                        travel.merge(w.channel, abs(d).toDouble(), Double::plus)
                        nWrites.merge(w.channel, 1, Int::plus)
                        if (d != 0f) {
                            val dir = if (d > 0) 1 else -1
                            val pd = lastDir[w.channel] ?: 0
                            if (pd != 0 && dir != pd)
                                revs.merge(w.channel, 1, Int::plus)
                            lastDir[w.channel] = dir
                        }
                        lastW[w.channel] = w.levelDb
                        if (w.levelDb > 2.001f)
                            viol.merge("HARD: fader above +2 cap on ch%02d"
                                .format(w.channel + 1), 1, Int::plus)
                    }
                    var boost = 0.0
                    for (ch in 0 until 16) {
                        val o = e.offsetDb(ch)
                        if (o < -12.001f || o > 6.001f)
                            viol.merge("HARD: offset outside [-12,+6] on " +
                                "ch%02d".format(ch + 1), 1, Int::plus)
                        if (o > 0f) boost += o
                    }
                    if (boost > e.settings.mixBoostBudgetDb + 0.101)
                        viol.merge("HARD: boost budget breached", 1, Int::plus)
                    onTick?.invoke(t)
                    nextTick += 1.0
                }
                t += 0.05
            }
        }

        fun fader(ch: Int) = baseline + e.offsetDb(ch)
        fun contrib(ch: Int) = cur[ch] + fader(ch)
        fun accomp(chs: List<Int>) =
            chs.map { contrib(it).toDouble() }.average()

        fun metricsSummary(durMin: Double): String = buildString {
            for (ch in 0 until 16) {
                val tr = travel[ch] ?: continue
                if (tr < 0.3) continue
                val rv = revs[ch] ?: 0
                val per10 = tr / durMin * 10
                val rpm = rv / durMin
                val flags = buildString {
                    if (per10 > 40) append(" [WANDERING]")
                    if (rpm > 4) append(" [PUMPING]")
                }
                append(("  ch%02d %-15s travel %6.1f dB (%6.1f dB/10min)  " +
                    "writes %4d  reversals %3d (%4.1f/min)%s\n").format(
                        ch + 1, NAMES[ch] ?: "?", tr, per10,
                        nWrites[ch] ?: 0, rv, rpm, flags))
            }
            if (viol.isNotEmpty())
                for ((v, n) in viol) append("  VIOLATION x$n: $v\n")
        }
    }

    // ------------------------------------------------------------------
    // 1. Musician swap mid-song: acoustic guitar (ch 8 idx 7) goes
    //    silent; congas plug into the SAME jack 10 s later, 6 dB hotter.
    // ------------------------------------------------------------------
    @Test fun `S1 musician swap on the same channel`() {
        val s = Sim()
        val duo = silence().also { it[7] = -18f; it[8] = -24f }
        s.feed(duo, 5.0); s.takeover()
        s.feed(duo, 90.0)                       // settled duo mix
        val gapBefore = s.contrib(8) - s.contrib(7)
        s.feed(duo.copyOf().also { it[7] = -80f }, 10.0)   // guitar unplugs
        val congas = duo.copyOf().also { it[7] = -12f }    // congas, hot
        s.resetMetrics()
        var backOnTop = -1.0
        var streak = 0
        val start = s.t
        s.feed(congas, 180.0) { tt ->
            if (s.contrib(8) > s.contrib(7)) streak++ else streak = 0
            if (backOnTop < 0 && streak >= 5) backOnTop = tt - start
        }
        val gapAfter = s.contrib(8) - s.contrib(7)
        rep("== S1 musician swap (guitar -> congas on idx 7, -18 -> -12) ==")
        rep("  vocal-over-ch7 gap: settled duo %.1f dB; 180 s after swap %.1f dB"
            .format(gapBefore, gapAfter))
        rep("  vocal back on top after swap: " +
            (if (backOnTop < 0) "NEVER in 180 s" else "%.0f s".format(backOnTop)))
        rep("  ch08 offset %+.1f, ch09 offset %+.1f"
            .format(s.e.offsetDb(7), s.e.offsetDb(8)))
        rep(s.metricsSummary(3.0))
        assertTrue(s.viol.isEmpty(), s.viol.keys.toString())
    }

    // ------------------------------------------------------------------
    // 1b. Congas on "Congo / Vox 3" (idx 10, BACKING_VOCAL) play through
    //     the between-song pause; the singer stops for 25 s then returns.
    // ------------------------------------------------------------------
    @Test fun `S1b congas on the vox3 channel capture lead-follow`() {
        val s = Sim()
        val band = silence().also {
            it[0] = -20f; it[11] = -21f          // kick, bass
            it[5] = -24f; it[6] = -24f           // piano
            it[8] = -22f                          // singer
            it[10] = -28f                         // congas on Congo/Vox3
        }
        s.feed(band, 5.0); s.takeover()
        s.feed(band, 60.0)
        val leadDuringSong = s.e.leadVocal
        val pause = band.copyOf().also { it[8] = -80f }   // song ends,
        s.feed(pause, 25.0)                               // congas noodle on
        val leadDuringPause = s.e.leadVocal
        val duckDuringPause = (0 until 16).filter {
            s.e.targetDb(it) < s.e.offsetDb(it) - 0.5f }
        s.feed(band, 90.0)                                // singer returns
        val leadAfterReturn = s.e.leadVocal
        rep("== S1b congas hijack lead-follow via ch11 'Congo / Vox 3' ==")
        rep("  lead during song: ch${leadDuringSong?.plus(1)}   " +
            "during 25 s pause: ch${leadDuringPause?.plus(1)}   " +
            "90 s after singer returns: ch${leadAfterReturn?.plus(1)}")
        rep("  singer contrib %.1f vs congas contrib %.1f (congas offset %+.1f)"
            .format(s.contrib(8), s.contrib(10), s.e.offsetDb(10)))
        rep("  channels being pulled down during the pause: " +
            duckDuringPause.map { it + 1 })
        rep("")
        assertTrue(s.viol.isEmpty(), s.viol.keys.toString())
    }

    // ------------------------------------------------------------------
    // 2. Singer rotation: 3 vocal channels trade the lead every 60-90 s
    //    for 20 minutes over a steady band bed.
    // ------------------------------------------------------------------
    @Test fun `S2 singer rotation for 20 minutes`() {
        val s = Sim()
        val rnd = Random(7)
        val singers = listOf(8, 9, 10)
        fun bed() = silence().also {
            it[0] = -20f; it[11] = -21f; it[5] = -24f; it[6] = -24f }
        var lvl = bed().also { it[8] = -22f }
        s.feed(lvl, 5.0); s.takeover()
        s.feed(lvl, 40.0)
        var lastLead = s.e.leadVocal
        var leadChanges = 0
        val followDelays = ArrayList<Double>()
        var neverFollowed = 0
        var elapsed = 0.0
        var i = 0
        while (elapsed < 1200.0) {
            val who = singers[i % 3]
            val dur = 60.0 + rnd.nextDouble() * 30.0
            lvl = bed().also { it[who] = -22f }
            val rotStart = s.t
            var followedAt = -1.0
            s.feed(lvl, dur) { tt ->
                if (s.e.leadVocal != lastLead) {
                    leadChanges++; lastLead = s.e.leadVocal
                }
                if (followedAt < 0 && s.e.leadVocal == who)
                    followedAt = tt - rotStart
            }
            if (followedAt < 0) neverFollowed++ else followDelays.add(followedAt)
            elapsed += dur; i++
        }
        rep("== S2 singer rotation, $i rotations over %.0f min ==".format(elapsed / 60))
        rep("  lead switches observed: $leadChanges (rotations: $i) " +
            (if (leadChanges > i + 2) "[FLAPPING]" else ""))
        rep("  follow delay: avg %.1f s, max %.1f s; rotations never followed: %d"
            .format(followDelays.average(), followDelays.maxOrNull() ?: -1.0,
                neverFollowed))
        rep("  end offsets vox: ch9 %+.1f ch10 %+.1f ch11 %+.1f"
            .format(s.e.offsetDb(8), s.e.offsetDb(9), s.e.offsetDb(10)))
        rep(s.metricsSummary(elapsed / 60))
        assertTrue(s.viol.isEmpty(), s.viol.keys.toString())
    }

    // ------------------------------------------------------------------
    // 3. "Everyone plugs in at once": silence -> 8 channels appear at
    //    wildly wrong relative levels.
    // ------------------------------------------------------------------
    @Test fun `S3 everyone plugs in at once at wrong gains`() {
        val s = Sim()
        s.feed(silence(), 5.0); s.takeover()
        s.feed(silence(), 25.0)                    // learning window passes
        val all = silence().also {
            it[0] = -10f    // kick screaming
            it[1] = -12f    // snare hot
            it[11] = -35f   // bass whisper
            it[5] = -15f; it[6] = -15f  // piano hot
            it[4] = -8f     // guitar amp roaring
            it[7] = -30f    // guitar DI quiet
            it[8] = -38f    // vocal buried
        }
        s.resetMetrics()
        val start = s.t
        var vocalOnTopAt = -1.0
        var streak = 0
        val accompCh = listOf(0, 1, 11, 5, 6, 4, 7)
        s.feed(all, 300.0) { tt ->
            if (s.contrib(8) > s.accomp(accompCh)) streak++ else streak = 0
            if (vocalOnTopAt < 0 && streak >= 5) vocalOnTopAt = tt - start
        }
        rep("== S3 everyone plugs in at once (8 ch, gains 30 dB apart) ==")
        rep("  vocal above accompaniment mean: " +
            (if (vocalOnTopAt < 0) "NEVER in 300 s" else
                "after %.0f s".format(vocalOnTopAt)))
        rep("  final vocal contrib %.1f vs accomp mean %.1f (gap %+.1f)"
            .format(s.contrib(8), s.accomp(accompCh),
                s.contrib(8) - s.accomp(accompCh)))
        rep(("  intra-foundation: kick contrib %.1f vs bass contrib %.1f " +
            "(gap %.1f dB)").format(
                s.contrib(0), s.contrib(11), s.contrib(0) - s.contrib(11)))
        rep("  guitar amp contrib %.1f (offset %+.1f, floor -12)"
            .format(s.contrib(4), s.e.offsetDb(4)))
        rep(s.metricsSummary(5.0))
        assertTrue(s.viol.isEmpty(), s.viol.keys.toString())
    }

    // ------------------------------------------------------------------
    // 4. Three minutes of dead air between acts, then a new act starts.
    // ------------------------------------------------------------------
    @Test fun `S4 dead air between acts then a new act`() {
        val s = Sim()
        val act1 = silence().also {
            it[0] = -20f; it[1] = -23f; it[11] = -21f
            it[5] = -24f; it[6] = -24f; it[4] = -23f; it[8] = -22f }
        s.feed(act1, 5.0); s.takeover()
        s.feed(act1, 120.0)
        s.feed(silence(), 180.0)                  // dead air
        val wakeOffsets = (0 until 16).associateWith { s.e.offsetDb(it) }
        val staleLead = s.e.leadVocal
        // act 2: piano + 2nd singer, nothing else
        val act2 = silence().also { it[5] = -22f; it[6] = -22f; it[9] = -24f }
        s.resetMetrics()
        val start = s.t
        var followed = -1.0
        var balanced = -1.0
        var streak = 0
        s.feedDyn({ act2 }, 240.0) { tt ->
            if (followed < 0 && s.e.leadVocal == 9) followed = tt - start
            if (s.contrib(9) > s.accomp(listOf(5, 6))) streak++ else streak = 0
            if (balanced < 0 && streak >= 5) balanced = tt - start
        }
        val staleWrites = s.nWrites.filterKeys { it !in setOf(5, 6, 9) }
        rep("== S4 3 min dead air, then piano + singer-2 act ==")
        rep("  state at wake: lead still ch${staleLead?.plus(1)}; offsets " +
            wakeOffsets.filterValues { abs(it) > 0.5f }
                .map { "ch%02d %+.1f".format(it.key + 1, it.value) })
        rep("  lead follows to ch10: " +
            (if (followed < 0) "NEVER in 240 s" else "%.0f s".format(followed)) +
            "; vocal above piano: " +
            (if (balanced < 0) "NEVER in 240 s" else "%.0f s".format(balanced)))
        rep("  writes to channels NOT in act 2 during act 2: " +
            staleWrites.map { "ch%02d x%d".format(it.key + 1, it.value) })
        rep(s.metricsSummary(4.0))
        assertTrue(s.viol.isEmpty(), s.viol.keys.toString())
    }

    // ------------------------------------------------------------------
    // 5. Flickering cable: a channel alternates active/silent every 3 s
    //    for a minute. Two variants: (a) hot guitar in a duo - measures
    //    the broadband-hold ratchet; (b) kick in a band - measures
    //    anchor flapping.
    // ------------------------------------------------------------------
    @Test fun `S5a flickering hot channel in a duo blocks all boosts`() {
        val s = Sim()
        val duo = silence().also { it[4] = -8f; it[8] = -20f }
        s.feed(duo, 5.0); s.takeover()
        s.feed(duo, 60.0)
        val voxBefore = s.e.offsetDb(8)
        s.resetMetrics()
        var boostBlockedTicks = 0; var ticks = 0
        // singer backs off the mic exactly as the cable starts flickering:
        // the vocal now NEEDS a lift while the flicker is running
        s.feedDyn({ tt ->
            val on = ((tt / 3.0).toInt() % 2) == 0
            silence().also { it[4] = if (on) -8f else -80f; it[8] = -30f }
        }, 60.0) { tt ->
            ticks++
            if (!s.e.boostsAllowed(tt)) boostBlockedTicks++
        }
        val voxAfterFlicker = s.e.offsetDb(8)
        // cable reseated, singer still quiet: lift should now happen
        val fixed = silence().also { it[4] = -8f; it[8] = -30f }
        val fixT = s.t
        var liftAt = -1.0
        s.feed(fixed, 120.0) { tt ->
            if (liftAt < 0 && s.e.offsetDb(8) > voxAfterFlicker + 1f)
                liftAt = tt - fixT
        }
        rep("== S5a flickering hot guitar (duo), 3 s on / 3 s off x 60 s ==")
        rep("  boosts blocked %d of %d ticks during flicker".format(
            boostBlockedTicks, ticks))
        rep(("  vocal offset: before %+.1f; after flicker minute %+.1f " +
            "(singer 10 dB quieter, no lift given); first lift %s after fix; " +
            "final %+.1f").format(voxBefore, voxAfterFlicker,
                if (liftAt < 0) "NEVER" else "%.0f s".format(liftAt),
                s.e.offsetDb(8)))
        rep(s.metricsSummary(1.0))
        rep("")
        assertTrue(s.viol.isEmpty(), s.viol.keys.toString())
    }

    // ------------------------------------------------------------------
    // 8. Boost-budget starvation: quiet instruments split the 6 dB
    //    boost budget with the buried lead vocal - index order, no
    //    vocal priority.
    // ------------------------------------------------------------------
    @Test fun `S8 quiet keys starve the buried vocal of boost budget`() {
        val s = Sim()
        val band = silence().also {
            it[0] = -14f                      // kick hot (anchor)
            it[5] = -30f; it[6] = -30f        // piano quiet, wants lift
            it[8] = -30f                      // lead vocal buried
        }
        s.feed(band, 5.0); s.takeover()
        s.feed(band, 240.0)
        val boostSum = (0 until 16).sumOf {
            maxOf(0f, s.e.offsetDb(it)).toDouble() }
        rep("== S8 boost budget split, no vocal priority ==")
        rep(("  offsets: pianoL %+.1f pianoR %+.1f vocal %+.1f " +
            "(vocal bound is +6, budget used %.1f of 6)").format(
                s.e.offsetDb(5), s.e.offsetDb(6), s.e.offsetDb(8), boostSum))
        rep(("  contribs: kick %.1f piano %.1f/%.1f vocal %.1f -> vocal vs " +
            "accomp mean gap %+.1f").format(
                s.contrib(0), s.contrib(5), s.contrib(6), s.contrib(8),
                s.contrib(8) - s.accomp(listOf(0, 5, 6))))
        rep("")
        assertTrue(s.viol.isEmpty(), s.viol.keys.toString())
    }

    @Test fun `S5b flickering kick in a band - oscillation check`() {
        val s = Sim()
        val band = silence().also {
            it[0] = -18f; it[5] = -24f; it[6] = -24f; it[8] = -22f }
        s.feed(band, 5.0); s.takeover()
        s.feed(band, 60.0)
        s.resetMetrics()
        var ensembleFlips = 0
        var lastDrums = s.e.hasDrums
        s.feedDyn({ tt ->
            val on = ((tt / 3.0).toInt() % 2) == 0
            silence().also {
                it[0] = if (on) -18f else -80f
                it[5] = -24f; it[6] = -24f; it[8] = -22f }
        }, 60.0) { _ ->
            if (s.e.hasDrums != lastDrums) { ensembleFlips++; lastDrums = s.e.hasDrums }
        }
        rep("== S5b flickering kick (band), 3 s on / 3 s off x 60 s ==")
        rep("  hasDrums flips: $ensembleFlips in 60 s " +
            "(each one logs 'ensemble' and opens the fast lane)")
        rep(s.metricsSummary(1.0))
        assertTrue(s.viol.isEmpty(), s.viol.keys.toString())
    }

    // ------------------------------------------------------------------
    // 6. Drummer soundchecking alone: hits at -6, gaps at -80, 5 min.
    // ------------------------------------------------------------------
    @Test fun `S6 drummer soundcheck with huge dynamics`() {
        val s = Sim()
        // establish takeover while drummer already hitting
        fun drums(tt: Double): FloatArray {
            val phase = ((tt * 20).toInt()) % 10       // 2-of-10 frames hit
            return silence().also {
                it[0] = if (phase < 2) -6f else -80f            // kick
                it[1] = if (phase in 5..6) -8f else -80f        // snare
                it[2] = if (phase < 2 || phase in 5..6) -14f else -80f
            }
        }
        s.feedDyn(::drums, 5.0); s.takeover()
        s.resetMetrics()
        var ensembleFlips = 0
        var lastDrums = s.e.hasDrums
        s.feedDyn(::drums, 300.0) { _ ->
            if (s.e.hasDrums != lastDrums) { ensembleFlips++; lastDrums = s.e.hasDrums }
        }
        val nonDrumWrites = s.nWrites.filterKeys { it !in setOf(0, 1, 2) }
        rep("== S6 drummer alone, -6 hits / -80 gaps, 5 min ==")
        rep("  hasDrums flips: $ensembleFlips; " +
            "writes to non-drum channels: $nonDrumWrites")
        rep("  drum offsets end: kick %+.1f snare %+.1f OH %+.1f".format(
            s.e.offsetDb(0), s.e.offsetDb(1), s.e.offsetDb(2)))
        rep(s.metricsSummary(5.0))
        assertTrue(s.viol.isEmpty(), s.viol.keys.toString())
    }

    // ------------------------------------------------------------------
    // 7. A 3-hour night compressed: 12 random acts back-to-back.
    // ------------------------------------------------------------------
    @Test fun `S7 twelve random acts back to back`() {
        val s = Sim()
        val rnd = Random(2026)
        val instPool = listOf(0, 1, 2, 3, 4, 5, 6, 7, 11, 12, 13, 14, 15)
        s.feed(silence(), 5.0); s.takeover()
        s.feed(silence(), 25.0)
        var actsBalanced = 0
        val failures = ArrayList<String>()
        for (act in 1..12) {
            val vox = listOf(8, 9, 10)[rnd.nextInt(3)]
            val nInst = 2 + rnd.nextInt(4)
            val insts = instPool.shuffled(rnd).take(nInst)
            val lvl = silence()
            lvl[vox] = -30f + rnd.nextInt(13)           // -30..-18
            for (c in insts) lvl[c] = -28f + rnd.nextInt(15)  // -28..-14
            val start = s.t
            var onTopAt = -1.0; var streak = 0
            var onTopShare90 = 0; var post90 = 0
            s.feed(lvl, 240.0) { tt ->
                val top = s.contrib(vox) > s.accomp(insts)
                if (top) streak++ else streak = 0
                if (onTopAt < 0 && streak >= 5) onTopAt = tt - start
                if (tt - start >= 90.0) { post90++; if (top) onTopShare90++ }
            }
            val pct = if (post90 > 0) 100 * onTopShare90 / post90 else 0
            val srcGap = lvl[vox] - insts.map { lvl[it].toDouble() }.average()
            if (onTopAt in 0.0..90.0 && pct >= 95) actsBalanced++
            else failures.add(
                "act %02d vox ch%02d (src gap %+.1f dB, %d insts): on-top at %s, on-top after 90 s %d%%"
                    .format(act, vox + 1, srcGap, nInst,
                        if (onTopAt < 0) "NEVER" else "%.0f s".format(onTopAt), pct))
            s.feed(silence(), 20.0)                     // changeover
        }
        rep("== S7 12 random acts x 4 min (seed 2026) ==")
        rep("  acts with vocal on top within 90 s and holding: $actsBalanced / 12")
        for (f in failures) rep("  MISS: $f")
        rep(s.metricsSummary(52.0))
        assertTrue(s.viol.isEmpty(), s.viol.keys.toString())
    }
}
