"""
Document Studio & Universal File Creator for JARVIS (ChatGPT / Claude style).
Enables deep document analysis, PDF reading & editing (merge, split, page extraction, watermark),
and arbitrary file generation for any format (.pdf, .docx, .py, .csv, .json, .md, .html).
"""

from __future__ import annotations

import csv
import json
import os
import re
import subprocess
import sys
import xml.sax.saxutils as saxutils
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
            import pymupdf
            doc = pymupdf.open(str(path))
            pages_text = []
            scanned_pages = []
            for i, page in enumerate(doc):
                ptxt = page.get_text() or ""
                if len(ptxt.strip()) < 30:
                    scanned_pages.append(i)
                pages_text.append(ptxt)

            # If pages seem image-based / scanned, run vision extraction on up to 5 key pages
            if scanned_pages and len(scanned_pages) >= len(doc) * 0.8:
                try:
                    from core import gemini
                    ocr_pages = []
                    for idx in scanned_pages[:6]:
                        pix = doc[idx].get_pixmap(dpi=150)
                        img_bytes = pix.tobytes("png")
                        ocr_txt = gemini.text([
                            "Extract and transcribe all text, questions, diagrams, and math from this document page accurately:",
                            {"inline_data": {"mime_type": "image/png", "data": img_bytes}}
                        ], tier=gemini.FAST, timeout_ms=30000)
                        if ocr_txt:
                            ocr_pages.append(f"--- Page {idx+1} (Vision OCR) ---\n{ocr_txt}")
                    if ocr_pages:
                        doc.close()
                        return "\n\n".join(ocr_pages)
                except Exception:
                    pass

            doc.close()
            text = "\n\n--- Page Break ---\n\n".join(pages_text)
            if not text.strip():
                raise ValueError("PyMuPDF returned empty text")
        except Exception:
            try:
                import pdfplumber
                with pdfplumber.open(path) as pdf:
                    pages_text = [page.extract_text() or "" for page in pdf.pages[:80]]
                    text = "\n\n--- Page Break ---\n\n".join(pages_text)
            except Exception:
                try:
                    import PyPDF2
                    with open(path, "rb") as f:
                        reader = PyPDF2.PdfReader(f)
                        pages_text = [p.extract_text() or "" for p in reader.pages[:80]]
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
    """Generate a clean, beautiful, fully valid PDF from markdown or text content.
    Uses ReportLab as the primary rich typesetter and PyMuPDF as a guaranteed binary fallback."""
    dest = _resolve_dest(output_filename)
    if dest.suffix.lower() != ".pdf":
        dest = dest.with_suffix(".pdf")
    dest.parent.mkdir(parents=True, exist_ok=True)
    
    # 1. Primary Engine: ReportLab (Professional Multi-page Typesetting)
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors

        doc = SimpleDocTemplate(
            str(dest),
            pagesize=letter,
            leftMargin=44, rightMargin=44,
            topMargin=44, bottomMargin=44
        )
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            'DocTitle',
            parent=styles['Title'],
            fontName='Helvetica-Bold',
            fontSize=18,
            leading=22,
            textColor=colors.HexColor('#1a2a40'),
            spaceAfter=8,
            alignment=0
        )
        h1_style = ParagraphStyle(
            'DocH1',
            parent=styles['Heading1'],
            fontName='Helvetica-Bold',
            fontSize=13,
            leading=17,
            textColor=colors.HexColor('#1e40af'),
            spaceBefore=10,
            spaceAfter=4
        )
        h2_style = ParagraphStyle(
            'DocH2',
            parent=styles['Heading2'],
            fontName='Helvetica-Bold',
            fontSize=11,
            leading=15,
            textColor=colors.HexColor('#1f2937'),
            spaceBefore=8,
            spaceAfter=3
        )
        body_style = ParagraphStyle(
            'DocBody',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=9.5,
            leading=13.5,
            textColor=colors.HexColor('#262626'),
            spaceAfter=4
        )
        bullet_style = ParagraphStyle(
            'DocBullet',
            parent=body_style,
            leftIndent=14,
            firstLineIndent=-10,
            spaceAfter=3
        )
        code_style = ParagraphStyle(
            'DocCode',
            parent=body_style,
            fontName='Courier',
            fontSize=8.5,
            leading=11.5,
            textColor=colors.HexColor('#0f172a'),
            backColor=colors.HexColor('#f1f5f9'),
            spaceBefore=4,
            spaceAfter=4
        )

        def _clean_markup(txt: str) -> str:
            t = saxutils.escape(txt)
            t = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', t)
            t = re.sub(r'\*(.*?)\*', r'<i>\1</i>', t)
            t = re.sub(r'`(.*?)`', r'<font name="Courier">\1</font>', t)
            return t

        story = []
        if title:
            story.append(Paragraph(_clean_markup(title), title_style))
            story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#1e40af'), spaceBefore=2, spaceAfter=10))

        in_code_block = False
        code_lines = []

        for raw_line in content.splitlines():
            line = raw_line.rstrip()
            if line.startswith("```"):
                if in_code_block:
                    block_txt = "<br/>".join(_clean_markup(cl) for cl in code_lines)
                    story.append(Paragraph(block_txt, code_style))
                    story.append(Spacer(1, 4))
                    code_lines = []
                    in_code_block = False
                else:
                    in_code_block = True
                    code_lines = []
                continue

            if in_code_block:
                code_lines.append(line)
                continue

            sline = line.strip()
            if not sline:
                story.append(Spacer(1, 5))
                continue

            if sline.startswith("# "):
                story.append(Paragraph(_clean_markup(sline[2:]), h1_style))
            elif sline.startswith("## "):
                story.append(Paragraph(_clean_markup(sline[3:]), h2_style))
            elif sline.startswith("### "):
                story.append(Paragraph(_clean_markup(sline[4:]), h2_style))
            elif sline.startswith("- ") or sline.startswith("* "):
                story.append(Paragraph(f"&bull; {_clean_markup(sline[2:])}", bullet_style))
            elif re.match(r'^\d+\.\s', sline):
                m = re.match(r'^(\d+\.)\s*(.*)', sline)
                if m:
                    story.append(Paragraph(f"<b>{m.group(1)}</b> {_clean_markup(m.group(2))}", bullet_style))
                else:
                    story.append(Paragraph(_clean_markup(sline), body_style))
            elif sline.startswith("---") or sline.startswith("___"):
                story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#cbd5e1'), spaceBefore=4, spaceAfter=4))
            else:
                story.append(Paragraph(_clean_markup(sline), body_style))

        if in_code_block and code_lines:
            block_txt = "<br/>".join(_clean_markup(cl) for cl in code_lines)
            story.append(Paragraph(block_txt, code_style))

        doc.build(story)
        if dest.exists() and dest.stat().st_size > 200:
            return f"✅ Generated PDF document saved to `{dest}`"
    except Exception as e:
        print(f"[DocumentStudio] ReportLab error: {e}, using PyMuPDF fallback")

    # 2. Secondary Engine (Guaranteed Binary Fallback): PyMuPDF
    try:
        import pymupdf
        mupdf_doc = pymupdf.open()
        page_w, page_h = 595.0, 842.0  # A4 size
        margin = 44.0

        page = mupdf_doc.new_page(width=page_w, height=page_h)
        y_cursor = margin + 20

        if title:
            page.insert_text(pymupdf.Point(margin, y_cursor), title, fontsize=16, fontname="helv", color=(0.1, 0.15, 0.3))
            y_cursor += 12
            page.draw_line(pymupdf.Point(margin, y_cursor), pymupdf.Point(page_w - margin, y_cursor), color=(0.1, 0.25, 0.6), width=1.2)
            y_cursor += 18

        rect = pymupdf.Rect(margin, y_cursor, page_w - margin, page_h - margin)
        rc = page.insert_textbox(rect, content, fontsize=9.5, fontname="helv", color=(0.15, 0.15, 0.15))

        # Handle overflow onto subsequent pages
        max_pages = 25
        page_count = 1
        while rc < 0 and page_count < max_pages:
            page = mupdf_doc.new_page(width=page_w, height=page_h)
            rect = pymupdf.Rect(margin, margin + 20, page_w - margin, page_h - margin)
            rc = page.insert_textbox(rect, content, fontsize=9.5, fontname="helv", color=(0.15, 0.15, 0.15))
            page_count += 1

        mupdf_doc.save(str(dest))
        mupdf_doc.close()
        return f"✅ Generated PDF document saved to `{dest}`"
    except Exception as e2:
        return f"Error generating PDF: {e2}"


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
                # Add redaction over existing text
                page.add_redact_annot(r, fill=(1, 1, 1))
                page.apply_redactions()
                # Insert replacement text
                page.insert_text((r.x0, r.y1 - 2), replace_text, fontsize=10, color=(0, 0, 0))
                replaced_count += 1

        doc.save(str(dest))
        doc.close()

        if replaced_count == 0:
            return f"Search text '{search_text}' was not found in `{path.name}`."
        return f"✅ Replaced {replaced_count} occurrence(s) of '{search_text}' with '{replace_text}'. Saved to `{dest}`"
    except Exception as e:
        return f"Error editing PDF: {e}"


