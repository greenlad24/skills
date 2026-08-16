package com.stagemix.engine

import kotlin.math.abs
import kotlin.math.ln
import kotlin.math.max
import kotlin.math.min

/**
 * Ringing out a stage, automatically.
 *
 * "There were times in the night where a feedback was happening — on the
 * stage, in the monitors."
 *
 * The watchdog already hears it: eight rings over three nights, at 196,
 * 160, 226 and 3377 Hz. All it did about them was freeze the engine's
 * boosts, which does exactly nothing for a wedge that is howling — the
 * loop is the microphone, the wedge and the air between them, and the
 * mains fader is not in it.
 *
 * What a human does is ring the stage out: find the frequency, put a
 * narrow cut there, move on. That is what this does, and it does it on
 * the CHANNEL rather than on the monitor bus, for three reasons:
 *
 *  · The channel is in every loop that mic is part of, so one cut fixes
 *    the wedge, the side-fill and the mains at once.
 *  · A tenth-octave cut on one microphone is inaudible to an audience
 *    and is the same move a human would make with a parametric.
 *  · Monitor buses are the band's ears. Cutting a channel's tone is
 *    ours; the wedge mix is not.
 *
 * WHICH microphone is the loop is a question the console can answer.
 * A howl circulates acoustically so every open mic hears it, but the
 * one IN the loop hears it far louder than the rest — so when a ring
 * starts, the analyzer sweeps the stage and measures every channel at
 * that one frequency. The loudest is the one to cut.
 *
 * Everything here is cut-only, bounded, slow to arrive and slower to
 * leave, and it says what it did.
 */
