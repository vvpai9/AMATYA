"""
actions/workflow_engine.py — Adaptive Workflow & Routine Automation for AMATYA.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from core import outcome
from core.proactive_engine import get_proactive_engine
from core.workflow_engine import WorkflowRoutine, get_workflow_engine

SKILL_METADATA = {
    "name": "workflow_engine",
    "version": "1.0.0",
    "description": (
        "Manage, learn, trigger, and execute multi-step user workflows and routines "
        "with explicit human approval gates and proactive status checks."
    ),
    "capabilities": [
        "workflow_orchestration",
        "routine_automation",
        "approval_gating",
        "proactive_notifications",
    ],
    "permissions": ["system_control"],
    "dependencies": [],
    "supported_actions": [
        "list_workflows",
        "execute_workflow",
        "register_routine",
        "approve_routine",
        "delete_workflow",
        "check_proactive",
        "dismiss_notification",
    ],
    "security_level": "normal",
}

TOOL = {
    "name": "workflow_engine",
    "description": (
        "Inspect, register, execute, or approve adaptive multi-step workflows and "
        "proactive routines. Actions: 'list_workflows', 'execute_workflow', 'register_routine', "
        "'approve_routine', 'delete_workflow', 'check_proactive', 'dismiss_notification'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "Action: 'list_workflows', 'execute_workflow', 'register_routine', "
                    "'approve_routine', 'delete_workflow', 'check_proactive', or 'dismiss_notification'."
                ),
            },
            "workflow_id": {
                "type": "STRING",
                "description": "Identifier of the workflow or routine to operate on.",
            },
            "name": {
                "type": "STRING",
                "description": "Human-readable name of the workflow/routine.",
            },
            "description": {
                "type": "STRING",
                "description": "Description of what the workflow accomplishes.",
            },
            "trigger_type": {
                "type": "STRING",
                "description": "Trigger type: 'schedule', 'event', 'sensor', 'manual'.",
            },
            "trigger_config": {
                "type": "OBJECT",
                "description": "Configuration dictionary for trigger (e.g. {'cron': '0 8 * * *'}).",
            },
            "actions": {
                "type": "ARRAY",
                "items": {"type": "OBJECT"},
                "description": "List of action step specifications.",
            },
            "notification_id": {
                "type": "STRING",
                "description": "Notification ID to dismiss for 'dismiss_notification'.",
            },
        },
        "required": ["action"],
    },
}


def execute(
    parameters: dict[str, Any],
    response=None,
    player=None,
    session_memory=None,
) -> Any:
    action = str(parameters.get("action", "list_workflows") or "list_workflows").strip().lower()
    wf_engine = get_workflow_engine()
    proactive = get_proactive_engine()

    if action in ("list_workflows", "list"):
        wfs = wf_engine.list_workflows()
        lines = []
        for w in wfs:
            appr = "Approved" if w["requires_approval"] is False or w.get("approved_by_user") else "Needs Approval"
            en = "Active" if w["enabled"] else "Disabled"
            lines.append(f"- [{w['id']}] {w['name']} ({w['trigger_type']}, {en}, {appr}): {len(w['actions'])} steps")
        summary = "\n".join(lines) if lines else "No routines or workflows registered."
        return outcome.done(
            "workflow_engine",
            result=f"Registered Workflows ({len(wfs)}):\n{summary}",
            data={"workflows": wfs},
        )

    if action in ("execute_workflow", "run", "execute"):
        wid = str(parameters.get("workflow_id", "") or "").strip()
        if not wid:
            return outcome.failed("workflow_engine", "Parameter 'workflow_id' is required.")
        res = wf_engine.execute_workflow(wid)
        if not res.get("ok"):
            return outcome.failed("workflow_engine", res.get("error", "Execution failed."), data=res)
        return outcome.done(
            "workflow_engine",
            result=f"Workflow '{wid}' executed successfully ({len(res.get('step_results', []))} steps).",
            data=res,
        )

    if action in ("approve_routine", "approve"):
        wid = str(parameters.get("workflow_id", "") or "").strip()
        if not wid:
            return outcome.failed("workflow_engine", "Parameter 'workflow_id' is required.")
        ok, msg = wf_engine.approve_routine(wid)
        return outcome.done("workflow_engine", result=msg) if ok else outcome.failed("workflow_engine", msg)

    if action in ("delete_workflow", "delete", "remove"):
        wid = str(parameters.get("workflow_id", "") or "").strip()
        if not wid:
            return outcome.failed("workflow_engine", "Parameter 'workflow_id' is required.")
        ok, msg = wf_engine.delete_workflow(wid)
        return outcome.done("workflow_engine", result=msg) if ok else outcome.failed("workflow_engine", msg)

    if action in ("register_routine", "register"):
        wid = str(parameters.get("workflow_id", "") or "").strip()
        name = str(parameters.get("name", "") or wid).strip()
        desc = str(parameters.get("description", "") or "").strip()
        trigger_type = str(parameters.get("trigger_type", "manual") or "manual").strip()
        trigger_config = parameters.get("trigger_config") or {}
        acts = parameters.get("actions") or []
        if not wid or not acts:
            return outcome.failed("workflow_engine", "Both 'workflow_id' and 'actions' are required.")
        routine = WorkflowRoutine(
            id=wid,
            name=name,
            description=desc,
            trigger_type=trigger_type,
            trigger_config=trigger_config,
            actions=acts,
            requires_approval=True,
            created_by="user",
        )
        ok, msg = wf_engine.register_routine(routine)
        return outcome.done("workflow_engine", result=msg) if ok else outcome.failed("workflow_engine", msg)

    if action in ("check_proactive", "proactive"):
        notes = proactive.evaluate_proactive_opportunities()
        active = proactive.get_active_alerts()
        lines = [f"[{a.kind.upper()} P{a.priority}] {a.title}: {a.message}" for a in active]
        msg = f"Active Proactive Notifications ({len(active)}):\n" + "\n".join(lines) if lines else "No pending notifications."
        return outcome.done("workflow_engine", result=msg, data={"notifications": [asdict(a) for a in active]})

    if action in ("dismiss_notification", "dismiss"):
        nid = str(parameters.get("notification_id", "") or "").strip()
        if not nid:
            return outcome.failed("workflow_engine", "Parameter 'notification_id' is required.")
        ok = proactive.dismiss_alert(nid)
        return outcome.done("workflow_engine", result=f"Notification '{nid}' dismissed." if ok else f"Notification '{nid}' not found.")

    return outcome.failed("workflow_engine", f"Unknown workflow_engine action '{action}'.")
