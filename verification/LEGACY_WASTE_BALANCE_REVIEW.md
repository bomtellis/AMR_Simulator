# Legacy waste outcome conservation — slice 2T

Baseline: `0912391`. The legacy `DepartmentWasteTaskGenerator` deducted fill when
creating a collection but ignored later failure. A reference generating 0.6 m³
and failing its collection before pickup left zero fill: the volume disappeared.
The reproducing failure is in `latest/legacy-waste-balance-before.txt`.

## Changed behaviour

Each legacy collection now has a volume allocation. Success marks it completed.
A failure before physical pickup restores fill exactly once; a later eligible
poll can retry it. Failure after pickup leaves an unconfirmed allocation rather
than pretending the waste is still at its source. Duplicate notifications and
return-task callbacks cannot modify the allocation again.

The conserved model balance is:

`accrued = unallocated residual + pending + completed + unconfirmed`

Restored attempts are a separate diagnostic, already represented in residual or
subsequent allocations. Adding them to this identity would double count waste.
Generation stops at the configured demand horizon; restoration after its final
poll remains residual, without inventing post-horizon retries.

## Evidence compatibility

The saved accumulated-waste manifest now uses schema 2, capability
`waste_volume_balance_v2` and explicit scope
`dynamic_and_legacy_accumulated_waste`. Group summaries identify their generator.
Results Investigation includes legacy `waste_task_generated` events when checking
allocation volumes and terminal outcomes. Missing generation evidence conflicts;
missing generator identity or incompatible schema/capability remains unknown.

Schema 1 remains readable with its original dynamic-only scope. Its absence of
legacy volume is not retrospectively interpreted as zero legacy activity. Older
applications that only understand capability 1 cannot claim reconciliation of a
new combined-scope log. The metric definition shows the supported scope.

## Independent references and manual review

Ten tests in `tests/test_legacy_waste_balance.py` cover allocation, idempotent
callbacks, failed attempts, confirmed completion, inactive departments, actual
saved runs and compatibility with old dynamic evidence.

The saved `scenarios/legacy-waste-balance.json` models one active hour, a rate of
0.6 m³/hour and a 0.6 m³ collection threshold. One collection completes with
accrued 0.6, completed 0.6 and residual 0. If the door is reduced to 0.5 m, the
collection fails before pickup and the final balance is accrued 0.6, residual 0.6,
completed 0. Extending this blocked case to two hours gives accrued/residual 1.2
and three failed 0.6 attempts: restored-attempt volume is 1.8, not fresh accrual.

Import the saved reference, run with full logging, and open **Results investigation
→ Metrics → Accumulated waste reconciliation**. Inspect the linked legacy
generation record, terminal outcome and allocation. Repeat with the narrower
door, then with the two-hour horizon. Check the definition before comparing a
new log with an older dynamic-only run.

The full verification pack passed **1,103 / 1,103 tests in 129.634 seconds**,
with **zero broken evidence links** and unchanged source hashes during execution.
The focused legacy/dynamic waste and investigation suites passed 63 tests. Evidence
is in `latest/legacy-waste-balance-focused.txt`,
`latest/legacy-waste-balance-pack-build.txt` and `latest/evidence.json`.

Both bounded 60-minute LTN demand-window runs completed four tasks with zero failed
or pending tasks. Their outcome hash remains
`5368460ed4fd5fd466e832b82d3d6358977abfaccbb456d45e268cfb7c0ab474`.
See `latest/legacy-waste-balance-ltn/`; this does not establish full LTN acceptance.
Unrelated `ltn.json` working changes are preserved outside this checkpoint.

## Limits and next work

The legacy rate formula, per-stream application, seed adapter and routes retain
their existing semantics. Logical volume and task completion do not establish
physical disposal, decontamination or successful recovery of unconfirmed cargo.
The legacy and modern generators still differ in supported department-stream
overrides; this checkpoint does not claim parity. Ordinary scheduled/sporadic
demand is outside accumulated-waste balances and needs separate outcome evidence.

Continue the mode/precedence and inventory interaction audit, then the remaining
core workspace and geometry gates. UI workflow approval, the graph-focused CAD
rework, tutorial and final release validation remain in their agreed sequence.
