"""
actions/kwin_desktop.py — Wayland desktop automation via kwin-mcp.

WHAT THIS IS
    On Wayland, pyautogui, mss, xdotool and wmctrl silently do nothing — the
    compositor was designed to prevent exactly this. kwin-mcp
    (https://github.com/isac322/kwin-mcp) is an MCP server that works on KDE
    Plasma 6 Wayland by speaking KWin's private EIS D-Bus interface and
    KWin ScreenShot2. This action wraps its tools so the model can type,
    click, screenshot, manage windows and read the clipboard on a real
    Wayland desktop.

HOW IT IS WIRED
    * Discovered by core/action_loader.py like every other actions/*.py file
      (exposes a module-level TOOL dict).
    * The kwin-mcp client (core/kwin_mcp_client.py) starts the server
      lazily on first use, connects to the live Wayland session, and keeps it
      running for the process lifetime.
    * platform_support.py reports can_control_input / can_capture_screen /
      can_focus_windows as True on Wayland when kwin-mcp is installed, so the
      model is told it *can* drive the screen — and it can, through kwin-mcp.

WHICH ACTIONS EXIST
    kwin_type, kwin_press, kwin_hotkey, kwin_click, kwin_double_click,
    kwin_right_click, kwin_move_mouse, kwin_scroll, kwin_drag,
    kwin_screenshot, kwin_focus_window, kwin_list_windows,
    kwin_close_window, kwin_clipboard_read, kwin_clipboard_write,
    kwin_element_query, kwin_element_act, kwin_session_info

CAUTION
    Destructive infrastructure: keystrokes, clicks and window closes reach
    real applications on the user's desktop. Irreversible actions (close)
    should go through the confirmation gate (core/confirm).
"""
from __future__ import annotations

import base64
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from core import appidentity, outcome
from core.kwin_mcp_client import get_client, available as kwin_available
from core.lazyimport import installed

_SYSTEM = platform.system()          # "Windows" | "Darwin" | "Linux"

# Lazy, like every other heavy dependency in this file.
_PYAUTOGUI = installed("pyautogui")
pyautogui = None  # type: ignore[assignment]

if _PYAUTOGUI:
    from core.lazyimport import LazyModule

    def _configure_pa(module) -> None:
        module.FAILSAFE = True
        module.PAUSE = 0.05

    pyautogui = LazyModule("pyautogui", _configure_pa)


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _get_api_key() -> str:
    try:
        import json as _json

        return _json.loads(
            (_base_dir() / "config" / "api_keys.json").read_text(encoding="utf-8")
        ).get("gemini_api_key", "")
    except Exception:
        return ""


def _need_kwin() -> None:
    """Ensure kwin-mcp client is started. Auto-starts if needed."""
    if not kwin_available():
        raise RuntimeError(
            "kwin-mcp is not installed. Install it with: pip install kwin-mcp"
        )
    client = get_client()
    if not client.running:
        # Auto-start kwin-mcp if it hasn't been started yet (e.g. if the
        # startup code in main.py didn't run or failed).
        try:
            client.start()
            # Connect to the live session.
            client.connect_session()
        except Exception as e:
            raise RuntimeError(
                f"kwin-mcp is installed but failed to start: {e}. "
                f"Make sure you're running on KDE Plasma 6 Wayland."
            )


def _is_wayland() -> bool:
    return (
        _SYSTEM == "Linux"
        and (
            (os.environ.get("XDG_SESSION_TYPE") or "").strip().lower() == "wayland"
            or bool(os.environ.get("WAYLAND_DISPLAY"))
        )
    )


# Key name normalization — kwin-mcp expects standard key names like "Return",
# "Escape", "Tab", "Space", "Backspace", "Delete", etc.
_KEY_NAME_MAP = {
    "enter": "Return",
    "return": "Return",
    "esc": "Escape",
    "escape": "Escape",
    "tab": "Tab",
    "space": "Space",
    "backspace": "Backspace",
    "delete": "Delete",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    "home": "Home",
    "end": "End",
    "pageup": "PageUp",
    "pagedown": "PageDown",
    "insert": "Insert",
    "f1": "F1", "f2": "F2", "f3": "F3", "f4": "F4",
    "f5": "F5", "f6": "F6", "f7": "F7", "f8": "F8",
    "f9": "F9", "f10": "F10", "f11": "F11", "f12": "F12",
}


def _normalize_key(key: str) -> str:
    """Normalize a key name to kwin-mcp's expected format."""
    return _KEY_NAME_MAP.get(key.lower(), key)


