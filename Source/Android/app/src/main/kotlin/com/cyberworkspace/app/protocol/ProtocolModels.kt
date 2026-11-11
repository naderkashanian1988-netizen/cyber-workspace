package com.cyberworkspace.app.protocol

import java.time.Instant
import java.time.temporal.ChronoUnit
import java.util.UUID
import java.util.concurrent.atomic.AtomicLong
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * CYBER WORKSPACE — shared remote protocol v1 (Android mirror).
 *
 * Normative source: PROTOCOL.md; reference model:
 * Source/Windows/cyber_workspace/protocol/messages.py. Every wire string below matches
 * the contract EXACTLY. Clients must ignore unknown payload fields (§8.1) and
 * must treat unknown ops as BAD_REQUEST (§8.2) — handled by WorkspaceConnection.
 */
object Protocol {
    const val VERSION = 1

    /** Capabilities the host may announce in `auth_ok` (contract §3.2). */
    val CAPABILITIES = listOf("metrics", "logs", "commands", "approvals", "keep_awake")

    /** Subscribe topics (contract §3.1). */
    val TOPICS = listOf("state", "metrics", "notifications")
}

/** Operation names on the wire (contract §3.1 / §3.2). */
object Op {
    // client -> host
    const val PAIRING = "pairing"
    const val AUTH = "auth"
    const val SUBSCRIBE = "subscribe"
    const val UNSUBSCRIBE = "unsubscribe"
    const val GET_STATE = "get_state"
    const val GET_TASK = "get_task"
    const val GET_LOGS = "get_logs"
    const val COMMAND = "command"
    const val APPROVE = "approve"
    const val PING = "ping"
    // host -> client
    const val WELCOME = "welcome"
    const val PAIRING_OK = "pairing_ok"
    const val AUTH_OK = "auth_ok"
    const val AUTH_FAILED = "auth_failed"
    const val STATE_SNAPSHOT = "state_snapshot"
    const val TASK_EVENT = "task_event"
    const val METRICS = "metrics"
    const val NOTIFICATION = "notification"
    const val APPROVAL_REQUEST = "approval_request"
    const val COMMAND_ACK = "command_ack"
    const val ERROR = "error"
    const val PONG = "pong"
}

/** Wire error codes (contract §2, §7; mirrors protocol.messages.ErrorCode). */
object ErrorCodes {
    const val VERSION_MISMATCH = "VERSION_MISMATCH"
    const val NOT_AUTHENTICATED = "NOT_AUTHENTICATED"
    const val UNPAIRED = "UNPAIRED"
    const val INVALID_TOKEN = "INVALID_TOKEN"
    const val REVOKED = "REVOKED"
    const val SESSION_EXPIRED = "SESSION_EXPIRED"
    const val NOT_FOUND = "NOT_FOUND"
    const val INVALID_COMMAND = "INVALID_COMMAND"
    const val FORBIDDEN = "FORBIDDEN"
    const val RATE_LIMITED = "RATE_LIMITED"
    const val CONFLICT = "CONFLICT"
    const val BAD_REQUEST = "BAD_REQUEST"
    const val INTERNAL = "INTERNAL"
}

/** Event kinds carried by `task_event` (contract §3.2). */
object TaskEventKind {
    const val STATE_CHANGED = "state_changed"
    const val PROGRESS = "progress"
    const val METRICS = "metrics"
    const val REMOVED = "removed"
}

/** Approve decisions (contract §3.1, approve payload). */
const val DECISION_APPROVE = "approve"
const val DECISION_DENY = "deny"

/** Task states — closed set, mirrors Source/Windows/cyber_workspace/core/state.py (§3.3). */
@Serializable
enum class TaskState {
    RUNNING,
    WAITING_FOR_USER,
    NETWORK_WAITING,
    COMPLETED,
    ERROR,
    UNRESPONSIVE,
    PAUSED,
    UNKNOWN
}

/** Notification categories — closed set (§3.3). */
@Serializable
enum class NotificationCategory {
    @SerialName("approval_required") APPROVAL_REQUIRED,
    @SerialName("permission_required") PERMISSION_REQUIRED,
    @SerialName("task_error") TASK_ERROR,
    @SerialName("network_interruption") NETWORK_INTERRUPTION,
    @SerialName("task_completed") TASK_COMPLETED,
    @SerialName("task_crashed") TASK_CRASHED,
    @SerialName("task_unresponsive") TASK_UNRESPONSIVE,
    @SerialName("security_warning") SECURITY_WARNING,
    @SerialName("recovery_required") RECOVERY_REQUIRED,
    @SerialName("info") INFO
}

/**
 * Closed set of remote actions — the command-injection boundary (§3.1).
 * No free-form shell strings ever cross the wire.
 */
