package com.stagemix.app.ui

import android.os.SystemClock
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
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
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlin.math.ceil

/**
 * WHAT THIS APP IS DOING TO YOUR MIXER, RIGHT NOW.
 *
 * The largest object on the screen, and it is also the control. There
 * were two controls for this before — a switch in the header and a
 * button below it labelled "Take over the mains" that did something
 * else entirely — and the state itself was thirteen-point text in a row
 * of nine other things. Three nights in a row the app watched an entire
 * gig without writing a fader, and the screen never said so loudly
 * enough for anybody to notice.
 *
 * So: one thing, one place, one tap. And whenever the app is NOT
 * writing to the mixer, the band is drawn with hazard stripes across
 * it — a texture, not a colour, because texture is what survives a dark
 * room, a red stage wash and a glance from two metres away.
 */
@Composable
fun ModeBand(
    directing: Boolean,
    keeping: Boolean,
    stageMuted: Boolean,
    frozen: Boolean,
    fault: String?,
    channelsMixed: Int,
    channelsTotal: Int,
    onToggle: () -> Unit,
) {
    // Precedence: a failure never hides behind a green banner.
    val word: String
    val sub: String
    val colour: Color
    val striped: Boolean
    when {
        fault != null -> {
            word = "PROBLEM"; sub = fault; colour = Bad; striped = true
        }
        frozen -> {
            word = "FROZEN"
            sub = "every fader is held exactly where it is — tap FREEZE to resume"
            colour = Accent; striped = true
        }
        !directing -> {
            word = "WATCHING ONLY"
            sub = "nothing is being sent to the mixer — tap here to start mixing"
            colour = Warn; striped = true
        }
        stageMuted -> {
            word = "WAITING"
            sub = "you have the band muted — there is no mix to make"
            colour = Warn; striped = true
        }
        keeping -> {
            word = "MIXING"
            sub = "holding the balance you kept · $channelsMixed of " +
                "$channelsTotal channels · monitors untouched"
            colour = Ok; striped = false
        }
        else -> {
            word = "MIXING"
            sub = "finding the balance · $channelsMixed of $channelsTotal " +
                "channels · monitors untouched"
            colour = Ok; striped = false
        }
    }

    val pulse = if (fault != null) {
        val t = rememberInfiniteTransition(label = "alarm")
        t.animateFloat(initialValue = 1f, targetValue = 0.62f,
            animationSpec = Motion.Alarm, label = "alarmAlpha").value
    } else 1f

    Box(
        Modifier
            .fillMaxWidth()
            .height(122.dp)
            .background(colour.copy(alpha = 0.14f * pulse))
            .clickable { onToggle() },
    ) {
        if (striped) Canvas(Modifier.fillMaxSize()) {
            // 45° hazard stripes. The only thing in this app drawn as a
            // texture, and it means exactly one thing: the mixer is not
            // being written to.
            var x = -size.height
            while (x < size.width + size.height) {
                drawLine(colour.copy(alpha = 0.16f),
                    Offset(x, size.height), Offset(x + size.height, 0f),
                    strokeWidth = 10f)
                x += 34f
            }
        }
        Row(
            Modifier.fillMaxSize().padding(horizontal = 22.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Box(Modifier.size(26.dp)
                .background(colour.copy(alpha = pulse), CircleShape))
            Spacer(Modifier.width(18.dp))
            Column(Modifier.weight(1f)) {
                Text(word, color = colour, fontSize = 46.sp,
                    fontWeight = FontWeight.Black, letterSpacing = 3.sp)
                Text(sub, color = Ink, fontSize = 19.sp,
                    fontWeight = FontWeight.Medium)
            }
        }
    }
}

/**
 * ONE SENTENCE: what it is doing, and why.
 *
 * With a dot that flashes on every engine tick beside it, because the
 * hardest question to answer from across a stage is "is this thing
 * alive or has it stopped?" — and a screen where nothing ever moves is
 * indistinguishable from a screen that has frozen. When the mix is
 * settled and nothing needs doing, that is what this says, in words,
 * rather than going quiet.
 */
@Composable
fun NowLine(headline: String, detail: String, tickMs: Long, shadow: Boolean) {
    val now = SystemClock.elapsedRealtime()
    val alive = now - tickMs < 3000
    Row(
        Modifier.fillMaxWidth()
            .background(Panel, RoundedCornerShape(10.dp))
            .padding(horizontal = 14.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(12.dp).background(
            if (alive) Ok.copy(alpha = 0.9f) else Bad, CircleShape))
        Spacer(Modifier.width(12.dp))
        Column {
            Text(
                // In shadow every decision is one the app did NOT make,
                // and saying so on every line is the honest way to fill
                // a screen that would otherwise look like it was working.
                (if (shadow) "WOULD " else "") + headline,
                color = if (shadow) Warn else Ink,
                fontSize = 22.sp, fontWeight = FontWeight.Bold)
            if (detail.isNotBlank())
                Text(detail, color = Ink2, fontSize = 15.sp)
        }
    }
}

/**
 * Something with a deadline, drawn as a deadline.
 *
 * Every long wait in this engine has a known end — twenty seconds of
 * listening, ten minutes of setting channels up, eight seconds of
 * hunting a howl, two minutes of hands off a fader you touched. A bar
 * that fills toward a number of seconds is the difference between "it
 * is thinking" and "it is stuck", and it is why there is not one
 * spinner anywhere in this app.
 */
@Composable
fun PhaseBar(p: Phase) {
    val frac = remember(p.key) { mutableIntStateOf(0) }
    val secs = remember(p.key) { mutableIntStateOf(0) }
    LaunchedEffect(p.key) {
        while (true) {
            kotlinx.coroutines.delay(100)
            val now = SystemClock.elapsedRealtime()
            val span = (p.endsAtMs - p.startedAtMs).coerceAtLeast(1L)
            frac.intValue = (((now - p.startedAtMs) * 1000L) / span)
                .coerceIn(0L, 1000L).toInt()
            secs.intValue = ceil((p.endsAtMs - now) / 1000.0)
                .toInt().coerceAtLeast(0)
        }
    }
    val tone = if (p.alarm) Bad else Accent
    Column(Modifier.fillMaxWidth().padding(top = 8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(p.label, color = tone, fontSize = 17.sp,
                fontWeight = FontWeight.Bold)
            Spacer(Modifier.weight(1f))
            Text("${secs.intValue}s", color = tone, fontSize = 20.sp,
                fontFamily = FontFamily.Monospace,
                fontWeight = FontWeight.Bold)
        }
        Spacer(Modifier.height(4.dp))
        Canvas(Modifier.fillMaxWidth().height(8.dp)) {
            drawRect(Inset)
            drawRect(tone, size = androidx.compose.ui.geometry.Size(
                size.width * (frac.intValue / 1000f), size.height))
        }
        if (p.why.isNotBlank())
            Text(p.why, color = Muted, fontSize = 13.sp)
    }
}

/** the four things worth doing while holding an instrument */
@Composable
fun ActionPads(
    frozen: Boolean,
    onFreeze: () -> Unit,
    onKeep: () -> Unit,
    onUndo: () -> Unit,
    onDetail: () -> Unit,
) {
    Row(Modifier.fillMaxWidth().height(84.dp),
        horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Pad(if (frozen) "▶  RESUME" else "⏸  FREEZE ALL",
            if (frozen) Ok else Bad, Modifier.weight(1f), onFreeze)
        Pad("✓  KEEP THIS MIX", Accent, Modifier.weight(1f), onKeep)
        Pad("↩  UNDO MY MOVES", Ink2, Modifier.weight(1f), onUndo)
        Pad("☰  DETAIL", Ink2, Modifier.weight(1f), onDetail)
    }
}

@Composable
private fun Pad(label: String, colour: Color, modifier: Modifier,
                onClick: () -> Unit) {
    Box(
        modifier
            .fillMaxSize()
            .background(Panel2, RoundedCornerShape(12.dp))
            .clickable { onClick() },
        contentAlignment = Alignment.Center,
    ) {
        Text(label, color = colour, fontSize = 18.sp,
            fontWeight = FontWeight.Bold)
    }
}
