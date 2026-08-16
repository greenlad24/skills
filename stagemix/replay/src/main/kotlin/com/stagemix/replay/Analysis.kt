package com.stagemix.replay

import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.ln
import kotlin.math.log10
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * Turns recorded audio back into the numbers the console would have
 * sent, so the real engine sees the same inputs it would see live:
 *
 *  · a per-channel level, 20x a second, in dBFS — `/meters/1`
 *  · a 100-bin log-spaced RTA of one channel at a time — `/meters/4`
 *
 * The console's meters are not raw RMS: they rise fast and fall slowly,
 * like any programme meter. Replaying a raw block RMS would make the
 * engine see a far spikier stage than it ever does live, so the same
 * ballistics are applied here (fast attack, ~300 ms release).
 */
class LevelMeter(private val sampleRate: Int) {
    private var env = 0f
    private val atk = 1f - kotlin.math.exp(-1.0 / (0.010 * sampleRate)).toFloat()
    private val rel = 1f - kotlin.math.exp(-1.0 / (0.300 * sampleRate)).toFloat()

    /** feed a block, return the level in dBFS at the end of it */
    fun push(x: FloatArray, n: Int): Float {
        for (i in 0 until n) {
            val a = kotlin.math.abs(x[i])
            env += (if (a > env) atk else rel) * (a - env)
        }
        return if (env <= 1e-7f) -128f else (20.0 * log10(env.toDouble())).toFloat()
    }
}

/**
 * The console's RTA: 100 bins, 10 per octave, 20 Hz to 20 kHz, values in
 * dB. Built from a windowed FFT of a short capture of one channel.
 */
class Rta(private val sampleRate: Int, val fftSize: Int = 4096) {
    private val re = DoubleArray(fftSize)
    private val im = DoubleArray(fftSize)
    private val win = DoubleArray(fftSize) {
        0.5 - 0.5 * cos(2.0 * PI * it / (fftSize - 1))
    }
    private val buf = FloatArray(fftSize)
    private var have = 0

    /** returns a 100-bin spectrum once enough samples have arrived */
    fun push(x: FloatArray, n: Int): FloatArray? {
        var i = 0
        while (i < n) {
            val take = min(fftSize - have, n - i)
            System.arraycopy(x, i, buf, have, take)
            have += take; i += take
            if (have == fftSize) { have = 0; return spectrum() }
        }
        return null
    }

    private fun spectrum(): FloatArray {
        for (k in 0 until fftSize) { re[k] = buf[k] * win[k]; im[k] = 0.0 }
        fft(re, im)
        val bins = FloatArray(100) { -128f }
        val binHz = sampleRate.toDouble() / fftSize
        // 100 log-spaced bands: centre_i = 20 Hz * 2^(i/10)
        val acc = DoubleArray(100)
        val cnt = IntArray(100)
        for (k in 1 until fftSize / 2) {
            val hz = k * binHz
            if (hz < 20.0 || hz > 20000.0) continue
            val idx = (10.0 * (ln(hz / 20.0) / ln(2.0))).toInt()
            if (idx !in 0..99) continue
            val p = re[k] * re[k] + im[k] * im[k]
            acc[idx] += p; cnt[idx]++
        }
        for (b in 0 until 100) {
            if (cnt[b] == 0) { bins[b] = -128f; continue }
            // The ENERGY in the band, not the average of its FFT bins. A
            // 1/10-octave band up at 2 kHz spans thirty FFT bins, so
            // averaging buried a pure tone 15 dB under its real level —
            // which is exactly how a howl hides from an analyzer.
            val rms = sqrt(acc[b]) * 2.0 / fftSize
            bins[b] = if (rms <= 1e-9) -128f
                      else max(-128.0, 20.0 * log10(rms)).toFloat()
        }
        return bins
    }

    /** in-place radix-2 FFT; [re]/[im] length must be a power of two */
    private fun fft(re: DoubleArray, im: DoubleArray) {
        val n = re.size
        var j = 0
        for (i in 1 until n) {
            var bit = n shr 1
            while (j and bit != 0) { j = j xor bit; bit = bit shr 1 }
            j = j or bit
            if (i < j) {
                var t = re[i]; re[i] = re[j]; re[j] = t
                t = im[i]; im[i] = im[j]; im[j] = t
            }
        }
        var len = 2
        while (len <= n) {
            val ang = -2.0 * PI / len
            val wr = cos(ang); val wi = sin(ang)
            var i = 0
            while (i < n) {
                var cr = 1.0; var ci = 0.0
                for (k in 0 until len / 2) {
                    val ur = re[i + k]; val ui = im[i + k]
                    val vr = re[i + k + len / 2] * cr - im[i + k + len / 2] * ci
                    val vi = re[i + k + len / 2] * ci + im[i + k + len / 2] * cr
                    re[i + k] = ur + vr; im[i + k] = ui + vi
                    re[i + k + len / 2] = ur - vr; im[i + k + len / 2] = ui - vi
                    val ncr = cr * wr - ci * wi
                    ci = cr * wi + ci * wr; cr = ncr
                }
                i += len
            }
            len = len shl 1
        }
    }
}

/** integrated loudness-ish measure of a rendered mix, for the summary */
class MixStats {
    private var sum = 0.0
    private var n = 0L
    private var peak = 0f

    fun push(l: FloatArray, r: FloatArray, count: Int) {
        for (i in 0 until count) {
            val m = (l[i] + r[i]) * 0.5f
            sum += m.toDouble() * m; n++
            val a = max(kotlin.math.abs(l[i]), kotlin.math.abs(r[i]))
            if (a > peak) peak = a
        }
    }

    fun rmsDb(): Float =
        // sum==0 is pure digital silence; log10(0) is -Infinity, which
        // then poisons every average and diff it feeds. Floor it like
        // peakDb does, so silence reads as the floor, not -oo.
        if (n == 0L || sum <= 0.0) -128f else (10.0 * log10(sum / n)).toFloat()

    fun peakDb(): Float =
        if (peak <= 0f) -128f else (20.0 * log10(peak.toDouble())).toFloat()
}
