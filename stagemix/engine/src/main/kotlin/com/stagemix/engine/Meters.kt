package com.stagemix.engine

import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * X-Air meter blob decoder.
 *
 * Unlike the X32 (float32), X-Air meter blobs are: little-endian int32
 * count, then count x little-endian signed int16, each value dB * 256
 * (1/256 dB resolution, floor around -128 dB). Verified against the
 * official protocol doc text and three independent client
 * implementations (bitfocus companion, notameadow/xair-osc,
 * ericdahl-dev live captures).
 */
object Meters {
    /** /meters/1 layout (XR18/MR18): first 16 values = input channels (pre). */
    const val BANK_INPUTS = 1
    const val INPUT_COUNT = 16

    fun decode(blob: ByteArray): FloatArray? {
        if (blob.size < 4) return null
        val buf = ByteBuffer.wrap(blob).order(ByteOrder.LITTLE_ENDIAN)
        val count = buf.int
        if (count < 0 || blob.size < 4 + count * 2) return null
        return FloatArray(count) { buf.short / 256f }
    }
}
