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
            for (i in 0 until ja.length()) {
                val c = ja.getJSONObject(i)
                chs.add(ChannelConfig(c.getInt("i"), c.getString("n"),
                    Role.valueOf(c.getString("r"))))
            }
            config.value = Config(o.optString("ip"),
                if (chs.isEmpty()) Config().channels else chs)
        } catch (e: Exception) {
            // corrupted prefs -> defaults; never crash on startup
        }
    }
}
