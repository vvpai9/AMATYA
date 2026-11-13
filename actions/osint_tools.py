"""
actions/osint_tools.py — Open-Source Intelligence (OSINT) & Reconnaissance Subsystem
===================================================================================
Provides deep, passive, ethical open-source intelligence gathering across:
  1. Domain Intelligence: DNS records (A, AAAA, MX, NS, TXT, CNAME, SOA),
     WHOIS/RDAP registration, SSL/TLS certificate transparency & SAN, security headers.
  2. IP Address Telemetry: Geolocation, ASN, ISP, reverse DNS, abuse contacts.
  3. Username Reconnaissance: Cross-platform identity footprinting across top services.
  4. Email Intelligence: Syntax, MX exchange verification, disposable domain checks, Gravatar.
  5. Phone Number Intelligence: Carrier, geocoding, E.164 formatting, timezones via libphonenumber.
  6. File & Image Forensic Metadata: EXIF extraction, camera/lens data, GPS coordinates, hashes.
  7. Historical Archive Tracking: Wayback Machine availability and snapshot history.
  8. Threat & Reputation Assessment: Heuristics, DNSBL indicators, and IoC classification.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import ssl
import sys
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# Optional third-party OSINT libraries with graceful fallbacks
try:
    import dns.resolver
    _HAVE_DNS = True
except ImportError:
    _HAVE_DNS = False

try:
    import phonenumbers
    from phonenumbers import carrier as pn_carrier
    from phonenumbers import geocoder as pn_geocoder
    from phonenumbers import timezone as pn_timezone
    _HAVE_PHONENUMBERS = True
except ImportError:
    _HAVE_PHONENUMBERS = False

try:
    from ipwhois import IPWhois
    _HAVE_IPWHOIS = True
except ImportError:
    _HAVE_IPWHOIS = False

try:
    import piexif
    from PIL import Image, ExifTags
    _HAVE_PIEXIF = True
except ImportError:
    _HAVE_PIEXIF = False

try:
    import feedparser
    _HAVE_FEEDPARSER = True
except ImportError:
    _HAVE_FEEDPARSER = False


# Known disposable / temporary email domains list
DISPOSABLE_DOMAINS = {
    "mailinator.com", "tempmail.com", "10minutemail.com", "guerrillamail.com",
    "sharklasers.com", "yopmail.com", "throwawaymail.com", "dispostable.com",
    "trashmail.com", "fakeinbox.com", "getairmail.com", "mohmal.com",
}

# Major social and developer platforms for username profiling
PLATFORMS = [
    {"name": "GitHub", "url": "https://github.com/{}", "check_url": "https://api.github.com/users/{}"},
    {"name": "Reddit", "url": "https://www.reddit.com/user/{}", "check_url": "https://www.reddit.com/user/{}/about.json"},
    {"name": "Telegram", "url": "https://t.me/{}", "check_url": "https://t.me/{}"},
    {"name": "GitLab", "url": "https://gitlab.com/{}", "check_url": "https://gitlab.com/{}"},
    {"name": "HackerNews", "url": "https://news.ycombinator.com/user?id={}", "check_url": "https://hacker-news.firebaseio.com/v0/user/{}.json"},
    {"name": "Keybase", "url": "https://keybase.io/{}", "check_url": "https://keybase.io/_/api/1.0/user/lookup.json?usernames={}"},
    {"name": "Gravatar", "url": "https://gravatar.com/{}", "check_url": "https://en.gravatar.com/{}.json"},
    {"name": "Dev.to", "url": "https://dev.to/{}", "check_url": "https://dev.to/{}"},
    {"name": "Medium", "url": "https://medium.com/@{}", "check_url": "https://medium.com/@{}"},
    {"name": "Pinterest", "url": "https://www.pinterest.com/{}/", "check_url": "https://www.pinterest.com/{}/"},
]


# ── Network & HTTP Utilities ──────────────────────────────────────────────────

def _fetch_json(url: str, headers: dict | None = None, timeout: float = 6.0) -> Optional[dict]:
    """Fetch JSON from endpoint with browser-like user agent."""
    req_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
    }
    if headers:
        req_headers.update(headers)
    try:
        req = urllib.request.Request(url, headers=req_headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read().decode("utf-8", errors="replace")
            return json.loads(data)
    except Exception:
        return None


def _head_or_get_status(url: str, timeout: float = 5.0) -> tuple[int, dict[str, str]]:
    """Perform light HTTP check returning status code and response headers."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            headers = {k.lower(): v for k, v in resp.headers.items()}
            return resp.status, headers
    except urllib.error.HTTPError as he:
        return he.code, {}
    except Exception:
        return 0, {}


