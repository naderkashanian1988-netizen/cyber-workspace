package com.cyberworkspace.app.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.IBinder
import androidx.core.app.NotificationCompat
import com.cyberworkspace.app.data.LocalDb
import com.cyberworkspace.app.protocol.TaskState
import com.cyberworkspace.app.tasks.LocalTaskEngine
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch

/**
 * Foreground service (type dataSync) that keeps [LocalTaskEngine] running so
 * local URL monitors keep ticking in the background. The "tasks" notification
 * channel carries the persistent status notification showing how many tasks
 * are currently running.
 */
class MonitorService : Service() {

    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var engine: LocalTaskEngine? = null
    private var watchJob: Job? = null

    override fun onCreate() {
        super.onCreate()
        createChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val eng = engine ?: LocalTaskEngine(this, LocalDb.get(this).localTaskDao())
            .also { engine = it }
        startInForeground(eng.runningCount())
        eng.start()
        watchJob?.cancel()
        watchJob = serviceScope.launch {
            eng.runtimes.collectLatest { runtimes ->
                val running = runtimes.count { it.state == TaskState.RUNNING }
                startInForeground(running)
            }
        }
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        watchJob?.cancel()
        watchJob = null
        engine?.stopAll()
        engine = null
        stopForeground(STOP_FOREGROUND_REMOVE)
        serviceScope.cancel()
        super.onDestroy()
    }

    // -- internals ----------------------------------------------------------

    private fun startInForeground(runningCount: Int) {
        startForeground(
            NOTIFICATION_ID,
            buildNotification(runningCount),
            ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC
        )
    }

    private fun buildNotification(runningCount: Int): Notification {
        val total = engine?.tasks?.value?.size ?: 0
        val text = when {
            runningCount == 0 -> "No tasks running"
            total > 0 -> "$runningCount of $total tasks running"
            else -> "$runningCount tasks running"
        }
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(applicationInfo.icon)
            .setContentTitle("Cyber Workspace")
            .setContentText(text)
            .setCategory(Notification.CATEGORY_SERVICE)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setContentIntent(launchIntent())
            .build()
    }

    private fun launchIntent(): PendingIntent? {
        val intent = packageManager.getLaunchIntentForPackage(packageName) ?: return null
        return PendingIntent.getActivity(this, 0, intent, PendingIntent.FLAG_IMMUTABLE)
    }

    private fun createChannel() {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val channel = NotificationChannel(CHANNEL_ID, "Tasks", NotificationManager.IMPORTANCE_LOW)
        channel.description = "Local task monitoring status"
        manager.createNotificationChannel(channel)
    }

    private companion object {
        const val CHANNEL_ID = "tasks"
        const val NOTIFICATION_ID = 1
    }
}
