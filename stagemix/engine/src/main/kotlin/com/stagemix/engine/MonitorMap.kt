package com.stagemix.engine

import kotlin.math.abs

/**
 * What is in each wedge, and what ought to be.
 *
 * "The app can do rebalancing to the monitors but in a different way to
 * the way it does on the outside. It needs to understand the current
 * balance of each monitor separately and then adjust it slightly based
 * on the position of it — and if the sound engineer is changing that
 * balance, understand what's happening and go with it rather than fight
 * it."
 *
 * This class is the understanding half. It reads every channel's send
 * to every monitor bus off the console, works out what each wedge is
 * FOR from the name the engineer gave it, and says — in dB, per
 * channel — how far the mix in that wedge is from what a monitor mix
 * for that position wants to be.
 *
 * It writes nothing. Not one address. What it produces is a critique,
 * for the log and the screen, and the material a keeper would act on
 * later. That separation is deliberate: monitors are the band's ears,
 * the loudest single cause of feedback on any stage is a wedge send,
 * and the first version of anything that touches them should be one
 * that cannot.
 *
 * ## The positions on this stage, in the operator's own words
 *
 *  · CENTRE (bus 1) — the singer's wedge. "Vocals at high volume (but
 *    not feedbacking volume), no drums, DI1 (the acoustic guitar) at
 *    good volume, all the rest balanced at lower volumes."
 *  · GUITAR (bus 2, labelled "piano monitor") — "guitar at higher
 *    volume, vocals, no drums, and all the rest balanced at lower
 *    volumes."
 *  · BASS — "bass and congas a little bit on top, all the rest balanced
 *    (without drums) at lower volumes."
 *  · DRUM IN-EAR (bus 3) — "for drums the in-ear is the drums", with a
 *    balanced mix under them.
 *  · PLAYER IN-EAR (bus 6) — "piano + bass": the piano and DI2 above a
 *    balanced mix.
 *
 * The generalisation, which is what the code encodes: an in-ear wants
 * that player's own instrument on top of a complete mix; a wedge wants
 * that player's own instrument on top of a partial one, with the drums
 * left out because they arrive over the top of the stage anyway.
 */
class MonitorMap {

    /** the six monitor buses on an M18/X-Air */
    val buses = AUX_SEND_FIRST..AUX_SEND_LAST

    enum class Kind {
        /** the singer's wedge: voices first */
        CENTRE_VOCAL,
        /** a guitarist's wedge */
        GUITAR,
        /** the bass player's wedge */
        BASS,
        /** the drummer's ears */
        DRUM_IEM,
        /** somebody else's ears — keys, bass, a horn player */
        PLAYER_IEM,
        /** named something this cannot read */
        UNKNOWN,
    }

    /** one monitor, as the console has it right now */
    class Wedge(val bus: Int, val name: String, val kind: Kind) {
        /** channel -> send level in dB, as read from the desk */
        val sends = HashMap<Int, Float>()
        /** the level the engineer had it at when we last looked */
        val known = HashMap<Int, Float>()
        var master: Float? = null
    }

    private val wedges = LinkedHashMap<Int, Wedge>()

    fun onBusName(bus: Int, name: String) {
        val k = kindOf(name, bus)
        val w = wedges[bus]
        if (w == null || w.name != name)
            wedges[bus] = Wedge(bus, name, k).also { nw ->
                w?.sends?.forEach { (c, v) -> nw.sends[c] = v }
            }
    }

    fun onSend(bus: Int, ch: Int, db: Float) {
        val w = wedges.getOrPut(bus) { Wedge(bus, "bus $bus", kindOf("", bus)) }
        w.sends[ch] = db
    }

    fun wedge(bus: Int): Wedge? = wedges[bus]
    fun all(): List<Wedge> = wedges.values.sortedBy { it.bus }

