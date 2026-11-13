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

    # Check if user only asked for outage telemetry
    if params.get("check_outages_only"):
        scan = news_service.check_all_outages()
        active = scan.get("active_outages", [])
        if active:
            outage_lines = [
                f"# ⚠️ Global Web Service Outages",
                f"**Scanned:** `{scan['total_monitored']}` services | **Active Outages:** `{len(active)}`",
                "---",
            ]
            for o in active:
                outage_lines.append(f"- **{o['service']} ({o['domain']}):** DOWN for **{o.get('duration_str', 'unknown')}** ({o.get('error')})")
            if player is not None:
                try:
                    player.show_content("Global Service Outages", "\n".join(outage_lines))
                    for o in active:
                        player.write_log(f"ALERT: {o['service']} is DOWN ({o.get('duration_str')})")
                except Exception:
                    pass
            names = ", ".join(o['service'] for o in active)
            return f"Global outage alert: {names} {'is' if len(active) == 1 else 'are'} currently down."
        else:
            if player is not None:
                try:
                    player.write_log("SYS: All monitored global services (Google, AWS, Cloudflare, GitHub, OpenAI) are UP.")
                except Exception:
                    pass
            return "All monitored global services are fully operational, sir."

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
