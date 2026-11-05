"""
core/desktop_agent.py — Autonomous Wayland-native desktop agent for AMATYA.

WHAT THIS IS
    An agent that follows the observe → plan → act → verify loop:

        1. Observe      — capture the current screen (kwin-mcp / mss), active window,
                          open window list, and AT-SPI2 accessibility elements
        2. Understand   — OCR text, active window state, accessible UI tree
        3. Plan         — decide the next action toward the goal (ModelRouter / Gemini VLM),
                          preferring AT-SPI2 accessibility actions, D-Bus/CLI, and hotkeys
                          before falling back to screen coordinates
        4. Act          — execute via kwin-mcp client (invoke_ui_action, focus, type, click, etc.)
        5. Verify       — capture again, compare screenshots & window state, confirm outcome
        6. Recover      — if an action fails or screen is unchanged, replan or try fallback
        7. Repeat       — until the task is complete, cancelled, or max_steps reached

AUTONOMY LEVELS (Section 14)
    * Level 1: observe_only          — watch and report, never act
    * Level 2: recommend (suggest)   — propose actions, wait for user approval
    * Level 3: confirm               — execute with confirmation for sensitive/destructive ops
    * Level 4: autonomous_low_risk   — execute low-risk actions automatically, confirm destructive
    * Level 5: autonomous_workflows  — execute approved multi-step workflows autonomously
"""
from __future__ import annotations

import asyncio
import os
import re
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from core import confirm as confirm_gate
from core import gemini as _gemini
from core.screen_automation import ScreenAutomation, get_automation
from core.vision import Vision, get_vision


class AutonomyLevel(Enum):
    OBSERVE_ONLY = "observe_only"                  # Level 1
    RECOMMEND = "recommend"                        # Level 2
    SUGGEST = "suggest"                            # Alias for Level 2
    CONFIRM = "confirm"                            # Level 3
    AUTONOMOUS_LOW_RISK = "autonomous_low_risk"    # Level 4
    AUTONOMOUS_WORKFLOWS = "autonomous_workflows"  # Level 5
    AUTONOMOUS = "autonomous"                      # Alias for Level 5

    @classmethod
    def parse(cls, value: str | "AutonomyLevel") -> "AutonomyLevel":
        if isinstance(value, cls):
            return value
        norm = str(value or "confirm").strip().lower()
        aliases = {
            "1": cls.OBSERVE_ONLY,
            "level_1": cls.OBSERVE_ONLY,
            "observe": cls.OBSERVE_ONLY,
            "observe_only": cls.OBSERVE_ONLY,
            "2": cls.RECOMMEND,
            "level_2": cls.RECOMMEND,
            "recommend": cls.RECOMMEND,
            "suggest": cls.SUGGEST,
            "3": cls.CONFIRM,
            "level_3": cls.CONFIRM,
            "confirm": cls.CONFIRM,
            "4": cls.AUTONOMOUS_LOW_RISK,
            "level_4": cls.AUTONOMOUS_LOW_RISK,
            "autonomous_low_risk": cls.AUTONOMOUS_LOW_RISK,
            "low_risk": cls.AUTONOMOUS_LOW_RISK,
            "5": cls.AUTONOMOUS_WORKFLOWS,
            "level_5": cls.AUTONOMOUS_WORKFLOWS,
            "autonomous_workflows": cls.AUTONOMOUS_WORKFLOWS,
            "autonomous": cls.AUTONOMOUS,
        }
        return aliases.get(norm, cls.CONFIRM)


_DESTRUCTIVE_KEYWORDS = (
    "close_window", "delete", "remove", "rm ", "format", "shutdown",
    "reboot", "poweroff", "send", "publish", "submit", "pay", "purchase",
    "uninstall", "kill", "alt+f4", "ctrl+q",
)


def _is_high_risk_action(plan: str) -> bool:
    low = plan.lower()
    return any(k in low for k in _DESTRUCTIVE_KEYWORDS)


