"""State machine rules (master spec §7)."""
import pytest

from cyber_workspace.core.state import (UNKNOWN_REASON, SegmentKind,
                                        STATE_SEGMENT, TaskState, can_transition)


def test_all_eight_states_exist():
    assert {s.value for s in TaskState} == {
        "RUNNING", "WAITING_FOR_USER", "NETWORK_WAITING", "COMPLETED",
        "ERROR", "UNRESPONSIVE", "PAUSED", "UNKNOWN"}


def test_running_is_fully_connected():
    for s in TaskState:
        if s is not TaskState.RUNNING:
            assert can_transition(TaskState.RUNNING, s), s


def test_completed_is_terminal():
    assert not any(can_transition(TaskState.COMPLETED, s) for s in TaskState)


def test_error_is_not_completed():
    """A crashed task must never silently become COMPLETED."""
    assert not can_transition(TaskState.ERROR, TaskState.COMPLETED)
    assert not can_transition(TaskState.UNRESPONSIVE, TaskState.COMPLETED)


def test_unknown_can_go_anywhere():
    for s in TaskState:
        if s is not TaskState.UNKNOWN:
            assert can_transition(TaskState.UNKNOWN, s), s


def test_every_state_has_a_timer_bucket():
    for s in TaskState:
        assert s in STATE_SEGMENT
    assert STATE_SEGMENT[TaskState.WAITING_FOR_USER] is SegmentKind.WAITING
    assert STATE_SEGMENT[TaskState.NETWORK_WAITING] is SegmentKind.WAITING
    assert STATE_SEGMENT[TaskState.ERROR] is SegmentKind.ERROR
    assert STATE_SEGMENT[TaskState.UNRESPONSIVE] is SegmentKind.ERROR
    assert STATE_SEGMENT[TaskState.PAUSED] is SegmentKind.PAUSED
    assert STATE_SEGMENT[TaskState.UNKNOWN] is SegmentKind.UNKNOWN


def test_unknown_reason_string_is_honest():
    assert "could not be determined" in UNKNOWN_REASON.lower()
