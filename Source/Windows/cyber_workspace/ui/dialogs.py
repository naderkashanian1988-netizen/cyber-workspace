"""CYBER WORKSPACE — dialogs: add task, rename, devices, settings, task detail.

Every dialog is scoped to exactly the task/device it names. Sensitive actions
(revoke device, remove task, exit) require explicit confirmation.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
                               QPlainTextEdit, QPushButton, QSpinBox, QVBoxLayout,
                               QWidget)

from ..core.engine import TaskEngine
from ..core.task import Task
from ..settings import AppSettings
from . import theme
from .task_card import fmt_ms


class AddTaskDialog(QDialog):
    """Create a task of one of the four supported types."""

    def __init__(self, parent: QWidget | None = None,
                 browser_available: bool = True):
        super().__init__(parent)
        self.setWindowTitle("Add task — CYBER WORKSPACE")
        self.setMinimumWidth(460)
        self.browser_ok = browser_available
        form = QFormLayout(self)
        self.name = QLineEdit()
        self.name.setPlaceholderText("e.g. Nightly report build")
        form.addRow("Task name", self.name)
        self.type_box = QComboBox()
        self.type_box.addItems(["script", "terminal", "external", "browser"])
        if not browser_available:
            self.type_box.setItemData(3, 0, Qt.ItemDataRole.Role_Disabled)
            note = QLabel("Browser tasks need PySide6 (QtWebEngine). The option is "
                          "disabled because WebEngine is unavailable in this install.")
            note.setWordWrap(True)
            note.setObjectName("MonoDim")
            form.addRow(note)
        form.addRow("Type", self.type_box)
        # dynamic field rows
        self.lbl_a = QLabel("Script path")
        self.field_a = QLineEdit()
        self.field_a.setPlaceholderText("C:\\tasks\\report.py or a command path")
        self.lbl_b = QLabel("Arguments (space-separated)")
        self.field_b = QLineEdit()
        self.lbl_c = QLabel("Working directory (optional)")
        self.field_c = QLineEdit()
        self.lbl_d = QLabel("Interpreter (optional, for scripts)")
        self.field_d = QLineEdit()
        self.field_d.setPlaceholderText("defaults to this workspace's Python")
        self.chk_heartbeat = QCheckBox("Require heartbeat (automation scripts)")
        self.chk_heartbeat.setToolTip("Verification mode: active time counts only "
                                      "while the script reports recent activity.")
        form.addRow(self.lbl_a, self.field_a)
        form.addRow(self.lbl_b, self.field_b)
        form.addRow(self.lbl_c, self.field_c)
        form.addRow(self.lbl_d, self.field_d)
        form.addRow(self.chk_heartbeat)
        self.type_box.currentTextChanged.connect(self._type_changed)
        self._type_changed("script")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _type_changed(self, t: str) -> None:
        labels = {"script": ("Script path", "Arguments", "Working directory",
                             "Interpreter"),
                  "terminal": ("Shell (powershell/cmd/pwsh/path)", "Shell args",
                               "Working directory", "—"),
                  "external": ("Executable path", "Arguments", "Working directory", "—"),
                  "browser": ("URL", "—", "—", "—")}
        a, b, c, d = labels.get(t, ("", "", "", ""))
        self.lbl_a.setText(a)
        self.lbl_b.setText(b)
        self.lbl_c.setText(c)
        self.lbl_d.setText(d)
        self.field_d.setEnabled(t == "script")
        self.chk_heartbeat.setVisible(t == "script")

    def values(self) -> dict:
        t = self.type_box.currentText()
        cfg: dict = {}
        a = self.field_a.text().strip()
        args = [x for x in self.field_b.text().split() if x]
        cwd = self.field_c.text().strip() or None
        if t == "script":
            cfg = {"script_path": a, "args": args, "workdir": cwd,
                   "require_heartbeat": self.chk_heartbeat.isChecked()}
            if self.field_d.text().strip():
                cfg["interpreter"] = self.field_d.text().strip()
        elif t == "terminal":
            cfg = {"shell": a or "powershell", "args": args, "workdir": cwd}
        elif t == "external":
            cfg = {"exe": a, "args": args, "workdir": cwd}
        elif t == "browser":
            cfg = {"url": a or "https://example.com"}
        return {"name": self.name.text().strip(), "type": t, "config": cfg}


class RenameDialog(QDialog):
    def __init__(self, current: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Rename task")
        self.edit = QLineEdit(current)
        form = QFormLayout(self)
        form.addRow("New name", self.edit)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)


class DevicesDialog(QDialog):
    """Paired Android devices: show fingerprint + revoke (audit-logged)."""

    def __init__(self, engine: TaskEngine, fingerprint: str | None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.engine = engine
        self.setWindowTitle("Paired devices — CYBER WORKSPACE")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        if fingerprint:
            fp = QLabel("TLS certificate fingerprint (must match the Android app):")
            fp.setObjectName("MonoDim")
            val = QLabel(fingerprint)
            val.setObjectName("Mono")
            val.setWordWrap(True)
            lay.addWidget(fp)
            lay.addWidget(val)
        self.list = QListWidget()
        lay.addWidget(self.list)
        self.revoke = QPushButton("Revoke selected device")
        self.revoke.setObjectName("Danger")
        self.revoke.clicked.connect(self._revoke)
        lay.addWidget(self.revoke)
        self._reload()

    def _reload(self) -> None:
        self.list.clear()
        for row in self.engine.device_repo.all():
            perms = row["permissions"]
            state = "REVOKED" if row["revoked"] else "active"
            QListWidgetItem(
                f"{row['name']} — {state} — perms {perms} — last seen {row['last_seen_utc'] or 'never'}",
                self.list)
            self.list.item(self.list.count() - 1).setData(Qt.ItemDataRole.UserRole,
                                                          row["device_id"])

    def _revoke(self) -> None:
        item = self.list.currentItem()
        if not item:
            return
        device_id = item.data(Qt.ItemDataRole.UserRole)
        ret = QMessageBox.question(self, "Revoke device",
                                   "Revoke this device? It will lose access immediately "
                                   "and must re-pair with a new code.")
        if ret == QMessageBox.StandardButton.Yes:
            self.engine.device_repo.revoke(device_id)
            self.engine.audit_repo.add("local", "device_revoked", device_id)
            self._reload()


class PairingCodeDialog(QDialog):
    """Show a one-time pairing code for a new Android device."""

    def __init__(self, code: str, fingerprint: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Pair a new device")
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        info = QLabel("On the Android app choose Pair, enter host:port and this "
                      "one-time code (valid 5 minutes, single use). Then verify the "
                      "fingerprint shown there matches the one below:")
        info.setWordWrap(True)
        lay.addWidget(info)
        code_lbl = QLabel(code)
        code_lbl.setObjectName("Mono")
        code_lbl.setStyleSheet(f"font-size: 22pt; color: {theme.NEON};")
        code_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(code_lbl)
        host_hint = QLabel("Host address: the LAN IP of this Windows machine "
                           "(port shown in Settings → Remote access).")
        host_hint.setObjectName("MonoDim")
        host_hint.setWordWrap(True)
        lay.addWidget(host_hint)
        fp = QLabel(f"Fingerprint (SHA-256):\n{fingerprint}")
        fp.setObjectName("Mono")
        fp.setWordWrap(True)
        lay.addWidget(fp)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.clicked.connect(self.accept)
        lay.addWidget(buttons)


class SettingsDialog(QDialog):
    def __init__(self, settings: AppSettings, parent: QWidget | None = None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Settings — CYBER WORKSPACE")
        form = QFormLayout(self)
        self.chk_rain = QCheckBox("Digital rain header animation (lightweight)")
        self.chk_rain.setChecked(settings.rain_enabled)
        self.chk_probe = QCheckBox("Network latency probe enabled")
        self.chk_probe.setChecked(settings.net_probe_enabled)
        self.spin_unresp = QSpinBox()
        self.spin_unresp.setRange(5, 300)
        self.spin_unresp.setValue(settings.unresponsive_timeout_s)
        self.spin_unresp.setSuffix(" s")
        self.spin_unresp.setToolTip("No verified activity for this long → the task is "
                                    "reported UNRESPONSIVE (heartbeat adapters only).")
        self.spin_max = QSpinBox()
        self.spin_max.setRange(1, 50)
        self.spin_max.setValue(settings.max_tasks)
        self.spin_max.setToolTip("Initial capacity ≥ 6; scale beyond 10 subject to "
                                 "device resources.")
        self.chk_remote = QCheckBox("Enable remote control server (Android pairing)")
        self.chk_remote.setChecked(settings.remote_enabled)
        self.spin_port = QSpinBox()
        self.spin_port.setRange(1024, 65535)
        self.spin_port.setValue(settings.remote_port)
        self.chk_exit = QCheckBox("Confirm before exit")
        self.chk_exit.setChecked(settings.confirm_exit)
        form.addRow("Visual", self.chk_rain)
        form.addRow("Network probe", self.chk_probe)
        form.addRow("Unresponsive timeout", self.spin_unresp)
        form.addRow("Max tasks", self.spin_max)
        form.addRow("Remote access", self.chk_remote)
        form.addRow("Remote port", self.spin_port)
        form.addRow("Exit", self.chk_exit)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._apply)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _apply(self) -> None:
        self.settings.rain_enabled = self.chk_rain.isChecked()
        self.settings.net_probe_enabled = self.chk_probe.isChecked()
        self.settings.unresponsive_timeout_s = self.spin_unresp.value()
        self.settings.max_tasks = self.spin_max.value()
        self.settings.remote_enabled = self.chk_remote.isChecked()
        self.settings.remote_port = self.spin_port.value()
        self.settings.confirm_exit = self.chk_exit.isChecked()
        self.accept()


class TaskDetailDialog(QDialog):
    """Full status, tri-timer breakdown (incl. unknown/paused), logs and
    controls for ONE task. Other tasks are never affected."""

    def __init__(self, engine: TaskEngine, task: Task,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.engine = engine
        self.task = task
        self.setWindowTitle(f"{task.cfg.name} — details")
        self.setMinimumSize(640, 520)
        lay = QVBoxLayout(self)
        self._head = QLabel("")
        self._head.setWordWrap(True)
        self._head.setObjectName("Mono")
        lay.addWidget(self._head)
        self._timers = QLabel("")
        self._timers.setObjectName("Mono")
        lay.addWidget(self._timers)
        note = QLabel("Unknown time = intervals where activity could not be "
                      "determined confidently — never counted as active work.")
        note.setObjectName("MonoDim")
        note.setWordWrap(True)
        lay.addWidget(note)
        self._approval = QLabel("")
        self._approval.setWordWrap(True)
        self._approval.setStyleSheet(f"color: {theme.AMBER};")
        lay.addWidget(self._approval)
        row = QHBoxLayout()
        self.btn_approve = QPushButton("Approve request")
        self.btn_deny = QPushButton("Deny request")
        self.btn_approve.setObjectName("Primary")
        self.btn_approve.clicked.connect(lambda: self._decide("approve"))
        self.btn_deny.clicked.connect(lambda: self._decide("deny"))
        row.addWidget(self.btn_approve)
        row.addWidget(self.btn_deny)
        lay.addLayout(row)
        self._stdin = QLineEdit()
        self._stdin.setPlaceholderText("Send a line to the task's stdin (script/terminal)")
        self._stdin.returnPressed.connect(self._send_stdin)
        lay.addWidget(self._stdin)
        log_lbl = QLabel("LOGS (latest first)")
        log_lbl.setObjectName("PanelTitle")
        lay.addWidget(log_lbl)
        self._logs = QPlainTextEdit()
        self._logs.setReadOnly(True)
        self._logs.setFont(theme.mono_font(9))
        self._logs.setMaximumBlockCount(800)
        lay.addWidget(self._logs, 1)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        close.clicked.connect(self.accept)
        lay.addWidget(close)
        self.refresh()

    def refresh(self) -> None:
        task = self.task
        snap = task.snapshot()
        self._head.setText(
            f"{task.cfg.name}  [{snap['type']}]\n"
            f"state: {snap['state']}   reason: {snap['reason'] or '—'}\n"
            f"pid: {snap['pid'] or '—'}   app: {snap['app'] or '—'}   "
            f"last activity: {snap['last_activity_utc'] or '—'}\n"
            f"progress: {snap['last_progress'] or '—'}")
        t = snap
        self._timers.setText(
            f"ACTIVE  {fmt_ms(t['active_ms'])}\n"
            f"WAITING {fmt_ms(t['waiting_ms'])}\n"
            f"ERROR   {fmt_ms(t['error_ms'])}\n"
            f"PAUSED  {fmt_ms(t['paused_ms'])}\n"
            f"UNKNOWN {fmt_ms(t['unknown_ms'])}")
        pend = snap["pending_approval"]
        self._approval.setVisible(pend is not None)
        self.btn_approve.setVisible(pend is not None)
        self.btn_deny.setVisible(pend is not None)
        if pend:
            self._approval.setText(f"PENDING APPROVAL: {pend['question']}")
        self._logs.setPlainText("\n".join(reversed(task.logs_tail(200))) or "(no logs)")

    def _decide(self, decision: str) -> None:
        pend = self.task.pending_approval
        if pend:
            self.engine.approve(pend.id, decision, actor="local")
        self.refresh()

    def _send_stdin(self) -> None:
        line = self._stdin.text()
        adapter = self.task.adapter
        if adapter is not None and hasattr(adapter, "send_stdin"):
            adapter.send_stdin(line)
            self.task.log(f"stdin: {line[:120]}")
        self._stdin.clear()
