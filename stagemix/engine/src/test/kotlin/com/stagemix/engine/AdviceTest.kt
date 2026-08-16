package com.stagemix.engine

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class AdviceTest {

    private val fine = Situation(
        connected = true, everConnected = true, directing = true,
        balanceKept = true, channelsTotal = 16, channelsMixed = 16,
        wedgesRead = 5, mixingSec = 600.0)

    @Test
    fun `not mixing is a fault, not a note`() {
        val a = adviseOn(fine.copy(directing = false))
        val n = a.first { it.key == "notmixing" }
        assertEquals(Level.FAULT, n.level,
            "three shows went by because this was not a fault")
        assertEquals(a.first(), n, "and it must be the first thing said")
    }

    @Test
    fun `every single message carries something to do`() {
        val situations = listOf(
            fine,
            fine.copy(directing = false),
            fine.copy(connected = false),
            fine.copy(connected = false, connecting = true),
            fine.copy(metersAgeSec = 9f),
            fine.copy(channelsMixed = 9),
            fine.copy(frozenAll = true),
            fine.copy(stageMuted = true),
            fine.copy(hunting = true),
            fine.copy(wedgesRead = 0),
            fine.copy(balanceKept = false),
            fine.copy(doctorOn = false),
            fine.copy(consecutiveErrors = 4, engineError = "boom"),
            fine.copy(wedgesOut = 2, monitorsEnabled = false),
        )
        for (s in situations) {
            val a = adviseOn(s)
            assertTrue(a.isNotEmpty(), "said nothing at all for $s")
            for (x in a) {
                assertTrue(x.what.isNotBlank(), "blank what: ${x.key}")
                assertTrue(x.doThis.isNotBlank(),
                    "no remedy for ${x.key} — a fault without a remedy " +
                    "is just bad news")
                assertTrue(x.doThis.length > 20,
                    "remedy for ${x.key} is too short to help")
            }
        }
    }

    @Test
    fun `worst first`() {
        val a = adviseOn(fine.copy(directing = false, frozenAll = true,
            doctorOn = false))
        val levels = a.map { it.level.ordinal }
        assertEquals(levels.sortedDescending(), levels)
    }

    @Test
    fun `when everything is fine it says so rather than going blank`() {
        val a = adviseOn(fine)
        assertEquals(1, a.size)
        assertEquals("ok", a[0].key)
        assertEquals(Level.NOTE, a[0].level)
    }

    @Test
    fun `a partial takeover is a fault and names the count`() {
        val a = adviseOn(fine.copy(channelsMixed = 9))
        val p = a.first { it.key == "partial" }
        assertEquals(Level.FAULT, p.level)
        assertTrue("9 of 16" in p.what, p.what)
        assertTrue("7" in p.what, p.what)
    }

    @Test
    fun `the remedy for not mixing depends on whether auto-start is on`() {
        val on = adviseOn(fine.copy(directing = false, autoStart = true))
            .first { it.key == "notmixing" }
        val off = adviseOn(fine.copy(directing = false, autoStart = false))
            .first { it.key == "notmixing" }
        assertTrue("should have started by itself" in on.doThis)
        assertTrue("Auto-start is switched off" in off.doThis)
    }

    @Test
    fun `the work bar always has a number to show`() {
        assertEquals(0.5f, holdingWork(8, 16, true).frac)
        assertEquals(0f, holdingWork(0, 0, false).frac)
        assertTrue(holdingWork(3, 4, false).detail.contains("KEEP"))
        assertTrue(holdingWork(3, 4, true).label.contains("kept"))
    }
}
