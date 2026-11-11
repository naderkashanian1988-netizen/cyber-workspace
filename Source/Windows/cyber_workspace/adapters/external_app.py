"""CYBER WORKSPACE — External application task adapter.

Launches an arbitrary external application as an independent, supervised OS
process. Per the master spec we do NOT force fragile window embedding: the
application keeps its own window; the workspace supervises the process
(liveness, exit, CPU/RAM) and can terminate it safely.

Honesty: a GUI app's "active work" cannot be verified, so its timer bucket is
UNKNOWN while running (never fabricated as active). When the process exits,
the outcome cannot be verified either — state UNKNOWN, never COMPLETED.
"""
from __future__ import annotations

import os
import subprocess
import sys

import psutil

from .base import ActivityMode, ExitEvidence, TaskAdapter

_CREATIONFLAGS = 0x00000008 if sys.platform == "win32" else 0  # DETACHED_PROCESS


class ExternalAppAdapter(TaskAdapter):
    kind = "external"

    def __init__(self, task, config: dict):
        super().__init__(task, config)
        self.activity_mode = ActivityMode.UNVERIFIABLE
        self.exit_evidence = ExitEvidence.NONE
        self.capabilities = {"pause": False, "restart": True, "logs": True, "stdin": False}
        self._proc: subprocess.Popen | None = None
        self._attached_ps: psutil.Process | None = None
        self._exit_reported = False

    def _command(self) -> list[str]:
        exe = self.config.get("exe") or ""
        if not exe:
            raise ValueError("exe is required")
        args = self.config.get("args") or []
        if not isinstance(args, list):
            raise ValueError("args must be a list")
        return [str(exe)] + [str(a) for a in args]

    def start(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            raise RuntimeError("application already running")
        self._proc = subprocess.Popen(
            self._command(), cwd=self.config.get("workdir") or None,
            creationflags=_CREATIONFLAGS, close_fds=True,
        )
        self._attached_ps = None
        self._exit_reported = False
        self.task.log("launched: " + " ".join(self._command()))

    def stop(self, timeout: float = 8.0) -> None:
        proc, self._proc = self._proc, None
        self._attached_ps = None
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.terminate()  # graceful WM_CLOSE-equivalent on Windows
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        except Exception as exc:
            self.task.log(f"stop error: {exc}", "warning")

    def poll(self) -> None:
        if self._proc is None or self._exit_reported:
            return
        rc = self._proc.poll()
        if rc is not None:
            self._exit_reported = True
            self.task.emit("exit", rc)

    def pid(self) -> int | None:
        if self._proc and self._proc.poll() is None:
            return self._proc.pid
        if self._attached_ps is not None:
            try:
                if self._attached_ps.is_running():
                    return self._attached_ps.pid
            except psutil.Error:
                pass
        return None

    def describe(self) -> dict:
        return {"app": os.path.basename(self._command()[0]), "detail": "external application"}

    def reattach(self, pid: int) -> bool:
        try:
            p = psutil.Process(pid)
            if not p.is_running():
                return False
            # verify the binary roughly matches what this task would launch
            expected = os.path.basename(self._command()[0]).lower()
            actual = os.path.basename(p.exe() or "").lower()
            if expected and actual and expected != actual:
                self.task.log(f"pid {pid} no longer matches expected app "
                              f"({actual} != {expected}); not adopting", "warning")
                return False
            self._attached_ps = p
            self._exit_reported = False
            self.task.log(f"re-attached to surviving application pid={pid} "
                          "(monitoring only)", "warning")
            return True
        except psutil.Error:
            return False
