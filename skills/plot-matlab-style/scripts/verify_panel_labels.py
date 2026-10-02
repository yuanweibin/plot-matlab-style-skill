#!/usr/bin/env python3
"""Generate PNG/PDF examples and verify renderer-based panel-label exports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg
import numpy as np
from PIL import Image

import matlab_style_plots as style


def verify(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    original_save = style._save
    records = []
    expected = {}
    captured = []

    def checked_save(fig, prefix, dpi, **kwargs):
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        labels = fig.texts
        if expected.get("omit"):
            assert len(labels) == 0, "annotation=None created a label"
        else:
            assert len(labels) == 1
            label = labels[0]
            assert label.get_text() == expected["annotation"]
            assert label.get_fontsize() == 16.5
            assert label.get_fontfamily() == ["serif"]
            assert label.get_usetex()
            assert label.get_ha() == label.get_va() == "center"
            assert label.get_in_layout() and not label.get_clip_on()
            if "anchor" in expected:
                anchor = expected["anchor"]
            else:
                ax = expected.get("ax", fig.axes[0])
                title = expected.get("title")
                if title is None and len(fig.axes) == 2:
                    title = fig.axes[1].title
                ylabel_box = ax.yaxis.label.get_window_extent(renderer)
                top_box = (ax if title is None else title).get_window_extent(renderer)
                anchor = (ylabel_box.x0, top_box.y1)
            bbox = label.get_window_extent(renderer)
            center = ((bbox.x0 + bbox.x1) / 2, (bbox.y0 + bbox.y1) / 2)
            np.testing.assert_allclose(center, anchor, rtol=0, atol=1e-7)
        tight = fig.get_tightbbox(renderer)
        if expected.get("capture"):
            captured.append((fig, tight.frozen()))
        outputs = original_save(fig, prefix, dpi, **kwargs)
        # Check actual raster margins, not just a nominal pad argument.
        pixels = np.asarray(Image.open(outputs["png"]).convert("RGB"))
        rows, cols = np.where(np.any(pixels < 250, axis=2))
        margins = [cols.min(), rows.min(), pixels.shape[1] - 1 - cols.max(),
                   pixels.shape[0] - 1 - rows.max()]
        assert min(margins) >= (kwargs.get("padding_pt", 6) - 0.5) * dpi / 72
        assert style._png_has_clear_border(outputs["png"])
        record = {"name": Path(prefix).name, "dpi": dpi,
                  "raster_margins_px": list(map(int, margins)),
                  "label": None if expected.get("omit") else labels[0].get_text()}
        try:
            import pymupdf
        except ImportError:
            record["pdf_check"] = "Use verify_pdf.py and pdftoppm separately (PyMuPDF unavailable)"
        else:
            with pymupdf.open(outputs["pdf"]) as pdf:
                page = pdf[0]
                pad = kwargs.get("padding_pt", 6)
                np.testing.assert_allclose(
                    (page.rect.width, page.rect.height),
                    (tight.width * 72 + 2 * pad, tight.height * 72 + 2 * pad),
                    rtol=0, atol=1e-3,
                )
                preview = output_dir / (Path(prefix).name + "_pdf_preview.png")
                page.get_pixmap(dpi=dpi, alpha=False).save(preview)
                assert style._png_has_clear_border(preview), "PDF rasterization clips content"
                if not expected.get("omit"):
                    spans = [span for block in page.get_text("dict")["blocks"]
                             if "lines" in block for line in block["lines"]
                             for span in line["spans"]
                             if span["text"].strip() == labels[0].get_text()]
                    assert len(spans) == 1, "PDF label must remain searchable vector text"
                    span = spans[0]
                    assert span["font"].startswith("CMR"), span
                    # LaTeX points are 1/72.27 inch; PDF points are 1/72 inch.
                    assert abs(span["size"] - 16.5 * 72 / 72.27) < 0.01, span
                    x0, y0, x1, y1 = span["bbox"]
                    assert min(x0, y0, page.rect.width - x1, page.rect.height - y1) > 0
                    record["pdf_label_font"] = span["font"]
                    record["pdf_label_size_bp"] = span["size"]
        records.append(record)
        return outputs

    style._save = checked_save
    try:
        x = np.linspace(0, 1, 61)
        expected.update(annotation="(a)")
        style.line_plot(x, {r"$y=x$": x, r"$y=x^2$": x**2},
                        output_prefix=output_dir / "line", xlim=(0, 1), ylim=(0, 1))
        expected.update(annotation="(c)")
        style.line_plot(np.geomspace(1, 1000, 61), {"": np.geomspace(.001, 10, 61)},
                        output_prefix=output_dir / "loglog", scale="loglog",
                        ylabel=r"$\varepsilon_{\mathrm{relative}}$", annotation="(c)",
                        legend_loc=None)
        y = np.linspace(0, 2, 71)
        xx, yy = np.meshgrid(x, y, indexing="ij")
        z = np.sin(2 * np.pi * xx) + np.cos(4 * np.pi * yy)
        expected.update(annotation="(b)", capture=True)
        style.contour_plot(x, y, z, box_ratio=(4, 3),
                           output_prefix=output_dir / "contour", zlim=(-2, 2),
                           colorbar_title=r"$(v+U_{\infty})/U_{\infty}$",
                           ylabel=r"$y/L_y$", annotation="(b)", dpi=150)
        source, source_tight = captured[0]
        # _save captured the figure before contour_plot closed it. A closed
        # figure needs a new Agg canvas before it can serve as a reference.
        FigureCanvasAgg(source)
        expected.clear()
        expected.update(omit=True)
        style.line_plot(x, {"": x}, output_prefix=output_dir / "line_no_label",
                        annotation=None, legend_loc=None)
        style.contour_plot(x, y, z, box_ratio=(1, 1),
                           output_prefix=output_dir / "contour_no_label", annotation=None)

        # Native 2x2 layout: ylabel and title belong to different panels.
        with plt.rc_context(style.PUBLICATION_RC):
            fig, axes = plt.subplots(2, 2, figsize=(9, 7), dpi=180)
            fig.subplots_adjust(left=.14, right=.78, top=.82, bottom=.12, wspace=.4, hspace=.5)
            for ax in axes.flat:
                filled = ax.contourf(x, y, z.T, levels=40, cmap="RdBu_r")
                ax.set_xlabel(r"$x/L_x$")
                ax.set_ylabel(r"$y/L_y$")
            cax = fig.add_axes((.84, .55, .025, .27))
            cbar = fig.colorbar(filled, cax=cax)
            title = cbar.ax.set_title(r"$\Delta U/U_{\infty}$", fontsize=16, pad=10.5)
            expected.clear()
            expected.update(annotation="(d)", ax=axes[0, 0], title=title)
            style.add_panel_label(fig, axes[0, 0], "(d)", colorbar_title=title)
            style._save(fig, output_dir / "native_contour_composite", 180)
            plt.close(fig)

        # Stitch at a different DPI, with a colorbar reference from another
        # upper-row panel and deliberately different paste positions.
        source.texts[0].remove()
        source_png = original_save(source, output_dir / "stitch_source", 150)["png"]
        source.canvas.draw()
        renderer = source.canvas.get_renderer()
        source_tight = source.get_tightbbox(renderer)
        axes_box = source.axes[0].get_window_extent(renderer)
        title_box = source.axes[1].title.get_window_extent(renderer)
        ylabel_box = source.axes[0].yaxis.label.get_window_extent(renderer)
        with Image.open(source_png) as image:
            panel = image.convert("RGB")
        scale = 2
        panel = panel.resize((panel.width * scale, panel.height * scale))
        offset = ((axes_box.x0 / 150 - source_tight.x0 + 6 / 72) * 300,
                  (source_tight.y1 + 6 / 72 - axes_box.y1 / 150) * 300)
        paste_first = (140, 130)
        paste_title = (panel.width + 240, 90)
        canvas = Image.new("RGB", (2 * panel.width + 400, 2 * panel.height + 320), "white")
        for paste in (paste_first, paste_title, (140, panel.height + 230),
                      (panel.width + 240, panel.height + 190)):
            canvas.paste(panel, paste)
        first_top_left = tuple(a + b for a, b in zip(paste_first, offset))
        title_top_left = tuple(a + b for a, b in zip(paste_title, offset))
        expected.clear()
        expected.update(annotation="(e)", anchor=(
            first_top_left[0] + (ylabel_box.x0 - axes_box.x0) * scale,
            canvas.height - title_top_left[1] - (axes_box.y1 - title_box.y1) * scale,
        ))
        # Separate figure identity to exercise references from different panels.
        with plt.rc_context(style.PUBLICATION_RC):
            title_fig = plt.figure(figsize=source.get_size_inches(), dpi=150)
            title_ax = title_fig.add_axes(source.axes[0].get_position().bounds)
            title_ax.set_ylim(*source.axes[0].get_ylim())
            title_cax = title_fig.add_axes(source.axes[1].get_position().bounds)
            title = title_cax.set_title(source.axes[1].title.get_text(), fontsize=16, pad=10.5)
            style.save_labeled_composite(canvas, output_dir / "stitched_contour_composite",
                reference_ax=source.axes[0], colorbar_title=title,
                first_axes_top_left=first_top_left, title_reference_ax=title_ax,
                title_axes_top_left=title_top_left, annotation="(e)", dpi=300)
            plt.close(title_fig)
        plt.close(source)
    finally:
        style._save = original_save
    (output_dir / "verification.json").write_text(json.dumps(records, indent=2) + "\n")
    print(f"OK: {len(records)} PNG/PDF exports; alignment, typography, omission and margins verified")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("panel_label_verification"))
    verify(parser.parse_args().output_dir)
