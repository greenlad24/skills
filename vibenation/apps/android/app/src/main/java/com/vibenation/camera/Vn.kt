package com.vibenation.camera

import android.content.Context
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.util.TypedValue

/** Design tokens from designs/vibenation-canvas (warm studio glass). */
object Vn {
    val BG = Color.parseColor("#000000")
    val IMAGE_BG = Color.parseColor("#070403")
    val PANEL = Color.parseColor("#D1100B08") // rgba(16,11,8,0.82)
    val TEXT = Color.parseColor("#F5EEE6")
    val TEXT_2 = Color.parseColor("#C9BDB1")
    val TEXT_3 = Color.parseColor("#9C9084")
    val GLASS = Color.parseColor("#0FFFECDC") // rgba(255,236,220,0.06)
    val GLASS_EDGE = Color.parseColor("#24FFECDC") // 0.14
    val GLASS_EDGE_SOFT = Color.parseColor("#1FFFECDC") // 0.12
    val CARD = Color.parseColor("#0DFFECDC") // 0.05
    val CARD_EDGE = Color.parseColor("#0FFFECDC") // 0.06
    val TALLY_OFF = Color.parseColor("#2A211B")
    val EMBER = Color.parseColor("#FF9A5A")

    /** On air = blue. */
    val LIVE = Color.parseColor("#3D8BFF")
    val LIVE_DEEP = Color.parseColor("#1F66E0")
    /** Errors only. */
    val ERROR = Color.parseColor("#FF5A52")
    /** Warnings. */
    val WARN = Color.parseColor("#FFB224")
    /** Claude / AI. */
    val LILAC = Color.parseColor("#B9A6FF")
    /** Healthy standby dot. */
    val IDLE = Color.parseColor("#7D7268")

    private val cache = HashMap<String, Typeface>()
    private fun font(ctx: Context, file: String, weight: Int): Typeface =
        cache.getOrPut("$file$weight") {
            try {
                Typeface.Builder(ctx.assets, "fonts/$file")
                    .setFontVariationSettings("'wght' $weight")
                    .build() ?: Typeface.DEFAULT_BOLD
            } catch (_: Throwable) {
                Typeface.create(Typeface.SANS_SERIF, if (weight >= 600) Typeface.BOLD else Typeface.NORMAL)
            }
        }

    fun sora(ctx: Context, w: Int = 700) = font(ctx, "sora.ttf", w)
    fun sans(ctx: Context, w: Int = 400) = font(ctx, "dmsans.ttf", w)
    fun mono(ctx: Context, w: Int = 700) = font(ctx, "jetbrainsmono.ttf", w)

    fun dp(ctx: Context, v: Float): Int =
        TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v, ctx.resources.displayMetrics).toInt()

    fun rounded(fill: Int, radiusPx: Float, stroke: Int = 0, strokePx: Int = 0) = GradientDrawable().apply {
        setColor(fill)
        cornerRadius = radiusPx
        if (strokePx > 0) setStroke(strokePx, stroke)
    }
}
