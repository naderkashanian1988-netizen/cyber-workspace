package com.cyberworkspace.app.data

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase

@Database(
    entities = [TaskEntity::class, NotificationEntity::class, LocalTaskEntity::class],
    version = 1,
    exportSchema = false
)
abstract class LocalDb : RoomDatabase() {

    abstract fun taskDao(): TaskDao
    abstract fun notificationDao(): NotificationDao
    abstract fun localTaskDao(): LocalTaskDao

    companion object {
        @Volatile
        private var instance: LocalDb? = null

        fun get(context: Context): LocalDb = instance ?: synchronized(this) {
            instance ?: Room.databaseBuilder(
                context.applicationContext,
                LocalDb::class.java,
                "cyber_workspace.db"
            )
                .fallbackToDestructiveMigration()
                .build()
                .also { instance = it }
        }
    }
}
