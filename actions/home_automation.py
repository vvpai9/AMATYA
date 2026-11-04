"""
actions/home_automation.py — Smart Home Automation, Device Registry & Routines for AMATYA.
"""
from __future__ import annotations

from typing import Any

from core import outcome
from core.home_automation import get_home_controller

SKILL_METADATA = {
    "name": "home_automation",
    "version": "1.0.0",
    "description": "Control smart home lights, fans, AC, plugs, TVs, locks, security systems, sensors, and routines via Home Assistant, MQTT, Matter/Zigbee/Tuya/Shelly/ESPHome, or the Simulated Home Environment.",
    "capabilities": [
        "device_control",
        "state_verification",
        "routines_engine",
        "environmental_telemetry",
        "home_assistant_integration",
        "mqtt_integration",
    ],
    "permissions": ["network", "device_control"],
    "dependencies": ["paho-mqtt", "tinytuya"],
    "supported_actions": [
        "status",
        "list_devices",
        "control_device",
        "run_routine",
        "list_routines",
        "save_routine",
        "register_device",
        "environment",
        "configure",
    ],
    "security_level": "high",
}

TOOL = {
    "name": "home_automation",
    "description": (
        "AMATYA Smart Home Automation subsystem. Control lights, fans, switches, "
        "AC/climate, appliances, Redmi TV, locks, and security systems with "
        "post-command state verification; execute routines ('morning', 'evening', "
        "'leaving_home', 'returning_home', 'sleep'); read environmental sensors. "
        "Clearly distinguishes live Home Assistant from the Simulated Home "
        "Environment. Actions: 'status', 'list_devices', 'control_device', "
        "'run_routine', 'list_routines', 'save_routine', 'register_device', "
        "'environment', 'configure'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "Action: 'status', 'list_devices', 'control_device', "
                    "'run_routine', 'list_routines', 'save_routine', "
                    "'register_device', 'environment', 'configure'."
                ),
            },
            "target": {
                "type": "STRING",
                "description": "Device entity_id or natural name (e.g. 'living room lights', 'light.living_room_main', 'study ac', 'front door').",
            },
            "command": {
                "type": "STRING",
                "description": "Command: 'turn_on', 'turn_off', 'toggle', 'set_temperature', 'set_speed', 'lock', 'unlock', 'arm_away', 'arm_home', 'disarm'.",
            },
            "room": {
                "type": "STRING",
                "description": "Filter devices by room (e.g. 'living_room', 'study', 'bedroom').",
            },
            "device_type": {
                "type": "STRING",
                "description": "Filter devices by type ('light', 'fan', 'climate', 'lock', 'sensor').",
            },
            "brightness_pct": {"type": "INTEGER"},
            "temperature_c": {"type": "NUMBER"},
            "speed_pct": {"type": "INTEGER"},
            "routine_name": {
                "type": "STRING",
                "description": "Routine name ('morning', 'evening', 'leaving_home', 'returning_home', 'sleep').",
            },
            "confirmed": {
                "type": "BOOLEAN",
                "description": "Set True if user explicitly confirmed a sensitive routine.",
            },
            "pin": {
                "type": "STRING",
                "description": "Optional security PIN for critical lock/security operations.",
            },
            "include_cameras": {
                "type": "BOOLEAN",
                "description": "Explicit opt-in to include camera state in environmental check.",
            },
            "ha_url": {"type": "STRING", "description": "Home Assistant URL (e.g. 'http://homeassistant.local:8123')."},
            "ha_token": {"type": "STRING", "description": "Home Assistant Long-Lived Access Token."},
            "mqtt_host": {"type": "STRING", "description": "MQTT broker hostname or IP."},
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
    action = str(parameters.get("action", "status") or "status").strip().lower()
    ctrl = get_home_controller()

    if action in ("status", "environment"):
        inc_cam = bool(parameters.get("include_cameras", False))
        env = ctrl.get_environment_summary(include_cameras=inc_cam)
        tel = env["telemetry"]
        lights = ", ".join(env["active_lights"]) if env["active_lights"] else "none"
        summary = (
            f"{env['mode_label']} Temperature: {tel.get('temperature_c')}°C, "
            f"Humidity: {tel.get('humidity_pct')}%, Power: {tel.get('power_consumption_w')}W, "
            f"Front Door: {env['front_door_lock']} ({tel.get('front_door_contact')}), "
            f"Security: {env['security_system']}, Active Lights: {lights}."
        )
        return outcome.done(summary, data=env)

    if action == "list_devices":
        res = ctrl.list_devices(
            room=parameters.get("room"),
            device_type=parameters.get("device_type"),
        )
        lines = [
            f"- {d['name']} ({d['entity_id']}, room={d['room']}): state={d['state']}"
            for d in res["devices"]
        ]
        summary = f"{res['mode_label']} {res['count']} device(s):\n" + "\n".join(lines)
        return outcome.done(summary, data=res)

    if action == "control_device":
        target = str(parameters.get("target", "") or "").strip()
        cmd = str(parameters.get("command", "turn_on") or "turn_on").strip()
        if not target:
            return outcome.failed("Please specify 'target' device to control.")
        extra_params: dict[str, Any] = {}
        for k in ("brightness_pct", "temperature_c", "speed_pct"):
            if parameters.get(k) is not None:
                extra_params[k] = parameters[k]
        res = ctrl.control_device(
            target=target,
            command=cmd,
            params=extra_params,
            pin=parameters.get("pin"),
        )
        if not res.get("ok"):
            return outcome.failed(res.get("error", f"Failed to control '{target}'."), data=res)
        msg = (
            f"{res['mode_label']} {res['name']} ({res['entity_id']}) → state='{res['state']}' "
            f"(verified={res['verified']})."
        )
        if res.get("verified"):
            return outcome.done(msg, data=res)
        return outcome.unverified(msg, data=res)

    if action == "list_routines":
        routines = ctrl.list_routines()
        lines = [f"- {k}: {v.get('description', '')}" for k, v in routines.items()]
        return outcome.done(
            f"Configured Home Routines ({len(routines)}):\n" + "\n".join(lines),
            data={"routines": routines},
        )

    if action == "run_routine":
        rname = str(parameters.get("routine_name") or parameters.get("target") or "").strip()
        if not rname:
            return outcome.failed("Please provide 'routine_name' (e.g. 'morning', 'leaving_home', 'sleep').")
        res = ctrl.execute_routine(
            routine_name=rname,
            confirmed=bool(parameters.get("confirmed", False)),
            pin=parameters.get("pin"),
        )
        if not res.get("ok"):
            return outcome.failed(res.get("error", f"Routine '{rname}' could not run."), data=res)
        msg = (
            f"{res['mode_label']} Executed routine '{res['name']}' "
            f"({len(res['results'])} device actions, all_verified={res['verified']})."
        )
        return outcome.done(msg, data=res) if res.get("verified") else outcome.unverified(msg, data=res)

    if action == "register_device":
        ok, msg = ctrl.register_device(parameters)
        return outcome.done(msg) if ok else outcome.failed(msg)

    if action == "configure":
        res = ctrl.configure_connection(
            ha_url=parameters.get("ha_url"),
            ha_token=parameters.get("ha_token"),
            mqtt_host=parameters.get("mqtt_host"),
        )
        return outcome.done(f"Home Automation connection status: {res['mode_label']}", data=res)

    return outcome.failed(f"Unknown home_automation action '{action}'.")