@Serializable
enum class CommandAction {
    @SerialName("pause") PAUSE,
    @SerialName("resume") RESUME,
    @SerialName("restart") RESTART,
    @SerialName("close") CLOSE,
    @SerialName("set_keep_awake") SET_KEEP_AWAKE
}

/** Task types (contract §3.3 TaskSnapshot.type). */
@Serializable
enum class TaskType {
    @SerialName("script") SCRIPT,
    @SerialName("terminal") TERMINAL,
    @SerialName("external") EXTERNAL,
    @SerialName("browser") BROWSER
}

/** Wire name of a CommandAction (SerialName values, for manual payload building). */
fun wireName(action: CommandAction): String = when (action) {
    CommandAction.PAUSE -> "pause"
    CommandAction.RESUME -> "resume"
    CommandAction.RESTART -> "restart"
    CommandAction.CLOSE -> "close"
    CommandAction.SET_KEEP_AWAKE -> "set_keep_awake"
}

/** Shared JSON codec: ignore unknown fields (§8.1), keep defaults on encode, drop nulls. */
val ProtocolJson: Json = Json {
    ignoreUnknownKeys = true
    encodeDefaults = true
    explicitNulls = false
}

/** One JSON object per message, both directions (§2). */
@Serializable
data class Envelope(
    val v: Int = Protocol.VERSION,
    val op: String,
    val seq: Int = 0,
    val ts: String = "",
    val payload: JsonObject = JsonObject(emptyMap())
)

/** Pending approval embedded in a TaskSnapshot (§3.3). */
@Serializable
data class PendingApproval(
    val id: String,
    val question: String,
    val options: List<String> = emptyList()
)

/**
 * TaskSnapshot — all fields per §3.3. Unavailable values are `null`, never
 * fabricated; timer fields are always present (defaults keep decoding lenient).
 */
@Serializable
data class TaskSnapshot(
    val id: String,
    val name: String,
    val type: String,
    val state: TaskState = TaskState.UNKNOWN,
    val reason: String? = null,
    @SerialName("active_ms") val activeMs: Long = 0,
    @SerialName("waiting_ms") val waitingMs: Long = 0,
    @SerialName("error_ms") val errorMs: Long = 0,
    @SerialName("paused_ms") val pausedMs: Long = 0,
    @SerialName("unknown_ms") val unknownMs: Long = 0,
    @SerialName("cpu_percent") val cpuPercent: Double? = null,
    @SerialName("ram_mb") val ramMb: Double? = null,
    @SerialName("last_activity_utc") val lastActivityUtc: String? = null,
    @SerialName("last_progress") val lastProgress: String? = null,
    @SerialName("keep_awake") val keepAwake: Boolean = false,
    val minimized: Boolean = false,
    val pid: Int? = null,
    val app: String? = null,
    @SerialName("created_utc") val createdUtc: String? = null,
    @SerialName("pending_approval") val pendingApproval: PendingApproval? = null
)

/** Network probe inside SystemStatus; latency is a TCP connect probe (§3.3). */
@Serializable
data class NetStatus(
    @SerialName("down_bps") val downBps: Double? = null,
    @SerialName("up_bps") val upBps: Double? = null,
    @SerialName("latency_ms") val latencyMs: Double? = null,
    val status: String = "UNKNOWN"
)

/** SystemStatus (§3.3). */
@Serializable
data class SystemStatus(
    @SerialName("cpu_percent") val cpuPercent: Double? = null,
    @SerialName("ram_percent") val ramPercent: Double? = null,
    @SerialName("ram_used_mb") val ramUsedMb: Double? = null,
    @SerialName("ram_total_mb") val ramTotalMb: Double? = null,
    val net: NetStatus = NetStatus(),
    @SerialName("keep_awake_active") val keepAwakeActive: Boolean = false,
    @SerialName("server_time") val serverTime: String? = null
)

@Serializable
data class NotificationAction(
    val id: String,
    val label: String
)

/** `notification` payload (§3.2). */
@Serializable
data class NotificationMsg(
    val id: String,
    @SerialName("created_utc") val createdUtc: String,
    val category: NotificationCategory,
    val title: String,
    val body: String,
    @SerialName("task_id") val taskId: String? = null,
    val actions: List<NotificationAction> = emptyList()
)

/** `approval_request` payload (§3.2). */
@Serializable
data class ApprovalRequestMsg(
    val id: String,
    @SerialName("created_utc") val createdUtc: String,
    @SerialName("task_id") val taskId: String,
    val question: String,
    val options: List<String> = emptyList()
)

/** `command_ack` payload (§3.2). */
@Serializable
data class CommandAckMsg(
    @SerialName("command_id") val commandId: String,
    val ok: Boolean,
    val error: String? = null
)

