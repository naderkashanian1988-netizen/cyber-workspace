"""CYBER WORKSPACE — system resource monitor (psutil, real values only).

All values come from psutil; anything that cannot be measured is None
("unavailable") and is displayed as such — never fabricated.
"""
from __future__ import annotations

import psutil


class SystemMonitor:
    def __init__(self):
        self.cpu_percent: float | None = None
        self.ram_percent: float | None = None
        self.ram_used_mb: float | None = None
        self.ram_total_mb: float | None = None
        try:
            psutil.cpu_percent(interval=None)  # prime the counter
        except Exception:
            pass

    def sample(self) -> dict:
        try:
            self.cpu_percent = psutil.cpu_percent(interval=None)
        except Exception:
            self.cpu_percent = None
        try:
            vm = psutil.virtual_memory()
            self.ram_percent = vm.percent
            self.ram_used_mb = vm.used / (1024 * 1024)
            self.ram_total_mb = vm.total / (1024 * 1024)
        except Exception:
            self.ram_percent = self.ram_used_mb = self.ram_total_mb = None
        return {"cpu_percent": self.cpu_percent, "ram_percent": self.ram_percent,
                "ram_used_mb": self.ram_used_mb, "ram_total_mb": self.ram_total_mb}

    @staticmethod
    def process_metrics(pid: int) -> tuple[float | None, float | None]:
        """(cpu_percent, ram_mb) for one process, or (None, None)."""
        try:
            p = psutil.Process(pid)
            return p.cpu_percent(interval=None), p.memory_info().rss / (1024 * 1024)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return None, None
        except psutil.Error:
            return None, None
