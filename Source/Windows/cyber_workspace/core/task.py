"""CYBER WORKSPACE — Task model.

A Task is the runtime representation of one managed unit of work: its config,
adapter, state machine slot, tri-timer, ring-buffer log, live metrics and any
pending approval. Fields written by reader threads (activity, progress, log
lines, adapter intents) are guarded by `lock`; the engine is the single writer
of state.
"""
from __future__ import annotations

import collections
import datetime as _dt
import threading
from dataclasses import dataclass, field
from typing import Any

UTC = _dt.timezone.utc

MAX_LOG_LINES = 600
MAX_INTENTS = 500


@dataclass
class ApprovalRequest:
    id: str
    task_id: str
    question: str
    options: list[str]
    created_utc: str

    def to_dict(self) -> dict:
        return {"id": self.id, "question": self.question, "options": self.options}


@dataclass
class TaskConfig:
    id: str
    name: str
    type: str
    position: int = 0
    created_utc: str = ""
    config: dict[str, Any] = field(default_factory=dict)
    keep_awake: bool = False

    def to_row(self) -> dict:
        return {
            "id": self.id, "name": self.name, "type": self.type,
            "position": self.position, "created_utc": self.created_utc,
            "config_json": json_dumps(self.config),
            "keep_awake": 1 if self.keep_awake else 0,
        }


def json_dumps(obj: Any) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


class Task:
    """One independently-managed task. One failure here never touches siblings:
    all adapter errors are captured in intents/logs and applied by the engine
    to THIS task only."""

    def __init__(self, cfg: TaskConfig):
        self.cfg = cfg
        self.state = "UNKNOWN"
        self.reason: str | None = None
        self.state_utc: str | None = None
        self.adapter: Any = None            # TaskAdapter; set by engine
        self.timer: Any = None              # TriTimer; set by engine
        self.pending_approval: ApprovalRequest | None = None
        self.minimized = False
        self.pid: int | None = None
        self.exit_code: int | None = None
        self.app_name: str | None = None
        self.last_activity_utc: str | None = None
        self.last_progress: str | None = None
        self.cpu_percent: float | None = None
        self.ram_mb: float | None = None
        self.net_bps: float | None = None   # adapter-reported when measurable; else None
        self.history: collections.deque = collections.deque(maxlen=120)  # (cpu, ram)
        self.log_ring: collections.deque = collections.deque(maxlen=MAX_LOG_LINES)
        self._intents: collections.deque = collections.deque(maxlen=MAX_INTENTS)
        self._lock = threading.Lock()
        self.dirty = True                   # snapshot changed since last broadcast
        self.last_seen_utc: str | None = None
        self.run_count = 0

    # ---------- intents (thread-safe; reader threads call these) ----------
    def emit(self, kind: str, payload: Any = None) -> None:
        with self._lock:
            self._intents.append((kind, payload))

    def drain_intents(self) -> list[tuple[str, Any]]:
        with self._lock:
            items = list(self._intents)
            self._intents.clear()
        return items

    def note_activity(self, note: str | None = None) -> None:
        self.last_activity_utc = _dt.datetime.now(UTC).isoformat(
            timespec="milliseconds").replace("+00:00", "Z")
        if note:
            self.last_progress = note[:300]
        self.dirty = True

    def log(self, message: str, level: str = "info") -> None:
        stamp = _dt.datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        with self._lock:
            self.log_ring.append(f"[{stamp}] [{level}] {message}")
        self.dirty = True

    def logs_tail(self, n: int = 200) -> list[str]:
        with self._lock:
            items = list(self.log_ring)
        return items[-max(1, min(n, MAX_LOG_LINES)):]

    # ---------- snapshot ----------
    def snapshot(self, timer_totals: dict | None = None) -> dict:
        t = timer_totals or (self.timer.snapshot() if self.timer else
                             {"active_ms": 0, "waiting_ms": 0, "error_ms": 0,
                              "paused_ms": 0, "unknown_ms": 0})
        return {
            "id": self.cfg.id,
            "name": self.cfg.name,
            "type": self.cfg.type,
            "state": self.state,
            "reason": self.reason,
            "active_ms": t["active_ms"],
            "waiting_ms": t["waiting_ms"],
            "error_ms": t["error_ms"],
            "paused_ms": t["paused_ms"],
            "unknown_ms": t["unknown_ms"],
            "cpu_percent": self.cpu_percent,
            "ram_mb": self.ram_mb,
            "last_activity_utc": self.last_activity_utc,
            "last_progress": self.last_progress,
            "keep_awake": self.cfg.keep_awake,
            "minimized": self.minimized,
            "pid": self.pid,
            "app": self.app_name,
            "created_utc": self.cfg.created_utc,
            "pending_approval": self.pending_approval.to_dict() if self.pending_approval else None,
        }
