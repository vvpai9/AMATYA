# AMATYA Phase 13.8 — Source-Grounded Research Engine Specification
## Structured Investigation, Primary Evidence Extraction & Citation Integrity

**Version:** 13.8.0  
**Implementation:** `core/research_engine.py`  
**Target Architecture:** Evidence-grounded research workflow with zero hallucinated sources.

---

## 1. Overview and Core Workflow

The Research Intelligence Engine executes multi-step investigation plans:

```
  User Research Query
          │
          ▼
  1. Research Planning ────────► Deconstructs topic into core search vectors
          │
          ▼
  2. Source Discovery  ────────► Queries Hybrid Search (Lexical + Vector + Graph)
          │
          ▼
  3. Evidence Extraction ──────► Isolates raw factual excerpts from primary sources
          │
          ▼
  4. Contradiction Audit ──────► Evaluates discrepancies across sources
          │
          ▼
  5. Synthesis & Report ───────► Produces structured Markdown report with citations
```

---

## 2. API Usage

```python
from core.research_engine import get_research_engine

researcher = get_research_engine()
report = researcher.conduct_research("Phase 13 Universal Ingestion architecture", max_sources=3)

print("Topic:", report.topic)
print("Conclusions:", len(report.conclusions))
print("Citations:", [c.citation_id for c in report.evidence])
print(report.to_markdown())
```