/** `welcome` payload (§3.2) — sent immediately on connect, before auth. */
@Serializable
data class WelcomeMsg(
    @SerialName("protocol_version") val protocolVersion: Int = Protocol.VERSION,
    @SerialName("server_version") val serverVersion: String = "",
    val fingerprint: String = "",
    @SerialName("pairing_available") val pairingAvailable: Boolean = false
) {
    companion object {
        const val UNKNOWN_DEVICE = "UNKNOWN_DEVICE"
    }
}

/** `auth_failed` payload (§3.2) — host closes the connection afterwards. */
@Serializable
data class AuthFailedMsg(
    val reason: String
) {
    companion object {
        const val REASON_INVALID_TOKEN = "INVALID_TOKEN"
        const val REASON_REVOKED = "REVOKED"
        const val REASON_SESSION_EXPIRED = "SESSION_EXPIRED"
        const val REASON_UNKNOWN_DEVICE = "UNKNOWN_DEVICE"
    }
}

/** `pairing_ok` payload (§3.2) — the only time the token travels. */
@Serializable
data class PairingOkMsg(
    @SerialName("device_id") val deviceId: String,
    val token: String,
    val permissions: List<String> = emptyList(),
    @SerialName("token_ttl_days") val tokenTtlDays: Int? = null
)

/** `auth_ok` payload (§3.2). */
@Serializable
data class AuthOkMsg(
    @SerialName("protocol_version") val protocolVersion: Int = Protocol.VERSION,
    @SerialName("server_version") val serverVersion: String = "",
    val capabilities: List<String> = emptyList(),
    val permissions: List<String> = emptyList(),
    @SerialName("token_ttl_days") val tokenTtlDays: Int? = null
)

/** `state_snapshot` payload (§3.2) — first one after subscribe is the baseline (§6). */
@Serializable
data class StateSnapshotMsg(
    val tasks: List<TaskSnapshot> = emptyList(),
    val system: SystemStatus = SystemStatus()
)

/** `task_event` payload (§3.2) — carries the full snapshot of the changed task. */
@Serializable
data class TaskEventMsg(
    @SerialName("task_id") val taskId: String,
    val event: String,
    val task: TaskSnapshot? = null,
    val extra: JsonObject? = null
)

/** Per-task live metrics inside `metrics` (§3.2) — advisory, may be dropped. */
@Serializable
data class TaskLiveMetrics(
    @SerialName("cpu_percent") val cpuPercent: Double? = null,
    @SerialName("ram_mb") val ramMb: Double? = null
)

/** `metrics` payload (§3.2). */
@Serializable
data class MetricsMsg(
    val system: SystemStatus = SystemStatus(),
    val tasks: Map<String, TaskLiveMetrics> = emptyMap()
)

// ---------------------------------------------------------------------------
// Builders (mirror protocol.messages.build/validate helpers)
// ---------------------------------------------------------------------------

private val seqCounter = AtomicLong(0)

/** ISO 8601 UTC timestamp with `Z` suffix, whole seconds (§2). */
fun nowUtc(): String = Instant.now().truncatedTo(ChronoUnit.SECONDS).toString()

/** Empty payload object — payload is never `null` (§2). */
fun emptyPayload(): JsonObject = JsonObject(emptyMap())

/**
 * Envelope builder. When `seq` is negative a client-side monotonic counter is
 * used; acks echo the seq back (§2).
 */
fun buildEnvelope(op: String, payload: JsonObject = emptyPayload(), seq: Int = -1): Envelope {
    val resolvedSeq = if (seq >= 0) seq else seqCounter.incrementAndGet().toInt()
    return Envelope(v = Protocol.VERSION, op = op, seq = resolvedSeq, ts = nowUtc(), payload = payload)
}

/** `command` payload builder (§3.1). `set_keep_awake` requires params {"enabled": bool}. */
fun buildCommand(action: CommandAction, taskId: String?, params: JsonObject = emptyPayload()): Envelope {
    val payload = buildJsonObject {
        put("command_id", UUID.randomUUID().toString())
        put("action", wireName(action))
        if (!taskId.isNullOrBlank()) put("task_id", taskId)
        put("params", params)
    }
    return buildEnvelope(Op.COMMAND, payload)
}

/** `approve` payload builder (§3.1); decision is "approve" or "deny", note optional. */
fun buildApprove(requestId: String, decision: String, note: String? = null): Envelope {
    val payload = buildJsonObject {
        put("command_id", UUID.randomUUID().toString())
        put("request_id", requestId)
        put("decision", decision)
        if (note != null) put("note", note)
    }
    return buildEnvelope(Op.APPROVE, payload)
}
