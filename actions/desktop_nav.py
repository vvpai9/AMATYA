"""
actions/desktop_nav.py — AMATYA Fast Directory Navigation via Zoxide
===================================================================
Provides voice- and text-driven intelligent directory jumping, frecency
history exploration, and desktop file manager / terminal navigation using
`zoxide` (with automatic fallback to a resilient internal frecency engine).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from core import zoxide_nav


def zoxide_nav_action(
    parameters: dict,
    player: Any = None,
    session_memory: Any = None,
    **kwargs,
) -> str:
    """Execute zoxide directory jumping and navigation."""
    params = parameters or {}
    action = str(params.get("action") or "jump").strip().lower()
    query = str(params.get("query") or params.get("path") or "").strip()
    open_fm = bool(params.get("open_file_manager", False) or action in ("open_fm", "open", "open_file_manager"))
    open_term = bool(params.get("open_terminal", False) or action in ("open_term", "terminal", "open_terminal"))
    limit = int(params.get("limit", 12))

    if action in ("list", "top", "history"):
        top_dirs = zoxide_nav.list_top_directories(keywords=query, limit=limit)
        if not top_dirs:
            return f"No directories found in frecency history matching '{query}'." if query else "Frecency directory history is currently empty."

        md_lines = [
            "# 🚀 AMATYA Fast Navigation — Frecency Directory Index",
            f"**Search Query:** `{query or 'Top Ranked Directories'}` | **Results:** `{len(top_dirs)}`",
            f"**Engine:** `{'Native Zoxide (' + (zoxide_nav.get_zoxide_executable() or '') + ')' if zoxide_nav.is_zoxide_available() else 'AMATYA Smart Frecency Fallback'}`",
            "---",
            "| Rank | Folder Name | Path | Score |",
            "| :--- | :--- | :--- | :--- |",
        ]
        for idx, d in enumerate(top_dirs, 1):
            md_lines.append(f"| #{idx} | **{d.get('name', '')}** | `{d.get('path', '')}` | {d.get('score', 0.0):.1f} |")

        md_lines.append("\n*To jump directly to any folder, say:* `Jump to <Folder Name>` or `Open folder <Folder Name>`")

        if player is not None:
            try:
                player.show_content("Fast Directory Navigation (Zoxide)", "\n".join(md_lines))
                player.write_log(f"ZOXIDE: Displayed {len(top_dirs)} ranked directories on HUD.")
            except Exception:
                pass

        sample_names = ", ".join(d.get("name", "") for d in top_dirs[:3])
        return f"Found {len(top_dirs)} matching folders including {sample_names}. You can jump to any of them directly."

    elif action in ("add", "record"):
        if not query:
            return "Please specify a directory path to add to the navigation index."
        target_path = Path(query).expanduser()
        if not target_path.is_dir():
            return f"Cannot add '{query}' because it is not an existing directory."
        ok = zoxide_nav.add_directory(target_path)
        if ok:
            if player is not None:
                try:
                    player.write_log(f"ZOXIDE: Added {target_path} to frecency index.")
                except Exception:
                    pass
            return f"Successfully added '{target_path.resolve()}' to directory frecency index."
        return f"Could not add '{query}' to navigation index."

    elif action in ("remove", "delete"):
        if not query:
            return "Please specify a directory path to remove from navigation history."
        target_path = Path(query).expanduser()
        ok = zoxide_nav.remove_directory(target_path)
        if ok:
            return f"Removed '{query}' from directory frecency history."
        return f"Could not remove '{query}' from navigation history."

    elif action in ("query", "search", "find"):
        if not query:
            return "Please provide a folder name or search keyword to query."
        match = zoxide_nav.query_directory(query)
        if not match:
            return f"Could not find any directory matching '{query}' in your filesystem or history."
        return f"Found directory: {match}"

    elif action in ("jump", "navigate", "open_fm", "open", "open_file_manager", "open_term", "terminal", "open_terminal"):
        if not query:
            return "Please provide a folder name, keyword, or path to navigate to."

        # Default jump behavior: if open_fm or open_term not explicitly requested, open_fm can be enabled when action specifies open
        if action in ("open_fm", "open", "open_file_manager"):
            open_fm = True
        elif action in ("open_term", "terminal", "open_terminal"):
            open_term = True

        ok, target_path, msg = zoxide_nav.jump_directory(
            query=query,
            open_file_manager=open_fm,
            open_terminal=open_term,
            player=player,
        )
        if not ok or not target_path:
            return msg

        md_card = [
            f"# 📂 Navigated to: `{target_path.name}`",
            f"**Full Path:** `{target_path}`",
            f"**File Manager:** `{'Launched' if open_fm else 'Not Requested'}` | **Terminal:** `{'Launched' if open_term else 'Not Requested'}`",
            "---",
            f"*AMATYA directory navigation completed via {'Zoxide' if zoxide_nav.is_zoxide_available() else 'Smart Frecency Fallback'}.*",
        ]
        if player is not None:
            try:
                player.show_content(f"Jump: {target_path.name}", "\n".join(md_card))
            except Exception:
                pass

        return msg

    return f"Unknown directory navigation action '{action}'."


MANIFEST = {
    "name": "zoxide_navigate",
    "version": "1.0.0",
    "description": "Fast directory navigation, fuzzy folder jumping, and frecency exploration via Zoxide.",
    "capabilities": [
        "fast_directory_navigation",
        "frecency_ranking",
        "file_manager_launch",
        "terminal_launch",
    ],
    "permissions": ["filesystem_read"],
    "dependencies": [],
    "supported_actions": ["jump", "list", "query", "add", "remove", "open_fm", "open_term"],
    "security_level": "normal",
}

TOOL = {
    "name": "zoxide_navigate",
    "description": (
        "Fast directory navigation and fuzzy folder jumping via Zoxide and frecency ranking. "
        "Allows jumping to any frequently visited folder (e.g. 'jump to amatya', 'jump to projects', "
        "'list frequent folders'), opening folders in native file managers (Dolphin/Nautilus/Explorer) "
        "or launching terminals directly at that location."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["jump", "list", "query", "add", "remove", "open_fm", "open_term"],
                "description": "Action to perform: 'jump' to directory, 'list' top frecency directories on HUD, 'query' path, 'open_fm' in file manager, 'open_term' in terminal, 'add' directory, or 'remove' directory.",
            },
            "query": {
                "type": "STRING",
                "description": "Directory name, fuzzy keywords, or path (e.g. 'amatya', 'desktop', 'downloads', 'projects').",
            },
            "open_file_manager": {
                "type": "BOOLEAN",
                "description": "Whether to open the resolved directory in the native desktop file manager (Dolphin/Nautilus/Explorer).",
            },
            "open_terminal": {
                "type": "BOOLEAN",
                "description": "Whether to launch a terminal window in the resolved directory.",
            },
            "limit": {
                "type": "INTEGER",
                "description": "Maximum number of directories to return when listing.",
            },
        },
    },
    "handler": zoxide_nav_action,
}

execute = zoxide_nav_action
