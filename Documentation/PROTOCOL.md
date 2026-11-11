# CYBER WORKSPACE — Shared Remote Protocol v1

Status: **Specification — normative** for the Windows host server (`Source/Windows/cyber_workspace/remote/server.py`)
and the Android client (`Source/Android/app/src/main/kotlin/com/cyberworkspace/app/net/`).
Reference implementation of the message model: `Source/Windows/cyber_workspace/protocol/messages.py`.

Protocol version: **1** (`PROTOCOL_VERSION = 1`). Any breaking change requires bumping the version and
adding a compatibility note to `VERSIONING.md`.

---

## 1. Transport & Security

| Property | Value |
| --- | --- |
| Transport | WebSocket (one message = one JSON object, UTF-8) |
| Encryption | TLS 1.2+ (TLS 1.3 preferred). Server presents a self-signed certificate generated on first host start |
| Trust model | The Android client stores the SHA-256 certificate fingerprint shown on the host during pairing and refuses connections whose fingerprint differs (SPKI/cert fingerprint pinning) |
| Authentication | Per-device bearer token (256-bit, `secrets.token_urlsafe`), issued **once** during pairing over the already-encrypted channel; the host stores only a SHA-256 hash |
| Confidentiality | No plaintext control channel ever exists; pairing PIN is single-use, 6 digits, 5-minute TTL |
| Access control | Permissions: `view` (read-only) or `view` + `control` (commands/approvals). Assigned at pairing, revocable per device |
| Audit | Every authenticated command and pairing event is written to the host audit log |

Non-negotiable requirements:

- The host must **never** accept commands before a successful `auth_ok`.
- The Android client must **never** connect without TLS, and must abort on fingerprint mismatch.
- The host must rate-limit and size-limit messages (see §7) and must treat any protocol violation as fatal for that connection only — never for the engine.

## 2. Envelope

Every message (both directions) is one JSON object:

```json
{
  "v": 1,
  "op": "auth",
  "seq": 12,
  "ts": "2026-11-11T09:00:00Z",
  "payload": { }
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `v` | int | Protocol version, must equal `1`. On mismatch the server replies `error` with code `VERSION_MISMATCH` and closes the connection |
| `op` | string | Operation name, one of the enums in §3 |
| `seq` | int | Client-side monotonically increasing request id. Acks that answer a request echo it |
| `ts` | string | ISO 8601 UTC timestamp with `Z` suffix |
| `payload` | object | Operation-specific; never `null`, use `{}` when empty |

Unknown `op` values must be answered with `error` code `BAD_REQUEST` and must not crash the connection.

## 3. Operations

### 3.1 Client → Host

| op | payload | reply |
| --- | --- | --- |
| `pairing` | `{ "device_name": str, "code": "6 digits" }` | `pairing_ok` or `error` |
| `auth` | `{ "device_id": str, "token": str, "device_name": str? }` | `auth_ok` or `auth_failed` |
| `subscribe` | `{ "topics": ["state","metrics","notifications"] }` | `state_snapshot`, then streamed events |
| `unsubscribe` | `{}` | `command_ack` |
| `get_state` | `{}` | `state_snapshot` |
| `get_task` | `{ "task_id": str }` | `{ "task": TaskSnapshot }` or `error` |
| `get_logs` | `{ "task_id": str, "last_n": int ≤ 1000 }` | `{ "task_id": str, "lines": [str] }` |
| `command` | `{ "command_id": str, "action": CommandAction, "task_id": str?, "params"?: object }` | `command_ack` (applied asynchronously; state changes follow as `task_event`) |
| `approve` | `{ "command_id": str, "request_id": str, "decision": "approve"\|"deny", "note"?: str }` | `command_ack` |
| `ping` | `{}` | `pong` |

`CommandAction` enum (closed set — **no free-form shell strings cross the wire**, this is the command-injection boundary):

```
pause | resume | restart | close | set_keep_awake(params: {"enabled": bool})
```

### 3.2 Host → Client

| op | payload |
| --- | --- |
| `welcome` | `{ "protocol_version": 1, "server_version": str, "fingerprint": "AA:BB:…", "pairing_available": bool }` — sent immediately on connect, before auth |
| `pairing_ok` | `{ "device_id": str, "token": str, "permissions": ["view"\|"control"], "token_ttl_days": int }` |
| `auth_ok` | `{ "protocol_version": 1, "server_version": str, "capabilities": ["metrics","logs","commands","approvals","keep_awake"], "permissions": ["view"\|"control"], "token_ttl_days": int }` |
| `auth_failed` | `{ "reason": "INVALID_TOKEN"\|"REVOKED"\|"SESSION_EXPIRED"\|"UNKNOWN_DEVICE" }` then close |
| `state_snapshot` | `{ "tasks": [TaskSnapshot…], "system": SystemStatus }` |
| `task_event` | `{ "task_id": str, "event": "state_changed"\|"progress"\|"metrics"\|"removed", "task": TaskSnapshot, "extra"?: object }` |
| `metrics` | `{ "system": SystemStatus, "tasks": { "<task_id>": {"cpu_percent": number\|null, "ram_mb": number\|null} } }` — every 2 s while subscribed |
| `notification` | `{ "id", "created_utc", "category", "title", "body", "task_id": str\|null, "actions": [{"id","label"}…] }` |
| `approval_request` | `{ "id", "created_utc", "task_id", "question", "options": [str…] }` |
| `command_ack` | `{ "command_id", "ok": bool, "error"?: str }` |
| `error` | `{ "code": str, "message": str }` |
| `pong` | `{ "ts": str }` |

### 3.3 Shared data models

**TaskState** (closed set, mirrors `Source/Windows/cyber_workspace/core/state.py`):

```
RUNNING | WAITING_FOR_USER | NETWORK_WAITING | COMPLETED | ERROR | UNRESPONSIVE | PAUSED | UNKNOWN
```

**NotificationCategory**:

```
approval_required | permission_required | task_error | network_interruption |
task_completed | task_crashed | task_unresponsive | security_warning | recovery_required | info
```

**TaskSnapshot** (all fields always present; unavailable metrics are `null`, never fabricated):

```json
{
  "id": "uuid4",
  "name": "Build report",
  "type": "script|terminal|external|browser",
  "state": "RUNNING",
  "reason": "exit code 0 (script finished normally) | null",
  "active_ms": 154000,
  "waiting_ms": 32000,
  "error_ms": 0,
  "paused_ms": 0,
  "unknown_ms": 41000,
  "cpu_percent": 12.4,
  "ram_mb": 231.5,
  "last_activity_utc": "2026-11-11T08:59:57Z",
  "last_progress": "step 12/20",
  "keep_awake": false,
  "minimized": false,
  "pid": 4812,
  "app": "python.exe",
  "created_utc": "2026-11-11T08:30:00Z",
  "pending_approval": { "id": "…", "question": "Deploy now?", "options": ["Yes","No"] } | null
}
```

**SystemStatus**:

```json
{
  "cpu_percent": 34.0,
  "ram_percent": 61.2,
  "ram_used_mb": 9840.1,
  "ram_total_mb": 16384.0,
  "net": { "down_bps": 184000.0, "up_bps": 22000.0, "latency_ms": 18.4, "status": "UP|DOWN|UNKNOWN" },
  "keep_awake_active": false,
  "server_time": "2026-11-11T09:00:00Z"
}
```

`latency_ms` is a **TCP connect latency** probe (not ICMP). Any unavailable value must be `null`,
never `0` and never a placeholder number.

## 4. Pairing flow

```
Android                          Host
  │── TLS connect ────────────────▶│
  │◀──────────── welcome ─────────│  (fingerprint shown on both screens)
  │  user verifies fingerprint + enters 6-digit PIN displayed on host
  │── pairing {device_name, code} ▶│  (single-use, 5-min TTL)
  │◀──────────── pairing_ok ──────│  (device_id + token — only time the token travels)
  │── auth {device_id, token} ────▶│
  │◀────────────── auth_ok ───────│
  │── subscribe ──────────────────▶│
  │◀─────── state_snapshot + stream│
