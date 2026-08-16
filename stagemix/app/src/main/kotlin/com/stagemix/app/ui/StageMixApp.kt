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
        Spacer(Modifier.height(18.dp))
        OutlinedButton(onClick = {
            com.stagemix.app.DemoStage.start()
        }) { Text("See it without a mixer (demo band)") }
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
    val notches by AppState.ringNotches.collectAsState()
    val leadDb by AppState.leadDb.collectAsState()
    val bandDb by AppState.bandDb.collectAsState()
    val startedMs by AppState.mixingSinceMs.collectAsState()
    val advice by AppState.advice.collectAsState()
    val work by AppState.work.collectAsState()
    var tab by remember { mutableStateOf(AppState.startTab) }
    var picking by remember { mutableStateOf<AppState.StripUi?>(null) }

    val fault = when {
        err != null -> err
        conn != AppState.Conn.CONNECTED ->
            "no answer from the mixer — nothing is moving"
        else -> null
    }
    val live = directing && fault == null && !frozenAll && !stageMuted

    Faceplate(warning = !live) {
        Column(Modifier.fillMaxSize()) {

            // ============ the top of the box: readout and transport
            Row(verticalAlignment = Alignment.CenterVertically) {
                // Just the clock here. The mode was stated twice — a
                // small LCD line AND the big word beside it — which on a
                // 600 dp-tall tablet, in a fault state (the extra fault
                // line, the hazard border), pushed the whole fixed
                // header far enough down that the rack's fader canvas
                // collapsed to nothing. One statement of the mode, the
                // big legible one, plus a compact CH count on the clock.
                Column {
                    Lcd(elapsed(startedMs, directing, tickMs), 34.sp,
                        if (live) Ok else Muted, weight = FontWeight.Black)
                    Spacer(Modifier.height(4.dp))
                    Lcd(if (directing) "$mixed CH" else "—",
                        12.sp, if (live) Ok else Muted)
                }
                Spacer(Modifier.width(16.dp))
                // The state, said in words as well as lit, because a lamp
                // alone is not an explanation.
                Column(Modifier.weight(1f)) {
                    Text(
                        when {
                            fault != null -> "PROBLEM"
                            frozenAll -> "FROZEN"
                            stageMuted -> "WAITING"
                            !directing -> "WATCHING ONLY"
                            else -> "MIXING"
                        },
                        color = when {
                            fault != null -> Bad
                            !directing || frozenAll || stageMuted -> Warn
                            else -> Ok
                        },
                        fontSize = 30.sp, fontWeight = FontWeight.Black,
                        letterSpacing = 2.sp)
                    Text(
                        when {
                            fault != null -> fault
                            frozenAll -> "every fader is held exactly where " +
                                "it is — tap FREEZE to resume"
                            stageMuted -> "you have the band muted on the " +
                                "desk — unmute to let it pick up again"
                            !directing -> "nothing is being sent to the " +
                                "mixer — tap MIX to start"
                            balanceKept -> "holding the balance you kept · " +
                                "monitors untouched"
                            else -> "finding the balance · monitors untouched"
                        },
                        color = Ink2, fontSize = 14.sp, maxLines = 2)
                }
                Spacer(Modifier.width(12.dp))
                // THE PANIC CONTROLS CHANGE THE TRUTH HERE, NOT IN A
                // SERVICE.
                //
                // Every key used to be a pure remote control: fire an
                // Intent at MixerService and hope. All the state they
                // appear to change is owned by that service and written
                // only inside onStartCommand — so when the service is
                // not up, the key does nothing, says nothing, and looks
                // exactly like a key that worked. A UI smoke test on a
                // tablet caught MIX and FREEZE doing precisely that.
                //
                // At a gig the service is a live foreground service and
                // the round trip completes, but that guarantee lapses
                // the moment it dies or is disconnected — and FREEZE is
                // the panic button. It has to work with no service, no
                // engine and no console. So the flag flips here, and
                // the service is told afterwards.
                TransportKey("MIX", live, Live, Modifier.width(88.dp)) {
                    AppState.directing.value = !directing
                    MixerService.cmd(ctx, MixerService.ACTION_DIRECTING,
                        "on" to AppState.directing.value)
                }
                Spacer(Modifier.width(8.dp))
                TransportKey("FREEZE", frozenAll, Bad, Modifier.width(88.dp),
                    square = true) {
                    AppState.frozenAll.value = !frozenAll
                    MixerService.cmd(ctx, MixerService.ACTION_FREEZE_ALL,
                        "on" to AppState.frozenAll.value)
                }
                Spacer(Modifier.width(8.dp))
                TransportKey("KEEP", balanceKept, Ok, Modifier.width(88.dp)) {
                    MixerService.cmd(ctx, MixerService.ACTION_KEEP_BALANCE)
                }
                Spacer(Modifier.width(8.dp))
                // REBALANCE: do it now, on both mixes.
                //
                // The mains get re-laddered against the balance being
                // defended; the wedges get one deliberate pass instead
                // of the slow drip. Bounded by exactly the same totals
                // as the automatic work — pressing a button is
                // permission to act now, not permission to act
                // differently.
                TransportKey("Re-Balance", false, Accent,
                    Modifier.width(104.dp)) {
                    MixerService.cmd(ctx, MixerService.ACTION_REBALANCE)
                }
                Spacer(Modifier.width(8.dp))
                TransportKey("UNDO", false, Accent, Modifier.width(88.dp)) {
                    // Like MIX/FREEZE: hand-back pauses the app, so the
                    // truth changes here whether or not a service is up.
                    AppState.directing.value = false
                    MixerService.cmd(ctx, MixerService.ACTION_REVERT)
                }
            }

            Spacer(Modifier.height(10.dp))

            // ============ tabs, and the master meters beside them
            Row(verticalAlignment = Alignment.CenterVertically) {
                Segmented(
                    listOf("MIXER", "MONITORS", "STATUS", "LOG", "SETUP"),
                    tab) { tab = it }
                Spacer(Modifier.width(14.dp))
                MasterMeters(leadDb, bandDb, Modifier.weight(1f))
            }

            Spacer(Modifier.height(10.dp))

            // ============ one line of plain English, always
            NowLine(
                headline = headlineFor(decisions.firstOrNull(), hold,
                    directing, strips),
                detail = decisions.firstOrNull()?.reason ?: "",
                tickMs = tickMs,
                shadow = !directing && decisions.isNotEmpty())

            // THE WORST THING WRONG, ON EVERY TAB.
            //
            // Including "the app is not mixing", which is a fault and is
            // coloured like one. Three shows went by with that being
            // true and nothing on the screen saying it.
            FaultLine(advice.firstOrNull())

            // AND WHAT IT IS DOING, ALWAYS — see WorkBar. This is never
            // absent: with no countdown to run it shows how much of the
            // mix is where it belongs, which moves all night.
            work?.let { WorkBar(it) }

            Spacer(Modifier.height(10.dp))

            // ============ the rack, or whatever else the tab asks for
            Box(Modifier.weight(1f).fillMaxWidth()) {
                when (tab) {
                    0 -> MixerRack(
                        strips = strips, leadVocal = lead,
                        directing = directing, notches = notches,
                        modifier = Modifier.fillMaxSize(),
                        onTap = { picking = it })
                    1 -> MonitorPanel(Modifier.fillMaxSize())
                    2 -> FaultPanel(advice, Modifier.fillMaxSize())
                    3 -> LastFive(decisions, Modifier.fillMaxSize())
                    else -> SetupPanel(Modifier.fillMaxSize())
                }
            }
        }
    }

    picking?.let { s -> InstrumentPicker(s) { picking = null } }
}