# ── action implementations ───────────────────────────────────────────────

def _kwin_type(text: str, method: str = "unicode") -> str:
    _need_kwin()
    client = get_client()
    result = client.keyboard_type(text, method=method)
    return _render_result(result, "typed")


def _kwin_press(keys: str) -> str:
    _need_kwin()
    client = get_client()
    # Normalize key names to kwin-mcp's expected format (e.g. "enter" -> "Return")
    normalized = _normalize_key(keys)
    result = client.keyboard_key(normalized)
    return _render_result(result, f"pressed {normalized}")


def _kwin_hotkey(raw_keys: str) -> str:
    _need_kwin()
    keys = [k.strip() for k in raw_keys.split("+")] if isinstance(raw_keys, str) else raw_keys
    # Normalize key names to kwin-mcp's expected format
    keys = [_normalize_key(k) for k in keys]
    chord = "+".join(keys)
    client = get_client()
    result = client.keyboard_key(chord)
    return _render_result(result, f"hotkey {chord}")


def _kwin_click(x=None, y=None, button: str = "left", count: int = 1) -> str:
    _need_kwin()
    client = get_client()
    if x is not None and y is not None:
        # kwin-mcp v0.12.0 takes x, y, button, count at top level (not nested under target)
        result = client.mouse_click(int(x), int(y), button=button, count=count)
        return _render_result(
            result,
            f"{'double-c' if count == 2 else 'c'}licked ({x}, {y}) [{button}]",
        )
    raise RuntimeError("click on Wayland requires x and y coordinates")


def _kwin_move_mouse(x: int, y: int) -> str:
    _need_kwin()
    client = get_client()
    result = client.mouse_move(int(x), int(y))
    return _render_result(result, f"mouse → ({x}, {y})")


def _kwin_scroll(direction: str = "down", amount: int = 3, x=None, y=None) -> str:
    _need_kwin()
    client = get_client()
    if x is None or y is None:
        raise RuntimeError("scroll on Wayland requires x and y coordinates")
    delta = amount if direction in ("up", "right") else -amount
    horizontal = direction in ("left", "right")
    result = client.mouse_scroll(int(x), int(y), delta=delta, horizontal=horizontal)
    return _render_result(result, f"scrolled {direction} ×{amount}")


def _kwin_drag(x1: int, y1: int, x2: int, y2: int) -> str:
    _need_kwin()
    client = get_client()
    result = client.mouse_drag(
        int(x1), int(y1), int(x2), int(y2),
    )
    return _render_result(result, f"dragged ({x1},{y1}) → ({x2},{y2})")


def _kwin_screenshot(save_path: str | None = None) -> str:
    _need_kwin()
    client = get_client()
    result = client.screenshot()
    # kwin-mcp v0.12.0 screenshot returns image data as MCP image content
    # blocks with base64-encoded PNG data.
    path = _extract_screenshot_path(result)
    if save_path:
        try:
            import shutil as _shutil

            _shutil.copy(path, save_path)
            path = save_path
        except Exception as e:
            return f"screenshot captured at {path} but could not copy to {save_path}: {e}"
    return f"Screenshot saved: {path}"


def _kwin_focus_window(title: str) -> str:
    _need_kwin()
    client = get_client()
    # Find the window by caption/app substring, then focus it.
    windows = client.get_kwin_windows()
    matches = _match_windows(windows, title)
    if matches:
        window = matches[0]
        window_id = window.get("id")
        result = client.focus_window(window_id=window_id)
        return _render_result(result, f"focused window: {window.get('caption') or title}")
    # Direct fallback via app_name parameter
    result = client.focus_window(app_name=title)
    return _render_result(result, f"focused window: {title}")


def _kwin_list_windows(filter_str: str = "") -> str:
    _need_kwin()
    client = get_client()
    windows = client.get_kwin_windows()
    if not windows:
        return "No windows."
    lines = []
    for w in windows:
        cap = str(w.get("caption") or w.get("title") or "")
        app = str(w.get("app") or w.get("app_id") or "")
        if filter_str and (
            filter_str.lower() not in cap.lower()
            and filter_str.lower() not in app.lower()
        ):
            continue
        lines.append(
            f"id={w.get('id')} app={app} "
            f"caption={cap} active={w.get('active', False)} "
            f"geom=({w.get('x', 0)},{w.get('y', 0)} {w.get('width', 0)}x{w.get('height', 0)})"
        )
    return "\n".join(lines) if lines else f"No windows matching '{filter_str}'."


