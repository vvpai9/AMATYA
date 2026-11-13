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
    """Read location from config or memory, or fallback to 'Global'."""
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

MONITORED_SERVICES = {
    "Google": "google.com",
    "Cloudflare": "cloudflare.com",
    "AWS": "aws.amazon.com",
    "GitHub": "github.com",
    "Microsoft 365": "microsoft.com",
    "X / Twitter": "x.com",
    "YouTube": "youtube.com",
    "WhatsApp": "whatsapp.com",
    "Reddit": "reddit.com",
    "OpenAI": "openai.com",
    "Discord": "discord.com",
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


# ── Outage Monitor (downforeveryoneorjustme.com telemetry) ────────────────────

def check_service_status(service_name: str, domain: str) -> dict[str, Any]:
    """Query service availability and latency."""
    now = time.time()

    # 1. Direct TCP handshake probe to port 443 / 80
    t0 = time.perf_counter()
    is_up = False
    status_code = 0
    err_msg = ""
    try:
        with socket.create_connection((domain, 443), timeout=3.5):
            is_up = True
            status_code = 200
    except Exception as exc:
        err_msg = str(exc)

    latency_ms = round((time.perf_counter() - t0) * 1000.0, 1)

    # 2. Check downforeveryoneorjustme API as secondary source if available
    try:
        api_url = f"https://downforeveryoneorjustme.com/api/v2/status/{domain}"
        req = urllib.request.Request(
            api_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AMATYA-Monitor/1.0"},
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            # downforeveryone returns isDown: bool
            if data.get("isDown") is True:
                is_up = False
                err_msg = "Confirmed down by downforeveryoneorjustme.com"
    except Exception:
        pass

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
                "latency_ms": latency_ms,
                "down_since": 0.0,
                "duration_seconds": 0,
                "duration_str": "",
                "error": "",
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
    """Scan all major monitored services in parallel."""
    results = {}
    threads = []

    def _worker(name, domain):
        results[name] = check_service_status(name, domain)

    for name, domain in MONITORED_SERVICES.items():
        t = threading.Thread(target=_worker, args=(name, domain), daemon=True)
        threads.append(t)
        t.start()

    for t in threads:
        t.join(timeout=4.5)

    active_outages = [item for item in results.values() if not item.get("is_up")]

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
        th.join(timeout=5.0)
    outage_th.join(timeout=4.0)

    services_map = scan_res.get("services", {})
    active_outages = scan_res.get("active_outages", [])

    # Build Markdown HUD Briefing
    period_label = period.replace("_", " ").title()
    now_str = datetime.now().strftime("%A, %B %d, %Y — %I:%M %p")
    md_lines = [
        f"# 🌍 AMATYA {period_label} Intelligence Briefing",
        f"**Date:** `{now_str}` | **Regional Scope:** `{location}`",
        "---",
    ]

    if active_outages:
        md_lines.append("## 📡 Global Service Outage Alerts")
        for o in active_outages:
            dur = o.get("duration_str") or "Just detected"
            md_lines.append(f"> ⚠️ **OUTAGE DETECTED:** **{o['service']} ({o['domain']})** is **DOWN** for **{dur}** ({o.get('error', 'Unreachable')})")
        md_lines.append("")
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
            outage_speech = f" Note: global outage detected for {', '.join(o['service'] for o in active_outages[:2])}."
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
