package com.stagemix.app

import android.content.Context
import com.stagemix.engine.ChannelConfig
import com.stagemix.engine.Decision
import com.stagemix.engine.Role
import kotlinx.coroutines.flow.MutableStateFlow
import org.json.JSONArray
import org.json.JSONObject

/**
 * Single source of truth shared between MixerService and the Compose UI.
 * A plain singleton on StateFlows: the service writes, the UI collects.
 */
object AppState {
    /** the M18/MR18 input strip count — the only valid channel indices */
    const val MIXER_CHANNELS = 16

    enum class Conn { DISCONNECTED, CONNECTING, CONNECTED }

    data class MixerInfo(val ip: String = "", val name: String = "",
                         val model: String = "", val firmware: String = "")

    data class StripUi(
        val channel: Int,
        val name: String,
        val role: Role,
        val levelDb: Float,
        val active: Boolean,
        val frozen: Boolean,
        /** offset from snapshot on the currently viewed bus */
        val offsetDb: Float,
        val targetDb: Float,
        /** channel-doctor tone offsets (largest EQ band move, thr move) */
        val eqOffsetDb: Float = 0f,
        val thrOffsetDb: Float = 0f,
        /**
         * What is on this channel right now, in words.
         *
         * Separate from [role] on purpose, and the operator asked for it
         * in exactly those terms: "I want the software to show in the UI
         * what is the instrument in the channel right now". [role] is
         * where the channel sits in the balance; this is what the app
         * believes is plugged into it — which on a house desk with
         * inherited labels is a different and much less obvious thing.
         */
        val identLabel: String = "",
        /** true when the AUDIO settled it, not the console's label */
        val identHeard: Boolean = false,
        /** 0..1 — how much listening is behind that claim */
        val identEvidence: Float = 0f,
        /**
         * True when the app will not move this fader at all — a voice or
         * the rhythm section, once the balance is made. "Which channels
         * can this thing touch?" is the first question anyone asks of an
         * autopilot and the answer belongs on the strip.
         */
        val heldByYou: Boolean = false,
        /**
         * The operator has this channel muted on the desk — read from
         * `/ch/NN/mix/on`, never written. Worth its own flag on the
         * strip because the level meter cannot show it: metering is
         * pre-fader and pre-mute, so a muted channel looks exactly like
         * a playing one right up until you notice you cannot hear it.
         */
        val deskMuted: Boolean = false,
        /**
         * Where YOUR fader is — the level the app is bounded around.
         * The strip draws its own scale from this, so the fader on
         * screen is in the same units as the fader on the desk.
         */
        val baselineDb: Float = -10f,
        /** and where it was when the app took over, for the tick */
        val takeoverDb: Float = -10f,
        /** true while the app is actually moving this fader right now */
        val riding: Boolean = false,
    )

    val conn = MutableStateFlow(Conn.DISCONNECTED)
    /**
     * True once this session has talked to the mixer at all.
     *
     * The console screen is shown for CONNECTED only, and a ten-second
     * gap in the meters drops the state to CONNECTING — which on the
     * M18's own 2.4 GHz AP, in a room full of phones, happens during
     * shows: it is in both real logs. So mid-song the whole console was
     * being replaced by the SETUP page, complete with an IP box and a
     * "find my mixer" button that builds a NEW engine and a NEW show
     * log. One tap in the dark and the night's takeover baselines and
     * the balance the operator had kept were gone, and every channel
     * would be placed again from scratch.
     *
     * Once a night has started, a dropout is a message, not a screen.
     */
    val everConnected = MutableStateFlow(false)
    val mixer = MutableStateFlow(MixerInfo())
    val discovered = MutableStateFlow<List<MixerInfo>>(emptyList())
    val strips = MutableStateFlow<List<StripUi>>(emptyList())
    val busNames = MutableStateFlow<Map<Int, String>>(emptyMap())
    val decisions = MutableStateFlow<List<Decision>>(emptyList())
    val holdReason = MutableStateFlow<String?>(null)
    val snapshotTaken = MutableStateFlow(false)
    val directing = MutableStateFlow(false)
    /** true once there is an adopted balance being defended */
    val balanceKept = MutableStateFlow(false)
    /** the operator has muted the whole band: the engine does nothing */
    val stageMuted = MutableStateFlow(false)
    val doctorOn = MutableStateFlow(true)
    val frozenAll = MutableStateFlow(false)
    val lastError = MutableStateFlow<String?>(null)
    /**
     * WHO IS CARRYING THE SONG, for the crown on the stage plot.
     */
    val leadVocal = MutableStateFlow<Int?>(null)

