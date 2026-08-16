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
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
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
import androidx.compose.ui.graphics.drawscope.Stroke
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
 * The console, as a console.
 *
 * Sixteen strips across the screen, each one the same object an
 * engineer already knows how to read: a meter, a fader in a lane with a
 * scale, the number, and the channel's own spectrum along the bottom.
 * Nothing invented, nothing cute — everything on a strip is a real
 * measurement off the desk.
 *
 * What each strip carries, top to bottom:
 *
 *   NAME        the console's own label, and under it what the app has
 *               worked out is actually plugged in — which on a house
 *               desk with inherited labels is a different thing
 *   METER       pre-fader level, twenty frames a second, with a peak
 *               that hangs and falls the way a meter should
 *   FADER LANE  the whole window the app is allowed to work in
 *               (-12 to +6 dB around your level), with a bright tick at
 *               YOUR fader and the app's cap wherever it has put it. The
 *               gap between tick and cap IS what the app has done.
 *   NUMBER      that gap, in dB, big enough to read from a metre away
 *   STATE       HELD / RIDING / YOURS / MUTED
 *   SPECTRUM    what this channel sounds like, from the analyzer
 */

private fun roleTint(role: Role): Color = when (role) {
    Role.VOCAL -> RoleVocal
    Role.BACKING_VOCAL -> RoleBacking
    Role.FOUNDATION -> RoleFoundation
    Role.PERCUSSION -> RolePercussion
    Role.KEYS -> RoleKeys
    Role.RHYTHM_GTR -> RoleRhythm
    Role.SOLO_GTR -> RoleSolo
    Role.COLOR -> RoleColour
    else -> Ink2
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
    // ONE CLOCK FOR EVERY METER ON THE RACK.
    //
    // Levels arrive twenty times a second and are drawn sixty. Both
    // followers live here, outside Compose entirely: reading `tick`
    // inside a Canvas lambda invalidates the drawing and nothing else,
    // so sixteen moving meters cost no recomposition at all.
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
                    .padding(horizontal = 2.dp),
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
        modifier
            .background(if (s.active) Panel2 else Panel, RoundedCornerShape(8.dp))
            .border(1.dp, if (lead) RoleVocal.copy(alpha = 0.55f) else Line,
                RoundedCornerShape(8.dp))
            .clickable { onTap() }
            .padding(horizontal = 5.dp, vertical = 6.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        // ---- the console's label, and what is actually on it
        Text(
            s.name.take(11),
            color = if (s.deskMuted) Muted else Ink,
            fontSize = 13.sp, fontWeight = FontWeight.Bold,
            maxLines = 1, overflow = TextOverflow.Ellipsis,
            textAlign = TextAlign.Center)
        Text(
            if (lead) "LEAD VOCAL"
            else if (s.identLabel.isNotBlank()) s.identLabel.take(12)
            else s.role.name.lowercase().replace('_', ' '),
            color = if (lead) RoleVocal else tint,
            fontSize = 11.sp, maxLines = 1, overflow = TextOverflow.Ellipsis,
            textAlign = TextAlign.Center)

        Spacer(Modifier.height(6.dp))

        // ---- meter + fader lane, the two things that are actually the
        //      console. Everything here is drawn, not composed.
        Canvas(Modifier.fillMaxWidth().weight(1f)) {
            tick                                  // draw-phase subscribe
            drawStrip(this, s, tint, directing,
                level.getOrElse(s.channel) { -128f },
                peak.getOrElse(s.channel) { -128f })
        }

        Spacer(Modifier.height(5.dp))

        // ---- what the app has done to this fader, in dB
        Text(
            if (s.deskMuted) "MUTED"
            else "%+.1f".format(s.offsetDb),
            color = when {
                s.deskMuted -> Bad
                abs(s.offsetDb) < 0.1f -> Ink2
                s.offsetDb > 0 -> Warn
                else -> Accent
            },
            fontSize = 19.sp, fontWeight = FontWeight.Bold,
            fontFamily = FontFamily.Monospace)
        Text(
            when {
                s.deskMuted -> "by you"
                s.frozen -> "LOCKED"
                s.heldByYou -> "HELD"
                s.riding -> "RIDING"
                !directing -> "would"
                else -> "following"
            },
            color = when {
                s.frozen -> Ink
                s.heldByYou -> tint
                s.riding -> Accent
                else -> Muted
            },
            fontSize = 11.sp, fontWeight = FontWeight.Bold,
            maxLines = 1)
        if (notch != null)
            Text(notch, color = Bad, fontSize = 10.sp, maxLines = 1,
                fontFamily = FontFamily.Monospace)

        // ---- and what it sounds like
        Spacer(Modifier.height(4.dp))
        Canvas(Modifier.fillMaxWidth().height(22.dp)) {
            tick
            drawSpectrum(this, Spectra.band.getOrNull(s.channel), tint,
                s.active)
        }
    }
}

