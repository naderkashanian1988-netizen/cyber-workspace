# CYBER WORKSPACE — Security Documentation

## 1. Threat model

| Asset | Threat | Mitigation |
| --- | --- | --- |
| Task configurations/logs | local snooping | stored in the user profile; no secrets in task configs; logs never include credentials (we do not log argv of env vars beyond the launch line) |
| Remote control channel | MITM / sniffing on LAN | TLS 1.2+ with a self-signed host certificate; fingerprint verified out-of-band at pairing and pinned on the device |
| Device tokens | theft/replay | 256-bit random tokens; server stores SHA-256 hashes only; constant-time comparison; single-session-per-device; revocation UI; 30-day unused-session expiry |
| Pairing | rogue device joins | 6-digit single-use code, 5-minute TTL, issued only from the host UI; every pairing is audit-logged |
| Command injection | malicious "command" through the remote API | commands are a **closed enum** (`pause/resume/restart/close/set_keep_awake`) validated in `protocol.messages.validate_command`; nothing free-form ever reaches process-launch code; script launches use argv lists, never `shell=True` |
| Local privilege | escalation via the app | the app runs unprivileged, opens settings pages via `control.exe`, uses only user-level APIs; no services, no drivers |
| Sensitive operations | accidental destruction | close/remove/revoke require explicit confirmation; remote `close` is enum-gated and audit-logged |

## 2. Least privilege in practice

- No admin rights required to install (portable) or run.
- ICMP ping is deliberately avoided (needs raw sockets) — latency is a plain
  TCP connect probe, labelled as such.
- Per-task network attribution would require elevated ETW/packet-counter
  APIs; the workspace refuses to elevate and reports `n/a` instead.
- Keep-awake uses `SetThreadExecutionState` — a documented, temporary,
  thread-scoped API. `powercfg` is invoked read-only (`/a`).

## 3. Credential storage

| Store | What | How |
| --- | --- | --- |
| Windows host | device token hashes | SHA-256 in SQLite `devices.token_hash` |
| Windows host | TLS private key | `%APPDATA%\CyberWorkspace\remote-key.pem`, filesystem ACL (0600 on creation) |
| Android | device token + fingerprint | `EncryptedSharedPreferences` (AES-256-GCM master key) |
| Logs | — | never contain tokens, codes or secrets |

## 4. Pairing & session lifecycle

1. Host UI issues a single-use 6-digit code (300 s TTL) — audit-logged.
2. Android connects over TLS, sends `pairing` → receives `device_id` +
   `token` **once** (plaintext token exists only on this encrypted reply).
3. Subsequent connections use `auth`; failure reasons are
   `UNKNOWN_DEVICE / INVALID_TOKEN / REVOKED / SESSION_EXPIRED`.
4. One live session per device (second concurrent auth → `CONFLICT`).
5. 3 auth attempts per connection, then the connection is closed.
6. Tokens unused for 30 days are treated as expired (re-pair required).
7. Revocation (Devices dialog) is immediate and audit-logged.

## 5. Audit trail

Every pairing, revocation, authentication and remote command is appended to
`audit_log` with actor (`local` / `remote:<device-prefix>`), action, task and
outcome. The audit log is readable from the SQLite database and survives
restarts.

## 6. Input validation

- Protocol: message size ≤ 64 KiB, rate ≤ 30 msg/s (burst 60), unknown ops →
  `BAD_REQUEST`, version mismatch → `VERSION_MISMATCH` + close.
- Adapter configs: argv-list only; paths used as given (user's own machine,
  user's own privileges); no string interpolation into shells.
- Android: same enum set compiled in (`ProtocolModels.kt` mirrors
  `messages.py`); malformed JSON is rejected before reaching UI logic.

## 7. Update strategy (see VERSIONING.md)

Release artifacts should be code-signed (Authenticode for EXE/installer,
APK signing key for Android). The delivered tree does not include signing
keys; the build pipeline marks where signing hooks in. Update verification:
compare the pinned protocol version on connect; incompatible hosts/clients
must refuse rather than degrade silently.

## 8. Reporting issues

This is a local/LAN product. Do not expose the remote port to the internet;
if you must, put it behind a VPN. Security-relevant bugs found in the field
should include the `audit_log` excerpt (redact device ids) and protocol trace.
