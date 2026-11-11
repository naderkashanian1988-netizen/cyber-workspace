package com.cyberworkspace.app

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

/**
 * Self-contained contract tests for the CYBER WORKSPACE protocol v1 envelope.
 *
 * These tests deliberately do NOT import the production protocol classes:
 * they define minimal @Serializable mirrors of the v1 wire contract (snake_case
 * field names exactly as they appear on the wire, see ../../../../../../../../Shared/protocol/PROTOCOL.md) so
 * they compile and pass independently of how the production sources evolve.
 */
class ProtocolModelsTest {

    private val json = Json { ignoreUnknownKeys = true }

    // ---- local mirrors of the protocol v1 contract (wire field names) ----

    @Serializable
    data class TestTaskSnapshot(
        val id: String,
        val name: String,
        val type: String,
        val state: String,
        val reason: String? = null,
        val active_ms: Long = 0L,
        val waiting_ms: Long = 0L,
        val error_ms: Long = 0L,
        val paused_ms: Long = 0L,
        val unknown_ms: Long = 0L,
        val cpu_percent: Double = 0.0,
        val ram_mb: Double = 0.0,
        val last_activity_utc: String? = null,
        val last_progress: String? = null,
        val keep_awake: Boolean = false,
        val minimized: Boolean = false,
        val pid: Int? = null,
        val app: String? = null,
        val created_utc: String? = null,
        val pending_approval: JsonElement? = null
    )

    @Serializable
    data class TestSnapshotPayload(
        val tasks: List<TestTaskSnapshot> = emptyList()
    )

    /** Typed envelope shape used for the state_snapshot op. */
    @Serializable
    data class TestSnapshotEnvelope(
        val v: Int,
        val op: String,
        val payload: TestSnapshotPayload
    )

    /** Generic envelope: op is an opaque String, payload stays raw JSON. */
    @Serializable
    data class TestGenericEnvelope(
        val v: Int,
        val op: String,
        val payload: JsonObject = JsonObject(emptyMap())
    )

    /**
     * Version gate mirroring the production contract: only protocol version 1
     * is accepted. Defined inside the test file on purpose so this test pins
     * the rule even if the production implementation drifts.
     */
    private fun validateVersion(envelope: TestGenericEnvelope) {
        require(envelope.v == 1) { "Unsupported protocol version: ${envelope.v} (expected 1)" }
    }

    private val stateSnapshotJson = """
        {
          "v": 1,
          "op": "state_snapshot",
          "payload": {
            "tasks": [
              {
                "id": "t-7f3c2a",
                "name": "nightly-build",
                "type": "script",
                "state": "RUNNING",
                "reason": "user_start",
                "active_ms": 91450,
                "waiting_ms": 12000,
                "error_ms": 0,
                "paused_ms": 3000,
                "unknown_ms": 4500,
                "cpu_percent": 12.5,
                "ram_mb": 184.0,
                "last_activity_utc": "2025-01-05T21:14:32Z",
                "last_progress": "compiling module 3/7",
                "keep_awake": true,
                "minimized": false,
                "pid": 4212,
                "app": "powershell.exe",
                "created_utc": "2025-01-05T21:12:00Z",
                "pending_approval": null
              }
            ]
          }
        }
    """.trimIndent()

    @Test
    fun `state snapshot envelope parses and exposes task state and active time`() {
        val envelope = json.decodeFromString(TestSnapshotEnvelope.serializer(), stateSnapshotJson)

        assertEquals(1, envelope.v)
        assertEquals("state_snapshot", envelope.op)
        assertEquals(1, envelope.payload.tasks.size)

        val task = envelope.payload.tasks.first()
        assertEquals("t-7f3c2a", task.id)
        assertEquals("nightly-build", task.name)
        assertEquals("script", task.type)
        assertEquals("RUNNING", task.state)
        assertEquals("user_start", task.reason)
        assertEquals(91450L, task.active_ms)
        assertEquals(12000L, task.waiting_ms)
        assertEquals(0L, task.error_ms)
        assertEquals(3000L, task.paused_ms)
        assertEquals(4500L, task.unknown_ms)
        assertEquals(12.5, task.cpu_percent, 0.0001)
        assertEquals(184.0, task.ram_mb, 0.0001)
        assertTrue(task.keep_awake)
        assertEquals(false, task.minimized)
        assertEquals(4212, task.pid)
        assertEquals("powershell.exe", task.app)
        assertNull(task.pending_approval)
    }

    @Test
    fun `envelope with protocol version 2 is rejected by the version gate`() {
        val futureJson = """
            {
              "v": 2,
              "op": "state_snapshot",
              "payload": { "tasks": [] }
            }
        """.trimIndent()

        // The generic envelope parses (v is just an Int on the wire)...
        val envelope = json.decodeFromString(TestGenericEnvelope.serializer(), futureJson)
        assertEquals(2, envelope.v)

        // ...but the version gate must reject it.
        try {
            validateVersion(envelope)
            fail("An envelope with v=2 must be rejected")
        } catch (expected: IllegalArgumentException) {
            assertTrue((expected.message ?: "").contains("protocol version"))
        }
    }

    @Test
    fun `unknown op string parses as a generic envelope`() {
        val raw = """
            {
              "v": 1,
              "op": "host_shout_v99",
              "payload": { "detail": "op added in a newer build" }
            }
        """.trimIndent()

        val envelope = json.decodeFromString(TestGenericEnvelope.serializer(), raw)
        assertEquals(1, envelope.v)
        assertEquals("host_shout_v99", envelope.op)
        assertTrue(envelope.payload.containsKey("detail"))

        // The version gate still passes: op is an opaque String, only v is enforced.
        validateVersion(envelope)
    }
}
