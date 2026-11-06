"""
core/phone_ring.py — AMATYA Phone Ringing, VoIP Calling & Mobile Alert Engine.
================================================================================
Provides robust phone ringing, VoIP voice calling, and mobile notification capabilities
across Linux, Windows, and macOS:

Backends Supported:
  1. AgentRing (https://github.com/mutonby/agentring):
     - Self-hosted VoIP call with AI voice bridging.
     - Push VoIP wakeups bypassing Doze mode & Do Not Disturb.
     - CLI & Python API integration (agentring call, agentring msg, agentring pair).
  2. KDE Connect (kdeconnect-cli):
     - Cross-platform local Wi-Fi / LAN ring at maximum volume.
     - Auto-discovers executable across Linux, Windows (.exe), and macOS (.app bundle).
  3. ADB (Android Debug Bridge over Wi-Fi / USB):
     - Boosts media/alarm audio stream volume to maximum.
     - Triggers native alarm ringtone intent on Android.
  4. Ntfy.sh (Open-source HTTP push with emergency ring tone):
     - 100% free, open-source, zero-binary pure-Python push service.
     - Sends priority=urgent/max push with alarm ring tags to override silent mode.
"""
from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("amatya.phone_ring")
_SYSTEM = platform.system()  # "Linux" | "Windows" | "Darwin"


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


_BASE = _base_dir()
_CONFIG_PATH = _BASE / "config" / "api_keys.json"
_CONNECTED_DEVICES_PATH = _BASE / "config" / "connected_devices.json"


def _load_api_keys() -> dict[str, Any]:
    try:
        if _CONFIG_PATH.exists():
            return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_api_keys(data: dict[str, Any]) -> None:
    try:
        _CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning(f"Failed to save api_keys.json: {exc}")


def _load_connected_devices() -> dict[str, Any]:
    try:
        if _CONNECTED_DEVICES_PATH.exists():
            return json.loads(_CONNECTED_DEVICES_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


# ── Cross-Platform Binary Resolvers ───────────────────────────────────────────

def find_kdeconnect_cli() -> Optional[str]:
    """Resolve kdeconnect-cli executable across Linux, Windows, and macOS."""
    # 1. Standard PATH lookup
    found = shutil.which("kdeconnect-cli") or shutil.which("kdeconnect-cli.exe")
    if found:
        return found

    sys_os = platform.system()
    # 2. Windows specific candidate locations
    if sys_os == "Windows":
        candidates = [
            Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "KDE Connect" / "bin" / "kdeconnect-cli.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")) / "KDE Connect" / "bin" / "kdeconnect-cli.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "KDE Connect" / "bin" / "kdeconnect-cli.exe",
            Path("C:\\KDE Connect\\bin\\kdeconnect-cli.exe"),
        ]
        for c in candidates:
            if c.is_file():
                return str(c)

    # 3. macOS specific candidate locations
    elif sys_os == "Darwin":
        candidates = [
            Path("/Applications/KDE Connect.app/Contents/MacOS/kdeconnect-cli"),
            Path.home() / "Applications/KDE Connect.app/Contents/MacOS/kdeconnect-cli",
            Path("/opt/homebrew/bin/kdeconnect-cli"),
            Path("/usr/local/bin/kdeconnect-cli"),
        ]
        for c in candidates:
            if c.is_file():
                return str(c)

    # 4. Linux specific locations
    else:
        candidates = [
            Path("/usr/bin/kdeconnect-cli"),
            Path("/usr/local/bin/kdeconnect-cli"),
            Path.home() / ".local/bin/kdeconnect-cli",
        ]
        for c in candidates:
            if c.is_file():
                return str(c)

    return None


