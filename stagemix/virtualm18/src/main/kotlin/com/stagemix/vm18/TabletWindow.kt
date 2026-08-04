package com.stagemix.vm18

import com.stagemix.engine.Decision
import com.stagemix.engine.Role
import java.awt.BorderLayout
import java.awt.Color
import java.awt.Dimension
import java.awt.Font
import java.awt.Graphics
import java.awt.Graphics2D
import java.awt.GridLayout
import java.awt.RenderingHints
import java.util.Locale
import javax.swing.BorderFactory
import javax.swing.Box
import javax.swing.BoxLayout
import javax.swing.JButton
import javax.swing.JFrame
import javax.swing.JLabel
import javax.swing.JPanel
import javax.swing.JScrollPane
import javax.swing.JTextArea
import javax.swing.SwingUtilities
import javax.swing.Timer
import kotlin.math.abs

private val BG = Color(0x0B, 0x0E, 0x14)
private val PANEL = Color(0x11, 0x16, 0x1F)
private val PANEL2 = Color(0x16, 0x1B, 0x24)
private val INSET = Color(0x0A, 0x0D, 0x12)
private val LINE = Color(0x25, 0x2E, 0x3C)
private val INK = Color(0xE9, 0xEE, 0xF5)
private val INK2 = Color(0xAE, 0xBA, 0xCB)
private val MUTED = Color(0x7C, 0x8A, 0xA0)
private val OK = Color(0x36, 0xD3, 0x99)
private val WARN = Color(0xF5, 0xA6, 0x23)
private val BAD = Color(0xE5, 0x48, 0x4E)
private val LIVE = Color(0xFF, 0x46, 0x52)
private val ACCENT = Color(0x5A, 0x9B, 0xFF)

/**
 * The tablet's console screen, on the Mac.
 *
 * A Swing stand-in for the app's Compose UI, showing the same things off
 * the same live engine: the mode and hold reason, MIX HEALTH, the
 * feedback bar, one strip per channel with its role, level, correction
 * and doctor moves, and the running decision log.
 *
 * It is a replica of the screen, not the screen itself — the shipping UI
 * is Compose and only runs on Android. Everything it *displays* and
 * every button it drives is the real engine, so it is honest about the
 * mixing and not about the pixels.
 */
class TabletWindow(private val client: DeskClient) {
    private val frame = JFrame("StageMix — tablet screen (simulated)")
    private val strips = ArrayList<Strip>()
    private val mode = JLabel("PAUSED")
    private val health = JLabel(" ")
    private val hold = JLabel(" ")
    private val decisions = JTextArea(10, 90)

    fun show() {
        frame.defaultCloseOperation = JFrame.DISPOSE_ON_CLOSE
        frame.contentPane.background = BG
        frame.layout = BorderLayout(6, 6)
        frame.add(top(), BorderLayout.NORTH)

        val grid = JPanel(GridLayout(1, 16, 5, 0))
        grid.background = BG
        grid.border = BorderFactory.createEmptyBorder(2, 10, 6, 10)
        for (c in 0 until 16) { val s = Strip(c); strips.add(s); grid.add(s) }
        frame.add(grid, BorderLayout.CENTER)

        decisions.background = PANEL
        decisions.foreground = INK2
        decisions.font = Font(Font.MONOSPACED, Font.PLAIN, 11)
        decisions.isEditable = false
        val sp = JScrollPane(decisions)
        sp.border = BorderFactory.createEmptyBorder(0, 10, 10, 10)
        sp.preferredSize = Dimension(100, 170)
        frame.add(sp, BorderLayout.SOUTH)

        frame.setSize(1240, 780)
        frame.setLocation(40, 40)
        frame.isVisible = true
        Timer(100) { tick() }.start()
    }

