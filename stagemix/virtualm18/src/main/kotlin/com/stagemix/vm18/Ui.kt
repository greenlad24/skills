package com.stagemix.vm18

import java.awt.BorderLayout
import java.awt.Color
import java.awt.Dimension
import java.awt.Font
import java.awt.Graphics
import java.awt.Graphics2D
import java.awt.GridLayout
import java.awt.RenderingHints
import java.io.File
import javax.swing.BorderFactory
import javax.swing.Box
import javax.swing.BoxLayout
import javax.swing.JButton
import javax.swing.JFileChooser
import javax.swing.JFrame
import javax.swing.JLabel
import javax.swing.JPanel
import javax.swing.JScrollPane
import javax.swing.JTextArea
import javax.swing.SwingUtilities
import javax.swing.Timer

private val BG = Color(0x0B, 0x0E, 0x14)
private val PANEL = Color(0x11, 0x16, 0x1F)
private val INK = Color(0xE9, 0xEE, 0xF5)
private val MUTED = Color(0x7C, 0x8A, 0xA0)
private val OK = Color(0x36, 0xD3, 0x99)
private val WARN = Color(0xF5, 0xA6, 0x23)
private val LIVE = Color(0xFF, 0x46, 0x52)
private val BAD = Color(0xE5, 0x48, 0x4E)
private val ACCENT = Color(0x5A, 0x9B, 0xFF)

/**
 * The bench window: sixteen strips showing what the desk is hearing and
 * where the tablet has put each fader, so a fader move on the app is
 * visible here within a frame and audible in the room immediately.
 *
 * Deliberately plain — this is test equipment, not the product. The
 * product is the tablet; this is the console it thinks it is talking to.
 */
