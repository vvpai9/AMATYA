"""
core/zoxide_nav.py — Fast Directory Navigation and Frecency Engine via Zoxide
=============================================================================
Provides intelligent, lightning-fast directory jumping and navigation for AMATYA:
  - Leverages `zoxide` (the frecency-based fast directory jumper) if available.
  - Automatically discovers zoxide across standard PATH and user bin directories.
  - Features a built-in Python frecency fallback engine when zoxide CLI is not installed.
  - Seamlessly integrates with system file managers (Dolphin, Nautilus, Explorer, Finder)
    and terminal emulators (Konsole, GNOME Terminal, xterm, Kitty, Alacritty, Windows Terminal).
  - Automatically records and learns user directory access habits over time.
"""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Optional

from memory.config_manager import CONFIG_DIR

FALLBACK_STORE_PATH = CONFIG_DIR / "zoxide_history.json"
_LOCK = threading.RLock()
_SYSTEM = platform.system()


# ── Executable Discovery ──────────────────────────────────────────────────────

def get_zoxide_executable() -> Optional[str]:
    """Find the zoxide executable on system PATH or standard install locations."""
    # 1. System PATH
    found = shutil.which("zoxide")
    if found:
        return found

    # 2. Common per-user installation locations
    user_home = Path.home()
    candidates = [
        user_home / ".local" / "bin" / "zoxide",
        user_home / ".cargo" / "bin" / "zoxide",
        Path("/usr/local/bin/zoxide"),
        Path("/usr/bin/zoxide"),
    ]
    if _SYSTEM == "Windows":
        candidates.extend([
            user_home / "AppData" / "Local" / "Programs" / "zoxide" / "zoxide.exe",
            user_home / ".cargo" / "bin" / "zoxide.exe",
        ])

    for c in candidates:
        if c.is_file() and os.access(c, os.X_OK):
            return str(c)

    return None


def is_zoxide_available() -> bool:
    """Return True if native zoxide binary is available and functional."""
    exe = get_zoxide_executable()
    if not exe:
        return False
    try:
        proc = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=2.0)
        return proc.returncode == 0
    except Exception:
        return False


# ── Fallback Frecency Store ───────────────────────────────────────────────────

