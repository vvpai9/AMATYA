"""gui/theme.py — Palette, typography and the configuration values every part of the HUD reads.

Split out of ui.py in Mark LVII; behaviour unchanged."""
from __future__ import annotations

import json
import math
import os
import platform
import random
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil

if platform.system() == "Windows":
    _WIN_HIDE: dict = {"creationflags": subprocess.CREATE_NO_WINDOW}
else:
    _WIN_HIDE: dict = {}

# Qt's video backend prints the ffmpeg stream banner — codec, bitrate, the
# whole signed googlevideo URL — to the console for every stream it opens. That
# is two screenfuls per video, it looks like an error to anyone reading the log,
# and it puts a URL carrying the viewer's IP address into a terminal people
# paste into bug reports. Silenced here, before Qt initialises its logging.
# An explicit setting from the user is left alone.
os.environ.setdefault("QT_LOGGING_RULES", "qt.multimedia.*=false")

from PyQt6.QtCore import (
    QEasingCurve, QLineF, QMimeData, QObject, QParallelAnimationGroup, QPointF,
    QPoint, QPropertyAnimation, QRect, QRectF, QSize, QSizeF, Qt, QTimer,
    QUrl, pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush, QColor, QConicalGradient, QDragEnterEvent, QDropEvent, QFont,
    QFontDatabase, QKeySequence, QLinearGradient, QPainter, QPainterPath,
    QPen, QPixmap, QRadialGradient, QShortcut,
)
# Video playback for the HUD. Part of PyQt6, so it costs no new dependency —
# but the multimedia plugins are a separate piece of the Qt install and can be
# absent on a stripped-down system, so a failure here disables one feature
# rather than stopping JARVIS from starting.
try:
    from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PyQt6.QtMultimediaWidgets import QGraphicsVideoItem
    HAVE_VIDEO = True
except Exception as _e:            # noqa: BLE001 - reported, never fatal
    QAudioOutput = QMediaPlayer = QGraphicsVideoItem = None
    HAVE_VIDEO = False
    print(f"[Video] playback unavailable ({_e}) — the HUD will not show video.")

from PyQt6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QPushButton, QScrollArea, QSizePolicy, QSplitter,
    QGraphicsScene, QGraphicsView, QGraphicsPixmapItem,
    QStackedWidget, QTextEdit, QVBoxLayout, QWidget, QProgressBar, QSlider,
)

try:
    from core.avatar import HoloAvatar
except Exception:      # pragma: no cover — HUD must never die over cosmetics
    HoloAvatar = None


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR   = _base_dir()
CONFIG_DIR = BASE_DIR / "config"
API_FILE   = CONFIG_DIR / "api_keys.json"


