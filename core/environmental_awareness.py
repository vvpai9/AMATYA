"""
AMATYA Environmental Awareness Engine (core/environmental_awareness.py)
========================================================================
Phase 16 Core Objective A:
Maintains lightweight, debounced situational awareness without CPU-spinning loops:
  - Active desktop window and focused application
  - System telemetry (CPU, RAM, disk, thermal, battery)
  - Connected devices status (Android phone, audio devices, smart home)
  - Critical environment alerts
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)
_LOCK = threading.RLock()


@dataclass
class EnvironmentalSnapshot:
    timestamp: float = field(default_factory=time.time)
    active_window: Dict[str, str] = field(default_factory=lambda: {"title": "", "app_name": "", "window_id": ""})
    system_health: Dict[str, Any] = field(default_factory=dict)
    connected_devices: List[Dict[str, Any]] = field(default_factory=list)
    telemetry_alerts: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EnvironmentalAwareness:
    """Provides cached, debounced situational telemetry for the cognitive core."""

    def __init__(self, cache_ttl_seconds: float = 2.0) -> None:
        self.cache_ttl = cache_ttl_seconds
        self._last_snapshot: Optional[EnvironmentalSnapshot] = None
        self._last_snapshot_time: float = 0.0

    def get_snapshot(self, force_refresh: bool = False) -> EnvironmentalSnapshot:
        """Get an environmental snapshot, using cached telemetry if within TTL."""
        with _LOCK:
            now = time.time()
            if not force_refresh and self._last_snapshot and (now - self._last_snapshot_time < self.cache_ttl):
                return self._last_snapshot

            snapshot = self._gather_snapshot()
            self._last_snapshot = snapshot
            self._last_snapshot_time = now
            return snapshot

    def _gather_snapshot(self) -> EnvironmentalSnapshot:
        snap = EnvironmentalSnapshot()

        # 1. Desktop active window
        snap.active_window = self._get_active_window()

        # 2. System health & telemetry
        snap.system_health, alerts = self._get_system_health()
        snap.telemetry_alerts = alerts

        # 3. Connected devices
        snap.connected_devices = self._get_connected_devices()

        return snap

    def _get_active_window(self) -> Dict[str, str]:
        """Detect active window on Linux X11/Wayland with fallback to context manager."""
        # Try xdotool if installed
        try:
            if shutil.which("xdotool"):
                wid_proc = subprocess.run(
                    ["xdotool", "getactivewindow"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    timeout=0.5,
                )
                if wid_proc.returncode == 0 and wid_proc.stdout.strip():
                    wid = wid_proc.stdout.strip()
                    name_proc = subprocess.run(
                        ["xdotool", "getwindowname", wid],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,
                        text=True,
                        timeout=0.5,
                    )
                    title = name_proc.stdout.strip() if name_proc.returncode == 0 else ""
                    return {"title": title, "app_name": "", "window_id": wid}
        except Exception:
            pass

        # Fallback to ContextManager state
        try:
            from core.context_manager import get_context_manager
            cm = get_context_manager()
            st = cm.get_state()
            return {
                "title": st.get("current_window_title") or "",
                "app_name": st.get("last_app") or "",
                "window_id": st.get("current_window_id") or "",
            }
        except Exception:
            return {"title": "", "app_name": "", "window_id": ""}

    def _get_system_health(self) -> tuple[Dict[str, Any], List[str]]:
        """Collect CPU, RAM, disk, thermal, and battery metrics safely."""
        health: Dict[str, Any] = {
            "cpu_pct": 0.0,
            "ram_pct": 0.0,
            "disk_free_gb": 0.0,
            "max_temp_c": 0.0,
            "battery_pct": None,
            "power_plugged": True,
        }
        alerts: List[str] = []

        try:
            import psutil
            cpu = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            health["cpu_pct"] = float(cpu)
            health["ram_pct"] = float(ram.percent)
            health["disk_free_gb"] = round(disk.free / (1024 ** 3), 1)

            if ram.percent > 90.0:
                alerts.append(f"High RAM usage: {ram.percent:.1f}%")
            if cpu > 95.0:
                alerts.append(f"High CPU load: {cpu:.1f}%")
            if (disk.free / (1024 ** 3)) < 5.0:
                alerts.append(f"Low disk space: {health['disk_free_gb']} GB free")

            # Battery
            sensors_battery = getattr(psutil, "sensors_battery", None)
            if callable(sensors_battery):
                bat = sensors_battery()
                if bat:
                    health["battery_pct"] = round(bat.percent, 1)
                    health["power_plugged"] = bat.power_plugged
                    if not bat.power_plugged and bat.percent < 20.0:
                        alerts.append(f"Low battery: {bat.percent:.1f}%")

            # Thermal sensors
            sensors_temps = getattr(psutil, "sensors_temperatures", None)
            if callable(sensors_temps):
                temps = sensors_temps()
                max_t = 0.0
                for entries in temps.values():
                    for entry in entries:
                        if entry.current and entry.current > max_t:
                            max_t = entry.current
                health["max_temp_c"] = round(max_t, 1)
                if max_t > 90.0:
                    alerts.append(f"Thermal warning: Peak temperature {max_t:.1f}°C")

        except Exception as e:
            logger.debug(f"psutil telemetry error: {e}")

        return health, alerts

    def _get_connected_devices(self) -> List[Dict[str, Any]]:
        """Collect connected Android / audio / smart home devices."""
        devices: List[Dict[str, Any]] = []
        try:
            from core.device_manager import get_device_manager
            dm = get_device_manager()
            if hasattr(dm, "list_devices"):
                for d in dm.list_devices():
                    if isinstance(d, dict):
                        devices.append(d)
        except Exception:
            pass
        return devices


_ENV_AWARENESS = EnvironmentalAwareness()


def get_environmental_awareness() -> EnvironmentalAwareness:
    return _ENV_AWARENESS

