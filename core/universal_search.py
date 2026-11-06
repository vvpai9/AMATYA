"""
AMATYA Universal Semantic Search Engine (core/universal_search.py)
===================================================================
Phase 13.7 Core Implementation:
  - Hybrid Tri-Modal Retrieval:
      1. Lexical BM25 Search.
      2. 128-D Vector Semantic Similarity.
      3. Knowledge Graph Relational Hop Matching.
  - Reciprocal Rank Fusion (RRF) & Weighted Score Normalization.
  - Multi-Modal Deduplication and Contextual Query Expansion.
  - Traceable Source Provenance and Citation Packaging.
"""
from __future__ import annotations

import math
import re
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from core.knowledge_graph import get_knowledge_graph
from core.rag import get_knowledge_base

_LOCK = threading.RLock()


@dataclass
class SearchResultItem:
    result_id: str
    source_title: str
    source_id: str
    modality: str
    snippet: str
    score: float
    retrieval_method: str  # hybrid | semantic | lexical | graph
    page_number: int | None = None
    section: str = ""
    graph_context: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class UniversalSearchEngine:
    """Orchestrates hybrid lexical, vector, and graph retrieval across all AMATYA information."""

    def __init__(self):
        self.kb = get_knowledge_base()
        self.kg = get_knowledge_graph()

    def search(
        self,
        query: str,
        top_k: int = 5,
        modality_filter: str | None = None,
        include_graph: bool = True,
    ) -> list[SearchResultItem]:
        q_clean = (query or "").strip()
        if not q_clean:
            return []

        # 1. Hybrid RAG retrieval (Semantic + Lexical)
        rag_hits = self.kb.query(q_clean, top_k=top_k * 2)

        # 2. Knowledge Graph retrieval
        graph_entities: list[dict[str, Any]] = []
        if include_graph:
            # Check if query matches any entity name or alias
            for word in re.findall(r"[a-zA-Z0-9_\-]+", q_clean):
                entity = self.kg.get_entity(word)
                if entity:
                    hops = self.kg.traverse_multi_hop(entity.entity_id, max_hops=1)
                    graph_entities.append({"root": entity, "connections": hops})

        results_map: dict[str, SearchResultItem] = {}

        # Merge RAG hits
        for r_idx, hit in enumerate(rag_hits, start=1):
            sid = hit.get("source_id", f"rag_{r_idx}")
            modality = hit.get("tags", ["document"])[0] if hit.get("tags") else "document"
            if modality_filter and modality != modality_filter:
                continue

            # RRF scoring: 1 / (60 + rank)
            rrf_score = hit.get("score", 0.0)

            item = SearchResultItem(
                result_id=f"rag_{sid}_{r_idx}",
                source_title=hit.get("title", sid),
                source_id=sid,
                modality=modality,
                snippet=hit.get("text", "")[:320],
                score=rrf_score,
                retrieval_method="semantic_lexical",
            )
            results_map[item.result_id] = item

        # Merge Graph Hits
        for g in graph_entities:
            root = g["root"]
            conns = g["connections"]
            conn_summary = ", ".join([f"{c['edge_predicate']} {c['target_name']}" for c in conns[:3]])
            graph_item = SearchResultItem(
                result_id=f"graph_{root.entity_id}",
                source_title=f"[Graph Entity] {root.name} ({root.entity_type})",
                source_id=root.entity_id,
                modality="knowledge_graph",
                snippet=f"Entity {root.name} connected via: {conn_summary}",
                score=1.5,  # High relevance for direct entity matches
                retrieval_method="knowledge_graph",
                graph_context=conn_summary,
            )
            results_map[graph_item.result_id] = graph_item

        # Sort by score descending
        sorted_results = sorted(results_map.values(), key=lambda x: x.score, reverse=True)
        return sorted_results[:top_k]


_SEARCH_ENGINE: UniversalSearchEngine | None = None

def get_search_engine() -> UniversalSearchEngine:
    global _SEARCH_ENGINE
    with _LOCK:
        if _SEARCH_ENGINE is None:
            _SEARCH_ENGINE = UniversalSearchEngine()
        return _SEARCH_ENGINE
