package com.vibenation.camera

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test
import kotlin.math.abs

class CctTest {
    @Test fun mccamyD65() { assertEquals(6500.0, Cct.mccamy(0.3127, 0.3290)!!.toDouble(), 100.0) }
    @Test fun mccamyIlluminantA() { assertEquals(2900.0, Cct.mccamy(0.4476, 0.4074)!!.toDouble(), 100.0) }
    @Test fun mccamyRejectsNonsense() { assertNull(Cct.mccamy(0.9, 0.05)) }

    @Test fun invertIdentity() {
        val i = Cct.invert3(doubleArrayOf(1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0))!!
        assertEquals(1.0, i[0], 1e-9); assertEquals(0.0, i[1], 1e-9); assertEquals(1.0, i[8], 1e-9)
    }

    @Test fun invertRoundTrip() {
        val m = doubleArrayOf(2.0, 1.0, 0.0, 0.0, 1.0, 3.0, 1.0, 0.0, 1.0)
        val inv = Cct.invert3(m)!!
        for (r in 0 until 3) for (c in 0 until 3) {
            var s = 0.0
            for (k in 0 until 3) s += m[r * 3 + k] * inv[k * 3 + c]
            assertEquals(if (r == c) 1.0 else 0.0, s, 1e-9)
        }
    }

    @Test fun kelvinFromGainsWithXyzIdentityLikeMatrix() {
        // With camera == XYZ, gains that map the D65 white point to neutral should read ~6500 K.
        val x = 0.3127; val y = 0.3290
        val X = x / y; val Z = (1 - x - y) / y
        val k = Cct.kelvin(1.0 / X, 1.0, 1.0 / Z, doubleArrayOf(1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0))
        assertNotNull(k)
        assert(abs(k!! - 6500) <= 100) { "got $k" }
    }

    @Test fun wifiLabels() {
        assertEquals("Strong", Telemetry.rssiLabel(-50))
        assertEquals("Good", Telemetry.rssiLabel(-65))
        assertEquals("Weak", Telemetry.rssiLabel(-80))
    }
}
