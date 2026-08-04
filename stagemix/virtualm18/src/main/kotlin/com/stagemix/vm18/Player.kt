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
    private val dyn = List(channels) { ChannelDynamics(sampleRate) }
    private val gate = FloatArray(16)
    private val comp = FloatArray(16)

    /** the room's feedback path — see RoomLoop */
    val room = RoomLoop(sampleRate)
    private val howl = FloatArray(blockFrames)

    /**
     * Which channels are open microphones. Only these are part of the
     * feedback loop: a bass DI cannot howl however far you push it.
     */
    var isMic: (Int) -> Boolean = { ch ->
        val n = (console.names[ch] ?: "").lowercase()
        n.isNotBlank() &&
            !listOf("di", "synth", "808").any { it in n } &&
            listOf("vocal", "vox", "mic", "sax", "harm", "conga", "congo",
                "snare", "overhead", "amp", "flute", "kick", "tom", "hat")
                .any { it in n }
    }

    private val outFmt = AudioFormat(sampleRate.toFloat(), 16, 2, true, false)
    private var line: SourceDataLine? = null
    private val mixL = FloatArray(blockFrames)
    private val mixR = FloatArray(blockFrames)
    private val outBytes = ByteArray(blockFrames * 4)

    @Volatile var playing = false; private set
    @Volatile var positionSec = 0.0; private set
    /** the take has run out — not the end of the bench */
    @Volatile var finished = false; private set
    @Volatile private var running = true
    /** what the room is hearing per channel, post-fader, for the UI */
    val postDb = FloatArray(channels) { -128f }
    var mute = false
    var log: ((String) -> Unit)? = null

    private val srcFiles = files.toMutableList()

    /** the file currently loaded on a channel, for the window */
    fun fileOf(ch: Int): File? = srcFiles.getOrNull(ch)

    fun open() {
        for (c in 0 until channels) load(c, srcFiles[c])
        line = try {
            AudioSystem.getSourceDataLine(outFmt).apply {
                open(outFmt, blockFrames * 8)
                start()
            }
        } catch (e: Exception) {
            // No output device, or one that will not take this format.
            // Everything else still works — meters, the OSC conversation,
            // the autopilot — so say so and carry on rather than dying
            // before the window is even up.
            log?.invoke("NO AUDIO OUTPUT: ${e.message} — the bench will " +
                "still meter and mix, you just will not hear it")
            null
        }
        log?.invoke("output: ${line?.format ?: "none"}")
    }

    /**
     * Put a file on a channel — the way channels get loaded one at a
     * time from the window. Takes effect from the current position, so
     * it is meant for a stopped player; loading mid-play simply starts
     * that channel from its own beginning.
     */
    @Synchronized fun load(ch: Int, f: File?): Boolean {
        if (ch !in 0 until channels) return false
        runCatching { streams[ch]?.close() }
        streams[ch] = null
        srcFiles[ch] = f
        if (f == null) { log?.invoke("ch${ch + 1}: cleared"); return true }
        return try {
            val st = decoded(f)
            streams[ch] = st
            log?.invoke("ch%02d: %s — %.0f Hz, %d bit, %d ch"
                .format(java.util.Locale.ROOT, ch + 1, f.name,
                    st.format.sampleRate, st.format.sampleSizeInBits,
                    st.format.channels))
            true
        } catch (e: Exception) {
            log?.invoke("ch${ch + 1}: cannot open ${f.name} — ${e.message}")
            false
        }
    }

    /** back to the top, without reopening the output line */
    @Synchronized fun rewind() {
        val was = playing
        playing = false
        finished = false
        for (c in 0 until channels) load(c, srcFiles[c])
        positionSec = 0.0
        playing = was
    }

    /**
     * Open any supported file as signed 16-bit PCM at our output rate.
     *
     * In TWO steps, which matters. An mp3 arrives as an MPEG-encoded
     * stream whose `sampleSizeInBits` is NOT_SPECIFIED, and asking for a
     * decode and a sample-rate change in one hop is not a conversion the
     * JDK offers — so the one-step version silently handed back the
     * still-encoded stream, whose bytes-per-sample then came out as
     * zero. Every read returned nothing, the player decided the take had
     * ended, and pressing PLAY produced silence. Decode first, resample
     * second, and refuse anything that is still not PCM.
     */
    private fun decoded(f: File): AudioInputStream {
        val src = AudioSystem.getAudioInputStream(f)
        val sf = src.format
        // 1. whatever it is, get it to PCM at its own rate
        val pcmFmt = AudioFormat(
            AudioFormat.Encoding.PCM_SIGNED, sf.sampleRate, 16,
            sf.channels.coerceAtLeast(1), sf.channels.coerceAtLeast(1) * 2,
            sf.sampleRate, false)
        val pcm = if (sf.encoding == AudioFormat.Encoding.PCM_SIGNED &&
                      sf.sampleSizeInBits > 0) src
                  else AudioSystem.getAudioInputStream(pcmFmt, src)
        // 2. then to our output rate, if it is not already there
        val want = AudioFormat(
            AudioFormat.Encoding.PCM_SIGNED, sampleRate.toFloat(),
            pcm.format.sampleSizeInBits, pcm.format.channels,
            pcm.format.frameSize, sampleRate.toFloat(), false)
        val out = if (pcm.format.sampleRate.toInt() == sampleRate) pcm
                  else if (AudioSystem.isConversionSupported(want, pcm.format))
                      AudioSystem.getAudioInputStream(want, pcm)
                  else pcm     // different rate, but at least it is audio
        require(out.format.sampleSizeInBits > 0) {
            "${f.name}: could not be decoded to PCM " +
            "(${sf.encoding}, ${sf.sampleSizeInBits} bit)"
        }
        if (out.format.sampleRate.toInt() != sampleRate)
            log?.invoke("note: ${f.name} is ${out.format.sampleRate.toInt()} Hz " +
                "and could not be resampled — it will play at the wrong speed")
        return out
    }

    fun testTone() {
        val l = line ?: run { log?.invoke("no audio output line"); return }
        val n = sampleRate
        val b = ByteArray(n * 4)
        var p = 0
        for (i in 0 until n) {
            val v = (0.2 * kotlin.math.sin(2 * Math.PI * 1000.0 * i / n) *
                32767).toInt()
            b[p++] = (v and 255).toByte(); b[p++] = ((v shr 8) and 255).toByte()
            b[p++] = (v and 255).toByte(); b[p++] = ((v shr 8) and 255).toByte()
        }
        l.write(b, 0, b.size)
        log?.invoke("test tone sent to ${l.format}")
    }

    /**
     * A second of 1 kHz straight to the output line. If this is silent
     * the problem is the Mac's output device or its volume; if it plays
     * and the channels do not, the problem is the files.
     */
    fun play() {
        // Pressing PLAY before loading anything used to be permanent:
        // the reader hit the end of nothing, the loop broke, and every
        // later PLAY was silent however many channels had been loaded
        // since. Starting again from the top is what the button means.
        if (finished || streams.all { it == null }) rewind()
        playing = true
    }
    fun pause() { playing = false }

    fun close() {
        running = false
        playing = false
        streams.forEach { runCatching { it?.close() } }
        line?.let { runCatching { it.stop(); it.close() } }
    }

    /** peak of the last block that went to the speakers, for tests */
    @Volatile var lastMixPeak = 0f; private set

    /**
     * One block: read every channel, run the room, meter, mix through
     * the tablet's faders. Returns the frames produced, 0 at the end.
     * Split out from [run] so it can be exercised with no sound card.
     */
    fun processBlock(): Int {
        val n = readAll()
        if (n <= 0) return 0
        positionSec += n.toDouble() / sampleRate
            // The room, before anything is metered: if the mains are
            // ringing, the open mics hear it exactly as they would on
            // stage — so the meters, the RTA and the speakers all get it.
            val openMics = (0 until channels)
                .filter { isMic(it) }
                .map { console.faderDb(it) }
            if (room.advance(openMics, n, howl))
                for (c in 0 until channels)
                    if (isMic(c)) for (i in 0 until n) bufs[c][i] += howl[i]

            // pre-fader levels: what the console meters and the app steers on
            for (c in 0 until channels)
                levels[c] = meters[c].push(bufs[c], n)
            console.inputDb = levels.copyOf()

            // the dynamics the desk would be applying, so /meters/6 is
            // worth reading — against the threshold the console holds,
            // which is the one the Channel Doctor moves
            for (c in 0 until channels) {
                val thr = (console.params["/ch/%02d/dyn/thr"
                    .format(java.util.Locale.ROOT, c + 1)] ?: 0.667f) * 60f - 60f
                dyn[c].push(bufs[c], n, thr)
                gate[c] = dyn[c].gateGrDb
                comp[c] = dyn[c].compGrDb
            }
            console.gateGr = gate.copyOf()
            console.compGr = comp.copyOf()

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
        var peak = 0f
        var p = 0
        for (i in 0 until n) {
            val lv = if (mute) 0f else mixL[i]
            val rv = if (mute) 0f else mixR[i]
            if (kotlin.math.abs(lv) > peak) peak = kotlin.math.abs(lv)
            val li = pcm(lv); val ri = pcm(rv)
            outBytes[p++] = (li and 255).toByte()
            outBytes[p++] = ((li shr 8) and 255).toByte()
            outBytes[p++] = (ri and 255).toByte()
            outBytes[p++] = ((ri shr 8) and 255).toByte()
        }
        lastMixPeak = peak
        outBytesUsed = p
        return n
    }

    private var outBytesUsed = 0

    /**
     * The real-time loop. It runs for the life of the bench: reaching the
     * end of a take stops PLAYBACK, it does not end the loop, or the
     * transport would be dead for the rest of the session.
     */
    fun run() {
        while (running) {
            if (!playing) { Thread.sleep(20); continue }
            val n = processBlock()
            if (n <= 0) {
                playing = false
                finished = true
                log?.invoke(if (streams.all { it == null })
                    "nothing loaded — load the channels, then press PLAY"
                    else "end of the take (press START to play it again)")
                continue
            }
            // writing to the line is what paces the show; with no output
            // device there is nothing to pace against, so keep time here
            val l = line
            if (l != null) l.write(outBytes, 0, outBytesUsed)
            else Thread.sleep((1000L * n / sampleRate))
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
            // a stream that reports neither must not divide by zero and
            // must not be mistaken for the end of the night
            if (bps <= 0 || chn <= 0) {
                streams[c] = null
                log?.invoke("ch${c + 1}: unreadable format " +
                    "(${fmt.sampleSizeInBits} bit, ${fmt.channels} ch) — dropped")
                continue
            }
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
