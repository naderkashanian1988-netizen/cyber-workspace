package com.cyberworkspace.app.net

import android.util.Log
import com.cyberworkspace.app.protocol.ApprovalRequestMsg
import com.cyberworkspace.app.protocol.AuthFailedMsg
import com.cyberworkspace.app.protocol.AuthOkMsg
import com.cyberworkspace.app.protocol.CommandAction
import com.cyberworkspace.app.protocol.CommandAckMsg
import com.cyberworkspace.app.protocol.DECISION_APPROVE
import com.cyberworkspace.app.protocol.Envelope
import com.cyberworkspace.app.protocol.ErrorCodes
import com.cyberworkspace.app.protocol.MetricsMsg
import com.cyberworkspace.app.protocol.NotificationMsg
import com.cyberworkspace.app.protocol.Op
import com.cyberworkspace.app.protocol.PairingOkMsg
import com.cyberworkspace.app.protocol.Protocol
import com.cyberworkspace.app.protocol.ProtocolJson
import com.cyberworkspace.app.protocol.StateSnapshotMsg
import com.cyberworkspace.app.protocol.SystemStatus
import com.cyberworkspace.app.protocol.TaskEventMsg
import com.cyberworkspace.app.protocol.TaskSnapshot
import com.cyberworkspace.app.protocol.WelcomeMsg
import com.cyberworkspace.app.protocol.buildApprove
import com.cyberworkspace.app.protocol.buildCommand
import com.cyberworkspace.app.protocol.buildEnvelope
import com.cyberworkspace.app.protocol.emptyPayload
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.serialization.decodeFromJsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.add
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicReference

/** Every parsed host message, delivered to collectors in order. */
sealed interface ProtocolEvent {
    /** `welcome` — arrives on connect, before auth (§3.2). */
    data class Welcome(val serverVersion: String, val fingerprint: String, val pairingAvailable: Boolean) : ProtocolEvent
    /** `pairing_ok` — credentials were persisted to AuthStore (the token never leaves here). */
    data class PairingOk(val deviceId: String, val permissions: List<String>) : ProtocolEvent
    /** `auth_ok`. */
    data class AuthOk(val serverVersion: String, val permissions: List<String>) : ProtocolEvent
    /** `auth_failed` — reasons: INVALID_TOKEN | REVOKED | SESSION_EXPIRED | UNKNOWN_DEVICE (§3.2). */
    data class AuthFailed(val reason: String) : ProtocolEvent
    /** `state_snapshot` — first after subscribe is the authoritative baseline (§6). */
    data class StateSnapshot(val tasks: List<TaskSnapshot>, val system: SystemStatus) : ProtocolEvent
    /** `task_event` — full snapshot of the changed task; must not be dropped (§6). */
    data class TaskEvent(val taskId: String, val event: String, val task: TaskSnapshot?) : ProtocolEvent
    /** `metrics` — advisory, may be dropped under backpressure (§6). */
    data class Metrics(val system: SystemStatus) : ProtocolEvent
    /** `notification`. */
    data class Notification(val notification: NotificationMsg) : ProtocolEvent
    /** `approval_request`. */
    data class ApprovalRequest(val request: ApprovalRequestMsg) : ProtocolEvent
    /** `command_ack`. */
    data class CommandAck(val ack: CommandAckMsg) : ProtocolEvent
    /** `error` or local protocol violation. */
    data class ProtocolError(val code: String, val message: String) : ProtocolEvent
    /** `pong`. */
    data class Pong(val ts: String) : ProtocolEvent
}

/** Connection lifecycle; PairingRequired means user action (pairing / re-pairing) is needed. */
sealed class ConnState {
    object Disconnected : ConnState()
    object Connecting : ConnState()
    object Authenticating : ConnState()
    object Connected : ConnState()
    data class PairingRequired(val reason: String) : ConnState()
}

/**
 * Single OkHttp WebSocket connection to the paired host over WSS with
 * certificate-fingerprint pinning (PROTOCOL.md §1). Flow: connect → welcome
 * (version check) → auth → auth_ok → subscribe {state, metrics, notifications}.
 * Auto-reconnects with exponential backoff 1s, 2s, 4s … capped at 30s, reset on
 * auth_ok. All message handling runs on one serial dispatcher; the socket and
 * lifecycle flags are atomics/synchronized, so the instance is thread-safe.
 */
