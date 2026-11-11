"""Shared pytest fixtures: temp data dirs and engine factory."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

WIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WIN_ROOT))

from cyber_workspace.core.engine import TaskEngine          # noqa: E402
from cyber_workspace.core.events import EventBus            # noqa: E402
from cyber_workspace.settings import DEFAULTS as ENGINE_DEFAULTS  # noqa: E402


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    d = tmp_path / "cw-data"
    d.mkdir()
    return d


@pytest.fixture()
def bus() -> EventBus:
    return EventBus()


@pytest.fixture()
def make_engine(data_dir, bus):
    """Factory with fast watchdog settings for tests."""
    created: list[TaskEngine] = []

    def _make(**overrides) -> TaskEngine:
        settings = {
            "unresponsive_timeout_s": 1.0,
            "unknown_grace_s": 0.5,
            "metrics_interval_s": 0.5,
            "net_probe_target": ("127.0.0.1", 9),  # closed port → DOWN, fast
            "net_probe_interval_s": 1.0,
            "max_tasks": 12,
            "stop_timeout_s": 3.0,
        }
        settings.update(overrides)
        eng = TaskEngine(data_dir, settings=settings, bus=bus, power=None)
        created.append(eng)
        return eng

    yield _make
    for eng in created:
        try:
            eng.db.close()
        except Exception:
            pass


@pytest.fixture()
def fake_script(tmp_path: Path) -> Path:
    return Path(__file__).parent / "fake_task_scripts.py"
