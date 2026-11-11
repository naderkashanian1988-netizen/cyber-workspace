package com.cyberworkspace.remote.net

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ReconnectPolicyTest {

    @Test
    fun `backoff grows exponentially and caps at 30s`() {
        val policy = ReconnectPolicy()
        val delays = List(8) { policy.nextDelaySeconds() }
        assertEquals(listOf(1L, 2L, 4L, 8L, 16L, 30L, 30L, 30L), delays)
    }

    @Test
    fun `success resets the sequence`() {
        val policy = ReconnectPolicy()
        repeat(5) { policy.nextDelaySeconds() }
        policy.onSuccess()
        assertEquals(0, policy.attempts)
        assertEquals(1L, policy.nextDelaySeconds())
    }

    @Test
    fun `never gives up by default while a session is wanted`() {
        val policy = ReconnectPolicy()
        repeat(1000) { policy.nextDelaySeconds() }
        assertFalse(policy.shouldGiveUp())
    }

    @Test
    fun `bounded attempts give up after the limit`() {
        val policy = ReconnectPolicy(maxAttempts = 3)
        repeat(2) { policy.nextDelaySeconds() }
        assertFalse(policy.shouldGiveUp())
        policy.nextDelaySeconds()
        assertTrue(policy.shouldGiveUp())
    }

    @Test
    fun `session expiry detected from wall clock`() {
        val policy = ReconnectPolicy()
        assertFalse(policy.sessionLikelyExpired(1000L, null))
        assertFalse(policy.sessionLikelyExpired(999L, 1000L))
        assertTrue(policy.sessionLikelyExpired(1000L, 1000L))
        assertTrue(policy.sessionLikelyExpired(2000L, 1000L))
    }
}
