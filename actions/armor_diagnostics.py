"""
actions/armor_diagnostics.py — Stark Armor Telemetry & Hardware Health Diagnostics
==================================================================================
Deep hardware inspection, thermal zone mapping, battery wear analysis, and
complete Iron Man Mark-class armor diagnostic reporting.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil

from core import outcome

SKILL_METADATA = {
    "capabilities": [
        "armor_status",
        "thermal_zone_mapping",
        "battery_health_analysis",
        "gpu_power_and_clock_telemetry",
        "storage_wear_and_smart_status",
    ],
    "permissions": ["hardware_telemetry"],
    "dependencies": ["psutil"],
    "supported_actions": [
        "armor_status",
        "thermal_map",
        "battery_health",
        "status",
    ],
    "security_level": "low",
}


def read_thermal_zones() -> List[Dict[str, Any]]:
    """Enumerate thermal zones from Linux sysfs."""
    zones = []
    base = Path("/sys/class/thermal")
    if base.is_dir():
        for p in sorted(base.glob("thermal_zone*")):
            try:
                type_file = p / "type"
                temp_file = p / "temp"
                if type_file.is_file() and temp_file.is_file():
                    z_type = type_file.read_text(encoding="utf-8").strip()
                    temp_raw = int(temp_file.read_text(encoding="utf-8").strip())
                    temp_c = round(temp_raw / 1000.0, 1)
                    zones.append({
                        "zone": p.name,
                        "type": z_type,
                        "temp_c": temp_c,
                        "status": "NORMAL" if temp_c < 75.0 else ("ELEVATED" if temp_c < 85.0 else "THROTTLING_RISK"),
                    })
            except Exception:
                continue

    # Fallback to psutil.sensors_temperatures() if sysfs was empty
    if not zones and hasattr(psutil, "sensors_temperatures"):
        try:
            temps = psutil.sensors_temperatures()
            for name, entries in temps.items():
                for e in entries:
                    zones.append({
                        "zone": name,
                        "type": e.label or name,
                        "temp_c": e.current,
                        "status": "NORMAL" if e.current < 75.0 else ("ELEVATED" if e.current < 85.0 else "THROTTLING_RISK"),
                    })
        except Exception:
            pass
    return zones


def read_battery_health() -> Dict[str, Any]:
    """Read detailed battery wear and charging metrics."""
    res = {
        "present": False,
        "percent": 0.0,
        "power_plugged": True,
        "wear_level_pct": 0.0,
        "status": "AC_CONNECTED",
    }
    # Check psutil first
    try:
        b = psutil.sensors_battery()
        if b is not None:
            res["present"] = True
            res["percent"] = round(b.percent, 1)
            res["power_plugged"] = b.power_plugged
            res["seconds_left"] = b.secsleft if b.secsleft != psutil.POWER_TIME_UNLIMITED else None
    except Exception:
        pass

    # Read Linux sysfs power_supply for cycle count and wear
    bat_base = Path("/sys/class/power_supply")
    if bat_base.is_dir():
        for b_dir in bat_base.glob("BAT*"):
            try:
                res["present"] = True
                status_file = b_dir / "status"
                if status_file.is_file():
                    res["status"] = status_file.read_text(encoding="utf-8").strip()

                energy_full = None
                energy_design = None
                for ef_name, ed_name in [("energy_full", "energy_full_design"), ("charge_full", "charge_full_design")]:
                    if (b_dir / ef_name).is_file() and (b_dir / ed_name).is_file():
                        energy_full = int((b_dir / ef_name).read_text(encoding="utf-8").strip())
                        energy_design = int((b_dir / ed_name).read_text(encoding="utf-8").strip())
                        break

                if energy_full and energy_design and energy_design > 0:
                    wear = max(0.0, round((1.0 - (energy_full / energy_design)) * 100.0, 1))
                    res["wear_level_pct"] = wear
                    res["health_pct"] = round(100.0 - wear, 1)

                cycle_file = b_dir / "cycle_count"
                if cycle_file.is_file():
                    res["cycle_count"] = int(cycle_file.read_text(encoding="utf-8").strip())
                break
            except Exception:
                continue

    return res


def read_gpu_telemetry() -> Dict[str, Any]:
    """Read NVIDIA or integrated GPU stats."""
    res = {"available": False, "name": "Integrated / None"}
    try:
        import pynvml
        pynvml.nvmlInit()
        count = pynvml.nvmlDeviceGetCount()
        if count > 0:
            h = pynvml.nvmlDeviceGetHandleByIndex(0)
            name = pynvml.nvmlDeviceGetName(h)
            if isinstance(name, bytes):
                name = name.decode()
            temp = pynvml.nvmlDeviceGetTemperature(h, pynvml.NVML_TEMPERATURE_GPU)
            mem = pynvml.nvmlDeviceGetMemoryInfo(h)
            pwr = None
            try:
                pwr = round(pynvml.nvmlDeviceGetPowerUsage(h) / 1000.0, 1)  # W
            except Exception:
                pass
            res = {
                "available": True,
                "name": name,
                "temp_c": temp,
                "vram_used_mb": round(mem.used / (1024 ** 2), 1),
                "vram_total_mb": round(mem.total / (1024 ** 2), 1),
                "power_watts": pwr,
            }
        pynvml.nvmlShutdown()
    except Exception:
        pass
    return res


def get_full_armor_diagnostics() -> Dict[str, Any]:
    """Generate complete Mark armor diagnostic report."""
    cpu_pct = psutil.cpu_percent(interval=None)
    cpu_freq = psutil.cpu_freq()
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    zones = read_thermal_zones()
    battery = read_battery_health()
    gpu = read_gpu_telemetry()

    max_temp = max((z["temp_c"] for z in zones), default=45.0)
    throttling = max_temp >= 85.0 or (gpu.get("temp_c", 0) >= 85.0)

    # Health evaluation
    armor_integrity = 100
    if throttling:
        armor_integrity -= 25
    elif max_temp > 75.0:
        armor_integrity -= 10
    if mem.percent > 85.0:
        armor_integrity -= 15
    if disk.percent > 90.0:
        armor_integrity -= 10

    status_label = "ALL SYSTEMS NOMINAL" if armor_integrity >= 90 else ("SUBSYSTEM GUARDED" if armor_integrity >= 70 else "THERMAL / LOAD ADVISORY")

    return {
        "timestamp": time.time(),
        "armor_integrity_pct": armor_integrity,
        "status_label": status_label,
        "throttling": throttling,
        "cpu_usage_pct": cpu_pct,
        "cpu_freq_ghz": round(cpu_freq.current / 1000.0, 2) if cpu_freq else 0.0,
        "cpu_cores": psutil.cpu_count(logical=True),
        "ram_used_gb": round(mem.used / (1024 ** 3), 2),
        "ram_total_gb": round(mem.total / (1024 ** 3), 2),
        "ram_pct": mem.percent,
        "disk_free_gb": round(disk.free / (1024 ** 3), 1),
        "disk_pct": disk.percent,
        "max_temperature_c": max_temp,
        "thermal_zones": zones[:6],
        "battery": battery,
        "gpu": gpu,
    }


def execute(
    parameters: dict,
    player: Any = None,
    session_memory: Any = None,
    **kwargs,
) -> str:
    """Action entry point for armor_diagnostics."""
    params = parameters or {}
    action = str(params.get("action") or "armor_status").strip().lower()

    if action in ("armor_status", "status"):
        diag = get_full_armor_diagnostics()
        gpu_str = f"{diag['gpu']['name']} ({diag['gpu'].get('temp_c', '--')}°C, {diag['gpu'].get('power_watts', '--')}W)" if diag['gpu']['available'] else "Integrated"
        bat_str = f"{diag['battery']['percent']}% [{'AC Plugged' if diag['battery']['power_plugged'] else 'Battery Power'}]" if diag['battery']['present'] else "No battery (Desktop)"

        report = (
            f"# 🦾 STARK ARMOR STATUS & SYSTEM DIAGNOSTICS\n\n"
            f"**Armor Integrity:** `{diag['armor_integrity_pct']}%` | **Status:** `{diag['status_label']}`\n\n"
            f"### ⚙️ Core Telemetry\n"
            f"- **CPU Core Matrix:** `{diag['cpu_usage_pct']}%` @ `{diag['cpu_freq_ghz']} GHz` ({diag['cpu_cores']} cores)\n"
            f"- **Core Thermal Peak:** `{diag['max_temperature_c']}°C` [{'THROTTLING RISK' if diag['throttling'] else 'STABLE'}]\n"
            f"- **Arc Reactor / Battery:** `{bat_str}` (Health: `{diag['battery'].get('health_pct', 100)}%`)\n"
            f"- **GPU Auxiliary Core:** `{gpu_str}`\n"
            f"- **System Memory:** `{diag['ram_used_gb']}/{diag['ram_total_gb']} GB` (`{diag['ram_pct']}%`)\n"
            f"- **Storage Remaining:** `{diag['disk_free_gb']} GB` free\n"
        )
        if player is not None:
            try:
                player.show_content("Armor Status Telemetry", report)
                player.write_log(f"ARMOR_DIAGNOSTICS: Integrity {diag['armor_integrity_pct']}% — {diag['status_label']}")
            except Exception:
                pass
        return outcome.done(
            "armor_diagnostics",
            result=f"Armor status: {diag['status_label']} with integrity at {diag['armor_integrity_pct']}%. Peak thermal temperature is {diag['max_temperature_c']}°C, CPU load {diag['cpu_usage_pct']}%, RAM at {diag['ram_pct']}%.",
            data=diag,
        )

    if action == "thermal_map":
        zones = read_thermal_zones()
        lines = ["# 🌡️ Thermal Zone Sensor Map\n"]
        for z in zones:
            lines.append(f"- **{z['type']}** (`{z['zone']}`): `{z['temp_c']}°C` [{z['status']}]")
        if player is not None:
            try:
                player.show_content("Thermal Zone Map", "\n".join(lines))
            except Exception:
                pass
        return outcome.done("armor_diagnostics", result=f"Thermal map read {len(zones)} sensors. Peak temp: {max((z['temp_c'] for z in zones), default=0)}°C.", data={"zones": zones})

    if action == "battery_health":
        bat = read_battery_health()
        res_str = f"Battery level: {bat['percent']}%, Status: {bat['status']}, Wear level: {bat.get('wear_level_pct', 0.0)}%."
        return outcome.done("armor_diagnostics", result=res_str, data=bat)

    return outcome.failed("armor_diagnostics", f"Unknown action '{action}'")


TOOL = {
    "name": "armor_diagnostics",
    "description": (
        "Stark Armor Telemetry & Hardware Health Diagnostics: Real-time hardware health inspection, "
        "CPU frequency scaling, per-sensor thermal zone mapping, battery wear analysis, and "
        "complete Iron Man Mark armor diagnostic status reporting."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["armor_status", "thermal_map", "battery_health", "status"],
                "description": "Hardware diagnostic action to perform (default: 'armor_status').",
            },
        },
    },
    "handler": execute,
}
