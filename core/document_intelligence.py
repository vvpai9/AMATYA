"""
AMATYA Advanced Document Intelligence Engine (core/document_intelligence.py)
=============================================================================
Phase 13.3 Core Implementation:
  - Structural Document Parsing (Headings, Paragraphs, Tables, Figures, Footnotes, References).
  - Page-Aware Indexing & Source Location Preservation.
  - Robust Table Extraction (Structured Rows/Cols, Data Types, Missing-Value Preservation).
  - Cross-Reference Resolution (Figure, Table, Section linking).
  - Document Reasoning:
      * Structural Summarization & Key Conclusion Extraction.
      * Targeted Section Discovery.
      * Numerical Specification & Unit Extraction.
      * Multi-Document Comparative Analysis without source contamination.
  - Structured Exports (CSV, XLSX, Markdown, JSON).
"""
from __future__ import annotations

import csv
import io
import json
import re
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from core.security import redact_secrets

_LOCK = threading.RLock()


# ============================================================================
# Data Structures
# ============================================================================

@dataclass
class HeadingNode:
    level: int
    text: str
    page_number: int | None = None
    breadcrumb: str = ""
    line_offset: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DocumentTable:
    table_id: str
    page_number: int | None
    title_or_caption: str
    headers: list[str]
    rows: list[list[Any]]  # Missing values are None or "", NEVER silently coerced to 0!
    row_count: int
    col_count: int

    def to_markdown(self) -> str:
        if not self.headers and not self.rows:
            return ""
        lines: list[str] = []
        if self.title_or_caption:
            lines.append(f"**Table: {self.title_or_caption}**\n")
        headers = self.headers if self.headers else [f"Col {i+1}" for i in range(self.col_count)]
        lines.append("| " + " | ".join(str(h) for h in headers) + " |")
        lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
        for row in self.rows:
            formatted_cells = [str(cell) if cell is not None else "" for cell in row]
            # Pad if needed
            while len(formatted_cells) < len(headers):
                formatted_cells.append("")
            lines.append("| " + " | ".join(formatted_cells[:len(headers)]) + " |")
        return "\n".join(lines)

    def to_csv(self) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        if self.headers:
            writer.writerow(self.headers)
        for row in self.rows:
            writer.writerow([cell if cell is not None else "" for cell in row])
        return output.getvalue()

    def to_dict(self) -> dict[str, Any]:
        return {
            "table_id": self.table_id,
            "page_number": self.page_number,
            "title_or_caption": self.title_or_caption,
            "headers": self.headers,
            "rows": self.rows,
            "row_count": self.row_count,
            "col_count": self.col_count,
        }


@dataclass
class DocumentFigure:
    figure_id: str
    page_number: int | None
    label: str  # e.g., "Figure 1"
    caption: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DocumentReference:
    ref_id: str  # e.g., "[1]" or "Author2024"
    text: str
    page_number: int | None
    ref_type: str = "reference"  # reference | footnote | citation

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ParsedDocument:
    path: str
    title: str
    page_count: int
    headings: list[HeadingNode] = field(default_factory=list)
    tables: list[DocumentTable] = field(default_factory=list)
    figures: list[DocumentFigure] = field(default_factory=list)
    references: list[DocumentReference] = field(default_factory=list)
    pages: dict[int, str] = field(default_factory=dict)
    cross_references: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    full_text: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "title": self.title,
            "page_count": self.page_count,
            "headings": [h.to_dict() for h in self.headings],
            "tables": [t.to_dict() for t in self.tables],
            "figures": [f.to_dict() for f in self.figures],
            "references": [r.to_dict() for r in self.references],
            "page_count_indexed": len(self.pages),
            "cross_references": self.cross_references,
            "metadata": self.metadata,
            "error": self.error,
        }


# ============================================================================
# Structural Document Parser
# ============================================================================

