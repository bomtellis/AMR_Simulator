# Tracked-stock results evidence — slice 2S

This checkpoint adds recorded reconciliation to Results Investigation. It does not
change demand, routing, consumption or replenishment timing. Each confirmed direct
delivery or staff handoff now emits one `tracked_stock_delivery_confirmed` receipt
with supplied and removed quantities. Generated-task records identify the drop-off
zone; the final coverage record counts balances, requests and receipts.

## Acceptance contract

For each rule, stock resource and item, the viewer checks:

- Initial + delivered = consumed + removed + remaining, using finite quantities.
- Requests agree with generated-task item quantities and terminal task outcomes.
- Delivered requests have exactly one receipt with the ordered quantities and
  appropriate direct-completion or staff-handoff confirmation.
- Receipts have corresponding physical payload arrivals at the stock resource,
  with the same payload identity and an arrival time no later than confirmation.
- Recorded supplied and removed counters equal the receipt totals.

Different item units are not summed. Remaining stock, unmet consumption and a
reconciliation status appear as per-item metrics; selecting a metric shows its
contributing records. Conflicting complete records produce **Conflict**. Partial,
malformed or old logs without the new receipt capability remain **unknown**.
Explicit complete coverage with no tracked stock is distinguishable from missing
evidence. Repeated CSV flushes do not duplicate receipts or final balances.

## Independent references and review

The ten tests in `tests/test_tracked_stock_evidence.py` use real saved simulations
and deliberately altered event records. With the saved `scenarios/tracked-stock.json`
reference, two active hours consume 16 units, confirmed supply adds 16 and final
stock is 10. A 0.5 m door blocks both deliveries: consumed 10, unmet 6, supply 0,
remaining 0. Staff unavailable until after the demand horizon gives consumed 10,
unmet 6, eventual supply 8 and remaining 8. Immediate staff availability gives the
normal 16/16/10 result. One-hour full exchange removes the old 2 Supply units and
19 Other units, leaving the configured 10 and 20 units respectively.

Negative references alter balances, supply/removal quantities, generated requests,
terminal outcomes, timestamps and payload identities. Missing, duplicated and
malformed evidence cannot present a reconciled balance. A Qt acceptance test checks
that selecting remaining stock opens the contributing receipts and balance records.

Manual review: import `scenarios/tracked-stock.json`, run with full logging, then
open **Results investigation → Metrics**. Select **Tracked stock reconciliation**
and the **Remaining stock** metric. Inspect the balance definition and two delivery
receipts. Repeat with the reduced door opening and inspect the unmet consumption.
Older logs remain readable; rerun to obtain the new receipt evidence.

The full verification pack passed **1,093 / 1,093 tests in 130.255 seconds**,
with **zero broken evidence links** and unchanged source hashes during execution.
The focused stock/waste/investigation suites passed 68 tests. The inventory retains
450 unreviewed option entries; this is not a missing-feature count. Evidence is in
`latest/tracked-stock-evidence-focused.txt`,
`latest/tracked-stock-evidence-pack-build.txt` and `latest/evidence.json`.

Both 60-minute LTN demand-window runs completed four tasks with zero failures or
pending tasks and unchanged outcome hash
`5368460ed4fd5fd466e832b82d3d6358977abfaccbb456d45e268cfb7c0ab474`.
Outputs are in `latest/tracked-stock-evidence-ltn/`. This is bounded regression
evidence, not full LTN acceptance. Unrelated local `ltn.json` edits remain outside
the checkpoint.

## Limits and next work

This checks recorded accounting against independent event records from the same
simulator. It does not independently recalculate every consumption interval from
frozen inputs, establish real-world stock accuracy, or prove distinct physical
handling for each exchange mode. Initially full logical stock, unlimited sources,
per-rule/resource accounting and the other boundaries in
[Tracked stock](TRACKED_STOCK_REVIEW.md) remain in force.

Continue the legacy/scheduled demand and inventory interaction audit. The geometry,
CAD workflow approval, UI rework, tutorial and final release gates remain open.
