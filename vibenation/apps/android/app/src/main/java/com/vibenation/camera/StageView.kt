package com.vibenation.camera

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.text.TextUtils
import android.view.GestureDetector
import android.view.MotionEvent
import android.view.ScaleGestureDetector
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import io.livekit.android.renderer.TextureViewRenderer

/**
 * The camera screen. Landscape: [left strip | full 16:9 image | right strip].
 * Nothing is drawn over the image. The left strip holds the blue tally line, the right strip the
 * drawer handle with a status dot. The drawer slides in from the right edge.
 */
@SuppressLint("ViewConstructor")
class StageView(context: Context, private val actions: Actions) : ViewGroup(context) {
    interface Actions {
        fun onGuidesToggled(on: Boolean)
        fun onRelock()
        fun onLeave()
        fun onLensSelected(key: String)
        /** Pinch: factor > 1 = zoom in. */
        fun onZoom(factor: Float)
        /** Tap at (u, v) across the picture (0..1); null = double tap, back to auto focus. */
        fun onFocus(u: Float?, v: Float?)
    }

    private fun dp(v: Float) = Vn.dp(context, v)

    // Left strip: tally.
    private val leftBar = FrameLayout(context)
    private val tallyGlow = View(context)
    private val tallyLine = View(context)

    // Image.
    val imageBox = FrameLayout(context).apply { setBackgroundColor(Vn.IMAGE_BG) }
    val renderer = TextureViewRenderer(context)
    private val guides = GuidesView(context).apply { visibility = GONE }
    private val placeholder = TextView(context).apply {
        setTextColor(Vn.TEXT_3); textSize = 13f; typeface = Vn.sans(context, 600); gravity = Gravity.CENTER
    }

    // Right strip: handle.
    private val rightBar = FrameLayout(context)
    private val handle = LinearLayout(context)
    private val handleChevron = IconView(context, IconView.Kind.CHEVRON_LEFT)
    private val handleDot = View(context)
    // Zoom + focus readout in the strip (nothing is drawn over the picture).
    private val zoomText = TextView(context).apply {
        setTextColor(Vn.TEXT_2); textSize = 12f; typeface = Vn.mono(context, 700); gravity = Gravity.CENTER
    }
    private val focusText = TextView(context).apply {
        setTextColor(Vn.TEXT_3); textSize = 9f; typeface = Vn.sans(context, 800); gravity = Gravity.CENTER; letterSpacing = 0.08f
    }

    // Drawer.
    private val drawer = FrameLayout(context)
    private val pillLive = TextView(context)
    private val pillStandby = TextView(context)
    private val camNum = TextView(context)
    private val camName = TextView(context)
    private val statKeys = Array(6) { TextView(context) }
    private val statVals = Array(6) { TextView(context) }
    private val note = TextView(context)
    private val unlockedRow = LinearLayout(context)
    private val guidesBtn = GlassButton(context, "Guides off")
    private val lensRow = LinearLayout(context).apply { orientation = LinearLayout.HORIZONTAL }
    private val lensBtns = mutableMapOf<String, GlassButton>()
    private var lensKey = "main"
    private val holdBtn: HoldButton

    var drawerOpen = false
        private set
    private var unlocked = false
    private var guidesOn = false
    private val relockSettings = Runnable { setUnlocked(false) }

    init {
        setBackgroundColor(Vn.BG)

        // --- tally
        tallyGlow.background = GradientDrawable(GradientDrawable.Orientation.LEFT_RIGHT, intArrayOf(Color.TRANSPARENT, Color.TRANSPARENT, Color.TRANSPARENT))
        leftBar.addView(tallyGlow)
        leftBar.addView(tallyLine)
        addView(leftBar)

        // --- image
        imageBox.addView(renderer, FrameLayout.LayoutParams(-1, -1))
        imageBox.addView(placeholder, FrameLayout.LayoutParams(-1, -1))
        imageBox.addView(guides, FrameLayout.LayoutParams(-1, -1))
        imageBox.contentDescription = "Full camera image, exactly what goes on air"
        addView(imageBox)

        // --- handle
        handle.orientation = LinearLayout.VERTICAL
        handle.gravity = Gravity.CENTER
        handle.background = Vn.rounded(Vn.GLASS, dp(22f).toFloat(), Vn.GLASS_EDGE, dp(1f))
        handle.addView(handleChevron, LinearLayout.LayoutParams(dp(18f), dp(18f)))
        handle.addView(handleDot, LinearLayout.LayoutParams(dp(6f), dp(6f)).apply { topMargin = dp(8f) })
        handle.isClickable = true
        handle.contentDescription = "Open drawer"
        handle.setOnClickListener { setDrawer(!drawerOpen) }
        rightBar.addView(handle, FrameLayout.LayoutParams(dp(44f), dp(88f), Gravity.CENTER))
        val readout = LinearLayout(context).apply { orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER_HORIZONTAL }
        readout.addView(zoomText); readout.addView(focusText)
        rightBar.addView(readout, FrameLayout.LayoutParams(-2, -2, Gravity.CENTER_HORIZONTAL or Gravity.BOTTOM).apply { bottomMargin = dp(18f) })
        addView(rightBar)
        setupGestures()

        // --- drawer
        holdBtn = HoldButton(context, 1500L) { setUnlocked(true) }
        buildDrawer()
        addView(drawer)
        drawer.visibility = INVISIBLE

        setGuides(false)
        setLive(false)
    }