def _load_fallback_store() -> list[dict[str, Any]]:
    """Load directory access history for fallback engine."""
    with _LOCK:
        if not FALLBACK_STORE_PATH.is_file():
            return []
        try:
            data = json.loads(FALLBACK_STORE_PATH.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []


def _save_fallback_store(entries: list[dict[str, Any]]) -> None:
    """Persist directory access history."""
    with _LOCK:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        # Keep top 150 entries by score
        trimmed = sorted(entries, key=lambda x: x.get("score", 0.0), reverse=True)[:150]
        FALLBACK_STORE_PATH.write_text(json.dumps(trimmed, indent=2), encoding="utf-8")


def _record_fallback_access(dir_path: Path) -> None:
    """Update frecency score in fallback store."""
    resolved = str(dir_path.resolve())
    now = time.time()
    with _LOCK:
        store = _load_fallback_store()
        found = False
        for item in store:
            if item.get("path") == resolved:
                item["score"] = round(item.get("score", 1.0) + 1.0, 2)
                item["last_accessed"] = now
                found = True
                break
        if not found:
            store.append({
                "path": resolved,
                "score": 1.0,
                "last_accessed": now,
            })
        _save_fallback_store(store)


# ── Core Zoxide Interface ─────────────────────────────────────────────────────

def add_directory(path: Path | str) -> bool:
    """Add a directory to the zoxide frecency database and fallback engine."""
    try:
        p = Path(path).expanduser().resolve()
    except Exception:
        return False

    if not p.is_dir():
        return False

    _record_fallback_access(p)

    exe = get_zoxide_executable()
    if exe:
        try:
            res = subprocess.run([exe, "add", str(p)], capture_output=True, text=True, timeout=3.0)
            return res.returncode == 0
        except Exception:
            pass

    return True


def remove_directory(path: Path | str) -> bool:
    """Remove a directory from the zoxide database and fallback engine."""
    target_str = str(Path(path).expanduser().resolve())

    # Fallback remove
    with _LOCK:
        store = _load_fallback_store()
        store = [item for item in store if item.get("path") != target_str]
        _save_fallback_store(store)

    exe = get_zoxide_executable()
    if exe:
        try:
            res = subprocess.run([exe, "remove", target_str], capture_output=True, text=True, timeout=3.0)
            return res.returncode == 0
        except Exception:
            pass

    return True


def query_directory(keywords: str | list[str], base_dir: Path | None = None) -> Optional[Path]:
    """Query zoxide for the best matching directory path.

    Falls back to frecency database and standard user directory shortcuts.
    """
    if isinstance(keywords, str):
        terms = [t.strip() for t in keywords.split() if t.strip()]
    else:
        terms = [str(t).strip() for t in keywords if str(t).strip()]

    if not terms:
        return None

    query_str = " ".join(terms)
    clean_lower = query_str.lower()

    # 1. Quick check for common named shortcuts
    user_home = Path.home()
    named_map = {
        "desktop": user_home / "Desktop",
        "downloads": user_home / "Downloads",
        "documents": user_home / "Documents",
        "pictures": user_home / "Pictures",
        "music": user_home / "Music",
        "videos": user_home / "Videos",
        "home": user_home,
    }
    if clean_lower in named_map and named_map[clean_lower].is_dir():
        add_directory(named_map[clean_lower])
        return named_map[clean_lower]

    # 2. Direct absolute/relative directory check
    direct_p = Path(query_str).expanduser()
    if direct_p.is_dir():
        add_directory(direct_p)
        return direct_p.resolve()

    # 3. Native zoxide query
    exe = get_zoxide_executable()
    if exe:
        cmd = [exe, "query"]
        if base_dir and base_dir.is_dir():
            cmd.extend(["--base-dir", str(base_dir)])
        cmd.extend(terms)

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=3.0)
            if res.returncode == 0 and res.stdout.strip():
                match_p = Path(res.stdout.strip())
                if match_p.is_dir():
                    add_directory(match_p)
                    return match_p
        except Exception:
            pass

    # 4. Fallback search via internal frecency store
    store = _load_fallback_store()
    best_match = None
    best_score = -1.0

    for item in store:
        p_str = item.get("path", "")
        p_lower = p_str.lower()
        if all(term.lower() in p_lower for term in terms):
            score = float(item.get("score", 1.0))
            if score > best_score and Path(p_str).is_dir():
                best_score = score
                best_match = Path(p_str)

    if best_match:
        add_directory(best_match)
        return best_match

    # 5. Fallback: Search subdirectories in home and common project roots
    search_roots = [user_home / "Projects", user_home, user_home / "Documents"]
    for root in search_roots:
        if root.is_dir():
            try:
                for sub in root.iterdir():
                    if sub.is_dir() and all(t.lower() in sub.name.lower() for t in terms):
                        add_directory(sub)
                        return sub.resolve()
            except Exception:
                pass

    return None


def list_top_directories(keywords: str = "", limit: int = 15) -> list[dict[str, Any]]:
    """List ranked directories by frecency score matching query terms."""
    terms = [t.strip() for t in keywords.split() if t.strip()]
    results: list[dict[str, Any]] = []

    exe = get_zoxide_executable()
    if exe:
        cmd = [exe, "query", "-l", "-s"]
        cmd.extend(terms)
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=3.0)
            if res.returncode == 0:
                for line in res.stdout.strip().splitlines():
                    parts = line.strip().split(None, 1)
                    if len(parts) == 2:
                        try:
                            score_val = float(parts[0])
                        except ValueError:
                            score_val = 0.0
                        path_val = parts[1].strip()
                        if Path(path_val).is_dir():
                            results.append({
                                "path": path_val,
                                "name": Path(path_val).name or path_val,
                                "score": score_val,
                            })
        except Exception:
            pass

    if not results:
        # Fallback list from local store
        store = _load_fallback_store()
        for item in store:
            p_str = item.get("path", "")
            if terms and not all(t.lower() in p_str.lower() for t in terms):
                continue
            if Path(p_str).is_dir():
                results.append({
                    "path": p_str,
                    "name": Path(p_str).name or p_str,
                    "score": float(item.get("score", 1.0)),
                })

    return results[:limit]


