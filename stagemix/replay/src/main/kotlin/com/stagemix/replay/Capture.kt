package com.stagemix.replay

import java.io.BufferedInputStream
import java.io.BufferedOutputStream
import java.io.DataInputStream
import java.io.DataOutputStream
import java.io.File
import java.io.FileInputStream
import java.io.FileOutputStream
import java.util.zip.GZIPInputStream
import java.util.zip.GZIPOutputStream

/**
 * A METER TAPE: what the console would have sent, and nothing else.
 *
 * A night recorded off the M18's USB is tens of gigabytes of audio, and
 * none of it is what the engine actually sees. The engine's whole input
 * is sixteen level numbers twenty times a second plus a 100-bin
 * spectrum of one channel at a time. Written at half-dB resolution
 * that is one byte per channel per frame — about a megabyte for a
 * three-hour night, small enough to send anywhere.
 *
 * So the audio never has to leave the machine it was recorded on:
 *
 *     java -jar stagemix-replay.jar <session> --capture night.smcap
 *
 * and `night.smcap` replays through the real engine anywhere, producing
 * the same decisions and the same show log as the audio would.
 *
 * Format (gzipped):
 *   "SMCAP1\n"
 *   header line: sampleRateHz meterHz channelCount
 *   one line per channel: the channel name
 *   then records:
 *     0x01 <int16 t_ms/10> <int8 dB x2 per channel>      level frame
 *     0x02 <int16 t_ms/10> <int8 ch> <int8 dB x2 x100>   RTA frame
 *   dB is clamped to -120..+7 and stored as round(dB*2), so one byte
 *   carries half a dB — finer than the deadband, finer than the fader.
 */
object Capture {
    const val MAGIC = "SMCAP1"
    private const val REC_LEVEL = 1
    private const val REC_RTA = 2

    private fun enc(db: Float): Byte =
        (db.coerceIn(-120f, 7f) * 2f).toInt().coerceIn(-128, 127).toByte()

    private fun dec(b: Byte): Float = b.toFloat() / 2f

    class Writer(file: File, sampleRate: Int, meterHz: Int,
                 names: List<String>) {
        private val out = DataOutputStream(BufferedOutputStream(
            GZIPOutputStream(FileOutputStream(file), 1 shl 16)))
        val channels = names.size
        private val row = ByteArray(channels)
        private val rtaRow = ByteArray(100)
        var levelFrames = 0L; private set
        var rtaFrames = 0L; private set

        init {
            out.write((MAGIC + "\n").toByteArray(Charsets.US_ASCII))
            out.write("$sampleRate $meterHz $channels\n"
                .toByteArray(Charsets.US_ASCII))
            for (n in names)
                out.write((n.replace('\n', ' ') + "\n")
                    .toByteArray(Charsets.US_ASCII))
        }

        fun level(tSec: Double, db: FloatArray) {
            out.writeByte(REC_LEVEL)
            out.writeShort(((tSec * 100).toLong() and 0xFFFF).toInt())
            for (c in 0 until channels) row[c] = enc(db.getOrElse(c) { -128f })
            out.write(row)
            levelFrames++
        }

        fun rta(tSec: Double, ch: Int, bins: FloatArray) {
            out.writeByte(REC_RTA)
            out.writeShort(((tSec * 100).toLong() and 0xFFFF).toInt())
            out.writeByte(ch)
            for (i in 0 until 100) rtaRow[i] = enc(bins.getOrElse(i) { -128f })
            out.write(rtaRow)
            rtaFrames++
        }

        fun close() { out.flush(); out.close() }
    }

    class Tape(
        val sampleRate: Int,
        val meterHz: Int,
        val names: List<String>,
    )

    /**
     * Stream a capture back. [onLevel] and [onRta] are called in the
     * order they were recorded, with the show clock rebuilt from the
     * frame count (the stored stamp only carries the fractional part,
     * which is all that is needed to keep sub-second ordering).
     */
    fun read(file: File,
             onHeader: (Tape) -> Unit,
             onLevel: (Double, FloatArray) -> Unit,
             onRta: (Double, Int, FloatArray) -> Unit) {
        DataInputStream(BufferedInputStream(
            GZIPInputStream(FileInputStream(file), 1 shl 16))).use { inp ->
            fun line(): String {
                val sb = StringBuilder()
                while (true) {
                    val b = inp.read()
                    if (b < 0 || b == '\n'.code) break
                    sb.append(b.toChar())
                }
                return sb.toString()
            }
            require(line() == MAGIC) { "$file is not a StageMix capture" }
            val (sr, hz, n) = line().trim().split(" ").map { it.toInt() }
            val names = (0 until n).map { line() }
            onHeader(Tape(sr, hz, names))

            val db = FloatArray(16) { -128f }
            val bins = FloatArray(100)
            val row = ByteArray(n)
            val rtaRow = ByteArray(100)
            var frames = 0L
            while (true) {
                val kind = inp.read()
                if (kind < 0) break
                inp.readShort()      // stamp: ordering only
                when (kind) {
                    REC_LEVEL -> {
                        inp.readFully(row)
                        for (c in 0 until minOf(n, 16)) db[c] = dec(row[c])
                        onLevel(frames.toDouble() / hz, db)
                        frames++
                    }
                    REC_RTA -> {
                        val ch = inp.read()
                        inp.readFully(rtaRow)
                        for (i in 0 until 100) bins[i] = dec(rtaRow[i])
                        onRta(frames.toDouble() / hz, ch, bins)
                    }
                    else -> throw IllegalStateException(
                        "corrupt capture at frame $frames")
                }
            }
        }
    }
}
