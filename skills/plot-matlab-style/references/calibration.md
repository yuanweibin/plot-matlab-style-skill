# Calibrated MATLAB-style geometry

Use these measurements when the user requests the established line/contour style or asks to match the original MATLAB PDFs. Coordinates are PDF points from the lower-left page origin.

## Shared typography and strokes

- External LaTeX: `text.usetex=True`
- Panel labels: existing LaTeX serif font, 16.5 pt, centered horizontally and vertically; position from renderer bounding boxes after draw, never fixed page/pixel coordinates.
- Main/tick font size: 16 pt
- Axis-label size: approximately 1.1 times the tick size (17.6-18 pt)
- Legend size: approximately 0.9 times the tick size (14.4 pt)
- Axis/tick color: `#262626`
- Data line width: 1 pt with butt caps
- Axis/tick width after MATLAB PDF export: 2/3 pt
- Major ticks: inward on all four sides; keep 3-6 labels per axis
- MATLAB line colors begin with `#0072BD`, `#D95319`
- Raster preview: 300 dpi

## Line figure

- PDF page: 368 x 299 pt
- Axes rectangle: left 52, bottom 47.5, width 310, height 232.5 pt. The current line-style invariant is an exact 4:3 width:height axes box; it supersedes the legacy measured height of 231 pt.
- Legend: upper left, square frame, white background, 1 pt border
- Figure annotation `(a)`: horizontal center at the ylabel bbox's left edge; vertical center at the axes bbox's top edge.
- Calibrated reference content: `y=x`, `y=x^2`, both axes 0-1

## Filled-contour figure

- PDF page: 370 x 308 pt
- Main axes rectangle: left 51.5, bottom 49.5, width 263.5, height 231 pt
- Colorbar rectangle: left 332, bottom 49.5, width 16, height 231 pt
- Main axis range in the reference: x 0-1, y 0-2
- Default signed-data map: `RdBu_r`, 200 levels, symmetric limits
- Colorbar outline/ticks: 0.5 pt; Times New Roman 14.4 pt tick labels
- Colorbar title: LaTeX, 16 pt
- Figure annotation: horizontal center at the ylabel bbox's left edge; vertical center at the colorbar top-title bbox's **top edge**, not the ylabel or colorbar ticks. For multi-panel composites, use the first panel's ylabel and upper row colorbar title, including their placement offsets (and reference-to-output DPI conversion for raster stitching).
- Calibrated reference data: `Z = sin(2*pi*X) + cos(4*pi*Y)`
- The 263.5 x 231 pt rectangle is the legacy maximum frame, not a default box ratio. Ask the user for the desired contour axes-box width:height ratio, then fit that exact ratio inside this frame and align the colorbar vertically with the fitted axes.

## Safe export and fixed-page matching

- Normal exports use the complete Matplotlib artist bounding box plus at least 6 pt of padding. This may change the final PNG/PDF canvas dimensions while leaving the physical axes-box ratio unchanged.
- The exporter checks the outer PNG pixels and automatically retries with more padding when rendered content reaches the edge. This is the primary clipping safeguard; manual crop inspection is only a spot check.
- For exact reference-page matching, disable automatic cropping and retain the calibrated fixed page. In that mode, programmatically or visually verify that all text stays inside the page because the automatic canvas expansion is intentionally unavailable.

## Legend clearance

The legend is anchored to an axes corner, so a dense upper-left or upper-right
region puts it straight on top of the curves it labels. `line_plot` therefore
checks, after drawing, whether any plotted point inside the axes falls within the
legend frame plus 2 pt, and if so grows the y range one tick step at a time until
it does not. Growing the range rather than shrinking or moving the axes is what
keeps this calibration intact: every dimension in this file stays fixed, and only
the data shrinks away from the legend.

Ticks are re-derived after each step, so the 4--6 uniform label rule still holds
afterwards; a range of 0--15 with a six-entry legend typically ends at 0--20.
The search gives up after 6 expansions and warns. Explicit `ylim` or `yticks` are
never overridden.

## Reference-matching procedure

1. Inspect the MATLAB source before inferring data or labels from pixels.
2. Use `pdfinfo` to measure the reference page.
3. Convert both PDFs with `pdftoppm -png -r 300 -singlefile`.
4. Compare axes boundaries, tick locations, label/annotation bounding boxes, colorbar placement, and several interior RGB samples.
5. Treat one-channel raster differences of roughly 1/255 and hairline polygon seams as renderer differences when the vector colors and geometry agree.
