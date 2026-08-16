package com.stagemix.app.ui

import android.os.SystemClock
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlin.math.ceil

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
        Modifier.fillMaxWidth().well(8.dp)
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
