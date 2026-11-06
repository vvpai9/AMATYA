"""
AMATYA Universal Ingestion Framework (core/ingestion.py)
=========================================================
Phase 13.2 Core Implementation:
  - Universal Source Abstraction (File, Directory, URL, Text, Code, Media).
  - Robust Modality and MIME Type Detection (Magic bytes + Extension fallback).
  - Modular Extraction Pipeline (Documents, Code, Images, Audio, Video, Web).
  - Structural Normalization, Page/Section Preservation & Semantic Chunking.
  - Full Provenance, Cryptographic Integrity (SHA-256) & Metadata Tracking.
  - Incremental Indexing (New, Modified, Unchanged, Deleted) with O(1) Fast-Path.
  - Untrusted Data Sandboxing & Secret Redaction (Security Governance).
  - Interrupted Ingestion Recovery & Resumption State Machine.
"""
from __future__ import annotations

import csv
import hashlib
import io
import ipaddress
import json
import mimetypes
import os
import re
import shutil
import socket
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from core.security import redact_secrets
from memory.config_manager import BASE_DIR

INGESTION_INDEX_PATH = BASE_DIR / "memory" / "ingestion_index.json"
_LOCK = threading.RLock()


# ============================================================================
# Modality and Source Enums
# ============================================================================

class Modality(str, Enum):
    DOCUMENT = "document"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    CODE = "code"
    DATA = "data"
    WEB = "web"
    UNKNOWN = "unknown"


class SourceType(str, Enum):
    FILE = "file"
    DIRECTORY = "directory"
    URL = "url"
    TEXT = "text"
    STREAM = "stream"
    REPO = "repo"


class IngestionStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    DELETED = "deleted"


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class ProvenanceRecord:
    source_id: str
    ingested_at: float = field(default_factory=time.time)
    extractor: str = "core.ingestion"
    parser_version: str = "13.2.0"
    model_used: str | None = None
    confidence: float = 1.0  # 0.0 to 1.0
    allow_cloud: bool = True
    untrusted: bool = True
    checksum: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProvenanceRecord:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ContentChunk:
    chunk_id: str
    source_id: str
    chunk_index: int
    text: str
    page_number: int | None = None
    section: str = ""
    tokens_approx: int = 0
    modality: str = Modality.DOCUMENT.value
    tags: list[str] = field(default_factory=list)
    embedding: list[float] | None = None
    untrusted: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContentChunk:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ExtractedContent:
    source_id: str
    title: str
    raw_text: str
    modality: Modality
    mime_type: str
    chunks: list[ContentChunk] = field(default_factory=list)
    provenance: ProvenanceRecord | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    tables: list[dict[str, Any]] = field(default_factory=list)
    extracted_entities: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    @property
    def is_success(self) -> bool:
        return self.error is None and len(self.raw_text.strip()) > 0


@dataclass
class SourceRecord:
    source_id: str
    uri: str
    source_type: str
    modality: str
    mime_type: str
    size_bytes: int
    content_hash: str
    mtime: float
    status: str
    error: str | None = None
    chunk_count: int = 0
    provenance: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SourceRecord:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ============================================================================
# Modality & MIME Detection Engine
# ============================================================================

