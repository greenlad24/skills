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
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
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
import android.content.Intent
import android.widget.Toast
import com.stagemix.app.AppState
import com.stagemix.app.LogExport
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
            // ONCE THE NIGHT HAS STARTED, A DROPOUT IS A MESSAGE — NOT
            // A DIFFERENT SCREEN.
            //
            // This read `CONNECTED -> console, else -> setup`, and ten
            // seconds without a meter packet drops the state to
            // CONNECTING. On the console's own 2.4 GHz AP in a full bar
            // that happens during shows — it is in both real logs. So
            // mid-song the console was replaced by the setup page,
            // offering an IP box and a "find my mixer" button that
            // builds a NEW engine and a NEW show log: one tap and the
            // night's takeover baselines and the kept balance are gone,
            // and every channel is placed again from scratch.
            val everCon by AppState.everConnected.collectAsState()
            when {
                conn == AppState.Conn.CONNECTED || everCon -> ConsoleScreen()
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
            // The mixer's own access point has no internet, and Android
            // will happily send everything out a phone network instead
            // while the Wi-Fi icon sits there looking connected. The app
            // now pins its sockets to the console's Wi-Fi, so this is a
            // belt to that braces — but flight mode with Wi-Fi on is the
            // one setting that cannot be argued with.
            "No SIM / mobile data off — or flight mode with Wi-Fi ON",
            "Say YES to “stay connected” if Android warns about no internet",
            "Wedges rung out at soundcheck — keep the usual 6 dB margin",
            "Install the APK BEFORE you leave: there is no internet at the desk",
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
    val strips by AppState.strips.collectAsState()
    val decisions by AppState.decisions.collectAsState()
    val hold by AppState.holdReason.collectAsState()
    val directing by AppState.directing.collectAsState()
    val frozenAll by AppState.frozenAll.collectAsState()
    val balanceKept by AppState.balanceKept.collectAsState()
    val stageMuted by AppState.stageMuted.collectAsState()
    val err by AppState.lastError.collectAsState()
    val conn by AppState.conn.collectAsState()
    val lead by AppState.leadVocal.collectAsState()
    val phase by AppState.phase.collectAsState()
    val tickMs by AppState.tickMs.collectAsState()
    val mixed by AppState.channelsMixed.collectAsState()
    val wedges by AppState.wedges.collectAsState()
    val notches by AppState.ringNotches.collectAsState()
    var detail by remember { mutableStateOf(false) }
    var picking by remember { mutableStateOf<AppState.StripUi?>(null) }

    val fault = when {
        err != null -> err
        conn != AppState.Conn.CONNECTED ->
            "no answer from the mixer — nothing is moving"
        else -> null
    }

    Column(Modifier.fillMaxSize()) {
        // Everything the operator must know without reading: what state
        // the app is in, and that tapping here changes it.
        ModeBand(
            directing = directing, keeping = balanceKept,
            stageMuted = stageMuted, frozen = frozenAll, fault = fault,
            channelsMixed = mixed, channelsTotal = strips.size,
            onToggle = {
                MixerService.cmd(ctx, MixerService.ACTION_DIRECTING,
                    "on" to !directing)
            })

        Column(Modifier.weight(1f).padding(12.dp)) {
            val newest = decisions.firstOrNull()
            NowLine(
                headline = headlineFor(newest, hold, directing, strips),
                detail = newest?.reason ?: "",
                tickMs = tickMs, shadow = !directing && newest != null)
            phase?.let { PhaseBar(it) }
            Spacer(Modifier.height(10.dp))
            // THE CONSOLE. Sixteen strips, each one the object an
            // engineer already knows how to read — a meter, a fader in
            // a lane with a scale, the number, and what that channel
            // sounds like. Everything on it is a real measurement off
            // the desk.
            MixerRack(
                strips = strips, leadVocal = lead, directing = directing,
                notches = notches,
                modifier = Modifier.weight(1f).fillMaxWidth(),
                onTap = { picking = it })
        }

        ActionPads(
            frozen = frozenAll,
            onFreeze = {
                MixerService.cmd(ctx, MixerService.ACTION_FREEZE_ALL,
                    "on" to !frozenAll)
            },
            onKeep = { MixerService.cmd(ctx, MixerService.ACTION_KEEP_BALANCE) },
            onUndo = { MixerService.cmd(ctx, MixerService.ACTION_REVERT) },
            onDetail = { detail = true })
    }

    picking?.let { s -> InstrumentPicker(s) { picking = null } }
    if (detail) DetailSheet { detail = false }
}

