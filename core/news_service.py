"""
core/news_service.py — Global & Local News Intelligence and Outage Monitor
========================================================================
Implements comprehensive news aggregation across world affairs:
  - Topics: Politics, Geopolitics, Ongoing Wars/Conflicts, Current Affairs,
    New Developments, Sports, Tech, Business, Science, and Local News.
  - User Preferences: Onboarding topic selection and persistent preferences.
  - Scheduling: Thrice-daily briefings (morning, afternoon, evening) + startup.
  - Global Outage Telemetry: Real-time monitoring of popular web services
    (Google, AWS, Cloudflare, GitHub, X, WhatsApp, OpenAI, Reddit, etc.)
    with downtime duration tracking and HUD integration.
"""
from __future__ import annotations

import html
import json
import re
import socket
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

try:
    import feedparser
    _HAVE_FEEDPARSER = True
except ImportError:
    _HAVE_FEEDPARSER = False

from memory.config_manager import CONFIG_DIR, get_user_name

def get_user_location() -> str:
    """Read location from geolocation service, memory, or fallback to 'Global'."""
    try:
        from core.geolocation import get_device_location_name
        loc = get_device_location_name()
        if loc and loc != "Local Region":
            return loc
    except Exception:
        pass
    try:
        from memory.memory_manager import load_memory
        loc = load_memory().get("user_location") or load_memory().get("location")
        if loc:
            return str(loc).strip()
    except Exception:
        pass
    return "Global"

PREFS_PATH = CONFIG_DIR / "news_preferences.json"
OUTAGE_CACHE_PATH = CONFIG_DIR / "outages_cache.json"

AVAILABLE_TOPICS = [
    "politics",
    "geopolitics",
    "ongoing_wars",
    "current_affairs",
    "new_developments",
    "sports",
    "tech",
    "science",
    "business",
    "local_news",
]

TOPIC_QUERIES = {
    "politics": "world politics national government policy elections",
    "geopolitics": "geopolitics diplomacy international relations treaty summit",
    "ongoing_wars": "conflict war ceasefire military strikes battlefield frontline",
    "current_affairs": "breaking news world current events top headlines",
    "new_developments": "breakthrough innovation discoveries progress development",
    "sports": "sports tournament championship league scores football cricket tennis",
    "tech": "technology artificial intelligence cyber software hardware computing",
    "science": "science space research climate physics astronomy biology",
    "business": "economy markets trade finance global business industry",
    "local_news": "local city community municipal regional news",
}

KNOWN_STATUS_APIS = {
    "Anthropic Claude": "https://status.anthropic.com/api/v2/status.json",
    "OpenAI": "https://status.openai.com/api/v2/status.json",
    "Cloudflare": "https://www.cloudflarestatus.com/api/v2/status.json",
    "GitHub": "https://www.githubstatus.com/api/v2/status.json",
    "Discord": "https://discordstatus.com/api/v2/status.json",
    "Reddit": "https://redditstatus.com/api/v2/status.json",
}

MONITORED_SERVICES = {
    "Anthropic Claude": "claude.ai",
    "OpenAI": "openai.com",
    "Outlook / Hotmail": "outlook.live.com",
    "Microsoft Copilot": "copilot.microsoft.com",
    "OneDrive": "onedrive.live.com",
    "Microsoft 365": "microsoft.com",
    "Google": "google.com",
    "AWS": "aws.amazon.com",
    "Cloudflare": "cloudflare.com",
    "GitHub": "github.com",
    "Discord": "discord.com",
    "Reddit": "reddit.com",
    "WhatsApp": "whatsapp.com",
    "X / Twitter": "x.com",
    "YouTube": "youtube.com",
    "Wikipedia": "wikipedia.org",
}

_LOCK = threading.RLock()
_OUTAGE_HISTORY: dict[str, dict[str, Any]] = {}


# ── Preferences Management ────────────────────────────────────────────────────

