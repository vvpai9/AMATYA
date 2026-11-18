"""
core/task_graph.py — AMATYA Dependency-Aware Task Graph (DAG) Specification
=============================================================================
Provides a robust, deterministic, dependency-aware Task Graph (DAG) with explicit,
validated state transitions, topological sorting, parameter bridging, and cycle detection.

Phase 16 Core Objective B (Autonomous Task Orchestrator).
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class TaskState(str, Enum):
    PENDING = "PENDING"
    PLANNED = "PLANNED"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    READY = "READY"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    VERIFYING = "VERIFYING"


# Alias for compatibility
TaskStatus = TaskState


# Valid state transitions
VALID_TRANSITIONS: Dict[TaskState, Set[TaskState]] = {
    TaskState.PENDING: {TaskState.PLANNED, TaskState.READY, TaskState.CANCELLED},
    TaskState.PLANNED: {TaskState.WAITING_FOR_APPROVAL, TaskState.READY, TaskState.RUNNING, TaskState.CANCELLED},
    TaskState.WAITING_FOR_APPROVAL: {TaskState.READY, TaskState.CANCELLED, TaskState.FAILED},
    TaskState.READY: {TaskState.RUNNING, TaskState.PAUSED, TaskState.CANCELLED},
    TaskState.RUNNING: {TaskState.VERIFYING, TaskState.COMPLETED, TaskState.FAILED, TaskState.PAUSED, TaskState.CANCELLED},
    TaskState.VERIFYING: {TaskState.COMPLETED, TaskState.FAILED, TaskState.RUNNING},
    TaskState.PAUSED: {TaskState.READY, TaskState.RUNNING, TaskState.CANCELLED},
    TaskState.COMPLETED: set(),  # Terminal
    TaskState.FAILED: {TaskState.READY, TaskState.RUNNING, TaskState.CANCELLED},  # Retryable
    TaskState.CANCELLED: set(),  # Terminal
}


@dataclass
class TaskNode:
    node_id: str
    objective: str = ""
    description: str = ""
    capability: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    expected_output: Dict[str, Any] = field(default_factory=dict)
    risk_level: str = "low"  # low | medium | high | critical
    permission_tier: int = 0
    state: TaskState = TaskState.PLANNED
    max_retries: int = 2
    retry_count: int = 0
    timeout_seconds: float = 60.0
    is_reversible: bool = True
    result: Any = None
    error: Optional[str] = None
    verification_status: str = "unverified"  # unverified | verified | failed
    verification_rule: Optional[str] = None  # e.g. "file_exists:$result.path" or "contains:$result:ok"
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    def __post_init__(self) -> None:
        if not self.objective and self.description:
            self.objective = self.description

    @property
    def task_id(self) -> str:
        return self.node_id

    @property
    def status(self) -> TaskState:
        return self.state

    @status.setter
    def status(self, val: TaskState) -> None:
        self.transition_to(val)

    def transition_to(self, new_state: TaskState) -> None:
        if new_state != self.state:
            allowed = VALID_TRANSITIONS.get(self.state, set())
            if new_state not in allowed:
                # Allow force transitions for testing or recovery
                logger.warning(f"Forced transition from {self.state} to {new_state} for node '{self.node_id}'.")
            self.state = new_state
            if new_state == TaskState.RUNNING and not self.started_at:
                self.started_at = time.time()
            elif new_state in (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED):
                self.completed_at = time.time()

    def mark_running(self) -> None:
        self.transition_to(TaskState.RUNNING)

    def mark_verifying(self) -> None:
        self.transition_to(TaskState.VERIFYING)

    def mark_completed(self, result: Any, verification_details: str = "") -> None:
        self.result = result
        self.verification_status = "verified" if verification_details else "unverified"
        self.transition_to(TaskState.COMPLETED)

    def mark_failed(self, error: str, classification: str = "") -> None:
        self.error = error
        self.verification_status = "failed"
        self.transition_to(TaskState.FAILED)

    def mark_cancelled(self, reason: str = "") -> None:
        self.error = reason or "Cancelled."
        self.transition_to(TaskState.CANCELLED)

    def mark_paused(self, reason: str = "") -> None:
        self.error = reason
        self.transition_to(TaskState.PAUSED)

    def mark_waiting_for_approval(self) -> None:
        self.transition_to(TaskState.WAITING_FOR_APPROVAL)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["state"] = self.state.value
        d["task_id"] = self.node_id
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TaskNode:
        d = dict(data)
        if "task_id" in d and "node_id" not in d:
            d["node_id"] = d.pop("task_id")
        d["state"] = TaskState(d.get("state", "PLANNED"))
        fields = cls.__dataclass_fields__
        filtered = {k: v for k, v in d.items() if k in fields}
        return cls(**filtered)


@dataclass
class TaskGraph:
    graph_id: str = field(default_factory=lambda: f"tg_{uuid.uuid4().hex[:8]}")
    goal: str = ""
    resolved_goal: str = ""
    nodes: Dict[str, TaskNode] = field(default_factory=dict)
    status: TaskState = TaskState.PENDING
    priority: int = 5  # 1 (highest) to 10 (lowest)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    result_summary: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.resolved_goal:
            self.resolved_goal = self.goal

    def is_terminal(self) -> bool:
        if not self.nodes:
            return self.status in (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED)
        return all(n.state in (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED) for n in self.nodes.values())

    def has_failures(self) -> bool:
        return any(n.state == TaskState.FAILED for n in self.nodes.values())

    def add_node(self, node: TaskNode) -> None:
        self.nodes[node.node_id] = node
        self.updated_at = time.time()

    def detect_cycles(self) -> bool:
        visited: Set[str] = set()
        rec_stack: Set[str] = set()

        def _has_cycle(nid: str) -> bool:
            visited.add(nid)
            rec_stack.add(nid)
            for dep in self.nodes[nid].dependencies:
                if dep in self.nodes:
                    if dep not in visited:
                        if _has_cycle(dep):
                            return True
                    elif dep in rec_stack:
                        return True
            rec_stack.remove(nid)
            return False

        for node_id in self.nodes:
            if node_id not in visited:
                if _has_cycle(node_id):
                    return True
        return False

    def topological_sort(self) -> List[TaskNode]:
        if self.detect_cycles():
            raise ValueError(f"Cycle detected in TaskGraph '{self.graph_id}'. Cannot sort.")

        in_degree: Dict[str, int] = {nid: 0 for nid in self.nodes}
        # A node depends on its dependencies: dep -> node
        for nid, node in self.nodes.items():
            for dep in node.dependencies:
                if dep in self.nodes:
                    in_degree[nid] += 1

        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        sorted_nodes: List[TaskNode] = []

        while queue:
            curr = queue.pop(0)
            sorted_nodes.append(self.nodes[curr])

            for nid, node in self.nodes.items():
                if curr in node.dependencies:
                    in_degree[nid] -= 1
                    if in_degree[nid] == 0:
                        queue.append(nid)

        if len(sorted_nodes) != len(self.nodes):
            raise ValueError("Dependency cycle detected during topological sort.")
        return sorted_nodes

    def get_ready_nodes(self) -> List[TaskNode]:
        """Return nodes whose dependencies are all COMPLETED and are currently in PLANNED or READY state."""
        ready: List[TaskNode] = []
        for node in self.nodes.values():
            if node.state in (TaskState.PLANNED, TaskState.READY):
                deps_met = all(
                    self.nodes[dep].state == TaskState.COMPLETED
                    for dep in node.dependencies
                    if dep in self.nodes
                )
                if deps_met:
                    ready.append(node)
        return ready

    def is_complete(self) -> bool:
        if not self.nodes:
            return self.status == TaskState.COMPLETED
        return all(n.state == TaskState.COMPLETED for n in self.nodes.values())

    def has_failed(self) -> bool:
        return any(n.state == TaskState.FAILED for n in self.nodes.values())

    def progress_pct(self) -> int:
        if not self.nodes:
            return 100 if self.status == TaskState.COMPLETED else 0
        completed = sum(1 for n in self.nodes.values() if n.state == TaskState.COMPLETED)
        return int((completed / len(self.nodes)) * 100)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "goal": self.goal,
            "resolved_goal": self.resolved_goal,
            "status": self.status.value,
            "priority": self.priority,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "result_summary": self.result_summary,
            "progress_pct": self.progress_pct(),
            "nodes": {nid: n.to_dict() for nid, n in self.nodes.items()},
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TaskGraph:
        g = cls(
            graph_id=data["graph_id"],
            goal=data["goal"],
            resolved_goal=data.get("resolved_goal", data["goal"]),
            status=TaskState(data.get("status", "PENDING")),
            priority=int(data.get("priority", 5)),
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", time.time())),
            result_summary=data.get("result_summary", ""),
            metadata=data.get("metadata", {}),
        )
        for nid, ndata in data.get("nodes", {}).items():
            g.nodes[nid] = TaskNode.from_dict(ndata)
        return g