    /**
     * Something the app is doing that has a known end — see [Phase].
     * Never more than one at a time on screen: the most important.
     */
    val phase = MutableStateFlow<com.stagemix.app.ui.Phase?>(null)

    /**
     * The monotonic time of the last engine tick.
     *
     * The screen shows this as a dot that flashes once a second, which
     * is the only honest answer to "is this thing alive?" — and the
     * question three nights of shadow-mode running should have raised
     * on the first evening.
     */
    val tickMs = MutableStateFlow(0L)

    /** how many channels the app actually has authority over */
    val channelsMixed = MutableStateFlow(0)

    /**
     * A monitor, as the app understands it — read from the desk, never
     * written. Drawn on the stage so the wedges are visible objects
     * rather than something the app has never looked at.
     */
    data class WedgeUi(
        val bus: Int,
        val name: String,
        val kind: String,
        /** the three loudest things in it, by channel */
        val top: List<Int> = emptyList(),
        /** the worst disagreement with what this position wants, in dB */
        val worstOffDb: Float = 0f,
        val worstCh: Int? = null,
        /**
         * The wedge as a mixer: every channel's send level, where this
         * position wants it, and how far the keeper has moved it.
         *
         * A wedge IS a mix — sixteen sends with a balance between them,
         * exactly like the mains — so it is read the same way, on
         * strips, rather than described in a paragraph.
         */
        val sendDb: Map<Int, Float> = emptyMap(),
        val targetDb: Map<Int, Float> = emptyMap(),
        val appDb: Map<Int, Float> = emptyMap(),
    )

    val wedges = MutableStateFlow<List<WedgeUi>>(emptyList())

    /**
     * OPEN THE APP AND IT MIXES.
     *
     * "the auto mix should be on by default — when the app is opened it
     *  should connect automatically (if available) and start mixing."
     *
     * This reverses the app's original default, and the reversal is
     * earned: the old default was WATCHING, chosen so that nothing
     * could ever be moved by surprise, and the result was three whole
     * shows in which nothing was moved at all. A tool that has to be
     * armed correctly before every gig, in the dark, will eventually
     * not be — and the failure is silent. Still one tap to stop, still
     * a twenty-second listen before it writes a single fader, and still
     * a switch here for anyone who wants the old behaviour.
     */
    val autoStart = MutableStateFlow(true)

    /**
     * Whether the app may correct the wedges at all.
     *
     * Separate from [directing] because it is a separate promise. The
     * mains are the app's job; the monitors are the band's ears, and
     * for most of this app's life it could not write one even by
     * accident. It can now — slightly, cut-first, following the
     * engineer's hand — and this switch is how that stays a choice.
     */
    val keepMonitors = MutableStateFlow(true)

    /** what the monitor keeper has changed, per bus, for the screen */
    data class WedgeMove(val bus: Int, val ch: Int, val db: Float)
    val wedgeMoves = MutableStateFlow<List<WedgeMove>>(emptyList())

    /**
     * Everything wrong, worst first, each with the thing to do about
     * it. Never empty — see [com.stagemix.engine.adviseOn].
     */
    val advice = MutableStateFlow<List<com.stagemix.engine.Advice>>(emptyList())

    /**
     * What it is doing right now, with a bar that fills. Always set:
     * when there is no countdown to run, this carries how much of the
     * mix is sitting where it should be.
     */
    val work = MutableStateFlow<com.stagemix.engine.Work?>(null)

    /**
     * The two numbers the master meter shows: the voice carrying the
     * song, and everything else. Their RELATIONSHIP is what this whole
     * engine exists to hold — if LEAD sits above BAND, the mix works.
     */
    val leadDb = MutableStateFlow(-128f)
    val bandDb = MutableStateFlow(-128f)

    /** which tab the console opens on — only ever set by the demo */
    @Volatile var startTab = 0

    /** when MIXING was switched on, for the show clock */
    val mixingSinceMs = MutableStateFlow(0L)

    /** channels with a ring-out notch on them right now */
    val ringNotches = MutableStateFlow<Map<Int, String>>(emptyMap())

    /** channel names read from the console's own config */
    val mixerChannelNames = MutableStateFlow<Map<Int, String>>(emptyMap())

