---
name: plot-matlab-style
description: Create and revise publication-ready Python/Matplotlib linear, semilog, loglog, and filled contour plots using the user's calibrated MATLAB style, including LaTeX-rendered text, exact page and axes geometry, MATLAB colors, RdBu_r contours, colorbars, PNG/PDF export, and rendered comparison against MATLAB PDFs. Use automatically when the user asks in natural language to use Python to draw a line plot, curve plot, 折线图, 线图, semilog plot, loglog plot, contour, contourf, 等高线图, or 云图; to reproduce a MATLAB figure or plotting style; or to make a publication-quality scientific plot with LaTeX, even when the user does not mention this skill. Do not use for generic data analysis without a plotting request or when the user explicitly requires a non-Matplotlib plotting stack.
---

# Plot MATLAB Style

Create line and filled-contour figures with the calibrated style while preserving the user's data and scientific meaning.

## Workflow

1. Identify the requested plot type, linear/semilog/loglog axis scale, input data, labels, limits, ticks, legend, color scale, and output formats. Infer harmless defaults; ask only when a missing choice would materially change the scientific meaning.
2. Check that Python can import NumPy and Matplotlib and that `latex`, `dvipng`, and Ghostscript are available. Prefer the existing `pythonlineplot` Conda environment when present.
3. Use `scripts/matlab_style_plots.py` instead of recreating style constants. Import its `line_plot` or `contour_plot` function from a small project-local driver script. Copy the module into the project only when portable source code is required.
4. Preserve supplied data. Never substitute the bundled demo data into a real request.
5. Use the calibrated geometry by default, but choose page size and font size from the figure's final display size in the manuscript. Before exporting, determine the intended LaTeX insertion width, such as `0.45\linewidth`, `0.5\linewidth`, or `0.8\linewidth`. The apparent manuscript font is approximately `source_font_size * inserted_width / natural_pdf_width`. Choose either (a) a natural PDF width close to the intended inserted width with 9--10 pt source fonts, or (b) a larger natural PDF width with proportionally larger source fonts. For example, a 390 pt wide PDF inserted at about 216 pt would need roughly 18 pt source fonts to appear exactly 10 pt in the paper, but dense half-width plots often need a practical compromise around 14--16 pt source fonts to avoid tick-label and legend crowding. For linear axes without explicit limits, jointly choose outward-rounded limits and 4--6 uniformly spaced ticks that include both endpoints. For logarithmic axes, use positive outward-rounded limits and clean 1--2--5 or decade ticks. Preserve explicit limits and ticks exactly. Adapt sizes only when the user requests another journal width, aspect ratio, layout, colorbar orientation, or final insertion width.
6. Save both PNG and vector PDF unless the user requests one format. Render the PDF at 300 dpi and visually inspect the latest result for clipping, seams, illegible labels, incorrect limits, or misplaced annotations.
7. When matching a supplied MATLAB PDF, read `references/calibration.md`, render both PDFs at the same DPI, compare page/axes/colorbar geometry, and report any remaining renderer-only differences.
8. Run `scripts/verify_pdf.py` on the final PDF when `pdfinfo` and `pdffonts` are available.

## Quick Use

```python
from pathlib import Path
import sys

skill_scripts = Path.home() / ".codex/skills/plot-matlab-style/scripts"
sys.path.insert(0, str(skill_scripts))

from matlab_style_plots import line_plot

line_plot(
    x,
    {r"$y=x$": y1, r"$y=x^2$": y2},
    output_prefix="output/my_line_plot",
    xlabel=r"$x/L$",
    ylabel=r"$y/L$",
    xlim=(0, 1),
    ylim=(0, 1),
    scale="linear",
)
```

Set `scale="semilogx"`, `scale="semilogy"`, or `scale="loglog"` for native
Matplotlib logarithmic axes. Pass the original positive data; never apply
`np.log`, `np.log10`, or another manual transform before calling `line_plot`.
Use `series_styles={label: {"marker": "s", "linestyle": "None"}}` for
per-series marker and line styling, and set `legend_loc=None` to omit a legend.

Use the analogous `contour_plot(x, y, z, ...)` function for filled contours. Read the function docstrings before adapting unusual inputs.

## Quality Rules

- Keep 4-6 uniformly spaced labeled major ticks on linear axes. Include both displayed endpoints and make `(upper_limit - lower_limit) / tick_interval` an integer. Use outward-rounded limits unless the user supplies limits or domain conventions require otherwise. On logarithmic axes, require positive data and prefer clean 1-2-5 ticks or decade ticks.
- Match font size to the final manuscript display, not merely to the source PDF. For paper figures, the rendered axis labels, tick labels, legends, and annotations should usually appear about 9--10 pt after `\includegraphics` scaling. Use one font size within each figure unless the user explicitly asks for hierarchy. If a figure will be inserted at about half page width, increase the source font or reduce the natural PDF width so that the final apparent font is not compressed to 5--6 pt.
- Use dimensionless axis labels when the user supplies the normalization.
- Keep LaTeX enabled; do not silently fall back to MathText when exact typography matters.
- Use a symmetric diverging color scale for signed contour data unless the user specifies different limits.
- Keep line colors distinguishable in color and grayscale; preserve explicitly requested colors.
- Keep page size, axes position, colorbar position, and font embedding verifiable in the exported PDF.

## Resources

- `scripts/matlab_style_plots.py`: calibrated plotting functions and runnable demos.
- `scripts/verify_pdf.py`: PDF page-size and embedded-font checks.
- `references/calibration.md`: measured line/contour geometry and typography details.
