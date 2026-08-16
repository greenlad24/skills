package com.stagemix.engine

/**
 * Everything that is wrong, in the order it matters, each with the
 * thing to do about it.
 *
 * "In any case there's an error it should be shown as well. All types
 *  of errors (not mixing is also an error) — it should tell what should
 *  be done to fix it."
 *
 * The second half of that sentence is the whole point of this file. An
 * app that says FAULT has told you that you have a problem, which you
 * already knew; the useful part is the sentence after it. So an Advice
 * is not a message, it is a pair: what is true, and what to press.
 *
 * The first half matters just as much, and it is the lesson of three
 * nights that were never mixed. **Not mixing is a fault.** The app sat
 * there for three shows, connected, healthy, reading meters, drawing a
 * beautiful screen, and writing nothing — and nothing on it was red,
 * because by its own reckoning nothing had gone wrong. A tool whose
 * entire purpose is to mix, and which is not mixing, is broken, and it
 * has to say so in the same colour it uses for a dead console.
 *
 * This is a pure function of a snapshot so that it can be tested
 * without an Android device, a console or a band.
 */

enum class Level {
    /** worth knowing */
    NOTE,
    /** the show is fine but this wants attention before the next set */
    WARN,
    /** it is not doing its job */
    FAULT,
}

data class Advice(
    /** stable, so the screen does not re-animate a message that is still true */
    val key: String,
    val level: Level,
    /** what is true, in the operator's language */
    val what: String,
    /** and what to do about it — never blank */
    val doThis: String,
)

/** everything the adviser needs to know, and nothing Android-shaped */
data class Situation(
    val connected: Boolean = false,
    val connecting: Boolean = false,
    val everConnected: Boolean = false,
    val autoStart: Boolean = true,
    val directing: Boolean = false,
    val frozenAll: Boolean = false,
    val stageMuted: Boolean = false,
    val balanceKept: Boolean = false,
    val doctorOn: Boolean = true,
    val channelsTotal: Int = 16,
    val channelsMixed: Int = 0,
    val frozenChannels: Int = 0,
    /** how long since a meter frame arrived */
    val metersAgeSec: Float = 0f,
    /** the last exception the tick loop caught, if any */
    val engineError: String? = null,
    val consecutiveErrors: Int = 0,
    /** a ring is being hunted right now */
    val hunting: Boolean = false,
    val ringNotches: Int = 0,
    /** how many monitor buses were read off the desk */
    val wedgesRead: Int = 0,
    /** and how many of them are more than a couple of dB out */
    val wedgesOut: Int = 0,
    val monitorsEnabled: Boolean = true,
    /** seconds since MIXING was switched on, or -1 */
    val mixingSec: Double = -1.0,
)

/**
 * The list, worst first. Never empty of meaning: when everything is
 * genuinely fine it returns a single NOTE saying so, because a blank
 * panel and a broken panel look identical, which is the mistake this
 * whole app is built around not making twice.
 */
