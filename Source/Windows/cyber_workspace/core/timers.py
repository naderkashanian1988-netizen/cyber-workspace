"""CYBER WORKSPACE — Independent per-task tri-timer.

Records three (plus paused/unknown) separate time measurements per task as
wall-clock UTC segments persisted to SQLite the moment they close:

  * active  — only verified / sufficiently reliable productive work
  * waiting — waiting for user approval or for the network
  * error   — error / unavailable time (incl. UNRESPONSIVE)
  * paused  — deliberately paused by the user
  * unknown — intervals where activity could not be determined confidently;
              NEVER counted as active work

Design notes
------------
* Wall-clock (UTC) start/end per segment => totals survive restarts and crashes
  without monotonic-clock drift or double counting. Monotonic time is used only
  for the live, in-memory display of the currently open segment.
* Exactly one segment is open at a time (the segment matching the task's current
  state). `transition_to` closes the open segment and opens the next one in the
  same call, so no gap/overlap can accumulate.
* `freeze()` (COMPLETED) closes the open segment; totals are then final.
* Crash recovery: `recover_orphans(cutoff_utc)` closes segments left open by a
  previous crashed run at a persisted cutoff (last seen time), so nothing is
  double counted.
"""
from __future__ import annotations

import datetime as _dt
import time as _time
from typing import Protocol

from .state import SegmentKind, STATE_SEGMENT, TaskState

UTC = _dt.timezone.utc


def now_utc() -> str:
    return _dt.datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_utc(ts: str) -> _dt.datetime:
    return _dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))


class TimerRepo(Protocol):
    def close_segment(self, task_id: str, seg_id: int, end_utc: str, end_kind_note: str | None = None) -> None: ...
    def open_segment(self, task_id: str, kind: SegmentKind, start_utc: str) -> int: ...
    def sum_totals(self, task_id: str) -> dict[str, int]: ...
    def close_orphans_for_task(self, task_id: str, end_utc: str) -> int: ...


class TriTimer:
    """Per-task timer owner. One instance per task; engine is the single writer."""

    def __init__(self, task_id: str, repo: TimerRepo):
        self.task_id = task_id
        self._repo = repo
        # Open segment: (seg_id, kind, start_utc, start_mono)
        self._open: tuple[int, SegmentKind, str, float] | None = None
        self.frozen = False

    # -- lifecycle ---------------------------------------------------------
    def set_bucket(self, kind: SegmentKind) -> None:
        """Ensure the open segment is of `kind`; switch by closing + opening.

        Used while a task stays RUNNING but its verifiable-activity bucket
        changes between ACTIVE and UNKNOWN.
        """
        if self.frozen:
            return
        if self._open is not None and self._open[1] is kind:
            return
        self._close_open()
        seg_id = self._repo.open_segment(self.task_id, kind, now_utc())
        self._open = (seg_id, kind, self._open_start_utc_or_now(), _time.monotonic())

    def transition_to(self, state: TaskState) -> None:
        """Close the currently open segment (if any) and open the segment that
        corresponds to `state`. Called by the engine on every state change."""
        if self.frozen:
            return
        kind = STATE_SEGMENT[state]
        self._close_open()
        if state is TaskState.COMPLETED:
            # completed: freeze; nothing stays open
            self.frozen = True
            return
        seg_id = self._repo.open_segment(self.task_id, kind, now_utc())
        self._open = (seg_id, kind, self._open_start_utc_or_now(), _time.monotonic())

    def _open_start_utc_or_now(self) -> str:
        return now_utc()

    def _close_open(self) -> None:
        if self._open is None:
            return
        seg_id, _kind, start_utc, start_mono = self._open
        elapsed = _time.monotonic() - start_mono
        end_utc = parse_utc(start_utc) + _dt.timedelta(seconds=elapsed)
        self._repo.close_segment(self.task_id, seg_id,
                                 end_utc.isoformat(timespec="milliseconds").replace("+00:00", "Z"))
        self._open = None

    def freeze(self) -> None:
        """Freeze final totals (task COMPLETED)."""
        self._close_open()
        self.frozen = True

    def recover_orphans(self, cutoff_utc: str) -> int:
        """Called once at startup: close any segment left open by a crashed run.

        The cutoff is the task's last persisted 'seen' time (or startup time if
        unavailable) so the dead interval is not stretched to 'now'.
        """
        closed = self._repo.close_orphans_for_task(self.task_id, cutoff_utc)
        self._open = None
        self.frozen = False
        return closed

    # -- reading -----------------------------------------------------------
    def live_elapsed_ms(self) -> int:
        """Elapsed ms of the currently open segment (for live UI display)."""
        if self._open is None:
            return 0
        _, _kind, _, start_mono = self._open
        return int((_time.monotonic() - start_mono) * 1000)

    def open_kind(self) -> SegmentKind | None:
        return self._open[1] if self._open else None

    def totals_ms(self) -> dict[str, int]:
        """Totals from persisted closed segments + the live open segment."""
        totals = self._repo.sum_totals(self.task_id)
        for kind in SegmentKind:
            totals.setdefault(kind.value, 0)
        if self._open is not None:
            _, kind, _, start_mono = self._open
            totals[kind.value] += int((_time.monotonic() - start_mono) * 1000)
        return totals

    def snapshot(self) -> dict[str, int]:
        t = self.totals_ms()
        return {
            "active_ms": t.get("active", 0),
            "waiting_ms": t.get("waiting", 0),
            "error_ms": t.get("error", 0),
            "paused_ms": t.get("paused", 0),
            "unknown_ms": t.get("unknown", 0),
        }
