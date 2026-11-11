"""CYBER WORKSPACE — application settings (JSON, human-editable)."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

DEFAULTS = {
    "rain_enabled": True,
    "animations_enabled": True,
    "metrics_interval_s": 2.0,
    "net_probe_enabled": True,
    "unresponsive_timeout_s": 20,
    "max_tasks": 12,
    "remote_enabled": False,
    "remote_host": "0.0.0.0",
    "remote_port": 47770,
    "stop_timeout_s": 8.0,
    "start_minimized": False,
    "confirm_exit": True,
}


@dataclass
class AppSettings:
    rain_enabled: bool = True
    animations_enabled: bool = True
    metrics_interval_s: float = 2.0
    net_probe_enabled: bool = True
    unresponsive_timeout_s: int = 20
    max_tasks: int = 12
    remote_enabled: bool = False
    remote_host: str = "0.0.0.0"
    remote_port: int = 47770
    stop_timeout_s: float = 8.0
    start_minimized: bool = False
    confirm_exit: bool = True

    # ------------------------------------------------------------------
    @classmethod
    def path(cls, data_dir: Path) -> Path:
        return Path(data_dir) / "settings.json"

    @classmethod
    def load(cls, data_dir: Path) -> "AppSettings":
        p = cls.path(data_dir)
        data = dict(DEFAULTS)
        if p.exists():
            try:
                stored = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(stored, dict):
                    data.update({k: v for k, v in stored.items() if k in DEFAULTS})
            except (json.JSONDecodeError, OSError):
                pass
        return cls(**data)

    def save(self, data_dir: Path) -> None:
        p = self.path(data_dir)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(asdict(self), indent=2, sort_keys=True),
                     encoding="utf-8")

    def engine_overrides(self) -> dict:
        return {
            "unresponsive_timeout_s": self.unresponsive_timeout_s,
            "metrics_interval_s": self.metrics_interval_s,
            "max_tasks": self.max_tasks,
            "stop_timeout_s": self.stop_timeout_s,
        }
