package com.stagemix.vm18

import com.stagemix.engine.defaultRigProfile
import java.io.File
import java.util.Locale

/**
 * VIRTUAL M18 — the bench.
 *
 * Runs on a Mac (or anything with Java 17) and pretends to be the
 * console. Load a night the desk recorded, press play, and point the
 * real Android tablet at this machine's IP: the app connects, reads the
 * channel names, takes over the faders and starts mixing. The faders it
 * writes are applied to the audio coming out of the speakers, so you
 * hear the mix it is making while you watch it work on the tablet.
 *
 * Nothing in the app is modified or aware of this. It is talking OSC to
 * something that answers exactly as the console does — same addresses,
 * same meter banks at the same 50 ms cadence, same 1024-step fader
 * quantization, same 10-second subscription timeout.
 *
 *     java -jar virtual-m18.jar "/path/to/the night's channels"
 *
 * Files are matched to channels by a leading number in the name
 * ("09 Vocal Center.mp3" is channel 9). WAV and MP3 both work.
 *
 * Options:
 *   --port 10024     what the app connects to (the console's port)
 *   --rate 48000     output sample rate
 *   --start 600      begin this far into the night
 *   --echo           behave like firmware that reflects parameter
 *                    changes back to the sender — the case that used to
 *                    make the app freeze itself. Worth one run.
 *   --no-quantize    perfect faders instead of the console's 1024 steps
 *   --headless       no window (for a soak test over ssh)
 */
fun main(args: Array<String>) {
    var dir: String? = null
    var port = 10024
    var rate = 48000
    var echo = false
    var quantize = true
    var headless = false
    var startSec = 0.0
    var autopilot = false
    var i = 0
    while (i < args.size) {
        when (args[i]) {
            "--port" -> port = args[++i].toInt()
            "--rate" -> rate = args[++i].toInt()
            "--start" -> startSec = args[++i].toDouble()
            "--echo" -> echo = true
            "--no-quantize" -> quantize = false
            "--headless" -> headless = true
            "--autopilot" -> autopilot = true
            "-h", "--help" -> { usage(); return }
            else -> if (dir == null) dir = args[i]
        }
        i++
    }
    // Double-clicked from the Dock there are no arguments at all, so the
    // window opens empty and channels are loaded from it — by folder or
    // one at a time.
    if (dir == null && headless) { usage(); return }

    val folder = dir?.let { File(it) }
    if (folder != null && !folder.isDirectory) {
        System.err.println("not a folder: $folder"); return
    }
    val (files, names) = if (folder != null) assignFolder(folder)
        else MutableList<File?>(16) { null } to
            MutableList(16) { defaultRigProfile().getOrNull(it)?.name
                ?: "ch${it + 1}" }
    val live = files.count { it != null }
    if (live == 0 && headless) {
        System.err.println("no .wav or .mp3 files to play"); return
    }

    println("Virtual M18 — StageMix bench")
    println("  $live of 16 channels loaded" +
        (folder?.let { " from ${it.name}" } ?: ""))
    for (c in 0 until 16)
        println("  ch%02d  %-22s %s".format(Locale.ROOT, c + 1, names[c],
            files[c]?.name ?: "(silent)"))

    val console = Console(port = port, echoOwnWrites = echo,
        quantize = quantize)
    for (c in 0 until 16) console.names[c] = names[c]
    val player = Player(files, console, sampleRate = rate)

    val bench = if (headless) null else Bench(console, player, names, files)
    val note: (String) -> Unit = { s ->
        println(s); bench?.note(s)
    }
    console.log = note
    player.log = note
    console.onWrite = { addr, v ->
        // fader moves are the interesting ones; the doctor's EQ and comp
        // writes are logged too so the whole conversation is visible
        if (addr.endsWith("/mix/fader")) {
            val ch = addr.substring(4, 6).toIntOrNull()
            if (ch != null) note("tablet: ch%02d fader -> %+.2f dB"
                .format(Locale.ROOT, ch,
                    com.stagemix.engine.FaderLaw.floatToDb(v)))
        } else note("tablet: $addr = %.4f".format(Locale.ROOT, v))
    }

    player.open()
    console.start()
    note("ready — on the tablet, enter this Mac's IP and connect")
    note("(if it does not find it, check both are on the same Wi-Fi and " +
        "that the Mac firewall is not blocking UDP $port)")

    bench?.onChannelLoaded = { ch, _, nm ->
        console.names[ch] = nm
        names[ch] = nm
    }

    // The autopilot, on this machine, for testing without the tablet.
    // It goes over real UDP to the console above — same subscriptions,
    // same meter decoding, same fader writes, same quantization coming
    // back — so the whole path is exercised, not shortcut in-process.
    var client: DeskClient? = null
    val logDir = File(System.getProperty("user.home"), "StageMix")
    fun startAutopilot(): DeskClient {
        val c = DeskClient("127.0.0.1", port, logDir)
        c.log = note
        c.start()
        note("autopilot running on this Mac — logs in ${logDir.path}/logs")
        return c
    }
    bench?.onAutopilot = { on ->
        if (on) client = startAutopilot()
        else { client?.stop(); note("autopilot stopped — log: " +
            (client?.logFile()?.path ?: "none")); client = null }
    }
    bench?.onMixing = { on -> client?.directing = on }
    bench?.show()
    if (startSec > 0) note("starting %.0f s in".format(Locale.ROOT, startSec))
    if (autopilot) {
        client = startAutopilot()
        Thread.sleep(1500)
        client?.directing = true
    }
    if (headless) player.play()   // from the window you press PLAY yourself

    Runtime.getRuntime().addShutdownHook(Thread {
        client?.stop(); player.close(); console.stop()
    })
    player.run()
    note("end of the recording")
    if (headless) { player.close(); console.stop() }
}

