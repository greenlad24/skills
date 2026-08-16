package com.stagemix.engine

import kotlin.math.abs
import kotlin.test.Test
import kotlin.test.assertTrue

/**
 * The two ways the starting chain could add gain at this rig's ring
 * frequencies, and the desk snapshot that closes both. RULEBOOK §0.1.
 */
class TreatmentDeskTest {
    private fun verdict(c: Float) = InstrumentId.Verdict(Family.VOICELIKE, c, "voice")
    private fun spec() = DoubleArray(100) { -30.0 }

    @Test fun `a high-pass the engineer set higher is never lowered`() {
        val t = ChannelTreatment()
        // engineer's low-cut at 200 Hz, in, to fight a 196 Hz ring
        t.snapshotDesk(8, hpfHz = 200f, hpfOn = true, eqDb = null)
        val w = t.consider(8, Role.VOCAL, verdict(0.95f), 1f, spec(), 100.0)
        val hpf = w.firstOrNull { it.address == "/ch/09/preamp/hpf" }
        if (hpf != null) {
            val hz = 20f * Math.pow(20.0, hpf.value.toDouble()).toFloat()
            assertTrue(hz >= 199f,
                "the chain lowered the engineer's 200 Hz high-pass to " +
                "%.0f Hz — that adds gain at the ring".format(hz))
        }
        // preferably it does not touch the high-pass at all
    }

    @Test fun `a band the engineer is cutting is left alone, a boost is flattened`() {
        val t = ChannelTreatment()
        // band 3 cut 8 dB (a ring-out), band 2 boosted 6 dB (a hazard)
        t.snapshotDesk(8, hpfHz = null, hpfOn = false,
            eqDb = floatArrayOf(0f, 6f, -8f, 0f))
        val w = t.consider(8, Role.VOCAL, verdict(0.95f), 1f, spec(), 100.0)
        val addrs = w.map { it.address }
        if (addrs.contains("/ch/09/eq/on")) {
            // the ring-out cut must survive: band 3 not written (unless
            // the chain itself uses band 3)
            val b3 = w.firstOrNull { it.address == "/ch/09/eq/3/g" }
            if (b3 != null)
                assertTrue(b3.value < 0.5f - GAIN_EPS,
                    "the chain flattened the engineer's ring-out at band 3")
            // the boost at band 2 must be neutralised (unless chain uses it)
            val b2 = w.firstOrNull { it.address == "/ch/09/eq/2/g" }
            if (b2 != null)
                assertTrue(b2.value <= 0.5f + GAIN_EPS,
                    "the stored +6 dB boost at band 2 was left in circuit")
        }
    }

    @Test fun `with no snapshot every band is still flattened, as before`() {
        val t = ChannelTreatment()
        val w = t.consider(8, Role.VOCAL, verdict(0.95f), 1f, spec(), 100.0)
        val addrs = w.map { it.address }
        if (addrs.contains("/ch/09/eq/on"))
            for (b in 1..3)
                assertTrue(addrs.contains("/ch/09/eq/$b/g"),
                    "an unsnapshotted channel must still flatten band $b")
    }
}
