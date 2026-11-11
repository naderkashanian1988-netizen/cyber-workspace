package com.cyberworkspace.app

import android.Manifest
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.cyberworkspace.app.data.LocalDb
import com.cyberworkspace.app.data.LocalTaskEntity
import com.cyberworkspace.app.data.NotificationEntity
import com.cyberworkspace.app.data.TaskEntity
import com.cyberworkspace.app.net.AuthStore
import com.cyberworkspace.app.net.ConnState
import com.cyberworkspace.app.net.ProtocolEvent
import com.cyberworkspace.app.net.WorkspaceConnection
import com.cyberworkspace.app.net.fingerprintHostnameVerifier
import com.cyberworkspace.app.protocol.CommandAction
import com.cyberworkspace.app.protocol.DECISION_APPROVE
import com.cyberworkspace.app.protocol.DECISION_DENY
import com.cyberworkspace.app.protocol.Envelope
import com.cyberworkspace.app.protocol.NotificationCategory
import com.cyberworkspace.app.protocol.Op
import com.cyberworkspace.app.protocol.PairingOkMsg
import com.cyberworkspace.app.protocol.PendingApproval
import com.cyberworkspace.app.protocol.ProtocolJson
import com.cyberworkspace.app.protocol.TaskEventKind
import com.cyberworkspace.app.protocol.TaskSnapshot
import com.cyberworkspace.app.protocol.WelcomeMsg
import com.cyberworkspace.app.protocol.buildEnvelope
import com.cyberworkspace.app.ui.DashboardScreen
import com.cyberworkspace.app.ui.LocalTasksScreen
import com.cyberworkspace.app.ui.NotificationsScreen
import com.cyberworkspace.app.ui.PairingScreen
import com.cyberworkspace.app.ui.SettingsScreen
import com.cyberworkspace.app.ui.TaskDetailScreen
import com.cyberworkspace.app.ui.theme.CyberTheme
import java.security.SecureRandom
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.decodeFromJsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener

class MainActivity : ComponentActivity() {

    private val viewModel: AppViewModel by viewModels()

    private val notificationPermission =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
            // Result is not tracked: AppViewModel re-checks the grant before every post.
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
        setContent {
            CyberTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    AppRoot(viewModel)
                }
            }
        }
    }
}

/** Outcome of a pairing handshake, consumed by PairingScreen. */
sealed interface PairingEvent {
    object Success : PairingEvent
    data class Failed(val reason: String) : PairingEvent
}

/**
 * UI-layer store: owns the persistent [WorkspaceConnection], the Room database
 * accessors and the ephemeral pairing handshake. Protocol events are persisted
 * to Room (task cache / notification log) and surfaced as system notifications.
 */
class AppViewModel(app: android.app.Application) : AndroidViewModel(app) {

    val authStore: AuthStore = AuthStore(app)
    private val db: LocalDb = LocalDb.get(app)
    private val conn: WorkspaceConnection = WorkspaceConnection(authStore)

    private val uiPrefs = app.getSharedPreferences(UI_PREFS_NAME, Context.MODE_PRIVATE)

    val connState: StateFlow<ConnState> = conn.state

    private val pairingFpFlow = MutableStateFlow("")
    val pairingFingerprint: StateFlow<String> = pairingFpFlow.asStateFlow()

    private val pairingEventsBus = MutableSharedFlow<PairingEvent>(extraBufferCapacity = 8)
    val pairingEvents: SharedFlow<PairingEvent> = pairingEventsBus.asSharedFlow()

    private var pairingSocket: WebSocket? = null
    private var pairingClient: OkHttpClient? = null
    @Volatile private var pairingDone = false
    private var autoConnectDone = false
    private val notifyIds = AtomicInteger(100)

    init {
        viewModelScope.launch {
            conn.events.collect { onProtocolEvent(it) }
        }
    }

    // -- lookups -----------------------------------------------------------

    fun isPaired(): Boolean = authStore.isPaired()

    fun hasControl(): Boolean = authStore.hasPermission("control")

    fun observeTasks() = db.taskDao().observeAll()

    fun observeNotifications() = db.notificationDao().recent(NOTIFICATION_LIMIT)

    fun observeUnreadCount() = db.notificationDao().unreadCount()

    fun observeLocalTasks() = db.localTaskDao().observeAll()

    // -- commands and approvals --------------------------------------------

    fun pause(taskId: String) {
        conn.sendCommand(CommandAction.PAUSE, taskId)
    }

