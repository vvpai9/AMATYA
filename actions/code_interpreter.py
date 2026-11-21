"""
ChatGPT Code Interpreter & Claude Artifacts Engine for AMATYA.
Contributed by Aman Kumar (@iamTechieAman).

Provides:
1. Python Code Execution & Data Analysis (executing scripts, math calculations, Pandas dataframes).
2. Data Visualization & Auto-Plotting (Matplotlib charts saved to Desktop and rendered in HUD).
3. Symbolic Mathematics & Calculus Solver (SymPy step-by-step calculus, integrals, limits, algebra).
4. Claude-Style Interactive Artifacts & Canvas (HTML5/JS apps, SVG graphics, Mermaid architecture diagrams).
5. Dataset Explorer (CSV, Excel summary stats, correlation, and distribution).
"""

from __future__ import annotations

import csv
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

DESKTOP = Path.home() / "Desktop"
CHARTS_DIR = DESKTOP / "AMATYA_Charts"
ARTIFACTS_DIR = DESKTOP / "AMATYA_Artifacts"

for d in (CHARTS_DIR, ARTIFACTS_DIR):
    d.mkdir(parents=True, exist_ok=True)


def _get_python_executable() -> str:
    """Find the best Python executable (.venv, AMATYA venv, or system)."""
    base_dir = Path(__file__).resolve().parent.parent
    amatya_py = base_dir / "AMATYA" / "bin" / "python"
    if amatya_py.exists():
        return str(amatya_py)
    venv_py = base_dir / ".venv" / "bin" / "python"
    if venv_py.exists():
        return str(venv_py)
    return sys.executable


def execute_python_code(code: str, timeout: int = 30) -> dict:
    """
    Executes Python code in an isolated subprocess.
    Automatically captures stdout, stderr, and intercepts matplotlib plots to save as images.
    """
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    chart_dest = CHARTS_DIR / f"chart_{timestamp}.png"

    # Prepend headless matplotlib backend and auto-save interceptor if matplotlib is used
    wrapper_code = f"""
import sys
import os

# Auto-detect matplotlib and configure headless Agg backend
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    def _custom_show():
        plt.savefig(r"{chart_dest}", bbox_inches='tight', dpi=150)
        print(f"\\n[Plot saved: {chart_dest.name}]")

    plt.show = _custom_show
except Exception:
    pass

# Execute user code
{code}

# If a figure was created but show() was not called, save it automatically
try:
    import matplotlib.pyplot as plt
    if plt.get_fignums():
        plt.savefig(r"{chart_dest}", bbox_inches='tight', dpi=150)
        print(f"\\n[Plot saved: {chart_dest.name}]")
        plt.close('all')
except Exception:
    pass
"""

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(wrapper_code)
        temp_script = f.name

    py_exe = _get_python_executable()
    try:
        proc = subprocess.run(
            [py_exe, temp_script],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(DESKTOP),
        )
        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()
        has_chart = chart_dest.exists() and chart_dest.stat().st_size > 0

        # Open chart on desktop if created
        if has_chart:
            if sys.platform == "darwin":
                subprocess.run(["open", str(chart_dest)], timeout=3)
            elif sys.platform == "linux" and os.environ.get("DISPLAY"):
                subprocess.run(["xdg-open", str(chart_dest)], timeout=3, stderr=subprocess.DEVNULL)

        return {
            "success": proc.returncode == 0,
            "stdout": stdout,
            "stderr": stderr,
            "chart_path": str(chart_dest) if has_chart else None,
            "chart_name": chart_dest.name if has_chart else None,
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Execution timed out after {timeout} seconds.",
            "chart_path": None,
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(e),
            "chart_path": None,
        }
    finally:
        try:
            os.unlink(temp_script)
        except Exception:
            pass