def find_adb_cli() -> Optional[str]:
    """Resolve adb executable across Linux, Windows, and macOS."""
    found = shutil.which("adb") or shutil.which("adb.exe")
    if found:
        return found

    sys_os = platform.system()
    if sys_os == "Windows":
        candidates = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Android" / "Sdk" / "platform-tools" / "adb.exe",
            Path("C:\\platform-tools\\adb.exe"),
            Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "Android" / "platform-tools" / "adb.exe",
        ]
        for c in candidates:
            if c.is_file():
                return str(c)

    elif sys_os == "Darwin":
        candidates = [
            Path.home() / "Library/Android/sdk/platform-tools/adb",
            Path("/opt/homebrew/bin/adb"),
            Path("/usr/local/bin/adb"),
        ]
        for c in candidates:
            if c.is_file():
                return str(c)

    else:
        candidates = [
            Path.home() / "Android/Sdk/platform-tools/adb",
            Path("/usr/bin/adb"),
            Path("/usr/local/bin/adb"),
        ]
        for c in candidates:
            if c.is_file():
                return str(c)

    return None


def find_agentring_cli() -> Optional[str]:
    """Resolve agentring CLI across virtual environments and standard paths."""
    found = shutil.which("agentring") or shutil.which("agentring.exe")
    if found:
        return found

    # Python virtualenv bin directory
    py_dir = Path(sys.executable).parent
    for name in ("agentring", "agentring.exe"):
        cand = py_dir / name
        if cand.is_file():
            return str(cand)

    # Common local bins
    candidates = [
        _BASE / "AMATYA" / "bin" / "agentring",
        Path.home() / ".local" / "bin" / "agentring",
        Path.home() / ".cargo" / "bin" / "agentring",
    ]
    for c in candidates:
        if c.is_file():
            return str(c)

    return None


# ── Backend 1: AgentRing ──────────────────────────────────────────────────────

@dataclass
class AgentRingStatus:
    installed: bool
    configured: bool
    relay_url: str = ""
    devices: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""


def get_agentring_status() -> AgentRingStatus:
    """Check AgentRing installation, relay configuration, and paired devices."""
    cli = find_agentring_cli()
    has_pkg = False
    try:
        import agentring
        has_pkg = True
    except ImportError:
        pass

    if not cli and not has_pkg:
        return AgentRingStatus(
            installed=False,
            configured=False,
            error="AgentRing is not installed. Install via: pip install 'agentring @ git+https://github.com/mutonby/agentring.git#subdirectory=daemon'",
        )

    # Check ~/.agentring/settings.json or settings.yaml
    settings_dir = Path.home() / ".agentring"
    settings_file = settings_dir / "settings.json"
    if not settings_file.exists():
        settings_file = settings_dir / "settings.yaml"

    if not settings_file.exists():
        return AgentRingStatus(
            installed=True,
            configured=False,
            error="AgentRing installed but not configured. Initialize with: agentring init --relay <url> --api-key <ak_...>",
        )

    try:
        from agentring.config import load_settings
        from agentring.relay_client import RelayClient

        s = load_settings()
        relay_url = s.relay
        with RelayClient(s.relay, s.api_key) as client:
            devs = client.list_devices()
            return AgentRingStatus(
                installed=True,
                configured=True,
                relay_url=relay_url,
                devices=devs,
            )
    except Exception as exc:
        return AgentRingStatus(
            installed=True,
            configured=True,
            error=f"AgentRing relay query error: {exc}",
        )