    // ------------------------------------------------------------ config
    data class Config(
        val mixerIp: String = "",
        /** The band's rig is the default; console names refine it. */
        val channels: List<ChannelConfig> =
            com.stagemix.engine.defaultRigProfile(),
    )

    val config = MutableStateFlow(Config())

    /** Cross-night learning surface. */
    val health = MutableStateFlow<com.stagemix.engine.StageEngine.MixHealth?>(null)
    val nightsCount = MutableStateFlow(0)
    /** where tonight's show log is being written, for the export screen */
    val logPath = MutableStateFlow("")
    val tasteSummary = MutableStateFlow("")
    val lastNightSummary = MutableStateFlow("")

    fun saveBias(ctx: Context, bias: Map<com.stagemix.engine.Role, Float>) {
        val o = JSONObject()
        for ((r, v) in bias) if (kotlin.math.abs(v) > 0.01f)
            o.put(r.name, v.toDouble())
        ctx.getSharedPreferences("stagemix", Context.MODE_PRIVATE)
            .edit().putString("bias", o.toString()).apply()
        tasteSummary.value = summarizeBias(bias)
    }

    fun loadBias(ctx: Context): Map<com.stagemix.engine.Role, Float> {
        val raw = ctx.getSharedPreferences("stagemix", Context.MODE_PRIVATE)
            .getString("bias", null) ?: return emptyMap()
        return try {
            val o = JSONObject(raw)
            val out = HashMap<com.stagemix.engine.Role, Float>()
            for (k in o.keys())
                out[com.stagemix.engine.Role.valueOf(k)] =
                    o.getDouble(k).toFloat()
            tasteSummary.value = summarizeBias(out)
            out
        } catch (e: Exception) { emptyMap() }
    }

    /**
     * What the operator has told us is on each channel, by the CONSOLE'S
     * name for it.
     *
     * Kept across nights on purpose. The app can hear that a channel is
     * a moving melody in the voice band with nothing underneath, and it
     * cannot hear whether that is a singer or a saxophone — they are the
     * same thing to a hundred-bin spectrum. On the rig this was written
     * for, the channel labelled SAXOPHONE is a singer and the one
     * labelled UTILITY 3 is the saxophone, and neither the ears nor the
     * labels will ever sort that out. A person does it once.
     */
    fun saveKnownInstruments(ctx: Context, known: Map<String, com.stagemix.engine.Role>) {
        val o = JSONObject()
        for ((n, r) in known) o.put(n, r.name)
        ctx.getSharedPreferences("stagemix", Context.MODE_PRIVATE)
            .edit().putString("known_instruments", o.toString()).apply()
    }

    fun loadKnownInstruments(ctx: Context): Map<String, com.stagemix.engine.Role> {
        val raw = ctx.getSharedPreferences("stagemix", Context.MODE_PRIVATE)
            .getString("known_instruments", null) ?: return emptyMap()
        return try {
            val o = JSONObject(raw)
            val out = HashMap<String, com.stagemix.engine.Role>()
            for (k in o.keys())
                // stored prefs are not a trusted source of role names
                runCatching {
                    out[k] = com.stagemix.engine.Role.valueOf(o.getString(k))
                }
            out
        } catch (e: Exception) { emptyMap() }
    }

    /**
     * The balance this engineer keeps arriving at, across nights.
     *
     * The single most valuable thing the app owns: every time they
     * press KEEP it learns where they actually put each instrument, and
     * that is a far better answer than the built-in pyramid's guess.
     * Losing it on a restart would throw away the only real knowledge
     * the thing has.
     */
    fun saveLearnedBalance(ctx: Context, snap: Map<String, Pair<Float, Int>>) {
        val o = JSONObject()
        for ((k, v) in snap)
            o.put(k, JSONObject().put("s", v.first.toDouble()).put("n", v.second))
        ctx.getSharedPreferences("stagemix", Context.MODE_PRIVATE)
            .edit().putString("learned_balance", o.toString()).apply()
    }

    fun loadLearnedBalance(ctx: Context): Map<String, Pair<Float, Int>> {
        val raw = ctx.getSharedPreferences("stagemix", Context.MODE_PRIVATE)
            .getString("learned_balance", null) ?: return emptyMap()
        return try {
            val o = JSONObject(raw)
            val out = HashMap<String, Pair<Float, Int>>()
            for (k in o.keys()) runCatching {
                val e = o.getJSONObject(k)
                out[k] = e.getDouble("s").toFloat() to e.getInt("n")
            }
            out
        } catch (e: Exception) { emptyMap() }
    }