class ModalityDetector:
    """Accurately detects modality and MIME type via magic bytes, content sniffing, and extensions."""

    MAGIC_SIGNATURES: list[tuple[bytes, Modality, str]] = [
        (b"%PDF-", Modality.DOCUMENT, "application/pdf"),
        (b"\x89PNG\r\n\x1a\n", Modality.IMAGE, "image/png"),
        (b"\xff\xd8\xff", Modality.IMAGE, "image/jpeg"),
        (b"RIFF", Modality.AUDIO, "audio/wav"),  # Will verify 'WAVE' chunk below
        (b"ID3", Modality.AUDIO, "audio/mpeg"),
        (b"\xff\xfb", Modality.AUDIO, "audio/mpeg"),
        (b"fLaC", Modality.AUDIO, "audio/flac"),
        (b"OggS", Modality.AUDIO, "audio/ogg"),
        (b"\x1a\x45\xdf\xa3", Modality.VIDEO, "video/webm"),  # Matroska / WebM
        (b"PK\x03\x04", Modality.DOCUMENT, "application/zip"),  # Office docs (docx/pptx/xlsx) checked specifically
    ]

    EXT_MAP: dict[str, tuple[Modality, str]] = {
        # Documents
        ".pdf": (Modality.DOCUMENT, "application/pdf"),
        ".docx": (Modality.DOCUMENT, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ".doc": (Modality.DOCUMENT, "application/msword"),
        ".pptx": (Modality.DOCUMENT, "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
        ".ppt": (Modality.DOCUMENT, "application/vnd.ms-powerpoint"),
        ".xlsx": (Modality.DATA, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ".xls": (Modality.DATA, "application/vnd.ms-excel"),
        ".csv": (Modality.DATA, "text/csv"),
        ".tsv": (Modality.DATA, "text/tab-separated-values"),
        ".txt": (Modality.DOCUMENT, "text/plain"),
        ".md": (Modality.DOCUMENT, "text/markdown"),
        ".markdown": (Modality.DOCUMENT, "text/markdown"),
        ".rtf": (Modality.DOCUMENT, "application/rtf"),
        ".epub": (Modality.DOCUMENT, "application/epub+zip"),
        ".html": (Modality.DOCUMENT, "text/html"),
        ".htm": (Modality.DOCUMENT, "text/html"),

        # Images
        ".png": (Modality.IMAGE, "image/png"),
        ".jpg": (Modality.IMAGE, "image/jpeg"),
        ".jpeg": (Modality.IMAGE, "image/jpeg"),
        ".webp": (Modality.IMAGE, "image/webp"),
        ".svg": (Modality.IMAGE, "image/svg+xml"),
        ".bmp": (Modality.IMAGE, "image/bmp"),
        ".tiff": (Modality.IMAGE, "image/tiff"),
        ".tif": (Modality.IMAGE, "image/tiff"),
        ".ico": (Modality.IMAGE, "image/x-icon"),

        # Audio
        ".wav": (Modality.AUDIO, "audio/wav"),
        ".mp3": (Modality.AUDIO, "audio/mpeg"),
        ".flac": (Modality.AUDIO, "audio/flac"),
        ".ogg": (Modality.AUDIO, "audio/ogg"),
        ".m4a": (Modality.AUDIO, "audio/mp4"),
        ".aac": (Modality.AUDIO, "audio/aac"),
        ".opus": (Modality.AUDIO, "audio/opus"),
        ".wma": (Modality.AUDIO, "audio/x-ms-wma"),

        # Video
        ".mp4": (Modality.VIDEO, "video/mp4"),
        ".mkv": (Modality.VIDEO, "video/x-matroska"),
        ".webm": (Modality.VIDEO, "video/webm"),
        ".mov": (Modality.VIDEO, "video/quicktime"),
        ".avi": (Modality.VIDEO, "video/x-msvideo"),
        ".flv": (Modality.VIDEO, "video/x-flv"),

        # Code & Technical
        ".py": (Modality.CODE, "text/x-python"),
        ".js": (Modality.CODE, "application/javascript"),
        ".ts": (Modality.CODE, "application/typescript"),
        ".tsx": (Modality.CODE, "text/tsx"),
        ".jsx": (Modality.CODE, "text/jsx"),
        ".c": (Modality.CODE, "text/x-c"),
        ".cpp": (Modality.CODE, "text/x-c++"),
        ".h": (Modality.CODE, "text/x-chdr"),
        ".hpp": (Modality.CODE, "text/x-c++hdr"),
        ".rs": (Modality.CODE, "text/rust"),
        ".go": (Modality.CODE, "text/x-go"),
        ".java": (Modality.CODE, "text/x-java"),
        ".sh": (Modality.CODE, "text/x-shellscript"),
        ".bash": (Modality.CODE, "text/x-shellscript"),
        ".sql": (Modality.CODE, "application/sql"),
        ".yaml": (Modality.CODE, "application/yaml"),
        ".yml": (Modality.CODE, "application/yaml"),
        ".toml": (Modality.CODE, "application/toml"),
        ".json": (Modality.DATA, "application/json"),
        ".ini": (Modality.CODE, "text/plain"),
        ".cfg": (Modality.CODE, "text/plain"),
        ".log": (Modality.DOCUMENT, "text/plain"),
    }

    @classmethod
    def detect(cls, uri_or_path: str | Path, content_sample: bytes | None = None) -> tuple[Modality, str]:
        uri_str = str(uri_or_path)

        # Check URL
        if uri_str.startswith("http://") or uri_str.startswith("https://"):
            return Modality.WEB, "text/html"

        path = Path(uri_str)
        ext = path.suffix.lower()

        # If magic bytes provided or readable
        sample = content_sample
        if sample is None and path.exists() and path.is_file():
            try:
                with open(path, "rb") as f:
                    sample = f.read(512)
            except Exception:
                pass

        if sample:
            # Check magic signatures
            for sig, mod, mime in cls.MAGIC_SIGNATURES:
                if sample.startswith(sig):
                    if sig == b"RIFF" and len(sample) >= 12:
                        if sample[8:12] == b"WAVE":
                            return Modality.AUDIO, "audio/wav"
                        elif sample[8:12] == b"AVI ":
                            return Modality.VIDEO, "video/x-msvideo"
                    elif sig == b"PK\x03\x04":
                        # Inspect Zip contents for office document types
                        if ext in (".docx", ".pptx", ".xlsx"):
                            if ext in cls.EXT_MAP:
                                return cls.EXT_MAP[ext]
                    else:
                        return mod, mime

            # Check for MP4 ftyp
            if len(sample) >= 12 and sample[4:8] == b"ftyp":
                return Modality.VIDEO, "video/mp4"

        # Fall back to extension mapping
        if ext in cls.EXT_MAP:
            return cls.EXT_MAP[ext]

        # Standard mimetypes library guess
        guessed_mime, _ = mimetypes.guess_type(uri_str)
        if guessed_mime:
            if guessed_mime.startswith("image/"):
                return Modality.IMAGE, guessed_mime
            if guessed_mime.startswith("audio/"):
                return Modality.AUDIO, guessed_mime
            if guessed_mime.startswith("video/"):
                return Modality.VIDEO, guessed_mime
            if guessed_mime.startswith("text/"):
                return Modality.DOCUMENT, guessed_mime

        return Modality.UNKNOWN, "application/octet-stream"


# ============================================================================
# Security & Governance Boundary
# ============================================================================

class SecurityGovernance:
    """Enforces directory restrictions, credential redaction, and untrusted boundaries."""

    _RESTRICTED_PREFIXES = (
        "/etc", "/proc", "/sys", "/dev", "/root", "/var/run",
        "/run/credentials", "/etc/shadow", "/etc/passwd",
    )

    @classmethod
    def validate_path(cls, path: Path) -> tuple[bool, str]:
        resolved = path.resolve()
        resolved_str = str(resolved)
        for prefix in cls._RESTRICTED_PREFIXES:
            if resolved_str == prefix or resolved_str.startswith(prefix + "/"):
                return False, f"Access denied: Path '{resolved}' is in a protected system directory."
        return True, ""

    @classmethod
    def validate_url(cls, url: str) -> tuple[bool, str]:
        """Guards against SSRF and access to internal private IP spaces."""
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False, f"Invalid scheme '{parsed.scheme}'. Only 'http' and 'https' are allowed."
        host = parsed.hostname or ""
        if not host:
            return False, "Invalid URL: Missing hostname."

        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            try:
                ip_str = socket.gethostbyname(host)
                ip = ipaddress.ip_address(ip_str)
            except Exception as e:
                return False, f"DNS resolution failed for '{host}': {e}"

        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False, f"Access denied: Target '{host}' ({ip}) resolves to a restricted private or loopback IP."

        return True, ""

    @classmethod
    def sanitize_untrusted_text(cls, text: str) -> str:
        """Strips secret keys and guards against prompt injection delimiters."""
        redacted = redact_secrets(text or "")
        # Neutralize potential system delimiter injections
        sanitized = re.sub(r"(<\s*/?\s*(?:system|user|assistant|instruction|guidelines|prompt)\s*>)", r"[\1]", redacted, flags=re.IGNORECASE)
        return sanitized


# ============================================================================
# Chunking and Normalization Engine
# ============================================================================

class SemanticChunker:
    """Splits normalized text into structurally sound chunks with provenance and token approximations."""

    def __init__(self, target_chars: int = 800, overlap_chars: int = 120):
        self.target_chars = target_chars
        self.overlap_chars = overlap_chars

    def chunk(
        self,
        text: str,
        source_id: str,
        modality: str = Modality.DOCUMENT.value,
        page_number: int | None = None,
        section: str = "",
        tags: list[str] | None = None,
    ) -> list[ContentChunk]:
        clean = SecurityGovernance.sanitize_untrusted_text(text).strip()
        if not clean:
            return []

        chunks: list[ContentChunk] = []
        if len(clean) <= self.target_chars:
            chunks.append(
                ContentChunk(
                    chunk_id=f"{source_id}#chunk_0",
                    source_id=source_id,
                    chunk_index=0,
                    text=clean,
                    page_number=page_number,
                    section=section,
                    tokens_approx=max(1, len(clean) // 4),
                    modality=modality,
                    tags=tags or [],
                    untrusted=True,
                )
            )
            return chunks

        start = 0
        n = len(clean)
        idx = 0
        while start < n:
            end = min(n, start + self.target_chars)
            # Boundary break preference: Paragraph newline -> Period/Sentence -> Space
            if end < n:
                para_break = clean.rfind("\n\n", start + self.target_chars // 2, end)
                if para_break != -1:
                    end = para_break + 2
                else:
                    nl_break = clean.rfind("\n", start + self.target_chars // 2, end)
                    if nl_break != -1:
                        end = nl_break + 1
                    else:
                        sent_break = clean.rfind(". ", start + self.target_chars // 2, end)
                        if sent_break != -1:
                            end = sent_break + 2

            segment = clean[start:end].strip()
            if segment:
                chunks.append(
                    ContentChunk(
                        chunk_id=f"{source_id}#chunk_{idx}",
                        source_id=source_id,
                        chunk_index=idx,
                        text=segment,
                        page_number=page_number,
                        section=section,
                        tokens_approx=max(1, len(segment) // 4),
                        modality=modality,
                        tags=tags or [],
                        untrusted=True,
                    )
                )
                idx += 1

            if end >= n:
                break
            start = max(start + 1, end - self.overlap_chars)

        return chunks


# ============================================================================
# Modality Extractors
# ============================================================================

class DocumentExtractor:
    """Extracts text, structure, tables, and page metadata from document formats."""

    def __init__(self, chunker: SemanticChunker):
        self.chunker = chunker

    def extract(self, path: Path, source_id: str, mime_type: str) -> ExtractedContent:
        ext = path.suffix.lower()
        title = path.name
        chunks: list[ContentChunk] = []
        tables: list[dict[str, Any]] = []
        raw_text_parts: list[str] = []
        metadata: dict[str, Any] = {"file_name": path.name, "file_size": path.stat().st_size}

        try:
            if ext == ".pdf":
                # PDF parsing with pdfplumber
                try:
                    import pdfplumber
                    with pdfplumber.open(str(path)) as pdf:
                        metadata["page_count"] = len(pdf.pages)
                        for page_idx, page in enumerate(pdf.pages, start=1):
                            page_text = page.extract_text() or ""
                            if page_text.strip():
                                raw_text_parts.append(page_text)
                                page_chunks = self.chunker.chunk(
                                    page_text,
                                    source_id=source_id,
                                    modality=Modality.DOCUMENT.value,
                                    page_number=page_idx,
                                    section=f"Page {page_idx}",
                                    tags=["pdf"],
                                )
                                chunks.extend(page_chunks)
                            # Extract tables
                            extracted_tables = page.extract_tables() or []
                            for t_idx, t in enumerate(extracted_tables):
                                if t and len(t) > 1:
                                    tables.append({
                                        "page": page_idx,
                                        "table_index": t_idx + 1,
                                        "headers": t[0],
                                        "row_count": len(t) - 1,
                                        "data": t[1:11],  # Preview rows
                                    })
                except Exception as pdf_err:
                    return ExtractedContent(
                        source_id=source_id,
                        title=title,
                        raw_text="",
                        modality=Modality.DOCUMENT,
                        mime_type=mime_type,
                        error=f"PDF extraction failure: {pdf_err}",
                        metadata=metadata,
                    )

            elif ext == ".docx":
                # DOCX parsing with python-docx
                try:
                    import docx
                    doc = docx.Document(str(path))
                    current_section = "Introduction"
                    sec_paras: list[str] = []

                    for p in doc.paragraphs:
                        txt = p.text.strip()
                        if not txt:
                            continue
                        if p.style and p.style.name.startswith("Heading"):
                            if sec_paras:
                                sec_text = "\n".join(sec_paras)
                                raw_text_parts.append(sec_text)
                                chunks.extend(self.chunker.chunk(
                                    sec_text,
                                    source_id=source_id,
                                    modality=Modality.DOCUMENT.value,
                                    section=current_section,
                                    tags=["docx"],
                                ))
                                sec_paras = []
                            current_section = txt
                        sec_paras.append(txt)

                    if sec_paras:
                        sec_text = "\n".join(sec_paras)
                        raw_text_parts.append(sec_text)
                        chunks.extend(self.chunker.chunk(
                            sec_text,
                            source_id=source_id,
                            modality=Modality.DOCUMENT.value,
                            section=current_section,
                            tags=["docx"],
                        ))

                    # Tables in DOCX
                    for t_idx, t in enumerate(doc.tables):
                        t_data = [[c.text.strip() for c in row.cells] for row in t.rows]
                        if t_data and len(t_data) > 1:
                            tables.append({
                                "table_index": t_idx + 1,
                                "headers": t_data[0],
                                "row_count": len(t_data) - 1,
                                "data": t_data[1:11],
                            })
                except Exception as docx_err:
                    return ExtractedContent(
                        source_id=source_id,
                        title=title,
                        raw_text="",
                        modality=Modality.DOCUMENT,
                        mime_type=mime_type,
                        error=f"DOCX extraction failure: {docx_err}",
                        metadata=metadata,
                    )

            elif ext == ".pptx":
                # PPTX parsing with python-pptx
                try:
                    from pptx import Presentation
                    prs = Presentation(str(path))
                    metadata["slide_count"] = len(prs.slides)
                    for slide_idx, slide in enumerate(prs.slides, start=1):
                        slide_texts = []
                        slide_title = f"Slide {slide_idx}"
                        for shape in slide.shapes:
                            if shape.has_text_frame:
                                txt = shape.text_frame.text.strip()
                                if txt:
                                    if shape == slide.shapes[0] and not slide_texts:
                                        slide_title = txt[:60]
                                    slide_texts.append(txt)
                        if slide_texts:
                            s_text = "\n".join(slide_texts)
                            raw_text_parts.append(s_text)
                            chunks.extend(self.chunker.chunk(
                                s_text,
                                source_id=source_id,
                                modality=Modality.DOCUMENT.value,
                                page_number=slide_idx,
                                section=slide_title,
                                tags=["pptx"],
                            ))
                except Exception as pptx_err:
                    return ExtractedContent(
                        source_id=source_id,
                        title=title,
                        raw_text="",
                        modality=Modality.DOCUMENT,
                        mime_type=mime_type,
                        error=f"PPTX extraction failure: {pptx_err}",
                        metadata=metadata,
                    )

            elif ext in (".xlsx", ".xls"):
                # Excel parsing with openpyxl
                try:
                    import openpyxl
                    wb = openpyxl.load_workbook(str(path), data_only=True)
                    metadata["sheets"] = wb.sheetnames
                    for sheet_name in wb.sheetnames:
                        ws = wb[sheet_name]
                        rows = list(ws.iter_rows(values_only=True))
                        if rows:
                            header = [str(c or "") for c in rows[0]]
                            rows_data = [[str(c or "") for c in r] for r in rows[1:]]
                            tables.append({
                                "sheet": sheet_name,
                                "headers": header,
                                "row_count": len(rows_data),
                                "data": rows_data[:10],
                            })
                            # Format sheet into readable text
                            sheet_lines = [f"=== Sheet: {sheet_name} ===", " | ".join(header)]
                            for r in rows_data[:50]:
                                sheet_lines.append(" | ".join(r))
                            s_text = "\n".join(sheet_lines)
                            raw_text_parts.append(s_text)
                            chunks.extend(self.chunker.chunk(
                                s_text,
                                source_id=source_id,
                                modality=Modality.DATA.value,
                                section=f"Sheet: {sheet_name}",
                                tags=["spreadsheet"],
                            ))
                except Exception as xlsx_err:
                    return ExtractedContent(
                        source_id=source_id,
                        title=title,
                        raw_text="",
                        modality=Modality.DATA,
                        mime_type=mime_type,
                        error=f"Spreadsheet extraction failure: {xlsx_err}",
                        metadata=metadata,
                    )

            elif ext in (".csv", ".tsv"):
                delimiter = "\t" if ext == ".tsv" else ","
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    reader = csv.reader(f, delimiter=delimiter)
                    rows = list(reader)
                    if rows:
                        headers = rows[0]
                        data_rows = rows[1:]
                        tables.append({
                            "headers": headers,
                            "row_count": len(data_rows),
                            "data": data_rows[:10],
                        })
                        csv_text = "\n".join([" | ".join(r) for r in rows[:100]])
                        raw_text_parts.append(csv_text)
                        chunks.extend(self.chunker.chunk(
                            csv_text,
                            source_id=source_id,
                            modality=Modality.DATA.value,
                            section="CSV Table",
                            tags=["csv"],
                        ))

            elif ext in (".html", ".htm"):
                from bs4 import BeautifulSoup
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    soup = BeautifulSoup(f.read(), "html.parser")
                    title = soup.title.string if soup.title else path.name
                    for script in soup(["script", "style"]):
                        script.decompose()
                    body_text = soup.get_text(separator="\n").strip()
                    raw_text_parts.append(body_text)
                    chunks.extend(self.chunker.chunk(
                        body_text,
                        source_id=source_id,
                        modality=Modality.DOCUMENT.value,
                        section=title,
                        tags=["html"],
                    ))

            else:
                # Standard UTF-8 text / Markdown
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    txt = f.read()
                    raw_text_parts.append(txt)
                    chunks.extend(self.chunker.chunk(
                        txt,
                        source_id=source_id,
                        modality=Modality.DOCUMENT.value,
                        section=path.stem,
                        tags=[ext.lstrip(".") or "text"],
                    ))

        except Exception as exc:
            return ExtractedContent(
                source_id=source_id,
                title=title,
                raw_text="",
                modality=Modality.DOCUMENT,
                mime_type=mime_type,
                error=f"Extraction failure: {exc}",
                metadata=metadata,
            )

        full_raw_text = "\n\n".join(raw_text_parts)
        provenance = ProvenanceRecord(
            source_id=source_id,
            extractor="DocumentExtractor",
            confidence=0.95 if full_raw_text else 0.0,
        )

        return ExtractedContent(
            source_id=source_id,
            title=title,
            raw_text=full_raw_text,
            modality=Modality.DOCUMENT if ext not in (".xlsx", ".xls", ".csv", ".tsv") else Modality.DATA,
            mime_type=mime_type,
            chunks=chunks,
            provenance=provenance,
            metadata=metadata,
            tables=tables,
        )


class CodeExtractor:
    """Extracts structure, functions, classes, and comments from source code files."""

    def __init__(self, chunker: SemanticChunker):
        self.chunker = chunker

    def extract(self, path: Path, source_id: str, mime_type: str) -> ExtractedContent:
        title = path.name
        metadata: dict[str, Any] = {"file_name": path.name, "language": path.suffix.lstrip(".")}

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                code_text = f.read()

            metadata["line_count"] = code_text.count("\n") + 1

            # Detect top-level definitions
            defs: list[str] = []
            if path.suffix == ".py":
                for line in code_text.splitlines():
                    m = re.match(r"^\s*(def|class)\s+([a-zA-Z0-9_]+)", line)
                    if m:
                        defs.append(f"{m.group(1)} {m.group(2)}")
                metadata["symbols"] = defs

            chunks = self.chunker.chunk(
                code_text,
                source_id=source_id,
                modality=Modality.CODE.value,
                section=f"Source: {path.name}",
                tags=["code", path.suffix.lstrip(".")],
            )

            provenance = ProvenanceRecord(
                source_id=source_id,
                extractor="CodeExtractor",
                confidence=1.0,
            )

            return ExtractedContent(
                source_id=source_id,
                title=title,
                raw_text=code_text,
                modality=Modality.CODE,
                mime_type=mime_type,
                chunks=chunks,
                provenance=provenance,
                metadata=metadata,
            )
        except Exception as exc:
            return ExtractedContent(
                source_id=source_id,
                title=title,
                raw_text="",
                modality=Modality.CODE,
                mime_type=mime_type,
                error=f"Code extraction failure: {exc}",
                metadata=metadata,
            )


class MediaExtractor:
    """Extracts metadata, dimensions, perceptual properties, and stream info from images, audio, and video."""

    def __init__(self, chunker: SemanticChunker):
        self.chunker = chunker

    def extract_image(self, path: Path, source_id: str, mime_type: str) -> ExtractedContent:
        title = path.name
        metadata: dict[str, Any] = {"file_name": path.name, "file_size": path.stat().st_size}
        try:
            from PIL import Image
            with Image.open(path) as img:
                metadata["width"], metadata["height"] = img.size
                metadata["format"] = img.format
                metadata["mode"] = img.mode

            summary_text = (
                f"[Image: {title}] Format: {metadata.get('format')}, "
                f"Dimensions: {metadata.get('width')}x{metadata.get('height')}, Mode: {metadata.get('mode')}."
            )
            chunks = self.chunker.chunk(
                summary_text,
                source_id=source_id,
                modality=Modality.IMAGE.value,
                section="Image Metadata",
                tags=["image", path.suffix.lstrip(".")],
            )
            provenance = ProvenanceRecord(
                source_id=source_id,
                extractor="MediaExtractor.Image",
                confidence=0.9,
            )
            return ExtractedContent(
                source_id=source_id,
                title=title,
                raw_text=summary_text,
                modality=Modality.IMAGE,
                mime_type=mime_type,
                chunks=chunks,
                provenance=provenance,
                metadata=metadata,
            )
        except Exception as exc:
            return ExtractedContent(
                source_id=source_id,
                title=title,
                raw_text="",
                modality=Modality.IMAGE,
                mime_type=mime_type,
                error=f"Image extraction failure: {exc}",
                metadata=metadata,
            )

    def extract_audio(self, path: Path, source_id: str, mime_type: str) -> ExtractedContent:
        title = path.name
        metadata: dict[str, Any] = {"file_name": path.name, "file_size": path.stat().st_size}
        try:
            # Native wave reading if wav
            if path.suffix.lower() == ".wav":
                import wave
                with wave.open(str(path), "rb") as wf:
                    metadata["channels"] = wf.getnchannels()
                    metadata["sample_rate"] = wf.getframerate()
                    metadata["duration_seconds"] = round(wf.getnframes() / float(wf.getframerate()), 2)
            else:
                # ffprobe stream probe
                cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=channels,sample_rate", "-of", "json", str(path)]
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
                if res.returncode == 0:
                    info = json.loads(res.stdout)
                    fmt = info.get("format", {})
                    metadata["duration_seconds"] = float(fmt.get("duration", 0.0))

            summary_text = (
                f"[Audio Recording: {title}] Duration: {metadata.get('duration_seconds', 'unknown')}s, "
                f"Channels: {metadata.get('channels', 'unknown')}, Sample Rate: {metadata.get('sample_rate', 'unknown')}Hz."
            )
            chunks = self.chunker.chunk(
                summary_text,
                source_id=source_id,
                modality=Modality.AUDIO.value,
                section="Audio Metadata",
                tags=["audio", path.suffix.lstrip(".")],
            )
            provenance = ProvenanceRecord(
                source_id=source_id,
                extractor="MediaExtractor.Audio",
                confidence=0.85,
            )
            return ExtractedContent(
                source_id=source_id,
                title=title,
                raw_text=summary_text,
                modality=Modality.AUDIO,
                mime_type=mime_type,
                chunks=chunks,
                provenance=provenance,
                metadata=metadata,
            )
        except Exception as exc:
            return ExtractedContent(
                source_id=source_id,
                title=title,
                raw_text="",
                modality=Modality.AUDIO,
                mime_type=mime_type,
                error=f"Audio extraction failure: {exc}",
                metadata=metadata,
            )

    def extract_video(self, path: Path, source_id: str, mime_type: str) -> ExtractedContent:
        title = path.name
        metadata: dict[str, Any] = {"file_name": path.name, "file_size": path.stat().st_size}
        try:
            cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=width,height,codec_name", "-of", "json", str(path)]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
            if res.returncode == 0:
                info = json.loads(res.stdout)
                fmt = info.get("format", {})
                metadata["duration_seconds"] = float(fmt.get("duration", 0.0))
                streams = info.get("streams", [])
                if streams:
                    v_stream = next((s for s in streams if "width" in s), streams[0])
                    metadata["width"] = v_stream.get("width")
                    metadata["height"] = v_stream.get("height")
                    metadata["codec"] = v_stream.get("codec_name")

            summary_text = (
                f"[Video Recording: {title}] Duration: {metadata.get('duration_seconds', 'unknown')}s, "
                f"Resolution: {metadata.get('width', '?')}x{metadata.get('height', '?')}, Codec: {metadata.get('codec', '?')}."
            )
            chunks = self.chunker.chunk(
                summary_text,
                source_id=source_id,
                modality=Modality.VIDEO.value,
                section="Video Metadata",
                tags=["video", path.suffix.lstrip(".")],
            )
            provenance = ProvenanceRecord(
                source_id=source_id,
                extractor="MediaExtractor.Video",
                confidence=0.85,
            )
            return ExtractedContent(
                source_id=source_id,
                title=title,
                raw_text=summary_text,
                modality=Modality.VIDEO,
                mime_type=mime_type,
                chunks=chunks,
                provenance=provenance,
                metadata=metadata,
            )
        except Exception as exc:
            return ExtractedContent(
                source_id=source_id,
                title=title,
                raw_text="",
                modality=Modality.VIDEO,
                mime_type=mime_type,
                error=f"Video extraction failure: {exc}",
                metadata=metadata,
            )


class WebExtractor:
    """Safely extracts text, structure, headers, and metadata from authorized online URLs."""

    def __init__(self, chunker: SemanticChunker):
        self.chunker = chunker

    def extract(self, url: str, source_id: str) -> ExtractedContent:
        valid, err_msg = SecurityGovernance.validate_url(url)
        if not valid:
            return ExtractedContent(
                source_id=source_id,
                title=url,
                raw_text="",
                modality=Modality.WEB,
                mime_type="text/html",
                error=err_msg,
            )

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "AMATYA-Ingestion-Agent/13.2 (Compatible; Linux)"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                content_bytes = resp.read(5 * 1024 * 1024)  # 5 MB max
                content_type = resp.headers.get_content_type() or "text/html"
                encoding = resp.headers.get_content_charset() or "utf-8"

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(content_bytes.decode(encoding, errors="replace"), "html.parser")
            title = soup.title.string.strip() if soup.title and soup.title.string else url

            # Remove navigation and scripts
            for tag in soup(["script", "style", "nav", "footer"]):
                tag.decompose()

            body_text = soup.get_text(separator="\n").strip()
            chunks = self.chunker.chunk(
                body_text,
                source_id=source_id,
                modality=Modality.WEB.value,
                section=title,
                tags=["web", "online"],
            )

            provenance = ProvenanceRecord(
                source_id=source_id,
                extractor="WebExtractor",
                confidence=0.9,
                checksum=hashlib.sha256(content_bytes).hexdigest(),
            )

            return ExtractedContent(
                source_id=source_id,
                title=title,
                raw_text=body_text,
                modality=Modality.WEB,
                mime_type=content_type,
                chunks=chunks,
                provenance=provenance,
                metadata={"url": url, "content_length": len(content_bytes)},
            )
        except Exception as exc:
            return ExtractedContent(
                source_id=source_id,
                title=url,
                raw_text="",
                modality=Modality.WEB,
                mime_type="text/html",
                error=f"Web extraction failure: {exc}",
            )


# ============================================================================
# Universal Ingestion Pipeline
# ============================================================================

class ExtractionPipeline:
    """Orchestrates modality validation, extractor selection, secret redaction, and chunking."""

    def __init__(self):
        self.chunker = SemanticChunker()
        self.doc_extractor = DocumentExtractor(self.chunker)
        self.code_extractor = CodeExtractor(self.chunker)
        self.media_extractor = MediaExtractor(self.chunker)
        self.web_extractor = WebExtractor(self.chunker)

    def extract(self, path: Path, source_id: str, modality: Modality, mime_type: str) -> ExtractedContent:
        # Enforce security path boundary
        valid, err_msg = SecurityGovernance.validate_path(path)
        if not valid:
            return ExtractedContent(
                source_id=source_id,
                title=path.name,
                raw_text="",
                modality=modality,
                mime_type=mime_type,
                error=err_msg,
            )

        if modality == Modality.DOCUMENT or modality == Modality.DATA:
            return self.doc_extractor.extract(path, source_id, mime_type)
        elif modality == Modality.CODE:
            return self.code_extractor.extract(path, source_id, mime_type)
        elif modality == Modality.IMAGE:
            return self.media_extractor.extract_image(path, source_id, mime_type)
        elif modality == Modality.AUDIO:
            return self.media_extractor.extract_audio(path, source_id, mime_type)
        elif modality == Modality.VIDEO:
            return self.media_extractor.extract_video(path, source_id, mime_type)
        else:
            # Fallback to document extractor
            return self.doc_extractor.extract(path, source_id, mime_type)

    def extract_url(self, url: str, source_id: str) -> ExtractedContent:
        return self.web_extractor.extract(url, source_id)


# ============================================================================
# Incremental Registry & State Store
# ============================================================================

class IngestionRegistry:
    """Thread-safe persistent catalog of all ingested sources with state tracking."""

    def __init__(self, index_path: Path | None = None):
        self._path = index_path or INGESTION_INDEX_PATH
        self._sources: dict[str, SourceRecord] = {}
        self._load()

    def _load(self) -> None:
        with _LOCK:
            if not self._path.exists():
                self._sources = {}
                return
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                sources = {}
                for sid, sdata in data.get("sources", {}).items():
                    rec = SourceRecord.from_dict(sdata)
                    # Auto-recover interrupted items on restart
                    if rec.status == IngestionStatus.PROCESSING.value:
                        rec.status = IngestionStatus.PENDING.value
                    sources[sid] = rec
                self._sources = sources
            except Exception:
                self._sources = {}

    def _save(self) -> None:
        with _LOCK:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self._path.with_suffix(".tmp")
            out = {
                "version": "13.2.0",
                "updated_at": time.time(),
                "sources": {sid: rec.to_dict() for sid, rec in self._sources.items()},
            }
            temp_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
            temp_path.replace(self._path)

    def get(self, source_id: str) -> SourceRecord | None:
        with _LOCK:
            return self._sources.get(source_id)

    def set(self, record: SourceRecord) -> None:
        with _LOCK:
            record.updated_at = time.time()
            self._sources[record.source_id] = record
            self._save()

    def remove(self, source_id: str) -> bool:
        with _LOCK:
            if source_id in self._sources:
                del self._sources[source_id]
                self._save()
                return True
            return False

    def list_all(self) -> list[SourceRecord]:
        with _LOCK:
            return list(self._sources.values())

    def clear(self) -> None:
        with _LOCK:
            self._sources.clear()
            self._save()


# ============================================================================
# Universal Ingestion Engine
# ============================================================================

class UniversalIngestionEngine:
    """Master controller for universal multimodal ingestion and incremental synchronization."""

    def __init__(self, registry_path: Path | None = None):
        self.registry = IngestionRegistry(registry_path)
        self.pipeline = ExtractionPipeline()

    @staticmethod
    def compute_sha256(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()

    def ingest_file(
        self,
        file_path: str | Path,
        force_reindex: bool = False,
        allow_cloud: bool = True,
        bridge_to_rag: bool = True,
    ) -> ExtractedContent:
        """Ingest a single local file with incremental change detection and RAG bridging."""
        path = Path(file_path).expanduser().resolve()
        if not path.exists() or not path.is_file():
            source_id = f"file_{hashlib.sha256(str(path).encode()).hexdigest()[:16]}"
            return ExtractedContent(
                source_id=source_id,
                title=path.name,
                raw_text="",
                modality=Modality.UNKNOWN,
                mime_type="application/octet-stream",
                error=f"File not found: {path}",
            )

        source_id = f"file_{hashlib.sha256(str(path).encode()).hexdigest()[:16]}"
        stat = path.stat()
        mtime = stat.st_mtime
        size_bytes = stat.st_size

        # O(1) Fast-Path: Check existing completed record
        existing = self.registry.get(source_id)
        if existing and not force_reindex:
            if existing.status == IngestionStatus.COMPLETED.value:
                if existing.mtime == mtime and existing.size_bytes == size_bytes:
                    # File is identical; return skipped content without disk I/O
                    return ExtractedContent(
                        source_id=source_id,
                        title=path.name,
                        raw_text=f"[Unchanged source already indexed with {existing.chunk_count} chunk(s)]",
                        modality=Modality(existing.modality),
                        mime_type=existing.mime_type,
                        metadata={"status": "unchanged", "skipped": True},
                    )

        # Content sniffing and modality detection
        modality, mime_type = ModalityDetector.detect(path)

        # Mark in-progress
        rec = SourceRecord(
            source_id=source_id,
            uri=str(path),
            source_type=SourceType.FILE.value,
            modality=modality.value,
            mime_type=mime_type,
            size_bytes=size_bytes,
            content_hash="",
            mtime=mtime,
            status=IngestionStatus.PROCESSING.value,
        )
        self.registry.set(rec)

        # Execute extraction
        extracted = self.pipeline.extract(path, source_id, modality, mime_type)

        if not extracted.is_success and extracted.error:
            rec.status = IngestionStatus.FAILED.value
            rec.error = extracted.error
            self.registry.set(rec)
            return extracted

        # Compute cryptographic hash of content
        content_hash = self.compute_sha256(path)
        rec.content_hash = content_hash
        rec.chunk_count = len(extracted.chunks)
        rec.status = IngestionStatus.COMPLETED.value
        rec.error = None
        if extracted.provenance:
            extracted.provenance.checksum = content_hash
            extracted.provenance.allow_cloud = allow_cloud
            rec.provenance = extracted.provenance.to_dict()
        rec.metadata = extracted.metadata
        self.registry.set(rec)

        # Bridge chunks to RAG if requested
        if bridge_to_rag and extracted.chunks:
            self._bridge_chunks_to_rag(extracted)

        return extracted

    def ingest_directory(
        self,
        dir_path: str | Path,
        recursive: bool = True,
        max_files: int = 100,
        force_reindex: bool = False,
    ) -> dict[str, Any]:
        """Incrementally ingests an entire directory tree, skipping unchanged files."""
        root = Path(dir_path).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            return {"ok": False, "error": f"Directory not found: {root}"}

        valid, err_msg = SecurityGovernance.validate_path(root)
        if not valid:
            return {"ok": False, "error": err_msg}

        skip_dirs = {".git", "__pycache__", "node_modules", ".venv", "venv", "AMATYA"}
        files_to_process: list[Path] = []

        scanner = root.rglob("*") if recursive else root.glob("*")
        for p in scanner:
            if len(files_to_process) >= max_files:
                break
            if any(part in skip_dirs for part in p.parts):
                continue
            if p.is_file():
                files_to_process.append(p)

        results = {
            "total_files": len(files_to_process),
            "new": 0,
            "modified": 0,
            "unchanged": 0,
            "failed": 0,
            "chunks_created": 0,
        }

        for fp in files_to_process:
            sid = f"file_{hashlib.sha256(str(fp).encode()).hexdigest()[:16]}"
            prev = self.registry.get(sid)
            is_new = prev is None

            res = self.ingest_file(fp, force_reindex=force_reindex)
            if res.metadata.get("skipped"):
                results["unchanged"] += 1
            elif res.is_success:
                if is_new:
                    results["new"] += 1
                else:
                    results["modified"] += 1
                results["chunks_created"] += len(res.chunks)
            else:
                results["failed"] += 1

        return {"ok": True, "path": str(root), "stats": results}

    def ingest_text(
        self,
        text: str,
        title: str = "Untitled Note",
        source_id: str | None = None,
        tags: list[str] | None = None,
    ) -> ExtractedContent:
        """Ingests raw text or in-memory notes directly."""
        sid = source_id or f"text_{hashlib.sha256(text.encode()).hexdigest()[:16]}"
        chunks = self.pipeline.chunker.chunk(
            text,
            source_id=sid,
            modality=Modality.DOCUMENT.value,
            section=title,
            tags=tags or ["note"],
        )
        provenance = ProvenanceRecord(
            source_id=sid,
            extractor="DirectTextIngestion",
            confidence=1.0,
            checksum=hashlib.sha256(text.encode()).hexdigest(),
        )
        extracted = ExtractedContent(
            source_id=sid,
            title=title,
            raw_text=text,
            modality=Modality.DOCUMENT,
            mime_type="text/plain",
            chunks=chunks,
            provenance=provenance,
            metadata={"source_type": "text"},
        )
        rec = SourceRecord(
            source_id=sid,
            uri=f"memory://note/{title}",
            source_type=SourceType.TEXT.value,
            modality=Modality.DOCUMENT.value,
            mime_type="text/plain",
            size_bytes=len(text.encode("utf-8")),
            content_hash=provenance.checksum,
            mtime=time.time(),
            status=IngestionStatus.COMPLETED.value,
            chunk_count=len(chunks),
            provenance=provenance.to_dict(),
        )
        self.registry.set(rec)
        self._bridge_chunks_to_rag(extracted)
        return extracted

    def propagate_deletion(self, source_id: str) -> bool:
        """Removes a source from the registry and cascades deletion to the RAG index."""
        rec = self.registry.get(source_id)
        if not rec:
            return False

        # Cascade purge from RAG index
        try:
            from core.rag import get_knowledge_base
            kb = get_knowledge_base()
            kb.remove_source(source_id)
        except Exception:
            pass

        return self.registry.remove(source_id)

    def ingest_url(
        self,
        url: str,
        force_reindex: bool = False,
        bridge_to_rag: bool = True,
    ) -> ExtractedContent:
        """Ingests a web URL safely with SSRF protection."""
        source_id = f"url_{hashlib.sha256(url.encode()).hexdigest()[:16]}"
        existing = self.registry.get(source_id)
        if existing and not force_reindex:
            if existing.status == IngestionStatus.COMPLETED.value:
                if time.time() - existing.updated_at < 21600:
                    return ExtractedContent(
                        source_id=source_id,
                        title=url,
                        raw_text=f"[Unchanged web source already indexed with {existing.chunk_count} chunk(s)]",
                        modality=Modality.WEB,
                        mime_type="text/html",
                        metadata={"status": "unchanged", "skipped": True},
                    )

        rec = SourceRecord(
            source_id=source_id,
            uri=url,
            source_type=SourceType.URL.value,
            modality=Modality.WEB.value,
            mime_type="text/html",
            size_bytes=0,
            content_hash="",
            mtime=time.time(),
            status=IngestionStatus.PROCESSING.value,
        )
        self.registry.set(rec)

        extracted = self.pipeline.extract_url(url, source_id)
        if not extracted.is_success and extracted.error:
            rec.status = IngestionStatus.FAILED.value
            rec.error = extracted.error
            self.registry.set(rec)
            return extracted

        rec.content_hash = extracted.provenance.checksum if extracted.provenance else ""
        rec.chunk_count = len(extracted.chunks)
        rec.status = IngestionStatus.COMPLETED.value
        rec.size_bytes = extracted.metadata.get("content_length", len(extracted.raw_text.encode("utf-8")))
        if extracted.provenance:
            rec.provenance = extracted.provenance.to_dict()
        rec.metadata = extracted.metadata
        self.registry.set(rec)

        if bridge_to_rag and extracted.chunks:
            self._bridge_chunks_to_rag(extracted)

        return extracted

    def check_incremental(self, file_paths: list[str | Path]) -> dict[str, list[str]]:
        """Previews incremental changes without modifying index: classifies into new, modified, unchanged."""
        categorized: dict[str, list[str]] = {"new": [], "modified": [], "unchanged": []}
        for fp in file_paths:
            path = Path(fp).expanduser().resolve()
            if not path.exists() or not path.is_file():
                continue
            sid = f"file_{hashlib.sha256(str(path).encode()).hexdigest()[:16]}"
            rec = self.registry.get(sid)
            if not rec:
                categorized["new"].append(str(path))
            else:
                stat = path.stat()
                if rec.status == IngestionStatus.COMPLETED.value and rec.mtime == stat.st_mtime and rec.size_bytes == stat.st_size:
                    categorized["unchanged"].append(str(path))
                else:
                    categorized["modified"].append(str(path))
        return categorized

    def get_stats(self) -> dict[str, Any]:
        """Returns aggregate statistics across all registered ingestion sources."""
        sources = self.registry.list_all()
        by_modality: dict[str, int] = {}
        by_status: dict[str, int] = {}
        total_chunks = 0
        total_bytes = 0

        for s in sources:
            by_modality[s.modality] = by_modality.get(s.modality, 0) + 1
            by_status[s.status] = by_status.get(s.status, 0) + 1
            total_chunks += s.chunk_count
            total_bytes += s.size_bytes

        return {
            "total_sources": len(sources),
            "by_modality": by_modality,
            "by_status": by_status,
            "total_chunks": total_chunks,
            "total_bytes": total_bytes,
        }

    def _bridge_chunks_to_rag(self, extracted: ExtractedContent) -> None:
        """Bridges extracted chunks into the local hybrid RAG index."""
        try:
            from core.rag import get_knowledge_base
            kb = get_knowledge_base()
            kb.index_text(
                source_id=extracted.source_id,
                text=extracted.raw_text,
                title=extracted.title,
                tags=[extracted.modality.value],
            )
        except Exception:
            pass


# Singleton accessor
_ENGINE: UniversalIngestionEngine | None = None

def get_ingestion_engine() -> UniversalIngestionEngine:
    global _ENGINE
    with _LOCK:
        if _ENGINE is None:
            _ENGINE = UniversalIngestionEngine()
        return _ENGINE
