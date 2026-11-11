"""CYBER WORKSPACE — SQLite persistence layer.

Thread-safety: one shared connection guarded by an RLock (sqlite3 objects must
not be shared across threads without serialization). WAL journal mode. The
schema file lives in Source/Windows/db/schema.sql and is applied idempotently.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Any, Iterable

from ..core.state import SegmentKind, TaskState
from . import schema_sql

UTC = _dt.timezone.utc


def default_data_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "CyberWorkspace"


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._migrate()

    def _migrate(self) -> None:
        version = self._conn.execute("PRAGMA user_version").fetchone()[0]
        if version < 1:
            self._conn.executescript(schema_sql.SCHEMA)
            self._conn.execute("PRAGMA user_version = 1")
        self._conn.commit()

    def execute(self, sql: str, params: Iterable[Any] | dict = ()) -> sqlite3.Cursor:
        with self._lock:
            bound = params if isinstance(params, dict) else tuple(params)
            cur = self._conn.execute(sql, bound)
            self._conn.commit()
            return cur

    def query(self, sql: str, params: Iterable[Any] | dict = ()) -> list[sqlite3.Row]:
        with self._lock:
            bound = params if isinstance(params, dict) else tuple(params)
            return self._conn.execute(sql, bound).fetchall()

    def close(self) -> None:
        with self._lock:
            self._conn.commit()
            self._conn.close()


def new_id() -> str:
    return uuid.uuid4().hex


def _iso(dt: _dt.datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class TaskRepo:
    def __init__(self, db: Database):
        self.db = db

    def upsert(self, task: dict) -> None:
        self.db.execute(
            """INSERT INTO tasks (id,name,type,position,created_utc,last_state,last_state_utc,
                                  last_reason,last_pid,last_exit_code,last_seen_utc,minimized,
                                  keep_awake,config_json,layout_json)
               VALUES (:id,:name,:type,:position,:created_utc,:last_state,:last_state_utc,
                       :last_reason,:last_pid,:last_exit_code,:last_seen_utc,:minimized,
                       :keep_awake,:config_json,:layout_json)
               ON CONFLICT(id) DO UPDATE SET
                   name=excluded.name, type=excluded.type, position=excluded.position,
                   last_state=excluded.last_state, last_state_utc=excluded.last_state_utc,
                   last_reason=excluded.last_reason, last_pid=excluded.last_pid,
                   last_exit_code=excluded.last_exit_code, last_seen_utc=excluded.last_seen_utc,
                   minimized=excluded.minimized, keep_awake=excluded.keep_awake,
                   config_json=excluded.config_json, layout_json=excluded.layout_json""",
            task,
        )

    def all(self) -> list[sqlite3.Row]:
        return self.db.query("SELECT * FROM tasks ORDER BY position, created_utc")

    def get(self, task_id: str) -> sqlite3.Row | None:
        rows = self.db.query("SELECT * FROM tasks WHERE id=?", (task_id,))
        return rows[0] if rows else None

    def delete(self, task_id: str) -> None:
        self.db.execute("DELETE FROM tasks WHERE id=?", (task_id,))

    def set_positions(self, ids_in_order: list[str]) -> None:
        with self.db._lock:
            for pos, tid in enumerate(ids_in_order):
                self.db._conn.execute("UPDATE tasks SET position=? WHERE id=?", (pos, tid))
            self.db._conn.commit()


class TimerRepo:
    def __init__(self, db: Database):
        self.db = db

    def open_segment(self, task_id: str, kind: SegmentKind, start_utc: str) -> int:
        cur = self.db.execute(
            "INSERT INTO timer_segments (task_id,kind,start_utc) VALUES (?,?,?)",
            (task_id, kind.value, start_utc),
        )
        return cur.lastrowid or 0

    def close_segment(self, task_id: str, seg_id: int, end_utc: str,
                      note: str | None = None) -> None:
        self.db.execute(
            "UPDATE timer_segments SET end_utc=? WHERE id=? AND end_utc IS NULL",
            (end_utc, seg_id),
        )

    def close_orphans_for_task(self, task_id: str, end_utc: str) -> int:
        cur = self.db.execute(
            """UPDATE timer_segments SET end_utc=?, recovered=1
               WHERE task_id=? AND end_utc IS NULL""",
            (end_utc, task_id),
        )
        return cur.rowcount

    def sum_totals(self, task_id: str) -> dict[str, int]:
        rows = self.db.query(
            """SELECT kind,
                      SUM(ROUND((julianday(CASE WHEN end_utc IS NULL THEN start_utc ELSE end_utc END)
                          - julianday(start_utc)) * 86400000.0)) AS ms
               FROM timer_segments WHERE task_id=? GROUP BY kind""",
            (task_id,),
        )
        out = {k.value: 0 for k in SegmentKind}
        for r in rows:
            out[r["kind"]] = int(r["ms"] or 0)
        return out

    def open_segments(self) -> list[sqlite3.Row]:
        return self.db.query("SELECT * FROM timer_segments WHERE end_utc IS NULL")


class EventRepo:
    def __init__(self, db: Database):
        self.db = db

    def add(self, task_id: str | None, kind: str, message: str,
            level: str = "info") -> None:
        self.db.execute(
            "INSERT INTO task_events (task_id,ts_utc,level,kind,message) VALUES (?,?,?,?,?)",
            (task_id, _iso(_dt.datetime.now(UTC)), level, kind, message),
        )

    def recent(self, task_id: str | None = None, limit: int = 200) -> list[sqlite3.Row]:
        if task_id:
            return self.db.query(
                "SELECT * FROM task_events WHERE task_id=? ORDER BY id DESC LIMIT ?",
                (task_id, limit))
        return self.db.query("SELECT * FROM task_events ORDER BY id DESC LIMIT ?", (limit,))

    def logs_for(self, task_id: str, last_n: int) -> list[str]:
        rows = self.db.query(
            "SELECT level, kind, message FROM task_events WHERE task_id=? "
            "ORDER BY id DESC LIMIT ?", (task_id, max(1, min(last_n, 1000))))
        return [f"[{r['level']}] {r['kind']}: {r['message']}" for r in reversed(rows)]


class MetricsRepo:
    def __init__(self, db: Database, keep_per_task: int = 240):
        self.db = db
        self.keep = keep_per_task

    def add(self, task_id: str, cpu: float | None, ram_mb: float | None) -> None:
        self.db.execute(
            "INSERT INTO metric_samples (task_id,ts_utc,cpu_percent,ram_mb) VALUES (?,?,?,?)",
            (task_id, _iso(_dt.datetime.now(UTC)), cpu, ram_mb))
        self.db.execute(
            """DELETE FROM metric_samples WHERE task_id=? AND id NOT IN
               (SELECT id FROM metric_samples WHERE task_id=? ORDER BY id DESC LIMIT ?)""",
            (task_id, task_id, self.keep))

    def history(self, task_id: str, limit: int = 120) -> list[sqlite3.Row]:
        return self.db.query(
            "SELECT * FROM metric_samples WHERE task_id=? ORDER BY id DESC LIMIT ?",
            (task_id, limit))


class NotificationRepo:
    def __init__(self, db: Database):
        self.db = db

    def add(self, category: str, title: str, body: str = "", task_id: str | None = None,
            actions: list[dict] | None = None) -> str:
        nid = new_id()
        self.db.execute(
            "INSERT INTO notifications (id,ts_utc,task_id,category,title,body,actions_json) "
            "VALUES (?,?,?,?,?,?,?)",
            (nid, _iso(_dt.datetime.now(UTC)), task_id, category, title, body,
             json.dumps(actions or [])),
        )
        return nid

    def unread_count(self) -> int:
        row = self.db.query("SELECT COUNT(*) AS c FROM notifications WHERE read=0")
        return int(row[0]["c"]) if row else 0

    def recent(self, limit: int = 100) -> list[sqlite3.Row]:
        return self.db.query("SELECT * FROM notifications ORDER BY ts_utc DESC LIMIT ?", (limit,))

    def mark_read(self, nid: str) -> None:
        self.db.execute("UPDATE notifications SET read=1 WHERE id=?", (nid,))

    def mark_all_read(self) -> None:
        self.db.execute("UPDATE notifications SET read=1")


class DeviceRepo:
    def __init__(self, db: Database):
        self.db = db

    def add(self, device_id: str, name: str, token_hash: str,
            permissions: list[str]) -> None:
        count = self.db.query("SELECT COUNT(*) AS c FROM devices WHERE revoked=0")[0]["c"]
        if count >= 8:
            raise RuntimeError("maximum number of paired devices reached (8)")
        self.db.execute(
            "INSERT INTO devices (device_id,name,paired_utc,token_hash,permissions) "
            "VALUES (?,?,?,?,?)",
            (device_id, name, _iso(_dt.datetime.now(UTC)), token_hash,
             json.dumps(permissions)),
        )

    def all(self) -> list[sqlite3.Row]:
        return self.db.query("SELECT * FROM devices ORDER BY paired_utc")

    def find_active(self, device_id: str) -> sqlite3.Row | None:
        rows = self.db.query(
            "SELECT * FROM devices WHERE device_id=? AND revoked=0", (device_id,))
        return rows[0] if rows else None

    def touch(self, device_id: str) -> None:
        self.db.execute("UPDATE devices SET last_seen_utc=? WHERE device_id=?",
                        (_iso(_dt.datetime.now(UTC)), device_id))

    def revoke(self, device_id: str) -> None:
        self.db.execute("UPDATE devices SET revoked=1 WHERE device_id=?", (device_id,))


class AuditRepo:
    def __init__(self, db: Database):
        self.db = db

    def add(self, actor: str, action: str, detail: str = "") -> None:
        self.db.execute(
            "INSERT INTO audit_log (ts_utc,actor,action,detail) VALUES (?,?,?,?)",
            (_iso(_dt.datetime.now(UTC)), actor, action, detail))


class SettingsRepo:
    def __init__(self, db: Database):
        self.db = db

    def get(self, key: str, default: str | None = None) -> str | None:
        rows = self.db.query("SELECT value FROM settings WHERE key=?", (key,))
        return rows[0]["value"] if rows else default

    def set(self, key: str, value: str) -> None:
        self.db.execute(
            "INSERT INTO settings (key,value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


class RecoveryRepo:
    """Meta keys used for crash-safe recovery."""
    def __init__(self, db: Database):
        self.db = db

    def set_shutdown_clean(self, clean: bool) -> None:
        self.db.execute(
            "INSERT INTO meta (key,value) VALUES ('shutdown_clean',?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            ("1" if clean else "0",))

    def was_shutdown_clean(self) -> bool:
        rows = self.db.query("SELECT value FROM meta WHERE key='shutdown_clean'")
        return bool(rows) and rows[0]["value"] == "1"
