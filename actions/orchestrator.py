"""
actions/orchestrator.py — Central Intelligence, Context Resolver & Multi-Step Orchestrator for AMATYA.
"""
from __future__ import annotations

from typing import Any

from core import outcome
from core.orchestrator import TaskRecord, get_orchestrator

SKILL_METADATA = {
    "name": "orchestrator",
    "version": "1.0.0",
    "description": "Resolve contextual references ('Open that', 'Close the previous window', 'Send that file to my phone'), plan and execute multi-step workflows, manage task queue priorities, and trigger emergency stop.",
    "capabilities": [
        "contextual_reference_resolution",
        "multi_step_planning",
        "task_prioritization",
        "emergency_stop",
    ],
    "permissions": ["orchestration"],
    "dependencies": [],
    "supported_actions": [
        "resolve_context",
        "get_context",
        "update_context",
        "plan_and_execute",
        "resume_last_task",
        "multitask",
        "list_tasks",
        "emergency_stop",
    ],
    "security_level": "normal",
}

TOOL = {
    "name": "orchestrator",
    "description": (
        "AMATYA Central Orchestrator & Contextual Reference Resolver. Resolves "
        "pronouns and contextual references ('Open that', 'Close the previous "
        "window', 'Continue what you were doing', 'Check the same project again', "
        "'Send that file to my phone'), plans and executes multi-step cross-domain "
        "workflows, runs multiple simultaneous tasks concurrently with voice updates (multitask), "
        "lists active/prioritized tasks, and supports emergency_stop. "
        "Actions: 'resolve_context', 'get_context', 'update_context', "
        "'plan_and_execute', 'resume_last_task', 'multitask', 'list_tasks', 'emergency_stop'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "Action: 'resolve_context', 'get_context', 'update_context', "
                    "'plan_and_execute', 'resume_last_task', 'multitask', 'list_tasks', 'emergency_stop'."
                ),
            },
            "instruction": {
                "type": "STRING",
                "description": "Natural language instruction or contextual command.",
            },
            "tasks": {
                "type": "ARRAY",
                "items": {"type": "STRING"},
                "description": "List of task instructions to execute simultaneously in parallel (for action='multitask').",
            },
            "priority": {
                "type": "INTEGER",
                "description": "Task priority from 1 (highest) to 10 (lowest), default 5.",
            },
            "last_file": {"type": "STRING"},
            "last_project": {"type": "STRING"},
            "last_app": {"type": "STRING"},
            "last_device": {"type": "STRING"},
            "window_id": {"type": "STRING"},
            "window_title": {"type": "STRING"},
        },
        "required": ["action"],
    },
}


