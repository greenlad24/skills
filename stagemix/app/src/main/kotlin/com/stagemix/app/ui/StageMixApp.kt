package com.stagemix.app.ui

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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.stagemix.app.AppState
import com.stagemix.app.MixerService
import com.stagemix.engine.ChannelConfig
import com.stagemix.engine.Role

@Composable
fun StageMixApp() {
    StageMixTheme {
        val ctx = LocalContext.current
        val conn by AppState.conn.collectAsState()
        // Fully automatic: on launch, find the mixer on this network
        // (the M18's own AP — offline, no internet needed) and connect.
        androidx.compose.runtime.LaunchedEffect(Unit) {
            if (AppState.conn.value == AppState.Conn.DISCONNECTED)
                MixerService.cmd(ctx, MixerService.ACTION_CONNECT,
                    "ip" to AppState.config.value.mixerIp)
        }
        Surface(Modifier.fillMaxSize(), color = Bg) {
            when (conn) {
                AppState.Conn.CONNECTED -> ConsoleScreen()
                else -> ConnectScreen()
            }
        }
    }
}

// ---------------------------------------------------------------- connect
@Composable
fun ConnectScreen() {
    val ctx = LocalContext.current
    val cfg by AppState.config.collectAsState()
    val conn by AppState.conn.collectAsState()
    val err by AppState.lastError.collectAsState()
    var ip by remember { mutableStateOf(cfg.mixerIp) }

    Column(
        Modifier.fillMaxSize().padding(48.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text("STAGEMIX AI", color = Ink, fontSize = 34.sp,
            fontWeight = FontWeight.Black, letterSpacing = 4.sp)
        Text("the on-stage mix engineer for your M18",
            color = Ink2, fontSize = 14.sp)
        Spacer(Modifier.height(28.dp))
        Text(
            "Join the same Wi-Fi / network as the mixer, then enter the " +
            "console's IP address (M AIR / Mixing Station show it in " +
            "their connection screens).",
            color = Ink2, fontSize = 13.sp,
        )
        Spacer(Modifier.height(16.dp))
        Button(
            enabled = conn != AppState.Conn.CONNECTING,
            onClick = {
                AppState.config.value = cfg.copy(mixerIp = "")
                AppState.save(ctx)
                MixerService.cmd(ctx, MixerService.ACTION_CONNECT, "ip" to "")
            },
        ) {
            Text(if (conn == AppState.Conn.CONNECTING) "Searching…"
                 else "🔍 Find my mixer (automatic)")
        }
        Spacer(Modifier.height(12.dp))
        Text("or connect by IP:", color = Muted, fontSize = 12.sp)
        Spacer(Modifier.height(6.dp))
        OutlinedTextField(
            value = ip, onValueChange = { ip = it },
            label = { Text("Mixer IP — e.g. 192.168.1.1") },
            singleLine = true,
        )
        Spacer(Modifier.height(10.dp))
        OutlinedButton(
            enabled = conn != AppState.Conn.CONNECTING && ip.isNotBlank(),
            onClick = {
                AppState.config.value = cfg.copy(mixerIp = ip)
                AppState.save(ctx)
                MixerService.cmd(ctx, MixerService.ACTION_CONNECT, "ip" to ip)
            },
        ) { Text("Connect to this IP") }
        err?.let {
            Spacer(Modifier.height(14.dp))
            Text(it, color = Bad, fontSize = 13.sp)
        }
        Spacer(Modifier.height(30.dp))
        Checklist()
    }
}

@Composable
fun Checklist() {
    Column(
        Modifier.fillMaxWidth(0.72f)
            .background(Panel, RoundedCornerShape(12.dp))
            .border(1.dp, Line, RoundedCornerShape(12.dp))
            .padding(18.dp)
    ) {
        Text("SHOW-NIGHT CHECKLIST", color = Muted, fontSize = 11.sp,
            letterSpacing = 2.sp)
        Spacer(Modifier.height(8.dp))
        for (item in listOf(
            "Tablet plugged into power (screen stays on while mixing)",
            "Battery optimization OFF for StageMix (Settings → Apps)",
            "Samsung: remove StageMix from “Sleeping apps”",
            "Wedges rung out at soundcheck — keep the usual 6 dB margin",
            "Take the soundcheck snapshot BEFORE flipping DIRECTING on",
        )) {
            Row(Modifier.padding(vertical = 3.dp)) {
                Text("•  ", color = Accent)
                Text(item, color = Ink2, fontSize = 13.sp)
            }
        }
    }
}

// ---------------------------------------------------------------- console
@Composable
fun ConsoleScreen() {
    val ctx = LocalContext.current
    val mixer by AppState.mixer.collectAsState()
    val strips by AppState.strips.collectAsState()
    val decisions by AppState.decisions.collectAsState()
    val hold by AppState.holdReason.collectAsState()
    val snap by AppState.snapshotTaken.collectAsState()
    val directing by AppState.directing.collectAsState()
    val doctorOn by AppState.doctorOn.collectAsState()
    val frozenAll by AppState.frozenAll.collectAsState()

    Column(Modifier.fillMaxSize().padding(14.dp)) {
        // ---- header bar
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("STAGEMIX", color = Ink, fontWeight = FontWeight.Black,
                fontSize = 18.sp, letterSpacing = 2.sp)
            Spacer(Modifier.width(10.dp))
            Text("${mixer.model} ${mixer.firmware} @ ${mixer.ip}",
                color = Muted, fontSize = 12.sp)
            Spacer(Modifier.weight(1f))
            hold?.let {
                Text(it.uppercase(), color = Warn, fontSize = 12.sp,
                    fontWeight = FontWeight.Bold)
                Spacer(Modifier.width(14.dp))
            }
            Text("DOCTOR", color = if (doctorOn) Ok else Muted,
                fontWeight = FontWeight.Bold, fontSize = 12.sp)
            Spacer(Modifier.width(4.dp))
            Switch(checked = doctorOn, onCheckedChange = {
                MixerService.cmd(ctx, MixerService.ACTION_DOCTOR, "on" to it)
            })
            Spacer(Modifier.width(14.dp))
            Text(if (directing) "MIXING — AUTO" else "PAUSED",
                color = if (directing) Live else Muted,
                fontWeight = FontWeight.Bold, fontSize = 13.sp)
            Spacer(Modifier.width(8.dp))
            Switch(checked = directing, onCheckedChange = {
                MixerService.cmd(ctx, MixerService.ACTION_DIRECTING, "on" to it)
            })
        }
        Spacer(Modifier.height(10.dp))

        // ---- transport row
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Button(
                onClick = { MixerService.cmd(ctx, MixerService.ACTION_SNAPSHOT) },
                colors = ButtonDefaults.buttonColors(
                    containerColor = if (snap) Panel2 else Accent),
            ) { Text(if (snap) "Re-baseline (bounds = now)" else "Take over the mains",
                     color = if (snap) Ink else Bg) }
            OutlinedButton(onClick = {
                MixerService.cmd(ctx, MixerService.ACTION_REVERT)
            }) { Text("Hand back the mains") }
            Button(
                onClick = {
                    MixerService.cmd(ctx, MixerService.ACTION_FREEZE_ALL,
                        "on" to !frozenAll)
                },
                colors = ButtonDefaults.buttonColors(
                    containerColor = if (frozenAll) Ok else Bad),
            ) { Text(if (frozenAll) "▶ Resume" else "⏸ FREEZE ALL", color = Bg) }
        }
        Spacer(Modifier.height(12.dp))

        Row(Modifier.weight(1f)) {
            // ---- strips
            LazyRow(
                Modifier.weight(2.2f).fillMaxHeight(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                items(strips, key = { it.channel }) { s -> Strip(s) }
            }
            Spacer(Modifier.width(12.dp))
            // ---- decision feed
            Column(
                Modifier.weight(1f).fillMaxHeight()
                    .background(Panel, RoundedCornerShape(12.dp))
                    .border(1.dp, Line, RoundedCornerShape(12.dp))
                    .padding(12.dp)
            ) {
                Text("ENGINE LOG", color = Muted, fontSize = 11.sp,
                    letterSpacing = 2.sp)
                Spacer(Modifier.height(6.dp))
                if (decisions.isEmpty())
                    Text("Waiting. Take the soundcheck snapshot, then flip " +
                        "MIXING on — every move lands here with its reason.",
                        color = Ink2, fontSize = 13.sp)
                LazyColumn {
                    items(decisions) { d ->
                        Column(Modifier.padding(vertical = 4.dp)) {
                            Text(
                                "${d.kind.uppercase()}  " +
                                (if (d.deltaDb != 0f)
                                    "%+.1f dB".format(d.deltaDb) else ""),
                                color = when (d.kind) {
                                    "duck" -> Warn; "freeze" -> Bad
                                    "revert" -> Accent; else -> Ok
                                },
                                fontSize = 12.sp, fontFamily = FontFamily.Monospace)
                            Text(d.reason, color = Ink2, fontSize = 12.sp)
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun Strip(s: AppState.StripUi) {
    val ctx = LocalContext.current
    val vu = ((s.levelDb + 60f) / 60f).coerceIn(0f, 1f)
    Column(
        Modifier.width(92.dp).fillMaxHeight()
            .background(if (s.active) Panel2 else Panel, RoundedCornerShape(10.dp))
            .border(1.dp, if (s.active) Line else Inset, RoundedCornerShape(10.dp))
            .padding(8.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(s.name, color = Ink, fontSize = 12.sp, fontWeight = FontWeight.Bold,
            maxLines = 1)
        Text(
            when (s.role) {
                Role.FOUNDATION -> "FOUND"; Role.KEYS -> "KEYS"
                Role.PERCUSSION -> "PERC"; Role.RHYTHM_GTR -> "RHYTHM"
                Role.SOLO_GTR -> "SOLO"; Role.COLOR -> "COLOR"
                Role.BACKING_VOCAL -> "BVOX"; Role.VOCAL -> "VOCAL"
                Role.TALK -> "TALK"; else -> "INST"
            },
            color = when (s.role) {
                Role.VOCAL -> Live
                Role.BACKING_VOCAL -> Warn
                Role.FOUNDATION -> Accent
                else -> Muted
            }, fontSize = 9.sp, letterSpacing = 1.sp)
        Spacer(Modifier.height(6.dp))
        // VU
        Box(
            Modifier.weight(1f).width(14.dp)
                .background(Inset, RoundedCornerShape(4.dp)),
            contentAlignment = Alignment.BottomCenter,
        ) {
            Box(
                Modifier.fillMaxWidth().fillMaxHeight(vu)
                    .background(
                        when {
                            s.levelDb > -6f -> Bad
                            s.levelDb > -18f -> Warn
                            else -> Ok
                        }, RoundedCornerShape(4.dp))
            )
        }
        Spacer(Modifier.height(6.dp))
        Text("%+.1f".format(s.offsetDb), color = when {
            s.offsetDb > 0.2f -> Warn
            s.offsetDb < -0.2f -> Accent
            else -> Muted
        }, fontSize = 12.sp, fontFamily = FontFamily.Monospace)
        Text("dB adj", color = Muted, fontSize = 9.sp)
        if (kotlin.math.abs(s.eqOffsetDb) > 0.2f ||
            kotlin.math.abs(s.thrOffsetDb) > 0.2f) {
            Text(buildString {
                if (kotlin.math.abs(s.eqOffsetDb) > 0.2f)
                    append("EQ%+.1f ".format(s.eqOffsetDb))
                if (kotlin.math.abs(s.thrOffsetDb) > 0.2f)
                    append("TH%+.1f".format(s.thrOffsetDb))
            }, color = Ok, fontSize = 9.sp, fontFamily = FontFamily.Monospace)
        }
        Spacer(Modifier.height(6.dp))
        Box(
            Modifier.size(30.dp).clickable {
                MixerService.cmd(ctx, MixerService.ACTION_FREEZE_CH,
                    "ch" to s.channel, "on" to !s.frozen)
            }.background(if (s.frozen) Warn else Inset, CircleShape),
            contentAlignment = Alignment.Center,
        ) { Text(if (s.frozen) "🔒" else "🔓", fontSize = 13.sp) }
    }
}
