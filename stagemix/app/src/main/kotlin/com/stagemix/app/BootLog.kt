package com.stagemix.app

import android.content.Context
import android.util.Log
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * THE FIRST-MOMENTS LOG.
 *
 * ShowLog — the night's real log — only opens once the mixer has
 * answered. Everything before that answer used to happen with nothing
 * writing it down: the app opening, the crash-recovery check, the
 * auto-connect, the foreground-service start, the Wi-Fi binding, the
 * discovery broadcast, the socket setup, the handshake. On a tablet that
 * closes AT connect, that silent window is exactly the one that matters.
 *
 * BootLog is alive from the very first line of onCreate. It writes a
 * small, timestamped file (`logs/boot.txt`) next to the show logs, keeps
 * the last session's file aside as `boot-prev.txt` so a crash loop still
 * leaves two lives to read, holds the lines in memory so the show log can
 * fold them in the moment it opens, and is prepended to every export — so
 * the log the operator sends reads from the first moment the app drew a
 * frame, not from the first meter packet.
 *
 * It never touches the network and is bounded in size, so it is safe to
 * leave on for the life of every launch.
 */
object BootLog {
    /** a boot story is a few kB; cap it so nothing can grow without bound */
    private const val MAX_BYTES = 64 * 1024
    private const val MAX_LINES_MEM = 500

    private val clock = SimpleDateFormat("HH:mm:ss.SSS", Locale.ROOT)
    private val recent = ArrayDeque<String>()
    private var file: File? = null
    private var baseDir: File? = null
    private var t0 = 0L

    /** Call FIRST thing in onCreate. Idempotent within a process. */
    @Synchronized fun init(ctx: Context) {
        if (file != null) return
        t0 = System.currentTimeMillis()
        baseDir = ctx.getExternalFilesDir(null) ?: ctx.filesDir
        val dir = File(ctx.getExternalFilesDir(null) ?: ctx.filesDir, "logs")
        runCatching { dir.mkdirs() }
        val f = File(dir, "boot.txt")
        // keep the previous life aside — a crash loop needs both
        runCatching {
            if (f.exists()) f.copyTo(File(dir, "boot-prev.txt"), overwrite = true)
        }
        runCatching { f.writeText("") }
        file = f
        val build = runCatching {
            "${BuildConfig.GIT_SHA} v${BuildConfig.VERSION_NAME}"
        }.getOrDefault("(unknown)")
        log("BOOT", "StageMix opening — build $build — ${Date()}")
    }

    /**
     * One timestamped line, to the file, to memory, and to logcat. Never
     * throws: a full disk or a closed file must not take the app down —
     * this logger exists to explain crashes, not to cause them.
     */
    @Synchronized fun log(tag: String, msg: String) {
        val since = if (t0 == 0L) 0L
                    else (System.currentTimeMillis() - t0).coerceAtLeast(0L)
        val line = "%s +%6dms %-6s %s".format(Locale.ROOT,
            clock.format(Date()), since, tag, msg)
        recent.addLast(line)
        while (recent.size > MAX_LINES_MEM) recent.removeFirst()
        runCatching { Log.i("StageMixBoot", line) }
        val f = file ?: return
        runCatching { if (f.length() < MAX_BYTES) f.appendText(line + "\n") }
    }

    /** the boot lines held in memory, for the show log to fold in on open */
    @Synchronized fun recent(): List<String> = recent.toList()

    /** the whole boot file, for the export to prepend */
    fun text(ctx: Context): String = runCatching {
        File(File(ctx.getExternalFilesDir(null) ?: ctx.filesDir, "logs"),
            "boot.txt").takeIf { it.exists() }?.readText()
    }.getOrNull() ?: ""

    /**
     * Write the crash report file — the same crash.txt the export folds
     * in and the setup screen shows. Used by the draw guard, which has no
     * Context of its own but must still land its trace where the export
     * and the next launch look for it.
     */
    @Synchronized fun writeCrash(text: String) {
        val dir = baseDir ?: return
        runCatching { File(dir, "crash.txt").writeText(text) }
    }
}
