package com.stagemix.engine

import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.Locale

/**
 * Build an OSC address. Every address in this app is built with `%02d`
 * channel numbers, and `String.format` follows `Locale.getDefault()` —
 * so on a tablet set to Arabic, Persian, Bengali, Burmese, Nepali or
 * Thai-native-digits, `/ch/02/mix/fader` came out as `/ch/٠٢/mix/fader`,
 * which the ASCII encoder then turned into `/ch/??/mix/fader`. All 16
 * channels collapsed onto one address the console silently drops: the
 * autopilot would look perfectly healthy and never move a fader.
 * Addresses are wire protocol, so they are always formatted in ROOT.
 */
fun osc(format: String, vararg args: Any): String =
    String.format(Locale.ROOT, format, *args)

/**
 * Minimal OSC 1.0 codec for the X-Air / M-Air dialect.
 *
 * Hand-rolled on purpose: the mixer does not support bundles, uses only
 * i/f/s/b argument types, and its meter replies carry a vendor-specific
 * binary blob — a full OSC library buys nothing here. Everything is
 * covered by unit tests against byte fixtures.
 */
data class OscMessage(val address: String, val args: List<Any>) {

    fun intArg(i: Int): Int? = args.getOrNull(i) as? Int
    fun floatArg(i: Int): Float? = args.getOrNull(i) as? Float
    fun stringArg(i: Int): String? = args.getOrNull(i) as? String
    fun blobArg(i: Int): ByteArray? = args.getOrNull(i) as? ByteArray

    fun encode(): ByteArray {
        val out = ArrayList<Byte>(64)
        out.addPaddedString(address)
        val tags = StringBuilder(",")
        for (a in args) tags.append(
            when (a) {
                is Int -> 'i'
                is Float -> 'f'
                is String -> 's'
                is ByteArray -> 'b'
                else -> throw IllegalArgumentException(
                    "unsupported OSC arg type: ${a::class}")
            })
        out.addPaddedString(tags.toString())
        for (a in args) when (a) {
            is Int -> out.addAll(ByteBuffer.allocate(4).putInt(a).array().toList())
            is Float -> out.addAll(ByteBuffer.allocate(4).putFloat(a).array().toList())
            is String -> out.addPaddedString(a)
            is ByteArray -> {
                out.addAll(ByteBuffer.allocate(4).putInt(a.size).array().toList())
                out.addAll(a.toList())
                repeat((4 - a.size % 4) % 4) { out.add(0) }
            }
        }
        return out.toByteArray()
    }

    companion object {
        fun decode(data: ByteArray): OscMessage? {
            try {
                val buf = ByteBuffer.wrap(data).order(ByteOrder.BIG_ENDIAN)
                val address = buf.readPaddedString() ?: return null
                if (!address.startsWith("/")) return null
                if (!buf.hasRemaining()) return OscMessage(address, emptyList())
                val tags = buf.readPaddedString() ?: return OscMessage(address, emptyList())
                if (!tags.startsWith(",")) return OscMessage(address, emptyList())
                val args = ArrayList<Any>(tags.length - 1)
                for (t in tags.drop(1)) when (t) {
                    'i' -> args.add(buf.int)
                    'f' -> args.add(buf.float)
                    's' -> args.add(buf.readPaddedString() ?: return null)
                    'b' -> {
                        val n = buf.int
                        if (n < 0 || n > buf.remaining()) return null
                        val blob = ByteArray(n)
                        buf.get(blob)
                        buf.position(buf.position() + (4 - n % 4) % 4)
                        args.add(blob)
                    }
                    else -> return null // unknown tag: refuse rather than misparse
                }
                return OscMessage(address, args)
            } catch (e: Exception) {
                return null
            }
        }

        private fun ByteBuffer.readPaddedString(): String? {
            val start = position()
            var terminated = false
            while (hasRemaining()) if (get() == 0.toByte()) { terminated = true; break }
            // An OSC string MUST be null-terminated. Treating the last
            // byte of a truncated packet as the terminator silently
            // invents a shorter address — refuse instead of misparsing.
            if (!terminated) return null
            val end = position() - 1
            if (end < start) return null
            val bytes = ByteArray(end - start)
            position(start); get(bytes); get() // consume terminator
            // skip padding to 4-byte boundary (terminator included in count)
            val consumed = (end - start) + 1
            position(start + consumed + (4 - consumed % 4) % 4)
            return String(bytes, Charsets.US_ASCII)
        }

        private fun ArrayList<Byte>.addPaddedString(s: String) {
            val b = s.toByteArray(Charsets.US_ASCII)
            addAll(b.toList())
            add(0)
            repeat((4 - (b.size + 1) % 4) % 4) { add(0) }
        }
    }
}
