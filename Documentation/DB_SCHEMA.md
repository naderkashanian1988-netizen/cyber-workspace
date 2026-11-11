# Database Schema — CYBER WORKSPACE (schema version 1)

SQLite database at `%LOCALAPPDATA%\CYBERWorkspace\workspace.db`
(Windows) or `~/.local/share/cyberworkspace/workspace.db` (development on
Linux). WAL mode, foreign keys on. Authoritative DDL:
`Source/Windows/db/schema.sql`.

All timestamps are **UTC epoch seconds** (REAL). Timer intervals are linked
to workspace runs via `session_id` so recovery can clamp without
double-counting.

## tables

### tasks
| column | type | meaning |
| --- | --- | --- |
| id | TEXT PK | UUID |
| name / adapter | TEXT | display name; adapter key (`python`,`terminal`,`external`,`http`,`browser`) |
| config_json | TEXT | adapter configuration (script path, command, url, ...) |
| state | TEXT | one of the 8 task states |
| state_reason | TEXT | human-readable, honest reason for the state |
| last_progress | TEXT | last progress text reported |
| last_activity_utc | REAL | last verified activity |
| last_heartbeat_utc | REAL | last watchdog heartbeat (5 s cadence) — the recovery clamp anchor |
| pid | INTEGER | managed process id, when applicable |
| position | INTEGER | card order |
| autostart | INTEGER | user opt-in; recovered tasks are never auto-restarted regardless of this flag |
| timer_state_json | TEXT | serialized in-flight timer totals + open segment (heartbeat-persisted) |
| created_utc / updated_utc | REAL | bookkeeping |

### timer_intervals
| column | type | meaning |
| --- | --- | --- |
| id | INTEGER PK | |
| task_id | TEXT FK → tasks ON DELETE CASCADE | |
| kind | TEXT CHECK | `active` \| `waiting` \| `error` \| `unknown` |
| start_utc / end_utc | REAL | interval bounds (UTC) |
| seconds | REAL | interval length |
| source | TEXT | what produced it: `engine`, `recovery-clamped`, adapter source tags |
| session_id | TEXT | which workspace run billed it |

Invariants: every billed second appears in exactly one interval row;
in-memory totals always equal `SUM(seconds) GROUP BY kind` (enforced by the
no-double-count recovery tests); `elapsed = Σ all kinds` by definition.

### events
Append-only log: `ts_utc`, `task_id` (nullable for engine-wide), `level`,
`code` (`process_started`, `stream:stdout`, `progress`, `waiting_user`,
`network_waiting`, `watchdog`, `approval_resolved`, ...), `message`.
Task logs shown in the UI come from here plus the in-memory ring buffer.

### notifications
`id` (UUID PK), `ts_utc`, `severity` (`info|warning|critical`), `task_id`,
`code` (e.g. `user_approval_required`, `task_crashed`,
`recovery_required`), `title`, `body`, `read`.

### paired_devices
`device_id` (UUID PK), `name`, `platform`, `token_hash` (SHA-256 of the
token — the token itself is never stored), `scopes_json` (`["view",
"approve","control"]`), `paired_utc`, `last_seen_utc`, `revoked`.

### audit_log
`ts_utc`, `device_id` (nullable for pre-auth attempts), `action`
(`pair_attempt`, `pair_fail`, `pair_success`, `auth`, `command:pause`, ...),
`target` (task id / address / client name), `result` (`ok`, `denied`,
`failed`, details), `detail`.

### sessions
One row per workspace run: `id` (PK = session id used by timer intervals),
`started_utc`, `ended_utc`, `shutdown_kind` (`app_exit`, `test`, ...).

### schema_meta
`key`/`value`; holds `schema_version`.

## Migration policy

Migrations are additive and run at startup before the engine opens;
`schema_version` gates them. Destructive schema changes require a documented
backup path first (see `VERSIONING.md`).
