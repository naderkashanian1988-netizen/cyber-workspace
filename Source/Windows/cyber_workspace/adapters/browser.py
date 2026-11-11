"""CYBER WORKSPACE — Browser task adapter (QtWebEngine, gracefully optional).

QtWebEngine was selected over WebView2 for integration reasons: it is a pure
pip-installable dependency (no OS component installation step), it runs in the
UI process with a managed lifecycle, and per-tab sessions can be supervised by
the same adapter/engine interface as every other task type.

If QtWebEngine is not installed the adapter raises BrowserUnavailableError and
the UI hides the browser option with an explanation — nothing is faked.

The adapter is a thin bridge: the UI owns the QWebEngineView widget and feeds
lifecycle signals into the adapter; the engine sees a normal supervised task.
A closed tab is NOT completion — the task becomes UNKNOWN with an explicit
reason, per master rule §7.
"""
from __future__ import annotations

import time as _time

from .base import ActivityMode, ExitEvidence, TaskAdapter

try:  # guarded: optional heavy dependency
    from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
    HAS_WEBENGINE = True
except Exception:  # pragma: no cover - depends on environment
    HAS_WEBENGINE = False


class BrowserUnavailableError(RuntimeError):
    def __init__(self):
        super().__init__(
            "QtWebEngine is not available. Install PySide6 (full) with WebEngine "
            "support to enable browser tasks. Other task types are unaffected.")


class BrowserAdapter(TaskAdapter):
    kind = "browser"

    def __init__(self, task, config: dict):
        super().__init__(task, config)
        if not HAS_WEBENGINE:
            raise BrowserUnavailableError()
        self.activity_mode = ActivityMode.ACTIVITY_WINDOW
        self.activity_window_s = float(config.get("activity_window_s", 90))
        self.exit_evidence = ExitEvidence.NONE
        self.capabilities = {"pause": False, "restart": True, "logs": True, "stdin": False}
        self.url: str = str(config.get("url") or "https://example.com")
        self.profile: str = str(config.get("profile") or "default")
        self._open = False
        self._last_activity = 0.0
        # wired by the UI:
        self.on_request_open = None      # callable(url, profile)
        self.on_request_close = None     # callable()

    # -- UI bridge ----------------------------------------------------------
    def ui_open(self) -> None:
        self._open = True
        if self.on_request_open:
            self.on_request_open(self.url, self.profile)

    def ui_close(self) -> None:
        self._open = False
        self.task.emit("exit", None)

    def notify_load_started(self, url: str) -> None:
        self.url = url
        self._touch()
        self.task.emit("progress", f"loading {url[:120]}")

    def notify_load_finished(self, ok: bool, url: str = "") -> None:
        self._touch()
        if ok:
            self.task.emit("progress", f"loaded {url[:120]}")
            self.task.emit("netok", None)
        else:
            self.task.emit("netwait", f"page failed to load: {url[:120]}")

    def notify_user_input(self) -> None:
        self._touch()

    def notify_console(self, message: str) -> None:
        """JS bridge: window.cwApproval(question) logs 'CW_APPROVAL:{json}'."""
        self._touch()
        if message.startswith("CW_APPROVAL:"):
            import json
            try:
                data = json.loads(message[len("CW_APPROVAL:"):])
                self.task.emit("approval", data if isinstance(data, dict) else {})
            except json.JSONDecodeError:
                self.task.emit("error_log", "malformed CW_APPROVAL message")

    def _touch(self) -> None:
        self._last_activity = _time.monotonic()
        self.task.emit("activity", None)

    # -- engine interface ----------------------------------------------------
    def start(self) -> None:
        if not HAS_WEBENGINE:
            raise BrowserUnavailableError()
        self._open = True
        if self.on_request_open:
            self.on_request_open(self.url, self.profile)
        self.task.log(f"browser tab opened: {self.url}")

    def stop(self, timeout: float = 8.0) -> None:
        self._open = False
        if self.on_request_close:
            try:
                self.on_request_close()
            except Exception:
                pass

    def poll(self) -> None:
        pass  # tab liveness is pushed by the UI via ui_close()/notify_*

    def pid(self) -> int | None:
        return None  # in-process; renderer process is internal to QtWebEngine

    def describe(self) -> dict:
        return {"app": "browser", "detail": self.url}

    def heartbeat_age(self) -> float | None:
        return _time.monotonic() - self._last_activity if self._open else None

    def reattach(self, pid: int) -> bool:
        return False