def execute(
    parameters: dict[str, Any],
    response=None,
    player=None,
    session_memory=None,
    speak=None,
    **kwargs,
) -> Any:
    action = str(parameters.get("action", "get_context") or "get_context").strip().lower()
    orch = get_orchestrator()

    if action == "get_context":
        st = orch.context.get_state()
        return outcome.done(
            f"Active Context: file='{st.get('last_file')}', project='{st.get('last_project')}', "
            f"app='{st.get('last_app')}', prev_window='{st.get('previous_window_title') or st.get('previous_window_id')}', "
            f"device='{st.get('last_device')}'.",
            data=st,
        )

    if action == "update_context":
        updates = {
            k: parameters[k]
            for k in ("last_file", "last_project", "last_app", "last_device", "window_id", "window_title")
            if k in parameters and parameters[k] is not None
        }
        st = orch.context.update_entity(**updates)
        return outcome.done("orchestrator", result="Updated operational context.", data=st)

    if action == "resolve_context":
        instr = str(parameters.get("instruction", "") or "").strip()
        if not instr:
            return outcome.failed("orchestrator", "Please provide 'instruction' to resolve.")
        res = orch.context.resolve_references(instr)
        return outcome.done(
            "orchestrator",
            result=f"Resolved '{res['original']}' → '{res['resolved']}'",
            data=res,
        )

    if action == "plan_and_execute":
        instr = str(parameters.get("instruction", "") or "").strip()
        if not instr:
            return outcome.failed("orchestrator", "Please provide 'instruction' to plan and execute.")
        prio = int(parameters.get("priority", 5) or 5)
        task = orch.plan_workflow(instr, priority=prio)
        completed = orch.execute_task(task)
        if completed.status == "completed":
            return outcome.done(
                "orchestrator",
                result=f"Executed workflow '{completed.resolved_goal}': {completed.result_summary}",
                data=completed.to_dict(),
            )
        return outcome.failed(
            "orchestrator",
            f"Workflow '{completed.resolved_goal}' ended with status '{completed.status}': {completed.result_summary}",
            data=completed.to_dict(),
        )

    if action == "resume_last_task":
        st = orch.context.get_state()
        lt = st.get("last_task")
        if not isinstance(lt, dict) or not lt.get("goal"):
            return outcome.failed("orchestrator", "No previous task found in context to resume.")
        task = TaskRecord(
            task_id=str(lt.get("task_id", "resumed")),
            goal=str(lt.get("goal", "")),
            resolved_goal=str(lt.get("resolved_goal", lt.get("goal", ""))),
            domain=str(lt.get("domain", "general")),
            priority=int(lt.get("priority", 5)),
            status="pending",
            steps=list(lt.get("steps", [])),
            current_step_index=min(
                int(lt.get("current_step_index", 0)),
                max(0, len(lt.get("steps", [])) - 1),
            ),
        )
        completed = orch.execute_task(task)
        return outcome.done(
            "orchestrator",
            result=f"Resumed task '{completed.resolved_goal}': {completed.result_summary}",
            data=completed.to_dict(),
        )

    if action in ("multitask", "concurrent_tasks"):
        tasks = parameters.get("tasks") or parameters.get("instructions")
        if not tasks and parameters.get("instruction"):
            tasks = [parameters.get("instruction")]
        if isinstance(tasks, str):
            tasks = [t.strip() for t in tasks.split(",") if t.strip()]
        if not isinstance(tasks, list) or not tasks:
            return outcome.failed("orchestrator", "Please provide a list of 'tasks' to run simultaneously.")
        res = orch.run_multitask(tasks, speak=speak or kwargs.get("speak"))
        if res.get("ok"):
            return outcome.done("orchestrator", result=res.get("summary", "Multitasking completed successfully."), data=res)
        return outcome.failed("orchestrator", res.get("summary", "Multitasking encountered issues."), data=res)

    if action in ("task_status", "what_are_you_doing", "status"):
        summary = orch.get_active_task_summary()
        return outcome.done("orchestrator", result=summary, data={"active_tasks": orch.list_tasks()})

    if action == "pause_task":
        tid = str(parameters.get("task_id", "") or "").strip()
        res = orch.pause_task(tid)
        return outcome.done("orchestrator", result=res.get("message", str(res)), data=res) if res.get("ok") else outcome.failed("orchestrator", res.get("error", "Failed to pause task."))

    if action == "cancel_task":
        tid = str(parameters.get("task_id", "") or "").strip()
        res = orch.cancel_task(tid)
        return outcome.done("orchestrator", result=res.get("message", str(res)), data=res) if res.get("ok") else outcome.failed("orchestrator", res.get("error", "Failed to cancel task."))

    if action == "list_tasks":
        tasks = orch.list_tasks()
        return outcome.done(
            "orchestrator",
            result=f"Orchestrator has {len(tasks)} tracked task(s).",
            data={"tasks": tasks},
        )

    if action == "emergency_stop":
        msg = orch.cancel_all()
        return outcome.done("orchestrator", result=msg)

    return outcome.failed("orchestrator", f"Unknown orchestrator action '{action}'.")

