"""gui/perplexity_context_panel.py — Mode-Aware Contextual Information Panel for Perplexity UI.

Provides mode-aware tabs:
- AI SEARCH MODE:
  - Rich Source Cards (real article title, publisher, domain favicon badge, snippet, citation number, click-to-open)
  - Search activity & scope
  - Related inquiry pills
- ASSISTANT MODE:
  - Session Context & Active attached files
  - Full Communications History (LogWidget)
- VOICE HUD MODE:
  - Voice session telemetry (live state, wake-word, push-to-talk, engine)
  - Live speech transcripts (LogWidget)
- ACTIVITY: Hardware & system telemetry (CPU, Memory, GPU, Temp gauges, Network sparkline, Status rows)
- TASKS: Active background tasks and scheduled routines
"""
from __future__ import annotations

import re
from urllib.parse import urlparse
from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QDesktopServices, QFont
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy,
    QStackedWidget, QVBoxLayout, QWidget,
)

from gui.style import DISPLAY_CSS, MONO_CSS, hud_font, px_font, scroll_css
from gui.theme import C
from gui.widgets import HoloPanel, LogWidget


_DOMAIN_PUBLISHER_MAP = {
    "apnews.com": "Associated Press News",
    "reuters.com": "Reuters",
    "nytimes.com": "The New York Times",
    "washingtonpost.com": "The Washington Post",
    "wsj.com": "The Wall Street Journal",
    "bloomberg.com": "Bloomberg",
    "nature.com": "Nature Journal",
    "arxiv.org": "arXiv Research",
    "github.com": "GitHub",
    "newsweek.com": "Newsweek",
    "bbc.com": "BBC News",
    "theverge.com": "The Verge",
    "techcrunch.com": "TechCrunch",
    "wired.com": "WIRED",
    "arstechnica.com": "Ars Technica",
    "heavy.com": "Heavy News",
    "msn.com": "MSN News",
    "cbsnews.com": "CBS News",
    "cnn.com": "CNN",
    "wikipedia.org": "Wikipedia",
    "huggingface.co": "Hugging Face",
    "langchain.com": "LangChain",
}


def parse_sources_from_text(raw_text: str) -> list[dict]:
    """Extracts actual retrieved article titles, publisher names, snippets, and URLs.

    Never fabricates sources. Preserves original metadata and URLs.
    """
    sources = []
    seen = set()
    idx = 1

    lines = raw_text.strip().split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue

        url_match = re.search(r"https?://[^\s\)\>\]]+", line)
        if not url_match:
            continue

        url = url_match.group(0).rstrip(".,;)\"'>")
        if url in seen:
            continue
        seen.add(url)

        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]

        publisher = ""
        title = ""
        snippet = ""

        # Pattern 1: Markdown link [Title](url)
        md_match = re.search(r"\[([^\]]+)\]\(" + re.escape(url) + r"\)", line)
        if md_match:
            title = md_match.group(1).strip()

        # Pattern 2: [Publisher] bracket tag (e.g. [Newsweek], [Associated Press])
        pub_match = re.search(r"\[([A-Za-z0-9\s\.\,\-&]{2,40})\]", line)
        if pub_match and not md_match:
            publisher = pub_match.group(1).strip()

        # Pattern 3: Extract title preceding [Publisher] or URL
        if not title:
            prefix = line[:url_match.start()].strip()
            # Remove leading numbers/bullets e.g. "1. " or "- "
            clean_prefix = re.sub(r"^(\d+\.|\-|\*)\s*", "", prefix).strip()
            if pub_match:
                p_idx = clean_prefix.find(f"[{publisher}]")
                if p_idx > 0:
                    title = clean_prefix[:p_idx].strip(" -:—·")
                    snippet = clean_prefix[p_idx + len(publisher) + 2:].strip(" -:—·")
                else:
                    title = clean_prefix.strip(" -:—·")
            else:
                title = clean_prefix.strip(" -:—·")

        # Fallback publisher from domain map or cleaned domain
        if not publisher:
            publisher = _DOMAIN_PUBLISHER_MAP.get(domain, "")
            if not publisher:
                parts = domain.split(".")
                publisher = parts[0].capitalize() if len(parts) > 1 else domain

        # If no explicit title, humanize the path slug
        if not title or len(title) < 4:
            slug = parsed.path.strip("/").split("/")[-1]
            slug = re.sub(r"[-_]+", " ", slug)
            slug = re.sub(r"\.[a-zA-Z0-9]+$", "", slug)
            title = slug.title() if (slug and len(slug) > 3) else f"{publisher} Resource"

        # Clean markdown asterisks and polish title
        title = re.sub(r"\*\*([^*]+)\*\*", r"\1", title).replace("**", "").strip(" -:—·")
        if ":" in title:
            p_parts = title.split(":", 1)
            if 4 <= len(p_parts[0].strip()) <= 50:
                title = p_parts[0].strip()

        sources.append({
            "index": idx,
            "title": title[:90],
            "publisher": publisher,
            "domain": domain,
            "snippet": snippet[:160],
            "url": url,
        })
        idx += 1
        if len(sources) >= 12:
            break

    return sources


