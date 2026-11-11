package com.cyberworkspace.app.tasks

import android.content.Context
import android.os.PowerManager
import com.cyberworkspace.app.data.LocalTaskDao
import com.cyberworkspace.app.data.LocalTaskEntity
import com.cyberworkspace.app.protocol.TaskState
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** Runtime view of one local task: entity + live tri-timer totals. */
data class LocalTaskRuntime(
    val task: LocalTaskEntity,
    val state: TaskState,
    val reason: String?,
    val progress: String?,
    val totals: TimerTotals
)

/**
 * Runs the user-defined local monitor tasks ([LocalTaskEntity]) as coroutines.
 *
 * Honest reporting rule: before every cycle, if the device is in Doze / App
 * Standby (PowerManager.isDeviceIdleMode) the cycle is skipped and that
 * interval is charged to UNKNOWN via [UrlMonitorTask.markUnknownIdle] —
 * work that could not be verified is never reported as active.
 *
 * Exposes the persisted task list and live runtimes as StateFlows plus
 * start/stop/pause controls. The Room table is the single source of truth;
 * edits flow back through LocalTaskDao.observeAll().
 */
class LocalTaskEngine(
    context: Context,
    private val dao: LocalTaskDao,
    private val scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
) {

    private val powerManager =
        context.applicationContext.getSystemService(Context.POWER_SERVICE) as PowerManager

    private val lock = Any()
    private val entitiesById = HashMap<String, LocalTaskEntity>()
    private val jobs = HashMap<String, Job>()
    private val timers = HashMap<String, TriTimer>()
    private val runtimesMap = HashMap<String, LocalTaskRuntime>()
    private var observerJob: Job? = null

    private val tasksFlow = MutableStateFlow<List<LocalTaskEntity>>(emptyList())
    val tasks: StateFlow<List<LocalTaskEntity>> = tasksFlow.asStateFlow()

    private val runtimesFlow = MutableStateFlow<List<LocalTaskRuntime>>(emptyList())
    val runtimes: StateFlow<List<LocalTaskRuntime>> = runtimesFlow.asStateFlow()

    /** Start the engine: observe the task table and run every enabled task. */
    fun start() {
        synchronized(lock) {
            if (observerJob?.isActive == true) return
            observerJob = scope.launch {
                dao.observeAll().collect { entities -> onEntitiesUpdated(entities) }
            }
        }
    }

    /** Stop everything: cancel all task loops and the table observer. */
    fun stopAll() {
        synchronized(lock) {
            observerJob?.cancel()
            observerJob = null
            jobs.values.forEach { it.cancel() }
            jobs.clear()
            timers.clear()
            runtimesMap.clear()
            publishRuntimes()
        }
    }

    /** Cancel one task's loop and mark it PAUSED (charged to the paused bucket). */
    fun pause(taskId: String) {
        synchronized(lock) {
            jobs.remove(taskId)?.cancel()
            val timer = timers.getOrPut(taskId) { TriTimer() }
            timer.transitionTo(TaskState.PAUSED)
            publishRuntime(taskId, TaskState.PAUSED, "paused by user", null)
        }
    }

    /** Relaunch a paused task's loop. */
    fun resume(taskId: String) {
        synchronized(lock) {
            entitiesById[taskId]?.let { if (it.enabled) launchTask(it) }
        }
    }

    /** Start (or restart) a single task loop. */
    fun startTask(taskId: String) {
        synchronized(lock) {
            entitiesById[taskId]?.let { if (it.enabled) launchTask(it) }
        }
    }

    /** Stop a single task and drop its runtime view. */
    fun stopTask(taskId: String) {
        synchronized(lock) {
            jobs.remove(taskId)?.cancel()
            timers.remove(taskId)
            runtimesMap.remove(taskId)
            publishRuntimes()
        }
    }

    /** Number of tasks currently charging the ACTIVE bucket. */
    fun runningCount(): Int = runtimesFlow.value.count { it.state == TaskState.RUNNING }

    // -- internals ----------------------------------------------------------

    private fun onEntitiesUpdated(entities: List<LocalTaskEntity>) {
        synchronized(lock) {
            val previous = HashMap(entitiesById)
            entitiesById.clear()
            entities.forEach { entitiesById[it.id] = it }
            tasksFlow.value = entities
            val enabledIds = entities.filter { it.enabled }.map { it.id }.toSet()
            (jobs.keys - enabledIds).forEach { id ->
                jobs.remove(id)?.cancel()
                timers.remove(id)
                runtimesMap.remove(id)
            }
            entities.filter { it.enabled }.forEach { entity ->
                if (!jobs.containsKey(entity.id) || previous[entity.id] != entity) {
                    launchTask(entity)
                }
            }
            publishRuntimes()
        }
    }

    private fun launchTask(entity: LocalTaskEntity) {
        jobs.remove(entity.id)?.cancel()
        val timer = timers.getOrPut(entity.id) { TriTimer() }
        val monitor = UrlMonitorTask(
            id = entity.id,
            name = entity.name,
            url = entity.url,
            intervalSec = entity.intervalSec,
            timer = timer,
            onTransition = { state, reason, progress ->
                persistState(entity.id, state)
                publishRuntime(entity.id, state, reason, progress)
            }
        )
        jobs[entity.id] = scope.launch { taskLoop(monitor) }
    }

    private suspend fun taskLoop(monitor: UrlMonitorTask) {
        val intervalMs = monitor.intervalSec.coerceIn(5, 3600) * 1000L
        while (currentCoroutineContext().isActive) {
            if (powerManager.isDeviceIdleMode) {
                // Doze / App Standby: report the interval as UNKNOWN, not active.
                monitor.markUnknownIdle("device idle (doze) — interval could not be verified")
            } else {
                monitor.runCycle()
            }
            delay(intervalMs)
        }
    }

    private fun persistState(taskId: String, state: TaskState) {
        scope.launch { runCatching { dao.updateLastState(taskId, state.name) } }
    }

    private fun publishRuntime(taskId: String, state: TaskState, reason: String?, progress: String?) {
        synchronized(lock) {
            val entity = entitiesById[taskId] ?: return
            val timer = timers.getOrPut(taskId) { TriTimer() }
            runtimesMap[taskId] = LocalTaskRuntime(entity, state, reason, progress, timer.totals())
            publishRuntimes()
        }
    }

    private fun publishRuntimes() {
        runtimesFlow.value = runtimesMap.values.toList().sortedBy { it.task.name }
    }
}