# ── Domain Intelligence ───────────────────────────────────────────────────────

def analyze_domain(domain: str) -> dict[str, Any]:
    """Gather DNS records, WHOIS/RDAP telemetry, SSL cert info, and security headers."""
    clean_domain = domain.strip().lower()
    clean_domain = re.sub(r"^https?://", "", clean_domain).split("/")[0].split(":")[0]

    result: dict[str, Any] = {
        "domain": clean_domain,
        "dns": {},
        "ssl_certificate": {},
        "security_headers": {},
        "rdap": {},
    }

    # 1. DNS Resolution
    if _HAVE_DNS:
        resolver = dns.resolver.Resolver()
        resolver.timeout = 4.0
        resolver.lifetime = 4.0
        for rtype in ("A", "AAAA", "MX", "NS", "TXT", "SOA", "CNAME"):
            try:
                answers = resolver.resolve(clean_domain, rtype)
                result["dns"][rtype] = [str(r.to_text()).strip('"') for r in answers]
            except Exception:
                pass
    else:
        # Fallback to standard socket resolution for A records
        try:
            _, _, ip_list = socket.gethostbyname_ex(clean_domain)
            result["dns"]["A"] = ip_list
        except Exception:
            pass

    # 2. SSL/TLS Certificate & Subject Alternative Names (SAN)
    try:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with socket.create_connection((clean_domain, 443), timeout=4.0) as sock:
            with ctx.wrap_socket(sock, server_hostname=clean_domain) as ssock:
                cert = ssock.getpeercert(binary_form=False)
                if not cert:
                    bin_cert = ssock.getpeercert(binary_form=True)
                    # When unverified, extract subject from DER if needed
                    result["ssl_certificate"]["status"] = "Active SSL/TLS connection established"
                else:
                    subject = dict(x[0] for x in cert.get("subject", ()))
                    issuer = dict(x[0] for x in cert.get("issuer", ()))
                    sans = [x[1] for x in cert.get("subjectAltName", ()) if x[0] == "DNS"]
                    result["ssl_certificate"] = {
                        "subject": subject.get("commonName", ""),
                        "issuer": issuer.get("organizationName") or issuer.get("commonName", ""),
                        "not_before": cert.get("notBefore", ""),
                        "not_after": cert.get("notAfter", ""),
                        "san_subdomains": sans[:15],
                    }
    except Exception as exc:
        result["ssl_certificate"]["error"] = f"SSL inspection note: {exc}"

    # 3. HTTP Headers & Security Posture
    status, headers = _head_or_get_status(f"https://{clean_domain}")
    if status == 0:
        status, headers = _head_or_get_status(f"http://{clean_domain}")

    result["http_status"] = status
    result["server"] = headers.get("server", "Hidden/Unknown")
    result["security_headers"] = {
        "strict_transport_security": headers.get("strict-transport-security", "Missing (High Risk)"),
        "content_security_policy": "Present" if "content-security-policy" in headers else "Missing",
        "x_frame_options": headers.get("x-frame-options", "Missing (Clickjacking risk)"),
        "x_content_type_options": headers.get("x-content-type-options", "Missing"),
    }

    # 4. RDAP / Registry Data
    rdap_data = _fetch_json(f"https://rdap.org/domain/{clean_domain}", timeout=5.0)
    if rdap_data:
        events = {ev.get("eventAction"): ev.get("eventDate") for ev in rdap_data.get("events", [])}
        result["rdap"] = {
            "registrar": rdap_data.get("entities", [{}])[0].get("vcardArray", [None, []])[1] if rdap_data.get("entities") else "N/A",
            "created": events.get("registration", "Unknown"),
            "expires": events.get("expiration", "Unknown"),
            "status": rdap_data.get("status", []),
        }

    return result


