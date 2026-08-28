"""
scripts/convert_notebooks.py
============================
Converts the .py analysis scripts in notebooks/ into proper Jupyter .ipynb
files with inline figure outputs, using nbformat (no jupytext required).

Each .py file is structured so that:
- Top-level docstrings become Markdown cells
- Triple-quoted strings (standalone, not assigned) become Markdown cells
- Everything else becomes Code cells

Run from project root:
    python scripts/convert_notebooks.py
"""

import sys
import re
import ast
import json
import subprocess
import base64
from pathlib import Path

import nbformat
from nbformat.v4 import new_notebook, new_markdown_cell, new_code_cell, new_output

ROOT = Path(__file__).resolve().parent.parent
NOTEBOOKS_DIR = ROOT / "notebooks"
FIGURES_DIR = ROOT / "data" / "processed" / "figures"

SCRIPTS = [
    "01_eda.py",
    "02_rfm_segmentation.py",
    "03_clv_prediction.py",
    "04_forecasting.py",
    "05_cohort_retention.py",
]

# Map each notebook to the figures it produces (in order)
NOTEBOOK_FIGURES = {
    "01_eda.py": [
        "01_monthly_revenue.png",
        "01b_day_of_week_revenue.png",
        "02a_top_products_revenue.png",
        "02b_top_countries.png",
        "03a_order_value_dist.png",
        "03b_order_frequency_dist.png",
    ],
    "02_rfm_segmentation.py": [
        "04_segment_sizes.png",
        "05_segment_revenue.png",
        "06_rfm_scatter.png",
        "07_rfm_heatmap.png",
    ],
    "03_clv_prediction.py": [
        "08_clv_by_segment.png",
        "09_feature_importance.png",
        "10_clv_actual_vs_predicted.png",
    ],
    "04_forecasting.py": [
        "11_revenue_forecast.png",
        "12_seasonal_decomposition.png",
        "13_seasonal_pattern.png",
    ],
    "05_cohort_retention.py": [
        "14_cohort_heatmap.png",
        "15_retention_curve.png",
        "16_cohort_sizes.png",
    ],
}


def png_to_output(png_path: Path) -> nbformat.NotebookNode:
    """Convert a PNG file to a Jupyter image output cell."""
    data = base64.b64encode(png_path.read_bytes()).decode("ascii")
    return new_output(
        output_type="display_data",
        data={"image/png": data, "text/plain": ["<Figure>"]},
        metadata={"image/png": {"width": 900}},
    )


def split_into_cells(source: str) -> list[dict]:
    """
    Parse a .py file into a list of (type, content) tuples.
    Rules:
    - Module-level docstring (first triple-quoted string) -> Markdown
    - Standalone triple-quoted strings (not assigned to anything) -> Markdown
    - Section comment blocks (lines starting with # ──) -> Markdown heading
    - Everything else -> Code
    """
    cells = []
    lines = source.splitlines(keepends=True)

    # ── Pass 1: extract module docstring ─────────────────────────────────────
    try:
        tree = ast.parse(source)
        first_node = tree.body[0] if tree.body else None
        if isinstance(first_node, ast.Expr) and isinstance(first_node.value, ast.Constant):
            doc = first_node.value.value
            # Convert the docstring to a markdown cell
            cells.append(("markdown", doc.strip()))
            # Find where docstring ends in source
            doc_end_line = first_node.end_lineno
            lines = lines[doc_end_line:]  # skip past docstring
    except Exception:
        pass

    # ── Pass 2: split remaining source into code/markdown blocks ─────────────
    remaining = "".join(lines)

    # Split on standalone triple-quoted strings and section markers
    # Strategy: find all standalone triple-quoted strings
    pattern = re.compile(
        r'(?m)^"""(.+?)"""',
        re.DOTALL,
    )

    last_end = 0
    for match in pattern.finditer(remaining):
        # Code before this string
        code_chunk = remaining[last_end:match.start()].strip()
        if code_chunk:
            cells.append(("code", code_chunk))

        # The triple-quoted string itself as markdown
        md_text = match.group(1).strip()
        if md_text:
            cells.append(("markdown", md_text))

        last_end = match.end()

    # Remaining code after last match
    tail = remaining[last_end:].strip()
    if tail:
        cells.append(("code", tail))

    return cells


def build_notebook(script_path: Path, figures: list[str]) -> nbformat.NotebookNode:
    source = script_path.read_text(encoding="utf-8")
    cells_raw = split_into_cells(source)

    nb_cells = []
    fig_idx = 0  # pointer into figures list

    for cell_type, content in cells_raw:
        if cell_type == "markdown":
            nb_cells.append(new_markdown_cell(content))
        else:
            # Create code cell
            code_cell = new_code_cell(content)

            # Attach figure outputs if this code block saves a figure
            outputs = []
            while fig_idx < len(figures) and f'"{figures[fig_idx]}"' in content:
                fig_path = FIGURES_DIR / figures[fig_idx]
                if fig_path.exists():
                    outputs.append(png_to_output(fig_path))
                fig_idx += 1

            code_cell["outputs"] = outputs
            nb_cells.append(code_cell)

    nb = new_notebook(cells=nb_cells)
    nb.metadata["kernelspec"] = {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }
    nb.metadata["language_info"] = {
        "name": "python",
        "version": "3.14.2",
    }
    return nb


def main():
    print(f"Converting {len(SCRIPTS)} scripts to .ipynb ...")
    for script_name in SCRIPTS:
        script_path = NOTEBOOKS_DIR / script_name
        if not script_path.exists():
            print(f"  SKIP (not found): {script_name}")
            continue

        figures = NOTEBOOK_FIGURES.get(script_name, [])
        nb = build_notebook(script_path, figures)

        out_name = script_name.replace(".py", ".ipynb")
        out_path = NOTEBOOKS_DIR / out_name
        nbformat.write(nb, out_path)
        print(f"  Written: {out_name}  ({len(nb.cells)} cells, {len(figures)} figures)")

    print("\nDone. Open any .ipynb in Jupyter or VS Code to view rendered notebooks.")


if __name__ == "__main__":
    main()
