# Checkpoint 2O — shared-bin identity and return lifecycle

Review date: 3 October 2026. Baseline: `81de242`.

This slice verifies one-route physical bin collection, delayed return and failure
handling. It also blocks conflicting definitions among active dynamic shared
contributors. It does not close the full waste-generation or engineering audit.

## Defects and changed results

- Seeding previously preferred the global stream payload over a department payload
  override. It now uses the nonblank department value, with global fallback for
  omitted, blank or whitespace values, matching dynamic generation.
- Pickup lookup previously took the first available bin of the right payload type,
  even if it belonged to another group. Grouped tasks now require their own group.
  The existing location suffix on nonshared department seeds remains supported.
- Dynamic tasks discarded return timing, priority and profile when the generic
  return was disabled or had no valid payload. Physical seeded-bin returns are
  mandatory, so these settings now survive the later runtime decision to return.
- A collection generated while the bin was away could bind to the returned bin
  later without acquiring a return policy. Mandatory same-instance return is now
  established when the collection is generated, independent of bin availability.

The last two defects interacted: ignored delays let the initial count-only example
pass without exercising the claimed wait. The acceptance test now asserts exact
movement times and identity, not merely four completed tasks.

## Independent timing and conservation reference

Open [the reference project](scenarios/shared-bin-return.json). The route is two
5 m edges through a door, travelled at 2 m/s. Loading and unloading each take 2 s.
Each loaded leg therefore takes **2 + 10/2 + 2 = 9 seconds**. Both nominal
collections use the same bin and are released at 60 s and 120 s. Return delay is
120 s. The initial bin is at A; collections go to B.

| Physical record | Expected time, seconds | Location |
| --- | ---: | --- |
| Initial bin | 0 | A |
| First collection arrives | 69 | B |
| First return arrives: 69 + 120 + 9 | 198 | A |
| Waiting second collection arrives: 198 + 9 | 207 | B |
| Second return arrives: 207 + 120 + 9 | 336 | A |

Expected totals: two collections, two returns, zero failures, one physical bin,
four physical exits, and the same ID throughout. Work released within the four-minute
demand horizon may finish afterward. These are bin movements, not a waste-volume
balance. The scheduled example accrues no volume.

Additional references establish:

- A department payload override seeds and transports that payload, with no phantom
  global-type bin. A blank override falls back to the global stream definition.
- Two compatible contributors at the same source share one bin through two cycles,
  before and after editor import. Numeric capacity strings resolve consistently.
- A door too narrow for outbound travel causes two failed collections, leaving the
  original bin at A, with no exits or lingering reservations.
- A return profile allowing only A → Door → B permits the first collection but
  prevents its return. The bin remains at B. The return fails and the second
  collection reaches its five-minute deferral limit. No replacement bin is issued.
- Department initial-container opt-out or global seed opt-out uses ordinary
  outbound issuance. These choices do not assert a reusable physical-bin cycle.
- A missing requested group cannot borrow another group's bin. A shared-group
  lookup can locate its bin at another source; complete multi-location lifecycle
  semantics are not established by that lookup test.

## Shared-definition checks

The task-generation manager compares **resolved active dynamic instances**, after
existing override precedence. Contributors to a shared group must agree on payload,
container capacity, effective threshold and initial-container presence. Differences
raise a specific error before simulation execution. Different schedules, demand
rates and priorities remain permitted. Disabled dynamic contributors are excluded.

Project Checks uses the same resolver and presents `SHARED_CONTAINER_CONFLICT`
errors, identifying the group, rules, field and conflicting values. Navigation
targets Waste configuration. Acknowledging warnings cannot bypass these errors.
Relevant demand, department, stream, payload and location edits stale the findings.
This validation does not rewrite inputs or claim that all raw seed definitions have
already been reconciled with dynamic instances.

Checks resolve definitions without preparing runtime task-count caches. The first
full-suite attempt exposed a regression where preflight expanded an enormous
timeframe count before Demand Preview could reject its size. That run was stopped;
the definition-only path and an explicit non-expansion regression now protect
preflight, and the existing preview size-limit test passes.

## Verification and manual review

Fifteen tests in `tests/test_shared_bin_lifecycle.py` cover the stated behavior.
The final focused regression run passed 135 tests in 10.270 seconds, including
Demand Preview size limits, Project Checks, generation contracts and payload timing.

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_shared_bin_lifecycle -q
.\.venv\Scripts\python.exe -m verification.run --output verification/latest
.\.venv\Scripts\python.exe -m verification.smoke --config ltn.json --minutes 60 --output verification/latest/shared-bin-ltn
```

The full pack passed **1,042 / 1,042 tests in 128.043 seconds**, with **zero broken
evidence links** and unchanged source hashes during execution. The inventory has
457 unreviewed option entries; this is an audit count, not a missing-feature count.
Local outputs are `latest/shared-bin-pack-build.txt`, `latest/tests.txt` and
`latest/evidence.json`.

Both bounded LTN runs completed four tasks with zero failures or pending tasks,
retaining the baseline outcome hash
`5368460ed4fd5fd466e832b82d3d6358977abfaccbb456d45e268cfb7c0ab474`.
This is bounded regression evidence, not full LTN acceptance. Unrelated local
`ltn.json` edits remain preserved and excluded from the checkpoint commit.

For manual review, import the reference JSON, run with full event evidence, then
inspect payload-location events and the four task outcomes against the table.
In a copy, add a second enabled department using shared group `BIN`, then assign
it a different threshold. Project Checks should show a blocking shared-definition
finding. Restore consistent values to clear it. Demand Preview alone does not
establish that physical collection or return completed.

## Remaining boundaries and next action

Physical seeding still reads raw department settings, while dynamic generation
resolves category and group inheritance. Inherited pickup/group/initial flags,
inactive seed contributors, automatic grouping with multiple pickups, and limited
inventory spaces need the next parity audit. The current reference uses explicit
department pickup and group values. Legacy generator lifecycle combinations also
remain open.

Threshold generation consumes accumulated volume when it creates a collection
record. Physical task failure does not by itself prove that volume is restored.
Failed-collection volume reconciliation, multiple route-pair collection accounting
and tracked-item consumption remain open. A preserved bin ID is not proof of
preserved waste volume. Forced seeded returns still inherit the outbound profile
when their return profile is blank; broader precedence needs an explicit contract.

Next: align initial-bin definitions with resolved active demand, then reconcile
threshold demand against failed/completed physical collections and remaining stock.
Retain the later geometry, approved UI workflow and tutorial gates.
