"""
AMATYA Document & Archive Generation and Analysis Engine (core/doc_generator.py)
================================================================================
Implements Section 10.3 (Document and file generation & analysis):
  Supports creating and reading/analyzing:
    - PDF documents (.pdf)
    - Word documents (.docx via python-docx)
    - Excel spreadsheets (.xlsx via openpyxl / xlsxwriter)
    - PowerPoint presentations (.pptx via python-pptx)
    - CSV tables (.csv)
    - Markdown / Technical reports (.md)
    - ZIP archives (.zip)
"""
from __future__ import annotations

import csv
import json
import zipfile
from pathlib import Path
from typing import Any


def _write_simple_pdf(output_path: Path, title: str, body: str) -> None:
    """Write a clean, standards-compliant PDF-1.4 document with Helvetica text
    (zero external system dependencies required)."""
    lines: list[str] = []
    if title:
        lines.append(title)
        lines.append("=" * min(60, len(title)))
        lines.append("")
    for raw_line in (body or "").splitlines():
        # Wrap long lines at 88 chars
        while len(raw_line) > 88:
            lines.append(raw_line[:88])
            raw_line = raw_line[88:]
        lines.append(raw_line)

    # Escape PDF literal string characters
    def _esc(s: str) -> str:
        safe = s.encode("latin-1", errors="replace").decode("latin-1")
        return safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    # Paginate at 46 lines per page
    pages_lines = [lines[i:i + 46] for i in range(0, max(1, len(lines)), 46)]

    objects: list[bytes] = []
    # 1: Catalog, 2: Pages, 3: Font (Helvetica)
    page_obj_ids = [4 + 2 * i for i in range(len(pages_lines))]
    kids_str = " ".join(f"{pid} 0 R" for pid in page_obj_ids)

    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{kids_str}] /Count {len(pages_lines)} >>".encode("ascii"))
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    for idx, plines in enumerate(pages_lines):
        page_id = 4 + 2 * idx
        content_id = page_id + 1
        stream_cmds = ["BT", "/F1 11 Tf", "50 750 Td", "15 TL"]
        for l in plines:
            stream_cmds.append(f"({_esc(l)}) Tj T*")
        stream_cmds.append("ET")
        stream_bytes = "\n".join(stream_cmds).encode("latin-1", errors="replace")

        page_dict = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>"
        ).encode("ascii")
        content_dict = (
            f"<< /Length {len(stream_bytes)} >>\nstream\n".encode("ascii")
            + stream_bytes
            + b"\nendstream"
        )
        objects.append(page_dict)
        objects.append(content_dict)

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: list[int] = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{i} 0 obj\n".encode("ascii"))
        out.extend(obj)
        out.extend(b"\nendobj\n")

    xref_offset = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for off in offsets:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    out.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(bytes(out))


