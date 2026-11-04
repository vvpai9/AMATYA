"""
actions/creator.py — CREATOR Autonomous Software Engineering & Document Engine for AMATYA.
"""
from __future__ import annotations

from typing import Any

from core import outcome
from core.creator import classify_command_risk, get_creator_engine
from core.doc_generator import analyze_document, generate_document

SKILL_METADATA = {
    "name": "creator",
    "version": "1.0.0",
    "description": "CREATOR autonomous software engineering, repository inspection, git workflows, test runner, risk-gated shell execution, and PDF/DOCX/XLSX/PPTX/CSV/ZIP document generation and analysis.",
    "capabilities": [
        "repository_analysis",
        "code_search",
        "multi_file_edit",
        "test_execution",
        "git_workflow",
        "risk_classified_shell",
        "document_generation",
        "document_analysis",
    ],
    "permissions": ["file_read", "file_write", "shell_exec", "git"],
    "dependencies": ["pdfplumber", "python-docx", "openpyxl", "python-pptx"],
    "supported_actions": [
        "check_project",
        "inspect_repo",
        "search_code",
        "run_tests",
        "git_status",
        "git_diff",
        "git_log",
        "git_commit",
        "apply_edits",
        "run_shell",
        "classify_command",
        "generate_doc",
        "analyze_doc",
        "code_assist",
    ],
    "security_level": "high",
}

