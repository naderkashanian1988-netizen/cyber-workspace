package com.cyberworkspace.app.tasks

import com.cyberworkspace.app.protocol.TaskState
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.IOException
import java.util.concurrent.TimeUnit

/** Outcome of a single monitor check. */
data class UrlCheckResult(
    val state: TaskState,
    val reason: String?,
    val progress: String?
)

/**
 * Periodic HTTPS monitor with evidence-based state transitions (honest
 * reporting — a state is never changed without a reason):
 *
 *  - transport failure (IOException) -> NETWORK_WAITING, reason = exception
 *    class name; the interval is charged to the TriTimer `waiting` bucket;
 *  - HTTP status >= 400              -> ERROR, reason = the status code;
 *  - success (2xx/3xx)               -> COMPLETED with progress evidence;
 *    the timer freezes (Windows semantics: completed run is terminal) and the
 *    next cycle restarts it with a fresh ACTIVE segment, totals accumulate.
 *
 * The engine owns the schedule (intervalSec) and calls [runCycle] once per
 * cycle so it can interpose Doze checks.
 */
class UrlMonitorTask(
    val id: String,
    val name: String,
    val url: String,
    val intervalSec: Int = 60,
    private val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS)
        .build(),
    private val timer: TriTimer = TriTimer(),
    private val onTransition: (state: TaskState, reason: String?, progress: String?) -> Unit = { _, _, _ -> }
) {

    private var lastState: TaskState = TaskState.UNKNOWN

    val totals: TimerTotals
        get() = timer.totals()

    fun isFrozen(): Boolean = timer.isFrozen()

    fun lastKnownState(): TaskState = lastState

    /**
     * Charge the current interval to UNKNOWN (device idle / Doze suspended us,
     * so the interval could not be verified — never reported as active work).
     */
    fun markUnknownIdle(reason: String) {
        timer.transitionTo(TaskState.UNKNOWN)
        lastState = TaskState.UNKNOWN
        onTransition(TaskState.UNKNOWN, reason, null)
    }

    /** Perform one evidence-gathering check. Blocking IO is moved off the caller. */
    suspend fun runCycle(): UrlCheckResult {
        beginCycle()
        return withContext(Dispatchers.IO) {
            val request = Request.Builder().url(url).GET().build()
            try {
                client.newCall(request).execute().use { response ->
                    val code = response.code
                    if (code >= 400) {
                        finish(TaskState.ERROR, "HTTP $code", "HTTP $code (${response.message})")
                    } else {
                        val bytes = response.body?.contentLength()
                        val detail = if (bytes != null && bytes >= 0) "HTTP $code, $bytes bytes" else "HTTP $code"
                        finish(TaskState.COMPLETED, "HTTP $code ok", detail)
                    }
                }
            } catch (e: IOException) {
                finish(TaskState.NETWORK_WAITING, e.javaClass.simpleName, null)
            }
        }
    }

    // -- internals ----------------------------------------------------------

    private fun beginCycle() {
        if (timer.isFrozen()) {
            // Previous run completed; restart opens a new ACTIVE run segment.
            timer.restart()
            lastState = TaskState.RUNNING
            onTransition(TaskState.RUNNING, "cycle started", null)
            return
        }
        if (lastState != TaskState.RUNNING) {
            timer.transitionTo(TaskState.RUNNING)
            lastState = TaskState.RUNNING
            onTransition(TaskState.RUNNING, "cycle started", null)
        }
    }

    private fun finish(state: TaskState, reason: String, progress: String?): UrlCheckResult {
        timer.transitionTo(state)
        lastState = state
        onTransition(state, reason, progress)
        return UrlCheckResult(state, reason, progress)
    }
}
