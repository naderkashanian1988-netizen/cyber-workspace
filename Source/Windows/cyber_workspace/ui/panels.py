"""CYBER WORKSPACE — dashboard panels: overview, network, power, notifications.

All values shown come from real measurements (psutil / probes); anything not
measurable is displayed as "n/a" — the UI never invents numbers.
"""
from __future__ import annotations

import time as _time

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QProgressBar, QPushButton, QVBoxLayout, QWidget)

from ..core.engine import TaskEngine
from . import theme
from .task_card import fmt_ms


def panel(title: str) -> tuple[QFrame, QVBoxLayout]:
    f = QFrame()
    f.setObjectName("Panel")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(12, 10, 12, 10)
    lbl = QLabel(title.upper())
    lbl.setObjectName("PanelTitle")
    lay.addWidget(lbl)
    return f, lay


class OverviewPanel(QWidget):
    """Workspace overview: task counters + CPU/RAM gauges + system status."""

    def __init__(self, engine: TaskEngine, parent: QWidget | None = None):
        super().__init__(parent)
        self.engine = engine
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        f, lay = panel("Workspace overview")
        self._counts = QLabel("")
        self._counts.setObjectName("Mono")
        self._keep = QLabel("")
        self._keep.setWordWrap(True)
        self._server = QLabel("")
        self._server.setObjectName("MonoDim")
        self._server.setWordWrap(True)
        lay.addWidget(self._counts)
        lay.addWidget(self._keep)
        lay.addWidget(self._server)
        root.addWidget(f, 2)

        f2, lay2 = panel("System resources")
        grid = QGridLayout()
        self._cpu_bar = QProgressBar()
        self._ram_bar = QProgressBar()
        self._cpu_val = QLabel("CPU n/a")
        self._cpu_val.setObjectName("Mono")
        self._ram_val = QLabel("RAM n/a")
        self._ram_val.setObjectName("Mono")
        grid.addWidget(QLabel("CPU"), 0, 0)
        grid.addWidget(self._cpu_bar, 0, 1)
        grid.addWidget(self._cpu_val, 0, 2)
        grid.addWidget(QLabel("RAM"), 1, 0)
        grid.addWidget(self._ram_bar, 1, 1)
        grid.addWidget(self._ram_val, 1, 2)
        lay2.addLayout(grid)
        self._uptime = QLabel("")
        self._uptime.setObjectName("MonoDim")
        lay2.addWidget(self._uptime)
        root.addWidget(f2, 2)

    def refresh(self, sys_status: dict) -> None:
        tasks = self.engine.tasks.values()
        n_run = sum(1 for t in tasks if t.state == "RUNNING")
        n_wait = sum(1 for t in tasks if t.state in ("WAITING_FOR_USER", "NETWORK_WAITING"))
        n_done = sum(1 for t in tasks if t.state == "COMPLETED")
        n_fail = sum(1 for t in tasks if t.state in ("ERROR", "UNRESPONSIVE"))
        self._counts.setText(
            f"ACTIVE {n_run}   WAITING {n_wait}   COMPLETED {n_done}   FAILED {n_fail}"
            f"   TOTAL {len(self.engine.tasks)}")
        ka = sys_status.get("keep_awake_active", False)
        self._keep.setText(
            "☕ KEEP-AWAKE ACTIVE — system sleep is being prevented while selected "
            "tasks run. Display-off does NOT stop tasks. Sleep/hibernate WILL suspend "
            "them." if ka else
            "Keep-awake inactive (enable per task with ☕ or in the Power panel).")
        self._keep.setStyleSheet(
            f"color: {theme.NEON};" if ka else f"color: {theme.TEXT_DIM};")
        self._server.setText(f"started {self.engine._started_utc} · "
                             f"tasks limit {self.engine.settings['max_tasks']}")
        cpu = sys_status.get("cpu_percent")
        ram = sys_status.get("ram_percent")
        if cpu is not None:
            self._cpu_bar.setValue(int(cpu))
            self._cpu_val.setText(f"CPU {cpu:.0f}%")
        else:
            self._cpu_val.setText("CPU n/a")
        if ram is not None:
            self._ram_bar.setValue(int(ram))
            self._ram_val.setText(f"RAM {ram:.0f}%")
        else:
            self._ram_val.setText("RAM n/a")


