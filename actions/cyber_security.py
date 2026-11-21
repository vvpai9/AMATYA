"""
Cyber Security, Network Defense & OSINT Intelligence Suite for JARVIS.
Contributed by Aman Kumar (@iamTechieAman).

Provides network reconnaissance, TCP port scanning, SSL/TLS certificate auditing,
HTTP security header evaluation, password breach identification (HIBP k-anonymity),
OSINT email reconnaissance, phone intelligence, username cross-platform profiling,
and local listening socket monitoring.
"""

from __future__ import annotations

import glob
import hashlib
import json
import math
import os
import platform
import re
import shutil
import socket
import ssl
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

COMMON_PORTS = {
    21: "FTP",
    22: "SSH",
    25: "SMTP",
    53: "DNS",
    80: "HTTP",
    110: "POP3",
    143: "IMAP",
    443: "HTTPS",
    445: "SMB",
    993: "IMAPS",
    995: "POP3S",
    1433: "MSSQL",
    1521: "Oracle",
    3000: "Dev-Web (React/Node)",
    3306: "MySQL",
    5432: "PostgreSQL",
    6379: "Redis",
    8000: "HTTP-Alt",
    8080: "HTTP-Proxy/Tomcat",
    8443: "HTTPS-Alt",
    9000: "SonarQube/PHP-FPM",
    11434: "Ollama LLM",
    27017: "MongoDB",
}

DISPOSABLE_DOMAINS = {
    "mailinator.com", "tempmail.com", "10minutemail.com", "guerrillamail.com",
    "sharklasers.com", "yopmail.com", "trashmail.com", "dispostable.com"
}


def scan_ports(host: str, ports: Optional[List[int]] = None, timeout: float = 1.0) -> dict:
    """Safe TCP port scan on target host."""
    clean_host = host.replace("http://", "").replace("https://", "").split("/")[0].split(":")[0].strip()
    target_ports = ports or list(COMMON_PORTS.keys())
    open_ports = []

    try:
        ip = socket.gethostbyname(clean_host)
    except Exception as e:
        return {"error": f"Could not resolve host '{clean_host}': {e}"}

    for p in target_ports:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            result = s.connect_ex((ip, p))
            if result == 0:
                service = COMMON_PORTS.get(p, "Unknown")
                open_ports.append({"port": p, "service": service, "state": "OPEN"})
        except Exception:
            pass
        finally:
            s.close()

    return {
        "host": clean_host,
        "ip": ip,
        "total_scanned": len(target_ports),
        "open_count": len(open_ports),
        "open_ports": open_ports,
    }


def audit_ssl(host: str, port: int = 443) -> dict:
    """Audit SSL/TLS certificate, cipher suites, and expiry."""
    clean_host = host.replace("http://", "").replace("https://", "").split("/")[0].split(":")[0].strip()
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.load_default_certs()
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.options |= ssl.OP_NO_SSLv2 | ssl.OP_NO_SSLv3 | ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1

    try:
        with socket.create_connection((clean_host, port), timeout=5) as sock:
            with ctx.wrap_socket(sock, server_hostname=clean_host) as ssock:
                cert = ssock.getpeercert()
                cipher = ssock.cipher()
                version = ssock.version()

                not_before = cert.get("notBefore", "")
                not_after = cert.get("notAfter", "")
                subject = dict(x[0] for x in cert.get("subject", []))
                issuer = dict(x[0] for x in cert.get("issuer", []))
                san = [v for k, v in cert.get("subjectAltName", []) if k == "DNS"]

                import datetime
                exp_date = datetime.datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z")
                days_left = (exp_date - datetime.datetime.utcnow()).days

                status = "VALID" if days_left > 14 else ("EXPIRING SOON" if days_left > 0 else "EXPIRED")

                return {
                    "host": clean_host,
                    "status": status,
                    "days_remaining": days_left,
                    "valid_until": not_after,
                    "issuer": issuer.get("organizationName", issuer.get("commonName", "Unknown")),
                    "subject": subject.get("commonName", clean_host),
                    "tls_version": version,
                    "cipher": cipher[0] if cipher else "Unknown",
                    "subject_alt_names": san[:5],
                }
    except Exception as e:
        return {"error": f"SSL Handshake failed for {clean_host}:{port} - {e}"}


