---
title: Report structure and PDF insertion
nav_order: 2
parent: Investigate and report
---
# Report structure and PDF insertion

The Report page includes **Export 5-minute lift usage CSV** and **Open lift usage
CSV**. This restores the existing lift-cohort export, including five-minute and
hourly rows, without generating a PDF. Rows contain each lift's transfer trips,
reposition trips, total trips, travel time and average trip time; the `cohort`
column identifies the interval. Dates remain separate and zero-trip buckets are
included. The CSV is saved as `report_lift_cohorts.csv` in the selected run's new
report output folder. Normal PDF generation also writes this CSV beside the PDF.

Every generated report has a separate title page, a linked contents page (which
continues over multiple pages when needed), numbered sections and numbered
subheadings. Numbers follow the selected section order. PDF bookmarks and contents
links point to the final page locations, including landscape pages and heatmaps.
The report title can be set in either report dialog or with `--report-title`.

Report tables fill the usable width of their actual page, including A3 landscape,
A3 portrait and A4 templates. Column proportions are preserved, with room for
header words and wrapped cell text. Continuation pages repeat the headers and
retain the full width; weekly staff timetables use the same sizing rule.

## SLA categories and targets

Select **SLA categories and assigned targets** (`sla_categories`) to show:

- Effective enabled category rules, department overrides and department-group
  rules, using the simulator's own rule resolver and waste-stream precedence.
- Outbound targets and separately configured return/collection targets, with
  their scope, exact seconds, minutes and completion rule.
- Timeframe deadlines, including overnight windows. These use time remaining
  from actual task release to the deadline rather than a fixed duration.
- Positive targets on explicit configured tasks.
- Targets actually recorded in the run, grouped by logistics stream and exact
  target, with request counts, completions, overdue counts and compliance.

Zero/negative/invalid targets are not SLA assignments. Disabled generation rules
are excluded. Without a matching configuration, the report can show recorded
targets but cannot establish configured assignments. Configuration and observed
tables are also saved as `<report>_sla_assignments.csv` and
`<report>_sla_observed_targets.csv`.

## Insert selected sections into an existing PDF

In the project Report panel or standalone report dialog:

1. Select the report sections to add (clear the other checkboxes).
2. Choose an **Existing PDF**.
3. Leave the insertion position at **Append to end**, or specify an existing
   page to insert after. `0` means before the first page.
4. Generate the report. Project reports save a new PDF under the selected run's
   reports folder. In the standalone dialog choose a different output PDF.

Only selected sections are rendered. Existing pages, charts and drawings are
copied, retaining their printed pagination, bookmarks and contents links. The
inserted supplement has its own title, linked contents and numbering starting
at page 1. Existing contents pages are preserved; they are not rewritten as a
single combined index. This allows reuse of PDFs with no original report data.
The original PDF is never overwritten.

Selected sections still require analysis of the matching simulation log. To skip
analysis completely, insert an already prepared sections PDF from the standalone
dialog's **Prepared sections PDF** field, or the command below.

```powershell
python report/amr_report_main.py simulation_steps.csv --config-json config.json `
  --report-sections sla_categories,operational_kpis --omit-drawings `
  --existing-pdf original.pdf --insert-after-page 5 -o combined.pdf

python report/amr_report_main.py --existing-pdf original.pdf `
  --insert-pdf prepared_sections.pdf --insert-after-page 5 -o combined.pdf
```

Omit `--insert-after-page` to append. Project reports record the original PDF's
path and checksum, verify it is unchanged during generation, and retain the
selected run's frozen-input checks.