TOOL = {
    "name": "creator",
    "description": (
        "AMATYA CREATOR Software Engineering & Document Processing subsystem. "
        "Inspect repositories, check whether changes broke anything ('check_project'), "
        "search code ('search_code'), run test suites ('run_tests'), manage Git "
        "('git_status', 'git_diff', 'git_log', 'git_commit'), apply multi-file edits "
        "('apply_edits'), run risk-classified terminal commands ('run_shell'), and "
        "generate or analyze PDF, DOCX, XLSX, PPTX, CSV, Markdown, and ZIP files "
        "('generate_doc', 'analyze_doc')."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "Action: 'check_project', 'inspect_repo', 'search_code', "
                    "'run_tests', 'git_status', 'git_diff', 'git_log', 'git_commit', "
                    "'apply_edits', 'run_shell', 'classify_command', 'generate_doc', "
                    "'analyze_doc', 'code_assist'."
                ),
            },
            "project_path": {
                "type": "STRING",
                "description": "Repository or project directory path.",
            },
            "pattern": {
                "type": "STRING",
                "description": "Regex or keyword pattern for 'search_code'.",
            },
            "command": {
                "type": "STRING",
                "description": "Shell command for 'run_shell' or 'classify_command'.",
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
            "edits": {
                "type": "ARRAY",
                "items": {"type": "OBJECT"},
                "description": "List of file edit dicts [{'path': ..., 'target': ..., 'replacement': ...}].",
            },
            "output_path": {
                "type": "STRING",
                "description": "Output file path (.pdf, .docx, .xlsx, .pptx, .csv, .md, .zip) for 'generate_doc'.",
            },
            "file_path": {
                "type": "STRING",
                "description": "Input file path for 'analyze_doc'.",
            },
            "title": {"type": "STRING"},
            "content": {"type": "STRING"},
            "sections": {"type": "ARRAY", "items": {"type": "OBJECT"}},
            "rows": {"type": "ARRAY", "items": {"type": "ARRAY"}},
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
) -> Any:
    action = str(parameters.get("action", "check_project") or "check_project").strip().lower()
    engine = get_creator_engine()
    proj = parameters.get("project_path")

    if action == "check_project":
        info = engine.inspect_repository(proj)
        if not info.get("ok"):
            return outcome.failed(info.get("error", "Repository check failed."), data=info)
        tests = engine.run_tests(proj)
        summary = (
            f"Project '{info['project_path']}' (branch={info['git_branch']}, "
            f"{info['total_files']} files): Git status: {info['git_status'][:200]}. "
            f"Tests/Verification ({tests.get('elapsed_sec', 0)}s): "
            f"{'PASSED' if tests.get('ok') else 'FAILED'} — {tests.get('output', '')[:300]}"
        )
        return outcome.done(summary, data={"repo": info, "tests": tests})

    if action == "inspect_repo":
        info = engine.inspect_repository(proj)
        if not info.get("ok"):
            return outcome.failed(info.get("error", "Failed to inspect repo."), data=info)
        return outcome.done(
            f"Inspected '{info['project_path']}': {info['total_files']} files, "
            f"branch='{info['git_branch']}', types={info['file_types']}.",
            data=info,
        )

    if action == "search_code":
        pat = str(parameters.get("pattern", "") or "").strip()
        res = engine.search_code(pat, proj)
        if not res.get("ok"):
            return outcome.failed(res.get("error", "Search failed."), data=res)
        lines = [f"{m['file']}:{m['line']}: {m['text']}" for m in res["matches"][:15]]
        return outcome.done(
            f"Found {res['count']} match(es) for '{pat}':\n" + "\n".join(lines),
            data=res,
        )

    if action == "run_tests":
        res = engine.run_tests(proj, test_target=parameters.get("file_path"))
        if res.get("ok"):
            return outcome.done(
                f"Tests/checks passed in {res.get('elapsed_sec')}s: {res.get('output')}",
                data=res,
            )
        return outcome.failed(f"Tests/checks failed: {res.get('output') or res.get('error')}", data=res)

    if action in ("git_status", "git_diff", "git_log", "git_commit"):
        op = action.replace("git_", "")
        res = engine.git_operation(proj, op=op, message=str(parameters.get("commit_message", "") or ""))
        if not res.get("ok"):
            return outcome.failed(res.get("error") or res.get("stdout", "Git operation failed."), data=res)
        return outcome.done(f"Git {op}: {res.get('stdout', '')}", data=res)

    if action == "apply_edits":
        edits = parameters.get("edits")
        if not isinstance(edits, list) or not edits:
            return outcome.failed("Please provide a non-empty 'edits' list.")
        res = engine.apply_edits(edits)
        if not res.get("ok"):
            return outcome.failed(res.get("error", "Edit failed."), data=res)
        return outcome.done(f"Modified {len(res['modified_files'])} file(s).", data=res)

    if action == "classify_command":
        cmd = str(parameters.get("command", "") or "")
        risk = classify_command_risk(cmd)
        return outcome.done(
            f"Command '{cmd}' classified as {risk['risk_level']} "
            f"(requires_confirmation={risk['requires_confirmation']}): {risk['reason']}",
            data=risk,
        )

    if action == "run_shell":
        cmd = str(parameters.get("command", "") or "").strip()
        if not cmd:
            return outcome.failed("Please provide 'command' to run.")
        res = engine.run_shell(
            command=cmd,
            cwd=proj,
            confirmed=bool(parameters.get("confirmed", False)),
            pin=parameters.get("pin"),
        )
        if not res.get("ok"):
            return outcome.failed(res.get("error") or res.get("stderr", "Command failed."), data=res)
        return outcome.done(
            f"Command ({res['risk']['risk_level']}) succeeded:\n{res.get('stdout', '')}",
            data=res,
        )

    if action == "generate_doc":
        out_path = str(parameters.get("output_path") or parameters.get("file_path") or "").strip()
        if not out_path:
            return outcome.failed("Please specify 'output_path' (.pdf, .docx, .xlsx, .pptx, .csv, .md, .zip).")
        res = generate_document(
            output_path=out_path,
            title=str(parameters.get("title", "AMATYA Document")),
            content=str(parameters.get("content", "")),
            sections=parameters.get("sections"),
            rows=parameters.get("rows"),
            source_paths=parameters.get("source_paths"),
        )
        if not res.get("ok"):
            return outcome.failed(res.get("error", "Document generation failed."), data=res)
        return outcome.done(
            f"Generated {res['format'].upper()} document at '{res['path']}' ({res['size_bytes']} bytes).",
            data=res,
        )

    if action == "analyze_doc":
        fpath = str(parameters.get("file_path") or parameters.get("output_path") or "").strip()
        if not fpath:
            return outcome.failed("Please specify 'file_path' to analyze.")
        res = analyze_document(fpath)
        if not res.get("ok"):
            return outcome.failed(res.get("error", "Document analysis failed."), data=res)
        preview = str(res.get("text") or res.get("rows") or res.get("sheets") or res.get("entries") or "")[:600]
        return outcome.done(
            f"Analyzed {res['format'].upper()} file '{res['path']}':\n{preview}",
            data=res,
        )

    if action == "code_assist":
        prompt = str(parameters.get("prompt", "") or "").strip()
        if not prompt:
            return outcome.failed("Please provide 'prompt' for code_assist.")
        ans = engine.analyze_or_generate_code(prompt, str(parameters.get("content", "") or ""))
        return outcome.done(ans)

    return outcome.failed(f"Unknown creator action '{action}'.")
