# AMATYA Phase 13.2 — Universal Ingestion Framework Specification
## Multimodal Ingestion, Extraction Pipeline, Provenance & Incremental Synchronization

**Version:** 13.2.0  
**Implementation:** `core/ingestion.py`  
**Tool Action:** `actions/knowledge_base.py` (Actions: `ingest`, `ingestion_status`, `sync_incremental`)  
**Target Architecture:** Multi-format universal ingestion across documents, technical code, media, web URLs, and memory notes.

---

## 1. Overview and Architecture

The Universal Ingestion Framework (`core/ingestion.py`) provides an unified information-processing backbone for AMATYA. Rather than treating each file format or data source as an isolated ad-hoc task, the ingestion architecture establishes a common, reproducible, and verifiable lifecycle:

```
  ┌────────────────────────────────────────────────────────────────────────┐
  │                           Data Sources                                 │
  │    Local Files  │  Directories  │  Web URLs  │  Code Repos  │  Notes   │
  └───────────────────────────────────┬────────────────────────────────────┘
                                      │
                         ┌────────────▼───────────┐
                         │ 1. Security Governance │
                         │  - Path boundaries     │
                         │  - SSRF protection     │
                         │  - Secret redaction    │
                         └────────────┬───────────┘
                                      │
                         ┌────────────▼───────────┐
                         │ 2. Modality Detection  │
                         │  - Magic signatures    │
                         │  - MIME sniffer        │
                         │  - Content inspection  │
                         └────────────┬───────────┘
                                      │
                         ┌────────────▼───────────┐
                         │ 3. Extraction Pipeline │
                         │  - DocumentExtractor   │
                         │  - CodeExtractor       │
                         │  - MediaExtractor      │
                         │  - WebExtractor        │
                         └────────────┬───────────┘
                                      │
                         ┌────────────▼───────────┐
                         │ 4. Semantic Chunking   │
                         │  - Structural splits   │
                         │  - Untrusted tagging   │
                         │  - Token approximation │
                         └────────────┬───────────┘
                                      │
             ┌────────────────────────┴────────────────────────┐
             │                                                 │
┌────────────▼───────────┐                        ┌────────────▼───────────┐
│ 5. Ingestion Registry  │                        │ 6. Hybrid RAG Store    │
│  - SHA-256 Checksum    │                        │  - Semantic Embeddings │
│  - Full Provenance     │                        │  - Lexical Inverted Idx│
│  - Status & Recovery   │                        │  - Source Linking      │
└────────────────────────┘                        └────────────────────────┘
```

---

## 2. Modality and MIME Type Detection

Modality detection inspects binary file signatures first, falling back to extension and standard MIME detection:

| Modality | MIME Type | Magic Bytes / Header | Extensions |
|---|---|---|---|
| **DOCUMENT** | `application/pdf` | `%PDF-` | `.pdf` |
| **DOCUMENT** | `application/vnd.openxml...` | `PK\x03\x04` (Zip w/ `word/`) | `.docx` |
| **DOCUMENT** | `application/vnd.ms-powerpoint` | `PK\x03\x04` (Zip w/ `ppt/`) | `.pptx` |
| **DOCUMENT** | `text/markdown`, `text/plain` | Plaintext / UTF-8 | `.md`, `.txt`, `.rtf` |
| **DOCUMENT** | `text/html` | `<!DOCTYPE html`, `<html>` | `.html`, `.htm` |
| **DATA** | `application/vnd.openxml...` | `PK\x03\x04` (Zip w/ `xl/`) | `.xlsx` |
| **DATA** | `text/csv`, `text/tab...` | Tabular delimiter sniff | `.csv`, `.tsv` |
| **DATA** | `application/json` | JSON syntax | `.json` |
| **IMAGE** | `image/png` | `\x89PNG\r\n\x1a\n` | `.png` |
| **IMAGE** | `image/jpeg` | `\xff\xd8\xff` | `.jpg`, `.jpeg` |
| **IMAGE** | `image/webp` | `RIFF....WEBP` | `.webp` |
| **AUDIO** | `audio/wav` | `RIFF....WAVE` | `.wav` |
| **AUDIO** | `audio/mpeg` | `ID3` or `\xff\xfb` | `.mp3` |
| **AUDIO** | `audio/flac` | `fLaC` | `.flac` |
| **AUDIO** | `audio/ogg` | `OggS` | `.ogg` |
| **VIDEO** | `video/mp4` | `....ftyp` | `.mp4`, `.mov` |
| **VIDEO** | `video/webm` | `\x1a\x45\xdf\xa3` | `.webm`, `.mkv` |
| **CODE** | `text/x-python`, etc. | Language syntax | `.py`, `.js`, `.ts`, `.c`, `.cpp`, `.rs`, `.go`, `.sh`, `.sql` |
| **WEB** | `text/html` | Scheme `http://`, `https://` | Web URLs |

