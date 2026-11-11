"""Tri-timer honesty (TEST E): active/waiting/error separation, UNKNOWN never
counted as active, freeze on completion, crash recovery without double counting."""
import time

from cyber_workspace.persistence.repos import Database, TimerRepo
from cyber_workspace.core.state import SegmentKind, TaskState
from cyber_workspace.core.timers import TriTimer, now_utc
from cyber_workspace.persistence.repos import Database


def test_buckets_follow_state(make_engine, fake_script):
    eng = make_engine()
    t = eng.add_task("timer task", "script",
                     {"script_path": str(fake_script), "args": ["long"]})
    eng.tick()
    assert t.timer.open_kind() is SegmentKind.ACTIVE  # script alive = verified work
    eng.pause_task(t.cfg.id)
    assert t.timer.open_kind() is SegmentKind.PAUSED
    eng.resume_task(t.cfg.id)
    assert t.timer.open_kind() is SegmentKind.ACTIVE


def test_unknown_never_merges_into_active(make_engine):
    eng = make_engine()
    t = eng.add_task("gui", "external", {"exe": "notepad.exe"})
    t.state = "RUNNING"  # simulate started GUI app
    eng._apply_transition(t, TaskState.RUNNING, "simulated", _force=False)
    # external apps are UNVERIFIABLE → UNKNOWN bucket
    for _ in range(3):
        eng.tick()
        time.sleep(0.05)
    totals = t.timer.totals_ms()
    assert totals["active"] == 0
    assert totals["unknown"] > 0


def test_freeze_on_completed(make_engine, fake_script):
    eng = make_engine()
    t = eng.add_task("quick", "script",
                     {"script_path": str(fake_script), "args": ["done"]})
    deadline = time.time() + 10
    while t.state != "COMPLETED" and time.time() < deadline:
        eng.tick()
        time.sleep(0.05)
    assert t.state == "COMPLETED"
    assert t.timer.frozen
    before = t.timer.totals_ms()
    time.sleep(0.1)
    after = t.timer.totals_ms()
    assert before == after  # frozen: no accumulation


def test_persistence_roundtrip_no_double_count(tmp_path):
    db = Database(tmp_path / "t.db")
    repo = TimerRepo(db)
    timer = TriTimer("task1", repo)
    timer.set_bucket(SegmentKind.ACTIVE)
    time.sleep(0.15)
    timer.transition_to(TaskState.WAITING_FOR_USER)
    time.sleep(0.1)
    timer.freeze()
    totals1 = timer.totals_ms()
    assert totals1["active"] >= 100
    assert totals1["waiting"] >= 50
    # simulate app restart: totals must come purely from persisted segments
    timer2 = TriTimer("task1", repo)
    totals2 = timer2.totals_ms()
    assert totals2 == totals1


def test_orphan_recovery_uses_cutoff(tmp_path):
    db = Database(tmp_path / "t.db")
    repo = TimerRepo(db)
    timer = TriTimer("t2", repo)
    timer.set_bucket(SegmentKind.ACTIVE)
    # crash: no close. Recovery closes at cutoff NOW (short orphan).
    closed = timer.recover_orphans(now_utc())
    assert closed == 1
    totals = timer.totals_ms()
    assert totals["active"] < 2000  # not stretched to arbitrary 'later'
    assert timer.open_kind() is None
