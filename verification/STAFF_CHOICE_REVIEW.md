# Checkpoint 2D — explicit staff choice and legacy omission

Review date: 3 October 2026. Baseline: `b732098`.

An explicit `requires_staff=false` previously still allocated staff for Stores
deliveries because the legacy fallback ran whenever the value was false. That
could delay returns and consume staff resources despite the configured choice.

The task model now distinguishes an unspecified requirement from explicit false.
Unspecified retains the legacy Stores fallback; explicit false suppresses it;
explicit true enables staff. A group false overrides a category true. Physical
department drop-off-zone handoffs still force staff, and automatic return tasks
do not allocate a second payload-handling service.

Imported omission remains absent across repeated editor load/save. New-project
templates retain their explicit choices. This refines slice 2C's import fix by
retaining omission instead of materialising it as false; zero default handling
duration remains unchanged. No hidden compatibility marker is written into JSON.

## Independent reference

The outbound Clean journey releases at 60 seconds and arrives at 69 seconds:
2 seconds pickup + 10 m / 2 m/s + 2 seconds drop-off. Configure a one-minute return
delay and three-minute staff handling with all-day Monday staff hours.

| Effective setting | Staff evidence | Return starts |
| --- | --- | --- |
| Omitted on legacy Stores rule | One 180-second handling record | 69 + 180 = 249 s (00:04:09) |
| Explicit false | No staff handling booking | 69 + 60 = 129 s (00:02:09) |
| Explicit true | One 180-second handling record | 249 s (00:04:09) |

These expectations pass for both raw and editor-normalised input. Tests also
cover direct Task construction, static task loading, group/category precedence,
three successive editor roundtrips and zone-handoff enforcement.

The full evidence pack passed **917 tests in 125.901 seconds**, with **zero broken
evidence links** and unchanged source hashes during testing. Two bounded LTN runs
again completed four tasks with zero failures or pending tasks, retaining outcome
hash `5368460ed4fd5fd466e832b82d3d6358977abfaccbb456d45e268cfb7c0ab474`.
Local outputs are saved in `latest/staff-choice-ltn/` and
`latest/staff-choice-pack-build.txt`. The source `ltn.json` was not modified.

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_staff_requirement tests.test_generation_contracts -q
.\.venv\Scripts\python.exe -m verification.run --output verification/latest
```

## Changed results and boundaries

Projects with explicit false on Stores tasks/rules may now have earlier returns
and less staff utilisation. This is the intended correction; omission preserves
the legacy fallback. Existing saved files do not reveal whether an older version
inserted a stored false or the user chose it. Review that setting when comparing
historical results. Historical logs remain unchanged.

This verifies choice resolution and its effect on the reference booking/timeline,
not all staff movement, roster, queue or automatically expanded staffing policies.
Broader generation boolean validation remains open. Internally unspecified is
represented by `None`; ordinary configuration should omit the field or use a JSON
boolean, rather than rely on ambiguous scalar conversions.

The core audit remains active. Next: staff resource contention and capacity
semantics, then remaining generation and return interactions. Geometry, UI rework
and tutorial remain in their agreed sequence.
