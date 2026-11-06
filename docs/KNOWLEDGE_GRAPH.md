# AMATYA Phase 13.6 — Personal Knowledge Graph Specification
## Entity Modeling, Multi-Hop Traversal, Contradiction Detection & Provenance

**Version:** 13.6.0  
**Implementation:** `core/knowledge_graph.py`  
**Persistence:** `memory/knowledge_graph.json`  
**Target Architecture:** Relational knowledge graph connecting projects, devices, documents, people, and engineering concepts.

---

## 1. Overview and Topology

The Personal Knowledge Graph transforms AMATYA from a disconnected collection of semantic text chunks into an interconnected relational intelligence mesh:

```
                  ┌──────────────────────┐
                  │ Project: Mark-LVI    │
                  └──────────┬───────────┘
                             │
            ┌────────────────┴────────────────┐
            │ [IMPLEMENTS]                    │ [USES]
            ▼                                 ▼
┌──────────────────────┐           ┌──────────────────────┐
│ Concept: Phase 13    │           │ Device: Android Phone │
└──────────┬───────────┘           └──────────────────────┘
           │
           │ [REFERENCES]
           ▼
┌──────────────────────────────┐
│ Document: PHASE_13_ARCH.md   │
└──────────────────────────────┘
```

---

## 2. Strongly-Typed Entity & Relationship Schema

### Entity Types (`EntityType`)
- `PROJECT`, `PERSON`, `ORGANIZATION`, `DEVICE`, `APPLICATION`, `DOCUMENT`, `CONCEPT`, `COMPONENT`, `EVENT`, `TASK`, `REPOSITORY`, `LOCATION`.

### Relationship Predicates (`RelationType`)
- `BELONGS_TO`, `DEPENDS_ON`, `CREATED_BY`, `REFERENCES`, `DERIVED_FROM`, `RELATED_TO`, `SUPERSEDES`, `CONTRADICTS`, `IMPLEMENTS`, `USED_IN`, `CONNECTED_TO`, `REPLACES`.

---

## 3. Key Capabilities

1. **Multi-Hop Traversal (`traverse_multi_hop`):** Breadth-first relational path exploration finding connections up to $N$ hops away (e.g. `Mark-LVI -[IMPLEMENTS]-> Phase 13 -[REFERENCES]-> Architecture Doc`).
2. **Contradiction Detection (`detect_contradictions`):** Surfaces conflicting statements or opposing edges (`CONTRADICTS`).
3. **Deletion Cascading (`propagate_deletion`):** Removes an entity and purges all attached directional edges, ensuring no orphaned relations survive.
4. **Confidence & Inferences:** Relationships carry explicit confidence ratings (0.0 to 1.0) and flag `is_inferred: bool`, preventing assumptions from masquerading as verified facts.

---

## 4. API Usage

```python
from core.knowledge_graph import get_knowledge_graph, EntityType, RelationType

kg = get_knowledge_graph()

# Add entities
p_node = kg.add_entity("Mark-LVI", EntityType.PROJECT)
d_node = kg.add_entity("Android Phone", EntityType.DEVICE)

# Link relationship
kg.add_relationship(p_node.entity_id, RelationType.CONNECTED_TO, d_node.entity_id, confidence=1.0)

# Multi-hop query
connections = kg.traverse_multi_hop(p_node.entity_id, max_hops=2)
for conn in connections:
    print(f"Connected: {conn['target_name']} via {conn['path_trace']}")
```
