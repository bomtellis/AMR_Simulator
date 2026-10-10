# Direct-event volume outcomes — slice 2W

Baseline: `39564c8`. Scheduled waste and sporadic task records can carry explicit
volume without drawing from an accumulated pool. That volume now has separate
outcome accounting. Hybrid's discrete component is included; its continuous
threshold pool remains in accumulated-waste accounting.

## Contract and evidence

Each generated direct-volume task is registered once. Its volume satisfies:

`requested = pending + completed tasks + failed before pickup + unconfirmed after pickup`

Failures are outcomes, not fresh demand. No automatic retry, replenishment or
restoration to an unmodelled stock pool is inferred. Duplicate callbacks and return
tasks cannot register that volume again. Route-pair multiplicity remains explicit:
two occurrences across two valid category route pairs produce four task records.

Full logs add a generated-task component label, a coverage manifest, grouped
totals and per-task outcome records under `direct_event_volume_v1`. Results
Investigation checks manifest counts, identities, finite quantities, group/request
totals, generated rule/component/volume and terminal outcomes. Before/after-pickup
failure classification is checked against physical pickup events. It also flags
the same task appearing in both direct demand and accumulated-waste allocations.
Tagged generated tasks cannot disappear behind an empty accounting manifest.

Metrics show requested, pending, completed-task, failed-before-pickup and
unconfirmed-after-pickup volumes, plus reconciliation status. Selecting a metric
opens its supporting records. Old, partial or malformed evidence remains unknown.
Explicit complete coverage with no direct-volume work is known zero. Tasks with
an explicit zero volume retain request records and are not mistaken for missing
evidence. Repeated log flushes do not duplicate the accounting.

## Independent references and manual verification

Thirteen tests in `tests/test_direct_volume_balance.py` cover pending work,
duplicate and return callbacks, hybrid separation, route multiplicity, successful
and blocked saved runs, injected post-pickup failure, scheduled/threshold scope,
zero volume, old evidence, corrupt quantities and missing/duplicated records.

The saved `scenarios/direct-event-volume.json` uses one active hour, 48 events per
24 eligible hours and 0.2 m³ per event. Two requests give 0.4 m³ requested and,
after successful transport, 0.4 m³ attached to completed tasks. A 0.5 m door blocks
both before pickup: requested 0.4, failed-before-pickup 0.4, completed 0. The
injected-failure reference fails both after their actual pickup events: requested
0.4, unconfirmed 0.4, completed 0. Removing pickup evidence produces a conflict.

Import the saved reference and run with full logging. Open **Results investigation
→ Metrics → Direct-event volume reconciliation**. Inspect the two generated
records, request outcomes and completions. Compare the completed and pending
volume metrics. Repeat with the reduced door opening and inspect failed volume.
Do not add these requested/outcome figures to accumulated-waste stock totals.

The full verification pack passed **1,142 / 1,142 tests in 131.944 seconds**,
with **zero broken evidence links** and unchanged source hashes during execution.
The focused direct/pooled/stock/investigation suites passed 86 tests. Evidence is
in `latest/direct-volume-focused.txt`, `latest/direct-volume-pack-build.txt` and
`latest/evidence.json`. The inventory retains 450 unreviewed option entries; that
audit count is not a count of missing implementations.

Both bounded 60-minute LTN demand-window runs completed four tasks, with no failed
or pending tasks, retaining outcome hash
`5368460ed4fd5fd466e832b82d3d6358977abfaccbb456d45e268cfb7c0ab474`.
Outputs are in `latest/direct-volume-ltn/`. This is bounded regression evidence,
not full LTN acceptance. Unrelated local `ltn.json` edits remain outside the commit.

## Limits and next work

These are recorded task-volume outcomes, not an independent recalculation of all
configured demand. A completed AMR task is not proof of final staff handoff,
physical disposal or decontamination. Failure after pickup remains unconfirmed
task volume even if a physical arrival occurred before a later task-stage failure;
the event timeline supplies that detail.

Scope covers dynamic scheduled waste with explicitly assigned event volume, and
dynamic sporadic records including hybrid. Ordinary non-waste schedules do not
use `volume_per_event_m3`; manual tasks, timeframe records, legacy waste pools and
tracked consumable quantities retain their separate scopes. No new physical
inventory model or automatic recovery workflow is introduced.

Next: consolidate the remaining configuration dispositions against the implemented
acceptance evidence, then continue mixed-service inventory and workspace gaps.
The geometry, approved CAD UI workflow, tutorial and release-validation gates
remain in the agreed order.