    private fun summarizeBias(bias: Map<com.stagemix.engine.Role, Float>): String =
        bias.filterValues { kotlin.math.abs(it) > 0.01f }.entries
            .sortedByDescending { kotlin.math.abs(it.value) }
            .joinToString(" · ") {
                "${it.key.name.lowercase().replace('_', ' ')} %+.1f"
                    .format(it.value)
            }

    fun saveNight(ctx: Context, h: com.stagemix.engine.StageEngine.MixHealth) {
        val p = ctx.getSharedPreferences("stagemix", Context.MODE_PRIVATE)
        val n = p.getInt("nights", 0) + 1
        val summary = "night $n: vocal on top ${h.vocalOnTopPct}% · " +
                "in place ${h.inPlacePct}% · ${h.overrides} overrides"
        p.edit().putInt("nights", n).putString("last_night", summary).apply()
        nightsCount.value = n
        lastNightSummary.value = summary
    }

    fun loadNights(ctx: Context) {
        val p = ctx.getSharedPreferences("stagemix", Context.MODE_PRIVATE)
        nightsCount.value = p.getInt("nights", 0)
        lastNightSummary.value = p.getString("last_night", "") ?: ""
    }

    /** the two switches that change what the app does on its own */
    fun saveSwitches(ctx: Context) {
        ctx.getSharedPreferences("stagemix", Context.MODE_PRIVATE).edit()
            .putBoolean("auto_start", autoStart.value)
            .putBoolean("keep_monitors", keepMonitors.value)
            .apply()
    }

    fun loadSwitches(ctx: Context) {
        val p = ctx.getSharedPreferences("stagemix", Context.MODE_PRIVATE)
        autoStart.value = p.getBoolean("auto_start", true)
        keepMonitors.value = p.getBoolean("keep_monitors", true)
    }

    fun save(ctx: Context) {
        val c = config.value
        val o = JSONObject()
        o.put("ip", c.mixerIp)
        o.put("channels", JSONArray().apply {
            c.channels.forEach { ch ->
                put(JSONObject().put("i", ch.index).put("n", ch.name)
                    .put("r", ch.role.name))
            }
        })
        ctx.getSharedPreferences("stagemix", Context.MODE_PRIVATE)
            .edit().putString("config", o.toString()).apply()
    }

    fun load(ctx: Context) {
        val raw = ctx.getSharedPreferences("stagemix", Context.MODE_PRIVATE)
            .getString("config", null) ?: return
        try {
            val o = JSONObject(raw)
            val chs = ArrayList<ChannelConfig>()
            val ja = o.getJSONArray("channels")
            val seen = HashSet<Int>()
            for (i in 0 until ja.length()) {
                val c = ja.getJSONObject(i)
                // Stored prefs are not a trusted source of channel
                // numbers: an index of -1 or 16 builds /ch/00/… or
                // /ch/17/…, addresses the console has no answer for and
                // silently drops, leaving the channel dead all night.
                val idx = c.getInt("i")
                if (idx !in 0 until MIXER_CHANNELS || !seen.add(idx)) continue
                // THE RIG'S STRUCTURE IS NOT THE OPERATOR'S TO LOSE.
                //
                // Saved preferences carry the name and the role — the
                // two things a person edits. `locked` and `pairWith`
                // are facts about the rig that live in the profile:
                // microphones taped to a drum kit, two DIs that are one
                // bass, two channels that are one piano. Rebuilding a
                // ChannelConfig from prefs alone quietly dropped both,
                // so the first time this app saved anything, the kick,
                // the snare and BOTH bass DIs stopped being locked —
                // and on the next real night the listener duly re-roled
                // "BASS DI" and "DI 2" to congas, which is exactly what
                // the lock exists to prevent. Structure comes from the
                // profile, by index, every time.
                val shape = com.stagemix.engine.defaultRigProfile()
                    .getOrNull(idx)
                chs.add(ChannelConfig(idx, c.getString("n"),
                    Role.valueOf(c.getString("r")),
                    locked = shape?.locked ?: false,
                    pairWith = shape?.pairWith))
            }
            config.value = Config(o.optString("ip"),
                if (chs.isEmpty()) Config().channels else chs)
        } catch (e: Exception) {
            // corrupted prefs -> defaults; never crash on startup
        }
    }
}
