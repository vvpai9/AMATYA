"""
Full-Spectrum Coding & Pipeline Automation Action for JARVIS.
Handles multi-file scaffolding, test/build pipeline execution, Git version control operations,
and terminal command automation with output parsing.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

def run_cmd(cmd: str, cwd: Optional[str] = None, timeout: int = 60) -> dict:
    """Run shell command and return stdout, stderr, and exit code."""
    try:
        res = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd or os.getcwd(),
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return {
            "stdout": res.stdout.strip(),
            "stderr": res.stderr.strip(),
            "returncode": res.returncode
        }
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": f"Command timed out after {timeout} seconds", "returncode": -1}
    except Exception as e:
        return {"stdout": "", "stderr": str(e), "returncode": -1}

def handle_git(action: str, message: str = "", branch: str = "", remote: str = "origin") -> str:
    """Run git version control operations."""
    if action == "status":
        res = run_cmd("git status")
        return res["stdout"] or res["stderr"]
    elif action == "diff":
        res = run_cmd("git diff --stat")
        return res["stdout"] or "No diff detected."
    elif action == "commit":
        if not message:
            message = "Update from JARVIS Coding Pipeline"
        run_cmd("git add -A")
        res = run_cmd(f'git commit -m "{message}"')
        return res["stdout"] or res["stderr"]
    elif action == "log":
        res = run_cmd("git log --oneline -n 10")
        return res["stdout"] or res["stderr"]
    elif action == "branch":
        if branch:
            res = run_cmd(f"git checkout -b {branch}")
            return res["stdout"] or res["stderr"]
        res = run_cmd("git branch -a")
        return res["stdout"] or res["stderr"]
    elif action == "push":
        res = run_cmd(f"git push {remote} {branch or 'HEAD'}")
        return res["stdout"] or res["stderr"]
    elif action == "pull":
        res = run_cmd(f"git pull {remote} {branch or 'HEAD'}")
        return res["stdout"] or res["stderr"]
    return f"Unknown git action: {action}"

def scaffold_project(project_type: str, target_dir: str) -> str:
    """Create project boilerplate."""
    dest = Path(target_dir).expanduser().resolve()
    dest.mkdir(parents=True, exist_ok=True)
    
    pt = project_type.lower()
    created_files = []

    if "fastapi" in pt or "python" in pt:
        main_py = dest / "main.py"
        req_txt = dest / "requirements.txt"
        readme = dest / "README.md"
        
        main_py.write_text("""from fastapi import FastAPI

app = FastAPI(title="JARVIS Generated API")

@app.get("/")
def read_root():
    return {"message": "System online and operational"}

@app.get("/health")
def health():
    return {"status": "healthy"}
""", encoding="utf-8")
        req_txt.write_text("fastapi\nuvicorn[standard]\nrequests\n", encoding="utf-8")
        readme.write_text(f"# {dest.name}\n\nFastAPI service created by JARVIS.\n\nRun:\n```bash\nuvicorn main:app --reload\n```\n", encoding="utf-8")
        created_files = ["main.py", "requirements.txt", "README.md"]

    elif "react" in pt or "next" in pt or "web" in pt:
        package_json = dest / "package.json"
        package_json.write_text(f"""{{
  "name": "{dest.name.lower()}",
  "version": "1.0.0",
  "private": true,
  "scripts": {{
    "dev": "vite",
    "build": "vite build"
  }}
}}""", encoding="utf-8")
        created_files = ["package.json"]

    else:
        app_py = dest / "app.py"
        app_py.write_text("""def main():
    print("Application initialized successfully.")

if __name__ == "__main__":
    main()
""", encoding="utf-8")
        created_files = ["app.py"]

    return f"🚀 Scaffolded {project_type} project in `{dest}` with files: {', '.join(created_files)}"

def coding_pipeline(parameters: dict, player=None, session_memory=None) -> str:
    """Entry handler for coding_pipeline."""
    action = parameters.get("action", "run_command").lower().strip()
    command = parameters.get("command", "")
    cwd = parameters.get("cwd")
    project_type = parameters.get("project_type", "fastapi")
    target_dir = parameters.get("target_dir", str(Path.home() / "Desktop" / "my_project"))
    git_action = parameters.get("git_action", "status")
    commit_msg = parameters.get("commit_msg", "")
    branch = parameters.get("branch", "")

    if player:
        try: player.write_log(f"PIPELINE: Executing {action}...")
        except Exception: pass

    if action in ("run_command", "exec", "terminal", "bash"):
        if not command:
            return "Please provide 'command' to execute."
        res = run_cmd(command, cwd=cwd)
        out = res["stdout"]
        err = res["stderr"]
        code = res["returncode"]
        report = [f"💻 Command: `{command}` (Exit Code: {code})"]
        if out: report.append(f"Output:\n```\n{out[:2000]}\n```")
        if err: report.append(f"Errors / Stderr:\n```\n{err[:2000]}\n```")
        return "\n".join(report)

    elif action in ("git", "vcs"):
        return handle_git(git_action, message=commit_msg, branch=branch)

    elif action in ("scaffold", "new_project"):
        return scaffold_project(project_type, target_dir)

    elif action in ("test", "build", "pipeline"):
        test_cmd = command or "pytest"
        res = run_cmd(test_cmd, cwd=cwd)
        status = "✅ PASSED" if res["returncode"] == 0 else "❌ FAILED"
        return f"Pipeline Execution ({test_cmd}): {status}\n{res['stdout'] or res['stderr']}"

    return f"Coding pipeline action '{action}' completed."


TOOL = {
    "name": "coding_pipeline",
    "description": (
        "Full-Spectrum Coding & Pipeline Automation engine. Executes shell commands, build & test pipelines "
        "(pytest, npm, cargo, make), manages Git version control (status, commit, branch, diff, push, pull), "
        "and scaffolds complete project architectures (FastAPI, React, Python CLI)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "run_command | git | scaffold | test | pipeline",
            },
            "command": {
                "type": "STRING",
                "description": "Shell command or test runner command to execute",
            },
            "cwd": {
                "type": "STRING",
                "description": "Working directory for command execution",
            },
            "git_action": {
                "type": "STRING",
                "description": "status | diff | commit | log | branch | push | pull",
            },
            "commit_msg": {
                "type": "STRING",
                "description": "Commit message for git commit",
            },
            "branch": {
                "type": "STRING",
                "description": "Git branch name",
            },
            "project_type": {
                "type": "STRING",
                "description": "fastapi | react | python (for project scaffolding)",
            },
            "target_dir": {
                "type": "STRING",
                "description": "Directory path for scaffolding new projects",
            }
        },
        "required": ["action"],
    },
    "handler": coding_pipeline,
}
