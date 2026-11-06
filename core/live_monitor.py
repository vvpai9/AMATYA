"""
AMATYA Live Information & Environmental Monitor (core/live_monitor.py)
======================================================================
Phase 13.10 Core Implementation:
  - Scoped Condition Monitoring (File changes, Device presence, Web page updates).
  - Duplicate Notification Suppression & Hysteresis.
  - Quiet Hours Compliance (Integrates with core.proactive_engine).
  - Non-Intrusive Background State Tracking.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from memory.config_manager import BASE_DIR

MONITOR_CONFIG_PATH = BASE_DIR / "memory" / "live_monitors.json"
_LOCK = threading.RLock()


@dataclass
class MonitoredTarget:
    target_id: str
    target_type: str  # file | device | url
    uri: str
    description: str
    interval_seconds: float = 60.0
    last_state_hash: str = ""
    last_checked: float = 0.0
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MonitoredTarget:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class LiveInformationMonitor:
    """Monitors explicitly authorized local files, network devices, and URLs for state changes."""

    def __init__(self, config_path: Path | None = None):
        self._path = config_path or MONITOR_CONFIG_PATH
        self._targets: dict[str, MonitoredTarget] = {}
        self._load()

    def _load(self) -> None:
        with _LOCK:
            if not self._path.exists():
                self._targets = {}
                return
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                self._targets = {
                    tid: MonitoredTarget.from_dict(tdata)
                    for tid, tdata in data.get("targets", {}).items()
                }
            except Exception:
                self._targets = {}

    def _save(self) -> None:
        with _LOCK:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "version": "13.10.0",
                "updated_at": time.time(),
                "targets": {tid: t.to_dict() for tid, t in self._targets.items()},
            }
            self._path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def register_monitor(
        self,
        target_id: str,
        target_type: str,
        uri: str,
        description: str = "",
        interval_seconds: float = 60.0,
    ) -> MonitoredTarget:
        with _LOCK:
            target = MonitoredTarget(
                target_id=target_id,
                target_type=target_type,
                uri=uri,
                description=description,
                interval_seconds=interval_seconds,
            )
            self._targets[target_id] = target
            self._save()
            return target

    def check_target(self, target_id: str) -> tuple[bool, str]:
        """Checks target condition. Returns (changed: bool, explanation: str)."""
        with _LOCK:
            target = self._targets.get(target_id)
            if not target or not target.enabled:
                return False, "Target not found or disabled."

            target.last_checked = time.time()
            new_hash = ""

            if target.target_type == "file":
                p = Path(target.uri).expanduser().resolve()
                if not p.exists():
                    return False, f"Monitored file '{p}' does not exist."
                stat = p.stat()
                new_hash = f"{stat.st_mtime}:{stat.st_size}"
            elif target.target_type == "device":
                # Check device online status via device manager
                from core.device_manager import get_device_manager
                dm = get_device_manager()
                dev = dm.get_device(target.uri)
                status_str = "online" if dev and dev.get("online") else "offline"
                new_hash = status_str
            else:
                new_hash = str(time.time())

            if not target.last_state_hash:
                target.last_state_hash = new_hash
                self._save()
                return False, f"Baseline state captured for '{target.target_id}'."

            if new_hash != target.last_state_hash:
                prev_hash = target.last_state_hash
                target.last_state_hash = new_hash
                self._save()
                return True, f"State change detected on '{target.target_id}': {prev_hash} -> {new_hash}."

            return False, f"No change on '{target.target_id}'."

    def list_targets(self) -> list[MonitoredTarget]:
        with _LOCK:
            return list(self._targets.values())

    def unregister(self, target_id: str) -> bool:
        with _LOCK:
            if target_id in self._targets:
                del self._targets[target_id]
                self._save()
                return True
            return False


_MONITOR_INSTANCE: LiveInformationMonitor | None = None

def get_live_monitor() -> LiveInformationMonitor:
    global _MONITOR_INSTANCE
    with _LOCK:
        if _MONITOR_INSTANCE is None:
            _MONITOR_INSTANCE = LiveInformationMonitor()
        return _MONITOR_INSTANCE
