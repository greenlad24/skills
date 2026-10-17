package com.vibenation.camera

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.drawable.ClipDrawable
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.LayerDrawable
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView

/** Small line icons drawn from 24×24 paths (chevrons, lock). */
class IconView(context: Context, var kind: Kind, var color: Int = Vn.TEXT) : View(context) {
    enum class Kind { CHEVRON_LEFT, CHEVRON_RIGHT, LOCK, UNLOCK }

    private val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
    }
    private val path = Path()

    override fun onDraw(canvas: Canvas) {
        val s = minOf(width, height) / 24f
        canvas.save()
        canvas.translate((width - 24 * s) / 2, (height - 24 * s) / 2)
        canvas.scale(s, s)
        paint.color = color
        paint.strokeWidth = 2.2f
        path.reset()
        when (kind) {
            Kind.CHEVRON_LEFT -> { path.moveTo(15f, 6f); path.lineTo(9f, 12f); path.lineTo(15f, 18f) }
            Kind.CHEVRON_RIGHT -> { path.moveTo(9f, 6f); path.lineTo(15f, 12f); path.lineTo(9f, 18f) }
            Kind.LOCK, Kind.UNLOCK -> {
                paint.strokeWidth = 2f
                path.addRoundRect(5f, 11f, 19f, 21f, 2f, 2f, Path.Direction.CW)
                path.moveTo(8f, 11f); path.lineTo(8f, 7f)
                path.arcTo(8f, 3f, 16f, 11f, 180f, 180f, false)
                if (kind == Kind.LOCK) path.lineTo(16f, 11f) else path.lineTo(16f, 8f)
            }
        }
        canvas.drawPath(path, paint)
        canvas.restore()
    }
}

/** Rule-of-thirds framing guides (off by default; only drawn when switched on). */
class GuidesView(context: Context) : View(context) {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.argb(90, 245, 238, 230)
        strokeWidth = Vn.dp(context, 1f).toFloat()
    }
    override fun onDraw(canvas: Canvas) {
        val w = width.toFloat(); val h = height.toFloat()
        for (i in 1..2) {
            canvas.drawLine(w * i / 3, 0f, w * i / 3, h, paint)
            canvas.drawLine(0f, h * i / 3, w, h * i / 3, paint)
        }
        val c = Vn.dp(context, 10f).toFloat()
        canvas.drawLine(w / 2 - c, h / 2, w / 2 + c, h / 2, paint)
        canvas.drawLine(w / 2, h / 2 - c, w / 2, h / 2 + c, paint)
    }
}

/** Frosted pill button used in the drawer (min 44dp tall). */
open class GlassButton(context: Context, text: String) : LinearLayout(context) {
    val label = TextView(context).apply {
        this.text = text
        setTextColor(Vn.TEXT)
        textSize = 12f
        typeface = Vn.sans(context, 700)
        gravity = Gravity.CENTER
    }
    init {
        orientation = HORIZONTAL
        gravity = Gravity.CENTER
        minimumHeight = Vn.dp(context, 44f)
        val pad = Vn.dp(context, 10f)
        setPadding(pad, 0, pad, 0)
        background = Vn.rounded(Vn.CARD, Vn.dp(context, 12f).toFloat(), Vn.GLASS_EDGE_SOFT, Vn.dp(context, 1f))
        isClickable = true
        isFocusable = true
        addView(label)
    }
}

/**
 * Press and hold for [holdMs] to fire [onUnlocked]. A fill sweeps across while held.
 */
@SuppressLint("ViewConstructor", "ClickableViewAccessibility")
class HoldButton(context: Context, private val holdMs: Long, private val onUnlocked: () -> Unit) : GlassButton(context, "Hold to unlock") {
    val icon = IconView(context, IconView.Kind.LOCK).apply {
        layoutParams = LayoutParams(Vn.dp(context, 14f), Vn.dp(context, 14f)).apply { marginEnd = Vn.dp(context, 6f) }
    }
    private val fill = ClipDrawable(
        GradientDrawable().apply { setColor(Color.argb(70, 61, 139, 255)); cornerRadius = Vn.dp(context, 12f).toFloat() },
        Gravity.START, ClipDrawable.HORIZONTAL,
    )
    private var downAt = 0L
    private val tick = object : Runnable {
        override fun run() {
            val p = ((System.currentTimeMillis() - downAt).toFloat() / holdMs).coerceIn(0f, 1f)
            fill.level = (p * 10000).toInt()
            if (p >= 1f) { fill.level = 0; downAt = 0; performHapticFeedback(android.view.HapticFeedbackConstants.LONG_PRESS); onUnlocked() }
            else postOnAnimation(this)
        }
    }
    /** When true the button simply calls [onTap] (e.g. "lock again"). */
    var tapMode = false
    var onTap: (() -> Unit)? = null

    init {
        addView(icon, 0)
        background = LayerDrawable(arrayOf(background, fill))
        contentDescription = "Hold for one and a half seconds to unlock settings"
        setOnTouchListener { _, ev ->
            if (tapMode) {
                if (ev.action == MotionEvent.ACTION_UP) onTap?.invoke()
                return@setOnTouchListener true
            }
            when (ev.action) {
                MotionEvent.ACTION_DOWN -> { downAt = System.currentTimeMillis(); removeCallbacks(tick); postOnAnimation(tick) }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> { removeCallbacks(tick); downAt = 0; fill.level = 0 }
            }
            true
        }
    }
}
