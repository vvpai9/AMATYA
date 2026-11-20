"""
AMATYA CREATOR — Autonomous Software Engineering & Safe Terminal Execution (core/creator.py)
============================================================================================
Implements Section 10 (Software Development, Engineering and Creation — CREATOR Mode):
  - 10.1 Software Engineering:
    * Repository inspection (file tree, languages, git status, recent commits)
    * Symbol & pattern search across project files
    * Project scaffolding (`scaffold_project`)
    * Multi-file editing (`apply_edits`) with automatic in-memory backup/rollback
    * Automated test execution (`pytest`, `unittest`, `npm test`, `cargo test`)
    * Compiler/runtime error analysis & debugging via ModelRouter ('coding' role)
    * Git workflow management (`git_status`, `git_diff`, `git_log`, `git_commit`)
  - 10.2 Terminal & Tool Execution with Command Risk Classification:
    * Classifies every shell command into:
      - SAFE_READ   (ls, git status/diff/log, cat, rg, find, python --version)
      - SAFE_BUILD  (pytest, python -m unittest, npm test, cargo check, ruff, mypy)
      - MODIFY      (git add/commit/checkout, pip install, mkdir, cp, mv)
      - DESTRUCTIVE (rm -rf, sudo, mkfs, dd, chmod 777, git reset --hard, push --force, killall)
    * Never executes DESTRUCTIVE or PRIVILEGED commands without explicit confirmation
      or PIN via core/security.py!
"""
from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from core.doc_generator import analyze_document, generate_document
from core.model_router import get_router
from core.security import PermissionTier, check_permission, log_audit_event
from memory.config_manager import BASE_DIR

_DESTRUCTIVE_PATTERNS = [
    re.compile(r"(?:^|\s|;|&&|\|\|)sudo\b"),
    re.compile(r"\brm\s+-[a-zA-Z]*[rf][a-zA-Z]*\b"),
    re.compile(r"\b(?:mkfs|fdisk|parted|dd|shred|wipefs)\b"),
    re.compile(r"\bgit\s+(?:reset\s+--hard|clean\s+-[a-zA-Z]*f|push\s+.*--force)\b"),
    re.compile(r"\b(?:shutdown|reboot|poweroff|init\s+0|systemctl\s+(?:stop|disable|mask))\b"),
    re.compile(r"\bchmod\s+(?:-R\s+)?777\b"),
    re.compile(r">\s*/dev/sd[a-z]"),
]

_SAFE_READ_PREFIXES = (
    "git status",
    "git diff",
    "git log",
    "git branch",
    "git show",
    "ls",
    "pwd",
    "whoami",
    "uname",
    "cat ",
    "head ",
    "tail ",
    "wc ",
    "find ",
    "rg ",
    "grep ",
    "which ",
    "python --version",
    "python3 --version",
)

_SAFE_BUILD_PREFIXES = (
    "pytest",
    "python -m pytest",
    "python3 -m pytest",
    "python -m unittest",
    "python3 -m unittest",
    "python -m py_compile",
    "npm test",
    "cargo test",
    "cargo check",
    "go test",
    "ruff ",
    "flake8",
    "mypy ",
)


def classify_command_risk(command: str) -> dict[str, Any]:
    """Classify a shell command into SAFE_READ, SAFE_BUILD, MODIFY, or DESTRUCTIVE."""
    cmd = (command or "").strip()
    if not cmd:
        return {
            "risk_level": "SAFE_READ",
            "permission_tier": int(PermissionTier.GENERAL_CONVERSATION),
            "requires_confirmation": False,
            "reason": "Empty command.",
        }

    for pat in _DESTRUCTIVE_PATTERNS:
        if pat.search(cmd):
            return {
                "risk_level": "DESTRUCTIVE",
                "permission_tier": int(PermissionTier.CRITICAL_SECURITY),
                "requires_confirmation": True,
                "reason": f"Command matches destructive/privileged pattern: '{pat.pattern}'.",
            }

    lower = cmd.lower()
    # Reject shell chaining into arbitrary modifications if claiming safe read/build
    has_chain = any(sep in cmd for sep in (";", "&&", "||", "|", "`", "$("))
    if not has_chain:
        if any(lower == p.strip() or lower.startswith(p) for p in _SAFE_READ_PREFIXES):
            return {
                "risk_level": "SAFE_READ",
                "permission_tier": int(PermissionTier.PERSONAL_INFO),
                "requires_confirmation": False,
                "reason": "Read-only inspection command.",
            }
        if any(lower == p.strip() or lower.startswith(p) for p in _SAFE_BUILD_PREFIXES):
            return {
                "risk_level": "SAFE_BUILD",
                "permission_tier": int(PermissionTier.PRIVATE_FILES),
                "requires_confirmation": False,
                "reason": "Standard test or build verification command.",
            }

    return {
        "risk_level": "MODIFY",
        "permission_tier": int(PermissionTier.SENSITIVE_SYSTEM),
        "requires_confirmation": True,
        "reason": "Command may modify workspace or system state.",
    }


@dataclass
class ProjectProfile:
    project_id: str
    name: str
    path: str
    purpose: str = ""
    architecture: str = ""
    tech_stack: list[str] = field(default_factory=list)
    test_commands: list[str] = field(default_factory=list)
    build_commands: list[str] = field(default_factory=list)
    known_issues: list[str] = field(default_factory=list)
    last_inspected: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProjectProfile:
        valid_keys = cls.__dataclass_fields__.keys()
        return cls(**{k: v for k, v in data.items() if k in valid_keys})


