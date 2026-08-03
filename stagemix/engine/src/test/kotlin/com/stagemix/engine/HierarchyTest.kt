package com.stagemix.engine

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Balance-ladder scenarios for the user's actual band: foundation
 * (kick + bass) dominant, then piano, rhythm gtr, solo gtr, color
 * (sax/harmonica), backing vox, main vocal on top — plus congas.
 */
class HierarchyTest {

    // ch: 0 kick, 1 bass, 2 piano, 3 rhythm, 4 solo, 5 vocal, 6 bvox,
    //     7 sax, 8 congas
    private val chans = listOf(
        ChannelConfig(0, "Kick", Role.FOUNDATION),
        ChannelConfig(1, "Bass", Role.FOUNDATION),
        ChannelConfig(2, "Piano", Role.KEYS),
        ChannelConfig(3, "Rhythm Gtr", Role.RHYTHM_GTR),
        ChannelConfig(4, "Solo Gtr", Role.SOLO_GTR),
        ChannelConfig(5, "Lead Vox", Role.VOCAL),
        ChannelConfig(6, "BVox", Role.BACKING_VOCAL),
        ChannelConfig(7, "Sax", Role.COLOR),
        ChannelConfig(8, "Congas", Role.PERCUSSION),
    )
    private val bus = BusConfig(0, "Wedge", vocalChannel = 5)

    private fun engine() = StageEngine(chans, listOf(bus))

    /** soundcheck balance: pyramid as the user described it */
    private val checkLevels = floatArrayOf(
        -18f, -19f, -24f, -27f, -25f, -20f, -26f, -26f, -28f)

    private fun sends() = chans.associate { (it.index to 0) to -10f }

    private fun run(e: StageEngine, levels: FloatArray, from: Double,
                    sec: Double): Pair<List<SendWrite>, Double> {
        val writes = ArrayList<SendWrite>()
        var t = from
        var nextTick = from + 1.0
        while (t < from + sec) {
            e.onMeters(levels, t)
            if (t >= nextTick) { writes += e.tick(t); nextTick += 1.0 }
            t += 0.05
        }
        return writes to t
    }

    private fun soundcheck(e: StageEngine): Double {
        val (_, t) = run(e, checkLevels, 0.0, 60.0)
        e.takeSnapshot(sends(), t)
        return t
    }

    @Test fun `whole band louder together is not drift - pyramid intact`() {
        val e = engine()
        val t = soundcheck(e)
        // encore energy: EVERYONE +4 dB — ratios unchanged
        val louder = FloatArray(checkLevels.size) { checkLevels[it] + 4f }
        val (writes, _) = run(e, louder, t, 180.0)
        val ladderCuts = writes.filter { it.channel !in setOf(0, 1) }
        assertTrue(ladderCuts.isEmpty(),
            "ladder channels must not be corrected when ratios are intact: " +
            ladderCuts.take(3))
        // foundation itself may trim back toward soundcheck (absolute
        // anchor) — bounded and slow, and that's the only movement
        assertTrue(writes.all { it.channel in setOf(0, 1) })
    }

    @Test fun `rhythm guitar creeping over its layer gets pulled back`() {
        val e = engine()
        val t = soundcheck(e)
        val crept = checkLevels.copyOf().also { it[3] += 6f }
        val (writes, _) = run(e, crept, t, 180.0)
        val gtr = writes.filter { it.channel == 3 }
        assertTrue(gtr.isNotEmpty(), "creeping rhythm gtr must be corrected")
        assertTrue(gtr.last().levelDb < -10f, "correction is a cut")
        assertTrue(writes.none { it.channel == 2 },
            "piano held its ratio — must not be touched")
    }

    @Test fun `foundation sags - pyramid follows it down, dominance kept`() {
        val e = engine()
        val t = soundcheck(e)
        // bass amp sags 5 dB; everyone else unchanged -> every layer is
        // now ~5 dB ABOVE its place relative to the foundation
        val sagged = checkLevels.copyOf().also { it[0] -= 5f; it[1] -= 5f }
        val (writes, _) = run(e, sagged, t, 240.0)
        // foundation gets boosted (capped +3)
        val foundation = writes.filter { it.channel in setOf(0, 1) }
        assertTrue(foundation.isNotEmpty(), "foundation must be lifted")
        assertTrue(foundation.all { it.levelDb <= -10f + 3.01f })
        // upper layers ease DOWN toward the sagging anchor
        val vox = writes.filter { it.channel == 5 }
        assertTrue(vox.isNotEmpty(), "layers must follow the anchor down")
        assertTrue(vox.last().levelDb < -10f)
    }

    @Test fun `backing vocal holds its in-the-mix ratio`() {
        val e = engine()
        val t = soundcheck(e)
        // backing vocal wanders up 5 dB — starts competing with the lead
        val bvUp = checkLevels.copyOf().also { it[6] += 5f }
        val (writes, _) = run(e, bvUp, t, 180.0)
        val bv = writes.filter { it.channel == 6 }
        assertTrue(bv.isNotEmpty(), "backing vocal must be tucked back in")
        assertTrue(bv.last().levelDb < -10f)
        assertTrue(writes.none { it.channel == 5 },
            "lead vocal held its place — untouched")
    }