def get_news_preferences() -> dict[str, Any]:
    """Load or initialize user news preferences."""
    with _LOCK:
        if PREFS_PATH.is_file():
            try:
                data = json.loads(PREFS_PATH.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "topics" in data:
                    return data
            except Exception:
                pass

        default_prefs = {
            "initialized": False,
            "topics": [
                "politics", "geopolitics", "ongoing_wars",
                "current_affairs", "new_developments", "tech", "local_news"
            ],
            "briefing_times": {
                "morning": "08:00",
                "afternoon": "13:00",
                "evening": "19:00",
            },
            "brief_on_startup": True,
            "location": get_user_location() or "Global",
            "last_briefing": "",
        }
        save_news_preferences(default_prefs)
        return default_prefs


def save_news_preferences(prefs: dict[str, Any]) -> None:
    """Save user news preferences to disk."""
    with _LOCK:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        PREFS_PATH.write_text(json.dumps(prefs, indent=2), encoding="utf-8")


def set_user_topics(topics: list[str]) -> dict[str, Any]:
    """Update preferred topics and mark preferences as initialized."""
    prefs = get_news_preferences()
    valid_topics = [t.strip().lower() for t in topics if t.strip().lower() in AVAILABLE_TOPICS]
    if valid_topics:
        prefs["topics"] = valid_topics
        prefs["initialized"] = True
        save_news_preferences(prefs)
    return prefs


# ── RSS & Web News Gathering ──────────────────────────────────────────────────

def _clean_headline_and_source(raw_title: str) -> tuple[str, str]:
    """Clean raw RSS headline and extract source name.

    Google News headlines typically look like 'Headline Text - Source Name'.
    """
    clean = html.unescape(raw_title or "").strip()
    clean = re.sub(r"\s+", " ", clean)
    if " - " in clean:
        parts = clean.rsplit(" - ", 1)
        title = parts[0].strip()
        source = parts[1].strip()
        return title, source
    return clean, ""


def _clean_summary(raw_summary: str, clean_title: str, source: str) -> str:
    """Clean summary snippet, removing HTML entities and eliminating redundancy."""
    if not raw_summary:
        return ""
    clean = html.unescape(raw_summary)
    clean = re.sub(r"<[^>]+>", " ", clean)
    clean = re.sub(r"&nbsp;|\xa0", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip()

    # If the summary is essentially the title and source repeated, drop it
    norm_clean = re.sub(r"[^\w\s]", "", clean.lower()).strip()
    norm_title = re.sub(r"[^\w\s]", "", clean_title.lower()).strip()
    norm_source = re.sub(r"[^\w\s]", "", source.lower()).strip()

    if not norm_clean or norm_clean in norm_title or norm_clean == f"{norm_title} {norm_source}".strip():
        return ""
    if len(clean) < 25:
        return ""

    if len(clean) > 160:
        clean = clean[:157].rsplit(" ", 1)[0] + "..."
    return clean


def _fetch_rss(url: str, timeout: float = 6.0) -> list[dict[str, str]]:
    """Fetch and parse RSS feed entries with fallback to standard xml."""
    items = []
    if _HAVE_FEEDPARSER:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:8]:
                raw_title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()
                raw_summary = entry.get("summary", "").strip()
                published = entry.get("published", "")
                if raw_title:
                    c_title, c_source = _clean_headline_and_source(raw_title)
                    c_summary = _clean_summary(raw_summary, c_title, c_source)
                    items.append({
                        "title": raw_title,
                        "clean_title": c_title,
                        "source": c_source,
                        "link": link,
                        "summary": c_summary,
                        "published": published,
                    })
            if items:
                return items
        except Exception:
            pass

    # Standard library fallback
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read()
            root = ET.fromstring(content)
            for item in root.findall(".//item")[:8]:
                t = item.find("title")
                l = item.find("link")
                d = item.find("description")
                raw_title = t.text.strip() if t is not None and t.text else ""
                link = l.text.strip() if l is not None and l.text else ""
                raw_summary = d.text.strip() if d is not None and d.text else ""
                if raw_title:
                    c_title, c_source = _clean_headline_and_source(raw_title)
                    c_summary = _clean_summary(raw_summary, c_title, c_source)
                    items.append({
                        "title": raw_title,
                        "clean_title": c_title,
                        "source": c_source,
                        "link": link,
                        "summary": c_summary,
                        "published": "",
                    })
    except Exception:
        pass
    return items


def fetch_topic_news(topic: str, location: str = "") -> list[dict[str, str]]:
    """Retrieve latest articles for a specific news topic."""
    t = topic.strip().lower()
    query = TOPIC_QUERIES.get(t, t)
    if t == "local_news" and location:
        query = f"{location} local city news"

    encoded_q = urllib.parse.quote(query)
    google_rss = f"https://news.google.com/rss/search?q={encoded_q}&hl=en-US&gl=US&ceid=US:en"
    articles = _fetch_rss(google_rss)

    if not articles:
        # Fallback to general world news feed
        articles = _fetch_rss("https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en")

    return articles[:4]


# ── Outage Monitor (Statuspage APIs, Downdetector, HTTP Probes & Incidents) ──

def fetch_downdetector_outages() -> list[dict[str, Any]]:
    """Scan Downdetector incident reports and trending user disruption alerts."""
    incidents = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    # 1. Google News Downdetector search
    try:
        url = "https://news.google.com/rss/search?q=Downdetector+outage+OR+down&hl=en-US&gl=US&ceid=US:en"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            root = ET.fromstring(resp.read())
            for it in root.findall(".//item")[:15]:
                title = it.find("title").text if it.find("title") is not None else ""
                link = it.find("link").text if it.find("link") is not None else ""
                pubDate = it.find("pubDate").text if it.find("pubDate") is not None else ""
                if any(w in title.lower() for w in ("outage", "down", "disruption", "issues", "problem", "glitch", "recovers")):
                    incidents.append({
                        "title": title,
                        "link": link,
                        "source": "Downdetector / Media",
                        "pubDate": pubDate,
                    })
    except Exception as exc:
        print(f"[NewsService] Downdetector RSS error: {exc}")

    # 2. DDGS News search
    try:
        from ddgs import DDGS
        ddgs = DDGS()
        for r in ddgs.news("downdetector outage down", max_results=8):
            incidents.append({
                "title": r.get("title", ""),
                "link": r.get("url", ""),
                "source": r.get("source", "Downdetector"),
                "pubDate": r.get("date", ""),
            })
    except Exception:
        pass

    # Deduplicate
    unique = []
    seen = set()
    for inc in incidents:
        t = re.sub(r"[^a-zA-Z0-9 ]", "", inc["title"].lower())
        short = " ".join(t.split()[:5])
        if short and short not in seen:
            seen.add(short)
            unique.append(inc)

    return unique


def fetch_trending_outages() -> list[dict[str, str]]:
    """Scan news feeds for breaking and active global cloud/service outages."""
    try:
        articles = _fetch_rss(
            "https://news.google.com/rss/search?q=outage+down+service+issues&hl=en-US&gl=US&ceid=US:en"
        )
        incidents = []
        keywords = ("outage", "down", "offline", "disruption", "crash", "issues", "problem")
        for a in articles:
            title_lower = (a.get("clean_title") or a.get("title") or "").lower()
            if any(k in title_lower for k in keywords):
                incidents.append(a)
        return incidents[:3]
    except Exception:
        return []


def check_service_status(service_name: str, domain: str) -> dict[str, Any]:
    """Query service availability and latency via official Statuspage API or HTTP probe."""
    now = time.time()
    t0 = time.perf_counter()
    is_up = True
    status_label = "Operational"
    err_msg = ""

    # 1. Official status API (e.g. Anthropic, OpenAI, Cloudflare, GitHub, Discord, Reddit)
    status_api = KNOWN_STATUS_APIS.get(service_name)
    if status_api:
        try:
            req = urllib.request.Request(
                status_api,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AMATYA-Monitor/1.0"},
            )
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                st = data.get("status", {})
                ind = str(st.get("indicator", "none")).lower()
                desc = st.get("description", "")
                if ind in ("major", "critical"):
                    is_up = False
                    status_label = "OUTAGE"
                    err_msg = f"Status API: {desc or ind.title()}"
                elif ind in ("minor", "degraded"):
                    status_label = "DEGRADED"
                    err_msg = f"Degraded: {desc or ind.title()}"
        except Exception:
            pass

    # 2. HTTP / SSL Probe with strict timeout (not just TCP socket SYN)
    if is_up:
        try:
            url = f"https://{domain}"
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AMATYA-Monitor/1.0"},
            )
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                pass
        except urllib.error.HTTPError as he:
            if he.code in (500, 502, 503, 504):
                is_up = False
                status_label = "OUTAGE"
                err_msg = f"HTTP {he.code} {he.reason}"
        except Exception as exc:
            # Check TCP port 443 before declaring full failure
            try:
                with socket.create_connection((domain, 443), timeout=2.0):
                    status_label = "DEGRADED"
                    err_msg = "SSL handshake latency / Slow response"
            except Exception:
                is_up = False
                status_label = "OUTAGE"
                err_msg = str(exc)

    latency_ms = round((time.perf_counter() - t0) * 1000.0, 1)

    with _LOCK:
        prev = _OUTAGE_HISTORY.get(service_name)
        if not is_up:
            if prev and not prev.get("is_up", True):
                down_since = prev.get("down_since", now)
            else:
                down_since = now
            duration_sec = int(now - down_since)
            entry = {
                "service": service_name,
                "domain": domain,
                "is_up": False,
                "status": status_label,
                "latency_ms": latency_ms,
                "down_since": down_since,
                "duration_seconds": duration_sec,
                "duration_str": _format_duration(duration_sec),
                "error": err_msg or "Connection failed",
            }
        else:
            entry = {
                "service": service_name,
                "domain": domain,
                "is_up": True,
                "status": status_label,
                "latency_ms": latency_ms,
                "down_since": 0.0,
                "duration_seconds": 0,
                "duration_str": "",
                "error": err_msg,
            }
        _OUTAGE_HISTORY[service_name] = entry

    return entry