```

Notes:

- The token is generated by the host, returned exactly once in `pairing_ok`, stored hashed on the host,
  stored in Android `EncryptedSharedPreferences` on the client.
- Tokens that stay unused beyond `token_ttl_days` (default 30) are treated as `SESSION_EXPIRED`;
  the client must re-pair.
- Host UI lists paired devices with last-seen time and supports revocation (`REVOKED`).

## 5. Session & connection rules

1. One connection per `device_id`: a second concurrent auth with the same id is rejected with
   `error CONFLICT` (the existing session is preserved — never the reverse).
2. Authenticated connections that send no traffic for 15 minutes are closed by the host.
3. `SESSION_EXPIRED` / `REVOKED` / `INVALID_TOKEN` → host sends `auth_failed` then closes.
4. Any transport error affects only that connection; the host engine never stops.

## 6. Ordering & consistency

- The first `state_snapshot` after `subscribe` is the authoritative baseline; afterwards
  `task_event` messages carry the **full TaskSnapshot** of the changed task so clients stay
  stateless-per-task and can survive missed messages by re-requesting `get_state`.
- `metrics` messages are advisory (they may be dropped under backpressure by the client);
  `task_event` messages must not be dropped.
- Timers in TaskSnapshot are monotonically consistent with `server_time` in the same message batch.

## 7. Limits (host-enforced)

| Limit | Value |
| --- | --- |
| Max message size | 64 KiB |
| Client message rate | 30 msg/s (burst 60) → beyond: `error RATE_LIMITED` then close |
| `get_logs.last_n` | ≤ 1000 |
| Max paired devices | 8 |
| Auth attempts per connection | 3, then close |

## 8. Compatibility rules

1. Clients must ignore unknown fields inside `payload` (forward compatibility).
2. Clients must treat unknown `op` as `error BAD_REQUEST` (log + ignore), not as a fatal condition.
3. Adding new ops or new fields requires a minor doc update, **not** a version bump.
4. Removing/renaming fields or changing semantics requires `v=2` and a migration note in
   `VERSIONING.md`; the host must keep serving `v=1` for at least one minor release cycle.