/**
 * The newest decision, in the operator's language rather than the
 * engine's — and, when there is nothing to report, a sentence saying
 * exactly that. Silence on this line is the one thing it must never do:
 * "nothing needed doing" and "this app has stopped" look identical
 * otherwise, which is how three nights went by.
 */
private fun headlineFor(d: com.stagemix.engine.Decision?, hold: String?,
                        directing: Boolean,
                        strips: List<AppState.StripUi>): String {
    hold?.let { return it.replaceFirstChar { c -> c.uppercase() } }
    if (d == null) return if (!directing)
        "Watching the band — nothing has been sent to your mixer"
        else "Listening to the room"
    val name = d.channel?.let { ch ->
        strips.firstOrNull { it.channel == ch }?.name
            ?: "ch%02d".format(ch + 1) } ?: ""
    val db = if (d.deltaDb != 0f) " · %+.1f dB".format(d.deltaDb) else ""
    return when (d.kind) {
        "ride" -> "Easing $name back to its place$db"
        "placed" -> "Found a place for $name$db"
        "leave" -> "Left $name where you had it"
        "arrive" -> "$name came in — listening before placing it"
        "feature" -> "$name stepped up — leaving the feature with the player"
        "duck" -> "Clearing room for the vocal$db"
        "held-down" -> "$name held down — nothing on it"
        "ident" -> "Worked out what $name is"
        "lead" -> "$name is carrying the song now"
        "gap" -> "Between songs — holding everything still"
        "music" -> "The band is back"
        "stage-mute" -> "You have the band muted"
        "override" -> "You moved $name$db — that is the new level"
        "soloride" -> "Keeping your lift on $name for the solo"
        "rebalance" -> "Finding the balance again"
        "keep" -> "Keeping this balance"
        "treat" -> "Setting up $name"
        "ensemble" -> "The line-up changed"
        "takeover" -> "Took the mains"
        else -> d.kind.replaceFirstChar { c -> c.uppercase() } +
            (if (name.isNotBlank()) " · $name" else "") + db
    }
}

/**
 * The five things worth knowing, newest first — landmarks only.
 *
 * The running commentary (every ride, every trim) belongs in the log
 * and not on a stage. What belongs here is what changed: somebody
 * arrived, somebody soloed, you overruled it, the band stopped.
 */
private val LANDMARKS = setOf("arrive", "feature", "soloride", "override",
    "rebalance", "keep", "held-down", "ident", "leave", "lead", "gap",
    "music", "stage-mute", "takeover", "treat", "feedback")

@Composable
private fun LastFive(decisions: List<com.stagemix.engine.Decision>,
                     modifier: Modifier) {
    Column(
        modifier
            .background(Panel, RoundedCornerShape(12.dp))
            .border(1.dp, Line, RoundedCornerShape(12.dp))
            .padding(12.dp)
    ) {
        Text("WHAT IT HAS DONE", color = Muted, fontSize = 12.sp,
            letterSpacing = 2.sp)
        Spacer(Modifier.height(8.dp))
        val marks = decisions.filter { it.kind in LANDMARKS }.take(5)
        if (marks.isEmpty())
            Text("Nothing worth reporting yet.", color = Ink2, fontSize = 15.sp)
        for (d in marks) {
            Column(Modifier.padding(bottom = 10.dp)) {
                Text(d.kind.uppercase() +
                    (if (d.deltaDb != 0f) "  %+.1f dB".format(d.deltaDb) else ""),
                    color = when (d.kind) {
                        "override", "soloride" -> Warn
                        "held-down", "leave" -> Bad
                        else -> Ok
                    },
                    fontSize = 13.sp, fontFamily = FontFamily.Monospace,
                    fontWeight = FontWeight.Bold)
                Text(d.reason, color = Ink2, fontSize = 14.sp)
            }
        }
        Spacer(Modifier.weight(1f))
        Text("${decisions.size} decisions tonight — all of them in the log",
            color = Muted, fontSize = 12.sp)
    }
}

/**
 * THE MONITORS, read off the desk and never written.
 *
 * The app now reads all ninety-six sends and works out what each wedge
 * is for from the name you gave it. This is what it found, and where it
 * thinks each one disagrees with what a monitor in that position wants.
 * It is a second opinion, not an action: nothing here is ever sent.
 */
