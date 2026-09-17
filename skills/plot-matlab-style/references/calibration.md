# Calibrated MATLAB-style geometry

Use these measurements when the user requests the established line/contour style or asks to match the original MATLAB PDFs. Coordinates are PDF points from the lower-left page origin.

## Shared typography and strokes

- External LaTeX: `text.usetex=True`
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

- PDF page: 368 x 299 pt **nominal**; see "Page expansion" below
- Axes rectangle: left 52, bottom 47.5, width 310, height 232.5 pt. The exact 4:3 width:height box is the current invariant and supersedes the legacy measured height of 231 pt.
- Legend: upper left, square frame, white background, 1 pt border
- Figure annotation `(a)`: near the page upper-left corner
- Calibrated reference content: `y=x`, `y=x^2`, both axes 0-1

## Filled-contour figure

- PDF page: 370 x 308 pt
- Main axes rectangle: left 51.5, bottom 49.5, width 263.5, height 231 pt
- Colorbar rectangle: left 332, bottom 49.5, width 16, height 231 pt
- Main axis range in the reference: x 0-1, y 0-2
- Default signed-data map: `RdBu_r`, 200 levels, symmetric limits
- Colorbar outline/ticks: 0.5 pt; Times New Roman 14.4 pt tick labels
- Colorbar title: LaTeX, 16 pt
- Calibrated reference data: `Z = sin(2*pi*X) + cos(4*pi*Y)`
- The 263.5 x 231 pt main-axes rectangle is the legacy maximum frame, not a default contour ratio. Ask the user for the desired axes-box width:height ratio, fit it exactly inside this frame, and align the colorbar vertically with the fitted axes.

## Page expansion

The nominal page leaves 368 - (52 + 310) = 6 pt to the right of the axes and 52 pt to its left.
That fits the calibration content, whose tick labels are as short as `1` and `0.5`, but not real
data: `0.15` on the y axis needs roughly 26 pt plus the 6 pt tick pad plus the rotated y-label, and
a final x tick of `25` overhangs its centre by more than 6 pt. Both used to be silently cut off.

`_expand_page_to_fit` therefore measures the drawn figure and, when any artist would fall outside
the page, grows the page by exactly the overflow while each axes rectangle keeps its size in points
and shifts to stay in the same place relative to the data. Everything is a pure translation at fixed
font size, so a single measurement suffices. A figure that already fits with 1 pt to spare is left
untouched, which keeps both reference demos at exactly 368 x 299 and 370 x 308 pt.

Consequence for checking: compare the *axes rectangle*, not the page, against this file. A page of
374.5 x 299 pt with a 310 x 232.5 pt axes rectangle is correct; a page of exactly 368 x 299 pt with a
shrunken axes rectangle is not.

After saving, the exporter also checks the outer two PNG pixel rows and columns.
If they are not blank white canvas, export fails instead of returning a possibly
clipped figure. This deterministic artist-bound plus border validation replaces
manual image segmentation; visual review is only a scientific/layout spot check.

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
