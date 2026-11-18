# Find AMR fleet size

Open **Runs → Find AMR fleet size…**. Choose an AMR type, starting quantity and
maximum quantity to try. The target utilisation defaults to **75%** and is a
reference only: the recommendation is based on task outcomes, regardless of
utilisation. Other AMR types keep their quantities from the editor snapshot.

After the standard project checks, a passing starting fleet is reduced one AMR
at a time until the first failing trial. The previous passing quantity is
recommended. If the starting fleet fails, the search instead increases the
quantity one AMR at a time until it passes or reaches the maximum. Zero is a
valid trial: another AMR type may already provide enough capacity. If zero
passes, it is the lower bound and no artificial failure is created.

Each trial uses the normal engine, full compact event logging in SQLite memory,
deferred exports, and the current configured simulation period. Its first
recorded task failure raises `TaskFailureStop`, unwinding the event handler
immediately. The failure task ID, time and reason are copied into the summary.
No later events or report/evidence finalisation are run for that trial. The
event store and routing executor are closed on success, failure, cancellation
or exceptions. Trial evidence is discarded before constructing the next trial;
only compact summaries remain in the dialog. The document's existing retained
memory runs continue to count against the shared memory budget.

Successful-trial utilisation reuses `amr_run_utilisation.summarise_utilisation`:
overlapping recorded movement, handling, waiting and charging intervals count
once; inactive robots count at zero; the window includes the configured horizon
and any work completed later. The table shows average utilisation for the
selected AMR type. Failed trials cannot establish a full-run utilisation.

The dialog does not change quantities or save the project or simulation files.
Set the recommended quantity in the editor when ready. Cancel search, Escape,
or closing the dialog cancels the worker and waits for its cleanup before
closing. Incomplete runs, runs with unfinished tasks, empty workloads, errors,
and searches that reach the maximum without a pass produce no recommendation.
Changing settings clears a previous recommendation.

The result is the smallest **tested** passing quantity next to the first
failure boundary. Smaller quantities beyond that boundary are not tested;
nonmonotonic behaviour caused by congestion or resource contention is possible.
This is one-type sizing for the current workload and fixed other quantities,
not a global optimisation of the mixed fleet. The search uses the simulator's
existing definition of task failure, including configured deferral limits.

## Application and compatibility brief

- Existing Python 3.13 / PySide6 editor; Runs panel remains the entry point.
- A native bounded dialog reuses the application's stylesheet, form controls,
  read-only table, standard checks and `QThreadPool` worker pattern.
- Inputs are frozen by `MemoryRuns.prepare`; project edits and concurrent runs
  are locked while the modal sizing dialog is open. No application data format,
  export command, normal simulation default or existing run review is changed.
- The new engine flag defaults to false. Ordinary simulations retain all task
  failures and their usual evidence and cleanup behaviour.
- Source-graph reuse queries covered `MemoryRun` and
  `simulator.Simulation._record_failed_task`; source inspection confirmed the
  memory-store, failure, cancellation, checks and utilisation dependencies.

## Acceptance evidence

Verified 17 November 2026 in the application's Windows Python 3.13 environment.

| Check | Result and evidence |
| --- | --- |
| Boundary search | Pass: real three-task case passes with 4 and 3 AMRs; 2 AMRs stops at the first availability failure at 0.6 simulated seconds; recommends 3. |
| Increasing search / fixed types | Pass: starts at zero of selected type, increases to first pass, and preserves other AMR quantities. |
| Immediate failure / normal engine | Pass: failing trial records one failure, handles no later event and closes memory storage; normal run records both failures. |
| Cancellation and errors | Pass: cancellation between and during trials, close during work, input-check cancellation, incomplete/no-work cases and maximum limit covered. No recommendation is claimed for inconclusive searches. |
| No outputs / memory budget | Pass: trial SQLite connections use `:memory:`, no simulation output is opened, inputs remain unchanged and dialog search leaves no retained memory run. |
| Existing workflows | Pass: combined 80 tests cover sizing, memory-run publication/report generation, utilisation, engineering reference cases, failure investigation, task deferral and run controls. |
| Dialog / entry point | Pass: actual asynchronous dialog search and Runs button exercised; editing locks restored on close. |
| Display scaling / keyboard | Pass: rendered and inspected at 100% and 150%; form labels, result summaries, table and actions fit. Keyboard Tab moves from target to starting count. Failure reason is available in the cell tooltip. |
| Assistive technology / mixed monitors | Not tested with a screen reader or across physical monitors. Native widgets and accessible names are provided. |
| Packaging and project migration | Not applicable: source installation only; no packaging, project schema, preferences or layout migration. |

Workspace evidence: `tests/test_fleet_sizing.py`, `verification-1.json`,
`verification-1.5.json`, and `fleet-sizing-{ready,result,runs}-{1,1.5}.png`.
Installation uses exact original hashes and backs up every replaced file; see
the installation manifest and backup directory for rollback.
