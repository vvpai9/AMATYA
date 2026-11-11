"""
actions/knowledge_base.py — Semantic RAG Knowledge Base & Memory Controls for AMATYA.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from core import outcome
from core.creator_knowledge import get_creator_knowledge_manager
from core.document_intelligence import (
    DocumentParser,
    DocumentReasoningEngine,
    export_table_csv,
    export_tables_xlsx,
    resolve_user_path,
    resolve_user_output_path,
)
from core.ingestion import get_ingestion_engine, Modality, SourceType
from core.knowledge_graph import EntityType, RelationType, get_knowledge_graph
from core.live_monitor import get_live_monitor
from core.media_intelligence import MediaIntelligenceEngine
from core.memory_engine import get_memory_engine
from core.rag import get_knowledge_base
from core.research_engine import get_research_engine
from core.universal_search import get_search_engine
from core.visual_intelligence import VisualIntelligenceEngine
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
        "document_intelligence",
        "table_extraction",
        "cross_document_comparison",
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
        "parse_document",
        "extract_tables",
        "compare_documents",
        "document_summary",
        "find_section",
        "visual_analyze",
        "visual_verify",
        "analyze_audio",
        "analyze_video",
        "graph_query",
        "graph_stats",
        "conduct_research",
        "manage_space",
        "live_monitor",
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
        "Universal multimodal ingestion, document intelligence (tables, headings, comparisons, summaries), "
        "and search across local documents (PDF, DOCX, XLSX, PPTX, CSV), code, web URLs, images, and notes "
        "using AMATYA's Phase 13 Ingestion & Document Intelligence Engines. Actions: 'query', 'ingest', "
        "'ingestion_status', 'sync_incremental', 'parse_document', 'extract_tables', 'compare_documents', "
        "'document_summary', 'find_section', 'index_path', 'index_note', 'list_sources', 'remove_source', "
        "'clear_index', 'export_memory', 'list_memory', 'delete_memory', 'clear_memory_category', "
        "'store_fact', 'correct_fact', 'search_memories', 'toggle_memory'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "Action: 'query', 'ingest', 'ingestion_status', 'sync_incremental', "
                    "'parse_document', 'extract_tables', 'compare_documents', 'document_summary', 'find_section', "
                    "'index_path', 'index_note', 'list_sources', 'remove_source', 'clear_index', "
                    "'export_memory', 'list_memory', 'delete_memory', 'clear_memory_category', "
                    "'store_fact', 'correct_fact', 'search_memories', 'toggle_memory'."
                ),
            },
            "query": {
                "type": "STRING",
                "description": "Search query for 'query', 'find_section', or 'search_memories' action.",
            },
            "path": {
                "type": "STRING",
                "description": "File or directory path for 'ingest', 'sync_incremental', 'parse_document', 'extract_tables', 'compare_documents', 'document_summary', 'find_section', 'index_path', or 'export_memory'.",
            },
            "path_b": {
                "type": "STRING",
                "description": "Second document path for 'compare_documents' action.",
            },
            "output_path": {
                "type": "STRING",
                "description": "Optional file path to export tables (.csv or .xlsx) in 'extract_tables'.",
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

    if action == "parse_document":
        path_str = str(parameters.get("path", "") or "").strip()
        if not path_str:
            return outcome.failed("knowledge_base", "Please specify 'path' to parse.")
        parsed = DocumentParser.parse(path_str)
        if parsed.error:
            return outcome.failed("knowledge_base", parsed.error)
        summary = (
            f"Parsed '{parsed.title}': {parsed.page_count} page(s), {len(parsed.headings)} heading(s), "
            f"{len(parsed.tables)} table(s), {len(parsed.figures)} figure(s), {len(parsed.references)} reference(s)."
        )
        return outcome.done("knowledge_base", result=summary, data=parsed.to_dict())

    if action == "extract_tables":
        path_str = str(parameters.get("path", "") or "").strip()
        if not path_str:
            return outcome.failed("knowledge_base", "Please specify 'path' to extract tables from.")
        parsed = DocumentParser.parse(path_str)
        if parsed.error:
            return outcome.failed("knowledge_base", parsed.error)
        if not parsed.tables:
            return outcome.done("knowledge_base", result=f"No structured tables found in '{parsed.title}'.", data={"tables": []})

        out_path = parameters.get("output_path")
        exported_msg = ""
        if out_path:
            out_p = resolve_user_output_path(out_path)
            if out_p.suffix.lower() == ".csv":
                if parsed.tables:
                    export_table_csv(parsed.tables[0], out_p)
                    exported_msg = f" Exported primary table to {out_p}."
            elif out_p.suffix.lower() == ".xlsx":
                export_tables_xlsx(parsed.tables, out_p)
                exported_msg = f" Exported {len(parsed.tables)} tables to {out_p}."

        table_summaries = [f"Table {t.table_id} (Page {t.page_number}): {t.row_count} rows x {t.col_count} cols" for t in parsed.tables]
        result_text = f"Extracted {len(parsed.tables)} table(s) from '{parsed.title}'.{exported_msg}\n" + "\n".join(table_summaries)
        return outcome.done(
            "knowledge_base",
            result=result_text,
            data={"tables": [t.to_dict() for t in parsed.tables]},
        )

    if action == "compare_documents":
        path_a = str(parameters.get("path", "") or "").strip()
        path_b = str(parameters.get("path_b", "") or "").strip()
        if not path_a or not path_b:
            return outcome.failed("knowledge_base", "Both 'path' and 'path_b' are required to compare documents.")
        doc_a = DocumentParser.parse(path_a)
        doc_b = DocumentParser.parse(path_b)
        if doc_a.error:
            return outcome.failed("knowledge_base", f"Error in document A ({path_a}): {doc_a.error}")
        if doc_b.error:
            return outcome.failed("knowledge_base", f"Error in document B ({path_b}): {doc_b.error}")

        comp = DocumentReasoningEngine.compare_documents(doc_a, doc_b)
        disc_count = len(comp["discrepancies"])
        summary = (
            f"Comparison between '{doc_a.title}' and '{doc_b.title}': "
            f"{comp['common_parameters_count']} common parameter(s), {disc_count} discrepancy(ies), "
            f"{len(comp['agreements'])} agreement(s)."
        )
        return outcome.done("knowledge_base", result=summary, data=comp)

    if action == "document_summary":
        path_str = str(parameters.get("path", "") or "").strip()
        if not path_str:
            return outcome.failed("knowledge_base", "Please specify 'path' for document summary.")
        parsed = DocumentParser.parse(path_str)
        if parsed.error:
            return outcome.failed("knowledge_base", parsed.error)
        summary = DocumentReasoningEngine.summarize(parsed)
        conc_lines = [f"- {c['point']} (Section: {c['source_section']}, Page: {c['page']})" for c in summary["conclusions"]]
        result_text = (
            f"Document Summary for '{parsed.title}' ({summary['page_count']} pages, {summary['total_headings']} sections):\n"
            f"Key Conclusions:\n" + ("\n".join(conc_lines) if conc_lines else "No explicit conclusion section found.")
        )
        return outcome.done("knowledge_base", result=result_text, data=summary)

    if action == "find_section":
        path_str = str(parameters.get("path", "") or "").strip()
        query = str(parameters.get("query", "") or "").strip()
        if not path_str or not query:
            return outcome.failed("knowledge_base", "Both 'path' and 'query' are required for 'find_section'.")
        parsed = DocumentParser.parse(path_str)
        if parsed.error:
            return outcome.failed("knowledge_base", parsed.error)
        matches = DocumentReasoningEngine.find_section(parsed, query)
        if not matches:
            return outcome.done("knowledge_base", result=f"No sections matching '{query}' found in '{parsed.title}'.", data={"matches": []})
        lines = [f"- [{m['breadcrumb']} (Page {m['page']})]: {m['preview']}" for m in matches[:5]]
        return outcome.done(
            "knowledge_base",
            result=f"Found {len(matches)} section match(es) for '{query}' in '{parsed.title}':\n" + "\n".join(lines),
            data={"matches": matches},
        )

    if action == "visual_analyze":
        path_str = str(parameters.get("path", "") or "").strip()
        q = str(parameters.get("query", "") or "").strip()
        if not path_str:
            return outcome.failed("knowledge_base", "Please specify 'path' for visual_analyze.")
        res = VisualIntelligenceEngine.analyze_image(path_str, query=q)
        return outcome.done("knowledge_base", result=res.summary, data=res.to_dict())

    if action == "visual_verify":
        before_p = str(parameters.get("path", "") or parameters.get("before_path", "") or "").strip()
        after_p = str(parameters.get("path_b", "") or parameters.get("after_path", "") or "").strip()
        if not before_p or not after_p:
            return outcome.failed("knowledge_base", "Both 'path' (before) and 'path_b' (after) are required for visual_verify.")
        res = VisualIntelligenceEngine.verify_action(before_p, after_p)
        return outcome.done("knowledge_base", result=res.explanation, data=res.to_dict())

    if action == "analyze_audio":
        path_str = str(parameters.get("path", "") or "").strip()
        if not path_str:
            return outcome.failed("knowledge_base", "Please specify 'path' for analyze_audio.")
        res = MediaIntelligenceEngine.analyze_audio(path_str)
        return outcome.done("knowledge_base", result=res.summary, data=res.to_dict())

    if action == "analyze_video":
        path_str = str(parameters.get("path", "") or "").strip()
        if not path_str:
            return outcome.failed("knowledge_base", "Please specify 'path' for analyze_video.")
        res = MediaIntelligenceEngine.analyze_video(path_str)
        return outcome.done("knowledge_base", result=res.summary, data=res.to_dict())

    if action == "graph_query":
        kg = get_knowledge_graph()
        q = str(parameters.get("query", "") or "").strip()
        if not q:
            return outcome.failed("knowledge_base", "Please specify 'query' (entity name) for graph_query.")
        entity = kg.get_entity(q)
        if not entity:
            return outcome.done("knowledge_base", result=f"No entity matching '{q}' found in knowledge graph.", data={"entity": None})
        hops = kg.traverse_multi_hop(entity.entity_id, max_hops=int(parameters.get("hops", 2)))
        hop_lines = [f"- {h['path_trace']} ({h['target_type']})" for h in hops[:8]]
        summary = f"Entity '{entity.name}' ({entity.entity_type}) with {len(hops)} connected path(s):\n" + "\n".join(hop_lines)
        return outcome.done("knowledge_base", result=summary, data={"entity": entity.to_dict(), "paths": hops})

    if action == "graph_stats":
        kg = get_knowledge_graph()
        stats = kg.get_stats()
        summary = f"Knowledge Graph: {stats['total_entities']} entities, {stats['total_edges']} edges. Types: {stats['by_type']}. Relations: {stats['by_relation']}."
        return outcome.done("knowledge_base", result=summary, data=stats)

    if action == "conduct_research":
        researcher = get_research_engine()
        topic = str(parameters.get("topic", "") or parameters.get("query", "") or "").strip()
        if not topic:
            return outcome.failed("knowledge_base", "Please provide 'topic' or 'query' for conduct_research.")
        report = researcher.conduct_research(topic, max_sources=int(parameters.get("top_k", 5)))
        return outcome.done("knowledge_base", result=report.summary, data=report.to_dict())

    if action == "manage_space":
        km = get_creator_knowledge_manager()
        sub_action = str(parameters.get("sub_action", "get_active")).strip().lower()
        if sub_action == "create":
            sid = str(parameters.get("space_id", "") or "").strip()
            name = str(parameters.get("name", sid) or sid).strip()
            if not sid:
                return outcome.failed("knowledge_base", "Please specify 'space_id' to create knowledge space.")
            space = km.create_space(sid, name, description=parameters.get("description", ""))
            return outcome.done("knowledge_base", result=f"Created knowledge space '{space.name}' ({space.space_id}).", data=space.to_dict())
        elif sub_action == "switch":
            sid = str(parameters.get("space_id", "") or "").strip()
            ok = km.set_active_space(sid)
            return outcome.done("knowledge_base", result=f"Switched active knowledge space to '{sid}'.") if ok else outcome.failed("knowledge_base", f"Space '{sid}' not found.")
        else:
            active = km.get_active_space()
            return outcome.done("knowledge_base", result=f"Active Knowledge Space: '{active.name}' ({active.space_id}).", data=active.to_dict())

    if action == "live_monitor":
        mon = get_live_monitor()
        sub_action = str(parameters.get("sub_action", "list")).strip().lower()
        if sub_action == "register":
            tid = str(parameters.get("target_id", "") or "").strip()
            ttype = str(parameters.get("target_type", "file")).strip()
            uri = str(parameters.get("uri", "") or parameters.get("path", "") or "").strip()
            if not tid or not uri:
                return outcome.failed("knowledge_base", "Both 'target_id' and 'uri' (or 'path') are required.")
            target = mon.register_monitor(tid, ttype, uri, description=parameters.get("description", ""))
            return outcome.done("knowledge_base", result=f"Registered monitor target '{target.target_id}' ({target.target_type}).", data=target.to_dict())
        elif sub_action == "check":
            tid = str(parameters.get("target_id", "") or "").strip()
            if not tid:
                return outcome.failed("knowledge_base", "Please provide 'target_id' to check.")
            changed, explanation = mon.check_target(tid)
            return outcome.done("knowledge_base", result=explanation, data={"changed": changed})
        else:
            targets = mon.list_targets()
            summary = f"Monitoring {len(targets)} target(s): " + ", ".join([t.target_id for t in targets])
            return outcome.done("knowledge_base", result=summary, data={"targets": [t.to_dict() for t in targets]})

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

