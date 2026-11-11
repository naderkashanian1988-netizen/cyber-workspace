package com.cyberworkspace.app.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.TextUnit
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

/** Terminal palette — single source of truth for the UI layer. */
val CyberGreen = Color(0xFF00FF66)
val CyberAmber = Color(0xFFFFB300)
val CyberCyan = Color(0xFF00E5FF)
val CyberErrorRed = Color(0xFFFF3D3D)
val CyberGray = Color(0xFF9AA09A)
val CyberBackground = Color(0xFF0A0C0A)
val CyberSurface = Color(0xFF10140F)

private val CyberColors = darkColorScheme(
    primary = CyberGreen,
    onPrimary = Color(0xFF03140A),
    secondary = CyberAmber,
    onSecondary = Color(0xFF140C03),
    tertiary = CyberCyan,
    onTertiary = Color(0xFF031418),
    background = CyberBackground,
    onBackground = Color(0xFFD7E4D7),
    surface = CyberSurface,
    onSurface = Color(0xFFD7E4D7),
    surfaceVariant = Color(0xFF182014),
    onSurfaceVariant = CyberGray,
    error = CyberErrorRed,
    onError = Color(0xFF160303),
    outline = Color(0xFF2A342A)
)

/** Data styles are monospace: timers, metrics and ids read as fixed columns. */
private fun mono(size: TextUnit, weight: FontWeight = FontWeight.Normal) = TextStyle(
    fontFamily = FontFamily.Monospace,
    fontSize = size,
    fontWeight = weight
)

private val CyberTypography = Typography(
    displaySmall = mono(30.sp, FontWeight.Bold),
    headlineLarge = mono(26.sp, FontWeight.Bold),
    headlineMedium = mono(22.sp, FontWeight.Bold),
    headlineSmall = mono(19.sp, FontWeight.Bold),
    titleLarge = mono(17.sp, FontWeight.SemiBold),
    titleMedium = mono(15.sp, FontWeight.SemiBold),
    titleSmall = mono(13.sp, FontWeight.Medium),
    bodyLarge = mono(14.sp),
    bodyMedium = mono(12.sp),
    bodySmall = mono(10.sp),
    labelLarge = mono(13.sp, FontWeight.Medium),
    labelMedium = mono(11.sp, FontWeight.Medium),
    labelSmall = mono(9.sp, FontWeight.Medium)
)

/** Dark terminal-styled theme for the whole app. */
@Composable
fun CyberTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = CyberColors, typography = CyberTypography, content = content)
}