class NetworkPanel(QWidget):
    """Live network dashboard: real measured speeds + TCP-connect latency."""

    def __init__(self, engine: TaskEngine, parent: QWidget | None = None):
        super().__init__(parent)
        self.engine = engine
        f, lay = panel("Network monitor")
        self._down = QLabel("down: n/a")
        self._up = QLabel("up: n/a")
        self._lat = QLabel("latency (TCP): n/a")
        self._status = QLabel("status: UNKNOWN")
        self._note = QLabel("Per-task network attribution is not reliably measurable "
                            "without elevated system APIs — per-task values are shown "
                            "as n/a unless an adapter self-reports. Network speed alone "
                            "never diagnoses a task failure; the engine combines network, "
                            "process, activity and log evidence, and reports UNKNOWN "
                            "when the cause cannot be determined.")
        self._note.setWordWrap(True)
        self._note.setObjectName("MonoDim")
        for lbl in (self._down, self._up, self._lat, self._status):
            lbl.setObjectName("Mono")
        lay.addWidget(self._down)
        lay.addWidget(self._up)
        lay.addWidget(self._lat)
        lay.addWidget(self._status)
        lay.addWidget(self._note)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(f)

    @staticmethod
    def _fmt_bps(v: float | None) -> str:
        if v is None:
            return "n/a"
        for unit in ("B/s", "KB/s", "MB/s"):
            if v < 1024 or unit == "MB/s":
                return f"{v:.0f} {unit}" if unit == "B/s" else f"{v / 1024:.1f} {unit}"
            v /= 1024
        return "n/a"

    def refresh(self) -> None:
        net = self.engine.net
        color = {"UP": theme.NEON, "DOWN": theme.RED}.get(net["status"], theme.GRAY)
        self._down.setText(f"down: {self._fmt_bps(net['down_bps'])}")
        self._up.setText(f"up: {self._fmt_bps(net['up_bps'])}")
        lat = net["latency_ms"]
        self._lat.setText(f"latency (TCP connect): {lat:.1f} ms" if lat is not None
                          else "latency (TCP connect): n/a")
        self._status.setText(f"status: {net['status']}")
        self._status.setStyleSheet(f"color: {color}; font-weight: 600;")


class PowerPanel(QWidget):
    """Power & sleep quick access + KEEP-AWAKE feature (TEST G)."""

    open_power = Signal()
    open_screensaver = Signal()
    open_display = Signal()

    def __init__(self, engine: TaskEngine, parent: QWidget | None = None):
        super().__init__(parent)
        self.engine = engine
        f, lay = panel("Power & sleep")
        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._explain = QLabel(
            "How this works: the keep-awake switch uses the supported Windows API "
            "SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED) — a "
            "TEMPORARY override. Permanent power plans are never modified, and "
            "normal power behaviour is restored when disabled or on exit.\n\n"
            "Facts you should know:\n"
            "• Turning off the display does NOT stop your tasks.\n"
            "• System Sleep or Hibernate WILL suspend task execution — this "
            "workspace cannot prevent that, and we do not claim uninterrupted "
            "execution during sleep, hibernate or shutdown.\n"
            "• Standby capabilities of this machine are listed below (powercfg /a).")
        self._explain.setWordWrap(True)
        self._explain.setObjectName("MonoDim")
        b1 = QPushButton("Open Power & Sleep settings")
        b2 = QPushButton("Open Screen Saver settings")
        b3 = QPushButton("Open Display settings")
        b4 = QPushButton("Show standby capabilities (powercfg /a)")
        b1.clicked.connect(self.open_power.emit)
        b2.clicked.connect(self.open_screensaver.emit)
        b3.clicked.connect(self.open_display.emit)
        b4.clicked.connect(self._show_standby)
        lay.addWidget(self._status)
        lay.addWidget(self._explain)
        row = QHBoxLayout()
        for b in (b1, b2, b3):
            row.addWidget(b)
        lay.addLayout(row)
        lay.addWidget(b4)
        self._standby = QLabel("")
        self._standby.setObjectName("MonoDim")
        self._standby.setWordWrap(True)
        lay.addWidget(self._standby)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(f)

    def refresh(self) -> None:
        active = self.engine.keep_awake_active
        self._status.setText(
            "☕ KEEP WINDOWS AWAKE: ACTIVE — selected running tasks are keeping the "
            "system awake." if active else
            "☕ KEEP WINDOWS AWAKE: off — enable per task (card ☕ button). Windows "
            "stays awake only while a task with ☕ is RUNNING.")
        self._status.setStyleSheet(
            f"color: {theme.NEON}; font-weight: 600;" if active
            else f"color: {theme.TEXT_DIM};")

    def _show_standby(self) -> None:
        from ..platform.power import PowerManager
        out = PowerManager.standby_capabilities()
        self._standby.setText(out or "powercfg /a unavailable on this system.")


