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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.withFrameNanos
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.stagemix.app.AppState
import com.stagemix.app.clampFinite
import com.stagemix.app.finite
import kotlin.math.abs
import kotlin.math.max

/**
 * A wedge, as a mixer.
 *
 * "Monitors UI should also be a mixer."
 *
 * It should, and the reason is not consistency — it is that a monitor
 * mix IS a mix. Sixteen sends with a balance between them, exactly like
 * the mains, and an engineer already knows how to read that: strips,
 * faders, meters, one number each. The paragraph this replaces could
 * say the singer's wedge was four dB out; it could not show you WHICH
 * four channels were carrying it, which one the app had touched, or how
 * far any of them sat from where that position wants them.
 *
 * One wedge at a time, chosen by name — the whole stage's ninety-six
 * sends at once is a spreadsheet, not a console. Each strip carries the
 * channel's live meter (the same source that feeds the wedge), the send
 * level as the desk has it, a ghost mark at what this position wants,
 * and the keeper's own travel picked out in colour.
 */

/** the window a monitor send is drawn in */
private const val MON_TOP_DB = 0f
private const val MON_BOTTOM_DB = -50f

@Composable
fun MonitorRack(
    wedges: List<AppState.WedgeUi>,
    names: Map<Int, String>,
    keeping: Boolean,
    modifier: Modifier = Modifier,
) {
    if (wedges.isEmpty()) {
        Column(modifier.well(10.dp).padding(16.dp)) {
            Text("MONITORS", color = Muted, fontSize = 11.sp,
                fontWeight = FontWeight.Bold, letterSpacing = 2.sp)
            Spacer(Modifier.height(10.dp))
            Text("Nothing read yet. All six buses are read off the desk " +
                "when the app takes the mains.",
                color = Ink2, fontSize = 15.sp)
        }
        return
    }

    var sel by remember(wedges.size) { mutableStateOf(0) }
    val w = wedges.getOrElse(sel) { wedges[0] }

    // one frame clock for every meter on this rack, as on the mains
    val lvl = remember { FloatArray(Levels.N) { -128f } }
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
            }
            tick.intValue++
        }
    }

    Column(modifier) {
        // ---- which wedge
        Row(verticalAlignment = Alignment.CenterVertically) {
            Segmented(wedges.map { it.name.take(11) }, sel) { sel = it }
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                Text(w.kind.lowercase().replace('_', ' '),
                    color = Accent, fontSize = 14.sp,
                    fontWeight = FontWeight.Bold)
                Text(
                    if (keeping)
                        "kept slightly · cuts first · never against your hand"
                    else "read only — monitor keeping is off in SETUP",
                    color = Muted, fontSize = 12.sp)
            }
            // IN-EARS / WEDGE — the drummer swaps between the two, and each
            // wants a different mix. Sealed ears want the whole kit on top;
            // a floor wedge wants the band in front of it, vocals on top.
            InEarsToggle(w)
        }
        Spacer(Modifier.height(10.dp))

        Row(Modifier.fillMaxWidth().weight(1f)) {
            for (ch in 0 until AppState.MIXER_CHANNELS) {
                MonStrip(
                    ch = ch,
                    name = names[ch] ?: "ch%02d".format(ch + 1),
                    sendDb = w.sendDb[ch],
                    wantDb = w.targetDb[ch],
                    appDb = w.appDb[ch] ?: 0f,
                    level = lvl, tick = tick.intValue,
                    modifier = Modifier.weight(1f).fillMaxHeight()
                        .padding(horizontal = 3.dp))
            }
        }
    }
}

/**
 * IN-EARS or a FLOOR WEDGE, per monitor. One tap flips it; the mix the
 * keeper aims for follows (see MonitorMap.wants). Works with or without a
 * live service — it updates the state directly and lets the service, when
 * there is one, make it authoritative and persist it.
 */
@Composable
private fun InEarsToggle(w: AppState.WedgeUi) {
    val ctx = androidx.compose.ui.platform.LocalContext.current
    fun set(inEars: Boolean) {
        if (inEars == w.inEars) return
        // update the state now, so it shows immediately in demo and live
        AppState.monitorInEars.value =
            AppState.monitorInEars.value + (w.bus to inEars)
        AppState.wedges.value = AppState.wedges.value.map {
            if (it.bus == w.bus) it.copy(inEars = inEars) else it }
        // and tell the service (a no-op in the demo, authoritative live)
        com.stagemix.app.MixerService.cmd(ctx,
            com.stagemix.app.MixerService.ACTION_MONITOR_INEARS,
            "bus" to w.bus, "inEars" to inEars)
    }
    Row(verticalAlignment = Alignment.CenterVertically) {
        InEarPill("IN-EARS", w.inEars) { set(true) }
        Spacer(Modifier.width(6.dp))
        InEarPill("WEDGE", !w.inEars) { set(false) }
    }
}

