package com.stagemix.app

import com.stagemix.app.ui.Levels
import com.stagemix.app.ui.Spectra
import com.stagemix.engine.Decision
import com.stagemix.engine.Role
import com.stagemix.engine.StageEngine
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlin.math.abs
import kotlin.math.sin

/**
 * A band, without a band.
 *
 * The app cannot show itself: every screen past the first needs sixteen
 * channels of live meter off a console that is only ever in one room. So
 * there was no way to look at the thing away from a gig — not to check a
 * change, not to show somebody, and not to take a picture of it.
 *
 * This drives the same state the real service publishes, from a
 * synthetic band: drums that hit on the beat, a bass and a guitar that
 * sustain, a singer who phrases, a sax that comes in for a solo. It
 * writes ONLY to the UI's own state — it never opens a socket, never
 * builds an engine that could write to a desk, and refuses to start at
 * all if the app is connected to a real mixer.
 *
 * It is also how the screenshots in the release are taken.
 */
object DemoStage {

    @Volatile var running = false; private set
    private var job: Job? = null
    private val scope = CoroutineScope(Dispatchers.Default)

    private val NAMES = listOf(
        "DRUM KICK", "DRUM SNAR", "DRUM OVRH", "DI 1", "GUITAR AMP",
        "PIANO L", "PIANO R", "GUITAR DI", "VOCAL CEN", "VOCAL PIA",
        "VOX 3", "BASS DI", "CONGO 2", "DI 2", "UTILITY 3", "HARMONICA")

    private val ROLES = listOf(
        Role.FOUNDATION, Role.PERCUSSION, Role.PERCUSSION, Role.RHYTHM_GTR,
        Role.SOLO_GTR, Role.KEYS, Role.KEYS, Role.RHYTHM_GTR,
        Role.VOCAL, Role.VOCAL, Role.VOCAL, Role.FOUNDATION,
        Role.PERCUSSION, Role.FOUNDATION, Role.COLOR, Role.COLOR)

    private val IDENT = listOf(
        "kick", "snare", "overheads", "guitar", "lead guitar",
        "piano / keys", "piano / keys", "guitar", "voice", "voice",
        "voice", "bass", "congas / toms", "bass", "horn / reed",
        "horn / reed")

    /** the channels the engine promises never to move */
    private val HELD = setOf(0, 1, 2, 8, 9, 10, 11, 12, 13)

    /** where the app has put each fader, in dB from the operator's own */
    private val OFFSET = listOf(
        0f, 0f, 0f, -1.8f, -2.6f, +0.9f, +0.7f, -0.4f,
        0f, 0f, 0f, 0f, 0f, 0f, +2.0f, -1.2f)

    private val BASE = listOf(
        -5.1f, -12.9f, -18.7f, -3.5f, +1.0f, -3.3f, -3.4f, +0.4f,
        +5.6f, +4.9f, +3.0f, -6.9f, -14.9f, +1.0f, -4.5f, -5.6f)

