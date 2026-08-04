package com.stagemix.vm18

import com.stagemix.replay.WavWriter
import java.io.File
import kotlin.math.PI
import kotlin.math.sin
import kotlin.test.Test
import kotlin.test.assertTrue

/**
 * "I put the channels in, pressed play, no sound."
 *
 * Silence has too many possible causes to guess at from the outside, so
 * the whole path from a file on disk to the bytes that would go to the
 * speakers runs here, with no sound card involved: load the WAVs, read a
 * block, meter it, mix it through the faders, and check that what comes
 * out is not zero.
 */
class PlaybackTest {

    private fun stem(f: File, sr: Int, seconds: Double, hz: Double,
                     level: Float = 0.3f) {
        val w = WavWriter(f, sr, channels = 1)
        val n = (sr * seconds).toInt()
        val b = FloatArray(4096)
        var i = 0
        while (i < n) {
            val k = minOf(b.size, n - i)
            for (j in 0 until k)
                b[j] = (level * sin(2 * PI * hz * (i + j) / sr)).toFloat()
            w.write(b, b, k)
            i += k
        }
        w.close()
    }

    private fun bench(dir: File, port: Int): Pair<Console, Player> {
        val (files, names) = assignFolder(dir)
        val console = Console(port = port)
        for (c in 0 until 16) console.names[c] = names[c]
        val player = Player(files, console, sampleRate = 48000)
        player.log = { println("  $it") }
        player.open()
        return console to player
    }

    @Test fun `wav channels reach the speakers`() {
        val dir = File(System.getProperty("java.io.tmpdir"), "sm-play-wav")
            .apply { deleteRecursively(); mkdirs() }
        // the formats a DAW actually exports, all at once
        stem(File(dir, "01 Kick Drum.wav"), 48000, 2.0, 60.0)
        stem(File(dir, "09 Vocal Center.wav"), 48000, 2.0, 300.0)
        stem(File(dir, "12 Bass DI.wav"), 44100, 2.0, 80.0)   // odd rate

        val (console, player) = bench(dir, 21201)
        try {
            var peak = 0f
            var frames = 0
            repeat(20) {
                val n = player.processBlock()
                if (n > 0) { frames += n; if (player.lastMixPeak > peak)
                    peak = player.lastMixPeak }
            }
            assertTrue(frames > 0,
                "the player read no frames at all — PLAY would be silent " +
                "and would stop immediately")
            assertTrue(peak > 0.01f,
                "the mix came out at peak $peak — PLAY would be silent")
            // and the desk heard the sources, or the engine steers on nothing
            val heard = console.inputDb.count { it > -60f }
            assertTrue(heard >= 3,
                "the console metered only $heard channels of the 3 loaded")
            println("mixed ${frames} frames, peak $peak, $heard channels metered")
        } finally { player.close(); console.stop() }
    }

    @Test fun `24 bit stems are not silent`() {
        // WavWriter writes 24-bit, which is what Studio One exports; a
        // wrong bytes-per-sample here reads as silence or as noise
        val dir = File(System.getProperty("java.io.tmpdir"), "sm-play-24")
            .apply { deleteRecursively(); mkdirs() }
        stem(File(dir, "05 Guitar Amp.wav"), 48000, 1.0, 220.0, level = 0.5f)
        val (console, player) = bench(dir, 21202)
        try {
            var peak = 0f
            repeat(10) {
                player.processBlock()
                if (player.lastMixPeak > peak) peak = player.lastMixPeak
            }
            // one channel at the -10 dB takeover fader: about 0.5 * 0.316
            assertTrue(peak > 0.05f, "24-bit stem came out at $peak")
            println("24-bit peak $peak")
        } finally { player.close(); console.stop() }
    }

    @Test fun `the faders the tablet writes are audible in the mix`() {
        val dir = File(System.getProperty("java.io.tmpdir"), "sm-play-fade")
            .apply { deleteRecursively(); mkdirs() }
        stem(File(dir, "01 Kick Drum.wav"), 48000, 3.0, 60.0)
        val (console, player) = bench(dir, 21203)
        try {
            repeat(6) { player.processBlock() }
            val before = player.lastMixPeak
            // the autopilot pulls it 20 dB down
            console.params["/ch/01/mix/fader"] =
                com.stagemix.engine.FaderLaw.dbToFloat(-30f)
            repeat(6) { player.processBlock() }
            val after = player.lastMixPeak
            assertTrue(after < before * 0.3f,
                "a 20 dB fader cut changed the mix from $before to $after — " +
                "the tablet's moves are not reaching the audio")
            println("fader cut: $before -> $after")
        } finally { player.close(); console.stop() }
    }

    @Test fun `a missing sound card does not stop the bench`() {
        // this container has no audio device at all, which is the point:
        // open() must survive it and everything else must still run
        val dir = File(System.getProperty("java.io.tmpdir"), "sm-play-nodev")
            .apply { deleteRecursively(); mkdirs() }
        stem(File(dir, "01 Kick Drum.wav"), 48000, 1.0, 60.0)
        val (console, player) = bench(dir, 21204)
        try {
            assertTrue(player.processBlock() > 0,
                "with no sound card the bench must still mix and meter")
        } finally { player.close(); console.stop() }
    }

    @Test fun `pressing play before loading does not kill the transport`() {
        // The reported symptom: channels in, PLAY, silence. Pressing PLAY
        // on an empty bench used to break the loop for good, so every
        // later PLAY was silent no matter what had been loaded since.
        val dir = File(System.getProperty("java.io.tmpdir"), "sm-play-order")
            .apply { deleteRecursively(); mkdirs() }
        val console = Console(port = 21205)
        val player = Player(MutableList(16) { null }, console,
            sampleRate = 48000)
        player.log = { println("  $it") }
        try {
            player.open()
            val loop = Thread { player.run() }.apply { isDaemon = true; start() }

            // press PLAY with nothing loaded
            player.play()
            Thread.sleep(200)
            assertTrue(!player.playing, "an empty bench should stop playing")

            // now load a channel, as an operator would, and press PLAY
            stem(File(dir, "01 Kick Drum.wav"), 48000, 2.0, 60.0)
            assertTrue(player.load(0, File(dir, "01 Kick Drum.wav")),
                "the channel did not load")
            console.names[0] = "Kick Drum"
            player.play()
            Thread.sleep(600)

            assertTrue(player.playing || player.positionSec > 0.0,
                "PLAY did nothing after an earlier PLAY on an empty bench — " +
                "the transport was dead")
            assertTrue(player.lastMixPeak > 0.01f,
                "still silent after loading: peak ${player.lastMixPeak}")
            println("recovered: peak ${player.lastMixPeak} at " +
                "${player.positionSec}s")
            loop.interrupt()
        } finally { player.close(); console.stop() }
    }
}
