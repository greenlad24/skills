package com.stagemix.app

import android.content.Context
import android.content.Intent
import android.util.Log
import androidx.core.content.FileProvider
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * "Export logs" — hand the night's show log to WhatsApp, mail, Drive or
 * anything else on the tablet, through the normal Android share sheet.
 *
 * Two details make this actually work rather than nearly work:
 *
 *  · The file is copied to a `.txt` before sharing. WhatsApp decides
 *    what it will accept from the extension and the MIME type, and it
 *    refuses `.log`; the same bytes named `.txt` attach as a document.
 *  · The tablet is on the mixer's Wi-Fi, with no internet. The share
 *    itself is offline — WhatsApp queues the attachment and sends it
 *    the moment the tablet is back on a normal network, so exporting at
 *    the end of the night works without leaving the M18's Wi-Fi.
 */
object LogExport {

    /** the newest show log, or null if nothing has been recorded */
    fun latest(ctx: Context): File? =
        File(ctx.getExternalFilesDir(null) ?: ctx.filesDir, "logs")
            .listFiles()?.filter { it.isFile && it.length() > 0 }
            ?.maxByOrNull { it.lastModified() }

    fun all(ctx: Context): List<File> =
        File(ctx.getExternalFilesDir(null) ?: ctx.filesDir, "logs")
            .listFiles()?.filter { it.isFile }?.sortedByDescending {
                it.lastModified() } ?: emptyList()

    /**
     * Build the share intent for [log]. Returns null if the file cannot
     * be staged (no external storage) — the caller shows the path
     * instead so the operator can fetch it over USB.
     */
    fun shareIntent(ctx: Context, log: File): Intent? {
        return try {
            val outDir = File(ctx.getExternalFilesDir(null) ?: ctx.filesDir,
                "export")
                .apply { mkdirs() }
            // one staged copy, .txt so WhatsApp takes it as a document
            outDir.listFiles()?.forEach { runCatching { it.delete() } }
            val staged = File(outDir, log.name.removeSuffix(".log") + ".txt")
            log.copyTo(staged, overwrite = true)

            val uri = FileProvider.getUriForFile(
                ctx, "${ctx.packageName}.logs", staged)
            val when_ = SimpleDateFormat("EEE d MMM, HH:mm", Locale.ROOT)
                .format(Date(log.lastModified()))
            // If the app has crashed, its stack trace is the most important
            // thing to get out — put it right at the top of the message so
            // it comes through even when the attachment does not.
            val crash = runCatching {
                File(ctx.getExternalFilesDir(null) ?: ctx.filesDir, "crash.txt")
                    .takeIf { it.exists() }?.readText()
            }.getOrNull()
            // The app's first moments — everything from open to the first
            // meter packet. On a crash at connect this is the whole story.
            val boot = BootLog.text(ctx)
            Intent(Intent.ACTION_SEND).apply {
                type = "text/plain"
                putExtra(Intent.EXTRA_STREAM, uri)
                putExtra(Intent.EXTRA_SUBJECT, "StageMix show log — $when_")
                putExtra(Intent.EXTRA_TEXT, buildString {
                    if (!crash.isNullOrBlank()) {
                        append("⚠️ CRASH REPORT — please send this:\n")
                        append(crash.take(6000))
                        append("\n\n————————————————\n\n")
                    }
                    if (boot.isNotBlank()) {
                        append("— the app's first moments —\n")
                        append(boot.takeLast(4000))
                        append("\n\n————————————————\n\n")
                    }
                    append("StageMix show log — $when_\n")
                    append("${log.length() / 1024} KB. ")
                    append("Levels, EQ, compression and every decision the ")
                    append("autopilot made, with reasons.\n\n")
                    append(tail(log, 12))
                })
                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                clipData = android.content.ClipData.newRawUri("log", uri)
            }
        } catch (e: Exception) {
            Log.w("StageMix", "export failed: ${e.message}")
            null
        }
    }

    /** the last [n] lines, for the message body / a quick look */
    fun tail(log: File, n: Int): String = try {
        val lines = log.readLines()
        lines.takeLast(n).joinToString("\n")
    } catch (e: Exception) { "" }

