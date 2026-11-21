import os
import tempfile
from pathlib import Path
import pytest

from actions.code_interpreter import (
    execute_python_code,
    solve_symbolic_math,
    create_interactive_artifact,
    analyze_dataset,
    code_interpreter,
    CHARTS_DIR,
    ARTIFACTS_DIR,
)
from actions.cyber_security import clean_temp_files, deep_system_scan
from actions.document_studio import pdf_to_docx, docx_to_pdf, edit_pdf_text
from core import gemini


class DummyPlayer:
    def __init__(self):
        self.logs = []
        self.contents = []

    def write_log(self, text: str):
        self.logs.append(text)

    def show_content(self, title: str, text: str):
        self.contents.append((title, text))


def test_execute_python_code_basic():
    code = "print(sum([1, 2, 3, 4, 5]))"
    res = execute_python_code(code, timeout=10)
    assert res["success"] is True
    assert "15" in res["stdout"]


def test_execute_python_code_error():
    code = "raise ValueError('intentional test error')"
    res = execute_python_code(code, timeout=10)
    assert res["success"] is False
    assert "intentional test error" in res["stderr"]


def test_solve_symbolic_math():
    # Derivative
    res_diff = solve_symbolic_math("diff(x**3, x)")
    assert "3*x**2" in res_diff["result"]
    assert "Derivative" in res_diff["operation"]
    assert "latex" in res_diff

    # Integral
    res_int = solve_symbolic_math("integrate(x**2, x)")
    assert "x**3/3" in res_int["result"]
    assert "Integral" in res_int["operation"]

    # Equation
    res_eq = solve_symbolic_math("2*x - 10 = 0")
    assert "5" in res_eq["result"]

    # Expression simplification
    res_simp = solve_symbolic_math("cos(0) + sin(pi/2)")
    assert "2" in res_simp["result"]


def test_create_interactive_artifact():
    # HTML artifact
    res_html = create_interactive_artifact("html", "<p>Interactive Test</p>", title="Test Widget")
    assert Path(res_html["file"]).exists()
    assert "AMATYA Artifact" in Path(res_html["file"]).read_text(encoding="utf-8")
    assert res_html["type"] == "HTML Web App"

    # Mermaid diagram
    res_m = create_interactive_artifact("mermaid", "graph TD; A-->B;", title="Test Architecture")
    assert Path(res_m["file"]).exists()
    assert "mermaid" in Path(res_m["file"]).read_text(encoding="utf-8")

    # SVG vector
    res_svg = create_interactive_artifact("svg", "<svg><circle r='10'/></svg>", title="Test Circle")
    assert Path(res_svg["file"]).exists()
    assert "<circle" in Path(res_svg["file"]).read_text(encoding="utf-8")


def test_analyze_dataset(tmp_path):
    csv_file = tmp_path / "test_data.csv"
    csv_file.write_text("name,age,score\nAlice,25,95\nBob,30,88\nCharlie,35,92\n", encoding="utf-8")

    res = analyze_dataset(str(csv_file))
    assert res["rows"] == 3
    assert res["columns"] == 3
    assert "name" in res["column_names"]
    assert len(res["head"]) == 3


def test_code_interpreter_handler():
    player = DummyPlayer()
    out = code_interpreter({"action": "execute", "code": "print('amatya_interpreter_ok')"}, player=player)
    assert "amatya_interpreter_ok" in out
    assert len(player.contents) > 0

    out_math = code_interpreter({"action": "math", "problem": "diff(x**4, x)"}, player=player)
    assert "4*x**3" in out_math

    out_artifact = code_interpreter({
        "action": "artifact",
        "content": "<div>Test</div>",
        "title": "Sample Canvas",
        "artifact_type": "html"
    }, player=player)
    assert "Interactive Artifact Created" in out_artifact


def test_clean_temp_files():
    res = clean_temp_files()
    assert "freed_display" in res
    assert "files_deleted" in res
    assert isinstance(res["categories"], dict)


def test_deep_system_scan():
    res = deep_system_scan()
    assert "hostname" in res
    assert "score" in res
    assert "grade" in res
    assert 0 <= res["score"] <= 100


def test_document_studio_converters():
    # Testing graceful handling when target file is missing
    missing_pdf = pdf_to_docx("/path/to/nonexistent/doc.pdf")
    assert "File not found" in missing_pdf

    missing_docx = docx_to_pdf("/path/to/nonexistent/doc.docx")
    assert "File not found" in missing_docx

    missing_edit = edit_pdf_text("/path/to/nonexistent/doc.pdf", "old", "new")
    assert "File not found" in missing_edit


def test_gemini_key_rotation(monkeypatch):
    # Test multi-key pool behavior with cleanup
    orig_pool = list(gemini._key_pool)
    orig_idx = gemini._key_idx
    orig_cached = gemini._cached_key
    try:
        gemini._key_pool = ["key_alpha", "key_beta", "key_gamma"]
        gemini._key_idx = 0
        gemini._cached_key = "key_alpha"

        assert gemini.has_alternative_keys() is True
        assert gemini.get_key_count() == 3

        rotated = gemini.rotate_api_key(reason="test_quota")
        assert rotated == "key_beta"
        assert gemini.get_key_index() == 1

        rotated_again = gemini.rotate_api_key(reason="test_quota_2")
        assert rotated_again == "key_gamma"
        assert gemini.get_key_index() == 2
    finally:
        gemini._key_pool = orig_pool
        gemini._key_idx = orig_idx
        gemini._cached_key = orig_cached
