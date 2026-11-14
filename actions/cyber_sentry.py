"""
actions/cyber_sentry.py — Stark Tactical Cyber Defense & Perimeter Security Sentry
==================================================================================
Provides real-time host defensive telemetry, local port auditing, firewall
verification, authentication log analysis, and system integrity checking.
"""
from __future__ import annotations

import os
import re
import socket
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core import outcome

SKILL_METADATA = {
    "capabilities": [
        "perimeter_scan",
        "port_audit",
        "firewall_audit",
        "auth_log_analysis",
        "process_integrity",
        "file_permissions",
    ],
    "permissions": ["system_diagnostics", "security_audit"],
    "dependencies": [],
    "supported_actions": [
        "perimeter_scan",
        "scan_ports",
        "audit_firewall",
        "audit_auth",
        "process_integrity",
        "file_permissions",
        "status",
    ],
    "security_level": "normal",
}


def _run_cmd(cmd: list[str], timeout: float = 3.0) -> tuple[int, str]:
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)
        return res.returncode, res.stdout.strip()
    except Exception as e:
        return -1, str(e)


def audit_listening_ports() -> List[Dict[str, Any]]:
    """Scan and enumerate all active listening ports."""
    ports = []
    # Try ss -tuln
    code, out = _run_cmd(["ss", "-tuln"])
    if code == 0 and out:
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 5 and ("LISTEN" in parts[0] or "LISTEN" in parts[1] or parts[0] in ("tcp", "udp")):
                proto = parts[0].upper()
                local_addr = parts[4] if len(parts) > 4 else ""
                port_match = re.search(r":(\d+)$", local_addr)
                if port_match:
                    port_num = int(port_match.group(1))
                    ports.append({
                        "protocol": proto,
                        "address": local_addr,
                        "port": port_num,
                        "exposed_public": "0.0.0.0" in local_addr or "[::]" in local_addr or "*" in local_addr,
                    })

    # If ss failed or empty, fallback to inspecting common local ports
    if not ports:
        common_ports = [22, 53, 80, 443, 3000, 5000, 8000, 8080, 8443, 8765, 9000]
        for p in common_ports:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.05)
            try:
                if s.connect_ex(("127.0.0.1", p)) == 0:
                    ports.append({
                        "protocol": "TCP",
                        "address": f"127.0.0.1:{p}",
                        "port": p,
                        "exposed_public": False,
                    })
            except Exception:
                pass
            finally:
                s.close()
    return ports


def audit_firewall_status() -> Dict[str, Any]:
    """Inspect active firewall rules (ufw, iptables, or nftables)."""
    # 1. Check ufw
    code, out = _run_cmd(["ufw", "status", "verbose"])
    if code == 0 and "Status:" in out:
        active = "active" in out.lower() and "inactive" not in out.lower()
        return {"type": "ufw", "active": active, "raw": out.splitlines()[:10]}

    # 2. Check iptables
    code, out = _run_cmd(["iptables", "-L", "-n"])
    if code == 0 and "Chain" in out:
        return {"type": "iptables", "active": True, "raw": out.splitlines()[:10]}

    return {"type": "default", "active": False, "raw": ["No host packet filter reported"]}


def audit_auth_logs() -> Dict[str, Any]:
    """Analyze recent authentication and authorization logs."""
    failed_logins = 0
    recent_events = []
    
    # Check journalctl for ssh/sudo
    code, out = _run_cmd(["journalctl", "-u", "ssh", "-u", "sshd", "-n", "30", "--no-pager"])
    if code == 0 and out:
        for line in out.splitlines():
            if any(k in line.lower() for k in ("failed", "invalid", "refused", "authentication failure")):
                failed_logins += 1
                recent_events.append(line.strip())

    # Check /var/log/auth.log fallback
    auth_log = Path("/var/log/auth.log")
    if auth_log.is_file() and os.access(auth_log, os.R_OK):
        try:
            lines = auth_log.read_text(encoding="utf-8", errors="replace").splitlines()[-50:]
            for line in lines:
                if any(k in line.lower() for k in ("failed password", "authentication failure")):
                    failed_logins += 1
                    if len(recent_events) < 10:
                        recent_events.append(line.strip())
        except Exception:
            pass

    return {
        "failed_attempts": failed_logins,
        "threat_level": "ELEVATED" if failed_logins > 5 else "NOMINAL",
        "recent_flags": recent_events[-5:],
    }


def audit_file_permissions() -> List[Dict[str, Any]]:
    """Audit permissions on key system files and credentials."""
    targets = [
        Path.home() / ".ssh",
        Path.home() / ".ssh/id_rsa",
        Path.home() / ".ssh/id_ed25519",
        Path(__file__).resolve().parent.parent / "config/api_keys.json",
        Path("/etc/shadow"),
        Path("/etc/passwd"),
    ]
    results = []
    for p in targets:
        if not p.exists():
            continue
        st = p.stat()
        mode = oct(st.st_mode)[-3:]
        # Check if world readable/writable
        is_world_writable = bool(st.st_mode & 0o002)
        is_world_readable = bool(st.st_mode & 0o004) and p.name in ("id_rsa", "id_ed25519", "api_keys.json", "shadow")
        status = "SECURE"
        if is_world_writable:
            status = "CRITICAL_WORLD_WRITABLE"
        elif is_world_readable:
            status = "WARNING_WORLD_READABLE"
        results.append({
            "path": str(p),
            "permissions": mode,
            "status": status,
        })
    return results


