# Checkpoint 2I — consistent staff switches and timeframe releases

Review date: 3 October 2026. Baseline: `e0b88d1`.

The global staff switches now have distinct, consistent effects on generated
tasks. Disabling global working patterns removes the shared daily calendar and
rotating-team definition, giving generated staff tasks one all-day roster. It
does not remove a requirement for staff. Explicit custom weekly hours remain
effective. The separate spreading switch controls timeframe releases, while
runtime handling continues to observe the applicable hours.

Previously the global enable switch affected generator windows but left runtime
patterns active. Legacy omitted Stores requirements were also recognised by
runtime handling but excluded from staff-assisted spreading. Generation, runtime
and preview now share effective staff-choice resolution through
`amr_staff_policy.py`. Explicit false remains authoritative for ordinary tasks;
the existing forced zone-handoff rules remain in place.

The legacy fallback retains its existing label, generated-ID, source and payload
recognition. Generated-ID normalisation is shared with the rule check so category
punctuation does not make generation and runtime disagree. Omission remains
omission in saved input and generated task metadata.

## Independent schedule references

Use Monday 5 January 2026, timeframe 08:00–18:00, four tasks and default staff
hours 09:00–17:00. The intersection lasts eight hours: four release slots divide
it into two-hour steps, excluding the end of the window.

| Settings | Task releases | Runtime handling requested at t=60 |
| --- | --- | --- |
| Omitted Stores choice or explicit true; both switches on | 09:00, 11:00, 13:00, 15:00 | Wait until 09:00 |
| Explicit false | Four releases at 08:00 | No staff booking |
| Spreading off; global patterns on | Four releases at 08:00 | Wait until 09:00 |
| Global patterns off; no custom hours | Four releases at 08:00 | Start at t=60, one roster |
| Global patterns off; custom Monday 10:00–14:00; spreading on | 10:00, 11:00, 12:00, 13:00 | Wait until 10:00 |

Nine tests in `tests/test_staff_calendar_switches.py` cover these combinations,
raw/editor parity, demand-preview agreement and the existing fixed-time schedule
behaviour. Two groups of two tasks share four slots rather than duplicating them.
Calendar inspection does not consume slots, and repeated generation does not
emit them twice. When global patterns are disabled, stored but inactive pattern
choices do not divide otherwise identical custom-hour groups.

With a preview horizon ending at 10:00, only the 09:00 task is shown. The preview
does not apply its independent unspaced-count formula to that assisted rule;
the expected count remains unestablished by that formula. The earlier unstaffed
count test now explicitly uses false to preserve its independent scope.

Global staff dialog tooltips explain both switches, custom-hour precedence and
the distinction between release scheduling and staff handling. The two switches
now have individual source/default/precedence/validation/test contracts. No major
UI workflow was changed.

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_staff_calendar_switches tests.test_staff_requirement tests.test_scheduled_dispatch -q
.\.venv\Scripts\python.exe -m verification.run --output verification/latest
.\.venv\Scripts\python.exe -m verification.smoke --config ltn.json --minutes 60 --output verification/latest/staff-calendar-ltn
```

The full pack passed **969 tests in 126.842 seconds**, with **zero broken evidence
links** and unchanged source hashes during testing. Both bounded LTN runs completed
four tasks with zero failures or pending tasks, retaining outcome hash
`5368460ed4fd5fd466e832b82d3d6358977abfaccbb456d45e268cfb7c0ab474`.
Local outputs are `latest/staff-calendar-pack-build.txt` and `latest/staff-calendar-ltn/`.
The source `ltn.json` and its unrelated local changes were preserved. This bounded
regression does not establish full LTN acceptance.

## Changed results and limits

Legacy Stores timeframe projects with spreading enabled can now release work
across the staff window instead of releasing everything at timeframe start.
Disabling global patterns now also removes their runtime waiting and team
rotation; custom weekly restrictions remain. These are intentional corrections
to the settings exposed by the application. Fixed scheduled releases, explicit
staff choices and historical logs are preserved.

The existing no-overlap/out-of-hours generation fallback is retained. Complete
acceptance of that policy, heterogeneous department-hour intersections within
pooled timeframe groups, arbitrary work/rest cycles, complete utilisation and
broad scalar validation remain open. Direct/static legacy task metadata is not
rewritten by generation settings. Staffing is still a sizing model rather than
a fixed-capacity queue or optimisation model.

Next: return to the broader configuration audit, starting with generation input
checks and visible findings for malformed or unsupported options. The remaining
resource, geometry, approved UI and tutorial checkpoints retain their original
scope and order.
