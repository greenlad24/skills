package com.stagemix.engine

import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.Base64

/**
 * Mixing Station desktop metering2 decoder.
 *
 * The MS WebSocket API pushes metering as base64 (non-padded), each
 * value a big-endian signed int16 scaled x100 (1.02 dB -> 102), per the
 * official API docs. Distinct from the mixer's own blob format
 * (little-endian, x256) — decoded by [Meters].
 */
object MsMeters {
    fun decode(b64: String): FloatArray? {
        return try {
            val padded = b64 + "=".repeat((4 - b64.length % 4) % 4)
            val bytes = Base64.getDecoder().decode(padded)
            if (bytes.size < 2) return null
            val buf = ByteBuffer.wrap(bytes).order(ByteOrder.BIG_ENDIAN)
            FloatArray(bytes.size / 2) { buf.short / 100f }
        } catch (e: IllegalArgumentException) {
            null
        }
    }
}
