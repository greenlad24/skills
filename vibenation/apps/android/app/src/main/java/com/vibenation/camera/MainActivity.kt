package com.vibenation.camera

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.hardware.display.DisplayManager
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.view.Surface
import android.view.View
import android.view.WindowManager
import android.view.inputmethod.EditorInfo
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions
import io.livekit.android.room.Room
import io.livekit.android.room.track.LocalVideoTrack
import kotlinx.coroutines.launch

class MainActivity : AppCompatActivity(), StageView.Actions, CamSession.Listener {

    private lateinit var prefs: Prefs
    private lateinit var session: CamSession
    private lateinit var root: FrameLayout
    private lateinit var stage: StageView
    private lateinit var joinView: View
    private lateinit var nameInput: EditText
    private lateinit var joinBtn: TextView
    private lateinit var scanBtn: TextView
    private lateinit var joinHint: TextView
    private lateinit var joinError: TextView

    @Volatile private var displayRotationDeg = 90
    private var rendererReady = false
    private var renderedTrack: LocalVideoTrack? = null

    private val scan = registerForActivityResult(ScanContract()) { res ->
        val parsed = Prefs.parseInvite(res.contents)
        if (res.contents == null) return@registerForActivityResult
        if (parsed == null) { showJoinError("That QR code isn't a VibeNation camera link."); return@registerForActivityResult }
        acceptInvite(parsed, autoJoin = true)
    }