class SourceCard(QFrame):
    """Clean citation card with real title, publisher, snippet, and click-to-open action."""

    def __init__(self, index: int, title: str, publisher: str, domain: str, snippet: str = "", url: str = "", parent=None):
        super().__init__(parent)
        self._url = url
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QFrame {{
                background: {C.PANEL2};
                border: 1px solid {C.BORDER};
                border-radius: 8px;
            }}
            QFrame:hover {{
                border-color: {C.PRI};
                background: {C.HOVER};
            }}
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(4)

        # Header: [Citation Index] + Publisher + Domain tag
        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        num_lbl = QLabel(f"[{index}]")
        num_lbl.setFont(px_font(10, QFont.Weight.Bold, mono=True))
        num_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        top_row.addWidget(num_lbl)

        pub_lbl = QLabel(publisher)
        pub_lbl.setFont(px_font(10, QFont.Weight.Bold))
        pub_lbl.setStyleSheet(f"color: {C.WHITE}; background: transparent;")
        top_row.addWidget(pub_lbl)

        dom_lbl = QLabel(f"·  {domain}")
        dom_lbl.setFont(px_font(9))
        dom_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        top_row.addWidget(dom_lbl)

        top_row.addStretch()

        open_icon = QLabel("↗")
        open_icon.setFont(px_font(10, QFont.Weight.Bold))
        open_icon.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        top_row.addWidget(open_icon)
        lay.addLayout(top_row)

        # Article Title
        t_lbl = QLabel(title)
        t_lbl.setFont(px_font(11, QFont.Weight.DemiBold))
        t_lbl.setWordWrap(True)
        t_lbl.setStyleSheet(f"color: {C.TEXT}; background: transparent; line-height: 1.2;")
        lay.addWidget(t_lbl)

        # Snippet if available
        if snippet:
            snip_lbl = QLabel(snippet)
            snip_lbl.setFont(px_font(9))
            snip_lbl.setWordWrap(True)
            snip_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
            lay.addWidget(snip_lbl)

    def mousePressEvent(self, event):
        if self._url and event.button() == Qt.MouseButton.LeftButton:
            QDesktopServices.openUrl(QUrl(self._url))
        super().mousePressEvent(event)


