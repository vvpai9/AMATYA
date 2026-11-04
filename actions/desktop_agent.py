"""
actions/desktop_agent.py — Autonomous desktop agent control for AMATYA.

WHAT THIS IS
    Exposes the core.desktop_agent.DesktopAgent as a JARVIS/AMATYA tool so the
    model can start, monitor, and cancel autonomous desktop automation tasks.

    The agent follows an observe → plan → act → verify loop:
        1. Observe      — capture the current screen (kwin-mcp / mss)
        2. Understand   — OCR text, identify UI elements
        3. Plan         — decide the next action toward the goal
        4. Act          — execute via kwin_desktop (type, click, etc.)
        5. Verify       — capture again, compare, confirm the action worked

TOOLS EXPOSED
    desktop_agent — control the autonomous agent:
        action='start'     — begin a new task (goal, autonomy, max_steps)
        action='cancel'    — cancel the running task
        action='status'    — get the current task status and steps
        action='autonomy'  — set autonomy level (observe_only/suggest/confirm/autonomous)

AUTONOMY LEVELS
    * observe_only   — watch and report, never act
    * suggest        — propose actions, wait for user approval
    * confirm        — execute low-risk actions, ask before destructive ones (default)
    * autonomous     — execute approved actions without asking (within limits)

CONFIRMATION
    Destructive operations (close_app, delete, send, publish) go through the
    confirmation gate regardless of autonomy level.

THREADING
    The agent runs as an asyncio task. Action handlers run in executor threads
    from main.py; the agent itself submits coroutines to main.py's event loop.
"""
from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional

from core import outcome
from core.desktop_agent import DesktopAgent, AutonomyLevel, get_desktop_agent
from core.lazyimport import installed

# Lazy, like every other heavy dependency in this file.
_PYAUTOGUI = installed("pyautogui")
pyautogui = None  # type: ignore[assignment]

if _PYAUTOGUI:
    from core.lazyimport import LazyModule

    def _configure_pa(module) -> None:
        module.FAILSAFE = True
        module.PAUSE = 0.05

    pyautogui = LazyModule("pyautogui", _configure_pa)


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


# ── action implementations ───────────────────────────────────────────────

def _desktop_agent_start(goal: str, autonomy: str = "confirm",
                         max_steps: int = 10, session=None) -> str:
    """Start a new autonomous desktop task."""
    agent = get_desktop_agent()
    try:
        task = agent.start_task(goal=goal, autonomy=autonomy,
                                max_steps=max_steps, session=session)
        return (f"desktop agent started: '{goal}' "
                f"(autonomy={autonomy}, max_steps={max_steps}, "
                f"task_id={id(task)})")
    except RuntimeError as e:
        return f"desktop agent: {e}"


def _desktop_agent_cancel() -> str:
    """Cancel the running task."""
    agent = get_desktop_agent()
    agent.cancel_task()
    return "desktop agent: cancelled"


def _desktop_agent_status() -> str:
    """Get the current task status."""
    agent = get_desktop_agent()
    task = agent.get_task()
    if task is None:
        return "desktop agent: no task running"
    steps_summary = ""
    for s in task.steps[-5:]:
        steps_summary += (
            f"  step {s.step_no}: {s.action or '(planning)'} "
            f"(verified={s.verified})\n"
        )
    return (
        f"desktop agent: {task.status}\n"
        f"  goal: {task.goal}\n"
        f"  autonomy: {task.autonomy.value}\n"
        f"  steps: {len(task.steps)}/{task.max_steps}\n"
        f"{steps_summary if steps_summary else '  (no steps yet)'}"
    )


def _desktop_agent_autonomy(level: str) -> str:
    """Set the autonomy level for future tasks."""
    if not level:
        return (
            "desktop agent: specify level (observe_only | recommend | confirm | "
            "autonomous_low_risk | autonomous_workflows)"
        )
    agent = get_desktop_agent()
    parsed = agent.set_default_autonomy(level)
    return f"desktop agent: default autonomy set to {parsed.value}"


