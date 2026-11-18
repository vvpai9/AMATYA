"""
AMATYA Autonomous Task Orchestrator (core/task_orchestrator.py)
================================================================
Phase 16 Core Engine: Persistent, dependency-aware, multi-step task graph orchestrator.

Features:
  - Persistent state checkpointing to memory/orchestrator_tasks.json after every transition.
  - Startup recovery of interrupted task graphs (fails closed; pauses in-flight tasks).
  - Dependency-aware parallel and sequential scheduling via topological task graph.
  - Central Security Gateway enforcement before any capability execution.
  - Automatic post-execution verification via TaskVerifier.
  - Intelligent failure classification and exponential backoff retry via FailureRecoveryEngine.
  - Interactive approval gating for sensitive/high-risk actions.
  - Thread-safe control: pause, resume, cancel, and emergency stop.
"""
from __future__ import annotations

import concurrent.futures
import json
import logging
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

from core.capability_registry import get_capability_registry, RiskLevel
from core.failure_recovery import ErrorCategory, FailureRecoveryEngine, RecoveryPlan, get_recovery_engine
from core.security import (
    PermissionTier,
    authorize_tool_execution,
    get_autonomy_level,
    log_audit_event,
)
from core.task_graph import TaskGraph, TaskNode, TaskStatus
from core.task_verifier import TaskVerifier, get_verifier
from memory.config_manager import BASE_DIR

logger = logging.getLogger(__name__)

ORCHESTRATOR_TASKS_PATH = BASE_DIR / "memory" / "orchestrator_tasks.json"
_LOCK = threading.RLock()


def _resolve_bridged_value(val: Any, parent_results: dict[str, Any]) -> Any:
    """Recursively resolve parameter references from parent results.

    Supports:
      - "$parent_task_id.key" or "$parent_task_id"
      - "{parent_task_id.key}" inside string templates
    """
    if isinstance(val, str):
        # Direct reference: "$node_id.field" or "$node_id"
        if val.startswith("$"):
            expr = val[1:].strip()
            parts = expr.split(".", 1)
            parent_id = parts[0]
            field = parts[1] if len(parts) > 1 else None

            if parent_id in parent_results:
                pres = parent_results[parent_id]
                if field is None:
                    return pres
                if isinstance(pres, dict) and field in pres:
                    return pres[field]
                # Try finding field inside 'data' or 'result' dict if pres is an outcome
                if isinstance(pres, dict):
                    for subk in ("data", "result"):
                        if isinstance(pres.get(subk), dict) and field in pres[subk]:
                            return pres[subk][field]
            return val

        # Template string replacement: "{node_id.key}"
        def _replace_template(match: re.Match) -> str:
            expr = match.group(1).strip()
            parts = expr.split(".", 1)
            parent_id = parts[0]
            field = parts[1] if len(parts) > 1 else None
            if parent_id in parent_results:
                pres = parent_results[parent_id]
                if field is None:
                    return str(pres)
                if isinstance(pres, dict) and field in pres:
                    return str(pres[field])
                if isinstance(pres, dict):
                    for subk in ("data", "result"):
                        if isinstance(pres.get(subk), dict) and field in pres[subk]:
                            return str(pres[subk][field])
            return match.group(0)

        return re.sub(r"\{([a-zA-Z0-9_\-\.]+)\}", _replace_template, val)

    elif isinstance(val, dict):
        return {k: _resolve_bridged_value(v, parent_results) for k, v in val.items()}
    elif isinstance(val, list):
        return [_resolve_bridged_value(item, parent_results) for item in val]
    return val


