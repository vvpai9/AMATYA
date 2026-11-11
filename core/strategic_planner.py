"""
core/strategic_planner.py — Strategic Planning, Critical Path Method (CPM) & CREATOR Integration for AMATYA Phase 14.

Provides deterministic project dependency graph scheduling, Critical Path Method (CPM) analysis,
Early/Late schedule computation, float/slack quantification, resource bottleneck identification,
and tight integration with CREATOR engineering workflows.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class PlannedTask:
    id: str
    name: str
    duration: float  # days or hours
    predecessors: List[str] = field(default_factory=list)
    resource_demands: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Calculated schedule attributes
    early_start: float = 0.0
    early_finish: float = 0.0
    late_start: float = 0.0
    late_finish: float = 0.0
    total_slack: float = 0.0
    is_critical: bool = False


@dataclass
class SchedulePlan:
    project_name: str
    total_duration: float
    critical_path: List[str]
    tasks: Dict[str, PlannedTask]
    bottlenecks: List[Dict[str, Any]] = field(default_factory=list)
    summary_markdown: str = ""
    mermaid_gantt: str = ""


class StrategicPlanner:
    """
    AMATYA Strategic Planner & Project Scheduler.
    Implements Critical Path Method (CPM) with topological dependency validation.
    """

    def __init__(self):
        pass

    def compute_schedule(
        self,
        project_name: str,
        tasks: List[PlannedTask],
        resource_capacities: Optional[Dict[str, float]] = None,
    ) -> SchedulePlan:
        """
        Calculates Early Start (ES), Early Finish (EF), Late Start (LS), Late Finish (LF),
        total float, critical path, and resource bottlenecks.
        """
        task_dict: Dict[str, PlannedTask] = {t.id: t for t in tasks}
        if not task_dict:
            return SchedulePlan(project_name, 0.0, [], {}, summary_markdown="No tasks provided.")

        # Build successor map and check for cycles (topological sort)
        successors: Dict[str, List[str]] = {t_id: [] for t_id in task_dict}
        in_degree: Dict[str, int] = {t_id: 0 for t_id in task_dict}

        for t_id, task in task_dict.items():
            for p_id in task.predecessors:
                if p_id in successors:
                    successors[p_id].append(t_id)
                    in_degree[t_id] += 1
                else:
                    raise ValueError(f"Task '{t_id}' references unknown predecessor '{p_id}'")

        # Kahn's algorithm for topological ordering
        queue = [t_id for t_id, deg in in_degree.items() if deg == 0]
        topo_order: List[str] = []

        while queue:
            curr = queue.pop(0)
            topo_order.append(curr)
            for succ in successors[curr]:
                in_degree[succ] -= 1
                if in_degree[succ] == 0:
                    queue.append(succ)

        if len(topo_order) != len(task_dict):
            raise ValueError("Dependency cycle detected in project task graph! CPM requires a DAG.")

        # --- Forward Pass (Early Start, Early Finish) ---
        for t_id in topo_order:
            task = task_dict[t_id]
            if not task.predecessors:
                task.early_start = 0.0
            else:
                task.early_start = max(task_dict[p_id].early_finish for p_id in task.predecessors)
            task.early_finish = task.early_start + max(0.0, task.duration)

        # Total project duration
        total_duration = max(t.early_finish for t in task_dict.values())

        # --- Backward Pass (Late Finish, Late Start) ---
        for t_id in reversed(topo_order):
            task = task_dict[t_id]
            succ_list = successors[t_id]
            if not succ_list:
                task.late_finish = total_duration
            else:
                task.late_finish = min(task_dict[s_id].late_start for s_id in succ_list)
            task.late_start = task.late_finish - max(0.0, task.duration)

            # Slack & Critical Path
            task.total_slack = round(task.late_start - task.early_start, 4)
            task.is_critical = abs(task.total_slack) < 1e-4

        critical_path = [t_id for t_id in topo_order if task_dict[t_id].is_critical]

        # --- Resource Bottleneck Analysis ---
        bottlenecks: List[Dict[str, Any]] = []
        if resource_capacities:
            # Check resource contention at task change points
            time_points = sorted(list(set(
                [t.early_start for t in task_dict.values()] +
                [t.early_finish for t in task_dict.values()]
            )))

            for i in range(len(time_points) - 1):
                t_mid = (time_points[i] + time_points[i + 1]) / 2.0
                active_tasks = [
                    t for t in task_dict.values()
                    if t.early_start <= t_mid < t.early_finish
                ]

                # Tally resources
                usage: Dict[str, float] = {}
                for at in active_tasks:
                    for res_name, res_amt in at.resource_demands.items():
                        usage[res_name] = usage.get(res_name, 0.0) + res_amt

                for res_name, capacity in resource_capacities.items():
                    current_usage = usage.get(res_name, 0.0)
                    if current_usage > capacity:
                        bottlenecks.append({
                            "resource": res_name,
                            "time_interval": [time_points[i], time_points[i + 1]],
                            "demand": current_usage,
                            "capacity": capacity,
                            "competing_tasks": [at.id for at in active_tasks if res_name in at.resource_demands],
                        })

        # --- Generate Mermaid Gantt Diagram ---
        mermaid_lines = ["```mermaid", "gantt", f"    title {project_name} CPM Schedule", "    dateFormat X", "    axisFormat %s"]
        for t_id in topo_order:
            t = task_dict[t_id]
            crit_flag = "crit, " if t.is_critical else ""
            mermaid_lines.append(f"    {t.name} :{crit_flag}{t.id}, {int(t.early_start)}, {int(t.early_finish)}")
        mermaid_lines.append("```")
        mermaid_gantt = "\n".join(mermaid_lines)

        # --- Build Markdown Summary ---
        md_lines = [
            f"# Strategic Project Schedule: {project_name}",
            "",
            f"- **Total Duration:** `{total_duration:.2f}` units",
            f"- **Critical Path:** `{' -> '.join(critical_path)}`",
            f"- **Total Tasks:** {len(task_dict)}",
            "",
            "### Task Schedule & Float Analysis:",
            "| ID | Task | Duration | Predecessors | Early Start | Early Finish | Late Start | Late Finish | Slack | Critical |",
            "|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|",
        ]
        for t_id in topo_order:
            t = task_dict[t_id]
            preds = ", ".join(t.predecessors) if t.predecessors else "None"
            crit_badge = "🔴 **CRITICAL**" if t.is_critical else "🟢 Normal"
            md_lines.append(
                f"| `{t.id}` | {t.name} | {t.duration:.1f} | {preds} | {t.early_start:.1f} | {t.early_finish:.1f} | "
                f"{t.late_start:.1f} | {t.late_finish:.1f} | {t.total_slack:.1f} | {crit_badge} |"
            )

        if bottlenecks:
            md_lines.extend([
                "",
                "### ⚠️ Resource Bottlenecks Detected:",
                "| Resource | Interval | Demand / Capacity | Competing Tasks |",
                "|:---|:---:|:---:|:---|",
            ])
            for b in bottlenecks:
                md_lines.append(
                    f"| `{b['resource']}` | [{b['time_interval'][0]:.1f}, {b['time_interval'][1]:.1f}] | "
                    f"**{b['demand']:.1f}** / {b['capacity']:.1f} | {', '.join(b['competing_tasks'])} |"
                )

        return SchedulePlan(
            project_name=project_name,
            total_duration=total_duration,
            critical_path=critical_path,
            tasks=task_dict,
            bottlenecks=bottlenecks,
            summary_markdown="\n".join(md_lines),
            mermaid_gantt=mermaid_gantt,
        )


_strategic_planner: Optional[StrategicPlanner] = None


def get_strategic_planner() -> StrategicPlanner:
    global _strategic_planner
    if _strategic_planner is None:
        _strategic_planner = StrategicPlanner()
    return _strategic_planner

