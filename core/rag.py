"""
AMATYA Local Knowledge Base & Hybrid Semantic RAG Engine (core/rag.py)
======================================================================
Implements Section 6.2 (Semantic memory and RAG) and Section 6.3 (User control):
  - Indexes project files, Markdown, source code, PDFs, DOCX, notes, and task summaries.
  - Redacts secrets/credentials automatically before indexing.
  - Hybrid retrieval combining 128-D embedding cosine similarity (via ModelRouter.embed)
    and BM25-inspired lexical term scoring.
  - Full user control: inspect indexed sources, remove sources, export or clear index.
"""
from __future__ import annotations

import json
import math
import re
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np

from core.model_router import get_router
from core.security import redact_secrets
from memory.config_manager import BASE_DIR

KNOWLEDGE_INDEX_PATH = BASE_DIR / "memory" / "knowledge_index.json"
_LOCK = threading.RLock()

_TEXT_EXTENSIONS = {
    ".md", ".txt", ".rst", ".py", ".js", ".ts", ".tsx", ".jsx", ".json",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".sh", ".html", ".css",
    ".c", ".cpp", ".h", ".rs", ".go", ".java", ".sql",
}
_SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", "AMATYA",
    ".mypy_cache", ".pytest_cache", "dist", "build",
}


def _extract_file_text(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        try:
            import pdfplumber
            pages = []
            with pdfplumber.open(str(file_path)) as pdf:
                for p in pdf.pages[:50]:
                    t = p.extract_text()
                    if t:
                        pages.append(t)
            return "\n\n".join(pages)
        except Exception:
            try:
                from PyPDF2 import PdfReader
                reader = PdfReader(str(file_path))
                return "\n\n".join((p.extract_text() or "") for p in reader.pages[:50])
            except Exception as exc:
                return f"[PDF extraction error: {exc}]"

    if suffix == ".docx":
        try:
            import docx
            doc = docx.Document(str(file_path))
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except Exception as exc:
            return f"[DOCX extraction error: {exc}]"

    try:
        return file_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _chunk_text(text: str, chunk_chars: int = 900, overlap_chars: int = 150) -> list[str]:
    clean = redact_secrets((text or "").strip())
    if not clean:
        return []
    if len(clean) <= chunk_chars:
        return [clean]
    chunks: list[str] = []
    start = 0
    n = len(clean)
    while start < n:
        end = min(n, start + chunk_chars)
        # Prefer breaking on paragraph or newline boundary
        if end < n:
            nl = clean.rfind("\n", start + chunk_chars // 2, end)
            if nl != -1:
                end = nl
        piece = clean[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= n:
            break
        start = max(start + 1, end - overlap_chars)
    return chunks


class LocalKnowledgeBase:
    """Persistent hybrid vector + lexical RAG store for AMATYA."""

    def __init__(self, index_path: Path | None = None) -> None:
        self._path = index_path or KNOWLEDGE_INDEX_PATH
        self._router = get_router()

    def _load(self) -> dict[str, Any]:
        with _LOCK:
            if not self._path.exists():
                return {"sources": {}, "chunks": []}
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "chunks" in data:
                    data.setdefault("sources", {})
                    return data
            except Exception:
                pass
            return {"sources": {}, "chunks": []}

    def _save(self, data: dict[str, Any]) -> None:
        with _LOCK:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    def index_text(
        self,
        source_id: str,
        text: str,
        title: str = "",
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Index raw text or a note under `source_id`."""
        chunks = _chunk_text(text)
        if not chunks:
            return {"ok": False, "error": "No indexable text content found."}

        with _LOCK:
            data = self._load()
            # Remove any old chunks from the same source_id
            data["chunks"] = [c for c in data["chunks"] if c.get("source_id") != source_id]

            now_iso = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            for idx, ch in enumerate(chunks):
                emb = self._router.embed(ch)
                data["chunks"].append({
                    "source_id": source_id,
                    "title": title or source_id,
                    "chunk_index": idx,
                    "text": ch,
                    "tags": tags or [],
                    "embedding": emb,
                    "updated_at": now_iso,
                })

            data["sources"][source_id] = {
                "title": title or source_id,
                "chunk_count": len(chunks),
                "tags": tags or [],
                "updated_at": now_iso,
            }
            self._save(data)

        return {
            "ok": True,
            "source_id": source_id,
            "title": title or source_id,
            "chunk_count": len(chunks),
        }

    def index_path(
        self,
        target_path: str | Path,
        max_files: int = 40,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Index a single document/file or recursively index a project directory."""
        p = Path(target_path).expanduser().resolve()
        if not p.exists():
            return {"ok": False, "error": f"Path not found: {p}"}

        files_to_index: list[Path] = []
        if p.is_file():
            files_to_index.append(p)
        else:
            for item in sorted(p.rglob("*")):
                if len(files_to_index) >= max_files:
                    break
                if any(part in _SKIP_DIRS for part in item.parts):
                    continue
                if item.is_file() and (
                    item.suffix.lower() in _TEXT_EXTENSIONS
                    or item.suffix.lower() in (".pdf", ".docx")
                ):
                    if item.stat().st_size <= 2 * 1024 * 1024:  # <= 2 MB
                        files_to_index.append(item)

        indexed_files = 0
        total_chunks = 0
        for fp in files_to_index:
            txt = _extract_file_text(fp)
            if not txt.strip():
                continue
            res = self.index_text(
                source_id=str(fp),
                text=txt,
                title=fp.name,
                tags=tags or [fp.suffix.lstrip(".") or "file"],
            )
            if res.get("ok"):
                indexed_files += 1
                total_chunks += int(res.get("chunk_count", 0))

        return {
            "ok": indexed_files > 0,
            "path": str(p),
            "indexed_files": indexed_files,
            "total_chunks": total_chunks,
        }

    def query(self, query_text: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Hybrid semantic + lexical retrieval over indexed knowledge chunks."""
        q_clean = (query_text or "").strip()
        if not q_clean:
            return []

        data = self._load()
        chunks = data.get("chunks", [])
        if not chunks:
            return []

        q_emb = np.asarray(self._router.embed(q_clean), dtype=np.float32)
        q_words = [w for w in re.findall(r"[a-z0-9_]{2,}", q_clean.lower())]

        scored: list[tuple[float, dict[str, Any]]] = []
        for ch in chunks:
            c_emb = np.asarray(ch.get("embedding", []), dtype=np.float32)
            if c_emb.shape == q_emb.shape and c_emb.size > 0:
                sem_score = float(np.dot(q_emb, c_emb))
            else:
                sem_score = 0.0

            txt_lower = str(ch.get("text", "")).lower()
            title_lower = str(ch.get("title", "")).lower()
            lex_hits = 0.0
            for w in q_words:
                if w in title_lower:
                    lex_hits += 2.0
                if w in txt_lower:
                    lex_hits += 1.0
            lex_score = min(1.0, lex_hits / max(1.0, len(q_words) * 1.5))

            combined = 0.60 * max(0.0, sem_score) + 0.40 * lex_score
            if combined > 0.05:
                scored.append((
                    combined,
                    {
                        "source_id": ch.get("source_id"),
                        "title": ch.get("title"),
                        "chunk_index": ch.get("chunk_index"),
                        "score": round(combined, 4),
                        "text": ch.get("text"),
                        "tags": ch.get("tags", []),
                        "updated_at": ch.get("updated_at"),
                    },
                ))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in scored[: max(1, int(top_k))]]

    def list_sources(self) -> dict[str, Any]:
        data = self._load()
        return {
            "total_sources": len(data.get("sources", {})),
            "total_chunks": len(data.get("chunks", [])),
            "sources": data.get("sources", {}),
        }

    def remove_source(self, source_id: str) -> tuple[bool, str]:
        with _LOCK:
            data = self._load()
            if source_id not in data.get("sources", {}):
                # Also allow matching by basename
                matches = [
                    k for k in data.get("sources", {})
                    if Path(k).name == source_id or k == source_id
                ]
                if not matches:
                    return False, f"Source '{source_id}' not found in knowledge index."
                source_id = matches[0]

            data["sources"].pop(source_id, None)
            before = len(data.get("chunks", []))
            data["chunks"] = [c for c in data.get("chunks", []) if c.get("source_id") != source_id]
            removed = before - len(data["chunks"])
            self._save(data)
            return True, f"Removed source '{source_id}' ({removed} chunks deleted)."

    def clear_all(self) -> str:
        self._save({"sources": {}, "chunks": []})
        return "Cleared entire RAG knowledge index."


_KB_INSTANCE: LocalKnowledgeBase | None = None


def get_knowledge_base() -> LocalKnowledgeBase:
    global _KB_INSTANCE
    if _KB_INSTANCE is None:
        _KB_INSTANCE = LocalKnowledgeBase()
    return _KB_INSTANCE