def generate_document(
    output_path: str | Path,
    title: str = "AMATYA Document",
    content: str = "",
    sections: list[dict[str, Any]] | None = None,
    rows: list[list[Any]] | None = None,
    source_paths: list[str] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Generate a PDF, DOCX, XLSX, PPTX, CSV, Markdown, or ZIP file."""
    out = Path(output_path).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    ext = out.suffix.lower()

    try:
        if ext == ".pdf":
            body_parts = [content] if content else []
            for sec in (sections or []):
                body_parts.append(f"\n{sec.get('heading', '')}\n{sec.get('body', '')}")
            _write_simple_pdf(out, title, "\n".join(body_parts).strip())
            return {"ok": True, "format": "pdf", "path": str(out), "size_bytes": out.stat().st_size}

        if ext == ".docx":
            import docx
            doc = docx.Document()
            if title:
                doc.add_heading(title, level=0)
            if content:
                for para in content.split("\n\n"):
                    if para.strip():
                        doc.add_paragraph(para.strip())
            for sec in (sections or []):
                if sec.get("heading"):
                    doc.add_heading(str(sec["heading"]), level=int(sec.get("level", 1)))
                if sec.get("body"):
                    doc.add_paragraph(str(sec["body"]))
            if rows:
                table = doc.add_table(rows=len(rows), cols=max(len(r) for r in rows))
                for r_idx, row in enumerate(rows):
                    for c_idx, val in enumerate(row):
                        table.cell(r_idx, c_idx).text = str(val)
            doc.save(str(out))
            return {"ok": True, "format": "docx", "path": str(out), "size_bytes": out.stat().st_size}

        if ext == ".xlsx":
            import openpyxl
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = (title or "Sheet1")[:31]
            data_rows = rows or []
            if not data_rows and content:
                for line in content.splitlines():
                    data_rows.append([cell.strip() for cell in line.split(",")])
            for r in data_rows:
                ws.append(list(r))
            wb.save(str(out))
            return {"ok": True, "format": "xlsx", "path": str(out), "rows": len(data_rows), "size_bytes": out.stat().st_size}

        if ext == ".pptx":
            pptx_content = content
            pptx_title = title
            pptx_sections = sections
            pptx_theme = str(kwargs.get("theme", "navy"))
            if isinstance(content, dict):
                pptx_title = title or content.get("title") or "AMATYA Professional Presentation"
                pptx_sections = sections or content.get("slides") or content.get("sections")
                pptx_theme = str(content.get("theme") or kwargs.get("theme", "navy"))
                pptx_content = content.get("subtitle") or content.get("content") or ""

            return _build_professional_pptx(
                output_path=out,
                title=pptx_title or "AMATYA Professional Presentation",
                content=str(pptx_content or ""),
                sections=pptx_sections or [],
                rows=rows or [],
                source_paths=source_paths or [],
                theme=pptx_theme,
            )

        if ext == ".csv":
            data_rows = rows or []
            if not data_rows and content:
                for line in content.splitlines():
                    data_rows.append([c.strip() for c in line.split(",")])
            with out.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerows(data_rows)
            return {"ok": True, "format": "csv", "path": str(out), "rows": len(data_rows), "size_bytes": out.stat().st_size}

        if ext == ".zip":
            srcs = [Path(p).expanduser().resolve() for p in (source_paths or [])]
            with zipfile.ZipFile(str(out), "w", zipfile.ZIP_DEFLATED) as zf:
                if srcs:
                    for sp in srcs:
                        if sp.is_file():
                            zf.write(str(sp), arcname=sp.name)
                        elif sp.is_dir():
                            for child in sp.rglob("*"):
                                if child.is_file():
                                    zf.write(str(child), arcname=str(child.relative_to(sp.parent)))
                elif content:
                    zf.writestr("README.md", f"# {title}\n\n{content}\n")
            return {"ok": True, "format": "zip", "path": str(out), "size_bytes": out.stat().st_size}

        # Default: Markdown / code / text
        text_out = content
        if title and ext in (".md", ".rst") and not content.lstrip().startswith("#"):
            text_out = f"# {title}\n\n{content}\n"
        out.write_text(text_out, encoding="utf-8")
        return {"ok": True, "format": ext.lstrip(".") or "txt", "path": str(out), "size_bytes": out.stat().st_size}

    except Exception as exc:
        return {"ok": False, "path": str(out), "error": f"Document generation failed: {exc}"}


def analyze_document(file_path: str | Path) -> dict[str, Any]:
    """Read and extract structured content + metadata from PDF, DOCX, XLSX, PPTX, CSV, ZIP, or text."""
    fp = Path(file_path).expanduser().resolve()
    if not fp.exists():
        return {"ok": False, "error": f"File not found: {fp}"}

    ext = fp.suffix.lower()
    try:
        if ext == ".pdf":
            text_pages: list[str] = []
            try:
                import pdfplumber
                with pdfplumber.open(str(fp)) as pdf:
                    for p in pdf.pages:
                        text_pages.append(p.extract_text() or "")
            except Exception:
                from PyPDF2 import PdfReader
                reader = PdfReader(str(fp))
                for p in reader.pages:
                    text_pages.append(p.extract_text() or "")
            full_text = "\n\n".join(text_pages).strip()
            return {
                "ok": True,
                "format": "pdf",
                "path": str(fp),
                "pages": len(text_pages),
                "text": full_text,
            }

        if ext == ".docx":
            import docx
            doc = docx.Document(str(fp))
            paras = [p.text for p in doc.paragraphs if p.text.strip()]
            tables_data = []
            for t in doc.tables:
                tables_data.append([[cell.text.strip() for cell in row.cells] for row in t.rows])
            return {
                "ok": True,
                "format": "docx",
                "path": str(fp),
                "paragraphs": len(paras),
                "tables": tables_data,
                "text": "\n\n".join(paras),
            }

        if ext == ".xlsx":
            import openpyxl
            wb = openpyxl.load_workbook(str(fp), data_only=True)
            sheets: dict[str, list[list[Any]]] = {}
            for name in wb.sheetnames:
                ws = wb[name]
                rows = []
                for row in ws.iter_rows(values_only=True):
                    if any(cell is not None for cell in row):
                        rows.append([cell for cell in row])
                sheets[name] = rows[:200]
            return {
                "ok": True,
                "format": "xlsx",
                "path": str(fp),
                "sheet_names": wb.sheetnames,
                "sheets": sheets,
            }

        if ext == ".pptx":
            from pptx import Presentation
            prs = Presentation(str(fp))
            slides_text: list[dict[str, Any]] = []
            for idx, slide in enumerate(prs.slides, start=1):
                texts = []
                for shape in slide.shapes:
                    if getattr(shape, "has_text_frame", False):
                        t = shape.text_frame.text.strip()
                        if t:
                            texts.append(t)
                slides_text.append({"slide": idx, "text": "\n".join(texts)})
            return {
                "ok": True,
                "format": "pptx",
                "path": str(fp),
                "slide_count": len(slides_text),
                "slides": slides_text,
                "text": "\n\n".join(f"[Slide {s['slide']}]\n{s['text']}" for s in slides_text),
            }

        if ext == ".csv":
            with fp.open("r", encoding="utf-8", errors="replace") as fh:
                rows = list(csv.reader(fh))
            return {
                "ok": True,
                "format": "csv",
                "path": str(fp),
                "row_count": len(rows),
                "rows": rows[:200],
            }

        if ext == ".zip":
            with zipfile.ZipFile(str(fp), "r") as zf:
                entries = [
                    {"filename": info.filename, "size_bytes": info.file_size}
                    for info in zf.infolist()
                ]
            return {
                "ok": True,
                "format": "zip",
                "path": str(fp),
                "file_count": len(entries),
                "entries": entries,
            }

        text = fp.read_text(encoding="utf-8", errors="replace")
        return {
            "ok": True,
            "format": ext.lstrip(".") or "txt",
            "path": str(fp),
            "text": text,
        }
    except Exception as exc:
        return {"ok": False, "path": str(fp), "error": f"Document analysis failed: {exc}"}


def _build_professional_pptx(
    output_path: Path,
    title: str,
    content: str = "",
    sections: list[dict[str, Any]] | None = None,
    rows: list[list[Any]] | None = None,
    source_paths: list[str] | None = None,
    theme: str = "navy",
) -> dict[str, Any]:
    """Generate high-impact, widescreen 16:9 professional presentations with cards,
    metrics, images, and slide transitions."""
    import time
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.enum.text import PP_ALIGN
    from pptx.oxml import parse_xml
    from pptx.util import Inches, Pt

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank_layout = prs.slide_layouts[6]

    is_dark = theme.lower() != "corporate"
    bg_color = RGBColor(11, 19, 43) if is_dark else RGBColor(248, 249, 250)
    card_color = RGBColor(28, 37, 65) if is_dark else RGBColor(255, 255, 255)
    card_border = RGBColor(58, 80, 107) if is_dark else RGBColor(222, 226, 230)
    primary_accent = RGBColor(0, 180, 216) if is_dark else RGBColor(29, 53, 87)
    gold_accent = RGBColor(255, 209, 102) if is_dark else RGBColor(230, 57, 70)
    text_title_color = RGBColor(255, 255, 255) if is_dark else RGBColor(29, 53, 87)
    text_body_color = RGBColor(224, 225, 221) if is_dark else RGBColor(43, 45, 66)
    text_muted_color = RGBColor(144, 224, 239) if is_dark else RGBColor(108, 117, 125)

    transitions = [
        '<p:transition xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" spd="med"><p:fade/></p:transition>',
        '<p:transition xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" spd="med"><p:push dir="l"/></p:transition>',
        '<p:transition xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" spd="med"><p:wipe dir="r"/></p:transition>',
        '<p:transition xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" spd="med"><p:split orient="horz"/></p:transition>',
    ]

    def set_background(slide):
        bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(13.333), Inches(7.5))
        bg.fill.solid()
        bg.fill.fore_color.rgb = bg_color
        bg.line.fill.background()
        return bg

    def apply_transition(slide, idx):
        try:
            trans_xml = transitions[idx % len(transitions)]
            slide._element.append(parse_xml(trans_xml))
        except Exception:
            pass

    slide_index = 0

    # ── 1. Title Slide ──────────────────────────────────────────────────────────
    s1 = prs.slides.add_slide(blank_layout)
    set_background(s1)
    apply_transition(s1, slide_index)
    slide_index += 1

    # Accent Stripe
    stripe = s1.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(1.8), Inches(0.12), Inches(3.2))
    stripe.fill.solid()
    stripe.fill.fore_color.rgb = primary_accent
    stripe.line.fill.background()

    # Title & Subtitle Box
    tb1 = s1.shapes.add_textbox(Inches(1.2), Inches(1.8), Inches(11.2), Inches(2.2))
    tf1 = tb1.text_frame
    tf1.word_wrap = True
    p1 = tf1.paragraphs[0]
    p1.text = title or "AMATYA Executive Briefing"
    p1.font.size = Pt(40)
    p1.font.bold = True
    p1.font.color.rgb = text_title_color

    p1_sub = tf1.add_paragraph()
    p1_sub.text = (content[:160] + "...") if len(content) > 160 else (content or "Autonomous Intelligence & Systems Engineering")
    p1_sub.font.size = Pt(18)
    p1_sub.font.color.rgb = text_muted_color
    p1_sub.space_before = Pt(14)

    # Footer Card
    f_card = s1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1.2), Inches(5.6), Inches(10.8), Inches(0.9))
    f_card.fill.solid()
    f_card.fill.fore_color.rgb = card_color
    f_card.line.color.rgb = card_border
    ftf = f_card.text_frame
    ftf.word_wrap = True
    ftp = ftf.paragraphs[0]
    ftp.text = f"Prepared by AMATYA Companion  •  {time.strftime('%B %d, %Y')}  •  Confidential / Professional Document"
    ftp.font.size = Pt(13)
    ftp.font.color.rgb = text_muted_color
    ftp.alignment = PP_ALIGN.CENTER

    # ── Prepare Content Slides ──────────────────────────────────────────────────
    slide_items = list(sections or [])
    if not slide_items:
        # Auto-structure content into multi-slide presentation
        paragraphs = [p.strip() for p in (content or "").split("\n\n") if p.strip()]
        if len(paragraphs) >= 4:
            slide_items = [
                {"heading": "Executive Overview & Context", "body": paragraphs[0]},
                {"heading": "Core Analysis & Technical Principles", "body": paragraphs[1]},
                {"heading": "Key Performance Metrics & Findings", "body": paragraphs[2]},
                {"heading": "Strategic Conclusion & Recommendations", "body": "\n".join(paragraphs[3:])},
            ]
        elif paragraphs:
            slide_items = [{"heading": title or "Detailed Overview", "body": p} for p in paragraphs]
        else:
            slide_items = [
                {
                    "heading": "Executive Overview",
                    "cards": [
                        {"title": "Core Objective", "text": "High-reliability autonomous operations with complete local governance."},
                        {"title": "Strategic Focus", "text": "Continuous context tracking and secure execution of compound engineering workflows."},
                    ],
                },
                {
                    "heading": "Operational Metrics",
                    "stats": [
                        {"value": "100%", "label": "Test Suite Pass Rate"},
                        {"value": "<50ms", "label": "Command Latency"},
                        {"value": "6 Tiers", "label": "Security Hierarchy"},
                    ],
                },
                {
                    "heading": "Strategic Roadmap",
                    "cards": [
                        {"title": "Phase 1: Foundation", "text": "Hardware-aware intelligence routing and Wayland desktop integration."},
                        {"title": "Phase 2: Deployment", "text": "Adaptive workflow learning and proactive companion notifications."},
                    ],
                },
            ]

    # Find available images from source_paths or sections
    available_images = [Path(p) for p in (source_paths or []) if Path(p).suffix.lower() in (".png", ".jpg", ".jpeg", ".webp") and Path(p).exists()]

    # ── 2..N Content Slides ─────────────────────────────────────────────────────
    for sec_idx, sec in enumerate(slide_items):
        s = prs.slides.add_slide(blank_layout)
        set_background(s)
        apply_transition(s, slide_index)
        slide_index += 1

        heading = str(sec.get("heading") or sec.get("title") or f"Section {sec_idx + 1}")
        subheading = str(sec.get("subheading") or sec.get("subtitle") or "")

        # Slide Header Pill
        header_pill = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(0.55), Inches(0.12), Inches(0.8))
        header_pill.fill.solid()
        header_pill.fill.fore_color.rgb = primary_accent
        header_pill.line.fill.background()

        # Header Text Box
        htb = s.shapes.add_textbox(Inches(1.1), Inches(0.45), Inches(11.4), Inches(1.1))
        htf = htb.text_frame
        htf.word_wrap = True
        hp = htf.paragraphs[0]
        hp.text = heading
        hp.font.size = Pt(26)
        hp.font.bold = True
        hp.font.color.rgb = text_title_color
        if subheading:
            hp_sub = htf.add_paragraph()
            hp_sub.text = subheading
            hp_sub.font.size = Pt(13)
            hp_sub.font.color.rgb = text_muted_color

        # Case A: Stat callouts
        stat_list = sec.get("stats") or sec.get("metrics")
        if stat_list and isinstance(stat_list, list):
            stats = stat_list[:4]
            count = len(stats)
            c_width = (11.6 - (count - 1) * 0.3) / count
            for i, st in enumerate(stats):
                left = Inches(0.8 + i * (c_width + 0.3))
                card = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, Inches(2.2), Inches(c_width), Inches(3.8))
                card.fill.solid()
                card.fill.fore_color.rgb = card_color
                card.line.color.rgb = card_border

                ctf = card.text_frame
                ctf.word_wrap = True
                cp1 = ctf.paragraphs[0]
                cp1.text = str(st.get("value", ""))
                cp1.font.size = Pt(36)
                cp1.font.bold = True
                cp1.font.color.rgb = gold_accent
                cp1.alignment = PP_ALIGN.CENTER
                cp1.space_before = Pt(36)

                cp2 = ctf.add_paragraph()
                cp2.text = str(st.get("label", ""))
                cp2.font.size = Pt(15)
                cp2.font.color.rgb = text_body_color
                cp2.alignment = PP_ALIGN.CENTER
                cp2.space_before = Pt(14)

        # Case B: Multi-column cards
        elif sec.get("cards") and isinstance(sec["cards"], list):
            cards = sec["cards"][:3]
            count = len(cards)
            c_width = (11.6 - (count - 1) * 0.4) / count
            for i, cd in enumerate(cards):
                left = Inches(0.8 + i * (c_width + 0.4))
                card = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, Inches(2.0), Inches(c_width), Inches(4.5))
                card.fill.solid()
                card.fill.fore_color.rgb = card_color
                card.line.color.rgb = card_border

                ctf = card.text_frame
                ctf.word_wrap = True
                cp1 = ctf.paragraphs[0]
                cp1.text = str(cd.get("title", ""))
                cp1.font.size = Pt(19)
                cp1.font.bold = True
                cp1.font.color.rgb = primary_accent

                cp2 = ctf.add_paragraph()
                cp2.text = str(cd.get("text") or cd.get("content") or cd.get("body", ""))
                cp2.font.size = Pt(14)
                cp2.font.color.rgb = text_body_color
                cp2.space_before = Pt(10)

        # Case C: Image on right, text on left
        elif sec.get("image") or (available_images and sec_idx == 1):
            img_path = Path(sec.get("image") or available_images[0])
            # Left text card
            left_card = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(2.0), Inches(6.0), Inches(4.6))
            left_card.fill.solid()
            left_card.fill.fore_color.rgb = card_color
            left_card.line.color.rgb = card_border

            ltf = left_card.text_frame
            ltf.word_wrap = True
            lines = [l.strip() for l in str(sec.get("body", "")).splitlines() if l.strip()]
            for li, line in enumerate(lines[:6]):
                lp = ltf.paragraphs[0] if li == 0 else ltf.add_paragraph()
                lp.text = f"•  {line}"
                lp.font.size = Pt(14)
                lp.font.color.rgb = text_body_color
                if li > 0:
                    lp.space_before = Pt(8)

            # Right image container
            try:
                s.shapes.add_picture(str(img_path), Inches(7.2), Inches(2.0), width=Inches(5.2))
            except Exception:
                pass

        # Case D: Detailed 2-column bullet layout
        else:
            body_text = str(sec.get("body", ""))
            lines = [l.strip("-*• \t\r\n") for l in body_text.splitlines() if l.strip("-*• \t\r\n")]
            if not lines and content:
                lines = [content[:200]]

            mid = (len(lines) + 1) // 2
            left_lines = lines[:mid]
            right_lines = lines[mid:]

            # Left Card
            c1 = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(2.0), Inches(5.6), Inches(4.6))
            c1.fill.solid()
            c1.fill.fore_color.rgb = card_color
            c1.line.color.rgb = card_border
            tf_c1 = c1.text_frame
            tf_c1.word_wrap = True
            for li, line in enumerate(left_lines or ["Key Findings"]):
                p = tf_c1.paragraphs[0] if li == 0 else tf_c1.add_paragraph()
                p.text = f"▸  {line}"
                p.font.size = Pt(14)
                p.font.color.rgb = text_body_color
                if li > 0:
                    p.space_before = Pt(8)

            # Right Card
            c2 = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(6.8), Inches(2.0), Inches(5.6), Inches(4.6))
            c2.fill.solid()
            c2.fill.fore_color.rgb = card_color
            c2.line.color.rgb = card_border
            tf_c2 = c2.text_frame
            tf_c2.word_wrap = True
            for li, line in enumerate(right_lines or ["Strategic Directives"]):
                p = tf_c2.paragraphs[0] if li == 0 else tf_c2.add_paragraph()
                p.text = f"▸  {line}"
                p.font.size = Pt(14)
                p.font.color.rgb = text_body_color
                if li > 0:
                    p.space_before = Pt(8)

    prs.save(str(output_path))
    return {
        "ok": True,
        "format": "pptx",
        "path": str(output_path),
        "slides": len(prs.slides),
        "theme": theme,
        "size_bytes": output_path.stat().st_size,
    }

