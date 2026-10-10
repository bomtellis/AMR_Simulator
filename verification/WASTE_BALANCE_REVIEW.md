# Checkpoint 2Q — accumulated waste and collection outcomes

Review date: 3 October 2026. Baseline: `833a35e`.

Dynamic accumulated waste now has an inspectable balance through collection
generation and terminal outcomes. This fixes two reproduced defects: a single
threshold could create several full-volume collections across route pairs, and
failure before pickup did not return the allocated volume to the demand pool.

The first seven references produced three failures and four missing-balance API
errors. The final module contains thirteen acceptance tests, including recorded
evidence and missing/malformed coverage.

## Allocation contract and changed results

One threshold now funds **one** collection. If the triggering rule offers several
valid route pairs, successive thresholds rotate through them in resolved order.
The choice is deterministic and shared by generation and preview. It is not a
spatial distribution model for where waste accumulated within a pooled group.
For example, 1 m³ accrued, threshold 0.4 m³ and two dropoffs now produce two
collections of 0.4 m³, one to each dropoff, with 0.2 m³ remaining. Previously the
same pool produced four collections claiming 1.6 m³.

Each dynamic waste threshold allocation records its task ID, rule, requested
endpoints, volume and status. A pre-pickup failure restores that allocation once;
repeated failure notifications do not restore it again. A later eligible poll may
retry the available volume. A failure after pickup remains unconfirmed instead of
inventing replacement waste at the source. Completed collections stay completed
even if their empty-bin return later fails. Returns are separate physical journeys
and add no collected volume.

The balance is:

**Accrued = residual unallocated + pending allocations + completed collections +
unconfirmed volume after pickup.**

Restored-after-failure volume is a diagnostic sum across attempts. It is already
included in residual volume or a later allocation and must not be added to the
balance. Repeated failed attempts can make this diagnostic exceed distinct accrued
volume. Collection completion does not establish physical disposal or decontamination.

## Independent references

The saved [volume-balance project](scenarios/waste-volume-balance.json) accrues
24 m³/day over exactly one open hour: **24 × 1/24 = 1 m³**. The global bin is
0.5 m³ with fill fraction 0.8, so each threshold is **0.5 × 0.8 = 0.4 m³**.
There are two allocations and 0.2 m³ residual. It polls at 3,600 seconds and
released transport may finish after the one-hour demand horizon.

| Reference | Independent expectation |
| --- | --- |
| Generation before dispatch | 1 accrued = 0.8 pending + 0.2 residual |
| Both collections complete | 1 accrued = 0.8 completed + 0.2 residual |
| Door too narrow for either collection | Two failures before pickup; all 1 m³ remains unallocated |
| One of two allocations fails before pickup | 0.6 residual + 0.4 pending; duplicate failure changes nothing |
| Another hour accrues after that failure | 0.6 + 1 new m³ funds four further allocations; total pending becomes 2 m³ |
| One allocation fails after pickup | 0.4 unconfirmed + 0.4 pending + 0.2 residual |
| Completed collection is notified twice, then its return fails | Its 0.4 m³ is counted once as completed |
| Two shared contributors each accrue 0.3 m³, threshold 0.5 | One 0.5 m³ allocation + 0.1 residual = 0.6 accrued |
| Two scheduled-threshold fill events each add 0.3 m³ | One 0.4 m³ allocation + 0.2 residual = 0.6 accrued |

Normal completion and blocked outbound travel are full-simulation tests. The
post-pickup unconfirmed and repeated-notification cases test the generator callback
contract directly; the wider in-transit failure/recovery interaction matrix remains
open. Earlier physical payload tests continue to cover container identity separately.

## Recorded evidence and Results Investigation

Full logs record coverage counts, one summary per pool and one allocation record
per task, using stable event identifiers. Keeping allocations in individual rows
avoids a single giant CSV field for larger runs. Repeated final CSV writes cannot
duplicate these records. The programmatic simulation summary also exposes balances.

Results Investigation adds accumulated-volume metrics for accrual, residual,
pending, completed, unconfirmed and restored attempts. Reconciliation checks the
equation, allocation totals, generated task volumes and terminal task outcomes.
Metric evidence links include the relevant accounting, generation and outcome
records. A conflict is displayed if those records disagree. Group/allocation
coverage counts detect missing records. Malformed, absent, older or incomplete
evidence stays unknown; it is not converted into zero volume.

This balance covers **dynamic accumulated waste and threshold collections**.
Ordinary scheduled/sporadic work, legacy generators and tracked-item consumption
are outside it. Hybrid mode's separate sporadic transport is likewise excluded.
Current full-evidence rules require a finished, bound log; cancelled snapshots
remain partial evidence in Results Investigation.

## Verification and manual review

The focused waste regressions passed 50 tests before the final missing-record
coverage reference was added. Another 58 generation/investigation tests passed
before the final scalable evidence layout. The full pack validates the final source.

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_waste_volume_balance -q
.\.venv\Scripts\python.exe -m verification.run --output verification/latest
.\.venv\Scripts\python.exe -m verification.smoke --config ltn.json --minutes 60 --output verification/latest/waste-balance-ltn
```

The full pack passed **1,066 / 1,066 tests in 127.628 seconds**, with **zero broken
evidence links** and unchanged source hashes during execution. The inventory has
457 unreviewed option entries; this is an audit count, not a missing-feature count.
Evidence is retained in
`latest/waste-balance-before.txt`, `latest/waste-balance-focused.txt`,
`latest/waste-balance-pack-build.txt` and `latest/evidence.json`.

Both bounded LTN runs completed four tasks with zero failures or pending tasks,
retaining outcome hash
`5368460ed4fd5fd466e832b82d3d6358977abfaccbb456d45e268cfb7c0ab474`.
Outputs are in `latest/waste-balance-ltn/`. This is bounded regression evidence,
not full LTN acceptance. Unrelated local `ltn.json` edits were preserved and are
excluded from this checkpoint.

For manual review, import the saved project, simulate with full event logging and
open Results Investigation. Verify 1 m³ accrued, 0.8 m³ completed, 0.2 m³ residual,
zero pending/unconfirmed and a reconciled status. Select a metric to inspect its
contributing records. In a copy, reduce the door clear width to 0.5 m and rerun:
both collections should fail, leaving 1 m³ residual and zero completed volume.

## Remaining work

Tracked-item consumption, legacy waste accounting and the separate scheduled /
sporadic components still need balances and independent references. Recovery of
unconfirmed volume is not connected to this ledger; do not infer recovery from a
newly created unrelated task. Broader multi-department routing, resource failures
and retry policies remain under audit. The existing geometry, approved CAD UI,
tutorial and release-validation gates remain unchanged.

Next: audit tracked-item consumption and return/exchange resets, including whether
generated demand and remaining stock conserve the independently specified inputs.