    fun resume(taskId: String) {
        conn.sendCommand(CommandAction.RESUME, taskId)
    }

    fun restart(taskId: String) {
        conn.sendCommand(CommandAction.RESTART, taskId)
    }

    fun close(taskId: String) {
        conn.sendCommand(CommandAction.CLOSE, taskId)
    }

    fun setKeepAwake(taskId: String, enabled: Boolean) {
        conn.sendCommand(
            CommandAction.SET_KEEP_AWAKE,
            taskId,
            buildJsonObject { put("enabled", enabled) }
        )
    }

    fun approve(requestId: String) {
        conn.sendApprove(requestId, DECISION_APPROVE)
    }

    fun deny(requestId: String) {
        conn.sendApprove(requestId, DECISION_DENY)
    }

    /** Re-request the authoritative state baseline (PROTOCOL.md §6). */
    fun refresh() {
        conn.refreshState()
    }

    fun disconnect() {
        conn.disconnect()
    }

    // -- notifications -----------------------------------------------------

    fun markRead(id: String) {
        viewModelScope.launch { runCatching { db.notificationDao().markRead(id) } }
    }

    fun markAllRead() {
        viewModelScope.launch { runCatching { db.notificationDao().markAllRead() } }
    }

    // -- local monitor tasks -----------------------------------------------

    fun addLocalTask(name: String, url: String, intervalSec: Int) {
        val task = LocalTaskEntity(
            id = java.util.UUID.randomUUID().toString(),
            name = name.trim(),
            url = url.trim(),
            intervalSec = intervalSec.coerceIn(5, 3600),
            enabled = true
        )
        viewModelScope.launch { runCatching { db.localTaskDao().upsert(task) } }
    }

    fun setLocalTaskEnabled(id: String, enabled: Boolean) {
        viewModelScope.launch {
            runCatching {
                db.localTaskDao().get(id)?.let { db.localTaskDao().upsert(it.copy(enabled = enabled)) }
            }
        }
    }

    fun deleteLocalTask(id: String) {
        viewModelScope.launch { runCatching { db.localTaskDao().delete(id) } }
    }

    // -- pairing (PROTOCOL.md §4) ------------------------------------------

