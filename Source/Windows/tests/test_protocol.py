"""Protocol v1 message model: closed command set (injection boundary),
version check, approval validation."""
import pytest

from cyber_workspace.protocol import messages as M


def test_envelope_roundtrip():
    raw = M.build(M.Op.COMMAND, {"action": "pause", "task_id": "t1"}, seq=3, ts="t")
    op, payload, seq = M.parse(raw)
    assert op is M.Op.COMMAND and payload["task_id"] == "t1" and seq == 3


def test_version_mismatch_rejected():
    bad = '{"v": 2, "op": "ping", "seq": 0, "ts": "", "payload": {}}'
    with pytest.raises(M.ProtocolError) as e:
        M.parse(bad)
    assert e.value.code == "VERSION_MISMATCH"


def test_unknown_op_rejected():
    bad = '{"v": 1, "op": "host_shout_v99", "seq": 0, "ts": "", "payload": {}}'
    with pytest.raises(M.ProtocolError) as e:
        M.parse(bad)
    assert e.value.code == "BAD_REQUEST"


def test_oversized_message_rejected():
    with pytest.raises(M.ProtocolError) as e:
        M.parse("x" * (M.MAX_MESSAGE_BYTES + 1))
    assert e.value.code == "BAD_REQUEST"


def test_command_action_is_closed_set():
    for payload in (
        {"action": "rm -rf /", "task_id": "t1"},
        {"action": "__import__('os').system('calc')"},
        {"action": None},
    ):
        with pytest.raises(M.ProtocolError) as e:
            M.validate_command(payload)
        assert e.value.code == "INVALID_COMMAND"


def test_valid_commands_parse():
    action, tid, params = M.validate_command({"action": "pause", "task_id": "t1"})
    assert action is M.CommandAction.PAUSE and tid == "t1"
    action, tid, params = M.validate_command(
        {"action": "set_keep_awake", "params": {"enabled": True}})
    assert action is M.CommandAction.SET_KEEP_AWAKE and params["enabled"] is True


def test_set_keep_awake_requires_bool():
    with pytest.raises(M.ProtocolError):
        M.validate_command({"action": "set_keep_awake", "params": {"enabled": "yes"}})


def test_approve_validation():
    rid, dec, note = M.validate_approve({"request_id": "r1", "decision": "approve"})
    assert rid == "r1" and dec == "approve"
    with pytest.raises(M.ProtocolError):
        M.validate_approve({"request_id": "r1", "decision": "maybe"})


def test_message_never_hides_arbitrary_shell_strings_into_engine():
    """Even if a malicious client sends a crafted payload, the engine command
    queue only accepts the enum — validated at engine.submit_command too."""
    with pytest.raises(ValueError):
        M.CommandAction("format c:")
