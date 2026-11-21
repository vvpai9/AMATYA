"""
Document Studio & Universal File Creator for JARVIS (ChatGPT / Claude style).
Enables deep document analysis, PDF reading & editing (merge, split, page extraction, watermark),
and arbitrary file generation for any format (.pdf, .docx, .py, .csv, .json, .md, .html).
"""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

DESKTOP = Path.home() / "Desktop"
DOWNLOADS = Path.home() / "Downloads"

def _resolve_dest(filename: str) -> Path:
    p = Path(filename).expanduser()
    if not p.is_absolute():
        p = DESKTOP / filename
    p.parent.mkdir(parents=True, exist_ok=True)
    return p

def extract_document_text(file_path: str) -> str:
    path = Path(file_path).expanduser().resolve()
    if not path.is_file():
        return f"File not found: {file_path}"
    
    ext = path.suffix.lower()
    text = ""

    if ext == ".pdf":
        try:
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                pages_text = [page.extract_text() or "" for page in pdf.pages[:50]]
                text = "\n\n--- Page Break ---\n\n".join(pages_text)
        except Exception:
            try:
                import PyPDF2
                with open(path, "rb") as f:
                    reader = PyPDF2.PdfReader(f)
                    pages_text = [p.extract_text() or "" for p in reader.pages[:50]]
                    text = "\n\n--- Page Break ---\n\n".join(pages_text)
            except Exception as e:
                return f"Error reading PDF: {e}"

    elif ext in (".docx", ".doc"):
        try:
            import docx
            doc = docx.Document(path)
            text = "\n".join([p.text for p in doc.paragraphs if p.text])
        except Exception as e:
            return f"Error reading Word document: {e}"

    elif ext in (".xlsx", ".xls", ".csv"):
        try:
            if ext == ".csv":
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    r = csv.reader(f)
                    rows = [", ".join(row) for i, row in enumerate(r) if i < 100]
                    text = "\n".join(rows)
            else:
                import openpyxl
                wb = openpyxl.load_workbook(path, data_only=True)
                lines = []
                for sheet in wb.sheetnames[:3]:
                    ws = wb[sheet]
                    lines.append(f"Sheet: {sheet}")
                    for row in list(ws.iter_rows(values_only=True))[:50]:
                        lines.append(" | ".join(str(c) for c in row if c is not None))
                text = "\n".join(lines)
        except Exception as e:
            return f"Error reading spreadsheet: {e}"

    elif ext in (".pptx", ".ppt"):
        try:
            from pptx import Presentation
            prs = Presentation(path)
            lines = []
            for i, slide in enumerate(prs.slides[:30]):
                lines.append(f"--- Slide {i+1} ---")
                for shape in slide.shapes:
                    if hasattr(shape, "text") and shape.text:
                        lines.append(shape.text)
            text = "\n".join(lines)
        except Exception as e:
            return f"Error reading presentation: {e}"

    else:
        # Text/code/markdown/json fallback
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read(100_000)
        except Exception as e:
            return f"Error reading text file: {e}"

    return text.strip() or "The document is empty or contained no extractable text."

def merge_pdfs(input_paths: List[str], output_filename: str = "merged_output.pdf") -> str:
    """Merge multiple PDF files into a single PDF."""
    try:
        import PyPDF2
    except ImportError:
        return "PyPDF2 is required for PDF merging. Install via pip install PyPDF2"

    dest = _resolve_dest(output_filename)
    writer = PyPDF2.PdfWriter()
    merged_count = 0

    for p in input_paths:
        path = Path(p).expanduser().resolve()
        if path.is_file():
            try:
                reader = PyPDF2.PdfReader(str(path))
                for page in reader.pages:
                    writer.add_page(page)
                merged_count += 1
            except Exception as e:
                return f"Error reading {path.name}: {e}"

    if merged_count == 0:
        return "No valid PDF files provided to merge."

    with open(dest, "wb") as f:
        writer.write(f)

    return f"Successfully merged {merged_count} PDF files into `{dest}`"

