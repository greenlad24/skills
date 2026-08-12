package com.stagemix.engine

import java.io.File
import kotlin.test.Test
import kotlin.test.assertTrue

/**
 * The log is the product.
 *
 * "I want the logs to be more detailed so next time I paste logs here
 * you will understand exactly what to fix." Everything here is a
 * question I could not answer from the last two nights' logs, turned
 * into an assertion that the file can answer it.
 *
 * The two real failures behind these tests: 48 MB of log with not one
 * fader write in it, so there was no way to tell how much of a night's
 * 651 dB of fader travel was the app and how much was the operator; and
 * no record at all of the flags — the gap detector, the stage mute —
 * that silence the entire engine, so "it did nothing for twenty
 * minutes" could not be told apart from "it decided the band had gone
 * home".
 */
class ShowLogTest {

    private val rig = defaultRigProfile()

    private fun night(): Pair<File, StageEngine> {
        val dir = File(System.getProperty("java.io.tmpdir"),
            "stagemix-logtest-" + System.nanoTime())
        val log = ShowLog(dir, snapshotSec = 5.0, name = "night.log")
        val e = StageEngine(rig, EngineSettings(mode = BalanceMode.KEEP))
        e.onDecision = { d -> log.decision(d) }
        val names = (0 until 16).associateWith { "CH${it + 1} DESK NAME" }
        log.head("name='M18' ip=10.0.0.1", e, names, 3, "vocal +0.5 dB",
            build = "abc1234 (built now, v0.1.0)")

        var t = 0.0
        val band = FloatArray(16) { -80f }
        fun play(on: Boolean) {
            band.fill(-80f)
            if (on) {
                band[0] = -18f; band[1] = -21f; band[3] = -22f
                band[4] = -20f; band[5] = -23f; band[7] = -24f
                band[8] = -19f; band[11] = -17f; band[14] = -25f
            }
        }
        var lastSent = HashMap<Int, Float>()
        fun run(sec: Double, directing: Boolean = true) {
            val end = t + sec
            var nextTick = t
            while (t < end) {
                e.onMeters(band, t)
                if (t >= nextTick) {
                    nextTick += 1.0
                    for (w in e.tick(t)) {
                        log.fader(w.channel, w.levelDb,
                            names[w.channel] ?: "", lastSent[w.channel],
                            e.decisions.firstOrNull { it.channel == w.channel }
                                ?.let { "— ${it.kind}: ${it.reason}" })
                        lastSent[w.channel] = w.levelDb
                    }
                    log.snapshot(t, e, null, names, directing)
                    log.summary(t, e, names)
                }
                t += 0.05
            }
        }
        play(true)
        run(6.0)
        log.takeover((0 until 16).associateWith { -10f }, names)
        e.takeover((0 until 16).associateWith { -10f }, t)
        run(150.0)
        e.adoptBalance(t)
        // a song ends: everything stops, then comes back
        play(false); run(60.0)
        play(true); run(120.0)
        // and the operator moves a fader by hand
        e.operatorOverride(4, -4f, t)
        run(30.0)
        log.footer(e, names)
        log.flush()
        return log.file to e
    }

    // ------------------------------------------------------------------
    @Test fun `the log says which build wrote it`() {
        val (f, _) = night()
        val head = f.readLines().filter { " HEAD  " in it }
        assertTrue(head.any { "abc1234" in it },
            "a night's log is unreadable without knowing which version " +
            "made it: " + head.take(3))
        assertTrue(head.any { "gates:" in it && "between-songs" in it },
            "and what the switches that silence the engine were set to")
    }

    @Test fun `every fader write says where it came from and why`() {
        val (f, _) = night()
        val moves = f.readLines().filter { " FADER " in it }
        assertTrue(moves.isNotEmpty(), "the app moved faders; the log must say so")
        println(moves.take(3).joinToString("\n"))
        assertTrue(moves.count { "->" in it && "(" in it } >= moves.size / 2,
            "a destination with no origin cannot be added up: " +
            moves.first())
        assertTrue(moves.any { "—" in it },
            "and each one carries the reason the engine gave")
    }

    @Test fun `the night has a timeline you can grep`() {
        val (f, _) = night()
        val marks = f.readLines().filter { " MARK  " in it }
        println("MARKS:\n" + marks.joinToString("\n").take(1200))
        assertTrue(marks.any { "GAP" in it },
            "the band stopped and the engine froze itself — that is a " +
            "landmark: $marks")
        assertTrue(marks.any { "MUSIC" in it },
            "and it noticed when they came back")
        assertTrue(marks.any { "OVERRIDE" in it || "SOLORIDE" in it },
            "the operator moved a fader by hand")
    }

    @Test fun `the table says who moved what`() {
        val (f, _) = night()
        val lines = f.readLines()
        val dgst = lines.filter { " DGST  " in it }
        assertTrue(dgst.any { "app" in it && "you" in it },
            "the digest needs its column header: " + dgst.take(2))
        assertTrue(dgst.count { Regex("ch\\d\\d ").containsMatchIn(it) } >= 16,
            "one row per channel, every two minutes")
        println("DIGEST:\n" + dgst.take(20).joinToString("\n"))
    }

    @Test fun `the end of the night is a report card`() {
        val (f, _) = night()
        val card = f.readLines().filter { " CARD  " in it }
        println("CARD:\n" + card.joinToString("\n"))
        assertTrue(card.any { "TOTAL fader travel" in it },
            "the first question about a night is how much of the " +
            "movement was the app's: $card")
        assertTrue(card.count { Regex("ch\\d\\d ").containsMatchIn(it) } >= 16,
            "and every channel gets its line")
        val sum = f.readLines().filter { " SUM   " in it }
        assertTrue(sum.any { "decisions tonight:" in it },
            "with every kind of decision counted, so a runaway shows up " +
            "at the bottom instead of hiding in a hundred thousand lines")
    }

    @Test fun `a processing write is written in dB and Hz, not in floats`() {
        // The desk stores everything as a 0..1 float, so a raw log of
        // the chain reads /ch/09/eq/2/g = 0.400 — which is a 3 dB cut,
        // to somebody willing to do the arithmetic on every line.
        val dir = File(System.getProperty("java.io.tmpdir"),
            "stagemix-paramtest-" + System.nanoTime())
        val log = ShowLog(dir, name = "p.log")
        val t = ChannelTreatment()
        val writes = t.consider(8, Role.VOCAL,
            InstrumentId.Verdict(Family.VOICELIKE, 0.95f, "because"), 1f,
            DoubleArray(100), 100.0,
            ChannelTreatment.Shape(lowEdgeHz = 87f))
        for (w in writes) log.param(w.address, w.value, "LEAD VOX",
            "— first time", 100.0)
        log.flush()
        val out = log.file.readLines().filter { " PARAM " in it }
        println(out.joinToString("\n"))
        assertTrue(out.any { "high-pass at 78 Hz" in it },
            "the corner in Hz: " + out.take(2))
        assertTrue(out.any { Regex("band \\d gain -[0-9.]+ dB").containsMatchIn(it) },
            "and the cuts in dB")
        assertTrue(out.none { Regex("= 0\\.\\d\\d\\d").containsMatchIn(it) },
            "no raw console floats")
    }

    @Test fun `the running picture carries the plan and the error`() {
        val (f, _) = night()
        val lvl = f.readLines().filter { " LVL   " in it }
        assertTrue(lvl.any { "plan" in it && "err" in it },
            "in KEEP mode those two numbers are the whole explanation " +
            "for a fader move: " + lvl.take(2))
        println(lvl.takeLast(4).joinToString("\n"))
    }
}