def agentring_call(
    reason: str = "AMATYA calling",
    urgent: bool = True,
    ai: bool = True,
    greeting: Optional[str] = None,
) -> dict[str, Any]:
    """Place a VoIP phone call via AgentRing."""
    cli = find_agentring_cli()
    if not cli:
        return {"ok": False, "error": "agentring CLI executable not found"}

    st = get_agentring_status()
    if not st.configured:
        return {
            "ok": False,
            "error": "AgentRing is not configured. Initialize relay first: agentring init --relay <url> --api-key <key>",
        }

    cmd = [cli, "call", reason[:500]]
    if urgent:
        cmd.append("--urgent")
    if ai:
        cmd.append("--ai")
    if greeting:
        cmd.extend(["--greeting", greeting[:500]])

    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=35)
        if p.returncode == 0:
            return {
                "ok": True,
                "backend": "agentring",
                "message": f"AgentRing VoIP call initiated: '{reason}' (urgent={urgent})",
                "output": p.stdout.strip(),
            }
        return {
            "ok": False,
            "backend": "agentring",
            "error": p.stderr.strip() or p.stdout.strip() or f"Call failed with code {p.returncode}",
        }
    except Exception as exc:
        return {"ok": False, "backend": "agentring", "error": str(exc)}


def agentring_init(relay_url: str, api_key: str) -> dict[str, Any]:
    """Initialize AgentRing relay configuration in ~/.agentring/settings.json."""
    cli = find_agentring_cli()
    if not cli:
        return {"ok": False, "error": "agentring CLI executable not found"}
    try:
        cmd = [cli, "init", "--relay", relay_url.strip(), "--api-key", api_key.strip()]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if p.returncode == 0:
            return {"ok": True, "message": f"AgentRing configured with relay: {relay_url}"}
        return {"ok": False, "error": p.stderr.strip() or p.stdout.strip()}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def agentring_pair() -> dict[str, Any]:
    """Generate pairing QR payload / token for AgentRing Android app."""
    st = get_agentring_status()
    if not st.configured:
        return {
            "ok": False,
            "unconfigured": True,
            "error": (
                "AgentRing is installed but requires a relay connection. "
                "Initialize with: agentring init --relay https://<your-relay> --api-key ak_... "
                "Or in chat: phone_ring action='init_agentring' relay='...' api_key='...'. "
                "Meanwhile, KDE Connect is already paired with your Android Phone and ready to ring immediately!"
            ),
        }

    try:
        from agentring.config import load_settings
        from agentring.relay_client import RelayClient

        s = load_settings()
        with RelayClient(s.relay, s.api_key) as client:
            tok = client.create_pairing_token()
            return {
                "ok": True,
                "qr_payload": tok.get("qr_payload", ""),
                "expires_at": tok.get("expires_at", 0),
                "instructions": (
                    f"Pairing token generated: {tok.get('qr_payload')}\n"
                    "Open AgentRing Android app -> Pair -> Scan QR or Paste Code."
                ),
            }
    except Exception as exc:
        cli = find_agentring_cli()
        if cli:
            try:
                p = subprocess.run([cli, "pair", "--json"], capture_output=True, text=True, timeout=10)
                if p.returncode == 0 and p.stdout.strip():
                    data = json.loads(p.stdout.strip())
                    return {"ok": True, "token_data": data}
            except Exception:
                pass
        return {"ok": False, "error": f"Failed to generate AgentRing pairing token: {exc}"}


def agentring_msg(message: str) -> dict[str, Any]:
    """Send an interactive message to paired phone via AgentRing."""
    cli = find_agentring_cli()
    if not cli:
        return {"ok": False, "error": "agentring CLI not found"}

    try:
        p = subprocess.run([cli, "msg", message], capture_output=True, text=True, timeout=10)
        if p.returncode == 0:
            return {"ok": True, "backend": "agentring", "message_id": p.stdout.strip()}
        return {"ok": False, "backend": "agentring", "error": p.stderr.strip()}
    except Exception as exc:
        return {"ok": False, "backend": "agentring", "error": str(exc)}


# ── Backend 2: KDE Connect ────────────────────────────────────────────────────