    @Test fun `sax feature holds - color layer corrected like a soloist`() {
        val e = engine()
        val t = soundcheck(e)
        val saxLow = checkLevels.copyOf().also { it[7] -= 6f }
        val (writes, _) = run(e, saxLow, t, 300.0)
        val sax = writes.filter { it.channel == 7 }
        assertTrue(sax.isNotEmpty(), "quiet sax gets helped back up")
        assertTrue(sax.all { it.levelDb <= -10f + 3.01f },
            "but never more than +3 over soundcheck")
    }

    @Test fun `vocal ducking never touches the backing vocal`() {
        val e = engine()
        val t = soundcheck(e)
        // band swells 6 dB while lead vocal stays: ratio to vocal broken
        val swell = FloatArray(checkLevels.size) {
            if (it in setOf(5, 6)) checkLevels[it] else checkLevels[it] + 6f
        }
        val (writes, _) = run(e, swell, t, 120.0)
        assertTrue(writes.none { it.channel == 6 && it.levelDb < -10f - 4.5f },
            "backing vocal must not be ducked with the band")
    }

    @Test fun `singer switches mics mid-song - lead follows within seconds`() {
        val e = engine()
        var t = soundcheck(e)
        assertEquals(5, e.leadVocal, "soundcheck lead is Vocal Center")
        // main singer stops, second singer (bvox mic, ch 6) carries the
        // song — bvox sits 6 dB under the lead's soundcheck ratio
        val switched = checkLevels.copyOf().also {
            it[5] = -80f          // lead mic silent
            it[6] = -26f          // second singer singing (their level)
        }
        val (writes, t2) = run(e, switched, t, 40.0)
        assertEquals(6, e.leadVocal, "lead must follow to the singing mic")
        assertTrue(e.decisions.any { it.kind == "lead" },
            "lead switch must be logged")
        // the new lead gets pushed toward the TOP height (boost, capped)
        val bv = writes.filter { it.channel == 6 }
        assertTrue(bv.isNotEmpty(), "new lead must be lifted to the top")
        assertTrue(bv.all { it.levelDb <= -10f + 3.01f }, "still railed")
        assertTrue(t2 - t <= 41.0, "switch + lift all inside 40 s of audio")
    }

    @Test fun `lead does not flap between singers on a shared chorus`() {
        val e = engine()
        var t = soundcheck(e)
        // both singing together — lead must stay put (hysteresis)
        val both = checkLevels.copyOf().also { it[6] = -22f }
        run(e, both, t, 60.0)
        assertEquals(5, e.leadVocal, "shared singing must not steal the lead")
    }

    @Test fun `role inference covers the whole band`() {
        assertEquals(Role.FOUNDATION, inferRole("Bass Drum"))
        assertEquals(Role.FOUNDATION, inferRole("Synth Bass"))
        assertEquals(Role.KEYS, inferRole("Piano"))
        assertEquals(Role.KEYS, inferRole("Keyboard"))
        assertEquals(Role.RHYTHM_GTR, inferRole("Rhythm Gtr"))
        assertEquals(Role.SOLO_GTR, inferRole("Solo Guitar"))
        assertEquals(Role.VOCAL, inferRole("Lead Vox"))
        assertEquals(Role.BACKING_VOCAL, inferRole("Backing Vox"))
        assertEquals(Role.BACKING_VOCAL, inferRole("BGV 1"))
        assertEquals(Role.COLOR, inferRole("Sax"))
        assertEquals(Role.COLOR, inferRole("Harmonica"))
        assertEquals(Role.PERCUSSION, inferRole("Congas"))
        assertEquals(Role.PERCUSSION, inferRole("Congos"))
        assertEquals(Role.TALK, inferRole("Talkback"))
        assertEquals(Role.INSTRUMENT, inferRole("Ch 12"))
    }

    @Test fun `role inference matches the user's actual console names`() {
        assertEquals(Role.FOUNDATION, inferRole("Kick Drum"))
        assertEquals(Role.PERCUSSION, inferRole("Snare"))
        assertEquals(Role.PERCUSSION, inferRole("Overheads"))
        assertEquals(Role.FOUNDATION, inferRole("Bass Mic"))
        assertEquals(Role.SOLO_GTR, inferRole("Guitar AMP"))
        assertEquals(Role.RHYTHM_GTR, inferRole("Guitar DI"))
        assertEquals(Role.VOCAL, inferRole("Vocal Center"))
        assertEquals(Role.VOCAL, inferRole("Vocal Piano"))
        assertEquals(Role.FOUNDATION, inferRole("Bass DI"))
        assertEquals(Role.FOUNDATION, inferRole("DI2"))
        assertEquals(Role.FOUNDATION, inferRole("DI 2"))
        assertEquals(Role.COLOR, inferRole("Saxophone"))
        assertEquals(Role.COLOR, inferRole("Flute"))
        assertEquals(Role.COLOR, inferRole("Harmonica"))
        assertEquals(Role.PERCUSSION, inferRole("Congo 2"))
    }

    @Test fun `default rig profile is complete and sane`() {
        val rig = defaultRigProfile()
        assertEquals(16, rig.size)
        assertEquals(Role.VOCAL, rig[8].role)      // Vocal Center
        assertEquals(Role.VOCAL, rig[9].role)      // Vocal Piano
        assertEquals(Role.BACKING_VOCAL, rig[10].role)
        assertEquals(Role.FOUNDATION, rig[0].role) // Kick
        assertEquals(Role.FOUNDATION, rig[11].role) // Bass DI
        assertEquals(Role.FOUNDATION, rig[13].role) // DI2
        assertEquals(Role.COLOR, rig[15].role)     // Harmonica
    }
}