def _format_duration(seconds: int) -> str:
    """Format seconds into readable human duration string."""
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m {seconds % 60}s"
    hours = minutes // 60
    return f"{hours}h {minutes % 60}m"


def check_all_outages() -> dict[str, Any]:
    """Scan all major monitored services in parallel and retrieve trending & Downdetector incidents."""
    results = {}
    threads = []

    def _worker(name, domain):
        results[name] = check_service_status(name, domain)

    for name, domain in MONITORED_SERVICES.items():
        t = threading.Thread(target=_worker, args=(name, domain), daemon=True)
        threads.append(t)
        t.start()

    # Fetch trending and Downdetector incidents in parallel
    trending_incidents = []
    downdetector_incidents = []

    def _fetch_trend():
        nonlocal trending_incidents
        trending_incidents = fetch_trending_outages()

    def _fetch_dd():
        nonlocal downdetector_incidents
        downdetector_incidents = fetch_downdetector_outages()

    trend_th = threading.Thread(target=_fetch_trend, daemon=True)
    dd_th = threading.Thread(target=_fetch_dd, daemon=True)
    trend_th.start()
    dd_th.start()

    deadline = time.time() + 4.0
    for t in threads:
        rem = max(0.02, deadline - time.time())
        t.join(timeout=rem)

    rem_extra = max(0.02, deadline - time.time())
    trend_th.join(timeout=rem_extra)
    dd_th.join(timeout=rem_extra)

    # Any service that didn't complete within timeout is considered timed out / degraded
    for name, domain in MONITORED_SERVICES.items():
        if name not in results:
            results[name] = {
                "service": name,
                "domain": domain,
                "is_up": False,
                "status": "OUTAGE",
                "latency_ms": 3800.0,
                "down_since": time.time(),
                "duration_seconds": 0,
                "duration_str": "Just detected",
                "error": "Connection timed out (>3.8s)",
            }

    # Correlate Downdetector alerts with monitored services
    SERVICE_KEYWORDS = {
        "Outlook / Hotmail": ["outlook", "hotmail", "exchange", "msn"],
        "Microsoft 365": ["microsoft 365", "office 365", "m365", "microsoft office"],
        "Microsoft Copilot": ["copilot"],
        "OneDrive": ["onedrive"],
        "Anthropic Claude": ["claude", "anthropic"],
        "OpenAI": ["chatgpt", "openai"],
        "AWS": ["aws", "amazon web services", "amazon cloud"],
        "Cloudflare": ["cloudflare"],
        "GitHub": ["github"],
        "Discord": ["discord"],
        "Reddit": ["reddit"],
        "WhatsApp": ["whatsapp"],
        "X / Twitter": ["twitter", " x down", " x outage", "grok"],
        "YouTube": ["youtube"],
        "Google": ["google", "gmail", "google drive"],
        "Wikipedia": ["wikipedia"],
    }

    for svc_name, kws in SERVICE_KEYWORDS.items():
        if svc_name in results:
            for inc in downdetector_incidents:
                t_lower = inc["title"].lower()
                if any(kw in t_lower for kw in kws) and any(w in t_lower for w in ("down", "outage", "disruption", "issues", "problem")):
                    curr = results[svc_name]
                    curr["downdetector_alert"] = True
                    curr["downdetector_headline"] = inc["title"]
                    curr["downdetector_link"] = inc.get("link", "")
                    curr["is_up"] = False
                    curr["status"] = "OUTAGE (Downdetector)"
                    curr["error"] = f"Downdetector: {inc['title']}"
                    break

    active_outages = [item for item in results.values() if not item.get("is_up")]
    degraded = [item for item in results.values() if item.get("is_up") and item.get("status") == "DEGRADED"]

    # Persist cache
    try:
        OUTAGE_CACHE_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
    except Exception:
        pass

    return {
        "timestamp": datetime.now().isoformat(),
        "total_monitored": len(results),
        "active_outages_count": len(active_outages),
        "active_outages": active_outages,
        "degraded_services": degraded,
        "trending_incidents": trending_incidents,
        "downdetector_incidents": downdetector_incidents,
        "services": results,
    }


