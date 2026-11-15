# Contingency performance and lift packing — 4 November 2026

The inspected saved study covers seven days and five services. Its baseline has
26,217 generated obligations, including runtime-dependent reattempts; these are
not 26,217 independent original requests. A budget of 200 applies to each of four
comparisons, permitting 800 full-period simulations. A budget of one evaluates
only the no-staff baseline and cannot establish a staffed roster.

Profiling found repeated department-calendar work, repeated graph/lift searches
for identical insertion previews, a full scan of unresolved work for each shift
option, repeated empty simulations, and large indented JSON checkpoints. Progress
previously appeared only at trial boundaries.

Changes retain the native generator, task deadlines, inventory dependencies and
per-candidate lift queues. Calendar cache keys include input content and local
timezone identity. Corridor paths are cached independently of queues; journey
previews require identical times, loads, permissions and reservations and are
cleared on commit. Shift overlap counts use an indexed sweep with exactly the
previous inclusive/exclusive comparisons. Saves remain atomic and hash-checked.

The person can rearrange individual payloads inside a lift. Packing considers
permitted rotations, each person's floor space, height, non-overlap and the other
loads on a shared departure. The corridor footprint is separate. No stacking is
assumed. Packing effort is bounded; exhaustion is distinguished from impossible
fit. Individual generated obligations that demonstrably fit no lift produce a
specific setup finding; the former in-line envelope is not used for that finding.

Representative measurements on this machine (not a guarantee for every roster):

| Check | Before | After |
| --- | ---: | ---: |
| Weekly six-shift roster, original fixed envelope | 119.3 s | 13.8 s, identical result hash |
| Weekly six-shift roster, corrected flexible lift model | 81.1 s | 13.6 s, identical result hash |
| Shift-option ranking under profiling | 4.52 s | 0.052 s |
| One-trial four-comparison study | — | 10.8 s |
| One-trial checkpoint file | 78.8 MB | 51.4 MB |

The corrected lift model completes 157 obligations in that deliberately small
roster, versus 124 with the previous fixed envelope. It is still a failing roster;
these measurements are performance evidence, not a staffing recommendation.

Regression coverage includes the contingency UI and engine, calendars, schedules,
stock/inventory, lift contention, saved studies, cancellation/resume, exact overlap
counts and non-overlapping rotated lift layouts. Two older unrelated corridor
optimisation tests already fail in the installed baseline because their mock
does not accept the `prior_journeys` argument; that test mismatch is outside this
change. The relevant calendar tests and current lift regression suites pass.

Restart the application and create a new study after installation. Old study
evidence is retained, but source-version binding prevents resuming it with changed
calculations. No user project or existing study is rewritten by the update.
