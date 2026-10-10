# Route-triggered charging — review checkpoint

**D034:** an individual route could need more battery than the preliminary
same-floor distance estimate predicted. Cross-floor connectors, slower movement
and local bay manoeuvres were examples. Even at an operational charger, an exact
shortfall could leave the task pending instead of charging.

An individual route that fits the usable full battery now retries after charging
when the AMR is already at an operational charger. A discarded commit restores
its corridor, lift, inventory, payload and battery state before the retry.
The route is rebuilt at the later time, so a lift occupied after charging is
respected. Only the successful attempt retains reservations and a charge interval.
If the constructed route exceeds full battery minus reserve, the pending reason
states that explicitly; no charge or resource claim is retained.

**D035:** pre-task charging started the segment timeline at charging completion,
then included the charge segment again. Movement and physical pickup/dropoff
events therefore ran late. The plan now starts at charging start and its duration,
resource reservations, physical actions and completion use one consistent timeline.

Baseline failures are in `baseline/route-charge-replanning-before.txt`. The prior
committed simulator (`e798897`) was also loaded in memory to reproduce D035:
`baseline/pre-task-charge-timing-before.json` records pickup/arrival at 342/349
seconds instead of independently expected 172/179 seconds after a 170-second charge.

## Review the saved project

1. Open [route-charge-replanning.json](scenarios/route-charge-replanning.json).
   The deliberately tiny battery makes the calculation easy to inspect; it is
   an engineering reference, not a recommended robot specification.
2. Verify capacity **0.001 kWh**, initial charge **10%**, charge rate **0.036 kW**,
   and reserve **0%**. A is the configured charging location.
3. Run project checks, then simulate. One task should complete, with no failures.
4. Inspect charging, pickup, lift and arrival events against this table.

| Observation | Independent expectation |
| --- | --- |
| Initial energy | 0.001 × 10% = **0.0001 kWh** |
| Required traction | 960 W × 1.035 × 1 second / 3,600,000 = **0.000276 kWh** |
| Recharge | (0.001 − 0.0001) / 0.036 × 3600 = **90 seconds** |
| Pickup | 90 seconds charging + 2 seconds loading = **92 seconds** |
| Lift reservation | Starts after the 0.5-second connector, at **92.5 seconds** |
| Arrival/completion | 90 + 2 + 0.5 + 5 + 0.5 + 2 = **100 seconds** |
| Final battery | (0.001 − 0.000276) / 0.001 × 100 = **72.4%** |

Nine references cover raw/editor-normalised input, pure estimates, route retry,
full-battery excess, failure after charging, later lift conflict, local bay
movement, and physical events in both the old preliminary and new retry paths.
With another lift reservation from 90 to 120 seconds, arrival becomes **127.5
seconds** and traction remains unchanged because the extra interval is waiting.

The full verification pack passes **527/527 tests**, with zero broken evidence
links. The saved reference completes one task, with no failures or pending work,
and frozen-input/event reconciliation passes; see
`latest/route-charge-replanning-reference/summary.json`.

Six-hour LTN remains **203 completed, zero failed and zero pending** in 15.749
seconds. Its detailed result hash is unchanged from the preceding energy checkpoint:
`d14b1f761b262af7d875bb003e63a6bc776b52c2819ed80751b1ea7413b34cd4`.
See `latest/ltn-route-charge-replanning/summary.json`.

## Remaining limits

Automatic charging dispatch from a non-charging location when the battery is above
reserve but inadequate for a particular route is still open. Batches do not yet
charge within their route plan; individual assignment remains available. Fast
assignment estimates can omit local bay effects; the committing route is checked
and can trigger this retry. The full-battery reason applies to the constructed
route at that time; it does not establish that all future traffic or alternative
routes are infeasible. Full-fleet charging optimisation, charging losses and
complete energy/report reconciliation remain open.

The [full roadmap](ROADMAP.md) remains open. Review and automated warning
acknowledgement are separate from human acceptance.
