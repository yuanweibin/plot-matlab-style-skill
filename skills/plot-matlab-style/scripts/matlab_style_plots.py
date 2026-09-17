#!/usr/bin/env python3
"""Calibrated Matplotlib line and filled-contour plots.

The functions save PNG and PDF outputs directly so LaTeX rendering happens
inside the calibrated rc context. Run this file with ``--demo both`` for a
smoke test.
"""

from __future__ import annotations

import argparse
import shutil
import warnings
from collections.abc import Mapping, Sequence
from pathlib import Path

import matplotlib
import numpy as np

# These functions only ever write files, and an interactive backend silently
# breaks the one thing this style guarantees.  A real window snaps the canvas to
# whole pixels at the figure dpi, so macosx turns a requested 368 x 299 pt page
# into 367.92 x 298.8 -- off-spec before a single curve is drawn.  Agg keeps the
# requested size exactly, through set_size_inches and through both savefig calls.
matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import NullFormatter, StrMethodFormatter  # noqa: E402


MATLAB_DARK_GRAY = "#262626"
MATLAB_LINE_COLORS = (
    "#0072BD",
    "#D95319",
    "#EDB120",
    "#7E2F8E",
    "#77AC30",
    "#4DBEEE",
    "#A2142F",
)

LINE_SCALE_METHODS = {
    "linear": ("linear", "linear", "plot"),
    "semilogx": ("log", "linear", "semilogx"),
    "semilogy": ("linear", "log", "semilogy"),
    "loglog": ("log", "log", "loglog"),
}

LINE_PAGE_PT = (368.0, 299.0)
LINE_AXES_PT = (52.0, 47.5, 310.0, 310.0 * 3.0 / 4.0)

CONTOUR_PAGE_PT = (370.0, 308.0)
CONTOUR_AXES_FRAME_PT = (51.5, 49.5, 263.5, 231.0)
CONTOUR_CBAR_PT = (332.0, 49.5, 16.0, 231.0)

PUBLICATION_RC = {
    "text.usetex": True,
    "font.family": "serif",
    "font.size": 16,
    "axes.labelsize": 18,
    "axes.linewidth": 2 / 3,
    "axes.edgecolor": MATLAB_DARK_GRAY,
    "axes.labelcolor": MATLAB_DARK_GRAY,
    "lines.linewidth": 1,
    "lines.markersize": 4,
    "lines.solid_capstyle": "butt",
    "xtick.direction": "in",
    "ytick.direction": "in",
    "xtick.top": True,
    "ytick.right": True,
    "xtick.color": MATLAB_DARK_GRAY,
    "ytick.color": MATLAB_DARK_GRAY,
    "xtick.labelsize": 16,
    "ytick.labelsize": 16,
    "xtick.major.size": 3.1,
    "ytick.major.size": 3.1,
    "xtick.major.width": 2 / 3,
    "ytick.major.width": 2 / 3,
    "xtick.major.pad": 7.75,
    "ytick.major.pad": 6,
    "legend.fontsize": 14.4,
    "savefig.facecolor": "white",
    "pdf.fonttype": 42,
}


def require_latex_tools() -> None:
    """Raise a clear error when Matplotlib's external LaTeX chain is missing."""

    required = ("latex", "dvipng", "gs")
    missing = [command for command in required if shutil.which(command) is None]
    if missing:
        raise RuntimeError(
            "External LaTeX rendering requires these commands: "
            + ", ".join(missing)
        )


def _normalized_bounds(bounds_pt: Sequence[float], page_pt: Sequence[float]):
    left, bottom, width, height = bounds_pt
    page_width, page_height = page_pt
    return (
        left / page_width,
        bottom / page_height,
        width / page_width,
        height / page_height,
    )


def _box_ratio_value(box_ratio: float | Sequence[float]) -> float:
    """Normalize a physical axes-box width:height ratio."""

    if np.isscalar(box_ratio):
        ratio = float(box_ratio)
    else:
        values = tuple(float(value) for value in box_ratio)
        if len(values) != 2:
            raise ValueError("box_ratio must be a number or (width, height)")
        width, height = values
        if width <= 0 or height <= 0:
            raise ValueError("box_ratio width and height must be positive")
        ratio = width / height
    if not np.isfinite(ratio) or ratio <= 0:
        raise ValueError("box_ratio must be positive and finite")
    return ratio


