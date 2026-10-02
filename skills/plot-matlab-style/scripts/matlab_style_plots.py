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

# File-only plotting keeps exact physical geometry with the Agg backend.
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import NullFormatter, StrMethodFormatter


MATLAB_DARK_GRAY = "#262626"
PANEL_LABEL_FONT_PT = 16.5
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
# The line-plot axes box is a strict 4:3 (width:height).  Keep the calibrated
# width and let the height follow from the invariant.
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


def _panel_label_anchor(ax, *, colorbar_title=None) -> tuple[float, float]:
    """Measure the ylabel left edge and axes/title top in display coordinates."""

    fig = ax.figure
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    ylabel_box = ax.yaxis.label.get_window_extent(renderer)
    if colorbar_title is None:
        top = ax.get_window_extent(renderer).y1
    else:
        if colorbar_title.figure is not fig:
            raise ValueError("colorbar_title and ax must belong to the same figure")
        top = colorbar_title.get_window_extent(renderer).y1
    return float(ylabel_box.x0), float(top)


def _panel_label_text(fig, position, annotation):
    """Create an unclipped, crop-aware label with the publication LaTeX font."""

    return fig.text(
        *position,
        annotation,
        transform=fig.transFigure,
        ha="center",
        va="center",
        fontsize=PANEL_LABEL_FONT_PT,
        fontfamily=PUBLICATION_RC["font.family"],
        usetex=PUBLICATION_RC["text.usetex"],
        color="black",
        clip_on=False,
        in_layout=True,
    )


def add_panel_label(fig, ax, annotation: str | None = "(a)", *, colorbar_title=None):
    """Add a renderer-positioned panel label and return its Text artist.

    For lines, its center is at the ylabel bbox's left edge and the axes
    bbox's top. For contours, pass the Text returned by the colorbar axes'
    ``set_title``: its bbox's TOP is the vertical reference, not the ylabel
    or colorbar ticks. ``None`` omits the label. Call after setting all ticks,
    labels and layout, before export. In a native multi-panel figure, pass
    the FIRST panel's axes and the UPPER ROW colorbar title; the figure's
    display coordinates already include both panels' layout offsets.
    """

    if annotation is None:
        return None
    if ax.figure is not fig:
        raise ValueError("ax must belong to fig")
    anchor = _panel_label_anchor(ax, colorbar_title=colorbar_title)
    position = fig.transFigure.inverted().transform(anchor)
    return _panel_label_text(fig, position, annotation)


def save_labeled_composite(
    canvas,
    output_prefix: str | Path,
    *,
    reference_ax,
    colorbar_title,
    first_axes_top_left: tuple[float, float],
    title_reference_ax=None,
    title_axes_top_left: tuple[float, float] | None = None,
    annotation: str | None = "(a)",
    dpi: int = 300,
    auto_crop: bool = True,
    padding_pt: float = 6.0,
) -> dict[str, Path]:
    """Export a stitched contour image with a measured LaTeX panel label.

    ``canvas`` is a PIL image or RGB(A) array, assembled at ``dpi``.
    ``reference_ax`` must reproduce the FIRST panel's actual ylabel, ticks
    and geometry. ``colorbar_title`` is the UPPER ROW colorbar's title Text.
    If that title belongs to a different panel, also pass its main axes as
    ``title_reference_ax`` and their ``title_axes_top_left`` in the canvas.
    Both top-left coordinates refer to axes boxes (not image corners), in
    canvas pixels measured from the top-left. Renderer-derived offsets are
    scaled from each reference figure's DPI to the canvas DPI; no guessed
    text offsets are used. Keep reference figures open until this returns.
    PNG/PDF use the same crop and padding policy as standalone plots.
    """

    require_latex_tools()
    pixels = np.asarray(canvas)
    height, width = pixels.shape[:2]
    with plt.rc_context(PUBLICATION_RC):
        fig = plt.figure(figsize=(width / dpi, height / dpi), dpi=dpi)
        image_ax = fig.add_axes((0, 0, 1, 1))
        image_ax.imshow(pixels, interpolation="none", aspect="auto")
        image_ax.set_axis_off()
        if annotation is not None:
            title_ax = reference_ax if title_reference_ax is None else title_reference_ax
            if title_axes_top_left is None:
                if title_ax is not reference_ax:
                    raise ValueError("title_axes_top_left is required for a different title panel")
                title_axes_top_left = first_axes_top_left
            ylabel_left, _ = _panel_label_anchor(reference_ax)
            _, title_top = _panel_label_anchor(title_ax, colorbar_title=colorbar_title)
            first_box = reference_ax.get_window_extent(reference_ax.figure.canvas.get_renderer())
            title_box = title_ax.get_window_extent(title_ax.figure.canvas.get_renderer())
            center_x = first_axes_top_left[0] + (
                ylabel_left - first_box.x0
            ) * dpi / reference_ax.figure.dpi
            center_y = title_axes_top_left[1] + (
                title_box.y1 - title_top
            ) * dpi / title_ax.figure.dpi
            fig.canvas.draw()
            # Canvas coordinates run down from the top; display coordinates
            # run up from the bottom. Apply offsets before figure conversion.
            position = fig.transFigure.inverted().transform((center_x, height - center_y))
            _panel_label_text(fig, position, annotation)
        try:
            return _save(fig, output_prefix, dpi, auto_crop=auto_crop, padding_pt=padding_pt)
        finally:
            plt.close(fig)


