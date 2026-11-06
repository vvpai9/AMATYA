"""
actions/knowledge_base.py — Semantic RAG Knowledge Base & Memory Controls for AMATYA.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from core import outcome
from core.ingestion import get_ingestion_engine, Modality, SourceType
from core.memory_engine import get_memory_engine
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
    "version": "13.2.0",
    "description": "Universal Multimodal Ingestion, semantic RAG knowledge base, and layered persistent memory management for AMATYA.",
    "capabilities": [
        "universal_ingestion",
        "multimodal_extraction",
        "incremental_sync",
        "rag_indexing",
        "semantic_search",
        "memory_management",
        "memory_export",
        "layered_memory",
        "contradiction_detection",
    ],
    "permissions": ["file_read", "memory_write"],
    "dependencies": ["numpy"],
    "supported_actions": [
        "query",
        "ingest",
        "ingestion_status",
        "sync_incremental",
        "index_path",
        "index_note",
        "list_sources",
        "remove_source",
        "clear_index",
        "export_memory",
        "list_memory",
        "delete_memory",
        "clear_memory_category",
        "store_fact",
        "correct_fact",
        "search_memories",
        "toggle_memory",
    ],
    "security_level": "normal",
}

TOOL = {
    "name": "knowledge_base",
    "description": (
        "Universal multimodal ingestion and search across local documents (PDF, DOCX, XLSX, PPTX, CSV), "
        "code, web URLs, images, audio/video, and notes using AMATYA's Phase 13 Ingestion Framework and RAG store, "
        "or inspect/export/delete/correct layered personal memory. Actions: 'query', 'ingest', 'ingestion_status', "
        "'sync_incremental', 'index_path', 'index_note', 'list_sources', 'remove_source', 'clear_index', "
        "'export_memory', 'list_memory', 'delete_memory', 'clear_memory_category', "
        "'store_fact', 'correct_fact', 'search_memories', 'toggle_memory'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "Action: 'query', 'ingest', 'ingestion_status', 'sync_incremental', "
                    "'index_path', 'index_note', 'list_sources', 'remove_source', 'clear_index', "
                    "'export_memory', 'list_memory', 'delete_memory', 'clear_memory_category', "
                    "'store_fact', 'correct_fact', 'search_memories', 'toggle_memory'."
                ),
            },
            "query": {
                "type": "STRING",
                "description": "Search query for 'query' or 'search_memories' action.",
            },
            "path": {
                "type": "STRING",
                "description": "File or directory path for 'ingest', 'sync_incremental', 'index_path', or 'export_memory'.",
            },
            "url": {
                "type": "STRING",
                "description": "Web URL to safely ingest for 'ingest' action.",
            },
            "source_id": {
                "type": "STRING",
                "description": "Source identifier for 'index_note', 'remove_source', or 'ingestion_status'.",
            },
            "title": {
                "type": "STRING",
                "description": "Document or note title for 'index_note' or 'ingest'.",
            },
            "text": {
                "type": "STRING",
                "description": "Text content for 'index_note' or raw text 'ingest'.",
            },
            "force_reindex": {
                "type": "BOOLEAN",
                "description": "Force re-extraction and indexing even if unchanged.",
            },
            "preview": {
                "type": "BOOLEAN",
                "description": "Preview incremental changes (new, modified, unchanged) without indexing.",
            },
            "top_k": {
                "type": "INTEGER",
                "description": "Number of RAG chunks or memory results to retrieve (default 5).",
            },
            "category": {
                "type": "STRING",
                "description": "Memory category ('identity', 'preferences', 'projects', 'relationships', 'wishes', 'notes').",
            },
            "key": {
                "type": "STRING",
                "description": "Memory key for 'delete_memory', 'store_fact', or 'correct_fact'.",
            },
            "value": {
                "type": "STRING",
                "description": "Memory value for 'store_fact' or 'correct_fact'.",
            },
            "provenance": {
                "type": "STRING",
                "description": "Provenance for 'store_fact' ('user_stated', 'observed', 'inferred').",
            },
            "enabled": {
                "type": "BOOLEAN",
                "description": "Whether memory retention is enabled (for 'toggle_memory').",
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
            return outcome.failed("knowledge_base", "Please provide a 'query' string.")
        top_k = int(parameters.get("top_k", 5) or 5)
        hits = kb.query(q, top_k=top_k)
        mem_hits = search_memory(q, limit=5)
        if not hits and "Nothing stored" in mem_hits:
            return outcome.done("knowledge_base", result=f"No matching knowledge or memory found for '{q}'.", data={"rag_hits": []})
        lines = []
        for idx, h in enumerate(hits, 1):
            lines.append(
                f"[{idx}] {h['title']} (score={h['score']}):\n{h['text'][:360]}"
            )
        rag_block = "\n\n".join(lines) if lines else "No indexed document chunks matched."
        return outcome.done(
            "knowledge_base",
            result=f"Knowledge Base Results for '{q}':\n{rag_block}\n\nLong-Term Memory:\n{mem_hits}",
            data={"rag_hits": hits, "memory_summary": mem_hits},
        )

    engine = get_ingestion_engine()

    if action == "ingest":
        path_str = str(parameters.get("path", "") or "").strip()
        url_str = str(parameters.get("url", "") or "").strip()
        text_str = str(parameters.get("text", "") or "").strip()
        title_str = str(parameters.get("title", "") or "").strip()
        force_reindex = bool(parameters.get("force_reindex", False))

        if url_str:
            res = engine.ingest_url(url_str, force_reindex=force_reindex)
            if not res.is_success and res.error:
                return outcome.failed("knowledge_base", f"Failed to ingest URL: {res.error}")
            return outcome.done(
                "knowledge_base",
                result=f"Successfully ingested URL '{res.title}' ({len(res.chunks)} chunk(s)).",
                data={"source_id": res.source_id, "chunks": len(res.chunks), "metadata": res.metadata},
            )

        if text_str:
            res = engine.ingest_text(text_str, title=title_str or "Untitled Note")
            return outcome.done(
                "knowledge_base",
                result=f"Successfully ingested note '{res.title}' ({len(res.chunks)} chunk(s)).",
                data={"source_id": res.source_id, "chunks": len(res.chunks)},
            )

        if path_str:
            p = Path(path_str).expanduser().resolve()
            if not p.exists():
                return outcome.failed("knowledge_base", f"Path not found: {p}")
            if p.is_file():
                res = engine.ingest_file(p, force_reindex=force_reindex)
                if not res.is_success and res.error:
                    return outcome.failed("knowledge_base", f"Failed to ingest file: {res.error}")
                skipped = res.metadata.get("skipped", False)
                msg = f"Source '{p.name}' unchanged, skipped re-indexing." if skipped else f"Successfully ingested file '{p.name}' ({len(res.chunks)} chunk(s), modality={res.modality.value})."
                return outcome.done(
                    "knowledge_base",
                    result=msg,
                    data={"source_id": res.source_id, "chunks": len(res.chunks), "modality": res.modality.value, "metadata": res.metadata},
                )
            else:
                dir_res = engine.ingest_directory(p, force_reindex=force_reindex)
                if not dir_res.get("ok"):
                    return outcome.failed("knowledge_base", dir_res.get("error", "Failed to ingest directory."))
                stats = dir_res["stats"]
                summary = f"Directory '{p.name}' ingested: {stats['new']} new, {stats['modified']} modified, {stats['unchanged']} unchanged ({stats['chunks_created']} chunks)."
                return outcome.done("knowledge_base", result=summary, data=dir_res)

        return outcome.failed("knowledge_base", "Please provide 'path', 'url', or 'text' to ingest.")

    if action == "ingestion_status":
        sid = str(parameters.get("source_id", "") or "").strip()
        if sid:
            rec = engine.registry.get(sid)
            if not rec:
                return outcome.failed("knowledge_base", f"No ingestion record found for source '{sid}'.")
            return outcome.done(
                "knowledge_base",
                result=f"Source [{rec.source_id}] {rec.uri}: Status={rec.status}, Modality={rec.modality}, Chunks={rec.chunk_count}.",
                data=rec.to_dict(),
            )
        stats = engine.get_stats()
        summary = (
            f"Ingestion Registry: {stats['total_sources']} total sources, {stats['total_chunks']} chunks, "
            f"{stats['total_bytes']} bytes. Modalities: {stats['by_modality']}. Status: {stats['by_status']}."
        )
        return outcome.done("knowledge_base", result=summary, data=stats)

    if action == "sync_incremental":
        path_str = str(parameters.get("path", "") or "").strip()
        if not path_str:
            return outcome.failed("knowledge_base", "Please specify 'path' for incremental sync.")
        p = Path(path_str).expanduser().resolve()
        if not p.exists():
            return outcome.failed("knowledge_base", f"Path not found: {p}")

        preview = bool(parameters.get("preview", False))
        if preview:
            files = [item for item in p.rglob("*") if item.is_file()][:100] if p.is_dir() else [p]
            categorized = engine.check_incremental(files)
            summary = f"Incremental preview for '{p.name}': {len(categorized['new'])} new, {len(categorized['modified'])} modified, {len(categorized['unchanged'])} unchanged."
            return outcome.done("knowledge_base", result=summary, data=categorized)

        if p.is_dir():
            res = engine.ingest_directory(p, recursive=True)
            stats = res.get("stats", {})
            summary = f"Incremental sync for '{p.name}': {stats.get('new', 0)} new, {stats.get('modified', 0)} modified, {stats.get('unchanged', 0)} unchanged."
            return outcome.done("knowledge_base", result=summary, data=res)
        else:
            res = engine.ingest_file(p)
            skipped = res.metadata.get("skipped", False)
            msg = f"Incremental sync for '{p.name}': File was unchanged." if skipped else f"Incremental sync for '{p.name}': Ingested {len(res.chunks)} chunks."
            return outcome.done("knowledge_base", result=msg, data={"chunks": len(res.chunks), "skipped": skipped})

    if action == "index_path":
        path = str(parameters.get("path", "") or "").strip()
        if not path:
            return outcome.failed("knowledge_base", "Please specify 'path' to index.")
        res = kb.index_path(path)
        if not res.get("ok"):
            return outcome.failed("knowledge_base", res.get("error", f"No indexable files found in {path}."), data=res)
        return outcome.done(
            "knowledge_base",
            result=f"Indexed {res['indexed_files']} file(s) ({res['total_chunks']} chunks) from '{res['path']}'.",
            data=res,
        )

    if action == "index_note":
        sid = str(parameters.get("source_id") or parameters.get("title") or "note").strip()
        title = str(parameters.get("title") or sid).strip()
        text = str(parameters.get("text", "") or "").strip()
        res = kb.index_text(source_id=sid, text=text, title=title)
        if not res.get("ok"):
            return outcome.failed("knowledge_base", res.get("error", "Failed to index note."), data=res)
        return outcome.done(
            "knowledge_base",
            result=f"Indexed note '{title}' ({res['chunk_count']} chunk(s)).",
            data=res,
        )

    if action == "list_sources":
        info = kb.list_sources()
        return outcome.done(
            "knowledge_base",
            result=f"Knowledge Base contains {info['total_sources']} source(s) and {info['total_chunks']} chunk(s).",
            data=info,
        )

    if action == "remove_source":
        sid = str(parameters.get("source_id", "") or "").strip()
        if not sid:
            return outcome.failed("knowledge_base", "Please specify 'source_id' to remove.")
        engine.propagate_deletion(sid)
        ok, msg = kb.remove_source(sid)
        return outcome.done("knowledge_base", result=msg) if ok else outcome.failed("knowledge_base", msg)

    if action == "clear_index":
        msg = kb.clear_all()
        return outcome.done("knowledge_base", result=msg)

    if action == "export_memory":
        path = parameters.get("path")
        ok, msg = export_memory(path)
        return outcome.done("knowledge_base", result=f"Memory exported to {msg}.") if ok else outcome.failed("knowledge_base", msg)

    mem_engine = get_memory_engine()

    if action == "list_memory":
        entries = all_entries_for_ui()
        memories = mem_engine.list_all_memories()
        return outcome.done(
            "knowledge_base",
            result=f"Layered memory has {len(memories)} semantic item(s) and {len(entries)} legacy item(s).",
            data={"entries": entries, "semantic_memories": memories, "memory_enabled": mem_engine.is_enabled()},
        )

    if action == "delete_memory":
        cat = str(parameters.get("category", "notes") or "notes").strip()
        key = str(parameters.get("key", "") or "").strip()
        if not key:
            return outcome.failed("knowledge_base", "Please provide 'key' (and optional 'category') to delete.")
        msg = forget(key, cat)
        mem_engine.delete_memory(key)
        return outcome.done("knowledge_base", result=f"{msg} (Purged from semantic and long-term stores).")

    if action == "store_fact":
        key = str(parameters.get("key", "") or "").strip()
        val = str(parameters.get("value", "") or parameters.get("text", "") or "").strip()
        cat = str(parameters.get("category", "notes") or "notes").strip()
        provenance = str(parameters.get("provenance", "user_stated") or "user_stated").strip()
        if not key or not val:
            return outcome.failed("knowledge_base", "Both 'key' and 'value' are required to store a fact.")
        res = mem_engine.store_fact(key=key, value=val, category=cat, provenance=provenance)
        if not res.get("ok"):
            return outcome.failed("knowledge_base", res.get("message", "Failed to store fact."))
        return outcome.done("knowledge_base", result=res["message"], data=res)

    if action == "correct_fact":
        key = str(parameters.get("key", "") or "").strip()
        val = str(parameters.get("value", "") or parameters.get("text", "") or "").strip()
        reason = str(parameters.get("reason", "user_correction") or "user_correction").strip()
        if not key or not val:
            return outcome.failed("knowledge_base", "Both 'key' and 'value' are required to correct a fact.")
        res = mem_engine.correct_fact(key=key, new_value=val, reason=reason)
        if not res.get("ok"):
            return outcome.failed("knowledge_base", res.get("message", "Failed to correct fact."))
        return outcome.done("knowledge_base", result=res["message"], data=res)

    if action == "search_memories":
        q = str(parameters.get("query", "") or "").strip()
        if not q:
            return outcome.failed("knowledge_base", "Please provide a 'query' to search memories.")
        top_k = int(parameters.get("top_k") or parameters.get("limit") or 5)
        results = mem_engine.search_memories(q, limit=top_k, top_k=top_k)
        if not results:
            return outcome.done("knowledge_base", result=f"No matching memories found for '{q}'.", data={"memories": []})
        summary_lines = [f"- [{m.category}] {m.key}: {m.value} (conf={m.confidence:.2f})" for m in results]
        return outcome.done(
            "knowledge_base",
            result=f"Found {len(results)} memory match(es) for '{q}':\n" + "\n".join(summary_lines),
            data={"memories": [m.to_dict() if hasattr(m, "to_dict") else dict(m) for m in results]},
        )

    if action == "toggle_memory":
        enabled = parameters.get("enabled")
        if enabled is None:
            status_str = "enabled" if mem_engine.is_enabled() else "disabled"
            return outcome.done("knowledge_base", result=f"Memory engine is currently {status_str}.")
        mem_engine.set_enabled(bool(enabled))
        new_status = "enabled" if mem_engine.is_enabled() else "disabled"
        return outcome.done("knowledge_base", result=f"Memory engine has been {new_status}.")

    if action == "clear_memory_category":
        cat = str(parameters.get("category", "") or "").strip()
        msg = clear_category(cat)
        return outcome.done("knowledge_base", result=msg)

    return outcome.failed("knowledge_base", f"Unknown knowledge_base action '{action}'.")

