"""
AMATYA Unified Diagnostics & Holographic Telemetry Engine (core/diagnostics.py)
==============================================================================
Aggregates complete, real-time hardware, process, device, audio, and model
telemetry for AMATYA's JARVIS-class Command Centre:
  - CPU utilization, frequency, and core distribution
  - System RAM and NVIDIA GPU VRAM metrics
  - Connected devices status (Xiaomi TV, Android Phone, KDE Connect)
  - Active Orchestrator tasks and progress
  - Audio pipeline and PipeWire status
  - Security, Autonomy Level, and Model Router states
"""
from __future__ import annotations

import os
import platform
import subprocess
import time
from typing import Any

import psutil

from core.device_manager import get_device_manager
from core.model_router import get_current_vram_gb, get_router
from core.orchestrator import get_orchestrator
from core.security import get_session_auth_status
from memory.config_manager import get_autonomy_level, get_input_device, get_output_device


def gather_system_telemetry() -> dict[str, Any]:
    """Capture snapshot of all operating companion telemetry."""
    # 1. CPU & Memory
    cpu_pct = psutil.cpu_percent(interval=None)
    cpu_cores = psutil.cpu_count(logical=True) or 4
    vmem = psutil.virtual_memory()
    ram_total_gb = round(vmem.total / (1024 ** 3), 2)
    ram_used_gb = round(vmem.used / (1024 ** 3), 2)
    ram_pct = vmem.percent

    # 2. GPU & VRAM
    vram_used_gb, vram_total_gb = get_current_vram_gb()
    router = get_router()
    gpu_name = router.hardware().gpu_name or "NVIDIA GeForce GTX 1650 Mobile"

    # 3. Audio & Devices
    in_dev = get_input_device() or "pipewire default"
    out_dev = get_output_device() or "pipewire default"

    # 4. Connected Devices
    dev_mgr = get_device_manager()
    registered = dev_mgr.list_registered_devices()
    dev_summary = []
    for d in registered:
        dev_summary.append({
            "name": d.get("name"),
            "type": d.get("type"),
            "connectivity": d.get("connectivity"),
            "ip": d.get("ip_address"),
            "status": d.get("status", {}),
        })

    # 5. Orchestrator Active Tasks
    orch = get_orchestrator()
    tasks = orch.list_tasks()
    active_tasks = [t for t in tasks if t.get("status") in ("running", "pending")]

    # 6. Security State
    auth_status = get_session_auth_status()

    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "platform": {
            "os": platform.system(),
            "release": platform.release(),
            "desktop_session": os.environ.get("XDG_SESSION_TYPE", "wayland"),
        },
        "hardware": {
            "cpu_percent": cpu_pct,
            "cpu_cores": cpu_cores,
            "ram_total_gb": ram_total_gb,
            "ram_used_gb": ram_used_gb,
            "ram_percent": ram_pct,
            "gpu_name": gpu_name,
            "vram_used_gb": vram_used_gb,
            "vram_total_gb": vram_total_gb,
            "vram_safe": vram_used_gb <= 3.5 if vram_total_gb >= 3.0 else True,
        },
        "audio": {
            "input_device": in_dev,
            "output_device": out_dev,
            "sample_rate": 48000,
            "subsystem": "PipeWire",
        },
        "devices": dev_summary,
        "tasks": {
            "active_count": len(active_tasks),
            "summary": orch.get_active_task_summary(),
            "active": active_tasks,
        },
        "security": {
            "autonomy_level": get_autonomy_level(),
            "voice_verified": auth_status.get("voice_session_active", False),
            "pin_configured": auth_status.get("pin_configured", False),
        },
        "model_router": {
            "reasoning": router.route("reasoning"),
            "planning": router.route("planning"),
            "coding": router.route("coding"),
        },
    }


def format_command_centre_hud(telemetry: dict[str, Any] | None = None) -> str:
    """Render a futuristic holographic HUD status readout for AMATYA."""
    data = telemetry or gather_system_telemetry()
    hw = data["hardware"]
    sec = data["security"]
    tasks = data["tasks"]
    devs = data["devices"]

    dev_lines = []
    for d in devs[:4]:
        dev_lines.append(f"  • {d['name']} ({d['type']}): {d['connectivity'].upper()}")

    return (
        "╔══════════════════════════════════════════════════════════════════╗\n"
        "║                     AMATYA COMMAND CENTRE HUD                    ║\n"
        "╠══════════════════════════════════════════════════════════════════╣\n"
        f"║ CPU : {hw['cpu_percent']:>5.1f}% [{hw['cpu_cores']} Cores]       RAM : {hw['ram_used_gb']:>4.1f}/{hw['ram_total_gb']:<4.1f} GB ({hw['ram_percent']:>4.1f}%) ║\n"
        f"║ GPU : {hw['vram_used_gb']:>5.2f}/{hw['vram_total_gb']:<4.1f} GB VRAM     SAFE: {'YES' if hw['vram_safe'] else 'GUARDED!':<8}                     ║\n"
        "╠──────────────────────────────────────────────────────────────────╣\n"
        f"║ AUTONOMY: {sec['autonomy_level'].upper():<20} VOICE VERIFIED: {'YES' if sec['voice_verified'] else 'NO':<13}  ║\n"
        f"║ ACTIVE TASK: {tasks['summary'][:49]:<51} ║\n"
        "╠──────────────────────────────────────────────────────────────────╣\n"
        "║ CONNECTED DEVICES:                                               ║\n"
        + "\n".join(f"║ {line:<64} ║" for line in (dev_lines or ["  • No registered devices online"])) + "\n"
        "╚══════════════════════════════════════════════════════════════════╝"
    )
