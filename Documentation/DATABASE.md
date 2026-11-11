# CYBER WORKSPACE — Database

Engine: SQLite (WAL mode), one file per workspace:
`%APPDATA%\CyberWorkspace\workspace.db` (Windows) — schema v1.

Authoritative runtime schema: `Source/Windows/cyber_workspace/persistence/schema_sql.py`
(`SCHEMA` constant). `Source/Windows/db/schema.sql` is the identical, documented copy
shipped with the PyInstaller bundle.

## Tables

| Table | Purpose | Notes |
| --- | --- | --- |
| `meta` | crash-recovery flags | `shutdown_clean` distinguishes clean exit from crash |
| `tasks` | configuration + last lifecycle snapshot | `last_state`, `last_reason`, `last_pid`, `last_seen_utc`, `config_json`, `keep_awake`, `minimized` |
| `timer_segments` | wall-clock time buckets | kinds `active/waiting/error/paused/unknown`; exactly one open segment (end_utc NULL) per task; `recovered=1` marks crash-closed orphans |
| `task_events` | structured lifecycle log | state changes, approvals, recovery actions |
| `metric_samples` | per-task CPU/RAM history | ring buffer, 240 samples/task |
| `notifications` | notification center | persistent across restarts, read flags |
| `devices` | paired Android devices | **token stored SHA-256-hashed only**, permissions list, revocation flag, last_seen |
| `audit_log` | who did what | pairing, revocations, remote commands with ok/error |
| `settings` | simple KV prefs | e.g. saved task order |

## Timer totals (no double counting)

```
totals[kind] = Σ segments(kind, closed)           -- persisted wall clock
             + elapsed(open segment, monotonic)   -- live display only
```

A segment is closed the instant its bucket changes; `COMPLETED` freezes
everything. Recovery closes orphans at `last_seen_utc` (≤5 s staleness), so a
crash costs at most one small, honest interval — never a stretched one.

## Retention & size

- `metric_samples` trimmed to 240 rows/task on each write.
- `task_events` and `audit_log` grow with usage; the data directory is
  user-managed. (A future schema version may add rotation — see VERSIONING.)

## Reset / uninstall

Close the workspace, then delete `%APPDATA%\CyberWorkspace\` (database, logs,
settings, remote TLS key material). The Inno Setup uninstaller deliberately
preserves this folder.
