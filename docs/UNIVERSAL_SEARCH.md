# AMATYA Phase 13.7 — Universal Semantic Search Specification
## Hybrid Lexical, Vector & Knowledge Graph Fusion with Reciprocal Rank Normalization

**Version:** 13.7.0  
**Implementation:** `core/universal_search.py`  
**Target Architecture:** Multi-modal query retrieval combining inverted lexical indexes, 128-D vector embeddings, and relational graph paths.

---

## 1. Overview and Hybrid Architecture

Universal Semantic Search unifies all retrieval modalities into a cohesive rank-fusion engine:

```
                          ┌───────────────────────────┐
                          │     User Query String     │
                          └─────────────┬─────────────┘
                                        │
         ┌──────────────────────────────┼──────────────────────────────┐
         │                              │                              │
┌────────▼────────┐            ┌────────▼────────┐            ┌────────▼────────┐
│ Lexical BM25    │            │ 128-D Vector    │            │ Knowledge Graph │
│ Term Matching   │            │ Cosine Sim      │            │ Relational Hops │
└────────┬────────┘            └────────┬────────┘            └────────┬────────┘
         │                              │                              │
         └──────────────────────────────┼──────────────────────────────┘
                                        │
                         ┌──────────────▼─────────────┐
                         │ Reciprocal Rank Fusion     │
                         │ & Deduplication Pipeline   │
                         └──────────────┬─────────────┘
                                        │
                         ┌──────────────▼─────────────┐
                         │ Evidence-Grounded Results  │
                         │ with Verifiable Citations  │
                         └────────────────────────────┘
```

---

## 2. API Usage

```python
from core.universal_search import get_search_engine

engine = get_search_engine()
results = engine.search("Mark-LVI voltage regulation architecture", top_k=5)

for r in results:
    print(f"[{r.score:.2f}] ({r.retrieval_method}) {r.source_title}: {r.snippet[:100]}...")
```