def _desktop_agent_history() -> str:
    """List recent autonomous desktop tasks."""
    agent = get_desktop_agent()
    tasks = agent.get_history(limit=10)
    if not tasks:
        return "desktop agent: no task history yet."
    lines = ["desktop agent history:"]
    for i, t in enumerate(tasks, 1):
        lines.append(
            f"  {i}. [{t.status}] {t.goal} — {len(t.steps)} steps — {t.result or ''}"
        )
    return "\n".join(lines)


def _desktop_agent_observe(enable: bool, interval: float = 30.0) -> str:
    """Start or stop continuous opt-in desktop observation."""
    from core.screen_automation import get_automation
    sa = get_automation()
    if enable:
        sa.start_observation(interval_seconds=max(5.0, float(interval)))
        return f"desktop observation enabled (interval={interval}s)"
    sa.stop_observation()
    return "desktop observation stopped"


# ── entry point ──────────────────────────────────────────────────────────

def desktop_agent(
    parameters=None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """
    Dispatch table for autonomous desktop agent control.

    parameters keys:
        action     : (required) start | cancel | status | autonomy | history | observe_start | observe_stop
        goal       : natural language task description (for 'start')
        autonomy   : observe_only | recommend | confirm | autonomous_low_risk | autonomous_workflows
        max_steps  : maximum steps before giving up (for 'start', default: 10)
    """
    params = parameters or {}
    action = params.get("action", "").lower().strip()

    if not action:
        return "No action specified for desktop_agent."

    if player:
        print(f"[DesktopAgent] {action}")

    print(f"[DesktopAgent] ▶ {action}  {params}")

    try:
        if action == "start":
            return _desktop_agent_start(
                params.get("goal", ""),
                autonomy=params.get("autonomy", ""),
                max_steps=int(params.get("max_steps", 10)),
                session=response,
            )

        if action == "cancel":
            return _desktop_agent_cancel()

        if action == "status":
            return _desktop_agent_status()

        if action == "autonomy":
            return _desktop_agent_autonomy(params.get("level") or params.get("autonomy") or "")

        if action == "history":
            return _desktop_agent_history()

        if action == "observe_start":
            return _desktop_agent_observe(True, float(params.get("interval", 30.0)))

        if action == "observe_stop":
            return _desktop_agent_observe(False)

        return f"Unknown desktop_agent action: '{action}'"

    except Exception as e:
        print(f"[DesktopAgent] ❌ {action}: {e}")
        return f"desktop_agent '{action}' failed: {e}"


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────

TOOL = {
    "name": "desktop_agent",
    "description": (
        "Autonomous desktop agent for AMATYA. Start a task and the agent "
        "observes the screen, plans actions, executes them via kwin-desktop, "
        "and verifies results. Use for multi-step desktop tasks like 'open "
        "Chrome and search for weather', 'create a document and type a letter', "
        "or 'organize the desktop'. Actions: "
        "desktop_agent.start(goal, autonomy, max_steps) — begin a task; "
        "desktop_agent.cancel() — stop the current task; "
        "desktop_agent.status() — check progress; "
        "desktop_agent.autonomy(level) — set default autonomy level. "
        "Autonomy levels: observe_only (watch only), suggest (propose actions), "
        "confirm (execute with confirmation for destructive actions, default), "
        "autonomous (execute within limits). Destructive operations always "
        "require confirmation regardless of autonomy level."
    ),
    "brief": (
        "Autonomous desktop agent: start/cancel/status tasks with observe-plan-act-verify loop."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "start | cancel | status | autonomy",
            },
            "goal": {
                "type": "STRING",
                "description": "Natural language task description (for 'start').",
            },
            "autonomy": {
                "type": "STRING",
                "description": "observe_only | suggest | confirm | autonomous (default: confirm).",
            },
            "max_steps": {
                "type": "INTEGER",
                "description": "Maximum steps before giving up (default: 10).",
            },
            "level": {
                "type": "STRING",
                "description": "Autonomy level for 'autonomy' action.",
            },
        },
        "required": ["action"],
    },
    "handler": desktop_agent,
}