/** meter on the left, fader lane on the right — the strip proper */
private fun drawStrip(
    ds: DrawScope, s: AppState.StripUi, tint: Color, directing: Boolean,
    levelDb: Float, peakDb: Float,
) = with(ds) {
    val w = size.width
    val h = size.height
    val meterW = (w * 0.30f).coerceAtMost(18f)
    val laneX = meterW + w * 0.16f
    val laneW = (w * 0.26f).coerceAtMost(16f)

    // ---------------- METER: -60..0 dBFS, with the zones drawn in
    fun yOf(db: Float) = h * (1f - ((db + 60f) / 60f).coerceIn(0f, 1f))
    drawRect(Inset, Offset(0f, 0f), Size(meterW, h))
    val top = yOf(levelDb)
    if (top < h) {
        // one bar, coloured by where its top is: green working, amber
        // hot, red about to clip. The same law the desk's own meter uses.
        val c = when {
            levelDb > -6f -> Bad
            levelDb > -18f -> Warn
            else -> Ok
        }
        drawRect(c.copy(alpha = if (s.active) 0.95f else 0.4f),
            Offset(0f, top), Size(meterW, h - top))
    }
    // the two marks an engineer looks for
    for (mark in intArrayOf(-18, -6)) {
        val y = yOf(mark.toFloat())
        drawLine(Line, Offset(0f, y), Offset(meterW, y), strokeWidth = 1f)
    }
    // peak, hanging
    if (peakDb > -59f) {
        val y = yOf(peakDb)
        drawLine(Ink, Offset(0f, y), Offset(meterW, y), strokeWidth = 2f)
    }

    // ---------------- FADER LANE: the window the app may work in
    val base = s.baselineDb
    val lo = base - LANE_BELOW
    val hi = base + LANE_ABOVE
    fun laneY(db: Float) = h * (1f - ((db - lo) / (hi - lo)).coerceIn(0f, 1f))

    // the lane, and inside it the part the app is actually allowed
    drawRect(Inset, Offset(laneX, 0f), Size(laneW, h))
    drawRect(Line.copy(alpha = 0.5f), Offset(laneX, 0f),
        Size(laneW, h), style = Stroke(width = 1f))

    // scale ticks every 3 dB, longer at 6
    var d = -LANE_BELOW
    while (d <= LANE_ABOVE + 0.01f) {
        val y = laneY(base + d)
        val long = (d.toInt() % 6) == 0
        drawLine(if (long) Muted else Line,
            Offset(laneX + laneW + 2f, y),
            Offset(laneX + laneW + (if (long) 8f else 4f), y),
            strokeWidth = 1f)
        d += 3f
    }

    // YOUR fader: the bright reference the whole strip is measured from
    val byou = laneY(base)
    drawLine(Ink.copy(alpha = 0.75f), Offset(laneX - 4f, byou),
        Offset(laneX + laneW + 4f, byou), strokeWidth = 2f)

    // where the app has it, and the travel between the two
    val now = laneY(base + s.offsetDb)
    if (abs(s.offsetDb) > 0.05f) {
        val c = if (s.offsetDb > 0) Warn else Accent
        drawRect(c.copy(alpha = if (directing) 0.35f else 0.15f),
            Offset(laneX, minOf(byou, now)),
            Size(laneW, abs(now - byou)))
    }

    // the cap. A held channel gets a flat sealed bar — it is never going
    // to move and it should not look like something that might.
    val capH = 13f
    val capC = if (s.deskMuted) Bad else if (s.heldByYou) tint else Ink
    drawRect(capC.copy(alpha = if (directing || s.heldByYou) 1f else 0.5f),
        Offset(laneX - 3f, now - capH / 2), Size(laneW + 6f, capH))
    if (s.heldByYou)
        drawLine(Panel, Offset(laneX - 3f, now), Offset(laneX + laneW + 3f, now),
            strokeWidth = 2f)

    if (s.deskMuted) {
        // muted on the desk: cross the whole strip out
        drawLine(Bad.copy(alpha = 0.5f), Offset(0f, 0f), Offset(w, h),
            strokeWidth = 2f)
    }
}

/** the channel's own spectrum, from the analyzer */
private fun drawSpectrum(
    ds: DrawScope, bands: FloatArray?, tint: Color, active: Boolean,
) = with(ds) {
    drawRect(Inset)
    if (bands == null) return@with
    val n = bands.size
    val bw = size.width / n
    val p = Path()
    p.moveTo(0f, size.height)
    for (i in 0 until n) {
        // the shape is dB below this channel's own peak: -40..0
        val v = ((bands[i] + 40f) / 40f).coerceIn(0f, 1f)
        p.lineTo(i * bw + bw / 2, size.height * (1f - v))
    }
    p.lineTo(size.width, size.height)
    p.close()
    drawPath(p, tint.copy(alpha = if (active) 0.45f else 0.18f))
}