def _kwin_close_window(app_name: str) -> str:
    _need_kwin()
    client = get_client()
    windows = client.get_kwin_windows()
    matches = _match_windows(windows, app_name)
    if not matches:
        return outcome.failed(
            "kwin_close_window",
            f"no running window matches '{app_name}'",
            app=app_name,
        )
    window = matches[0]
    window_id = window.get("id")
    result = client.window_close(window_id)
    return _render_result(result, f"closed {app_name}")


def _kwin_clipboard_read() -> str:
    _need_kwin()
    client = get_client()
    result = client.clipboard_get()
    text = _extract_text(result)
    return text if text else "(clipboard empty)"


def _kwin_clipboard_write(text: str) -> str:
    _need_kwin()
    client = get_client()
    result = client.clipboard_set(text)
    return _render_result(result, f"clipboard set ({len(text)} chars)")


def _kwin_element_query(desc: str) -> str:
    _need_kwin()
    client = get_client()
    result = client.find_ui_elements(
        query=desc, app_name=None, states=None
    )
    return _render_result(result, f"element query: {desc}")


def _kwin_element_act(desc: str, action: str = "press", app_name: str | None = None) -> str:
    _need_kwin()
    client = get_client()
    query = client.find_ui_elements(
        query=desc, app_name=app_name, states=None
    )
    elements = _extract_elements(query)
    if not elements:
        return f"element_act: no element matches '{desc}'"
    el = elements[0]
    el_actions = el.get("actions") or []
    action_to_use = action
    if el_actions and action.lower() not in [str(a).lower() for a in el_actions]:
        action_to_use = str(el_actions[0])
    elif not action_to_use:
        action_to_use = "Press"

    result = client.invoke_ui_action(
        query=desc,
        action_name=action_to_use,
        app_name=app_name,
        fallback_action_names=["Press", "press", "click", "Click", "activate"],
    )
    rendered = _render_result(result, f"acted on '{desc}' ({action_to_use})")
    # If AT-SPI invoke failed (e.g. ambiguous match or unconfirmed) and we have screen rect, fall back to click
    if rendered.startswith("error:") and isinstance(el.get("rect"), dict):
        rect = el["rect"]
        cx = int(rect.get("x", 0)) + int(rect.get("width", 0)) // 2
        cy = int(rect.get("y", 0)) + int(rect.get("height", 0)) // 2
        if cx > 0 and cy > 0:
            click_res = client.mouse_click(cx, cy, button="left")
            return _render_result(click_res, f"clicked element '{desc}' at ({cx}, {cy})")
    return rendered


def _kwin_session_info() -> str:
    _need_kwin()
    client = get_client()
    result = client.window_geometry()
    return _render_result(result, "session info")


# ── helpers ──────────────────────────────────────────────────────────────

def _match_windows(windows: Any, name: str) -> list[dict[str, Any]]:
    """Return windows whose caption or app_id contains name (case-insensitive)."""
    if not isinstance(windows, list):
        return []
    name_l = name.lower()
    out = []
    for w in windows:
        if not isinstance(w, dict):
            continue
        caption = str(w.get("caption", "")).lower()
        app_id = str(w.get("app_id", "")).lower()
        if name_l in caption or name_l in app_id:
            out.append(w)
    return out


def _render_result(result: Any, fallback: str) -> str:
    """Turn a kwin-mcp MCP tool result into a short sentence.

    MCP tools/call returns {"content": [...], "structuredContent": {...}}.
    """
    if not isinstance(result, dict):
        return fallback

    # Check for error first.
    if result.get("isError"):
        # Pull the error text from content blocks.
        content = result.get("content", [])
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    return f"error: {block.get('text', '')}"
        return "error: kwin-mcp tool reported an error"

    # Extract text from content blocks.
    content = result.get("content", [])
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                if text:
                    return str(text)

    # Fall back to structuredContent fields.
    sc = result.get("structuredContent") or result.get("structured_content") or {}
    if isinstance(sc, dict):
        for key in ("message", "detail", "result", "text"):
            if sc.get(key):
                return str(sc[key])

    return fallback


