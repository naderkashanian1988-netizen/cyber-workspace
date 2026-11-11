"""CYBER WORKSPACE — Task adapter base classes.

An adapter owns ONE work unit's execution context. Adapters never touch other
tasks: they receive their own config and report events through the owning
Task's thread-safe emit() only. All adapter exceptions are caught by the
engine per-task (TEST B isolation).

Activity modes (timer honesty):
  verified_when_alive  — the process running IS the work evidence (scripts)
  verified_on_heartbeat — active only while the adapter reports fresh activity
                          (automation); stale → UNKNOWN bucket, long-stale →
                          UNRESPONSIVE via engine watchdog
  activity_window      — ACTIVE while last reported activity is within
                         adapter.activity_window_s (browser); never auto-marked
                         UNRESPONSIVE (idle browsing is normal)
  unverifiable         — cannot be determined (GUI apps): UNKNOWN bucket,
                         never fabricated
"""
from __future__ import annotations

import abc
from enum import Enum


class ActivityMode(str, Enum):
    VERIFIED_WHEN_ALIVE = "verified_when_alive"
    VERIFIED_ON_HEARTBEAT = "verified_on_heartbeat"
    ACTIVITY_WINDOW = "activity_window"
    UNVERIFIABLE = "unverifiable"


class ExitEvidence(str, Enum):
    NONE = "none"          # disappearing means nothing verifiable → UNKNOWN
    EXIT_CODE = "exit_code"  # real exit code semantics (scripts) → COMPLETED/ERROR


class TaskAdapter(abc.ABC):
    kind = "base"

    def __init__(self, task, config: dict):
        self.task = task
        self.config = dict(config)
        self.activity_mode = ActivityMode.VERIFIED_WHEN_ALIVE
        self.exit_evidence = ExitEvidence.NONE
        self.activity_window_s = 90.0
        self.capabilities = {"pause": False, "restart": True, "logs": True, "stdin": False}

    # ---- lifecycle ----
    @abc.abstractmethod
    def start(self) -> None: ...

    @abc.abstractmethod
    def stop(self, timeout: float = 8.0) -> None: ...

    @abc.abstractmethod
    def poll(self) -> None:
        """Called every tick: detect exit and enqueue intents. Must not raise
        for expected conditions."""

    def pause(self) -> None:
        raise RuntimeError(f"{self.kind} tasks cannot be paused")

    def resume(self) -> None:
        raise RuntimeError(f"{self.kind} tasks cannot be resumed")

    # ---- introspection ----
    @abc.abstractmethod
    def pid(self) -> int | None: ...

    def describe(self) -> dict:
        return {"app": None, "detail": ""}

    def heartbeat_age(self) -> float | None:
        return None

    def reattach(self, pid: int) -> bool:
        """Attempt to adopt a surviving OS process after workspace restart.
        Returns True if adopted (monitoring-only; control may be limited)."""
        return False

    def on_decision(self, decision: str, request: dict) -> None:
        """Approval decision delivered (only adapters that declared stdin/approval)."""