/**
 * Match files to channels. A leading number wins ("12 Bass DI.wav" is
 * channel 12); otherwise files fill the channels in name order. Channel
 * names come from the files, so the app reads them off "the console"
 * exactly as it would live — which is also what sets the roles.
 */
internal fun assignFolder(folder: File): Pair<MutableList<File?>, MutableList<String>> {
    val rig = defaultRigProfile()
    val files = MutableList<File?>(16) { null }
    val names = MutableList(16) { rig.getOrNull(it)?.name ?: "ch${it + 1}" }
    val audio = folder.listFiles { f: File ->
        f.isFile && f.name.lowercase().let {
            it.endsWith(".wav") || it.endsWith(".mp3") ||
            it.endsWith(".aif") || it.endsWith(".aiff") }
    }?.sortedBy { it.name } ?: emptyList()

    val unnumbered = ArrayList<File>()
    for (f in audio) {
        val n = Regex("^\\s*(\\d{1,2})\\b").find(f.name)
            ?.groupValues?.get(1)?.toIntOrNull()
        if (n != null && n in 1..16 && files[n - 1] == null) {
            files[n - 1] = f
            names[n - 1] = cleanName(f)
        } else unnumbered.add(f)
    }
    var slot = 0
    for (f in unnumbered) {
        while (slot < 16 && files[slot] != null) slot++
        if (slot >= 16) break
        files[slot] = f; names[slot] = cleanName(f); slot++
    }
    return files to names
}

internal fun cleanName(f: File): String =
    f.name.substringBeforeLast('.')
        .replace(Regex("^\\s*\\d{1,2}[ _.-]*"), "").trim()
        .ifBlank { f.name }.take(20)

private fun usage() = println("""
    Virtual M18 — a console on the bench for testing the StageMix tablet.

      java -jar virtual-m18.jar "<folder of the night's channels>" [options]

    Put one file per channel in a folder, named with the channel number:
      01 Kick Drum.wav   05 Guitar Amp.mp3   09 Vocal Center.wav   ...
    WAV, MP3 and AIFF all work, and they do not have to be the same
    format or sample rate.

    Then press PLAY, and on the tablet enter this machine's IP address
    and connect. The app will read the channel names, take over the
    faders, and mix — and what you hear is its mix.

    options
      --port 10024    the port the app connects to (the console's)
      --rate 48000    output sample rate
      --start <sec>   begin this far into the night
      --echo          behave like firmware that reflects parameter changes
                      back to the sender (the case that used to freeze the
                      app solid) — worth one run
      --no-quantize   perfect faders instead of the console's 1024 steps
      --autopilot     run the StageMix autopilot on THIS machine and
                      switch MIXING on, so a night can be tested with no
                      tablet in the room. In the window it is a button.
      --headless      no window
""".trimIndent())
