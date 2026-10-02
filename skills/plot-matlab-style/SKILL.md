---
name: plot-matlab-style
description: Create and revise publication-ready Python/Matplotlib linear, semilog, loglog, and filled contour plots using the user's calibrated MATLAB style, including LaTeX-rendered text, exact page and axes geometry, MATLAB colors, RdBu_r contours, colorbars, PNG/PDF export, and rendered comparison against MATLAB PDFs. Use automatically when the user asks in natural language to use Python to draw a line plot, curve plot, 折线图, 线图, semilog plot, loglog plot, contour, contourf, 等高线图, or 云图; to reproduce a MATLAB figure or plotting style; or to make a publication-quality scientific plot with LaTeX, even when the user does not mention this skill. Do not use for generic data analysis without a plotting request or when the user explicitly requires a non-Matplotlib plotting stack.
---

# Plot MATLAB Style

Create line and filled-contour figures with the calibrated style while preserving the user's data and scientific meaning.

## Workflow

1. Identify the requested plot type, linear/semilog/loglog axis scale, input data, labels, limits, ticks, legend, color scale, and output formats. For every line plot, use an axes-box width:height ratio of exactly 4:3. For every contour plot, if the user has not already supplied the axes-box ratio, ask them for it before drawing; do not infer a contour ratio from the data or a reference image. Infer other harmless defaults; ask only when a missing choice would materially change the scientific meaning.
2. Check that Python can import NumPy and Matplotlib and that `latex`, `dvipng`, and Ghostscript are available. Prefer the existing `pythonlineplot` Conda environment when present.
3. Use `scripts/matlab_style_plots.py` instead of recreating style constants. Import its `line_plot` or `contour_plot` function from a small project-local driver script. Copy the module into the project only when portable source code is required.
4. Preserve supplied data. Never substitute the bundled demo data into a real request.
5. Use the calibrated geometry by default. Treat "box ratio" as the physical axes rectangle width:height, not the data aspect. The line-plot box is a non-negotiable 4:3. Pass the user-selected contour ratio to `contour_plot(box_ratio=...)`. For linear axes without explicit limits, jointly choose outward-rounded limits and 4--6 uniformly spaced ticks that include both endpoints. For logarithmic axes, use positive outward-rounded limits and clean 1--2--5 or decade ticks. Preserve explicit limits and ticks exactly. Adapt other sizes only when the user requests another journal width, layout, or colorbar orientation. Use the automatic panel-label placement described below; do not override it with fixed coordinates.
6. Save both PNG and vector PDF unless the user requests one format. Keep `auto_crop=True` and at least 6 pt of padding by default. This uses Matplotlib's complete artist bounding box and an automatic border check/retry so tick labels, axis labels, legends, annotations, and colorbar titles are not cut off. Do not spend time manually deciding crop boundaries; visually inspect only as a final spot check for scientific/layout errors. Use `auto_crop=False` only when exact fixed-page dimensions are required for MATLAB-reference matching, and then explicitly verify that every label remains inside the fixed canvas.
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
    annotation="(a)",
)
```

The line axes box is always exactly 4:3. Do not add a line-plot ratio control
or infer a different ratio from the data.

Set `scale="semilogx"`, `scale="semilogy"`, or `scale="loglog"` for native
Matplotlib logarithmic axes. Pass the original positive data; never apply
`np.log`, `np.log10`, or another manual transform before calling `line_plot`.
Use `series_styles={label: {"marker": "s", "linestyle": "None"}}` for
per-series marker and line styling, and set `legend_loc=None` to omit a legend.

Use the analogous `contour_plot(x, y, z, box_ratio=(width, height), ...)`
function for filled contours. The ratio is required by the API to prevent an
unasked-for default. For example, pass `box_ratio=(4, 3)` only after the user
chooses 4:3. Read the function docstrings before adapting unusual inputs.

## Panel labels

`line_plot` and `contour_plot` automatically place the supplied `annotation`
(default `"(a)"`); pass `"(b)"` or any other label as needed. `annotation=None`
adds no label. Labels use the existing LaTeX serif font at **16.5 pt**, with
`ha="center"` and `va="center"`.

- **Lines:** the label's horizontal center aligns with the **left edge of
  the y-axis label bounding box**; its vertical center aligns with the
  **top edge of the axes bounding box**.
- **Contours with a colorbar:** use the same horizontal reference, but
  align the vertical center with the **top edge of the colorbar's top-title
  bounding box**. This reference is the title above the colorbar, never the
  y-axis label or colorbar tick labels. For a standalone contour without a
  colorbar, the helper uses the axes' top edge.

The implementation completes `fig.canvas.draw()`, obtains actual bounding
boxes through the renderer, and converts their display coordinates with
`fig.transFigure.inverted()`. Set all labels, ticks and final layout before
adding the label; rerun placement if the layout changes. Do not use fixed
pixel offsets or estimated text heights. Artist-aware cropping includes the
entire label even if its center lies outside the original canvas, and keeps
the existing blank padding and border verification.

For a **native multi-panel contour figure**, call
`add_panel_label(fig, first_ax, annotation, colorbar_title=upper_cbar.ax.title)`
after finalizing the layout. Use the first panel's ylabel for x and the
upper row colorbar's top title for y. Renderer coordinates already include
panel offsets in the full figure. Pass the title Text, not `cbar.ax.yaxis.label`.

For a **raster stitched contour figure**, use `save_labeled_composite` from
the same module. Supply the canvas, output prefix, the first panel's
`reference_ax`, the upper colorbar's `colorbar_title` Text, and
`first_axes_top_left` (actual axes-box top-left in canvas pixels). When the
title comes from another panel, also supply its main `title_reference_ax`
and `title_axes_top_left`. These open reference figures must reproduce the
actual source labels, ticks and axes geometry. The helper measures each
reference after draw, converts the measured offsets to the composite DPI,
adds each panel's placement offset, flips the canvas y direction, and then
converts to figure coordinates. It exports PNG/PDF with the existing crop
and padding rules. Use `annotation=None` on constituent panels so the
composite receives only its requested label.

## Quality Rules

- Never let the legend cover a curve. `line_plot` widens an automatic y range until it does not; this is on by default (`legend_clearance=True`). Explicit `ylim`/`yticks` are still honoured exactly, so a collision there is only warned about -- drop the explicit range, or choose a different `legend_loc`, rather than leaving data hidden.
- Keep 4-6 uniformly spaced labeled major ticks on linear axes. Include both displayed endpoints and make `(upper_limit - lower_limit) / tick_interval` an integer. Use outward-rounded limits unless the user supplies limits or domain conventions require otherwise. On logarithmic axes, require positive data and prefer clean 1-2-5 ticks or decade ticks.
- Use dimensionless axis labels when the user supplies the normalization.
- Keep LaTeX enabled; do not silently fall back to MathText when exact typography matters.
- Use a symmetric diverging color scale for signed contour data unless the user specifies different limits.
- Keep line colors distinguishable in color and grayscale; preserve explicitly requested colors.
- Use the Agg backend for file exports so interactive canvas pixel rounding does not change physical geometry.
- Keep page size, axes position, colorbar position, and font embedding verifiable in the exported PDF.
- Prefer automatic artist-aware cropping with padding and border validation over manual pixel-based crop inspection. A successful default export must have a blank outer raster border; if the exporter cannot establish one after its retries, treat that as an error rather than delivering a possibly clipped figure.

## Resources

- `scripts/matlab_style_plots.py`: calibrated plotting functions and runnable demos.
- `scripts/verify_pdf.py`: PDF page-size and embedded-font checks.
- `scripts/verify_panel_labels.py`: generates line, contour and composite PNG/PDF examples and checks measured alignment, label typography, omission and crop margins.
- `references/calibration.md`: measured line/contour geometry and typography details.