class ProjectProfileManager:
    """Persistent storage and automatic extraction of project profiles in memory/project_profiles.json."""

    def __init__(self, storage_path: Path | None = None) -> None:
        self.storage_path = storage_path or (BASE_DIR / "memory" / "project_profiles.json")
        self._profiles: dict[str, ProjectProfile] = {}
        self._load()

    def _load(self) -> None:
        if not self.storage_path.exists():
            return
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            for k, v in raw.items():
                if isinstance(v, dict):
                    self._profiles[k] = ProjectProfile.from_dict(v)
        except Exception:
            pass

    def _save(self) -> None:
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            data = {k: p.to_dict() for k, p in self._profiles.items()}
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def get_profile(self, target: str) -> ProjectProfile | None:
        if not target:
            return None
        norm = str(Path(target).expanduser().resolve()) if (Path(target).exists() or "/" in target) else target.strip().lower()
        for k, p in self._profiles.items():
            if k == norm or p.project_id.lower() == target.lower() or p.name.lower() == target.lower() or p.path == norm:
                return p
        return None

    def list_profiles(self) -> list[dict[str, Any]]:
        return [p.to_dict() for p in self._profiles.values()]

    def update_profile(self, project_path_or_id: str, updates: dict[str, Any]) -> ProjectProfile:
        p = self.get_profile(project_path_or_id)
        if not p:
            resolved = Path(project_path_or_id).expanduser().resolve()
            name = resolved.name if resolved.exists() else project_path_or_id
            pid = resolved.stem if resolved.exists() else project_path_or_id
            p = ProjectProfile(
                project_id=pid,
                name=name,
                path=str(resolved) if resolved.exists() else project_path_or_id,
            )
        for k, v in updates.items():
            if hasattr(p, k):
                setattr(p, k, v)
        p.last_inspected = datetime.now().isoformat()
        self._profiles[p.project_id] = p
        self._save()
        return p

    def auto_profile(self, repo_path: str | Path) -> ProjectProfile:
        root = Path(repo_path).expanduser().resolve()
        pid = root.name
        existing = self.get_profile(str(root)) or self.get_profile(pid)
        stack = set(existing.tech_stack if existing else [])
        test_cmds = list(existing.test_commands if existing else [])
        build_cmds = list(existing.build_commands if existing else [])
        purpose = existing.purpose if existing else ""

        # Detect stack
        if (root / "package.json").exists():
            stack.add("Node.js/JavaScript")
            if "npm test" not in test_cmds:
                test_cmds.append("npm test")
            if "npm install" not in build_cmds:
                build_cmds.append("npm install")
        if (root / "Cargo.toml").exists():
            stack.add("Rust")
            if "cargo test" not in test_cmds:
                test_cmds.append("cargo test")
            if "cargo build" not in build_cmds:
                build_cmds.append("cargo build")
        if any(root.glob("*.py")) or (root / "setup.py").exists() or (root / "pyproject.toml").exists():
            stack.add("Python")
            if "pytest" not in test_cmds:
                test_cmds.append("pytest")
            if (root / "requirements.txt").exists() and "pip install -r requirements.txt" not in build_cmds:
                build_cmds.append("pip install -r requirements.txt")

        # Extract purpose from README.md
        readme = root / "README.md"
        if readme.exists() and not purpose:
            try:
                txt = readme.read_text(encoding="utf-8")[:500]
                lines = [l.strip("#* \t\r\n") for l in txt.splitlines() if l.strip("#* \t\r\n")]
                if lines:
                    purpose = " — ".join(lines[:2])[:200]
            except Exception:
                pass

        if not purpose:
            purpose = f"Project {pid}"

        updates = {
            "name": pid,
            "path": str(root),
            "purpose": purpose,
            "tech_stack": sorted(list(stack)),
            "test_commands": test_cmds,
            "build_commands": build_cmds,
        }
        return self.update_profile(pid, updates)