    /**
     * Ephemeral pairing handshake on its own socket: TLS connect → welcome
     * (fingerprint shown here and on the host) → pairing {device_name, code} →
     * pairing_ok (credentials persisted once) → auth → auth_ok. During pairing
     * there is no stored fingerprint to pin yet, so the certificate is accepted
     * and the user performs the verification against the Windows screen; the
     * persistent connection afterwards pins via FingerprintPinningTrustManager.
     */
    fun pair(host: String, port: Int, deviceName: String, code: String) {
        if (pairingSocket != null) return
        pairingDone = false
        pairingFpFlow.value = ""

        val trustManager = object : X509TrustManager {
            override fun checkClientTrusted(chain: Array<java.security.cert.X509Certificate>, authType: String) = Unit
            override fun checkServerTrusted(chain: Array<java.security.cert.X509Certificate>, authType: String) = Unit
            override fun getAcceptedIssuers(): Array<java.security.cert.X509Certificate> = emptyArray()
        }
        val sslContext = SSLContext.getInstance("TLS").apply {
            init(null, arrayOf<TrustManager>(trustManager), SecureRandom())
        }
        val client = OkHttpClient.Builder()
            .connectTimeout(10, TimeUnit.SECONDS)
            .readTimeout(20, TimeUnit.SECONDS)
            .sslSocketFactory(sslContext.socketFactory, trustManager)
            .hostnameVerifier(fingerprintHostnameVerifier())
            .build()
        pairingClient = client

        pairingSocket = client.newWebSocket(
            Request.Builder().url("wss://${host.trim()}:$port/").build(),
            object : WebSocketListener() {
                override fun onOpen(webSocket: WebSocket, response: Response) {
                    // Waiting for `welcome`; nothing to send before it arrives.
                }

                override fun onMessage(webSocket: WebSocket, text: String) {
                    onPairingMessage(webSocket, text, host.trim(), port, deviceName.trim(), code.trim())
                }

                override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                    failPairing("connection failed: ${t.message ?: t.javaClass.simpleName}")
                }

                override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                    if (!pairingDone) failPairing("connection closed: ${reason.ifBlank { "code $code" }}")
                }
            }
        )
        viewModelScope.launch {
            delay(PAIRING_TIMEOUT_MS)
            if (!pairingDone) failPairing("pairing timed out — no response from host")
        }
    }

    private fun onPairingMessage(ws: WebSocket, text: String, host: String, port: Int, deviceName: String, code: String) {
        val root = try {
            ProtocolJson.parseToJsonElement(text).jsonObject
        } catch (e: Exception) {
            failPairing("unparseable host message")
            return
        }
        val payload = (root["payload"] as? JsonObject) ?: JsonObject(emptyMap())
        when (root["op"]?.jsonPrimitive?.contentOrNull) {
            Op.WELCOME -> {
                val welcome = runCatching { ProtocolJson.decodeFromJsonElement<WelcomeMsg>(payload) }.getOrNull()
                val fingerprint = welcome?.fingerprint?.takeIf { it.isNotBlank() }
                if (fingerprint == null) {
                    failPairing("host did not report a certificate fingerprint")
                    return
                }
                pairingFpFlow.value = fingerprint
                ws.send(
                    ProtocolJson.encodeToString(
                        Envelope.serializer(),
                        buildEnvelope(
                            Op.PAIRING,
                            buildJsonObject {
                                put("device_name", deviceName)
                                put("code", code)
                            }
                        )
                    )
                )
            }
            Op.PAIRING_OK -> {
                val ok = runCatching { ProtocolJson.decodeFromJsonElement<PairingOkMsg>(payload) }.getOrNull()
                if (ok == null) {
                    failPairing("malformed pairing_ok")
                    return
                }
                // Token travels exactly once; stored encrypted on this device.
                authStore.save(ok.deviceId, ok.token, pairingFpFlow.value, ok.permissions)
                ws.send(
                    ProtocolJson.encodeToString(
                        Envelope.serializer(),
                        buildEnvelope(
                            Op.AUTH,
                            buildJsonObject {
                                put("device_id", ok.deviceId)
                                put("token", ok.token)
                                put("device_name", deviceName)
                            }
                        )
                    )
                )
            }
            Op.AUTH_OK -> {
                pairingDone = true
                uiPrefs.edit().putString(KEY_HOST, host).putInt(KEY_PORT, port).apply()
                closePairingSocket()
                pairingEventsBus.tryEmit(PairingEvent.Success)
                conn.connect(host, port)
            }
            Op.AUTH_FAILED -> failPairing("authentication failed after pairing")
            Op.ERROR -> {
                val errorCode = payload["code"]?.jsonPrimitive?.contentOrNull ?: "ERROR"
                val message = payload["message"]?.jsonPrimitive?.contentOrNull ?: ""
                failPairing(if (message.isBlank()) errorCode else "$errorCode: $message")
            }
        }
    }

    private fun failPairing(reason: String) {
        if (pairingDone) return
        pairingDone = true
        closePairingSocket()
        pairingEventsBus.tryEmit(PairingEvent.Failed(reason))
    }

    private fun closePairingSocket() {
        pairingSocket?.cancel()
        pairingSocket = null
        pairingClient?.dispatcher?.executorService?.shutdown()
        pairingClient = null
    }

    /** Reconnect with the persisted host on app start (once per VM lifetime). */
    fun autoConnect() {
        if (autoConnectDone) return
        autoConnectDone = true
        if (!authStore.isPaired()) return
        val host = uiPrefs.getString(KEY_HOST, null)
        val port = uiPrefs.getInt(KEY_PORT, 0)
        if (!host.isNullOrBlank() && port > 0) conn.connect(host, port)
    }

    /** Wipe credentials and the persisted host, then require re-pairing. */
    fun clearPairing() {
        conn.disconnect()
        pairingDone = true
        closePairingSocket()
        authStore.clear()
        uiPrefs.edit().clear().apply()
        pairingFpFlow.value = ""
    }

    // -- protocol event persistence -----------------------------------------

    private fun onProtocolEvent(event: ProtocolEvent) {
        when (event) {
            is ProtocolEvent.StateSnapshot -> viewModelScope.launch {
                runCatching { db.taskDao().upsertAll(event.tasks.map { it.toEntity() }) }
            }
            is ProtocolEvent.TaskEvent -> viewModelScope.launch {
                if (event.event == TaskEventKind.REMOVED) {
                    runCatching { db.taskDao().delete(event.taskId) }
                } else {
                    event.task?.let { runCatching { db.taskDao().upsert(it.toEntity()) } }
                }
            }
            is ProtocolEvent.Notification -> viewModelScope.launch {
                val entity = NotificationEntity(
                    id = event.notification.id,
                    createdUtc = event.notification.createdUtc,
                    taskId = event.notification.taskId,
                    category = event.notification.category.name,
                    title = event.notification.title,
                    body = event.notification.body,
                    read = false
                )
                runCatching { db.notificationDao().insert(entity) }
                postSystemNotification(entity.title, entity.body, highPriority = false)
            }
            is ProtocolEvent.ApprovalRequest -> viewModelScope.launch {
                val entity = NotificationEntity(
                    id = event.request.id,
                    createdUtc = event.request.createdUtc,
                    taskId = event.request.taskId,
                    category = NotificationCategory.APPROVAL_REQUIRED.name,
                    title = "Approval required",
                    body = event.request.question,
                    read = false
                )
                runCatching { db.notificationDao().insert(entity) }
                postSystemNotification(entity.title, entity.body, highPriority = true)
            }
            else -> Unit // auth lifecycle / acks / pongs are handled inside WorkspaceConnection
        }
    }

    private fun postSystemNotification(title: String, body: String, highPriority: Boolean) {
        val app = getApplication<android.app.Application>()
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(app, Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            return
        }
        val manager = app.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val intent: Intent = app.packageManager.getLaunchIntentForPackage(app.packageName) ?: return
        val pending = PendingIntent.getActivity(
            app, 0, intent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        val builder = NotificationCompat.Builder(
            app,
            if (highPriority) CyberApp.CHANNEL_APPROVALS else CyberApp.CHANNEL_TASKS
        )
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setAutoCancel(true)
            .setContentIntent(pending)
        if (highPriority) {
            builder.setPriority(NotificationCompat.PRIORITY_HIGH)
                .setCategory(NotificationCompat.CATEGORY_REMINDER)
        } else {
            builder.setPriority(NotificationCompat.PRIORITY_DEFAULT)
                .setCategory(NotificationCompat.CATEGORY_STATUS)
        }
        manager.notify(notifyIds.incrementAndGet(), builder.build())
    }

    private companion object {
        const val UI_PREFS_NAME = "cyber_workspace_ui"
        const val KEY_HOST = "host"
        const val KEY_PORT = "port"
        const val NOTIFICATION_LIMIT = 200
        const val PAIRING_TIMEOUT_MS = 25_000L
    }
}

