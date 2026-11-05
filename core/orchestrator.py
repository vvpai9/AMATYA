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

import hashlib
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
ACTIVE_TASKS_PATH = BASE_DIR / "memory" / "active_tasks.json"
_LOCK = threading.RLock()


class LoopDetectedError(RuntimeError):
    """Raised when an orchestrator task repeats identical failing states without progress."""
    pass


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
    step_results: list[Any] = field(default_factory=list)
    result_summary: str = ""
    retry_counts: dict[str, int] = field(default_factory=dict)
    state_history: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def progress_pct(self) -> int:
        if not self.steps:
            return 100 if self.status == "completed" else 0
        return int((self.current_step_index / len(self.steps)) * 100)


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


def _extract_file_path(val: Any) -> str:
    """Extract a valid file path string from arbitrary tool return values."""
    if not val:
        return ""
    if isinstance(val, dict):
        for k in ("file_path", "output_path", "path", "target_path"):
            cand = val.get(k)
            if isinstance(cand, str) and cand.strip():
                return cand.strip()
    if isinstance(val, str):
        # Match explicit paths like /home/... or ./... or *.pdf/*.pptx/*.md
        m = re.search(r"(/[\w\.\-]+(?:/[\w\.\-]+)+|\./[\w\.\-]+|\b[\w\-]+\.(?:pdf|pptx|docx|xlsx|md|py|json|txt)\b)", val)
        if m:
            return m.group(1).strip()
    return ""


def _extract_summary_text(val: Any) -> str:
    """Extract summary/content text from tool return values."""
    if not val:
        return ""
    if isinstance(val, dict):
        for k in ("summary", "content", "result", "text", "message"):
            cand = val.get(k)
            if isinstance(cand, str) and cand.strip():
                return cand.strip()
    return str(val).strip()


def resolve_bridged_parameters(
    params: dict[str, Any],
    step_results: list[Any],
    context_state: dict[str, Any],
) -> dict[str, Any]:
    """Dynamically bridge parameters across multi-step plans using outputs from earlier steps."""
    resolved = dict(params)
    prev_result = step_results[-1] if step_results else None

    for k, v in list(resolved.items()):
        if isinstance(v, str):
            v_str = v.strip()
            # 1. $prev.file_path or $prev.output_path
            if v_str in ("$prev.file_path", "$prev.output_path", "$prev.path"):
                fp = _extract_file_path(prev_result) or context_state.get("last_file", "")
                resolved[k] = fp
            # 2. $prev.summary or $prev.content
            elif v_str in ("$prev.summary", "$prev.content", "$prev.text"):
                sum_text = _extract_summary_text(prev_result)
                resolved[k] = sum_text or "Automated summary."
            # 3. $prev
            elif v_str == "$prev":
                resolved[k] = prev_result
            # 4. $step_N.<key>
            elif v_str.startswith("$step_"):
                m = re.match(r"^\$step_(\d+)(?:\.([a-zA-Z_0-9]+))?$", v_str)
                if m:
                    idx = int(m.group(1)) - 1
                    prop = m.group(2)
                    if 0 <= idx < len(step_results):
                        sres = step_results[idx]
                        if not prop:
                            resolved[k] = sres
                        elif prop in ("file_path", "output_path", "path"):
                            resolved[k] = _extract_file_path(sres)
                        elif prop in ("summary", "content", "text"):
                            resolved[k] = _extract_summary_text(sres)
                        elif isinstance(sres, dict) and prop in sres:
                            resolved[k] = sres[prop]

    # Automatic fallback for device parameter
    if "device" in resolved and resolved["device"] in ("$prev.device", "", None):
        resolved["device"] = context_state.get("last_device") or "phone"

    # Automatic fallback if file_path is requested but still contains placeholder
    if "file_path" in resolved and str(resolved["file_path"]).startswith("$prev"):
        resolved["file_path"] = _extract_file_path(prev_result) or context_state.get("last_file", "")

    return resolved


