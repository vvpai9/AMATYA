"""
actions/knowledge_base.py — Semantic RAG Knowledge Base & Memory Controls for AMATYA.
"""
from __future__ import annotations

from typing import Any

from core import outcome
from core.rag import get_knowledge_base
from memory.memory_manager import (
    all_entries_for_ui,
    clear_category,
    export_memory,
    forget,
    remember,
    search_memory,
)

SKILL_METADATA = {
    "name": "knowledge_base",
    "version": "1.0.0",
    "description": "Index local documents/projects into AMATYA's semantic RAG store, query knowledge, and manage/export long-term memory.",
    "capabilities": ["rag_indexing", "semantic_search", "memory_management", "memory_export"],
    "permissions": ["file_read", "memory_write"],
    "dependencies": ["numpy"],
    "supported_actions": [
        "query",
        "index_path",
        "index_note",
        "list_sources",
        "remove_source",
        "clear_index",
        "export_memory",
        "list_memory",
        "delete_memory",
        "clear_memory_category",
    ],
    "security_level": "normal",
}

TOOL = {
    "name": "knowledge_base",
    "description": (
        "Index and search local documents, project repositories, PDFs, DOCX, "
        "and notes using AMATYA's local semantic RAG knowledge base, or inspect/"
        "export/delete long-term memory. Actions: 'query', 'index_path', "
        "'index_note', 'list_sources', 'remove_source', 'clear_index', "
        "'export_memory', 'list_memory', 'delete_memory', 'clear_memory_category'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "Action: 'query', 'index_path', 'index_note', 'list_sources', "
                    "'remove_source', 'clear_index', 'export_memory', 'list_memory', "
                    "'delete_memory', 'clear_memory_category'."
                ),
            },
            "query": {
                "type": "STRING",
                "description": "Search query for 'query' action.",
            },
            "path": {
                "type": "STRING",
                "description": "File or directory path for 'index_path' or 'export_memory'.",
            },
            "source_id": {
                "type": "STRING",
                "description": "Source identifier for 'index_note' or 'remove_source'.",
            },
            "title": {
                "type": "STRING",
                "description": "Document or note title for 'index_note'.",
            },
            "text": {
                "type": "STRING",
                "description": "Text content for 'index_note'.",
            },
            "top_k": {
                "type": "INTEGER",
                "description": "Number of RAG chunks to retrieve (default 5).",
            },
            "category": {
                "type": "STRING",
                "description": "Memory category ('identity', 'preferences', 'projects', 'relationships', 'wishes', 'notes').",
            },
            "key": {
                "type": "STRING",
                "description": "Memory key for 'delete_memory'.",
            },
        },
        "required": ["action"],
    },
}


def execute(
    parameters: dict[str, Any],
    response=None,
    player=None,
    session_memory=None,
) -> Any:
    action = str(parameters.get("action", "query") or "query").strip().lower()
    kb = get_knowledge_base()

    if action == "query":
        q = str(parameters.get("query", "") or "").strip()
        if not q:
            return outcome.failed("Please provide a 'query' string.")
        top_k = int(parameters.get("top_k", 5) or 5)
        hits = kb.query(q, top_k=top_k)
        mem_hits = search_memory(q, limit=5)
        if not hits and "Nothing stored" in mem_hits:
            return outcome.done(f"No matching knowledge or memory found for '{q}'.", data={"rag_hits": []})
        lines = []
        for idx, h in enumerate(hits, 1):
            lines.append(
                f"[{idx}] {h['title']} (score={h['score']}):\n{h['text'][:360]}"
            )
        rag_block = "\n\n".join(lines) if lines else "No indexed document chunks matched."
        return outcome.done(
            f"Knowledge Base Results for '{q}':\n{rag_block}\n\nLong-Term Memory:\n{mem_hits}",
            data={"rag_hits": hits, "memory_summary": mem_hits},
        )

    if action == "index_path":
        path = str(parameters.get("path", "") or "").strip()
        if not path:
            return outcome.failed("Please specify 'path' to index.")
        res = kb.index_path(path)
        if not res.get("ok"):
            return outcome.failed(res.get("error", f"No indexable files found in {path}."), data=res)
        return outcome.done(
            f"Indexed {res['indexed_files']} file(s) ({res['total_chunks']} chunks) from '{res['path']}'.",
            data=res,
        )

    if action == "index_note":
        sid = str(parameters.get("source_id") or parameters.get("title") or "note").strip()
        title = str(parameters.get("title") or sid).strip()
        text = str(parameters.get("text", "") or "").strip()
        res = kb.index_text(source_id=sid, text=text, title=title)
        if not res.get("ok"):
            return outcome.failed(res.get("error", "Failed to index note."), data=res)
        return outcome.done(
            f"Indexed note '{title}' ({res['chunk_count']} chunk(s)).",
            data=res,
        )

    if action == "list_sources":
        info = kb.list_sources()
        return outcome.done(
            f"Knowledge Base contains {info['total_sources']} source(s) and {info['total_chunks']} chunk(s).",
            data=info,
        )

    if action == "remove_source":
        sid = str(parameters.get("source_id", "") or "").strip()
        if not sid:
            return outcome.failed("Please specify 'source_id' to remove.")
        ok, msg = kb.remove_source(sid)
        return outcome.done(msg) if ok else outcome.failed(msg)

    if action == "clear_index":
        msg = kb.clear_all()
        return outcome.done(msg)

    if action == "export_memory":
        path = parameters.get("path")
        ok, msg = export_memory(path)
        return outcome.done(f"Memory exported to {msg}.") if ok else outcome.failed(msg)

    if action == "list_memory":
        entries = all_entries_for_ui()
        return outcome.done(
            f"Long-term memory has {len(entries)} stored item(s).",
            data={"entries": entries},
        )

    if action == "delete_memory":
        cat = str(parameters.get("category", "notes") or "notes").strip()
        key = str(parameters.get("key", "") or "").strip()
        if not key:
            return outcome.failed("Please provide 'key' (and optional 'category') to delete.")
        msg = forget(key, cat)
        return outcome.done(msg)

    if action == "clear_memory_category":
        cat = str(parameters.get("category", "") or "").strip()
        msg = clear_category(cat)
        return outcome.done(msg)

    return outcome.failed(f"Unknown knowledge_base action '{action}'.")

