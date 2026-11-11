"""TEST E (unresponsive watchdog) + TEST H (session recovery)."""
import time

from cyber_workspace.core.engine import TaskEngine
from cyber_workspace.core.state import TaskState


def test_unresponsive_watchdog(make_engine, fake_script):
    eng = make_engine()
    t = eng.add_task("automation", "script",
                     {"script_path": str(fake_script), "args": ["heartbeat"],
                      "require_heartbeat": True})
    deadline = time.time() + 8
    while time.time() < deadline:
        eng.tick()
        if t.state == "UNRESPONSIVE":
            break
        time.sleep(0.1)
    assert t.state == "UNRESPONSIVE"
    assert "no verified activity" in (t.reason or "")
    # timer honesty: during stall, time must have gone to UNKNOWN/ERROR, not active
    snap = t.timer.totals_ms()
    assert snap["active"] < 3000 or snap["unknown"] + snap["error"] > 0


def test_h_recovery_persists_tasks_and_timers(make_engine, fake_script, data_dir):
    eng1 = make_engine()
    t1 = eng1.add_task("persisted", "script",
                       {"script_path": str(fake_script), "args": ["long"]})
    for _ in range(4):
        eng1.tick()
        time.sleep(0.05)
    active_before = t1.timer.totals_ms()["active"]
    task_id = t1.cfg.id
    eng1.shutdown()  # clean shutdown persists state

    eng2 = TaskEngine(data_dir,
                      settings={"unresponsive_timeout_s": 1.0, "unknown_grace_s": 0.5,
                                "metrics_interval_s": 0.5, "max_tasks": 12},
                      power=None)
    t2 = eng2.tasks[task_id]
    assert t2.cfg.name == "persisted"
    assert t2.state == "UNKNOWN"  # process was stopped by clean shutdown → unknown, honest
    assert "not found or not adoptable" in (t2.reason or "") or \
           "restarted" in (t2.reason or "")
    # timers survived; not double counted
    active_after = t2.timer.totals_ms()["active"]
    assert active_after >= active_before
    eng2.shutdown()


def test_h_recovery_adopts_surviving_process(make_engine, fake_script, data_dir):
    """If the child process survives a workspace crash, the new engine adopts it
    (monitoring-only) instead of pretending it never ran."""
    import subprocess
    import sys
    eng1 = make_engine()
    t1 = eng1.add_task("survivor", "script",
                       {"script_path": str(fake_script), "args": ["long"]})
    eng1.tick()
    assert t1.state == "RUNNING"
    pid = t1.pid
    assert pid

    # simulate crash: engine object dies without shutdown; child keeps running
    task_id = t1.cfg.id
    eng1.db.close()
    del eng1

    eng2 = TaskEngine(data_dir,
                      settings={"unresponsive_timeout_s": 1.0, "unknown_grace_s": 0.5,
                                "max_tasks": 12}, power=None)
    t2 = eng2.tasks[task_id]
    assert t2.state == "UNKNOWN"
    assert "process survived" in (t2.reason or "")
    assert t2.pid == pid and t2.adapter.pid() == pid
    eng2.shutdown()
    # clean up the orphan child process
    try:
        import psutil
        psutil.Process(pid).terminate()
    except Exception:
        pass
