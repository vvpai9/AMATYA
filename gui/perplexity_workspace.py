"""gui/perplexity_workspace.py — Central Workspace for Perplexity AI Experience.

Houses 3 distinct experiences:
- MODE 0: AI SEARCH MODE (Structured research answers, source carousels, inline citations, follow-up actions)
- MODE 1: PERSONAL ASSISTANT MODE (Clean content-driven bubbles, rich Markdown, code blocks, copy & regenerate)
- MODE 2: AMATYA VOICE HUD MODE (Immersive 3D animated reactor orb, holographic face, full unencumbered canvas)

Includes top minimal navigation with mode switcher pills, engine indicator, and context panel toggle.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse
from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QClipboard, QColor, QDesktopServices, QFont, QResizeEvent
from PyQt6.QtWidgets import (
    QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QStackedWidget, QTextBrowser, QVBoxLayout, QWidget,
)

from gui.perplexity_context_panel import parse_sources_from_text
from gui.style import DISPLAY_CSS, MONO_CSS, hud_font, px_font, scroll_css
from gui.theme import C


class SuggestionPill(QPushButton):
    """Clickable suggestion chip on the welcome screen."""

    def __init__(self, icon: str, text: str, parent=None):
        super().__init__(parent)
        self.setText(f"{icon}  {text}".replace("&", "&&"))
        self.setToolTip(text)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(38)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(f"""
            QPushButton {{
                background: {C.PANEL};
                color: {C.TEXT};
                border: 1px solid {C.BORDER};
                border-radius: 8px;
                padding: 0 14px;
                font-family: {DISPLAY_CSS};
                font-size: 12px;
                font-weight: 500;
                text-align: left;
            }}
            QPushButton:hover {{
                background: {C.HOVER};
                border-color: {C.BORDER_B};
                color: {C.WHITE};
            }}
        """)


class MiniSourceCard(QFrame):
    """Compact source card displayed above research answers."""

    def __init__(self, index: int, title: str, publisher: str, domain: str, url: str, parent=None):
        super().__init__(parent)
        self._url = url
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedWidth(190)
        self.setFixedHeight(68)
        self.setStyleSheet(f"""
            QFrame {{
                background: {C.PANEL2};
                border: 1px solid {C.BORDER};
                border-radius: 6px;
            }}
            QFrame:hover {{
                border-color: {C.PRI};
                background: {C.HOVER};
            }}
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(3)

        top_row = QHBoxLayout()
        top_row.setSpacing(4)

        num = QLabel(f"[{index}]")
        num.setFont(px_font(9, QFont.Weight.Bold, mono=True))
        num.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        top_row.addWidget(num)

        pub = QLabel(publisher[:18])
        pub.setFont(px_font(9, QFont.Weight.Bold))
        pub.setStyleSheet(f"color: {C.WHITE}; background: transparent;")
        top_row.addWidget(pub)
        top_row.addStretch()

        dom = QLabel(domain[:14])
        dom.setFont(px_font(8))
        dom.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        top_row.addWidget(dom)
        lay.addLayout(top_row)

        t_lbl = QLabel(title)
        t_lbl.setFont(px_font(10, QFont.Weight.DemiBold))
        t_lbl.setWordWrap(True)
        t_lbl.setStyleSheet(f"color: {C.TEXT}; background: transparent;")
        lay.addWidget(t_lbl)

    def mousePressEvent(self, event):
        if self._url and event.button() == Qt.MouseButton.LeftButton:
            QDesktopServices.openUrl(QUrl(self._url))
        super().mousePressEvent(event)


