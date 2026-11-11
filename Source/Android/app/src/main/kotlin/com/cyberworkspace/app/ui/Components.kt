package com.cyberworkspace.app.ui

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.cyberworkspace.app.data.TaskEntity
import com.cyberworkspace.app.net.ConnState
import com.cyberworkspace.app.protocol.PendingApproval
import com.cyberworkspace.app.protocol.ProtocolJson
import com.cyberworkspace.app.protocol.TaskSnapshot
import com.cyberworkspace.app.protocol.TaskState
import com.cyberworkspace.app.ui.theme.CyberAmber
import com.cyberworkspace.app.ui.theme.CyberCyan
import com.cyberworkspace.app.ui.theme.CyberErrorRed
import com.cyberworkspace.app.ui.theme.CyberGray
import com.cyberworkspace.app.ui.theme.CyberGreen
import java.util.Locale

/** Tri-timer bucket colors — UNKNOWN is its own bucket, never merged into active. */
val ActiveTimerColor = CyberGreen
val WaitingTimerColor = CyberAmber
val ErrorTimerColor = CyberErrorRed
val PausedTimerColor = Color(0xFF8A8F8A)
val UnknownTimerColor = CyberGray

/** LED / indicator color for a TaskState. */
fun stateColor(state: TaskState): Color = when (state) {
    TaskState.RUNNING -> CyberGreen
    TaskState.WAITING_FOR_USER -> CyberAmber
    TaskState.NETWORK_WAITING -> CyberCyan
    TaskState.ERROR, TaskState.UNRESPONSIVE -> CyberErrorRed
    TaskState.PAUSED -> PausedTimerColor
    TaskState.UNKNOWN -> CyberGray
    TaskState.COMPLETED -> Color(0xFF2E9E55) // dim green
}

/** Human label of a TaskState (wire names, spaced for readability). */
fun stateLabel(state: TaskState): String = when (state) {
    TaskState.WAITING_FOR_USER -> "WAITING FOR USER"
    TaskState.NETWORK_WAITING -> "NETWORK WAITING"
    else -> state.name
}

/** Connection LED color / label / pulse, shared by dashboard and settings. */
fun connStateColor(state: ConnState): Color = when (state) {
    ConnState.Connected -> CyberGreen
    ConnState.Connecting, ConnState.Authenticating -> CyberAmber
    is ConnState.PairingRequired -> CyberErrorRed
    ConnState.Disconnected -> CyberGray
}

fun connStateLabel(state: ConnState): String = when (state) {
    ConnState.Connected -> "Connected"
    ConnState.Connecting -> "Connecting…"
    ConnState.Authenticating -> "Authenticating…"
    ConnState.Disconnected -> "Disconnected"
    is ConnState.PairingRequired -> "Re-pairing required (${state.reason})"
}

fun connStateActive(state: ConnState): Boolean =
    state == ConnState.Connecting || state == ConnState.Authenticating

/** Milliseconds → HH:MM:SS (hours grow past two digits when needed). */
fun formatHms(ms: Long): String {
    val total = ms.coerceAtLeast(0L) / 1000L
    return String.format(Locale.US, "%02d:%02d:%02d", total / 3600, (total % 3600) / 60, total % 60)
}

/** Pulsing status LED; active states pulse, others glow steady. */
@Composable
fun StatusLed(color: Color, active: Boolean, modifier: Modifier = Modifier) {
    val transition = rememberInfiniteTransition(label = "status-led")
    val pulse by transition.animateFloat(
        initialValue = 0.35f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = 700, easing = LinearEasing),
            repeatMode = RepeatMode.Reverse
        ),
        label = "status-led-alpha"
    )
    val alpha = if (active) pulse else 0.75f
    Box(modifier = modifier.size(12.dp).clip(CircleShape).background(color.copy(alpha = alpha)))
}

/** One timer bucket row: colored dot + label + HH:MM:SS value. */
@Composable
fun TimerRow(label: String, ms: Long, color: Color, modifier: Modifier = Modifier) {
    Row(modifier = modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(8.dp).clip(CircleShape).background(color))
        Spacer(Modifier.width(8.dp))
        Text(
            text = label,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.weight(1f)
        )
        Text(
            text = formatHms(ms),
            style = MaterialTheme.typography.bodyMedium,
            color = color,
            fontWeight = FontWeight.Bold
        )
    }
}

/** Green-bordered neon action button. */
@Composable
fun NeonButton(
    text: String,
    onClick: () -> Unit,
    isPrimary: Boolean = false,
    enabled: Boolean = true,
    modifier: Modifier = Modifier
) {
    OutlinedButton(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier,
        border = BorderStroke(
            width = 1.dp,
            color = if (isPrimary) MaterialTheme.colorScheme.primary
            else MaterialTheme.colorScheme.primary.copy(alpha = 0.45f)
        ),
        colors = ButtonDefaults.outlinedButtonColors(
            contentColor = if (isPrimary) MaterialTheme.colorScheme.primary
            else MaterialTheme.colorScheme.onSurfaceVariant,
            disabledContentColor = MaterialTheme.colorScheme.outline
        )
    ) {
        Text(text, style = MaterialTheme.typography.labelLarge)
    }
}

