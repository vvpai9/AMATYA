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
import re
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

_TV_APP_MAP: dict[str, str] = {
    "org.videolan.vlc": "VLC",
    "com.google.android.youtube.tv": "YouTube",
    "com.netflix.ninja": "Netflix",
    "com.amazon.amazonvideo.livingroom": "Prime Video",
    "com.google.android.tvlauncher": "Android TV Launcher",
}


from core.tv_control import (
    DEFAULT_CERT_FILE,
    DEFAULT_KEY_FILE,
    AndroidTVController,
    async_finish_pairing_flow,
    async_start_pairing_flow,
    is_tv_configured,
)

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
        "name": "Android Phone",
        "type": "android_phone",
        "transport": "kdeconnect",
        "kdeconnect_id": "generic_kde_id_001",
        "adb_serial": "",
        "ip_address": "192.168.1.100",
        "authorized": True,
        "paired": False,
        "connectivity": "offline",
        "status": {
            "battery_pct": 100,
            "charging": False,
            "notifications": [],
            "last_shared_file": "",
        },
    },
    "redmi_tv": {
        "device_id": "redmi_tv",
        "name": "Living Room Android TV",
        "type": "android_tv",
        "transport": "atvremote",
        "ip_address": "",
        "cert_file": str(DEFAULT_CERT_FILE),
        "key_file": str(DEFAULT_KEY_FILE),
        "authorized": True,
        "paired": False,
        "configured": False,
        "connectivity": "offline",
        "status": {
            "power": "standby",
            "volume_pct": 10,
            "muted": False,
            "current_app": "",
            "model": "Generic Android TV",
        },
    },
}