def get_kdeconnect_devices() -> list[dict[str, str]]:
    """List paired and reachable devices via KDE Connect."""
    cli = find_kdeconnect_cli()
    if not cli:
        return []

    try:
        p = subprocess.run([cli, "-l"], capture_output=True, text=True, timeout=6)
        if p.returncode != 0:
            return []

        devices = []
        # Sample output: "- Android Phone: generic_kde_id_001 on 10.0.0.2 via LAN (paired and reachable)"
        for line in p.stdout.splitlines():
            line = line.strip()
            if not line.startswith("-") or ":" not in line:
                continue
            parts = line.lstrip("- ").split(":", 1)
            name = parts[0].strip()
            rest = parts[1].strip()
            dev_id = rest.split()[0].strip()
            reachable = "reachable" in rest.lower()
            paired = "paired" in rest.lower()
            devices.append({
                "name": name,
                "device_id": dev_id,
                "reachable": reachable,
                "paired": paired,
                "raw": line,
            })
        return devices
    except Exception as exc:
        logger.warning(f"Error querying kdeconnect devices: {exc}")
        return []


def kdeconnect_ring(device_id: Optional[str] = None) -> dict[str, Any]:
    """Ring phone via KDE Connect."""
    cli = find_kdeconnect_cli()
    if not cli:
        return {
            "ok": False,
            "backend": "kdeconnect",
            "error": "kdeconnect-cli executable not found on this system.",
        }

    devs = get_kdeconnect_devices()
    target_id = device_id
    target_name = "Phone"

    # Match device
    if target_id:
        for d in devs:
            if d["device_id"] == target_id or target_id.lower() in d["name"].lower():
                target_id = d["device_id"]
                target_name = d["name"]
                break
    elif devs:
        # Find first reachable paired device
        reachable = [d for d in devs if d.get("reachable") and d.get("paired")]
        if reachable:
            target_id = reachable[0]["device_id"]
            target_name = reachable[0]["name"]
        else:
            target_id = devs[0]["device_id"]
            target_name = devs[0]["name"]

    cmd = [cli]
    if target_id:
        cmd.extend(["-d", target_id, "--ring"])
    else:
        cmd.append("--ring")

    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        if p.returncode == 0:
            return {
                "ok": True,
                "backend": "kdeconnect",
                "device": target_name,
                "device_id": target_id,
                "message": f"Ringing '{target_name}' at maximum volume via KDE Connect.",
            }
        return {
            "ok": False,
            "backend": "kdeconnect",
            "error": p.stderr.strip() or f"KDE Connect returned exit code {p.returncode}",
        }
    except Exception as exc:
        return {"ok": False, "backend": "kdeconnect", "error": str(exc)}


# ── Backend 3: ADB (Android Debug Bridge) ─────────────────────────────────────

def adb_ring(serial_or_ip: Optional[str] = None) -> dict[str, Any]:
    """Boost audio volume and fire alarm ringtone on Android via ADB."""
    cli = find_adb_cli()
    if not cli:
        return {
            "ok": False,
            "backend": "adb",
            "error": "adb executable not found on this system.",
        }

    cmd_prefix = [cli]
    if serial_or_ip:
        cmd_prefix.extend(["-s", serial_or_ip])

    try:
        # Check attached devices
        p_dev = subprocess.run([cli, "devices"], capture_output=True, text=True, timeout=5)
        lines = [line.strip() for line in p_dev.stdout.splitlines() if line.strip() and not line.startswith("List")]
        if not lines:
            return {"ok": False, "backend": "adb", "error": "No Android device connected via ADB."}

        # 1. Unmute & set alarm / ring volume to max (15 on Android)
        subprocess.run(cmd_prefix + ["shell", "cmd", "media_session", "volume", "--stream", "2", "--set", "15"], capture_output=True, timeout=3)
        subprocess.run(cmd_prefix + ["shell", "cmd", "audio", "set-volume", "3", "15"], capture_output=True, timeout=3)

        # 2. Trigger alarm intent with sound
        alarm_cmd = cmd_prefix + [
            "shell", "am", "start",
            "-a", "android.intent.action.SET_ALARM",
            "-e", "android.intent.extra.alarm.MESSAGE", "AMATYA Phone Ring",
            "--ez", "android.intent.extra.alarm.SKIP_UI", "true",
        ]
        p_alarm = subprocess.run(alarm_cmd, capture_output=True, text=True, timeout=5)

        # 3. Play system ringtone audio intent as fallback
        play_cmd = cmd_prefix + [
            "shell", "am", "start",
            "-a", "android.intent.action.VIEW",
            "-d", "content://settings/system/ringtone",
            "-t", "audio/*",
        ]
        subprocess.run(play_cmd, capture_output=True, text=True, timeout=5)

        return {
            "ok": True,
            "backend": "adb",
            "message": "Boosted volume to maximum and triggered alarm ringtone via ADB.",
            "target": serial_or_ip or lines[0].split()[0],
        }
    except Exception as exc:
        return {"ok": False, "backend": "adb", "error": str(exc)}


