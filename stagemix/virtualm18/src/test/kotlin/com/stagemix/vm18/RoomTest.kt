package com.stagemix.vm18

import com.stagemix.engine.FeedbackWatchdog
import com.stagemix.replay.Rta
import kotlin.math.log10
import kotlin.test.Test
import kotlin.test.assertTrue

/**
 * The room model exists for one reason: to make the howl watchdog
 * testable indoors. So these check that it actually rings up when the
 * faders are open, that it comes back down when they are pulled, and —
 * the point of the whole exercise — that the shipping watchdog SEES it.
 */
class RoomTest {

    private val sr = 24000

    @Test fun `it rings up when the loop is over unity, and down when cut`() {
        // four open mics at unity sum to +6 dB of loop; -3 dB of
        // coupling leaves +3 dB, which is unambiguously over unity
        val room = RoomLoop(sr, couplingDb = 0.0)
        room.enabled = true
        val out = FloatArray(1200)
        repeat(60) { room.advance(listOf(0f, 0f, 0f, 0f), out.size, out) }
        val rung = room.amplitude
        assertTrue(rung > 0.05,
            "the room did not ring up with the loop wide open: $rung")
        assertTrue(room.loopGainDb > 0, "loop gain should be over unity")

        // the engine pulls those mics down 20 dB, as it would on a veto
        repeat(120) { room.advance(listOf(-20f, -20f, -20f, -20f), out.size, out) }
        assertTrue(room.amplitude < rung * 0.2,
            "pulling the mics down did not stop the ring: ${room.amplitude}")
    }

    @Test fun `a well behaved stage does not ring`() {
        val room = RoomLoop(sr, couplingDb = -20.0)
        room.enabled = true
        val out = FloatArray(1200)
        repeat(200) { room.advance(listOf(-6f, -6f), out.size, out) }
        assertTrue(room.amplitude < 1e-3,
            "a quiet stage rang up anyway: ${room.amplitude}")
    }

    /**
     * A band, spectrally. NOT a pure sine — a sine is narrow, parked and
     * has no harmonics, which is precisely the description of feedback,
     * so testing against one proves nothing. Real instruments carry a
     * fundamental with harmonics at 2f and 3f, and that harmonic family
     * is exactly what the watchdog uses to tell music from a howl.
     */
    private fun band(t: Double, i: Int, rnd: java.util.Random): Float {
        val tt = t + i.toDouble() / sr
        var v = 0.0
        // a bass note and a guitar chord, each with their harmonics
        for ((f0, amp) in listOf(110.0 to 0.06, 330.0 to 0.04, 440.0 to 0.03))
            for (h in 1..5)
                v += amp / h * Math.sin(2 * Math.PI * f0 * h * tt)
        return (v + 0.02 * rnd.nextGaussian()).toFloat()
    }