def _fit_box_ratio(
    frame_pt: Sequence[float], box_ratio: float | Sequence[float]
) -> tuple[float, float, float, float]:
    """Fit an exact width:height axes box inside a calibrated frame."""

    left, bottom, frame_width, frame_height = map(float, frame_pt)
    ratio = _box_ratio_value(box_ratio)
    if frame_width / frame_height > ratio:
        height = frame_height
        width = height * ratio
    else:
        width = frame_width
        height = width / ratio
    return (
        left + (frame_width - width) / 2.0,
        bottom + (frame_height - height) / 2.0,
        width,
        height,
    )


_FIT_SLACK_PT = 1.0
"""Minimum clearance demanded between the outermost ink and the page edge.

Without it a label whose extent lands exactly on the boundary is antialiased
against nothing and reads as shaved.
"""


def _renderer(fig):
    fig.canvas.draw()
    try:
        return fig.canvas.get_renderer()
    except AttributeError:
        from matplotlib.backends.backend_agg import FigureCanvasAgg

        return FigureCanvasAgg(fig).get_renderer()


def _expand_page_to_fit(fig, boxes_pt, page_pt, annotation_artist=None):
    """Grow the page until nothing is clipped, keeping the axes rectangles fixed.

    What this style calibrates is the axes rectangle and the typography, not the
    page: the reference page leaves only 368 - (52 + 310) = 6 pt to the right of
    the axes and 52 pt to its left.  That is enough for the calibration content,
    whose tick labels are as short as "1" and "0.5".  Real data is not so
    convenient -- "0.15" on the y axis needs about 26 pt plus the tick pad and
    the rotated y-label, and a final x tick of "25" overhangs its centre by more
    than 6 pt -- so the y-label and the last x tick label were being cut off.

    Shrinking the axes to make room would silently break the calibrated
    geometry, so instead the page grows by exactly the overflow and each axes
    rectangle keeps its size in points, shifted to stay in the same place
    relative to the data.  Everything is a pure translation at fixed font size,
    so one measurement suffices; no iteration is needed.

    A figure that already fits with ``_FIT_SLACK_PT`` to spare is left alone,
    which keeps the reference demos byte-comparable.

    Returns the page size in points actually used.
    """
    page_width, page_height = page_pt

    # Restate the calibrated size before measuring against it, so the helper is
    # correct whatever size the figure was actually created at.  The module
    # forces Agg for this reason too; under an interactive backend a new canvas
    # is snapped to whole pixels and the page silently drifts off-spec.
    fig.set_size_inches(page_width / 72.0, page_height / 72.0)

    bbox = fig.get_tightbbox(_renderer(fig))
    if bbox is None:
        return page_pt

    left = max(0.0, _FIT_SLACK_PT - bbox.x0 * 72.0)
    bottom = max(0.0, _FIT_SLACK_PT - bbox.y0 * 72.0)
    right = max(0.0, bbox.x1 * 72.0 - (page_width - _FIT_SLACK_PT))
    top = max(0.0, bbox.y1 * 72.0 - (page_height - _FIT_SLACK_PT))
    if max(left, bottom, right, top) <= 0.0:
        return page_pt

    new_width = page_width + left + right
    new_height = page_height + bottom + top
    fig.set_size_inches(new_width / 72.0, new_height / 72.0)
    for axes, bounds in boxes_pt:
        box_left, box_bottom, box_width, box_height = bounds
        axes.set_position(
            _normalized_bounds(
                (box_left + left, box_bottom + bottom, box_width, box_height),
                (new_width, new_height),
            )
        )
    if annotation_artist is not None:
        # The annotation marks the page corner, so it follows the new corner.
        annotation_artist.set_position((1 / new_width, 1 - 2.75 / new_height))
    return (new_width, new_height)


def _output_prefix(value: str | Path) -> Path:
    prefix = Path(value).expanduser()
    if prefix.suffix.lower() in {".png", ".pdf"}:
        prefix = prefix.with_suffix("")
    prefix.parent.mkdir(parents=True, exist_ok=True)
    return prefix


def _png_has_clear_border(path: Path, border_px: int = 2) -> bool:
    """Return whether the outer PNG pixels are blank white canvas."""

    image = plt.imread(path)
    if (
        image.ndim != 3
        or image.shape[0] < 2 * border_px
        or image.shape[1] < 2 * border_px
    ):
        return False
    rgb = image[..., :3]
    if image.shape[-1] == 4:
        alpha = image[..., 3:4]
        rgb = rgb * alpha + (1.0 - alpha)
    border = np.concatenate(
        (
            rgb[:border_px].reshape(-1, 3),
            rgb[-border_px:].reshape(-1, 3),
            rgb[:, :border_px].reshape(-1, 3),
            rgb[:, -border_px:].reshape(-1, 3),
        ),
        axis=0,
    )
    return bool(np.all(border >= 0.995))


