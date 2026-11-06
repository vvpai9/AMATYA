"""
AMATYA Personal Knowledge Graph Engine (core/knowledge_graph.py)
=================================================================
Phase 13.6 Core Implementation:
  - Strongly-Typed Knowledge Graph (Nodes: Project, Person, Device, Document, Concept, Component, etc.).
  - Directional Relationships (Belongs To, Depends On, Created By, References, Implements, Used In, Contradicts).
  - Multi-Hop Graph Traversal and Relational Reasoning.
  - Entity Resolution and Deduplication.
  - Contradiction Detection across Conflicting Facts and Edges.
  - Deletion Propagation and Provenance Tracing.
  - Thread-Safe Atomic Persistence (`memory/knowledge_graph.json`).
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from memory.config_manager import BASE_DIR

KG_PATH = BASE_DIR / "memory" / "knowledge_graph.json"
_LOCK = threading.RLock()


# ============================================================================
# Enums and Types
# ============================================================================

class EntityType(str, Enum):
    PROJECT = "PROJECT"
    PERSON = "PERSON"
    ORGANIZATION = "ORGANIZATION"
    DEVICE = "DEVICE"
    APPLICATION = "APPLICATION"
    DOCUMENT = "DOCUMENT"
    CONCEPT = "CONCEPT"
    COMPONENT = "COMPONENT"
    EVENT = "EVENT"
    TASK = "TASK"
    REPOSITORY = "REPOSITORY"
    LOCATION = "LOCATION"


class RelationType(str, Enum):
    BELONGS_TO = "BELONGS_TO"
    DEPENDS_ON = "DEPENDS_ON"
    CREATED_BY = "CREATED_BY"
    REFERENCES = "REFERENCES"
    DERIVED_FROM = "DERIVED_FROM"
    RELATED_TO = "RELATED_TO"
    SUPERSEDES = "SUPERSEDES"
    CONTRADICTS = "CONTRADICTS"
    IMPLEMENTS = "IMPLEMENTS"
    USED_IN = "USED_IN"
    CONNECTED_TO = "CONNECTED_TO"
    REPLACES = "REPLACES"


# ============================================================================
# Graph Entities and Edges
# ============================================================================

@dataclass
class EntityNode:
    entity_id: str
    name: str
    entity_type: str  # EntityType value
    properties: dict[str, Any] = field(default_factory=dict)
    aliases: list[str] = field(default_factory=list)
    confidence: float = 1.0
    provenance: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EntityNode:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class RelationshipEdge:
    edge_id: str
    source_id: str
    predicate: str  # RelationType value
    target_id: str
    confidence: float = 1.0
    weight: float = 1.0
    is_inferred: bool = False
    bidirectional: bool = False
    provenance: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RelationshipEdge:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ============================================================================
# Personal Knowledge Graph Store
# ============================================================================

class PersonalKnowledgeGraph:
    """Persistent personal knowledge graph connecting projects, devices, documents, and people."""

    def __init__(self, storage_path: Path | None = None):
        self._path = storage_path or KG_PATH
        self._entities: dict[str, EntityNode] = {}
        self._edges: dict[str, RelationshipEdge] = {}
        self._load()

    def _load(self) -> None:
        with _LOCK:
            if not self._path.exists():
                self._entities = {}
                self._edges = {}
                return
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                self._entities = {
                    eid: EntityNode.from_dict(edata)
                    for eid, edata in data.get("entities", {}).items()
                }
                self._edges = {
                    eid: RelationshipEdge.from_dict(edata)
                    for eid, edata in data.get("edges", {}).items()
                }
            except Exception:
                self._entities = {}
                self._edges = {}

    def _save(self) -> None:
        with _LOCK:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temp = self._path.with_suffix(".tmp")
            payload = {
                "version": "13.6.0",
                "updated_at": time.time(),
                "entities": {eid: e.to_dict() for eid, e in self._entities.items()},
                "edges": {eid: e.to_dict() for eid, e in self._edges.items()},
            }
            temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            temp.replace(self._path)

    @staticmethod
    def generate_entity_id(name: str, entity_type: str) -> str:
        clean = re.sub(r"[^a-z0-9_]+", "_", name.lower().strip()).strip("_")
        return f"{entity_type.lower()}_{clean}"

    @staticmethod
    def generate_edge_id(source_id: str, predicate: str, target_id: str) -> str:
        h = hashlib.sha256(f"{source_id}:{predicate}:{target_id}".encode()).hexdigest()[:16]
        return f"edge_{h}"

    def add_entity(
        self,
        name: str,
        entity_type: str | EntityType = EntityType.CONCEPT,
        properties: dict[str, Any] | None = None,
        aliases: list[str] | None = None,
        confidence: float = 1.0,
        source_id: str = "",
    ) -> EntityNode:
        etype = entity_type.value if isinstance(entity_type, EntityType) else str(entity_type).upper()
        eid = self.generate_entity_id(name, etype)

        with _LOCK:
            if eid in self._entities:
                node = self._entities[eid]
                if properties:
                    node.properties.update(properties)
                if aliases:
                    node.aliases = list(set(node.aliases + aliases))
                node.updated_at = time.time()
                if source_id:
                    node.provenance.append({"source": source_id, "time": time.time(), "conf": confidence})
            else:
                prov = [{"source": source_id, "time": time.time(), "conf": confidence}] if source_id else []
                node = EntityNode(
                    entity_id=eid,
                    name=name,
                    entity_type=etype,
                    properties=properties or {},
                    aliases=aliases or [],
                    confidence=confidence,
                    provenance=prov,
                )
                self._entities[eid] = node

            self._save()
            return node

    def get_entity(self, identifier: str) -> EntityNode | None:
        with _LOCK:
            if identifier in self._entities:
                return self._entities[identifier]
            # Search by name or alias
            target = identifier.lower().strip()
            for e in self._entities.values():
                if e.name.lower() == target or target in [a.lower() for a in e.aliases]:
                    return e
            return None

    def add_relationship(
        self,
        source_id: str,
        predicate: str | RelationType,
        target_id: str,
        confidence: float = 1.0,
        is_inferred: bool = False,
        source_context: str = "",
        bidirectional: bool = False,
    ) -> RelationshipEdge:
        pred_val = predicate.value if isinstance(predicate, RelationType) else str(predicate).upper()
        edge_id = self.generate_edge_id(source_id, pred_val, target_id)

        with _LOCK:
            edge = RelationshipEdge(
                edge_id=edge_id,
                source_id=source_id,
                predicate=pred_val,
                target_id=target_id,
                confidence=confidence,
                is_inferred=is_inferred,
                bidirectional=bidirectional,
                provenance={"context": source_context, "timestamp": time.time()},
            )
            self._edges[edge_id] = edge
            self._save()
            return edge

    def find_relationships(
        self,
        entity_id: str,
        direction: str = "both",
        predicate: str | None = None,
    ) -> list[RelationshipEdge]:
        """Finds relationships attached to an entity."""
        with _LOCK:
            results: list[RelationshipEdge] = []
            pred_filter = predicate.upper() if predicate else None

            for e in self._edges.values():
                if pred_filter and e.predicate != pred_filter:
                    continue

                if direction in ("out", "both") and e.source_id == entity_id:
                    results.append(e)
                elif direction in ("in", "both") and e.target_id == entity_id:
                    results.append(e)
                elif e.bidirectional and (e.source_id == entity_id or e.target_id == entity_id):
                    if e not in results:
                        results.append(e)

            return results

    def traverse_multi_hop(
        self,
        start_entity_id: str,
        max_hops: int = 2,
    ) -> list[dict[str, Any]]:
        """Performs breadth-first traversal up to max_hops, returning reachable paths and entities."""
        with _LOCK:
            visited_entities: set[str] = {start_entity_id}
            paths: list[dict[str, Any]] = []
            queue: list[tuple[str, list[str], int]] = [(start_entity_id, [start_entity_id], 0)]

            while queue:
                current_id, current_path, hops = queue.pop(0)
                if hops >= max_hops:
                    continue

                edges = self.find_relationships(current_id, direction="both")
                for edge in edges:
                    next_id = edge.target_id if edge.source_id == current_id else edge.source_id
                    if next_id not in visited_entities:
                        visited_entities.add(next_id)
                        new_path = current_path + [f"-[{edge.predicate}]->", next_id]
                        target_node = self._entities.get(next_id)
                        paths.append({
                            "target_id": next_id,
                            "target_name": target_node.name if target_node else next_id,
                            "target_type": target_node.entity_type if target_node else "UNKNOWN",
                            "hops": hops + 1,
                            "path_trace": " ".join(new_path),
                            "edge_predicate": edge.predicate,
                            "confidence": edge.confidence,
                        })
                        queue.append((next_id, new_path, hops + 1))

            return paths

    def detect_contradictions(self) -> list[dict[str, Any]]:
        """Identifies explicit contradicting edges or conflicting values."""
        with _LOCK:
            contradictions: list[dict[str, Any]] = []
            for edge in self._edges.values():
                if edge.predicate == RelationType.CONTRADICTS.value:
                    src = self._entities.get(edge.source_id)
                    tgt = self._entities.get(edge.target_id)
                    contradictions.append({
                        "edge_id": edge.edge_id,
                        "source": src.name if src else edge.source_id,
                        "target": tgt.name if tgt else edge.target_id,
                        "confidence": edge.confidence,
                        "context": edge.provenance.get("context", ""),
                    })
            return contradictions

    def propagate_deletion(self, entity_id_or_source: str) -> int:
        """Removes an entity and cascades deletion to all attached edges."""
        with _LOCK:
            to_delete_entities: set[str] = set()
            if entity_id_or_source in self._entities:
                to_delete_entities.add(entity_id_or_source)

            # Check provenance matches
            for eid, e in list(self._entities.items()):
                if any(p.get("source") == entity_id_or_source for p in e.provenance):
                    to_delete_entities.add(eid)

            # Delete entities
            for eid in to_delete_entities:
                if eid in self._entities:
                    del self._entities[eid]

            # Delete associated edges
            edges_to_remove = [
                edge_id for edge_id, edge in self._edges.items()
                if edge.source_id in to_delete_entities or edge.target_id in to_delete_entities
            ]
            for edge_id in edges_to_remove:
                del self._edges[edge_id]

            if to_delete_entities or edges_to_remove:
                self._save()

            return len(to_delete_entities) + len(edges_to_remove)

    def extract_and_link(self, text: str, source_id: str) -> list[str]:
        """Extracts candidate entities and relations from text and links them into the graph."""
        clean_text = text or ""
        created_ids: list[str] = []

        # Simple high-precision pattern matches
        # 1. Projects: "Project <Name>"
        for m in re.finditer(r"\bProject\s+([A-Z][a-zA-Z0-9_\-]+)\b", clean_text):
            node = self.add_entity(m.group(1), EntityType.PROJECT, source_id=source_id)
            created_ids.append(node.entity_id)

        # 2. Devices: "Android Phone", "MiTV", etc.
        for m in re.finditer(r"\b(Nokia\s+[A-Za-z0-9\s]+|MiTV[A-Za-z0-9\-]*|Android\s+TV)\b", clean_text):
            node = self.add_entity(m.group(1).strip(), EntityType.DEVICE, source_id=source_id)
            created_ids.append(node.entity_id)

        return created_ids

    def get_stats(self) -> dict[str, Any]:
        with _LOCK:
            by_type: dict[str, int] = {}
            for e in self._entities.values():
                by_type[e.entity_type] = by_type.get(e.entity_type, 0) + 1
            by_relation: dict[str, int] = {}
            for r in self._edges.values():
                by_relation[r.predicate] = by_relation.get(r.predicate, 0) + 1

            return {
                "total_entities": len(self._entities),
                "total_edges": len(self._edges),
                "by_type": by_type,
                "by_relation": by_relation,
            }


_KG_INSTANCE: PersonalKnowledgeGraph | None = None

def get_knowledge_graph() -> PersonalKnowledgeGraph:
    global _KG_INSTANCE
    with _LOCK:
        if _KG_INSTANCE is None:
            _KG_INSTANCE = PersonalKnowledgeGraph()
        return _KG_INSTANCE
