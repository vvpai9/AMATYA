"""
AMATYA Unified Context Broker (core/context_broker.py)
======================================================
Phase 16 Core Objective A:
Synthesizes Working Memory, Episodic Memory, Semantic Knowledge, Knowledge Graph,
and Environmental Telemetry into a unified context payload.

Includes rigorous prompt injection boundary tagging to isolate untrusted external content.
"""
from __future__ import annotations

import html
import logging
import re
import threading
import time
from typing import Any, Dict, List, Optional

from core.context_manager import get_context_manager
from core.environmental_awareness import get_environmental_awareness
from core.knowledge_graph import get_knowledge_graph
from core.memory_engine import get_memory_engine

logger = logging.getLogger(__name__)
_LOCK = threading.RLock()


def wrap_untrusted_content(content: str, source: str, label: str = "") -> str:
    """Isolate untrusted content within strict security boundary delimiters.

    Escapes any closing tags or prompt-breaking tokens within the payload to prevent
    delimiter spoofing or context breakout attacks.
    """
    if not content:
        return ""

    safe_text = str(content)
    # Neutralize nested boundary closing tags
    safe_text = re.sub(r"</\s*UNTRUSTED_CONTENT\s*>", r"&lt;/UNTRUSTED_CONTENT&gt;", safe_text, flags=re.IGNORECASE)
    # Neutralize common chat template delimiters
    safe_text = safe_text.replace("<|im_start|>", "&lt;|im_start|&gt;").replace("<|im_end|>", "&lt;|im_end|&gt;")

    label_attr = f' label="{html.escape(label)}"' if label else ""
    return (
        f'<UNTRUSTED_CONTENT source="{html.escape(source)}"{label_attr}>\n'
        f"{safe_text}\n"
        f"</UNTRUSTED_CONTENT>"
    )


class ContextBroker:
    """Synthesizes all layers of AMATYA context into a cohesive, secure representation."""

    def __init__(self) -> None:
        self.context_mgr = get_context_manager()
        self.memory_engine = get_memory_engine()
        self.knowledge_graph = get_knowledge_graph()
        self.env_awareness = get_environmental_awareness()

    def build_cognitive_context(
        self,
        query: str,
        include_environment: bool = True,
        max_episodes: int = 3,
        max_kg_depth: int = 1,
    ) -> Dict[str, Any]:
        """Aggregate all context sources into a structured dictionary."""
        with _LOCK:
            # 1. Working Context (entities, recent turns, focused window)
            working_st = self.context_mgr.get_state()

            # 2. Episodic Memory (relevant past sessions & events)
            recent_episodes = self.memory_engine.get_recent_episodes(limit=max_episodes)

            # 3. Semantic Memory (facts & preferences relevant to query)
            relevant_facts = self.memory_engine.search_memories(query, limit=5)

            # 4. Knowledge Graph (entities related to query or working context)
            kg_entities = []
            entity_cand = working_st.get("last_entity") or working_st.get("last_project") or ""
            if entity_cand:
                ent = self.knowledge_graph.get_entity(entity_cand)
                if ent:
                    kg_entities.append(ent)

            # 5. Environmental Telemetry
            env_snap = self.env_awareness.get_snapshot().to_dict() if include_environment else {}

            return {
                "timestamp": time.time(),
                "query": query,
                "working_context": working_st,
                "recent_episodes": recent_episodes,
                "relevant_facts": relevant_facts,
                "kg_entities": kg_entities,
                "environment": env_snap,
            }

    def render_system_prompt_context(self, query: str) -> str:
        """Render context as a clean markdown block suitable for LLM system prompts."""
        bundle = self.build_cognitive_context(query)
        lines: List[str] = ["### Contextual Situational Awareness"]

        # Working context
        wk = bundle["working_context"]
        active_items = []
        if wk.get("current_window_title"):
            active_items.append(f"Active Window: '{wk['current_window_title']}'")
        if wk.get("last_file"):
            active_items.append(f"Recent File: '{wk['last_file']}'")
        if wk.get("last_project"):
            active_items.append(f"Active Project: '{wk['last_project']}'")
        if wk.get("last_device"):
            active_items.append(f"Primary Device: '{wk['last_device']}'")

        if active_items:
            lines.append("- " + " | ".join(active_items))

        # System health & alerts
        env = bundle.get("environment", {})
        health = env.get("system_health", {})
        if health:
            sys_str = f"CPU: {health.get('cpu_pct', 0)}% | RAM: {health.get('ram_pct', 0)}%"
            if health.get("battery_pct") is not None:
                sys_str += f" | Battery: {health.get('battery_pct')}%"
            lines.append(f"- Telemetry: {sys_str}")

        alerts = env.get("telemetry_alerts", [])
        if alerts:
            lines.append(f"- Active System Alerts: {'; '.join(alerts)}")

        # Relevant facts
        facts = bundle.get("relevant_facts", [])
        if facts:
            fact_strs = [f.get("content", str(f)) for f in facts if isinstance(f, dict)]
            if fact_strs:
                lines.append(f"- Relevant User Knowledge: {'; '.join(fact_strs[:3])}")

        return "\n".join(lines)


_CONTEXT_BROKER = ContextBroker()


def get_context_broker() -> ContextBroker:
    return _CONTEXT_BROKER

