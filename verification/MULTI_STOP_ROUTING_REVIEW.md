# Multi-stop route restrictions — review checkpoint

Each loaded leg now respects every payload currently carried. Resolve each task's
profile and task allowances using the existing union rule, then use the common
permissions of the onboard tasks. This applies separately to nodes, directed
edges and lifts. Restrictions begin at pickup and end at delivery.

An empty user allow-list still means unrestricted. Two non-empty lists with no
common permission mean forbidden, including when a previous unrestricted route
is cached. Having no common lift does not forbid a same-floor route.

The existing batch grouping by profile name and dirty label remains. Clean/dirty
and shared access continue to be defined by route profiles; no second route
classification is introduced.

## Review projects and calculations

Open the following JSONs, save disposable projects and simulate. Each has one
two-slot AMR at A, travelling at 2 m/s, with 2 seconds to load or unload. The two
branches use explicit model distances: A–X–B is 5 + 5 = 10 m; A–Y–B is
10 + 10 = 20 m. These override straight drawing distance deliberately.

| Project | Expected result | Independent calculation |
| --- | --- | --- |
| `scenarios/multi-stop-shared.json` | Two completed tasks in one AMR journey using A–Y–B; final delivery at 16 seconds | One shared pickup 2 + travel 20/2 + two dropoffs 2 + 2 |
| `scenarios/multi-stop-separate.json` | Two completed tasks in separate journeys; final delivery at 28 seconds | First service 2 + 10/2 + 2 = 9; second includes empty return 10/2 + pickup 2 + loaded travel 20/2 + dropoff 2 = 19 |

In the shared example the clean profile allows the long branch. T1 also permits
the short branch, but T2 does not. The short branch must not become available to
the loaded pair simply because T1 is first in the batch. Before D015 this happened,
and the invalid shared tour took 11 seconds. In the separate example, the tasks
have disjoint permissions and must not share a loaded tour.

Inspect Results investigation and playback to distinguish two task records from
one or two physical AMR journeys. The separate example travels 40 m in total:
30 m transporting payloads and 10 m returning empty.

## Additional acceptance evidence

Twenty tests cover task-order independence, unrestricted companions, node and lift
restrictions, shared profile/task unions, cache separation, separate-journey
fallback, and the raw/editor-normalised review projects.

For a two-floor case, the common permitted lift gives 2 seconds of horizontal
travel and 1 second of vertical travel. One shared pickup and two dropoffs make
the tour 2 + 2 + 1 + 2 + 2 = **9 seconds**. A faster prohibited lift is rejected.

After a wide payload is delivered at B, a remaining narrow payload can traverse
the 0.65 m B–C corridor when the robot is 0.6 m wide. The 0.7 m delivered load
must not continue blocking it. The corresponding approach case verifies that a
wide payload awaiting pickup does not restrict an earlier narrow loaded leg.

The route-restriction and footprint reproductions are retained separately in
`baseline/multi-stop-route-rules-before-fix.txt` and
`baseline/multi-stop-footprint-before-fix.txt`.

## Remaining limits

Stop ordering remains greedy and pickup-first. Failure to find a batch tour does
not prove that every possible interleaved pickup/delivery order is infeasible;
single-task assignment remains available. The candidate limit can also omit
otherwise useful combinations. This is not a tour-optimisation acceptance claim.

Clearance uses the largest currently carried oriented envelope under the existing
straight-passage model. It does not prove combined slot layout, swept turns,
door-leaf clearance, physical lanes or junction conflicts. Corridor energy still
uses the full-batch aggregate over loaded travel and needs independent refinement.
The subsequent [storage checkpoint](STORAGE_RESERVATIONS_REVIEW.md) verifies
multi-stop reservation rollback and distinct bay claims; broader resource and
exchange interactions remain open. The full completion ledger remains open.

## Recorded verification

- **380/380 tests pass**, with no broken feature-to-test evidence links.
- Both saved-project cases complete two tasks with zero failures, unknown
  outcomes, unpaired payload exits or tracking conflicts. Investigation records
  **one AMR journey** for the shared case and **two** for the separate case;
  summary and completion-event sets reconcile.
- Evidence is in `latest/multi-stop-shared-reference/summary.json` and
  `latest/multi-stop-separate-reference/summary.json`, with frozen external runs.
- Six-hour LTN remains **203 completed, 0 failed, 0 pending**, with detailed
  outcome hash `21cd7e6d1fe83f255ab425307acd0fd1f830f4aa155412eba1767b3996fcf0f6`,
  unchanged from the exact-scheduling checkpoint. Evidence:
  `latest/ltn-multi-stop-rules/summary.json`. Input-preservation checks pass.
- One initial full-suite process exited during the background demand-preview UI
  test without a diagnostic. Two diagnostic full-suite runs passed, as did
  **20 fresh-process repeats** of that UI test. The cause remains unconfirmed;
  this is not claimed as a repaired UI defect. See
  `baseline/multi-stop-verification-observation.txt` and
  `latest/preview-ui-repeatability.json`.
- Automated reference runs acknowledge warnings programmatically; these results
  do not record human review or acceptance of remaining limitations.