class ChatMessageCard(QFrame):
    """User or Assistant message bubble with content-driven height and zero excess blank space."""

    regenerate_clicked = pyqtSignal()

    def __init__(self, sender: str, text: str, parent=None):
        super().__init__(parent)
        self._raw_text = text
        self._is_user = sender.upper() == "YOU"

        bg_col = C.PANEL2 if self._is_user else C.PANEL
        border_col = C.BORDER_A if self._is_user else C.BORDER

        self.setStyleSheet(f"""
            QFrame#ChatMessageCard {{
                background: {bg_col};
                border: 1px solid {border_col};
                border-radius: 10px;
            }}
        """)
        self.setObjectName("ChatMessageCard")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(6)

        # Header row: Sender badge + timestamp + actions
        hdr = QHBoxLayout()
        hdr.setSpacing(6)

        badge = QLabel("👤 YOU" if self._is_user else "⚡ AMATYA")
        badge.setFont(px_font(10, QFont.Weight.Bold))
        badge.setStyleSheet(f"color: {C.PRI if self._is_user else C.GREEN}; background: transparent; letter-spacing: 1px;")
        hdr.addWidget(badge)
        hdr.addStretch()

        if not self._is_user:
            regen_btn = QPushButton("↻ Retry")
            regen_btn.setFixedSize(50, 20)
            regen_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            regen_btn.setFont(px_font(9))
            regen_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER};
                    border-radius: 4px;
                }}
                QPushButton:hover {{
                    color: {C.PRI};
                    border-color: {C.PRI};
                }}
            """)
            regen_btn.clicked.connect(self.regenerate_clicked.emit)
            hdr.addWidget(regen_btn)

        copy_btn = QPushButton("Copy")
        copy_btn.setFixedSize(46, 20)
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.setFont(px_font(9, QFont.Weight.DemiBold))
        copy_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {C.TEXT_DIM};
                border: 1px solid {C.BORDER};
                border-radius: 4px;
            }}
            QPushButton:hover {{
                color: {C.PRI};
                border-color: {C.PRI};
            }}
        """)
        copy_btn.clicked.connect(self._copy_text)
        hdr.addWidget(copy_btn)
        lay.addLayout(hdr)

        # Message body: Markdown rendered text browser
        self._body = QTextBrowser()
        self._body.setOpenExternalLinks(True)
        self._body.setFont(px_font(13))
        self._body.setFrameShape(QFrame.Shape.NoFrame)
        self._body.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._body.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._body.setStyleSheet(f"""
            QTextBrowser {{
                background: transparent;
                color: {C.TEXT};
                border: none;
                padding: 0px;
                selection-background-color: {C.PRI_GHO};
            }}
        """)

        # Render Markdown
        if any(sym in text for sym in ("# ", "## ", "### ", "**", "```", "- ", "* ", "1. ", "|")):
            try:
                self._body.setMarkdown(text)
            except Exception:
                self._body.setPlainText(text)
        else:
            self._body.setPlainText(text)

        # Dynamic content height calculation
        self._body.document().documentLayout().documentSizeChanged.connect(self._on_doc_size_changed)
        lay.addWidget(self._body)

    def _on_doc_size_changed(self, size):
        h = int(size.height())
        self._body.setFixedHeight(max(24, h + 8))
        self.adjustSize()

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        w = max(100, self.width() - 32)
        self._body.document().setTextWidth(w)
        h = int(self._body.document().size().height())
        self._body.setFixedHeight(max(24, h + 8))

    def _copy_text(self):
        cb = QApplication.clipboard()
        if cb:
            cb.setText(self._raw_text)


