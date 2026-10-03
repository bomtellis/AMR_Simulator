# Checkpoint 2R — tracked consumption and confirmed replenishment

Review date: 3 October 2026. Baseline: `e491c54`.

Tracked stock no longer refills when a replenishment task is merely generated.
Supply is credited once, after direct task completion or confirmed staff handoff
from a drop-off zone. Failed requests leave stock depleted and permit a later
retry. Consumption continues while supply is pending, with shortage recorded as
unmet demand instead of being hidden by a clamp at zero.

The initial seven references had four failures and three missing callback/balance
API errors. The final module contains seventeen tests, including complete runs,
editor import, staff handoff, recorded evidence and invalid inputs.

## Stock contract

Each generated service has stock per resolved department resource and tracked item.
Stock starts at the configured maximum. `consumption_per_day` means item units per
24 active hours, divided between that department's resources. Category dates and
department opening periods both apply. A poll after closing retains consumption
from the preceding open period; an inactive date contributes none. Older polls
cannot move the consumption watermark backwards and consume an interval twice.

The identity checked for each item/resource is:

**Initial + delivered = consumed + removed + remaining.**

Unmet demand is requested consumption that exceeded available stock. It is reported
separately and is not subtracted again. This is a logical content balance, separate
from the physical payload/container identity balance.

The three settings now have distinct content behavior:

- `top_up_only` orders the deficit at request time. Consumption while it is in
  transit can leave stock below target when it arrives. Scheduled top-ups subtract
  supplies already on order to avoid ordering the same deficit twice.
- `full_exchange` supplies the target quantities for every tracked item and
  records the old contents still present at delivery as removed.
- `replace_empty` waits until an item is empty, rather than using its top-up
  threshold, and supplies its target quantity.

Automatic consumption-triggered requests are limited to one pending request per
resource. Explicit scheduled requests still occur; their content quantities account
for pending supplies. A full resource does not generate a zero-quantity automatic
request merely because its trigger equals its maximum. Threshold comparison allows
floating-point noise scaled to target quantity at 1e-12; handoff timing previously
left a computed 2.000000000000001 just above a threshold of 2.

AMR arrival at a drop-off zone does not replenish department stock. The current
staff-handoff code confirms it when that handoff commits, rather than backdating
stock to an earlier planned walking arrival. Direct completion and handoff
notifications are idempotent. Return journeys do not supply the same contents again.

## Independent references

The [saved reference](scenarios/tracked-stock.json) starts with ten units and
consumes 192 units/day over active time: **192 / 24 = 8 units/hour**. It requests a
top-up at two units and runs demand for two hours, with hourly consumption polls.
Supply already requested may arrive after the demand horizon; consumption ends at
that horizon. This retains the simulator's demand-window/transport-drain distinction.

| Reference | Independent expectation |
| --- | --- |
| One hour, before transport succeeds | 10 − 8 = 2 units; one request for 8; no refill |
| Another hour while that request stays pending | Zero stock, ten total units consumed, six unmet; no duplicate automatic request |
| First request arrives 7.5 minutes later | One further unit consumed; 1 remaining + 8 supplied = 9 |
| Duplicate completion notification | Stock remains 9 |
| Failed first request | Stock remains 2; a later poll can retry |
| Two-hour normal full run | 10 initial + 16 delivered − 16 consumed = 10 remaining |
| Two-hour run with blocked outbound travel | Two failed requests; ten consumed, six unmet, zero supply and zero remaining |
| Staff unavailable until 09:00, after the two-hour horizon | One request waits; ten consumed and six unmet, then eight supplied and eight remaining |
| Staff available during demand | Both supplies arrive; sixteen consumed, sixteen supplied and ten remaining |
| Two scheduled requests at 01:00 and 01:15, both still pending | First orders 8, second orders 2 after accounting for incoming 8; both arrivals leave 10 |
| Full exchange with another item starting at 20 and consuming 1/hour | Remove 2 and 19 old units; supply 10 and 20; both items end at target |
| Replace empty | No request at two units; one request at zero after 1.25 hours |

The shared-resource reference already in `test_dropoff_zones.py` remains in the
regression set: ten units/day across two resources consumes five from each.

## Input checks, help and recorded results

Raw import, runtime and Project Checks now validate `track_items`, item maxima,
thresholds and consumption rates, and exchange-mode names. Maxima must be finite
and positive; supplied thresholds are nonnegative and cannot exceed the maximum;
rates are finite and nonnegative. Numeric strings remain accepted and booleans
cannot masquerade as numbers. Generation-check dependencies include payload edits.

Explicit non-continuous `usage_rate` labels produce an unsupported-option warning:
they do not implement a separate scheduled or stochastic consumption process.
Mixed item-source or exchange-payload definitions also warn that a single request
does not visit/load every source/type. Both demand editors explain the confirmed
replenishment and content-mode behavior in their exchange-mode help.

The programmatic simulation summary exposes per-item balances. Full logs retain
coverage counts, final item/resource balances and each request's quantities and
delivered/failed/pending state. Rows have stable event IDs and repeated final saves
do not duplicate them. These records support later Results Investigation stock
metrics; this slice does not yet add a dedicated stock-reconciliation view.

## Verification and manual review

The focused regression set passed **114 tests in 3.187 seconds**, covering stock,
existing zone behavior, waste balances, raw generation checks, provenance, check
staleness and task-generation export.

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_tracked_stock_reference -q
.\.venv\Scripts\python.exe -m verification.run --output verification/latest
.\.venv\Scripts\python.exe -m verification.smoke --config ltn.json --minutes 60 --output verification/latest/tracked-stock-ltn
```

The full pack passed **1,083 / 1,083 tests in 128.173 seconds**, with **zero broken
evidence links** and unchanged source hashes during execution. The inventory now
has 450 unreviewed option entries; this is an audit count, not a missing-feature count.
Evidence is in
`latest/tracked-stock-before.txt`, `latest/tracked-stock-focused.txt`,
`latest/tracked-stock-pack-build.txt` and `latest/evidence.json`.

Both bounded LTN runs completed four tasks with zero failures or pending tasks,
retaining outcome hash
`5368460ed4fd5fd466e832b82d3d6358977abfaccbb456d45e268cfb7c0ab474`.
Outputs are in `latest/tracked-stock-ltn/`. This is bounded regression evidence,
not full LTN acceptance. Unrelated local `ltn.json` edits remain untouched and are
excluded from this checkpoint.

For manual review, import the saved reference and run with full logging. Inspect
`tracked_stock_balance_summary` and the two `tracked_stock_request` records:
sixteen units should be delivered, sixteen consumed and ten left. In a copy,
reduce the door opening to 0.5 m: no supply should arrive, ten units are consumed,
six are unmet and stock ends at zero. Demand Preview shows requests, not proof of
successful replenishment.

## Remaining boundaries and next action

The model assumes initially full logical stock and unlimited supply at configured
sources. Distinct physical handling workflows for top-up versus whole-tote exchange
are not established by these content tests; existing physical handoff behavior is
retained. Cross-rule shared stock, partial deliveries, expiry, shortages at supply
sources and complete mixed-source routes remain open. Legacy/direct task sources
outside the dynamic generator are not connected to these per-rule balances.

Next: reconcile recorded tracked-stock balances with generated requests and actual
delivery/handoff events in Results Investigation, then continue the remaining
legacy/scheduled demand and inventory interaction audit. The later geometry,
approved CAD workflows, tutorial and release-validation gates remain unchanged.
