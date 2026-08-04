package com.stagemix.vm18

import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.exp
import kotlin.math.log10
import kotlin.math.max
import kotlin.math.pow
import kotlin.math.sin

/**
 * The part of a real stage a recording cannot contain: the loop from the
 * PA back into the open mics.
 *
 * Replaying a recorded night through the engine is honest about the
 * band and silent about the room — the recording is fixed, so the
 * engine's own moves cannot change what it hears, and a gain runaway can
 * never happen. Which means the howl watchdog, the single most
 * consequential safety feature in the app, is untestable on a recording.
 *
 * So the room is modelled. Not the whole room — one resonance, which is
 * what feedback actually is:
 *
 *   · every open mic hears the mains, attenuated by how far it is from
 *     the boxes ([couplingDb]) and by wherever its fader is now;
 *   · at one frequency the room rings, and the loop gain there is the
 *     sum of those paths;
 *   · above unity the ring grows exponentially, below it decays.
 *
 * The tone is injected into the mic channels BEFORE metering, so it
 * arrives everywhere it would live: the input meters see it, the RTA
 * sees a narrow peak climbing at a fixed frequency, and it comes out of
 * the speakers. If the engine boosts an open mic too far, the room
 * answers — and either the watchdog freezes the boosts in time or it
 * does not, which is exactly the thing worth finding out indoors.
 */
class RoomLoop(
    private val sampleRate: Int,
    /** the ringing frequency, Hz */
    var freqHz: Double = 2400.0,
    /**
     * How much of the mains gets back into an open mic, in dB, with the
     * fader at unity. −6 dB is a mic in front of the boxes on a bad
     * night; −20 dB is a well-behaved stage. The default sits just under
     * the edge so a couple of dB of boost tips it over — which is the
     * situation the watchdog exists for.
     */
    var couplingDb: Double = -12.0,
    /** how fast it rings up once the loop is over unity (seconds to e) */
    private val tauSec: Double = 0.35,
) {
    /** the current ring amplitude, 0..1 */
    var amplitude = 0.0; private set
    /** the loop gain last computed, in dB — over 0 means it is growing */
    var loopGainDb = -60.0; private set
    var enabled = false
    /** momentarily open the loop, as if someone walked a mic into the PA */
    private var provokeUntil = 0.0
    private var phase = 0.0
    private var t = 0.0

    fun provoke(seconds: Double = 6.0) { provokeUntil = t + seconds }

    private companion object {
        /** roughly −74 dBFS: the hiss a live mic channel always carries */
        const val MIC_NOISE_FLOOR = 2e-4
    }

    /**
     * Advance the room by one block.
     *
     * [openMicGainDb] is the fader position of every channel that is an
     * open microphone — DI'd instruments cannot feed back and are not
     * part of the loop. Returns the tone to add to those channels.
     */
    fun advance(openMicGainDb: List<Float>, frames: Int, out: FloatArray): Boolean {
        val dt = frames.toDouble() / sampleRate
        t += dt
        if (!enabled || openMicGainDb.isEmpty()) {
            amplitude *= exp(-dt / 0.2)      // whatever is ringing, decays
            loopGainDb = -60.0
            if (amplitude < 1e-6) { amplitude = 0.0; return false }
        } else {
            // the paths sum as power: two mics equally open are 3 dB worse
            var p = 0.0
            for (g in openMicGainDb) p += 10.0.pow(g / 10.0)
            val extra = if (t < provokeUntil) 10.0 else 0.0
            loopGainDb = 10.0 * log10(max(p, 1e-12)) + couplingDb + extra
            // Above unity it grows, below it decays. What it grows FROM
            // is the mic's own noise floor — real feedback does not
            // start from nothing, it takes the hiss already in the
            // channel and multiplies it, which is why it goes from
            // inaudible to painful in a second or two.
            amplitude = (amplitude + MIC_NOISE_FLOOR) *
                exp((loopGainDb / 8.686) * dt / tauSec)
            if (amplitude > 0.7) amplitude = 0.7   // the PA limits, not us
            if (amplitude < 1e-7) { amplitude = 0.0; return false }
        }
        val w = 2.0 * PI * freqHz / sampleRate
        for (i in 0 until frames) {
            out[i] = (amplitude * sin(phase)).toFloat()
            phase += w
            if (phase > 2 * PI) phase -= 2 * PI
        }
        return true
    }

    /** for the window: how close the room is to running away */
    fun status(): String = when {
        !enabled -> "room loop off"
        amplitude <= 0.0 -> "room stable (loop %.1f dB)".format(
            java.util.Locale.ROOT, loopGainDb)
        loopGainDb > 0 -> "RINGING UP — loop %+.1f dB, %.0f dB of tone"
            .format(java.util.Locale.ROOT, loopGainDb, 20 * log10(amplitude))
        else -> "ringing down (loop %+.1f dB)".format(
            java.util.Locale.ROOT, loopGainDb)
    }
}

/**
 * The channel dynamics the console would be applying, so `/meters/6`
 * carries gain reduction a Channel Doctor can actually work from.
 *
 * The bench used to send zeros, which meant compressor tending could not
 * be exercised at all. This is a plain feed-forward peak compressor and
 * a downward gate, reading the SAME threshold the console holds — so
 * when the doctor eases a threshold, the gain reduction it sees on the
 * next meter frame really does respond. That closes the loop the
 * feature needs to be testable.
 *
 * It is not the M18's dynamics section — no knee shape, no auto modes,
 * no sidechain filter. It is enough to be worth something and it is
 * labelled as a model, not as the desk.
 */
class ChannelDynamics(private val sampleRate: Int) {
    private var compEnv = 0f
    private var gateEnv = 0f
    var compGrDb = 0f; private set
    var gateGrDb = 0f; private set

    private val atk = 1f - exp(-1.0 / (0.005 * sampleRate)).toFloat()
    private val rel = 1f - exp(-1.0 / (0.150 * sampleRate)).toFloat()

    /**
     * @param thresholdDb the compressor threshold the console holds
     * @param ratio compression ratio (the X-Air default is around 3:1)
     * @param gateThreshDb below this the gate closes
     */
    fun push(x: FloatArray, n: Int, thresholdDb: Float,
             ratio: Float = 3f, gateThreshDb: Float = -60f) {
        for (i in 0 until n) {
            val a = abs(x[i])
            compEnv += (if (a > compEnv) atk else rel) * (a - compEnv)
            gateEnv += (if (a > gateEnv) atk else rel) * (a - gateEnv)
        }
        val db = if (compEnv <= 1e-7f) -128f
                 else (20.0 * log10(compEnv.toDouble())).toFloat()
        compGrDb = if (db <= thresholdDb) 0f
                   else -((db - thresholdDb) * (1f - 1f / ratio))
        val gdb = if (gateEnv <= 1e-7f) -128f
                  else (20.0 * log10(gateEnv.toDouble())).toFloat()
        gateGrDb = if (gdb >= gateThreshDb) 0f
                   else -((gateThreshDb - gdb).coerceAtMost(40f))
    }
}
