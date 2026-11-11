"""CYBER WORKSPACE — task card widget (one card per task, dashboard grid item).

Shows every required field: name, app/page, status LED + chip, active work
time, waiting time, error time, CPU/RAM when measurable, last activity,
last progress, and the task controls. Clicking the card opens the detail view;
buttons act on that task only — never on siblings.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QPushButton, QVBoxLayout, QWidget)

from ..core.task import Task
from . import theme


def fmt_ms(ms: int) -> str:
    s = int(ms // 1000)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


class Led(QWidget):
    def __init__(self, color: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._color = QColor(color)
        self.setFixedSize(12, 12)

    def set_color(self, color: str) -> None:
        self._color = QColor(color)
        self.update()

    def paintEvent(self, e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        glow = QColor(self._color)
        glow.setAlpha(70)
        p.setBrush(glow)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(0, 0, 12, 12)
        p.setBrush(self._color)
        p.drawEllipse(3, 3, 6, 6)
        p.end()


class TaskCard(QFrame):
    clicked = Signal(str)          # task_id
    pause_clicked = Signal(str)
    resume_clicked = Signal(str)
    restart_clicked = Signal(str)
    close_clicked = Signal(str)
    keepawake_toggled = Signal(str, bool)

    def __init__(self, task: Task, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("TaskCard")
        self.task_id = task.cfg.id
        self._led = Led(theme.GRAY)
        title = QLabel(task.cfg.name)
        title.setObjectName("CardTitle")
        title.setWordWrap(False)
        self._app = QLabel("—")
        self._app.setObjectName("MonoDim")
        self._state_chip = QLabel("UNKNOWN")
        self._state_chip.setObjectName("StateChip")
        self._reason = QLabel("")
        self._reason.setObjectName("MonoDim")
        self._reason.setWordWrap(True)
        self._timers = QLabel("")
        self._timers.setObjectName("TimerValue")
        self._usage = QLabel("CPU n/a · RAM n/a")
        self._usage.setObjectName("MonoDim")
        self._activity = QLabel("last activity: —")
        self._activity.setObjectName("MonoDim")
        self._progress = QLabel("")
        self._progress.setObjectName("MonoDim")
        self._progress.setWordWrap(True)
        self._approve_btn = QPushButton("Open approval")
        self._approve_btn.setObjectName("Primary")
        self._approve_btn.setVisible(False)
        self._approve_btn.clicked.connect(lambda: self.clicked.emit(self.task_id))

        btn_pause = QPushButton("⏸")
        btn_pause.setToolTip("Pause this task")
        btn_resume = QPushButton("▶")
        btn_resume.setToolTip("Resume this task")
        btn_restart = QPushButton("⟳")
        btn_restart.setToolTip("Restart this task")
        btn_close = QPushButton("✕")
        btn_close.setObjectName("Danger")
        btn_close.setToolTip("Close this task (outcome will be reported as unknown)")
        btn_pause.clicked.connect(lambda: self.pause_clicked.emit(self.task_id))
        btn_resume.clicked.connect(lambda: self.resume_clicked.emit(self.task_id))
        btn_restart.clicked.connect(lambda: self.restart_clicked.emit(self.task_id))
        btn_close.clicked.connect(lambda: self.close_clicked.emit(self.task_id))
        self._btn_pause, self._btn_resume = btn_pause, btn_resume
        self._keep_btn = QPushButton("☕")
        self._keep_btn.setToolTip("Keep system awake while this task runs")
        self._keep_btn.setCheckable(True)
        self._keep_btn.toggled.connect(
            lambda on: self.keepawake_toggled.emit(self.task_id, on))

        for b in (btn_pause, btn_resume, btn_restart, btn_close, self._keep_btn):
            b.setFixedWidth(34)

        head = QHBoxLayout()
        head.addWidget(self._led)
        head.addWidget(title, 1)
        head.addWidget(self._state_chip)
        head.addWidget(btn_pause)
        head.addWidget(btn_resume)
        head.addWidget(btn_restart)
        head.addWidget(self._keep_btn)
        head.addWidget(btn_close)

        grid = QGridLayout()
        grid.addWidget(self._make_label("App / page"), 0, 0)
        grid.addWidget(self._app, 0, 1)
        grid.addWidget(self._make_label("Active"), 1, 0)
        grid.addWidget(self._timers, 1, 1)
        grid.addWidget(self._make_label("Usage"), 2, 0)
        grid.addWidget(self._usage, 2, 1)
        grid.addWidget(self._make_label("Last activity"), 3, 0)
        grid.addWidget(self._activity, 3, 1)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(4)
        lay.addLayout(head)
        lay.addWidget(self._reason)
        lay.addLayout(grid)
        lay.addWidget(self._progress)
        lay.addWidget(self._approve_btn)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_from(task)

    @staticmethod
    def _make_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("MonoDim")
        return lbl

    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.task_id)
        super().mousePressEvent(e)

    def update_from(self, task: Task) -> None:
        snap = task.snapshot()
        color = theme.STATE_COLORS.get(snap["state"], theme.GRAY)
        self._led.set_color(color)
        self._state_chip.setText(snap["state"])
        self._state_chip.setStyleSheet(f"color: {color};")
        self._app.setText(snap["app"] or "—")
        reason = snap["reason"] or ""
        self._reason.setText(reason)
        self._reason.setVisible(bool(reason))
        self._timers.setText(
            f"active {fmt_ms(snap['active_ms'])}  ·  waiting {fmt_ms(snap['waiting_ms'])}"
            f"  ·  error {fmt_ms(snap['error_ms'])}")
        cpu = snap["cpu_percent"]
        ram = snap["ram_mb"]
        self._usage.setText(
            f"CPU {cpu:.1f}% · RAM {ram:.0f} MB" if cpu is not None and ram is not None
            else "CPU n/a · RAM n/a")
        self._activity.setText(f"last activity: {snap['last_activity_utc'] or '—'}")
        prog = snap["last_progress"] or ""
        self._progress.setText(prog)
        self._progress.setVisible(bool(prog))
        self._approve_btn.setVisible(snap["pending_approval"] is not None)
        self._keep_btn.setChecked(bool(snap["keep_awake"]))
        running = snap["state"] == "RUNNING"
        self._btn_pause.setEnabled(running)
        self._btn_resume.setEnabled(snap["state"] in ("PAUSED", "WAITING_FOR_USER"))
        self._keep_btn.setVisible(True)
