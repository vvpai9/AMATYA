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

import concurrent.futures
import hashlib
import json
import re
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from core.context_manager import ContextManager, get_context_manager
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


class ContextTracker(ContextManager):
    """Tracks conversational and operational entities across turns so pronouns and
    elliptical commands ('Open that', 'Close the previous window', 'Check the same
    project again', 'Send that file to my phone', 'Continue what you were doing')
    resolve deterministically."""
    pass


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
    # If val contains or points to a document or text file, read the file directly!
    fp = _extract_file_path(val)
    if fp:
        p = Path(fp).expanduser()
        if p.is_file() and p.suffix.lower() in (".txt", ".md", ".json", ".docx", ".pdf", ".csv"):
            try:
                from core.doc_generator import analyze_document
                doc_res = analyze_document(p)
                if doc_res.get("ok") and doc_res.get("text"):
                    return doc_res["text"]
                return p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                pass
    if isinstance(val, dict):
        for k in ("summary", "content", "result", "text", "message"):
            cand = val.get(k)
            if isinstance(cand, str) and cand.strip() and not cand.startswith("File created:"):
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

    _extract_summary_text = staticmethod(_extract_summary_text)

    def __init__(self) -> None:
        self.context = ContextTracker()
        self._tasks: dict[str, TaskRecord] = {}
        self._active_tasks_path = ACTIVE_TASKS_PATH
        self._cancel_requested = threading.Event()
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=6, thread_name_prefix="amatya-task")
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
        on_status_update: Callable[[TaskRecord, str], None] | None = None,
        speak: Callable[[str], None] | None = None,
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

            # Continuous voice / listener updates
            step_desc = step.get("description") or f"Running {tool_name}"
            if on_status_update:
                on_status_update(task, f"Task '{task.goal}' started step {idx + 1}/{len(task.steps)}: {step_desc}")
            if speak:
                speak(f"Sir, {task.goal}: starting step {idx + 1}.")

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
                    # Direct action module dispatch with security gateway enforcement
                    from core.security import authorize_tool_execution
                    auth = authorize_tool_execution(tool_name, params, actor="orchestrator")
                    if not auth["allowed"]:
                        raise PermissionError(f"Security gateway blocked '{tool_name}': {auth.get('reason')}")
                    mod = __import__(f"actions.{tool_name}", fromlist=["execute"])
                    res_obj = mod.execute(params)
                    res_str = str(res_obj)

                step["status"] = "completed"
                step["result"] = res_str[:500]
                task.step_results.append(res_obj)
                summaries.append(f"Step {idx + 1} ({tool_name}): {res_str[:200]}")
                self.context.record_tool_call(tool_name, params)
                self._save_active_tasks()

                if on_status_update:
                    on_status_update(task, f"Task '{task.goal}' finished step {idx + 1}/{len(task.steps)}.")
                if speak:
                    speak(f"Sir, {task.goal}: step {idx + 1} completed.")
            except Exception as exc:
                step["status"] = "failed"
                step["error"] = str(exc)
                task.status = "failed"
                task.result_summary = f"Step {idx + 1} ({tool_name}) failed: {exc}"
                self.context.update_entity(last_task=task.to_dict())
                self._save_active_tasks()
                if on_status_update:
                    on_status_update(task, f"Task '{task.goal}' failed at step {idx + 1}: {exc}")
                return task

        task.status = "completed"
        task.current_step_index = len(task.steps)
        task.result_summary = " | ".join(summaries) if summaries else "Completed."
        task.updated_at = time.time()
        self.context.update_entity(last_task=task.to_dict())
        self._save_active_tasks()

        if on_status_update:
            on_status_update(task, f"Task '{task.goal}' completed successfully.")
        if speak:
            speak(f"Sir, completed task: {task.goal}.")

        # Acoustic notification on completed task
        try:
            from core.audio_cues import play_task_complete_chime
            play_task_complete_chime()
        except Exception:
            pass

        return task

    def execute_task_async(
        self,
        task: TaskRecord,
        action_runner: Callable[[str, dict[str, Any]], Any] | None = None,
        on_status_update: Callable[[TaskRecord, str], None] | None = None,
        speak: Callable[[str], None] | None = None,
    ) -> concurrent.futures.Future:
        """Run task asynchronously on the background worker pool."""
        if not hasattr(self, "_executor") or self._executor is None:
            self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=6, thread_name_prefix="amatya-task")
        return self._executor.submit(self.execute_task, task, action_runner, on_status_update, speak)

    def run_multitask(
        self,
        instructions: list[str],
        action_runner: Callable[[str, dict[str, Any]], Any] | None = None,
        speak: Callable[[str], None] | None = None,
        status_interval_sec: float = 3.0,
    ) -> dict[str, Any]:
        """Execute two or more tasks simultaneously while providing continuous voice status updates."""
        if not instructions:
            return {"ok": False, "error": "No tasks provided for multitasking."}

        tasks: list[TaskRecord] = []
        for inst in instructions:
            t = self.plan_workflow(inst)
            tasks.append(t)

        task_titles = [f"'{t.goal}'" for t in tasks]
        init_announcement = f"Sir, initiating concurrent multitasking for {len(tasks)} tasks: {' and '.join(task_titles)}."
        if speak:
            speak(init_announcement)

        status_log: list[str] = [init_announcement]

        def _voice_update(task: TaskRecord, message: str) -> None:
            status_log.append(message)
            if speak:
                speak(f"Task update: {task.goal} at step {task.current_step_index + 1} of {len(task.steps)}.")

        futures = []
        for t in tasks:
            f = self.execute_task_async(t, action_runner=action_runner, on_status_update=_voice_update, speak=None)
            futures.append(f)

        # Monitor loop for continuous status updates while running
        while any(not f.done() for f in futures):
            active_info = []
            for t in tasks:
                if t.status in ("running", "pending"):
                    active_info.append(f"{t.goal} ({t.progress_pct}% complete)")
            if speak and active_info:
                speak(f"Current task progress: {', '.join(active_info)}.")
            time.sleep(status_interval_sec)

        # Collect finished tasks
        results = [f.result() for f in futures]
        all_completed = all(r.status == "completed" for r in results)
        final_announcement = (
            f"Sir, all {len(results)} concurrent tasks have completed successfully."
            if all_completed
            else f"Sir, concurrent multitasking finished with {sum(1 for r in results if r.status == 'completed')}/{len(results)} completed."
        )
        if speak:
            speak(final_announcement)

        return {
            "ok": all_completed,
            "tasks_count": len(results),
            "tasks": [r.to_dict() for r in results],
            "status_log": status_log,
            "summary": final_announcement,
        }

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

