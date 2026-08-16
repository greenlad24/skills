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
    /**
     * How far clear of the field a channel has to be to end the sweep
     * early, and how many channels must have been measured first.
     *
     * Six dB is not a close call BETWEEN OPEN MICROPHONES — but that
     * is only the right comparison if most of the stage has actually
     * been measured. `heard` contains only the channels the analyzer
     * has physically visited, and at a half-second dwell the first
     * version of this could fire having seen four consecutive channels:
     * one subgroup, chosen by wherever the RTA happened to be parked.
     * Four DIs reading their own noise floor differ by more than six dB
     * routinely, and a bass playing G3 reads loud at a 196 Hz ring
     * without being anywhere near the loop.
     *
     * The consequence was not a slower fix, it was the wrong one: a
     * notch on an innocent channel, and — because a notch claims its
     * frequency — no further hunt for the microphone that was actually
     * howling. Twelve of sixteen is three quarters of the stage, about
     * six seconds instead of eight, which is the whole honest saving
     * here.
     */
    val decisiveDb: Float = 6f,
    val minHeardChannels: Int = 12,
    /** silence at that frequency for this long and the cut is eased out */
    val releaseAfterSec: Double = 600.0,
    /** how much comes back at a time, so nothing snaps */
    val releaseStepDb: Float = 1.5f,
    /** how narrow: this is a notch, not a tone control */
    val q: Float = 8f,
) {

    /** one cut on one channel, and why it is there */
    class Notch(val ch: Int, var hz: Float) {
        var cutDb = 0f
        var wanted = 0f
        var lastRingT = -1.0
        var rings = 0
        var written = false
        /**
         * A pre-ring GUARD, not a live howl: a shallow standing cut put
         * on a frequency this rig has fed back at before, so the recurring
         * howl is pre-empted rather than hunted from cold every night. It
         * does not ease out on its own, and — unlike a live ring — it does
         * NOT bar the mic from being raised (it has not howled tonight).
         * The moment it actually rings it stops being a guard.
         */
        var guard = false
    }

    private val notches = HashMap<Int, Notch>()

    /** one channel-frequency that has fed back, for carrying across nights */
    data class Learned(val ch: Int, val hz: Float, val rings: Int)

    /**
     * The feedback this rig has produced this session, so it can be saved
     * and carried into the next night. Every channel-frequency that has
     * actually rung (a guard that never howled is not evidence of
     * anything, so it is not exported).
     */
    fun learnedProfile(): List<Learned> = notches.values
        .filter { it.rings > 0 }
        .map { Learned(it.ch, it.hz, it.rings) }

    /**
     * Pre-ring the stage from a saved profile: put a shallow guard cut on
     * every channel-frequency that has howled here before often enough to
     * count. Returns the guards actually placed, for the log. Skips a
     * channel that is already notched (a live ring owns it).
     */
    fun seedGuards(profile: List<Learned>, minRings: Int, guardDb: Float):
            List<Learned> {
        val placed = ArrayList<Learned>()
        for (p in profile) {
            if (p.rings < minRings) continue
            if (notches[p.ch]?.let { it.wanted > 0f } == true) continue
            val n = notches.getOrPut(p.ch) { Notch(p.ch, p.hz) }
            n.hz = p.hz
            n.wanted = min(maxCutDb, guardDb)
            n.guard = true
            n.written = false
            n.lastRingT = -1.0
            placed.add(p)
        }
        return placed
    }

    /** the ring being hunted right now, if any */
    private var huntHz = 0f
    private var huntUntil = -1.0
    private val heard = HashMap<Int, Float>()

    /** true while the analyzer should be sweeping rather than dawdling */
    val hunting: Boolean get() = huntUntil > 0

    /** seconds of hunt still to run, so the screen can draw a real bar */
    fun huntLeft(tSec: Double): Double =
        if (huntUntil > 0) (huntUntil - tSec).coerceAtLeast(0.0) else 0.0
    val huntSpan: Double get() = huntSec

    /** what was done, for the log */
    var lastAction: String = ""; private set

    /**
     * The watchdog has a ring. Start looking for the microphone it is
     * living in — or, if this frequency is already notched somewhere,
     * take that as evidence the cut is not yet deep enough.
     */
    fun ringing(hz: Int, tSec: Double) {
        if (hz <= 0) return
        // Only a notch that is actually CUTTING owns its frequency. A
        // fully-released one still matched here, so the next ring at
        // that pitch re-cut the old channel and suppressed the hunt —
        // and if the singer had moved to a different microphone in the
        // meantime, the app cut an innocent channel and did nothing
        // whatever about the howl.
        val existing = notches.values.firstOrNull {
            it.wanted > 0f && sameNote(it.hz, hz.toFloat()) }
        if (existing != null) {
            // a guard that actually howls is no longer a guard — it is a
            // live ring now, and follows the reactive rules from here
            val wasGuard = existing.guard
            existing.guard = false
            existing.rings++
            existing.lastRingT = tSec
            existing.wanted = min(maxCutDb, existing.wanted + deeperDb)
            lastAction = (if (wasGuard)
                "ch%02d rang at %d Hz — the pre-ring guard was right; " +
                "deepening it to %.1f dB"
                else "ch%02d is ringing at %d Hz again — taking it " +
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
        // STOP LOOKING THE MOMENT THE ANSWER IS OBVIOUS.
        //
        // "I want the app to fix feedbacks as fast as it can." The hunt
        // used to run its full eight seconds every time, which is eight
        // seconds of a stage howling while the app finishes a sweep
        // whose answer it already has. A microphone that is actually IN
        // the loop is not marginally louder at the ringing frequency
        // than the others — it is enormously louder, because everything
        // else is hearing the same howl across a room. So once enough
        // channels have been measured to make a comparison meaningful
        // and one of them is [decisiveDb] clear of the field, that is
        // the microphone, and waiting longer only prolongs the noise.
        //
        // The full sweep still runs whenever the field is close, which
        // is exactly the case where guessing early would cut the wrong
        // channel.
        if (huntUntil > 0 && heard.size >= minHeardChannels) {
            val ranked = heard.entries.sortedByDescending { it.value }
            val lead = ranked[0].value - ranked[1].value
            if (lead >= decisiveDb) huntUntil = tSec
        }
        // the hunt is over: whichever microphone heard it loudest is
        // the one in the loop
        if (huntUntil > 0 && tSec >= huntUntil) {
            huntUntil = -1.0
            // The same guard the early exit has: do not call a culprit
            // from a handful of channels. If Wi-Fi dropped most of the
            // sweep, notching the loudest of the few that reported is
            // the wrong-microphone failure the whole minHeardChannels
            // rule exists to prevent — better to miss this ring and let
            // the watchdog re-trigger a fresh sweep than cut an innocent
            // channel and stop looking.
            val best = if (heard.size >= minHeardChannels)
                heard.maxByOrNull { it.value } else null
            if (best != null && best.value > -90f) {
                val n = notches.getOrPut(best.key) { Notch(best.key, huntHz) }
                // ONE RESERVED BAND MEANS ONE NOTCH PER CHANNEL, so when
                // the same microphone rings at a genuinely different
                // frequency the band has to MOVE. It used to keep the
                // old frequency and merely deepen it, while the log
                // said it had cut the new one: a 9 dB hole grew at
                // 196 Hz in a voice's fundamentals and the 3377 Hz howl
                // — the most piercing of the four this rig produces —
                // was never touched at all, all night.
                if (!sameNote(n.hz, huntHz)) {
                    lastAction = ("ch%02d already had a cut at %.0f Hz; " +
                        "it is ringing at %.0f now, so the cut moves " +
                        "there — one microphone, one reserved band")
                        .format(java.util.Locale.ROOT, n.ch + 1, n.hz, huntHz)
                    n.hz = huntHz
                    n.wanted = 0f
                    n.rings = 0
                    n.written = false
                }
                n.guard = false          // it howled: a live ring now
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
        // ease out anything that has not rung for a long time — but NOT a
        // pre-ring guard: it is a standing cut on a known-bad frequency,
        // held all night by design (a guard that actually rings stops
        // being a guard, so it will ease out normally after that)
        for (n in notches.values) {
            if (n.wanted > 0f && !n.guard && n.lastRingT > 0 &&
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