@dataclass
class AgentStep:
    """One step in the agent's execution."""
    step_no: int
    observation: str
    plan: str
    action: Optional[str] = None
    action_result: Optional[str] = None
    verified: bool = False
    verification_note: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class AgentTask:
    """A desktop automation task."""
    goal: str
    autonomy: AutonomyLevel = AutonomyLevel.CONFIRM
    max_steps: int = 10
    steps: list[AgentStep] = field(default_factory=list)
    status: str = "pending"   # pending, running, completed, blocked, failed
    result: Optional[str] = None
    started_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    session: Optional[Any] = None


# Key name normalization for kwin-mcp
_KEY_NAME_MAP = {
    "enter": "Return",
    "return": "Return",
    "esc": "Escape",
    "escape": "Escape",
    "tab": "Tab",
    "space": "Space",
    "backspace": "Backspace",
    "delete": "Delete",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    "home": "Home",
    "end": "End",
    "pageup": "PageUp",
    "pagedown": "PageDown",
    "insert": "Insert",
    "f1": "F1", "f2": "F2", "f3": "F3", "f4": "F4",
    "f5": "F5", "f6": "F6", "f7": "F7", "f8": "F8",
    "f9": "F9", "f10": "F10", "f11": "F11", "f12": "F12",
}


def _normalize_key(key: str) -> str:
    parts = [p.strip() for p in key.split("+") if p.strip()]
    return "+".join(_KEY_NAME_MAP.get(p.lower(), p) for p in parts)