    fun start(directing: Boolean = true) {
        // A demo must never be able to touch a console. If this app is
        // talking to a mixer, it is a show and not a demonstration.
        if (AppState.conn.value != AppState.Conn.DISCONNECTED) return
        if (running) return
        running = true
        AppState.everConnected.value = true
        AppState.conn.value = AppState.Conn.CONNECTED
        AppState.mixer.value = AppState.MixerInfo(
            name = "MR18-DEMO", model = "MR18", firmware = "1.18",
            ip = "demo")
        AppState.directing.value = directing
        AppState.balanceKept.value = directing
        AppState.doctorOn.value = true
        AppState.mixingSinceMs.value =
            android.os.SystemClock.elapsedRealtime() - 1_465_000L
        AppState.leadVocal.value = 8
        AppState.channelsMixed.value = 16
        AppState.nightsCount.value = 4
        AppState.tasteSummary.value = "vocal +0.8 · rhythm gtr -0.6"
        AppState.mixerChannelNames.value =
            NAMES.indices.associateWith { NAMES[it] }
        AppState.ringNotches.value = mapOf(8 to "196 Hz -4.0 dB")
        AppState.busNames.value = mapOf(
            0 to "CENTER MON", 1 to "PIANO MON", 2 to "DRUM IEM",
            3 to "BASS MON", 5 to "IN EAR 2")
        AppState.wedges.value = listOf(
            AppState.WedgeUi(1, "CENTER MON", "CENTRE_VOCAL",
                listOf(8, 3, 9), -4.2f, 8),
            AppState.WedgeUi(2, "PIANO MON", "GUITAR", listOf(4, 8, 5)),
            AppState.WedgeUi(3, "DRUM IEM", "DRUM_IEM", listOf(0, 1, 11)),
            AppState.WedgeUi(4, "BASS MON", "BASS", listOf(11, 13, 12)),
            AppState.WedgeUi(6, "IN EAR 2", "PLAYER_IEM", listOf(5, 13, 8)))

        AppState.strips.value = NAMES.indices.map { i ->
            AppState.StripUi(
                channel = i, name = NAMES[i], role = ROLES[i],
                levelDb = -30f, active = true, frozen = false,
                offsetDb = if (directing) OFFSET[i] else 0f,
                targetDb = BASE[i] + OFFSET[i],
                identLabel = IDENT[i], identHeard = true,
                identEvidence = 1f,
                heldByYou = HELD.contains(i) && directing,
                deskMuted = i == 10,
                baselineDb = BASE[i], takeoverDb = BASE[i],
                riding = directing && (i == 4 || i == 14))
        }
        AppState.decisions.value = listOf(
            Decision(1465.0, "ride", 4, null, -1.4f,
                "GUITAR AMP is +1.6 dB off the balance — easing it back down"),
            Decision(1402.0, "feature", 14, null, +2.0f,
                "UTILITY 3 stepped up — leaving the feature with the player"),
            Decision(1290.0, "ident", 14, null, 0f,
                "UTILITY 3: instrument -> horn — it sounds like a reed " +
                "(a steady tone with a strong second harmonic)"),
            Decision(1104.0, "keep", null, null, 0f,
                "keeping the balance on the desk — 9 channels held where " +
                "they are; from here only the source moving, a solo or an " +
                "instrument arriving changes anything"),
            Decision(980.0, "arrive", 15, null, 0f,
                "HARMONICA came in — listening before placing it"),
            Decision(880.0, "override", 5, null, +1.2f,
                "PIANO L — you moved it +1.2 dB; adopting your level, " +
                "holding off 2 min — learned: keys taste now +0.2 dB"),
            Decision(40.0, "takeover", null, null, 0f,
                "autopilot took the mains — listening for 20s, then " +
                "keeping the balance you made"))
        AppState.health.value = StageEngine.MixHealth(91, 88, 3, 1465)

        job = scope.launch {
            var t = 0.0
            val lv = FloatArray(16) { -80f }
            while (isActive) {
                // a band: drums on the beat, everything else sustaining
                val beat = 0.5
                fun hit(per: Double, phase: Double, peak: Float, dec: Double) =
                    maxOf(peak - (((t - phase) % per + per) % per / dec)
                        .toFloat() * 40f, -90f)
                lv[0] = hit(beat * 2, 0.0, -9f, 0.17)
                lv[1] = hit(beat * 2, beat, -12f, 0.13)
                lv[2] = hit(beat / 2, 0.0, -22f, 0.09)
                lv[12] = hit(beat, 0.25, -20f, 0.14)
                lv[3] = -21f + 3f * sin(t * 1.7).toFloat()
                lv[4] = -14f + 4f * sin(t * 0.9).toFloat()
                lv[5] = -18f + 3f * sin(t * 1.1).toFloat()
                lv[6] = -19f + 3f * sin(t * 1.3 + 1).toFloat()
                lv[7] = -26f + 2f * sin(t * 2.1).toFloat()
                // the singer phrases: on for three bars, off for one
                val phrase = ((t / beat).toInt()) % 8
                lv[8] = if (phrase < 6) -11f + 2f * sin(t * 3.0).toFloat()
                        else -70f
                lv[9] = if (phrase in 2..5) -19f else -70f
                lv[10] = -90f                      // muted on the desk
                lv[11] = -12f + 2f * sin(t * 0.7).toFloat()
                lv[13] = -16f + 2f * sin(t * 0.6).toFloat()
                lv[14] = -13f + 5f * sin(t * 1.4).toFloat()   // the solo
                lv[15] = -34f + 4f * sin(t * 2.3).toFloat()
                Levels.publish(lv)

                // and a plausible spectrum for each, so the strips have
                // the shape the analyzer would have built
                if ((t * 20).toInt() % 20 == 0) for (c in 0 until 16) {
                    val peakBand = when (ROLES[c]) {
                        Role.FOUNDATION -> 3
                        Role.PERCUSSION -> if (c == 2) 18 else 9
                        Role.KEYS -> 10
                        Role.VOCAL, Role.BACKING_VOCAL -> 11
                        Role.COLOR -> 13
                        else -> 12
                    }
                    val bins = FloatArray(100) { b ->
                        val d = abs(b / 4f - peakBand)
                        -6f - d * 3.2f - 8f * sin(b * 0.7f + t.toFloat())
                    }
                    Spectra.publish(c, bins)
                }

                AppState.tickMs.value =
                    android.os.SystemClock.elapsedRealtime()
                AppState.leadDb.value = -13.5f + 2f * sin(t * 0.8).toFloat()
                AppState.bandDb.value = -16.5f + 2f * sin(t * 0.5).toFloat()
                t += 0.05
                delay(50)
            }
        }
    }

    fun stop() {
        job?.cancel(); job = null
        running = false
        AppState.conn.value = AppState.Conn.DISCONNECTED
        AppState.everConnected.value = false
        AppState.directing.value = false
        AppState.strips.value = emptyList()
        AppState.decisions.value = emptyList()
    }
}