fun adviseOn(s: Situation): List<Advice> {
    val out = ArrayList<Advice>()

    // ---- can it reach the desk at all
    if (!s.connected && !s.connecting) out.add(Advice(
        "conn", Level.FAULT,
        if (s.everConnected) "Lost the mixer — nothing is being sent"
        else "Not connected to the mixer",
        "Check the tablet is on the M18's Wi-Fi, then tap CONNECT. " +
        "The desk keeps the last mix it was given, so the show is not " +
        "affected while this is out."))
    else if (s.connecting) out.add(Advice(
        "conn.try", Level.NOTE, "Looking for the mixer",
        "Nothing to do — it finds the desk by itself on the M18's " +
        "own Wi-Fi. If this does not clear in about ten seconds, the " +
        "tablet is on the wrong network."))

    if (s.connected && s.metersAgeSec > 2f) out.add(Advice(
        "meters", Level.FAULT,
        "Meters have stopped — every fader is held where it is",
        "Usually the venue's 2.4 GHz Wi-Fi rather than a fault. It " +
        "recovers by itself; nothing moves until it does. Move the " +
        "tablet closer to the desk if it keeps happening."))

    // ---- THE ONE THAT COST THREE NIGHTS
    if (s.connected && !s.directing) out.add(Advice(
        "notmixing", Level.FAULT,
        "NOT MIXING — the app is only watching",
        if (s.autoStart)
            "It should have started by itself. Tap MIX to take the " +
            "mains now. Everything on the screen below is what it " +
            "WOULD have done, not what it did."
        else
            "Tap MIX to take the mains. Auto-start is switched off in " +
            "SETUP, so it will not do this by itself."))

    if (s.frozenAll) out.add(Advice(
        "frozen", Level.WARN,
        "FROZEN — nothing will move until you release it",
        "Tap FREEZE again to resume. Nothing is lost; every fader is " +
        "exactly where it was when you pressed it."))

    if (s.stageMuted) out.add(Advice(
        "muted", Level.WARN, "The band is muted on the desk",
        "Nothing to fix here — the app reads your mute keys and will " +
        "not try to balance a silent stage. It picks up when you " +
        "unmute."))

    // ---- partial takeover: the failure that hides
    val missing = s.channelsTotal - s.channelsMixed
    if (s.connected && s.directing && s.channelsMixed > 0 && missing > 0)
        out.add(Advice(
            "partial", Level.FAULT,
            "Only ${s.channelsMixed} of ${s.channelsTotal} channels " +
            "answered — $missing are not being mixed",
            "Tap MIX off and on to ask them again. This is dropped " +
            "Wi-Fi packets, not broken channels, and it matters before " +
            "the first song rather than in the morning."))

    if (s.consecutiveErrors > 0) out.add(Advice(
        "err", if (s.consecutiveErrors >= 3) Level.FAULT else Level.WARN,
        "Something went wrong inside the app" +
            (s.engineError?.let { ": $it" } ?: ""),
        "It keeps running and the desk holds your last mix. Five in a " +
        "row and it stops writing on its own — if that happens, tap " +
        "MIX off and on."))

    // ---- feedback
    if (s.hunting) out.add(Advice(
        "ring", Level.FAULT, "Feedback — finding which microphone it is in",
        "Give it a few seconds. It is measuring every channel at the " +
        "ringing frequency and will cut the one that is in the loop. " +
        "Pull the wedge down if it is unbearable; it will follow you."))

    // ---- monitors
    if (s.connected && s.wedgesRead == 0) out.add(Advice(
        "wedges", Level.WARN, "The monitors have not been read yet",
        "It reads all six buses just after takeover. Until then it " +
        "cannot balance a wedge or tell you what is in one."))
    else if (s.wedgesOut > 0 && !s.monitorsEnabled) out.add(Advice(
        "wedgesoff", Level.NOTE,
        "${s.wedgesOut} monitor${if (s.wedgesOut > 1) "s are" else " is"} " +
        "out of balance, and monitor keeping is off",
        "Turn on KEEP MONITORS in SETUP to let it correct them " +
        "slightly, or press REBALANCE to do it once."))

    // ---- balance
    if (s.connected && s.directing && !s.balanceKept && s.mixingSec > 180)
        out.add(Advice(
            "keep", Level.WARN,
            "No balance has been kept — it is still deciding for itself",
            "When it sounds right, press KEEP. That balance becomes the " +
            "thing it defends all night instead of re-deciding."))

    if (s.connected && s.directing && !s.doctorOn) out.add(Advice(
        "doctor", Level.NOTE, "EQ and compression are switched off",
        "Faders only. Turn EQ + COMP on in SETUP if you want it to set " +
        "the high-pass and the compressor an engineer would at " +
        "soundcheck."))

    if (out.none { it.level != Level.NOTE }) out.add(0, Advice(
        "ok", Level.NOTE, "Everything is working",
        "Mixing, meters arriving, monitors read. Nothing needs doing."))

    return out.sortedByDescending { it.level.ordinal }
}

/**
 * What it is doing right now, always — with a bar that fills.
 *
 * "The progress the app is doing should be shown at all times
 *  (including a progress bar)."
 *
 * The hard case is not the twenty-second listen or the eight-second
 * feedback hunt; those have obvious deadlines. It is the other three
 * hours, when the correct behaviour is to do almost nothing. A bar that
 * disappears whenever the app is working properly teaches you to read
 * an empty screen as normal — which is exactly how three nights of not
 * mixing went unnoticed. So when there is no countdown to show, the bar
 * shows how much of the mix is where it should be, and that number
 * moves all night.
 */
data class Work(
    val key: String,
    val label: String,
    val detail: String,
    /** 0..1, always meaningful */
    val frac: Float,
    /** a countdown, when there is one */
    val secsLeft: Int? = null,
    val alarm: Boolean = false,
)

/** the steady state: how much of the mix is sitting where it belongs */
fun holdingWork(inPlace: Int, total: Int, kept: Boolean): Work {
    val f = if (total <= 0) 0f else inPlace.toFloat() / total
    return Work(
        key = "holding",
        label = if (kept) "Holding the balance you kept"
                else "Finding the balance",
        detail = "$inPlace of $total channels sitting where they should be" +
            if (kept) "" else " — press KEEP when it sounds right",
        frac = f)
}