class WorkspaceConnection(
    private val authStore: AuthStore,
    private val scope: CoroutineScope =
        CoroutineScope(SupervisorJob() + Dispatchers.IO.limitedParallelism(1)),
    baseClient: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .writeTimeout(10, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS) // host pushes indefinitely
        .pingInterval(30, TimeUnit.SECONDS)    // transport-level keepalive
        .build()
) {

    private val stateFlow = MutableStateFlow<ConnState>(ConnState.Disconnected)
    val state: StateFlow<ConnState> = stateFlow.asStateFlow()

    private val eventsFlow = MutableSharedFlow<ProtocolEvent>(
        extraBufferCapacity = 128,
        onBufferOverflow = BufferOverflow.DROP_OLDEST
    )
    val events: SharedFlow<ProtocolEvent> = eventsFlow.asSharedFlow()

    private val webSocketRef = AtomicReference<WebSocket?>(null)
    private val clientRef = AtomicReference<OkHttpClient?>(null)

    @Volatile private var wantConnected = false
    @Volatile private var host: String = ""
    @Volatile private var port: Int = 0
    @Volatile private var clientFingerprint: String = ""
    private val attempts = AtomicInteger(0)
    private var pingJob: Job? = null
    private var reconnectJob: Job? = null

    /** Open the (single) connection to wss://host:port. */
    @Synchronized
    fun connect(host: String, port: Int) {
        if (host.isBlank() || port <= 0) {
            emitError(ErrorCodes.BAD_REQUEST, "connect requires a host and a port")
            return
        }
        this.host = host.trim()
        this.port = port
        wantConnected = true
        attempts.set(0)
        openSocket()
    }

    /** Close the connection and stop reconnect / ping loops. */
    @Synchronized
    fun disconnect() {
        wantConnected = false
        cancelPing()
        reconnectJob?.cancel()
        reconnectJob = null
        webSocketRef.getAndSet(null)?.close(1000, "client disconnect")
        stateFlow.value = ConnState.Disconnected
    }

    /** Send a `command` (§3.1). Returns false if the socket is down. */
    fun sendCommand(action: CommandAction, taskId: String?, params: JsonObject = emptyPayload()): Boolean =
        sendEnvelope(buildCommand(action, taskId, params))

    /** Send an `approve` (§3.1); decision "approve" | "deny", optional note. */
    fun sendApprove(requestId: String, decision: String = DECISION_APPROVE, note: String? = null): Boolean =
        sendEnvelope(buildApprove(requestId, decision, note))

    /** Re-request the authoritative baseline after a gap (§6). */
    fun refreshState(): Boolean = sendEnvelope(buildEnvelope(Op.GET_STATE))

    // -- connection internals ---------------------------------------------

    private fun openSocket() {
        if (!wantConnected) return
        val fingerprint = authStore.fingerprint
        if (fingerprint.isBlank()) {
            // Never connect without TLS pinning (§1): pairing must happen first.
            stateFlow.value = ConnState.PairingRequired(REASON_NOT_PAIRED)
            return
        }
        if (webSocketRef.get() != null) return // one connection per device (§5.1)
        stateFlow.value = ConnState.Connecting
        val request = Request.Builder().url("wss://$host:$port/").build()
        val webSocket = clientFor(fingerprint).newWebSocket(request, listener)
        webSocketRef.set(webSocket)
    }

    /** Rebuild the client only when the pinned fingerprint changes. */
    private fun clientFor(fingerprint: String): OkHttpClient {
        val existing = clientRef.get()
        if (existing != null && clientFingerprint == fingerprint) return existing
        val (factory, trustManager) = sslSocketFactory(fingerprint)
        val client = baseClient.newBuilder()
            .sslSocketFactory(factory, trustManager)
            .hostnameVerifier(fingerprintHostnameVerifier())
            .build()
        clientFingerprint = fingerprint
        clientRef.set(client)
        return client
    }

    private val listener = object : WebSocketListener() {
        override fun onOpen(webSocket: WebSocket, response: Response) {
            stateFlow.value = ConnState.Authenticating
            sendAuth(webSocket)
        }

        override fun onMessage(webSocket: WebSocket, text: String) {
            scope.launch { handleMessage(text) }
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            webSocketRef.compareAndSet(webSocket, null)
            cancelPing()
            Log.w(TAG, "connection failure: ${t.message}")
            stateFlow.value = ConnState.Disconnected
            scheduleReconnect()
        }

        override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
            webSocketRef.compareAndSet(webSocket, null)
            cancelPing()
            Log.i(TAG, "connection closed: code=$code reason=$reason")
            stateFlow.value = ConnState.Disconnected
            scheduleReconnect()
        }
    }

    private fun sendAuth(webSocket: WebSocket) {
        val deviceId = authStore.deviceId
        val token = authStore.token
        if (deviceId.isBlank() || token.isBlank()) {
            wantConnected = false
            stateFlow.value = ConnState.PairingRequired(REASON_NOT_PAIRED)
            webSocket.close(1000, "not paired")
            return
        }
        val payload = buildJsonObject {
            put("device_id", deviceId)
            put("token", token)
        }
        webSocket.send(ProtocolJson.encodeToString(Envelope.serializer(), buildEnvelope(Op.AUTH, payload)))
    }

    private fun sendEnvelope(envelope: Envelope): Boolean {
        val webSocket = webSocketRef.get() ?: return false
        return webSocket.send(ProtocolJson.encodeToString(Envelope.serializer(), envelope))
    }

    private fun sendSubscribe() {
        val payload = buildJsonObject {
            put("topics", buildJsonArray { Protocol.TOPICS.forEach { add(jsonPrimitiveOf(it)) } })
        }
        sendEnvelope(buildEnvelope(Op.SUBSCRIBE, payload))
    }

    private fun jsonPrimitiveOf(value: String) = kotlinx.serialization.json.JsonPrimitive(value)

    private fun startPingLoop() {
        cancelPing()
        pingJob = scope.launch {
            while (isActive) {
                delay(PING_INTERVAL_MS) // host closes idle authed sessions after 15 min (§5.2)
                sendEnvelope(buildEnvelope(Op.PING))
            }
        }
    }

    private fun cancelPing() {
        pingJob?.cancel()
        pingJob = null
    }

    private fun scheduleReconnect() {
        if (!wantConnected) return
        if (reconnectJob?.isActive == true) return
        val attempt = attempts.getAndIncrement()
        val backoffMs = (BASE_BACKOFF_MS shl attempt.coerceAtMost(5)).coerceAtMost(MAX_BACKOFF_MS)
        reconnectJob = scope.launch {
            delay(backoffMs)
            synchronized(this@WorkspaceConnection) { openSocket() }
        }
    }

    // -- message dispatch --------------------------------------------------

    private fun handleMessage(text: String) {
        val root = try {
            ProtocolJson.parseToJsonElement(text).jsonObject
        } catch (e: Exception) {
            Log.w(TAG, "unparseable message: ${e.message}")
            emitError(ErrorCodes.BAD_REQUEST, "invalid message")
            return
        }
        val version = root["v"]?.jsonPrimitive?.intOrNull ?: -1
        if (version != Protocol.VERSION) {
            emitError(ErrorCodes.VERSION_MISMATCH, "unsupported protocol version $version")
            wantConnected = false
            webSocketRef.get()?.close(1002, "version mismatch")
            return
        }
        val op = root["op"]?.jsonPrimitive?.contentOrNull ?: run {
            emitError(ErrorCodes.BAD_REQUEST, "missing op")
            return
        }
        val payload = (root["payload"] as? JsonObject) ?: emptyPayload()
        when (op) {
            Op.WELCOME -> onWelcome(payload)
            Op.PAIRING_OK -> onPairingOk(payload)
            Op.AUTH_OK -> onAuthOk(payload)
            Op.AUTH_FAILED -> onAuthFailed(payload)
            Op.STATE_SNAPSHOT -> onStateSnapshot(payload)
            Op.TASK_EVENT -> onTaskEvent(payload)
            Op.METRICS -> onMetrics(payload)
            Op.NOTIFICATION -> onNotification(payload)
            Op.APPROVAL_REQUEST -> onApprovalRequest(payload)
            Op.COMMAND_ACK -> onCommandAck(payload)
            Op.ERROR -> onError(payload)
            Op.PONG -> onPong(payload)
            else -> {
                // §8.2: unknown op = log + ignore, never fatal.
                Log.w(TAG, "unknown op ignored: $op")
                emitError(ErrorCodes.BAD_REQUEST, "unknown op $op")
            }
        }
    }

    private fun onWelcome(payload: JsonObject) {
        val welcome = decode<WelcomeMsg>(payload) ?: return
        if (welcome.protocolVersion != Protocol.VERSION) {
            Log.e(TAG, "server speaks protocol ${welcome.protocolVersion}, we speak ${Protocol.VERSION}")
            emitError(ErrorCodes.VERSION_MISMATCH, "server protocol ${welcome.protocolVersion}")
            wantConnected = false
            webSocketRef.get()?.close(1002, "version mismatch")
            return
        }
        eventsFlow.tryEmit(
            ProtocolEvent.Welcome(welcome.serverVersion, welcome.fingerprint, welcome.pairingAvailable)
        )
    }

    private fun onPairingOk(payload: JsonObject) {
        val ok = decode<PairingOkMsg>(payload) ?: return
        authStore.save(ok.deviceId, ok.token, authStore.fingerprint, ok.permissions)
        eventsFlow.tryEmit(ProtocolEvent.PairingOk(ok.deviceId, ok.permissions))
        // Authenticate immediately with the fresh credentials on the same socket.
        webSocketRef.get()?.let { sendAuth(it) }
    }

    private fun onAuthOk(payload: JsonObject) {
        val ok = decode<AuthOkMsg>(payload) ?: return
        attempts.set(0) // backoff resets on auth_ok
        stateFlow.value = ConnState.Connected
        eventsFlow.tryEmit(ProtocolEvent.AuthOk(ok.serverVersion, ok.permissions))
        sendSubscribe()
        startPingLoop()
    }

    private fun onAuthFailed(payload: JsonObject) {
        val failed = decode<AuthFailedMsg>(payload) ?: return
        // §5.3: INVALID_TOKEN / REVOKED / SESSION_EXPIRED → close, do not hammer reconnects.
        wantConnected = false
        stateFlow.value = ConnState.PairingRequired(failed.reason)
        eventsFlow.tryEmit(ProtocolEvent.AuthFailed(failed.reason))
    }

    private fun onStateSnapshot(payload: JsonObject) {
        val snapshot = decode<StateSnapshotMsg>(payload) ?: return
        eventsFlow.tryEmit(ProtocolEvent.StateSnapshot(snapshot.tasks, snapshot.system))
    }

    private fun onTaskEvent(payload: JsonObject) {
        val event = decode<TaskEventMsg>(payload) ?: return
        eventsFlow.tryEmit(ProtocolEvent.TaskEvent(event.taskId, event.event, event.task))
    }

    private fun onMetrics(payload: JsonObject) {
        val metrics = decode<MetricsMsg>(payload) ?: return
        eventsFlow.tryEmit(ProtocolEvent.Metrics(metrics.system))
    }

    private fun onNotification(payload: JsonObject) {
        val notification = decode<NotificationMsg>(payload) ?: return
        eventsFlow.tryEmit(ProtocolEvent.Notification(notification))
    }

    private fun onApprovalRequest(payload: JsonObject) {
        val request = decode<ApprovalRequestMsg>(payload) ?: return
        eventsFlow.tryEmit(ProtocolEvent.ApprovalRequest(request))
    }

    private fun onCommandAck(payload: JsonObject) {
        val ack = decode<CommandAckMsg>(payload) ?: return
        eventsFlow.tryEmit(ProtocolEvent.CommandAck(ack))
    }

    private fun onError(payload: JsonObject) {
        val code = payload["code"]?.jsonPrimitive?.contentOrNull ?: ErrorCodes.INTERNAL
        val message = payload["message"]?.jsonPrimitive?.contentOrNull ?: ""
        eventsFlow.tryEmit(ProtocolEvent.ProtocolError(code, message))
    }

    private fun onPong(payload: JsonObject) {
        eventsFlow.tryEmit(ProtocolEvent.Pong(payload["ts"]?.jsonPrimitive?.contentOrNull ?: ""))
    }

    private inline fun <reified T : Any> decode(payload: JsonObject): T? = try {
        ProtocolJson.decodeFromJsonElement(payload)
    } catch (e: Exception) {
        Log.w(TAG, "malformed payload: ${e.message}")
        null
    }

    private fun emitError(code: String, message: String) {
        eventsFlow.tryEmit(ProtocolEvent.ProtocolError(code, message))
    }

    private companion object {
        const val TAG = "WorkspaceConnection"
        const val REASON_NOT_PAIRED = "unpaired"
        const val BASE_BACKOFF_MS = 1_000L
        const val MAX_BACKOFF_MS = 30_000L
        const val PING_INTERVAL_MS = 5 * 60_000L
    }
}
