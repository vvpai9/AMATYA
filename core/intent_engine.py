"""
AMATYA Intent Understanding Engine (core/intent_engine.py)
==========================================================
Phase 16 Core Objective A.2:
Understands user objectives, decomposes instructions, identifies implicit constraints,
determines required capabilities, detects ambiguity, and generates clarification questions.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from core.capability_registry import get_capability_registry

logger = logging.getLogger(__name__)


class IntentType(str, Enum):
    CONVERSATIONAL = "CONVERSATIONAL"          # Greetings, pleasantries, banter
    INFORMATIONAL = "INFORMATIONAL"            # Q&A, knowledge lookup, factual explanations
    OPERATIONAL_DIRECT = "OPERATIONAL_DIRECT"  # Single-step immediate tool invocation
    COMPLEX_GOAL = "COMPLEX_GOAL"              # Multi-step autonomous task graph needed
    UNCERTAIN = "UNCERTAIN"                    # Ambiguous, needs clarification


@dataclass
class ParsedIntent:
    raw_input: str
    intent_type: IntentType
    primary_goal: str
    explicit_instructions: List[str] = field(default_factory=list)
    implicit_requirements: List[str] = field(default_factory=list)
    constraints: Dict[str, Any] = field(default_factory=dict)
    required_capabilities: List[str] = field(default_factory=list)
    expected_output: str = "text"
    confidence: float = 1.0
    is_ambiguous: bool = False
    clarification_question: Optional[str] = None
    high_impact_warning: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["intent_type"] = self.intent_type.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ParsedIntent:
        d = dict(data)
        d["intent_type"] = IntentType(d.get("intent_type", "INFORMATIONAL"))
        fields = cls.__dataclass_fields__
        return cls(**{k: v for k, v in d.items() if k in fields})


class IntentEngine:
    """Understands user intent and resolves goals to operational specifications."""

    # Common conversational greetings & pleasantries
    CONVERSATIONAL_PATTERNS = (
        r"^(hi|hello|hey|good\s+(morning|afternoon|evening)|jarvis|amatya)(\s+(jarvis|amatya|there|assistant))?[\s\.,!]*$",
        r"^(how\s+are\s+you|who\s+are\s+you|what\s+is\s+your\s+name|tell\s+me\s+a\s+joke)[\s\.,!\?]*$",
        r"^(thank\s+you|thanks|good\s+job|bye|goodbye|see\s+you)[\s\.,!]*$",
    )

    # Keywords signaling complex multi-step orchestration
    COMPLEX_INDICATORS = (
        r"\b(and\s+then|after\s+that|first\b.*then\b|organize.*and.*generate|find.*and.*delete|search.*and.*summarize|clean\s+up.*and|build.*and.*test)\b",
        r"\b(audit|reorganize|refactor|benchmark|batch\s+process|workflow|pipeline|synthesize)\b",
    )

    # High-impact destructive triggers
    HIGH_IMPACT_INDICATORS = (
        r"\b(delete|remove|erase|format|kill|terminate|destroy|wipe|overwrite|purge|reboot|shutdown)\b",
    )

    # Ambiguity triggers (pronouns without clear context or underspecified broad scope)
    AMBIGUOUS_PATTERNS = (
        r"^(do\s+it|fix\s+it|run\s+that|clean\s+everything|clean\s+all|delete\s+(all|them|everything)|remove\s+(all|them|everything))[\s\.,!]*$",
        r"^(open\s+that|close\s+it|check\s+that)[\s\.,!]*$",
    )

    def __init__(self) -> None:
        pass

    def parse(self, text: str, context: Optional[Dict[str, Any]] = None) -> ParsedIntent:
        """Parse natural language instruction into structured ParsedIntent."""
        raw = (text or "").strip()
        lower = raw.lower()
        ctx = context or {}

        # ── 1. Check for Ambiguity / Underspecified Commands ──────────────────
        is_ambiguous = False
        clarification_q = None
        for pattern in self.AMBIGUOUS_PATTERNS:
            if re.search(pattern, lower):
                # Destructive commands on broad scopes ('everything', 'all') are always ambiguous
                is_destructive = any(w in lower for w in ("delete", "remove", "clean", "erase", "wipe"))
                has_entity = any(ctx.get(k) for k in ("last_file", "last_app", "last_task", "last_project", "previous_window_title"))
                if is_destructive or not has_entity:
                    is_ambiguous = True
                    clarification_q = f"Which specific target or directory do you want me to {raw}? Please confirm explicitly."
                    return ParsedIntent(
                        raw_input=raw,
                        intent_type=IntentType.UNCERTAIN,
                        primary_goal=raw,
                        is_ambiguous=True,
                        clarification_question=clarification_q,
                        confidence=0.4,
                    )

        # ── 2. Check Conversational ──────────────────────────────────────────
        for pattern in self.CONVERSATIONAL_PATTERNS:
            if re.search(pattern, lower):
                return ParsedIntent(
                    raw_input=raw,
                    intent_type=IntentType.CONVERSATIONAL,
                    primary_goal="Engage in general conversation",
                    explicit_instructions=[raw],
                    confidence=0.95,
                )

        # ── 3. Check High-Impact Warning ─────────────────────────────────────
        high_impact_warning = None
        for pattern in self.HIGH_IMPACT_INDICATORS:
            if re.search(pattern, lower):
                high_impact_warning = f"High-impact operation detected: '{raw}'. Explicit confirmation will be enforced."
                break

        # ── 4. Check Complex Goal vs. Direct Operational ─────────────────────
        is_complex = False
        for pattern in self.COMPLEX_INDICATORS:
            if re.search(pattern, lower):
                is_complex = True
                break

        # Also check for multiple coordinating conjunctions / punctuation
        steps = [s.strip() for s in re.split(r"\b(?:then|and\s+then|after\s+that)\b|[;]\s*", raw, flags=re.IGNORECASE) if s.strip()]
        if len(steps) > 1:
            is_complex = True

        # Match capabilities from CapabilityRegistry
        cap_reg = get_capability_registry()
        matched_caps: List[str] = []
        for cap in cap_reg.list_capabilities():
            # Check name or category in text
            name_words = cap.name.replace("_", " ")
            if name_words in lower or cap.name in lower:
                matched_caps.append(cap.name)

        # ── 5. Classify Intent Type ──────────────────────────────────────────
        if is_complex:
            itype = IntentType.COMPLEX_GOAL
            implicit = []
            if "delete" in lower or "remove" in lower:
                implicit.append("Verify target items before deletion to avoid data loss.")
            if "report" in lower or "summary" in lower:
                implicit.append("Format output into structured markdown.")

            return ParsedIntent(
                raw_input=raw,
                intent_type=itype,
                primary_goal=raw,
                explicit_instructions=steps if len(steps) > 1 else [raw],
                implicit_requirements=implicit,
                constraints={"safety_confirmation": bool(high_impact_warning)},
                required_capabilities=matched_caps,
                expected_output="structured_report" if "report" in lower else "task_graph_outcome",
                confidence=0.9,
                high_impact_warning=high_impact_warning,
            )

        # Direct Operational vs Informational
        action_verbs = ("open", "launch", "close", "start", "stop", "set", "play", "pause", "toggle", "mute", "unmute", "click", "type")
        if any(lower.startswith(v + " ") for v in action_verbs) or matched_caps:
            return ParsedIntent(
                raw_input=raw,
                intent_type=IntentType.OPERATIONAL_DIRECT,
                primary_goal=raw,
                explicit_instructions=[raw],
                required_capabilities=matched_caps,
                expected_output="action_status",
                confidence=0.85,
                high_impact_warning=high_impact_warning,
            )

        # Informational default
        return ParsedIntent(
            raw_input=raw,
            intent_type=IntentType.INFORMATIONAL,
            primary_goal=raw,
            explicit_instructions=[raw],
            required_capabilities=matched_caps,
            expected_output="explanation_or_answer",
            confidence=0.85,
            high_impact_warning=high_impact_warning,
        )


_INTENT_ENGINE = IntentEngine()


def get_intent_engine() -> IntentEngine:
    return _INTENT_ENGINE
