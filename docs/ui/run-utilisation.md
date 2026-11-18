# Quick utilisation review

In **Simulate**, select a completed **Memory only** run and choose **View utilisation**.
The dialog shows AMR and lift averages, and separate sortable tables of utilisation,
busy minutes and idle minutes. Resources with no recorded activity are included.
The busiest resource appears first. No save, export or simulation rerun is required.

## Calculation and compatibility boundary

The source is the selected run's immutable inputs and retained event store, never
current editor inputs. AMR busy intervals use the report's segment selection:
movement, handling, waiting, charging and repositioning. Lift busy intervals use
transfers and empty repositioning. Both reuse the report's interval merger and
total functions, including its one-second gap tolerance. Shared routes and
overlapping segments count once per physical resource.

The denominator begins at simulation time zero and ends at the greater of the
frozen configured demand horizon and last recorded event time. It therefore
includes initial idle time, the whole configured period and any later work.
Segment plans are clipped to this window. The window is displayed explicitly;
it can differ from the existing report's first-to-last-event observation window.
Existing report calculations have not changed. A zero-duration window displays
an unavailable percentage rather than dividing by zero.

Stopped/partial runs and reduced-logging runs cannot establish these full-run
figures. The action requires a completed memory run and full event evidence.
Stopped-run review remains available through Investigation and Playback.

## Application and UI scope

Existing Windows/PySide6 application. This adds one native dialog to the existing
run-review controls; it retains the current workspace, theme and command paths.
It does not change the simulator, project archive, compact events, exports,
report schema, saved-run review, CLI, editing, history or recovery behavior.

The existing selected run owns selection. Loading uses QRunnable/QThreadPool and
the MemoryRun store lease; closing cancels reading and late results are ignored.
The dialog is modal, preventing selection or document changes during review.
Only the small aggregate is cached per run. Saving or discarding a run removes
its cached aggregate; the worker releases its source when finished. Closing a
loading dialog does not discard its source run.

Native tables expose names, values, keyboard selection and sorting. The dialog
inherits application styling and fonts. Labels wrap, and a Close button/Escape
returns to Simulate. No new settings or project migration is introduced.

## Validation evidence — 17 November 2026

- Passed: 11 feature tests and all 10 existing memory-run tests, including
  playback, investigation, publication, PDF generation, cancellation, memory
  limits, reduced logging, partial runs and document switching.
- Passed: independent overlap/duplicate, waiting, charging, idle resource,
  zero-window, delayed-start, overrun and clipping cases.
- Passed: an actual completed in-memory multi-payload lift journey counted its
  one-second transfer once, included the unused lift at zero, and wrote no files.
- Passed: background loading, closing/cancellation, ignoring late results,
  repeat-view cache reuse and cache removal when discarded.
- Passed: native dialog rendering at 100% and 150%, with AMR and lift tables;
  tab-bar keyboard navigation switches views. Screenshots and timing records
  are retained in the task workspace under `utilisation-work`.
- Timing: the summary calculation over 200,000 synthetic segment records took
  approximately 0.4 seconds in the test environment. This measures aggregation,
  not disk loading or a complete large simulation. First view also scans the
  retained compact store; subsequent views reuse the aggregate.
- Not assessed: screen-reader certification, mixed-monitor transitions and
  other operating systems. Native widgets and the existing theme are retained.

Installation saves exact originals and records checksums. Rollback restores the
original project-runs panel and removes only the four newly added feature,
test and documentation files. User projects and simulation evidence are untouched.
