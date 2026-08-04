package com.stagemix.vm18

import java.io.BufferedInputStream
import java.io.File
import java.io.FileInputStream
import java.io.RandomAccessFile
import javax.sound.sampled.AudioFormat
import javax.sound.sampled.AudioInputStream

/**
 * A WAV reader of our own, because `AudioSystem` cannot be trusted to
 * pick one.
 *
 * `AudioSystem.getAudioInputStream(File)` asks every reader on the
 * classpath, in an order nobody specifies, and takes the first that says
 * yes. The mp3 SPI we carry for mp3 playback says yes to almost
 * anything: it scans for an MPEG sync word, and PCM audio is full of
 * byte pairs that look like one. On this machine it was winning against
 * the JDK's own WAV reader for ten of sixteen channels.
 *
 * The damage was not a clean refusal. It reported a 48 kHz kick drum as
 * 12 kHz — an MPEG-2.5 rate, which is the tell — handed back a stream
 * that decoded as MPEG Layer I, and then threw
 * `ArrayIndexOutOfBoundsException` out of the middle of
 * `LayerIDecoder.read_allocation`. That killed the transport thread, and
 * from then on the window said PLAYING while the room stayed silent.
 *
 * So a file that begins with a RIFF or RF64 header is parsed here, by
 * hand, and never offered to the guessing. It is not much code: the
 * bench needs uncompressed PCM and nothing else, which is all a DAW
 * writes anyway. Anything that is genuinely compressed — an actual mp3 —
 * falls through to `AudioSystem`, where the SPI belongs.
 *
 * Handles RIFF and RF64 (the >4 GB form a long recording produces),
 * WAVE_FORMAT_EXTENSIBLE, integer and float samples, and chunks in any
 * order with the odd-byte padding the spec requires and some writers
 * forget.
 */
object WavFile {

    /** the stream, or null if this is not a RIFF/RF64 WAVE we can read */
    fun open(f: File): AudioInputStream? {
        val h = header(f) ?: return null
        val fis = FileInputStream(f)
        var skip = h.dataOffset
        while (skip > 0) {
            val k = fis.skip(skip)
            if (k <= 0) { fis.close(); return null }
            skip -= k
        }
        return AudioInputStream(BufferedInputStream(fis, 1 shl 16),
            h.format, h.frames)
    }

    /** what a file says about itself, for the log */
    fun describe(f: File): String? =
        header(f)?.let {
            "%.0f Hz, %d bit%s, %d ch".format(java.util.Locale.ROOT,
                it.format.sampleRate, it.format.sampleSizeInBits,
                if (it.format.encoding == AudioFormat.Encoding.PCM_FLOAT)
                    " float" else "",
                it.format.channels)
        }

    private class Head(val format: AudioFormat, val dataOffset: Long,
                       val frames: Long)

    private fun header(f: File): Head? {
        if (f.length() < 16) return null
        try {
            RandomAccessFile(f, "r").use { r ->
                val magic = ByteArray(12)
                r.readFully(magic)
                val riff = String(magic, 0, 4, Charsets.US_ASCII)
                val wave = String(magic, 8, 4, Charsets.US_ASCII)
                if (riff != "RIFF" && riff != "RF64") return null
                if (wave != "WAVE") return null

                var channels = 0
                var rate = 0
                var bits = 0
                var blockAlign = 0
                var isFloat = false
                var haveFmt = false
                var dataOffset = -1L
                var dataLen = -1L
                var ds64DataLen = -1L

                val end = f.length()
                var pos = 12L
                while (pos + 8 <= end) {
                    r.seek(pos)
                    val idb = ByteArray(4)
                    r.readFully(idb)
                    val id = String(idb, Charsets.US_ASCII)
                    val size = u32(r)
                    val body = pos + 8

                    when (id) {
                        // RF64 keeps the real 64-bit lengths out here,
                        // because the RIFF fields cannot hold them
                        "ds64" -> if (size >= 16) {
                            r.seek(body + 8); ds64DataLen = i64(r)
                        }
                        "fmt " -> if (size >= 16) {
                            r.seek(body)
                            var tag = u16(r)
                            channels = u16(r)
                            rate = u32(r).toInt()
                            u32(r)                       // byte rate
                            blockAlign = u16(r)
                            bits = u16(r)
                            // EXTENSIBLE hides the real tag in the GUID
                            if (tag == 0xFFFE && size >= 40) {
                                r.seek(body + 24); tag = u16(r)
                            }
                            when (tag) {
                                1 -> isFloat = false
                                3 -> isFloat = true
                                else -> return null      // compressed
                            }
                            haveFmt = true
                        }
                        "data" -> {
                            dataOffset = body
                            // 0xFFFFFFFF means "look in ds64"
                            dataLen = if (size == 0xFFFFFFFFL) ds64DataLen
                                      else size
                        }
                    }
                    if (id == "data") break
                    // chunks are padded to an even length
                    pos = body + size + (size and 1L)
                    if (size <= 0L) break                // a malformed chunk
                }

                if (!haveFmt || dataOffset < 0) return null
                if (channels <= 0 || rate <= 0 || bits <= 0) return null
                val frameSize =
                    if (blockAlign > 0) blockAlign else channels * ((bits + 7) / 8)
                if (frameSize <= 0) return null

                // A file still being written, or one whose header lies,
                // must be read to where the bytes actually stop.
                val avail = end - dataOffset
                val useLen = if (dataLen in 1..avail) dataLen else avail
                val frames = useLen / frameSize
                if (frames <= 0) return null

                val enc = when {
                    isFloat -> AudioFormat.Encoding.PCM_FLOAT
                    bits == 8 -> AudioFormat.Encoding.PCM_UNSIGNED
                    else -> AudioFormat.Encoding.PCM_SIGNED
                }
                return Head(AudioFormat(enc, rate.toFloat(), bits, channels,
                    frameSize, rate.toFloat(), false), dataOffset, frames)
            }
        } catch (e: Exception) {
            return null          // unreadable as a WAV; let the SPI try
        }
    }

    private fun u16(r: RandomAccessFile): Int {
        val a = r.read(); val b = r.read()
        if (a < 0 || b < 0) return 0
        return a or (b shl 8)
    }

    private fun u32(r: RandomAccessFile): Long {
        val a = r.read(); val b = r.read(); val c = r.read(); val d = r.read()
        if (a < 0 || b < 0 || c < 0 || d < 0) return 0
        return (a.toLong() or (b.toLong() shl 8) or (c.toLong() shl 16) or
            (d.toLong() shl 24))
    }

    private fun i64(r: RandomAccessFile): Long {
        var v = 0L
        for (i in 0 until 8) {
            val k = r.read()
            if (k < 0) return v
            v = v or (k.toLong() shl (8 * i))
        }
        return v
    }
}
