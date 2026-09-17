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
5. Let the legend clear the data. `line_plot` grows an automatic y range one tick step at a time (a decade step on log axes) until the legend frame no longer covers any plotted point, re-deriving ticks each step so the 4--6 uniform label rule keeps holding. Pass `legend_clearance=False` to disable it. When `ylim` or `yticks` is explicit the range is left exactly as given and the collision is reported as a warning instead.
6. Use the calibrated geometry by default. Treat "box ratio" as the physical axes rectangle width:height, not the data aspect. The line-plot box is always exactly 4:3. Pass the user-selected contour ratio to `contour_plot(box_ratio=...)`. For linear axes without explicit limits, jointly choose outward-rounded limits and 4--6 uniformly spaced ticks that include both endpoints. For logarithmic axes, use positive outward-rounded limits and clean 1--2--5 or decade ticks. Preserve explicit limits and ticks exactly. Adapt other sizes only when the user requests another journal width, layout, or colorbar orientation.
7. Save both PNG and vector PDF unless the user requests one format. Do not manually guess crop boundaries. Clipping is handled automatically from the complete Matplotlib artist bounding box: the page grows by exactly the overflow while the axes box remains fixed, and the saved PNG must pass the blank-border check or export fails. Visually inspect only as a final spot check for scientific/layout errors.
8. When matching a supplied MATLAB PDF, read `references/calibration.md`, render both PDFs at the same DPI, compare page/axes/colorbar geometry, and report any remaining renderer-only differences.
9. Run `scripts/verify_pdf.py` on the final PDF when `pdfinfo` and `pdffonts` are available. Pass the page size the figure actually produced when checking an exact reference: wide tick labels legitimately widen the page past the nominal size, while the axes rectangle stays fixed. Only a *changed axes rectangle* indicates a real geometry regression.

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

The line axes box is always exactly 4:3; do not add a per-figure line ratio
control or infer a different ratio from the data.

Set `scale="semilogx"`, `scale="semilogy"`, or `scale="loglog"` for native
Matplotlib logarithmic axes. Pass the original positive data; never apply
`np.log`, `np.log10`, or another manual transform before calling `line_plot`.
Use `series_styles={label: {"marker": "s", "linestyle": "None"}}` for
per-series marker and line styling, and set `legend_loc=None` to omit a legend.

Use the analogous `contour_plot(x, y, z, box_ratio=(width, height), ...)`
function for filled contours. The ratio is required by the API to prevent an
unasked-for default. For example, pass `box_ratio=(4, 3)` only after the user
chooses 4:3. Read the function docstrings before adapting unusual inputs.

## Quality Rules

- Never let the legend cover a curve. `line_plot` widens an automatic y range until it does not; this is on by default (`legend_clearance=True`). Explicit `ylim`/`yticks` are still honoured exactly, so a collision there is only warned about -- drop the explicit range, or choose a different `legend_loc`, rather than leaving data hidden.
- Keep 4-6 uniformly spaced labeled major ticks on linear axes. Include both displayed endpoints and make `(upper_limit - lower_limit) / tick_interval` an integer. Use outward-rounded limits unless the user supplies limits or domain conventions require otherwise. On logarithmic axes, require positive data and prefer clean 1-2-5 ticks or decade ticks.
- Use dimensionless axis labels when the user supplies the normalization.
- Keep LaTeX enabled; do not silently fall back to MathText when exact typography matters.
- Use a symmetric diverging color scale for signed contour data unless the user specifies different limits.
- Keep line colors distinguishable in color and grayscale; preserve explicitly requested colors.
- Keep the axes rectangle, colorbar position, and font embedding verifiable in the exported PDF. The page size is a container, not a calibrated quantity: it may exceed the nominal size so that nothing is clipped.
- Never let ink touch the page edge. The module renders through the Agg backend for this reason as well: an interactive backend snaps the canvas to whole pixels and silently moves the page off-spec.
- Treat the automatic artist-bound measurement and saved-PNG border check as the clipping gate. Do not spend time manually segmenting the image to decide whether text was cut.

## Resources

- `scripts/matlab_style_plots.py`: calibrated plotting functions and runnable demos.
- `scripts/verify_pdf.py`: PDF page-size and embedded-font checks.
- `references/calibration.md`: measured line/contour geometry and typography details.
