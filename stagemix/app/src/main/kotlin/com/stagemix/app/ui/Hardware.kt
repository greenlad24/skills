package com.stagemix.app.ui

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * THE FACEPLATE.
 *
 * Everything on this screen is a piece of hardware: raised buttons with
 * a bevel and a lit indicator, wells sunk into the panel, backlit
 * readouts, faders in slots with a scale beside them and light spilling
 * from the cap. The rule that makes it read as a machine rather than as
 * a drawing of one is consistency about where the light comes from —
 * always from above, so a raised thing is lighter along its top edge
 * and a sunk thing is darker along it.
 *
 * The palette is the one this app already had; nothing here is a new
 * colour. Green means live, amber means held, blue means the app moved
 * something down, red means a fault or a mute.
 */

/** the two surface treatments the whole panel is built from */
private val RaisedTop = Color(0xFF232B36)
private val RaisedBottom = Color(0xFF141A22)
private val WellTop = Color(0xFF070A0E)
private val WellBottom = Color(0xFF141A23)

/** a raised control: lighter at the top, shadow underneath */
fun Modifier.raised(corner: Dp = 8.dp, elevation: Dp = 3.dp): Modifier =
    this.shadow(elevation, RoundedCornerShape(corner))
        .background(
            Brush.verticalGradient(listOf(RaisedTop, RaisedBottom)),
            RoundedCornerShape(corner))
        .border(1.dp, Color(0x14FFFFFF), RoundedCornerShape(corner))

/** a well sunk into the panel: dark at the top, a hint of light below */
fun Modifier.well(corner: Dp = 8.dp): Modifier =
    this.background(
        Brush.verticalGradient(listOf(WellTop, WellBottom)),
        RoundedCornerShape(corner))
        .border(1.dp, Color(0x0DFFFFFF), RoundedCornerShape(corner))

/**
 * The panel itself, with the four screws that make it a box rather
 * than a rectangle — and, when the app is not writing to the mixer, a
 * hazard border around the whole thing. On a faceplate that reads
 * exactly the way an interlock does on real equipment.
 */
@Composable
fun Faceplate(warning: Boolean, content: @Composable () -> Unit) {
    Box(
        Modifier.fillMaxSize()
            .background(Brush.verticalGradient(listOf(Color(0xFF161C24), Bg)))
    ) {
        if (warning) Canvas(Modifier.fillMaxSize()) {
            val t = 7f
            var x = -size.height
            while (x < size.width + size.height) {
                drawLine(Warn.copy(alpha = 0.5f),
                    Offset(x, size.height), Offset(x + size.height, 0f),
                    strokeWidth = t)
                x += 30f
            }
            drawRect(Bg, Offset(t, t),
                Size(size.width - 2 * t, size.height - 2 * t))
        }
        Canvas(Modifier.fillMaxSize()) {
            val m = 26f
            for (p in listOf(
                Offset(m, m), Offset(size.width - m, m),
                Offset(m, size.height - m),
                Offset(size.width - m, size.height - m))) {
                drawCircle(Color(0xFF0A0E13), 7f, p)
                drawCircle(Color(0x22FFFFFF), 7f, p.copy(y = p.y - 1f))
                drawCircle(Color(0xFF1A2029), 5f, p)
            }
        }
        Box(Modifier.fillMaxSize().padding(if (warning) 14.dp else 10.dp)) {
            content()
        }
    }
}

/**
 * A backlit readout. Dark glass, lit characters — the same thing every
 * piece of studio hardware puts a number on, and the reason the big
 * figure on this screen can be read from across a room.
 */
