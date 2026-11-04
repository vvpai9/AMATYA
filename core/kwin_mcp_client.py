"""
core/kwin_mcp_client.py — MCP stdio client for kwin-mcp.

WHAT THIS IS
    kwin-mcp (https://github.com/isac322/kwin-mcp) is a Model Context Protocol
    server that gives AI agents desktop automation on KDE Plasma 6 Wayland:
    keyboard, mouse, touch, screenshots, window management, clipboard,
    accessibility tree, D-Bus. It speaks MCP over stdio — JSON-RPC 2.0
    messages, one per line.

WHY A SEPARATE PROCESS
    kwin-mcp is not a library you import. It is a standalone server that owns
    its own KWin session connection, its own dbus, its own libei input context.
    AMATYA starts it as a subprocess, speaks MCP over its stdin/stdout, and
    shuts it down when the assistant exits.

    This matters on Wayland: pyautogui, mss, xdotool, wmctrl all silently do
    nothing. kwin-mcp uses KWin's private EIS (Emulated Input Server) D-Bus
    interface and KWin ScreenShot2, so it works where nothing else can.

SESSION MODES
    * Virtual (session_start): isolated kwin_wayland --virtual session. The
      user's desktop never sees its windows or input. Safe for testing, useless
      for controlling the user's real desktop.
    * Live (session_connect): attaches to the user's actual KWin/Wayland
      session. Actions affect real applications. This is what AMATYA uses —
      --default-live-session makes session_connect the recommended default.

THE MCP PROTOCOL OVER STDIO
    Each message is one JSON-RPC 2.0 object on one line:

        → {"jsonrpc":"2.0","id":1,"method":"initialize","params":{...}}
        ← {"jsonrpc":"2.0","id":1,"result":{...}}

    After initialize + initialized notification, tools/list and tools/call work.
    This client implements just enough: initialize, tools/list, tools/call.

CAUTION
    This is destructive infrastructure. injected keystrokes, mouse clicks,
    window closes — they reach real applications on the user's desktop. The
    confirmation gate (core/confirm) should wrap irreversible actions.

THREADING MODEL
    All public methods are SYNCHRONOUS. Internally the client runs its own
    asyncio event loop on a daemon thread; each public method submits a
    coroutine to that loop via run_coroutine_threadsafe and blocks for the
    result. Action handlers (which run in executor threads from main.py) can
    call client.keyboard_key("Return") directly — no async/await needed.

TOOL NAMES (kwin-mcp v0.12.0)
    session_start, session_connect, session_close, screenshot,
    accessibility_tree, find_ui_elements, mouse_click, mouse_move,
    mouse_scroll, mouse_drag, mouse_button_down, mouse_button_up,
    invoke_ui_action, keyboard_type, keyboard_type_unicode, keyboard_key,
    keyboard_key_down, keyboard_key_up, touch_tap, touch_swipe, touch_pinch,
    touch_multi_swipe, clipboard_get, clipboard_set, wait_for_element,
    launch_app, list_windows, focus_window, window_geometry,
    active_window, window_set_geometry, virtual_desktops,
    window_set_desktop, window_close, dbus_call, read_app_log, wayland_info
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import threading
from typing import Any, Optional

from core.lazyimport import installed


_SERVER_CMD = "kwin-mcp"
# --default-live-session: attach to the user's real desktop (not a virtual one)
# --screenshot-images: attach PNG frames to results so the vision path can see them
# --screenshot-max-edge 2576: bound frames within model vision limits
_SERVER_FLAGS = ("--default-live-session", "--screenshot-images", "--screenshot-max-edge", "2576")


def _resolve_server_cmd() -> list[str] | None:
    """Resolve the kwin-mcp command from PATH, active venv bin, or python -m kwin_mcp."""
    from pathlib import Path
    which_bin = shutil.which(_SERVER_CMD)
    if which_bin:
        return [which_bin]
    venv_bin = Path(sys.executable).resolve().parent / _SERVER_CMD
    if venv_bin.exists():
        return [str(venv_bin)]
    if installed("kwin_mcp"):
        return [sys.executable, "-m", "kwin_mcp"]
    return None

_REQUEST_TIMEOUT = 30.0
_STARTUP_TIMEOUT = 60.0
_SESSION_STOP_TIMEOUT = 10.0


class _McpSession:
    """One MCP stdio connection, running on its own asyncio loop thread."""

    def __init__(self, log=None):
        self._log = log or (lambda m: None)
        self._proc: Optional[subprocess.Popen] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self._start_error: Optional[Exception] = None
        self._pending: dict[int, threading.Event] = {}
        self._results: dict[int, Any] = {}
        self._errors: dict[int, Exception] = {}
        self._next_id = 1
        self._id_lock = threading.Lock()
        self._initialized = False
        self._session_connected = False
        self._started = False

    @property
    def running(self) -> bool:
        return self._started and self._proc is not None and self._proc.poll() is None

    # ── start / stop ──────────────────────────────────────────────────────

    def start(self) -> None:
        """Launch kwin-mcp, run its asyncio loop on a daemon thread, handshake."""
        cmd_prefix = _resolve_server_cmd()
        if not cmd_prefix:
            raise RuntimeError(
                "kwin-mcp is not installed. Install it with: pip install kwin-mcp"
            )

        self._log("[KwinMcp] starting kwin-mcp server…")
        env = dict(os.environ)
        try:
            self._proc = subprocess.Popen(
                [*cmd_prefix, *_SERVER_FLAGS],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
                bufsize=1,
            )
        except Exception as e:
            self._log(f"[KwinMcp] failed to start process: {e}")
            raise

        self._log(f"[KwinMcp] process started, PID={self._proc.pid}")

        # Stderr drain thread — a blocked server must not deadlock on its pipe.
        def _drain_stderr():
            try:
                assert self._proc is not None
                assert self._proc.stderr is not None
                for line in self._proc.stderr:
                    line = line.rstrip()
                    if line:
                        self._log(f"[KwinMcp server] {line}")
            except Exception as e:
                self._log(f"[KwinMcp] stderr thread error: {e}")

        threading.Thread(target=_drain_stderr, daemon=True, name="kwin-mcp-stderr").start()

        # Stdout reader thread — feeds JSON-RPC responses to pending futures.
        def _read_stdout():
            try:
                assert self._proc is not None
                assert self._proc.stdout is not None
                for line in self._proc.stdout:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        self._log(f"[KwinMcp] unparseable: {line[:120]}")
                        continue
                    msg_id = obj.get("id")
                    if msg_id is None:
                        self._log(f"[KwinMcp] notification: {obj.get('method')}")
                        continue
                    with self._id_lock:
                        evt = self._pending.pop(msg_id, None)
                    if evt is not None:
                        if "error" in obj:
                            self._errors[msg_id] = RuntimeError(
                                f"kwin-mcp error: {obj['error'].get('message', obj['error'])}"
                            )
                        else:
                            self._results[msg_id] = obj.get("result")
                        evt.set()
            except Exception as e:
                self._log(f"[KwinMcp] stdout thread error: {e}")

        threading.Thread(target=_read_stdout, daemon=True, name="kwin-mcp-stdout").start()

        # The asyncio loop runs on its own thread.
        def _run_loop():
            try:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
                self._ready.set()
                self._loop.run_forever()
            except Exception as e:
                self._start_error = e
                self._ready.set()

        self._loop_thread = threading.Thread(target=_run_loop, daemon=True, name="kwin-mcp-loop")
        self._loop_thread.start()
        self._ready.wait(timeout=_STARTUP_TIMEOUT)

        if self._start_error:
            self.stop()
            raise self._start_error

        if self._loop is None:
            self.stop()
            raise RuntimeError("kwin-mcp event loop failed to start")

        try:
            self._handshake_sync()
            self._initialized = True
            self._started = True
            self._log("[KwinMcp] server ready")
        except Exception:
            self.stop()
            raise

    def ensure_started(self, connect: bool = True) -> bool:
        """Ensure the kwin-mcp subprocess is started and connected to the session."""
        if not self.running:
            self._started = False
            self._initialized = False
            self._session_connected = False
            self.start()
        if connect and not self._session_connected:
            self.connect_session()
        return self.running

    def stop(self) -> None:
        """End the session, close pipes, terminate the subprocess."""
        if self._session_connected and self._loop is not None:
            try:
                fut = asyncio.run_coroutine_threadsafe(
                    self._async_send("tools/call", {"name": "session_stop", "arguments": {}}),
                    self._loop,
                )
                fut.result(timeout=_SESSION_STOP_TIMEOUT)
            except Exception:
                pass
            self._session_connected = False

        if self._proc is not None:
            try:
                if self._proc.stdin is not None:
                    self._proc.stdin.close()
            except Exception:
                pass
            try:
                self._proc.terminate()
                self._proc.wait(timeout=5)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None

        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._loop = None
        self._ready.clear()
        self._initialized = False
        self._started = False

    # ── async primitives (run on the loop thread) ─────────────────────────

    async def _async_send(self, method: str, params: dict[str, Any] | None = None) -> Any:
        loop = asyncio.get_event_loop()
        with self._id_lock:
            msg_id = self._next_id
            self._next_id += 1
        evt = threading.Event()
        with self._id_lock:
            self._pending[msg_id] = evt

        assert self._proc is not None
        assert self._proc.stdin is not None
        msg = {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params or {}}
        self._proc.stdin.write(json.dumps(msg) + "\n")
        self._proc.stdin.flush()

        if not evt.wait(timeout=_REQUEST_TIMEOUT):
            with self._id_lock:
                self._pending.pop(msg_id, None)
            raise RuntimeError(f"kwin-mcp request timed out: {method}")

        with self._id_lock:
            self._pending.pop(msg_id, None)
        if msg_id in self._errors:
            exc = self._errors.pop(msg_id)
            raise exc
        return self._results.pop(msg_id, None)

    def _async_notify(self, method: str, params: dict[str, Any]) -> None:
        assert self._proc is not None
        assert self._proc.stdin is not None
        msg = {"jsonrpc": "2.0", "method": method, "params": params}
        self._proc.stdin.write(json.dumps(msg) + "\n")
        self._proc.stdin.flush()

    # ── async handshake (run on the loop thread) ──────────────────────────

    async def _async_handshake(self) -> None:
        result = await self._async_send(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "amatya", "version": "LVI"},
            },
        )
        # Send initialized notification (fire-and-forget).
        self._async_notify("notifications/initialized", {})
        # Confirm connectivity.
        await self._async_send("tools/list", {})

    def _handshake_sync(self) -> None:
        """Run initialize + initialized + tools/list on the loop thread."""
        fut = asyncio.run_coroutine_threadsafe(self._async_handshake(), self._loop)
        fut.result(timeout=_STARTUP_TIMEOUT)

    # ── synchronous public API ────────────────────────────────────────────
    def _call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        """Submit one JSON-RPC request to the loop thread and block for result."""
        if self._loop is None:
            raise RuntimeError("kwin-mcp client not started")
        fut = asyncio.run_coroutine_threadsafe(self._async_send(method, params), self._loop)
        return fut.result(timeout=_REQUEST_TIMEOUT)

    def list_tools(self) -> list[dict[str, Any]]:
        result = self._call("tools/list", {})
        return result.get("tools", []) if isinstance(result, dict) else []

    def connect_session(self, enable_accessibility: bool = True) -> Any:
        """Attach to the live KWin/Wayland desktop session."""
        result = self._call(
            "tools/call",
            {
                "name": "session_connect",
                "arguments": {"enable_accessibility": bool(enable_accessibility)},
            },
        )
        self._session_connected = True
        return result

    def close_session(self) -> Any:
        """Detach from the live KWin/Wayland desktop session."""
        self._session_connected = False
        return self._call("tools/call", {"name": "session_stop", "arguments": {}})

    # ── convenience wrappers — kwin-mcp v0.12.0 tool names ──────────────

    def keyboard_type(self, text: str, method: str = "unicode") -> Any:
        text_str = str(text)
        if method == "unicode" or not text_str.isascii():
            return self._call(
                "tools/call",
                {"name": "keyboard_type_unicode", "arguments": {"text": text_str}},
            )
        return self._call(
            "tools/call",
            {"name": "keyboard_type", "arguments": {"text": text_str}},
        )

    def keyboard_type_unicode(self, text: str) -> Any:
        return self._call(
            "tools/call",
            {"name": "keyboard_type_unicode", "arguments": {"text": str(text)}},
        )

    def keyboard_key(self, keys: str) -> Any:
        """Press and release one key or chord, e.g. 'Return', 'ctrl+c'."""
        return self._call(
            "tools/call", {"name": "keyboard_key", "arguments": {"key": str(keys)}}
        )

    def keyboard_key_down(self, keys: str) -> Any:
        """Press (hold) one key or chord."""
        return self._call(
            "tools/call", {"name": "keyboard_key_down", "arguments": {"key": str(keys)}}
        )

    def keyboard_key_up(self, keys: str) -> Any:
        """Release one key or chord."""
        return self._call(
            "tools/call", {"name": "keyboard_key_up", "arguments": {"key": str(keys)}}
        )

    def mouse_click(
        self,
        x: int,
        y: int,
        button: str = "left",
        count: int = 1,
        modifiers: Optional[Any] = None,
        hold_ms: int = 0,
        double: bool = False,
        triple: bool = False,
    ) -> Any:
        args: dict[str, Any] = {
            "x": int(x),
            "y": int(y),
            "button": button,
        }
        if triple or count >= 3:
            args["triple"] = True
        elif double or count == 2:
            args["double"] = True
        if modifiers:
            if isinstance(modifiers, str):
                args["modifiers"] = [m.strip() for m in modifiers.replace("+", ",").split(",") if m.strip()]
            elif isinstance(modifiers, (list, tuple)):
                args["modifiers"] = [str(m) for m in modifiers]
        if hold_ms:
            args["hold_ms"] = int(hold_ms)
        return self._call("tools/call", {"name": "mouse_click", "arguments": args})

    def mouse_move(self, x: int, y: int) -> Any:
        return self._call(
            "tools/call", {"name": "mouse_move", "arguments": {"x": int(x), "y": int(y)}}
        )

    def mouse_scroll(
        self,
        x: int,
        y: int,
        delta: int,
        horizontal: bool = False,
        discrete: bool = True,
        steps: int = 1,
    ) -> Any:
        return self._call(
            "tools/call",
            {
                "name": "mouse_scroll",
                "arguments": {
                    "x": int(x),
                    "y": int(y),
                    "delta": int(delta),
                    "horizontal": bool(horizontal),
                    "discrete": bool(discrete),
                    "steps": int(steps),
                },
            },
        )

    def mouse_drag(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        button: str = "left",
        modifiers: Optional[Any] = None,
        waypoints: Optional[list[Any]] = None,
        dwell_ms: int = 0,
    ) -> Any:
        args: dict[str, Any] = {
            "from_x": int(x1),
            "from_y": int(y1),
            "to_x": int(x2),
            "to_y": int(y2),
            "button": button,
        }
        if modifiers:
            if isinstance(modifiers, str):
                args["modifiers"] = [m.strip() for m in modifiers.replace("+", ",").split(",") if m.strip()]
            elif isinstance(modifiers, (list, tuple)):
                args["modifiers"] = [str(m) for m in modifiers]
        if waypoints:
            norm_wp = []
            for wp in waypoints:
                if isinstance(wp, dict):
                    norm_wp.append([
                        int(wp.get("x", 0)),
                        int(wp.get("y", 0)),
                        int(wp.get("dwell_ms", dwell_ms or 50)),
                    ])
                elif isinstance(wp, (list, tuple)) and len(wp) >= 2:
                    norm_wp.append([
                        int(wp[0]),
                        int(wp[1]),
                        int(wp[2]) if len(wp) >= 3 else int(dwell_ms or 50),
                    ])
            if norm_wp:
                args["waypoints"] = norm_wp
        return self._call("tools/call", {"name": "mouse_drag", "arguments": args})

    def mouse_button_down(self, x: int, y: int, button: str = "left") -> Any:
        return self._call(
            "tools/call",
            {"name": "mouse_button_down", "arguments": {"x": int(x), "y": int(y), "button": button}},
        )

    def mouse_button_up(self, x: int, y: int, button: str = "left") -> Any:
        return self._call(
            "tools/call",
            {"name": "mouse_button_up", "arguments": {"x": int(x), "y": int(y), "button": button}},
        )

    def screenshot(
        self,
        region: Optional[Any] = None,
        max_edge: Optional[int] = None,
        include_cursor: bool = False,
    ) -> Any:
        args: dict[str, Any] = {}
        if region:
            if isinstance(region, dict):
                rx = int(region.get("x", 0))
                ry = int(region.get("y", 0))
                rw = int(region.get("width", region.get("w", 0)))
                rh = int(region.get("height", region.get("h", 0)))
                if rw > 0 and rh > 0:
                    args["region"] = [rx, ry, rw, rh]
            elif isinstance(region, (list, tuple)) and len(region) == 4:
                args["region"] = [int(v) for v in region]
        if max_edge is not None:
            args["max_edge"] = int(max_edge)
        if include_cursor:
            args["include_cursor"] = True
        return self._call("tools/call", {"name": "screenshot", "arguments": args})

    # Alias for callers using the older name
    screen_capture = screenshot

    def active_window(self) -> Any:
        return self._call("tools/call", {"name": "active_window", "arguments": {}})

    def accessibility_tree(
        self,
        app_name: str = "",
        max_depth: int = 15,
        role: str = "",
    ) -> Any:
        args: dict[str, Any] = {"max_depth": int(max_depth)}
        if app_name:
            args["app_name"] = str(app_name)
        if role:
            args["role"] = str(role)
        return self._call("tools/call", {"name": "accessibility_tree", "arguments": args})

    def find_ui_elements(
        self,
        query: Optional[str] = None,
        app_name: Optional[str] = None,
        states: Optional[list[str]] = None,
        max_depth: int = 15,  # accepted for backwards compatibility
    ) -> Any:
        args: dict[str, Any] = {"query": str(query or "")}
        if app_name:
            args["app_name"] = str(app_name)
        if states:
            args["states"] = [str(s) for s in states]
        return self._call(
            "tools/call", {"name": "find_ui_elements", "arguments": args}
        )

    def wait_for_element(
        self,
        query: str = "",
        app_name: str = "",
        timeout_ms: int = 5000,
        poll_interval_ms: int = 200,
        expected_states: Optional[list[str]] = None,
    ) -> Any:
        args: dict[str, Any] = {
            "query": str(query),
            "timeout_ms": int(timeout_ms),
            "poll_interval_ms": int(poll_interval_ms),
        }
        if app_name:
            args["app_name"] = str(app_name)
        if expected_states:
            args["expected_states"] = [str(s) for s in expected_states]
        return self._call("tools/call", {"name": "wait_for_element", "arguments": args})

    def invoke_ui_action(
        self,
        query: str,
        action_name: str = "Press",
        app_name: Optional[str] = None,
        exact_name: bool = False,
        fallback_action_names: Optional[list[str]] = None,
        spoken_name: bool = False,
    ) -> Any:
        args: dict[str, Any] = {"query": str(query), "action_name": str(action_name or "Press")}
        if app_name:
            args["app_name"] = str(app_name)
        if exact_name:
            args["exact_name"] = True
        if fallback_action_names is not None:
            args["fallback_action_names"] = [str(a) for a in fallback_action_names]
        if spoken_name and not exact_name:
            args["spoken_name"] = True
        return self._call(
            "tools/call", {"name": "invoke_ui_action", "arguments": args}
        )

    def list_windows(self) -> Any:
        return self._call("tools/call", {"name": "list_windows", "arguments": {}})

    # Alias for callers using the older name
    window_list = list_windows

    def get_kwin_windows(self, app_name: str = "") -> list[dict[str, Any]]:
        """Return normalized KWin window list with id, app, app_id, caption, title, active, and geometry."""
        out: list[dict[str, Any]] = []
        try:
            res = self.window_geometry(app_name=app_name or None)
            if isinstance(res, dict):
                sc = res.get("structuredContent") or res.get("structured_content") or {}
                wins = sc.get("windows") if isinstance(sc, dict) else None
                if isinstance(wins, list):
                    for w in wins:
                        if not isinstance(w, dict):
                            continue
                        frame = w.get("frame") if isinstance(w.get("frame"), dict) else {}
                        client_rect = w.get("client") if isinstance(w.get("client"), dict) else frame
                        app_str = str(w.get("app") or w.get("app_id") or "")
                        cap_str = str(w.get("caption") or w.get("title") or "")
                        out.append({
                            "id": str(w.get("id", "")),
                            "app": app_str,
                            "app_id": app_str,
                            "caption": cap_str,
                            "title": cap_str,
                            "active": bool(w.get("active", False)),
                            "frame": frame,
                            "client": client_rect,
                            "x": int(frame.get("x", 0)),
                            "y": int(frame.get("y", 0)),
                            "width": int(frame.get("width", 0)),
                            "height": int(frame.get("height", 0)),
                        })
        except Exception:
            pass
        if out:
            return out
        # Fallback: check AT-SPI list_windows
        try:
            res = self.list_windows()
            if isinstance(res, list):
                return [w for w in res if isinstance(w, dict)]
            if isinstance(res, dict):
                sc = res.get("structuredContent") or res.get("structured_content") or {}
                apps = sc.get("applications") if isinstance(sc, dict) else None
                if isinstance(apps, list):
                    for app_entry in apps:
                        if not isinstance(app_entry, dict):
                            continue
                        aname = str(app_entry.get("name", ""))
                        if app_name and app_name.lower() not in aname.lower():
                            continue
                        for win in app_entry.get("windows", []) or [{"title": aname}]:
                            wtitle = str(win.get("title", aname)) if isinstance(win, dict) else aname
                            out.append({
                                "id": aname,
                                "app": aname,
                                "app_id": aname,
                                "caption": wtitle,
                                "title": wtitle,
                                "active": False,
                            })
        except Exception:
            pass
        return out

    def virtual_desktops(self) -> Any:
        return self._call("tools/call", {"name": "virtual_desktops", "arguments": {}})

    # Alias for callers using the older name
    desktop_list = virtual_desktops

    def focus_window(
        self,
        app_name: Optional[str] = None,
        window_id: Optional[Any] = None,
    ) -> Any:
        args: dict[str, Any] = {}
        if isinstance(app_name, dict):
            # Handle legacy focus_window({"id": ...}) call shape
            wid = app_name.get("id") or app_name.get("window_id")
            if wid is not None:
                args["window_id"] = str(wid)
            if app_name.get("app_name"):
                args["app_name"] = str(app_name["app_name"])
        else:
            if app_name:
                args["app_name"] = str(app_name)
            if window_id is not None:
                args["window_id"] = str(window_id)
        return self._call("tools/call", {"name": "focus_window", "arguments": args})

    def window_geometry(
        self,
        app_name: Optional[str] = None,
        window_id: Optional[Any] = None,
    ) -> Any:
        args: dict[str, Any] = {}
        if app_name:
            args["app_name"] = str(app_name)
        if window_id is not None:
            args["window_id"] = str(window_id)
        return self._call(
            "tools/call", {"name": "window_geometry", "arguments": args}
        )

    def window_set_geometry(
        self,
        window_id: Any,
        x: Optional[int] = None,
        y: Optional[int] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
    ) -> Any:
        args: dict[str, Any] = {"window_id": str(window_id)}
        if x is not None:
            args["x"] = int(x)
        if y is not None:
            args["y"] = int(y)
        if width is not None:
            args["width"] = int(width)
        if height is not None:
            args["height"] = int(height)
        return self._call(
            "tools/call", {"name": "window_set_geometry", "arguments": args}
        )

    def window_set_desktop(self, window_id: Any, desktop_id: str) -> Any:
        return self._call(
            "tools/call",
            {
                "name": "window_set_desktop",
                "arguments": {"window_id": str(window_id), "desktop_id": str(desktop_id)},
            },
        )

    def window_close(self, window_id: Any) -> Any:
        if isinstance(window_id, dict):
            window_id = window_id.get("id") or window_id.get("window_id") or ""
        wid = str(window_id)
        res = self._call(
            "tools/call", {"name": "window_close", "arguments": {"window_id": wid}}
        )
        if isinstance(res, dict) and res.get("isError"):
            content = res.get("content", [])
            err_txt = " ".join(
                str(b.get("text", "")) for b in content if isinstance(b, dict)
            )
            if "disabled in live sessions" in err_txt:
                # In a live session, focus the specific window and press Alt+F4
                self.focus_window(window_id=wid)
                return self.keyboard_key("alt+F4")
        return res

    def clipboard_get(self) -> Any:
        return self._call("tools/call", {"name": "clipboard_get", "arguments": {}})

    def clipboard_set(self, text: str) -> Any:
        return self._call(
            "tools/call", {"name": "clipboard_set", "arguments": {"text": str(text)}}
        )

    def touch_tap(self, x: int, y: int, hold_ms: int = 0) -> Any:
        args: dict[str, Any] = {"x": int(x), "y": int(y)}
        if hold_ms:
            args["hold_ms"] = int(hold_ms)
        return self._call("tools/call", {"name": "touch_tap", "arguments": args})

    def touch_swipe(
        self,
        from_x: int,
        from_y: int,
        to_x: int,
        to_y: int,
        fingers: int = 1,
        duration_ms: int = 300,
    ) -> Any:
        if int(fingers) > 1:
            return self._call(
                "tools/call",
                {
                    "name": "touch_multi_swipe",
                    "arguments": {
                        "from_x": int(from_x),
                        "from_y": int(from_y),
                        "to_x": int(to_x),
                        "to_y": int(to_y),
                        "fingers": int(fingers),
                        "duration_ms": int(duration_ms),
                    },
                },
            )
        return self._call(
            "tools/call",
            {
                "name": "touch_swipe",
                "arguments": {
                    "from_x": int(from_x),
                    "from_y": int(from_y),
                    "to_x": int(to_x),
                    "to_y": int(to_y),
                    "duration_ms": int(duration_ms),
                },
            },
        )

    def touch_pinch(
        self,
        center_x: int,
        center_y: int,
        start_distance: float,
        end_distance: float,
        duration_ms: int = 500,
    ) -> Any:
        return self._call(
            "tools/call",
            {
                "name": "touch_pinch",
                "arguments": {
                    "center_x": int(center_x),
                    "center_y": int(center_y),
                    "start_distance": int(start_distance),
                    "end_distance": int(end_distance),
                    "duration_ms": int(duration_ms),
                },
            },
        )

    def dbus_call(
        self,
        service: str,
        path: str,
        interface: str,
        method: str,
        args=None,
    ) -> Any:
        call_args: dict[str, Any] = {
            "service": service,
            "path": path,
            "interface": interface,
            "method": method,
        }
        if args is not None:
            call_args["args"] = args
        return self._call("tools/call", {"name": "dbus_call", "arguments": call_args})

    def wayland_info(self, filter: str = "") -> Any:
        return self._call(
            "tools/call", {"name": "wayland_info", "arguments": {"filter_protocol": filter}}
        )

    def launch_app(self, command: str, env=None) -> Any:
        args: dict[str, Any] = {"command": command}
        if env is not None:
            args["env"] = env
        return self._call("tools/call", {"name": "launch_app", "arguments": args})

    def read_app_log(self, pid: int, last_n_lines: int = 50) -> Any:
        return self._call(
            "tools/call",
            {
                "name": "read_app_log",
                "arguments": {"pid": int(pid), "last_n_lines": int(last_n_lines)},
            },
        )


# ── module-level singleton ─────────────────────────────────────────────

_client: Optional[_McpSession] = None
_client_lock = threading.Lock()


def get_client(log=None) -> _McpSession:
    """Return the singleton kwin-mcp client, creating it if needed."""
    global _client
    with _client_lock:
        if _client is None:
            _client = _McpSession(log=log)
    return _client


def reset_client() -> None:
    """Drop the singleton (mainly for tests)."""
    global _client
    with _client_lock:
        _client = None


def available() -> bool:
    """True if kwin-mcp can be found on PATH, in the current venv, or as a module."""
    return _resolve_server_cmd() is not None
