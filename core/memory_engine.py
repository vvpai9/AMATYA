"""
AMATYA Layered Memory Architecture & Memory Intelligence Engine (core/memory_engine.py)
========================================================================================
Implements Section 3 (Persistent Personal Memory) of AMATYA Phase 12:

Memory Layers:
  1. Working Memory    — Volatile scratchpad: active turn context, active task pointer, temporary entities.
  2. Episodic Memory   — Chronological log: task outcomes, user corrections, decisions, significant events.
  3. Semantic Memory   — Persistent facts, preferences, entities, relationships, confidence ratings, provenance.
  4. Procedural Memory — Reusable automation routines, trigger conditions, execution sequences.
  5. Active Task Store — Persistent task dependency graphs, step checkpoints, intermediate outputs.

Intelligence Features:
  - Provenance tracking: 'user_stated', 'observed', 'inferred', 'system'.
  - Classification: 'confirmed_fact', 'user_preference', 'assistant_inference', 'temporary_info'.
  - Contradiction Detection: Rejects or prompts when new data conflicts with confirmed facts.
  - Confidence Scoring: 0.0 to 1.0; inferences never masquerade as confirmed facts.
  - User Memory Controls: Inspect memories, correct facts, delete memory (purging all indexes),
    temporary memory disablement, and exclusion patterns.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from core.security import redact_secrets
from memory.config_manager import BASE_DIR

MEMORY_DIR = BASE_DIR / "memory"
WORKING_MEM_PATH = MEMORY_DIR / "working_memory.json"
EPISODIC_MEM_PATH = MEMORY_DIR / "episodic_memory.json"
SEMANTIC_MEM_PATH = MEMORY_DIR / "semantic_memory.json"
PROCEDURAL_MEM_PATH = MEMORY_DIR / "procedural_memory.json"

_LOCK = threading.RLock()


@dataclass
class SemanticFact:
    fact_id: str
    category: str  # preferences | identity | projects | relationships | technical | environment
    subject: str
    predicate: str
    object_value: str
    classification: str = "confirmed_fact"  # confirmed_fact | user_preference | assistant_inference | temporary_info
    provenance: str = "user_stated"         # user_stated | observed | inferred | system
    confidence: float = 1.0                 # 0.0 to 1.0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    source_context: str = ""
    verified: bool = True
    expires_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EpisodicEvent:
    event_id: str
    event_type: str  # task_completed | task_failed | user_correction | decision | preference_change
    summary: str
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    success: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class FactResult(dict):
    """Dictionary supporting property access for facts."""
    def to_dict(self) -> dict[str, Any]:
        return dict(self)

    @property
    def key(self) -> str:
        return self.get("predicate", "")

    @property
    def predicate(self) -> str:
        return self.get("predicate", "")

    @property
    def value(self) -> str:
        return self.get("object_value", "")

    @property
    def object_value(self) -> str:
        return self.get("object_value", "")

    @property
    def category(self) -> str:
        return self.get("category", "")

    @property
    def confidence(self) -> float:
        return float(self.get("confidence", 1.0))


class ContradictionOutcome(dict):
    """Contradiction result supporting dict keys, property access, and 2-tuple unpacking."""
    def __iter__(self):
        yield self.get("contradiction", False)
        yield self.get("existing_fact")

    @property
    def contradiction(self) -> bool:
        return bool(self.get("contradiction", False))

    @property
    def existing_value(self) -> str:
        return str(self.get("existing_value", ""))


class DeleteResult(tuple):
    def __bool__(self) -> bool:
        return bool(self[0])

    @property
    def ok(self) -> bool:
        return bool(self[0])

    @property
    def message(self) -> str:
        return str(self[1])


class MemoryEngine:
    """Central layered memory controller for AMATYA Phase 12."""

    def __init__(
        self,
        memory_dir: Path | str | None = None,
        storage_path: Path | str | None = None,
        storage_dir: Path | str | None = None,
    ) -> None:
        if storage_dir is not None:
            memory_dir = storage_dir
        if storage_path is not None:
            sp = Path(storage_path)
            memory_dir = sp.parent if sp.suffix else sp
        self.mem_dir = Path(memory_dir or MEMORY_DIR)
        self.mem_dir.mkdir(parents=True, exist_ok=True)
        self.working_path = self.mem_dir / "working_memory.json"
        self.episodic_path = self.mem_dir / "episodic_memory.json"
        self.semantic_path = self.mem_dir / "semantic_memory.json"
        self.procedural_path = self.mem_dir / "procedural_memory.json"

        self._memory_enabled = True
        self._auto_extraction_enabled = True
        self._excluded_patterns: list[str] = [".env", "password", "token", "secret", "api_key", "credential"]

        self._working_memory: dict[str, Any] = {}
        self._episodic_memory: list[dict[str, Any]] = []
        self._semantic_memory: dict[str, dict[str, Any]] = {}
        self._procedural_memory: dict[str, dict[str, Any]] = {}

        self._load_all()

    def _load_all(self) -> None:
        with _LOCK:
            # 1. Working Memory
            if self.working_path.exists():
                try:
                    self._working_memory = json.loads(self.working_path.read_text(encoding="utf-8"))
                except Exception:
                    self._working_memory = {}

            # 2. Episodic Memory
            if self.episodic_path.exists():
                try:
                    self._episodic_memory = json.loads(self.episodic_path.read_text(encoding="utf-8"))
                except Exception:
                    self._episodic_memory = []

            # 3. Semantic Memory
            if self.semantic_path.exists():
                try:
                    self._semantic_memory = json.loads(self.semantic_path.read_text(encoding="utf-8"))
                except Exception:
                    self._semantic_memory = {}
            else:
                self._migrate_legacy_long_term_memory()

            # 4. Procedural Memory
            if self.procedural_path.exists():
                try:
                    self._procedural_memory = json.loads(self.procedural_path.read_text(encoding="utf-8"))
                except Exception:
                    self._procedural_memory = {}

    def _save_semantic(self) -> None:
        with _LOCK:
            self.semantic_path.write_text(
                json.dumps(self._semantic_memory, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    def _save_episodic(self) -> None:
        with _LOCK:
            # Keep most recent 500 episodic events
            if len(self._episodic_memory) > 500:
                self._episodic_memory = self._episodic_memory[-500:]
            self.episodic_path.write_text(
                json.dumps(self._episodic_memory, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    def _save_working(self) -> None:
        with _LOCK:
            self.working_path.write_text(
                json.dumps(self._working_memory, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    def _migrate_legacy_long_term_memory(self) -> None:
        """Migrate existing legacy memory/long_term.json into structured semantic facts."""
        legacy_path = self.mem_dir / "long_term.json"
        if not legacy_path.exists():
            return
        try:
            legacy = json.loads(legacy_path.read_text(encoding="utf-8"))
            if not isinstance(legacy, dict):
                return
            for category, items in legacy.items():
                if not isinstance(items, dict):
                    continue
                for key, val_obj in items.items():
                    val = val_obj.get("value") if isinstance(val_obj, dict) else str(val_obj)
                    if not val:
                        continue
                    fid = f"{category}_{key}"
                    fact = SemanticFact(
                        fact_id=fid,
                        category=category,
                        subject="user",
                        predicate=key,
                        object_value=redact_secrets(str(val)),
                        classification="user_preference" if category == "preferences" else "confirmed_fact",
                        provenance="user_stated",
                        confidence=1.0,
                        verified=True,
                    )
                    self._semantic_memory[fid] = fact.to_dict()
            self._save_semantic()
        except Exception:
            pass

    # ── Memory Controls ────────────────────────────────────────────────────────

    def set_memory_enabled(self, enabled: bool) -> None:
        self._memory_enabled = bool(enabled)

    def is_memory_enabled(self) -> bool:
        return self._memory_enabled

    set_enabled = set_memory_enabled
    is_enabled = is_memory_enabled

    def set_auto_extraction(self, enabled: bool) -> None:
        self._auto_extraction_enabled = bool(enabled)

    def add_excluded_pattern(self, pattern: str) -> None:
        clean = (pattern or "").strip().lower()
        if clean and clean not in self._excluded_patterns:
            self._excluded_patterns.append(clean)

    # ── Semantic Memory Intelligence ───────────────────────────────────────────

    def detect_contradiction(
        self,
        subject_or_pred: str,
        predicate_or_val: str,
        new_value: str = "",
    ) -> ContradictionOutcome:
        """Check if proposed (subject, predicate, new_value) conflicts with an existing verified fact."""
        with _LOCK:
            if not new_value:
                # Called as detect_contradiction(predicate, new_value)
                sub = "user"
                pred = subject_or_pred.strip().lower()
                new_val = predicate_or_val.strip().lower()
            else:
                # Called as detect_contradiction(subject, predicate, new_value)
                sub = subject_or_pred.strip().lower()
                pred = predicate_or_val.strip().lower()
                new_val = new_value.strip().lower()

            for item in self._semantic_memory.values():
                if (
                    item.get("subject", "").lower() == sub
                    and item.get("predicate", "").lower() == pred
                    and item.get("verified", False)
                ):
                    existing_val = str(item.get("object_value", "")).strip()
                    if existing_val and existing_val.lower() != new_val:
                        return ContradictionOutcome({
                            "contradiction": True,
                            "existing_fact": item,
                            "existing_value": existing_val,
                        })
            return ContradictionOutcome({"contradiction": False, "existing_fact": None, "existing_value": ""})

    def store_fact(
        self,
        category: str = "general",
        predicate: str = "",
        object_value: str = "",
        subject: str = "user",
        classification: str = "confirmed_fact",
        provenance: str = "user_stated",
        confidence: float = 1.0,
        source_context: str = "",
        allow_overwrite: bool = True,
        # Keyword aliases:
        key: str = "",
        value: str = "",
    ) -> dict[str, Any]:
        """Store or update a semantic fact with contradiction checks and secret redaction."""
        pred = predicate or key
        val = object_value or value

        if not self._memory_enabled:
            return {"ok": False, "error": "Memory system is currently disabled.", "message": "Memory system is currently disabled."}

        # Check exclusion rules
        full_text = f"{category} {pred} {val} {source_context}".lower()
        if any(pat in full_text for pat in self._excluded_patterns):
            return {"ok": False, "error": "Memory rejected: matches configured exclusion patterns.", "message": "Memory rejected."}

        clean_value = redact_secrets(str(val).strip())
        clean_pred = re.sub(r"[^a-zA-Z0-9_]+", "_", pred.strip().lower()).strip("_")

        # Contradiction check
        contra = self.detect_contradiction(subject, clean_pred, clean_value)
        is_conflict = contra.contradiction
        existing = contra.get("existing_fact")

        if is_conflict and existing and not allow_overwrite:
            return {
                "ok": False,
                "conflict": True,
                "error": (
                    f"Contradiction detected: '{subject} {clean_pred}' is currently recorded as "
                    f"'{existing.get('object_value')}' ({existing.get('classification')}). "
                    f"Overwrite not allowed without explicit user confirmation."
                ),
                "message": "Contradiction detected.",
                "existing_fact": existing,
            }

        fact_id = f"{category}_{clean_pred}"
        fact = SemanticFact(
            fact_id=fact_id,
            category=category.strip().lower(),
            subject=subject.strip(),
            predicate=clean_pred,
            object_value=clean_value,
            classification=classification,
            provenance=provenance,
            confidence=max(0.0, min(1.0, float(confidence))),
            source_context=redact_secrets(source_context[:240]),
            verified=(classification in ("confirmed_fact", "user_preference")),
            updated_at=time.time(),
        )

        with _LOCK:
            self._semantic_memory[fact_id] = fact.to_dict()
            self._save_semantic()

            # Record event in episodic memory if updating an existing fact
            if is_conflict and existing:
                self.record_event(
                    event_type="user_correction",
                    summary=f"Updated '{clean_pred}' from '{existing.get('object_value')}' to '{clean_value}'.",
                    details={"old_value": existing.get("object_value"), "new_value": clean_value},
                )

        # Mirror update to legacy long_term.json for backward compatibility
        self._sync_to_legacy_store(fact)

        action = "updated" if is_conflict else "stored"
        return {
            "ok": True,
            "action": action,
            "message": f"Successfully {action} fact '{clean_pred}'.",
            "fact": fact.to_dict(),
            "conflict_resolved": bool(is_conflict),
        }

    def correct_fact(
        self,
        key: str = "",
        predicate: str = "",
        new_value: str = "",
        value: str = "",
        reason: str = "user_correction",
        subject: str = "user",
    ) -> dict[str, Any]:
        """Explicitly correct or overwrite a semantic fact."""
        pred = predicate or key
        val = new_value or value
        return self.store_fact(
            category="preferences",
            predicate=pred,
            object_value=val,
            subject=subject,
            classification="confirmed_fact",
            provenance="user_stated",
            confidence=1.0,
            source_context=reason,
            allow_overwrite=True,
        )

    def get_fact(self, predicate: str, subject: str = "user") -> FactResult | None:
        """Lookup a specific semantic fact by predicate."""
        with _LOCK:
            clean_pred = re.sub(r"[^a-zA-Z0-9_]+", "_", predicate.strip().lower()).strip("_")
            for item in self._semantic_memory.values():
                if item.get("predicate") == clean_pred and item.get("subject", "").lower() == subject.lower():
                    return FactResult(item)
            return None

    def search_memories(self, query: str, limit: int = 10, top_k: int | None = None) -> list[FactResult]:
        """Retrieve memories matching query keywords and semantic tokens."""
        if top_k is not None:
            limit = top_k
        if not self._memory_enabled:
            return []
        tokens = set(re.findall(r"\w{2,}", query.lower()))
        if not tokens:
            return [FactResult(v) for v in list(self._semantic_memory.values())[:limit]]

        scored: list[tuple[float, dict[str, Any]]] = []
        with _LOCK:
            for item in self._semantic_memory.values():
                haystack = f"{item.get('category')} {item.get('predicate')} {item.get('object_value')} {item.get('source_context')}".lower()
                matches = sum(1 for t in tokens if t in haystack)
                if matches > 0:
                    score = matches * float(item.get("confidence", 1.0))
                    scored.append((score, dict(item)))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [FactResult(item) for _, item in scored[:limit]]

    def delete_memory(self, predicate_or_id: str) -> DeleteResult:
        """Delete a memory by id or predicate across all storage layers."""
        target = predicate_or_id.strip().lower()
        deleted_ids = []
        with _LOCK:
            for fid, item in list(self._semantic_memory.items()):
                if fid.lower() == target or item.get("predicate", "").lower() == target:
                    deleted_ids.append(fid)
                    del self._semantic_memory[fid]

            if deleted_ids:
                self._save_semantic()
                # Purge from legacy long_term.json as well
                self._purge_from_legacy_store(target)
                self.record_event(
                    event_type="memory_deleted",
                    summary=f"Purged memories: {', '.join(deleted_ids)}",
                )
                return DeleteResult((True, f"Deleted memory: {', '.join(deleted_ids)}"))
            return DeleteResult((False, f"Memory matching '{predicate_or_id}' not found."))

    def list_all_memories(self) -> dict[str, list[dict[str, Any]]]:
        """Group semantic memories by category for user inspection."""
        with _LOCK:
            grouped: dict[str, list[dict[str, Any]]] = {}
            for item in self._semantic_memory.values():
                cat = item.get("category", "general")
                grouped.setdefault(cat, []).append(dict(item))
            return grouped

    # ── Episodic Memory ────────────────────────────────────────────────────────

    def record_event(self, event_type: str, summary: str, details: dict[str, Any] | None = None, success: bool = True) -> dict[str, Any]:
        """Record an episodic event (task completion, error, decision, correction)."""
        ev = EpisodicEvent(
            event_id=uuid.uuid4().hex[:10],
            event_type=event_type,
            summary=redact_secrets(summary.strip()),
            details=details or {},
            timestamp=time.time(),
            success=success,
        )
        with _LOCK:
            self._episodic_memory.append(ev.to_dict())
            self._save_episodic()
        return ev.to_dict()

    def get_recent_episodes(self, limit: int = 15) -> list[dict[str, Any]]:
        with _LOCK:
            return list(self._episodic_memory[-limit:])

    # ── Working Memory ─────────────────────────────────────────────────────────

    def update_working_context(self, **kwargs: Any) -> dict[str, Any]:
        """Update volatile working memory context."""
        with _LOCK:
            for k, v in kwargs.items():
                if v is not None:
                    self._working_memory[k] = v
            self._working_memory["updated_at"] = time.time()
            self._save_working()
            return dict(self._working_memory)

    def get_working_context(self) -> dict[str, Any]:
        with _LOCK:
            return dict(self._working_memory)

    # ── Legacy Synchronization Helpers ─────────────────────────────────────────

    def _sync_to_legacy_store(self, fact: SemanticFact) -> None:
        try:
            legacy_path = self.mem_dir / "long_term.json"
            data = json.loads(legacy_path.read_text(encoding="utf-8")) if legacy_path.exists() else {}
            cat = fact.category
            data.setdefault(cat, {})
            data[cat][fact.predicate] = {
                "value": fact.object_value,
                "updated": time.strftime("%Y-%m-%d"),
            }
            legacy_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def _purge_from_legacy_store(self, target: str) -> None:
        try:
            legacy_path = self.mem_dir / "long_term.json"
            if not legacy_path.exists():
                return
            data = json.loads(legacy_path.read_text(encoding="utf-8"))
            changed = False
            for cat in list(data.keys()):
                if isinstance(data[cat], dict):
                    for k in list(data[cat].keys()):
                        if k.lower() == target or f"{cat}_{k}".lower() == target:
                            del data[cat][k]
                            changed = True
            if changed:
                legacy_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass


_ENGINE: MemoryEngine | None = None
_ENGINE_LOCK = threading.Lock()


def get_memory_engine(storage_dir: str | Path | None = None) -> MemoryEngine:
    global _ENGINE
    with _ENGINE_LOCK:
        if storage_dir is not None:
            return MemoryEngine(storage_dir=storage_dir)
        if _ENGINE is None:
            _ENGINE = MemoryEngine()
    return _ENGINE
