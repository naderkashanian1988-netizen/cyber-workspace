package com.cyberworkspace.remote.protocol

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ProtocolCodecTest {

    @Test
    fun `envelope round trip keeps all fields`() {
        val env = ProtocolCodec.envelope(
            type = "hello",
            payload = ProtocolCodec.helloPayload("unit-test", "android"),
            id = "fixed-id",
            ts = 1234L,
        )
        val wire = ProtocolCodec.encode(env)
        val parsed = ProtocolCodec.decode(wire)
        assertEquals(1, parsed.v)
        assertEquals("fixed-id", parsed.id)
        assertEquals("hello", parsed.type)
        assertEquals(1234L, parsed.ts)
        val hello = ProtocolCodec.json.decodeFromJsonElement(
            HelloPayload.serializer(), parsed.payload)
        assertEquals("unit-test", hello.client_name)
        assertEquals(1, hello.protocol_version)
    }

    @Test
    fun `task card with null metrics decodes honestly`() {
        val card = """
            {"id":"t1","name":"Ingest job","adapter":"python","state":"RUNNING",
             "state_reason":"","pid":41232,
             "progress":{"text":"3/10 files","pct":30.0},
             "last_activity_ms":1730000000000,
             "timers":{"active_s":120.5,"waiting_s":30.0,"error_s":0.0,
                       "unknown_s":5.0,"elapsed_s":190.0},
             "metrics":{"cpu_percent":3.2,"ram_mb":148.6,"net":null},
             "approval_pending":null,"position":2}
        """.trimIndent()
        val parsed = ProtocolCodec.decodeTaskCardJson(card)
        assertEquals("t1", parsed.id)
        assertEquals("RUNNING", parsed.state)
        assertEquals(30.0, parsed.progress.pct!!)
        assertEquals(120.5, parsed.timers.active_s)
        assertTrue(parsed.metrics?.cpu_percent == 3.2)
        assertNull(parsed.metrics?.net) // v1: per-task network must stay null
        assertNull(parsed.approval_pending)
    }

    @Test
    fun `task card approval banner parses request id`() {
        val card = """
            {"id":"t2","name":"w","adapter":"python","state":"WAITING_FOR_USER",
             "approval_pending":{"request_id":"req-9","summary":"Approve license?"}}
        """.trimIndent()
        val parsed = ProtocolCodec.decodeTaskCardJson(card)
        assertEquals("req-9", parsed.approval_pending?.request_id)
        assertEquals("Approve license?", parsed.approval_pending?.summary)
    }

    @Test
    fun `degenerate payload degrades to defaults instead of crashing`() {
        val env = ProtocolEnvelope(1, "x", "snapshot", 0, JsonObject(emptyMap()))
        val snapshot = ProtocolCodec.snapshotOf(env)
        assertTrue(snapshot.tasks.isEmpty())
        val card = ProtocolCodec.decodeTaskCardJson("not json at all")
        assertEquals("", card.id)
    }

    @Test
    fun `unknown wire fields are ignored for forward compatibility`() {
        val env = ProtocolCodec.decode(
            """{"v":1,"id":"i","type":"welcome","ts":1,
                "payload":{"protocol_version":1,"brand_new_field":42}}""")
        val welcome = ProtocolCodec.welcomeOf(env)
        assertEquals(1, welcome.protocol_version)
    }

    @Test
    fun `malformed envelope raises ProtocolParseException`() {
        try {
            ProtocolCodec.decode("{definitely not json")
            assertFalse("expected ProtocolParseException", true)
        } catch (expected: ProtocolParseException) {
            assertTrue(expected.message!!.isNotEmpty())
        }
    }

    @Test
    fun `command and approve payloads serialize per spec`() {
        val env = ProtocolCodec.envelope(
            "command", ProtocolCodec.commandPayload("t1", "pause"))
        val obj = ProtocolCodec.json.parseJsonElement(
            ProtocolCodec.encode(env)).jsonObject
        assertEquals("command", obj["type"]!!.jsonPrimitive.content)
        val payload = obj["payload"]!!.jsonObject
        assertEquals("t1", payload["task_id"]!!.jsonPrimitive.content)
        assertEquals("pause", payload["action"]!!.jsonPrimitive.content)

        val approve = ProtocolCodec.envelope(
            "approve", ProtocolCodec.approvePayload("req-9", "deny"))
        val payload2 = ProtocolCodec.json
            .parseJsonElement(ProtocolCodec.encode(approve)).jsonObject["payload"]!!
            .jsonObject
        assertEquals("req-9", payload2["request_id"]!!.jsonPrimitive.content)
        assertEquals("deny", payload2["decision"]!!.jsonPrimitive.content)
    }

    @Test
    fun `type registries cover the protocol`() {
        // Every message type from PROTOCOL.md §3 is known to the codec.
        for (t in listOf("hello", "pair_request", "auth", "subscribe",
                         "get_snapshot", "command", "approve", "ping")) {
            assertTrue("client type missing: $t", t in ProtocolCodec.CLIENT_TYPES)
        }
        for (t in listOf("welcome", "pair_result", "auth_result", "snapshot",
                         "task_event", "notification", "command_result",
                         "logs", "pong", "error")) {
            assertTrue("server type missing: $t", t in ProtocolCodec.SERVER_TYPES)
        }
    }
}