def create_any_file(file_path: str, content: str) -> str:
    """Create or overwrite any file with specified content.
    If the requested file is a PDF, routes automatically through the PDF compiler."""
    dest = _resolve_dest(file_path)
    if dest.suffix.lower() == ".pdf":
        return generate_pdf_from_text(content, str(dest), title=dest.stem)
    with open(dest, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Created file `{dest}` ({len(content)} characters)."


def deep_document_analysis(file_path: str, query: str = "", action: str = "analyze", player=None) -> str:
    """ChatGPT / Claude grade deep document analyzer and problem solver.
    Extracts complete text, solves questions step-by-step, displays the full formatted
    solution on screen in the HUD panel, and saves it permanently to Desktop."""
    path = Path(file_path).expanduser().resolve()
    if not path.is_file():
        return f"File not found: {file_path}"

    text = extract_document_text(str(path))
    if not text or text.startswith("Error"):
        return f"Could not read document: {text}"

    from core import gemini

    task_desc = query.strip() if query and query.strip() else {
        "solve": "Solve all questions, numericals, and problems in this document step-by-step with full workings.",
        "solution": "Provide complete, rigorous step-by-step solutions for all problems in this document.",
        "explain": "Explain every concept, theorem, section, and finding in this document in thorough detail.",
        "summarize": "Provide an executive summary, key takeaways, chapter breakdown, and conclusions.",
    }.get(action, "Provide a comprehensive, detailed breakdown, solutions to all questions, and executive analysis.")

    prompt = f"""You are an elite academic and professional document analyst (ChatGPT & Claude grade).
Analyze this document thoroughly and answer the user request with highest quality, depth, and mathematical/technical rigor.

DOCUMENT NAME: {path.name}
USER REQUEST / INSTRUCTION: {task_desc}

DOCUMENT TEXT CONTENT:
{text[:65000]}

MANDATORY GUIDELINES:
1. Provide a comprehensive, detailed, step-by-step solution or breakdown.
2. If the document has questions, exercises, or math/physics problems, show EVERY single step, formula, derivation, and clear final boxed/bold answer. Never skip steps or say 'exercise left to reader'.
3. Use clean GitHub-flavored Markdown with clear headings (`#`, `##`), bullet points, bold keywords, and LaTeX/code blocks where appropriate.
4. Do NOT abbreviate or truncate the output. Be exhaustive and thorough.
5. Conclude with a crisp key takeaways summary.
"""
    if player and hasattr(player, "write_log"):
        try: player.write_log(f"DOC: Analyzing {path.name} with AI reasoning tier...")
        except Exception: pass

    solution = gemini.text(prompt, tier=gemini.SMART, timeout_ms=120000)
    if not solution:
        solution = f"Could not generate analysis for `{path.name}`. Please check API quota or try with Groq fallback."

    # Display on screen in HUD content panel
    if player and hasattr(player, "show_content"):
        try:
            player.show_content(f"📄 Solution: {path.name}", solution)
        except Exception:
            pass

    # Save to desktop as permanent markdown and pristine PDF
    save_msg = ""
    try:
        sol_dest = DESKTOP / f"{path.stem}_solution.md"
        sol_dest.write_text(f"# Detailed Analysis & Solution: {path.name}\n\n**Query:** {task_desc}\n\n---\n\n{solution}", encoding="utf-8")
        # Also automatically compile a real, valid PDF if pdf is requested or for study solutions
        pdf_dest = DESKTOP / f"{path.stem}_solution.pdf"
        generate_pdf_from_text(solution, str(pdf_dest), title=f"Solutions: {path.stem}")
        save_msg = f" Full detailed solution saved to `{sol_dest.name}` and `{pdf_dest.name}` on Desktop and displayed on your screen."
    except Exception as e:
        print(f"[DocumentStudio] Error saving solutions to desktop: {e}")

    return f"✅ Detailed analysis complete for `{path.name}`.{save_msg}\n\n{solution}"


def document_studio(parameters: dict, player=None, session_memory=None) -> str:
    """Entry handler for document_studio."""
    action = parameters.get("action", "read").lower().strip()
    file_path = parameters.get("file_path", "") or parameters.get("path", "")
    content = parameters.get("content", "")
    query = (
        parameters.get("query")
        or parameters.get("instruction")
        or parameters.get("question")
        or parameters.get("prompt")
        or ""
    )
    output_filename = parameters.get("output_filename", "")
    title = parameters.get("title", "Generated Document")
    pages_spec = parameters.get("pages_spec", "1")
    input_paths = parameters.get("input_paths", [])
    search_text = parameters.get("search_text", "")
    replace_text = parameters.get("replace_text", "")

    if player and hasattr(player, "write_log"):
        try: player.write_log(f"DOC: Executing {action}...")
        except Exception: pass

    # Deep Analysis / Problem Solving
    if action in ("analyze", "ask", "solve", "solution", "explain", "summarize") or (action == "read" and query):
        if not file_path:
            return "Please provide 'file_path' of the document to analyze or solve."
        return deep_document_analysis(file_path, query=query, action=action, player=player)

    elif action == "read":
        if not file_path:
            return "Please provide 'file_path' of the document to read."
        text = extract_document_text(file_path)
        if player and hasattr(player, "show_content"):
            try: player.show_content(f"Document: {Path(file_path).name}", text[:10000])
            except Exception: pass
        if len(text) > 4000:
            preview = text[:4000] + "\n\n... [Document truncated for speech. Full text is on screen. Total length: " + str(len(text)) + " characters]"
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
        target_name = file_path or output_filename or "output.txt"
        return create_any_file(target_name, content)

    return f"Document Studio action '{action}' completed."


TOOL = {
    "name": "document_studio",
    "description": (
        "ChatGPT & Claude style Document Studio. Reads, deeply analyzes, and solves problems from any document "
        "(PDF, DOCX, XLSX, PPTX, CSV, JSON, Markdown). Generates pristine, valid, beautiful PDFs from text or markdown, "
        "converts PDF to Word (.docx) and Word (.docx) to PDF, edits and replaces text inside PDFs without breaking layout, "
        "merges multiple PDFs, extracts specific page ranges, and creates any type of file (.docx, .pdf, .py, .csv, .json, .sh, .html, .md)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "solve | analyze | explain | summarize | read | generate_pdf | "
                    "pdf_to_word | word_to_pdf | edit_pdf | merge_pdf | split_pdf | create_file"
                ),
            },
            "file_path": {
                "type": "STRING",
                "description": "Path to target document or input file (.pdf, .docx, etc.)",
            },
            "query": {
                "type": "STRING",
                "description": "Specific question, problem to solve, or instruction for deep analysis of the document.",
            },
            "instruction": {
                "type": "STRING",
                "description": "Alias for query (free-form instruction or question for document analysis).",
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
                "description": "Text or markdown content for generating a PDF or writing a new file",
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