def _extract_screenshot_path(result: Any) -> str:
    """Extract screenshot path or image data from kwin-mcp screenshot result.

    kwin-mcp v0.12.0 screenshot returns image data as MCP image content
    blocks with base64-encoded PNG data, plus possibly a file path/URI.
    """
    if not isinstance(result, dict):
        return "(screenshot path unavailable)"

    # Check structuredContent for a Frame.
    sc = result.get("structuredContent") or result.get("structured_content") or {}
    if isinstance(sc, dict):
        path = sc.get("path") or sc.get("file_path") or ""
        if path:
            return str(path)
        uri = sc.get("uri") or sc.get("frame_uri") or ""
        if uri and uri.startswith("kwin://screenshots/"):
            return str(uri)

    # Top-level fields.
    path = result.get("path") or result.get("file_path") or ""
    if path:
        return str(path)
    uri = result.get("uri") or result.get("frame_uri") or ""
    if uri and uri.startswith("kwin://screenshots/"):
        return str(uri)

    # Content blocks may carry image data as base64 or path as text.
    content = result.get("content", [])
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type", "")
            if btype == "image":
                # Image data is base64-encoded in the 'data' field.
                b64_data = block.get("data", "")
                if b64_data:
                    try:
                        import base64
                        image_bytes = base64.b64decode(b64_data)
                        # Save to a temp file and return the path
                        import tempfile
                        cache_dir = Path.home() / ".cache" / "amatya"
                        cache_dir.mkdir(parents=True, exist_ok=True)
                        tmp = tempfile.NamedTemporaryFile(
                            suffix=".png", delete=False, dir=str(cache_dir)
                        )
                        tmp.write(image_bytes)
                        tmp.close()
                        return tmp.name
                    except Exception:
                        pass
            elif btype == "text":
                text = str(block.get("text", ""))
                if text.startswith("/") or text.startswith("kwin://"):
                    return text

    return "(screenshot path unavailable)"


def _extract_text(result: Any) -> str:
    if not isinstance(result, dict):
        return ""

    content = result.get("content", [])
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                if text:
                    return str(text)

    sc = result.get("structuredContent") or result.get("structured_content") or {}
    if isinstance(sc, dict):
        text = sc.get("text") or sc.get("content") or ""
        if text:
            return str(text)

    return ""


def _extract_elements(result: Any) -> list[dict[str, Any]]:
    if not isinstance(result, dict):
        return []

    sc = result.get("structuredContent") or result.get("structured_content") or {}
    if isinstance(sc, dict):
        elements = sc.get("elements") or []
        if isinstance(elements, list):
            return elements

    elements = result.get("elements") or []
    if isinstance(elements, list):
        return elements

    return []


# ── entry point ──────────────────────────────────────────────────────────