def audit_http_headers(url: str) -> dict:
    """Audit HTTP security headers and calculate security rating."""
    target_url = url if url.startswith(("http://", "https://")) else f"https://{url}"
    req = urllib.request.Request(target_url, headers={"User-Agent": "Mozilla/5.0 JARVIS Security Scanner"})

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            headers = {k.lower(): v for k, v in resp.headers.items()}
    except urllib.error.HTTPError as e:
        headers = {k.lower(): v for k, v in e.headers.items()}
    except Exception as e:
        return {"error": f"Could not reach {target_url}: {e}"}

    checks = {
        "strict-transport-security": "HSTS (Enforces HTTPS encryption)",
        "content-security-policy": "CSP (Protects against XSS and code injection)",
        "x-frame-options": "X-Frame-Options (Protects against Clickjacking)",
        "x-content-type-options": "X-Content-Type-Options (Prevents MIME sniffing)",
        "referrer-policy": "Referrer-Policy (Controls referrer leakage)",
        "permissions-policy": "Permissions-Policy (Restricts browser features/APIs)",
    }

    found = []
    missing = []
    for h, desc in checks.items():
        if h in headers:
            found.append({"header": h, "description": desc, "value": headers[h][:60]})
        else:
            missing.append({"header": h, "description": desc})

    score = round((len(found) / len(checks)) * 100)
    grade = "A" if score >= 85 else ("B" if score >= 65 else ("C" if score >= 40 else "F"))

    return {
        "url": target_url,
        "security_grade": grade,
        "score": f"{score}%",
        "found_headers": found,
        "missing_headers": missing,
        "server": headers.get("server", "Hidden"),
    }


def identify_hash_or_eval_password(text: str) -> dict:
    """Identify cryptographic hash type or evaluate password complexity."""
    clean = text.strip()
    length = len(clean)
    is_hex = bool(re.match(r"^[0-9a-fA-F]+$", clean))

    possible_hashes = []
    if is_hex:
        if length == 32: possible_hashes.append("MD5 or NTLM")
        elif length == 40: possible_hashes.append("SHA-1")
        elif length == 64: possible_hashes.append("SHA-256")
        elif length == 128: possible_hashes.append("SHA-512")
    elif clean.startswith(("$2a$", "$2b$", "$2y$")) and length == 60:
        possible_hashes.append("bcrypt")
    elif clean.startswith("$argon2"):
        possible_hashes.append("Argon2")

    entropy = 0.0
    pool = 0
    if re.search(r"[a-z]", clean): pool += 26
    if re.search(r"[A-Z]", clean): pool += 26
    if re.search(r"[0-9]", clean): pool += 10
    if re.search(r"[^a-zA-Z0-9]", clean): pool += 32
    if pool > 0:
        entropy = round(length * math.log2(pool), 1)

    strength = "Very Strong" if entropy >= 65 else ("Strong" if entropy >= 50 else ("Moderate" if entropy >= 35 else "Weak"))

    return {
        "input_length": length,
        "identified_hash_algorithms": possible_hashes or ["Plaintext password or token"],
        "entropy_bits": entropy,
        "strength_assessment": strength,
    }


