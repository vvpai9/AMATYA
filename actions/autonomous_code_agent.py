"""
Antigravity-Style Autonomous Code Engineering Agent for JARVIS.
Contributed by Aman Kumar (@iamTechieAman).

Gives JARVIS the full coding, refactoring, code search, and surgical editing
capabilities of an expert AI software engineer like Antigravity.

Supported operations:
  - 'read': Read specific lines or whole files across any workspace.
  - 'edit': Exact surgical find-and-replace edit with AST validation.
  - 'write': Create or overwrite files.
  - 'search': Search for symbols, text, or regex across a directory.
  - 'command': Execute build, test, or package commands and capture outputs.
"""
from __future__ import annotations

import ast
import os
import re
import subprocess
import time
from pathlib import Path

MAX_READ_BYTES = 50_000


def _safe_path(raw_path: str) -> Path:
    p = Path(raw_path).expanduser().resolve()
    return p


def autonomous_code_agent(parameters: dict, player=None) -> str:
    """
    Antigravity-style autonomous code agent.
    parameters:
      action: 'read' | 'edit' | 'write' | 'search' | 'command'
      path: absolute or relative file/directory path
      target: string to replace (for 'edit')
      replacement: replacement string (for 'edit')
      content: full file content (for 'write')
      start_line: integer line offset (optional, for 'read')
      end_line: integer line offset (optional, for 'read')
      query: search pattern or keyword (for 'search')
      command: shell command string (for 'command')
    """
    action = (parameters.get("action") or "read").lower().strip()
    raw_path = parameters.get("path") or "."
    target = parameters.get("target") or ""
    replacement = parameters.get("replacement") or ""
    content = parameters.get("content") or ""
    query = parameters.get("query") or ""
    command = parameters.get("command") or ""

    try:
        p = _safe_path(raw_path)
    except Exception as e:
        return f"Invalid path provided: {e}"

    if action == "read":
        if not p.is_file():
            return f"Error: File '{p}' does not exist."
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
            start = int(parameters.get("start_line") or 1) - 1
            end = int(parameters.get("end_line") or len(lines))
            start = max(0, start)
            end = min(len(lines), end)
            selected = "".join(lines[start:end])
            if len(selected) > MAX_READ_BYTES:
                selected = selected[:MAX_READ_BYTES] + "\n...[truncated]"
            
            if player and hasattr(player, "show_content"):
                player.show_content(f"Code Viewer: {p.name}", f"```\n{selected}\n```")
            return f"Read lines {start+1} to {end} of {p.name} ({len(selected)} characters)."
        except Exception as e:
            return f"Failed to read file: {e}"

    elif action == "edit":
        if not p.is_file():
            return f"Error: Target file '{p}' does not exist."
        if not target:
            return "Error: Edit requires a non-empty 'target' string."
        try:
            original = p.read_text(encoding="utf-8", errors="replace")
            if target not in original:
                return f"Error: Target snippet not found in {p.name}."
            count = original.count(target)
            updated = original.replace(target, replacement)
            
            # If python file, validate AST before writing
            if p.suffix == ".py":
                try:
                    ast.parse(updated, filename=str(p))
                except SyntaxError as se:
                    return f"Edit aborted: Syntax validation failed on line {se.lineno}: {se.msg}"
            
            p.write_text(updated, encoding="utf-8")
            diff_summary = f"Replaced {count} occurrence(s) in {p.name}."
            if player and hasattr(player, "show_content"):
                player.show_content(f"Code Edit: {p.name}", f"### Modified {p.name}\n- {diff_summary}")
            if player and hasattr(player, "write_log"):
                player.write_log(f"CODE: Surgically edited {p.name} ({diff_summary})")
            return f"Successfully edited {p.name}. {diff_summary}"
        except Exception as e:
            return f"Failed to edit file: {e}"

    elif action == "write":
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            if p.suffix == ".py":
                try:
                    ast.parse(content, filename=str(p))
                except SyntaxError as se:
                    return f"Write aborted: Syntax error on line {se.lineno}: {se.msg}"
            p.write_text(content, encoding="utf-8")
            if player and hasattr(player, "show_content"):
                player.show_content(f"Created File: {p.name}", f"```\n{content[:2000]}\n```")
            if player and hasattr(player, "write_log"):
                player.write_log(f"CODE: Wrote file {p.name} ({len(content)} bytes)")
            return f"Successfully created {p.name} ({len(content)} bytes)."
        except Exception as e:
            return f"Failed to write file: {e}"

    elif action == "search":
        if not query:
            return "Error: Search action requires a 'query' string."
        if not p.is_dir():
            p = p.parent
        matches = []
        try:
            pattern = re.compile(re.escape(query), re.IGNORECASE)
            for f in p.rglob("*"):
                if f.is_file() and not any(part.startswith(".") or part == "__pycache__" for part in f.parts):
                    try:
                        text = f.read_text(encoding="utf-8", errors="ignore")
                        for idx, line in enumerate(text.splitlines(), 1):
                            if pattern.search(line):
                                matches.append(f"{f.relative_to(p)}:{idx}: {line.strip()[:100]}")
                                if len(matches) >= 25:
                                    break
                    except Exception:
                        continue
                if len(matches) >= 25:
                    break
            
            result_text = "\n".join(matches) if matches else f"No matches found for '{query}' in {p}."
            if player and hasattr(player, "show_content"):
                player.show_content(f"Code Search: '{query}'", f"```\n{result_text}\n```")
            return f"Found {len(matches)} matching line(s) for '{query}'."
        except Exception as e:
            return f"Search failed: {e}"

    elif action == "command":
        if not command:
            return "Error: Command action requires a 'command' string."
        # Safe execution in project or specified directory
        cwd = p if p.is_dir() else p.parent
        try:
            r = subprocess.run(command, shell=True, cwd=cwd, capture_output=True, text=True, timeout=60)
            out = (r.stdout + "\n" + r.stderr).strip()
            if len(out) > 2000:
                out = out[:2000] + "\n...[output truncated]"
            if player and hasattr(player, "show_content"):
                player.show_content(f"Terminal Output: {command[:30]}", f"Exit Code: {r.returncode}\n```\n{out}\n```")
            return f"Command executed with exit code {r.returncode}. Output: {out[:200]}"
        except subprocess.TimeoutExpired:
            return "Command timed out after 60 seconds."
        except Exception as e:
            return f"Command execution failed: {e}"

    elif action in ("create_project", "scaffold"):
        project_name = parameters.get("project_name") or p.name or "new_project"
        project_dir = p if p.is_dir() and p.name == project_name else (p / project_name if p.is_dir() else p.parent / project_name)
        project_type = (parameters.get("project_type") or "python").lower()
        files = parameters.get("files") or {}

        try:
            project_dir.mkdir(parents=True, exist_ok=True)
            created_files = []

            # If user or model provided custom files dictionary
            if isinstance(files, dict) and files:
                for rel_path, file_content in files.items():
                    fpath = project_dir / rel_path
                    fpath.parent.mkdir(parents=True, exist_ok=True)
                    fpath.write_text(str(file_content), encoding="utf-8")
                    created_files.append(rel_path)
            else:
                # Built-in templates based on project_type
                if "python" in project_type:
                    (project_dir / "main.py").write_text(
                        f'"""\n{project_name} - Built by JARVIS Autonomous Engineering\n"""\n\ndef main():\n    print("Hello from {project_name}!")\n\nif __name__ == "__main__":\n    main()\n',
                        encoding="utf-8"
                    )
                    (project_dir / "requirements.txt").write_text("# Project dependencies\nrequests\n", encoding="utf-8")
                    (project_dir / "README.md").write_text(f"# {project_name}\n\nAutomated project scaffolded by JARVIS for Aman Kumar.\n\n## Getting Started\n```bash\npython main.py\n```\n", encoding="utf-8")
                    created_files.extend(["main.py", "requirements.txt", "README.md"])
                elif "react" in project_type or "web" in project_type or "html" in project_type:
                    (project_dir / "index.html").write_text(
                        f'<!DOCTYPE html>\n<html lang="en">\n<head>\n  <meta charset="UTF-8">\n  <title>{project_name}</title>\n  <style>body {{ font-family: sans-serif; background: #0f172a; color: #f8fafc; text-align: center; padding: 4rem; }}</style>\n</head>\n<body>\n  <h1>⚡ {project_name}</h1>\n  <p>Engineered autonomously by JARVIS.</p>\n  <script src="app.js"></script>\n</body>\n</html>',
                        encoding="utf-8"
                    )
                    (project_dir / "app.js").write_text(f'console.log("{project_name} initialized by JARVIS.");\n', encoding="utf-8")
                    (project_dir / "README.md").write_text(f"# {project_name}\nWeb application scaffolded by JARVIS.\n", encoding="utf-8")
                    created_files.extend(["index.html", "app.js", "README.md"])
                else:
                    (project_dir / "README.md").write_text(f"# {project_name}\n\nCreated by JARVIS.\n", encoding="utf-8")
                    created_files.append("README.md")

            # Try git init
            try:
                subprocess.run(["git", "init"], cwd=project_dir, capture_output=True, timeout=10)
            except Exception:
                pass

            summary = f"Created new {project_type} project at {project_dir} with {len(created_files)} files: {', '.join(created_files)}."
            if player and hasattr(player, "show_content"):
                player.show_content(f"Project Created: {project_name}", f"### Location: `{project_dir}`\n\n**Files generated:**\n" + "\n".join(f"- `{f}`" for f in created_files))
            if player and hasattr(player, "write_log"):
                player.write_log(f"CODE: Scaffolded project '{project_name}' ({len(created_files)} files)")

            return summary
        except Exception as e:
            return f"Failed to create project: {e}"

    return f"Unknown action '{action}'. Supported actions: read, edit, write, search, command, create_project."


