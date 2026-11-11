"""CYBER WORKSPACE — Terminal task adapter.

Runs a persistent interactive shell (PowerShell / cmd / custom) as an
independent OS process with captured I/O shown in the task detail view. The
shell's lifetime IS the task; when the shell exits the outcome cannot be
verified — the task is marked UNKNOWN, never COMPLETED (master rule §7).
"""
from __future__ import annotations

import os
import subprocess
import threading
import time as _time

from .base import ActivityMode, ExitEvidence, TaskAdapter

SHELLS = {
    "powershell": ["powershell.exe", "-NoLogo"],
    "pwsh": ["pwsh", "-NoLogo"],
    "cmd": ["cmd.exe"],
}


class TerminalAdapter(TaskAdapter):
    kind = "terminal"

    def __init__(self, task, config: dict):
        super().__init__(task, config)
        self.activity_mode = ActivityMode.VERIFIED_WHEN_ALIVE
        self.exit_evidence = ExitEvidence.NONE
        self.capabilities = {"pause": False, "restart": True, "logs": True, "stdin": True}
        self._proc: subprocess.Popen | None = None
        self._exit_reported = False
        self._stdin_lock = threading.Lock()

    def _command(self) -> list[str]:
        shell = self.config.get("shell", "powershell")
        if shell in SHELLS:
            base = list(SHELLS[shell])
        else:
            base = [str(shell)]
        extra = self.config.get("args") or []
        if not isinstance(extra, list):
            raise ValueError("args must be a list")
        return base + [str(a) for a in extra]

    def start(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            raise RuntimeError("terminal already running")
        self._proc = subprocess.Popen(
            self._command(), cwd=self.config.get("workdir") or None,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
        self._exit_reported = False
        self.task.log("terminal started: " + " ".join(self._command()))
        threading.Thread(target=self._pump, daemon=True,
                         name=f"cw-term-{self.task.cfg.id[:8]}").start()

    def stop(self, timeout: float = 8.0) -> None:
        proc, self._proc = self._proc, None
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.terminate()
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
        return None

    def describe(self) -> dict:
        return {"app": os.path.basename(self._command()[0]), "detail": "interactive shell"}

    def reattach(self, pid: int) -> bool:
        return False  # interactive shell pipes cannot be re-adopted; honest limitation

    def _pump(self) -> None:
        try:
            for raw in iter(self._proc.stdout.readline, ""):
                if not raw:
                    break
                self.task.emit("log", raw.rstrip("\r\n")[:400])
        except (ValueError, OSError):
            pass
        finally:
            try:
                self._proc.stdout.close()
            except Exception:
                pass

    def send_stdin(self, line: str) -> None:
        if self._proc is None or self._proc.poll() is not None:
            return
        try:
            with self._stdin_lock:
                self._proc.stdin.write(line.rstrip("\n") + "\n")
                self._proc.stdin.flush()
        except (OSError, ValueError) as exc:
            self.task.log(f"stdin failed: {exc}", "warning")