def get_current_outages() -> list[dict[str, Any]]:
    """Return currently active outages from cache or instant scan."""
    with _LOCK:
        down = [v for v in _OUTAGE_HISTORY.values() if not v.get("is_up")]
    if not down:
        scan = check_all_outages()
        down = scan.get("active_outages", [])
    return down


# ── News Briefing Synthesis ───────────────────────────────────────────────────

def generate_news_briefing(
    period: str = "launch",
    topics: list[str] | None = None,
    player: Any = None,
) -> dict[str, Any]:
    """Compile aggregated news, check outages, format HUD panel, and return spoken brief."""
    prefs = get_news_preferences()
    selected_topics = topics or prefs.get("topics", ["current_affairs", "politics", "tech"])
    location = prefs.get("location") or get_user_location() or "Global"

    aggregated_news: dict[str, list[dict[str, str]]] = {}
    threads = []
    lock = threading.Lock()

    def _topic_fetch(t):
        arts = fetch_topic_news(t, location=location)
        if arts:
            with lock:
                aggregated_news[t] = arts

    for t in selected_topics:
        th = threading.Thread(target=_topic_fetch, args=(t,), daemon=True)
        threads.append(th)
        th.start()

    # In parallel, check global outages
    scan_res = {}
    def _run_scan():
        nonlocal scan_res
        scan_res = check_all_outages()

    outage_th = threading.Thread(target=_run_scan, daemon=True)
    outage_th.start()

    for th in threads:
        th.join(timeout=4.0)
    outage_th.join(timeout=4.5)

    services_map = scan_res.get("services", {})
    active_outages = scan_res.get("active_outages", [])
    degraded_services = scan_res.get("degraded_services", [])
    trending_incidents = scan_res.get("trending_incidents", [])
    downdetector_incidents = scan_res.get("downdetector_incidents", [])

    # Build Markdown HUD Briefing
    period_label = period.replace("_", " ").title()
    now_str = datetime.now().strftime("%A, %B %d, %Y — %I:%M %p")
    md_lines = [
        f"# 🌍 AMATYA {period_label} Intelligence Briefing",
        f"**Date:** `{now_str}` | **Regional Scope:** `{location}`",
        "---",
    ]

    if active_outages or degraded_services or trending_incidents or downdetector_incidents:
        md_lines.append("## 📡 Global Cloud & Service Outages (Downdetector & Telemetry)")
        if active_outages:
            for o in active_outages:
                dur = o.get("duration_str") or "Just detected"
                md_lines.append(f"> ⚠️ **OUTAGE DETECTED:** **{o['service']} ({o['domain']})** is **DOWN** for **{dur}** ({o.get('error', 'Unreachable')})")
        if degraded_services:
            for d in degraded_services:
                md_lines.append(f"> 🟡 **SERVICE DEGRADED:** **{d['service']} ({d['domain']})** — *{d.get('error', 'Performance degraded')}*")
        if downdetector_incidents:
            md_lines.append("")
            md_lines.append("**Downdetector Outage Reports:**")
            for inc in downdetector_incidents[:3]:
                title = inc.get("title", "")
                link = inc.get("link", "")
                source = inc.get("source", "Downdetector")
                pub = f" ({inc['pubDate']})" if inc.get("pubDate") else ""
                if link:
                    md_lines.append(f"• **[{title}]({link})** — *{source}*{pub}")
                else:
                    md_lines.append(f"• **{title}** — *{source}*{pub}")
        if trending_incidents:
            md_lines.append("")
            md_lines.append("**Breaking Outage Reports:**")
            for inc in trending_incidents[:3]:
                title = inc.get("clean_title") or inc.get("title", "")
                link = inc.get("link", "")
                source = inc.get("source", "")
                source_tag = f" — *{source}*" if source else ""
                if link:
                    md_lines.append(f"• **[{title}]({link})**{source_tag}")
                else:
                    md_lines.append(f"• **{title}**{source_tag}")
        md_lines.append("")
        if active_outages:
            md_lines.append("| Affected Service | Domain | Status | Duration |")
            md_lines.append("| :--- | :--- | :--- | :--- |")
            for o in active_outages:
                md_lines.append(f"| **{o['service']}** | `{o['domain']}` | 🔴 DOWN | {o.get('duration_str', 'Just detected')} |")
        md_lines.append("---")
    else:
        avg_lat = sum(item.get("latency_ms", 0) for item in services_map.values()) / max(len(services_map), 1)
        md_lines.append("## 📡 Global Cloud Infrastructure")
        md_lines.append(f"> 🟢 **All {len(services_map)} Monitored Global Services Operational** (Avg Latency: `{avg_lat:.1f} ms` · Zero Outages)")
        md_lines.append("---")

    # Topic Sections
    topic_icons = {
        "geopolitics": "🌐",
        "politics": "🏛️",
        "wars": "⚔️",
        "current_affairs": "📰",
        "tech": "💻",
        "science": "🔬",
        "sports": "⚽",
        "business": "📈",
        "local_news": "📍",
    }

    speech_headlines = []
    for t in selected_topics:
        arts = aggregated_news.get(t, [])
        if not arts:
            continue
        display_topic = t.replace("_", " ").title()
        icon = topic_icons.get(t.lower(), "📌")
        md_lines.append(f"### {icon} {display_topic}")
        for a in arts:
            title = a.get("clean_title") or a["title"]
            source = a.get("source", "")
            link = a.get("link", "")
            summary = a.get("summary", "")

            source_tag = f" — *{source}*" if source else ""
            if link:
                md_lines.append(f"• **[{title}]({link})**{source_tag}")
            else:
                md_lines.append(f"• **{title}**{source_tag}")
            if summary:
                md_lines.append(f"  *{summary}*")
        md_lines.append("")
        if arts:
            lead_title = arts[0].get("clean_title") or arts[0]["title"]
            speech_headlines.append(f"In {display_topic}, {lead_title}")

    md_content = "\n".join(md_lines).strip()

    # Spoken Summary Synthesis
    if speech_headlines:
        top_slice = speech_headlines[:4]
        outage_speech = ""
        if active_outages:
            dd_names = [o['service'] for o in active_outages if o.get("downdetector_alert")]
            if dd_names:
                outage_speech = f" Note: Downdetector reports outages for {', '.join(dd_names[:2])}."
            else:
                outage_speech = f" Note: global outage detected for {', '.join(o['service'] for o in active_outages[:2])}."
        elif degraded_services:
            outage_speech = f" Note: service degradation reported for {', '.join(d['service'] for d in degraded_services[:2])}."
        spoken = f"Here is your {period} news briefing, sir. " + ". ".join(top_slice) + "." + outage_speech
    else:
        spoken = f"Your {period} briefing is ready on the HUD with the latest global and local reports."

    # Update HUD
    if player is not None:
        try:
            player.show_content(f"News Briefing ({period_label})", md_content)
            if active_outages:
                for o in active_outages:
                    player.write_log(f"ALERT: {o['service']} outage detected (down for {o.get('duration_str')})")
        except Exception:
            pass

    return {
        "period": period,
        "timestamp": now_str,
        "spoken": spoken,
        "markdown": md_content,
        "topics": selected_topics,
        "active_outages": active_outages,
    }


