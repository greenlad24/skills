package com.stagemix.app.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.withFrameNanos
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.stagemix.app.AppState
import com.stagemix.engine.Role
import kotlin.math.abs
import kotlin.math.max

/**
 * The rack: sixteen strips, each one a piece of the faceplate.
 *
 * A lit badge for what the channel is, a segmented meter beside a fader
 * in a slot, the number on a small readout, and the channel's own
 * spectrum along the bottom. Everything on a strip is a real
 * measurement off the desk — the only thing invented is the lighting.
 */

private fun roleTint(role: Role): Color = when (role) {
    Role.VOCAL -> RoleVocal
    Role.BACKING_VOCAL -> RoleBacking
    Role.FOUNDATION -> RoleFoundation
    Role.DRUMS -> RolePercussion
    Role.PERCUSSION -> RolePercussion
    Role.KEYS -> RoleKeys
    Role.RHYTHM_GTR -> RoleRhythm
    Role.SOLO_GTR -> RoleSolo
    Role.COLOR -> RoleColour
    else -> Ink2
}

/** one glyph per kind of thing, drawn rather than typed */
private fun roleGlyph(role: Role): String = when (role) {
    Role.VOCAL, Role.BACKING_VOCAL -> "◍"
    Role.FOUNDATION -> "◒"
    Role.DRUMS -> "◎"
    Role.PERCUSSION -> "◎"
    Role.KEYS -> "▤"
    Role.RHYTHM_GTR, Role.SOLO_GTR -> "◫"
    Role.COLOR -> "◈"
    Role.TALK -> "☎"
    else -> "◦"
}

/** the window the app may work in, around the operator's own fader */
private const val LANE_BELOW = 12f
private const val LANE_ABOVE = 6f

@Composable
fun MixerRack(
    strips: List<AppState.StripUi>,
    leadVocal: Int?,
    directing: Boolean,
    notches: Map<Int, String>,
    modifier: Modifier = Modifier,
    onTap: (AppState.StripUi) -> Unit = {},
) {
    // One frame clock for every meter on the rack. Levels arrive twenty
    // times a second and are drawn sixty; both followers live outside
    // Compose, so sixteen moving meters cost no recomposition at all.
    val lvl = remember { FloatArray(Levels.N) { -128f } }
    val peak = remember { FloatArray(Levels.N) { -128f } }
    val tick = remember { mutableIntStateOf(0) }
    LaunchedEffect(Unit) {
        var last = 0L
        while (true) withFrameNanos { now ->
            val dt = if (last == 0L) 0f
                     else ((now - last) / 1e9f).coerceAtMost(0.25f)
            last = now
            for (i in 0 until Levels.N) {
                val raw = Levels.db[i]
                lvl[i] = if (raw > lvl[i]) raw
                    else max(raw, lvl[i] - Motion.METER_FALL_DB_PER_S * dt)
                peak[i] = if (raw > peak[i]) raw
                    else max(raw, peak[i] - Motion.PEAK_FALL_DB_PER_S * dt)
            }
            tick.intValue++
        }
    }

    Row(modifier) {
        for (s in strips) {
            ChannelStrip(
                s = s,
                lead = s.channel == leadVocal,
                directing = directing,
                notch = notches[s.channel],
                level = lvl, peak = peak, tick = tick.intValue,
                modifier = Modifier.weight(1f).fillMaxHeight()
                    .padding(horizontal = 3.dp),
                onTap = { onTap(s) })
        }
    }
}

