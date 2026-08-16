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

    /** the rate the file is actually at; we do the rate change ourselves */
    private val srcRate = DoubleArray(channels) { sampleRate.toDouble() }
    /** source samples read but not yet consumed by the resampler */
    private val srcBuf = Array(channels) { FloatArray(blockFrames + 8) }
    private val srcHeld = IntArray(channels)
    private val srcPos = DoubleArray(channels)
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
        srcHeld[ch] = 0
        srcPos[ch] = 0.0
        srcRate[ch] = sampleRate.toDouble()
        srcFiles[ch] = f
        if (f == null) { log?.invoke("ch${ch + 1}: cleared"); return true }
        return try {
            val st = decoded(f)
            streams[ch] = st
            srcRate[ch] = st.format.sampleRate.toDouble()
                .let { if (it > 0) it else sampleRate.toDouble() }
            log?.invoke("ch%02d: %s — %.0f Hz, %d bit, %d ch [%s]%s"
                .format(java.util.Locale.ROOT, ch + 1, f.name,
                    st.format.sampleRate, st.format.sampleSizeInBits,
                    st.format.channels,
                    // which reader opened it. When a file is misread this
                    // is the first thing worth knowing.
                    if (WavFile.describe(f) != null) "riff" else "spi",
                    if (srcRate[ch].toInt() == sampleRate) ""
                    else " — resampling to ${sampleRate} Hz"))
            true
        } catch (e: Exception) {
            log?.invoke("ch${ch + 1}: cannot open ${f.name} — ${e.message}")
            false
        }
    }

    /**
     * Put an already-open stream on a channel. The bench never needs
     * this — it exists so the tests can hand the transport a decoder
     * that misbehaves, which is the whole failure being defended
     * against and cannot be produced from a well-formed file.
     */
    @Synchronized internal fun loadStream(ch: Int, st: AudioInputStream) {
        if (ch !in 0 until channels) return
        runCatching { streams[ch]?.close() }
        streams[ch] = st
        srcHeld[ch] = 0
        srcPos[ch] = 0.0
        srcRate[ch] = st.format.sampleRate.toDouble()
            .let { if (it > 0) it else sampleRate.toDouble() }
    }

    /** back to the top, without reopening the output line */
    @Synchronized fun rewind() {
        log?.invoke("REWIND — ${state()}")
        val was = playing
        playing = false
        finished = false
        for (c in 0 until channels) load(c, srcFiles[c])
        positionSec = 0.0
        blocksPlayed = 0
        playing = was
        log?.invoke("REWIND done — ${state()}")
    }

    /**
     * Open any supported file as signed PCM AT ITS OWN SAMPLE RATE.
     *
     * Decoding is the JDK's job; the rate change is ours. Asking the JDK
     * to decode and resample in one hop is not a conversion it offers —
     * so the one-step version silently handed back a still-encoded mp3,
     * whose bytes-per-sample then came out as zero, every read returned
     * nothing, and PLAY produced silence.
     *
     * Doing the decode in one step and the rate change in another fixed
     * that and introduced a worse one: the JDK's own resampler threw
     * `ArrayIndexOutOfBoundsException` out of the middle of a read, which
     * killed the transport thread outright — the window still said
     * PLAYING and no amount of pressing PLAY brought it back. That
     * resampler is a known-fragile corner of the JDK and there is no need
     * to be near it: a 16-channel bench already owns its mixing loop, so
     * it may as well own its interpolation too (see [resampleBlock]).
     * Anything that will not decode to PCM at all is refused here, where
     * the file can still be named.
     */
    private fun decoded(f: File): AudioInputStream {
        // A RIFF/RF64 file is parsed by us and never offered to the
        // guessing — see WavFile for what the guessing did to a folder
        // of perfectly good WAVs.
        val src = WavFile.open(f) ?: AudioSystem.getAudioInputStream(f)
        val sf = src.format
        // And if something still claims a file as MPEG that does not
        // begin like one, it is wrong: refuse it here, where the file
        // can be named, rather than three layers down inside a decoder.
        val enc = sf.encoding.toString()
        if (("MPEG" in enc || "mpeg" in enc) && !looksLikeMpeg(f)) {
            runCatching { src.close() }
            throw IllegalStateException(
                "${f.name}: the mp3 decoder claimed this file, but it is " +
                "not an mp3 — refusing it rather than letting it crash " +
                "mid-show")
        }
        val pcmFmt = AudioFormat(
            AudioFormat.Encoding.PCM_SIGNED, sf.sampleRate, 16,
            sf.channels.coerceAtLeast(1), sf.channels.coerceAtLeast(1) * 2,
            sf.sampleRate, false)
        val out = if (sf.encoding == AudioFormat.Encoding.PCM_SIGNED &&
                      sf.sampleSizeInBits > 0) src
                  else AudioSystem.getAudioInputStream(pcmFmt, src)
        require(out.format.sampleSizeInBits > 0) {
            "${f.name}: could not be decoded to PCM " +
            "(${sf.encoding}, ${sf.sampleSizeInBits} bit)"
        }
        require(out.format.sampleRate > 0f) {
            "${f.name}: the file does not say what rate it is at"
        }
        return out
    }

    /**
     * Does this file actually begin like an MPEG stream? An ID3 tag, or
     * a frame sync (eleven set bits) in the first few bytes. Deliberately
     * strict: this is only ever used to reject a claim, and a real mp3
     * that starts with junk will still open the normal way.
     */
    private fun looksLikeMpeg(f: File): Boolean = try {
        java.io.FileInputStream(f).use { s ->
            val b = ByteArray(4)
            val n = s.read(b)
            n >= 3 && (
                (b[0] == 'I'.code.toByte() && b[1] == 'D'.code.toByte() &&
                    b[2] == '3'.code.toByte()) ||
                ((b[0].toInt() and 0xFF) == 0xFF &&
                    (b[1].toInt() and 0xE0) == 0xE0))
        }
    } catch (e: Exception) { false }

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
        log?.invoke("PLAY pressed — before: ${state()}")
        // Pressing PLAY before loading anything used to be permanent:
        // the reader hit the end of nothing, the loop broke, and every
        // later PLAY was silent however many channels had been loaded
        // since. Starting again from the top is what the button means.
        if (finished || streams.all { it == null }) {
            log?.invoke("  (rewinding first: finished=$finished, " +
                "${streams.count { it != null }} channels loaded)")
            rewind()
        }
        // Exactly what is about to be decoded, at the moment of pressing
        // PLAY. The formats are logged as each file loads too, but that
        // is hundreds of lines earlier — and when a decode goes wrong it
        // is the format that explains it.
        for (c in 0 until channels) {
            val s = streams[c] ?: continue
            log?.invoke("  ch%02d %-22s %.0f Hz %d bit %d ch%s"
                .format(java.util.Locale.ROOT, c + 1,
                    srcFiles[c]?.name ?: "?", s.format.sampleRate,
                    s.format.sampleSizeInBits, s.format.channels,
                    if (srcRate[c].toInt() == sampleRate) ""
                    else " -> ${sampleRate} Hz"))
        }
        blocksPlayed = 0
        playing = true
        log?.invoke("PLAY — after:  ${state()}")
        if (!loopAlive) log?.invoke(
            "  WARNING: the transport loop is not running, so nothing " +
            "will be read. This is a bug — please send this log.")
    }
    fun pause() {
        playing = false
        log?.invoke("PAUSE — ${state()}")
    }

    fun close() {
        running = false
        playing = false
        streams.forEach { runCatching { it?.close() } }
        line?.let { runCatching { it.stop(); it.close() } }
    }

    /** peak of the last block that went to the speakers, for tests */
    @Volatile var lastMixPeak = 0f; private set

    /** a sample of the last block that went to the speakers, for tests */
    fun blockL(i: Int): Float = if (i in mixL.indices) mixL[i] else 0f
    /** blocks produced since the transport last started */
    @Volatile var blocksPlayed = 0L; private set
    /** why the last block produced nothing, for the log */
    @Volatile var lastStallReason = ""; private set
    /** is the run loop alive at all? */
    @Volatile var loopAlive = false; private set

    /** everything the transport knows about itself, in one line */
    fun state(): String {
        val loaded = streams.count { it != null }
        return ("playing=%s loop=%s pos=%.2fs blocks=%d peak=%.3f " +
            "loaded=%d/%d finished=%s out=%s%s").format(java.util.Locale.ROOT,
            playing, if (loopAlive) "alive" else "DEAD", positionSec,
            blocksPlayed, lastMixPeak, loaded, channels, finished,
            if (line == null) "none" else "ok",
            if (lastStallReason.isBlank()) "" else " stall=$lastStallReason")
    }

    /**
     * One block: read every channel, run the room, meter, mix through
     * the tablet's faders. Returns the frames produced, 0 at the end.
     * Split out from [run] so it can be exercised with no sound card.
     */
    fun processBlock(): Int {
        // Everything downstream is sized to one block. A decoder that
        // hands back more than it was asked for must not be able to walk
        // off the end of the mix buffers.
        val n = readAll().coerceAtMost(blockFrames)
        if (n <= 0) return 0
        positionSec += n.toDouble() / sampleRate
            // The room, before anything is metered: if the mains are
            // ringing, the open mics hear it exactly as they would on
            // stage — so the meters, the RTA and the speakers all get it.
            val openMics = (0 until channels)
                .filter { isMic(it) }
                .map { console.faderDb(it) + ringBandCutDb(it) }
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
        // Restart rather than die: a transport that has thrown leaves
        // everything looking alive with nothing ever playing again, and
        // no amount of pressing PLAY brings it back.
        var restarts = 0
        while (running && restarts < 20) {
            if (restarts > 0) log?.invoke(
                "transport restarting (attempt $restarts)" +
                if (playing) " — carrying on from %.1fs"
                    .format(java.util.Locale.ROOT, positionSec) else "")
            loop()
            if (!running) break
            restarts++
            // `playing` is deliberately left alone: if the loop threw
            // mid-show the restarted one picks the show straight back
            // up, which is the only acceptable behaviour in a room with
            // people in it.
            Thread.sleep(200)
        }
        if (restarts >= 20) log?.invoke(
            "transport gave up after $restarts restarts — please send this log")
    }

    private fun loop() {
        loopAlive = true
        log?.invoke("transport loop started")
        try {
        while (running) {
            if (!playing) { Thread.sleep(20); continue }
            val n = processBlock()
            if (n <= 0) {
                playing = false
                finished = true
                log?.invoke((if (streams.all { it == null })
                    "STOPPED: nothing loaded — load the channels, then PLAY"
                    else "STOPPED: no audio came back — $lastStallReason") +
                    "  |  ${state()}")
                continue
            }
            blocksPlayed++
            // a heartbeat, so a silent run still says what it is doing
            if (blocksPlayed == 1L || blocksPlayed % 100L == 0L)
                log?.invoke("playing — ${state()}")
            // writing to the line is what paces the show; with no output
            // device there is nothing to pace against, so keep time here
            val l = line
            if (l != null) l.write(outBytes, 0, outBytesUsed)
            else Thread.sleep((1000L * n / sampleRate))
        }
        } catch (e: Throwable) {
            // a thrown transport is the worst failure of all: everything
            // still looks alive and nothing will ever play again
            log?.invoke("TRANSPORT DIED: ${e::class.simpleName}: ${e.message}")
            for (fr in e.stackTrace.take(12)) log?.invoke("    at $fr")
            e.printStackTrace()
        } finally {
            loopAlive = false
            log?.invoke("transport loop ended")
        }
    }

    /** one block from every channel; short channels simply fall silent */
    private fun readAll(): Int {
        var most = 0
        var ended = 0
        var live = 0
        for (c in 0 until channels) {
            val s = streams[c]
            java.util.Arrays.fill(bufs[c], 0f)
            if (s == null) continue
            val fmt = s.format
            val bps = fmt.sampleSizeInBits / 8
            val chn = fmt.channels
            try {
                // a stream that reports neither must not divide by zero
                // and must not be mistaken for the end of the night
                if (bps <= 0 || chn <= 0) {
                    streams[c] = null
                    log?.invoke("ch${c + 1}: unreadable format " +
                        "(${fmt.sampleSizeInBits} bit, ${fmt.channels} ch) — " +
                        "dropped")
                    continue
                }
                val ratio = srcRate[c] / sampleRate
                val frames =
                    if (kotlin.math.abs(ratio - 1.0) < 1e-9)
                        readSource(c, bps, chn, bufs[c], 0, blockFrames)
                    else resampleBlock(c, bps, chn, ratio)
                if (frames > most) most = frames
                if (frames > 0) live++ else ended++
            } catch (e: Throwable) {
                // one unreadable channel must not take the show down
                streams[c] = null
                ended++
                log?.invoke("ch%02d READ FAILED (%s: %s) — dropped, the rest "
                    .format(java.util.Locale.ROOT, c + 1,
                        e::class.simpleName, e.message) + "keep playing")
                log?.invoke("  at " + e.stackTrace.take(4).joinToString(" <- ") {
                    "${it.className.substringAfterLast('.')}." +
                        "${it.methodName}:${it.lineNumber}"
                })
            }
        }
        if (most == 0) lastStallReason =
            "$live channels gave audio, $ended gave nothing, " +
            "${streams.count { it != null }} open"
        return most
    }

    /**
     * [want] frames of channel [c] straight off the stream, as mono
     * floats — the left channel of anything wider. Returns how many
     * frames actually arrived, which is short only at the end of a file.
     *
     * Every write is bounded by the destination as well as by the read,
     * because "the stream handed back more than I asked for" is exactly
     * the kind of thing that ends a show.
     */
    private fun readSource(c: Int, bps: Int, chn: Int,
                           dst: FloatArray, off: Int, want: Int): Int {
        val s = streams[c] ?: return 0
        if (want <= 0 || off >= dst.size) return 0
        val bytes = want * bps * chn
        if (raw[c].size < bytes) raw[c] = ByteArray(bytes)
        val b = raw[c]
        var got = 0
        while (got < bytes) {
            val k = s.read(b, got, bytes - got)
            if (k <= 0) break
            got += k
        }
        val frames = minOf(got / (bps * chn), want, dst.size - off)
        val scale = 1f / (1 shl (bps * 8 - 1))
        for (i in 0 until frames) {
            val p = i * bps * chn
            var v = b[p + bps - 1].toInt()
            for (k in bps - 2 downTo 0) v = (v shl 8) or (b[p + k].toInt() and 255)
            dst[off + i] = v * scale
        }
        return frames
    }

    /**
     * A block of channel [c] pulled up or down to the output rate by
     * linear interpolation, carrying the fractional position and the
     * unconsumed tail across blocks so a three-hour file does not click
     * every 50 ms.
     *
     * Linear is honest here: this bench is judged on levels, spectra and
     * fader moves, none of which care about the last few dB of
     * interpolation noise at the top of the band, and the alternative on
     * offer — the JDK's converter — is the thing that was killing the
     * transport.
     */
    private fun resampleBlock(c: Int, bps: Int, chn: Int, ratio: Double): Int {
        // the furthest source sample any of this block's outputs will
        // touch, plus the one after it for the interpolation
        val need = kotlin.math.floor(
            srcPos[c] + (blockFrames - 1) * ratio).toInt() + 2
        if (srcBuf[c].size < need) srcBuf[c] = srcBuf[c].copyOf(need + blockFrames)
        if (srcHeld[c] < need)
            srcHeld[c] += readSource(c, bps, chn, srcBuf[c], srcHeld[c],
                need - srcHeld[c])

        val sb = srcBuf[c]
        val held = srcHeld[c]
        var pos = srcPos[c]
        var out = 0
        while (out < blockFrames) {
            val i0 = pos.toInt()
            if (i0 < 0 || i0 + 1 >= held) break        // out of source
            val f = (pos - i0).toFloat()
            bufs[c][out++] = sb[i0] + (sb[i0 + 1] - sb[i0]) * f
            pos += ratio
        }

        val consumed = pos.toInt().coerceIn(0, held)
        if (consumed > 0) {
            System.arraycopy(sb, consumed, sb, 0, held - consumed)
            srcHeld[c] = held - consumed
            pos -= consumed
        }
        srcPos[c] = pos
        return out
    }

    private fun pcm(f: Float): Int =
        (f.coerceIn(-1f, 1f) * 32767f).toInt()

    private fun db2lin(db: Float) = 10.0.pow(db / 20.0).toFloat()

    /**
     * How much a channel's ring-out band is cutting the room's resonance,
     * in dB (0 or negative). The ring-out always notches ON the resonant
     * frequency, band 4, so a cut there really does reduce this mic's loop
     * gain — which is what makes the notch quell the modelled howl, not
     * just log it. Read straight off the console the app is writing to.
     */
    private fun ringBandCutDb(ch: Int): Float {
        val p = console.params
        fun f(a: String) = p["/ch/%02d/$a".format(java.util.Locale.ROOT, ch + 1)]
        val gDb = (f("eq/4/g") ?: return 0f) * 30f - 15f
        if (gDb >= -0.1f) return 0f                         // not a cut
        if ((f("eq/on") ?: 0f) < 0.5f) return 0f            // EQ bypassed
        val fHz = 20f * Math.pow(1000.0,
            (f("eq/4/f") ?: return 0f).toDouble()).toFloat()
        val ratio = fHz / room.freqHz.toFloat()
        // only if the notch is tuned near the resonance (~a tone either way)
        return if (ratio in 0.85f..1.18f) gDb else 0f
    }
}
