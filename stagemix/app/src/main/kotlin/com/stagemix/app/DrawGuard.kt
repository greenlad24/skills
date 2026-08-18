package com.stagemix.app

import android.util.Log

/**
 * SURVIVE A BAD DRAW, AND CATCH IT IN THE ACT.
 *
 * The app vanishes the instant the mixer or monitor strips render a value
 * from a real desk that some draw did not expect. Two things have to be
 * true at once: the show must not die (a live tool cannot vanish
 * mid-set), and the cause must not be lost (swallowing it silently would
 * leave the next night just as blind).
 *
 * This runs a draw block, and on the FIRST exception it captures the full
 * stack — where the draw actually failed — to the boot log (so EXPORT
 * carries it out) and to the on-screen error, then keeps the app alive.
 * Every later failure is counted, not re-reported, so a 60-fps redraw
 * cannot spam. The one trace it keeps is the one that names the bug.
 */
object DrawGuard {
    @Volatile private var reported = false
    @Volatile private var swallowed = 0

    inline fun run(block: () -> Unit) {
        try { block() } catch (t: Throwable) { report(t) }
    }

    fun report(t: Throwable) {
        swallowed++
        if (reported) return
        reported = true
        val stack = Log.getStackTraceString(t)
        BootLog.log("DRAW", "RENDER CRASH CAUGHT (app kept running): " +
            "${t.javaClass.simpleName}: ${t.message}")
        for (line in stack.lineSequence().take(20)) BootLog.log("DRAW", line)
        // Land it in crash.txt too, so EXPORT folds it into the log and
        // the next launch shows it — the same place every other crash goes.
        BootLog.writeCrash(buildString {
            append("StageMix render error (caught — app kept running) — ")
            append(java.util.Date())
            append("\n\n")
            append(stack)
        })
        AppState.lastError.value = buildString {
            append("A drawing error was caught — the app kept running ")
            append("instead of closing. SCREENSHOT this or tap EXPORT:\n\n")
            append("${t.javaClass.simpleName}: ${t.message}\n\n")
            append(stack.lineSequence().take(16).joinToString("\n"))
        }
    }
}
