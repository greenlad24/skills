package com.stagemix.vm18

import java.io.File

/**
 * What was loaded last time.
 *
 * Picking the same sixteen files out of the same folder after every
 * rebuild is the kind of friction that stops a thing being tested, so
 * the bench remembers the channel assignment and puts it back on the
 * next launch. Only the paths and the names — the audio is never
 * copied anywhere.
 *
 * Stored one channel per line as `index<tab>name<tab>path`, in the same
 * folder as the logs, so it can be read, edited or deleted by hand.
 */
object Session {

    private val file = File(File(System.getProperty("user.home"), "StageMix"),
        "bench-session.txt")

    val path: String get() = file.path

    fun save(files: List<File?>, names: List<String>) {
        try {
            file.parentFile?.mkdirs()
            file.writeText(buildString {
                appendLine("# StageMix bench — the channels loaded last time.")
                appendLine("# Delete this file, or start with --fresh, to " +
                    "begin empty.")
                for (c in files.indices) {
                    val f = files[c] ?: continue
                    appendLine("$c\t${names.getOrElse(c) { "" }}\t${f.path}")
                }
            })
        } catch (e: Exception) { /* a bench that cannot remember still runs */ }
    }

    /** what was loaded last time, or null if there is nothing to restore */
    fun load(): Restored? {
        if (!file.isFile) return null
        val files = MutableList<File?>(16) { null }
        val names = MutableList(16) { "" }
        val missing = ArrayList<String>()
        var found = 0
        try {
            for (line in file.readLines()) {
                if (line.startsWith("#") || line.isBlank()) continue
                val p = line.split("\t")
                if (p.size < 3) continue
                val idx = p[0].toIntOrNull() ?: continue
                if (idx !in 0 until 16) continue
                val f = File(p[2])
                names[idx] = p[1]
                if (f.isFile) { files[idx] = f; found++ }
                else missing.add("ch%02d %s".format(java.util.Locale.ROOT,
                    idx + 1, f.name))
            }
        } catch (e: Exception) { return null }
        if (found == 0 && missing.isEmpty()) return null
        return Restored(files, names, found, missing)
    }

    fun forget() { runCatching { file.delete() } }

    class Restored(
        val files: MutableList<File?>,
        val names: MutableList<String>,
        val found: Int,
        /** files that have moved or been deleted since */
        val missing: List<String>,
    )
}
