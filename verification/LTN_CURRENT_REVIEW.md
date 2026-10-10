# Current LTN measurements — 4 October 2026

The current working `ltn.json` has six floors, 22 robots and a configured
1–8 January 2026 window starting at 05:00. Its SHA-256 is
`77ea27f29e79ac3ea004a965eed134846125b3d7d077361ce2068ef07179a181`.
The source configuration and existing `ltn.amrproj` were not modified. Measurements
use commit `4623c38` plus the preserved local simulator and LTN edits; they do not
represent a clean-install or upstream-only checkout.

## Portable project storage

`python -m verification.project_storage --config ltn.json --output <new-folder>`
measured six drawing references sharing five unique drawings. The drawings total
227,733,904 bytes and the JSON 1,391,935 bytes. The compressed project contains
both in 15,140,221 bytes. Save took 2.080 seconds; reopen took 0.317 seconds.
Configuration roundtrip and unchanged source checks pass. This is one local
sample; reopening the archive does not measure drawing parsing, scene rendering
or interactive editor performance. See `ltn-evidence/storage.json`.

## Six-hour saved-project run

Two independent calls to `python -m verification.project_runs --config ltn.json
--output <new-folder> --minutes 360` create separate projects with a 05:00–11:00
input window on 1 January. The tool copies the configuration and changes only
its end time for the bounded run. Project warnings are acknowledged automatically
for this engineering measurement, not approved by a person.

Both runs produce **150 completed tasks, 15 failed tasks and zero pending tasks**.
All three outcome counts reconcile with recorded events. Execution, exports and
investigation/binding checks take 10.634 and 10.717 seconds. Both outcome hashes
are `f590a2f075511fb1355df4ab1bd6c9ec8faf53d389eaa2f84b2a36ba54a816aa`.
Source preservation passes in both runs. This verifies repeatability and report
reconciliation for this bounded input; it does not establish successful delivery
of every task, seven-day LTN behaviour, or the separate 10-floor scale target.

See `ltn-evidence/six-hours.json`, `six-hours-repeat.json`, and `failed_tasks.csv`.
Full local projects, inputs, checks and logs are retained under
`latest/ltn-current-six-hours` and `latest/ltn-current-six-hours-repeat`.

## Layout finding to surface before simulation

All 15 failures report an invalid local-manoeuvre start at the drop-off zone's
graph location. Inspection shows the entry lies inside these bay obstacle bounds:

| Drop-off zone | Bay covering entry | Failed requests |
| --- | --- | ---: |
| D29-DROP-ZONE | Burlodge Trolley space 2 | 3 |
| D32-DROP-ZONE | Burlodge Trolley space 2 | 2 |
| D33-DROP-ZONE | Burlodge Trolley space 3 | 2 |
| D35-DROP-ZONE | Burlodge Trolley space 2 | 2 |
| D38-DROP-ZONE | Burlodge Trolley space 2 | 2 |
| D39-DROP-ZONE | Burlodge Trolley space 2 | 2 |
| D41-DROP-ZONE | Burlodge Trolley space 2 | 2 |

Local routing treats other drawn bays as axis-aligned obstacle bounds expanded
by 0.15 m and excludes the selected target bay. An entry inside another bay can
therefore prevent access to the selected bay. This is a model-layout risk, not a
claim about physical walls or proof that no alternate geometric path exists.
The invalid-local-manoeuvre bypass is not enabled in this input and was not
switched on to make the measurement pass.

Follow-up: the navigable Project checks warning and independent reference tests
are recorded in `LOCAL_BAY_ENTRY_REVIEW.md`. Interactive LTN drawing/cursor/drag
measurements remain open.
