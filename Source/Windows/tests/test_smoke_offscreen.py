"""Offscreen UI smoke test (skipped when Qt/offscreen is unavailable)."""
import os
import time
from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtWidgets")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QLockFile, QStandardPaths, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cyber_workspace.core.engine import TaskEngine          # noqa: E402
from cyber_workspace.settings import AppSettings            # noqa: E402
from cyber_workspace.ui.main_window import MainWindow       # noqa: E402
from cyber_workspace.ui.theme import qss                    # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_app_lock_uses_standard_location_enum(qapp):
    """Regression: app.main() lock file must use QStandardPaths.StandardLocation
    (not StandardPath). Covers the exact expression used in app.main()."""
    lock = QLockFile(str(Path(QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.TempLocation)) / "cyber-workspace-test.lock"))
    try:
        assert lock.tryLock(100)
    finally:
        lock.unlock()


def test_dashboard_smoke(qapp, tmp_path, fake_script):
    data = tmp_path / "ui-data"
    data.mkdir()
    eng = TaskEngine(data, settings={"unresponsive_timeout_s": 1.0,
                                     "unknown_grace_s": 0.5, "max_tasks": 12},
                     power=None)
    t1 = eng.add_task("ui smoke running", "script",
                      {"script_path": str(fake_script), "args": ["long"]})
    t2 = eng.add_task("ui smoke done", "script",
                      {"script_path": str(fake_script), "args": ["done"]})
    settings = AppSettings.load(data)
    win = MainWindow(eng, settings, power=None, tray=None)
    win.setStyleSheet(qss())
    win.show()

    deadline = time.time() + 8
    while time.time() < deadline:
        eng.tick()
        qapp.processEvents()
        if t1.state == "RUNNING" and t2.state == "COMPLETED":
            break
        time.sleep(0.05)
    qapp.processEvents()
    assert t1.state == "RUNNING"
    assert t2.state == "COMPLETED"
    assert win.list.count() == 2
    card = win.list.itemWidget(win.list.item(0))
    assert card is not None
    # notification center renders persisted rows
    win.notif_panel.refresh()
    qapp.processEvents()
    # overview refresh does not crash with real metrics
    eng._sample_metrics(time.monotonic())
    win.overview.refresh(eng.system_status())
    qapp.processEvents()
    win._shutdown()
    assert not win.isVisible()
