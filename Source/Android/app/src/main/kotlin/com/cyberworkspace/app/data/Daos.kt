package com.cyberworkspace.app.data

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.Query
import androidx.room.Upsert
import kotlinx.coroutines.flow.Flow

@Dao
interface TaskDao {
    @Upsert
    suspend fun upsert(task: TaskEntity)

    @Upsert
    suspend fun upsertAll(tasks: List<TaskEntity>)

    @Query("SELECT * FROM tasks ORDER BY name COLLATE NOCASE")
    fun observeAll(): Flow<List<TaskEntity>>

    @Query("SELECT * FROM tasks WHERE id = :id")
    suspend fun get(id: String): TaskEntity?

    @Query("DELETE FROM tasks WHERE id = :id")
    suspend fun delete(id: String)

    @Query("DELETE FROM tasks")
    suspend fun clear()
}

@Dao
interface NotificationDao {
    @Insert
    suspend fun insert(notification: NotificationEntity)

    @Query("SELECT * FROM notifications ORDER BY createdUtc DESC LIMIT :limit")
    fun recent(limit: Int): Flow<List<NotificationEntity>>

    @Query("UPDATE notifications SET read = 1 WHERE id = :id")
    suspend fun markRead(id: String)

    @Query("UPDATE notifications SET read = 1")
    suspend fun markAllRead()

    @Query("SELECT COUNT(*) FROM notifications WHERE read = 0")
    fun unreadCount(): Flow<Int>
}

@Dao
interface LocalTaskDao {
    @Upsert
    suspend fun upsert(task: LocalTaskEntity)

    @Upsert
    suspend fun upsertAll(tasks: List<LocalTaskEntity>)

    @Query("SELECT * FROM local_tasks ORDER BY name COLLATE NOCASE")
    fun observeAll(): Flow<List<LocalTaskEntity>>

    @Query("SELECT * FROM local_tasks WHERE id = :id")
    suspend fun get(id: String): LocalTaskEntity?

    @Query("SELECT * FROM local_tasks WHERE enabled = 1")
    suspend fun enabledTasks(): List<LocalTaskEntity>

    @Query("DELETE FROM local_tasks WHERE id = :id")
    suspend fun delete(id: String)

    @Query("UPDATE local_tasks SET lastState = :state WHERE id = :id")
    suspend fun updateLastState(id: String, state: String)
}
