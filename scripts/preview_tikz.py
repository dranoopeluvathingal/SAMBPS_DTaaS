"""
preview_tikz.py
---------------
Local TikZ figure preview helper for VS Code / Jupyter.

Workflow:
  1. Write your standalone .tex figure file
  2. Run: python scripts/preview_tikz.py path/to/figure.tex
  3. Two outputs are produced every time:
       figure_preview.png      — clean image (no grid)
       figure_grid.png         — grid + coordinate markers (layout reference)
  4. The clean PDF is also kept alongside the .tex file.

Requirements:
  pip install matplotlib pillow
  sudo apt-get install texlive-latex-extra texlive-pictures pdf2svg poppler-utils
"""

import subprocess
import sys
import os
import re
import math
import shutil
import tempfile
from pathlib import Path


PREAMBLE_INJECT = r"\input{thesis_figure_definitions}"


# =============================================================================
# STANDALONE WRAPPER
# =============================================================================

def wrap_in_standalone(tex_content: str) -> str:
    """Ensure the content is wrapped in a standalone document."""
    if r"\documentclass" in tex_content:
        return tex_content
    return (
        r"\documentclass[border=10pt]{standalone}" + "\n"
        + PREAMBLE_INJECT + "\n"
        + r"\begin{document}" + "\n"
        + tex_content + "\n"
        + r"\end{document}"
    )


# =============================================================================
# GRID OVERLAY HELPERS
# =============================================================================

def _detect_bbox(tex_content: str):
    """
    Scan for all explicit (x, y) numeric coordinate pairs in the source.
    Returns (xmin, ymin, xmax, ymax) with a small margin.
    """
    coords = re.findall(
        r'\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)',
        tex_content
    )
    if not coords:
        return -1.0, -7.0, 25.0, 7.0
    xs = [float(x) for x, _ in coords]
    ys = [float(y) for _, y in coords]
    margin = 1.5
    return min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin


def _extract_coords(tex_content: str):
    """Return sorted list of unique (x, y) numeric pairs found in the source."""
    raw = re.findall(
        r'\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)',
        tex_content
    )
    return sorted({(float(x), float(y)) for x, y in raw})


def _build_grid_overlay(xmin, ymin, xmax, ymax, coords) -> str:
    """
    Return TikZ code that draws:
      • light 1-unit grid
      • bolder 5-unit grid
      • x / y axis tick labels
      • small red dot + label at every explicit coordinate
    """
    xi0 = int(math.floor(xmin))
    xi1 = int(math.ceil(xmax))
    yi0 = int(math.floor(ymin))
    yi1 = int(math.ceil(ymax))

    lines = [
        r"% ---- GRID OVERLAY (auto-injected by preview_tikz.py) ----",
        r"\begin{scope}[on background layer]",
        f"\\draw[gray!18, very thin, step=1] ({xi0},{yi0}) grid ({xi1},{yi1});",
        f"\\draw[gray!40, thin, step=5] ({xi0},{yi0}) grid ({xi1},{yi1});",
        r"\end{scope}",
        r"% axis tick labels",
    ]

    for x in range(xi0, xi1 + 1):
        lines.append(
            f"\\node[font=\\fontsize{{4}}{{4}}\\selectfont\\sffamily, gray, below]"
            f" at ({x},{yi0-0.3}) {{{x}}};"
        )
    for y in range(yi0, yi1 + 1):
        lines.append(
            f"\\node[font=\\fontsize{{4}}{{4}}\\selectfont\\sffamily, gray, left]"
            f" at ({xi0-0.3},{y}) {{{y}}};"
        )

    # coordinate markers
    lines.append(r"% coordinate markers")
    for x, y in coords:
        label = f"({x:g},{y:g})"
        lines += [
            f"\\fill[red!70] ({x},{y}) circle (1.8pt);",
            f"\\node[font=\\fontsize{{3.5}}{{3.5}}\\selectfont\\sffamily,"
            f" red!80, above right, inner sep=0.3pt] at ({x},{y}) {{{label}}};",
        ]

    lines.append(r"% ---- END GRID OVERLAY ----")
    return "\n".join(lines)


def _inject_grid(tex_content: str, overlay: str) -> str:
    """Insert overlay code just before the last \\end{tikzpicture}."""
    marker = r"\end{tikzpicture}"
    idx = tex_content.rfind(marker)
    if idx == -1:
        return tex_content          # nothing to inject into
    return tex_content[:idx] + overlay + "\n" + tex_content[idx:]


# =============================================================================
# COMPILATION
# =============================================================================

def _copy_defs(tex_path: Path, work_dir: Path):
    """Copy thesis_figure_definitions.tex into the work directory."""
    defs_src = tex_path.parent / "thesis_figure_definitions.tex"
    if not defs_src.exists():
        defs_src = (
            Path(__file__).parent.parent
            / "overleaf_template"
            / "thesis_figure_definitions.tex"
        )
    if defs_src.exists():
        shutil.copy(defs_src, work_dir / "thesis_figure_definitions.tex")