def _save(fig, output_prefix: str | Path, dpi: int) -> dict[str, Path]:
    """Save both formats and fail closed if the fitted PNG still touches an edge."""

    prefix = _output_prefix(output_prefix)
    png = prefix.with_suffix(".png")
    pdf = prefix.with_suffix(".pdf")
    fig.savefig(png, dpi=dpi)
    fig.savefig(pdf)
    if not _png_has_clear_border(png):
        raise RuntimeError(
            "page fitting left rendered content on the PNG boundary; "
            "the output may be clipped"
        )
    return {"png": png.resolve(), "pdf": pdf.resolve()}


def _nice_number_ceiling(value: float) -> float:
    """Round a positive value upward to 1, 2, or 5 times a power of ten."""

    if not np.isfinite(value) or value <= 0:
        raise ValueError("value must be positive and finite")
    exponent = np.floor(np.log10(value))
    scale = 10.0**exponent
    fraction = value / scale
    for candidate in (1.0, 2.0, 5.0, 10.0):
        if fraction <= candidate * (1 + 1e-12):
            return candidate * scale
    return 10.0 * scale


def _nice_bounds(data_min: float, data_max: float) -> tuple[float, float, float]:
    """Return outward-rounded bounds and their rounding quantum.

    The boundary quantum is based on roughly one tenth of the data span.  For
    example, data from 54 to 358 uses a quantum of 50 and produces bounds of
    50 and 400.
    """

    if not np.isfinite(data_min) or not np.isfinite(data_max):
        raise ValueError("axis data must contain finite values")
    if data_min > data_max:
        data_min, data_max = data_max, data_min
    span = data_max - data_min
    if span == 0:
        reference = max(abs(data_min), 1.0)
        span = reference * 0.1
        data_min -= span / 2
        data_max += span / 2

    quantum = _nice_number_ceiling(span / 10.0)
    tolerance = 1e-12
    scaled_min = data_min / quantum
    scaled_max = data_max / quantum
    lower = np.floor(scaled_min + tolerance * max(1.0, abs(scaled_min))) * quantum
    upper = np.ceil(scaled_max - tolerance * max(1.0, abs(scaled_max))) * quantum
    if lower == upper:
        lower -= quantum
        upper += quantum
    return float(lower), float(upper), float(quantum)


def _significant_digit_count(value: float) -> int:
    """Return the decimal significant digits needed to express a step."""

    exponent = np.floor(np.log10(abs(value)))
    normalized = value / 10.0**exponent
    for digits in range(1, 7):
        if np.isclose(
            normalized,
            np.round(normalized, digits - 1),
            rtol=0,
            atol=1e-10,
        ):
            return digits
    return 9


def _uniform_ticks(
    lower: float,
    upper: float,
    *,
    min_labels: int = 4,
    max_labels: int = 6,
) -> np.ndarray:
    """Create 4--6 uniformly spaced labels including both endpoints."""

    if not 2 <= min_labels <= max_labels:
        raise ValueError("tick label bounds must satisfy 2 <= min <= max")
    span = upper - lower
    if not np.isfinite(span) or span <= 0:
        raise ValueError("axis limits must be finite and increasing")

    candidates = []
    for label_count in range(min_labels, max_labels + 1):
        step = span / (label_count - 1)
        score = (
            _significant_digit_count(step),
            abs(label_count - 5),
            -label_count,
        )
        candidates.append((score, label_count))
    label_count = min(candidates)[1]
    ticks = np.linspace(lower, upper, label_count)
    ticks[np.isclose(ticks, 0.0, rtol=0, atol=span * 1e-12)] = 0.0
    return ticks


