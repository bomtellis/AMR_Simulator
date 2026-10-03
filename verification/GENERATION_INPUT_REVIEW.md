# Checkpoint 2J — raw generation inputs and unsupported settings

Review date: 3 October 2026. Baseline: `bdd2ab4`.

Generation input checks now run before editor defaults, simulator construction
and direct task-manager generation. Previously a JSON string such as `"false"`
could become true through editor normalisation while the generator interpreted
it as false. Unknown modes could silently generate no work. Invalid staff
settings could be replaced by defaults before the user could inspect the problem.

`amr_generation_inputs.py` provides a shared, non-mutating check. Errors include
the exact JSON pointer. The editor's generation-settings setter also checks
before replacing its stored settings, so rejection leaves the project unchanged.

## Covered input contracts

| Input | Accepted | Rejected |
| --- | --- | --- |
| Selected generation/staff flags | JSON true/false; omission retains inheritance | Strings, numbers, null, containers |
| Generation mode | Existing named modes or blank default | Unknown names and non-strings |
| Initial staff and payload multiples | Finite whole values at least one, including numeric strings | Fractional, zero, negative, boolean, null, non-finite |
| Handling, collection and return delays | Finite non-negative values, including numeric strings | Negative, boolean, null, non-finite |
| Polling interval | Finite non-negative value; zero keeps the runtime minimum | Negative, boolean, null, non-finite |
| Staff pattern | Fixed/rotating patterns and existing category aliases | Unknown names and non-strings |
| Global/custom staff hours | HH:MM; end time may be 24:00 | Invalid times and non-boolean custom enable switches |
| Nested settings | Objects/maps/lists appropriate to the field | Containers that cannot represent those settings |

Checks cover category settings, department overrides, group payloads, known
legacy categories, global staff settings and applicable static-task fields.
Department waste streams retain both supported forms: names and setting objects.
Global pattern definitions use canonical names; category pattern selections retain
their existing aliases. This remains a bounded input contract, not a complete schema.

## Unsupported work/rest cycles

The allocator alternates rotating teams at fixed four-day boundaries. Stored
`work_days` and `rest_days` do not implement a configurable cycle. Project Checks
now reports custom counts as `GENERATION_UNSUPPORTED`, with kind `unsupported`,
the affected field and the actual fixed behavior. The setting is preserved so it
can be inspected rather than silently overwritten.

The existing warning acknowledgement workflow permits an exploratory run. It
records acceptance of the limitation, not execution of the requested cycle.
Editing demand settings makes the finding evidence stale and prevents reuse of
the old run readiness. Direct CLI constructors reject malformed values, but
unsupported-warning acknowledgement remains a Project Checks workflow.

## Acceptance and review

Ten tests in `tests/test_generation_input_validation.py` cover import/runtime
agreement, precise error paths, non-mutation, direct-manager/setter protection,
valid numeric strings and legacy forms, and warning acknowledgement/staleness.
The initial reproduction failed before the shared checks were integrated.
The focused suite passed 102 tests. The full verification pack passed **979 tests
in 128.119 seconds**, with **zero broken evidence links** and unchanged source
hashes during testing. The inventory still has 476 unreviewed option paths; this
is an audit classification, not a count of missing features.

Both bounded 60-minute LTN demand-horizon runs completed four tasks with zero
failures or pending tasks. Their outcome hash retained the baseline value
`5368460ed4fd5fd466e832b82d3d6358977abfaccbb456d45e268cfb7c0ab474`.
This establishes bounded regression repeatability, not full LTN acceptance.
Local evidence is in `latest/generation-input-pack-build.txt`, `latest/evidence.json`
and `latest/generation-input-ltn/`. Unrelated local `ltn.json` edits were preserved.

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_generation_input_validation -q
.\.venv\Scripts\python.exe -m verification.run --output verification/latest
.\.venv\Scripts\python.exe -m verification.smoke --config ltn.json --minutes 60 --output verification/latest/generation-input-ltn
```

For a manual check, use a copy of a project. Set a category's `requires_staff`
to the string `"false"`: import/run must reject it with the category field path.
Use the JSON boolean `false` to express an explicit disabled choice. In another
copy, set the rotating global pattern's `work_days` to 3. Project Checks must
explain the fixed four-day limitation and require warning acknowledgement.
After editing that setting, run the checks again before simulation.

## Remaining limits

Unknown fields, all policy names, weekday-list semantics, complete calendar
intersections and every mode's independent demand totals remain open. Direct
lower-level generator classes do not constitute a validated project entry point.
Existing static-task shift metadata is not comprehensively checked. A valid
scalar does not prove feasibility, resource sufficiency or a correct aggregate
result. The configuration inventory and checkpoint 2 completion gate remain open.

Next: continue the generation/calendar acceptance audit with no-work rules and
out-of-hours behavior, recording independent expectations before changing policy.
Keep geometry, approved UI workflow work and the tutorial in their planned order.