/** Wire snapshot → Room cache row (pending approval kept as raw JSON). */
private fun TaskSnapshot.toEntity(): TaskEntity = TaskEntity(
    id = id,
    name = name,
    type = type,
    state = state.name,
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
    pendingApprovalJson = pendingApproval?.let { pa ->
        runCatching { ProtocolJson.encodeToString(PendingApproval.serializer(), pa) }.getOrNull()
    },
    updatedAt = System.currentTimeMillis()
)

@Composable
fun AppRoot(viewModel: AppViewModel) {
    val navController = rememberNavController()

    androidx.compose.runtime.LaunchedEffect(Unit) {
        viewModel.autoConnect()
    }

    NavHost(
        navController = navController,
        startDestination = if (viewModel.isPaired()) "dashboard" else "pairing"
    ) {
        composable("pairing") {
            PairingScreen(viewModel = viewModel, onPaired = {
                navController.navigate("dashboard") {
                    popUpTo("pairing") { inclusive = true }
                }
            })
        }
        composable("dashboard") {
            DashboardScreen(
                viewModel = viewModel,
                onOpenTask = { taskId -> navController.navigate("task/$taskId") },
                onOpenLocal = { navController.navigate("local") },
                onOpenNotifications = { navController.navigate("notifications") },
                onOpenSettings = { navController.navigate("settings") }
            )
        }
        composable("task/{taskId}") { entry ->
            val taskId = entry.arguments?.getString("taskId")
            if (taskId != null) {
                TaskDetailScreen(viewModel = viewModel, taskId = taskId, onBack = { navController.popBackStack() })
            }
        }
        composable("notifications") {
            NotificationsScreen(viewModel = viewModel, onOpenTask = { taskId ->
                navController.navigate("task/$taskId")
            })
        }
        composable("local") {
            LocalTasksScreen(viewModel = viewModel)
        }
        composable("settings") {
            SettingsScreen(viewModel = viewModel, onPairingNeeded = {
                navController.navigate("pairing") {
                    popUpTo(0) { inclusive = true }
                }
            })
        }
    }
}