def _auto_axis_scale(values) -> tuple[tuple[float, float], np.ndarray]:
    """Jointly choose clean bounds and an exactly divisible tick interval."""

    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        raise ValueError("axis data must contain at least one finite value")

    lower, upper, quantum = _nice_bounds(float(finite.min()), float(finite.max()))
    candidates = []
    # Search a few outward quantum increments. Prefer the simplest step first,
    # then the least extra padding, while retaining 4--6 labels.
    for lower_expansion in range(5):
        for upper_expansion in range(5):
            candidate_lower = lower - lower_expansion * quantum
            candidate_upper = upper + upper_expansion * quantum
            ticks = _uniform_ticks(candidate_lower, candidate_upper)
            step = ticks[1] - ticks[0]
            score = (
                _significant_digit_count(step),
                lower_expansion + upper_expansion,
                abs(ticks.size - 5),
                -ticks.size,
                abs(candidate_lower) + abs(candidate_upper),
                lower_expansion,
            )
            candidates.append(
                (score, (float(candidate_lower), float(candidate_upper)), ticks)
            )
    _, bounds, ticks = min(candidates, key=lambda item: item[0])
    return bounds, ticks


def _axis_scale(
    values,
    limits: tuple[float, float] | None,
    ticks: Sequence[float] | None,
) -> tuple[tuple[float, float], Sequence[float]]:
    if limits is None:
        bounds, resolved_ticks = _auto_axis_scale(values)
    else:
        lower, upper = map(float, limits)
        if not np.isfinite(lower) or not np.isfinite(upper) or lower >= upper:
            raise ValueError("axis limits must be finite and increasing")
        bounds = (lower, upper)
        resolved_ticks = _uniform_ticks(lower, upper)

    if ticks is not None:
        resolved_ticks = ticks
    return bounds, resolved_ticks


def _log_candidates(lower: float, upper: float) -> np.ndarray:
    """Return 1--2--5 tick candidates spanning positive bounds."""

    lower_exp = int(np.floor(np.log10(lower))) - 2
    upper_exp = int(np.ceil(np.log10(upper))) + 2
    values = [
        multiplier * 10.0**exponent
        for exponent in range(lower_exp, upper_exp + 1)
        for multiplier in (1.0, 2.0, 5.0)
    ]
    return np.asarray(sorted(set(values)), dtype=float)


def _thin_log_ticks(ticks: np.ndarray, lower: float, upper: float) -> np.ndarray:
    """Reduce a long 1--2--5 sequence while retaining clean log labels."""

    if ticks.size <= 6:
        return ticks

    exponent_min = int(np.ceil(np.log10(lower)))
    exponent_max = int(np.floor(np.log10(upper)))
    decades = np.asarray(
        [10.0**exponent for exponent in range(exponent_min, exponent_max + 1)],
        dtype=float,
    )
    anchors = np.unique(np.concatenate(([lower], decades, [upper])))
    anchors = anchors[(anchors >= lower) & (anchors <= upper)]
    if anchors.size < 4:
        anchors = ticks
    if anchors.size <= 6:
        return anchors

    indices = np.rint(np.linspace(0, anchors.size - 1, 6)).astype(int)
    return anchors[np.unique(indices)]


def _log_axis_scale(
    values,
    limits: tuple[float, float] | None,
    ticks: Sequence[float] | None,
) -> tuple[tuple[float, float], Sequence[float]]:
    """Resolve positive log-axis bounds and clean 1--2--5 major ticks."""

    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        raise ValueError("log axis data must contain at least one finite value")
    if np.any(finite <= 0):
        raise ValueError("log axes require strictly positive data")

    if limits is None:
        data_min = float(finite.min())
        data_max = float(finite.max())
        candidates = _log_candidates(data_min, data_max)
        lower_index = int(np.flatnonzero(candidates <= data_min)[-1])
        upper_index = int(np.flatnonzero(candidates >= data_max)[0])
        while upper_index - lower_index + 1 < 4:
            lower_padding = np.log(data_min / candidates[lower_index - 1])
            upper_padding = np.log(candidates[upper_index + 1] / data_max)
            if lower_padding <= upper_padding:
                lower_index -= 1
            else:
                upper_index += 1
        lower = float(candidates[lower_index])
        upper = float(candidates[upper_index])
        resolved_ticks = candidates[lower_index : upper_index + 1]
    else:
        lower, upper = map(float, limits)
        if (
            not np.isfinite(lower)
            or not np.isfinite(upper)
            or lower <= 0
            or lower >= upper
        ):
            raise ValueError("log axis limits must be positive and increasing")
        candidates = _log_candidates(lower, upper)
        interior = candidates[(candidates > lower) & (candidates < upper)]
        resolved_ticks = np.unique(np.concatenate(([lower], interior, [upper])))

    bounds = (lower, upper)
    resolved_ticks = _thin_log_ticks(resolved_ticks, lower, upper)
    if ticks is not None:
        resolved_ticks = np.asarray(ticks, dtype=float)
        if (
            resolved_ticks.size == 0
            or not np.isfinite(resolved_ticks).all()
            or np.any(resolved_ticks <= 0)
        ):
            raise ValueError("log axis ticks must be finite and strictly positive")
    return bounds, resolved_ticks