/** Small rounded label chip in the given tint. */
@Composable
fun LabelChip(text: String, color: Color) {
    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(4.dp))
            .background(color.copy(alpha = 0.15f))
            .padding(horizontal = 6.dp, vertical = 2.dp)
    ) {
        Text(text, style = MaterialTheme.typography.labelSmall, color = color)
    }
}

private fun oneDecimal(value: Double): String = String.format(Locale.US, "%.1f", value)

/** Room cache row → protocol display model (pending approval JSON decoded). */
fun TaskEntity.toTaskSnapshot(): TaskSnapshot = TaskSnapshot(
    id = id,
    name = name,
    type = type,
    state = runCatching { TaskState.valueOf(state) }.getOrDefault(TaskState.UNKNOWN),
    reason = reason,
    activeMs = activeMs,
    waitingMs = waitingMs,
    errorMs = errorMs,
    pausedMs = pausedMs,
    unknownMs = unknownMs,
    cpuPercent = cpuPercent,
    ramMb = ramMb,
    lastActivityUtc = lastActivityUtc,
    lastProgress = lastProgress,
    keepAwake = keepAwake,
    minimized = minimized,
    pendingApproval = pendingApprovalJson?.let { raw ->
        runCatching { ProtocolJson.decodeFromString(PendingApproval.serializer(), raw) }.getOrNull()
    }
)

/**
 * Task summary card: state LED, name, type/state chips, the three headline
 * timer buckets (unknown gets its own row when > 0), metrics, progress, and —
 * when this device has control — the command row and the approval block.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun TaskCard(
    task: TaskSnapshot,
    onClick: () -> Unit,
    onPause: () -> Unit,
    onResume: () -> Unit,
    onRestart: () -> Unit,
    onClose: () -> Unit,
    onKeepAwake: (Boolean) -> Unit,
    hasControl: Boolean,
    onApprove: (requestId: String, approve: Boolean) -> Unit = { _, _ -> },
    modifier: Modifier = Modifier
) {
    val stateCol = stateColor(task.state)
    Card(
        onClick = onClick,
        modifier = modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline)
    ) {
        Column(Modifier.padding(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                StatusLed(
                    color = stateCol,
                    active = task.state == TaskState.RUNNING ||
                        task.state == TaskState.ERROR ||
                        task.state == TaskState.UNRESPONSIVE
                )
                Spacer(Modifier.width(10.dp))
                Column(Modifier.weight(1f)) {
                    Text(
                        text = task.name,
                        style = MaterialTheme.typography.titleMedium,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                    Spacer(Modifier.height(4.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        LabelChip(task.type, MaterialTheme.colorScheme.tertiary)
                        LabelChip(stateLabel(task.state), stateCol)
                        if (task.minimized) LabelChip("minimized", MaterialTheme.colorScheme.outline)
                        if (task.keepAwake) LabelChip("keep-awake", MaterialTheme.colorScheme.secondary)
                    }
                }
            }
            Spacer(Modifier.height(10.dp))
            TimerRow("Active", task.activeMs, ActiveTimerColor)
            TimerRow("Waiting", task.waitingMs, WaitingTimerColor)
            TimerRow("Error", task.errorMs, ErrorTimerColor)
            if (task.unknownMs > 0) TimerRow("Unknown", task.unknownMs, UnknownTimerColor)
            if (task.cpuPercent != null || task.ramMb != null) {
                Spacer(Modifier.height(6.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    task.cpuPercent?.let { Text("CPU ${oneDecimal(it)}%", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
                    task.ramMb?.let { Text("RAM ${oneDecimal(it)} MB", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
                }
            }
            task.lastProgress?.let {
                Spacer(Modifier.height(4.dp))
                Text(
                    text = "progress: $it",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
            }
            task.reason?.let {
                Spacer(Modifier.height(2.dp))
                Text(
                    text = "reason: $it",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis
                )
            }
            if (hasControl) {
                Spacer(Modifier.height(10.dp))
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    if (task.state == TaskState.PAUSED) {
                        NeonButton("Resume", onResume)
                    } else {
                        NeonButton("Pause", onPause)
                    }
                    NeonButton("Restart", onRestart)
                    NeonButton("Close", onClose)
                    NeonButton(
                        text = if (task.keepAwake) "Keep awake ON" else "Keep awake OFF",
                        onClick = { onKeepAwake(!task.keepAwake) }
                    )
                }
            }
            val approval = task.pendingApproval
            if (approval != null && hasControl) {
                Spacer(Modifier.height(10.dp))
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(6.dp))
                        .background(MaterialTheme.colorScheme.secondary.copy(alpha = 0.12f))
                        .padding(10.dp)
                ) {
                    Text(
                        text = "Approval required",
                        style = MaterialTheme.typography.labelLarge,
                        color = MaterialTheme.colorScheme.secondary
                    )
                    Spacer(Modifier.height(4.dp))
                    Text(approval.question, style = MaterialTheme.typography.bodyMedium)
                    if (approval.options.isNotEmpty()) {
                        Spacer(Modifier.height(2.dp))
                        Text(
                            text = approval.options.joinToString(" · "),
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                    Spacer(Modifier.height(8.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        NeonButton("Approve", { onApprove(approval.id, true) }, isPrimary = true)
                        NeonButton("Deny", { onApprove(approval.id, false) })
                    }
                }
            }
        }
    }
}
