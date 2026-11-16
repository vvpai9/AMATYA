# AMATYA Phase 13 — Data Governance, Security & Privacy Specification
## Source Permissions, Secret Redaction, Untrusted Content Sandboxing & Deletion Propagation

**Version:** 13.0.0  
**Scope:** Universal Multimodal Ingestion, Document Intelligence, Knowledge Graph & Search  
**Target Environment:** Local Edge-First Autonomous Companion

---

## 1. Core Security & Privacy Principles

1. **Untrusted Ingested Content:**
   - All retrieved documents, web articles, OCR text, and transcripts are strictly treated as untrusted data.
   - Text is sanitized against prompt injection patterns (`<system>`, `<user>`, `<instruction>`, etc.).
   - Model outputs separate retrieved quotes from synthetic reasoning.
2. **Secret Redaction at Ingestion Boundary:**
   - All text streams pass through `core.security.redact_secrets` before chunking, embedding, indexing, or saving.
   - High-entropy tokens, API keys (e.g. Gemini `API_KEY_PATTERN...`, AWS keys, SSH private keys) are scrubbed and replaced with safe tokens.
3. **SSRF Guard:**
   - Web extraction strictly forbids resolution to RFC 1918 private subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), loopbacks (`127.0.0.1`), link-local (`169.254.0.0/16`), and multicast addresses.
4. **Local vs Cloud Boundary:**
   - Sources carry explicit `allow_cloud: bool` flags. When disabled, content never touches remote vision or text endpoints.
5. **Cascading Deletion:**
   - Removing a source triggers atomic deletion across `ingestion_index.json`, `knowledge_index.json` (RAG chunks), and `knowledge_graph.json` (entity nodes & relational edges).
