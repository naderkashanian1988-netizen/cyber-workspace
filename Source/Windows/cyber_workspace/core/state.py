"""CYBER WORKSPACE — Task state machine.

Eight states per the master specification. The engine is the single writer of
task state: all transitions go through `TaskEngine._apply_transition`, which
validates against TRANSITIONS, records the reason and updates the tri-timer.

Core rule: a state is never changed without a reason. If the cause cannot be
determined reliably, the reason is recorded as "cause could not be determined"
and/or the task moves to UNKNOWN — a task is never reported COMPLETED merely
because its window or process disappeared.
"""
from __future__ import annotations

from enum import Enum

UNKNOWN_REASON = "cause could not be determined"


class TaskState(str, Enum):
    RUNNING = "RUNNING"
    WAITING_FOR_USER = "WAITING_FOR_USER"
    NETWORK_WAITING = "NETWORK_WAITING"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"
    UNRESPONSIVE = "UNRESPONSIVE"
    PAUSED = "PAUSED"
    UNKNOWN = "UNKNOWN"


class SegmentKind(str, Enum):
    """Time-accounting buckets for the tri-timer (plus paused, tracked separately)."""
    ACTIVE = "active"      # verified productive work
    WAITING = "waiting"    # waiting for user approval or network
    ERROR = "error"        # error / unavailable (incl. UNRESPONSIVE)
    PAUSED = "paused"      # deliberately paused by the user (not productive time)
    UNKNOWN = "unknown"    # cannot be determined confidently — never counted as active


# Which timer bucket each state maps to while the task sits in that state.
STATE_SEGMENT: dict[TaskState, SegmentKind] = {
    TaskState.RUNNING: SegmentKind.ACTIVE,
    TaskState.WAITING_FOR_USER: SegmentKind.WAITING,
    TaskState.NETWORK_WAITING: SegmentKind.WAITING,
    TaskState.COMPLETED: SegmentKind.ACTIVE,  # closed immediately; bucket irrelevant when frozen
    TaskState.ERROR: SegmentKind.ERROR,
    TaskState.UNRESPONSIVE: SegmentKind.ERROR,
    TaskState.PAUSED: SegmentKind.PAUSED,
    TaskState.UNKNOWN: SegmentKind.UNKNOWN,
}

# Valid state transitions. COMPLETED is terminal for a run; restart opens a new run.
TRANSITIONS: dict[TaskState, set[TaskState]] = {
    TaskState.RUNNING: {
        TaskState.WAITING_FOR_USER, TaskState.NETWORK_WAITING, TaskState.COMPLETED,
        TaskState.ERROR, TaskState.UNRESPONSIVE, TaskState.PAUSED, TaskState.UNKNOWN,
    },
    TaskState.WAITING_FOR_USER: {
        TaskState.RUNNING, TaskState.PAUSED, TaskState.ERROR,
        TaskState.UNRESPONSIVE, TaskState.UNKNOWN,
    },
    TaskState.NETWORK_WAITING: {
        TaskState.RUNNING, TaskState.PAUSED, TaskState.ERROR,
        TaskState.UNRESPONSIVE, TaskState.UNKNOWN, TaskState.COMPLETED,
    },
    TaskState.COMPLETED: set(),  # restart() starts a fresh run instead
    TaskState.ERROR: {
        TaskState.RUNNING, TaskState.PAUSED, TaskState.UNKNOWN,
    },
    TaskState.UNRESPONSIVE: {
        TaskState.RUNNING, TaskState.ERROR, TaskState.PAUSED, TaskState.UNKNOWN,
    },
    TaskState.PAUSED: {
        TaskState.RUNNING, TaskState.ERROR, TaskState.UNKNOWN,
    },
    TaskState.UNKNOWN: {
        TaskState.RUNNING, TaskState.WAITING_FOR_USER, TaskState.NETWORK_WAITING,
        TaskState.COMPLETED, TaskState.ERROR, TaskState.UNRESPONSIVE, TaskState.PAUSED,
    },
}


class StateTransitionError(RuntimeError):
    def __init__(self, current: TaskState, target: TaskState):
        super().__init__(f"illegal transition {current.value} -> {target.value}")
        self.current = current
        self.target = target


def can_transition(current: TaskState, target: TaskState) -> bool:
    return target in TRANSITIONS.get(current, set())
