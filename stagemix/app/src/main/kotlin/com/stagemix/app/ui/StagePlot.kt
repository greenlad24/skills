package com.stagemix.app.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.withFrameNanos
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import com.stagemix.app.AppState
import com.stagemix.engine.Role
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

/**
 * The band, drawn where they stand.
 *
 * "Maybe a visual representation of the stage."
 *
 * A list of sixteen channel strips answers "what is channel 11 doing".
 * A musician glancing at a tablet between songs is asking a different
 * question — what is this thing doing to US — and the answer to that is
 * a picture. Each player is a puck in the position they actually
 * occupy, so it is read by spatial memory rather than by reading
 * sixteen labels: the drums are at the back, the singers are at the
 * front, the wedges point at the people they feed.
 *
 * What a puck says, and this is the whole design:
 *
 *   FILL      how loud that source is right now (a real meter, twenty
 *             frames a second, with a proper fall time)
 *   RING      whether the app may move this fader at all. A CLOSED ring
 *             is a channel the app has promised never to touch — the
 *             voices, the kick, the snare, the bass. An OPEN arc is a
 *             channel it is riding, and the arc's length is how far it
 *             has moved it from where you left it.
 *   COLOUR    what the app thinks the instrument is
 *   HATCH     you have it muted on the desk
 *
 * That "closed ring versus open arc" is a difference of SHAPE, not of
 * colour, which is what makes it survive a dark room, a red stage wash,
 * a colour-blind operator and a two-second glance. Ten of the sixteen
 * channels on this rig are held, so ten pucks are visibly sealed and
 * six are visibly live: the app's central promise, drawn.
 */

/** where each channel stands, in fractions of the stage rectangle */
private data class Spot(val x: Float, val y: Float, val big: Boolean = false)

/**
 * The rig, from the back of the stage to the front. Hand-placed rather
 * than derived, because a stage is a physical fact and this one does
 * not change: "the first and second channels will always be kick and
 * snare mics", the basses are fixed, the three singers are across the
 * front.
 */
private val SPOTS = mapOf(
    0 to Spot(0.50f, 0.16f, big = true),    // kick, back centre
    1 to Spot(0.62f, 0.16f, big = true),    // snare
    2 to Spot(0.38f, 0.13f),                // overheads
    12 to Spot(0.74f, 0.20f),               // congas
    3 to Spot(0.14f, 0.34f),                // bass mic
    11 to Spot(0.10f, 0.50f, big = true),   // bass DI
    13 to Spot(0.18f, 0.64f),               // DI 2
    4 to Spot(0.86f, 0.36f, big = true),    // guitar amp
    7 to Spot(0.90f, 0.54f),                // guitar DI
    5 to Spot(0.66f, 0.44f),                // piano L
    6 to Spot(0.76f, 0.44f),                // piano R
    8 to Spot(0.50f, 0.76f, big = true),    // lead vocal, front centre
    9 to Spot(0.32f, 0.72f),                // vocal at the piano
    10 to Spot(0.68f, 0.76f),               // third voice
    14 to Spot(0.84f, 0.80f),               // sax
    15 to Spot(0.20f, 0.84f),               // harmonica
)

