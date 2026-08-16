package com.stagemix.app.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

// Broadcast-console palette, matching AutoDirector's Control Room.
val Bg = Color(0xFF0A0D12)
val Panel = Color(0xFF12161D)
val Panel2 = Color(0xFF161B24)
val Inset = Color(0xFF0D1117)
val Line = Color(0xFF222A35)
val Ink = Color(0xFFE9EEF5)
val Ink2 = Color(0xFF9FABB9)
// WAS #5F6C7B, which is 2.9:1 against this background — under the 4.5
// minimum, on a tablet held at arm's length, in a dark bar. It was
// carrying the role label, the "dB adj" caption and the mix health.
val Muted = Color(0xFF8A96A5)
val Accent = Color(0xFF4FB8FF)
val Ok = Color(0xFF3FD68F)
val Warn = Color(0xFFFFC24B)
val Bad = Color(0xFFFF5D5D)
val Live = Color(0xFFFF4652)

/**
 * THE STAGE.
 *
 * Blue against amber rather than green against red, because a red stage
 * wash collapses red and green toward each other and red/green is the
 * common colour deficiency — so the two states an operator must never
 * confuse are told apart by the one pair that survives both, and by
 * texture and words as well as hue.
 */
val StageFloor = Color(0xFF0B0F14)
val StageLine = Color(0xFF1B2430)
/** roles, for the pucks */
val RoleVocal = Color(0xFF7FE9FF)
val RoleBacking = Color(0xFF4FA8BC)
val RoleFoundation = Color(0xFF8A7CFF)
val RolePercussion = Color(0xFF7C8AA0)
val RoleKeys = Color(0xFF49C2A8)
val RoleRhythm = Color(0xFF9FB35A)
val RoleSolo = Color(0xFFFF9F45)
val RoleColour = Color(0xFFE07BD6)

@Composable
fun StageMixTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = darkColorScheme(
            primary = Accent,
            background = Bg,
            surface = Panel,
            surfaceVariant = Panel2,
            onPrimary = Bg,
            onBackground = Ink,
            onSurface = Ink,
        ),
        content = content,
    )
}