class CentralOrchestrator:
    """Hierarchical Task Planner, Context Resolver & Multi-Step Orchestrator for AMATYA."""

    def __init__(self) -> None:
        self.context = ContextTracker()
        self._tasks: dict[str, TaskRecord] = {}
        self._active_tasks_path = ACTIVE_TASKS_PATH
        self._cancel_requested = threading.Event()
        self._load_active_tasks()

    def _load_active_tasks(self) -> None:
        with _LOCK:
            if not self._active_tasks_path.exists():
                return
            try:
                data = json.loads(self._active_tasks_path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get("task_id"):
                            tr = TaskRecord(**{k: v for k, v in item.items() if k in TaskRecord.__dataclass_fields__})
                            self._tasks[tr.task_id] = tr
            except Exception:
                pass

    def _save_active_tasks(self) -> None:
        with _LOCK:
            try:
                self._active_tasks_path.parent.mkdir(parents=True, exist_ok=True)
                serialized = [t.to_dict() for t in self._tasks.values()]
                self._active_tasks_path.write_text(
                    json.dumps(serialized, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            except Exception:
                pass

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
        if any(w in lower for w in ("pdf", "docx", "xlsx", "pptx", "spreadsheet", "presentation", "report", "summarize it")):
            return "document_processing"
        return "general"

    def plan_workflow(self, instruction: str, priority: int = 5) -> TaskRecord:
        """Resolve references and decompose compound multi-subsystem goals into structured tasks."""
        ref = self.context.resolve_references(instruction)
        resolved_goal = ref["resolved"]
        domain = self.classify_domain(resolved_goal)
        lower = resolved_goal.lower()

        steps: list[dict[str, Any]] = []

        # ── 1. Compound Multi-Subsystem Workflow: Document Pipeline ───────────
        # "find the latest PDF in my project directory, summarize it, create a presentation from it and send the presentation to my phone"
        is_doc_pipeline = (
            ("pdf" in lower or "document" in lower or "file" in lower)
            and ("summarize" in lower or "analyze" in lower)
            and ("presentation" in lower or "pptx" in lower or "slides" in lower or "report" in lower)
            and ("phone" in lower or "device" in lower or "send" in lower)
        )
        if is_doc_pipeline:
            domain = "document_processing"
            target_ext = ".pdf" if "pdf" in lower else (".docx" if "docx" in lower else "")
            target_format = "pptx" if ("presentation" in lower or "pptx" in lower or "slides" in lower) else "pdf"
            proj = self.context.get_state().get("last_project") or str(BASE_DIR)
            out_name = f"summary_presentation.{target_format}"

            steps = [
                {
                    "step": 1,
                    "description": f"Find latest {target_ext or 'document'} in project directory ({proj})",
                    "tool": "file_controller",
                    "parameters": {"action": "latest_file", "path": proj, "extension": target_ext},
                    "status": "pending",
                },
                {
                    "step": 2,
                    "description": "Extract content and generate structured summary of the document",
                    "tool": "creator",
                    "parameters": {"action": "analyze_doc", "file_path": "$prev.file_path"},
                    "status": "pending",
                },
                {
                    "step": 3,
                    "description": f"Create {target_format.upper()} presentation document from summary",
                    "tool": "creator",
                    "parameters": {
                        "action": "generate_doc",
                        "output_path": out_name,
                        "title": "Document Summary Presentation",
                        "content": "$prev.summary",
                    },
                    "status": "pending",
                },
                {
                    "step": 4,
                    "description": f"Transmit generated {target_format.upper()} presentation to authorized phone",
                    "tool": "device_control",
                    "parameters": {
                        "action": "send_file",
                        "device": "phone",
                        "file_path": "$prev.output_path",
                    },
                    "status": "pending",
                },
            ]

        # ── 2. Contextual Single-Action Shortcut ─────────────────────────────
        elif ref.get("recommended_action"):
            act = ref["recommended_action"]
            steps.append({
                "step": 1,
                "description": resolved_goal,
                "tool": act["tool"],
                "parameters": act["parameters"],
                "status": "pending",
            })

        # ── 3. Software Engineering Audit ─────────────────────────────────────
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

        # ── 4. Home Automation ────────────────────────────────────────────────
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

        # ── 5. Desktop Automation ─────────────────────────────────────────────
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

        # ── 6. Default / General Reasoning ───────────────────────────────────
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
            self._save_active_tasks()
        return task

    def execute_task(
        self,
        task: TaskRecord,
        action_runner: Callable[[str, dict[str, Any]], Any] | None = None,
    ) -> TaskRecord:
        """Execute a planned TaskRecord step-by-step with parameter bridging and loop prevention."""
        self._cancel_requested.clear()
        task.status = "running"
        task.updated_at = time.time()
        summaries: list[str] = []

        context_state = self.context.get_state()

        for idx in range(task.current_step_index, len(task.steps)):
            if self._cancel_requested.is_set():
                task.status = "paused"
                task.current_step_index = idx
                task.result_summary = "Task paused/cancelled by user."
                self.context.update_entity(last_task=task.to_dict())
                self._save_active_tasks()
                return task

            step = task.steps[idx]
            step["status"] = "running"
            task.current_step_index = idx
            tool_name = step.get("tool", "")
            raw_params = step.get("parameters", {})

            # ── Dynamic Parameter Bridging across steps ───────────────────────
            params = resolve_bridged_parameters(raw_params, task.step_results, context_state)
            step["resolved_parameters"] = params

            # ── Loop Prevention & Cycle Detection ─────────────────────────────
            param_key = tuple(sorted((k, str(v)) for k, v in params.items()))
            state_sig = hashlib.sha256(f"{tool_name}:{param_key}".encode("utf-8")).hexdigest()[:12]
            if task.state_history.count(state_sig) >= 2:
                step["status"] = "failed"
                step["error"] = "Loop detected: step repeated without state transition."
                task.status = "failed"
                task.result_summary = f"Loop detected at step {idx + 1} ({tool_name})."
                self.context.update_entity(last_task=task.to_dict())
                self._save_active_tasks()
                raise LoopDetectedError(task.result_summary)
            task.state_history.append(state_sig)

            try:
                res_obj: Any = None
                if action_runner and tool_name != "reasoning":
                    res_obj = action_runner(tool_name, params)
                    res_str = str(res_obj)
                elif tool_name == "reasoning":
                    res_str = get_router().generate("reasoning", params.get("prompt", task.resolved_goal))
                    res_obj = {"result": res_str}
                else:
                    # Direct action module dispatch
                    mod = __import__(f"actions.{tool_name}", fromlist=["execute"])
                    res_obj = mod.execute(params)
                    res_str = str(res_obj)

                step["status"] = "completed"
                step["result"] = res_str[:500]
                task.step_results.append(res_obj)
                summaries.append(f"Step {idx + 1} ({tool_name}): {res_str[:200]}")
                self.context.record_tool_call(tool_name, params)
                self._save_active_tasks()
            except Exception as exc:
                step["status"] = "failed"
                step["error"] = str(exc)
                task.status = "failed"
                task.result_summary = f"Step {idx + 1} ({tool_name}) failed: {exc}"
                self.context.update_entity(last_task=task.to_dict())
                self._save_active_tasks()
                return task

        task.status = "completed"
        task.current_step_index = len(task.steps)
        task.result_summary = " | ".join(summaries) if summaries else "Completed."
        task.updated_at = time.time()
        self.context.update_entity(last_task=task.to_dict())
        self._save_active_tasks()

        # Acoustic notification on completed task
        try:
            from core.audio_cues import play_task_complete_chime
            play_task_complete_chime()
        except Exception:
            pass

        return task

    def get_active_task_summary(self) -> str:
        """Provide a concise conversational status for 'What are you doing?'."""
        with _LOCK:
            active = [t for t in self._tasks.values() if t.status in ("running", "pending")]
            if not active:
                return "All tasks completed. Standing by for instructions, sir."
            top = active[0]
            step_desc = ""
            if 0 <= top.current_step_index < len(top.steps):
                step_desc = f": {top.steps[top.current_step_index].get('description', '')}"
            return (
                f"Currently working on '{top.goal}' "
                f"[{top.progress_pct}% complete, step {top.current_step_index + 1}/{len(top.steps)}{step_desc}]."
            )

    def pause_task(self, task_id: str) -> dict[str, Any]:
        with _LOCK:
            task = self._tasks.get(task_id)
            if not task:
                return {"ok": False, "error": f"Task '{task_id}' not found."}
            task.status = "paused"
            task.updated_at = time.time()
            self._save_active_tasks()
            return {"ok": True, "message": f"Paused task '{task.goal}'.", "task": task.to_dict()}

    def resume_task(self, task_id: str) -> TaskRecord:
        with _LOCK:
            task = self._tasks.get(task_id)
            if not task:
                raise KeyError(f"Task '{task_id}' not found.")
            task.status = "pending"
            task.updated_at = time.time()
            self._save_active_tasks()
        return self.execute_task(task)

    def cancel_task(self, task_id: str) -> dict[str, Any]:
        with _LOCK:
            task = self._tasks.get(task_id)
            if not task:
                return {"ok": False, "error": f"Task '{task_id}' not found."}
            task.status = "cancelled"
            task.updated_at = time.time()
            self._save_active_tasks()
            return {"ok": True, "message": f"Cancelled task '{task.goal}'.", "task": task.to_dict()}

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
            self._save_active_tasks()
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

