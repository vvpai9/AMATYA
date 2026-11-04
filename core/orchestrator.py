"""
AMATYA Central Intelligence, Context Resolver & Multi-Task Orchestrator (core/orchestrator.py)
==============================================================================================
Implements Section 2 (Natural Intelligence, Contextual Reference Resolution,
Multi-Step Instructions, Background Task Execution, and Task Prioritization):

Contextual References Resolved:
  - "Open that."                  → resolves to last_file, last_url, or last_project
  - "Close the previous window."  → resolves to previous_window_id / previous_window_title
  - "Continue what you were doing." → resumes last interrupted/paused task or workflow
  - "Check the same project again." → resolves to last_project and runs git/test audit
  - "Send that file to my phone." → resolves last_file + primary Android phone device
"""
from __future__ import annotations

import json
import re
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from core.model_router import get_router
from memory.config_manager import BASE_DIR

CONTEXT_STATE_PATH = BASE_DIR / "memory" / "context_state.json"
_LOCK = threading.RLock()


@dataclass
class TaskRecord:
    task_id: str
    goal: str
    resolved_goal: str
    domain: str
    priority: int = 5  # 1 (highest) to 10 (lowest)
    status: str = "pending"  # pending | running | paused | completed | failed | cancelled
    steps: list[dict[str, Any]] = field(default_factory=list)
    current_step_index: int = 0
    result_summary: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ContextTracker:
    """Tracks conversational and operational entities across turns so pronouns and
    elliptical commands ('Open that', 'Close the previous window', 'Check the same
    project again', 'Send that file to my phone', 'Continue what you were doing')
    resolve deterministically."""

    def __init__(self, state_path: Path | None = None) -> None:
        self._path = state_path or CONTEXT_STATE_PATH
        self._state: dict[str, Any] = {
            "last_file": "",
            "last_project": str(BASE_DIR),
            "last_app": "",
            "current_window_id": "",
            "current_window_title": "",
            "previous_window_id": "",
            "previous_window_title": "",
            "last_device": "phone",
            "last_url": "",
            "last_entity": "",
            "last_tool": "",
            "last_task": None,
            "updated_at": 0.0,
        }
        self._load()

    def _load(self) -> None:
        with _LOCK:
            if self._path.exists():
                try:
                    data = json.loads(self._path.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        self._state.update(data)
                except Exception:
                    pass

    def _save(self) -> None:
        with _LOCK:
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                self._state["updated_at"] = time.time()
                self._path.write_text(
                    json.dumps(self._state, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            except Exception:
                pass

    def get_state(self) -> dict[str, Any]:
        with _LOCK:
            return dict(self._state)

    def update_entity(self, **kwargs: Any) -> dict[str, Any]:
        with _LOCK:
            if "window_id" in kwargs or "window_title" in kwargs:
                new_wid = str(kwargs.pop("window_id", "") or "")
                new_wtitle = str(kwargs.pop("window_title", "") or "")
                if new_wid and new_wid != self._state.get("current_window_id"):
                    self._state["previous_window_id"] = self._state.get("current_window_id", "")
                    self._state["previous_window_title"] = self._state.get("current_window_title", "")
                    self._state["current_window_id"] = new_wid
                    self._state["current_window_title"] = new_wtitle
                elif new_wtitle and new_wtitle != self._state.get("current_window_title"):
                    self._state["previous_window_title"] = self._state.get("current_window_title", "")
                    self._state["current_window_title"] = new_wtitle

            for k, v in kwargs.items():
                if v is not None and v != "":
                    self._state[k] = v
                    if k in ("last_file", "last_url", "last_project", "last_app"):
                        self._state["last_entity"] = v
            self._save()
            return dict(self._state)

    def record_tool_call(self, tool_name: str, args: dict[str, Any]) -> None:
        """Automatically extract context entities from any executed tool call."""
        updates: dict[str, Any] = {"last_tool": tool_name}
        if not isinstance(args, dict):
            self.update_entity(**updates)
            return

        for fkey in ("file_path", "path", "source_path", "output_path", "target_path"):
            val = args.get(fkey)
            if isinstance(val, str) and val.strip():
                p = Path(val.strip()).expanduser()
                if p.suffix:
                    updates["last_file"] = str(p)
                else:
                    updates["last_project"] = str(p)

        if args.get("project_path") or args.get("repo_path"):
            updates["last_project"] = str(args.get("project_path") or args.get("repo_path"))

        if args.get("app_name") or args.get("app"):
            updates["last_app"] = str(args.get("app_name") or args.get("app"))

        if args.get("url"):
            updates["last_url"] = str(args["url"])

        if args.get("device_id") or args.get("device"):
            updates["last_device"] = str(args.get("device_id") or args.get("device"))

        if args.get("window_id") or args.get("title"):
            updates["window_id"] = str(args.get("window_id", ""))
            updates["window_title"] = str(args.get("title", ""))

        self.update_entity(**updates)

    def resolve_references(self, instruction: str) -> dict[str, Any]:
        """Resolve contextual references in a user instruction using tracked state."""
        text = (instruction or "").strip()
        lower = text.lower()
        st = self.get_state()
        resolutions: dict[str, Any] = {}
        resolved_text = text
        recommended_action: dict[str, Any] | None = None

        # 1. "Send that file to my phone" / "transfer that file to my phone"
        if re.search(r"\b(send|share|transfer|push)\s+(that|this|the)\s+(file|document|pdf|image|report)\b", lower):
            target_file = st.get("last_file") or st.get("last_entity") or ""
            target_device = st.get("last_device") or "phone"
            resolutions["file_path"] = target_file
            resolutions["device"] = target_device
            if target_file:
                resolved_text = f"Send file '{target_file}' to device '{target_device}'."
                recommended_action = {
                    "tool": "device_control",
                    "parameters": {
                        "action": "send_file",
                        "device": target_device,
                        "file_path": target_file,
                    },
                }

        # 2. "Check the same project again" / "test that project again"
        elif re.search(r"\b(check|test|inspect|compile|build|audit)\s+(the\s+same|that|this)\s+(project|repo|repository)\b", lower):
            proj = st.get("last_project") or str(BASE_DIR)
            resolutions["project_path"] = proj
            resolved_text = f"Inspect repository status and run tests in project '{proj}'."
            recommended_action = {
                "tool": "creator",
                "parameters": {
                    "action": "check_project",
                    "project_path": proj,
                },
            }

        # 3. "Close the previous window" / "switch to the previous window"
        elif re.search(r"\b(close|focus|switch\s+to)\s+(the\s+)?(previous|last|prior)\s+window\b", lower):
            verb = "close_window" if "close" in lower else "focus_window"
            prev_id = st.get("previous_window_id") or st.get("current_window_id") or ""
            prev_title = st.get("previous_window_title") or st.get("current_window_title") or ""
            resolutions["window_id"] = prev_id
            resolutions["window_title"] = prev_title
            target_desc = prev_title or prev_id or "previous window"
            resolved_text = f"{'Close' if verb == 'close_window' else 'Focus'} window '{target_desc}' (id={prev_id})."
            recommended_action = {
                "tool": "kwin_desktop",
                "parameters": {
                    "action": verb,
                    "window_id": prev_id,
                    "title": prev_title,
                },
            }

        # 4. "Continue what you were doing" / "resume the task"
        elif re.search(r"\b(continue|resume)\s+(what\s+you\s+were\s+doing|the\s+task|previous\s+task|that\s+task)\b", lower):
            last_task = st.get("last_task")
            resolutions["last_task"] = last_task
            if isinstance(last_task, dict) and last_task.get("goal"):
                resolved_text = f"Resume task '{last_task.get('goal')}' from step {last_task.get('current_step_index', 0) + 1}."
                recommended_action = {
                    "tool": "orchestrator",
                    "parameters": {
                        "action": "resume_last_task",
                    },
                }

        # 5. "Open that" / "open it"
        elif re.search(r"^\s*open\s+(that|it|this)(\s+file|\s+project|\s+folder|\s+link|\s+url)?\s*[\.!\?]?\s*$", lower):
            target = st.get("last_file") or st.get("last_url") or st.get("last_project") or st.get("last_app") or ""
            resolutions["target"] = target
            if target:
                resolved_text = f"Open '{target}'."
                recommended_action = {
                    "tool": "open_app",
                    "parameters": {"app_name": target},
                }

        return {
            "original": text,
            "resolved": resolved_text,
            "resolutions": resolutions,
            "recommended_action": recommended_action,
            "context_snapshot": {
                "last_file": st.get("last_file"),
                "last_project": st.get("last_project"),
                "last_app": st.get("last_app"),
                "previous_window_id": st.get("previous_window_id"),
                "previous_window_title": st.get("previous_window_title"),
                "last_device": st.get("last_device"),
            },
        }


class CentralOrchestrator:
    """Decomposes, prioritizes, executes, and tracks multi-step cross-domain tasks."""

    def __init__(self) -> None:
        self.context = ContextTracker()
        self._tasks: dict[str, TaskRecord] = {}
        self._cancel_requested = threading.Event()

    def classify_domain(self, instruction: str) -> str:
        lower = (instruction or "").lower()
        if any(w in lower for w in ("leaving home", "morning routine", "evening routine", "sleep routine", "lights", "thermostat", "fan", "home assistant", "lock the door")):
            return "home_automation"
        if any(w in lower for w in ("my phone", "android", "tv", "redmi", "kde connect", "adb", "network devices", "tailscale", "ssh")):
            return "connected_devices"
        if any(w in lower for w in ("project", "repository", "git", "compile", "pytest", "unit test", "broken anything", "refactor", "code", "bug")):
            return "software_engineering"
        if any(w in lower for w in ("desktop", "window", "screen", "click", "type", "browser", "dialog")):
            return "desktop_automation"
        if any(w in lower for w in ("pdf", "docx", "xlsx", "pptx", "spreadsheet", "presentation", "report")):
            return "document_processing"
        return "general"

    def plan_workflow(self, instruction: str, priority: int = 5) -> TaskRecord:
        """Resolve references in `instruction` and build an executable multi-step plan."""
        ref = self.context.resolve_references(instruction)
        resolved_goal = ref["resolved"]
        domain = self.classify_domain(resolved_goal)
        lower = resolved_goal.lower()

        steps: list[dict[str, Any]] = []
        if ref.get("recommended_action"):
            act = ref["recommended_action"]
            steps.append({
                "step": 1,
                "description": resolved_goal,
                "tool": act["tool"],
                "parameters": act["parameters"],
                "status": "pending",
            })
        elif domain == "software_engineering":
            proj = self.context.get_state().get("last_project") or str(BASE_DIR)
            steps = [
                {
                    "step": 1,
                    "description": f"Inspect repository status and recent changes in {proj}",
                    "tool": "creator",
                    "parameters": {"action": "git_status", "project_path": proj},
                    "status": "pending",
                },
                {
                    "step": 2,
                    "description": f"Run test suite and verify build health in {proj}",
                    "tool": "creator",
                    "parameters": {"action": "run_tests", "project_path": proj},
                    "status": "pending",
                },
            ]
        elif domain == "home_automation":
            routine_match = None
            for rname in ("leaving_home", "returning_home", "morning", "evening", "sleep"):
                if rname.replace("_", " ") in lower or rname in lower:
                    routine_match = rname
                    break
            if routine_match:
                steps = [
                    {
                        "step": 1,
                        "description": f"Execute home automation routine '{routine_match}'",
                        "tool": "home_automation",
                        "parameters": {"action": "run_routine", "routine_name": routine_match},
                        "status": "pending",
                    }
                ]
            else:
                steps = [
                    {
                        "step": 1,
                        "description": f"Check home automation state for: {resolved_goal}",
                        "tool": "home_automation",
                        "parameters": {"action": "status"},
                        "status": "pending",
                    }
                ]
        elif domain == "desktop_automation":
            steps = [
                {
                    "step": 1,
                    "description": "Observe open Wayland windows and active application state",
                    "tool": "kwin_desktop",
                    "parameters": {"action": "list_windows"},
                    "status": "pending",
                },
                {
                    "step": 2,
                    "description": f"Execute desktop objective: {resolved_goal}",
                    "tool": "desktop_agent",
                    "parameters": {"action": "start", "goal": resolved_goal},
                    "status": "pending",
                },
            ]
        else:
            steps = [
                {
                    "step": 1,
                    "description": resolved_goal,
                    "tool": "reasoning",
                    "parameters": {"prompt": resolved_goal},
                    "status": "pending",
                }
            ]

        task = TaskRecord(
            task_id=uuid.uuid4().hex[:10],
            goal=instruction,
            resolved_goal=resolved_goal,
            domain=domain,
            priority=max(1, min(10, int(priority))),
            status="pending",
            steps=steps,
        )
        with _LOCK:
            self._tasks[task.task_id] = task
            self.context.update_entity(last_task=task.to_dict())
        return task

    def execute_task(
        self,
        task: TaskRecord,
        action_runner: Callable[[str, dict[str, Any]], Any] | None = None,
    ) -> TaskRecord:
        """Execute a planned TaskRecord step-by-step with cancellation support."""
        self._cancel_requested.clear()
        task.status = "running"
        task.updated_at = time.time()
        summaries: list[str] = []

        for idx in range(task.current_step_index, len(task.steps)):
            if self._cancel_requested.is_set():
                task.status = "paused"
                task.current_step_index = idx
                task.result_summary = "Task paused/cancelled by user."
                self.context.update_entity(last_task=task.to_dict())
                return task

            step = task.steps[idx]
            step["status"] = "running"
            task.current_step_index = idx
            tool_name = step.get("tool", "")
            params = step.get("parameters", {})

            try:
                if action_runner and tool_name != "reasoning":
                    res = action_runner(tool_name, params)
                    res_str = str(res)
                elif tool_name == "reasoning":
                    res_str = get_router().generate("reasoning", params.get("prompt", task.resolved_goal))
                else:
                    # Direct action module dispatch
                    mod = __import__(f"actions.{tool_name}", fromlist=["execute"])
                    res = mod.execute(params)
                    res_str = str(res)

                step["status"] = "completed"
                step["result"] = res_str[:500]
                summaries.append(f"Step {idx + 1} ({tool_name}): {res_str[:240]}")
                self.context.record_tool_call(tool_name, params)
            except Exception as exc:
                step["status"] = "failed"
                step["error"] = str(exc)
                task.status = "failed"
                task.result_summary = f"Step {idx + 1} ({tool_name}) failed: {exc}"
                self.context.update_entity(last_task=task.to_dict())
                return task

        task.status = "completed"
        task.current_step_index = len(task.steps)
        task.result_summary = " | ".join(summaries) if summaries else "Completed."
        task.updated_at = time.time()
        self.context.update_entity(last_task=task.to_dict())
        return task

    def cancel_all(self) -> str:
        """Emergency Stop: cancel running orchestrator tasks and DesktopAgent."""
        self._cancel_requested.set()
        cancelled = 0
        with _LOCK:
            for t in self._tasks.values():
                if t.status in ("running", "pending"):
                    t.status = "paused"
                    cancelled += 1
                    self.context.update_entity(last_task=t.to_dict())
        try:
            from core.desktop_agent import get_desktop_agent
            da = get_desktop_agent()
            if da is not None and da.is_running:
                da.cancel()
        except Exception:
            pass
        return f"Emergency Stop triggered: paused/cancelled {cancelled} active orchestrator task(s) and stopped DesktopAgent."

    def list_tasks(self) -> list[dict[str, Any]]:
        with _LOCK:
            ordered = sorted(
                self._tasks.values(),
                key=lambda t: (t.priority, -t.created_at),
            )
            return [t.to_dict() for t in ordered]


_ORCHESTRATOR: CentralOrchestrator | None = None


def get_orchestrator() -> CentralOrchestrator:
    global _ORCHESTRATOR
    if _ORCHESTRATOR is None:
        _ORCHESTRATOR = CentralOrchestrator()
    return _ORCHESTRATOR
