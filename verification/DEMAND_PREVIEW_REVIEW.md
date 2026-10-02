# Demand preview checkpoint — 2 October 2026

Open **Home → Demand preview → Build preview** in the editor. The workspace
uses a frozen copy of the project and runs its calculation in the background.
It does not dispatch robots or change inventory. The default period comes from
the simulation settings; without an end it uses one day. The optional end field
accepts an ISO date/time. Limits are 31 days and 20,000 task records, with an
explicit failure rather than silently truncated totals.

## Review steps

1. Build the current LTN preview. At this checkpoint it contains **1,224 planned
   task records** and **190 rules with unknown total demand**, including returns.
   These are not completion or journey totals.
2. Filter by department, category, payload, date and route profile. Search for a
   destination. Tasks and the hourly timetable should show the same filtered
   demand. The Rules tab always covers the whole preview.
3. Select a task to inspect its originating group or department rule, effective
   endpoints, priority, staff handling and return settings. Select a rule for
   inherited values and precedence. Stored destination values can differ from
   effective department destinations; both remain visible.
4. Inspect disabled rules, suppressed category defaults and department overrides.
   Their explanations should match the intended project configuration.
5. Edit a setting. Confirm the preview becomes stale and cannot be exported until
   rebuilt. Export includes frozen inputs, rule provenance, task records and totals.

## Counts and limitations

The preview evaluates fixed scheduled and timeframe components using the existing
generator. Scheduled/sporadic rules can show their fixed component with an unknown
additional total. Thresholds, inventory consumption, legacy waste and returns
depend on runtime events; unknown is explicitly different from zero.
Mass collections are not represented as AMR task totals.

Per-rule counts sum to the task table. A separate arithmetic check calculates
expected counts for simple scheduled/timeframe rules with one distinct route pair
and unrestricted department hours (timeframes also require no staff spacing).
Other rules explicitly say **Not assessed** for independent count verification.
LTN's complex rules currently have no independently assessed counts; zero count
mismatches does not mean all LTN demand has been independently verified.

The period includes its end instant. Existing department scheduling can move
earlier start-day releases to time zero; this is exposed and covered by a reference
test. Daily schedule sweeps show planned releases, not a promise about simulator
poll timing or dispatch. Cross-day opening adjustments and more complex calendars
need additional independent references. Preview identifiers are stable for frozen
inputs, but are not simulation event identifiers. Generated records now carry
additive rule identifiers/paths; event-log persistence belongs to Results investigation.

For waste rules, stream defaults and department stream values add precedence layers.
The preview shows their resolved configuration and the documented order; it does
not claim exact per-field source attribution through every derived waste value.

## Evidence

Nineteen new acceptance tests cover hand-calculated schedules, timeframe quantities,
two groups, explicit-task quantities, inclusive boundaries, department destinations,
override precedence, missing departments, inactive rules, unknown runtime demand,
filters, stale exports, background building, repeatability and unchanged LTN input.
The existing LTN check test was made independent of the removed D26 rule so your
project correction does not become a test failure.

The full suite passed **191/191**. Two six-hour LTN demand windows both completed
203 tasks, failed none, left none pending and produced outcome hash
`593945bef454f5d602c82f0f15180cbc26285d3711d93102d483635da36faab5`, matching the
earlier checkpoint. Your uncommitted LTN edits are preserved and excluded from
the implementation commit. Generated evidence snapshots include the actual tested
LTN bytes so the results remain reproducible.

Pause here for user verification before implementing Results investigation.