class RingOut(
    /** how deep a single notch may ever go */
    val maxCutDb: Float = 9f,
    /** the first cut, and how much deeper each recurrence goes */
    val firstCutDb: Float = 4f,
    val deeperDb: Float = 2.5f,
    /** how long to sweep the stage looking for the microphone */
    val huntSec: Double = 8.0,
    /** silence at that frequency for this long and the cut is eased out */
    val releaseAfterSec: Double = 600.0,
    /** how much comes back at a time, so nothing snaps */
    val releaseStepDb: Float = 1.5f,
    /** how narrow: this is a notch, not a tone control */
    val q: Float = 8f,
) {

    /** one cut on one channel, and why it is there */
    class Notch(val ch: Int, val hz: Float) {
        var cutDb = 0f
        var wanted = 0f
        var lastRingT = -1.0
        var rings = 0
        var written = false
    }

    private val notches = HashMap<Int, Notch>()

    /** the ring being hunted right now, if any */
    private var huntHz = 0f
    private var huntUntil = -1.0
    private val heard = HashMap<Int, Float>()

    /** true while the analyzer should be sweeping rather than dawdling */
    val hunting: Boolean get() = huntUntil > 0

    /** what was done, for the log */
    var lastAction: String = ""; private set

    /**
     * The watchdog has a ring. Start looking for the microphone it is
     * living in — or, if this frequency is already notched somewhere,
     * take that as evidence the cut is not yet deep enough.
     */
    fun ringing(hz: Int, tSec: Double) {
        if (hz <= 0) return
        val existing = notches.values.firstOrNull { sameNote(it.hz, hz.toFloat()) }
        if (existing != null) {
            existing.rings++
            existing.lastRingT = tSec
            existing.wanted = min(maxCutDb, existing.wanted + deeperDb)
            lastAction = ("ch%02d is ringing at %d Hz again — taking it " +
                "down %.1f dB in total").format(java.util.Locale.ROOT,
                    existing.ch + 1, hz, existing.wanted)
            return
        }
        huntHz = hz.toFloat()
        huntUntil = tSec + huntSec
        heard.clear()
        lastAction = "ringing at $hz Hz — finding which microphone it is in"
    }

    /** the ring cleared before we found it */
    fun cleared(tSec: Double) {
        if (huntUntil > 0 && heard.isEmpty()) huntUntil = -1.0
    }

    /**
     * A spectrum from one channel. While hunting, all that matters is
     * how loud THIS channel is at the ringing frequency.
     */
    fun onRta(ch: Int, bins: FloatArray, tSec: Double) {
        if (huntUntil <= 0) return
        val b = FrequencyMap.binOf(huntHz)
        var peak = -128f
        for (i in max(0, b - 1)..min(bins.size - 1, b + 1))
            peak = max(peak, bins[i])
        heard[ch] = max(heard[ch] ?: -128f, peak)
    }

    /**
     * Decide, and produce the writes. Called on the engine's own beat.
     *
     * @param mayWrite false while the app is only watching, or while a
     *        hand is on that channel — the hunt still runs, so the log
     *        says what it would have done.
     */
    fun tick(tSec: Double, mayWrite: Boolean = true): List<ParamWrite> {
        // the hunt is over: whichever microphone heard it loudest is
        // the one in the loop
        if (huntUntil > 0 && tSec >= huntUntil) {
            huntUntil = -1.0
            val best = heard.maxByOrNull { it.value }
            if (best != null && best.value > -90f) {
                val n = notches.getOrPut(best.key) { Notch(best.key, huntHz) }
                n.rings++
                n.lastRingT = tSec
                n.wanted = if (n.wanted <= 0f) firstCutDb
                           else min(maxCutDb, n.wanted + deeperDb)
                lastAction = ("%.0f Hz is loudest on ch%02d (%.0f dB, next " +
                    "loudest %.0f) — cutting it %.1f dB there")
                    .format(java.util.Locale.ROOT, huntHz, best.key + 1,
                        best.value,
                        heard.values.sortedDescending().getOrElse(1) { -128f },
                        n.wanted)
            } else {
                lastAction = "the ring cleared before it could be traced"
            }
            heard.clear()
        }
        // ease out anything that has not rung for a long time
        for (n in notches.values) {
            if (n.wanted > 0f && n.lastRingT > 0 &&
                tSec - n.lastRingT > releaseAfterSec) {
                n.wanted = max(0f, n.wanted - releaseStepDb)
                n.lastRingT = tSec
                lastAction = ("ch%02d has not rung at %.0f Hz for %d minutes " +
                    "— easing the cut back to %.1f dB")
                    .format(java.util.Locale.ROOT, n.ch + 1, n.hz,
                        (releaseAfterSec / 60).toInt(), n.wanted)
            }
        }
        if (!mayWrite) return emptyList()
        val out = ArrayList<ParamWrite>()
        for (n in notches.values) {
            if (n.written && abs(n.cutDb - n.wanted) < 0.05f) continue
            n.cutDb = n.wanted
            n.written = true
            val c = osc("%02d", n.ch + 1)
            // The reserved band. The starting chain never writes it —
            // see ChannelTreatment.RING_BAND — so a notch and a chain
            // cannot argue with each other.
            out.add(ParamWrite("/ch/$c/eq/$RING_BAND/f",
                ChannelTreatment.freqToFloat(n.hz)))
            out.add(ParamWrite("/ch/$c/eq/$RING_BAND/q",
                ChannelTreatment.qToFloat(q)))
            out.add(ParamWrite("/ch/$c/eq/$RING_BAND/g",
                ChannelTreatment.eqGainToFloat(-n.cutDb)))
            out.add(ParamWrite("/ch/$c/eq/on", 1f))
        }
        return out.filter { isSafeAddress(it.address) &&
            !isGainAdding(it.address, it.value) }
    }

    /** every cut currently in place, for the screen and the log */
    fun active(): List<Notch> = notches.values.filter { it.cutDb > 0f }

    fun describe(): String =
        if (active().isEmpty()) "no rings cut"
        else active().joinToString("  ") {
            "ch%02d %.0fHz -%.1fdB".format(java.util.Locale.ROOT,
                it.ch + 1, it.hz, it.cutDb)
        }

    fun forget(ch: Int) { notches.remove(ch) }

    /** within a tenth of an octave is the same ring */
    private fun sameNote(a: Float, b: Float): Boolean =
        abs(ln(a / b) / ln(2f)) < 0.1f

    companion object {
        /**
         * The EQ band kept for ring-outs, on every channel.
         *
         * Band 4 rather than one of the middle two because the starting
         * chain uses 1-3 and writes the others flat; a notch that the
         * next re-treat erases is not a notch.
         */
        const val RING_BAND = 4
    }
}
