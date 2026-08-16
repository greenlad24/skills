package com.stagemix.app.ui

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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.stagemix.engine.Advice
import com.stagemix.engine.Level

/**
 * Everything that is wrong, and the thing to do about each one.
 *
 * Two rules, both learned the hard way.
 *
 * The first: the worst one is also on the top line of the screen, not
 * only in here. A fault on a tab nobody has open is a fault nobody
 * knows about, and the failure this app exists to not repeat — three
 * shows in watching mode — was visible on a screen the whole time.
 *
 * The second: no message without a remedy. "FAULT" tells an operator
 * something they can already hear. The useful half is the sentence
 * after it, so [Advice] carries both and this draws both, always.
 */

private fun tone(l: Level): Color = when (l) {
    Level.FAULT -> Bad
    Level.WARN -> Warn
    Level.NOTE -> Ink2
}

/** the single worst thing, for the top of the console */
@Composable
fun FaultLine(a: Advice?, modifier: Modifier = Modifier) {
    if (a == null || a.level == Level.NOTE) return
    Row(
        modifier.fillMaxWidth().well(8.dp)
            .padding(horizontal = 14.dp, vertical = 9.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(11.dp).background(tone(a.level), CircleShape))
        Spacer(Modifier.width(11.dp))
        Column {
            // Ellipsis, not clip. The second line is the REMEDY — the
            // half that tells you what to press — and clipping it
            // removes the useful part of the message with nothing on
            // screen to say anything was removed. At a large system
            // font scale that is most of the remedies in the app.
            Text(a.what, color = tone(a.level), fontSize = 17.sp,
                fontWeight = FontWeight.Bold, maxLines = 1,
                overflow = TextOverflow.Ellipsis)
            Text(a.doThis, color = Ink2, fontSize = 13.sp, maxLines = 2,
                overflow = TextOverflow.Ellipsis)
        }
    }
}

/** and the whole list, on its own tab */
@Composable
fun FaultPanel(advice: List<Advice>, modifier: Modifier = Modifier) {
    Column(modifier) {
        Text("WHAT IS WRONG, AND WHAT TO DO",
            color = Muted, fontSize = 11.sp,
            fontWeight = FontWeight.Bold, letterSpacing = 2.sp)
        Spacer(Modifier.height(8.dp))
        LazyColumn {
            items(advice, key = { it.key }) { a ->
                Row(
                    Modifier.fillMaxWidth().padding(vertical = 7.dp),
                    verticalAlignment = Alignment.Top,
                ) {
                    Box(Modifier.padding(top = 6.dp).size(10.dp)
                        .background(tone(a.level), CircleShape))
                    Spacer(Modifier.width(12.dp))
                    Column {
                        Text(a.what, color = tone(a.level), fontSize = 17.sp,
                            fontWeight = FontWeight.Bold)
                        Text(a.doThis, color = Ink2, fontSize = 14.sp)
                    }
                }
            }
        }
    }
}
