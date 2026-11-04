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
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
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


class CreatorEngine:
    """Autonomous software engineering, git workflow, test execution, and document creation engine."""

    def __init__(self) -> None:
        self._last_backups: dict[str, str] = {}

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
        return {
            "ok": True,
            "project_path": str(root),
            "total_files": total_files,
            "top_entries": top_entries,
            "file_types": dict(sorted(ext_counts.items(), key=lambda kv: -kv[1])[:12]),
            "git_status": git_info.get("stdout", ""),
            "git_branch": git_info.get("branch", ""),
        }

    def git_operation(
        self,
        project_path: str | Path | None,
        op: str = "status",
        message: str = "",
        branch: str = "",
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

        return {"ok": False, "error": f"Unsupported git operation '{op}'."}

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
            r = subprocess.run(
                command,
                shell=True,
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

