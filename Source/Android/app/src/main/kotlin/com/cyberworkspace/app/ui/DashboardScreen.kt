package com.cyberworkspace.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
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
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.cyberworkspace.app.AppViewModel
import com.cyberworkspace.app.data.TaskEntity
import com.cyberworkspace.app.net.ConnState

/** Dashboard filter over the cached task list. */
private enum class DashFilter {
    ALL, RUNNING, WAITING, FAILED;

    fun matches(task: TaskEntity): Boolean = when (this) {
        ALL -> true
        RUNNING -> task.state == "RUNNING"
        WAITING -> task.state == "WAITING_FOR_USER" || task.state == "NETWORK_WAITING"
        FAILED -> task.state == "ERROR" || task.state == "UNRESPONSIVE"
    }
}

/**
 * Main screen: connection LED in the title bar, filter chips, grid of task
 * cards from the Room cache, FAB to the local monitor tasks and a bottom nav
 * for Notifications and Settings. Pull-refresh equivalent = re-request the
 * authoritative state snapshot (PROTOCOL.md §6).
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DashboardScreen(
    viewModel: AppViewModel,
    onOpenTask: (String) -> Unit,
    onOpenLocal: () -> Unit,
    onOpenNotifications: () -> Unit,
    onOpenSettings: () -> Unit
) {
    val tasks by viewModel.observeTasks().collectAsState(initial = emptyList())
    val conn by viewModel.connState.collectAsState()
    val unread by viewModel.observeUnreadCount().collectAsState(initial = 0)
    val hasControl = remember { viewModel.hasControl() }
    var filter by remember { mutableStateOf(DashFilter.ALL) }

    val filtered = tasks.filter { filter.matches(it) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("CYBER WORKSPACE", style = MaterialTheme.typography.titleLarge)
                        Spacer(Modifier.width(10.dp))
                        StatusLed(color = connStateColor(conn), active = connStateActive(conn))
                    }
                },
                actions = {
                    IconButton(onClick = { viewModel.refresh() }) {
                        Icon(Icons.Filled.Refresh, contentDescription = "Refresh state snapshot")
                    }
                }
            )
        },
        bottomBar = {
            NavigationBar {
                NavigationBarItem(
                    selected = false,
                    onClick = onOpenNotifications,
                    icon = {
                        BadgedBox(badge = {
                            if (unread > 0) Badge { Text(unread.toString()) }
                        }) {
                            Icon(Icons.Filled.Notifications, contentDescription = null)
                        }
                    },
                    label = { Text("Notifications") }
                )
                NavigationBarItem(
                    selected = false,
                    onClick = onOpenSettings,
                    icon = { Icon(Icons.Filled.Settings, contentDescription = null) },
                    label = { Text("Settings") }
                )
            }
        },
        floatingActionButton = {
            FloatingActionButton(onClick = onOpenLocal) {
                Icon(Icons.Filled.Add, contentDescription = "Local monitor tasks")
            }
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .padding(padding)
                .fillMaxSize()
        ) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 12.dp, vertical = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                DashFilter.values().forEach { candidate ->
                    FilterChip(
                        selected = filter == candidate,
                        onClick = { filter = candidate },
                        label = {
                            Text(candidate.name.lowercase().replace('_', ' '))
                        }
                    )
                }
            }
            if (filtered.isEmpty()) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    val message = when (val state = conn) {
                        ConnState.Connected ->
                            "Host reports no tasks for this filter yet — waiting for state updates."
                        is ConnState.PairingRequired ->
                            "Session requires re-pairing (${state.reason}). Open Settings to reconnect."
                        else ->
                            "Not connected to the host. The task list fills in once a connection is established."
                    }
                    Text(
                        text = message,
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        textAlign = TextAlign.Center,
                        modifier = Modifier.padding(32.dp)
                    )
                }
            } else {
                LazyVerticalGrid(
                    columns = GridCells.Adaptive(minSize = 320.dp),
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(12.dp),
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    items(
                        count = filtered.size,
                        key = { index -> filtered[index].id }
                    ) { index ->
                        val snapshot = filtered[index].toTaskSnapshot()
                        TaskCard(
                            task = snapshot,
                            onClick = { onOpenTask(snapshot.id) },
                            onPause = { viewModel.pause(snapshot.id) },
                            onResume = { viewModel.resume(snapshot.id) },
                            onRestart = { viewModel.restart(snapshot.id) },
                            onClose = { viewModel.close(snapshot.id) },
                            onKeepAwake = { enabled -> viewModel.setKeepAwake(snapshot.id, enabled) },
                            hasControl = hasControl,
                            onApprove = { requestId, approve ->
                                if (approve) viewModel.approve(requestId) else viewModel.deny(requestId)
                            }
                        )
                    }
                }
            }
        }
    }
}
