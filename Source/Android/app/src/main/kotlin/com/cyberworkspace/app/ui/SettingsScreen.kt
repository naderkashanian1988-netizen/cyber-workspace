package com.cyberworkspace.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
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
import androidx.compose.ui.unit.dp
import com.cyberworkspace.app.AppViewModel
import com.cyberworkspace.app.net.ConnState

/**
 * Session settings: connection LED, pinned fingerprint, granted permissions,
 * the session-expiry explainer, disconnect and clear-pairing actions, and the
 * release footer.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(viewModel: AppViewModel, onPairingNeeded: () -> Unit) {
    val conn by viewModel.connState.collectAsState()
    val fingerprint = remember { viewModel.authStore.fingerprint }
    val permissions = remember { viewModel.authStore.permissions }
    val paired = remember { viewModel.isPaired() }
    val hasControl = remember { viewModel.hasControl() }

    Scaffold(
        topBar = { TopAppBar(title = { Text("Settings") }) }
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
                Row(
                    modifier = Modifier.padding(12.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    StatusLed(color = connStateColor(conn), active = connStateActive(conn))
                    Spacer(Modifier.width(10.dp))
                    Column {
                        Text("Connection", style = MaterialTheme.typography.titleSmall)
                        Text(
                            text = connStateLabel(conn),
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
            }

            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
            ) {
                Column(
                    modifier = Modifier.padding(12.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    Text("Device credentials", style = MaterialTheme.typography.titleSmall)
                    Text(
                        text = if (paired) "This device is paired with the host." else "This device is not paired.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        text = "Certificate fingerprint",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.secondary
                    )
                    Text(
                        text = fingerprint.ifBlank { "not paired" },
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        text = "Permissions",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.secondary
                    )
                    Text(
                        text = if (permissions.isEmpty()) "none" else permissions.joinToString(", "),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        text = if (hasControl)
                            "This device may send commands and approval decisions."
                        else
                            "This device is view-only; commands and approvals are disabled.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }

            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
            ) {
                Column(modifier = Modifier.padding(12.dp)) {
                    Text("Session expiry", style = MaterialTheme.typography.titleSmall)
                    Spacer(Modifier.height(6.dp))
                    Text(
                        text = "The pairing token is issued once at pairing time and expires after " +
                            "30 days of disuse (SESSION_EXPIRED); the host can also revoke a device " +
                            "(REVOKED). In both cases the connection is refused and this device must " +
                            "re-pair with a fresh 6-digit code. While connected, the app sends a ping " +
                            "every 5 minutes so the host does not close the session after 15 minutes " +
                            "of silence.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }

            NeonButton(
                text = "Disconnect",
                onClick = { viewModel.disconnect() },
                enabled = conn != ConnState.Disconnected,
                modifier = Modifier.fillMaxWidth()
            )
            NeonButton(
                text = "Clear pairing",
                onClick = {
                    viewModel.clearPairing()
                    onPairingNeeded()
                },
                modifier = Modifier.fillMaxWidth()
            )

            Box(modifier = Modifier.fillMaxWidth()) {
                Text(
                    text = "CYBER WORKSPACE 1.0.0-rc.1",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    textAlign = TextAlign.Center,
                    modifier = Modifier
                        .align(Alignment.Center)
                        .padding(top = 8.dp, bottom = 16.dp)
                )
            }
        }
    }
}
