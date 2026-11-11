package com.cyberworkspace.app

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context

/**
 * Application entry point. Creates the two notification channels up front so
 * that notifications posted by the UI layer and MonitorService land on the
 * right channel on every supported API level. Channel ids are public so the
 * rest of the app posts without re-declaring them.
 */
class CyberApp : Application() {

    override fun onCreate() {
        super.onCreate()
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.createNotificationChannel(tasksChannel())
        manager.createNotificationChannel(approvalsChannel())
    }

    private fun tasksChannel(): NotificationChannel =
        NotificationChannel(CHANNEL_TASKS, "Tasks", NotificationManager.IMPORTANCE_DEFAULT).apply {
            description = "Task state changes, completions and errors from the host"
        }

    private fun approvalsChannel(): NotificationChannel =
        NotificationChannel(CHANNEL_APPROVALS, "Approvals", NotificationManager.IMPORTANCE_HIGH).apply {
            description = "Approval requests that need an immediate decision"
        }

    companion object {
        const val CHANNEL_TASKS = "tasks"
        const val CHANNEL_APPROVALS = "approvals"
    }
}
