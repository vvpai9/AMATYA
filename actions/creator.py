"""
actions/creator.py — CREATOR Autonomous Software Engineering & Document Engine for AMATYA.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core import outcome
from core.creator import classify_command_risk, get_creator_engine
from core.doc_generator import analyze_document, generate_document
from core.document_intelligence import resolve_user_path, resolve_user_output_path

SKILL_METADATA = {
    "name": "creator",
    "version": "2.0.0",
    "description": (
        "AMATYA CREATOR unified autonomous software engineering, self-repair and multi-modal generation suite. "
        "Integrates AST-validated surgical code editing, line-bounded code reading, universal file writing, "
        "repository inspection, project scaffolding, automated testing, git workflows, risk-gated terminal execution, "
        "autonomous self-repair and system health diagnostics, PDF/DOCX/XLSX/PPTX/CSV document studio, "
        "and multi-modal image & video generation. "
        "Includes major autonomous engineering, diagnostic self-healing, and generation capabilities "
        "contributed by Aman Kumar (@iamTechieAman)."
    ),
    "capabilities": [
        "repository_analysis",
        "code_search",
        "code_reading",
        "ast_surgical_edit",
        "multi_file_edit",
        "universal_file_creation",
        "project_scaffolding",
        "test_execution",
        "git_workflow",
        "risk_classified_shell",
        "autonomous_self_repair",
        "system_diagnostics",
        "document_generation",
        "document_analysis",
        "pdf_merge_and_extraction",
        "ai_image_generation",
        "ai_video_studio",
    ],
    "permissions": ["file_read", "file_write", "shell_exec", "git"],
    "dependencies": ["pdfplumber", "python-docx", "openpyxl", "python-pptx", "pillow"],
    "supported_actions": [
        "check_project",
        "inspect_repo",
        "search_code",
        "read_code",
        "edit_code",
        "write_code",
        "create_file",
        "scaffold",
        "create_project",
        "run_tests",
        "git_status",
        "git_diff",
        "git_log",
        "git_commit",
        "git_branch",
        "git_push",
        "git_pull",
        "apply_edits",
        "apply_edits_and_verify",
        "run_shell",
        "classify_command",
        "self_repair",
        "audit_system",
        "generate_doc",
        "analyze_doc",
        "merge_pdf",
        "extract_pdf_pages",
        "generate_image",
        "create_video",
        "code_assist",
        "get_profile",
        "update_profile",
        "list_profiles",
    ],
    "security_level": "high",
}

TOOL = {
    "name": "creator",
    "description": (
        "AMATYA CREATOR — Unified Autonomous Software Engineering, Self-Repair & Multi-Modal Generation Suite. "
        "Inspect repositories and check test integrity ('check_project'), search code ('search_code'), "
        "read code with line offsets ('read_code'), surgically edit code with AST syntax validation ('edit_code'), "
        "create or write files ('write_code', 'create_file'), scaffold projects ('scaffold', 'create_project'), "
        "run test suites ('run_tests'), manage Git ('git_status', 'git_diff', 'git_log', 'git_commit', 'git_branch', 'git_push', 'git_pull'), "
        "apply multi-file edits with auto-rollback ('apply_edits'), run risk-classified terminal commands ('run_shell'), "
        "perform autonomous system self-repair & diagnostics ('self_repair', 'audit_system'), "
        "generate & analyze multi-format documents ('generate_doc', 'analyze_doc', 'merge_pdf', 'extract_pdf_pages'), "
        "synthesize AI images with FLUX ('generate_image'), generate cinematic HUD video clips ('create_video'), "
        "and manage project profiles ('get_profile', 'update_profile', 'list_profiles')."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "Action: 'check_project', 'inspect_repo', 'search_code', 'read_code', 'edit_code', 'write_code', "
                    "'create_file', 'scaffold', 'create_project', 'run_tests', 'git_status', 'git_diff', 'git_log', "
                    "'git_commit', 'git_branch', 'git_push', 'git_pull', 'apply_edits', 'apply_edits_and_verify', "
                    "'run_shell', 'classify_command', 'self_repair', 'audit_system', 'generate_doc', 'analyze_doc', "
                    "'merge_pdf', 'extract_pdf_pages', 'generate_image', 'create_video', 'code_assist', "
                    "'get_profile', 'update_profile', 'list_profiles'."
                ),
            },
            "project_path": {
                "type": "STRING",
                "description": "Repository or project directory path.",
            },
            "path": {
                "type": "STRING",
                "description": "File or directory path for read_code, edit_code, write_code, create_file.",
            },
            "file_path": {
                "type": "STRING",
                "description": "Input file path for analyze_doc, read_code, edit_code, extract_pdf_pages.",
            },
            "output_path": {
                "type": "STRING",
                "description": "Output file path (.pdf, .docx, .xlsx, .pptx, .csv, .md, .zip, .jpg, .mp4).",
            },
            "target": {
                "type": "STRING",
                "description": "Target string snippet to replace (for edit_code) or subsystem (for self_repair).",
            },
            "replacement": {
                "type": "STRING",
                "description": "Replacement string snippet (for edit_code).",
            },
            "pattern": {
                "type": "STRING",
                "description": "Regex or keyword pattern for 'search_code'.",
            },
            "command": {
                "type": "STRING",
                "description": "Shell command for 'run_shell' or 'classify_command'.",
            },
            "start_line": {
                "type": "INTEGER",
                "description": "Starting 1-indexed line offset for 'read_code'.",
            },
            "end_line": {
                "type": "INTEGER",
                "description": "Ending 1-indexed line offset for 'read_code'.",
            },
            "project_name": {
                "type": "STRING",
                "description": "Project name for 'scaffold' or 'create_project'.",
            },
            "project_type": {
                "type": "STRING",
                "description": "Project archetype: 'python'/'fastapi', 'react'/'web', 'html', etc.",
            },
            "files": {
                "type": "OBJECT",
                "description": "Custom dictionary of {relative_path: content} for scaffolding.",
            },
            "pages_spec": {
                "type": "STRING",
                "description": "Comma-separated page spec (e.g. '1-3,5') for 'extract_pdf_pages'.",
            },
            "input_paths": {
                "type": "ARRAY",
                "items": {"type": "STRING"},
                "description": "List of PDF file paths to merge for 'merge_pdf'.",
            },
            "auto_install": {
                "type": "BOOLEAN",
                "description": "Set True to allow self_repair to auto-install missing packages via pip.",
            },
            "width": {
                "type": "INTEGER",
                "description": "Image width in pixels for 'generate_image' (default: 1024).",
            },
            "height": {
                "type": "INTEGER",
                "description": "Image height in pixels for 'generate_image' (default: 1024).",
            },
            "duration": {
                "type": "INTEGER",
                "description": "Duration in seconds for 'create_video' (2-30 seconds).",
            },
            "theme": {
                "type": "STRING",
                "description": "Visual theme for document or video ('cyber', 'cinematic', 'gold', 'neon', 'navy').",
            },
            "image_path": {
                "type": "STRING",
                "description": "Path to base image for 'create_video'.",
            },
            "confirmed": {
                "type": "BOOLEAN",
                "description": "Set True if user explicitly confirmed a MODIFY/DESTRUCTIVE command.",
            },
            "pin": {
                "type": "STRING",
                "description": "Security PIN for destructive/privileged commands.",
            },
            "commit_message": {
                "type": "STRING",
                "description": "Commit message for 'git_commit'.",
            },
            "branch": {
                "type": "STRING",
                "description": "Branch name for git operations.",
            },
            "remote": {
                "type": "STRING",
                "description": "Remote name for git operations (default: 'origin').",
            },
            "edits": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "path": {"type": "STRING"},
                        "target": {"type": "STRING"},
                        "replacement": {"type": "STRING"},
                    },
                },
                "description": "List of file edit dicts [{'path': ..., 'target': ..., 'replacement': ...}].",
            },
            "title": {"type": "STRING"},
            "content": {"type": "STRING"},
            "sections": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "heading": {"type": "STRING"},
                        "text": {"type": "STRING"},
                    },
                },
            },
            "rows": {
                "type": "ARRAY",
                "items": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                },
            },
            "source_paths": {"type": "ARRAY", "items": {"type": "STRING"}},
            "prompt": {"type": "STRING"},
        },
        "required": ["action"],
    },
}


def execute(
    parameters: dict[str, Any],
    response=None,
    player=None,
    session_memory=None,
    speak=None,
    **kwargs,
) -> Any:
    action = str(parameters.get("action", "check_project") or "check_project").strip().lower()
    engine = get_creator_engine()
    proj = parameters.get("project_path")

    if action == "check_project":
        info = engine.inspect_repository(proj)
        if not info.get("ok"):
            return outcome.failed("creator", info.get("error", "Repository check failed."), data=info)
        tests = engine.run_tests(proj)
        summary = (
            f"Project '{info['project_path']}' (branch={info['git_branch']}, "
            f"{info['total_files']} files): Git status: {info['git_status'][:200]}. "
            f"Tests/Verification ({tests.get('elapsed_sec', 0)}s): "
            f"{'PASSED' if tests.get('ok') else 'FAILED'} — {tests.get('output', '')[:300]}"
        )
        return outcome.done("creator", result=summary, data={"repo": info, "tests": tests})

    if action == "inspect_repo":
        info = engine.inspect_repository(proj)
        if not info.get("ok"):
            return outcome.failed("creator", info.get("error", "Failed to inspect repo."), data=info)
        return outcome.done(
            "creator",
            result=f"Inspected '{info['project_path']}': {info['total_files']} files, "
                   f"branch='{info['git_branch']}', types={info['file_types']}.",
            data=info,
        )

    if action == "search_code":
        pat = str(parameters.get("pattern", "") or "").strip()
        res = engine.search_code(pat, proj)
        if not res.get("ok"):
            return outcome.failed("creator", res.get("error", "Search failed."), data=res)
        lines = [f"{m['file']}:{m['line']}: {m['text']}" for m in res["matches"][:15]]
        return outcome.done(
            "creator",
            result=f"Found {res['count']} match(es) for '{pat}':\n" + "\n".join(lines),
            data=res,
        )

    if action == "run_tests":
        res = engine.run_tests(proj, test_target=parameters.get("file_path"))
        if res.get("ok"):
            return outcome.done(
                "creator",
                result=f"Tests/checks passed in {res.get('elapsed_sec')}s: {res.get('output')}",
                data=res,
            )
        return outcome.failed("creator", f"Tests/checks failed: {res.get('output') or res.get('error')}", data=res)

    if action == "read_code":
        fpath = str(parameters.get("file_path") or parameters.get("path") or "").strip()
        if not fpath:
            return outcome.failed("creator", "Please specify 'file_path' or 'path' to read.")
        resolved = resolve_user_path(fpath)
        s_line = parameters.get("start_line")
        e_line = parameters.get("end_line")
        res = engine.read_code(resolved, start_line=int(s_line) if s_line else 1, end_line=int(e_line) if e_line else None)
        if not res.get("ok"):
            return outcome.failed("creator", res.get("error", "Read failed."), data=res)
        if player and hasattr(player, "show_content"):
            try:
                player.show_content(f"Code Viewer: {res.get('filename')}", f"```\n{res['content']}\n```")
            except Exception:
                pass
        return outcome.done(
            "creator",
            result=f"Read lines {res['start_line']} to {res['end_line']} of {res.get('filename')} ({len(res['content'])} characters):\n{res['content'][:1500]}",
            data=res,
        )

    if action == "edit_code":
        fpath = str(parameters.get("file_path") or parameters.get("path") or "").strip()
        if not fpath:
            return outcome.failed("creator", "Please specify 'file_path' or 'path' to edit.")
        target = parameters.get("target") or ""
        replacement = parameters.get("replacement") or ""
        resolved = resolve_user_path(fpath)
        res = engine.edit_code(resolved, target=target, replacement=replacement)
        if not res.get("ok"):
            return outcome.failed("creator", res.get("error", "Edit failed."), data=res)
        if player and hasattr(player, "show_content"):
            try:
                player.show_content(f"Code Edit: {Path(fpath).name}", f"### Modified {Path(fpath).name}\n- {res['diff_summary']}")
            except Exception:
                pass
        if player and hasattr(player, "write_log"):
            try:
                player.write_log(f"CREATOR: Surgically edited {Path(fpath).name} ({res['diff_summary']})")
            except Exception:
                pass
        return outcome.done("creator", result=f"Successfully edited {Path(fpath).name}. {res['diff_summary']}", data=res)

    if action in ("write_code", "create_file"):
        fpath = str(parameters.get("file_path") or parameters.get("path") or parameters.get("output_path") or "").strip()
        if not fpath:
            return outcome.failed("creator", "Please specify 'file_path' or 'path' to write.")
        content = parameters.get("content", "")
        resolved = resolve_user_output_path(fpath)
        res = engine.write_code(resolved, content=content)
        if not res.get("ok"):
            return outcome.failed("creator", res.get("error", "Write failed."), data=res)
        if player and hasattr(player, "show_content"):
            try:
                player.show_content(f"Created File: {resolved.name}", f"```\n{content[:2000]}\n```")
            except Exception:
                pass
        if player and hasattr(player, "write_log"):
            try:
                player.write_log(f"CREATOR: Wrote file {resolved.name} ({res['bytes_written']} bytes)")
            except Exception:
                pass
        return outcome.done("creator", result=f"Successfully created {resolved.name} ({res['bytes_written']} bytes).", data=res)

    if action in ("scaffold", "create_project"):
        pname = str(parameters.get("project_name") or parameters.get("title") or "new_project").strip()
        ptype = str(parameters.get("project_type") or "python").strip()
        tdir = parameters.get("project_path") or parameters.get("target_dir")
        files_spec = parameters.get("files")
        res = engine.scaffold_project(pname, project_type=ptype, target_dir=tdir, files=files_spec)
        if not res.get("ok"):
            return outcome.failed("creator", res.get("error", "Scaffold failed."), data=res)
        summary = f"Scaffolded {ptype.upper()} project '{pname}' at '{res['project_dir']}': created {', '.join(res['created_files'])}."
        if player and hasattr(player, "show_content"):
            try:
                player.show_content(f"Scaffolded Project: {pname}", f"### Project {pname}\n- Directory: `{res['project_dir']}`\n- Type: {ptype}\n- Files: {', '.join(res['created_files'])}")
            except Exception:
                pass
        return outcome.done("creator", result=summary, data=res)

    if action in ("git_status", "git_diff", "git_log", "git_commit", "git_branch", "git_push", "git_pull"):
        op = action.replace("git_", "")
        res = engine.git_operation(
            proj,
            op=op,
            message=str(parameters.get("commit_message", "") or ""),
            branch=str(parameters.get("branch", "") or ""),
            remote=str(parameters.get("remote", "origin") or "origin"),
        )
        if not res.get("ok"):
            return outcome.failed("creator", res.get("error") or res.get("stdout", "Git operation failed."), data=res)
        return outcome.done("creator", result=f"Git {op}: {res.get('stdout', '')}", data=res)

    if action in ("apply_edits", "apply_edits_and_verify"):
        edits = parameters.get("edits")
        if not isinstance(edits, list) or not edits:
            return outcome.failed("creator", "Please provide a non-empty 'edits' list.")
        if action == "apply_edits_and_verify" or parameters.get("verify_tests"):
            res = engine.apply_edits_and_verify(edits, project_path=proj)
        else:
            res = engine.apply_edits(edits)
        if not res.get("ok"):
            return outcome.failed("creator", res.get("error", "Edit failed."), data=res)
        return outcome.done("creator", result=f"Modified {len(res['modified_files'])} file(s).", data=res)

    if action == "classify_command":
        cmd = str(parameters.get("command", "") or "")
        risk = classify_command_risk(cmd)
        return outcome.done(
            "creator",
            result=f"Command '{cmd}' classified as {risk['risk_level']} "
                   f"(requires_confirmation={risk['requires_confirmation']}): {risk['reason']}",
            data=risk,
        )

    if action == "run_shell":
        cmd = str(parameters.get("command", "") or "").strip()
        if not cmd:
            return outcome.failed("creator", "Please provide 'command' to run.")
        res = engine.run_shell(
            command=cmd,
            cwd=proj,
            confirmed=bool(parameters.get("confirmed", False)),
            pin=parameters.get("pin"),
        )
        if not res.get("ok"):
            return outcome.failed("creator", res.get("error") or res.get("stderr", "Command failed."), data=res)
        return outcome.done(
            "creator",
            result=f"Command ({res['risk']['risk_level']}) succeeded:\n{res.get('stdout', '')}",
            data=res,
        )

    if action == "generate_doc":
        out_path_raw = str(parameters.get("output_path") or parameters.get("file_path") or "").strip()
        if not out_path_raw:
            return outcome.failed("creator", "Please specify 'output_path' (.pdf, .docx, .xlsx, .pptx, .csv, .md, .zip).")
        out_path = str(resolve_user_output_path(out_path_raw))

        raw_sections = parameters.get("sections") or parameters.get("slides")
        if isinstance(raw_sections, str) and raw_sections.strip().startswith(("[", "{")):
            try:
                parsed_s = json.loads(raw_sections.strip())
                if isinstance(parsed_s, list):
                    raw_sections = parsed_s
                elif isinstance(parsed_s, dict):
                    raw_sections = parsed_s.get("slides") or parsed_s.get("sections")
            except Exception:
                pass

        raw_content = parameters.get("content", "")
        title_val = str(parameters.get("title", "") or "").strip()
        if isinstance(raw_content, str) and raw_content.strip().startswith(("[", "{")):
            try:
                parsed_c = json.loads(raw_content.strip())
                if isinstance(parsed_c, list) and not raw_sections:
                    raw_sections = parsed_c
                    raw_content = ""
                elif isinstance(parsed_c, dict):
                    if not raw_sections:
                        raw_sections = parsed_c.get("slides") or parsed_c.get("sections")
                    if not title_val and parsed_c.get("title"):
                        title_val = str(parsed_c["title"])
                    if parsed_c.get("content") or parsed_c.get("subtitle"):
                        raw_content = str(parsed_c.get("content") or parsed_c.get("subtitle") or "")
            except Exception:
                pass

        # If raw_content is a path to an existing file, load its real text content
        if raw_content and isinstance(raw_content, str) and "\n" not in raw_content and len(raw_content.strip()) < 300:
            try:
                c_cand = resolve_user_path(raw_content.strip())
                if c_cand.is_file():
                    d_res = analyze_document(c_cand)
                    if d_res.get("ok") and d_res.get("text"):
                        raw_content = d_res["text"]
                    else:
                        raw_content = c_cand.read_text(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass

        # If raw_content is empty or a generic placeholder, check source_paths or context last_file
        source_candidates: list[str] = []
        if parameters.get("source_paths") and isinstance(parameters["source_paths"], list):
            source_candidates.extend(parameters["source_paths"])
        for sk in ("source_path", "source_file", "file_path", "input_file"):
            if parameters.get(sk):
                source_candidates.append(parameters[sk])

        is_vague = not raw_content or str(raw_content).strip().lower() in (
            "automated summary.", "summary", "project report", "$prev.summary",
            "$prev.content", "$prev.text", "amatya document", "summary of project report"
        )

        if is_vague and source_candidates:
            extracted_texts = []
            for sf in source_candidates:
                p = resolve_user_path(str(sf))
                if p.is_file() and p.suffix.lower() in (".txt", ".md", ".json", ".csv", ".docx", ".pdf"):
                    try:
                        d_res = analyze_document(p)
                        if d_res.get("ok") and d_res.get("text"):
                            extracted_texts.append(d_res["text"])
                        else:
                            extracted_texts.append(p.read_text(encoding="utf-8", errors="replace"))
                    except Exception:
                        pass
            if extracted_texts:
                raw_content = "\n\n".join(extracted_texts)
                is_vague = False

        if is_vague and not raw_sections:
            try:
                from core.orchestrator import get_orchestrator
                orch = get_orchestrator()
                ctx_st = orch.context.get_state()
                recent_cands = []
                if ctx_st.get("last_file"):
                    recent_cands.append(ctx_st["last_file"])
                last_task = ctx_st.get("last_task", {})
                if isinstance(last_task, dict) and last_task.get("artifacts"):
                    recent_cands.extend(last_task["artifacts"])
                for rf in recent_cands:
                    p = resolve_user_path(str(rf))
                    if p.is_file() and p.suffix.lower() in (".txt", ".md", ".json", ".docx", ".pdf"):
                        d_res = analyze_document(p)
                        if d_res.get("ok") and d_res.get("text"):
                            raw_content = d_res["text"]
                            break
                        txt = p.read_text(encoding="utf-8", errors="replace")
                        if len(txt.strip()) > 30:
                            raw_content = txt
                            break
            except Exception:
                pass

        res = generate_document(
            output_path=out_path,
            title=title_val or "AMATYA Document",
            content=str(raw_content or ""),
            sections=raw_sections,
            slides=raw_sections,
            rows=parameters.get("rows"),
            source_paths=parameters.get("source_paths"),
            theme=str(parameters.get("theme", "navy")),
        )
        if not res.get("ok"):
            return outcome.failed("creator", res.get("error", "Document generation failed."), data=res)
        return outcome.done(
            "creator",
            result=f"Generated {res['format'].upper()} document at '{res['path']}' ({res['size_bytes']} bytes).",
            data=res,
        )

    if action == "analyze_doc":
        fpath_raw = str(parameters.get("file_path") or parameters.get("output_path") or "").strip()
        if not fpath_raw:
            return outcome.failed("creator", "Please specify 'file_path' to analyze.")
        fpath = str(resolve_user_path(fpath_raw))
        res = analyze_document(fpath)
        if not res.get("ok"):
            return outcome.failed("creator", res.get("error", "Document analysis failed."), data=res)
        preview = str(res.get("text") or res.get("rows") or res.get("sheets") or res.get("entries") or "")[:600]
        return outcome.done(
            "creator",
            result=f"Analyzed {res['format'].upper()} file '{res['path']}':\n{preview}",
            data=res,
        )

    if action in ("self_repair", "audit_system"):
        tgt = str(parameters.get("target", "all") or "all")
        auto_install = bool(parameters.get("auto_install", False))
        res = engine.self_repair(target=tgt, player=player, auto_install=auto_install)
        return outcome.done("creator", result=res["summary"], data=res)

    if action == "merge_pdf":
        inputs = parameters.get("input_paths") or parameters.get("source_paths") or []
        out_name = str(parameters.get("output_path") or parameters.get("filename") or "merged_output.pdf")
        if not inputs or not isinstance(inputs, list):
            return outcome.failed("creator", "Please provide a list of 'input_paths' to merge.")
        res = engine.merge_pdfs(inputs, output_filename=out_name)
        if not res.get("ok"):
            return outcome.failed("creator", res.get("error", "PDF merge failed."), data=res)
        return outcome.done("creator", result=res["message"], data=res)

    if action == "extract_pdf_pages":
        in_path = str(parameters.get("file_path") or parameters.get("path") or "").strip()
        pages = str(parameters.get("pages_spec") or parameters.get("pages") or "").strip()
        out_name = str(parameters.get("output_path") or parameters.get("filename") or "extracted_pages.pdf")
        if not in_path or not pages:
            return outcome.failed("creator", "Please provide 'file_path' and 'pages_spec' (e.g. '1-3,5').")
        res = engine.extract_pdf_pages(in_path, pages_spec=pages, output_filename=out_name)
        if not res.get("ok"):
            return outcome.failed("creator", res.get("error", "PDF extraction failed."), data=res)
        return outcome.done("creator", result=res["message"], data=res)

    if action == "generate_image":
        prompt = str(parameters.get("prompt") or parameters.get("content") or "").strip()
        if not prompt:
            return outcome.failed("creator", "Please provide 'prompt' describing the image.")
        w = int(parameters.get("width") or 1024)
        h = int(parameters.get("height") or 1024)
        fname = parameters.get("filename") or parameters.get("output_path")
        if player and hasattr(player, "write_log"):
            try:
                player.write_log(f"CREATOR: Generating image '{prompt[:40]}...'")
            except Exception:
                pass
        res = engine.generate_image(prompt, width=w, height=h, filename=fname)
        if not res.get("ok"):
            return outcome.failed("creator", res.get("error", "Image generation failed."), data=res)
        return outcome.done("creator", result=res["message"], data=res)

    if action == "create_video":
        title = str(parameters.get("title") or "AMATYA Production").strip()
        text = str(parameters.get("text") or parameters.get("content") or title)
        img_p = str(parameters.get("image_path") or "")
        dur = int(parameters.get("duration") or 5)
        theme = str(parameters.get("theme") or "cyber")
        res = engine.create_video(title, text=text, image_path=img_p, duration=dur, theme=theme)
        if not res.get("ok"):
            return outcome.failed("creator", res.get("error", "Video creation failed."), data=res)
        return outcome.done("creator", result=res["message"], data=res)

    if action == "code_assist":
        prompt = str(parameters.get("prompt", "") or "").strip()
        if not prompt:
            return outcome.failed("creator", "Please provide 'prompt' for code_assist.")
        ans = engine.analyze_or_generate_code(prompt, str(parameters.get("content", "") or ""))
        return outcome.done("creator", result=ans)

    if action == "get_profile":
        proj = str(parameters.get("project_path") or parameters.get("project_id") or "").strip()
        prof = engine.get_profile(proj)
        if not prof:
            return outcome.failed("creator", f"No project profile found for '{proj}'.")
        return outcome.done("creator", result=f"Profile for {prof['name']}: {prof['purpose']}", data=prof)

    if action == "update_profile":
        proj = str(parameters.get("project_path") or parameters.get("project_id") or "").strip()
        if not proj:
            return outcome.failed("creator", "Please provide 'project_path' or 'project_id' to update profile.")
        updates = parameters.get("updates") or {}
        if not isinstance(updates, dict):
            updates = {
                "purpose": str(parameters.get("purpose", "")),
                "architecture": str(parameters.get("architecture", "")),
            }
        prof = engine.update_profile(proj, updates)
        return outcome.done("creator", result=f"Updated profile for '{prof['name']}'.", data=prof)

    if action == "list_profiles":
        profs = engine.list_profiles()
        lines = [f"- [{p['project_id']}] {p['name']} ({', '.join(p['tech_stack'])}): {p['purpose']}" for p in profs]
        summary = "\n".join(lines) if lines else "No project profiles registered yet."
        return outcome.done("creator", result=f"Stored Project Profiles ({len(profs)}):\n{summary}", data={"profiles": profs})

    return outcome.failed("creator", f"Unknown creator action '{action}'.")

