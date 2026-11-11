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
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Checkbox
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.cyberworkspace.app.AppViewModel
import com.cyberworkspace.app.PairingEvent
import android.os.Build

/**
 * Pairing flow (PROTOCOL.md §4): host + port + device name + the 6-digit code
 * shown on the host. The certificate fingerprint received in `welcome` is
 * displayed as soon as the TLS handshake completes; Connect is only enabled
 * once every field is filled and the user confirmed the fingerprint check.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PairingScreen(viewModel: AppViewModel, onPaired: () -> Unit) {
    var host by remember { mutableStateOf("") }
    var port by remember { mutableStateOf("") }
    var deviceName by remember { mutableStateOf(Build.MODEL.ifBlank { "android-device" }) }
    var code by remember { mutableStateOf("") }
    var verified by remember { mutableStateOf(false) }

    val fingerprint by viewModel.pairingFingerprint.collectAsState()
    val snackbarHostState = remember { SnackbarHostState() }

    LaunchedEffect(Unit) {
        viewModel.pairingEvents.collect { event ->
            when (event) {
                is PairingEvent.Failed -> snackbarHostState.showSnackbar(event.reason)
                PairingEvent.Success -> onPaired()
            }
        }
    }

    val portValid = (port.toIntOrNull() ?: 0) in 1..65535
    val codeValid = code.length == 6 && code.all { it.isDigit() }
    val fieldsValid = host.isNotBlank() && deviceName.isNotBlank() && portValid && codeValid
    val canConnect = fieldsValid && verified

    Scaffold(
        snackbarHost = { SnackbarHost(snackbarHostState) },
        topBar = { TopAppBar(title = { Text("Pair with CYBER WORKSPACE") }) }
    ) { padding ->
        Column(
            modifier = Modifier
                .padding(padding)
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Text(
                text = "Connect to the Windows host over TLS. The host shows a certificate " +
                    "fingerprint and a single-use 6-digit pairing code (expires after 5 minutes).",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            OutlinedTextField(
                value = host,
                onValueChange = { host = it },
                label = { Text("Host") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth()
            )
            OutlinedTextField(
                value = port,
                onValueChange = { port = it },
                label = { Text("Port") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                modifier = Modifier.fillMaxWidth()
            )
            OutlinedTextField(
                value = deviceName,
                onValueChange = { deviceName = it },
                label = { Text("Device name") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth()
            )
            OutlinedTextField(
                value = code,
                onValueChange = { code = it.filter { ch -> ch.isDigit() }.take(6) },
                label = { Text("6-digit pairing code") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                modifier = Modifier.fillMaxWidth()
            )
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 4.dp)
            ) {
                Column {
                    Text(
                        text = "Host certificate fingerprint",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.secondary
                    )
                    Spacer(Modifier.height(2.dp))
                    Text(
                        text = fingerprint.ifBlank { "waiting for TLS handshake…" },
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.fillMaxWidth()
            ) {
                Checkbox(checked = verified, onCheckedChange = { verified = it })
                Spacer(Modifier.width(8.dp))
                Text(
                    text = "Fingerprint verified on the Windows screen",
                    style = MaterialTheme.typography.bodyMedium
                )
            }
            NeonButton(
                text = "Connect",
                onClick = {
                    val portNumber = port.toIntOrNull() ?: return@NeonButton
                    viewModel.pair(host = host, port = portNumber, deviceName = deviceName, code = code)
                },
                isPrimary = true,
                enabled = canConnect,
                modifier = Modifier.fillMaxWidth()
            )
            Text(
                text = "On success the device token is issued once and stored encrypted on this " +
                    "device (PROTOCOL.md §4). If the session later expires or is revoked, pairing " +
                    "must be repeated.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}
