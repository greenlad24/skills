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
    /**
     * The autopilot running on this Mac, when there is one — so the
     * strips can show what the engine currently believes is plugged into
     * each channel.
     */
    var client: (() -> DeskClient?)? = null
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

    /** a heading over a group of buttons, so the row reads as sentences */
    private fun caption(text: String): JLabel {
        val l = JLabel(text)
        l.foreground = MUTED
        l.font = Font(Font.SANS_SERIF, Font.BOLD, 10)
        l.border = BorderFactory.createEmptyBorder(0, 0, 0, 8)
        return l
    }

    private fun row(): JPanel {
        val p = JPanel()
        p.background = BG
        p.layout = BoxLayout(p, BoxLayout.X_AXIS)
        p.border = BorderFactory.createEmptyBorder(6, 12, 2, 12)
        return p
    }

    /**
     * The controls, in two rows that say what they are for.
     *
     * They were one row of eleven buttons with names like "MIXING", and
     * the operator's verdict on that was fair: "I don't [want] so many
     * buttons that I don't understand their meaning (what is mixing on
     * or off)". The two that mattered were the two least explicable —
     * "AUTOPILOT on this Mac" starts the app in a WATCHING state where
     * it hears everything and touches nothing, and "MIXING" is what
     * actually lets it move the faders. Neither label said so, and the
     * distinction is the single most important thing on the screen. Now
     * each button says what it will do when clicked, and each row says
     * what the buttons under it are about.
     */
    private fun header(): JPanel {
        val stack = JPanel()
        stack.background = BG
        stack.layout = BoxLayout(stack, BoxLayout.Y_AXIS)
        stack.add(playbackRow())
        stack.add(appRow())
        return stack
    }

    private fun playbackRow(): JPanel {
        val p = row()
        p.add(caption("THE BAND"))

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
        val jump = JButton("⏩ +5 MIN")
        jump.toolTipText = "skip the take forward five minutes — get to a " +
            "later part of the night without sitting through it"
        jump.addActionListener {
            jump.isEnabled = false
            note("jumping five minutes forward…")
            Thread {
                player.skipForward(300.0)
                javax.swing.SwingUtilities.invokeLater { jump.isEnabled = true }
            }.apply { isDaemon = true }.start()
        }
        val folder = JButton("Choose folder…")
        folder.addActionListener { chooseFolder() }
        val forget = JButton("Forget these")
        forget.toolTipText = "the channels are remembered and put back on " +
            "the next launch; this clears that"
        forget.addActionListener { onForgetSession?.invoke() }
        p.add(play); p.add(Box.createHorizontalStrut(8)); p.add(rewind)
        p.add(Box.createHorizontalStrut(8)); p.add(jump)
        p.add(Box.createHorizontalStrut(8)); p.add(mute)
        p.add(Box.createHorizontalStrut(16)); p.add(folder)
        p.add(Box.createHorizontalStrut(4)); p.add(forget)
        p.add(Box.createHorizontalStrut(8)); p.add(tone)
        p.add(Box.createHorizontalGlue())
        val hint = JLabel("click a channel to load one file at a time")
        hint.foreground = MUTED
        hint.font = Font(Font.SANS_SERIF, Font.PLAIN, 11)
        p.add(hint)
        return p
    }

    private fun appRow(): JPanel {
        val p = row()
        p.add(caption("THE APP"))

        // testing without the tablet: run the autopilot right here
        val auto = JButton("START THE APP")
        auto.toolTipText = "runs the tablet's engine on this Mac and opens " +
            "its screen — it starts out WATCHING, not mixing"
        val mixing = JButton("it is only WATCHING — click to let it mix")
        mixing.toolTipText = "until you click this, the app hears everything " +
            "and touches nothing; after it, it moves the channel faders"
        mixing.isEnabled = false
        auto.addActionListener {
            autopilotOn = !autopilotOn
            onAutopilot?.invoke(autopilotOn)
            auto.text = if (autopilotOn) "STOP THE APP" else "START THE APP"
            mixing.isEnabled = autopilotOn
            if (!autopilotOn) {
                mixingOn = false
                mixing.text = "it is only WATCHING — click to let it mix"
            }
        }
        mixing.addActionListener {
            mixingOn = !mixingOn
            onMixing?.invoke(mixingOn)
            mixing.text = if (mixingOn) "it is MIXING — click to stop it"
                          else "it is only WATCHING — click to let it mix"
        }
        p.add(auto); p.add(Box.createHorizontalStrut(6)); p.add(mixing)

        // the parts of a real stage a recording cannot contain
        p.add(Box.createHorizontalStrut(20))
        p.add(caption("THE ROOM"))
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
    /**
     * "This channel is a…"
     *
     * The app can hear that a channel is a moving melody in the voice
     * band with nothing underneath it. It cannot hear whether that is a
     * singer or a saxophone — they are the same thing to a hundred-bin
     * spectrum, which is exactly why both work as the top line over a
     * band. On the rig this was written for, the channel the desk calls
     * SAXOPHONE is a singer and the one it calls UTILITY 3 is the
     * saxophone, and no amount of listening will sort that out.
     *
     * A person sorts it out in one click, and it is remembered against
     * the console's own name for the channel, so it holds for the rest
     * of this night and every night after.
     */
    private fun instrumentMenu(ch: Int): javax.swing.JPopupMenu {
        val m = javax.swing.JPopupMenu("what is on channel ${ch + 1}?")
        val choices = listOf(
            com.stagemix.engine.Role.VOCAL to "a lead vocal",
            com.stagemix.engine.Role.BACKING_VOCAL to "a backing vocal",
            com.stagemix.engine.Role.COLOR to "a horn, sax or harmonica",
            com.stagemix.engine.Role.SOLO_GTR to "a lead guitar",
            com.stagemix.engine.Role.RHYTHM_GTR to "a rhythm guitar",
            com.stagemix.engine.Role.KEYS to "keys or piano",
            com.stagemix.engine.Role.DRUMS to "the drum kit",
            com.stagemix.engine.Role.PERCUSSION to "congas or percussion",
            com.stagemix.engine.Role.FOUNDATION to "kick or bass",
            com.stagemix.engine.Role.TALK to "a talkback mic (never mixed)")
        for ((role, text) in choices) {
            val i = javax.swing.JMenuItem(text)
            i.addActionListener {
                val e = client?.invoke()?.engine
                if (e == null) { note("start the app first"); return@addActionListener }
                e.setRole(ch, role)
                note("ch%02d is %s — remembered for '%s' from now on"
                    .format(java.util.Locale.ROOT, ch + 1, text,
                        e.state[ch]?.name ?: "?"))
                strips.getOrNull(ch)?.repaint()
            }
            m.add(i)
        }
        return m
    }

    private inner class Strip(val ch: Int, var label: String) : JPanel() {
        init {
            background = PANEL
            preferredSize = Dimension(68, 520)
            border = BorderFactory.createEmptyBorder(6, 4, 6, 4)
            toolTipText = "click the name to load a file on channel " +
                "${ch + 1}; drag the fader on the right to overrule the " +
                "app; RIGHT-CLICK to say what is plugged in"
            componentPopupMenu = instrumentMenu(ch)
            // The fader lane is a real fader. Without this there was no
            // way to put a hand on the desk at all, so the one thing that
            // matters most about a mixing autopilot — that a human can
            // overrule it instantly, mid-song — could not be tried before
            // a show. Dragging here goes out over OSC exactly as a move
            // on the surface or in Mixing Station would.
            val drag = object : java.awt.event.MouseAdapter() {
                private fun inFaderLane(e: java.awt.event.MouseEvent) =
                    e.x >= 44
                override fun mousePressed(e: java.awt.event.MouseEvent) {
                    if (inFaderLane(e)) setFaderFromY(e.y)
                }
                override fun mouseDragged(e: java.awt.event.MouseEvent) {
                    if (inFaderLane(e)) setFaderFromY(e.y)
                }
                override fun mouseClicked(e: java.awt.event.MouseEvent) {
                    if (!inFaderLane(e)) chooseFile(ch)
                }
            }
            addMouseListener(drag)
            addMouseMotionListener(drag)
        }

        /** where the mouse is, as a fader position */
        private fun setFaderFromY(my: Int) {
            val top = 48; val bot = height - 54
            val span = (bot - top).toFloat()
            if (span <= 0) return
            val frac = ((bot - my) / span).coerceIn(0f, 1f)
            console.humanFader(ch, frac * 60f - 60f)
            repaint()
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

            // WHAT IS ON THIS CHANNEL, as the app currently hears it.
            // The desk label is whatever the last engineer typed; this
            // is what the audio says, and the two are not always the
            // same channel-for-channel. Dimmed while it is still
            // listening, so a guess is never mistaken for a verdict.
            val eng = client?.invoke()?.engine
            eng?.channelIdent(ch)?.let { id ->
                g2.font = Font(Font.SANS_SERIF, Font.PLAIN, 9)
                g2.color = when {
                    id.label == "LEAD VOCAL" -> LIVE
                    id.evidence >= 1f && id.heard -> OK
                    else -> MUTED
                }
                g2.drawString(id.label.take(11), 4, 35)
            }
            // and whether the app will touch this fader at all. Muted
            // outranks both: the meter is pre-mute and goes on showing
            // signal, so nothing else on the strip would give it away.
            if (eng != null && eng.isDeskMuted(ch)) {
                g2.font = Font(Font.SANS_SERIF, Font.PLAIN, 8)
                g2.color = WARN
                g2.drawString("muted by you", 4, 44)
            } else if (eng != null && eng.balanceAdopted) {
                g2.font = Font(Font.SANS_SERIF, Font.PLAIN, 8)
                if (eng.held(ch)) {
                    g2.color = ACCENT
                    g2.drawString("🔒 yours", 4, 44)
                } else {
                    g2.color = MUTED
                    g2.drawString("following", 4, 44)
                }
            }

            val top = 48; val bot = h - 54
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