def kwin_desktop(
    parameters=None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """
    Dispatch table for Wayland desktop control via kwin-mcp.

    parameters keys:
        action     : (required) kwin_type | kwin_press | kwin_hotkey |
                     kwin_click | kwin_double_click | kwin_right_click |
                     kwin_move_mouse | kwin_scroll | kwin_drag |
                     kwin_screenshot | kwin_focus_window |
                     kwin_list_windows | kwin_close_window |
                     kwin_clipboard_read | kwin_clipboard_write |
                     kwin_element_query | kwin_element_act |
                     kwin_session_info
        text       : text to type / paste / set on clipboard
        keys       : key chord, e.g. 'ctrl+c'
        key        : single key, e.g. 'Return'
        x, y       : screen coordinates (global logical pixels)
        button     : 'left' | 'right' | 'middle' (default: left)
        count      : click count (1 single, 2 double)
        direction  : 'up' | 'down' | 'left' | 'right'
        amount     : scroll amount (default: 3)
        title      : window title fragment for focus / close
        app_name   : application name for close
        description: element description for element_query / element_act
        action     : AT-SPI action name for element_act (default: press)
        path       : save path for screenshot
    """
    params = parameters or {}
    action = params.get("action", "").lower().strip()

    if not action:
        return "No action specified for kwin_desktop."

    if player:
        print(f"[KwinDesktop] {action}")

    print(f"[KwinDesktop] ▶ {action}  {params}")

    try:
        if action == "kwin_type":
            return _kwin_type(params.get("text", ""), method=params.get("method", "unicode"))

        if action == "kwin_press":
            return _kwin_press(params.get("key", "Return"))

        if action == "kwin_hotkey":
            return _kwin_hotkey(params.get("keys", ""))

        if action in ("kwin_click", "kwin_left_click"):
            return _kwin_click(params.get("x"), params.get("y"), "left", 1)

        if action == "kwin_double_click":
            return _kwin_click(params.get("x"), params.get("y"), "left", 2)

        if action == "kwin_right_click":
            return _kwin_click(params.get("x"), params.get("y"), "right", 1)

        if action == "kwin_move_mouse":
            return _kwin_move_mouse(int(params.get("x", 0)), int(params.get("y", 0)))

        if action == "kwin_scroll":
            return _kwin_scroll(
                direction=params.get("direction", "down"),
                amount=int(params.get("amount", 3)),
                x=params.get("x"),
                y=params.get("y"),
            )

        if action == "kwin_drag":
            return _kwin_drag(
                int(params.get("x1", 0)), int(params.get("y1", 0)),
                int(params.get("x2", 0)), int(params.get("y2", 0)),
            )

        if action == "kwin_screenshot":
            return _kwin_screenshot(params.get("path"))

        if action == "kwin_focus_window":
            return _kwin_focus_window(params.get("title", ""))

        if action == "kwin_list_windows":
            return _kwin_list_windows(params.get("filter", ""))

        if action == "kwin_close_window":
            return _kwin_close_window(
                params.get("app_name") or params.get("text") or ""
            )

        if action == "kwin_clipboard_read":
            return _kwin_clipboard_read()

        if action == "kwin_clipboard_write":
            return _kwin_clipboard_write(params.get("text", ""))

        if action == "kwin_element_query":
            return _kwin_element_query(params.get("description", ""))

        if action == "kwin_element_act":
            return _kwin_element_act(
                params.get("description", ""),
                action=params.get("kwin_action", "press"),
            )

        if action == "kwin_session_info":
            return _kwin_session_info()

        return f"Unknown kwin_desktop action: '{action}'"

    except Exception as e:
        print(f"[KwinDesktop] ❌ {action}: {e}")
        return f"kwin_desktop '{action}' failed: {e}"


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────

TOOL = {
    "name": "kwin_desktop",
    "description": (
        "Wayland desktop control through kwin-mcp (KDE Plasma 6). "
        "Use on Wayland where pyautogui / xdotool / wmctrl cannot reach "
        "applications. Actions: "
        "kwin_type(text) — type text at keyboard focus; "
        "kwin_press(key) — press one key; "
        "kwin_hotkey(keys) — chord like 'ctrl+c'; "
        "kwin_click(x,y,button) — click at coordinates; "
        "kwin_double_click(x,y); "
        "kwin_right_click(x,y); "
        "kwin_move_mouse(x,y); "
        "kwin_scroll(x,y,direction,amount); "
        "kwin_drag(x1,y1,x2,y2); "
        "kwin_screenshot(path) — capture screen; "
        "kwin_focus_window(title); "
        "kwin_list_windows(filter); "
        "kwin_close_window(app_name); "
        "kwin_clipboard_read(); "
        "kwin_clipboard_write(text); "
        "kwin_element_query(description); "
        "kwin_element_act(description,action). "
        "Read the status: 'done' confirmed, 'unverified' requested but not "
        "confirmed, 'ask' nothing done — ask the user first."
    ),
    "brief": (
        "Wayland desktop control via kwin-mcp: type, click, scroll, "
        "screenshot, focus/close windows, clipboard, element actions."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "kwin_type | kwin_press | kwin_hotkey | kwin_click | kwin_double_click | kwin_right_click | kwin_move_mouse | kwin_scroll | kwin_drag | kwin_screenshot | kwin_focus_window | kwin_list_windows | kwin_close_window | kwin_clipboard_read | kwin_clipboard_write | kwin_element_query | kwin_element_act | kwin_session_info",
            },
            "app_name": {
                "type": "STRING",
                "description": "For kwin_close_window: the application to close.",
            },
            "text": {
                "type": "STRING",
                "description": "Text to type or set on clipboard.",
            },
            "x": {"type": "INTEGER", "description": "X coordinate (global logical px)."},
            "y": {"type": "INTEGER", "description": "Y coordinate (global logical px)."},
            "keys": {
                "type": "STRING",
                "description": "Key chord e.g. 'ctrl+c'.",
            },
            "key": {
                "type": "STRING",
                "description": "Single key e.g. 'Return'.",
            },
            "direction": {
                "type": "STRING",
                "description": "up | down | left | right.",
            },
            "amount": {
                "type": "INTEGER",
                "description": "Scroll amount (default: 3).",
            },
            "title": {
                "type": "STRING",
                "description": "Window title fragment for kwin_focus_window.",
            },
            "description": {
                "type": "STRING",
                "description": "Element description for kwin_element_query / kwin_element_act.",
            },
            "kwin_action": {
                "type": "STRING",
                "description": "AT-SPI action name for kwin_element_act (default: press).",
            },
            "path": {
                "type": "STRING",
                "description": "Save path for kwin_screenshot.",
            },
        },
        "required": ["action"],
    },
    "handler": kwin_desktop,
}
