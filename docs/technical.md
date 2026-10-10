---
title: Technical reference
nav_order: 9
has_children: true
permalink: /technical/
---
# Technical reference

Most operational users can work through the graphical application. This section
supports source setup, explicit JSON studies, command-line runs and advanced
geometry/lift investigations.

## Input formats and units

A `.amrproj` is a portable project with drawings and revisions. The simulator's
CLI takes **JSON**, not the project archive. Use **Export JSON** from the
workbench to create simulator input and an adjacent drawings folder. Exported
paths are absolute for existing-tool compatibility; export again after moving
the project to another computer.

Use metres for coordinates and dimensions, kilograms for mass, seconds for
fields ending `_sec`, kWh for battery capacity, kW for charge rate, and watts for
motor power. Fields explicitly labelled minutes or percent retain those units.
Date/time strings and schedules must match the run and department calendars.
Keep identifiers unique and references consistent; Project checks expose many
malformed inputs without establishing every option's operational validity.

Read [scenario configuration](user-guide/02-understanding-a-scenario-config.md)
for the main JSON sections. Start from a validated example rather than copying
partial README snippets containing comments or ellipses, which are not valid JSON.

## Command-line simulation

From the repository root, using the same environment as the workbench:

```powershell
# A fresh illustrative JSON; do not overwrite your study.
.\.venv\Scripts\python.exe simulator.py --write-example "C:\AMR studies\example.json"

# An exported/checked study, with an explicit output filename.
.\.venv\Scripts\python.exe simulator.py --config "C:\AMR studies\hospital.json" --verbose --verbose-csv "C:\AMR studies\simulation_steps.csv"
```

Create the destination folder first. The example writer provides illustrative
input, not a validated hospital or Detailed-mode template. CLI runs do not provide
the workbench's complete save/check/run gate or revision-bound review workflow.
Use saved project runs when that evidence binding matters.

Use `simulator.py --help` for output options, including failure, transport-matrix,
route-length, charger-estimate and scenario-impact CSVs. `--interactive` enables
interactive operation; Ctrl+C interrupts and saves the available CSV. An
interrupted log must be interpreted as partial observation.

## Command-line reporting

```powershell
.\.venv\Scripts\python.exe report\amr_report_main.py "C:\AMR studies\simulation_steps.csv" --config-json "C:\AMR studies\hospital.json" --omit-drawings -o "C:\AMR studies\report.pdf"

.\.venv\Scripts\python.exe report\amr_report_main.py "C:\AMR studies\simulation_steps.csv" --config-json "C:\AMR studies\hospital.json" --lift-csv-only --lift-travel-csv "C:\AMR studies\lift-travel.csv"

.\.venv\Scripts\python.exe report\amr_report_main.py "C:\AMR studies\simulation_steps.csv" --config-json "C:\AMR studies\hospital.json" --department-review-only --department-review-dir "C:\AMR studies\department-reviews" --department-review-formats both
```

Use the JSON saved for the run, not a later edited project. Section IDs, PDF
insertion and period inputs are documented in [report structure](report-structure.md)
and [KPI definitions](report-kpis.md). Use `report/amr_report_main.py --help`
to inspect the supported options in your installed revision.

## Advanced studies and developer evidence

- [Geometry and movement](reference/geometry.md): Detailed readiness and the separate geometry workbench.
- [Lift planning](reference/lift-planning.md): confirmed CAD interpretation, candidate evaluation and frozen comparison evidence.
- [Verification reference cases](https://github.com/bomtellis/AMR_Simulator/tree/main/verification): source contracts and reproducible checks, with revision-specific limitations.

The legacy launcher and `visualiser/amr_editor_main.py` remain source entry
points for existing workflows. The primary instructions in this guide use
`amr_app.py` and the unified workbench.
