package com.stagemix.replay

import java.io.BufferedOutputStream
import java.io.File
import java.io.FileOutputStream
import java.io.OutputStream
import javax.sound.sampled.AudioFormat
import javax.sound.sampled.AudioInputStream
import javax.sound.sampled.AudioSystem

/**
 * Streaming WAV I/O for the replay tool.
 *
 * A night recorded off the M18's USB is 16 tracks of 24-bit audio for
 * hours — tens of gigabytes. Nothing here ever holds a whole take in
 * memory: reads and writes are block at a time.
 *
 * Handles what a DAW actually exports: 16/24/32-bit PCM and 32-bit
 * float, mono or interleaved multichannel, little-endian.
 */
class WavReader(val file: File) {
    private val ais: AudioInputStream = AudioSystem.getAudioInputStream(file)
    private val fmt: AudioFormat = ais.format
    val channels: Int = fmt.channels
    val sampleRate: Int = fmt.sampleRate.toInt()
    private val bytesPerSample = fmt.sampleSizeInBits / 8
    private val frameBytes = bytesPerSample * channels
    private val isFloat = fmt.encoding == AudioFormat.Encoding.PCM_FLOAT
    private val bigEndian = fmt.isBigEndian
    private var raw = ByteArray(0)

    init {
        require(bytesPerSample in 2..4) {
            "${file.name}: ${fmt.sampleSizeInBits}-bit is not supported " +
            "(export 16, 24 or 32 bit PCM, or 32-bit float)"
        }
    }

    /**
     * Read up to [frames] frames into [out] as floats in -1..1.
     * `out[c][i]` is channel c, frame i. Returns frames actually read.
     */
    fun read(out: Array<FloatArray>, frames: Int): Int {
        val want = frames * frameBytes
        if (raw.size < want) raw = ByteArray(want)
        var got = 0
        while (got < want) {
            val n = ais.read(raw, got, want - got)
            if (n <= 0) break
            got += n
        }
        val n = got / frameBytes
        for (i in 0 until n) {
            var p = i * frameBytes
            for (c in 0 until channels) {
                out[c][i] = sample(p)
                p += bytesPerSample
            }
        }
        return n
    }

    private fun sample(p: Int): Float {
        if (isFloat) {
            val bits = if (bigEndian)
                (raw[p].toInt() and 255 shl 24) or (raw[p + 1].toInt() and 255 shl 16) or
                (raw[p + 2].toInt() and 255 shl 8) or (raw[p + 3].toInt() and 255)
            else
                (raw[p + 3].toInt() and 255 shl 24) or (raw[p + 2].toInt() and 255 shl 16) or
                (raw[p + 1].toInt() and 255 shl 8) or (raw[p].toInt() and 255)
            return Float.fromBits(bits)
        }
        // signed PCM, sign-extended from the top byte
        var v = 0
        if (bigEndian) {
            v = raw[p].toInt()                      // sign-extends
            for (k in 1 until bytesPerSample) v = (v shl 8) or (raw[p + k].toInt() and 255)
        } else {
            v = raw[p + bytesPerSample - 1].toInt()
            for (k in bytesPerSample - 2 downTo 0) v = (v shl 8) or (raw[p + k].toInt() and 255)
        }
        val full = 1 shl (bytesPerSample * 8 - 1)
        return v.toFloat() / full
    }

    fun close() = ais.close()
}

/** 24-bit stereo WAV writer — what the rendered mixes are written as. */
class WavWriter(file: File, private val sampleRate: Int,
                private val channels: Int = 2) {
    private val out: OutputStream = BufferedOutputStream(
        FileOutputStream(file), 1 shl 18)
    private var frames = 0L
    private val raf = file

    init { header(0) }

    private fun header(dataBytes: Int) {
        val bps = 3
        val byteRate = sampleRate * channels * bps
        val b = java.io.ByteArrayOutputStream()
        fun s(t: String) = b.write(t.toByteArray(Charsets.US_ASCII))
        fun i32(v: Int) { for (k in 0 until 4) b.write((v ushr (8 * k)) and 255) }
        fun i16(v: Int) { for (k in 0 until 2) b.write((v ushr (8 * k)) and 255) }
        s("RIFF"); i32(36 + dataBytes); s("WAVE")
        s("fmt "); i32(16); i16(1); i16(channels); i32(sampleRate)
        i32(byteRate); i16(channels * bps); i16(bps * 8)
        s("data"); i32(dataBytes)
        out.write(b.toByteArray())
    }

    fun write(l: FloatArray, r: FloatArray, n: Int) {
        for (i in 0 until n) {
            put(l[i]); if (channels > 1) put(r[i])
        }
        frames += n
    }

    private fun put(f: Float) {
        val v = (f.coerceIn(-1f, 1f) * 8_388_607f).toInt()
        out.write(v and 255); out.write((v ushr 8) and 255)
        out.write((v ushr 16) and 255)
    }

    /** close and patch the RIFF sizes now that the length is known */
    fun close() {
        out.flush(); out.close()
        val dataBytes = (frames * channels * 3).toInt()
        java.io.RandomAccessFile(raf, "rw").use { f ->
            f.seek(4); f.write(le32(36 + dataBytes))
            f.seek(40); f.write(le32(dataBytes))
        }
    }

    private fun le32(v: Int) = byteArrayOf(
        (v and 255).toByte(), ((v ushr 8) and 255).toByte(),
        ((v ushr 16) and 255).toByte(), ((v ushr 24) and 255).toByte())
}