class ResearchAnswerCard(QFrame):
    """Premium Perplexity-inspired research answer with source carousel, inline citations, and follow-ups."""

    follow_up_selected = pyqtSignal(str)
    regenerate_clicked = pyqtSignal()

    def __init__(self, raw_text: str, parent=None):
        super().__init__(parent)
        self._raw_text = raw_text

        self.setStyleSheet(f"""
            QFrame#ResearchAnswerCard {{
                background: {C.PANEL};
                border: 1px solid {C.BORDER};
                border-radius: 12px;
            }}
        """)
        self.setObjectName("ResearchAnswerCard")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(10)

        # ── 1. Top Row: Header + Copy ─────────────────────────────────────
        top_hdr = QHBoxLayout()
        badge = QLabel("⚡ AMATYA RESEARCH ENGINE")
        badge.setFont(px_font(10, QFont.Weight.Bold))
        badge.setStyleSheet(f"color: {C.GREEN}; background: transparent; letter-spacing: 1px;")
        top_hdr.addWidget(badge)
        top_hdr.addStretch()

        regen_btn = QPushButton("↻ Retry")
        regen_btn.setFixedSize(52, 20)
        regen_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        regen_btn.setFont(px_font(9))
        regen_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {C.TEXT_DIM};
                border: 1px solid {C.BORDER};
                border-radius: 4px;
            }}
            QPushButton:hover {{
                color: {C.PRI};
                border-color: {C.PRI};
            }}
        """)
        regen_btn.clicked.connect(self.regenerate_clicked.emit)
        top_hdr.addWidget(regen_btn)

        copy_btn = QPushButton("Copy")
        copy_btn.setFixedSize(46, 20)
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.setFont(px_font(9, QFont.Weight.DemiBold))
        copy_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {C.TEXT_DIM};
                border: 1px solid {C.BORDER};
                border-radius: 4px;
            }}
            QPushButton:hover {{
                color: {C.PRI};
                border-color: {C.PRI};
            }}
        """)
        copy_btn.clicked.connect(self._copy_text)
        top_hdr.addWidget(copy_btn)
        lay.addLayout(top_hdr)

        # ── 2. Source Cards Carousel / Shelf ──────────────────────────────
        sources = parse_sources_from_text(raw_text)
        if sources:
            src_lbl = QLabel(f"SOURCES ({len(sources)})")
            src_lbl.setFont(px_font(9, QFont.Weight.Bold))
            src_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; letter-spacing: 0.8px;")
            lay.addWidget(src_lbl)

            shelf_scroll = QScrollArea()
            shelf_scroll.setFixedHeight(76)
            shelf_scroll.setWidgetResizable(True)
            shelf_scroll.setFrameShape(QFrame.Shape.NoFrame)
            shelf_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            shelf_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            shelf_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }" + scroll_css())

            shelf_widget = QWidget()
            shelf_widget.setStyleSheet("background: transparent;")
            shelf_lay = QHBoxLayout(shelf_widget)
            shelf_lay.setContentsMargins(0, 0, 0, 0)
            shelf_lay.setSpacing(8)

            for s in sources[:8]:
                card = MiniSourceCard(s["index"], s["title"], s["publisher"], s["domain"], s["url"])
                shelf_lay.addWidget(card)
            shelf_lay.addStretch()

            shelf_scroll.setWidget(shelf_widget)
            lay.addWidget(shelf_scroll)

        # ── 3. Structured Answer Body with Inline [1], [2] Citations ───────
        formatted_text = self._inline_citations(raw_text, sources)
        self._body = QTextBrowser()
        self._body.setOpenExternalLinks(True)
        self._body.setFont(px_font(13))
        self._body.setFrameShape(QFrame.Shape.NoFrame)
        self._body.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._body.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._body.setStyleSheet(f"""
            QTextBrowser {{
                background: transparent;
                color: {C.TEXT};
                border: none;
                padding: 0px;
                selection-background-color: {C.PRI_GHO};
            }}
            a {{
                color: {C.PRI};
                text-decoration: none;
                font-weight: bold;
            }}
            a:hover {{
                text-decoration: underline;
            }}
        """)
        try:
            self._body.setMarkdown(formatted_text)
        except Exception:
            self._body.setPlainText(formatted_text)

        self._body.document().documentLayout().documentSizeChanged.connect(self._on_doc_size_changed)
        lay.addWidget(self._body)

        # ── 4. Related Questions & Follow-ups ─────────────────────────────
        rel_box = QWidget()
        rel_box.setStyleSheet("background: transparent;")
        rel_lay = QVBoxLayout(rel_box)
        rel_lay.setContentsMargins(0, 8, 0, 0)
        rel_lay.setSpacing(6)

        rel_hdr = QLabel("RELATED QUESTIONS")
        rel_hdr.setFont(px_font(9, QFont.Weight.Bold))
        rel_hdr.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; letter-spacing: 0.8px;")
        rel_lay.addWidget(rel_hdr)

        rel_flow = QHBoxLayout()
        rel_flow.setSpacing(6)
        first_title = sources[0]["title"] if sources else "this subject"
        related_prompts = [
            f"Key factors behind {first_title[:24]}?",
            "Compare with historical precedents",
            "What are the next strategic steps?",
        ]
        for q in related_prompts:
            b = QPushButton(f"• {q}")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFixedHeight(26)
            b.setStyleSheet(f"""
                QPushButton {{
                    background: {C.PANEL2};
                    color: {C.TEXT_MED};
                    border: 1px solid {C.BORDER};
                    border-radius: 6px;
                    padding: 0 10px;
                    font-size: 11px;
                }}
                QPushButton:hover {{
                    color: {C.PRI};
                    border-color: {C.PRI_DIM};
                }}
            """)
            b.clicked.connect(lambda _, prompt=q: self.follow_up_selected.emit(prompt))
            rel_flow.addWidget(b)
        rel_flow.addStretch()
        rel_lay.addLayout(rel_flow)
        lay.addWidget(rel_box)

    def _inline_citations(self, text: str, sources: list[dict]) -> str:
        """Converts raw URLs in narrative text to sleek inline citation links [[1]](url)."""
        res = text
        for s in sources:
            url = s["url"]
            idx = s["index"]
            # Replace raw URL with bold markdown citation link
            res = res.replace(url, f"**[[{idx}]]({url})**")
        return res

    def _on_doc_size_changed(self, size):
        h = int(size.height())
        self._body.setFixedHeight(max(30, h + 8))
        self.adjustSize()

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        w = max(100, self.width() - 36)
        self._body.document().setTextWidth(w)
        h = int(self._body.document().size().height())
        self._body.setFixedHeight(max(30, h + 8))

    def _copy_text(self):
        cb = QApplication.clipboard()
        if cb:
            cb.setText(self._raw_text)


