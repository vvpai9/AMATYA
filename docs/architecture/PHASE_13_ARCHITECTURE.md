# AMATYA Phase 13 Architecture Specification
## Multimodal Intelligence, Knowledge Graph & Universal Information Understanding

**Version:** 13.0.0  
**Target Environment:** Linux (KDE Plasma 6 Wayland, PipeWire 1.6, Python 3.12)  
**Host Profile:** Intel Core i5-11300H (8 threads / 4 cores), 16 GB RAM, NVIDIA GeForce GTX 1650 Mobile (4 GB VRAM)  
**Upstream Lineage:** Built upon [FatihMakes/Mark-LVII](https://github.com/FatihMakes/Mark-LVII) with Wayland desktop automation, cross-platform phone ring/telemetry, and layered cognitive architecture.

---

## 1. Phase 12 Implementation Verification

A comprehensive audit of the repository establishes that Phase 12 capabilities are operational and verified across the test baseline:

- **Layered Persistent Memory (`core/memory_engine.py`):**
  - Working memory scratchpad (`working_memory.json`).
  - Chronological episodic memory (`episodic_memory.json`).
  - Semantic knowledge base (`semantic_memory.json`) with provenance tags (`user_stated`, `observed`, `inferred`, `system`) and confidence metrics (0.0 to 1.0).
  - Procedural memory (`procedural_memory.json`) for automation routines.
  - Contradiction detection preventing silent overwriting of established facts.
  - Full purge, export, and user toggle support.
- **Contextual Intelligence (`core/context_manager.py`):**
  - Pronoun and implicit reference resolution (`resolve_references`).
  - Active application and window tracking.
  - Ambiguity detection flagging missing context without hallucination.
- **Central Orchestrator (`core/orchestrator.py`):**
  - Autonomous multi-step task planning with dependency graph resolution.
  - Step checkpoints and dynamic replanning on intermediate failure.
  - Fixed model router integration passing structured `config` with `system_instruction`.
- **Proactive Intelligence & Background Automation (`core/proactive_engine.py`, `actions/background_monitor.py`):**
  - 5-tier priority evaluation, quiet-hours suppression, and non-intrusive notification.
- **Device & Cross-Platform Integrations (`core/device_manager.py`, `core/phone_ring.py`, `core/whatsapp.py`):**
  - Dynamic local subnet discovery via `nmap -sn -T4`, IPv6 neighbor mapping, and Tailscale peer mesh.
  - Cross-platform phone alert engine supporting AgentRing VoIP, KDE Connect, and Ntfy.sh.
  - WhatsApp messaging and document delivery.
- **Test Baseline:** Full suite of 54 acceptance tests passing cleanly in under 30 seconds.

---

## 2. Current Information-Processing Architecture

Prior to Phase 13, AMATYA possessed fragmented information capabilities:

```
  Existing File Inputs
  ├── actions/file_processor.py   ──► Format-specific operations (PDF, DOCX, CSV, Image, Audio)
  ├── core/rag.py                 ──► Local hybrid RAG (128-D embedding + lexical search)
  ├── core/vision.py              ──► KWin screenshot capture + Gemini vision analysis
  ├── core/doc_generator.py       ──► CREATOR document, markdown, and PPTX generator
  └── core/jyotisha.py            ──► Ephemeris computations and SVG/PNG Kundali rendering
```

### Limitations of the Pre-Phase 13 Baseline:
1. **Siloed Ingestion:** Each action independently parsed files without shared metadata, content normalization, or centralized status tracking.
2. **Missing Knowledge Graph:** Entities discovered in documents, screens, or conversations were stored as flat key-value pairs or text chunks, losing relational topology (e.g., *Person X works on Project Y using Library Z*).
3. **No Incremental Ingestion:** Ingesting directories required rescanning and re-reading files, wasting compute and I/O.
4. **Lack of Uniform Provenance:** Chunks did not consistently maintain cryptographic hashes, extractor names, or processing confidence.

---

## 3. Existing Functionality Reuse Matrix

| Subsystem / Module | Existing Capability | Phase 13 Integration Strategy |
|---|---|---|
| `core/rag.py` | 128-D cosine embedding & lexical search | Upgrade to consume unified chunks from `core/ingestion.py`. |
| `actions/file_processor.py` | Individual format readers (PDF, DOCX, XLSX, etc.) | Abstract extraction logic into modular extractors within `core/ingestion.py`. |
| `core/vision.py` | Wayland screenshot capture & multimodal inspection | Ground visual elements into ingestion pipelines for screenshots and diagrams. |
| `core/memory_engine.py` | Semantic fact store & contradiction checker | Connect as the persistent storage layer for Knowledge Graph nodes & edges. |
| `core/security.py` | Secret redaction (`redact_secrets`) & path verification | Enforce at the ingestion boundary before any content is parsed or indexed. |
| `core/model_router.py` | Tiered model execution (Fast, Smart, Reasoning) | Route multimodal extraction tasks according to privacy and modality constraints. |

---

## 4. Multimodal Model Capability Assessment

AMATYA operates in a hybrid edge-cloud environment:
- **Cloud Modality (Gemini 2.5 Flash / Pro):**
  - High-precision document OCR, complex technical diagram understanding, multimodal reasoning over images and audio.
  - Used strictly when `allow_cloud=True` and content is unredacted/non-restricted.
- **Local Modality (Edge CPU/GPU):**
  - Text & Code: Regex tokenization, BM25 term weighting, 128-D lightweight embedding generation.
  - Image/Video: OpenCV (`cv2`) for resolution, frame sampling, perceptual hashing (`pHash`), aspect ratio, and metadata.
  - Audio: Wave header inspection, `ffprobe` stream metadata, duration, channels, sample rate.
  - Documents: Native local parsing via `pdfplumber`, `python-docx`, `python-pptx`, `openpyxl`, and `beautifulsoup4`.
- **Capability Boundaries:**
  - If external network or cloud keys are unavailable, AMATYA gracefully falls back to local structured extraction and keyword indexing, marking extraction confidence accordingly.
  - Sensitive files (credentials, private keys, financial records) are locked to local-only processing.

---

## 5. Proposed Universal Ingestion Architecture

```
                    ┌────────────────────────────┐
                    │ Raw Source (File, URL, Text)│
                    └─────────────┬──────────────┘
                                  │
                    ┌─────────────▼──────────────┐
                    │ 1. Source Validation       │
                    │    - Directory permissions │
                    │    - Path traversal check  │
                    │    - Size limits           │
                    └─────────────┬──────────────┘
                                  │
                    ┌─────────────▼──────────────┐
                    │ 2. Modality & Type Detect  │
                    │    - Magic bytes signature │
                    │    - MIME type & suffix    │
                    │    - Modality classification│
                    └─────────────┬──────────────┘
                                  │
                    ┌─────────────▼──────────────┐
                    │ 3. Security Boundary       │
                    │    - Secret redaction      │
                    │    - Cloud policy check    │
                    │    - Untrusted data tagging │
                    └─────────────┬──────────────┘
                                  │
                    ┌─────────────▼──────────────┐
                    │ 4. Modular Extraction      │
                    │    - DocumentExtractor     │
                    │    - ImageExtractor        │
                    │    - AudioExtractor        │
                    │    - CodeExtractor         │
                    │    - WebExtractor          │
                    └─────────────┬──────────────┘
                                  │
                    ┌─────────────▼──────────────┐
                    │ 5. Normalization & Chunk   │
                    │    - Structural chunking   │
                    │    - Token approximation   │
                    │    - Context preservation  │
                    └─────────────┬──────────────┘
                                  │
         ┌────────────────────────┴────────────────────────┐
         │                                                 │
┌────────▼─────────────────┐                    ┌──────────▼────────────────┐
│ 6. Ingestion Registry    │                    │ 7. RAG & Knowledge Index  │
│    - SHA256 checksum     │                    │    - Lexical + Embeddings │
│    - Provenance record   │                    │    - Entity Extraction    │
│    - Modification state  │                    │    - Knowledge Graph Edges│
└──────────────────────────┘                    └───────────────────────────┘
```

---

## 6. Proposed Knowledge Graph Schema

The Knowledge Graph represents interconnected entities extracted across multimodal sources:

### Entities (`Node`)
- `id`: Deterministic hash (`sha256(canonical_name + type)`).
- `name`: Human-readable label (e.g., "AMATYA", "Project Mark-LVII", "Mobile Device").
- `entity_type`: `PERSON`, `PROJECT`, `DEVICE`, `ORGANIZATION`, `CONCEPT`, `TECHNOLOGY`, `FILE`, `LOCATION`, `EVENT`.
- `attributes`: Key-value properties (e.g., `ip_address`, `file_type`, `version`).
- `provenance`: `[source_id, timestamp, confidence]`.
- `created_at` / `updated_at`: Epoch timestamps.

### Relationships (`Edge`)
- `id`: `sha256(source_id + predicate + target_id)`.
- `source_id`: Origin entity ID.
- `predicate`: Normalized relationship verb (e.g., `OWNS`, `USES`, `DEPENDS_ON`, `CREATED_BY`, `LOCATED_AT`, `PART_OF`).
- `target_id`: Destination entity ID.
- `weight` / `confidence`: Float between 0.0 and 1.0.
- `bidirectional`: Boolean.
- `provenance`: Source citation and observation context.

---

## 7. Storage and Indexing Strategy

- **Ingestion Registry (`memory/ingestion_index.json`):**
  - Atomic JSON store protected by file-level locking (`threading.RLock`).
  - Maps `source_id` -> `SourceRecord` (path, hash, mtime, size, modality, status, chunk_count, provenance).
  - Fast fingerprinting: `(mtime, size_bytes)` allows $O(1)$ skipping of unchanged files during recursive directory syncs.
- **RAG Store (`memory/knowledge_index.json`):**
  - Inverted index for lexical search with BM25 term weighting.
  - Normalized 128-D vector embeddings for semantic similarity.
  - Source-level chunk filtering: allows atomic purging of all chunks belonging to a deleted file.
- **Knowledge Graph Store (`memory/knowledge_graph.json`):**
  - Adjacency list storing nodes and directed edges with queryable multi-hop traversal.

---

## 8. Security and Privacy Assessment

1. **Untrusted Content Sandboxing:**
   - Content extracted from PDFs, web pages, or images is treated as untrusted data.
   - Text is wrapped in defensive boundaries (`<UNTRUSTED_INGESTED_CONTENT>`) to prevent prompt-injection attacks.
2. **Secret Redaction:**
   - All extracted text passes through `core.security.redact_secrets` before persisting or indexing.
   - Credentials (API keys, private keys, passwords) are scrubbed.
3. **Cloud Processing Boundaries:**
   - Sources are tagged with `allow_cloud: bool`. If disabled, data is never transmitted to remote models.
4. **Deletion Consistency:**
   - Deleting a source removes its record from `ingestion_index.json`, purges its chunks from `knowledge_index.json`, and prunes associated edges from `knowledge_graph.json`.

---

## 9. Hardware and Performance Assessment

- **Host Profile:**
  - Intel Core i5-11300H (4 Cores / 8 Threads, up to 4.4 GHz Turbo).
  - 16 GB DDR4 RAM.
  - NVIDIA GeForce GTX 1650 Mobile (4 GB GDDR6).
- **Resource Constraints & Mitigations:**
  - **Memory:** Chunk batches during directory ingestion; avoid loading full multi-gigabyte files into RAM simultaneously.
  - **CPU:** Parallelize extraction across worker threads for multi-file batches (`ThreadPoolExecutor`).
  - **Disk I/O:** Stat cache checking `mtime` and `size` before calculating SHA256 hashes.

---

## 10. Phase 13 Implementation Roadmap

- **Phase 13.1 — Repository Audit & Architecture (Complete):**
  - Validated Phase 12 stability, test baselines, hardware profile, and architectural design.
- **Phase 13.2 — Universal Ingestion Framework (Current Target):**
  - Universal `IngestionSource` abstraction, modality detection, multi-format extraction pipeline, metadata/provenance tracking, and incremental sync.
- **Phase 13.3 — Advanced Document Intelligence:**
  - Structural heading parsing, table extraction, and page-aware indexing.
- **Phase 13.4 — Visual Intelligence:**
  - Screen understanding, technical schematics, and OCR integration.
- **Phase 13.5 — Audio and Video Intelligence:**
  - Audio transcription, scene segmentation, and timestamped retrieval.
- **Phase 13.6 — Knowledge Graph:**
  - Entity-relationship extraction, multi-hop reasoning, and graph persistence.
- **Phase 13.7 — Universal Search:**
  - Unified multimodal query engine combining lexical, semantic, and graph search.
- **Phase 13.8 — Research Intelligence:**
  - Evidence-grounded synthesis, source citation, and contradiction resolution.
- **Phase 13.9 — CREATOR Integration:**
  - Knowledge spaces powering autonomous presentation, document, and code generation.
- **Phase 13.10 — Live Information and Monitoring:**
  - Dynamic file watch, network status tracking, and proactive event reporting.
- **Phase 13.11 — Unified Knowledge Interface:**
  - Centralized GUI dashboard and voice command center.
- **Phase 13.12 — Production Hardening:**
  - End-to-end acceptance suite, stress testing, and security verification.