def solve_symbolic_math(problem: str) -> dict:
    """
    Solves advanced calculus, algebra, derivatives, integrals, and limits using SymPy.
    """
    try:
        import sympy as sp
        x, y, z, t = sp.symbols('x y z t')

        # Clean problem string
        clean = problem.strip()
        # Derivative check (e.g. diff(sin(x)*x, x) or d/dx)
        if "diff(" in clean or "derivative" in clean.lower():
            expr_str = re.sub(r"(?i)derivative of|diff\(|\)", "", clean).strip()
            if "," in expr_str:
                parts = [p.strip() for p in expr_str.split(",")]
                expr = sp.sympify(parts[0])
                var = sp.Symbol(parts[1]) if len(parts) > 1 and parts[1] else x
                res = sp.diff(expr, var)
            else:
                expr = sp.sympify(expr_str)
                res = sp.diff(expr, x)
            latex_res = sp.latex(res)
            return {
                "operation": "Derivative (d/dx)",
                "expression": str(expr),
                "result": str(res),
                "latex": f"\\frac{{d}}{{dx}} \\left( {sp.latex(expr)} \\right) = {latex_res}",
            }

        # Integral check
        elif "integrate(" in clean or "integral" in clean.lower():
            expr_str = re.sub(r"(?i)integral of|integrate\(|\)", "", clean).strip()
            if "," in expr_str:
                parts = [p.strip() for p in expr_str.split(",")]
                expr = sp.sympify(parts[0])
                var = sp.Symbol(parts[1]) if len(parts) > 1 and parts[1] else x
                res = sp.integrate(expr, var)
            else:
                expr = sp.sympify(expr_str)
                res = sp.integrate(expr, x)
            latex_res = sp.latex(res)
            return {
                "operation": "Indefinite Integral (∫ dx)",
                "expression": str(expr),
                "result": str(res) + " + C",
                "latex": f"\\int \\left( {sp.latex(expr)} \\right) dx = {latex_res} + C",
            }

        # General equation or expression
        else:
            if "=" in clean:
                lhs_str, rhs_str = clean.split("=", 1)
                eq = sp.Eq(sp.sympify(lhs_str), sp.sympify(rhs_str))
                sol = sp.solve(eq)
                return {
                    "operation": "Solve Equation",
                    "expression": clean,
                    "result": str(sol),
                    "latex": f"{sp.latex(eq)} \\implies x = {sp.latex(sol)}",
                }
            else:
                expr = sp.sympify(clean)
                simplified = sp.simplify(expr)
                try:
                    num_val = float(simplified.evalf())
                except Exception:
                    num_val = None

                return {
                    "operation": "Simplify & Evaluate",
                    "expression": str(expr),
                    "result": str(simplified),
                    "decimal_approximation": num_val,
                    "latex": f"{sp.latex(expr)} = {sp.latex(simplified)}",
                }
    except ImportError:
        return {"error": "sympy is not installed. Install it with: pip install sympy"}
    except Exception as e:
        return {"error": f"Symbolic math error: {e}"}