class PerplexityWorkspace(QWidget):
    """Central container managing the 3 main user experiences."""

    prompt_selected        = pyqtSignal(str)   # when a suggestion or related inquiry is clicked
    mode_changed           = pyqtSignal(int)   # 0: Search, 1: Assistant, 2: Voice HUD
    engine_clicked         = pyqtSignal()
    context_panel_toggled  = pyqtSignal()
    regenerate_requested   = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active_mode = 0
        self._last_user_query = ""

        self.setStyleSheet(f"background: {C.BG};")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Top Minimal Navigation Bar (Hidden as MainWindow header owns unified pills) ────
        self._top_nav = self._build_top_nav()
        self._top_nav.hide()

        # ── Main Stacked View (3 Modes) ───────────────────────────────────
        self._stack = QStackedWidget()

        # Mode 0: AI Search View
        self._search_view = self._build_search_view()
        self._stack.addWidget(self._search_view)

        # Mode 1: Personal Assistant View
        self._chat_view = self._build_chat_view()
        self._stack.addWidget(self._chat_view)

        # Mode 2: Voice HUD View Container (filled via set_hud_widget)
        self._hud_container = QWidget()
        self._hud_lay = QVBoxLayout(self._hud_container)
        self._hud_lay.setContentsMargins(0, 0, 0, 0)
        self._hud_lay.setSpacing(0)
        self._stack.addWidget(self._hud_container)

        root.addWidget(self._stack, stretch=1)
        self.set_mode(0)

    def _build_top_nav(self) -> QWidget:
        nav = QWidget()
        nav.setFixedHeight(46)
        nav.setStyleSheet(f"""
            QWidget {{
                background: {C.BG};
                border-bottom: 1px solid {C.BORDER};
            }}
        """)
        lay = QHBoxLayout(nav)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(10)

        # Mode selector pills in top header
        self._mode_pills = []
        pills_data = [("🌐 AI Search", 0), ("💬 Assistant", 1), ("⚛ Voice HUD", 2)]
        for label, idx in pills_data:
            b = QPushButton(label)
            b.setFixedHeight(28)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFont(px_font(11, QFont.Weight.DemiBold))
            b.clicked.connect(lambda _, i=idx: self.set_mode(i))
            self._mode_pills.append(b)
            lay.addWidget(b)

        lay.addStretch()

        # Engine Status Pill (clickable to open providers)
        self._engine_btn = QPushButton("● GEMINI LIVE")
        self._engine_btn.setFixedHeight(26)
        self._engine_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._engine_btn.setFont(px_font(10, QFont.Weight.Bold, mono=True))
        self._engine_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.PANEL2};
                color: {C.GREEN};
                border: 1px solid {C.BORDER_A};
                border-radius: 13px;
                padding: 0 10px;
            }}
            QPushButton:hover {{
                border-color: {C.GREEN};
            }}
        """)
        self._engine_btn.clicked.connect(self.engine_clicked.emit)
        lay.addWidget(self._engine_btn)

        # Context Panel Toggle Pill
        self._context_btn = QPushButton("◨ Context Panel")
        self._context_btn.setFixedHeight(26)
        self._context_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._context_btn.setFont(px_font(11, QFont.Weight.DemiBold))
        self._context_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.PANEL};
                color: {C.TEXT_MED};
                border: 1px solid {C.BORDER};
                border-radius: 6px;
                padding: 0 10px;
            }}
            QPushButton:hover {{
                color: {C.PRI};
                border-color: {C.PRI_DIM};
            }}
        """)
        self._context_btn.clicked.connect(self.context_panel_toggled.emit)
        lay.addWidget(self._context_btn)

        return nav

    # ── MODE 0: AI Search View (Perplexity) ────────────────────────────────
    def _build_search_view(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 12, 16, 4)
        lay.setSpacing(10)

        self._search_scroll = QScrollArea()
        self._search_scroll.setWidgetResizable(True)
        self._search_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._search_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }" + scroll_css())

        self._search_content = QWidget()
        self._search_content.setStyleSheet("background: transparent;")
        self._search_lay = QVBoxLayout(self._search_content)
        self._search_lay.setContentsMargins(0, 0, 0, 0)
        self._search_lay.setSpacing(12)

        # Hero Welcome Section (Claude & Perplexity style)
        self._search_hero = QWidget()
        self._search_hero.setStyleSheet("background: transparent;")
        hero_lay = QVBoxLayout(self._search_hero)
        hero_lay.setContentsMargins(16, 28, 16, 16)
        hero_lay.setSpacing(12)
        hero_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        h_title = QLabel("Good to see you. How can I help?")
        h_title.setFont(px_font(24, QFont.Weight.Bold))
        h_title.setStyleSheet(f"color: {C.WHITE}; background: transparent;")
        h_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h_title.setWordWrap(True)
        hero_lay.addWidget(h_title)

        h_sub = QLabel("Search the web, solve complex academic assignments, or analyze code with real citations.")
        h_sub.setFont(px_font(13))
        h_sub.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        h_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h_sub.setWordWrap(True)
        hero_lay.addWidget(h_sub)

        # Suggestion Pills Grid (Centered, Max 780px wide)
        self._search_grid_w = QWidget()
        self._search_grid_w.setMaximumWidth(780)
        self._search_grid_w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._search_grid_w.setStyleSheet("background: transparent;")
        self._search_grid = QGridLayout(self._search_grid_w)
        self._search_grid.setContentsMargins(0, 10, 0, 10)
        self._search_grid.setSpacing(10)

        suggestions = [
            ("🌐", "Explain quantum computing from first principles"),
            ("🛡", "Audit system security score & vulnerabilities"),
            ("📈", "Generate quantitative trading signals for NVDA"),
            ("📑", "Solve cloud security question bank unit 1 to 3 PDF"),
            ("⚡", "Compare AI Agent frameworks: LangGraph vs Autogen vs AGY"),
            ("📰", "What are the latest AI and tech breakthroughs today?"),
        ]
        self._search_pills = []
        for idx, (icon, text) in enumerate(suggestions):
            pill = SuggestionPill(icon, text)
            pill.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            pill.clicked.connect(lambda _, t=text: self.prompt_selected.emit(t))
            self._search_pills.append(pill)
            self._search_grid.addWidget(pill, idx // 2, idx % 2)

        hero_lay.addWidget(self._search_grid_w, alignment=Qt.AlignmentFlag.AlignCenter)
        self._search_lay.addWidget(self._search_hero)
        self._search_lay.addStretch()

        self._search_scroll.setWidget(self._search_content)
        lay.addWidget(self._search_scroll, stretch=1)
        return w

    # ── MODE 1: Personal Assistant View ───────────────────────────────────
    def _build_chat_view(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 12, 16, 4)
        lay.setSpacing(10)

        self._chat_scroll = QScrollArea()
        self._chat_scroll.setWidgetResizable(True)
        self._chat_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._chat_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }" + scroll_css())

        self._chat_content = QWidget()
        self._chat_content.setStyleSheet("background: transparent;")
        self._chat_lay = QVBoxLayout(self._chat_content)
        self._chat_lay.setContentsMargins(0, 0, 0, 0)
        self._chat_lay.setSpacing(10)

        # Chat Hero Welcome (Claude & Perplexity style)
        self._chat_hero = QWidget()
        self._chat_hero.setStyleSheet("background: transparent;")
        c_hero_lay = QVBoxLayout(self._chat_hero)
        c_hero_lay.setContentsMargins(16, 28, 16, 16)
        c_hero_lay.setSpacing(12)
        c_hero_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        c_title = QLabel("AMATYA Personal Assistant")
        c_title.setFont(px_font(24, QFont.Weight.Bold))
        c_title.setStyleSheet(f"color: {C.WHITE}; background: transparent;")
        c_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        c_title.setWordWrap(True)
        c_hero_lay.addWidget(c_title)

        c_sub = QLabel("Autonomous coding agent, document studio, system diagnostics, and communication hub.")
        c_sub.setFont(px_font(13))
        c_sub.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        c_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        c_sub.setWordWrap(True)
        c_hero_lay.addWidget(c_sub)

        self._chat_grid_w = QWidget()
        self._chat_grid_w.setMaximumWidth(780)
        self._chat_grid_w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._chat_grid_w.setStyleSheet("background: transparent;")
        self._chat_grid = QGridLayout(self._chat_grid_w)
        self._chat_grid.setContentsMargins(0, 10, 0, 10)
        self._chat_grid.setSpacing(10)

        chat_suggestions = [
            ("💻", "Inspect this repository and clean temp caches"),
            ("📄", "Generate a detailed cover letter and PDF on desktop"),
            ("💬", "WhatsApp Mummy saying I will be home in 10 minutes"),
            ("🧩", "List installed plugins and system capabilities"),
        ]
        self._chat_pills = []
        for idx, (icon, text) in enumerate(chat_suggestions):
            pill = SuggestionPill(icon, text)
            pill.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            pill.clicked.connect(lambda _, t=text: self.prompt_selected.emit(t))
            self._chat_pills.append(pill)
            self._chat_grid.addWidget(pill, idx // 2, idx % 2)

        c_hero_lay.addWidget(self._chat_grid_w, alignment=Qt.AlignmentFlag.AlignCenter)
        self._chat_lay.addWidget(self._chat_hero)
        self._chat_lay.addStretch()

        self._chat_scroll.setWidget(self._chat_content)
        lay.addWidget(self._chat_scroll, stretch=1)
        return w

    def set_hud_widget(self, w: QWidget):
        """Embeds the existing HUD canvas & stack into Mode 2."""
        self._hud_lay.addWidget(w)

    def set_mode(self, idx: int):
        if getattr(self, "_mode_updating", False):
            return
        if hasattr(self, "_active_mode") and self._active_mode == idx and getattr(self, "_mode_initialized", False):
            return
        self._mode_updating = True
        try:
            self._active_mode = idx
            self._mode_initialized = True
            self._stack.setCurrentIndex(idx)
            for i, pill in enumerate(self._mode_pills):
                if i == idx:
                    pill.setStyleSheet(f"""
                        QPushButton {{
                            background: {C.PANEL2};
                            color: {C.PRI};
                            border: 1px solid {C.PRI_DIM};
                            border-radius: 6px;
                            padding: 0 12px;
                        }}
                    """)
                else:
                    pill.setStyleSheet(f"""
                        QPushButton {{
                            background: transparent;
                            color: {C.TEXT_MED};
                            border: 1px solid transparent;
                            border-radius: 6px;
                            padding: 0 12px;
                        }}
                        QPushButton:hover {{
                            background: {C.PANEL};
                            color: {C.TEXT};
                        }}
                    """)
            self.mode_changed.emit(idx)
        finally:
            self._mode_updating = False

    def get_mode(self) -> int:
        return self._active_mode

    def set_engine_label(self, label: str):
        self._engine_btn.setText(f"● {label.upper()}")

    def set_state(self, state: str):
        pass

    def add_user_message(self, text: str):
        self._last_user_query = text
        self._search_hero.hide()
        self._chat_hero.hide()

        card = ChatMessageCard("YOU", text)
        target_lay = self._search_lay if self._active_mode == 0 else self._chat_lay
        target_lay.insertWidget(target_lay.count() - 1, card)
        self._scroll_to_bottom()

    def add_assistant_message(self, text: str, is_research: bool = False):
        self._search_hero.hide()
        self._chat_hero.hide()

        # Check if research answer
        has_urls = "http://" in text or "https://" in text
        if (self._active_mode == 0 or is_research) and has_urls:
            card = ResearchAnswerCard(text)
            card.follow_up_selected.connect(self.prompt_selected.emit)
            card.regenerate_clicked.connect(self.regenerate_requested.emit)
        else:
            card = ChatMessageCard("AMATYA", text)
            card.regenerate_clicked.connect(self.regenerate_requested.emit)

        target_lay = self._search_lay if self._active_mode == 0 else self._chat_lay
        target_lay.insertWidget(target_lay.count() - 1, card)
        self._scroll_to_bottom()

    def clear_conversation(self):
        for lay, hero in ((self._search_lay, self._search_hero), (self._chat_lay, self._chat_hero)):
            for i in reversed(range(lay.count())):
                item = lay.itemAt(i)
                if item and item.widget() and item.widget() != hero:
                    w = item.widget()
                    lay.removeWidget(w)
                    w.deleteLater()
            hero.show()

    def _scroll_to_bottom(self):
        scroll = self._search_scroll if self._active_mode == 0 else self._chat_scroll
        QApplication.processEvents()
        vs = scroll.verticalScrollBar()
        if vs:
            vs.setValue(vs.maximum())

    def _reflow_grids(self):
        w = self.width()
        cols = 1 if w < 780 else 2
        if getattr(self, "_current_grid_cols", None) == cols:
            return
        self._current_grid_cols = cols

        # Reflow search pills
        if hasattr(self, "_search_pills") and hasattr(self, "_search_grid"):
            for pill in self._search_pills:
                self._search_grid.removeWidget(pill)
            for idx, pill in enumerate(self._search_pills):
                r = idx if cols == 1 else idx // cols
                c = 0 if cols == 1 else idx % cols
                self._search_grid.addWidget(pill, r, c)

        # Reflow chat pills
        if hasattr(self, "_chat_pills") and hasattr(self, "_chat_grid"):
            for pill in self._chat_pills:
                self._chat_grid.removeWidget(pill)
            for idx, pill in enumerate(self._chat_pills):
                r = idx if cols == 1 else idx // cols
                c = 0 if cols == 1 else idx % cols
                self._chat_grid.addWidget(pill, r, c)

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self._reflow_grids()

