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
            from pptx import Presentation
            prs = Presentation()
            # Title slide
            title_layout = prs.slide_layouts[0]
            slide = prs.slides.add_slide(title_layout)
            slide.shapes.title.text = title or "AMATYA Presentation"
            if len(slide.placeholders) > 1:
                slide.placeholders[1].text = content[:250] if content else "Generated by AMATYA CREATOR"

            slide_items = sections or []
            if not slide_items and content:
                slide_items = [{"heading": title or "Overview", "body": content}]

            bullet_layout = prs.slide_layouts[1]
            for sec in slide_items:
                s = prs.slides.add_slide(bullet_layout)
                s.shapes.title.text = str(sec.get("heading", "Slide"))
                tf = s.placeholders[1].text_frame
                body_lines = str(sec.get("body", "")).splitlines()
                for idx, bl in enumerate(body_lines):
                    if idx == 0:
                        tf.text = bl
                    else:
                        p = tf.add_paragraph()
                        p.text = bl
            prs.save(str(out))
            return {"ok": True, "format": "pptx", "path": str(out), "slides": len(prs.slides), "size_bytes": out.stat().st_size}

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