    private val askCamera = registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) startStreaming() else showJoinError("VibeNation needs the camera to stream. Allow it in Settings → Apps.")
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        hideSystemBars()

        prefs = Prefs(this)
        session = CamSession(applicationContext, prefs) { displayRotationDeg }
        session.listener = this

        root = FrameLayout(this).apply { setBackgroundColor(Color.BLACK) }
        stage = StageView(this, this)
        stage.setGuides(prefs.guides)
        joinView = buildJoinView()
        root.addView(stage, FrameLayout.LayoutParams(-1, -1))
        root.addView(joinView, FrameLayout.LayoutParams(-1, -1))
        setContentView(root)
        showJoin()

        trackDisplayRotation()

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                when {
                    stage.visibility == View.VISIBLE && stage.drawerOpen -> stage.setDrawer(false)
                    stage.visibility == View.VISIBLE -> stage.setDrawer(true) // leaving needs hold-to-unlock
                    else -> finish()
                }
            }
        })

        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                session.ui.collect { u ->
                    stage.render(u)
                    if (u.stage == CamUi.Stage.Failed) {
                        showJoin()
                        showJoinError(u.error ?: "Stopped")
                    }
                }
            }
        }

        handleIntent(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleIntent(intent)
    }

    private fun handleIntent(intent: Intent?) {
        if (intent?.action != Intent.ACTION_VIEW) return
        val parsed = Prefs.parseInvite(intent.dataString) ?: return
        acceptInvite(parsed, autoJoin = false)
    }

    private fun acceptInvite(parsed: Pair<String, String>, autoJoin: Boolean) {
        val (base, k) = parsed
        if (k != prefs.invite) prefs.camId = null // a new show: let the server number us
        prefs.base = base
        prefs.invite = k
        if (session.running) { session.stop(); showJoin() }
        refreshJoin()
        showJoinError(null)
        if (autoJoin && !prefs.name.isNullOrBlank()) onJoinPressed()
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) hideSystemBars()
    }

    private fun hideSystemBars() {
        val c = WindowInsetsControllerCompat(window, window.decorView)
        c.hide(WindowInsetsCompat.Type.systemBars())
        c.systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
    }

    private fun trackDisplayRotation() {
        fun read() {
            @Suppress("DEPRECATION")
            val r = (if (android.os.Build.VERSION.SDK_INT >= 30) display?.rotation else windowManager.defaultDisplay.rotation) ?: Surface.ROTATION_90
            displayRotationDeg = when (r) { Surface.ROTATION_0 -> 0; Surface.ROTATION_90 -> 90; Surface.ROTATION_180 -> 180; else -> 270 }
        }
        read()
        getSystemService(DisplayManager::class.java)?.registerDisplayListener(object : DisplayManager.DisplayListener {
            override fun onDisplayAdded(displayId: Int) {}
            override fun onDisplayRemoved(displayId: Int) {}
            override fun onDisplayChanged(displayId: Int) { read() }
        }, null)
    }

    // ---------------------------------------------------------------- join screen

    private fun dp(v: Float) = Vn.dp(this, v)

    private fun buildJoinView(): View {
        val frame = FrameLayout(this)
        frame.background = GradientDrawable().apply {
            gradientType = GradientDrawable.RADIAL_GRADIENT
            colors = intArrayOf(Color.parseColor("#3A1A0C"), Color.parseColor("#140D09"), Color.parseColor("#0B0806"))
            gradientRadius = dp(520f).toFloat()
            setGradientCenter(0.2f, 0.9f)
        }
        val scroll = ScrollView(this).apply { isFillViewport = true }
        frame.addView(scroll, FrameLayout.LayoutParams(-1, -1))
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(40f), dp(24f), dp(40f), dp(24f))
        }
        scroll.addView(row, FrameLayout.LayoutParams(-1, -2))

        val brand = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        brand.addView(TextView(this).apply {
            text = "VibeNation"; setTextColor(Vn.TEXT); textSize = 30f; typeface = Vn.sora(this@MainActivity, 800)
        })
        brand.addView(TextView(this).apply {
            text = "CAMERA"; setTextColor(Vn.EMBER); textSize = 12f; typeface = Vn.mono(this@MainActivity, 700); letterSpacing = 0.2f
        })
        brand.addView(TextView(this).apply {
            text = "Turn the phone sideways, put it on a stand and plug it in. " +
                "After joining, white balance and exposure set themselves and lock for the whole show."
            setTextColor(Vn.TEXT_2); textSize = 13f; typeface = Vn.sans(this@MainActivity, 400)
            setLineSpacing(0f, 1.25f)
            setPadding(0, dp(14f), dp(24f), 0)
        })
        row.addView(brand, LinearLayout.LayoutParams(0, -2, 1f))

        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = Vn.rounded(Color.parseColor("#B3140D09"), dp(22f).toFloat(), Vn.GLASS_EDGE, dp(1f))
            setPadding(dp(18f), dp(18f), dp(18f), dp(18f))
        }
        card.addView(TextView(this).apply {
            text = "CAMERA NAME"; setTextColor(Vn.TEXT_3); textSize = 10f; typeface = Vn.sans(this@MainActivity, 700); letterSpacing = 0.06f
        })
        nameInput = EditText(this).apply {
            hint = "e.g. Drums wide"
            setHintTextColor(Vn.TEXT_3)
            setTextColor(Vn.TEXT); textSize = 16f; typeface = Vn.sora(this@MainActivity, 600)
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_SENTENCES
            imeOptions = EditorInfo.IME_ACTION_DONE or EditorInfo.IME_FLAG_NO_EXTRACT_UI
            maxLines = 1
            filters = arrayOf(android.text.InputFilter.LengthFilter(40))
            background = Vn.rounded(Vn.CARD, dp(12f).toFloat(), Vn.GLASS_EDGE_SOFT, dp(1f))
            setPadding(dp(12f), dp(10f), dp(12f), dp(10f))
            setOnEditorActionListener { _, a, _ -> if (a == EditorInfo.IME_ACTION_DONE) { onJoinPressed(); true } else false }
        }
        card.addView(nameInput, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(6f) })

        joinBtn = primaryButton("Join show") { onJoinPressed() }
        card.addView(joinBtn, LinearLayout.LayoutParams(-1, dp(48f)).apply { topMargin = dp(14f) })
        scanBtn = secondaryButton("Scan QR code") { startScan() }
        card.addView(scanBtn, LinearLayout.LayoutParams(-1, dp(44f)).apply { topMargin = dp(8f) })
        joinHint = TextView(this).apply { setTextColor(Vn.TEXT_3); textSize = 11f; typeface = Vn.sans(this@MainActivity, 400) }
        card.addView(joinHint, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(10f) })
        joinError = TextView(this).apply { setTextColor(Vn.ERROR); textSize = 12f; typeface = Vn.sans(this@MainActivity, 600); visibility = View.GONE }
        card.addView(joinError, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(6f) })

        row.addView(card, LinearLayout.LayoutParams(dp(320f), -2))
        return frame
    }

    private fun primaryButton(text: String, onClick: () -> Unit) = TextView(this).apply {
        this.text = text
        gravity = Gravity.CENTER
        setTextColor(Color.parseColor("#1A0D06")); textSize = 14f; typeface = Vn.sora(this@MainActivity, 700)
        background = GradientDrawable(GradientDrawable.Orientation.LEFT_RIGHT, intArrayOf(Color.parseColor("#FFC08F"), Vn.EMBER)).apply {
            cornerRadius = dp(14f).toFloat()
        }
        isClickable = true; isFocusable = true
        setOnClickListener { onClick() }
    }

    private fun secondaryButton(text: String, onClick: () -> Unit) = TextView(this).apply {
        this.text = text
        gravity = Gravity.CENTER
        setTextColor(Vn.TEXT); textSize = 13f; typeface = Vn.sans(this@MainActivity, 700)
        background = Vn.rounded(Vn.CARD, dp(14f).toFloat(), Vn.GLASS_EDGE_SOFT, dp(1f))
        isClickable = true; isFocusable = true
        setOnClickListener { onClick() }
    }

    private fun refreshJoin() {
        if (nameInput.text.isNullOrBlank()) nameInput.setText(prefs.name.orEmpty())
        val hasInvite = !prefs.invite.isNullOrBlank()
        joinBtn.visibility = if (hasInvite) View.VISIBLE else View.GONE
        joinBtn.text = prefs.camId?.let { "Rejoin as CAM $it" } ?: "Join show"
        scanBtn.text = if (hasInvite) "Scan a new QR code" else "Scan QR code"
        joinHint.text = if (hasInvite) "Camera link ready. Picture only — the microphone is never used."
        else "Open VibeNation → Cameras → Add phone, then scan the code."
    }

    private fun showJoin() {
        refreshJoin()
        joinView.visibility = View.VISIBLE
        stage.visibility = View.GONE
    }

    private fun showJoinError(msg: String?) {
        joinError.text = msg.orEmpty()
        joinError.visibility = if (msg.isNullOrBlank()) View.GONE else View.VISIBLE
    }

    private fun startScan() {
        scan.launch(ScanOptions().apply {
            setDesiredBarcodeFormats(ScanOptions.QR_CODE)
            setPrompt("Scan the camera QR code shown in VibeNation")
            setBeepEnabled(false)
            setOrientationLocked(true)
        })
    }

    private fun onJoinPressed() {
        val name = nameInput.text?.toString()?.trim().orEmpty()
        if (name.isEmpty()) { showJoinError("Give this camera a name (e.g. Drums wide)."); return }
        if (prefs.invite.isNullOrBlank()) { startScan(); return }
        prefs.name = name
        showJoinError(null)
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) startStreaming()
        else askCamera.launch(Manifest.permission.CAMERA)
    }

    private fun startStreaming() {
        currentFocus?.let { v ->
            (getSystemService(INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager).hideSoftInputFromWindow(v.windowToken, 0)
        }
        joinView.visibility = View.GONE
        stage.visibility = View.VISIBLE
        hideSystemBars()
        session.start()
    }

    // ---------------------------------------------------------------- stage actions

    override fun onGuidesToggled(on: Boolean) { prefs.guides = on }
    override fun onRelock() { session.relockPicture() }
    override fun onLeave() {
        stage.setDrawer(false)
        session.stop()
        showJoin()
    }

    // ---------------------------------------------------------------- preview

    override fun onTrack(room: Room, track: LocalVideoTrack) {
        runOnUiThread {
            if (rendererReady) { try { stage.renderer.release() } catch (_: Exception) {} }
            room.initVideoRenderer(stage.renderer)
            stage.renderer.setMirror(false)
            rendererReady = true
            track.addRenderer(stage.renderer)
            renderedTrack = track
        }
    }

    override fun onTrackGone() {
        val t = renderedTrack ?: return
        renderedTrack = null
        try { t.removeRenderer(stage.renderer) } catch (_: Exception) {}
        stage.renderer.clearImage()
    }

    override fun onDestroy() {
        session.destroy()
        if (rendererReady) try { stage.renderer.release() } catch (_: Exception) {}
        super.onDestroy()
    }
}