@Composable
private fun MonitorPanel(modifier: Modifier) {
    val wedges by AppState.wedges.collectAsState()
    val names by AppState.mixerChannelNames.collectAsState()
    Column(
        modifier
            .background(Panel, RoundedCornerShape(12.dp))
            .border(1.dp, Line, RoundedCornerShape(12.dp))
            .padding(14.dp)
    ) {
        Text("MONITORS — READ ONLY", color = Muted, fontSize = 12.sp,
            letterSpacing = 2.sp)
        Spacer(Modifier.height(8.dp))
        if (wedges.isEmpty())
            Text("Nothing read yet. The wedges are read when the app " +
                "takes the mains.", color = Ink2, fontSize = 15.sp)
        for (w in wedges) {
            Column(Modifier.padding(bottom = 12.dp)) {
                Text("${w.name}  ·  ${w.kind.lowercase().replace('_', ' ')}",
                    color = Ink, fontSize = 15.sp,
                    fontWeight = FontWeight.Bold)
                Text("loudest: " + (w.top.joinToString(", ") {
                        names[it] ?: "ch%02d".format(it + 1) }
                        .ifBlank { "nothing" }),
                    color = Ink2, fontSize = 14.sp)
                w.worstCh?.let { ch ->
                    Text((names[ch] ?: "ch%02d".format(ch + 1)) +
                        " is %+.1f dB from where this position wants it"
                            .format(-w.worstOffDb),
                        color = Warn, fontSize = 14.sp)
                }
            }
        }
        Spacer(Modifier.weight(1f))
        Text("The app has never written a monitor send or a bus master.",
            color = Muted, fontSize = 12.sp)
    }
}

/** everything that is not a mid-song decision */
@Composable
private fun DetailSheet(onClose: () -> Unit) {
    val ctx = LocalContext.current
    val doctorOn by AppState.doctorOn.collectAsState()
    val health by AppState.health.collectAsState()
    val nights by AppState.nightsCount.collectAsState()
    val taste by AppState.tasteSummary.collectAsState()
    val lastNight by AppState.lastNightSummary.collectAsState()
    val strips by AppState.strips.collectAsState()
    Surface(color = Bg, modifier = Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize().padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("DETAIL", color = Ink, fontSize = 22.sp,
                    fontWeight = FontWeight.Black, letterSpacing = 2.sp)
                Spacer(Modifier.weight(1f))
                Button(onClick = onClose) { Text("Back to the show") }
            }
            Spacer(Modifier.height(12.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("EQ + COMP", color = if (doctorOn) Ok else Muted,
                    fontWeight = FontWeight.Bold, fontSize = 16.sp)
                Spacer(Modifier.width(8.dp))
                Switch(checked = doctorOn, onCheckedChange = {
                    MixerService.cmd(ctx, MixerService.ACTION_DOCTOR, "on" to it)
                })
                Spacer(Modifier.width(20.dp))
                OutlinedButton(onClick = {
                    MixerService.cmd(ctx, MixerService.ACTION_SNAPSHOT)
                }) { Text("Re-baseline (bounds = now)") }
                Spacer(Modifier.width(10.dp))
                OutlinedButton(onClick = {
                    MixerService.cmd(ctx, MixerService.ACTION_REBALANCE)
                }) { Text("Find a new balance") }
            }
            Spacer(Modifier.height(12.dp))
            health?.let { h ->
                Text(
                    (if (h.vocalOnTopPct < 0) "vocal on top — listening"
                     else "vocal on top ${h.vocalOnTopPct}%") +
                    "   ·   channels in place ${h.inPlacePct}%" +
                    "   ·   you out-mixed it ${h.overrides} times",
                    color = Ink2, fontSize = 15.sp,
                    fontFamily = FontFamily.Monospace)
            }
            if (nights > 0 || taste.isNotBlank())
                Text(buildString {
                    if (nights > 0) append("NIGHT ${nights + 1}")
                    if (taste.isNotBlank()) append("  ·  learned: $taste")
                }, color = Accent, fontSize = 14.sp)
            if (lastNight.isNotBlank())
                Text(lastNight, color = Muted, fontSize = 13.sp)
            Spacer(Modifier.height(12.dp))
            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                items(listOf(
                    "good" to "👍 Sounds great",
                    "vocal_up" to "Vocal louder",
                    "vocal_down" to "Vocal softer",
                    "gtr_down" to "Less guitar",
                    "gtr_up" to "More guitar",
                    "keys_up" to "More piano",
                    "keys_down" to "Less piano",
                    "low_up" to "More low end",
                    "perc_down" to "Less percussion",
                    "color_down" to "Softer sax/harp",
                ), key = { it.first }) { (kind, label) ->
                    OutlinedButton(onClick = {
                        MixerService.cmd(ctx, MixerService.ACTION_FEEDBACK,
                            "kind" to kind)
                    }) { Text(label, fontSize = 14.sp,
                              color = if (kind == "good") Ok else Ink2) }
                }
            }
            Spacer(Modifier.height(14.dp))
            Row(Modifier.weight(1f)) {
                MonitorPanel(Modifier.weight(1f).fillMaxHeight())
                Spacer(Modifier.width(12.dp))
                LastFive(AppState.decisions.value,
                    Modifier.weight(1f).fillMaxHeight())
            }
            Spacer(Modifier.height(10.dp))
            ExportLogButtons()
        }
    }
}

