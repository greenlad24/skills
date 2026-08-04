package com.stagemix.replay

import java.io.File
import kotlin.math.PI
import kotlin.math.sin
import kotlin.test.Test
import kotlin.test.assertTrue

/**
 * End to end: write stems the way a DAW would, replay them through the
 * real engine, and check that the tool read the audio, heard the right
 * levels, made decisions and rendered a mix.
 *
 * The stems are synthetic — the point of this test is the plumbing
 * (24-bit WAV in, metering, RTA, engine, log, mix out), not musical
 * judgement. That is what a real recording is for.
 */
class ReplayTest {

    private val sr = 24000

    private fun writeStem(f: File, seconds: Double, level: Float,
                          hz: Double, gateAfter: Double = -1.0) {
        val w = WavWriter(f, sr, channels = 1)
        val n = (sr * seconds).toInt()
        val block = FloatArray(2048)
        var i = 0
        val rnd = java.util.Random(hz.toLong())
        while (i < n) {
            val k = minOf(block.size, n - i)
            for (j in 0 until k) {
                val t = (i + j).toDouble() / sr
                val on = gateAfter < 0 || t < gateAfter
                // a tone with a slow tremolo and some noise: moves like
                // an instrument, so the static-source detector leaves it
                // alone
                val env = if (on) (0.7 + 0.3 * sin(2 * PI * 0.7 * t)) else 0.0
                block[j] = (level * env * (sin(2 * PI * hz * t) +
                        0.15 * rnd.nextGaussian())).toFloat()
            }
            w.write(block, block, k)
            i += k
        }
        w.close()
    }

    /**
     * KEEP is what the tablet ships in, so the replay tool has to be
     * able to answer "what would KEEP have done to this night" — but
     * LEAD is its DEFAULT, and the difference is worth stating because
     * a green build once depended on nobody noticing it. A folder of
     * stems has no desk and no human mix on it, only the flat starting
     * fader; asked to KEEP that, the engine correctly keeps it, decides
     * almost nothing, and renders a mix identical to the reference. The
     * question a recording can actually answer is "what would the app
     * have made of this from scratch", and that is LEAD.
     */
    @Test fun `the replay tool asks the question a recording can answer`() {
        val dir = File(System.getProperty("java.io.tmpdir"),
            "stagemix-replay-mode").apply { deleteRecursively(); mkdirs() }
        val secs = 40.0
        writeStem(File(dir, "01 Kick Drum.wav"), secs, 0.30f, 60.0)
        writeStem(File(dir, "09 Vocal Center.wav"), secs, 0.06f, 180.0)
        writeStem(File(dir, "12 Bass DI.wav"), secs, 0.25f, 80.0)

        fun decisionsWith(vararg extra: String): Int {
            val out = File(dir, "out-" + extra.joinToString("").ifEmpty { "default" })
            main(arrayOf(dir.absolutePath, "--out", out.absolutePath,
                "--snapshot", "2", *extra))
            val log = File(out, "logs").listFiles()?.firstOrNull()
            assertTrue(log != null, "no show log written")
            return log!!.readLines().count { " DEC " in it }
        }
        val lead = decisionsWith()
        val keep = decisionsWith("--keep")
        println("decisions: LEAD $lead, KEEP $keep")
        assertTrue(lead > 3,
            "the default must be the mode that actually mixes: $lead")
        assertTrue(keep < lead,
            "KEEP has a balance to defend and should barely move: " +
            "KEEP $keep vs LEAD $lead")
    }

    @Test fun `a recorded take replays through the real engine`() {
        val dir = File(System.getProperty("java.io.tmpdir"),
            "stagemix-replay-test").apply { deleteRecursively(); mkdirs() }
        val secs = 45.0
        // a small band: kick, snare, piano pair, guitar, bass, two vocals.
        // The bass arrives a third of the way in, so the lineup changes.
        writeStem(File(dir, "01 Kick Drum.wav"), secs, 0.30f, 60.0)
        writeStem(File(dir, "02 Snare.wav"), secs, 0.16f, 220.0)
        writeStem(File(dir, "05 Guitar Amp.wav"), secs, 0.20f, 330.0)
        writeStem(File(dir, "06 Piano L.wav"), secs, 0.10f, 262.0)
        writeStem(File(dir, "07 Piano R.wav"), secs, 0.10f, 264.0)
        writeStem(File(dir, "09 Vocal Center.wav"), secs, 0.13f, 180.0)
        writeStem(File(dir, "10 Vocal Piano.wav"), secs, 0.07f, 240.0)
        // bass silent for the first 15 s, then plays
        run {
            val f = File(dir, "12 Bass DI.wav")
            val w = WavWriter(f, sr, channels = 1)
            val n = (sr * secs).toInt(); val block = FloatArray(2048)
            var i = 0; val rnd = java.util.Random(7)
            while (i < n) {
                val k = minOf(block.size, n - i)
                for (j in 0 until k) {
                    val t = (i + j).toDouble() / sr
                    block[j] = if (t < 15.0) 0f
                    else (0.33 * (0.7 + 0.3 * sin(2 * PI * 0.5 * t)) *
                            (sin(2 * PI * 80.0 * t) +
                             0.1 * rnd.nextGaussian())).toFloat()
                }
                w.write(block, block, k); i += k
            }
            w.close()
        }

        val out = File(dir, "out")
        main(arrayOf(dir.absolutePath, "--render", "--out", out.absolutePath,
            "--snapshot", "2"))

        val log = File(out, "logs").listFiles()?.firstOrNull()
        assertTrue(log != null && log.length() > 0, "no show log written")
        val text = log!!.readLines()

        // it read the audio: the levels it heard must be sane dBFS, not
        // silence and not clipping
        val lvl = text.filter { " LVL " in it }
        assertTrue(lvl.isNotEmpty(), "no level snapshots in the log")
        val srcDb = lvl.mapNotNull {
            Regex("src\\s*(-?\\d+\\.\\d)").find(it)?.groupValues?.get(1)
                ?.toFloatOrNull() }
        assertTrue(srcDb.any { it > -40f && it < 0f },
            "the tool heard nothing plausible: ${srcDb.take(5)}")

        // it took over, decided things, and moved faders
        assertTrue(text.any { " TAKE " in it }, "never took over")
        assertTrue(text.count { " DEC " in it } > 3,
            "the engine made no decisions")
        assertTrue(text.count { " FADER " in it } > 3, "no fader moves")
        // the bass arriving is a lineup change the engine should notice
        assertTrue(text.any { "ensemble" in it && " DEC " in it },
            "the bass arriving was not detected as a lineup change")

        // and it rendered both mixes, of a believable size
        val auto = File(out, "${dir.name}_autopilot.wav")
        val flat = File(out, "${dir.name}_flat.wav")
        assertTrue(auto.exists() && flat.exists(), "mixes not rendered")
        val expect = (sr * secs * 2 * 3).toLong()   // stereo, 24-bit
        assertTrue(auto.length() > expect * 0.8,
            "autopilot mix is short: ${auto.length()} vs ~$expect")
        assertTrue(flat.length() > expect * 0.8, "flat mix is short")
    }

