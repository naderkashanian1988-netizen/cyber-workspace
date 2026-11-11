"""CYBER WORKSPACE — Windows system tray integration.

Minimizing to tray NEVER suspends or terminates managed processes — the engine
and all task adapters keep running; the tray only mirrors status and provides
restore/exit. Exit is explicit and safe (engine.shutdown closes segments and
persists the session).
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from ..core.engine import TaskEngine
from . import theme


def make_tray_icon(active: int = 0) -> QIcon:
    """Programmatic neon terminal-glyph icon (no external assets needed)."""
    pm = QPixmap(32, 32)
    pm.fill(QColor(theme.BG))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QColor(theme.NEON))
    f = theme.mono_font(14, bold=True)
    p.setFont(f)
    p.drawText(6, 24, ">_")
    if active:
        p.setBrush(QColor(theme.NEON))
        p.setPen(QColor(theme.NEON))
        p.drawEllipse(23, 5, 7, 7)
    p.end()
    return QIcon(pm)


class TrayIcon(QSystemTrayIcon):
    open_task_requested = Signal(str)   # task_id from a clicked notification
    restore_requested = Signal()
    exit_requested = Signal()
    notifications_requested = Signal()

    def __init__(self, engine: TaskEngine, parent: QObject | None = None):
        super().__init__(make_tray_icon(), parent)
        self.engine = engine
        self.setToolTip("CYBER WORKSPACE")
        self._last_task_by_notification: dict[str, str] = {}
        menu = QMenu()
        self.act_restore = QAction("Restore workspace", menu)
        self.act_restore.triggered.connect(self.restore_requested.emit)
        menu.addAction(self.act_restore)
        menu.addSeparator()
        self.act_counts = QAction("0 running · 0 waiting", menu)
        self.act_counts.setEnabled(False)
        menu.addAction(self.act_counts)
        self.act_center = QAction("Notification center", menu)
        self.act_center.triggered.connect(self.notifications_requested.emit)
        menu.addAction(self.act_center)
        menu.addSeparator()
        self.act_exit = QAction("Exit workspace (safe shutdown)", menu)
        self.act_exit.triggered.connect(self.exit_requested.emit)
        menu.addAction(self.act_exit)
        self.setContextMenu(menu)
        self.messageClicked.connect(self._on_message_clicked)
        self.activated.connect(self._on_activated)

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.restore_requested.emit()

    def register_task_notification(self, notif_id: str, task_id: str) -> None:
        self._last_task_by_notification[notif_id] = task_id
        self._last_task_id = task_id

    def _on_message_clicked(self) -> None:
        task_id = getattr(self, "_last_task_id", "")
        if task_id:
            # open ONLY the relevant task — never disturb others (spec §8)
            self.open_task_requested.emit(task_id)

    def refresh(self) -> None:
        running = sum(1 for t in self.engine.tasks.values() if t.state == "RUNNING")
        waiting = sum(1 for t in self.engine.tasks.values()
                      if t.state in ("WAITING_FOR_USER", "NETWORK_WAITING"))
        self.act_counts.setText(f"{running} running · {waiting} waiting")
        self.setToolTip(f"CYBER WORKSPACE — {running} running, {waiting} waiting")
        self.setIcon(make_tray_icon(active=running))

    def toast(self, title: str, body: str, notif_id: str = "",
              task_id: str = "") -> None:
        if task_id:
            self.register_task_notification(notif_id, task_id)
        self.showMessage(title, body,
                         QSystemTrayIcon.MessageIcon.Information, 6000)