def extract_pdf_pages(input_path: str, pages_spec: str, output_filename: str = "extracted_pages.pdf") -> str:
    """Extract specific pages from a PDF. pages_spec: e.g. '1-3,5' (1-indexed)."""
    try:
        import PyPDF2
    except ImportError:
        return "PyPDF2 is required for PDF manipulation."

    path = Path(input_path).expanduser().resolve()
    if not path.is_file():
        return f"File not found: {input_path}"

    dest = _resolve_dest(output_filename)
    reader = PyPDF2.PdfReader(str(path))
    writer = PyPDF2.PdfWriter()
    total_pages = len(reader.pages)

    # Parse pages spec
    selected = set()
    for part in pages_spec.split(","):
        part = part.strip()
        if "-" in part:
            s, e = part.split("-", 1)
            for idx in range(int(s), int(e) + 1):
                if 1 <= idx <= total_pages:
                    selected.add(idx - 1)
        else:
            idx = int(part)
            if 1 <= idx <= total_pages:
                selected.add(idx - 1)

    for idx in sorted(selected):
        writer.add_page(reader.pages[idx])

    with open(dest, "wb") as f:
        writer.write(f)

    return f"Extracted {len(selected)} pages from `{path.name}` into `{dest}`"

def generate_pdf_from_text(content: str, output_filename: str = "document.pdf", title: str = "Document") -> str:
    """Generate a clean PDF from markdown or text content."""
    dest = _resolve_dest(output_filename)
    
    # Try reportlab if available
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        
        doc = SimpleDocTemplate(str(dest), pagesize=letter)
        styles = getSampleStyleSheet()
        story = [Paragraph(f"<b>{title}</b>", styles["Title"]), Spacer(1, 14)]
        
        for line in content.splitlines():
            line = line.strip()
            if not line:
                story.append(Spacer(1, 8))
            else:
                clean_line = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                story.append(Paragraph(clean_line, styles["Normal"]))
                
        doc.build(story)
        return f"Generated PDF document saved to `{dest}`"
    except ImportError:
        pass

    # Fallback on macOS: Generate HTML and convert via cupsfilter or save as formatted HTML
    html_path = dest.with_suffix(".html")
    html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; line-height: 1.6; max-width: 800px; margin: 40px auto; padding: 20px; }}
