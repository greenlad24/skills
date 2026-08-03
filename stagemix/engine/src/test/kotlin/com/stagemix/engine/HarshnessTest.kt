package com.stagemix.engine

import kotlin.test.Test
import kotlin.test.assertTrue

class HarshnessTest {

    /** spectrum with a body level and a 2-6 kHz harsh region level */
    private fun spectrum(body: Float, harsh: Float) = FloatArray(100) { i ->
        when (i) {
            in 26..60 -> body
            in 66..82 -> harsh
            else -> body - 10f
        }
    }

    private fun doctor(role: Role) =
        ToneDoctor(listOf(0), mapOf(0 to role))

    private fun settle(d: ToneDoctor, body: Float, harsh: Float, from: Double,
                       frames: Int = 40): Double {
        var t = from
        repeat(frames) { d.onRta(0, spectrum(body, harsh), t); t += 0.5 }
        return t
    }

    @Test fun `harsh guitar gets its high-mids eased down, capped at 2db`() {
        val d = doctor(Role.SOLO_GTR)
        var t = settle(d, body = -30f, harsh = -30f, from = 0.0)
        d.snapshotChannel(0, floatArrayOf(0f, 0f, 0f, 0f), thrDb = null)
        // amp turns shrill: harsh region 10 dB over the body
        t = settle(d, body = -30f, harsh = -20f, from = t)
        val writes = ArrayList<ParamWrite>()
        repeat(15) { writes.addAll(d.tick(setOf(0), true, false)) }
        val hm = writes.filter { it.address == "/ch/01/eq/3/g" }
        assertTrue(hm.isNotEmpty(), "harsh guitar must be softened")
        // cut-only, capped at -2 from snapshot (0 dB): floor (−2+15)/30
        assertTrue(hm.all { it.value <= (0f + 15f) / 30f + 1e-4f }, "cut-only")
        assertTrue(hm.last().value >= (-2f + 15f) / 30f - 1e-4f, "capped -2")
        // harshness passes -> released back toward snapshot
        t = settle(d, body = -30f, harsh = -30f, from = t)
        val rel = ArrayList<ParamWrite>()
        repeat(15) { rel.addAll(d.tick(setOf(0), true, false)) }
        val back = rel.filter { it.address == "/ch/01/eq/3/g" }
        assertTrue(back.isNotEmpty() &&
                back.last().value > (-1f + 15f) / 30f,
            "guard must release when the harshness passes")
    }

    @Test fun `balanced bright-ish channel is left alone`() {
        val d = doctor(Role.VOCAL)
        var t = settle(d, body = -30f, harsh = -26f, from = 0.0)  // +4 < 6
        d.snapshotChannel(0, floatArrayOf(0f, 0f, 0f, 0f), thrDb = null)
        settle(d, body = -30f, harsh = -26f, from = t)
        val writes = ArrayList<ParamWrite>()
        repeat(10) { writes.addAll(d.tick(setOf(0), true, false)) }
        assertTrue(writes.none { it.address == "/ch/01/eq/3/g" },
            "presence is not harshness — below threshold stays untouched")
    }

    @Test fun `cymbals and kick click are exempt`() {
        for (role in listOf(Role.PERCUSSION, Role.FOUNDATION)) {
            val d = doctor(role)
            var t = settle(d, body = -35f, harsh = -18f, from = 0.0)
            d.snapshotChannel(0, floatArrayOf(0f, 0f, 0f, 0f), thrDb = null)
            settle(d, body = -35f, harsh = -18f, from = t)
            val writes = ArrayList<ParamWrite>()
            repeat(10) { writes.addAll(d.tick(setOf(0), true, false)) }
            assertTrue(writes.none { it.address == "/ch/01/eq/3/g" },
                "$role is naturally bright — guard must not dull it")
        }
    }
}
