package com.vibenation.camera

import android.content.Context
import android.util.Log
import io.livekit.android.LiveKit
import io.livekit.android.AudioOptions
import io.livekit.android.LiveKitOverrides
import io.livekit.android.RoomOptions
import io.livekit.android.audio.NoAudioHandler
import io.livekit.android.events.RoomEvent
import io.livekit.android.room.Room
import io.livekit.android.room.participant.VideoTrackPublishOptions
import io.livekit.android.room.track.CustomVideoPreset
import io.livekit.android.room.track.LocalVideoTrack
import io.livekit.android.room.track.LocalVideoTrackOptions
import io.livekit.android.room.track.Track
import io.livekit.android.room.track.VideoCaptureParameter
import io.livekit.android.room.track.VideoEncoding
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.math.BigInteger
import java.util.concurrent.TimeUnit

/** Everything the camera screen shows. */
data class CamUi(
    val stage: Stage = Stage.Idle,
    val num: String = "",
    val name: String = "",
    val live: Boolean = false,
    val statusConnected: Boolean = false,
    val publishing: Boolean = false,
    val locked: Boolean = false,
    val wb: String = "—",
    val exposure: String = "—",
    val fps: Double? = null,
    val targetFps: Int = 60,
    val width: Int = 0,
    val height: Int = 0,
    val kbps: Int? = null,
    val battery: Int = 100,
    val charging: Boolean = false,
    val temp: Int? = null,
    val wifi: String = "—",
    val thermalWarn: Boolean = false,
    val error: String? = null,
) {
    enum class Stage { Idle, Joining, Connecting, Streaming, Reconnecting, Failed }

    /** Amber warnings, same rules as the server. */
    val warn: String?
        get() = when {
            battery < 25 && !charging -> "Battery $battery%"
            (temp ?: 0) >= 45 || thermalWarn -> "Hot ${temp ?: "—"} °C"
            publishing && fps != null && fps < targetFps - 10 -> "${fps.toInt()} fps"
            publishing && !locked -> "Locking picture…"
            else -> null
        }

    val hasError: Boolean get() = error != null || stage == Stage.Failed || stage == Stage.Reconnecting ||
        (stage == Stage.Streaming && !statusConnected)
}

class JoinRejected(message: String) : Exception(message)

/**
 * One phone camera: join with the invite, publish to LiveKit, keep the status/tally socket alive.
 * Reconnects forever until [stop] is called.
 */
