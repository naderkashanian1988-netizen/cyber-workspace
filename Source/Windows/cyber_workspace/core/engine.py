"""CYBER WORKSPACE — Task Engine (Qt-free, unit-testable).

The single writer of task state. The UI, the remote server and adapter reader
threads NEVER mutate task state directly: they enqueue intents / commands and
the engine applies them inside tick().

Isolation guarantees (TEST B/C/D):
* Every adapter error is caught inside _poll_task / _drain_intents and applied
  to that task only. No exception from one task can escape tick() and no
  exception can stop the loop that serves the other tasks.
* A failure in one adapter cannot cancel, pause or restart another.

Clock rules: wall-clock UTC for persisted segments; monotonic only for live
display. last_seen_utc is persisted (throttled) so crash recovery can close
orphan segments at the right cutoff without double counting.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import threading
import time as _time
import traceback
from pathlib import Path

from ..persistence.repos import (AuditRepo, Database, DeviceRepo, EventRepo,
                                 MetricsRepo, new_id, NotificationRepo,
                                 RecoveryRepo, SettingsRepo, TaskRepo, TimerRepo)
from ..protocol.messages import CommandAction
from .events import EventBus
from .state import SegmentKind, TaskState, UNKNOWN_REASON, can_transition
from .task import ApprovalRequest, Task, TaskConfig
from .timers import TriTimer, now_utc, parse_utc

log = logging.getLogger("cyber.engine")

UTC = _dt.timezone.utc

STATE_BUCKET_SPECIAL = {TaskState.RUNNING}  # bucket decided per-adapter activity


class TaskEngine:
    def __init__(self, data_dir: Path, settings: dict | None = None,
                 bus: EventBus | None = None, power=None,
                 max_tasks: int = 12):
        self.data_dir = Path(data_dir)
        self.settings = {
            "unresponsive_timeout_s": 20,
            "unknown_grace_s": 10,
            "metrics_interval_s": 2.0,
            "last_seen_interval_s": 5.0,
            "net_probe_target": ("1.1.1.1", 443),
            "net_probe_interval_s": 5.0,
            "max_tasks": max_tasks,
            "stop_timeout_s": 8.0,
        }
        if settings:
            self.settings.update(settings)
        self.bus = bus or EventBus()
        self.db = Database(self.data_dir / "workspace.db")
        self.tasks_repo = TaskRepo(self.db)
        self.timer_repo = TimerRepo(self.db)
        self.event_repo = EventRepo(self.db)
        self.metrics_repo = MetricsRepo(self.db)
        self.notif_repo = NotificationRepo(self.db)
        self.device_repo = DeviceRepo(self.db)
        self.audit_repo = AuditRepo(self.db)
        self.settings_repo = SettingsRepo(self.db)
        self.recovery_repo = RecoveryRepo(self.db)
        self.power = power  # platform.power.PowerManager-like; may be None (tests)
        self.tasks: dict[str, Task] = {}
        self._cmd_queue: list[dict] = []
        self._cmd_lock = threading.Lock()
        self._last_metrics = 0.0
        self._last_lastseen = 0.0
        self._last_netprobe = 0.0
        self._started_utc = now_utc()
        self.system_cpu: float | None = None
        self.system_ram_percent: float | None = None
        self.system_ram_used_mb: float | None = None
        self.system_ram_total_mb: float | None = None
        self.net = {"down_bps": None, "up_bps": None,
                    "latency_ms": None, "status": "UNKNOWN"}
        self.net_history: list[tuple] = []
        self.keep_awake_active = False
        self._recover_session()

    # ------------------------------------------------------------------
    # session recovery (TEST H)
    # ------------------------------------------------------------------
    def _recover_session(self) -> None:
        clean = self.recovery_repo.was_shutdown_clean()
        startup = now_utc()
        for row in self.tasks_repo.all():
            cfg = TaskConfig(
                id=row["id"], name=row["name"], type=row["type"],
                position=row["position"], created_utc=row["created_utc"],
                config=json.loads(row["config_json"] or "{}"),
                keep_awake=bool(row["keep_awake"]),
            )
            task = Task(cfg)
            task.state = row["last_state"] if row["last_state"] in [s.value for s in TaskState] else "UNKNOWN"
            task.reason = row["last_reason"]
            task.state_utc = row["last_state_utc"]
            task.minimized = bool(row["minimized"])
            task.last_seen_utc = row["last_seen_utc"]
            task.timer = TriTimer(cfg.id, self.timer_repo)
            self.tasks[cfg.id] = task

            cutoff = row["last_seen_utc"] or startup
            orphaned = task.timer.recover_orphans(cutoff)

            if task.state in (TaskState.COMPLETED.value, TaskState.ERROR.value):
                task.timer.freeze()
            # Adopt surviving processes where possible (best effort, honest):
            pid = row["last_pid"]
            adopted = False
            if pid and task.state not in ("COMPLETED",):
                try:
                    task.adapter = self._make_adapter(task)
                    adopted = task.adapter.reattach(pid)
                except Exception as exc:            # adapter unavailable (e.g. browser)
                    task.log(f"adapter unavailable during recovery: {exc}", "error")
            if adopted:
                task.pid = pid
                task.app_name = task.adapter.describe().get("app")
                self._apply_transition(task, TaskState.UNKNOWN,
                                       "workspace restarted; process survived — "
                                       "re-attached, monitoring resumed",
                                       _force=True)
            elif task.state not in ("COMPLETED",):
                self._apply_transition(
                    task, TaskState.UNKNOWN,
                    "workspace restarted; previous process not found or not adoptable — "
                    "previous state was %s; outcome not verified" % task.state,
                    _force=True)
            if orphaned:
                task.log(f"recovery closed {orphaned} orphan timer segment(s) at {cutoff}",
                         "warning")
        if not clean:
            self.notify("recovery_required",
                        "Workspace recovered after unclean shutdown",
                        "Sessions and timers were restored from disk; tasks that cannot "
                        "be re-adopted are marked UNKNOWN.", task_id=None)
        self.recovery_repo.set_shutdown_clean(False)
        # restore saved z-order
        order_raw = self.settings_repo.get("task_order")
        if order_raw:
            try:
                ids = json.loads(order_raw)
                ids = [i for i in ids if i in self.tasks] + \
                      [i for i in self.tasks if i not in ids]
                self.tasks_repo.set_positions(ids)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # task CRUD
    # ------------------------------------------------------------------
    def _make_adapter(self, task: Task):
        from ..adapters import create_adapter  # lazy; browser import is guarded
        return create_adapter(task)

    def add_task(self, name: str, type_: str, config: dict,
                 autostart: bool = True) -> Task:
        if len(self.tasks) >= self.settings["max_tasks"]:
            raise RuntimeError(f"task limit reached ({self.settings['max_tasks']}); "
                               "increase max_tasks in settings subject to device resources")
        cfg = TaskConfig(id=new_id(), name=name, type=type_,
                         position=len(self.tasks),
                         created_utc=now_utc(), config=config)
        task = Task(cfg)
        task.timer = TriTimer(cfg.id, self.timer_repo)
        task.adapter = self._make_adapter(task)
        self.tasks[cfg.id] = task
        self._persist_task(task)
        self.event_repo.add(cfg.id, "created", f"task '{name}' ({type_}) created")
        task.log("task created")
        if autostart:
            self.start_task(cfg.id)
        self.bus.publish("task_update", {"task_id": cfg.id})
        return task

    def remove_task(self, task_id: str) -> None:
        task = self.tasks.get(task_id)
        if not task:
            return
        try:
            if task.adapter:
                task.adapter.stop(self.settings["stop_timeout_s"])
        except Exception as exc:
            task.log(f"adapter stop during removal failed: {exc}", "warning")
        self.tasks.pop(task_id, None)
        self.tasks_repo.delete(task_id)
        self.event_repo.add(None, "removed", f"task '{task.cfg.name}' removed")
        self.bus.publish("task_update", {"task_id": task_id, "removed": True})

    def rename_task(self, task_id: str, name: str) -> None:
        task = self.tasks.get(task_id)
        if not task:
            return
        task.cfg.name = name.strip() or task.cfg.name
        self._persist_task(task)
        task.dirty = True
        self.bus.publish("task_update", {"task_id": task_id})

    def reorder(self, ids_in_order: list[str]) -> None:
        self.tasks_repo.set_positions(ids_in_order)
        self.settings_repo.set("task_order", json.dumps(ids_in_order))
        for pos, tid in enumerate(ids_in_order):
            if tid in self.tasks:
                self.tasks[tid].cfg.position = pos

    def _persist_task(self, task: Task) -> None:
        row = task.cfg.to_row()
        row.update({
            "last_state": task.state, "last_state_utc": task.state_utc,
            "last_reason": task.reason, "last_pid": task.pid,
            "last_exit_code": task.exit_code, "last_seen_utc": task.last_seen_utc,
            "minimized": 1 if task.minimized else 0,
            "layout_json": "{}",
        })
        self.tasks_repo.upsert(row)

    # ------------------------------------------------------------------
    # lifecycle commands (user or remote)
    # ------------------------------------------------------------------
    def start_task(self, task_id: str) -> tuple[bool, str | None]:
        task = self.tasks.get(task_id)
        if not task:
            return False, "task not found"
        try:
            if task.adapter is None:
                task.adapter = self._make_adapter(task)
            task.adapter.start()
            task.run_count += 1
            task.pid = task.adapter.pid()
            task.app_name = task.adapter.describe().get("app")
            task.exit_code = None
            self._apply_transition(task, TaskState.RUNNING, "started")
            return True, None
        except Exception as exc:
            task.log(f"failed to start: {exc}", "error")
            self._apply_transition(task, TaskState.ERROR, f"failed to start: {exc}")
            return False, str(exc)

    def pause_task(self, task_id: str) -> tuple[bool, str | None]:
        task = self.tasks.get(task_id)
        if not task or task.state == TaskState.PAUSED.value:
            return False, "not pauseable"
        if not can_transition(TaskState(task.state), TaskState.PAUSED):
            return False, f"cannot pause from {task.state}"
        if task.adapter is None:
            return False, "task has no running process"
        try:
            task.adapter.pause()
        except Exception as exc:
            task.log(f"pause failed: {exc}", "error")
            return False, str(exc)
        self._apply_transition(task, TaskState.PAUSED, "paused by user")
        return True, None

    def resume_task(self, task_id: str) -> tuple[bool, str | None]:
        task = self.tasks.get(task_id)
        if not task:
            return False, "task not found"
        cur = TaskState(task.state)
        target = TaskState.RUNNING
        try:
            if task.adapter:
                task.adapter.resume()
        except Exception as exc:
            task.log(f"resume failed: {exc}", "error")
            return False, str(exc)
        if not can_transition(cur, target):
            return False, f"cannot resume from {task.state}"
        reason = "resumed by user"
        if cur is TaskState.WAITING_FOR_USER:
            reason = "resumed after user approval"
        self._apply_transition(task, target, reason)
        return True, None

    def restart_task(self, task_id: str) -> tuple[bool, str | None]:
        task = self.tasks.get(task_id)
        if not task:
            return False, "task not found"
        try:
            if task.adapter:
                task.adapter.stop(self.settings["stop_timeout_s"])
        except Exception as exc:
            task.log(f"stop during restart failed: {exc}", "warning")
        # previous run: freeze nothing — totals are lifetime segments; open a fresh run
        task.timer.frozen = False
        ok, err = self.start_task(task_id)
        if ok:
            task.reason = "restarted by user"
            task.dirty = True
        return ok, err

    def close_task(self, task_id: str) -> tuple[bool, str | None]:
        """User-initiated close: stop the work unit. A task is NEVER reported
        COMPLETED merely because it was closed — outcome is UNKNOWN."""
        task = self.tasks.get(task_id)
        if not task:
            return False, "task not found"
        try:
            if task.adapter:
                task.adapter.stop(self.settings["stop_timeout_s"])
        except Exception as exc:
            task.log(f"close failed: {exc}", "warning")
        if task.state not in ("COMPLETED", "ERROR"):
            self._apply_transition(task, TaskState.UNKNOWN,
                                   "closed by user; outcome could not be verified",
                                   _force=True)
        task.timer.freeze()
        self._persist_task(task)
        task.dirty = True
        self.bus.publish("task_update", {"task_id": task_id})
        return True, None

    def approve(self, request_id: str, decision: str, actor: str = "local") -> tuple[bool, str | None]:
        for task in self.tasks.values():
            if task.pending_approval and task.pending_approval.id == request_id:
                req = task.pending_approval
                task.pending_approval = None
                task.log(f"approval '{req.question}' -> {decision} (by {actor})")
                self.event_repo.add(task.cfg.id, "approval",
                                    f"{decision} by {actor}: {req.question}")
                if task.adapter is not None and hasattr(task.adapter, "on_decision"):
                    try:
                        task.adapter.on_decision(decision, req.to_dict())
                    except Exception as exc:
                        task.log(f"adapter decision hook failed: {exc}", "warning")
                if TaskState(task.state) is TaskState.WAITING_FOR_USER:
                    self._apply_transition(task, TaskState.RUNNING,
                                           f"approval {decision} by {actor}")
                task.dirty = True
                self.bus.publish("task_update", {"task_id": task.cfg.id})
                return True, None
        return False, "approval request not found"

    def set_task_keep_awake(self, task_id: str, enabled: bool) -> tuple[bool, str | None]:
        task = self.tasks.get(task_id)
        if not task:
            return False, "task not found"
        task.cfg.keep_awake = bool(enabled)
        self._persist_task(task)
        task.dirty = True
        self.bus.publish("task_update", {"task_id": task_id})
        return True, None

    def submit_command(self, action: str, task_id: str | None, params: dict | None,
                       actor: str, command_id: str | None = None) -> None:
        """Queue a validated command for execution in tick() (single writer)."""
        try:
            action = CommandAction(action)
        except ValueError:
            return
        with self._cmd_lock:
            self._cmd_queue.append({"action": action, "task_id": task_id,
                                    "params": params or {}, "actor": actor,
                                    "command_id": command_id or new_id()})

    # ------------------------------------------------------------------
    # notifications
    # ------------------------------------------------------------------
    def notify(self, category: str, title: str, body: str = "",
               task_id: str | None = None, actions: list[dict] | None = None) -> str:
        nid = self.notif_repo.add(category, title, body, task_id, actions)
        payload = {"id": nid, "category": category, "title": title, "body": body,
                   "task_id": task_id, "actions": actions or [],
                   "created_utc": now_utc()}
        self.bus.publish("notification", payload)
        return nid

    # ------------------------------------------------------------------
    # state transitions
    # ------------------------------------------------------------------
    def _apply_transition(self, task: Task, target: TaskState, reason: str | None,
                          _force: bool = False) -> None:
        cur = TaskState(task.state)
        if cur is target:
            task.reason = reason or task.reason
            task.dirty = True
            return
        if not _force and not can_transition(cur, target):
            task.log(f"ignored illegal transition {cur.value} -> {target.value} ({reason})",
                     "warning")
            return
        task.state = target.value
        task.reason = reason or UNKNOWN_REASON
        task.state_utc = now_utc()
        task.dirty = True
        # timer bucketing
        if target is TaskState.COMPLETED:
            task.timer.set_bucket(SegmentKind.ACTIVE)
            task.timer.freeze()
        else:
            task.timer.transition_to(target)
        self.event_repo.add(task.cfg.id, "state_changed",
                            f"{cur.value} -> {target.value}: {task.reason}")
        task.log(f"state {cur.value} -> {target.value}: {task.reason}")
        self._persist_task(task)
        self.bus.publish("task_update", {"task_id": task.cfg.id})

    # ------------------------------------------------------------------
    # per-task intents
    # ------------------------------------------------------------------
    def _drain_intents(self, task: Task) -> None:
        for kind, payload in task.drain_intents():
            try:
                self._handle_intent(task, kind, payload)
            except Exception as exc:
                task.log(f"intent {kind} handling failed: {exc}", "error")

    def _handle_intent(self, task: Task, kind: str, payload) -> None:
        if kind == "activity":
            task.note_activity(payload if isinstance(payload, str) else None)
        elif kind == "progress":
            task.note_activity(str(payload))
        elif kind == "log":
            task.log(str(payload), level="info")
        elif kind == "error_log":
            task.log(str(payload), level="error")
        elif kind == "netwait":
            cur = TaskState(task.state)
            if cur is TaskState.RUNNING:
                self._apply_transition(task, TaskState.NETWORK_WAITING,
                                       f"network waiting: {payload}")
        elif kind == "netok":
            if TaskState(task.state) is TaskState.NETWORK_WAITING:
                self._apply_transition(task, TaskState.RUNNING,
                                       "network activity resumed")
        elif kind == "approval":
            q = (payload or {}).get("question", "approval required")
            opts = (payload or {}).get("options") or ["Approve", "Deny"]
            req = ApprovalRequest(new_id(), task.cfg.id, str(q), [str(o) for o in opts],
                                  now_utc())
            task.pending_approval = req
            self._apply_transition(task, TaskState.WAITING_FOR_USER,
                                   f"user approval requested: {req.question}")
            self.notify("approval_required", f"Approval required — {task.cfg.name}",
                        str(q), task_id=task.cfg.id,
                        actions=[{"id": "approve", "label": "Approve"},
                                 {"id": "deny", "label": "Deny"}])
            self.bus.publish("approval", {"task_id": task.cfg.id,
                                          "request": req.to_dict(),
                                          "created_utc": req.created_utc})
        elif kind == "exit":
            code = payload
            task.exit_code = code if isinstance(code, int) else None
            task.pid = None
            self._handle_exit(task, code)
        elif kind == "crash":
            self._apply_transition(task, TaskState.ERROR, str(payload))
        else:
            task.log(f"unknown intent kind {kind}", "warning")

    def _handle_exit(self, task: Task, code: int | None) -> None:
        """Evidence-based exit handling. Only script/terminal-style adapters
        with real exit-code semantics may complete; everything else that
        disappears becomes UNKNOWN, never COMPLETED."""
        evidence = getattr(task.adapter, "exit_evidence", None)
        evidence = evidence.value if hasattr(evidence, "value") else str(evidence or "none")
        cur = TaskState(task.state)
        if evidence == "exit_code":
            if code == 0:
                self._apply_transition(task, TaskState.COMPLETED,
                                       "exit code 0 (task finished normally)")
                self.notify("task_completed", f"Task completed — {task.cfg.name}",
                            "exit code 0", task_id=task.cfg.id)
            else:
                self._apply_transition(task, TaskState.ERROR,
                                       f"exit code {code} (task reported failure)")
                self.notify("task_error", f"Task error — {task.cfg.name}",
                            f"exit code {code}", task_id=task.cfg.id)
        else:
            if cur is TaskState.PAUSED or cur is TaskState.COMPLETED:
                return
            self._apply_transition(
                task, TaskState.UNKNOWN,
                f"process exited (code {code if code is not None else 'unknown'}); "
                "outcome could not be verified", _force=True)

    # ------------------------------------------------------------------
    # watchdog
    # ------------------------------------------------------------------
    def _watchdog(self, task: Task, now: float) -> None:
        if task.state != "RUNNING" or task.adapter is None:
            return
        mode = getattr(task.adapter, "activity_mode", "verified_when_alive")
        if mode != "verified_on_heartbeat":
            return
        age = task.adapter.heartbeat_age()
        if age is None:
            return
        to = float(self.settings["unresponsive_timeout_s"])
        grace = float(self.settings["unknown_grace_s"])
        if age > to + grace:
            if task.state == "RUNNING":
                self._apply_transition(task, TaskState.UNRESPONSIVE,
                                       f"no verified activity for {int(age)}s "
                                       f"(heartbeat timeout {int(to)}s)")
                self.notify("task_unresponsive",
                            f"Task unresponsive — {task.cfg.name}",
                            f"no verified activity for {int(age)}s",
                            task_id=task.cfg.id)
        elif age > to and task.state == "RUNNING":
            # uncertain: switch the timer bucket to UNKNOWN but keep RUNNING
            task.timer.set_bucket(SegmentKind.UNKNOWN)

    # ------------------------------------------------------------------
    # metrics & network
    # ------------------------------------------------------------------
    def _sample_metrics(self, now: float) -> None:
        import psutil
        self.system_cpu = psutil.cpu_percent(interval=None)
        vm = psutil.virtual_memory()
        self.system_ram_percent = vm.percent
        self.system_ram_total_mb = vm.total / (1024 * 1024)
        self.system_ram_used_mb = vm.used / (1024 * 1024)
        for task in self.tasks.values():
            cpu = ram = None
            pid = task.pid or (task.adapter.pid() if task.adapter else None)
            if pid:
                try:
                    proc = psutil.Process(pid)
                    cpu = proc.cpu_percent(interval=None)
                    ram = proc.memory_info().rss / (1024 * 1024)
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    cpu = ram = None
            task.cpu_percent = cpu
            task.ram_mb = ram
            task.history.append((now, cpu, ram))
            self.metrics_repo.add(task.cfg.id, cpu, ram)
        self.bus.publish("system", self.system_status())

    def _sample_network(self, now: float) -> None:
        import psutil
        try:
            counters = psutil.net_io_counters()
            if not hasattr(self, "_net_prev"):
                self._net_prev = (now, counters.bytes_recv, counters.bytes_sent)
                return
            dt = now - self._net_prev[0]
            if dt <= 0:
                return
            self.net["down_bps"] = max(0.0, (counters.bytes_recv - self._net_prev[1]) / dt)
            self.net["up_bps"] = max(0.0, (counters.bytes_sent - self._net_prev[2]) / dt)
            self._net_prev = (now, counters.bytes_recv, counters.bytes_sent)
        except Exception:
            self.net["down_bps"] = None
            self.net["up_bps"] = None
        # latency probe
        if now - self._last_netprobe >= float(self.settings["net_probe_interval_s"]):
            self._last_netprobe = now
            self.net["latency_ms"], self.net["status"] = self._tcp_probe()
            self.net_history.append((now, self.net["down_bps"], self.net["up_bps"],
                                     self.net["latency_ms"], self.net["status"]))
            if len(self.net_history) > 360:
                del self.net_history[:180]
            self.bus.publish("network", dict(self.net))

    def _tcp_probe(self) -> tuple[float | None, str]:
        import socket
        target = self.settings["net_probe_target"]
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2.0)
            t0 = _time.monotonic()
            s.connect((target[0], int(target[1])))
            ms = (_time.monotonic() - t0) * 1000.0
            s.close()
            return round(ms, 1), "UP"
        except OSError:
            return None, "DOWN"

    def system_status(self) -> dict:
        return {
            "cpu_percent": self.system_cpu,
            "ram_percent": self.system_ram_percent,
            "ram_used_mb": self.system_ram_used_mb,
            "ram_total_mb": self.system_ram_total_mb,
            "net": dict(self.net),
            "keep_awake_active": self.keep_awake_active,
            "server_time": now_utc(),
        }

    # ------------------------------------------------------------------
    # keep-awake (TEST G logic)
    # ------------------------------------------------------------------
    def _evaluate_keep_awake(self) -> None:
        wanted = any(t.cfg.keep_awake and t.state == "RUNNING" for t in self.tasks.values())
        if wanted != self.keep_awake_active:
            ok = True
            if self.power is not None:
                ok = bool(self.power.set_keep_awake(wanted))
            self.keep_awake_active = wanted and ok
            self.audit_repo.add("local", "keep_awake",
                                f"{'enabled' if wanted else 'disabled'}")
            self.bus.publish("engine", {"kind": "keep_awake",
                                        "active": self.keep_awake_active})

    # ------------------------------------------------------------------
    # command execution (single writer)
    # ------------------------------------------------------------------
    def _execute_commands(self) -> None:
        with self._cmd_lock:
            queue, self._cmd_queue = self._cmd_queue, []
        for cmd in queue:
            action: CommandAction = cmd["action"]
            tid = cmd["task_id"]
            params = cmd["params"]
            actor = cmd["actor"]
            try:
                if action is CommandAction.PAUSE:
                    ok, err = self.pause_task(tid)
                elif action is CommandAction.RESUME:
                    ok, err = self.resume_task(tid)
                elif action is CommandAction.RESTART:
                    ok, err = self.restart_task(tid)
                elif action is CommandAction.CLOSE:
                    ok, err = self.close_task(tid)
                elif action is CommandAction.SET_KEEP_AWAKE:
                    ok, err = self.set_task_keep_awake(tid, bool(params.get("enabled")))
                else:
                    ok, err = False, "unsupported action"
                self.audit_repo.add(actor, action.value, f"task={tid} ok={ok} {err or ''}")
            except Exception as exc:
                log.error("command %s failed: %s\n%s", action.value, exc,
                          traceback.format_exc())
                ok, err = False, str(exc)
            self.bus.publish("audit", {"actor": actor, "action": action.value,
                                       "detail": f"task={tid} ok={ok} {err or ''}",
                                       "command_id": cmd["command_id"], "ok": ok,
                                       "error": err})

    # ------------------------------------------------------------------
    # main tick — errors in one task can never break the others
    # ------------------------------------------------------------------
    def tick(self) -> None:
        now = _time.monotonic()
        for task in list(self.tasks.values()):
            try:
                self._poll_task(task, now)
            except Exception as exc:
                task.log(f"engine poll error: {exc}", "error")
        for task in list(self.tasks.values()):
            try:
                self._drain_intents(task)
                self._update_timer_bucket(task)
            except Exception as exc:
                task.log(f"engine intent error: {exc}", "error")
        for task in list(self.tasks.values()):
            try:
                self._watchdog(task, now)
            except Exception as exc:
                task.log(f"watchdog error: {exc}", "error")
        try:
            self._sample_network(now)
        except Exception:
            pass
        if now - self._last_metrics >= float(self.settings["metrics_interval_s"]):
            self._last_metrics = now
            try:
                self._sample_metrics(now)
            except Exception as exc:
                log.error("metrics sampling failed: %s", exc)
        try:
            self._evaluate_keep_awake()
        except Exception:
            pass
        try:
            self._execute_commands()
        except Exception as exc:
            log.error("command execution failed: %s", exc)
        if now - self._last_lastseen >= float(self.settings["last_seen_interval_s"]):
            self._last_lastseen = now
            for task in self.tasks.values():
                task.last_seen_utc = now_utc()
                try:
                    self._persist_task(task)
                except Exception:
                    pass

    def _poll_task(self, task: Task, now: float) -> None:
        adapter = task.adapter
        if adapter is None:
            return
        adapter.poll()      # enqueue exit intents if the process ended
        pid = adapter.pid()
        task.pid = pid
        if task.app_name is None:
            d = adapter.describe()
            task.app_name = d.get("app")

    def _update_timer_bucket(self, task: Task) -> None:
        state = TaskState(task.state)
        if state is TaskState.COMPLETED:
            return
        if state is TaskState.RUNNING:
            mode = getattr(task.adapter, "activity_mode", "unverifiable") \
                if task.adapter else "unverifiable"
            if mode == "verified_when_alive":
                task.timer.set_bucket(SegmentKind.ACTIVE)
            elif mode == "verified_on_heartbeat":
                age = task.adapter.heartbeat_age()
                to = float(self.settings["unresponsive_timeout_s"])
                task.timer.set_bucket(SegmentKind.ACTIVE if (age is not None and age <= to)
                                      else SegmentKind.UNKNOWN)
            elif mode == "activity_window":
                age = task.adapter.heartbeat_age()
                window = float(getattr(task.adapter, "activity_window_s", 90))
                task.timer.set_bucket(SegmentKind.ACTIVE if (age is not None and age <= window)
                                      else SegmentKind.UNKNOWN)
            else:
                task.timer.set_bucket(SegmentKind.UNKNOWN)
        else:
            from .state import STATE_SEGMENT
            task.timer.set_bucket(STATE_SEGMENT[state])

    # ------------------------------------------------------------------
    # shutdown
    # ------------------------------------------------------------------
    def shutdown(self) -> None:
        for task in list(self.tasks.values()):
            try:
                if task.adapter:
                    task.adapter.stop(self.settings["stop_timeout_s"])
            except Exception:
                pass
            task.last_seen_utc = now_utc()
            try:
                self._persist_task(task)
            except Exception:
                pass
        if self.power is not None:
            try:
                self.power.set_keep_awake(False)
            except Exception:
                pass
        self.recovery_repo.set_shutdown_clean(True)
        self.event_repo.add(None, "shutdown", "workspace shut down cleanly")
        self.db.close()