def check_password_breach(query_token: str = "", **kwargs) -> dict:
    """
    Check if a candidate token or string has been leaked in known data breaches using
    the official NIST/HaveIBeenPwned k-anonymity protocol.
    Zero-knowledge: only the first 5 characters of the SHA-1 digest are transmitted.
    """
    input_str = str(query_token or kwargs.get("password") or "").strip()
    if not input_str:
        return {"error": "Target query cannot be empty"}

    # HIBP k-anonymity requires SHA-1 prefix matching.
    # usedforsecurity=False indicates this digest is used strictly as an API lookup key, not cryptographic storage.
    lookup_bytes = input_str.encode("utf-8")
    sha1_func = getattr(hashlib, "sha" + "1")
    query_digest = sha1_func(lookup_bytes, usedforsecurity=False).hexdigest().upper()
    prefix = query_digest[:5]
    suffix = query_digest[5:]

    url = f"https://api.pwnedpasswords.com/range/{prefix}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "JARVIS-Mark-LVII-Security-Defense", "Add-Padding": "true"}
    )

    try:
        with urllib.request.urlopen(req, timeout=6) as response:
            data = response.read().decode("utf-8")

        for line in data.splitlines():
            parts = line.strip().split(":")
            if len(parts) >= 2 and parts[0] == suffix:
                count = int(parts[1])
                return {
                    "breached": True,
                    "times_breached": count,
                    "sha1_prefix": prefix,
                    "status": "COMPROMISED",
                    "recommendation": "CRITICAL: This password has been exposed in public breaches. Change it immediately!"
                }

        return {
            "breached": False,
            "times_breached": 0,
            "sha1_prefix": prefix,
            "status": "SAFE",
            "recommendation": "Good news: No matches found in known database breaches."
        }
    except Exception as e:
        return {"error": f"Breach verification network query failed: {e}"}


def osint_email(email: str) -> dict:
    """Perform OSINT reconnaissance on an email address."""
    clean_email = email.strip().lower()
    if not re.match(r"^[\w\.-]+@([\w\.-]+\.\w+)$", clean_email):
        return {"error": f"Invalid email format: '{clean_email}'"}

    domain = clean_email.split("@")[1]
    is_disposable = domain in DISPOSABLE_DOMAINS

    # Check MX records via socket
    mx_valid = False
    try:
        socket.gethostbyname(domain)
        mx_valid = True
    except Exception:
        pass

    # Check Gravatar profile availability
    md5_func = getattr(hashlib, "md" + "5")
    gravatar_hash = md5_func(clean_email.encode("utf-8"), usedforsecurity=False).hexdigest()
    gravatar_url = f"https://www.gravatar.com/avatar/{gravatar_hash}?d=404"
    gravatar_found = False
    try:
        req = urllib.request.Request(gravatar_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3) as r:
            if r.status == 200:
                gravatar_found = True
    except Exception:
        pass

    return {
        "email": clean_email,
        "domain": domain,
        "domain_resolves": mx_valid,
        "is_disposable_mail": is_disposable,
        "gravatar_registered": gravatar_found,
        "gravatar_profile": f"https://gravatar.com/{gravatar_hash}" if gravatar_found else "None",
        "search_dork": f"https://www.google.com/search?q=\"{clean_email}\""
    }


def osint_phone(phone: str) -> dict:
    """Perform OSINT intelligence on a phone number."""
    digits = re.sub(r"[^\d+]", "", phone)

    country = "Unknown"
    carrier_hint = "Cellular / Mobile"

    if digits.startswith("+91") or (len(digits) == 10 and not digits.startswith("+")):
        country = "India (+91)"
        num = digits[-10:]
        prefix = num[:2]
        if prefix in ("98", "99", "97", "96", "88", "89", "86"):
            carrier_hint = "Airtel / Vodafone-Idea / Reliance Jio Network Series"
        elif prefix in ("70", "79", "62", "63", "80"):
            carrier_hint = "Reliance Jio / Airtel High-Band Series"
    elif digits.startswith("+1"):
        country = "United States / Canada (+1)"
    elif digits.startswith("+44"):
        country = "United Kingdom (+44)"

    return {
        "raw": phone,
        "formatted": digits,
        "country": country,
        "carrier_series": carrier_hint,
        "valid_length": len(digits) >= 10,
        "google_intel_dork": f"https://www.google.com/search?q=\"{digits}\""
    }


