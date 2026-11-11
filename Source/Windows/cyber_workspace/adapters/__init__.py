"""CYBER WORKSPACE — adapter registry (factory)."""
from __future__ import annotations

from .base import ActivityMode, ExitEvidence, TaskAdapter  # noqa: F401
from .script import ScriptAdapter
from .terminal import TerminalAdapter
from .external_app import ExternalAppAdapter

_registry = {
    "script": ScriptAdapter,
    "terminal": TerminalAdapter,
    "external": ExternalAppAdapter,
}


def browser_available() -> bool:
    from .browser import HAS_WEBENGINE
    return HAS_WEBENGINE


def create_adapter(task):
    t = task.cfg.type
    if t == "browser":
        from .browser import BrowserAdapter  # lazy, guarded import
        return BrowserAdapter(task, task.cfg.config)
    cls = _registry.get(t)
    if cls is None:
        raise ValueError(f"unknown task type {t!r}")
    return cls(task, task.cfg.config)
