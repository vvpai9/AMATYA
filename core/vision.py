"""
core/vision.py — Vision subsystem for AMATYA.

WHAT THIS IS
    A vision layer that lets AMATYA understand what is on screen. It combines:

    * Screen capture via kwin-mcp (Wayland-native, KDE Plasma 6) or mss (X11 fallback)
    * OCR via pytesseract (optional) or OpenCV preprocessing + Gemini Live VLM
    * Vision-language understanding through the existing Gemini Live session
    * Screenshot comparison (before/after) to verify action outcomes

ARCHITECTURE
    Vision is replaceable: the VLM backend can be swapped without touching the
    rest of the app. By default it uses the main Gemini Live session's vision
    capability (screenshots are injected as user turns). An optional local VLM
    can be routed through the providers/ sidecar.

THREADING
    All public methods are synchronous. Capture runs in an executor thread from
    main.py; OCR and image processing are CPU-bound and also run in the
    executor. VLM calls go through the async session loop.

CAPTURE MODES
    * full        — entire desktop (all monitors combined)
    * monitor(N)  — a specific monitor by index (1-based)
    * window(N)   — a specific window by kwin-mcp window id
    * region      — a rectangular region {x, y, width, height}

BEFORE/AFTER VERIFICATION
    capture_before() / capture_after() pairs let the desktop agent verify that
    an action changed the screen as expected. Results are stored in
    screenshot_history for review.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import platform
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np

from core.lazyimport import LazyModule, installed

# Optional OCR
_PYTESSERACT = installed("pytesseract")
pytesseract = None  # type: ignore[assignment]
if _PYTESSERACT:
    import pytesseract  # type: ignore[assignment]

# OpenCV for image preprocessing
_CV2 = installed("cv2")
cv2 = LazyModule("cv2")

# PIL for image handling
_PIL = installed("PIL")
PILImage = None  # type: ignore[assignment]
if _PIL:
    from PIL import Image as PILImage  # type: ignore[assignment]


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


_BASE = _base_dir()
SCREENSHOT_DIR = _BASE / "memory" / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

_MAX_SCREENSHOTS = 200   # cap history size


@dataclass
class CaptureResult:
    """Result of a screen capture."""
    ok: bool
    image_bytes: bytes = b""
    mime_type: str = "image/png"
    monitor: int = 0
    region: Optional[dict[str, Any]] = None
    size_kb: int = 0
    hash: str = ""
    path: Optional[str] = None
    uri: Optional[str] = None
    error: Optional[str] = None
    captured_at: float = field(default_factory=time.time)


@dataclass
class OCRResult:
    """Result of OCR on an image."""
    ok: bool
    text: str = ""
    confidence: float = 0.0
    error: Optional[str] = None


@dataclass
class ComparisonResult:
    """Result of comparing two screenshots."""
    changed: bool
    similarity: float   # 0.0 = totally different, 1.0 = identical
    diff_pixels: int = 0
    error: Optional[str] = None


class Vision:
    """
    Vision subsystem: capture, OCR, VLM understanding, comparison.

    Usage:
        vision = Vision()
        cap = vision.capture_full()                      # full desktop
        text = vision.ocr(cap.image_bytes)               # OCR (if pytesseract)
        desc = vision.describe(cap.image_bytes, "What is open?")  # VLM
        comp = vision.compare(before, after)             # did screen change?
    """

    def __init__(self, log=None):
        self._log = log or (lambda m: None)
        self._history: list[CaptureResult] = []
        self._kwin_client = None   # set lazily when on Wayland + kwin-mcp

    # ── lifecycle ────────────────────────────────────────────────────────

    def _ensure_kwin(self) -> bool:
        """Get the kwin-mcp client if on Wayland and ensure it is started."""
        if self._kwin_client is not None and self._kwin_client.running:
            return True
        try:
            from core.kwin_mcp_client import get_client, available as kwin_available
            if not kwin_available():
                return False
            self._kwin_client = get_client(log=self._log)
            self._kwin_client.ensure_started()
            return self._kwin_client.running
        except Exception as e:
            self._log(f"[Vision] kwin-mcp unavailable: {e}")
            return False

    # ── capture ──────────────────────────────────────────────────────────

    def capture_full(self) -> CaptureResult:
        """Capture the entire desktop (all monitors)."""
        return self._capture(kind="full")

    def capture_monitor(self, index: int = 1) -> CaptureResult:
        """Capture a specific monitor (1-based)."""
        return self._capture(kind="monitor", monitor=index)

    def capture_region(self, x: int, y: int, width: int, height: int) -> CaptureResult:
        """Capture a rectangular region in global logical pixels."""
        return self._capture(
            kind="region",
            region={"x": x, "y": y, "width": width, "height": height},
        )

    def capture_window(self, window_id: Any) -> CaptureResult:
        """Capture a specific window by kwin-mcp window id or app name."""
        return self._capture(kind="window", window_id=window_id)

    def capture_active_window(self) -> CaptureResult:
        """Capture the currently focused/active window."""
        return self._capture(kind="active_window")

    @staticmethod
    def _is_completely_black(image_bytes: bytes) -> bool:
        """Return True if image data represents an unpainted/black buffer."""
        if not image_bytes or len(image_bytes) < 100:
            return True
        try:
            import io
            from PIL import Image
            import numpy as np
            im = Image.open(io.BytesIO(image_bytes))
            arr = np.asarray(im)
            return bool(arr.max() == 0)
        except Exception:
            return False

    def _capture(
        self,
        kind: str,
        monitor: int = 1,
        region: Optional[dict[str, Any]] = None,
        window_id: Optional[Any] = None,
    ) -> CaptureResult:
        """Internal capture dispatcher with graceful multi-tier fallback."""
        fallback_candidate: Optional[CaptureResult] = None

        # 1. Try kwin-mcp on Wayland (native, works where mss fails).
        if self._ensure_kwin():
            try:
                res = self._capture_kwin(kind, monitor, region, window_id)
                if res.ok and res.image_bytes:
                    if not self._is_completely_black(res.image_bytes):
                        return res
                    fallback_candidate = fallback_candidate or res
                self._log("[Vision] kwin-mcp returned empty or black image, falling back.")
            except Exception as e:
                self._log(f"[Vision] kwin-mcp capture error, falling back: {e}")

        # 2. Native KDE Plasma Wayland capture via spectacle (Linux)
        if platform.system() == "Linux":
            try:
                res_spec = self._capture_spectacle(kind, monitor, region, window_id)
                if res_spec.ok and res_spec.image_bytes:
                    if not self._is_completely_black(res_spec.image_bytes):
                        return res_spec
                    fallback_candidate = fallback_candidate or res_spec
                self._log("[Vision] spectacle returned empty or black image, falling back.")
            except Exception as e:
                self._log(f"[Vision] spectacle capture error, falling back: {e}")

        # 3. Native macOS screencapture
        if platform.system() == "Darwin":
            try:
                res_mac = self._capture_macos_screencapture(kind, monitor, region, window_id)
                if res_mac.ok and res_mac.image_bytes:
                    if not self._is_completely_black(res_mac.image_bytes):
                        return res_mac
                    fallback_candidate = fallback_candidate or res_mac
            except Exception as e:
                self._log(f"[Vision] macOS screencapture error: {e}")

        # 4. Native Windows ImageGrab
        if platform.system() == "Windows":
            try:
                res_win = self._capture_windows_imagegrab(kind, monitor, region)
                if res_win.ok and res_win.image_bytes:
                    if not self._is_completely_black(res_win.image_bytes):
                        return res_win
                    fallback_candidate = fallback_candidate or res_win
            except Exception as e:
                self._log(f"[Vision] Windows ImageGrab error: {e}")

        # 5. Fallback to mss (X11, Windows, macOS, or when other backends fail).
        try:
            res_mss = self._capture_mss(kind, monitor, region)
            if res_mss.ok and res_mss.image_bytes:
                if not self._is_completely_black(res_mss.image_bytes):
                    return res_mss
                fallback_candidate = fallback_candidate or res_mss
        except Exception as e:
            self._log(f"[Vision] mss capture error: {e}")

        if fallback_candidate is not None and fallback_candidate.ok and fallback_candidate.image_bytes:
            return fallback_candidate

        return CaptureResult(ok=False, error="All screen capture backends failed or returned unpainted frames.")

    def _capture_spectacle(
        self,
        kind: str,
        monitor: int = 1,
        region: Optional[dict[str, Any]] = None,
        window_id: Optional[Any] = None,
    ) -> CaptureResult:
        """Capture via spectacle (KDE Plasma Wayland native tool)."""
        import shutil as _shutil
        import subprocess as _sp
        import tempfile as _tmp
        if not _shutil.which("spectacle"):
            return CaptureResult(ok=False, error="spectacle not installed")
        tmp_file = Path(_tmp.gettempdir()) / f"amatya_spec_{int(time.time() * 1000)}.png"
        cmd = ["spectacle", "-b", "-n"]
        if kind in ("window", "active_window"):
            cmd.append("-a")
        elif kind == "monitor":
            cmd.append("-m")
        else:
            cmd.append("-f")
        for attempt in range(2):
            tmp_file = Path(_tmp.gettempdir()) / f"amatya_spec_{int(time.time() * 1000)}_{attempt}.png"
            cmd_run = list(cmd) + ["-o", str(tmp_file)]
            try:
                p = _sp.run(cmd_run, capture_output=True, timeout=8)
                # Spectacle can flush file asynchronously right before/after exit
                for _ in range(12):
                    if tmp_file.exists() and tmp_file.stat().st_size > 0:
                        break
                    time.sleep(0.1)

                if tmp_file.exists() and tmp_file.stat().st_size > 0:
                    img_bytes = tmp_file.read_bytes()
                    tmp_file.unlink(missing_ok=True)
                    # If region requested, crop image using PIL
                    if kind == "region" and region:
                        try:
                            import io
                            from PIL import Image
                            im = Image.open(io.BytesIO(img_bytes))
                            box = (region["x"], region["y"], region["x"] + region["width"], region["y"] + region["height"])
                            cropped = im.crop(box)
                            buf = io.BytesIO()
                            cropped.save(buf, format="PNG")
                            img_bytes = buf.getvalue()
                        except Exception:
                            pass
                    return self._finalize_capture(img_bytes, "image/png", kind, monitor, region, window_id, None, None)
                if attempt == 0:
                    time.sleep(0.3)
            except Exception as exc:
                if attempt == 0:
                    time.sleep(0.3)
                    continue
                return CaptureResult(ok=False, error=f"spectacle error: {exc}")

        err_msg = p.stderr.decode("utf-8", errors="ignore") if p.stderr else "unknown error"
        return CaptureResult(ok=False, error=f"spectacle failed: {err_msg}")

    def _capture_macos_screencapture(
        self,
        kind: str,
        monitor: int = 1,
        region: Optional[dict[str, Any]] = None,
        window_id: Optional[Any] = None,
    ) -> CaptureResult:
        """Capture via macOS native screencapture tool."""
        import subprocess as _sp
        import tempfile as _tmp
        import shutil as _shutil

        if not _shutil.which("screencapture"):
            return CaptureResult(ok=False, error="screencapture not available")

        tmp_file = Path(_tmp.gettempdir()) / f"amatya_mac_{int(time.time() * 1000)}.png"
        cmd = ["screencapture", "-x"]  # -x = silent, no sound
        if kind in ("window", "active_window"):
            cmd.append("-w")
        elif kind == "region" and region:
            cmd.extend(["-R", f"{region['x']},{region['y']},{region['width']},{region['height']}"])

        cmd.append(str(tmp_file))

        try:
            p = _sp.run(cmd, capture_output=True, timeout=6)
            if tmp_file.exists() and tmp_file.stat().st_size > 0:
                img_bytes = tmp_file.read_bytes()
                tmp_file.unlink(missing_ok=True)
                return self._finalize_capture(img_bytes, "image/png", kind, monitor, region, window_id, None, None)
            return CaptureResult(ok=False, error="screencapture produced no output")
        except Exception as exc:
            return CaptureResult(ok=False, error=f"screencapture error: {exc}")

    def _capture_windows_imagegrab(
        self,
        kind: str,
        monitor: int = 1,
        region: Optional[dict[str, Any]] = None,
    ) -> CaptureResult:
        """Capture via PIL.ImageGrab on Windows."""
        try:
            from PIL import ImageGrab
            import io
            if kind == "region" and region:
                bbox = (region["x"], region["y"], region["x"] + region["width"], region["y"] + region["height"])
                im = ImageGrab.grab(bbox=bbox, all_screens=True)
            else:
                im = ImageGrab.grab(all_screens=True)
            buf = io.BytesIO()
            im.save(buf, format="PNG")
            img_bytes = buf.getvalue()
            return self._finalize_capture(img_bytes, "image/png", kind, monitor, region, None, None, None)
        except Exception as exc:
            return CaptureResult(ok=False, error=f"Windows ImageGrab error: {exc}")

    def _get_monitor_region(self, monitor: int) -> Optional[dict[str, int]]:
        """Query KDE kscreen-doctor JSON for monitor geometry (1-based index)."""
        try:
            import json as _json
            import shutil as _shutil
            import subprocess as _sp
            if _shutil.which("kscreen-doctor"):
                proc = _sp.run(
                    ["kscreen-doctor", "-j"],
                    capture_output=True, text=True, timeout=3
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    data = _json.loads(proc.stdout)
                    outputs = [
                        o for o in data.get("outputs", [])
                        if isinstance(o, dict) and o.get("enabled") and o.get("connected")
                    ]
                    if 1 <= monitor <= len(outputs):
                        out = outputs[monitor - 1]
                        pos = out.get("pos") or {}
                        size = out.get("size") or {}
                        w = int(size.get("width", 0))
                        h = int(size.get("height", 0))
                        if w > 0 and h > 0:
                            return {
                                "x": int(pos.get("x", 0)),
                                "y": int(pos.get("y", 0)),
                                "width": w,
                                "height": h,
                            }
        except Exception:
            pass
        return None

    def _capture_kwin(
        self,
        kind: str,
        monitor: int,
        region: Optional[dict[str, Any]],
        window_id: Optional[Any],
    ) -> CaptureResult:
        """Capture via kwin-mcp screenshot."""
        from core.kwin_mcp_client import get_client

        client = get_client()
        client.ensure_started()
        capture_region: Optional[dict[str, Any]] = None

        if kind == "region" and region:
            capture_region = region
        elif kind == "monitor":
            capture_region = self._get_monitor_region(monitor)
        elif kind in ("window", "active_window"):
            windows = client.get_kwin_windows()
            target_win = None
            if kind == "active_window" or window_id is None:
                target_win = next((w for w in windows if w.get("active")), None)
            else:
                wid_str = str(window_id).lower()
                target_win = next(
                    (
                        w for w in windows
                        if str(w.get("id", "")).lower() == wid_str
                        or wid_str in str(w.get("app", "")).lower()
                        or wid_str in str(w.get("caption", "")).lower()
                    ),
                    None,
                )
            if target_win and target_win.get("width", 0) > 0 and target_win.get("height", 0) > 0:
                capture_region = {
                    "x": int(target_win.get("x", 0)),
                    "y": int(target_win.get("y", 0)),
                    "width": int(target_win.get("width", 0)),
                    "height": int(target_win.get("height", 0)),
                }

        result = client.screenshot(region=capture_region)
        return self._wrap_kwin_result(result, kind, monitor, capture_region or region, window_id)

    def _wrap_kwin_result(
        self,
        result: Any,
        kind: str,
        monitor: int,
        region: Optional[dict[str, Any]],
        window_id: Optional[int],
    ) -> CaptureResult:
        """Convert a kwin-mcp screen_capture result into a CaptureResult."""
        if not isinstance(result, dict):
            return CaptureResult(ok=False, error="unexpected kwin-mcp result type")

        # kwin-mcp returns {"content": [...], "structuredContent": {...}}
        content = result.get("content", [])
        image_bytes = b""
        mime_type = "image/png"
        path = None
        uri = None

        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type", "")
                if btype == "image":
                    # Image data is base64-encoded in the 'data' field.
                    b64_data = block.get("data", "")
                    if b64_data:
                        import base64
                        try:
                            image_bytes = base64.b64decode(b64_data)
                            mime_type = block.get("mime_type", "image/png")
                            break
                        except Exception:
                            pass
                elif btype == "text":
                    text = block.get("text", "")
                    # kwin-mcp may return a file path or URI in text
                    if text.startswith("/") or text.startswith("kwin://"):
                        path = text
                        uri = text if text.startswith("kwin://") else None

        sc = result.get("structuredContent") or result.get("structured_content") or {}
        if isinstance(sc, dict):
            path = path or sc.get("path") or sc.get("file_path") or ""
            uri = uri or sc.get("uri") or sc.get("frame_uri") or ""
            image_b64 = sc.get("data") or sc.get("image_data") or ""
            if image_b64:
                import base64
                image_bytes = base64.b64decode(image_b64)

        # If we got a path/URI, read the file.
        if path and not image_bytes:
            try:
                image_bytes = Path(path).read_bytes()
            except Exception:
                pass

        # If we still have no bytes, the capture may have failed silently.
        if not image_bytes:
            return CaptureResult(ok=False, error="kwin-mcp returned no image data")

        return self._finalize_capture(image_bytes, mime_type, kind, monitor,
                                      region, window_id, path, uri)

    def _capture_mss(
        self,
        kind: str,
        monitor: int,
        region: Optional[dict[str, Any]],
    ) -> CaptureResult:
        """Capture via mss (X11 fallback)."""
        mss = installed("mss")
        if not mss:
            return CaptureResult(ok=False, error="mss not installed")
        import mss  # type: ignore[import-untyped]
        import mss.tools  # type: ignore[import-untyped]

        with mss.mss() as sct:
            monitors = sct.monitors  # [0] = all, [1..n] = real screens
            if kind == "monitor" and 1 <= monitor < len(monitors):
                target = monitors[monitor]
            elif kind == "region" and region:
                target = {
                    "left": region["x"],
                    "top": region["y"],
                    "width": region["width"],
                    "height": region["height"],
                }
            else:
                target = monitors[1] if len(monitors) > 1 else monitors[0]

            shot = sct.grab(target)
            png = mss.tools.to_png(shot.rgb, shot.size)

        return self._finalize_capture(png, "image/png", kind, monitor, region, None)

    def _finalize_capture(
        self,
        image_bytes: bytes,
        mime_type: str,
        kind: str,
        monitor: int,
        region: Optional[dict[str, Any]],
        window_id: Optional[int],
        path: Optional[str] = None,
        uri: Optional[str] = None,
    ) -> CaptureResult:
        """Common finalization: hash, store, history, compress."""
        img_hash = hashlib.sha256(image_bytes).hexdigest()[:16]
        size_kb = len(image_bytes) // 1024

        result = CaptureResult(
            ok=True,
            image_bytes=image_bytes,
            mime_type=mime_type,
            monitor=monitor,
            region=region,
            size_kb=size_kb,
            hash=img_hash,
            path=path,
            uri=uri,
        )

        # Store to disk.
        try:
            fname = f"cap_{int(time.time()*1000)}_{img_hash}.png"
            fpath = SCREENSHOT_DIR / fname
            fpath.write_bytes(image_bytes)
            result.path = str(fpath)
        except Exception:
            pass

        # Append to history (capped).
        self._history.append(result)
        while len(self._history) > _MAX_SCREENSHOTS:
            self._history.pop(0)

        return result

    # ── history ──────────────────────────────────────────────────────────

    def history(self, limit: int = 50) -> list[CaptureResult]:
        """Return the most recent captures, newest first."""
        return list(reversed(self._history[-limit:]))

    def get_capture(self, index_from_recent: int = 0) -> Optional[CaptureResult]:
        """Get a capture by index from the most recent (0 = latest)."""
        if not self._history:
            return None
        idx = len(self._history) - 1 - index_from_recent
        if idx < 0:
            return None
        return self._history[idx]

    # ── OCR ─────────────────────────────────────────────────────────────

    def ocr(self, image_bytes: bytes, lang: str = "eng") -> OCRResult:
        """Run OCR on image bytes. Returns text and average confidence."""
        if not _PYTESSERACT:
            return OCRResult(
                ok=False,
                error="pytesseract not installed. Run: pip install pytesseract",
            )
        if not image_bytes:
            return OCRResult(ok=False, error="empty image")

        try:
            # Preprocess with OpenCV for better OCR results.
            arr = np.frombuffer(image_bytes, dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None:
                return OCRResult(ok=False, error="could not decode image")

            # Grayscale + threshold for cleaner text.
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

            data = pytesseract.image_to_data(
                thresh, lang=lang,
                config="--psm 6", output_type=pytesseract.Output.DICT,
            )
            confs = [c for c in data["conf"] if c > 0]
            text = " ".join(t for t in data["text"] if t.strip())
            avg_conf = sum(confs) / len(confs) if confs else 0.0

            return OCRResult(ok=True, text=text.strip(), confidence=avg_conf / 100.0)
        except Exception as e:
            return OCRResult(ok=False, error=str(e))

    # ── VLM understanding ──────────────────────────────────────────────

    def describe(
        self,
        image_bytes: bytes,
        question: str = "What do you see in this screenshot?",
        session=None,
    ) -> str:
        """
        Ask the model to describe an image.

        If `session` (a Gemini Live session) is given, the image is injected
        as a user turn and the model's next transcription is the description.
        Otherwise falls back to OCR.
        """
        if session is not None:
            try:
                import base64
                from google.genai import types
                b64 = base64.b64encode(image_bytes).decode("ascii")
                # Inject as a user turn with the image.
                # This is fire-and-forget; the model's response will come
                # through the normal receive loop.
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.run_coroutine_threadsafe(
                        session.send_client_content(
                            turns={"role": "user", "parts": [
                                {"inline_data": {"mime_type": "image/png", "data": b64}},
                                {"text": question},
                            ]},
                            turn_complete=True,
                        ),
                        loop,
                    )
                return f"(image injected for vision analysis: {question})"
            except Exception as e:
                return f"vision injection failed: {e}"

        # Fallback: OCR only.
        ocr = self.ocr(image_bytes)
        if ocr.ok and ocr.text:
            return f"OCR text: {ocr.text}"
        return "no vision session available and OCR returned nothing"

    # ── comparison ──────────────────────────────────────────────────────

    def compare(self, before: CaptureResult, after: CaptureResult) -> ComparisonResult:
        """Compare two captures. Returns whether the screen changed."""
        if not before.ok or not after.ok:
            return ComparisonResult(changed=False, similarity=0.0,
                                    error="one or both captures failed")
        if before.hash == after.hash:
            return ComparisonResult(changed=False, similarity=1.0)

        try:
            a = cv2.imdecode(
                np.frombuffer(before.image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
            b = cv2.imdecode(
                np.frombuffer(after.image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
            if a is None or b is None:
                return ComparisonResult(changed=True, similarity=0.0,
                                        error="could not decode images")

            # Resize to match if needed.
            if a.shape != b.shape:
                b = cv2.resize(b, (a.shape[1], a.shape[0]))

            gray_a = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
            gray_b = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)

            diff = cv2.absdiff(gray_a, gray_b)
            _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
            diff_pixels = int(cv2.countNonZero(thresh))
            total = thresh.size
            similarity = 1.0 - (diff_pixels / total)

            changed = diff_pixels > total * 0.01  # >1% changed

            return ComparisonResult(
                changed=changed,
                similarity=round(similarity, 4),
                diff_pixels=diff_pixels,
            )
        except Exception as e:
            return ComparisonResult(changed=True, similarity=0.0, error=str(e))

    # ── before/after verification ───────────────────────────────────────

    def capture_before(self, label: str = "") -> CaptureResult:
        """Capture a 'before' snapshot and return it. Also stored in history."""
        cap = self.capture_full()
        self._log(f"[Vision] before ({label or 'untitled'}): {cap.size_kb}KB, hash={cap.hash}")
        return cap

    def capture_after(
        self,
        before: CaptureResult,
        label: str = "",
        expect_change: bool = True,
    ) -> tuple[CaptureResult, ComparisonResult]:
        """Capture an 'after' snapshot and compare with `before`."""
        cap = self.capture_full()
        comp = self.compare(before, cap)
        self._log(
            f"[Vision] after ({label or 'untitled'}): {cap.size_kb}KB, "
            f"changed={comp.changed}, similarity={comp.similarity}"
        )
        if expect_change and not comp.changed:
            self._log(f"[Vision] ⚠️  Expected change after '{label}' but screen is unchanged.")
        return cap, comp


# ── module-level singleton ─────────────────────────────────────────────

_vision: Optional[Vision] = None
_vision_lock = __import__("threading").Lock()


def get_vision(log=None) -> Vision:
    """Return the singleton Vision instance."""
    global _vision
    with _vision_lock:
        if _vision is None:
            _vision = Vision(log=log)
    return _vision


def reset_vision() -> None:
    """Drop the singleton (mainly for tests)."""
    global _vision
    with _vision_lock:
        _vision = None