/** the show clock, in the units a recorder uses */
private fun elapsed(startedMs: Long, directing: Boolean, tickMs: Long): String {
    // 0 means "never started", and that is the only value that means it.
    // The old guard rejected anything <= 0, which quietly stopped the
    // clock whenever the anchor sat before the device booted — the demo
    // asks for a show already 24 minutes old, and on a machine that has
    // been up for two, that anchor is negative and perfectly valid.
    if (!directing || startedMs == 0L) return "--:--:--"
    val s = ((android.os.SystemClock.elapsedRealtime() - startedMs) / 1000L)
        .coerceAtLeast(0L)
    return "%02d:%02d:%02d".format(s / 3600, (s % 3600) / 60, s % 60)
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
    Column(modifier.well(10.dp).padding(16.dp)) {
        Text("WHAT IT HAS DONE", color = Muted, fontSize = 12.sp,
            letterSpacing = 2.sp)
        Spacer(Modifier.height(8.dp))
        val marks = decisions.filter { it.kind in LANDMARKS }.take(12)
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
    val keeping by AppState.keepMonitors.collectAsState()
    Column(modifier.well(10.dp).padding(12.dp)) {
        MonitorRack(wedges, names, keeping, Modifier.fillMaxWidth().weight(1f))
        Spacer(Modifier.height(6.dp))
        Text(
            if (keeping)
                "Cuts before boosts, at most 6 dB down and 1.5 dB up on " +
                "any send all night, nothing between songs — and no " +
                "address in this app can move a bus master."
            else "Monitor keeping is off: these are read from the desk " +
                "and nothing is written.",
            color = Muted, fontSize = 12.sp)
    }
}

/** everything that is not a mid-song decision, on its own tab */
@Composable
private fun SetupPanel(modifier: Modifier) {
    val ctx = LocalContext.current
    val doctorOn by AppState.doctorOn.collectAsState()
    val health by AppState.health.collectAsState()
    val nights by AppState.nightsCount.collectAsState()
    val taste by AppState.tasteSummary.collectAsState()
    val lastNight by AppState.lastNightSummary.collectAsState()
    val autoStart by AppState.autoStart.collectAsState()
    val keepMon by AppState.keepMonitors.collectAsState()
    val preRing by AppState.preRing.collectAsState()
    Column(modifier.well(10.dp).padding(16.dp)) {
        // The two switches that decide what the app does without being
        // asked. Both default ON; both are one tap from off.
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("AUTO-START", color = if (autoStart) Ok else Muted,
                fontWeight = FontWeight.Bold, fontSize = 15.sp,
                letterSpacing = 1.sp)
            Spacer(Modifier.width(8.dp))
            Switch(checked = autoStart, onCheckedChange = {
                MixerService.cmd(ctx, MixerService.ACTION_AUTO_START,
                    "on" to it)
            })
            Spacer(Modifier.width(20.dp))
            Text("KEEP MONITORS", color = if (keepMon) Ok else Muted,
                fontWeight = FontWeight.Bold, fontSize = 15.sp,
                letterSpacing = 1.sp)
            Spacer(Modifier.width(8.dp))
            Switch(checked = keepMon, onCheckedChange = {
                MixerService.cmd(ctx, MixerService.ACTION_KEEP_MONITORS,
                    "on" to it)
            })
        }
        Text(
            (if (autoStart) "connects and takes the mains by itself"
             else "waits for you to tap MIX") + "  ·  " +
            (if (keepMon) "wedges corrected slightly, cut-first, never " +
                "against your hand"
             else "wedges untouched"),
            color = Muted, fontSize = 12.5.sp)
        Spacer(Modifier.height(12.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("PRE-RING", color = if (preRing) Ok else Muted,
                fontWeight = FontWeight.Bold, fontSize = 15.sp,
                letterSpacing = 1.sp)
            Spacer(Modifier.width(8.dp))
            Switch(checked = preRing, onCheckedChange = {
                MixerService.cmd(ctx, MixerService.ACTION_PRE_RING, "on" to it)
            })
        }
        Text(
            if (preRing) "at takeover, a shallow guard cut on frequencies " +
                "this rig has howled at before — cut-only, deepens if it " +
                "still rings"
            else "feedback is learned and logged; turn on to pre-cut the " +
                "frequencies that howl here",
            color = Muted, fontSize = 12.5.sp)
        Spacer(Modifier.height(12.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("EQ + COMP", color = if (doctorOn) Ok else Muted,
                fontWeight = FontWeight.Bold, fontSize = 15.sp,
                letterSpacing = 1.sp)
            Spacer(Modifier.width(8.dp))
            Switch(checked = doctorOn, onCheckedChange = {
                MixerService.cmd(ctx, MixerService.ACTION_DOCTOR, "on" to it)
            })
            Spacer(Modifier.width(20.dp))
            Box(Modifier.raised(8.dp).clickable {
                MixerService.cmd(ctx, MixerService.ACTION_SNAPSHOT)
            }.padding(horizontal = 14.dp, vertical = 10.dp)) {
                Text("RE-BASELINE", color = Ink2, fontSize = 13.sp,
                    fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
            }
            Spacer(Modifier.width(10.dp))
            Box(Modifier.raised(8.dp).clickable {
                MixerService.cmd(ctx, MixerService.ACTION_REBALANCE)
            }.padding(horizontal = 14.dp, vertical = 10.dp)) {
                Text("NEW BALANCE", color = Ink2, fontSize = 13.sp,
                    fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
            }
        }
        Spacer(Modifier.height(14.dp))
        health?.let { h ->
            Lcd((if (h.vocalOnTopPct < 0) "VOCAL ON TOP  --"
                 else "VOCAL ON TOP %3d%%".format(h.vocalOnTopPct)) +
                "   IN PLACE %3d%%   YOU OUT-MIXED IT %d".format(
                    h.inPlacePct, h.overrides),
                13.sp, Ink2)
        }
        Spacer(Modifier.height(8.dp))
        if (nights > 0 || taste.isNotBlank())
            Text(buildString {
                if (nights > 0) append("NIGHT ${nights + 1}")
                if (taste.isNotBlank()) append("  ·  learned: $taste")
            }, color = Accent, fontSize = 14.sp)
        if (lastNight.isNotBlank())
            Text(lastNight, color = Muted, fontSize = 13.sp)
        Spacer(Modifier.height(14.dp))
        Text("TELL IT WHAT YOU WANT", color = Muted, fontSize = 11.sp,
            letterSpacing = 2.sp)
        Spacer(Modifier.height(8.dp))
        LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            items(listOf(
                "good" to "Sounds great",
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
                Box(Modifier.raised(8.dp).clickable {
                    MixerService.cmd(ctx, MixerService.ACTION_FEEDBACK,
                        "kind" to kind)
                }.padding(horizontal = 13.dp, vertical = 9.dp)) {
                    Text(label, fontSize = 13.sp,
                        color = if (kind == "good") Ok else Ink2)
                }
            }
        }
        Spacer(Modifier.weight(1f))
        ExportLogButtons()
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
        Role.DRUMS to "Drums / kit",
        Role.PERCUSSION to "Percussion (congas)",
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