class Bench(
    private val console: Console,
    private val player: Player,
    private val names: List<String>,
    private val files: MutableList<File?>,
) {
    private val frame = JFrame("Virtual M18 — StageMix bench")
    /** told when a channel gets a new file, so the console renames it */
    var onChannelLoaded: ((Int, File?, String) -> Unit)? = null
    /** start / stop the autopilot running on this machine */
    var onAutopilot: ((Boolean) -> Unit)? = null
    /** true once the autopilot has taken the mains */
    var onMixing: ((Boolean) -> Unit)? = null
    /** the operator wants the next launch to start empty */
    var onForgetSession: (() -> Unit)? = null
    private val strips = ArrayList<Strip>()
    private val status = JLabel(" ")
    private val logArea = JTextArea(8, 100)
    private var autopilotOn = false
    private var mixingOn = false

    fun show() {
        frame.defaultCloseOperation = JFrame.EXIT_ON_CLOSE
        frame.contentPane.background = BG
        frame.layout = BorderLayout(8, 8)

        frame.add(header(), BorderLayout.NORTH)

        val grid = JPanel(GridLayout(1, names.size, 6, 0))
        grid.background = BG
        grid.border = BorderFactory.createEmptyBorder(4, 10, 4, 10)
        for (c in names.indices) {
            val s = Strip(c, names[c])
            strips.add(s); grid.add(s)
        }
        frame.add(grid, BorderLayout.CENTER)

        logArea.background = PANEL; logArea.foreground = MUTED
        logArea.font = Font(Font.MONOSPACED, Font.PLAIN, 11)
        logArea.isEditable = false
        val south = JPanel(BorderLayout())
        south.background = BG
        status.foreground = INK
        status.font = Font(Font.MONOSPACED, Font.PLAIN, 12)
        status.border = BorderFactory.createEmptyBorder(4, 12, 4, 12)
        south.add(status, BorderLayout.NORTH)
        south.add(JScrollPane(logArea), BorderLayout.CENTER)
        frame.add(south, BorderLayout.SOUTH)

        frame.pack()
        frame.setSize(maxOf(1100, names.size * 74), 720)
        frame.setLocationRelativeTo(null)
        frame.isVisible = true

        Timer(50) { tick() }.start()
    }

    private fun header(): JPanel {
        val p = JPanel()
        p.background = BG
        p.layout = BoxLayout(p, BoxLayout.X_AXIS)
        p.border = BorderFactory.createEmptyBorder(10, 12, 4, 12)

        val play = JButton("▶  PLAY")
        play.addActionListener {
            if (player.playing) { player.pause(); play.text = "▶  PLAY" }
            else { player.play(); play.text = "❚❚ PAUSE" }
        }
        val tone = JButton("TEST TONE")
        tone.toolTipText = "a second of 1 kHz straight to the speakers — " +
            "if you hear this, the output works and the problem is the files"
        tone.addActionListener {
            Thread { player.testTone() }.apply { isDaemon = true }.start()
            note("test tone — if you hear nothing, it is the Mac's output " +
                "device, not the channels")
        }
        val mute = JButton("MUTE SPEAKERS")
        mute.addActionListener {
            player.mute = !player.mute
            mute.text = if (player.mute) "UNMUTE" else "MUTE SPEAKERS"
        }
        val rewind = JButton("⏮  START")
        rewind.addActionListener { player.rewind() }
        val folder = JButton("Choose folder…")
        folder.addActionListener { chooseFolder() }
        val forget = JButton("Forget these")
        forget.toolTipText = "the channels are remembered and put back on " +
            "the next launch; this clears that"
        forget.addActionListener { onForgetSession?.invoke() }
        p.add(play); p.add(Box.createHorizontalStrut(8)); p.add(rewind)
        p.add(Box.createHorizontalStrut(8)); p.add(tone)
        p.add(Box.createHorizontalStrut(8)); p.add(mute)
        p.add(Box.createHorizontalStrut(16)); p.add(folder)
        p.add(Box.createHorizontalStrut(4)); p.add(forget)

        // testing without the tablet: run the autopilot right here
        p.add(Box.createHorizontalStrut(20))
        val auto = JButton("AUTOPILOT on this Mac")
        val mixing = JButton("MIXING")
        mixing.isEnabled = false
        auto.addActionListener {
            autopilotOn = !autopilotOn
            onAutopilot?.invoke(autopilotOn)
            auto.text = if (autopilotOn) "stop autopilot"
                        else "AUTOPILOT on this Mac"
            mixing.isEnabled = autopilotOn
            if (!autopilotOn) { mixingOn = false; mixing.text = "MIXING" }
        }
        mixing.addActionListener {
            mixingOn = !mixingOn
            onMixing?.invoke(mixingOn)
            mixing.text = if (mixingOn) "MIXING — ON" else "MIXING"
        }
        p.add(auto); p.add(Box.createHorizontalStrut(6)); p.add(mixing)

        // the parts of a real stage a recording cannot contain
        p.add(Box.createHorizontalStrut(20))
        val roomBtn = JButton("ROOM LOOP: off")
        roomBtn.toolTipText = "let the PA back into the open mics, so " +
            "feedback can actually happen"
        roomBtn.addActionListener {
            player.room.enabled = !player.room.enabled
            roomBtn.text = if (player.room.enabled) "ROOM LOOP: ON"
                           else "ROOM LOOP: off"
            note(if (player.room.enabled)
                "room loop on — the mains now feed back into the open mics"
                else "room loop off")
        }
        val provoke = JButton("PROVOKE FEEDBACK")
        provoke.toolTipText = "as if someone walked a mic into the boxes"
        provoke.addActionListener {
            player.room.enabled = true
            roomBtn.text = "ROOM LOOP: ON"
            player.room.provoke(6.0)
            note("someone just walked a mic in front of the PA")
        }
        val drop = JButton("DROP WI-FI 8s")
        drop.addActionListener {
            console.stall(8.0)
            note("radio dropout — the console goes silent for 8 s")
        }
        p.add(roomBtn); p.add(Box.createHorizontalStrut(6)); p.add(provoke)
        p.add(Box.createHorizontalStrut(6)); p.add(drop)

        // getting the log OFF this machine is the whole point of having
        // one, so it is a button and not a file path to go hunting for
        p.add(Box.createHorizontalStrut(20))
        val copy = JButton("📋 COPY LOG")
        copy.toolTipText = "the whole log, plus the state of everything, " +
            "on the clipboard — paste it straight into a message"
        copy.addActionListener { copyLog(copy) }
        p.add(copy)
        val hint = JLabel("  (click a channel to load one file at a time)")
        hint.foreground = MUTED
        hint.font = Font(Font.SANS_SERIF, Font.PLAIN, 11)
        p.add(hint)
        p.add(Box.createHorizontalGlue())

        val ip = JLabel("point the tablet at this Mac's IP, port 10024")
        ip.foreground = ACCENT
        ip.font = Font(Font.SANS_SERIF, Font.BOLD, 13)
        p.add(ip)
        return p
    }

    private fun tick() {
        for (s in strips) s.repaint()
        val subs = console.subscriberCount()
        status.text = ("t %s   |   %s   |   tablet: %s   |   in %d / out %d " +
            "(%d lost)   |   RTA ch%02d   |   %s")
            .format(java.util.Locale.ROOT,
                clock(player.positionSec),
                // the transport, in full: a stopped loop and a paused one
                // look identical from the outside and are not the same
                if (player.playing) "PLAYING %d blocks, peak %.2f"
                    .format(java.util.Locale.ROOT, player.blocksPlayed,
                        player.lastMixPeak)
                else if (!player.loopAlive) "TRANSPORT DEAD"
                else "stopped",
                if (console.stalled()) "RADIO DOWN"
                else if (subs > 0) "CONNECTED ($subs)" else "not connected",
                console.packetsIn, console.packetsOut, console.packetsDropped,
                console.rtaSource + 1,
                player.room.status())
        status.foreground = when {
            console.stalled() -> BAD
            player.room.amplitude > 0.02 -> LIVE
            subs > 0 -> OK
            else -> WARN
        }
    }

    private fun clock(s: Double) =
        "%d:%02d:%05.2f".format(java.util.Locale.ROOT,
            (s / 3600).toInt(), ((s % 3600) / 60).toInt(), s % 60)

    fun note(line: String) = SwingUtilities.invokeLater {
        logArea.append(line + "\n")
        logArea.caretPosition = logArea.document.length
    }

    /**
     * The log, plus a snapshot of everything that would otherwise have to
     * be asked for one question at a time: the machine, the audio
     * devices, the transport's own account of itself, every channel and
     * what is loaded on it, and where the tablet stands.
     */
    private fun copyLog(button: JButton) {
        val sb = StringBuilder()
        sb.appendLine("=== StageMix bench log ===")
        sb.appendLine("when: " + java.util.Date())
        sb.appendLine("java: " + System.getProperty("java.version") +
            " on " + System.getProperty("os.name") + " " +
            System.getProperty("os.version") + " " +
            System.getProperty("os.arch"))
        sb.appendLine()
        sb.appendLine("--- transport ---")
        sb.appendLine(player.state())
        sb.appendLine("room: " + player.room.status())
        sb.appendLine()
        sb.appendLine("--- audio devices ---")
        try {
            for (m in javax.sound.sampled.AudioSystem.getMixerInfo())
                sb.appendLine("  ${m.name} — ${m.description}")
        } catch (e: Exception) { sb.appendLine("  unavailable: ${e.message}") }
        sb.appendLine()
        sb.appendLine("--- console ---")
        sb.appendLine("subscribers=${console.subscriberCount()} " +
            "in=${console.packetsIn} out=${console.packetsOut} " +
            "dropped=${console.packetsDropped} " +
            "rtaSource=ch%02d".format(java.util.Locale.ROOT,
                console.rtaSource + 1))
        sb.appendLine()
        sb.appendLine("--- channels ---")
        for (c in 0 until strips.size) {
            val f = player.fileOf(c)
            sb.appendLine("  ch%02d %-20s src%7.1f dB  out%7.1f dB  " +
                "fader%+6.2f  %s".format(java.util.Locale.ROOT, c + 1,
                strips[c].label,
                console.inputDb.getOrElse(c) { -128f },
                player.postDb.getOrElse(c) { -128f },
                console.faderDb(c),
                f?.name ?: "(nothing loaded)"))
        }
        sb.appendLine()
        sb.appendLine("--- log ---")
        sb.append(logArea.text)

        try {
            java.awt.Toolkit.getDefaultToolkit().systemClipboard.setContents(
                java.awt.datatransfer.StringSelection(sb.toString()), null)
            val n = sb.count { it == '\n' }
            button.text = "✓ COPIED ($n lines)"
            javax.swing.Timer(2500) { button.text = "📋 COPY LOG" }
                .apply { isRepeats = false }.start()
            note("log copied to the clipboard — paste it into a message")
        } catch (e: Exception) {
            note("could not reach the clipboard (${e.message}) — the same " +
                "log is at ~/StageMix/bench-console.log")
        }
    }

    /** one channel: the source the desk hears, and the tablet's fader */
    private inner class Strip(val ch: Int, var label: String) : JPanel() {
        init {
            background = PANEL
            preferredSize = Dimension(68, 520)
            border = BorderFactory.createEmptyBorder(6, 4, 6, 4)
            toolTipText = "click to put a file on channel ${ch + 1}"
            addMouseListener(object : java.awt.event.MouseAdapter() {
                override fun mouseClicked(e: java.awt.event.MouseEvent) =
                    chooseFile(ch)
            })
        }

        override fun paintComponent(g: Graphics) {
            super.paintComponent(g)
            val g2 = g as Graphics2D
            g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING,
                RenderingHints.VALUE_ANTIALIAS_ON)
            val w = width; val h = height
            g2.color = MUTED
            g2.font = Font(Font.SANS_SERIF, Font.PLAIN, 9)
            g2.drawString("ch%02d".format(java.util.Locale.ROOT, ch + 1), 4, 12)
            g2.color = INK
            g2.font = Font(Font.SANS_SERIF, Font.BOLD, 10)
            g2.drawString(label.take(9), 4, 25)

            val top = 34; val bot = h - 54
            val span = (bot - top).toFloat()
            fun y(db: Float) = bot - (span * ((db + 60f) / 60f)
                .coerceIn(0f, 1f)).toInt()

            // scale
            g2.color = Color(0x1D, 0x24, 0x30)
            for (d in intArrayOf(0, -10, -20, -30, -40, -50))
                g2.drawLine(2, y(d.toFloat()), w - 2, y(d.toFloat()))

            // what the desk hears, pre-fader
            val src = console.inputDb.getOrElse(ch) { -128f }
            g2.color = if (src > -3f) LIVE else ACCENT
            val sy = y(src)
            g2.fillRect(6, sy, 16, bot - sy)

            // what the room hears, after the tablet's fader
            val post = player.postDb.getOrElse(ch) { -128f }
            g2.color = OK
            val py = y(post)
            g2.fillRect(26, py, 16, bot - py)

            // the fader itself
            val f = console.faderDb(ch)
            val fy = y(f)
            g2.color = INK
            g2.fillRect(46, fy - 2, 18, 4)
            g2.color = MUTED
            g2.drawLine(54, top, 54, bot)

            g2.font = Font(Font.MONOSPACED, Font.PLAIN, 10)
            g2.color = ACCENT
            g2.drawString("%.0f".format(java.util.Locale.ROOT, src), 4, bot + 14)
            g2.color = OK
            g2.drawString("%.0f".format(java.util.Locale.ROOT, post), 26, bot + 14)
            g2.color = INK
            g2.drawString("%+.1f".format(java.util.Locale.ROOT, f), 4, bot + 28)
            g2.color = MUTED
            g2.font = Font(Font.SANS_SERIF, Font.PLAIN, 8)
            g2.drawString(
                if (player.fileOf(ch) == null) "click to load" else "src out fdr",
                4, bot + 40)
        }
    }

    // ------------------------------------------------------------------
    private fun chooseFile(ch: Int) {
        val fc = JFileChooser()
        fc.dialogTitle = "Channel ${ch + 1} — choose the file"
        player.fileOf(ch)?.parentFile?.let { fc.currentDirectory = it }
        fc.fileFilter = object : javax.swing.filechooser.FileFilter() {
            override fun accept(f: File) = f.isDirectory ||
                f.name.lowercase().let {
                    it.endsWith(".wav") || it.endsWith(".mp3") ||
                    it.endsWith(".aif") || it.endsWith(".aiff") }
            override fun getDescription() = "Audio (wav, mp3, aiff)"
        }
        if (fc.showOpenDialog(frame) != JFileChooser.APPROVE_OPTION) return
        val f = fc.selectedFile
        if (!player.load(ch, f)) return
        files[ch] = f
        val nm = f.name.substringBeforeLast('.')
            .replace(Regex("^\\s*\\d{1,2}[ _.-]*"), "").trim().take(20)
        strips[ch].label = nm
        onChannelLoaded?.invoke(ch, f, nm)
        note("ch%02d is now %s".format(java.util.Locale.ROOT, ch + 1, nm))
    }

    private fun chooseFolder() {
        val fc = JFileChooser()
        fc.dialogTitle = "Choose the folder holding the night's channels"
        fc.fileSelectionMode = JFileChooser.DIRECTORIES_ONLY
        if (fc.showOpenDialog(frame) != JFileChooser.APPROVE_OPTION) return
        val (fs, ns) = assignFolder(fc.selectedFile)
        for (c in 0 until 16) {
            if (fs[c] == null) continue
            if (!player.load(c, fs[c])) continue
            files[c] = fs[c]
            strips[c].label = ns[c]
            onChannelLoaded?.invoke(c, fs[c], ns[c])
        }
        note("loaded ${fs.count { it != null }} channels from " +
            fc.selectedFile.name)
    }
}