# ── Background Scheduler & Startup Trigger ────────────────────────────────────

_SCHEDULER_THREAD: Optional[threading.Thread] = None
_STOP_EVENT = threading.Event()
_DELIVERED_TODAY: set[str] = set()


def start_news_scheduler(player: Any = None) -> None:
    """Start background scheduler for thrice-daily briefings, startup briefing, and outage monitoring."""
    global _SCHEDULER_THREAD
    if _SCHEDULER_THREAD and _SCHEDULER_THREAD.is_alive():
        return

    _STOP_EVENT.clear()

    def _loop():
        # 1. Startup briefing on AMATYA launch
        prefs = get_news_preferences()
        if prefs.get("brief_on_startup", True):
            try:
                generate_news_briefing(period="launch", player=player)
                if not prefs.get("initialized"):
                    if player is not None:
                        try:
                            player.show_content(
                                "Choose Your Preferred News Topics",
                                "# 📰 Select Preferred Topics\n"
                                "AMATYA monitors global news across: politics, geopolitics, ongoing_wars, "
                                "current_affairs, new_developments, sports, tech, science, business, and local_news.\n\n"
                                "To customize topics, say: *'Set news topics to politics, tech and sports'* or use the `news_briefing` command."
                            )
                        except Exception:
                            pass
            except Exception:
                pass

        last_outage_check = 0.0

        while not _STOP_EVENT.is_set():
            now = datetime.now()
            today_str = now.strftime("%Y-%m-%d")
            hour_min = now.strftime("%H:%M")

            schedule_map = {
                "morning": "08:00",
                "afternoon": "13:00",
                "evening": "19:00",
            }
            times = prefs.get("briefing_times") or schedule_map

            for period, t_str in times.items():
                slot_key = f"{today_str}_{period}"
                if hour_min == t_str and slot_key not in _DELIVERED_TODAY:
                    _DELIVERED_TODAY.add(slot_key)
                    try:
                        generate_news_briefing(period=period, player=player)
                    except Exception:
                        pass

            # Outage check every 5 minutes (300 seconds)
            if time.time() - last_outage_check >= 300.0:
                last_outage_check = time.time()
                try:
                    check_all_outages()
                    active = get_current_outages()
                    if active and player is not None:
                        for o in active:
                            player.write_log(f"ALERT: {o['service']} outage detected (down for {o.get('duration_str')})")
                except Exception:
                    pass

            _STOP_EVENT.wait(timeout=30.0)

    _SCHEDULER_THREAD = threading.Thread(target=_loop, daemon=True, name="amatya-news-scheduler")
    _SCHEDULER_THREAD.start()


def stop_news_scheduler() -> None:
    _STOP_EVENT.set()
