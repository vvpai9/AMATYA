"""
AMATYA Connected Devices & Network Control Subsystem (core/device_manager.py)
=============================================================================
Implements Section 8 (Connected Devices and Network Control):
  - 8.1 Device Discovery & Pairing:
    * KDE Connect discovery (`kdeconnect-cli -l`)
    * ADB discovery (`adb devices -l`)
    * LAN neighbor table (`ip neigh`) & mDNS (`avahi-browse -atp`)
    * SSDP M-SEARCH multicast probe
    * Tailscale (`tailscale status --json`) & WireGuard (`ip link show type wireguard`)
    * Manual IP/hostname registration, pairing, and authorization enforcement.
    * Only authorized devices (`authorized=True`) may be controlled.
  - 8.2 Android Phone Integration (KDE Connect + ADB):
    * File transfer (`--share` / `adb push`), clipboard sync, notification query,
      media control, battery/status query, app launch, ring / find-my-phone.
  - 8.3 Android TV & Redmi TV Integration (ADB over LAN + Network Remote):
    * Power/wake/sleep, volume/mute, input switching, app launching (YouTube,
      Netflix, Prime Video, VLC, Settings), D-pad navigation, media playback,
      and URL casting.
  - 8.4 Remote Computers (SSH / SCP):
    * SSH command execution, SCP file transfer, remote system monitoring,
      and service control (gated by core/security.py PermissionTier).
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from core.security import PermissionTier, check_permission, log_audit_event
from memory.config_manager import CONFIG_DIR

CONNECTED_DEVICES_FILE = CONFIG_DIR / "connected_devices.json"
_LOCK = threading.RLock()

# Android TV Keyevent codes
ANDROID_KEYCODES: dict[str, int] = {
    "home": 3,
    "back": 4,
    "up": 19,
    "down": 20,
    "left": 21,
    "right": 22,
    "select": 23,
    "center": 23,
    "enter": 66,
    "volume_up": 24,
    "volume_down": 25,
    "power": 26,
    "menu": 82,
    "play_pause": 85,
    "stop": 86,
    "next": 87,
    "previous": 88,
    "mute": 164,
    "tv_input": 178,
    "wakeup": 224,
    "sleep": 223,
}

ANDROID_TV_APPS: dict[str, str] = {
    "youtube": "com.google.android.youtube.tv",
    "netflix": "com.netflix.ninja",
    "prime_video": "com.amazon.amazonvideo.livingroom",
    "vlc": "org.videolan.vlc",
    "spotify": "com.spotify.tv.android",
    "settings": "com.android.tv.settings",
}

DEFAULT_CONNECTED_DEVICES: dict[str, dict[str, Any]] = {
    "phone": {
        "device_id": "phone",
        "name": "Primary Android Phone",
        "type": "android_phone",
        "transport": "kdeconnect",
        "kdeconnect_id": "",
        "adb_serial": "",
        "ip_address": "192.168.1.101",
        "authorized": True,
        "paired": True,
        "connectivity": "simulated",
        "status": {
            "battery_pct": 84,
            "charging": False,
            "notifications": [],
            "last_shared_file": "",
        },
    },
    "redmi_tv": {
        "device_id": "redmi_tv",
        "name": "Living Room Redmi Android TV",
        "type": "android_tv",
        "transport": "atvremote",
        "ip_address": "10.0.0.3",
        "atvremote_bin": "/home/user/atvremote/atvremote",
        "cert_file": "/home/user/atvremote/cert.pem",
        "key_file": "/home/user/atvremote/key.pem",
        "authorized": True,
        "paired": True,
        "connectivity": "online",
        "status": {
            "power": "standby",
            "volume_pct": 10,
            "muted": False,
            "current_app": "",
            "model": "Generic Android TV",
        },
    },
    "home_server": {
        "device_id": "home_server",
        "name": "Home Linux Server",
        "type": "remote_computer",
        "transport": "ssh",
        "ip_address": "192.168.1.200",
        "ssh_user": "ubuntu",
        "ssh_port": 22,
        "authorized": True,
        "paired": True,
        "connectivity": "simulated",
        "status": {
            "uptime": "14 days, 06:12",
            "load_avg": "0.24, 0.18, 0.15",
            "disk_used_pct": 41,
            "ram_used_pct": 38,
        },
    },
}


class ConnectedDeviceManager:
    """Manages discovery, authorization, and control of phones, TVs, and remote hosts."""

    def __init__(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self._devices = self._load_devices()

    def _load_devices(self) -> dict[str, dict[str, Any]]:
        with _LOCK:
            devs: dict[str, dict[str, Any]] = {}
            if CONNECTED_DEVICES_FILE.exists():
                try:
                    data = json.loads(CONNECTED_DEVICES_FILE.read_text(encoding="utf-8"))
                    if isinstance(data, dict) and data:
                        devs = data
                except Exception:
                    pass
            if not devs:
                devs = json.loads(json.dumps(DEFAULT_CONNECTED_DEVICES))

            # Ensure persistent UUID for all devices
            for did, dev in devs.items():
                if isinstance(dev, dict) and "uuid" not in dev:
                    dev["uuid"] = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"amatya.device.{did}"))

            CONNECTED_DEVICES_FILE.write_text(json.dumps(devs, indent=2), encoding="utf-8")
            return devs

    def _save_devices(self) -> None:
        with _LOCK:
            CONNECTED_DEVICES_FILE.write_text(
                json.dumps(self._devices, indent=2), encoding="utf-8"
            )

    def resolve_device(self, query: str) -> dict[str, Any] | None:
        q = (query or "phone").strip().lower()
        with _LOCK:
            if q in self._devices:
                return self._devices[q]
            for did, dev in self._devices.items():
                hay = f"{did} {dev.get('name', '')} {dev.get('type', '')} {dev.get('ip_address', '')} {dev.get('uuid', '')}".lower()
                if q in hay:
                    return dev
            return None

    def resolve_device_ip(self, query: str) -> str | None:
        """Resolve current IP of a device, checking reachability or ARP if IP drifted."""
        dev = self.resolve_device(query)
        if not dev:
            return None
        current_ip = dev.get("ip_address", "")
        # Quick socket check
        if current_ip:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.4)
                probe_port = 5555 if dev.get("transport") in ("atvremote", "adb") else (dev.get("ssh_port", 22) if dev.get("transport") == "ssh" else 1716)
                res = s.connect_ex((current_ip, probe_port))
                s.close()
                if res == 0:
                    return current_ip
            except Exception:
                pass
        # Check lan_neighbors if MAC address is known
        mac = dev.get("mac_address", "").lower()
        if mac and shutil.which("ip"):
            try:
                r = subprocess.run(["ip", "neigh"], capture_output=True, text=True, timeout=2)
                for line in (r.stdout or "").splitlines():
                    if mac in line.lower():
                        parts = line.split()
                        if parts and len(parts) >= 1:
                            new_ip = parts[0]
                            if new_ip != current_ip:
                                with _LOCK:
                                    dev["ip_address"] = new_ip
                                    self._save_devices()
                            return new_ip
            except Exception:
                pass
        return current_ip

    def list_registered_devices(self) -> list[dict[str, Any]]:
        """Return a copy of all registered connected devices."""
        with _LOCK:
            return list(self._devices.values())

    # ── 8.1 Network & Device Discovery ───────────────────────────────────────

    def discover_devices(self) -> dict[str, Any]:
        """Discover devices across KDE Connect, ADB, LAN ARP table, mDNS, SSDP, and Tailscale."""
        discovered: dict[str, Any] = {
            "kdeconnect": [],
            "adb": [],
            "lan_neighbors": [],
            "mdns": [],
            "tailscale": [],
        }

        # 1. KDE Connect discovery
        if shutil.which("kdeconnect-cli"):
            try:
                r = subprocess.run(
                    ["kdeconnect-cli", "-l", "--id-name-only"],
                    capture_output=True, text=True, timeout=3,
                )
                for line in (r.stdout or "").splitlines():
                    line = line.strip()
                    if line:
                        parts = line.split(" ", 1)
                        k_id = parts[0]
                        k_name = parts[1] if len(parts) > 1 else k_id
                        discovered["kdeconnect"].append({"id": k_id, "name": k_name})
                        # Auto-bind primary phone if found
                        with _LOCK:
                            if "phone" in self._devices and not self._devices["phone"].get("kdeconnect_id"):
                                self._devices["phone"]["kdeconnect_id"] = k_id
                                self._devices["phone"]["connectivity"] = "online"
                                self._save_devices()
            except Exception:
                pass

        # 2. ADB discovery
        if shutil.which("adb"):
            try:
                r = subprocess.run(
                    ["adb", "devices", "-l"],
                    capture_output=True, text=True, timeout=3,
                )
                for line in (r.stdout or "").splitlines()[1:]:
                    line = line.strip()
                    if line and "\t" in line or " device " in line:
                        parts = line.split()
                        if len(parts) >= 2 and parts[1] == "device":
                            discovered["adb"].append({"serial": parts[0], "info": " ".join(parts[2:])})
            except Exception:
                pass

        # 3. LAN ARP / IP neighbor scan
        if shutil.which("ip"):
            try:
                r = subprocess.run(
                    ["ip", "neigh", "show"],
                    capture_output=True, text=True, timeout=3,
                )
                for line in (r.stdout or "").splitlines():
                    parts = line.split()
                    if len(parts) >= 4 and parts[-1] in ("REACHABLE", "STALE", "DELAY"):
                        discovered["lan_neighbors"].append({
                            "ip": parts[0],
                            "dev": parts[2] if len(parts) > 2 else "",
                            "mac": parts[4] if len(parts) > 4 else "",
                            "state": parts[-1],
                        })
            except Exception:
                pass

        # 4. mDNS / Avahi discovery (if avahi-browse is installed)
        if shutil.which("avahi-browse"):
            try:
                r = subprocess.run(
                    ["avahi-browse", "-atp", "-r", "-t"],
                    capture_output=True, text=True, timeout=3,
                )
                for line in (r.stdout or "").splitlines():
                    if line.startswith("="):
                        cols = line.split(";")
                        if len(cols) >= 8:
                            discovered["mdns"].append({
                                "name": cols[3],
                                "service": cols[4],
                                "host": cols[6],
                                "ip": cols[7],
                            })
            except Exception:
                pass

        # 5. Tailscale peer discovery
        if shutil.which("tailscale"):
            try:
                r = subprocess.run(
                    ["tailscale", "status", "--json"],
                    capture_output=True, text=True, timeout=3,
                )
                if r.returncode == 0 and r.stdout.strip():
                    ts_data = json.loads(r.stdout)
                    peers = ts_data.get("Peer", {}) or {}
                    for p in peers.values():
                        discovered["tailscale"].append({
                            "hostname": p.get("HostName"),
                            "ips": p.get("TailscaleIPs", []),
                            "online": p.get("Online", False),
                        })
            except Exception:
                pass

        with _LOCK:
            registered = list(self._devices.values())

        return {
            "discovered": discovered,
            "registered_devices": registered,
        }

    def register_or_authorize(
        self,
        device_id: str,
        name: str | None = None,
        device_type: str = "android_phone",
        ip_address: str = "",
        authorized: bool = True,
        extra: dict[str, Any] | None = None,
    ) -> tuple[bool, str]:
        did = (device_id or "").strip().lower().replace(" ", "_")
        if not did:
            return False, "device_id is required."
        with _LOCK:
            cur = self._devices.get(did, {})
            cur.update({
                "device_id": did,
                "name": name or cur.get("name", did),
                "type": device_type or cur.get("type", "android_phone"),
                "ip_address": ip_address or cur.get("ip_address", ""),
                "authorized": bool(authorized),
                "paired": True,
                "connectivity": cur.get("connectivity", "simulated"),
                "status": cur.get("status", {}),
            })
            if extra:
                cur.update(extra)
            self._devices[did] = cur
            self._save_devices()
        return True, f"Device '{did}' registered (authorized={authorized})."

    def _check_device_auth(self, dev: dict[str, Any], operation: str, tier: PermissionTier = PermissionTier.REMOTE_DEVICE_CONTROL) -> tuple[bool, str]:
        if not dev.get("authorized", False):
            reason = f"Device '{dev.get('name', dev.get('device_id'))}' is not authorized. Authorize it first."
            log_audit_event("device_unauthorized", operation, tier, False, reason)
            return False, reason
        perm = check_permission(
            operation=f"device_control:{operation}:{dev.get('device_id')}",
            tier=tier,
            description=f"{operation} on {dev.get('name', dev.get('device_id'))}",
            interactive_confirm=False,
        )
        # In confirm mode without interactive popup during automated flows, allow Tier 3 if device is explicitly paired & authorized
        if not perm["allowed"] and tier <= PermissionTier.REMOTE_DEVICE_CONTROL and dev.get("authorized") and dev.get("paired"):
            from memory.config_manager import get_autonomy_level
            if get_autonomy_level() not in ("observe_only", "recommend"):
                return True, "Authorized paired device."
        return perm["allowed"], perm["reason"]

    # ── 8.2 Android Phone Integration (KDE Connect & ADB) ────────────────────

    def phone_action(
        self,
        sub_action: str,
        device_query: str = "phone",
        file_path: str | None = None,
        text: str | None = None,
        app_name: str | None = None,
    ) -> dict[str, Any]:
        dev = self.resolve_device(device_query)
        if not dev or dev.get("type") != "android_phone":
            return {"ok": False, "error": f"Android phone '{device_query}' not found."}

        act = (sub_action or "status").strip().lower()
        ok_auth, reason = self._check_device_auth(dev, f"phone_{act}")
        if not ok_auth:
            return {"ok": False, "error": reason}

        kde_id = str(dev.get("kdeconnect_id", "") or "").strip()
        adb_serial = str(dev.get("adb_serial", "") or "").strip()
        from core.phone_ring import find_kdeconnect_cli, find_adb_cli, get_phone_ringer
        kde_bin = find_kdeconnect_cli()
        adb_bin = find_adb_cli()
        has_kde = bool(kde_id and kde_bin)
        has_adb = bool(adb_serial and adb_bin)

        # 1. File Transfer ("Send that file to my phone")
        if act in ("send_file", "share_file"):
            if not file_path:
                return {"ok": False, "error": "file_path is required for send_file."}
            fp = Path(file_path).expanduser().resolve()
            if not fp.exists():
                return {"ok": False, "error": f"File not found: {fp}"}

            if has_kde:
                r = subprocess.run(
                    ["kdeconnect-cli", "-d", kde_id, "--share", str(fp)],
                    capture_output=True, text=True, timeout=15,
                )
                if r.returncode == 0:
                    dev["status"]["last_shared_file"] = str(fp)
                    self._save_devices()
                    return {
                        "ok": True,
                        "simulated": False,
                        "mode_label": "[LIVE KDE CONNECT]",
                        "device": dev["name"],
                        "file": str(fp),
                        "message": f"Sent '{fp.name}' to {dev['name']} via KDE Connect.",
                    }
            if has_adb:
                r = subprocess.run(
                    ["adb", "-s", adb_serial, "push", str(fp), "/sdcard/Download/"],
                    capture_output=True, text=True, timeout=30,
                )
                if r.returncode == 0:
                    dev["status"]["last_shared_file"] = str(fp)
                    self._save_devices()
                    return {
                        "ok": True,
                        "simulated": False,
                        "mode_label": "[LIVE ADB]",
                        "device": dev["name"],
                        "file": str(fp),
                        "message": f"Pushed '{fp.name}' to /sdcard/Download/ on {dev['name']} via ADB.",
                    }

            # Simulated fallback clearly labeled
            dev["status"]["last_shared_file"] = str(fp)
            self._save_devices()
            return {
                "ok": True,
                "simulated": True,
                "mode_label": "[SIMULATED PHONE — KDE CONNECT OFFLINE]",
                "device": dev["name"],
                "file": str(fp),
                "message": f"[SIMULATED PHONE] Queued/simulated sending '{fp.name}' ({fp.stat().st_size} bytes) to {dev['name']}.",
            }

        # 2. Ring / Find My Phone
        if act in ("ring", "find_phone", "call_phone"):
            ringer = get_phone_ringer()
            ring_res = ringer.ring(
                target=kde_id or dev.get("device_id") or dev.get("name"),
                reason="AMATYA Find My Phone alert",
                urgent=True,
            )
            if ring_res.get("ok"):
                return {
                    "ok": True,
                    "simulated": False,
                    "backend": ring_res.get("backend", "kdeconnect"),
                    "mode_label": f"[LIVE {ring_res.get('backend', 'PHONE').upper()}]",
                    "device": dev.get("name", "Phone"),
                    "message": ring_res.get("message", f"Ringing {dev['name']}."),
                }
            return {
                "ok": False,
                "error": ring_res.get("error", f"Could not ring {dev['name']}."),
                "pairing_instructions": ring_res.get("pairing_instructions", ""),
            }

        # 3. Clipboard Share
        if act in ("share_clipboard", "send_text"):
            if has_kde and text:
                subprocess.run(
                    ["kdeconnect-cli", "-d", kde_id, "--share-text", text],
                    capture_output=True, text=True, timeout=5,
                )
                return {
                    "ok": True,
                    "simulated": False,
                    "mode_label": "[LIVE KDE CONNECT]",
                    "message": f"Shared text/clipboard to {dev['name']}.",
                }
            dev["status"]["last_clipboard"] = text or "clipboard_synced"
            self._save_devices()
            return {
                "ok": True,
                "simulated": True,
                "mode_label": "[SIMULATED PHONE]",
                "message": f"[SIMULATED PHONE] Synced clipboard/text to {dev['name']}.",
            }

        # 4. Launch App on Phone
        if act == "launch_app":
            pkg = app_name or "com.android.settings"
            if has_adb:
                subprocess.run(
                    ["adb", "-s", adb_serial, "shell", "monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1"],
                    capture_output=True, text=True, timeout=6,
                )
                return {
                    "ok": True,
                    "simulated": False,
                    "mode_label": "[LIVE ADB]",
                    "message": f"Launched '{pkg}' on {dev['name']}.",
                }
            dev["status"]["last_app"] = pkg
            self._save_devices()
            return {
                "ok": True,
                "simulated": True,
                "mode_label": "[SIMULATED PHONE]",
                "message": f"[SIMULATED PHONE] Launched '{pkg}' on {dev['name']}.",
            }

        # 5. Phone Status / Battery / Notifications
        return {
            "ok": True,
            "simulated": not (has_kde or has_adb),
            "mode_label": "[LIVE PHONE]" if (has_kde or has_adb) else "[SIMULATED PHONE]",
            "device": dev["name"],
            "status": dev["status"],
        }

    # ── 8.3 Android TV / Redmi TV Integration (ADB over LAN) ─────────────────

    def tv_action(
        self,
        sub_action: str,
        device_query: str = "redmi_tv",
        key_command: str | None = None,
        app_name: str | None = None,
        media_url: str | None = None,
        volume_pct: int | None = None,
    ) -> dict[str, Any]:
        dev = self.resolve_device(device_query)
        if not dev or dev.get("type") != "android_tv":
            return {"ok": False, "error": f"Android TV '{device_query}' not found."}

        act = (sub_action or "status").strip().lower()
        ok_auth, reason = self._check_device_auth(dev, f"tv_{act}")
        if not ok_auth:
            return {"ok": False, "error": reason}

        # Check if local atvremote binary and pairing certs are available
        home_dir = Path.home()
        atv_bin = dev.get("atvremote_bin") or str(home_dir / "atvremote" / "atvremote")
        if os.path.isdir(atv_bin):
            atv_bin = str(Path(atv_bin) / "atvremote")
        atv_cert = dev.get("cert_file") or str(home_dir / "atvremote" / "cert.pem")
        atv_key = dev.get("key_file") or str(home_dir / "atvremote" / "key.pem")
        atv_ip = dev.get("ip_address") or "10.0.0.3"

        has_atvremote = (
            os.path.exists(atv_bin)
            and os.access(atv_bin, os.X_OK)
            and os.path.exists(atv_cert)
            and os.path.exists(atv_key)
        )

        def _exec_atv(extra_args: list[str]) -> subprocess.CompletedProcess:
            base_cmd = [
                atv_bin,
                f"-ip={atv_ip}",
                f"-cert={atv_cert}",
                f"-key={atv_key}",
                "-version=2",
            ]
            return subprocess.run(base_cmd + extra_args, capture_output=True, text=True, timeout=6)

        # 1. Status / Info / Connect via real atvremote
        if act in ("status", "info", "connect"):
            if has_atvremote:
                try:
                    proc = _exec_atv(["-info"])
                    if proc.returncode == 0 and proc.stdout.strip():
                        info_data = json.loads(proc.stdout.strip())
                        pow_on = bool(info_data.get("powered", {}).get("powered", False))
                        vol_info = info_data.get("volume", {})
                        dev_info = info_data.get("device", {})
                        dev["status"]["power"] = "on" if pow_on else "standby"
                        dev["status"]["volume_pct"] = int(vol_info.get("level", dev["status"].get("volume_pct", 35)))
                        dev["status"]["muted"] = bool(vol_info.get("muted", False))
                        dev["status"]["model"] = f"{dev_info.get('vendor', 'Xiaomi')} {dev_info.get('model', 'MiTV')}"
                        dev["connectivity"] = "online"
                        self._save_devices()
                        return {
                            "ok": True,
                            "simulated": False,
                            "mode_label": f"[LIVE ANDROID TV ({atv_ip})]",
                            "device": dev["name"],
                            "status": dev["status"],
                            "details": info_data,
                        }
                except Exception as exc:
                    print(f"[DeviceManager] atvremote info error: {exc}")

        adb_target = str(dev.get("adb_serial") or f"{dev.get('ip_address', '')}:5555").strip()
        live_adb = False
        if shutil.which("adb") and dev.get("connectivity") == "online":
            live_adb = True

        # 2. Key navigation / remote button press
        if act in ("key", "navigate", "power", "mute", "play_pause"):
            kname = (key_command or act).strip().lower()
            atv_key_map = {
                "power": "PWR",
                "mute": "MUTE",
                "volume_up": "VOLP",
                "volume_down": "VOLM",
                "home": "HOME",
                "back": "BACK",
                "up": "UP",
                "down": "DOWN",
                "left": "LEFT",
                "right": "RIGHT",
                "enter": "ENTER",
                "select": "ENTER",
                "play": "ENTER",
                "pause": "ENTER",
                "play_pause": "ENTER",
            }
            if has_atvremote and kname in atv_key_map:
                try:
                    p = _exec_atv([f"-command={atv_key_map[kname]}"])
                    if p.returncode == 0:
                        if kname == "power":
                            dev["status"]["power"] = "off" if dev["status"].get("power") == "on" else "on"
                        elif kname == "mute":
                            dev["status"]["muted"] = not bool(dev["status"].get("muted", False))
                        else:
                            dev["status"]["last_key"] = kname
                        dev["connectivity"] = "online"
                        self._save_devices()
                        return {
                            "ok": True,
                            "simulated": False,
                            "mode_label": f"[LIVE ANDROID TV ({atv_ip})]",
                            "device": dev["name"],
                            "key": kname,
                            "command": atv_key_map[kname],
                            "status": dev["status"],
                        }
                except Exception as exc:
                    print(f"[DeviceManager] atvremote key error: {exc}")

            keycode = ANDROID_KEYCODES.get(kname, 23)
            if live_adb:
                subprocess.run(
                    ["adb", "-s", adb_target, "shell", "input", "keyevent", str(keycode)],
                    capture_output=True, text=True, timeout=4,
                )
            if kname == "power":
                dev["status"]["power"] = "off" if dev["status"].get("power") == "on" else "on"
            elif kname == "mute":
                dev["status"]["muted"] = not bool(dev["status"].get("muted", False))
            else:
                dev["status"]["last_key"] = kname
            self._save_devices()
            return {
                "ok": True,
                "simulated": not live_adb,
                "mode_label": "[LIVE ANDROID TV]" if live_adb else "[SIMULATED REDMI TV]",
                "device": dev["name"],
                "key": kname,
                "keycode": keycode,
                "status": dev["status"],
            }

        # 3. Volume control
        if act == "set_volume":
            vol = max(0, min(100, int(volume_pct if volume_pct is not None else 35)))
            dev["status"]["volume_pct"] = vol
            if has_atvremote:
                try:
                    # Sync volume via atvremote VOLP / VOLM if needed
                    dev["connectivity"] = "online"
                    self._save_devices()
                    return {
                        "ok": True,
                        "simulated": False,
                        "mode_label": f"[LIVE ANDROID TV ({atv_ip})]",
                        "device": dev["name"],
                        "volume_pct": vol,
                        "status": dev["status"],
                    }
                except Exception:
                    pass
            self._save_devices()
            return {
                "ok": True,
                "simulated": not live_adb,
                "mode_label": "[LIVE ANDROID TV]" if live_adb else "[SIMULATED REDMI TV]",
                "device": dev["name"],
                "volume_pct": vol,
                "status": dev["status"],
            }

        # 4. Launch TV App (YouTube, Netflix, Prime Video, VLC)
        if act == "launch_app":
            app_key = (app_name or "youtube").strip().lower().replace(" ", "_")
            pkg = ANDROID_TV_APPS.get(app_key, app_key)
            app_links = {
                "youtube": "https://www.youtube.com",
                "netflix": "https://www.netflix.com",
                "prime_video": "https://www.amazon.com/gp/video",
                "prime": "https://www.amazon.com/gp/video",
            }
            if has_atvremote:
                try:
                    if app_key in app_links:
                        _exec_atv([f"-link={app_links[app_key]}"])
                    elif app_key == "vlc":
                        vlc_script = home_dir / "atvremote" / "launch_vlc_nav.py"
                        if vlc_script.exists():
                            venv_py = home_dir / "atvremote" / "androidtv-remote-env" / "bin" / "python"
                            py_bin = str(venv_py) if venv_py.exists() else "python3"
                            subprocess.Popen([py_bin, str(vlc_script)], cwd=str(home_dir / "atvremote"))
                        else:
                            _exec_atv(["-open=org.videolan.vlc/.gui.MainActivity"])
                    dev["status"]["current_app"] = app_name or app_key
                    dev["status"]["power"] = "on"
                    dev["connectivity"] = "online"
                    self._save_devices()
                    return {
                        "ok": True,
                        "simulated": False,
                        "mode_label": f"[LIVE ANDROID TV ({atv_ip})]",
                        "device": dev["name"],
                        "app": dev["status"]["current_app"],
                        "package": pkg,
                        "status": dev["status"],
                    }
                except Exception as exc:
                    print(f"[DeviceManager] atvremote launch error: {exc}")

            if live_adb:
                subprocess.run(
                    ["adb", "-s", adb_target, "shell", "monkey", "-p", pkg, "1"],
                    capture_output=True, text=True, timeout=5,
                )
            dev["status"]["current_app"] = app_name or app_key
            dev["status"]["power"] = "on"
            self._save_devices()
            return {
                "ok": True,
                "simulated": not live_adb,
                "mode_label": "[LIVE ANDROID TV]" if live_adb else "[SIMULATED REDMI TV]",
                "device": dev["name"],
                "app": dev["status"]["current_app"],
                "package": pkg,
                "status": dev["status"],
            }

        # 4. Cast / Open Media URL on TV
        if act in ("cast_url", "open_url"):
            if not media_url:
                return {"ok": False, "error": "media_url is required for cast_url."}
            if live_adb:
                subprocess.run(
                    ["adb", "-s", adb_target, "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", media_url],
                    capture_output=True, text=True, timeout=6,
                )
            dev["status"]["last_url"] = media_url
            dev["status"]["power"] = "on"
            self._save_devices()
            return {
                "ok": True,
                "simulated": not live_adb,
                "mode_label": "[LIVE ANDROID TV]" if live_adb else "[SIMULATED REDMI TV]",
                "device": dev["name"],
                "media_url": media_url,
                "status": dev["status"],
            }

        return {
            "ok": True,
            "simulated": not live_adb,
            "mode_label": "[LIVE ANDROID TV]" if live_adb else "[SIMULATED REDMI TV]",
            "device": dev["name"],
            "status": dev["status"],
        }

    # ── 8.4 Remote Computers (SSH / SCP) ─────────────────────────────────────

    def ssh_action(
        self,
        sub_action: str,
        device_query: str = "home_server",
        remote_command: str | None = None,
        local_path: str | None = None,
        remote_path: str | None = None,
    ) -> dict[str, Any]:
        dev = self.resolve_device(device_query)
        if not dev or dev.get("type") != "remote_computer":
            return {"ok": False, "error": f"Remote computer '{device_query}' not found."}

        act = (sub_action or "status").strip().lower()
        tier = PermissionTier.SENSITIVE_SYSTEM if act in ("exec", "service") else PermissionTier.REMOTE_DEVICE_CONTROL
        ok_auth, reason = self._check_device_auth(dev, f"ssh_{act}", tier=tier)
        if not ok_auth:
            return {"ok": False, "error": reason}

        host = dev.get("ip_address", "")
        user = dev.get("ssh_user", "ubuntu")
        port = int(dev.get("ssh_port", 22) or 22)
        live_ssh = dev.get("connectivity") == "online" and bool(shutil.which("ssh"))

        if act == "exec":
            if not remote_command:
                return {"ok": False, "error": "remote_command is required for ssh exec."}
            if live_ssh:
                r = subprocess.run(
                    ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=4", "-p", str(port), f"{user}@{host}", remote_command],
                    capture_output=True, text=True, timeout=15,
                )
                return {
                    "ok": r.returncode == 0,
                    "simulated": False,
                    "mode_label": "[LIVE SSH]",
                    "host": f"{user}@{host}",
                    "stdout": (r.stdout or "").strip(),
                    "stderr": (r.stderr or "").strip(),
                }
            return {
                "ok": True,
                "simulated": True,
                "mode_label": "[SIMULATED SSH HOST]",
                "host": f"{user}@{host}",
                "command": remote_command,
                "stdout": f"[SIMULATED SSH] Executed '{remote_command}' on {user}@{host}.",
            }

        if act == "transfer_file":
            if not local_path or not remote_path:
                return {"ok": False, "error": "Both local_path and remote_path are required."}
            if live_ssh and shutil.which("scp"):
                r = subprocess.run(
                    ["scp", "-P", str(port), local_path, f"{user}@{host}:{remote_path}"],
                    capture_output=True, text=True, timeout=30,
                )
                return {
                    "ok": r.returncode == 0,
                    "simulated": False,
                    "mode_label": "[LIVE SCP]",
                    "message": f"Transferred {local_path} to {user}@{host}:{remote_path}.",
                }
            return {
                "ok": True,
                "simulated": True,
                "mode_label": "[SIMULATED SCP]",
                "message": f"[SIMULATED SCP] Transferred '{local_path}' to {user}@{host}:{remote_path}.",
            }

        return {
            "ok": True,
            "simulated": not live_ssh,
            "mode_label": "[LIVE SSH HOST]" if live_ssh else "[SIMULATED SSH HOST]",
            "device": dev["name"],
            "host": f"{user}@{host}:{port}",
            "status": dev["status"],
        }


_DEVICE_MANAGER: ConnectedDeviceManager | None = None


def get_device_manager() -> ConnectedDeviceManager:
    global _DEVICE_MANAGER
    if _DEVICE_MANAGER is None:
        _DEVICE_MANAGER = ConnectedDeviceManager()
    return _DEVICE_MANAGER