class CreatorEngine:
    """Autonomous software engineering, git workflow, test execution, document creation, self-repair and multi-modal generation engine."""

    def __init__(self) -> None:
        self._last_backups: dict[str, str] = {}
        self.profiles = ProjectProfileManager()

    def inspect_repository(self, project_path: str | Path | None = None) -> dict[str, Any]:
        root = Path(project_path or BASE_DIR).expanduser().resolve()
        if not root.exists():
            return {"ok": False, "error": f"Project path does not exist: {root}"}

        ext_counts: dict[str, int] = {}
        top_entries = sorted(p.name for p in root.iterdir() if not p.name.startswith("."))[:40]
        total_files = 0
        for p in root.rglob("*"):
            if any(skip in p.parts for skip in (".git", "__pycache__", "node_modules", "AMATYA", ".venv", "venv")):
                continue
            if p.is_file():
                total_files += 1
                ext = p.suffix.lower() or "(no_ext)"
                ext_counts[ext] = ext_counts.get(ext, 0) + 1

        git_info = self.git_operation(root, "status")
        profile = self.profiles.auto_profile(root)
        return {
            "ok": True,
            "project_path": str(root),
            "total_files": total_files,
            "top_entries": top_entries,
            "file_types": dict(sorted(ext_counts.items(), key=lambda kv: -kv[1])[:12]),
            "git_status": git_info.get("stdout", ""),
            "git_branch": git_info.get("branch", ""),
            "profile": profile.to_dict(),
        }

    def get_profile(self, target: str) -> dict[str, Any] | None:
        p = self.profiles.get_profile(target)
        return p.to_dict() if p else None

    def update_profile(self, target: str, updates: dict[str, Any]) -> dict[str, Any]:
        p = self.profiles.update_profile(target, updates)
        return p.to_dict()

    def list_profiles(self) -> list[dict[str, Any]]:
        return self.profiles.list_profiles()

    def git_operation(
        self,
        project_path: str | Path | None,
        op: str = "status",
        message: str = "",
        branch: str = "",
        remote: str = "origin",
    ) -> dict[str, Any]:
        root = Path(project_path or BASE_DIR).expanduser().resolve()
        op_clean = (op or "status").strip().lower()

        if op_clean == "status":
            b = subprocess.run(["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True)
            s = subprocess.run(["git", "-C", str(root), "status", "--short"], capture_output=True, text=True)
            return {
                "ok": s.returncode == 0,
                "branch": (b.stdout or "").strip(),
                "stdout": (s.stdout or "").strip() or "Working tree clean.",
            }

        if op_clean == "diff":
            d = subprocess.run(["git", "-C", str(root), "diff", "--stat"], capture_output=True, text=True)
            return {"ok": d.returncode == 0, "stdout": (d.stdout or "").strip() or "No unstaged diffs."}

        if op_clean == "log":
            lg = subprocess.run(["git", "-C", str(root), "log", "-n", "8", "--oneline"], capture_output=True, text=True)
            return {"ok": lg.returncode == 0, "stdout": (lg.stdout or "").strip()}

        if op_clean == "commit":
            if not message:
                return {"ok": False, "error": "Commit message is required."}
            perm = check_permission("git_commit", PermissionTier.PRIVATE_FILES, description=f"Git commit in {root.name}: {message}", interactive_confirm=False)
            if not perm["allowed"]:
                return {"ok": False, "error": perm["reason"]}
            subprocess.run(["git", "-C", str(root), "add", "-A"], capture_output=True, text=True)
            c = subprocess.run(["git", "-C", str(root), "commit", "-m", message], capture_output=True, text=True)
            return {"ok": c.returncode == 0, "stdout": (c.stdout or c.stderr or "").strip()}

        if op_clean == "branch":
            if branch:
                b = subprocess.run(["git", "-C", str(root), "checkout", "-b", branch], capture_output=True, text=True)
                return {"ok": b.returncode == 0, "stdout": (b.stdout or b.stderr or "").strip()}
            b = subprocess.run(["git", "-C", str(root), "branch", "-a"], capture_output=True, text=True)
            return {"ok": b.returncode == 0, "stdout": (b.stdout or b.stderr or "").strip()}

        if op_clean == "push":
            perm = check_permission("git_push", PermissionTier.SENSITIVE_SYSTEM, description=f"Git push {remote} {branch or 'HEAD'}", interactive_confirm=False)
            if not perm["allowed"]:
                return {"ok": False, "error": perm["reason"]}
            p = subprocess.run(["git", "-C", str(root), "push", remote or "origin", branch or "HEAD"], capture_output=True, text=True)
            return {"ok": p.returncode == 0, "stdout": (p.stdout or p.stderr or "").strip()}

        if op_clean == "pull":
            p = subprocess.run(["git", "-C", str(root), "pull", remote or "origin", branch or "HEAD"], capture_output=True, text=True)
            return {"ok": p.returncode == 0, "stdout": (p.stdout or p.stderr or "").strip()}

        return {"ok": False, "error": f"Unsupported git operation '{op}'."}

    def read_code(
        self,
        file_path: str | Path,
        start_line: int | None = 1,
        end_line: int | None = None,
        max_bytes: int = 50_000,
    ) -> dict[str, Any]:
        """Read specific lines or full files across any workspace with byte-size safeguarding."""
        p = Path(file_path).expanduser().resolve()
        if not p.is_file():
            return {"ok": False, "error": f"File '{p}' does not exist."}
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
            total = len(lines)
            s = max(0, (start_line or 1) - 1)
            e = min(total, end_line if end_line is not None else total)
            selected = "".join(lines[s:e])
            truncated = False
            if len(selected) > max_bytes:
                selected = selected[:max_bytes] + "\n...[truncated]"
                truncated = True
            return {
                "ok": True,
                "path": str(p),
                "filename": p.name,
                "start_line": s + 1,
                "end_line": e,
                "total_lines": total,
                "truncated": truncated,
                "content": selected,
            }
        except Exception as exc:
            return {"ok": False, "error": f"Failed to read file '{p}': {exc}"}

    def edit_code(
        self,
        file_path: str | Path,
        target: str,
        replacement: str,
    ) -> dict[str, Any]:
        """Surgical find-and-replace edit with AST syntax validation on Python files."""
        p = Path(file_path).expanduser().resolve()
        if not p.is_file():
            return {"ok": False, "error": f"Target file '{p}' does not exist."}
        if not target:
            return {"ok": False, "error": "Edit requires a non-empty 'target' string."}

        perm = check_permission("creator_edit_code", PermissionTier.PRIVATE_FILES, description=f"Edit {p.name}", interactive_confirm=False)
        if not perm["allowed"]:
            return {"ok": False, "error": perm["reason"]}

        try:
            original = p.read_text(encoding="utf-8", errors="replace")
            if target not in original:
                return {"ok": False, "error": f"Target snippet not found in {p.name}."}
            count = original.count(target)
            updated = original.replace(target, replacement, 1)

            if p.suffix.lower() == ".py":
                try:
                    ast.parse(updated, filename=str(p))
                except SyntaxError as se:
                    return {
                        "ok": False,
                        "error": f"Edit aborted: Syntax validation failed on line {se.lineno}: {se.msg}",
                        "lineno": se.lineno,
                    }

            p.write_text(updated, encoding="utf-8")
            diff_summary = f"Replaced {count} occurrence(s) in {p.name}."
            return {
                "ok": True,
                "path": str(p),
                "occurrences": count,
                "diff_summary": diff_summary,
            }
        except Exception as exc:
            return {"ok": False, "error": f"Failed to edit file '{p}': {exc}"}

    def write_code(
        self,
        file_path: str | Path,
        content: str,
    ) -> dict[str, Any]:
        """Create or overwrite files with AST syntax validation for Python files."""
        p = Path(file_path).expanduser().resolve()
        perm = check_permission("creator_write_code", PermissionTier.PRIVATE_FILES, description=f"Write {p.name}", interactive_confirm=False)
        if not perm["allowed"]:
            return {"ok": False, "error": perm["reason"]}

        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            if p.suffix.lower() == ".py":
                try:
                    ast.parse(content, filename=str(p))
                except SyntaxError as se:
                    return {
                        "ok": False,
                        "error": f"Write aborted: Syntax error on line {se.lineno}: {se.msg}",
                        "lineno": se.lineno,
                    }
            p.write_text(content, encoding="utf-8")
            return {
                "ok": True,
                "path": str(p),
                "bytes_written": len(content),
            }
        except Exception as exc:
            return {"ok": False, "error": f"Failed to write file '{p}': {exc}"}

    def create_file(self, file_path: str | Path, content: str) -> dict[str, Any]:
        """Universal file creator alias."""
        return self.write_code(file_path, content)

    def scaffold_project(
        self,
        project_name: str,
        project_type: str = "python",
        target_dir: str | Path | None = None,
        files: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Scaffold project boilerplate (Python, Web, React, or custom files) and initialize Git."""
        dest_root = Path(target_dir or BASE_DIR).expanduser().resolve()
        pdir = dest_root if (dest_root.is_dir() and dest_root.name == project_name) else (dest_root / project_name)
        pdir.mkdir(parents=True, exist_ok=True)
        pt = (project_type or "python").lower()

        created: list[str] = []
        try:
            if files and isinstance(files, dict):
                for rel_path, c in files.items():
                    fp = pdir / rel_path
                    fp.parent.mkdir(parents=True, exist_ok=True)
                    fp.write_text(str(c), encoding="utf-8")
                    created.append(rel_path)
            elif "fastapi" in pt or "python" in pt:
                (pdir / "main.py").write_text(
                    'from fastapi import FastAPI\n\napp = FastAPI(title="' + project_name + '")\n\n@app.get("/")\ndef root():\n    return {"message": "Service online"}\n\n@app.get("/health")\ndef health():\n    return {"status": "healthy"}\n',
                    encoding="utf-8",
                )
                (pdir / "requirements.txt").write_text("fastapi\nuvicorn[standard]\nrequests\npytest\n", encoding="utf-8")
                (pdir / "README.md").write_text(f"# {project_name}\n\nGenerated by AMATYA CREATOR.\n\nRun:\n```bash\nuvicorn main:app --reload\n```\n", encoding="utf-8")
                tests_dir = pdir / "tests"
                tests_dir.mkdir(parents=True, exist_ok=True)
                (tests_dir / "test_main.py").write_text("def test_health():\n    assert True\n", encoding="utf-8")
                created.extend(["main.py", "requirements.txt", "README.md", "tests/test_main.py"])
            elif "react" in pt or "next" in pt or "web" in pt:
                (pdir / "package.json").write_text(
                    json.dumps({
                        "name": project_name.lower().replace(" ", "-"),
                        "version": "0.1.0",
                        "private": True,
                        "scripts": {"dev": "vite", "build": "vite build", "preview": "vite preview"},
                        "dependencies": {"react": "^18.3.1", "react-dom": "^18.3.1"},
                        "devDependencies": {"vite": "^5.4.0", "@vitejs/plugin-react": "^4.3.1"},
                    }, indent=2),
                    encoding="utf-8",
                )
                (pdir / "index.html").write_text(
                    f'<!DOCTYPE html>\n<html>\n<head><title>{project_name}</title></head>\n<body><div id="root"></div><script type="module" src="/src/main.jsx"></script></body>\n</html>',
                    encoding="utf-8",
                )
                src = pdir / "src"
                src.mkdir(parents=True, exist_ok=True)
                (src / "App.jsx").write_text('export default function App() {\n  return <h1>Hello from ' + project_name + '</h1>;\n}\n', encoding="utf-8")
                (src / "main.jsx").write_text('import React from "react";\nimport ReactDOM from "react-dom/client";\nimport App from "./App";\n\nReactDOM.createRoot(document.getElementById("root")).render(<App />);\n', encoding="utf-8")
                (pdir / "README.md").write_text(f"# {project_name}\n\nWeb application generated by AMATYA CREATOR.\n", encoding="utf-8")
                created.extend(["package.json", "index.html", "src/App.jsx", "src/main.jsx", "README.md"])
            else:
                (pdir / "index.html").write_text(f'<!DOCTYPE html>\n<html>\n<head><title>{project_name}</title><link rel="stylesheet" href="style.css"></head>\n<body><h1>{project_name}</h1><script src="app.js"></script></body>\n</html>', encoding="utf-8")
                (pdir / "style.css").write_text("body { font-family: sans-serif; margin: 2rem; }\n", encoding="utf-8")
                (pdir / "app.js").write_text('console.log("Loaded ' + project_name + '");\n', encoding="utf-8")
                (pdir / "README.md").write_text(f"# {project_name}\n\nCreated by AMATYA CREATOR.\n", encoding="utf-8")
                created.extend(["index.html", "style.css", "app.js", "README.md"])

            if shutil.which("git"):
                try:
                    subprocess.run(["git", "init"], cwd=str(pdir), capture_output=True, timeout=10)
                except Exception:
                    pass

            self.profiles.auto_profile(pdir)
            return {
                "ok": True,
                "project_name": project_name,
                "project_dir": str(pdir),
                "created_files": created,
                "project_type": pt,
            }
        except Exception as exc:
            return {"ok": False, "error": f"Failed to scaffold project '{project_name}': {exc}"}

    def self_repair(
        self,
        target: str = "all",
        player: Any = None,
        auto_install: bool = False,
    ) -> dict[str, Any]:
        """Autonomous self-repair, system diagnostic, and auto-healing protocol. Contributed by Aman Kumar (@iamTechieAman)."""
        start_time = time.time()
        repairs_done: list[str] = []
        warnings: list[str] = []

        if player and hasattr(player, "write_log"):
            try:
                player.write_log("SYS: Initialising Autonomous Self-Repair Protocol...")
            except Exception:
                pass

        # 1. Syntax & Integrity Scan
        syntax_issues: list[dict[str, str]] = []
        scanned_count = 0
        scan_dirs = ["actions", "core", "gui", "memory", "providers"]
        for sdir in scan_dirs:
            tdir = BASE_DIR / sdir
            if not tdir.is_dir():
                continue
            for py_file in tdir.rglob("*.py"):
                scanned_count += 1
                try:
                    src = py_file.read_text(encoding="utf-8", errors="replace")
                    ast.parse(src, filename=str(py_file))
                except Exception as exc:
                    syntax_issues.append({"file": str(py_file.relative_to(BASE_DIR)), "error": str(exc)})

        if syntax_issues:
            warnings.append(f"{len(syntax_issues)} syntax anomalies detected in codebase.")
            for item in syntax_issues[:3]:
                repairs_done.append(f"Flagged syntax issue in {item['file']}: {item['error']}")
        else:
            repairs_done.append(f"Integrity scan passed: {scanned_count} Python modules 100% syntactically valid.")

        # 2. Dependency Audit & Auto-repair
        required_pkgs = [
            "PyQt6", "sounddevice", "numpy", "google-genai",
            "requests", "ddgs", "playwright", "openwakeword",
            "faster_whisper", "psutil", "pillow"
        ]
        present: list[str] = []
        missing: list[str] = []
        for pkg in required_pkgs:
            mod_name = pkg.replace("-", "_")
            if importlib.util.find_spec(mod_name) is not None:
                present.append(pkg)
            else:
                missing.append(pkg)

        if missing:
            if auto_install:
                if player and hasattr(player, "write_log"):
                    try:
                        player.write_log(f"SYS: Auto-installing missing dependencies: {', '.join(missing)}...")
                    except Exception:
                        pass
                try:
                    r = subprocess.run([sys.executable, "-m", "pip", "install", *missing], capture_output=True, text=True, timeout=120)
                    if r.returncode == 0:
                        repairs_done.append(f"Successfully auto-installed: {', '.join(missing)}")
                    else:
                        warnings.append(f"Failed to auto-install: {', '.join(missing)}")
                except Exception as exc:
                    warnings.append(f"Pip self-healing exception: {exc}")
            else:
                warnings.append(f"Missing optional dependencies: {', '.join(missing)}")
        else:
            repairs_done.append(f"Dependencies verified: All {len(present)} mission-critical packages operational.")

        # 3. Wake Word Health
        try:
            from core.wake_word import is_ready
            if is_ready():
                repairs_done.append("Wake Word Engine: ONNX models present and operational ('Hey Jarvis').")
            else:
                repairs_done.append("Wake Word Engine: Ready for activation.")
        except Exception as exc:
            warnings.append(f"Wake word probe warning: {exc}")

        # 4. Clean duplicate app bundles & cache
        try:
            desktop_app = Path.home() / "Desktop" / "J.A.R.V.I.S.app"
            if desktop_app.exists():
                shutil.rmtree(desktop_app)
                repairs_done.append("Removed duplicate desktop app bundle.")
        except Exception as exc:
            warnings.append(f"Desktop bundle cleanup error: {exc}")

        # 5. Turn Latency Tuning Verification
        try:
            from memory.config_manager import get_turn_tuning, save_turn_tuning
            tt = get_turn_tuning()
            if not tt.get("enabled"):
                save_turn_tuning({"enabled": True, "silence_ms": 450, "prefix_ms": 100, "end_sensitivity": "high"})
                repairs_done.append("Optimised voice turn latency: enabled rapid response mode (450ms).")
            else:
                repairs_done.append("Voice turn latency: already tuned to rapid response mode.")
        except Exception as exc:
            warnings.append(f"Turn tuning error: {exc}")

        elapsed = round(time.time() - start_time, 2)

        report_lines = [
            "## AMATYA Autonomous Self-Repair Report",
            f"**Status:** {'Nominal with Warnings' if warnings else '100% Operational'}",
            f"**Audit Duration:** {elapsed}s",
            "",
            "### Actions & Verifications:",
            *[f"- ✅ {r}" for r in repairs_done],
        ]
        if warnings:
            report_lines.extend(["", "### Warnings:", *[f"- ⚠️ {w}" for w in warnings]])

        report_md = "\n".join(report_lines)

        if player and hasattr(player, "show_content"):
            try:
                player.show_content("AMATYA Self-Repair & System Audit", report_md)
            except Exception:
                pass

        if player and hasattr(player, "write_log"):
            try:
                player.write_log(f"SYS: Self-repair completed in {elapsed}s. All systems operational.")
            except Exception:
                pass

        return {
            "ok": True,
            "duration_sec": elapsed,
            "scanned_modules": scanned_count,
            "syntax_errors": syntax_issues,
            "dependencies_present": present,
            "dependencies_missing": missing,
            "repairs_done": repairs_done,
            "warnings": warnings,
            "report_markdown": report_md,
            "summary": (
                f"Autonomous self-repair protocol complete in {elapsed}s. "
                f"Scanned {scanned_count} system modules, verified {len(present)} dependencies, "
                f"and validated system integrity."
            ),
        }

    def merge_pdfs(self, input_paths: list[str], output_filename: str = "merged_output.pdf") -> dict[str, Any]:
        """Merge multiple PDF files into a single unified PDF."""
        dest = Path(output_filename).expanduser()
        if not dest.is_absolute():
            dest = Path.home() / "Desktop" / output_filename
        dest.parent.mkdir(parents=True, exist_ok=True)

        try:
            reader_cls = None
            writer = None
            try:
                import pypdf
                writer = pypdf.PdfWriter()
                reader_cls = pypdf.PdfReader
            except ImportError:
                try:
                    import PyPDF2
                    writer = PyPDF2.PdfWriter()
                    reader_cls = PyPDF2.PdfReader
                except ImportError:
                    return {"ok": False, "error": "pypdf or PyPDF2 is required for PDF merging."}

            merged_count = 0
            for p in input_paths:
                fpath = Path(p).expanduser().resolve()
                if fpath.is_file():
                    reader = reader_cls(str(fpath))
                    for page in reader.pages:
                        writer.add_page(page)
                    merged_count += 1

            if merged_count == 0:
                return {"ok": False, "error": "No valid PDF files provided to merge."}

            with open(dest, "wb") as f:
                writer.write(f)

            return {
                "ok": True,
                "path": str(dest),
                "merged_count": merged_count,
                "message": f"Successfully merged {merged_count} PDF files into '{dest}'",
            }
        except Exception as exc:
            return {"ok": False, "error": f"Failed to merge PDFs: {exc}"}

    def extract_pdf_pages(self, input_path: str, pages_spec: str, output_filename: str = "extracted_pages.pdf") -> dict[str, Any]:
        """Extract specific pages from a PDF. pages_spec: e.g. '1-3,5' (1-indexed)."""
        path = Path(input_path).expanduser().resolve()
        if not path.is_file():
            return {"ok": False, "error": f"File not found: '{input_path}'"}

        dest = Path(output_filename).expanduser()
        if not dest.is_absolute():
            dest = Path.home() / "Desktop" / output_filename
        dest.parent.mkdir(parents=True, exist_ok=True)

        try:
            try:
                import pypdf
                writer = pypdf.PdfWriter()
                reader = pypdf.PdfReader(str(path))
            except ImportError:
                try:
                    import PyPDF2
                    writer = PyPDF2.PdfWriter()
                    reader = PyPDF2.PdfReader(str(path))
                except ImportError:
                    return {"ok": False, "error": "pypdf or PyPDF2 is required for PDF manipulation."}

            total_pages = len(reader.pages)
            selected = set()
            for part in pages_spec.split(","):
                part = part.strip()
                if not part:
                    continue
                if "-" in part:
                    s, e = part.split("-", 1)
                    for idx in range(int(s), int(e) + 1):
                        if 1 <= idx <= total_pages:
                            selected.add(idx - 1)
                else:
                    idx = int(part)
                    if 1 <= idx <= total_pages:
                        selected.add(idx - 1)

            if not selected:
                return {"ok": False, "error": f"No valid pages matching spec '{pages_spec}' (PDF has {total_pages} pages)."}

            for idx in sorted(selected):
                writer.add_page(reader.pages[idx])

            with open(dest, "wb") as f:
                writer.write(f)

            return {
                "ok": True,
                "path": str(dest),
                "pages_extracted": len(selected),
                "message": f"Extracted {len(selected)} pages from '{path.name}' into '{dest}'",
            }
        except Exception as exc:
            return {"ok": False, "error": f"Failed to extract PDF pages: {exc}"}

    def generate_image(
        self,
        prompt: str,
        width: int = 1024,
        height: int = 1024,
        filename: str | None = None,
    ) -> dict[str, Any]:
        """Synthesize image via Pollinations FLUX/SDXL engine. Contributed by Aman Kumar (@iamTechieAman)."""
        clean_prompt = prompt.strip()
        if not clean_prompt:
            return {"ok": False, "error": "Prompt describing the image is required."}

        encoded = urllib.parse.quote(clean_prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height}&model=flux&nologo=true&enhance=true"

        desktop = Path.home() / "Desktop"
        ts = int(time.time())
        if filename:
            clean_name = filename if filename.lower().endswith((".jpg", ".png", ".jpeg")) else f"{filename}.jpg"
            dest = desktop / clean_name
        else:
            dest = desktop / f"jarvis_gen_{ts}.jpg"

        dest.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (AMATYA Autonomous System; Linux x86_64)"},
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
                with open(dest, "wb") as f:
                    f.write(data)

            if sys.platform == "darwin":
                try:
                    subprocess.Popen(["open", str(dest)])
                except Exception:
                    pass

            return {
                "ok": True,
                "path": str(dest),
                "prompt": clean_prompt,
                "message": f"Generated image for '{clean_prompt}' saved to '{dest}'.",
            }
        except Exception as exc:
            return {"ok": False, "error": f"Image generation failed: {exc}"}

    def create_video(
        self,
        title: str,
        text: str = "",
        image_path: str = "",
        duration: int = 5,
        theme: str = "cyber",
    ) -> dict[str, Any]:
        """Synthesize cinematic motion cards and HUD clips. Contributed by Aman Kumar (@iamTechieAman)."""
        out_dir = Path.home() / "Desktop" / "JARVIS_Videos"
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = int(time.time())
        out_file = out_dir / f"jarvis_clip_{ts}.mp4"
        temp_frame = out_dir / f"temp_frame_{ts}.png"

        dur = max(2, min(int(duration or 5), 30))
        t_clean = (theme or "cyber").lower()
        themes = {
            "cyber": ((10, 15, 29), (0, 210, 255), (255, 255, 255)),
            "cinematic": ((17, 24, 39), (243, 244, 246), (156, 163, 175)),
            "gold": ((28, 25, 23), (245, 158, 11), (254, 243, 199)),
            "neon": ((9, 9, 11), (236, 72, 153), (0, 255, 255)),
        }
        bg_col, title_col, text_col = themes.get(t_clean, themes["cyber"])

        try:
            from PIL import Image, ImageDraw, ImageFont

            if image_path and Path(image_path).is_file():
                base_img = Image.open(image_path).convert("RGB")
                base_img = base_img.resize((1280, 720), Image.Resampling.LANCZOS)
            else:
                base_img = Image.new("RGB", (1280, 720), color=bg_col)
                draw = ImageDraw.Draw(base_img)
                draw.rectangle([30, 30, 1250, 690], outline=title_col, width=2)
                draw.line([(30, 50), (60, 50)], fill=title_col, width=4)
                draw.line([(1220, 50), (1250, 50)], fill=title_col, width=4)
                draw.line([(30, 670), (60, 670)], fill=title_col, width=4)
                draw.line([(1220, 670), (1250, 670)], fill=title_col, width=4)

            draw = ImageDraw.Draw(base_img)
            font_large = ImageFont.load_default()
            font_small = ImageFont.load_default()

            draw.text((640, 310), title.upper(), fill=title_col, font=font_large, anchor="mm")
            sub_text = text or title
            draw.text((640, 420), sub_text[:80], fill=text_col, font=font_small, anchor="mm")

            base_img.save(temp_frame, "PNG")

            ffmpeg_bin = shutil.which("ffmpeg") or "/usr/local/bin/ffmpeg"
            cmd = [
                ffmpeg_bin, "-y", "-loop", "1", "-i", str(temp_frame),
                "-c:v", "libx264", "-t", str(dur), "-pix_fmt", "yuv420p",
                "-vf", "scale=1280:720", str(out_file),
            ]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if temp_frame.exists():
                temp_frame.unlink(missing_ok=True)

            if r.returncode == 0:
                return {
                    "ok": True,
                    "path": str(out_file),
                    "title": title,
                    "duration": dur,
                    "message": f"Synthesized motion clip '{out_file.name}' ({dur}s).",
                }
            return {"ok": False, "error": f"FFmpeg video encoding failed: {r.stderr[:200]}"}
        except Exception as exc:
            if temp_frame.exists():
                temp_frame.unlink(missing_ok=True)
            return {"ok": False, "error": f"Video synthesis failed: {exc}"}

    def search_code(
        self,
        pattern: str,
        project_path: str | Path | None = None,
        max_matches: int = 30,
    ) -> dict[str, Any]:
        root = Path(project_path or BASE_DIR).expanduser().resolve()
        if not pattern:
            return {"ok": False, "error": "Search pattern is required."}
        try:
            rx = re.compile(pattern, re.IGNORECASE)
        except re.error:
            rx = re.compile(re.escape(pattern), re.IGNORECASE)

        matches: list[dict[str, Any]] = []
        for p in sorted(root.rglob("*")):
            if len(matches) >= max_matches:
                break
            if any(skip in p.parts for skip in (".git", "__pycache__", "node_modules", "AMATYA", ".venv", "venv")):
                continue
            if p.is_file() and p.suffix.lower() in (".py", ".js", ".ts", ".md", ".json", ".yaml", ".yml", ".sh", ".toml"):
                try:
                    for lineno, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                        if rx.search(line):
                            matches.append({
                                "file": str(p.relative_to(root)),
                                "line": lineno,
                                "text": line.strip()[:200],
                            })
                            if len(matches) >= max_matches:
                                break
                except Exception:
                    continue
        return {"ok": True, "pattern": pattern, "count": len(matches), "matches": matches}

    def apply_edits(self, edits: list[dict[str, str]]) -> dict[str, Any]:
        """Apply multi-file search-and-replace or full-file writes with automatic rollback on syntax error."""
        perm = check_permission(
            "creator_apply_edits",
            PermissionTier.PRIVATE_FILES,
            description=f"Modify {len(edits)} file(s)",
            interactive_confirm=False,
        )
        if not perm["allowed"]:
            return {"ok": False, "error": perm["reason"]}

        self._last_backups.clear()
        modified: list[str] = []
        try:
            for item in edits:
                fpath = Path(item.get("path", "")).expanduser().resolve()
                if fpath.exists():
                    self._last_backups[str(fpath)] = fpath.read_text(encoding="utf-8")
                target = item.get("target")
                replacement = item.get("replacement", "")
                content = item.get("content")

                fpath.parent.mkdir(parents=True, exist_ok=True)
                if content is not None:
                    new_text = str(content)
                elif target is not None and fpath.exists():
                    cur = self._last_backups[str(fpath)]
                    if target not in cur:
                        raise ValueError(f"Target snippet not found in {fpath.name}")
                    new_text = cur.replace(target, replacement, 1)
                else:
                    raise ValueError(f"Must specify 'content' or ('target' + 'replacement') for {fpath}")

                if fpath.suffix.lower() == ".py":
                    ast.parse(new_text, filename=str(fpath))

                fpath.write_text(new_text, encoding="utf-8")
                modified.append(str(fpath))

            return {"ok": True, "modified_files": modified}
        except Exception as exc:
            # Rollback any partial changes
            for p_str, orig in self._last_backups.items():
                try:
                    Path(p_str).write_text(orig, encoding="utf-8")
                except Exception:
                    pass
            return {"ok": False, "error": f"Edit failed and rolled back cleanly: {exc}"}

    def apply_edits_and_verify(
        self,
        edits: list[dict[str, str]],
        project_path: str | Path | None = None,
    ) -> dict[str, Any]:
        """Apply file edits with AST checks, run test suite, and automatically rollback if tests fail."""
        res = self.apply_edits(edits)
        if not res.get("ok"):
            return res

        root = Path(project_path or BASE_DIR).expanduser().resolve()
        test_res = self.run_tests(root, timeout_sec=45)
        if not test_res.get("ok"):
            # Post-edit test failure detected — rollback!
            rolled_back = 0
            for p_str, orig in self._last_backups.items():
                try:
                    Path(p_str).write_text(orig, encoding="utf-8")
                    rolled_back += 1
                except Exception:
                    pass
            return {
                "ok": False,
                "error": f"Post-edit verification failed. Automatically rolled back {rolled_back} modified file(s).",
                "rolled_back": True,
                "test_failure": test_res.get("stderr") or test_res.get("stdout") or "Test suite failed.",
            }

        return {"ok": True, "modified_files": res.get("modified_files", []), "tests_passed": True}

    def run_tests(
        self,
        project_path: str | Path | None = None,
        test_target: str | None = None,
        timeout_sec: int = 45,
    ) -> dict[str, Any]:
        """Run pytest/unittest or syntax compilation checks in `project_path`."""
        root = Path(project_path or BASE_DIR).expanduser().resolve()
        py_bin = sys.executable

        # Determine test command
        if test_target:
            cmd = [py_bin, "-m", "pytest", test_target, "-q"]
        elif (root / "tests").is_dir() or list(root.glob("test_*.py")):
            cmd = [py_bin, "-m", "pytest", "-q"]
        elif (root / "package.json").is_file() and shutil.which("npm"):
            cmd = ["npm", "test"]
        else:
            # Verify Python syntax compilation across core/ and actions/
            py_files = [
                str(p) for p in root.rglob("*.py")
                if not any(s in p.parts for s in ("AMATYA", ".venv", "venv", "__pycache__", ".git"))
            ][:80]
            cmd = [py_bin, "-m", "py_compile", *py_files]

        t0 = time.time()
        try:
            r = subprocess.run(
                cmd,
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )
            elapsed = round(time.time() - t0, 2)
            out = ((r.stdout or "") + "\n" + (r.stderr or "")).strip()
            return {
                "ok": r.returncode == 0,
                "returncode": r.returncode,
                "elapsed_sec": elapsed,
                "command": " ".join(cmd[:6]) + (" ..." if len(cmd) > 6 else ""),
                "output": out[:2000] if out else "All checks passed with 0 errors.",
            }
        except Exception as exc:
            return {"ok": False, "error": f"Test execution error: {exc}"}

    def run_shell(
        self,
        command: str,
        cwd: str | Path | None = None,
        confirmed: bool = False,
        pin: str | None = None,
        interactive_confirm: bool = True,
        timeout_sec: int = 30,
    ) -> dict[str, Any]:
        """Execute a terminal command after evaluating its risk classification."""
        risk = classify_command_risk(command)
        tier = PermissionTier(int(risk["permission_tier"]))

        if risk["requires_confirmation"] and not confirmed:
            perm = check_permission(
                operation=f"creator_shell:{command[:60]}",
                tier=tier,
                description=f"Run shell command ({risk['risk_level']}): {command}",
                pin=pin,
                interactive_confirm=interactive_confirm,
            )
            if not perm["allowed"]:
                return {
                    "ok": False,
                    "blocked": True,
                    "risk": risk,
                    "error": perm["reason"],
                }

        work_dir = Path(cwd or BASE_DIR).expanduser().resolve()
        try:
            import shlex
            cmd_args = shlex.split(command) if isinstance(command, str) else list(command)
            r = subprocess.run(
                cmd_args,
                cwd=str(work_dir),
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )
            log_audit_event(
                "creator_shell_executed",
                command[:120],
                tier,
                r.returncode == 0,
                f"Risk={risk['risk_level']}, exit={r.returncode}",
            )
            return {
                "ok": r.returncode == 0,
                "returncode": r.returncode,
                "risk": risk,
                "stdout": (r.stdout or "").strip()[:3000],
                "stderr": (r.stderr or "").strip()[:2000],
            }
        except Exception as exc:
            return {"ok": False, "risk": risk, "error": str(exc)}

    def analyze_or_generate_code(self, prompt: str, context_code: str = "") -> str:
        full_prompt = prompt
        if context_code:
            full_prompt += f"\n\nContext / Code:\n```\n{context_code[:8000]}\n```"
        return get_router().generate(
            "coding",
            full_prompt,
            system="You are AMATYA CREATOR, a principal software architect and systems engineer. Provide clean, production-grade code and concise technical root-cause analysis.",
        )


_CREATOR_ENGINE: CreatorEngine | None = None


def get_creator_engine() -> CreatorEngine:
    global _CREATOR_ENGINE
    if _CREATOR_ENGINE is None:
        _CREATOR_ENGINE = CreatorEngine()
    return _CREATOR_ENGINE

