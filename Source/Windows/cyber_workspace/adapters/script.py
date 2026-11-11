"""CYBER WORKSPACE — Script task adapter.

Runs a Python (or configured interpreter) script as an INDEPENDENT OS process
with captured stdout/stderr and a writable stdin. All launches use argv lists
(never shell=True) — there is no shell interpolation, which is the
command-injection boundary.

In-task marker protocol (scripts may print these on stdout):
  @@CW:PROGRESS@@ {"note": "step 3/10"}     → last progress + activity
  @@CW:APPROVAL@@ {"question": "...", "options": ["Yes","No"]}
                                            → WAITING_FOR_USER + notification;
                                              the decision is written to stdin as
                                              "approve <request_id>" / "deny <request_id>"
  @@CW:NETWAIT@@ {"reason": "upload failed"} → NETWORK_WAITING (self-reported)
  @@CW:NETOK@@                              → network recovered
  @@CW:HEARTBEAT@@                          → verified-activity heartbeat

Config: interpreter (default: current Python), script_path, args (list),
workdir, env (dict), require_heartbeat (bool, automation scripts).

Exit semantics (evidence-based): exit code 0 → COMPLETED; non-zero → ERROR
with the code in the reason. Nothing is invented beyond the exit code.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time as _time

import psutil

from .base import ActivityMode, ExitEvidence, TaskAdapter

MARKERS = ("@@CW:PROGRESS@@", "@@CW:APPROVAL@@", "@@CW:NETWAIT@@",
           "@@CW:NETOK@@", "@@CW:HEARTBEAT@@")


def parse_marker(line: str) -> tuple[str, dict] | None:
    for m in MARKERS:
        if line.startswith(m):
            body = line[len(m):].strip()
            try:
                data = json.loads(body) if body else {}
                return m, (data if isinstance(data, dict) else {})
            except json.JSONDecodeError:
                return m, {}
    return None


class ScriptAdapter(TaskAdapter):
    kind = "script"

    def __init__(self, task, config: dict):
        super().__init__(task, config)
        self.activity_mode = ActivityMode.VERIFIED_WHEN_ALIVE
        if config.get("require_heartbeat"):
            self.activity_mode = ActivityMode.VERIFIED_ON_HEARTBEAT
        self.exit_evidence = ExitEvidence.EXIT_CODE
        self.capabilities = {"pause": True, "restart": True, "logs": True, "stdin": True}
        self._proc: subprocess.Popen | None = None
        self._attached_ps: psutil.Process | None = None
        self._exit_reported = False
        self._last_activity = 0.0
        self._require_heartbeat = bool(config.get("require_heartbeat"))
        self._stdin_lock = threading.Lock()

    # -- helpers ----------------------------------------------------------
    def _command(self) -> list[str]:
        interpreter = self.config.get("interpreter") or sys.executable
        script = self.config.get("script_path") or ""
        if not script:
            raise ValueError("script_path is required")
        args = self.config.get("args") or []
        if not isinstance(args, list):
            raise ValueError("args must be a list")
        return [str(interpreter), str(script)] + [str(a) for a in args]

    def _env(self) -> dict | None:
        env = self.config.get("env")
        if not isinstance(env, dict) or not env:
            return None
        merged = dict(os.environ)
        for k, v in env.items():
            merged[str(k)] = str(v)
        return merged

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            raise RuntimeError("script already running")
        cmd = self._command()
        workdir = self.config.get("workdir") or None
        self._proc = subprocess.Popen(
            cmd, cwd=workdir, env=self._env(),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
        self._attached_ps = None
        self._exit_reported = False
        self._last_activity = _time.monotonic()
        self.task.log("started: " + " ".join(cmd))
        threading.Thread(target=self._pump, args=(self._proc.stdout, False),
                         daemon=True, name=f"cw-out-{self.task.cfg.id[:8]}").start()
        threading.Thread(target=self._pump, args=(self._proc.stderr, True),
                         daemon=True, name=f"cw-err-{self.task.cfg.id[:8]}").start()

    def stop(self, timeout: float = 8.0) -> None:
        proc, self._proc = self._proc, None
        self._attached_ps = None
        if proc is None or proc.poll() is not None:
            return
        try:
            with self._stdin_lock:
                try:
                    proc.stdin.close()
                except Exception:
                    pass
            proc.terminate()
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        except Exception as exc:
            self.task.log(f"stop error: {exc}", "warning")

    def pause(self) -> None:
        self._suspend(True)

    def resume(self) -> None:
        self._suspend(False)

    def _suspend(self, suspend: bool) -> None:
        target = self._proc if (self._proc and self._proc.poll() is None) else self._attached_ps
        if target is None:
            raise RuntimeError("no running process")
        p = psutil.Process(target.pid)
        (p.suspend if suspend else p.resume)()

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
        cmd = self._command()
        return {"app": os.path.basename(cmd[0]), "detail": cmd[1]}

    def heartbeat_age(self) -> float | None:
        if not self._require_heartbeat:
            return None
        return _time.monotonic() - self._last_activity

    # -- recovery ----------------------------------------------------------
    def reattach(self, pid: int) -> bool:
        try:
            p = psutil.Process(pid)
            if not p.is_running():
                return False
            self._attached_ps = p
            self._exit_reported = False
            self.task.log(f"re-attached to surviving process pid={pid} "
                          "(monitoring only; stdin/stdout lost)", "warning")
            return True
        except psutil.Error:
            return False

    # -- streams -----------------------------------------------------------
    def _pump(self, stream, is_err: bool) -> None:
        try:
            for raw in iter(stream.readline, ""):
                if not raw:
                    break
                line = raw.rstrip("\r\n")
                if is_err:
                    self.task.emit("error_log", line[:400])
                else:
                    parsed = parse_marker(line)
                    if parsed:
                        marker, data = parsed
                        if marker == "@@CW:PROGRESS@@":
                            self.task.emit("progress", str(data.get("note", ""))[:300])
                        elif marker == "@@CW:APPROVAL@@":
                            self.task.emit("approval", data)
                        elif marker == "@@CW:NETWAIT@@":
                            self.task.emit("netwait", str(data.get("reason", "unspecified")))
                        elif marker == "@@CW:NETOK@@":
                            self.task.emit("netok", None)
                        elif marker == "@@CW:HEARTBEAT@@":
                            self._last_activity = _time.monotonic()
                            self.task.emit("activity", None)
                        continue
                    self.task.emit("log", line[:400])
                self._last_activity = _time.monotonic()
        except (ValueError, OSError):
            pass  # stream closed by stop()
        finally:
            try:
                stream.close()
            except Exception:
                pass

    # -- approvals ----------------------------------------------------------
    def on_decision(self, decision: str, request: dict) -> None:
        if self._proc is None or self._proc.poll() is not None:
            self.task.log("approval decision could not be delivered: process gone", "warning")
            return
        try:
            with self._stdin_lock:
                self._proc.stdin.write(f"{decision} {request.get('id', '')}\n")
                self._proc.stdin.flush()
        except (OSError, ValueError) as exc:
            self.task.log(f"failed to deliver approval: {exc}", "warning")

    def send_stdin(self, line: str) -> None:
        """User-typed stdin from the task detail view (terminal-like control)."""
        if self._proc is None or self._proc.poll() is not None:
            return
        try:
            with self._stdin_lock:
                self._proc.stdin.write(line.rstrip("\n") + "\n")
                self._proc.stdin.flush()
        except (OSError, ValueError) as exc:
            self.task.log(f"stdin failed: {exc}", "warning")
