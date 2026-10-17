package com.vibenation.camera

import android.content.Context
import android.net.Uri

/** Remembered between launches so a phone can rejoin as the same camera. */
class Prefs(ctx: Context) {
    private val p = ctx.getSharedPreferences("vibenation-camera", Context.MODE_PRIVATE)

    var invite: String?
        get() = p.getString("invite", null)
        set(v) = p.edit().putString("invite", v).apply()
    var base: String
        get() = p.getString("base", DEFAULT_BASE) ?: DEFAULT_BASE
        set(v) = p.edit().putString("base", v).apply()
    var name: String?
        get() = p.getString("name", null)
        set(v) = p.edit().putString("name", v).apply()
    var camId: Int?
        get() = p.getInt("camId", 0).takeIf { it > 0 }
        set(v) = p.edit().putInt("camId", v ?: 0).apply()
    var guides: Boolean
        get() = p.getBoolean("guides", false)
        set(v) = p.edit().putBoolean("guides", v).apply()

    companion object {
        const val DEFAULT_BASE = "https://app.jeeznews.com"

        /** Accepts https://<host>/cam?k=…, vibenation://cam?k=… or a bare invite. Returns (base, invite). */
        fun parseInvite(text: String?): Pair<String, String>? {
            val s = text?.trim().orEmpty()
            if (s.isEmpty()) return null
            val uri = try { Uri.parse(s) } catch (_: Exception) { null }
            if (uri != null && uri.scheme != null) {
                val k = uri.getQueryParameter("k")?.takeIf { it.isNotBlank() } ?: return null
                val base = when (uri.scheme) {
                    "https" -> "https://${uri.encodedAuthority}"
                    "vibenation" -> DEFAULT_BASE
                    else -> return null // never send the camera over plain http
                }
                return base to k
            }
            // Bare token (two base64url parts joined by a dot).
            return if (Regex("^[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+$").matches(s)) DEFAULT_BASE to s else null
        }
    }
}