# ── IP Address Telemetry ──────────────────────────────────────────────────────

def analyze_ip(ip_address: str) -> dict[str, Any]:
    """Inspect IP geolocation, ASN routing, reverse DNS, and network owner."""
    ip = ip_address.strip()
    result: dict[str, Any] = {
        "ip": ip,
        "reverse_dns": "None",
        "geolocation": {},
        "network": {},
    }

    # 1. Reverse DNS
    try:
        host, _, _ = socket.gethostbyaddr(ip)
        result["reverse_dns"] = host
    except Exception:
        pass

    # 2. Geolocation & ASN telemetry via public RDAP/Geo endpoints
    geo = _fetch_json(f"https://ipapi.co/{ip}/json/", timeout=5.0)
    if geo and "country_name" in geo:
        result["geolocation"] = {
            "city": geo.get("city"),
            "region": geo.get("region"),
            "country": geo.get("country_name"),
            "country_code": geo.get("country_code"),
            "postal": geo.get("postal"),
            "latitude": geo.get("latitude"),
            "longitude": geo.get("longitude"),
            "timezone": geo.get("timezone"),
        }
        result["network"] = {
            "asn": geo.get("asn"),
            "organization": geo.get("org"),
            "network_range": geo.get("network"),
        }
    else:
        # Fallback to ip-api.com
        geo2 = _fetch_json(f"http://ip-api.com/json/{ip}", timeout=5.0)
        if geo2 and geo2.get("status") == "success":
            result["geolocation"] = {
                "city": geo2.get("city"),
                "region": geo2.get("regionName"),
                "country": geo2.get("country"),
                "country_code": geo2.get("countryCode"),
                "postal": geo2.get("zip"),
                "latitude": geo2.get("lat"),
                "longitude": geo2.get("lon"),
                "timezone": geo2.get("timezone"),
            }
            result["network"] = {
                "asn": geo2.get("as"),
                "isp": geo2.get("isp"),
                "organization": geo2.get("org"),
            }

    # 3. Optional RDAP/WHOIS via ipwhois
    if _HAVE_IPWHOIS and not result["network"].get("organization"):
        try:
            obj = IPWhois(ip)
            res = obj.lookup_rdap(depth=1)
            result["network"]["asn"] = res.get("asn")
            result["network"]["asn_cidr"] = res.get("asn_cidr")
            result["network"]["asn_description"] = res.get("asn_description")
        except Exception:
            pass

    return result


# ── Username Reconnaissance ───────────────────────────────────────────────────

def analyze_username(username: str) -> dict[str, Any]:
    """Scan across popular social, developer, and public services for user presence."""
    user = username.strip().lstrip("@")
    found_profiles = []
    threads = []
    lock = threading.Lock()

    def _check_platform(platform: dict):
        chk_url = platform["check_url"].format(user)
        pub_url = platform["url"].format(user)
        try:
            req = urllib.request.Request(
                chk_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"}
            )
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                if resp.status in (200, 301, 302):
                    with lock:
                        found_profiles.append({
                            "platform": platform["name"],
                            "url": pub_url,
                            "status": "Confirmed (200 OK)",
                        })
        except urllib.error.HTTPError as he:
            # 404 indicates non-existent profile
            if he.code != 404 and he.code in (403, 429):
                # Rate limited or cloudflare challenge
                pass
        except Exception:
            pass

    for p in PLATFORMS:
        t = threading.Thread(target=_check_platform, args=(p,), daemon=True)
        threads.append(t)
        t.start()

    for t in threads:
        t.join(timeout=4.5)

    return {
        "username": user,
        "searched_platforms": len(PLATFORMS),
        "found_count": len(found_profiles),
        "profiles": sorted(found_profiles, key=lambda x: x["platform"]),
    }


# ── Email Intelligence ────────────────────────────────────────────────────────

