package com.cyberworkspace.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

/**
 * Self-contained tests for the CYBER WORKSPACE TriTimer contract.
 *
 * The production TriTimer lives in another source set, so this file ships a
 * tiny behaviour clone instead of importing it: five time buckets (ACTIVE,
 * WAITING, ERROR, PAUSED, UNKNOWN), wall-clock segments driven by an injected
 * clock lambda, at most one open segment at a time, a freeze switch, and an
 * orphan-recovery pass for segments left open by a process crash.
 */
class TriTimerTest {

    enum class Bucket { ACTIVE, WAITING, ERROR, PAUSED, UNKNOWN }

    /** One wall-clock span. `end == null` means the segment is still open. */
    class Segment(val bucket: Bucket, val start: Long, var end: Long?) {
        val isOpen: Boolean get() = end == null
    }

    private class TriTimer(private val clock: () -> Long) {

        private val totals = LongArray(Bucket.values().size)
        private val recorded = mutableListOf<Segment>()
        private var open: Segment? = null
        private var frozen = false

        val segments: List<Segment> get() = recorded.toList()

        fun activeMs(): Long = totals[Bucket.ACTIVE.ordinal]
        fun waitingMs(): Long = totals[Bucket.WAITING.ordinal]
        fun errorMs(): Long = totals[Bucket.ERROR.ordinal]
        fun pausedMs(): Long = totals[Bucket.PAUSED.ordinal]
        fun unknownMs(): Long = totals[Bucket.UNKNOWN.ordinal]
        fun totalMs(): Long = totals.sum()
        fun isFrozen(): Boolean = frozen

        /** Closes any open segment and opens a new one for [bucket] at now(). */
        fun start(bucket: Bucket) {
            check(!frozen) { "TriTimer is frozen; unfreeze before opening a new segment" }
            closeOpen(clock())
            val segment = Segment(bucket, clock(), null)
            recorded.add(segment)
            open = segment
        }

        /** Closes the open segment at now(); a no-op when nothing is open. */
        fun close() {
            closeOpen(clock())
        }

        /** Banks the open segment at now() and stops all accumulation. */
        fun freeze() {
            closeOpen(clock())
            frozen = true
        }

        fun unfreeze() {
            frozen = false
        }

        /**
         * Closes a segment left open by a crash at [cutoff] instead of the
         * current wall clock, exactly once; later calls are no-ops.
         */
        fun recoverOrphans(cutoff: Long) {
            val orphan = open ?: return
            if (orphan.end == null) {
                val closedAt = cutoff.coerceAtLeast(orphan.start)
                orphan.end = closedAt
                totals[orphan.bucket.ordinal] += closedAt - orphan.start
            }
            open = null
        }

        private fun closeOpen(at: Long) {
            val segment = open ?: return
            if (segment.end == null) {
                segment.end = at
                totals[segment.bucket.ordinal] += (at - segment.start).coerceAtLeast(0)
            }
            open = null
        }
    }

    @Test
    fun `active then waiting then error accumulate into their own buckets`() {
        var now = 0L
        val timer = TriTimer { now }

        timer.start(Bucket.ACTIVE)
        now = 1_000
        timer.start(Bucket.WAITING)
        now = 2_500
        timer.start(Bucket.ERROR)
        assertEquals(1, timer.segments.count { it.isOpen }) // one open segment max
        now = 4_000
        timer.close()
        assertTrue(timer.segments.none { it.isOpen })

        assertEquals(1_000L, timer.activeMs())
        assertEquals(1_500L, timer.waitingMs())
        assertEquals(1_500L, timer.errorMs())
        assertEquals(0L, timer.pausedMs())
        assertEquals(0L, timer.unknownMs())
        assertEquals(4_000L, timer.totalMs())
    }

    @Test
    fun `unknown time is never merged into active`() {
        var now = 0L
        val timer = TriTimer { now }

        timer.start(Bucket.ACTIVE)
        now = 800
        timer.start(Bucket.UNKNOWN) // Doze suspension: not active work
        now = 2_000
        timer.start(Bucket.ACTIVE)
        now = 2_600
        timer.close()

        assertEquals(1_400L, timer.activeMs()) // 800 + 600, never +1200
        assertEquals(1_200L, timer.unknownMs())
        assertEquals(0L, timer.waitingMs())
        assertEquals(0L, timer.errorMs())
        assertEquals(2_600L, timer.totalMs())
    }

    @Test
    fun `freeze stops accumulation and unfreeze resumes it`() {
        var now = 0L
        val timer = TriTimer { now }

        timer.start(Bucket.WAITING)
        now = 700
        timer.freeze() // banks [0, 700] and blocks further accumulation

        now = 99_999 // the wall clock keeps running while frozen
        assertTrue(timer.isFrozen())
        assertEquals(700L, timer.waitingMs())
        assertEquals(700L, timer.totalMs())

        timer.close() // must remain a no-op while frozen
        assertEquals(700L, timer.waitingMs())

        timer.unfreeze()
        timer.start(Bucket.WAITING) // opens at 99_999
        now = 100_699
        timer.close()
        assertEquals(1_400L, timer.waitingMs())
    }

    @Test
    fun `starting a segment while frozen is rejected`() {
        var now = 0L
        val timer = TriTimer { now }

        timer.start(Bucket.PAUSED)
        timer.freeze()
        try {
            timer.start(Bucket.ACTIVE)
            fail("start() while frozen must be rejected")
        } catch (ignored: IllegalStateException) {
            // expected: a frozen timer refuses new segments
        }
        assertEquals(0L, timer.pausedMs()) // only the zero-length [0,0] was banked
    }

    @Test
    fun `recoverOrphans closes an open segment at cutoff without double counting`() {
        var now = 0L
        val timer = TriTimer { now }

        timer.start(Bucket.ERROR)
        now = 2_500
        timer.start(Bucket.ERROR) // first span [0, 2500] closes here
        assertEquals(2_500L, timer.errorMs())

        // Simulate a crash: the second segment stays open while the wall clock races ahead.
        now = 60_000
        assertEquals(2_500L, timer.errorMs()) // open segments are not counted yet

        timer.recoverOrphans(cutoff = 4_000)
        assertEquals(4_000L, timer.errorMs()) // 2500 + (4000 - 2500), not +57500
        assertFalse(timer.segments.last().isOpen)
        assertEquals(4_000L, timer.segments.last().end!!)

        // Idempotent: a second recovery pass must not add anything.
        timer.recoverOrphans(cutoff = 4_000)
        assertEquals(4_000L, timer.errorMs())
        assertEquals(4_000L, timer.totalMs())
    }
}
