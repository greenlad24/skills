package com.stagemix.app

import android.content.Context
import android.os.Handler
import android.os.Looper
import java.io.File
import java.util.Date

/**
 * THE MISSING STACK TRACE FOR A FREEZE.
 *
 * On a real desk the app has been closing with NO Java exception: the
 * boot log runs right up to takeover and stops, `crashedLast` is never
 * set, and not one CRASH/ERR/FATAL line is written — even though every
 * exception path now writes one. That is the signature of the SYSTEM
 * killing the process, not of code throwing. The commonest reason for
 * that, exactly when the UI first floods with sixteen channels of live
 * meter data at takeover, is an ANR: the main (UI) thread stops
 * responding for long enough that Android terminates the app.
 *
 * A thrown error leaves a stack trace; a freeze leaves nothing. This
 * watchdog IS that missing stack trace. A background thread asks the main
 * thread to answer once a second; when it has not answered for [stallMs],
 * it captures the main thread's stack — where it is stuck — and writes it
 * to crash.txt (and the boot log) before the system pulls the app down.
 * Next launch shows it on the setup screen, ready to send.
 *
 * It touches nothing but a timestamp and is a daemon thread, so it cannot
 * itself hold the app up or keep it alive.
 */
object AnrWatchdog {
    @Volatile private var lastResponded = 0L
    private var thread: Thread? = null

    fun start(ctx: Context, stallMs: Long = 6000L) {
        if (thread != null) return
        val app = ctx.applicationContext
        val main = Handler(Looper.getMainLooper())
        lastResponded = System.currentTimeMillis()
        val t = Thread({
            var reportedThisStall = false
            while (!Thread.currentThread().isInterrupted) {
                val token = System.currentTimeMillis()
                main.post { lastResponded = token }
                try { Thread.sleep(1000) }
                catch (e: InterruptedException) { return@Thread }
                val since = System.currentTimeMillis() - lastResponded
                if (since >= stallMs) {
                    if (!reportedThisStall) {
                        reportedThisStall = true
                        runCatching { report(app, since) }
                    }
                } else {
                    reportedThisStall = false
                }
            }
        }, "stagemix-anr-watchdog")
        t.isDaemon = true
        thread = t
        t.start()
        BootLog.log("ANR", "watchdog armed (stall ${stallMs}ms)")
    }

    private fun report(ctx: Context, stalledMs: Long) {
        val trace = Looper.getMainLooper().thread.stackTrace
        BootLog.log("ANR", "MAIN THREAD BLOCKED ${stalledMs}ms — capturing stack")
        val build = runCatching {
            "${BuildConfig.GIT_SHA} v${BuildConfig.VERSION_NAME}"
        }.getOrDefault("(unknown)")
        val text = buildString {
            appendLine("StageMix FROZE (ANR) — the UI thread stopped " +
                "responding for ${stalledMs}ms — ${Date()}")
            appendLine("build $build")
            appendLine("Android was about to kill the app. This is NOT a " +
                "code exception — the main thread was stuck here:")
            appendLine()
            for (f in trace) appendLine("    at $f")
            appendLine()
            appendLine("— the app's first moments —")
            for (l in BootLog.recent()) appendLine(l)
        }
        runCatching {
            File(ctx.getExternalFilesDir(null) ?: ctx.filesDir, "crash.txt")
                .writeText(text)
        }
        runCatching {
            ctx.getSharedPreferences("stagemix-crash", Context.MODE_PRIVATE)
                .edit().putBoolean("crashed", true).apply()
        }
    }
}
