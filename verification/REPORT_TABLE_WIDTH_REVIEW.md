# Report table width review

## Change

Both dataframe tables and weekly staff timetables now use `PageWidthTable`.
Section column widths are proportions, scaled to the actual ReportLab frame
instead of being fixed to a nominal paper size. Header words receive minimum
widths where the frame permits. Cell text retains its existing font sizes and
wraps inside the allocated columns. Tables align with the body text margins.

The rule also applies to split tables and their repeated headers. It supports
A3/A4 portrait and landscape pages without applying an A3 cap to other templates.
Page sizes and margins remain those chosen by each report section.

## Complete saved-report review

The proposal report was regenerated from the frozen log and report configuration
for `proposal-1_results/run_20261010_152221_7j5ol3jm`. Every one of its 47 pages was
rendered and visually reviewed, including all contents pages, charts, tables,
continuations and three floor heatmaps. Dense tables were also inspected at full
render resolution.

- 35 pages contain tables, including 13 A3 landscape pages.
- Every table spans 100% of the frame's usable width.
- All table left/right borders align with the body text frame.
- No text crosses a table's column rules or the page's print margins.
- The original report had narrow or misaligned tables on 34 of those pages.

The regenerated PDF is `output/pdf/proposal-1-full-width-report.pdf`.
Original saved reports and simulation evidence were read without modification.

A larger regression report was also regenerated from the frozen six-floor LTN
run, with all report sections selected. All 324 pages were rendered and visually
reviewed, including timetable continuations, dense storage tables and six A0
floor drawings. The 311 table pages all use 100% of their frame width, with no
text crossing column borders or print margins. All 92 PDF bookmarks resolve to
valid pages. The temporary PDF is `tmp/pdfs/report-width-ltn/report.pdf`.

## Regression checks

88 tests passed across table width/pagination, report structure and PDF insertion,
KPIs, storage reporting, staff reporting, energy reporting, drop-off-zone reporting
and lift trip cohorts. The new table tests independently verify actual PDF border
positions on every continuation page for all four A3/A4 orientations, retention
of every data row, dense header allocation, and all timetable continuation entries.
