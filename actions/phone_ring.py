"""
actions/phone_ring.py — AMATYA Phone Ringing & Mobile Alert Action.
===================================================================
Provides native phone ring, VoIP calling, and mobile alert capabilities across
Linux, Windows, and macOS:
  - AgentRing (https://github.com/mutonby/agentring) VoIP calls with AI voice
  - KDE Connect (kdeconnect-cli) local LAN/Wi-Fi max volume ringing
  - ADB volume boosting & alarm triggers over Wi-Fi / USB
  - Ntfy.sh open-source HTTP urgent push alerts overriding DND
"""
from __future__ import annotations

import json
from typing import Any

from core import outcome
from core.phone_ring import (
    agentring_call,
    agentring_msg,
    agentring_pair,
    get_kdeconnect_devices,
    get_or_create_ntfy_topic,
    get_phone_ringer,
    kdeconnect_ring,
    ntfy_ring,
)

SKILL_METADATA = {
    "name": "phone_ring",
    "version": "1.0.0",
    "description": (
        "Ring or call the user's mobile phone using AgentRing (VoIP), KDE Connect, ADB, or Ntfy. "
        "Supports 'ring', 'call', 'pair_agentring', 'pair_kdeconnect', 'send_message', and 'status'. "
        "Works seamlessly across Linux, Windows, and macOS."
    ),
    "capabilities": [
        "phone_ringing",
        "voip_calling",
        "find_my_phone",
        "agentring_integration",
        "kdeconnect_ringing",
        "adb_alarm_trigger",
        "ntfy_push_alert",
    ],
    "permissions": ["device_control"],
    "dependencies": ["agentring"],
    "supported_actions": [
        "ring",
        "find_phone",
        "call",
        "pair_agentring",
        "pair_kdeconnect",
        "send_message",
        "status",
    ],
    "security_level": "normal",
}

TOOL = {
    "name": "phone_ring",
    "description": (
        "Ring or call the user's phone. Actions: "
        "'ring' (or 'find_phone') to sound alarm/ringtone on the phone, "
        "'call' to initiate a VoIP voice call via AgentRing, "
        "'pair_agentring' to generate pairing QR/token for the AgentRing Android app, "
        "'send_message' to send a notification message, "
        "'status' to inspect all mobile ring backends."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "Action: 'ring', 'find_phone', 'call', 'pair_agentring', 'send_message', or 'status'.",
            },
            "backend": {
                "type": "STRING",
                "description": "Optional specific backend: 'auto' (default), 'agentring', 'kdeconnect', 'adb', or 'ntfy'.",
            },
            "reason": {
                "type": "STRING",
                "description": "Reason for ringing or calling (e.g. 'AMATYA Find My Phone', 'Emergency Task Finished').",
            },
            "target": {
                "type": "STRING",
                "description": "Optional specific device name, device ID, or IP.",
            },
            "urgent": {
                "type": "BOOLEAN",
                "description": "Whether the call/ring should be urgent and bypass Do Not Disturb (default: true).",
            },
            "message": {
                "type": "STRING",
                "description": "Message text when using 'send_message'.",
            },
        },
        "required": ["action"],
    },
    "handler": None,
}


