"""
actions/whatsapp_connector.py — AMATYA WhatsApp Connector Action.
================================================================
Exposes WhatsApp capabilities as an auto-discovered AMATYA action:
  - 'send_message': send text message to phone number or contact
  - 'send_file': share Kundali image, report, or presentation
  - 'notify': autonomous task completion notification
"""
from __future__ import annotations

from typing import Any

from core import outcome
from core.whatsapp import get_whatsapp_manager

SKILL_METADATA = {
    "name": "whatsapp_connector",
    "version": "1.0.0",
    "description": (
        "Send messages, Kundali charts, presentations, reports, and autonomous "
        "notifications via WhatsApp Web and Desktop."
    ),
    "capabilities": [
        "whatsapp_messaging",
        "whatsapp_file_share",
        "autonomous_whatsapp_notifications",
    ],
    "permissions": ["network", "browser_control"],
    "dependencies": [],
    "supported_actions": [
        "send_message",
        "send_file",
        "notify",
    ],
    "security_level": "normal",
}

TOOL = {
    "name": "whatsapp_connector",
    "description": (
        "Send WhatsApp messages, files, and autonomous alerts. Actions: "
        "'send_message' (send text to recipient), "
        "'send_file' (send file_path such as Kundali image or PPT to recipient), "
        "'notify' (send autonomous task completion alert to user)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "Action: 'send_message', 'send_file', or 'notify'.",
            },
            "recipient": {
                "type": "STRING",
                "description": "Recipient phone number with country code (e.g. '+919876543210') or contact name.",
            },
            "message": {
                "type": "STRING",
                "description": "Message text to send.",
            },
            "file_path": {
                "type": "STRING",
                "description": "File path for send_file (e.g. Kundali PNG or PPTX).",
            },
            "title": {
                "type": "STRING",
                "description": "Notification title for action='notify'.",
            },
        },
        "required": ["action"],
    },
    "handler": None,
}


def whatsapp_connector(parameters: dict[str, Any] | None = None, **kwargs: Any) -> str:
    params = dict(parameters or {})
    if kwargs:
        params.update(kwargs)

    action = str(params.get("action", "send_message") or "send_message").strip().lower()
    recipient = str(params.get("recipient") or params.get("to") or "").strip()
    msg = str(params.get("message") or params.get("text") or "").strip()

    mgr = get_whatsapp_manager()

    if action in ("send_message", "message", "send"):
        if not msg:
            return outcome.failed("whatsapp_connector", "Message text is required.")
        res = mgr.send_message(recipient=recipient, message=msg)
        if res.get("ok"):
            return outcome.done(
                "whatsapp_connector",
                result=f"WhatsApp message dispatched to {recipient or 'active chat'}: '{msg[:60]}...'",
                data=res,
            )
        return outcome.failed("whatsapp_connector", res.get("error", "Failed to send WhatsApp message"))

    if action in ("send_file", "share_file", "send_kundali"):
        fp = str(params.get("file_path") or params.get("path") or "").strip()
        if not fp:
            return outcome.failed("whatsapp_connector", "File path is required.")
        res = mgr.send_file(recipient=recipient, file_path=fp, caption=msg)
        if res.get("ok"):
            return outcome.done(
                "whatsapp_connector",
                result=f"File '{fp}' prepared for WhatsApp delivery to {recipient or 'active chat'}.",
                data=res,
            )
        return outcome.failed("whatsapp_connector", res.get("error", "Failed to send file on WhatsApp"))

    if action in ("notify", "autonomous_notify"):
        title = str(params.get("title") or "Task Completed").strip()
        res = mgr.send_autonomous_notification(title=title, details=msg, recipient=recipient)
        return outcome.done(
            "whatsapp_connector",
            result=f"Autonomous notification sent via WhatsApp: {title}",
            data=res,
        )

    return outcome.failed("whatsapp_connector", f"Unknown action: {action}")


TOOL["handler"] = whatsapp_connector
