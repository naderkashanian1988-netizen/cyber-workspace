"""CYBER WORKSPACE — main dashboard window.

Layout: header (title + rain + status LEDs + actions) · task list (left,
drag-reorderable, one independent card per task) · side panels (right:
overview, network, power, notification center) · status bar.

Engine ticking and bus draining happen in this window's timers (UI thread) —
reader threads only enqueue intents, so the engine keeps its single-writer
guarantee even with a GUI attached.
"""
from __future__ import annotations

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QMainWindow, QMessageBox, QSplitter, QStackedWidget,
                               QToolBar, QVBoxLayout, QWidget)

from ..core.engine import TaskEngine
from ..platform.power import PowerManager
from ..settings import AppSettings
from . import theme
from .dialogs import (AddTaskDialog, DevicesDialog, PairingCodeDialog,
                      RenameDialog, SettingsDialog, TaskDetailDialog)
from .panels import NetworkPanel, NotificationCenterPanel, OverviewPanel, PowerPanel
from .rain_widget import RainWidget
from .task_card import TaskCard
from .tray import TrayIcon


class TaskList(QListWidget):
    """Reorderable list of task cards. After a drag-drop the new order is
    persisted through engine.reorder()."""

    order_changed = Signal(list)


PANEL_OVERVIEW, PANEL_NETWORK, PANEL_POWER, PANEL_NOTIF = 0, 1, 2, 3


