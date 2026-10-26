package com.roamsync.app.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val RoamSyncColors = lightColorScheme(
    primary = Color(0xFF006B5E),
    secondary = Color(0xFF4A635D),
    tertiary = Color(0xFF426277),
    background = Color(0xFFF7FBF8),
    surface = Color(0xFFF7FBF8),
)

@Composable
fun RoamSyncTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = RoamSyncColors, content = content)
}
