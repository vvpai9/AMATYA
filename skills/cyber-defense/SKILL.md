---
name: cyber-defense
description: "Perform tactical host cybersecurity audits, perimeter port scanning, firewall inspection (UFW, iptables), auth log threat intelligence, and file permission integrity checks. Use whenever the user asks to 'scan perimeter', 'audit ports', 'check security status', 'run vulnerability scan', 'firewall check', or inspect host intrusion posture like Iron Man's JARVIS defense matrix."
license: Apache-2.0
---

# Stark Tactical Cyber Defense & Security Sentry

Provides autonomous host defensive posture auditing, network perimeter scanning, firewall rule verification, and suspicious auth monitoring.

## Capabilities

1. **Perimeter Defense Matrix (`perimeter_scan`):**
   - Correlates open ports, public exposure, active packet filters, and failed login threats into a normalized Defense Posture rating (`MAXIMUM DEFENSE`, `GUARDED`, `ELEVATED ALERT`).

2. **Listening Port Audit (`scan_ports`):**
   - Scans active TCP and UDP listening sockets.
   - Detects wildcard bindings (`0.0.0.0` or `[::]`) exposed to the external network.

3. **Firewall Verification (`audit_firewall`):**
   - Verifies whether UFW or iptables is running and enforces packet filtering policies.

4. **Authentication & Intrusion Monitoring (`audit_auth`):**
   - Analyzes recent authentication attempts in system journals and auth logs for brute-force patterns.

5. **File Permission & Credential Shield:**
   - Detects dangerous world-writable or world-readable permissions on SSH keys and credential vaults.
