# Stark Tactical Cyber Defense Matrix

AMATYA equips the user with a JARVIS-class defensive security matrix powered by `actions/cyber_sentry.py` and the `skills/cyber-defense` skill.

---

## 1. Capabilities & Tools

The `cyber_sentry` tool provides 5 core tactical assessment actions:

### 1. Perimeter Scan (`perimeter_scan`)
- Discovers host network interfaces, active IPv4/IPv6 addresses, MAC addresses, default gateway, and external IP routing.
- Inspects system hostname, domain bindings, and active DNS resolvers.

### 2. Local & LAN Open Port Audit (`scan_ports`)
- Probes system network sockets and LAN listeners.
- Audits critical service ports including SSH (22), HTTP (80), HTTPS (443), VNC (5900), Redis (6379), PostgreSQL (5432), and dev servers (3000, 8000, 8080).
- Flags unexpected listening services and unencrypted endpoints.

### 3. Native Firewall Status Audit (`audit_firewall`)
- Cross-platform inspection of host firewall engines:
  - **Linux:** Audits `ufw`, `nftables`, and `iptables`.
  - **macOS:** Inspects `pfctl` and Application Firewall (`socketfilterfw`).
  - **Windows:** Queries Windows Defender Firewall status across Domain, Private, and Public profiles.
- Alerts if the host firewall is inactive or has permissive forward rules.

### 4. Authentication Intrusion Auditing (`auth_audit`)
- Analyzes system security logs (`/var/log/auth.log`, systemd `journalctl -u ssh`, or Windows Security Event Log).
- Identifies failed password attempts, invalid user brute-force attacks, and IP sources with repeated authentication failures.

### 5. File System Privilege & Permission Audit (`file_permissions`)
- Scans system directories for dangerous SUID/SGID root binaries.
- Identifies world-writable directories and files in sensitive paths.

---

## 2. Spoken Voice Commands

You can trigger security operations naturally by speaking to AMATYA:
- *"Run a perimeter scan"*
- *"Scan open ports on this machine"*
- *"Audit the firewall status"*
- *"Check auth logs for intrusion attempts"*
- *"Check system file permissions and SUID binaries"*
- *"Report tactical security status"*

---

## 3. Security Boundary & Fail-Closed Policy

All actions in the Stark Tactical Matrix operate under AMATYA's centralized Security Gateway (`core/security.py`).
- Read-only diagnostics are permitted under `PermissionTier.GENERAL_CONVERSATION`.
- Any external packet transmission is strictly restricted to loopback and LAN targets unless elevated by the user.
- Unregistered tools or parameters fail closed automatically.
