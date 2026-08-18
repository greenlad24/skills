package com.stagemix.app

import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import com.stagemix.app.ui.StageMixApp

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // BEFORE ANYTHING ELSE: start the first-moments log. From here on
        // every step of startup is written down, so a close during launch
        // or connect leaves a trail instead of a silence.
        BootLog.init(this)
        BootLog.log("APP", "MainActivity.onCreate")
        installCrashLogger()
        // Catch a FREEZE, not just a throw. The boot log shows the app
        // dying at takeover with no Java exception — the signature of an
        // ANR (the system killing a frozen UI thread). This writes the
        // main thread's stuck stack to crash.txt before that kill.
        AnrWatchdog.start(this)
        // A mixer console never sleeps mid-show; screen-on also keeps the
        // low-latency Wi-Fi lock honored and Doze away (see checklist).
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        AppState.load(this)
        AppState.loadSwitches(this)
        // IF WE CRASHED LAST TIME, do not fling the operator straight back
        // into it: auto-start stays off this launch, and the crash is shown
        // and kept in crash.txt next to the logs so it can be read and fixed.
        val prefs = getSharedPreferences("stagemix-crash", MODE_PRIVATE)
        val crashedLast = prefs.getBoolean("crashed", false)
        BootLog.log("APP", "crashedLast=$crashedLast autoStart=" +
            "${AppState.autoStart.value} conn=${AppState.conn.value} " +
            "ip='${AppState.config.value.mixerIp}'")
        if (crashedLast) {
            prefs.edit().putBoolean("crashed", false).apply()
            // Show the actual crash on screen so it can be SCREENSHOT and
            // sent — crash.txt lives in scoped storage a file manager can't
            // reach, so a photo of this screen is the quickest way to get
            // the stack trace out of the tablet and fix the real cause.
            val crash = runCatching {
                java.io.File(getExternalFilesDir(null) ?: filesDir, "crash.txt")
                    .takeIf { it.exists() }?.readText()
            }.getOrNull()
            AppState.lastError.value = buildString {
                append("Closed unexpectedly last time — auto-start is OFF. ")
                append("SCREENSHOT this and send it so it can be fixed:\n\n")
                if (crash.isNullOrBlank()) append("(no crash file found)")
                else append(crash.lineSequence().take(30).joinToString("\n"))
            }
        }
        // SHOWING THE APP WITHOUT A BAND.
        //
        // Every screen past the first needs sixteen channels of live
        // meter off a console that is only ever in one room, so there
        // was no way to look at this thing away from a gig — or to
        // photograph it. `--ez demo true` drives the whole screen from
        // a synthetic band. It cannot reach a mixer: see DemoStage.
        if (intent?.getBooleanExtra("demo", false) == true) {
            DemoStage.stop()
            AppState.startTab = intent?.getIntExtra("tab", 0) ?: 0
            DemoStage.start(
                directing = intent?.getBooleanExtra("mixing", true) != false)
            // Let the demo be launched straight into a panic state, so the
            // headless smoke test can check that FROZEN / WAITING render
            // truthfully without depending on an emulator tap landing on a
            // key drawn in the top bar of a screen that recomposes ~20x a
            // second — which it does not do reliably. The keys' handlers
            // are one-line AppState flips; what matters at a gig is that
            // each state they produce shows the truth, which this drives.
            if (intent?.getBooleanExtra("frozen", false) == true)
                AppState.frozenAll.value = true
            if (intent?.getBooleanExtra("muted", false) == true)
                AppState.stageMuted.value = true
        }
        // OPEN IT AND IT GOES.
        //
        // No IP to type, no button to find in the dark: it broadcasts
        // for the desk on the mixer's own Wi-Fi and, once it answers,
        // takes the mains by itself (MixerService does that half). The
        // saved IP is tried first and discovery is the fallback, so a
        // rig that always uses the same address connects instantly.
        else if (!crashedLast && AppState.autoStart.value &&
                 AppState.conn.value == AppState.Conn.DISCONNECTED) {
            BootLog.log("APP", "auto-connect: starting MixerService (CONNECT)")
            MixerService.cmd(this, MixerService.ACTION_CONNECT,
                "ip" to AppState.config.value.mixerIp)
        }
        BootLog.log("APP", "setContent — first frame")
        setContent { StageMixApp() }
    }

    /**
     * Catch ANY uncaught crash — including a Compose/UI-thread one the
     * engine's own try/catch cannot reach — to a file next to the show
     * logs, and remember that it happened. A crash on the tablet used to
     * just vanish; now it can be read the morning after and, more to the
     * point, exported and sent so it can be fixed.
     */
    private fun installCrashLogger() {
        val prev = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, ex ->
            runCatching {
                BootLog.log("CRASH", "${ex.javaClass.simpleName}: " +
                    (ex.message ?: "") + " on ${thread.name}")
            }
            runCatching {
                val dir = getExternalFilesDir(null) ?: filesDir
                java.io.File(dir, "crash.txt").writeText(buildString {
                    appendLine("StageMix crash — " + java.util.Date())
                    appendLine("thread: " + thread.name)
                    appendLine()
                    append(android.util.Log.getStackTraceString(ex))
                })
                getSharedPreferences("stagemix-crash", MODE_PRIVATE)
                    .edit().putBoolean("crashed", true).apply()
            }
            prev?.uncaughtException(thread, ex)
        }
    }
}
