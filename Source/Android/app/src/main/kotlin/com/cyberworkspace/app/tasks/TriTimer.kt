package com.cyberworkspace.app.tasks

import com.cyberworkspace.app.protocol.TaskState
import java.util.concurrent.locks.ReentrantLock
import kotlin.concurrent.withLock

/**
 * Time-accounting buckets — mirrors Source/Windows/cyber_workspace/core/state.py
 * SegmentKind. `unknown` is NEVER merged into active work.
 */
enum class Bucket(val wire: String) {
    ACTIVE("active"),
    WAITING("waiting"),
    ERROR("error"),
    PAUSED("paused"),
    UNKNOWN("unknown")
}

/** Which bucket each TaskState charges while the task sits in it (STATE_SEGMENT map). */
fun bucketFor(state: TaskState): Bucket = when (state) {
    TaskState.RUNNING -> Bucket.ACTIVE
    TaskState.WAITING_FOR_USER -> Bucket.WAITING
    TaskState.NETWORK_WAITING -> Bucket.WAITING
    TaskState.COMPLETED -> Bucket.ACTIVE // closed immediately; bucket irrelevant once frozen
    TaskState.ERROR -> Bucket.ERROR
    TaskState.UNRESPONSIVE -> Bucket.ERROR
    TaskState.PAUSED -> Bucket.PAUSED
    TaskState.UNKNOWN -> Bucket.UNKNOWN
}

data class TimerTotals(
    val activeMs: Long = 0,
    val waitingMs: Long = 0,
    val errorMs: Long = 0,
    val pausedMs: Long = 0,
    val unknownMs: Long = 0
)

/**
 * In-memory per-task tri-timer, same semantics as the Windows side
 * (Source/Windows/cyber_workspace/core/timers.py):
 *
 *  - Segments are wall-clock UTC (epoch ms); the live segment uses monotonic
 *    elapsed only for the current open interval, exactly like the Windows
 *    implementation (end = start_utc + monotonic elapsed).
 *  - Exactly ONE segment is open at any time. [transitionTo] closes the open
 *    segment and opens the next one in the same call — no gaps, no overlap.
 *  - [totals] sums the closed segments plus the live open segment.
 *  - [freeze] (COMPLETED) closes the open segment; totals become final.
 *  - [recoverOrphans] closes segments left open by a crashed/suspended run at
 *    a persisted cutoff so dead time is not stretched to "now".
 *  - UNKNOWN never folds into ACTIVE: it is its own bucket forever.
 */
class TriTimer(private val nowMs: () -> Long = System::currentTimeMillis) {

    private val lock = ReentrantLock()

    private class Segment(val kind: Bucket, val startWallMs: Long, val startMonoMs: Long)

    private var open: Segment? = null
    private var frozenFlag = false
    private val closedTotals = mutableMapOf<Bucket, Long>()

    fun isFrozen(): Boolean = lock.withLock { frozenFlag }

    fun openKind(): Bucket? = lock.withLock { open?.kind }

    /** Elapsed ms of the currently open segment (live display), 0 when frozen. */
    fun liveElapsedMs(): Long = lock.withLock {
        open?.let { mono() - it.startMonoMs } ?: 0L
    }

    /** Close the open segment and open the one matching `state`. Called on every state change. */
    fun transitionTo(state: TaskState) {
        lock.withLock {
            if (frozenFlag) return
            closeOpen()
            if (state == TaskState.COMPLETED) {
                frozenFlag = true // completed: nothing stays open
                return
            }
            open = Segment(bucketFor(state), nowMs(), mono())
        }
    }

    /** Ensure the open segment is of `kind`; switch by closing + opening. */
    fun setBucket(kind: Bucket) {
        lock.withLock {
            if (frozenFlag) return
            val current = open
            if (current != null && current.kind == kind) return
            closeOpen()
            open = Segment(kind, nowMs(), mono())
        }
    }

    /** Freeze final totals (task COMPLETED). */
    fun freeze() {
        lock.withLock {
            closeOpen()
            frozenFlag = true
        }
    }

    /**
     * Windows treats COMPLETED as terminal for a run and opens a new run on
     * restart. Local monitors are long-lived, so this unfreezes the timer and
     * opens a fresh ACTIVE segment while accumulated closed totals are kept.
     */
    fun restart() {
        lock.withLock {
            frozenFlag = false
            open = Segment(Bucket.ACTIVE, nowMs(), mono())
        }
    }

    /**
     * Close a leftover open segment (previous crashed/suspended run) at
     * `cutoffMs` — the last persisted seen time — instead of stretching the
     * dead interval to now. Returns how many orphans were closed.
     */
    fun recoverOrphans(cutoffMs: Long): Int {
        lock.withLock {
            if (open == null) return 0
            closeOpenAt(cutoffMs)
            open = null
            frozenFlag = false
            return 1
        }
    }

    /** Closed segments + live open segment, per bucket. */
    fun totals(): TimerTotals {
        lock.withLock {
            var active = closedTotals[Bucket.ACTIVE] ?: 0L
            var waiting = closedTotals[Bucket.WAITING] ?: 0L
            var error = closedTotals[Bucket.ERROR] ?: 0L
            var paused = closedTotals[Bucket.PAUSED] ?: 0L
            var unknown = closedTotals[Bucket.UNKNOWN] ?: 0L
            open?.let { seg ->
                val elapsedMs = mono() - seg.startMonoMs
                when (seg.kind) {
                    Bucket.ACTIVE -> active += elapsedMs
                    Bucket.WAITING -> waiting += elapsedMs
                    Bucket.ERROR -> error += elapsedMs
                    Bucket.PAUSED -> paused += elapsedMs
                    Bucket.UNKNOWN -> unknown += elapsedMs
                }
            }
            return TimerTotals(active, waiting, error, paused, unknown)
        }
    }

    // -- internals (call with lock held) ----------------------------------

    private fun closeOpen() {
        val seg = open ?: return
        closeSegment(seg, seg.startWallMs + (mono() - seg.startMonoMs))
        open = null
    }

    private fun closeOpenAt(endWallMs: Long) {
        val seg = open ?: return
        closeSegment(seg, endWallMs.coerceAtLeast(seg.startWallMs))
        open = null
    }

    private fun closeSegment(seg: Segment, endWallMs: Long) {
        val durationMs = (endWallMs - seg.startWallMs).coerceAtLeast(0)
        closedTotals[seg.kind] = (closedTotals[seg.kind] ?: 0L) + durationMs
    }

    private fun mono(): Long = System.nanoTime() / 1_000_000
}
