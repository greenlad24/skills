package com.stagemix.vm18

import com.stagemix.replay.LevelMeter
import com.stagemix.replay.Rta
import java.io.File
import javax.sound.sampled.AudioFormat
import javax.sound.sampled.AudioInputStream
import javax.sound.sampled.AudioSystem
import javax.sound.sampled.SourceDataLine
import kotlin.math.pow

/**
 * Plays the night, in real time, with the tablet's faders on it.
 *
 * Sixteen files are opened at once and read a block at a time, so a
 * three-hour recording streams rather than loading. Every block:
 *
 *   · the PRE-fader level of each channel goes to the console, which is
 *     what the app steers against — it hears the true sources whatever
 *     it does with the faders;
 *   · the channel is multiplied by the fader the app has set and summed
 *     into the mix that goes to the speakers;
 *   · one channel at a time is analysed into the 100-bin RTA the
 *     Channel Doctor round-robins across.
 *
 * MP3 and WAV both open through `AudioSystem`; the mp3 SPI on the
 * classpath makes an mp3 look like any other stream. Files with
 * different sample rates are converted to the output rate on the way in,
 * so a folder of whatever the DAW happened to export still plays
 * together.
 */
class Player(
    files: List<File?>,
    private val console: Console,
    val sampleRate: Int = 48000,
    private val blockFrames: Int = 2400,      // 50 ms: the console's cadence
) {
    val channels = files.size
    private val streams = arrayOfNulls<AudioInputStream>(channels)
    private val bufs = Array(channels) { FloatArray(blockFrames) }
    private val raw = Array(channels) { ByteArray(blockFrames * 4) }
    private val meters = List(channels) { LevelMeter(sampleRate) }
    private val rta = List(channels) { Rta(sampleRate, 4096) }
    private val levels = FloatArray(16) { -128f }

    private val outFmt = AudioFormat(sampleRate.toFloat(), 16, 2, true, false)
    private var line: SourceDataLine? = null
    private val mixL = FloatArray(blockFrames)
    private val mixR = FloatArray(blockFrames)
    private val outBytes = ByteArray(blockFrames * 4)

    @Volatile var playing = false; private set
    @Volatile var positionSec = 0.0; private set
    @Volatile var finished = false; private set
    /** what the room is hearing per channel, post-fader, for the UI */
    val postDb = FloatArray(channels) { -128f }
    var mute = false
    var log: ((String) -> Unit)? = null

    private val srcFiles = files

    fun open() {
        for (c in 0 until channels) {
            val f = srcFiles[c] ?: continue
            streams[c] = try { decoded(f) } catch (e: Exception) {
                log?.invoke("ch${c + 1}: cannot open ${f.name} — ${e.message}")
                null
            }
        }
        line = AudioSystem.getSourceDataLine(outFmt).apply {
            open(outFmt, blockFrames * 8)
            start()
        }
    }

    /** open any supported file and convert it to mono float at our rate */
    private fun decoded(f: File): AudioInputStream {
        val raw = AudioSystem.getAudioInputStream(f)
        val want = AudioFormat(sampleRate.toFloat(), 16,
            raw.format.channels.coerceAtMost(2), true, false)
        return if (AudioSystem.isConversionSupported(want, raw.format))
            AudioSystem.getAudioInputStream(want, raw) else raw
    }

    fun play() { playing = true }
    fun pause() { playing = false }

    fun close() {
        playing = false
        streams.forEach { runCatching { it?.close() } }
        line?.let { runCatching { it.stop(); it.close() } }
    }

    /** the real-time loop; run it on its own thread */
    fun run() {
        val l = line ?: return
        while (!finished) {
            if (!playing) { Thread.sleep(20); continue }
            val n = readAll()
            if (n <= 0) { finished = true; playing = false; break }
            positionSec += n.toDouble() / sampleRate

            // pre-fader levels: what the console meters and the app steers on
            for (c in 0 until channels)
                levels[c] = meters[c].push(bufs[c], n)
            console.inputDb = levels.copyOf()

            // the RTA the app has parked on a channel
            val focus = console.rtaSource
            if (focus in 0 until channels)
                rta[focus].push(bufs[focus], n)?.let { console.rtaBins = it }

            // the tablet's faders, on the audio
            java.util.Arrays.fill(mixL, 0, n, 0f)
            java.util.Arrays.fill(mixR, 0, n, 0f)
            for (c in 0 until channels) {
                val g = db2lin(console.faderDb(c))
                postDb[c] = levels[c] + console.faderDb(c)
                if (g <= 0f) continue
                val x = bufs[c]
                for (i in 0 until n) { val v = x[i] * g; mixL[i] += v; mixR[i] += v }
            }
            var p = 0
            for (i in 0 until n) {
                val li = pcm(if (mute) 0f else mixL[i])
                val ri = pcm(if (mute) 0f else mixR[i])
                outBytes[p++] = (li and 255).toByte()
                outBytes[p++] = ((li shr 8) and 255).toByte()
                outBytes[p++] = (ri and 255).toByte()
                outBytes[p++] = ((ri shr 8) and 255).toByte()
            }
            l.write(outBytes, 0, p)     // blocks: this is what paces the show
        }
    }

    /** one block from every channel; short channels simply fall silent */
    private fun readAll(): Int {
        var most = 0
        for (c in 0 until channels) {
            val s = streams[c]
            java.util.Arrays.fill(bufs[c], 0f)
            if (s == null) continue
            val fmt = s.format
            val bps = fmt.sampleSizeInBits / 8
            val chn = fmt.channels
            val want = blockFrames * bps * chn
            if (raw[c].size < want) raw[c] = ByteArray(want)
            var got = 0
            while (got < want) {
                val k = s.read(raw[c], got, want - got)
                if (k <= 0) break
                got += k
            }
            val frames = got / (bps * chn)
            val b = raw[c]
            for (i in 0 until frames) {
                // take the left channel of anything stereo
                val p = i * bps * chn
                var v = b[p + bps - 1].toInt()
                for (k in bps - 2 downTo 0) v = (v shl 8) or (b[p + k].toInt() and 255)
                bufs[c][i] = v.toFloat() / (1 shl (bps * 8 - 1))
            }
            if (frames > most) most = frames
        }
        return most
    }

    private fun pcm(f: Float): Int =
        (f.coerceIn(-1f, 1f) * 32767f).toInt()

    private fun db2lin(db: Float) = 10.0.pow(db / 20.0).toFloat()
}