class NotificationCenterPanel(QWidget):
    """Notification center: click opens ONLY the relevant task (spec §8)."""

    open_task = Signal(str)
    approve_requested = Signal(str)   # request_id
    deny_requested = Signal(str)

    def __init__(self, engine: TaskEngine, parent: QWidget | None = None):
        super().__init__(parent)
        self.engine = engine
        f, lay = panel("Notification center")
        self._unread = QLabel("")
        self._unread.setObjectName("Mono")
        self._list = QVBoxLayout()
        self._list.setSpacing(6)
        lay.addWidget(self._unread)
        lay.addLayout(self._list)
        clear = QPushButton("Mark all read")
        clear.clicked.connect(self._mark_all)
        lay.addWidget(clear)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(f)

    def refresh(self) -> None:
        while self._list.count():
            item = self._list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        rows = self.engine.notif_repo.recent(40)
        unread = sum(1 for r in rows if not r["read"])
        self._unread.setText(f"{unread} unread · showing latest {len(rows)}")
        for r in rows:
            self._list.addWidget(self._row(r))

    def _row(self, r) -> QFrame:
        f = QFrame()
        f.setObjectName("Panel")
        lay = QHBoxLayout(f)
        lay.setContentsMargins(8, 6, 8, 6)
        color = {"approval_required": theme.AMBER, "task_error": theme.RED,
                 "task_crashed": theme.RED, "task_unresponsive": theme.RED,
                 "network_interruption": theme.CYAN, "task_completed": theme.NEON_DIM,
                 "security_warning": theme.RED, "recovery_required": theme.CYAN,
                 "permission_required": theme.AMBER}.get(r["category"], theme.TEXT_DIM)
        title = QLabel(f"● {r['title']}")
        title.setStyleSheet(f"color: {color}; font-weight: 600;")
        title.setWordWrap(True)
        body = QLabel(r["body"])
        body.setObjectName("MonoDim")
        body.setWordWrap(True)
        left = QVBoxLayout()
        left.addWidget(title)
        left.addWidget(body)
        lay.addLayout(left, 1)
        actions = []
        try:
            import json
            actions = json.loads(r["actions_json"] or "[]")
        except json.JSONDecodeError:
            actions = []
        for a in actions:
            b = QPushButton(a["label"])
            b.setObjectName("Primary" if a["id"] == "approve" else "")
            b.clicked.connect(lambda _=False, nid=r["id"], aid=a["id"]: self._action(nid, aid))
            lay.addWidget(b)
        open_btn = QPushButton("Open")
        open_btn.clicked.connect(lambda _=False, tid=r["task_id"]: self._open(tid))
        open_btn.setEnabled(bool(r["task_id"]))
        lay.addWidget(open_btn)
        if r["read"]:
            f.setStyleSheet("opacity: 0.7;")
        return f

    def _action(self, notif_id: str, action: str) -> None:
        row = self.engine.notif_repo
        # find pending approval of the task this notification belongs to
        rows = self.engine.notif_repo.recent(100)
        task_id = next((r["task_id"] for r in rows if r["id"] == notif_id), None)
        task = self.engine.tasks.get(task_id or "")
        req = task.pending_approval if task else None
        if req:
            (self.approve_requested if action == "approve" else self.deny_requested).emit(req.id)
        row.mark_read(notif_id)
        self.refresh()

    def _open(self, task_id: str) -> None:
        self.engine.notif_repo.mark_all_read()
        self.open_task.emit(task_id)
        self.refresh()

    def _mark_all(self) -> None:
        self.engine.notif_repo.mark_all_read()
        self.refresh()