    /**
     * What is this monitor FOR? Read off the name the engineer typed,
     * because they are the only person who knows — and on this rig the
     * guitarist's wedge is called "piano monitor", which no amount of
     * listening would ever have worked out.
     */
    fun kindOf(name: String, bus: Int): Kind {
        val n = name.lowercase()
        fun has(vararg k: String) = k.any { it in n }
        return when {
            has("drum", "drm", "dr ") && has("ear", "iem") -> Kind.DRUM_IEM
            has("ear", "iem", "in ear", "in-ear") -> Kind.PLAYER_IEM
            has("centre", "center", "cen", "vocal", "vox", "sing") ->
                Kind.CENTRE_VOCAL
            has("bass", "bs ") -> Kind.BASS
            has("gtr", "guitar", "piano", "keys") -> Kind.GUITAR
            has("drum", "drm") -> Kind.DRUM_IEM
            else -> Kind.UNKNOWN
        }
    }

    /**
     * How loud a role wants to be in this kind of monitor, in dB
     * relative to the wedge's own average — the same idea as the mains
     * pyramid, one ladder per position.
     *
     * `null` means "should not be in this monitor at all", which on a
     * wedge is the drum kit: it is three feet away and arrives over the
     * top of everything.
     */
    fun wants(kind: Kind, role: Role, isKit: Boolean = false): Float? {
        // "NO DRUMS" MEANS THE KIT, NOT ALL PERCUSSION.
        //
        // A wedge on this stage is three feet from a drum kit and gets
        // it acoustically whether anybody sends it or not; putting it
        // in the wedge as well only costs gain before feedback. The
        // congas are a different matter — they are across the stage,
        // they are "the rest" in most wedges, and the bass player
        // explicitly wants them. In-ears seal the ears off from the
        // room, so they need everything, kit included.
        val wedge = kind == Kind.CENTRE_VOCAL || kind == Kind.GUITAR ||
                    kind == Kind.BASS
        if (isKit && wedge) return null
        return when (kind) {
        Kind.CENTRE_VOCAL -> when (role) {
            Role.VOCAL -> 8f
            Role.BACKING_VOCAL -> 4f
            // DI 1 is the acoustic guitar on this rig, and the singer
            // plays it: "DI1 at good volume"
            Role.RHYTHM_GTR -> 3f
            Role.FOUNDATION -> -3f
            Role.TALK -> null
            else -> -2f
        }
        Kind.GUITAR -> when (role) {
            Role.SOLO_GTR -> 8f
            Role.RHYTHM_GTR -> 4f
            Role.VOCAL -> 4f
            Role.BACKING_VOCAL -> 0f
            Role.FOUNDATION -> -3f
            Role.TALK -> null
            else -> -2f
        }
        Kind.BASS -> when (role) {
            Role.FOUNDATION -> 6f
            // "bass and congas a little bit on top"
            Role.PERCUSSION -> 2f
            Role.VOCAL -> 0f
            Role.TALK -> null
            else -> -3f
        }
        // "for drums the in-ear is the drums" — the KIT on top, not
        // merely the PERCUSSION role. The kick is FOUNDATION, so a
        // role-only ladder put it a rung UNDER the snare in the
        // drummer's own ears; isKit fixes that by promoting the whole
        // kit above everything, with the congas just under and the
        // bass guitar present but below the kit.
        Kind.DRUM_IEM -> when {
            isKit -> 7f
            role == Role.PERCUSSION -> 6f
            role == Role.FOUNDATION -> 2f
            role == Role.VOCAL -> 2f
            role == Role.TALK -> null
            else -> -1f
        }
        // "piano + bass ... the piano and DI2" on top. Here the kit is
        // NOT the point — it is part of the balanced mix underneath, so
        // it must not be promoted the way FOUNDATION alone would drag
        // the kick up next to the bass DI.
        Kind.PLAYER_IEM -> when {
            isKit -> -1f
            role == Role.KEYS -> 6f
            role == Role.FOUNDATION -> 4f
            role == Role.VOCAL -> 2f
            role == Role.TALK -> null
            else -> -1f
        }
        Kind.UNKNOWN -> null
        }
    }

    /** one channel's standing in one wedge */
    data class Note(val ch: Int, val role: Role, val nowDb: Float,
                    val wantDb: Float?, val offDb: Float)