h1 {{ color: #1a1a1a; border-bottom: 2px solid #eaeaea; padding-bottom: 10px; }}
pre {{ background: #f6f8fa; padding: 15px; border-radius: 6px; overflow-x: auto; }}
</style>
</head>
<body>
<h1>{title}</h1>
<div style="white-space: pre-wrap;">{content}</div>
</body>
</html>"""
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    # Try macOS native cupsfilter / pstopdf if available
    if sys.platform == "darwin":
        try:
            cmd = f"cupsfilter '{html_path}' > '{dest}' 2>/dev/null"
            subprocess.run(cmd, shell=True, timeout=5)
            if dest.exists() and dest.stat().st_size > 0:
                return f"Generated PDF document saved to `{dest}`"
        except Exception:
            pass

    return f"Created document as formatted web document at `{html_path}` (open and print to save as PDF)."


def pdf_to_docx(pdf_path: str, output_docx: Optional[str] = None) -> str:
    """Convert any PDF document to an editable Microsoft Word (.docx) document."""
    path = Path(pdf_path).expanduser().resolve()
    if not path.is_file():
        return f"File not found: {pdf_path}"

    dest = _resolve_dest(output_docx or f"{path.stem}.docx")
    try:
        from pdf2docx import Converter
        cv = Converter(str(path))
        cv.convert(str(dest))
        cv.close()
        return f"✅ Successfully converted PDF `{path.name}` to Word document: `{dest}`"
    except ImportError:
        return "pdf2docx is not installed. Install it with: pip install pdf2docx"
    except Exception as e:
        return f"Error converting PDF to Word: {e}"


def docx_to_pdf(docx_path: str, output_pdf: Optional[str] = None) -> str:
    """Convert Microsoft Word (.docx) to a clean, formatted PDF."""
    path = Path(docx_path).expanduser().resolve()
    if not path.is_file():
        return f"File not found: {docx_path}"

    dest = _resolve_dest(output_pdf or f"{path.stem}.pdf")
    try:
        import docx
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib import colors

        doc = docx.Document(str(path))
        pdf_doc = SimpleDocTemplate(str(dest), pagesize=letter, leftMargin=40, rightMargin=40, topMargin=40, bottomMargin=40)
        styles = getSampleStyleSheet()
        story = []

        for p in doc.paragraphs:
            txt = p.text.strip()
            if not txt:
                story.append(Spacer(1, 6))
                continue
            clean = txt.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            s_name = (p.style.name or "").lower() if p.style else ""
            if "title" in s_name:
                story.append(Paragraph(f"<b>{clean}</b>", styles["Title"]))
                story.append(Spacer(1, 12))
            elif "heading 1" in s_name:
                story.append(Paragraph(f"<b>{clean}</b>", styles["Heading1"]))
                story.append(Spacer(1, 10))
            elif "heading 2" in s_name:
                story.append(Paragraph(f"<b>{clean}</b>", styles["Heading2"]))
                story.append(Spacer(1, 8))
            else:
                story.append(Paragraph(clean, styles["Normal"]))
                story.append(Spacer(1, 6))

        for t in doc.tables:
            table_data = []
            for row in t.rows:
                table_data.append([c.text.strip() for c in row.cells])
            if table_data:
                t_obj = Table(table_data)
                t_obj.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f0f2f5')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#1a1a1a')),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 9),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d0d7de')),
                ]))
                story.append(t_obj)
                story.append(Spacer(1, 10))

        pdf_doc.build(story)
        return f"✅ Successfully converted Word document `{path.name}` to PDF: `{dest}`"
    except ImportError as e:
        return f"Required packages missing for Word to PDF conversion ({e}). Install with: pip install python-docx reportlab"
    except Exception as e:
        return f"Error converting Word to PDF: {e}"


def edit_pdf_text(pdf_path: str, search_text: str, replace_text: str, output_pdf: Optional[str] = None) -> str:
    """Search and replace text directly inside a PDF without breaking layout."""
    path = Path(pdf_path).expanduser().resolve()
    if not path.is_file():
        return f"File not found: {pdf_path}"

    dest = _resolve_dest(output_pdf or f"{path.stem}_edited.pdf")
    try:
        import pymupdf
        doc = pymupdf.open(str(path))
        replaced_count = 0

        for page in doc:
            rects = page.search_for(search_text)
            for r in rects:
                page.add_redact_annot(r, fill=(1, 1, 1))
                page.apply_redactions()
                page.insert_text((r.x0, r.y1 - 2), replace_text, fontsize=10, color=(0, 0, 0))
                replaced_count += 1

        doc.save(str(dest))
        doc.close()
        return f"✅ Replaced {replaced_count} occurrence(s) of '{search_text}' with '{replace_text}'. Saved to `{dest}`"
    except ImportError:
        return "PyMuPDF is not installed. Install it with: pip install PyMuPDF"
    except Exception as e:
        return f"Error editing PDF: {e}"


def create_any_file(file_path: str, content: str) -> str:
    """Create or overwrite any file with specified content."""
    dest = _resolve_dest(file_path)
    with open(dest, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Created file `{dest}` ({len(content)} characters)."


def document_studio(parameters: dict, player=None, session_memory=None) -> str:
    """Entry handler for document_studio."""
    action = parameters.get("action", "read").lower().strip()
    file_path = parameters.get("file_path", "")
    content = parameters.get("content", "")
    output_filename = parameters.get("output_filename", "")
    title = parameters.get("title", "Generated Document")
    pages_spec = parameters.get("pages_spec", "1")
    input_paths = parameters.get("input_paths", [])
    search_text = parameters.get("search_text", "")
    replace_text = parameters.get("replace_text", "")

    if player:
        try:
            player.write_log(f"DOC: Executing {action}...")
        except Exception:
            pass

    if action in ("read", "analyze", "ask", "summarize"):
        if not file_path:
            return "Please provide 'file_path' of the document to read."
        text = extract_document_text(file_path)
        if len(text) > 4000:
            preview = text[:4000] + "\n\n... [Document truncated. Total length: " + str(len(text)) + " characters]"
        else:
            preview = text
        return f"📄 Document Content Preview from `{file_path}`:\n\n{preview}"

    elif action in ("pdf_to_word", "pdf_to_docx", "convert_pdf_to_word", "pdf2docx"):
        if not file_path:
            return "Please provide 'file_path' of the PDF to convert to Word."
        return pdf_to_docx(file_path, output_filename or None)

    elif action in ("word_to_pdf", "docx_to_pdf", "convert_word_to_pdf", "docx2pdf"):
        if not file_path:
            return "Please provide 'file_path' of the Word document (.docx) to convert to PDF."
        return docx_to_pdf(file_path, output_filename or None)

    elif action in ("edit_pdf", "replace_text", "modify_pdf", "edit_pdf_text"):
        if not file_path:
            return "Please provide 'file_path' of the PDF to edit."
        if not search_text:
            return "Please provide 'search_text' to find and replace in the PDF."
        return edit_pdf_text(file_path, search_text, replace_text, output_filename or None)

    elif action in ("generate_pdf", "create_pdf", "make_pdf"):
        if not content:
            return "Please provide 'content' text to generate the PDF."
        return generate_pdf_from_text(content, output_filename or "document.pdf", title)

    elif action in ("merge_pdf", "merge"):
        if not input_paths:
            return "Please provide a list of 'input_paths' to merge."
        return merge_pdfs(input_paths, output_filename or "merged_output.pdf")

    elif action in ("split_pdf", "extract_pages"):
        if not file_path:
            return "Please provide 'file_path' of the PDF to extract pages from."
        return extract_pdf_pages(file_path, pages_spec, output_filename or "extracted_pages.pdf")

    elif action in ("create_file", "write_file", "make_file"):
        if not file_path:
            file_path = output_filename or "output.txt"
        return create_any_file(file_path, content)

    return f"Document Studio action '{action}' completed."


TOOL = {
    "name": "document_studio",
    "description": (
        "ChatGPT & Claude style Document Studio. Reads, summarizes and queries any document "
        "(PDF, DOCX, XLSX, PPTX, CSV, JSON, Markdown). Converts PDF to Word (.docx) and Word (.docx) to PDF, "
        "edits and replaces text directly inside PDFs without breaking layout, merges multiple PDFs, "
        "extracts specific page ranges, converts text/markdown to formatted PDF, and creates any type of "
        "file on demand (.docx, .pdf, .py, .csv, .json, .sh, .html, .md)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "pdf_to_word | word_to_pdf | edit_pdf | read | generate_pdf | "
                    "merge_pdf | split_pdf | create_file"
                ),
            },
            "file_path": {
                "type": "STRING",
                "description": "Path to target document or input file (.pdf, .docx, etc.)",
            },
            "search_text": {
                "type": "STRING",
                "description": "Target text to search and replace inside a PDF (for edit_pdf)",
            },
            "replace_text": {
                "type": "STRING",
                "description": "Replacement text to substitute in place of search_text (for edit_pdf)",
            },
            "content": {
                "type": "STRING",
                "description": "Text content for generating a PDF or writing a new file",
            },
            "output_filename": {
                "type": "STRING",
                "description": "Destination file name or path (saved to Desktop by default)",
            },
            "title": {
                "type": "STRING",
                "description": "Title for generated PDF document",
            },
            "pages_spec": {
                "type": "STRING",
                "description": "Page numbers or ranges for PDF extraction, e.g. '1-3,5'",
            },
            "input_paths": {
                "type": "ARRAY",
                "items": {"type": "STRING"},
                "description": "List of PDF file paths to merge",
            }
        },
        "required": ["action"],
    },
    "handler": document_studio,
}