private fun roleColour(role: Role): Color = when (role) {
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

/** -60..0 dBFS across the puck */
private fun levelFrac(db: Float): Float =
    ((db + 60f) / 60f).coerceIn(0f, 1f)

@Composable
fun StagePlot(
    strips: List<AppState.StripUi>,
    leadVocal: Int?,
    directing: Boolean,
    modifier: Modifier = Modifier,
    onTap: (Int) -> Unit = {},
) {
    // The meter clock. Sixteen envelope followers, advanced once per
    // frame in the DRAW phase — reading `tick` inside the Canvas lambda
    // invalidates the drawing and nothing else, so none of this touches
    // composition or layout. It stops dead when the app is not mixing
    // and there is nothing to watch.
    val shown = remember { FloatArray(Levels.N) { -128f } }
    val tick = remember { mutableIntStateOf(0) }
    LaunchedEffect(Unit) {
        var last = 0L
        while (true) withFrameNanos { now ->
            val dt = if (last == 0L) 0f else ((now - last) / 1e9f).coerceAtMost(0.2f)
            last = now
            for (i in 0 until Levels.N) {
                val raw = Levels.db[i]
                shown[i] = if (raw > shown[i]) raw
                    else max(raw, shown[i] - Motion.METER_FALL_DB_PER_S * dt)
            }
            tick.intValue++
        }
    }

    val byCh = remember(strips) { strips.associateBy { it.channel } }
    Box(modifier) {
        Canvas(
            Modifier
                .fillMaxSize()
                .pointerInput(strips.size) {
                    detectTapGestures { p ->
                        val hit = SPOTS.entries.minByOrNull { (_, s) ->
                            val dx = p.x - s.x * size.width
                            val dy = p.y - s.y * size.height
                            dx * dx + dy * dy
                        }
                        hit?.let { onTap(it.key) }
                    }
                }
        ) {
            tick.intValue          // subscribe: draw-phase only
            drawStage(this, byCh, shown, leadVocal, directing)
        }
    }
}

private fun drawStage(
    ds: DrawScope,
    byCh: Map<Int, AppState.StripUi>,
    level: FloatArray,
    leadVocal: Int?,
    directing: Boolean,
) = with(ds) {
    val w = size.width
    val h = size.height
    // the floor, and the line the audience is on
    drawRect(StageFloor)
    drawLine(StageLine, Offset(0f, h - 2f), Offset(w, h - 2f), strokeWidth = 2f)

    val unit = min(w, h)
    for ((ch, spot) in SPOTS) {
        val s = byCh[ch] ?: continue
        val cx = spot.x * w
        val cy = spot.y * h
        val r = unit * (if (spot.big) 0.062f else 0.052f)
        val col = roleColour(s.role)

        // 1. THE FILL — how loud this source is, right now.
        val f = levelFrac(level.getOrElse(ch) { -128f })
        val body = Rect(cx - r, cy - r, cx + r, cy + r)
        drawRoundRectCompat(this, body, Inset)
        if (f > 0.01f) {
            val fh = 2 * r * f
            drawRoundRectCompat(this,
                Rect(cx - r, cy + r - fh, cx + r, cy + r),
                col.copy(alpha = if (s.active) 0.85f else 0.30f))
        }

        // 2. THE RING — may the app move this fader, and has it?
        val ringR = r * 1.42f
        if (s.heldByYou) {
            // a closed ring: this one is promised, and never moves
            drawCircle(col.copy(alpha = 0.85f), ringR, Offset(cx, cy),
                style = Stroke(width = unit * 0.006f))
        } else {
            // an open arc from the top: how far it has been moved, and
            // which way. Hollow while the app is only watching, because
            // in shadow this is what it WOULD have done.
            drawCircle(Line, ringR, Offset(cx, cy),
                style = Stroke(width = unit * 0.004f))
            val off = s.offsetDb
            if (abs(off) > 0.15f) {
                val span = (off / (if (off > 0) 6f else 12f))
                    .coerceIn(-1f, 1f) * 150f
                drawArc(
                    color = if (off > 0) Warn else Accent,
                    startAngle = -90f,
                    sweepAngle = span,
                    useCenter = false,
                    topLeft = Offset(cx - ringR, cy - ringR),
                    size = Size(ringR * 2, ringR * 2),
                    style = Stroke(width = unit * (if (directing) 0.010f else 0.005f)),
                    alpha = if (directing) 1f else 0.55f,
                )
            }
        }

        // 3. THE LEAD VOCAL wears a crown.
        if (ch == leadVocal) {
            drawArc(
                color = RoleVocal, startAngle = -150f, sweepAngle = 120f,
                useCenter = false,
                topLeft = Offset(cx - ringR * 1.25f, cy - ringR * 1.25f),
                size = Size(ringR * 2.5f, ringR * 2.5f),
                style = Stroke(width = unit * 0.008f))
        }

        // 4. YOU HAVE IT MUTED. Outranks everything: the meters are
        //    pre-mute, so a muted channel looks exactly like a playing
        //    one right up until nobody can hear it.
        if (s.deskMuted) {
            val p = Path()
            var x = -2 * r
            while (x < 2 * r) {
                p.moveTo(cx + x, cy + r)
                p.lineTo(cx + x + 2 * r, cy - r)
                x += r * 0.42f
            }
            clipRect(cx - r, cy - r, cx + r, cy + r) {
                drawPath(p, Bad.copy(alpha = 0.65f),
                    style = Stroke(width = unit * 0.004f))
            }
        }

        // 5. FROZEN by a hand: a dashed collar, drawn as four ticks.
        if (s.frozen) for (a in 0 until 4) {
            val ang = Math.toRadians((a * 90 + 45).toDouble())
            val ox = (Math.cos(ang) * ringR * 1.18f).toFloat()
            val oy = (Math.sin(ang) * ringR * 1.18f).toFloat()
            drawCircle(Ink, unit * 0.006f, Offset(cx + ox, cy + oy))
        }
    }
}

/** rounded rect without pulling in a shape API for two calls */
private fun drawRoundRectCompat(ds: DrawScope, r: Rect, c: Color) = with(ds) {
    drawRect(c, topLeft = Offset(r.left, r.top),
        size = Size(r.width, r.height))
}

/** DrawScope.clipRect with a lambda, spelled out for older compilers */
private inline fun DrawScope.clipRect(
    l: Float, t: Float, rr: Float, b: Float, block: DrawScope.() -> Unit,
) {
    drawContext.canvas.save()
    drawContext.canvas.clipRect(l, t, rr, b)
    block()
    drawContext.canvas.restore()
}
