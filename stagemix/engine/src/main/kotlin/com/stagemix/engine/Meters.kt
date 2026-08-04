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
    /**
     * `/meters/1` on an XR18/MR18 returns 40 values:
     *   16 mono channels (pre) · 5x2 fx/aux returns · 6 buses ·
     *   4 fx sends (all pre) · 2 stereo (post) · 2 monitor.
     * The first 16 are the input strips, pre-fader — which is what the
     * engine steers against: it hears the true source regardless of its
     * own moves.
     */
    const val BANK_INPUTS = 1
    const val INPUT_COUNT = 16

    /** `/meters/4`: the 100-bin RTA of whatever `/-stat/rta/source` selects. */
    const val BANK_RTA = 4
    const val RTA_BINS = 100

    /**
     * `/meters/6` returns 39 values, in BLOCKS, not interleaved:
     *   [0..15]  channel GATE gain reduction
     *   [16..31] channel COMPRESSOR gain reduction
     *   [32..37] bus compressor gain reduction
     *   [38]     main compressor gain reduction
     * This app had it as interleaved [gate, comp] pairs, which read
     * channel 2's gate as channel 1's compressor.
     */
    const val BANK_DYNAMICS = 6
    const val DYN_COUNT = 39

    /** index of channel [ch]'s COMPRESSOR gain reduction in `/meters/6` */
    fun compGrIndex(ch: Int): Int = INPUT_COUNT + ch

    /** index of channel [ch]'s GATE gain reduction in `/meters/6` */
    fun gateGrIndex(ch: Int): Int = ch

    fun decode(blob: ByteArray): FloatArray? {
        if (blob.size < 4) return null
        val buf = ByteBuffer.wrap(blob).order(ByteOrder.LITTLE_ENDIAN)
        val count = buf.int
        // count * 2 overflows for hostile/huge values -> compare in Long
        if (count < 0 || blob.size.toLong() < 4L + count.toLong() * 2L)
            return null
        return FloatArray(count) { buf.short / 256f }
    }
}
