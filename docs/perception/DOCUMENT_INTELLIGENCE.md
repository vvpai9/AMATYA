# AMATYA Phase 13.3 — Advanced Document Intelligence Specification
## Structural Parsing, Table Extraction, Page-Aware Reasoning & Cross-Document Analysis

**Version:** 13.3.0  
**Implementation:** `core/document_intelligence.py`  
**Tool Action:** `actions/knowledge_base.py` (Actions: `parse_document`, `extract_tables`, `compare_documents`, `document_summary`, `find_section`)  
**Target Architecture:** Multi-format structural document comprehension across PDF, DOCX, PPTX, Markdown, HTML, and CSV.

---

## 1. Overview and Core Objectives

AMATYA Phase 13.3 elevates document processing from simple flat text extraction into **hierarchical structural comprehension and evidence-grounded reasoning**. 

Rather than treating a document as an unstructured stream of tokens, the Document Intelligence Engine (`core/document_intelligence.py`) models:
1. **Document Hierarchy:** Nested headings ($H_1 \to H_2 \to H_3$) and breadcrumb contexts (e.g. `Section 2 > Power Subsystem > Voltage Regulator`).
2. **Page & Coordinate Grounding:** Precise page numbers and source offsets for every extracted paragraph, table, and figure.
3. **Structured Tabular Intelligence:** Tables parsed as discrete 2D matrices preserving row headers, column headers, and data types, while strictly preserving missing values as `None` or `""` (never coercing missing data into `0`).
4. **Figure & Footnote Extraction:** Automated detection of figure labels/captions (`Figure 1: ...`) and footnote/citation links (`[1]`, `[^ref]`).
5. **Cross-Reference Resolution:** Resolving in-text references (e.g., *"see Figure 2 on page 4"* or *"refer to Table 3"*).
6. **Isolated Cross-Document Reasoning:** Comparative analysis across multiple reports and specifications without mixing unrelated facts.

---

## 2. Document Hierarchy and Structural Parsing

```
  ┌─────────────────────────────────────────────────────────────┐
  │                    ParsedDocument Object                    │
  ├─────────────────────────────────────────────────────────────┤
  │ Title: "Mark-LVII Power Architecture"                        │
  │ Page Count: 14                                              │
  │                                                             │
  │ ├── Headings:                                               │
  │ │   ├── [Level 1, Page 1]: "1. Executive Summary"           │
  │ │   └── [Level 2, Page 3]: "2.1 Voltage Regulation"         │
  │ │                                                           │
  │ ├── Tables:                                                 │
  │ │   └── [Table 1, Page 4]: Headers: ["Rail", "Voltage", "I"]│
  │ │                          Rows: [["VCC_CORE", 1.2, 15.0]]  │
  │ │                                                           │
  │ ├── Figures:                                                │
  │ │   └── [Figure 1, Page 6]: "Power Distribution Network"    │
  │ │                                                           │
  │ ├── References:                                             │
  │ │   └── [Ref [1], Page 14]: "IEEE Standard 1149.1-2013"     │
  │ │                                                           │
  │ └── Pages: {1: "...", 2: "...", ...}                        │
  └─────────────────────────────────────────────────────────────┘
```

### Supported Formats & Parsing Strategies:
- **PDF (`pdfplumber`):** Iterates over pages; extracts clean text, table cell boundaries, font hierarchy for headers, figure captions, and bottom-of-page footnotes.
- **DOCX (`python-docx`):** Traverses paragraph styles (`Heading 1`, `Heading 2`, etc.), maintaining a dynamic breadcrumb stack, and extracts Word tables into `DocumentTable` records.
- **PPTX (`python-pptx`):** Treats slides as pages, extracts slide titles as heading nodes, shape text frames, and embedded slide tables.
- **Markdown / Plaintext:** Parses `#` syntax, standard Markdown tables (`| ... |`), image captions (`![Alt](url)`), and footnotes (`[^1]: ...`).
- **HTML (`BeautifulSoup`):** Extracts `<h1>`-`<h6>` tags, `<table>`, `<figure>`, `<figcaption>`, and hyperlinks.
- **Spreadsheets / CSV:** Parses tabular rows and headers into structured matrices with type preservation.

---

## 3. Strict Tabular Data Governance

A common failure in naive document parsers is silently coercing empty cells into numeric `0` or omitting sparse rows. AMATYA enforces strict tabular integrity:
- Empty cells are preserved as `None` or `""`.
- Tables can be rendered losslessly to Markdown (`table.to_markdown()`) or exported directly to standard CSV (`table.to_csv()`) and multi-sheet Excel workbooks (`export_tables_xlsx()`).

---

## 4. Document Reasoning Engine

The `DocumentReasoningEngine` provides four specialized analytical capabilities:

### 4.1 Structural Summarization (`summarize`)
- Extracts executive takeaways and key conclusions by targeting explicit conclusion, summary, or findings sections.
- Cites the exact page number and section heading for each conclusion.

### 4.2 Targeted Section Discovery (`find_section`)
- Finds sections discussing specific topics (e.g., *"power consumption"*, *"thermal throttling"*, *"clock distribution"*).
- Returns the exact section breadcrumb, page number, and relevant excerpt.

### 4.3 Numerical Specification & Unit Extraction (`extract_specifications`)
- Regex and table parsing of numerical specifications with units (e.g. `VCC = 1.2 V`, `Frequency = 3.3 GHz`, `Max Temp = 85 °C`).
- Preserves parameter name, numeric value, unit, and page origin.

### 4.4 Multi-Document Comparative Analysis (`compare_documents`)
- Evaluates Document A vs Document B:
  - Identifies overlapping technical parameters.
  - Flags specification discrepancies (e.g., Document A specifies `10 W` while Document B specifies `15 W`).
  - Reports structural differences (page count, table count, figure count).
  - Guarantees strict isolation: facts from Document A are never attributed to Document B.

---

## 5. Tool Action API (`actions/knowledge_base.py`)

| Action | Parameters | Description |
|---|---|---|
| `parse_document` | `path` | Parses full structure, headings, tables, figures, references, and page map. |
| `extract_tables` | `path`, `[output_path]` | Extracts all tables as JSON, with optional export to `.csv` or `.xlsx`. |
| `compare_documents` | `path`, `path_b` | Performs comparative specification analysis between two documents. |
| `document_summary` | `path` | Generates section-aware summary and key conclusions with page citations. |
| `find_section` | `path`, `query` | Locates specific topics/sections within a document with page breadcrumbs. |

---

## 6. Verification and Acceptance Criteria

Acceptance tests in `tests/test_phase13_acceptance.py` verify:
1. **Structural Heading Recognition:** Validates heading levels ($H_1, H_2$) and breadcrumbs.
2. **Table Extraction & Missing-Value Preservation:** Validates table row/col matrix without zero coercion.
3. **Page-Aware Locality:** Verifies that findings and summaries report accurate source page numbers.
4. **Specification Comparison:** Accurately detects discrepancies between two documents with conflicting parameters.
5. **Cross-Reference Resolution:** Verifies figure, table, and section cross-reference linking.

