"""
Tests for the Unified AMATYA CREATOR Suite (tests/test_creator_suite.py)
Validates autonomous software engineering, AST surgical code editing,
self-repair and diagnostics, project scaffolding, git operations,
document studio, and permission-tier integration.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from actions import creator
from core.creator import CreatorEngine, classify_command_risk, get_creator_engine
from core.security import PermissionTier, classify_tool_permission


@pytest.fixture(autouse=True)
def authenticate_session():
    from core.security import mark_voice_verified
    mark_voice_verified("test_user", 0.99)
    yield


@pytest.fixture
def temp_workspace():
    tmp = tempfile.mkdtemp(prefix="amatya_creator_test_")
    yield Path(tmp)
    shutil.rmtree(tmp, ignore_errors=True)


class MockPlayer:
    def __init__(self):
        self.logs = []
        self.contents = []

    def write_log(self, msg: str):
        self.logs.append(msg)

    def show_content(self, title: str, content: str):
        self.contents.append((title, content))


def test_creator_engine_singleton():
    e1 = get_creator_engine()
    e2 = get_creator_engine()
    assert e1 is e2
    assert isinstance(e1, CreatorEngine)


def test_command_risk_classification():
    safe_read = classify_command_risk("git status")
    assert safe_read["risk_level"] == "SAFE_READ"
    assert safe_read["requires_confirmation"] is False

    safe_build = classify_command_risk("pytest -q")
    assert safe_build["risk_level"] == "SAFE_BUILD"
    assert safe_build["requires_confirmation"] is False

    modify_cmd = classify_command_risk("pip install requests")
    assert modify_cmd["risk_level"] == "MODIFY"
    assert modify_cmd["requires_confirmation"] is True

    destructive_cmd = classify_command_risk("rm -rf /tmp/test")
    assert destructive_cmd["risk_level"] == "DESTRUCTIVE"
    assert destructive_cmd["requires_confirmation"] is True

    sudo_cmd = classify_command_risk("sudo apt update")
    assert sudo_cmd["risk_level"] == "DESTRUCTIVE"
    assert sudo_cmd["requires_confirmation"] is True


def test_ast_surgical_edit_and_rollback(temp_workspace):
    engine = get_creator_engine()
    py_file = temp_workspace / "sample.py"
    py_file.write_text("def hello():\n    return 'world'\n", encoding="utf-8")

    # 1. Valid AST replacement
    res = engine.edit_code(py_file, target="'world'", replacement="'amatya'")
    assert res["ok"] is True
    assert res["occurrences"] == 1
    assert "return 'amatya'" in py_file.read_text(encoding="utf-8")

    # 2. Invalid syntax replacement — must abort and preserve file
    res_bad = engine.edit_code(py_file, target="'amatya'", replacement="def definitely invalid syntax ((")
    assert res_bad["ok"] is False
    assert "Syntax validation failed" in res_bad["error"]
    # File content must remain unchanged!
    assert "return 'amatya'" in py_file.read_text(encoding="utf-8")

    # 3. Missing target
    res_missing = engine.edit_code(py_file, target="non_existent_string", replacement="foo")
    assert res_missing["ok"] is False
    assert "Target snippet not found" in res_missing["error"]


def test_read_code_line_ranges(temp_workspace):
    engine = get_creator_engine()
    py_file = temp_workspace / "numbered.py"
    lines = [f"line_{i} = {i}\n" for i in range(1, 21)]
    py_file.write_text("".join(lines), encoding="utf-8")

    res = engine.read_code(py_file, start_line=5, end_line=10)
    assert res["ok"] is True
    assert res["start_line"] == 5
    assert res["end_line"] == 10
    assert "line_5 = 5" in res["content"]
    assert "line_10 = 10" in res["content"]
    assert "line_11" not in res["content"]


def test_write_code_with_ast_validation(temp_workspace):
    engine = get_creator_engine()
    target_file = temp_workspace / "nested" / "module.py"

    # Valid Python
    res = engine.write_code(target_file, "def foo(): pass\n")
    assert res["ok"] is True
    assert target_file.is_file()
    assert res["bytes_written"] > 0

    # Invalid Python syntax
    bad_file = temp_workspace / "nested" / "bad.py"
    res_bad = engine.write_code(bad_file, "class 123 Invalid:\n")
    assert res_bad["ok"] is False
    assert "Syntax error" in res_bad["error"]
    assert not bad_file.exists()


def test_project_scaffolding(temp_workspace):
    engine = get_creator_engine()
    res = engine.scaffold_project("my_api", project_type="fastapi", target_dir=temp_workspace)
    assert res["ok"] is True
    proj_dir = Path(res["project_dir"])
    assert (proj_dir / "main.py").is_file()
    assert (proj_dir / "requirements.txt").is_file()
    assert (proj_dir / "README.md").is_file()
    assert (proj_dir / "tests" / "test_main.py").is_file()
    assert "main.py" in res["created_files"]


def test_autonomous_self_repair():
    engine = get_creator_engine()
    player = MockPlayer()
    res = engine.self_repair(target="all", player=player, auto_install=False)
    assert res["ok"] is True
    assert res["scanned_modules"] > 0
    assert len(res["dependencies_present"]) > 0
    assert "AMATYA Autonomous Self-Repair Report" in res["report_markdown"]
    assert len(player.contents) >= 1


def test_creator_tool_execute_read_and_edit(temp_workspace):
    test_file = temp_workspace / "tool_test.py"
    test_file.write_text("x = 10\ny = 20\n", encoding="utf-8")

    # Read action
    res_read = creator.execute({"action": "read_code", "path": str(test_file), "start_line": 1, "end_line": 2})
    assert "status=done" in res_read
    assert "Read lines 1 to 2" in res_read

    # Edit action
    res_edit = creator.execute({"action": "edit_code", "path": str(test_file), "target": "y = 20", "replacement": "y = 42"})
    assert "status=done" in res_edit
    assert "Replaced 1 occurrence" in res_edit
    assert "y = 42" in test_file.read_text(encoding="utf-8")


def test_creator_tool_execute_scaffold_and_profiles(temp_workspace):
    res_scaffold = creator.execute({
        "action": "scaffold",
        "project_name": "web_demo",
        "project_type": "react",
        "target_dir": str(temp_workspace),
    })
    assert "status=done" in res_scaffold
    proj_dir = temp_workspace / "web_demo"
    assert (proj_dir / "package.json").is_file()

    # List profiles
    res_profs = creator.execute({"action": "list_profiles"})
    assert "status=done" in res_profs


def test_creator_security_permission_tiers():
    t_read, _ = classify_tool_permission("creator", "read_code")
    assert t_read == PermissionTier.GENERAL_CONVERSATION

    t_inspect, _ = classify_tool_permission("creator", "inspect_repo")
    assert t_inspect == PermissionTier.GENERAL_CONVERSATION

    t_edit, _ = classify_tool_permission("creator", "edit_code")
    assert t_edit == PermissionTier.PRIVATE_FILES

    t_scaffold, _ = classify_tool_permission("creator", "scaffold")
    assert t_scaffold == PermissionTier.PRIVATE_FILES

    t_commit, _ = classify_tool_permission("creator", "git_commit")
    assert t_commit == PermissionTier.SENSITIVE_SYSTEM

    t_repair, _ = classify_tool_permission("creator", "self_repair")
    assert t_repair == PermissionTier.SENSITIVE_SYSTEM

    t_destruct, _ = classify_tool_permission("creator", "run_shell", {"command": "rm -rf /"})
    assert t_destruct == PermissionTier.CRITICAL_SECURITY
