"""CYBER WORKSPACE — Shared remote protocol v1 message model.

Normative source for message names, enums and validation. The Android client
(android/app/.../protocol/) mirrors these definitions; PROTOCOL.md is the
specification. This module is UI-free and dependency-free (stdlib only) so the
task engine can use it in unit tests without Qt.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

PROTOCOL_VERSION = 1
SERVER_VERSION = "1.0.0-rc.1"

MAX_MESSAGE_BYTES = 64 * 1024
MAX_LOG_LINES = 1000


class ProtocolError(ValueError):
    """Raised when an incoming message violates the protocol."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class Op(str, Enum):
    # client -> host
    PAIRING = "pairing"
    AUTH = "auth"
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"
    GET_STATE = "get_state"
    GET_TASK = "get_task"
    GET_LOGS = "get_logs"
    COMMAND = "command"
    APPROVE = "approve"
    PING = "ping"
    # host -> client
    WELCOME = "welcome"
    PAIRING_OK = "pairing_ok"
    AUTH_OK = "auth_ok"
    AUTH_FAILED = "auth_failed"
    STATE_SNAPSHOT = "state_snapshot"
    TASK_EVENT = "task_event"
    METRICS = "metrics"
    NOTIFICATION = "notification"
    APPROVAL_REQUEST = "approval_request"
    COMMAND_ACK = "command_ack"
    ERROR = "error"
    PONG = "pong"


class CommandAction(str, Enum):
    """Closed set of remote actions — the command-injection boundary."""
    PAUSE = "pause"
    RESUME = "resume"
    RESTART = "restart"
    CLOSE = "close"
    SET_KEEP_AWAKE = "set_keep_awake"


class ErrorCode(str, Enum):
    VERSION_MISMATCH = "VERSION_MISMATCH"
    NOT_AUTHENTICATED = "NOT_AUTHENTICATED"
    UNPAIRED = "UNPAIRED"
    INVALID_TOKEN = "INVALID_TOKEN"
    REVOKED = "REVOKED"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    NOT_FOUND = "NOT_FOUND"
    INVALID_COMMAND = "INVALID_COMMAND"
    FORBIDDEN = "FORBIDDEN"
    RATE_LIMITED = "RATE_LIMITED"
    CONFLICT = "CONFLICT"
    BAD_REQUEST = "BAD_REQUEST"
    INTERNAL = "INTERNAL"


class TaskType(str, Enum):
    SCRIPT = "script"
    TERMINAL = "terminal"
    EXTERNAL = "external"
    BROWSER = "browser"


# Mirrors core.state.TaskState; kept here so the protocol is self-contained.
TASK_STATES = (
    "RUNNING", "WAITING_FOR_USER", "NETWORK_WAITING", "COMPLETED",
    "ERROR", "UNRESPONSIVE", "PAUSED", "UNKNOWN",
)

NOTIFICATION_CATEGORIES = (
    "approval_required", "permission_required", "task_error", "network_interruption",
    "task_completed", "task_crashed", "task_unresponsive", "security_warning",
    "recovery_required", "info",
)

CAPABILITIES = ("metrics", "logs", "commands", "approvals", "keep_awake")


@dataclass
class Envelope:
    op: Op
    payload: dict = field(default_factory=dict)
    seq: int = 0
    ts: str = ""

    def to_json(self) -> str:
        return json.dumps(
            {"v": PROTOCOL_VERSION, "op": self.op.value if isinstance(self.op, Op) else str(self.op),
             "seq": self.seq, "ts": self.ts, "payload": self.payload},
            separators=(",", ":"),
        )


def build(op: Op | str, payload: dict | None = None, seq: int = 0, ts: str = "") -> str:
    return Envelope(op=Op(op), payload=payload or {}, seq=seq, ts=ts).to_json()


def parse(raw: str | bytes) -> tuple[Op, dict, int]:
    """Parse and minimally validate an incoming envelope.

    Returns (op, payload, seq). Raises ProtocolError with a wire error code.
    """
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    if len(raw) > MAX_MESSAGE_BYTES:
        raise ProtocolError(ErrorCode.BAD_REQUEST.value, "message too large")
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProtocolError(ErrorCode.BAD_REQUEST.value, f"invalid JSON: {exc}") from None
    if not isinstance(obj, dict):
        raise ProtocolError(ErrorCode.BAD_REQUEST.value, "message must be a JSON object")
    version = obj.get("v")
    if version != PROTOCOL_VERSION:
        raise ProtocolError(ErrorCode.VERSION_MISMATCH.value,
                            f"unsupported protocol version {version!r}")
    op_raw = obj.get("op")
    try:
        op = Op(op_raw)
    except ValueError:
        raise ProtocolError(ErrorCode.BAD_REQUEST.value, f"unknown op {op_raw!r}") from None
    payload = obj.get("payload", {})
    if not isinstance(payload, dict):
        raise ProtocolError(ErrorCode.BAD_REQUEST.value, "payload must be an object")
    seq = obj.get("seq", 0)
    if not isinstance(seq, int) or seq < 0:
        seq = 0
    return op, payload, seq


def validate_command(payload: dict) -> tuple[CommandAction, str | None, dict]:
    """Validate a `command` payload. Returns (action, task_id, params).

    Raises ProtocolError(INVALID_COMMAND) on any violation. Actions are a closed
    enum; no arbitrary strings ever reach process-launching code.
    """
    action_raw = payload.get("action")
    try:
        action = CommandAction(action_raw)
    except ValueError:
        raise ProtocolError(ErrorCode.INVALID_COMMAND.value,
                            f"unknown action {action_raw!r}") from None
    task_id = payload.get("task_id")
    if action in (CommandAction.PAUSE, CommandAction.RESUME, CommandAction.RESTART,
                  CommandAction.CLOSE):
        if not isinstance(task_id, str) or not task_id:
            raise ProtocolError(ErrorCode.INVALID_COMMAND.value, f"{action.value} requires task_id")
    params = payload.get("params") or {}
    if not isinstance(params, dict):
        raise ProtocolError(ErrorCode.INVALID_COMMAND.value, "params must be an object")
    if action is CommandAction.SET_KEEP_AWAKE:
        if "enabled" not in params or not isinstance(params["enabled"], bool):
            raise ProtocolError(ErrorCode.INVALID_COMMAND.value,
                                "set_keep_awake requires params.enabled: bool")
    return action, task_id, params


def validate_approve(payload: dict) -> tuple[str, str, str | None]:
    request_id = payload.get("request_id")
    decision = payload.get("decision")
    note = payload.get("note")
    if not isinstance(request_id, str) or not request_id:
        raise ProtocolError(ErrorCode.INVALID_COMMAND.value, "approve requires request_id")
    if decision not in ("approve", "deny"):
        raise ProtocolError(ErrorCode.INVALID_COMMAND.value,
                            "decision must be 'approve' or 'deny'")
    if note is not None and not isinstance(note, str):
        raise ProtocolError(ErrorCode.INVALID_COMMAND.value, "note must be a string")
    return request_id, decision, note