    @Test fun `a meter tape replays to the same mix as the audio`() {
        // The point of the tape: the recording never has to leave the
        // machine it was made on. A megabyte of levels must therefore
        // drive the engine to the same place tens of gigabytes of audio
        // would — otherwise it is not a test of anything.
        val dir = File(System.getProperty("java.io.tmpdir"),
            "stagemix-tape-test").apply { deleteRecursively(); mkdirs() }
        val secs = 40.0
        writeStem(File(dir, "01 Kick Drum.wav"), secs, 0.30f, 60.0)
        writeStem(File(dir, "05 Guitar Amp.wav"), secs, 0.20f, 330.0)
        writeStem(File(dir, "06 Piano L.wav"), secs, 0.10f, 262.0)
        writeStem(File(dir, "09 Vocal Center.wav"), secs, 0.13f, 180.0)
        writeStem(File(dir, "12 Bass DI.wav"), secs, 0.33f, 80.0)

        val fromAudio = File(dir, "audio").apply { mkdirs() }
        val tape = File(dir, "night.smcap")
        main(arrayOf(dir.absolutePath, "--out", fromAudio.absolutePath,
            "--capture", tape.absolutePath, "--snapshot", "2"))
        assertTrue(tape.exists() && tape.length() > 0, "no capture written")

        val fromTape = File(dir, "tape").apply { mkdirs() }
        main(arrayOf(tape.absolutePath, "--out", fromTape.absolutePath,
            "--snapshot", "2"))

        fun finalOffsets(out: File): Map<String, Float> {
            val log = File(out, "logs").listFiles()!!.first()
            val last = log.readLines().filter { " LVL " in it }
            val byCh = LinkedHashMap<String, Float>()
            for (l in last) {
                val ch = Regex("LVL\\s+(ch\\d\\d)").find(l)
                    ?.groupValues?.get(1) ?: continue
                val off = Regex("off\\s*([+-]\\d+\\.\\d+)").find(l)
                    ?.groupValues?.get(1)?.toFloatOrNull() ?: continue
                byCh[ch] = off      // later lines overwrite: ends at the last
            }
            return byCh
        }
        val a = finalOffsets(fromAudio)
        val b = finalOffsets(fromTape)
        assertTrue(a.isNotEmpty() && b.isNotEmpty(), "no levels logged")
        assertTrue(a.keys == b.keys, "different channels: ${a.keys} ${b.keys}")
        for (ch in a.keys)
            assertTrue(kotlin.math.abs(a[ch]!! - b[ch]!!) <= 0.75f,
                "$ch ended at ${a[ch]} from the audio but ${b[ch]} from the " +
                "tape — the tape is not a faithful stand-in")
        println("tape ${tape.length()} bytes vs " +
            "${dir.listFiles()!!.filter { it.name.endsWith(".wav") }
                .sumOf { it.length() }} bytes of audio")
    }

    @Test fun `wav round trip survives 24 bit`() {
        val f = File(System.getProperty("java.io.tmpdir"), "sm-rt.wav")
        val w = WavWriter(f, 48000, channels = 1)
        val x = FloatArray(1024) { sin(2 * PI * it / 64.0).toFloat() * 0.5f }
        w.write(x, x, x.size); w.close()
        val r = WavReader(f)
        val back = Array(1) { FloatArray(1024) }
        val n = r.read(back, 1024)
        r.close()
        assertTrue(n == 1024, "read $n of 1024 frames")
        for (i in 0 until 1024)
            assertTrue(kotlin.math.abs(back[0][i] - x[i]) < 1e-3f,
                "sample $i: ${back[0][i]} vs ${x[i]}")
    }
}