def _scaled_axis(
    values,
    limits: tuple[float, float] | None,
    ticks: Sequence[float] | None,
    axis_scale: str,
) -> tuple[tuple[float, float], Sequence[float]]:
    if axis_scale == "log":
        return _log_axis_scale(values, limits, ticks)
    return _axis_scale(values, limits, ticks)


_LEGEND_CLEARANCE_PT = 2.0
"""Clearance demanded between the legend frame and the nearest plotted point."""

_MAX_LEGEND_EXPANSIONS = 6
"""Cap on how far the axis is grown before giving up and warning instead."""


def _legend_collides(ax, legend, renderer) -> bool:
    """True when any plotted point falls inside the legend frame.

    Only points that are actually inside the axes count: a curve clipped away
    at the edge of the view is not something the legend can hide.
    """
    if legend is None:
        return False
    pad = _LEGEND_CLEARANCE_PT * ax.figure.dpi / 72.0
    frame = legend.get_window_extent(renderer).padded(pad)
    axes_box = ax.get_window_extent(renderer)
    for line in ax.lines:
        data = line.get_xydata()
        if data is None or len(data) == 0:
            continue
        points = line.get_transform().transform(data)
        points = points[np.isfinite(points).all(axis=1)]
        if points.size == 0:
            continue
        visible = (
            (points[:, 0] >= axes_box.x0)
            & (points[:, 0] <= axes_box.x1)
            & (points[:, 1] >= axes_box.y0)
            & (points[:, 1] <= axes_box.y1)
        )
        if not visible.any():
            continue
        inside = points[visible]
        hit = (
            (inside[:, 0] >= frame.x0)
            & (inside[:, 0] <= frame.x1)
            & (inside[:, 1] >= frame.y0)
            & (inside[:, 1] <= frame.y1)
        )
        if hit.any():
            return True
    return False


def _next_log_bound(value: float, *, upward: bool) -> float:
    """Step a positive bound to the next clean 1--2--5 value."""
    candidates = _log_candidates(value, value)
    if upward:
        larger = candidates[candidates > value * (1 + 1e-9)]
        return float(larger[0]) if larger.size else value * 10.0
    smaller = candidates[candidates < value * (1 - 1e-9)]
    return float(smaller[-1]) if smaller.size else value / 10.0


def _clear_legend(
    ax,
    legend,
    values,
    bounds,
    ticks,
    legend_loc,
    axis_scale: str,
    *,
    expandable: bool,
):
    """Grow the y range until the legend stops covering data.

    A legend drawn on top of the curves it labels destroys the figure's whole
    purpose, and the fix that preserves the calibrated geometry is to make room
    in the data range rather than to shrink or move the axes: the legend is
    anchored to an axes corner, so widening the view pushes the curves away from
    it while every calibrated dimension stays put.

    The range grows one tick step at a time (a decade step on log axes) and the
    ticks are re-derived after each step, so the 4--6 uniform label rule keeps
    holding.  Explicit limits or ticks are never overridden -- the caller asked
    for those exactly -- so an unavoidable collision is reported as a warning
    instead.
    """
    renderer = _renderer(ax.figure)
    if not _legend_collides(ax, legend, renderer):
        return bounds, ticks
    if not expandable:
        warnings.warn(
            "the legend overlaps plotted data, but the y axis uses explicit "
            "limits or ticks and will not be changed; pass ylim=None and "
            "yticks=None to let the range expand, or move the legend",
            stacklevel=3,
        )
        return bounds, ticks

    lower, upper = bounds
    upward = "lower" not in str(legend_loc)
    step = float(ticks[1] - ticks[0]) if len(ticks) > 1 else (upper - lower)
    for _ in range(_MAX_LEGEND_EXPANSIONS):
        if axis_scale == "log":
            if upward:
                upper = _next_log_bound(upper, upward=True)
            else:
                lower = _next_log_bound(lower, upward=False)
            bounds, ticks = _log_axis_scale(values, (lower, upper), None)
        else:
            if upward:
                upper += step
            else:
                lower -= step
            ticks = _uniform_ticks(lower, upper)
            bounds = (lower, upper)
        ax.set_yticks(ticks)
        ax.set_ylim(*bounds)
        if not _legend_collides(ax, legend, _renderer(ax.figure)):
            return bounds, ticks
    warnings.warn(
        "could not clear the legend from the plotted data within "
        f"{_MAX_LEGEND_EXPANSIONS} axis expansions; consider another legend_loc",
        stacklevel=3,
    )
    return bounds, ticks