def query_kdeconnect_battery(kde_id: str) -> tuple[int | None, bool | None]:
    """Query live battery percentage and charging state via D-Bus for a paired KDE Connect device."""
    if not kde_id:
        return None, None
    for qdbus_bin in ("qdbus6", "qdbus"):
        if shutil.which(qdbus_bin):
            try:
                r_charge = subprocess.run(
                    [qdbus_bin, "org.kde.kdeconnect", f"/modules/kdeconnect/devices/{kde_id}/battery", "org.kde.kdeconnect.device.battery.charge"],
                    capture_output=True, text=True, timeout=3
                )
                if r_charge.returncode == 0 and r_charge.stdout.strip().lstrip("-").isdigit():
                    pct = int(r_charge.stdout.strip())
                    r_chg = subprocess.run(
                        [qdbus_bin, "org.kde.kdeconnect", f"/modules/kdeconnect/devices/{kde_id}/battery", "org.kde.kdeconnect.device.battery.isCharging"],
                        capture_output=True, text=True, timeout=3
                    )
                    charging = "true" in r_chg.stdout.lower()
                    return pct, charging
            except Exception:
                pass

    if shutil.which("busctl"):
        try:
            r = subprocess.run(
                ["busctl", "--user", "get-property", "org.kde.kdeconnect", f"/modules/kdeconnect/devices/{kde_id}/battery", "org.kde.kdeconnect.device.battery", "charge"],
                capture_output=True, text=True, timeout=3
            )
            if r.returncode == 0:
                parts = r.stdout.strip().split()
                if len(parts) >= 2 and parts[1].lstrip("-").isdigit():
                    pct = int(parts[1])
                    r_chg = subprocess.run(
                        ["busctl", "--user", "get-property", "org.kde.kdeconnect", f"/modules/kdeconnect/devices/{kde_id}/battery", "org.kde.kdeconnect.device.battery", "isCharging"],
                        capture_output=True, text=True, timeout=3
                    )
                    charging = "true" in r_chg.stdout.lower()
                    return pct, charging
        except Exception:
            pass

    return None, None


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
        """Dynamically discover live devices across LAN (nmap/ARP), IPv6, and Tailscale."""
        discovered: dict[str, Any] = {
            "kdeconnect": [],
            "adb": [],
            "lan_neighbors": [],
            "nmap_hosts": [],
            "tailscale": [],
            "formatted_devices": [],
        }

        # Step A: IPv6 neighbors map by MAC address & IP
        mac_to_ip6: dict[str, str] = {}
        ip4_to_mac: dict[str, str] = {}
        if shutil.which("ip"):
            try:
                r6 = subprocess.run(["ip", "-6", "neigh", "show"], capture_output=True, text=True, timeout=3)
                for line in (r6.stdout or "").splitlines():
                    parts = line.split()
                    if len(parts) >= 5 and "lladdr" in parts:
                        mac_idx = parts.index("lladdr") + 1
                        if mac_idx < len(parts):
                            mac_to_ip6[parts[mac_idx].lower()] = parts[0]
            except Exception:
                pass

            try:
                r4 = subprocess.run(["ip", "neigh", "show"], capture_output=True, text=True, timeout=3)
                for line in (r4.stdout or "").splitlines():
                    parts = line.split()
                    if len(parts) >= 4 and parts[-1] in ("REACHABLE", "STALE", "DELAY"):
                        ip_val = parts[0]
                        mac_val = parts[4].lower() if len(parts) > 4 else ""
                        if mac_val:
                            ip4_to_mac[ip_val] = mac_val
                        discovered["lan_neighbors"].append({
                            "ip": ip_val,
                            "dev": parts[2] if len(parts) > 2 else "",
                            "mac": mac_val,
                            "state": parts[-1],
                        })
            except Exception:
                pass

        # Step B: Identify active local subnets for nmap
        subnets_to_scan = []
        if shutil.which("ip"):
            try:
                r_sub = subprocess.run(["ip", "-o", "-4", "addr", "show"], capture_output=True, text=True, timeout=3)
                for line in (r_sub.stdout or "").splitlines():
                    parts = line.split()
                    if len(parts) >= 4 and not parts[1].startswith("lo") and not parts[1].startswith("tailscale"):
                        cidr = parts[3]
                        if "/" in cidr:
                            ip_addr, mask = cidr.split("/", 1)
                            octets = ip_addr.split(".")
                            if len(octets) == 4 and mask == "24":
                                subnets_to_scan.append(f"{octets[0]}.{octets[1]}.{octets[2]}.0/24")
                            elif len(octets) == 4:
                                subnets_to_scan.append(cidr)
            except Exception:
                pass

        subnets_to_scan = list(dict.fromkeys(subnets_to_scan))

        # Step C: Dynamic nmap ping/ARP scan (fast parallel scan)
        nmap_hosts: list[dict[str, str]] = []
        if shutil.which("nmap"):
            for subnet in subnets_to_scan:
                try:
                    rn = subprocess.run(
                        ["nmap", "-sn", "-T4", "--min-parallelism", "32", subnet],
                        capture_output=True, text=True, timeout=12,
                    )
                    cur_host = ""
                    cur_ip = ""
                    cur_mac = ""
                    for line in (rn.stdout or "").splitlines():
                        m = re.match(r"Nmap scan report for (?:([^\s()]+)\s+\(([\d.]+)\)|([\d.]+))", line)
                        if m:
                            if cur_ip:
                                nmap_hosts.append({"name": cur_host or cur_ip, "ip": cur_ip, "mac": cur_mac})
                                cur_mac = ""
                            if m.group(1):
                                cur_host = m.group(1)
                                cur_ip = m.group(2)
                            else:
                                cur_host = m.group(3)
                                cur_ip = m.group(3)
                        elif "MAC Address:" in line:
                            mm = re.search(r"MAC Address:\s+([0-9A-Fa-f:]+)", line)
                            if mm:
                                cur_mac = mm.group(1).lower()
                    if cur_ip:
                        nmap_hosts.append({"name": cur_host or cur_ip, "ip": cur_ip, "mac": cur_mac})
                except Exception:
                    pass

        discovered["nmap_hosts"] = nmap_hosts

        # Step D: KDE Connect discovery
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
            except Exception:
                pass

        # Step E: Tailscale peer discovery
        if shutil.which("tailscale"):
            try:
                r = subprocess.run(
                    ["tailscale", "status", "--json"],
                    capture_output=True, text=True, timeout=4,
                )
                if r.returncode == 0 and r.stdout.strip():
                    ts_data = json.loads(r.stdout)
                    self_host = ts_data.get("Self", {}).get("HostName", "Localhost")
                    self_ips = ts_data.get("Self", {}).get("TailscaleIPs", [])
                    s_ip4 = next((ip for ip in self_ips if ":" not in ip), "")
                    s_ip6 = next((ip for ip in self_ips if ":" in ip), "")
                    if s_ip4:
                        discovered["tailscale"].append({
                            "hostname": f"{self_host} (Tailscale)",
                            "ipv4": s_ip4,
                            "ipv6": s_ip6 or "None",
                            "online": True,
                        })

                    peers = ts_data.get("Peer", {}) or {}
                    for p in peers.values():
                        p_host = p.get("HostName", "Peer")
                        p_ips = p.get("TailscaleIPs", [])
                        p_ip4 = next((ip for ip in p_ips if ":" not in ip), "")
                        p_ip6 = next((ip for ip in p_ips if ":" in ip), "")
                        discovered["tailscale"].append({
                            "hostname": f"{p_host} (Tailscale)",
                            "ipv4": p_ip4,
                            "ipv6": p_ip6 or "None",
                            "online": p.get("Online", False),
                        })
            except Exception:
                pass

        with _LOCK:
            registered = [d for d in self._devices.values() if d.get("connectivity") != "simulated"]

        # Step F: Build unified dynamic list in strict format: Name, IPv4 address, IPv6 address
        device_entries: list[dict[str, str]] = []
        seen_ips: set[str] = set()

        for nh in nmap_hosts:
            ip4 = nh["ip"]
            if ip4 in seen_ips:
                continue
            seen_ips.add(ip4)
            name = nh["name"]
            mac = nh.get("mac") or ip4_to_mac.get(ip4, "")
            ip6 = mac_to_ip6.get(mac, "None") if mac else "None"
            device_entries.append({
                "name": name,
                "ipv4": ip4,
                "ipv6": ip6,
            })

        for ln in discovered["lan_neighbors"]:
            ip4 = ln["ip"]
            if ":" in ip4:
                continue
            if ip4 not in seen_ips:
                seen_ips.add(ip4)
                mac = ln.get("mac", "").lower()
                ip6 = mac_to_ip6.get(mac, "None") if mac else "None"
                # If we know a registered device on this IP, use its name
                matching_name = next((d["name"] for d in registered if d.get("ip_address") == ip4), ip4)
                device_entries.append({
                    "name": matching_name,
                    "ipv4": ip4,
                    "ipv6": ip6,
                })

        for ts in discovered["tailscale"]:
            ip4 = ts.get("ipv4")
            if ip4 and ip4 not in seen_ips:
                seen_ips.add(ip4)
                device_entries.append({
                    "name": ts["hostname"],
                    "ipv4": ip4,
                    "ipv6": ts.get("ipv6", "None"),
                })

        discovered["formatted_devices"] = device_entries

        with _LOCK:
            registered = [d for d in self._devices.values() if d.get("connectivity") != "simulated"]

        return {
            "discovered": discovered,
            "registered_devices": registered,
            "device_table": [f"{d['name']}, {d['ipv4']}, {d['ipv6']}" for d in device_entries],
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
        live_battery = None
        is_charging = None
        if has_kde:
            live_battery, is_charging = query_kdeconnect_battery(kde_id)
        if live_battery is None and has_adb:
            try:
                r_adb = subprocess.run(["adb", "-s", adb_serial, "shell", "dumpsys", "battery"], capture_output=True, text=True, timeout=3)
                m_lvl = re.search(r"level:\s*(\d+)", r_adb.stdout)
                if m_lvl:
                    live_battery = int(m_lvl.group(1))
                m_chg = re.search(r"powered:\s*(true|false)", r_adb.stdout, re.IGNORECASE)
                if m_chg:
                    is_charging = m_chg.group(1).lower() == "true"
            except Exception:
                pass

        if live_battery is not None:
            dev["status"]["battery_pct"] = live_battery
            if is_charging is not None:
                dev["status"]["charging"] = is_charging
            dev["connectivity"] = "online"
            self._save_devices()

        chg_text = " (charging)" if dev["status"].get("charging") else " (discharging)"
        return {
            "ok": True,
            "simulated": not (has_kde or has_adb),
            "mode_label": "[LIVE PHONE]" if (has_kde or has_adb) else "[SIMULATED PHONE]",
            "device": dev["name"],
            "status": dev["status"],
            "message": f"{dev['name']}: Battery is at {dev['status'].get('battery_pct')}%{chg_text}.",
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
        code: str | None = None,
        ip_address: str | None = None,
        require_configured: bool = False,
    ) -> dict[str, Any]:
        dev = self.resolve_device(device_query)
        if not dev or dev.get("type") != "android_tv":
            # If redmi_tv was requested but not found, check default or create placeholder
            if device_query in ("redmi_tv", "tv", "android_tv"):
                with _LOCK:
                    dev = self._devices.get("redmi_tv")
                    if not dev:
                        dev = dict(DEFAULT_CONNECTED_DEVICES.get("redmi_tv", {}))
                        self._devices["redmi_tv"] = dev
                        self._save_devices()
            if not dev:
                return {"ok": False, "error": f"Android TV '{device_query}' not found."}

        act = (sub_action or "status").strip().lower()

        # Handle TV Setup & Pairing flows
        if act in ("setup_tv", "pair_initiate", "pair_start"):
            target_ip = (ip_address or dev.get("ip_address") or "").strip()
            if not target_ip:
                # Attempt to find discovered Android TV from LAN scan
                disc = self.discover_devices().get("discovered", {})
                for nh in disc.get("nmap_hosts", []):
                    if "tv" in nh.get("name", "").lower():
                        target_ip = nh.get("ip", "")
                        break
            if not target_ip:
                return {
                    "ok": False,
                    "error": (
                        "Please specify your Android TV IP address to initiate pairing, e.g.: "
                        "device_control action='setup_tv' ip_address='192.168.1.5' "
                        "(or run action='discover' to scan your network)."
                    ),
                }

            import asyncio
            ok_start, msg_start = asyncio.run(async_start_pairing_flow(host=target_ip))
            if ok_start:
                dev["ip_address"] = target_ip
                dev["configured"] = False
                dev["paired"] = False
                self._save_devices()
                return {
                    "ok": True,
                    "mode_label": "[TV PAIRING INITIATED]",
                    "message": msg_start,
                    "status": dev.get("status", {}),
                }
            return {"ok": False, "error": msg_start}

        if act in ("pair_tv", "pair_finish", "pair_code"):
            p_code = (code or key_command or "").strip()
            if not p_code:
                return {
                    "ok": False,
                    "error": "Pairing code is required. Please provide the 6-character code shown on your TV screen: action='pair_tv' code='<CODE>'.",
                }

            import asyncio
            ok_fin, msg_fin, p_host = asyncio.run(async_finish_pairing_flow(code=p_code))
            if ok_fin:
                dev["configured"] = True
                dev["paired"] = True
                dev["authorized"] = True
                dev["connectivity"] = "online"
                if p_host:
                    dev["ip_address"] = p_host
                dev["cert_file"] = str(DEFAULT_CERT_FILE)
                dev["key_file"] = str(DEFAULT_KEY_FILE)
                dev["transport"] = "atvremote"
                self._save_devices()
                return {
                    "ok": True,
                    "mode_label": "[TV PAIRED]",
                    "message": msg_fin,
                    "status": dev.get("status", {}),
                }
            return {"ok": False, "error": msg_fin}

        # Check if TV is configured initially
        if not is_tv_configured(dev):
            if require_configured:
                return {
                    "ok": False,
                    "not_configured": True,
                    "mode_label": "[TV NOT CONFIGURED]",
                    "error": (
                        "No Android TV is configured yet. Please configure your TV by running: "
                        "device_control with action='setup_tv' and ip_address='<TV_IP>' (or 'discover' to scan your network). "
                        "AMATYA will initiate pairing and display a 6-character code on your TV screen."
                    ),
                }
            # Unconfigured programmatic call fallback to simulated mode
            dev["status"]["current_app"] = app_name or dev["status"].get("current_app", "Home")
            if volume_pct is not None:
                dev["status"]["volume_pct"] = volume_pct
            self._save_devices()
            return {
                "ok": True,
                "simulated": True,
                "mode_label": "[SIMULATED ANDROID TV]",
                "device": dev["name"],
                "status": dev["status"],
            }

        ok_auth, reason = self._check_device_auth(dev, f"tv_{act}")
        if not ok_auth:
            return {"ok": False, "error": reason}

        atv_cert = dev.get("cert_file") or str(DEFAULT_CERT_FILE)
        atv_key = dev.get("key_file") or str(DEFAULT_KEY_FILE)
        atv_ip = dev.get("ip_address", "").strip()

        # 1. Status / Info / Connect via native AndroidTVController
        if act in ("status", "info", "connect"):
            try:
                import asyncio
                async def _query_status():
                    tv = AndroidTVController(host=atv_ip, cert_file=atv_cert, key_file=atv_key)
                    ok = await tv.connect(timeout=4.0, settle=0.3)
                    if not ok:
                        tv.disconnect()
                        return None
                    st = tv.get_status_dict()
                    tv.disconnect()
                    return st

                res_status = asyncio.run(_query_status())
                if res_status:
                    dev["status"]["power"] = res_status["power"]
                    dev["status"]["is_on"] = res_status["is_on"]
                    dev["status"]["current_app"] = res_status["current_app"]
                    dev["status"]["volume_pct"] = res_status["volume_pct"]
                    dev["connectivity"] = "online"
                    self._save_devices()
                    return {
                        "ok": True,
                        "simulated": False,
                        "mode_label": f"[LIVE ANDROID TV ({atv_ip})]",
                        "device": dev["name"],
                        "status": dev["status"],
                        "details": res_status,
                    }
            except Exception as exc:
                print(f"[DeviceManager] AndroidTVController status error: {exc}")

        # 2. Key navigation / remote button press / Power
        if act in ("key", "navigate", "power", "mute", "play_pause"):
            kname = (key_command or act).strip().lower()
            if kname == "power":
                try:
                    import asyncio
                    async def _toggle_power():
                        tv = AndroidTVController(host=atv_ip, cert_file=atv_cert, key_file=atv_key)
                        ok = await tv.connect(timeout=5.0, settle=0.3)
                        if not ok:
                            tv.disconnect()
                            return False, False, "Failed to connect to TV."
                        was_on = bool(tv.is_on)
                        if not was_on:
                            ok_pow = await tv.power_on(verify_seconds=15)
                        else:
                            ok_pow = await tv.power_off(verify_seconds=10)
                        now_on = bool(tv.is_on)
                        tv.disconnect()
                        return ok_pow, now_on, None

                    ok_pow, now_on, err = asyncio.run(_toggle_power())
                    dev["status"]["power"] = "on" if now_on else "standby"
                    dev["status"]["is_on"] = now_on
                    dev["connectivity"] = "online"
                    self._save_devices()
                    return {
                        "ok": True,
                        "simulated": False,
                        "mode_label": f"[LIVE ANDROID TV ({atv_ip})]",
                        "device": dev["name"],
                        "key": "power",
                        "status": dev["status"],
                        "message": f"{dev['name']} is now {'ON' if now_on else 'OFF (standby)'}.",
                    }
                except Exception as exc:
                    print(f"[DeviceManager] AndroidTVController power error: {exc}")

            else:
                try:
                    import asyncio
                    async def _send_key():
                        tv = AndroidTVController(host=atv_ip, cert_file=atv_cert, key_file=atv_key)
                        ok = await tv.connect(timeout=4.0, settle=0.3)
                        if not ok:
                            tv.disconnect()
                            return False
                        ok_k = await tv.send_key(kname)
                        tv.disconnect()
                        return ok_k

                    ok_k = asyncio.run(_send_key())
                    if ok_k:
                        dev["status"]["last_key"] = kname
                        dev["connectivity"] = "online"
                        self._save_devices()
                        return {
                            "ok": True,
                            "simulated": False,
                            "mode_label": f"[LIVE ANDROID TV ({atv_ip})]",
                            "device": dev["name"],
                            "key": kname,
                            "status": dev["status"],
                            "message": f"Sent key '{kname}' to {dev['name']}.",
                        }
                except Exception as exc:
                    print(f"[DeviceManager] AndroidTVController key error: {exc}")

        # 3. Volume control
        if act in ("set_volume", "volume"):
            vol = max(0, min(100, int(volume_pct if volume_pct is not None else 35)))
            try:
                import asyncio
                async def _adjust_volume():
                    tv = AndroidTVController(host=atv_ip, cert_file=atv_cert, key_file=atv_key)
                    ok = await tv.connect(timeout=5.0, settle=0.3)
                    if not ok:
                        tv.disconnect()
                        return None
                    await tv.set_volume(vol)
                    st = tv.get_status_dict()
                    tv.disconnect()
                    return st.get("volume_pct", vol)

                res_vol = asyncio.run(_adjust_volume())
                if res_vol is not None:
                    dev["status"]["volume_pct"] = int(res_vol)
                    dev["connectivity"] = "online"
                    self._save_devices()
                    return {
                        "ok": True,
                        "simulated": False,
                        "mode_label": f"[LIVE ANDROID TV ({atv_ip})]",
                        "device": dev["name"],
                        "volume_pct": dev["status"]["volume_pct"],
                        "status": dev["status"],
                        "message": f"Volume on {dev['name']} set to {dev['status']['volume_pct']}%.",
                    }
            except Exception as exc:
                print(f"[DeviceManager] AndroidTVController volume error: {exc}")

        # 4. Launch TV App (YouTube, Netflix, Prime Video, VLC, etc.)
        if act == "launch_app":
            app_key = (app_name or "youtube").strip().lower().replace(" ", "_")
            try:
                import asyncio
                async def _launch():
                    tv = AndroidTVController(host=atv_ip, cert_file=atv_cert, key_file=atv_key)
                    ok = await tv.connect(timeout=4.0, settle=0.3)
                    if not ok:
                        tv.disconnect()
                        return False
                    ok_l = await tv.launch_app(app_key)
                    tv.disconnect()
                    return ok_l

                ok_launch = asyncio.run(_launch())
                if ok_launch:
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
                        "status": dev["status"],
                        "message": f"Launched {dev['status']['current_app']} on {dev['name']}.",
                    }
            except Exception as exc:
                print(f"[DeviceManager] AndroidTVController launch error: {exc}")

        # 5. Cast / Open Media URL on TV
        if act in ("cast_url", "open_url"):
            if not media_url:
                return {"ok": False, "error": "media_url is required for cast_url."}
            try:
                import asyncio
                async def _cast():
                    tv = AndroidTVController(host=atv_ip, cert_file=atv_cert, key_file=atv_key)
                    ok = await tv.connect(timeout=4.0, settle=0.3)
                    if not ok:
                        tv.disconnect()
                        return False
                    ok_c = await tv.launch_app(media_url)
                    tv.disconnect()
                    return ok_c

                ok_cast = asyncio.run(_cast())
                if ok_cast:
                    dev["status"]["last_url"] = media_url
                    dev["status"]["power"] = "on"
                    dev["connectivity"] = "online"
                    self._save_devices()
                    return {
                        "ok": True,
                        "simulated": False,
                        "mode_label": f"[LIVE ANDROID TV ({atv_ip})]",
                        "device": dev["name"],
                        "media_url": media_url,
                        "status": dev["status"],
                        "message": f"Casting URL to {dev['name']}.",
                    }
            except Exception as exc:
                print(f"[DeviceManager] AndroidTVController cast error: {exc}")

        # Simulated fallback if offline
        dev["status"]["current_app"] = app_name or dev["status"].get("current_app", "Home")
        if volume_pct is not None:
            dev["status"]["volume_pct"] = volume_pct
        self._save_devices()
        return {
            "ok": True,
            "simulated": True,
            "mode_label": "[SIMULATED ANDROID TV]",
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