def analyze_email(email_address: str) -> dict[str, Any]:
    """Validate email syntax, check MX existence, disposable domains, and Gravatar footprint."""
    clean_email = email_address.strip().lower()
    email_regex = r"^([a-zA-Z0-9_\-\.\+]+)@([a-zA-Z0-9_\-\.]+)\.([a-zA-Z]{2,12})$"
    match = re.match(email_regex, clean_email)

    if not match:
        return {"email": clean_email, "valid_syntax": False, "error": "Invalid email syntax format"}

    local_part, domain = match.group(1), match.group(2) + "." + match.group(3)
    is_disposable = domain in DISPOSABLE_DOMAINS or any(d in domain for d in ("temp", "trash", "fake", "dispos"))

    result: dict[str, Any] = {
        "email": clean_email,
        "valid_syntax": True,
        "local_part": local_part,
        "domain": domain,
        "is_disposable": is_disposable,
        "mx_records": [],
        "gravatar": {},
    }

    # Query domain MX records
    if _HAVE_DNS:
        try:
            answers = dns.resolver.resolve(domain, "MX")
            result["mx_records"] = [str(r.exchange).rstrip(".") for r in answers]
            result["accepts_mail"] = len(result["mx_records"]) > 0
        except Exception:
            result["accepts_mail"] = False
    else:
        try:
            socket.gethostbyname(domain)
            result["accepts_mail"] = "Domain Resolves (DNS Library not installed)"
        except Exception:
            result["accepts_mail"] = False

    # Gravatar Profile Check (MD5 hash of lowercase email)
    md5_hash = hashlib.md5(clean_email.encode("utf-8")).hexdigest()
    gravatar_data = _fetch_json(f"https://en.gravatar.com/{md5_hash}.json", timeout=3.5)
    if gravatar_data and "entry" in gravatar_data:
        entry = gravatar_data["entry"][0]
        result["gravatar"] = {
            "profile_found": True,
            "display_name": entry.get("displayName", ""),
            "profile_url": entry.get("profileUrl", ""),
            "about_me": entry.get("aboutMe", ""),
            "photos": [p.get("value") for p in entry.get("photos", []) if p.get("value")],
        }
    else:
        result["gravatar"] = {"profile_found": False}

    return result


# ── Phone Number Intelligence ─────────────────────────────────────────────────

def analyze_phone(phone_input: str, default_region: str = "US") -> dict[str, Any]:
    """Extract carrier, country, line type, and timezone via libphonenumber."""
    raw = phone_input.strip()
    if not _HAVE_PHONENUMBERS:
        return {
            "phone": raw,
            "error": "phonenumbers package not available. Install with `pip install phonenumbers`.",
        }

    try:
        pn = phonenumbers.parse(raw, default_region)
    except Exception as e:
        return {"phone": raw, "valid": False, "error": f"Failed to parse phone number: {e}"}

    is_valid = phonenumbers.is_valid_number(pn)
    is_possible = phonenumbers.is_possible_number(pn)
    number_type = phonenumbers.number_type(pn)

    type_map = {
        0: "FIXED_LINE", 1: "MOBILE", 2: "FIXED_LINE_OR_MOBILE",
        3: "TOLL_FREE", 4: "PREMIUM_RATE", 5: "SHARED_COST",
        6: "VOIP", 7: "PERSONAL_NUMBER", 8: "PAGER", 9: "UAN",
        10: "VOICEMAIL",
    }

    country_name = pn_geocoder.description_for_number(pn, "en")
    carrier_name = pn_carrier.name_for_number(pn, "en")
    tz_list = list(pn_timezone.time_zones_for_number(pn))

    return {
        "phone": raw,
        "valid": is_valid,
        "possible": is_possible,
        "e164_format": phonenumbers.format_number(pn, phonenumbers.PhoneNumberFormat.E164),
        "international_format": phonenumbers.format_number(pn, phonenumbers.PhoneNumberFormat.INTERNATIONAL),
        "national_format": phonenumbers.format_number(pn, phonenumbers.PhoneNumberFormat.NATIONAL),
        "country_code": pn.country_code,
        "line_type": type_map.get(number_type, "UNKNOWN"),
        "country_region": country_name or "Unknown",
        "carrier": carrier_name or "Unknown / Unassigned",
        "timezones": tz_list,
    }


