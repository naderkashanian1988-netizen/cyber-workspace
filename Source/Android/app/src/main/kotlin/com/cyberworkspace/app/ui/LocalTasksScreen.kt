package com.cyberworkspace.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.cyberworkspace.app.AppViewModel
import com.cyberworkspace.app.data.LocalTaskEntity
import com.cyberworkspace.app.protocol.TaskState

/** Honesty note shown above the task list: what the app does NOT claim. */
private const val HONESTY_NOTE =
    "Reporting honesty: these monitors run on this device. When Android suspends the app " +
        "(Doze / App Standby) a cycle cannot run — that interval is charged to the UNKNOWN " +
        "bucket and is never reported as active work, so displayed timers may lag behind " +
        "wall-clock time. Very short intervals can also be delayed by the OS."

/**
 * Locally defined URL monitor tasks: add form (name, url, interval), enable
 * toggle and delete. The Room table is the source of truth; MonitorService's
 * LocalTaskEngine observes it and runs the enabled tasks.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LocalTasksScreen(viewModel: AppViewModel) {
    val tasks by viewModel.observeLocalTasks().collectAsState(initial = emptyList())
    var name by remember { mutableStateOf("") }
    var url by remember { mutableStateOf("") }
    var interval by remember { mutableStateOf("60") }

    val intervalValid = (interval.toIntOrNull() ?: 0) >= 5
    val canAdd = name.isNotBlank() && url.isNotBlank() && intervalValid

    Scaffold(
        topBar = { TopAppBar(title = { Text("Local monitor tasks") }) }
    ) { padding ->
        Column(
            modifier = Modifier
                .padding(padding)
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
            ) {
                Column(
                    modifier = Modifier.padding(12.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Text(
                        text = "Add monitor task",
                        style = MaterialTheme.typography.titleSmall,
                        color = MaterialTheme.colorScheme.primary
                    )
                    OutlinedTextField(
                        value = name,
                        onValueChange = { name = it },
                        label = { Text("Name") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )
                    OutlinedTextField(
                        value = url,
                        onValueChange = { url = it },
                        label = { Text("URL to monitor") },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
                        modifier = Modifier.fillMaxWidth()
                    )
                    OutlinedTextField(
                        value = interval,
                        onValueChange = { interval = it.filter { ch -> ch.isDigit() }.take(5) },
                        label = { Text("Interval in seconds (min 5)") },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        modifier = Modifier.fillMaxWidth()
                    )
                    NeonButton(
                        text = "Add task",
                        onClick = {
                            val seconds = interval.toIntOrNull() ?: return@NeonButton
                            viewModel.addLocalTask(name = name, url = url, intervalSec = seconds)
                            name = ""
                            url = ""
                            interval = "60"
                        },
                        isPrimary = true,
                        enabled = canAdd,
                        modifier = Modifier.fillMaxWidth()
                    )
                }
            }
            Text(
                text = HONESTY_NOTE,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            Text(
                text = "Tasks (${tasks.size})",
                style = MaterialTheme.typography.titleSmall,
                color = MaterialTheme.colorScheme.primary
            )
            if (tasks.isEmpty()) {
                Text(
                    text = "No local monitor tasks defined yet.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            } else {
                tasks.forEach { task ->
                    LocalTaskRow(
                        task = task,
                        onToggle = { viewModel.setLocalTaskEnabled(task.id, !task.enabled) },
                        onDelete = { viewModel.deleteLocalTask(task.id) }
                    )
                }
            }
            Spacer(Modifier.height(16.dp))
        }
    }
}

@Composable
private fun LocalTaskRow(task: LocalTaskEntity, onToggle: () -> Unit, onDelete: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
    ) {
        Row(
            modifier = Modifier.padding(12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = task.name,
                    style = MaterialTheme.typography.titleSmall,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
                Text(
                    text = task.url,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
                Spacer(Modifier.height(4.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                    LabelChip("every ${task.intervalSec}s", MaterialTheme.colorScheme.tertiary)
                    LabelChip(
                        "last: ${task.lastState}",
                        stateColor(runCatching { TaskState.valueOf(task.lastState) }.getOrDefault(TaskState.UNKNOWN))
                    )
                }
            }
            Spacer(Modifier.width(8.dp))
            Switch(checked = task.enabled, onCheckedChange = { onToggle() })
            IconButton(onClick = onDelete) {
                Icon(Icons.Filled.Delete, contentDescription = "Delete task")
            }
        }
    }
}