class DocumentParser:
    """Parses documents with structural hierarchy, table retention, and page awareness."""

    FIG_PATTERN = re.compile(r"^\s*(Fig(?:ure)?\.?\s*(\d+[A-Za-z0-9_.-]*))\s*[:\-—]\s*(.*)$", re.IGNORECASE)
    TABLE_PATTERN = re.compile(r"^\s*(Table\s*(\d+[A-Za-z0-9_.-]*))\s*[:\-—]\s*(.*)$", re.IGNORECASE)
    FOOTNOTE_PATTERN = re.compile(r"^\s*\[(\d+)\]\s+(.*)$")
    CROSS_REF_PATTERN = re.compile(r"\b(?:see|refer to|in|as shown in)\s+(Figure|Table|Section|Appendix)\s+([A-Za-z0-9_.-]+)", re.IGNORECASE)

    @classmethod
    def parse(cls, file_path: str | Path) -> ParsedDocument:
        p = Path(file_path).expanduser().resolve()
        if not p.exists() or not p.is_file():
            return ParsedDocument(
                path=str(p),
                title=p.name,
                page_count=0,
                error=f"File not found: {p}",
            )

        suffix = p.suffix.lower()
        if suffix == ".pdf":
            return cls._parse_pdf(p)
        elif suffix == ".docx":
            return cls._parse_docx(p)
        elif suffix == ".pptx":
            return cls._parse_pptx(p)
        elif suffix in (".md", ".markdown"):
            return cls._parse_markdown(p)
        elif suffix in (".html", ".htm"):
            return cls._parse_html(p)
        elif suffix in (".csv", ".tsv"):
            return cls._parse_csv(p)
        else:
            return cls._parse_text(p)

    @classmethod
    def _parse_pdf(cls, path: Path) -> ParsedDocument:
        try:
            import pdfplumber
        except ImportError:
            return ParsedDocument(path=str(path), title=path.name, page_count=0, error="pdfplumber is required for PDF parsing.")

        pages_dict: dict[int, str] = {}
        headings: list[HeadingNode] = []
        tables: list[DocumentTable] = []
        figures: list[DocumentFigure] = []
        references: list[DocumentReference] = []
        cross_refs: list[dict[str, Any]] = []
        full_text_parts: list[str] = []

        try:
            with pdfplumber.open(str(path)) as pdf:
                page_count = len(pdf.pages)
                table_counter = 1
                fig_counter = 1

                for page_idx, page in enumerate(pdf.pages, start=1):
                    raw_text = page.extract_text() or ""
                    clean_text = redact_secrets(raw_text).strip()
                    pages_dict[page_idx] = clean_text
                    if clean_text:
                        full_text_parts.append(clean_text)

                    # 1. Extract Tables
                    extracted_tables = page.extract_tables() or []
                    for t_idx, t in enumerate(extracted_tables):
                        if t and len(t) >= 1:
                            raw_headers = [str(c or "").strip() for c in t[0]]
                            raw_rows = [[c if c is not None else None for c in row] for row in t[1:]]
                            col_cnt = max(len(raw_headers), max((len(r) for r in raw_rows), default=0))
                            dt = DocumentTable(
                                table_id=f"table_p{page_idx}_{t_idx+1}",
                                page_number=page_idx,
                                title_or_caption=f"Table {table_counter} (Page {page_idx})",
                                headers=raw_headers,
                                rows=raw_rows,
                                row_count=len(raw_rows),
                                col_count=col_cnt,
                            )
                            tables.append(dt)
                            table_counter += 1

                    # 2. Extract Headings, Figures, Footnotes from page lines
                    lines = clean_text.splitlines()
                    for line_idx, line in enumerate(lines):
                        stripped = line.strip()
                        if not stripped:
                            continue

                        # Heading Detection (Uppercase or numbering)
                        if (
                            re.match(r"^(\d+\.[\d.]*)\s+([A-Za-z0-9].*)$", stripped)
                            or (len(stripped) < 70 and stripped.isupper() and len(stripped) > 3)
                        ):
                            level = 1 if stripped.isupper() else stripped.count(".") + 1
                            headings.append(
                                HeadingNode(
                                    level=min(level, 4),
                                    text=stripped,
                                    page_number=page_idx,
                                    breadcrumb=stripped,
                                    line_offset=line_idx,
                                )
                            )

                        # Figure Caption Detection
                        fig_m = cls.FIG_PATTERN.match(stripped)
                        if fig_m:
                            figures.append(
                                DocumentFigure(
                                    figure_id=f"fig_{fig_counter}",
                                    page_number=page_idx,
                                    label=fig_m.group(1),
                                    caption=fig_m.group(3) or fig_m.group(1),
                                )
                            )
                            fig_counter += 1

                        # Footnote Detection
                        fn_m = cls.FOOTNOTE_PATTERN.match(stripped)
                        if fn_m and line_idx > len(lines) - 8:  # Bottom of page
                            references.append(
                                DocumentReference(
                                    ref_id=f"[{fn_m.group(1)}]",
                                    text=fn_m.group(2),
                                    page_number=page_idx,
                                    ref_type="footnote",
                                )
                            )

                        # Cross References
                        for cref in cls.CROSS_REF_PATTERN.finditer(stripped):
                            cross_refs.append({
                                "page_number": page_idx,
                                "type": cref.group(1).title(),
                                "target": cref.group(2),
                                "context": stripped[:120],
                            })

            return ParsedDocument(
                path=str(path),
                title=path.name,
                page_count=page_count,
                headings=headings,
                tables=tables,
                figures=figures,
                references=references,
                pages=pages_dict,
                cross_references=cross_refs,
                metadata={"file_size": path.stat().st_size},
                full_text="\n\n".join(full_text_parts),
            )
        except Exception as exc:
            return ParsedDocument(
                path=str(path),
                title=path.name,
                page_count=0,
                error=f"PDF parsing error: {exc}",
            )

    @classmethod
    def _parse_docx(cls, path: Path) -> ParsedDocument:
        try:
            import docx
            doc = docx.Document(str(path))
        except Exception as exc:
            return ParsedDocument(path=str(path), title=path.name, page_count=0, error=f"DOCX parsing error: {exc}")

        headings: list[HeadingNode] = []
        tables: list[DocumentTable] = []
        figures: list[DocumentFigure] = []
        references: list[DocumentReference] = []
        cross_refs: list[dict[str, Any]] = []
        text_lines: list[str] = []

        breadcrumb_stack: list[str] = []

        for p_idx, p in enumerate(doc.paragraphs):
            txt = redact_secrets(p.text.strip())
            if not txt:
                continue
            text_lines.append(txt)

            # Heading styles
            if p.style and p.style.name.startswith("Heading"):
                try:
                    level = int(p.style.name.replace("Heading", "").strip() or 1)
                except ValueError:
                    level = 1
                # Update breadcrumb stack
                while len(breadcrumb_stack) >= level:
                    breadcrumb_stack.pop()
                breadcrumb_stack.append(txt)
                headings.append(
                    HeadingNode(
                        level=level,
                        text=txt,
                        page_number=1,  # DOCX doesn't have native page divisions without word layout engine
                        breadcrumb=" > ".join(breadcrumb_stack),
                        line_offset=p_idx,
                    )
                )

            # Figure Captions
            fig_m = cls.FIG_PATTERN.match(txt)
            if fig_m:
                figures.append(
                    DocumentFigure(
                        figure_id=f"fig_{len(figures)+1}",
                        page_number=1,
                        label=fig_m.group(1),
                        caption=fig_m.group(3) or fig_m.group(1),
                    )
                )

            # Cross references
            for cref in cls.CROSS_REF_PATTERN.finditer(txt):
                cross_refs.append({
                    "page_number": 1,
                    "type": cref.group(1).title(),
                    "target": cref.group(2),
                    "context": txt[:120],
                })

        # Tables
        for t_idx, table in enumerate(doc.tables, start=1):
            t_rows = [[cell.text.strip() if cell.text.strip() else None for cell in row.cells] for row in table.rows]
            if t_rows:
                headers = [str(c or "") for c in t_rows[0]]
                data_rows = t_rows[1:]
                tables.append(
                    DocumentTable(
                        table_id=f"table_{t_idx}",
                        page_number=1,
                        title_or_caption=f"Table {t_idx}",
                        headers=headers,
                        rows=data_rows,
                        row_count=len(data_rows),
                        col_count=len(headers),
                    )
                )

        full_text = "\n".join(text_lines)
        return ParsedDocument(
            path=str(path),
            title=path.name,
            page_count=1,
            headings=headings,
            tables=tables,
            figures=figures,
            references=references,
            pages={1: full_text},
            cross_references=cross_refs,
            metadata={"paragraphs": len(doc.paragraphs), "tables": len(doc.tables)},
            full_text=full_text,
        )

    @classmethod
    def _parse_pptx(cls, path: Path) -> ParsedDocument:
        try:
            from pptx import Presentation
            prs = Presentation(str(path))
        except Exception as exc:
            return ParsedDocument(path=str(path), title=path.name, page_count=0, error=f"PPTX parsing error: {exc}")

        headings: list[HeadingNode] = []
        tables: list[DocumentTable] = []
        figures: list[DocumentFigure] = []
        pages_dict: dict[int, str] = {}
        all_text_parts: list[str] = []

        for slide_idx, slide in enumerate(prs.slides, start=1):
            slide_texts: list[str] = []
            slide_title = f"Slide {slide_idx}"
            for shape in slide.shapes:
                if shape.has_text_frame:
                    t = redact_secrets(shape.text_frame.text.strip())
                    if t:
                        if not slide_texts and shape == slide.shapes[0]:
                            slide_title = t.splitlines()[0][:60]
                        slide_texts.append(t)
                if shape.has_table:
                    tbl = shape.table
                    t_rows = [[c.text.strip() if c.text.strip() else None for c in row.cells] for row in tbl.rows]
                    if t_rows:
                        headers = [str(c or "") for c in t_rows[0]]
                        tables.append(
                            DocumentTable(
                                table_id=f"table_slide_{slide_idx}_{len(tables)+1}",
                                page_number=slide_idx,
                                title_or_caption=f"Slide {slide_idx} Table",
                                headers=headers,
                                rows=t_rows[1:],
                                row_count=len(t_rows) - 1,
                                col_count=len(headers),
                            )
                        )

            headings.append(
                HeadingNode(
                    level=1,
                    text=slide_title,
                    page_number=slide_idx,
                    breadcrumb=f"Slide {slide_idx} > {slide_title}",
                )
            )

            slide_body = "\n".join(slide_texts)
            pages_dict[slide_idx] = slide_body
            if slide_body:
                all_text_parts.append(f"--- Slide {slide_idx}: {slide_title} ---\n{slide_body}")

        full_text = "\n\n".join(all_text_parts)
        return ParsedDocument(
            path=str(path),
            title=path.name,
            page_count=len(prs.slides),
            headings=headings,
            tables=tables,
            figures=figures,
            pages=pages_dict,
            full_text=full_text,
        )

    @classmethod
    def _parse_markdown(cls, path: Path) -> ParsedDocument:
        content = redact_secrets(path.read_text(encoding="utf-8", errors="replace"))
        headings: list[HeadingNode] = []
        tables: list[DocumentTable] = []
        figures: list[DocumentFigure] = []
        references: list[DocumentReference] = []
        cross_refs: list[dict[str, Any]] = []

        lines = content.splitlines()
        breadcrumb_stack: list[str] = []
        in_table = False
        table_lines: list[str] = []
        t_counter = 1

        for idx, line in enumerate(lines):
            stripped = line.strip()

            # Markdown Table detection
            if stripped.startswith("|") and stripped.endswith("|"):
                in_table = True
                table_lines.append(stripped)
                continue
            elif in_table:
                # Table ended
                if len(table_lines) >= 2:
                    cls._process_md_table(table_lines, t_counter, tables)
                    t_counter += 1
                table_lines = []
                in_table = False

            # Markdown Headings (# Header)
            h_match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
            if h_match:
                level = len(h_match.group(1))
                htext = h_match.group(2).strip()
                while len(breadcrumb_stack) >= level:
                    breadcrumb_stack.pop()
                breadcrumb_stack.append(htext)
                headings.append(
                    HeadingNode(
                        level=level,
                        text=htext,
                        page_number=1,
                        breadcrumb=" > ".join(breadcrumb_stack),
                        line_offset=idx,
                    )
                )

            # Figures / Images ![Alt](url "Caption")
            img_m = re.match(r"^!\[(.*?)\]\((.*?)\)$", stripped)
            if img_m:
                figures.append(
                    DocumentFigure(
                        figure_id=f"fig_{len(figures)+1}",
                        page_number=1,
                        label=f"Figure {len(figures)+1}",
                        caption=img_m.group(1) or img_m.group(2),
                    )
                )

            # Footnotes [^1]: text
            fn_m = re.match(r"^\[\^([A-Za-z0-9_.-]+)\]:\s*(.*)$", stripped)
            if fn_m:
                references.append(
                    DocumentReference(
                        ref_id=f"[^{fn_m.group(1)}]",
                        text=fn_m.group(2),
                        page_number=1,
                        ref_type="footnote",
                    )
                )

            # Cross references
            for cref in cls.CROSS_REF_PATTERN.finditer(stripped):
                cross_refs.append({
                    "page_number": 1,
                    "type": cref.group(1).title(),
                    "target": cref.group(2),
                    "context": stripped[:120],
                })

        if in_table and len(table_lines) >= 2:
            cls._process_md_table(table_lines, t_counter, tables)

        return ParsedDocument(
            path=str(path),
            title=path.name,
            page_count=1,
            headings=headings,
            tables=tables,
            figures=figures,
            references=references,
            pages={1: content},
            cross_references=cross_refs,
            full_text=content,
        )

    @classmethod
    def _process_md_table(cls, lines: list[str], t_counter: int, tables: list[DocumentTable]) -> None:
        raw_rows = []
        for l in lines:
            parts = [c.strip() for c in l.strip("|").split("|")]
            raw_rows.append(parts)
        if not raw_rows:
            return
        headers = raw_rows[0]
        # Skip separator row if present
        data_rows = raw_rows[1:]
        if data_rows and all(re.match(r"^:?-+:?$", cell) for cell in data_rows[0]):
            data_rows = data_rows[1:]
        # Convert empty strings to None where applicable
        cleaned_rows = [[cell if cell else None for cell in r] for r in data_rows]
        tables.append(
            DocumentTable(
                table_id=f"table_{t_counter}",
                page_number=1,
                title_or_caption=f"Table {t_counter}",
                headers=headers,
                rows=cleaned_rows,
                row_count=len(cleaned_rows),
                col_count=len(headers),
            )
        )

    @classmethod
    def _parse_html(cls, path: Path) -> ParsedDocument:
        from bs4 import BeautifulSoup
        html = redact_secrets(path.read_text(encoding="utf-8", errors="replace"))
        soup = BeautifulSoup(html, "html.parser")
        title = soup.title.string.strip() if soup.title and soup.title.string else path.name

        headings: list[HeadingNode] = []
        tables: list[DocumentTable] = []
        figures: list[DocumentFigure] = []

        for h_tag in soup.find_all(re.compile(r"^h[1-6]$")):
            lvl = int(h_tag.name[1])
            headings.append(
                HeadingNode(
                    level=lvl,
                    text=h_tag.get_text().strip(),
                    page_number=1,
                    breadcrumb=h_tag.get_text().strip(),
                )
            )

        for t_idx, table_tag in enumerate(soup.find_all("table"), start=1):
            t_rows = []
            for tr in table_tag.find_all("tr"):
                cells = [td.get_text().strip() if td.get_text().strip() else None for td in tr.find_all(["td", "th"])]
                if cells:
                    t_rows.append(cells)
            if t_rows:
                headers = [str(c or "") for c in t_rows[0]]
                tables.append(
                    DocumentTable(
                        table_id=f"table_{t_idx}",
                        page_number=1,
                        title_or_caption=f"Table {t_idx}",
                        headers=headers,
                        rows=t_rows[1:],
                        row_count=len(t_rows) - 1,
                        col_count=len(headers),
                    )
                )

        clean_text = soup.get_text(separator="\n").strip()
        return ParsedDocument(
            path=str(path),
            title=title,
            page_count=1,
            headings=headings,
            tables=tables,
            figures=figures,
            pages={1: clean_text},
            full_text=clean_text,
        )

    @classmethod
    def _parse_csv(cls, path: Path) -> ParsedDocument:
        delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
        content = redact_secrets(path.read_text(encoding="utf-8", errors="replace"))
        reader = csv.reader(io.StringIO(content), delimiter=delimiter)
        rows = list(reader)
        tables: list[DocumentTable] = []
        if rows:
            headers = rows[0]
            data_rows = [[cell if cell != "" else None for cell in r] for r in rows[1:]]
            tables.append(
                DocumentTable(
                    table_id="table_csv_1",
                    page_number=1,
                    title_or_caption=path.name,
                    headers=headers,
                    rows=data_rows,
                    row_count=len(data_rows),
                    col_count=len(headers),
                )
            )

        return ParsedDocument(
            path=str(path),
            title=path.name,
            page_count=1,
            tables=tables,
            pages={1: content},
            full_text=content,
        )

    @classmethod
    def _parse_text(cls, path: Path) -> ParsedDocument:
        content = redact_secrets(path.read_text(encoding="utf-8", errors="replace"))
        headings: list[HeadingNode] = []
        lines = content.splitlines()
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if (
                re.match(r"^(\d+\.[\d.]*)\s+([A-Za-z0-9].*)$", stripped)
                or (len(stripped) < 60 and stripped.isupper() and len(stripped) > 3)
            ):
                headings.append(
                    HeadingNode(
                        level=1,
                        text=stripped,
                        page_number=1,
                        breadcrumb=stripped,
                        line_offset=idx,
                    )
                )

        return ParsedDocument(
            path=str(path),
            title=path.name,
            page_count=1,
            headings=headings,
            pages={1: content},
            full_text=content,
        )