# ── File & Image Forensic Metadata ────────────────────────────────────────────

def analyze_file_metadata(file_path: str) -> dict[str, Any]:
    """Extract cryptographic hashes, file attributes, and EXIF/GPS telemetry."""
    path = Path(file_path).expanduser().resolve()
    if not path.is_file():
        return {"file": str(path), "error": "File not found or inaccessible"}

    file_bytes = path.read_bytes()
    size_bytes = len(file_bytes)

    res: dict[str, Any] = {
        "file_name": path.name,
        "file_path": str(path),
        "size_kb": round(size_bytes / 1024, 2),
        "hashes": {
            "md5": hashlib.md5(file_bytes).hexdigest(),
            "sha1": hashlib.sha1(file_bytes).hexdigest(),
            "sha256": hashlib.sha256(file_bytes).hexdigest(),
        },
        "exif": {},
        "gps": {},
    }

    # Image EXIF extraction
    if path.suffix.lower() in (".jpg", ".jpeg", ".tiff", ".png") and _HAVE_PIEXIF:
        try:
            exif_dict = piexif.load(str(path))
            zeroth = exif_dict.get("0th", {})
            exif = exif_dict.get("Exif", {})
            gps = exif_dict.get("GPS", {})

            # Clean helper
            def _clean_val(v):
                if isinstance(v, bytes):
                    return v.decode("utf-8", errors="replace").strip("\x00")
                if isinstance(v, tuple):
                    return list(v)
                return str(v)

            if piexif.ImageIFD.Make in zeroth:
                res["exif"]["camera_make"] = _clean_val(zeroth[piexif.ImageIFD.Make])
            if piexif.ImageIFD.Model in zeroth:
                res["exif"]["camera_model"] = _clean_val(zeroth[piexif.ImageIFD.Model])
            if piexif.ImageIFD.Software in zeroth:
                res["exif"]["software"] = _clean_val(zeroth[piexif.ImageIFD.Software])
            if piexif.ExifIFD.DateTimeOriginal in exif:
                res["exif"]["date_taken"] = _clean_val(exif[piexif.ExifIFD.DateTimeOriginal])

            # GPS telemetry conversion
            if gps and piexif.GPSIFD.GPSLatitude in gps and piexif.GPSIFD.GPSLongitude in gps:
                lat_t = gps[piexif.GPSIFD.GPSLatitude]
                lat_ref = gps.get(piexif.GPSIFD.GPSLatitudeRef, b"N").decode("utf-8", errors="replace")
                lon_t = gps[piexif.GPSIFD.GPSLongitude]
                lon_ref = gps.get(piexif.GPSIFD.GPSLongitudeRef, b"E").decode("utf-8", errors="replace")

                def _dms_to_deg(dms):
                    d = dms[0][0] / dms[0][1]
                    m = dms[1][0] / dms[1][1]
                    s = dms[2][0] / dms[2][1]
                    return d + (m / 60.0) + (s / 3600.0)

                lat = _dms_to_deg(lat_t)
                if lat_ref == "S":
                    lat = -lat
                lon = _dms_to_deg(lon_t)
                if lon_ref == "W":
                    lon = -lon

                res["gps"] = {
                    "latitude": round(lat, 6),
                    "longitude": round(lon, 6),
                    "google_maps": f"https://www.google.com/maps?q={lat:.6f},{lon:.6f}",
                }
        except Exception:
            pass

    return res


# ── Wayback Machine & Archive History ─────────────────────────────────────────

def analyze_wayback(target_url: str) -> dict[str, Any]:
    """Retrieve historical snapshot presence and earliest/latest capture timestamps."""
    url = target_url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    api_url = f"https://archive.org/wayback/available?url={urllib.parse.quote(url)}"
    data = _fetch_json(api_url, timeout=5.0)

    if not data or not data.get("archived_snapshots"):
        return {"url": url, "archived": False, "message": "No snapshots recorded in Wayback Machine."}

    closest = data["archived_snapshots"].get("closest", {})
    return {
        "url": url,
        "archived": bool(closest.get("available")),
        "snapshot_url": closest.get("url", ""),
        "timestamp": closest.get("timestamp", ""),
        "status": closest.get("status", ""),
    }