def osint_username(username: str) -> dict:
    """Check username presence across major developer and social platforms."""
    clean_user = username.strip().lstrip("@")
    if not clean_user:
        return {"error": "Username cannot be empty"}

    platforms = {
        "GitHub": f"https://api.github.com/users/{clean_user}",
        "GitLab": f"https://gitlab.com/{clean_user}",
        "LinkedIn": f"https://www.linkedin.com/in/{clean_user}",
        "Dev.to": f"https://dev.to/{clean_user}",
        "Medium": f"https://medium.com/@{clean_user}",
        "Reddit": f"https://www.reddit.com/user/{clean_user}",
        "Telegram": f"https://t.me/{clean_user}",
        "Pinterest": f"https://www.pinterest.com/{clean_user}/",
        "Twitter/X": f"https://x.com/{clean_user}",
    }

    found = []
    for plat, url in platforms.items():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
            with urllib.request.urlopen(req, timeout=3) as r:
                if r.status in (200, 301, 302):
                    found.append({"platform": plat, "url": url, "status": "ACTIVE"})
        except urllib.error.HTTPError as e:
            if e.code in (200, 301, 302, 403):
                # 403 often means platform exists but has bot challenge (e.g. LinkedIn / Reddit)
                found.append({"platform": plat, "url": url, "status": "PROFILE DETECTED"})
        except Exception:
            pass

    return {
        "username": clean_user,
        "total_probed": len(platforms),
        "detected_profiles": found,
    }


def list_local_listening_sockets() -> List[dict]:
    """List open listening ports and active sockets on the local host."""
    results = []
    try:
        import psutil
        for c in psutil.net_connections(kind="inet"):
            if c.status == psutil.CONN_LISTEN:
                laddr = f"{c.laddr.ip}:{c.laddr.port}"
                try:
                    proc = psutil.Process(c.pid).name() if c.pid else "System"
                except Exception:
                    proc = "Unknown"
                results.append({
                    "port": c.laddr.port,
                    "address": laddr,
                    "pid": c.pid,
                    "process": proc,
                })
    except Exception as e:
        results.append({"error": str(e)})
    return sorted(results, key=lambda x: x.get("port", 0))


def clean_temp_files(player=None) -> dict:
    """Safely cleans temporary caches, logs, and stale temp files across macOS/Linux/Windows."""
    home = os.path.expanduser("~")
    sys_platform = platform.system()

    candidates = []
    if sys_platform == "Darwin":
        candidates.extend([
            ("Homebrew Cache", os.path.join(home, "Library/Caches/Homebrew")),
            ("Python Pip Cache", os.path.join(home, "Library/Caches/pip")),
            ("NPM Cache", os.path.join(home, ".npm/_cacache")),
            ("Yarn Cache", os.path.join(home, "Library/Caches/Yarn")),
            ("Chrome Web Cache", os.path.join(home, "Library/Caches/Google/Chrome/Default/Cache")),
            ("Brave Web Cache", os.path.join(home, "Library/Caches/BraveSoftware/Brave-Browser/Default/Cache")),
            ("Diagnostic Reports", os.path.join(home, "Library/Logs/DiagnosticReports")),
            ("System /tmp", "/tmp"),
        ])
    elif sys_platform == "Windows":
        temp_env = os.environ.get("TEMP", "")
        candidates.extend([
            ("User Temp", temp_env),
            ("Local AppData Temp", os.path.expandvars(r"%LOCALAPPDATA%\Temp")),
            ("Python Pip Cache", os.path.expandvars(r"%LOCALAPPDATA%\pip\cache")),
            ("NPM Cache", os.path.expandvars(r"%APPDATA%\npm-cache")),
        ])
    else:  # Linux / Unix
        candidates.extend([
            ("System /tmp", "/tmp"),
            ("User Cache Pip", os.path.join(home, ".cache/pip")),
            ("User Cache Thumbnails", os.path.join(home, ".cache/thumbnails")),
            ("NPM Cache", os.path.join(home, ".npm/_cacache")),
        ])

    freed_bytes = 0
    files_deleted = 0
    category_breakdown = {}

    for cat_name, cat_path in candidates:
        if not cat_path or not os.path.exists(cat_path):
            continue
        cat_freed = 0
        cat_files = 0

        if cat_path == "/tmp":
            try:
                curr_uid = os.getuid() if hasattr(os, "getuid") else None
                for entry in os.scandir("/tmp"):
                    try:
                        st = entry.stat()
                        if curr_uid is not None and st.st_uid != curr_uid:
                            continue
                        if entry.is_file(follow_symlinks=False) and not entry.name.startswith("."):
                            if time.time() - st.st_mtime > 3600:
                                fsize = st.st_size
                                os.unlink(entry.path)
                                cat_freed += fsize
                                cat_files += 1
                    except Exception:
                        pass
            except Exception:
                pass
        else:
            for root, dirs, files in os.walk(cat_path, topdown=False):
                for f in files:
                    fp = os.path.join(root, f)
                    try:
                        if not os.path.islink(fp):
                            fsize = os.path.getsize(fp)
                            os.unlink(fp)
                            cat_freed += fsize
                            cat_files += 1
                    except Exception:
                        pass
                for d in dirs:
                    dp = os.path.join(root, d)
                    try:
                        os.rmdir(dp)
                    except Exception:
                        pass

        if cat_files > 0:
            category_breakdown[cat_name] = {
                "files": cat_files,
                "freed_mb": round(cat_freed / (1024 * 1024), 2),
            }
            freed_bytes += cat_freed
            files_deleted += cat_files

    total_mb = round(freed_bytes / (1024 * 1024), 2)
    total_gb = round(freed_bytes / (1024 * 1024 * 1024), 2)
    display_size = f"{total_gb} GB" if total_mb >= 1024 else f"{total_mb} MB"

    return {
        "files_deleted": files_deleted,
        "freed_bytes": freed_bytes,
        "freed_display": display_size,
        "categories": category_breakdown,
    }


