"""
actions/device_control.py — Connected Devices, Android Phone, Redmi TV & SSH Control for AMATYA.
"""
from __future__ import annotations

from typing import Any

from core import outcome
from core.device_manager import get_device_manager

SKILL_METADATA = {
    "name": "device_control",
    "version": "1.0.0",
    "description": "Discover and control connected devices (Android phone via KDE Connect/ADB, Redmi Android TV via ADB over LAN, and remote Linux computers via SSH/SCP).",
    "capabilities": [
        "network_discovery",
        "android_phone_integration",
        "android_tv_control",
        "remote_ssh_execution",
        "file_transfer",
    ],
    "permissions": ["network", "device_control", "file_read"],
    "dependencies": [],
    "supported_actions": [
        "discover",
        "register",
        "send_file",
        "ring_phone",
        "share_clipboard",
        "phone_status",
        "phone_launch_app",
        "tv_key",
        "tv_power",
        "tv_volume",
        "tv_launch_app",
        "tv_cast_url",
        "tv_status",
        "ssh_exec",
        "ssh_transfer",
        "ssh_status",
    ],
    "security_level": "high",
}

TOOL = {
    "name": "device_control",
    "description": (
        "AMATYA Connected Devices & Network Control subsystem. Discover LAN/"
        "Tailscale/KDE Connect/ADB devices; transfer files to your Android phone "
        "('send_file'), ring phone ('ring_phone'), share clipboard, check phone "
        "battery/status; control Redmi Android TV ('tv_key', 'tv_volume', "
        "'tv_launch_app', 'tv_cast_url', 'tv_status'); monitor or transfer files "
        "to remote computers via SSH ('ssh_status', 'ssh_exec', 'ssh_transfer')."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "Action: 'discover', 'register', 'send_file', 'ring_phone', "
                    "'share_clipboard', 'phone_status', 'phone_launch_app', "
                    "'tv_key', 'tv_volume', 'tv_launch_app', 'tv_cast_url', "
                    "'tv_status', 'ssh_exec', 'ssh_transfer', 'ssh_status'."
                ),
            },
            "device": {
                "type": "STRING",
                "description": "Target device ID or name ('phone', 'redmi_tv', 'home_server').",
            },
            "file_path": {
                "type": "STRING",
                "description": "Local file path for 'send_file' or 'ssh_transfer'.",
            },
            "remote_path": {
                "type": "STRING",
                "description": "Remote destination path for 'ssh_transfer'.",
            },
            "text": {
                "type": "STRING",
                "description": "Text content for 'share_clipboard'.",
            },
            "app_name": {
                "type": "STRING",
                "description": "App name to launch on phone or TV (e.g. 'youtube', 'netflix', 'vlc').",
            },
            "key_command": {
                "type": "STRING",
                "description": "TV remote key ('power', 'home', 'back', 'up', 'down', 'left', 'right', 'select', 'mute', 'play_pause', 'tv_input').",
            },
            "volume_pct": {
                "type": "INTEGER",
                "description": "Volume percentage (0-100) for 'tv_volume'.",
            },
            "media_url": {
                "type": "STRING",
                "description": "Media URL to cast or open on the TV.",
            },
            "remote_command": {
                "type": "STRING",
                "description": "Shell command to run on remote SSH host.",
            },
            "ip_address": {"type": "STRING"},
            "device_type": {"type": "STRING"},
            "authorized": {"type": "BOOLEAN"},
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
    action = str(parameters.get("action", "discover") or "discover").strip().lower()
    mgr = get_device_manager()
    dev_target = str(parameters.get("device", "") or "").strip()

    if action in ("discover", "scan", "list_network", "scan_network"):
        res = mgr.discover_devices()
        dev_table = res.get("device_table", [])
        if dev_table:
            table_str = "\n".join(dev_table)
        else:
            table_str = "No dynamic devices discovered."
        return outcome.done("device_control", result=table_str, data=res)

    if action == "register":
        did = dev_target or str(parameters.get("device_id", "") or "").strip()
        ok, msg = mgr.register_or_authorize(
            device_id=did,
            name=parameters.get("name"),
            device_type=str(parameters.get("device_type", "android_phone")),
            ip_address=str(parameters.get("ip_address", "")),
            authorized=bool(parameters.get("authorized", True)),
        )
        return outcome.done("device_control", result=msg) if ok else outcome.failed("device_control", msg)

    # Phone actions
    if action in ("send_file", "ring_phone", "share_clipboard", "phone_status", "phone_launch_app"):
        sub_map = {
            "send_file": "send_file",
            "ring_phone": "ring",
            "share_clipboard": "share_clipboard",
            "phone_status": "status",
            "phone_launch_app": "launch_app",
        }
        res = mgr.phone_action(
            sub_action=sub_map[action],
            device_query=dev_target or "phone",
            file_path=parameters.get("file_path"),
            text=parameters.get("text"),
            app_name=parameters.get("app_name"),
        )
        if not res.get("ok"):
            return outcome.failed("device_control", res.get("error", "Phone action failed."), data=res)
        msg = res.get("message") or (
            f"{res['mode_label']} {res['device']}: battery={res['status'].get('battery_pct')}%"
        )
        return outcome.done("device_control", result=msg, data=res)

    # TV actions
    if action in ("tv_key", "tv_power", "tv_volume", "tv_launch_app", "tv_cast_url", "tv_status"):
        sub_map = {
            "tv_key": "key",
            "tv_power": "key",
            "tv_volume": "set_volume",
            "tv_launch_app": "launch_app",
            "tv_cast_url": "cast_url",
            "tv_status": "status",
        }
        k_cmd = "power" if action == "tv_power" else parameters.get("key_command")
        res = mgr.tv_action(
            sub_action=sub_map[action],
            device_query=dev_target or "redmi_tv",
            key_command=k_cmd,
            app_name=parameters.get("app_name"),
            media_url=parameters.get("media_url"),
            volume_pct=parameters.get("volume_pct"),
        )
        if not res.get("ok"):
            return outcome.failed("device_control", res.get("error", "TV action failed."), data=res)
        st = res.get("status", {})
        msg = (
            f"{res['mode_label']} {res['device']}: power={st.get('power')}, "
            f"app={st.get('current_app')}, volume={st.get('volume_pct')}%."
        )
        return outcome.done("device_control", result=msg, data=res)

    # SSH actions
    if action in ("ssh_exec", "ssh_transfer", "ssh_status"):
        sub_map = {
            "ssh_exec": "exec",
            "ssh_transfer": "transfer_file",
            "ssh_status": "status",
        }
        res = mgr.ssh_action(
            sub_action=sub_map[action],
            device_query=dev_target or "home_server",
            remote_command=parameters.get("remote_command"),
            local_path=parameters.get("file_path"),
            remote_path=parameters.get("remote_path"),
        )
        if not res.get("ok"):
            return outcome.failed("device_control", res.get("error", "SSH action failed."), data=res)
        msg = res.get("message") or res.get("stdout") or f"{res['mode_label']} {res.get('host')}: {res.get('status')}"
        return outcome.done("device_control", result=msg, data=res)

    return outcome.failed("device_control", f"Unknown device_control action '{action}'.")