# ── Threat & IoC Assessment ───────────────────────────────────────────────────

def analyze_threat(indicator: str) -> dict[str, Any]:
    """Assess whether target exhibits known suspicious patterns or malicious IoC traits."""
    target = indicator.strip()
    findings = []
    risk_level = "Low"

    # Pattern heuristics
    if re.search(r"\b(login|verify|account|banking|update|secure|wallet)[-_.]", target, re.I):
        findings.append("Suspicious credential-harvesting keywords in target string.")
        risk_level = "Elevated"

    if re.search(r"(\.top|\.xyz|\.click|\.tk|\.ga|\.cf|\.gq|\.pw)$", target, re.I):
        findings.append("High-abuse TLD detected.")
        if risk_level == "Elevated":
            risk_level = "High"

    # Check IP private range
    if re.match(r"^(10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[0-1])\.)", target):
        findings.append("Private RFC1918 internal IP address; not routable on public Internet.")

    return {
        "indicator": target,
        "risk_level": risk_level,
        "heuristic_findings": findings if findings else ["No immediate heuristic anomalies detected."],
    }


# ── Auto Classifier & Dispatcher ──────────────────────────────────────────────

def _detect_category(target: str) -> str:
    t = target.strip()
    if t.lower().startswith(("http://", "https://")):
        try:
            parsed = urllib.parse.urlparse(t)
            host = (parsed.hostname or "").lower()
            if host == "archive.org" or host.endswith(".archive.org"):
                return "wayback"
        except Exception:
            pass
        return "domain"
    if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", t):
        return "ip"
    if "@" in t and not t.startswith("@"):
        return "email"
    if re.match(r"^\+?[0-9\-\s\(\)]{8,20}$", t) and any(c.isdigit() for c in t):
        return "phone"
    if Path(t).is_file() or any(t.lower().endswith(ext) for ext in (".jpg", ".png", ".jpeg", ".pdf", ".docx", ".exe")):
        return "metadata"
    if "." in t and not " " in t:
        return "domain"
    return "username"


