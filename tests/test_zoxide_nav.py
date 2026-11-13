"""
tests/test_zoxide_nav.py — Unit tests for Zoxide Navigation and DesktopAuto
============================================================================
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core import zoxide_nav
from core.security import PermissionTier, classify_tool_permission
from actions.desktop_nav import zoxide_nav_action, TOOL as ZOXIDE_TOOL
from actions.file_controller import file_controller, _resolve_path


class DummyPlayer:
    def __init__(self):
        self.logs: list[str] = []
        self.content_cards: list[tuple[str, str]] = []

    def write_log(self, text: str) -> None:
        self.logs.append(text)

    def show_content(self, title: str, text: str) -> None:
        self.content_cards.append((title, text))


@pytest.fixture
def temp_dirs():
    temp_root = Path(tempfile.mkdtemp(prefix="amatya_zoxide_test_"))
    dir_a = temp_root / "project_alpha"
    dir_b = temp_root / "project_beta"
    dir_a.mkdir(parents=True)
    dir_b.mkdir(parents=True)
    yield temp_root, dir_a, dir_b
    shutil.rmtree(temp_root, ignore_errors=True)


def test_zoxide_discovery_and_availability():
    """Verify discovery logic does not crash and returns string or None."""
    exe = zoxide_nav.get_zoxide_executable()
    assert exe is None or isinstance(exe, str)
    avail = zoxide_nav.is_zoxide_available()
    assert isinstance(avail, bool)


def test_add_and_query_directory(temp_dirs):
    temp_root, dir_a, dir_b = temp_dirs

    # Add directories
    ok_a = zoxide_nav.add_directory(dir_a)
    ok_b = zoxide_nav.add_directory(dir_b)
    assert ok_a is True
    assert ok_b is True

    # Query by exact or fuzzy name
    res_a = zoxide_nav.query_directory("project_alpha")
    assert res_a is not None
    assert res_a.resolve() == dir_a.resolve()

    res_b = zoxide_nav.query_directory("project_beta")
    assert res_b is not None
    assert res_b.resolve() == dir_b.resolve()


def test_shortcuts_resolution():
    desktop_res = zoxide_nav.query_directory("desktop")
    if desktop_res:
        assert desktop_res.is_dir()

    home_res = zoxide_nav.query_directory("home")
    assert home_res is not None
    assert home_res.resolve() == Path.home().resolve()


def test_list_top_directories(temp_dirs):
    temp_root, dir_a, dir_b = temp_dirs
    zoxide_nav.add_directory(dir_a)
    zoxide_nav.add_directory(dir_b)

    results = zoxide_nav.list_top_directories(keywords="project", limit=10)
    assert isinstance(results, list)
    paths = [Path(r["path"]).resolve() for r in results]
    assert dir_a.resolve() in paths or dir_b.resolve() in paths


def test_jump_directory(temp_dirs):
    temp_root, dir_a, _ = temp_dirs
    zoxide_nav.add_directory(dir_a)

    player = DummyPlayer()
    with patch("core.zoxide_nav.open_directory_in_file_manager", return_value=(True, "Opened FM")):
        with patch("core.zoxide_nav.open_directory_in_terminal", return_value=(True, "Opened Term")):
            ok, target, msg = zoxide_nav.jump_directory(
                query="project_alpha",
                open_file_manager=True,
                open_terminal=True,
                player=player,
            )
            assert ok is True
            assert target is not None
            assert target.resolve() == dir_a.resolve()
            assert "Navigated to" in msg
            assert any("Jumped to" in log for log in player.logs)


def test_remove_directory(temp_dirs):
    temp_root, dir_a, _ = temp_dirs
    zoxide_nav.add_directory(dir_a)
    assert zoxide_nav.remove_directory(dir_a) is True


def test_desktop_nav_action_list():
    player = DummyPlayer()
    out = zoxide_nav_action({"action": "list", "query": ""}, player=player)
    assert isinstance(out, str)
    assert "Found" in out or "empty" in out.lower()
    if player.content_cards:
        assert "Fast Directory Navigation" in player.content_cards[0][0]


def test_desktop_nav_action_jump(temp_dirs):
    temp_root, dir_a, _ = temp_dirs
    zoxide_nav.add_directory(dir_a)

    player = DummyPlayer()
    with patch("core.zoxide_nav.open_directory_in_file_manager", return_value=(True, "Opened FM")):
        out = zoxide_nav_action(
            {"action": "jump", "query": "project_alpha", "open_file_manager": True},
            player=player,
        )
        assert f"project_alpha" in out or "Navigated to" in out


def test_desktop_nav_action_add_and_remove(temp_dirs):
    temp_root, dir_a, _ = temp_dirs
    # Add
    out_add = zoxide_nav_action({"action": "add", "query": str(dir_a)})
    assert "Successfully added" in out_add

    # Remove
    out_rm = zoxide_nav_action({"action": "remove", "query": str(dir_a)})
    assert "Removed" in out_rm


def test_file_controller_zoxide_integration(temp_dirs):
    temp_root, dir_a, _ = temp_dirs
    zoxide_nav.add_directory(dir_a)

    # Test _resolve_path resolves fuzzy query
    resolved = _resolve_path("project_alpha")
    assert resolved.resolve() == dir_a.resolve()

    # Test jump action in file_controller
    player = DummyPlayer()
    with patch("core.zoxide_nav.open_directory_in_file_manager", return_value=(True, "Opened FM")):
        res = file_controller(
            {"action": "jump", "path": "project_alpha", "open_file_manager": True},
            player=player,
        )
        assert "Navigated to" in res or "project_alpha" in res


def test_security_classification():
    """Verify security matrix classifies zoxide_navigate properly."""
    tier, _ = classify_tool_permission("zoxide_navigate", "jump")
    assert tier == PermissionTier.GENERAL_CONVERSATION

    tier_list, _ = classify_tool_permission("zoxide_navigate", "list")
    assert tier_list == PermissionTier.GENERAL_CONVERSATION

    tier_rm, _ = classify_tool_permission("zoxide_navigate", "remove")
    assert tier_rm == PermissionTier.PRIVATE_FILES

    tier_fc_jump, _ = classify_tool_permission("file_controller", "jump")
    assert tier_fc_jump == PermissionTier.GENERAL_CONVERSATION


def test_action_loader_discovers_zoxide():
    from core.action_loader import discover_actions
    registry = discover_actions(Path("actions"))
    assert registry.has("zoxide_navigate")
    tool_decl = registry.get_tool_declarations()
    tool_names = [t.get("name") for t in tool_decl]
    assert "zoxide_navigate" in tool_names