    // ------------------------------------------------------------------
    private fun top(): JPanel {
        val col = JPanel()
        col.background = BG
        col.layout = BoxLayout(col, BoxLayout.Y_AXIS)
        col.border = BorderFactory.createEmptyBorder(10, 12, 2, 12)

        val r1 = row()
        val title = JLabel("STAGEMIX AI")
        title.foreground = INK
        title.font = Font(Font.SANS_SERIF, Font.BOLD, 20)
        r1.add(title); r1.add(Box.createHorizontalStrut(14))
        mode.font = Font(Font.SANS_SERIF, Font.BOLD, 13)
        r1.add(mode); r1.add(Box.createHorizontalStrut(16))
        health.foreground = INK2
        health.font = Font(Font.MONOSPACED, Font.PLAIN, 12)
        r1.add(health)
        r1.add(Box.createHorizontalGlue())
        col.add(r1)

        val r2 = row()
        r2.add(btn("Take over the mains") { client.directing = true })
        r2.add(btn("Hand back the mains") {
            client.directing = false
            note("you handed the mains back")
        })
        val freeze = btn("⏸ FREEZE ALL") { }
        freeze.addActionListener {
            client.engine.frozenAll = !client.engine.frozenAll
            freeze.text = if (client.engine.frozenAll) "▶ Resume"
                          else "⏸ FREEZE ALL"
            note(if (client.engine.frozenAll) "you pressed FREEZE ALL"
                 else "you released FREEZE ALL")
        }
        r2.add(freeze)
        val doc = btn("DOCTOR: on") { }
        doc.addActionListener {
            client.doctorOn = !client.doctorOn
            doc.text = if (client.doctorOn) "DOCTOR: on" else "DOCTOR: off"
            note("you turned the Channel Doctor " +
                if (client.doctorOn) "ON" else "OFF")
        }
        r2.add(doc)
        r2.add(btn("Show the log") {
            client.logFile()?.let {
                java.awt.Desktop.getDesktop().open(it.parentFile)
            }
        })
        r2.add(Box.createHorizontalGlue())
        col.add(r2)

        val r3 = row()
        val chips = listOf(
            "good" to "👍 Sounds great", "vocal_up" to "Vocal louder",
            "vocal_down" to "Vocal softer", "gtr_down" to "Less guitar",
            "gtr_up" to "More guitar", "keys_up" to "More piano",
            "keys_down" to "Less piano", "low_up" to "More low end",
            "perc_down" to "Less percussion", "color_down" to "Softer sax/harp")
        for ((kind, label) in chips) {
            val b = JButton(label)
            b.font = Font(Font.SANS_SERIF, Font.PLAIN, 11)
            b.margin = java.awt.Insets(1, 6, 1, 6)
            b.addActionListener {
                val said = client.engine.applyFeedback(kind, nowSec())
                note("you tapped '$label' — $said")
            }
            r3.add(b); r3.add(Box.createHorizontalStrut(4))
        }
        r3.add(Box.createHorizontalGlue())
        col.add(r3)

        val r4 = row()
        hold.foreground = WARN
        hold.font = Font(Font.SANS_SERIF, Font.PLAIN, 12)
        r4.add(hold); r4.add(Box.createHorizontalGlue())
        col.add(r4)
        return col
    }

    private fun row(): JPanel {
        val p = JPanel()
        p.background = BG
        p.layout = BoxLayout(p, BoxLayout.X_AXIS)
        p.border = BorderFactory.createEmptyBorder(3, 0, 3, 0)
        return p
    }

    private fun btn(text: String, action: () -> Unit): JButton {
        val b = JButton(text)
        b.font = Font(Font.SANS_SERIF, Font.PLAIN, 12)
        b.addActionListener { action() }
        return b
    }

    /** the engine's own clock — never the wall clock (see DeskClient) */
    private fun nowSec() = client.clock()

    fun note(s: String) = SwingUtilities.invokeLater {
        decisions.append("· $s\n")
        decisions.caretPosition = decisions.document.length
    }

    fun onDecision(d: Decision) = SwingUtilities.invokeLater {
        decisions.append("%-9s %-5s %s\n".format(Locale.ROOT, d.kind,
            d.channel?.let { "ch%02d".format(Locale.ROOT, it + 1) } ?: "",
            d.reason))
        decisions.caretPosition = decisions.document.length
    }

    // ------------------------------------------------------------------
    private fun tick() {
        val e = client.engine
        mode.text = when {
            e.frozenAll -> "FROZEN"
            client.directing -> "MIXING — AUTO"
            else -> "SHADOW — watching only"
        }
        mode.foreground = when {
            e.frozenAll -> BAD
            client.directing -> LIVE
            else -> WARN
        }
        val h = e.health()
        health.text = ("MIX HEALTH   vocal on top %s   ·   in place %d%%   " +
            "·   %d overrides").format(Locale.ROOT,
                if (h.vocalOnTopPct < 0) "n/a" else "${h.vocalOnTopPct}%",
                h.inPlacePct, h.overrides)
        hold.text = e.holdReason(nowSec()) ?: " "
        for (s in strips) s.repaint()
    }

