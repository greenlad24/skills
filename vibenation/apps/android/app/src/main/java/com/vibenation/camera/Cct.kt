package com.vibenation.camera

import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraMetadata
import android.hardware.camera2.params.ColorSpaceTransform
import android.hardware.camera2.params.RggbChannelVector
import kotlin.math.roundToInt

/**
 * Rough colour temperature of the white balance the camera settled on.
 * Camera neutral = 1 / WB gains; XYZ = inverse(XYZ->camera matrix) * neutral; then McCamy's formula.
 * It is an estimate ("≈ 4300 K") good to a few hundred kelvin, enough to compare phones.
 */
object Cct {
    fun pickColorTransform(ch: CameraCharacteristics): DoubleArray? {
        val ill1 = ch.get(CameraCharacteristics.SENSOR_REFERENCE_ILLUMINANT1)
        val m1 = ch.get(CameraCharacteristics.SENSOR_COLOR_TRANSFORM1)
        val m2 = ch.get(CameraCharacteristics.SENSOR_COLOR_TRANSFORM2)
        val d65 = CameraMetadata.SENSOR_REFERENCE_ILLUMINANT1_D65
        val pick = when {
            ill1 == d65 && m1 != null -> m1
            m2 != null -> m2
            else -> m1
        } ?: return null
        return toArray(pick)
    }

    private fun toArray(t: ColorSpaceTransform): DoubleArray =
        DoubleArray(9) { i -> t.getElement(i % 3, i / 3).toDouble() }

    fun kelvinFromGains(g: RggbChannelVector, xyzToCamera: DoubleArray): Int? =
        kelvin(g.red.toDouble(), (g.greenEven + g.greenOdd) / 2.0, g.blue.toDouble(), xyzToCamera)

    /** Pure function (unit-tested): gains + row-major 3x3 XYZ->camera matrix -> kelvin rounded to 100. */
    fun kelvin(r: Double, g: Double, b: Double, m: DoubleArray): Int? {
        if (r <= 0 || g <= 0 || b <= 0 || m.size != 9) return null
        val inv = invert3(m) ?: return null
        val n = doubleArrayOf(g / r, 1.0, g / b)
        val x = inv[0] * n[0] + inv[1] * n[1] + inv[2] * n[2]
        val y = inv[3] * n[0] + inv[4] * n[1] + inv[5] * n[2]
        val z = inv[6] * n[0] + inv[7] * n[1] + inv[8] * n[2]
        val sum = x + y + z
        if (sum <= 0) return null
        return mccamy(x / sum, y / sum)
    }

    fun mccamy(x: Double, y: Double): Int? {
        val d = 0.1858 - y
        if (d == 0.0) return null
        val n = (x - 0.3320) / d
        val k = 449 * n * n * n + 3525 * n * n + 6823.3 * n + 5520.33
        if (k.isNaN() || k < 1500 || k > 15000) return null
        return ((k / 100).roundToInt() * 100)
    }

    fun invert3(m: DoubleArray): DoubleArray? {
        val (a, b, c, d, e, f, g, h, i) = m.toList()
        val det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
        if (det == 0.0) return null
        val k = 1.0 / det
        return doubleArrayOf(
            (e * i - f * h) * k, (c * h - b * i) * k, (b * f - c * e) * k,
            (f * g - d * i) * k, (a * i - c * g) * k, (c * d - a * f) * k,
            (d * h - e * g) * k, (b * g - a * h) * k, (a * e - b * d) * k,
        )
    }

    private operator fun <T> List<T>.component6() = this[5]
    private operator fun <T> List<T>.component7() = this[6]
    private operator fun <T> List<T>.component8() = this[7]
    private operator fun <T> List<T>.component9() = this[8]
}