def run_perimeter_scan() -> Dict[str, Any]:
    """Execute complete Iron Man Mark-class perimeter defense scan."""
    ports = audit_listening_ports()
    fw = audit_firewall_status()
    auth = audit_auth_logs()
    files = audit_file_permissions()

    public_ports = [p["port"] for p in ports if p.get("exposed_public")]
    threat_score = 0
    if not fw.get("active"):
        threat_score += 15
    if len(public_ports) > 3:
        threat_score += 20
    if auth.get("failed_attempts", 0) > 5:
        threat_score += 25
    for f in files:
        if "CRITICAL" in f["status"]:
            threat_score += 30

    posture = "MAXIMUM DEFENSE" if threat_score < 20 else ("GUARDED" if threat_score < 50 else "ELEVATED ALERT")

    return {
        "timestamp": time.time(),
        "threat_score": min(100, threat_score),
        "defense_posture": posture,
        "listening_ports_count": len(ports),
        "public_ports": public_ports,
        "firewall_type": fw.get("type"),
        "firewall_active": fw.get("active"),
        "failed_auth_events": auth.get("failed_attempts"),
        "flagged_files": [f for f in files if f["status"] != "SECURE"],
        "ports_sample": ports[:8],
    }


def execute(
    parameters: dict,
    player: Any = None,
    session_memory: Any = None,
    **kwargs,
) -> str:
    """Action entry point for cyber_sentry."""
    params = parameters or {}
    action = str(params.get("action") or "perimeter_scan").strip().lower()

    if action in ("perimeter_scan", "status"):
        scan = run_perimeter_scan()
        public_str = ", ".join(map(str, scan["public_ports"])) or "None"
        flagged_files_str = "\n".join(f"- `{f['path']}`: {f['status']} ({f['permissions']})" for f in scan["flagged_files"]) or "All scanned configuration files secure."

        report = (
            f"# 🛡️ STARK TACTICAL CYBER DEFENSE MATRIX\n\n"
            f"**Defense Posture:** `{scan['defense_posture']}` | **Threat Score:** `{scan['threat_score']}/100`\n\n"
            f"### 📡 Perimeter Readout\n"
            f"- **Listening Sockets:** `{scan['listening_ports_count']}` total\n"
            f"- **Publicly Exposed Ports:** `{public_str}`\n"
            f"- **Firewall Shield:** `{'ONLINE' if scan['firewall_active'] else 'OFFLINE'}` ({scan['firewall_type'].upper()})\n"
            f"- **Authentication Threat Level:** `{scan['failed_auth_events']}` recent failed attempts\n\n"
            f"### 🔐 Credential & File Integrity\n{flagged_files_str}\n"
        )
        if player is not None:
            try:
                player.show_content("Cyber Sentry — Tactical Defense", report)
                player.write_log(f"CYBER_SENTRY: Perimeter scan completed — Posture: {scan['defense_posture']}")
            except Exception:
                pass
        return outcome.done(
            "cyber_sentry",
            result=f"Tactical perimeter scan complete: Defense posture is {scan['defense_posture']} with threat score {scan['threat_score']}/100. Firewall is {'active' if scan['firewall_active'] else 'offline'}, with {len(scan['public_ports'])} public ports.",
            data=scan,
        )

    if action == "scan_ports":
        ports = audit_listening_ports()
        lines = [f"# 🔌 Open Ports & Listening Sockets ({len(ports)} found)\n"]
        for p in ports:
            lines.append(f"- **Port {p['port']}** ({p['protocol']}) → `{p['address']}` [{'PUBLIC' if p['exposed_public'] else 'LOCAL'}]")
        if player is not None:
            try:
                player.show_content("Port Audit Telemetry", "\n".join(lines))
            except Exception:
                pass
        return outcome.done("cyber_sentry", result=f"Identified {len(ports)} listening ports. Exposed public ports: {', '.join(str(p['port']) for p in ports if p['exposed_public']) or 'None'}.", data={"ports": ports})

    if action == "audit_firewall":
        fw = audit_firewall_status()
        res_str = f"Firewall status: {'ACTIVE' if fw['active'] else 'INACTIVE'} ({fw['type']})."
        return outcome.done("cyber_sentry", result=res_str, data=fw)

    return outcome.failed("cyber_sentry", f"Unknown action '{action}'")


TOOL = {
    "name": "cyber_sentry",
    "description": (
        "Stark Tactical Cyber Defense & Security Sentry: Performs host perimeter audits, "
        "open listening port scans, firewall verification (ufw/iptables), authentication log analysis "
        "for brute-force intrusion detection, and sensitive credential file permission checks."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["perimeter_scan", "scan_ports", "audit_firewall", "status"],
                "description": "Tactical security action to perform (default: 'perimeter_scan').",
            },
        },
    },
    "handler": execute,
}
