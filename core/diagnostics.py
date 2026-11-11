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
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import psutil

from core.device_manager import get_device_manager
from core.memory_engine import get_memory_engine
from core.model_router import get_current_vram_gb, get_router
from core.orchestrator import get_orchestrator
from core.proactive_engine import get_proactive_engine
from core.security import get_session_auth_status
from core.workflow_engine import get_workflow_engine
from memory.config_manager import (
    get_autonomy_level,
    get_input_device,
    get_output_device,
    load_api_keys,
)


def diagnose_all_subsystems() -> dict[str, dict[str, Any]]:
    """Evaluate health states across all core AMATYA subsystems.

    States: Healthy, Degraded, Unavailable, Simulated, Not Configured.
    """
    subsystems: dict[str, dict[str, Any]] = {}

    # 1. Audio Pipeline
    in_dev = get_input_device()
    out_dev = get_output_device()
    has_pipewire = shutil.which("pipewire") is not None or shutil.which("pw-dump") is not None
    if has_pipewire or in_dev or out_dev:
        subsystems["audio"] = {
            "status": "Healthy",
            "details": f"Subsystem: PipeWire. In: {in_dev or 'default'}, Out: {out_dev or 'default'}",
        }
    else:
        subsystems["audio"] = {
            "status": "Degraded",
            "details": "Audio server not detected or running in fallback audio mode.",
        }

    # 2. AI Model Router & Local Models
    router = get_router()
    probed = router.probe_providers()
    local_online = any(v.get("online") for v in probed.values())
    gemini_key = load_api_keys().get("gemini_api_key") or os.environ.get("GEMINI_API_KEY")
    privacy = router.get_privacy_mode()

    if local_online and gemini_key:
        subsystems["models"] = {
            "status": "Healthy",
            "details": f"Hybrid active. Local providers online; Gemini fallback available. Privacy: {privacy}",
        }
    elif local_online and not gemini_key:
        subsystems["models"] = {
            "status": "Healthy" if privacy == "strict_local" else "Degraded",
            "details": f"Local provider online. No Gemini key set. Privacy: {privacy}",
        }
    elif not local_online and gemini_key:
        subsystems["models"] = {
            "status": "Unavailable" if privacy == "strict_local" else "Degraded",
            "details": f"Local inference offline; routing requests to cloud. Privacy: {privacy}",
        }
    else:
        subsystems["models"] = {
            "status": "Unavailable",
            "details": "Neither local model provider nor cloud Gemini API key configured.",
        }

    # 3. Layered Memory Engine
    mem = get_memory_engine()
    if mem.is_enabled():
        subsystems["memory"] = {
            "status": "Healthy",
            "details": f"Layered memory active. {len(mem.list_all_memories())} semantic facts stored.",
        }
    else:
        subsystems["memory"] = {
            "status": "Degraded",
            "details": "Memory engine is disabled by user policy.",
        }

    # 4. Wayland Desktop & KWin
    wayland_display = os.environ.get("WAYLAND_DISPLAY")
    xdg_session = os.environ.get("XDG_SESSION_TYPE", "")
    if wayland_display or xdg_session.lower() == "wayland":
        subsystems["desktop"] = {
            "status": "Healthy",
            "details": f"Wayland display active ({wayland_display or 'wayland-0'}). KWin integration ready.",
        }
    elif os.environ.get("DISPLAY"):
        subsystems["desktop"] = {
            "status": "Degraded",
            "details": f"Running under X11/XWayland ({os.environ.get('DISPLAY')}).",
        }
    else:
        subsystems["desktop"] = {
            "status": "Unavailable",
            "details": "No graphical desktop session detected.",
        }

    # 5. Connected Devices
    dm = get_device_manager()
    registered = dm.list_registered_devices()
    tv = dm.resolve_device("redmi_tv")
    tv_real = tv and (Path(tv.get("atvremote_bin", "")).exists() if tv.get("atvremote_bin") else False)
    tv_ip = tv.get("ip_address") if tv else ""
    subsystems["devices"] = {
        "status": "Healthy" if tv_real else "Simulated",
        "details": f"{len(registered)} devices registered. TV at {tv_ip or 'unconfigured'} (atvremote={'present' if tv_real else 'missing'}).",
    }

    # 6. Security Subsystem
    sec_status = get_session_auth_status()
    subsystems["security"] = {
        "status": "Healthy" if sec_status.get("pin_configured") else "Degraded",
        "details": f"Autonomy: {get_autonomy_level()}, Voice active: {sec_status.get('voice_session_active', False)}, PIN set: {sec_status.get('pin_configured', False)}",
    }

    return subsystems


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
            "privacy_mode": router.get_privacy_mode(),
        },
        "subsystems": diagnose_all_subsystems(),
        "memory": {
            "enabled": get_memory_engine().is_enabled(),
            "facts_count": len(get_memory_engine().list_all_memories()),
        },
        "workflows": {
            "count": len(get_workflow_engine().list_workflows()),
        },
        "proactive": {
            "active_alerts": len(get_proactive_engine().get_active_alerts()),
        },
    }


def format_command_centre_hud(telemetry: dict[str, Any] | None = None) -> str:
    """Render a futuristic holographic HUD status readout for AMATYA."""
    data = telemetry or gather_system_telemetry()
    hw = data["hardware"]
    sec = data["security"]
    tasks = data["tasks"]
    devs = data["devices"]
    subs = data.get("subsystems", {})
    sub_lines = [f"{k.capitalize()}:{v.get('status')[:3]}" for k, v in subs.items()]
    sub_str = " | ".join(sub_lines) if sub_lines else "All Systems Nominal"

    dev_lines = []
    for d in devs[:4]:
        dev_lines.append(f"  • {d['name']} ({d['type']}): {d['connectivity'].upper()}")

    privacy = data.get("model_router", {}).get("privacy_mode", "hybrid").upper()

    return (
        "╔══════════════════════════════════════════════════════════════════╗\n"
        "║                     AMATYA COMMAND CENTRE HUD                    ║\n"
        "╠══════════════════════════════════════════════════════════════════╣\n"
        f"║ CPU : {hw['cpu_percent']:>5.1f}% [{hw['cpu_cores']} Cores]       RAM : {hw['ram_used_gb']:>4.1f}/{hw['ram_total_gb']:<4.1f} GB ({hw['ram_percent']:>4.1f}%) ║\n"
        f"║ GPU : {hw['vram_used_gb']:>5.2f}/{hw['vram_total_gb']:<4.1f} GB VRAM     SAFE: {'YES' if hw['vram_safe'] else 'GUARDED!':<8}                     ║\n"
        "╠──────────────────────────────────────────────────────────────────╣\n"
        f"║ PRIVACY: {privacy:<15} AUTONOMY: {sec['autonomy_level'].upper():<20} VOICE: {'VERIFIED' if sec['voice_verified'] else 'GUEST':<8} ║\n"
        f"║ HEALTH : {sub_str:<55} ║\n"
        f"║ ACTIVE TASK: {tasks['summary'][:49]:<51} ║\n"
        "╠──────────────────────────────────────────────────────────────────╣\n"
        "║ CONNECTED DEVICES:                                               ║\n"
        + "\n".join(f"║ {line:<64} ║" for line in (dev_lines or ["  • No registered devices online"])) + "\n"
        "╚══════════════════════════════════════════════════════════════════╝"
    )
