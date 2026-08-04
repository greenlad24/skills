package com.stagemix.vm18

import java.io.ByteArrayInputStream
import java.io.File
import javax.sound.sampled.AudioFileFormat
import javax.sound.sampled.AudioFormat
import javax.sound.sampled.AudioInputStream
import javax.sound.sampled.AudioSystem
import kotlin.math.PI
import kotlin.math.sin
import kotlin.test.Test
import kotlin.test.assertTrue

/**
 * The operator's actual rig, from the log they sent: sixteen 48 kHz
 * 16-bit WAVs, some mono and some stereo, loaded one at a time from the
 * window, then PLAY.
 *
 * Everything before this used mono 24-bit stems written by our own
 * writer, which is not what a DAW hands you.
 */
class RealRigTest {

    /** a 16-bit WAV, mono or stereo, the way a DAW exports one */
    private fun wav16(f: File, sr: Int, seconds: Double, hz: Double,
                      channels: Int, level: Float = 0.4f) {
        val n = (sr * seconds).toInt()
        val bytes = ByteArray(n * 2 * channels)
        var p = 0
        for (i in 0 until n) {
            val v = (level * sin(2 * PI * hz * i / sr) * 32767).toInt()
            for (c in 0 until channels) {
                bytes[p++] = (v and 255).toByte()
                bytes[p++] = ((v shr 8) and 255).toByte()
            }
        }
        val fmt = AudioFormat(sr.toFloat(), 16, channels, true, false)
        AudioSystem.write(
            AudioInputStream(ByteArrayInputStream(bytes), fmt, n.toLong()),
            AudioFileFormat.Type.WAVE, f)
    }

    @Test fun `the operator's rig plays`() {
        val dir = File(System.getProperty("java.io.tmpdir"), "sm-realrig")
            .apply { deleteRecursively(); mkdirs() }
        // exactly the shapes in their log: mono and stereo mixed
        val spec = listOf(
            "KICK" to 1, "SNARE" to 1, "OVERHEAD" to 1, "BASS" to 1,
            "GTR AMP" to 2, "PIANO L" to 2, "PIANO L 2" to 2, "GTR DI" to 2,
            "VOCAL CENTRE" to 1, "VOCAL PIANO" to 1, "SNARE 2" to 1,
            "CONGOS" to 1, "DI 1" to 2, "DI 2" to 1, "UTILITY 3" to 2,
            "HARMONICA" to 1)
        val files = spec.mapIndexed { i, (name, ch) ->
            val f = File(dir, "$name.wav")
            wav16(f, 48000, 3.0, 80.0 + i * 40, ch)
            f
        }

        val console = Console(port = 21301)
        // launched from the Dock: no files at all until the window loads them
        val player = Player(MutableList(16) { null }, console,
            sampleRate = 48000)
        val lines = ArrayList<String>()
        player.log = { lines.add(it); println("  $it") }
        try {
            player.open()
            val loop = Thread { player.run() }.apply { isDaemon = true; start() }
            Thread.sleep(100)

            // load them one at a time, as clicking each strip does
            for ((i, f) in files.withIndex()) {
                assertTrue(player.load(i, f), "ch${i + 1} did not load")
                console.names[i] = f.name.substringBeforeLast('.')
            }

            player.play()
            Thread.sleep(1000)

            assertTrue(player.positionSec > 0.2,
                "PLAY produced no movement at all: position " +
                "${player.positionSec}s, playing=${player.playing}\n" +
                lines.joinToString("\n"))
            assertTrue(player.lastMixPeak > 0.02f,
                "sixteen channels loaded and the mix came out at " +
                "${player.lastMixPeak} — this is the reported silence\n" +
                lines.joinToString("\n"))
            println("position ${player.positionSec}s, peak ${player.lastMixPeak}")
            loop.interrupt()
        } finally { player.close(); console.stop() }
    }

    @Test fun `a stereo 16 bit wav is read at full level`() {
        // stereo was never covered: every earlier test used mono stems
        val dir = File(System.getProperty("java.io.tmpdir"), "sm-stereo16")
            .apply { deleteRecursively(); mkdirs() }
        val f = File(dir, "05 GTR AMP.wav")
        wav16(f, 48000, 2.0, 220.0, channels = 2, level = 0.5f)
        val console = Console(port = 21302)
        val player = Player(MutableList(16) { null }, console, sampleRate = 48000)
        player.log = { println("  $it") }
        try {
            player.open()
            assertTrue(player.load(4, f), "stereo wav did not load")
            var peak = 0f
            repeat(10) {
                player.processBlock()
                if (player.lastMixPeak > peak) peak = player.lastMixPeak
            }
            // 0.5 at the -10 dB takeover fader is about 0.16
            assertTrue(peak > 0.05f, "stereo 16-bit came out at $peak")
            println("stereo peak $peak")
        } finally { player.close(); console.stop() }
    }

    @Test fun `the channels loaded are remembered for the next launch`() {
        val dir = File(System.getProperty("java.io.tmpdir"), "sm-session")
            .apply { deleteRecursively(); mkdirs() }
        val kick = File(dir, "KICK.wav").also { wav16(it, 48000, 0.5, 60.0, 1) }
        val vox = File(dir, "VOCAL CENTRE.wav")
            .also { wav16(it, 48000, 0.5, 300.0, 1) }
        val gone = File(dir, "GONE.wav").also { wav16(it, 48000, 0.5, 200.0, 1) }

        val files = MutableList<File?>(16) { null }
        val names = MutableList(16) { "" }
        files[0] = kick; names[0] = "KICK"
        files[8] = vox;  names[8] = "VOCAL CENTRE"
        files[15] = gone; names[15] = "GONE"
        Session.save(files, names)

        // the file moves away between sessions, as they do
        gone.delete()

        val back = Session.load()
        assertTrue(back != null, "nothing was remembered")
        assertTrue(back!!.found == 2,
            "expected 2 files back, got ${back.found}")
        assertTrue(back.files[0]?.name == "KICK.wav", "ch01 not restored")
        assertTrue(back.files[8]?.name == "VOCAL CENTRE.wav",
            "ch09 not restored")
        assertTrue(back.names[8] == "VOCAL CENTRE", "the name was not kept")
        assertTrue(back.files[15] == null,
            "a file that no longer exists must not be handed back as loaded")
        assertTrue(back.missing.any { "GONE" in it },
            "a file that has moved should be named, not silently dropped: " +
            "${back.missing}")

        // and it can be forgotten
        Session.forget()
        assertTrue(Session.load() == null, "forgetting did not clear it")
        println("remembered ${back.found}, missing ${back.missing}")
    }
}
