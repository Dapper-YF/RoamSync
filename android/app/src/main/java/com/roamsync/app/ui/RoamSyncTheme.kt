package com.roamsync.app.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

private val RoamSyncColors = lightColorScheme(
    primary = Color(0xFF287D70),
    onPrimary = Color(0xFFFFFFFF),
    secondary = Color(0xFF195B53),
    tertiary = Color(0xFFDD815D),
    background = Color(0xFFF7F4EB),
    onBackground = Color(0xFF183A38),
    surface = Color(0xFFFFFDF7),
    onSurface = Color(0xFF183A38),
    surfaceVariant = Color(0xFFEAE9DE),
    onSurfaceVariant = Color(0xFF536E66),
    primaryContainer = Color(0xFFDCEBE1),
    onPrimaryContainer = Color(0xFF195B53),
    secondaryContainer = Color(0xFFE9EEE4),
    onSecondaryContainer = Color(0xFF195B53),
    error = Color(0xFF9D4433),
    errorContainer = Color(0xFFF4DDD5),
    outline = Color(0xFF82918A),
    outlineVariant = Color(0xFFD9D8CD),
)

private val RoamSyncTypography = Typography(
    displayLarge = TextStyle(fontFamily = FontFamily.Serif, fontWeight = FontWeight.Medium, fontSize = 40.sp, lineHeight = 48.sp, letterSpacing = (-1.2).sp),
    displayMedium = TextStyle(fontFamily = FontFamily.Serif, fontWeight = FontWeight.Medium, fontSize = 34.sp, lineHeight = 42.sp, letterSpacing = (-0.7).sp),
    headlineLarge = TextStyle(fontFamily = FontFamily.Serif, fontWeight = FontWeight.Medium, fontSize = 30.sp, lineHeight = 38.sp, letterSpacing = (-0.5).sp),
    headlineMedium = TextStyle(fontFamily = FontFamily.Serif, fontWeight = FontWeight.Medium, fontSize = 25.sp, lineHeight = 33.sp, letterSpacing = (-0.35).sp),
    headlineSmall = TextStyle(fontFamily = FontFamily.Serif, fontWeight = FontWeight.Medium, fontSize = 21.sp, lineHeight = 29.sp),
    titleLarge = TextStyle(fontFamily = FontFamily.Serif, fontWeight = FontWeight.SemiBold, fontSize = 20.sp, lineHeight = 28.sp),
    titleMedium = TextStyle(fontWeight = FontWeight.SemiBold, fontSize = 16.sp, lineHeight = 24.sp),
    bodyLarge = TextStyle(fontSize = 16.sp, lineHeight = 25.sp),
    bodyMedium = TextStyle(fontSize = 14.sp, lineHeight = 21.sp),
    bodySmall = TextStyle(fontSize = 12.sp, lineHeight = 18.sp),
    labelLarge = TextStyle(fontWeight = FontWeight.SemiBold, fontSize = 14.sp, lineHeight = 20.sp),
)

@Composable
fun RoamSyncTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = RoamSyncColors, typography = RoamSyncTypography, content = content)
}
