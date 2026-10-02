# Charger capacity and failure handling — review checkpoint

This checkpoint closes three reproduced defects:

- **D041:** charge-start processing occupied a bay before arrival. A failed bay
  claim still left a completion event capable of filling the battery. Unavailable
  charging also created synthetic failed delivery tasks. Charging now has distinct
  scheduled, travelling, arrived/charging and terminal phases, with cycle IDs that
  reject duplicate or obsolete events. A busy charger records an operational wait;
  a failed arrival/completion records an operational failure with no battery credit.
- **D042:** a delivery completion at the same timestamp as a new assignment could
  clear the newer charger reservation. Completion only attempts to stow a robot
  that has not started charging or been committed beyond that completion time.
- **D043:** local bay routing added an alignment loop even when position and
  heading were identical. An unchanged pose now has zero movement, time and energy.

`baseline/charger-contention-before.txt` records early occupancy and synthetic
failure reproductions at `2551213`. The accompanying
`baseline/charger-contention-interactions-before.json` contains the full inputs
that made two robots reserve the same charger from 16.025968 to 23.811162 seconds.
The second failed its bay claim but both received charging energy. It also records
an invented 1.026248 m / 0.513124 second manoeuvre for an identical start/end pose.

## Review the reference

1. Open [charger-contention.json](scenarios/charger-contention.json). Two robots
   initially deliver from C to A, then collect two longer A-to-B tasks at 10 seconds.
   Only C's single bay can charge them.
2. Run checks and simulate. Expect **four completed deliveries**, zero failed or
   pending tasks, **two successful charge cycles** and peak charger use **one**.
3. Review the charging records: R-1 charges from **15 to 22.38 seconds**; R-2 from
   **27.38 to 34.76 seconds**. Their long deliveries finish at **51.38** and
   **63.76 seconds**, respectively. No charging interval overlaps another.
4. In Results Investigation inspect **Failed charging attempts**, which is known
   zero for this reference, and each model battery balance, which should be Matched.
   Operational charging events are separate from delivery outcomes. Older logs
   without the arrival capability show unknown operational totals.

This deliberately isolates resource accounting. The charger bay centre coincides
with node C, and the second robot initially uses the existing location-node
fallback because only one bay exists. Review that initial-capacity warning; this
is not a geometrically validated parking layout or a production site design.

## Independent calculation

Each robot starts with **0.005 kWh**. The first 10 m loaded delivery consumes
960 × 1.035 × (10/2) / 3,600,000 = **0.00138 kWh**. Its empty 10 m return consumes
720 × (10/2) / 3,600,000 = **0.001 kWh**, leaving **0.00262 kWh** on arrival.
Refilling the 0.01 kWh battery requires **0.00738 kWh**, or **7.38 seconds at
3.6 kW**. The first arrival is 10 + 10/2 = **15 seconds**. The second can depart
for the charger when the first is dispatched again at 22.38 seconds; its arrival
is therefore **27.38 seconds**.

After charging, a 5-second empty approach, 2-second pickup, 20-second loaded route
and 2-second dropoff take **29 seconds**. Per-robot total traction is
0.00138 + 0.001 + 0.001 + 0.00552 = **0.0089 kWh**. Final battery is
0.005 + 0.00738 - 0.0089 = **0.00348 kWh**; fleet charging totals **0.01476 kWh**.

Thirteen references cover raw/editor-normalised saved inputs, the original
simultaneous-completion clash, reservations before arrival, serial bay reuse,
unchanged wait suppression, independent time/energy, lost bays at arrival or
completion, stale/duplicate events, zero-duration cycles, identical poses and
idle-return completion after a newer charging reservation. The latter case was
added after LTN exposed an uninitialised idle-return report field while stowing
was skipped; the corrected full LTN run passes.
Two older tests now expect operational wait evidence and an explicit arrival
event instead of a synthetic failed task and immediate occupancy.

The full verification pack passes **592/592 tests**, with **zero broken evidence
links**. The saved reference completes **4 tasks**, no failed or pending work,
and two matching battery balances. Its applied charging is **0.01476 kWh**.
See `latest/charger-contention-reference/summary.json` and
`latest/charger-contention-balances.json`.

The six-hour LTN run completes **203 tasks**, no failed or pending work, in
**16.192 seconds** (an observation, not a controlled performance threshold).
All **22 battery balances match**, with **3.931007709822394 kWh** applied charge
and zero failed charging attempts. Its detailed task outcome hash is unchanged:
`cbbdd6eba406e47d09ca44d14115111acf9f06ac967044715b65d64ee850f79b`.
Frozen inputs and task outcomes reconcile; see `latest/ltn-charger-contention/summary.json`.

## Limits

The `is_charging` scheduling flag still covers travel as well as charging; event
phases distinguish them. The robot retains its bay after charging until it leaves.
The scheduler retries available work; this is not a FIFO charger queue or an
automatic policy to relocate an idle full robot. Locations without explicit bays
retain legacy unbounded location-level charging.
The charging-wait metric counts explicit charging-attempt observations only.
Route-required tasks can also wait through their ordinary pending reasons, so
zero observations does not establish zero time waiting for charge.

Bay-loss tests inject runtime faults; they do not introduce a user-configurable
charger-failure scenario. Bay availability is rechecked at arrival and completion,
not continuously monitored between those events. A cycle rejected at completion
credits no energy under the existing completion-credit model; fractional charge
during a failed/interrupted cycle remains unmodelled. Failed zero-duration arrivals
are excluded from charger-use estimates; failed occupied intervals are truncated
at failure, while their planned end remains recorded. These estimates still mix
planned and completed demand and are not a measured electrical-load forecast.
The [full roadmap](ROADMAP.md) remains open.
