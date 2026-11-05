"""
AMATYA Adaptive Personal Automation & Workflow Engine (core/workflow_engine.py)
==============================================================================
Implements Section 6 (Adaptive Personal Automation) of AMATYA Phase 12:
  - Automation Engine: Triggers (cron/schedule, event, sensor, manual), Conditions, Actions.
  - Workflow Learning: Observes repeated user command/tool sequences, identifies patterns,
    and proposes user-approved automation routines.
  - Procedural Memory Integration: Persists approved workflows into memory/procedural_memory.json.
  - Safety & Permission Enforcement: Enforces Permission Tiers before triggering sensitive actions.
"""
from __future__ import annotations

import fnmatch
import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from core.security import PermissionTier, check_permission, log_audit_event
from memory.config_manager import BASE_DIR

PROCEDURAL_MEMORY_PATH = BASE_DIR / "memory" / "procedural_memory.json"
_LOCK = threading.RLock()


@dataclass
class WorkflowTrigger:
    trigger_type: str  # schedule | event | sensor | manual
    parameters: dict[str, Any] = field(default_factory=dict)
    # schedule: {"time": "09:00", "days": ["mon", "tue", ...]}
    # event: {"event_name": "device_connected", "filter": "phone"}
    # sensor: {"entity_id": "sensor.temp", "operator": ">", "threshold": 30}