    /**
     * The night on one screen. The full log runs to megabytes — right
     * for an attachment, useless in a chat message — so this pulls out
     * the parts you would actually read first: what the rig was, what
     * you did, what the network did, how the balance ended up, and what
     * the engine spent the night deciding.
     */
    fun digest(log: File): String = try {
        val lines = log.readLines()
        fun tagged(t: String) = lines.filter { it.contains(" $t ") }
        val head = tagged("HEAD")
        val user = tagged("USER")
        val net = tagged("NET")
        val howl = tagged("HOWL")
        val sums = tagged("SUM")
        val dec = tagged("DEC")

        // what the engine spent the night doing, by kind
        val kinds = LinkedHashMap<String, Int>()
        for (l in dec) {
            val k = l.substringAfter(" DEC ").trim().substringBefore(' ')
            if (k.isNotBlank()) kinds.merge(k, 1, Int::plus)
        }
        // the balance as it stood at the last snapshot
        val lastMix = lines.lastOrNull { it.contains(" MIX ") }
        val lastLvlBlock = run {
            val idx = lines.indexOfLast { it.contains(" MIX ") }
            if (idx < 0) emptyList()
            else lines.drop(idx + 1).takeWhile {
                it.contains(" LVL ") || it.contains(" MIX ") }
        }
        // per-channel fader travel: how hard it worked on each channel
        val travel = LinkedHashMap<String, Int>()
        for (l in tagged("FADER")) {
            val ch = l.substringAfter(" FADER ").take(4)
            travel.merge(ch, 1, Int::plus)
        }

        buildString {
            appendLine("STAGEMIX — THE NIGHT IN SHORT")
            appendLine("(the full log is the attachment; this is the summary)")
            appendLine()
            appendLine("== the rig ==")
            head.take(6).forEach { appendLine(it) }
            appendLine()
            if (user.isNotEmpty()) {
                appendLine("== what you did (${user.size} actions) ==")
                user.takeLast(25).forEach { appendLine(it) }
                appendLine()
            }
            if (howl.isNotEmpty()) {
                appendLine("== feedback / howl ==")
                howl.takeLast(10).forEach { appendLine(it) }
                appendLine()
            }
            if (net.isNotEmpty()) {
                appendLine("== network ==")
                net.takeLast(12).forEach { appendLine(it) }
                appendLine()
            }
            appendLine("== what it decided (whole night) ==")
            if (kinds.isEmpty()) appendLine("  (no decisions logged)")
            else kinds.entries.sortedByDescending { it.value }
                .forEach { appendLine("  ${it.key.padEnd(10)} ${it.value}") }
            appendLine()
            if (travel.isNotEmpty()) {
                appendLine("== fader moves per channel ==")
                travel.entries.sortedByDescending { it.value }.take(16)
                    .forEach { appendLine("  ${it.key} ${it.value}") }
                appendLine()
            }
            appendLine("== the balance at the end ==")
            lastMix?.let { appendLine(it) }
            lastLvlBlock.forEach { appendLine(it) }
            appendLine()
            appendLine("== minute by minute (last 15) ==")
            sums.takeLast(15).forEach { appendLine(it) }
        }
    } catch (e: Exception) { "could not read the log: ${e.message}" }

    fun shareDigest(ctx: Context, log: File): Intent =
        Intent(Intent.ACTION_SEND).apply {
            type = "text/plain"
            // the crash report rides on the short export too, so whichever
            // button the operator reaches for carries it out
            val crash = runCatching {
                File(ctx.getExternalFilesDir(null) ?: ctx.filesDir, "crash.txt")
                    .takeIf { it.exists() }?.readText()
            }.getOrNull()
            putExtra(Intent.EXTRA_TEXT, buildString {
                if (!crash.isNullOrBlank()) {
                    append("⚠️ CRASH REPORT — please send this:\n")
                    append(crash.take(6000))
                    append("\n\n————————————————\n\n")
                }
                append(digest(log))
            })
            putExtra(Intent.EXTRA_SUBJECT, "StageMix — the night in short")
        }
}
