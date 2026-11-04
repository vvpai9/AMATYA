"""
core/screen_automation.py — Enhanced screen capture & automation for AMATYA.

WHAT THIS IS
    Builds on core/vision.py to provide:

    * Multi-monitor discovery and per-monitor capture
    * Active-window capture via kwin-mcp window list
    * Continuous / periodic screen observation (opt-in)
    * Screenshot history management with pruning
    * Before/after action verification pairs

DESIGN
    All capture goes through Vision. This module adds the automation
    orchestration: discovering monitors, tracking the active window, running
    periodic observation loops, and managing the screenshot history.

    On Wayland, kwin-mcp provides window enumeration and screen capture.
    On X11, mss is the fallback.
"""
from __future__ import annotations

import asyncio
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from core.lazyimport import installed
from core.vision import CaptureResult, ComparisonResult, Vision, get_vision


@dataclass
class MonitorInfo:
    """Information about a connected display."""
    index: int          # 1-based
    x: int
    y: int
    width: int
    height: int
    primary: bool = False


@dataclass
class WindowInfo:
    """Information about a window (kwin-mcp)."""
    id: Any
    app_id: str
    caption: str
    active: bool
    frame: Optional[dict[str, Any]] = None
    client: Optional[dict[str, Any]] = None


@dataclass
class ObservationConfig:
    """Configuration for continuous observation."""
    enabled: bool = False
    interval_seconds: float = 30.0
    min_change_percent: float = 1.0   # only log if >1% changed
    max_history: int = 500