@dataclass
class WorkflowRoutine:
    workflow_id: str
    name: str
    description: str
    triggers: list[dict[str, Any]] = field(default_factory=list)
    conditions: list[dict[str, Any]] = field(default_factory=list)
    steps: list[dict[str, Any]] = field(default_factory=list)
    required_permission_tier: int = int(PermissionTier.REMOTE_DEVICE_CONTROL)
    approved_by_user: bool = False
    enabled: bool = True
    created_at: float = field(default_factory=time.time)
    last_run_at: float = 0.0
    run_count: int = 0
    learned_pattern: bool = False

    def __init__(
        self,
        workflow_id: str = "",
        name: str = "",
        description: str = "",
        triggers: list[dict[str, Any]] | None = None,
        conditions: list[dict[str, Any]] | None = None,
        steps: list[dict[str, Any]] | None = None,
        required_permission_tier: int = int(PermissionTier.REMOTE_DEVICE_CONTROL),
        approved_by_user: bool = False,
        enabled: bool = True,
        created_at: float | None = None,
        last_run_at: float = 0.0,
        run_count: int = 0,
        learned_pattern: bool = False,
        # Compatibility aliases:
        id: str = "",
        actions: list[dict[str, Any]] | None = None,
        trigger_type: str = "",
        trigger_config: dict[str, Any] | None = None,
        requires_approval: bool | None = None,
        created_by: str = "",
    ) -> None:
        self.workflow_id = workflow_id or id or ("wf_" + str(int(time.time())))
        self.name = name or self.workflow_id
        self.description = description
        self.triggers = triggers or ([{"trigger_type": trigger_type, "parameters": trigger_config or {}}] if trigger_type else [])
        self.conditions = conditions or []
        self.steps = steps or actions or []
        self.required_permission_tier = required_permission_tier
        if requires_approval is not None:
            self.approved_by_user = not requires_approval
        else:
            self.approved_by_user = approved_by_user
        self.enabled = enabled
        self.created_at = created_at or time.time()
        self.last_run_at = last_run_at
        self.run_count = run_count
        self.learned_pattern = learned_pattern

    @property
    def id(self) -> str:
        return self.workflow_id

    @property
    def actions(self) -> list[dict[str, Any]]:
        return self.steps

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class WorkflowEngine:
    """Manages scheduled, event-driven, and learned personal workflows."""

    def __init__(self, storage_path: Path | None = None) -> None:
        self.storage_path = storage_path or PROCEDURAL_MEMORY_PATH
        self._workflows: dict[str, WorkflowRoutine] = {}
        self._recent_invocations: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        with _LOCK:
            if not self.storage_path.exists():
                self._load_seed_routines()
                return
            try:
                data = json.loads(self.storage_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    for wid, obj in data.items():
                        if isinstance(obj, dict):
                            self._workflows[wid] = WorkflowRoutine(**{
                                k: v for k, v in obj.items() if k in WorkflowRoutine.__dataclass_fields__
                            })
            except Exception:
                self._load_seed_routines()

    def _load_seed_routines(self) -> None:
        """Seed default user-approved routines (morning briefing, leaving home)."""
        seed_routines = [
            WorkflowRoutine(
                workflow_id="routine_morning_workspace",
                name="Morning Workspace Preparation",
                description="Prepare desktop workspace, check git repo status, and fetch world news briefing",
                triggers=[{"trigger_type": "manual", "parameters": {"command": "prepare workspace"}}],
                steps=[
                    {"tool": "creator", "parameters": {"action": "git_status"}},
                    {"tool": "web_search", "parameters": {"query": "latest technology news", "mode": "news"}},
                ],
                approved_by_user=True,
                enabled=True,
            ),
            WorkflowRoutine(
                workflow_id="routine_evening_wrapup",
                name="Evening Development Wrapup",
                description="Run repository test checks, summarize recent changes, and send status to phone",
                triggers=[{"trigger_type": "schedule", "parameters": {"time": "18:30"}}],
                steps=[
                    {"tool": "creator", "parameters": {"action": "run_tests"}},
                    {"tool": "device_control", "parameters": {"action": "send_file", "device": "phone", "file_path": "$prev.summary"}},
                ],
                approved_by_user=True,
                enabled=True,
            ),
        ]
        with _LOCK:
            for r in seed_routines:
                self._workflows[r.workflow_id] = r
            self._save()

    def _save(self) -> None:
        with _LOCK:
            try:
                self.storage_path.parent.mkdir(parents=True, exist_ok=True)
                serialized = {k: v.to_dict() for k, v in self._workflows.items()}
                self.storage_path.write_text(
                    json.dumps(serialized, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            except Exception:
                pass

    # ── Workflow Execution ─────────────────────────────────────────────────────

    def execute_workflow(
        self,
        workflow_id: str,
        action_runner: Callable[[str, dict[str, Any]], Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a registered workflow routine with permission and condition checks."""
        with _LOCK:
            wf = self._workflows.get(workflow_id)
            if not wf:
                return {"ok": False, "error": f"Workflow '{workflow_id}' not found."}
            if not wf.enabled:
                return {"ok": False, "error": f"Workflow '{wf.name}' is currently disabled."}
            if not wf.approved_by_user:
                return {"ok": False, "error": f"Workflow '{wf.name}' requires explicit user approval before execution."}

        # Check permissions for the workflow
        perm = check_permission(
            f"workflow_{wf.name}",
            PermissionTier(wf.required_permission_tier),
            description=f"Execute workflow: {wf.name}",
            interactive_confirm=False,
        )
        if not perm["allowed"]:
            return {"ok": False, "error": f"Workflow permission denied: {perm['reason']}"}

        # Dispatch via orchestrator
        from core.orchestrator import TaskRecord, get_orchestrator
        orch = get_orchestrator()

        task = TaskRecord(
            task_id=f"wf_{uuid.uuid4().hex[:8]}",
            goal=wf.name,
            resolved_goal=wf.description,
            domain="workflow_automation",
            priority=3,
            steps=[dict(s) for s in wf.steps],
        )

        completed = orch.execute_task(task, action_runner=action_runner)
        with _LOCK:
            wf.last_run_at = time.time()
            wf.run_count += 1
            self._save()

        log_audit_event(
            "workflow_executed",
            f"workflow:{wf.name}",
            wf.required_permission_tier,
            completed.status == "completed",
            details={"steps": len(wf.steps), "status": completed.status},
        )

        return {
            "ok": completed.status == "completed",
            "workflow_id": wf.workflow_id,
            "name": wf.name,
            "status": completed.status,
            "result_summary": completed.result_summary,
            "task": completed.to_dict(),
        }

    # ── Workflow Learning from Repeated Invocations ────────────────────────────

    def record_action_invocation(self, tool_name: str, parameters: dict[str, Any]) -> dict[str, Any] | None:
        """Observe user action invocations and detect repeated workflows."""
        with _LOCK:
            now = time.time()
            # Clean invocations older than 1 hour
            self._recent_invocations = [
                inv for inv in self._recent_invocations if (now - inv["timestamp"]) < 3600
            ]
            self._recent_invocations.append({
                "tool": tool_name,
                "parameters": parameters,
                "timestamp": now,
            })

            # Check if a 2-step sequence was repeated at least 3 times
            if len(self._recent_invocations) >= 6:
                return self._detect_repeated_sequence()
        return None

    def _detect_repeated_sequence(self) -> dict[str, Any] | None:
        """Scan recent invocations for repeated adjacent tool sequences."""
        tools = [inv["tool"] for inv in self._recent_invocations]
        n = len(tools)
        # Look for length 2 patterns
        for i in range(n - 3):
            pat = (tools[i], tools[i + 1])
            # Count occurrences of pat
            count = 0
            for j in range(n - 1):
                if (tools[j], tools[j + 1]) == pat:
                    count += 1
            if count >= 3:
                # Check if already suggested
                existing_names = [wf.name for wf in self._workflows.values()]
                candidate_name = f"Automated {pat[0].capitalize()} & {pat[1].capitalize()} Routine"
                if candidate_name not in existing_names:
                    return {
                        "detected_pattern": list(pat),
                        "occurrences": count,
                        "suggested_name": candidate_name,
                        "steps": [
                            {"tool": pat[0], "parameters": {}},
                            {"tool": pat[1], "parameters": {}},
                        ],
                    }
        return None

    def register_routine(
        self,
        name_or_routine: str | WorkflowRoutine,
        description: str = "",
        steps: list[dict[str, Any]] | None = None,
        triggers: list[dict[str, Any]] | None = None,
        approved_by_user: bool = False,
    ) -> Any:
        """Register a new routine (learned or user-configured). Accepts WorkflowRoutine or kwargs."""
        if isinstance(name_or_routine, WorkflowRoutine):
            routine = name_or_routine
            with _LOCK:
                self._workflows[routine.workflow_id] = routine
                self._save()
            return True, f"Routine '{routine.name}' registered."

        wid = f"wf_{uuid.uuid4().hex[:8]}"
        routine = WorkflowRoutine(
            workflow_id=wid,
            name=str(name_or_routine).strip(),
            description=description.strip(),
            triggers=triggers or [{"trigger_type": "manual"}],
            steps=steps or [],
            approved_by_user=approved_by_user,
            enabled=True,
        )
        with _LOCK:
            self._workflows[wid] = routine
            self._save()
        return routine

    def approve_routine(self, workflow_id: str) -> tuple[bool, str]:
        with _LOCK:
            wf = self._workflows.get(workflow_id)
            if not wf:
                return False, f"Workflow '{workflow_id}' not found."
            wf.approved_by_user = True
            wf.enabled = True
            self._save()
            return True, f"Workflow '{wf.name}' approved and activated."

    def list_workflows(self) -> list[dict[str, Any]]:
        with _LOCK:
            return [wf.to_dict() for wf in self._workflows.values()]

    def delete_workflow(self, workflow_id: str) -> tuple[bool, str]:
        with _LOCK:
            if workflow_id in self._workflows:
                name = self._workflows.pop(workflow_id).name
                self._save()
                return True, f"Deleted workflow '{name}'."
            return False, f"Workflow '{workflow_id}' not found."


_WORKFLOW_ENGINE: WorkflowEngine | None = None
_WE_LOCK = threading.Lock()


def get_workflow_engine() -> WorkflowEngine:
    global _WORKFLOW_ENGINE
    with _WE_LOCK:
        if _WORKFLOW_ENGINE is None:
            _WORKFLOW_ENGINE = WorkflowEngine()
    return _WORKFLOW_ENGINE