class DesktopAgent:
    """
    Autonomous Wayland-native desktop agent.

    Executes the observe → plan → act → verify → recover loop using
    AT-SPI2 accessibility, D-Bus/CLI, and KWin Wayland input/capture.
    """

    def __init__(self, log=None):
        self._log = log or (lambda m: None)
        self._automation = get_automation(log=log)
        self._vision = get_vision(log=log)
        self._current_task: Optional[AgentTask] = None
        self._history: list[AgentTask] = []
        self._default_autonomy: AutonomyLevel = AutonomyLevel.CONFIRM
        self._task_lock = threading.Lock()
        self._cancel = False
        self._worker_thread: Optional[threading.Thread] = None

    # ── autonomy configuration ─────────────────────────────────────────

    @property
    def default_autonomy(self) -> AutonomyLevel:
        return self._default_autonomy

    def set_default_autonomy(self, level: str | AutonomyLevel) -> AutonomyLevel:
        self._default_autonomy = AutonomyLevel.parse(level)
        self._log(f"[DesktopAgent] default autonomy set to {self._default_autonomy.value}")
        return self._default_autonomy

    # ── task lifecycle ─────────────────────────────────────────────────

    def start_task(
        self,
        goal: str,
        autonomy: Optional[str] = None,
        max_steps: int = 10,
        session: Optional[Any] = None,
        blocking: bool = False,
    ) -> AgentTask:
        """Start a new autonomous desktop task."""
        with self._task_lock:
            if self._current_task is not None and self._current_task.status == "running":
                raise RuntimeError("a task is already running")

            level = AutonomyLevel.parse(autonomy) if autonomy else self._default_autonomy
            task = AgentTask(
                goal=goal,
                autonomy=level,
                max_steps=max_steps,
                status="running",
                session=session,
            )
            self._current_task = task
            self._cancel = False

        self._log(f"[DesktopAgent] task started: {goal} (autonomy={level.value})")
        self._log(f"[DesktopAgent] max steps: {max_steps}")

        if blocking:
            asyncio.run(self._run_task(task))
            return task

        # Run in a dedicated daemon thread with its own event loop so start_task()
        # works reliably whether called from an executor thread, Qt thread, or async loop.
        def _runner():
            try:
                asyncio.run(self._run_task(task))
            except Exception as e:
                self._log(f"[DesktopAgent] runner thread error: {e}")

        self._worker_thread = threading.Thread(
            target=_runner, daemon=True, name="amatya-desktop-agent"
        )
        self._worker_thread.start()
        return task

    def cancel_task(self) -> None:
        """Cancel the running task immediately."""
        with self._task_lock:
            self._cancel = True
            if self._current_task and self._current_task.status == "running":
                self._current_task.status = "blocked"
                self._current_task.result = "cancelled by user"
        self._log("[DesktopAgent] task cancelled by user")

    def get_task(self) -> Optional[AgentTask]:
        """Return the current or most recent task, if any."""
        with self._task_lock:
            return self._current_task

    def get_history(self, limit: int = 10) -> list[AgentTask]:
        """Return recent completed/cancelled/failed tasks."""
        with self._task_lock:
            return list(self._history[-limit:])

    @property
    def autonomy(self) -> str:
        return self._default_autonomy.value

    def set_autonomy(self, level: str) -> None:
        self._default_autonomy = AutonomyLevel(level)

    # ── desktop context gathering (accessibility + windows) ────────────

    def _gather_desktop_context(self) -> str:
        """Gather active window, open windows, and visible AT-SPI2 elements."""
        lines: list[str] = []
        try:
            client = self._get_client()
            windows = client.get_kwin_windows()
            if windows:
                lines.append("OPEN WINDOWS:")
                for w in windows[:15]:
                    act = " [ACTIVE]" if w.get("active") else ""
                    lines.append(
                        f"  - id={w.get('id')} app={w.get('app')} "
                        f"caption={w.get('caption')!r} "
                        f"geom=({w.get('x')},{w.get('y')} {w.get('width')}x{w.get('height')}){act}"
                    )
            # Query accessible interactive elements in the active application
            active_app = next((w.get("app") for w in windows if w.get("active")), None)
            el_res = client.find_ui_elements(query="", app_name=active_app, states=["visible"])
            if isinstance(el_res, dict):
                sc = el_res.get("structuredContent") or el_res.get("structured_content") or {}
                elements = sc.get("elements") if isinstance(sc, dict) else []
                if isinstance(elements, list) and elements:
                    lines.append("ACCESSIBLE UI ELEMENTS (prefer kwin_element_act over coordinates):")
                    shown = 0
                    for el in elements:
                        if not isinstance(el, dict):
                            continue
                        name = str(el.get("name") or "").strip()
                        role = str(el.get("role") or "").strip()
                        actions = el.get("actions") or []
                        rect = el.get("rect")
                        if not name and not actions:
                            continue
                        rect_str = ""
                        if isinstance(rect, dict):
                            cx = int(rect.get("x", 0)) + int(rect.get("width", 0)) // 2
                            cy = int(rect.get("y", 0)) + int(rect.get("height", 0)) // 2
                            rect_str = f" center=({cx},{cy})"
                        lines.append(
                            f"  - role={role!r} name={name!r} actions={actions}{rect_str}"
                        )
                        shown += 1
                        if shown >= 25:
                            break
        except Exception as e:
            lines.append(f"(accessibility context unavailable: {e})")
        return "\n".join(lines)

    # ── agent loop ─────────────────────────────────────────────────────

    async def _run_task(self, task: AgentTask) -> None:
        """Main observe → plan → act → verify → recover loop."""
        unchanged_streak = 0
        try:
            while len(task.steps) < task.max_steps and not self._cancel:
                step_no = len(task.steps) + 1

                # 1. OBSERVE
                self._log(f"[DesktopAgent] step {step_no}: observing desktop")
                cap = await asyncio.to_thread(self._automation.capture_full)
                if not cap.ok:
                    task.status = "failed"
                    task.result = f"screen capture failed: {cap.error}"
                    self._log(f"[DesktopAgent] {task.result}")
                    break

                observation = f"screen captured: {cap.size_kb}KB, hash={cap.hash}"
                ocr = await asyncio.to_thread(self._vision.ocr, cap.image_bytes)
                if ocr.ok and ocr.text:
                    observation += f"; OCR text: {ocr.text[:300]}"

                ui_ctx = await asyncio.to_thread(self._gather_desktop_context)
                if ui_ctx:
                    observation += f"\n{ui_ctx}"

                # 2. PLAN — ask the model what to do next.
                plan = await self._plan_next(
                    step_no, task.goal, cap, task.steps, ui_ctx, unchanged_streak
                )
                if plan is None:
                    task.status = "failed"
                    task.result = "planner returned no action"
                    break

                plan_clean = plan.strip()
                if plan_clean.upper().startswith("DONE:"):
                    task.status = "completed"
                    task.result = plan_clean[len("DONE:"):].strip() or "task complete"
                    task.completed_at = time.time()
                    self._log(f"[DesktopAgent] task completed: {task.result}")
                    break
                if plan_clean.lower() in ("done", "complete", "finished"):
                    task.status = "completed"
                    task.result = "task complete"
                    task.completed_at = time.time()
                    self._log(f"[DesktopAgent] task completed: {task.result}")
                    break

                # 3. Check autonomy level & confirmation policy.
                if task.autonomy == AutonomyLevel.OBSERVE_ONLY:
                    task.status = "blocked"
                    task.result = f"observe-only mode: observed state, next planned action would be: {plan_clean}"
                    break

                if task.autonomy in (AutonomyLevel.RECOMMEND, AutonomyLevel.SUGGEST):
                    self._log(f"[DesktopAgent] recommended action: {plan_clean}")
                    task.status = "blocked"
                    task.result = f"recommended action (awaiting approval): {plan_clean}"
                    break

                # In CONFIRM or AUTONOMOUS_LOW_RISK mode, gate destructive/high-risk actions
                if _is_high_risk_action(plan_clean) and task.autonomy in (
                    AutonomyLevel.CONFIRM,
                    AutonomyLevel.AUTONOMOUS_LOW_RISK,
                    AutonomyLevel.AUTONOMOUS_WORKFLOWS,
                    AutonomyLevel.AUTONOMOUS,
                ):
                    approved = await asyncio.to_thread(
                        confirm_gate.ask,
                        title="Confirm Desktop Action",
                        detail=f"Goal: {task.goal}\nAction: {plan_clean}",
                    )
                    if not approved:
                        task.status = "blocked"
                        task.result = f"user declined high-risk action: {plan_clean}"
                        break
                elif task.autonomy == AutonomyLevel.CONFIRM:
                    # Level 3 (CONFIRM): ask confirmation before state-modifying steps
                    # unless it's a read-only step (screenshot, list_windows, element_query)
                    is_read_only = any(
                        plan_clean.startswith(ro)
                        for ro in ("kwin_screenshot", "kwin_list_windows", "kwin_element_query")
                    )
                    if not is_read_only and step_no == 1:
                        approved = await asyncio.to_thread(
                            confirm_gate.ask,
                            title="Approve Desktop Automation",
                            detail=f"Goal: {task.goal}\nFirst action: {plan_clean}",
                        )
                        if not approved:
                            task.status = "blocked"
                            task.result = f"user declined action: {plan_clean}"
                            break

                # 4. ACT — execute via kwin-mcp.
                self._log(f"[DesktopAgent] step {step_no}: acting: {plan_clean}")
                action_result = await self._act(plan_clean)
                step = AgentStep(
                    step_no=step_no,
                    observation=observation[:600],
                    plan=plan_clean,
                    action=plan_clean,
                    action_result=action_result,
                )
                task.steps.append(step)

                # Brief pause for UI animations/rendering to settle on Wayland
                await asyncio.sleep(0.35)

                # 5. VERIFY — capture again and compare.
                after = await asyncio.to_thread(self._automation.capture_full)
                comp = await asyncio.to_thread(self._vision.compare, cap, after)
                action_ok = not str(action_result).lower().startswith(("error:", "unrecognized"))
                step.verified = bool(comp.changed or (action_ok and "list_windows" in plan_clean))
                step.verification_note = (
                    f"screen changed: {comp.changed}, similarity={comp.similarity}, "
                    f"action_ok={action_ok}"
                )
                self._log(
                    f"[DesktopAgent] step {step_no} verified: {step.verified} — "
                    f"{step.verification_note}"
                )

                if not comp.changed:
                    unchanged_streak += 1
                    if unchanged_streak >= 2:
                        self._log(
                            f"[DesktopAgent] screen unchanged for {unchanged_streak} steps; "
                            "instructing planner to recover/replan"
                        )
                else:
                    unchanged_streak = 0

            if self._cancel:
                task.status = "blocked"
                task.result = "cancelled by user"
            elif task.status not in ("completed", "failed", "blocked"):
                task.status = "blocked"
                task.result = f"max steps ({task.max_steps}) reached without completion"

        except Exception as e:
            self._log(f"[DesktopAgent] task error: {e}")
            task.status = "failed"
            task.result = str(e)
        finally:
            task.completed_at = time.time()
            with self._task_lock:
                self._history.append(task)
                if len(self._history) > 50:
                    self._history = self._history[-50:]
            self._log(f"[DesktopAgent] task finished: {task.status} — {task.result}")

    # ── planning ─────────────────────────────────────────────────────────

    async def _plan_next(
        self,
        step_no: int,
        goal: str,
        cap: Any,
        previous_steps: list[AgentStep],
        ui_ctx: str = "",
        unchanged_streak: int = 0,
    ) -> Optional[str]:
        """Ask the VLM / planning model what the next action should be."""
        history_summary = ""
        if previous_steps:
            lines = []
            for s in previous_steps[-5:]:
                lines.append(
                    f"  step {s.step_no}: {s.action or '(planning)'} "
                    f"-> {s.action_result or '(pending)'} (verified={s.verified})"
                )
            history_summary = "\n".join(lines)

        recovery_hint = ""
        if unchanged_streak >= 1:
            recovery_hint = (
                "\nWARNING: The previous action did NOT change the screen! "
                "Do NOT repeat the exact same action. Try an alternative method: "
                "use kwin_element_act, kwin_focus_window, kwin_launch_app, or a keyboard shortcut.\n"
            )

        prompt = (
            f"GOAL: {goal}\n"
            f"STEP: {step_no}\n"
            f"PREVIOUS STEPS:\n{history_summary or '  (none)'}\n"
            f"{recovery_hint}\n"
            f"DESKTOP & ACCESSIBILITY STATE:\n{ui_ctx or '  (none)'}\n\n"
            "You are operating the user's KDE Plasma 6 Wayland desktop. Decide the "
            "SINGLE next action to take to make progress toward the goal.\n"
            "Reply with exactly one line in this format:\n"
            "  ACTION: <action_call>\n"
            "or if the goal has been achieved:\n"
            "  DONE: <brief summary of what was accomplished>\n\n"
            "Available actions (prefer accessibility, app launch, and window/keyboard tools over coordinates):\n"
            "  kwin_element_act(query, Press) — invoke AT-SPI2 UI element by accessible name (PREFERRED)\n"
            "  kwin_element_query(query) — search accessible UI elements matching query\n"
            "  kwin_launch_app(command) — launch an application (e.g. kwin_launch_app(firefox))\n"
            "  kwin_focus_window(title) — bring a window to front by title or app name\n"
            "  kwin_list_windows() — list open windows\n"
            "  kwin_close_window(app_name) — close an application window\n"
            "  kwin_type(text) — type text at keyboard focus\n"
            "  kwin_press(key) — press one key (e.g. Return, Escape, Tab)\n"
            "  kwin_hotkey(keys) — chord like 'ctrl+c', 'ctrl+l', 'alt+F4'\n"
            "  kwin_clipboard_write(text) — copy text to clipboard\n"
            "  kwin_clipboard_read() — read clipboard text\n"
            "  kwin_click(x,y) — fallback: left-click at screen coordinates\n"
            "  kwin_double_click(x,y) — fallback: double-click at coordinates\n"
            "  kwin_right_click(x,y) — fallback: right-click at coordinates\n"
            "  kwin_move_mouse(x,y) — move pointer to coordinates\n"
            "  kwin_scroll(x,y,direction) — scroll up/down/left/right at (x,y)\n"
            "  kwin_drag(x1,y1,x2,y2) — drag from (x1,y1) to (x2,y2)\n"
            "  kwin_screenshot() — re-capture the screen\n"
        )

        text = ""
        # 1. Try local/configured model router first if available
        try:
            from core.model_router import get_router
            router = get_router()
            routed = await asyncio.to_thread(
                router.generate,
                role="vision",
                prompt=prompt,
                image_bytes=cap.image_bytes,
            )
            if routed:
                text = routed.strip()
        except Exception:
            pass

        # 2. Fallback to Gemini VLM
        if not text:
            try:
                from google.genai import types
                contents = [
                    types.Part.from_bytes(data=cap.image_bytes, mime_type="image/png"),
                    prompt,
                ]
                reply = await asyncio.to_thread(
                    _gemini.call,
                    contents,
                    tier=_gemini.SMART,
                    timeout_ms=30_000,
                )
                if reply is not None:
                    text = (getattr(reply, "text", None) or "").strip()
            except Exception as e:
                self._log(f"[DesktopAgent] planning failed: {e}")
                return None

        if not text:
            return None

        for line in text.splitlines():
            line = line.strip()
            if line.upper().startswith("ACTION:"):
                return line[len("ACTION:"):].strip()
            if line.upper().startswith("DONE:"):
                return "DONE: " + line[len("DONE:"):].strip()

        return text

    # ── acting ───────────────────────────────────────────────────────────

    async def _act(self, plan: str) -> str:
        """Execute a planned action via kwin-mcp."""
        plan = plan.strip()

        # kwin_element_act(query, action) or kwin_element_act(query)
        m = re.match(r"kwin_element_act\((.+)\)", plan)
        if m:
            inner = m.group(1).strip()
            parts = [p.strip().strip('"').strip("'") for p in inner.rsplit(",", 1)]
            query = parts[0]
            act_name = parts[1] if len(parts) > 1 else "Press"
            return await asyncio.to_thread(self._kwin_element_act, query, act_name)

        # kwin_element_query(query)
        m = re.match(r"kwin_element_query\((.+)\)", plan)
        if m:
            query = m.group(1).strip().strip('"').strip("'")
            return await asyncio.to_thread(self._kwin_element_query, query)

        # kwin_launch_app(command)
        m = re.match(r"kwin_launch_app\((.+)\)", plan)
        if m:
            cmd = m.group(1).strip().strip('"').strip("'")
            return await asyncio.to_thread(self._kwin_launch_app, cmd)

        # kwin_clipboard_write(text)
        m = re.match(r"kwin_clipboard_write\((.+)\)", plan, re.DOTALL)
        if m:
            txt = m.group(1).strip().strip('"').strip("'")
            return await asyncio.to_thread(self._kwin_clipboard_write, txt)

        # kwin_clipboard_read()
        if plan.startswith("kwin_clipboard_read"):
            return await asyncio.to_thread(self._kwin_clipboard_read)

        # kwin_type(text)
        m = re.match(r"kwin_type\((.+)\)", plan, re.DOTALL)
        if m:
            text = m.group(1).strip().strip('"').strip("'")
            return await asyncio.to_thread(self._kwin_type, text)

        # kwin_press(key)
        m = re.match(r"kwin_press\(([^)]+)\)", plan)
        if m:
            key = m.group(1).strip().strip('"').strip("'")
            return await asyncio.to_thread(self._kwin_press, key)

        # kwin_hotkey(keys)
        m = re.match(r"kwin_hotkey\((.+)\)", plan)
        if m:
            keys = m.group(1).strip().strip('"').strip("'")
            return await asyncio.to_thread(self._kwin_hotkey, keys)

        # kwin_click(x, y)
        m = re.match(r"kwin_click\((-?\d+)\s*,\s*(-?\d+)\)", plan)
        if m:
            return await asyncio.to_thread(
                self._kwin_click, int(m.group(1)), int(m.group(2))
            )

        # kwin_double_click(x, y)
        m = re.match(r"kwin_double_click\((-?\d+)\s*,\s*(-?\d+)\)", plan)
        if m:
            return await asyncio.to_thread(
                self._kwin_double_click, int(m.group(1)), int(m.group(2))
            )

        # kwin_right_click(x, y)
        m = re.match(r"kwin_right_click\((-?\d+)\s*,\s*(-?\d+)\)", plan)
        if m:
            return await asyncio.to_thread(
                self._kwin_right_click, int(m.group(1)), int(m.group(2))
            )

        # kwin_move_mouse(x, y)
        m = re.match(r"kwin_move_mouse\((-?\d+)\s*,\s*(-?\d+)\)", plan)
        if m:
            return await asyncio.to_thread(
                self._kwin_move_mouse, int(m.group(1)), int(m.group(2))
            )

        # kwin_scroll(x, y, direction)
        m = re.match(r"kwin_scroll\((-?\d+)\s*,\s*(-?\d+)\s*,\s*(\w+)\)", plan)
        if m:
            return await asyncio.to_thread(
                self._kwin_scroll, int(m.group(1)), int(m.group(2)), m.group(3)
            )

        # kwin_drag(x1, y1, x2, y2)
        m = re.match(r"kwin_drag\((-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\)", plan)
        if m:
            return await asyncio.to_thread(
                self._kwin_drag,
                int(m.group(1)), int(m.group(2)),
                int(m.group(3)), int(m.group(4)),
            )

        # kwin_screenshot()
        if plan.startswith("kwin_screenshot"):
            return await asyncio.to_thread(self._kwin_screenshot)

        # kwin_focus_window(title)
        m = re.match(r"kwin_focus_window\((.+)\)", plan)
        if m:
            title = m.group(1).strip().strip('"').strip("'")
            return await asyncio.to_thread(self._kwin_focus_window, title)

        # kwin_list_windows()
        if plan.startswith("kwin_list_windows"):
            return await asyncio.to_thread(self._kwin_list_windows)

        # kwin_close_window(app_name)
        m = re.match(r"kwin_close_window\((.+)\)", plan)
        if m:
            app = m.group(1).strip().strip('"').strip("'")
            return await asyncio.to_thread(self._kwin_close_window, app)

        # kwin_dismiss_popup()
        if plan.startswith("kwin_dismiss_popup"):
            return await asyncio.to_thread(self._kwin_press, "Escape")

        return f"unrecognized action: {plan}"

    def get_active_window_summary(self) -> dict[str, Any]:
        """Return structured summary of the currently active window and open windows."""
        try:
            client = self._get_client()
            windows = client.get_kwin_windows()
            active = next((w for w in windows if w.get("active")), None)
            return {
                "active_window": active,
                "window_count": len(windows),
                "windows": windows,
            }
        except Exception as exc:
            return {"active_window": None, "window_count": 0, "error": str(exc), "windows": []}

    # ── kwin-mcp wrappers (v0.12.0 methods) ────────────────────────────

    def _get_client(self):
        from core.kwin_mcp_client import get_client, available as kwin_available
        if not kwin_available():
            raise RuntimeError("kwin-mcp is not installed")
        client = get_client(log=self._log)
        client.ensure_started()
        return client

    def _kwin_element_act(self, query: str, action_name: str = "Press") -> str:
        from actions.kwin_desktop import _kwin_element_act
        return _kwin_element_act(query, action=action_name)

    def _kwin_element_query(self, query: str) -> str:
        from actions.kwin_desktop import _kwin_element_query
        return _kwin_element_query(query)

    def _kwin_launch_app(self, command: str) -> str:
        client = self._get_client()
        result = client.launch_app(command)
        return str(result)

    def _kwin_clipboard_write(self, text: str) -> str:
        client = self._get_client()
        result = client.clipboard_set(text)
        return str(result)

    def _kwin_clipboard_read(self) -> str:
        client = self._get_client()
        result = client.clipboard_get()
        return str(result)

    def _kwin_type(self, text: str) -> str:
        client = self._get_client()
        result = client.keyboard_type(text, method="unicode")
        return str(result)

    def _kwin_press(self, keys: str) -> str:
        client = self._get_client()
        result = client.keyboard_key(_normalize_key(keys))
        return str(result)

    def _kwin_hotkey(self, keys: str) -> str:
        client = self._get_client()
        result = client.keyboard_key(_normalize_key(keys))
        return str(result)

    def _kwin_click(self, x: int, y: int) -> str:
        client = self._get_client()
        result = client.mouse_click(int(x), int(y), button="left", count=1)
        return str(result)

    def _kwin_double_click(self, x: int, y: int) -> str:
        client = self._get_client()
        result = client.mouse_click(int(x), int(y), button="left", count=2, double=True)
        return str(result)

    def _kwin_right_click(self, x: int, y: int) -> str:
        client = self._get_client()
        result = client.mouse_click(int(x), int(y), button="right", count=1)
        return str(result)

    def _kwin_move_mouse(self, x: int, y: int) -> str:
        client = self._get_client()
        result = client.mouse_move(int(x), int(y))
        return str(result)

    def _kwin_scroll(self, x: int, y: int, direction: str) -> str:
        client = self._get_client()
        delta = 3 if direction in ("up", "right") else -3
        horizontal = direction in ("left", "right")
        result = client.mouse_scroll(int(x), int(y), delta=delta, horizontal=horizontal)
        return str(result)

    def _kwin_drag(self, x1: int, y1: int, x2: int, y2: int) -> str:
        client = self._get_client()
        result = client.mouse_drag(int(x1), int(y1), int(x2), int(y2))
        return str(result)

    def _kwin_screenshot(self) -> str:
        client = self._get_client()
        result = client.screenshot()
        return str(result)

    def _kwin_focus_window(self, title: str) -> str:
        client = self._get_client()
        windows = client.get_kwin_windows()
        matches = self._match_windows(windows, title)
        if matches:
            result = client.focus_window(window_id=matches[0]["id"])
            return str(result)
        result = client.focus_window(app_name=title)
        return str(result)

    def _kwin_list_windows(self) -> str:
        client = self._get_client()
        windows = client.get_kwin_windows()
        if not windows:
            return "No windows."
        lines = []
        for w in windows:
            lines.append(
                f"id={w.get('id')} app={w.get('app', '')} "
                f"caption={w.get('caption', '')} active={w.get('active', False)}"
            )
        return "\n".join(lines)

    def _kwin_close_window(self, app_name: str) -> str:
        client = self._get_client()
        windows = client.get_kwin_windows()
        matches = self._match_windows(windows, app_name)
        if not matches:
            return f"no window matches '{app_name}'"
        result = client.window_close(matches[0]["id"])
        return str(result)

    def _match_windows(self, windows: Any, name: str) -> list[dict[str, Any]]:
        if not isinstance(windows, list):
            return []
        name_l = name.lower()
        out = []
        for w in windows:
            if not isinstance(w, dict):
                continue
            caption = str(w.get("caption", "")).lower()
            app_id = str(w.get("app_id") or w.get("app") or "").lower()
            if name_l in caption or name_l in app_id:
                out.append(w)
        return out


# ── module-level singleton ─────────────────────────────────────────────

_desktop_agent: Optional[DesktopAgent] = None
_desktop_agent_lock = threading.Lock()


def get_desktop_agent(log=None) -> DesktopAgent:
    """Return the singleton DesktopAgent instance."""
    global _desktop_agent
    with _desktop_agent_lock:
        if _desktop_agent is None:
            _desktop_agent = DesktopAgent(log=log)
        elif log is not None:
            _desktop_agent._log = log
    return _desktop_agent


def reset_desktop_agent() -> None:
    """Drop the singleton (mainly for tests)."""
    global _desktop_agent
    with _desktop_agent_lock:
        _desktop_agent = None