@Composable
private fun InEarPill(label: String, on: Boolean, onTap: () -> Unit) {
    Box(
        Modifier
            .clip(RoundedCornerShape(8.dp))
            .background(if (on) Accent.copy(alpha = 0.18f) else Color(0x14FFFFFF))
            .border(1.dp, if (on) Accent else Color(0x22FFFFFF),
                RoundedCornerShape(8.dp))
            .clickable { onTap() }
            .padding(horizontal = 12.dp, vertical = 7.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(label, color = if (on) Accent else Muted, fontSize = 12.sp,
            fontWeight = FontWeight.Bold, letterSpacing = 0.5.sp, maxLines = 1)
    }
}

@Composable
private fun MonStrip(
    ch: Int,
    name: String,
    sendDb: Float?,
    wantDb: Float?,
    appDb: Float,
    level: FloatArray,
    tick: Int,
    modifier: Modifier,
) {
    // A send below the floor is OFF, not quiet — the engineer chose not
    // to route it. It is drawn as a dark strip rather than a fader at
    // the bottom, because those are different facts.
    val off = sendDb == null || sendDb <= -60f
    val tint = when {
        off -> Muted
        appDb > 0.05f -> Warn
        appDb < -0.05f -> Accent
        else -> Ok
    }
    Column(modifier, horizontalAlignment = Alignment.CenterHorizontally) {
        Box(
            Modifier.size(30.dp).raised(8.dp, 2.dp)
                .border(1.dp, tint.copy(alpha = if (off) 0.15f else 0.4f),
                    RoundedCornerShape(8.dp)),
            contentAlignment = Alignment.Center,
        ) {
            Text("%02d".format(ch + 1),
                color = if (off) Muted else Ink2, fontSize = 12.sp,
                fontWeight = FontWeight.Bold)
        }
        Spacer(Modifier.height(4.dp))
        Text(name.take(10), color = if (off) Muted else Ink,
            fontSize = 11.sp, fontWeight = FontWeight.Bold,
            maxLines = 1, overflow = TextOverflow.Ellipsis,
            textAlign = TextAlign.Center)
        Spacer(Modifier.height(6.dp))

        Canvas(Modifier.fillMaxWidth().weight(1f)) {
            tick
            drawMonStrip(this, level.getOrElse(ch) { -128f },
                sendDb, wantDb, appDb, tint, off)
        }

        Spacer(Modifier.height(5.dp))
        Lcd(
            text = if (off) "OFF" else "%+.0f".format(sendDb),
            size = 14.sp, tint = if (off) Muted else Ink2,
            modifier = Modifier.fillMaxWidth())
        Spacer(Modifier.height(3.dp))
        Text(
            when {
                off -> "NOT SENT"
                abs(appDb) < 0.05f -> "AS YOU SET"
                else -> "%+.1f".format(appDb)
            },
            color = if (abs(appDb) < 0.05f) Muted else tint,
            fontSize = 9.sp, fontWeight = FontWeight.Bold,
            letterSpacing = 0.5.sp, maxLines = 1)
        Box(Modifier.height(14.dp), contentAlignment = Alignment.Center) {
            if (!off && wantDb != null && abs(sendDb!! - wantDb) > 2.5f)
                Text("%+.0f".format(wantDb - sendDb), color = Warn,
                    fontSize = 9.sp, maxLines = 1)
        }
    }
}

/**
 * The send, in its window: the channel's own meter on the left, the
 * send fader on the right, and a ghost tick where this position wants
 * it. The gap between the cap and the ghost is the disagreement — the
 * same reading as the mains rack, so it needs learning once.
 */
private fun drawMonStrip(
    ds: androidx.compose.ui.graphics.drawscope.DrawScope,
    levelDb: Float, sendDb: Float?, wantDb: Float?, appDb: Float,
    tint: Color, off: Boolean,
) = with(ds) {
    val w = size.width
    val h = size.height
    val meterW = (w * 0.24f).coerceIn(8f, 14f)
    val slotW = (w * 0.17f).coerceIn(7f, 11f)
    val faderX = meterW + (w - meterW) * 0.52f

    // the source feeding this wedge
    // Sanitize every dB before it becomes a Canvas coordinate: a NaN from
    // a real desk send crashes Skia natively, and coerceIn won't stop it.
    val levelDb = levelDb.finite(-128f)
    val segs = 22
    val segH = h / segs
    val lit = (((levelDb + 60f) / 60f).clampFinite(0f, 1f) * segs).toInt()
    for (i in 0 until segs) {
        val y = h - (i + 1) * segH
        val on = i < lit
        val c = when {
            !on -> Color(0xFF141B23)
            i > segs * 0.90f -> Bad
            i > segs * 0.70f -> Warn
            else -> Ok
        }
        drawRect(c.copy(alpha = if (on && off) 0.3f else 1f),
            Offset(0f, y + 1f), Size(meterW, segH - 2f))
    }

    if (off) {
        drawRect(Color(0x14FFFFFF), Offset(faderX - slotW, 6f),
            Size(slotW * 2f, h - 12f))
        return@with
    }

    val appDb = appDb.finite(0f)
    fun yOf(db: Float) = h * (1f -
        ((db - MON_BOTTOM_DB) / (MON_TOP_DB - MON_BOTTOM_DB))
            .clampFinite(0f, 1f))

    // where the engineer had it, before the keeper moved anything
    val send = sendDb!!.finite(MON_BOTTOM_DB)
    val yours = yOf(send - appDb)
    drawFader(
        x = faderX, top = 6f, bottom = h - 6f, slotW = slotW,
        yourY = yours.clampFinite(6f, h - 6f),
        capY = yOf(send).clampFinite(6f, h - 6f),
        tint = tint,
        glow = if (abs(appDb) > 0.05f) tint else null,
        held = false, dim = false)

    // a ghost where this position wants it
    if (wantDb != null) {
        val y = yOf(wantDb.finite(MON_BOTTOM_DB)).clampFinite(2f, h - 2f)
        drawLine(Warn.copy(alpha = 0.55f),
            Offset(faderX - slotW * 1.6f, y),
            Offset(faderX + slotW * 1.6f, y), strokeWidth = 2f)
    }
}