def _format_axes(
    ax,
    xticks,
    yticks,
    xscale: str = "linear",
    yscale: str = "linear",
) -> None:
    ax.set_xticks(xticks)
    ax.set_yticks(yticks)
    ax.xaxis.set_major_formatter(StrMethodFormatter("{x:g}"))
    ax.yaxis.set_major_formatter(StrMethodFormatter("{x:g}"))
    if xscale == "log":
        ax.xaxis.set_minor_formatter(NullFormatter())
    if yscale == "log":
        ax.yaxis.set_minor_formatter(NullFormatter())


def line_plot(
    x: Sequence[float],
    series: Mapping[str, Sequence[float]],
    *,
    output_prefix: str | Path = "line_plot",
    xlabel: str = r"$x/L$",
    ylabel: str = r"$y/L$",
    xlim: tuple[float, float] | None = None,
    ylim: tuple[float, float] | None = None,
    xticks: Sequence[float] | None = None,
    yticks: Sequence[float] | None = None,
    scale: str = "linear",
    colors: Sequence[str] | None = None,
    series_styles: Mapping[str, Mapping[str, object]] | None = None,
    legend_loc: str | None = "upper left",
    legend_clearance: bool = True,
    annotation: str | None = "(a)",
    dpi: int = 300,
) -> dict[str, Path]:
    """Save a calibrated line figure.

    ``series`` maps legend labels to y arrays. Labels may contain LaTeX.
    ``scale`` accepts ``"linear"``, ``"semilogx"``, ``"semilogy"``, or
    ``"loglog"`` and uses the corresponding native Matplotlib method without
    transforming the supplied data. ``series_styles`` optionally maps series
    labels to Matplotlib line properties, such as marker and linestyle.
    Set ``legend_loc=None`` to omit the legend. Automatic linear limits use
    4--6 uniform ticks; automatic log limits use clean 1--2--5 ticks. Explicit
    limits or ticks always take precedence. The physical axes box is always
    exactly 4:3 (width:height); this is independent of data limits and scale.

    With ``legend_clearance`` (the default) an automatic y range is widened
    until the legend no longer sits on top of any curve. It has no effect when
    ``ylim`` or ``yticks`` is given, since those are honoured exactly; such a
    collision is reported as a warning instead.
    """

    require_latex_tools()
    x_array = np.asarray(x, dtype=float)
    if x_array.ndim != 1 or x_array.size == 0:
        raise ValueError("x must be a non-empty one-dimensional array")
    if not series:
        raise ValueError("series must contain at least one labeled y array")
    if scale not in LINE_SCALE_METHODS:
        choices = ", ".join(repr(value) for value in LINE_SCALE_METHODS)
        raise ValueError(f"scale must be one of: {choices}")
    styles = dict(series_styles or {})
    unknown_style_labels = set(styles) - set(series)
    if unknown_style_labels:
        labels = ", ".join(repr(label) for label in sorted(unknown_style_labels))
        raise ValueError(f"series_styles contains unknown labels: {labels}")

    palette = tuple(colors) if colors is not None else MATLAB_LINE_COLORS
    page_width, page_height = LINE_PAGE_PT

    processed_series = []
    for label, values in series.items():
        y_array = np.asarray(values, dtype=float)
        if y_array.shape != x_array.shape:
            raise ValueError(
                f"series {label!r} has shape {y_array.shape}; "
                f"expected {x_array.shape}"
            )
        processed_series.append((label, y_array))

    x_axis_scale, y_axis_scale, plot_method = LINE_SCALE_METHODS[scale]
    x_bounds, resolved_xticks = _scaled_axis(
        x_array, xlim, xticks, x_axis_scale
    )
    all_y = np.concatenate([values.ravel() for _, values in processed_series])
    y_bounds, resolved_yticks = _scaled_axis(
        all_y, ylim, yticks, y_axis_scale
    )

    with plt.rc_context(PUBLICATION_RC):
        fig = plt.figure(figsize=(page_width / 72, page_height / 72))
        ax = fig.add_axes(_normalized_bounds(LINE_AXES_PT, LINE_PAGE_PT))

        plotter = getattr(ax, plot_method)
        for index, (label, y_array) in enumerate(processed_series):
            plot_kwargs = {
                "color": palette[index % len(palette)],
                "label": label,
            }
            plot_kwargs.update(styles.get(label, {}))
            plotter(
                x_array,
                y_array,
                **plot_kwargs,
            )

        _format_axes(
            ax,
            resolved_xticks,
            resolved_yticks,
            x_axis_scale,
            y_axis_scale,
        )
        # Set limits after ticks because Matplotlib may otherwise expand the
        # view to include user-supplied ticks outside explicit bounds.
        ax.set_xlim(*x_bounds)
        ax.set_ylim(*y_bounds)
        ax.set_xlabel(xlabel, labelpad=5)
        ax.set_ylabel(ylabel, labelpad=5)

        legend = None
        if legend_loc is not None:
            legend = ax.legend(
                loc=legend_loc,
                frameon=True,
                fancybox=False,
                framealpha=1,
                facecolor="white",
                edgecolor=MATLAB_DARK_GRAY,
                borderaxespad=0.556,
                borderpad=0.294,
                labelspacing=0.225,
                handlelength=2.09,
                handletextpad=0.285,
            )
            legend.get_frame().set_linewidth(1)

            if legend_clearance:
                y_bounds, resolved_yticks = _clear_legend(
                    ax,
                    legend,
                    all_y,
                    y_bounds,
                    resolved_yticks,
                    legend_loc,
                    y_axis_scale,
                    expandable=ylim is None and yticks is None,
                )

        annotation_artist = None
        if annotation:
            annotation_artist = fig.text(
                1 / page_width,
                1 - 2.75 / page_height,
                annotation,
                va="top",
                ha="left",
                color="black",
                fontsize=16.5,
            )

        _expand_page_to_fit(
            fig, ((ax, LINE_AXES_PT),), LINE_PAGE_PT, annotation_artist
        )
        outputs = _save(fig, output_prefix, dpi)
        plt.close(fig)
    return outputs


