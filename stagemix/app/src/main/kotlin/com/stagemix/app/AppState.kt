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
    )

    val conn = MutableStateFlow(Conn.DISCONNECTED)
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
    val doctorOn = MutableStateFlow(true)
    val frozenAll = MutableStateFlow(false)
    val lastError = MutableStateFlow<String?>(null)
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
                chs.add(ChannelConfig(idx, c.getString("n"),
                    Role.valueOf(c.getString("r"))))
            }
            config.value = Config(o.optString("ip"),
                if (chs.isEmpty()) Config().channels else chs)
        } catch (e: Exception) {
            // corrupted prefs -> defaults; never crash on startup
        }
    }
}
