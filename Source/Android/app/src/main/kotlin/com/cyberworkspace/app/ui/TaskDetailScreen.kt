package com.cyberworkspace.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.cyberworkspace.app.AppViewModel
import com.cyberworkspace.app.protocol.TaskState

/**
 * Full task view: all five tri-timer buckets (Paused and Unknown included —
 * unknown time is never folded into active), state + reason, process info,
 * controls when the device has control permission, the pending approval
 * decision UI, and the log pane (monospace lines when provided).
 */
@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun TaskDetailScreen(
    viewModel: AppViewModel,
    taskId: String,
    onBack: () -> Unit,
    logLines: List<String> = emptyList()
) {
    val tasks by viewModel.observeTasks().collectAsState(initial = emptyList())
    val hasControl = remember { viewModel.hasControl() }
    val entity = tasks.firstOrNull { it.id == taskId }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        text = entity?.name ?: "Task",
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.Filled.ArrowBack, contentDescription = "Back")
                    }
                }
            )
        }
    ) { padding ->
        if (entity == null) {
            Box(
                modifier = Modifier
                    .padding(padding)
                    .fillMaxSize(),
                contentAlignment = Alignment.Center
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(
                        text = "This task is not in the local cache. It may have been removed on " +
                            "the host, or the state snapshot has not arrived yet.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        textAlign = TextAlign.Center,
                        modifier = Modifier.padding(32.dp)
                    )
                    NeonButton("Back", onClick = onBack)
                }
            }
            return@Scaffold
        }

        val task = entity.toTaskSnapshot()
        val stateCol = stateColor(task.state)
        val processInfo = when {
            task.pid != null && task.app != null -> "pid ${task.pid} · ${task.app}"
            task.pid != null -> "pid ${task.pid}"
            task.app != null -> task.app
            else -> "process info unavailable"
        }

        Column(
            modifier = Modifier
                .padding(padding)
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                StatusLed(
                    color = stateCol,
                    active = task.state == TaskState.RUNNING ||
                        task.state == TaskState.ERROR ||
                        task.state == TaskState.UNRESPONSIVE
                )
                Spacer(Modifier.width(10.dp))
                Column {
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        LabelChip(task.type, MaterialTheme.colorScheme.tertiary)
                        LabelChip(stateLabel(task.state), stateCol)
                        if (task.minimized) LabelChip("minimized", MaterialTheme.colorScheme.outline)
                        if (task.keepAwake) LabelChip("keep-awake", MaterialTheme.colorScheme.secondary)
                    }
                    Spacer(Modifier.height(4.dp))
                    Text(
                        text = processInfo,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
            task.reason?.let {
                Text(
                    text = "reason: $it",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            task.lastActivityUtc?.let {
                Text(
                    text = "last activity: $it",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            task.lastProgress?.let {
                Text(
                    text = "progress: $it",
                    style = MaterialTheme.typography.bodyMedium
                )
            }
            if (task.cpuPercent != null || task.ramMb != null) {
                Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                    task.cpuPercent?.let {
                        Text(
                            "CPU ${String.format(java.util.Locale.US, "%.1f", it)}%",
                            style = MaterialTheme.typography.bodyMedium
                        )
                    }
                    task.ramMb?.let {
                        Text(
                            "RAM ${String.format(java.util.Locale.US, "%.1f", it)} MB",
                            style = MaterialTheme.typography.bodyMedium
                        )
                    }
                }
            }

            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = androidx.compose.material3.CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.surface
                )
            ) {
                Column(
                    modifier = Modifier.padding(12.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    Text(
                        text = "Timers",
                        style = MaterialTheme.typography.titleSmall,
                        color = MaterialTheme.colorScheme.primary
                    )
                    TimerRow("Active", task.activeMs, ActiveTimerColor)
                    TimerRow("Waiting", task.waitingMs, WaitingTimerColor)
                    TimerRow("Error", task.errorMs, ErrorTimerColor)
                    TimerRow("Paused", task.pausedMs, PausedTimerColor)
                    TimerRow("Unknown", task.unknownMs, UnknownTimerColor)
                    Text(
                        text = "UNKNOWN time is never merged into active time.",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }

            if (hasControl) {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = androidx.compose.material3.CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.surface
                    )
                ) {
                    Column(modifier = Modifier.padding(12.dp)) {
                        Text(
                            text = "Controls",
                            style = MaterialTheme.typography.titleSmall,
                            color = MaterialTheme.colorScheme.primary
                        )
                        Spacer(Modifier.height(8.dp))
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            if (task.state == TaskState.PAUSED) {
                                NeonButton("Resume", { viewModel.resume(task.id) })
                            } else {
                                NeonButton("Pause", { viewModel.pause(task.id) })
                            }
                            NeonButton("Restart", { viewModel.restart(task.id) })
                            NeonButton("Close", { viewModel.close(task.id) })
                            NeonButton(
                                text = if (task.keepAwake) "Keep awake: ON" else "Keep awake: OFF",
                                onClick = { viewModel.setKeepAwake(task.id, !task.keepAwake) }
                            )
                        }
                    }
                }
            }

            val approval = task.pendingApproval
            if (approval != null) {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = androidx.compose.material3.CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.surface
                    )
                ) {
                    Column(modifier = Modifier.padding(12.dp)) {
                        Text(
                            text = "Approval required",
                            style = MaterialTheme.typography.titleSmall,
                            color = MaterialTheme.colorScheme.secondary
                        )
                        Spacer(Modifier.height(4.dp))
                        Text(approval.question, style = MaterialTheme.typography.bodyMedium)
                        if (approval.options.isNotEmpty()) {
                            Text(
                                text = "options: " + approval.options.joinToString(" · "),
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                        Spacer(Modifier.height(8.dp))
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            NeonButton(
                                "Approve",
                                onClick = { viewModel.approve(approval.id) },
                                isPrimary = true,
                                enabled = hasControl
                            )
                            NeonButton(
                                "Deny",
                                onClick = { viewModel.deny(approval.id) },
                                enabled = hasControl
                            )
                        }
                        if (!hasControl) {
                            Spacer(Modifier.height(4.dp))
                            Text(
                                text = "This device is view-only and cannot answer approvals.",
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
                }
            }

            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = androidx.compose.material3.CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.surface
                )
            ) {
                Column(modifier = Modifier.padding(12.dp)) {
                    Text(
                        text = "Logs",
                        style = MaterialTheme.typography.titleSmall,
                        color = MaterialTheme.colorScheme.primary
                    )
                    Spacer(Modifier.height(8.dp))
                    if (logLines.isEmpty()) {
                        Text(
                            text = "No log lines available for this task.",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    } else {
                        LazyColumn(
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(220.dp)
                        ) {
                            items(
                                count = logLines.size,
                                key = { index -> index }
                            ) { index ->
                                Text(
                                    text = logLines[index],
                                    style = MaterialTheme.typography.bodySmall,
                                    modifier = Modifier.padding(vertical = 2.dp)
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}
