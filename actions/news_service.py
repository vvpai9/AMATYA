"""
actions/news_service.py — AMATYA World Affairs News Intelligence & Outage Action
================================================================================
Exposes actions for:
  - World & local news briefings across politics, geopolitics, wars, tech, sports.
  - Configuring user preferred topics on initialization or on demand.
  - Tracking global website and cloud service outages with downtime duration.
"""
from __future__ import annotations

from typing import Any

from core import news_service


def news_briefing_action(
    parameters: dict,
    player: Any = None,
    session_memory: Any = None,
    **kwargs,
) -> str:
    """Action handler for news briefings and topic configuration."""
    params = parameters or {}

    # Check if user wants to update preferred topics
    new_topics = params.get("configure_topics")
    if new_topics:
        if isinstance(new_topics, str):
            topic_list = [t.strip() for t in new_topics.replace(",", " ").split() if t.strip()]
        else:
            topic_list = list(new_topics)
        updated = news_service.set_user_topics(topic_list)
        msg = f"News preferences updated. Now following: {', '.join(updated.get('topics', []))}."
        if player is not None:
            try:
                player.write_log(f"SYS: {msg}")
            except Exception:
                pass
        return msg

    # Check if user asked for outage telemetry
    action_val = str(params.get("action", "")).lower()
    if params.get("check_outages_only") or action_val in ("outages", "outage", "check_outages", "infrastructure", "down"):
        scan = news_service.check_all_outages()
        active = scan.get("active_outages", [])
        services_map = scan.get("services", {})
        downdetector_incidents = scan.get("downdetector_incidents", [])

        operational_count = sum(1 for s in services_map.values() if s.get("is_up", True))
        avg_lat = (
            sum(item.get("latency_ms", 0) for item in services_map.values() if item.get("is_up"))
            / max(operational_count, 1)
        )
        outage_lines = [
            f"# 📡 Global Cloud Infrastructure & Outage Monitor",
            f"**Operational:** `{operational_count}/{scan['total_monitored']}` | **Active Outages:** `{len(active)}` | **Avg Latency:** `{avg_lat:.1f} ms`",
            "---",
        ]
        if active:
            outage_lines.append("### 🔴 Active Service Outages")
            outage_lines.append("| Affected Service | Status | Duration | Diagnostic Detail |")
            outage_lines.append("| :--- | :---: | :---: | :--- |")
            for o in active:
                dur = o.get("duration_str") or "Just detected"
                err = o.get("error") or "Unreachable"
                outage_lines.append(f"| **{o['service']}** | 🔴 DOWN | `{dur}` | {err} |")
            outage_lines.append("")
        else:
            outage_lines.append("> 🟢 **All monitored global platforms operational — zero active outages detected.**\n")

        if downdetector_incidents:
            outage_lines.append("### 📡 Downdetector Trending Disruptions")
            for inc in downdetector_incidents[:4]:
                title = inc.get("title", "")
                link = inc.get("link", "")
                src = inc.get("source", "Downdetector")
                pub = f" ({inc['pubDate']})" if inc.get("pubDate") else ""
                if link:
                    outage_lines.append(f"• **[{title}]({link})** — *{src}*{pub}")
                else:
                    outage_lines.append(f"• **{title}** — *{src}*{pub}")
            outage_lines.append("")

        outage_lines.append("### 🌐 Monitored Global Endpoints")
        outage_lines.append("| Platform | Status | Response Latency |")
        outage_lines.append("| :--- | :---: | :---: |")
        for s_name in sorted(services_map.keys()):
            item = services_map[s_name]
            is_up = item.get("is_up", True)
            status_badge = "🟢 Operational" if is_up else "🔴 OUTAGE"
            lat = f"`{item.get('latency_ms', 0):.1f} ms`" if is_up else "`Timeout`"
            outage_lines.append(f"| **{s_name}** | {status_badge} | {lat} |")

        if player is not None:
            try:
                player.show_content("Global Service Outages & Infrastructure", "\n".join(outage_lines))
                if active:
                    for o in active:
                        player.write_log(f"ALERT: {o['service']} is DOWN ({o.get('duration_str')})")
                else:
                    player.write_log("SYS: All monitored global cloud platforms (Google, AWS, Cloudflare, GitHub, OpenAI) are UP.")
            except Exception:
                pass

        if active:
            names = ", ".join(o['service'] for o in active)
            return f"Global outage alert: {names} {'is' if len(active) == 1 else 'are'} currently down. Detailed telemetry is on your HUD."
        return f"All {scan['total_monitored']} monitored global services (including Google, AWS, Cloudflare, GitHub, OpenAI, and WhatsApp) are operational with zero detected outages."

    # Generate full news briefing
    period = str(params.get("period") or "current").lower()
    specific_topic = params.get("topic")
    topics = [specific_topic] if specific_topic else None

    briefing = news_service.generate_news_briefing(period=period, topics=topics, player=player)
    return briefing.get("spoken", "News briefing generated on HUD.")


SKILL_METADATA = {
    "capabilities": [
        "news_briefing",
        "global_affairs",
        "geopolitics",
        "outage_monitoring",
        "topic_customization",
    ],
    "permissions": ["network_access"],
    "dependencies": ["feedparser"],
    "supported_actions": ["news", "briefing", "outages", "configure_topics"],
    "security_level": "normal",
}

TOOL = {
    "name": "news_briefing",
    "description": (
        "Provides comprehensive global and local news briefings across politics, geopolitics, "
        "ongoing wars, technology, sports, and current affairs. Also monitors global outages "
        "for major internet services with downtime duration tracking and displays them on the HUD."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "period": {
                "type": "STRING",
                "enum": ["morning", "afternoon", "evening", "launch", "current"],
                "description": "Briefing schedule period (morning, afternoon, evening, launch, or current).",
            },
            "topic": {
                "type": "STRING",
                "description": "Specific news topic (politics, geopolitics, ongoing_wars, tech, sports, science, business, local_news).",
            },
            "check_outages_only": {
                "type": "BOOLEAN",
                "description": "If true, only checks and displays live global service outages without fetching news.",
            },
            "configure_topics": {
                "type": "ARRAY",
                "items": {"type": "STRING"},
                "description": "List of preferred topics to customize user preferences.",
            },
        },
    },
    "handler": news_briefing_action,
}
