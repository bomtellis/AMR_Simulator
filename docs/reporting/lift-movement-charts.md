# Lift movements by trip purpose

Select a completed run in Simulate and choose **Report selected run**. The new
**Export stacked lift charts (Excel)** button creates one editable stacked column
chart per lift, including configured lifts with no recorded movements. Each lift
sheet has a **Day** dropdown and **Empty repositioning** Yes/No selector. The
workbook retains every observation day regardless of the initial selection.

For a PDF, select **Lift movements by purpose - stacked bars** in the report
sections list. This section is unchecked by default. The **Stacked lift charts**
controls choose the day, interval and inclusion of empty repositioning. Blank or
**All days** combines counts at the same clock time across all observation days;
it does not calculate an average. A PDF contains one chart per lift for that
selection. Its pages are A3 landscape with vector charts. Existing line profiles
and five-minute/hourly usage exports are retained.

## Counting and classification

- A bar counts physical lift movements beginning in each 5, 15, 30 or 60 minute
  interval; 30 minutes is the default. It does not measure travel duration,
  occupancy, passengers or utilisation percentage.
- Colours represent recorded service categories, such as Catering, Linen,
  Pharmacy, Waste and Stores. Outbound and return trips share the same purpose.
- A movement carrying several purposes counts once as **Mixed purposes**.
- Empty car repositioning is a separate grey series, included by default for
  these charts. The selector changes chart counts only.
- Missing service evidence remains **Unclassified**. An identifiable empty AMR
  movement without a service purpose is **Empty AMR travel**. Categories are not
  inferred from payload names.
- Source times retain their precision until binning. A midnight start belongs
  to the following day. Missing durations do not remove countable movements;
  missing or invalid start times produce an explanation rather than being
  silently omitted.
- Calendar days include zero-movement days in the frozen observation period.
  Partial first/last days stay partial. Old logs without a calendar epoch use
  explicit **Day 1**, **Day 2** selectors and time within each simulation day.
- Each Excel chart has a fixed vertical scale based on its all-days peak so
  changing the day does not disguise differences in counts. The Movement counts
  sheet provides typed, filterable source counts and the event-file checksum.
  Formula-backed count tables beneath the charts remain editable.

## Saved evidence and background operation

The Excel export reads verified frozen configuration and recorded events, using
the same evidence checks as the existing third-party exports. It does not run a
simulation or change the project. Work runs in a child process. The completed
workbook is published atomically after rechecking the source checksums; failure
or cancellation leaves the previous completed output in place. PDF generation
retains the existing report worker, report manifest and provenance checks.

The Excel builder uses the existing spreadsheet runtime. No new Python package
or Excel installation is required to create a workbook. Excel is used for the
native filtering verification during delivery.

## Command line

```text
python amr_app.py RUN_DIRECTORY --lift-charts-xlsx lift-movements.xlsx
python amr_app.py RUN_DIRECTORY --lift-charts-xlsx lift-movements.xlsx --lift-chart-day 2026-01-02 --lift-chart-bin-minutes 15 --lift-chart-exclude-reposition
python amr_app.py --generate-report RUN_DIRECTORY NEW_OUTPUT_DIRECTORY --sections lift_movement_stacks --lift-chart-day 2026-01-02
```

The report CLI also accepts `--lift-charts-xlsx`, `--lift-chart-day`,
`--lift-chart-bin-minutes` and `--lift-chart-exclude-reposition`. Standalone Excel
export skips PDF generation. Third-party CSV and trip-table Excel switches keep
their existing meanings and cannot be combined with the chart export switch.

## Delivery verification

The affected routing and simulation code is unchanged. Report/export tests cover
the day boundaries, per-purpose totals, shared loads, unavailable purposes,
empty/unused lifts, legacy elapsed times, duration-free movement evidence,
native chart/formula structure, source mutation, cancellation, background export,
PDF opt-in and forwarding of chart controls. Existing lift, energy, storage,
staffing, project-run and PDF report regressions are also included.

The representative completed LTN run `run_20261109_192517_qocx7w0b` contains
11,235 AMR lift transfers and 7,628 empty car reposition movements. All 18,863
movements reconcile to the new counts across eight lifts and eight calendar
dates, including partial days. See `verification/lift-movement-charts-20261109`
for delivery evidence. Installation uses a bounded file manifest and a
checksum-verified rollback backup; project files and synced sources are excluded.