    @Test fun `the shipping watchdog catches the room ringing`() {
        // The assertion the whole room model exists for: a real band
        // playing, the room ringing up underneath it, and the SHIPPING
        // watchdog has to pick the howl out and name its frequency.
        // two open mics at unity sum to +3 dB of loop; with no
        // attenuation back from the boxes that is +3 dB — a stage well
        // over the edge, which is the case the watchdog is for
        val room = RoomLoop(sr, freqHz = 2400.0, couplingDb = 0.0)
        room.enabled = true
        val watchdog = FeedbackWatchdog()
        val rta = Rta(sr, 4096)
        val tone = FloatArray(4096)
        val block = FloatArray(4096)
        val rnd = java.util.Random(3)
        var t = 0.0
        var caught = -1.0
        var caughtHz = 0
        // Measured in ANALYZER FRAMES, not seconds: this fixture's FFT
        // produces a spectrum every 4096 samples (~6 a second) while the
        // console streams its RTA at 20. Seconds here would flatter or
        // damn the watchdog by an accident of the test's block size.
        var frames = 0
        var caughtFrame = -1

        repeat(160) {
            room.advance(listOf(0f, 0f), tone.size, tone)
            for (i in block.indices) block[i] = band(t, i, rnd) + tone[i]
            rta.push(block, block.size)?.let { bins ->
                frames++
                watchdog.onRta(bins, t)
                if (watchdog.vetoActive && caught < 0) {
                    caught = t; caughtHz = watchdog.lastFreqHz
                    caughtFrame = frames
                }
            }
            t += block.size.toDouble() / sr
        }
        assertTrue(caught >= 0,
            "the room rang up to %.0f dB and the watchdog never vetoed — "
                .format(java.util.Locale.ROOT, 20 * log10(room.amplitude)) +
            "on a real stage that is a scream")
        // and it has to be the HOWL it caught, not the band
        assertTrue(caughtHz > 1600 && caughtHz < 3600,
            "the watchdog vetoed at ${caughtHz} Hz but the room is ringing " +
            "at 2400 Hz — it latched onto the band, which is a false alarm, " +
            "not a catch")
        // 60 analyzer frames is three seconds at the console's rate, ten
        // of which are the watchdog's own confirmation window. It
        // measures around 40; the headroom is so this fails on a real
        // regression rather than on a fixture's rounding.
        assertTrue(caughtFrame in 1..60,
            "the watchdog needed $caughtFrame analyzer frames to notice — " +
            "at the console's 20 Hz that is ${caughtFrame / 20.0}s of howling")
        println(("watchdog caught the room after %d analyzer frames " +
            "(~%.1fs at the console's rate), at %d Hz")
            .format(java.util.Locale.ROOT, caughtFrame,
                caughtFrame / 20.0, caughtHz))
    }

    @Test fun `the band alone never trips the watchdog`() {
        // the other half of the same claim: no howl, no veto
        val watchdog = FeedbackWatchdog()
        val rta = Rta(sr, 4096)
        val block = FloatArray(4096)
        val rnd = java.util.Random(11)
        var t = 0.0
        repeat(160) {
            for (i in block.indices) block[i] = band(t, i, rnd)
            rta.push(block, block.size)?.let { watchdog.onRta(it, t) }
            t += block.size.toDouble() / sr
        }
        assertTrue(!watchdog.vetoActive,
            "the watchdog vetoed on a band that was only playing, at " +
            "${watchdog.lastFreqHz} Hz")
    }

    @Test fun `the dynamics model answers the threshold the doctor moves`() {
        // /meters/6 used to be zeros, so compressor tending could not be
        // exercised at all. The gain reduction must respond to the
        // threshold the console holds, or the loop is still open.
        val d = ChannelDynamics(sr)
        val x = FloatArray(2400) {
            (0.3 * Math.sin(2 * Math.PI * 200.0 * it / sr)).toFloat() }
        repeat(20) { d.push(x, x.size, thresholdDb = -30f) }
        val deep = d.compGrDb
        repeat(20) { d.push(x, x.size, thresholdDb = -6f) }
        val shallow = d.compGrDb
        assertTrue(deep < -1f, "a low threshold must compress: $deep")
        assertTrue(shallow > deep + 1f,
            "raising the threshold must reduce the gain reduction " +
            "($deep -> $shallow) or the doctor is steering nothing")
    }

    @Test fun `the gate reports reduction only when the source is quiet`() {
        val d = ChannelDynamics(sr)
        val loud = FloatArray(2400) {
            (0.3 * Math.sin(2 * Math.PI * 200.0 * it / sr)).toFloat() }
        repeat(20) { d.push(loud, loud.size, -20f) }
        assertTrue(d.gateGrDb > -0.5f, "a loud source is not gated")
        val quiet = FloatArray(2400) { 0f }
        repeat(60) { d.push(quiet, quiet.size, -20f) }
        assertTrue(d.gateGrDb < -5f, "silence should close the gate")
    }
}