    private fun buildDrawer() {
        drawer.background = GradientDrawable().apply {
            setColor(Vn.PANEL)
            val r = dp(22f).toFloat()
            cornerRadii = floatArrayOf(r, r, 0f, 0f, 0f, 0f, r, r)
            setStroke(dp(1f), Color.argb(26, 255, 236, 220))
        }
        drawer.elevation = dp(16f).toFloat()
        drawer.isClickable = true // swallow touches so they don't reach the image

        val scroll = ScrollView(context).apply { isFillViewport = true; isVerticalScrollBarEnabled = false }
        val col = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(18f), dp(16f), dp(16f), dp(16f))
        }
        scroll.addView(col, FrameLayout.LayoutParams(-1, -2))
        drawer.addView(scroll, FrameLayout.LayoutParams(-1, -1))

        // Header: ON AIR / STANDBY, CAM n + name, close.
        val header = LinearLayout(context).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
        pillLive.apply {
            text = "●  ON AIR"
            setTextColor(Color.WHITE); textSize = 11f; typeface = Vn.sora(context, 800); letterSpacing = 0.1f
            background = Vn.rounded(Vn.LIVE_DEEP, dp(8f).toFloat())
            setPadding(dp(10f), dp(5f), dp(10f), dp(5f))
            elevation = dp(6f).toFloat()
        }
        pillStandby.apply {
            text = "STANDBY"
            setTextColor(Vn.TEXT_2); textSize = 11f; typeface = Vn.sora(context, 800); letterSpacing = 0.1f
            background = Vn.rounded(Color.TRANSPARENT, dp(8f).toFloat(), Color.argb(38, 255, 236, 220), dp(1f))
            setPadding(dp(10f), dp(5f), dp(10f), dp(5f))
        }
        header.addView(pillLive)
        header.addView(pillStandby)
        val names = LinearLayout(context).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(10f), 0, 0, 0) }
        camNum.apply { setTextColor(Vn.TEXT_3); textSize = 10f; typeface = Vn.mono(context, 700) }
        camName.apply {
            setTextColor(Vn.TEXT); textSize = 15f; typeface = Vn.sora(context, 700)
            maxLines = 1; ellipsize = TextUtils.TruncateAt.END
        }
        names.addView(camNum); names.addView(camName)
        header.addView(names, LinearLayout.LayoutParams(0, -2, 1f))
        val close = FrameLayout(context).apply {
            background = Vn.rounded(Color.argb(10, 255, 236, 220), dp(12f).toFloat(), Vn.GLASS_EDGE_SOFT, dp(1f))
            isClickable = true
            contentDescription = "Close drawer"
            setOnClickListener { setDrawer(false) }
            addView(IconView(context, IconView.Kind.CHEVRON_RIGHT, Vn.TEXT_2), FrameLayout.LayoutParams(dp(16f), dp(16f), Gravity.CENTER))
        }
        header.addView(close, LinearLayout.LayoutParams(dp(40f), dp(40f)))
        col.addView(header)

        // Stats grid 2×3.
        val keys = arrayOf("WHITE BAL.", "EXPOSURE", "BATTERY", "TEMP", "WI-FI", "BITRATE")
        for (row in 0 until 3) {
            val r = LinearLayout(context).apply { orientation = LinearLayout.HORIZONTAL }
            for (c in 0 until 2) {
                val i = row * 2 + c
                val card = LinearLayout(context).apply {
                    orientation = LinearLayout.VERTICAL
                    background = Vn.rounded(Vn.CARD, dp(12f).toFloat(), Vn.CARD_EDGE, dp(1f))
                    setPadding(dp(10f), dp(8f), dp(10f), dp(8f))
                }
                statKeys[i].apply { text = keys[i]; setTextColor(Vn.TEXT_3); textSize = 10f; typeface = Vn.sans(context, 700); letterSpacing = 0.06f }
                statVals[i].apply { text = "—"; setTextColor(Vn.TEXT); textSize = 13f; typeface = Vn.mono(context, 700); maxLines = 1; ellipsize = TextUtils.TruncateAt.END }
                card.addView(statKeys[i]); card.addView(statVals[i])
                r.addView(card, LinearLayout.LayoutParams(0, -2, 1f).apply { if (c == 0) marginEnd = dp(8f) })
            }
            col.addView(r, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(if (row == 0) 12f else 8f) })
        }

        // Lens choice (changing it needs the settings unlocked, like the other picture settings).
        col.addView(TextView(context).apply {
            text = "CAMERA"; setTextColor(Vn.TEXT_3); textSize = 10f; typeface = Vn.sans(context, 700); letterSpacing = 0.06f
        }, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(12f) })
        col.addView(lensRow, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(6f) })

        note.apply { textSize = 11f; typeface = Vn.sans(context, 600); visibility = GONE }
        col.addView(note, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(8f) })

        col.addView(View(context), LinearLayout.LayoutParams(-1, 0, 1f))

        // Settings that need unlocking.
        unlockedRow.orientation = LinearLayout.HORIZONTAL
        val relock = GlassButton(context, "Re-lock picture").apply {
            setOnClickListener { if (unlocked) { touchUnlocked(); actions.onRelock() } }
            contentDescription = "Run auto white balance and exposure again, then lock"
        }
        val leave = GlassButton(context, "Leave show").apply {
            label.setTextColor(Vn.TEXT_2)
            setOnClickListener { if (unlocked) actions.onLeave() }
        }
        unlockedRow.addView(relock, LinearLayout.LayoutParams(0, -2, 1f).apply { marginEnd = dp(8f) })
        unlockedRow.addView(leave, LinearLayout.LayoutParams(0, -2, 1f))
        unlockedRow.visibility = GONE
        col.addView(unlockedRow, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(12f) })

        val bottom = LinearLayout(context).apply { orientation = LinearLayout.HORIZONTAL }
        guidesBtn.setOnClickListener {
            if (!unlocked) { flashNote("Hold to unlock first", Vn.WARN); return@setOnClickListener }
            touchUnlocked()
            setGuides(!guidesOn)
            actions.onGuidesToggled(guidesOn)
        }
        holdBtn.onTap = { setUnlocked(false) }
        bottom.addView(guidesBtn, LinearLayout.LayoutParams(0, -2, 1f).apply { marginEnd = dp(8f) })
        bottom.addView(holdBtn, LinearLayout.LayoutParams(0, -2, 1f))
        col.addView(bottom, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(8f) })
    }

    /** Fill the lens buttons with what this phone has (Ultra-wide / Main / Telephoto / Front). */
    fun setLenses(lenses: List<LockingCameraCapturer.Lens>) {
        lensRow.removeAllViews(); lensBtns.clear()
        lenses.forEachIndexed { i, l ->
            val b = GlassButton(context, l.label).apply {
                label.textSize = 11f
                contentDescription = "Use the ${l.label} camera"
                setOnClickListener {
                    if (!unlocked) { flashNote("Hold to unlock first", Vn.WARN); return@setOnClickListener }
                    touchUnlocked()
                    if (l.key != lensKey) actions.onLensSelected(l.key)
                }
            }
            lensBtns[l.key] = b
            lensRow.addView(b, LinearLayout.LayoutParams(0, -2, 1f).apply { if (i > 0) marginStart = dp(6f) })
        }
        lensRow.visibility = if (lenses.size > 1) VISIBLE else GONE
        markLens(lensKey)
    }

    private fun markLens(key: String) {
        lensKey = key
        for ((k, b) in lensBtns) {
            val on = k == key
            b.background = Vn.rounded(if (on) Color.argb(46, 255, 236, 220) else Vn.CARD, dp(12f).toFloat(), if (on) Vn.TEXT else Vn.GLASS_EDGE_SOFT, dp(1f))
            b.label.setTextColor(if (on) Vn.TEXT else Vn.TEXT_2)
        }
    }

    /** Pinch on the picture zooms; a tap sets the focus point there; a double tap goes back to auto focus. */
    @SuppressLint("ClickableViewAccessibility")
    private fun setupGestures() {
        val scale = ScaleGestureDetector(context, object : ScaleGestureDetector.SimpleOnScaleGestureListener() {
            override fun onScale(d: ScaleGestureDetector): Boolean {
                actions.onZoom(d.scaleFactor)
                return true
            }
        })
        val taps = GestureDetector(context, object : GestureDetector.SimpleOnGestureListener() {
            override fun onDown(e: MotionEvent) = true
            override fun onSingleTapConfirmed(e: MotionEvent): Boolean {
                if (imageBox.width == 0 || imageBox.height == 0) return false
                actions.onFocus((e.x / imageBox.width).coerceIn(0f, 1f), (e.y / imageBox.height).coerceIn(0f, 1f))
                flashNote("Focus set here · double-tap for auto focus", Vn.TEXT_2)
                return true
            }
            override fun onDoubleTap(e: MotionEvent): Boolean {
                actions.onFocus(null, null)
                flashNote("Auto focus", Vn.TEXT_2)
                return true
            }
        })
        imageBox.setOnTouchListener { _, ev ->
            scale.onTouchEvent(ev)
            if (!scale.isInProgress && ev.pointerCount == 1) taps.onTouchEvent(ev)
            true
        }
    }

    private var noteOverride: Pair<String, Int>? = null
    private val clearNote = Runnable { noteOverride = null; applyNote() }
    private var stateNote: Pair<String, Int>? = null

    private fun flashNote(text: String, color: Int) {
        noteOverride = text to color
        applyNote()
        removeCallbacks(clearNote)
        postDelayed(clearNote, 2500)
    }

    private fun applyNote() {
        val n = noteOverride ?: stateNote
        if (n == null) { note.visibility = GONE; return }
        note.visibility = VISIBLE
        note.text = n.first
        note.setTextColor(n.second)
    }

    private fun touchUnlocked() {
        removeCallbacks(relockSettings)
        postDelayed(relockSettings, 30_000)
    }

    private fun setUnlocked(on: Boolean) {
        unlocked = on
        unlockedRow.visibility = if (on) VISIBLE else GONE
        holdBtn.tapMode = on
        holdBtn.label.text = if (on) "Lock settings" else "Hold to unlock"
        holdBtn.icon.kind = if (on) IconView.Kind.UNLOCK else IconView.Kind.LOCK
        holdBtn.icon.invalidate()
        if (on) touchUnlocked() else removeCallbacks(relockSettings)
    }

    fun setGuides(on: Boolean) {
        guidesOn = on
        guides.visibility = if (on) VISIBLE else GONE
        guidesBtn.label.text = if (on) "Guides on" else "Guides off"
    }

    fun setDrawer(open: Boolean) {
        if (open == drawerOpen) return
        drawerOpen = open
        handleChevron.kind = if (open) IconView.Kind.CHEVRON_RIGHT else IconView.Kind.CHEVRON_LEFT
        handleChevron.invalidate()
        handle.contentDescription = if (open) "Close drawer" else "Open drawer"
        val w = drawer.width.toFloat().coerceAtLeast(dp(300f).toFloat())
        if (open) {
            drawer.visibility = VISIBLE
            drawer.translationX = w
            drawer.animate().translationX(0f).setDuration(220).start()
        } else {
            setUnlocked(false)
            drawer.animate().translationX(w).setDuration(200).withEndAction { if (!drawerOpen) drawer.visibility = INVISIBLE }.start()
        }
    }

    private var live = false
    fun setLive(isLive: Boolean) {
        live = isLive
        val c = if (isLive) Vn.LIVE else Vn.TALLY_OFF
        tallyLine.background = Vn.rounded(c, dp(2f).toFloat())
        tallyGlow.background = GradientDrawable(
            GradientDrawable.Orientation.LEFT_RIGHT,
            if (isLive) intArrayOf(Color.TRANSPARENT, Color.argb(90, 61, 139, 255), Color.TRANSPARENT)
            else intArrayOf(Color.TRANSPARENT, Color.TRANSPARENT, Color.TRANSPARENT),
        )
        pillLive.visibility = if (isLive) VISIBLE else GONE
        pillStandby.visibility = if (isLive) GONE else VISIBLE
        leftBar.contentDescription = if (isLive) "On air" else "Standby"
    }

    fun render(u: CamUi) {
        setLive(u.live && u.publishing)
        camNum.text = u.num.ifBlank { "CAM" }
        camName.text = u.name.ifBlank { "Camera" }

        val wb = if (u.locked && u.wb != "—") "${u.wb} · lock" else u.wb
        val vals = arrayOf(
            wb to (if (u.publishing && !u.locked) Vn.WARN else Vn.TEXT),
            u.exposure to Vn.TEXT,
            "${u.battery}%${if (u.charging) " charging" else ""}" to (if (u.battery < 25 && !u.charging) Vn.WARN else Vn.TEXT),
            (u.temp?.let { "$it °C" } ?: "—") to (if ((u.temp ?: 0) >= 40 || u.thermalWarn) Vn.WARN else Vn.TEXT),
            u.wifi to (when (u.wifi) { "Weak" -> Vn.WARN; "Offline" -> Vn.ERROR; else -> Vn.TEXT }),
            (u.kbps?.let { if (it >= 1000) String.format("%.1f Mbps", it / 1000.0) else "$it kbps" } ?: "—") to Vn.TEXT,
        )
        for (i in vals.indices) { statVals[i].text = vals[i].first; statVals[i].setTextColor(vals[i].second) }

        val dot = when {
            u.hasError -> Vn.ERROR
            u.warn != null -> Vn.WARN
            u.live && u.publishing -> Vn.LIVE
            else -> Vn.IDLE
        }
        handleDot.background = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(dot) }

        stateNote = when {
            u.error != null -> u.error to Vn.ERROR
            u.stage == CamUi.Stage.Streaming && !u.statusConnected -> "Status link down — retrying" to Vn.ERROR
            u.warn != null -> u.warn!! to Vn.WARN
            u.fps != null && u.publishing -> "${u.width}×${u.height} · ${u.fps.toInt()} fps" to Vn.TEXT_3
            else -> null
        }
        applyNote()

        placeholder.text = when (u.stage) {
            CamUi.Stage.Joining -> "Joining…"
            CamUi.Stage.Connecting -> "Connecting camera…"
            CamUi.Stage.Reconnecting -> "Reconnecting…"
            CamUi.Stage.Failed -> u.error ?: "Stopped"
            else -> ""
        }
        placeholder.visibility = if (u.publishing) GONE else VISIBLE

        if (u.lens != lensKey) markLens(u.lens)
        zoomText.text = if (u.publishing) String.format("%.1f×", u.zoom) else ""
        focusText.text = if (u.publishing && u.focusSet) "FOCUS" else ""
        zoomText.contentDescription = "Zoom ${String.format("%.1f", u.zoom)} times"
    }

    // ---------------------------------------------------------------- layout

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val w = MeasureSpec.getSize(widthMeasureSpec)
        val h = MeasureSpec.getSize(heightMeasureSpec)
        setMeasuredDimension(w, h)
        val r = imageRect(w, h)
        val strip = r[0]
        fun exact(v: Int) = MeasureSpec.makeMeasureSpec(v, MeasureSpec.EXACTLY)
        leftBar.measure(exact(strip), exact(h))
        rightBar.measure(exact(w - r[2]), exact(h))
        imageBox.measure(exact(r[2] - r[0]), exact(r[3] - r[1]))
        drawer.measure(exact(drawerWidth(w)), exact(h))
        val lineH = (h * 0.7f).toInt()
        tallyLine.measure(exact(dp(4f)), exact(lineH))
        tallyGlow.measure(exact(dp(28f).coerceAtMost(strip)), exact(lineH))
    }

    override fun onLayout(changed: Boolean, l: Int, t: Int, r: Int, b: Int) {
        val w = r - l; val h = b - t
        val rect = imageRect(w, h)
        leftBar.layout(0, 0, rect[0], h)
        imageBox.layout(rect[0], rect[1], rect[2], rect[3])
        rightBar.layout(rect[2], 0, w, h)
        val dw = drawerWidth(w)
        drawer.layout(w - dw, 0, w, h)
        val cx = rect[0] / 2
        val lineTop = (h - tallyLine.measuredHeight) / 2
        tallyLine.layout(cx - tallyLine.measuredWidth / 2, lineTop, cx + tallyLine.measuredWidth / 2 + 1, lineTop + tallyLine.measuredHeight)
        tallyGlow.layout(cx - tallyGlow.measuredWidth / 2, lineTop, cx + tallyGlow.measuredWidth / 2, lineTop + tallyGlow.measuredHeight)
        if (!drawerOpen) drawer.translationX = dw.toFloat()
    }

    private fun drawerWidth(w: Int) = minOf(dp(300f), (w * 0.6f).toInt())

    /** [left, top, right, bottom] of the 16:9 image, leaving at least 56dp strips on each side. */
    private fun imageRect(w: Int, h: Int): IntArray {
        val minStrip = dp(56f)
        var iw = h * 16 / 9
        var ih = h
        if (w - iw < 2 * minStrip) {
            iw = w - 2 * minStrip
            ih = iw * 9 / 16
        }
        val left = (w - iw) / 2
        val top = (h - ih) / 2
        return intArrayOf(left, top, left + iw, top + ih)
    }
}
