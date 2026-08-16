package com.stagemix.engine

import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

/**
 * The keeper of the wedges — the half that writes.
 *
 * [MonitorMap] works out what each monitor is for and how far its mix
 * is from what that position wants. This acts on that, under the one
 * instruction that governs the whole class:
 *
 *   "the app can do rebalancing to the monitors but in a different way
 *    it does on the outside ... adjust it slightly based on the
 *    position of it ... if the sound engineer is changing that balance,
 *    understand what's happening and go with it rather than fight it"
 *
 * and, later, "monitors will rebalance slightly not much".
 *
 * ## Cut-preferred, always
 *
 * The single most important rule here, and the reason this can be
 * trusted at all: **to make something louder in a wedge, it turns
 * something else down.**
 *
 * Every monitor mix is a ratio. If the singer's voice is 4 dB below
 * where the centre wedge wants it, there are two ways to fix that, and
 * they are not equally safe. Raising the vocal send spends gain before
 * feedback on the loudest open microphone in the room, pointed at the
 * wedge that is about to howl. Lowering everything else by the same
 * amount produces the identical ratio and spends nothing — the loop
 * gain goes DOWN. "I want the app to avoid creating feedbacks" and
 * "I would like the balance in the monitors to be perfect" are only
 * compatible one way round, and this is it.
 *
 * So a raise is the last resort, not the first: it happens only when
 * there is genuinely nothing left to cut, it is capped at a dB and a
 * half over the whole night, and it is refused outright on any channel
 * and bus that has ever been part of a ring.
 *
 * ## Whose stage it is
 *
 * The engineer's hand always wins and is never argued with. When a
 * send moves and this class did not move it, that level becomes the new
 * truth, the app's own offset on it is forgotten, and the entire bus is
 * left alone for five minutes. Following is not the same as obeying
 * afterwards: it re-anchors, so the target is recomputed around where
 * they put it rather than dragged back to where it was.
 *
 * ## And how little it does
 *
 * One move per bus per twenty seconds, 0.7 dB at a time, at most 6 dB
 * of cut and 1.5 dB of boost on any one send across a whole night, and
 * nothing at all between songs. On a wedge that is already inside two
 * and a half dB of where it should be, nothing at all ever.
 */
