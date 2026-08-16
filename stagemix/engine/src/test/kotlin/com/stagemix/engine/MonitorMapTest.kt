package com.stagemix.engine

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Reading the wedges.
 *
 * "It needs to understand the current balance of each monitor
 * separately... in yesterday's show we had 3 front monitors and 2
 * in-ears that had a completely different balance."
 *
 * Understanding is all this does. Every test that matters here is a
 * test that it wrote nothing — monitors are the band's ears, a wedge
 * send is the single loudest cause of feedback on any stage, and the
 * first version of anything that touches them should be one that
 * cannot.
 */
class MonitorMapTest {

    private val roles = mapOf(
        0 to Role.FOUNDATION,      // kick
        1 to Role.PERCUSSION,      // snare
        2 to Role.PERCUSSION,      // overheads
        3 to Role.RHYTHM_GTR,      // DI 1 — the acoustic guitar
        4 to Role.SOLO_GTR,        // guitar amp
        5 to Role.KEYS, 6 to Role.KEYS,
        8 to Role.VOCAL,           // centre vocal
        9 to Role.BACKING_VOCAL,
        11 to Role.FOUNDATION,     // bass DI
        12 to Role.PERCUSSION,     // congas
        13 to Role.FOUNDATION,     // DI 2
        14 to Role.COLOR)

    private fun stage(m: MonitorMap, bus: Int, name: String,
                      sends: Map<Int, Float>) {
        m.onBusName(bus, name)
        for ((ch, db) in sends) m.onSend(bus, ch, db)
    }

    // ------------------------------------------------------------------
    @Test fun `a wedge is read for what the engineer called it`() {
        val m = MonitorMap()
        // the names off this rig's own desk
        assertEquals(MonitorMap.Kind.CENTRE_VOCAL, m.kindOf("CENTER MON", 1))
        assertEquals(MonitorMap.Kind.DRUM_IEM, m.kindOf("DRUM IEM", 3))
        assertEquals(MonitorMap.Kind.PLAYER_IEM, m.kindOf("IN EAR 2", 6))
        assertEquals(MonitorMap.Kind.BASS, m.kindOf("BASS MON", 4))
        // "the guitar monitor, which is called piano monitor" — the
        // engineer's label wins, because they are the only person who
        // knows, and no amount of listening would work this one out
        assertEquals(MonitorMap.Kind.GUITAR, m.kindOf("PIANO MON", 2))
    }

    @Test fun `the singer's wedge wants voices and not the drum kit`() {
        val m = MonitorMap()
        stage(m, 1, "CENTER MON", mapOf(
            0 to -6f,      // kick — should not be in a wedge at all
            1 to -10f,     // snare — likewise
            8 to -14f,     // the singer's own mic, far too quiet
            9 to -18f,
            3 to -20f,     // the acoustic guitar he plays
            4 to -12f, 5 to -16f, 11 to -14f))
        val notes = m.critique(1, roles, kit = setOf(0, 1, 2))
        println(notes.joinToString("\n") {
            "ch%02d %-14s now %+.1f want %s off %+.1f".format(
                it.ch + 1, it.role, it.nowDb,
                it.wantDb?.let { w -> "%+.1f".format(w) } ?: "not here",
                it.offDb) })

        val kick = notes.first { it.ch == 0 }
        assertTrue(kick.wantDb == null,
            "a drum kit three feet away does not belong in a wedge")
        val vox = notes.first { it.ch == 8 }
        assertTrue(vox.offDb < -3f,
            "the singer is under his own monitor mix: ${vox.offDb}")
        val gtr = notes.first { it.ch == 3 }
        assertTrue(gtr.wantDb != null && gtr.wantDb!! > vox.wantDb!! - 8f,
            "the acoustic he is playing wants to be audible too")
    }

    @Test fun `an in-ear is a whole mix with one thing on top`() {
        val m = MonitorMap()
        stage(m, 3, "DRUM IEM", mapOf(
            0 to -6f, 1 to -8f, 2 to -12f,      // his own kit, on top
            8 to -16f, 4 to -20f, 11 to -14f))  // and everything else under
        val notes = m.critique(3, roles, kit = setOf(0, 1, 2))
        assertTrue(notes.none { it.wantDb == null },
            "an in-ear has no exclusions: the drummer needs everything")
        val snare = notes.first { it.ch == 1 }
        val gtr = notes.first { it.ch == 4 }
        assertTrue(snare.wantDb!! > gtr.wantDb!!,
            "the drummer's ears want the drums above the guitar")
    }

    @Test fun `the bass player wants the congas, not the whole kit`() {
        val m = MonitorMap()
        stage(m, 4, "BASS MON", mapOf(
            11 to -10f, 13 to -12f, 12 to -18f,
            0 to -8f, 1 to -12f, 8 to -16f, 4 to -18f))
        val notes = m.critique(4, roles, kit = setOf(0, 1, 2))
        val congas = notes.first { it.ch == 12 }
        assertTrue(notes.none { it.ch == 0 && it.wantDb != null },
            "the kick is three feet from the bass player's head")
        assertTrue(congas.wantDb != null,
            "congas are the part of the kit that is not next to him")
        // both are PERCUSSION to the engine, so this is honest about
        // what it cannot yet tell apart
        println("congas want ${congas.wantDb} in the bass wedge")
        val bass = notes.first { it.ch == 11 }
        assertTrue(bass.wantDb!! > congas.wantDb!!,
            "and his own instrument on top of both")
    }

    @Test fun `an unnamed bus is left completely alone`() {
        val m = MonitorMap()
        stage(m, 5, "Bus 5", mapOf(0 to -6f, 8 to -10f, 4 to -12f))
        assertTrue(m.critique(5, roles).isEmpty(),
            "a monitor nobody named is a monitor nobody understands")
    }

    @Test fun `a wedge with almost nothing in it is not judged`() {
        val m = MonitorMap()
        stage(m, 2, "PIANO MON", mapOf(4 to -10f, 8 to -14f))
        assertTrue(m.critique(2, roles).isEmpty(),
            "two sends is not a monitor mix to have an opinion about")
    }

    @Test fun `it says what is in each wedge in one line`() {
        val m = MonitorMap()
        stage(m, 2, "PIANO MON", mapOf(
            4 to -6f, 8 to -10f, 5 to -14f, 0 to -30f, 11 to -16f))
        val line = m.describe(2, mapOf(4 to "GUITAR AMP", 8 to "VOCAL CEN"))
        println(line)
        assertTrue("PIANO MON" in line && "GUITAR" in line,
            "the line has to name the wedge and what is loudest: $line")
    }
}