class CamSession(
    private val appContext: Context,
    private val prefs: Prefs,
    private val displayRotation: () -> Int,
) {
    interface Listener {
        fun onTrack(room: Room, track: LocalVideoTrack)
        fun onTrackGone()
    }

    var listener: Listener? = null
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private val http = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
        .pingInterval(15, TimeUnit.SECONDS)
        .build()
    private val telemetry = Telemetry(appContext)

    private val _ui = MutableStateFlow(CamUi())
    val ui: StateFlow<CamUi> = _ui

    private var mainJob: Job? = null
    private var room: Room? = null
    private var track: LocalVideoTrack? = null
    private var capturer: LockingCameraCapturer? = null
    @Volatile private var camToken: String? = null
    private var ws: WebSocket? = null
    private var wsJob: Job? = null
    private var rejoin: CompletableDeferred<String>? = null

    val running get() = mainJob?.isActive == true

    fun start() {
        if (running) return
        mainJob = scope.launch { mainLoop() }
        wsJob = scope.launch { wsLoop() }
        scope.launch { statusLoop() }
    }

    fun stop() {
        mainJob?.cancel(); wsJob?.cancel()
        mainJob = null; wsJob = null
        ws?.close(1000, "bye"); ws = null
        teardownRoom()
        scope.coroutineContext[Job]?.children?.forEach { it.cancel() }
        _ui.value = CamUi()
    }

    fun relockPicture() { capturer?.relock() }

    // ---------------------------------------------------------------- join + LiveKit

    private suspend fun mainLoop() {
        var backoff = 1000L
        while (scope.isActive) {
            val invite = prefs.invite
            if (invite.isNullOrBlank()) { fail("Scan the camera QR code in VibeNation."); return }
            try {
                _ui.update { it.copy(stage = if (it.publishing || it.stage == CamUi.Stage.Reconnecting) CamUi.Stage.Reconnecting else CamUi.Stage.Joining, error = null) }
                val j = join(prefs.base, invite, prefs.name, prefs.camId)
                prefs.camId = j.camId
                prefs.name = j.name
                camToken = j.camToken
                ws?.cancel() // make the status socket pick up the fresh token
                _ui.update { it.copy(num = j.num, name = j.name, stage = CamUi.Stage.Connecting) }
                val reason = runRoom(j)
                Log.i(TAG, "room ended: $reason")
                backoff = 1000L
                _ui.update { it.copy(stage = CamUi.Stage.Reconnecting, publishing = false, error = reason) }
            } catch (e: JoinRejected) {
                fail(e.message ?: "This camera link was refused.")
                return
            } catch (e: kotlinx.coroutines.CancellationException) {
                throw e
            } catch (e: Exception) {
                Log.w(TAG, "join/connect failed", e)
                _ui.update { it.copy(stage = CamUi.Stage.Reconnecting, publishing = false, error = friendly(e)) }
            } finally {
                teardownRoom()
            }
            delay(backoff)
            backoff = (backoff * 2).coerceAtMost(8000L)
        }
    }

    private fun fail(msg: String) {
        _ui.update { it.copy(stage = CamUi.Stage.Failed, error = msg, publishing = false) }
    }

    private fun friendly(e: Exception): String = when (e) {
        is java.net.UnknownHostException -> "No internet — check Wi-Fi"
        is java.net.SocketTimeoutException -> "Server not answering"
        is java.net.ConnectException -> "Can't reach VibeNation"
        else -> e.message?.take(80) ?: "Connection problem"
    }

    data class Joined(val camId: Int, val num: String, val name: String, val livekitUrl: String, val token: String, val camToken: String)

    private suspend fun join(base: String, k: String, name: String?, camId: Int?): Joined = withContext(Dispatchers.IO) {
        val body = JSONObject().apply {
            put("k", k)
            put("device", "android")
            if (!name.isNullOrBlank()) put("name", name)
            if (camId != null && camId > 0) put("camId", camId)
        }.toString().toRequestBody("application/json".toMediaType())
        val req = Request.Builder().url("$base/api/cams/join").post(body).build()
        http.newCall(req).execute().use { res ->
            val text = res.body?.string().orEmpty()
            val json = try { JSONObject(text) } catch (_: Exception) { JSONObject() }
            if (res.code == 403 || res.code == 400) throw JoinRejected(json.optString("error", "This camera link has expired. Scan the QR code in VibeNation again."))
            if (!res.isSuccessful) throw java.io.IOException("Server error ${res.code}")
            Joined(
                camId = json.getInt("camId"),
                num = json.optString("num", "CAM ${json.getInt("camId")}"),
                name = json.optString("name", name ?: ""),
                livekitUrl = json.getString("livekitUrl"),
                token = json.getString("token"),
                camToken = json.getString("camToken"),
            )
        }
    }

    /** Connect, publish, and suspend until the room is gone. Returns a human reason. */
    private suspend fun runRoom(j: Joined): String {
        val fmt = LockingCameraCapturer.pickFormat(appContext) ?: throw IllegalStateException("No usable camera found")
        val r = LiveKit.create(
            appContext,
            RoomOptions(adaptiveStream = false, dynacast = true),
            LiveKitOverrides(audioOptions = AudioOptions(audioHandler = NoAudioHandler())),
        )
        room = r
        val ended = CompletableDeferred<String>()
        val rj = CompletableDeferred<String>()
        rejoin = rj
        val eventsJob = scope.launch {
            r.events.events.collect { ev ->
                when (ev) {
                    is RoomEvent.Reconnecting -> _ui.update { it.copy(stage = CamUi.Stage.Reconnecting, error = "Network blip — reconnecting") }
                    is RoomEvent.Reconnected -> _ui.update { it.copy(stage = CamUi.Stage.Streaming, error = null) }
                    is RoomEvent.Disconnected -> ended.complete(ev.error?.message ?: "Disconnected (${ev.reason})")
                    else -> {}
                }
            }
        }
        try {
            r.connect(j.livekitUrl, j.token)
            val cap = LockingCameraCapturer(appContext, fmt, displayRotation, capListener)
            capturer = cap
            val t = r.localParticipant.createVideoTrack(
                name = "camera",
                capturer = cap,
                options = LocalVideoTrackOptions(
                    position = null,
                    captureParams = VideoCaptureParameter(fmt.width, fmt.height, fmt.fps, adaptOutputToDimensions = false),
                ),
            )
            track = t
            t.startCapture()
            val ok = r.localParticipant.publishVideoTrack(
                t,
                VideoTrackPublishOptions(
                    name = "camera",
                    videoEncoding = VideoEncoding(8_000_000, fmt.fps),
                    simulcast = true,
                    videoCodec = "h264",
                    source = Track.Source.CAMERA,
                    simulcastLayers = listOf(
                        CustomVideoPreset(VideoCaptureParameter(640, 360, 30), VideoEncoding(700_000, 30)),
                    ),
                ),
            )
            if (!ok) throw IllegalStateException("Publishing the camera failed")
            _ui.update { it.copy(stage = CamUi.Stage.Streaming, publishing = true, error = null, width = fmt.width, height = fmt.height, targetFps = fmt.fps) }
            listener?.onTrack(r, t)
            // Wait for the room to end, or for the status socket to ask for a fresh join.
            return kotlinx.coroutines.selects.select {
                ended.onAwait { it }
                rj.onAwait { it }
            }
        } finally {
            eventsJob.cancel()
        }
    }

    private fun teardownRoom() {
        listener?.onTrackGone()
        try { track?.stopCapture() } catch (_: Exception) {}
        try { track?.dispose() } catch (_: Exception) {}
        track = null
        capturer = null
        room?.let { r ->
            try { r.disconnect() } catch (_: Exception) {}
            try { r.release() } catch (_: Exception) {}
        }
        room = null
        lastBytes = null
        _ui.update { it.copy(publishing = false, kbps = null, fps = null) }
    }

    private val capListener = object : LockingCameraCapturer.Listener {
        override fun onPicture(locked: Boolean, wb: String, exposure: String) {
            _ui.update { it.copy(locked = locked, wb = wb, exposure = exposure) }
        }
        override fun onFps(fps: Double) { _ui.update { it.copy(fps = fps) } }
        override fun onCameraError(message: String) {
            _ui.update { it.copy(error = message) }
            rejoin?.complete(message)
        }
    }

    // ---------------------------------------------------------------- status + tally socket

    private suspend fun wsLoop() {
        var backoff = 1000L
        while (scope.isActive) {
            val ct = camToken
            if (ct == null) { delay(500); continue }
            val closed = CompletableDeferred<Int>()
            val url = prefs.base.replaceFirst("https://", "wss://").replaceFirst("http://", "ws://") + "/cam-ws?ct=$ct"
            ws = http.newWebSocket(Request.Builder().url(url).build(), object : WebSocketListener() {
                override fun onOpen(webSocket: WebSocket, response: Response) {
                    _ui.update { it.copy(statusConnected = true) }
                    sendStatus(webSocket)
                }
                override fun onMessage(webSocket: WebSocket, text: String) {
                    val m = try { JSONObject(text) } catch (_: Exception) { return }
                    when (m.optString("type")) {
                        "tally" -> _ui.update { it.copy(live = m.optBoolean("live")) }
                        "rename" -> {
                            val n = m.optString("name").take(40)
                            if (n.isNotBlank()) { prefs.name = n; _ui.update { it.copy(name = n) } }
                        }
                    }
                }
                override fun onClosing(webSocket: WebSocket, code: Int, reason: String) { webSocket.close(code, null); closed.complete(code) }
                override fun onClosed(webSocket: WebSocket, code: Int, reason: String) { closed.complete(code) }
                override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) { closed.complete(-1) }
            })
            val code = closed.await()
            ws = null
            _ui.update { it.copy(statusConnected = false) }
            if (code == 4003) {
                // Server forgot this camera (restart or expired token): join again for a new token.
                if (camToken == ct) camToken = null
                rejoin?.complete("Status token refused")
                backoff = 1000L
            } else {
                delay(backoff)
                backoff = (backoff * 2).coerceAtMost(5000L)
                if (code == 1000) backoff = 1000L
            }
            if (_ui.value.statusConnected) backoff = 1000L
        }
    }

    private suspend fun statusLoop() {
        while (scope.isActive) {
            val t = telemetry.read()
            _ui.update { it.copy(battery = t.battery, charging = t.charging, temp = t.tempC, wifi = t.wifi, thermalWarn = t.thermalWarn) }
            updateKbps()
            ws?.let { sendStatus(it) }
            delay(2000)
        }
    }

    private fun sendStatus(socket: WebSocket) {
        val u = _ui.value
        val o = JSONObject().apply {
            put("type", "status")
            put("battery", u.battery)
            put("charging", u.charging)
            u.temp?.let { put("temp", it) }
            put("wifi", u.wifi)
            u.kbps?.let { put("kbps", it) }
            u.fps?.let { put("fps", Math.round(it * 10) / 10.0) }
            if (u.width > 0) { put("width", u.width); put("height", u.height) }
            put("wb", if (u.locked) "${u.wb} · lock" else u.wb)
            put("exposure", u.exposure)
            put("locked", u.locked)
            put("landscape", true) // activity is locked to sensorLandscape
        }
        socket.send(o.toString())
    }

    private var lastBytes: Pair<Long, Long>? = null // bytes, time ms

    private suspend fun updateKbps() {
        val t = track ?: return
        val report = try { t.getRTCStats() } catch (_: Exception) { null } ?: return
        var bytes = 0L
        for (s in report.statsMap.values) {
            if (s.type != "outbound-rtp") continue
            when (val b = s.members["bytesSent"]) {
                is BigInteger -> bytes += b.toLong()
                is Number -> bytes += b.toLong()
            }
        }
        val now = System.currentTimeMillis()
        val prev = lastBytes
        lastBytes = bytes to now
        if (prev != null && now > prev.second && bytes >= prev.first) {
            val kbps = ((bytes - prev.first) * 8 / (now - prev.second)).toInt()
            _ui.update { it.copy(kbps = kbps) }
        }
    }

    fun destroy() {
        stop()
        scope.cancel()
    }

    companion object { private const val TAG = "VnSession" }
}