def _output_prefix(value: str | Path) -> Path:
    prefix = Path(value).expanduser()
    if prefix.suffix.lower() in {".png", ".pdf"}:
        prefix = prefix.with_suffix("")
    prefix.parent.mkdir(parents=True, exist_ok=True)
    return prefix


def _png_has_clear_border(path: Path, border_px: int = 2) -> bool:
    """Return whether the outer PNG pixels are blank white canvas."""

    image = plt.imread(path)
    if image.ndim != 3 or image.shape[0] < 2 * border_px or image.shape[1] < 2 * border_px:
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


def _save(
    fig,
    output_prefix: str | Path,
    dpi: int,
    *,
    auto_crop: bool = True,
    padding_pt: float = 6.0,
) -> dict[str, Path]:
    """Save PNG/PDF without clipping text or other visible artists.

    The default uses Matplotlib's artist-aware tight bounding box, adds a
    safety margin, and checks the PNG border.  If rasterized content reaches
    the edge, the margin grows automatically and both formats are rewritten.
    Set ``auto_crop=False`` only when an exact fixed page is required for
    reference matching.
    """

    if padding_pt < 0:
        raise ValueError("padding_pt must be non-negative")
    prefix = _output_prefix(output_prefix)
    png = prefix.with_suffix(".png")
    pdf = prefix.with_suffix(".pdf")
    if not auto_crop:
        fig.savefig(png, dpi=dpi)
        fig.savefig(pdf)
        return {"png": png.resolve(), "pdf": pdf.resolve()}

    padding_inches = padding_pt / 72.0
    for _ in range(3):
        save_kwargs = {"bbox_inches": "tight", "pad_inches": padding_inches}
        fig.savefig(png, dpi=dpi, **save_kwargs)
        fig.savefig(pdf, **save_kwargs)
        if _png_has_clear_border(png):
            return {"png": png.resolve(), "pdf": pdf.resolve()}
        padding_inches = max(padding_inches * 2.0, 1.0 / dpi)

    raise RuntimeError(
        "automatic export could not create a clear outer border; "
        "inspect artists with custom transforms or clipping disabled"
    )


def _box_ratio_value(box_ratio: float | Sequence[float]) -> float:
    """Normalize a requested axes-box width:height ratio."""

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


def _renderer(fig):
    fig.canvas.draw()
    try:
        return fig.canvas.get_renderer()
    except AttributeError:
        from matplotlib.backends.backend_agg import FigureCanvasAgg

        return FigureCanvasAgg(fig).get_renderer()


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
    auto_crop: bool = True,
    padding_pt: float = 6.0,
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
    exactly 4:3 (width:height). ``auto_crop=True`` uses artist-aware export
    bounds plus ``padding_pt`` of safety margin so labels are not clipped.
    ``legend_clearance=True`` preserves automatic y-range expansion to avoid
    covering curves; explicit limits/ticks remain fixed and collisions warn.
    ``annotation`` uses a 16.5 pt LaTeX serif label centered on the ylabel's
    left bbox edge and axes' top bbox edge; ``None`` omits it.
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
        fig = plt.figure(figsize=(page_width / 72, page_height / 72), dpi=dpi)
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
                    ax, legend, all_y, y_bounds, resolved_yticks, legend_loc,
                    y_axis_scale, expandable=ylim is None and yticks is None,
                )

        add_panel_label(fig, ax, annotation)

        outputs = _save(
            fig,
            output_prefix,
            dpi,
            auto_crop=auto_crop,
            padding_pt=padding_pt,
        )
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
    auto_crop: bool = True,
    padding_pt: float = 6.0,
    show_colorbar: bool = True,
) -> dict[str, Path]:
    """Save a calibrated filled-contour figure.

    Accept ``z`` in either Matplotlib shape ``(len(y), len(x))`` or MATLAB
    ``ndgrid`` shape ``(len(x), len(y))``. Signed data defaults to symmetric
    color limits around zero. ``box_ratio`` is required and denotes the
    physical axes-box width:height ratio, either as a positive number or a
    ``(width, height)`` pair. Callers should obtain it from the user rather
    than infer it. ``auto_crop=True`` prevents text clipping during export.
    Set ``show_colorbar=False`` when assembling panels that share a colorbar.
    ``annotation`` is a 16.5 pt LaTeX serif label centered on the ylabel's
    left bbox edge and colorbar TOP TITLE's top bbox edge. With no colorbar,
    use the axes' top edge; for shared-colorbar composites omit per-panel
    annotations and call ``add_panel_label`` or ``save_labeled_composite``.
    ``annotation=None`` omits the label.
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
        fig = plt.figure(figsize=(page_width / 72, page_height / 72), dpi=dpi)
        ax = fig.add_axes(_normalized_bounds(axes_pt, CONTOUR_PAGE_PT))
        cax = (
            fig.add_axes(_normalized_bounds(cbar_pt, CONTOUR_PAGE_PT))
            if show_colorbar
            else None
        )

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

        title_text = None
        if show_colorbar:
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
            title_text = colorbar.ax.set_title(colorbar_title, fontsize=16, pad=10.5)

        add_panel_label(fig, ax, annotation, colorbar_title=title_text)

        outputs = _save(
            fig,
            output_prefix,
            dpi,
            auto_crop=auto_crop,
            padding_pt=padding_pt,
        )
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