# ── System Integration (File Manager & Terminal Launching) ────────────────────

def open_directory_in_file_manager(dir_path: Path) -> tuple[bool, str]:
    """Launch the native operating system file manager at specified directory."""
    target = str(dir_path.resolve())
    if not dir_path.is_dir():
        return False, f"Directory does not exist: {target}"

    try:
        if _SYSTEM == "Linux":
            # Prefer desktop-specific file managers, then xdg-open
            for fm in ("dolphin", "nautilus", "thunar", "nemo", "pcmanfm", "xdg-open"):
                if shutil.which(fm):
                    subprocess.Popen([fm, target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                    return True, f"Opened in {fm}: {target}"
        elif _SYSTEM == "Darwin":
            subprocess.Popen(["open", target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            return True, f"Opened in Finder: {target}"
        elif _SYSTEM == "Windows":
            os.startfile(target)  # type: ignore[attr-defined]
            return True, f"Opened in File Explorer: {target}"
    except Exception as exc:
        return False, f"Failed to launch file manager: {exc}"

    return False, "No compatible file manager launcher found."


def open_directory_in_terminal(dir_path: Path) -> tuple[bool, str]:
    """Launch a terminal emulator at the specified directory."""
    target = str(dir_path.resolve())
    if not dir_path.is_dir():
        return False, f"Directory does not exist: {target}"

    try:
        if _SYSTEM == "Linux":
            # Check popular terminal emulators
            for term, args in [
                ("konsole", ["--workdir", target]),
                ("gnome-terminal", ["--working-directory", target]),
                ("xfce4-terminal", ["--working-directory", target]),
                ("kitty", ["--directory", target]),
                ("alacritty", ["--working-directory", target]),
                ("xterm", ["-e", f"cd '{target}' && $SHELL"]),
            ]:
                if shutil.which(term):
                    cmd = [term] + args
                    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                    return True, f"Launched terminal ({term}) at {target}"
        elif _SYSTEM == "Darwin":
            cmd = ["open", "-a", "Terminal", target]
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            return True, f"Launched Terminal at {target}"
        elif _SYSTEM == "Windows":
            cmd = ["cmd.exe", "/K", f"cd /d {target}"]
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            return True, f"Launched Command Prompt at {target}"
    except Exception as exc:
        return False, f"Failed to launch terminal: {exc}"

    return False, "No compatible terminal emulator detected."


def jump_directory(
    query: str,
    open_file_manager: bool = False,
    open_terminal: bool = False,
    player: Any = None,
) -> tuple[bool, Optional[Path], str]:
    """Resolve directory query using zoxide and navigate/open it."""
    clean_q = (query or "").strip()
    if not clean_q:
        return False, None, "Please provide a directory search term or shortcut."

    match_path = query_directory(clean_q)
    if not match_path:
        return False, None, f"Could not find any directory matching '{clean_q}'."

    # Record access in zoxide
    add_directory(match_path)

    extra_actions = []
    if open_file_manager:
        ok_fm, msg_fm = open_directory_in_file_manager(match_path)
        if ok_fm:
            extra_actions.append("Opened in file manager")

    if open_terminal:
        ok_term, msg_term = open_directory_in_terminal(match_path)
        if ok_term:
            extra_actions.append("Opened in terminal")

    action_text = f" ({', '.join(extra_actions)})" if extra_actions else ""
    status_msg = f"Navigated to: {match_path}{action_text}"

    if player is not None:
        try:
            player.write_log(f"ZOXIDE: Jumped to {match_path}")
        except Exception:
            pass

    return True, match_path, status_msg