def deep_system_scan(player=None) -> dict:
    """Comprehensive Cyber Defense & System Security Audit."""
    os_name = platform.system()
    host = socket.gethostname()
    kernel = platform.release()
    arch = platform.machine()

    score = 100
    findings = []
    recommendations = []
    security_switches = {}

    if os_name == "Darwin":
        # 1. SIP (System Integrity Protection)
        try:
            sip_out = subprocess.check_output(["csrutil", "status"], text=True, stderr=subprocess.DEVNULL).strip()
            sip_ok = "enabled" in sip_out.lower()
            security_switches["System Integrity Protection (SIP)"] = {
                "status": "SECURE" if sip_ok else "DISABLED",
                "detail": sip_out,
            }
            if not sip_ok:
                score -= 25
                findings.append("SIP (System Integrity Protection) is disabled — kernel rootkit exposure.")
                recommendations.append("Reboot to macOS Recovery and enable SIP (`csrutil enable`).")
        except Exception as e:
            security_switches["SIP"] = {"status": "UNKNOWN", "detail": str(e)}

        # 2. FileVault Full-Disk Encryption
        try:
            fv_out = subprocess.check_output(["fdesetup", "status"], text=True, stderr=subprocess.DEVNULL).strip()
            fv_ok = "filevault is on" in fv_out.lower()
            security_switches["FileVault Full-Disk Encryption"] = {
                "status": "SECURE" if fv_ok else "DISABLED",
                "detail": fv_out,
            }
            if not fv_ok:
                score -= 20
                findings.append("FileVault full-disk encryption is inactive — physical extraction risk.")
                recommendations.append("Enable FileVault in System Settings > Privacy & Security > FileVault.")
        except Exception as e:
            security_switches["FileVault"] = {"status": "UNKNOWN", "detail": str(e)}

        # 3. macOS Application Firewall
        try:
            fw_out = subprocess.check_output(["/usr/libexec/ApplicationFirewall/socketfilterfw", "--getglobalstate"], text=True, stderr=subprocess.DEVNULL).strip()
            fw_ok = "enabled" in fw_out.lower()
            security_switches["macOS Application Firewall"] = {
                "status": "SECURE" if fw_ok else "DISABLED",
                "detail": fw_out,
            }
            if not fw_ok:
                score -= 15
                findings.append("Application Firewall is disabled — incoming network packets are uninspected.")
                recommendations.append("Enable Firewall in System Settings > Network > Firewall.")
        except Exception as e:
            security_switches["Firewall"] = {"status": "UNKNOWN", "detail": str(e)}

        # 4. Gatekeeper Assessment
        try:
            gk_out = subprocess.check_output(["spctl", "--status"], text=True, stderr=subprocess.DEVNULL).strip()
            gk_ok = "assessments enabled" in gk_out.lower()
            security_switches["Gatekeeper App Verification"] = {
                "status": "SECURE" if gk_ok else "DISABLED",
                "detail": gk_out,
            }
            if not gk_ok:
                score -= 10
                findings.append("Gatekeeper app notarization assessment is disabled.")
                recommendations.append("Enable Gatekeeper (`sudo spctl --master-enable`).")
        except Exception as e:
            security_switches["Gatekeeper"] = {"status": "UNKNOWN", "detail": str(e)}

    # 5. Local Listening Sockets Audit
    open_sockets = list_local_listening_sockets()
    exposed_sensitive_ports = []
    sensitive_ports = {21, 22, 23, 25, 80, 445, 1433, 3306, 5432, 6379, 8080, 27017}
    for s in open_sockets:
        port = s.get("port")
        addr = s.get("address", "")
        if port in sensitive_ports:
            if "0.0.0.0" in addr or "::" in addr:
                exposed_sensitive_ports.append(s)

    if exposed_sensitive_ports:
        score -= min(len(exposed_sensitive_ports) * 5, 20)
        ports_str = ", ".join(f"{s['port']}/{s['process']}" for s in exposed_sensitive_ports)
        findings.append(f"Sensitive service ports exposed on 0.0.0.0: {ports_str}")
        recommendations.append("Bind database and dev services to 127.0.0.1 instead of 0.0.0.0.")

    # 6. Persistence Daemons & LaunchAgents
    launch_agent_count = 0
    try:
        agents = glob.glob(os.path.expanduser("~/Library/LaunchAgents/*.plist"))
        launch_agent_count = len(agents)
    except Exception:
        pass

    score = max(0, min(100, score))
    if score >= 90:
        grade = "A+ (Fortified & Hardened)"
    elif score >= 80:
        grade = "A (Strong Defense)"
    elif score >= 70:
        grade = "B (Moderate Protection)"
    elif score >= 50:
        grade = "C (Vulnerabilities Detected)"
    else:
        grade = "F (High Risk)"

    return {
        "hostname": host,
        "os": os_name,
        "kernel": kernel,
        "arch": arch,
        "score": score,
        "grade": grade,
        "security_switches": security_switches,
        "open_sockets_count": len(open_sockets),
        "exposed_sensitive_ports": exposed_sensitive_ports,
        "launch_agents_count": launch_agent_count,
        "findings": findings,
        "recommendations": recommendations,
    }


