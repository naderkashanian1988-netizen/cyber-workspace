package com.cyberworkspace.app.data

import androidx.room.Entity
import androidx.room.PrimaryKey
import com.cyberworkspace.app.protocol.TaskState

/**
 * Room mirror of the host's TaskSnapshot (PROTOCOL.md §3.3). Timer fields are
 * in milliseconds, metrics are nullable because the host never fabricates
 * values. pendingApprovalJson keeps the raw pending_approval object so the UI
 * can render approval questions without a schema change.
 */
@Entity(tableName = "tasks")
data class TaskEntity(
    @PrimaryKey val id: String,
    val name: String,
    val type: String,
    val state: String,
    val reason: String?,
    val activeMs: Long = 0,
    val waitingMs: Long = 0,
    val errorMs: Long = 0,
    val pausedMs: Long = 0,
    val unknownMs: Long = 0,
    val cpuPercent: Double? = null,
    val ramMb: Double? = null,
    val lastActivityUtc: String? = null,
    val lastProgress: String? = null,
    val keepAwake: Boolean = false,
    val minimized: Boolean = false,
    val pendingApprovalJson: String? = null,
    val updatedAt: Long = 0
)

/** Persisted host notification (PROTOCOL.md §3.2 `notification`). */
@Entity(tableName = "notifications")
data class NotificationEntity(
    @PrimaryKey val id: String,
    val createdUtc: String,
    val taskId: String?,
    val category: String,
    val title: String,
    val body: String,
    val read: Boolean = false
)

/** User-defined monitor task that runs locally on this device. */
@Entity(tableName = "local_tasks")
data class LocalTaskEntity(
    @PrimaryKey val id: String,
    val name: String,
    val url: String,
    val intervalSec: Int = 60,
    val enabled: Boolean = true,
    val lastState: String = TaskState.UNKNOWN.name
)