class ScreenAutomation:
    """
    Orchestrates screen capture across monitors and windows.

    Usage:
        sa = ScreenAutomation()
        monitors = sa.discover_monitors()
        cap = sa.capture_active_window()
        sa.start_observation(interval=30.0)
    """

    def __init__(self, log=None):
        self._log = log or (lambda m: None)
        self._vision = get_vision(log=log)
        self._monitors: list[MonitorInfo] = []
        self._observation_task: Optional[asyncio.Task] = None
        self._observation_config = ObservationConfig()
        self._observation_lock = threading.Lock()
        self._last_observation_hash: Optional[str] = None
        self._discover_monitors()

    # ── monitor discovery ──────────────────────────────────────────────

    def _discover_monitors(self) -> None:
        """Discover connected monitors via KDE kscreen-doctor, kwin-mcp, or mss."""
        self._monitors = []

        # 1. Try KDE kscreen-doctor JSON (Wayland-native on KDE Plasma 6).
        try:
            import json as _json
            import shutil as _shutil
            import subprocess as _sp
            if _shutil.which("kscreen-doctor"):
                proc = _sp.run(
                    ["kscreen-doctor", "-j"],
                    capture_output=True, text=True, timeout=3,
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    data = _json.loads(proc.stdout)
                    outputs = [
                        o for o in data.get("outputs", [])
                        if isinstance(o, dict) and o.get("enabled") and o.get("connected")
                    ]
                    for idx, out in enumerate(outputs, start=1):
                        pos = out.get("pos") or {}
                        size = out.get("size") or {}
                        w = int(size.get("width", 0))
                        h = int(size.get("height", 0))
                        if w > 0 and h > 0:
                            self._monitors.append(MonitorInfo(
                                index=idx,
                                x=int(pos.get("x", 0)),
                                y=int(pos.get("y", 0)),
                                width=w,
                                height=h,
                                primary=bool(out.get("priority", idx) == 1 or out.get("primary", idx == 1)),
                            ))
        except Exception:
            pass

        # 2. Fallback: mss monitor enumeration (X11 or XWayland).
        if not self._monitors:
            try:
                mss_mod = installed("mss")
                if mss_mod:
                    import mss  # type: ignore[import-untyped]
                    with mss.mss() as sct:
                        for i, mon in enumerate(sct.monitors):
                            if i == 0:
                                continue  # skip "all combined"
                            self._monitors.append(MonitorInfo(
                                index=i,
                                x=mon.get("left", 0),
                                y=mon.get("top", 0),
                                width=mon.get("width", 0),
                                height=mon.get("height", 0),
                                primary=(i == 1),
                            ))
            except Exception:
                pass

        if not self._monitors:
            # Ultimate fallback: a single synthetic monitor.
            self._monitors.append(MonitorInfo(index=1, x=0, y=0,
                                              width=1920, height=1080, primary=True))

    def discover_monitors(self) -> list[MonitorInfo]:
        """Return the list of connected monitors."""
        return list(self._monitors)

    def primary_monitor(self) -> MonitorInfo:
        """Return the primary monitor, or the first one."""
        for m in self._monitors:
            if m.primary:
                return m
        return self._monitors[0] if self._monitors else MonitorInfo(
            index=1, x=0, y=0, width=1920, height=1080, primary=True)

    # ── capture methods ─────────────────────────────────────────────────

    def capture_full(self) -> CaptureResult:
        """Capture the entire desktop."""
        return self._vision.capture_full()

    def capture_monitor(self, index: int = 1) -> CaptureResult:
        """Capture a specific monitor (1-based)."""
        return self._vision.capture_monitor(index)

    def capture_region(self, x: int, y: int, width: int, height: int) -> CaptureResult:
        """Capture a rectangular region."""
        return self._vision.capture_region(x, y, width, height)

    def capture_active_window(self) -> CaptureResult:
        """
        Capture the currently focused window.

        On Wayland with kwin-mcp, this queries window geometry for the active
        window and captures its region. Falls back to full desktop if no
        active window can be determined.
        """
        try:
            cap = self._vision.capture_active_window()
            if cap.ok:
                return cap
        except Exception as e:
            self._log(f"[ScreenAutomation] active window capture error: {e}")

        # Fall back to full desktop capture.
        return self.capture_full()

    def _parse_window_list(self, result: Any) -> list[WindowInfo]:
        """Parse a kwin-mcp window list or geometry result into WindowInfo objects."""
        windows: list[WindowInfo] = []
        if isinstance(result, list):
            for w in result:
                if isinstance(w, dict):
                    windows.append(WindowInfo(
                        id=w.get("id", ""),
                        app_id=str(w.get("app_id") or w.get("app") or ""),
                        caption=str(w.get("caption") or w.get("title") or ""),
                        active=bool(w.get("active", False)),
                        frame=w.get("frame"),
                        client=w.get("client"),
                    ))
            return windows
        if not isinstance(result, dict):
            return windows

        content = result.get("content", [])
        structured = result.get("structuredContent") or result.get("structured_content") or {}

        # Try structured content first.
        if isinstance(structured, dict):
            items = structured.get("windows") or structured.get("items") or []
            if isinstance(items, list):
                for w in items:
                    if isinstance(w, dict):
                        windows.append(WindowInfo(
                            id=w.get("id", ""),
                            app_id=str(w.get("app_id") or w.get("app") or ""),
                            caption=str(w.get("caption") or w.get("title") or ""),
                            active=bool(w.get("active", False)),
                            frame=w.get("frame"),
                            client=w.get("client"),
                        ))

        # Fall back to parsing content blocks.
        if not windows and isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text", "")
                    for line in text.splitlines():
                        parts = {}
                        for kv in line.split():
                            if "=" in kv:
                                k, v = kv.split("=", 1)
                                parts[k] = v
                        if "id" in parts:
                            windows.append(WindowInfo(
                                id=parts["id"],
                                app_id=parts.get("app", ""),
                                caption=parts.get("caption", ""),
                                active=parts.get("active", "False") == "True",
                            ))

        return windows

    def list_windows(self) -> list[WindowInfo]:
        """List all windows via kwin-mcp."""
        try:
            from core.kwin_mcp_client import get_client, available as kwin_available
            if not kwin_available():
                return []
            client = get_client(log=self._log)
            client.ensure_started()
            wins = client.get_kwin_windows()
            return self._parse_window_list(wins)
        except Exception as e:
            self._log(f"[ScreenAutomation] window list failed: {e}")
            return []

    # ── observation loop ─────────────────────────────────────────────────

    def start_observation(
        self,
        interval_seconds: float = 30.0,
        min_change_percent: float = 1.0,
        max_history: int = 500,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        """
        Start periodic screen observation.

        Captures the full desktop every `interval_seconds`. If the screen
        changes by more than `min_change_percent`, logs a SYS message.
        Observation history is capped at `max_history`.

        This runs as an asyncio task on the given loop (main.py's loop).
        """
        with self._observation_lock:
            if self._observation_task is not None and not self._observation_task.done():
                self._log("[ScreenAutomation] observation already running")
                return

            self._observation_config = ObservationConfig(
                enabled=True,
                interval_seconds=interval_seconds,
                min_change_percent=min_change_percent,
                max_history=max_history,
            )
            self._last_observation_hash = None

            loop = loop or asyncio.get_event_loop()
            self._observation_task = asyncio.create_task(self._observation_loop(loop))
            self._log(f"[ScreenAutomation] observation started (interval={interval_seconds}s)")

    async def _observation_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Background task: periodic capture + comparison."""
        cfg = self._observation_config
        while self._observation_config.enabled:
            await asyncio.sleep(cfg.interval_seconds)
            if not self._observation_config.enabled:
                break

            try:
                cap = await loop.run_in_executor(None, self.capture_full)
                if not cap.ok:
                    self._log(f"[ScreenAutomation] capture failed: {cap.error}")
                    continue

                with self._observation_lock:
                    if self._last_observation_hash is not None \
                            and cap.hash == self._last_observation_hash:
                        continue  # no change

                    self._vision._history.append(cap)
                    while len(self._vision._history) > cfg.max_history:
                        self._vision._history.pop(0)

                    self._last_observation_hash = cap.hash
                    self._log(
                        f"[ScreenAutomation] observation: {cap.size_kb}KB, hash={cap.hash}"
                    )
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._log(f"[ScreenAutomation] observation error: {e}")

    def stop_observation(self) -> None:
        """Stop the periodic observation loop."""
        with self._observation_lock:
            self._observation_config.enabled = False
            if self._observation_task is not None:
                self._observation_task.cancel()
                self._observation_task = None
            self._last_observation_hash = None
        self._log("[ScreenAutomation] observation stopped")

    # ── before/after verification ───────────────────────────────────────

    def verify_action(
        self,
        label: str,
        expect_change: bool = True,
    ) -> tuple[CaptureResult, CaptureResult, ComparisonResult]:
        """
        Capture before, run the action externally, capture after, compare.

        The caller is responsible for performing the action between the two
        captures. This method just captures and compares.

        Returns (before, after, comparison).
        """
        before = self._vision.capture_before(label)
        after = self._vision.capture_full()
        comp = self._vision.compare(before, after)
        self._log(
            f"[ScreenAutomation] verify '{label}': changed={comp.changed}, "
            f"similarity={comp.similarity}, diff_pixels={comp.diff_pixels}"
        )
        if expect_change and not comp.changed:
            self._log(f"[ScreenAutomation] ⚠️  No change detected after '{label}'")
        return before, after, comp


# ── module-level singleton ─────────────────────────────────────────────

_automation: Optional[ScreenAutomation] = None
_automation_lock = threading.Lock()


def get_automation(log=None) -> ScreenAutomation:
    """Return the singleton ScreenAutomation instance."""
    global _automation
    with _automation_lock:
        if _automation is None:
            _automation = ScreenAutomation(log=log)
    return _automation


def reset_automation() -> None:
    """Drop the singleton (mainly for tests)."""
    global _automation
    with _automation_lock:
        _automation = None
