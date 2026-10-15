package com.roamsync.app.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val RoamSyncColors = lightColorScheme(
    primary = Color(0xFF218F84),
    secondary = Color(0xFF4A635D),
    tertiary = Color(0xFF426277),
    background = Color(0xFFF4F6F3),
    surface = Color(0xFFFCFDFB),
    onSurface = Color(0xFF11243F),
    onBackground = Color(0xFF11243F),
    primaryContainer = Color(0xFFD9EFEA),
    onPrimaryContainer = Color(0xFF135A52),
    secondaryContainer = Color(0xFFD9EFEA),
    onSecondaryContainer = Color(0xFF135A52),
    surfaceVariant = Color(0xFFE8EFEB),
    outline = Color(0xFF81958E),
    outlineVariant = Color(0xFFCDDCD5),
)

@Composable
fun RoamSyncTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = RoamSyncColors, content = content)
}