@Composable
private fun InstrumentPicker(s: AppState.StripUi, onDone: () -> Unit) {
    val ctx = LocalContext.current
    val choices = listOf(
        Role.VOCAL to "Lead vocal",
        Role.BACKING_VOCAL to "Backing vocal",
        Role.COLOR to "Horn / sax / harmonica",
        Role.SOLO_GTR to "Lead guitar",
        Role.RHYTHM_GTR to "Rhythm guitar",
        Role.KEYS to "Keys / piano",
        Role.PERCUSSION to "Drums / percussion",
        Role.FOUNDATION to "Kick / bass",
        Role.TALK to "Talkback (never mixed)")
    androidx.compose.material3.AlertDialog(
        onDismissRequest = onDone,
        confirmButton = {},
        dismissButton = {
            OutlinedButton(onClick = onDone) { Text("Cancel") }
        },
        title = { Text("What is on ${s.name}?") },
        text = {
            Column {
                Text("The app hears a melody in the voice band and cannot " +
                    "tell a singer from a saxophone. Tell it once and it " +
                    "will remember this channel name.",
                    color = Muted, fontSize = 12.sp)
                Spacer(Modifier.height(10.dp))
                for ((role, label) in choices) {
                    OutlinedButton(
                        onClick = {
                            MixerService.cmd(ctx, MixerService.ACTION_SET_ROLE,
                                "ch" to s.channel, "role" to role.name)
                            onDone()
                        },
                        modifier = Modifier.fillMaxWidth()
                            .padding(vertical = 2.dp),
                    ) { Text(label) }
                }
            }
        },
    )
}

/**
 * Export the night. The tablet is on the mixer's Wi-Fi with no
 * internet, so nothing is uploaded here: the share sheet hands the file
 * to WhatsApp (or mail, or Drive), which queues it and sends the moment
 * the tablet is back on a normal network.
 *
 * Two sizes, because both are useful the morning after: the whole log
 * as an attachment, and a one-screen digest that pastes straight into a
 * chat message.
 */
@Composable
private fun ExportLogButtons() {
    val ctx = LocalContext.current
    val logPath by AppState.logPath.collectAsState()
    fun latest() = LogExport.latest(ctx)

    Button(
        onClick = {
            val f = latest()
            if (f == null) {
                Toast.makeText(ctx,
                    "No show log yet — connect to the mixer first",
                    Toast.LENGTH_SHORT).show()
                return@Button
            }
            val intent = LogExport.shareIntent(ctx, f)
            if (intent == null) {
                Toast.makeText(ctx, "Log is at ${f.absolutePath}",
                    Toast.LENGTH_LONG).show()
            } else {
                ctx.startActivity(Intent.createChooser(intent,
                    "Send the show log").apply {
                        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    })
            }
        },
        colors = ButtonDefaults.buttonColors(containerColor = Panel2),
    ) { Text("⤴  EXPORT LOG", color = Ink, fontSize = 12.sp) }

    Spacer(Modifier.width(6.dp))
    OutlinedButton(onClick = {
        val f = latest() ?: return@OutlinedButton
        ctx.startActivity(Intent.createChooser(
            LogExport.shareDigest(ctx, f), "Send the short version").apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            })
    }) { Text("short version", fontSize = 11.sp) }

    if (logPath.isNotBlank()) {
        Spacer(Modifier.width(8.dp))
        Text("recording", color = Live, fontSize = 10.sp, letterSpacing = 1.sp)
    }
}
