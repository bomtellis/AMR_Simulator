# Independent category teams, shift periods and flexible releases

Implementation baseline: current Windows application, 4 November 2026.
Scope: existing non-modal Human contingency study, its shared callable/CLI
operations and report exports. Synced sources and user projects remain unchanged.

## Behaviour

- Optional version-1 release policies default to fixed. Eligible generated tasks
  can align to staffed intervals, excluding breaks, using native department and
  category calendars. Scheduled and explicit tasks remain fixed. Deadlines move
  by the authorised delay, never beyond the category allowance. Dependency
  delays and unmet stock remain visible. The native generator is unchanged.
- Dedicated categories can override default shift rules independently. Exact
  start/finish periods, overnight shifts, days, breaks and per-team limits feed
  the same candidate generator as start-window/length search. All dedicated
  teams run in one simulation with the same lift queues and inventory lifecycle.
- The first dedicated staffing candidate seeds every category with released
  obligations. Further additions use relative category completion and staffing
  to prevent the largest absolute task count monopolising the bounded search.
  Simulated passing candidates still rank by staffed hours, combined peak, trips
  and travel. There is no claim of a globally optimal roster.
- Roster search coverage uses the original-to-latest permitted timing interval,
  so a failed late candidate does not prevent the search testing earlier staff.
- Dedicated results contain per-category staffed hours and peak people. Shared
  results leave these dedicated-only columns empty and attribute active time.
  Original/revised task timing is inspectable, exported and summarised in PDF.

## Acceptance evidence

| Check | Result |
| --- | --- |
| Domain and regression tests | 330 passed: human demand/stock/returns/lifts, timing policies, exact periods, independent teams, cancellation/resume, UI, reports and saved projects, plus existing generation/staff/inventory/lift regressions. |
| Hand-calculated flexible delivery | Release 120 → 600 s, deadline 480 → 960 s, delivery at 614 s; quantity and source demand unchanged. |
| Return identity and readiness | Return ready at 254 s moves to 600 s; deadline 454 → 800 s; the same container returns to source. |
| Independent teams | Two concurrent categories each receive one person even when the per-team maximum is one; independent periods and limits are honoured. Existing shared-lift contention regression passes. |
| Overnight boundary | Sunday 22:00–Monday 06:00 covers a Monday 00:00 study start; full eight-hour shift charged, no pre-study demand inferred. |
| UI | Current LTN project opened read-only for verification. Normal and 14pt renders at 752×700 retain visible footer actions; forms scroll and labels retain units. Inactive search/period fields are hidden. |
| Background/resume | Existing QProcess and edit locks retained; independent-period cancellation/resume matches uninterrupted results. Callable partial overrides normalise before saving so UI reopening does not falsely mark edits. |
| Reports | Four passing comparisons, two categories with different periods; task CSV timestamps checked; two-page PDF rendered and inspected. |
| Weekly replay | 14.10 s for the same saved six-person weekly candidate: 157 completed, 133 trips, 25,973 obligations, 48 staffed hours, zero retimed tasks with flexibility disabled. This candidate is still failing; the measurement is not a staffing recommendation. |
| Not covered | Live mixed-monitor transitions, screen-reader operation and site calibration of human carrying/handling assumptions. |

Evidence is retained with the installation backup. Existing results need a new
study after this software change; saved project settings remain editable and
old results remain viewable/exportable. Installation changes only the listed
application/test/documentation files and retains rollback copies. No user project
or synced source is migrated or overwritten.