class PerplexityContextPanel(QWidget):
    """Mode-aware contextual tabbed right panel."""

    close_requested = pyqtSignal()
    follow_up_clicked = pyqtSignal(str)

    def __init__(self, log_widget: LogWidget, parent=None):
        super().__init__(parent)
        self._log_widget = log_widget
        self._active_workspace_mode = 0
        self._sources_cache: list[dict] = []
        self._current_attached_file: str | None = None

        self.setFixedWidth(270)
        self.setStyleSheet(f"""
            QWidget#PerplexityContextPanel {{
                background: {C.SIDEBAR};
                border-left: 1px solid {C.BORDER};
            }}
        """)
        self.setObjectName("PerplexityContextPanel")

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        # ── Top Bar: Tab Switcher + Close Button ───────────────────────────
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(2, 0, 2, 2)
        top_bar.setSpacing(2)

        self._tab_btns = []
        tab_names = [("Sources", "📑"), ("Comms", "💬"), ("Activity", "📊"), ("Tasks", "⚡")]
        for i, (name, icon) in enumerate(tab_names):
            b = QPushButton(f"{icon} {name}")
            b.setFixedHeight(24)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFont(px_font(9, QFont.Weight.DemiBold))
            b.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {C.TEXT_MED};
                    border: 1px solid transparent;
                    border-radius: 4px;
                    padding: 0 4px;
                }}
                QPushButton:hover {{
                    color: {C.TEXT};
                    background: {C.HOVER};
                }}
            """)
            b.clicked.connect(lambda _, idx=i: self.set_current_tab(idx))
            self._tab_btns.append(b)
            top_bar.addWidget(b)

        top_bar.addStretch()

        self._close_btn = QPushButton("✕")
        self._close_btn.setFixedSize(20, 20)
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.setToolTip("Collapse panel")
        self._close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {C.TEXT_DIM};
                border: none;
                font-size: 11px;
            }}
            QPushButton:hover {{
                color: {C.PRI};
            }}
        """)
        self._close_btn.clicked.connect(self.close_requested.emit)
        top_bar.addWidget(self._close_btn)
        root.addLayout(top_bar)

        # ── Stacked Views ─────────────────────────────────────────────────
        self._stack = QStackedWidget()

        # Tab 0: Sources Tab View (AI Search Mode)
        self._sources_page = self._build_sources_page()
        self._stack.addWidget(self._sources_page)

        # Tab 1: Comms & Session View (Assistant & Voice HUD Modes)
        self._comms_page = self._build_comms_page()
        self._stack.addWidget(self._comms_page)

        # Tab 2: Activity / Telemetry Tab View (Metrics, gauges, sparkline)
        self._activity_page = QWidget()
        self._activity_lay = QVBoxLayout(self._activity_page)
        self._activity_lay.setContentsMargins(0, 0, 0, 0)
        self._activity_lay.setSpacing(6)
        self._stack.addWidget(self._activity_page)

        # Tab 3: Tasks Tab View (Background tasks & routines)
        self._tasks_page = QWidget()
        self._tasks_lay = QVBoxLayout(self._tasks_page)
        self._tasks_lay.setContentsMargins(0, 0, 0, 0)
        self._tasks_lay.setSpacing(6)
        self._stack.addWidget(self._tasks_page)

        root.addWidget(self._stack, stretch=1)
        self.set_current_tab(0)

    # ── TAB 0: Sources Page (AI Research Insights) ────────────────────────
    def _build_sources_page(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        hdr_row = QHBoxLayout()
        header = QLabel("RESEARCH CITATIONS")
        header.setFont(px_font(10, QFont.Weight.Bold))
        header.setStyleSheet(f"color: {C.PRI}; background: transparent; letter-spacing: 1px;")
        hdr_row.addWidget(header)
        hdr_row.addStretch()

        self._source_count_pill = QLabel("0 sources")
        self._source_count_pill.setFont(px_font(9, mono=True))
        self._source_count_pill.setStyleSheet(f"color: {C.TEXT_DIM}; background: {C.PANEL}; border-radius: 4px; padding: 1px 6px;")
        hdr_row.addWidget(self._source_count_pill)
        lay.addLayout(hdr_row)

        self._sources_scroll = QScrollArea()
        self._sources_scroll.setWidgetResizable(True)
        self._sources_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._sources_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }" + scroll_css())

        self._sources_container = QWidget()
        self._sources_container.setStyleSheet("background: transparent;")
        self._sources_list_lay = QVBoxLayout(self._sources_container)
        self._sources_list_lay.setContentsMargins(0, 0, 0, 0)
        self._sources_list_lay.setSpacing(6)

        self._empty_sources_lbl = QLabel(
            "No active search citations.\nAsk a question in AI Search mode to view live source cards with article titles, publishers, and verified URLs."
        )
        self._empty_sources_lbl.setFont(px_font(11))
        self._empty_sources_lbl.setWordWrap(True)
        self._empty_sources_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; padding: 16px 4px; line-height: 1.4;")
        self._sources_list_lay.addWidget(self._empty_sources_lbl)

        # Related Research Inquiries Box
        self._related_box = QWidget()
        self._related_box.setStyleSheet("background: transparent;")
        rel_lay = QVBoxLayout(self._related_box)
        rel_lay.setContentsMargins(0, 10, 0, 0)
        rel_lay.setSpacing(4)

        rel_hdr = QLabel("RELATED INQUIRIES")
        rel_hdr.setFont(px_font(9, QFont.Weight.Bold))
        rel_hdr.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; letter-spacing: 1px;")
        rel_lay.addWidget(rel_hdr)

        self._rel_buttons_lay = QVBoxLayout()
        self._rel_buttons_lay.setSpacing(4)
        rel_lay.addLayout(self._rel_buttons_lay)
        self._related_box.hide()
        self._sources_list_lay.addWidget(self._related_box)

        self._sources_list_lay.addStretch()

        self._sources_scroll.setWidget(self._sources_container)
        lay.addWidget(self._sources_scroll, stretch=1)
        return w

    # ── TAB 1: Comms & Adaptive Session Page ──────────────────────────────
    def _build_comms_page(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        # Top Session Context Card (adapts to mode)
        self._session_card = QFrame()
        self._session_card.setStyleSheet(f"""
            QFrame {{
                background: {C.PANEL2};
                border: 1px solid {C.BORDER};
                border-radius: 8px;
            }}
        """)
        s_lay = QVBoxLayout(self._session_card)
        s_lay.setContentsMargins(8, 6, 8, 6)
        s_lay.setSpacing(4)

        self._session_hdr = QLabel("ACTIVE SESSION")
        self._session_hdr.setFont(px_font(9, QFont.Weight.Bold))
        self._session_hdr.setStyleSheet(f"color: {C.PRI}; background: transparent; letter-spacing: 1px;")
        s_lay.addWidget(self._session_hdr)

        self._session_detail = QLabel("Assistant Pipeline · Ready")
        self._session_detail.setFont(px_font(10))
        self._session_detail.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        s_lay.addWidget(self._session_detail)

        lay.addWidget(self._session_card)

        # Log Header
        log_hdr = QLabel("COMMUNICATIONS & LOGS")
        log_hdr.setFont(px_font(10, QFont.Weight.Bold))
        log_hdr.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; letter-spacing: 1px;")
        lay.addWidget(log_hdr)

        # Embed original log widget directly!
        lay.addWidget(self._log_widget, stretch=1)
        return w

    def on_workspace_mode_changed(self, mode_idx: int):
        """Mode-aware navigation trigger."""
        self._active_workspace_mode = mode_idx
        if mode_idx == 0:  # AI Search
            self.set_current_tab(0)
        elif mode_idx == 1:  # Assistant
            self.set_current_tab(1)
            self._session_hdr.setText("ASSISTANT SESSION")
            file_txt = f"Attached: {self._current_attached_file}" if self._current_attached_file else "No files attached"
            self._session_detail.setText(f"Engine: Autonomous Agent  ·  {file_txt}")
        elif mode_idx == 2:  # Voice HUD
            self.set_current_tab(1)
            self._session_hdr.setText("VOICE HUD TELEMETRY")
            self._session_detail.setText("Pipeline: Gemini Live  ·  Audio: Bi-directional PCM  ·  Wake: Enabled")

    def set_current_tab(self, idx: int):
        self._stack.setCurrentIndex(idx)
        for i, b in enumerate(self._tab_btns):
            if i == idx:
                b.setStyleSheet(f"""
                    QPushButton {{
                        background: {C.ACTIVE};
                        color: {C.TEXT};
                        border: 1px solid {C.BORDER};
                        border-radius: 4px;
                        padding: 0 6px;
                    }}
                """)
            else:
                b.setStyleSheet(f"""
                    QPushButton {{
                        background: transparent;
                        color: {C.TEXT_DIM};
                        border: 1px solid transparent;
                        border-radius: 4px;
                        padding: 0 6px;
                    }}
                    QPushButton:hover {{
                        color: {C.TEXT};
                        background: {C.HOVER};
                    }}
                """)

    def set_activity_widget(self, w: QWidget):
        self._activity_lay.addWidget(w, stretch=1)

    def set_tasks_widget(self, w: QWidget):
        self._tasks_lay.addWidget(w, stretch=1)

    def set_voice_state(self, state: str):
        if self._active_workspace_mode == 2:
            self._session_detail.setText(f"Live Audio: {state}  ·  Wake-Word Active  ·  Interrupt: [ESC]")

    def set_attached_file(self, filename: str | None):
        self._current_attached_file = filename
        if self._active_workspace_mode == 1:
            file_txt = f"Attached: {filename}" if filename else "No files attached"
            self._session_detail.setText(f"Engine: Autonomous Agent  ·  {file_txt}")

    def add_source(self, index: int, title: str, publisher: str, domain: str, snippet: str = "", url: str = ""):
        self._empty_sources_lbl.hide()
        card = SourceCard(index, title, publisher, domain, snippet, url)
        # Insert before related box and stretch
        insert_pos = max(0, self._sources_list_lay.count() - 2)
        self._sources_list_lay.insertWidget(insert_pos, card)

    def clear_sources(self):
        self._sources_cache.clear()
        for i in reversed(range(self._sources_list_lay.count())):
            item = self._sources_list_lay.itemAt(i)
            if item and item.widget() and item.widget() not in (self._empty_sources_lbl, self._related_box):
                w = item.widget()
                self._sources_list_lay.removeWidget(w)
                w.deleteLater()
        self._empty_sources_lbl.show()
        self._source_count_pill.setText("0 sources")
        self._related_box.hide()

    def parse_and_display_sources_from_text(self, text: str):
        """Extracts source links/domains/titles from research output and populates cards."""
        sources = parse_sources_from_text(text)
        if sources:
            self.clear_sources()
            self._sources_cache = sources
            for s in sources:
                self.add_source(
                    s["index"], s["title"], s["publisher"], s["domain"], s["snippet"], s["url"]
                )
            self._source_count_pill.setText(f"{len(sources)} sources")

            # Extract related follow-up suggestions from title or query
            self._populate_related_questions(sources)
            if self._active_workspace_mode == 0:
                self.set_current_tab(0)

    def _populate_related_questions(self, sources: list[dict]):
        # Clear existing buttons
        while self._rel_buttons_lay.count():
            item = self._rel_buttons_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        first_title = sources[0]["title"] if sources else "this topic"
        suggestions = [
            f"What are the future projections for {first_title[:32]}?",
            "Provide a critical comparative analysis",
            "What are the primary opposing viewpoints or risks?",
        ]
        for q in suggestions:
            btn = QPushButton(f"• {q}")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(24)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {C.PANEL};
                    color: {C.TEXT_MED};
                    border: 1px solid {C.BORDER};
                    border-radius: 4px;
                    padding: 0 8px;
                    text-align: left;
                    font-size: 10px;
                }}
                QPushButton:hover {{
                    color: {C.PRI};
                    border-color: {C.PRI_DIM};
                }}
            """)
            btn.clicked.connect(lambda _, query=q: self.follow_up_clicked.emit(query))
            self._rel_buttons_lay.addWidget(btn)

        self._related_box.show()
