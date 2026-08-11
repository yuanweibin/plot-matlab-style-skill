#!/usr/bin/env python3
"""Calibrated Matplotlib line and filled-contour plots.

The functions save PNG and PDF outputs directly so LaTeX rendering happens
inside the calibrated rc context. Run this file with ``--demo both`` for a
smoke test.
"""

from __future__ import annotations

import argparse
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import NullFormatter, StrMethodFormatter


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
LINE_AXES_PT = (52.0, 47.5, 310.0, 231.0)

CONTOUR_PAGE_PT = (370.0, 308.0)
CONTOUR_AXES_PT = (51.5, 49.5, 263.5, 231.0)
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


def _output_prefix(value: str | Path) -> Path:
    prefix = Path(value).expanduser()
    if prefix.suffix.lower() in {".png", ".pdf"}:
        prefix = prefix.with_suffix("")
    prefix.parent.mkdir(parents=True, exist_ok=True)
    return prefix


def _save(fig, output_prefix: str | Path, dpi: int) -> dict[str, Path]:
    prefix = _output_prefix(output_prefix)
    png = prefix.with_suffix(".png")
    pdf = prefix.with_suffix(".pdf")
    fig.savefig(png, dpi=dpi)
    fig.savefig(pdf)
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
    limits or ticks always take precedence.
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

        if annotation:
            fig.text(
                1 / page_width,
                1 - 2.75 / page_height,
                annotation,
                va="top",
                ha="left",
                color="black",
                fontsize=16.5,
            )

        outputs = _save(fig, output_prefix, dpi)
        plt.close(fig)
    return outputs


def contour_plot(
    x: Sequence[float],
    y: Sequence[float],
    z,
    *,
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
    color limits around zero.
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

    page_width, page_height = CONTOUR_PAGE_PT
    with plt.rc_context(PUBLICATION_RC):
        fig = plt.figure(figsize=(page_width / 72, page_height / 72))
        ax = fig.add_axes(_normalized_bounds(CONTOUR_AXES_PT, CONTOUR_PAGE_PT))
        cax = fig.add_axes(_normalized_bounds(CONTOUR_CBAR_PT, CONTOUR_PAGE_PT))

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

        if annotation:
            fig.text(
                7.25 / page_width,
                1 - 6.25 / page_height,
                annotation,
                va="top",
                ha="left",
                color="black",
                fontsize=16.5,
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