---

## 3. Modular Extraction Pipeline

### 3.1 Document Extractor (`DocumentExtractor`)
- **PDF:** Uses `pdfplumber` for page-aware extraction, preserving page numbers in chunks and capturing tables (`extract_tables()`). Gracefully falls back if corrupted.
- **DOCX:** Uses `python-docx`, maintaining heading hierarchy and document tables.
- **PPTX:** Uses `python-pptx`, capturing slide titles, shapes, text frames, and speaker notes with slide indices.
- **Spreadsheets & CSV:** Uses `openpyxl` and `csv.reader` to extract sheet names, headers, table previews, and row content.
- **HTML:** Uses `BeautifulSoup` to strip navigational noise (`script`, `style`, `nav`, `footer`) and extract document body text.

### 3.2 Code Extractor (`CodeExtractor`)
- Extracts line counts, functions, classes, docstrings, and language tags (`.py`, `.ts`, `.rs`, etc.).
- Chunks preserve structural source block boundaries.

### 3.3 Media Extractor (`MediaExtractor`)
- **Images:** Uses PIL to extract format, dimensions ($W \times H$), color mode, and perceptual summary.
- **Audio:** Uses native `wave` module or `ffprobe` to determine channels, sample rate, and duration.
- **Video:** Uses `ffprobe` to extract resolution, duration, video codecs, and audio streams.

### 3.4 Web Extractor (`WebExtractor`)
- Fetches remote URLs with custom user agent (`AMATYA-Ingestion-Agent/13.2`).
- Restricts payload download to 5 MB max to protect memory.
- Enforces strict SSRF protection (blocking private networks and loopbacks).

---

## 4. Semantic Normalization & Chunking

The `SemanticChunker` splits normalized content into contextual chunks:
- **Target Size:** ~800 characters (~200 tokens).
- **Overlap:** 120 characters to preserve boundary context.
- **Break Preference:** Double newline (`\n\n`) -> Single newline (`\n`) -> Sentence break (`. `) -> Word space (` `).
- **Attributes:** Each chunk retains `chunk_id`, `source_id`, `page_number`, `section`, `modality`, and `tokens_approx`.

---

## 5. Security and Governance Controls

1. **Path Restrictions:** Files originating in system directories (`/etc`, `/proc`, `/sys`, `/root`, `/var/run`) are blocked at the boundary.
2. **SSRF Guard:** Web URLs resolving to loopback (`127.0.0.1`), RFC 1918 private ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), or link-local addresses are rejected immediately.
3. **Secret Redaction:** All extracted text passes through `core.security.redact_secrets` before chunking and persistence.
4. **Untrusted Data Isolation:** Chunks are marked `untrusted=True` and sanitized to prevent prompt-injection attacks.

---

## 6. Incremental Indexing & Recovery State Machine

### 6.1 Incremental Fingerprinting
- **$O(1)$ Fast-Path:** Before computing file checksums or reading content, the engine compares `(mtime, size_bytes)` against the registry. If identical to a completed ingestion, the file is marked `UNCHANGED` and skipped instantly.
- **Modified Files:** If `mtime` or `size` changes, the engine computes SHA-256. If hash differs, the file is re-extracted, old RAG chunks are replaced, and the registry is updated.
- **Deleted Files:** `propagate_deletion(source_id)` removes the source from `ingestion_index.json` and cascades chunk purging to `knowledge_index.json`.

### 6.2 Interrupted Recovery
- State transitions: `PENDING` -> `PROCESSING` -> `COMPLETED` / `FAILED`.
- If AMATYA terminates during an ingestion batch, any items left in `PROCESSING` are automatically identified and reset to `PENDING` upon engine initialization.

---

## 7. Action and Tool Interface

The Universal Ingestion Framework is accessible via `actions/knowledge_base.py`:

```python
# Ingest single file or directory
res = action_loader.run("knowledge_base", {"action": "ingest", "path": "/path/to/doc.pdf"})

# Ingest online documentation
res = action_loader.run("knowledge_base", {"action": "ingest", "url": "https://example.com/guide"})

# Ingest note directly
res = action_loader.run("knowledge_base", {"action": "ingest", "text": "Important project note", "title": "Setup Note"})

# Check ingestion registry telemetry
res = action_loader.run("knowledge_base", {"action": "ingestion_status"})

# Perform incremental directory sync with preview
preview = action_loader.run("knowledge_base", {"action": "sync_incremental", "path": "./docs", "preview": True})
sync = action_loader.run("knowledge_base", {"action": "sync_incremental", "path": "./docs"})
```

