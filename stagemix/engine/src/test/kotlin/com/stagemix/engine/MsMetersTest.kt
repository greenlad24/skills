package com.stagemix.engine

import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.Base64
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class MsMetersTest {
    private fun b64(vararg db: Float): String {
        val buf = ByteBuffer.allocate(db.size * 2).order(ByteOrder.BIG_ENDIAN)
        for (v in db) buf.putShort((v * 100f).toInt().toShort())
        return Base64.getEncoder().withoutPadding().encodeToString(buf.array())
    }

    @Test fun `decodes big-endian int16 db x100 without padding`() {
        val out = MsMeters.decode(b64(1.02f, -12.5f, -80f))!!
        assertEquals(3, out.size)
        assertEquals(1.02f, out[0], 0.01f)
        assertEquals(-12.5f, out[1], 0.01f)
        assertEquals(-80f, out[2], 0.01f)
    }

    @Test fun `garbage returns null not crash`() {
        assertNull(MsMeters.decode("!!not-base64!!"))
        assertNull(MsMeters.decode(""))   // fewer than one value -> null
    }
}
