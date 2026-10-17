package com.vibenation.camera

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Matrix
import android.graphics.SurfaceTexture
import android.hardware.camera2.CameraCaptureSession
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraDevice
import android.hardware.camera2.CameraManager
import android.hardware.camera2.CameraMetadata
import android.hardware.camera2.CaptureRequest
import android.hardware.camera2.CaptureResult
import android.hardware.camera2.TotalCaptureResult
import android.os.Handler
import android.os.HandlerThread
import android.util.Log
import android.util.Range
import android.util.Size
import android.view.Surface
import livekit.org.webrtc.CapturerObserver
import livekit.org.webrtc.SurfaceTextureHelper
import livekit.org.webrtc.TextureBufferImpl
import livekit.org.webrtc.VideoCapturer
import livekit.org.webrtc.VideoFrame
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlin.math.roundToInt

/**
 * Camera2 capturer for LiveKit that runs auto white balance / exposure for a few seconds, then LOCKS
 * them (CONTROL_AWB_LOCK, CONTROL_AE_LOCK) so colour and brightness stay constant for the whole stream.
 * Focus is never locked: continuous video autofocus keeps following the performers. Frame handling mirrors WebRTC's own Camera2Session.
 */
class LockingCameraCapturer(
    private val context: Context,
    val format: Format,
    /** Current display rotation in degrees (0/90/180/270). */
    private val displayRotation: () -> Int,
    private val listener: Listener,
) : VideoCapturer {

    data class Format(
        val cameraId: String,
        val width: Int,
        val height: Int,
        val fps: Int,
        val fpsRange: Range<Int>,
        val sensorOrientation: Int,
        val frontFacing: Boolean,
    )

    interface Listener {
        /** Called on the camera thread whenever lock state or the reported values change. */
        fun onPicture(locked: Boolean, wb: String, exposure: String)
        fun onFps(fps: Double)
        fun onCameraError(message: String)
    }

    /** The locked picture, kept for the life of the app so a hard reconnect restores the same look. */
    class Held(
        val cameraId: String,
        val iso: Int,
        val exposureNs: Long,
        val gains: android.hardware.camera2.params.RggbChannelVector,
        val ccm: android.hardware.camera2.params.ColorSpaceTransform,
        val focus: Float?,
        val wb: String,
        val exposure: String,
    )

    companion object {
        private const val TAG = "VnCamera"
        const val LOCK_AFTER_MS = 4000L

        /** Last locked picture in this app session (null = lock fresh). */
        @Volatile var held: Held? = null

        /** Back camera, 1920x1080 (or the closest 16:9 below), 60 fps when the device can, else 30. */
        fun pickFormat(context: Context): Format? {
            val cm = context.getSystemService(CameraManager::class.java) ?: return null
            val ids = try { cm.cameraIdList.toList() } catch (_: Exception) { return null }
            val id = ids.firstOrNull {
                cm.getCameraCharacteristics(it).get(CameraCharacteristics.LENS_FACING) == CameraMetadata.LENS_FACING_BACK
            } ?: ids.firstOrNull() ?: return null
            val ch = cm.getCameraCharacteristics(id)
            val map = ch.get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP) ?: return null
            val sizes = map.getOutputSizes(SurfaceTexture::class.java)?.toList().orEmpty()
            if (sizes.isEmpty()) return null
            val size: Size = sizes.firstOrNull { it.width == 1920 && it.height == 1080 }
                ?: sizes.filter { it.width * 9 == it.height * 16 && it.width <= 1920 }.maxByOrNull { it.width * it.height }
                ?: sizes.filter { it.width <= 1920 }.maxByOrNull { it.width * it.height }
                ?: sizes.minByOrNull { it.width * it.height }!!
            val minDur = try { map.getOutputMinFrameDuration(SurfaceTexture::class.java, size) } catch (_: Exception) { 0L }
            val ranges = ch.get(CameraCharacteristics.CONTROL_AE_AVAILABLE_TARGET_FPS_RANGES)?.toList().orEmpty()
            val sizeAllows60 = minDur == 0L || minDur <= 16_700_000L
            fun best(target: Int): Range<Int>? =
                ranges.firstOrNull { it.lower == target && it.upper == target }
                    ?: ranges.filter { it.upper == target }.maxByOrNull { it.lower }
            val r60 = if (sizeAllows60) best(60) else null
            val range = r60 ?: best(30) ?: ranges.maxByOrNull { it.upper } ?: Range(30, 30)
            return Format(
                cameraId = id,
                width = size.width,
                height = size.height,
                fps = if (r60 != null) 60 else minOf(30, range.upper),
                fpsRange = range,
                sensorOrientation = ch.get(CameraCharacteristics.SENSOR_ORIENTATION) ?: 90,
                frontFacing = ch.get(CameraCharacteristics.LENS_FACING) == CameraMetadata.LENS_FACING_FRONT,
            )
        }
    }

    private val cameraManager = context.getSystemService(CameraManager::class.java)
    private val characteristics = cameraManager.getCameraCharacteristics(format.cameraId)
    private val afModes = characteristics.get(CameraCharacteristics.CONTROL_AF_AVAILABLE_MODES)?.toSet().orEmpty()
    private val canContinuousAf = CameraMetadata.CONTROL_AF_MODE_CONTINUOUS_VIDEO in afModes
    private val xyzToCamera: DoubleArray? = Cct.pickColorTransform(characteristics)
    private val manualCapable: Boolean = characteristics.get(CameraCharacteristics.REQUEST_AVAILABLE_CAPABILITIES)?.let { caps ->
        CameraMetadata.REQUEST_AVAILABLE_CAPABILITIES_MANUAL_SENSOR in caps &&
            CameraMetadata.REQUEST_AVAILABLE_CAPABILITIES_MANUAL_POST_PROCESSING in caps
    } ?: false

    private var helper: SurfaceTextureHelper? = null
    private var observer: CapturerObserver? = null
    private var thread: HandlerThread? = null
    private var handler: Handler? = null
    private var device: CameraDevice? = null
    private var session: CameraCaptureSession? = null
    private var surface: Surface? = null

    @Volatile var locked = false
        private set
    @Volatile private var running = false
    private var lockRunnable: Runnable? = null
    private var lastReportNs = 0L
    private var lastWb = ""
    private var lastExposure = ""
    private var lastLocked = false

    // fps measurement
    private var frameCount = 0
    private var fpsWindowStartNs = 0L

    override fun initialize(surfaceTextureHelper: SurfaceTextureHelper, applicationContext: Context, capturerObserver: CapturerObserver) {
        helper = surfaceTextureHelper
        observer = capturerObserver
    }

    override fun startCapture(width: Int, height: Int, framerate: Int) {
        if (running) return
        running = true
        locked = false
        val t = HandlerThread("vn-camera").also { it.start() }
        thread = t
        handler = Handler(t.looper)
        handler!!.post { openCamera() }
    }

    @SuppressLint("MissingPermission")
    private fun openCamera() {
        try {
            cameraManager.openCamera(format.cameraId, object : CameraDevice.StateCallback() {
                override fun onOpened(d: CameraDevice) {
                    if (!running) { d.close(); return }
                    device = d
                    createSession()
                }
                override fun onDisconnected(d: CameraDevice) {
                    d.close(); device = null
                    listener.onCameraError("Camera taken by another app")
                }
                override fun onError(d: CameraDevice, error: Int) {
                    d.close(); device = null
                    listener.onCameraError("Camera error $error")
                    observer?.onCapturerStarted(false)
                }
            }, handler)
        } catch (e: Exception) {
            Log.e(TAG, "openCamera", e)
            listener.onCameraError("Can't open camera: ${e.message}")
            observer?.onCapturerStarted(false)
        }
    }

    private fun createSession() {
        val h = helper ?: return
        val d = device ?: return
        h.setTextureSize(format.width, format.height)
        val s = Surface(h.surfaceTexture)
        surface = s
        h.startListening { frame -> onFrame(frame) }
        try {
            @Suppress("DEPRECATION")
            d.createCaptureSession(listOf(s), object : CameraCaptureSession.StateCallback() {
                override fun onConfigured(cs: CameraCaptureSession) {
                    if (!running) { cs.close(); return }
                    session = cs
                    val h = held
                    if (h != null && h.cameraId == format.cameraId && manualCapable && repeatHeld(h)) {
                        locked = true
                        lastWb = h.wb; lastExposure = h.exposure; lastLocked = true
                        listener.onPicture(true, h.wb, h.exposure)
                    } else {
                        repeat(lockedNow = false)
                        scheduleLock(LOCK_AFTER_MS)
                    }
                    observer?.onCapturerStarted(true)
                }
                override fun onConfigureFailed(cs: CameraCaptureSession) {
                    listener.onCameraError("Camera can't run ${format.width}×${format.height} @ ${format.fps}")
                    observer?.onCapturerStarted(false)
                }
            }, handler)
        } catch (e: Exception) {
            Log.e(TAG, "createCaptureSession", e)
            listener.onCameraError("Camera session failed: ${e.message}")
            observer?.onCapturerStarted(false)
        }
    }

    private fun baseRequest(lockedNow: Boolean): CaptureRequest.Builder {
        val b = device!!.createCaptureRequest(CameraDevice.TEMPLATE_RECORD)
        b.addTarget(surface!!)
        b.set(CaptureRequest.CONTROL_MODE, CameraMetadata.CONTROL_MODE_AUTO)
        b.set(CaptureRequest.CONTROL_AE_MODE, CameraMetadata.CONTROL_AE_MODE_ON)
        b.set(CaptureRequest.CONTROL_AWB_MODE, CameraMetadata.CONTROL_AWB_MODE_AUTO)
        b.set(CaptureRequest.CONTROL_AE_TARGET_FPS_RANGE, format.fpsRange)
        b.set(CaptureRequest.CONTROL_AE_ANTIBANDING_MODE, CameraMetadata.CONTROL_AE_ANTIBANDING_MODE_AUTO)
        // Tripod camera: no digital stabilisation (it crops and wobbles).
        b.set(CaptureRequest.CONTROL_VIDEO_STABILIZATION_MODE, CameraMetadata.CONTROL_VIDEO_STABILIZATION_MODE_OFF)
        if (canContinuousAf) b.set(CaptureRequest.CONTROL_AF_MODE, CameraMetadata.CONTROL_AF_MODE_CONTINUOUS_VIDEO)
        b.set(CaptureRequest.CONTROL_AE_LOCK, lockedNow)
        b.set(CaptureRequest.CONTROL_AWB_LOCK, lockedNow)
        return b
    }

    private val resultCallback = object : CameraCaptureSession.CaptureCallback() {
        override fun onCaptureCompleted(s: CameraCaptureSession, request: CaptureRequest, result: TotalCaptureResult) {
            report(result)
        }
    }

    private fun repeat(lockedNow: Boolean) {
        val cs = session ?: return
        try {
            cs.setRepeatingRequest(baseRequest(lockedNow).build(), resultCallback, handler)
        } catch (e: Exception) {
            Log.e(TAG, "setRepeatingRequest", e)
            listener.onCameraError("Camera stopped: ${e.message}")
        }
    }

    /** Re-apply a previously locked picture with manual sensor + colour settings. */
    private fun repeatHeld(h: Held): Boolean {
        val cs = session ?: return false
        return try {
            val b = baseRequest(lockedNow = true)
            b.set(CaptureRequest.CONTROL_AE_MODE, CameraMetadata.CONTROL_AE_MODE_OFF)
            b.set(CaptureRequest.SENSOR_SENSITIVITY, h.iso)
            b.set(CaptureRequest.SENSOR_EXPOSURE_TIME, h.exposureNs)
            b.set(CaptureRequest.SENSOR_FRAME_DURATION, 1_000_000_000L / format.fps)
            b.set(CaptureRequest.CONTROL_AWB_MODE, CameraMetadata.CONTROL_AWB_MODE_OFF)
            b.set(CaptureRequest.COLOR_CORRECTION_MODE, CameraMetadata.COLOR_CORRECTION_MODE_TRANSFORM_MATRIX)
            b.set(CaptureRequest.COLOR_CORRECTION_GAINS, h.gains)
            b.set(CaptureRequest.COLOR_CORRECTION_TRANSFORM, h.ccm)
            // Focus is never locked: it keeps following the performers (continuous video AF, set in baseRequest).
            cs.setRepeatingRequest(b.build(), resultCallback, handler)
            true
        } catch (e: Exception) {
            Log.w(TAG, "restore held picture failed, locking fresh", e)
            false
        }
    }

    private fun scheduleLock(delayMs: Long) {
        val h = handler ?: return
        lockRunnable?.let { h.removeCallbacks(it) }
        val r = Runnable { lockNow() }
        lockRunnable = r
        h.postDelayed(r, delayMs)
    }

    /** Freeze AE + AWB. Focus stays continuous (user, 17 Oct 2026: cameras must keep auto focus). */
    private fun lockNow() {
        val cs = session ?: return
        try {
            repeat(lockedNow = true)
            locked = true
        } catch (e: Exception) {
            Log.e(TAG, "lock", e)
        }
    }

    /** Unlock, let auto settle on the new scene for a few seconds, then lock again. */
    fun relock() {
        held = null
        handler?.post {
            val cs = session ?: return@post
            locked = false
            try {
                if (canContinuousAf) {
                    val c = baseRequest(lockedNow = false)
                    c.set(CaptureRequest.CONTROL_AF_TRIGGER, CameraMetadata.CONTROL_AF_TRIGGER_CANCEL)
                    cs.capture(c.build(), resultCallback, handler)
                }
                repeat(lockedNow = false)
            } catch (e: Exception) {
                Log.e(TAG, "relock", e)
            }
            scheduleLock(LOCK_AFTER_MS)
        }
    }

    private fun report(r: CaptureResult) {
        val now = System.nanoTime()
        if (now - lastReportNs < 500_000_000L) return
        lastReportNs = now
        val iso = r.get(CaptureResult.SENSOR_SENSITIVITY)
        val expNs = r.get(CaptureResult.SENSOR_EXPOSURE_TIME)
        val exposure = buildString {
            if (iso != null) append("ISO $iso")
            if (expNs != null && expNs > 0) {
                if (isNotEmpty()) append(" · ")
                val denom = (1_000_000_000.0 / expNs)
                append(if (denom >= 1.5) "1/${denom.roundToInt()}" else String.format("%.1fs", expNs / 1e9))
            }
            if (isEmpty()) append("Auto")
        }
        val gains = r.get(CaptureResult.COLOR_CORRECTION_GAINS)
        val kelvin = if (gains != null && xyzToCamera != null) Cct.kelvinFromGains(gains, xyzToCamera) else null
        val wb = kelvin?.let { "$it K" } ?: "Auto"
        val aeLocked = r.get(CaptureResult.CONTROL_AE_STATE) == CameraMetadata.CONTROL_AE_STATE_LOCKED
        val awbLocked = r.get(CaptureResult.CONTROL_AWB_STATE) == CameraMetadata.CONTROL_AWB_STATE_LOCKED
        // Some HALs never report the LOCKED state; trust our request in that case.
        val isLocked = locked && (aeLocked || awbLocked || r.get(CaptureResult.CONTROL_AE_LOCK) == true)
        // While locked, keep the first reported values (the HAL may jitter metadata slightly).
        if (isLocked && lastLocked && lastWb.isNotEmpty()) return
        if (isLocked && held == null) {
            val iso2 = iso; val exp2 = expNs; val g2 = gains
            val ccm = r.get(CaptureResult.COLOR_CORRECTION_TRANSFORM)
            if (iso2 != null && exp2 != null && g2 != null && ccm != null) {
                held = Held(format.cameraId, iso2, exp2, g2, ccm, r.get(CaptureResult.LENS_FOCUS_DISTANCE), wb, exposure)
            }
        }
        if (wb != lastWb || exposure != lastExposure || isLocked != lastLocked) {
            lastWb = wb; lastExposure = exposure; lastLocked = isLocked
            listener.onPicture(isLocked, wb, exposure)
        }
    }

    private fun frameOrientation(): Int {
        var rotation = displayRotation()
        if (!format.frontFacing) rotation = 360 - rotation
        return (format.sensorOrientation + rotation) % 360
    }

    private fun onFrame(frame: VideoFrame) {
        if (!running) return
        val obs = observer ?: return
        val buf = frame.buffer as? TextureBufferImpl ?: return
        val m = Matrix()
        m.preTranslate(0.5f, 0.5f)
        if (format.frontFacing) m.preScale(-1f, 1f)
        m.preRotate(-format.sensorOrientation.toFloat())
        m.preTranslate(-0.5f, -0.5f)
        val out = VideoFrame(buf.applyTransformMatrix(m, buf.width, buf.height), frameOrientation(), frame.timestampNs)
        obs.onFrameCaptured(out)
        out.release()

        val now = System.nanoTime()
        if (fpsWindowStartNs == 0L) fpsWindowStartNs = now
        frameCount++
        val dt = now - fpsWindowStartNs
        if (dt >= 2_000_000_000L) {
            listener.onFps(frameCount * 1e9 / dt)
            frameCount = 0
            fpsWindowStartNs = now
        }
    }

    override fun stopCapture() {
        if (!running) return
        running = false
        val h = handler
        val latch = CountDownLatch(1)
        if (h != null) {
            h.post {
                lockRunnable?.let { h.removeCallbacks(it) }
                try { session?.close() } catch (_: Exception) {}
                session = null
                try { device?.close() } catch (_: Exception) {}
                device = null
                latch.countDown()
            }
            latch.await(3, TimeUnit.SECONDS)
        }
        helper?.stopListening()
        surface?.release()
        surface = null
        observer?.onCapturerStopped()
        thread?.quitSafely()
        thread = null
        handler = null
        locked = false
        lastWb = ""; lastLocked = false
        frameCount = 0; fpsWindowStartNs = 0L
    }

    override fun changeCaptureFormat(width: Int, height: Int, framerate: Int) {
        stopCapture()
        startCapture(width, height, framerate)
    }

    override fun dispose() {
        stopCapture()
    }

    override fun isScreencast() = false
}
