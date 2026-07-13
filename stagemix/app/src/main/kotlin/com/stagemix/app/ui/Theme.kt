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
val Muted = Color(0xFF5F6C7B)
val Accent = Color(0xFF4FB8FF)
val Ok = Color(0xFF3FD68F)
val Warn = Color(0xFFFFC24B)
val Bad = Color(0xFFFF5D5D)
val Live = Color(0xFFFF4652)

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
