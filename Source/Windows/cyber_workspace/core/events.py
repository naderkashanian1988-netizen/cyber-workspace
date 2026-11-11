"""CYBER WORKSPACE — Thread-safe event bus.

Publishers (process reader threads, the remote server thread, engine ticks) push
events into per-subscriber queues. The Qt UI and the remote server each drain
their own queue, so a slow consumer can never block the engine, and a failed
consumer only loses its own queue.

Topics:
  task_update   payload = {"task_id": str}           (task state/field changed)
  notification  payload = notification dict          (also persisted)
  approval      payload = approval request dict
  audit         payload = {"ts","actor","action","detail"}
  system        payload = {"cpu_percent","ram_percent", ...}
  network       payload = {"down_bps","up_bps","latency_ms","status"}
  engine        payload = {"kind": str, ...}          (lifecycle notices, e.g. shutdown)
"""
from __future__ import annotations

import queue
import threading


class EventBus:
    def __init__(self, max_queue: int = 4000):
        self._lock = threading.Lock()
        self._subs: dict[int, queue.Queue] = {}
        self._next_id = 0
        self._max = max_queue

    def subscribe(self) -> tuple[int, queue.Queue]:
        with self._lock:
            self._next_id += 1
            sub_id = self._next_id
            q: queue.Queue = queue.Queue(maxsize=self._max)
            self._subs[sub_id] = q
            return sub_id, q

    def unsubscribe(self, sub_id: int) -> None:
        with self._lock:
            self._subs.pop(sub_id, None)

    def publish(self, topic: str, payload: dict) -> None:
        with self._lock:
            subs = list(self._subs.values())
        item = (topic, payload)
        for q in subs:
            try:
                q.put_nowait(item)
            except queue.Full:
                # Drop the OLDEST item to keep recent events flowing.
                try:
                    q.get_nowait()
                    q.put_nowait(item)
                except (queue.Empty, queue.Full):
                    pass
