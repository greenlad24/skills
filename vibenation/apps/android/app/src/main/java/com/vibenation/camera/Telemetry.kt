package com.vibenation.camera

import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.wifi.WifiManager
import android.os.BatteryManager
import android.os.Build
import android.os.PowerManager

/** Battery, heat and Wi-Fi as the drawer and the server want them. */
class Telemetry(private val ctx: Context) {
    data class Snapshot(
        val battery: Int,
        val charging: Boolean,
        val tempC: Int?,
        val wifi: String,
        val thermalWarn: Boolean,
    )

    fun read(): Snapshot {
        val bi: Intent? = ctx.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
        val level = bi?.getIntExtra(BatteryManager.EXTRA_LEVEL, -1) ?: -1
        val scale = bi?.getIntExtra(BatteryManager.EXTRA_SCALE, 100) ?: 100
        val pct = if (level >= 0 && scale > 0) (level * 100 / scale) else 100
        val status = bi?.getIntExtra(BatteryManager.EXTRA_STATUS, -1) ?: -1
        val plugged = bi?.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0) ?: 0
        val charging = plugged != 0 || status == BatteryManager.BATTERY_STATUS_CHARGING || status == BatteryManager.BATTERY_STATUS_FULL
        val t = bi?.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, Int.MIN_VALUE) ?: Int.MIN_VALUE
        val temp = if (t == Int.MIN_VALUE) null else Math.round(t / 10f)
        val thermal = if (Build.VERSION.SDK_INT >= 29) {
            val pm = ctx.getSystemService(PowerManager::class.java)
            (pm?.currentThermalStatus ?: 0) >= PowerManager.THERMAL_STATUS_SEVERE
        } else false
        return Snapshot(pct, charging, temp, wifi(), thermal)
    }

    private fun wifi(): String {
        val cm = ctx.getSystemService(ConnectivityManager::class.java) ?: return "Unknown"
        val caps = cm.getNetworkCapabilities(cm.activeNetwork) ?: return "Offline"
        if (!caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)) {
            return if (caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR)) "Mobile data"
            else if (caps.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET)) "Wired" else "Other"
        }
        var rssi = caps.signalStrength
        if (rssi == NetworkCapabilities.SIGNAL_STRENGTH_UNSPECIFIED || rssi >= 0) {
            @Suppress("DEPRECATION")
            rssi = (ctx.applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager)?.connectionInfo?.rssi ?: -127
        }
        return rssiLabel(rssi)
    }

    companion object {
        fun rssiLabel(rssi: Int): String = when {
            rssi <= -127 || rssi >= 0 -> "Wi-Fi"
            rssi >= -60 -> "Strong"
            rssi >= -70 -> "Good"
            else -> "Weak"
        }
    }
}