TOOL = {
    "name": "autonomous_code_agent",
    "description": (
        "Antigravity-grade autonomous software engineering tool for JARVIS. "
        "Allows reading file contents, performing surgical code edits with AST syntax verification, "
        "writing new code files, searching codebases across directories, executing terminal commands, "
        "and creating brand new project structures/scaffolds from scratch."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "Operation: read | edit | write | search | command | create_project",
            },
            "path": {
                "type": "STRING",
                "description": "Target file or directory path (absolute or relative)",
            },
            "target": {
                "type": "STRING",
                "description": "Exact text or code snippet to replace (for action='edit')",
            },
            "replacement": {
                "type": "STRING",
                "description": "New replacement code snippet (for action='edit')",
            },
            "content": {
                "type": "STRING",
                "description": "Full file content to create or write (for action='write')",
            },
            "start_line": {
                "type": "INTEGER",
                "description": "Starting line number for reading (for action='read')",
            },
            "end_line": {
                "type": "INTEGER",
                "description": "Ending line number for reading (for action='read')",
            },
            "query": {
                "type": "STRING",
                "description": "Search keyword or regex pattern (for action='search')",
            },
            "command": {
                "type": "STRING",
                "description": "Shell/terminal command to execute (for action='command')",
            },
        },
        "required": ["action"],
    },
    "handler": autonomous_code_agent,
}

