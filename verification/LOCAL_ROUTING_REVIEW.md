# Checkpoint 1 — local routing and software evidence

Review date: 3 October 2026. Baseline: `7f08e1b`.
This checkpoint addresses the concrete defects from the source reassessment.
It does not complete the later geometric traffic model or the full option audit.

## Changed behaviour

| Defect | Reproduction and expected outcome | Correction |
| --- | --- | --- |
| Blocked direct fallback | A four-wall ring encloses `(0,0)`; target `(4,0)` is outside. No route may cross a wall. | Return `search_exhausted` when the bounded planner cannot find a clear route. No fabricated straight movement. |
| Lost route endpoints | `(0,0)` and `(2,0)` lie inside rectangle `(-1,-1,3,1)`. Obstacle corners must not replace them. | Reject an invalid start/end with `invalid_endpoint`; preserve exact endpoint indices for valid requests. |
| Unsafe visual smoothing | A safe detour can be shortened through an obstacle by corner smoothing. | Check smoothed segments; retain the clear, unsmoothed polyline when smoothing is unsafe. |
| Incomplete software fingerprint | Reservation, generation-provenance, project and check modules were outside the old source list. | Fingerprint root Python modules and all Python modules under `visualiser/` and `report/`, using relative paths. |

Every visibility-graph edge is checked against the complete local obstacle set,
including obstacles omitted from the bounded candidate selection. Failed local
routes propagate through single-task and batch planning. Pending/failure reasons
record the outcome; the existing transaction restores bookings, inventory claims
and robot state. Failed routes are not cached as successful paths.

The fingerprint is deliberately conservative: even a presentation-only application
source change invalidates a prepared run. Prepare and check it again before
execution. Completed historical runs remain readable. Older fingerprint coverage
is labelled incomplete or unverified in Results investigation. This source binding
does not fingerprint installed third-party packages or the Python runtime.

## Verification and review

The final full suite passed **885 tests in 126.119 seconds** (15 additional tests
over the reassessed baseline). The saved application-review scenario has no
blocking check findings and produces its expected failure both as raw JSON and
after editor normalisation.

The new routing tests first reproduced the defects against the baseline. Acceptance
tests cover enclosed and invalid endpoints, nonfinite inputs, exact endpoint
preservation, an unobstructed 3–4–5 route, a rectangle detour, smoothing, departure,
single/batch rollback, and a real blocked-dropoff simulation. Fingerprint tests
cover required dependencies, nested/new/deleted/changed modules, every currently
fingerprinted file invalidating prepared execution, and legacy evidence reading.

Automated commands from the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_local_manoeuvre_safety tests.test_software_fingerprint tests.test_project_runs tests.test_results_investigation -q
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
.\.venv\Scripts\python.exe -m verification.smoke --config ltn.json --minutes 60 --output verification/latest/checkpoint-1-ltn
```

For application review, import [local-blocked-dropoff.json](scenarios/local-blocked-dropoff.json)
as a separate project. The destination node B is `(6,8)` and its bay centre is
`(10,8)`. Four modelled inventory obstacles enclose B. Their local bounds are
`(-1,-1,1,-0.8)`, `(-1,0.8,1,1)`, `(-1,-1,-0.8,1)`, `(0.8,-1,1,1)`;
the existing obstacle expansion is 0.15 m. These form a closed barrier even before
expansion. Expected: task T fails with `search_exhausted`, zero completed tasks,
no physical payload arrival at B, and no assigned journey through the barrier.
This deliberately constrained scenario is for failure review, not a useful layout.

LTN comparison uses a one-hour demand horizon and allows already assigned work to
drain beyond it. Two corrected runs produced four completions, zero failures and
zero pending tasks, with identical outcome hash
`5368460ed4fd5fd466e832b82d3d6358977abfaccbb456d45e268cfb7c0ab474`.
The baseline simulator produced the same hash. Final corrected elapsed times
were 1.64 and 1.70 seconds, versus 1.60 seconds for the baseline (indicative timings,
not a performance acceptance threshold). This short case is a repeatability and
regression check, not independent validation of LTN's entire schedule.

Local machine outputs are retained under `verification/latest/`:
`checkpoint-1-tests.txt`, and `checkpoint-1-ltn/` containing configuration,
outcomes, baseline comparison, timings and input hashes. These generated files
are not versioned; the source scenario and test expectations are versioned.

## Remaining boundaries

- `search_exhausted` means the bounded local planner found no usable route. It
  does not prove geometric infeasibility over every possible path.
- Obstacle checks remain centreline checks against expanded axis-aligned boxes.
  Loaded swept footprints, strict turn radii, lane/junction geometry, pivots and
  reverse manoeuvres remain checkpoints 5–7.
- Bays without a drawn position retain the existing zero-movement behaviour at
  their parent node. Default display boxes do not establish explicit bay geometry.
  Regression checking caught and removed an unintended change to this behaviour.
- A blocked candidate bay can reject the current plan; this checkpoint does not
  introduce exhaustive searches over alternative bays or manoeuvres.
- Historical results produced by the unsafe fallback are not rewritten. Re-run
  affected projects to obtain results under the corrected behaviour.

Next: user verification of this checkpoint, then checkpoint 2's feature inventory
and independent acceptance coverage. Major UI rework remains after core completion.
