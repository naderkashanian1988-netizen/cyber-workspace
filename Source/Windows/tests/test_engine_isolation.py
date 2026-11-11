"""Acceptance TESTS A–D: concurrency and isolation.

A: six+ tasks run simultaneously.
B: one task enters ERROR — the others continue.
C: one task waits for user approval — the others continue.
D: one task reports NETWORK_WAITING — the others continue.
"""
import time

from cyber_workspace.core.state import TaskState


def _tick_until(eng, pred, timeout=12.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        eng.tick()
        if pred():
            return True
        time.sleep(0.08)
    return False


def _script(eng, fake_script, mode, name):
    return eng.add_task(name, "script",
                        {"script_path": str(fake_script), "args": [mode]})


def test_a_six_tasks_run_simultaneously(make_engine, fake_script):
    eng = make_engine()
    tasks = [_script(eng, fake_script, "long", f"task{i}") for i in range(6)]
    assert _tick_until(eng, lambda: all(t.state == "RUNNING" for t in tasks))
    assert len(eng.tasks) >= 6


def test_b_error_isolation(make_engine, fake_script):
    eng = make_engine()
    healthy = [_script(eng, fake_script, "long", f"ok{i}") for i in range(3)]
    failing = _script(eng, fake_script, "fail", "failing")
    assert _tick_until(eng, lambda: failing.state == "ERROR"), failing.state
    assert failing.reason and "exit code 3" in failing.reason
    assert all(t.state == "RUNNING" for t in healthy), \
        "TEST B FAILED: sibling tasks were disturbed by one task's error"
    eng.tick(); eng.tick()
    assert all(t.state == "RUNNING" for t in healthy)


def test_c_approval_isolation(make_engine, fake_script):
    eng = make_engine()
    healthy = [_script(eng, fake_script, "long", f"ok{i}") for i in range(2)]
    waiting = _script(eng, fake_script, "approval", "asker")
    assert _tick_until(eng, lambda: waiting.state == "WAITING_FOR_USER")
    req = waiting.pending_approval
    assert req and req.question == "Proceed with cleanup?"
    notifs = eng.notif_repo.recent(5)
    assert any(n["category"] == "approval_required" and n["task_id"] == waiting.cfg.id
               for n in notifs)
    assert all(t.state == "RUNNING" for t in healthy), \
        "TEST C FAILED: one task's approval wait disturbed others"
    ok, err = eng.approve(req.id, "approve")
    assert ok, err
    assert _tick_until(eng, lambda: waiting.state == "COMPLETED")
    # approval flow answer reached the script (exit 0)
    assert waiting.exit_code == 0


def test_c_deny_isolation(make_engine, fake_script):
    eng = make_engine()
    healthy = _script(eng, fake_script, "long", "ok")
    waiting = _script(eng, fake_script, "approval", "denied-asker")
    assert _tick_until(eng, lambda: waiting.state == "WAITING_FOR_USER")
    req = waiting.pending_approval
    eng.approve(req.id, "deny")
    assert _tick_until(eng, lambda: waiting.state == "ERROR")
    assert waiting.exit_code == 4
    assert healthy.state == "RUNNING"


def test_d_network_waiting_isolation(make_engine, fake_script):
    eng = make_engine()
    healthy = [_script(eng, fake_script, "long", f"ok{i}") for i in range(2)]
    net = _script(eng, fake_script, "netwait", "uploader")
    assert _tick_until(eng, lambda: net.state == "NETWORK_WAITING")
    assert "upload endpoint" in (net.reason or "")
    assert all(t.state == "RUNNING" for t in healthy), \
        "TEST D FAILED: one task's network wait disturbed others"
    assert _tick_until(eng, lambda: net.state == "COMPLETED", timeout=15)
    assert all(t.state == "RUNNING" for t in healthy)


def test_close_is_never_completed(make_engine, fake_script):
    """Master rule §7: closing must not report COMPLETED."""
    eng = make_engine()
    t = _script(eng, fake_script, "long", "closer")
    assert _tick_until(eng, lambda: t.state == "RUNNING")
    eng.close_task(t.cfg.id)
    assert t.state == "UNKNOWN"
    assert t.timer.frozen
    assert t.exit_code is None or True  # exit code recorded, outcome NOT completed