def contour_plot(
    x: Sequence[float],
    y: Sequence[float],
    z,
    *,
    box_ratio: float | tuple[float, float],
    output_prefix: str | Path = "contour_plot",
    xlabel: str = r"$x/L$",
    ylabel: str = r"$y/L$",
    colorbar_title: str = r"$Z$",
    zlim: tuple[float, float] | None = None,
    level_count: int = 200,
    cmap: str = "RdBu_r",
    xticks: Sequence[float] | None = None,
    yticks: Sequence[float] | None = None,
    colorbar_ticks: Sequence[float] | None = None,
    annotation: str | None = "(a)",
    dpi: int = 300,
) -> dict[str, Path]:
    """Save a calibrated filled-contour figure.

    Accept ``z`` in either Matplotlib shape ``(len(y), len(x))`` or MATLAB
    ``ndgrid`` shape ``(len(x), len(y))``. Signed data defaults to symmetric
    color limits around zero. ``box_ratio`` is required and denotes the
    physical axes-box width:height ratio, either as a positive number or a
    ``(width, height)`` pair. Callers should obtain it from the user rather
    than infer it.
    """

    require_latex_tools()
    x_array = np.asarray(x, dtype=float)
    y_array = np.asarray(y, dtype=float)
    z_array = np.asarray(z, dtype=float)
    if x_array.ndim != 1 or y_array.ndim != 1:
        raise ValueError("x and y must be one-dimensional arrays")
    if z_array.shape == (x_array.size, y_array.size):
        z_xy = z_array.T
    elif z_array.shape == (y_array.size, x_array.size):
        z_xy = z_array
    else:
        raise ValueError(
            f"z has shape {z_array.shape}; expected "
            f"{(y_array.size, x_array.size)} or {(x_array.size, y_array.size)}"
        )

    if zlim is None:
        data_min = float(np.nanmin(z_xy))
        data_max = float(np.nanmax(z_xy))
        if data_min < 0 < data_max:
            magnitude = max(abs(data_min), abs(data_max))
            zlim = (-magnitude, magnitude)
        else:
            zlim = (data_min, data_max)
    vmin, vmax = zlim
    if not vmin < vmax:
        raise ValueError("zlim must be increasing")
    if level_count < 2:
        raise ValueError("level_count must be at least 2")
    levels = np.linspace(vmin, vmax, level_count)

    if colorbar_ticks is None:
        colorbar_ticks = np.linspace(vmin, vmax, 5)

    axes_pt = _fit_box_ratio(CONTOUR_AXES_FRAME_PT, box_ratio)
    cbar_pt = (
        CONTOUR_CBAR_PT[0],
        axes_pt[1],
        CONTOUR_CBAR_PT[2],
        axes_pt[3],
    )
    page_width, page_height = CONTOUR_PAGE_PT
    with plt.rc_context(PUBLICATION_RC):
        fig = plt.figure(figsize=(page_width / 72, page_height / 72))
        ax = fig.add_axes(_normalized_bounds(axes_pt, CONTOUR_PAGE_PT))
        cax = fig.add_axes(_normalized_bounds(cbar_pt, CONTOUR_PAGE_PT))

        filled = ax.contourf(
            x_array,
            y_array,
            z_xy,
            levels=levels,
            cmap=cmap,
            vmin=vmin,
            vmax=vmax,
            antialiased=False,
        )
        ax.set_xlim(float(x_array.min()), float(x_array.max()))
        ax.set_ylim(float(y_array.min()), float(y_array.max()))
        _, resolved_xticks = _axis_scale(
            x_array,
            (float(x_array.min()), float(x_array.max())),
            xticks,
        )
        _, resolved_yticks = _axis_scale(
            y_array,
            (float(y_array.min()), float(y_array.max())),
            yticks,
        )
        _format_axes(ax, resolved_xticks, resolved_yticks)
        ax.tick_params(length=2.64)
        ax.set_xlabel(xlabel, labelpad=4, fontsize=17.6)
        ax.set_ylabel(ylabel, labelpad=2.5, fontsize=17.6)

        colorbar = fig.colorbar(filled, cax=cax, ticks=colorbar_ticks)
        colorbar.outline.set_linewidth(0.5)
        colorbar.ax.yaxis.set_ticks_position("right")
        colorbar.ax.tick_params(
            direction="in",
            length=2.31,
            width=0.5,
            pad=4.8,
            labelsize=14.4,
        )
        tick_text = [f"{float(value):g}" for value in colorbar_ticks]
        colorbar.set_ticklabels(tick_text)
        for tick_label in colorbar.ax.get_yticklabels():
            tick_label.set_usetex(False)
            tick_label.set_fontfamily("Times New Roman")
            tick_label.set_fontsize(14.4)
        colorbar.ax.set_title(colorbar_title, fontsize=16, pad=10.5)

        annotation_artist = None
        if annotation:
            annotation_artist = fig.text(
                7.25 / page_width,
                1 - 6.25 / page_height,
                annotation,
                va="top",
                ha="left",
                color="black",
                fontsize=16.5,
            )

        _expand_page_to_fit(
            fig,
            ((ax, axes_pt), (cax, cbar_pt)),
            CONTOUR_PAGE_PT,
            annotation_artist,
        )
        outputs = _save(fig, output_prefix, dpi)
        plt.close(fig)
    return outputs