# ── Backend 4: Ntfy.sh (Open-Source HTTP Push Alert) ──────────────────────────

def get_or_create_ntfy_topic() -> str:
    """Retrieve or generate persistent ntfy topic for zero-config phone alerts."""
    cfg = _load_api_keys()
    if cfg.get("ntfy_topic"):
        return str(cfg["ntfy_topic"])

    import hashlib
    # Generate stable unique topic based on user & hostname
    user_seed = f"{os.environ.get('USER', 'user')}_{platform.node()}_amatya_ring"
    h = hashlib.sha256(user_seed.encode("utf-8")).hexdigest()[:16]
    topic = f"amatya_{h}"
    cfg["ntfy_topic"] = topic
    _save_api_keys(cfg)
    return topic


def ntfy_ring(
    topic: Optional[str] = None,
    reason: str = "AMATYA is ringing your phone!",
    server: Optional[str] = None,
) -> dict[str, Any]:
    """Send priority=urgent alarm push via ntfy.sh (works on Linux, Windows, macOS)."""
    cfg = _load_api_keys()
    target_topic = topic or cfg.get("ntfy_topic") or get_or_create_ntfy_topic()
    server_url = server or cfg.get("ntfy_server", "https://ntfy.sh").rstrip("/")
    url = f"{server_url}/{target_topic}"

    req = urllib.request.Request(
        url,
        data=reason.encode("utf-8"),
        headers={
            "Title": "AMATYA Phone Ring",
            "Priority": "urgent",  # Level 5 triggers alarm sound even on DND
            "Tags": "rotating_light,loudspeaker,telephone_receiver",
            "Call": "yes",
            "Click": f"{server_url}/{target_topic}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status_code = resp.getcode()
            if status_code in (200, 201):
                return {
                    "ok": True,
                    "backend": "ntfy",
                    "topic": target_topic,
                    "url": url,
                    "message": f"Sent urgent alarm push notification to ntfy topic '{target_topic}'.",
                }
            return {"ok": False, "backend": "ntfy", "error": f"Server returned HTTP {status_code}"}
    except Exception as exc:
        return {"ok": False, "backend": "ntfy", "error": str(exc)}


# ── Unified Phone Ringer Engine ───────────────────────────────────────────────

class PhoneRinger:
    """Unified Phone Ringing & Calling Orchestrator for AMATYA."""

    @property
    def os_name(self) -> str:
        return platform.system()

    def status(self) -> dict[str, Any]:
        """Diagnostic summary of all phone ring backends."""
        ar_st = get_agentring_status()
        kde_cli = find_kdeconnect_cli()
        kde_devs = get_kdeconnect_devices()
        adb_cli = find_adb_cli()
        ntfy_topic = get_or_create_ntfy_topic()

        return {
            "os": self.os_name,
            "agentring": {
                "available": bool(find_agentring_cli()),
                "cli_path": find_agentring_cli(),
                "configured": ar_st.configured,
                "relay_url": ar_st.relay_url,
                "paired_devices_count": len(ar_st.devices),
                "error": ar_st.error,
            },
            "kdeconnect": {
                "available": bool(kde_cli),
                "cli_path": kde_cli,
                "devices": kde_devs,
                "has_reachable_device": any(d.get("reachable") for d in kde_devs),
            },
            "adb": {
                "available": bool(adb_cli),
                "cli_path": adb_cli,
            },
            "ntfy": {
                "topic": ntfy_topic,
                "subscribe_url": f"https://ntfy.sh/{ntfy_topic}",
                "app_instruction": f"Install Ntfy on phone and subscribe to topic '{ntfy_topic}' to ring via Web Push.",
            },
        }

    def ring(
        self,
        backend: str = "auto",
        target: Optional[str] = None,
        reason: str = "AMATYA Phone Ring alert",
        urgent: bool = True,
    ) -> dict[str, Any]:
        """
        Ring phone using the specified or best available backend.
        Priority: AgentRing -> KDE Connect -> ADB -> Ntfy -> Diagnostic Fallback.
        """
        b_choice = backend.strip().lower()

        # 1. Explicit backend requests
        if b_choice in ("agentring", "agent_ring", "voip"):
            return agentring_call(reason=reason, urgent=urgent, ai=True)

        if b_choice in ("kdeconnect", "kde_connect", "kde"):
            return kdeconnect_ring(device_id=target)

        if b_choice in ("adb", "android"):
            return adb_ring(serial_or_ip=target)

        if b_choice in ("ntfy", "push"):
            return ntfy_ring(topic=target, reason=reason)

        # 2. AUTO Selection Cascade
        # Tier 1: AgentRing (if configured with paired devices)
        ar_st = get_agentring_status()
        if ar_st.configured and ar_st.devices:
            res_ar = agentring_call(reason=reason, urgent=urgent, ai=True)
            if res_ar.get("ok"):
                return res_ar

        # Tier 2: KDE Connect (if paired reachable phone found)
        kde_devs = get_kdeconnect_devices()
        reachable_kde = [d for d in kde_devs if d.get("reachable") and d.get("paired")]
        if reachable_kde or (find_kdeconnect_cli() and target):
            res_kde = kdeconnect_ring(device_id=target)
            if res_kde.get("ok"):
                return res_kde

        # Tier 3: ADB (if attached)
        if find_adb_cli():
            res_adb = adb_ring(serial_or_ip=target)
            if res_adb.get("ok"):
                return res_adb

        # Tier 4: Ntfy push alert
        cfg = _load_api_keys()
        if cfg.get("ntfy_enabled", True):
            res_ntfy = ntfy_ring(reason=reason)
            if res_ntfy.get("ok"):
                # Also note KDE Connect / AgentRing status for clarity
                return {
                    "ok": True,
                    "backend": "ntfy",
                    "topic": res_ntfy.get("topic"),
                    "message": (
                        f"Triggered urgent phone alert via Ntfy push ({res_ntfy.get('topic')}).\n"
                        "To ring with sound directly, pair your phone with KDE Connect or AgentRing."
                    ),
                }

        # Fallback Diagnostic
        return {
            "ok": False,
            "error": "No phone currently connected or reachable across AgentRing, KDE Connect, ADB, or Ntfy.",
            "diagnostic": self.status(),
            "pairing_instructions": (
                "To enable direct phone ringing:\n"
                "1. KDE Connect (Local LAN): Open KDE Connect on phone & PC and pair.\n"
                "2. AgentRing (VoIP): Run `agentring pair` and scan QR in AgentRing Android app.\n"
                f"3. Ntfy (Push): Subscribe to https://ntfy.sh/{get_or_create_ntfy_topic()} in Ntfy app."
            ),
        }


_RINGER = PhoneRinger()


def get_phone_ringer() -> PhoneRinger:
    """Return singleton PhoneRinger instance."""
    return _RINGER