def execute_osint_investigation(
    target: str,
    category: str = "auto",
    player: Any = None,
) -> str:
    """Run specified OSINT investigation, render HUD findings, and return spoken summary."""
    clean_target = (target or "").strip()
    if not clean_target:
        return "Please specify a target for OSINT reconnaissance, sir."

    cat = (category or "auto").strip().lower()
    if cat == "auto":
        cat = _detect_category(clean_target)

    report_data: dict[str, Any] = {"target": clean_target, "category": cat}

    if cat == "domain":
        report_data["data"] = analyze_domain(clean_target)
    elif cat == "ip":
        report_data["data"] = analyze_ip(clean_target)
    elif cat == "username":
        report_data["data"] = analyze_username(clean_target)
    elif cat == "email":
        report_data["data"] = analyze_email(clean_target)
    elif cat == "phone":
        report_data["data"] = analyze_phone(clean_target)
    elif cat == "metadata":
        report_data["data"] = analyze_file_metadata(clean_target)
    elif cat == "wayback":
        report_data["data"] = analyze_wayback(clean_target)
    elif cat == "threat_check":
        report_data["data"] = analyze_threat(clean_target)
    else:
        # Fallback to combined domain/username investigation
        report_data["data"] = analyze_domain(clean_target)

    # Format Markdown Report for HUD
    md_lines = [
        f"# 🛰️ OSINT Intelligence Telemetry: {clean_target}",
        f"**Category:** `{cat.upper()}` | **Timestamp:** `{time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}`",
        "---",
    ]

    spoken_summary = f"OSINT reconnaissance completed for {clean_target}."

    if cat == "domain":
        d = report_data["data"]
        dns_sec = d.get("dns", {})
        md_lines.append(f"### DNS Resolution")
        for k, v in dns_sec.items():
            md_lines.append(f"- **{k}:** {', '.join(v)}")
        ssl_info = d.get("ssl_certificate", {})
        if ssl_info.get("subject"):
            md_lines.append(f"\n### SSL/TLS Certificate")
            md_lines.append(f"- **Subject:** `{ssl_info.get('subject')}`")
            md_lines.append(f"- **Issuer:** `{ssl_info.get('issuer')}`")
            md_lines.append(f"- **Valid To:** `{ssl_info.get('not_after')}`")
            if ssl_info.get("san_subdomains"):
                md_lines.append(f"- **SAN Subdomains:** {', '.join(ssl_info['san_subdomains'])}")
        headers = d.get("security_headers", {})
        md_lines.append(f"\n### Security Posture")
        for hk, hv in headers.items():
            md_lines.append(f"- **{hk.replace('_', ' ').title()}:** {hv}")
        a_records = dns_sec.get("A", [])
        spoken_summary = f"Domain {clean_target} resolved with {len(a_records)} IP address{'es' if len(a_records) != 1 else ''}. Server is running {d.get('server', 'unknown software')}."

    elif cat == "ip":
        d = report_data["data"]
        geo = d.get("geolocation", {})
        net = d.get("network", {})
        md_lines.append(f"### Geolocation & Network")
        md_lines.append(f"- **Location:** {geo.get('city')}, {geo.get('region')}, {geo.get('country')}")
        md_lines.append(f"- **Coordinates:** {geo.get('latitude')}, {geo.get('longitude')} (Timezone: {geo.get('timezone')})")
        md_lines.append(f"- **ASN / ISP:** {net.get('asn')} — {net.get('organization') or net.get('isp', 'N/A')}")
        md_lines.append(f"- **Reverse DNS:** `{d.get('reverse_dns')}`")
        spoken_summary = f"IP address {clean_target} is located in {geo.get('city', 'unknown city')}, {geo.get('country', 'unknown country')}, routed by {net.get('organization') or 'unknown network'}."

    elif cat == "username":
        d = report_data["data"]
        profiles = d.get("profiles", [])
        md_lines.append(f"### Discovered Profiles ({len(profiles)} found across {d.get('searched_platforms')} platforms)")
        if profiles:
            for p in profiles:
                md_lines.append(f"- **{p['platform']}:** [{p['url']}]({p['url']})")
            spoken_summary = f"Username {clean_target} located across {len(profiles)} public platforms including {', '.join(p['platform'] for p in profiles[:3])}."
        else:
            md_lines.append("- No public accounts confirmed on indexed services.")
            spoken_summary = f"No public accounts confirmed for username {clean_target} on indexed platforms."

    elif cat == "email":
        d = report_data["data"]
        md_lines.append(f"### Email Verification")
        md_lines.append(f"- **Syntax Valid:** {d.get('valid_syntax')}")
        md_lines.append(f"- **Disposable Email Domain:** {d.get('is_disposable')}")
        md_lines.append(f"- **MX Mail Servers:** {', '.join(d.get('mx_records', [])) or 'None'}")
        grav = d.get("gravatar", {})
        if grav.get("profile_found"):
            md_lines.append(f"- **Gravatar Identity:** {grav.get('display_name')} ([Profile]({grav.get('profile_url')}))")
        spoken_summary = f"Email {clean_target} is {'a valid' if d.get('valid_syntax') else 'an invalid'} address. Mail servers are {'active' if d.get('accepts_mail') else 'inactive'}."

    elif cat == "phone":
        d = report_data["data"]
        md_lines.append(f"### Phone Telemetry")
        md_lines.append(f"- **Formatted (E.164):** `{d.get('e164_format', 'N/A')}`")
        md_lines.append(f"- **Carrier:** {d.get('carrier')}")
        md_lines.append(f"- **Country / Region:** {d.get('country_region')}")
        md_lines.append(f"- **Line Type:** {d.get('line_type')}")
        md_lines.append(f"- **Timezones:** {', '.join(d.get('timezones', []))}")
        spoken_summary = f"Phone number belongs to {d.get('carrier', 'unknown carrier')} in {d.get('country_region', 'unknown region')}, type {d.get('line_type', 'unknown')}."

    elif cat == "metadata":
        d = report_data["data"]
        md_lines.append(f"### File Forensics")
        md_lines.append(f"- **Size:** {d.get('size_kb')} KB")
        md_lines.append(f"- **SHA-256:** `{d.get('hashes', {}).get('sha256')}`")
        exif = d.get("exif", {})
        if exif:
            md_lines.append(f"### EXIF Telemetry")
            for ek, ev in exif.items():
                md_lines.append(f"- **{ek.replace('_', ' ').title()}:** {ev}")
        gps = d.get("gps", {})
        if gps:
            md_lines.append(f"### Embedded GPS Coordinates")
            md_lines.append(f"- **Coordinates:** `{gps.get('latitude')}, {gps.get('longitude')}` ([View on Google Maps]({gps.get('google_maps')}))")
        spoken_summary = f"Forensic analysis of {d.get('file_name', 'file')} complete. Computed cryptographic SHA-256 hash and extracted metadata."

    elif cat == "wayback":
        d = report_data["data"]
        md_lines.append(f"### Archive Telemetry")
        md_lines.append(f"- **Archived:** {d.get('archived')}")
        if d.get("archived"):
            md_lines.append(f"- **Latest Snapshot:** [{d.get('timestamp')}]({d.get('snapshot_url')})")
        spoken_summary = f"Wayback Machine shows {clean_target} is {'archived with historical snapshots' if d.get('archived') else 'not archived'}."

    elif cat == "threat_check":
        d = report_data["data"]
        md_lines.append(f"### Threat Assessment")
        md_lines.append(f"- **Risk Level:** `{d.get('risk_level')}`")
        for f in d.get("heuristic_findings", []):
            md_lines.append(f"- {f}")
        spoken_summary = f"Threat assessment classified {clean_target} with {d.get('risk_level')} risk."

    # Render on HUD if player interface is available
    if player is not None:
        try:
            player.show_content(f"OSINT: {clean_target}", "\n".join(md_lines))
            player.write_log(f"OSINT: Completed {cat} investigation for {clean_target}")
        except Exception:
            pass

    return spoken_summary