def _run_demo(kind: str, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    if kind in {"line", "both"}:
        x = np.arange(0.0, 1.0001, 0.01)
        outputs = line_plot(
            x,
            {r"$y=x$": x, r"$y=x^2$": x**2},
            output_prefix=output_dir / "line_demo",
            xlim=(0, 1),
            ylim=(0, 1),
            xticks=np.linspace(0, 1, 6),
            yticks=np.linspace(0, 1, 6),
        )
        print(*(str(path) for path in outputs.values()), sep="\n")

    if kind in {"contour", "both"}:
        x = np.arange(0.0, 1.0001, 0.01)
        y = np.arange(0.0, 2.0001, 0.01)
        x_grid, y_grid = np.meshgrid(x, y, indexing="ij")
        z = np.sin(2 * np.pi * x_grid) + np.cos(4 * np.pi * y_grid)
        outputs = contour_plot(
            x,
            y,
            z,
            box_ratio=(263.5, 231.0),
            output_prefix=output_dir / "contour_demo",
            zlim=(-2, 2),
            xticks=np.linspace(0, 1, 6),
            yticks=np.linspace(0, 2, 5),
            colorbar_ticks=(-2, -1, 0, 1, 2),
        )
        print(*(str(path) for path in outputs.values()), sep="\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", choices=("line", "contour", "both"), default="both")
    parser.add_argument("--output-dir", type=Path, default=Path("plot_demo_output"))
    args = parser.parse_args()
    _run_demo(args.demo, args.output_dir)


if __name__ == "__main__":
    main()