@Composable
private fun ChannelStrip(
    s: AppState.StripUi,
    lead: Boolean,
    directing: Boolean,
    notch: String?,
    level: FloatArray,
    peak: FloatArray,
    tick: Int,
    modifier: Modifier,
    onTap: () -> Unit,
) {
    val tint = roleTint(s.role)
    Column(
        modifier.clickable { onTap() },
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        // ---- the badge: a lit key with the kind of instrument on it
        Box(
            Modifier.size(38.dp).raised(9.dp, 2.dp)
                .border(1.dp,
                    if (lead) RoleVocal.copy(alpha = 0.7f)
                    else tint.copy(alpha = 0.35f),
                    RoundedCornerShape(9.dp)),
            contentAlignment = Alignment.Center,
        ) {
            Text(roleGlyph(s.role),
                color = if (s.deskMuted) Muted else tint, fontSize = 19.sp)
        }
        Spacer(Modifier.height(5.dp))
        Text(s.name.take(11),
            color = if (s.deskMuted) Muted else Ink,
            fontSize = 12.sp, fontWeight = FontWeight.Bold,
            maxLines = 1, overflow = TextOverflow.Ellipsis,
            textAlign = TextAlign.Center)
        Text(
            if (lead) "LEAD" else if (s.identLabel.isNotBlank())
                s.identLabel.take(12)
            else s.role.name.lowercase().replace('_', ' '),
            color = if (lead) RoleVocal else Muted,
            fontSize = 10.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)

        Spacer(Modifier.height(5.dp))

        // ---- meter and fader, drawn as one piece of hardware
        Canvas(Modifier.fillMaxWidth().weight(1f)) {
            tick                                  // draw-phase subscribe
            drawStrip(this, s, tint, directing,
                level.getOrElse(s.channel) { -128f },
                peak.getOrElse(s.channel) { -128f })
        }

        Spacer(Modifier.height(4.dp))

        // ---- the readout: what the app has done to this fader
        Lcd(
            text = if (s.deskMuted) "MUTE" else "%+.1f".format(s.offsetDb),
            size = 15.sp,
            tint = when {
                s.deskMuted -> Bad
                abs(s.offsetDb) < 0.1f -> Ink2
                s.offsetDb > 0 -> Warn
                else -> Accent
            },
            modifier = Modifier.fillMaxWidth())
        Spacer(Modifier.height(3.dp))
        Text(
            when {
                s.deskMuted -> "BY YOU"
                s.frozen -> "LOCKED"
                s.heldByYou -> "HELD"
                s.riding -> "RIDING"
                !directing -> "WOULD"
                else -> "FOLLOW"
            },
            color = when {
                s.frozen -> Ink
                s.heldByYou -> tint
                s.riding -> Accent
                else -> Muted
            },
            fontSize = 9.sp, fontWeight = FontWeight.Bold,
            letterSpacing = 1.sp, maxLines = 1)
        // The notch line is reserved on every strip whether or not there
        // is a notch to show. A rack reads as one instrument because its
        // rows line up; letting one strip grow a row taller pushes its
        // readout, its state word and its spectrum out of line with the
        // fifteen beside it, and a rack that does not line up looks
        // broken rather than busy.
        // 14 dp, not 12: a 9 sp line box is taller than 12 dp once the
        // reader's font scale is anything but the smallest, and the
        // first version of this row sliced the frequency in half — the
        // one number on the strip that says WHY a channel has been cut.
        // The line height is pinned too, so the row cannot be resized
        // out from under the text by a system font setting.
        Box(Modifier.height(14.dp), contentAlignment = Alignment.Center) {
            if (notch != null)
                Text(notch, color = Bad, fontSize = 9.sp, maxLines = 1,
                    lineHeight = 10.sp,
                    fontFamily = FontFamily.Monospace)
        }

        // ---- and what it sounds like
        Spacer(Modifier.height(4.dp))
        Box(Modifier.fillMaxWidth().height(16.dp).well(5.dp)) {
            Canvas(Modifier.fillMaxWidth().fillMaxHeight()) {
                tick
                drawSpectrum(this, Spectra.band.getOrNull(s.channel), tint,
                    s.active)
            }
        }
    }
}

/** segmented meter on the left, fader in its slot on the right */
private fun drawStrip(
    ds: DrawScope, s: AppState.StripUi, tint: Color, directing: Boolean,
    levelDb: Float, peakDb: Float,
) = with(ds) {
    val w = size.width
    val h = size.height
    val meterW = (w * 0.26f).coerceIn(9f, 16f)
    val slotW = (w * 0.17f).coerceIn(7f, 11f)
    val faderX = meterW + (w - meterW) * 0.52f

    // ---------------- METER: segmented, -60..0 dBFS
    fun yOf(db: Float) = h * (1f - ((db + 60f) / 60f).coerceIn(0f, 1f))
    val segs = 26
    val segH = h / segs
    val lit = (((levelDb + 60f) / 60f).coerceIn(0f, 1f) * segs).toInt()
    for (i in 0 until segs) {
        val y = h - (i + 1) * segH
        val on = i < lit
        val c = when {
            !on -> Color(0xFF141B23)
            i > segs * 0.90f -> Bad
            i > segs * 0.70f -> Warn
            else -> Ok
        }
        drawRect(c.copy(alpha = if (on && !s.active) 0.45f else 1f),
            Offset(0f, y + 1f), Size(meterW, segH - 2f))
    }
    if (peakDb > -59f) {
        val y = yOf(peakDb)
        drawLine(Ink, Offset(0f, y), Offset(meterW, y), strokeWidth = 2f)
    }

    // ---------------- FADER: the window the app may work in
    val base = s.baselineDb
    val lo = base - LANE_BELOW
    val hi = base + LANE_ABOVE
    fun laneY(db: Float) =
        h * (1f - ((db - lo) / (hi - lo)).coerceIn(0f, 1f))

    val travelTint = if (s.offsetDb > 0) Warn else Accent
    drawFader(
        x = faderX, top = 6f, bottom = h - 6f, slotW = slotW,
        yourY = laneY(base).coerceIn(6f, h - 6f),
        capY = laneY(base + s.offsetDb).coerceIn(6f, h - 6f),
        tint = travelTint,
        glow = when {
            s.deskMuted -> null
            s.heldByYou -> null
            s.riding -> Accent
            directing -> Ok
            else -> null
        },
        held = s.heldByYou,
        dim = !directing || s.deskMuted)

    if (s.deskMuted) drawLine(Bad.copy(alpha = 0.45f),
        Offset(0f, 0f), Offset(w, h), strokeWidth = 2f)
}

/** the channel's own spectrum, from the analyzer */
private fun drawSpectrum(
    ds: DrawScope, bands: FloatArray?, tint: Color, active: Boolean,
) = with(ds) {
    if (bands == null) return@with
    val n = bands.size
    val bw = size.width / n
    val p = Path()
    p.moveTo(0f, size.height)
    for (i in 0 until n) {
        val v = ((bands[i] + 40f) / 40f).coerceIn(0f, 1f)
        p.lineTo(i * bw + bw / 2, size.height * (1f - v))
    }
    p.lineTo(size.width, size.height)
    p.close()
    drawPath(p, tint.copy(alpha = if (active) 0.5f else 0.2f))
}