# ── Action Execution Wrapper ──────────────────────────────────────────────────

def osint_investigate(
    parameters: dict,
    player: Any = None,
    session_memory: Any = None,
    **kwargs,
) -> str:
    """Entry point for AMATYA OSINT tool."""
    target = str(parameters.get("target", "")).strip()
    category = str(parameters.get("category", "auto")).strip()
    try:
        return execute_osint_investigation(target=target, category=category, player=player)
    except Exception as exc:
        return f"OSINT reconnaissance failed: {exc}"


# ── Action Metadata & Tool Declaration ────────────────────────────────────────

SKILL_METADATA = {
    "capabilities": [
        "osint",
        "domain_intelligence",
        "ip_telemetry",
        "username_reconnaissance",
        "email_investigation",
        "phone_intelligence",
        "forensic_metadata",
        "threat_assessment",
        "wayback_snapshots",
    ],
    "permissions": ["network_access", "read_local_files"],
    "dependencies": ["phonenumbers", "dnspython", "ipwhois", "piexif"],
    "supported_actions": ["domain", "ip", "username", "email", "phone", "metadata", "wayback", "threat_check", "auto"],
    "security_level": "normal",
}

TOOL = {
    "name": "osint_investigate",
    "description": (
        "Performs Open-Source Intelligence (OSINT) and passive reconnaissance on a given target. "
        "Supports domain inspection (DNS/SSL/RDAP/headers), IP geolocation/ASN, username profiling, "
        "email/phone intelligence, image EXIF/GPS forensic extraction, and historical archive lookups."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "target": {
                "type": "STRING",
                "description": "Domain, IP address, username, email, phone number, file path, or URL to investigate.",
            },
            "category": {
                "type": "STRING",
                "enum": ["auto", "domain", "ip", "username", "email", "phone", "metadata", "wayback", "threat_check"],
                "description": "Category of investigation. Defaults to 'auto' which infers the type automatically.",
            },
        },
        "required": ["target"],
    },
    "handler": osint_investigate,
}
