# Reports from runs in memory

Select a completed **Memory only** run in Simulate, choose **Report selected run**, select the report sections, and choose **Generate report**. Choose a destination folder when prompted. A new report folder contains the PDF, supporting tables, and report manifest.

The report uses the run's frozen configuration, drawings, and recorded events. Current editor changes do not affect it. It does not rerun the simulation or save a project. The run stays available for review, another report, or **Save run**.

Report input is prepared in the background in a temporary folder, verified by the same checks used for saved runs, and removed after completion, cancellation, or failure. **Stop generation** cancels preparation or the report worker. Reports require a completed run with full event evidence, as they do for saved runs. Partial and reduced logging runs remain available through their existing review and save actions.

The Report panel also supports the existing lift usage CSV export for memory runs. Standalone third-party lift exports and chart workbooks remain available for saved runs.

Python callers can pass a completed `MemoryRun` to `amr_project_report.generate(run, output, sections, **options)`. The report manifest identifies `source_storage` as `memory` and preserves the original run key and frozen configuration digest.