# ============================================================================
# Document Reasoning Engine
# ============================================================================

class DocumentReasoningEngine:
    """Performs structured reasoning over single or multiple documents without cross-contamination."""

    SPEC_PATTERN = re.compile(
        r"\b([A-Za-z0-9_\-\s]{2,25}?)\s*[:=]\s*([+\-]?[0-9]+(?:\.[0-9]+)?)\s*([A-Za-zµ%°/]{1,10})\b"
    )

    @classmethod
    def _extract_section_text(cls, doc: ParsedDocument, heading: HeadingNode) -> str:
        text = doc.pages.get(heading.page_number or 1, "") or doc.full_text
        pos = text.find(heading.text)
        if pos == -1:
            return ""
        start = pos + len(heading.text)
        lines = text[start:].splitlines()
        body_lines: list[str] = []
        for line in lines:
            stripped = line.strip()
            # If line is another heading (# or 1. etc.)
            if stripped.startswith("#") or re.match(r"^(\d+\.[\d.]*)\s+", stripped):
                break
            if stripped:
                body_lines.append(stripped)
        return "\n".join(body_lines).strip()

    @classmethod
    def summarize(cls, doc: ParsedDocument, max_points: int = 5) -> dict[str, Any]:
        """Produces a structural summary, highlighting main conclusions with page references."""
        conclusions: list[dict[str, Any]] = []
        key_sections: list[dict[str, Any]] = []

        # Identify Conclusion / Summary sections
        for h in doc.headings:
            key_sections.append({
                "title": h.text,
                "breadcrumb": h.breadcrumb,
                "page": h.page_number,
                "level": h.level,
            })
            if re.search(r"\b(conclusion|conclusions|summary|findings|results|takeaway)\b", h.text, re.IGNORECASE):
                sec_text = cls._extract_section_text(doc, h)
                if not sec_text:
                    sec_text = doc.pages.get(h.page_number or 1, "")
                sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", sec_text) if len(s.strip()) > 15]
                for s in sentences[:max_points]:
                    conclusions.append({
                        "point": s,
                        "source_section": h.text,
                        "page": h.page_number,
                    })

        # Fallback if no explicit conclusion section
        if not conclusions and doc.full_text:
            sentences = [s.strip() for s in re.split(r"\.\s+", doc.full_text) if len(s.strip()) > 30]
            for s in sentences[-max_points:]:
                conclusions.append({
                    "point": s,
                    "source_section": "Document Body",
                    "page": doc.page_count,
                })

        return {
            "title": doc.title,
            "page_count": doc.page_count,
            "total_headings": len(doc.headings),
            "total_tables": len(doc.tables),
            "total_figures": len(doc.figures),
            "key_sections": key_sections[:10],
            "conclusions": conclusions[:max_points],
        }

    @classmethod
    def find_section(cls, doc: ParsedDocument, query: str) -> list[dict[str, Any]]:
        """Finds sections discussing a specific topic, preserving page citations."""
        q_clean = query.strip().lower()
        q_tokens = [w for w in re.findall(r"[a-z0-9_]{3,}", q_clean)]
        matches: list[dict[str, Any]] = []

        # Check headings first
        for h in doc.headings:
            h_lower = h.text.lower()
            if any(t in h_lower for t in q_tokens):
                sec_text = cls._extract_section_text(doc, h) or doc.pages.get(h.page_number or 1, "")
                matches.append({
                    "section_title": h.text,
                    "breadcrumb": h.breadcrumb,
                    "page": h.page_number,
                    "relevance": "heading_match",
                    "preview": sec_text[:280] if sec_text else "",
                })

        # Check page text for matching paragraphs
        for p_num, p_text in doc.pages.items():
            if all(t in p_text.lower() for t in q_tokens):
                # Already matched in heading?
                if not any(m["page"] == p_num for m in matches):
                    snippet = p_text[:300].strip()
                    matches.append({
                        "section_title": f"Page {p_num}",
                        "breadcrumb": f"Page {p_num}",
                        "page": p_num,
                        "relevance": "body_match",
                        "preview": snippet,
                    })

        return matches

        # Check page text for matching paragraphs
        for p_num, p_text in doc.pages.items():
            if all(t in p_text.lower() for t in q_tokens):
                # Already matched in heading?
                if not any(m["page"] == p_num for m in matches):
                    snippet = p_text[:300].strip()
                    matches.append({
                        "section_title": f"Page {p_num}",
                        "breadcrumb": f"Page {p_num}",
                        "page": p_num,
                        "relevance": "body_match",
                        "preview": snippet,
                    })

        return matches

    @classmethod
    def extract_specifications(cls, doc: ParsedDocument) -> list[dict[str, Any]]:
        """Extracts numerical specifications, values, and units from text and tables."""
        specs: list[dict[str, Any]] = []

        # From text
        for p_num, p_text in doc.pages.items():
            for m in cls.SPEC_PATTERN.finditer(p_text):
                param = m.group(1).strip()
                val = float(m.group(2))
                unit = m.group(3).strip()
                specs.append({
                    "parameter": param,
                    "value": val,
                    "unit": unit,
                    "page": p_num,
                    "source": "text",
                })

        # From tables
        for t in doc.tables:
            for r in t.rows:
                if len(r) >= 2 and r[0] is not None and r[1] is not None:
                    param = str(r[0]).strip()
                    val_str = str(r[1]).strip()
                    # Check if val_str contains number + optional unit
                    num_m = re.match(r"^([+\-]?[0-9]+(?:\.[0-9]+)?)\s*([A-Za-zµ%°/]{0,10})$", val_str)
                    if num_m:
                        specs.append({
                            "parameter": param,
                            "value": float(num_m.group(1)),
                            "unit": num_m.group(2) or "",
                            "page": t.page_number,
                            "source": f"Table: {t.title_or_caption}",
                        })

        return specs

    @classmethod
    def compare_documents(cls, doc_a: ParsedDocument, doc_b: ParsedDocument) -> dict[str, Any]:
        """Compares two documents: structure, specifications, and differences."""
        specs_a = cls.extract_specifications(doc_a)
        specs_b = cls.extract_specifications(doc_b)

        # Map specs by normalized parameter name
        map_a: dict[str, dict[str, Any]] = {s["parameter"].lower(): s for s in specs_a}
        map_b: dict[str, dict[str, Any]] = {s["parameter"].lower(): s for s in specs_b}

        common_params = set(map_a.keys()) & set(map_b.keys())
        discrepancies: list[dict[str, Any]] = []
        agreements: list[dict[str, Any]] = []

        for p in common_params:
            item_a = map_a[p]
            item_b = map_b[p]
            if item_a["value"] != item_b["value"] or item_a["unit"] != item_b["unit"]:
                discrepancies.append({
                    "parameter": item_a["parameter"],
                    f"{doc_a.title}": f"{item_a['value']} {item_a['unit']}".strip(),
                    f"{doc_b.title}": f"{item_b['value']} {item_b['unit']}".strip(),
                    "page_a": item_a["page"],
                    "page_b": item_b["page"],
                })
            else:
                agreements.append({
                    "parameter": item_a["parameter"],
                    "value": f"{item_a['value']} {item_a['unit']}".strip(),
                })

        return {
            "document_a": {
                "title": doc_a.title,
                "pages": doc_a.page_count,
                "headings": len(doc_a.headings),
                "tables": len(doc_a.tables),
                "figures": len(doc_a.figures),
                "specs_count": len(specs_a),
            },
            "document_b": {
                "title": doc_b.title,
                "pages": doc_b.page_count,
                "headings": len(doc_b.headings),
                "tables": len(doc_b.tables),
                "figures": len(doc_b.figures),
                "specs_count": len(specs_b),
            },
            "common_parameters_count": len(common_params),
            "discrepancies": discrepancies,
            "agreements": agreements,
            "unique_to_a": [map_a[k]["parameter"] for k in set(map_a.keys()) - set(map_b.keys())][:10],
            "unique_to_b": [map_b[k]["parameter"] for k in set(map_b.keys()) - set(map_a.keys())][:10],
        }


# ============================================================================
# Export Utilities
# ============================================================================

def export_table_csv(table: DocumentTable, output_path: str | Path) -> Path:
    p = Path(output_path).expanduser().resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(table.to_csv(), encoding="utf-8")
    return p


def export_tables_xlsx(tables: list[DocumentTable], output_path: str | Path) -> Path:
    import openpyxl
    p = Path(output_path).expanduser().resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    # Remove default sheet
    wb.remove(wb.active)

    for idx, table in enumerate(tables, start=1):
        sheet_title = (table.title_or_caption[:25] or f"Table_{idx}").replace(":", "_").replace("/", "_")
        ws = wb.create_sheet(title=sheet_title)
        if table.headers:
            ws.append(table.headers)
        for row in table.rows:
            ws.append([cell if cell is not None else "" for cell in row])

    wb.save(str(p))
    return p