def create_interactive_artifact(
    artifact_type: str,
    content: str,
    title: str = "Artifact"
) -> dict:
    """
    Creates Claude-style live interactive artifacts (HTML5 web apps, SVG, Mermaid charts, Markdown).
    Saves to Desktop and launches in browser for user interaction.
    """
    slug = re.sub(r"[^\w\-]", "_", title.lower()).strip("_") or "artifact"
    timestamp = time.strftime("%Y%m%d_%H%M%S")

    atype = artifact_type.lower().strip()
    if atype in ("html", "webapp", "js", "web", "canvas"):
        dest = ARTIFACTS_DIR / f"{slug}_{timestamp}.html"
        full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} — AMATYA Artifact</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      margin: 0; padding: 24px; background: #0c0e14; color: #e2e8f0;
      min-height: 100vh; display: flex; flex-direction: column; align-items: center;
    }}
    .artifact-card {{
      width: 100%; max-width: 900px; background: #161a23;
      border: 1px solid #2d3748; border-radius: 12px; padding: 24px;
      box-shadow: 0 10px 25px rgba(0,0,0,0.5);
    }}
    h1 {{ color: #6366f1; margin-top: 0; font-size: 20px; border-bottom: 1px solid #2d3748; padding-bottom: 12px; }}
  </style>
</head>
<body>
  <div class="artifact-card">
    <h1>🚀 {title}</h1>
    {content}
  </div>
</body>
</html>"""
        dest.write_text(full_html, encoding="utf-8")
        if sys.platform == "darwin":
            subprocess.run(["open", str(dest)], timeout=3)
        elif sys.platform == "linux" and os.environ.get("DISPLAY"):
            subprocess.run(["xdg-open", str(dest)], timeout=3, stderr=subprocess.DEVNULL)
        return {"file": str(dest), "url": f"file://{dest}", "type": "HTML Web App"}

    elif atype in ("mermaid", "diagram", "flowchart"):
        dest = ARTIFACTS_DIR / f"{slug}_{timestamp}.html"
        full_html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>{title} — Architecture Diagram</title>
  <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
  <script>mermaid.initialize({{startOnLoad:true, theme:'dark'}});</script>
  <style>
    body {{ font-family: sans-serif; background: #0f172a; color: #fff; padding: 30px; text-align: center; }}
    .diagram-box {{ background: #1e293b; padding: 30px; border-radius: 12px; display: inline-block; max-width: 95%; }}
  </style>
</head>
<body>
  <h2>📊 {title}</h2>
  <div class="diagram-box">
    <div class="mermaid">
{content}
    </div>
  </div>
</body>
</html>"""
        dest.write_text(full_html, encoding="utf-8")
        if sys.platform == "darwin":
            subprocess.run(["open", str(dest)], timeout=3)
        elif sys.platform == "linux" and os.environ.get("DISPLAY"):
            subprocess.run(["xdg-open", str(dest)], timeout=3, stderr=subprocess.DEVNULL)
        return {"file": str(dest), "url": f"file://{dest}", "type": "Mermaid Diagram"}

    elif atype in ("svg", "vector"):
        dest = ARTIFACTS_DIR / f"{slug}_{timestamp}.svg"
        dest.write_text(content, encoding="utf-8")
        if sys.platform == "darwin":
            subprocess.run(["open", str(dest)], timeout=3)
        elif sys.platform == "linux" and os.environ.get("DISPLAY"):
            subprocess.run(["xdg-open", str(dest)], timeout=3, stderr=subprocess.DEVNULL)
        return {"file": str(dest), "url": f"file://{dest}", "type": "SVG Vector"}

    else:
        dest = ARTIFACTS_DIR / f"{slug}_{timestamp}.md"
        dest.write_text(content, encoding="utf-8")
        return {"file": str(dest), "url": f"file://{dest}", "type": "Markdown Document"}


def analyze_dataset(file_path: str) -> dict:
    """
    Performs ChatGPT Code Interpreter style Pandas exploratory data analysis.
    """
    path = Path(file_path).expanduser().resolve()
    if not path.is_file():
        return {"error": f"File not found: {file_path}"}

    try:
        import pandas as pd
        if path.suffix.lower() == ".csv":
            df = pd.read_csv(path)
        else:
            df = pd.read_excel(path)

        summary = {
            "rows": int(df.shape[0]),
            "columns": int(df.shape[1]),
            "column_names": list(df.columns),
            "data_types": {col: str(dtype) for col, dtype in df.dtypes.items()},
            "missing_values": {col: int(cnt) for col, cnt in df.isnull().sum().items() if cnt > 0},
            "numerical_summary": df.describe().round(2).to_dict() if not df.select_dtypes(include='number').empty else {},
            "head": df.head(5).to_dict(orient="records"),
        }
        return summary
    except ImportError:
        if path.suffix.lower() == ".csv":
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                cols = reader.fieldnames or []
                return {
                    "rows": len(rows),
                    "columns": len(cols),
                    "column_names": cols,
                    "missing_values": {},
                    "numerical_summary": {},
                    "head": rows[:5],
                }
        return {"error": "pandas is required to analyze Excel files. Install it with: pip install pandas openpyxl"}
    except Exception as e:
        return {"error": f"Dataset analysis error: {e}"}


def code_interpreter(parameters: dict, player=None, session_memory=None) -> str:
    """Entry handler for code_interpreter."""
    action = parameters.get("action", "execute").lower().strip()
    code = parameters.get("code", "").strip()
    problem = parameters.get("problem", "").strip()
    file_path = parameters.get("file_path", "").strip()
    content = parameters.get("content", "").strip()
    title = parameters.get("title", "Interactive Artifact").strip()
    artifact_type = parameters.get("artifact_type", "html").strip()

    if player and hasattr(player, "write_log"):
        try:
            player.write_log(f"INTERPRETER: Executing action '{action}'...")
        except Exception:
            pass

    if action in ("execute", "run_code", "python", "calc", "calculate"):
        if not code:
            code = problem or content
        if not code:
            return "Please provide Python 'code' to execute."

        res = execute_python_code(code)
        lines = []
        if res["stdout"]:
            lines.append("```text\n" + res["stdout"] + "\n```")
        if res["stderr"]:
            lines.append("⚠️ **Errors / Warnings:**\n```text\n" + res["stderr"] + "\n```")
        if res["chart_path"]:
            lines.append(f"📊 **Chart Created & Displayed:** [{res['chart_name']}]({res['chart_path']})")

        out = "\n\n".join(lines) or "Code executed with no output."
        if player and hasattr(player, "show_content"):
            player.show_content("Code Interpreter Output", out)
        return out

    elif action in ("math", "solve_math", "calculus", "sympy"):
        query = problem or code or content
        if not query:
            return "Please provide a mathematical equation or expression in 'problem'."
        res = solve_symbolic_math(query)
        if "error" in res:
            return res["error"]

        report = f"""# 📐 Symbolic Mathematics & Calculus Solver
**Operation:** `{res.get('operation')}`  
**Problem:** `{res.get('expression')}`  
**Result:** **`{res.get('result')}`**  

### Formula (LaTeX):
$${res.get('latex')}$$
"""
        if "decimal_approximation" in res and res["decimal_approximation"] is not None:
            report += f"\n**Decimal Value:** `{res['decimal_approximation']}`"

        if player and hasattr(player, "show_content"):
            player.show_content("Math Solution", report)
        return report

    elif action in ("artifact", "canvas", "render_artifact", "create_artifact"):
        raw = content or code
        if not raw:
            return "Please provide HTML, SVG, or Mermaid 'content' for the artifact."
        res = create_interactive_artifact(artifact_type, raw, title)
        msg = f"🚀 **Claude-Style Interactive Artifact Created:**\n• **Title:** {title}\n• **Type:** {res['type']}\n• **Local File:** `{res['file']}`\n\n*The artifact has been saved and launched for exploration.*"
        if player and hasattr(player, "show_content"):
            player.show_content(f"Artifact: {title}", msg)
        return msg

    elif action in ("data_analysis", "dataset", "analyze_csv", "pandas"):
        if not file_path:
            return "Please provide 'file_path' of the CSV or Excel spreadsheet to analyze."
        res = analyze_dataset(file_path)
        if "error" in res:
            return res["error"]

        missing_str = chr(10).join(f"- **{k}**: {v} missing" for k, v in res['missing_values'].items()) if res['missing_values'] else "✅ No missing values detected."
        report = f"""# 📊 Exploratory Data Analysis: `{Path(file_path).name}`
• **Dataset Dimensions:** `{res['rows']} rows × {res['columns']} columns`  
• **Columns:** `{', '.join(res['column_names'][:15])}`  

### 🔍 Missing Values:
{missing_str}

### 📈 First 5 Sample Records:
```json
{json.dumps(res['head'], indent=2)[:1000]}
```
"""
        if player and hasattr(player, "show_content"):
            player.show_content("Data Analysis", report)
        return report

    return f"Code Interpreter action '{action}' completed."


TOOL = {
    "name": "code_interpreter",
    "description": (
        "ChatGPT Code Interpreter & Claude Artifacts Engine for AMATYA. "
        "Executes arbitrary Python code safely with standard data science libraries (Pandas, NumPy, SciPy), "
        "auto-generates and opens Matplotlib charts on Desktop/HUD, solves advanced symbolic calculus/math with SymPy, "
        "renders interactive Claude-style HTML5/JS canvas artifacts and Mermaid diagrams, and performs "
        "automated CSV/Excel exploratory data analysis."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "execute | math | artifact | data_analysis",
            },
            "code": {
                "type": "STRING",
                "description": "Python source code string to execute (with auto-plotting support)",
            },
            "problem": {
                "type": "STRING",
                "description": "Mathematical equation, integral, derivative, or algebraic expression to solve",
            },
            "file_path": {
                "type": "STRING",
                "description": "Path to CSV or Excel file for data_analysis",
            },
            "content": {
                "type": "STRING",
                "description": "HTML, SVG, or Mermaid markup for creating interactive artifacts",
            },
            "artifact_type": {
                "type": "STRING",
                "description": "html | mermaid | svg | markdown (default: html)",
            },
            "title": {
                "type": "STRING",
                "description": "Title for the interactive artifact or generated chart",
            }
        },
        "required": ["action"],
    },
    "handler": code_interpreter,
}
