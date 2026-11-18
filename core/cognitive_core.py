"""
AMATYA Cognitive Core (core/cognitive_core.py)
==============================================
Phase 16 Primary Cognitive Engine:
Executes the continuous 8-stage operational cycle:
  PERCEIVE → UNDERSTAND → REASON → PLAN → AUTHORIZE → EXECUTE → VERIFY → LEARN

Transforms AMATYA into a persistent, autonomous, context-aware AI operating system.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional

from core.capability_registry import get_capability_registry
from core.context_broker import get_context_broker
from core.context_manager import get_context_manager
from core.intent_engine import IntentType, ParsedIntent, get_intent_engine
from core.memory_engine import get_memory_engine
from core.perception import PerceptionEvent, PerceptionSource, get_perception_hub
from core.security import PermissionTier, get_autonomy_level, log_audit_event
from core.task_graph import TaskGraph, TaskNode, TaskState
from core.task_orchestrator import get_task_orchestrator

logger = logging.getLogger(__name__)
_LOCK = threading.RLock()


@dataclass
class CognitiveOutcome:
    cycle_id: str
    instruction: str
    intent: ParsedIntent
    response_text: str
    graph_id: Optional[str] = None
    task_status: Optional[str] = None
    execution_data: Dict[str, Any] = field(default_factory=dict)
    clarification_needed: bool = False
    clarification_question: Optional[str] = None
    duration_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["intent"] = self.intent.to_dict()
        return d


class CognitiveCore:
    """AMATYA Unified Cognitive Engine implementing the 8-stage operational cycle."""

    def __init__(self) -> None:
        self.perception_hub = get_perception_hub()
        self.intent_engine = get_intent_engine()
        self.context_broker = get_context_broker()
        self.context_manager = get_context_manager()
        self.orchestrator = get_task_orchestrator()
        self.cap_registry = get_capability_registry()
        self.memory_engine = get_memory_engine()

    def process(
        self,
        text: str,
        source: PerceptionSource = PerceptionSource.TEXT_CHAT,
        user: str = "user",
        player: Any = None,
        speak: Optional[Callable[[str], None]] = None,
        interactive: bool = True,
    ) -> CognitiveOutcome:
        """Run the full 8-stage cognitive cycle on input text or voice."""
        start_time = time.time()
        cycle_id = f"cog_{int(start_time)}_{text[:10].replace(' ', '_')}"

        # ── 1. PERCEIVE ───────────────────────────────────────────────────────
        if source == PerceptionSource.VOICE:
            evt = self.perception_hub.ingest_voice_transcript(text, speaker=user)
        else:
            evt = self.perception_hub.ingest_user_text(text, user=user)

        # ── 2. UNDERSTAND ─────────────────────────────────────────────────────
        # Context reference resolution (e.g. 'Open that', 'the previous window')
        resolved_dict = self.context_manager.resolve_references(text)
        resolved_text = resolved_dict.get("resolved", text)

        intent = self.intent_engine.parse(resolved_text, context=self.context_manager.get_state())

        # If instruction is ambiguous and clarification is required:
        if intent.is_ambiguous and intent.clarification_question:
            q_text = intent.clarification_question
            if player and hasattr(player, "write_log"):
                player.write_log(f"AMATYA: Clarification needed: {q_text}")
            if speak:
                speak(q_text)
            return CognitiveOutcome(
                cycle_id=cycle_id,
                instruction=text,
                intent=intent,
                response_text=q_text,
                clarification_needed=True,
                clarification_question=q_text,
                duration_seconds=round(time.time() - start_time, 2),
            )

        # ── 3. REASON ─────────────────────────────────────────────────────────
        # Handle Conversational
        if intent.intent_type == IntentType.CONVERSATIONAL:
            resp = self._handle_conversational(resolved_text, player=player)
            if speak:
                speak(resp)
            self._learn_step(resolved_text, "conversational", resp)
            return CognitiveOutcome(
                cycle_id=cycle_id,
                instruction=text,
                intent=intent,
                response_text=resp,
                duration_seconds=round(time.time() - start_time, 2),
            )

        # Handle Informational / Q&A
        if intent.intent_type == IntentType.INFORMATIONAL and not intent.required_capabilities:
            resp = self._handle_informational(resolved_text, player=player)
            if speak:
                speak(resp)
            self._learn_step(resolved_text, "informational", resp)
            return CognitiveOutcome(
                cycle_id=cycle_id,
                instruction=text,
                intent=intent,
                response_text=resp,
                duration_seconds=round(time.time() - start_time, 2),
            )

        # ── 4. PLAN ───────────────────────────────────────────────────────────
        # Construct dependency-aware TaskGraph
        graph = self._plan_task_graph(resolved_text, intent)

        # ── 5. AUTHORIZE ──────────────────────────────────────────────────────
        # Graph execution checks authorization per node; if any node requires confirmation,
        # it transitions to WAITING_FOR_APPROVAL and notifies.
        self.orchestrator.submit_graph(graph)

        # ── 6. EXECUTE ────────────────────────────────────────────────────────
        # Execute graph synchronously or asynchronously based on complexity
        is_direct = (intent.intent_type == IntentType.OPERATIONAL_DIRECT)
        completed_graph = self.orchestrator.run_graph(graph.graph_id, async_exec=not is_direct)

        # ── 7. VERIFY ─────────────────────────────────────────────────────────
        # Summarize outcome
        summary = self._summarize_graph_outcome(completed_graph)

        # ── 8. LEARN ──────────────────────────────────────────────────────────
        self._learn_step(resolved_text, "workflow", summary, metadata={"graph_id": graph.graph_id})

        if player and hasattr(player, "write_log"):
            player.write_log(f"AMATYA: {summary}")
        if speak and is_direct:
            speak(summary)

        return CognitiveOutcome(
            cycle_id=cycle_id,
            instruction=text,
            intent=intent,
            response_text=summary,
            graph_id=graph.graph_id,
            task_status=completed_graph.status.value,
            execution_data=completed_graph.to_dict(),
            duration_seconds=round(time.time() - start_time, 2),
        )

    def _handle_conversational(self, text: str, player: Any = None) -> str:
        """Handle conversational greeting or pleasantry."""
        lower = text.lower()
        if any(g in lower for g in ("morning", "afternoon", "evening", "hello", "hi", "hey")):
            resp = "Good day, sir. AMATYA cognitive systems online and standing by. How may I assist you?"
        elif "who are you" in lower:
            resp = "I am AMATYA, your autonomous personal AI operating system, designed to understand, plan, execute, and verify tasks across your digital and physical environment."
        elif "thank" in lower:
            resp = "At your service, sir. Always."
        else:
            resp = "Systems operational and listening, sir."

        if player and hasattr(player, "show_content"):
            player.show_content("AMATYA Assistant", resp)
        return resp

    def _handle_informational(self, query: str, player: Any = None) -> str:
        """Answer informational query using context broker."""
        system_context = self.context_broker.render_system_prompt_context(query)
        try:
            from core import gemini
            prompt = (
                f"You are AMATYA (JARVIS-level personal AI). Ground your answer strictly in system context.\n\n"
                f"{system_context}\n\n"
                f"User Question: {query}\n\n"
                f"Provide a concise, professional answer."
            )
            answer = gemini.text(prompt, tier=gemini.FAST)
            if answer:
                if player and hasattr(player, "show_content"):
                    player.show_content("AMATYA Intelligence", answer)
                return answer
        except Exception as e:
            logger.debug(f"Gemini fallback for query: {e}")

        resp = f"Informational query received: '{query}'. Context active."
        return resp

    def _plan_task_graph(self, text: str, intent: ParsedIntent) -> TaskGraph:
        """Create a TaskGraph matching the parsed instructions and capabilities."""
        graph = TaskGraph(goal=text, resolved_goal=text)

        # Direct Operational (single action)
        if intent.intent_type == IntentType.OPERATIONAL_DIRECT or len(intent.explicit_instructions) <= 1:
            cap_name = intent.required_capabilities[0] if intent.required_capabilities else "code_helper"
            node = TaskNode(
                node_id="task_1",
                objective=text,
                capability=cap_name,
                parameters={"instruction": text, "action": "execute"},
                risk_level="high" if intent.high_impact_warning else "low",
            )
            graph.add_node(node)
            return graph

        # Multi-step complex workflow
        prev_node_id = None
        for idx, step_desc in enumerate(intent.explicit_instructions):
            node_id = f"step_{idx + 1}"
            # Identify best matching capability
            step_lower = step_desc.lower()
            matched_cap = "code_helper"
            for cap in intent.required_capabilities:
                if cap in step_lower:
                    matched_cap = cap
                    break

            deps = [prev_node_id] if prev_node_id else []
            node = TaskNode(
                node_id=node_id,
                objective=step_desc,
                capability=matched_cap,
                parameters={"instruction": step_desc},
                dependencies=deps,
                risk_level="high" if any(w in step_lower for w in ("delete", "remove", "kill")) else "low",
            )
            graph.add_node(node)
            prev_node_id = node_id

        return graph

    def _summarize_graph_outcome(self, graph: TaskGraph) -> str:
        """Produce human-readable outcome summary of the task graph."""
        if graph.status == TaskState.COMPLETED:
            return f"Successfully executed workflow: '{graph.goal}'. All {len(graph.nodes)} task(s) completed and verified."
        elif graph.status == TaskState.WAITING_FOR_APPROVAL:
            waiting = [n.node_id for n in graph.nodes.values() if n.state == TaskState.WAITING_FOR_APPROVAL]
            return f"Workflow '{graph.goal}' is paused awaiting your authorization for: {', '.join(waiting)}."
        elif graph.status == TaskState.FAILED:
            failed_nodes = [f"{n.node_id} ({n.error})" for n in graph.nodes.values() if n.state == TaskState.FAILED]
            return f"Workflow '{graph.goal}' halted due to failure: {'; '.join(failed_nodes)}."
        else:
            return f"Workflow '{graph.goal}' is currently {graph.status.value}."

    def _learn_step(self, instruction: str, category: str, result_summary: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Record the episode and entity interactions in persistent memory."""
        try:
            self.memory_engine.record_event(
                category=category,
                summary=f"Executed: {instruction} -> {result_summary[:100]}",
                metadata=metadata or {},
            )
        except Exception as e:
            logger.debug(f"Failed to record memory event: {e}")


_COGNITIVE_CORE = CognitiveCore()


def get_cognitive_core() -> CognitiveCore:
    return _COGNITIVE_CORE