def _read_full_config() -> dict:
    """Read api_keys.json config dict. Returns {} on any error."""
    try:
        return json.loads(API_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


# Single source of truth for the release name — the window title, the header
# badge and the readme must never disagree again.
APP_VERSION  = "MARK LVII"
APP_PROTOCOL = APP_VERSION.split()[-1]

_DEFAULT_W, _DEFAULT_H = 1260, 800
_MIN_W,     _MIN_H     = 940, 620
_LEFT_W  = 148
_RIGHT_W = 340

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"


class C:
    # ── Premium Deep-Black Dark Theme System ──────────────────────────────────
    BG        = "#050505"      # Main app background & main voice/HUD canvas: #050505
    SIDEBAR   = "#080808"      # Sidebar and top bar: #080808
    TOPBAR    = "#080808"      # Top bar background: #080808
    CANVAS    = "#050505"      # Main voice/HUD canvas: #050505
    PANEL     = "#101010"      # Cards and panels: #101010
    PANEL2    = "#0C0C0C"      # Nested secondary panels / cards: #0C0C0C
    INPUT     = "#121212"      # Inputs and composer: #121212
    HOVER     = "#1A1A1A"      # Hover surfaces: #1A1A1A
    ACTIVE    = "#202020"      # Active / selected surfaces: #202020
    BORDER    = "#303030"      # Standard visible borders: #303030
    BORDER_B  = "#555555"      # Interactive control borders: #555555
    BORDER_A  = "#404040"      # Focus / active borders: #404040
    PRI       = "#22D3EE"      # Restrained cyan accent: #22D3EE
    PRI_DIM   = "#0E7490"      # Deep cyan: #0E7490
    PRI_GHO   = "#0F2830"      # Translucent subtle tint
    ACC       = "#F59E0B"      # Speaking state: warm amber #F59E0B
    ACC2      = "#D97706"      # Bright golden highlight
    GREEN     = "#4ADE80"      # Live/success green: #4ADE80
    GREEN_D   = "#166534"      # Emerald dim: #166534
    RED       = "#F87171"      # Muted/error red: #F87171
    MUTED_C   = "#F87171"      # Muted state: soft red: #F87171
    TEXT      = "#F5F5F5"      # Primary text: #F5F5F5
    TEXT_MED  = "#B8B8B8"      # Secondary text: #B8B8B8
    TEXT_DIM  = "#949494"      # Muted readable text: #949494
    ICON_PRI  = "#E5E5E5"      # Primary icons: #E5E5E5
    ICON_SEC  = "#A6A6A6"      # Secondary icons: #A6A6A6
    WHITE     = "#FFFFFF"      # High contrast white
    DARK      = "#050505"      # Deepest black
    BAR_BG    = "#1A1A1A"      # Progress bar trough


# Keys tied to the accent colour — dark glass surfaces and typography stay crisp & neutral
_HUE_LINKED = (
    "PRI", "PRI_DIM", "PRI_GHO",
)
_PALETTE_DEFAULTS: dict[str, str] = {k: getattr(C, k) for k in _HUE_LINKED}

DEFAULT_UI_COLOR = _PALETTE_DEFAULTS["PRI"]


def apply_ui_accent(accent_hex: str) -> bool:
    """
    Re-derives the whole teal-family palette from the chosen accent colour
    (hue shift — brightness/saturation ratios are preserved, design stays intact).
    Painted elements (HUD, waveform, metrics) pick up the new colour on the next
    frame; stylesheet-based panels pick it up when they are rebuilt.
    """
    import colorsys

    accent_hex = (accent_hex or "").strip().lower()
    if not (accent_hex.startswith("#") and len(accent_hex) == 7):
        return False
    try:
        int(accent_hex[1:], 16)
    except ValueError:
        return False

    def _hsv(h: str) -> tuple[float, float, float]:
        r = int(h[1:3], 16) / 255
        g = int(h[3:5], 16) / 255
        b = int(h[5:7], 16) / 255
        return colorsys.rgb_to_hsv(r, g, b)

    base_h            = _hsv(_PALETTE_DEFAULTS["PRI"])[0]
    acc_h, acc_s, _av = _hsv(accent_hex)
    dh   = acc_h - base_h
    grey = acc_s < 0.08   # near-grey accent → the whole theme is desaturated

    for key, hex0 in _PALETTE_DEFAULTS.items():
        h, s, v = _hsv(hex0)
        if grey:
            s *= 0.15
        r, g, b = colorsys.hsv_to_rgb((h + dh) % 1.0, s, v)
        setattr(C, key, "#{:02x}{:02x}{:02x}".format(
            int(r * 255 + 0.5), int(g * 255 + 0.5), int(b * 255 + 0.5)))
    return True


def current_palette() -> dict[str, str]:
    """A snapshot of the accent-linked colours currently on class C."""
    return {k: getattr(C, k) for k in _HUE_LINKED}


def retheme_all_widgets(old: dict[str, str], new: dict[str, str]) -> None:
    """
    LIVE full theme change. Replaces the old palette colours with the new ones
    in EVERY widget's stylesheet across the app and repaints them. This way the
    colour change applies INSTANTLY across the whole interface — panels, buttons,
    borders included — not just the painted elements. No restart needed.
    """
    mapping = {old[k].lower(): new[k].lower()
               for k in old if old[k].lower() != new.get(k, old[k]).lower()}
    if not mapping:
        return
    app = QApplication.instance()
    if app is None:
        return
    for w in app.allWidgets():
        try:
            ss = w.styleSheet()
            if ss:
                s2 = ss
                for o, n in mapping.items():
                    if o in s2:
                        s2 = s2.replace(o, n)
                if s2 != ss:
                    w.setStyleSheet(s2)
            w.update()
        except Exception:
            pass


def qcol(h: str, a: int = 255) -> QColor:
    c = QColor(h); c.setAlpha(a); return c

