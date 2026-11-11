"""Persistence layer + device token hashing (TEST H foundations)."""
import json

from cyber_workspace.persistence.repos import (Database, DeviceRepo, EventRepo,
                                               NotificationRepo, TaskRepo,
                                               TimerRepo, AuditRepo)
from cyber_workspace.remote.auth import hash_token, new_token, tokens_match


def test_task_repo_roundtrip(tmp_path):
    db = Database(tmp_path / "a.db")
    repo = TaskRepo(db)
    row = {"id": "t1", "name": "Job", "type": "script", "position": 0,
           "created_utc": "2026-11-11T00:00:00Z", "last_state": "RUNNING",
           "last_state_utc": None, "last_reason": None, "last_pid": 42,
           "last_exit_code": None, "last_seen_utc": None, "minimized": 0,
           "keep_awake": 1, "config_json": "{}", "layout_json": "{}"}
    repo.upsert(row)
    got = repo.get("t1")
    assert got["name"] == "Job" and got["last_pid"] == 42
    repo.upsert({**row, "name": "Renamed"})
    assert repo.get("t1")["name"] == "Renamed"
    assert len(repo.all()) == 1


def test_device_token_stored_hashed(tmp_path):
    db = Database(tmp_path / "b.db")
    repo = DeviceRepo(db)
    token = new_token()
    repo.add("dev1", "Pixel", hash_token(token), ["view", "control"])
    stored = repo.find_active("dev1")
    assert token not in stored["token_hash"]        # never plaintext
    assert stored["token_hash"] == hash_token(token)
    assert tokens_match(token, stored["token_hash"])
    assert not tokens_match("wrong", stored["token_hash"])
    repo.revoke("dev1")
    assert repo.find_active("dev1") is None


def test_notifications_and_events(tmp_path):
    db = Database(tmp_path / "c.db")
    n = NotificationRepo(db)
    nid = n.add("approval_required", "Approval required — build",
                "Proceed with cleanup?", task_id="t9",
                actions=[{"id": "approve", "label": "Approve"}])
    rows = n.recent(5)
    assert rows[0]["id"] == nid and n.unread_count() == 1
    n.mark_read(nid)
    assert n.unread_count() == 0
    ev = EventRepo(db)
    ev.add("t9", "state_changed", "RUNNING -> WAITING_FOR_USER")
    assert "WAITING_FOR_USER" in ev.logs_for("t9", 10)[0]


def test_timer_repo_sums_by_kind(tmp_path):
    db = Database(tmp_path / "d.db")
    repo = TimerRepo(db)
    from cyber_workspace.core.state import SegmentKind
    s1 = repo.open_segment("t", SegmentKind.ACTIVE, "2026-11-11T00:00:00.000Z")
    repo.close_segment("t", s1, "2026-11-11T00:00:10.000Z")
    s2 = repo.open_segment("t", SegmentKind.WAITING, "2026-11-11T00:00:10.000Z")
    repo.close_segment("t", s2, "2026-11-11T00:00:25.000Z")
    totals = repo.sum_totals("t")
    assert totals["active"] == 10000
    assert totals["waiting"] == 15000
    assert totals["error"] == 0
    assert repo.close_orphans_for_task("t", "2026-11-11T01:00:00.000Z") == 0


def test_audit_log(tmp_path):
    db = Database(tmp_path / "e.db")
    a = AuditRepo(db)
    a.add("local", "device_paired", "Pixel (abcd…)")
    a.add("remote:deadbeef", "pause", "task=t1 ok=True")
    rows = a.__dict__ and db.query("SELECT * FROM audit_log")
    assert len(rows) == 2
    assert json.dumps(rows[0]["action"])  # serializable
