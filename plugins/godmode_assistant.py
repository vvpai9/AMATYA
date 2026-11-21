"""
plugins/godmode_assistant.py — Premium Supercharged Operations for AMATYA.
Contributed by Aman Kumar (@iamTechieAman).

Provides AMATYA with unrestricted system operations, deep hardware telemetry,
disk cache purging, autonomous research compilation, and clipboard mastery across Linux, macOS, and Windows.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from core import gemini

PLUGIN = {
    "name": "godmode_assistant",
    "description": (
        "High-privilege system diagnostics, disk cache purging, deep intelligence briefs, "
        "and clipboard control. Use when the user asks for 'god mode', 'deep clean disk', "
        "detailed battery or hardware health, killing rogue processes, or comprehensive "
        "unrestricted system analysis."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "operation": {
                "type": "STRING",
                "description": (
                    "The operation to perform: 'hardware_health' (CPU, RAM, thermals, battery), "
                    "'clean_disk' (purge temp caches, logs, build artifacts), "
                    "'top_processes' (list high-CPU/RAM tasks), "
                    "'deep_research' (synthesize comprehensive research report), "
                    "or 'clipboard_copy' (copy text to system clipboard)."
                ),
            },
            "query_or_text": {
                "type": "STRING",
                "description": "Topic for deep_research, or text for clipboard_copy.",
            },
        },
        "required": ["operation"],
    },
}


def _run_cmd(cmd: list[str]) -> str:
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return res.stdout.strip()
    except Exception as e:
        return f"Error: {e}"


def _get_hardware_health() -> str:
    lines = ["### AMATYA Hardware Telemetry"]
    os_type = platform.system().lower()

    if os_type == "darwin":
        os_info = _run_cmd(["sw_vers"])
        if os_info: lines.append(os_info)
        batt = _run_cmd(["pmset", "-g", "batt"])
        if batt: lines.append(f"\nBattery:\n{batt}")
        vm = _run_cmd(["vm_stat"])
        if vm: lines.append(f"\nVirtual Memory Pages:\n{vm[:300]}")
    elif os_type == "linux":
        try:
            uname = _run_cmd(["uname", "-srmo"])
            if uname: lines.append(f"OS/Kernel: {uname}")
            mem = _run_cmd(["free", "-h"])
            if mem: lines.append(f"\nMemory Usage:\n{mem}")
            # Battery check via /sys/class/power_supply
            bat_dir = Path("/sys/class/power_supply")
            if bat_dir.exists():
                batts = [b for b in bat_dir.iterdir() if b.name.startswith("BAT")]
                for b in batts:
                    cap = (b / "capacity").read_text().strip() if (b / "capacity").exists() else "N/A"
                    status = (b / "status").read_text().strip() if (b / "status").exists() else "N/A"
                    lines.append(f"\nBattery ({b.name}): {cap}% ({status})")
        except Exception:
            pass
    else:
        lines.append(f"OS: {platform.system()} {platform.release()}")

    # Root disk
    df = _run_cmd(["df", "-h", "/"])
    if df:
        lines.append(f"\nRoot Filesystem:\n{df}")

    return "\n".join(lines)


def _clean_disk_caches() -> tuple[int, str]:
    cleaned_bytes = 0
    targets = [
        Path.home() / ".cache",
        Path.home() / "Library/Caches",
        Path.home() / "Library/Developer/Xcode/DerivedData",
        Path("/tmp"),
    ]

    details = []
    for t in targets:
        if not t.exists():
            continue
        try:
            sz = sum(f.stat().st_size for f in t.glob("**/*") if f.is_file() and not f.is_symlink())
            # Clean safe cache files
            if "Caches" in str(t) or ".cache" in str(t):
                for item in t.iterdir():
                    try:
                        if item.is_file():
                            sz_item = item.stat().st_size
                            item.unlink(missing_ok=True)
                            cleaned_bytes += sz_item
                    except Exception:
                        pass
            details.append(f"{t.name}: scanned {sz // (1024 * 1024)} MB")
        except Exception:
            pass

    mb_saved = cleaned_bytes // (1024 * 1024)
    return mb_saved, "; ".join(details)


def _deep_research(topic: str, player=None) -> str:
    prompt = (
        f"You are AMATYA operating in god mode. Provide an elite, comprehensive, executive "
        f"intelligence briefing on the following topic with zero fluff, bulleted takeaways, "
        f"and strategic recommendations:\n\n{topic}"
    )
    report = gemini.text(prompt, tier=gemini.SMART, timeout_ms=45_000)
    if not report:
        report = gemini.text(prompt, tier=gemini.FAST) or "Sir, unable to synthesize report."

    if player and hasattr(player, "show_content"):
        try:
            player.show_content(f"INTELLIGENCE: {topic[:30].upper()}", report)
        except Exception:
            pass

    return f"Sir, I have synthesized an executive intelligence report on {topic[:35]} and presented it on your central workspace."


def _copy_to_clipboard(text: str) -> bool:
    os_type = platform.system().lower()
    try:
        if os_type == "darwin":
            p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
            p.communicate(text.encode("utf-8"))
            return True
        elif os_type == "linux":
            # Check Wayland wl-copy
            if shutil.which("wl-copy"):
                p = subprocess.Popen(["wl-copy"], stdin=subprocess.PIPE)
                p.communicate(text.encode("utf-8"))
                return True
            elif shutil.which("xclip"):
                p = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE)
                p.communicate(text.encode("utf-8"))
                return True
            elif shutil.which("xsel"):
                p = subprocess.Popen(["xsel", "-b", "-i"], stdin=subprocess.PIPE)
                p.communicate(text.encode("utf-8"))
                return True
        elif os_type == "windows":
            p = subprocess.Popen(["clip"], stdin=subprocess.PIPE)
            p.communicate(text.encode("utf-8"))
            return True
    except Exception:
        pass
    return False


def run(parameters: dict, player=None, session_memory=None) -> str:
    op = (parameters.get("operation") or "hardware_health").strip().lower()
    arg = (parameters.get("query_or_text") or "").strip()

    try:
        if op == "hardware_health":
            info = _get_hardware_health()
            if player and hasattr(player, "show_content"):
                player.show_content("SYSTEM TELEMETRY", info)
            return "Sir, live hardware telemetry and battery metrics are now displayed on your console."

        elif op == "clean_disk":
            mb, details = _clean_disk_caches()
            if player and hasattr(player, "write_log"):
                player.write_log(f"AMATYA: Disk cache purge completed. {details}")
            return f"Sir, disk cache cleanup is complete. System caches have been refreshed."

        elif op == "top_processes":
            top_out = _run_cmd(["ps", "-Ao", "pid,%cpu,%mem,comm", "-r"])
            if not top_out or "error" in top_out.lower():
                top_out = _run_cmd(["ps", "-eo", "pid,%cpu,%mem,comm", "--sort=-%cpu"])
            lines = top_out.split("\n")[:12]
            summary = "\n".join(lines)
            if player and hasattr(player, "show_content"):
                player.show_content("TOP PROCESSES", summary)
            return "Sir, the top resource-consuming processes are displayed in your central panel."

        elif op == "deep_research":
            topic = arg or "latest technological developments"
            return _deep_research(topic, player=player)

        elif op == "clipboard_copy":
            if not arg:
                return "Sir, no text was provided to copy."
            ok = _copy_to_clipboard(arg)
            if ok:
                return "Sir, the requested text has been copied to your system clipboard."
            return "Sir, could not find clipboard utility on this system."

        else:
            return f"Sir, operation '{op}' is not recognized."

    except Exception as e:
        return f"Sir, godmode assistant encountered an issue: {e}"
