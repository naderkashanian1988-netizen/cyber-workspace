"""CYBER WORKSPACE — Windows power management.

Two capabilities, both explicit and reversible:

1. KEEP-AWAKE (TEST G): while selected tasks are RUNNING, hold
   SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED) from a dedicated
   long-lived thread (the ES_CONTINUOUS flag is per-calling-thread; if the
   thread died the effect would silently vanish). This is a *temporary*
   system-awake override — permanent power plans are never modified. Normal
   behaviour is restored on disable, task stop, or workspace exit.

   Truths enforced by design:
   * Display turning off does NOT stop tasks (ES_SYSTEM_REQUIRED does not hold
     the display).
   * Sleep / hibernate WILL suspend task execution — the UI states this
     explicitly; we never promise uninterrupted execution through sleep,
     hibernate or shutdown.

2. QUICK ACCESS: opens the real Windows settings pages (Power & sleep, Screen
   saver, Standby capabilities via `powercfg /a`). No registry hacking.
"""
from __future__ import annotations

import ctypes
import logging
import subprocess
import threading

log = logging.getLogger("cyber.power")

IS_WINDOWS = __import__("platform").system() == "Windows"

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002


class PowerManager:
    """Injected into TaskEngine; safe no-op off-Windows so tests pass anywhere."""

    def __init__(self):
        self._thread: threading.Thread | None = None
        self._stop_evt = threading.Event()
        self._awake = False
        self._include_display = False
        self._last_error: str | None = None

    # ---- keep-awake core ----
    def set_keep_awake(self, enabled: bool, include_display: bool = False) -> bool:
        """Enable/disable the temporary system-awake override.
        Returns True if the platform supports it and the request was applied."""
        self._include_display = include_display
        if not IS_WINDOWS:
            self._awake = False
            return False
        if enabled:
            self._stop_evt.clear()
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._hold_loop, daemon=True,
                                                name="cw-power")
                self._thread.start()
            self._awake = True
            return True
        # disable
        self._stop_evt.set()
        self._awake = False
        return True

    def _hold_loop(self) -> None:
        flags = ES_CONTINUOUS | ES_SYSTEM_REQUIRED
        if self._include_display:
            flags |= ES_DISPLAY_REQUIRED
        try:
            ok = ctypes.windll.kernel32.SetThreadExecutionState(flags)  # type: ignore[attr-defined]
            if not ok:
                self._last_error = "SetThreadExecutionState failed"
                log.warning(self._last_error)
            while not self._stop_evt.wait(timeout=30):
                # re-assert periodically; the flag persists with ES_CONTINUOUS
                ctypes.windll.kernel32.SetThreadExecutionState(flags)  # type: ignore[attr-defined]
        finally:
            try:
                ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)  # type: ignore[attr-defined]
            except Exception:
                pass
            log.info("keep-awake released; normal power behaviour restored")

    def is_active(self) -> bool:
        return self._awake

    def last_error(self) -> str | None:
        return self._last_error

    # ---- quick access (real settings pages) ----
    @staticmethod
    def open_power_settings() -> bool:
        return PowerManager._open("control", "/name", "Microsoft.PowerOptions",
                                  "/page", "pageGlobalSettings")

    @staticmethod
    def open_screen_saver_settings() -> bool:
        return PowerManager._open("control", "/name", "Microsoft.Personalization",
                                  "/page", "pageScreenSaver")

    @staticmethod
    def open_display_settings() -> bool:
        return PowerManager._open("control", "/name", "Microsoft.Display")

    @staticmethod
    def standby_capabilities() -> str | None:
        """`powercfg /a` output (available sleep states) or None off-Windows."""
        if not IS_WINDOWS:
            return None
        try:
            out = subprocess.run(["powercfg", "/a"], capture_output=True,
                                 text=True, timeout=10, check=False)
            return (out.stdout or "") + (out.stderr or "")
        except Exception as exc:
            log.warning("powercfg /a failed: %s", exc)
            return None

    @staticmethod
    def _open(*argv: str) -> bool:
        try:
            subprocess.Popen(list(argv), close_fds=True)
            return True
        except OSError as exc:
            log.warning("could not open settings: %s", exc)
            return False
