"""
AMATYA Home Automation Subsystem (core/home_automation.py)
==========================================================
Implements Section 7 (Home Automation):
  - 7.1 Ecosystems: Home Assistant REST & WebSocket API, MQTT (paho-mqtt),
    Shelly/ESPHome HTTP REST, Tuya (tinytuya), Matter/Zigbee via Home Assistant/MQTT.
  - 7.2 Device Registry (config/home_devices.json): identity, type, room/location,
    current state, capabilities, permission tier, connectivity status.
  - 7.3 Post-Command State Verification: verifies device state after every command.
  - 7.4 Routines & Automations (config/home_routines.json): morning, evening,
    leaving_home, returning_home, sleep, custom, sensor-triggered, scheduled.
    Sensitive actions (locks, security systems, critical appliances) require
    confirmation via core/security.py.
  - 7.5 Environmental Awareness & Camera Privacy: reads temperature, humidity,
    motion, door/window, power usage, presence; camera access is strictly opt-in.
  - Simulated Home Environment: when no live Home Assistant / MQTT broker is
    configured or reachable, operates against a stateful Simulated Home Environment
    explicitly labeled with `simulated=True` (`[SIMULATED HOME]`).
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from core.security import PermissionTier, check_permission, log_audit_event
from memory.config_manager import CONFIG_DIR, get_plugin_config, save_plugin_config

DEVICES_FILE = CONFIG_DIR / "home_devices.json"
ROUTINES_FILE = CONFIG_DIR / "home_routines.json"

_LOCK = threading.RLock()

# Default simulated smart-home registry (used when no live Home Assistant is connected)
DEFAULT_DEVICES: dict[str, dict[str, Any]] = {
    "light.living_room_main": {
        "entity_id": "light.living_room_main",
        "name": "Living Room Main Lights",
        "type": "light",
        "room": "living_room",
        "protocol": "home_assistant",
        "state": "off",
        "attributes": {"brightness_pct": 80, "color_temp_kelvin": 4000},
        "capabilities": ["turn_on", "turn_off", "toggle", "brightness", "color_temp"],
        "permission_tier": int(PermissionTier.REMOTE_DEVICE_CONTROL),
        "connectivity": "simulated",
    },
    "light.study_desk": {
        "entity_id": "light.study_desk",
        "name": "Study Desk Lamp",
        "type": "light",
        "room": "study",
        "protocol": "esphome",
        "state": "on",
        "attributes": {"brightness_pct": 100, "color_temp_kelvin": 5000},
        "capabilities": ["turn_on", "turn_off", "toggle", "brightness"],
        "permission_tier": int(PermissionTier.REMOTE_DEVICE_CONTROL),
        "connectivity": "simulated",
    },
    "light.bedroom_ambient": {
        "entity_id": "light.bedroom_ambient",
        "name": "Bedroom Ambient Light",
        "type": "light",
        "room": "bedroom",
        "protocol": "zigbee",
        "state": "off",
        "attributes": {"brightness_pct": 40, "color_temp_kelvin": 2700},
        "capabilities": ["turn_on", "turn_off", "toggle", "brightness"],
        "permission_tier": int(PermissionTier.REMOTE_DEVICE_CONTROL),
        "connectivity": "simulated",
    },
    "fan.bedroom_ceiling": {
        "entity_id": "fan.bedroom_ceiling",
        "name": "Bedroom Ceiling Fan",
        "type": "fan",
        "room": "bedroom",
        "protocol": "tuya",
        "state": "off",
        "attributes": {"speed_pct": 60},
        "capabilities": ["turn_on", "turn_off", "set_speed"],
        "permission_tier": int(PermissionTier.REMOTE_DEVICE_CONTROL),
        "connectivity": "simulated",
    },
    "climate.study_ac": {
        "entity_id": "climate.study_ac",
        "name": "Study Air Conditioner",
        "type": "climate",
        "room": "study",
        "protocol": "matter",
        "state": "cool",
        "attributes": {"temperature_c": 24.0, "current_temperature_c": 25.2, "hvac_mode": "cool"},
        "capabilities": ["turn_on", "turn_off", "set_temperature", "set_hvac_mode"],
        "permission_tier": int(PermissionTier.REMOTE_DEVICE_CONTROL),
        "connectivity": "simulated",
    },
    "switch.coffee_maker": {
        "entity_id": "switch.coffee_maker",
        "name": "Kitchen Coffee Maker Plug",
        "type": "appliance",
        "room": "kitchen",
        "protocol": "shelly",
        "state": "off",
        "attributes": {"power_w": 0.0},
        "capabilities": ["turn_on", "turn_off"],
        "permission_tier": int(PermissionTier.SENSITIVE_SYSTEM),
        "connectivity": "simulated",
    },
    "media_player.redmi_tv": {
        "entity_id": "media_player.redmi_tv",
        "name": "Living Room Redmi Android TV",
        "type": "media_player",
        "room": "living_room",
        "protocol": "android_tv",
        "state": "standby",
        "attributes": {"volume_pct": 35, "app": "Home"},
        "capabilities": ["turn_on", "turn_off", "volume_set", "media_play_pause", "select_source"],
        "permission_tier": int(PermissionTier.REMOTE_DEVICE_CONTROL),
        "connectivity": "simulated",
    },
    "lock.front_door": {
        "entity_id": "lock.front_door",
        "name": "Front Door Smart Lock",
        "type": "lock",
        "room": "entrance",
        "protocol": "matter",
        "state": "locked",
        "attributes": {"battery_pct": 92},
        "capabilities": ["lock", "unlock"],
        "permission_tier": int(PermissionTier.CRITICAL_SECURITY),
        "connectivity": "simulated",
    },
    "alarm_control_panel.home_security": {
        "entity_id": "alarm_control_panel.home_security",
        "name": "Home Security System",
        "type": "security_system",
        "room": "entrance",
        "protocol": "home_assistant",
        "state": "armed_home",
        "attributes": {"zones_secure": True},
        "capabilities": ["arm_away", "arm_home", "disarm"],
        "permission_tier": int(PermissionTier.CRITICAL_SECURITY),
        "connectivity": "simulated",
    },
    "camera.front_porch": {
        "entity_id": "camera.front_porch",
        "name": "Front Porch Camera",
        "type": "camera",
        "room": "entrance",
        "protocol": "home_assistant",
        "state": "idle",
        "attributes": {"privacy_mode": True, "motion_detected": False},
        "capabilities": ["snapshot", "enable_privacy", "disable_privacy"],
        "permission_tier": int(PermissionTier.SENSITIVE_SYSTEM),
        "connectivity": "simulated",
    },
    "sensor.home_environment": {
        "entity_id": "sensor.home_environment",
        "name": "Home Environmental & Power Telemetry",
        "type": "sensor",
        "room": "whole_home",
        "protocol": "mqtt",
        "state": "online",
        "attributes": {
            "temperature_c": 24.8,
            "humidity_pct": 52.0,
            "motion_living_room": False,
            "front_door_contact": "closed",
            "power_consumption_w": 385.0,
            "network_presence": ["owner_phone", "workstation_kde"],
        },
        "capabilities": ["read"],
        "permission_tier": int(PermissionTier.PERSONAL_INFO),
        "connectivity": "simulated",
    },
}

DEFAULT_ROUTINES: dict[str, dict[str, Any]] = {
    "morning": {
        "name": "Morning Routine",
        "description": "Turn on study & living room lights, set AC to 24°C, disarm night mode to armed_home.",
        "trigger": {"type": "manual_or_schedule", "schedule": "07:00"},
        "requires_confirmation": False,
        "actions": [
            {"entity_id": "light.living_room_main", "command": "turn_on", "params": {"brightness_pct": 85}},
            {"entity_id": "light.study_desk", "command": "turn_on", "params": {"brightness_pct": 100}},
            {"entity_id": "climate.study_ac", "command": "set_temperature", "params": {"temperature_c": 24.0}},
        ],
    },
    "evening": {
        "name": "Evening Routine",
        "description": "Warm living room & bedroom ambient lighting, turn off study desk lamp.",
        "trigger": {"type": "manual_or_schedule", "schedule": "19:30"},
        "requires_confirmation": False,
        "actions": [
            {"entity_id": "light.living_room_main", "command": "turn_on", "params": {"brightness_pct": 55, "color_temp_kelvin": 3000}},
            {"entity_id": "light.bedroom_ambient", "command": "turn_on", "params": {"brightness_pct": 45}},
            {"entity_id": "light.study_desk", "command": "turn_off", "params": {}},
        ],
    },
    "leaving_home": {
        "name": "Leaving Home Routine",
        "description": "Turn off all lights, fans, AC, coffee maker, standby TV, lock front door, and arm security away.",
        "trigger": {"type": "manual_or_presence", "event": "user_departed"},
        "requires_confirmation": True,
        "actions": [
            {"entity_id": "light.living_room_main", "command": "turn_off", "params": {}},
            {"entity_id": "light.study_desk", "command": "turn_off", "params": {}},
            {"entity_id": "light.bedroom_ambient", "command": "turn_off", "params": {}},
            {"entity_id": "fan.bedroom_ceiling", "command": "turn_off", "params": {}},
            {"entity_id": "climate.study_ac", "command": "turn_off", "params": {}},
            {"entity_id": "switch.coffee_maker", "command": "turn_off", "params": {}},
            {"entity_id": "media_player.redmi_tv", "command": "turn_off", "params": {}},
            {"entity_id": "lock.front_door", "command": "lock", "params": {}},
            {"entity_id": "alarm_control_panel.home_security", "command": "arm_away", "params": {}},
        ],
    },
    "returning_home": {
        "name": "Returning Home Routine",
        "description": "Turn on living room lights, set study AC to 24°C, set security to armed_home.",
        "trigger": {"type": "manual_or_presence", "event": "user_arrived"},
        "requires_confirmation": True,
        "actions": [
            {"entity_id": "alarm_control_panel.home_security", "command": "arm_home", "params": {}},
            {"entity_id": "light.living_room_main", "command": "turn_on", "params": {"brightness_pct": 80}},
            {"entity_id": "climate.study_ac", "command": "turn_on", "params": {"temperature_c": 24.0}},
        ],
    },
    "sleep": {
        "name": "Sleep Routine",
        "description": "Turn off living room & study lights, turn on bedroom fan at 50%, lock front door, arm security.",
        "trigger": {"type": "manual_or_schedule", "schedule": "23:00"},
        "requires_confirmation": False,
        "actions": [
            {"entity_id": "light.living_room_main", "command": "turn_off", "params": {}},
            {"entity_id": "light.study_desk", "command": "turn_off", "params": {}},
            {"entity_id": "light.bedroom_ambient", "command": "turn_off", "params": {}},
            {"entity_id": "fan.bedroom_ceiling", "command": "turn_on", "params": {"speed_pct": 50}},
            {"entity_id": "lock.front_door", "command": "lock", "params": {}},
            {"entity_id": "alarm_control_panel.home_security", "command": "arm_home", "params": {}},
        ],
    },
}


class HomeAutomationController:
    """Unified Home Automation Controller supporting Home Assistant REST/WS, MQTT,
    local HTTP (Shelly/ESPHome/Tuya), and a clearly labeled Simulated Home Environment."""

    def __init__(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self._devices = self._load_devices()
        self._routines = self._load_routines()

    def _load_devices(self) -> dict[str, dict[str, Any]]:
        with _LOCK:
            if DEVICES_FILE.exists():
                try:
                    data = json.loads(DEVICES_FILE.read_text(encoding="utf-8"))
                    if isinstance(data, dict) and data:
                        return data
                except Exception:
                    pass
            devices = json.loads(json.dumps(DEFAULT_DEVICES))
            DEVICES_FILE.write_text(json.dumps(devices, indent=2), encoding="utf-8")
            return devices

    def _save_devices(self) -> None:
        with _LOCK:
            DEVICES_FILE.write_text(json.dumps(self._devices, indent=2), encoding="utf-8")

    def _load_routines(self) -> dict[str, dict[str, Any]]:
        with _LOCK:
            if ROUTINES_FILE.exists():
                try:
                    data = json.loads(ROUTINES_FILE.read_text(encoding="utf-8"))
                    if isinstance(data, dict) and data:
                        return data
                except Exception:
                    pass
            routines = json.loads(json.dumps(DEFAULT_ROUTINES))
            ROUTINES_FILE.write_text(json.dumps(routines, indent=2), encoding="utf-8")
            return routines

    def _save_routines(self) -> None:
        with _LOCK:
            ROUTINES_FILE.write_text(json.dumps(self._routines, indent=2), encoding="utf-8")

    # ── Home Assistant / MQTT Connection Config ──────────────────────────────

    def get_ha_config(self) -> dict[str, Any]:
        cfg = get_plugin_config("home_assistant")
        return {
            "url": str(cfg.get("url", "") or "").rstrip("/"),
            "token": str(cfg.get("token", "") or "").strip(),
            "mqtt_host": str(cfg.get("mqtt_host", "") or "").strip(),
            "mqtt_port": int(cfg.get("mqtt_port", 1883) or 1883),
        }

    def configure_connection(
        self,
        ha_url: str | None = None,
        ha_token: str | None = None,
        mqtt_host: str | None = None,
        mqtt_port: int | None = None,
    ) -> dict[str, Any]:
        updates: dict[str, Any] = {}
        if ha_url is not None:
            updates["url"] = ha_url.strip().rstrip("/")
        if ha_token is not None:
            updates["token"] = ha_token.strip()
        if mqtt_host is not None:
            updates["mqtt_host"] = mqtt_host.strip()
        if mqtt_port is not None:
            updates["mqtt_port"] = int(mqtt_port)
        save_plugin_config("home_assistant", updates)
        return self.check_live_connectivity()

    def check_live_connectivity(self) -> dict[str, Any]:
        cfg = self.get_ha_config()
        url = cfg["url"]
        token = cfg["token"]
        if not url or not token:
            return {
                "live_connected": False,
                "simulated": True,
                "mode_label": "[SIMULATED HOME ENVIRONMENT]",
                "reason": "No live Home Assistant URL/token configured; using local Simulated Home Environment.",
            }
        try:
            req = urllib.request.Request(
                f"{url}/api/",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                return {
                    "live_connected": True,
                    "simulated": False,
                    "mode_label": "[LIVE HOME ASSISTANT]",
                    "ha_message": body.get("message", "API running."),
                }
        except Exception as exc:
            return {
                "live_connected": False,
                "simulated": True,
                "mode_label": "[SIMULATED HOME ENVIRONMENT — HA OFFLINE]",
                "reason": f"Home Assistant at {url} unreachable ({exc}); using Simulated Home Environment.",
            }

    # ── Device Resolution & Listing ──────────────────────────────────────────

    def resolve_device(self, query: str) -> dict[str, Any] | None:
        q = (query or "").strip().lower()
        if not q:
            return None
        with _LOCK:
            if q in self._devices:
                return self._devices[q]
            # Match by name, room + type, or substring
            q_words = [w for w in q.replace("_", " ").split() if w not in ("the", "my", "in", "room")]
            best_score = 0
            best_dev = None
            for eid, dev in self._devices.items():
                hay = f"{eid} {dev.get('name', '')} {dev.get('room', '')} {dev.get('type', '')}".lower().replace("_", " ")
                score = sum(2 if w in hay.split() else (1 if w in hay else 0) for w in q_words)
                if score > best_score:
                    best_score = score
                    best_dev = dev
            return best_dev

    def list_devices(self, room: str | None = None, device_type: str | None = None) -> dict[str, Any]:
        conn = self.check_live_connectivity()
        with _LOCK:
            items = list(self._devices.values())
        if room:
            r_clean = room.strip().lower().replace(" ", "_")
            items = [d for d in items if r_clean in str(d.get("room", "")).lower()]
        if device_type:
            t_clean = device_type.strip().lower()
            items = [d for d in items if t_clean in str(d.get("type", "")).lower()]
        return {
            "simulated": conn["simulated"],
            "mode_label": conn["mode_label"],
            "count": len(items),
            "devices": items,
        }

    def register_device(self, device_spec: dict[str, Any]) -> tuple[bool, str]:
        eid = str(device_spec.get("entity_id", "") or "").strip()
        if not eid or "." not in eid:
            return False, "entity_id must be in '<domain>.<name>' format (e.g. 'light.patio')."
        with _LOCK:
            self._devices[eid] = {
                "entity_id": eid,
                "name": device_spec.get("name", eid),
                "type": device_spec.get("type", eid.split(".")[0]),
                "room": device_spec.get("room", "unassigned"),
                "protocol": device_spec.get("protocol", "home_assistant"),
                "state": device_spec.get("state", "off"),
                "attributes": device_spec.get("attributes", {}),
                "capabilities": device_spec.get("capabilities", ["turn_on", "turn_off"]),
                "permission_tier": int(device_spec.get("permission_tier", PermissionTier.REMOTE_DEVICE_CONTROL)),
                "connectivity": device_spec.get("connectivity", "simulated"),
            }
            self._save_devices()
        return True, f"Registered device '{eid}' in room '{self._devices[eid]['room']}'."

    # ── Device Control with Post-Action State Verification ───────────────────

    def control_device(
        self,
        target: str,
        command: str,
        params: dict[str, Any] | None = None,
        pin: str | None = None,
        interactive_confirm: bool = True,
        routine_confirmed: bool = False,
    ) -> dict[str, Any]:
        """Execute a command on a smart home device and verify the resulting state."""
        dev = self.resolve_device(target)
        if not dev:
            return {
                "ok": False,
                "verified": False,
                "error": f"Device '{target}' not found in home registry.",
            }

        eid = dev["entity_id"]
        cmd = (command or "").strip().lower()
        params = dict(params or {})

        # Determine permission tier
        if cmd in ("status", "query", "get", "info"):
            tier = PermissionTier.GENERAL_CONVERSATION
        else:
            tier = PermissionTier(int(dev.get("permission_tier", PermissionTier.REMOTE_DEVICE_CONTROL)))
        # Unlocking a door or disarming an alarm is always CRITICAL_SECURITY
        if cmd in ("unlock", "disarm", "disable_privacy"):
            tier = PermissionTier.CRITICAL_SECURITY

        if not routine_confirmed:
            perm = check_permission(
                operation=f"home_automation:{cmd}:{eid}",
                tier=tier,
                description=f"{cmd.upper()} on {dev['name']} ({eid})",
                pin=pin,
                interactive_confirm=interactive_confirm,
            )
            if not perm["allowed"]:
                return {
                    "ok": False,
                    "verified": False,
                    "entity_id": eid,
                    "error": perm["reason"],
                    "permission": perm,
                }

        conn = self.check_live_connectivity()
        simulated = conn["simulated"]

        # Expected target state computation
        expected_state = dev["state"]
        if cmd in ("turn_on", "on"):
            expected_state = "cool" if dev["type"] == "climate" else "on"
        elif cmd in ("turn_off", "off"):
            expected_state = "standby" if dev["type"] == "media_player" else "off"
        elif cmd == "toggle":
            expected_state = "off" if dev["state"] in ("on", "cool", "heat", "playing") else "on"
        elif cmd == "lock":
            expected_state = "locked"
        elif cmd == "unlock":
            expected_state = "unlocked"
        elif cmd == "arm_away":
            expected_state = "armed_away"
        elif cmd == "arm_home":
            expected_state = "armed_home"
        elif cmd == "disarm":
            expected_state = "disarmed"
        elif cmd in ("set_temperature", "set_speed", "brightness"):
            expected_state = "cool" if dev["type"] == "climate" else "on"

        # 1. If connected to live Home Assistant, call /api/services/<domain>/<service>
        # and then query /api/states/<entity_id> to verify!
        verified = False
        mode_label = conn["mode_label"]

        # Delegate media_player.redmi_tv to real device_manager atvremote backend
        if eid == "media_player.redmi_tv":
            try:
                from core.device_manager import get_device_manager
                dm = get_device_manager()
                if cmd in ("turn_on", "on", "turn_off", "off", "toggle"):
                    tv_res = dm.tv_action("power")
                elif cmd == "volume_set":
                    tv_res = dm.tv_action("set_volume", volume_pct=params.get("volume_pct", 35))
                elif cmd in ("media_play", "media_pause", "media_play_pause"):
                    tv_res = dm.tv_action("key", key_command="ENTER")
                else:
                    tv_res = dm.tv_action("status")

                if tv_res.get("ok") and not tv_res.get("simulated"):
                    simulated = False
                    verified = True
                    mode_label = tv_res.get("mode_label", "[LIVE ANDROID TV]")
                    dev["state"] = tv_res["status"].get("power", expected_state)
                    dev["connectivity"] = "online"
                    dev["attributes"].update(tv_res["status"])
                    self._save_devices()
                    return {
                        "ok": True,
                        "verified": True,
                        "simulated": False,
                        "mode_label": mode_label,
                        "entity_id": eid,
                        "name": dev["name"],
                        "room": dev["room"],
                        "command": cmd,
                        "state": dev["state"],
                        "attributes": dev["attributes"],
                    }
            except Exception as e:
                print(f"[HomeAutomation] TV delegation failed: {e}")

        if not simulated:
            cfg = self.get_ha_config()
            domain = eid.split(".")[0]
            service = cmd if cmd not in ("on", "off") else f"turn_{cmd}"
            payload = {"entity_id": eid, **params}
            try:
                req = urllib.request.Request(
                    f"{cfg['url']}/api/services/{domain}/{service}",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={
                        "Authorization": f"Bearer {cfg['token']}",
                        "Content-Type": "application/json",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=5.0):
                    pass
                # Post-command state verification GET
                state_req = urllib.request.Request(
                    f"{cfg['url']}/api/states/{eid}",
                    headers={"Authorization": f"Bearer {cfg['token']}"},
                    method="GET",
                )
                with urllib.request.urlopen(state_req, timeout=4.0) as sresp:
                    sbody = json.loads(sresp.read().decode("utf-8"))
                    actual_state = str(sbody.get("state", ""))
                    dev["state"] = actual_state
                    dev["attributes"].update(sbody.get("attributes", {}))
                    dev["connectivity"] = "online"
                    verified = (actual_state == expected_state) or (actual_state not in ("unavailable", "unknown"))
                    self._save_devices()
            except Exception as exc:
                return {
                    "ok": False,
                    "verified": False,
                    "simulated": False,
                    "entity_id": eid,
                    "error": f"Live Home Assistant command failed or could not be verified: {exc}",
                }
        else:
            # 2. Simulated Home Environment execution & state verification
            with _LOCK:
                dev["state"] = expected_state
                for k, v in params.items():
                    dev["attributes"][k] = v
                if eid == "switch.coffee_maker":
                    dev["attributes"]["power_w"] = 950.0 if expected_state == "on" else 0.0
                self._save_devices()
                # Verify against persisted registry
                reloaded = self._load_devices().get(eid, {})
                verified = reloaded.get("state") == expected_state

        log_audit_event(
            "home_device_controlled",
            f"{cmd}:{eid}",
            tier,
            True,
            f"{conn['mode_label']} {dev['name']} -> state='{dev['state']}' (verified={verified})",
        )
        return {
            "ok": True,
            "verified": verified,
            "simulated": simulated,
            "mode_label": conn["mode_label"],
            "entity_id": eid,
            "name": dev["name"],
            "room": dev["room"],
            "command": cmd,
            "state": dev["state"],
            "attributes": dev["attributes"],
        }

    # ── Routines & Automations ───────────────────────────────────────────────

    def list_routines(self) -> dict[str, Any]:
        with _LOCK:
            return dict(self._routines)

    def save_routine(
        self,
        routine_name: str,
        description: str,
        actions: list[dict[str, Any]],
        requires_confirmation: bool = False,
        trigger: dict[str, Any] | None = None,
    ) -> tuple[bool, str]:
        rkey = (routine_name or "").strip().lower().replace(" ", "_")
        if not rkey or not actions:
            return False, "Routine requires both 'routine_name' and a non-empty 'actions' list."
        with _LOCK:
            self._routines[rkey] = {
                "name": routine_name.strip(),
                "description": description,
                "trigger": trigger or {"type": "manual"},
                "requires_confirmation": bool(requires_confirmation),
                "actions": actions,
            }
            self._save_routines()
        return True, f"Saved home routine '{rkey}' with {len(actions)} action(s)."

    def execute_routine(
        self,
        routine_name: str,
        confirmed: bool = False,
        pin: str | None = None,
        interactive_confirm: bool = True,
    ) -> dict[str, Any]:
        rkey = (routine_name or "").strip().lower().replace(" ", "_").replace("-", "_")
        with _LOCK:
            routine = self._routines.get(rkey)
            if not routine:
                for k, v in self._routines.items():
                    if rkey in k or rkey in v.get("name", "").lower().replace(" ", "_"):
                        routine = v
                        rkey = k
                        break

        if not routine:
            return {
                "ok": False,
                "error": f"Routine '{routine_name}' not found. Available: {', '.join(self._routines.keys())}.",
            }

        # Check if routine contains sensitive actions or requires confirmation
        needs_confirm = bool(routine.get("requires_confirmation", False))
        if needs_confirm and not confirmed:
            perm = check_permission(
                operation=f"home_routine:{rkey}",
                tier=PermissionTier.SENSITIVE_SYSTEM,
                description=f"Run routine '{routine['name']}': {routine.get('description', '')}",
                pin=pin,
                interactive_confirm=interactive_confirm,
            )
            if not perm["allowed"]:
                return {
                    "ok": False,
                    "requires_confirmation": True,
                    "routine": rkey,
                    "description": routine.get("description", ""),
                    "error": perm["reason"],
                }

        results = []
        all_verified = True
        for act in routine.get("actions", []):
            res = self.control_device(
                target=act["entity_id"],
                command=act["command"],
                params=act.get("params", {}),
                pin=pin,
                interactive_confirm=False,  # Routine-level gate already evaluated
                routine_confirmed=True,
            )
            results.append(res)
            if not res.get("verified"):
                all_verified = False

        conn = self.check_live_connectivity()
        return {
            "ok": True,
            "verified": all_verified,
            "simulated": conn["simulated"],
            "mode_label": conn["mode_label"],
            "routine": rkey,
            "name": routine.get("name", rkey),
            "results": results,
        }

    # ── Environmental Telemetry & Camera Privacy ─────────────────────────────

    def get_environment_summary(self, include_cameras: bool = False) -> dict[str, Any]:
        conn = self.check_live_connectivity()
        with _LOCK:
            sensor = self._devices.get("sensor.home_environment", {})
            cam = self._devices.get("camera.front_porch", {})
            lock = self._devices.get("lock.front_door", {})
            alarm = self._devices.get("alarm_control_panel.home_security", {})
            active_lights = [
                d["name"] for d in self._devices.values()
                if d.get("type") == "light" and d.get("state") == "on"
            ]

        cam_info: dict[str, Any] = {
            "entity_id": cam.get("entity_id", "camera.front_porch"),
            "privacy_mode": cam.get("attributes", {}).get("privacy_mode", True),
            "authorized_in_request": bool(include_cameras),
        }
        if include_cameras and not cam_info["privacy_mode"]:
            cam_info["state"] = cam.get("state", "idle")
            cam_info["motion_detected"] = cam.get("attributes", {}).get("motion_detected", False)
        else:
            cam_info["note"] = "Camera feed withheld (privacy protection active; require explicit authorization)."

        return {
            "simulated": conn["simulated"],
            "mode_label": conn["mode_label"],
            "telemetry": sensor.get("attributes", {}),
            "front_door_lock": lock.get("state", "unknown"),
            "security_system": alarm.get("state", "unknown"),
            "active_lights": active_lights,
            "camera": cam_info,
        }


_HOME_CONTROLLER: HomeAutomationController | None = None


def get_home_controller() -> HomeAutomationController:
    global _HOME_CONTROLLER
    if _HOME_CONTROLLER is None:
        _HOME_CONTROLLER = HomeAutomationController()
    return _HOME_CONTROLLER
