package com.stagemix.engine

import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.abs
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

class OscCodecTest {
    @Test fun `roundtrip int float string`() {
        val m = OscMessage("/ch/01/mix/01/level", listOf(3, 0.75f, "hi"))
        val d = OscMessage.decode(m.encode())!!
        assertEquals(m.address, d.address)
        assertEquals(3, d.intArg(0))
        assertEquals(0.75f, d.floatArg(1))
        assertEquals("hi", d.stringArg(2))
    }

    @Test fun `roundtrip blob with padding`() {
        val blob = byteArrayOf(1, 2, 3, 4, 5) // 5 bytes -> 3 pad bytes
        val m = OscMessage("/meters/1", listOf(blob))
        val d = OscMessage.decode(m.encode())!!
        assertTrue(blob.contentEquals(d.blobArg(0)!!))
    }

    @Test fun `no-arg message like xremote`() {
        val enc = OscMessage("/xremote", emptyList()).encode()
        assertEquals(0, enc.size % 4)
        val d = OscMessage.decode(enc)!!
        assertEquals("/xremote", d.address)
        assertTrue(d.args.isEmpty())
    }

    @Test fun `meters subscribe encoding matches wire format`() {
        // /meters ,s /meters/1 — the canonical X-Air subscription
        val enc = OscMessage("/meters", listOf("/meters/1")).encode()
        assertEquals(0, enc.size % 4)
        val d = OscMessage.decode(enc)!!
        assertEquals("/meters/1", d.stringArg(0))
    }

    @Test fun `garbage does not crash`() {
        assertNull(OscMessage.decode(byteArrayOf()))
        assertNull(OscMessage.decode("not osc".toByteArray()))
        OscMessage.decode(ByteArray(64) { it.toByte() }) // must not throw
    }
}

class FaderLawTest {
    @Test fun `NaN and infinities never propagate`() {
        for (bad in listOf(Float.NaN, Float.POSITIVE_INFINITY,
                           Float.NEGATIVE_INFINITY)) {
            val db = FaderLaw.floatToDb(bad)
            assertTrue(db.isFinite(), "floatToDb($bad) = $db")
            val f = FaderLaw.dbToFloat(bad)
            assertTrue(f.isFinite() && f in 0f..1f, "dbToFloat($bad) = $f")
        }
    }

    @Test fun `known anchor points`() {
        // From the Maillot piecewise law: f=1.0 -> +10, 0.75 -> 0 dB,
        // 0.5 -> -10, 0.25 -> -30, 0.0625 -> -60, 0 -> -90
        assertEquals(10f, FaderLaw.floatToDb(1f), 0.01f)
        assertEquals(0f, FaderLaw.floatToDb(0.75f), 0.01f)
        assertEquals(-10f, FaderLaw.floatToDb(0.5f), 0.01f)
        assertEquals(-30f, FaderLaw.floatToDb(0.25f), 0.01f)
        assertEquals(-60f, FaderLaw.floatToDb(0.0625f), 0.01f)
        assertEquals(-90f, FaderLaw.floatToDb(0f), 0.01f)
    }

    @Test fun `inverse within a fader step everywhere`() {
        var f = 0f
        while (f <= 1f) {
            val back = FaderLaw.dbToFloat(FaderLaw.floatToDb(f))
            assertTrue(abs(back - f) < 1f / 1024f + 1e-4f,
                "roundtrip broke at f=$f -> $back")
            f += 0.001f
        }
    }
}

class MetersTest {
    private fun blob(vararg db: Float): ByteArray {
        val buf = ByteBuffer.allocate(4 + db.size * 2).order(ByteOrder.LITTLE_ENDIAN)
        buf.putInt(db.size)
        for (v in db) buf.putShort((v * 256f).toInt().toShort())
        return buf.array()
    }

    @Test fun `decodes little-endian int16 db x256`() {
        val out = Meters.decode(blob(-12.5f, 0f, -80f))!!
        assertEquals(3, out.size)
        assertEquals(-12.5f, out[0], 0.01f)
        assertEquals(0f, out[1], 0.01f)
        assertEquals(-80f, out[2], 0.01f)
    }

    @Test fun `rejects truncated blob`() {
        val b = blob(-10f, -20f).copyOf(5)
        assertNull(Meters.decode(b))
        assertNull(Meters.decode(byteArrayOf(1, 2)))
    }
}