def phone_ring(parameters: dict[str, Any] | None = None, **kwargs: Any) -> str:
    """Execute phone ringing and calling operations."""
    params = dict(parameters or {})
    if kwargs:
        params.update(kwargs)

    action = str(params.get("action", "ring") or "ring").strip().lower()
    backend = str(params.get("backend", "auto") or "auto").strip().lower()
    reason = str(params.get("reason", "AMATYA Find My Phone") or "AMATYA Find My Phone").strip()
    target = params.get("target")
    urgent = bool(params.get("urgent", True))

    ringer = get_phone_ringer()

    # 1. Status query
    if action in ("status", "diagnostics", "check"):
        st = ringer.status()
        summary_lines = [
            f"✦ AMATYA PHONE RING SUBSYSTEM STATUS ({st['os'].upper()}) ✦",
            f"• AgentRing (VoIP): {'Installed' if st['agentring']['available'] else 'Not Installed'} | "
            f"Configured: {st['agentring']['configured']} (Paired Devices: {st['agentring']['paired_devices_count']})",
            f"• KDE Connect: {'Available' if st['kdeconnect']['available'] else 'Not Found'} | "
            f"Reachable Devices: {len(st['kdeconnect']['devices'])}",
        ]
        for kd in st["kdeconnect"]["devices"]:
            summary_lines.append(f"  - {kd['name']} (ID: {kd['device_id']}) — Reachable: {kd['reachable']}")

        summary_lines.append(f"• ADB: {'Available' if st['adb']['available'] else 'Not Found'}")
        summary_lines.append(f"• Ntfy.sh Web Push: Topic '{st['ntfy']['topic']}' ({st['ntfy']['subscribe_url']})")

        return outcome.done("phone_ring", result="\n".join(summary_lines), data=st)

    # 2. Pair / Init AgentRing
    if action in ("init_agentring", "configure_agentring"):
        relay = str(params.get("relay") or params.get("relay_url") or "").strip()
        api_key = str(params.get("api_key") or params.get("key") or "").strip()
        if not relay or not api_key:
            return outcome.failed(
                "phone_ring",
                "Please provide both 'relay' (URL) and 'api_key' to configure AgentRing.",
            )
        from core.phone_ring import agentring_init
        res_init = agentring_init(relay, api_key)
        if res_init.get("ok"):
            res_pair = agentring_pair()
            msg = f"AgentRing configured successfully with relay {relay}.\n{res_pair.get('instructions', '')}"
            return outcome.done("phone_ring", result=msg, data=res_pair)
        return outcome.failed("phone_ring", reason=res_init.get("error", "AgentRing init failed"))

    if action in ("pair_agentring", "agentring_pair", "pair"):
        res_pair = agentring_pair()
        if res_pair.get("ok"):
            msg = (
                f"✦ AGENTRING PAIRING ✦\n"
                f"{res_pair.get('instructions', '')}\n"
                f"Token: {res_pair.get('qr_payload', '')}"
            )
            return outcome.done("phone_ring", result=msg, data=res_pair)
        return outcome.failed(
            "phone_ring",
            reason=res_pair.get("error", "Failed to initiate AgentRing pairing. Make sure relay is configured: agentring init"),
        )

    # 3. Direct VoIP Call via AgentRing with Automatic Phone Ring Fallback
    if action in ("call", "voip_call", "agentring_call"):
        res_call = agentring_call(reason=reason, urgent=urgent, ai=True)
        if res_call.get("ok"):
            return outcome.done("phone_ring", result=res_call["message"], data=res_call)

        # AgentRing VoIP is unavailable/unconfigured: automatically cascade to ringing the phone
        # via KDE Connect or Ntfy so the user's phone ACTUALLY rings and the alert is received!
        res_ring = ringer.ring(reason=f"Call Request: {reason}", backend="auto", target=target)
        if res_ring.get("ok"):
            call_msg = (
                f"✦ AMATYA PHONE CALL ALERT ✦\n"
                f"• AgentRing VoIP: {res_call.get('error', 'Unconfigured')}\n"
                f"• Fallback: Rang phone immediately via {res_ring.get('backend', 'KDE Connect')} "
                f"({res_ring.get('device', 'Android Phone')}) at max volume so you do not miss this alert!"
            )
            return outcome.done("phone_ring", result=call_msg, data={"call_attempt": res_call, "ring_fallback": res_ring})

        return outcome.failed(
            "phone_ring",
            reason=f"AgentRing call failed ({res_call.get('error')}) and ring fallback failed ({res_ring.get('error')}).",
        )

    # 4. Send Message via AgentRing or Ntfy
    if action in ("send_message", "msg", "push_message"):
        msg_text = str(params.get("message") or reason).strip()
        if backend == "ntfy":
            res_ntfy = ntfy_ring(topic=target, reason=msg_text)
            if res_ntfy.get("ok"):
                return outcome.done("phone_ring", result=res_ntfy["message"], data=res_ntfy)
            return outcome.failed("phone_ring", reason=res_ntfy.get("error", "Ntfy failed"))

        # Default to AgentRing msg
        res_msg = agentring_msg(msg_text)
        if res_msg.get("ok"):
            return outcome.done("phone_ring", result=f"Message sent via AgentRing: {msg_text}", data=res_msg)
        # Fallback to Ntfy
        res_ntfy = ntfy_ring(reason=msg_text)
        if res_ntfy.get("ok"):
            return outcome.done("phone_ring", result=f"Sent push message via Ntfy: {msg_text}", data=res_ntfy)
        return outcome.failed("phone_ring", reason=f"Failed to send message: {res_msg.get('error')}")

    # 5. Ring Phone (Auto-selection or specified backend)
    if action in ("ring", "find_phone", "ring_phone", "sound_alarm"):
        res_ring = ringer.ring(backend=backend, target=target, reason=reason, urgent=urgent)
        if res_ring.get("ok"):
            return outcome.done("phone_ring", result=res_ring["message"], data=res_ring)

        err_detail = (
            f"Failed to ring phone: {res_ring.get('error')}\n\n"
            f"{res_ring.get('pairing_instructions', '')}"
        )
        return outcome.failed("phone_ring", reason=err_detail)

    return outcome.failed(
        "phone_ring",
        reason=f"Unknown action '{action}'. Supported: 'ring', 'call', 'pair_agentring', 'send_message', 'status'.",
    )


TOOL["handler"] = phone_ring
execute = phone_ring

