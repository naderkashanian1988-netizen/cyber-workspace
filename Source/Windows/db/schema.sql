-- CYBER WORKSPACE — SQLite schema (user_version = 1)
-- All timestamps are ISO-8601 UTC strings ("...Z"); all durations are integer milliseconds.

PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Task configuration + last known lifecycle snapshot (persisted every state change).
CREATE TABLE IF NOT EXISTS tasks (
    id              TEXT PRIMARY KEY,             -- uuid4 hex
    name            TEXT NOT NULL,
    type            TEXT NOT NULL CHECK (type IN ('script','terminal','external','browser')),
    position        INTEGER NOT NULL DEFAULT 0,
    created_utc     TEXT NOT NULL,
    last_state      TEXT NOT NULL DEFAULT 'UNKNOWN',
    last_state_utc  TEXT,
    last_reason     TEXT,
    last_pid        INTEGER,
    last_exit_code  INTEGER,
    last_seen_utc   TEXT,                         -- last time the engine could observe it
    minimized       INTEGER NOT NULL DEFAULT 0,
    keep_awake      INTEGER NOT NULL DEFAULT 0,
    config_json     TEXT NOT NULL DEFAULT '{}',   -- adapter-specific configuration
    layout_json     TEXT NOT NULL DEFAULT '{}'    -- per-card UI prefs (width, color tag…)
);

-- Wall-clock timer segments. Exactly one open segment per task (end_utc IS NULL).
-- Kinds: active | waiting | error | paused | unknown
CREATE TABLE IF NOT EXISTS timer_segments (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id   TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    kind      TEXT NOT NULL CHECK (kind IN ('active','waiting','error','paused','unknown')),
    start_utc TEXT NOT NULL,
    end_utc   TEXT,                               -- NULL while open
    recovered INTEGER NOT NULL DEFAULT 0          -- 1 = closed by crash recovery
);
CREATE INDEX IF NOT EXISTS idx_segments_task   ON timer_segments(task_id);
CREATE INDEX IF NOT EXISTS idx_segments_open   ON timer_segments(task_id) WHERE end_utc IS NULL;

-- Structured lifecycle events (state changes, approvals, recovery actions).
CREATE TABLE IF NOT EXISTS task_events (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT,
    ts_utc  TEXT NOT NULL,
    level   TEXT NOT NULL DEFAULT 'info',         -- info | warning | error
    kind    TEXT NOT NULL,                        -- state_changed | approval | recovery | adapter | …
    message TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_task ON task_events(task_id, id);

-- Rolling per-task resource samples (trimmed by the engine).
CREATE TABLE IF NOT EXISTS metric_samples (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    ts_utc  TEXT NOT NULL,
    cpu_percent REAL,
    ram_mb      REAL
);
CREATE INDEX IF NOT EXISTS idx_metrics_task ON metric_samples(task_id, id);

-- Notification center (persistent across restarts).
CREATE TABLE IF NOT EXISTS notifications (
    id         TEXT PRIMARY KEY,
    ts_utc     TEXT NOT NULL,
    task_id    TEXT,
    category   TEXT NOT NULL,
    title      TEXT NOT NULL,
    body       TEXT NOT NULL DEFAULT '',
    read       INTEGER NOT NULL DEFAULT 0,
    actions_json TEXT NOT NULL DEFAULT '[]'
);

-- Paired Android devices. Token stored HASHED (SHA-256 hex) — never plaintext.
CREATE TABLE IF NOT EXISTS devices (
    device_id    TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    paired_utc   TEXT NOT NULL,
    token_hash   TEXT NOT NULL,
    permissions  TEXT NOT NULL DEFAULT '["view"]',
    last_seen_utc TEXT,
    revoked      INTEGER NOT NULL DEFAULT 0
);

-- Audit log: who did what (pairing, remote commands, security events).
CREATE TABLE IF NOT EXISTS audit_log (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_utc  TEXT NOT NULL,
    actor   TEXT NOT NULL,                        -- 'local' | device_id
    action  TEXT NOT NULL,
    detail  TEXT NOT NULL DEFAULT ''
);

-- Simple key/value preferences that must survive restarts.
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
