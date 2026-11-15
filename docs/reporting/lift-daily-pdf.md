# Daily lift charts in the PDF report

The report section list now contains a separate, optional entry:
**Lift movements by purpose - daily charts**. It is unchecked by default. The
existing **Lift movements by purpose - stacked bars** overview remains a separate
option. Select either section or both.

With **Day = All days**, the daily section contains one chart per lift per
observation day, grouped by lift then date. With one date selected, it contains
only that date. Zero-movement days and partial first/last days are retained.
Each chart counts physical movements by recorded trip purpose, using the same
interval and empty-repositioning selection as the existing charts. Daily charts
for a lift share the same vertical scale across the selected dates.

The **PDF chart lift** selector offers **All lifts** or one lift from the selected
run's frozen configuration. It limits both PDF lift-chart sections. It does not
filter unrelated report sections. To export a PDF for one lift, choose that lift
and select the desired chart section. To export one day, also choose the date.
Every PDF uses the existing report generation and output location.

Excel retains its existing export button, per-lift sheets, day dropdowns,
formulas, counts and source data. The new PDF lift selector does not affect it.
No project setting or simulation calculation is changed.

## Command line

```text
python amr_app.py --generate-report RUN_DIRECTORY NEW_OUTPUT_DIRECTORY --sections lift_movement_daily
python amr_app.py --generate-report RUN_DIRECTORY NEW_OUTPUT_DIRECTORY --sections lift_movement_daily --lift-chart-lift-id Lift-2
python amr_app.py --generate-report RUN_DIRECTORY NEW_OUTPUT_DIRECTORY --sections lift_movement_stacks,lift_movement_daily --lift-chart-lift-id Lift-2 --lift-chart-day 2026-01-02
```

`--lift-chart-lift-id` is available on the project and legacy report command
lines, can be repeated for multiple lifts, and applies only to PDF chart
sections. Unknown lift IDs or dates produce an error instead of silently
exporting other lifts. Older logs without calendar dates retain explicit
simulation-day labels such as **Day 1**.

## Application boundary and verification

This update adds one section and native controls to the existing report panel
and report dialog. It retains the background worker, cancellation and frozen-run
verification. The report manifest records the selected lift IDs, day and whether
the daily section was requested. Save/reopen and Undo/Redo are unaffected because
the choices belong to report generation, not the project model.

Compatibility checks cover the existing Excel/CSV exports, default PDF section
selection, report insertion/navigation, report workers and project-run evidence.
New checks cover daily/combined reconciliation, midnight boundaries, zero days,
partial observations, relative-day evidence, selected lifts/dates, empty
repositioning, invalid IDs and propagation through the real report worker.
Visual review covers the native controls and rendered daily PDF pages. Installation
is bounded to reporting files with a checksum-verified rollback backup; Excel
builders, simulation code, project files and synced sources remain unchanged.
