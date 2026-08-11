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

- PDF page: 368 x 299 pt
- Axes rectangle: left 52, bottom 47.5, width 310, height 231 pt
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

## Reference-matching procedure

1. Inspect the MATLAB source before inferring data or labels from pixels.
2. Use `pdfinfo` to measure the reference page.
3. Convert both PDFs with `pdftoppm -png -r 300 -singlefile`.
4. Compare axes boundaries, tick locations, label/annotation bounding boxes, colorbar placement, and several interior RGB samples.
5. Treat one-channel raster differences of roughly 1/255 and hairline polygon seams as renderer differences when the vector colors and geometry agree.