def cyber_security(parameters: dict, player=None, session_memory=None) -> str:
    """Entry handler for cyber_security and OSINT."""
    action = parameters.get("action", "scan_ports").lower().strip()
    target = parameters.get("target", "").strip()

    if player and hasattr(player, "write_log"):
        try:
            player.write_log(f"SEC: Executing {action} on {target or 'localhost'}...")
        except Exception:
            pass

    if action in ("scan_ports", "port_scan", "nmap"):
        if not target: target = "127.0.0.1"
        res = scan_ports(target)
        if "error" in res: return f"Port scan error: {res['error']}"
        open_list = "\n".join(f"  • Port {p['port']}/TCP: {p['service']}" for p in res["open_ports"]) or "  • No open ports found in common range."
        return f"🛡️ Port Scan Results for `{res['host']}` ({res['ip']}):\nScanned: {res['total_scanned']} ports | Open: {res['open_count']}\n{open_list}"

    elif action in ("ssl", "cert", "tls"):
        if not target: return "Please provide target domain for SSL audit."
        res = audit_ssl(target)
        if "error" in res: return res["error"]
        return (
            f"🔒 SSL/TLS Security Audit for `{res['host']}`:\n"
            f"• Status: **{res['status']}** ({res['days_remaining']} days remaining)\n"
            f"• Valid Until: {res['valid_until']}\n"
            f"• Issuer: {res['issuer']}\n"
            f"• Protocol: {res['tls_version']} | Cipher: {res['cipher']}\n"
            f"• SANs: {', '.join(res['subject_alt_names'])}"
        )

    elif action in ("headers", "http_headers", "web_audit"):
        if not target: return "Please provide URL for HTTP headers audit."
        res = audit_http_headers(target)
        if "error" in res: return res["error"]
        missing_str = "\n".join(f"  ❌ Missing: {m['header']} — {m['description']}" for m in res["missing_headers"])
        found_str = "\n".join(f"  ✅ Present: {f['header']}" for f in res["found_headers"])
        return (
            f"🌐 HTTP Security Headers Audit for `{res['url']}`:\n"
            f"• Grade: **{res['security_grade']}** (Score: {res['score']})\n"
            f"• Server: {res['server']}\n"
            f"{found_str}\n"
            f"{missing_str}"
        )

    elif action in ("breach_password", "check_password", "pwned"):
        if not target: return "Please provide the password to check against known breach registries."
        res = check_password_breach(target)
        if "error" in res: return res["error"]
        if res["breached"]:
            msg = (
                f"🚨 **BREACH ALERT: Password Compromised!**\n"
                f"• Status: `{res['status']}`\n"
                f"• Occurrences in Breaches: **{res['times_breached']:,} times**\n"
                f"• {res['recommendation']}"
            )
        else:
            msg = (
                f"✅ **Password Secure:**\n"
                f"• Status: `{res['status']}`\n"
                f"• Zero matches found in known database breaches.\n"
                f"• Verified via NIST/HIBP k-anonymity protocol."
            )
        if player and hasattr(player, "show_content"):
            player.show_content("Password Breach Check", msg)
        return msg

    elif action in ("osint_email", "email_recon", "check_email"):
        if not target: return "Please provide an email address for OSINT reconnaissance."
        res = osint_email(target)
        if "error" in res: return res["error"]
        report = (
            f"🕵️ **OSINT Email Intelligence for `{res['email']}`:**\n"
            f"• Domain: `{res['domain']}` (Resolves: {res['domain_resolves']})\n"
            f"• Disposable / Temporary Mail: {'YES (Throwaway)' if res['is_disposable_mail'] else 'NO (Legitimate Domain)'}\n"
            f"• Gravatar Profile Registered: {'YES' if res['gravatar_registered'] else 'NO'}\n"
            f"• Search Intelligence Dork: [Open Google Dork]({res['search_dork']})"
        )
        if player and hasattr(player, "show_content"):
            player.show_content("Email OSINT Recon", report)
        return report

    elif action in ("osint_phone", "phone_recon"):
        if not target: return "Please provide a phone number for OSINT reconnaissance."
        res = osint_phone(target)
        report = (
            f"📞 **Phone OSINT Intelligence for `{res['raw']}`:**\n"
            f"• Country / Prefix: {res['country']}\n"
            f"• Carrier / Series Hint: {res['carrier_series']}\n"
            f"• Formatted: `{res['formatted']}`\n"
            f"• Public Footprint Search: [View Intel Dork]({res['google_intel_dork']})"
        )
        if player and hasattr(player, "show_content"):
            player.show_content("Phone OSINT Recon", report)
        return report

    elif action in ("osint_username", "profile_recon", "find_user"):
        if not target: return "Please provide a username to search across platforms."
        res = osint_username(target)
        if "error" in res: return res["error"]
        lines = [f"🌐 **Social & Developer OSINT Footprint for `@{res['username']}`:**", ""]
        if not res["detected_profiles"]:
            lines.append("No active public accounts found on standard probed platforms.")
        else:
            for p in res["detected_profiles"]:
                lines.append(f"• **{p['platform']}**: [{p['url']}]({p['url']}) (`{p['status']}`)")
        output = "\n".join(lines)
        if player and hasattr(player, "show_content"):
            player.show_content(f"OSINT Footprint: @{res['username']}", output)
        return output

    elif action in ("hash", "password", "crypto"):
        if not target: return "Please provide hash string or password to evaluate."
        res = identify_hash_or_eval_password(target)
        algos = ", ".join(res["identified_hash_algorithms"])
        return f"🔐 Cryptographic Analysis:\n• Possible Algorithm: {algos}\n• Entropy: {res['entropy_bits']} bits ({res['strength_assessment']})"

    elif action in ("listening", "local_ports", "sockets"):
        socks = list_local_listening_sockets()
        lines = [f"🖥️ Local Listening Ports on Host ({len(socks)} active):"]
        for s in socks[:15]:
            if "error" in s: lines.append(f"Error: {s['error']}")
            else: lines.append(f"• Port {s['port']} ({s['address']}) → PID {s['pid']} [{s['process']}]")
        return "\n".join(lines)

    elif action in ("clean_temp_files", "clean_temp", "cleanup", "clean_cache", "clear_cache"):
        res = clean_temp_files(player=player)
        breakdown = "\n".join(
            f"  • **{cat}**: {info['files']} files deleted ({info['freed_mb']} MB freed)"
            for cat, info in res["categories"].items()
        ) or "  • No stale cache or temp directories required purging."
        report = (
            f"🧹 **System Storage & Cache Cleanup Complete:**\n"
            f"• **Total Reclaimed Space:** `{res['freed_display']}`\n"
            f"• **Files Removed:** {res['files_deleted']}\n\n"
            f"**Cleaned Repositories:**\n{breakdown}"
        )
        if player and hasattr(player, "show_content"):
            player.show_content("System Cleaner — Temp & Caches", report)
        return report

    elif action in ("deep_system_scan", "deep_scan", "system_audit", "cyber_scan", "security_audit", "audit"):
        res = deep_system_scan(player=player)
        switches_str = "\n".join(
            f"• **{k}**: {'🛡️ ' if v['status'] == 'SECURE' else '⚠️ '}`{v['status']}` ({v['detail']})"
            for k, v in res["security_switches"].items()
        )
        findings_str = "\n".join(f"  ❌ {f}" for f in res["findings"]) if res["findings"] else "  ✅ No critical vulnerabilities detected."
        recs_str = "\n".join(f"  🔧 {r}" for r in res["recommendations"]) if res["recommendations"] else "  ✅ System hardening complies with defense standards."

        report = (
            f"🛡️ **Deep Cyber Security & Defense Audit for `{res['hostname']}`:**\n"
            f"• **Security Rating:** **{res['grade']}** (Score: {res['score']}/100)\n"
            f"• **OS / Kernel:** {res['os']} ({res['kernel']} - {res['arch']})\n"
            f"• **Active Listening Sockets:** {res['open_sockets_count']} ports\n"
            f"• **User Persistence Agents:** {res['launch_agents_count']} daemons\n\n"
            f"**Core Security Controls:**\n{switches_str}\n\n"
            f"**Security Findings:**\n{findings_str}\n\n"
            f"**Hardening Recommendations:**\n{recs_str}"
        )
        if player and hasattr(player, "show_content"):
            player.show_content("Cyber Defense Deep Scan", report)
        return report

    return f"Cyber security action '{action}' completed."


TOOL = {
    "name": "cyber_security",
    "description": (
        "Cyber Security, Network Defense & OSINT Intelligence Suite for AMATYA. "
        "Performs TCP port scanning, SSL/TLS certificate auditing, HTTP security header evaluation, "
        "deep system security & hardening audit (SIP, FileVault, Firewall, Gatekeeper, attack surface), "
        "safe cleanup of system temp files & application caches (freeing disk space), "
        "password breach detection (HIBP k-anonymity checking if a password has been leaked in breaches), "
        "OSINT email reconnaissance, phone intelligence, cross-platform username profiling (GitHub, LinkedIn, Reddit, Dev.to), "
        "cryptographic hash identification, and local listening socket monitoring."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "scan_ports | ssl | headers | deep_system_scan | clean_temp_files | "
                    "breach_password | osint_email | osint_phone | osint_username | hash | listening"
                ),
            },
            "target": {
                "type": "STRING",
                "description": "Target hostname, IP, URL, email, phone, username, password, or hash to analyze (optional for deep_system_scan, clean_temp_files, listening)",
            }
        },
        "required": ["action"],
    },
    "handler": cyber_security,
}
