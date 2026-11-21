"""gui/perplexity_nav.py — Collapsible Left Sidebar for the Perplexity-inspired UI.

Provides navigation for:
- New Thread / Search
- Mode 1: AI Search (Web research, citations, sources)
- Mode 2: Personal Assistant (Chat, coding, document studio)
- Mode 3: Voice HUD (Animated 3D Siri/Perplexity reactor core & holographic face)
- Discover / News, Library, Tasks & Routines, Memory, Plugins, Remote Control
- Settings (API Keys, Providers, Audio Devices, Customization, Auto-Start, Shortcut)
- Collapsible to compact icon-only mode with tooltips.
"""
from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPaintEvent
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy,
    QToolTip, QVBoxLayout, QWidget,
)

from gui.style import DISPLAY_CSS, hud_font, px_font, scroll_css
from gui.theme import C


class NavItemButton(QPushButton):
    """Sidebar navigation item with active indicator, icon, and optional badge."""

    def __init__(self, icon_str: str, label_str: str, parent=None, is_action: bool = False):
        super().__init__(parent)
        self._icon_str = icon_str
        self._label_str = label_str
        self._is_action = is_action
        self._active = False
        self._collapsed = False
        self._badge_text = ""

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(38)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._update_text()
        self._apply_style()

    def set_collapsed(self, collapsed: bool):
        self._collapsed = collapsed
        self._update_text()
        if collapsed:
            self.setToolTip(f"{self._icon_str}  {self._label_str}")
        else:
            self.setToolTip("")
        self._apply_style()

    def set_active(self, active: bool):
        self._active = active
        self._apply_style()

    def set_badge(self, text: str):
        self._badge_text = text
        self._update_text()

    def _update_text(self):
        if self._collapsed:
            self.setText(self._icon_str)
        else:
            badge = f"  [{self._badge_text}]" if self._badge_text else ""
            display_str = f" {self._icon_str}   {self._label_str}{badge}".replace("&", "&&")
            self.setText(display_str)

    def _apply_style(self):
        align = "center" if self._collapsed else "left"
        pad = "padding: 0;" if self._collapsed else "padding: 0 12px;"

        if self._is_action:
            # Prominent action button (like New Thread)
            self.setStyleSheet(f"""
                QPushButton {{
                    background: {C.PANEL};
                    color: {C.PRI};
                    border: 1px solid {C.BORDER};
                    border-radius: 8px;
                    font-family: {DISPLAY_CSS};
                    font-size: 13px;
                    font-weight: 600;
                    text-align: {align};
                    {pad}
                }}
                QPushButton:hover {{
                    background: {C.HOVER};
                    border-color: {C.BORDER_B};
                    color: {C.WHITE};
                }}
            """)
        elif self._active:
            # Active navigation tab
            self.setStyleSheet(f"""
                QPushButton {{
                    background: {C.ACTIVE};
                    color: {C.TEXT};
                    border: 1px solid {C.BORDER};
                    border-left: 3px solid {C.PRI};
                    border-radius: 6px;
                    font-family: {DISPLAY_CSS};
                    font-size: 13px;
                    font-weight: 600;
                    text-align: {align};
                    {pad}
                }}
                QPushButton:hover {{
                    color: {C.WHITE};
                    background: {C.HOVER};
                }}
            """)
        else:
            # Regular inactive tab
            self.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {C.TEXT_MED};
                    border: 1px solid transparent;
                    border-radius: 6px;
                    font-family: {DISPLAY_CSS};
                    font-size: 13px;
                    font-weight: 500;
                    text-align: {align};
                    {pad}
                }}
                QPushButton:hover {{
                    background: {C.HOVER};
                    color: {C.TEXT};
                    border: 1px solid {C.BORDER};
                }}
            """)


class PerplexitySidebar(QWidget):
    """Collapsible navigation sidebar."""

    mode_selected    = pyqtSignal(int)   # 0: Search, 1: Assistant, 2: Voice HUD
    new_chat_clicked = pyqtSignal()
    settings_action  = pyqtSignal(str)   # action identifier
    collapsed_changed = pyqtSignal(bool)

    EXPANDED_WIDTH  = 210
    COLLAPSED_WIDTH = 56

    def __init__(self, parent=None):
        super().__init__(parent)
        self._collapsed = False
        self._active_mode = 0

        self.setFixedWidth(self.EXPANDED_WIDTH)
        self.setStyleSheet(f"""
            QWidget#PerplexitySidebar {{
                background: {C.SIDEBAR};
                border-right: 1px solid {C.BORDER};
            }}
        """)
        self.setObjectName("PerplexitySidebar")

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 12, 8, 12)
        root.setSpacing(6)

        # ── Header: Logo + Collapse/Expand Toggle ─────────────────────────
        hdr = QHBoxLayout()
        hdr.setContentsMargins(4, 0, 4, 8)
        hdr.setSpacing(6)

        self._logo_label = QLabel("AMATYA")
        self._logo_label.setFont(hud_font(12, QFont.Weight.Bold))
        self._logo_label.setStyleSheet(f"color: {C.WHITE}; background: transparent; letter-spacing: 2px;")
        hdr.addWidget(self._logo_label, stretch=1)

        self._collapse_btn = QPushButton("◀")
        self._collapse_btn.setFixedSize(26, 26)
        self._collapse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._collapse_btn.setToolTip("Collapse sidebar")
        self._collapse_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {C.TEXT_DIM};
                border: 1px solid transparent;
                border-radius: 4px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background: {C.PANEL};
                color: {C.PRI};
                border: 1px solid {C.BORDER};
            }}
        """)
        self._collapse_btn.clicked.connect(self.toggle_collapse)
        hdr.addWidget(self._collapse_btn)
        root.addLayout(hdr)

        # ── Primary Action: New Thread / Search ───────────────────────────
        self._btn_new = NavItemButton("+", "New Thread", is_action=True)
        self._btn_new.setToolTip("Start a new search or conversation  [Cmd+K]")
        self._btn_new.clicked.connect(self.new_chat_clicked.emit)
        root.addWidget(self._btn_new)

        # ── Primary Modes Section ─────────────────────────────────────────
        self._btn_search = NavItemButton("🌐", "AI Search")
        self._btn_search.clicked.connect(lambda: self._select_mode(0))
        root.addWidget(self._btn_search)

        self._btn_chat = NavItemButton("💬", "Assistant")
        self._btn_chat.clicked.connect(lambda: self._select_mode(1))
        root.addWidget(self._btn_chat)

        self._btn_hud = NavItemButton("⚛", "Voice HUD")
        self._btn_hud.clicked.connect(lambda: self._select_mode(2))
        root.addWidget(self._btn_hud)

        # Subtle separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background: {C.BORDER}; max-height: 1px; margin: 4px 0;")
        root.addWidget(sep)

        # ── Scrollable Secondary Navigation ───────────────────────────────
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; }" + scroll_css())

        scroll_widget = QWidget()
        scroll_widget.setStyleSheet("background: transparent;")
        scroll_lay = QVBoxLayout(scroll_widget)
        scroll_lay.setContentsMargins(0, 0, 0, 0)
        scroll_lay.setSpacing(4)

        self._btn_news = NavItemButton("📰", "Discover / News")
        self._btn_news.clicked.connect(lambda: self.settings_action.emit("news"))
        scroll_lay.addWidget(self._btn_news)

        self._btn_library = NavItemButton("📚", "Library")
        self._btn_library.clicked.connect(lambda: self.settings_action.emit("library"))
        scroll_lay.addWidget(self._btn_library)

        self._btn_tasks = NavItemButton("⚡", "Tasks & Routines")
        self._btn_tasks.clicked.connect(lambda: self.settings_action.emit("tasks"))
        scroll_lay.addWidget(self._btn_tasks)

        self._btn_memory = NavItemButton("🧠", "Memory")
        self._btn_memory.clicked.connect(lambda: self.settings_action.emit("memory"))
        scroll_lay.addWidget(self._btn_memory)

        self._btn_plugins = NavItemButton("🧩", "Plugins")
        self._btn_plugins.clicked.connect(lambda: self.settings_action.emit("plugins"))
        scroll_lay.addWidget(self._btn_plugins)

        self._btn_remote = NavItemButton("📱", "Remote Control")
        self._btn_remote.clicked.connect(lambda: self.settings_action.emit("remote"))
        scroll_lay.addWidget(self._btn_remote)

        scroll_lay.addStretch()
        scroll_area.setWidget(scroll_widget)
        root.addWidget(scroll_area, stretch=1)

        # ── Bottom Settings & Utility ─────────────────────────────────────
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"background: {C.BORDER}; max-height: 1px; margin: 4px 0;")
        root.addWidget(sep2)

        self._btn_settings = NavItemButton("⚙", "Settings")
        self._btn_settings.clicked.connect(lambda: self.settings_action.emit("settings"))
        root.addWidget(self._btn_settings)

        self._mode_buttons = [self._btn_search, self._btn_chat, self._btn_hud]
        self._nav_buttons = [
            self._btn_new, self._btn_search, self._btn_chat, self._btn_hud,
            self._btn_news, self._btn_library, self._btn_tasks,
            self._btn_memory, self._btn_plugins, self._btn_remote, self._btn_settings
        ]
        self._select_mode(0)

    def _select_mode(self, idx: int):
        self._active_mode = idx
        for i, btn in enumerate(self._mode_buttons):
            btn.set_active(i == idx)
        self.mode_selected.emit(idx)

    def set_active_mode(self, idx: int):
        if 0 <= idx < len(self._mode_buttons):
            self._active_mode = idx
            for i, btn in enumerate(self._mode_buttons):
                btn.set_active(i == idx)

    def toggle_collapse(self):
        self.set_collapsed(not self._collapsed)

    def set_collapsed(self, collapsed: bool):
        self._collapsed = collapsed
        w = self.COLLAPSED_WIDTH if collapsed else self.EXPANDED_WIDTH
        self.setFixedWidth(w)
        self._logo_label.setVisible(not collapsed)
        self._collapse_btn.setText("▶" if collapsed else "◀")
        self._collapse_btn.setToolTip("Expand sidebar" if collapsed else "Collapse sidebar")
        for btn in self._nav_buttons:
            btn.set_collapsed(collapsed)
        self.collapsed_changed.emit(collapsed)
