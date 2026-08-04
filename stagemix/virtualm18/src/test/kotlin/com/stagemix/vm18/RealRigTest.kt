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

    @Test fun `a folder of mixed sample rates plays together`() {
        // The rig that killed the transport. A DAW folder is not all one
        // rate — a 44.1 kHz bounce sits next to 48 kHz stems — and the
        // JDK's own resampler threw ArrayIndexOutOfBoundsException out of
        // the middle of a read, which took the whole transport thread
        // with it: the window still said PLAYING and no amount of
        // pressing PLAY ever brought it back.
        val dir = File(System.getProperty("java.io.tmpdir"), "sm-rates")
            .apply { deleteRecursively(); mkdirs() }
        val rates = listOf(48000, 44100, 96000, 88200, 32000, 22050)
        val files = rates.mapIndexed { i, sr ->
            File(dir, "ch${i + 1}-$sr.wav")
                .also { wav16(it, sr, 2.0, 220.0, if (i % 2 == 0) 1 else 2) }
        }

        val console = Console(port = 21303)
        val player = Player(MutableList(16) { null }, console, sampleRate = 48000)
        val lines = ArrayList<String>()
        player.log = { lines.add(it); println("  $it") }
        try {
            player.open()
            for ((i, f) in files.withIndex())
                assertTrue(player.load(i, f), "ch${i + 1} ($f) did not load")

            var peak = 0f
            var blocks = 0
            // 2 s of audio at 50 ms a block; run past the end of the
            // shortest file so the tail is exercised too
            repeat(50) {
                if (player.processBlock() > 0) blocks++
                if (player.lastMixPeak > peak) peak = player.lastMixPeak
            }
            assertTrue(blocks >= 40,
                "only $blocks blocks of 50 came back\n" +
                lines.joinToString("\n"))
            assertTrue(peak > 0.05f,
                "mixed rates came out at $peak\n" + lines.joinToString("\n"))
            assertTrue(lines.none { "READ FAILED" in it || "dropped" in it },
                "a channel was dropped:\n" + lines.joinToString("\n"))
            println("mixed rates: $blocks blocks, peak $peak")
        } finally { player.close(); console.stop() }
    }

    @Test fun `a resampled channel keeps its pitch and its continuity`() {
        // Interpolating each block from scratch clicks 20 times a second;
        // the fractional position has to survive the block boundary. A
        // 44.1 kHz 1 kHz tone resampled to 48 kHz must still be a clean
        // 1 kHz tone with no step at any 50 ms seam.
        val dir = File(System.getProperty("java.io.tmpdir"), "sm-resamp")
            .apply { deleteRecursively(); mkdirs() }
        val f = File(dir, "tone.wav")
        wav16(f, 44100, 2.0, 1000.0, channels = 1, level = 0.5f)

        val console = Console(port = 21304)
        val player = Player(MutableList(16) { null }, console, sampleRate = 48000)
        player.log = { println("  $it") }
        try {
            player.open()
            // channel 1 alone, fader at unity, so the mix IS the channel
            assertTrue(player.load(0, f))
            console.params["/ch/01/mix/fader"] = 0.75f     // 0 dB

            var peak = 0f
            var worstStep = 0f
            var prevEnd = 0f
            repeat(30) {
                val n = player.processBlock()
                if (n > 0) {
                    val first = player.blockL(0)
                    // 1 kHz at 48 kHz moves at most ~0.066 per sample;
                    // a seam glitch shows up as a jump far bigger
                    val step = kotlin.math.abs(first - prevEnd)
                    if (it > 0 && step > worstStep) worstStep = step
                    prevEnd = player.blockL(n - 1)
                    if (player.lastMixPeak > peak) peak = player.lastMixPeak
                }
            }
            assertTrue(peak > 0.3f, "0 dB on a 0.5 tone came out at $peak")
            assertTrue(worstStep < 0.15f,
                "a click at the block seam: jump of $worstStep between " +
                "blocks — the resampler is not carrying its position")
            println("resampled peak $peak, worst seam step $worstStep")
        } finally { player.close(); console.stop() }
    }

    @Test fun `a decoder that throws does not take the show down`() {
        // The reported failure, exactly: something deep in a decode threw
        // `ArrayIndexOutOfBoundsException: Index 580 out of bounds for
        // length 580` out of the middle of a read. It escaped the
        // transport thread, the thread ended, and from then on the window
        // still said PLAYING while nothing came out and no amount of
        // pressing PLAY brought it back. One bad channel must cost that
        // channel and nothing else.
        val dir = File(System.getProperty("java.io.tmpdir"), "sm-badch")
            .apply { deleteRecursively(); mkdirs() }
        val good = File(dir, "GOOD.wav").also { wav16(it, 48000, 5.0, 220.0, 1) }

        val console = Console(port = 21305)
        val player = Player(MutableList(16) { null }, console, sampleRate = 48000)
        val lines = ArrayList<String>()
        player.log = { lines.add(it); println("  $it") }
        try {
            player.open()
            for (c in 0 until 3) assertTrue(player.load(c, good))
            // channel 4 blows up on the third read, the way a decoder does
            var reads = 0
            val rogue = object : java.io.InputStream() {
                override fun read(): Int = 0
                override fun read(b: ByteArray, off: Int, len: Int): Int {
                    if (++reads >= 3)
                        throw ArrayIndexOutOfBoundsException(
                            "Index 580 out of bounds for length 580")
                    java.util.Arrays.fill(b, off, off + len, 0)
                    return len
                }
            }
            player.loadStream(3, AudioInputStream(rogue,
                AudioFormat(48000f, 16, 1, true, false), Long.MAX_VALUE))

            val loop = Thread { player.run() }.apply { isDaemon = true; start() }
            player.play()
            Thread.sleep(1200)

            assertTrue(lines.any { "READ FAILED" in it && "ch04" in it },
                "the bad channel was not named:\n" + lines.joinToString("\n"))
            assertTrue(lines.none { "TRANSPORT DIED" in it },
                "the transport died over one bad channel:\n" +
                lines.joinToString("\n"))
            assertTrue(player.loopAlive, "the transport thread is gone")
            assertTrue(player.playing, "playback stopped: ${player.state()}")
            assertTrue(player.lastMixPeak > 0.02f,
                "the three good channels went silent too: ${player.state()}\n" +
                lines.joinToString("\n"))
            println("survived: ${player.state()}")
            loop.interrupt()
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