class TaskOrchestrator:
    """Persistent, dependency-aware autonomous task orchestrator."""

    def __init__(
        self,
        tasks_file: Optional[Path] = None,
        max_workers: int = 6,
    ) -> None:
        self.tasks_file = tasks_file or ORCHESTRATOR_TASKS_PATH
        self.max_workers = max_workers
        self._graphs: dict[str, TaskGraph] = {}
        self._listeners: list[Callable[[str, dict[str, Any]], None]] = []
        self._cancel_requested = threading.Event()
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="amatya-orch",
        )
        self._running_futures: dict[str, concurrent.futures.Future] = {}
        self._poll_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Load existing state & perform crash recovery
        self._load_state()
        self.recover_interrupted_tasks()

    def add_listener(self, listener: Callable[[str, dict[str, Any]], None]) -> None:
        """Register a notification callback for orchestrator events."""
        with _LOCK:
            if listener not in self._listeners:
                self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[str, dict[str, Any]], None]) -> None:
        with _LOCK:
            if listener in self._listeners:
                self._listeners.remove(listener)

    def _notify(self, event_type: str, data: dict[str, Any]) -> None:
        """Dispatch notification to registered listeners without holding locks."""
        listeners_copy = list(self._listeners)
        for listener in listeners_copy:
            try:
                listener(event_type, data)
            except Exception as e:
                logger.warning(f"Orchestrator listener error on '{event_type}': {e}")

    # ── Persistence & Checkpointing ───────────────────────────────────────────

    def _load_state(self) -> None:
        with _LOCK:
            if not self.tasks_file.exists():
                return
            try:
                content = self.tasks_file.read_text(encoding="utf-8")
                if not content.strip():
                    return
                data = json.loads(content)
                if isinstance(data, dict):
                    for gid, gdict in data.items():
                        try:
                            self._graphs[gid] = TaskGraph.from_dict(gdict)
                        except Exception as ex:
                            logger.error(f"Failed to deserialize TaskGraph '{gid}': {ex}")
            except Exception as e:
                logger.error(f"Failed to read orchestrator tasks file: {e}")

    def checkpoint(self) -> None:
        """Persist current state of all task graphs to disk."""
        with _LOCK:
            try:
                self.tasks_file.parent.mkdir(parents=True, exist_ok=True)
                serialized = {gid: g.to_dict() for gid, g in self._graphs.items()}
                temp_file = self.tasks_file.with_suffix(".tmp")
                temp_file.write_text(
                    json.dumps(serialized, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                temp_file.replace(self.tasks_file)
            except Exception as e:
                logger.error(f"Failed to checkpoint orchestrator tasks: {e}")

    def recover_interrupted_tasks(self) -> int:
        """Recover from previous application crash / restart.

        Any graphs or nodes in RUNNING or VERIFYING state are safely set to PAUSED
        so that in-progress work is not duplicated or left in an inconsistent state.
        Returns the number of recovered graphs.
        """
        recovered_count = 0
        with _LOCK:
            for gid, graph in self._graphs.items():
                if graph.status in (TaskStatus.RUNNING, TaskStatus.VERIFYING):
                    graph.status = TaskStatus.PAUSED
                    recovered_count += 1
                    for nid, node in graph.nodes.items():
                        if node.status in (TaskStatus.RUNNING, TaskStatus.VERIFYING):
                            node.status = TaskStatus.PAUSED
                            node.error = "Process interrupted by application restart. Paused for verification."
                    log_audit_event(
                        "task_recovery",
                        gid,
                        PermissionTier.GENERAL_CONVERSATION,
                        True,
                        f"Recovered interrupted TaskGraph '{gid}' in PAUSED state.",
                    )
            if recovered_count > 0:
                self.checkpoint()
                logger.info(f"Crash recovery: Paused {recovered_count} interrupted task graph(s).")
        return recovered_count

    # ── Graph Management ──────────────────────────────────────────────────────

    def submit_graph(self, graph: TaskGraph) -> str:
        """Register and save a new task graph."""
        with _LOCK:
            self._graphs[graph.graph_id] = graph
            self.checkpoint()
            self._notify("graph_submitted", {"graph_id": graph.graph_id, "goal": graph.goal})
        return graph.graph_id

    def get_graph(self, graph_id: str) -> Optional[TaskGraph]:
        with _LOCK:
            return self._graphs.get(graph_id)

    def list_graphs(self, limit: int = 50) -> list[dict[str, Any]]:
        with _LOCK:
            sorted_graphs = sorted(
                self._graphs.values(),
                key=lambda g: g.created_at,
                reverse=True,
            )
            return [g.to_dict() for g in sorted_graphs[:limit]]

    # ── Task Execution Engine ─────────────────────────────────────────────────

    def run_graph(self, graph_id: str, async_exec: bool = True) -> TaskGraph:
        """Execute a task graph respecting dependencies, security, and verification.

        If async_exec is True, launches execution in a background thread and returns immediately.
        """
        graph = self.get_graph(graph_id)
        if not graph:
            raise ValueError(f"TaskGraph '{graph_id}' not found.")

        if graph.status == TaskStatus.CANCELLED:
            raise RuntimeError(f"Cannot run cancelled TaskGraph '{graph_id}'.")

        graph.status = TaskStatus.RUNNING
        self.checkpoint()
        self._notify("graph_started", {"graph_id": graph_id, "goal": graph.goal})

        if async_exec:
            thread = threading.Thread(
                target=self._execution_loop,
                args=(graph_id,),
                daemon=True,
                name=f"orch-graph-{graph_id[:8]}",
            )
            thread.start()
            return graph
        else:
            self._execution_loop(graph_id)
            return self.get_graph(graph_id) or graph

    def _execution_loop(self, graph_id: str) -> None:
        """Continuous dependency-aware execution loop for a single graph."""
        recovery_engine = get_recovery_engine()
        verifier = get_verifier()
        cap_reg = get_capability_registry()

        while not self._cancel_requested.is_set():
            with _LOCK:
                graph = self.get_graph(graph_id)
                if not graph:
                    break

                # Check if graph paused or cancelled externally
                if graph.status in (TaskStatus.PAUSED, TaskStatus.CANCELLED, TaskStatus.COMPLETED, TaskStatus.FAILED):
                    break

                # Check if all tasks have reached terminal states
                if graph.is_terminal():
                    if graph.has_failures():
                        graph.status = TaskStatus.FAILED
                    else:
                        graph.status = TaskStatus.COMPLETED
                    self.checkpoint()
                    self._notify("graph_completed", {"graph_id": graph_id, "status": graph.status.value})
                    break

                # Get ready nodes whose dependencies are COMPLETED
                ready_nodes = graph.get_ready_nodes()

                # If no nodes are ready, check active nodes
                running_or_verifying = [
                    n for n in graph.nodes.values()
                    if n.status in (TaskStatus.RUNNING, TaskStatus.VERIFYING)
                ]
                waiting_approval = [
                    n for n in graph.nodes.values()
                    if n.status == TaskStatus.WAITING_FOR_APPROVAL
                ]

                if not ready_nodes and not running_or_verifying:
                    if waiting_approval:
                        # All active work is waiting for human authorization
                        graph.status = TaskStatus.WAITING_FOR_APPROVAL
                        self.checkpoint()
                        self._notify("graph_waiting_for_approval", {"graph_id": graph_id})
                        break

                    # Deadlock or unresolvable dependencies (e.g. failed upstream dependencies)
                    unmet = [n for n in graph.nodes.values() if n.status == TaskStatus.PENDING]
                    if unmet:
                        for n in unmet:
                            n.mark_cancelled("Upstream dependency failed or cancelled.")
                        graph.status = TaskStatus.FAILED
                        self.checkpoint()
                        self._notify("graph_failed", {"graph_id": graph_id, "error": "Unmet dependencies or failed upstream tasks."})
                    break

            if not ready_nodes:
                # Active nodes are still processing or waiting for approval, sleep brief interval
                time.sleep(0.2)
                continue

            # Process ready nodes
            for node in ready_nodes:
                if self._cancel_requested.is_set():
                    break

                # Check approval requirements
                if self._requires_approval(node):
                    node.mark_waiting_for_approval()
                    self.checkpoint()
                    self._notify("task_waiting_for_approval", {
                        "graph_id": graph_id,
                        "task_id": node.task_id,
                        "capability": node.capability,
                        "parameters": node.parameters,
                    })
                    continue

                # Prepare inputs by bridging parameters from parent nodes
                parent_results = {dep_id: graph.nodes[dep_id].result for dep_id in node.dependencies if dep_id in graph.nodes}
                resolved_params = _resolve_bridged_value(node.parameters, parent_results)

                # Mark node RUNNING
                node.mark_running()
                self.checkpoint()
                self._notify("task_started", {"graph_id": graph_id, "task_id": node.task_id})

                # Dispatch execution asynchronously or inline
                future = self._executor.submit(
                    self._execute_single_node,
                    graph_id,
                    node.task_id,
                    node.capability,
                    resolved_params,
                )
                self._running_futures[f"{graph_id}:{node.task_id}"] = future

            time.sleep(0.1)

    def _requires_approval(self, node: TaskNode) -> bool:
        """Determine whether a task node requires human authorization before running."""
        cap_reg = get_capability_registry()
        cap = cap_reg.get_capability(node.capability)
        autonomy_raw = get_autonomy_level()

        autonomy_map = {
            "observe_only": 1,
            "recommend": 2,
            "confirm": 3,
            "autonomous_low_risk": 4,
            "autonomous_workflows": 5,
        }
        if isinstance(autonomy_raw, str):
            autonomy = autonomy_map.get(autonomy_raw.strip().lower(), 3)
        else:
            try:
                autonomy = int(autonomy_raw)
            except Exception:
                autonomy = 3

        # If autonomy level is 'observe_only' (1) or 'recommend' (2), side-effecting tasks require approval
        if autonomy <= 2:
            return True

        if cap:
            # High risk or critical permission tiers require confirmation
            if cap.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL) and autonomy < 5:
                return True
            if cap.permission_tier >= PermissionTier.SENSITIVE_SYSTEM:
                return True

        if node.risk_level in ("high", "critical") and autonomy < 5:
            return True

        return False

    def _execute_single_node(
        self,
        graph_id: str,
        task_id: str,
        capability: str,
        parameters: dict[str, Any],
    ) -> None:
        """Worker thread function to execute, verify, and handle recovery for a single node."""
        cap_reg = get_capability_registry()
        verifier = get_verifier()
        recovery_engine = get_recovery_engine()

        graph = self.get_graph(graph_id)
        if not graph or task_id not in graph.nodes:
            return
        node = graph.nodes[task_id]

        try:
            # 1. Execute capability
            result = cap_reg.execute_capability(
                capability,
                parameters,
                actor="amatya.task_orchestrator",
                interactive_confirm=False,
            )

            # 2. Transition to VERIFYING and verify
            node.mark_verifying()
            self.checkpoint()

            verification = verifier.verify_task(node, result)
            if verification.passed:
                node.mark_completed(result, verification_details=verification.details)
                self.checkpoint()
                self._notify("task_completed", {
                    "graph_id": graph_id,
                    "task_id": task_id,
                    "result": str(result)[:200],
                })
            else:
                # Verification failed - treat as error and evaluate recovery
                err_msg = f"Task verification failed: {'; '.join(verification.errors)}"
                self._handle_node_failure(graph_id, node, RuntimeError(err_msg))

        except Exception as ex:
            self._handle_node_failure(graph_id, node, ex)

    def _handle_node_failure(self, graph_id: str, node: TaskNode, error: Exception) -> None:
        """Handle execution or verification failure with RecoveryPlan."""
        recovery_engine = get_recovery_engine()
        plan = recovery_engine.diagnose(
            capability=node.capability,
            parameters=node.parameters,
            error_msg=str(error),
            retry_count=node.retry_count,
            max_retries=node.max_retries,
            is_reversible=node.is_reversible,
        )

        if plan.can_retry and node.retry_count < node.max_retries:
            node.retry_count += 1
            node.status = TaskStatus.READY
            logger.info(
                f"Retrying task '{node.task_id}' in graph '{graph_id}' "
                f"(attempt {node.retry_count}/{node.max_retries}) after {plan.backoff_seconds:.1f}s backoff. Strategy: {plan.recommended_strategy}"
            )
            time.sleep(plan.backoff_seconds)
            self.checkpoint()
            self._notify("task_retry", {
                "graph_id": graph_id,
                "task_id": node.task_id,
                "attempt": node.retry_count,
                "reason": plan.recommended_strategy,
            })
        else:
            # Cannot retry or max retries exceeded
            node.mark_failed(str(error), classification=plan.category.value)
            self.checkpoint()
            self._notify("task_failed", {
                "graph_id": graph_id,
                "task_id": node.task_id,
                "error": str(error),
                "classification": plan.category.value,
                "recommended_strategy": plan.recommended_strategy,
            })

    # ── Interactive Approval & Controls ───────────────────────────────────────

    def approve_task(self, graph_id: str, task_id: str) -> dict[str, Any]:
        """Approve a task currently WAITING_FOR_APPROVAL to transition to READY."""
        with _LOCK:
            graph = self.get_graph(graph_id)
            if not graph or task_id not in graph.nodes:
                return {"ok": False, "error": f"Task '{task_id}' not found in graph '{graph_id}'."}

            node = graph.nodes[task_id]
            if node.status != TaskStatus.WAITING_FOR_APPROVAL:
                return {"ok": False, "error": f"Task '{task_id}' is not waiting for approval (current status: {node.status.value})."}

            node.status = TaskStatus.READY
            self.checkpoint()
            log_audit_event(
                "task_approved",
                task_id,
                PermissionTier.GENERAL_CONVERSATION,
                True,
                f"Task '{task_id}' approved for execution by user/operator.",
            )
            self._notify("task_approved", {"graph_id": graph_id, "task_id": task_id})

        # Ensure execution loop is running to pick up the newly ready task
        self.run_graph(graph_id, async_exec=True)
        return {"ok": True, "message": f"Task '{task_id}' approved and scheduled."}

    def deny_task(self, graph_id: str, task_id: str, reason: str = "Denied by user.") -> dict[str, Any]:
        """Deny an approval request, marking the node failed."""
        with _LOCK:
            graph = self.get_graph(graph_id)
            if not graph or task_id not in graph.nodes:
                return {"ok": False, "error": f"Task '{task_id}' not found in graph '{graph_id}'."}

            node = graph.nodes[task_id]
            node.mark_failed(f"User denied approval: {reason}", classification="authorization_denied")
            self.checkpoint()
            log_audit_event(
                "task_denied",
                task_id,
                PermissionTier.GENERAL_CONVERSATION,
                False,
                f"Task '{task_id}' denied: {reason}",
            )
            self._notify("task_denied", {"graph_id": graph_id, "task_id": task_id, "reason": reason})
        return {"ok": True, "message": f"Task '{task_id}' denied."}

    def pause_graph(self, graph_id: str) -> dict[str, Any]:
        """Pause execution of a task graph."""
        with _LOCK:
            graph = self.get_graph(graph_id)
            if not graph:
                return {"ok": False, "error": f"Graph '{graph_id}' not found."}
            graph.status = TaskStatus.PAUSED
            self.checkpoint()
            self._notify("graph_paused", {"graph_id": graph_id})
            return {"ok": True, "message": f"Graph '{graph_id}' paused."}

    def resume_graph(self, graph_id: str) -> dict[str, Any]:
        """Resume execution of a paused task graph."""
        with _LOCK:
            graph = self.get_graph(graph_id)
            if not graph:
                return {"ok": False, "error": f"Graph '{graph_id}' not found."}
            if graph.status != TaskStatus.PAUSED:
                return {"ok": False, "error": f"Graph '{graph_id}' is not paused (status: {graph.status.value})."}

            graph.status = TaskStatus.READY
            for node in graph.nodes.values():
                if node.status == TaskStatus.PAUSED:
                    node.status = TaskStatus.READY
            self.checkpoint()
            self._notify("graph_resumed", {"graph_id": graph_id})

        self.run_graph(graph_id, async_exec=True)
        return {"ok": True, "message": f"Graph '{graph_id}' resumed."}

    def cancel_graph(self, graph_id: str, reason: str = "Cancelled by user.") -> dict[str, Any]:
        """Cancel a task graph and any pending tasks."""
        with _LOCK:
            graph = self.get_graph(graph_id)
            if not graph:
                return {"ok": False, "error": f"Graph '{graph_id}' not found."}
            graph.status = TaskStatus.CANCELLED
            for node in graph.nodes.values():
                if node.status in (TaskStatus.PENDING, TaskStatus.READY, TaskStatus.WAITING_FOR_APPROVAL, TaskStatus.PAUSED):
                    node.mark_cancelled(reason)
            self.checkpoint()
            self._notify("graph_cancelled", {"graph_id": graph_id, "reason": reason})
            return {"ok": True, "message": f"Graph '{graph_id}' cancelled."}

    def emergency_stop(self) -> dict[str, Any]:
        """Immediately pause/cancel all running task graphs."""
        with _LOCK:
            self._cancel_requested.set()
            count = 0
            for graph in self._graphs.values():
                if graph.status in (TaskStatus.RUNNING, TaskStatus.READY):
                    graph.status = TaskStatus.CANCELLED
                    for node in graph.nodes.values():
                        if node.status in (TaskStatus.RUNNING, TaskStatus.READY, TaskStatus.PENDING, TaskStatus.WAITING_FOR_APPROVAL):
                            node.mark_cancelled("Emergency stop triggered.")
                    count += 1
            self.checkpoint()
            log_audit_event(
                "emergency_stop",
                "system",
                PermissionTier.CRITICAL_SECURITY,
                True,
                f"Emergency stop halted {count} active graph(s).",
            )
            self._notify("emergency_stop", {"halted_graphs": count})
            self._cancel_requested.clear()
            return {"ok": True, "message": f"Emergency stop executed. Halted {count} graph(s)."}


_ORCHESTRATOR_INSTANCE: Optional[TaskOrchestrator] = None


def get_task_orchestrator() -> TaskOrchestrator:
    global _ORCHESTRATOR_INSTANCE
    with _LOCK:
        if _ORCHESTRATOR_INSTANCE is None:
            _ORCHESTRATOR_INSTANCE = TaskOrchestrator()
        return _ORCHESTRATOR_INSTANCE