@Composable
fun Lcd(
    text: String,
    size: androidx.compose.ui.unit.TextUnit = 15.sp,
    tint: Color = Ok,
    modifier: Modifier = Modifier,
    weight: FontWeight = FontWeight.Bold,
) {
    Box(
        modifier.well(6.dp).padding(horizontal = 10.dp, vertical = 5.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(text, color = tint, fontSize = size, fontWeight = weight,
            fontFamily = FontFamily.Monospace, letterSpacing = 1.sp,
            maxLines = 1)
    }
}

/**
 * A transport key: a raised button with an indicator that lights.
 *
 * The lamp is the point. A lit red key on a piece of hardware means one
 * thing to everybody who has ever seen a recorder, and it is a better
 * answer to "is this thing running?" than any amount of text — which is
 * the question three whole nights were lost to.
 */
@Composable
fun TransportKey(
    label: String,
    lampOn: Boolean,
    lampColour: Color,
    modifier: Modifier = Modifier,
    square: Boolean = false,
    onClick: () -> Unit,
) {
    val glow by animateFloatAsState(
        targetValue = if (lampOn) 1f else 0f,
        animationSpec = Motion.StateChange, label = "lamp")
    Column(
        modifier.raised(9.dp, if (lampOn) 5.dp else 2.dp)
            .clickable { onClick() }
            .padding(horizontal = 10.dp, vertical = 9.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Canvas(Modifier.size(20.dp)) {
            val c = Offset(this.size.width / 2, this.size.height / 2)
            if (glow > 0.02f) drawCircle(
                Brush.radialGradient(
                    listOf(lampColour.copy(alpha = 0.55f * glow),
                        Color.Transparent),
                    center = c, radius = this.size.width * 0.9f),
                radius = this.size.width * 0.9f, center = c)
            val r = this.size.width * 0.30f
            if (square) drawRect(
                lampColour.copy(alpha = 0.25f + 0.75f * glow),
                Offset(c.x - r, c.y - r), Size(r * 2, r * 2))
            else drawCircle(
                lampColour.copy(alpha = 0.25f + 0.75f * glow), r, c)
        }
        Spacer(Modifier.height(5.dp))
        Text(label, color = if (lampOn) Ink else Ink2, fontSize = 11.sp,
            fontWeight = FontWeight.Bold, letterSpacing = 1.sp, maxLines = 1)
    }
}

/** the tab strip: a well with one raised key in it */
@Composable
fun Segmented(
    tabs: List<String>,
    selected: Int,
    modifier: Modifier = Modifier,
    onSelect: (Int) -> Unit,
) {
    Row(
        modifier.well(9.dp).padding(3.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        tabs.forEachIndexed { i, t ->
            val on = i == selected
            Box(
                Modifier
                    .then(if (on) Modifier.raised(7.dp, 2.dp) else Modifier)
                    .clickable { onSelect(i) }
                    .padding(horizontal = 16.dp, vertical = 8.dp),
                contentAlignment = Alignment.Center,
            ) {
                Text(t, color = if (on) Ink else Muted, fontSize = 12.sp,
                    fontWeight = FontWeight.Bold, letterSpacing = 1.5.sp,
                    maxLines = 1)
            }
        }
    }
}

/**
 * The master meter: segmented, the way a meter bridge is, with the
 * scale printed under it.
 *
 * Two rows, and they are the two numbers this whole engine exists to
 * hold in a relationship: the voice carrying the song, and everything
 * else. If LEAD is sitting above BAND, the mix is working.
 */
@Composable
fun MasterMeters(leadDb: Float, bandDb: Float, modifier: Modifier = Modifier) {
    Column(modifier.well(9.dp).padding(horizontal = 12.dp, vertical = 9.dp)) {
        MeterRow("LEAD", leadDb, RoleVocal)
        Spacer(Modifier.height(6.dp))
        MeterRow("BAND", bandDb, Ink2)
        Spacer(Modifier.height(5.dp))
        Row(Modifier.fillMaxWidth().padding(start = 30.dp)) {
            for ((i, m) in listOf("-42", "-32", "-16", "-12", "0")
                    .withIndex()) {
                Text(m, color = Muted, fontSize = 9.sp,
                    fontFamily = FontFamily.Monospace)
                if (i < 4) Spacer(Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun MeterRow(label: String, db: Float, tint: Color) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(label, color = Muted, fontSize = 10.sp,
            fontWeight = FontWeight.Bold, fontFamily = FontFamily.Monospace)
        Spacer(Modifier.width(8.dp))
        Canvas(Modifier.weight(1f).height(13.dp)) {
            val segs = 48
            val gap = 1.6f
            val w = (size.width - gap * (segs - 1)) / segs
            val lit = (((db + 60f) / 60f).coerceIn(0f, 1f) * segs).toInt()
            for (i in 0 until segs) {
                val on = i < lit
                val c = when {
                    !on -> Color(0xFF1A222C)
                    i > segs * 0.90f -> Bad
                    i > segs * 0.78f -> Warn
                    else -> tint
                }
                drawRect(c, Offset(i * (w + gap), 0f), Size(w, size.height))
            }
        }
    }
}

/**
 * A fader in its slot.
 *
 * The slot carries the whole window the app is allowed to work in, the
 * scale is ticked down both sides of it the way it is on a console, and
 * the cap spills light when the app is actually holding that channel
 * somewhere other than where you left it. A sealed cap — a flat bar,
 * no light — is a channel it has promised never to move.
 */
fun androidx.compose.ui.graphics.drawscope.DrawScope.drawFader(
    x: Float, top: Float, bottom: Float, slotW: Float,
    yourY: Float, capY: Float,
    tint: Color, glow: Color?, held: Boolean, dim: Boolean,
) {
    val h = bottom - top
    // ticks either side, every 3 dB over an 18 dB window
    for (i in 0..6) {
        val y = top + h * i / 6f
        val long = i % 2 == 0
        val len = if (long) slotW * 0.85f else slotW * 0.5f
        val c = if (long) Color(0xFF3A4553) else Color(0xFF232C38)
        drawLine(c, Offset(x - slotW / 2 - 3f - len, y),
            Offset(x - slotW / 2 - 3f, y), strokeWidth = 1.5f)
        drawLine(c, Offset(x + slotW / 2 + 3f, y),
            Offset(x + slotW / 2 + 3f + len, y), strokeWidth = 1.5f)
    }
    // the slot
    drawRoundRect(
        Brush.verticalGradient(listOf(WellTop, WellBottom)),
        topLeft = Offset(x - slotW / 2, top),
        size = Size(slotW, h),
        cornerRadius = androidx.compose.ui.geometry.CornerRadius(slotW / 2))
    // where YOU left it
    drawLine(Ink.copy(alpha = 0.55f),
        Offset(x - slotW * 1.15f, yourY), Offset(x + slotW * 1.15f, yourY),
        strokeWidth = 1.5f)
    // the travel between your fader and where the app has it
    if (kotlin.math.abs(capY - yourY) > 1.5f) drawRect(
        tint.copy(alpha = if (dim) 0.18f else 0.42f),
        Offset(x - slotW / 2, minOf(capY, yourY)),
        Size(slotW, kotlin.math.abs(capY - yourY)))
    // the light spilling from the cap
    if (glow != null && !dim) {
        for (s in intArrayOf(-1, 1)) drawCircle(
            Brush.radialGradient(
                listOf(glow.copy(alpha = 0.75f), Color.Transparent),
                center = Offset(x + s * slotW * 0.95f, capY),
                radius = slotW * 1.5f),
            radius = slotW * 1.5f,
            center = Offset(x + s * slotW * 0.95f, capY))
    }
    // the cap
    val capH = if (held) 9f else 22f
    val capW = slotW * 2.3f
    drawRoundRect(
        Brush.verticalGradient(listOf(RaisedTop, RaisedBottom)),
        topLeft = Offset(x - capW / 2, capY - capH / 2),
        size = Size(capW, capH),
        cornerRadius = androidx.compose.ui.geometry.CornerRadius(
            if (held) 3f else capW / 2.4f))
    drawLine(Color(0xFF0A0E13), Offset(x - capW * 0.32f, capY),
        Offset(x + capW * 0.32f, capY), strokeWidth = 2f)
    drawRoundRect(
        Color(if (held) 0x33FFFFFF else 0x22FFFFFF),
        topLeft = Offset(x - capW / 2, capY - capH / 2),
        size = Size(capW, capH),
        cornerRadius = androidx.compose.ui.geometry.CornerRadius(
            if (held) 3f else capW / 2.4f),
        style = androidx.compose.ui.graphics.drawscope.Stroke(1f))
}
