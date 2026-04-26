package com.nsu.transcriptmobile.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val DarkScheme = darkColorScheme(
    primary = Color(0xFF19D2C0),
    onPrimary = Color(0xFF022427),
    secondary = Color(0xFF39A7FF),
    background = Color(0xFF060B1E),
    surface = Color(0xFF0F1630),
    onBackground = Color(0xFFE6EDFF),
    onSurface = Color(0xFFE6EDFF)
)

private val LightScheme = lightColorScheme(
    primary = Color(0xFF006C64),
    onPrimary = Color.White,
    secondary = Color(0xFF005C9D),
    background = Color(0xFFF3F8FF),
    surface = Color.White,
    onBackground = Color(0xFF0D1B2A),
    onSurface = Color(0xFF0D1B2A)
)

@Composable
fun NsuTheme(content: @Composable () -> Unit) {
    val scheme = if (isSystemInDarkTheme()) DarkScheme else LightScheme
    MaterialTheme(
        colorScheme = scheme,
        typography = AppTypography,
        content = content
    )
}