class MonitorBalance(
    private val map: MonitorMap,
    /** inside this, the wedge is right and is left alone */
    val tolDb: Float = 2.5f,
    /** how far one move may go */
    val stepDb: Float = 0.7f,
    /** how much may ever be taken OUT of one send, all night */
    val maxCutDb: Float = 6f,
    /** how much may ever be ADDED to one send, all night */
    val maxRaiseDb: Float = 1.5f,
    /** and how long between moves on the same bus */
    val minGapSec: Double = 20.0,
    /** how long to keep hands off a bus after the engineer touches it */
    val handBackOffSec: Double = 300.0,
    /** a send that moved by more than this, that we did not move */
    val handDb: Float = 0.4f,
    /** no raising anywhere on a bus for this long after it rings */
    val ringQuietSec: Double = 240.0,
) {

    /** one send, as the desk has it and as this class has changed it */
    class Send(val bus: Int, val ch: Int) {
        /** the level the engineer set, which is what we balance around */
        var anchorDb = 0f
        /** what this class has added to it since, net */
        var appDb = 0f
        /** what we last wrote, so a change we did not make is detectable */
        var writtenDb: Float? = null
        var lastMoveT = -1e9
        /** this send has been in a ring: it is never raised again */
        var ringProne = false
        val nowDb: Float get() = anchorDb + appDb
    }

    private val sends = HashMap<Long, Send>()
    private val handUntil = HashMap<Int, Double>()
    private val ringQuietUntil = HashMap<Int, Double>()
    private val lastBusMove = HashMap<Int, Double>()

    /** what it did and why, newest last — drained by the log */
    val notes = ArrayList<String>()

    private fun key(bus: Int, ch: Int) = bus.toLong() * 64L + ch
    private fun send(bus: Int, ch: Int) =
        sends.getOrPut(key(bus, ch)) { Send(bus, ch) }

    /** every send this class has moved, for the screen */
    fun moved(): List<Send> = sends.values.filter { abs(it.appDb) > 0.05f }
        .sortedWith(compareBy({ it.bus }, { it.ch }))

    /**
     * A send level, read off the console.
     *
     * This is also the only place a human's hand is detected. If the
     * level is not where we left it, they moved it — so adopt it, drop
     * whatever we had done to that send, and leave the whole bus alone
     * for five minutes.
     */
    fun onSend(bus: Int, ch: Int, db: Float, tSec: Double) {
        val s = send(bus, ch)
        val w = s.writtenDb
        if (w == null) {
            // first sighting: this is their mix, and it is the anchor
            s.anchorDb = db
            s.appDb = 0f
            s.writtenDb = db
            return
        }
        if (abs(db - w) > handDb) {
            s.anchorDb = db
            s.appDb = 0f
            s.writtenDb = db
            handUntil[bus] = tSec + handBackOffSec
            notes.add("bus " + bus + " ch" + (ch + 1) + " — you moved " +
                "that send to " + db(db) + " dB; taking it as the " +
                "balance you want and leaving bus " + bus + " alone for " +
                (handBackOffSec / 60).toInt() + " min")
        }
    }

    /**
     * Something rang. Every wedge carrying that microphone stops being
     * raised — that one for good, the rest for a few minutes.
     */
    fun onRing(ch: Int, tSec: Double) {
        for (bus in map.buses) {
            ringQuietUntil[bus] = tSec + ringQuietSec
            // getOrPut, not a raw lookup. Send replies get dropped on a
            // venue's Wi-Fi all the time, and a send whose reply was
            // lost is exactly the one this must not forget: without the
            // entry, ringProne is never set, and four minutes later the
            // keeper is free to raise the microphone that just howled.
            send(bus, ch).ringProne = true
        }
    }

    /** true while this bus may not be raised at all */
    fun raiseBarred(bus: Int, tSec: Double): Boolean =
        tSec < (ringQuietUntil[bus] ?: -1e9)

    /** true while the engineer's hand is being respected on this bus */
    fun following(bus: Int, tSec: Double): Boolean =
        tSec < (handUntil[bus] ?: -1e9)

    /**
     * Decide what to change, and produce the writes.
     *
     * @param playing false between songs — then this does nothing at
     *        all, which is the standing instruction for the mains too.
     * @param push true when the operator asked for a rebalance: a few
     *        moves instead of one, and a bigger step. Still bounded by
     *        every total, because a button press is not permission to
     *        rearrange somebody's ears.
     */
    fun plan(
        tSec: Double,
        roles: Map<Int, Role>,
        kit: Set<Int>,
        playing: Boolean,
        push: Boolean = false,
    ): List<ParamWrite> {
        if (!playing) return emptyList()
        val out = ArrayList<ParamWrite>()
        val step = if (push) stepDb * 2f else stepDb
        val movesPerBus = if (push) 3 else 1
        for (w in map.all()) {
            if (w.kind == MonitorMap.Kind.UNKNOWN) continue
            if (following(w.bus, tSec)) continue
            if (!push && tSec - (lastBusMove[w.bus] ?: -1e9) < minGapSec)
                continue
            // RE-READ THE WEDGE AFTER EVERY MOVE.
            //
            // The critique is a ratio against the wedge's own average,
            // so one cut changes every other channel's verdict. Walking
            // a stale list was two bugs at once: in a push pass all
            // three moves picked the SAME channel as the thing to bring
            // down and dropped it 4.2 dB in one batch, and between
            // passes the identical verdict came back for ever, so a
            // 3 dB error was "corrected" nine times until the send hit
            // its 6 dB cap. Recomputing makes the loop closed and makes
            // it stop when the wedge is right.
            var made = 0
            while (made < movesPerBus) {
                val ns = map.critique(w.bus, roles, kit)
                if (ns.isEmpty()) break
                var did: ParamWrite? = null
                for (n in ns) {
                    did = moveFor(w, n, ns, step, tSec)
                    if (did != null) break
                }
                if (did == null) break
                out.add(did)
                made++
            }
            if (made > 0) lastBusMove[w.bus] = tSec
        }
        return out.filter { isMonitorSend(it.address) }
    }

    /**
     * One channel, in one wedge: what to do about it, if anything.
     *
     * The whole cut-preferred rule lives in the `off < 0` branch.
     */
    private fun moveFor(
        w: MonitorMap.Wedge, n: MonitorMap.Note,
        all: List<MonitorMap.Note>, step: Float, tSec: Double,
    ): ParamWrite? {
        val s = send(w.bus, n.ch)

        // A channel that should not be in this wedge at all — the kit in
        // a floor monitor. Always a cut, always safe, always right.
        if (n.wantDb == null) {
            if (n.nowDb <= MonitorMap.MONITOR_FLOOR_DB) return null
            return cut(s, step, tSec,
                w.name + ": the kit is three feet away — taking it out " +
                "of the wedge, it only costs gain before feedback")
        }

        if (abs(n.offDb) <= tolDb) return null

        // Too loud: turn it down. Simple, and always available.
        if (n.offDb > 0) return cut(s, min(step, n.offDb / 2f), tSec,
            w.name + ": " + label(n) + " is " + db(n.offDb) +
            " dB above where this position wants it")

        // TOO QUIET — AND THIS IS THE INTERESTING ONE.
        //
        // The ratio is what is wrong, and there are two ends to a ratio.
        // Look for something in this same wedge that is above ITS target
        // and take that down instead: the balance moves the same way and
        // the loop gain moves the right way.
        val loudest = all.firstOrNull {
            it.wantDb != null && it.offDb > tolDb / 2f && it.ch != n.ch
        }
        if (loudest != null) {
            val ls = send(w.bus, loudest.ch)
            return cut(ls, min(step, loudest.offDb), tSec,
                w.name + ": " + label(n) + " is " + db(-n.offDb) +
                " dB low — bringing " + label(loudest) + " down instead " +
                "of raising it, so the balance moves without spending " +
                "any gain")
        }

        // Nothing left to cut. Only now may a send go up, and barely.
        if (s.ringProne) {
            once("bus" + w.bus + "rp" + n.ch,
                w.name + ": " + label(n) + " is low, but that microphone " +
                "has been in a ring on this stage — leaving it alone")
            return null
        }
        if (raiseBarred(w.bus, tSec)) return null
        if (s.appDb >= maxRaiseDb - 0.05f) return null
        val by = min(min(step, -n.offDb), maxRaiseDb - s.appDb)
        if (by < 0.1f) return null
        return write(s, by, tSec,
            w.name + ": " + label(n) + " is " + db(-n.offDb) + " dB low " +
            "and there is nothing left to bring down — up " + db(by) +
            " dB, " + db(s.appDb + by) + " of the " + db(maxRaiseDb) +
            " dB of headroom allowed all night")
    }

    private fun cut(s: Send, by: Float, tSec: Double, why: String):
        ParamWrite? {
        val room = maxCutDb + s.appDb          // appDb is negative here
        val d = min(by, room)
        if (d < 0.1f) return null
        return write(s, -d, tSec, why)
    }

    private fun write(s: Send, deltaDb: Float, tSec: Double, why: String):
        ParamWrite? {
        // BUILD AND CHECK THE ADDRESS BEFORE CHANGING ANY STATE.
        //
        // plan() used to filter the list at the end, after write() had
        // already banked the move. A discarded write left the class
        // believing it had moved a send it never touched, with
        // writtenDb set to a level the desk had never seen — so the
        // next reading looked like the engineer's hand, refilled the
        // night's cut budget and froze the bus for five minutes. If it
        // is not going to be sent, nothing about it may be recorded.
        val addr = osc("/ch/%02d/mix/%02d/level", s.ch + 1, s.bus)
        if (!isMonitorSend(addr)) return null

        s.appDb += deltaDb
        s.lastMoveT = tSec
        val target = s.nowDb
        s.writtenDb = target
        // And tell the map, so the next critique sees what this did.
        // Without it the keeper is open-loop: it cannot observe its own
        // effect and repeats the same correction until it runs out of
        // authority.
        map.onSend(s.bus, s.ch, target)
        notes.add(why + " · " + db(deltaDb) + " dB (net " +
            db(s.appDb) + ")")
        return ParamWrite(addr, FaderLaw.dbToFloat(target))
    }

    /**
     * A number, as text.
     *
     * Nothing in this class may put desk-supplied text through
     * String.format. Bus names are typed by the engineer, and a wedge
     * called "MON 100%" turned every log line into an
     * UnknownFormatConversionException thrown out of plan(), on every
     * tick, until the tick-failure limit switched MIXING off mid-set.
     * Numbers get formatted; names get concatenated.
     */
    private fun db(v: Float) =
        "%+.1f".format(java.util.Locale.ROOT, v)

    private val said = HashSet<String>()
    private fun once(k: String, msg: String) {
        if (said.add(k)) notes.add(msg)
    }

    private fun label(n: MonitorMap.Note) =
        "ch%02d %s".format(java.util.Locale.ROOT, n.ch + 1,
            n.role.name.lowercase().replace('_', ' '))

    /** everything it has done to the wedges, in one line */
    fun describe(): String {
        val m = moved()
        if (m.isEmpty()) return "wedges untouched"
        return m.joinToString("  ") {
            "b%d.ch%02d %+.1f".format(java.util.Locale.ROOT,
                it.bus, it.ch + 1, it.appDb)
        }
    }

    fun drainNotes(): List<String> {
        val out = ArrayList(notes)
        notes.clear()
        return out
    }
}
