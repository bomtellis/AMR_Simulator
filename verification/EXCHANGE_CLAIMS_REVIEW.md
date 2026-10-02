# Finite empty-bin exchange claims — review checkpoint

Each full-bin exchange plan now claims a distinct physical empty bin at the
destination store. Estimates check availability without claiming or removing
stock. Committed plans reserve instances for their task; pickup processing uses
that task's own claim. A rejected plan or a failed task releases unconsumed claims.
Same-bin servicing continues to leave the separate exchange stock alone.

This closes **D025**: two individual plans, or two tasks in one batch, could
previously depend on the same empty bin. The batch planner now rejects a shortage
before assignment. Serial delivery remains possible where resources permit it.
Existing claims belonging to other tasks are respected.

## Review projects

Open the JSON, save a disposable `.amrproj`, simulate, and inspect task outcomes
and the payload monitor. Both projects release two full-bin deliveries at time
zero, enable empty-bin returns and use a one-minute task deferral limit. No mass
collection replenishes the empty stock during these cases.

| Project | Independent expectation |
| --- | --- |
| [One empty bin, two robots](scenarios/exchange-one-empty.json) | One empty supports one exchange: T1 and its return complete. T2 is not assigned and fails at **60 seconds**, its original deadline. One full bin remains at B; the original empty returns to A. Two physical transfers. |
| [Two empty bins](scenarios/exchange-two-empties.json) | Two exchanges produce **four completed tasks**, with no failures. The two original empties finish at A and the two delivered full bins at B: **four physical bins and four transfers**. |

The saved-project evidence is in `latest/exchange-one-empty-reference/` and
`latest/exchange-two-empties-reference/`. Summary and event outcomes reconcile;
neither has unpaired exits or tracking conflicts. The first has two assigned AMR
journeys, the second three, because its deliveries can share a journey. A shared
journey does not merge the identities of the bins it carries.

## Acceptance evidence

Fourteen tests cover individual and batch claims, estimates, rollback, task-failure
release, externally owned stock, reverse pickup order, same-bin servicing, two
robots competing for one empty, complete cycles, and raw/editor-normalised
projects. The original failures are in `baseline/exchange-claims-before-fix.txt`.

The full local pack passes **433/433 tests**, with zero broken feature-to-test
links. Six-hour LTN retains **203 completed, zero failed and zero pending**, with
unchanged detailed outcome hash
`21cd7e6d1fe83f255ab425307acd0fd1f830f4aa155412eba1767b3996fcf0f6`.
Its input-preservation and summary/event checks pass; runtime was about 14 seconds.
See `latest/ltn-exchange-claims/summary.json`.

## Remaining limits

The existing engine stages the empty bin when outbound pickup is processed,
before the full bin reaches the store. That timing is retained here; exact bay
occupancy through arrival, a modelled staging area and recovery after pickup
still require verification. Exchange tasks without a return also need an explicit
physical-disposition policy. This checkpoint proves exclusive claims and the
listed completed-cycle conservation cases, not all inventory workflows.

Other open work includes delivery/lift energy attribution and reconciliation of
operational failures with reports. The full [roadmap](ROADMAP.md) remains open.
The earlier unexplained preview-process interruption remains recorded in
`baseline/multi-stop-verification-observation.txt`. Automated warning
acknowledgement does not record human review or acceptance.