    /**
     * The critique: for each channel in this wedge, how far its send is
     * from where a monitor mix for this position would put it.
     *
     * Measured against the wedge's OWN average rather than an absolute
     * level, because the only person who decides how loud a monitor is
     * is the person standing in front of it. This says "the vocal is
     * four dB lower than it should be RELATIVE to the rest of what is
     * in here" — never "this wedge should be louder".
     */
    fun critique(bus: Int, roles: Map<Int, Role>,
                 kit: Set<Int> = emptySet(),
                 minChannels: Int = 3): List<Note> {
        val w = wedges[bus] ?: return emptyList()
        if (w.kind == Kind.UNKNOWN) return emptyList()
        val live = w.sends.filter { it.value > MONITOR_FLOOR_DB }
        if (live.size < minChannels) return emptyList()

        // THE COMPARED SET IS THE SAME SET ON BOTH SIDES.
        //
        // Two separate ways of getting this wrong, both of which end
        // with a whole wedge cut to its caps in the middle of a song.
        //
        // First, a send the engineer never routed reads −90 dB. Judged
        // against a ladder it is seventy dB "too quiet", it sorts to
        // the top of the critique as the worst problem in the wedge,
        // and since no amount of work can ever satisfy it, the keeper
        // cuts everything else in that wedge to the floor trying. A
        // send that is OFF is not a balance error; it is a routing
        // decision, and it is not ours.
        //
        // Second, the reference level and the ladder centre have to be
        // averaged over the SAME channels. Take the level from every
        // live send but the ladder only from the ones that have a role
        // and a rung, and the difference between those two sets lands
        // on every channel as a uniform bias — one roleless channel
        // sitting quietly at −55 dB in a −14 dB wedge was enough to
        // make all six sends read as ~7 dB too loud. Cutting cannot
        // remove that bias, because cutting moves the mean too; it just
        // runs everything to the cap.
        //
        // So: build the compared set first, and take both averages from
        // it. What is left is the shape, which is the only thing this
        // app has an opinion about. How loud the wedge is stays with
        // the person standing in front of it.
        val compared = ArrayList<Triple<Int, Role, Float>>()
        for ((ch, db) in w.sends.entries.sortedBy { it.key }) {
            if (db <= MONITOR_FLOOR_DB) continue          // off, not quiet
            val role = roles[ch] ?: continue              // unknown, not ours
            val rung = wants(w.kind, role, ch in kit) ?: continue
            compared.add(Triple(ch, role, rung))
        }
        if (compared.size < minChannels) return emptyList()
        val mean = compared.map { w.sends[it.first]!! }.average().toFloat()
        val ladderMean = compared.map { it.third }.average().toFloat()

        val out = ArrayList<Note>()
        // things that should not be in this wedge at all, and are
        for ((ch, db) in w.sends.entries.sortedBy { it.key }) {
            val role = roles[ch] ?: continue
            if (wants(w.kind, role, ch in kit) == null && db > MONITOR_FLOOR_DB)
                out.add(Note(ch, role, db, null, db - MONITOR_FLOOR_DB))
        }
        for ((ch, role, rung) in compared) {
            val target = mean + (rung - ladderMean)
            out.add(Note(ch, role, w.sends[ch]!!, target,
                w.sends[ch]!! - target))
        }
        return out.sortedByDescending { abs(it.offDb) }
    }

    /**
     * The one line per wedge that says what it is and what is on top of
     * it — the thing to read first, and the thing that was missing from
     * every log so far: the monitors were never even looked at.
     */
    fun describe(bus: Int, names: Map<Int, String>): String {
        val w = wedges[bus] ?: return "bus $bus — nothing read"
        val live = w.sends.filter { it.value > MONITOR_FLOOR_DB }
            .entries.sortedByDescending { it.value }
        if (live.isEmpty()) return "bus %02d %-16s (%s) — empty"
            .format(java.util.Locale.ROOT, bus, w.name.take(16), w.kind.name)
        return ("bus %02d %-16s (%-12s) %d channels, loudest: %s")
            .format(java.util.Locale.ROOT, bus, w.name.take(16),
                w.kind.name, live.size,
                live.take(4).joinToString("  ") {
                    "%s %+.1f".format(java.util.Locale.ROOT,
                        (names[it.key] ?: "ch%02d".format(it.key + 1)).take(10),
                        it.value)
                })
    }

    companion object {
        /** below this a send is off, not quiet */
        const val MONITOR_FLOOR_DB = -60f
    }
}