class MainWindow(QMainWindow):
    def __init__(self, engine: TaskEngine, settings: AppSettings,
                 power: PowerManager, tray: TrayIcon | None,
                 fingerprint: str | None = None,
                 pairing_provider=None):
        super().__init__()
        self.engine = engine
        self.settings = settings
        self.power = power
        self.tray = tray
        self.fingerprint = fingerprint
        self.pairing_provider = pairing_provider  # callable -> pairing code str
        self.setWindowTitle("CYBER WORKSPACE")
        self.resize(1180, 760)
        self.setStyleSheet(theme.qss())

        # ---------------- header ----------------
        header = QWidget()
        header.setObjectName("HeaderFrame")
        hlay = QHBoxLayout(header)
        hlay.setContentsMargins(14, 6, 14, 6)
        title_col = QVBoxLayout()
        t = QLabel("CYBER WORKSPACE")
        t.setObjectName("TitleLabel")
        sub = QLabel("independent task lifecycle · black + neon green")
        sub.setObjectName("SubtitleLabel")
        title_col.addWidget(t)
        title_col.addWidget(sub)
        hlay.addLayout(title_col)
        self.rain = RainWidget()
        self.rain.setEnabled(settings.rain_enabled)
        hlay.addWidget(self.rain, 1)

        self.led_net = QLabel("NET —")
        self.led_ka = QLabel("☕")
        self.led_ka.setToolTip("Keep-awake status")
        self.led_ka.setVisible(False)
        for lbl in (self.led_net, self.led_ka):
            lbl.setObjectName("Mono")
            hlay.addWidget(lbl)
        hlay.addSpacing(10)

        tb = QToolBar()
        tb.setMovable(False)
        tb.setStyleSheet(f"background: transparent; border: 0;")
        act_add = QAction("＋ Add task", self)
        act_add.triggered.connect(self._add_task)
        act_power = QAction("⚡ Power", self)
        act_power.triggered.connect(lambda: self._show_panel(PANEL_POWER))
        act_notif = QAction("🔔 Notifications", self)
        act_notif.triggered.connect(lambda: self._show_panel(PANEL_NOTIF))
        act_net = QAction("📶 Network", self)
        act_net.triggered.connect(lambda: self._show_panel(PANEL_NETWORK))
        act_devices = QAction("📱 Devices", self)
        act_devices.triggered.connect(self._devices)
        act_pair = QAction("🔑 Pair new device", self)
        act_pair.triggered.connect(self._pair_new)
        act_settings = QAction("⚙ Settings", self)
        act_settings.triggered.connect(self._settings)
        act_exit = QAction("Exit", self)
        act_exit.triggered.connect(self._exit)
        for a in (act_add, act_power, act_notif, act_net, act_devices,
                  act_pair, act_settings, act_exit):
            tb.addAction(a)
        hlay.addWidget(tb)
        self.addToolBarBreak()
        # place header as central top widget
        top = QWidget()
        v = QVBoxLayout(top)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(header)

        # ---------------- body ----------------
        self.list = TaskList()
        self.list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        try:  # tolerate rebuilds
            self.list.order_changed.connect(self._reordered)
        except Exception:
            pass
        self.list.model().rowsMoved.connect(self._rows_moved)

        self.stack = QStackedWidget()
        self.overview = OverviewPanel(engine)
        self.network = NetworkPanel(engine)
        self.power_panel = PowerPanel(engine)
        self.power_panel.open_power.connect(lambda: self.power.open_power_settings())
        self.power_panel.open_screensaver.connect(lambda: self.power.open_screen_saver_settings())
        self.power_panel.open_display.connect(lambda: self.power.open_display_settings())
        self.notif_panel = NotificationCenterPanel(engine)
        self.notif_panel.open_task.connect(self._open_task)
        self.notif_panel.approve_requested.connect(
            lambda rid: self.engine.approve(rid, "approve", actor="local"))
        self.notif_panel.deny_requested.connect(
            lambda rid: self.engine.approve(rid, "deny", actor="local"))
        for w in (self.overview, self.network, self.power_panel, self.notif_panel):
            self.stack.addWidget(w)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(self.list)
        split.addWidget(self.stack)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        v.addWidget(split, 1)
        self.setCentralWidget(top)

        self.statusBar().showMessage("engine ready")

        # ---------------- timers ----------------
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(1000)
        self._tick_timer.timeout.connect(self._on_tick)
        self._tick_timer.start()
        self._ui_timer = QTimer(self)
        self._ui_timer.setInterval(300)
        self._ui_timer.timeout.connect(self._drain_bus)
        self._ui_timer.start()

        self._sub_id, self._bus_queue = engine.bus.subscribe()
        self._detail_dialog: TaskDetailDialog | None = None
        self._rebuild_cards()

    # ------------------------------------------------------------ tasks UI
    def _rebuild_cards(self) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        tasks = sorted(self.engine.tasks.values(), key=lambda t: t.cfg.position)
        for task in tasks:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, task.cfg.id)
            item.setSizeHint(TaskCard(task).sizeHint())
            self.list.addItem(item)
            card = TaskCard(task)
            card.clicked.connect(self._open_task)
            card.pause_clicked.connect(self._pause)
            card.resume_clicked.connect(self._resume)
            card.restart_clicked.connect(self._restart)
            card.close_clicked.connect(self._close)
            card.keepawake_toggled.connect(self._keepawake)
            self.list.setItemWidget(item, card)
        self.list.blockSignals(False)
        if self.tray:
            self.tray.refresh()

    def _refresh_card(self, task_id: str) -> None:
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == task_id:
                w = self.list.itemWidget(item)
                task = self.engine.tasks.get(task_id)
                if w and task:
                    w.update_from(task)
                return
        self._rebuild_cards()

    def _rows_moved(self, *args) -> None:  # drag-drop reorder
        order = []
        for i in range(self.list.count()):
            tid = self.list.item(i).data(Qt.ItemDataRole.UserRole)
            if tid:
                order.append(tid)
        self.engine.reorder(order)
        self.statusBar().showMessage("task order saved", 3000)

    def _reordered(self, order: list[str]) -> None:
        self.engine.reorder(order)
        self._rebuild_cards()

    def _add_task(self) -> None:
        from ..adapters import browser_available
        dlg = AddTaskDialog(self, browser_available=browser_available())
        if dlg.exec():
            vals = dlg.values()
            if not vals["name"]:
                return
            try:
                task = self.engine.add_task(vals["name"], vals["type"], vals["config"])
                self._rebuild_cards()
                self.statusBar().showMessage(f"task '{task.cfg.name}' created", 4000)
            except Exception as exc:
                QMessageBox.warning(self, "Add task failed", str(exc))

    def _task(self, task_id: str):
        return self.engine.tasks.get(task_id)

    def _open_task(self, task_id: str) -> None:
        task = self._task(task_id)
        if not task:
            return
        dlg = TaskDetailDialog(self.engine, task, self)
        dlg.exec()
        self._refresh_card(task_id)

    def _pause(self, task_id: str) -> None:
        ok, err = self.engine.pause_task(task_id)
        self._flash(err or ("paused" if ok else "cannot pause"), ok)

    def _resume(self, task_id: str) -> None:
        ok, err = self.engine.resume_task(task_id)
        self._flash(err or ("resumed" if ok else "cannot resume"), ok)

    def _restart(self, task_id: str) -> None:
        ok, err = self.engine.restart_task(task_id)
        self._flash(err or "restarted", ok)

    def _close(self, task_id: str) -> None:
        ret = QMessageBox.question(
            self, "Close task",
            "Close this task? Its process will be terminated and the outcome will "
            "be reported as UNKNOWN (never as completed).")
        if ret == QMessageBox.StandardButton.Yes:
            ok, err = self.engine.close_task(task_id)
            self._flash(err or "closed", ok)

    def _keepawake(self, task_id: str, enabled: bool) -> None:
        ok, err = self.engine.set_task_keep_awake(task_id, enabled)
        if not ok:
            self.statusBar().showMessage(err or "failed", 3000)

    def _flash(self, msg: str, ok: bool) -> None:
        self.statusBar().showMessage(("✔ " if ok else "✖ ") + msg, 4000)

    def _rename_if_needed(self, task_id: str) -> None:
        task = self._task(task_id)
        if not task:
            return
        dlg = RenameDialog(task.cfg.name, self)
        if dlg.exec():
            self.engine.rename_task(task_id, dlg.edit.text())
            self._rebuild_cards()

    def _show_panel(self, idx: int) -> None:
        self.stack.setCurrentIndex(idx)
        if idx == PANEL_NOTIF:
            self.notif_panel.refresh()
        if idx == PANEL_POWER:
            self.power_panel.refresh()

    # ------------------------------------------------------------ dialogs
    def _devices(self) -> None:
        DevicesDialog(self.engine, self.fingerprint, self).exec()

    def _pair_new(self) -> None:
        if not self.settings.remote_enabled:
            QMessageBox.information(self, "Remote access",
                                    "Enable the remote control server in Settings "
                                    "first (Settings → Remote access).")
            return
        if self.pairing_provider is None:
            QMessageBox.warning(self, "Pairing", "Pairing manager unavailable.")
            return
        code = self.pairing_provider()
        PairingCodeDialog(code, self.fingerprint or "", self).exec()

    def _settings(self) -> None:
        dlg = SettingsDialog(self.settings, self)
        if dlg.exec():
            self.settings.save(self.engine.data_dir)
            self.engine.settings.update(self.settings.engine_overrides())
            self.rain.setEnabled(self.settings.rain_enabled)
            self.statusBar().showMessage("settings saved", 3000)

    # ------------------------------------------------------------ engine I/O
    def _on_tick(self) -> None:
        self.engine.tick()

    def _drain_bus(self) -> None:
        import queue as _q
        drained = 0
        while drained < 300:
            try:
                topic, payload = self._bus_queue.get_nowait()
            except _q.Empty:
                break
            drained += 1
            try:
                if topic == "task_update":
                    tid = payload.get("task_id", "")
                    if payload.get("removed"):
                        self._rebuild_cards()
                    else:
                        self._refresh_card(tid)
                elif topic == "notification":
                    self._toast(payload)
                    if self.stack.currentIndex() == PANEL_NOTIF:
                        self.notif_panel.refresh()
                elif topic == "approval":
                    if self.stack.currentIndex() == PANEL_NOTIF:
                        self.notif_panel.refresh()
                elif topic in ("system", "network"):
                    self.overview.refresh(self.engine.system_status())
                    self.network.refresh()
                    self._led_net.setText(
                        f"NET {self.engine.net['status']}"
                        f"{' ' + format(self.engine.net['latency_ms'], '.0f') + 'ms' if self.engine.net['latency_ms'] else ''}")
                    self._led_net.setStyleSheet(
                        f"color: {theme.STATE_COLORS.get('RUNNING') if self.engine.net['status'] == 'UP' else theme.RED};")
                    self._led_ka.setVisible(self.engine.keep_awake_active)
                    self.power_panel.refresh()
            except Exception:
                pass

    def _toast(self, payload: dict) -> None:
        if self.tray:
            self.tray.toast(payload.get("title", ""), payload.get("body", ""),
                            payload.get("id", ""), payload.get("task_id") or "")
        self.statusBar().showMessage(f"notification: {payload.get('title', '')}", 4000)

    def open_task_from_tray(self, task_id: str) -> None:
        self.show()
        self.raise_()
        self._open_task(task_id)

    # ------------------------------------------------------------ exit
    def _exit(self) -> None:
        if self.settings.confirm_exit:
            ret = QMessageBox.question(
                self, "Exit CYBER WORKSPACE",
                "Exit the workspace? Running task processes will be stopped, timers "
                "and sessions are saved.")
            if ret != QMessageBox.StandardButton.Yes:
                return
        self._shutdown()

    def _shutdown(self) -> None:
        self._tick_timer.stop()
        self._ui_timer.stop()
        try:
            self.engine.shutdown()
        except Exception:
            pass
        self.close()

    def closeEvent(self, e) -> None:  # noqa: N802
        if self.tray is not None and self.isVisible() and self.settings.start_minimized:
            e.ignore()
            self.hide()
            return
        e.accept()