    /** one channel strip, the same information the tablet shows */
    private inner class Strip(val ch: Int) : JPanel() {
        init {
            preferredSize = Dimension(74, 430)
            background = PANEL
        }

        override fun paintComponent(g: Graphics) {
            val e = client.engine
            val st = e.state[ch]
            val active = st?.active == true
            background = if (active) PANEL2 else PANEL
            super.paintComponent(g)
            val g2 = g as Graphics2D
            g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING,
                RenderingHints.VALUE_ANTIALIAS_ON)
            g2.color = if (active) LINE else INSET
            g2.drawRoundRect(0, 0, width - 1, height - 1, 10, 10)

            val name = client.names[ch] ?: st?.cfg?.name ?: "ch${ch + 1}"
            g2.color = INK
            g2.font = Font(Font.SANS_SERIF, Font.BOLD, 11)
            g2.drawString(name.take(10), 6, 16)

            val role = st?.role ?: Role.INSTRUMENT
            g2.color = when (role) {
                Role.VOCAL -> LIVE; Role.BACKING_VOCAL -> WARN
                Role.FOUNDATION -> ACCENT; else -> MUTED
            }
            g2.font = Font(Font.SANS_SERIF, Font.PLAIN, 9)
            g2.drawString(when (role) {
                Role.FOUNDATION -> "FOUND"; Role.KEYS -> "KEYS"
                Role.PERCUSSION -> "PERC"; Role.RHYTHM_GTR -> "RHYTHM"
                Role.SOLO_GTR -> "SOLO"; Role.COLOR -> "COLOR"
                Role.BACKING_VOCAL -> "BVOX"; Role.VOCAL -> "VOCAL"
                Role.TALK -> "TALK"; else -> "INST"
            }, 6, 28)

            // VU of what the engine hears
            val db = st?.lastLevelDb ?: -128f
            val top = 38; val bot = height - 96
            val h = bot - top
            g2.color = INSET
            g2.fillRoundRect(28, top, 16, h, 4, 4)
            val v = ((db + 60f) / 60f).coerceIn(0f, 1f)
            g2.color = when { db > -6f -> BAD; db > -18f -> WARN; else -> OK }
            val vh = (h * v).toInt()
            g2.fillRoundRect(28, bot - vh, 16, vh, 4, 4)

            // what the autopilot has done to it
            val off = e.offsetDb(ch)
            g2.font = Font(Font.MONOSPACED, Font.BOLD, 13)
            g2.color = when {
                off > 0.2f -> WARN; off < -0.2f -> ACCENT; else -> MUTED
            }
            g2.drawString("%+.1f".format(Locale.ROOT, off), 6, bot + 20)
            g2.color = MUTED
            g2.font = Font(Font.SANS_SERIF, Font.PLAIN, 9)
            g2.drawString("dB adj", 6, bot + 31)

            val d = client.doctor?.state?.get(ch)
            val eq = d?.eqOffset?.maxByOrNull { abs(it) } ?: 0f
            val thr = d?.thrOffset ?: 0f
            if (abs(eq) > 0.2f || abs(thr) > 0.2f) {
                g2.color = OK
                g2.font = Font(Font.MONOSPACED, Font.PLAIN, 9)
                g2.drawString(buildString {
                    if (abs(eq) > 0.2f) append("EQ%+.1f ".format(Locale.ROOT, eq))
                    if (abs(thr) > 0.2f) append("TH%+.1f".format(Locale.ROOT, thr))
                }, 4, bot + 44)
            }

            // the flags the log carries, so the screen tells the same story
            g2.font = Font(Font.SANS_SERIF, Font.PLAIN, 9)
            var y = bot + 57
            fun flag(t: String, c: Color) {
                g2.color = c; g2.drawString(t, 5, y); y += 11
            }
            if (ch == e.leadVocal) flag("LEAD", LIVE)
            if ((st?.featureStart ?: -1.0) >= 0.0) flag("FEATURE", WARN)
            if (st?.isStatic == true) flag("ROOM TONE", MUTED)
            if (st?.idleRamped == true) flag("idle", MUTED)
            if ((st?.duckDb ?: 0f) < -0.2f) flag("ducked", ACCENT)
            if (!active) flag("silent", MUTED)
        }
    }
}