def _run_pdflatex(tex_file: Path, work_dir: Path) -> Path:
    """Run pdflatex; return path to PDF or raise on failure."""
    result = subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", tex_file.name],
        cwd=work_dir,
        capture_output=True,
        text=True,
    )
    pdf = work_dir / tex_file.with_suffix(".pdf").name
    if not pdf.exists():
        print("--- LaTeX Error Log ---")
        print(result.stdout[-3000:])
        raise RuntimeError("PDF compilation failed. See log above.")
    return pdf


def _pdf_to_png(pdf: Path, out_png: Path, dpi: int = 200):
    """Convert first page of PDF to PNG via pdftoppm."""
    tmp_base = pdf.parent / "out"
    subprocess.run(
        ["pdftoppm", "-r", str(dpi), "-png", str(pdf), str(tmp_base)],
        capture_output=True,
    )
    pngs = sorted(pdf.parent.glob("out*.png"))
    if not pngs:
        raise RuntimeError("PNG conversion failed. Is poppler-utils installed?")
    shutil.copy(pngs[0], out_png)


def compile_tex(tex_path: str, output_dir: str = None) -> str:
    """
    Compile a .tex file to a clean PNG (no grid).
    Returns path to the generated PNG.
    """
    tex_path = Path(tex_path).resolve()
    if not tex_path.exists():
        raise FileNotFoundError(f"File not found: {tex_path}")

    work_dir = Path(tempfile.mkdtemp())
    tex_file = work_dir / tex_path.name

    content = wrap_in_standalone(tex_path.read_text())
    tex_file.write_text(content)
    _copy_defs(tex_path, work_dir)

    pdf = _run_pdflatex(tex_file, work_dir)

    # also copy PDF to output location
    out_dir = Path(output_dir) if output_dir else tex_path.parent
    out_pdf = out_dir / (tex_path.stem + ".pdf")
    shutil.copy(pdf, out_pdf)

    out_png = out_dir / (tex_path.stem + "_preview.png")
    _pdf_to_png(pdf, out_png)

    shutil.rmtree(work_dir)
    return str(out_png)


def compile_tex_grid(tex_path: str, output_dir: str = None) -> str:
    """
    Compile a .tex file with grid + coordinate markers overlaid.
    Returns path to the generated *_grid.png.
    """
    tex_path = Path(tex_path).resolve()
    if not tex_path.exists():
        raise FileNotFoundError(f"File not found: {tex_path}")

    raw_content = tex_path.read_text()

    # build overlay from the RAW source (before standalone wrapping)
    bbox = _detect_bbox(raw_content)
    coords = _extract_coords(raw_content)
    overlay = _build_grid_overlay(*bbox, coords)

    # inject into the tikzpicture, then wrap
    content_with_grid = _inject_grid(raw_content, overlay)
    content_with_grid = wrap_in_standalone(content_with_grid)

    work_dir = Path(tempfile.mkdtemp())
    tex_file = work_dir / tex_path.name
    tex_file.write_text(content_with_grid)
    _copy_defs(tex_path, work_dir)

    pdf = _run_pdflatex(tex_file, work_dir)

    out_dir = Path(output_dir) if output_dir else tex_path.parent
    out_png = out_dir / (tex_path.stem + "_grid.png")
    _pdf_to_png(pdf, out_png, dpi=250)   # higher DPI for readability of labels

    shutil.rmtree(work_dir)
    return str(out_png)


# =============================================================================
# DISPLAY
# =============================================================================

def show_inline(png_path: str, figsize=(16, 10)):
    """Display PNG inline in Jupyter, or open in VS Code / system viewer."""
    try:
        from IPython.display import Image, display
        display(Image(filename=png_path))
        print(f"Preview: {png_path}")
        return
    except ImportError:
        pass

    try:
        import matplotlib.pyplot as plt
        import matplotlib.image as mpimg
        img = mpimg.imread(png_path)
        plt.figure(figsize=figsize)
        plt.imshow(img)
        plt.axis("off")
        plt.tight_layout()
        plt.show()
        return
    except ImportError:
        pass

    for cmd in [["code", png_path], ["xdg-open", png_path], ["open", png_path]]:
        try:
            subprocess.Popen(cmd)
            print(f"Opened in viewer: {png_path}")
            return
        except FileNotFoundError:
            continue
    print(f"Preview saved to: {png_path}")


# =============================================================================
# PUBLIC API
# =============================================================================

def preview(tex_path: str, figsize=(16, 10)):
    """
    Compile a figure and produce TWO outputs:
      *_preview.png  — clean image shown to viewer
      *_grid.png     — grid + coordinate markers (stored for layout reference)
    Also writes a clean PDF alongside the .tex file.

    Usage in Jupyter:  from scripts.preview_tikz import preview; preview("figure.tex")
    Usage in terminal: python scripts/preview_tikz.py figure.tex
    """
    print(f"Compiling {tex_path} ...")
    clean_png = compile_tex(tex_path)
    print(f"  Clean  → {clean_png}")

    print(f"Compiling grid version ...")
    grid_png = compile_tex_grid(tex_path)
    print(f"  Grid   → {grid_png}")

    print("Displaying grid version (use clean PNG for thesis):")
    show_inline(grid_png, figsize=figsize)
    return clean_png, grid_png


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python preview_tikz.py <path/to/figure.tex>")
        sys.exit(1)
    preview(sys.argv[1])
