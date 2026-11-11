"""Embedded schema (authoritative runtime copy of Source/Windows/db/schema.sql)."""
SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    type            TEXT NOT NULL CHECK (type IN ('script','terminal','external','browser')),
    position        INTEGER NOT NULL DEFAULT 0,
    created_utc     TEXT NOT NULL,
    last_state      TEXT NOT NULL DEFAULT 'UNKNOWN',
    last_state_utc  TEXT,
    last_reason     TEXT,
    last_pid        INTEGER,
    last_exit_code  INTEGER,
    last_seen_utc   TEXT,
    minimized       INTEGER NOT NULL DEFAULT 0,
    keep_awake      INTEGER NOT NULL DEFAULT 0,
    config_json     TEXT NOT NULL DEFAULT '{}',
    layout_json     TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS timer_segments (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id   TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    kind      TEXT NOT NULL CHECK (kind IN ('active','waiting','error','paused','unknown')),
    start_utc TEXT NOT NULL,
    end_utc   TEXT,
    recovered INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_segments_task ON timer_segments(task_id);
CREATE INDEX IF NOT EXISTS idx_segments_open ON timer_segments(task_id) WHERE end_utc IS NULL;
CREATE TABLE IF NOT EXISTS task_events (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT,
    ts_utc  TEXT NOT NULL,
    level   TEXT NOT NULL DEFAULT 'info',
    kind    TEXT NOT NULL,
    message TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_task ON task_events(task_id, id);
CREATE TABLE IF NOT EXISTS metric_samples (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    ts_utc  TEXT NOT NULL,
    cpu_percent REAL,
    ram_mb      REAL
);
CREATE INDEX IF NOT EXISTS idx_metrics_task ON metric_samples(task_id, id);
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
CREATE TABLE IF NOT EXISTS devices (
    device_id    TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    paired_utc   TEXT NOT NULL,
    token_hash   TEXT NOT NULL,
    permissions  TEXT NOT NULL DEFAULT '["view"]',
    last_seen_utc TEXT,
    revoked      INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS audit_log (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_utc  TEXT NOT NULL,
    actor   TEXT NOT NULL,
    action  TEXT NOT NULL,
    detail  TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""
