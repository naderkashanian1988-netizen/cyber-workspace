"""CYBER WORKSPACE — network monitor (real OS measurements only).

* Speeds: psutil.net_io_counters() deltas over the sample interval — genuine
  byte counters from the OS, no smoothing/fabrication.
* Latency: TCP connect probe to a configurable target (default 1.1.1.1:443).
  This is TCP connect latency, NOT ICMP ping; it is labelled as such in the UI.
  ICMP requires elevated privileges on Windows, which we refuse (least privilege).
* Status: UP (last probe ok) / DOWN (probe failed) / UNKNOWN (probe disabled).
* Per-task network attribution is NOT reliably measurable without elevated
  ETW/packet-counter APIs, so per-task network activity is reported as
  unavailable (None) unless an adapter self-reports — never fabricated.
"""
from __future__ import annotations

import collections
import socket
import time as _time


class NetworkMonitor:
    def __init__(self, target=("1.1.1.1", 443), probe_interval_s: float = 5.0,
                 enabled: bool = True):
        self.target = target
        self.probe_interval_s = probe_interval_s
        self.enabled = enabled
        self.down_bps: float | None = None
        self.up_bps: float | None = None
        self.latency_ms: float | None = None
        self.status = "UNKNOWN"
        self.history: collections.deque = collections.deque(maxlen=360)
        self._prev: tuple[float, int, int] | None = None
        self._last_probe = 0.0

    def sample(self, now: float | None = None) -> dict:
        import psutil
        now = now if now is not None else _time.monotonic()
        try:
            c = psutil.net_io_counters()
            if self._prev is not None:
                dt = now - self._prev[0]
                if dt > 0:
                    self.down_bps = max(0.0, (c.bytes_recv - self._prev[1]) / dt)
                    self.up_bps = max(0.0, (c.bytes_sent - self._prev[2]) / dt)
            self._prev = (now, c.bytes_recv, c.bytes_sent)
        except Exception:
            self.down_bps = self.up_bps = None
        if self.enabled and (now - self._last_probe) >= self.probe_interval_s:
            self._last_probe = now
            self.latency_ms, self.status = self.tcp_probe()
        self.history.append((now, self.down_bps, self.up_bps,
                             self.latency_ms, self.status))
        return self.snapshot()

    def tcp_probe(self) -> tuple[float | None, str]:
        if not self.enabled:
            return None, "UNKNOWN"
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2.0)
            t0 = _time.monotonic()
            s.connect((self.target[0], int(self.target[1])))
            ms = (_time.monotonic() - t0) * 1000.0
            s.close()
            return round(ms, 1), "UP"
        except OSError:
            return None, "DOWN"

    def snapshot(self) -> dict:
        return {"down_bps": self.down_bps, "up_bps": self.up_bps,
                "latency_ms": self.latency_ms, "status": self.status}
